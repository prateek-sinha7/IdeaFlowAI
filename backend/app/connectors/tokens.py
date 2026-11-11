"""Access tokens for connector calls: single-flight refresh with rotation.

``TokenProvider.access_token(user_id, key)`` returns a valid access token for the
user's connection, refreshing it ``CONNECTOR_REFRESH_SKEW_SECONDS`` (300 s) before
expiry or after a provider answered 401 (``force_refresh``).

Both providers rotate refresh tokens, and a lost race invalidates the losing
refresh token, so refreshes are serialized twice (design section 1.3):

* an in-process ``asyncio.Lock`` per (user, connector) and event loop, so parallel
  tool calls wait on one coroutine instead of many worker threads;
* a PostgreSQL row lock (``SELECT ... FOR UPDATE`` with ``lock_timeout``), so a
  second process cannot refresh the same connection at the same time.

Inside the row lock the provider is called, the rotated tokens are written and the
transaction is **committed before any token is returned**. A caller that arrives
after another refresh sees a moved ``token_version`` and uses the stored token.
Failures never leak a token or a provider response body.
"""

from __future__ import annotations

import asyncio
import logging
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import NoReturn

from sqlalchemy.exc import SQLAlchemyError

from app.connectors.crypto import TokenCodec
from app.connectors.errors import (
    ConnectorError,
    ConnectorNotConfigured,
    ConnectorNotFound,
    ToolErrorCode,
    UndecryptableToken,
)
from app.connectors.http import ProviderCallFailed
from app.connectors.oauth import OAuthClient
from app.connectors.registry import ConnectorRegistry
from app.connectors.store import (
    AuditEntry,
    ConnectionRecord,
    ConnectionStore,
    LockedConnection,
    utcnow,
)
from app.models.connector import (
    AUDIT_OUTCOME_ERROR,
    AUDIT_OUTCOME_OK,
    AUDIT_REFRESH_FAILED,
    AUDIT_REFRESHED,
)

logger = logging.getLogger("app.connectors.tokens")

_UNDECRYPTABLE = "undecryptable"
_NO_REFRESH_TOKEN = "no_refresh_token"


@dataclass(frozen=True)
class AccessToken:
    """A usable access token and the ``token_version`` it was read at."""

    token: str = field(repr=False)
    version: int


@dataclass(frozen=True)
class _Reading:
    token: AccessToken
    needs_refresh: bool


