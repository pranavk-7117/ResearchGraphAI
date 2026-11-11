"""
Property-based oracle tests (>= 200 randomized cases per structure) for DS-1 (`app.dsa`).
NetworkX / heapq / dict are used strictly here in tests as correctness oracles.
"""

import heapq
import random
import networkx as nx
import pytest

from app.dsa.graph import Graph, bfs, connected_components, dfs, has_cycle
from app.dsa.hashtable import HashTable
from app.dsa.heap import MinHeap, top_k
from app.dsa.mst import kruskal_mst
from app.dsa.shortest_path import dijkstra
from app.dsa.topo import CycleError, is_unique_topological_order, kahn_topological_sort
from app.dsa.trie import Trie
from app.dsa.union_find import UnionFind


def test_graph_traversals_and_components_200_random_cases():
    rng = random.Random(42)
    for _ in range(200):
        n = rng.randint(2, 16)
        directed = rng.choice([True, False])
        g = Graph(directed=directed)
        nx_g = nx.DiGraph() if directed else nx.Graph()
        for u in range(n):
            g.add_node(u)
            nx_g.add_node(u)
        for _ in range(rng.randint(0, n * 2)):
            u, v = rng.randrange(n), rng.randrange(n)
            if u != v:
                g.add_edge(u, v)
                nx_g.add_edge(u, v)

        # Connected components oracle
        ours = {frozenset(c) for c in connected_components(g)}
        oracle_cc = (
            {frozenset(c) for c in nx.weakly_connected_components(nx_g)}
            if directed
            else {frozenset(c) for c in nx.connected_components(nx_g)}
        )
        assert ours == oracle_cc

        # BFS reachable set + level order vs nx.bfs_tree
        start = rng.randrange(n)
        bfs_order = bfs(g, start)
        assert set(bfs_order) == set(nx.bfs_tree(nx_g, start).nodes())

        # Iterative and recursive DFS visit identical reachable set as nx.dfs_tree
        dfs_iter = dfs(g, start, recursive=False)
        dfs_rec = dfs(g, start, recursive=True)
        nx_dfs_nodes = set(nx.dfs_tree(nx_g, start).nodes())
        assert set(dfs_iter) == nx_dfs_nodes
        assert set(dfs_rec) == nx_dfs_nodes

        # Cycle detection oracle
        if directed:
            oracle_cycle = not nx.is_directed_acyclic_graph(nx_g)
        else:
            try:
                nx.find_cycle(nx_g)
                oracle_cycle = True
            except nx.NetworkXNoCycle:
                oracle_cycle = False
        assert has_cycle(g) == oracle_cycle


def test_union_find_200_random_cases():
    rng = random.Random(101)
    for _ in range(200):
        n = rng.randint(3, 25)
        uf = UnionFind(range(n))
        nx_g = nx.Graph()
        nx_g.add_nodes_from(range(n))
        for _ in range(rng.randint(1, n * 2)):
            a, b = rng.randrange(n), rng.randrange(n)
            uf.union(a, b)
            nx_g.add_edge(a, b)

        for _ in range(10):
            x, y = rng.randrange(n), rng.randrange(n)
            assert uf.connected(x, y) == nx.has_path(nx_g, x, y)


def test_kahn_topological_sort_and_uniqueness_200_random_cases():
    rng = random.Random(202)
    for _ in range(200):
        n = rng.randint(2, 14)
        g = Graph(directed=True)
        nx_g = nx.DiGraph()
        for u in range(n):
            g.add_node(u)
            nx_g.add_node(u)
        make_dag = rng.random() < 0.7
        if make_dag:
            for u in range(n):
                for v in range(u + 1, n):
                    if rng.random() < 0.35:
                        g.add_edge(u, v)
                        nx_g.add_edge(u, v)
            order = kahn_topological_sort(g)
            pos = {node: idx for idx, node in enumerate(order)}
            assert len(order) == n
            for u, v, _ in g.edges():
                assert pos[u] < pos[v]
            # Uniqueness oracle: unique iff there is only 1 topological sort in NetworkX (when small)
            if n <= 8:
                all_sorts = list(nx.all_topological_sorts(nx_g))
                assert is_unique_topological_order(g) == (len(all_sorts) == 1)
        else:
            # Force at least one cycle
            a, b, c = 0, 1, rng.randrange(2, n) if n > 2 else 1
            g.add_edge(a, b)
            g.add_edge(b, c)
            g.add_edge(c, a)
            with pytest.raises(CycleError) as exc_info:
                kahn_topological_sort(g)
            assert len(exc_info.value.cycle) >= 2
            assert is_unique_topological_order(g) is False


