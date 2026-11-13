"""
Tests for Round 3 facts extraction improvements (Tasks E1, E2, E5, E6, E7).
Tests cue lexicon scoring, semantic validation, paper classification, and extraction states.
"""
import pytest
from app.services.facts_extraction import (
    classify_paper_kind,
    score_chunk_for_cues,
    select_candidate_chunks,
    validate_extracted_item,
    parse_structured_items,
    FactExtractionService,
)


def test_classify_paper_kind():
    # Survey classifications
    assert classify_paper_kind("A Comprehensive Survey on Deep Learning", "We review the landscape...") == "survey"
    assert classify_paper_kind("Graph Neural Networks: A Systematic Literature Review", "This systematic review covers...") == "survey"
    assert classify_paper_kind("Recent Advances in NLP: A Meta-Analysis", "Meta-analysis of benchmark results.") == "survey"
    assert classify_paper_kind("An Overview on the Current Status of Biomarkers", "This paper provides a state of the art summary.") == "survey"

    # Empirical questionnaire surveys (must NOT be misclassified as literature surveys)
    assert classify_paper_kind("Management of Diabetic Foot Ulcers: An International Survey", "We administered a survey of clinicians across 14 hospitals.") == "empirical"
    assert classify_paper_kind("Physical Activity in Neuropathy: A Questionnaire Survey", "A cross-sectional survey of patients was conducted.") == "empirical"

    # Word-boundary check: 'biotic' must not match 'iot' and turn into a system paper
    assert classify_paper_kind("Biotic and Abiotic Stresses in Crops", "Plant genetics under environmental stress.") != "system"

    # Empirical classifications
    assert classify_paper_kind("Evaluating Treatment Efficacy in Diabetic Patients", "We conduct a randomized controlled trial with cohort analysis.") == "empirical"

    # System classifications (matches architecture / prototype / hardware, not topic hardcodes)
    assert classify_paper_kind("AutoGraph: An Automated Graph Processing Framework", "We design an open-source pipeline and framework architecture.") == "system"
    assert classify_paper_kind("Low-Cost Wearable Hardware Prototype for Gait Monitoring", "We design an embedded system architecture.") == "system"

    # Theory classifications
    assert classify_paper_kind("On the Convergence Bounds of SGD", "We establish theorems and asymptotic convergence proofs.") == "theory"

    # Unknown fallback
    assert classify_paper_kind("Deep Learning", "Some notes on algorithms.") == "unknown"


def test_score_chunk_for_cues():
    chunk_lim = {
        "text": "A key limitation of our study is the small sample size and lack of diverse demographics.",
        "section": "Limitations",
    }
    score_lim = score_chunk_for_cues(chunk_lim)
    assert score_lim >= 7.0  # section boost (+5) + phrase matches

    chunk_body = {
        "text": "The loss function converges after twenty epochs with standard Adam optimizer.",
        "section": "Body",
    }
    score_body = score_chunk_for_cues(chunk_body)
    assert score_body == 0.0

    chunk_future = {
        "text": "Future research should explore extending this architecture to multimodal video streams.",
        "section": "Conclusion",
    }
    score_future = score_chunk_for_cues(chunk_future)
    assert score_future >= 4.0  # section boost (+3) + cue phrase


def test_select_candidate_chunks_ranking():
    chunks = [
        {"id": 1, "text": "Regular background intro", "section": "Introduction"},
        {"id": 2, "text": "A notable limitation is the absence of longitudinal follow-up.", "section": "Discussion"},
        {"id": 3, "text": "Our findings suggest further work is needed on edge devices.", "section": "Future Work"},
        {"id": 4, "text": "Benchmark table showing 94.2 percent accuracy.", "section": "Results"},
    ]
    candidates = select_candidate_chunks(chunks, max_chunks=2)
    cand_ids = [c["id"] for c in candidates]
    # Chunks 2 and 3 should have highest cue scores
    assert cand_ids[0] in [2, 3]
    assert cand_ids[1] in [2, 3]


def test_semantic_validation_rejects_echoes_and_short():
    title = "Graph Neural Networks for Diabetic Foot Ulcer Detection"
    abstract = "This paper presents a graph neural network method for diabetic foot ulcer detection in ambulatory monitoring."

    # 1. Reject too short (< 6 tokens)
    res_short = validate_extracted_item(
        "Too short item.",
        field_name="limitations",
        title=title,
        abstract=abstract,
    )
    assert res_short["valid"] is False
    assert res_short["reject_reason"] == "too_short"

    # 2. Reject title echo (> 0.6 overlap)
    res_echo = validate_extracted_item(
        "Graph neural networks for diabetic foot ulcer detection methods",
        field_name="limitations",
        title=title,
        abstract=abstract,
    )
    assert res_echo["valid"] is False
    assert res_echo["reject_reason"] == "title_echo"

    # 3. Reject abstract echo (> 0.85 overlap)
    res_ab_echo = validate_extracted_item(
        "This paper presents a graph neural network method for diabetic foot ulcer detection in ambulatory monitoring",
        field_name="limitations",
        title=title,
        abstract=abstract,
    )
    assert res_ab_echo["valid"] is False
    assert res_ab_echo["reject_reason"] == "abstract_echo"

    # 4. Reject generic background statement lacking limitation phrasing
    res_generic = validate_extracted_item(
        "The number of connected vehicles has grown very quickly in recent years worldwide.",
        field_name="limitations",
        title=title,
        abstract=abstract,
    )
    assert res_generic["valid"] is False
    assert res_generic["reject_reason"] == "not_a_limitation"

    # 5. Accept valid specific limitation with genuine limitation indicator
    valid_lim = "Evaluation was restricted to synthetic gait simulations without real in-clinic patient trials."
    res_valid = validate_extracted_item(
        valid_lim,
        field_name="limitations",
        title=title,
        abstract=abstract,
    )
    assert res_valid["valid"] is True
    assert res_valid["reject_reason"] is None


def test_parse_structured_items_clean_list():
    raw_list = [
        {"value": "Sample size was restricted to only 15 healthy adult participants.", "quote": "only 15 participants"},
        {"value": "Hardware sensor drift required manual calibration every two hours.", "quote": ""},
        "Short.",  # should be filtered out by validation
    ]
    title = "Wearable Pressure Sensor Calibration"
    abstract = "We evaluate wearable pressure sensors in smart insole designs."

    cleaned = parse_structured_items(raw_list, "limitations", title, abstract, max_items=5)
    assert len(cleaned) == 2
    assert all("value" in item for item in cleaned)
    assert "Sample size was restricted" in cleaned[0]["value"]
    assert "Hardware sensor drift" in cleaned[1]["value"]


def test_paper_facts_model_has_check_constraints():
    from app.models import PaperFact
    from sqlalchemy import CheckConstraint

    constraints = [c for c in PaperFact.__table__.constraints if isinstance(c, CheckConstraint)]
    c_names = {c.name for c in constraints}
    assert "ck_paper_facts_status" in c_names
    assert "ck_paper_facts_source_scope" in c_names
    assert "ck_paper_facts_paper_kind" in c_names
