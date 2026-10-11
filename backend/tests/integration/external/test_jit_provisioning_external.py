"""Just-in-time provisioning of local rows from Cognito identities.

Covers Decision 4 of the Cognito-only auth migration
(``.kiro/specs/login/prompt.md``): the two entry points (``provision_from_login`` on the
login path, ``provision_from_token_sub`` on the token path), the negative-result refusal
cache, the ``resolve_principal`` JIT hook, and the role-projection refresh.

Importantly it covers the cases where provisioning must REFUSE — a provisioning bug that
fails open would hand an authenticated foothold to a disabled or ambiguous identity.

Lives in ``tests/integration/external/`` for the same reason as
``test_cognito_admin_lifecycle_external.py``: the subject is an adapter over a stubbed
third-party provider. The Cognito side is faked end-to-end by ``FakeCognitoPool``, while
the LOCAL side must be a real session, because what is being asserted IS the persistence
outcome — that exactly ONE row is created, that repeated calls are idempotent rather than
duplicating, that a concurrent winner is re-read instead of raising, that an email held by
a different sub is refused, and that a stale projection is rewritten only by a NEWER
token. Those are statements about rows and uniqueness constraints; a mocked Session would
let every one of them pass vacuously. Offline and fast regardless: no AWS, no network,
hermetic in-memory engine. The unit-suite isolation guard (``tests/unit/conftest.py``)
correctly refuses a real DB connection there.

The premise this whole design rests on — that ``AdminGetUser`` resolves a ``sub`` as
``Username``, discharging the proof obligation in ``MERGE_NOTES.md`` §6 — needs no
database and stays in ``tests/unit/api/test_jit_provisioning.py``.
"""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import cognito, provisioning
from app.core.entitlements import ADMIN_GROUP, group_for_tier
from app.core.identity import Principal, resolve_principal
from app.core.provisioning import (
    ProvisioningRefused,
    provision_from_login,
    provision_from_token_sub,
    refresh_projection_if_stale,
)
from app.models.database import Base
from app.models.user import User
from tests.fakes.cognito_pool import FakeCognitoPool


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = maker()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def pool(monkeypatch) -> FakeCognitoPool:
    return FakeCognitoPool().install(monkeypatch)


def _principal(sub: str, *, groups: list[str] | None = None, iat: int = 1_700_000_000):
    return Principal(
        provider="cognito", sub=sub, jti="jti-1", iat=iat, groups=groups or []
    )


# ─── Token path (Decision 4b) ───────────────────────────────────────────────


class TestProvisionFromTokenSub:
    def test_provision_from_token_sub_creates_a_row_when_none_exists(
        self, session, pool
    ):
        pool.add(
            sub="sub-1",
            email="console@example.com",
            groups={group_for_tier("pro"), ADMIN_GROUP},
        )

        user = provision_from_token_sub(
            session, sub="sub-1", groups=[group_for_tier("pro"), ADMIN_GROUP]
        )

        assert user is not None
        assert user.cognito_sub == "sub-1"
        assert user.email == "console@example.com"
        assert user.status == "active"
        assert user.roles_synced_at is not None
        # Projection seeded from groups -- advisory, but it must not be WRONG.
        assert user.tier == "pro"
        assert user.is_admin is True

    def test_provision_from_token_sub_returns_none_when_pool_user_is_absent(
        self, session, pool
    ):
        assert provision_from_token_sub(session, sub="ghost", groups=[]) is None
        assert session.query(User).count() == 0

    def test_provision_from_token_sub_refuses_a_disabled_pool_user(self, session, pool):
        """A disabled account must gain no foothold, even holding a valid token.

        AdminDisableUser cannot revoke an access token already issued -- it stays
        offline-valid until its own exp -- so refusing to provision is part of
        what makes 'disabled' meaningful rather than cosmetic.
        """
        pool.add(sub="sub-off", email="off@example.com", enabled=False)

        assert provision_from_token_sub(session, sub="sub-off", groups=[]) is None
        assert session.query(User).count() == 0

    def test_provision_from_token_sub_fails_closed_when_cognito_is_unreachable(
        self, session, monkeypatch
    ):
        def _boom(_username):
            raise RuntimeError("no credentials configured")

        monkeypatch.setattr(cognito, "admin_get_user", _boom)

        assert provision_from_token_sub(session, sub="sub-1", groups=[]) is None
        assert session.query(User).count() == 0

    def test_provision_from_token_sub_refuses_a_pool_user_with_no_email(
        self, session, pool, monkeypatch
    ):
        monkeypatch.setattr(
            cognito,
            "admin_get_user",
            lambda _u: {
                "Enabled": True,
                "UserAttributes": [{"Name": "sub", "Value": "s"}],
            },
        )

        assert provision_from_token_sub(session, sub="s", groups=[]) is None
        assert session.query(User).count() == 0

    def test_provisioning_is_idempotent_across_repeated_calls(self, session, pool):
        pool.add(sub="sub-1", email="one@example.com")

        first = provision_from_token_sub(session, sub="sub-1", groups=[])
        second = provision_from_token_sub(session, sub="sub-1", groups=[])

        assert first is not None and second is not None
        assert first.id == second.id
        assert session.query(User).count() == 1


