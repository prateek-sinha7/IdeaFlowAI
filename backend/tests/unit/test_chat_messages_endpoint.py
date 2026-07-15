"""tests/unit/test_chat_messages_endpoint.py — CHAT-01/CHAT-02/CHAT-05 (29-09).

The chat backbone up-channel ``POST /api/runs/{id}/messages``, proven OFFLINE (TestClient
+ in-memory SQLite scoped store; no live Bedrock / uvicorn). Two halves:

  * **Task 1 — persist + idempotency + owner 404**: a turn persists as ONE
    ``chat_message`` ``run_events`` row via ``ScopedStore.append_event`` (zero new
    tables, D-01); a replayed ``message_id`` is a no-op (no second row); a cross-owner
    run → 404 (IDOR → 404, never 403).
  * **Task 3 — routing**: the persisted turn is delivered by the mechanical router per
    run state — clarify → answers seam ; gate → gate seam (4 actions incl. update_specs) ;
    running → steering ; terminal → revision ; a gate action after terminal → fenced.

LOCK-B: drives the REAL endpoint; touches NO production file beyond the allow-list.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

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
    from app.api import run_commands as rc_module
    from app.api import run_engine as ws_module
    from app.models import database as db_module
    from app.models.database import Base

    db_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)

    # Patch _get_db on BOTH modules: run_commands binds its OWN reference at import
    # (``from app.api.run_engine import _get_db``), so patching ws_module alone would
    # leave the endpoint's Layer-1 query on the real DB.
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(rc_module, "_get_db", lambda: TestingSession())
    # ScopedStore(session=None) opens app.models.database.SessionLocal() — bind it too so
    # the endpoint's store hits the in-memory DB.
    monkeypatch.setattr(db_module, "SessionLocal", TestingSession)

    import agents.artifact_store.store as store_mod
    store_mod._STORE = None
    store = store_mod.get_artifact_store()

    from app.api.run_commands import router
    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)

    yield {
        "ws": ws_module,
        "store": store,
        "client": client,
        "state": state,
        "Session": TestingSession,
    }

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()
    store_mod._STORE = None


def _seed_user(env, tag: str) -> _FakeUser:
    from app.models.user import User

    db = env["Session"]()
    try:
        u = User(id=str(uuid.uuid4()),
                 email=f"chat09-{tag}-{uuid.uuid4().hex[:8]}@example.com",
                 password_hash="x")
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_run(env, user_id: str, *, status: str = "running",
              workspace_id: str = "ws-1") -> str:
    """A scoped run (owner_id + workspace_id set — the engine's set_run_scope has run),
    so the Layer-2 default-deny ``get_run`` resolves it and its events are readable."""
    from app.models.workflow import WorkflowRun

    run_id = str(uuid.uuid4())
    db = env["Session"]()
    try:
        db.add(WorkflowRun(
            id=run_id, user_id=user_id, owner_id=user_id, workspace_id=workspace_id,
            title="t", type="prototype", status=status, input="i",
            agent_count=1, session_id=user_id, created_at=datetime.now(timezone.utc),
        ))
        db.commit()
        return run_id
    finally:
        db.close()


def _seed_events(env, run_id, rows, *, owner_id, workspace_id="ws-1"):
    from app.models.run_event import RunEvent

    db = env["Session"]()
    try:
        for seq, etype, payload in rows:
            db.add(RunEvent(
                id=str(uuid.uuid4()), run_id=run_id, owner_id=owner_id,
                workspace_id=workspace_id, seq=seq, event_id=str(uuid.uuid4()),
                type=etype, payload_json=payload,
            ))
        db.commit()
    finally:
        db.close()


def _chat_rows(env, run_id):
    from app.models.run_event import RunEvent

    db = env["Session"]()
    try:
        return (
            db.query(RunEvent)
            .filter(RunEvent.run_id == run_id, RunEvent.type == "chat_message")
            .order_by(RunEvent.seq.asc())
            .all()
        )
    finally:
        db.close()


def _post(env, run_id, **body):
    body.setdefault("message_id", uuid.uuid4().hex)
    return env["client"].post(f"/api/runs/{run_id}/messages", json=body)


# ════════════════════════════════════════════════════════════════════════════
# Task 1 — persist + idempotency + owner 404
# ════════════════════════════════════════════════════════════════════════════
class TestPersist:
    def test_turn_persists_as_chat_message_row(self, env):
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id)
        env["state"]["user"] = owner

        resp = _post(env, run_id, text="hello run", message_id="m-1")
        assert resp.status_code == 200, resp.text
        assert resp.json()["persisted"] is True

        rows = _chat_rows(env, run_id)
        assert len(rows) == 1
        assert rows[0].type == "chat_message"
        assert rows[0].payload_json["message_id"] == "m-1"
        assert rows[0].payload_json["text"] == "hello run"
        assert rows[0].event_id == "chat:m-1"  # event_id derived from message_id

    def test_seq_is_next_after_existing_events(self, env):
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id)
        _seed_events(env, run_id, [(1, "agent_start", {}), (2, "agent_chunk", {})],
                     owner_id=owner.id)
        env["state"]["user"] = owner

        resp = _post(env, run_id, text="hi", message_id="m-2")
        assert resp.json()["seq"] == 3  # max(1,2)+1

    def test_replayed_message_id_is_noop(self, env):
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id)
        env["state"]["user"] = owner

        r1 = _post(env, run_id, text="once", message_id="dup")
        r2 = _post(env, run_id, text="once", message_id="dup")  # replay
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["persisted"] is True
        assert r2.json()["persisted"] is False  # idempotent no-op
        assert r2.json()["seq"] == r1.json()["seq"]
        assert len(_chat_rows(env, run_id)) == 1  # exactly ONE row

    def test_attachments_are_not_retained(self, env):
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id)
        env["state"]["user"] = owner

        resp = _post(env, run_id, text="see pic", message_id="m-att",
                     attachments=[{"kind": "image", "data": "BIGBASE64"}])
        assert resp.status_code == 200
        stored = _chat_rows(env, run_id)[0].payload_json["attachments"]
        assert stored == [{"kind": "image", "retained": False}]  # bytes NOT persisted

    def test_cross_owner_is_404(self, env):
        owner = _seed_user(env, "owner")
        attacker = _seed_user(env, "attacker")
        run_id = _seed_run(env, owner.id)
        env["state"]["user"] = attacker

        resp = _post(env, run_id, text="intrude", message_id="m-x")
        assert resp.status_code == 404
        assert resp.status_code != 403  # never leak run existence via 403
        assert _chat_rows(env, run_id) == []  # no write past the owner boundary

    def test_missing_run_is_404(self, env):
        caller = _seed_user(env, "caller")
        env["state"]["user"] = caller
        resp = _post(env, str(uuid.uuid4()), text="ghost", message_id="m-g")
        assert resp.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# Task 3 — mechanical routing: each run state → the correct command seam
# ════════════════════════════════════════════════════════════════════════════
def _arm_review(env, gate_key):
    env["store"]._resume_events[f"review:{gate_key}"] = asyncio.Event()


class TestRouting:
    def test_clarify_waiting_routes_to_answers_seam(self, env):
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="waiting_for_user")
        _seed_events(env, run_id, [(1, "questionnaire_ready", {})], owner_id=owner.id)
        env["state"]["user"] = owner

        resp = _post(env, run_id, text="dark mode please", message_id="m-c")
        assert resp.status_code == 200, resp.text
        assert resp.json()["channel"] == "answers"
        recorded = env["store"]._questionnaire_responses.get(run_id)
        assert recorded == [{"question_id": "freeform", "answer": "dark mode please"}]

    def test_gate_paused_routes_to_gate_seam_approve(self, env):
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="waiting_for_user")
        gate_key = f"{run_id}:prototype-specify"
        _seed_events(env, run_id, [(1, "review_gate_ready", {"gate_key": gate_key})],
                     owner_id=owner.id)
        _arm_review(env, gate_key)
        env["state"]["user"] = owner

        resp = _post(env, run_id, message_id="m-g1")  # default action approve
        assert resp.json()["channel"] == "gate"
        recorded = env["store"]._questionnaire_responses.get(f"review:{gate_key}")
        assert recorded and recorded[0]["approved"] is True

    def test_gate_update_specs_routes_to_kan101(self, env):
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="waiting_for_user")
        gate_key = f"{run_id}:prototype-analyze"
        _seed_events(env, run_id, [(1, "review_gate_ready", {"gate_key": gate_key})],
                     owner_id=owner.id)
        _arm_review(env, gate_key)
        env["state"]["user"] = owner

        resp = _post(env, run_id, action="update_specs", analysis_report="RPT",
                     message_id="m-us")
        assert resp.json()["channel"] == "gate"
        recorded = env["store"]._questionnaire_responses.get(f"review:{gate_key}")
        assert recorded[0]["action"] == "update_specs"
        assert recorded[0]["instructions"] == "RPT"

    def test_gate_redo_carries_instructions(self, env):
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="waiting_for_user")
        gate_key = f"{run_id}:prototype-specify"
        _seed_events(env, run_id, [(1, "review_gate_ready", {"gate_key": gate_key})],
                     owner_id=owner.id)
        _arm_review(env, gate_key)
        env["state"]["user"] = owner

        resp = _post(env, run_id, action="redo", text="tighten header", message_id="m-r")
        assert resp.json()["channel"] == "gate"
        recorded = env["store"]._questionnaire_responses.get(f"review:{gate_key}")
        assert recorded[0]["action"] == "redo"
        assert recorded[0]["instructions"] == "tighten header"

    def test_excluded_gate_not_pending_routes_to_steering(self, env):
        """KAN-94: a dangling review_gate_ready with NO armed store event (an agent the
        engine skipped via gate_agent_ids) is NOT a pause — the turn steers instead."""
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="running")
        gate_key = f"{run_id}:skipped-agent"
        _seed_events(env, run_id, [(1, "review_gate_ready", {"gate_key": gate_key})],
                     owner_id=owner.id)
        # NOT armed — KAN-94 ground truth says no genuine pause.
        env["state"]["user"] = owner

        resp = _post(env, run_id, text="keep going", message_id="m-k")
        assert resp.json()["channel"] == "steering"
        # No gate resolution written (the gate was never pending).
        assert env["store"]._questionnaire_responses.get(f"review:{gate_key}") is None

    def test_running_routes_to_steering(self, env):
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="running")
        _seed_events(env, run_id, [(1, "agent_start", {}), (2, "agent_chunk", {})],
                     owner_id=owner.id)
        env["state"]["user"] = owner

        resp = _post(env, run_id, text="prefer teal", message_id="m-s")
        assert resp.status_code == 200
        assert resp.json()["channel"] == "steering"
        # The turn is durably recorded as a chat_message (the steering record, ND-9).
        rows = _chat_rows(env, run_id)
        assert len(rows) == 1 and rows[0].payload_json["text"] == "prefer teal"

    def test_terminal_routes_to_revision(self, env, monkeypatch):
        from app.api import run_commands as rc_module
        from app.models.workflow import WorkflowRun

        async def _noop_drive(**kwargs):
            return None

        monkeypatch.setattr(rc_module, "_drive_revision_to_queue", _noop_drive)

        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="completed")
        env["state"]["user"] = owner

        resp = _post(env, run_id, text="make the CTA bigger", message_id="m-rev")
        assert resp.status_code == 200, resp.text
        assert resp.json()["channel"] == "revision"
        child_id = resp.json()["revision_run_id"]

        db = env["Session"]()
        try:
            child = db.query(WorkflowRun).filter(WorkflowRun.id == child_id).first()
            assert child is not None
            assert child.parent_run_id == run_id
            assert child.type.endswith("_revision")
        finally:
            db.close()

    def test_gate_action_after_terminal_is_fenced(self, env):
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="cancelled")
        env["state"]["user"] = owner

        resp = _post(env, run_id, action="approve", message_id="m-f")
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "pipeline_not_running"
        assert resp.json()["detail"]["recoverable"] is False
