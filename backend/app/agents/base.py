"""Base agent class with Anthropic Claude LLM configuration."""

from typing import AsyncGenerator

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings


class AgentConfigurationError(Exception):
    """Raised when the agent is misconfigured (e.g., missing API key)."""

    pass


class BaseAgent:
    """Base class for all LangChain agents.

    Configures the Anthropic Claude LLM and provides streaming/non-streaming
    methods for subclasses to use.
    """

    def __init__(self, system_prompt: str, model: str = "claude-sonnet-4-20250514"):
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
        )

    def _build_messages(
        self, user_message: str, context: dict | None = None
    ) -> list:
        """Build the message list for the LLM call.

        Args:
            user_message: The user's input message.
            context: Optional context dict from prior phases.

        Returns:
            A list of LangChain message objects.
        """
        messages = [SystemMessage(content=self.system_prompt)]

        if context:
            context_str = "\n".join(
                f"{key}: {value}" for key, value in context.items()
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
        """Stream the LLM response token-by-token.

        Args:
            user_message: The user's input message.
            context: Optional context dict from prior phases.

        Yields:
            String chunks of the LLM response.
        """
        messages = self._build_messages(user_message, context)

        async for chunk in self.llm.astream(messages):
            if chunk.content:
                yield chunk.content

    async def run(self, user_message: str, context: dict | None = None) -> str:
        """Run the LLM and return the full response.

        Args:
            user_message: The user's input message.
            context: Optional context dict from prior phases.

        Returns:
            The complete LLM response as a string.
        """
        messages = self._build_messages(user_message, context)
        response = await self.llm.ainvoke(messages)
        return response.content
