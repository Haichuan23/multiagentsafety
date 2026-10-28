import hashlib
import json
from pathlib import Path
import random


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(root, seed=42):
    root = Path(root)
    rows = []
    for path in sorted((root / 'vendor/BIG-Bench-Hard-main/bbh').glob('*.json')):
        for i, ex in enumerate(json.loads(path.read_text())['examples']):
            rows.append(dict(id=f'{path.stem}:{i}', benchmark='bbh', task=path.stem,
                             input=ex['input'], target=ex['target']))
    if len(rows) < 150:
        raise ValueError('Official BBH source missing or incomplete')
    random.Random(seed).shuffle(rows)
    write_jsonl(root / 'data/bbh150.jsonl', rows[:150])
    research = []
    for line in (root / 'data/research_upstream.jsonl').read_text().splitlines():
        ex = json.loads(line)
        research.append(dict(id=f"research:{ex['task_id']}", benchmark='research',
                             input=ex['task']['content'], profiles=ex['agents']))
    write_jsonl(root / 'data/research100.jsonl', research)
    manifest = dict(sample_seed=seed, bbh_pool_size=len(rows), bbh_sample_size=150,
                    research_size=len(research), files={})
    for path in sorted((root / 'vendor/BIG-Bench-Hard-main/bbh').glob('*.json')):
        manifest['files'][str(path.relative_to(root))] = file_hash(path)
    for rel in ['data/bbh150.jsonl', 'data/research100.jsonl', 'data/research_upstream.jsonl',
                'vendor/marble_evaluator_prompts.json', 'paper/BRA-audit.pdf']:
        manifest['files'][rel] = file_hash(root / rel)
    (root / 'data/manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def write_jsonl(path, rows):
    Path(path).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))


def load(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    ids = [r['id'] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f'Duplicate example ids in {path}')
    return rows
