# Progress & Execution Memory

## Task List Checklist
- [x] **T1. Database foundation (Supabase Postgres + pgvector)**
  - Postgres-only engine from `DATABASE_URL` with `pool_pre_ping`, sensible pool size for Supabase pooler, clear startup error if URL is missing or unreachable.
  - Alembic / idempotent migration runner creating all tables; `CREATE EXTENSION IF NOT EXISTS vector`.
  - Embeddings stored in `vector(384)` columns with cosine HNSW index; `vector_store.py` does similarity search in SQL (`ORDER BY embedding <=> query`). Remove FAISS and JSON-text embeddings.
  - Real embedding model: `sentence-transformers` `all-MiniLM-L6-v2` (lazy-loaded, cached); optional OpenAI via env. Keep hash embedding only as test fake.
  - `python-dotenv` loading, `.env.example` (no real secrets), and `.env` in `.gitignore`.
- [ ] **T2. Workspaces + schema extensions**
  - `workspaces` (id, topic, status, expanded_queries JSON, created_at); `workspace_id` on papers, edges, chunks, chat_history; all existing endpoints scoped by workspace.
  - `papers`: doi, external_id, citation_count, venue, url, pdf_url, tldr, is_user_paper. `paper_facts` table (task, method, dataset, population, metric, result_summary, limitation, future_work, evidence_sentence, confidence). `jobs` table (type, status, progress, message, error).
- [ ] **T3. Topic discovery pipeline (services/discovery.py)**
  - `POST /workspaces` {topic, max_papers} starts background job; `GET /jobs/{id}` reports progress and errors.
  - LLM query expansion to 4-6 queries (fallback to raw topic).
  - Fetch from OpenAlex (primary, with mailto), plus Semantic Scholar and arXiv/PubMed; retries with exponential backoff; raw responses cached on disk keyed by query.
  - Dedupe by DOI then fuzzy title; rank by semantic relevance blended with citation count; keep top max_papers.
  - Ingest abstract + metadata; fetch open-access PDFs when available; missing PDF never fails job.
  - Citation edges from real reference lists (only between papers in workspace); similarity edges via configurable threshold.
  - `scripts/seed_demo_topics.py` pre-fetches and caches 2-3 topics including "AI in diabetic healthcare".
- [ ] **T4. Structured extraction + evidence-backed gap analysis**
  - LLM extraction into `paper_facts` via pydantic-validated JSON schema, batched, cached, retried; heuristic fallback marked low-confidence.
  - Gap analysis rebuilt on `paper_facts`: method x task and method x population/data-type matrices, sparse/empty cells, recurring limitations, future-work statements with no later paper addressing them. Evidence attached to every gap.
  - Research-front detection: concept counts per year, rising vs declining.
- [ ] **T5. Evolution chain upgrade**
  - Cluster papers into method families (embedding clustering + LLM labels); time-sliced lineage with LLM-grounded explanation per consecutive pair using only those two papers' stored text; topological ordering backbone; prerequisite-ordered reading plan.
  - Timeline data endpoint: nodes (year, cluster, citation_count) and labelled edges.
- [ ] **T6. Compare against my paper**
  - `POST /workspaces/{id}/my-paper` (PDF upload or pasted title+abstract[+text]); mark `is_user_paper`, embed, extract facts.
  - `GET /workspaces/{id}/compare` returns: nearest neighbours with scores; side-by-side facts table versus top N; novelty analysis; suggested citations; novelty score with formula and inputs shown; reviewer-style critique tied to evidence.
- [ ] **T7. Extra analysis + exports**
  - PageRank and betweenness (bridge papers); foundational vs recent labels; dataset/benchmark tracker; auto-generated Related Work section with in-text citations (Markdown + DOCX); BibTeX, CSV, and one-page PDF report exports; workspace-scoped grounded RAG chat with "no evidence" guard.
