"""Unit tests for the BaseAgent class."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.agents.base import BaseAgent, AgentConfigurationError


def _bedrock_settings(mock_settings, **overrides):
    """Apply a default 'bedrock provider OK' settings shape to a mock."""
    mock_settings.LLM_PROVIDER = overrides.get("LLM_PROVIDER", "bedrock")
    mock_settings.BEDROCK_MODEL_ID = overrides.get(
        "BEDROCK_MODEL_ID", "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
    )
    mock_settings.AWS_REGION = overrides.get("AWS_REGION", "eu-west-2")
    mock_settings.ANTHROPIC_API_KEY = overrides.get("ANTHROPIC_API_KEY", "")
    mock_settings.ANTHROPIC_MODEL = overrides.get(
        "ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"
    )
    return mock_settings


def _anthropic_settings(mock_settings, **overrides):
    """Apply a default 'anthropic provider OK' settings shape to a mock."""
    mock_settings.LLM_PROVIDER = overrides.get("LLM_PROVIDER", "anthropic")
    mock_settings.BEDROCK_MODEL_ID = overrides.get("BEDROCK_MODEL_ID", "")
    mock_settings.AWS_REGION = overrides.get("AWS_REGION", "")
    mock_settings.ANTHROPIC_API_KEY = overrides.get(
        "ANTHROPIC_API_KEY", "sk-ant-test-key"
    )
    mock_settings.ANTHROPIC_MODEL = overrides.get(
        "ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"
    )
    return mock_settings


class TestBaseAgentConfiguration:
    """Tests for BaseAgent initialization and configuration."""

    def test_bedrock_provider_default(self):
        """BaseAgent constructs successfully under the default Bedrock provider."""
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
            assert kwargs["region_name"] == "eu-west-2"
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

    def test_bedrock_missing_model_id_raises(self):
        """Bedrock with empty BEDROCK_MODEL_ID raises AgentConfigurationError."""
        with patch("app.agents.base.settings") as mock_settings, \
                patch("langchain_aws.ChatBedrockConverse"):
            _bedrock_settings(mock_settings, BEDROCK_MODEL_ID="")
            with pytest.raises(AgentConfigurationError) as exc_info:
                BaseAgent(system_prompt="test")
            assert "BEDROCK_MODEL_ID" in str(exc_info.value)

    def test_bedrock_missing_region_raises(self):
        """Bedrock with empty AWS_REGION raises AgentConfigurationError."""
        with patch("app.agents.base.settings") as mock_settings, \
                patch("langchain_aws.ChatBedrockConverse"):
            _bedrock_settings(mock_settings, AWS_REGION="")
            with pytest.raises(AgentConfigurationError) as exc_info:
                BaseAgent(system_prompt="test")
            assert "AWS_REGION" in str(exc_info.value)

    def test_anthropic_provider_with_key(self):
        """BaseAgent constructs successfully under the Anthropic fallback."""
        with patch("app.agents.base.settings") as mock_settings, \
                patch("langchain_anthropic.ChatAnthropic") as mock_anthropic:
            _anthropic_settings(mock_settings)
            mock_anthropic.return_value = MagicMock()

            agent = BaseAgent(system_prompt="You are helpful.")

            assert agent.system_prompt == "You are helpful."
            assert agent.model == "claude-haiku-4-5-20251001"
            assert agent.llm is not None
            mock_anthropic.assert_called_once()
            kwargs = mock_anthropic.call_args.kwargs
            assert kwargs["model"] == "claude-haiku-4-5-20251001"
            assert kwargs["anthropic_api_key"] == "sk-ant-test-key"
            assert kwargs["streaming"] is True

    def test_anthropic_accepts_custom_model(self):
        """An explicit model= overrides the Anthropic default."""
        with patch("app.agents.base.settings") as mock_settings, \
                patch("langchain_anthropic.ChatAnthropic") as mock_anthropic:
            _anthropic_settings(mock_settings)
            mock_anthropic.return_value = MagicMock()

            agent = BaseAgent(
                system_prompt="test", model="claude-3-haiku-20240307"
            )

            assert agent.model == "claude-3-haiku-20240307"

    def test_anthropic_missing_key_raises(self):
        """Anthropic provider with empty ANTHROPIC_API_KEY raises."""
        with patch("app.agents.base.settings") as mock_settings, \
                patch("langchain_anthropic.ChatAnthropic"):
            _anthropic_settings(mock_settings, ANTHROPIC_API_KEY="")
            with pytest.raises(AgentConfigurationError) as exc_info:
                BaseAgent(system_prompt="test")
            assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    def test_unknown_provider_raises(self):
        """An unrecognised LLM_PROVIDER raises AgentConfigurationError."""
        with patch("app.agents.base.settings") as mock_settings:
            _bedrock_settings(mock_settings, LLM_PROVIDER="foo")
            with pytest.raises(AgentConfigurationError) as exc_info:
                BaseAgent(system_prompt="test")
            assert "LLM_PROVIDER" in str(exc_info.value)


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
