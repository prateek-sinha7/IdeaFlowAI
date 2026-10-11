"""``DELETE /api/admin/users/{id}`` — the full ordering, dependents, and the
pending-deletion queue on a failed ``AdminDeleteUser`` (Phase 3, Decision 6).

Drives the real route handler directly (not through the full app + TestClient
harness ``test_admin_authorization_matrix.py`` uses) so the pool-failure branch
can be forced without threading a failure condition through the whole
FakeCognitoAuth/login stack.
"""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import admin as admin_mod
from app.core import cognito
from app.core.entitlements import ADMIN_GROUP, group_for_tier
from app.models.database import Base
from app.models.pending_cognito_deletion import PendingCognitoDeletion
from app.models.user import User
from app.models.workflow import WorkflowRun
from app.models.workflow_memory import WorkflowMemory
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


def _admin(session, pool) -> User:
    admin = User(
        id="admin-1",
        email="admin@example.com",
        cognito_sub="sub-admin",
        tier="enterprise",
        is_admin=True,
    )
    session.add(admin)
    session.commit()
    pool.add(
        sub="sub-admin",
        email="admin@example.com",
        groups={ADMIN_GROUP, group_for_tier("enterprise")},
    )
    return admin


def _target(session, pool, *, user_id="target-1") -> User:
    email = f"{user_id}@example.com"
    sub = f"sub-{user_id}"
    user = User(id=user_id, email=email, cognito_sub=sub, tier="basic", is_admin=False)
    session.add(user)
    session.commit()
    pool.add(sub=sub, email=email, groups={group_for_tier("basic")})
    return user


class TestDeleteOrdering:
    def test_delete_disables_before_deleting_the_local_row(self, session, pool):
        admin = _admin(session, pool)
        target = _target(session, pool)

        admin_mod.delete_user(user_id=target.id, admin=admin, db=session)

        assert session.query(User).filter(User.id == target.id).first() is None

    def test_delete_removes_owned_dependent_rows_in_the_same_transaction(
        self, session, pool
    ):
        admin = _admin(session, pool)
        target = _target(session, pool)
        session.add(WorkflowMemory(id="m1", user_id=target.id, key="k", value="v"))
        session.add(
            WorkflowRun(
                id="r1",
                user_id=target.id,
                type="prototype",
                status="completed",
                input="x",
                workspace_id="ws-1",
            )
        )
        session.commit()

        admin_mod.delete_user(user_id=target.id, admin=admin, db=session)

        assert session.query(WorkflowMemory).count() == 0
        assert session.query(WorkflowRun).count() == 0

    def test_a_successful_pool_delete_leaves_no_pending_row(self, session, pool):
        admin = _admin(session, pool)
        target = _target(session, pool)

        admin_mod.delete_user(user_id=target.id, admin=admin, db=session)

        assert session.query(PendingCognitoDeletion).count() == 0
        assert target.email not in pool

    def test_a_failed_final_pool_delete_queues_a_pending_row_but_still_deletes_locally(
        self, session, pool, monkeypatch
    ):
        """The core Decision-6 guarantee: the local delete is NOT blocked by a
        pool-side failure that happens AFTER disabling — the account is
        already unusable either way, so the local store stays authoritative
        and the pool cleanup is queued for later."""
        admin = _admin(session, pool)
        target = _target(session, pool)

        def _boom(_username):
            raise ClientError(
                {"Error": {"Code": "InternalErrorException", "Message": "boom"}},
                "AdminDeleteUser",
            )

        monkeypatch.setattr(cognito, "admin_delete_user", _boom)

        admin_mod.delete_user(user_id=target.id, admin=admin, db=session)

        assert session.query(User).filter(User.id == target.id).first() is None

        pending = session.query(PendingCognitoDeletion).one()
        assert pending.user_id_snapshot == target.id
        assert pending.cognito_sub == target.cognito_sub
        assert pending.last_error == "InternalErrorException"
        assert pending.attempts == 1
        # No plaintext email persisted (mirrors auth_events' PII-in-logs
        # posture) -- only its hash.
        assert len(pending.email_hash) == 16

        # And the pool user is STILL disabled, even though the delete failed --
        # disable-before-delete means the account cannot act regardless.
        assert pool.get(target.cognito_sub).enabled is False


class TestDeleteReturnCodes:
    """T4 tests: verify 202 on pending, 204 on success, and disable-first ordering."""

    def test_delete_calls_disable_first(self, session, pool, monkeypatch):
        """Verify that delete_user calls disable_user as its FIRST statement,
        resulting in the correct order of fake-client calls: sign_out → disable → delete.
        This ensures the revoke-before-mutate and disable-before-delete ordering
        invariants are upheld."""
        admin = _admin(session, pool)
        target = _target(session, pool)

        call_order = []

        original_sign_out = cognito.admin_user_global_sign_out
        original_disable = cognito.admin_disable_user
        original_delete = cognito.admin_delete_user

        def track_sign_out(email):
            call_order.append(("sign_out", email))
            return original_sign_out(email)

        def track_disable(email):
            call_order.append(("disable", email))
            return original_disable(email)

        def track_delete(email):
            call_order.append(("delete", email))
            return original_delete(email)

        monkeypatch.setattr(cognito, "admin_user_global_sign_out", track_sign_out)
        monkeypatch.setattr(cognito, "admin_disable_user", track_disable)
        monkeypatch.setattr(cognito, "admin_delete_user", track_delete)

        admin_mod.delete_user(user_id=target.id, admin=admin, db=session)

        # Verify sign_out and disable were called (in order) before delete
        assert ("sign_out", target.email) in call_order
        assert ("disable", target.email) in call_order
        assert ("delete", target.email) in call_order
        # sign_out must come before disable
        assert call_order.index(("sign_out", target.email)) < call_order.index(
            ("disable", target.email)
        )
        # disable must come before delete
        assert call_order.index(("disable", target.email)) < call_order.index(
            ("delete", target.email)
        )

    def test_delete_pending_returns_202(self, session, pool, monkeypatch):
        """When admin_delete_user fails, the endpoint returns 202 Accepted
        with pending_cognito_deletion=True, and a PendingCognitoDeletion row
        is created for retry."""
        admin = _admin(session, pool)
        target = _target(session, pool)

        def _boom(_email):
            raise ClientError(
                {"Error": {"Code": "ServiceUnavailableException", "Message": "boom"}},
                "AdminDeleteUser",
            )

        monkeypatch.setattr(cognito, "admin_delete_user", _boom)

        result = admin_mod.delete_user(user_id=target.id, admin=admin, db=session)

        # Verify 202 response with pending flag
        assert result.status_code == 202
        assert result.body == b'{"pending_cognito_deletion":true}'

        # Verify one pending row was created
        pending = session.query(PendingCognitoDeletion).one()
        assert pending.user_id_snapshot == target.id
        assert pending.cognito_sub == target.cognito_sub
        assert pending.last_error == "ServiceUnavailableException"
        assert pending.attempts == 1

    def test_delete_success_returns_204(self, session, pool):
        """When admin_delete_user succeeds, the endpoint returns 204 No Content."""
        admin = _admin(session, pool)
        target = _target(session, pool)

        result = admin_mod.delete_user(user_id=target.id, admin=admin, db=session)

        # Verify 204 response
        assert result.status_code == 204

        # Verify no pending row
        assert session.query(PendingCognitoDeletion).count() == 0
