"""tail x variant matrix for _reconcile_terminal_status, run through the repo's own test harness.

Safety: DATABASE_URL is pinned to a throwaway SQLite file BEFORE any `app` import (mirrors
tests/conftest.py), so nothing can bind the developer's Postgres. Nothing under backend/ is written.
"""
import os, sys, tempfile, asyncio, uuid, ast, logging
_tmp = tempfile.mkdtemp(prefix="qakb036-")
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
TAILS = {  # name: (tail, what the LATEST ATTEMPT actually did)
 "T1 degraded -> clean resume":            ([("pipeline_start",1,{}),("pipeline_complete",2,DEG),("run_resuming",3,{}),("pipeline_start",4,{}),("pipeline_complete",5,{})], "completed"),
 "T2 clean -> degraded resume":            ([("pipeline_start",1,{}),("pipeline_complete",2,{}),("run_resuming",3,{}),("pipeline_start",4,{}),("pipeline_complete",5,DEG)], "degraded"),
 "T3 degraded only":                       ([("pipeline_start",1,{}),("pipeline_complete",2,DEG)], "degraded"),
 "T4 no completion at all":                ([("pipeline_start",1,{}),("agent_start",2,{})], "failed"),
 "T5 ISS-436: degraded -> resume FAILS":   ([("pipeline_start",1,{}),("pipeline_complete",2,DEG),("run_resuming",3,{}),("pipeline_start",4,{}),("agent_error",5,{"error":"boom"}),("pipeline_failed",6,{"error":"boom"})], "failed"),
 "T6 ISS-437: failed -> clean resume":     ([("pipeline_start",1,{}),("pipeline_failed",2,{"error":"old"}),("run_resuming",3,{}),("pipeline_start",4,{}),("pipeline_complete",5,{})], "completed"),
 "T7 ISS-435: cancelled -> degraded":      ([("pipeline_start",1,{}),("pipeline_cancelled",2,{}),("run_resuming",3,{}),("pipeline_start",4,{}),("pipeline_complete",5,DEG)], "degraded"),
}
ORIG = rc._reconcile_terminal_status

def install(path):
    if path == "head":
        rc._reconcile_terminal_status = ORIG; return
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
    out = (row.status, row.error); session.close(); mp.undo(); return out

variants = [("head", "head"), ("narrow", f"{SP}/narrow.py"), ("agreed", f"{SP}/agreed.py"), ("opt2", f"{SP}/opt2.py"), ("opt3", f"{SP}/opt3.py")]
res = {}
for vname, vpath in variants:
    install(vpath)
    for tname, (tail, _) in TAILS.items():
        res[(vname, tname)] = asyncio.run(one(tail))
print(f"{'tail':<40}{'truth':<11}" + "".join(f"{v:<12}" for v, _ in variants))
for tname, (_, truth) in TAILS.items():
    cells = "".join(f"{res[(v, tname)][0]:<12}" for v, _ in variants)
    print(f"{tname:<40}{truth:<11}{cells}")
print("\nerror column for the degraded verdicts (head vs narrow must match):")
for tname in ("T2 clean -> degraded resume", "T3 degraded only"):
    print(f"  {tname:<32} head={res[('head',tname)][1]!r}  narrow={res[('narrow',tname)][1]!r}  agreed={res[('agreed',tname)][1]!r}")
