"""
T13 Benchmark: Hybrid Retrieval Evaluation on BEIR SciFact (nDCG@10, Recall@10, MRR@10).

Evaluates 5 retrieval configurations across all 300 SciFact test queries:
1. dense_only (all-MiniLM-L6-v2 cosine similarity)
2. fts_only (BM25/FTS lexical scoring)
3. rrf (Reciprocal Rank Fusion k=60 via app.services.chat.fuse_retrieval_hits)
4. convex (Min-max normalized linear blend alpha=0.5 via fuse_retrieval_hits)
5. hybrid_cross_encoder (RRF top-20 reranked with cross-encoder/ms-marco-MiniLM-L-6-v2)

Usage:
  cd backend && python ../evaluation/evaluate_retrieval.py
"""

from collections import Counter, defaultdict
import csv
import io
import json
import math
from pathlib import Path
import re
import sys
import time
from typing import Any
import zipfile

import httpx
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.services.chat import fuse_retrieval_hits, get_cross_encoder
from app.services.embeddings import EmbeddingService

SCIFACT_URL = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip"
CACHE_DIR = PROJECT_ROOT / "evaluation" / ".cache" / "scifact"
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "he",
    "in", "is", "it", "its", "of", "on", "that", "the", "to", "was", "were", "will", "with",
}


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 1 and t not in STOPWORDS]


def ensure_scifact() -> Path:
    data_dir = CACHE_DIR / "scifact"
    if (data_dir / "corpus.jsonl").exists() and (data_dir / "qrels" / "test.tsv").exists():
        return data_dir

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = CACHE_DIR / "scifact.zip"
    if not zip_path.exists():
        print(f"Downloading BEIR SciFact dataset from {SCIFACT_URL}...")
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            resp = client.get(SCIFACT_URL)
            resp.raise_for_status()
            zip_path.write_bytes(resp.content)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(CACHE_DIR)
    return data_dir


