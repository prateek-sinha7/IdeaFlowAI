"""T080 — Performance validation tests (Phase 9 / SC-002, SC-003, SC-006–SC-008).

All tests require a live LLM provider (Bedrock/Anthropic) and are skipped
automatically when no credentials are configured.

Performance targets:
  SC-002: Deep_Planner_Agent < 15s
  SC-003: Total pre-pipeline (planning + clarification if triggered) < 30s
  SC-006: Thinking tab render < 1s (frontend — not testable here)
  SC-007: WorkflowRun restored within 30s of backend restart
  SC-008: Clarification questions restored within 5s of reconnect

Note: SC-006 is a frontend rendering target verified manually.
SC-007 and SC-008 are covered by test_resumability.py (unit level).
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid

import pytest

from agents.artifact_store.store import ArtifactStore
from agents.execution_engine.engine import ExecutionEngine
from agents.registry import get_pipeline_agents


def _llm_configured() -> bool:
    return bool(
        os.getenv("ANTHROPIC_API_KEY")
        or (os.getenv("BEDROCK_MODEL_ID") and os.getenv("AWS_REGION"))
        or (os.getenv("BEDROCK_INFERENCE_PROFILE_ID") and os.getenv("AWS_REGION"))
    )


requires_api_key = pytest.mark.skipif(
    not _llm_configured(), reason="No LLM provider configured"
)


@requires_api_key
class TestPerformanceTargets:
    """Live performance validation — requires LLM credentials."""

    @pytest.mark.asyncio
    async def test_planner_completes_within_15s(self):
        """SC-002: Deep_Planner_Agent must complete in under 15 seconds."""
        engine = ExecutionEngine()
        engine._store = ArtifactStore(use_db=False)
        pipeline_run_id = str(uuid.uuid4())

        start = time.monotonic()
        planning_context, gate = await engine._run_planner(
            user_message="Build a login feature for a SaaS app",
            pipeline_run_id=pipeline_run_id,
            model_id=None,
            cancel_event=None,
        )
        elapsed = time.monotonic() - start

        assert elapsed < 15.0, (
            f"SC-002 FAILED: Deep_Planner_Agent took {elapsed:.1f}s (limit: 15s)"
        )
        assert planning_context.get("execution_gate") in ("PROCEED", "CLARIFY_REQUIRED")

    @pytest.mark.asyncio
    async def test_total_pre_pipeline_within_30s(self):
        """SC-003: Total time from submission to first domain agent < 30s."""
        agents = get_pipeline_agents("user_stories")
        engine = ExecutionEngine()
        engine._store = ArtifactStore(use_db=False)
        pipeline_run_id = str(uuid.uuid4())

        start = time.monotonic()
        first_agent_start_time: float | None = None

        async for ev in engine.execute(
            agents=agents,
            user_message="Build a login feature",
            pipeline_run_id=pipeline_run_id,
            pipeline_type="user_stories",
        ):
            if ev["type"] == "agent_start" and first_agent_start_time is None:
                first_agent_start_time = time.monotonic()
                break  # Stop after first agent starts

        if first_agent_start_time is not None:
            elapsed = first_agent_start_time - start
            assert elapsed < 30.0, (
                f"SC-003 FAILED: Pre-pipeline took {elapsed:.1f}s (limit: 30s)"
            )

    @pytest.mark.asyncio
    async def test_clarification_restore_within_5s(self):
        """SC-008: Clarification questions restored within 5s of reconnect."""
        store = ArtifactStore(use_db=False)
        pipeline_run_id = str(uuid.uuid4())

        # Simulate a paused run with stored clarifications
        await store.store(
            run_id=pipeline_run_id,
            artifact_type="clarifications",
            name="clarifications_round_1",
            content='[{"question_id": "r1_q1", "question_text": "What is the target audience?", "impact_level": "high", "round": 1}]',
            producing_agent_id="clarify-agent",
        )

        # Simulate reconnect — retrieve clarifications
        start = time.monotonic()
        clarifications = await store.retrieve_latest(pipeline_run_id, "clarifications")
        elapsed = time.monotonic() - start

        assert clarifications is not None
        assert elapsed < 5.0, (
            f"SC-008 FAILED: Clarification restore took {elapsed:.3f}s (limit: 5s)"
        )
