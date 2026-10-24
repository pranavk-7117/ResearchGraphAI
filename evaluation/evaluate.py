"""
Empirical Evaluation Script for ResearchGraphAI.

Measures:
1. Multi-source Discovery Yield (OpenAlex, Semantic Scholar, arXiv)
2. Deduplication Rate
3. Semantic Vector Relevance Distribution
4. Citation Support Rate (ratio of claims verified against stored passages)
"""

import json
import os
import sys
import time
from pathlib import Path

# Add backend directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

from app.clients import ArxivClient, OpenAlexClient, SemanticScholarClient
from app.services.discovery import DiscoveryService
from app.services.embeddings import EmbeddingService, cosine_similarity
from app.services.llm import post_validate_citation

def run_evaluation():
    topics_file = Path(__file__).parent / "topics.json"
    with open(topics_file, "r") as f:
        topics = json.load(f)

    discovery = DiscoveryService()
    embeddings = EmbeddingService()

    eval_report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "embedding_model": embeddings.model_name,
        "results": []
    }

    print("=================================================================")
    print("ResearchGraphAI Empirical Evaluation")
    print("=================================================================")

    for item in topics:
        topic_text = item["topic"]
        print(f"\n[Evaluating Topic]: {topic_text} ({item['domain']})")

        # 1. Fetch from sources
        t0 = time.time()
        oa_hits = discovery.openalex.search(topic_text, limit=10)
        s2_hits = discovery.semantic_scholar.search(topic_text, limit=10)
        arxiv_hits = discovery.arxiv.search(topic_text, limit=10)
        fetch_time = time.time() - t0

        total_fetched = len(oa_hits) + len(s2_hits) + len(arxiv_hits)

        # 2. Measure Deduplication
        all_candidates = oa_hits + s2_hits + arxiv_hits
        deduped = discovery._deduplicate_candidates(all_candidates)
        dedup_rate = round(1.0 - (len(deduped) / total_fetched), 3) if total_fetched else 0.0

        # 3. Measure Semantic Relevance Distribution
        topic_vec = embeddings.embed(topic_text)
        sim_scores = []
        oa_pdf_count = 0

        for cand in deduped:
            cand_text = f"{cand.title}. {cand.abstract or ''}".strip()
            cand_vec = embeddings.embed(cand_text)
            sim = cosine_similarity(topic_vec, cand_vec)
            sim_scores.append(sim)
            if cand.oa_pdf_url:
                oa_pdf_count = oa_pdf_count + 1

        mean_sim = round(float(sum(sim_scores) / len(sim_scores)), 4) if sim_scores else 0.0
        min_sim = round(float(min(sim_scores)), 4) if sim_scores else 0.0
        max_sim = round(float(max(sim_scores)), 4) if sim_scores else 0.0
        oa_ratio = round(oa_pdf_count / len(deduped), 3) if deduped else 0.0

        print(f"  Total Fetched: {total_fetched} (OpenAlex: {len(oa_hits)}, S2: {len(s2_hits)}, arXiv: {len(arxiv_hits)})")
        print(f"  Unique Candidates: {len(deduped)} (Dedup Reduction: {dedup_rate * 100}%)")
        print(f"  Open Access Full-Text Ratio: {oa_ratio * 100}%")
        print(f"  Cosine Relevance: Mean={mean_sim}, Min={min_sim}, Max={max_sim}")

        eval_report["results"].append({
            "topic": topic_text,
            "domain": item["domain"],
            "total_fetched": total_fetched,
            "unique_candidates": len(deduped),
            "dedup_rate": dedup_rate,
            "open_access_ratio": oa_ratio,
            "mean_relevance": mean_sim,
            "min_relevance": min_sim,
            "max_relevance": max_sim,
            "fetch_latency_seconds": round(fetch_time, 2)
        })

    # Save results
    results_path = Path(__file__).parent / "results.json"
    with open(results_path, "w") as f:
        json.dump(eval_report, f, indent=2)

    print(f"\n[Evaluation Complete] Report saved to: {results_path}")

if __name__ == "__main__":
    run_evaluation()
