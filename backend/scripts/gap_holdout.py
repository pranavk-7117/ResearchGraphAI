"""
T12b Temporal Holdout Validation for the Bipartite Method x Task Gap Matrix.

Protocol:
- Cutoff T = current_year - 3 (H = 3-year post-T validation window: T+1 .. current_year).
- Builds a pre-T (year <= T) corpus per topic from OpenAlex.
- Extracts normalized (method, task_or_dataset) pairs from pre-T paper titles/abstracts
  via LLM structured output (when configured) and constructs the T12 bipartite matrix.
- Compares top-K predicted empty/sparse matrix cells (ranked by T12 lowest hypergeom p-value)
  against K randomly sampled empty cells from the same matrix on post-T (year >= T+1) OpenAlex hits
  verified by semantic similarity >= 0.45.

Usage:
  cd backend && python scripts/gap_holdout.py [--k 3] [--limit 25]
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
from types import SimpleNamespace
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

from app.clients import OpenAlexClient
from app.services.embeddings import EmbeddingService, cosine_similarity
from app.services.gap_matrix import build_method_task_matrix
from app.services.llm import LLMService


class PaperPairExtraction(BaseModel):
    paper_index: int
    method: str = ""
    task_or_dataset: str = ""


class TopicPairBatch(BaseModel):
    items: list[PaperPairExtraction] = Field(default_factory=list)


def extract_pairs_pre_t(papers: list[Any], llm: LLMService) -> list[tuple[int, str, Any]]:
    """Extract (method, task_or_dataset) facts for pre-T abstracts in small batches."""
    if not papers or not llm.is_available():
        return []

    fact_rows: list[tuple[int, str, Any]] = []
    batch_size = 6
    for offset in range(0, len(papers), batch_size):
        chunk = papers[offset : offset + batch_size]
        context_lines = []
        for local_idx, p in enumerate(chunk, start=offset + 1):
            abs_snip = (p.abstract or "")[:300].replace("\n", " ")
            context_lines.append(f"[{local_idx}] {p.title} ({p.year})\nAbstract: {abs_snip}")

        prompt = (
            "For each numbered paper, output paper_index, method (1-4 word technical method/model name), "
            "and task_or_dataset (1-4 word evaluation task or benchmark/domain). Keep concise canonical terms."
        )
        try:
            batch = llm.generate_structured(
                schema=TopicPairBatch,
                prompt=prompt,
                system_prompt="Return strict JSON matching TopicPairBatch with no extra text.",
                context="\n\n".join(context_lines),
            )
        except Exception as exc:
            print(f"  [warn] batch extraction failed at offset {offset}: {exc}")
            continue

        by_idx = {item.paper_index: item for item in batch.items}
        for local_idx, p in enumerate(chunk, start=offset + 1):
            ext = by_idx.get(local_idx)
            if not ext or not ext.method.strip() or not ext.task_or_dataset.strip():
                continue
            fact_rows.append((
                local_idx,
                p.title,
                SimpleNamespace(
                    method={"value": ext.method.strip()},
                    algorithm_or_model=None,
                    dataset={"value": ext.task_or_dataset.strip()},
                    problem=None,
                ),
            ))
    return fact_rows


def validate_cell_post_t(
    cell: dict[str, Any],
    topic: str,
    cutoff_t: int,
    openalex: OpenAlexClient,
    embeddings: EmbeddingService,
    sim_threshold: float = 0.45,
) -> dict[str, Any]:
    """Check whether post-T (> cutoff_t) literature addresses (method, task) via OpenAlex + embedding sim."""
    method = cell["method"]
    task = cell["task"]
    query = f'"{method}" "{task}"'
    hits = openalex.search(query, limit=8, year_min=cutoff_t + 1)

    target_vec = embeddings.embed(f"{topic}: {method} applied to {task}")
    matched_hits = []
    for h in hits:
        text = f"{h.title}. {h.abstract or ''}".strip()
        sim = cosine_similarity(target_vec, embeddings.embed(text))
        if sim >= sim_threshold:
            matched_hits.append({"title": h.title, "year": h.year, "sim": round(sim, 3)})

    return {
        "method": method,
        "task": task,
        "count_pre_t": cell["count"],
        "hypergeom_p": cell["hypergeom_p"],
        "post_t_raw_hits": len(hits),
        "post_t_verified_hits": len(matched_hits),
        "addressed_post_t": len(matched_hits) > 0,
        "top_matches": matched_hits[:2],
    }


def run_holdout(k: int = 3, limit: int = 25, seed: int = 42) -> dict[str, Any]:
    topics_path = PROJECT_ROOT / "evaluation" / "topics.json"
    with open(topics_path, "r", encoding="utf-8") as f:
        topics = json.load(f)

    current_year = datetime.now(timezone.utc).year
    cutoff_t = min(current_year - 3, 2023)

    openalex = OpenAlexClient()
    llm = LLMService()
    embeddings = EmbeddingService()
    rng = random.Random(seed)

    per_topic: list[dict[str, Any]] = []
    total_gap_pred = 0
    total_gap_hits = 0
    total_rand_pred = 0
    total_rand_hits = 0

    for t in topics:
        topic_str = t["topic"]
        print(f"\n[T12b Holdout] Topic: {topic_str} (cutoff <= {cutoff_t}, post >= {cutoff_t + 1})")
        pre_papers = openalex.search(topic_str, limit=limit, year_max=cutoff_t)
        pre_papers = [p for p in pre_papers if p.abstract]
        fact_rows = extract_pairs_pre_t(pre_papers[:18], llm)
        matrix = build_method_task_matrix(fact_rows, min_support=1 if len(fact_rows) < 12 else 2)

        all_empty = [c for c in matrix["cells"] if c["count"] == 0]
        ranked_voids = matrix["candidates"] or sorted(all_empty, key=lambda c: (c["hypergeom_p"], -c["expected"]))
        top_preds = ranked_voids[:k]

        top_keys = {(c["method"], c["task"]) for c in top_preds}
        remaining_empty = [c for c in all_empty if (c["method"], c["task"]) not in top_keys]
        if len(remaining_empty) < len(top_preds):
            remaining_empty = all_empty
        rand_preds = rng.sample(remaining_empty, min(len(top_preds), len(remaining_empty))) if remaining_empty else []

        pred_evals = [validate_cell_post_t(c, topic_str, cutoff_t, openalex, embeddings) for c in top_preds]
        rand_evals = [validate_cell_post_t(c, topic_str, cutoff_t, openalex, embeddings) for c in rand_preds]

        gap_hits = sum(1 for e in pred_evals if e["addressed_post_t"])
        rand_hits = sum(1 for e in rand_evals if e["addressed_post_t"])
        total_gap_pred += len(pred_evals)
        total_gap_hits += gap_hits
        total_rand_pred += len(rand_evals)
        total_rand_hits += rand_hits

        p_at_k = round(gap_hits / len(pred_evals), 3) if pred_evals else 0.0
        rand_at_k = round(rand_hits / len(rand_evals), 3) if rand_evals else 0.0
        print(f"  Pre-T papers={len(pre_papers)}, pairs={len(fact_rows)}, P@{k}={p_at_k} ({gap_hits}/{len(pred_evals)}), Random={rand_at_k} ({rand_hits}/{len(rand_evals)})")

        per_topic.append({
            "id": t["id"],
            "topic": topic_str,
            "domain": t["domain"],
            "pre_t_papers": len(pre_papers),
            "extracted_pairs": len(fact_rows),
            "matrix_methods": len(matrix["methods"]),
            "matrix_tasks": len(matrix["tasks"]),
            "predicted_precision_at_k": p_at_k,
            "random_precision_at_k": rand_at_k,
            "predicted_gaps": pred_evals,
            "random_baseline": rand_evals,
        })

    overall_gap_p = round(total_gap_hits / total_gap_pred, 3) if total_gap_pred else 0.0
    overall_rand_p = round(total_rand_hits / total_rand_pred, 3) if total_rand_pred else 0.0

    summary = {
        "cutoff_year_T": cutoff_t,
        "validation_window_H": 3,
        "k": k,
        "num_topics": len(per_topic),
        "overall_gap_precision_at_k": overall_gap_p,
        "overall_random_precision_at_k": overall_rand_p,
        "total_predicted_checked": total_gap_pred,
        "total_predicted_addressed_post_t": total_gap_hits,
        "total_random_checked": total_rand_pred,
        "total_random_addressed_post_t": total_rand_hits,
        "caveats": [
            "Small sample size (5 topics, pre-T abstract-only extraction capped at 18 papers per topic).",
            "Post-T confirmation checks OpenAlex title/abstract keyword co-occurrence + cosine >= 0.45 rather than human expert peer review.",
            "Empty cells can reflect negative/unpublished results or terminology drift across years rather than true scientific novelty.",
        ],
        "topics": per_topic,
    }

    out_json = PROJECT_ROOT / "evaluation" / "gap_holdout_results.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    md_lines = [
        "# T12b Temporal Holdout Gap Validation Summary",
        "",
        f"- **Cutoff Year (T)**: `{cutoff_t}` | **Validation Window**: `{cutoff_t + 1}`–`{current_year}` (`H = 3` years)",
        f"- **Overall Matrix Gap Precision@{k}**: **{overall_gap_p:.3f}** ({total_gap_hits}/{total_gap_pred}) vs **Random Empty Cell Baseline**: **{overall_rand_p:.3f}** ({total_rand_hits}/{total_rand_pred})",
        "",
        "| Topic | Domain | Pre-T Papers | Pairs Extracted | Matrix Void Precision@K | Random Baseline |",
        "|---|---|---|---|---|---|",
    ]
    for row in per_topic:
        md_lines.append(
            f"| {row['topic']} | {row['domain']} | {row['pre_t_papers']} | {row['extracted_pairs']} | "
            f"{row['predicted_precision_at_k']:.3f} | {row['random_precision_at_k']:.3f} |"
        )
    md_lines.extend([
        "",
        "## Honest Caveats",
        "- Small evaluation scale (5 benchmark topics; pre-T extraction from abstracts rather than full PDFs).",
        "- Post-T check measures OpenAlex keyword + embedding matches (`cosine >= 0.45`), which captures topical follow-up but does not guarantee methodological rigor.",
    ])
    out_md = PROJECT_ROOT / "evaluation" / "gap_holdout_summary.md"
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")

    print(f"\nSaved T12b results to {out_json} and {out_md}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    run_holdout(k=args.k, limit=args.limit)
