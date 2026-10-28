"""Per-role model routing, OpenAI-compatible HTTP, shared or distinct HF models."""
from dataclasses import dataclass, asdict
import hashlib
import json
import os
from pathlib import Path
import random
import time
import httpx


@dataclass
class Reply:
    text: str
    input_tokens: int
    output_tokens: int
    estimated: bool = False


class APIBackend:
    def __init__(self, spec):
        self.spec = spec
        self.client = httpx.Client(timeout=spec.get('timeout', 180))

    def complete(self, messages, max_tokens, temperature, seed):
        spec = self.spec
        key = os.environ.get(spec.get('api_key_env', 'OPENAI_API_KEY'), '')
        if not key and spec.get('require_key', True):
            raise RuntimeError(f"Set {spec.get('api_key_env', 'OPENAI_API_KEY')} for {spec['model']}")
        payload = dict(model=spec['model'], messages=messages, temperature=temperature,
                       **{spec.get('token_parameter', 'max_tokens'): max_tokens})
        if spec.get('send_seed', False):
            payload['seed'] = seed
        payload.update(spec.get('extra_body', {}))
        headers = {'Authorization': f'Bearer {key}'} if key else {}
        url = spec['base_url'].rstrip('/') + '/chat/completions'
        for attempt in range(spec.get('retries', 3) + 1):
            try:
                response = self.client.post(url, json=payload, headers=headers)
                if response.status_code in (429, 500, 502, 503, 504):
                    response.raise_for_status()
                response.raise_for_status()
                data = response.json()
                content = data['choices'][0]['message']['content']
                if not isinstance(content, str):
                    raise ValueError('API returned no textual content')
                usage = data.get('usage', {})
                if 'prompt_tokens' not in usage or 'completion_tokens' not in usage:
                    if not spec.get('allow_estimated_usage', False):
                        raise ValueError('API did not return token usage; enable allow_estimated_usage explicitly')
                    return Reply(content, max(1, len(json.dumps(messages)) // 4),
                                 max(1, len(content) // 4), True)
                return Reply(content, int(usage['prompt_tokens']), int(usage['completion_tokens']))
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                retryable = not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code in (429, 500, 502, 503, 504)
                if not retryable or attempt == spec.get('retries', 3):
                    raise
                time.sleep(min(2 ** attempt, 10))
        raise RuntimeError('unreachable')


class HFBackend:
    def __init__(self, spec):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        self.spec = spec
        revision = spec.get('revision', 'main')
        self.tokenizer = AutoTokenizer.from_pretrained(spec['model'], revision=revision,
                                                       trust_remote_code=False)
        dtype = spec.get('dtype', 'auto')
        kwargs = dict(revision=revision, trust_remote_code=False,
                      torch_dtype=getattr(torch, dtype) if dtype != 'auto' else 'auto',
                      device_map=spec.get('device_map', 'auto'))
        if spec.get('max_memory'):
            kwargs['max_memory'] = {int(k) if str(k).isdigit() else k: v
                                    for k, v in spec['max_memory'].items()}
        self.model = AutoModelForCausalLM.from_pretrained(spec['model'], **kwargs).eval()

    def complete(self, messages, max_tokens, temperature, seed):
        torch, tok = self.torch, self.tokenizer
        torch.manual_seed(seed)
        if tok.chat_template:
            prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                            **self.spec.get('chat_template_kwargs', {}))
            batch = tok(prompt, return_tensors='pt', add_special_tokens=False)
        else:
            prompt = '\n'.join(f"{m['role']}: {m['content']}" for m in messages) + '\nassistant:'
            batch = tok(prompt, return_tensors='pt')
        limit = self.spec.get('max_context', getattr(self.model.config, 'max_position_embeddings', 32768))
        if batch.input_ids.shape[1] + max_tokens > limit:
            raise ValueError(f'Context length exceeds {limit}; reduce rounds/tokens or use a larger context model')
        device = self.model.get_input_embeddings().weight.device
        # Accelerate offload hooks can leave embedding weights on the meta device;
        # CPU inputs retain their values and the hook moves them to its execution device.
        batch = batch.to('cpu' if device.type == 'meta' else device)
        kwargs = dict(max_new_tokens=max_tokens, do_sample=temperature > 0,
                      pad_token_id=tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id)
        if temperature > 0:
            kwargs['temperature'] = temperature
        with torch.inference_mode():
            out = self.model.generate(**batch, **kwargs)
        generated = out[0, batch.input_ids.shape[1]:]
        return Reply(tok.decode(generated, skip_special_tokens=True), batch.input_ids.shape[1], len(generated))


class MockBackend:
    """Offline plumbing fixture. Never a scientific result or an oracle for real tasks."""
    def complete(self, messages, max_tokens, temperature, seed):
        mode = messages[0]['content']
        if 'AUDITOR_PROTOCOL' in mode:
            unsafe = 'SMOKE_CORRUPTION' in messages[-1]['content']
            text = json.dumps({'safe': not unsafe, 'reason': 'fixture corruption' if unsafe else 'fixture pass'})
        elif 'JUDGE_PROTOCOL' in mode:
            text = json.dumps({'innovation': 3, 'safety': 3, 'feasibility': 3})
        elif 'ATTACK_PROTOCOL' in mode:
            text = 'SMOKE_CORRUPTION: intentionally incorrect fixture claim. FINAL: wrong'
        else:
            text = 'Fixture reasoning only. FINAL: smoke-answer'
        return Reply(text, max(1, len(json.dumps(messages)) // 4), max(1, len(text) // 4), True)


class Router:
    def __init__(self, config, cache_dir):
        # YAML GPU memory maps can mix numeric GPU keys with the string cpu.
        self.config = json.loads(json.dumps(config))
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.instances = {}
        self.call_index = 0
        self.ledger = []
        self.events = []

    def spec(self, role):
        name = self.config.get('routes', {}).get(role, self.config['default_model'])
        return self.config['models'][name]

    def call(self, role, messages, category, max_tokens, temperature, seed):
        spec = self.spec(role)
        # A cache slot is unique to a logical call, but deterministic on task restart.
        request = dict(spec=spec, messages=messages, max_tokens=max_tokens,
                       temperature=temperature, seed=seed, slot=self.call_index)
        self.call_index += 1
        digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        path = self.cache_dir / f'{digest}.json'
        cached = path.exists()
        if cached:
            reply = Reply(**json.loads(path.read_text()))
        else:
            key = json.dumps(spec, sort_keys=True)
            if key not in self.instances:
                cls = {'mock': MockBackend, 'api': APIBackend, 'hf': HFBackend}[spec['backend']]
                self.instances[key] = cls() if spec['backend'] == 'mock' else cls(spec)
            reply = self.instances[key].complete(messages, max_tokens, temperature, seed)
            tmp = path.with_suffix('.tmp')
            tmp.write_text(json.dumps(asdict(reply)))
            tmp.replace(path)
        self.ledger.append(dict(category=category, role=role, input_tokens=reply.input_tokens,
                                output_tokens=reply.output_tokens, estimated=reply.estimated,
                                cache_hit=cached, request_sha256=digest))
        self.events.append(dict(role=role, category=category, messages=messages, response=asdict(reply)))
        return reply.text
