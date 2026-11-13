"""
Pytest configuration and test database isolation for ResearchGraphAI.

Rules:
1. Tests must NEVER run against a production/live Supabase database by accident.
2. If TEST_DATABASE_URL is set (e.g. in local Docker or CI), tests connect to that scratch database.
3. If TEST_DATABASE_URL is absent and ALLOW_LIVE_TESTS != '1', all tests requiring a live database
   (@pytest.mark.live_db) are automatically skipped with an explanatory message.
"""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def pytest_configure(config):
    config.addinivalue_line("markers", "live_db: test requires a live PostgreSQL+pgvector database")
    config.addinivalue_line("markers", "fake_embeddings: test uses mock/synthetic embeddings")
    config.addinivalue_line("markers", "requires_model: test requires a local ONNX or sentence-transformer model")


def is_live_db_permitted() -> tuple[bool, str]:
    """
    Check whether running database-backed tests is currently safe and permitted.
    Returns (permitted: bool, reason_or_url: str).
    """
    test_db_url = os.getenv("TEST_DATABASE_URL", "").strip()
    prod_db_url = os.getenv("DATABASE_URL", "").strip()
    allow_live = os.getenv("ALLOW_LIVE_TESTS", "0").strip() == "1"

    if test_db_url:
        # Prevent test_db_url from pointing to Supabase unless explicitly allowed
        if "supabase" in test_db_url.lower() and not allow_live:
            return False, "TEST_DATABASE_URL points to Supabase. Set ALLOW_LIVE_TESTS=1 to override."
        return True, test_db_url

    if allow_live and prod_db_url:
        return True, prod_db_url

    return False, "Neither TEST_DATABASE_URL nor ALLOW_LIVE_TESTS=1 is set. Database tests are skipped to protect production."


def pytest_collection_modifyitems(config, items):
    permitted, reason = is_live_db_permitted()
    if not permitted:
        skip_marker = pytest.mark.skip(reason=f"Live DB test skipped: {reason}")
        for item in items:
            if "live_db" in item.keywords:
                item.add_marker(skip_marker)


@pytest.fixture(scope="session", autouse=True)
def run_alembic_migrations_on_test_db():
    """When TEST_DATABASE_URL is set, automatically run alembic upgrade head on the scratch database."""
    test_db_url = os.getenv("TEST_DATABASE_URL", "").strip()
    if not test_db_url:
        return
    permitted, _ = is_live_db_permitted()
    if not permitted:
        return

    try:
        from alembic.config import Config
        from alembic import command
        from pathlib import Path

        backend_dir = Path(__file__).resolve().parent.parent
        alembic_cfg_path = backend_dir / "alembic.ini"
        if alembic_cfg_path.exists():
            alembic_cfg = Config(str(alembic_cfg_path))
            alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)
            command.upgrade(alembic_cfg, "head")
    except Exception as e:
        pytest.fail(f"Failed to run alembic upgrade head on TEST_DATABASE_URL: {e}")


@pytest.fixture(scope="session")
def test_db_session_factory():
    permitted, url = is_live_db_permitted()
    if not permitted:
        pytest.skip(f"Live database not permitted: {url}")

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    engine = create_engine(url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return Session