def test_min_heap_and_top_k_200_random_cases():
    rng = random.Random(303)
    for _ in range(200):
        arr = [rng.randint(-500, 500) for _ in range(rng.randint(1, 60))]
        mh = MinHeap()
        for x in arr:
            mh.push(x)
        popped = []
        while len(mh) > 0:
            popped.append(mh.pop())
        assert popped == sorted(arr)

        k = rng.randint(1, min(10, len(arr)))
        assert top_k(arr, k, reverse=True) == heapq.nlargest(k, arr)
        assert top_k(arr, k, reverse=False) == heapq.nsmallest(k, arr)


def test_dijkstra_200_random_cases():
    rng = random.Random(404)
    for _ in range(200):
        n = rng.randint(3, 15)
        g = Graph(directed=True)
        nx_g = nx.DiGraph()
        for u in range(n):
            g.add_node(u)
            nx_g.add_node(u)
        for _ in range(rng.randint(2, n * 3)):
            u, v = rng.randrange(n), rng.randrange(n)
            if u != v:
                w = round(rng.uniform(0.1, 10.0), 3)
                g.add_edge(u, v, weight=w)
                nx_g.add_edge(u, v, weight=w)

        src, tgt = rng.randrange(n), rng.randrange(n)
        res = dijkstra(g, src, tgt)
        try:
            nx_len = nx.shortest_path_length(nx_g, src, tgt, weight="weight")
            assert res is not None
            dist, path = res
            assert pytest.approx(dist, abs=1e-6) == nx_len
            assert path[0] == src and path[-1] == tgt
        except nx.NetworkXNoPath:
            assert res is None


def test_kruskal_mst_200_random_cases():
    rng = random.Random(505)
    for _ in range(200):
        n = rng.randint(3, 15)
        g = Graph(directed=False)
        nx_g = nx.Graph()
        for u in range(n):
            g.add_node(u)
            nx_g.add_node(u)
        for _ in range(rng.randint(2, n * 3)):
            u, v = rng.randrange(n), rng.randrange(n)
            if u != v and not g.has_edge(u, v):
                w = round(rng.uniform(0.1, 1.0), 4)
                g.add_edge(u, v, weight=w)
                nx_g.add_edge(u, v, weight=w)

        mst_min = kruskal_mst(g, maximum=False)
        nx_min = nx.minimum_spanning_tree(nx_g, weight="weight")
        assert pytest.approx(sum(w for _, _, w in mst_min), abs=1e-6) == sum(
            d["weight"] for _, _, d in nx_min.edges(data=True)
        )

        mst_max = kruskal_mst(g, maximum=True)
        nx_max = nx.maximum_spanning_tree(nx_g, weight="weight")
        assert pytest.approx(sum(w for _, _, w in mst_max), abs=1e-6) == sum(
            d["weight"] for _, _, d in nx_max.edges(data=True)
        )


def test_trie_and_hashtable_200_random_cases():
    rng = random.Random(606)
    # 200 random Trie prefix checks
    vocab = [f"paper_{i}_{chr(97 + (i % 26))}{chr(97 + ((i * 7) % 26))}" for i in range(60)]
    trie = Trie()
    for idx, word in enumerate(vocab):
        trie.insert(word, payload=idx)
    for _ in range(200):
        pref = rng.choice(vocab)[: rng.randint(1, 8)]
        expected = {w for w in vocab if w.lower().startswith(pref.lower())}
        got = {r["text"] for r in trie.search_prefix(pref, limit=100)}
        assert got == expected

    # 200 random HashTable ops vs Python dict oracle
    ht = HashTable(initial_capacity=8)
    oracle: dict[str, int] = {}
    for step in range(200):
        k = f"hash_{rng.randrange(50)}"
        op_choice = rng.random()
        if op_choice < 0.6:
            ht.put(k, step)
            oracle[k] = step
        elif op_choice < 0.85:
            assert ht.get(k) == oracle.get(k)
            assert (k in ht) == (k in oracle)
        else:
            assert ht.delete(k) == (oracle.pop(k, None) is not None)
        assert len(ht) == len(oracle)
