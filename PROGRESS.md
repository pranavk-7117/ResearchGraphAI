# ResearchGraphAI — Autonomous Improvement Loop Progress

## Task Checklist

### PHASE A — Credibility fixes
- [x] **T0. Reset documentation state**
  - Rewrite `PROGRESS.md` to the new Phase A–E checklist.
  - Align `README.md` test count with real `pytest` collection count.
- [x] **T1. Make chat retrieval actually hybrid** (`backend/app/services/chat.py`, new migration)
- [x] **T2. Fix the Evolution service** (`backend/app/services/evolution.py`, `backend/app/services/constants.py`)
- [x] **T3. Strict quote verification** (`backend/app/services/llm.py`, `facts_extraction.py`, `gaps.py`)
- [x] **T4. Correct graph construction and PageRank** (`relations.py`, `research_graph.py`, `routes.py`, `clustering.py`)
- [x] **T5. Make the gap endpoint side-effect free** (`routes.py`, new migration, `GapsPage.tsx`)

### PHASE B — Hand-built Data Structures and Discrete Math
- [x] **T6. DS-1: `backend/app/dsa/` package, zero third-party graph libraries**
- [ ] **T7. DM-1: `backend/app/dm/` package & `docs/DM_PROOFS.md`**

### PHASE C — Graph and analytics improvements
- [ ] **T8. Multi-layer graph** (`relations.py`, `routes.py`, `schemas.py`, `GraphPage.tsx`)
- [ ] **T9. Better clustering** (`clustering.py`, UI display)
- [ ] **T10. Evolution uses main-path analysis** (`evolution.py`, `EvolutionPage.tsx`)

### PHASE D — The differentiators
- [ ] **T11. Corpus completeness meter** (`completeness.py`, endpoint, migration, UI card)
- [ ] **T12. Auditable gap engine** (`gaps.py`, `gap_matrix.py`, migration, `GapsPage.tsx`)
- [ ] **T12b. Temporal holdout validation** (`backend/scripts/gap_holdout.py`, `evaluation/`)
- [ ] **T13. Evaluation harness** (`evaluation/evaluate_retrieval.py`, `evaluate_attribution.py`, `evaluate.py`, `docs/EVALUATION.md`)
- [ ] **T14. Novelty assessment that is defensible** (`compare.py`)

### PHASE E — DBMS depth and polish
- [ ] **T15. DBMS additions** (migrations, `docs/DBMS_NOTES.md`, Dashboard stats)
- [ ] **T16. Final report and cleanup** (`README.md`, `docs/COURSE_MAPPING.md`, final evaluation summary)

---

## Decisions
1. **Database Engine**: PostgreSQL with `pgvector` extension, managed via SQLAlchemy 2.0 and versioned Alembic migrations (`backend/alembic/versions/`). Never edit existing migration `5d4d80a9f2aa`.
2. **Retrieval & Grounding**: Hybrid dense vector (`pgvector` cosine `<=>`) + PostgreSQL full-text search (`tsvector` + GIN index + `websearch_to_tsquery`), fused via configurable RRF or convex combination, with strict span-level quote verification.
3. **Hand-built DSA/DM Modules**: `backend/app/dsa/` and `backend/app/dm/` are implemented in pure Python with zero `networkx` or `scikit-learn` imports (`networkx` is permitted only inside tests as an oracle).
4. **Honesty & Non-Fabrication**: Missing metadata/evidence returns `null`/empty rather than synthetic template strings.

---

## Known Issues / Environment Blockers
- None currently blocking. Supabase PostgreSQL (`pgvector` 0.8.2, Alembic `5d4d80a9f2aa`) is live and verified.

---

## Loop Log

### T0 — Reset documentation state
- **Changed**: Rewrote `PROGRESS.md` to the Phase A–E checklist with zero references to legacy architecture; updated `README.md` test count from 15 to 19 (19 collected tests).
- **Tests**: `python -m pytest tests/ -v`: 19 passed in 39.29s against live Supabase Postgres.
- **Acceptance**: `Select-String` on `PROGRESS.md` for legacy terms returned 0 matches. **PASS**.

### T1 — Make chat retrieval actually hybrid
- **Changed**: Added Alembic migration `a1b2c3d4e501_t1_hybrid_fts_gin.py` (generated `tsvector` column `text_tsv` on `paper_chunks`, GIN index `ix_paper_chunks_text_tsv_gin`, GIN index `ix_papers_title_abstract_tsv_gin`); updated `PaperChunk` in `models.py`; rewrote `ChatService._hybrid_retrieve` in `services/chat.py` with pgvector `<=>` (top 30), `websearch_to_tsquery` + `ts_rank_cd` (top 30), `RETRIEVAL_FUSION=rrf|convex` (`alpha=0.5`), optional `RERANKER=none|cross_encoder`, and strict no-evidence threshold guard (removed score-0 abstract fallback).
- **Tests**: `python -m pytest tests/ -q` (`backend/`): 23 passed (including dense-only, keyword-only, RRF & convex ordering, no-evidence guard, and live DB isolation).
- **Acceptance**: `alembic upgrade head` / `downgrade -1` / `upgrade head` succeeded; `EXPLAIN` output: `Bitmap Heap Scan on paper_chunks -> Bitmap Index Scan on ix_paper_chunks_text_tsv_gin (cost=0.00..9.92 rows=1 width=0)`. **PASS**.

