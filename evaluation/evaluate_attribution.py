"""
T13 Benchmark: Citation Attribution & Off-Topic Refusal Evaluation.

Evaluates:
- 30 in-domain questions (6 per topic across 5 topics in evaluation/topics.json)
  against real OpenAlex abstracts/chunks retrieved via our hybrid dense+FTS pipeline.
  Measures:
    1. quote_verification_precision (strict exact + >=0.9 LCS against cited passage)
    2. fraction_with_at_least_one_verified_quote
- 10 out-of-domain / unanswerable questions tested against the threshold guard
  (`min_dense_similarity >= 0.22`), measuring honest refusal rate.

Usage:
  cd backend && python ../evaluation/evaluate_attribution.py
"""

import json
import math
from pathlib import Path
import re
import sys
import time
from typing import Any

from dotenv import load_dotenv
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

from app.clients import OpenAlexClient
from app.services.chat import fuse_retrieval_hits
from app.services.embeddings import EmbeddingService
from app.services.llm import LLMService, post_validate_citation


OFF_TOPIC_QUESTIONS = [
    "What tax reforms were enacted during the reign of Emperor Diocletian in Rome?",
    "Compare oil painting brushwork techniques between Caravaggio and Rembrandt.",
    "How do sourdough lactic acid bacteria metabolize maltose during cold fermentation?",
    "What rules govern offside trap formation in modern 4-3-3 football tactics?",
    "Describe violin varnish formulations used in 18th century Cremona luthiery.",
    "Explain the financial derivatives pricing rules under Basel III liquidity ratios.",
    "What causes monsoon onset delays over the Bay of Bengal in May?",
    "How does limestone karst cave stalactite formation respond to dripwater pH?",
    "Compare medieval Japanese katana differential clay tempering temperatures.",
    "What zoning laws regulate coastal high-rise setbacks in Miami Beach?",
]


def wilson_score_interval(successes: int, total: int, z: float = 1.96) -> list[float]:
    """Compute exact Wilson score 95% confidence interval for a proportion."""
    if total <= 0:
        return [0.0, 0.0]
    p_hat = successes / float(total)
    denom = 1.0 + (z**2) / total
    center = (p_hat + (z**2) / (2 * total)) / denom
    margin = (z / denom) * math.sqrt((p_hat * (1.0 - p_hat) / total) + (z**2) / (4.0 * total**2))
    return [round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)]


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", (text or "").lower()))


