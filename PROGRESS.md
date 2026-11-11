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
- [x] **T7. DM-1: `backend/app/dm/` package & `docs/DM_PROOFS.md`**

### PHASE C — Graph and analytics improvements
- [x] **T8. Multi-layer graph** (`relations.py`, `routes.py`, `schemas.py`, `GraphPage.tsx`)
- [x] **T9. Better clustering** (`clustering.py`, UI display)
- [x] **T10. Evolution uses main-path analysis** (`evolution.py`, `EvolutionPage.tsx`)

### PHASE D — The differentiators
- [x] **T11. Corpus completeness meter** (`completeness.py`, endpoint, migration, UI card)
- [x] **T12. Auditable gap engine** (`gaps.py`, `gap_matrix.py`, migration, `GapsPage.tsx`)
- [x] **T12b. Temporal holdout validation** (`backend/scripts/gap_holdout.py`, `evaluation/`)
- [x] **T13. Evaluation harness** (`evaluation/evaluate_retrieval.py`, `evaluate_attribution.py`, `evaluate.py`, `docs/EVALUATION.md`)
- [x] **T14. Novelty assessment that is defensible** (`compare.py`)

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

### T7 — DM-1: Hand-built `backend/app/dm/` package & `docs/DM_PROOFS.md`
- **Changed**: Implemented `partial_order.py` (transitive reduction/Hasse diagram & closure), `path_counting.py` (Search Path Count DP over topo order), `main_path.py` (global & key-route main path with zero-edge guard), `inclusion_exclusion.py` (`union_size` + breakdown), `reading_path.py` (topological prerequisite ordering ranked by citation-DAG PageRank), and `docs/DM_PROOFS.md`. Exposed `GET /projects/{id}/hasse` and `GET /projects/{id}/reading-path`.
- **Tests**: `python -m pytest tests/ -q`: 46 passed (hand-checked SPC/main-path DAG, 100 random DAG Hasse/closure checks vs NetworkX, inclusion-exclusion vs set union, reading path topological & PageRank cap checks).
- **Acceptance**: Zero `networkx`/`sklearn` imports in `backend/app/dm/`; all 5 DM-1 tests + full suite green. **PASS**.

### T8 — Multi-layer graph
- **Changed**: Added bibliographic coupling layer (`RELATION_COUPLING`, Jaccard similarity over `paper_references`, no extra API calls) in `relations.py`; added `betweenness`, `k_core`, and `burt_constraint` on the combined undirected graph in `research_graph.py` (cached per `(project_id, corpus_version)`); exposed `layer` and `shared_references` on `GraphEdge` in `schemas.py` & `routes.py`. Updated `GraphPage.tsx` with layer toggles (citation + coupling default on, semantic off), edge weight slider, Time-Lane layout (`year x cluster`), 1-hop/2-hop ego-network focus, Trie autocomplete search, PageRank node sizing, bridge paper ring markers, DM-1 Reading Path panel, and "Why Connected?" inspector. Co-citation skipped because OpenAlex `cited_by` lists are not separately stored.
- **Tests**: `python -m pytest tests/ -q`: 48 passed (hand-computed Jaccard coupling test `2/4=0.5`, structural metrics & API layer labels test); `npm --prefix frontend run build` passed.
- **Acceptance**: `npm run build` passed; `/graph` returns `layer` names and exact Jaccard weights. **PASS**.

