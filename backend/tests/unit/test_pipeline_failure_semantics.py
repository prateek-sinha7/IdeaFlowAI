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

  2. [RETIRED — see note] WS INGRESS guard: the ``missing_template_context``
     fail-fast lived ONLY in the deleted ``websocket.py::_handle_workflow_execution``
     ingress (engine.py:5265 confirms it "lives only at the run_pipeline WS
     ingress"). The ``/ws/chat`` retirement (44-07) deleted that handler, so the
     WS-half tests (old scenarios d/e/f, which drove ``_handle_workflow_execution``)
     were removed in 44-08. The guard is NOT replicated on the REST launch path
     (``run_commands.py::launch_run`` has no ``missing_template_context`` reject),
     so its behavioral coverage cannot be re-homed by a tests-only plan — this is a
     SRC gap flagged for a follow-up (see 44-08-SUMMARY.md "Deferred / Findings").

Scenarios (engine-level terminal semantics — the surviving, transport-neutral half):
  (a) all-agents-error run → exactly one pipeline_failed, NO pipeline_complete,
      state "failed", agents_failed lists every agent id;
  (b) one-of-two agents errors → terminal pipeline_complete carries
      status="degraded" + the failed id; agents_completed reflects the survivor;
  (c) clean run → pipeline_complete data contains NEITHER "status" NOR
      "agents_failed" (parity guard).

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
        # ``**_kw`` absorbs additive keyword-only params (ISS-097 added
        # ``invocation_gated``) so this double never pins a stale arity.
        **_kw,
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
    """Run the FULL user_stories roster through the REAL execute() path
    (dispatch loop + terminal block) with the stubbed per-agent runner.
    Returns (events, engine, run_id).

    ISS-632: the original harness used ``get_pipeline_agents("user_stories")[:2]``,
    a strict subset of the 6-step plan. ADR-0008's ``_roster_is_partial`` check fills
    in the full plan, so the engine always ran all 6 while the test expected 2.
    Now drives the full roster so count assertions are correct.
    """
    specs = get_pipeline_agents("user_stories")  # full roster — no [:2] slice
    assert len(specs) >= 2, "harness expects at least two user_stories agents"
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
    return events, engine, run_id, specs


def _events_of(events: list[dict], etype: str) -> list[dict]:
    return [e for e in events if e.get("type") == etype]


# ────────────────────────────────────────────────────────────────────────────
# (a) Total collapse → pipeline_failed terminal, state "failed"
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.issue("ISS-632")
@pytest.mark.asyncio
async def test_all_agents_failed_emits_pipeline_failed_not_complete(
    _offline_engine_env, monkeypatch
):
    # ISS-632: use full roster — no [:2] slice (ADR-0008 would expand it anyway).
    specs = get_pipeline_agents("user_stories")
    all_ids = {s.id for s in specs}

    events, engine, run_id, specs = await _drive_engine(monkeypatch, fail_ids=all_ids)

    failed = _events_of(events, "pipeline_failed")
    assert len(failed) == 1, f"expected exactly one pipeline_failed, got {events}"
    assert _events_of(events, "pipeline_complete") == [], (
        "a totally-failed run must NEVER emit pipeline_complete (F3)"
    )

    data = failed[0]["data"]
    assert data["agents_completed"] == 0
    assert data["agents_total"] == len(specs)
    assert data["agents_failed"] == sorted(all_ids)
    # IN-04 (13 review fix): neutral message — gate-skipped agents are neither
    # completed nor failed, so the old "all agents failed" could overstate.
    assert data["error"] == "no agent completed"
    assert data["pipeline_type"] == "user_stories"
    assert data["pipeline_run_id"] == run_id
    assert "total_duration" in data and "timestamp" in data

    # The state machine landed in the terminal "failed" state.
    assert engine._state_machine.get_state(run_id) == "failed"


# ────────────────────────────────────────────────────────────────────────────
# (b) Partial failure → degraded pipeline_complete (additive fields)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.issue("ISS-632")
@pytest.mark.asyncio
async def test_partial_failure_emits_degraded_pipeline_complete(
    _offline_engine_env, monkeypatch
):
    # ISS-632: full roster — no [:2] slice.
    specs = get_pipeline_agents("user_stories")
    failed_id = specs[0].id  # first agent fails; the rest survive

    events, engine, run_id, specs = await _drive_engine(monkeypatch, fail_ids={failed_id})

    assert _events_of(events, "pipeline_failed") == [], (
        "a partially-failed run completes (degraded) — it is not a total collapse"
    )
    complete = _events_of(events, "pipeline_complete")
    assert len(complete) == 1

    data = complete[0]["data"]
    assert data["status"] == "degraded"
    assert data["agents_failed"] == [failed_id]
    assert data["agents_completed"] == len(specs) - 1  # all but the one that failed
    assert data["agents_total"] == len(specs)
    assert engine._state_machine.get_state(run_id) == "completed"


# ────────────────────────────────────────────────────────────────────────────
# (c) Clean run → payload byte-identical (neither degraded key present)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.issue("ISS-632")
@pytest.mark.asyncio
async def test_clean_run_payload_carries_no_degraded_keys(
    _offline_engine_env, monkeypatch
):
    events, engine, run_id, specs = await _drive_engine(monkeypatch, fail_ids=set())

    assert _events_of(events, "pipeline_failed") == []
    complete = _events_of(events, "pipeline_complete")
    assert len(complete) == 1

    data = complete[0]["data"]
    # STRICTLY CONDITIONAL (INV-3 parity guard): a clean run's payload contains
    # NEITHER key — the characterization snapshots gate the full byte-identity.
    assert "status" not in data, f"clean run leaked 'status': {data!r}"
    assert "agents_failed" not in data, f"clean run leaked 'agents_failed': {data!r}"
    assert data["agents_completed"] == len(specs)
    assert engine._state_machine.get_state(run_id) == "completed"


# ────────────────────────────────────────────────────────────────────────────
# WR-05 (13 review fix): recoverable error + completion from the SAME agent
# (the agent-timeout degrade shape) is NOT a failure
# ────────────────────────────────────────────────────────────────────────────


def _make_timeout_shaped_stub(timeout_ids: set[str]):
    """Agents in ``timeout_ids`` emit a recoverable ``agent_error`` and then
    CONTINUE — appending a (partial/fallback) result and emitting
    ``agent_complete`` — exactly the engine's agent-timeout interleaving."""

    async def _stub(
        self, spec, index, ordered_agents, user_message, sandbox,
        pipeline_run_id, pipeline_type, planning_context, attached_skills,
        attached_hooks, model_id, results, cancel_event, ectx,
        # ``**_kw`` absorbs additive keyword-only params (ISS-097 added
        # ``invocation_gated``) so this double never pins a stale arity.
        **_kw,
    ):
        yield {
            "type": "agent_start",
            "data": {"agent_id": spec.id, "name": spec.name, "role": spec.role,
                     "icon": spec.icon, "index": index, "total": len(ordered_agents)},
        }
        if spec.id in timeout_ids:
            yield {
                "type": "agent_error",
                "data": {"agent_id": spec.id,
                         "error": "Agent timed out after 600s — using best available output",
                         "recoverable": True},
            }
            # …and CONTINUES (timeout degrade path): partial output is used.
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


@pytest.mark.issue("ISS-632")
@pytest.mark.asyncio
async def test_recovered_timeout_agent_is_not_listed_as_failed(
    _offline_engine_env, monkeypatch
):
    """An agent that emits a recoverable agent_error and then COMPLETES (timeout
    degrade) must not flip the run to "degraded" — pre-fix it appeared in BOTH
    agents_completed and agents_failed (a contradictory payload), and a
    timeout-only run lost its clean-completion presentation."""
    # ISS-632: full roster — no [:2] slice.
    specs = get_pipeline_agents("user_stories")
    monkeypatch.setattr(
        ExecutionEngine, "_run_agent", _make_timeout_shaped_stub({specs[0].id})
    )

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

    assert _events_of(events, "pipeline_failed") == []
    complete = _events_of(events, "pipeline_complete")
    assert len(complete) == 1

    data = complete[0]["data"]
    # All agents completed — the recovered timeout is NOT a failure.
    assert data["agents_completed"] == len(specs)
    assert "status" not in data, (
        f"recovered timeout flipped the run to degraded: {data!r}"
    )
    assert "agents_failed" not in data, (
        f"an agent appears in BOTH agents_completed and agents_failed: {data!r}"
    )
    assert engine._state_machine.get_state(run_id) == "completed"


@pytest.mark.issue("ISS-632")
@pytest.mark.asyncio
async def test_unrecovered_failure_alongside_recovered_timeout_lists_only_the_failure(
    _offline_engine_env, monkeypatch
):
    """Mixed run: agent 1 times out but recovers (error + complete), agent 2
    hard-fails (error, no complete) → degraded, agents_failed lists ONLY agent 2."""
    # ISS-632: full roster — no [:2] slice. Pick the first two agents for the
    # specific recovered/failed roles; the remaining agents all complete normally.
    specs = get_pipeline_agents("user_stories")
    recovered_id, failed_id = specs[0].id, specs[1].id

    def _mixed_stub():
        async def _stub(
            self, spec, index, ordered_agents, user_message, sandbox,
            pipeline_run_id, pipeline_type, planning_context, attached_skills,
            attached_hooks, model_id, results, cancel_event, ectx,
            **_kw,  # additive keyword-only params (ISS-097: invocation_gated)
        ):
            yield {
                "type": "agent_start",
                "data": {"agent_id": spec.id, "name": spec.name, "role": spec.role,
                         "icon": spec.icon, "index": index,
                         "total": len(ordered_agents)},
            }
            if spec.id == failed_id:
                yield {
                    "type": "agent_error",
                    "data": {"agent_id": spec.id, "error": "hard failure",
                             "recoverable": True},
                }
                return  # hard fail — no result, no agent_complete
            yield {
                "type": "agent_error",
                "data": {"agent_id": spec.id, "error": "timed out",
                         "recoverable": True},
            }
            results.append({
                "agent_id": spec.id, "name": spec.name, "role": spec.role,
                "icon": spec.icon, "output": "partial", "duration": 0.01,
                "input_tokens": 1, "output_tokens": 1, "total_tokens": 2,
            })
            yield {
                "type": "agent_complete",
                "data": {"agent_id": spec.id, "name": spec.name, "duration": 0.01,
                         "output_length": 7, "index": index,
                         "total": len(ordered_agents), "input_tokens": 1,
                         "output_tokens": 1, "total_tokens": 2},
            }

        return _stub

    monkeypatch.setattr(ExecutionEngine, "_run_agent", _mixed_stub())

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

    data = _events_of(events, "pipeline_complete")[0]["data"]
    assert data["status"] == "degraded"
    assert data["agents_failed"] == [failed_id], (
        "agents_failed must list ONLY the agent that never completed"
    )
    # recovered + (N-2) clean agents completed; only failed_id is absent.
    assert data["agents_completed"] == len(specs) - 1

