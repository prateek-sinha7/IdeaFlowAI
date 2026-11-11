"""Persistence for connector connections, OAuth states and audit rows.

``ConnectionStore`` is the only module that reads or writes the three connector
tables. Every connection query filters on the verified ``user_id`` it is given, so
one user can never read or change another user's tokens. Tokens cross this
boundary only as Fernet ciphertext; encryption and decryption belong to
``TokenCipher``. Dataclasses that hold ciphertext keep it out of their ``repr``.

All code here is synchronous (FastAPI threadpool, or a worker thread for async
callers). Datetimes are UTC and timezone-aware at the interface. SQLite (tests)
drops the offset on read, so reads re-attach UTC.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.connectors.errors import TooManyPendingAuthorizations
from app.models.connector import (
    CONNECTION_STATUS_ACTIVE,
    CONNECTION_STATUS_EXPIRED,
    ConnectorAuditLog,
    ConnectorConnection,
    OAuthState,
)

logger = logging.getLogger("app.connectors.store")

SessionFactory = Callable[[], Session]
Clock = Callable[[], datetime]

#: Rows removed per sweep of long-expired states (bounded, no background job).
_SWEEP_BATCH = 500


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """Attach UTC to a naive datetime read back from SQLite; leave aware values alone."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@dataclass(frozen=True)
class ConnectionRecord:
    """A stored connection. Ciphertext fields are hidden from ``repr``."""

    id: str
    user_id: str
    connector_key: str
    status: str
    provider_account_id: str
    provider_account_login: str | None
    provider_account_name: str | None
    granted_scopes: tuple[str, ...]
    provider_metadata: dict[str, Any] | None
    access_token_expires_at: datetime | None
    refresh_token_expires_at: datetime | None
    token_version: int
    last_refreshed_at: datetime | None
    last_error_code: str | None
    created_at: datetime
    updated_at: datetime
    access_token_ciphertext: str = field(repr=False)
    refresh_token_ciphertext: str | None = field(repr=False)

    @property
    def is_active(self) -> bool:
        """Whether the connection can still be used (not marked expired)."""
        return self.status == CONNECTION_STATUS_ACTIVE


def _record_from_row(row: ConnectorConnection) -> ConnectionRecord:
    return ConnectionRecord(
        id=row.id,
        user_id=row.user_id,
        connector_key=row.connector_key,
        status=row.status,
        provider_account_id=row.provider_account_id,
        provider_account_login=row.provider_account_login,
        provider_account_name=row.provider_account_name,
        granted_scopes=tuple(row.granted_scopes or ()),
        provider_metadata=row.provider_metadata,
        access_token_expires_at=as_utc(row.access_token_expires_at),
        refresh_token_expires_at=as_utc(row.refresh_token_expires_at),
        token_version=row.token_version,
        last_refreshed_at=as_utc(row.last_refreshed_at),
        last_error_code=row.last_error_code,
        created_at=as_utc(row.created_at) or utcnow(),
        updated_at=as_utc(row.updated_at) or utcnow(),
        access_token_ciphertext=row.access_token_ciphertext,
        refresh_token_ciphertext=row.refresh_token_ciphertext,
    )


@dataclass(frozen=True)
class NewConnection:
    """Everything a successful callback stores for one (user, connector)."""

    user_id: str
    connector_key: str
    provider_account_id: str
    provider_account_login: str | None
    provider_account_name: str | None
    granted_scopes: tuple[str, ...]
    provider_metadata: dict[str, Any] | None
    access_token_expires_at: datetime | None
    refresh_token_expires_at: datetime | None
    access_token_ciphertext: str = field(repr=False)
    refresh_token_ciphertext: str | None = field(repr=False)


@dataclass(frozen=True)
class ConsumedState:
    """A just-consumed authorization state: who started it and what to redeem it with."""

    user_id: str
    connector_key: str
    redirect_uri: str
    code_verifier_ciphertext: str = field(repr=False)