# ─── Refusal negative cache ─────────────────────────────────────────────────


class TestRefusalCache:
    """A refused sub must not cost an AdminGetUser on every subsequent request.

    Without the cache, a holder of a valid-but-unprovisionable token (deleted or
    disabled pool user) turns each request into a Cognito Admin API call, which
    is both a cost and a throttling surface an unauthenticated-ish caller
    controls.
    """

    @pytest.fixture()
    def counted_pool(self, pool, monkeypatch):
        """Wrap the fake pool's AdminGetUser with a call counter."""
        calls: list[str] = []
        original = cognito.admin_get_user

        def _counting(username):
            calls.append(username)
            return original(username)

        monkeypatch.setattr(cognito, "admin_get_user", _counting)
        return calls

    def test_provision_from_token_sub_skips_cognito_when_the_sub_was_just_refused(
        self, session, counted_pool
    ):
        assert provision_from_token_sub(session, sub="ghost", groups=[]) is None
        assert len(counted_pool) == 1

        assert provision_from_token_sub(session, sub="ghost", groups=[]) is None

        assert len(counted_pool) == 1, "second call must be served from the cache"
        assert session.query(User).count() == 0

    def test_provision_from_token_sub_caches_a_disabled_pool_user_refusal(
        self, session, counted_pool, pool
    ):
        pool.add(sub="sub-off", email="off@example.com", enabled=False)

        assert provision_from_token_sub(session, sub="sub-off", groups=[]) is None
        assert provision_from_token_sub(session, sub="sub-off", groups=[]) is None

        assert len(counted_pool) == 1
        assert session.query(User).count() == 0

    def test_provision_from_token_sub_queries_cognito_again_when_the_entry_expired(
        self, session, counted_pool
    ):
        assert provision_from_token_sub(session, sub="ghost", groups=[]) is None
        assert len(counted_pool) == 1

        # Age the entry past its 60 s TTL.
        provisioning._refusal_cache["ghost"] -= 61

        assert provision_from_token_sub(session, sub="ghost", groups=[]) is None

        assert len(counted_pool) == 2

    def test_provision_from_token_sub_does_not_cache_a_successful_provision(
        self, session, counted_pool, pool
    ):
        pool.add(sub="sub-ok", email="ok@example.com")

        user = provision_from_token_sub(session, sub="sub-ok", groups=[])

        assert user is not None
        assert "sub-ok" not in provisioning._refusal_cache


# ─── Login path (Decision 4a) ───────────────────────────────────────────────