class TokenProvider:
    """Hands out valid access tokens for (user, connector), refreshing when needed."""

    def __init__(
        self,
        *,
        registry: ConnectorRegistry,
        store: ConnectionStore,
        cipher: TokenCodec,
        client: OAuthClient,
        skew_seconds: int = 300,
        lock_timeout_seconds: int = 15,
        read_timeout_seconds: float = 10.0,
        refresh_timeout_seconds: float = 20.0,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._registry = registry
        self._store = store
        self._cipher = cipher
        self._client = client
        self._skew = timedelta(seconds=skew_seconds)
        self._lock_timeout_seconds = lock_timeout_seconds
        self._read_timeout = read_timeout_seconds
        self._refresh_timeout = refresh_timeout_seconds
        self._clock = clock
        # One lock table per event loop: asyncio locks must not cross loops.
        self._locks: weakref.WeakKeyDictionary[
            asyncio.AbstractEventLoop,
            weakref.WeakValueDictionary[tuple[str, str], asyncio.Lock],
        ] = weakref.WeakKeyDictionary()

    # ---- public API --------------------------------------------------------

    async def access_token(
        self,
        user_id: str,
        connector_key: str,
        *,
        force_refresh: bool = False,
        rejected_version: int | None = None,
    ) -> AccessToken:
        """Return a valid access token for the user's connection.

        ``force_refresh`` refreshes even when the token is not near expiry (the
        provider answered 401). ``rejected_version`` is the ``token_version`` of
        the token that was rejected; if another caller already replaced it, the
        stored token is returned without a second refresh.

        Raises:
            ConnectorError: ``connection_missing``, ``connection_expired``,
                ``not_configured``, ``client_misconfigured``,
                ``provider_unavailable`` or ``provider_error``.
        """
        try:
            reading = await asyncio.wait_for(
                asyncio.to_thread(self._read_current, user_id, connector_key),
                self._read_timeout,
            )
        except TimeoutError as exc:
            raise self._unavailable(connector_key) from exc
        if not (force_refresh or reading.needs_refresh):
            return reading.token
        observed = (
            rejected_version if rejected_version is not None else reading.token.version
        )
        async with self._async_lock(user_id, connector_key):
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(
                        self._refresh_locked, user_id, connector_key, observed
                    ),
                    self._refresh_timeout,
                )
            except TimeoutError as exc:
                raise self._unavailable(connector_key) from exc

    def access_token_blocking(
        self,
        user_id: str,
        connector_key: str,
        *,
        force_refresh: bool = False,
        rejected_version: int | None = None,
    ) -> AccessToken:
        """Synchronous ``access_token`` for threadpool callers (no asyncio lock).

        The PostgreSQL row lock still serializes refreshes across threads and
        processes.
        """
        reading = self._read_current(user_id, connector_key)
        if not (force_refresh or reading.needs_refresh):
            return reading.token
        observed = (
            rejected_version if rejected_version is not None else reading.token.version
        )
        return self._refresh_locked(user_id, connector_key, observed)

    def fresh_access_token(self, user_id: str, connector_key: str) -> str:
        """Return a current access token string, refreshing it when near expiry.

        Implements ``FreshAccessTokenSource`` for the disconnect flow.
        """
        return self.access_token_blocking(user_id, connector_key).token

    # ---- reading -----------------------------------------------------------

    def _definition_checked(self, connector_key: str) -> None:
        entry = self._registry.get(connector_key)
        if entry is None:
            raise ConnectorNotFound(connector_key)
        if not entry.configured:
            raise ConnectorNotConfigured(connector_key)

    def _read_current(self, user_id: str, connector_key: str) -> _Reading:
        self._definition_checked(connector_key)
        record = self._store.get(user_id, connector_key)
        if record is None:
            raise self._missing(connector_key)
        if not record.is_active:
            raise self._expired(connector_key)
        try:
            token = self._cipher.decrypt(record.access_token_ciphertext)
        except UndecryptableToken as exc:
            self._expire_undecryptable(user_id, connector_key)
            raise self._expired(connector_key) from exc
        return _Reading(
            token=AccessToken(token=token, version=record.token_version),
            needs_refresh=self._near_expiry(record),
        )

    def _near_expiry(self, record: ConnectionRecord) -> bool:
        expires_at = record.access_token_expires_at
        return expires_at is not None and expires_at - self._skew <= self._clock()

    def _expire_undecryptable(self, user_id: str, connector_key: str) -> None:
        logger.error("stored token is undecryptable connector=%s", connector_key)
        try:
            self._store.mark_expired(user_id, connector_key, _UNDECRYPTABLE)
        except SQLAlchemyError as exc:
            logger.warning(
                "could not mark connection expired connector=%s error=%s",
                connector_key,
                type(exc).__name__,
            )

    # ---- refresh -----------------------------------------------------------

    def _refresh_locked(
        self, user_id: str, connector_key: str, observed_version: int
    ) -> AccessToken:
        """Refresh under the row lock; commit before returning the new token."""
        self._definition_checked(connector_key)
        try:
            with self._store.locked_connection(
                user_id,
                connector_key,
                lock_timeout_seconds=self._lock_timeout_seconds,
            ) as locked:
                if locked is None:
                    raise self._missing(connector_key)
                record = locked.record
                if not record.is_active:
                    raise self._expired(connector_key)
                try:
                    if record.token_version != observed_version:
                        # Another caller refreshed since this one looked: use theirs.
                        return AccessToken(
                            token=self._cipher.decrypt(record.access_token_ciphertext),
                            version=record.token_version,
                        )
                    refresh_token = (
                        self._cipher.decrypt(record.refresh_token_ciphertext)
                        if record.refresh_token_ciphertext
                        else None
                    )
                except UndecryptableToken as exc:
                    self._expire_locked(locked, user_id, connector_key, _UNDECRYPTABLE)
                    raise self._expired(connector_key) from exc
                if refresh_token is None:
                    self._expire_locked(
                        locked, user_id, connector_key, _NO_REFRESH_TOKEN
                    )
                    raise self._expired(connector_key)
                return self._exchange_and_commit(
                    locked,
                    user_id,
                    connector_key,
                    refresh_token,
                )
        except SQLAlchemyError as exc:
            logger.warning(
                "refresh could not use the database connector=%s error=%s",
                connector_key,
                type(exc).__name__,
            )
            raise self._unavailable(connector_key) from exc

    def _exchange_and_commit(
        self,
        locked: LockedConnection,
        user_id: str,
        connector_key: str,
        refresh_token: str,
    ) -> AccessToken:
        entry = self._registry.get(connector_key)
        assert entry is not None  # checked by the caller
        try:
            tokens = self._client.refresh(
                entry.definition,
                self._registry.client_credentials(connector_key),
                refresh_token,
            )
        except ProviderCallFailed as exc:
            self._raise_refresh_failure(locked, user_id, connector_key, exc)
        now = self._clock()
        refresh_expiry = (
            now + timedelta(seconds=tokens.refresh_token_expires_in)
            if tokens.refresh_token_expires_in and tokens.refresh_token_expires_in > 0
            else None
        )
        access_expiry = (
            now + timedelta(seconds=tokens.expires_in)
            if tokens.expires_in and tokens.expires_in > 0
            else None
        )
        version = locked.write_refreshed(
            access_token_ciphertext=self._cipher.encrypt(tokens.access_token),
            refresh_token_ciphertext=(
                self._cipher.encrypt(tokens.refresh_token)
                if tokens.refresh_token
                else None
            ),
            access_token_expires_at=access_expiry,
            refresh_token_expires_at=refresh_expiry,
        )
        locked.add_audit(
            AuditEntry(
                user_id=user_id,
                connector_key=connector_key,
                action=AUDIT_REFRESHED,
                outcome=AUDIT_OUTCOME_OK,
            )
        )
        try:
            locked.commit()
        except SQLAlchemyError as exc:
            # The provider may already have rotated the refresh token: the stored
            # one is now stale and the next attempt can expire the connection.
            logger.error(
                "refresh commit failed after the provider rotated tokens connector=%s error=%s",
                connector_key,
                type(exc).__name__,
            )
            raise self._unavailable(connector_key) from exc
        return AccessToken(token=tokens.access_token, version=version)

    def _raise_refresh_failure(
        self,
        locked: LockedConnection,
        user_id: str,
        connector_key: str,
        exc: ProviderCallFailed,
    ) -> NoReturn:
        """Map a failed refresh call to the connector error; always raises."""
        if exc.kind == "rejected":
            logger.info(
                "refresh rejected, connection expired connector=%s code=%s",
                connector_key,
                exc.error_code,
            )
            self._expire_locked(
                locked, user_id, connector_key, exc.error_code or "refresh_rejected"
            )
            raise self._expired(connector_key) from exc
        if exc.kind == "client":
            definition = self._registry.get(connector_key)
            logger.error(
                "refresh refused the client credentials connector=%s; check %s and %s",
                connector_key,
                definition.definition.client_id_env if definition else "?",
                definition.definition.client_secret_env if definition else "?",
            )
            raise ConnectorError(
                ToolErrorCode.CLIENT_MISCONFIGURED,
                f"{self._display(connector_key)} is misconfigured on this server",
                connector=connector_key,
            ) from exc
        if exc.kind == "malformed":
            logger.warning("refresh answer was unusable connector=%s", connector_key)
            raise ConnectorError(
                ToolErrorCode.PROVIDER_ERROR,
                f"{self._display(connector_key)} returned an unusable answer",
                connector=connector_key,
            ) from exc
        logger.warning(
            "refresh unavailable connector=%s status=%s", connector_key, exc.status
        )
        raise self._unavailable(connector_key) from exc

    def _expire_locked(
        self,
        locked: LockedConnection,
        user_id: str,
        connector_key: str,
        error_code: str,
    ) -> None:
        """Stage and commit the ``expired`` status plus a ``refresh_failed`` audit row."""
        locked.write_expired(error_code)
        locked.add_audit(
            AuditEntry(
                user_id=user_id,
                connector_key=connector_key,
                action=AUDIT_REFRESH_FAILED,
                outcome=AUDIT_OUTCOME_ERROR,
                error_code=error_code,
            )
        )
        locked.commit()

    # ---- locks and errors --------------------------------------------------

    def _async_lock(self, user_id: str, connector_key: str) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        table = self._locks.get(loop)
        if table is None:
            table = weakref.WeakValueDictionary()
            self._locks[loop] = table
        key = (user_id, connector_key)
        lock = table.get(key)
        if lock is None:
            lock = asyncio.Lock()
            table[key] = lock
        return lock

    def _display(self, connector_key: str) -> str:
        entry = self._registry.get(connector_key)
        return entry.definition.display_name if entry else connector_key

    def _missing(self, connector_key: str) -> ConnectorError:
        return ConnectorError(
            ToolErrorCode.CONNECTION_MISSING,
            f"{self._display(connector_key)} connection missing, reconnect in Connectors",
            connector=connector_key,
        )

    def _expired(self, connector_key: str) -> ConnectorError:
        return ConnectorError(
            ToolErrorCode.CONNECTION_EXPIRED,
            f"{self._display(connector_key)} connection expired, reconnect in Connectors",
            connector=connector_key,
        )

    def _unavailable(self, connector_key: str) -> ConnectorError:
        return ConnectorError(
            ToolErrorCode.PROVIDER_UNAVAILABLE,
            f"{self._display(connector_key)} is temporarily unavailable",
            connector=connector_key,
        )
