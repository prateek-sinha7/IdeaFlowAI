"""Unit coverage for ``app.scripts.bootstrap_admin``.

Backed by a fresh in-memory SQLite database per test (the same pattern as
``tests/unit/test_logout.py``) and a session factory injected into the command,
so nothing here can reach the configured application database.

What is deliberately NOT covered here: the real ``LOCK TABLE`` statement and
genuine cross-connection contention. SQLite has no equivalent, so those live in
``tests/integration/test_bootstrap_admin_postgres.py``, which is opt-in and
needs its own throwaway PostgreSQL database. The lock-gating branch itself is
asserted below against a stub, so a regression that drops the lock on
PostgreSQL still fails fast without a server.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import verify_password
from app.models.database import Base
from app.models.user import User
from app.scripts import bootstrap_admin
from app.scripts.bootstrap_admin import (
    EXIT_BOOTSTRAP_REQUIRED,
    EXIT_ERROR,
    EXIT_OK,
    MIN_PASSWORD_LENGTH,
    check_only,
    create_admin,
    main,
)

VALID_PASSWORD = "bootstrap-password-0123456789"
assert len(VALID_PASSWORD) >= MIN_PASSWORD_LENGTH


@pytest.fixture(autouse=True)
def _force_local_auth_provider(monkeypatch):
    """Pin AUTH_PROVIDER=local for every test in this module.

    ``bootstrap_admin.create_admin`` branches on ``settings.AUTH_PROVIDER``:
    under ``cognito`` it provisions a real pool user via ``AdminCreateUser``.
    Without this fixture, every test below would silently change behaviour —
    and start making live AWS calls — on any machine whose ``.env`` or shell has
    ``AUTH_PROVIDER=cognito`` set. That breaks the migration plan's hard rule
    that CI stays offline-capable and no test calls AWS, and it fails in a
    confusing way (credential/network errors inside what looks like a pure
    bcrypt test).

    These tests characterize the LOCAL path, so they pin it explicitly rather
    than inheriting ambient configuration. The Cognito branch is covered
    separately in ``TestCognitoBranch`` with the AWS calls stubbed.
    """
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "local")


@pytest.fixture
def session_factory():
    """A sessionmaker bound to a private in-memory SQLite database.

    StaticPool keeps the one in-memory database alive across every connection
    checkout — without it SQLite hands each connection its own empty database
    and the schema created here disappears.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield factory
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def seed_user(session_factory):
    """Insert an arbitrary user so the table is no longer empty."""

    def _seed(email: str = "existing@example.com", *, is_admin: bool = False) -> str:
        session = session_factory()
        try:
            user = User(
                email=email,
                password_hash="not-a-real-hash",
                tier="basic",
                is_admin=is_admin,
            )
            session.add(user)
            session.commit()
            return user.id
        finally:
            session.close()

    return _seed


def _users(session_factory) -> list[User]:
    session = session_factory()
    try:
        return session.query(User).all()
    finally:
        session.close()


class TestCheckOnly:
    def test_empty_table_requires_bootstrap(self, session_factory):
        assert check_only(session_factory) == EXIT_BOOTSTRAP_REQUIRED

    def test_existing_user_means_not_needed(self, session_factory, seed_user):
        seed_user()
        assert check_only(session_factory) == EXIT_OK

    def test_existing_non_admin_user_still_means_not_needed(self, session_factory, seed_user):
        """The invariant is "any row", not "an admin row" — see the module docstring."""
        seed_user(is_admin=False)
        assert check_only(session_factory) == EXIT_OK

    def test_check_only_writes_nothing(self, session_factory):
        assert check_only(session_factory) == EXIT_BOOTSTRAP_REQUIRED
        assert _users(session_factory) == []

    def test_database_failure_is_exit_error(self):
        def broken_factory():
            raise RuntimeError("connection refused")

        assert check_only(broken_factory) == EXIT_ERROR

    def test_query_failure_is_exit_error(self):
        session = MagicMock()
        session.query.side_effect = RuntimeError("relation \"users\" does not exist")
        assert check_only(lambda: session) == EXIT_ERROR
        session.close.assert_called_once()


