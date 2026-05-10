"""Bedrock LLM exception mapping.

The backend uses AWS Bedrock via ``langchain_aws.ChatBedrockConverse`` which
wraps boto3 and raises ``botocore.exceptions.ClientError`` (with codes like
``ThrottlingException``, ``AccessDeniedException``, ``ValidationException``,
``ServiceUnavailableException``, ``ModelNotReadyException``,
``ModelStreamErrorException``…) plus connection-level errors
(``EndpointConnectionError``, ``ReadTimeoutError``, ``ConnectionError``).

The frontend's ``ErrorMessage`` component (``frontend/src/components/chat/
ErrorMessage.tsx``) keys off three things in the WebSocket ``error`` payload:

* ``error`` — human-friendly message shown to the user.
* ``code`` — short machine-friendly identifier (``api_key_missing``,
  ``auth_error``, ``rate_limit``, ``timeout``, ``connection_error``,
  ``internal_error``).
* ``recoverable`` — boolean. ``true`` shows a "Try Again" button; ``false``
  shows a static "this can't be retried" message.

This module maps any provider exception to that triple. Keep the codes and
messages stable: the frontend matches on them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("app.agents.llm_errors")


@dataclass(frozen=True)
class LLMErrorPayload:
    """Triple consumed by the WebSocket ``error`` event."""

    message: str
    code: str
    recoverable: bool


# ---------------------------------------------------------------------------
# botocore is imported lazily inside ``map_exception`` so a missing module
# (which would only happen in a malformed install) never breaks application
# startup — it simply falls through to the generic ``internal_error`` branch.
# ---------------------------------------------------------------------------

# Bedrock / botocore error-code → (code, recoverable)
# Drawn from the Bedrock Runtime API docs:
# https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html
_BEDROCK_CODE_MAP: dict[str, tuple[str, bool]] = {
    # Throttling / quota
    "ThrottlingException": ("rate_limit", True),
    "ServiceQuotaExceededException": ("rate_limit", True),
    "TooManyRequestsException": ("rate_limit", True),
    # Service-side errors
    "ServiceUnavailableException": ("connection_error", True),
    "InternalServerException": ("internal_error", True),
    "ModelNotReadyException": ("connection_error", True),
    "ModelStreamErrorException": ("connection_error", True),
    "ModelTimeoutException": ("timeout", True),
    # Auth / config
    "AccessDeniedException": ("auth_error", False),
    "UnauthorizedException": ("auth_error", False),
    "ResourceNotFoundException": ("api_key_missing", False),
    # Validation (caller-side; not retryable)
    "ValidationException": ("internal_error", False),
    "ModelErrorException": ("internal_error", True),
}


def map_exception(exc: BaseException) -> LLMErrorPayload:
    """Map any LLM-call exception to the triple shown to the user.

    Recognises Bedrock (botocore) errors and falls back to a generic
    ``internal_error`` for everything else.
    """
    # ---- Bedrock / botocore ------------------------------------------------
    try:
        from botocore import exceptions as botocore_exc

        if isinstance(exc, botocore_exc.ClientError):
            error = getattr(exc, "response", {}).get("Error", {}) or {}
            aws_code = error.get("Code") or "Unknown"
            mapped = _BEDROCK_CODE_MAP.get(aws_code)
            if mapped:
                code, recoverable = mapped
                return LLMErrorPayload(_message_for(code), code, recoverable)
            logger.warning("Unmapped Bedrock error code: %s", aws_code)
            return LLMErrorPayload(_message_for("internal_error"), "internal_error", True)

        if isinstance(exc, (botocore_exc.ConnectTimeoutError, botocore_exc.ReadTimeoutError)):
            return LLMErrorPayload(_message_for("timeout"), "timeout", True)

        if isinstance(
            exc,
            (
                botocore_exc.EndpointConnectionError,
                botocore_exc.ConnectionError,
                botocore_exc.ConnectionClosedError,
            ),
        ):
            return LLMErrorPayload(_message_for("connection_error"), "connection_error", True)

        # Credentials missing or partial — IAM/IMDS/profile misconfiguration.
        # Not retryable: every subsequent agent in the same pipeline will hit
        # the same wall, and the user can't fix it from the chat UI.
        # `recoverable=False` so the orchestrator short-circuits the pipeline
        # instead of plowing through six identical failures.
        if isinstance(exc, (botocore_exc.NoCredentialsError, botocore_exc.PartialCredentialsError)):
            return LLMErrorPayload(_message_for("auth_error"), "auth_error", False)
    except ImportError:  # pragma: no cover — botocore is always installed when Bedrock is in use
        pass

    # ---- Fallback ----------------------------------------------------------
    return LLMErrorPayload(_message_for("internal_error"), "internal_error", True)


# Stable user-facing copy. Frontend keys off ``code``; this message is what
# replaces the generic copy when the frontend chooses not to render its own.
_USER_MESSAGES: dict[str, str] = {
    "api_key_missing": "AI service is not configured. Please contact the administrator.",
    "auth_error": "AI service authentication failed. Please contact the administrator.",
    "rate_limit": "Too many requests. Please wait a moment and try again.",
    "timeout": "The AI service took too long to respond. Please try again.",
    "connection_error": "Unable to reach the AI service. Please check your connection and try again.",
    "internal_error": "Something went wrong. Please try again.",
}


def _message_for(code: str) -> str:
    return _USER_MESSAGES.get(code, _USER_MESSAGES["internal_error"])