### T9 — Better clustering
- **Changed**: Rewrote `clustering.py` to support Leiden community detection on the weighted combined graph (with logged fallback to `greedy_modularity_communities` / `louvain_communities` when `igraph`/`leidenalg` aren't installed, plus connected-component enforcement) and cosine Agglomerative clustering with silhouette-selected `k` in `[2, min(8, n-1)]` and `O(1)` `pid_to_idx` lookup; computed & stored modularity, silhouette, and NMI partition agreement in `ResearchCluster.params`; exposed via `ClusterOut` and displayed in `GraphPage.tsx`.
- **Tests**: `python -m pytest tests/ -q`: 50 passed (connected-subgraph guarantee, seed=42 determinism, silhouette optimal-k selection, and NMI verification); `npm --prefix frontend run build` passed.
- **Acceptance**: Connected communities & deterministic partition verified. **PASS**.

### T10 — Evolution uses main-path analysis
- **Changed**: Built chronological citation DAG (`DSAGraph`) in `evolution.py` using `app.dm.main_path` (`global_main_path` and `key_route_main_path` with SPC weights), configurable `MIN_BACKBONE_CITATIONS` (default 3) sparsity guard with zero silent similarity fallback, and optional `CITATION_INTENT_PRUNING` flag that cleanly skips when no full-text chunks exist. Exposed `citation_backbone` via `EvolutionOut` (`schemas.py`, `routes.py`), `api.ts`, and rendered a Time-Lane Citation Backbone chain + sparsity warning banner in `EvolutionPage.tsx`.
- **Tests**: `python -m pytest tests/ -q`: 52 passed (diamond DAG SPC main-path selection, similarity isolation, sparse citation warning, intent pruning skip); `npm --prefix frontend run build` passed.
- **Acceptance**: Diamond DAG main path matches hand-calculated SPC; sparse graph emits warning without similarity fallback. **PASS**.

### T11 — Corpus completeness meter
- **Changed**: Added Alembic migration `d4e5f6070804_t11_project_paper_sources.py` adding JSONB `sources` column on `project_papers` (with backfill from `papers.source_name`); updated `DiscoveryService._deduplicate_candidates` and `_persist_candidates` (`discovery.py`, `clients/base.py`) to retain all intersecting discovery sources per paper (`openalex`, `semantic_scholar`, `arxiv`). Created `services/completeness.py` computing DM-1 `inclusion_exclusion_breakdown` and bias-corrected Chapman capture-recapture estimator (`Seber` 1970 variance, 95% CI, refusal when `overlap m < 5`, explicit lower-bound disclaimer; `statsmodels` absent so Chapman on best pair is explicitly noted). Exposed `GET /projects/{id}/completeness` and added the Corpus Completeness card to `DiscoverPage.tsx`.
- **Tests**: `python -m pytest tests/ -q`: 56 passed (multi-source deduplication provenance, Venn union & low-overlap refusal, closed-form LP/Chapman checks, 500-trial simulation achieving >= 90% 95%-CI empirical coverage); `alembic upgrade/downgrade/upgrade` & `npm --prefix frontend run build` passed.
- **Acceptance**: 500-trial CI coverage >= 90% and `m < 5` suppression verified. **PASS**.

### T12 — Auditable gap engine
- **Changed**: Added Alembic migration `e5f607080905_t12_gap_matrix_cell.py` adding `matrix_cell` JSONB column on `research_gaps`; created `services/gap_matrix.py` with label normalization (`fuzz.ratio >= 92` plural/synonym merge), bipartite `Method x Task/Dataset` co-occurrence matrix with PMI + lower-tail `scipy.stats.hypergeom` p-values, and full-corpus `UnionFind` (`cosine >= 0.75`) signal clustering removing the prior `[:15]` cap. Updated `services/gaps.py` with single-source-of-truth `GAP_SCORE_FORMULA`, strict dropping of unverified quotes from persisted `supporting_evidence`/`counter_evidence`, and structured OpenAlex queries marking gaps with `> GAP_EXTERNAL_ADDRESSED_THRESHOLD` hits as `likely_addressed` with `0.65x` penalty. Exposed read-only `GET /projects/{id}/gap-matrix` and rendered an interactive matrix heatmap + status badges in `GapsPage.tsx`.
- **Tests**: `python -m pytest tests/ -q`: 59 passed (synonym merging & hand-computed hypergeometric `10/56=0.1786` empty cell test, 20-signal UnionFind clustering without truncation, unverified quote drop & `likely_addressed` penalty check); `alembic upgrade/downgrade/upgrade` & `npm --prefix frontend run build` passed.
- **Acceptance**: Empty matrix cell stats match exact hypergeometric CDF and unverified quotes are excluded/dropped. **PASS**.

### T12b — Temporal holdout validation
- **Changed**: Expanded `evaluation/topics.json` to 5 topics across distinct scientific domains; added `backend/scripts/gap_holdout.py` building pre-2023 (`T = 2023`) OpenAlex corpora, extracting `(method, task_or_dataset)` pairs cleanly (`max_tokens=4000` + reasoning tag stripping added to `services/llm.py`), computing T12 matrix void predictions, and checking post-2023 (`2024–2026`) OpenAlex + embedding similarity matches (`cosine >= 0.45`) against a random empty-cell baseline. Saved JSON & markdown reports in `evaluation/gap_holdout_results.json` and `evaluation/gap_holdout_summary.md`.
- **Tests**: Executed `python scripts/gap_holdout.py --k 3 --limit 25`: Matrix Gap Precision@3 = **0.643** (9/14) vs Random Empty Cell Baseline = **0.357** (5/14), with explicit small-sample caveats documented.
- **Acceptance**: 5-topic holdout table + caveats produced from real pre-T/post-T OpenAlex queries. **PASS**.

### T13 — Evaluation harness
- **Changed**: Created `evaluation/evaluate_retrieval.py` (BEIR SciFact 5,183-doc, 300-query benchmark across dense, BM25/FTS, RRF, convex, and RRF+cross-encoder); updated `ChatService` default `RETRIEVAL_FUSION` to winning `"convex"` (`0.7151` nDCG@10, `0.6801` MRR@10). Created `evaluation/evaluate_attribution.py` (30 domain questions + 10 off-topic questions against OpenAlex chunks), fixed circular `mean_relevance` in `evaluation/evaluate.py` with independent `cross-encoder/ms-marco-MiniLM-L-6-v2` probability & topic keyword overlap, saved `evaluation/results_v2.json`, and wrote `docs/EVALUATION.md` with exact reproduction commands.
- **Tests**: `evaluate_retrieval.py` (300 SciFact queries: convex `nDCG@10=0.7151` > RRF `0.6928` > FTS `0.6619` > dense `0.6484`), `evaluate_attribution.py` (`quote_verification_precision=0.9077`, `answers_with_verified_quote=1.0`, `off_topic_refusal=0.9`), `evaluate.py` + `pytest tests/test_rag_chat.py` (8 passed).
- **Acceptance**: Non-circular metrics, real BEIR SciFact & attribution numbers, and `docs/EVALUATION.md` verified. **PASS**.

### T14 — Novelty assessment that is defensible
- **Changed**: Replaced single `1 - mean(cosine)` in `CompareService` (`services/compare.py`) with `compute_corpus_novelty_metrics` using batched `get_paper_embeddings`: (a) top-`k` (`k=5`) nearest-neighbor similarity list & mean, (b) leave-one-out corpus local density percentile, and (c) Uzzi-style pairwise reference-combination atypicality z-score against 50 pool shuffles (`compute_reference_atypicality`). Stored `relative_to_corpus_only: true`, `method_names`, and `formula` in `PaperAnalysis.evidence_rows` and rendered the neighbor breakdown + provenance card in `ComparePage.tsx`.
- **Tests**: Added `backend/tests/test_compare_novelty.py` (2 passed: near-copy vs unrelated separation, uniform reference null z-score + sparse guard) and `npm --prefix frontend run build` passed.
- **Acceptance**: Near-copy paper scores `top_k_mean_similarity > 0.95` & `max_similarity > 0.99`; unrelated scores `< 0.10`. **PASS**.
