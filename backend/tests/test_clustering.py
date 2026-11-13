"""
Tests for T9: Community Clustering (Leiden / NetworkX fallback), Connected Subgraph
Guarantee, Seed Determinism, Cosine Silhouette Selection, and NMI Agreement.
"""

from unittest.mock import MagicMock
import networkx as nx
import numpy as np

from app.services.clustering import (
    MIN_CLUSTER_SIZE,
    compute_ctfidf_labels,
    compute_partition_nmi,
    merge_small_clusters,
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


def test_merge_small_clusters_enforces_min_size():
    """Clusters with < 3 papers must be merged into nearest large cluster via cosine similarity."""
    # 2 large clusters (size 4 each) and 2 small clusters (size 1 and 2)
    # Centroid A at [1, 0], Centroid B at [0, 1]
    large_a = [1, 2, 3, 4]
    large_b = [5, 6, 7, 8]
    small_c = [9]       # closest to A
    small_d = [10, 11]  # closest to B

    pids = list(range(1, 12))
    embs = {}
    for pid in [1, 2, 3, 4, 9]:
        embs[pid] = np.array([0.99, 0.05], dtype=np.float32)
    for pid in [5, 6, 7, 8, 10, 11]:
        embs[pid] = np.array([0.05, 0.99], dtype=np.float32)

    X = np.array([embs[pid] for pid in pids], dtype=np.float32)

    merged = merge_small_clusters(
        groups=[large_a, large_b, small_c, small_d],
        X=X,
        valid_paper_ids=pids,
        min_size=MIN_CLUSTER_SIZE,
    )

    # Every resulting cluster must have >= MIN_CLUSTER_SIZE (3) papers
    for grp in merged:
        assert len(grp) >= MIN_CLUSTER_SIZE

    # Paper 9 must have merged into A
    merged_a = next(g for g in merged if 1 in g)
    assert 9 in merged_a

    # Papers 10 and 11 must have merged into B
    merged_b = next(g for g in merged if 5 in g)
    assert 10 in merged_b and 11 in merged_b


def test_compute_ctfidf_labels_extracts_distinguishing_terms():
    """c-TF-IDF assigns distinguishing multi-word/unigram labels instead of paper titles."""
    cluster_a = [
        MagicMock(id=1, title="Diabetic foot ulcer pressure sensor analysis", abstract="Insole sensors for gait pressure."),
        MagicMock(id=2, title="Smart insole monitoring diabetic ulcers", abstract="Foot pressure measurement system."),
        MagicMock(id=3, title="Ulcer prevention through foot pressure mapping", abstract="Diabetic gait monitoring insoles."),
    ]
    cluster_b = [
        MagicMock(id=4, title="Deep learning transformer for genome sequence", abstract="Attention models for DNA gene splicing."),
        MagicMock(id=5, title="Genomic language model pretraining", abstract="Transformer attention over biological sequences."),
        MagicMock(id=6, title="Chromatin accessibility prediction via deep transformers", abstract="Gene sequence transformer embeddings."),
    ]

    labels = compute_ctfidf_labels([cluster_a, cluster_b])
    assert len(labels) == 2

    label_a, ev_a = labels[0]
    label_b, ev_b = labels[1]

    # Labels must be formatted in Title Case separated by ' · '
    assert " · " in label_a
    assert " · " in label_b

    # Cluster A should contain foot/pressure/ulcer/insole terms
    assert any(term in label_a.lower() for term in ("foot", "pressure", "ulcer", "insole", "diabetic", "gait"))
    assert ev_a["source"] == "c_tf_idf"
    assert len(ev_a["top_terms"]) > 0

    # Cluster B should contain transformer/sequence/genome/genomic terms
    assert any(term in label_b.lower() for term in ("transformer", "genome", "genomic", "sequence", "gene"))
    assert ev_b["source"] == "c_tf_idf"

