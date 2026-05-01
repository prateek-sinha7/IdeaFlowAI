"""Unit tests for the BaseAgent class."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.agents.base import BaseAgent, AgentConfigurationError


class TestBaseAgentConfiguration:
    """Tests for BaseAgent initialization and configuration."""

    def test_raises_error_when_api_key_missing(self):
        """BaseAgent raises AgentConfigurationError when ANTHROPIC_API_KEY is empty."""
        with patch("app.agents.base.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = ""
            with pytest.raises(AgentConfigurationError) as exc_info:
                BaseAgent(system_prompt="test")
            assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    def test_raises_error_when_api_key_none(self):
        """BaseAgent raises AgentConfigurationError when ANTHROPIC_API_KEY is None."""
        with patch("app.agents.base.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = None
            with pytest.raises(AgentConfigurationError) as exc_info:
                BaseAgent(system_prompt="test")
            assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    def test_creates_agent_with_valid_key(self):
        """BaseAgent initializes successfully with a valid API key."""
        with patch("app.agents.base.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"
            agent = BaseAgent(system_prompt="You are helpful.")
            assert agent.system_prompt == "You are helpful."
            assert agent.model == "claude-sonnet-4-20250514"
            assert agent.llm is not None

    def test_accepts_custom_model(self):
        """BaseAgent accepts a custom model name."""
        with patch("app.agents.base.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"
            agent = BaseAgent(
                system_prompt="test", model="claude-3-haiku-20240307"
            )
            assert agent.model == "claude-3-haiku-20240307"


class TestBaseAgentMessageBuilding:
    """Tests for BaseAgent message construction."""

    @pytest.fixture
    def agent(self):
        """Create a BaseAgent instance for testing."""
        with patch("app.agents.base.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"
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
        """Create a BaseAgent instance for testing."""
        with patch("app.agents.base.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"
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
