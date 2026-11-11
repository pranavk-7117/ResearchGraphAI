"""
Tests for T2: Honest, Data-Driven Evolution Service.
"""

from unittest.mock import MagicMock
from app import models
from app.services.constants import BASIS_EMBEDDING_SIMILARITY, KIND_THEMATIC_LINEAGE, RELATION_SIMILAR
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
    assert res["paper_stream"][0]["pub_type"] is None
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
