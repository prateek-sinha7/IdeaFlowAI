"""``core.cognito_admin`` — the ordering invariants, exercised directly.

Phase 3 of the Cognito-only auth migration (``.kiro/specs/login/prompt.md``,
Decision 6). These tests call the lifecycle functions directly against
``FakeCognitoPool`` rather than through the HTTP layer (that coverage lives in
``tests/integration/api/test_admin_authorization_matrix.py``), so each ordering
invariant can be pinned in isolation: commit-before-mutate, disable-before-
delete, idempotent ``UserNotFoundException``, and the last-admin check.

Lives in ``tests/integration/external/`` because the subject is the adapter over a
stubbed third-party provider: the Cognito side is faked end-to-end by
``FakeCognitoPool``, while the LOCAL side must be a real session — the whole point of
commit-before-mutate is that the cutoff is durable BEFORE the provider call, which
only a real ``commit()`` can demonstrate. A mocked Session would let the ordering
assertions pass against a recording of calls that never persisted anything. Offline
and fast regardless: no AWS, no network, hermetic in-memory engine. The unit-suite
isolation guard (``tests/unit/conftest.py``) correctly refuses a real DB connection
there.
"""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import cognito, cognito_admin
from app.core.entitlements import ADMIN_GROUP, group_for_tier
from app.models.database import Base
from app.models.handoff import UserApiKey
from app.models.user import User
from tests.fakes.cognito_pool import FakeCognitoPool


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def pool(monkeypatch) -> FakeCognitoPool:
    return FakeCognitoPool().install(monkeypatch)


def _seed(session, pool, *, email="target@example.com", tier="basic", is_admin=False):
    sub = f"sub-{email}"
    pool.add(
        sub=sub,
        email=email,
        groups={group_for_tier(tier)} | ({ADMIN_GROUP} if is_admin else set()),
    )
    user = User(
        id=f"id-{email}",
        email=email,
        cognito_sub=sub,
        tier=tier,
        is_admin=is_admin,
        status="active",
    )
    session.add(user)
    session.commit()
    return user


class TestInviteUser:
    def test_invite_creates_a_pool_user_and_assigns_groups(self, session, pool):
        created = cognito_admin.invite_user(
            "new@example.com", tier="pro", is_admin=True
        )

        assert created.email == "new@example.com"
        assert created.tier == "pro"
        assert created.is_admin is True
        pool_user = pool.get(created.cognito_sub)
        assert pool_user is not None
        assert group_for_tier("pro") in pool_user.groups
        assert ADMIN_GROUP in pool_user.groups

    def test_invite_never_sets_a_password(self, session, pool, monkeypatch):
        """The whole point of Phase 3, Decision 6: no AdminSetUserPassword call
        anywhere in the create path."""
        calls: list[str] = []
        monkeypatch.setattr(
            cognito,
            "admin_set_user_password",
            lambda *a, **k: calls.append("called"),
        )

        cognito_admin.invite_user("nopass@example.com", tier="basic", is_admin=False)

        assert calls == []

    def test_invite_sends_an_email_invitation(self, session, pool):
        created = cognito_admin.invite_user(
            "invited@example.com", tier="basic", is_admin=False
        )

        assert pool.get(created.cognito_sub).invited_via == ["EMAIL"]

    def test_invite_raises_conflict_on_duplicate_email(self, session, pool):
        pool.add(sub="existing-sub", email="dupe@example.com")

        with pytest.raises(cognito_admin.ConflictError):
            cognito_admin.invite_user("dupe@example.com", tier="basic", is_admin=False)

    def test_invite_group_failure_compensates(self, session, pool, monkeypatch):
        """T5: When group assignment fails after create, AdminDeleteUser is called
        to compensate, and a ProviderUnavailableError is raised. The pool user is
        deleted and no local User row is created."""

        def _boom(_email, _group):
            raise ClientError(
                {"Error": {"Code": "InternalErrorException", "Message": "boom"}},
                "AdminAddUserToGroup",
            )

        monkeypatch.setattr(cognito, "admin_add_user_to_group", _boom)

        with pytest.raises(cognito_admin.ProviderUnavailableError):
            cognito_admin.invite_user("fail@example.com", tier="basic", is_admin=False)

        # Verify the pool user was deleted as compensation
        assert "fail@example.com" not in pool


