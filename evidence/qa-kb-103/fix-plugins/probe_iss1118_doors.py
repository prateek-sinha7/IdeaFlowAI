"""Probe the three doors outside compile_override_steps (ISS-1118 item 3 / ISS-1129).

Case 3 (POST /api/runs with user_workflow_id), the route trigger, and the resume
recompile. _launch_run_core is replaced, so no run is minted and no model is called.
DATABASE_URL is forced to in-memory sqlite by the caller. Not a test file.
"""
import asyncio
import copy
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.run_commands as rc
import app.api.run_engine as run_engine
from agents.workflows.compiler import CompilerError
from agents.workflows.manifest import build_manifest_from_dict, load_manifest
from app.core.dependencies import get_current_principal
from app.models.database import Base
from app.models.workflow_definition import WorkflowDefinition
from tests.fakes.principal import principal_for

db = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(bind=db)
Session = sessionmaker(bind=db, autocommit=False, autoflush=False)

proto = copy.deepcopy(list(load_manifest("prototype", Path("agents/workflows")).steps))
added = copy.deepcopy(proto)
added[0]["compaction"] = "html_skeleton"  # prototype-specify declares none in the file


def seed(rid, steps, overrides, owner="owner"):
    s = Session()
    s.add(WorkflowDefinition(
        id=rid, user_id=owner, owner_id=owner, workspace_id=owner, name=rid,
        agents="[]", artifact_edges="[]", source="user", base_pipeline_type="prototype",
        overrides_pipeline_type=overrides, override_enabled=bool(overrides),
        manifest_json={"steps": copy.deepcopy(steps)},
    ))
    s.commit()
    s.close()


seed("ovr-proto", proto, "prototype")   # unchanged override
seed("ovr-added", added, "prototype", owner="owner2")   # user ADDED a reference -> must stay refused
seed("plain-proto", proto, None)        # not an override -> trust db, unchanged path

captured = {}


async def fake_core(**kw):
    captured.clear()
    captured.update(kw)
    return {"run_id": "probe-run", "pipeline_type": kw.get("pipeline_type")}


rc._launch_run_core = fake_core
rc._get_db = lambda: Session()
run_engine._get_db = lambda: Session()


def comp(c):
    return {s.agent_id: s.compaction for s in c.steps if s.compaction}


# ── Case 3: launch by user_workflow_id ────────────────────────────────────────
class U:
    tier, preferred_model = "enterprise", None

    def __init__(self, id):
        self.id = id


app = FastAPI()
app.include_router(rc.router)
client = TestClient(app)
OWNER = {"ovr-proto": "owner", "ovr-added": "owner2", "plain-proto": "owner"}
for rid in ("ovr-proto", "ovr-added", "plain-proto"):
    app.dependency_overrides[get_current_principal] = lambda o=OWNER[rid]: (U(o), principal_for(U(o)))
    captured.clear()
    r = client.post("/api/runs", json={"message": "go", "pipeline_type": "prototype", "user_workflow_id": rid})
    if captured.get("compiled") is not None:
        mf = captured.get("manifest_json") or {}
        print(f"CASE3   {rid}: {r.status_code} reached mint; compaction={comp(captured['compiled'])} "
              f"persisted _trust={mf.get('_trust')} _overrides={mf.get('_overrides')}")
        if rid == "ovr-proto":
            persisted = copy.deepcopy(mf)
    else:
        print(f"CASE3   {rid}: {r.status_code} {r.text[:170]}")

# ── the route trigger (KernelServices.run_trigger_workflow, user-row branch) ──
from agents.execution_engine.kernel_services import KernelServices

ks = KernelServices.__new__(KernelServices)
ectx = SimpleNamespace(owner_id="owner", run_id="parent-run", workspace_id="owner", trigger_depth=0)
for rid in ("ovr-proto", "ovr-added"):
    captured.clear()
    ectx.owner_id = ectx.workspace_id = OWNER[rid]
    try:
        asyncio.run(ks.run_trigger_workflow(None, ectx, workflow_ref=rid))
        print(f"TRIGGER {rid}: reached mint; compaction={comp(captured['compiled'])}")
    except CompilerError as e:
        print(f"TRIGGER {rid}: CompilerError {str(e)[:120]}")

# ── resume: the exact recompile block, on what Case 3 persisted ───────────────
from agents.capabilities.registry import CapabilityRegistry, discover
from agents.execution_engine.overrides import compile_with_baseline

for label, mf in (("with _overrides", persisted), ("pre-fix row (no _overrides)", {k: v for k, v in persisted.items() if k != "_overrides"})):
    _mf = dict(mf)
    _trust = _mf.pop("_trust", "user") or "user"
    _overrides = _mf.pop("_overrides", None)
    discover()
    try:
        c = compile_with_baseline(build_manifest_from_dict(_mf, "run:probe"), CapabilityRegistry(), trust=_trust, overrides=_overrides)
        print(f"RESUME  {label}: compiles; compaction={comp(c)}")
    except CompilerError as e:
        print(f"RESUME  {label}: CompilerError {str(e)[:110]}")

# ── ISS-1130 pin: an INLINE manifest has no baseline and must stay refused ─────
app.dependency_overrides[get_current_principal] = lambda: (U("owner"), principal_for(U("owner")))
captured.clear()
r = client.post("/api/runs", json={"message": "go", "pipeline_type": "custom", "manifest": {"steps": copy.deepcopy(proto)}})
print(f"INLINE  prototype steps: {r.status_code} minted={bool(captured)} {r.text[:120]}")
