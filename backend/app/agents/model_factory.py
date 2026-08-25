"""app/agents/model_factory.py — single source of truth for building the LLM client.

Every agent graph builds its chat model here, so provider selection and the
Bedrock reliability tuning live in exactly one place.

Provider chain, in order:
  - ANTHROPIC_API_KEY set   → ChatAnthropic (local dev)
  - BEDROCK id + AWS_REGION → ChatBedrockConverse (production)
  - MISTRAL_API_KEY set     → ChatMistralAI (fallback & opt-in for eval)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger("app.agents.model_factory")


class ModelConfigurationError(RuntimeError):
    """Raised when no configured LLM provider (Anthropic, Bedrock, or Mistral) resolves."""


def build_model(model: str | None = None, *, max_tokens: int | None = None,
                 provider: str | None = None,
                 disable_thinking: bool = False) -> "BaseChatModel":
    """Return a configured chat model for an agent graph.

    ``model`` overrides the provider default (the user's per-run selection).
    ``max_tokens`` defaults to settings.MAX_OUTPUT_TOKENS — no per-agent cap.
    ``disable_thinking`` forces thinking OFF regardless of THINKING_BUDGET_TOKENS.
    Use this for lightweight one-shot classifier calls where thinking is
    unnecessary and the tiny max_tokens budget would be below the thinking floor.
    On adaptive models (sonnet-5, opus-5) this passes {"type": "disabled"}
    explicitly — omitting the field is not enough since those models enable
    adaptive thinking by default.
    """
    if max_tokens is None:
        max_tokens = settings.MAX_OUTPUT_TOKENS

    if provider == "mistral":
        if not settings.MISTRAL_API_KEY:
            raise ModelConfigurationError(
                "provider='mistral' was requested but MISTRAL_API_KEY is not set."
            )
        from langchain_mistralai import ChatMistralAI

        model_id = model or settings.MISTRAL_MODEL_ID
        logger.debug(
            "build_model: ChatMistralAI (explicit provider) model=%s max_tokens=%d",
            model_id, max_tokens,
        )
        # ChatMistralAI's own default is timeout=120, which cannot deliver a
        # MAX_OUTPUT_TOKENS (32768) generation and silently truncates long ones
        # into an httpx.ReadTimeout mid-stream. Seen on the first
        # mistral-large-latest prototype build: 18176 tokens in, 26 out, then
        # ReadTimeout. LLM_CALL_TIMEOUT_SECONDS is this project's declared
        # budget for one streaming call — the 120 was an unstated default
        # nobody chose, not a policy.
        return ChatMistralAI(
            model=model_id, api_key=settings.MISTRAL_API_KEY,
            timeout=settings.LLM_CALL_TIMEOUT_SECONDS,
        )

    # Extended thinking, default OFF. At 0 neither provider branch adds a thinking
    # field or touches temperature. The budget is clamped below THIS call's
    # max_tokens, not the global ceiling. Claude requires temperature=1 when on.
    # disable_thinking=True forces thinking off regardless of THINKING_BUDGET_TOKENS.
    thinking_enabled = settings.THINKING_BUDGET_TOKENS > 0 and not disable_thinking
    budget = 0
    if thinking_enabled:
        budget = max(1024, min(settings.THINKING_BUDGET_TOKENS, max_tokens - 1))

    # Models that require thinking.type="adaptive" instead of "enabled".
    # claude-sonnet-5 (and newer) reject "enabled" on Bedrock with a
    # ValidationException; haiku-4-5 and earlier use "enabled" as before.
    _ADAPTIVE_THINKING_MODEL_FRAGMENTS = ("sonnet-5", "opus-5", "fable-5", "mythos-5")

    def _thinking_type(mid: str) -> str:
        return "adaptive" if any(f in mid for f in _ADAPTIVE_THINKING_MODEL_FRAGMENTS) else "enabled"

    if settings.ANTHROPIC_API_KEY:
        from langchain_anthropic import ChatAnthropic

        model_id = model or settings.ANTHROPIC_MODEL_ID or "claude-haiku-4-5-20251001"
        logger.debug("build_model: ChatAnthropic model=%s max_tokens=%d", model_id, max_tokens)
        anthropic_kwargs: dict = dict(
            model=model_id,
            api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=max_tokens,
        )
        if thinking_enabled:
            anthropic_kwargs["thinking"] = {"type": _thinking_type(model_id), "budget_tokens": budget}
            anthropic_kwargs["temperature"] = 1  # required when thinking is on
        elif disable_thinking and any(f in model_id for f in _ADAPTIVE_THINKING_MODEL_FRAGMENTS):
            anthropic_kwargs["thinking"] = {"type": "disabled"}
        return ChatAnthropic(**anthropic_kwargs)

    import os

    from botocore.config import Config
    from langchain_aws import ChatBedrockConverse

    # botocore reads the bearer token from the PROCESS ENV, and pydantic loads .env
    # into settings without exporting it. Without this bridge a native run would
    # silently fall back to SigV4 ambient credentials instead of the token.
    if settings.AWS_BEARER_TOKEN_BEDROCK and not os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = settings.AWS_BEARER_TOKEN_BEDROCK

    # Settings alone, deliberately NOT the ``model`` override — otherwise a
    # Mistral-only environment would read as Bedrock config and skip the fallback.
    bedrock_configured = bool(
        (settings.BEDROCK_INFERENCE_PROFILE_ID or settings.BEDROCK_MODEL_ID) and settings.AWS_REGION
    )
    if not bedrock_configured:
        if settings.MISTRAL_API_KEY:
            from langchain_mistralai import ChatMistralAI

            mistral_model_id = model or settings.MISTRAL_MODEL_ID
            logger.debug(
                "build_model: ChatMistralAI (fallback) model=%s max_tokens=%d",
                mistral_model_id, max_tokens,
            )
            # Same 120s-default problem as the explicit-provider branch above.
            return ChatMistralAI(
                model=mistral_model_id, api_key=settings.MISTRAL_API_KEY,
                timeout=settings.LLM_CALL_TIMEOUT_SECONDS,
            )
        raise ModelConfigurationError(
            "No LLM configured. Set ANTHROPIC_API_KEY for local dev, "
            "BEDROCK_INFERENCE_PROFILE_ID + AWS_REGION for production, "
            "or MISTRAL_API_KEY for a free-tier fallback."
        )
    model_id = model or settings.BEDROCK_INFERENCE_PROFILE_ID or settings.BEDROCK_MODEL_ID
    region = settings.AWS_REGION
    logger.debug(
        "build_model: ChatBedrockConverse model=%s region=%s max_tokens=%d",
        model_id, region, max_tokens,
    )
    # Passed as additional_model_request_fields only when non-empty, so the
    # thinking-disabled path never carries the kwarg at all.
    # Adaptive-mode models (sonnet-5, opus-5, etc.) reject budget_tokens —
    # Bedrock returns ValidationException: thinking.adaptive.budget_tokens:
    # Extra inputs are not permitted. Only the "enabled" type accepts it.
    # When disable_thinking=True on an adaptive model, we must explicitly pass
    # {"type": "disabled"} — omitting the field leaves adaptive thinking ON by
    # default on sonnet-5/opus-5, which would still violate the max_tokens floor.
    extra_fields: dict = {}
    if thinking_enabled:
        t_type = _thinking_type(model_id)
        thinking_field: dict = {"type": t_type}
        if t_type == "enabled":
            thinking_field["budget_tokens"] = budget
        extra_fields["thinking"] = thinking_field
    elif disable_thinking and any(f in model_id for f in _ADAPTIVE_THINKING_MODEL_FRAGMENTS):
        # Adaptive models enable thinking by default — explicitly disable it.
        extra_fields["thinking"] = {"type": "disabled"}
    bedrock_kwargs: dict = dict(
        model=model_id,
        region_name=region,
        max_tokens=max_tokens,
        # read_timeout bounds time-to-first-token on a slow stream; adaptive
        # retries absorb on-demand throttling.
        config=Config(
            read_timeout=600,
            connect_timeout=30,
            retries={"max_attempts": 5, "mode": "adaptive"},
        ),
    )
    if extra_fields:
        bedrock_kwargs["additional_model_request_fields"] = extra_fields
    if thinking_enabled:
        bedrock_kwargs["temperature"] = 1  # required when thinking is on
    return ChatBedrockConverse(**bedrock_kwargs)


def _build_bedrock_bearer_session():
    """Return a boto3 Session for Bedrock bearer-token auth.

    botocore (>= 1.39) uses token auth for ``bedrock-runtime`` clients whenever
    AWS_BEARER_TOKEN_BEDROCK is in the process env, so a plain session suffices.
    The env bridge below is the same one ``build_model`` does.
    """
    import os

    import boto3

    if settings.AWS_BEARER_TOKEN_BEDROCK and not os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = settings.AWS_BEARER_TOKEN_BEDROCK
    return boto3.Session()


def model_identifier(llm) -> str:
    """Best-effort model id off a built chat model (for token-cost reporting).

    ChatBedrockConverse exposes ``.model_id``; ChatAnthropic and ChatMistralAI
    expose ``.model``. ``.model_name`` covers providers that alias it instead.
    """
    return (
        getattr(llm, "model_id", None)
        or getattr(llm, "model", None)
        or getattr(llm, "model_name", None)
        or "unknown"
    )
