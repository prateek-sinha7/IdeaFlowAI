"""Scratch observation of the QA-KB-102 fix (outside the suite). Prints final state per scenario."""
import asyncio
import uuid

import tests.integration.agents.test_qa_kb_102_silent_resume as t
from tests.integration.agents.test_restart_resume_db import _make_session, _FIXTURE_ID
import app.api.run_commands as rc_mod
import app.api.run_engine as ws_mod


def _dump(label, session, run_id, items=None):
    from app.models.run_event import RunEvent
    from app.models.workflow import WorkflowRun

    session.expire_all()
    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    evs = session.query(RunEvent).filter(RunEvent.run_id == run_id).order_by(RunEvent.seq).all()
    print(f"\n== {label}: status={row.status!r} error={row.error!r}")
    print("   tail:", [(e.seq, e.type, (e.payload_json or {}).get("error")) for e in evs])
    if items is not None:
        print("   queue:", [None if i is None else (i["type"], i["data"].get("seq"), i["data"].get("error")) for i in items])
    print("   registries: queues=", list(ws_mod._PIPELINE_QUEUES), "tasks=", list(ws_mod._PIPELINE_TASKS))


async def test_observe_a(monkeypatch):
    for prior in ("failed", "cancelled", "degraded"):
        session, db = _make_session()
        rid = f"a-{prior}-{uuid.uuid4().hex[:6]}"
        t._seed_run(session, rid, prior, "custom", t._manifest(broken=True))
        await t._seed_prior(session, rid, "failed" if prior == "cancelled" else prior)
        if prior == "cancelled":
            from agents.authz import ScopedStore
            st = ScopedStore(owner_id=t.OWNER, workspace_id=t.WS, session=session)
            await st.append_event(rid, seq=99, event_id="ev-cx", type="pipeline_cancelled", payload_json={})
            session.commit()
        items = await t._post_resume(monkeypatch, session, db, rid)
        _dump(f"A prior={prior}", session, rid, items)


async def test_observe_c(monkeypatch):
    from app.agents.sandbox import RunSandbox
    session, db = _make_session()
    rid = f"c-{uuid.uuid4().hex[:6]}"
    t._seed_run(session, rid, "failed", _FIXTURE_ID)
    await t._seed_prior(session, rid, "failed")
    monkeypatch.setattr(RunSandbox, "detect_persistent_git_state", lambda self: {"state": "merge_in_progress"}, raising=False)
    monkeypatch.setattr(RunSandbox, "reconcile_persistent_git_state", lambda self, st: "quarantined", raising=False)
    monkeypatch.setattr(rc_mod, "_require_tier_entitlement", lambda *a, **k: None)
    items = await t._post_resume(monkeypatch, session, db, rid)
    _dump("C quarantine", session, rid, items)


async def test_observe_g(monkeypatch):
    import agents.execution_engine.engine as engine_mod
    session, db = _make_session()
    rid = f"g-{uuid.uuid4().hex[:6]}"
    t._seed_run(session, rid, "failed", _FIXTURE_ID)
    await t._seed_prior(session, rid, "failed")
    monkeypatch.setattr(rc_mod, "_require_tier_entitlement", lambda *a, **k: None)

    def _boom(*a, **k):
        raise RuntimeError("scripted fault before the funnel try")

    monkeypatch.setattr(engine_mod, "RunTrace", _boom)
    items = await t._post_resume(monkeypatch, session, db, rid)
    _dump("G pre-funnel", session, rid, items)


async def test_observe_control(monkeypatch):
    session, db = _make_session()
    rid = f"ok-{uuid.uuid4().hex[:6]}"
    t._seed_run(session, rid, "failed", "custom", t._manifest(broken=False))
    await t._seed_prior(session, rid, "failed")
    items = await t._post_resume(monkeypatch, session, db, rid)
    _dump("control valid manifest", session, rid, items)


async def test_observe_d_restart(monkeypatch):
    """Scenario D after the fix: two restart scans of a running composed run whose manifest no longer compiles."""
    from agents.authz import ScopedStore
    from tests.integration.agents.test_restart_resume_db import _ResumeHarness, _wire_user_resume_drive

    session, db = _make_session()
    rid = f"d-{uuid.uuid4().hex[:6]}"
    t._seed_run(session, rid, "running", "custom", t._manifest(broken=True))
    store = ScopedStore(owner_id=t.OWNER, workspace_id=t.WS, session=session)
    await store.append_event(rid, seq=1, event_id="ev-1", type="pipeline_start", payload_json={"pipeline_run_id": rid})
    await store.append_event(rid, seq=2, event_id="ev-2", type="agent_start", payload_json={"agent_id": "custom-agent:a"})
    session.commit()
    for scan in (1, 2):
        with _ResumeHarness(session, {}, fail_on=set(), db_engine=db) as h:
            engine = h.make_engine()
            _wire_user_resume_drive(monkeypatch, db, engine)
            t._arm(engine)
            await engine.restore_non_terminal_runs()
            for _ in range(200):
                await asyncio.sleep(0.05)
                task = ws_mod._PIPELINE_TASKS.get(rid)
                if task is None or task.done():
                    break
            await asyncio.sleep(0.2)
        _dump(f"D restart scan {scan}", session, rid)
