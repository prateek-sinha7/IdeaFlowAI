"""ISS-370 — whitespace-only API key name bypasses the "Default" fallback
(BUG-20260828-103900-handoff-settings-r2).

``create_api_key`` (``app/api/settings.py``) stores ``payload.name`` verbatim.
``ApiKeyCreateRequest.name`` only enforces ``min_length=1`` on the RAW string,
so a whitespace-only name (e.g. three spaces) satisfies validation and is
persisted as-is -- unlike the router's own ``upsert_github_pat`` sibling
handler in the same file, which strips its input and 422s on blank-after-strip.
There is no PATCH/PUT for ``/api-keys``, so the blank name is permanent once
created.

This test drives the real ``create_api_key`` handler function directly against
an in-memory SQLite session (mirrors the harness in
``test_settings_preferences_race.py``), passing a whitespace-only name and
asserting the stored row is never blank/whitespace-only.

Correct behaviour: a whitespace-only name must not be stored verbatim -- it
should either be rejected (422) or trimmed/defaulted to "Default".
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fastapi import HTTPException

from app.api.settings import ApiKeyCreateRequest, create_api_key
from app.models.database import Base
from app.models.user import User


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    s = Session()
    user = User(id="user-apikey", email="apikey@example.com", tier="enterprise")
    s.add(user)
    s.commit()
    yield s
    s.close()


@pytest.mark.issue("ISS-370")
def test_whitespace_only_name_not_stored_verbatim(session):
    """A whitespace-only key name must not produce a blank stored name."""
    user = session.query(User).filter(User.id == "user-apikey").one()
    payload = ApiKeyCreateRequest(name="   ")

    try:
        response = create_api_key(payload, user, session)
    except HTTPException as exc:
        assert exc.status_code == 422
        return

    assert response.name.strip() != "", (
        f"whitespace-only name was stored verbatim as {response.name!r}; "
        "expected rejection or a non-blank fallback"
    )
