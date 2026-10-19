import os
from pathlib import Path
import time
from collections.abc import Generator
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Load environment variables from backend/.env or root .env
BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR.parent / ".env")

RAW_DATABASE_URL = os.getenv("DATABASE_URL")

if not RAW_DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is not configured. "
        "Please provide a Supabase Postgres connection string in backend/.env"
    )

# Normalize Postgres URLs (e.g. postgres:// -> postgresql://)
if RAW_DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = RAW_DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = RAW_DATABASE_URL

if DATABASE_URL.startswith("sqlite"):
    raise RuntimeError(
        "SQLite database engine is disabled in production. "
        "ResearchGraphAI requires Supabase PostgreSQL with the pgvector extension."
    )

# Supabase PostgreSQL configuration with connection pooling and pre-ping
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


def init_db() -> None:
    """Ensure pgvector extension exists and initialize all database tables and extensions."""
    from app import models  # noqa: F401

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()

    Base.metadata.create_all(bind=engine)

    # Idempotent additive column migrations for PostgreSQL
    if engine.dialect.name == "postgresql":
        alter_statements = [
            "ALTER TABLE papers ADD COLUMN IF NOT EXISTS workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE;",
            "ALTER TABLE papers ADD COLUMN IF NOT EXISTS doi VARCHAR(255);",
            "ALTER TABLE papers ADD COLUMN IF NOT EXISTS external_id VARCHAR(255);",
            "ALTER TABLE papers ADD COLUMN IF NOT EXISTS citation_count INTEGER DEFAULT 0;",
            "ALTER TABLE papers ADD COLUMN IF NOT EXISTS venue VARCHAR(255);",
            "ALTER TABLE papers ADD COLUMN IF NOT EXISTS url TEXT;",
            "ALTER TABLE papers ADD COLUMN IF NOT EXISTS pdf_url TEXT;",
            "ALTER TABLE papers ADD COLUMN IF NOT EXISTS tldr TEXT;",
            "ALTER TABLE papers ADD COLUMN IF NOT EXISTS is_user_paper BOOLEAN DEFAULT FALSE;",
            "ALTER TABLE edges ADD COLUMN IF NOT EXISTS workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE;",
            "ALTER TABLE paper_chunks ADD COLUMN IF NOT EXISTS workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE;",
            "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE;",
            "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
        ]
        with engine.begin() as conn:
            for stmt in alter_statements:
                try:
                    conn.execute(text(stmt))
                except Exception:
                    pass


def get_db_info(db: Session) -> dict[str, Any]:
    """Retrieve DBMS metadata, table metrics, and schema information."""
    from app import models

    dialect_name = engine.dialect.name
    inspector = inspect(engine)

    table_models = {
        "workspaces": models.Workspace,
        "papers": models.Paper,
        "keywords": models.Keyword,
        "paper_keywords": models.PaperKeyword,
        "edges": models.Edge,
        "paper_chunks": models.PaperChunk,
        "paper_facts": models.PaperFact,
        "jobs": models.Job,
        "chat_history": models.ChatHistory,
    }

    tables_info = []
    total_records = 0

    for name, model_cls in table_models.items():
        try:
            count = db.query(model_cls).count()
        except Exception:
            count = 0
        total_records += count

        cols = []
        try:
            for col in inspector.get_columns(name):
                cols.append({
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                    "primary_key": bool(col.get("primary_key", False)),
                })
        except Exception:
            pass

        fks = []
        try:
            for fk in inspector.get_foreign_keys(name):
                fks.append({
                    "constrained_columns": fk.get("constrained_columns", []),
                    "referred_table": fk.get("referred_table", ""),
                    "referred_columns": fk.get("referred_columns", []),
                })
        except Exception:
            pass

        tables_info.append({
            "table_name": name,
            "row_count": count,
            "columns": cols,
            "foreign_keys": fks,
        })

    # Mask connection URL for security
    masked_url = str(engine.url)
    if engine.url.password:
        masked_url = masked_url.replace(engine.url.password, "********")

    return {
        "engine": dialect_name,
        "is_sqlite": False,
        "database_url_masked": masked_url,
        "total_tables": len(tables_info),
        "total_records": total_records,
        "tables": tables_info,
        "pool_status": {
            "pool_size": getattr(engine.pool, "size", lambda: 1)(),
            "checkedin": getattr(engine.pool, "checkedin", lambda: 0)(),
            "checkedout": getattr(engine.pool, "checkedout", lambda: 0)(),
        },
    }


def execute_read_only_query(db: Session, raw_sql: str) -> dict[str, Any]:
    """Safely execute a read-only query for interactive DBMS exploration."""
    cleaned = raw_sql.strip()
    first_word = cleaned.split()[0].upper() if cleaned.split() else ""

    allowed_prefixes = ("SELECT", "WITH", "EXPLAIN")
    if first_word not in allowed_prefixes:
        raise ValueError("Only read-only queries (SELECT, WITH, EXPLAIN) are permitted.")

    start_time = time.perf_counter()
    result = db.execute(text(cleaned))
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    columns = list(result.keys()) if result.returns_rows else []
    rows = []
    if result.returns_rows:
        for row in result.fetchmany(100):
            row_dict = {}
            for col, val in zip(columns, row):
                row_dict[col] = str(val) if val is not None else None
            rows.append(row_dict)

    return {
        "query": cleaned,
        "execution_time_ms": duration_ms,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
    }