def hybrid_retrieve_in_memory(
    passages: list[dict[str, Any]],
    passage_vecs: np.ndarray,
    embedder: EmbeddingService,
    query: str,
    min_dense_sim: float = 0.22,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    q_vec = np.asarray(embedder.embed(query), dtype=np.float32)
    q_norm = np.linalg.norm(q_vec)
    if q_norm > 0:
        q_vec = q_vec / q_norm

    sims = passage_vecs @ q_vec
    dense_hits = []
    for idx in np.argsort(sims)[::-1][:15]:
        sc = float(sims[int(idx)])
        if sc >= min_dense_sim:
            p = dict(passages[int(idx)])
            p["dense_score"] = sc
            p["score"] = sc
            dense_hits.append(p)

    q_toks = tokenize(query)
    fts_hits = []
    for p in passages:
        overlap = len(q_toks & tokenize(p["text"]))
        if overlap > 0:
            item = dict(p)
            sc = overlap / float(max(1, len(q_toks)))
            item["fts_score"] = sc
            item["score"] = sc
            fts_hits.append(item)
    fts_hits.sort(key=lambda x: x["score"], reverse=True)

    if not dense_hits:
        # Must pass semantic relevance guard so out-of-domain stopwords cannot leak through
        return []

    fused = fuse_retrieval_hits(dense_hits, fts_hits[:15], fusion_method="rrf")
    return fused[:top_k]


def extract_cited_quotes(answer_text: str) -> list[str]:
    norm = (answer_text or "").replace("\u201c", '"').replace("\u201d", '"')
    quotes = re.findall(r'"([^"]{12,450})"', norm)
    return [q.strip() for q in quotes if q.strip()]


def run_attribution_eval() -> dict[str, Any]:
    t0 = time.time()
    topics_path = PROJECT_ROOT / "evaluation" / "topics.json"
    with open(topics_path, "r", encoding="utf-8") as f:
        topics = json.load(f)

    oa = OpenAlexClient()
    embedder = EmbeddingService()
    llm = LLMService()

    passages: list[dict[str, Any]] = []
    domain_questions: list[dict[str, str]] = []

    cid = 1
    for t in topics:
        topic_str = t["topic"]
        hits = [p for p in oa.search(topic_str, limit=10) if p.abstract and len(p.abstract) > 120][:4]
        for p in hits:
            passages.append({
                "chunk_id": cid,
                "title": p.title,
                "year": p.year,
                "topic": topic_str,
                "text": p.abstract,
            })
            cid += 1

        # 6 specific domain questions per topic (30 total)
        templates = [
            f"What main methodology or mechanism is studied for {topic_str}?",
            f"What experimental metrics or quantitative findings are reported in {topic_str}?",
            f"What limitations or challenges are identified in {topic_str}?",
            f"How do recent studies evaluate {topic_str}?",
            f"What factors drive performance or stability in {topic_str}?",
            f"What key datasets, models, or conditions are investigated in {topic_str}?",
        ]
        for q in templates:
            domain_questions.append({"topic": topic_str, "question": q})

    vecs = np.asarray(embedder.embed_batch([p["text"] for p in passages]), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs = vecs / norms

    total_quotes_extracted = 0
    verified_quotes = 0
    answers_with_verified = 0
    per_question_log = []

    for q_item in domain_questions:
        hits = hybrid_retrieve_in_memory(passages, vecs, embedder, q_item["question"], min_dense_sim=0.22, top_k=3)
        if not hits:
            per_question_log.append({"question": q_item["question"], "retrieved": 0, "quotes": 0, "verified": 0})
            continue

        ctx = "\n\n".join(f"[{i}] {h['title']}: {h['text'][:550]}" for i, h in enumerate(hits, start=1))
        prompt = (
            f"Question: {q_item['question']}\n\n"
            "Write a short ### Evidence section answering from the excerpts above. "
            "You MUST copy 1 or 2 exact verbatim sentences or clauses from the excerpts inside double quotes (\"...\") followed by [1] or [2]."
        )
        time.sleep(1.5)
        try:
            ans = llm.complete(prompt, system_prompt="Always cite exact verbatim substrings from the excerpts inside double quotes.", context=ctx)
        except Exception:
            time.sleep(5.0)
            ans = llm.complete(prompt, system_prompt="Always cite exact verbatim substrings from the excerpts inside double quotes.", context=ctx)
        quotes = extract_cited_quotes(ans)
        v_cnt = 0
        for q in quotes:
            if any(post_validate_citation(q, h["text"], chunk_id=h["chunk_id"])["verified"] for h in hits):
                v_cnt += 1

        total_quotes_extracted += len(quotes)
        verified_quotes += v_cnt
        if v_cnt >= 1:
            answers_with_verified += 1
        per_question_log.append({
            "question": q_item["question"],
            "retrieved": len(hits),
            "quotes": len(quotes),
            "verified": v_cnt,
        })

    # 10 off-topic refusal checks
    off_topic_refused = 0
    for oq in OFF_TOPIC_QUESTIONS:
        hits = hybrid_retrieve_in_memory(passages, vecs, embedder, oq, min_dense_sim=0.22, top_k=4)
        if not hits:
            off_topic_refused += 1

    precision = round(verified_quotes / total_quotes_extracted, 4) if total_quotes_extracted else 0.0
    answer_cov = round(answers_with_verified / len(domain_questions), 4) if domain_questions else 0.0
    refusal_rate = round(off_topic_refused / len(OFF_TOPIC_QUESTIONS), 4)

    report = {
        "corpus_passages": len(passages),
        "domain_questions": len(domain_questions),
        "total_quotes_extracted": total_quotes_extracted,
        "verified_quotes": verified_quotes,
        "quote_verification_precision": precision,
        "quote_verification_precision_ci_95": wilson_score_interval(verified_quotes, total_quotes_extracted),
        "answers_with_at_least_one_verified_quote_rate": answer_cov,
        "answers_with_verified_quote_ci_95": wilson_score_interval(answers_with_verified, len(domain_questions)),
        "off_topic_questions": len(OFF_TOPIC_QUESTIONS),
        "off_topic_refusal_rate": refusal_rate,
        "off_topic_refusal_ci_95": wilson_score_interval(off_topic_refused, len(OFF_TOPIC_QUESTIONS)),
        "elapsed_seconds": round(time.time() - t0, 2),
        "samples": per_question_log[:10],
    }

    out_path = PROJECT_ROOT / "evaluation" / "attribution_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("Attribution Results:", json.dumps({k: v for k, v in report.items() if k != "samples"}, indent=2))
    return report


if __name__ == "__main__":
    run_attribution_eval()
