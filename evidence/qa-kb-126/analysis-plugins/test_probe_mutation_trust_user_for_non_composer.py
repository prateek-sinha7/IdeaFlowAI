"""MUTATION PROBE (not a product test), QA-KB-126 analysis. NO source file is edited.

Question: is the trust level of the compile the one lever that decides what a saved row can hold? If every compile
that today runs at trust="db" ran at trust="user" for a caller who may not hold the Composer, do all the doors of
test_probe_db_trust_doors.py close, with the enterprise Composer row untouched?

The mutation is a monkeypatch of WorkflowCompiler.compile (the class every compile site reaches: the save check
`_WORKFLOW_COMPILER.compile`, launch Case 3 / trigger / resume through `compile_with_baseline`). It stands in for the
one-helper change: "db" only for the Composer-entitled, "user" for everyone else. It does not model WHICH key picks
the trust (tier or row label); it shows the compile trust is sufficient at all four doors.
"""
import copy

import pytest

from agents.workflows.compiler import CompilerError, WorkflowCompiler
from app.models.workflow_definition import WorkflowDefinition
from test_probe_db_trust_doors import (  # same directory; harness + payloads shared with the baseline probe
    _ITEMS,
    _benign_step,
    _eff,
    _exec_step,
    _launch,
    _post,
    _world,
)

_orig_compile = WorkflowCompiler.compile


def _mutate(monkeypatch, tier):
    def compile_(self, manifest, registry, *, trust="file"):
        if trust == "db" and tier != "enterprise":
            trust = "user"  # the mutation
        return _orig_compile(self, manifest, registry, trust=trust)

    monkeypatch.setattr(WorkflowCompiler, "compile", compile_)


def _orm_row(session, rid, base, steps):
    session.add(WorkflowDefinition(
        id=rid, user_id="owner", owner_id="owner", workspace_id="owner", name=rid, agents="[]",
        artifact_edges="[]", source="user", base_pipeline_type=base, manifest_json={"steps": steps}))
    session.commit()


@pytest.mark.parametrize("tier", ["basic", "hexaware", "pro"])
def test_mut_save_closed(tier, monkeypatch):
    client, session, seen = _world(tier, monkeypatch)
    _mutate(monkeypatch, tier)
    base = {"basic": "ppt", "hexaware": "prototype", "pro": "ppt"}[tier]
    r = _post(client, base, [_exec_step()])
    print(f"\n[mut-S] {tier} POST base={base} exec-manifest -> {r.status_code} {str(r.json().get('detail'))[:110]}")
    assert r.status_code == 422
    r = _post(client, base, [_benign_step()], name="benign")
    print(f"[mut-S] {tier} POST base={base} benign manifest (control) -> {r.status_code}")
    assert r.status_code == 201


def test_mut_launch_legacy_row_closed(monkeypatch):
    """A row stored before the fix (ORM insert, as if saved under the old code) is refused at launch."""
    client, session, seen = _world("basic", monkeypatch)
    _mutate(monkeypatch, "basic")
    _orm_row(session, "legacy", "ppt", [_exec_step()])
    r = _launch(client, pipeline_type="ppt", user_workflow_id="legacy")
    detail = r.json().get("detail")
    print(f"\n[mut-L] basic launches a legacy exec row (base ppt) -> {r.status_code} "
          f"code={detail.get('code') if isinstance(detail, dict) else None} mint reached={bool(seen)}")
    assert r.status_code == 422 and not seen


def test_mut_patch_closed(monkeypatch):
    client, session, seen = _world("basic", monkeypatch)
    _mutate(monkeypatch, "basic")
    rid = client.post("/api/user-workflows", json={
        "name": "benign", "base_pipeline_type": "ppt", "agent_ids": ["ppt-brief-analyst"]}).json()["id"]
    r = client.patch(f"/api/user-workflows/{rid}", json={"manifest": {"steps": [_exec_step()]}})
    session.expire_all()
    print(f"\n[mut-P] basic PATCH exec manifest onto an entitled-label row -> {r.status_code}; "
          f"stored manifest_json={session.get(WorkflowDefinition, rid).manifest_json}")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_mut_trigger_closed(monkeypatch):
    from agents.execution_engine.kernel_services import KernelServices

    client, session, seen = _world("basic", monkeypatch)
    _mutate(monkeypatch, "basic")
    _orm_row(session, "legacy-t", "ppt", [_exec_step()])

    class _Ectx:
        run_id, owner_id, workspace_id, trigger_depth = "parent-run", "owner", "owner", 0

    ks = KernelServices.__new__(KernelServices)
    ks._pipeline_type = "ppt"
    ks._ordered_agents = []
    try:
        await ks.run_trigger_workflow(None, _Ectx(), workflow_ref="legacy-t", content="go")
        outcome = f"REACHED the mint, plan={_eff(seen['compiled'])}"
    except CompilerError as exc:
        outcome = f"CompilerError raised before the mint: {str(exc)[:100]}"
    print(f"\n[mut-T] trigger of a legacy exec row (owner basic) -> {outcome}; mint reached={bool(seen)}")
    assert not seen


def test_mut_enterprise_composer_unchanged(monkeypatch):
    client, session, seen = _world("enterprise", monkeypatch)
    _mutate(monkeypatch, "enterprise")
    rid = _post(client, "custom", [_exec_step()]).json()["id"]
    r = _launch(client, pipeline_type="custom", user_workflow_id=rid)
    comp = seen.get("compiled")
    print(f"\n[mut-E] enterprise Composer row (base custom) save+launch -> {r.status_code}; plan={_eff(comp)}; "
          f"_trust={seen['manifest_json']['_trust']!r}")
    assert r.status_code == 200 and comp.steps[0].tools.exec is True and seen["manifest_json"]["_trust"] == "db"


def test_mut_matrix_basic(monkeypatch):
    print()
    print(f"[mut-M] {'item':<62} basic save -> launch by id (mutated)")
    for i, (label, manifest) in enumerate(_ITEMS):
        client, session, seen = _world("basic", monkeypatch)
        _mutate(monkeypatch, "basic")
        saved = client.post("/api/user-workflows", json={
            "name": f"m{i}", "base_pipeline_type": "ppt", "agent_ids": ["ppt-brief-analyst"],
            "manifest": copy.deepcopy(manifest)})
        if saved.status_code != 201:
            out = f"SAVE {saved.status_code}"
        else:
            r = _launch(client, pipeline_type="ppt", user_workflow_id=saved.json()["id"])
            comp = seen.get("compiled")
            if r.status_code == 200 and comp is not None:
                s, t, lim = comp.steps[0], comp.steps[0].tools, comp.limits
                flags = [n for n, v in (("exec", t.exec), ("spawn", t.spawn_subagents), ("git", t.git)) if v]
                if t.tool_sets: flags.append(f"tool_sets={list(t.tool_sets)}")
                if s.gates: flags.append(f"gates={list(s.gates)}")
                if lim.max_subagents: flags.append(f"limits={lim.max_subagents}")
                out = "201+200 " + (",".join(flags) or "(nothing privileged)")
            else:
                out = f"201 then LAUNCH {r.status_code}"
        print(f"[mut-M] {label:<62} {out}")
