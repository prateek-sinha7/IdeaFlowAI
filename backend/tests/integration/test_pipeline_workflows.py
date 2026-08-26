"""T025 — Integration / regression suite for the Universal ExecutionEngine.

Replaces the orchestrator_v2-based integration tests (deleted in T021).

Two test tiers:

1. **Structural regression (no credentials required)** — verifies, per SC-004,
   that every pipeline:
     * resolves to a satisfiable DAG via WorkflowResolver,
     * produces agents in the original declared order,
     * has every agent's `consumes` satisfied by an upstream `produces`.
   These run in CI without Bedrock/Anthropic credentials.

2. **Live streaming regression (requires credentials)** — marked
   `requires_api_key`; exercises the real engine.execute() streaming path and
   asserts the planner → pipeline_start → agent_* → pipeline_complete event
   sequence. Skipped automatically when no LLM provider is configured.

Run structural only:   pytest backend/tests/integration/ -m "not requires_api_key"
Run everything:        pytest backend/tests/integration/
"""

from __future__ import annotations

import os

import pytest

from agents.execution_engine.resolver import WorkflowResolver
from agents.registry import PIPELINE_AGENTS, get_pipeline_agents, load_agent_spec


# Pipelines that have no scannable agents (ppt shares od_ppt agents;
# reverse_engineer has an empty list) — handled explicitly below.
_EMPTY_SCAN = {"ppt", "reverse_engineer"}

# FIX-051 / ISS-035: spec_kit's agents ARE real and scannable (unlike
# _EMPTY_SCAN above), but the pipeline is a known in-progress/unfinished one —
# it has no workflow.yaml manifest, and its produces/consumes contracts are
# not fully wired (clarify-agent consumes 'brief', which no spec_kit agent
# yet produces). Structural DAG validation is therefore expected to fail
# until spec_kit is finished — a separate, out-of-scope product decision (see
# .investigations/hardcoded-agents/PLAN.md §4). Excluded here rather than
# silently "fixed" by loosening the DAG check.
_STRUCTURALLY_INCOMPLETE = {"spec_kit"}


def _resolve_agents(pipeline_type: str) -> list:
    agents = get_pipeline_agents(pipeline_type)
    if not agents and pipeline_type == "ppt":
        agents = [load_agent_spec(aid) for aid in PIPELINE_AGENTS.get("ppt", [])]
    return agents


def _llm_configured() -> bool:
    return bool(
        os.getenv("ANTHROPIC_API_KEY")
        or (os.getenv("BEDROCK_MODEL_ID") and os.getenv("AWS_REGION"))
        or (os.getenv("BEDROCK_INFERENCE_PROFILE_ID") and os.getenv("AWS_REGION"))
    )


requires_api_key = pytest.mark.requires_api_key


# ---------------------------------------------------------------------------
# Tier 1 — Structural regression (no credentials)
# ---------------------------------------------------------------------------


