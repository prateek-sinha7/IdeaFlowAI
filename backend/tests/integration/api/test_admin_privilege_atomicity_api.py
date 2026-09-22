"""tests/integration/api/test_admin_privilege_atomicity_api.py — P1 fix
(COGNITO-AUTH-QA-BUGS.md "Privilege Mutation: Non-Atomic Cognito/DB Updates Can
Leave Stale Tokens Valid").

Lives in the INTEGRATION suite, not ``unit/``: the whole point of these tests is
real ORM ``commit()``/``refresh()`` semantics — a cutoff that survives a fresh
read after the Cognito call raised. A ``MagicMock(spec=Session)`` cannot prove
that, and the unit-suite isolation guard (``tests/unit/conftest.py``) correctly
refuses a real engine there. The self-contained engine fixture mirrors the
sibling ``test_admin_authorization_matrix.py`` in this folder.

Covers ``admin.py::update_user_tier`` / ``update_user_role``:

1. **Commit-before-Cognito ordering.** ``tokens_valid_from`` must be stamped and
   COMMITTED to the DB session BEFORE any Cognito mutation is attempted — so a
   Cognito failure (a raised ``ClientError``) still leaves the local cutoff in
   place (fail-closed: every outstanding token is revoked regardless of whether
   the provider-side change ever completes).
2. **Multi-tier-group cleanup.** ``update_user_tier`` removes EVERY stale tier
   group Cognito reports for the account (via a live ``AdminListGroupsForUser``
   read), not just the one inferred from the local ``tier`` column — closing the
   "higher-precedence conflicting group survives" gap the report calls out.

boto3 is mocked throughout — no live AWS calls, consistent with
``test_email_mfa.py`` / ``test_cognito_verifier.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registers every model on Base.metadata
from app.core import cognito
from app.models.database import Base
from app.models.user import User


@pytest.fixture
def db_session():
    """A hermetic in-memory session with the FULL model schema created.

    Deliberately shadows the Postgres-testcontainer ``db_session`` from
    ``tests/integration/conftest.py`` for this module: nothing asserted here is
    dialect-specific (commit ordering and column round-tripping only), and the
    handler's ``_to_response`` needs ``WorkflowRun`` present, which the
    ``app.models`` import above registers on ``Base.metadata``.
    """
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
        engine.dispose()


def _make_cognito_user(db, *, tier="basic") -> User:
    u = User(
        id="target-user",
        email="target@example.com",
        cognito_sub="sub-1",
        tier=tier,
        is_admin=False,
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


class _Req:
    """Minimal stand-in for UpdateTierRequest/UpdateRoleRequest."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _client_error(code: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": "boom"}}, "AdminAddUserToGroup"
    )


class TestTierUpdateAtomicity:
    def test_cutoff_committed_before_cognito_call_and_survives_cognito_failure(
        self, db_session
    ):
        """The local cutoff must be visible to a FRESH session read even if the
        Cognito mutation raises — proving commit-before-mutate, not the old
        commit-after-everything-succeeds ordering."""
        from app.api import admin as admin_mod

        user = _make_cognito_user(db_session, tier="basic")
        admin_user = _make_admin(db_session)
        before = datetime.now(timezone.utc) - timedelta(seconds=1)

        fake_client = MagicMock()
        fake_client.admin_list_groups_for_user.return_value = {
            "Groups": [{"GroupName": "flowin-tier-basic"}]
        }
        fake_client.admin_add_user_to_group.side_effect = _client_error(
            "InternalErrorException"
        )

        with patch.object(cognito, "_client", return_value=fake_client):
            with pytest.raises(HTTPException) as exc_info:
                admin_mod.update_user_tier(
                    user_id=user.id,
                    request=_Req(tier="enterprise"),
                    admin=admin_user,
                    db=db_session,
                )
        assert exc_info.value.status_code == 503

        # The cutoff committed BEFORE the failing Cognito call must still be
        # present — fail-closed even though the provider-side change never
        # completed.
        refreshed = db_session.query(User).filter(User.id == user.id).first()
        assert refreshed.tokens_valid_from is not None
        assert refreshed.tokens_valid_from.replace(tzinfo=timezone.utc) >= before
        # The local `tier` column was NOT advanced past the cutoff commit,
        # since the Cognito call failed before that final write.
        assert refreshed.tier == "basic"

    def test_removes_every_stale_tier_group_not_just_the_inferred_one(self, db_session):
        """A user somehow holding BOTH flowin-tier-basic and flowin-tier-pro (data
        corruption / a previous partial failure) must have BOTH stale groups
        removed on a tier change to enterprise — not only the one matching the
        local `tier` column."""
        from app.api import admin as admin_mod

        user = _make_cognito_user(db_session, tier="basic")
        admin_user = _make_admin(db_session)

        fake_client = MagicMock()
        # Live Cognito state has TWO tier groups, only one of which matches
        # the (advisory) local `tier` column.
        fake_client.admin_list_groups_for_user.return_value = {
            "Groups": [
                {"GroupName": "flowin-tier-basic"},
                {"GroupName": "flowin-tier-pro"},
            ]
        }

        with patch.object(cognito, "_client", return_value=fake_client):
            admin_mod.update_user_tier(
                user_id=user.id,
                request=_Req(tier="enterprise"),
                admin=admin_user,
                db=db_session,
            )

        removed_groups = {
            call.kwargs["GroupName"]
            for call in fake_client.admin_remove_user_from_group.call_args_list
        }
        assert removed_groups == {"flowin-tier-basic", "flowin-tier-pro"}
        fake_client.admin_add_user_to_group.assert_called_once()
        assert (
            fake_client.admin_add_user_to_group.call_args.kwargs["GroupName"]
            == "flowin-tier-enterprise"
        )

        refreshed = db_session.query(User).filter(User.id == user.id).first()
        assert refreshed.tier == "enterprise"


