"""
Uploaded Research Paper Comparison & Novelty Overlap Service for ResearchGraphAI.

Provides an evidence-grounded comparative analysis between an uploaded manuscript
and the project's literature corpus:
- Problem & methodology breakdown
- Gap alignment evaluation (addresses / partially addresses / does not address)
- Truthful semantic distance (explicitly labeled: distance from this corpus != absolute novelty)
- Missing comparison detection & uncited candidate literature
- Concrete suggested improvements and next experiments
Persisted in paper_analyses.
"""

from itertools import combinations
import math
import random
import re
from typing import Any
import numpy as np
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.services.embeddings import EmbeddingService, cosine_similarity, get_paper_embeddings
from app.services.llm import LLMService
from app.services.pdf_processing import PDFExtractionResult


NOVELTY_FORMULA = (
    "top_k_distance = 1 - mean(cos_sim(u, NN_k(u))); "
    "density_percentile = 100 * mean(I(mean_sim(NN_k(u)) >= mean_sim(NN_k(p_i))))"
)


def _extract_ref_tokens_from_text(text: str, max_refs: int = 25) -> list[str]:
    """Extract normalized venue/year/title tokens from a PDF's trailing references section."""
    if not text:
        return []
    m = re.search(r"\breferences\b|\bbibliography\b", text, flags=re.IGNORECASE)
    tail = text[m.start() :] if m else text[-3000:]
    lines = [ln.strip() for ln in tail.splitlines() if len(ln.strip()) > 20]
    tokens: list[str] = []
    for ln in lines[:max_refs]:
        clean = re.sub(r"^\[\d+\]\s*|\^\d+\.\s*", "", ln)
        words = [w for w in re.findall(r"[a-z0-9]{4,}", clean.lower()) if w not in {"http", "https", "doi", "arxiv", "proc", "conf", "journal", "pages"}]
        if words:
            tokens.append(" ".join(words[:3]))
    return list(dict.fromkeys(tokens))


def compute_reference_atypicality(
    uploaded_refs: list[str],
    corpus_ref_sets: list[list[str]],
    n_shuffles: int = 50,
    seed: int = 42,
) -> dict[str, Any]:
    """
    Compute Uzzi-style pairwise reference co-occurrence atypicality z-score against
    random corpus reference shuffles. Returns available=False when references are too sparse.
    """
    u_refs = list(dict.fromkeys([r.strip().lower() for r in uploaded_refs if r and r.strip()]))
    valid_corpus = [list(dict.fromkeys([r.strip().lower() for r in refs if r and r.strip()])) for refs in corpus_ref_sets if len(refs) >= 2]
    if len(u_refs) < 2 or len(valid_corpus) < 3:
        return {
            "available": False,
            "z_score": None,
            "median_z": None,
            "observed_mean_cooc": None,
            "reason": "Insufficient parsed reference lists (requires >=2 uploaded refs and >=3 corpus papers with >=2 refs).",
        }

    pair_counts: dict[tuple[str, str], int] = {}
    pool: list[str] = []
    for refs in valid_corpus:
        pool.extend(refs)
        for a, b in combinations(sorted(refs), 2):
            pair_counts[(a, b)] = pair_counts.get((a, b), 0) + 1

    u_pairs = [tuple(sorted((a, b))) for a, b in combinations(u_refs[:15], 2)]
    obs_vals = [float(pair_counts.get(p, 0)) for p in u_pairs]
    obs_mean = sum(obs_vals) / float(len(obs_vals))

    rng = random.Random(seed)
    null_means: list[float] = []
    sample_n = min(len(u_refs), 15, len(set(pool)))
    unique_pool = sorted(set(pool))
    if sample_n < 2:
        return {
            "available": False,
            "z_score": None,
            "median_z": None,
            "observed_mean_cooc": round(obs_mean, 4),
            "reason": "Reference pool too small for permutation null.",
        }

    for _ in range(n_shuffles):
        drawn = rng.sample(unique_pool, sample_n)
        d_pairs = [tuple(sorted((a, b))) for a, b in combinations(drawn, 2)]
        d_vals = [float(pair_counts.get(p, 0)) for p in d_pairs]
        null_means.append(sum(d_vals) / float(len(d_vals)))

    null_mu = sum(null_means) / float(len(null_means))
    null_var = sum((x - null_mu) ** 2 for x in null_means) / float(len(null_means))
    null_sd = math.sqrt(null_var)
    z = (obs_mean - null_mu) / null_sd if null_sd > 1e-9 else 0.0

    return {
        "available": True,
        "z_score": round(z, 3),
        "observed_mean_cooc": round(obs_mean, 4),
        "null_mean_cooc": round(null_mu, 4),
        "null_sd": round(null_sd, 4),
        "n_shuffles": n_shuffles,
        "reason": None,
    }


