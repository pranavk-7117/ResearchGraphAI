"""
Tests for Candidate Discovery, Client Rate Limits, Deduplication, and Multi-Feature Ranking.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.clients.base import RawCandidatePaper
from app.clients.openalex import OpenAlexClient, reconstruct_abstract
from app.services.discovery import DiscoveryService, hash_title, normalize_title


def test_openalex_abstract_reconstruction():
    inverted_index = {
        "This": [0],
        "is": [1],
        "a": [2],
        "reconstructed": [3],
        "abstract.": [4],
    }
    abstract = reconstruct_abstract(inverted_index)
    assert abstract == "This is a reconstructed abstract."
    assert reconstruct_abstract(None) is None


def test_candidate_deduplication():
    discovery = DiscoveryService()
    raw = [
        # Paper 1: DOI 10.1234/test
        RawCandidatePaper(
            source="openalex",
            external_id="W1",
            title="Transformer Architecture in NLP",
            doi="10.1234/test",
            citation_count=50,
        ),
        # Paper 2: Same DOI, different source -> must dedup
        RawCandidatePaper(
            source="semantic_scholar",
            external_id="S1",
            title="Transformer Architecture in Natural Language Processing",
            doi="10.1234/test",
            citation_count=45,
        ),
        # Paper 3: Fuzzy duplicate title without DOI -> must dedup
        RawCandidatePaper(
            source="arxiv",
            external_id="2101.0001",
            title="Transformer Architecture in NLP!",
            citation_count=0,
        ),
        # Paper 4: Distinct paper
        RawCandidatePaper(
            source="openalex",
            external_id="W2",
            title="Quantum Graph Neural Networks",
            doi="10.5678/quantum",
            citation_count=12,
        ),
    ]

    deduped = discovery._deduplicate_candidates(raw)
    assert len(deduped) == 2
    titles = [d.title for d in deduped]
    assert "Transformer Architecture in NLP" in titles
    assert "Quantum Graph Neural Networks" in titles


def test_ranking_modes():
    discovery = DiscoveryService()
    candidates = [
        RawCandidatePaper(
            source="openalex",
            external_id="P1",
            title="Foundational Classical Paper",
            abstract="Seminal work on routing algorithms.",
            year=2000,
            citation_count=5000,
            oa_pdf_url="https://example.com/p1.pdf",
        ),
        RawCandidatePaper(
            source="arxiv",
            external_id="P2",
            title="Recent Routing Breakthrough",
            abstract="Novel routing optimization algorithms.",
            year=2024,
            citation_count=5,
            oa_pdf_url="https://example.com/p2.pdf",
        ),
    ]

    # Mode: recent should rank 2024 paper higher
    ranked_recent = discovery._rank_candidates(candidates, topic="routing algorithms", mode="recent")
    assert ranked_recent[0][0].external_id == "P2"

    # Mode: citations should rank highly-cited paper higher
    ranked_cit = discovery._rank_candidates(candidates, topic="routing algorithms", mode="citations")
    assert ranked_cit[0][0].external_id == "P1"