class TestCreateAdminHappyPath:
    def test_creates_single_enterprise_admin(self, session_factory):
        assert create_admin("admin@example.com", VALID_PASSWORD, session_factory) == EXIT_OK

        users = _users(session_factory)
        assert len(users) == 1
        assert users[0].email == "admin@example.com"
        assert users[0].tier == "enterprise"
        assert users[0].is_admin is True

    def test_password_is_hashed_not_stored(self, session_factory):
        create_admin("admin@example.com", VALID_PASSWORD, session_factory)

        stored = _users(session_factory)[0].password_hash
        assert stored != VALID_PASSWORD
        assert VALID_PASSWORD not in stored
        assert verify_password(VALID_PASSWORD, stored) is True

    def test_email_is_normalised(self, session_factory):
        assert create_admin("  Admin@Example.COM  ", VALID_PASSWORD, session_factory) == EXIT_OK
        assert _users(session_factory)[0].email == "admin@example.com"

    def test_timestamps_come_from_the_model_defaults(self, session_factory):
        before = datetime.now(timezone.utc)
        create_admin("admin@example.com", VALID_PASSWORD, session_factory)

        user = _users(session_factory)[0]
        assert user.created_at is not None
        assert user.updated_at is not None
        # The column is a naive DateTime while the model default is an
        # aware UTC value, so the round-tripped value comes back naive
        # (the same asymmetry app.core.dependencies handles for
        # password_changed_at). Re-attach UTC before comparing rather than
        # comparing aware to naive, which raises TypeError.
        created_at = user.created_at.replace(tzinfo=timezone.utc)
        assert before <= created_at <= datetime.now(timezone.utc)

    def test_password_with_trailing_space_is_preserved(self, session_factory):
        password = VALID_PASSWORD + "  "
        create_admin("admin@example.com", password, session_factory)

        stored = _users(session_factory)[0].password_hash
        assert verify_password(password, stored) is True
        assert verify_password(VALID_PASSWORD, stored) is False


class TestCreateAdminIdempotency:
    def test_existing_user_is_a_successful_noop(self, session_factory, seed_user):
        seed_user("someone@example.com")

        assert create_admin("admin@example.com", VALID_PASSWORD, session_factory) == EXIT_OK

        users = _users(session_factory)
        assert len(users) == 1
        assert users[0].email == "someone@example.com"

    def test_existing_non_admin_is_never_promoted(self, session_factory, seed_user):
        seed_user("basic@example.com", is_admin=False)

        assert create_admin("admin@example.com", VALID_PASSWORD, session_factory) == EXIT_OK

        user = _users(session_factory)[0]
        assert user.is_admin is False
        assert user.tier == "basic"
        assert user.password_hash == "not-a-real-hash"

    def test_second_run_does_not_rotate_the_password(self, session_factory):
        create_admin("admin@example.com", VALID_PASSWORD, session_factory)
        first = _users(session_factory)[0]
        original_id, original_hash, original_created = (
            first.id,
            first.password_hash,
            first.created_at,
        )

        assert create_admin("admin@example.com", "a-different-password-9876", session_factory) == EXIT_OK

        again = _users(session_factory)[0]
        assert (again.id, again.password_hash, again.created_at) == (
            original_id,
            original_hash,
            original_created,
        )
        assert verify_password("a-different-password-9876", again.password_hash) is False

    def test_second_run_with_a_different_email_creates_nothing(self, session_factory):
        create_admin("first@example.com", VALID_PASSWORD, session_factory)

        assert create_admin("second@example.com", VALID_PASSWORD, session_factory) == EXIT_OK

        emails = [u.email for u in _users(session_factory)]
        assert emails == ["first@example.com"]


