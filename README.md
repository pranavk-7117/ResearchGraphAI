# Research Graph AI

A local research paper management system that combines a relational catalog, a graph engine, PDF ingestion, vector retrieval, and RAG-style answers.

## Stack

- Backend: Python, FastAPI, SQLAlchemy, SQLite
- Vector search: FAISS when available, deterministic numpy fallback
- LLM and embeddings: OpenAI when `LLM_PROVIDER=openai` and `OPENAI_API_KEY` are set, local deterministic fallback otherwise
- Frontend: React, Vite, `react-force-graph-2d`

## Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

Optional OpenAI mode:

```powershell
$env:LLM_PROVIDER="openai"
$env:OPENAI_API_KEY="your_key"
```

## 5-Minute Demo Script

1. Start the backend and frontend, then open the Graph page.
2. Show seeded papers connected by citation, similarity, and `extends` edges.
3. Select a node and explain its connection to a distant paper.
4. Open Gap Suggestions and show the cluster suggestion plus missing citation checks.
5. Open Evolution Chain, run a topic such as `retrieval`, and show the reading plan.
6. Open Chat and ask: `How do graph methods improve research discovery?`
7. Upload a PDF from the Upload page and return to the graph to see new edges when matches are found.

## Backend Tests

```powershell
cd backend
pytest
```

The graph tests cover BFS/DFS, shortest path, and cycle breaking for topological `extends` chains.

## Free Deployment

The project is configured for a single Render web service. FastAPI serves both the `/api` routes and the built React app.

1. Push this folder to a GitHub repository.
2. Open Render, choose **New +** -> **Blueprint**, and connect the repository.
3. Render will read `render.yaml`, install backend dependencies, build the frontend, and start:

```bash
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

The app seeds the demo research corpus automatically when the hosted SQLite database is empty.

Optional hosted OpenAI mode:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key
```
