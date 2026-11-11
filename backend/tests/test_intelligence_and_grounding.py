"""
Tests for Strict Quote Verification (T3), Fact Extraction Chunk Grounding,
Gap Evidence Filtering, and Corpus Quote Precision.
"""

from unittest.mock import MagicMock
from app.services.llm import post_validate_citation
from app.services.facts_extraction import FactExtractionService, ExtractedField, PaperFactsSchema, quote_verification_precision
from app.services.gaps import compute_gap_score, verify_evidence_list


def test_post_validate_citation_verification():
    real_chunk = (
        "Our experimental results demonstrate an 8.4x reduction in infer-\n"
        "ence latency when applying 4-bit integer quantization on edge ARM microcontrollers."
    )

    # 1. Exact normalized match (handles line-break hyphenation & case) -> Verified
    res_exact = post_validate_citation("8.4x REDUCTION in inference latency", real_chunk, chunk_id=42)
    assert res_exact["verified"] is True
    assert res_exact["chunk_id"] == 42
    assert res_exact["match_type"] == "exact"
    assert res_exact["score"] == 1.0

    # 2. Token-sequence match >= 0.9 of tokens in order (10/11 = 0.909)
    chunk_long = "we observe significant accuracy gains across ten cross validation clinical benchmarks today"
    near_quote = "we observe significant accuracy gains across cross validation clinical benchmarks today"
    res_near = post_validate_citation(near_quote, chunk_long, chunk_id=7, threshold=0.9)
    assert res_near["verified"] is True
    assert res_near["match_type"] == "token_sequence"
    assert res_near["score"] >= 0.9

    # 3. Near-match below 0.9 threshold -> Fails (8/10 = 0.8 < 0.9)
    below_quote = "we observe significant accuracy gains without tuning over clinical benchmarks today"
    res_below = post_validate_citation(below_quote, chunk_long, chunk_id=7, threshold=0.9)
    assert res_below["verified"] is False

    # 4. Paraphrase -> Fails
    res_para = post_validate_citation(
        "Latency dropped more than eightfold due to low-precision compression on microcontrollers",
        real_chunk,
        chunk_id=42,
    )
    assert res_para["verified"] is False
    assert res_para["match_type"] == "none"

    # 5. Empty quote -> Fails
    assert post_validate_citation("", real_chunk, chunk_id=42)["verified"] is False


def test_quote_in_different_chunk_fails_for_claimed_chunk():
    """A quote that exists only in chunk 2 must fail when claimed for chunk 1."""
    db = MagicMock()
    paper = MagicMock(id=1, title="Test Paper", abstract="Fallback abstract")
    c1 = MagicMock(id=101, paper_id=1, page_start=1, section="Intro", chunk_index=0,
                   text="Transformers process token sequences in parallel.")
    c2 = MagicMock(id=102, paper_id=1, page_start=2, section="Results", chunk_index=1,
                   text="Our quantized model achieved 94.2% F1 score on SciFact.")

    db.query.return_value.filter.return_value.first.return_value = paper
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [c1, c2]

    svc = FactExtractionService()
    svc.llm.is_available = MagicMock(return_value=True)
    svc.llm.provider = "mock"
    svc.llm.generate_structured = MagicMock(return_value=PaperFactsSchema(
        # Claims quote from c2 (102) belongs to chunk_id=101 -> MUST fail verification!
        results=ExtractedField(
            value="94.2% F1 on SciFact",
            quote="achieved 94.2% F1 score on SciFact",
            chunk_id=101,
            page=1,
            confidence=0.95,
        ),
        # Correctly claims chunk_id=101 for c1 quote -> MUST pass!
        method=ExtractedField(
            value="Parallel token processing",
            quote="Transformers process token sequences in parallel",
            chunk_id=101,
            page=1,
            confidence=0.9,
        ),
    ))

    fact_row = svc.extract_paper_facts(db, paper_id=1, project_id=10)
    assert fact_row.results["verified"] is False
    assert fact_row.method["verified"] is True
    assert fact_row.method["chunk_id"] == 101


def test_gap_score_excludes_unverified_quotes():
    chunks_by_pid = {
        1: [{"chunk_id": 11, "text": "Hardware thermal throttling limits clock frequency under load."}],
        2: [{"chunk_id": 22, "text": "Device temperature spikes during sustained workloads."}],
    }
    title_to_pid = {"paper 1": 1, "paper 2": 2}

    raw_evidence = [
        {"paper_title": "Paper 1", "quote": "Hardware thermal throttling limits clock frequency", "page": 4},
        {"paper_title": "Paper 2", "quote": "Completely fabricated quote not in paper 2", "page": 7},
    ]
    verified_list = verify_evidence_list(raw_evidence, chunks_by_pid, title_to_pid)

    assert len(verified_list) == 2
    assert verified_list[0]["verified"] is True
    assert verified_list[0]["chunk_id"] == 11
    assert verified_list[1]["verified"] is False  # Kept and flagged!

    # Score uses ONLY verified quotes (1 verified, not 2)
    verified_count = sum(1 for e in verified_list if e["verified"])
    assert verified_count == 1
    assert compute_gap_score(verified_count, 0, 0.85) < compute_gap_score(2, 0, 0.85)
    # Zero verified quotes -> minimum 0.1
    assert compute_gap_score(0, 0, 0.85) == 0.1


def test_quote_verification_precision_metric():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.side_effect = [
        [(1,)],  # project_papers paper_ids
        [
            MagicMock(
                research_question={"value": "RQ", "quote": "real quote 1", "verified": True},
                problem={"value": "P", "quote": "fake quote", "verified": False},
                method=None, algorithm_or_model=None, dataset=None, metrics=None,
                results=None, limitations=None, future_work=None, claimed_contributions=None,
            )
        ],  # facts
        [
            MagicMock(
                supporting_evidence=[{"quote": "gap real quote", "verified": True}],
                counter_evidence=[{"quote": "gap unverified", "verified": False}],
            )
        ],  # gaps
    ]

    precision = quote_verification_precision(project_id=1, db=db)
    assert precision == 0.5  # 2 verified / 4 total quotes
