"""Exercise the actual HTTP backend against an in-process protocol server."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import pytest
from bra_audit.backends import APIBackend, Router
from bra_audit.experiment import run_example
from pathlib import Path
import yaml


@pytest.fixture
def api_server():
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append((self.path, body))
            mode = body['messages'][0]['content']
            if 'AUDITOR_PROTOCOL' in mode:
                text = json.dumps({'safe': 'SMOKE_CORRUPTION' not in body['messages'][-1]['content'], 'reason': 'test'})
            elif 'ATTACK_PROTOCOL' in mode:
                text = 'SMOKE_CORRUPTION\nFINAL: wrong'
            else:
                text = 'FINAL: smoke-answer'
            data = json.dumps({'choices':[{'message': {'content':text}}],
                               'usage': {'prompt_tokens': 50, 'completion_tokens': 10}}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}/v1', requests
    server.shutdown()
    server.server_close()
    thread.join()


def test_real_http_and_usage(api_server):
    url, requests = api_server
    backend = APIBackend(dict(model='test', base_url=url, require_key=False))
    reply = backend.complete([{'role':'user','content':'hello'}], 20, 0, 42)
    assert (reply.input_tokens, reply.output_tokens, reply.estimated) == (50, 10, False)
    assert requests[0][0] == '/v1/chat/completions'
    assert requests[0][1]['max_tokens'] == 20


def test_api_multiagent_end_to_end(api_server, tmp_path):
    url, requests = api_server
    root = Path(__file__).resolve().parents[1]
    cfg = yaml.safe_load((root / 'configs/smoke.yaml').read_text())
    cfg['models'] = {'test': dict(backend='api', model='test', base_url=url, require_key=False)}
    cfg['default_model'] = 'test'
    result = run_example(dict(id='http-fixture', benchmark='bbh', input='Test', target='smoke-answer'),
                         cfg, cfg['conditions'][2], 42, Router(cfg, tmp_path), root)
    assert result['score'] == 1
    assert result['rollback_calls'] > 0
    assert result['total_tokens'] == len(requests) * 60


def test_missing_key_fails_early(monkeypatch):
    monkeypatch.delenv('BRA_TEST_MISSING_KEY', raising=False)
    b = APIBackend(dict(model='test',base_url='https://invalid.example/v1',api_key_env='BRA_TEST_MISSING_KEY'))
    with pytest.raises(RuntimeError, match='BRA_TEST_MISSING_KEY'):
        b.complete([], 1, 0, 0)


def test_yaml_gpu_memory_keys_are_canonicalized(tmp_path):
    cfg = dict(default_model='m', models={'m': dict(backend='mock', model='fixture',
               max_memory={0: '20GiB', 'cpu': '40GiB'})})
    router = Router(cfg, tmp_path)
    router.call('agent_0', [{'role':'system','content':'worker'}], 'work', 8, 0, 42)
    assert router.spec('agent_0')['max_memory'] == {'0': '20GiB', 'cpu': '40GiB'}
