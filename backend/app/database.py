import os
from pathlib import Path
from collections.abc import Generator
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR.parent / ".env")

RAW_DATABASE_URL = os.getenv("DATABASE_URL")

if not RAW_DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is not configured. "
        "Please provide a Supabase Postgres connection pooler URI in backend/.env"
    )

if RAW_DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = RAW_DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif RAW_DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = RAW_DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
elif RAW_DATABASE_URL.startswith("postgresql+psycopg://"):
    DATABASE_URL = RAW_DATABASE_URL.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
else:
    DATABASE_URL = RAW_DATABASE_URL

if DATABASE_URL.startswith("sqlite"):
    raise RuntimeError(
        "SQLite database engine is not supported. "
        "ResearchGraphAI requires Supabase PostgreSQL with the pgvector extension."
    )

if "@db." in DATABASE_URL and ".supabase.co" in DATABASE_URL:
    print(
        "\n[ResearchGraphAI WARNING] DATABASE_URL points to direct Supabase host 'db.xxxx.supabase.co'.\n"
        "Render free tier does not support IPv6 outbound network traffic.\n"
        "Please use the Supabase IPv4 connection pooler URI instead:\n"
        "Format: postgresql://postgres.[REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres?sslmode=require\n"
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_health(db: Session) -> dict[str, Any]:
    """Verify active PostgreSQL connectivity and pgvector extension readiness."""
    try:
        # Check basic connectivity
        db.execute(text("SELECT 1;"))
        
        # Check vector extension
        res = db.execute(text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';")).fetchone()
        vector_ready = res is not None
        vector_version = res[1] if res else None
        
        return {
            "database_connected": True,
            "engine": engine.dialect.name,
            "pgvector_installed": vector_ready,
            "pgvector_version": vector_version,
        }
    except Exception as e:
        return {
            "database_connected": False,
            "error": str(e),
            "pgvector_installed": False,
        }
