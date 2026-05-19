"""Base agent class. Wraps AWS Bedrock via langchain-aws ChatBedrockConverse."""

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


# Cost rates per 1K tokens (USD) — Bedrock Haiku / Sonnet inference profiles
_COST_PER_1K: dict[str, dict[str, float]] = {
    "anthropic.claude-haiku-4-5-20251001-v1:0":    {"input": 0.00025, "output": 0.00125},
    "eu.anthropic.claude-haiku-4-5-20251001-v1:0": {"input": 0.00025, "output": 0.00125},
    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0": {"input": 0.003,   "output": 0.015},
}
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

    Constructs a ``langchain_aws.ChatBedrockConverse`` client. Auth comes from
    the boto3 default credential chain (instance profile in prod,
    ``~/.aws/credentials`` / ``AWS_PROFILE`` locally). No API key.

    Subclasses inherit ``astream``/``run`` and may pass ``model=`` to override
    the default Bedrock model/inference-profile id.
    """

    def __init__(
        self,
        system_prompt: str,
        max_tokens: int = 32000,
        model: str | None = None,
    ):
        self.llm = self._make_bedrock_client(model, max_tokens)
        # model_id is the actual identifier sent to Bedrock — used for cost
        # estimation in orchestrator_v2.py.
        self.model_id = (
            model
            or settings.BEDROCK_INFERENCE_PROFILE_ID
            or settings.BEDROCK_MODEL_ID
        )
        # Keep self.model as an alias for backward compatibility.
        self.model = self.model_id
        self.system_prompt = system_prompt
        logger.debug(
            "Agent initialized model=%s max_tokens=%d prompt_len=%d",
            self.model_id,
            max_tokens,
            len(system_prompt),
        )

    @staticmethod
    def _make_bedrock_client(model: str | None, max_tokens: int):
        """Build a ChatBedrockConverse client.

        Resolution order:
        1. Explicit ``model=`` arg from the subclass.
        2. ``settings.BEDROCK_INFERENCE_PROFILE_ID`` — cross-region profile.
        3. ``settings.BEDROCK_MODEL_ID`` — foundation-model id.
        """
        from langchain_aws import ChatBedrockConverse  # noqa: WPS433

        model_id = (
            model
            or settings.BEDROCK_INFERENCE_PROFILE_ID
            or settings.BEDROCK_MODEL_ID
        )
        region = settings.AWS_REGION
        if not model_id or not region:
            raise AgentConfigurationError(
                "Bedrock provider requires BEDROCK_INFERENCE_PROFILE_ID (preferred) "
                "or BEDROCK_MODEL_ID, plus AWS_REGION, to be set."
            )
        return ChatBedrockConverse(
            model=model_id,
            region_name=region,
            max_tokens=max_tokens,
        )

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
        with input_tokens / output_tokens — we capture it and yield a
        TokenUsage so orchestrator_v2 can track costs without extra calls.
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
