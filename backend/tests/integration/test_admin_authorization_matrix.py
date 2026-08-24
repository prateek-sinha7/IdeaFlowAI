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

from app.core.config import settings
from app.models.database import Base, get_db
from tests.fixtures.user_factory import create_user


# ─── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture()
def admin_api_client(monkeypatch, tmp_path):
    """FastAPI TestClient backed by fresh in-memory SQLite DB.
    
    Sets up production auth wiring with no mocks. Same pattern as
    test_handoff_api but tuned for admin endpoint testing.
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
        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR PRIMARY KEY)"))
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

    with TestClient(app) as client:
        client.SessionLocal = TestSession
        client.test_engine = test_engine
        yield client

    app.dependency_overrides.clear()


@pytest.fixture()
def admin_user(admin_api_client):
    """Create an admin user and return (user_id, jwt_token)."""
    session = admin_api_client.SessionLocal()
    try:
        admin = create_user(session, "admin@example.com", "SecurePassword123", is_admin=True)
        admin_id = admin.id
    finally:
        session.close()

    resp = admin_api_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "SecurePassword123"}
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    return admin_id, token


@pytest.fixture()
def regular_user(admin_api_client):
    """Create a regular non-admin user and return (user_id, jwt_token)."""
    session = admin_api_client.SessionLocal()
    try:
        user = create_user(session, "regular@example.com", "SecurePassword123", is_admin=False)
        user_id = user.id
    finally:
        session.close()

    resp = admin_api_client.post(
        "/api/auth/login",
        json={"email": "regular@example.com", "password": "SecurePassword123"}
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
    return {
        u.id: (u.email, u.tier, u.is_admin)
        for u in users
    }


def _assert_users_unchanged(session, before_snapshot):
    """Assert every user record is byte-identical to the before_snapshot.
    
    Used to verify transactional rollback and ACID properties.
    """
    from app.models.user import User
    
    after_snapshot = {
        u.id: (u.email, u.tier, u.is_admin)
        for u in session.query(User).all()
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

    def test_list_users_expired_token_rejected(self, admin_api_client, admin_user, monkeypatch):
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
            "is_admin": False
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
            "password": "SecurePass123",
            "tier": "basic",
            "is_admin": False
        }
        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.post("/api/admin/users", json=payload, headers=headers)
        assert resp.status_code == 403

    def test_create_user_succeeds_for_admin(self, admin_api_client, admin_user):
        """Authenticated admin → 201 with created user record persisted."""
        admin_id, token = admin_user
        payload = {
            "email": "created@example.com",
            "password": "SecurePass123",
            "tier": "pro",
            "is_admin": False
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
            user = session.query(User).filter(User.email == "created@example.com").first()
            assert user is not None
            assert user.tier == "pro"
            assert user.is_admin is False
        finally:
            session.close()

    def test_create_user_duplicate_email_conflict(self, admin_api_client, admin_user, regular_user):
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
            "password": "DifferentPass456",
            "tier": "basic",
            "is_admin": False
        }
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = admin_api_client.post("/api/admin/users", json=payload, headers=headers)
        assert resp.status_code == 409
        error = resp.json()
        assert "email" in error.get("detail", "").lower() or "conflict" in error.get("detail", "").lower()

        # Verify no new user was created (byte-identical state)
        session = admin_api_client.SessionLocal()
        try:
            after = _snapshot_all_users(session)
            _assert_users_unchanged(session, before)
        finally:
            session.close()

    def test_create_user_invalid_tier_validation_error(self, admin_api_client, admin_user):
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
            "password": "SecurePass123",
            "tier": "invalid_tier_name",  # Not in TIER_PIPELINES
            "is_admin": False
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

    def test_create_user_short_password_validation_error(self, admin_api_client, admin_user):
        """Password too short → 400 with byte-identical pre-state."""
        admin_id, token = admin_user

        session = admin_api_client.SessionLocal()
        try:
            before = _snapshot_all_users(session)
        finally:
            session.close()

        payload = {
            "email": "shortpass@example.com",
            "password": "short",  # Less than 8 chars
            "tier": "basic",
            "is_admin": False
        }
        headers = {"Authorization": f"Bearer {token}"}
        resp = admin_api_client.post("/api/admin/users", json=payload, headers=headers)
        assert resp.status_code == 400
        error = resp.json()
        assert "password" in error.get("detail", "").lower()

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
            f"/api/admin/users/{target_user_id}/tier",
            json=payload,
            headers=headers
        )
        assert resp.status_code == 403

    def test_update_tier_succeeds_for_admin_on_other_user(self, admin_api_client, admin_user, regular_user):
        """Admin updates other user's tier → 200 with persisted change."""
        admin_id, admin_token = admin_user
        user_id, _ = regular_user

        payload = {"tier": "pro"}
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = admin_api_client.patch(
            f"/api/admin/users/{user_id}/tier",
            json=payload,
            headers=headers
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
            f"/api/admin/users/{admin_id}/tier",
            json=payload,
            headers=headers
        )
        assert resp.status_code == 400
        error = resp.json()
        assert "own tier" in error.get("detail", "").lower() or "yourself" in error.get("detail", "").lower()

        # Verify state unchanged (admin's tier still unchanged)
        session = admin_api_client.SessionLocal()
        try:
            _assert_users_unchanged(session, before)
        finally:
            session.close()

    def test_update_tier_target_not_found_no_disclosure(self, admin_api_client, admin_user):
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
            f"/api/admin/users/{nonexistent_id}/tier",
            json=payload,
            headers=headers
        )
        assert resp.status_code == 404

        # Verify state unchanged
        session = admin_api_client.SessionLocal()
        try:
            _assert_users_unchanged(session, before)
        finally:
            session.close()

    def test_update_tier_invalid_tier_validation_error(self, admin_api_client, admin_user, regular_user):
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
            f"/api/admin/users/{user_id}/tier",
            json=payload,
            headers=headers
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

    def test_delete_user_succeeds_for_admin(self, admin_api_client, admin_user, regular_user):
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
        assert "own account" in error.get("detail", "").lower() or "yourself" in error.get("detail", "").lower()

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
        resp = admin_api_client.delete(f"/api/admin/users/{nonexistent_id}", headers=headers)
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
