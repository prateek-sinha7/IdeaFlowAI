"""PostgreSQL-only coverage for ``app.scripts.bootstrap_admin``.

WHY THIS FILE IS OPT-IN
-----------------------
Everything ``bootstrap_admin`` does that SQLite can model is already covered in
``tests/unit/test_bootstrap_admin.py``. What is left needs a real PostgreSQL
server: the ``LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE`` statement itself,
and genuine cross-connection contention between two callers racing to bootstrap
the same empty database.

These tests therefore run ONLY when ``BOOTSTRAP_ADMIN_TEST_DATABASE_URL`` names
a database that exists purely to be wiped, and they are skipped otherwise — so
the default ``uv run pytest`` (and CI, which has no PostgreSQL service) stays
green.

THE SAFETY RAILS BELOW ARE NOT DECORATION
-----------------------------------------
These tests create and drop tables. An earlier draft of this file used the
application's own ``SessionLocal``, which resolves to whatever ``DATABASE_URL``
points at — i.e. a developer's real dev database — and deleted every row in
``users`` around each test. ``_resolve_test_database_url`` exists so that cannot
happen again:

* the URL must be supplied explicitly, in its own variable;
* it must not equal the configured application ``DATABASE_URL``;
* its database name must contain ``test``.

Run it like this (Git Bash, from ``backend/``)::

    createdb bootstrap_admin_test
    BOOTSTRAP_ADMIN_TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/bootstrap_admin_test \
        uv run pytest tests/integration/test_bootstrap_admin_postgres.py -v
"""

from __future__ import annotations

import os
import threading
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.security import verify_password
from app.models.database import Base
from app.models.user import User
from app.scripts.bootstrap_admin import EXIT_BOOTSTRAP_REQUIRED, EXIT_OK, check_only, create_admin

pytestmark = pytest.mark.requires_postgres

ENV_VAR = "BOOTSTRAP_ADMIN_TEST_DATABASE_URL"
VALID_PASSWORD = "bootstrap-password-0123456789"


@pytest.fixture(autouse=True)
def _force_local_auth_provider(monkeypatch):
    """Pin AUTH_PROVIDER=local for every test in this module.

    The same rail ``tests/unit/test_bootstrap_admin.py`` has, and for the same
    reason — it was missing here, which is a real defect, not a formality.
    ``create_admin`` branches on ``settings.AUTH_PROVIDER``, so on a developer
    machine whose ``.env`` sets ``cognito`` (the normal state since the
    migration) this suite called the LIVE ``AdminCreateUser`` / -
    ``AdminSetUserPassword`` / ``AdminAddUserToGroup`` against the real user
    pool. Observed 2026-08-06 while verifying KAN-167: the run created real pool
    users for ``admin@``/``first@``/``second@example.com`` and then failed on
    ``InvalidPasswordException`` (``VALID_PASSWORD`` satisfies this module's
    16-char floor but not the pool's uppercase policy), so every lock and
    concurrency assertion below failed for a reason that has nothing to do with
    PostgreSQL locking.

    What this suite exists to prove — the real ``LOCK TABLE`` statement and
    genuine cross-connection contention — is provider-independent. The Cognito
    branch is covered offline with stubs in the unit module. So the correct
    posture is the unit module's: pin the provider, keep the suite offline, and
    never let a test mutate a live pool.
    """
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "local")


def _resolve_test_database_url() -> str:
    """Return a URL that is safe to create and drop tables in, or skip.

    Every branch here is a guard against destroying real data; none of them is
    an inconvenience to be relaxed. If a guard fires, point the variable at a
    scratch database instead of loosening the check.
    """
    url = os.environ.get(ENV_VAR, "").strip()
    if not url:
        pytest.skip(f"{ENV_VAR} is not set — skipping the PostgreSQL bootstrap suite")

    if not url.startswith(("postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://")):
        pytest.skip(f"{ENV_VAR} is not a PostgreSQL URL — skipping")

    # Never operate on the database the application itself is configured for.
    if url == settings.DATABASE_URL:
        pytest.fail(
            f"{ENV_VAR} is identical to the application DATABASE_URL. "
            "This suite drops tables — point it at a throwaway database."
        )

    database_name = urlparse(url).path.lstrip("/")
    if not database_name:
        pytest.fail(f"{ENV_VAR} has no database name in its path.")
    if "test" not in database_name.lower():
        pytest.fail(
            f"Refusing to run against database {database_name!r}: this suite drops tables, "
            "so its name must contain 'test' to prove it is disposable."
        )

    return url


@pytest.fixture(scope="module")
def engine():
    url = _resolve_test_database_url()
    # NullPool: the concurrency test needs two genuinely independent
    # connections, and a pooled connection handed back and forth would let one
    # thread wait on a lock its own connection already holds.
    eng = create_engine(url, poolclass=NullPool, future=True)
    try:
        with eng.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — any connect failure means "skip, don't fail"
        eng.dispose()
        pytest.skip(f"cannot reach the PostgreSQL test database: {exc}")

    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    """A factory over the scratch database, emptied before and after each test."""
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    _truncate_users(factory)
    yield factory
    _truncate_users(factory)


def _truncate_users(factory) -> None:
    session = factory()
    try:
        # CASCADE because chat_sessions / workflow_runs carry FKs to users.
        session.execute(text("TRUNCATE TABLE users CASCADE"))
        session.commit()
    finally:
        session.close()


def _users(factory) -> list[User]:
    session = factory()
    try:
        return session.query(User).all()
    finally:
        session.close()


