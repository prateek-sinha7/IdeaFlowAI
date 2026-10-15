"""READ-ONLY PROBE (not a product test), QA-KB-126 analysis, HEAD 4e2ec8580.

Question: the enterprise-only Composer gate keys on a caller-chosen label (base_pipeline_type) while the
privilege (exec, spawn_subagents, ...) is conferred by the trust of the compile (trust="db"). For each door:

  S. SAVE      POST /api/user-workflows  (per tier, a base the tier may run vs the Composer base `custom`)
  L. LAUNCH    POST /api/runs by user_workflow_id (the real launch_run Case 3; ONLY _launch_run_core is stubbed,
               so nothing is minted, driven or paid for). Prints what the mint would receive.
  I. INLINE    the same bytes sent inline on POST /api/runs (trust="user"): the control that shows the asymmetry.
  P. PATCH     POST an agent_ids-only row, then PATCH a manifest onto it.
  T. TRIGGER   KernelServices.run_trigger_workflow(workflow_ref=<row id>) with the mint stubbed.
  N. NARROW    what a trust="user" compile does to a tool_sets request: accepted and silently narrowed.

Harness = in-memory SQLite + the user_workflows and run_commands routers + principal override (same as
evidence/qa-kb-104/fix-plugins/test_probe_fix_doors.py). It prints every observation and asserts the ones the
analysis relies on.
"""
import copy
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.run_commands as rc
import app.api.run_engine as re_mod
import app.models.artifact_ref  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
from app.api.user_workflows import router as uw_router
from app.core.dependencies import get_current_principal, get_current_user
from app.core.entitlements import can_run_pipeline
from app.models.database import Base, get_db
from app.models.workflow_definition import WorkflowDefinition
from tests.fakes.principal import principal_for

# A base each tier may run that is NOT the Composer base `custom` (the bypass), per entitlements.py.
TIER_BASE = {"basic": "ppt", "hexaware": "prototype", "pro": "ppt", "enterprise": "ppt"}


class _FakeUser:
    def __init__(self, id, tier):
        self.id = id
        self.tier = tier
        self.preferred_model = None


