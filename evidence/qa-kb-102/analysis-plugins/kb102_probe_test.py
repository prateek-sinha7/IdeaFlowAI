"""QA-KB-102 analysis probe -- NOT part of the test suite (lives under evidence/, run by path).

Question: does a user resume that cannot start end silently THROUGH THE REAL ENDPOINT, with the
REAL engine (not the stub engine of tests/integration/api/test_rest_resume_api.py)?

Everything is offline: in-memory SQLite (StaticPool) shared by the harness, no model call, no
network, no live DB. The scratch process is pinned to a throwaway SQLite file BEFORE `app.*` is
imported (the repo's conftest.py does the same, but it does not apply to a file outside
backend/tests), so the app's global engine can never bind the live Postgres.

Run:   cd backend && DATABASE_URL=sqlite:////<scratch>.db PYTHONPATH=. .venv/bin/python -m pytest \
           <this file> -c pyproject.toml -p no:cacheprovider -q
Output: appended to $KB102_OUT.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid

import pytest

# Hard guard: refuse to run against anything but a throwaway sqlite file.
assert os.environ.get("DATABASE_URL", "").startswith("sqlite:"), "set DATABASE_URL=sqlite:///... first"

import app.models  # noqa: E402,F401  (registers every model on Base.metadata)
from app.models.database import Base, engine as _global_engine  # noqa: E402

Base.metadata.create_all(bind=_global_engine)

from tests.integration.agents.test_restart_resume_db import (  # noqa: E402
    _FIXTURE_ID,
    _make_session,
    _ResumeHarness,
    _seed_workflow_run,
    _wire_user_resume_drive,
)

OUT = os.environ["KB102_OUT"]


def emit(line: str = "") -> None:
    with open(OUT, "a") as fh:
        fh.write(line + "\n")


class _User:
    """What the endpoint reads off the caller: id, tier, preferred_model."""

    def __init__(self, id: str, tier: str = "enterprise"):
        self.id = id
        self.tier = tier
        self.preferred_model = None


# A valid three-step composed manifest (shape copied from test_restart_resume_db.py:5657).
_TOOLS = {"read_files": True, "write_files": True, "exec": False, "tool_sets": []}


def _manifest(*, broken: bool) -> dict:
    return {
        "id": "composed-three-step",
        "name": "Three-Step Composed Workflow",
        "description": "A user-composed three-step custom workflow.",
        "planner": "skip",
        "clarify": {"mode": "skip", "defaults": []},
        # `broken`: a resolver name the registry does not know -> WorkflowCompiler.compile raises.
        "deliverable": {"strategy": "no_such_deliverable_resolver" if broken else "streamed_text"},
        "_trust": "db",
        "steps": [
            {"agent": "custom-agent", "instance_id": "a", "name": "Step A", "prompt": "Do A.",
             "depends_on": [], "tools": dict(_TOOLS)},
            {"agent": "custom-agent", "instance_id": "b", "name": "Step B", "prompt": "Do B.",
             "depends_on": ["custom-agent:a"], "tools": dict(_TOOLS)},
        ],
    }


PRIOR_ERROR = "prior attempt: step a raised ValueError('boom')"


async def _seed_prior_attempt(session, run_id, owner, ws, kind: str) -> None:
    """The durable tail a real earlier attempt leaves, ending in the `kind` terminal."""
    from agents.authz import ScopedStore

    store = ScopedStore(owner_id=owner, workspace_id=ws, session=session)
    seq = 0

    async def ev(type_, payload):
        nonlocal seq
        seq += 1
        await store.append_event(run_id, seq=seq, event_id=f"ev-{seq}", type=type_, payload_json=payload)

    await ev("pipeline_start", {"pipeline_run_id": run_id, "agent_count": 2})
    await ev("agent_start", {"agent_id": "custom-agent:a"})
    if kind == "failed":
        await ev("agent_error", {"agent_id": "custom-agent:a", "error": PRIOR_ERROR})
        await ev("pipeline_failed", {"error": PRIOR_ERROR, "agents_failed": ["custom-agent:a"]})
    elif kind == "cancelled":
        await ev("pipeline_cancelled", {"message": "Pipeline cancelled"})
    elif kind == "degraded":
        await ev("agent_complete", {"agent_id": "custom-agent:a", "total_tokens": 10})
        await ev("pipeline_complete", {"status": "degraded", "degraded_reason": "agent b failed",
                                       "agents_failed": ["custom-agent:b"], "final_output": ""})
    session.commit()


def _arm_like_main_py(engine, ws_mod, rc_mod) -> None:
    """The hooks app/main.py:159-190 injects on the startup singleton."""
    engine._resume_register_queue = ws_mod._register_resume_queue
    engine._resume_register_task = ws_mod._register_resume_task
    engine._resume_cleanup = ws_mod._cleanup_pipeline
    engine._resume_cancel_event = ws_mod._resume_cancel_event
    engine._resume_live_ectx_register = rc_mod.register_live_ectx
    engine._resume_live_ectx_unregister = rc_mod.unregister_live_ectx
    engine._resume_output_persist_sink = rc_mod.persist_resume_output_columns


def _dump(title, session, run_id, extra=None) -> None:
    from app.models.run_event import RunEvent
    from app.models.workflow import WorkflowRun

    session.expire_all()
    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    evs = session.query(RunEvent).filter(RunEvent.run_id == run_id).order_by(RunEvent.seq.asc()).all()
    emit(f"  {title}")
    emit(f"    workflow_runs.status={row.status!r}  .error={row.error!r}  .completed_at set={row.completed_at is not None}")
    emit("    run_events: " + ", ".join(f"{e.seq}:{e.type}" for e in evs))
    for k, v in (extra or {}).items():
        emit(f"    {k}: {v}")


async def _post_resume_through_endpoint(rc_mod, ws_mod, owner, run_id):
    """Call the REAL endpoint function; return (response, producer-queue items, driver outcome)."""
    from tests.fakes.principal import principal_for

    user = _User(owner)
    resp = await rc_mod.resume_run_endpoint(run_id, auth=(user, principal_for(user)))
    task = ws_mod._PIPELINE_TASKS[run_id]
    queue = ws_mod._PIPELINE_QUEUES[run_id]  # the object an attached SSE client would drain
    await asyncio.wait_for(task, timeout=120)
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return resp, items


@pytest.fixture
def spies(monkeypatch):
    """Count the app-layer failure channel (_flip_back_to_failed) and what resume_run did."""
    import app.api.run_commands as rc_mod

    calls = {"flip_back": [], "resume_run": []}
    orig_flip = rc_mod._flip_back_to_failed

    def _flip(run_id, err):
        calls["flip_back"].append(err)
        return orig_flip(run_id, err)

    monkeypatch.setattr(rc_mod, "_flip_back_to_failed", _flip)
    return calls


def _wrap_resume_run(engine, calls):
    orig = engine.resume_run

    async def _w(run_id):
        try:
            r = await orig(run_id)
            calls["resume_run"].append("returned None normally")
            return r
        except BaseException as exc:  # noqa: BLE001
            calls["resume_run"].append(f"RAISED {type(exc).__name__}: {exc}")
            raise

    engine.resume_run = _w


@pytest.fixture(autouse=True)
def _clean_registries():
    import app.api.run_engine as ws_mod

    for d in (ws_mod._PIPELINE_TASKS, ws_mod._PIPELINE_QUEUES, ws_mod._CANCEL_EVENTS, ws_mod._SUBSCRIBERS):
        d.clear()
    yield
    for d in (ws_mod._PIPELINE_TASKS, ws_mod._PIPELINE_QUEUES, ws_mod._CANCEL_EVENTS, ws_mod._SUBSCRIBERS):
        d.clear()


# ---------------------------------------------------------------------------------------------
# Control: the manifest is VALID -> the real engine drives (proves the harness reaches a dispatch).
# ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_00_control_valid_manifest_reaches_a_dispatch(monkeypatch, spies, caplog):
    import app.api.run_commands as rc_mod
    import app.api.run_engine as ws_mod

    session, db_engine = _make_session()
    run_id, owner, ws = f"c0-{uuid.uuid4().hex[:8]}", "kb102-user", "ws-kb102"
    _seed_workflow_run(session, run_id, owner=owner, status="failed", type_="custom", workspace_id=ws)
    from app.models.workflow import WorkflowRun

    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    row.manifest_json, row.error = _manifest(broken=False), PRIOR_ERROR
    session.commit()
    await _seed_prior_attempt(session, run_id, owner, ws, "failed")

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        _wire_user_resume_drive(monkeypatch, db_engine, engine)
        _arm_like_main_py(engine, ws_mod, rc_mod)
        reached = {"drive": 0}
        orig_drive = engine._drive_resumed_stream

        async def _spy_drive(*a, **k):
            reached["drive"] += 1
            # stop right after proving we got there: do not run agents (no model in this probe)
            return None

        engine._drive_resumed_stream = _spy_drive
        _wrap_resume_run(engine, spies)
        resp, items = await _post_resume_through_endpoint(rc_mod, ws_mod, owner, run_id)
    emit("=== 00 CONTROL: valid composed manifest, real engine, _drive_resumed_stream stubbed to count entry")
    emit(f"  endpoint returned {resp}; _drive_resumed_stream entered {reached['drive']}x (>=1 means resume_run got past every early exit)")
    session.close()
    assert reached["drive"] == 1


# ---------------------------------------------------------------------------------------------
# A. persisted manifest no longer compiles (engine.py:15642-15653) -- failed / cancelled / degraded.
# ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["failed", "cancelled", "degraded"])
async def test_a_persisted_manifest_no_longer_compiles(kind, monkeypatch, spies, caplog):
    import app.api.run_commands as rc_mod
    import app.api.run_engine as ws_mod
    from app.models.workflow import WorkflowRun

    caplog.set_level(logging.WARNING)
    session, db_engine = _make_session()
    run_id, owner, ws = f"a-{kind[:3]}-{uuid.uuid4().hex[:6]}", "kb102-user", "ws-kb102"
    _seed_workflow_run(session, run_id, owner=owner, status=kind, type_="custom", workspace_id=ws)
    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    row.manifest_json, row.error = _manifest(broken=True), PRIOR_ERROR
    session.commit()
    await _seed_prior_attempt(session, run_id, owner, ws, kind)

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        _wire_user_resume_drive(monkeypatch, db_engine, engine)
        _arm_like_main_py(engine, ws_mod, rc_mod)
        _wrap_resume_run(engine, spies)
        emit(f"=== A/{kind}: composed run, status {kind!r}, persisted manifest names an unknown deliverable resolver")
        _dump("BEFORE the click", session, run_id)
        resp, items = await _post_resume_through_endpoint(rc_mod, ws_mod, owner, run_id)
    warn = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING and run_id in r.getMessage()]
    _dump(
        "AFTER the driver task finished",
        session,
        run_id,
        {
            "endpoint response": resp,
            "live queue items an attached client receives": items,
            "engine.resume_run": spies["resume_run"],
            "_flip_back_to_failed calls (the app-layer failure channel)": spies["flip_back"],
            "server log WARNINGs naming the run": warn,
        },
    )
    session.close()
    assert resp == {"run_id": run_id}


# ---------------------------------------------------------------------------------------------
# B1. a pipeline type the entitlement whitelist does not know -> the endpoint refuses LOUDLY (403).
#     This is why the dev-DB runs of type 'user_stories_v2' are NOT an instance of the defect.
# ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b1_retired_pipeline_type_is_refused_at_the_gate(monkeypatch, spies, caplog):
    import app.api.run_commands as rc_mod
    import app.api.run_engine as ws_mod
    from fastapi import HTTPException

    session, db_engine = _make_session()
    run_id, owner, ws = f"b1-{uuid.uuid4().hex[:8]}", "kb102-user", "ws-kb102"
    _seed_workflow_run(session, run_id, owner=owner, status="failed", type_="user_stories_v2", workspace_id=ws)
    await _seed_prior_attempt(session, run_id, owner, ws, "failed")
    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        _wire_user_resume_drive(monkeypatch, db_engine, engine)
        _arm_like_main_py(engine, ws_mod, rc_mod)
        from tests.fakes.principal import principal_for

        user = _User(owner)
        emit("=== B1: run of type 'user_stories_v2' (the id of dev-DB runs 5ab1be23 and 05832e65; no workflow.yaml in any checkout)")
        try:
            await rc_mod.resume_run_endpoint(run_id, auth=(user, principal_for(user)))
            emit("  endpoint ACCEPTED the resume (unexpected)")
        except HTTPException as exc:
            emit(f"  endpoint refused: HTTP {exc.status_code} {exc.detail}")
    session.close()


# ---------------------------------------------------------------------------------------------
# B2. SIMULATED drift for a WHITELISTED type: a deploy drops the manifest, so roster and plan are
#     both unavailable (engine.py:15698/15717/15729).  Not a fault that exists in any checkout today.
# ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b2_simulated_manifest_drift_for_a_whitelisted_type(monkeypatch, spies, caplog):
    import agents.execution_engine.engine as engine_mod
    import agents.registry as registry_mod
    import app.api.run_commands as rc_mod
    import app.api.run_engine as ws_mod

    caplog.set_level(logging.WARNING)
    session, db_engine = _make_session()
    run_id, owner, ws = f"b2-{uuid.uuid4().hex[:8]}", "kb102-user", "ws-kb102"
    _seed_workflow_run(session, run_id, owner=owner, status="failed", type_="prototype", workspace_id=ws)
    from app.models.workflow import WorkflowRun

    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    row.error = PRIOR_ERROR
    session.commit()
    await _seed_prior_attempt(session, run_id, owner, ws, "failed")

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        _wire_user_resume_drive(monkeypatch, db_engine, engine)
        _arm_like_main_py(engine, ws_mod, rc_mod)
        _wrap_resume_run(engine, spies)
        saved = (engine_mod.compile_for_run, registry_mod.get_pipeline_agents)

        def _no_manifest(pt):
            raise FileNotFoundError(f"workflow.yaml not found for {pt!r} (simulated deploy drift)")

        engine_mod.compile_for_run = _no_manifest
        registry_mod.get_pipeline_agents = lambda pt: []
        try:
            emit("=== B2 (SIMULATED drift): whitelisted type 'prototype', roster empty and plan uncompilable")
            _dump("BEFORE the click", session, run_id)
            resp, items = await _post_resume_through_endpoint(rc_mod, ws_mod, owner, run_id)
        finally:
            engine_mod.compile_for_run, registry_mod.get_pipeline_agents = saved
    warn = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING and run_id in r.getMessage()]
    _dump(
        "AFTER the driver task finished",
        session,
        run_id,
        {
            "endpoint response": resp,
            "live queue items an attached client receives": items,
            "engine.resume_run": spies["resume_run"],
            "_flip_back_to_failed calls (the app-layer failure channel)": spies["flip_back"],
            "server log WARNINGs naming the run": warn,
        },
    )
    session.close()
    assert resp == {"run_id": run_id}


# ---------------------------------------------------------------------------------------------
# C. _execute_impl raises before dispatch (sandbox quarantine, engine.py:4503-4511) -> swallowed
#    at engine.py:16030.  C2: the SAME fault through engine.execute() reaches the caller.
# ---------------------------------------------------------------------------------------------
def _quarantine(monkeypatch):
    from app.agents.sandbox import RunSandbox

    monkeypatch.setattr(RunSandbox, "detect_persistent_git_state", lambda self: {"state": "merge_in_progress"}, raising=False)
    monkeypatch.setattr(RunSandbox, "reconcile_persistent_git_state", lambda self, st: "quarantined", raising=False)


@pytest.mark.asyncio
async def test_c_execute_impl_raises_before_dispatch(monkeypatch, spies, caplog):
    import app.api.run_commands as rc_mod
    import app.api.run_engine as ws_mod

    caplog.set_level(logging.WARNING)
    session, db_engine = _make_session()
    run_id, owner, ws = f"c-{uuid.uuid4().hex[:8]}", "kb102-user", "ws-kb102"
    _seed_workflow_run(session, run_id, owner=owner, status="failed", type_=_FIXTURE_ID, workspace_id=ws)
    from app.models.workflow import WorkflowRun

    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    row.error = PRIOR_ERROR
    session.commit()
    await _seed_prior_attempt(session, run_id, owner, ws, "failed")
    _quarantine(monkeypatch)
    # `sample_wave` is a harness fixture type, not in the tier whitelist (B1 shows that gate working);
    # stand it in for an entitled type so the probe reaches the engine.
    monkeypatch.setattr(rc_mod, "_require_tier_entitlement", lambda *a, **k: None)

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        _wire_user_resume_drive(monkeypatch, db_engine, engine)
        _arm_like_main_py(engine, ws_mod, rc_mod)
        _wrap_resume_run(engine, spies)
        emit("=== C: valid registry run (sample_wave), failed; the sandbox reconciles to 'quarantined' -> _execute_impl raises RuntimeError before dispatch")
        _dump("BEFORE the click", session, run_id)
        resp, items = await _post_resume_through_endpoint(rc_mod, ws_mod, owner, run_id)
        warn = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING and run_id in r.getMessage()]
        _dump(
            "AFTER the driver task finished (user resume)",
            session,
            run_id,
            {
                "endpoint response": resp,
                "live queue items an attached client receives": items,
                "engine.resume_run": spies["resume_run"],
                "_flip_back_to_failed calls (the app-layer failure channel)": spies["flip_back"],
                "server log WARNINGs naming the run": warn,
            },
        )

        # C2 -- the same fault on the LAUNCH-side entry point: engine.execute() re-raises, so
        # _drive_launch_to_queue's `except Exception` (run_commands.py:4368-4396) records it.
        run2 = f"c2-{uuid.uuid4().hex[:8]}"
        _seed_workflow_run(session, run2, owner=owner, status="running", type_=_FIXTURE_ID, workspace_id=ws)
        raised = None
        try:
            async for _ in engine.execute(
                agents=list(h.specs), user_message="brief", pipeline_run_id=run2,
                pipeline_type=_FIXTURE_ID, user_id=owner, gate_agent_ids=[],
            ):
                pass
        except Exception as exc:  # noqa: BLE001
            raised = f"{type(exc).__name__}: {exc}"
        emit("  C2 same fault via engine.execute() (what the launch driver wraps):")
        emit(f"    engine.execute raised to its caller: {raised}")
    session.close()
    assert resp == {"run_id": run_id}


# ---------------------------------------------------------------------------------------------
# D. RESTART auto-resume (restore_non_terminal_runs branch b, engine.py:12809-12910): no app wrapper
#    at all, so nothing even reconciles the status.
# ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_d_restart_auto_resume_ghost(monkeypatch, caplog):
    import app.api.run_commands as rc_mod
    import app.api.run_engine as ws_mod
    from app.models.workflow import WorkflowRun

    caplog.set_level(logging.WARNING)
    session, db_engine = _make_session()
    run_id, owner, ws = f"d-{uuid.uuid4().hex[:8]}", "kb102-user", "ws-kb102"
    _seed_workflow_run(session, run_id, owner=owner, status="running", type_="custom", workspace_id=ws)
    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    row.manifest_json = _manifest(broken=True)
    session.commit()
    # a run caught mid-flight by a restart: start + one agent, no terminal event
    from agents.authz import ScopedStore

    store = ScopedStore(owner_id=owner, workspace_id=ws, session=session)
    await store.append_event(run_id, seq=1, event_id="ev-1", type="pipeline_start", payload_json={"pipeline_run_id": run_id})
    await store.append_event(run_id, seq=2, event_id="ev-2", type="agent_start", payload_json={"agent_id": "custom-agent:a"})
    session.commit()

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        _wire_user_resume_drive(monkeypatch, db_engine, engine)
        _arm_like_main_py(engine, ws_mod, rc_mod)
        emit("=== D: backend restart, run left 'running' with durable step state; its persisted manifest no longer compiles")
        _dump("BEFORE the restart scan", session, run_id)
        await engine.restore_non_terminal_runs()
        # let the spawned _admitted_resume task finish
        for _ in range(200):
            await asyncio.sleep(0.05)
            if run_id not in ws_mod._PIPELINE_TASKS or ws_mod._PIPELINE_TASKS[run_id].done():
                break
        await asyncio.sleep(0.2)
    warn = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING and run_id in r.getMessage()]
    _dump("AFTER restore_non_terminal_runs + the auto-resume task finished", session, run_id,
          {"server log WARNINGs naming the run": warn})

    # the NEXT backend restart: the row is still 'running', so it is adopted again
    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h2:
        engine2 = h2.make_engine()
        _wire_user_resume_drive(monkeypatch, db_engine, engine2)
        _arm_like_main_py(engine2, ws_mod, rc_mod)
        await engine2.restore_non_terminal_runs()
        for _ in range(200):
            await asyncio.sleep(0.05)
            if run_id not in ws_mod._PIPELINE_TASKS or ws_mod._PIPELINE_TASKS[run_id].done():
                break
        await asyncio.sleep(0.2)
    _dump("AFTER a SECOND restart scan (next deploy)", session, run_id)
    session.close()


# ---------------------------------------------------------------------------------------------
# G. control: a fault BEFORE the funnel's try (RunTrace construction, engine.py:15922) DOES reach
#    the app-layer failure channel -- the same class of fault is recorded or lost by line number.
# ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_fault_before_the_funnel_try_is_recorded(monkeypatch, spies, caplog):
    import agents.execution_engine.engine as engine_mod
    import app.api.run_commands as rc_mod
    import app.api.run_engine as ws_mod

    caplog.set_level(logging.WARNING)
    session, db_engine = _make_session()
    run_id, owner, ws = f"g-{uuid.uuid4().hex[:8]}", "kb102-user", "ws-kb102"
    _seed_workflow_run(session, run_id, owner=owner, status="failed", type_=_FIXTURE_ID, workspace_id=ws)
    from app.models.workflow import WorkflowRun

    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    row.error = PRIOR_ERROR
    session.commit()
    await _seed_prior_attempt(session, run_id, owner, ws, "failed")
    monkeypatch.setattr(rc_mod, "_require_tier_entitlement", lambda *a, **k: None)

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        _wire_user_resume_drive(monkeypatch, db_engine, engine)
        _arm_like_main_py(engine, ws_mod, rc_mod)
        _wrap_resume_run(engine, spies)
        saved = engine_mod.RunTrace

        def _boom(*a, **k):
            raise RuntimeError("scripted fault in RunTrace(...) construction (engine.py:15922, outside the try)")

        engine_mod.RunTrace = _boom
        try:
            emit("=== G (control): same user resume, but the fault is raised BEFORE _drive_resumed_stream's try block")
            _dump("BEFORE the click", session, run_id)
            resp, items = await _post_resume_through_endpoint(rc_mod, ws_mod, owner, run_id)
        finally:
            engine_mod.RunTrace = saved
    task = ws_mod._PIPELINE_TASKS.get(run_id)
    _dump(
        "AFTER the driver task finished",
        session,
        run_id,
        {
            "endpoint response": resp,
            "live queue items an attached client receives": items,
            "engine.resume_run": spies["resume_run"],
            "_flip_back_to_failed calls (the app-layer failure channel)": spies["flip_back"],
            "registry after the driver is done: driver task still registered / done": (task is not None, task.done() if task else None),
            "registry after the driver is done: live queue still registered": run_id in ws_mod._PIPELINE_QUEUES,
        },
    )
    session.close()
