"""Both API-key transports enforce the same checks.

Phase 2 of the Cognito-only auth migration: *"``mcp.py::_get_user_from_bearer``
-> reuse ``get_user_via_api_key`` (enforce ``expires_at``)."*

An API key reaches the backend on two different headers -- ``X-Flowin-API-Key``
for the IDE/HTTP surface and ``Authorization: Bearer flowin_...`` for the MCP
JSON-RPC surface -- and each surface used to carry its own copy of the lookup.
The copies drifted. When key expiry landed (migration 0033), only the
``X-Flowin-API-Key`` side gained the ``is_expired()`` check; the MCP transport
went on accepting keys past the 90-day expiry stamped on their own row. That is
the longest-lived credential in the system, still working after the date it was
supposed to stop.

Both surfaces now share ``api_key_auth.resolve_api_key``. These tests assert the
two AGREE, rather than asserting each one's rules separately -- the failure mode
was never "one surface has a bug", it was "the two surfaces disagree", and only a
test written as a comparison can fail on that.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api_key_auth import (
    default_api_key_expiry,
    get_user_via_api_key,
    mint_api_key,
)
from app.api.mcp import _get_user_from_bearer
from app.models.database import Base, get_db
from app.models.handoff import UserApiKey
from app.models.user import User


@pytest.fixture()
def env():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()

    user = User(
        id="u1", email="ide@example.com", cognito_sub="sub-1", tier="pro", status="active"
    )
    session.add(user)
    session.commit()

    # Two endpoints over the two different credential transports, both resolving
    # to a User — the smallest harness that can compare them.
    app = FastAPI()

    @app.get("/via-header")
    def via_header(u: User = Depends(get_user_via_api_key)):
        return {"user_id": u.id}

    @app.get("/via-bearer")
    def via_bearer(u: User = Depends(_get_user_from_bearer)):
        return {"user_id": u.id}

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db

    try:
        yield {"client": TestClient(app), "session": session, "user": user}
    finally:
        session.close()
        engine.dispose()


def _mint(env, **row_kwargs) -> str:
    plaintext, prefix, digest = mint_api_key()
    defaults = dict(
        id=f"k-{prefix}",
        user_id=env["user"].id,
        name="test",
        token_prefix=prefix,
        token_hash=digest,
        expires_at=default_api_key_expiry(),
    )
    env["session"].add(UserApiKey(**{**defaults, **row_kwargs}))
    env["session"].commit()
    return plaintext


def _both(env, key: str) -> tuple[int, int]:
    """``(header_status, bearer_status)`` for the same key. Must always match."""
    header = env["client"].get("/via-header", headers={"X-Flowin-API-Key": key})
    bearer = env["client"].get(
        "/via-bearer", headers={"Authorization": f"Bearer {key}"}
    )
    return header.status_code, bearer.status_code


class TestBothSurfacesAgree:
    def test_a_valid_key_is_accepted_by_both(self, env):
        key = _mint(env)

        assert _both(env, key) == (200, 200)

    def test_an_expired_key_is_rejected_by_both(self, env):
        """The actual drift. Before Phase 2 this was (401, 200): the MCP bearer
        transport never called ``is_expired()``."""
        key = _mint(
            env, expires_at=datetime.now(timezone.utc) - timedelta(days=1)
        )

        assert _both(env, key) == (401, 401)

    def test_a_revoked_key_is_rejected_by_both(self, env):
        key = _mint(env, revoked_at=datetime.now(timezone.utc))

        assert _both(env, key) == (401, 401)

    def test_an_unknown_key_is_rejected_by_both(self, env):
        assert _both(env, "flowin_never-existed") == (401, 401)

    def test_a_malformed_key_is_rejected_by_both(self, env):
        """No ``flowin_`` prefix: rejected before any DB lookup."""
        assert _both(env, "not-a-flowin-key") == (401, 401)

    def test_a_disabled_owner_is_rejected_by_both(self, env):
        """Decision 6: disabling a user must also kill their long-lived keys.
        Otherwise disabling someone would end their browser sessions while leaving
        every paste-once IDE/MCP credential they hold fully functional."""
        key = _mint(env)
        env["user"].status = "disabled"
        env["session"].commit()

        assert _both(env, key) == (401, 401)

    def test_a_legacy_null_expiry_key_is_accepted_by_both(self, env):
        """``expires_at IS NULL`` means "never expires" (0033 kept pre-existing
        keys working). Migration 0040 backfills these; until it runs, both
        surfaces must treat them identically rather than one failing closed."""
        key = _mint(env, expires_at=None)

        assert _both(env, key) == (200, 200)


class TestUniformErrors:
    def test_neither_surface_distinguishes_why_a_key_failed(self, env):
        """Same body for unknown, revoked and expired, per surface. Splitting them
        would hand an attacker a probe for which key strings were ever real."""
        client = env["client"]
        expired = _mint(
            env, expires_at=datetime.now(timezone.utc) - timedelta(days=1)
        )
        revoked = _mint(env, revoked_at=datetime.now(timezone.utc))

        bodies = {
            client.get("/via-header", headers={"X-Flowin-API-Key": k}).json()["detail"]
            for k in (expired, revoked, "flowin_never-existed")
        }
        assert len(bodies) == 1

        bodies = {
            client.get("/via-bearer", headers={"Authorization": f"Bearer {k}"})
            .json()["detail"]
            for k in (expired, revoked, "flowin_never-existed")
        }
        assert len(bodies) == 1

    def test_a_missing_authorization_header_is_rejected(self, env):
        assert env["client"].get("/via-bearer").status_code == 401

    def test_a_non_bearer_authorization_header_is_rejected(self, env):
        resp = env["client"].get("/via-bearer", headers={"Authorization": "Basic abc"})

        assert resp.status_code == 401
