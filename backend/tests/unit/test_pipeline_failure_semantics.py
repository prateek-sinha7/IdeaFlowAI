"""tests/unit/test_pipeline_failure_semantics.py — F3 (13-06) terminal semantics.

Live UAT Gap 3 (finding F3, major): a run whose agents ALL hard-fail used to end
in ``pipeline_complete`` with ``final_output=''`` — an invisible failure. Two
compounding defects were fixed:

  1. ENGINE terminal semantics (engine.py Step-5 terminal block):
     * total collapse (every agent errored, nothing completed) → ONE
       ``pipeline_failed`` event + state machine in "failed" — never
       ``pipeline_complete``;
     * partial failure → ``pipeline_complete`` with the ADDITIVE
       ``status="degraded"`` + ``agents_failed`` keys;
     * clean run → payload byte-identical (NEITHER key present — the 5
       characterization snapshots gate this parity, INV-3).

  2. WS INGRESS guard (websocket.py): a pipeline whose resolved agents declare
     ``injects: [template, ...]`` with no loadable template body is rejected at
     ingress with code ``missing_template_context`` BEFORE the engine spins up
     (T-13-06-01) — mirroring the factory's ``_compose_injection`` raise
     condition EXACTLY. Generic: keyed on declared injects only, never a
     pipeline-name allow/deny list (SC-001).

Scenarios (per 13-06-PLAN.md):
  (a) all-agents-error run → exactly one pipeline_failed, NO pipeline_complete,
      state "failed", agents_failed lists every agent id;
  (b) one-of-two agents errors → terminal pipeline_complete carries
      status="degraded" + the failed id; agents_completed reflects the survivor;
  (c) clean run → pipeline_complete data contains NEITHER "status" NOR
      "agents_failed" (parity guard);
  (d) bare "prototype" with no template_id → exactly one error event with code
      "missing_template_context", engine never invoked;
  (e) the same pipeline with od_context carrying a template_body → guard passes
      (engine invoked, no missing_template_context error);
  (f) a no-injects pipeline (user_stories) with no template → guard does not fire.

Offline — stubbed ``_run_agent`` / stub engine, in-memory SQLite, no Bedrock.
"""

from __future__ import annotations

import uuid

import pytest

import agents.execution_engine.engine as engine_mod
from agents.execution_engine.engine import ExecutionEngine
from agents.registry import get_pipeline_agents


