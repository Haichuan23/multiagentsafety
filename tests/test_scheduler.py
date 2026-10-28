import itertools
import math
import random
import networkx as nx
import pytest
from bra_audit.scheduler import context, exposure, weights, select


def graph(edges, nodes=()):
    g = nx.DiGraph(edges)
    g.add_nodes_from(nodes)
    for i, u in enumerate(g):
        g.nodes[u]['agent'] = i
    return g


def test_bypass_path_preserved():
    g = graph([('a', 'b'), ('a', 'c'), ('b', 'd'), ('c', 'd')])
    assert context(g, 'd', {'b'}) == {'a', 'c', 'd'}
    assert context(g, 'd', {'b', 'c'}) == {'d'}
    assert context(g, 'b', {'b'}) == {'a', 'b'}


def test_context_against_path_definition():
    # Exhaustive paths oracle over random small DAGs, including bypass branches.
    rng = random.Random(8)
    for _ in range(30):
        g = graph([(str(i), str(j)) for i in range(5) for j in range(i+1, 5)
                   if rng.random() < .4], map(str, range(5)))
        for mask in range(32):
            cuts = {str(i) for i in range(5) if mask & (1 << i)}
            for v in g:
                expected = {v}
                for u in g:
                    if u != v and any(not (set(p[:-1]) & cuts) for p in nx.all_simple_paths(g, u, v)):
                        expected.add(u)
                assert context(g, v, cuts) == expected


def test_weights_and_chain_exposure():
    g = graph([('a', 'b'), ('b', 'c')])
    w = weights(g, 2, {0: 1, 1: 0, 2: 1})
    assert w == {'a': 3, 'b': 4, 'c': 1}
    assert exposure(g, set(), w) == 18
    assert exposure(g, {'b'}, w) == 11


def test_greedy_recomputes_marginal_gains():
    g = graph([(str(i), str(i+1)) for i in range(7)])
    w = weights(g, 1, {})
    chosen = set()
    for _ in range(3):
        old = exposure(g, chosen, w)
        remaining = sorted(set(g) - chosen)
        best = max(old - exposure(g, chosen | {u}, w) for u in remaining)
        chosen.add(next(u for u in remaining if old - exposure(g, chosen | {u}, w) == best))
    assert select(g, list(g), 3/8, 1, {}) == chosen


@pytest.mark.parametrize('ratio', [.2, .4, .6, 1])
def test_budget_and_mandatory_final(ratio):
    g = graph([('a','b'), ('b','c'), ('c','d'), ('d','e')])
    for strategy in ['bra', 'random']:
        result = select(g, list(g), ratio, 1, {}, strategy, mandatory='e')
        assert len(result) == math.ceil(ratio * len(g))
        assert 'e' in result


def test_invalid_graph():
    with pytest.raises(ValueError):
        select(graph([('a','b'),('b','a')]), ['a'], .4, 1, {})
