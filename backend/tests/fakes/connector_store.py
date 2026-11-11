"""In-memory stand-in for ``ConnectionStore`` and a settable clock.

``FakeConnectionStore`` has the public surface the OAuth service and the token
provider use, and the same observable behaviour: a state is consumed once,
the pending cap is enforced, ``locked_connection`` serializes writers like
``SELECT ... FOR UPDATE`` and a staged write becomes visible only on ``commit``.
The SQL itself is proven by ``tests/integration/repositories/test_connector_store_db.py``.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.connectors.errors import TooManyPendingAuthorizations
from app.connectors.store import (
    AuditEntry,
    ConnectionRecord,
    ConsumedState,
    NewConnection,
)
from app.models.connector import CONNECTION_STATUS_ACTIVE, CONNECTION_STATUS_EXPIRED

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class MutableClock:
    """A UTC clock tests move by hand."""

    def __init__(self, start: datetime = T0) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        """Move the clock forward."""
        self.now += timedelta(seconds=seconds)


class _FakeLocked:
    """Staged writes on one connection; ``commit`` publishes them."""

    def __init__(self, store: FakeConnectionStore, record: ConnectionRecord) -> None:
        self._store = store
        self._pending = record
        self._audit: list[AuditEntry] = []

    @property
    def record(self) -> ConnectionRecord:
        return self._pending

    def write_refreshed(
        self,
        *,
        access_token_ciphertext: str,
        refresh_token_ciphertext: str | None,
        access_token_expires_at: datetime | None,
        refresh_token_expires_at: datetime | None,
    ) -> int:
        changes: dict[str, Any] = {
            "access_token_ciphertext": access_token_ciphertext,
            "access_token_expires_at": access_token_expires_at,
            "token_version": self._pending.token_version + 1,
            "last_refreshed_at": self._store.clock(),
            "last_error_code": None,
            "status": CONNECTION_STATUS_ACTIVE,
        }
        if refresh_token_ciphertext is not None:
            changes["refresh_token_ciphertext"] = refresh_token_ciphertext
            changes["refresh_token_expires_at"] = refresh_token_expires_at
        self._pending = replace(self._pending, **changes)
        return self._pending.token_version

    def write_expired(self, error_code: str) -> None:
        self._pending = replace(
            self._pending,
            status=CONNECTION_STATUS_EXPIRED,
            last_error_code=error_code,
        )

    def add_audit(self, entry: AuditEntry) -> None:
        self._audit.append(entry)

    def commit(self) -> None:
        if self._store.fail_commit:
            raise SQLAlchemyError("simulated commit failure")
        self._store.connections[
            (self._pending.user_id, self._pending.connector_key)
        ] = self._pending
        self._store.audit.extend(self._audit)
        self._audit = []


class FakeConnectionStore:
    """Dictionary-backed ``ConnectionStore``."""

    def __init__(self, clock: MutableClock | None = None) -> None:
        self.clock = clock or MutableClock()
        self.connections: dict[tuple[str, str], ConnectionRecord] = {}
        self.states: dict[str, dict[str, Any]] = {}
        self.audit: list[AuditEntry] = []
        self.fail_commit = False
        self.fail_upsert = False
        self.lock_waits = 0
        self._row_lock = threading.Lock()

    # ---- connections -------------------------------------------------------

    def get(self, user_id: str, connector_key: str) -> ConnectionRecord | None:
        return self.connections.get((user_id, connector_key))

    def list_for_user(self, user_id: str) -> list[ConnectionRecord]:
        return sorted(
            (c for (u, _), c in self.connections.items() if u == user_id),
            key=lambda c: c.connector_key,
        )

    def upsert(self, new: NewConnection) -> ConnectionRecord:
        if self.fail_upsert:
            raise SQLAlchemyError("simulated upsert failure")
        now = self.clock()
        existing = self.connections.get((new.user_id, new.connector_key))
        record = ConnectionRecord(
            id=existing.id if existing else f"conn-{len(self.connections) + 1}",
            user_id=new.user_id,
            connector_key=new.connector_key,
            status=CONNECTION_STATUS_ACTIVE,
            provider_account_id=new.provider_account_id,
            provider_account_login=new.provider_account_login,
            provider_account_name=new.provider_account_name,
            granted_scopes=new.granted_scopes,
            provider_metadata=new.provider_metadata,
            access_token_expires_at=new.access_token_expires_at,
            refresh_token_expires_at=new.refresh_token_expires_at,
            token_version=(existing.token_version + 1) if existing else 1,
            last_refreshed_at=None,
            last_error_code=None,
            created_at=now,
            updated_at=now,
            access_token_ciphertext=new.access_token_ciphertext,
            refresh_token_ciphertext=new.refresh_token_ciphertext,
        )
        self.connections[(new.user_id, new.connector_key)] = record
        return record

    def seed(self, record: ConnectionRecord) -> ConnectionRecord:
        """Insert a prepared record as it is."""
        self.connections[(record.user_id, record.connector_key)] = record
        return record

    def delete(self, user_id: str, connector_key: str) -> bool:
        return self.connections.pop((user_id, connector_key), None) is not None

    def mark_expired(self, user_id: str, connector_key: str, error_code: str) -> bool:
        record = self.connections.get((user_id, connector_key))
        if record is None:
            return False
        self.connections[(user_id, connector_key)] = replace(
            record, status=CONNECTION_STATUS_EXPIRED, last_error_code=error_code
        )
        return True

    @contextmanager
    def locked_connection(
        self, user_id: str, connector_key: str, *, lock_timeout_seconds: int
    ) -> Iterator[_FakeLocked | None]:
        del lock_timeout_seconds
        with self._row_lock:
            record = self.connections.get((user_id, connector_key))
            yield _FakeLocked(self, record) if record is not None else None

    # ---- states ------------------------------------------------------------

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
        now = self.clock()
        self.states = {
            h: s
            for h, s in self.states.items()
            if not (s["user_id"] == user_id and s["expires_at"] < now)
        }
        pending = [
            s
            for s in self.states.values()
            if s["user_id"] == user_id
            and s["consumed_at"] is None
            and s["expires_at"] > now
        ]
        if len(pending) >= max_pending:
            raise TooManyPendingAuthorizations(connector_key)
        expires_at = now + timedelta(seconds=ttl_seconds)
        self.states[state_hash] = {
            "user_id": user_id,
            "connector_key": connector_key,
            "verifier": code_verifier_ciphertext,
            "redirect_uri": redirect_uri,
            "expires_at": expires_at,
            "consumed_at": None,
        }
        return expires_at

    def consume_state(self, state_hash: str) -> ConsumedState | None:
        state = self.states.get(state_hash)
        now = self.clock()
        if (
            state is None
            or state["consumed_at"] is not None
            or state["expires_at"] <= now
        ):
            return None
        state["consumed_at"] = now
        return ConsumedState(
            user_id=state["user_id"],
            connector_key=state["connector_key"],
            redirect_uri=state["redirect_uri"],
            code_verifier_ciphertext=state["verifier"],
        )

    def sweep_expired_states(self, older_than: timedelta) -> int:
        cutoff = self.clock() - older_than
        stale = [h for h, s in self.states.items() if s["expires_at"] < cutoff]
        for state_hash in stale:
            del self.states[state_hash]
        return len(stale)

    # ---- audit -------------------------------------------------------------

    def record_audit(self, entry: AuditEntry) -> None:
        self.audit.append(entry)

    def audit_actions(self) -> list[tuple[str, str, str | None]]:
        """``(action, outcome, error_code)`` of every audit row, in order."""
        return [(a.action, a.outcome, a.error_code) for a in self.audit]