class TestChangeTier:
    def test_commits_tokens_valid_from_before_the_cognito_mutation(
        self, session, pool, monkeypatch
    ):
        user = _seed(session, pool, tier="basic")
        before = user.tokens_valid_from

        def _boom(*a, **k):
            raise ClientError(
                {"Error": {"Code": "InternalErrorException", "Message": "boom"}},
                "AdminAddUserToGroup",
            )

        monkeypatch.setattr(cognito, "admin_add_user_to_group", _boom)

        with pytest.raises(cognito_admin.ProviderUnavailableError):
            cognito_admin.change_tier(user, "enterprise", session)

        # Re-read from a fresh query to prove it was actually COMMITTED, not
        # just mutated on the in-memory instance.
        refreshed = session.query(User).filter(User.id == user.id).first()
        assert refreshed.tokens_valid_from is not None
        assert refreshed.tokens_valid_from != before
        # The local `tier` column was NOT advanced -- the failure happened
        # before that final write.
        assert refreshed.tier == "basic"

    def test_removes_every_stale_tier_group(self, session, pool):
        user = _seed(session, pool, tier="basic")
        # Simulate accumulated drift: the pool user holds TWO tier groups.
        pool.get(user.cognito_sub).groups.add(group_for_tier("pro"))

        cognito_admin.change_tier(user, "enterprise", session)

        pool_groups = pool.get(user.cognito_sub).groups
        assert group_for_tier("basic") not in pool_groups
        assert group_for_tier("pro") not in pool_groups
        assert group_for_tier("enterprise") in pool_groups
        assert user.tier == "enterprise"


class TestChangeRole:
    def test_commits_tokens_valid_from_before_the_cognito_mutation(
        self, session, pool, monkeypatch
    ):
        user = _seed(session, pool, is_admin=False)

        def _boom(*a, **k):
            raise ClientError(
                {"Error": {"Code": "InternalErrorException", "Message": "boom"}},
                "AdminAddUserToGroup",
            )

        monkeypatch.setattr(cognito, "admin_add_user_to_group", _boom)

        with pytest.raises(cognito_admin.ProviderUnavailableError):
            cognito_admin.change_role(user, True, session)

        refreshed = session.query(User).filter(User.id == user.id).first()
        assert refreshed.tokens_valid_from is not None
        assert refreshed.is_admin is False


class TestDisableUser:
    def test_disable_revokes_sign_in_and_local_state(self, session, pool):
        user = _seed(session, pool)
        key = UserApiKey(
            id="k1", user_id=user.id, token_prefix="flowin_1", token_hash="h" * 64
        )
        session.add(key)
        user.encrypted_cognito_refresh_token = "cipher"
        session.commit()

        cognito_admin.disable_user(user, session)

        assert user.status == "disabled"
        assert user.encrypted_cognito_refresh_token is None
        assert pool.get(user.cognito_sub).enabled is False
        session.refresh(key)
        assert key.revoked_at is not None

    def test_disable_tolerates_a_pool_user_already_absent(self, session, pool):
        """Idempotent UserNotFoundException (module docstring) -- re-running a
        disable after a prior partial failure must converge, not raise."""
        user = User(
            id="ghost",
            email="ghost@example.com",
            cognito_sub="no-such-sub",
            tier="basic",
        )
        session.add(user)
        session.commit()

        cognito_admin.disable_user(user, session)  # must not raise

        assert user.status == "disabled"

    def test_disable_does_not_restore_on_a_second_call(self, session, pool):
        """Calling disable twice must not un-revoke anything -- confirms the
        idempotent path does not accidentally reset already-revoked state."""
        user = _seed(session, pool)
        key = UserApiKey(
            id="k1", user_id=user.id, token_prefix="flowin_1", token_hash="h" * 64
        )
        session.add(key)
        session.commit()

        cognito_admin.disable_user(user, session)
        first_revoked_at = key.revoked_at
        cognito_admin.disable_user(user, session)

        session.refresh(key)
        assert key.revoked_at == first_revoked_at


class TestEnableUser:
    def test_enable_reverses_disable_but_not_revocations(self, session, pool):
        user = _seed(session, pool)
        key = UserApiKey(
            id="k1", user_id=user.id, token_prefix="flowin_1", token_hash="h" * 64
        )
        session.add(key)
        session.commit()
        cognito_admin.disable_user(user, session)

        cognito_admin.enable_user(user, session)

        assert user.status == "active"
        assert pool.get(user.cognito_sub).enabled is True
        # API keys stay revoked -- re-enabling a login is not consent to
        # un-revoke a credential (module docstring).
        session.refresh(key)
        assert key.revoked_at is not None


