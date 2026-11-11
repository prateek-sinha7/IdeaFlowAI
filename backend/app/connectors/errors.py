"""Stable error codes and exceptions of the connectors runtime.

The codes are part of the contract with the model (tool error envelopes) and with
the browser (OAuth callback reasons), so they are enumerated once here. Messages
and exceptions never carry tokens, codes, state values or provider response bodies.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ToolErrorCode(StrEnum):
    """Codes a connector tool returns inside its error envelope (design section 5.6)."""

    CONNECTION_MISSING = "connection_missing"
    CONNECTION_EXPIRED = "connection_expired"
    NOT_CONFIGURED = "not_configured"
    SIGN_IN_REQUIRED = "sign_in_required"
    INSUFFICIENT_SCOPE = "insufficient_scope"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_ERROR = "provider_error"
    INVALID_ARGUMENTS = "invalid_arguments"
    TOOL_UNAVAILABLE = "tool_unavailable"
    CLIENT_MISCONFIGURED = "client_misconfigured"
    INTERNAL_ERROR = "internal_error"


#: Codes after which the same call can succeed without the user doing anything.
RECOVERABLE_TOOL_ERRORS: frozenset[ToolErrorCode] = frozenset(
    {
        ToolErrorCode.RATE_LIMITED,
        ToolErrorCode.PROVIDER_UNAVAILABLE,
        ToolErrorCode.INVALID_ARGUMENTS,
    }
)


class CallbackReason(StrEnum):
    """Reasons the OAuth callback hands to the landing page (design section 3)."""

    INVALID_STATE = "invalid_state"
    ACCESS_DENIED = "access_denied"
    PROVIDER_ERROR = "provider_error"
    MISSING_CODE = "missing_code"
    ISSUER_MISSING = "issuer_missing"
    ISSUER_MISMATCH = "issuer_mismatch"
    TOKEN_EXCHANGE_FAILED = "token_exchange_failed"
    ACCOUNT_LOOKUP_FAILED = "account_lookup_failed"
    NO_ACCESSIBLE_SITES = "no_accessible_sites"
    NOT_CONFIGURED = "not_configured"
    SERVER_ERROR = "server_error"


def is_recoverable(code: ToolErrorCode) -> bool:
    """Return whether ``code`` is worth retrying without user action."""
    return code in RECOVERABLE_TOOL_ERRORS


def error_envelope(
    code: ToolErrorCode, message: str, connector: str
) -> dict[str, dict[str, Any]]:
    """Build the error value a connector tool returns instead of raising."""
    return {
        "error": {
            "code": code.value,
            "message": message,
            "connector": connector,
            "recoverable": is_recoverable(code),
        }
    }


class ConnectorError(Exception):
    """Base of the connectors runtime errors. Carries a stable code, never a secret."""

    def __init__(
        self, code: ToolErrorCode, message: str, *, connector: str | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.connector = connector

    @property
    def recoverable(self) -> bool:
        """Whether retrying the same operation can succeed without user action."""
        return is_recoverable(self.code)


class ConnectorNotConfigured(ConnectorError):
    """The connector's settings are missing or invalid on this server."""

    def __init__(self, connector: str) -> None:
        super().__init__(
            ToolErrorCode.NOT_CONFIGURED,
            f"{connector} is not configured on this server",
            connector=connector,
        )


class ConnectorNotFound(ConnectorError):
    """No connector with the requested key exists in the catalog."""

    def __init__(self, connector: str) -> None:
        super().__init__(
            ToolErrorCode.NOT_FOUND,
            "no such connector",
            connector=connector,
        )


class TooManyPendingAuthorizations(ConnectorError):
    """The user already has the maximum number of unexpired, unconsumed states."""

    def __init__(self, connector: str) -> None:
        super().__init__(
            ToolErrorCode.RATE_LIMITED,
            "too many pending authorizations",
            connector=connector,
        )


class UndecryptableToken(ConnectorError):
    """No configured ``TOKEN_ENCRYPTION_KEY`` entry opens a stored ciphertext."""

    def __init__(self, connector: str | None = None) -> None:
        super().__init__(
            ToolErrorCode.CONNECTION_EXPIRED,
            "a stored token could not be decrypted",
            connector=connector,
        )
