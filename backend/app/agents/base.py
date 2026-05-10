"""Base agent class. Wraps AWS Bedrock via langchain-aws ChatBedrockConverse."""

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
        """Initialize the base agent with a system prompt and LLM configuration.

        Args:
            system_prompt: The system prompt defining the agent's role.
            max_tokens: Maximum output tokens for this agent.
            model: Optional explicit model identifier. If ``None``, the
                default from ``settings.BEDROCK_MODEL_ID`` is used.

        Raises:
            AgentConfigurationError: If ``BEDROCK_MODEL_ID`` or ``AWS_REGION``
                is missing.
        """
        self.llm = self._make_bedrock_client(model, max_tokens)
        # Mirror the resolution chain inside _make_bedrock_client so
        # agent.model is what actually went to Bedrock — not the foundation
        # id when the inference profile is what was invoked.
        self.model = (
            model
            or settings.BEDROCK_INFERENCE_PROFILE_ID
            or settings.BEDROCK_MODEL_ID
        )

        self.system_prompt = system_prompt
        logger.debug(
            "Agent initialized model=%s max_tokens=%d prompt_len=%d",
            self.model,
            max_tokens,
            len(system_prompt),
        )

    @staticmethod
    def _make_bedrock_client(model: str | None, max_tokens: int):
        """Build a ChatBedrockConverse client. Lazy-import keeps dev installs lean.

        Resolution order for the model identifier passed to Bedrock's
        Converse API:

        1. The explicit ``model=`` arg, if provided by the subclass.
        2. ``settings.BEDROCK_INFERENCE_PROFILE_ID`` — the cross-region
           inference profile id, e.g. ``eu.anthropic.claude-haiku-4-5-…``.
        3. ``settings.BEDROCK_MODEL_ID`` — the foundation-model id, e.g.
           ``anthropic.claude-haiku-4-5-…``.

        The inference profile is preferred because most regions (eu-central-1
        included) reject *on-demand* invocations of the foundation-model id
        directly with ``ValidationException: Invocation of model ID … with
        on-demand throughput isn't supported. Retry your request with the ID
        or ARN of an inference profile that contains this model.``
        Falling back to ``BEDROCK_MODEL_ID`` keeps regions/accounts that DO
        support on-demand foundation invocation working without any extra
        config.
        """
        from langchain_aws import ChatBedrockConverse  # noqa: WPS433 — lazy import

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
        """Pull text out of an AIMessage(Chunk).content payload.

        ``ChatBedrockConverse`` (langchain-aws 0.2.x) ALWAYS returns ``content``
        as a ``list[dict]`` of typed blocks — even for plain text streaming
        responses, where each text delta arrives as
        ``[{"type": "text", "text": "..."}]``. Other providers/wrappers may
        return a bare ``str``. We accept either; non-text blocks (tool_use,
        reasoning, image, …) are ignored at this layer because the WS payload
        downstream string-concatenates the result.

        Returning "" for unknown shapes is deliberate — yielding raw blocks
        upstream would break ``current_agent_output_live["output"] += chunk``
        in ``app.api.websocket`` with a ``TypeError: can only concatenate str
        (not "list") to str``.
        """
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
        logger.debug("Streaming LLM call — messages=%d, user_msg_length=%d", len(messages), len(user_message))

        chunk_count = 0
        async for chunk in self.llm.astream(messages):
            text = self._extract_text(chunk.content)
            if text:
                chunk_count += 1
                yield text

        logger.debug("Stream complete — %d chunks received", chunk_count)

    async def run(self, user_message: str, context: dict | None = None) -> str:
        """Run the LLM and return the full response."""
        messages = self._build_messages(user_message, context)
        logger.debug("Invoking LLM — messages=%d", len(messages))
        response = await self.llm.ainvoke(messages)
        text = self._extract_text(response.content)
        logger.debug("Response received — length=%d", len(text))
        return text
