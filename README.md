# ResearchGraphAI

> Evidence-Grounded AI Research Discovery & Scholarly Knowledge Graph Platform

ResearchGraphAI is a production-quality research intelligence platform that guides students and researchers from an inquiry topic to a rigorous, source-attributed understanding of a scientific field.

Unlike generic chatbot summarizers or synthetic demonstration apps, **ResearchGraphAI operates with strictly zero fabricated content, zero hardcoded domain templates, and zero synthetic paper seeding**. Every claim, gap statement, evolution transition, and chat response traces directly to verified academic citations and stored full-text passages.

---

## 1. Core Workflow & Capabilities

```mermaid
flowchart LR
    A[Topic Inquiry] --> B[Multi-Source Discovery<br/>OpenAlex, S2, arXiv]
    B --> C[Ranked Candidates<br/>Vector Sim + Recency + Citations]
    C --> D[User Selection]
    D --> E[Durable Background Worker<br/>PDF Ingest + PyMuPDF Page Extraction]
    E --> F[Idempotent pgvector Chunking<br/>all-MiniLM-L6-v2]
    F --> G[Knowledge Graph<br/>Citation vs Inferred Edges]
    G --> H[Thematic Clusters<br/>Agglomerative Clustering]
    H --> I[Evolution Chain & Literature Review]
    I --> J[Evidence-Grounded Gaps Engine]
    J --> K[Attributed RAG Chat & Manuscript Assessment]
```

1. **Academic Paper Discovery (Decoupled from Ingestion)**: Queries OpenAlex, Semantic Scholar, and arXiv in parallel. Ranks candidates using multi-factor normalized scoring (dense vector similarity, recency decay, log-scaled citations, open-access status) with transparent "Why Ranked" breakdowns.
2. **Durable Processing Pipeline**: Asynchronous background jobs backed by PostgreSQL (`SELECT ... FOR UPDATE SKIP LOCKED`). Downloads legal open-access PDFs, extracts page-by-page text with PyMuPDF, detects sections, and flags OCR-needed/image-only scans explicitly.
3. **Idempotent pgvector Embeddings**: Dense 384-dimensional vector embeddings (`all-MiniLM-L6-v2` or OpenAI) indexed via HNSW cosine ops with unique text hash constraints.
4. **Knowledge Graph with Distinct Edge Types**: Visually and semantically distinguishes verified citation linkages (`basis: citation_metadata`) from inferred semantic similarities (`basis: embedding_similarity`).
5. **Algorithmic Thematic Clustering**: Agglomerative clustering over document vectors with LLM-synthesized cluster labels grounded in member evidence.
6. **Tri-Perspective Evolution Engine**:
   - *Verified Citation Timeline*: Grounded along recorded citation lineages.
   - *Method & Metric Progression*: Chronological diffs across models, algorithms, and benchmark datasets.
   - *Finding Dynamics*: Documents whether subsequent papers confirm, extend, or contradict earlier findings.
7. **Transparent Research Gap Engine**: Detects recurring limitations and evaluation voids across papers. Assigns a formula-based evidence score, conducts targeted external verification against OpenAlex, and includes clear limitation disclosures on what the corpus cannot prove.
8. **Attributed RAG Chat**: Hybrid retrieval combining dense vector cosine similarity and full-text SQL matching with Reciprocal Rank Fusion (RRF). Answers structured as *Evidence* (with verbatim quotes and page numbers), *Interpretation*, and *Suggestions*.
9. **Manuscript Comparison & Gap Benchmarking**: Upload your own research draft to evaluate claimed contributions, detect missing related citations, and analyze semantic distance relative to the project corpus.

---

## 2. Database Schema (Supabase PostgreSQL + pgvector)

