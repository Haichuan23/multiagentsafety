"""Exact cumulative exposure and greedy marginal gains: paper Eqs. 7–13."""
import math
import random
import networkx as nx


def context(graph: nx.DiGraph, node: str, cuts: set[str]) -> set[str]:
    # The endpoint stays unchecked; upstream cut outputs are trusted boundaries.
    found = {node}
    stack = list(graph.predecessors(node))
    while stack:
        u = stack.pop()
        if u in cuts or u in found:
            continue
        found.add(u)
        stack.extend(graph.predecessors(u))
    return found


def weights(graph, round_index, last_audit):
    return {u: (round_index - last_audit.get(graph.nodes[u]['agent'], 0))
            * (1 + len(nx.descendants(graph, u))) for u in graph}


def exposure(graph, cuts, node_weights):
    return sum(sum(node_weights[u] for u in context(graph, v, cuts)) for v in graph)


def select(graph, candidates, ratio, round_index, last_audit, strategy='bra',
           mandatory=None, rng=None):
    if not 0 <= ratio <= 1:
        raise ValueError('audit ratio must be between zero and one')
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError('execution graph must be a DAG')
    candidates = sorted(set(candidates))
    if not set(candidates) <= set(graph):
        raise ValueError('unknown audit candidate')
    budget = math.ceil(ratio * len(candidates))
    if mandatory is not None and (mandatory not in candidates or budget == 0):
        raise ValueError('mandatory final audit must fit inside the budget')
    chosen = {mandatory} if mandatory is not None else set()
    if strategy == 'random':
        chosen.update((rng or random.Random(0)).sample(
            [v for v in candidates if v not in chosen], budget - len(chosen)))
    elif strategy == 'bra':
        w = weights(graph, round_index, last_audit)
        while len(chosen) < budget:
            old = exposure(graph, chosen, w)
            # Sorted iteration gives reproducible ties; recompute after every placement.
            gains = [(old - exposure(graph, chosen | {v}, w), v)
                     for v in candidates if v not in chosen]
            best = max(g for g, _ in gains)
            chosen.add(next(v for g, v in gains if g == best))
    else:
        raise ValueError(f'unknown scheduler: {strategy}')
    return chosen
