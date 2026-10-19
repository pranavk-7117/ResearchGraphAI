import os
from pathlib import Path
from app.database import Base, SessionLocal, engine, get_db_info, execute_read_only_query
from app import models
from app.services.features import FeatureService
from app.services.pdf_ingestion import PDFIngestionService
from app.api.routes import list_sample_papers


def setup_module():
    Base.metadata.create_all(bind=engine)


def test_db_info_and_query():
    db = SessionLocal()
    try:
        info = get_db_info(db)
        assert "engine" in info
        assert "tables" in info
        assert info["total_tables"] >= 5

        # Test safe read-only SQL execution
        query_res = execute_read_only_query(db, "SELECT COUNT(*) as paper_count FROM papers")
        assert query_res["columns"] == ["paper_count"]
        assert len(query_res["rows"]) == 1
    finally:
        db.close()


def test_rag_chat_grounding_and_anti_hallucination():
    db = SessionLocal()
    try:
        features = FeatureService()

        # 1. On-topic question: must answer and cite papers
        res = features.rag_chat(db, "How does hierarchical planning coordinate autonomous multi-agent systems?")
        assert "answer" in res
        assert "citations" in res
        # Must return at least one citation or a disclosure message — never fabricate
        if len(res["citations"]) > 0:
            # Cited papers should be non-empty strings
            assert all(isinstance(c, str) and len(c) > 0 for c in res["citations"])
        else:
            # If no citations, the answer must be a disclosure (not fabricated content)
            assert "cannot find direct factual evidence" in res["answer"].lower() or "insufficient" in res["answer"].lower()

        # 2. Completely off-topic question: must refuse to hallucinate and state insufficient evidence
        off_topic_res = features.rag_chat(db, "What is the best recipe for baking chocolate chip cookies?")
        assert "citations" in off_topic_res
        assert len(off_topic_res["citations"]) == 0
        assert "cannot find direct factual evidence" in off_topic_res["answer"].lower()
    finally:
        db.close()


def test_dynamic_gaps():
    db = SessionLocal()
    try:
        features = FeatureService()
        gaps = features.gap_suggestions(db)
        assert len(gaps) > 0
        for gap in gaps:
            assert "cluster" in gap
            assert "topic" in gap
            assert "opportunity_type" in gap
            assert "coverage_score" in gap
            assert "weak_edge_types" in gap
            assert len(gap["weak_edge_types"]) > 0
            assert "research_questions" in gap
            assert len(gap["research_questions"]) > 0
    finally:
        db.close()


def test_dynamic_evolution_multi_domain():
    db = SessionLocal()
    try:
        features = FeatureService()

        # Evolution on AI Domain
        ai_evo = features.evolution_chain(db, paper_ids=None, topic="Artificial Intelligence", days=5)
        assert len(ai_evo["papers"]) >= 3
        assert len(ai_evo["reading_plan"]) == 5
        assert "literature_review" in ai_evo
        assert len(ai_evo["literature_review"]) > 50

        # Evolution on IoT Domain
        iot_evo = features.evolution_chain(db, paper_ids=None, topic="Internet of Things", days=3)
        assert len(iot_evo["papers"]) >= 3
        assert len(iot_evo["reading_plan"]) == 3
    finally:
        db.close()


def test_downloads_folder_save(tmp_path):
    test_downloads = tmp_path / "test_downloads"
    os.environ["DOWNLOADS_DIR"] = str(test_downloads)

    ingestion = PDFIngestionService()
    fake_pdf = b"%PDF-1.4 test dummy pdf content"
    saved = ingestion._save_to_downloads(fake_pdf, "demo_test_paper.pdf")

    assert Path(saved).exists()
    assert Path(saved).read_bytes() == fake_pdf
    assert "demo_test_paper" in Path(saved).name


def test_sample_papers_disk_folder():
    res = list_sample_papers()
    assert res["total_papers"] >= 20
    assert len(res["domains"]) >= 5
    domain_names = [d["domain_name"] for d in res["domains"]]
    assert any("Artificial Intelligence" in n for n in domain_names)
    assert any("Machine Learning" in n for n in domain_names)
    assert any("Internet of Things" in n for n in domain_names)
