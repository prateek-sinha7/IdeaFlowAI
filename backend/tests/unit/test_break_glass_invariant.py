"""Break-glass admin invariants (COGNITO-MIGRATION-PLAN §5.6, Phase 5 step 4).

The break-glass account's justification is that there is exactly ONE of it,
documented and alarmed. These tests pin the fail-closed behaviour when that
assumption is violated, because the failure mode is silent otherwise: an extra
local admin row simply works, and nobody notices an unaudited privileged
credential exists.

Offline by design — no AWS calls. The local/legacy credential path is pure
local logic (bcrypt + HS256 + a DB lookup), so it is fully testable without a
Cognito pool.
"""
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.identity import (
    Principal,
    _local_admin_credential_is_permitted,
    resolve_principal,
)
from app.models.database import Base
from app.models.revoked_token import RevokedToken  # noqa: F401 - register table
from app.models.chat import ChatSession, Message  # noqa: F401 - register tables
from app.models.workflow import WorkflowRun  # noqa: F401 - register table
from app.models.user import User


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _add_user(db, *, is_admin: bool, auth_provider: str, email: str | None = None) -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=email or f"{uuid.uuid4().hex[:8]}@example.com",
        password_hash="$2b$12$fake" if auth_provider == "local" else None,
        auth_provider=auth_provider,
        is_admin=is_admin,
        tier="enterprise",
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def break_glass_on(monkeypatch):
    monkeypatch.setattr(settings, "BREAK_GLASS_ENABLED", True)


class TestSingleRowInvariant:
    def test_exactly_one_local_admin_is_permitted(self, db, break_glass_on):
        _add_user(db, is_admin=True, auth_provider="local")
        assert _local_admin_credential_is_permitted(db) is True

    def test_two_local_admins_fail_closed(self, db, break_glass_on):
        _add_user(db, is_admin=True, auth_provider="local")
        _add_user(db, is_admin=True, auth_provider="local")
        assert _local_admin_credential_is_permitted(db) is False

    def test_zero_local_admins_is_not_permitted(self, db, break_glass_on):
        assert _local_admin_credential_is_permitted(db) is False

    def test_kill_switch_overrides_a_valid_single_row(self, db, monkeypatch):
        _add_user(db, is_admin=True, auth_provider="local")
        monkeypatch.setattr(settings, "BREAK_GLASS_ENABLED", False)
        assert _local_admin_credential_is_permitted(db) is False

    def test_cognito_admins_do_not_count_toward_the_invariant(self, db, break_glass_on):
        """Only auth_provider='local' admins are break-glass accounts.

        A deployment with many Cognito admins and one local admin still
        satisfies the invariant — otherwise the control would misfire on every
        normally-administered environment.
        """
        _add_user(db, is_admin=True, auth_provider="local")
        for _ in range(3):
            _add_user(db, is_admin=True, auth_provider="cognito")
        assert _local_admin_credential_is_permitted(db) is True


class TestResolvePrincipalEnforcement:
    """resolve_principal must apply the gate, not just expose it."""

    def test_local_admin_rejected_when_invariant_violated(self, db, break_glass_on):
        admin = _add_user(db, is_admin=True, auth_provider="local")
        _add_user(db, is_admin=True, auth_provider="local")  # second one breaks it

        principal = Principal(provider="local", sub=admin.id, jti="j", iat=0)
        assert resolve_principal(principal, db) is None

    def test_local_admin_resolves_when_invariant_holds(self, db, break_glass_on):
        admin = _add_user(db, is_admin=True, auth_provider="local")

        principal = Principal(provider="local", sub=admin.id, jti="j", iat=0)
        resolved = resolve_principal(principal, db)
        assert resolved is not None
        assert resolved.id == admin.id

    def test_non_admin_local_user_is_unaffected_by_the_invariant(self, db, break_glass_on):
        """The gate targets the PRIVILEGED local path only.

        A non-admin local user (e.g. a pre-migration account during the
        dual-accept window) must keep working regardless of how many local
        admins exist — breaking those logins would turn a break-glass
        misconfiguration into a full outage.
        """
        _add_user(db, is_admin=True, auth_provider="local")
        _add_user(db, is_admin=True, auth_provider="local")  # invariant violated
        plain = _add_user(db, is_admin=False, auth_provider="local")

        principal = Principal(provider="local", sub=plain.id, jti="j", iat=0)
        resolved = resolve_principal(principal, db)
        assert resolved is not None
        assert resolved.id == plain.id

    def test_cognito_principal_resolves_by_cognito_sub(self, db, break_glass_on):
        user = _add_user(db, is_admin=False, auth_provider="cognito")
        user.cognito_sub = "pool-sub-123"
        db.commit()

        principal = Principal(provider="cognito", sub="pool-sub-123", jti="j", iat=0)
        resolved = resolve_principal(principal, db)
        assert resolved is not None
        assert resolved.id == user.id

    def test_cognito_principal_never_matches_a_local_users_id(self, db, break_glass_on):
        """A Cognito `sub` must never be resolved against users.id.

        Conflating the two namespaces would let a Cognito token authenticate as
        an arbitrary local row whose UUID happened to match. The two lookups
        are keyed on different columns precisely to prevent this.
        """
        local_user = _add_user(db, is_admin=True, auth_provider="local")

        principal = Principal(provider="cognito", sub=local_user.id, jti="j", iat=0)
        assert resolve_principal(principal, db) is None
