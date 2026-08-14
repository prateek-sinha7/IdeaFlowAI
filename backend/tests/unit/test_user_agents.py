"""Saved custom agents — owner-scoped ``/api/user-agents`` CRUD.

Mirrors ``test_user_workflows.py``'s harness: a ``TestClient`` with
``get_current_user`` + ``get_db`` overridden, an in-memory SQLite schema, and a
mutable ``state["user"]`` so a test can switch principal mid-request-sequence to
prove cross-owner isolation.

The security assertions are the point of this file:
  * a cross-owner id resolves to **404, not 403** — the endpoint must never
    confirm that another user's agent exists
  * a list is scoped to the caller
  * the create path stamps ``owner_id``/``workspace_id`` (AUTHZ-01)
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.user_agents import router
from app.core.dependencies import get_current_user
from app.models.database import Base, get_db
from app.models.user_agent import UserAgent


class _FakeUser:
    def __init__(self, id: str, tier: str = "enterprise"):
        self.id = id
        self.tier = tier


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def api(db_session):
    """Returns ``(client, state)`` — mutate ``state["user"]`` to switch principal."""
    app = FastAPI()
    app.include_router(router)

    state: dict = {"user": _FakeUser(id="owner")}

    app.dependency_overrides[get_current_user] = lambda: state["user"]

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app), state


_BODY = {"name": "Summariser", "prompt": "Summarise the input in one line.", "skills": []}


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------

def test_create_returns_201_and_stamps_ownership(api, db_session):
    client, _ = api
    r = client.post("/api/user-agents", json=_BODY)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Summariser"
    assert body["prompt"] == "Summarise the input in one line."
    assert body["skills"] == []

    # AUTHZ-01: every new table carries owner_id + workspace_id, stamped to the
    # creating principal.
    row = db_session.query(UserAgent).filter(UserAgent.id == body["id"]).one()
    assert row.user_id == "owner"
    assert row.owner_id == "owner"
    assert row.workspace_id == "owner"


def test_list_get_update_delete_roundtrip(api):
    client, _ = api
    created = client.post("/api/user-agents", json=_BODY).json()
    agent_id = created["id"]

    assert [a["id"] for a in client.get("/api/user-agents").json()] == [agent_id]
    assert client.get(f"/api/user-agents/{agent_id}").json()["name"] == "Summariser"

    r = client.patch(
        f"/api/user-agents/{agent_id}",
        json={**_BODY, "name": "Renamed", "prompt": "New prompt."},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"
    assert r.json()["prompt"] == "New prompt."

    assert client.delete(f"/api/user-agents/{agent_id}").status_code == 204
    assert client.get(f"/api/user-agents/{agent_id}").status_code == 404
    assert client.get("/api/user-agents").json() == []


# --------------------------------------------------------------------------
# Ownership — the reason this file exists
# --------------------------------------------------------------------------

def test_cross_owner_read_is_404_not_403(api):
    """IDOR→404: a 403 would confirm the row exists for someone else."""
    client, state = api
    agent_id = client.post("/api/user-agents", json=_BODY).json()["id"]

    state["user"] = _FakeUser(id="intruder")
    r = client.get(f"/api/user-agents/{agent_id}")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_cross_owner_update_and_delete_are_404(api, db_session):
    client, state = api
    agent_id = client.post("/api/user-agents", json=_BODY).json()["id"]

    state["user"] = _FakeUser(id="intruder")
    assert client.patch(f"/api/user-agents/{agent_id}", json=_BODY).status_code == 404
    assert client.delete(f"/api/user-agents/{agent_id}").status_code == 404

    # And the row survived both attempts.
    assert db_session.query(UserAgent).filter(UserAgent.id == agent_id).one().name == (
        "Summariser"
    )


def test_list_is_scoped_to_caller(api):
    client, state = api
    client.post("/api/user-agents", json=_BODY)

    state["user"] = _FakeUser(id="other")
    assert client.get("/api/user-agents").json() == []

    # The other user may reuse the same NAME — uniqueness is per-user, not global.
    assert client.post("/api/user-agents", json=_BODY).status_code == 201
    assert len(client.get("/api/user-agents").json()) == 1


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def test_duplicate_name_for_same_user_is_409(api):
    client, _ = api
    assert client.post("/api/user-agents", json=_BODY).status_code == 201
    r = client.post("/api/user-agents", json=_BODY)
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]


def test_rename_onto_an_existing_name_is_409_but_self_rename_is_fine(api):
    client, _ = api
    first = client.post("/api/user-agents", json=_BODY).json()
    client.post("/api/user-agents", json={**_BODY, "name": "Second"})

    # Renaming `first` onto the taken name collides...
    assert client.patch(
        f"/api/user-agents/{first['id']}", json={**_BODY, "name": "Second"}
    ).status_code == 409
    # ...but saving `first` under its OWN name must not collide with itself.
    assert client.patch(
        f"/api/user-agents/{first['id']}", json=_BODY
    ).status_code == 200


def test_unknown_skill_id_is_rejected(api):
    client, _ = api
    r = client.post(
        "/api/user-agents", json={**_BODY, "skills": ["definitely-not-a-real-skill"]}
    )
    assert r.status_code == 422
    assert "Unknown skill ids" in r.json()["detail"]


def test_blank_name_is_rejected(api):
    client, _ = api
    assert client.post("/api/user-agents", json={**_BODY, "name": "   "}).status_code == 422


def test_too_many_skills_is_rejected(api):
    client, _ = api
    r = client.post("/api/user-agents", json={**_BODY, "skills": [f"s{i}" for i in range(50)]})
    assert r.status_code == 422
    assert "At most" in r.json()["detail"]


def test_oversized_prompt_is_rejected_by_the_schema(api):
    client, _ = api
    r = client.post("/api/user-agents", json={**_BODY, "prompt": "x" * 20_001})
    assert r.status_code == 422
