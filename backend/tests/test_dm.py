"""
Tests for Discrete Mathematics package (DM-1):
- Hand-checked SPC values & Global / Key-Route Main Path
- Transitive Reduction (Hasse) & Closure vs NetworkX oracle on random DAGs
- Inclusion-Exclusion vs Python set union (2, 3, 4 sets)
- Topological prerequisite Reading Path with max_hops and PageRank cap
"""

import random
import networkx as nx

from app.dm.inclusion_exclusion import inclusion_exclusion_breakdown, union_size
from app.dm.main_path import global_main_path, key_route_main_path
from app.dm.partial_order import transitive_closure, transitive_reduction
from app.dm.path_counting import compute_spc
from app.dm.reading_path import compute_reading_path
from app.dsa.graph import Graph


def test_hand_checked_spc_and_main_path():
    """
    Hand-checked diamond+tail DAG:
      S -> A, S -> B
      A -> C, B -> C
      C -> D, C -> E
      D -> T, E -> T
    Sources: {S}. Sinks: {T}.
    N(S)=1, N(A)=1, N(B)=1, N(C)=2, N(D)=2, N(E)=2, N(T)=4.
    M(T)=1, M(D)=1, M(E)=1, M(C)=2, M(A)=2, M(B)=2, M(S)=4.
    SPC(S,A) = 1*2 = 2; SPC(A,C) = 1*2 = 2; SPC(C,D) = 2*1 = 2; SPC(D,T) = 2*1 = 2.
    Total source-to-sink paths = 4. Global main path total SPC = 8.
    """
    dag = Graph(directed=True)
    for u, v in [("S", "A"), ("S", "B"), ("A", "C"), ("B", "C"), ("C", "D"), ("C", "E"), ("D", "T"), ("E", "T")]:
        dag.add_edge(u, v)

    spc = compute_spc(dag)
    assert spc["N"] == {"S": 1, "A": 1, "B": 1, "C": 2, "D": 2, "E": 2, "T": 4}
    assert spc["M"] == {"S": 4, "A": 2, "B": 2, "C": 2, "D": 1, "E": 1, "T": 1}
    assert spc["total_paths"] == 4
    assert spc["edge_spc"][("S", "A")] == 2
    assert spc["edge_spc"][("C", "D")] == 2

    # Asymmetric branch to uniquely force S -> A -> C -> T
    dag2 = Graph(directed=True)
    for u, v in [("S", "A"), ("S", "B"), ("A", "C"), ("A", "D"), ("B", "D"), ("C", "T"), ("D", "T")]:
        dag2.add_edge(u, v)
    # Paths S->A->C->T, S->A->D->T, S->B->D->T (3 total):
    # N(S)=1, N(A)=1, N(B)=1, N(C)=1, N(D)=2, N(T)=3
    # M(T)=1, M(C)=1, M(D)=1, M(A)=2, M(B)=1, M(S)=3
    # SPC(S,A)=1*2=2, SPC(A,D)=1*1=1, SPC(D,T)=2*1=2 -> sum 5 (vs S-A-C-T: 2+1+1=4, S-B-D-T: 1+1+2=4)
    mp = global_main_path(dag2)
    assert mp["path"] == ["S", "A", "D", "T"]
    assert mp["total_spc"] == 5

    kr = key_route_main_path(dag2, top_k_edges=2)
    assert len(kr["key_route_edges"]) >= 2
    assert kr["key_route_edges"][0]["spc"] == 2


def test_main_path_empty_edges():
    g = Graph(directed=True)
    g.add_node(1)
    g.add_node(2)
    mp = global_main_path(g)
    assert mp["path"] == []
    assert mp["total_spc"] == 0
    assert "No citation edges" in mp["explanation"]

    kr = key_route_main_path(g)
    assert kr["key_route_edges"] == []
    assert "No citation edges" in kr["explanation"]


def test_transitive_reduction_and_closure_vs_networkx():
    rng = random.Random(707)
    for _ in range(100):
        n = rng.randint(3, 14)
        dag = Graph(directed=True)
        nx_dag = nx.DiGraph()
        for u in range(n):
            dag.add_node(u)
            nx_dag.add_node(u)
        for u in range(n):
            for v in range(u + 1, n):
                if rng.random() < 0.4:
                    dag.add_edge(u, v)
                    nx_dag.add_edge(u, v)

        clos = transitive_closure(dag)
        nx_clos = nx.transitive_closure(nx_dag)
        assert {(u, v) for u, v, _ in clos.edges()} == set(nx_clos.edges())

        hasse = transitive_reduction(dag)
        nx_hasse = nx.transitive_reduction(nx_dag)
        assert {(u, v) for u, v, _ in hasse.edges()} == set(nx_hasse.edges())


def test_inclusion_exclusion_vs_set_union():
    rng = random.Random(808)
    for k in (2, 3, 4):
        for _ in range(50):
            sets = [set(rng.sample(range(40), rng.randint(0, 15))) for _ in range(k)]
            expected = len(set().union(*sets)) if sets else 0
            assert union_size(sets) == expected

    bd = inclusion_exclusion_breakdown({
        "openalex": {1, 2, 3, 4},
        "semantic_scholar": {3, 4, 5},
        "arxiv": {4, 6},
    })
    assert bd["singles"] == {"openalex": 4, "semantic_scholar": 3, "arxiv": 2}
    assert bd["pairwise"]["openalex & semantic_scholar"] == 2
    assert bd["triple"]["openalex & semantic_scholar & arxiv"] == 1
    assert bd["union_size"] == 6


def test_reading_path_topological_order_and_cap():
    # Paper 10 cites 5 and 6; 5 cites 1 and 2; 6 cites 2 and 3; 2 cites 0 (3 hops from 10)
    dag = Graph(directed=True)
    for u, v in [(10, 5), (10, 6), (5, 1), (5, 2), (6, 2), (6, 3), (2, 0)]:
        dag.add_edge(u, v)

    pagerank = {0: 0.40, 1: 0.15, 2: 0.25, 3: 0.05, 5: 0.08, 6: 0.07, 10: 0.01}

    # max_hops=2 excludes paper 0 (3 hops away)
    rp_2hops = compute_reading_path(dag, target_paper_id=10, pagerank=pagerank, max_hops=2, max_papers=10)
    ids_2hops = [s["paper_id"] for s in rp_2hops]
    assert 0 not in ids_2hops
    assert set(ids_2hops) == {1, 2, 3, 5, 6}
    # Foundational cited papers must appear before papers that cite them:
    assert ids_2hops.index(1) < ids_2hops.index(5)
    assert ids_2hops.index(2) < ids_2hops.index(5)
    assert ids_2hops.index(2) < ids_2hops.index(6)

    # Capped at n=3 selects top 3 by PageRank: 0 (0.40), 2 (0.25), 1 (0.15)
    rp_cap = compute_reading_path(dag, target_paper_id=10, pagerank=pagerank, max_hops=3, max_papers=3)
    assert len(rp_cap) == 3
    assert {s["paper_id"] for s in rp_cap} == {0, 2, 1}
    # 0 is cited by 2 -> 0 appears before 2
    ids_cap = [s["paper_id"] for s in rp_cap]
    assert ids_cap.index(0) < ids_cap.index(2)
