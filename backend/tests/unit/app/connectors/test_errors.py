"""Unit tests for ``app.connectors.errors``."""

from __future__ import annotations

import pytest

from app.connectors import errors
from app.connectors.errors import (
    RECOVERABLE_TOOL_ERRORS,
    CallbackReason,
    ConnectorError,
    ConnectorNotConfigured,
    ToolErrorCode,
    UndecryptableToken,
    error_envelope,
    is_recoverable,
)

_EXPECTED_TOOL_CODES = {
    "connection_missing",
    "connection_expired",
    "not_configured",
    "sign_in_required",
    "insufficient_scope",
    "permission_denied",
    "not_found",
    "rate_limited",
    "provider_unavailable",
    "provider_error",
    "invalid_arguments",
    "tool_unavailable",
    "client_misconfigured",
    "internal_error",
}

_EXPECTED_CALLBACK_REASONS = {
    "invalid_state",
    "access_denied",
    "provider_error",
    "missing_code",
    "issuer_missing",
    "issuer_mismatch",
    "token_exchange_failed",
    "account_lookup_failed",
    "no_accessible_sites",
    "not_configured",
    "server_error",
}


def test_tool_error_codes_match_design_when_enumerated():
    # Assert
    assert {code.value for code in ToolErrorCode} == _EXPECTED_TOOL_CODES


def test_callback_reasons_match_design_when_enumerated():
    # Assert
    assert {reason.value for reason in CallbackReason} == _EXPECTED_CALLBACK_REASONS


def test_recoverable_set_is_rate_limit_unavailable_and_invalid_arguments_when_defined():
    # Assert
    assert RECOVERABLE_TOOL_ERRORS == {
        ToolErrorCode.RATE_LIMITED,
        ToolErrorCode.PROVIDER_UNAVAILABLE,
        ToolErrorCode.INVALID_ARGUMENTS,
    }


@pytest.mark.parametrize("code", list(ToolErrorCode))
def test_is_recoverable_follows_set_when_code_checked(code):
    # Assert
    assert is_recoverable(code) is (code in RECOVERABLE_TOOL_ERRORS)


def test_error_envelope_has_documented_shape_when_built():
    # Act
    envelope = error_envelope(
        ToolErrorCode.CONNECTION_MISSING,
        "Jira connection missing, reconnect in Connectors",
        "jira",
    )

    # Assert
    assert envelope == {
        "error": {
            "code": "connection_missing",
            "message": "Jira connection missing, reconnect in Connectors",
            "connector": "jira",
            "recoverable": False,
        }
    }


def test_error_envelope_marks_recoverable_when_rate_limited():
    # Act
    envelope = error_envelope(ToolErrorCode.RATE_LIMITED, "slow down", "jira")

    # Assert
    assert envelope["error"]["recoverable"] is True


def test_connector_error_exposes_code_and_recoverable_when_raised():
    # Act
    error = ConnectorError(
        ToolErrorCode.PROVIDER_UNAVAILABLE, "down", connector="github"
    )

    # Assert
    assert error.code is ToolErrorCode.PROVIDER_UNAVAILABLE
    assert error.connector == "github"
    assert error.recoverable is True
    assert str(error) == "down"


def test_connector_not_configured_carries_not_configured_code_when_raised():
    # Act
    error = ConnectorNotConfigured("jira")

    # Assert
    assert error.code is ToolErrorCode.NOT_CONFIGURED
    assert error.connector == "jira"
    assert error.recoverable is False


def test_undecryptable_token_means_connection_expired_when_raised():
    # Act
    error = UndecryptableToken("github")

    # Assert
    assert error.code is ToolErrorCode.CONNECTION_EXPIRED
    assert error.connector == "github"
    assert isinstance(error, ConnectorError)


def test_connector_not_found_carries_not_found_code_when_raised():
    # Act
    error = errors.ConnectorNotFound("slack")

    # Assert
    assert error.code is ToolErrorCode.NOT_FOUND
    assert error.connector == "slack"
    assert error.recoverable is False


def test_too_many_pending_authorizations_is_rate_limited_and_recoverable_when_raised():
    # Act
    error = errors.TooManyPendingAuthorizations("github")

    # Assert
    assert error.code is ToolErrorCode.RATE_LIMITED
    assert error.recoverable is True
