"""
Authentication and ownership authorization for ResearchGraphAI.

Verifies Supabase Auth JWT tokens using HMAC-SHA256 (HS256) or falls back
to a default local user profile for local development and test runners.
Enforces strict server-side project ownership checks.
"""

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app import models


class AuthenticatedUser(BaseModel):
    id: str
    email: str | None = None
    role: str = "authenticated"


DEFAULT_LOCAL_USER_ID = "00000000-0000-0000-0000-000000000000"
DEFAULT_LOCAL_EMAIL = "local-researcher@researchgraph.ai"


def _decode_jwt_part(part: str) -> dict:
    padded = part + "=" * (-len(part) % 4)
    data = base64.urlsafe_b64decode(padded)
    return json.loads(data.decode("utf-8"))


def verify_supabase_jwt(token: str) -> dict:
    """Verify Supabase JWT signature and expiration."""
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid JWT token structure",
        )

    header_b64, payload_b64, signature_b64 = parts
    payload = _decode_jwt_part(payload_b64)

    # Check expiration if present
    exp = payload.get("exp")
    if exp and time.time() > exp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT token has expired",
        )

    # If SUPABASE_JWT_SECRET is configured, strictly verify HS256 signature
    if jwt_secret:
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = hmac.new(
            jwt_secret.encode("utf-8"), signing_input, hashlib.sha256
        ).digest()
        padded_sig = signature_b64 + "=" * (-len(signature_b64) % 4)
        provided_sig = base64.urlsafe_b64decode(padded_sig)
        if not hmac.compare_digest(expected_sig, provided_sig):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid JWT signature",
            )

    return payload


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    """
    FastAPI dependency to extract and authenticate user.
    Ensures a corresponding Profile row exists in the database.
    """
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        payload = verify_supabase_jwt(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="JWT token missing 'sub' subject claim",
            )
        email = payload.get("email")
    else:
        # Local development / automated tests fallback user
        user_id = DEFAULT_LOCAL_USER_ID
        email = DEFAULT_LOCAL_EMAIL

    # Ensure profile exists in DB
    profile = db.query(models.Profile).filter(models.Profile.id == user_id).first()
    if not profile:
        profile = models.Profile(id=user_id, email=email, full_name="Active Researcher")
        db.add(profile)
        db.commit()

    return AuthenticatedUser(id=user_id, email=email)


def verify_project_ownership(
    project_id: int,
    user: AuthenticatedUser,
    db: Session,
) -> models.ResearchProject:
    """
    Enforce that the requesting user owns the specified project.
    Returns the project if authorized, raises 404 otherwise to avoid leaking existence.
    """
    project = (
        db.query(models.ResearchProject)
        .filter(
            models.ResearchProject.id == project_id,
            models.ResearchProject.user_id == user.id,
        )
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research project {project_id} not found or access denied",
        )
    return project
