"""ISS-1112 — every writer of an override row must refuse steps the read side refuses.

Caller is BASIC tier on purpose: the override of `ppt` is not tier-gated.
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
from app.core.dependencies import get_current_principal, get_current_user
from app.models.database import Base, get_db
from tests.fakes.principal import principal_for


class _FakeUser:
    def __init__(self, id: str, tier: str):
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
    user = _FakeUser("owner", "basic")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_principal] = lambda: (
        user,
        principal_for(user),
    )

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        yield TestClient(app), session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _step(iid, **over):
    s = {
        "agent": "custom-agent",
        "instance_id": iid,
        "name": iid,
        "prompt": f"You are {iid}.",
        "tools": {"read_files": False, "write_files": False, "exec": False},
    }
    s.update(over)
    return s


BAD = _step("mine", gates=["security"])


def _post(client, steps):
    return client.post(
        "/api/user-workflows",
        json={
            "name": "My Deck",
            "base_pipeline_type": "ppt",
            "agent_ids": ["ppt-brief-analyst"],
            "manifest": {"steps": steps},
            "overrides_pipeline_type": "ppt",
        },
    )


@pytest.mark.issue("ISS-1112")
def test_post_insert_of_a_smuggled_override_is_refused(api):
    client, _ = api
    resp = _post(client, [BAD])
    assert resp.status_code == 422, resp.text


@pytest.mark.issue("ISS-1112")
def test_post_upsert_of_a_smuggled_override_is_refused(api):
    client, _ = api
    assert _post(client, [_step("benign")]).status_code == 201
    resp = _post(client, [BAD])
    assert resp.status_code == 422, resp.text


@pytest.mark.issue("ISS-1112")
def test_patch_of_an_override_to_a_smuggled_step_is_refused(api):
    client, _ = api
    rid = _post(client, [_step("benign")])
    assert rid.status_code == 201, rid.text
    resp = client.patch(
        f"/api/user-workflows/{rid.json()['id']}", json={"manifest": {"steps": [BAD]}}
    )
    assert resp.status_code == 422, resp.text
