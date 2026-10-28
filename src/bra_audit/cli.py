import argparse
import csv
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import statistics
import sys
import time
import traceback
import yaml
from .backends import Router
from .data import prepare, load, file_hash
from .experiment import run_example


def atomic_json(path, value):
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    tmp.replace(path)


def summarize(output):
    output = Path(output)
    manifest = json.loads((output / 'manifest.json').read_text())
    rows = [json.loads(p.read_text()) for p in sorted((output / 'examples').glob('*.json'))]
    result = []
    for bench in manifest['data']:
        for condition in manifest['config']['conditions']:
            selected = [r for r in rows if r['benchmark'] == bench and r['condition'] == condition['name']]
            if not selected:
                continue
            seeds = manifest['config']['experiment']['seeds']
            per_seed = []
            for seed in seeds:
                values = [r['score'] for r in selected if r['seed'] == seed]
                if values:
                    per_seed.append(statistics.mean(values))
            expected = len(manifest['data'][bench]['selected_ids']) * len(seeds)
            row = dict(benchmark=bench, condition=condition['name'], n=len(selected), expected=expected,
                       complete=len(selected) == expected, smoke=manifest['smoke'],
                       score=statistics.mean(r['score'] for r in selected),
                       seed_std=statistics.stdev(per_seed) if len(per_seed) > 1 else None,
                       audit_k=statistics.mean(r['tokens']['audit'] for r in selected) / 1000,
                       rollback_k=statistics.mean(r['tokens']['rollback'] for r in selected) / 1000,
                       total_k=statistics.mean(r['total_tokens'] for r in selected) / 1000,
                       work_k=statistics.mean(r['tokens']['work'] for r in selected) / 1000,
                       evaluation_k=statistics.mean(r['tokens']['evaluation'] for r in selected) / 1000,
                       estimated_usage=any(v['estimated'] for r in selected for v in r['ledger']))
            result.append(row)
    atomic_json(output / 'summary.json', result)
    if result:
        with (output / 'table5.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(result[0]))
            writer.writeheader()
            writer.writerows(result)
    print(json.dumps(result, indent=2))
    return result


def run(args):
    root = Path(args.root).resolve()
    cfg = json.loads(json.dumps(yaml.safe_load(Path(args.config).read_text())))
    if len({x['name'] for x in cfg['conditions']}) != len(cfg['conditions']):
        raise ValueError('Condition names must be unique')
    if len(set(cfg['experiment']['seeds'])) != len(cfg['experiment']['seeds']):
        raise ValueError('Seeds must be unique')
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    lock = (output / '.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError(f'Another runner is using {output}')
    datasets, metadata = {}, {}
    if args.benchmark != 'all':
        benches = [args.benchmark]
    else:
        benches = list(cfg['data'])
    for bench in benches:
        path = root / cfg['data'][bench]
        rows = load(path)
        if not rows or any(r['benchmark'] != bench for r in rows):
            raise ValueError(f'Empty or mismatched benchmark data: {path}')
        if args.limit:
            rows = rows[:args.limit]
        datasets[bench] = rows
        metadata[bench] = dict(path=str(path), sha256=file_hash(path), selected_ids=[r['id'] for r in rows])
    smoke = any(s['backend'] == 'mock' for s in cfg['models'].values())
    # Hash config, exact data selection and implementation: never silently mix outputs.
    source_hash = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob('*.py')):
        source_hash.update(path.name.encode() + path.read_bytes())
    packages = {}
    for name in ['bra-audit-reconstruction', 'networkx', 'httpx', 'PyYAML', 'torch', 'transformers', 'accelerate']:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    spec = dict(config=cfg, data=metadata, smoke=smoke, source_sha256=source_hash.hexdigest(),
                rubric_sha256=file_hash(root / 'vendor/marble_evaluator_prompts.json'),
                python=sys.version, packages=packages)
    fingerprint = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
    manifest_path = output / 'manifest.json'
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text())
        if old['fingerprint'] != fingerprint:
            raise ValueError('Run differs from existing manifest. Use a new output directory.')
    else:
        atomic_json(manifest_path, dict(**spec, fingerprint=fingerprint, created_unix=time.time()))
    (output / 'examples').mkdir(exist_ok=True)
    (output / 'failures').mkdir(exist_ok=True)
    (output / 'traces').mkdir(exist_ok=True)
    router = Router(cfg, output / 'cache')
    failures = 0
    for bench, examples in datasets.items():
        for condition in cfg['conditions']:
            for seed in cfg['experiment']['seeds']:
                for example in examples:
                    key = hashlib.sha256(f"{bench}:{condition['name']}:{seed}:{example['id']}".encode()).hexdigest()[:24]
                    destination = output / 'examples' / f'{key}.json'
                    if destination.exists():
                        continue
                    router.call_index = 0
                    router.ledger = []
                    router.events = []
                    started = time.monotonic()
                    print(f"RUN {bench} {condition['name']} seed={seed} id={example['id']}", flush=True)
                    try:
                        result = run_example(example, cfg, condition, seed, router, root)
                        result['wall_seconds'] = time.monotonic() - started
                        atomic_json(output / 'traces' / f'{key}.json', router.events)
                        atomic_json(destination, result)
                        (output / 'failures' / f'{key}.json').unlink(missing_ok=True)
                    except Exception as exc:
                        failures += 1
                        atomic_json(output / 'traces' / f'{key}.json', router.events)
                        atomic_json(output / 'failures' / f'{key}.json',
                                    dict(benchmark=bench, condition=condition['name'], seed=seed,
                                         id=example['id'], error=str(exc), traceback=traceback.format_exc(),
                                         ledger=router.ledger))
                        print(f'FAILED {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
                        if not args.keep_going:
                            summarize(output)
                            raise
    summarize(output)
    lock.close()
    if failures:
        raise SystemExit(f'{failures} examples failed; inspect failures/. Rerun to retry.')


def main():
    parser = argparse.ArgumentParser(description='BRA-Audit Table 5 reconstruction')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare-data')
    p.add_argument('--root', default='.')
    p.add_argument('--seed', type=int, default=42)
    p = sub.add_parser('run')
    p.add_argument('--root', default='.')
    p.add_argument('--config', default='configs/smoke.yaml')
    p.add_argument('--output', default='results/smoke')
    p.add_argument('--benchmark', choices=['all', 'bbh', 'research'], default='all')
    p.add_argument('--limit', type=int, default=1, help='Examples per benchmark; 0 means all (explicit full run)')
    p.add_argument('--keep-going', action='store_true')
    p = sub.add_parser('summarize')
    p.add_argument('output')
    p = sub.add_parser('download-models')
    p.add_argument('--config', required=True)
    args = parser.parse_args()
    if args.command == 'prepare-data':
        print(json.dumps(prepare(args.root, args.seed), indent=2))
    elif args.command == 'summarize':
        summarize(args.output)
    elif args.command == 'download-models':
        from huggingface_hub import snapshot_download
        cfg = json.loads(json.dumps(yaml.safe_load(Path(args.config).read_text())))
        for model, revision in sorted({(s['model'], s.get('revision', 'main'))
                                       for s in cfg['models'].values() if s['backend'] == 'hf'}):
            print(snapshot_download(model, revision=revision))
    else:
        if args.limit < 0:
            parser.error('--limit must be nonnegative')
        run(args)


if __name__ == '__main__':
    main()
