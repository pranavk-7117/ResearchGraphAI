"""
Tests for T12: Auditable Bipartite Gap Matrix, UnionFind Signal Clustering, and Quote Dropping.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app import models
from app.services.gap_matrix import build_method_task_matrix, cluster_limitation_signals
from app.services.gaps import GapsService, SynthesizedGap, compute_gap_score


def test_bipartite_matrix_normalizes_synonyms_and_finds_known_empty_cell():
    """Known bipartite corpus merges plural synonyms and identifies exact empty void cell stats."""
    rows = [
        (1, "P1", SimpleNamespace(method={"value": "Transformers"}, algorithm_or_model=None, dataset={"value": "ImageNet"}, problem=None)),
        (2, "P2", SimpleNamespace(method={"value": "Transformer"}, algorithm_or_model=None, dataset={"value": "ImageNet"}, problem=None)),
        (3, "P3", SimpleNamespace(method={"value": "transformer"}, algorithm_or_model=None, dataset={"value": "ImageNet"}, problem=None)),
        (4, "P4", SimpleNamespace(method={"value": "Graph Neural Networks"}, algorithm_or_model=None, dataset={"value": "Protein Folding"}, problem=None)),
        (5, "P5", SimpleNamespace(method={"value": "Graph Neural Network"}, algorithm_or_model=None, dataset={"value": "Protein Folding"}, problem=None)),
        (6, "P6", SimpleNamespace(method={"value": "graph neural networks"}, algorithm_or_model=None, dataset={"value": "Protein Folding"}, problem=None)),
        (7, "P7", SimpleNamespace(method={"value": "Diffusion"}, algorithm_or_model=None, dataset={"value": "ImageNet"}, problem=None)),
        (8, "P8", SimpleNamespace(method={"value": "Diffusion"}, algorithm_or_model=None, dataset={"value": "ImageNet"}, problem=None)),
    ]

    mat = build_method_task_matrix(rows, min_support=2)
    assert mat["total_papers"] == 8
    # Synonyms collapsed cleanly into 3 canonical methods & 2 canonical tasks
    assert len(mat["methods"]) == 3
    assert len(mat["tasks"]) == 2

    void_pairs = {(c["method"], c["task"]): c for c in mat["candidates"]}
    assert ("transformer", "protein folding") in void_pairs
    cell = void_pairs[("transformer", "protein folding")]
    assert cell["count"] == 0
    assert cell["row_support"] == 3
    assert cell["col_support"] == 3
    assert abs(cell["expected"] - 1.125) < 1e-6
    # Hand-computed hypergeom.cdf(0, 8, 3, 3) = C(5,3) / C(8,3) = 10 / 56 = 0.178571...
    assert abs(cell["hypergeom_p"] - 0.1786) < 1e-4
    assert cell["pmi"] < 0


def test_signal_clustering_uses_all_signals_without_15_cap():
    """All 20 limitation signals must be clustered via UnionFind (no [:15] cap)."""
    signals = [
        {
            "paper_id": i,
            "title": f"Paper {i}",
            "year": 2023,
            "type": "limitation",
            "text": f"Theme {'A' if i <= 12 else 'B'} sample {i}",
            "quote": f"quote {i}",
            "page": 1,
            "chunk_id": i,
            "verified": True,
        }
        for i in range(1, 21)
    ]

    def fake_embed(texts):
        return [[1.0, 0.0] if "Theme A" in t else [0.0, 1.0] for t in texts]

    clusters = cluster_limitation_signals(signals, fake_embed, sim_threshold=0.75)
    assert len(clusters) == 2
    assert sum(len(c["signals"]) for c in clusters) == 20
    assert clusters[0]["paper_count"] == 12
    assert clusters[1]["paper_count"] == 8


def test_detect_gaps_drops_unverified_quotes_and_marks_likely_addressed():
    """Unverified LLM quotes are dropped from persisted gaps and >5 OpenAlex hits trigger likely_addressed."""
    papers = [
        MagicMock(id=1, title="Paper Alpha", year=2022),
        MagicMock(id=2, title="Paper Beta", year=2023),
    ]
    chunks = [
        MagicMock(id=101, paper_id=1, chunk_index=0, page_start=2, text="Latency increases quadratically on long sequences beyond 8k tokens."),
        MagicMock(id=201, paper_id=2, chunk_index=0, page_start=3, text="Sparse attention shows stable accuracy on short prompts."),
    ]
    facts = [
        MagicMock(
            paper_id=1,
            method={"value": "Dense Attention"},
            algorithm_or_model=None,
            dataset={"value": "LongContext"},
            problem=None,
            limitations={"value": "Quadratic latency beyond 8k tokens", "quote": "Latency increases quadratically on long sequences beyond 8k tokens.", "page": 2, "chunk_id": 101, "verified": True},
            future_work=None,
        ),
        MagicMock(
            paper_id=2,
            method={"value": "Sparse Attention"},
            algorithm_or_model=None,
            dataset={"value": "ShortPrompt"},
            problem=None,
            limitations={"value": "Short context only", "quote": "Sparse attention shows stable accuracy on short prompts.", "page": 3, "chunk_id": 201, "verified": True},
            future_work=None,
        ),
    ]

    db = MagicMock()
    project = MagicMock(id=1, topic="Efficient Transformers", corpus_version=1)

    def q_side_effect(model, *args):
        q = MagicMock()
        if model is models.ResearchGap:
            q.filter.return_value.delete.return_value = 0
            return q
        if model is models.ResearchGap.statement_hash:
            q.filter.return_value.all.return_value = []
            return q
        if model is models.ResearchProject:
            q.filter.return_value.first.return_value = project
        elif model is models.ProjectPaper:
            q.filter.return_value.all.return_value = [MagicMock(paper_id=1), MagicMock(paper_id=2)]
        elif model is models.Paper:
            q.filter.return_value.all.return_value = papers
        elif model is models.PaperChunk:
            q.filter.return_value.order_by.return_value.all.return_value = chunks
        elif model is models.PaperFact:
            q.filter.return_value.all.return_value = facts
        return q

    db.query.side_effect = q_side_effect

    svc = GapsService.__new__(GapsService)
    svc.llm = MagicMock()
    svc.llm.is_available.return_value = True
    svc.embeddings = MagicMock()
    svc.embeddings.embed_batch.return_value = [[1.0, 0.0], [0.9, 0.1]]
    svc.openalex = MagicMock()
    # 7 OpenAlex hits > default threshold 5 -> likely_addressed
    svc.openalex.search.return_value = [
        SimpleNamespace(title=f"Ext {i}", year=2024, doi=f"10.1/{i}", citation_count=10)
        for i in range(7)
    ]

    class Batch:
        gaps = [
            SynthesizedGap(
                gap_statement="Sparse attention remains unvalidated on long sequences beyond 8k tokens.",
                why_it_matters="Real documents exceed 8k tokens.",
                gap_type="evaluation_void",
                supporting_evidence=[
                    {"paper_title": "Paper Alpha", "quote": "Latency increases quadratically on long sequences beyond 8k tokens", "page": 2},
                    {"paper_title": "Paper Beta", "quote": "Completely fabricated claim missing from chunk 201", "page": 3},
                ],
                counter_evidence=[],
                corpus_cannot_establish="Hardware kernel optimizations.",
                suggested_research_question="How does sparse attention scale past 8k?",
                suggested_validation="Benchmark on 32k tokens.",
            )
        ]

    svc.llm.generate_structured.return_value = Batch()

    created = svc.detect_gaps(db, project_id=1)
    assert len(created) == 1
    row = created[0]
    # Unverified quote dropped!
    assert len(row.supporting_evidence) == 1
    assert row.supporting_evidence[0]["paper_id"] == 1
    assert row.score_components["unverified_quotes_dropped"] == 1
    assert row.status == "likely_addressed"
    expected_score = compute_gap_score(1, 0, 0.85, matrix_void_bonus=0.0, external_penalty=0.65)
    assert row.evidence_strength == expected_score
    assert row.score_components["calculated_strength"] == expected_score
