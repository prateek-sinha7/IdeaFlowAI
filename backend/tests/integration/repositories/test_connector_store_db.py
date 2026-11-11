"""``ConnectionStore`` against a real database (connections, OAuth states, audit rows).

Most classes run on the hermetic in-memory SQLite engine of this folder's
``db_session`` fixture: they assert SQL that is not dialect-specific (conditional
UPDATE ... RETURNING, unique constraints, the pending cap, the sweep). The last
class is ``requires_postgres``: row locking, ``lock_timeout``, concurrent consumes
and ``ON DELETE CASCADE`` are PostgreSQL behaviour, so they run on a throwaway
PostgreSQL database migrated to Alembic head (``PYTEST_POSTGRES_ADMIN_URL``, else the
testcontainers server, which needs Docker). SQLite never stands in for them.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from alembic import command
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.crypto import TokenCipher
from app.connectors.errors import (
    ConnectorError,
    TooManyPendingAuthorizations,
    ToolErrorCode,
)
from app.connectors.oauth import OAuthClient
from app.connectors.registry import ConnectorRegistry
from app.connectors.store import (
    AuditEntry,
    ConnectionStore,
    NewConnection,
)
from app.connectors.tokens import TokenProvider
from app.core.config import Settings
from app.models.connector import (
    ConnectorAuditLog,
    ConnectorConnection,
    OAuthState,
)
from app.models.user import User
from tests.factories.connector_factory import (
    ConnectorConnectionFactory,
    OAuthStateFactory,
)
from tests.fakes.connector_store import MutableClock
from tests.fakes.oauth_provider import (
    GITHUB_TOKEN_URL,
    FakeOAuthProvider,
    github_token_body,
    json_response,
    slow_response,
)
from tests.integration.db.conftest import (
    alembic_config_for,
    postgres_admin_url,
    throwaway_database,
)

USER_A = "user-a"
USER_B = "user-b"


def _add_users(db: Session, *user_ids: str) -> None:
    for user_id in user_ids:
        db.add(
            User(
                id=user_id, email=f"{user_id}@example.com", cognito_sub=f"sub-{user_id}"
            )
        )
    db.commit()


def _new_connection(
    user_id: str = USER_A, key: str = "github", **overrides
) -> NewConnection:
    values = {
        "user_id": user_id,
        "connector_key": key,
        "provider_account_id": "acct-1",
        "provider_account_login": "octo",
        "provider_account_name": "Octo",
        "granted_scopes": ("repo",),
        "provider_metadata": None,
        "access_token_expires_at": None,
        "refresh_token_expires_at": None,
        "access_token_ciphertext": "access-ct",
        "refresh_token_ciphertext": "refresh-ct",
    }
    values.update(overrides)
    return NewConnection(**values)


@pytest.fixture
def clock() -> MutableClock:
    """A settable UTC clock shared by the store under test."""
    return MutableClock()


@pytest.fixture
def store(db_session: Session, clock: MutableClock) -> ConnectionStore:
    """A ``ConnectionStore`` on the SQLite engine of ``db_session`` with two users."""
    _add_users(db_session, USER_A, USER_B)
    factory = sessionmaker(
        bind=db_session.get_bind(), autoflush=False, expire_on_commit=False
    )
    return ConnectionStore(factory, clock)


class TestConnectionRows:
    def test_upsert_creates_active_row_when_none_exists(
        self, store: ConnectionStore, clock: MutableClock
    ):
        # Act
        record = store.upsert(_new_connection())

        # Assert
        assert record.status == "active"
        assert record.token_version == 1
        assert record.created_at == clock.now
        assert record.granted_scopes == ("repo",)
        assert store.get(USER_A, "github") == record

    def test_upsert_replaces_tokens_and_bumps_version_when_reconnecting(
        self, store: ConnectionStore, clock: MutableClock
    ):
        # Arrange
        store.upsert(_new_connection())
        store.mark_expired(USER_A, "github", "invalid_grant")
        clock.advance(3600)

        # Act
        record = store.upsert(
            _new_connection(
                access_token_ciphertext="access-ct-2", provider_account_id="acct-2"
            )
        )

        # Assert
        assert record.token_version == 2
        assert record.status == "active"
        assert record.last_error_code is None
        assert record.access_token_ciphertext == "access-ct-2"
        assert record.provider_account_id == "acct-2"
        assert record.created_at == clock.now

    def test_upsert_keeps_one_row_per_user_and_connector_when_called_twice(
        self, store: ConnectionStore, db_session: Session
    ):
        # Act
        store.upsert(_new_connection())
        store.upsert(_new_connection())

        # Assert
        count = db_session.execute(
            select(func.count()).select_from(ConnectorConnection)
        ).scalar_one()
        assert count == 1

    def test_unique_constraint_rejects_duplicate_when_row_inserted_directly(
        self, store: ConnectionStore, db_session: Session
    ):
        # Arrange
        store.upsert(_new_connection())
        db_session.add(
            ConnectorConnectionFactory.build(user_id=USER_A, connector_key="github")
        )

        # Act / Assert
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_get_returns_none_when_other_user_owns_the_connection(
        self, store: ConnectionStore
    ):
        # Arrange
        store.upsert(_new_connection(USER_A))

        # Act / Assert
        assert store.get(USER_B, "github") is None

    def test_list_for_user_returns_only_own_rows_sorted_by_connector(
        self, store: ConnectionStore
    ):
        # Arrange
        store.upsert(_new_connection(USER_A, "jira"))
        store.upsert(_new_connection(USER_A, "github"))
        store.upsert(_new_connection(USER_B, "github"))

        # Act
        rows = store.list_for_user(USER_A)

        # Assert
        assert [r.connector_key for r in rows] == ["github", "jira"]
        assert {r.user_id for r in rows} == {USER_A}

    def test_delete_removes_only_the_callers_row_when_both_users_connected(
        self, store: ConnectionStore
    ):
        # Arrange
        store.upsert(_new_connection(USER_A))
        store.upsert(_new_connection(USER_B))

        # Act
        deleted = store.delete(USER_A, "github")

        # Assert
        assert deleted is True
        assert store.get(USER_A, "github") is None
        assert store.get(USER_B, "github") is not None

    def test_delete_returns_false_when_nothing_connected(self, store: ConnectionStore):
        # Act / Assert
        assert store.delete(USER_A, "github") is False

    def test_mark_expired_sets_status_and_code_when_row_exists(
        self, store: ConnectionStore
    ):
        # Arrange
        store.upsert(_new_connection())

        # Act
        changed = store.mark_expired(USER_A, "github", "undecryptable")

        # Assert
        record = store.get(USER_A, "github")
        assert changed is True
        assert record is not None
        assert (record.status, record.last_error_code) == ("expired", "undecryptable")
        assert store.mark_expired(USER_B, "github", "x") is False

    def test_record_repr_hides_ciphertext_when_formatted(self, store: ConnectionStore):
        # Arrange
        record = store.upsert(_new_connection(access_token_ciphertext="very-secret-ct"))

        # Act / Assert
        assert "very-secret-ct" not in repr(record)


def _create_state(
    store: ConnectionStore, user: str = USER_A, state_hash: str = "h1", **kw
):
    params = {
        "user_id": user,
        "connector_key": "github",
        "state_hash": state_hash,
        "code_verifier_ciphertext": "verifier-ct",
        "redirect_uri": "http://localhost:3000/api/connectors/oauth/callback",
        "ttl_seconds": 600,
        "max_pending": 5,
    }
    params.update(kw)
    return store.create_state(**params)


class TestOAuthStates:
    def test_create_state_returns_expiry_ten_minutes_ahead_when_stored(
        self, store: ConnectionStore, clock: MutableClock
    ):
        # Act
        expires_at = _create_state(store)

        # Assert
        assert expires_at == clock.now + timedelta(seconds=600)

    def test_consume_state_returns_row_once_when_replayed(self, store: ConnectionStore):
        # Arrange
        _create_state(store, state_hash="abc")

        # Act
        first = store.consume_state("abc")
        second = store.consume_state("abc")

        # Assert
        assert first is not None
        assert (first.user_id, first.connector_key) == (USER_A, "github")
        assert first.code_verifier_ciphertext == "verifier-ct"
        assert first.redirect_uri.endswith("/api/connectors/oauth/callback")
        assert second is None

    def test_consume_state_returns_none_when_unknown(self, store: ConnectionStore):
        # Act / Assert
        assert store.consume_state("nope") is None

    def test_consume_state_returns_none_when_expired(
        self, store: ConnectionStore, clock: MutableClock
    ):
        # Arrange
        _create_state(store, state_hash="abc")
        clock.advance(601)

        # Act / Assert
        assert store.consume_state("abc") is None

    def test_consume_state_accepts_state_just_before_expiry(
        self, store: ConnectionStore, clock: MutableClock
    ):
        # Arrange
        _create_state(store, state_hash="abc")
        clock.advance(599)

        # Act / Assert
        assert store.consume_state("abc") is not None

    def test_create_state_raises_when_pending_cap_reached(self, store: ConnectionStore):
        # Arrange
        for n in range(5):
            _create_state(store, state_hash=f"h{n}")

        # Act / Assert
        with pytest.raises(TooManyPendingAuthorizations):
            _create_state(store, state_hash="h5")

    def test_create_state_ignores_expired_and_consumed_rows_when_counting_pending(
        self, store: ConnectionStore, clock: MutableClock, db_session: Session
    ):
        # Arrange
        for n in range(4):
            _create_state(store, state_hash=f"old{n}")
        clock.advance(601)
        _create_state(store, state_hash="live")
        store.consume_state("live")

        # Act
        for n in range(5):
            _create_state(store, state_hash=f"new{n}")

        # Assert
        remaining = {
            h for (h,) in db_session.execute(select(OAuthState.state_hash)).all()
        }
        assert not {f"old{n}" for n in range(4)} & remaining

    def test_create_state_counts_per_user_when_other_user_at_cap(
        self, store: ConnectionStore
    ):
        # Arrange
        for n in range(5):
            _create_state(store, USER_A, f"a{n}")

        # Act
        _create_state(store, USER_B, "b0")

        # Assert
        assert store.consume_state("b0") is not None

    def test_create_state_rejects_duplicate_hash_when_reused(
        self, store: ConnectionStore
    ):
        # Arrange
        _create_state(store, state_hash="dup")

        # Act / Assert
        with pytest.raises(IntegrityError):
            _create_state(store, USER_B, "dup")

    def test_sweep_expired_states_deletes_only_long_expired_rows_when_called(
        self, store: ConnectionStore, clock: MutableClock, db_session: Session
    ):
        # Arrange
        _create_state(store, state_hash="ancient")
        clock.advance(25 * 3600)
        _create_state(store, USER_B, "recent")
        clock.advance(601)

        # Act
        removed = store.sweep_expired_states(timedelta(hours=24))

        # Assert
        remaining = {
            h for (h,) in db_session.execute(select(OAuthState.state_hash)).all()
        }
        assert removed == 1
        assert remaining == {"recent"}

    def test_state_factory_rows_match_model_when_inserted(self, db_session: Session):
        # Arrange
        _add_users(db_session, "user-1")

        # Act
        db_session.add(OAuthStateFactory.build())
        db_session.commit()

        # Assert
        assert (
            db_session.execute(
                select(func.count()).select_from(OAuthState)
            ).scalar_one()
            == 1
        )


class TestAuditRows:
    def test_record_audit_writes_row_without_secret_columns_when_called(
        self, store: ConnectionStore, db_session: Session
    ):
        # Act
        store.record_audit(
            AuditEntry(
                user_id=USER_A,
                connector_key="github",
                action="connected",
                outcome="ok",
            )
        )

        # Assert
        row = db_session.execute(select(ConnectorAuditLog)).scalar_one()
        assert (row.action, row.outcome, row.error_code) == ("connected", "ok", None)
        assert {c.name for c in ConnectorAuditLog.__table__.columns}.isdisjoint(
            {"access_token", "refresh_token", "code", "state", "payload", "arguments"}
        )

    def test_record_audit_does_not_raise_when_database_unavailable(
        self, tmp_path, caplog: pytest.LogCaptureFixture
    ):
        # Arrange
        broken = ConnectionStore(
            sessionmaker(
                bind=create_engine(f"sqlite:///{tmp_path / 'missing' / 'x.db'}")
            )
        )

        # Act
        with caplog.at_level("WARNING"):
            broken.record_audit(
                AuditEntry(
                    user_id=USER_A,
                    connector_key="github",
                    action="connected",
                    outcome="ok",
                )
            )

        # Assert
        assert "audit insert failed" in caplog.text


class TestLockedConnection:
    def test_locked_connection_persists_rotation_when_committed(
        self, store: ConnectionStore
    ):
        # Arrange
        store.upsert(_new_connection())

        # Act
        with store.locked_connection(
            USER_A, "github", lock_timeout_seconds=5
        ) as locked:
            assert locked is not None
            version = locked.write_refreshed(
                access_token_ciphertext="access-ct-2",
                refresh_token_ciphertext=None,
                access_token_expires_at=None,
                refresh_token_expires_at=None,
            )
            locked.add_audit(
                AuditEntry(
                    user_id=USER_A,
                    connector_key="github",
                    action="refreshed",
                    outcome="ok",
                )
            )
            locked.commit()

        # Assert
        record = store.get(USER_A, "github")
        assert record is not None
        assert version == 2 == record.token_version
        assert record.access_token_ciphertext == "access-ct-2"
        assert record.refresh_token_ciphertext == "refresh-ct"
        assert record.last_refreshed_at is not None

    def test_locked_connection_discards_writes_when_not_committed(
        self, store: ConnectionStore
    ):
        # Arrange
        store.upsert(_new_connection())

        # Act
        with store.locked_connection(
            USER_A, "github", lock_timeout_seconds=5
        ) as locked:
            assert locked is not None
            locked.write_expired("invalid_grant")

        # Assert
        record = store.get(USER_A, "github")
        assert record is not None and record.status == "active"

    def test_locked_connection_yields_none_when_row_missing(
        self, store: ConnectionStore
    ):
        # Act
        with store.locked_connection(
            USER_A, "github", lock_timeout_seconds=5
        ) as locked:
            # Assert
            assert locked is None

    def test_locked_connection_does_not_see_other_users_row(
        self, store: ConnectionStore
    ):
        # Arrange
        store.upsert(_new_connection(USER_B))

        # Act
        with store.locked_connection(
            USER_A, "github", lock_timeout_seconds=5
        ) as locked:
            # Assert
            assert locked is None


# ---------------------------------------------------------------------------
# PostgreSQL-only behaviour
# ---------------------------------------------------------------------------


def _pg_settings() -> Settings:
    return Settings(
        _env_file=None,
        ENV="development",
        APP_BASE_URL="http://localhost:3000",
        PUBLIC_BASE_URL="http://localhost:3000",
        TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        JIRA_OAUTH_CLIENT_ID="jira-client-id",
        JIRA_OAUTH_CLIENT_SECRET="jira-secret-placeholder",
        GITHUB_OAUTH_CLIENT_ID="github-client-id",
        GITHUB_OAUTH_CLIENT_SECRET="github-secret-placeholder",
    )


@pytest.mark.requires_postgres
class TestPostgresBehaviour:
    @pytest.fixture
    def pg_factory(
        self, request: pytest.FixtureRequest
    ) -> Generator[sessionmaker[Session], None, None]:
        """Session factory on a throwaway PostgreSQL database migrated to Alembic head."""
        with throwaway_database(postgres_admin_url(request), "conn0053") as url:
            command.upgrade(alembic_config_for(url), "head")
            engine = create_engine(url, pool_pre_ping=True)
            try:
                yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
            finally:
                engine.dispose()

    @staticmethod
    def _seed(pg_factory, cipher: TokenCipher, *, expires_in: int = 10) -> None:
        with pg_factory() as db:
            db.add(User(id=USER_A, email="a@example.com", cognito_sub="sub-a"))
            db.commit()
        store = ConnectionStore(pg_factory)
        store.upsert(
            _new_connection(
                access_token_ciphertext=cipher.encrypt("gho_old"),
                refresh_token_ciphertext=cipher.encrypt("ghr_old"),
                access_token_expires_at=datetime.now(timezone.utc)
                + timedelta(seconds=expires_in),
            )
        )

    def _provider(self, pg_factory, cipher_key: str, **token_options):
        settings = _pg_settings().model_copy(
            update={"TOKEN_ENCRYPTION_KEY": cipher_key}
        )
        cipher = TokenCipher(cipher_key)
        store = ConnectionStore(pg_factory)
        fake = FakeOAuthProvider()
        tokens = TokenProvider(
            registry=ConnectorRegistry(settings),
            store=store,
            cipher=cipher,
            client=OAuthClient(fake.http_factory),
            **token_options,
        )
        return cipher, store, fake, tokens

    def test_access_token_blocking_calls_provider_once_when_two_threads_refresh(
        self, pg_factory
    ):
        # Arrange
        key = Fernet.generate_key().decode()
        cipher, store, fake, tokens = self._provider(pg_factory, key)
        self._seed(pg_factory, cipher)
        fake.respond(
            "POST",
            GITHUB_TOKEN_URL,
            slow_response(
                json_response(
                    200,
                    github_token_body(access_token="gho_new", refresh_token="ghr_new"),
                ),
                0.6,
            ),
        )
        results: list[str] = []
        errors: list[BaseException] = []

        def refresh() -> None:
            try:
                results.append(
                    tokens.access_token_blocking(
                        USER_A, "github", force_refresh=True, rejected_version=1
                    ).token
                )
            except BaseException as exc:  # noqa: BLE001 - surfaced by the assertion
                errors.append(exc)

        threads = [threading.Thread(target=refresh) for _ in range(2)]

        # Act
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        # Assert
        assert errors == []
        assert results == ["gho_new", "gho_new"]
        assert len(fake.calls("POST", GITHUB_TOKEN_URL)) == 1
        record = store.get(USER_A, "github")
        assert record is not None and record.token_version == 2

    def test_access_token_blocking_reports_unavailable_when_row_lock_times_out(
        self, pg_factory
    ):
        # Arrange
        key = Fernet.generate_key().decode()
        cipher, store, fake, tokens = self._provider(
            pg_factory, key, lock_timeout_seconds=1
        )
        self._seed(pg_factory, cipher)
        holder_ready = threading.Event()
        release = threading.Event()

        def hold_lock() -> None:
            with store.locked_connection(USER_A, "github", lock_timeout_seconds=30):
                holder_ready.set()
                release.wait(timeout=30)

        holder = threading.Thread(target=hold_lock)
        holder.start()
        assert holder_ready.wait(timeout=10)
        started = time.monotonic()

        # Act
        try:
            with pytest.raises(ConnectorError) as raised:
                tokens.access_token_blocking(
                    USER_A, "github", force_refresh=True, rejected_version=1
                )
        finally:
            release.set()
            holder.join(timeout=10)

        # Assert
        assert raised.value.code is ToolErrorCode.PROVIDER_UNAVAILABLE
        assert time.monotonic() - started < 10
        assert fake.calls("POST", GITHUB_TOKEN_URL) == []

    def test_locked_connection_raises_operational_error_when_lock_timeout_elapses(
        self, pg_factory
    ):
        # Arrange
        key = Fernet.generate_key().decode()
        cipher, store, _fake, _tokens = self._provider(pg_factory, key)
        self._seed(pg_factory, cipher)
        holder_ready = threading.Event()
        release = threading.Event()

        def hold_lock() -> None:
            with store.locked_connection(USER_A, "github", lock_timeout_seconds=30):
                holder_ready.set()
                release.wait(timeout=30)

        holder = threading.Thread(target=hold_lock)
        holder.start()
        assert holder_ready.wait(timeout=10)

        # Act / Assert
        try:
            with pytest.raises(OperationalError):
                with store.locked_connection(USER_A, "github", lock_timeout_seconds=1):
                    pass
        finally:
            release.set()
            holder.join(timeout=10)

    def test_consume_state_succeeds_for_exactly_one_thread_when_consumed_concurrently(
        self, pg_factory
    ):
        # Arrange
        with pg_factory() as db:
            db.add(User(id=USER_A, email="a@example.com", cognito_sub="sub-a"))
            db.commit()
        store = ConnectionStore(pg_factory)
        _create_state(store, state_hash="race")
        outcomes: list[bool] = []
        barrier = threading.Barrier(8)

        def consume() -> None:
            barrier.wait(timeout=10)
            outcomes.append(store.consume_state("race") is not None)

        threads = [threading.Thread(target=consume) for _ in range(8)]

        # Act
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        # Assert
        assert sorted(outcomes) == [False] * 7 + [True]

    def test_user_delete_cascades_to_every_connector_table_when_user_removed(
        self, pg_factory
    ):
        # Arrange
        with pg_factory() as db:
            db.add(User(id=USER_A, email="a@example.com", cognito_sub="sub-a"))
            db.commit()
        store = ConnectionStore(pg_factory)
        store.upsert(_new_connection())
        _create_state(store, state_hash="s1")
        store.record_audit(
            AuditEntry(
                user_id=USER_A, connector_key="github", action="connected", outcome="ok"
            )
        )

        # Act
        with pg_factory() as db:
            db.delete(db.get(User, USER_A))
            db.commit()

        # Assert
        with pg_factory() as db:
            for model in (ConnectorConnection, OAuthState, ConnectorAuditLog):
                assert (
                    db.execute(select(func.count()).select_from(model)).scalar_one()
                    == 0
                )

    def test_foreign_key_rejects_connection_when_user_does_not_exist(self, pg_factory):
        # Arrange
        store = ConnectionStore(pg_factory)

        # Act / Assert
        with pytest.raises(IntegrityError):
            store.upsert(_new_connection("ghost"))
