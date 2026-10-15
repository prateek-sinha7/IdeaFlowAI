"""PROBE (not a product test), QA-KB-104 fix, 5-fixer 2026-10-09.

Covers the doors the card's test file does not drive, after the ISS-1117/ISS-1131 change:
  W. _trigger_entitlement_error directly: nested subagents, the pass-through targets
     (self, a saved-row id, a supported type with no workflow.yaml, trigger: step), malformed
     shapes, the two real file workflows that trigger (ex_A3_divert, ex_A4_human_divert), and
     the full tier x file-backed-target matrix against can_run_pipeline.
  P. PATCH /api/user-workflows/{id} with a manifest that triggers an unentitled pipeline.
  L. POST /api/runs: inline manifest, enabled override row, enterprise control, with
     _launch_run_core STUBBED (nothing minted, nothing spent).
  R. POST /api/runs/{id}/resume with a persisted manifest that triggers an unentitled pipeline,
     with the engine singleton STUBBED (nothing driven).

In-memory SQLite only. Prints each observation and asserts it.
"""
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import agents.execution_engine.engine as engine_mod
import app.api.run_commands as rc
import app.api.run_engine as re_mod
import app.models.artifact_ref  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
from agents.execution_engine.kernel_services import _is_file_backed_workflow
from agents.loader import SUPPORTED_PIPELINE_TYPES
from app.api.run_engine import _trigger_entitlement_error
from app.api.user_workflows import _load_file_manifest_dict
from app.api.user_workflows import router as uw_router
from app.core.dependencies import get_current_principal, get_current_user
from app.core.entitlements import TIER_PIPELINES, can_run_pipeline
from app.models.database import Base, get_db
from app.models.workflow import WorkflowRun
from app.models.workflow_definition import WorkflowDefinition
from tests.fakes.principal import principal_for


class _FakeUser:
    def __init__(self, id, tier):
        self.id = id
        self.tier = tier
        self.preferred_model = None


def _gate(target, trigger="workflow"):
    return {
        "agent": "custom-agent", "instance_id": "language", "name": "Pick Language",
        "produces": ["route_decision"], "prompt": 'Reply {"decision": "spanish"}', "gates": ["conditional"],
        "route": {"outcomes": {"spanish": {"trigger": trigger, "target": target, "feedback": "go"}},
                  "trigger_max_depth": 5},
        "tools": {"read_files": False, "write_files": False, "exec": False},
    }


def _plain(iid="emoji"):
    return {"agent": "custom-agent", "instance_id": iid, "name": iid, "prompt": f"You are {iid}.",
            "tools": {"read_files": False, "write_files": False, "exec": False}}


def _steps(target):
    return [_plain(), _gate(target)]


# ---------------------------------------------------------------- W: the walker itself

def test_W_walker():
    print()
    cases = [
        ("W1 top-level trigger app_builder", "basic", {"steps": _steps("app_builder")}),
        ("W2 nested subagents child triggers app_builder", "basic",
         {"steps": [{**_plain("parent"), "subagents": {"mode": "sequential",
                                                       "steps": [_plain("kid"), _gate("app_builder")]}}]}),
        ("W3 target self", "basic", {"steps": _steps("self")}),
        ("W4 target a saved-row id", "basic", {"steps": _steps(str(uuid.uuid4()))}),
        ("W5 target spec_kit (supported, no workflow.yaml)", "basic", {"steps": _steps("spec_kit")}),
        ("W6 trigger: step", "basic", {"steps": [_plain(), _gate("emoji", trigger="step")]}),
        ("W7a None", "basic", None),
        ("W7b {}", "basic", {}),
        ("W7c steps None", "basic", {"steps": None}),
        ("W7d steps a string", "basic", {"steps": "x"}),
        ("W7e junk entries", "basic", {"steps": [1, "a", {"route": "x"}, {"route": {"outcomes": [1]}}]}),
    ]
    expect = {"W1": 403, "W2": 403}
    for label, tier, manifest in cases:
        got = _trigger_entitlement_error(tier, manifest)
        print(f"[{label}] tier={tier} -> {got}")
        assert (got[0] if got else None) == expect.get(label.split()[0])
    print(f"    _is_file_backed_workflow('spec_kit')={_is_file_backed_workflow('spec_kit')} "
          f"'spec_kit' in SUPPORTED={'spec_kit' in SUPPORTED_PIPELINE_TYPES}")

    for wf in ("ex_A3_divert", "ex_A4_human_divert"):
        m = _load_file_manifest_dict(wf)
        for tier in ("enterprise", "pro", "basic"):
            got = _trigger_entitlement_error(tier, m)
            print(f"[W8 real file manifest {wf}] tier={tier} -> {got}")
            assert (got is None) == (tier == "enterprise")

    file_backed = sorted(t for t in SUPPORTED_PIPELINE_TYPES if _is_file_backed_workflow(t))
    mismatches = 0
    for tier in TIER_PIPELINES:
        refused = 0
        for target in file_backed:
            got = _trigger_entitlement_error(tier, {"steps": _steps(target)})
            if (got is None) != can_run_pipeline(tier, target)[0]:
                mismatches += 1
            refused += got is not None
        print(f"[W9 matrix] tier={tier}: {refused} of {len(file_backed)} file-backed targets refused "
              f"({len(file_backed) - refused} entitled)")
    print(f"[W9 matrix] mismatches vs can_run_pipeline: {mismatches}")
    assert mismatches == 0


# ---------------------------------------------------------------- shared HTTP world