class TestProvisionFromLogin:
    def test_provision_from_login_creates_a_row_without_touching_cognito(
        self, session, monkeypatch
    ):
        """The hot path must not pay for an AdminGetUser it does not need: sub and
        groups both come from the token the auth call just returned."""

        def _must_not_be_called(_username):
            raise AssertionError("provision_from_login called AdminGetUser")

        monkeypatch.setattr(cognito, "admin_get_user", _must_not_be_called)

        user = provision_from_login(
            session,
            email="fresh@example.com",
            sub="sub-9",
            groups=[group_for_tier("enterprise")],
        )

        assert user.cognito_sub == "sub-9"
        assert user.tier == "enterprise"

    def test_provision_from_login_returns_the_existing_row_for_a_known_sub(
        self, session
    ):
        existing = User(
            id="u1", email="known@example.com", cognito_sub="sub-known", tier="pro"
        )
        session.add(existing)
        session.commit()

        user = provision_from_login(
            session, email="known@example.com", sub="sub-known", groups=[]
        )

        assert user.id == "u1"
        assert session.query(User).count() == 1

    def test_provision_from_login_refuses_an_email_held_by_a_different_sub(
        self, session
    ):
        """Re-pointing an existing row at a new Cognito identity would be an
        account-takeover primitive: everything the user owns is keyed on
        ``users.id``, so whoever controlled that mailbox at the pool would
        inherit the previous holder's runs, chats, artifacts and API keys."""
        session.add(
            User(id="u1", email="reused@example.com", cognito_sub="sub-OLD", tier="pro")
        )
        session.commit()

        with pytest.raises(ProvisioningRefused):
            provision_from_login(
                session, email="reused@example.com", sub="sub-NEW", groups=[]
            )

        assert session.query(User).one().cognito_sub == "sub-OLD"

    def test_a_concurrent_winner_is_re_read_rather_than_raising(
        self, session, monkeypatch
    ):
        """Two parallel first-requests for the same brand-new identity both find
        no row and both insert; ``uq_users_cognito_sub`` picks one winner and the
        loser must adopt it, not 500."""
        from sqlalchemy.exc import IntegrityError

        winner = User(
            id="winner", email="race@example.com", cognito_sub="sub-race", tier="basic"
        )
        session.add(winner)
        session.commit()

        real_commit = session.commit
        calls = {"n": 0}

        def _commit_once_then_conflict():
            calls["n"] += 1
            if calls["n"] == 1:
                raise IntegrityError("INSERT", {}, Exception("uq_users_cognito_sub"))
            return real_commit()

        monkeypatch.setattr(session, "commit", _commit_once_then_conflict)

        user = provisioning._insert_user(
            session, email="race@example.com", sub="sub-race", groups=[]
        )

        assert user.id == "winner"


# ─── resolve_principal integration ─────────────────────────────────────────


class TestResolvePrincipalJit:
    def test_a_verified_token_for_an_unknown_sub_provisions_exactly_one_row(
        self, session, pool
    ):
        pool.add(
            sub="sub-jit", email="jit@example.com", groups={group_for_tier("hexaware")}
        )

        user = resolve_principal(
            _principal("sub-jit", groups=[group_for_tier("hexaware")]), session
        )

        assert user is not None
        assert user.email == "jit@example.com"
        assert session.query(User).count() == 1

    def test_resolve_principal_rejects_a_row_that_is_not_active(self, session, pool):
        """The backstop that does not depend on the disable path having completed
        every step in order."""
        session.add(
            User(
                id="u1",
                email="off@example.com",
                cognito_sub="sub-off",
                tier="pro",
                status="disabled",
            )
        )
        session.commit()

        assert resolve_principal(_principal("sub-off"), session) is None

    def test_resolve_principal_returns_none_for_an_unknown_sub_absent_from_the_pool(
        self, session, pool
    ):
        assert resolve_principal(_principal("sub-nope"), session) is None


# ─── Projection refresh (Decision 3 / 4) ───────────────────────────────────


class TestProjectionRefresh:
    def _user(self, session, **kw):
        defaults = dict(
            id="u1", email="p@example.com", cognito_sub="sub-p", tier="basic"
        )
        user = User(**{**defaults, **kw})
        session.add(user)
        session.commit()
        return user

    def test_a_newer_token_refreshes_the_projection(self, session):
        user = self._user(session)

        refresh_projection_if_stale(
            user, [group_for_tier("enterprise"), ADMIN_GROUP], 1_700_000_000, session
        )

        assert user.tier == "enterprise"
        assert user.is_admin is True
        assert user.roles_synced_at is not None

    def test_an_older_token_does_not_rewrite_the_projection(self, session):
        """Otherwise a still-valid pre-change token would keep undoing the
        projection an admin write just corrected, flapping the admin list."""
        user = self._user(session, tier="enterprise", is_admin=True)
        refresh_projection_if_stale(
            user, [group_for_tier("enterprise"), ADMIN_GROUP], 1_700_000_100, session
        )

        refresh_projection_if_stale(
            user, [group_for_tier("basic")], 1_600_000_000, session
        )

        assert user.tier == "enterprise"
        assert user.is_admin is True

    def test_a_token_with_no_iat_is_ignored(self, session):
        user = self._user(session, tier="pro")

        refresh_projection_if_stale(user, [group_for_tier("basic")], None, session)

        assert user.tier == "pro"
