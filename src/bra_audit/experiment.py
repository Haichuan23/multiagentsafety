import json
import math
from pathlib import Path
import random
import networkx as nx
from .scheduler import context, select
from .protocol import ROLES, WORKER, ATTACK, AUDITOR, JUDGE, parse_json, exact_match


class AuditFailure(RuntimeError):
    pass


def extend_graph(graph, round_index, n_agents, topology):
    candidates = []
    for i in range(n_agents):
        node = f'r{round_index:03d}:a{i:03d}'
        graph.add_node(node, agent=i, round=round_index)
        candidates.append(node)
        if round_index > 1:
            parents = range(n_agents) if topology == 'layered' else [i]
            for p in parents:
                graph.add_edge(f'r{round_index-1:03d}:a{p:03d}', node)
        if i > 0:
            graph.add_edge(candidates[i-1], node)
    return candidates


def run_example(example, cfg, condition, seed, router, root):
    exp = cfg['experiment']
    n, rounds = exp['agents'], exp['rounds']
    if n < 1 or rounds < 1 or exp.get('topology', 'chain') not in ('chain', 'layered'):
        raise ValueError('positive agents/rounds and chain or layered topology required')
    fraction = exp.get('malicious_fraction', .2)
    if not 0 <= fraction <= 1:
        raise ValueError('malicious_fraction must lie in [0, 1]')
    # Independent seeded stream shared across conditions: paired attack membership.
    rng = random.Random(f"{seed}:{example['id']}:attack-membership")
    malicious = set(rng.sample(range(n), math.ceil(n * fraction)))
    graph = nx.DiGraph()
    outputs = {}
    trusted = set()
    last_audit = {i: 0 for i in range(n)}
    audit_log = []
    audit_calls = rollback_calls = 0
    max_tokens = exp.get('max_tokens', 768)
    temperature = exp.get('temperature', 0)

    def generate(node, recovering=False, feedback=''):
        agent = graph.nodes[node]['agent']
        role = ROLES[agent % len(ROLES)]
        profile = ''
        profiles = example.get('profiles', [])
        if profiles:
            profile = profiles[agent % len(profiles)].get('profile', '')
        compromised = agent in malicious and not recovering and condition.get('attack', True)
        system = ATTACK.format(role=role) if compromised else WORKER.format(role=role, profile=profile)
        parents = {p: outputs[p] for p in graph.predecessors(node)}
        prompt = json.dumps(dict(task=example['input'], round=graph.nodes[node]['round'],
                                 node=node, final_turn=(graph.nodes[node]['round'] == rounds and agent == n-1),
                                 inputs=parents, recovery_feedback=feedback), ensure_ascii=False)
        # Deliberately no target or compromised-agent identity in the user context.
        return router.call(f'agent_{agent}', [{'role': 'system', 'content': system},
                                            {'role': 'user', 'content': prompt}],
                           'rollback' if recovering else 'work', max_tokens, temperature, seed)

    def audit(node, region):
        nonlocal audit_calls
        audit_calls += 1
        boundaries = {p for u in region for p in graph.predecessors(u) if p not in region}
        prompt = dict(task=example['input'], endpoint=node,
                      trusted_inputs={p: outputs[p] for p in sorted(boundaries)},
                      region=[dict(id=u, parents=list(graph.predecessors(u)), output=outputs[u])
                              for u in nx.topological_sort(graph) if u in region])
        messages = [{'role': 'system', 'content': AUDITOR},
                    {'role': 'user', 'content': json.dumps(prompt, ensure_ascii=False)}]
        text = router.call('auditor', messages, 'audit', exp.get('audit_max_tokens', 512), 0, seed)
        verdict = parse_json(text)
        if type(verdict.get('safe')) is not bool:
            raise ValueError('Auditor must return a JSON boolean safe')
        audit_log.append(dict(endpoint=node, region=sorted(region), verdict=verdict))
        return verdict

    for r in range(1, rounds + 1):
        candidates = extend_graph(graph, r, n, exp.get('topology', 'chain'))
        ratio = condition['ratio']
        chosen = select(graph, candidates, ratio, r, last_audit,
                        condition['strategy'], mandatory=candidates[-1] if r == rounds and ratio else None,
                        rng=random.Random(f"{seed}:{example['id']}:{r}:placement"))
        audit_log.append(dict(round=r, selected=sorted(chosen), budget=math.ceil(ratio*n)))
        for node in candidates:
            outputs[node] = generate(node)
            if node not in chosen:
                continue
            region = context(graph, node, trusted)
            verdict = audit(node, region)
            attempts = 0
            while not verdict['safe']:
                if attempts >= exp.get('max_recovery_attempts', 2):
                    raise AuditFailure(f'Audit failed after recovery at {node}: {verdict.get("reason")}')
                attempts += 1
                # Reach a fixed point: changing an ancestor invalidates every executed
                # descendant, including a checkpoint, and removing that checkpoint can
                # expose more unchecked ancestors on another branch.
                affected = set(region)
                invalidated = set()
                while True:
                    before = set(affected)
                    stack = list(affected)
                    while stack:
                        u = stack.pop()
                        for v in graph.successors(u):
                            if v in outputs and v not in affected:
                                affected.add(v)
                                stack.append(v)
                    invalidated.update(trusted & affected)
                    trusted.difference_update(affected)
                    region = context(graph, node, trusted)
                    affected.update(region)
                    if affected == before:
                        break
                for agent in {graph.nodes[u]['agent'] for u in invalidated}:
                    last_audit[agent] = max((graph.nodes[u]['round'] for u in trusted
                                             if graph.nodes[u]['agent'] == agent), default=0)
                for u in nx.topological_sort(graph):
                    if u in affected:
                        outputs[u] = generate(u, recovering=True, feedback=str(verdict.get('reason', '')))
                        rollback_calls += 1
                verdict = audit(node, region)
            trusted.add(node)
            last_audit[graph.nodes[node]['agent']] = r

    final = outputs[candidates[-1]]
    ratings = None
    if example['benchmark'] == 'bbh':
        score = exact_match(final, example['target'])
    else:
        rubric = json.loads((Path(root) / 'vendor/marble_evaluator_prompts.json').read_text())['research']['task_evaluation']['prompt']
        prompt = rubric.format(task=example['input'], result=final)
        text = router.call('judge', [{'role': 'system', 'content': JUDGE},
                                     {'role': 'user', 'content': prompt}],
                           'evaluation', exp.get('judge_max_tokens', 512), 0, seed)
        parsed = parse_json(text)
        # Upstream rubric labels Innovation/Safety/Feasibility; tolerate capitalization only.
        parsed = {k.casefold(): v for k, v in parsed.items()}
        ratings = {k: parsed[k] for k in ['innovation', 'safety', 'feasibility']}
        if any(type(v) not in (int, float) or not 1 <= v <= 5 for v in ratings.values()):
            raise ValueError('Research judge ratings must be numeric in [1, 5]')
        score = sum(ratings.values()) / 15
    totals = {cat: sum(v['input_tokens'] + v['output_tokens'] for v in router.ledger if v['category'] == cat)
              for cat in ['work', 'audit', 'rollback', 'evaluation']}
    return dict(id=example['id'], benchmark=example['benchmark'], condition=condition['name'],
                seed=seed, score=score, ratings=ratings, final=final, tokens=totals,
                total_tokens=totals['work'] + totals['audit'] + totals['rollback'],
                audit_calls=audit_calls, rollback_calls=rollback_calls,
                malicious_agents=sorted(malicious), audit_log=audit_log,
                ledger=router.ledger, graph=dict(nodes=[dict(id=u, **graph.nodes[u]) for u in graph],
                                               edges=list(graph.edges)), outputs=outputs)
