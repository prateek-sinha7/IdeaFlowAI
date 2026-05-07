"""Base agent class with Anthropic Claude LLM configuration."""

import logging
from typing import AsyncGenerator

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings

logger = logging.getLogger("app.agents.base")


class AgentConfigurationError(Exception):
    """Raised when the agent is misconfigured (e.g., missing API key)."""

    pass


class BaseAgent:
    """Base class for all LangChain agents.

    Configures the Anthropic Claude LLM and provides streaming/non-streaming
    methods for subclasses to use.
    """

    def __init__(self, system_prompt: str, model: str = "claude-haiku-4-5-20251001"):
        """Initialize the base agent with a system prompt and LLM configuration.

        Args:
            system_prompt: The system prompt defining the agent's role.
            model: The Anthropic model name to use.

        Raises:
            AgentConfigurationError: If ANTHROPIC_API_KEY is missing or empty.
        """
        if not settings.ANTHROPIC_API_KEY:
            raise AgentConfigurationError(
                "ANTHROPIC_API_KEY is not configured. "
                "Set the ANTHROPIC_API_KEY environment variable to use AI agents."
            )

        self.system_prompt = system_prompt
        self.model = model
        self.llm = ChatAnthropic(
            model=self.model,
            anthropic_api_key=settings.ANTHROPIC_API_KEY,
            streaming=True,
            max_tokens=32000,
        )
        logger.debug("Agent initialized with model=%s, prompt_length=%d", model, len(system_prompt))

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
