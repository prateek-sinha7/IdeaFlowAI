"""End-to-end integration tests for WorkflowOrchestrator — user_stories pipeline.

Tests cover:
  1. Execute user_stories pipeline with mocked LLM:
     - All 6 agents fire in correct order
     - len(WorkflowState.agent_outputs) == 6 after completion
     - pipeline_start event emitted with data.pipeline_type
     - 6 agent_start events emitted (one per agent)
     - 6 agent_complete events emitted (one per agent)
     - pipeline_complete event emitted with data.final_output

  2. If create_agent raises for one agent, an agent_error event is emitted
     and the pipeline halts:
     - Mock create_agent to raise FileNotFoundError for the 3rd agent
     - Assert agent_error event is emitted for that agent
     - Assert pipeline stops (no more agent_complete events after the error)

Requirements: 9.6, 9.7
"""

from __future__ import annotations

from typing import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest

from app.agents.base import BaseAgent, TokenUsage
from app.agents.orchestrator_v2 import WorkflowOrchestrator, WorkflowState

# The orchestrator imports create_agent at the top of orchestrator_v2.py:
#   from agents.factory import AgentContext, create_agent
# We must patch it at the point of use (the orchestrator module), not at the
# definition site (agents.factory), so the orchestrator picks up the mock.
_CREATE_AGENT_PATCH = "app.agents.orchestrator_v2.create_agent"

USER_STORIES_AGENTS = [
    "domain-analyst",
    "epic-architect",
    "story-estimator",
    "nfr-specialist",
    "backlog-reviewer",
    "backlog-compiler",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _mock_astream_with_usage(message: str, context=None) -> AsyncGenerator:
    """Async generator that yields a non-empty string then a TokenUsage."""
    yield "mock output for agent"
    yield TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30)


def _make_mock_agent() -> MagicMock:
    """Build a mock agent whose astream_with_usage yields a non-empty string.

    We use a plain MagicMock (not spec=BaseAgent) so that instance attributes
    like model_id — which are set in __init__, not declared at class level —
    are accessible without AttributeError.

    The user_stories agents all have tools: [], so the orchestrator always
    takes the astream_with_usage path (use_deep is False). No isinstance
    check against DeepAgent is needed.
    """
    mock_agent = MagicMock()
    mock_agent.model_id = "mock-model"
    mock_agent.astream_with_usage = _mock_astream_with_usage
    return mock_agent


def _collect_events(events: list[dict], event_type: str) -> list[dict]:
    """Filter events by type."""
    return [e for e in events if e["type"] == event_type]


# ---------------------------------------------------------------------------
# Test 1 — Happy path: all 6 agents fire in correct order
# ---------------------------------------------------------------------------


