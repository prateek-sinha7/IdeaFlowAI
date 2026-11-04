"""tests/agents/test_pipeline_complete_status_v4.py — ISS-872 visit-count fix.

Root cause: ``_execute_impl``'s ``_unrecovered_agents`` block used an exact
``(agent_id, task_number, visit_count)`` triple membership check against
``_completed_pairs``.  An agent that errored at visit N and was re-dispatched
via a route loop-back completes at visit N+1; the visit-N triple is absent from
``_completed_pairs``, so the agent is falsely kept in ``_unrecovered_agents``
and the run is persisted "degraded" even though the agent produced valid output.

Fix (``engine.py``, the ``_unrecovered_agents`` block): build a per-
``(agent_id, task_number)`` max-visit-count dict from ``_completed_pairs`` and
use ``_completed_max_visit.get((agent_id, task_number), -1) < visit_count``
instead of exact-triple membership.

This file drives the REAL ``_execute_impl`` end-to-end (offline ``_drive``
harness — zero Bedrock cost) using fake finalizers that inject controlled
``failed_invocations`` entries.  The ``step_visit_counts`` dict on the
``ExecutionContext`` is pre-seeded for the visit-mismatch scenario by wrapping
``ExecutionContext.__init__`` inside a ``patch.object`` context manager.

INV-3 safety: the fake finalizer always returns ``published_status="completed"``
so characterization goldens (which gate on byte-identical events for all-success
runs) are completely unaffected — ``failed_invocations`` is populated only by
the fake finalizer, never by the scripted model.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# Importing the harness forces InMemory checkpointer + temp RUNS_ROOT before
# app.core.config loads.  Keep this import first (mirrors test_cancel_paths_v3.py).
from tests.agents._scripted_model import _drive

import agents.execution_engine.context as ctx_mod
import agents.execution_engine.engine as engine_mod
from agents.execution_engine.finalization import FinalizationRecord

# First step in the custom pipeline — single_shot, text-only, no gates.
_AGENT_ID = "market-research-agent"


# ── helpers ──────────────────────────────────────────────────────────────────


def _pipeline_complete_events(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("type") == "pipeline_complete"]


def _injecting_finalizer(*failure_triples):
    """Fake finalizer that injects synthetic ``failed_invocations`` triples onto
    the ``ExecutionContext`` and always returns ``published_status="completed"``
    so the finalizer itself never contributes a degraded verdict — only the
    ``_unrecovered_agents`` computation under test can do that.
    """

    async def _finalize(run_id, ectx, *, candidate_status="completed"):
        for triple in failure_triples:
            ectx.failed_invocations.add(triple)
        return FinalizationRecord(
            run_id=run_id,
            owner_id="harness-user",
            workspace_id="",
            published_status="completed",
            candidate_status=candidate_status,
        )

    return _finalize


# ── tests ─────────────────────────────────────────────────────────────────────


class TestVisitCountMismatchNotFalsePositive:
    """ISS-872: an agent that errored at visit N and completed at visit N+1
    must NOT appear in ``_unrecovered_agents``."""

    @pytest.mark.asyncio
    async def test_lower_visit_failure_recovered_by_higher_visit_completion(
        self,
    ) -> None:
        """Visit-0 failure with visit-1 completion must NOT produce a degraded
        pipeline_complete.  Before the fix, the exact-triple check kept the
        visit-0 failure in ``_unrecovered_agents`` even when the agent completed
        at visit 1.
        """
        # Wrap ExecutionContext.__init__ to pre-seed step_visit_counts so the
        # agent runs and completes at visit_count=1.  The scripted model still
        # executes the agent normally — only the visit counter starts higher.
        _orig_init = ctx_mod.ExecutionContext.__init__

        def _preseeded_init(self, *args, **kwargs):  # noqa: N805
            _orig_init(self, *args, **kwargs)
            # Simulate: the step was re-entered once (route loop-back) so the
            # agent's visit counter is already at 1 before this run's dispatch.
            self.step_visit_counts[_AGENT_ID] = 1

        with patch.object(ctx_mod.ExecutionContext, "__init__", _preseeded_init):
            with patch.object(
                engine_mod,
                "finalize_terminal_run",
                # Stale failure at visit 0; the agent will complete at visit 1.
                _injecting_finalizer((_AGENT_ID, "", 0)),
            ):
                events = await _drive("custom")

        completes = _pipeline_complete_events(events)
        assert len(completes) == 1, f"expected 1 pipeline_complete, got {completes}"
        data = completes[0]["data"]

        # Load-bearing assertion: visit-0 failure should be considered recovered
        # because the agent completed at the higher visit-1.  The degraded verdict
        # would be a false positive (ISS-872 fix).
        assert data.get("status") != "degraded", (
            "A visit-0 failure with a visit-1 completion is a false positive — "
            "_unrecovered_agents must NOT include this agent after the ISS-872 fix."
        )
        agents_failed = data.get("agents_failed") or []
        assert (
            _AGENT_ID not in agents_failed
        ), f"{_AGENT_ID} must not appear in agents_failed when it completed at visit 1"

    @pytest.mark.asyncio
    async def test_genuinely_unrecovered_agent_stays_degraded(self) -> None:
        """An agent with no completion in results must stay in
        ``_unrecovered_agents`` → ``pipeline_complete.status == "degraded"``.
        """
        # 'ghost-agent-xyz' is NOT in the custom pipeline manifest; it will
        # never appear in results.
        _ghost = "ghost-agent-xyz"

        with patch.object(
            engine_mod,
            "finalize_terminal_run",
            _injecting_finalizer((_ghost, "", 0)),
        ):
            events = await _drive("custom")

        completes = _pipeline_complete_events(events)
        assert len(completes) == 1
        data = completes[0]["data"]

        assert data.get("status") == "degraded", (
            "A genuinely unrecovered agent (no agent_complete in results) must "
            "produce a degraded verdict."
        )
        assert _ghost in (data.get("agents_failed") or [])

    @pytest.mark.asyncio
    async def test_same_visit_failure_recovered_when_completion_matches(
        self,
    ) -> None:
        """Control: failure at visit 0 with completion also at visit 0 must still
        be treated as recovered (ISS-028 WR-05 contract preserved — same-visit
        recovery is the baseline the fix must not regress).
        """
        # market-research-agent runs at default visit_count=0 (step_visit_counts
        # not pre-seeded).  Injecting a failure at the same visit must be
        # subtracted by the completion at that visit.
        with patch.object(
            engine_mod,
            "finalize_terminal_run",
            _injecting_finalizer((_AGENT_ID, "", 0)),
        ):
            events = await _drive("custom")

        completes = _pipeline_complete_events(events)
        assert len(completes) == 1
        data = completes[0]["data"]

        assert data.get("status") != "degraded", (
            "A same-visit failure is recovered by a same-visit completion — "
            "this must remain true after the ISS-872 fix (WR-05 preserved)."
        )
        assert _AGENT_ID not in (data.get("agents_failed") or [])
