"""
Empirical Discovery Evaluation Script for ResearchGraphAI (T13 Non-Circular Version).

Replaces the prior circular bi-encoder cosine metric with an independent external
Cross-Encoder relevance judge (`cross-encoder/ms-marco-MiniLM-L-6-v2`) plus
OpenAlex/abstract topic keyword overlap, alongside multi-source yield and deduplication.

Usage:
  cd backend && python ../evaluation/evaluate.py
"""

import json
import math
from pathlib import Path
import re
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

from app.services.chat import get_cross_encoder
from app.services.discovery import DiscoveryService


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, x))))


def _topic_keyword_overlap(topic: str, text: str) -> float:
    t_tokens = {w for w in re.findall(r"[a-z0-9]{3,}", topic.lower())}
    d_tokens = {w for w in re.findall(r"[a-z0-9]{3,}", (text or "").lower())}
    if not t_tokens:
        return 0.0
    return len(t_tokens & d_tokens) / float(len(t_tokens))


def run_evaluation():
    topics_file = Path(__file__).parent / "topics.json"
    with open(topics_file, "r", encoding="utf-8") as f:
        topics = json.load(f)

    discovery = DiscoveryService()
    cross_encoder = get_cross_encoder()

    eval_report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_judge": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "circularity_note": "Replaced bi-encoder cosine similarity (which matched discovery ranking) with independent cross-encoder probability & keyword overlap.",
        "results": [],
    }

    print("=================================================================")
    print("ResearchGraphAI Discovery Evaluation (Non-Circular External Judge)")
    print("=================================================================")

    for item in topics:
        topic_text = item["topic"]
        print(f"\n[Evaluating Topic]: {topic_text} ({item['domain']})")

        t0 = time.time()
        oa_hits = discovery.openalex.search(topic_text, limit=10)
        s2_hits = discovery.semantic_scholar.search(topic_text, limit=10)
        arxiv_hits = discovery.arxiv.search(topic_text, limit=10)
        fetch_time = time.time() - t0

        total_fetched = len(oa_hits) + len(s2_hits) + len(arxiv_hits)
        all_candidates = oa_hits + s2_hits + arxiv_hits
        deduped = discovery._deduplicate_candidates(all_candidates)
        dedup_rate = round(1.0 - (len(deduped) / total_fetched), 3) if total_fetched else 0.0

        oa_pdf_count = sum(1 for c in deduped if c.oa_pdf_url)
        oa_ratio = round(oa_pdf_count / len(deduped), 3) if deduped else 0.0

        if deduped:
            pairs = [(topic_text, f"{c.title}. {c.abstract or ''}"[:800]) for c in deduped]
            ce_logits = cross_encoder.predict(pairs)
            ce_probs = [_sigmoid(float(s)) for s in ce_logits]
            kw_overlaps = [_topic_keyword_overlap(topic_text, f"{c.title} {c.abstract or ''}") for c in deduped]
            mean_ce = round(sum(ce_probs) / len(ce_probs), 4)
            min_ce = round(min(ce_probs), 4)
            max_ce = round(max(ce_probs), 4)
            mean_kw = round(sum(kw_overlaps) / len(kw_overlaps), 4)
        else:
            mean_ce = min_ce = max_ce = mean_kw = 0.0

        print(f"  Total Fetched: {total_fetched} | Unique: {len(deduped)} (Dedup: {dedup_rate * 100:.1f}%)")
        print(f"  External Cross-Encoder Prob: Mean={mean_ce}, Min={min_ce}, Max={max_ce} | Keyword Overlap: {mean_kw}")

        eval_report["results"].append({
            "topic": topic_text,
            "domain": item["domain"],
            "total_fetched": total_fetched,
            "unique_candidates": len(deduped),
            "dedup_rate": dedup_rate,
            "open_access_ratio": oa_ratio,
            "external_cross_encoder_mean": mean_ce,
            "external_cross_encoder_min": min_ce,
            "external_cross_encoder_max": max_ce,
            "topic_keyword_overlap_mean": mean_kw,
            "fetch_latency_seconds": round(fetch_time, 2),
        })

    # Merge any T13 retrieval/attribution/T12b summaries if present for unified results_v2.json
    unified = {"discovery": eval_report}
    for key, fname in [
        ("retrieval_scifact", "retrieval_results.json"),
        ("attribution", "attribution_results.json"),
        ("temporal_gap_holdout", "gap_holdout_results.json"),
    ]:
        fpath = Path(__file__).parent / fname
        if fpath.exists():
            with open(fpath, "r", encoding="utf-8") as fh:
                unified[key] = json.load(fh)

    results_path = Path(__file__).parent / "results_v2.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(unified, f, indent=2)

    print(f"\n[Evaluation Complete] Saved to: {results_path}")


if __name__ == "__main__":
    run_evaluation()
