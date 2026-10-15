"""ISS-877 / ISS-878 (QA-KB-034): the engine roster seam must not expand silently.

ISS-877: ``_execute_impl`` replaces a strictly-partial caller roster with the full compiled plan
(engine.py ~5004-5007) and logs nothing. Fix = one INFO record naming the requested ids, the
plan ids and the pipeline_type, only inside the ``_roster_is_partial`` branch.

ISS-878: ``run_trigger_workflow`` hands ``_launch_run_core`` the raw registry roster (1 agent)
for a 3-step plan, so ``agent_count`` is minted as 1.

Offline: scripted planner/runner, temp RUNS_ROOT, ``_launch_run_core`` stubbed. No Bedrock.
"""

from __future__ import annotations

import logging
import uuid
from types import SimpleNamespace

import pytest

from tests.agents._scripted_model import _RUNS_ROOT

_ENGINE_LOGGER = "agents.execution_engine.engine"
_PIPELINE = "user_stories"


async def _records_until_pipeline_start(caplog, agents_arg):
    """Drive execute() to the first pipeline_start, return (event, records)."""
    import agents.execution_engine.engine as engine_mod
    from agents.execution_engine.engine import ExecutionEngine

    from app.core.config import settings as _settings

    _settings.RUNS_ROOT = _RUNS_ROOT
    engine = ExecutionEngine()

    async def _fake_run_planner(user_message, *a, **k):
        return engine._default_planning_context(user_message), "PROCEED"

    engine._run_planner = _fake_run_planner  # type: ignore[assignment]

    orig = engine_mod.compile_for_run

    def _patched(ptype, _orig=orig):
        compiled = _orig(ptype)
        compiled.clarify.mode = "off"
        return compiled

    engine_mod.compile_for_run = _patched
    caplog.set_level(logging.INFO, logger=_ENGINE_LOGGER)
    caplog.clear()
    agen = engine.execute(
        agents=agents_arg,
        user_message="Build me a thing for managing tasks.",
        pipeline_run_id=f"roster-seam-{uuid.uuid4().hex[:8]}",
        pipeline_type=_PIPELINE,
        user_id="roster-seam-user",
        od_context=None,
        gate_agent_ids=[],
    )
    start = None
    try:
        async for ev in agen:
            if ev.get("type") == "pipeline_start":
                start = ev
                break
    finally:
        await agen.aclose()
        engine_mod.compile_for_run = orig
    return start, list(caplog.records)


def _roster_records(records):
    return [
        r
        for r in records
        if r.name == _ENGINE_LOGGER
        and r.levelno == logging.INFO
        and "roster" in r.getMessage().lower()
        and "expand" in r.getMessage().lower()
    ]


@pytest.mark.asyncio
@pytest.mark.issue("ISS-877")
async def test_partial_roster_expansion_logs_info(caplog):
    """ISS-877 — a partial roster expanded to the plan emits one INFO record with ids + pipeline_type."""
    from agents.execution_engine.engine import compile_for_run
    from agents.registry import get_pipeline_agents

    plan_ids = [s.agent_id for s in compile_for_run(_PIPELINE).steps]
    requested = get_pipeline_agents(_PIPELINE)[:2]
    assert len(requested) < len(plan_ids)

    start, records = await _records_until_pipeline_start(caplog, requested)
    assert start is not None and start["data"]["agent_count"] == len(plan_ids)

    found = _roster_records(records)
    assert (
        len(found) == 1
    ), f"expected one roster-expansion INFO record, got {len(found)}"
    msg = found[0].getMessage()
    assert _PIPELINE in msg
    for aid in [a.id for a in requested] + plan_ids:
        assert aid in msg, f"{aid} missing from roster log: {msg}"


@pytest.mark.asyncio
@pytest.mark.parametrize("roster", ["empty", "full"])
async def test_no_roster_log_when_not_partial(caplog, roster):
    """Guard — empty or full roster takes no partial branch, so no expansion record."""
    from agents.registry import get_pipeline_agents

    agents_arg = [] if roster == "empty" else get_pipeline_agents(_PIPELINE)
    start, records = await _records_until_pipeline_start(caplog, agents_arg)
    assert start is not None
    assert _roster_records(records) == []


@pytest.mark.asyncio
@pytest.mark.issue("ISS-878")
async def test_trigger_path_roster_matches_plan_size(monkeypatch):
    """ISS-878 — run_trigger_workflow must hand the core a roster as large as the plan."""
    import app.api.run_commands as rc
    from agents.execution_engine.engine import compile_for_run
    from agents.execution_engine.kernel_services import KernelServices

    captured: dict = {}

    async def _stub_core(**kw):
        captured.update(kw)
        return {"run_id": "stub-run"}

    monkeypatch.setattr(rc, "_launch_run_core", _stub_core)
    ks = KernelServices.__new__(KernelServices)
    ks._pipeline_type = "user_stories"
    ks._ordered_agents = []
    ectx = SimpleNamespace(run_id="r", owner_id="o", workspace_id="w", trigger_depth=0)

    wf = "prototype_v2_revision"
    await ks.run_trigger_workflow(None, ectx, workflow_ref=wf)

    plan_len = len(compile_for_run(wf).steps)
    compiled = captured["compiled"]
    minted = len(compiled.steps) if compiled is not None else len(captured["agents"])
    assert (
        minted == plan_len
    ), f"agent_count would be {minted} for a {plan_len}-step plan"
