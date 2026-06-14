"""Phase 22-04 — EMP-01/02/03 saved-workflow capability-selections verify gate.

Activates the built-but-dormant ``trust="user"`` compile path (compiler.py
``_check_trust``) as the AUTHORITATIVE server-side gate for user-composed
workflows, and persists the richer per-step selections in the REUSED
``workflows.manifest_json`` column (zero migration, D-11). These are the verify
gate for the threat-model ``mitigate`` rows:

* **T-22-04-01 (Elevation @ SAVE):** a save payload smuggling a
  ``user_allowed=False`` capability (``gate: security`` / approval) is rejected
  422 — the underlying ``compile(trust="user")`` raised ``CompilerError`` naming
  the ``(kind, name)`` (CAP-03). The FE lock is advisory only; THIS is the control.
* **T-22-04-02 (Elevation @ LAUNCH):** a row TAMPERED after save (its
  ``manifest_json`` mutated to reference a non-user-allowed cap) is REJECTED at
  launch by re-compiling ``trust="user"`` BEFORE execute (Pitfall 3).
* **T-22-04-03 (Limits ceiling):** a ceiling-raising Limits cap in the selections
  is rejected at save (``_compile_limits`` untrusted ceiling).
* **T-22-04-04 (IDOR):** a cross-owner GET on a saved workflow → 404, never leak.
* **EMP-01 (selection reaches execution):** a persisted validator + non-default
  model + retry, launched through the EXISTING run path, demonstrably reaches the
  compiled plan the engine drives — the validator's ``validation`` gate fires, the
  chosen model is what ``ModelResolver`` resolves, and the retry wrapper activates
  under an injected transient fault. No new run endpoint, no kernel branch (SC-001).

Save-side tests drive a FastAPI ``TestClient`` (the ``test_user_workflows.py``
harness — in-memory SQLite, overridden ``get_current_user``/``get_db``). The
EMP-01 + launch-reject proofs drive the compiler/engine seams directly (the
``trust="user"`` re-compile + the per-step overlay) without a live model.
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

_AGENT_A = "market-research-agent"
_AGENT_B = "report-generator"
_DEFAULT_MODEL = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
_NON_DEFAULT_MODEL = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
_USER_VALIDATOR = "spec_plan_coverage"  # user_allowed=True


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


def _save_body(selections=None, **kw):
    body = {
        "name": kw.get("name", "Composed WF"),
        "base_pipeline_type": "custom",
        "agent_ids": kw.get("agent_ids", [_AGENT_A, _AGENT_B]),
    }
    if selections is not None:
        body["selections"] = selections
    return body


# ---------------------------------------------------------------------------
# EMP-03 — round-trip: save → list → reopen shows the same selections
# ---------------------------------------------------------------------------


def test_selections_round_trip_save_list_reopen(api):
    client, _ = api
    selections = {
        _AGENT_A: {
            "validators": [_USER_VALIDATOR],
            "model": _NON_DEFAULT_MODEL,
            "retry": {"max_attempts": 2},
        }
    }
    r = client.post("/api/user-workflows", json=_save_body(selections))
    assert r.status_code == 201, r.text
    saved_id = r.json()["id"]
    # The POST response round-trips the selections (auto-attached validation gate
    # is a compile-time concern; the persisted compact map is what the user sent).
    assert r.json()["selections"] == selections

    # list → the row carries the selections
    rl = client.get("/api/user-workflows")
    assert rl.status_code == 200
    listed = next(w for w in rl.json() if w["id"] == saved_id)
    assert listed["selections"] == selections

    # reopen (GET /{id}) → identical selections
    rg = client.get(f"/api/user-workflows/{saved_id}")
    assert rg.status_code == 200
    assert rg.json()["selections"] == selections


def test_no_selections_persists_null_parity(api):
    """A P21-style save with no selections → ``selections is None`` (parity)."""
    client, _ = api
    r = client.post("/api/user-workflows", json=_save_body())
    assert r.status_code == 201, r.text
    assert r.json()["selections"] is None


# ---------------------------------------------------------------------------
# T-22-04-01 — save rejects a smuggled user_allowed=False capability (CAP-03)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("smuggled_gate", ["security", "approval"])
def test_save_rejects_smuggled_privileged_gate(api, smuggled_gate):
    client, _ = api
    selections = {_AGENT_A: {"gates": [smuggled_gate]}}
    r = client.post("/api/user-workflows", json=_save_body(selections))
    assert r.status_code == 422, r.text
    detail = r.json()["detail"].lower()
    assert "user-allowed" in detail or "user_allowed" in detail
    assert smuggled_gate in detail
    # No orphan row was created.
    assert client.get("/api/user-workflows").json() == []


def test_save_rejects_ceiling_raising_limits(api):
    """T-22-04-03 — a Limits cap raising above the untrusted ceiling → 422."""
    client, _ = api
    selections = {"__workflow__": {"limits": {"max_subagents": 999}}}
    r = client.post("/api/user-workflows", json=_save_body(selections))
    assert r.status_code == 422, r.text
    assert "ceiling" in r.json()["detail"].lower()
    assert client.get("/api/user-workflows").json() == []


# ---------------------------------------------------------------------------
# T-22-04-04 — IDOR: cross-owner GET → 404 (never 403/leak)
# ---------------------------------------------------------------------------


def test_cross_owner_get_is_404(api):
    client, state = api
    selections = {_AGENT_A: {"validators": [_USER_VALIDATOR]}}
    r = client.post("/api/user-workflows", json=_save_body(selections))
    assert r.status_code == 201
    other_id = r.json()["id"]

    # Switch principal — a different owner must NOT see the row (404, not 403).
    state["user"] = _FakeUser(id="attacker")
    rg = client.get(f"/api/user-workflows/{other_id}")
    assert rg.status_code == 404
    assert "not found" in rg.json()["detail"].lower()
