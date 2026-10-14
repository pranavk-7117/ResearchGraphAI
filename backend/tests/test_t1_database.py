import pytest
from app.database import SessionLocal, init_db
from app import models
from app.services.vector_store import VectorStore
from app.services.embeddings import EmbeddingService, cosine_similarity


def test_migration_runs_idempotently():
    """T1 ACCEPT 1: Migration runs twice with no error."""
    init_db()
    init_db()


def test_insert_embedding_and_nearest_neighbour():
    """T1 ACCEPT 2: Insert a row with an embedding and a nearest-neighbour query returns it."""
    db = SessionLocal()
    embed_svc = EmbeddingService()
    vector_store = VectorStore()

    test_title = "T1 Test Paper on Diabetic Retinopathy"
    vec = embed_svc.embed(test_title)

    paper = models.Paper(
        title=test_title,
        authors="Test Researcher",
        abstract="Deep learning models for blood glucose management in type 2 diabetes.",
        year=2024,
        source_type="test",
        whole_embedding=vec,
    )
    db.add(paper)
    db.flush()

    chunk = models.PaperChunk(
        paper_id=paper.id,
        chunk_index=0,
        text="Convolutional neural networks achieve 96% accuracy on retinal lesions.",
        embedding=vec,
    )
    db.add(chunk)
    db.commit()

    try:
        hits = vector_store.search_chunks(db, vec, limit=1)
        assert len(hits) >= 1
        score, hit_chunk = hits[0]
        assert hit_chunk.id == chunk.id
        assert score > 0.99
    finally:
        db.delete(chunk)
        db.flush()
        db.delete(paper)
        db.commit()
        db.close()


def test_semantic_similarity_relative_scoring():
    """T1 ACCEPT 3: Semantically related phrases score higher than unrelated ones."""
    embed_svc = EmbeddingService()

    v_diabetes = embed_svc.embed("diabetes")
    v_glucose = embed_svc.embed("blood glucose")
    v_astronomy = embed_svc.embed("quantum cosmology galaxy")

    score_related = cosine_similarity(v_diabetes, v_glucose)
    score_unrelated = cosine_similarity(v_diabetes, v_astronomy)

    assert score_related > score_unrelated, (
        f"Related score ({score_related}) should be higher than unrelated ({score_unrelated})"
    )


def test_app_database_connection():
    """T1 ACCEPT 4: App boots and connects against Supabase PostgreSQL."""
    from app.database import engine
    from sqlalchemy import text

    with engine.connect() as conn:
        res = conn.execute(text("SELECT 1;")).fetchone()
        assert res[0] == 1

        ext_check = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector';")
        ).fetchone()
        assert ext_check is not None
        assert ext_check[0] == "vector"
