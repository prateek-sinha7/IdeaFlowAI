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
import inspect
import json
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
        # RECONCILED on the 2026-08-13 `dev` merge (was an exact-dict equality). dev's
        # FIX-218 (KAN-170) additionally persists the attachment METADATA — name /
        # mimeType / sizeBytes — so the transcript can show a filename on replay. That
        # is a deliberate behaviour change, so the exact-equality form was over-strict.
        # What ND-10 actually requires, and what this test now pins, is that the BYTES
        # never reach the durable row. Asserting the invariant, not the dict shape.
        assert len(stored) == 1
        assert stored[0]["kind"] == "image"
        assert stored[0]["retained"] is False
        assert "data" not in stored[0]                     # the bytes NEVER persist
        assert "BIGBASE64" not in json.dumps(stored)       # nor anywhere else in the row

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
    @pytest.fixture(autouse=True)
    def _no_live_concierge(self, monkeypatch):
        """ISS-102 — keep this class's Concierge seam off the wire. DO NOT DELETE.

        A bare-text turn at ``PHASE_CLARIFY_WAITING`` / ``PHASE_GATE_PAUSED`` is
        *deliberately* routed to ``CHANNEL_CONCIERGE`` by
        ``app/api/chat_router.py::route_chat_turn`` — a plain text turn must NOT be
        auto-submitted as a freeform clarify answer, and must NOT default to
        ``approve``. The REAL ``ConciergeCapability`` resolved by
        ``run_commands._resolve_concierge`` (:918, called at :1442) carries
        ``model=None``, so it goes ``build_model()`` → ``ChatBedrockConverse`` → a live
        AWS ``ConverseStream`` call that bills real money.

        Class-wide rather than per-test because only 2 of the 8 methods reach the seam
        today but any of them could tomorrow; a per-test patch on the other 6 would be
        dead code (INV-12, "no shadows"). ``_StreamingConcierge`` is defined later in
        this file — the body resolves it as a module global at call time.
        """
        from app.api import run_commands as rc_module

        fake = _StreamingConcierge()
        monkeypatch.setattr(rc_module, "_resolve_concierge", lambda: fake)

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


# ════════════════════════════════════════════════════════════════════════════
# BE-2 — the fresh-Concierge POST streams as text/event-stream (Option B).
# ════════════════════════════════════════════════════════════════════════════
def _parse_sse_frames(text: str) -> list[dict]:
    """Parse the ``{type, data}`` JSON bodies out of an SSE response body.

    Each frame's wire is ``id: {seq}\\ndata: {json}\\n\\n``; we read only the
    ``data:`` lines (the ``{type, data}`` envelope the FE SSE reader consumes).
    """
    frames: list[dict] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload:
                frames.append(json.loads(payload))
    return frames


def _events_of_type(env, run_id, etype):
    from app.models.run_event import RunEvent

    db = env["Session"]()
    try:
        return (
            db.query(RunEvent)
            .filter(RunEvent.run_id == run_id, RunEvent.type == etype)
            .order_by(RunEvent.seq.asc())
            .all()
        )
    finally:
        db.close()


class _StreamingConcierge:
    """A scripted concierge (no live model): ``converse`` streams two deltas via the
    ``on_chunk`` sink then returns the full text, and surfaces one held gate proposal."""

    def __init__(self, deltas=("Hel", "lo"), answer="Hello", usage=None):
        self._deltas = list(deltas)
        self._answer = answer
        # ISS-092 — the OBSERVED model spend this turn, surfaced on the ctx exactly as
        # the real capability does. ``None`` models a converse that reported nothing:
        # the endpoint must then write NO chat_usage row (unmeasured is never invented).
        self._usage = usage
        self.seen: list = []
        # c72 — capture the ctx.chain_hints threaded onto each converse turn.
        self.seen_hints: list = []

    async def converse(self, ctx, user_message, on_chunk=None):
        self.seen.append(user_message)
        self.seen_hints.append(getattr(ctx, "chain_hints", None))
        if self._usage is not None:
            ctx.usage = dict(self._usage)
        for delta in self._deltas:
            if on_chunk is not None:
                res = on_chunk(delta)
                if inspect.isawaitable(res):
                    await res
        return self._answer

    def drain_proposals(self, ctx=None):
        from app.agents.chat.concierge import ProposalIntent

        return [ProposalIntent(channel="gate_action", params={"action": "approve"})]


