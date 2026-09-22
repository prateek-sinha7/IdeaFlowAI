"""Tests for /api/auth/logout and JWT revocation (blocker A4).

Covers:
- The freshly-issued JWT carries a ``jti`` claim.
- /api/auth/logout returns 204 and revokes the presented token.
- A subsequent /api/auth/me with the revoked token returns 401.
- A second login produces a fresh ``jti`` whose token still works after the
  first one is revoked.
- Changing the password blanket-revokes every JWT whose ``iat`` predates the
  rotation (the ``tokens_valid_from`` path).
- Logging out twice with the same ``jti`` is idempotent — both calls 204.

These tests stand up a real FastAPI ``TestClient`` against the auth router
backed by an in-memory SQLite database, with the production ``get_db``
dependency overridden so each test gets a fresh schema. Cognito is the sole
authentication authority (Cognito-only auth migration,
``.kiro/specs/login/prompt.md`` Phase 1): ``FakeCognitoAuth`` mints real
RS256 tokens the offline verifier accepts, with no network call — see
``tests/factories/user_factory.py``.

Lives in the INTEGRATION suite: revocation IS a persistence claim. "The token is
revoked" means a row exists keyed on that ``jti`` with a matching ``exp``, and "a second
login's token survives the first logout" means revocation is scoped per-row rather than
per-user. Both are only observable by issuing a real token, calling logout, and then
re-authenticating against the stored state — a mocked Session would let a no-op logout
pass. Offline regardless (in-memory engine, no AWS), so the unit-suite isolation guard
(``tests/unit/conftest.py``) correctly refuses a real DB connection there.
"""

import time
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth import router as auth_router
from app.core import cognito
from app.models.database import Base, get_db

# Ensure RevokedToken's table is registered with Base.metadata before
# create_all is called.
from app.models.revoked_token import RevokedToken  # noqa: F401
from app.models.user import User  # noqa: F401  (registers the table on Base.metadata)
from app.models.chat import ChatSession, Message  # noqa: F401
from app.models.workflow import WorkflowRun  # noqa: F401
from tests.factories.user_factory import FakeCognitoAuth, create_user


@pytest.fixture
def client(monkeypatch):
    """Build a TestClient backed by a fresh in-memory SQLite DB."""
    # StaticPool keeps the in-memory database alive across the multiple
    # SQLAlchemy connections that get checked out per request — without it,
    # SQLite's default behaviour is "one in-memory DB per connection", and
    # the schema we created on the first connection vanishes on the next one.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_db] = override_get_db

    fake_auth = FakeCognitoAuth(monkeypatch)
    fake_auth.configure_settings()
    # revoke_token / decrypt path: /logout best-effort revokes a stored
    # refresh token, which these tests never populate, so no-op it.
    monkeypatch.setattr(cognito, "revoke_token", lambda *_a, **_k: None)
    # change_password always "succeeds" — password verification is Cognito's
    # job, not something these JWT/logout-focused tests exercise.
    monkeypatch.setattr(cognito, "change_password", lambda *_a, **_k: None)

    with TestClient(app) as test_client:
        # Exposed so _register can create users directly (self-registration
        # is disabled — see app/api/auth.py) against this test's own engine.
        test_client.SessionLocal = TestingSession
        test_client.fake_auth = fake_auth
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def decode_access_token(token: str) -> dict:
    """Decode a Cognito-shaped test token without re-verifying it (the
    signature was already proven by the real login/verify round-trip)."""
    from jose import jwt as jose_jwt

    return jose_jwt.get_unverified_claims(token)


def _register(
    client, email: str = "alice@example.com", password: str = "password123"
) -> dict:
    """Create a Cognito-linked user directly in the test DB, then log in and
    return the parsed AuthResponse JSON.

    ``POST /api/auth/register`` is a permanent 403 (self-registration is
    admin-only by design), so this helper can no longer exercise it. It
    inserts directly instead, with a ``cognito_sub`` that matches what
    ``FakeCognitoAuth`` will mint for this email — see
    ``tests/factories/user_factory.py``.

    These tests are about JWT/logout behaviour, not account creation, so the
    insert goes through the shared ``tests.factories.user_factory.create_user``
    helper (shared with every other auth suite) and the token comes from the
    real ``/api/auth/login`` flow — the part under test.
    """
    session = client.SessionLocal()
    try:
        create_user(session, email, password, cognito_sub=client.fake_auth.sub_for(email))
    finally:
        session.close()
    return _login(client, email=email, password=password)


def _login(
    client, email: str = "alice@example.com", password: str = "password123"
) -> dict:
    """Log in an existing user and return the parsed JSON response."""
    resp = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- 1. JWTs carry a jti claim ---------------------------------------------


class TestJtiClaim:
    """create_access_token now stamps a jti on every token."""

    def test_register_token_has_jti(self, client):
        auth = _register(client, email="jti@example.com", password="password123")
        payload = decode_access_token(auth["token"])
        assert "jti" in payload
        assert payload["jti"]
        # uuid4 strings are 36 chars; minimum sanity check.
        assert len(payload["jti"]) >= 16

    def test_two_tokens_have_distinct_jtis(self, client):
        _register(client, email="distinct@example.com", password="password123")
        a = _login(client, email="distinct@example.com", password="password123")
        b = _login(client, email="distinct@example.com", password="password123")
        pa = decode_access_token(a["token"])
        pb = decode_access_token(b["token"])
        assert pa["jti"] != pb["jti"]


# --- 2. Logout revokes the presented token ---------------------------------


