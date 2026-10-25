"""
FastAPI Application Entry Point for ResearchGraphAI.

Configures:
- Async lifespan event handler
- Comprehensive /health check with PostgreSQL and pgvector verification
- CORS middleware with strict origin whitelist
- API routes mounted at /api
- Frontend static asset serving without masking API 404s
"""

from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.api.routes import router
from app.database import check_db_health, get_db
from app import schemas


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: test database connection and pgvector extension
    db = next(get_db())
    try:
        health_status = check_db_health(db)
        print(f"[ResearchGraphAI] Startup DB Check: {health_status}")
    finally:
        db.close()
    yield
    # Shutdown logic if needed


app = FastAPI(
    title="ResearchGraphAI API",
    description="Evidence-Grounded AI Research Discovery & Knowledge Graph Platform",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS Configuration
default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]
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


@app.get("/health", response_model=schemas.HealthOut)
@app.get("/api/health", response_model=schemas.HealthOut)
def health_check(db: Session = Depends(get_db)):
    """Health check verifying database connectivity and pgvector extension presence."""
    info = check_db_health(db)
    if not info.get("database_connected"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed: {info.get('error')}",
        )
    return schemas.HealthOut(
        ok=True,
        database_connected=info["database_connected"],
        pgvector_installed=info.get("pgvector_installed", False),
        pgvector_version=info.get("pgvector_version"),
        engine=info.get("engine", "postgresql"),
    )


app.include_router(router, prefix="/api")

# Static frontend serving
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
              body { font-family: system-ui, sans-serif; margin: 0; padding: 48px; background: #f8fafc; color: #0f172a; }
              main { max-width: 720px; background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 28px; }
              a { color: #2563eb; }
            </style>
          </head>
          <body>
            <main>
              <h1>ResearchGraphAI API is live</h1>
              <p>The backend is active on Supabase PostgreSQL with pgvector.</p>
              <p><a href="/docs">OpenAPI Documentation</a> · <a href="/health">Health Status</a></p>
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
def serve_frontend_catchall(full_path: str):
    # Ensure API paths that 404 do not return the HTML frontend
    if full_path.startswith("api/"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API endpoint '/{full_path}' not found",
        )

    requested_path = FRONTEND_DIST / full_path
    if full_path and requested_path.is_file():
        return FileResponse(requested_path)
    return frontend_response()
