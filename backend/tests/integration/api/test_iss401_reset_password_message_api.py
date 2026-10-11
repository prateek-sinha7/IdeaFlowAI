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


# Cognito-only auth migration (b2a621f8 / a4801e5f): `auth_provider` and
# `password_hash` were dropped and `cognito_sub` is NOT NULL, so break-glass
# "local" accounts — and the 409 branch that refused them — no longer exist.
# The ISS-401 intent survives: no failure the reset endpoint can return may
# claim the password is "managed outside the application". The only refusal
# path left is the provider failure mapped by admin._raise_for, so that is
# what this test now drives.
def _make_local_user(db) -> User:
    u = User(
        id="break-glass-user",
        email="breakglass@example.com",
        cognito_sub="sub-break-glass",
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
        tier="enterprise",
        is_admin=True,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@pytest.mark.issue("ISS-401")
def test_reset_password_409_does_not_claim_credentials_are_managed_externally(
    db_session, monkeypatch
):
    """ISS-401 — a refused reset must not claim the password is "managed
    outside the application". Local accounts are gone, so the refusal under
    test is the provider-failure one; it must be an honest 503.
    """
    from app.api import admin as admin_mod
    from app.core.cognito_admin import ProviderUnavailableError

    user = _make_local_user(db_session)
    admin_user = _make_admin(db_session)

    def _provider_down(db, target):
        raise ProviderUnavailableError(
            "Could not reset the password at the identity provider.",
            code="InternalErrorException",
        )

    monkeypatch.setattr(admin_mod.cognito_admin, "reset_password", _provider_down)

    request = admin_mod.ResetPasswordRequest()  # temp password is server-generated now

    with pytest.raises(HTTPException) as exc_info:
        admin_mod.reset_user_password(
            user_id=user.id,
            request=request,
            admin=admin_user,
            db=db_session,
        )

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert (
        "outside the application" not in detail
    ), f"409 detail still claims external credential management: {detail!r}"
