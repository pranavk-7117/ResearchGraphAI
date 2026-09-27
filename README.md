# Research Graph AI 📚🔬

A full-stack scientific research paper management and intelligence system combining a **relational database catalog**, an **in-memory knowledge graph engine**, **PDF ingestion with automatic Downloads storage**, **FAISS vector search**, and a **grounded zero-hallucination RAG assistant**.

---

## 🌟 Key Features

1. **Relational Database Catalog & DBMS Inspector**:
   - Supports both **Local SQLite** (zero configuration) and **PostgreSQL / Supabase** (cloud DBMS with pooling and pre-ping).
   - Fully normalized 3NF relational schema: `papers`, `keywords`, `paper_keywords` (M:N associative table), `edges`, `paper_chunks`, and `chat_history`.
   - **Interactive In-App SQL Console**: Run live `SELECT`, `JOIN`, and aggregation queries directly from the frontend with sub-millisecond execution reporting.
2. **Grounded Anti-Hallucination RAG Engine**:
   - Combines FAISS dense vector search over paper passages with SQL lexical matching.
   - Enforces strict factual context bounding: answers are synthesized strictly from retrieved paper chunks and cited with `[Paper Title]`.
   - Provider flexibility: Supports **OpenAI**, **Google Gemini**, **Groq**, or **Smart Local Dynamic Extraction** (no external API key required).
3. **Automatic Research Paper Storage in Downloads**:
   - Every PDF uploaded via the Upload portal is automatically ingested and preserved in the user's local `Downloads` folder (`C:\Users\<User>\Downloads`).
4. **Interactive Knowledge Graph & Lineage Engine**:
   - Directed force-directed graph powered by BFS, DFS, and unweighted shortest-path pathfinding.
   - Topological sorting of paper extension lineages with cycle detection and cycle breaking.
   - Research gap analysis with connected component clustering and missing citation discovery.

---

## 🏗️ Architecture & DBMS Schema

```
┌────────────────────────────────────────────────────────┐
│                        React UI                        │
│  (Upload | Graph | Gaps | Evolution | Chat | Database) │
└───────────────────────────┬────────────────────────────┘
                            │ REST API
┌───────────────────────────▼────────────────────────────┐
│                    FastAPI Backend                     │
├────────────────────────────────────────────────────────┤
│ • Features & Graph Engine (BFS/DFS, Dijkstra/Shortest) │
│ • Vector Store (FAISS IndexFlatIP + Cosine Similarity) │
│ • Grounded RAG Synthesizer (OpenAI / Gemini / Local)   │
│ • PDF Parser & Downloads Storage (PyMuPDF + Fitz)      │
└───────────────────────────┬────────────────────────────┘
                            │ SQLAlchemy 2.0
┌───────────────────────────▼────────────────────────────┐
│        Relational Database (SQLite / Supabase)         │
├────────────────────────────────────────────────────────┤
│ • papers (id, title, authors, abstract, year, text)    │
│ • keywords (id, text)                                  │
│ • paper_keywords (paper_id, keyword_id) [M:N Join]     │
│ • edges (source_id, target_id, edge_type, confidence)  │
│ • paper_chunks (paper_id, chunk_index, text, embedding)│
│ • chat_history (question, answer, cited_paper_ids)     │
└────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Setup & Run

### 1. Backend Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload
```

### 2. Frontend Setup

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

---

## 🗄️ Database Options: SQLite vs. Supabase (PostgreSQL)

The system automatically switches between **SQLite** and **Supabase (PostgreSQL)** based on the `DATABASE_URL` environment variable:

### Option A: Local SQLite (Default)
No setup required. The application automatically creates `backend/research_graph.db`.

### Option B: Supabase (PostgreSQL)
To connect to Supabase:
1. Create a free project at [supabase.com](https://supabase.com).
2. Go to **Project Settings** -> **Database** and copy your **URI connection string** (`postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres`).
3. Set your environment variable:
   ```powershell
   $env:DATABASE_URL="postgresql://postgres:your_password@db.your_ref.supabase.co:5432/postgres"
   ```
4. Run the seeder to populate tables and initial research corpus:
   ```powershell
   python -m app.seed
   ```
5. Start your backend! You can now view live data in both Supabase Studio and the in-app **Database** tab.

---

## 🤖 LLM & RAG Configuration

The RAG chat engine supports multiple providers:

- **Local Dynamic (Default)**: Zero-hallucination dynamic context extraction & citation generation. No API key required.
- **OpenAI**:
  ```powershell
  $env:LLM_PROVIDER="openai"
  $env:OPENAI_API_KEY="sk-..."
  ```
- **Google Gemini**:
  ```powershell
  $env:LLM_PROVIDER="gemini"
  $env:GEMINI_API_KEY="AIza..."
  ```
- **Groq (Fast Llama 3.3)**:
  ```powershell
  $env:LLM_PROVIDER="groq"
  $env:GROQ_API_KEY="gsk_..."
  ```

---

## 🧪 Testing

Run automated tests covering graph algorithms, database queries, grounded RAG synthesis, and file downloads:

```powershell
cd backend
python -m pytest
```
