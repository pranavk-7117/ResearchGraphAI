"""
Tests for T5: Side-Effect Free GET /gaps, Async POST /gaps/detect Job,
and DB Unique Constraint on (project_id, corpus_version, statement_hash).
"""

import hashlib
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy.exc import IntegrityError

from app import models
from app.api.routes import detect_gaps_job, get_gaps
from app.auth import AuthenticatedUser
from app.database import SessionLocal


def test_get_gaps_is_strictly_read_only():
    """GET /projects/{id}/gaps must never mutate DB or trigger gap detection."""
    db = MagicMock()
    proj = MagicMock(id=5, user_id="u1")
    db.query.return_value.filter.return_value.first.return_value = proj
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    with patch("app.api.routes.GapsService") as mock_gaps_cls:
        out = get_gaps(project_id=5, user=AuthenticatedUser(id="u1"), db=db)
        assert out == []
        mock_gaps_cls.assert_not_called()
        db.commit.assert_not_called()
        db.delete.assert_not_called()
        db.add.assert_not_called()


def test_post_gaps_detect_enqueues_job():
    """POST /projects/{id}/gaps/detect enqueues a gaps_detect job without blocking."""
    db = MagicMock()
    proj = MagicMock(id=5, user_id="u1")
    db.query.return_value.filter.return_value.first.return_value = proj

    with patch("app.api.routes.threading.Thread") as mock_thread:
        job_out = detect_gaps_job(project_id=5, user=AuthenticatedUser(id="u1"), db=db)
        assert job_out.type == "gaps_detect"
        assert job_out.status == "pending"
        assert job_out.project_id == 5
        mock_thread.return_value.start.assert_called_once()


def test_research_gap_unique_constraint_prevents_duplicates():
    """Live DB check: unique constraint (project_id, corpus_version, statement_hash) rejects duplicates."""
    db = SessionLocal()
    prof_id = "test-t5-gaps-user"
    if not db.query(models.Profile).filter(models.Profile.id == prof_id).first():
        db.add(models.Profile(id=prof_id, email="t5@test.com"))
        db.commit()

    proj = models.ResearchProject(user_id=prof_id, topic="T5 Unique Constraint Test", corpus_version=1)
    db.add(proj)
    db.commit()
    db.refresh(proj)

    try:
        stmt = "Limited longitudinal evaluation across patient cohorts."
        shash = hashlib.sha256(stmt.strip().lower().encode("utf-8")).hexdigest()

        g1 = models.ResearchGap(
            project_id=proj.id, corpus_version=1, statement_hash=shash,
            gap_statement=stmt, why_it_matters="W1", gap_type="evaluation_void",
            corpus_cannot_establish="C1", suggested_research_question="Q1",
            suggested_validation="V1", evidence_strength=0.7,
        )
        db.add(g1)
        db.commit()

        g2 = models.ResearchGap(
            project_id=proj.id, corpus_version=1, statement_hash=shash,
            gap_statement=stmt, why_it_matters="W2", gap_type="evaluation_void",
            corpus_cannot_establish="C2", suggested_research_question="Q2",
            suggested_validation="V2", evidence_strength=0.6,
        )
        db.add(g2)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.delete(proj)
        db.commit()
        db.close()
