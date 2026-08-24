"""tests/unit/test_admin_privilege_atomicity.py — P1 fix (COGNITO-AUTH-QA-BUGS.md
"Privilege Mutation: Non-Atomic Cognito/DB Updates Can Leave Stale Tokens Valid").

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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import cognito
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


def _make_cognito_user(db, *, tier="basic") -> User:
    u = User(
        id="target-user",
        email="target@example.com",
        cognito_sub="sub-1",
        auth_provider="cognito",
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
        auth_provider="cognito",
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
    return ClientError({"Error": {"Code": code, "Message": "boom"}}, "AdminAddUserToGroup")


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
