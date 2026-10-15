"""QA-KB-075: tail x variant matrix for _reconcile_terminal_status through the repo's own test harness.

DATABASE_URL is pinned to a throwaway SQLite file BEFORE any `app` import (mirrors tests/conftest.py:87-88), so nothing can
bind the developer's Postgres. Nothing under backend/ is written. Run from backend/: SP=<dir> .venv/bin/python <this file>
"""
import os, sys, tempfile, asyncio, uuid, ast, logging

_tmp = tempfile.mkdtemp(prefix="qakb075-")
os.environ.pop("PYTEST_DATABASE_URL", None)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/m.db"
sys.path.insert(0, os.getcwd())
logging.disable(logging.CRITICAL)

import app.models  # noqa: F401  registers models
from app.models.database import Base, engine

Base.metadata.create_all(bind=engine)
import app.api.run_commands as rc
from tests.integration.agents.test_restart_resume_db import (
    _make_session, _seed_workflow_run, _ResumeHarness, _wire_user_resume_drive)
from _pytest.monkeypatch import MonkeyPatch
from agents.authz import ScopedStore
from app.models.workflow import WorkflowRun

SP = os.environ["SP"]
DEG = {"status": "degraded", "agents_failed": ["x"], "degraded_reason": "x failed"}
S, C, RR, F = "pipeline_start", "pipeline_complete", "run_resuming", "pipeline_failed"
TAILS = {  # name: (tail, verdict the LIVE FIX-484 rule gives = what the latest ATTEMPT actually did)
 "T1 degraded -> clean resume (test tail 1)":      ([(S,1,{}),(C,2,DEG),(RR,3,{}),(S,4,{}),(C,5,{})], "completed"),
 "T2 clean -> degraded resume (test tail 2)":      ([(S,1,{}),(C,2,{}),(RR,3,{}),(S,4,{}),(C,5,DEG)], "degraded"),
 "T3 degraded only (test tail 3)":                 ([(S,1,{}),(C,2,DEG)], "degraded"),
 "T4 no completion at all (test tail 4)":          ([(S,1,{}),("agent_start",2,{"agent_id":"w"})], "failed"),
 "T5 degraded -> resume FAILS (ISS-436 lock)":     ([(S,1,{}),(C,2,DEG),(RR,3,{}),(S,4,{}),("agent_error",5,{"error":"boom"}),(F,6,{})], "failed"),
 "T6 failed -> clean resume (ISS-437 lock)":       ([(S,1,{}),(F,2,{}),(RR,3,{}),(S,4,{}),(C,5,{})], "completed"),
 "T8 degraded -> resume cut off, no terminal":     ([(S,1,{}),(C,2,DEG),(RR,3,{}),(S,4,{}),("agent_start",5,{"agent_id":"w"})], "failed"),
 "T9 clean -> resume cut off, no terminal":        ([(S,1,{}),(C,2,{}),(RR,3,{}),(S,4,{}),("agent_start",5,{"agent_id":"w"})], "failed"),
}
ORIG = rc._reconcile_terminal_status


def install(path):
    if path == "head":
        rc._reconcile_terminal_status = ORIG
        return
    tree = ast.parse(open(path).read())
    fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_reconcile_terminal_status")
    exec(compile(ast.Module(body=[fn], type_ignores=[]), path, "exec"), rc.__dict__)


async def one(tail):
    mp = MonkeyPatch()
    session, db_engine = _make_session()
    run_id = f"mx-{uuid.uuid4().hex[:8]}"; owner, ws = "mx-user", "ws-mx"
    _seed_workflow_run(session, run_id, owner=owner, status="generating", workspace_id=ws)
    store = ScopedStore(owner_id=owner, workspace_id=ws, session=session)
    for t, seq, payload in tail:
        await store.append_event(run_id, seq=seq, event_id=f"mx-{seq}", type=t, payload_json=payload)
    session.commit()
    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        rcm = _wire_user_resume_drive(mp, db_engine, h.make_engine())
        await rcm._reconcile_terminal_status(run_id)
    session.expire_all()
    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    out = row.status; session.close(); mp.undo(); return out


variants = [("head", "head"), ("opt2", f"{SP}/opt2.py"), ("opt4", f"{SP}/opt4.py")]
res = {}
for vname, vpath in variants:
    install(vpath)
    for tname, (tail, _) in TAILS.items():
        res[(vname, tname)] = asyncio.run(one(tail))
print(f"{'tail':<48}{'live rule':<11}" + "".join(f"{v:<11}" for v, _ in variants))
for tname, (_, truth) in TAILS.items():
    print(f"{tname:<48}{truth:<11}" + "".join(f"{res[(v, tname)]:<11}" for v, _ in variants))
