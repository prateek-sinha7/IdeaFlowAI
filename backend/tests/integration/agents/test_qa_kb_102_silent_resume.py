"""QA-KB-102 — a resume that cannot start must END VISIBLY, not silently.

Each test drives the REAL engine (not the stub of test_rest_resume_api.py) and asserts the
CORRECT behaviour, so it is red until the engine funnel records a failure (one terminal
event after the resume marker, the row failed with the new reason, a live frame, cleanup).
Harness and recipes: evidence/qa-kb-102/analysis-plugins/kb102_probe_test.py.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

import app.api.run_commands as rc_mod
import app.api.run_engine as ws_mod
from tests.integration.agents.test_restart_resume_db import (
    _make_session,
    _ResumeHarness,
    _seed_workflow_run,
    _wire_user_resume_drive,
)

OWNER, WS = "kb102-user", "ws-kb102"
PRIOR_ERROR = "prior attempt: step a raised ValueError('boom')"
_TOOLS = {"read_files": True, "write_files": True, "exec": False, "tool_sets": []}


class _User:
    def __init__(self, id, tier="enterprise"):
        self.id, self.tier, self.preferred_model = id, tier, None


def _manifest(*, broken: bool) -> dict:
    return {
        "id": "composed-two-step",
        "name": "Two-Step",
        "description": "d",
        "planner": "skip",
        "clarify": {"mode": "skip", "defaults": []},
        "deliverable": {
            "strategy": "no_such_deliverable_resolver" if broken else "streamed_text"
        },
        "_trust": "db",
        "steps": [
            {
                "agent": "custom-agent",
                "instance_id": "a",
                "name": "A",
                "prompt": "Do A.",
                "depends_on": [],
                "tools": dict(_TOOLS),
            },
            {
                "agent": "custom-agent",
                "instance_id": "b",
                "name": "B",
                "prompt": "Do B.",
                "depends_on": ["custom-agent:a"],
                "tools": dict(_TOOLS),
            },
        ],
    }


async def _seed_prior(session, run_id, kind):
    from agents.authz import ScopedStore

    store = ScopedStore(owner_id=OWNER, workspace_id=WS, session=session)
    seq = 0

    async def ev(t, p):
        nonlocal seq
        seq += 1
        await store.append_event(
            run_id, seq=seq, event_id=f"ev-{seq}", type=t, payload_json=p
        )

    await ev("pipeline_start", {"pipeline_run_id": run_id, "agent_count": 2})
    await ev("agent_start", {"agent_id": "custom-agent:a"})
    if kind == "failed":
        await ev(
            "pipeline_failed",
            {"error": PRIOR_ERROR, "agents_failed": ["custom-agent:a"]},
        )
    elif kind == "degraded":
        await ev("agent_complete", {"agent_id": "custom-agent:a", "total_tokens": 10})
        await ev(
            "pipeline_complete",
            {
                "status": "degraded",
                "degraded_reason": "agent b failed",
                "agents_failed": ["custom-agent:b"],
                "final_output": "",
            },
        )
    session.commit()


def _arm(engine):
    engine._resume_register_queue = ws_mod._register_resume_queue
    engine._resume_register_task = ws_mod._register_resume_task
    engine._resume_cleanup = ws_mod._cleanup_pipeline
    engine._resume_cancel_event = ws_mod._resume_cancel_event
    engine._resume_live_ectx_register = rc_mod.register_live_ectx
    engine._resume_live_ectx_unregister = rc_mod.unregister_live_ectx
    engine._resume_output_persist_sink = rc_mod.persist_resume_output_columns


@pytest.fixture(autouse=True)
def _clean_registries():
    ds = (
        ws_mod._PIPELINE_TASKS,
        ws_mod._PIPELINE_QUEUES,
        ws_mod._CANCEL_EVENTS,
        ws_mod._SUBSCRIBERS,
    )
    for d in ds:
        d.clear()
    yield
    for d in ds:
        d.clear()


def _state(session, run_id):
    from app.models.run_event import RunEvent
    from app.models.workflow import WorkflowRun

    session.expire_all()
    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    evs = (
        session.query(RunEvent)
        .filter(RunEvent.run_id == run_id)
        .order_by(RunEvent.seq.asc())
        .all()
    )
    return row, [e.type for e in evs]


def _seed_run(session, run_id, status, type_, manifest=None):
    from app.models.workflow import WorkflowRun

    _seed_workflow_run(
        session, run_id, owner=OWNER, status=status, type_=type_, workspace_id=WS
    )
    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    row.manifest_json, row.error = manifest, PRIOR_ERROR
    session.commit()


async def _post_resume(monkeypatch, session, db_engine, run_id, *, mutate=None):
    """POST /resume through the real endpoint function; wait for the driver; return queue items."""
    from tests.fakes.principal import principal_for

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        _wire_user_resume_drive(monkeypatch, db_engine, engine)
        _arm(engine)
        if mutate:
            mutate()
        user = _User(OWNER)
        resp = await rc_mod.resume_run_endpoint(
            run_id, auth=(user, principal_for(user))
        )
        task = ws_mod._PIPELINE_TASKS[run_id]
        queue = ws_mod._PIPELINE_QUEUES[run_id]
        await asyncio.wait_for(task, timeout=120)
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    assert resp == {"run_id": run_id}
    return items


@pytest.mark.issue("ISS-1103")
async def test_refused_user_resume_records_a_new_failure(monkeypatch):
    """ISS-1103 — a resume whose manifest no longer compiles must append a NEW pipeline_failed
    and carry a NEW .error, not leave the previous attempt's text as the reason."""
    session, db_engine = _make_session()
    run_id = f"a-{uuid.uuid4().hex[:8]}"
    _seed_run(session, run_id, "failed", "custom", _manifest(broken=True))
    await _seed_prior(session, run_id, "failed")
    await _post_resume(monkeypatch, session, db_engine, run_id)
    row, types = _state(session, run_id)
    assert (
        types.count("pipeline_failed") == 2
    ), f"no failure recorded for the refused resume: {types}"
    assert row.error and row.error != PRIOR_ERROR, f"error is stale: {row.error!r}"