def compute_corpus_novelty_metrics(
    uploaded_vector: list[float],
    corpus_vectors: dict[int, list[float]],
    corpus_papers: list[Any],
    uploaded_refs: list[str] | None = None,
    corpus_ref_sets: list[list[str]] | None = None,
    k: int = 5,
    rng_seed: int = 42,
) -> dict[str, Any]:
    """
    Compute multi-dimensional relative novelty metrics against the indexed project corpus:
    (a) Top-k nearest-neighbor cosine similarity + neighbor list
    (b) Local density percentile compared with corpus leave-one-out k-NN similarities
    (c) Reference-combination atypicality z-score when reference metadata is available
    """
    valid_pids = [p.id for p in corpus_papers if p.id in corpus_vectors]
    paper_by_id = {p.id: p for p in corpus_papers}

    if not valid_pids:
        return {
            "relative_to_corpus_only": True,
            "method_names": ["top_k_nearest_neighbors", "local_density_percentile", "reference_combination_atypicality_zscore"],
            "formula": NOVELTY_FORMULA,
            "k": 0,
            "top_k_mean_similarity": 0.0,
            "max_similarity": 0.0,
            "semantic_distance": 1.0,
            "local_density_percentile": 0.0,
            "novelty_distance_percentile": 100.0,
            "top_k_neighbors": [],
            "papers_compared": 0,
            "reference_atypicality": compute_reference_atypicality(uploaded_refs or [], corpus_ref_sets or [], seed=rng_seed),
        }

    eff_k = min(k, len(valid_pids))
    u_vec = np.asarray(uploaded_vector, dtype=float)
    u_norm = np.linalg.norm(u_vec)
    if u_norm > 0:
        u_vec = u_vec / u_norm

    mat = np.asarray([corpus_vectors[pid] for pid in valid_pids], dtype=float)
    m_norms = np.linalg.norm(mat, axis=1, keepdims=True)
    m_norms[m_norms == 0] = 1.0
    mat = mat / m_norms

    u_sims = mat @ u_vec
    order = np.argsort(u_sims)[::-1]
    neighbors = []
    for idx in order[:eff_k]:
        pid = valid_pids[int(idx)]
        p = paper_by_id[pid]
        neighbors.append({
            "paper_id": pid,
            "title": p.title,
            "year": p.year,
            "similarity": round(float(u_sims[int(idx)]), 4),
        })

    top_k_mean = float(np.mean([n["similarity"] for n in neighbors]))
    max_sim = float(neighbors[0]["similarity"]) if neighbors else 0.0
    sem_distance = round(max(0.0, min(1.0, 1.0 - top_k_mean)), 4)

    # Local density distribution across corpus papers (leave-one-out top-k)
    if len(valid_pids) >= 2:
        pair_sim = mat @ mat.T
        loo_k = min(k, len(valid_pids) - 1)
        corpus_knn_means = []
        for i in range(len(valid_pids)):
            row_vals = np.delete(pair_sim[i], i)
            top_vals = np.sort(row_vals)[::-1][:loo_k]
            corpus_knn_means.append(float(np.mean(top_vals)))
        density_pct = round(
            100.0 * sum(1 for d in corpus_knn_means if top_k_mean >= d) / float(len(corpus_knn_means)),
            1,
        )
    else:
        density_pct = 50.0

    ref_atyp = compute_reference_atypicality(uploaded_refs or [], corpus_ref_sets or [], seed=rng_seed)

    return {
        "relative_to_corpus_only": True,
        "method_names": ["top_k_nearest_neighbors", "local_density_percentile", "reference_combination_atypicality_zscore"],
        "formula": NOVELTY_FORMULA,
        "k": eff_k,
        "top_k_mean_similarity": round(top_k_mean, 4),
        "max_similarity": round(max_sim, 4),
        "semantic_distance": sem_distance,
        "local_density_percentile": density_pct,
        "novelty_distance_percentile": round(100.0 - density_pct, 1),
        "top_k_neighbors": neighbors,
        "papers_compared": len(valid_pids),
        "reference_atypicality": ref_atyp,
    }


