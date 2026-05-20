"""Unit tests for agents/registry.py — pipeline ordering and get_pipeline_agents.

Tests cover:
  - list_agent_ids returns IDs in strictly ascending order with no duplicates
  - get_pipeline_agents returns AgentSpec objects sorted by ascending order
  - get_pipeline_agents with unsupported pipeline type returns []

Requirements: 9.3
"""

from __future__ import annotations

import pytest

from agents.loader import list_agent_ids, load_agent_spec, SUPPORTED_PIPELINE_TYPES
from agents.registry import get_pipeline_agents


# ---------------------------------------------------------------------------
# Task 19.4 — Pipeline ordering tests
# ---------------------------------------------------------------------------


class TestPipelineOrdering:
    """Verify list_agent_ids returns strictly ascending order with no duplicates.

    Uses the REAL filesystem (agents/prompts/).
    Requirements: 9.3
    """

    def test_list_agent_ids_strictly_ascending_for_all_pipelines(self):
        """For every pipeline type, list_agent_ids must return IDs in strictly ascending order."""
        for pipeline_type in sorted(SUPPORTED_PIPELINE_TYPES):
            ids = list_agent_ids(pipeline_type)
            if not ids:
                continue  # empty pipelines are fine (e.g. reverse_engineer)

            # Resolve each ID to its order value
            orders = [load_agent_spec(agent_id).order for agent_id in ids]

            for i in range(1, len(orders)):
                assert orders[i] > orders[i - 1], (
                    f"Pipeline {pipeline_type!r}: order is not strictly ascending at position {i}. "
                    f"Got orders={orders}, ids={ids}"
                )

    def test_list_agent_ids_no_duplicate_orders_for_all_pipelines(self):
        """For every pipeline type, no two agents may share the same order value."""
        for pipeline_type in sorted(SUPPORTED_PIPELINE_TYPES):
            ids = list_agent_ids(pipeline_type)
            if not ids:
                continue

            orders = [load_agent_spec(agent_id).order for agent_id in ids]
            assert len(orders) == len(set(orders)), (
                f"Pipeline {pipeline_type!r}: duplicate order values found. "
                f"orders={orders}, ids={ids}"
            )

    def test_list_agent_ids_returns_list_of_strings(self):
        """list_agent_ids must return a list of strings for every pipeline type."""
        for pipeline_type in sorted(SUPPORTED_PIPELINE_TYPES):
            ids = list_agent_ids(pipeline_type)
            assert isinstance(ids, list), (
                f"Pipeline {pipeline_type!r}: expected list, got {type(ids).__name__}"
            )
            for agent_id in ids:
                assert isinstance(agent_id, str), (
                    f"Pipeline {pipeline_type!r}: agent ID {agent_id!r} is not a string"
                )


class TestGetPipelineAgents:
    """Verify get_pipeline_agents returns AgentSpec objects sorted by ascending order.

    Requirements: 9.3, 5.6, 5.7
    """

    def test_get_pipeline_agents_returns_agent_specs_sorted_by_order(self):
        """get_pipeline_agents must return AgentSpec objects sorted by ascending order."""
        from agents.loader import AgentSpec

        for pipeline_type in sorted(SUPPORTED_PIPELINE_TYPES):
            specs = get_pipeline_agents(pipeline_type)
            if not specs:
                continue

            # All items must be AgentSpec instances
            for spec in specs:
                assert isinstance(spec, AgentSpec), (
                    f"Pipeline {pipeline_type!r}: expected AgentSpec, got {type(spec).__name__}"
                )

            # Orders must be strictly ascending
            orders = [spec.order for spec in specs]
            for i in range(1, len(orders)):
                assert orders[i] > orders[i - 1], (
                    f"Pipeline {pipeline_type!r}: get_pipeline_agents not sorted by order. "
                    f"Got orders={orders}"
                )

    def test_get_pipeline_agents_unsupported_type_returns_empty_list(self):
        """Requirement 5.7: get_pipeline_agents with unsupported type returns []."""
        result = get_pipeline_agents("not_a_real_pipeline_type")
        assert result == [], (
            f"Expected [] for unsupported pipeline type, got {result!r}"
        )

    def test_get_pipeline_agents_empty_string_returns_empty_list(self):
        """get_pipeline_agents with empty string returns []."""
        result = get_pipeline_agents("")
        assert result == []

    def test_get_pipeline_agents_order_matches_list_agent_ids_order(self):
        """get_pipeline_agents order must match list_agent_ids order for every pipeline."""
        for pipeline_type in sorted(SUPPORTED_PIPELINE_TYPES):
            ids_from_list = list_agent_ids(pipeline_type)
            specs_from_get = get_pipeline_agents(pipeline_type)

            ids_from_get = [spec.id for spec in specs_from_get]
            assert ids_from_list == ids_from_get, (
                f"Pipeline {pipeline_type!r}: order mismatch between "
                f"list_agent_ids={ids_from_list} and get_pipeline_agents={ids_from_get}"
            )