@pytest.mark.issue("ISS-1103")
async def test_execute_impl_fault_before_dispatch_is_not_swallowed(monkeypatch):
    """ISS-1103 — a fault inside _execute_impl before the first dispatch (sandbox quarantine)
    must be recorded, not swallowed at _drive_resumed_stream."""
    from app.agents.sandbox import RunSandbox
    from tests.integration.agents.test_restart_resume_db import _FIXTURE_ID

    session, db_engine = _make_session()
    run_id = f"c-{uuid.uuid4().hex[:8]}"
    _seed_run(session, run_id, "failed", _FIXTURE_ID)
    await _seed_prior(session, run_id, "failed")
    monkeypatch.setattr(
        RunSandbox,
        "detect_persistent_git_state",
        lambda self: {"state": "merge_in_progress"},
        raising=False,
    )
    monkeypatch.setattr(
        RunSandbox,
        "reconcile_persistent_git_state",
        lambda self, st: "quarantined",
        raising=False,
    )
    monkeypatch.setattr(rc_mod, "_require_tier_entitlement", lambda *a, **k: None)
    await _post_resume(monkeypatch, session, db_engine, run_id)
    row, types = _state(session, run_id)
    assert (
        types.count("pipeline_failed") == 2
    ), f"swallowed fault left no terminal event: {types}"
    assert row.error != PRIOR_ERROR