class TestDeleteUser:
    def test_delete_disables_before_any_local_row_is_touched(self, session, pool):
        user = _seed(session, pool)

        cognito_admin.delete_user(user, session)

        assert pool.get(user.cognito_sub).enabled is False
        # The local row is untouched by this function -- that's the caller's
        # job (delete_user_dependents + db.delete), per the module docstring.
        assert session.query(User).filter(User.id == user.id).first() is not None

    def test_delete_tolerates_a_pool_user_already_absent(self, session, pool):
        user = User(
            id="ghost2", email="ghost2@example.com", cognito_sub="gone", tier="basic"
        )
        session.add(user)
        session.commit()

        cognito_admin.delete_user(user, session)  # must not raise


class TestTryDeletePoolUser:
    def test_returns_none_on_success(self, session, pool):
        user = _seed(session, pool)

        assert cognito_admin.try_delete_pool_user(user.email) is None
        assert user.email not in pool

    def test_returns_none_when_already_absent(self, session, pool):
        assert cognito_admin.try_delete_pool_user("nobody@example.com") is None

    def test_returns_the_error_code_on_a_real_failure(self, session, pool, monkeypatch):
        def _boom(_email):
            raise ClientError(
                {"Error": {"Code": "InternalErrorException", "Message": "boom"}},
                "AdminDeleteUser",
            )

        monkeypatch.setattr(cognito, "admin_delete_user", _boom)

        assert (
            cognito_admin.try_delete_pool_user("x@example.com")
            == "InternalErrorException"
        )


