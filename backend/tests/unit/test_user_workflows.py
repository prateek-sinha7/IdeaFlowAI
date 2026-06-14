"""Phase 21-01 — owner-scoped ``/api/user-workflows`` CRUD verify gate.

Pins the saved-workflow persistence spine: saved workflows are ``source="user"``
rows in the REUSED ``workflows`` table (REUSE-TABLE-INV12), owner-scoped, with
save-time validation that mirrors the launch predicates (SECURITY-REVALIDATE).
These are the verify gate for the threat-model ``mitigate`` rows:

* **T-21-01 (IDOR / ASVS V4):** GET/PATCH/DELETE ``/{id}`` filter
  ``id==:id AND user_id==current_user.id AND source=="user"`` — a cross-owner or
  missing id resolves to 404, never 403/leak (``test_cross_owner_*_is_404``). The
  list query additionally scopes ``source=="user"`` so a seeded ``source="file"``
  row and another user's row are excluded (``test_list_scopes_to_owner_user_rows``).
* **T-21-02 (Tampering):** POST re-validates ``base_pipeline_type`` /
  ``agent_ids`` / ``model_overrides`` with the SAME predicates the launch path
  uses — a bad value → 422 (the three ``test_post_rejects_*`` tests). Per-user
  name uniqueness is enforced at the API (``test_post_duplicate_name_rejected``).
* **T-21-05 (persistence integrity):** the insert stamps
  ``user_id=owner_id=workspace_id=current_user.id``, ``source="user"``,
  ``artifact_edges="[]"`` (``test_post_persists_owner_stamped_user_row``).

Plus a schema/migration test (``test_model_has_new_columns`` +
``test_migration_adds_then_drops_columns``) proving the 2 additive nullable
columns (ADDITIVE-MIGRATION) appear on the model and reverse cleanly offline.

Drives a FastAPI ``TestClient`` with ``get_current_user`` + ``get_db`` overridden
against an in-memory SQLite session (the ``test_runs_api.py`` harness) — no
Postgres.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.user_workflows import router
from app.core.dependencies import get_current_user
from app.models.database import Base, get_db
from app.models.workflow_definition import WorkflowDefinition

# A valid custom composition (custom needs enterprise tier).
_AGENT_A = "market-research-agent"
_AGENT_B = "report-generator"
_MODEL_ID = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


class _FakeUser:
    """Stand-in for ``app.models.user.User`` — id + tier are read by the API."""

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

    def override_user():
        return state["user"]

    def override_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    return TestClient(app), state


def _make_wf(db, *, wf_id="wf-1", user_id="owner", name="Seeded",
             source="user", agents='["market-research-agent"]', **kw):
    """Seed a WorkflowDefinition row directly (mirror ``_make_run``)."""
    import uuid
    from datetime import datetime, timezone

    row = WorkflowDefinition(
        id=wf_id or str(uuid.uuid4()),
        user_id=user_id,
        owner_id=user_id,
        workspace_id=user_id,
        name=name,
        agents=agents,
        artifact_edges="[]",
        source=source,
        base_pipeline_type=kw.get("base_pipeline_type", "custom"),
        model_overrides=kw.get("model_overrides"),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _valid_body(**over):
    body = {
        "name": "Competitive research",
        "description": "research flow",
        "base_pipeline_type": "custom",
        "agent_ids": [_AGENT_A, _AGENT_B],
        "model_overrides": {_AGENT_A: _MODEL_ID},
    }
    body.update(over)
    return body


# --- POST: create + owner stamp -------------------------------------------


def test_post_persists_owner_stamped_user_row(api, db_session):
    client, _ = api
    r = client.post("/api/user-workflows", json=_valid_body())
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["base_pipeline_type"] == "custom"
    assert data["agent_ids"] == [_AGENT_A, _AGENT_B]
    assert data["model_overrides"] == {_AGENT_A: _MODEL_ID}

    row = db_session.query(WorkflowDefinition).filter_by(id=data["id"]).first()
    assert row.source == "user"
    assert row.artifact_edges == "[]"
    # Self-id stamp (T-21-05).
    assert row.user_id == "owner"
    assert row.owner_id == "owner"
    assert row.workspace_id == "owner"


# --- POST: validation (save == launch) ------------------------------------


def test_post_rejects_unknown_base_pipeline_type(api):
    client, _ = api
    r = client.post(
        "/api/user-workflows",
        json=_valid_body(base_pipeline_type="not_a_real_pipeline"),
    )
    assert r.status_code == 422, r.text


def test_post_rejects_disallowed_agent_id(api):
    client, _ = api
    r = client.post(
        "/api/user-workflows",
        json=_valid_body(agent_ids=["definitely-not-an-allowed-agent"]),
    )
    assert r.status_code == 422, r.text


def test_post_rejects_unknown_model_id(api):
    client, _ = api
    r = client.post(
        "/api/user-workflows",
        json=_valid_body(model_overrides={_AGENT_A: "not-a-real-model"}),
    )
    assert r.status_code == 422, r.text


def test_post_rejects_override_targeting_non_member_agent(api):
    client, _ = api
    # Override key not in agent_ids → rejected (T-06-07 parity).
    r = client.post(
        "/api/user-workflows",
        json=_valid_body(agent_ids=[_AGENT_A], model_overrides={_AGENT_B: _MODEL_ID}),
    )
    assert r.status_code == 422, r.text


def test_post_entitlement_gate_blocks_basic_tier(api):
    client, state = api
    state["user"] = _FakeUser(id="owner", tier="basic")  # custom needs enterprise
    r = client.post("/api/user-workflows", json=_valid_body())
    assert r.status_code == 403, r.text


def test_post_duplicate_name_rejected(api):
    client, _ = api
    assert client.post("/api/user-workflows", json=_valid_body(name="Dup")).status_code == 201
    r = client.post("/api/user-workflows", json=_valid_body(name="Dup"))
    assert r.status_code == 409, r.text


# --- GET list: owner + source scoping -------------------------------------


def test_list_scopes_to_owner_user_rows(api, db_session):
    client, _ = api
    _make_wf(db_session, wf_id="mine", user_id="owner", name="Mine", source="user")
    _make_wf(db_session, wf_id="file", user_id="owner", name="File", source="file")
    _make_wf(db_session, wf_id="other", user_id="someone-else", name="Theirs", source="user")

    r = client.get("/api/user-workflows")
    assert r.status_code == 200
    ids = {row["id"] for row in r.json()}
    assert ids == {"mine"}  # file row + other user's row excluded


# --- IDOR → 404 ------------------------------------------------------------


def test_cross_owner_get_is_404(api, db_session):
    client, state = api
    _make_wf(db_session, wf_id="owned", user_id="owner", source="user")
    state["user"] = _FakeUser(id="attacker")
    assert client.get("/api/user-workflows/owned").status_code == 404


def test_cross_owner_patch_is_404(api, db_session):
    client, state = api
    _make_wf(db_session, wf_id="owned", user_id="owner", source="user")
    state["user"] = _FakeUser(id="attacker")
    r = client.patch("/api/user-workflows/owned", json={"name": "hijacked"})
    assert r.status_code == 404


def test_cross_owner_delete_is_404(api, db_session):
    client, state = api
    _make_wf(db_session, wf_id="owned", user_id="owner", source="user")
    state["user"] = _FakeUser(id="attacker")
    assert client.delete("/api/user-workflows/owned").status_code == 404


def test_get_missing_is_404(api):
    client, _ = api
    assert client.get("/api/user-workflows/nope").status_code == 404


# --- PATCH rename ----------------------------------------------------------


def test_patch_renames_own_row(api, db_session):
    client, _ = api
    _make_wf(db_session, wf_id="r1", user_id="owner", name="Old", source="user")
    r = client.patch("/api/user-workflows/r1", json={"name": "New"})
    assert r.status_code == 200
    assert r.json()["name"] == "New"


# --- DELETE → 204 ----------------------------------------------------------


def test_delete_own_row_then_get_404(api, db_session):
    client, _ = api
    _make_wf(db_session, wf_id="d1", user_id="owner", source="user")
    assert client.delete("/api/user-workflows/d1").status_code == 204
    assert client.get("/api/user-workflows/d1").status_code == 404


# --- Schema / migration (ADDITIVE-MIGRATION) ------------------------------


def test_model_has_new_columns():
    cols = set(WorkflowDefinition.__table__.columns.keys())
    assert "base_pipeline_type" in cols
    assert "model_overrides" in cols
    # Both nullable (additive, no constraint relaxation).
    assert WorkflowDefinition.__table__.columns["base_pipeline_type"].nullable
    assert WorkflowDefinition.__table__.columns["model_overrides"].nullable


def test_migration_adds_then_drops_columns():
    """Offline reversibility: 0021 adds the 2 cols on upgrade and removes them on
    downgrade (no Postgres) — proves ADDITIVE-MIGRATION reverses cleanly."""
    import os
    import tempfile

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    d = tempfile.mkdtemp()
    url = "sqlite:///" + os.path.join(d, "rev.db")
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", "alembic")

    command.upgrade(cfg, "head")
    eng = create_engine(url)
    cols = {c["name"] for c in inspect(eng).get_columns("workflows")}
    assert "base_pipeline_type" in cols and "model_overrides" in cols

    command.downgrade(cfg, "-1")
    eng2 = create_engine(url)
    cols2 = {c["name"] for c in inspect(eng2).get_columns("workflows")}
    assert "base_pipeline_type" not in cols2 and "model_overrides" not in cols2