class TestRealTableLock:
    def test_lock_statement_is_accepted_by_postgres(self, session_factory):
        """The statement is dialect-specific SQL — a typo only shows up here."""
        assert create_admin("admin@example.com", VALID_PASSWORD, session_factory) == EXIT_OK
        assert len(_users(session_factory)) == 1

    def test_lock_is_released_by_the_commit(self, session_factory):
        """A held lock would deadlock the next writer instead of no-opping."""
        assert create_admin("admin@example.com", VALID_PASSWORD, session_factory) == EXIT_OK
        # Would block forever if the first call left its transaction open.
        assert create_admin("second@example.com", VALID_PASSWORD, session_factory) == EXIT_OK
        assert len(_users(session_factory)) == 1

    def test_lock_is_released_by_the_noop_rollback(self, session_factory):
        create_admin("admin@example.com", VALID_PASSWORD, session_factory)

        # Three consecutive no-ops: each must roll back and release.
        for _ in range(3):
            assert create_admin("other@example.com", VALID_PASSWORD, session_factory) == EXIT_OK

        session = session_factory()
        try:
            session.execute(text("SET lock_timeout = '5s'"))
            session.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
            session.rollback()
        finally:
            session.close()


class TestConcurrentBootstrap:
    def test_two_racing_callers_create_exactly_one_user(self, session_factory):
        """The race the lock exists to prevent, on a real server.

        A barrier lines both threads up on the empty table, so both would
        observe "zero users" under a plain COUNT-then-INSERT.
        """
        barrier = threading.Barrier(2)
        results: list[int] = []
        lock = threading.Lock()

        def bootstrap(email: str) -> None:
            barrier.wait(timeout=30)
            code = create_admin(email, VALID_PASSWORD, session_factory)
            with lock:
                results.append(code)

        threads = [
            threading.Thread(target=bootstrap, args=("first@example.com",)),
            threading.Thread(target=bootstrap, args=("second@example.com",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
            assert not thread.is_alive(), "a bootstrap thread deadlocked on the table lock"

        # Both succeed: one inserts, the loser observes the row and no-ops.
        assert results == [EXIT_OK, EXIT_OK]

        users = _users(session_factory)
        assert len(users) == 1
        assert users[0].email in {"first@example.com", "second@example.com"}
        assert users[0].is_admin is True

    def test_many_racing_callers_create_exactly_one_user(self, session_factory):
        thread_count = 5
        barrier = threading.Barrier(thread_count)
        results: list[int] = []
        lock = threading.Lock()

        def bootstrap(index: int) -> None:
            barrier.wait(timeout=30)
            code = create_admin(f"admin{index}@example.com", VALID_PASSWORD, session_factory)
            with lock:
                results.append(code)

        threads = [threading.Thread(target=bootstrap, args=(i,)) for i in range(thread_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=90)
            assert not thread.is_alive(), "a bootstrap thread deadlocked on the table lock"

        assert results == [EXIT_OK] * thread_count
        assert len(_users(session_factory)) == 1

    def test_concurrent_plain_insert_is_serialised(self, session_factory):
        """The lock must also conflict with an ordinary INSERT.

        ``/api/admin/users`` inserts without taking any lock, so an advisory
        lock would not coordinate with it. Holding SHARE ROW EXCLUSIVE has to
        make that insert wait.
        """
        holder = session_factory()
        blocked_by_lock = threading.Event()

        try:
            holder.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))

            def plain_insert() -> None:
                session = session_factory()
                try:
                    session.execute(text("SET lock_timeout = '2s'"))
                    session.add(
                        User(
                            email="api-created@example.com",
                            password_hash="hash",
                            tier="basic",
                        )
                    )
                    session.commit()
                except Exception:  # noqa: BLE001 — a lock timeout is the expected outcome
                    session.rollback()
                    blocked_by_lock.set()
                finally:
                    session.close()

            thread = threading.Thread(target=plain_insert)
            thread.start()
            thread.join(timeout=30)
            assert not thread.is_alive()

            assert blocked_by_lock.is_set(), (
                "an ordinary INSERT was not blocked by SHARE ROW EXCLUSIVE — "
                "the lock mode no longer protects against the admin API"
            )
        finally:
            holder.rollback()
            holder.close()


class TestEndToEndOnPostgres:
    def test_first_deploy_then_redeploy(self, session_factory):
        """The exact sequence remote-deploy.sh §12 drives across two deploys."""
        assert check_only(session_factory) == EXIT_BOOTSTRAP_REQUIRED

        assert create_admin("admin@flowin.io", VALID_PASSWORD, session_factory) == EXIT_OK

        admin = _users(session_factory)[0]
        assert admin.is_admin is True
        assert admin.tier == "enterprise"
        assert verify_password(VALID_PASSWORD, admin.password_hash) is True

        # Second deploy: the check short-circuits, so the password is never
        # even fetched from SSM.
        assert check_only(session_factory) == EXIT_OK

    def test_redeploy_preserves_the_original_row(self, session_factory):
        create_admin("admin@flowin.io", VALID_PASSWORD, session_factory)
        original = _users(session_factory)[0]
        original_id, original_hash = original.id, original.password_hash

        assert create_admin("admin@flowin.io", "a-different-password-9876", session_factory) == EXIT_OK

        again = _users(session_factory)[0]
        assert (again.id, again.password_hash) == (original_id, original_hash)

    def test_existing_non_admin_user_blocks_bootstrap(self, session_factory):
        session = session_factory()
        try:
            session.add(
                User(email="basic@flowin.io", password_hash="hash", tier="basic", is_admin=False)
            )
            session.commit()
        finally:
            session.close()

        assert check_only(session_factory) == EXIT_OK
        assert create_admin("admin@flowin.io", VALID_PASSWORD, session_factory) == EXIT_OK

        users = _users(session_factory)
        assert len(users) == 1
        assert users[0].email == "basic@flowin.io"
        assert users[0].is_admin is False
