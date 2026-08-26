"""Spec 016 — the override round-trip, end to end over HTTP.

The unit tests cover the pieces; this covers the thing the user actually does:
save an edited version of `ppt`, then read `ppt` back and get THEIR steps —
while every workflow-level field still comes from the file manifest.

Both routers are mounted on one app against one SQLite session, so the save and
the read see the same row exactly as they do in production.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.user_workflows import router as uw_router
from app.api.workflows import router as wf_router
from app.core.dependencies import get_current_user
from app.models.database import Base, get_db


class _FakeUser:
    def __init__(self, id: str, tier: str = "enterprise"):
        self.id = id
        self.tier = tier


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    app = FastAPI()
    app.include_router(wf_router)
    app.include_router(uw_router)
    state = {"user": _FakeUser("owner")}
    app.dependency_overrides[get_current_user] = lambda: state["user"]

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        yield TestClient(app), state
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _step(iid: str):
    return {
        "agent": "custom-agent",
        "instance_id": iid,
        "name": f"My {iid}",
        "prompt": f"You are {iid}.",
        "tools": {"read_files": False, "write_files": False, "exec": False},
    }


def _save_override(client, *, steps, name="My Deck"):
    return client.post(
        "/api/user-workflows",
        json={
            "name": name,
            "base_pipeline_type": "ppt",
            "agent_ids": ["ppt-brief-analyst"],
            "manifest": {"steps": steps},
            "overrides_pipeline_type": "ppt",
        },
    )


def test_saving_an_override_then_reading_ppt_returns_my_steps(api):
    client, _ = api

    before = client.get("/api/workflows/ppt").json()
    assert before["is_overridden"] is False
    assert before["has_override"] is False
    file_step_ids = [s["agent_id"] for s in before["steps"]]

    saved = _save_override(client, steps=[_step("mine"), _step("also-mine")])
    assert saved.status_code == 201, saved.text
    assert saved.json()["overrides_pipeline_type"] == "ppt"
    assert saved.json()["override_enabled"] is True

    after = client.get("/api/workflows/ppt").json()
    assert after["is_overridden"] is True
    assert after["override_id"] == saved.json()["id"]
    assert [s["agent_id"] for s in after["steps"]] != file_step_ids
    assert len(after["steps"]) == 2
    # The authoring shape follows the compiled view — the two halves of one
    # payload must never disagree about which plan they describe.
    assert len(after["manifest_steps"]) == 2


def test_workflow_level_fields_still_come_from_the_file(api):
    """`deliverable: ppt` and `context_providers: [opendesign]` are NOT
    user_allowed. They survive only because the override never supplies them."""
    client, _ = api
    before = client.get("/api/workflows/ppt").json()
    _save_override(client, steps=[_step("mine")])
    after = client.get("/api/workflows/ppt").json()

    assert after["deliverable"] == before["deliverable"] == {"strategy": "ppt", "name": "presentation.pptx"}
    assert after["context_providers"] == before["context_providers"]
    assert "opendesign" in after["context_providers"]
    assert after["planner"] == before["planner"]
    assert after["clarify_mode"] == before["clarify_mode"]
    assert after["clarify_defaults"] == before["clarify_defaults"]


def test_original_query_param_shows_the_system_version(api):
    client, _ = api
    before = client.get("/api/workflows/ppt").json()
    _save_override(client, steps=[_step("mine")])

    orig = client.get("/api/workflows/ppt?original=true").json()
    assert orig["showing_original"] is True
    assert orig["is_overridden"] is True  # still reported, so the box renders ticked
    assert [s["agent_id"] for s in orig["steps"]] == [s["agent_id"] for s in before["steps"]]


def test_switching_the_override_off_restores_the_system_steps(api):
    client, _ = api
    before = client.get("/api/workflows/ppt").json()
    ov_id = _save_override(client, steps=[_step("mine")]).json()["id"]

    off = client.patch(f"/api/user-workflows/{ov_id}", json={"override_enabled": False})
    assert off.status_code == 200, off.text

    after = client.get("/api/workflows/ppt").json()
    assert after["is_overridden"] is False
    # ...but the row is still there, so the checkbox renders unticked rather
    # than vanishing with no way back on.
    assert after["has_override"] is True
    assert [s["agent_id"] for s in after["steps"]] == [s["agent_id"] for s in before["steps"]]


def test_saving_twice_updates_one_row(api):
    """'Once, or overwritten always' — the second save must not 409 on the name."""
    client, _ = api
    first = _save_override(client, steps=[_step("one")])
    second = _save_override(client, steps=[_step("one"), _step("two")])
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]

    rows = client.get("/api/user-workflows").json()
    assert len([r for r in rows if r["overrides_pipeline_type"] == "ppt"]) == 1
    assert len(client.get("/api/workflows/ppt").json()["steps"]) == 2


def test_another_users_override_is_invisible(api):
    client, state = api
    _save_override(client, steps=[_step("mine")])

    state["user"] = _FakeUser("someone-else")
    theirs = client.get("/api/workflows/ppt").json()
    assert theirs["is_overridden"] is False
    assert theirs["has_override"] is False
    assert theirs["override_id"] is None


def test_the_listing_reports_the_override_too(api):
    client, _ = api
    _save_override(client, steps=[_step("mine")])
    rows = {w["id"]: w for w in client.get("/api/workflows").json()}
    assert rows["ppt"]["is_overridden"] is True
    assert rows["ppt"]["step_count"] == 1
    # Every other built-in is untouched.
    assert rows["prototype"]["is_overridden"] is False