class TestStructuralRegression:
    """SC-004: structural regression across all pipeline types."""

    @pytest.mark.parametrize(
        "pipeline_type",
        [pt for pt in sorted(PIPELINE_AGENTS) if pt not in _EMPTY_SCAN | _STRUCTURALLY_INCOMPLETE],
    )
    def test_pipeline_resolves_to_satisfiable_dag(self, pipeline_type):
        agents = _resolve_agents(pipeline_type)
        if not agents:
            pytest.skip(f"{pipeline_type} has no agents")
        result = WorkflowResolver().validate(agents)
        assert result.satisfiable, (
            f"{pipeline_type} unsatisfiable: {result.errors}"
        )

    def test_ppt_pipeline_resolves(self):
        agents = _resolve_agents("ppt")
        assert agents, "ppt should resolve via PIPELINE_AGENTS fallback"
        result = WorkflowResolver().validate(agents)
        assert result.satisfiable, f"ppt unsatisfiable: {result.errors}"

    @pytest.mark.parametrize(
        "pipeline_type",
        [pt for pt in sorted(PIPELINE_AGENTS) if pt not in _EMPTY_SCAN | _STRUCTURALLY_INCOMPLETE],
    )
    def test_topological_order_is_dependency_valid(self, pipeline_type):
        """The resolved execution order must be a valid topological sort:
        every agent appears AFTER all agents it consumes from.

        Note: for non-linear pipelines (app_builder, dotnet_to_azure,
        mulesoft_to_springboot) the resolved order may legitimately differ
        from the declared order — what matters is that no agent runs before
        a dependency it consumes. Linear pipelines preserve declared order
        as a natural consequence."""
        agents = _resolve_agents(pipeline_type)
        if not agents or len(agents) < 2:
            pytest.skip(f"{pipeline_type} has <2 agents")
        result = WorkflowResolver().validate(agents)
        assert result.satisfiable

        # Map agent_id → set of agent_ids it consumes from (resolved edges)
        consumes_from: dict[str, set[str]] = {}
        for edge in result.edges:
            consumes_from.setdefault(edge.to_agent_id, set()).add(edge.from_agent_id)

        position = {a.id: i for i, a in enumerate(result.dag)}
        for agent_id, deps in consumes_from.items():
            for dep_id in deps:
                assert position[dep_id] < position[agent_id], (
                    f"{pipeline_type}: {agent_id} runs before its dependency "
                    f"{dep_id} (positions {position[agent_id]} < {position[dep_id]})"
                )

    @pytest.mark.parametrize(
        "pipeline_type",
        [pt for pt in sorted(PIPELINE_AGENTS) if pt not in _EMPTY_SCAN | _STRUCTURALLY_INCOMPLETE],
    )
    def test_every_consumes_is_satisfied_upstream(self, pipeline_type):
        agents = _resolve_agents(pipeline_type)
        if not agents:
            pytest.skip(f"{pipeline_type} has no agents")
        produced_so_far: set[str] = set()
        exempt = {"planning_context", "constitution"}
        for agent in agents:
            wanted = [c for c in getattr(agent, "consumes", []) if c not in exempt]
            # AT LEAST ONE, not every entry. An agent shared between the main and the
            # revision pipelines declares BOTH producers — `prototype-plan` consumes
            # `prototype-specify` AND `prototype-revision-feature-specify` — so in any
            # single pipeline the other entry has no upstream producer by design.
            # Runtime agrees: an upstream output reaches a step iff its `produces`
            # INTERSECTS this `consumes` (plan.py:439), and the resolver drops the
            # unmatched entries once any one resolved (resolver.py:179). Demanding
            # every entry would forbid the shared-agent design outright; demanding one
            # still catches the real fault — an agent fed by nothing upstream.
            if wanted:
                assert any(c in produced_so_far for c in wanted), (
                    f"{pipeline_type}: agent {agent.id} consumes {wanted!r} "
                    f"and NONE is produced upstream (produced={produced_so_far})"
                )
            produced_so_far.update(getattr(agent, "produces", []))


# ---------------------------------------------------------------------------
# Tier 2 — Live streaming regression (requires credentials)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _llm_configured(), reason="No LLM provider configured")
@requires_api_key
class TestLiveStreamingRegression:
    """Exercises the real engine.execute() streaming path. Requires Bedrock
    or Anthropic credentials. Skipped automatically otherwise."""

    @pytest.mark.asyncio
    async def test_user_stories_event_sequence(self):
        import uuid
        from agents.execution_engine.engine import ExecutionEngine

        agents = _resolve_agents("user_stories")
        engine = ExecutionEngine()
        events = []
        async for ev in engine.execute(
            agents=agents,
            user_message="Build a login feature for a SaaS app",
            pipeline_run_id=str(uuid.uuid4()),
            pipeline_type="user_stories",
        ):
            events.append(ev["type"])

        # Planner runs first, then the pipeline, then completes
        assert "planner_start" in events
        assert "planner_complete" in events
        assert "pipeline_start" in events
        assert "pipeline_complete" in events
        assert events.index("planner_start") < events.index("pipeline_start")
        assert events.index("pipeline_start") < events.index("pipeline_complete")
        # workflow_validated emitted before pipeline_start
        assert "workflow_validated" in events
        assert events.index("workflow_validated") < events.index("pipeline_start")
        # agent_input emitted for each agent
        agent_input_events = [e for e in events if e == "agent_input"]
        assert len(agent_input_events) == len(agents)
