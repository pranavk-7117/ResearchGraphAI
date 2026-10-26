import pytest
from app import models
from app.services.chat import ChatService, normalize_authors


def test_normalize_authors():
    assert normalize_authors(None) == []
    assert normalize_authors("Single Author") == [{"name": "Single Author"}]
    assert normalize_authors(["Author A", "Author B"]) == [{"name": "Author A"}, {"name": "Author B"}]
    assert normalize_authors([{"name": "Dict Author"}]) == [{"name": "Dict Author"}]


def test_chat_query_rag_empty_project(db_session=None):
    """Ensure query_rag on a project with no papers returns cleanly with retrieved_count=0."""
    from unittest.mock import MagicMock
    db = MagicMock()
    mock_project = MagicMock()
    mock_project.id = 999
    mock_project.topic = "Test Topic"
    db.query.return_value.filter.return_value.first.return_value = mock_project
    db.query.return_value.filter.return_value.all.return_value = []

    chat_service = ChatService()
    # Stub _hybrid_retrieve to return []
    chat_service._hybrid_retrieve = MagicMock(return_value=[])

    res = chat_service.query_rag(db, 999, "What are the methodologies evaluated?")
    assert "session_id" in res
    assert "answer" in res
    assert res["retrieved_count"] == 0
    assert res["citations"] == []


def test_chat_query_rag_with_passages():
    """Ensure query_rag with retrieved passages correctly returns citations and count."""
    from unittest.mock import MagicMock
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
    # Mock LLM complete
    chat_service.llm.complete = MagicMock(return_value="### Evidence\n[1] Piezoresistive sensors measure pressure.\n\n### Interpretation\nEffective monitoring.\n\n### Suggestions\nTest with more patients.")

    res = chat_service.query_rag(db, 999, "What methodologies are evaluated?")
    assert res["retrieved_count"] == 1
    assert len(res["citations"]) == 1
    assert res["citations"][0]["paper_id"] == 10
    assert res["citations"][0]["ref"] == "[1]"
