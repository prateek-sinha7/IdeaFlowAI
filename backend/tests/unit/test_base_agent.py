"""Unit tests for the BaseAgent class."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.agents.base import BaseAgent, AgentConfigurationError


def _bedrock_settings(mock_settings, **overrides):
    """Apply a default 'bedrock OK' settings shape to a mock."""
    mock_settings.BEDROCK_MODEL_ID = overrides.get(
        "BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0"
    )
    mock_settings.BEDROCK_INFERENCE_PROFILE_ID = overrides.get(
        "BEDROCK_INFERENCE_PROFILE_ID",
        "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
    )
    mock_settings.AWS_REGION = overrides.get("AWS_REGION", "eu-central-1")
    return mock_settings


class TestBaseAgentConfiguration:
    """Tests for BaseAgent initialization and configuration."""

    def test_bedrock_provider_default(self):
        """BaseAgent constructs and invokes the inference profile by default.

        Since both BEDROCK_MODEL_ID (foundation) and BEDROCK_INFERENCE_PROFILE_ID
        are set, the profile wins — that's the on-demand-invocation requirement
        on most regions (eu-central-1 in particular).
        """
        with patch("app.agents.base.settings") as mock_settings, \
                patch("langchain_aws.ChatBedrockConverse") as mock_bedrock:
            _bedrock_settings(mock_settings)
            mock_bedrock.return_value = MagicMock()

            agent = BaseAgent(system_prompt="You are helpful.")

            assert agent.system_prompt == "You are helpful."
            assert agent.model == "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
            assert agent.llm is not None
            mock_bedrock.assert_called_once()
            kwargs = mock_bedrock.call_args.kwargs
            assert kwargs["model"] == "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
            assert kwargs["region_name"] == "eu-central-1"
            assert kwargs["max_tokens"] == 32000

    def test_bedrock_accepts_custom_model(self):
        """An explicit model= overrides the Bedrock default."""
        with patch("app.agents.base.settings") as mock_settings, \
                patch("langchain_aws.ChatBedrockConverse") as mock_bedrock:
            _bedrock_settings(mock_settings)
            mock_bedrock.return_value = MagicMock()

            agent = BaseAgent(
                system_prompt="test",
                model="eu.anthropic.claude-3-5-sonnet-20241022-v2:0",
            )

            assert agent.model == "eu.anthropic.claude-3-5-sonnet-20241022-v2:0"
            kwargs = mock_bedrock.call_args.kwargs
            assert kwargs["model"] == "eu.anthropic.claude-3-5-sonnet-20241022-v2:0"

    def test_bedrock_missing_both_ids_raises(self):
        """Empty BOTH BEDROCK_MODEL_ID and BEDROCK_INFERENCE_PROFILE_ID raises.

        Either one alone is enough for the constructor to succeed (profile
        is preferred, model is the fallback). Only when both are empty does
        the boot-time guard fire.
        """
        with patch("app.agents.base.settings") as mock_settings, \
                patch("langchain_aws.ChatBedrockConverse"):
            _bedrock_settings(
                mock_settings,
                BEDROCK_MODEL_ID="",
                BEDROCK_INFERENCE_PROFILE_ID="",
            )
            with pytest.raises(AgentConfigurationError) as exc_info:
                BaseAgent(system_prompt="test")
            assert "BEDROCK_INFERENCE_PROFILE_ID" in str(exc_info.value) \
                or "BEDROCK_MODEL_ID" in str(exc_info.value)

    def test_bedrock_missing_region_raises(self):
        """Bedrock with empty AWS_REGION raises AgentConfigurationError."""
        with patch("app.agents.base.settings") as mock_settings, \
                patch("langchain_aws.ChatBedrockConverse"):
            _bedrock_settings(mock_settings, AWS_REGION="")
            with pytest.raises(AgentConfigurationError) as exc_info:
                BaseAgent(system_prompt="test")
            assert "AWS_REGION" in str(exc_info.value)


class TestBaseAgentMessageBuilding:
    """Tests for BaseAgent message construction."""

    @pytest.fixture
    def agent(self):
        """Create a BaseAgent instance for testing under the Bedrock default."""
        with patch("app.agents.base.settings") as mock_settings, \
                patch("langchain_aws.ChatBedrockConverse") as mock_bedrock:
            _bedrock_settings(mock_settings)
            mock_bedrock.return_value = MagicMock()
            return BaseAgent(system_prompt="You are a test agent.")

    def test_builds_messages_without_context(self, agent):
        """Messages include system prompt and user message when no context."""
        messages = agent._build_messages("Hello")
        assert len(messages) == 2
        assert messages[0].content == "You are a test agent."
        assert messages[1].content == "Hello"

    def test_builds_messages_with_context(self, agent):
        """Messages include system prompt, context, and user message."""
        context = {"phase_0": "discovery done", "output_selection": "ppt,prototype"}
        messages = agent._build_messages("Generate slides", context=context)
        assert len(messages) == 3
        assert messages[0].content == "You are a test agent."
        assert "phase_0: discovery done" in messages[1].content
        assert "output_selection: ppt,prototype" in messages[1].content
        assert messages[2].content == "Generate slides"

    def test_builds_messages_with_empty_context(self, agent):
        """Empty context dict is treated as no context."""
        messages = agent._build_messages("Hello", context={})
        assert len(messages) == 2


class TestBaseAgentStreaming:
    """Tests for BaseAgent streaming and run methods."""

    @pytest.fixture
    def agent(self):
        """Create a BaseAgent instance for testing under the Bedrock default."""
        with patch("app.agents.base.settings") as mock_settings, \
                patch("langchain_aws.ChatBedrockConverse") as mock_bedrock:
            _bedrock_settings(mock_settings)
            mock_bedrock.return_value = MagicMock()
            return BaseAgent(system_prompt="You are a test agent.")

    @pytest.mark.asyncio
    async def test_astream_yields_chunks(self, agent):
        """astream yields string chunks from the LLM."""
        mock_chunk_1 = MagicMock()
        mock_chunk_1.content = "Hello"
        mock_chunk_2 = MagicMock()
        mock_chunk_2.content = " world"

        async def mock_astream(messages):
            yield mock_chunk_1
            yield mock_chunk_2

        with patch.object(agent, "llm") as mock_llm:
            mock_llm.astream = mock_astream
            chunks = []
            async for chunk in agent.astream("Hi"):
                chunks.append(chunk)

        assert chunks == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_astream_skips_empty_chunks(self, agent):
        """astream skips chunks with empty content."""
        mock_chunk_1 = MagicMock()
        mock_chunk_1.content = "Hello"
        mock_chunk_2 = MagicMock()
        mock_chunk_2.content = ""
        mock_chunk_3 = MagicMock()
        mock_chunk_3.content = " world"

        async def mock_astream(messages):
            yield mock_chunk_1
            yield mock_chunk_2
            yield mock_chunk_3

        with patch.object(agent, "llm") as mock_llm:
            mock_llm.astream = mock_astream
            chunks = []
            async for chunk in agent.astream("Hi"):
                chunks.append(chunk)

        assert chunks == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_run_returns_full_response(self, agent):
        """run returns the complete LLM response as a string."""
        mock_response = MagicMock()
        mock_response.content = "Full response text"

        with patch.object(agent, "llm") as mock_llm:
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            result = await agent.run("Generate something")

        assert result == "Full response text"

    @pytest.mark.asyncio
    async def test_astream_handles_bedrock_block_format(self, agent):
        """ChatBedrockConverse yields content as list[dict] block format.

        Regression test for the bug where the WebSocket layer crashed with
        TypeError on the first chunk because chunks weren't strings. Each
        text delta from Bedrock arrives as `[{"type": "text", "text": "..."}]`.
        """
        chunk_1 = MagicMock()
        chunk_1.content = [{"type": "text", "text": "Hello"}]
        chunk_2 = MagicMock()
        chunk_2.content = [{"type": "text", "text": " world"}]

        async def mock_astream(messages):
            yield chunk_1
            yield chunk_2

        with patch.object(agent, "llm") as mock_llm:
            mock_llm.astream = mock_astream
            chunks = []
            async for chunk in agent.astream("Hi"):
                chunks.append(chunk)

        assert chunks == ["Hello", " world"]
        assert all(isinstance(c, str) for c in chunks)

    @pytest.mark.asyncio
    async def test_astream_skips_non_text_blocks(self, agent):
        """Tool-use / reasoning blocks are skipped — only text reaches the WS."""
        chunk = MagicMock()
        chunk.content = [
            {"type": "tool_use", "id": "tu_1", "name": "search", "input": {}},
            {"type": "text", "text": "answer"},
            {"type": "reasoning_content", "reasoning_content": {"text": "internal"}},
        ]

        async def mock_astream(messages):
            yield chunk

        with patch.object(agent, "llm") as mock_llm:
            mock_llm.astream = mock_astream
            chunks = [c async for c in agent.astream("Hi")]

        assert chunks == ["answer"]

    @pytest.mark.asyncio
    async def test_run_handles_bedrock_block_format(self, agent):
        """run() also extracts text from list-of-dict block payloads."""
        mock_response = MagicMock()
        mock_response.content = [
            {"type": "text", "text": "Full "},
            {"type": "text", "text": "response"},
        ]

        with patch.object(agent, "llm") as mock_llm:
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            result = await agent.run("Generate something")

        assert result == "Full response"

    def test_extract_text_branches(self):
        """Direct unit test of _extract_text — covers the four shapes."""
        assert BaseAgent._extract_text("plain string") == "plain string"
        assert BaseAgent._extract_text([{"type": "text", "text": "block"}]) == "block"
        assert BaseAgent._extract_text([
            {"type": "text", "text": "a"},
            {"type": "tool_use", "id": "x", "name": "t", "input": {}},
            {"type": "text", "text": "b"},
        ]) == "ab"
        assert BaseAgent._extract_text(None) == ""
        assert BaseAgent._extract_text(42) == ""

    def test_inference_profile_preferred_over_model_id(self):
        """When BEDROCK_INFERENCE_PROFILE_ID is set, that's what gets passed
        to ChatBedrockConverse — not the foundation BEDROCK_MODEL_ID. Regions
        like eu-central-1 reject on-demand foundation invocation, so the
        profile is the only id that works there."""
        with patch("app.agents.base.settings") as mock_settings, \
                patch("langchain_aws.ChatBedrockConverse") as mock_bedrock:
            mock_settings.BEDROCK_MODEL_ID = "anthropic.claude-haiku-4-5-20251001-v1:0"
            mock_settings.BEDROCK_INFERENCE_PROFILE_ID = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
            mock_settings.AWS_REGION = "eu-central-1"
            BaseAgent(system_prompt="x")

        kwargs = mock_bedrock.call_args.kwargs
        assert kwargs["model"] == "eu.anthropic.claude-haiku-4-5-20251001-v1:0", \
            "Inference profile id must take priority over the foundation model id"

    def test_falls_back_to_model_id_when_no_profile(self):
        """If only BEDROCK_MODEL_ID is set (e.g. an account/region that
        supports on-demand foundation invocation), the foundation id is used."""
        with patch("app.agents.base.settings") as mock_settings, \
                patch("langchain_aws.ChatBedrockConverse") as mock_bedrock:
            mock_settings.BEDROCK_MODEL_ID = "anthropic.claude-haiku-4-5-20251001-v1:0"
            mock_settings.BEDROCK_INFERENCE_PROFILE_ID = ""
            mock_settings.AWS_REGION = "us-east-1"
            BaseAgent(system_prompt="x")

        kwargs = mock_bedrock.call_args.kwargs
        assert kwargs["model"] == "anthropic.claude-haiku-4-5-20251001-v1:0"
