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
- [x] **T15. DBMS additions** (migrations, `docs/DBMS_NOTES.md`, Dashboard stats)
- [x] **T16. Final report and cleanup** (`README.md`, `docs/COURSE_MAPPING.md`, final evaluation summary)

---

## Round 2 Checklist

### Correctness & Evaluation Honesty
- [x] **R1. Fix FTS OR query** (`backend/app/services/chat.py`, tests in `test_rag_chat.py`)
- [x] **R2. Retrieval benchmark uses production path** (`evaluation/evaluate_retrieval.py`, `docs/EVALUATION.md`)
- [x] **R3. Attribution benchmark uses production path** (`evaluation/evaluate_attribution.py`, `docs/EVALUATION.md`)
- [x] **R4. Harden quote verifier** (`backend/app/services/llm.py`, `backend/tests/test_rag_chat.py`)
- [x] **R5. Gap holdout with real statistics** (`backend/scripts/gap_holdout.py`, `evaluation/`)
- [x] **R6. Completeness dependence diagnostic** (`backend/app/services/completeness.py`, `docs/EVALUATION.md`)
- [x] **R7. Test isolation from live DB** (`backend/tests/conftest.py`, `docker-compose.yml`, `.github/workflows/ci.yml`)
- [x] **R8. Housekeeping and small bugs** (`routes.py`, `dm/path_counting.py`, `dsa/mst.py`, requirements files)

### Knowledge Graph UI Improvements
- [x] **G1. Layout & edge pruning defaults** (time-lane default, min edge weight percentile)
- [x] **G2. Label culling & collision** (top 8 by size + hover/selected/ego)
- [x] **G3. Arrowheads ONLY on citation edges** (`directed` per edge, tests)
- [x] **G4. Node sizing & PageRank diagnostic** (citations default, warning chip on flat PageRank)
- [ ] **G5. Cluster readability & c-TF-IDF labels** (moved to K5 in Round 3)
- [x] **G6. Selected node inspector & unified graph page** (in/out corpus citations, path analysis)
- [x] **G7. Remove legacy fake research graph artifacts** (grep verification)
- [x] **G8. Frontend Vitest suite for Knowledge Graph** (`GraphPage.test.tsx` / `graph_logic.test.mjs`)

### Round 2 Wrap-up
- [x] **R-FINAL. Documentation, before/after table, screenshots** (`docs/EVALUATION.md`, `README.md`)

---

## Round 3 Checklist

### Part 1 — Knowledge Graph
- [x] **K1. Stop the graph from rearranging on click** (`frontend/src/pages/GraphPage.tsx`)
- [x] **K2. Readable defaults like the simple earlier version** (Radial Clustered default, beeswarm jitter for time-lane, solid coloured edges)
- [x] **K3. Real label collision avoidance** (greedy priority placer, bounding box checks, max 8 labels)
- [x] **K4. Fit and sizing** (initial render & layout change only, not on click)
- [x] **K5. Clusters that make sense** (`clustering.py`, `routes.py`, `GraphPage.tsx` — min size 3, merge small, c-TF-IDF labels, `POST /recluster`)
- [x] **K6. Remove dead and misleading graph/evolution fields** (remove `pub_type`, `new_aspects`, no `extends` edge)

### Part 2 — Evolution Timeline & Extraction Quality
- [x] **E1. Explicit extraction states** (`paper_facts.status`, `source_scope`, `paper_kind`, `error_reason`, migration, UI honest states)
- [x] **E2. Lists instead of single slots; fix misnamed field** (up to 5 items for limitations/future_work, rename `gaps_solved` -> `limitations_and_gaps`)
- [x] **E3. Fix section detection** (`pdf_processing.py` — line-anchored heading detector, PyMuPDF font/bold flags)
- [x] **E4. Better full-text access** (`fulltext.py` — multi-source fallbacks, timeout/retry, `fulltext_note`)
- [x] **E5. Targeted limitation / future-work extraction** (`facts_extraction.py` — cue lexicon scoring, top-10 candidates, exact quote return)
- [x] **E6. Semantic validation: reject verified junk** (title-echo < 0.6, abstract-echo, min 6 tokens, contribution fallback labels)
- [x] **E7. Paper-type awareness** (survey vs empirical vs system, open challenges for surveys)
- [x] **E8. Retries, backfill and coverage transparency** (`POST /facts/reextract`, `GET /facts/coverage`, Retry button)
- [x] **E9. Measure extraction quality honestly** (`extraction_eval.py`, gold template, `docs/EVALUATION.md`)

### Part 3 — Other Issues & Polish
- [x] **C1. Test database setup** (session-scoped fixture in `conftest.py` running `alembic upgrade head` on empty scratch DB)
- [x] **C2. Frontend duplicates cleanup** (unused components, legacy colours, types)
- [x] **C3. README / PROGRESS honesty audit** (verify all checklist claims against actual code)
- [x] **R3-FINAL. Report and cleanup** (screenshots, before/after tables, evaluation docs)

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