def _world(tier, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    user = _FakeUser("owner", tier)
    app = FastAPI()
    app.include_router(uw_router)
    app.include_router(rc.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_principal] = lambda: (user, principal_for(user))

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(rc, "_get_db", lambda: session, raising=False)
    monkeypatch.setattr(re_mod, "_get_db", lambda: session, raising=False)
    monkeypatch.setattr(session, "close", lambda: None)
    seen = {}

    async def fake_core(**kw):
        seen.update(kw)
        return {"run_id": "STUB-NOT-MINTED"}

    monkeypatch.setattr(rc, "_launch_run_core", fake_core)
    return TestClient(app), session, seen


def _row(session, rid, base, steps, override_of=None):
    session.add(WorkflowDefinition(
        id=rid, user_id="owner", owner_id="owner", workspace_id="owner", name=rid, agents="[]",
        artifact_edges="[]", source="user", base_pipeline_type=base,
        overrides_pipeline_type=override_of, override_enabled=bool(override_of),
        manifest_json={"steps": steps}))
    session.commit()


# ---------------------------------------------------------------- P: PATCH

def test_P_patch(monkeypatch):
    print()
    client, session, _ = _world("basic", monkeypatch)
    _row(session, "r1", "ppt", [_plain()])
    before = session.get(WorkflowDefinition, "r1").manifest_json
    r = client.patch("/api/user-workflows/r1", json={"manifest": {"steps": _steps("app_builder")}})
    session.expire_all()
    after = session.get(WorkflowDefinition, "r1").manifest_json
    print(f"[P1] basic PATCH manifest triggering app_builder -> {r.status_code} {r.json()} "
          f"row unchanged={after == before}")
    assert r.status_code == 403 and after == before
    r = client.patch("/api/user-workflows/r1", json={"manifest": {"steps": _steps("ppt")}})
    print(f"[P2] basic PATCH manifest triggering ppt (control) -> {r.status_code}")
    assert r.status_code == 200


# ---------------------------------------------------------------- L: launch

def _launch(client, **body):
    return client.post("/api/runs", json={"message": "go", **body})


def test_L_launch(monkeypatch):
    print()
    client, session, seen = _world("basic", monkeypatch)
    r = _launch(client, pipeline_type="ppt", manifest={"steps": _steps("app_builder")})
    print(f"[L1] basic inline manifest triggering app_builder -> {r.status_code} {r.json()} core reached={bool(seen)}")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "tier_not_entitled" and not seen
    r = _launch(client, pipeline_type="ppt", manifest={"steps": _steps("ppt")})
    print(f"[L2] basic inline manifest triggering ppt (control) -> {r.status_code} core reached={bool(seen)}")
    assert r.status_code == 200 and seen
    seen.clear()
    _row(session, "ok", "ppt", _steps("ppt"))
    r = _launch(client, pipeline_type="ppt", user_workflow_id="ok")
    print(f"[L3] basic stored row triggering ppt (control) -> {r.status_code} core reached={bool(seen)}")
    assert r.status_code == 200 and seen
    seen.clear()
    _row(session, "ov", "ppt", _steps("app_builder"), override_of="ppt")
    r = _launch(client, pipeline_type="ppt")
    print(f"[L4] basic launches built-in ppt with an ENABLED override whose steps trigger app_builder "
          f"-> {r.status_code} {r.json()} core reached={bool(seen)}")
    assert r.status_code == 403 and not seen


def test_L_enterprise_control(monkeypatch):
    print()
    client, session, seen = _world("enterprise", monkeypatch)
    _row(session, "hop", "ppt", _steps("app_builder"))
    r = _launch(client, pipeline_type="ppt", user_workflow_id="hop")
    print(f"[L5] enterprise stored row triggering app_builder (control) -> {r.status_code} core reached={bool(seen)}")
    assert r.status_code == 200 and seen


# ---------------------------------------------------------------- R: resume

class _StubEngine:
    def __init__(self):
        self.resume_calls = []

    async def _stamp_resume_marker(self, wr):
        return None

    async def resume_run(self, run_id):
        self.resume_calls.append(run_id)

    async def _recover_workspace_id(self, owner_id, run_id):
        return None


def _run(session, target):
    rid = str(uuid.uuid4())
    session.add(WorkflowRun(
        id=rid, user_id="owner", owner_id="owner", title="a run", type="ppt", status="failed",
        input="brief", agent_count=2,
        manifest_json={"id": "user-workflow-x", "steps": _steps(target), "_trust": "db"}))
    session.commit()
    return rid


def test_R_resume(monkeypatch):
    print()
    client, session, _ = _world("basic", monkeypatch)
    stub = _StubEngine()
    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: stub)
    for reg in (re_mod._PIPELINE_TASKS, re_mod._PIPELINE_QUEUES, re_mod._CANCEL_EVENTS):
        reg.clear()
    bad = _run(session, "app_builder")
    r = client.post(f"/api/runs/{bad}/resume")
    session.expire_all()
    status_after = session.get(WorkflowRun, bad).status
    print(f"[R1] basic resumes a failed ppt run whose persisted manifest triggers app_builder -> "
          f"{r.status_code} {r.json()} status after={status_after!r} queued={bad in re_mod._PIPELINE_QUEUES}")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "tier_not_entitled"
    assert status_after == "failed" and bad not in re_mod._PIPELINE_QUEUES
    ok = _run(session, "ppt")
    r = client.post(f"/api/runs/{ok}/resume")
    print(f"[R2] basic resumes a failed ppt run whose persisted manifest triggers ppt (control) -> {r.status_code}")
    assert r.status_code == 200
    for reg in (re_mod._PIPELINE_TASKS, re_mod._PIPELINE_QUEUES, re_mod._CANCEL_EVENTS):
        reg.clear()
