"""
Tests for Hybrid RAG Chat Retrieval (pgvector dense + tsvector GIN FTS, RRF & Convex fusion),
no-evidence guard, project isolation, and citation formatting.
"""

import pytest
from unittest.mock import MagicMock
from sqlalchemy import text

from app import models
from app.database import SessionLocal
from app.services.chat import ChatService, fuse_retrieval_hits, min_max_normalize, normalize_authors


def test_normalize_authors():
    assert normalize_authors(None) == []
    assert normalize_authors("Single Author") == [{"name": "Single Author"}]
    assert normalize_authors(["Author A", "Author B"]) == [{"name": "Author A"}, {"name": "Author B"}]
    assert normalize_authors([{"name": "Dict Author"}]) == [{"name": "Dict Author"}]


def test_chat_query_rag_empty_project():
    """Ensure query_rag on a project with no papers returns cleanly with retrieved_count=0."""
    db = MagicMock()
    mock_project = MagicMock()
    mock_project.id = 999
    mock_project.topic = "Test Topic"
    db.query.return_value.filter.return_value.first.return_value = mock_project
    db.query.return_value.filter.return_value.all.return_value = []

    chat_service = ChatService()
    chat_service._hybrid_retrieve = MagicMock(return_value=[])

    res = chat_service.query_rag(db, 999, "What are the methodologies evaluated?")
    assert "session_id" in res
    assert "answer" in res
    assert res["retrieved_count"] == 0
    assert res["citations"] == []


def test_chat_query_rag_with_passages():
    """Ensure query_rag with retrieved passages correctly returns citations and count."""
    db = MagicMock()
    mock_project = MagicMock()
    mock_project.id = 999
    mock_project.topic = "Smart Insole"
    db.query.return_value.filter.return_value.first.return_value = mock_project
    db.query.return_value.filter.return_value.all.return_value = []

    chat_service = ChatService()
    chat_service._hybrid_retrieve = MagicMock(return_value=[
        {
            "chunk_id": 1,
            "paper_id": 10,
            "page": 1,
            "section": "Abstract",
            "text": "This paper presents a smart insole using piezoresistive sensors for plantar pressure monitoring.",
            "title": "Smart Insole Monitoring",
            "authors": [{"name": "Alice Smith"}],
            "doi": "10.1234/test",
            "year": 2023,
            "score": 0.9,
        }
    ])
    chat_service.llm.complete = MagicMock(
        return_value="### Evidence\n[1] Piezoresistive sensors measure pressure.\n\n### Interpretation\nEffective.\n\n### Suggestions\nTest."
    )

    res = chat_service.query_rag(db, 999, "What methodologies are evaluated?")
    assert res["retrieved_count"] == 1
    assert len(res["citations"]) == 1
    assert res["citations"][0]["paper_id"] == 10
    assert res["citations"][0]["ref"] == "[1]"

    # Unicode lenticular brackets 【1】 must normalize to [1] and still match citation
    chat_service.llm.complete = MagicMock(
        return_value="### Evidence\nPiezoresistive sensors measure pressure【1】."
    )
    res_uni = chat_service.query_rag(db, 999, "What sensors?")
    assert "[1]" in res_uni["answer"]
    assert len(res_uni["citations"]) == 1


def test_dense_only_hit():
    """Dense-only retrieval succeeds when FTS returns empty."""
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [(1,)]

    svc = ChatService(fusion_method="rrf", min_fused_score=0.005)
    svc._dense_search = MagicMock(return_value=[
        {"chunk_id": 101, "paper_id": 1, "page": 1, "section": "Body", "text": "Dense hit",
         "title": "P1", "authors": [], "doi": None, "year": 2023, "dense_score": 0.82, "score": 0.82}
    ])
    svc._fts_search = MagicMock(return_value=[])

    hits = svc._hybrid_retrieve(db, project_id=1, query="semantic concept")
    assert len(hits) == 1
    assert hits[0]["chunk_id"] == 101


def test_keyword_only_hit():
    """Keyword-only retrieval succeeds when dense search returns empty."""
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [(1,)]

    svc = ChatService(fusion_method="rrf", min_fused_score=0.005)
    svc._dense_search = MagicMock(return_value=[])
    svc._fts_search = MagicMock(return_value=[
        {"chunk_id": 202, "paper_id": 1, "page": 2, "section": "Methods", "text": "Exact acronym XYZ-42",
         "title": "P1", "authors": [], "doi": None, "year": 2023, "fts_score": 0.45, "score": 0.45}
    ])

    hits = svc._hybrid_retrieve(db, project_id=1, query="XYZ-42")
    assert len(hits) == 1
    assert hits[0]["chunk_id"] == 202


