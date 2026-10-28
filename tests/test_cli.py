import json
from pathlib import Path
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_cli_resume_and_refuses_changed_config(tmp_path):
    cfg = yaml.safe_load((ROOT / 'configs/smoke.yaml').read_text())
    cfg['conditions'] = [cfg['conditions'][2]]
    path = tmp_path / 'config.yaml'
    path.write_text(yaml.safe_dump(cfg))
    output = tmp_path / 'run'
    cmd = [sys.executable, '-m', 'bra_audit.cli', 'run', '--root', str(ROOT),
           '--config', str(path), '--output', str(output), '--limit', '1']
    first = subprocess.run(cmd, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    examples = list((output / 'examples').glob('*.json'))
    assert len(examples) == 2
    mtimes = {p: p.stat().st_mtime_ns for p in examples}
    second = subprocess.run(cmd, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    assert mtimes == {p: p.stat().st_mtime_ns for p in examples}
    assert all(r['complete'] and r['smoke'] for r in json.loads((output/'summary.json').read_text()))
    cfg['experiment']['rounds'] += 1
    path.write_text(yaml.safe_dump(cfg))
    changed = subprocess.run(cmd, capture_output=True, text=True)
    assert changed.returncode != 0
    assert 'Run differs' in changed.stderr