def load_scifact(data_dir: Path) -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, int]]]:
    corpus: dict[str, str] = {}
    with open(data_dir / "corpus.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            corpus[row["_id"]] = f"{row.get('title', '')}. {row.get('text', '')}".strip()

    queries: dict[str, str] = {}
    with open(data_dir / "queries.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            queries[row["_id"]] = row["text"]

    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    with open(data_dir / "qrels" / "test.tsv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            score = int(row["score"])
            if score > 0:
                qrels[row["query-id"]][row["corpus-id"]] = score

    return corpus, queries, dict(qrels)


class LexicalBM25:
    def __init__(self, doc_ids: list[str], texts: list[str], k1: float = 1.2, b: float = 0.75):
        self.doc_ids = doc_ids
        self.k1 = k1
        self.b = b
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.doc_len: list[int] = []

        for idx, text in enumerate(texts):
            toks = tokenize(text)
            self.doc_len.append(len(toks))
            tf = Counter(toks)
            for term, freq in tf.items():
                self.postings[term].append((idx, freq))

        self.n_docs = len(doc_ids)
        self.avg_len = sum(self.doc_len) / float(self.n_docs) if self.n_docs else 1.0
        self.idf = {
            term: math.log((self.n_docs - len(plist) + 0.5) / (len(plist) + 0.5) + 1.0)
            for term, plist in self.postings.items()
        }

    def search(self, query: str, top_k: int = 30) -> list[tuple[int, float]]:
        scores: dict[int, float] = defaultdict(float)
        for term in set(tokenize(query)):
            if term not in self.postings:
                continue
            idf = self.idf[term]
            for idx, tf in self.postings[term]:
                dl = self.doc_len[idx]
                denom = tf + self.k1 * (1.0 - self.b + self.b * (dl / self.avg_len))
                scores[idx] += idf * ((tf * (self.k1 + 1.0)) / denom)
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]


def compute_metrics(ranked_ids: list[str], rel_map: dict[str, int], k: int = 10) -> tuple[float, float, float]:
    if not rel_map:
        return 0.0, 0.0, 0.0
    top_k_ids = ranked_ids[:k]
    dcg = 0.0
    for rank_idx, doc_id in enumerate(top_k_ids):
        rel = rel_map.get(doc_id, 0)
        if rel > 0:
            dcg += (2**rel - 1) / math.log2(rank_idx + 2)
    ideal_rels = sorted(rel_map.values(), reverse=True)[:k]
    idcg = sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(ideal_rels))
    ndcg = (dcg / idcg) if idcg > 0 else 0.0

    hits = sum(1 for doc_id in top_k_ids if doc_id in rel_map)
    recall = hits / float(len(rel_map))

    mrr = 0.0
    for rank_idx, doc_id in enumerate(top_k_ids):
        if doc_id in rel_map:
            mrr = 1.0 / float(rank_idx + 1)
            break
    return ndcg, recall, mrr


def bootstrap_ci(values: list[float], n_boot: int = 1000, alpha: float = 0.05) -> list[float]:
    """Compute empirical bootstrap 95% confidence interval across query metrics."""
    if not values:
        return [0.0, 0.0]
    rng = np.random.default_rng(42)
    arr = np.array(values, dtype=np.float64)
    means = [float(np.mean(rng.choice(arr, size=len(arr), replace=True))) for _ in range(n_boot)]
    low = float(np.percentile(means, 100 * (alpha / 2)))
    high = float(np.percentile(means, 100 * (1 - alpha / 2)))
    return [round(low, 4), round(high, 4)]


def run_retrieval_eval(max_queries: int = 300) -> dict[str, Any]:
    t0 = time.time()
    data_dir = ensure_scifact()
    corpus, queries, qrels = load_scifact(data_dir)
    doc_ids = list(corpus.keys())
    texts = [corpus[did] for did in doc_ids]

    embedder = EmbeddingService()
    emb_cache = CACHE_DIR / "scifact_corpus_emb.npy"
    if emb_cache.exists():
        doc_matrix = np.load(emb_cache)
    else:
        print(f"Embedding {len(texts)} SciFact corpus documents...")
        vecs = embedder.embed_batch(texts)
        doc_matrix = np.asarray(vecs, dtype=np.float32)
        norms = np.linalg.norm(doc_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        doc_matrix = doc_matrix / norms
        np.save(emb_cache, doc_matrix)

    bm25 = LexicalBM25(doc_ids, texts)
    cross_encoder = get_cross_encoder()

    eval_qids = [qid for qid in qrels.keys() if qid in queries][:max_queries]
    q_texts = [queries[qid] for qid in eval_qids]
    q_vecs = np.asarray(embedder.embed_batch(q_texts), dtype=np.float32)
    q_norms = np.linalg.norm(q_vecs, axis=1, keepdims=True)
    q_norms[q_norms == 0] = 1.0
    q_vecs = q_vecs / q_norms

    strategies = ["dense_only", "fts_only", "rrf", "convex", "rrf_cross_encoder"]
    totals: dict[str, list[tuple[float, float, float]]] = {s: [] for s in strategies}

    per_query_cache = []
    all_ce_pairs = []
    ce_slices = []

    for qi, qid in enumerate(eval_qids):
        qtext = queries[qid]
        rel_map = qrels[qid]

        sims = doc_matrix @ q_vecs[qi]
        top_dense_idx = np.argsort(sims)[::-1][:30]
        dense_hits = [
            {"chunk_id": int(idx), "doc_id": doc_ids[int(idx)], "dense_score": float(sims[int(idx)]), "score": float(sims[int(idx)])}
            for idx in top_dense_idx
        ]
        bm25_top = bm25.search(qtext, top_k=30)
        fts_hits = [
            {"chunk_id": int(idx), "doc_id": doc_ids[int(idx)], "fts_score": float(sc), "score": float(sc)}
            for idx, sc in bm25_top
        ]

        rrf_fused = fuse_retrieval_hits(dense_hits, fts_hits, fusion_method="rrf")
        convex_fused = fuse_retrieval_hits(dense_hits, fts_hits, fusion_method="convex", alpha=0.5)

        ce_pool = rrf_fused[:10]
        start_idx = len(all_ce_pairs)
        for item in ce_pool:
            all_ce_pairs.append((qtext, texts[item["chunk_id"]][:450]))
        ce_slices.append((start_idx, len(all_ce_pairs), ce_pool))

        per_query_cache.append((rel_map, dense_hits, fts_hits, rrf_fused, convex_fused))

    ce_all_scores = cross_encoder.predict(all_ce_pairs, batch_size=64) if all_ce_pairs else []

    for qi, (rel_map, dense_hits, fts_hits, rrf_fused, convex_fused) in enumerate(per_query_cache):
        s_idx, e_idx, ce_pool = ce_slices[qi]
        if ce_pool:
            q_ce_scores = ce_all_scores[s_idx:e_idx]
            ce_ranked = sorted(zip(ce_pool, q_ce_scores), key=lambda x: float(x[1]), reverse=True)
            ce_ids = [item["doc_id"] for item, _ in ce_ranked]
        else:
            ce_ids = []

        rankings = {
            "dense_only": [h["doc_id"] for h in dense_hits],
            "fts_only": [h["doc_id"] for h in fts_hits],
            "rrf": [h["doc_id"] for h in rrf_fused],
            "convex": [h["doc_id"] for h in convex_fused],
            "rrf_cross_encoder": ce_ids,
        }
        for name, doc_list in rankings.items():
            totals[name].append(compute_metrics(doc_list, rel_map, k=10))

    summary_rows = {}
    for name in strategies:
        vals = totals[name]
        n = len(vals)
        summary_rows[name] = {
            "ndcg_at_10": round(sum(v[0] for v in vals) / n, 4),
            "ndcg_ci_95": bootstrap_ci([v[0] for v in vals]),
            "recall_at_10": round(sum(v[1] for v in vals) / n, 4),
            "mrr_at_10": round(sum(v[2] for v in vals) / n, 4),
        }

    winner = max(summary_rows.items(), key=lambda item: item[1]["ndcg_at_10"])[0]
    report = {
        "dataset": "BEIR SciFact (test split)",
        "num_corpus_docs": len(doc_ids),
        "num_queries": len(eval_qids),
        "embedding_model": embedder.model_name,
        "cross_encoder_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "metrics": summary_rows,
        "winner_by_ndcg10": winner,
        "elapsed_seconds": round(time.time() - t0, 2),
    }

    out_path = PROJECT_ROOT / "evaluation" / "retrieval_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("SciFact Retrieval Results:", json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run_retrieval_eval()
