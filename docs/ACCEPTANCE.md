# Acceptance Criteria

### T1. Database foundation (Supabase Postgres + pgvector)
- **Engine**: Postgres-only engine initialized from `DATABASE_URL` with `pool_pre_ping=True`, sensible pool size for Supabase pooler (e.g. `pool_size=10`, `max_overflow=20`), and a clear startup error if the URL is missing or unreachable. No SQLite fallback in production code.
- **Migrations**: Alembic or idempotent migration runner creating all tables; `CREATE EXTENSION IF NOT EXISTS vector;`.
- **Vector Storage**: Embeddings stored in `vector(384)` columns with a cosine HNSW index (`vector_cosine_ops`); `vector_store.py` executes similarity search directly in SQL (`ORDER BY embedding <=> :query_vec`). FAISS and JSON-text embeddings removed.
- **Embedding Model**: Real embedding model: `sentence-transformers` `all-MiniLM-L6-v2` (lazy-loaded, cached); optional OpenAI via env. Keep hash embedding only as test fake.
- **Environment**: `python-dotenv` loading, `.env.example` (no real secrets), and `.env` in `.gitignore`.
- **ACCEPT**:
  1. Migration runs twice with no error (idempotent).
  2. A script/test inserts a row with an embedding and a nearest-neighbour query returns it.
  3. Semantically related phrases ("diabetes", "blood glucose") score higher than unrelated ones in a test.
  4. App boots cleanly against Supabase.

---

### T2. Workspaces + schema extensions
- **Workspaces**: `workspaces` table (`id`, `topic`, `status`, `expanded_queries` JSON, `created_at`). `workspace_id` foreign key on `papers`, `edges`, `chunks`, `chat_history`. All existing endpoints scoped by workspace.
- **Paper Extensions**: `papers`: `doi`, `external_id`, `citation_count`, `venue`, `url`, `pdf_url`, `tldr`, `is_user_paper`.
- **Paper Facts**: `paper_facts` table (`task`, `method`, `dataset`, `population`, `metric`, `result_summary`, `limitation`, `future_work`, `evidence_sentence`, `confidence`).
- **Jobs**: `jobs` table (`type`, `status`, `progress`, `message`, `error`).
- **ACCEPT**:
  1. Two workspaces with different topics stay fully isolated (test proves it).
  2. Migrations are additive and idempotent.
  3. Existing upload flow still works properly inside a workspace.

---

### T3. Topic discovery pipeline (services/discovery.py)
- **Job Endpoint**: `POST /workspaces` `{topic, max_papers}` starts background job; `GET /jobs/{id}` reports progress and errors.
- **Expansion**: LLM query expansion to 4-6 queries (fallback to raw topic).
- **APIs**: Fetch from OpenAlex (primary, with mailto), plus Semantic Scholar and arXiv/PubMed; retries with exponential backoff; every raw response cached on disk keyed by query.
- **Deduplication & Ranking**: Dedupe by DOI then fuzzy title; rank by semantic relevance blended with citation count; keep top `max_papers`.
- **Ingestion**: Ingest abstract + metadata; fetch open-access PDFs when available; missing PDF never fails the job.
- **Graph Edges**: Citation edges from real reference lists (only between papers in the workspace); similarity edges via configurable threshold.
- **Pre-seeding**: `scripts/seed_demo_topics.py` pre-fetches and caches 2-3 topics including "AI in diabetic healthcare".
- **ACCEPT**:
  1. Running the topic "AI in diabetic healthcare" against the real APIs yields at least 25 distinct real papers with titles, years, abstracts, and DOIs.
  2. Zero duplicate DOIs.
  3. At least some real citation edges.
  4. A second run is served from disk cache with zero network calls.
  5. Tests with mocked HTTP cover deduplication, ranking, backoff, and edge building.

---