### T15 — DBMS additions
- **Changed**: Added reversible Alembic migration `f60708091006_t15_dbms_views_trigger.py` creating SQL View `v_project_paper_stats`, Materialized View `mv_field_growth` (`ix_mv_field_growth_proj_year`), and PL/pgSQL trigger `trg_project_papers_bump_corpus_version` (`fn_bump_project_corpus_version`) bumping `research_projects.corpus_version` on `project_papers` INSERT/DELETE. Added `services/dbms_queries.py` implementing single-query view listing in `GET /projects`, `GET /projects/{id}/stats`, `POST /projects/{id}/stats/refresh`, `GET /projects/{id}/ancestors` (`WITH RECURSIVE` CTE with array cycle guard), and `GET /projects/{id}/cluster-representatives` (`RANK() OVER (PARTITION BY cluster_id ...)`). Wired stats into `DashboardPage.tsx` and authored `docs/DBMS_NOTES.md` with ER diagram, FDs/JSONB rationale, 3 real `EXPLAIN (ANALYZE, BUFFERS)` query plans, `SKIP LOCKED` isolation analysis, CAP/BASE comparison, and Supabase RLS policies.
- **Tests**: `python -m pytest tests/ -q`: 62 passed (`test_dbms_features.py` verified trigger INSERT/DELETE increments, `v_project_paper_stats`, `mv_field_growth`, `WITH RECURSIVE` matching `app.dsa.graph.bfs`, and `RANK() OVER`); `alembic upgrade/downgrade/upgrade` & `npm --prefix frontend run build` passed.
- **Acceptance**: Real `EXPLAIN ANALYZE` plans captured (`13.719ms` FTS GIN, `50.060ms` HNSW, `1.681ms` recursive CTE) and live Postgres test passed. **PASS**.

### T16 — Final report and cleanup
- **Changed**: Rewrote `README.md` to accurately reflect all implemented features, API endpoints, 3 core differentiators, honest limitations, 62 passing tests, and exact evaluation commands matching `docs/EVALUATION.md`. Created `docs/COURSE_MAPPING.md` mapping every DBMS, DS, and DM syllabus topic to exact source files, migrations, endpoints, and tests.
- **Tests**: Final `python -m pytest tests/ -q`: **62 passed in 90.02s**; `npm --prefix frontend run build`: **passed** (`vite v6.4.3`, `dist/assets/index-BiQXkUQe.js`); `Select-String` verified zero `networkx`/`sklearn` imports in `backend/app/dsa/` and `backend/app/dm/`.
- **Acceptance**: All checklist items `T0`–`T16` completed cleanly (`[x]`), test suite & production frontend build green, pushed to `origin main`. **PASS**.

---

## Round 2 Loop Log

### R1 — Fix FTS OR query
- **Changed**: Updated `_fts_search` in `backend/app/services/chat.py` to detect websearch operators (`"..."`, `-\w`, `or`, `and`). If absent, tokenizes query, drops terms `< 3` chars, caps at 12 lexemes, and joins with ` or ` so multi-word natural queries avoid empty result sets from default AND semantics. Added doc-length normalization `ts_rank_cd(..., 1)` to prevent long documents from biasing rank.
- **Tests**: Added `test_fts_search_query_formatting_and_guards` in `test_rag_chat.py` (passed).
- **Acceptance**: Natural language query with 7 terms successfully formats into an OR-expression and preserves exact quotes/hyphen operators. **PASS**.

### R4 — Harden quote verifier
- **Changed**: Rewrote `post_validate_citation` in `backend/app/services/llm.py` with:
  1. Minimum length guard (`min_tokens=5`) returning `reject_reason="too_short"` for 2-word noun phrases.
  2. Number extraction invariance: all numbers in the quote must match the passage verbatim (`reject_reason="number_mismatch"`).
  3. Polarity/negation checks: checks opposing words (e.g. `increases` vs `decreases`, `effective` vs `ineffective`) and counts negation words (`reject_reason="negation_flip"`).
  4. Contiguous sliding window search disallowing spliced non-contiguous clauses.
- **Tests**: Added `test_hardened_quote_verifier_guards_all_9_cases` in `test_intelligence_and_grounding.py` (all 9 cases pass).
- **Acceptance**: Exact quotes pass; spliced fragments, number mutations, short phrases, and polarity flips are strictly rejected. **PASS**.

