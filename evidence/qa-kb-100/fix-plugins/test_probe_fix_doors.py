"""PROBE (not a product test), QA-KB-100 fix stage.

Checks the doors no red test reaches, plus the controls that must NOT change:

  F1  PATCH a benign override row to the exec step                  -> 422 (ISS-1112)
  F2  sync-from-file sample_subagents_parallel INTO the override row -> 422 (ISS-1112)
  F3  sync-from-file ppt into the override row (ppt's own steps)     -> 200 (control)
  F4  benign override and a gates:[human] override                   -> 201 and applied (control)
  F5  enterprise Composer row (base custom, no override) w/ security -> 201 (control: ADR-0039 unchanged)
  F6  trigger door (run_trigger_workflow) on an override row         -> compile trust "user" (ISS-1113)
  F7  trigger door on a plain saved row                              -> compile trust "db" (control)
  F8  launch_run Case 3 on a plain saved row                         -> compile trust "db" (control)

Harness: in-memory SQLite + both routers + principal override, as
tests/integration/api/test_workflow_override_e2e_api.py and the analyzer's probe.
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.user_workflows import router as uw_router
from app.api.workflows import router as wf_router
from app.core.dependencies import get_current_principal, get_current_user
from app.models.database import Base, get_db
from tests.fakes.principal import principal_for


class _FakeUser:
    def __init__(self, id, tier):
        self.id = id
        self.tier = tier


def _step(iid="mine", **over):
    s = {"agent": "custom-agent", "instance_id": iid, "name": iid, "prompt": f"You are {iid}.",
         "tools": {"read_files": False, "write_files": False, "exec": False}}
    s.update(over)
    return s


EXEC = _step("mine", gates=["security", "approval"],
             tools={"read_files": True, "write_files": True, "exec": True}, validators=["code_test"])


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    try:
        yield Session
    finally:
        Base.metadata.drop_all(bind=engine)


def _client(Session, tier):
    session = Session()
    app = FastAPI()
    app.include_router(wf_router)
    app.include_router(uw_router)
    user = _FakeUser("owner", tier)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_principal] = lambda: (user, principal_for(user))
    app.dependency_overrides[get_db] = lambda: (yield session)
    return TestClient(app)


def _post(client, steps, base="ppt", over="ppt", name="My Deck"):
    body = {"name": name, "base_pipeline_type": base, "agent_ids": ["ppt-brief-analyst"],
            "manifest": {"steps": steps}}
    if over:
        body["overrides_pipeline_type"] = over
    return client.post("/api/user-workflows", json=body)


def test_probe_writers_and_controls(db):
    print()
    c = _client(db, "basic")
    r = _post(c, [_step("benign")])
    rid = r.json()["id"]
    print(f"[F4a] POST benign override (basic) -> {r.status_code}")
    d = c.get("/api/workflows/ppt").json()
    print(f"      GET /api/workflows/ppt -> is_overridden={d['is_overridden']} steps={[s['agent_id'] for s in d['steps']]}")

    r = c.patch(f"/api/user-workflows/{rid}", json={"manifest": {"steps": [EXEC]}})
    print(f"[F1]  PATCH that override to the exec step -> {r.status_code} {str(r.json().get('detail'))[:150]}")

    r = c.post(f"/api/user-workflows/{rid}/sync-from-file", json={"pipeline_type": "sample_subagents_parallel"})
    print(f"[F2]  sync-from-file(sample_subagents_parallel) into the ppt override -> {r.status_code} {str(r.json().get('detail'))[:150]}")

    r = c.post(f"/api/user-workflows/{rid}/sync-from-file", json={"pipeline_type": "ppt"})
    print(f"[F3]  sync-from-file(ppt) into the ppt override -> {r.status_code}")
    d = c.get("/api/workflows/ppt").json()
    print(f"      GET /api/workflows/ppt -> is_overridden={d['is_overridden']} steps={[s['agent_id'] for s in d['steps']]}")

    r = _post(c, [_step("reviewer", gates=["human"])])
    print(f"[F4b] POST override upsert, gates:[human] -> {r.status_code}")
    d = c.get("/api/workflows/ppt").json()
    print(f"      GET /api/workflows/ppt -> steps={[s['agent_id'] for s in d['steps']]} gates={[s['gates'] for s in d['steps']]}")

    e = _client(db, "enterprise")
    r = _post(e, [_step("c", gates=["security"])], base="custom", over=None, name="Composer row")
    print(f"[F5]  POST Composer row (enterprise, base custom, no override) with gates:[security] -> {r.status_code}")


def _row(Session, rid, over):
    from app.models.workflow_definition import WorkflowDefinition

    s = Session()
    s.add(WorkflowDefinition(
        id=rid, user_id="owner", name=rid, agents="[]", artifact_edges="[]", source="user",
        base_pipeline_type="ppt", overrides_pipeline_type=over, override_enabled=bool(over),
        manifest_json={"steps": [_step("mine", gates=["security"])]},
    ))
    s.commit()
    s.close()


def test_probe_trigger_and_case3_trust(db, monkeypatch):
    print()
    import app.api.run_commands as rc
    import app.api.run_engine as run_engine
    from agents.execution_engine.kernel_services import KernelServices
    from agents.workflows.compiler import CompilerError, WorkflowCompiler

    _row(db, "ovr-1", "ppt")
    _row(db, "plain-1", None)
    monkeypatch.setattr(run_engine, "_get_db", lambda: db())
    monkeypatch.setattr(rc, "_get_db", lambda: db())

    seen = []

    def fake_compile(self, parsed, registry, trust="file"):
        seen.append(trust)
        raise CompilerError("probe: stop before mint")

    monkeypatch.setattr(WorkflowCompiler, "compile", fake_compile)

    ks = KernelServices.__new__(KernelServices)
    ectx = SimpleNamespace(run_id="r0", owner_id="owner", workspace_id="owner", trigger_depth=0)
    for label, rid in (("F6", "ovr-1"), ("F7", "plain-1")):
        seen.clear()
        with pytest.raises(CompilerError):
            asyncio.run(ks.run_trigger_workflow(None, ectx, workflow_ref=rid))
        print(f"[{label}]  run_trigger_workflow(workflow_ref={rid!r}) compiled at trust={seen}")

    user = _FakeUser("owner", "basic")
    app = FastAPI()
    app.include_router(rc.router)
    app.dependency_overrides[get_current_principal] = lambda: (user, principal_for(user))
    for label, rid in (("F8", "plain-1"), ("F8b", "ovr-1")):
        seen.clear()
        r = TestClient(app).post("/api/runs", json={"message": "go", "pipeline_type": "ppt", "user_workflow_id": rid})
        print(f"[{label}]  POST /api/runs user_workflow_id={rid!r} -> {r.status_code}, Case 3 compiled at trust={seen}")
