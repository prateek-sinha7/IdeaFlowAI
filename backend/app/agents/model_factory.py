"""app/agents/model_factory.py — single source of truth for building the LLM client.

The deepagents runtime (and any auxiliary one-shot call) builds its chat model
here, so provider selection and the embedded reliability tuning (botocore
timeouts + adaptive retries) live in exactly one place.

Provider selection (unchanged from the legacy runtime):
  - ANTHROPIC_API_KEY set → ChatAnthropic (local dev)
  - otherwise             → ChatBedrockConverse (production, AWS Bedrock)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger("app.agents.model_factory")


class ModelConfigurationError(RuntimeError):
    """Raised when neither the Anthropic nor the Bedrock provider is configured."""


def build_model(model: str | None = None, *, max_tokens: int | None = None) -> "BaseChatModel":
    """Return a configured chat model for an agent graph.

    ``model`` overrides the provider's default model id — the user's per-run model
    selection threads through here. ``max_tokens`` defaults to the global ceiling
    (``settings.MAX_OUTPUT_TOKENS``); we do NOT cap per agent.

    Bedrock clients embed generous botocore timeouts + adaptive retries so a slow
    first token or transient throttling never aborts a long generation — these are
    the "embedded reliability" controls we keep from the custom runtime.
    """
    if max_tokens is None:
        max_tokens = settings.MAX_OUTPUT_TOKENS

    if settings.ANTHROPIC_API_KEY:
        from langchain_anthropic import ChatAnthropic

        model_id = model or settings.ANTHROPIC_MODEL_ID or "claude-haiku-4-5-20251001"
        logger.debug("build_model: ChatAnthropic model=%s max_tokens=%d", model_id, max_tokens)
        return ChatAnthropic(
            model=model_id,
            api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=max_tokens,
        )

    from botocore.config import Config
    from langchain_aws import ChatBedrockConverse

    model_id = model or settings.BEDROCK_INFERENCE_PROFILE_ID or settings.BEDROCK_MODEL_ID
    region = settings.AWS_REGION
    if not model_id or not region:
        raise ModelConfigurationError(
            "No LLM configured. Set ANTHROPIC_API_KEY for local dev or "
            "BEDROCK_INFERENCE_PROFILE_ID + AWS_REGION for production."
        )
    logger.debug(
        "build_model: ChatBedrockConverse model=%s region=%s max_tokens=%d",
        model_id, region, max_tokens,
    )
    return ChatBedrockConverse(
        model=model_id,
        region_name=region,
        max_tokens=max_tokens,
        # read_timeout bounds time-to-first-token on a slow Bedrock stream;
        # adaptive retries absorb on-demand throttling. Mirrors the tuning proven
        # in the legacy runtime, now applied to every deepagents graph's model.
        config=Config(
            read_timeout=600,
            connect_timeout=30,
            retries={"max_attempts": 5, "mode": "adaptive"},
        ),
    )


def model_identifier(llm) -> str:
    """Best-effort model id off a built chat model (for token-cost reporting).

    ChatBedrockConverse exposes ``.model_id``; ChatAnthropic exposes ``.model``.
    """
    return getattr(llm, "model_id", None) or getattr(llm, "model", None) or "unknown"