class TestLogoutRevokesToken:
    """Logging out invalidates the JWT used for the request."""

    def test_logout_returns_204_and_blocks_subsequent_me(self, client):
        auth = _register(client, email="logout@example.com", password="password123")
        token = auth["token"]

        # Token works before logout
        me = client.get("/api/auth/me", headers=_bearer(token))
        assert me.status_code == 200
        assert me.json()["email"] == "logout@example.com"

        # Logout
        logout = client.post("/api/auth/logout", headers=_bearer(token))
        assert logout.status_code == 204
        # 204 must have an empty body
        assert logout.content == b""

        # Same token now rejected
        me2 = client.get("/api/auth/me", headers=_bearer(token))
        assert me2.status_code == 401
        assert me2.json()["detail"] == "Token has been revoked"

    def test_logout_without_token_is_401(self, client):
        # Sanity: the endpoint requires authentication.
        resp = client.post("/api/auth/logout")
        # FastAPI's HTTPBearer returns 403 by default when no header is
        # present; tolerate either 401 or 403 as long as it's not a success.
        assert resp.status_code in (401, 403)


# --- 3. Other tokens for the same user keep working -----------------------


class TestPerTokenRevocation:
    """Revocation is per-jti, not per-user (unless password changes)."""

    def test_second_login_token_survives_first_logout(self, client):
        _register(client, email="dual@example.com", password="password123")
        a = _login(client, email="dual@example.com", password="password123")
        b = _login(client, email="dual@example.com", password="password123")
        token_a = a["token"]
        token_b = b["token"]
        assert token_a != token_b

        # Both work initially
        assert client.get("/api/auth/me", headers=_bearer(token_a)).status_code == 200
        assert client.get("/api/auth/me", headers=_bearer(token_b)).status_code == 200

        # Revoke A only
        logout = client.post("/api/auth/logout", headers=_bearer(token_a))
        assert logout.status_code == 204

        # A is now dead; B still alive
        assert client.get("/api/auth/me", headers=_bearer(token_a)).status_code == 401
        assert client.get("/api/auth/me", headers=_bearer(token_b)).status_code == 200


# --- 4. Password change blanket-revokes prior tokens ----------------------


class TestPasswordChangeRevocation:
    """Changing the password blanket-revokes all previously-issued JWTs."""

    def test_change_password_revokes_old_tokens(self, client):
        auth = _register(client, email="rotate@example.com", password="password123")
        old_token = auth["token"]

        # Token works
        assert client.get("/api/auth/me", headers=_bearer(old_token)).status_code == 200

        # Sleep ~1.1s so the iat-vs-password_changed_at comparison has at
        # least 1s of headroom: JWT timestamps are stored at 1-second
        # precision (jose serialises them with ``int(timestamp())``), so a
        # change_password call within the same second as the issuance can't
        # be distinguished from "iat == password_changed_at".
        time.sleep(1.1)

        change = client.post(
            "/api/auth/change-password",
            headers=_bearer(old_token),
            json={"current_password": "password123", "new_password": "newpassword456"},
        )
        assert change.status_code == 200, change.text

        # Old token is now blanket-revoked.
        me = client.get("/api/auth/me", headers=_bearer(old_token))
        assert me.status_code == 401
        assert me.json()["detail"] == "Token has been revoked"

        # New login with the new password issues a fresh JWT that works.
        new_auth = _login(client, email="rotate@example.com", password="newpassword456")
        new_token = new_auth["token"]
        assert client.get("/api/auth/me", headers=_bearer(new_token)).status_code == 200


# --- 5. Logout is idempotent ----------------------------------------------


class TestLogoutIdempotent:
    """Calling logout twice with the same token is a no-op the second time."""

    def test_double_logout_returns_204_each_time(self, client):
        auth = _register(client, email="idem@example.com", password="password123")
        token = auth["token"]

        first = client.post("/api/auth/logout", headers=_bearer(token))
        assert first.status_code == 204

        # /logout uses get_user_for_logout (not get_current_user), which
        # deliberately skips the per-jti revocation check so that a second
        # logout with the same JWT is a no-op rather than a 401. The handler
        # absorbs the duplicate insert via IntegrityError → rollback → 204.
        second = client.post("/api/auth/logout", headers=_bearer(token))
        assert second.status_code == 204

        # And the underlying authenticated state is still "revoked":
        me = client.get("/api/auth/me", headers=_bearer(token))
        assert me.status_code == 401


# --- 6. Logout records correct expires_at ---------------------------------


class TestLogoutPersistsCorrectRow:
    """The revoked_tokens row mirrors the JWT's exp."""

    def test_revocation_row_has_matching_exp(self, client):
        auth = _register(client, email="row@example.com", password="password123")
        token = auth["token"]
        payload = decode_access_token(token)
        expected_exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        expected_jti = payload["jti"]

        client.post("/api/auth/logout", headers=_bearer(token))

        # Fetch the row directly from the test DB. We grab the override that
        # was attached to the app and pull a session out of it.
        get_db_override = client.app.dependency_overrides[get_db]
        db = next(get_db_override())
        try:
            row = (
                db.query(RevokedToken).filter(RevokedToken.jti == expected_jti).first()
            )
            assert row is not None, "Logout did not create a revoked_tokens row"
            stored = row.expires_at
            if stored.tzinfo is None:
                stored = stored.replace(tzinfo=timezone.utc)
            # Allow 1-second skew for the int-second JWT exp truncation.
            assert abs((stored - expected_exp).total_seconds()) < 2
        finally:
            db.close()