class TestConciergeStreaming:
    def test_fresh_concierge_post_streams_chunks_then_terminal_reply(self, env, monkeypatch):
        """A fresh-Concierge POST responds text/event-stream: ordered chat_reply_chunk
        frames, then ONE terminal chat_reply carrying the full text + held proposals.
        The durable chat_reply row + the held proposal row persist regardless."""
        from app.api import run_commands as rc_module

        fake = _StreamingConcierge()
        monkeypatch.setattr(rc_module, "_resolve_concierge", lambda: fake)

        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="completed")
        env["state"]["user"] = owner

        resp = _post(env, run_id, text="what's the status?", concierge=True,
                     message_id="s1")
        assert resp.status_code == 200, resp.text
        # BE-2: the fresh-Concierge branch now streams the POST body.
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert fake.seen == ["what's the status?"]

        frames = _parse_sse_frames(resp.text)
        # Ordered transient chunk frames — the model's text deltas, in order.
        chunks = [f for f in frames if f["type"] == "chat_reply_chunk"]
        assert [c["data"]["delta"] for c in chunks] == ["Hel", "lo"]
        # Exactly ONE terminal chat_reply carrying the full concatenated answer.
        terminals = [f for f in frames if f["type"] == "chat_reply"]
        assert len(terminals) == 1
        assert terminals[0]["data"]["text"] == "Hello"
        assert terminals[0]["data"]["message_id"] == "s1"
        # Issue-3 guard: the STREAMED terminal carries the SAME distinct event_id as
        # the durable row (below), so the FE keys the reply on `chat-reply:{id}`
        # (merging the streamed bubble) instead of the bare message_id — which equals
        # the user turn's id and would OVERWRITE the user's bubble (BUG-018 regression).
        assert terminals[0]["data"]["event_id"] == "chat-reply:s1"
        assert terminals[0]["data"]["proposals"], "held proposals ride the terminal frame"
        assert terminals[0]["data"]["proposals"][0]["held"] is True

        # DURABLE side-effects landed regardless of client consumption: the single
        # canonical chat_reply row (event_id chat-reply:{message_id}, seq present) …
        replies = _events_of_type(env, run_id, "chat_reply")
        assert len(replies) == 1
        assert replies[0].event_id == "chat-reply:s1"
        assert replies[0].seq is not None
        assert replies[0].payload_json["text"] == "Hello"
        # … and NO transient chunk was ever persisted (the terminal is the only record).
        assert _events_of_type(env, run_id, "chat_reply_chunk") == []
        # … and the held proposal was written (behind the confirm chip, not executed).
        assert len(_events_of_type(env, run_id, "concierge_proposal")) == 1

    def test_chain_hints_reach_concierge_ctx(self, env, monkeypatch):
        """c72: a fresh-Concierge POST threads body.chain_hints onto the ctx handed to
        converse; a POST without chain_hints carries the degrade-safe [] default."""
        from app.api import run_commands as rc_module

        fake = _StreamingConcierge()
        monkeypatch.setattr(rc_module, "_resolve_concierge", lambda: fake)

        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="completed")
        env["state"]["user"] = owner

        # POST WITH chain_hints → the ctx carries them.
        r1 = _post(env, run_id, text="what can I do next?", concierge=True,
                   chain_hints=[{"id": "ppt", "label": "Presentation"}], message_id="h1")
        assert r1.status_code == 200, r1.text
        # POST WITHOUT chain_hints → the ctx carries the [] default.
        r2 = _post(env, run_id, text="and now?", concierge=True, message_id="h2")
        assert r2.status_code == 200, r2.text

        assert fake.seen_hints == [[{"id": "ppt", "label": "Presentation"}], []]

    def test_non_concierge_branch_still_returns_json(self, env, monkeypatch):
        """A non-Concierge turn (plain steering on a running run) still returns its
        UNCHANGED JSON contract with content-type application/json (no streaming)."""
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="running")
        _seed_events(env, run_id, [(1, "agent_start", {}), (2, "agent_chunk", {})],
                     owner_id=owner.id)
        env["state"]["user"] = owner

        resp = _post(env, run_id, text="prefer teal", message_id="m-plain")
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("application/json")
        assert resp.json()["channel"] == "steering"


