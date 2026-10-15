"""ISS-966 (QA-KB-048): a strict-subset caller roster must run as that subset, not the full plan.

Offline: reuses the ISS-877 harness (scripted planner, temp RUNS_ROOT, execute() stopped at
pipeline_start). Today engine.py ~5004-5007 re-expands the subset, so agent_count == plan size.
"""

from __future__ import annotations

import pytest

from tests.integration.agents import test_roster_seam_log as seam


@pytest.mark.asyncio
@pytest.mark.issue("ISS-966")
@pytest.mark.xfail(reason="ISS-966 unfixed", strict=True)
async def test_strict_subset_roster_runs_as_subset(caplog, monkeypatch):
    """ISS-966 — ppt_v2 minus its last step must start with 3 agents, not the full plan of 4."""
    from agents.execution_engine.engine import compile_for_run
    from agents.registry import load_agent_spec

    monkeypatch.setattr(seam, "_PIPELINE", "ppt_v2")
    plan_ids = [s.agent_id for s in compile_for_run("ppt_v2").steps]
    subset = [load_agent_spec(a) for a in plan_ids[:-1]]
    assert len(subset) < len(plan_ids)

    start, _ = await seam._records_until_pipeline_start(caplog, subset)
    assert start is not None
    assert start["data"]["agent_count"] == len(subset)