class TestIsLastAdmin:
    def test_true_when_exactly_one_admin(self, session, pool):
        user = _seed(session, pool, is_admin=True)

        assert cognito_admin.is_last_admin(user) is True

    def test_false_when_multiple_admins(self, session, pool):
        a = _seed(session, pool, email="a@example.com", is_admin=True)
        _seed(session, pool, email="b@example.com", is_admin=True)

        assert cognito_admin.is_last_admin(a) is False

    def test_true_when_zero_admins_somehow_remain(self, session, pool):
        """When the admin group is empty (or the user is not in it), return False
        because there is no last-admin concern. The user is not an admin."""
        # Create a user not in the admin group
        user = User(
            id="nobody",
            email="nobody@example.com",
            cognito_sub="sub-nobody",
            tier="basic",
            is_admin=False,
        )
        session.add(user)
        session.commit()
        # Add to pool but without admin group
        pool.add(sub="sub-nobody", email="nobody@example.com", groups=set())

        # User is not in admin group, so not a last-admin concern
        assert cognito_admin.is_last_admin(user) is False

    def test_t6_drift_detection_db_false_cognito_true(self, session, pool):
        """T6: A user with is_admin=False in DB but in the admin group in Cognito
        is still counted as a last admin when they are the sole group member."""
        # Create a user in Cognito admin group but with is_admin=False locally
        user = User(
            id="drifted",
            email="drifted@example.com",
            cognito_sub="sub-drifted",
            tier="enterprise",
            is_admin=False,  # Local DB says not admin
        )
        session.add(user)
        session.commit()
        # Add to pool in the admin group
        pool.add(sub="sub-drifted", email="drifted@example.com", groups={ADMIN_GROUP})

        # Should still be treated as last admin
        assert cognito_admin.is_last_admin(user) is True

    def test_t6_two_admins_in_cognito(self, session, pool):
        """T6: Two admins in Cognito group → not last admin."""
        a = _seed(session, pool, email="a@example.com", is_admin=True)
        _seed(session, pool, email="b@example.com", is_admin=True)

        assert cognito_admin.is_last_admin(a) is False

    def test_last_admin_detected_when_db_projection_stale(self, session, pool):
        """T6b: a stale ``is_admin=False`` row must not defeat the 409.

        Asserts the REFUSAL, not the boolean. ``test_t6_drift_detection_...``
        above already pins ``is_last_admin`` returning True for this shape; what
        that cannot show is whether the endpoint acts on it. Those are separate
        failures -- the predicate could be right while the caller short-circuits
        on ``user.is_admin`` and never asks -- and only the second one actually
        empties the admin group.

        Scenario: the sole member of the Cognito admin group carries
        ``is_admin=False`` locally (added via the AWS console, so the projection
        never learned about them). Demoting them would leave zero admins.
        """
        from fastapi import HTTPException

        from app.api.admin import UpdateRoleRequest, update_user_role

        # Sole member of the admin group in Cognito, but the DB disagrees.
        pool.add(sub="sub-stale", email="stale@example.com", groups={ADMIN_GROUP})
        target = User(
            id="id-stale",
            email="stale@example.com",
            cognito_sub="sub-stale",
            tier="enterprise",
            is_admin=False,  # the stale projection under test
            status="active",
        )
        session.add(target)

        # The actor is deliberately NOT in the pool's admin group: adding them
        # would make the group two-strong and the guard would correctly decline
        # to fire, so the test would pass for the wrong reason. `require_admin`
        # is bypassed here (the dependency is passed directly), so the actor
        # needs no real group membership to drive the endpoint.
        actor = User(
            id="id-actor",
            email="actor@example.com",
            cognito_sub="sub-actor",
            tier="enterprise",
            is_admin=True,
            status="active",
        )
        session.add(actor)
        session.commit()

        with pytest.raises(HTTPException) as exc:
            update_user_role(
                user_id=target.id,
                request=UpdateRoleRequest(is_admin=False),
                admin=actor,
                db=session,
            )

        assert exc.value.status_code == 409
        assert "last remaining administrator" in str(exc.value.detail)
        # The refusal must leave the group intact -- a guard that raises after
        # already removing the group would be worse than no guard.
        assert ADMIN_GROUP in cognito.admin_list_groups_for_user("stale@example.com")

    def test_is_last_admin_returns_false_when_user_absent_from_pool(
        self, session, pool
    ):
        """When a local ``is_admin=True`` row has no corresponding pool identity,
        the guard returns False (no admin rights to protect).

        This closes a gap where a dev-pool-recreated scenario would fail to block
        a demotion that left zero pool admins: the local projection would claim
        the row is admin, but ListGroupsForUser would raise UserNotFoundException
        (authoritative: no pool identity). The original code treated that as
        "assume they might be admin", but read APIs are outside
        prevent_user_existence_errors (see cognito.py:437-441), so the absence
        is definitive.
        """
        # Local row claims admin, but pool has no such identity
        user = User(
            id="orphaned",
            email="orphaned@example.com",
            cognito_sub="sub-orphaned",
            tier="enterprise",
            is_admin=True,  # Local DB says admin, but pool user is gone
            status="active",
        )
        session.add(user)
        session.commit()

        # Pool does NOT contain this user (e.g. pool was recreated), so
        # admin_list_groups_for_user will raise UserNotFoundException
        assert "orphaned@example.com" not in pool

        # The guard must return False, not raise or treat it as "maybe admin"
        assert cognito_admin.is_last_admin(user) is False


class TestThrottleRetry:
    def test_retries_once_on_throttling_then_succeeds(self, session, pool, monkeypatch):
        attempts = {"n": 0}
        real_add = cognito.admin_add_user_to_group

        def _flaky(email, group):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ClientError(
                    {"Error": {"Code": "TooManyRequestsException", "Message": "slow"}},
                    "AdminAddUserToGroup",
                )
            return real_add(email, group)

        monkeypatch.setattr(cognito, "admin_add_user_to_group", _flaky)
        monkeypatch.setattr(
            cognito_admin, "_THROTTLE_RETRY_DELAY_SECONDS", 0
        )  # don't actually sleep in tests

        user = _seed(session, pool, tier="basic")
        cognito_admin.change_tier(user, "enterprise", session)

        assert attempts["n"] == 2
        assert user.tier == "enterprise"

    def test_does_not_retry_a_non_throttle_error(self, session, pool, monkeypatch):
        attempts = {"n": 0}

        def _always_fails(*a, **k):
            attempts["n"] += 1
            raise ClientError(
                {"Error": {"Code": "InvalidParameterException", "Message": "bad"}},
                "AdminAddUserToGroup",
            )

        monkeypatch.setattr(cognito, "admin_add_user_to_group", _always_fails)

        user = _seed(session, pool, tier="basic")
        with pytest.raises(cognito_admin.ProviderUnavailableError):
            cognito_admin.change_tier(user, "enterprise", session)

        assert attempts["n"] == 1
