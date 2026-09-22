"""tests/integration/api/test_concierge_proposal_channels_api.py — CHAT / D-05
(33-03, Wave 3), endpoint half.

``POST /api/runs/{id}/messages`` with ``concierge=True`` driving the real
``CHANNEL_CONCIERGE`` branch end-to-end, with the Concierge resolve mocked so NO live
model call happens:

  * a fresh ask streams the reply and projects ONE durable ``chat_reply`` row;
  * a surfaced CONSEQUENTIAL proposal is HELD — a ``concierge_proposal`` row is written
    and the gate seam is NOT called until the user confirms (T-33-03-01);
  * the FE confirm round-trip (``confirm_proposal``) executes the held intent through
    its seam, marking the durable row resolved;
  * **H1 — the confirm-hold is SERVER-ENFORCED**: disposal reads ONLY the durable
    owner-scoped pending row. A confirm with no pending row is 404, a cross-owner
    confirm is 404 (IDOR), and the durable params beat a forged request body.

The app-layer DISPOSAL logic itself — ``run_commands._dispose_concierge_proposal``
routing each ``propose_*`` intent through its Phase-29 seam with the seams spied — is a
pure function of its arguments and lives in
``tests/unit/api/test_concierge_proposal_channels.py``.

Lives in the INTEGRATION suite because the H1 guarantees are claims about PERSISTED
state: that a pending row exists, is owner-scoped, is the source of the executed params,
and flips to ``resolved`` exactly once. "Dispose only from the durable row, never from
the client body" is unfalsifiable against a mocked Session — the forged-body and
cross-owner tests would pass without a durable row existing at all. Offline regardless
(in-memory engine, scripted concierge), so the unit-suite isolation guard
(``tests/unit/conftest.py``) correctly refuses a real DB connection there.

The intents are built from the REAL 33-02 ``propose_*`` tools (their frozen channel/param
contract), so a drift in that contract fails here.
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

from app.agents.chat.concierge import (
    propose_gate_action,
    propose_revision,
)
from app.api import run_commands as rc


# ════════════════════════════════════════════════════════════════════════════
# Endpoint — the real CHANNEL_CONCIERGE branch (Concierge resolve mocked).
# ════════════════════════════════════════════════════════════════════════════
class _FakeConcierge:
    """A scripted concierge: no live model. ``converse`` returns a fixed answer;
    ``drain_proposals`` surfaces any staged intents for the disposal loop."""

    def __init__(self, answer="the concierge answer", proposals=None):
        self._answer = answer
        self._proposals = list(proposals or [])
        self.seen: list = []

    async def converse(self, ctx, user_message, on_chunk=None):
        # BE-2: the fresh-Concierge branch now passes an ``on_chunk`` sink to stream the
        # reply. Emit the answer as a single delta (awaited iff awaitable) so the streamed
        # POST body carries a chat_reply_chunk; the terminal chat_reply stays canonical.
        self.seen.append((getattr(ctx, "run_id", None), user_message))
        if on_chunk is not None and self._answer:
            res = on_chunk(self._answer)
            if inspect.isawaitable(res):
                await res
        return self._answer

    def drain_proposals(self):
        out, self._proposals = self._proposals, []
        return out


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

    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(rc_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(db_module, "SessionLocal", TestingSession)

    import agents.artifact_store.store as store_mod

    store_mod._STORE = None
    store = store_mod.get_artifact_store()

    from app.api.run_commands import router
    from app.core.dependencies import get_current_principal, get_current_user

    from tests.fakes.principal import principal_for

    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    # post_message depends on get_current_principal: its revision/concierge
    # channels reach the tier gate, which reads cognito:groups (Decision 3).
    app.dependency_overrides[get_current_principal] = lambda: (
        state["user"],
        principal_for(state["user"]),
    )
    client = TestClient(app)

    yield {"store": store, "client": client, "state": state, "Session": TestingSession}

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()
    store_mod._STORE = None


class _FakeUser:
    def __init__(self, id, tier: str = "enterprise"):
        self.id = id
        self.tier = tier


def _seed_user(env, tag):
    from app.models.user import User

    db = env["Session"]()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"conc-{tag}-{uuid.uuid4().hex[:8]}@example.com",
            cognito_sub=str(uuid.uuid4()),
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(u.id)
    finally:
        db.close()


def _seed_run(env, user_id, *, status="running", workspace_id="ws-1"):
    from app.models.workflow import WorkflowRun

    run_id = str(uuid.uuid4())
    db = env["Session"]()
    try:
        db.add(
            WorkflowRun(
                id=run_id,
                user_id=user_id,
                owner_id=user_id,
                workspace_id=workspace_id,
                title="t",
                type="prototype",
                status=status,
                input="i",
                agent_count=1,
                session_id=user_id,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        return run_id
    finally:
        db.close()


def _seed_events(env, run_id, rows, *, owner_id, workspace_id="ws-1"):
    from app.models.run_event import RunEvent

    db = env["Session"]()
    try:
        for seq, etype, payload in rows:
            db.add(
                RunEvent(
                    id=str(uuid.uuid4()),
                    run_id=run_id,
                    owner_id=owner_id,
                    workspace_id=workspace_id,
                    seq=seq,
                    event_id=str(uuid.uuid4()),
                    type=etype,
                    payload_json=payload,
                )
            )
        db.commit()
    finally:
        db.close()


def _rows(env, run_id, etype):
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


def _post(env, run_id, **body):
    body.setdefault("message_id", uuid.uuid4().hex)
    return env["client"].post(f"/api/runs/{run_id}/messages", json=body)


def _sse_frames(resp) -> list[dict]:
    """Parse the ``{type, data}`` JSON envelopes from a streamed SSE response body."""
    frames: list[dict] = []
    for line in resp.text.splitlines():
        if line.startswith("data:"):
            payload = line[len("data:") :].strip()
            if payload:
                frames.append(json.loads(payload))
    return frames


def _arm_review(env, gate_key):
    env["store"]._resume_events[f"review:{gate_key}"] = asyncio.Event()


class TestConciergeEndpoint:
    def test_fresh_ask_projects_chat_reply(self, env, monkeypatch):
        fake = _FakeConcierge(answer="you are 2 agents in")
        monkeypatch.setattr(rc, "_resolve_concierge", lambda: fake)

        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="running")
        env["state"]["user"] = owner

        resp = _post(
            env, run_id, text="what's happening?", concierge=True, message_id="a1"
        )
        assert resp.status_code == 200, resp.text
        # BE-2: the fresh-Concierge branch STREAMS the POST body (text/event-stream). The
        # terminal chat_reply frame carries the full answer; the durable row is canonical.
        assert resp.headers["content-type"].startswith("text/event-stream")
        frames = _sse_frames(resp)
        terminal = next(f for f in frames if f["type"] == "chat_reply")
        assert terminal["data"]["text"] == "you are 2 agents in"
        # The Concierge saw the turn; its answer projected as ONE durable chat_reply row.
        assert fake.seen and fake.seen[0][1] == "what's happening?"
        replies = _rows(env, run_id, "chat_reply")
        assert len(replies) == 1
        assert replies[0].payload_json["text"] == "you are 2 agents in"

    def test_surfaced_consequential_proposal_is_held(self, env, monkeypatch):
        # A fresh ask whose Concierge surfaces a gate proposal → HELD (concierge_proposal
        # row emitted; the gate seam NOT called until the user confirms).
        gate_intent = propose_gate_action.func(action="approve")
        fake = _FakeConcierge(answer="I suggest approving", proposals=[gate_intent])
        monkeypatch.setattr(rc, "_resolve_concierge", lambda: fake)

        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="running")
        env["state"]["user"] = owner

        resp = _post(
            env, run_id, text="should I approve?", concierge=True, message_id="a2"
        )
        assert resp.status_code == 200, resp.text
        # BE-2: the held proposals ride the terminal chat_reply frame of the streamed body.
        terminal = next(f for f in _sse_frames(resp) if f["type"] == "chat_reply")
        held = terminal["data"]["proposals"]
        assert held and held[0]["held"] is True
        assert len(_rows(env, run_id, "concierge_proposal")) == 1
        # No gate resolution written (held behind the confirm chip).
        assert env["store"]._questionnaire_responses == {}

    def test_confirm_round_trip_executes_gate_seam(self, env, monkeypatch):
        # The FE confirm round-trip (33-04 / H1): the held intent is disposed from the
        # DURABLE pending row (written by the ask turn), through set_review_response.
        gate_intent = propose_gate_action.func(action="approve")
        fake = _FakeConcierge(answer="I suggest approving", proposals=[gate_intent])
        monkeypatch.setattr(rc, "_resolve_concierge", lambda: fake)

        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="waiting_for_user")
        gate_key = f"{run_id}:prototype-specify"
        _seed_events(
            env,
            run_id,
            [(1, "review_gate_ready", {"gate_key": gate_key})],
            owner_id=owner.id,
        )
        _arm_review(env, gate_key)
        env["state"]["user"] = owner

        # ── Ask turn: surface + HOLD the proposal (writes the durable pending row). ──
        ask = _post(
            env, run_id, text="should I approve?", concierge=True, message_id="mA"
        )
        assert ask.status_code == 200, ask.text
        assert len(_rows(env, run_id, "concierge_proposal")) >= 1
        seen_after_ask = list(fake.seen)

        # ── Confirm turn reuses the ask message_id (locates the pending row). ──
        resp = _post(
            env,
            run_id,
            concierge=True,
            message_id="mA",
            confirm_proposal={
                "channel": "gate_action",
                "params": {"action": "approve"},
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["proposal"]["disposed"] == "gate"
        recorded = env["store"]._questionnaire_responses.get(f"review:{gate_key}")
        assert recorded and recorded[0]["approved"] is True
        # No live model call happened on the confirm turn (converse untouched).
        assert fake.seen == seen_after_ask
        # The durable row is now marked resolved (a replayed confirm would 404).
        resolved = [
            r
            for r in _rows(env, run_id, "concierge_proposal")
            if r.payload_json.get("status") == "resolved"
        ]
        assert len(resolved) == 1

    def test_confirm_round_trip_executes_revision_seam(self, env, monkeypatch):
        rev_intent = propose_revision.func(
            instruction="make it pop", target="prototype_output"
        )
        fake = _FakeConcierge(answer="v2?", proposals=[rev_intent])
        monkeypatch.setattr(rc, "_resolve_concierge", lambda: fake)

        async def _noop_drive(**kwargs):
            return None

        monkeypatch.setattr(rc, "_drive_revision_to_queue", _noop_drive)

        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="completed")
        env["state"]["user"] = owner

        # ── Ask turn: surface + HOLD the revision proposal (durable pending row). ──
        ask = _post(env, run_id, text="revise please", concierge=True, message_id="mB")
        assert ask.status_code == 200, ask.text
        assert len(_rows(env, run_id, "concierge_proposal")) >= 1

        resp = _post(
            env,
            run_id,
            concierge=True,
            message_id="mB",
            confirm_proposal={
                "channel": "revision",
                "params": {"instruction": "make it pop", "target": "prototype_output"},
            },
        )
        assert resp.status_code == 200, resp.text
        child_id = resp.json()["proposal"]["revision_run_id"]

        from app.models.workflow import WorkflowRun

        db = env["Session"]()
        try:
            child = db.query(WorkflowRun).filter(WorkflowRun.id == child_id).first()
            assert child is not None
            assert child.parent_run_id == run_id
            assert child.type.endswith("_revision")
        finally:
            db.close()


# ════════════════════════════════════════════════════════════════════════════
# H1 — the confirm-hold is SERVER-ENFORCED: dispose ONLY from the durable
# owner-scoped pending row; the client body locates, never supplies, the intent.
# ════════════════════════════════════════════════════════════════════════════
class TestConfirmHoldServerEnforced:
    def test_confirm_without_pending_row_is_404(self, env, monkeypatch):
        # No durable pending row for this message_id/channel → 404 (nothing executes).
        fake = _FakeConcierge()
        monkeypatch.setattr(rc, "_resolve_concierge", lambda: fake)

        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="waiting_for_user")
        gate_key = f"{run_id}:prototype-specify"
        _seed_events(
            env,
            run_id,
            [(1, "review_gate_ready", {"gate_key": gate_key})],
            owner_id=owner.id,
        )
        _arm_review(env, gate_key)
        env["state"]["user"] = owner

        resp = _post(
            env,
            run_id,
            concierge=True,
            message_id="ghost",
            confirm_proposal={
                "channel": "gate_action",
                "params": {"action": "approve"},
            },
        )
        assert resp.status_code == 404, resp.text
        # The gate was NOT resolved (no forged confirm executed).
        assert env["store"]._questionnaire_responses.get(f"review:{gate_key}") is None

    def test_confirm_cross_owner_is_404(self, env, monkeypatch):
        # A forged/replayed confirm for a run the caller does NOT own → 404 (IDOR).
        gate_intent = propose_gate_action.func(action="approve")
        fake = _FakeConcierge(proposals=[gate_intent])
        monkeypatch.setattr(rc, "_resolve_concierge", lambda: fake)

        owner = _seed_user(env, "owner")
        attacker = _seed_user(env, "attacker")
        run_id = _seed_run(env, owner.id, status="waiting_for_user")
        gate_key = f"{run_id}:prototype-specify"
        _seed_events(
            env,
            run_id,
            [(1, "review_gate_ready", {"gate_key": gate_key})],
            owner_id=owner.id,
        )
        _arm_review(env, gate_key)

        # The owner surfaces + holds a real pending proposal.
        env["state"]["user"] = owner
        ask = _post(env, run_id, text="?", concierge=True, message_id="mV")
        assert ask.status_code == 200, ask.text

        # The attacker tries to confirm the victim's proposal → 404 (never sees the run).
        env["state"]["user"] = attacker
        resp = _post(
            env,
            run_id,
            concierge=True,
            message_id="mV",
            confirm_proposal={
                "channel": "gate_action",
                "params": {"action": "approve"},
            },
        )
        assert resp.status_code == 404, resp.text
        # The gate was NOT resolved by the attacker.
        assert env["store"]._questionnaire_responses.get(f"review:{gate_key}") is None

    def test_confirm_durable_params_win_over_forged_body(self, env, monkeypatch):
        # H1: the DURABLE row (request_changes) wins over a FORGED update_specs body.
        rc_intent = propose_gate_action.func(
            action="request_changes", rationale="tighten"
        )
        fake = _FakeConcierge(answer="hold on", proposals=[rc_intent])
        monkeypatch.setattr(rc, "_resolve_concierge", lambda: fake)

        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="waiting_for_user")
        gate_key = f"{run_id}:prototype-specify"
        _seed_events(
            env,
            run_id,
            [(1, "review_gate_ready", {"gate_key": gate_key})],
            owner_id=owner.id,
        )
        _arm_review(env, gate_key)
        env["state"]["user"] = owner

        # Ask surfaces + holds a request_changes proposal (durable params).
        ask = _post(
            env, run_id, text="what should I do?", concierge=True, message_id="mR"
        )
        assert ask.status_code == 200, ask.text

        # Confirm forges update_specs; the durable request_changes (→ redo) wins.
        resp = _post(
            env,
            run_id,
            concierge=True,
            message_id="mR",
            confirm_proposal={
                "channel": "gate_action",
                "params": {"action": "update_specs", "rationale": "FORGED"},
            },
        )
        assert resp.status_code == 200, resp.text
        assert (
            resp.json()["proposal"]["action"] == "redo"
        )  # durable request_changes wins
        recorded = env["store"]._questionnaire_responses.get(f"review:{gate_key}")
        assert recorded and recorded[0]["action"] == "redo"
        assert recorded[0]["approved"] is False
        # The forged instructions never reached the seam (durable rationale used).
        assert recorded[0]["instructions"] == "tighten"
