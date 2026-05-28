"""Base agent — auto-selects Anthropic (local dev) or Bedrock (production)."""

import logging
from dataclasses import dataclass
from typing import AsyncGenerator, Union

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings

logger = logging.getLogger("app.agents.base")


# ─── Token usage tracking ─────────────────────────────────────────────────────

@dataclass
class TokenUsage:
    """Token usage for a single agent invocation."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
        )

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }


# Cost rates per 1K tokens (USD) — covers all commonly used Bedrock models.
# If a model_id isn't listed, _DEFAULT_COST is used as a safe fallback.
# Source: https://aws.amazon.com/bedrock/pricing/
_COST_PER_1K: dict[str, dict[str, float]] = {
    # ── Claude Haiku 4.5 ──────────────────────────────────────────────────
    "anthropic.claude-haiku-4-5-20251001-v1:0":         {"input": 0.00025,  "output": 0.00125},
    "eu.anthropic.claude-haiku-4-5-20251001-v1:0":      {"input": 0.00025,  "output": 0.00125},
    "us.anthropic.claude-haiku-4-5-20251001-v1:0":      {"input": 0.00025,  "output": 0.00125},
    "ap.anthropic.claude-haiku-4-5-20251001-v1:0":      {"input": 0.00025,  "output": 0.00125},
    # ── Claude Haiku 3 ────────────────────────────────────────────────────
    "anthropic.claude-3-haiku-20240307-v1:0":           {"input": 0.00025,  "output": 0.00125},
    "eu.anthropic.claude-3-haiku-20240307-v1:0":        {"input": 0.00025,  "output": 0.00125},
    "us.anthropic.claude-3-haiku-20240307-v1:0":        {"input": 0.00025,  "output": 0.00125},
    # ── Claude Sonnet 4.5 ─────────────────────────────────────────────────
    "anthropic.claude-sonnet-4-5-20250929-v1:0":        {"input": 0.003,    "output": 0.015},
    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0":     {"input": 0.003,    "output": 0.015},
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0":     {"input": 0.003,    "output": 0.015},
    # ── Claude Sonnet 3.5 ─────────────────────────────────────────────────
    "anthropic.claude-3-5-sonnet-20241022-v2:0":        {"input": 0.003,    "output": 0.015},
    "eu.anthropic.claude-3-5-sonnet-20241022-v2:0":     {"input": 0.003,    "output": 0.015},
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0":     {"input": 0.003,    "output": 0.015},
    "anthropic.claude-3-5-sonnet-20240620-v1:0":        {"input": 0.003,    "output": 0.015},
    # ── Claude Sonnet 3 ───────────────────────────────────────────────────
    "anthropic.claude-3-sonnet-20240229-v1:0":          {"input": 0.003,    "output": 0.015},
    # ── Claude Opus 4 / 3 ─────────────────────────────────────────────────
    "anthropic.claude-opus-4-5-20251101-v1:0":          {"input": 0.015,    "output": 0.075},
    "eu.anthropic.claude-opus-4-5-20251101-v1:0":       {"input": 0.015,    "output": 0.075},
    "us.anthropic.claude-opus-4-5-20251101-v1:0":       {"input": 0.015,    "output": 0.075},
    "ap.anthropic.claude-opus-4-5-20251101-v1:0":       {"input": 0.015,    "output": 0.075},
    # ── Claude Sonnet 4.6 ─────────────────────────────────────────────────
    "anthropic.claude-sonnet-4-6":                      {"input": 0.003,    "output": 0.015},
    "eu.anthropic.claude-sonnet-4-6":                   {"input": 0.003,    "output": 0.015},
    "us.anthropic.claude-sonnet-4-6":                   {"input": 0.003,    "output": 0.015},
    "ap.anthropic.claude-sonnet-4-6":                   {"input": 0.003,    "output": 0.015},
    # ── Claude Opus 4.6 ───────────────────────────────────────────────────
    "anthropic.claude-opus-4-6-v1":                     {"input": 0.015,    "output": 0.075},
    "eu.anthropic.claude-opus-4-6-v1":                  {"input": 0.015,    "output": 0.075},
    "us.anthropic.claude-opus-4-6-v1":                  {"input": 0.015,    "output": 0.075},
    "ap.anthropic.claude-opus-4-6-v1":                  {"input": 0.015,    "output": 0.075},
    "anthropic.claude-3-opus-20240229-v1:0":            {"input": 0.015,    "output": 0.075},
    # ── Meta Llama 3 ──────────────────────────────────────────────────────
    "meta.llama3-8b-instruct-v1:0":                     {"input": 0.0003,   "output": 0.0006},
    "meta.llama3-70b-instruct-v1:0":                    {"input": 0.00265,  "output": 0.0035},
    "meta.llama3-1-8b-instruct-v1:0":                   {"input": 0.0003,   "output": 0.0006},
    "meta.llama3-1-70b-instruct-v1:0":                  {"input": 0.00265,  "output": 0.0035},
    "meta.llama3-1-405b-instruct-v1:0":                 {"input": 0.00532,  "output": 0.016},
    # ── Mistral ───────────────────────────────────────────────────────────
    "mistral.mistral-7b-instruct-v0:2":                 {"input": 0.00015,  "output": 0.0002},
    "mistral.mixtral-8x7b-instruct-v0:1":               {"input": 0.00045,  "output": 0.0007},
    "mistral.mistral-large-2402-v1:0":                  {"input": 0.004,    "output": 0.012},
    # ── Amazon Titan ──────────────────────────────────────────────────────
    "amazon.titan-text-express-v1":                     {"input": 0.0002,   "output": 0.0006},
    "amazon.titan-text-lite-v1":                        {"input": 0.00015,  "output": 0.0002},
    "amazon.titan-text-premier-v1:0":                   {"input": 0.0005,   "output": 0.0015},
    # ── Cohere ────────────────────────────────────────────────────────────
    "cohere.command-r-v1:0":                            {"input": 0.0005,   "output": 0.0015},
    "cohere.command-r-plus-v1:0":                       {"input": 0.003,    "output": 0.015},
}
# Fallback when model_id isn't in the table — uses Haiku rates (conservative)
_DEFAULT_COST = {"input": 0.00025, "output": 0.00125}


def estimate_cost_usd(usage: TokenUsage, model_id: str) -> float:
    """Estimate cost in USD for a given token usage and model."""
    rates = _COST_PER_1K.get(model_id, _DEFAULT_COST)
    return (
        (usage.input_tokens / 1000) * rates["input"]
        + (usage.output_tokens / 1000) * rates["output"]
    )


# ─── Agent configuration error ────────────────────────────────────────────────

class AgentConfigurationError(Exception):
    """Raised when the LLM client is misconfigured."""
    pass


# ─── Base agent ───────────────────────────────────────────────────────────────

class BaseAgent:
    """Base class for all LangChain agents.

    Auto-selects provider:
    - ANTHROPIC_API_KEY set → langchain-anthropic (local dev)
    - Otherwise            → langchain-aws ChatBedrockConverse (production)
    """

    def __init__(
        self,
        system_prompt: str,
        max_tokens: int = 32000,
        model: str | None = None,
    ):
        self.model_id = self._resolve_model_id(model)
        self.llm = self._make_client(self.model_id, max_tokens)
        self.model = self.model_id  # backward-compat alias
        self.system_prompt = system_prompt
        logger.debug("Agent initialized provider=%s max_tokens=%d",
                     "anthropic" if settings.ANTHROPIC_API_KEY else "bedrock", max_tokens)

    @staticmethod
    def _resolve_model_id(model: str | None) -> str:
        if model:
            return model
        if settings.ANTHROPIC_API_KEY:
            return settings.ANTHROPIC_MODEL_ID or "claude-haiku-4-5-20251001"
        return settings.BEDROCK_INFERENCE_PROFILE_ID or settings.BEDROCK_MODEL_ID or ""

    @staticmethod
    def _make_client(model_id: str, max_tokens: int):
        if settings.ANTHROPIC_API_KEY:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=model_id, api_key=settings.ANTHROPIC_API_KEY, max_tokens=max_tokens)

        from langchain_aws import ChatBedrockConverse  # noqa: WPS433
        if not model_id or not settings.AWS_REGION:
            raise AgentConfigurationError(
                "No LLM configured. Set ANTHROPIC_API_KEY for local dev or "
                "BEDROCK_INFERENCE_PROFILE_ID + AWS_REGION for production."
            )
        return ChatBedrockConverse(model=model_id, region_name=settings.AWS_REGION, max_tokens=max_tokens)

    @staticmethod
    def _extract_text(content) -> str:
        """Pull text out of an AIMessage(Chunk).content payload."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        return ""

    def _build_messages(
        self, user_message: str, context: dict | None = None
    ) -> list:
        """Build the message list for the LLM call."""
        system_prompt = self.system_prompt
        if context and context.get("mode_prompt"):
            system_prompt = context["mode_prompt"] + "\n\n" + system_prompt

        messages = [SystemMessage(content=system_prompt)]

        if context:
            filtered_context = {
                k: v for k, v in context.items()
                if k not in ("mode", "mode_prompt")
            }
            if filtered_context:
                context_str = "\n".join(
                    f"{key}: {value}" for key, value in filtered_context.items()
                )
                messages.append(
                    HumanMessage(
                        content=f"Here is the context from previous phases:\n{context_str}"
                    )
                )

        messages.append(HumanMessage(content=user_message))
        return messages

    async def astream(
        self, user_message: str, context: dict | None = None
    ) -> AsyncGenerator[str, None]:
        """Stream the LLM response token-by-token."""
        messages = self._build_messages(user_message, context)
        logger.debug("Streaming LLM call — messages=%d, user_msg_length=%d",
                     len(messages), len(user_message))
        chunk_count = 0
        async for chunk in self.llm.astream(messages):
            text = self._extract_text(chunk.content)
            if text:
                chunk_count += 1
                yield text
        logger.debug("Stream complete — %d chunks received", chunk_count)

    async def astream_with_usage(
        self, user_message: str, context: dict | None = None
    ) -> AsyncGenerator[Union[str, TokenUsage], None]:
        """Stream text chunks, then yield a final TokenUsage object.

        ChatBedrockConverse populates ``usage_metadata`` on the last chunk
        with input_tokens / output_tokens — works for any Bedrock model.
        """
        messages = self._build_messages(user_message, context)
        last_chunk = None
        async for chunk in self.llm.astream(messages):
            text = self._extract_text(chunk.content)
            if text:
                yield text
            last_chunk = chunk

        usage = TokenUsage()
        if last_chunk is not None:
            meta = getattr(last_chunk, "usage_metadata", None)
            if meta:
                usage = TokenUsage(
                    input_tokens=meta.get("input_tokens", 0),
                    output_tokens=meta.get("output_tokens", 0),
                    total_tokens=meta.get("total_tokens", 0),
                    cache_read_tokens=meta.get("cache_read_input_tokens", 0),
                    cache_write_tokens=meta.get("cache_creation_input_tokens", 0),
                )
                if usage.total_tokens == 0:
                    usage.total_tokens = usage.input_tokens + usage.output_tokens
        yield usage

    async def run(self, user_message: str, context: dict | None = None) -> str:
        """Run the LLM and return the full response."""
        messages = self._build_messages(user_message, context)
        logger.debug("Invoking LLM — messages=%d", len(messages))
        response = await self.llm.ainvoke(messages)
        text = self._extract_text(response.content)
        logger.debug("Response received — length=%d", len(text))
        return text
