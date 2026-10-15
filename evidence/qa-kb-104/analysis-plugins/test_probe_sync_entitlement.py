"""READ-ONLY PROBE (not a product test), QA-KB-104 analysis.

Questions:
  A. POST /api/user-workflows/{id}/sync-from-file copies a source pipeline's manifest into a PLAIN row the caller
     owns. For each caller tier, which of the 41 SUPPORTED pipeline types does it copy, versus what
     can_run_pipeline(tier, type) says that tier may RUN?
  B. The same for an OVERRIDE row (overrides_pipeline_type="ppt"), where FIX-766 compiles the steps at trust="user".
  C. Does a plain row synced from an unentitled pipeline pass every gate of the REAL REST launch (POST /api/runs,
     Case 3) up to the run mint? `_launch_run_core` is stubbed to record its arguments and return, so NO run is
     minted and nothing is spent. Control: launching the unentitled pipeline directly.

Harness = in-memory SQLite + the user_workflows router + principal override (same as
tests/integration/api/test_iss1112_override_writers_trust.py); C adds the run_commands router and the
`_get_db` / `session.close` patch used by test_iss1113_override_row_launch_trust.py.
It asserts nothing; it prints.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.run_commands as rc
from agents.loader import SUPPORTED_PIPELINE_TYPES
from app.api.user_workflows import router as uw_router
from app.core.dependencies import get_current_principal, get_current_user
from app.core.entitlements import can_run_pipeline
from app.models.database import Base, get_db
from app.models.workflow_definition import WorkflowDefinition
from tests.fakes.principal import principal_for

TIER_BASE = {"basic": "ppt", "hexaware": "prototype", "pro": "ppt", "enterprise": "ppt"}
ALL = sorted(SUPPORTED_PIPELINE_TYPES)


class _FakeUser:
    def __init__(self, id, tier):
        self.id = id
        self.tier = tier


def _world(tier, with_runs=False):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    user = _FakeUser("owner", tier)
    app = FastAPI()
    app.include_router(uw_router)
    if with_runs:
        app.include_router(rc.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_principal] = lambda: (user, principal_for(user))

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app), session, engine


def _row(session, rid, base, override_of=None):
    session.add(
        WorkflowDefinition(
            id=rid, user_id="owner", owner_id="owner", workspace_id="owner", name=rid, agents="[]",
            artifact_edges="[]", source="user", base_pipeline_type=base,
            overrides_pipeline_type=override_of, override_enabled=bool(override_of),
        )
    )
    session.commit()


def _sync(client, rid, ptype):
    r = client.post(f"/api/user-workflows/{rid}/sync-from-file", json={"pipeline_type": ptype})
    try:
        d = r.json()
    except Exception:
        d = {}
    return r.status_code, d


def test_probe_A_plain_row_matrix_by_tier():
    print()
    for tier in ("basic", "hexaware", "pro", "enterprise"):
        client, session, engine = _world(tier)
        base = TIER_BASE[tier]
        assert can_run_pipeline(tier, base)[0], (tier, base)
        legit, bypass, other = [], [], {}
        for i, p in enumerate(ALL):
            rid = f"row-{i}"
            _row(session, rid, base)
            code, d = _sync(client, rid, p)
            ent = can_run_pipeline(tier, p)[0]
            if code == 200 and ent:
                legit.append(p)
            elif code == 200 and not ent:
                bypass.append(p)
            else:
                other.setdefault(code, []).append((p, str(d.get("detail"))[:70]))
        print(f"[A] tier={tier} plain row base_pipeline_type={base}: {len(ALL)} supported types tried")
        print(f"    200 and entitled (legit)            : {len(legit)}")
        print(f"    200 and NOT entitled (entitlement bypass): {len(bypass)}")
        print(f"        {bypass}")
        print(f"    other status                        : { {k: [x[0] for x in v] for k, v in other.items()} }")
        for k, v in other.items():
            for p, det in v:
                print(f"        {k} {p}: {det}")
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_probe_B_override_row_matrix_basic():
    print()
    client, session, engine = _world("basic")
    ok_unentitled, ok_entitled, refused = [], [], {}
    for i, p in enumerate(ALL):
        session.query(WorkflowDefinition).delete()
        session.commit()
        _row(session, f"ovr-{i}", "ppt", override_of="ppt")
        code, d = _sync(client, f"ovr-{i}", p)
        ent = can_run_pipeline("basic", p)[0]
        if code == 200:
            (ok_entitled if ent else ok_unentitled).append(p)
        else:
            refused.setdefault(code, []).append((p, str(d.get("detail"))[:90]))
    print("[B] tier=basic, OVERRIDE row (overrides_pipeline_type=ppt, FIX-766 trust=user steps check on)")
    print(f"    200 and entitled                         : {ok_entitled}")
    print(f"    200 and NOT entitled (content bypass)    : {len(ok_unentitled)} {ok_unentitled}")
    for k, v in refused.items():
        print(f"    {k}: {len(v)} types")
        for p, det in v:
            ent = can_run_pipeline("basic", p)[0]
            print(f"        {p} (basic may run: {ent}): {det}")
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.mark.parametrize("ptype", ["sample_subagents_parallel", "app_builder", "mulesoft_to_springboot", "custom", "ppt"])
def test_probe_C_launch_of_a_synced_plain_row(monkeypatch, ptype):
    print()
    client, session, engine = _world("basic", with_runs=True)
    monkeypatch.setattr(rc, "_get_db", lambda: session, raising=False)
    monkeypatch.setattr(session, "close", lambda: None)
    seen = {}

    async def fake_core(**kw):
        seen.update(kw)
        return {"run_id": "STUB-NOT-MINTED"}

    monkeypatch.setattr(rc, "_launch_run_core", fake_core)

    ent = can_run_pipeline("basic", ptype)
    r = client.post("/api/runs", json={"message": "go", "pipeline_type": ptype})
    det = r.json().get("detail") if r.status_code != 200 else None
    code = det.get("code") if isinstance(det, dict) else det
    print(f"[C] basic launches pipeline_type={ptype} DIRECTLY -> {r.status_code} {code!s:.60}  (can_run_pipeline={ent[0]}) reached_mint={bool(seen)}")
    seen.clear()

    _row(session, "plain-1", "ppt")
    sc, sd = _sync(client, "plain-1", ptype)
    print(f"    sync-from-file {ptype} into basic's plain ppt row -> {sc}")
    r = client.post("/api/runs", json={"message": "go", "pipeline_type": "ppt", "user_workflow_id": "plain-1"})
    det = r.json().get("detail") if r.status_code != 200 else None
    code = det.get("code") if isinstance(det, dict) else det
    reached = bool(seen)
    print(f"    POST /api/runs {{pipeline_type: ppt, user_workflow_id}} -> {r.status_code} {code!s:.70} reached_mint_stub={reached}")
    if reached:
        compiled = seen["compiled"]
        steps = list(compiled.steps)
        n_exec = sum(1 for s in steps if getattr(s.tools, "exec", False))
        n_spawn = sum(1 for s in steps if getattr(s.tools, "spawn_subagents", False))
        gates = sorted({g for s in steps for g in s.gates})
        print(f"    pipeline_type passed to the run core={seen['pipeline_type']!r}; compiled.id={compiled.id!r}; steps={len(steps)}")
        print(f"    compiled at _trust={seen['manifest_json'].get('_trust')!r}; steps with exec={n_exec}, spawn_subagents={n_spawn}; gates used={gates}")
    session.close()
    Base.metadata.drop_all(bind=engine)


def _benign_step(iid="mine"):
    return {"agent": "custom-agent", "instance_id": iid, "name": iid, "prompt": f"You are {iid}.",
            "tools": {"read_files": False, "write_files": False, "exec": False}}


@pytest.mark.parametrize("target", ["app_builder", "sample_subagents_parallel", "custom"])
def test_probe_D_override_target_is_not_entitlement_checked_at_create(monkeypatch, target):
    """Sibling check: POST /api/user-workflows gates base_pipeline_type (user_workflows.py:740) but the
    overrides_pipeline_type target (:848-854) only has to be SUPPORTED. Is the stored override ever applied for
    a tier that cannot run the target? (launch applies an override only AFTER the tier gate.)"""
    print()
    client, session, engine = _world("basic", with_runs=True)
    monkeypatch.setattr(rc, "_get_db", lambda: session, raising=False)
    monkeypatch.setattr(session, "close", lambda: None)
    seen = {}

    async def fake_core(**kw):
        seen.update(kw)
        return {"run_id": "STUB-NOT-MINTED"}

    monkeypatch.setattr(rc, "_launch_run_core", fake_core)
    r = client.post("/api/user-workflows", json={
        "name": "ovr", "base_pipeline_type": "ppt", "agent_ids": ["ppt-brief-analyst"],
        "manifest": {"steps": [_benign_step()]}, "overrides_pipeline_type": target})
    print(f"[D] basic POST override of {target} (base ppt, benign step) -> {r.status_code} {str(r.json().get('detail', ''))[:80]}")
    r = client.post("/api/runs", json={"message": "go", "pipeline_type": target})
    det = r.json().get("detail") if r.status_code != 200 else None
    print(f"    basic launches {target} directly with that override stored -> {r.status_code} {det.get('code') if isinstance(det, dict) else det} reached_mint={bool(seen)}")
    session.close()
    Base.metadata.drop_all(bind=engine)


def _trigger_steps(target):
    """The ex_A3_divert shape (agents/workflows/ex_A3_divert/workflow.yaml): one conditional gate whose
    `spanish` outcome is `trigger: workflow` -> `target`. Every key is a custom-agent step key."""
    return [
        _benign_step("emoji"),
        {
            "agent": "custom-agent", "instance_id": "language", "name": "Pick Language",
            "produces": ["route_decision"], "prompt": 'Reply {"decision": "spanish"}', "gates": ["conditional"],
            "route": {"outcomes": {"spanish": {"trigger": "workflow", "target": target, "feedback": "go"}}, "trigger_max_depth": 5},
            "tools": {"read_files": False, "write_files": False, "exec": False},
        },
    ]


@pytest.mark.parametrize("target", ["app_builder", "sample_subagents_parallel", "custom"])
async def test_probe_E_workflow_trigger_door(monkeypatch, target):
    """Sibling check: a user-authored manifest names a pipeline as a `trigger: workflow` target.
    (i) does a BASIC caller's save accept it (compile at trust=db)? (ii) does the kernel delegate
    `run_trigger_workflow` reach `_launch_run_core` for that pipeline, with only an owner id and no tier?
    `_launch_run_core` is stubbed: nothing is minted, no run happens."""
    from agents.execution_engine.kernel_services import KernelServices

    client, session, engine = _world("basic", with_runs=False)
    r = client.post("/api/user-workflows", json={
        "name": "hop", "base_pipeline_type": "ppt", "agent_ids": ["ppt-brief-analyst"],
        "manifest": {"steps": _trigger_steps(target)}})
    print(f"\n[E] basic POST row (base ppt) whose gate has `trigger: workflow, target: {target}` -> {r.status_code} {str(r.json().get('detail', ''))[:90]}")
    print(f"    can_run_pipeline(basic, {target}) = {can_run_pipeline('basic', target)[0]}")

    seen = {}

    async def fake_core(**kw):
        seen.update(kw)
        return {"run_id": "STUB-NOT-MINTED"}

    monkeypatch.setattr(rc, "_launch_run_core", fake_core)

    class _Ectx:
        run_id, owner_id, workspace_id, trigger_depth = "parent-run", "owner", "owner", 0

    ks = KernelServices.__new__(KernelServices)
    ks._pipeline_type = "ppt"
    ks._ordered_agents = []
    new_id, resolved = await ks.run_trigger_workflow(None, _Ectx(), workflow_ref=target, content="go")
    print(f"    run_trigger_workflow(workflow_ref={target!r}) -> reached _launch_run_core={bool(seen)} pipeline_type={seen.get('pipeline_type')!r} "
          f"user={getattr(seen.get('user'), '__dict__', None)} owner_id_override={seen.get('owner_id_override')!r}  (no tier / principal anywhere on this path)")
    session.close()
    Base.metadata.drop_all(bind=engine)