def test_fusion_ordering_rrf_and_convex():
    """Verify RRF and convex min-max normalized fusion ordering."""
    dense = [
        {"chunk_id": 1, "paper_id": 1, "dense_score": 0.90, "text": "A"},
        {"chunk_id": 2, "paper_id": 2, "dense_score": 0.80, "text": "B"},
        {"chunk_id": 3, "paper_id": 3, "dense_score": 0.50, "text": "C"},
    ]
    fts = [
        {"chunk_id": 2, "paper_id": 2, "fts_score": 0.80, "text": "B"},
        {"chunk_id": 4, "paper_id": 4, "fts_score": 0.40, "text": "D"},
    ]

    # RRF: chunk 2 appears in both (rank 1 dense + rank 0 fts) -> beats single-list chunk 1
    rrf_out = fuse_retrieval_hits(dense, fts, fusion_method="rrf", rrf_k=60)
    assert rrf_out[0]["chunk_id"] == 2

    # Convex alpha=0.5:
    # dense norm: c1=1.0, c2=0.75, c3=0.0
    # fts norm: c2=1.0, c4=0.0
    # c2 fused = 0.5*0.75 + 0.5*1.0 = 0.875 > c1 fused = 0.5*1.0 + 0 = 0.5
    convex_out = fuse_retrieval_hits(dense, fts, fusion_method="convex", alpha=0.5)
    assert convex_out[0]["chunk_id"] == 2
    assert abs(convex_out[0]["fused_score"] - 0.875) < 1e-5
    assert convex_out[1]["chunk_id"] == 1
    assert abs(convex_out[1]["fused_score"] - 0.5) < 1e-5

    # Pure dense alpha=1.0 puts c1 on top
    convex_dense = fuse_retrieval_hits(dense, fts, fusion_method="convex", alpha=1.0)
    assert convex_dense[0]["chunk_id"] == 1

    # Min-max edge case with identical positive scores -> 1.0
    assert min_max_normalize([0.7, 0.7]) == [1.0, 1.0]


def test_no_evidence_guard_fires_on_unrelated_query():
    """Unrelated query with below-threshold scores returns empty and never pads abstracts."""
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [(1,)]

    svc = ChatService(fusion_method="convex", min_fused_score=0.3)
    svc._dense_search = MagicMock(return_value=[])
    svc._fts_search = MagicMock(return_value=[])

    assert svc._hybrid_retrieve(db, project_id=1, query="unrelated sourdough recipe") == []

    # Even if fused score exists below min_fused_score, guard fires
    svc._dense_search = MagicMock(return_value=[
        {"chunk_id": 1, "paper_id": 1, "dense_score": 0.23, "text": "weak"},
        {"chunk_id": 2, "paper_id": 1, "dense_score": 0.25, "text": "slightly less weak"},
    ])
    # Force threshold higher than RRF max (~0.016)
    svc_rrf = ChatService(fusion_method="rrf", min_fused_score=0.05)
    svc_rrf._dense_search = svc._dense_search
    svc_rrf._fts_search = MagicMock(return_value=[])
    assert svc_rrf._hybrid_retrieve(db, project_id=1, query="threshold test") == []


def test_fts_search_query_formatting_and_guards():
    """Verify R1: FTS formats natural multi-term queries with OR semantics and caps at 12."""
    svc = ChatService()
    db = MagicMock()

    # 1. Empty query or empty paper_ids returns []
    assert svc._fts_search(db, paper_ids=[], query="some query") == []
    assert svc._fts_search(db, paper_ids=[1, 2], query="   ") == []
    assert svc._fts_search(db, paper_ids=[1, 2], query="a an to") == []  # all < 3 chars

    # 2. 7-term query without operators: verifies execute called with " or " joined tokens
    db.execute.return_value.fetchall.return_value = []
    svc._fts_search(
        db,
        paper_ids=[10, 20],
        query="what are primary methodologies evaluated smart insole",
    )
    call_args = db.execute.call_args[0]
    sql_text = str(call_args[0])
    params = db.execute.call_args[1] if len(db.execute.call_args) > 1 and db.execute.call_args[1] else call_args[1]
    assert "ts_rank_cd(c.text_tsv, websearch_to_tsquery('english', :query), 1)" in sql_text
    # Param should have joined with ' or '
    assert " or " in params["query"]
    assert "methodologies" in params["query"]
    assert "insole" in params["query"]

    # 3. Query with explicit quotes preserves exact expression
    svc._fts_search(db, paper_ids=[10], query='"smart insole" -diabetes')
    params_quoted = db.execute.call_args[0][1]
    assert params_quoted["query"] == '"smart insole" -diabetes'


