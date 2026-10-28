"""Download two tiny random HF models and exercise real model loading/generation.
No benchmark score is produced. Intended for CPU login-node interface validation.
"""
import json
from pathlib import Path
from bra_audit.backends import Router

cfg = dict(default_model='llama', models={
    'llama': dict(backend='hf', model='hf-internal-testing/tiny-random-LlamaForCausalLM',
                  device_map={'': 'cpu'}, dtype='float32', max_context=2048),
    'gpt2': dict(backend='hf', model='hf-internal-testing/tiny-random-gpt2',
                 device_map={'': 'cpu'}, dtype='float32', max_context=512),
}, routes={'auditor': 'gpt2'})
router = Router(cfg, Path('results/hf-interface-smoke/cache'))
for role in ['agent_0', 'auditor']:
    answer = router.call(role, [{'role':'user', 'content':'Reply hello.'}], 'work', 8, 0, 42)
    assert isinstance(answer, str)
    assert router.ledger[-1]['output_tokens'] > 0
    print(json.dumps(dict(role=role, model=router.spec(role)['model'], output=answer,
                         usage=router.ledger[-1])))
# Distinct model configurations must coexist; one shared model per logical agent is optional.
if not all(x['cache_hit'] for x in router.ledger):
    assert len(router.instances) == 2
Path('results/hf-interface-smoke/validation.json').write_text(json.dumps(router.ledger, indent=2)+'\n')
print('PASS: two real HF models load and generate on CPU; CUDA placement requires a GPU node.')
