"""
Tests for T2: Honest, Data-Driven Evolution Service.
"""

from unittest.mock import MagicMock
from app import models
from app.services.constants import (
    BASIS_EMBEDDING_SIMILARITY,
    KIND_THEMATIC_LINEAGE,
    RELATION_CITES,
    RELATION_SIMILAR,
)
from app.services.evolution import EvolutionService, FindingComparisonSchema, FindingRelationEnum


def _make_mock_db(papers, relations, facts=None, chunks=None, clusters=None, cluster_members=None):
    db = MagicMock()
    facts = facts or []
    chunks = chunks or []
    clusters = clusters or []
    cluster_members = cluster_members or []

    def query_side_effect(model_or_tuple, *args):
        q = MagicMock()
        if model_or_tuple is models.EvolutionTransition:
            return q
        if model_or_tuple is models.ProjectPaper:
            q.filter.return_value.all.return_value = [MagicMock(paper_id=p.id) for p in papers]
        elif model_or_tuple is models.Paper:
            q.filter.return_value.order_by.return_value.all.return_value = sorted(
                papers, key=lambda p: (p.year or 9999, p.id)
            )
        elif model_or_tuple is models.PaperRelation:
            q.filter.return_value.all.return_value = relations
        elif model_or_tuple is models.PaperFact:
            q.filter.return_value.all.return_value = facts
        elif model_or_tuple is models.PaperChunk:
            q.filter.return_value.order_by.return_value.all.return_value = chunks
        elif model_or_tuple is models.ResearchProject:
            q.filter.return_value.first.return_value = MagicMock(id=1, topic="Quantum Sensing")
        elif model_or_tuple is models.ResearchCluster:
            q.filter.return_value.all.return_value = clusters
        elif model_or_tuple is models.ClusterMember:
            q.join.return_value.filter.return_value.all.return_value = cluster_members
        return q

    db.query.side_effect = query_side_effect
    return db


def test_similarity_fallback_fires_when_zero_citation_edges():
    """Fallback path must use RELATION_SIMILAR and .score when citation edges are absent."""
    p1 = MagicMock(id=1, title="Paper Early", year=2018, authors=[], abstract="A1", venue=None, citation_count=5, doi=None, original_url=None, source_name="openalex")
    p2 = MagicMock(id=2, title="Paper Late", year=2024, authors=[], abstract="A2", venue=None, citation_count=10, doi=None, original_url=None, source_name="arxiv")
    rel = MagicMock(source_id=1, target_id=2, relation_type=RELATION_SIMILAR, score=0.78)

    db = _make_mock_db([p1, p2], [rel])
    svc = EvolutionService()
    svc.llm.is_available = MagicMock(return_value=False)

    res = svc.generate_evolution(db, project_id=1)

    # Similarity fallback fired
    assert len(res["citation_timeline"]) == 1
    assert res["citation_timeline"][0]["kind"] == KIND_THEMATIC_LINEAGE
    assert res["citation_timeline"][0]["basis"] == BASIS_EMBEDDING_SIMILARITY
    assert res["citation_timeline"][0]["from_paper"]["id"] == 1
    assert res["citation_timeline"][0]["to_paper"]["id"] == 2

    # Empty windows omitted: only 2018 & 2024 have papers, so at most 2 phases (never 4 with empty ones)
    assert len(res["phases"]) == 2
    assert all(ph["paper_count"] > 0 for ph in res["phases"])

    # Zero template filler strings
    serialized = str(res)
    for forbidden in ("Addresses earlier limitations", "Authors indexed", "Foundational and preliminary"):
        assert forbidden not in serialized

    # Missing fields are null/None, not guessed
    assert res["paper_stream"][0]["authors_str"] is None
    assert res["paper_stream"][0]["venue"] is None


