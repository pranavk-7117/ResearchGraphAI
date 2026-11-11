"""
Tests for T11: Corpus Completeness Meter (Inclusion-Exclusion & Chapman Capture-Recapture).
"""

import random
from unittest.mock import MagicMock

from app import models
from app.clients.base import RawCandidatePaper
from app.services.completeness import CompletenessService, chapman_estimator, lincoln_petersen
from app.services.discovery import DiscoveryService


def test_deduplication_merges_multi_source_provenance():
    """Deduplicating identical papers across OpenAlex, Semantic Scholar, and arXiv retains all source tags."""
    svc = DiscoveryService.__new__(DiscoveryService)
    c1 = RawCandidatePaper(source="openalex", external_id="W1", title="Graph Neural Networks Survey", doi="10.1000/gnn")
    c2 = RawCandidatePaper(source="semantic_scholar", external_id="S2_1", title="Graph Neural Networks Survey", doi="10.1000/GNN")
    c3 = RawCandidatePaper(source="arxiv", external_id="2401.0001", title="Graph Neural Networks Survey")

    unique = svc._deduplicate_candidates([c1, c2, c3])
    assert len(unique) == 1
    assert unique[0].sources == ["arxiv", "openalex", "semantic_scholar"]


def test_completeness_venn_and_refusal_below_min_overlap():
    """Known 3-source overlap matches Inclusion-Exclusion union and refuses estimate when m < 5."""
    rows = []
    # Paper 1..4 in OpenAlex + S2 (overlap=4 < 5), Paper 5 in arXiv only
    source_lists = [
        ["openalex", "semantic_scholar"],
        ["openalex", "semantic_scholar"],
        ["openalex", "semantic_scholar"],
        ["openalex", "semantic_scholar"],
        ["arxiv"],
    ]
    for idx, srcs in enumerate(source_lists, start=1):
        pp = MagicMock(paper_id=idx, sources=srcs)
        paper = MagicMock(id=idx, source_name=srcs[0])
        rows.append((pp, paper))

    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.all.return_value = rows

    res = CompletenessService().compute(db, project_id=1)
    assert res["total_observed"] == 5
    assert res["venn_breakdown"]["union_size"] == 5
    assert res["venn_breakdown"]["singles"] == {"openalex": 4, "semantic_scholar": 4, "arxiv": 1}
    assert res["venn_breakdown"]["pairwise"]["openalex & semantic_scholar"] == 4
    assert res["estimate_available"] is False
    assert res["chapman_estimate"] is None
    assert "below minimum threshold" in res["disclaimer"]


def test_chapman_ci_coverage_500_simulations():
    """500 independent capture-recapture trials: empirical 95% CI coverage >= 90%."""
    rng = random.Random(42)
    true_n = 1000
    p1 = 0.25
    p2 = 0.20
    covered = 0
    trials = 500

    for _ in range(trials):
        s1 = {i for i in range(true_n) if rng.random() < p1}
        s2 = {i for i in range(true_n) if rng.random() < p2}
        m = len(s1 & s2)
        est = chapman_estimator(len(s1), len(s2), m)
        assert est["available"] is True
        low, high = est["ci_95"]
        if low <= true_n <= high:
            covered += 1

    coverage = covered / trials
    assert coverage >= 0.90, f"Chapman 95% CI empirical coverage too low: {coverage:.3f}"


def test_lincoln_petersen_and_chapman_formula():
    """Verify exact closed-form Lincoln-Petersen and Chapman calculations."""
    lp = lincoln_petersen(100, 80, 20)
    assert lp == 400.0
    chap = chapman_estimator(100, 80, 20)
    expected = ((101 * 81) / 21.0) - 1.0
    assert abs(chap["estimate"] - round(expected, 1)) < 1e-6
