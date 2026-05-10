"""Provider-agnostic LLM exception mapping.

The backend supports two LLM providers (see ``app.core.config``):

* AWS Bedrock via ``langchain_aws.ChatBedrockConverse`` — wraps boto3, raises
  ``botocore.exceptions.ClientError`` (with codes like ``ThrottlingException``,
  ``AccessDeniedException``, ``ValidationException``,
  ``ServiceUnavailableException``, ``ModelNotReadyException``,
  ``ModelStreamErrorException``…) plus connection-level errors
  (``EndpointConnectionError``, ``ReadTimeoutError``, ``ConnectionError``).
* Direct Anthropic API via ``langchain_anthropic.ChatAnthropic`` — raises
  ``anthropic.APITimeoutError``, ``RateLimitError``, ``APIConnectionError``,
  ``AuthenticationError``, ``BadRequestError``, etc.

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
# Imports are deliberately lazy: each provider lib may not be installed in
# every environment (langchain-anthropic is optional in a Bedrock-only deploy
# and vice versa). We import inside the ``map_*`` helpers so a missing module
# never breaks application startup.
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

    Recognises Bedrock (botocore), Anthropic (anthropic SDK), and falls back
    to a generic ``internal_error`` for everything else.
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
    except ImportError:  # pragma: no cover — botocore is always installed when Bedrock is in use
        pass

    # ---- Anthropic direct --------------------------------------------------
    try:
        import anthropic

        if isinstance(exc, anthropic.APITimeoutError):
            return LLMErrorPayload(_message_for("timeout"), "timeout", True)
        if isinstance(exc, anthropic.RateLimitError):
            return LLMErrorPayload(_message_for("rate_limit"), "rate_limit", True)
        if isinstance(exc, anthropic.APIConnectionError):
            return LLMErrorPayload(_message_for("connection_error"), "connection_error", True)
        if isinstance(exc, anthropic.AuthenticationError):
            return LLMErrorPayload(_message_for("auth_error"), "auth_error", False)
        if isinstance(exc, anthropic.BadRequestError):
            return LLMErrorPayload(_message_for("internal_error"), "internal_error", False)
        if isinstance(exc, anthropic.APIError):
            return LLMErrorPayload(_message_for("internal_error"), "internal_error", True)
    except ImportError:  # pragma: no cover — anthropic is always installed today
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
