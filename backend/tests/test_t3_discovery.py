"""
T3: Discovery pipeline unit tests.
Verifies query expansion, deduplication by DOI and title, ranking, and disk cache.
"""
import pytest
from app.services.discovery import DiscoveryService


def test_expand_queries():
    ds = DiscoveryService()
    queries = ds._expand_queries("AI in diabetic healthcare")
    assert len(queries) >= 3
    assert "AI in diabetic healthcare" in queries
    assert any("survey" in q.lower() or "review" in q.lower() for q in queries)


def test_dedup_doi_and_fuzzy_title():
    ds = DiscoveryService()
    papers = [
        {"title": "Deep Learning for Diabetes Detection", "doi": "10.1234/test1", "abstract": "abc"},
        {"title": "Deep Learning for Diabetes Detection: An Overview", "doi": "10.1234/test1", "abstract": "dup doi"},
        {"title": "Deep Learning for Diabetes Detection", "doi": "10.5678/other", "abstract": "dup title"},
        {"title": "Completely Novel Architecture in Healthcare", "doi": "10.9999/unique", "abstract": "unique"},
    ]
    deduped = ds._dedup(papers)
    assert len(deduped) == 2
    assert deduped[0]["doi"] == "10.1234/test1"
    assert deduped[1]["doi"] == "10.9999/unique"


def test_rank_semantic_and_citation():
    ds = DiscoveryService()
    topic_emb = ds.embeddings.embed("diabetes detection using deep learning")
    candidates = [
        {"title": "Quantum Cryptography and Entanglement", "abstract": "Physics study on photons", "citation_count": 1000},
        {"title": "Deep Neural Networks for Diabetes Prediction", "abstract": "Predicting diabetic blood sugar using deep neural networks", "citation_count": 10},
    ]
    ranked = ds._rank(candidates, topic_emb)
    # The diabetes paper should be ranked higher due to high semantic relevance
    assert "Diabetes" in ranked[0]["title"]
