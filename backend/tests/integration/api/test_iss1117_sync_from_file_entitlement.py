"""ISS-1117 / ISS-1131 — entitlement gate on doors that name a pipeline without launching it.

ISS-1117: POST /api/user-workflows/{id}/sync-from-file must refuse a pipeline the caller's tier may not run.
ISS-1131: a saved manifest whose gate triggers a pipeline the tier may not run must be refused (save + launch).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.run_commands as rc
from app.api.user_workflows import router as uw_router
from app.core.dependencies import get_current_principal, get_current_user
from app.models.database import Base, get_db
from app.models.workflow_definition import WorkflowDefinition
from tests.fakes.principal import principal_for


class _FakeUser:
    def __init__(self, id: str, tier: str):
        self.id = id
        self.tier = tier


def _world(tier, with_runs=False):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    user = _FakeUser("owner", tier)
    app = FastAPI()
    app.include_router(uw_router)
    if with_runs:
        app.include_router(rc.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_principal] = lambda: (
        user,
        principal_for(user),
    )

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app), session, engine


@pytest.fixture
def world():
    made = []

    def make(tier, with_runs=False):
        w = _world(tier, with_runs)
        made.append(w)
        return w

    yield make
    for _, session, engine in made:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _row(session, rid, base, override_of=None, manifest=None):
    session.add(
        WorkflowDefinition(
            id=rid,
            user_id="owner",
            owner_id="owner",
            workspace_id="owner",
            name=rid,
            agents="[]",
            artifact_edges="[]",
            source="user",
            base_pipeline_type=base,
            overrides_pipeline_type=override_of,
            override_enabled=bool(override_of),
            manifest_json=manifest,
        )
    )
    session.commit()


def _sync(client, rid, ptype):
    return client.post(
        f"/api/user-workflows/{rid}/sync-from-file", json={"pipeline_type": ptype}
    )


def _manifest_of(session, rid):
    session.expire_all()
    return session.get(WorkflowDefinition, rid).manifest_json


# --- ISS-1117: refusals (red today, 200) -------------------------------------------------------


@pytest.mark.issue("ISS-1117")
@pytest.mark.parametrize(
    "tier,base,override_of,source",
    [
        ("basic", "ppt", None, "sample_subagents_parallel"),
        ("basic", "ppt", None, "app_builder"),
        ("hexaware", "prototype", None, "ppt"),
        ("pro", "ppt", None, "custom"),
        ("basic", "ppt", "ppt", "prototype_v2"),
    ],
)
def test_sync_from_unentitled_pipeline_is_403_and_leaves_row_untouched(
    world, tier, base, override_of, source
):
    """ISS-1117 — sync-from-file refuses a source pipeline the effective tier may not run."""
    client, session, _ = world(tier)
    _row(session, "r1", base, override_of)
    before = _manifest_of(session, "r1")
    resp = _sync(client, "r1", source)
    assert resp.status_code == 403, resp.text
    assert _manifest_of(session, "r1") == before


# --- ISS-1117: controls (green before and after) -----------------------------------------------


@pytest.mark.issue("ISS-1117")
@pytest.mark.parametrize(
    "tier,base,source",
    [
        ("basic", "ppt", "ppt"),
        ("hexaware", "prototype", "prototype"),
        ("enterprise", "ppt", "sample_subagents_parallel"),
    ],
)
def test_sync_from_entitled_pipeline_still_200(world, tier, base, source):
    client, session, _ = world(tier)
    _row(session, "r1", base)
    assert _sync(client, "r1", source).status_code == 200


# --- ISS-1131: workflow-trigger door ----------------------------------------------------------


def _trigger_steps(target):
    plain = {
        "agent": "custom-agent",
        "instance_id": "emoji",
        "name": "emoji",
        "prompt": "You are emoji.",
        "tools": {"read_files": False, "write_files": False, "exec": False},
    }
    gate = {
        "agent": "custom-agent",
        "instance_id": "language",
        "name": "Pick Language",
        "produces": ["route_decision"],
        "prompt": 'Reply {"decision": "spanish"}',
        "gates": ["conditional"],
        "route": {
            "outcomes": {
                "spanish": {"trigger": "workflow", "target": target, "feedback": "go"}
            },
            "trigger_max_depth": 5,
        },
        "tools": {"read_files": False, "write_files": False, "exec": False},
    }
    return [plain, gate]


@pytest.mark.issue("ISS-1131")
@pytest.mark.parametrize("target", ["app_builder", "sample_subagents_parallel"])
def test_save_of_row_triggering_unentitled_pipeline_is_403(world, target):
    """ISS-1131 — a basic caller cannot save a row whose gate triggers a pipeline basic may not run."""
    client, _, _ = world("basic")
    resp = client.post(
        "/api/user-workflows",
        json={
            "name": "hop",
            "base_pipeline_type": "ppt",
            "agent_ids": ["ppt-brief-analyst"],
            "manifest": {"steps": _trigger_steps(target)},
        },
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.issue("ISS-1131")
def test_launch_of_stored_row_triggering_unentitled_pipeline_is_refused(
    world, monkeypatch
):
    """ISS-1131 — launch of a stored row with an unentitled trigger target never reaches the run core."""
    client, session, _ = world("basic", with_runs=True)
    monkeypatch.setattr(rc, "_get_db", lambda: session, raising=False)
    monkeypatch.setattr(session, "close", lambda: None)
    seen = {}

    async def fake_core(**kw):
        seen.update(kw)
        return {"run_id": "STUB-NOT-MINTED"}

    monkeypatch.setattr(rc, "_launch_run_core", fake_core)
    _row(session, "hop", "ppt", manifest={"steps": _trigger_steps("app_builder")})
    resp = client.post(
        "/api/runs",
        json={"message": "go", "pipeline_type": "ppt", "user_workflow_id": "hop"},
    )
    assert resp.status_code in (403, 422), resp.text
    assert not seen, "run core reached with an unentitled trigger target"


@pytest.mark.issue("ISS-1131")
def test_save_of_row_triggering_entitled_pipeline_still_201(world):
    client, _, _ = world("basic")
    resp = client.post(
        "/api/user-workflows",
        json={
            "name": "hop",
            "base_pipeline_type": "ppt",
            "agent_ids": ["ppt-brief-analyst"],
            "manifest": {"steps": _trigger_steps("ppt")},
        },
    )
    assert resp.status_code == 201, resp.text
