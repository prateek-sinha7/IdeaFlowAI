"""ISS-1164 / ISS-1165 (QA-KB-126) - the two doors that run a saved row with no fresh
launch in front of them must not give it more trust than that launch would.

ISS-1164: run_trigger_workflow holds a saved row to the persisted ``_trust`` of the run
that fires it (the kernel has no tier). ISS-1165: POST /api/runs/{id}/resume refuses a run
persisted at trust="db" for a caller a fresh launch would give "user".

Only _launch_run_core and the engine singleton are stubbed: nothing is minted or driven.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import agents.execution_engine.engine as engine_mod
import app.api.run_commands as rc
import app.api.run_engine as re_mod
from agents.execution_engine.kernel_services import KernelServices
from agents.workflows.compiler import CompilerError
from app.core.dependencies import get_current_principal
from app.models.database import Base
from app.models.workflow import WorkflowRun
from app.models.workflow_definition import WorkflowDefinition
from tests.fakes.principal import principal_for

_EXEC_STEP = {
    "agent": "custom-agent",
    "instance_id": "mine",
    "name": "mine",
    "prompt": "x",
    "gates": ["security", "approval"],
    "validators": ["code_test"],
    "tools": {"read_files": True, "write_files": True, "exec": True},
}


class _User:
    def __init__(self, tier):
        self.id, self.tier, self.preferred_model = "owner", tier, None


def _session(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    monkeypatch.setattr(rc, "_get_db", lambda: session, raising=False)
    monkeypatch.setattr(re_mod, "_get_db", lambda: session, raising=False)
    monkeypatch.setattr(session, "close", lambda: None)
    return session


def _run(session, rid, trust):
    session.add(
        WorkflowRun(
            id=rid,
            user_id="owner",
            owner_id="owner",
            title="t",
            type="user_stories",
            status="failed",
            input="brief",
            agent_count=1,
            manifest_json={"steps": [_EXEC_STEP], "_trust": trust},
        )
    )
    session.commit()


async def _trigger(session, monkeypatch, parent_run_id):
    """Fire the trigger at an exec row stored before ISS-1114; return the plan the mint gets."""
    session.add(
        WorkflowDefinition(
            id="row",
            user_id="owner",
            name="row",
            agents="[]",
            artifact_edges="[]",
            source="user",
            base_pipeline_type="ppt",
            manifest_json={"steps": [_EXEC_STEP]},
        )
    )
    session.commit()
    seen = {}

    async def fake_core(**kw):
        seen.update(kw)
        return {"run_id": "STUB"}

    monkeypatch.setattr(rc, "_launch_run_core", fake_core)
    ks = KernelServices.__new__(KernelServices)
    ks._pipeline_type, ks._ordered_agents = "ppt", []

    class _Ectx:
        run_id, owner_id, workspace_id, trigger_depth = (
            parent_run_id,
            "owner",
            "owner",
            0,
        )

    await ks.run_trigger_workflow(None, _Ectx(), workflow_ref="row")
    return seen["compiled"]


@pytest.mark.issue("ISS-1164")
@pytest.mark.parametrize(
    "parent_trust", [None, "user"], ids=["parent-has-none", "parent-user"]
)
async def test_trigger_holds_a_saved_row_to_the_firing_runs_trust(
    parent_trust, monkeypatch
):
    session = _session(monkeypatch)
    if parent_trust:
        _run(session, "parent", parent_trust)
    with pytest.raises(CompilerError):
        await _trigger(session, monkeypatch, "parent")


@pytest.mark.issue("ISS-1164")
async def test_trigger_from_a_db_trust_run_keeps_exec(monkeypatch):
    """Control: a run launched at db (an enterprise Composer row) still triggers a row at db."""
    session = _session(monkeypatch)
    _run(session, "parent", "db")
    assert (await _trigger(session, monkeypatch, "parent")).steps[0].tools.exec is True


class _StubEngine:
    async def _stamp_resume_marker(self, wr):
        return None

    async def resume_run(self, run_id):
        return None

    async def _recover_workspace_id(self, owner_id, run_id):
        return None


def _resume(session, monkeypatch, tier):
    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: _StubEngine())
    app = FastAPI()
    app.include_router(rc.router)
    user = _User(tier)
    app.dependency_overrides[get_current_principal] = lambda: (
        user,
        principal_for(user),
    )
    _run(session, "run-1", "db")
    try:
        return TestClient(app).post("/api/runs/run-1/resume")
    finally:
        for reg in (
            re_mod._PIPELINE_TASKS,
            re_mod._PIPELINE_QUEUES,
            re_mod._CANCEL_EVENTS,
        ):
            reg.pop("run-1", None)


@pytest.mark.issue("ISS-1165")
@pytest.mark.parametrize("tier", ["basic", "pro", "hexaware"])
def test_resume_refuses_a_db_trust_run_below_the_composer_tier(tier, monkeypatch):
    session = _session(monkeypatch)
    r = _resume(session, monkeypatch, tier)
    session.expire_all()
    assert (
        r.status_code == 403 and r.json()["detail"]["code"] == "tier_not_entitled"
    ), r.json()
    assert session.get(WorkflowRun, "run-1").status == "failed"


@pytest.mark.issue("ISS-1165")
def test_resume_of_a_db_trust_run_still_runs_for_enterprise(monkeypatch):
    session = _session(monkeypatch)
    assert _resume(session, monkeypatch, "enterprise").status_code == 200
