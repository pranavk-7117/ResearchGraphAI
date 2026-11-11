"""
Tests for T9: Community Clustering (Leiden / NetworkX fallback), Connected Subgraph
Guarantee, Seed Determinism, Cosine Silhouette Selection, and NMI Agreement.
"""

import networkx as nx
import numpy as np

from app.services.clustering import (
    compute_partition_nmi,
    run_agglomerative_silhouette,
    run_community_partition,
)


def test_community_partition_connected_and_deterministic():
    """Every community must induce a connected subgraph and be deterministic with fixed seed."""
    g = nx.Graph()
    # Two cliques (0..4 and 5..9) weakly bridged by edge (4, 5) + isolated component (10, 11)
    for i in range(5):
        for j in range(i + 1, 5):
            g.add_edge(i, j, weight=0.9)
    for i in range(5, 10):
        for j in range(i + 1, 10):
            g.add_edge(i, j, weight=0.9)
    g.add_edge(4, 5, weight=0.05)
    g.add_edge(10, 11, weight=0.8)

    comms_1, meta_1 = run_community_partition(g, resolution=1.0, seed=42)
    comms_2, meta_2 = run_community_partition(g, resolution=1.0, seed=42)

    # Determinism
    assert comms_1 == comms_2
    assert meta_1["modularity"] == meta_2["modularity"]
    assert meta_1["modularity"] > 0.3

    # Connected-subgraph guarantee for EVERY community
    for comm in comms_1:
        sub = g.subgraph(comm)
        assert nx.is_connected(sub)


def test_agglomerative_silhouette_selects_optimal_k_and_nmi():
    """Silhouette selection picks k=3 on 3 well-separated clusters rather than n//3."""
    rng = np.random.default_rng(7)
    centers = [
        np.array([1.0, 0.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0, 0.0]),
        np.array([0.0, 0.0, 1.0, 0.0]),
    ]
    X_rows = []
    pids = []
    pid = 1
    for c in centers:
        for _ in range(5):
            v = c + rng.normal(0, 0.03, size=4)
            v = v / np.linalg.norm(v)
            X_rows.append(v)
            pids.append(pid)
            pid += 1

    X = np.array(X_rows, dtype=np.float32)
    groups, meta = run_agglomerative_silhouette(X, pids, n_clusters=None)
    assert meta["n_clusters"] == 3
    assert meta["silhouette"] > 0.8

    part = [sorted(g) for g in groups.values()]
    assert compute_partition_nmi(part, part) == 1.0

    # Shifted / merged partition has NMI < 1.0
    merged = [part[0] + part[1], part[2]]
    nmi_diff = compute_partition_nmi(part, merged)
    assert nmi_diff is not None and 0.0 < nmi_diff < 1.0
