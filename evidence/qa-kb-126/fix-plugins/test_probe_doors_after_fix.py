"""PROBE (not a product test), QA-KB-126 fix, 5-fixer 2026-10-09.

Re-drives every door of analysis-01 after the ISS-1114 change, with the same harness
(analysis-plugins/test_probe_db_trust_doors.py: in-memory SQLite, real routers, principal override,
ONLY rc._launch_run_core stubbed, so nothing is minted, driven or paid for), and adds the controls:
  S  save per tier          M  what a basic caller still gets (save -> launch by id)
  L  legacy row at launch   P  PATCH door            T  trigger door, by parent _trust
  R  resume door            O  override rows (unchanged)   E  enterprise Composer (unchanged)
Prints each observation and asserts it.
"""
import copy
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis-plugins"))

import agents.execution_engine.engine as engine_mod  # noqa: E402
import app.api.run_engine as re_mod  # noqa: E402
from agents.workflows.compiler import CompilerError  # noqa: E402
from app.models.workflow import WorkflowRun  # noqa: E402
from app.models.workflow_definition import WorkflowDefinition  # noqa: E402
from test_probe_db_trust_doors import (  # noqa: E402
    _ITEMS, TIER_BASE, _benign_step, _eff, _exec_step, _launch, _post, _spawn_step, _world,
)


def _orm_row(session, rid, base, steps, override_of=None):
    session.add(WorkflowDefinition(
        id=rid, user_id="owner", owner_id="owner", workspace_id="owner", name=rid, agents="[]",
        artifact_edges="[]", source="user", base_pipeline_type=base,
        overrides_pipeline_type=override_of, override_enabled=bool(override_of),
        manifest_json={"steps": steps}))
    session.commit()


def _run(session, rid, trust, type_="user_stories"):
    session.add(WorkflowRun(id=rid, user_id="owner", owner_id="owner", title="t", type=type_, status="failed",
                            input="brief", agent_count=1,
                            manifest_json={"steps": [_exec_step()], **({"_trust": trust} if trust else {})}))
    session.commit()


@pytest.mark.parametrize("tier", ["basic", "hexaware", "pro", "enterprise"])
def test_S_save_per_tier(tier, monkeypatch):
    client, session, _ = _world(tier, monkeypatch)
    base = TIER_BASE[tier]
    out = {}
    for label, b, steps in (("custom exec", "custom", [_exec_step()]), (f"{base} exec", base, [_exec_step()]),
                            (f"{base} spawn", base, [_spawn_step()]), (f"{base} benign", base, [_benign_step()])):
        out[label] = _post(client, b, steps, name=label).status_code
    print(f"\n[S] tier={tier:<10} " + "  ".join(f"POST {k} -> {v}" for k, v in out.items()))
    if tier == "enterprise":
        assert set(out.values()) == {201}
    else:
        assert out["custom exec"] == 403 and out[f"{base} exec"] == 422 and out[f"{base} spawn"] == 422
        assert out[f"{base} benign"] == 201


def test_M_matrix_basic(monkeypatch):
    print(f"\n[M] {'item':<62} basic: save -> launch by id")
    for i, (label, manifest) in enumerate(_ITEMS):
        client, session, seen = _world("basic", monkeypatch)
        saved = client.post("/api/user-workflows", json={
            "name": f"m{i}", "base_pipeline_type": "ppt", "agent_ids": ["ppt-brief-analyst"],
            "manifest": copy.deepcopy(manifest)})
        if saved.status_code != 201:
            out = f"SAVE {saved.status_code}"
        else:
            r = _launch(client, pipeline_type="ppt", user_workflow_id=saved.json()["id"])
            comp = seen.get("compiled")
            assert r.status_code == 200 and comp is not None
            s, t, lim = comp.steps[0], comp.steps[0].tools, comp.limits
            flags = [n for n, v in (("exec", t.exec), ("spawn", t.spawn_subagents), ("git", t.git),
                                    ("network", t.network)) if v]
            if t.tool_sets: flags.append(f"tool_sets={list(t.tool_sets)}")
            if s.gates: flags.append(f"gates={list(s.gates)}")
            if lim.max_subagents: flags.append(f"limits={lim.max_subagents}")
            out = "201+200 " + (",".join(flags) or "(nothing privileged)") + f" _trust={seen['manifest_json']['_trust']}"
            assert seen["manifest_json"]["_trust"] == "user" and not (t.exec or t.spawn_subagents or t.git)
            assert set(t.tool_sets or []) <= {"file_extract", "playwright"}
        print(f"[M] {label:<62} {out}")


@pytest.mark.parametrize("tier", ["basic", "enterprise"])
def test_L_legacy_row(tier, monkeypatch):
    client, session, seen = _world(tier, monkeypatch)
    _orm_row(session, "legacy", "ppt", [_exec_step()])
    r = _launch(client, pipeline_type="ppt", user_workflow_id="legacy")
    detail = r.json().get("detail")
    print(f"\n[L] {tier} launches a stored exec row (base ppt, saved before the fix) -> {r.status_code} "
          f"code={detail.get('code') if isinstance(detail, dict) else None} mint reached={bool(seen)}"
          + (f" plan={_eff(seen['compiled'])} _trust={seen['manifest_json']['_trust']}" if seen else ""))
    if tier == "basic":
        assert r.status_code == 422 and not seen
    else:
        assert r.status_code == 200 and seen["compiled"].steps[0].tools.exec and seen["manifest_json"]["_trust"] == "db"


