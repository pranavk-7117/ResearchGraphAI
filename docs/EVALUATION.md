# ResearchGraphAI Empirical Evaluation Report

All metrics below were measured directly by the scripts in [`evaluation/`](../evaluation/) and [`backend/scripts/gap_holdout.py`](../backend/scripts/gap_holdout.py) against live datasets and models. No synthetic or mocked results appear in this report.

## 1. Reproduction Commands

```powershell
# 1. Hybrid Retrieval Benchmark on BEIR SciFact (300 test queries, 5,183 corpus abstracts)
cd backend; python ../evaluation/evaluate_retrieval.py

# 2. RAG Quote Attribution & Off-Topic Refusal Benchmark (30 domain + 10 off-topic queries)
cd backend; python ../evaluation/evaluate_attribution.py

# 3. Temporal Holdout Validation for Bipartite Method x Task Gap Matrix (5 topics, cutoff <= 2023)
cd backend; python scripts/gap_holdout.py --k 3 --limit 25

# 4. Non-Circular Multi-Source Discovery Evaluation & Unified results_v2.json
cd backend; python ../evaluation/evaluate.py
```

---

## 2. Retrieval Benchmark (BEIR SciFact, Test Split)

- **Dataset**: BEIR SciFact (`5,183` corpus documents, `300` test queries)
- **Embedding Model**: `all-MiniLM-L6-v2` (cosine similarity)
- **Lexical Baseline**: BM25 (`k1=1.2, b=0.75`) matching stemmed/stopword-filtered FTS ranking
- **Reranker Tested**: `cross-encoder/ms-marco-MiniLM-L-6-v2` (top-10 RRF candidates)

| Strategy | nDCG@10 | Recall@10 | MRR@10 | Notes |
|---|---:|---:|---:|---|
| `dense_only` | 0.6484 | 0.7883 | 0.6068 | Bi-encoder cosine only |
| `fts_only` | 0.6619 | 0.7866 | 0.6282 | Lexical BM25 only |
| `rrf` (`k=60`) | 0.6928 | **0.8412** | 0.6511 | Reciprocal Rank Fusion |
| **`convex` (`alpha=0.5`)** | **0.7151** | 0.8377 | **0.6801** | **Winner — set as `ChatService` default (`RETRIEVAL_FUSION=convex`)** |
| `rrf_cross_encoder` | 0.6522 | **0.8412** | 0.6004 | MS-MARCO MiniLM cross-encoder hurt scientific precision vs convex blend |

**Key takeaway**: Convex min-max combination (`alpha=0.5`) outperforms both single-modal baselines by **+0.0667 nDCG@10** over dense-only and **+0.0532 nDCG@10** over lexical-only, and beats MS-MARCO reranking on biomedical/scientific claims. Accordingly, [`ChatService`](../backend/app/services/chat.py) now defaults `RETRIEVAL_FUSION` to `"convex"`.

---

## 3. RAG Quote Attribution & Off-Topic Refusal (`evaluate_attribution.py`)

Evaluated across `20` OpenAlex abstracts (`4` per topic across `5` domains), `30` in-domain questions (`6` per topic), and `10` completely off-topic questions with `min_dense_similarity >= 0.22` threshold guard and strict T3 `post_validate_citation` verification (normalized exact substring or ordered token-sequence LCS >= 0.9):

| Metric | Measured Result |
|---|---:|
| Domain Questions Evaluated | 30 |
| Total Quoted Claims Extracted | 65 |
| Verified Against Retrieved Chunks | 59 |
| **Quote Verification Precision** | **0.9077 (90.8%)** |
| **Answers With >= 1 Verified Quote** | **1.0000 (30 / 30)** |
| Off-Topic Questions Evaluated | 10 |
| **No-Evidence / Off-Topic Refusal Rate** | **0.9000 (9 / 10)** |

---

## 4. Discovery Evaluation — Non-Circular External Judge (`evaluate.py`)

Previously, `evaluate.py` measured `mean_relevance` using `all-MiniLM-L6-v2` cosine similarity — the same signal used internally by `DiscoveryService._rank_candidates`. It was replaced with an independent neural architecture (`cross-encoder/ms-marco-MiniLM-L-6-v2` sigmoid relevance probability) and surface topic keyword overlap:

| Topic | Domain | Fetched | Unique (Dedup %) | Ext. Cross-Encoder Mean Prob | Topic Keyword Overlap |
|---|---|---:|---:|---:|---:|
| perovskite solar cell degradation mechanisms | Materials Science & Energy | 20 | 16 (20.0%) | 0.6470 | 0.6500 |
| retrieval augmented generation attribution benchmarks | Computer Science & NLP | 30 | 29 (3.3%) | 0.7839 | 0.7172 |
| crispr cas9 off target cleavage detection | Biomedical & Genetics | 20 | 18 (10.0%) | 0.7699 | 0.6759 |
| graph neural networks molecular property prediction | Graph ML & Chemistry | 20 | 20 (0.0%) | 0.5430 | 0.6917 |
| urban heat island remote sensing deep learning | Climate & Earth Obs. | 20 | 19 (5.0%) | 0.5393 | 0.7068 |

---

## 5. Temporal Holdout Gap Validation (`gap_holdout.py`)

Pre-2023 (`T = 2023`) bipartite Method x Task matrices checked against `2024–2026` (`H = 3`) OpenAlex literature (`cosine >= 0.45`):

- **Overall Matrix Void Precision@3**: **0.643** (`9/14`) vs **Random Empty Cell Baseline**: **0.357** (`5/14`).
- Full per-topic breakdown and caveats are in [`evaluation/gap_holdout_summary.md`](../evaluation/gap_holdout_summary.md) and [`evaluation/results_v2.json`](../evaluation/results_v2.json).
