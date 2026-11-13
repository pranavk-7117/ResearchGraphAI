# ResearchGraphAI

> Evidence-Grounded AI Research Discovery, Graph Analytics, and Auditable Gap Synthesis Platform

ResearchGraphAI is an academic research workspace built with **FastAPI + SQLAlchemy 2.0 + PostgreSQL/`pgvector`** and **React + Vite + TypeScript**. Every claim, gap statement, evolution backbone, and RAG chat citation traces strictly to verified scholarly metadata and stored passage chunks — missing fields return `null`/empty with explicit warnings rather than fabricated template filler.

---

## 1. Key Differentiators & Implemented Capabilities

1. **Corpus Completeness Meter (`app/dm/inclusion_exclusion.py`, `app/services/completeness.py`)**:
   - Tracks multi-source paper capture overlap across OpenAlex, Semantic Scholar, and arXiv (`project_papers.sources`).
   - Computes exact Venn overlaps via the Inclusion-Exclusion Principle and applies the bias-corrected **Chapman capture-recapture estimator** (with Seber variance 95% CI), explicitly labeled as a lower-bound estimate and automatically suppressed when overlap `m < 5`.
2. **Auditable Research Gap Engine & Temporal Holdout (`app/services/gap_matrix.py`, `app/services/gaps.py`)**:
   - **Bipartite Method x Task/Dataset Matrix**: Normalizes extracted methods and tasks/benchmarks (`fuzz.ratio >= 92` + light lemmatization) and scores empty/sparse cells with PMI + exact lower-tail **hypergeometric p-values** (`scipy.stats.hypergeom`).
   - **Full-Corpus Signal Clustering**: Groups all limitation & future-work statements via hand-built **Union-Find** (`cosine >= 0.75`) without artificial truncation.
   - **Strict Quote Verification & OpenAlex Check**: Drops unverified LLM quotes before scoring/persistence and runs structured `"method" AND "task"` queries in OpenAlex to flag externally addressed gaps (`status: likely_addressed`).
3. **Defensible Corpus-Relative Novelty Assessment (`app/services/compare.py`)**:
   - Benchmarks uploaded manuscript PDFs using batched corpus chunk embeddings: **Top-k (`k=5`) nearest-neighbor cosine similarity**, **local density percentile** (vs leave-one-out corpus k-NN distribution), and **Uzzi-style reference-combination atypicality z-score** against 50 shuffled nulls, explicitly marked `relative_to_corpus_only: true`.
4. **Multi-Layer Graph & Hand-Built DS/DM Core (`app/dsa/`, `app/dm/`)**:
   - Pure-Python data structures (zero `networkx`/`sklearn` runtime imports): `Graph` (BFS/DFS), `UnionFind`, Kahn's topological sort + cycle extraction, `MinHeap`/`top_k`, Dijkstra, Kruskal MST, Prefix `Trie`, and linear-probing `HashTable`.
   - Discrete Math engine: Hasse transitive reduction & closure, Search Path Count (SPC) DP, Global & Key-Route Main-Path Analysis (`evolution.py`), Inclusion-Exclusion, and Topological Reading Paths.
   - Graph layers: Citation DAG (`cites`), Bibliographic Coupling Jaccard (`coupling`), and pgvector LATERAL mutual k-NN similarity (`similar`), with citation-only PageRank, betweenness, k-core, Burt constraint, and Leiden/Louvain/Agglomerative clustering.
5. **Hybrid RAG Chat (`app/services/chat.py`)**:
   - Dual-stage **pgvector cosine `<=>` + PostgreSQL `tsvector` GIN `websearch_to_tsquery`**, fused by **convex combination (`alpha=0.5`, winner on BEIR SciFact)** or RRF, optional `CrossEncoder` reranking, and strict no-evidence threshold refusal.
6. **PostgreSQL Depth (`docs/DBMS_NOTES.md`, Alembic migrations)**:
   - Views (`v_project_paper_stats`), Materialized Views (`mv_field_growth`), PL/pgSQL trigger (`trg_project_papers_bump_corpus_version`), `WITH RECURSIVE` citation ancestor queries, window `RANK() OVER`, and `FOR UPDATE SKIP LOCKED` background job queues.

---

## 2. Core API Endpoints