### R7 — Test isolation from live DB
- **Changed**: Created `backend/tests/conftest.py` with `is_live_db_permitted()` guarding against accidental execution against production Supabase unless `ALLOW_LIVE_TESTS=1`. Registered markers (`live_db`, `fake_embeddings`, `requires_model`). Created `docker-compose.yml` (`pgvector/pgvector:pg16` on port 5433) and `.github/workflows/ci.yml`. Added `SET LOCAL enable_seqscan = off;` to GIN explain test. Marked live DB tests with `@pytest.mark.live_db` so CI/sandbox without DB skips safely instead of throwing DNS lookup errors. Added `test_test_isolation_guard.py` verifying the guard logic.
- **Tests**: `python -m pytest tests/ -q`: **65 passed, 7 skipped, 0 failed in 7.87s**.
- **Acceptance**: Scratch DB isolation verified; tests never hit live Supabase uncommanded. **PASS**.

### R8 — Housekeeping and small bugs
- **Changed**: Removed duplicate `GET /projects/{project_id}/completeness` route in `backend/app/api/routes.py` (was declared twice at lines 298 and 402). Fixed `dm/path_counting.py::compute_spc` isolated-node handling so isolated vertices do not count as phantom paths in `total_paths`. Exposed hand-built Kruskal MST via `GET /projects/{project_id}/backbone`. Created `requirements-eval.txt` and `requirements-leiden.txt`. Updated `docs/COURSE_MAPPING.md`.
- **Tests**: Added `test_spc_with_isolated_nodes` in `test_dm.py` (passed); `test_dsa.py` (all 200 Kruskal random oracle tests pass).
- **Acceptance**: Duplicate route eliminated; isolated node test passes; MST backbone reachable. **PASS**.

### R6 — Completeness dependence diagnostic
- **Changed**: Added source dependence diagnostic in `CompletenessService.compute` (`completeness.py`), calculating `observed_m / expected_m` under independence. Flagged positive dependence when ratio `> 1.15`. Updated `DiscoverPage.tsx` with explicit `"estimated coverage (lower bound)"` label and warning alert explaining source correlation on popular papers.
- **Tests**: Added `test_completeness_dependence_diagnostic` in `test_completeness.py` (passed).
- **Acceptance**: Overlap diagnostic and lower-bound warning rendered cleanly. **PASS**.

### R2, R3, R5 — Evaluation honesty & statistical rigor
- **Changed**: Updated `evaluation/evaluate_retrieval.py` with 1,000-sample bootstrap 95% confidence intervals. Updated `evaluation/evaluate_attribution.py` with exact Wilson score 95% confidence intervals. Updated `backend/scripts/gap_holdout.py` and `evaluation/gap_holdout_summary.md` with two-sided Fisher's exact test (`p = 0.257`, honestly reporting that directional advantage 9/14 vs 5/14 is not statistically significant at alpha=0.05).
- **Acceptance**: All reproduction commands verified and documented in `docs/EVALUATION.md`. **PASS**.

### G1–G8 — Knowledge Graph UI upgrades
- **Changed**:
  - **G1**: Set default `layoutMode` to `"time-lane"` (was `"force"`) and `nodeSizeMode` to `"citations"`. Added automatic edge-density pruning percentile when `edges > 3 * nodes` to eliminate initial hairball clutter.
  - **G2**: Implemented label culling in `nodeCanvasObject`: only renders labels for top 8 papers by citation count, the selected node, and immediate ego network neighbors.
  - **G3**: Set `linkDirectionalArrowLength` to 6 strictly for citation edges (`relation_type === 'cites'`); coupling and semantic edges render without arrowheads (dash/dotted undirected).
  - **G4**: Sizing defaults to citation counts; added automatic detection of uniform/uninformative PageRank with warning chip in toolbar.
  - **G5**: Enhanced cluster readability with small-cluster labels (`member_count < 3`).
  - **G6**: Added in-corpus citation breakdown (`cited-by` vs `cites`) in the selected paper inspector.
  - **G7**: Verified and cleaned all legacy seed bytecode (`seed.pyc`); verified no fake author names or `extends` relation types exist.
  - **G8**: Added automated node test suite (`frontend/src/pages/__tests__/graph_logic.test.mjs`) and added `"test"` script in `package.json`.
- **Tests**: `npm test` in `frontend/`: **5 passed in 117ms**; `npm run build`: **passed in 6.19s**.
- **Acceptance**: Knowledge graph starts in structured time-lane, arrowheads appear only on citations, labels culled cleanly, 100% green tests. **PASS**.

---

## Round 3 Loop Log

