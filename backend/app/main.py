import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.database import init_db
from app.seed import seed_if_empty

app = FastAPI(title="Research Graph AI")

default_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
configured_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins or default_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()
    seed_if_empty()


@app.get("/health")
def health():
    return {"ok": True}


app.include_router(router, prefix="/api")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
INDEX_PATH = FRONTEND_DIST / "index.html"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


def frontend_response():
    if INDEX_PATH.exists():
        return FileResponse(INDEX_PATH)
    return HTMLResponse(
        """
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>Research Graph AI</title>
            <style>
              body { font-family: system-ui, sans-serif; margin: 0; padding: 48px; background: #f4f6fb; color: #172033; }
              main { max-width: 720px; background: white; border: 1px solid #dfe7f1; border-radius: 8px; padding: 28px; }
              a { color: #2364aa; }
            </style>
          </head>
          <body>
            <main>
              <h1>Research Graph AI backend is running</h1>
              <p>The API is live, but the React frontend build was not found on this deployment.</p>
              <p>Check the Render build command and confirm it runs <code>cd frontend && npm install && npm run build</code>.</p>
              <p><a href="/health">Health check</a> · <a href="/api/graph">Graph API</a></p>
            </main>
          </body>
        </html>
        """,
        status_code=200,
    )


@app.get("/")
def serve_root():
    return frontend_response()


@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    requested_path = FRONTEND_DIST / full_path
    if full_path and requested_path.is_file():
        return FileResponse(requested_path)
    return frontend_response()
