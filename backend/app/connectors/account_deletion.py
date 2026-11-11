"""Revoke a deleted account's provider grants (best effort).

``admin.delete_user`` calls two steps around the deletion transaction:

1. ``collect`` runs inside the transaction, before any row is deleted. It locks the
   user's connections (``FOR UPDATE``, the lock a refresh takes) and decrypts the
   token each provider's revoke needs. It makes no provider call and writes nothing.
2. ``revoke`` runs after the commit. It sends one revoke per collected grant, one
   after the other, and returns the outcome per connector.

The tokens exist only in memory, in frozen dataclasses whose token fields are hidden
from ``repr``. Provider calls wait for the commit, so a provider outage can neither
block nor roll back the deletion, and no network call runs while row locks are held.
``revoke`` never raises. No audit row is written (the user's audit rows go with the
account); the record is the ``user_deleted`` auth event and the WARNING lines.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy.orm import Session

from agents.capabilities.connector_catalog import ConnectorDefinition
from app.connectors.adapters import RevokeMaterial, get_adapter
from app.connectors.crypto import TokenCodec
from app.connectors.errors import UndecryptableToken
from app.connectors.http import ProviderCallFailed
from app.connectors.oauth import OAuthClient
from app.connectors.registry import ClientCredentials, ConnectorRegistry
from app.connectors.store import ConnectionRecord, ConnectionStore, utcnow

logger = logging.getLogger("app.connectors.account_deletion")

RevocationResult = Literal["revoked", "failed", "not_attempted"]


@dataclass(frozen=True)
class CollectedGrant:
    """What the revoke of one connection needs. Token values are hidden from ``repr``."""

    connector_key: str
    attemptable: bool
    access_token: str = field(default="", repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    access_token_expires_at: datetime | None = None


class AccountDeletion:
    """Collects and revokes the provider grants of an account being deleted."""

    def __init__(
        self,
        *,
        registry: ConnectorRegistry,
        cipher: TokenCodec,
        client: OAuthClient,
        forget_user: Callable[[str], object],
        skew_seconds: int = 300,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._registry = registry
        self._cipher = cipher
        self._client = client
        self._forget_user = forget_user
        self._skew = timedelta(seconds=skew_seconds)
        self._clock = clock

    # ---- step 1: inside the deletion transaction ---------------------------

    def collect(self, db: Session, user_id: str) -> list[CollectedGrant]:
        """Lock the user's connections and decrypt the tokens their revokes need.

        A connection that cannot be revoked (unknown or unconfigured connector,
        undecryptable token) is returned as not attemptable. A database error
        propagates: the deletion transaction must roll back.
        """
        records = ConnectionStore.records_for_update(db, user_id)
        return [self._collect_one(record) for record in records]

    def _collect_one(self, record: ConnectionRecord) -> CollectedGrant:
        key = record.connector_key
        entry = self._registry.get(key)
        if entry is None or not entry.configured:
            logger.warning(
                "account deletion: revoke skipped connector=%s reason=not_configured",
                key,
            )
            return CollectedGrant(key, attemptable=False)
        try:
            access = self._cipher.decrypt(record.access_token_ciphertext)
            refresh = (
                self._cipher.decrypt(record.refresh_token_ciphertext)
                if record.refresh_token_ciphertext
                else None
            )
        except UndecryptableToken:
            logger.warning(
                "account deletion: revoke skipped connector=%s reason=undecryptable",
                key,
            )
            return CollectedGrant(key, attemptable=False)
        except Exception as exc:  # collect must not fail the deletion
            logger.warning(
                "account deletion: revoke skipped connector=%s reason=%s",
                key,
                type(exc).__name__,
            )
            return CollectedGrant(key, attemptable=False)
        return CollectedGrant(
            connector_key=key,
            attemptable=True,
            access_token=access,
            refresh_token=refresh,
            access_token_expires_at=record.access_token_expires_at,
        )

    # ---- step 2: after the commit ------------------------------------------

    def revoke(
        self, user_id: str, grants: list[CollectedGrant]
    ) -> dict[str, RevocationResult]:
        """Revoke every collected grant and return the outcome per connector. Never raises."""
        results: dict[str, RevocationResult] = {}
        for grant in grants:
            try:
                results[grant.connector_key] = self._revoke_one(grant)
            except Exception as exc:
                logger.warning(
                    "account deletion: revoke failed connector=%s reason=%s",
                    grant.connector_key,
                    type(exc).__name__,
                )
                results[grant.connector_key] = "failed"
        try:
            self._forget_user(user_id)
        except Exception as exc:
            logger.warning(
                "account deletion: tool cache not cleared error=%s", type(exc).__name__
            )
        return results

    def _revoke_one(self, grant: CollectedGrant) -> RevocationResult:
        key = grant.connector_key
        if not grant.attemptable:
            return "not_attempted"
        entry = self._registry.get(key)
        if entry is None or not entry.configured:
            return "not_attempted"
        definition = entry.definition
        credentials = self._registry.client_credentials(key)
        adapter = get_adapter(key)
        if adapter.revoke_needs_access_token:
            access_token = self._current_access_token(grant, definition, credentials)
            if access_token is None:
                return "failed"
            material = RevokeMaterial(access_token=access_token)
        else:
            material = RevokeMaterial(
                access_token=grant.access_token, refresh_token=grant.refresh_token
            )
        outcome = self._client.revoke(definition, credentials, material)
        if outcome == "failed":
            logger.warning("account deletion: provider revoke failed connector=%s", key)
        return outcome

    def _current_access_token(
        self,
        grant: CollectedGrant,
        definition: ConnectorDefinition,
        credentials: ClientCredentials,
    ) -> str | None:
        """Return a usable access token, refreshing in memory when it is (nearly) expired.

        Nothing is stored: the grant deletion that follows ends the new tokens too.
        """
        expires_at = grant.access_token_expires_at
        if expires_at is None or expires_at - self._skew > self._clock():
            return grant.access_token
        if not grant.refresh_token:
            logger.warning(
                "account deletion: no refresh token for an expired access token connector=%s",
                grant.connector_key,
            )
            return None
        try:
            tokens = self._client.refresh(definition, credentials, grant.refresh_token)
        except ProviderCallFailed as exc:
            logger.warning(
                "account deletion: token refresh failed connector=%s kind=%s code=%s",
                grant.connector_key,
                exc.kind,
                exc.error_code,
            )
            return None
        return tokens.access_token