class TestCreateAdminValidation:
    @pytest.mark.parametrize(
        "email",
        [
            None,
            "",
            "   ",
            "not-an-email",
            "@example.com",
            "admin@",
            "admin@localhost",
            123,
        ],
    )
    def test_unusable_email_is_rejected_without_touching_the_database(
        self, session_factory, email
    ):
        assert create_admin(email, VALID_PASSWORD, session_factory) == EXIT_ERROR
        assert _users(session_factory) == []

    @pytest.mark.parametrize(
        "password",
        [None, "", "short", "x" * (MIN_PASSWORD_LENGTH - 1), 12345678901234567890],
    )
    def test_weak_password_is_rejected_without_touching_the_database(
        self, session_factory, password
    ):
        assert create_admin("admin@example.com", password, session_factory) == EXIT_ERROR
        assert _users(session_factory) == []

    def test_minimum_length_password_is_accepted(self, session_factory):
        assert create_admin("admin@example.com", "x" * MIN_PASSWORD_LENGTH, session_factory) == EXIT_OK

    def test_validation_runs_before_a_session_is_opened(self):
        def exploding_factory():
            raise AssertionError("must not open a session for invalid input")

        assert create_admin(None, VALID_PASSWORD, exploding_factory) == EXIT_ERROR
        assert create_admin("admin@example.com", "short", exploding_factory) == EXIT_ERROR


class TestCreateAdminFailureHandling:
    def test_session_open_failure_is_exit_error(self):
        def broken_factory():
            raise RuntimeError("connection refused")

        assert create_admin("admin@example.com", VALID_PASSWORD, broken_factory) == EXIT_ERROR

    def test_commit_failure_rolls_back_and_leaves_no_user(self, session_factory):
        real_session = session_factory()

        class FailingCommitSession:
            """Delegates everything except commit, which fails like a lost connection."""

            def __getattr__(self, name):
                return getattr(real_session, name)

            def commit(self):
                raise RuntimeError("server closed the connection unexpectedly")

        assert (
            create_admin("admin@example.com", VALID_PASSWORD, FailingCommitSession)
            == EXIT_ERROR
        )
        assert _users(session_factory) == []

    def test_lock_failure_is_exit_error(self, session_factory, monkeypatch):
        def refuse_lock(_session):
            raise RuntimeError("lock timeout")

        monkeypatch.setattr(bootstrap_admin, "_lock_users_table", refuse_lock)

        assert create_admin("admin@example.com", VALID_PASSWORD, session_factory) == EXIT_ERROR
        assert _users(session_factory) == []


class TestTableLockGating:
    """The lock is the only thing preventing a double-bootstrap race."""

    def test_postgresql_takes_the_share_row_exclusive_lock(self):
        session = MagicMock()
        session.get_bind.return_value.dialect.name = "postgresql"

        bootstrap_admin._lock_users_table(session)

        session.execute.assert_called_once()
        statement = str(session.execute.call_args.args[0])
        assert statement == "LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"

    def test_other_dialects_issue_no_statement(self):
        session = MagicMock()
        session.get_bind.return_value.dialect.name = "sqlite"

        bootstrap_admin._lock_users_table(session)

        session.execute.assert_not_called()

    def test_insert_path_locks_before_reading(self, session_factory, monkeypatch):
        """Order matters: re-checking before the lock would reintroduce the race."""
        calls: list[str] = []

        real_lock = bootstrap_admin._lock_users_table
        real_exists = bootstrap_admin._users_exist

        def traced_lock(session):
            calls.append("lock")
            return real_lock(session)

        def traced_exists(session):
            calls.append("check")
            return real_exists(session)

        monkeypatch.setattr(bootstrap_admin, "_lock_users_table", traced_lock)
        monkeypatch.setattr(bootstrap_admin, "_users_exist", traced_exists)

        assert create_admin("admin@example.com", VALID_PASSWORD, session_factory) == EXIT_OK
        assert calls == ["lock", "check"]


