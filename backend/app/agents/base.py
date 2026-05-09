"""Base agent class. Provider is selectable: AWS Bedrock (default) or direct Anthropic API."""

import logging
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings

logger = logging.getLogger("app.agents.base")


class AgentConfigurationError(Exception):
    """Raised when the LLM client is misconfigured."""

    pass


class BaseAgent:
    """Base class for all LangChain agents.

    Constructs an LLM client based on ``settings.LLM_PROVIDER``:

    * ``"bedrock"`` (default) — ``langchain_aws.ChatBedrockConverse``. Auth via
      the boto3 default credential chain (no API key passed).
    * ``"anthropic"`` — ``langchain_anthropic.ChatAnthropic``. Emergency-
      continuity fallback; requires ``ANTHROPIC_API_KEY``.

    Subclasses inherit ``astream``/``run`` and may pass ``model=`` to override
    the provider-default model name.
    """

    def __init__(
        self,
        system_prompt: str,
        max_tokens: int = 32000,
        model: str | None = None,
    ):
        """Initialize the base agent with a system prompt and LLM configuration.

        Args:
            system_prompt: The system prompt defining the agent's role.
            max_tokens: Maximum output tokens for this agent.
            model: Optional explicit model identifier. If ``None``, the
                provider-appropriate default from settings is used.

        Raises:
            AgentConfigurationError: If the configured provider is unknown or
                its required settings are missing.
        """
        provider = (settings.LLM_PROVIDER or "bedrock").lower()
        if provider == "bedrock":
            self.llm = self._make_bedrock_client(model, max_tokens)
            self.model = model or settings.BEDROCK_MODEL_ID
        elif provider == "anthropic":
            self.llm = self._make_anthropic_client(model, max_tokens)
            self.model = (
                model
                or settings.ANTHROPIC_MODEL
                or "claude-haiku-4-5-20251001"
            )
        else:
            raise AgentConfigurationError(
                f"LLM_PROVIDER must be 'bedrock' or 'anthropic'; "
                f"got {settings.LLM_PROVIDER!r}"
            )

        self.system_prompt = system_prompt
        logger.debug(
            "Agent initialized provider=%s model=%s max_tokens=%d prompt_len=%d",
            provider,
            self.model,
            max_tokens,
            len(system_prompt),
        )

    @staticmethod
    def _make_bedrock_client(model: str | None, max_tokens: int):
        """Build a ChatBedrockConverse client. Lazy-import keeps dev installs lean."""
        from langchain_aws import ChatBedrockConverse  # noqa: WPS433 — lazy import

        model_id = model or settings.BEDROCK_MODEL_ID
        region = settings.AWS_REGION
        if not model_id or not region:
            raise AgentConfigurationError(
                "Bedrock provider requires BEDROCK_MODEL_ID and AWS_REGION to be set."
            )
        return ChatBedrockConverse(
            model=model_id,
            region_name=region,
            max_tokens=max_tokens,
        )

    @staticmethod
    def _make_anthropic_client(model: str | None, max_tokens: int):
        """Build a ChatAnthropic client (fallback path)."""
        from langchain_anthropic import ChatAnthropic  # noqa: WPS433 — lazy import

        if not settings.ANTHROPIC_API_KEY:
            raise AgentConfigurationError(
                "Anthropic provider requires ANTHROPIC_API_KEY to be set."
            )
        return ChatAnthropic(
            model=model or settings.ANTHROPIC_MODEL or "claude-haiku-4-5-20251001",
            anthropic_api_key=settings.ANTHROPIC_API_KEY,
            streaming=True,
            max_tokens=max_tokens,
        )

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
        logger.debug("Streaming LLM call — messages=%d, user_msg_length=%d", len(messages), len(user_message))

        chunk_count = 0
        async for chunk in self.llm.astream(messages):
            if chunk.content:
                chunk_count += 1
                yield chunk.content

        logger.debug("Stream complete — %d chunks received", chunk_count)

    async def run(self, user_message: str, context: dict | None = None) -> str:
        """Run the LLM and return the full response."""
        messages = self._build_messages(user_message, context)
        logger.debug("Invoking LLM — messages=%d", len(messages))
        response = await self.llm.ainvoke(messages)
        logger.debug("Response received — length=%d", len(response.content))
        return response.content