- [ ] **T8. Frontend**
  - Topic landing screen with live job progress; workspace switcher.
  - Graph: colour by cluster/year, size by citations, highlighted user paper, filters, time slider, detail drawer.
  - Evolution: horizontal timeline with method-family lanes and per-step explanations.
  - Gaps: heatmap of the matrix; click a gap to see its evidence.
  - Compare: upload/paste my paper, side-by-side table, novelty score, suggested citations, critique.
  - Remove Database tab from frontend sidebar as requested; export buttons; note on abstract-level vs full-text analysis; loading, empty, and error states everywhere.
- [ ] **T9. Docs and deploy**
  - README with Supabase setup (pooler string, pgvector, env vars), seeding script, demo walkthrough; update `render.yaml`.

---

## Decisions
1. **Database engine**: Strict PostgreSQL via Supabase with `pgvector` extension. Zero SQLite fallback in production code. Pure-unit tests may use test mocks/fakes where appropriate.
2. **Embeddings**: `sentence-transformers` (`all-MiniLM-L6-v2`, 384 dimensions) with lazy loading and local caching. Database stores `vector(384)` with HNSW cosine index (`vector_cosine_ops`).
3. **Vector search**: Replaces FAISS and JSON text with native PostgreSQL `<=>` operator ordered by cosine distance in SQL.
4. **Secrets**: `.env` is loaded via `python-dotenv`, excluded from git. Never print, log, or commit connection strings or API keys.
5. **Frontend Navigation**: Removed "Database" tab from navigation to meet user specifications and align Gaps/Evolution pages with user reference screenshots.

---

## Known issues
- None currently blocking. Supabase PostgreSQL with pgvector is verified active.

---

## Loop log
### Step 0: One-Time Setup
- Inspected codebase: models, database, routes, services (embeddings, vector_store, features, pdf_ingestion, llm, research_graph), schemas, main, and frontend pages.
- Generated `PROGRESS.md` and `docs/ACCEPTANCE.md`.
- Identified required libraries: `pgvector`, `sentence-transformers`, `alembic`.

### Task T1: Database Foundation (Supabase Postgres + pgvector)
1. **Plan**:
   - Install `pgvector`, `alembic`, `sentence-transformers`.
   - Resolve Supabase connection via IPv4 pooler with `sslmode=require` (avoiding IPv6 direct connection timeout).
   - Update `app/database.py` to enforce PostgreSQL engine with connection pooling, startup error on missing URL, and disable SQLite fallback.
   - Update `app/models.py` to store `vector(384)` with HNSW cosine indexes on `Paper.whole_embedding` and `PaperChunk.embedding`.
   - Update `app/services/vector_store.py` to execute cosine similarity search directly in SQL (`<=>`).
   - Update `app/services/embeddings.py` to lazy-load `all-MiniLM-L6-v2`.
   - Write automated test suite in `tests/test_t1_database.py`.
2. **Build**:
   - Implemented strict PostgreSQL engine in `app/database.py`.
   - Converted vector fields to `Vector(384)` with `vector_cosine_ops` HNSW index in `app/models.py`.
   - Implemented `search_chunks` and `search_papers` in `app/services/vector_store.py`.
   - Lazy-loaded `all-MiniLM-L6-v2` in `app/services/embeddings.py`.
   - Seeded 25 multi-domain research papers with dense embeddings into Supabase.
3. **Test**:
   - `python -m pytest tests/test_t1_database.py`: 4 passed in 22.91s.
   - `python -m pytest tests/`: 13 passed in 45.25s.
4. **Verify**:
   - Migrations ran twice idempotently without errors (`CREATE EXTENSION IF NOT EXISTS vector`).
   - Inserted row with 384-d vector, retrieved via nearest-neighbour query with score 1.0.
   - Semantic similarity: "diabetes" vs "blood glucose" (0.6651) > "diabetes" vs "quantum cosmology galaxy" (0.0874).
   - FastAPI `/health` returned 200, `/api/papers` returned 25 papers from Supabase, `/api/graph` returned 25 nodes and 50 edges, `/api/db/status` confirmed PostgreSQL engine and `is_sqlite: False`.
5. **Evaluate**:
   - Migration runs twice with no error: PASS
   - Nearest-neighbour embedding search: PASS
   - Semantic similarity relative ranking: PASS
   - App boots against Supabase: PASS