def _world(tier, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
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
        seen.clear()
        seen.update(kw)
        return {"run_id": "STUB-NOT-MINTED"}

    monkeypatch.setattr(rc, "_launch_run_core", fake_core)
    return TestClient(app), session, seen


def _exec_step(iid="mine"):
    # Exactly the validate-stage body (evidence/qa-kb-126/01-validate-...txt).
    return {
        "agent": "custom-agent", "instance_id": iid, "name": iid, "prompt": f"You are {iid}.",
        "gates": ["security", "approval"], "validators": ["code_test"],
        "tools": {"read_files": True, "write_files": True, "exec": True},
    }


def _spawn_step(iid="mine"):
    return {
        "agent": "custom-agent", "instance_id": iid, "name": iid, "prompt": f"You are {iid}.",
        "tools": {"read_files": True, "write_files": True, "exec": False, "spawn_subagents": True},
    }


def _benign_step(iid="mine"):
    return {
        "agent": "custom-agent", "instance_id": iid, "name": iid, "prompt": f"You are {iid}.",
        "tools": {"read_files": False, "write_files": False, "exec": False},
    }


def _post(client, base, steps, name="probe-row"):
    return client.post("/api/user-workflows", json={
        "name": name, "base_pipeline_type": base, "agent_ids": ["ppt-brief-analyst"],
        "manifest": {"steps": steps}})


def _eff(compiled):
    out = []
    for s in compiled.steps:
        t = s.tools
        out.append(
            f"{s.agent_id}: exec={t.exec} spawn={t.spawn_subagents} git={t.git} "
            f"tool_sets={list(t.tool_sets or [])} gates={list(s.gates)} validators={list(s.validators)}"
        )
    return out


def _launch(client, **body):
    return client.post("/api/runs", json={"message": "go", **body})


# ------------------------------------------------------------------------------------------ S: save, per tier

@pytest.mark.parametrize("tier", ["basic", "hexaware", "pro", "enterprise"])
def test_S_save_per_tier(tier, monkeypatch):
    client, session, _ = _world(tier, monkeypatch)
    base = TIER_BASE[tier]
    assert can_run_pipeline(tier, base)[0]
    ctl = _post(client, "custom", [_exec_step()], name="composer-ctl")
    bug = _post(client, base, [_exec_step()], name="plain-row")
    custom_ok = can_run_pipeline(tier, "custom")[0]
    print(
        f"\n[S] tier={tier:<10} can_run_pipeline(custom)={custom_ok!s:<5} "
        f"POST base=custom exec-manifest -> {ctl.status_code}   "
        f"POST base={base} exec-manifest -> {bug.status_code}"
    )
    assert ctl.status_code == (201 if custom_ok else 403)
    assert bug.status_code == 201  # the bug: every tier saves the privileged manifest under a base it may run
    row = session.get(WorkflowDefinition, bug.json()["id"])
    print(
        f"    stored: base_pipeline_type={row.base_pipeline_type} overrides_pipeline_type={row.overrides_pipeline_type} "
        f"exec={row.manifest_json['steps'][0]['tools']['exec']} gates={row.manifest_json['steps'][0]['gates']}"
    )


# ------------------------------------------------------------------------------------------ L: launch by id

@pytest.mark.parametrize("tier", ["basic", "pro"])
def test_L_launch_by_id(tier, monkeypatch):
    client, session, seen = _world(tier, monkeypatch)
    base = TIER_BASE[tier]
    rid = _post(client, base, [_exec_step()]).json()["id"]
    r = _launch(client, pipeline_type=base, user_workflow_id=rid)
    comp = seen.get("compiled")
    print(f"\n[L] tier={tier} POST /api/runs user_workflow_id=<exec row, base {base}> -> {r.status_code} {r.json()}")
    print(f"    mint reached={bool(seen)} pipeline_type={seen.get('pipeline_type')!r} "
          f"manifest_json._trust={ (seen.get('manifest_json') or {}).get('_trust')!r}")
    print("    compiled plan handed to the mint:", _eff(comp) if comp else None)
    assert r.status_code == 200 and comp is not None
    assert comp.steps[0].tools.exec is True
    assert seen["manifest_json"]["_trust"] == "db"


def test_L_spawn_by_id(monkeypatch):
    client, session, seen = _world("basic", monkeypatch)
    rid = _post(client, "ppt", [_spawn_step()]).json()["id"]
    r = _launch(client, pipeline_type="ppt", user_workflow_id=rid)
    comp = seen.get("compiled")
    print(f"\n[L2] basic launches a spawn_subagents row -> {r.status_code}; plan:", _eff(comp) if comp else None)
    assert r.status_code == 200 and comp.steps[0].tools.spawn_subagents is True


def test_L_enterprise_composer_control(monkeypatch):
    """The intended ADR-0039 behaviour a fix must keep: an enterprise Composer row (base custom) holds exec."""
    client, session, seen = _world("enterprise", monkeypatch)
    rid = _post(client, "custom", [_exec_step()]).json()["id"]
    r = _launch(client, pipeline_type="custom", user_workflow_id=rid)
    comp = seen.get("compiled")
    print(f"\n[L3] enterprise Composer row (base custom) launch -> {r.status_code}; plan:", _eff(comp) if comp else None,
          f"_trust={ (seen.get('manifest_json') or {}).get('_trust')!r}")
    assert r.status_code == 200 and comp.steps[0].tools.exec is True


# ------------------------------------------------------------------------------------------ I: inline control

def test_I_inline_same_bytes_refused(monkeypatch):
    client, session, seen = _world("basic", monkeypatch)
    r = _launch(client, pipeline_type="ppt", manifest={"steps": [_exec_step()]})
    detail = r.json().get("detail")
    print(f"\n[I] basic sends the SAME manifest inline on POST /api/runs -> {r.status_code} "
          f"code={detail.get('code') if isinstance(detail, dict) else None} mint reached={bool(seen)}")
    print(f"    reason: {str(detail.get('error') if isinstance(detail, dict) else detail)[:170]}")
    assert r.status_code == 422 and not seen


# ------------------------------------------------------------------------------------------ P: PATCH door

def test_P_patch_manifest_onto_plain_row(monkeypatch):
    client, session, seen = _world("basic", monkeypatch)
    r = client.post("/api/user-workflows", json={
        "name": "benign", "base_pipeline_type": "ppt", "agent_ids": ["ppt-brief-analyst"]})
    rid = r.json()["id"]
    print(f"\n[P1] basic POST agent_ids-only row (base ppt, no manifest) -> {r.status_code}")
    r = client.patch(f"/api/user-workflows/{rid}", json={"manifest": {"steps": [_exec_step()]}})
    print(f"[P2] basic PATCH manifest with the exec step onto that row -> {r.status_code}  "
          f"(update_user_workflow calls can_run_pipeline: never)")
    assert r.status_code == 200
    r = _launch(client, pipeline_type="ppt", user_workflow_id=rid)
    comp = seen.get("compiled")
    print(f"[P3] basic launches it -> {r.status_code}; plan:", _eff(comp) if comp else None)
    assert r.status_code == 200 and comp.steps[0].tools.exec is True


# ------------------------------------------------------------------------------------------ T: trigger door

@pytest.mark.asyncio
async def test_T_trigger_door_row_id(monkeypatch):
    from agents.execution_engine.kernel_services import KernelServices

    client, session, seen = _world("basic", monkeypatch)
    rid = _post(client, "ppt", [_exec_step()]).json()["id"]

    class _Ectx:
        run_id, owner_id, workspace_id, trigger_depth = "parent-run", "owner", "owner", 0

    ks = KernelServices.__new__(KernelServices)
    ks._pipeline_type = "ppt"
    ks._ordered_agents = []
    new_id, resolved = await ks.run_trigger_workflow(None, _Ectx(), workflow_ref=rid, content="go")
    comp = seen.get("compiled")
    print(f"\n[T] run_trigger_workflow(workflow_ref=<basic exec row id>) -> mint reached={bool(seen)} "
          f"pipeline_type={seen.get('pipeline_type')!r} user={getattr(seen.get('user'), '__dict__', None)}")
    print("    compiled plan handed to the mint:", _eff(comp) if comp else None,
          "(no tier, no principal and no can_run_pipeline on this path)")
    assert comp is not None and comp.steps[0].tools.exec is True


# ------------------------------------------------------------------------------------------ N: silent narrowing

def test_N_user_trust_narrows_tool_sets_silently():
    from agents.execution_engine.engine import _CAPABILITY_REGISTRY, _WORKFLOW_COMPILER
    from agents.workflows.compiler import CompilerError
    from agents.workflows.manifest import build_manifest_from_dict

    step = _benign_step()
    step["tools"] = {"read_files": True, "write_files": True,
                     "tool_sets": ["internet", "pptx", "spawn_subagents", "ask_user", "playwright"]}
    raw = {"id": "probe", "steps": [step], "deliverable": {"strategy": "streamed_text", "name": "output.md"},
           "planner": "skip", "clarify": {"mode": "skip", "defaults": []}, "capabilities": {}}
    print()
    res = {}
    for trust in ("db", "user"):
        try:
            c = _WORKFLOW_COMPILER.compile(build_manifest_from_dict(copy.deepcopy(raw), "probe"), _CAPABILITY_REGISTRY, trust=trust)
            res[trust] = list(c.steps[0].tools.tool_sets or [])
            print(f"[N] trust={trust:<4} compiles; effective tool_sets={res[trust]} git={c.steps[0].tools.git}")
        except CompilerError as exc:
            res[trust] = f"REFUSED {exc}"
            print(f"[N] trust={trust:<4} REFUSED: {exc}")
    # user trust does NOT refuse: it narrows. A dry-run "does it compile at user?" gate would pass this manifest
    # while the real db compile still grants the packs.
    assert isinstance(res["user"], list) and set(res["db"]) > set(res["user"])


# ------------------------------------------------------------------------------------------ M: what else db confers

def _with(step_over=None, top_over=None):
    s = _benign_step()
    s.update(step_over or {})
    m = {"steps": [s]}
    m.update(top_over or {})
    return m


_ITEMS = [
    ("CONTROL benign step", _with()),
    ("CONTROL gates=[human] (user_allowed)", _with({"gates": ["human"]})),
    ("gate security", _with({"gates": ["security"]})),
    ("gate approval", _with({"gates": ["approval"]})),
    ("exec + gates security,approval", _with({"gates": ["security", "approval"],
                                              "tools": {"read_files": True, "write_files": True, "exec": True}})),
    ("spawn_subagents grant", _with({"tools": {"read_files": True, "write_files": True, "spawn_subagents": True}})),
    ("network grant", _with({"tools": {"read_files": True, "network": True}})),
    ("secrets grant (list field)", _with({"tools": {"read_files": True, "secrets": ["PROBE_SECRET"]}})),
    ("git grant", _with({"tools": {"read_files": True, "git": True}})),
    ("engineer-only hook provenance_audit", _with({"hooks": ["provenance_audit"]})),
    ("compaction html_skeleton", _with({"compaction": "html_skeleton"})),
    ("post_step revision_validation", _with({"post_step": "revision_validation"})),
    ("tool_sets [internet,pptx,spawn_subagents,ask_user]",
     _with({"tools": {"read_files": True, "write_files": True,
                      "tool_sets": ["internet", "pptx", "spawn_subagents", "ask_user"]}})),
    ("limits raised (max_subagents 64, max_depth 6, wall_clock 7200)",
     _with(None, {"limits": {"max_subagents": 64, "max_depth": 6, "wall_clock_seconds": 7200}})),
]


def test_M_what_db_trust_confers_to_basic(monkeypatch):
    """Same manifest, two doors, a BASIC caller: saved row launched by id (trust=db) vs sent inline (trust=user)."""
    print()
    print(f"[M] {'item':<62} {'save+launch by id (db)':<26} inline (user)")
    for i, (label, manifest) in enumerate(_ITEMS):
        client, session, seen = _world("basic", monkeypatch)
        saved = client.post("/api/user-workflows", json={
            "name": f"m{i}", "base_pipeline_type": "ppt", "agent_ids": ["ppt-brief-analyst"], "manifest": manifest})
        if saved.status_code != 201:
            by_id = f"SAVE {saved.status_code}"
        else:
            r = _launch(client, pipeline_type="ppt", user_workflow_id=saved.json()["id"])
            comp = seen.get("compiled")
            if r.status_code == 200 and comp is not None:
                t = comp.steps[0].tools
                lim = comp.limits
                extra = []
                if t.exec: extra.append("exec")
                if t.spawn_subagents: extra.append("spawn")
                if t.tool_sets: extra.append(f"tool_sets={list(t.tool_sets)}")
                if comp.steps[0].gates: extra.append(f"gates={list(comp.steps[0].gates)}")
                if t.git: extra.append("git")
                if t.network: extra.append("network")
                if t.secrets: extra.append(f"secrets={list(t.secrets)}")
                _h = [h for h in comp.steps[0].hooks if h not in ("audit_logger", "secret_scan")]
                if _h: extra.append(f"hooks={_h}")
                if comp.steps[0].compaction: extra.append(f"compaction={comp.steps[0].compaction}")
                if comp.steps[0].post_step: extra.append(f"post_step={comp.steps[0].post_step}")
                if lim.max_subagents: extra.append(f"limits={lim.max_subagents}/{lim.max_depth}/{lim.wall_clock_seconds}")
                by_id = "201+200 " + ",".join(extra)
            else:
                by_id = f"201 then LAUNCH {r.status_code}"
        seen.clear()
        r2 = _launch(client, pipeline_type="ppt", manifest=copy.deepcopy(manifest))
        inline = "200 accepted" if r2.status_code == 200 else f"{r2.status_code} refused"
        print(f"[M] {label:<62} {by_id:<26} {inline}")