def test_P_patch(monkeypatch):
    client, session, _ = _world("basic", monkeypatch)
    rid = client.post("/api/user-workflows", json={
        "name": "benign", "base_pipeline_type": "ppt", "agent_ids": ["ppt-brief-analyst"]}).json()["id"]
    r = client.patch(f"/api/user-workflows/{rid}", json={"manifest": {"steps": [_exec_step()]}})
    session.expire_all()
    stored = session.get(WorkflowDefinition, rid).manifest_json
    print(f"\n[P1] basic PATCH exec manifest onto a ppt row -> {r.status_code}; stored manifest_json={stored}")
    assert r.status_code == 422 and stored is None
    r = client.patch(f"/api/user-workflows/{rid}", json={"manifest": {"steps": [_benign_step()]}})
    print(f"[P2] basic PATCH benign manifest (control) -> {r.status_code}")
    assert r.status_code == 200
    client, session, _ = _world("enterprise", monkeypatch)
    rid = _post(client, "custom", [_benign_step()]).json()["id"]
    r = client.patch(f"/api/user-workflows/{rid}", json={"manifest": {"steps": [_exec_step()]}})
    print(f"[P3] enterprise PATCH exec manifest onto a custom row (control) -> {r.status_code}")
    assert r.status_code == 200


@pytest.mark.parametrize("parent_trust", [None, "user", "db"])
async def test_T_trigger(parent_trust, monkeypatch):
    from agents.execution_engine.kernel_services import KernelServices

    client, session, seen = _world("basic", monkeypatch)
    _orm_row(session, "legacy-t", "ppt", [_exec_step()])
    _run(session, "parent-run", parent_trust)

    class _Ectx:
        run_id, owner_id, workspace_id, trigger_depth = "parent-run", "owner", "owner", 0

    ks = KernelServices.__new__(KernelServices)
    ks._pipeline_type, ks._ordered_agents = "ppt", []
    try:
        await ks.run_trigger_workflow(None, _Ectx(), workflow_ref="legacy-t", content="go")
        outcome = f"mint reached, plan={_eff(seen['compiled'])}"
    except CompilerError as exc:
        outcome = f"CompilerError before the mint: {str(exc)[:90]}"
    print(f"\n[T] parent run _trust={parent_trust!r}: trigger of a stored exec row -> {outcome}; mint reached={bool(seen)}")
    assert bool(seen) == (parent_trust == "db")


class _StubEngine:
    async def _stamp_resume_marker(self, wr):
        return None

    async def resume_run(self, run_id):
        return None

    async def _recover_workspace_id(self, owner_id, run_id):
        return None


@pytest.mark.parametrize("tier,trust", [("basic", "db"), ("basic", "user"), ("basic", None), ("enterprise", "db")])
def test_R_resume(tier, trust, monkeypatch):
    client, session, _ = _world(tier, monkeypatch)
    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: _StubEngine())
    rid = str(uuid.uuid4())
    _run(session, rid, trust)
    r = client.post(f"/api/runs/{rid}/resume")
    for reg in (re_mod._PIPELINE_TASKS, re_mod._PIPELINE_QUEUES, re_mod._CANCEL_EVENTS):
        reg.pop(rid, None)
    print(f"\n[R] {tier} resumes a failed run persisted at _trust={trust!r} -> {r.status_code} {r.json()}")
    assert r.status_code == (403 if (tier, trust) == ("basic", "db") else 200)


def test_O_override_rows_unchanged(monkeypatch):
    client, session, seen = _world("basic", monkeypatch)
    r = client.post("/api/user-workflows", json={
        "name": "My Deck", "base_pipeline_type": "ppt", "agent_ids": ["ppt-brief-analyst"],
        "overrides_pipeline_type": "ppt", "manifest": {"steps": [_benign_step()]}})
    print(f"\n[O1] basic saves a benign override of ppt -> {r.status_code}")
    assert r.status_code == 201
    r = _launch(client, pipeline_type="ppt", user_workflow_id=r.json()["id"])
    print(f"[O2] basic launches it by id -> {r.status_code}; _trust={(seen.get('manifest_json') or {}).get('_trust')!r}")
    assert r.status_code == 200 and seen["manifest_json"]["_trust"] == "user"
    r = client.post("/api/user-workflows", json={
        "name": "Exec Deck", "base_pipeline_type": "ppt", "agent_ids": ["ppt-brief-analyst"],
        "overrides_pipeline_type": "ppt_v2", "manifest": {"steps": [_exec_step()]}})
    print(f"[O3] basic saves an exec override -> {r.status_code}")
    assert r.status_code == 422


def test_E_enterprise_composer(monkeypatch):
    client, session, seen = _world("enterprise", monkeypatch)
    rid = _post(client, "custom", [_exec_step()]).json()["id"]
    r = _launch(client, pipeline_type="custom", user_workflow_id=rid)
    print(f"\n[E] enterprise Composer row (base custom) save+launch -> {r.status_code}; plan={_eff(seen['compiled'])}; "
          f"_trust={seen['manifest_json']['_trust']!r}")
    assert r.status_code == 200 and seen["compiled"].steps[0].tools.exec and seen["manifest_json"]["_trust"] == "db"


def test_I_inline_control(monkeypatch):
    client, session, seen = _world("basic", monkeypatch)
    r = _launch(client, pipeline_type="ppt", manifest={"steps": [_exec_step()]})
    print(f"\n[I] basic inline exec manifest -> {r.status_code} mint reached={bool(seen)}")
    assert r.status_code == 422 and not seen
