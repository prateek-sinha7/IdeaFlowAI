"""READ-ONLY PROBE (not a product test), QA-KB-100 analysis.

HTTP-level: which override-row WRITE paths accept privileged steps, and what the stored row then
compiles to on the READ path. Harness = the same in-memory SQLite + both routers + principal
override that tests/integration/api/test_workflow_override_e2e_api.py uses. The caller's tier is
set to BASIC (not enterprise) on purpose: `custom` (the Composer's base) is enterprise-only in
app/core/entitlements.py, `ppt` is not.
"""
import copy
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.user_workflows import router as uw_router
from app.api.workflows import router as wf_router, _overridden_plan
from app.api._workflow_override import find_override
from app.core.dependencies import get_current_principal, get_current_user
from app.models.database import Base, get_db
from tests.fakes.principal import principal_for
from agents.execution_engine.engine import compile_for_run


class _FakeUser:
    def __init__(self, id, tier):
        self.id = id
        self.tier = tier


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    app = FastAPI()
    app.include_router(wf_router)
    app.include_router(uw_router)
    state = {"user": _FakeUser("owner", "basic")}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    app.dependency_overrides[get_current_principal] = lambda: (state["user"], principal_for(state["user"]))

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        yield TestClient(app), state, session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _step(iid="mine", **over):
    s = {"agent": "custom-agent", "instance_id": iid, "name": iid, "prompt": f"You are {iid}.",
         "tools": {"read_files": False, "write_files": False, "exec": False}}
    s.update(over)
    return s


EXEC = _step("mine", gates=["security", "approval"],
             tools={"read_files": True, "write_files": True, "exec": True}, validators=["code_test"])
SPAWN = _step("mine", tools={"read_files": True, "write_files": True, "exec": False, "spawn_subagents": True})


def _post(client, steps, base="ppt", over="ppt", name="My Deck"):
    body = {"name": name, "base_pipeline_type": base, "agent_ids": ["ppt-brief-analyst"],
            "manifest": {"steps": steps}}
    if over:
        body["overrides_pipeline_type"] = over
    return client.post("/api/user-workflows", json=body)


def _eff(plan):
    out = []
    for s in plan.steps:
        t = s.tools
        out.append(f"{s.agent_id}: exec={t.exec} spawn={t.spawn_subagents} gates={list(s.gates)} validators={list(s.validators)}")
    return out


