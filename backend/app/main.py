import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
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

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    index_path = FRONTEND_DIST / "index.html"
    requested_path = FRONTEND_DIST / full_path
    if full_path and requested_path.is_file():
        return FileResponse(requested_path)
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Frontend build not found. Run `npm run build` in frontend."}