@dataclass(frozen=True)
class AuditEntry:
    """One audit row. Never holds a token, code, state, argument or tool result."""

    user_id: str
    connector_key: str
    action: str
    outcome: str
    error_code: str | None = None
    tool_name: str | None = None
    run_id: str | None = None
    agent_ref: str | None = None
    duration_ms: int | None = None


def _audit_row(entry: AuditEntry, now: datetime) -> ConnectorAuditLog:
    return ConnectorAuditLog(
        user_id=entry.user_id,
        connector_key=entry.connector_key,
        action=entry.action,
        outcome=entry.outcome,
        error_code=entry.error_code,
        tool_name=entry.tool_name,
        run_id=entry.run_id,
        agent_ref=entry.agent_ref,
        duration_ms=entry.duration_ms,
        created_at=now,
    )


class LockedConnection:
    """A connection row held under ``SELECT ... FOR UPDATE`` inside one transaction.

    Writes are staged on the session and become durable only on ``commit()``. The
    refresh path commits the rotated tokens before it returns a token to anyone.
    """

    def __init__(self, db: Session, row: ConnectorConnection, clock: Clock) -> None:
        self._db = db
        self._row = row
        self._clock = clock

    @property
    def record(self) -> ConnectionRecord:
        """A snapshot of the locked row as it is now (including staged writes)."""
        return _record_from_row(self._row)

    def write_refreshed(
        self,
        *,
        access_token_ciphertext: str,
        refresh_token_ciphertext: str | None,
        access_token_expires_at: datetime | None,
        refresh_token_expires_at: datetime | None,
    ) -> int:
        """Stage rotated tokens, bump ``token_version`` and return the new version.

        A ``None`` refresh ciphertext or refresh expiry keeps the stored value: a
        provider that does not rotate returns no new refresh token.
        """
        now = self._clock()
        self._row.access_token_ciphertext = access_token_ciphertext
        if refresh_token_ciphertext is not None:
            self._row.refresh_token_ciphertext = refresh_token_ciphertext
            self._row.refresh_token_expires_at = refresh_token_expires_at
        self._row.access_token_expires_at = access_token_expires_at
        self._row.token_version = int(self._row.token_version or 0) + 1
        self._row.last_refreshed_at = now
        self._row.last_error_code = None
        self._row.status = CONNECTION_STATUS_ACTIVE
        self._row.updated_at = now
        return int(self._row.token_version)

    def write_expired(self, error_code: str) -> None:
        """Stage the ``expired`` status with a stable error code (never provider text)."""
        self._row.status = CONNECTION_STATUS_EXPIRED
        self._row.last_error_code = error_code
        self._row.updated_at = self._clock()

    def add_audit(self, entry: AuditEntry) -> None:
        """Stage an audit row in the same transaction."""
        self._db.add(_audit_row(entry, self._clock()))

    def commit(self) -> None:
        """Make every staged write durable and release the row lock."""
        self._db.commit()