- **Projects & DBMS Stats**: `POST/GET/DELETE /api/projects`, `GET /api/projects/{id}/stats`, `POST /api/projects/{id}/stats/refresh`
- **Discovery & Completeness**: `POST /api/projects/{id}/discover`, `GET /api/projects/{id}/candidates`, `GET /api/projects/{id}/completeness`
- **Processing & Jobs**: `POST /api/projects/{id}/select-candidates`, `POST /api/projects/{id}/process`, `GET /api/jobs/{job_id}`
- **Graph, Clusters & Reading Paths**: `GET /api/projects/{id}/graph`, `POST /api/projects/{id}/recluster`, `GET /api/projects/{id}/backbone`, `POST /api/projects/{id}/clusters/recompute`, `GET /api/projects/{id}/cluster-representatives`, `GET /api/projects/{id}/autocomplete`, `GET /api/projects/{id}/hasse`, `GET /api/projects/{id}/reading-path`, `GET /api/projects/{id}/ancestors`
- **Evolution, Facts & Gaps**: `GET /api/projects/{id}/evolution`, `GET /api/projects/{id}/facts/coverage`, `POST /api/projects/{id}/facts/reextract`, `GET /api/projects/{id}/gaps`, `POST /api/projects/{id}/gaps/detect`, `GET /api/projects/{id}/gap-matrix`, `POST /api/gaps/{gap_id}/feedback`
- **RAG Chat & Manuscript Comparison**: `POST /api/projects/{id}/chat`, `POST /api/projects/{id}/upload-compare`, `GET /api/projects/{id}/analyses`

---

## 3. Getting Started

### Prerequisites
- Python 3.11+ & Node.js 18+
- PostgreSQL with `pgvector` extension enabled (e.g., Supabase)

### Environment & Database Setup
```bash
cd backend
cp .env.example .env
# Set DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, GROQ_API_KEY (or another provider), OPENALEX_MAILTO
alembic upgrade head
```

### Run Backend, Worker & Frontend
```bash
# Terminal 1: FastAPI API
cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2: Durable SKIP LOCKED Background Worker
cd backend && python -m app.worker

# Terminal 3: React Frontend
cd frontend && npm install && npm run dev -- --port 5174
```

---

## 4. Tests & Empirical Evaluation Reproduction

### Automated Test Suite (**80 backend test cases + 12 frontend tests**)
Covers unit tests, randomized property-oracle checks against `networkx`/`heapq`/`dict`, database isolation guards (protecting production Supabase), and PostgreSQL integration tests (RLS/isolation, GIN FTS, `pgvector` HNSW, triggers, views, `WITH RECURSIVE`, `RANK() OVER`, unique constraints):
```bash
cd backend && python -m pytest tests/ -v
cd frontend && npm test
cd frontend && npm run build
```

### Empirical Benchmarks (Full Methodology in [`docs/EVALUATION.md`](docs/EVALUATION.md))
```bash
cd backend && python ../evaluation/evaluate_retrieval.py     # BEIR SciFact (n=300): Convex nDCG@10=0.7151 vs Dense 0.6484
cd backend && python ../evaluation/evaluate_attribution.py   # 30 domain + 10 off-topic Qs: 90.8% quote precision, 90% refusal
cd backend && python scripts/gap_holdout.py --k 3 --limit 25 # 5-topic pre-2023 holdout: Precision@3=0.643 vs 0.357 random
cd backend && python ../evaluation/evaluate.py               # Non-circular external Cross-Encoder discovery benchmark -> results_v2.json
python evaluation/extraction_eval.py                         # Semantic validator discriminator benchmark (genuine limitations vs adversarial distractors)
```

---

## 5. Honest Limitations & Scientific Disclaimers

- **Bounded Sample & Corpus Scope**: Novelty metrics (`relative_to_corpus_only: true`), gap matrices, and Chapman completeness estimates characterize *only the retrieved/indexed project corpus* — never absolute proof of absence across all science.
- **Open-Access Full-Text Dependence**: While metadata and abstracts are indexed broadly, span-level quote verification on closed-access papers operates on abstracts only (`abstract_only: true`) and explicitly discloses that status.
- **Capture-Recapture Independence Assumption**: The Chapman completeness meter assumes approximate independence between indexed discovery sources and serves strictly as an educational lower-bound indicator (`m >= 5` required).
- **Community Detection Environment**: `igraph`/`leidenalg` wheels require C build tooling unavailable in some environments; when absent, [`ClusteringService`](backend/app/services/clustering.py) logs an explicit fallback to connected NetworkX modularity/Louvain communities rather than failing silently.