class TestSecretHygiene:
    def test_password_never_reaches_logs_or_stdout(self, session_factory, capsys, caplog):
        with caplog.at_level(logging.DEBUG):
            create_admin("admin@example.com", VALID_PASSWORD, session_factory)

        captured = capsys.readouterr()
        assert VALID_PASSWORD not in captured.out
        assert VALID_PASSWORD not in captured.err
        assert VALID_PASSWORD not in caplog.text

    def test_rejection_message_does_not_echo_the_password(self, session_factory, caplog):
        secret = "too-short"
        with caplog.at_level(logging.DEBUG):
            create_admin("admin@example.com", secret, session_factory)

        assert secret not in caplog.text
        assert str(MIN_PASSWORD_LENGTH) in caplog.text

    def test_stored_hash_is_not_logged(self, session_factory, caplog):
        with caplog.at_level(logging.DEBUG):
            create_admin("admin@example.com", VALID_PASSWORD, session_factory)

        assert _users(session_factory)[0].password_hash not in caplog.text


class TestMain:
    """The CLI surface remote-deploy.sh §12 actually invokes."""

    @pytest.fixture(autouse=True)
    def _bind_default_factory(self, session_factory, monkeypatch):
        """main() takes no factory, so point the module default at the test database."""
        monkeypatch.setattr(bootstrap_admin, "SessionLocal", session_factory)

    def test_check_only_reports_bootstrap_required(self):
        assert main(["--check-only"]) == EXIT_BOOTSTRAP_REQUIRED

    def test_check_only_reports_already_initialised(self, seed_user):
        seed_user()
        assert main(["--check-only"]) == EXIT_OK

    def test_create_reads_the_password_from_stdin(self, session_factory, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO(f"{VALID_PASSWORD}\n"))

        assert main(["--email", "admin@example.com", "--password-stdin"]) == EXIT_OK

        stored = _users(session_factory)[0].password_hash
        assert verify_password(VALID_PASSWORD, stored) is True

    def test_crlf_line_ending_is_stripped(self, session_factory, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO(f"{VALID_PASSWORD}\r\n"))

        assert main(["--email", "admin@example.com", "--password-stdin"]) == EXIT_OK
        assert verify_password(VALID_PASSWORD, _users(session_factory)[0].password_hash) is True

    def test_empty_stdin_is_an_error(self, session_factory, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        assert main(["--email", "admin@example.com", "--password-stdin"]) == EXIT_ERROR
        assert _users(session_factory) == []

    def test_check_only_refuses_to_be_combined_with_credentials(self, session_factory):
        assert main(["--check-only", "--email", "admin@example.com"]) == EXIT_ERROR
        assert _users(session_factory) == []

    def test_email_without_password_stdin_is_rejected(self, session_factory):
        assert main(["--email", "admin@example.com"]) == EXIT_ERROR
        assert _users(session_factory) == []

    def test_password_stdin_without_email_is_rejected(self, session_factory):
        assert main(["--password-stdin"]) == EXIT_ERROR
        assert _users(session_factory) == []

    def test_no_arguments_is_rejected(self, session_factory):
        assert main([]) == EXIT_ERROR
        assert _users(session_factory) == []


class TestCognitoBranch:
    """The AUTH_PROVIDER=cognito path — the fresh-environment critical path.

    With self-registration hard-disabled and `POST /api/admin/users` itself
    requiring an authenticated admin, this is the ONLY way into a brand-new
    Cognito environment (R1 in the migration plan's risk register). It is
    therefore worth real coverage rather than trusting it on first use in prod.

    AWS is stubbed: these assert what we ASK Cognito to do and how we persist
    the result, keeping the suite offline per the plan's CI rule.
    """

    @pytest.fixture
    def cognito_provider(self, monkeypatch):
        # Overrides the module-level autouse fixture for this class only.
        monkeypatch.setattr(settings, "AUTH_PROVIDER", "cognito")

    @pytest.fixture
    def fake_cognito(self, monkeypatch):
        """Stub the four Cognito calls the bootstrap path makes."""
        calls: dict[str, object] = {"groups": []}
        sub = "11111111-2222-3333-4444-555555555555"

        def admin_create_user(email):
            calls["created_email"] = email
            return {"User": {"Attributes": [{"Name": "sub", "Value": sub}]}}

        def admin_set_user_password(email, password, permanent=True):
            calls["password_email"] = email
            calls["permanent"] = permanent

        def admin_add_user_to_group(email, group):
            calls["groups"].append((email, group))  # type: ignore[union-attr]

        def admin_delete_user(email):
            calls["deleted_email"] = email

        from app.core import cognito as cognito_module

        monkeypatch.setattr(cognito_module, "admin_create_user", admin_create_user)
        monkeypatch.setattr(cognito_module, "admin_set_user_password", admin_set_user_password)
        monkeypatch.setattr(cognito_module, "admin_add_user_to_group", admin_add_user_to_group)
        monkeypatch.setattr(cognito_module, "admin_delete_user", admin_delete_user)
        calls["sub"] = sub
        return calls

    def test_provisions_pool_user_and_maps_it_locally(
        self, session_factory, cognito_provider, fake_cognito
    ):
        rc = create_admin(
            email="admin@example.com",
            password="a-valid-password-123",
            session_factory=session_factory,
        )
        assert rc == EXIT_OK

        rows = _users(session_factory)
        assert len(rows) == 1
        row = rows[0]

        # The local row must carry the pool `sub` — without it
        # resolve_principal() can never match this user and the admin simply
        # cannot log in (check C1 in verify_cognito_cutover.py).
        assert row.cognito_sub == fake_cognito["sub"]
        assert row.auth_provider == "cognito"
        assert row.is_admin is True

        # No local bcrypt hash: the credential lives in Cognito now. A residual
        # hash would be a second credential outside pool policy/MFA (check C3).
        assert row.password_hash is None

    def test_password_is_set_permanent_so_first_login_needs_no_challenge(
        self, session_factory, cognito_provider, fake_cognito
    ):
        """A forced NEW_PASSWORD_REQUIRED challenge would strand the bootstrap.

        Whoever runs this is trying to get into an empty environment; if the
        credential they were handed demands an interactive challenge before it
        works, the bootstrap has not actually delivered access.
        """
        create_admin(
            email="admin@example.com",
            password="a-valid-password-123",
            session_factory=session_factory,
        )
        assert fake_cognito["permanent"] is True

    def test_admin_is_added_to_the_admins_group(
        self, session_factory, cognito_provider, fake_cognito
    ):
        from app.core.entitlements import ADMIN_GROUP

        create_admin(
            email="admin@example.com",
            password="a-valid-password-123",
            session_factory=session_factory,
        )
        assert ("admin@example.com", ADMIN_GROUP) in fake_cognito["groups"]

    def test_local_commit_failure_compensates_by_deleting_the_pool_user(
        self, session_factory, cognito_provider, fake_cognito, monkeypatch
    ):
        """No orphaned pool user if the local insert fails (R7).

        An orphan authenticates against Cognito but has no local row, so it
        401s at resolve_principal — a state that is invisible unless someone
        runs the reconciliation report.
        """

        real_factory = session_factory

        class ExplodingSession:
            def __init__(self):
                self._inner = real_factory()

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def commit(self):
                raise RuntimeError("simulated local commit failure")

        rc = create_admin(
            email="admin@example.com",
            password="a-valid-password-123",
            session_factory=ExplodingSession,
        )

        assert rc == EXIT_ERROR
        assert fake_cognito.get("deleted_email") == "admin@example.com", (
            "a failed local commit must compensate by deleting the pool user"
        )

    def test_local_path_is_unaffected_when_provider_is_local(
        self, session_factory, fake_cognito
    ):
        """Regression guard for the default path.

        The autouse fixture pins AUTH_PROVIDER=local here, so no Cognito call
        should happen at all and a bcrypt hash must be written.
        """
        rc = create_admin(
            email="admin@example.com",
            password="a-valid-password-123",
            session_factory=session_factory,
        )
        assert rc == EXIT_OK

        row = _users(session_factory)[0]
        assert row.auth_provider == "local"
        assert row.cognito_sub is None
        assert row.password_hash is not None
        assert verify_password("a-valid-password-123", row.password_hash)
        assert "created_email" not in fake_cognito, "the local path must not call Cognito"
