"""ISS-1114 (QA-KB-126) - a tier that cannot run the Composer (base `custom`) must not
get exec / spawn_subagents from a saved manifest row by choosing an entitled base label.

Only _launch_run_core is stubbed, so nothing is minted. Correct behaviour: the save is
refused (4xx), or the launch is refused / compiled without the grant.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.run_commands as rc
import app.api.run_engine as re_mod
from app.api.user_workflows import router as uw_router
from app.core.dependencies import get_current_principal, get_current_user
from app.models.database import Base, get_db
from app.models.workflow_definition import WorkflowDefinition
from tests.fakes.principal import principal_for

_TIER_BASE = {"basic": "ppt", "pro": "ppt", "hexaware": "prototype"}


class _User:
    def __init__(self, tier):
        self.id, self.tier, self.preferred_model = "owner", tier, None


def _step(tools):
    return {
        "agent": "custom-agent",
        "instance_id": "mine",
        "name": "mine",
        "prompt": "x",
        "gates": ["security", "approval"],
        "validators": ["code_test"],
        "tools": tools,
    }


_EXEC = {"read_files": True, "write_files": True, "exec": True}
_SPAWN = {"read_files": True, "write_files": True, "spawn_subagents": True}


def _world(tier, monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    user = _User(tier)
    app = FastAPI()
    app.include_router(uw_router)
    app.include_router(rc.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_principal] = lambda: (
        user,
        principal_for(user),
    )
    app.dependency_overrides[get_db] = lambda: session
    monkeypatch.setattr(rc, "_get_db", lambda: session, raising=False)
    monkeypatch.setattr(re_mod, "_get_db", lambda: session, raising=False)
    monkeypatch.setattr(session, "close", lambda: None)
    seen = {}

    async def fake_core(**kw):
        seen.update(kw)
        return {"run_id": "STUB"}

    monkeypatch.setattr(rc, "_launch_run_core", fake_core)
    return TestClient(app), session, seen


def _granted(compiled):
    t = compiled.steps[0].tools
    return bool(t.exec or t.spawn_subagents)


@pytest.mark.issue("ISS-1114")
@pytest.mark.parametrize("tools", [_EXEC, _SPAWN], ids=["exec", "spawn"])
@pytest.mark.parametrize("tier", ["basic", "pro", "hexaware"])
def test_saved_row_never_grants_exec_or_spawn_below_composer_tier(
    tier, tools, monkeypatch
):
    """Save under an entitled label, launch by id: the mint must not see exec/spawn."""
    client, _, seen = _world(tier, monkeypatch)
    saved = client.post(
        "/api/user-workflows",
        json={
            "name": "row",
            "base_pipeline_type": _TIER_BASE[tier],
            "agent_ids": ["ppt-brief-analyst"],
            "manifest": {"steps": [_step(tools)]},
        },
    )
    if saved.status_code >= 400:
        return  # refused at save: correct
    r = client.post(
        "/api/runs",
        json={
            "message": "go",
            "pipeline_type": _TIER_BASE[tier],
            "user_workflow_id": saved.json()["id"],
        },
    )
    assert r.status_code >= 400 or not _granted(
        seen["compiled"]
    ), "launch minted a plan with exec/spawn"


@pytest.mark.issue("ISS-1114")
def test_legacy_stored_row_refused_or_narrowed_at_launch(monkeypatch):
    """A row already in the DB (saved before any fix) must still be safe at launch."""
    client, session, seen = _world("basic", monkeypatch)
    session.add(
        WorkflowDefinition(
            id="legacy-1",
            user_id="owner",
            name="legacy",
            agents="[]",
            artifact_edges="[]",
            source="user",
            base_pipeline_type="ppt",
            manifest_json={"steps": [_step(_EXEC)]},
        )
    )
    session.commit()
    r = client.post(
        "/api/runs",
        json={"message": "go", "pipeline_type": "ppt", "user_workflow_id": "legacy-1"},
    )
    assert r.status_code >= 400 or not _granted(
        seen["compiled"]
    ), "launch minted a plan with exec"


@pytest.mark.issue("ISS-1114")
def test_patch_cannot_put_exec_manifest_on_basic_row(monkeypatch):
    client, session, _ = _world("basic", monkeypatch)
    rid = client.post(
        "/api/user-workflows",
        json={
            "name": "benign",
            "base_pipeline_type": "ppt",
            "agent_ids": ["ppt-brief-analyst"],
        },
    ).json()["id"]
    r = client.patch(
        f"/api/user-workflows/{rid}", json={"manifest": {"steps": [_step(_EXEC)]}}
    )
    assert r.status_code >= 400, f"PATCH accepted an exec manifest: {r.status_code}"


@pytest.mark.issue("ISS-1114")
def test_enterprise_composer_row_keeps_exec(monkeypatch):
    """Control: the intended ADR-0039 behaviour stays."""
    client, _, seen = _world("enterprise", monkeypatch)
    rid = client.post(
        "/api/user-workflows",
        json={
            "name": "c",
            "base_pipeline_type": "custom",
            "agent_ids": ["ppt-brief-analyst"],
            "manifest": {"steps": [_step(_EXEC)]},
        },
    ).json()["id"]
    r = client.post(
        "/api/runs",
        json={"message": "go", "pipeline_type": "custom", "user_workflow_id": rid},
    )
    assert r.status_code == 200 and seen["compiled"].steps[0].tools.exec is True