class ConnectionStore:
    """Reads and writes connector rows for a verified ``user_id``."""

    def __init__(self, session_factory: SessionFactory, clock: Clock = utcnow) -> None:
        self._session_factory = session_factory
        self._clock = clock

    # ---- connections -------------------------------------------------------

    def get(self, user_id: str, connector_key: str) -> ConnectionRecord | None:
        """Return the user's connection to ``connector_key``, or ``None``."""
        with self._session_factory() as db:
            row = db.execute(
                select(ConnectorConnection).where(
                    ConnectorConnection.user_id == user_id,
                    ConnectorConnection.connector_key == connector_key,
                )
            ).scalar_one_or_none()
            return _record_from_row(row) if row is not None else None

    def list_for_user(self, user_id: str) -> list[ConnectionRecord]:
        """Return every connection of the user, ordered by connector key."""
        with self._session_factory() as db:
            rows = db.execute(
                select(ConnectorConnection)
                .where(ConnectorConnection.user_id == user_id)
                .order_by(ConnectorConnection.connector_key)
            ).scalars()
            return [_record_from_row(row) for row in rows]

    @staticmethod
    def records_for_update(db: Session, user_id: str) -> list[ConnectionRecord]:
        """Lock and read every connection of ``user_id`` inside the caller's transaction.

        Account deletion uses this before it deletes anything: ``FOR UPDATE`` is the
        lock a refresh takes, so a refresh already running finishes first and this
        read sees the rotated token. Nothing is written and nothing is committed.
        """
        rows = db.execute(
            select(ConnectorConnection)
            .where(ConnectorConnection.user_id == user_id)
            .order_by(ConnectorConnection.connector_key)
            .with_for_update()
        ).scalars()
        return [_record_from_row(row) for row in rows]

    def upsert(self, new: NewConnection) -> ConnectionRecord:
        """Create or replace the user's connection, as an ``active`` row.

        A reconnect replaces tokens and account, increments ``token_version``,
        clears the error code and restarts ``created_at`` (the "connected at"
        time). Two concurrent callbacks race on the unique constraint: the loser
        retries once as an update.
        """
        with self._session_factory() as db:
            attempt = 0
            while True:
                attempt += 1
                now = self._clock()
                row = db.execute(
                    select(ConnectorConnection).where(
                        ConnectorConnection.user_id == new.user_id,
                        ConnectorConnection.connector_key == new.connector_key,
                    )
                ).scalar_one_or_none()
                if row is None:
                    row = ConnectorConnection(
                        user_id=new.user_id,
                        connector_key=new.connector_key,
                        token_version=1,
                        created_at=now,
                    )
                    db.add(row)
                else:
                    row.token_version = int(row.token_version or 0) + 1
                    row.created_at = now
                row.status = CONNECTION_STATUS_ACTIVE
                row.provider_account_id = new.provider_account_id
                row.provider_account_login = new.provider_account_login
                row.provider_account_name = new.provider_account_name
                row.granted_scopes = list(new.granted_scopes)
                row.provider_metadata = new.provider_metadata
                row.access_token_ciphertext = new.access_token_ciphertext
                row.refresh_token_ciphertext = new.refresh_token_ciphertext
                row.access_token_expires_at = new.access_token_expires_at
                row.refresh_token_expires_at = new.refresh_token_expires_at
                row.last_refreshed_at = None
                row.last_error_code = None
                row.updated_at = now
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    if attempt >= 2:
                        raise
                    continue
                return _record_from_row(row)

    def delete(self, user_id: str, connector_key: str) -> bool:
        """Delete the user's connection. Returns whether a row existed."""
        with self._session_factory() as db:
            result = db.execute(
                delete(ConnectorConnection).where(
                    ConnectorConnection.user_id == user_id,
                    ConnectorConnection.connector_key == connector_key,
                )
            )
            db.commit()
            return bool(result.rowcount)  # type: ignore[attr-defined]

    def mark_expired(self, user_id: str, connector_key: str, error_code: str) -> bool:
        """Mark the user's connection ``expired``. Returns whether a row existed."""
        with self._session_factory() as db:
            result = db.execute(
                update(ConnectorConnection)
                .where(
                    ConnectorConnection.user_id == user_id,
                    ConnectorConnection.connector_key == connector_key,
                )
                .values(
                    status=CONNECTION_STATUS_EXPIRED,
                    last_error_code=error_code,
                    updated_at=self._clock(),
                )
            )
            db.commit()
            return bool(result.rowcount)  # type: ignore[attr-defined]

    @contextmanager
    def locked_connection(
        self, user_id: str, connector_key: str, *, lock_timeout_seconds: int
    ) -> Iterator[LockedConnection | None]:
        """Lock the user's connection row for update; yield ``None`` when it is absent.

        On PostgreSQL the transaction sets ``lock_timeout`` first, so a stuck lock
        raises ``OperationalError`` instead of waiting forever. On SQLite (tests)
        ``FOR UPDATE`` is a no-op. The session is closed on exit; anything not
        committed is rolled back.
        """
        db = self._session_factory()
        try:
            if db.get_bind().dialect.name == "postgresql":
                db.execute(
                    text("SELECT set_config('lock_timeout', :value, true)"),
                    {"value": f"{int(lock_timeout_seconds) * 1000}ms"},
                )
            row = db.execute(
                select(ConnectorConnection)
                .where(
                    ConnectorConnection.user_id == user_id,
                    ConnectorConnection.connector_key == connector_key,
                )
                .with_for_update()
            ).scalar_one_or_none()
            yield LockedConnection(db, row, self._clock) if row is not None else None
        finally:
            db.close()

    # ---- oauth states ------------------------------------------------------

    def create_state(
        self,
        *,
        user_id: str,
        connector_key: str,
        state_hash: str,
        code_verifier_ciphertext: str,
        redirect_uri: str,
        ttl_seconds: int,
        max_pending: int,
    ) -> datetime:
        """Store a new authorization state and return its expiry.

        The user's already-expired states are deleted first. When the user still
        has ``max_pending`` unexpired, unconsumed states, nothing is stored.

        Raises:
            TooManyPendingAuthorizations: the pending-state cap is reached.
        """
        with self._session_factory() as db:
            now = self._clock()
            db.execute(
                delete(OAuthState).where(
                    OAuthState.user_id == user_id, OAuthState.expires_at < now
                )
            )
            pending = db.execute(
                select(func.count())
                .select_from(OAuthState)
                .where(
                    OAuthState.user_id == user_id,
                    OAuthState.consumed_at.is_(None),
                    OAuthState.expires_at > now,
                )
            ).scalar_one()
            if pending >= max_pending:
                db.rollback()
                raise TooManyPendingAuthorizations(connector_key)
            expires_at = now + timedelta(seconds=ttl_seconds)
            db.add(
                OAuthState(
                    user_id=user_id,
                    connector_key=connector_key,
                    state_hash=state_hash,
                    code_verifier_ciphertext=code_verifier_ciphertext,
                    redirect_uri=redirect_uri,
                    created_at=now,
                    expires_at=expires_at,
                )
            )
            db.commit()
            return expires_at

    def consume_state(self, state_hash: str) -> ConsumedState | None:
        """Consume a state exactly once: one conditional ``UPDATE ... RETURNING``.

        Returns ``None`` for an unknown, expired or already-consumed state. Only the
        database is atomic across concurrent callbacks, so no read-then-write is used.
        """
        with self._session_factory() as db:
            now = self._clock()
            row = db.execute(
                update(OAuthState)
                .where(
                    OAuthState.state_hash == state_hash,
                    OAuthState.consumed_at.is_(None),
                    OAuthState.expires_at > now,
                )
                .values(consumed_at=now)
                .returning(
                    OAuthState.user_id,
                    OAuthState.connector_key,
                    OAuthState.code_verifier_ciphertext,
                    OAuthState.redirect_uri,
                )
                .execution_options(synchronize_session=False)
            ).first()
            db.commit()
            if row is None:
                return None
            return ConsumedState(
                user_id=row.user_id,
                connector_key=row.connector_key,
                code_verifier_ciphertext=row.code_verifier_ciphertext,
                redirect_uri=row.redirect_uri,
            )

    def sweep_expired_states(self, older_than: timedelta) -> int:
        """Delete up to a bounded batch of states that expired before ``now - older_than``."""
        with self._session_factory() as db:
            cutoff = self._clock() - older_than
            stale = (
                select(OAuthState.id)
                .where(OAuthState.expires_at < cutoff)
                .limit(_SWEEP_BATCH)
            )
            result = db.execute(delete(OAuthState).where(OAuthState.id.in_(stale)))
            db.commit()
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    # ---- audit -------------------------------------------------------------

    def record_audit(self, entry: AuditEntry) -> None:
        """Write one audit row in its own transaction. Never raises.

        A failed insert logs a WARNING (connector key and action only) and returns:
        auditing must not break a connect, a refresh or a tool call.
        """
        try:
            with self._session_factory() as db:
                db.add(_audit_row(entry, self._clock()))
                db.commit()
        except SQLAlchemyError:
            logger.warning(
                "connector audit insert failed connector=%s action=%s",
                entry.connector_key,
                entry.action,
            )
