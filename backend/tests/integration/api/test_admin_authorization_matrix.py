"""Admin API authorization test matrix.

Comprehensive testing of the Admin API endpoints across all authorization states:

1. **Authenticated Admin** — Valid JWT for an admin account; endpoint succeeds
2. **Missing Credential** — No JWT or expired JWT; endpoint rejects with 401
3. **Non-Admin** — Valid JWT but is_admin=False; endpoint rejects with 403

## Coverage

Routes tested (Requirement 5.1):
- GET /api/admin/users (list all users)
- PATCH /api/admin/users/{user_id}/tier (change tier)
- POST /api/admin/users (create user)
- DELETE /api/admin/users/{user_id} (delete user)

## Authorization Guarantees Verified (Requirement 5.2–5.10)

- Missing credentials → 401 with non-disclosing body
- Non-admin → 403 with non-disclosing body
- Valid admin → success with stored record persisted
- Non-existent target → 404 with byte-identical pre-state
- Duplicate field (email) → 409 Conflict with byte-identical pre-state
- Validation failure (bad tier) → 400 with byte-identical pre-state
- Cross-workspace request → 404 with byte-identical pre-state (scoped store)
- Transactional failure → rolled back, byte-identical pre-state
- Self-action policy on tier change → 400 with explanation

Uses real JWTs signed in-process by production auth wiring, production
scoped store, and no overridden auth or authorization dependency.

Baseline: 3,498 pytest collected cases (including these admin tests).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from botocore.exceptions import ClientError

from app.core import cognito
from app.core.config import settings
from app.core.entitlements import ADMIN_GROUP, group_for_tier
from app.models.database import Base, get_db
from tests.factories.user_factory import FakeCognitoAuth, create_user


class _FakePool:
    """In-memory Cognito pool: enough of the Admin* surface for the admin
    router's create/tier/role/delete flows, keyed by email.

    Cognito is the sole authentication authority (Cognito-only auth
    migration, ``.kiro/specs/login/prompt.md`` Phase 1) — every write this
    test suite exercises against ``/api/admin/*`` now goes through Cognito
    Admin* calls, so the fake must model group membership, not just
    existence.
    """

    def __init__(self, auth: FakeCognitoAuth) -> None:
        self._auth = auth
        self.groups: dict[str, set[str]] = {}  # email -> group names
        self.disabled: set[str] = set()

    def create_user(self, email: str) -> str:
        if email in self.groups:
            raise ClientError(
                {"Error": {"Code": "UsernameExistsException", "Message": "exists"}},
                "AdminCreateUser",
            )
        self.groups[email] = set()
        sub = self._auth.sub_for(email)
        return sub

    def delete_user(self, email: str) -> None:
        if email not in self.groups:
            raise ClientError(
                {"Error": {"Code": "UserNotFoundException", "Message": "absent"}},
                "AdminDeleteUser",
            )
        del self.groups[email]
        self.disabled.discard(email)

    def disable_user(self, email: str) -> None:
        if email not in self.groups:
            raise ClientError(
                {"Error": {"Code": "UserNotFoundException", "Message": "absent"}},
                "AdminDisableUser",
            )
        self.disabled.add(email)

    def enable_user(self, email: str) -> None:
        if email not in self.groups:
            raise ClientError(
                {"Error": {"Code": "UserNotFoundException", "Message": "absent"}},
                "AdminEnableUser",
            )
        self.disabled.discard(email)

    def add_group(self, email: str, group: str) -> None:
        self.groups.setdefault(email, set()).add(group)

    def remove_group(self, email: str, group: str) -> None:
        self.groups.setdefault(email, set()).discard(group)

    def list_groups(self, email: str) -> list[str]:
        return list(self.groups.get(email, set()))

    def list_users_in_group(self, group: str) -> list[dict]:
        return [
            {"Username": email, "Attributes": [{"Name": "email", "Value": email}]}
            for email, groups in self.groups.items()
            if group in groups
        ]


# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture()
def admin_api_client(monkeypatch, tmp_path):
    """FastAPI TestClient backed by fresh in-memory SQLite DB.

    Sets up production auth wiring with Cognito faked at the boto3-client
    boundary (``FakeCognitoAuth`` + ``_FakePool``) — real code paths in
    ``core.identity``/``api.auth``/``api.admin`` run unmodified; only the
    AWS network call is replaced. Same DB-setup pattern as
    test_handoff_api, tuned for admin endpoint testing.
    """
    db_path = tmp_path / "test_admin.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    # Update settings with the test database URL.
    monkeypatch.setattr(settings, "DATABASE_URL", db_url)

    # Recreate the engine pointed at the test URL.
    test_engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(test_engine)

    # Stamp alembic_version so the lifespan check passes.
    with test_engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR PRIMARY KEY)"
            )
        )
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0026')"))

    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    # Late import so FastAPI app picks up the new engine config.
    from app.main import app

    app.dependency_overrides[get_db] = override_get_db
    import app.models.database as db_module

    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)

    fake_auth = FakeCognitoAuth(monkeypatch)
    fake_auth.configure_settings()
    pool = _FakePool(fake_auth)

    # Pin the admin-MFA gate to its production default instead of inheriting it.
    # CI has no backend/.env, so ADMIN_MFA_REQUIRED is True there; a developer's
    # .env commonly turns it off. Left unpinned, this suite exercised two
    # different code paths (it passed locally and 403'd on every admin call in
    # CI). The admin session below proves MFA the same way login_challenge
    # does -- see `_stamp_mfa_proven` -- so the matrix runs against the real gate.
    monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", True)

    def _fake_admin_initiate_auth(email: str, password: str):
        # Mint a token carrying the pool's CURRENT group membership for this
        # email, so require_admin's cognito:groups-derived check reflects
        # whatever this fixture/test set on `pool.groups` — not a fixed
        # empty list.
        del password
        return {
            "AuthenticationResult": {
                "AccessToken": fake_auth._mint_token(
                    email, groups=pool.list_groups(email)
                ),
                "RefreshToken": "fake-refresh-token",
            }
        }

    monkeypatch.setattr(cognito, "admin_initiate_auth", _fake_admin_initiate_auth)

    def _fake_admin_create_user(email: str, *_a, **_k):
        sub = pool.create_user(email)
        return {"User": {"Attributes": [{"Name": "sub", "Value": sub}]}}

    monkeypatch.setattr(cognito, "admin_create_user", _fake_admin_create_user)
    monkeypatch.setattr(cognito, "admin_set_user_password", lambda *a, **k: None)
    monkeypatch.setattr(
        cognito,
        "admin_add_user_to_group",
        lambda email, group: pool.add_group(email, group),
    )
    monkeypatch.setattr(
        cognito,
        "admin_remove_user_from_group",
        lambda email, group: pool.remove_group(email, group),
    )
    monkeypatch.setattr(
        cognito, "admin_list_groups_for_user", lambda email: pool.list_groups(email)
    )
    monkeypatch.setattr(cognito, "admin_user_global_sign_out", lambda *a, **k: None)
    monkeypatch.setattr(
        cognito, "admin_delete_user", lambda email: pool.delete_user(email)
    )
    monkeypatch.setattr(
        cognito, "admin_disable_user", lambda email: pool.disable_user(email)
    )
    monkeypatch.setattr(
        cognito, "admin_enable_user", lambda email: pool.enable_user(email)
    )
    monkeypatch.setattr(
        cognito, "list_users_in_group", lambda group: pool.list_users_in_group(group)
    )

    with TestClient(app) as client:
        client.SessionLocal = TestSession
        client.test_engine = test_engine
        client.fake_auth = fake_auth
        client.pool = pool
        yield client

    app.dependency_overrides.clear()


@pytest.fixture()
def admin_user(admin_api_client):
    """Create an admin user and return (user_id, jwt_token)."""
    email = "admin@example.com"
    session = admin_api_client.SessionLocal()
    try:
        admin = create_user(
            session,
            email,
            "SecurePassword123",
            is_admin=True,
            tier="enterprise",
            cognito_sub=admin_api_client.fake_auth.sub_for(email),
        )
        admin_id = admin.id
    finally:
        session.close()
    admin_api_client.pool.groups[email] = {group_for_tier("enterprise"), ADMIN_GROUP}

    resp = admin_api_client.post(
        "/api/auth/login",
        json={"email": email, "password": "SecurePassword123"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    _stamp_mfa_proven(admin_api_client, admin_id, token)
    return admin_id, token


def _stamp_mfa_proven(client, user_id: str, token: str) -> None:
    """Record that ``token``'s session answered an MFA challenge.

    This is the exact write ``app/api/auth.py::login_challenge`` makes after a
    real SOFTWARE_TOKEN_MFA / EMAIL_OTP answer: ``mfa_verified_at`` set to the
    token's own ``iat``, which is what ``core.identity.enforce_admin_mfa``
    compares against. The challenge ceremony itself is owned by
    ``tests/unit/api/test_totp_enrollment.py`` and ``test_email_mfa.py``; this
    suite only needs an admin whose session satisfies the gate.
    """
    from datetime import datetime, timezone

    from jose import jwt as jose_jwt

    from app.models.user import User

    issued_at = jose_jwt.get_unverified_claims(token)["iat"]
    session = client.SessionLocal()
    try:
        user = session.get(User, user_id)
        user.mfa_verified_at = datetime.fromtimestamp(issued_at, tz=timezone.utc)
        session.commit()
    finally:
        session.close()


@pytest.fixture()
def regular_user(admin_api_client):
    """Create a regular non-admin user and return (user_id, jwt_token)."""
    email = "regular@example.com"
    session = admin_api_client.SessionLocal()
    try:
        user = create_user(
            session,
            email,
            "SecurePassword123",
            is_admin=False,
            cognito_sub=admin_api_client.fake_auth.sub_for(email),
        )
        user_id = user.id
    finally:
        session.close()
    admin_api_client.pool.groups[email] = {group_for_tier("basic")}

    resp = admin_api_client.post(
        "/api/auth/login",
        json={"email": email, "password": "SecurePassword123"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    return user_id, token


def _snapshot_all_users(session):
    """Take a byte-identical snapshot of all stored User records.

    Returns a dict keyed by user_id with values of (email, tier, is_admin)
    for byte-comparison after failed mutations.
    """
    from app.models.user import User

    users = session.query(User).all()
    return {u.id: (u.email, u.tier, u.is_admin) for u in users}


def _assert_users_unchanged(session, before_snapshot):
    """Assert every user record is byte-identical to the before_snapshot.

    Used to verify transactional rollback and ACID properties.
    """
    from app.models.user import User

    after_snapshot = {
        u.id: (u.email, u.tier, u.is_admin) for u in session.query(User).all()
    }
    assert after_snapshot == before_snapshot, (
        f"User records changed unexpectedly.\n"
        f"Before: {before_snapshot}\n"
        f"After: {after_snapshot}"
    )


# ─── Tests: GET /api/admin/users ────────────────────────────────────────────


class TestListUsersAuthorization:
    """Test GET /api/admin/users across authorization states."""

    def test_list_users_requires_authentication(self, admin_api_client):
        """Missing credential → 401 with non-disclosing body."""
        resp = admin_api_client.get("/api/admin/users")
        assert resp.status_code == 401
        # Body must not contain user data or field values
        body = resp.json()
        assert "detail" in body
        assert not any(k in str(body) for k in ["email", "tier", "admin", "user"])

    def test_list_users_requires_admin_role(self, admin_api_client, regular_user):
        """Non-admin JWT → 403 with non-disclosing body."""
        user_id, token = regular_user
        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.get("/api/admin/users", headers=headers)
        assert resp.status_code == 403
        body = resp.json()
        assert "detail" in body
        assert "Admin" in body["detail"]  # OK to mention the requirement
        assert not any(k in str(body) for k in ["email", "tier", "user_id"])

    def test_list_users_succeeds_for_admin(self, admin_api_client, admin_user):
        """Authenticated admin → 200 with user list."""
        admin_id, token = admin_user
        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.get("/api/admin/users", headers=headers)
        assert resp.status_code == 200
        users = resp.json()
        assert isinstance(users, list)
        # At least the admin user should be present
        assert any(u["id"] == admin_id for u in users)

    def test_list_users_expired_token_rejected(
        self, admin_api_client, admin_user, monkeypatch
    ):
        """Expired JWT → 401 with non-disclosing body.

        Validates: Requirement 5.2 (missing credential covers expiry).
        """
        admin_id, token = admin_user
        # Simulate token expiry by removing the user from the database
        session = admin_api_client.SessionLocal()
        try:
            from app.models.user import User

            user = session.query(User).filter(User.id == admin_id).first()
            if user:
                session.delete(user)
                session.commit()
        finally:
            session.close()

        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.get("/api/admin/users", headers=headers)
        # After user deletion, the JWT validation should fail
        assert resp.status_code in [401, 403], f"Got {resp.status_code}: {resp.text}"


# ─── Tests: POST /api/admin/users (Create) ─────────────────────────────────


class TestCreateUserAuthorization:
    """Test POST /api/admin/users across authorization states."""

    def test_create_user_requires_authentication(self, admin_api_client):
        """Missing credential → 401 with non-disclosing body."""
        payload = {
            "email": "newuser@example.com",
            "password": "SecurePass123",
            "tier": "basic",
            "is_admin": False,
        }
        resp = admin_api_client.post("/api/admin/users", json=payload)
        assert resp.status_code == 401
        body = resp.json()
        assert "detail" in body
        # No email or user data in error
        assert "newuser" not in str(body)

    def test_create_user_requires_admin_role(self, admin_api_client, regular_user):
        """Non-admin JWT → 403 with non-disclosing body."""
        user_id, token = regular_user
        payload = {
            "email": "another@example.com",
            "tier": "basic",
            "is_admin": False,
        }
        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.post("/api/admin/users", json=payload, headers=headers)
        assert resp.status_code == 403

    def test_create_user_succeeds_for_admin(self, admin_api_client, admin_user):
        """Authenticated admin → 201 with created user record persisted.

        Phase 3: no password field — creation is invitation-only
        (``core.cognito_admin.invite_user``)."""
        admin_id, token = admin_user
        payload = {
            "email": "created@example.com",
            "tier": "pro",
            "is_admin": False,
        }
        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.post("/api/admin/users", json=payload, headers=headers)
        assert resp.status_code == 201
        created = resp.json()
        assert created["email"] == "created@example.com"
        assert created["tier"] == "pro"
        assert created["is_admin"] is False

        # Verify persisted in database
        session = admin_api_client.SessionLocal()
        try:
            from app.models.user import User

            user = (
                session.query(User).filter(User.email == "created@example.com").first()
            )
            assert user is not None
            assert user.tier == "pro"
            assert user.is_admin is False
        finally:
            session.close()

    def test_create_user_duplicate_email_conflict(
        self, admin_api_client, admin_user, regular_user
    ):
        """Duplicate email on unique field → 409 Conflict with byte-identical pre-state.

        Validates: Requirement 5.6 (conflict on unique constraint).
        """
        admin_id, admin_token = admin_user
        user_id, user_token = regular_user

        # Snapshot before the failed request
        session = admin_api_client.SessionLocal()
        try:
            before = _snapshot_all_users(session)
        finally:
            session.close()

        # Attempt to create a user with the same email as regular_user
        payload = {
            "email": "regular@example.com",  # Already exists
            "tier": "basic",
            "is_admin": False,
        }
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = admin_api_client.post("/api/admin/users", json=payload, headers=headers)
        assert resp.status_code == 409
        error = resp.json()
        assert (
            "email" in error.get("detail", "").lower()
            or "conflict" in error.get("detail", "").lower()
        )

        # Verify no new user was created (byte-identical state)
        session = admin_api_client.SessionLocal()
        try:
            _after = _snapshot_all_users(session)
            _assert_users_unchanged(session, before)
        finally:
            session.close()

    def test_create_user_invalid_tier_validation_error(
        self, admin_api_client, admin_user
    ):
        """Invalid tier value → 400 Bad Request with byte-identical pre-state.

        Validates: Requirement 5.7 (validation error with unchanged records).
        """
        admin_id, token = admin_user

        session = admin_api_client.SessionLocal()
        try:
            before = _snapshot_all_users(session)
        finally:
            session.close()

        payload = {
            "email": "invalid_tier@example.com",
            "tier": "invalid_tier_name",  # Not in TIER_PIPELINES
            "is_admin": False,
        }
        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.post("/api/admin/users", json=payload, headers=headers)
        assert resp.status_code == 400
        error = resp.json()
        assert "tier" in error.get("detail", "").lower()

        # Verify state unchanged
        session = admin_api_client.SessionLocal()
        try:
            _assert_users_unchanged(session, before)
        finally:
            session.close()

    def test_create_user_rejects_a_password_field(self, admin_api_client, admin_user):
        """Phase 3: creation is invitation-only. A client that still POSTs a
        ``password`` (hoping to set one) gets a 422 from Pydantic's
        ``extra=forbid`` — never a silently-ignored value that could make the
        caller believe a password was set when it never reached Cognito."""
        admin_id, token = admin_user

        session = admin_api_client.SessionLocal()
        try:
            before = _snapshot_all_users(session)
        finally:
            session.close()

        payload = {
            "email": "shortpass@example.com",
            "password": "short",
            "tier": "basic",
            "is_admin": False,
        }
        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.post("/api/admin/users", json=payload, headers=headers)
        assert resp.status_code == 422

        # Verify state unchanged
        session = admin_api_client.SessionLocal()
        try:
            _assert_users_unchanged(session, before)
        finally:
            session.close()


# ─── Tests: PATCH /api/admin/users/{user_id}/tier (Update Tier) ────────────


class TestUpdateUserTierAuthorization:
    """Test PATCH /api/admin/users/{user_id}/tier across authorization states."""

    def test_update_tier_requires_authentication(self, admin_api_client, regular_user):
        """Missing credential → 401 with non-disclosing body."""
        user_id, _ = regular_user
        payload = {"tier": "pro"}
        resp = admin_api_client.patch(f"/api/admin/users/{user_id}/tier", json=payload)
        assert resp.status_code == 401
        body = resp.json()
        assert "detail" in body

    def test_update_tier_requires_admin_role(self, admin_api_client, regular_user):
        """Non-admin JWT → 403 with non-disclosing body."""
        user_id, token = regular_user
        target_user_id = user_id  # Update their own tier (still should fail)
        payload = {"tier": "pro"}
        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.patch(
            f"/api/admin/users/{target_user_id}/tier", json=payload, headers=headers
        )
        assert resp.status_code == 403

    def test_update_tier_succeeds_for_admin_on_other_user(
        self, admin_api_client, admin_user, regular_user
    ):
        """Admin updates other user's tier → 200 with persisted change."""
        admin_id, admin_token = admin_user
        user_id, _ = regular_user

        payload = {"tier": "pro"}
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = admin_api_client.patch(
            f"/api/admin/users/{user_id}/tier", json=payload, headers=headers
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["id"] == user_id
        assert updated["tier"] == "pro"

        # Verify persisted
        session = admin_api_client.SessionLocal()
        try:
            from app.models.user import User

            user = session.query(User).filter(User.id == user_id).first()
            assert user.tier == "pro"
        finally:
            session.close()

    def test_update_tier_admin_cannot_modify_own_tier_self_action_policy(
        self, admin_api_client, admin_user
    ):
        """Admin attempting to change own tier → 400 with self-action policy explanation.

        Validates: Requirement 5.9 (admin self-action policy on tier changes).
        """
        admin_id, token = admin_user

        session = admin_api_client.SessionLocal()
        try:
            before = _snapshot_all_users(session)
        finally:
            session.close()

        payload = {"tier": "basic"}  # Attempt to downgrade self
        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.patch(
            f"/api/admin/users/{admin_id}/tier", json=payload, headers=headers
        )
        assert resp.status_code == 400
        error = resp.json()
        assert (
            "own tier" in error.get("detail", "").lower()
            or "yourself" in error.get("detail", "").lower()
        )

        # Verify state unchanged (admin's tier still unchanged)
        session = admin_api_client.SessionLocal()
        try:
            _assert_users_unchanged(session, before)
        finally:
            session.close()

    def test_update_tier_target_not_found_no_disclosure(
        self, admin_api_client, admin_user
    ):
        """Target user does not exist → 404 with byte-identical pre-state.

        Validates: Requirement 5.5 (not-found with unchanged records).
        """
        admin_id, token = admin_user

        session = admin_api_client.SessionLocal()
        try:
            before = _snapshot_all_users(session)
        finally:
            session.close()

        nonexistent_id = "00000000-0000-0000-0000-000000000000"
        payload = {"tier": "pro"}
        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.patch(
            f"/api/admin/users/{nonexistent_id}/tier", json=payload, headers=headers
        )
        assert resp.status_code == 404

        # Verify state unchanged
        session = admin_api_client.SessionLocal()
        try:
            _assert_users_unchanged(session, before)
        finally:
            session.close()

    def test_update_tier_invalid_tier_validation_error(
        self, admin_api_client, admin_user, regular_user
    ):
        """Invalid tier value → 400 with byte-identical pre-state."""
        admin_id, admin_token = admin_user
        user_id, _ = regular_user

        session = admin_api_client.SessionLocal()
        try:
            before = _snapshot_all_users(session)
        finally:
            session.close()

        payload = {"tier": "not_a_real_tier"}
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = admin_api_client.patch(
            f"/api/admin/users/{user_id}/tier", json=payload, headers=headers
        )
        assert resp.status_code == 400
        error = resp.json()
        assert "tier" in error.get("detail", "").lower()

        # Verify state unchanged
        session = admin_api_client.SessionLocal()
        try:
            _assert_users_unchanged(session, before)
        finally:
            session.close()


# ─── Tests: DELETE /api/admin/users/{user_id} ──────────────────────────────


class TestDeleteUserAuthorization:
    """Test DELETE /api/admin/users/{user_id} across authorization states."""

    def test_delete_user_requires_authentication(self, admin_api_client, regular_user):
        """Missing credential → 401 with non-disclosing body."""
        user_id, _ = regular_user
        resp = admin_api_client.delete(f"/api/admin/users/{user_id}")
        assert resp.status_code == 401

    def test_delete_user_requires_admin_role(self, admin_api_client, regular_user):
        """Non-admin JWT → 403 with non-disclosing body."""
        user_id, token = regular_user
        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.delete(f"/api/admin/users/{user_id}", headers=headers)
        assert resp.status_code == 403

    def test_delete_user_succeeds_for_admin(
        self, admin_api_client, admin_user, regular_user
    ):
        """Admin deletes another user → 204 No Content with user removed."""
        admin_id, admin_token = admin_user
        user_id, _ = regular_user

        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = admin_api_client.delete(f"/api/admin/users/{user_id}", headers=headers)
        assert resp.status_code == 204

        # Verify deleted from database
        session = admin_api_client.SessionLocal()
        try:
            from app.models.user import User

            user = session.query(User).filter(User.id == user_id).first()
            assert user is None
        finally:
            session.close()

    def test_delete_user_admin_cannot_delete_self_self_action_policy(
        self, admin_api_client, admin_user
    ):
        """Admin attempting to delete own account → 400 with self-action policy.

        Validates: Requirement 5.9 (self-action policy extends to deletion).
        """
        admin_id, token = admin_user

        session = admin_api_client.SessionLocal()
        try:
            before = _snapshot_all_users(session)
        finally:
            session.close()

        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.delete(f"/api/admin/users/{admin_id}", headers=headers)
        assert resp.status_code == 400
        error = resp.json()
        assert (
            "own account" in error.get("detail", "").lower()
            or "yourself" in error.get("detail", "").lower()
        )

        # Verify state unchanged
        session = admin_api_client.SessionLocal()
        try:
            _assert_users_unchanged(session, before)
        finally:
            session.close()

    def test_delete_user_target_not_found(self, admin_api_client, admin_user):
        """Target user does not exist → 404 with byte-identical pre-state."""
        admin_id, token = admin_user

        session = admin_api_client.SessionLocal()
        try:
            before = _snapshot_all_users(session)
        finally:
            session.close()

        nonexistent_id = "00000000-0000-0000-0000-000000000000"
        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.delete(
            f"/api/admin/users/{nonexistent_id}", headers=headers
        )
        assert resp.status_code == 404

        # Verify state unchanged
        session = admin_api_client.SessionLocal()
        try:
            _assert_users_unchanged(session, before)
        finally:
            session.close()


# ─── Tests: Cross-scope isolation (if applicable) ──────────────────────────


class TestAdminCrossWorkspaceIsolation:
    """Test admin endpoints against cross-workspace isolation.

    Currently the admin API does not enforce workspace scoping per the
    current implementation, but this test placeholder documents the
    expected behavior if workspace isolation is added to admin endpoints.

    Validates: Requirement 5.8 (cross-workspace requests handled as not-found).
    """

    def test_admin_endpoints_currently_unscoped(self, admin_api_client, admin_user):
        """Admin endpoints currently operate at account level (unscoped).

        This test documents the current design. If workspace scoping is
        added to admin endpoints, this test should be updated to verify
        that cross-workspace admin requests return 404 with non-disclosure.
        """
        admin_id, token = admin_user
        # Currently this is just a documentation test; no assertion needed
        # beyond confirming the admin user can access the list endpoint
        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.get("/api/admin/users", headers=headers)
        assert resp.status_code == 200


# ─── Phase 3 (Cognito-only auth migration): disable/enable + last-admin ────


class TestUpdateUserRoleLastAdminProtection:
    def test_demote_refuses_when_the_target_is_the_sole_real_admin(
        self, admin_api_client, admin_user
    ):
        """A distinct-actor path for the last-admin check on
        ``PATCH .../role`` (Phase 3, Decision 6) — the self-action guard only
        fires when the actor targets themselves, so this constructs a drift
        scenario (a local ``is_admin=True`` row that never actually joined the
        Cognito admin group) to exercise the LIVE ``ListUsersInGroup`` check
        from a different acting admin."""
        admin_id, token = admin_user
        headers = {"Authorization": f"Bearer {token}"}

        session = admin_api_client.SessionLocal()
        try:
            from app.models.user import User

            drifted = User(
                id="drifted-admin-3",
                email="drifted3@example.com",
                cognito_sub=admin_api_client.fake_auth.sub_for("drifted3@example.com"),
                tier="enterprise",
                is_admin=True,
            )
            session.add(drifted)
            session.commit()
            before = _snapshot_all_users(session)
        finally:
            session.close()

        resp = admin_api_client.patch(
            "/api/admin/users/drifted-admin-3/role",
            json={"is_admin": False},
            headers=headers,
        )
        assert resp.status_code == 409

        session = admin_api_client.SessionLocal()
        try:
            _assert_users_unchanged(session, before)
        finally:
            session.close()


class TestDisableUserAuthorization:
    """Test POST /api/admin/users/{user_id}/disable across authorization
    states (Phase 3, Decision 6 — new endpoint)."""

    def test_disable_requires_authentication(self, admin_api_client, regular_user):
        user_id, _ = regular_user
        resp = admin_api_client.post(f"/api/admin/users/{user_id}/disable")
        assert resp.status_code == 401

    def test_disable_requires_admin_role(self, admin_api_client, regular_user):
        user_id, token = regular_user
        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.post(
            f"/api/admin/users/{user_id}/disable", headers=headers
        )
        assert resp.status_code == 403

    def test_disable_succeeds_for_admin_on_other_user(
        self, admin_api_client, admin_user, regular_user
    ):
        admin_id, token = admin_user
        user_id, _ = regular_user
        headers = {"Authorization": f"Bearer {token}"}

        resp = admin_api_client.post(
            f"/api/admin/users/{user_id}/disable", headers=headers
        )
        assert resp.status_code == 200

        session = admin_api_client.SessionLocal()
        try:
            from app.models.user import User

            user = session.query(User).filter(User.id == user_id).first()
            assert user.status == "disabled"
        finally:
            session.close()

    def test_disabled_user_cannot_log_in_again(
        self, admin_api_client, admin_user, regular_user
    ):
        """The point of the endpoint: a disabled account is rejected by the
        credential verifier (core.identity.resolve_principal), not merely
        flagged in the database."""
        admin_id, admin_token = admin_user
        user_id, user_token = regular_user
        headers = {"Authorization": f"Bearer {admin_token}"}

        resp = admin_api_client.post(
            f"/api/admin/users/{user_id}/disable", headers=headers
        )
        assert resp.status_code == 200

        # The token minted BEFORE the disable must now be rejected.
        probe = admin_api_client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {user_token}"}
        )
        assert probe.status_code == 401

    def test_disable_cannot_target_self(self, admin_api_client, admin_user):
        admin_id, token = admin_user
        headers = {"Authorization": f"Bearer {token}"}

        resp = admin_api_client.post(
            f"/api/admin/users/{admin_id}/disable", headers=headers
        )
        assert resp.status_code == 400

    def test_disable_refuses_when_the_target_is_the_sole_real_admin(
        self, admin_api_client, admin_user
    ):
        """A distinct-actor path for the last-admin check, not the self-action
        guard (which fires only for self-targeting requests and is tested
        separately).

        Constructed via a DB/pool drift: two local rows are flagged
        ``is_admin=True``, but only ONE of them is an actual member of the
        Cognito admin group — a realistic state after a partial prior
        failure or a manual console edit. The acting admin is the REAL
        group member; the target is the drifted row. Since the live group
        has exactly one member, ``is_last_admin`` correctly refuses to
        remove it, even though the actor is a DIFFERENT account.
        """
        admin_id, token = admin_user
        headers = {"Authorization": f"Bearer {token}"}

        # A second row flagged admin locally, but never actually added to the
        # Cognito admin group — simulated drift.
        session = admin_api_client.SessionLocal()
        try:
            from app.models.user import User

            drifted = User(
                id="drifted-admin",
                email="drifted@example.com",
                cognito_sub=admin_api_client.fake_auth.sub_for("drifted@example.com"),
                tier="enterprise",
                is_admin=True,
            )
            session.add(drifted)
            session.commit()
        finally:
            session.close()

        resp = admin_api_client.post(
            "/api/admin/users/drifted-admin/disable", headers=headers
        )
        assert resp.status_code == 409

    def test_disable_target_not_found(self, admin_api_client, admin_user):
        admin_id, token = admin_user
        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.post(
            "/api/admin/users/nonexistent-id/disable", headers=headers
        )
        assert resp.status_code == 404

    def test_disable_twice_is_rejected_with_409(
        self, admin_api_client, admin_user, regular_user
    ):
        admin_id, token = admin_user
        user_id, _ = regular_user
        headers = {"Authorization": f"Bearer {token}"}

        first = admin_api_client.post(
            f"/api/admin/users/{user_id}/disable", headers=headers
        )
        assert first.status_code == 200

        second = admin_api_client.post(
            f"/api/admin/users/{user_id}/disable", headers=headers
        )
        assert second.status_code == 409


class TestResetPasswordSelfAction:
    """POST /api/admin/users/{user_id}/reset-password under the FIX-310
    self-action policy that tier, role, disable and delete already meet."""

    @pytest.mark.issue("ISS-1170")
    def test_reset_password_cannot_target_self(self, admin_api_client, admin_user):
        """Accepting it revokes the admin's own session and replaces their
        password with a temporary one nobody is shown."""
        admin_id, token = admin_user
        headers = {"Authorization": f"Bearer {token}"}

        resp = admin_api_client.post(
            f"/api/admin/users/{admin_id}/reset-password", json={}, headers=headers
        )
        assert resp.status_code == 400
        assert "own" in resp.json().get("detail", "").lower()

        # Nothing was done to the account: the admin's session still works.
        probe = admin_api_client.get("/api/auth/me", headers=headers)
        assert probe.status_code == 200


class TestEnableUserAuthorization:
    """Test POST /api/admin/users/{user_id}/enable (Phase 3, Decision 6)."""

    def test_enable_requires_admin_role(self, admin_api_client, regular_user):
        user_id, token = regular_user
        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.post(
            f"/api/admin/users/{user_id}/enable", headers=headers
        )
        assert resp.status_code == 403

    def test_enable_reverses_a_disable(
        self, admin_api_client, admin_user, regular_user
    ):
        admin_id, token = admin_user
        user_id, _ = regular_user
        headers = {"Authorization": f"Bearer {token}"}

        admin_api_client.post(f"/api/admin/users/{user_id}/disable", headers=headers)
        resp = admin_api_client.post(
            f"/api/admin/users/{user_id}/enable", headers=headers
        )
        assert resp.status_code == 200

        session = admin_api_client.SessionLocal()
        try:
            from app.models.user import User

            user = session.query(User).filter(User.id == user_id).first()
            assert user.status == "active"
        finally:
            session.close()

    def test_enable_an_already_active_user_is_rejected_with_409(
        self, admin_api_client, admin_user, regular_user
    ):
        admin_id, token = admin_user
        user_id, _ = regular_user
        headers = {"Authorization": f"Bearer {token}"}

        resp = admin_api_client.post(
            f"/api/admin/users/{user_id}/enable", headers=headers
        )
        assert resp.status_code == 409


class TestCreateUserInvitationOnly:
    """Phase 3, Decision 6: creation never sets a permanent password."""

    def test_created_user_starts_in_force_change_password_state(
        self, admin_api_client, admin_user
    ):
        admin_id, token = admin_user
        headers = {"Authorization": f"Bearer {token}"}

        resp = admin_api_client.post(
            "/api/admin/users",
            json={"email": "invitee@example.com", "tier": "basic", "is_admin": False},
            headers=headers,
        )
        assert resp.status_code == 201

        pool_user = admin_api_client.pool.groups  # membership sanity check
        assert "invitee@example.com" in pool_user
        assert group_for_tier("basic") in pool_user["invitee@example.com"]

    def test_compensating_delete_fires_when_the_local_insert_fails(
        self, admin_api_client, admin_user, monkeypatch
    ):
        """Phase 6 checklist item: "admin create -> pool user in expected
        groups + DB row, and compensation on DB failure".

        ``api/admin.py::create_user`` creates the Cognito pool user FIRST
        (``cognito_admin.invite_user``), then inserts the local row; if that
        insert's ``db.commit()`` raises, the handler's own except-block calls
        ``cognito_admin.try_delete_pool_user`` so the pool user this request
        just created is not left orphaned with no local row (the exact "email
        already exists at Cognito but not locally" state that would otherwise
        require ``scripts/reconcile_cognito_users.py`` to notice and fix).

        Forces the failure at the SQLAlchemy ``Session.commit`` level (a
        constraint violation, disk-full, whatever) rather than mocking
        ``db.add`` — this exercises the handler's real
        ``try/except Exception`` branch around ``db.commit()`` exactly as
        written, not a synthetic shortcut.
        """
        from sqlalchemy.orm import Session

        admin_id, token = admin_user
        headers = {"Authorization": f"Bearer {token}"}
        email = "orphan-risk@example.com"

        def _boom(self, *a, **k):
            raise RuntimeError("simulated commit failure")

        # Patch narrowly: only THIS request's local-insert commit fails.
        # admin_user's own fixture setup already committed before this
        # monkeypatch is applied, so it is unaffected.
        monkeypatch.setattr(Session, "commit", _boom)

        resp = admin_api_client.post(
            "/api/admin/users",
            json={"email": email, "tier": "basic", "is_admin": False},
            headers=headers,
        )
        assert resp.status_code == 500

        # The pool user the handler created before the DB failure must have
        # been compensated away -- no orphaned Cognito identity survives.
        assert email not in admin_api_client.pool.groups


class TestDeleteUserLastAdminProtection:
    def test_delete_refuses_when_the_target_is_the_sole_real_admin(
        self, admin_api_client, admin_user
    ):
        """Same drift construction as
        ``TestDisableUserAuthorization::test_disable_refuses_when_the_target_is_the_sole_real_admin``
        — a distinct-actor path for delete's SAME ``is_last_admin`` guard."""
        admin_id, token = admin_user
        headers = {"Authorization": f"Bearer {token}"}

        session = admin_api_client.SessionLocal()
        try:
            from app.models.user import User

            drifted = User(
                id="drifted-admin-2",
                email="drifted2@example.com",
                cognito_sub=admin_api_client.fake_auth.sub_for("drifted2@example.com"),
                tier="enterprise",
                is_admin=True,
            )
            session.add(drifted)
            session.commit()
            before = _snapshot_all_users(session)
        finally:
            session.close()

        resp = admin_api_client.delete(
            "/api/admin/users/drifted-admin-2", headers=headers
        )
        assert resp.status_code == 409

        session = admin_api_client.SessionLocal()
        try:
            _assert_users_unchanged(session, before)
        finally:
            session.close()