def test_finding_dynamics_contradicts_with_does_not_confirm_and_quote_validation():
    """'does not confirm' must NEVER be labelled confirms, and unverified quotes force insufficient_evidence."""
    p1 = MagicMock(
        id=1, title="Early Study", year=2019, authors=[],
        abstract="Method X achieves 90% accuracy on static benchmark A.",
        venue=None, citation_count=5, doi=None, original_url=None, source_name="openalex",
    )
    p2 = MagicMock(
        id=2, title="Later Replication", year=2023, authors=[],
        abstract="In contrast, Method X drops to 52% on noisy real-world benchmark B.",
        venue=None, citation_count=8, doi=None, original_url=None, source_name="arxiv",
    )
    rel = MagicMock(source_id=1, target_id=2, relation_type=RELATION_SIMILAR, score=0.81)

    db = _make_mock_db([p1, p2], [rel])
    svc = EvolutionService()
    svc.llm.is_available = MagicMock(return_value=True)

    # Case A: Both quotes verified, explanation contains "does not confirm", enum is contradicts
    svc.llm.generate_structured = MagicMock(return_value=FindingComparisonSchema(
        relation=FindingRelationEnum.contradicts,
        explanation="Later Replication does not confirm Early Study under noisy deployment conditions.",
        quote_from_earlier="Method X achieves 90% accuracy on static benchmark A",
        quote_from_later="Method X drops to 52% on noisy real-world benchmark B",
    ))
    res_a = svc.generate_evolution(db, project_id=1)
    assert len(res_a["finding_dynamics"]) == 1
    assert res_a["finding_dynamics"][0]["kind"] == "contradicts"
    assert res_a["finding_dynamics"][0]["kind"] != "confirms"
    assert res_a["finding_dynamics"][0]["verified"] is True

    # Case B: Fabricated quote fails verification -> forced to insufficient_evidence
    db2 = _make_mock_db([p1, p2], [rel])
    svc.llm.generate_structured = MagicMock(return_value=FindingComparisonSchema(
        relation=FindingRelationEnum.confirms,
        explanation="Confirms earlier results.",
        quote_from_earlier="Hallucinated quote not present in early abstract",
        quote_from_later="Method X drops to 52% on noisy real-world benchmark B",
    ))
    res_b = svc.generate_evolution(db2, project_id=1)
    assert res_b["finding_dynamics"][0]["kind"] == "insufficient_evidence"
    assert res_b["finding_dynamics"][0]["verified"] is False


def test_citation_backbone_main_path_ignores_similarity_edges(monkeypatch):
    """SPC main-path backbone must rank true citation paths and ignore similarity edges."""
    monkeypatch.setenv("MIN_BACKBONE_CITATIONS", "3")
    monkeypatch.setenv("CITATION_INTENT_PRUNING", "false")

    papers = [
        MagicMock(id=1, title="Root", year=2018, authors=[], abstract="A1", venue=None, citation_count=50, doi=None, original_url=None, source_name="openalex"),
        MagicMock(id=2, title="Bridge", year=2020, authors=[], abstract="A2", venue=None, citation_count=30, doi=None, original_url=None, source_name="openalex"),
        MagicMock(id=3, title="Alt", year=2021, authors=[], abstract="A3", venue=None, citation_count=10, doi=None, original_url=None, source_name="openalex"),
        MagicMock(id=4, title="Sink A", year=2023, authors=[], abstract="A4", venue=None, citation_count=5, doi=None, original_url=None, source_name="openalex"),
        MagicMock(id=5, title="Sink B", year=2024, authors=[], abstract="A5", venue=None, citation_count=4, doi=None, original_url=None, source_name="openalex"),
    ]
    # Citation relations: source_id cites target_id (so chronological flow is target -> source)
    relations = [
        MagicMock(source_id=2, target_id=1, relation_type=RELATION_CITES, score=1.0),  # 1 -> 2 (SPC=2)
        MagicMock(source_id=3, target_id=1, relation_type=RELATION_CITES, score=1.0),  # 1 -> 3 (SPC=1)
        MagicMock(source_id=4, target_id=2, relation_type=RELATION_CITES, score=1.0),  # 2 -> 4 (SPC=1)
        MagicMock(source_id=5, target_id=2, relation_type=RELATION_CITES, score=1.0),  # 2 -> 5 (SPC=1)
        MagicMock(source_id=4, target_id=3, relation_type=RELATION_CITES, score=1.0),  # 3 -> 4 (SPC=1)
        # Strong similarity edge directly 1 <-> 5 should NEVER enter citation_backbone
        MagicMock(source_id=1, target_id=5, relation_type=RELATION_SIMILAR, score=0.99),
    ]

    db = _make_mock_db(papers, relations)
    svc = EvolutionService()
    svc.llm.is_available = MagicMock(return_value=False)

    res = svc.generate_evolution(db, project_id=1)
    bb = res["citation_backbone"]
    assert bb["is_sparse"] is False
    assert bb["edge_count"] == 5
    assert bb["total_paths"] == 3
    assert bb["total_spc"] == 3
    path_ids = [n["id"] for n in bb["global_path"]]
    assert path_ids[:2] == [1, 2]
    assert path_ids[-1] in (4, 5)
    assert bb["key_route_edges"][0]["spc"] == 2


