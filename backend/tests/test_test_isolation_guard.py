"""
Tests for R7: Test database isolation and live-DB guard rules.
"""

from tests.conftest import is_live_db_permitted


def test_guard_rejects_supabase_without_override(monkeypatch):
    """Guard must refuse to connect to Supabase if TEST_DATABASE_URL points to Supabase without ALLOW_LIVE_TESTS=1."""
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://postgres:pass@aws-0-pooler.supabase.com/postgres")
    monkeypatch.setenv("ALLOW_LIVE_TESTS", "0")
    permitted, reason = is_live_db_permitted()
    assert permitted is False
    assert "Supabase" in reason


def test_guard_permits_local_docker_scratch_db(monkeypatch):
    """Guard permits local Docker or CI scratch database."""
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://postgres:pass@localhost:5432/researchgraph_test")
    monkeypatch.setenv("ALLOW_LIVE_TESTS", "0")
    permitted, url = is_live_db_permitted()
    assert permitted is True
    assert "researchgraph_test" in url


def test_guard_skips_when_no_db_url_configured(monkeypatch):
    """Guard skips when no test database is available to protect production."""
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("ALLOW_LIVE_TESTS", "0")
    permitted, reason = is_live_db_permitted()
    assert permitted is False
    assert "skipped" in reason.lower()
