#!/usr/bin/env python3
"""
One-off Confirmation-Gated Database Reset Script for ResearchGraphAI.

Drops existing tables and types in Supabase Postgres so migrations start from a clean slate.
Usage:
    python scripts/reset_database.py --yes-i-am-sure
"""

import argparse
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR.parent / ".env")

from sqlalchemy import create_engine, text

def main():
    parser = argparse.ArgumentParser(description="Drop all ResearchGraphAI database tables.")
    parser.add_argument(
        "--yes-i-am-sure",
        action="store_true",
        help="Confirm that you genuinely want to wipe and reset the database."
    )
    args = parser.parse_args()

    if not args.yes_i_am_sure:
        print("ERROR: Safety flag --yes-i-am-sure was not provided.")
        print("This script will DESTROY all tables and records in the configured database.")
        print("If you really intend to reset the database, run:")
        print("    python scripts/reset_database.py --yes-i-am-sure")
        sys.exit(1)

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL is not set.")
        sys.exit(1)

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    print("Connecting to database to execute wipe...")
    engine = create_engine(db_url, pool_pre_ping=True)

    tables_to_drop = [
        # New schema tables
        "chat_messages",
        "chat_sessions",
        "paper_analyses",
        "literature_reviews",
        "evolution_transitions",
        "research_gaps",
        "cluster_members",
        "research_clusters",
        "paper_facts",
        "paper_relations",
        "paper_references",
        "paper_chunks",
        "paper_documents",
        "project_papers",
        "papers",
        "research_projects",
        "profiles",
        "research_jobs",
        "alembic_version",
        # Legacy tables
        "chat_history",
        "edges",
        "paper_keywords",
        "keywords",
        "jobs",
        "workspaces",
    ]

    with engine.begin() as conn:
        # Disable triggers/FK checks temporarily or drop with CASCADE
        for table in tables_to_drop:
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE;"))
                print(f"  [x] Dropped table (if existed): {table}")
            except Exception as e:
                print(f"  [!] Note on dropping {table}: {e}")

        # Ensure vector extension is intact
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            print("  [x] Verified pgvector extension exists.")
        except Exception as e:
            print(f"  [!] Vector extension check: {e}")

    print("\nDatabase reset complete. The database is clean and ready for Alembic migrations.")

if __name__ == "__main__":
    main()