def test_citation_backbone_sparse_warning_and_intent_pruning_skip(monkeypatch):
    """Sparse citation graphs show explicit warning without similarity fallback; intent pruning skips without chunks."""
    monkeypatch.setenv("MIN_BACKBONE_CITATIONS", "3")
    monkeypatch.setenv("CITATION_INTENT_PRUNING", "true")

    papers = [
        MagicMock(id=1, title="Seed", year=2019, authors=[], abstract="Abstract one", venue=None, citation_count=5, doi=None, original_url=None, source_name="openalex"),
        MagicMock(id=2, title="Followup", year=2022, authors=[], abstract="Abstract two", venue=None, citation_count=3, doi=None, original_url=None, source_name="openalex"),
        MagicMock(id=3, title="Unlinked", year=2024, authors=[], abstract="Abstract three", venue=None, citation_count=1, doi=None, original_url=None, source_name="arxiv"),
    ]
    relations = [
        MagicMock(source_id=2, target_id=1, relation_type=RELATION_CITES, score=1.0),
        MagicMock(source_id=2, target_id=3, relation_type=RELATION_SIMILAR, score=0.95),
    ]
    db = _make_mock_db(papers, relations, chunks=[])
    svc = EvolutionService()
    svc.llm.is_available = MagicMock(return_value=False)

    res = svc.generate_evolution(db, project_id=1)
    bb = res["citation_backbone"]
    assert bb["is_sparse"] is True
    assert bb["edge_count"] == 1
    assert bb["intent_pruning_status"] == "skipped_no_full_text_chunks"
    assert [n["id"] for n in bb["global_path"]] == [1, 2]
    assert "Sparse citation graph" in bb["message"]


def test_phase_transitions_populate_factual_key_changes_and_matching_counts():
    """Phase transitions must expose matching phase_from/to counts and factual key_changes from facts/relations."""
    papers = [
        MagicMock(id=1, title="Early Study", year=2018, authors=[], abstract="A1", venue=None, citation_count=10, doi=None, original_url=None, source_name="openalex"),
        MagicMock(id=2, title="Mid Study", year=2022, authors=[], abstract="A2", venue=None, citation_count=5, doi=None, original_url=None, source_name="openalex"),
        MagicMock(id=3, title="Recent Study", year=2025, authors=[], abstract="A3", venue=None, citation_count=2, doi=None, original_url=None, source_name="arxiv"),
    ]
    facts = [
        MagicMock(paper_id=1, method={"value": "Thresholding"}, dataset={"value": "Bench-A"}, limitations={"value": "Drift"}, future_work=None, claimed_contributions={"value": "First baseline"}),
        MagicMock(paper_id=2, method={"value": "Random Forest"}, dataset={"value": "Bench-B"}, limitations={"value": "Small cohort"}, future_work=None, claimed_contributions={"value": "Gait classification"}),
        MagicMock(paper_id=3, method={"value": "CNN"}, dataset={"value": "Bench-B"}, limitations=None, future_work={"value": "Longitudinal trial"}, claimed_contributions={"value": "Deep sensor fusion"}),
    ]
    relations = [MagicMock(source_id=2, target_id=1, relation_type=RELATION_CITES, score=1.0)]

    db = _make_mock_db(papers, relations, facts=facts)
    svc = EvolutionService()
    svc.llm.is_available = MagicMock(return_value=False)

    res = svc.generate_evolution(db, project_id=1)
    assert len(res["transitions"]) >= 1
    tr = res["transitions"][0]
    assert tr["phase_from_count"] == res["phases"][0]["paper_count"]
    assert tr["phase_to_count"] == res["phases"][1]["paper_count"]
    assert tr["paper_count"] == tr["phase_from_count"] + tr["phase_to_count"]
    assert len(tr["key_changes"]) >= 1
    assert any("New methods" in kc for kc in tr["key_changes"])
    assert res["paper_stream"][-1]["gaps_solved"] == ["Longitudinal trial"]