@pytest.mark.issue("ISS-1119")
async def test_restart_auto_resume_that_cannot_start_does_not_leave_a_running_ghost(
    monkeypatch,
):
    """ISS-1119 — after restore_non_terminal_runs cannot start a resume, the row must not stay
    'running' with no driver (and must not gain a run_resuming marker per restart)."""
    from agents.authz import ScopedStore

    session, db_engine = _make_session()
    run_id = f"d-{uuid.uuid4().hex[:8]}"
    _seed_run(session, run_id, "running", "custom", _manifest(broken=True))
    store = ScopedStore(owner_id=OWNER, workspace_id=WS, session=session)
    await store.append_event(
        run_id,
        seq=1,
        event_id="ev-1",
        type="pipeline_start",
        payload_json={"pipeline_run_id": run_id},
    )
    await store.append_event(
        run_id,
        seq=2,
        event_id="ev-2",
        type="agent_start",
        payload_json={"agent_id": "custom-agent:a"},
    )
    session.commit()
    for _ in range(2):  # two restarts
        with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
            engine = h.make_engine()
            _wire_user_resume_drive(monkeypatch, db_engine, engine)
            _arm(engine)
            await engine.restore_non_terminal_runs()
            for _ in range(200):
                await asyncio.sleep(0.05)
                t = ws_mod._PIPELINE_TASKS.get(run_id)
                if t is None or t.done():
                    break
            await asyncio.sleep(0.2)
    row, types = _state(session, run_id)
    assert row.status == "failed", f"ghost row: status={row.status!r}, events={types}"
    assert types.count("run_resuming") <= 1, types


@pytest.mark.issue("ISS-1120")
async def test_clarify_replay_that_cannot_start_fails_the_parked_run(monkeypatch):
    """ISS-1120 — _replay_clarify_run bailing (manifest no longer compiles) must not leave the
    waiting_for_user run parked behind an armed waiter nobody awaits."""
    session, db_engine = _make_session()
    run_id = f"r-{uuid.uuid4().hex[:8]}"
    _seed_run(session, run_id, "waiting_for_user", "custom", _manifest(broken=True))
    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        _wire_user_resume_drive(monkeypatch, db_engine, engine)
        _arm(engine)
        await engine._replay_clarify_run(run_id)
    row, types = _state(session, run_id)
    assert (
        row.status == "failed" and "pipeline_failed" in types
    ), f"{row.status!r} {types}"


@pytest.mark.issue("ISS-1122")
async def test_refused_resume_of_degraded_run_carries_its_own_reason(monkeypatch):
    """ISS-1122 — a refused resume of a degraded run relabels it failed; the reason must be the
    refusal, not the previous attempt's .error text."""
    session, db_engine = _make_session()
    run_id = f"g-{uuid.uuid4().hex[:8]}"
    _seed_run(session, run_id, "degraded", "custom", _manifest(broken=True))
    await _seed_prior(session, run_id, "degraded")
    await _post_resume(monkeypatch, session, db_engine, run_id)
    row, _ = _state(session, run_id)
    assert (
        row.error != PRIOR_ERROR
    ), f"status={row.status!r} still blames the previous attempt: {row.error!r}"


@pytest.mark.issue("ISS-1123")
async def test_pre_funnel_resume_fault_sends_a_frame_and_cleans_up(monkeypatch):
    """ISS-1123 — a resume fault before the funnel's try ends the row failed (already true) AND
    tells the live client: a terminal frame on the queue, registries cleaned."""
    import agents.execution_engine.engine as engine_mod
    from tests.integration.agents.test_restart_resume_db import _FIXTURE_ID

    session, db_engine = _make_session()
    run_id = f"f-{uuid.uuid4().hex[:8]}"
    _seed_run(session, run_id, "failed", _FIXTURE_ID)
    await _seed_prior(session, run_id, "failed")
    monkeypatch.setattr(rc_mod, "_require_tier_entitlement", lambda *a, **k: None)

    def _boom(*a, **k):
        raise RuntimeError("scripted fault before the funnel try")

    monkeypatch.setattr(engine_mod, "RunTrace", _boom)
    items = await _post_resume(monkeypatch, session, db_engine, run_id)
    row, _ = _state(session, run_id)
    assert row.status == "failed" and "scripted fault" in (
        row.error or ""
    )  # control: DB is right
    assert any(
        i for i in items if i is not None
    ), f"no terminal frame reached the live queue: {items}"
    assert (
        run_id not in ws_mod._PIPELINE_QUEUES
    ), "producer queue still registered after the driver ended"