### T3 — Strict quote verification
- **Changed**: Replaced `post_validate_citation` in `services/llm.py` with whitespace/case/hyphen normalization, exact normalized substring matching, and localized ordered token-sequence LCS fallback (`>= 0.9`) returning `{verified, chunk_id, match_type, score}`; updated `facts_extraction.py` to validate strictly per cited chunk and added `quote_verification_precision(project_id, db)`; updated `gaps.py` to verify all evidence items against stored chunks and exclude unverified quotes from gap scores.
- **Tests**: `python -m pytest tests/ -q` (`backend/`): 25 passed (exact, token-sequence threshold, paraphrase rejection, wrong-chunk failure, gap score exclusion, precision metric).
- **Acceptance**: All 4 grounding tests + full suite passed. **PASS**.

### T2 — Fix the Evolution service
- **Changed**: Added `services/constants.py` with shared relation-type & basis constants imported in `relations.py` and `evolution.py`; fixed `evolution.py` to query `RELATION_SIMILAR` and `.score` (fixing `"inferred_similarity"`/`.weight` bug); removed all template filler from `evolution.py`, `EvolutionPage.tsx`, and `GraphPage.tsx`; omitted empty phase windows; replaced keyword check in finding dynamics with structured Pydantic enum (`confirms|extends|contradicts|unrelated|insufficient_evidence`) + strict T3 quote validation across top-N similarity pairs.
- **Tests**: `python -m pytest tests/ -q`: 27 passed; `npm --prefix frontend run build` passed.
- **Acceptance**: `Select-String` grep for all removed filler strings across `backend/app/` and `frontend/src/` returned 0 matches. **PASS**.

### T4 — Correct graph construction and PageRank
- **Changed**: Added Alembic migration `b2c3d4e5f602_t4_directed_and_graph_cache.py` (`directed` boolean on `paper_relations`, `graph_analytics_cache` table); added batched L2-normalized mean chunk embedding helper `get_paper_embeddings` in `embeddings.py` used by `relations.py` & `clustering.py`; replaced O(N^2) pairwise loop & N+1 queries with O(1) lookup dicts, strict `fuzz.ratio >= 95` (±1 year) citation resolution, and pgvector LATERAL mutual k-NN (`SIM_K=4`, stored undirected `source_id < target_id`, `directed=False`); restricted PageRank strictly to citation DAG (`RELATION_CITES` only) with `(project_id, corpus_version)` caching.
- **Tests**: `python -m pytest tests/ -q`: 31 passed (including L2 mean embedding test, PageRank invariance under added/reversed similarity edges, strict citation fuzz test, and 40-paper bounded SQL query count <= 15).
- **Acceptance**: `alembic upgrade/downgrade/upgrade` succeeded; 40-paper relation build bounded to <= 15 SQL queries. **PASS**.

### T5 — Make the gap endpoint side-effect free
- **Changed**: Added Alembic migration `c3d4e5f60703_t5_gap_statement_hash_unique.py` (`statement_hash` column + unique constraint `uq_research_gaps_proj_ver_hash` on `(project_id, corpus_version, statement_hash)`); made `GET /projects/{id}/gaps` strictly read-only; added `POST /projects/{id}/gaps/detect` enqueuing `gaps_detect` job via `JobService`; deduplicated gaps at insert time in `gaps.py`; updated `GapsPage.tsx` with Detect Gaps button & live job progress polling.
- **Tests**: `python -m pytest tests/ -q`: 34 passed; `npm --prefix frontend run build` passed.
- **Acceptance**: `alembic upgrade/downgrade/upgrade` succeeded; `test_get_gaps_is_strictly_read_only`, `test_post_gaps_detect_enqueues_job`, and DB unique constraint `IntegrityError` test all passed. **PASS**.

### T6 — DS-1: Hand-built `backend/app/dsa/` package
- **Changed**: Implemented `graph.py`, `union_find.py`, `topo.py` (Kahn's algorithm, `CycleError`, `is_unique_topological_order`), `heap.py` (`MinHeap`, `top_k`), `shortest_path.py` (Dijkstra with semantic edge cost), `mst.py` (Kruskal MST/MaxST), `trie.py`, and `hashtable.py` (open addressing linear probing). Integrated `HashTable` and `top_k` into `discovery.py`/`relations.py`, `dijkstra` into `research_graph.py`, and `Trie` into `GET /projects/{id}/autocomplete`. Added `backend/scripts/bench_dsa.py`.
- **Tests**: `python -m pytest tests/ -q`: 41 passed (7 property-oracle tests x >=200 randomized cases each against `networkx`/`heapq`/`dict`). Benchmark (`bench_dsa.py`): HashTable 31.01ms vs dict 1.70ms (N=10k); top_k 9.93ms vs sorted 2.34ms (N=20k, k=25); Dijkstra 56.16ms vs nx 10.41ms (50 queries); Kruskal MST 5.09ms vs nx 4.80ms (V=300, E=1500).
- **Acceptance**: `Select-String` for `networkx`/`sklearn` in `backend/app/dsa/` returned 0 matches. **PASS**.
