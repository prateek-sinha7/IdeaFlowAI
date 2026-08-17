"""Shared helper for creating users directly in a test database.

``POST /api/auth/register`` is a permanent 403 by design (see
``app/api/auth.py``) — account creation is administrator-only, the endpoint
only still exists so legacy clients get a clear error instead of a 404.
Tests that need a logged-in user therefore insert the row directly, hashing
the password with the same ``hash_password`` helper ``/api/auth/login``
verifies against (mirrors ``app/scripts/bootstrap_admin.py``'s approach),
and then obtain a token via the real login endpoint.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User


def create_user(
    session: Session,
    email: str,
    password: str,
    *,
    tier: str = "basic",
    is_admin: bool = False,
) -> User:
    """Insert and commit a user row with a correctly-hashed password."""
    user = User(
        email=email,
        password_hash=hash_password(password),
        tier=tier,
        is_admin=is_admin,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
