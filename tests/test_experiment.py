from copy import deepcopy
import json
from pathlib import Path
import yaml
import pytest
from bra_audit.backends import Router
from bra_audit.experiment import run_example, AuditFailure
from bra_audit.protocol import exact_match

ROOT = Path(__file__).resolve().parents[1]


def config():
    return yaml.safe_load((ROOT / 'configs/smoke.yaml').read_text())


def example():
    return dict(id='fixture', benchmark='bbh', input='Fixture task', target='smoke-answer')


def test_recovery_accounting_no_answer_leak(tmp_path):
    cfg = config()
    router = Router(cfg, tmp_path)
    ex = example()
    ex['target'] = 'SECRET_GOLD_SHOULD_NEVER_BE_IN_PROMPTS'
    result = run_example(ex, cfg, cfg['conditions'][2], 42, router, ROOT)
    assert result['score'] == 0
    assert result['rollback_calls'] > 0
    assert result['audit_calls'] > sum(x.get('budget', 0) for x in result['audit_log'])
    assert result['tokens']['rollback'] > 0
    assert result['total_tokens'] == sum(result['tokens'][k] for k in ['work', 'audit', 'rollback'])
    assert 'SECRET_GOLD_SHOULD_NEVER_BE_IN_PROMPTS' not in json.dumps(router.events)
    for call in router.events:
        if call['role'] == 'auditor':
            assert 'malicious_agents' not in call['messages'][-1]['content']


def test_research_rubric_and_cost(tmp_path):
    cfg = config()
    router = Router(cfg, tmp_path)
    ex = dict(id='research-fixture', benchmark='research', input='Fixture idea')
    result = run_example(ex, cfg, cfg['conditions'][2], 42, router, ROOT)
    assert result['score'] == .6
    assert result['tokens']['evaluation'] > 0
    assert result['total_tokens'] + result['tokens']['evaluation'] == sum(result['tokens'].values())


def test_resume_cache_preserves_experimental_cost(tmp_path):
    cfg = config()
    first = Router(cfg, tmp_path)
    a = run_example(example(), cfg, cfg['conditions'][2], 42, first, ROOT)
    second = Router(cfg, tmp_path)
    b = run_example(example(), cfg, cfg['conditions'][2], 42, second, ROOT)
    assert a['tokens'] == b['tokens']
    assert all(x['cache_hit'] for x in second.ledger)
    assert a['outputs'] == b['outputs']


def test_retry_limit_fails_closed(tmp_path):
    cfg = config()
    cfg['experiment']['max_recovery_attempts'] = 0
    with pytest.raises(AuditFailure):
        run_example(example(), cfg, cfg['conditions'][4], 42, Router(cfg, tmp_path), ROOT)


@pytest.mark.parametrize('prediction,target,want', [
    ('Reason.\nFINAL: (A)', '(A)', 1), ('FINAL: A.', '(A)', 1),
    ('Reason mentions (A)\nFINAL: (B)', '(A)', 0),
    ('FINAL: not true', 'true', 0), ('FINAL: YES', 'yes', 1),
    ('FINAL: [1, 2]', '[1, 2]', 1)])
def test_answer_scoring(prediction, target, want):
    assert exact_match(prediction, target) == want


def test_malformed_auditor_cannot_pass(tmp_path):
    cfg = config()
    class InvalidAuditor(Router):
        def call(self, role, *args, **kwargs):
            if role == 'auditor':
                return '{"safe": "true", "reason": "bad schema"}'
            return super().call(role, *args, **kwargs)
    with pytest.raises(ValueError, match='JSON boolean'):
        run_example(example(), cfg, cfg['conditions'][2], 42, InvalidAuditor(cfg, tmp_path), ROOT)


def test_recovered_final_region_has_no_fixture_corruption(tmp_path):
    cfg = config()
    for condition in cfg['conditions']:
        result = run_example(example(), cfg, condition, 42, Router(cfg, tmp_path/condition['name']), ROOT)
        assert 'SMOKE_CORRUPTION' not in result['final']
        assert result['audit_log'][-1]['verdict']['safe'] is True