```mermaid
erDiagram
    PROFILES ||--o{ RESEARCH_PROJECTS : owns
    RESEARCH_PROJECTS ||--o{ PROJECT_PAPERS : contains
    PAPERS ||--o{ PROJECT_PAPERS : included_in
    PAPERS ||--o{ PAPER_CHUNKS : chunked_into
    PAPERS ||--o{ PAPER_FACTS : extracts
    PAPERS ||--o{ PAPER_DOCUMENTS : stored_in
    PAPERS ||--o{ PAPER_REFERENCES : cites
    RESEARCH_PROJECTS ||--o{ PAPER_RELATIONS : connects
    RESEARCH_PROJECTS ||--o{ RESEARCH_CLUSTERS : groups
    RESEARCH_CLUSTERS ||--o{ CLUSTER_MEMBERS : contains
    RESEARCH_PROJECTS ||--o{ RESEARCH_GAPS : formulates
    RESEARCH_PROJECTS ||--o{ EVOLUTION_TRANSITIONS : traces
    RESEARCH_PROJECTS ||--o{ LITERATURE_REVIEWS : compiles
    RESEARCH_PROJECTS ||--o{ CHAT_SESSIONS : records
    CHAT_SESSIONS ||--o{ CHAT_MESSAGES : logs
    RESEARCH_PROJECTS ||--o{ RESEARCH_JOBS : runs
```

- **`papers`**: Global, deduplicated academic metadata indexed by DOI, OpenAlex ID, Semantic Scholar ID, and title hash.
- **`paper_chunks`**: Page-level and section-level chunk passages with `vector(384)` HNSW indexing and unique `(paper_id, text_hash, embedding_model)` constraints.
- **`paper_facts`**: Structured scientific extractions (problem, method, dataset, metrics, results, limitations) with verbatim quotes and page attribution.
- **`paper_relations`**: Graph edges with explicit `basis` (`citation_metadata` vs `embedding_similarity`).
- **`research_gaps`**: Candidate gaps with transparent scoring formulas and OpenAlex verification.

---

## 3. Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+ & npm
- A Supabase Project with PostgreSQL and the `pgvector` extension enabled.

### 1. Configure Backend Environment
Copy `backend/.env.example` to `backend/.env` and provide your credentials:

```bash
cd backend
cp .env.example .env
```

Key variables:
- `DATABASE_URL`: Supabase IPv4 connection pooler URI (`postgresql://postgres.[REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres?sslmode=require`)
- `SUPABASE_URL` & `SUPABASE_SERVICE_ROLE_KEY`: Supabase credentials for private object storage.
- `LLM_PROVIDER`: `groq`, `openai`, `anthropic`, or `gemini`.
- `GROQ_API_KEY`: API key if using Groq (e.g. `qwen/qwen3.8-27b`).
- `OPENALEX_MAILTO`: Your email for the OpenAlex polite API pool.

### 2. Database Migrations
Run versioned Alembic migrations to create the schema and pgvector indexes:

```bash
cd backend
alembic upgrade head
```

*(Optional safety utility: `python scripts/reset_database.py --yes-i-am-sure` drops all tables if starting over from a clean slate.)*

### 3. Start Backend API & Worker
Terminal 1 (FastAPI Server):
```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Terminal 2 (Durable Background Worker):
```bash
cd backend
python -m app.worker
```

### 4. Start Frontend
```bash
cd frontend
npm install
npm run dev -- --port 5174
```

Open `http://localhost:5174` in your browser.

---

## 4. Empirical Evaluation & Tests

### Automated Test Suite
Run the full pytest suite (15 unit and integration tests covering JWT auth, cross-user denial, PDF parsing, OCR detection, deduplication, ranking, citation resolution, gap scoring, and worker locks):

```bash
cd backend
python -m pytest tests/ -v
```

### Discovery & Relevance Benchmark
Execute the automated evaluation script across 3 representative disciplines (Materials Science, NLP, Genetics):

```bash
python evaluation/evaluate.py
```
Outputs empirical yield, deduplication rates, full-text availability, and vector cosine distributions in `evaluation/results.json`.

---

## 5. Deployment (Render & Supabase)

`render.yaml` defines two production services:
1. **Web Service**: Runs FastAPI with Gunicorn/Uvicorn, serves the compiled React production bundle, and executes `alembic upgrade head` on build.
2. **Background Worker**: Continuously polls for queued research jobs using PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED`.

---

## 6. Limitations & Scientific Disclaimers

- **Corpus Boundaries**: Underrepresentation or lack of evidence in a project corpus represents a candidate hypothesis within the retrieved literature—it does not prove absolute absence in the global scientific record.
- **Open Access Reliance**: While metadata is indexed globally, full-text passage extraction depends on legal open-access PDF availability (Gold/Green OA or arXiv). When a publisher retains closed access, the system operates at the abstract level and marks the paper accordingly.
