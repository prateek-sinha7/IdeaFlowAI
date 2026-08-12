"""tests/unit/test_rest_answers_cancel.py — CHAT-07 / D-13 (29-03).

The up-channel REST twins of ``POST /api/runs/{id}/answers`` (clarify) and
``POST /api/runs/{id}/cancel`` (cooperative cancel), ported from
``test_pipeline_cancel.py`` (+ the WS ``submit_questionnaire`` assertions) against
the REST endpoints. Each endpoint is a thin wrapper over the SAME seams the WS
handlers call (LOCK-B — ``websocket.py`` is untouched):

  * answers → ``store.set_questionnaire_responses(run_id, responses,
    skip_clarification)`` (store.py:62), incl. the ISS-027 force-proceed and the
    ``question_id:"freeform"`` note mapping.
  * cancel  → sets the per-run cooperative ``asyncio.Event`` in
    ``_CANCEL_EVENTS[run_id]`` (ISS-007); the engine observes it and emits
    ``pipeline_cancelled`` through the normal persisted+drained path (suspend/
    persist semantics unchanged). Idempotent ack when nothing is active.

Both are owner-scoped (T-29-03-3): a cross-owner target denies with a
non-revealing 404 (IDOR → 404, never 403), touching no seam.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


class _FakeUser:
    def __init__(self, id: str):
        self.id = id


@pytest.fixture
def env(monkeypatch):
    # W4a (44-03): _get_db + _CANCEL_EVENTS relocated to app.api.run_engine
    # (INV-12 extract-before-delete). Patch the seam at its new home.
    from app.api import run_engine as ws_module
    from app.models.database import Base

    db_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())

    import agents.artifact_store.store as store_mod
    store_mod._STORE = None
    store = store_mod.get_artifact_store()

    # Clean cooperative-cancel + driver-task registries per test (module-globals on
    # ws_module). ISS-084: liveness is decided from _PIPELINE_TASKS, so a leaked entry
    # from another test would make an orphan look live.
    ws_module._CANCEL_EVENTS.clear()
    ws_module._PIPELINE_TASKS.clear()

    from app.api.run_commands import router
    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)

    yield {"ws": ws_module, "store": store, "client": client, "state": state}

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()
    store_mod._STORE = None
    ws_module._CANCEL_EVENTS.clear()
    ws_module._PIPELINE_TASKS.clear()


def _seed_user(env, email_tag: str) -> _FakeUser:
    from app.models.user import User

    db = env["ws"]._get_db()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"rest03ac-{email_tag}-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_run(env, user_id: str, *, status: str = "running") -> str:
    from app.models.workflow import WorkflowRun

    run_id = str(uuid.uuid4())
    db = env["ws"]._get_db()
    try:
        db.add(
            WorkflowRun(
                id=run_id,
                user_id=user_id,
                title="t",
                type="user_stories",
                status=status,
                input="i",
                agent_count=1,
                session_id=user_id,
            )
        )
        db.commit()
        return run_id
    finally:
        db.close()


# ────────────────────────────────────────────────────────────────────────────
# POST /{id}/answers — clarify responses (mirrors WS submit_questionnaire)
# ────────────────────────────────────────────────────────────────────────────


def test_answers_resolve_the_clarify_pause(env):
    """The owner's responses reach the SAME store seam and set the per-run resume
    event the ClarifyEngine awaits."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    env["state"]["user"] = owner
    responses = [{"question_id": "r1_q1", "answer": "yes"}]

    resp = env["client"].post(
        f"/api/runs/{run_id}/answers", json={"responses": responses}
    )
    assert resp.status_code == 200, resp.text
    assert env["store"]._questionnaire_responses[run_id] == responses
    # The resume event fired (clarify loop unblocks).
    assert env["store"]._resume_events[run_id].is_set() is True
    # Ordinary submission does NOT force-proceed (byte-identical default).
    assert env["store"]._questionnaire_force_proceed[run_id] is False


def test_answers_skip_clarification_force_proceeds(env):
    """ISS-027: "Skip all & run directly" flows through ``skip_clarification`` so
    the clarify loop proceeds immediately instead of re-asking."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    env["state"]["user"] = owner

    resp = env["client"].post(
        f"/api/runs/{run_id}/answers",
        json={"responses": [], "skip_clarification": True},
    )
    assert resp.status_code == 200, resp.text
    assert env["store"]._questionnaire_force_proceed[run_id] is True


def test_answers_freeform_maps_to_freeform_question_id(env):
    """The global "anything else" note rides as ``question_id:"freeform"`` (the
    shape the frontend + ClarifyEngine already use)."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    env["state"]["user"] = owner

    resp = env["client"].post(
        f"/api/runs/{run_id}/answers",
        json={"responses": [{"question_id": "r1_q1", "answer": "a"}], "freeform": "note"},
    )
    assert resp.status_code == 200, resp.text
    stored = env["store"]._questionnaire_responses[run_id]
    assert {"question_id": "freeform", "answer": "note"} in stored