@pytest.mark.live_db
def test_hybrid_db_isolation_and_gin_explain():
    """
    Live PostgreSQL test:
    1. Verifies retrieval never leaks chunks from another project.
    2. Verifies unrelated queries trigger the no-evidence guard.
    3. Verifies EXPLAIN shows GIN index usage on paper_chunks.text_tsv.
    """
    db = SessionLocal()
    try:
        prof_id = "test-t1-hybrid-user"
        if not db.query(models.Profile).filter(models.Profile.id == prof_id).first():
            db.add(models.Profile(id=prof_id, email="t1@test.com"))
            db.commit()

        proj_a = models.ResearchProject(user_id=prof_id, topic="Project A Cryogenic Quantum")
        proj_b = models.ResearchProject(user_id=prof_id, topic="Project B Botanical Taxonomy")
        db.add_all([proj_a, proj_b])
        db.commit()
        db.refresh(proj_a)
        db.refresh(proj_b)

        svc = ChatService(fusion_method="rrf", min_dense_similarity=0.30)
        v_a = svc.embeddings.embed("Superconducting transmon qubit coherence at millikelvin temperatures")
        v_b = svc.embeddings.embed("Rare orchid petal morphology and pollination in tropical rainforests")

        p_a = models.Paper(title="Transmon Qubit Paper", title_hash="t1_hash_a", source_name="test")
        p_b = models.Paper(title="Orchid Botany Paper", title_hash="t1_hash_b", source_name="test")
        db.add_all([p_a, p_b])
        db.commit()
        db.refresh(p_a)
        db.refresh(p_b)

        db.add(models.ProjectPaper(project_id=proj_a.id, paper_id=p_a.id, selected=True))
        db.add(models.ProjectPaper(project_id=proj_b.id, paper_id=p_b.id, selected=True))

        c_a = models.PaperChunk(
            paper_id=p_a.id, page_start=1, section="Body", chunk_index=0,
            text="Superconducting transmon qubit coherence at millikelvin temperatures.",
            text_hash="t1_chunk_a", embedding=v_a,
        )
        c_b = models.PaperChunk(
            paper_id=p_b.id, page_start=1, section="Body", chunk_index=0,
            text="Rare orchid petal morphology and pollination in tropical rainforests.",
            text_hash="t1_chunk_b", embedding=v_b,
        )
        db.add_all([c_a, c_b])
        db.commit()

        # Query proj_a for proj_b's content -> must return [] (never leak proj_b!)
        leaked = svc._hybrid_retrieve(db, proj_a.id, "orchid petal pollination rainforests")
        assert all(h["paper_id"] == p_a.id for h in leaked)
        assert len(leaked) == 0

        # Query proj_a for its own content -> returns p_a
        hits_a = svc._hybrid_retrieve(db, proj_a.id, "transmon qubit millikelvin")
        assert len(hits_a) >= 1
        assert all(h["paper_id"] == p_a.id for h in hits_a)

        # Force planner to prefer index scan over sequential scan on small test table
        db.execute(text("SET LOCAL enable_seqscan = off;"))

        # Verify EXPLAIN uses GIN index ix_paper_chunks_text_tsv_gin
        explain_rows = db.execute(
            text(
                "EXPLAIN SELECT id, ts_rank_cd(text_tsv, websearch_to_tsquery('english', :q)) "
                "FROM paper_chunks WHERE text_tsv @@ websearch_to_tsquery('english', :q)"
            ),
            {"q": "transmon qubit"},
        ).fetchall()
        plan_text = "\n".join(r[0] for r in explain_rows)
        assert "ix_paper_chunks_text_tsv_gin" in plan_text or "Bitmap Index Scan" in plan_text
    finally:
        for t in ("Project A Cryogenic Quantum", "Project B Botanical Taxonomy"):
            proj = db.query(models.ResearchProject).filter(models.ResearchProject.topic == t).first()
            if proj:
                db.delete(proj)
        for h in ("t1_hash_a", "t1_hash_b"):
            p = db.query(models.Paper).filter(models.Paper.title_hash == h).first()
            if p:
                db.delete(p)
        db.commit()
        db.close()


def test_onnx_embedder_runs_without_importing_torch():
    """Verify ONNX Runtime MiniLM embedder produces normalized 384-d vectors without PyTorch."""
    import sys
    from app.services.embeddings import EMBED_DIM, get_onnx_embedder

    onnx_emb = get_onnx_embedder()
    if onnx_emb is None:
        return  # Skip gracefully if onnxruntime/cache absent in offline CI
    vecs = onnx_emb.encode(["Smart insole plantar pressure offloading"])
    assert vecs.shape == (1, EMBED_DIM)
    norm = float((vecs[0] ** 2).sum() ** 0.5)
    assert abs(norm - 1.0) < 1e-4


def test_worker_main_runs_safely_in_background_thread(monkeypatch):
    """Worker loop must skip signal.signal when launched inside in_process_worker thread."""
    import threading
    from app import worker

    errors = []

    def fake_sleep(_sec):
        worker.RUNNING = False

    monkeypatch.setattr(worker.time, "sleep", fake_sleep)
    monkeypatch.setattr(worker, "SessionLocal", MagicMock())
    monkeypatch.setattr(worker.JobService, "acquire_next_job", MagicMock(return_value=None))
    worker.RUNNING = True

    def target():
        try:
            worker.main()
        except Exception as exc:
            errors.append(exc)

    t = threading.Thread(target=target, name="in_process_worker")
    t.start()
    t.join(timeout=5.0)
    assert not errors, f"Worker thread raised: {errors}"
