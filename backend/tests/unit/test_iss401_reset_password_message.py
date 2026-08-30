"""backend/tests/unit/test_iss401_reset_password_message.py — ISS-401.

`POST /api/admin/users/{user_id}/reset-password` refuses to act on a
break-glass/local account (`auth_provider != "cognito"`) with a 409 — that
refusal is correct by design (`admin.py:553-557`'s comment: the break-glass
credential must stay changeable independent of a Cognito outage). But the
`detail` string it returns claims *"This account's password is managed
outside the application and cannot be reset here"* — false for this exact
account type: `password_hash` (`backend/app/models/user.py:28-33`) is a
column on the app's own `User` row, and `POST /api/auth/change-password`'s
`local` branch (`auth.py:1254-1269`) verifies and rewrites it entirely
inside this application's own database.

Same root cause as ISS-404 (`SecuritySection.tsx`'s identical false claim),
filed separately because this endpoint has no wired frontend caller today
(grepped: no UI calls `adminResetUserPassword`) — confirmed via direct call
to the route function, not an HTTP round-trip.

See `bug-hunter/ledger.md`'s `BUG-20260828-032424-settings-security` entry and
`.knowledge/cards/20260828-2121-ISS-401.md`.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base
from app.models.user import User


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _make_local_user(db) -> User:
    u = User(
        id="break-glass-user",
        email="breakglass@example.com",
        cognito_sub=None,
        auth_provider="local",
        password_hash="bcrypt$fake-hash-not-used-by-this-test",
        tier="enterprise",
        is_admin=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_admin(db) -> User:
    a = User(
        id="admin-user",
        email="admin@example.com",
        cognito_sub="sub-admin",
        auth_provider="cognito",
        tier="enterprise",
        is_admin=True,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@pytest.mark.issue("ISS-401")
def test_reset_password_409_does_not_claim_credentials_are_managed_externally(
    db_session,
):
    """ISS-401 — the 409 for a break-glass/local account must not claim its
    password is "managed outside the application": this app's own database
    is the credential store for that account.
    """
    from app.api import admin as admin_mod

    user = _make_local_user(db_session)
    admin_user = _make_admin(db_session)

    request = admin_mod.ResetPasswordRequest(new_password="a-new-password-123")

    with pytest.raises(HTTPException) as exc_info:
        admin_mod.reset_user_password(
            user_id=user.id,
            request=request,
            admin=admin_user,
            db=db_session,
        )

    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert "outside the application" not in detail, (
        f"409 detail still claims external credential management: {detail!r}"
    )