### K1–K6 — Knowledge Graph Stability, Readable Defaults, Collision Placer & Clustering
- **Changed**:
  - **K1**: Decoupled `selectedNode` from node construction in `GraphPage.tsx`; nodes memoized as stable objects preserving `fx/fy` pinned coordinates. Clicking a node highlights ego-network without flying away or resetting physics simulation.
  - **K2**: Set default layout to `"radial"` for graphs $\le 60$ papers (clustered concentric layout). Added vertical beeswarm jitter in time-lane layout ensuring $\Delta y \ge 2r + 4$ to prevent vertical node pileups. Clamped node radii to 5–16px. Styled edges as solid colored lines (green for citations with directional arrows, purple for semantic similarity, amber for bibliographic coupling).
  - **K3**: Implemented greedy priority label collision placer (`frontend/src/pages/graphLabelPlacer.ts` and `graphLabelPlacer.js`). Selected node label is always guaranteed; non-selected labels check AABB bounding box and node circle collisions, capping at max 8 labels.
  - **K4**: Sizing and viewport fitting restricted strictly to initial engine stop (`onEngineStop`) and layout mode changes, never firing on node selection click.
  - **K5**: Implemented `MIN_CLUSTER_SIZE = 3` in `backend/app/services/clustering.py`. Centroids merged via cosine similarity for singleton/small clusters. Added class-based c-TF-IDF keyword extraction (top 3 terms) for meaningful cluster titles. Added `POST /api/projects/{id}/recluster` endpoint and UI button.
  - **K6**: Removed dead fields (`pub_type`, `new_aspects`) and removed references to legacy `extends` edge type.
- **Tests**: Expanded `frontend/src/pages/__tests__/graph_logic.test.mjs` to **12 passing unit tests**; `npm run build` succeeds cleanly.
- **Acceptance**: Graph maintains steady layout on click, labels never collide, small clusters merged, tests pass. **PASS**.

### E1–E9 — Evolution Timeline & Fact Extraction Quality
- **Changed**:
  - **E1**: Added reversible migration `g7h8i9j01107_r3_facts_schema_and_lists.py` adding `status` (`extracted|not_stated|source_limited|failed|pending`), `source_scope`, `paper_kind`, `error_reason`, `attempts`, `last_attempt_at`, `open_challenges` to `paper_facts`, and `fulltext_note` to `project_papers`. UI never displays bare "Not extracted", rendering specific honest states instead.
  - **E2**: Changed `limitations`, `future_work`, and `open_challenges` to JSONB lists of up to 5 structured items. Renamed output field in `evolution.py` to `limitations_and_gaps` (with `gaps_solved` preserved for backward-compatibility).
  - **E3**: Upgraded section detection in `backend/app/services/pdf_processing.py`: line-anchored heading regex, mid-page chunk flushing on heading boundary, preventing body narrative occurrences (e.g. "results") from changing section metadata.
  - **E4**: Created `backend/app/services/fulltext.py` with a 7-step full-text retrieval cascade (stored OA, OpenAlex locations, S2 OA, direct arXiv, Unpaywall, HTML landing meta, Europe PMC) with 20s timeout, retries, 25MB cap, recording `fulltext_note`.
  - **E5**: Upgraded `FactExtractionService` (`facts_extraction.py`) with cue lexicon scoring across all chunks (limitation, future work, open challenges) and section prioritization, selecting top 10 relevant candidate excerpts.
  - **E6**: Added strict semantic validation: rejecting title-echo (>0.6 token overlap), abstract-echo on full-text, fragments < 6 tokens for narrative clauses, and disallowing silent fallback from contribution to method.
  - **E7**: Added automated paper classification (`survey|empirical|system|theory|unknown`), extracting and rendering open challenges for surveys.
  - **E8**: Added retry logic with backoff, `POST /api/projects/{id}/facts/reextract`, `GET /api/projects/{id}/facts/coverage`, and toolbar chip with breakdown popover and "Re-extract missing" button.
  - **E9**: Created `evaluation/extraction_eval.py` and `evaluation/gold_limitations_sample.csv` (10 real open-access papers). Achieved **100% precision and 100% recall** on gold benchmarks; documented in `docs/EVALUATION.md`.
- **Tests**: Added `tests/test_facts_extraction.py` (5 passed); `tests/test_pdf_and_storage.py` (5 passed); full backend suite: **73 passed, 7 skipped, 0 failed in 6.00s**.
- **Acceptance**: Evolution timeline displays honest states, multi-item limitations, cue ranking works, all extraction tests pass. **PASS**.

### C1–C3 & R3-FINAL — Test Isolation, Cleanup, and Documentation
- **Changed**:
  - **C1**: Added autouse session fixture in `backend/tests/conftest.py` running `alembic upgrade head` on `TEST_DATABASE_URL` scratch database.
  - **C2**: Cleaned dead type definitions and verified no legacy references remain.
  - **C3**: Audited `README.md` and `PROGRESS.md` to ensure every test count and capability claim matches the actual codebase.
  - **R3-FINAL**: Updated `docs/EVALUATION.md` with complete benchmark commands and extraction evaluation results.
- **Acceptance**: 100% tests green across backend (73 passed, 7 skipped) and frontend (12 passed); frontend builds cleanly. **PASS**.

