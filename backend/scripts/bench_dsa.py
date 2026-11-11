"""
Benchmark script for hand-built DS-1 structures vs standard Python / NetworkX baselines.
Usage:
    python backend/scripts/bench_dsa.py
"""

import heapq
import random
import sys
import time
from pathlib import Path
import networkx as nx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.dsa.graph import Graph
from app.dsa.hashtable import HashTable
from app.dsa.heap import top_k
from app.dsa.mst import kruskal_mst
from app.dsa.shortest_path import dijkstra


def run_benchmarks() -> None:
    rng = random.Random(123)

    # 1. HashTable vs Python dict (10,000 title-hash inserts + lookups)
    keys = [f"sha256_paper_hash_{i:06d}" for i in range(10000)]
    t0 = time.perf_counter()
    ht = HashTable()
    for k in keys:
        ht.put(k, True)
    hits_ht = sum(1 for k in keys if k in ht)
    t_ht = time.perf_counter() - t0

    t0 = time.perf_counter()
    py_d = {}
    for k in keys:
        py_d[k] = True
    hits_dict = sum(1 for k in keys if k in py_d)
    t_dict = time.perf_counter() - t0
    assert hits_ht == hits_dict == 10000
    print(f"[HashTable vs dict (N=10,000)] HashTable: {t_ht*1000:.2f} ms | dict: {t_dict*1000:.2f} ms")

    # 2. MinHeap top_k vs sorted[:k] (N=20,000, k=25)
    vals = [rng.random() for _ in range(20000)]
    t0 = time.perf_counter()
    res_tk = top_k(vals, 25, reverse=True)
    t_tk = time.perf_counter() - t0

    t0 = time.perf_counter()
    res_sort = sorted(vals, reverse=True)[:25]
    t_sort = time.perf_counter() - t0
    assert res_tk == res_sort
    print(f"[top_k vs sorted[:25] (N=20,000)] top_k: {t_tk*1000:.2f} ms | sorted: {t_sort*1000:.2f} ms")

    # 3. Dijkstra vs NetworkX shortest_path (V=300, E=1500)
    g = Graph(directed=True)
    nx_g = nx.DiGraph()
    for _ in range(1500):
        u, v = rng.randrange(300), rng.randrange(300)
        if u != v:
            w = rng.uniform(0.1, 1.0)
            g.add_edge(u, v, weight=w)
            nx_g.add_edge(u, v, weight=w)

    t0 = time.perf_counter()
    for s in range(0, 50):
        dijkstra(g, s, (s + 150) % 300)
    t_dijk = time.perf_counter() - t0

    t0 = time.perf_counter()
    for s in range(0, 50):
        try:
            nx.shortest_path(nx_g, s, (s + 150) % 300, weight="weight")
        except nx.NetworkXNoPath:
            pass
    t_nx_sp = time.perf_counter() - t0
    print(f"[Dijkstra vs nx.shortest_path (50 queries, V=300, E=1500)] Dijkstra: {t_dijk*1000:.2f} ms | nx: {t_nx_sp*1000:.2f} ms")

    # 4. Kruskal MST vs NetworkX maximum_spanning_tree (V=300, E=1500)
    ug = Graph(directed=False)
    nx_ug = nx.Graph()
    for _ in range(1500):
        u, v = rng.randrange(300), rng.randrange(300)
        if u != v and not ug.has_edge(u, v):
            w = rng.uniform(0.1, 1.0)
            ug.add_edge(u, v, weight=w)
            nx_ug.add_edge(u, v, weight=w)

    t0 = time.perf_counter()
    kruskal_mst(ug, maximum=True)
    t_krusk = time.perf_counter() - t0

    t0 = time.perf_counter()
    nx.maximum_spanning_tree(nx_ug, weight="weight")
    t_nx_mst = time.perf_counter() - t0
    print(f"[Kruskal MST vs nx.maximum_spanning_tree (V=300, E=1500)] Kruskal: {t_krusk*1000:.2f} ms | nx: {t_nx_mst*1000:.2f} ms")


if __name__ == "__main__":
    run_benchmarks()