class TestUserStoriesPipelineHappyPath:
    """Execute user_stories pipeline with mocked LLM.

    Validates Requirements 9.6:
    - All 6 agents fire in correct order
    - len(WorkflowState.agent_outputs) == 6 after completion
    - pipeline_start event emitted with data.pipeline_type
    - 6 agent_start events emitted (one per agent)
    - 6 agent_complete events emitted (one per agent)
    - pipeline_complete event emitted with data.final_output
    """

    @pytest.mark.asyncio
    async def test_all_6_agents_fire_in_correct_order(self):
        """All 6 user_stories agents must fire in the correct order."""
        mock_agent = _make_mock_agent()

        with patch(_CREATE_AGENT_PATCH, return_value=mock_agent):
            orchestrator = WorkflowOrchestrator(pipeline_type="user_stories")
            events: list[dict] = []
            async for event in orchestrator.execute("Build a user story for a login feature"):
                events.append(event)

        agent_start_events = _collect_events(events, "agent_start")
        agent_ids_fired = [e["data"]["agent_id"] for e in agent_start_events]

        assert agent_ids_fired == USER_STORIES_AGENTS, (
            f"Expected agents in order {USER_STORIES_AGENTS}, got {agent_ids_fired}"
        )

    @pytest.mark.asyncio
    async def test_agent_outputs_has_6_entries_after_completion(self):
        """len(WorkflowState.agent_outputs) == 6 after pipeline completes."""
        mock_agent = _make_mock_agent()
        captured_state: dict = {}

        original_get_final_output = WorkflowOrchestrator._get_final_output

        def _capture_state(self, state: WorkflowState) -> str:
            captured_state["agent_outputs"] = dict(state.agent_outputs)
            return original_get_final_output(self, state)

        with patch(_CREATE_AGENT_PATCH, return_value=mock_agent):
            with patch.object(WorkflowOrchestrator, "_get_final_output", _capture_state):
                orchestrator = WorkflowOrchestrator(pipeline_type="user_stories")
                async for _ in orchestrator.execute("Build a user story for a login feature"):
                    pass

        assert "agent_outputs" in captured_state, "State was never captured"
        assert len(captured_state["agent_outputs"]) == 6, (
            f"Expected 6 agent outputs, got {len(captured_state['agent_outputs'])}: "
            f"{list(captured_state['agent_outputs'].keys())}"
        )

    @pytest.mark.asyncio
    async def test_pipeline_start_event_emitted_with_pipeline_type(self):
        """pipeline_start event must be emitted with data.pipeline_type == 'user_stories'."""
        mock_agent = _make_mock_agent()

        with patch(_CREATE_AGENT_PATCH, return_value=mock_agent):
            orchestrator = WorkflowOrchestrator(pipeline_type="user_stories")
            events: list[dict] = []
            async for event in orchestrator.execute("Build a user story"):
                events.append(event)

        pipeline_start_events = _collect_events(events, "pipeline_start")
        assert len(pipeline_start_events) == 1, (
            f"Expected exactly 1 pipeline_start event, got {len(pipeline_start_events)}"
        )
        assert pipeline_start_events[0]["data"]["pipeline_type"] == "user_stories", (
            f"Expected pipeline_type='user_stories', got "
            f"{pipeline_start_events[0]['data'].get('pipeline_type')!r}"
        )

    @pytest.mark.asyncio
    async def test_6_agent_start_events_emitted(self):
        """Exactly 6 agent_start events must be emitted (one per agent)."""
        mock_agent = _make_mock_agent()

        with patch(_CREATE_AGENT_PATCH, return_value=mock_agent):
            orchestrator = WorkflowOrchestrator(pipeline_type="user_stories")
            events: list[dict] = []
            async for event in orchestrator.execute("Build a user story"):
                events.append(event)

        agent_start_events = _collect_events(events, "agent_start")
        assert len(agent_start_events) == 6, (
            f"Expected 6 agent_start events, got {len(agent_start_events)}"
        )

        # Each event must have agent_id
        for evt in agent_start_events:
            assert "agent_id" in evt["data"], f"agent_start event missing agent_id: {evt}"

    @pytest.mark.asyncio
    async def test_6_agent_complete_events_emitted(self):
        """Exactly 6 agent_complete events must be emitted (one per agent)."""
        mock_agent = _make_mock_agent()

        with patch(_CREATE_AGENT_PATCH, return_value=mock_agent):
            orchestrator = WorkflowOrchestrator(pipeline_type="user_stories")
            events: list[dict] = []
            async for event in orchestrator.execute("Build a user story"):
                events.append(event)

        agent_complete_events = _collect_events(events, "agent_complete")
        assert len(agent_complete_events) == 6, (
            f"Expected 6 agent_complete events, got {len(agent_complete_events)}"
        )

        # Each event must have agent_id
        for evt in agent_complete_events:
            assert "agent_id" in evt["data"], f"agent_complete event missing agent_id: {evt}"

    @pytest.mark.asyncio
    async def test_pipeline_complete_event_emitted_with_final_output(self):
        """pipeline_complete event must be emitted with data.final_output."""
        mock_agent = _make_mock_agent()

        with patch(_CREATE_AGENT_PATCH, return_value=mock_agent):
            orchestrator = WorkflowOrchestrator(pipeline_type="user_stories")
            events: list[dict] = []
            async for event in orchestrator.execute("Build a user story"):
                events.append(event)

        pipeline_complete_events = _collect_events(events, "pipeline_complete")
        assert len(pipeline_complete_events) == 1, (
            f"Expected exactly 1 pipeline_complete event, got {len(pipeline_complete_events)}"
        )
        assert "final_output" in pipeline_complete_events[0]["data"], (
            "pipeline_complete event missing data.final_output"
        )

    @pytest.mark.asyncio
    async def test_agent_complete_events_in_correct_order(self):
        """agent_complete events must be emitted in the same order as USER_STORIES_AGENTS."""
        mock_agent = _make_mock_agent()

        with patch(_CREATE_AGENT_PATCH, return_value=mock_agent):
            orchestrator = WorkflowOrchestrator(pipeline_type="user_stories")
            events: list[dict] = []
            async for event in orchestrator.execute("Build a user story"):
                events.append(event)

        agent_complete_events = _collect_events(events, "agent_complete")
        completed_ids = [e["data"]["agent_id"] for e in agent_complete_events]
        assert completed_ids == USER_STORIES_AGENTS, (
            f"agent_complete events not in expected order. "
            f"Expected {USER_STORIES_AGENTS}, got {completed_ids}"
        )


# ---------------------------------------------------------------------------
# Test 2 — Error path: create_agent raises for 3rd agent → agent_error + halt
# ---------------------------------------------------------------------------