def test_answers_cross_owner_is_denied(env):
    """T-29-03-3: a cross-owner clarify submission denies with a non-revealing
    404 and never touches the seam (no resume event, no responses)."""
    victim = _seed_user(env, "victim")
    attacker = _seed_user(env, "attacker")
    run_id = _seed_run(env, victim.id)
    env["state"]["user"] = attacker

    resp = env["client"].post(
        f"/api/runs/{run_id}/answers",
        json={"responses": [{"question_id": "r1_q1", "answer": "x"}]},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown gate_key"
    assert run_id not in env["store"]._questionnaire_responses
    assert run_id not in env["store"]._resume_events


def test_answers_unknown_run_is_denied(env):
    caller = _seed_user(env, "caller")
    env["state"]["user"] = caller
    run_id = str(uuid.uuid4())

    resp = env["client"].post(
        f"/api/runs/{run_id}/answers", json={"responses": []}
    )
    assert resp.status_code == 404


# ────────────────────────────────────────────────────────────────────────────
# POST /{id}/cancel — cooperative cancel (mirrors WS cancel_pipeline)
# ────────────────────────────────────────────────────────────────────────────


def test_cancel_sets_the_cooperative_event(env):
    """ISS-007: a Stop over HTTP sets the per-run cooperative ``cancel_event``
    (never a destructive task kill) — the engine observes it and emits the clean
    ``pipeline_cancelled`` terminal through the normal drained path.

    ISS-084 reconcile: this test used to seed ONLY ``_CANCEL_EVENTS`` and assert the
    endpoint set it, which made its own docstring premise ("a live run has an armed cancel
    event") unfalsifiable — in production that entry was an orphan for every resumed run.
    The premise is now made TRUE by seeding the driver task as well, and the assertion is
    on the honest ``accepted`` acknowledgement rather than the unearned ``cancelled``.
    """
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    # A live run has an armed cancel event AND a driver task that can observe it.
    env["ws"]._CANCEL_EVENTS[run_id] = asyncio.Event()
    env["ws"]._PIPELINE_TASKS[run_id] = object()
    env["state"]["user"] = owner

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is True
    assert body["status"] == "stopping"
    assert env["ws"]._CANCEL_EVENTS[run_id].is_set() is True


def test_cancel_does_not_claim_success_without_a_live_driver(env):
    """ISS-084 — the anti-lie test. A ``_CANCEL_EVENTS`` entry with no in-process driver
    is an ORPHAN: setting it stops nothing, because nothing holds it. The endpoint must
    not report success for it.

    This is the shape that cost the owner 7,510,082 tokens: ``POST /cancel`` answered
    ``HTTP 200 {"cancelled": true}`` and the run went on to complete, emitting zero
    ``pipeline_cancelled`` events. The API asserted a result it had never verified.
    """
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    env["ws"]._CANCEL_EVENTS[run_id] = asyncio.Event()  # orphan: no driver task
    env["state"]["user"] = owner

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is False, (
        f"the endpoint claimed a cancellation nothing could perform: {body}"
    )
    assert body["cancelled"] is False
    assert body["status"] == "not_running"


def test_cancel_is_idempotent_with_no_active_event(env):
    """No active pipeline → an idempotent ack (nothing to cancel), so the client
    UI state machine can return to idle."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    env["state"]["user"] = owner  # no _CANCEL_EVENTS entry

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is False
    assert body["cancelled"] is False
    assert body["message"] == "No active pipeline"


def test_cancel_cross_owner_is_denied_and_does_not_fire_event(env):
    """T-29-03-3: a cross-owner Stop denies with 404 and must NOT set the
    victim's cooperative event (IDOR → 404, never 403)."""
    victim = _seed_user(env, "victim")
    attacker = _seed_user(env, "attacker")
    run_id = _seed_run(env, victim.id)
    env["ws"]._CANCEL_EVENTS[run_id] = asyncio.Event()
    env["state"]["user"] = attacker

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown gate_key"
    assert env["ws"]._CANCEL_EVENTS[run_id].is_set() is False


def test_cancel_unknown_run_is_denied(env):
    caller = _seed_user(env, "caller")
    env["state"]["user"] = caller
    run_id = str(uuid.uuid4())

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 404