def test_probe_write_paths_as_basic_tier(api):
    client, state, session = api
    print()
    print("caller tier:", state["user"].tier)

    # --- tier asymmetry: the Composer (base `custom`) is enterprise-only; an override of ppt is not
    r = _post(client, [_step("c")], base="custom", over=None, name="Composer")
    print(f"[W0] POST Composer row (base_pipeline_type=custom, no override) as BASIC -> {r.status_code}")

    # --- W1: POST insert
    r = _post(client, [copy.deepcopy(EXEC)])
    print(f"[W1] POST override insert, exec grant + gates security,approval + validators code_test -> {r.status_code}")
    row = find_override(session, state["user"], "ppt")
    plan = _overridden_plan(compile_for_run("ppt"), row)
    print("     served/launched plan steps:", _eff(plan))
    d = client.get("/api/workflows/ppt").json()
    print(f"     GET /api/workflows/ppt -> is_overridden={d['is_overridden']} steps.gates={[s['gates'] for s in d['steps']]} "
          f"manifest_steps.gates={[s.get('gates') for s in (d['manifest_steps'] or [])]}")

    # --- W2: POST upsert (second save of the same built-in) with spawn_subagents
    r = _post(client, [copy.deepcopy(SPAWN)])
    print(f"[W2] POST override UPSERT (same built-in), spawn_subagents grant -> {r.status_code}")
    session.expire_all()
    row = find_override(session, state["user"], "ppt")
    print("     plan:", _eff(_overridden_plan(compile_for_run("ppt"), row)))

    # --- W3: PATCH manifest on a benign override row
    client.delete(f"/api/user-workflows/{row.id}")
    r = _post(client, [_step("benign")])
    rid = r.json()["id"]
    print(f"[W3a] POST benign override -> {r.status_code}")
    r = client.patch(f"/api/user-workflows/{rid}", json={"manifest": {"steps": [copy.deepcopy(EXEC)]}})
    print(f"[W3b] PATCH that row's manifest to the exec step -> {r.status_code}")
    session.expire_all()
    row = find_override(session, state["user"], "ppt")
    print("     plan:", _eff(_overridden_plan(compile_for_run("ppt"), row)))

    # --- W4: sync-from-file on the override row, from a file workflow whose steps are privileged
    r = client.patch(f"/api/user-workflows/{rid}", json={"manifest": {"steps": [_step("benign")]}})
    r = client.post(f"/api/user-workflows/{rid}/sync-from-file", json={"pipeline_type": "sample_subagents_parallel"})
    print(f"[W4] POST sync-from-file(pipeline_type=sample_subagents_parallel) on the ppt override row -> {r.status_code} {str(r.json())[:120]}")
    session.expire_all()
    row = find_override(session, state["user"], "ppt")
    plan = _overridden_plan(compile_for_run("ppt"), row)
    print("     plan:", _eff(plan))
    d = client.get("/api/workflows/ppt").json()
    print(f"     GET /api/workflows/ppt -> is_overridden={d['is_overridden']} n_steps={len(d['steps'])} n_manifest_steps={len(d['manifest_steps'] or [])}")


def test_probe_non_override_manifest_row_as_basic_tier(api):
    """The same exposure WITHOUT overrides_pipeline_type: a manifest-backed saved row whose
    base_pipeline_type is `ppt` (basic may run it) instead of `custom` (enterprise-only)."""
    client, state, session = api
    print()
    print("caller tier:", state["user"].tier)
    r = _post(client, [copy.deepcopy(EXEC)], base="ppt", over=None, name="Plain row, base ppt")
    print(f"[W5] POST manifest-backed row, base_pipeline_type=ppt, NO overrides_pipeline_type, exec step -> {r.status_code}")
    rid = r.json().get("id")
    from app.models.workflow_definition import WorkflowDefinition
    row = session.get(WorkflowDefinition, rid)
    print("     stored: base_pipeline_type=%s overrides_pipeline_type=%s manifest.steps[0].tools.exec=%s gates=%s"
          % (row.base_pipeline_type, row.overrides_pipeline_type,
             row.manifest_json["steps"][0]["tools"]["exec"], row.manifest_json["steps"][0]["gates"]))
    # What launch_run Case 3 does with that row (run_commands.py:3345-3391), minus the HTTP layer:
    from agents.execution_engine.engine import _CAPABILITY_REGISTRY, _WORKFLOW_COMPILER
    from agents.workflows.manifest import build_manifest_from_dict
    raw = dict(row.manifest_json)
    raw.setdefault("id", f"user-workflow-{row.id}")
    raw["deliverable"] = {"strategy": "streamed_text", "name": "output.md"}
    raw["planner"] = "skip"
    raw["clarify"] = {"mode": "skip", "defaults": []}
    raw["capabilities"] = {}
    parsed = build_manifest_from_dict(raw, f"workflow:{row.id}")
    compiled = _WORKFLOW_COMPILER.compile(parsed, _CAPABILITY_REGISTRY, trust="db")
    print("     launch Case 3 compile (trust=db):", _eff(compiled))
    from app.core.entitlements import can_run_pipeline
    print("     launch tier gate keys on pipeline_type=%r -> can_run_pipeline(basic, ppt)=%s ; (basic, custom)=%s"
          % (row.base_pipeline_type, can_run_pipeline("basic", row.base_pipeline_type)[0], can_run_pipeline("basic", "custom")[0]))
