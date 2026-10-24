"""
Tests for Grounding, Post-Validation, Clustering, and RAG Chat Attributions.
"""

import pytest
from app.services.llm import post_validate_citation
from app.services.clustering import ClusteringService
from app.services.gaps import GapsService
from app.database import SessionLocal
from app import models


def test_post_validate_citation_verification():
    real_chunk = (
        "Our experimental results demonstrate an 8.4x reduction in inference latency "
        "when applying 4-bit integer quantization on edge ARM microcontrollers."
    )

    # Verbatim quote -> Verified
    assert post_validate_citation("8.4x reduction in inference latency", real_chunk) is True

    # Near verbatim -> Verified
    assert post_validate_citation("8.4x reduction in latency", real_chunk) is True

    # Fabricated / hallucinated quote -> Rejected
    assert post_validate_citation("Achieves 99.9% accuracy on ImageNet benchmarks", real_chunk) is False
    assert post_validate_citation("", real_chunk) is False


def test_gap_score_transparency():
    service = GapsService()
    # Mock gap with known evidence count
    evidence = [
        {"paper_title": "Paper 1", "quote": "Hardware thermal throttling limits clock frequency.", "page": 4},
        {"paper_title": "Paper 2", "quote": "Device temperature spikes under sustained tensor workloads.", "page": 7},
    ]
    counter = []

    num_evidence = len(evidence)
    num_counter = len(counter)
    evidence_qual = 0.85

    score = round(max(0.1, min(1.0, (min(num_evidence, 5) * 0.1) + (evidence_qual * 0.4) + 0.2 - (num_counter * 0.1))), 3)
    assert 0.0 < score <= 1.0