### T4. Structured extraction + evidence-backed gap analysis
- **Extraction**: LLM extraction into `paper_facts` via a pydantic-validated JSON schema, batched, cached, retried; heuristic fallback marked low-confidence.
- **Gap Analysis**: Rebuilt on `paper_facts`: method x task and method x population/data-type matrices, sparse/empty cells, recurring limitations, future-work statements with no later paper addressing them. Each gap includes evidence (paper titles + source sentence). Keep old structural graph gaps as secondary section.
- **Research Fronts**: Research-front detection: concept counts per year, rising vs declining.
- **ACCEPT**:
  1. On the demo workspace, gap endpoint returns at least 5 gaps.
  2. Each gap has at least one evidence sentence that actually appears in a stored abstract or full text (asserted by substring match test).
  3. Matrix endpoint returns non-empty structured data.

---

### T5. Evolution chain upgrade
- **Clustering**: Cluster papers into method families (embedding clustering + LLM labels).
- **Lineage**: Time-sliced lineage with LLM-grounded explanation per consecutive pair using only those two papers' stored text.
- **Ordering**: Topological ordering as the backbone; prerequisite-ordered reading plan.
- **Endpoint**: Returns timeline data: nodes (year, cluster, citation_count) and labelled edges.
- **ACCEPT**:
  1. Chain for demo workspace is ordered by year and lineage with no cycles.
  2. Each step explanation references terms found in both papers (test verified).
  3. Reading plan puts high-centrality foundational papers first.

---

### T6. Compare against my paper
- **Upload**: `POST /workspaces/{id}/my-paper` (PDF upload or pasted title+abstract[+text]); mark `is_user_paper`, embed, extract facts.
- **Compare Endpoint**: `GET /workspaces/{id}/compare` returns:
  - Nearest neighbours with scores.
  - Side-by-side facts table versus top N.
  - Novelty analysis (what is new vs overlapping).
  - Suggested papers to cite.
  - Novelty score with the formula and inputs shown.
  - Reviewer-style critique tied to evidence. If evidence is insufficient, explicitly say so.
- **ACCEPT**:
  1. Test with a user abstract close to a known cluster returns that cluster's papers as nearest neighbours.
  2. Novelty score is deterministic for the same inputs.
  3. Every critique point cites a stored paper or sentence.

---

### T7. Extra analysis + exports
- **Metrics**: PageRank and betweenness (bridge papers); foundational vs recent labels; dataset/benchmark tracker.
- **Related Work**: Auto-generated Related Work section with in-text citations (Markdown + DOCX).
- **Exports**: BibTeX, CSV, and one-page PDF report exports.
- **Chat**: Workspace-scoped grounded RAG chat with the "no evidence" guard.
- **ACCEPT**:
  1. Each export downloads and opens correctly.
  2. BibTeX entries parse cleanly.
  3. Chat returns the guard message for an off-topic question and cited answers for an on-topic one.

---

### T8. Frontend
- **Topic Landing Screen**: Topic landing screen with live job progress; workspace switcher.
- **Graph Page**: Colour by cluster/year, size by citations, highlighted user paper, filters, time slider, detail drawer.
- **Evolution Page**: Horizontal timeline with method-family lanes and per-step explanations.
- **Gaps Page**: Heatmap of the matrix; click a gap to see its evidence.
- **Compare Page**: Upload/paste my paper, side-by-side table, novelty score, suggested citations, critique.
- **Polish**: Export buttons; visible note that analysis is abstract-level unless full text was available; loading, empty, and error states everywhere. Database tab removed from navigation sidebar.
- **ACCEPT**:
  1. `npm run build` and `npx tsc --noEmit` pass with zero errors.
  2. Walking through full flow in browser (topic -> graph -> evolution -> gaps -> upload my paper -> compare -> export) works with the demo workspace and zero console errors.
  3. Evidence recorded in `PROGRESS.md`.

---

### T9. Docs and deploy
- **Documentation**: Comprehensive README with Supabase setup (pooler string, pgvector, env vars), seeding script, and demo walkthrough.
- **Deployment**: Update `render.yaml` (Postgres env vars, build commands, embedding model cache note).
- **ACCEPT**:
  1. Following README from a clean clone gets the app running against Supabase.
