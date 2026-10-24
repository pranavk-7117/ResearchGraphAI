"""
Tests for Authentication, Supabase JWT verification, and Project Ownership Isolation.
"""

import pytest
from fastapi import HTTPException

from app.auth import (
    AuthenticatedUser,
    verify_project_ownership,
    verify_supabase_jwt,
)
from app.database import SessionLocal
from app import models


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_cross_user_access_denial(db):
    """Verify that User A cannot read or delete User B's research project."""
    # Ensure User A profile and project
    user_a = AuthenticatedUser(id="user-a-1111-2222", email="user_a@test.com")
    prof_a = db.query(models.Profile).filter(models.Profile.id == user_a.id).first()
    if not prof_a:
        prof_a = models.Profile(id=user_a.id, email=user_a.email)
        db.add(prof_a)
        db.commit()

    proj_a = models.ResearchProject(user_id=user_a.id, topic="Quantum Cryptography")
    db.add(proj_a)
    db.commit()
    db.refresh(proj_a)

    # Ensure User B
    user_b = AuthenticatedUser(id="user-b-3333-4444", email="user_b@test.com")
    prof_b = db.query(models.Profile).filter(models.Profile.id == user_b.id).first()
    if not prof_b:
        prof_b = models.Profile(id=user_b.id, email=user_b.email)
        db.add(prof_b)
        db.commit()

    # User A can access their project
    retrieved = verify_project_ownership(proj_a.id, user_a, db)
    assert retrieved.id == proj_a.id

    # User B MUST be denied access (raises 404 to avoid leaking existence)
    with pytest.raises(HTTPException) as exc_info:
        verify_project_ownership(proj_a.id, user_b, db)
    assert exc_info.value.status_code == 404

    # Cleanup
    db.delete(proj_a)
    db.commit()


def test_invalid_jwt_rejection():
    """Verify malformed or invalid JWT tokens are rejected."""
    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_jwt("malformed.jwt")
    assert exc_info.value.status_code == 401