class TestUserStoriesPipelineErrorHalt:
    """If create_agent raises for one agent, agent_error is emitted and pipeline halts.

    Validates Requirement 9.7:
    - Mock create_agent to raise FileNotFoundError for the 3rd agent
    - Assert agent_error event is emitted for that agent
    - Assert pipeline stops (no more agent_complete events after the error)
    """

    @pytest.mark.asyncio
    async def test_agent_error_emitted_when_create_agent_raises(self):
        """agent_error event must be emitted when create_agent raises FileNotFoundError."""
        mock_agent = _make_mock_agent()
        third_agent_id = USER_STORIES_AGENTS[2]  # "story-estimator"

        def _create_agent_side_effect(agent_id, ctx):
            if agent_id == third_agent_id:
                raise FileNotFoundError(
                    f"agents/prompts/{third_agent_id}/AGENT.md not found"
                )
            return mock_agent

        with patch(_CREATE_AGENT_PATCH, side_effect=_create_agent_side_effect):
            orchestrator = WorkflowOrchestrator(pipeline_type="user_stories")
            events: list[dict] = []
            async for event in orchestrator.execute("Build a user story"):
                events.append(event)

        agent_error_events = _collect_events(events, "agent_error")
        assert len(agent_error_events) >= 1, (
            "Expected at least 1 agent_error event when create_agent raises"
        )

        # The error event must be for the 3rd agent
        error_agent_ids = [e["data"]["agent_id"] for e in agent_error_events]
        assert third_agent_id in error_agent_ids, (
            f"Expected agent_error for {third_agent_id!r}, got errors for {error_agent_ids}"
        )

    @pytest.mark.asyncio
    async def test_pipeline_halts_after_create_agent_raises(self):
        """Pipeline must stop after create_agent raises — no agent_complete events after the error."""
        mock_agent = _make_mock_agent()
        third_agent_id = USER_STORIES_AGENTS[2]  # "story-estimator"

        def _create_agent_side_effect(agent_id, ctx):
            if agent_id == third_agent_id:
                raise FileNotFoundError(
                    f"agents/prompts/{third_agent_id}/AGENT.md not found"
                )
            return mock_agent

        with patch(_CREATE_AGENT_PATCH, side_effect=_create_agent_side_effect):
            orchestrator = WorkflowOrchestrator(pipeline_type="user_stories")
            events: list[dict] = []
            async for event in orchestrator.execute("Build a user story"):
                events.append(event)

        agent_complete_events = _collect_events(events, "agent_complete")
        completed_ids = [e["data"]["agent_id"] for e in agent_complete_events]

        # Only the first 2 agents should have completed (before the 3rd raised)
        expected_completed = USER_STORIES_AGENTS[:2]
        assert completed_ids == expected_completed, (
            f"Expected only {expected_completed} to complete before halt, "
            f"but got {completed_ids}"
        )

        # No agents after the 3rd should have completed
        agents_after_error = USER_STORIES_AGENTS[2:]  # 3rd agent and beyond
        for agent_id in agents_after_error:
            assert agent_id not in completed_ids, (
                f"Agent {agent_id!r} completed after the pipeline should have halted"
            )

    @pytest.mark.asyncio
    async def test_pipeline_complete_still_emitted_after_error(self):
        """pipeline_complete event is still emitted even when the pipeline halts early."""
        mock_agent = _make_mock_agent()
        third_agent_id = USER_STORIES_AGENTS[2]

        def _create_agent_side_effect(agent_id, ctx):
            if agent_id == third_agent_id:
                raise FileNotFoundError(
                    f"agents/prompts/{third_agent_id}/AGENT.md not found"
                )
            return mock_agent

        with patch(_CREATE_AGENT_PATCH, side_effect=_create_agent_side_effect):
            orchestrator = WorkflowOrchestrator(pipeline_type="user_stories")
            events: list[dict] = []
            async for event in orchestrator.execute("Build a user story"):
                events.append(event)

        pipeline_complete_events = _collect_events(events, "pipeline_complete")
        assert len(pipeline_complete_events) == 1, (
            f"Expected 1 pipeline_complete event even after error, "
            f"got {len(pipeline_complete_events)}"
        )

    @pytest.mark.asyncio
    async def test_agents_before_error_complete_successfully(self):
        """Agents before the failing one must still emit agent_complete events."""
        mock_agent = _make_mock_agent()
        third_agent_id = USER_STORIES_AGENTS[2]

        def _create_agent_side_effect(agent_id, ctx):
            if agent_id == third_agent_id:
                raise FileNotFoundError(
                    f"agents/prompts/{third_agent_id}/AGENT.md not found"
                )
            return mock_agent

        with patch(_CREATE_AGENT_PATCH, side_effect=_create_agent_side_effect):
            orchestrator = WorkflowOrchestrator(pipeline_type="user_stories")
            events: list[dict] = []
            async for event in orchestrator.execute("Build a user story"):
                events.append(event)

        agent_complete_events = _collect_events(events, "agent_complete")
        completed_ids = [e["data"]["agent_id"] for e in agent_complete_events]

        # First 2 agents should have completed
        for agent_id in USER_STORIES_AGENTS[:2]:
            assert agent_id in completed_ids, (
                f"Agent {agent_id!r} should have completed before the error, "
                f"but was not in completed_ids={completed_ids}"
            )
