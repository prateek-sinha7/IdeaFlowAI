"""``users.status`` as a real access control, and the care taken to set it.

Two halves of Decision 6 of the Cognito-only auth migration
(``.kiro/specs/login/prompt.md``):

**Enforcement** -- ``core.identity.resolve_principal`` rejects any row whose
``status`` is not ``active``, whatever the token says. This matters because AWS
documents that a Cognito access token stays offline-verifiable until its own
``exp`` no matter what happens at the pool: ``AdminDisableUser`` alone cannot end
a session already in flight, so without a local check "disabled" would be a label
rather than a control.

**Attribution** -- the far more delicate half, and the reason this file leans on
it. The brief is explicit that a refresh rejection must NOT be taken as proof the
account was disabled ("only mark when ``AdminGetUser`` confirms disabled/missing;
otherwise return 401 without mutating"). AWS returns
``NotAuthorizedException`` for a whole family of ordinary, benign causes -- a
plain logout revoked the refresh token, it aged past the app client's validity
window, an ``AdminUserGlobalSignOut`` fired for a routine tier change, the stored
ciphertext is stale. Treating any of those as "disabled" would lock a user out
PERMANENTLY, since ``resolve_principal`` then refuses every future token,
including one from a fresh successful login. The asymmetry is deliberate: a
spurious 401 costs one sign-in, a spurious ``disabled`` costs the account until
an operator intervenes.
"""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.auth import _reconcile_status_on_refresh_rejection
from app.core import cognito
from app.core.identity import Principal, resolve_principal
from app.models.database import Base
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


def _seed(session, *, status: str = "active") -> User:
    user = User(
        id="u1",
        email="person@example.com",
        cognito_sub="sub-1",
        tier="pro",
        status=status,
    )
    session.add(user)
    session.commit()
    return user


def _principal(sub: str = "sub-1") -> Principal:
    return Principal(provider="cognito", sub=sub, jti="j", iat=1_700_000_000)


class TestEnforcement:
    def test_an_active_row_resolves(self, session, pool):
        user = _seed(session)

        assert resolve_principal(_principal(), session) is user

    def test_a_disabled_row_is_rejected_despite_a_valid_token(self, session, pool):
        _seed(session, status="disabled")

        assert resolve_principal(_principal(), session) is None

    def test_an_unrecognised_status_is_rejected_too(self, session, pool):
        """Fail closed on anything that is not exactly ``active`` -- a typo'd or
        future status value must deny, not accidentally permit."""
        _seed(session, status="suspended")

        assert resolve_principal(_principal(), session) is None


class TestRefreshRejectionAttribution:
    def test_a_missing_pool_user_is_confirmed_and_marked_disabled(
        self, session, pool, caplog
    ):
        user = _seed(session)  # pool is empty -> AdminGetUser raises UserNotFound

        _reconcile_status_on_refresh_rejection(user, session)

        session.refresh(user)
        assert user.status == "disabled"

    def test_an_explicitly_disabled_pool_user_is_marked_disabled(self, session, pool):
        user = _seed(session)
        pool.add(sub="sub-1", email="person@example.com", enabled=False)

        _reconcile_status_on_refresh_rejection(user, session)

        session.refresh(user)
        assert user.status == "disabled"

    def test_an_enabled_pool_user_is_left_alone(self, session, pool):
        """The benign case that must NOT mutate: the account is fine at the pool
        and the refresh token was merely revoked or expired. Marking this
        disabled would be a permanent lockout on an ordinary logout."""
        user = _seed(session)
        pool.add(sub="sub-1", email="person@example.com", enabled=True)

        _reconcile_status_on_refresh_rejection(user, session)

        session.refresh(user)
        assert user.status == "active"

    def test_an_unreachable_provider_is_left_alone(self, session, monkeypatch):
        """ "We could not check" must never be recorded as "we confirmed it is
        gone" -- otherwise a Cognito outage disables every user who happens to
        refresh during it."""
        user = _seed(session)

        def _boom(_username):
            raise RuntimeError("endpoint connection error")

        monkeypatch.setattr(cognito, "admin_get_user", _boom)

        _reconcile_status_on_refresh_rejection(user, session)

        session.refresh(user)
        assert user.status == "active"

    def test_a_throttled_provider_is_left_alone(self, session, monkeypatch):
        """A ClientError that is NOT UserNotFoundException is inconclusive: only
        UserNotFoundException is authoritative on a read API."""
        user = _seed(session)

        def _throttled(_username):
            raise ClientError(
                {"Error": {"Code": "TooManyRequestsException", "Message": "slow down"}},
                "AdminGetUser",
            )

        monkeypatch.setattr(cognito, "admin_get_user", _throttled)

        _reconcile_status_on_refresh_rejection(user, session)

        session.refresh(user)
        assert user.status == "active"

    def test_the_lookup_uses_the_canonical_sub_not_the_email(
        self, session, monkeypatch
    ):
        """Reads go through ``cognito_sub``. Passing the email would still work
        against a real pool (it is an alias) but would break the moment an
        operator changed the address, so the contract is pinned here."""
        user = _seed(session)
        seen: list[str] = []

        def _record(username):
            seen.append(username)
            raise ClientError(
                {"Error": {"Code": "UserNotFoundException", "Message": "gone"}},
                "AdminGetUser",
            )

        monkeypatch.setattr(cognito, "admin_get_user", _record)

        _reconcile_status_on_refresh_rejection(user, session)

        assert seen == ["sub-1"]
