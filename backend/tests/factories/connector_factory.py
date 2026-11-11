"""Builders for connector rows (connections, OAuth states).

Each builder returns an ORM instance that is not attached to any database session,
with every ``NOT NULL`` column filled. Token columns hold placeholder ciphertext;
pass real ciphertext (``TokenCipher.encrypt``) when a test needs the runtime to
decrypt it. Keyword overrides replace any column.
"""

from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.connector import (
    CONNECTION_STATUS_ACTIVE,
    ConnectorConnection,
    OAuthState,
)

DEFAULT_USER_ID = "user-1"
_counter = itertools.count(1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ConnectorConnectionFactory:
    """Builds ``ConnectorConnection`` rows."""

    @staticmethod
    def build(**overrides: Any) -> ConnectorConnection:
        """A GitHub connection for ``DEFAULT_USER_ID`` with placeholder ciphertext."""
        n = next(_counter)
        now = _now()
        values: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "user_id": DEFAULT_USER_ID,
            "connector_key": "github",
            "status": CONNECTION_STATUS_ACTIVE,
            "provider_account_id": f"acct-{n}",
            "provider_account_login": f"login-{n}",
            "provider_account_name": f"Name {n}",
            "granted_scopes": ["repo"],
            "provider_metadata": None,
            "access_token_ciphertext": f"access-ciphertext-{n}",
            "refresh_token_ciphertext": f"refresh-ciphertext-{n}",
            "access_token_expires_at": now + timedelta(hours=8),
            "refresh_token_expires_at": None,
            "token_version": 1,
            "last_refreshed_at": None,
            "last_error_code": None,
            "created_at": now,
            "updated_at": now,
        }
        values.update(overrides)
        return ConnectorConnection(**values)


class OAuthStateFactory:
    """Builds ``OAuthState`` rows."""

    @staticmethod
    def build(**overrides: Any) -> OAuthState:
        """An unconsumed state for ``DEFAULT_USER_ID`` expiring in 10 minutes."""
        n = next(_counter)
        now = _now()
        values: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "user_id": DEFAULT_USER_ID,
            "connector_key": "github",
            "state_hash": f"{n:064x}",
            "code_verifier_ciphertext": f"verifier-ciphertext-{n}",
            "redirect_uri": "http://localhost:3000/api/connectors/oauth/callback",
            "created_at": now,
            "expires_at": now + timedelta(seconds=600),
            "consumed_at": None,
        }
        values.update(overrides)
        return OAuthState(**values)