class ComparisonReportSchema(BaseModel):
    overview: str = Field(description="Summary of the uploaded paper's core premise")
    problem: str = Field(description="The specific scientific or engineering problem addressed")
    claimed_contributions: list[str] = Field(description="Key contributions claimed by authors")
    methodology: str = Field(description="Technical methods and experimental design employed")
    datasets_and_benchmarks: str = Field(description="Datasets or benchmarks evaluated")
    findings: str = Field(description="Key empirical results reported")
    limitations: str = Field(description="Limitations noted or observed in the study")
    gap_alignment: dict[str, Any] = Field(
        description="status (addresses | partially_addresses | does_not_address | cannot_assess) and explanation"
    )
    semantic_distance_label: str = Field(
        description="Explanation that semantic distance is measured relative to this corpus, not absolute scientific novelty"
    )
    novelty_overlap_analysis: str = Field(
        description="Qualitative overlap with existing methods and papers in the corpus"
    )
    candidate_uncited_comparisons: list[str] = Field(
        description="Papers in the corpus that address similar tasks but were not cited"
    )
    suggested_improvements: list[str] = Field(
        description="Actionable next experiments, baselines, or evaluations suggested"
    )


class CompareService:
    def __init__(self):
        self.embeddings = EmbeddingService()
        self.llm = LLMService()

    def compare_uploaded_paper(
        self,
        db: Session,
        project_id: int,
        extracted: PDFExtractionResult,
        document_id: int | None = None,
    ) -> models.PaperAnalysis:
        project = db.query(models.ResearchProject).filter(models.ResearchProject.id == project_id).first()
        if not project:
            raise RuntimeError(f"Project {project_id} not found")

        # Fetch corpus papers
        project_papers = (
            db.query(models.ProjectPaper)
            .filter(models.ProjectPaper.project_id == project_id)
            .all()
        )
        paper_ids = [p.paper_id for p in project_papers]
        corpus_papers = db.query(models.Paper).filter(models.Paper.id.in_(paper_ids)).all()

        # Compute batched corpus embeddings + multi-metric novelty assessment
        uploaded_text = f"{extracted.title or ''}. {extracted.abstract or ''}".strip()
        uploaded_vector = self.embeddings.embed(uploaded_text)

        corpus_vectors = get_paper_embeddings(db, paper_ids)
        corpus_refs_rows = (
            db.query(models.PaperReference.citing_paper_id, models.PaperReference.raw_reference)
            .filter(models.PaperReference.citing_paper_id.in_(paper_ids))
            .all()
        )
        refs_by_pid: dict[int, list[str]] = {}
        for cpid, raw_ref in corpus_refs_rows:
            tok = " ".join(re.findall(r"[a-z0-9]{4,}", str(raw_ref).lower())[:3])
            if tok:
                refs_by_pid.setdefault(cpid, []).append(tok)

        full_text_blob = "\n".join(c.text for c in extracted.chunks) if extracted.chunks else ""
        uploaded_refs = _extract_ref_tokens_from_text(full_text_blob)

        novelty_metrics = compute_corpus_novelty_metrics(
            uploaded_vector=uploaded_vector,
            corpus_vectors=corpus_vectors,
            corpus_papers=corpus_papers,
            uploaded_refs=uploaded_refs,
            corpus_ref_sets=list(refs_by_pid.values()),
            k=5,
        )

        semantic_distance = novelty_metrics["semantic_distance"]
        neighbor_by_id = {n["paper_id"]: n["similarity"] for n in novelty_metrics["top_k_neighbors"]}
        paper_by_id = {p.id: p for p in corpus_papers}
        ordered_papers = [paper_by_id[n["paper_id"]] for n in novelty_metrics["top_k_neighbors"] if n["paper_id"] in paper_by_id]
        for p in corpus_papers:
            if p.id not in neighbor_by_id:
                ordered_papers.append(p)

        corpus_summaries = [
            f"- '{p.title}' ({p.year or 'n.d.'}, sim: {round(neighbor_by_id.get(p.id, 0.0), 3)}): {(p.abstract or '')[:180]}"
            for p in ordered_papers[:12]
        ]

        # Build prompt for LLM comparison
        context = (
            f"Uploaded Paper Title: {extracted.title}\n"
            f"Abstract: {extracted.abstract or 'No abstract'}\n"
            f"Extracted Excerpts: {' '.join(c.text for c in extracted.chunks[:3])[:1200]}\n\n"
            f"Corpus Literature in Project '{project.topic}':\n"
            + "\n".join(corpus_summaries)
        )

        prompt = (
            "Analyze the uploaded research paper and compare it directly against the provided corpus literature. "
            "Synthesize a thorough, evidence-grounded comparative report adhering strictly to the JSON schema. "
            "In 'semantic_distance_label', clearly state: "
            f"'Top-{novelty_metrics['k']} nearest-neighbor distance ({semantic_distance}), local density percentile "
            f"({novelty_metrics['local_density_percentile']}%), reflects divergence relative to this project corpus ONLY "
            f"({novelty_metrics['papers_compared']} papers), not absolute novelty across all science.' "
            "Identify candidate papers in the corpus that are relevant to this work and examine whether they were cited or omitted."
        )

        system_prompt = (
            "You are a rigorous academic peer reviewer conducting a comparative literature analysis. "
            "Provide balanced, honest evaluations. Do not fabricate metrics."
        )

        try:
            report_data = self.llm.generate_structured(
                schema=ComparisonReportSchema,
                prompt=prompt,
                system_prompt=system_prompt,
                context=context,
            )
            report_dict = report_data.model_dump()
        except Exception as e:
            report_dict = {
                "overview": f"Comparative analysis generated with limited synthesis: {e}",
                "problem": "Unspecified",
                "claimed_contributions": [],
                "methodology": "Extracted from manuscript",
                "datasets_and_benchmarks": "N/A",
                "findings": "See uploaded PDF",
                "limitations": "N/A",
                "gap_alignment": {"status": "cannot_assess", "explanation": "LLM provider unavailable."},
                "semantic_distance_label": f"Semantic distance from this corpus: {semantic_distance} (relative measure).",
                "novelty_overlap_analysis": "Unable to compute deep qualitative overlap.",
                "candidate_uncited_comparisons": [],
                "suggested_improvements": [],
            }

        analysis_row = models.PaperAnalysis(
            project_id=project_id,
            uploaded_document_id=document_id,
            paper_title=extracted.title or "Uploaded Manuscript",
            report=report_dict,
            evidence_rows=[novelty_metrics],
            corpus_version=project.corpus_version,
        )
        db.add(analysis_row)
        db.commit()
        return analysis_row
