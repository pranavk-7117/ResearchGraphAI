import os
from pathlib import Path
from app.database import Base, SessionLocal, engine, get_db_info, execute_read_only_query
from app import models
from app.services.features import FeatureService
from app.services.pdf_ingestion import PDFIngestionService


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


def test_rag_chat_grounding():
    db = SessionLocal()
    try:
        features = FeatureService()
        res = features.rag_chat(db, "What is retrieval-augmented generation and how does it work?")
        assert "answer" in res
        assert "citations" in res
        assert len(res["answer"]) > 20
        # Ensure it didn't return an empty or canned response
        assert not res["answer"].startswith("Based on the retrieved papers, the collection points to graph-based organization")
    finally:
        db.close()


def test_downloads_folder_save(tmp_path):
    # Set DOWNLOADS_DIR to temporary path
    test_downloads = tmp_path / "test_downloads"
    os.environ["DOWNLOADS_DIR"] = str(test_downloads)

    ingestion = PDFIngestionService()
    fake_pdf = b"%PDF-1.4 test dummy pdf content"
    saved = ingestion._save_to_downloads(fake_pdf, "demo_test_paper.pdf")

    assert Path(saved).exists()
    assert Path(saved).read_bytes() == fake_pdf
    assert "demo_test_paper" in Path(saved).name