class TestRoleUpdateAtomicity:
    def test_cutoff_committed_before_cognito_call_and_survives_cognito_failure(
        self, db_session
    ):
        from app.api import admin as admin_mod

        user = _make_cognito_user(db_session)
        admin_user = _make_admin(db_session)
        before = datetime.now(timezone.utc) - timedelta(seconds=1)

        fake_client = MagicMock()
        fake_client.admin_add_user_to_group.side_effect = _client_error(
            "InternalErrorException"
        )

        with patch.object(cognito, "_client", return_value=fake_client):
            with pytest.raises(HTTPException) as exc_info:
                admin_mod.update_user_role(
                    user_id=user.id,
                    request=_Req(is_admin=True),
                    admin=admin_user,
                    db=db_session,
                )
        assert exc_info.value.status_code == 503

        refreshed = db_session.query(User).filter(User.id == user.id).first()
        assert refreshed.tokens_valid_from is not None
        assert refreshed.tokens_valid_from.replace(tzinfo=timezone.utc) >= before
        assert refreshed.is_admin is False


class TestPasswordResetAtomicity:
    def test_reset_password_rejects_permanent_field(self):
        """A body carrying ``permanent`` must be refused by the request schema.

        ``ResetPasswordRequest`` sets ``extra="forbid"``, so FastAPI answers 422
        rather than silently ignoring the field — an admin must never be able to
        believe they pinned a permanent password. Asserted against the schema
        directly (that is where the rule lives); calling the handler with a
        stand-in object would bypass validation entirely and prove nothing.
        """
        from app.api.admin import ResetPasswordRequest

        with pytest.raises(ValidationError) as exc_info:
            ResetPasswordRequest.model_validate({"permanent": True})

        assert exc_info.value.errors()[0]["type"] == "extra_forbidden"

    def test_reset_password_uses_temporary_only(self, db_session):
        """Verify that reset uses Permanent=False (temporary password)."""
        from app.api import admin as admin_mod

        user = _make_cognito_user(db_session)
        admin_user = _make_admin(db_session)

        fake_client = MagicMock()

        with patch.object(cognito, "_client", return_value=fake_client):
            admin_mod.reset_user_password(
                user_id=user.id,
                request=_Req(),
                admin=admin_user,
                db=db_session,
            )

        # Verify AdminSetUserPassword was called with Permanent=False
        fake_client.admin_set_user_password.assert_called_once()
        call_kwargs = fake_client.admin_set_user_password.call_args.kwargs
        assert call_kwargs["Permanent"] is False

    def test_reset_password_advances_cutoff_and_signs_out(self, db_session):
        """Verify tokens_valid_from is increased and sign-out is called."""
        from app.api import admin as admin_mod

        user = _make_cognito_user(db_session)
        admin_user = _make_admin(db_session)
        before = datetime.now(timezone.utc) - timedelta(seconds=1)

        fake_client = MagicMock()

        with patch.object(cognito, "_client", return_value=fake_client):
            admin_mod.reset_user_password(
                user_id=user.id,
                request=_Req(),
                admin=admin_user,
                db=db_session,
            )

        # Verify tokens_valid_from was advanced
        refreshed = db_session.query(User).filter(User.id == user.id).first()
        assert refreshed.tokens_valid_from is not None
        assert refreshed.tokens_valid_from.replace(tzinfo=timezone.utc) >= before

        # Verify AdminUserGlobalSignOut was called exactly once
        assert (
            fake_client.admin_user_global_sign_out.call_count == 1
        ), "AdminUserGlobalSignOut should be called exactly once"
