"""
Tests for T14: Defensible Multi-Metric Novelty Assessment in CompareService.
"""

from types import SimpleNamespace
import random

from app.services.compare import compute_corpus_novelty_metrics, compute_reference_atypicality


def test_near_copy_vs_unrelated_novelty_metrics():
    """Near-copy paper must trigger high top-k/max similarity and high density percentile vs unrelated."""
    papers = [SimpleNamespace(id=i, title=f"Corpus Paper {i}", year=2020 + (i % 4)) for i in range(1, 21)]
    # Papers 1..19 cluster near axis 0; Paper 20 sits near axis 1; near-copy is aligned with Paper 1
    vectors = {
        i: ([1.0, 0.0, 0.0] if i <= 5 else [0.7, 0.7, 0.0] if i <= 15 else [0.0, 1.0, 0.0])
        for i in range(1, 21)
    }

    near_copy_vec = [0.999, 0.02, 0.0]
    unrelated_vec = [0.0, 0.0, 1.0]

    res_copy = compute_corpus_novelty_metrics(near_copy_vec, vectors, papers, k=5)
    res_unrel = compute_corpus_novelty_metrics(unrelated_vec, vectors, papers, k=5)

    assert res_copy["relative_to_corpus_only"] is True
    assert res_copy["max_similarity"] > 0.99
    assert res_copy["top_k_mean_similarity"] > 0.95
    assert res_copy["semantic_distance"] < 0.05
    assert res_copy["local_density_percentile"] > res_unrel["local_density_percentile"]

    assert res_unrel["relative_to_corpus_only"] is True
    assert res_unrel["top_k_mean_similarity"] < 0.1
    assert res_unrel["semantic_distance"] > 0.9
    assert len(res_unrel["top_k_neighbors"]) == 5
    assert "top_k_nearest_neighbors" in res_unrel["method_names"]
    assert "formula" in res_unrel


def test_reference_combination_atypicality_z_near_zero_on_random_sample():
    """Uniform random reference combination yields z-score near zero under null model."""
    pool = [f"venue_{i}" for i in range(20)]
    rng = random.Random(7)
    corpus_refs = [rng.sample(pool, 6) for _ in range(30)]
    random_uploaded = rng.sample(pool, 6)

    atyp = compute_reference_atypicality(random_uploaded, corpus_refs, n_shuffles=80, seed=42)
    assert atyp["available"] is True
    assert atyp["z_score"] is not None
    assert abs(atyp["z_score"]) < 3.0

    # Sparse reference guard
    sparse = compute_reference_atypicality(["only_one"], corpus_refs)
    assert sparse["available"] is False
    assert sparse["z_score"] is None
