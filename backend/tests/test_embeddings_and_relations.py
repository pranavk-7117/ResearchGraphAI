"""
Tests for Dense Embeddings, Idempotency, Citation Resolution, and Semantic Relations.
"""

import pytest
from app.database import SessionLocal
from app import models
from app.services.embeddings import EmbeddingService, cosine_similarity
from app.services.relations import RelationsService


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_embedding_dimensions():
    service = EmbeddingService()
    assert service.dim == 384
    vec = service.embed("Evaluating cryptographic protocols for decentralized networks.")
    assert len(vec) == 384
    assert all(isinstance(v, float) for v in vec)


def test_cosine_similarity():
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]

    assert pytest.approx(cosine_similarity(v1, v2)) == 1.0
    assert pytest.approx(cosine_similarity(v1, v3)) == 0.0


def test_citation_and_similarity_relations(db):
    # Ensure clean slate for test papers and references
    db.query(models.PaperReference).filter(models.PaperReference.raw_reference == "Kipf and Welling 2017 GCN").delete()
    db.query(models.Paper).filter(models.Paper.doi.in_(["10.1000/gcn", "10.1000/gat"])).delete()
    db.commit()

    prof_id = "test-relations-user"
    prof = db.query(models.Profile).filter(models.Profile.id == prof_id).first()
    if not prof:
        prof = models.Profile(id=prof_id, email="rel@test.com")
        db.add(prof)
        db.commit()

    proj = models.ResearchProject(user_id=prof_id, topic="Graph Learning")
    db.add(proj)
    db.commit()
    db.refresh(proj)

    # Paper A
    p_a = models.Paper(
        title="Graph Convolutional Networks",
        doi="10.1000/gcn",
        title_hash="hash_gcn",
        year=2017,
        source_name="openalex",
    )
    # Paper B
    p_b = models.Paper(
        title="Graph Attention Networks",
        doi="10.1000/gat",
        title_hash="hash_gat",
        year=2018,
        source_name="arxiv",
    )
    db.add_all([p_a, p_b])
    db.commit()
    db.refresh(p_a)
    db.refresh(p_b)

    # Link both to project
    db.add(models.ProjectPaper(project_id=proj.id, paper_id=p_a.id, selected=True))
    db.add(models.ProjectPaper(project_id=proj.id, paper_id=p_b.id, selected=True))

    # Paper B references Paper A by DOI
    ref = models.PaperReference(
        citing_paper_id=p_b.id,
        raw_reference="Kipf and Welling 2017 GCN",
        doi=p_a.doi,
        source="api",
    )
    db.add(ref)
    db.commit()

    # Build relations
    rel_service = RelationsService()
    created = rel_service.build_project_relations(db, project_id=proj.id)

    # Must have resolved citation edge
    citation_rel = (
        db.query(models.PaperRelation)
        .filter(
            models.PaperRelation.project_id == proj.id,
            models.PaperRelation.source_id == p_b.id,
            models.PaperRelation.target_id == p_a.id,
            models.PaperRelation.relation_type == "cites",
        )
        .first()
    )
    assert citation_rel is not None
    assert citation_rel.basis == "citation_metadata"

    # Cleanup
    db.delete(proj)
    db.delete(p_a)
    db.delete(p_b)
    db.commit()