# ════════════════════════════════════════════════════════════════════════════
# ISS-092 — the Concierge's own model spend becomes a durable, readable number
# ════════════════════════════════════════════════════════════════════════════
_USAGE = {
    "input_tokens": 1200, "output_tokens": 340,
    "cache_read_tokens": 900, "cache_write_tokens": 100,
    "model_id": "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
}


class TestChatUsageAccounting:
    def test_chat_usage_row_records_observed_tokens_once_per_message_id(self, env, monkeypatch):
        """One durable ``chat_usage`` row per answered turn, idempotent on message_id.

        ``append_event_next_seq`` is keyed on ``event_id`` (``chat-usage:{message_id}``),
        so a retried/double-submitted POST resolves to the SAME row — a replay can never
        double-count the spend.
        """
        from app.api import run_commands as rc_module

        fake = _StreamingConcierge(usage=_USAGE)
        monkeypatch.setattr(rc_module, "_resolve_concierge", lambda: fake)

        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="completed")
        env["state"]["user"] = owner

        r1 = _post(env, run_id, text="what did it cost?", concierge=True, message_id="u1")
        assert r1.status_code == 200, r1.text

        rows = _events_of_type(env, run_id, "chat_usage")
        assert len(rows) == 1, "one answered turn must record exactly one chat_usage row"
        payload = rows[0].payload_json
        assert rows[0].event_id == "chat-usage:u1"
        assert payload["message_id"] == "u1"
        assert payload["input_tokens"] == 1200
        assert payload["output_tokens"] == 340
        assert payload["cache_read_tokens"] == 900
        assert payload["cache_write_tokens"] == 100
        assert payload["model_id"] == _USAGE["model_id"]
        # Priced from the OBSERVED counters — the number exists, so it can be reported.
        assert isinstance(payload["estimated_cost_usd"], (int, float))
        # Owner + workspace stamped by the ScopedStore (every durable row carries them).
        assert rows[0].owner_id == owner.id and rows[0].workspace_id == "ws-1"

        # A replayed POST with the SAME message_id must not add a second row.
        r2 = _post(env, run_id, text="what did it cost?", concierge=True, message_id="u1")
        assert r2.status_code == 200, r2.text
        assert len(_events_of_type(env, run_id, "chat_usage")) == 1, "replay double-counted"

    def test_chat_usage_never_mutates_workflow_run_token_usage(self, env, monkeypatch):
        """Chat spend is a SEPARATE line — it never touches the run's headline cost.

        ``workflow_runs.token_usage`` answers "what does this workflow cost to run", is
        written solely by ``_apply_terminal_completion`` (documented SOLE writer) and is
        pinned by the characterization goldens. Folding a user's chattiness into it would
        make two runs of the same workflow non-comparable and put a second writer on a
        deliberately consolidated seam.
        """
        from app.api import run_commands as rc_module
        from app.models.workflow import WorkflowRun

        fake = _StreamingConcierge(usage=_USAGE)
        monkeypatch.setattr(rc_module, "_resolve_concierge", lambda: fake)

        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="completed")
        env["state"]["user"] = owner

        db = env["Session"]()
        try:
            before = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first().token_usage
        finally:
            db.close()

        assert _post(env, run_id, text="hi", concierge=True, message_id="u2").status_code == 200
        # The row proves the turn WAS counted — so an unchanged headline is a decision,
        # not an accident of the spend never being observed.
        assert len(_events_of_type(env, run_id, "chat_usage")) == 1

        db = env["Session"]()
        try:
            after = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first().token_usage
        finally:
            db.close()
        assert after == before, "chat spend must NOT be folded into the run's headline cost"

    def test_no_chat_usage_row_when_spend_was_not_observed(self, env, monkeypatch):
        """A converse that reports no usage writes NO row — unmeasured is never invented.

        The absolute rule for ISS-092: a token that was not observed is reported as
        unmeasured. Deriving a count from ``len(chat_reply)`` would poison the downstream
        cache-savings figures (ISS-034), so the absence of a measurement stays an absence.
        """
        from app.api import run_commands as rc_module

        fake = _StreamingConcierge(usage=None)  # converse surfaces nothing
        monkeypatch.setattr(rc_module, "_resolve_concierge", lambda: fake)

        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="completed")
        env["state"]["user"] = owner

        assert _post(env, run_id, text="hi", concierge=True, message_id="u3").status_code == 200
        # The reply still landed — counting never gates the product.
        assert len(_events_of_type(env, run_id, "chat_reply")) == 1
        assert _events_of_type(env, run_id, "chat_usage") == []