# ════════════════════════════════════════════════════════════════════════════
# Engine-level harness — drive execute() with a stubbed _run_agent
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def _offline_engine_env(tmp_path, monkeypatch):
    """Offline engine prerequisites: writable RUNS_ROOT + planner skipped.

    ``compile_for_run`` is wrapped (NOT replaced — the real compiler runs) to
    flip ``planner`` to "skip" so no Deep-Planner model call is made; the
    clarify gate never opens on the skip path (gate_verdict=PROCEED).
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "RUNS_ROOT", str(tmp_path), raising=False)

    _orig = engine_mod.compile_for_run

    def _patched(pipeline_type, _orig=_orig):
        compiled = _orig(pipeline_type)
        compiled.planner = "skip"
        return compiled

    monkeypatch.setattr(engine_mod, "compile_for_run", _patched)


def _make_stub_run_agent(fail_ids: set[str]):
    """A stubbed ``ExecutionEngine._run_agent``: agents in ``fail_ids`` yield an
    ``agent_error`` and append NOTHING to results (mirrors the real except path);
    every other agent appends a result + yields ``agent_complete``."""

    async def _stub(
        self, spec, index, ordered_agents, user_message, sandbox,
        pipeline_run_id, pipeline_type, planning_context, attached_skills,
        attached_hooks, model_id, results, cancel_event, ectx,
    ):
        yield {
            "type": "agent_start",
            "data": {"agent_id": spec.id, "name": spec.name, "role": spec.role,
                     "icon": spec.icon, "index": index, "total": len(ordered_agents)},
        }
        if spec.id in fail_ids:
            yield {
                "type": "agent_error",
                "data": {"agent_id": spec.id, "error": "simulated hard failure",
                         "recoverable": True},
            }
            return
        results.append({
            "agent_id": spec.id, "name": spec.name, "role": spec.role,
            "icon": spec.icon, "output": f"{spec.id} output", "duration": 0.01,
            "input_tokens": 1, "output_tokens": 1, "total_tokens": 2,
        })
        yield {
            "type": "agent_complete",
            "data": {"agent_id": spec.id, "name": spec.name, "duration": 0.01,
                     "output_length": len(f"{spec.id} output"), "index": index,
                     "total": len(ordered_agents), "input_tokens": 1,
                     "output_tokens": 1, "total_tokens": 2},
        }

    return _stub


async def _drive_engine(monkeypatch, fail_ids: set[str]):
    """Run a 2-agent user_stories subset through the REAL execute() path
    (dispatch loop + terminal block) with the stubbed per-agent runner.
    Returns (events, engine, run_id)."""
    specs = get_pipeline_agents("user_stories")[:2]
    assert len(specs) == 2, "harness expects two user_stories agents"
    monkeypatch.setattr(ExecutionEngine, "_run_agent", _make_stub_run_agent(fail_ids))

    engine = ExecutionEngine()
    run_id = str(uuid.uuid4())
    events: list[dict] = []
    async for event in engine.execute(
        agents=specs,
        user_message="build a backlog",
        pipeline_run_id=run_id,
        pipeline_type="user_stories",
        session_id="sess-f3",
    ):
        events.append(event)
    return events, engine, run_id


def _events_of(events: list[dict], etype: str) -> list[dict]:
    return [e for e in events if e.get("type") == etype]


# ────────────────────────────────────────────────────────────────────────────
# (a) Total collapse → pipeline_failed terminal, state "failed"
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_all_agents_failed_emits_pipeline_failed_not_complete(
    _offline_engine_env, monkeypatch
):
    specs = get_pipeline_agents("user_stories")[:2]
    all_ids = {s.id for s in specs}

    events, engine, run_id = await _drive_engine(monkeypatch, fail_ids=all_ids)

    failed = _events_of(events, "pipeline_failed")
    assert len(failed) == 1, f"expected exactly one pipeline_failed, got {events}"
    assert _events_of(events, "pipeline_complete") == [], (
        "a totally-failed run must NEVER emit pipeline_complete (F3)"
    )

    data = failed[0]["data"]
    assert data["agents_completed"] == 0
    assert data["agents_total"] == 2
    assert data["agents_failed"] == sorted(all_ids)
    assert data["error"] == "all agents failed"
    assert data["pipeline_type"] == "user_stories"
    assert data["pipeline_run_id"] == run_id
    assert "total_duration" in data and "timestamp" in data

    # The state machine landed in the terminal "failed" state.
    assert engine._state_machine.get_state(run_id) == "failed"


# ────────────────────────────────────────────────────────────────────────────
# (b) Partial failure → degraded pipeline_complete (additive fields)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_partial_failure_emits_degraded_pipeline_complete(
    _offline_engine_env, monkeypatch
):
    specs = get_pipeline_agents("user_stories")[:2]
    failed_id = specs[0].id  # first agent fails; second survives

    events, engine, run_id = await _drive_engine(monkeypatch, fail_ids={failed_id})

    assert _events_of(events, "pipeline_failed") == [], (
        "a partially-failed run completes (degraded) — it is not a total collapse"
    )
    complete = _events_of(events, "pipeline_complete")
    assert len(complete) == 1

    data = complete[0]["data"]
    assert data["status"] == "degraded"
    assert data["agents_failed"] == [failed_id]
    assert data["agents_completed"] == 1  # the survivor
    assert data["agents_total"] == 2
    assert engine._state_machine.get_state(run_id) == "completed"


# ────────────────────────────────────────────────────────────────────────────
# (c) Clean run → payload byte-identical (neither degraded key present)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clean_run_payload_carries_no_degraded_keys(
    _offline_engine_env, monkeypatch
):
    events, engine, run_id = await _drive_engine(monkeypatch, fail_ids=set())

    assert _events_of(events, "pipeline_failed") == []
    complete = _events_of(events, "pipeline_complete")
    assert len(complete) == 1

    data = complete[0]["data"]
    # STRICTLY CONDITIONAL (INV-3 parity guard): a clean run's payload contains
    # NEITHER key — the characterization snapshots gate the full byte-identity.
    assert "status" not in data, f"clean run leaked 'status': {data!r}"
    assert "agents_failed" not in data, f"clean run leaked 'agents_failed': {data!r}"
    assert data["agents_completed"] == 2
    assert engine._state_machine.get_state(run_id) == "completed"
