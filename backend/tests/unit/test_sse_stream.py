"""tests/unit/test_sse_stream.py — the per-run SSE down-channel (CHAT-07 / D-13, 29-02).

OFFLINE (in-memory SQLite / scripted queue / no live Bedrock / no live server). Covers
``GET /api/runs/{id}/events/stream`` (``app/api/run_stream.py``):

  * replay  — the durable ``run_events`` tail past the ``Last-Event-ID`` cursor is
              projected as ``id:``=``seq`` SSE frames (``{type, data}`` body).
  * attach  — the post-replay ``stream_attached {live, replayed_through_seq}`` handshake
              (the new-transport replacement for ``pipeline_reconnected``); ``live``
              reflects whether the per-run live queue is attached; live frames drain off
              that queue until the ``None`` sentinel.
  * owner   — a cross-owner or missing run → 404 (IDOR → 404, never 403); the flag-off
              route reports feature-absent (404).
  * rearm / gate — D-14g: a run paused at a still-open ``review_gate_ready`` re-emits it
              on attach (re-armed from the owner-scoped durable log), and does NOT
              re-arm once the gate is resolved (``review_gate_approved``).
  * handshake — ``replayed_through_seq`` mirrors the last replayed ``seq``.
  * wire-parity — the endpoint's frames, bound to the REAL 29-01 projection
              (``assert_wire_parity``), replay the recorded ``/ws/chat`` frame sequence
              identically (guards against accidental divergence).

The core generator ``_iter_sse_frames`` is dependency-injected, so the frame-content
assertions drive it directly against a scripted ``ScopedStore`` + a pre-populated
``asyncio.Queue`` (no live server); the 404 / flag behavior goes through a FastAPI
``TestClient`` (those responses return BEFORE the stream body).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agents.authz import ScopedStore
from app.api.run_stream import _STREAM_TERMINAL_TYPES, _iter_sse_frames, router
from app.core.dependencies import get_current_user
from app.models.database import Base, get_db
from app.models.run_event import RunEvent
from app.models.workflow import WorkflowRun


# ════════════════════════════════════════════════════════════════════════════
# Harness — in-memory SQLite (StaticPool) + dependency-overridden TestClient
# ════════════════════════════════════════════════════════════════════════════
class _FakeUser:
    def __init__(self, id: str):
        self.id = id


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
def api(db_session, monkeypatch):
    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": _FakeUser(id="owner")}

    def override_user():
        return state["user"]

    def override_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db

    # BUG-004: stream_run_events now backs the streaming generator with a SESSION-LESS
    # ScopedStore (it opens app.models.database.SessionLocal per read so the request
    # connection is not held/leaked during the stream). In production SessionLocal and
    # get_db share one engine; this harness overrides get_db onto an in-memory StaticPool
    # engine, so SessionLocal must be redirected onto that SAME engine or the generator
    # would read the real dev DB (empty) instead of the seeded rows.
    import app.models.database as _db_mod

    test_sessionmaker = sessionmaker(
        bind=db_session.get_bind(), autocommit=False, autoflush=False, expire_on_commit=False
    )
    monkeypatch.setattr(_db_mod, "SessionLocal", test_sessionmaker)
    return TestClient(app), state


def _seed_run(db, *, run_id="run-1", owner_id="owner", workspace_id="ws-1", status="running"):
    db.add(
        WorkflowRun(
            id=run_id,
            user_id=owner_id,
            title="My Run",
            type="prototype",
            status=status,
            input="idea",
            owner_id=owner_id,
            workspace_id=workspace_id,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


def _seed_events(db, rows, *, run_id="run-1", owner_id="owner", workspace_id="ws-1"):
    """Seed ``run_events`` from ``[(seq, type, payload), ...]``."""
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


def _store(db, *, owner_id="owner", workspace_id="ws-1"):
    return ScopedStore(owner_id=owner_id, workspace_id=workspace_id, session=db)


def _parse(frame: dict) -> dict:
    """Parse an ``_iter_sse_frames`` frame dict → ``{"id", "type", "data"}``."""
    body = json.loads(frame["data"])
    return {"id": frame["id"], "type": body["type"], "data": body.get("data", {})}


async def _collect(gen) -> list[dict]:
    return [f async for f in gen]


# ════════════════════════════════════════════════════════════════════════════
# replay — durable tail past the Last-Event-ID cursor, id:=seq
# ════════════════════════════════════════════════════════════════════════════
class TestReplay:
    def test_replay_from_cursor_projects_seq_frames(self, db_session):
        _seed_run(db_session)
        _seed_events(
            db_session,
            [
                (1, "agent_start", {"seq": 1, "agent": "a"}),
                (2, "agent_chunk", {"seq": 2, "text": "hi"}),
                (3, "agent_complete", {"seq": 3}),
            ],
        )
        # The replayed body now also carries the row's authoritative event_id COLUMN
        # (see TestReplayIdentityProjection); _seed_events mints a fresh uuid4 per row,
        # so the expected value is read back rather than hardcoded.
        row_event_id = db_session.query(RunEvent).filter_by(run_id="run-1", seq=2).one().event_id
        frames = asyncio.run(
            _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=1, live_queue=None
                )
            )
        )
        parsed = [_parse(f) for f in frames]
        # Only seq > 1 replayed, ascending, id:=seq, then the stream_attached handshake.
        replay = [p for p in parsed if p["type"] != "stream_attached"]
        assert [p["id"] for p in replay] == ["2", "3"]
        assert [p["type"] for p in replay] == ["agent_chunk", "agent_complete"]
        assert replay[0]["data"] == {"seq": 2, "text": "hi", "event_id": row_event_id}

    def test_replay_full_when_cursor_zero(self, db_session):
        _seed_run(db_session)
        _seed_events(
            db_session,
            [(1, "agent_start", {"seq": 1}), (2, "agent_complete", {"seq": 2})],
        )
        frames = asyncio.run(
            _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=0, live_queue=None
                )
            )
        )
        replay = [_parse(f) for f in frames if _parse(f)["type"] != "stream_attached"]
        assert [p["id"] for p in replay] == ["1", "2"]

    def test_last_event_id_header_resumes_from_cursor(self, api, db_session):
        """The browser-native Last-Event-ID header is the resume cursor — a stream with
        the header set replays ONLY seq > header (proven by streaming a finished run)."""
        client, _ = api
        _seed_run(db_session, status="completed")
        _seed_events(
            db_session,
            [
                (1, "agent_start", {"seq": 1}),
                (2, "agent_chunk", {"seq": 2}),
                (3, "pipeline_complete", {"seq": 3}),
            ],
        )
        # Finished run (no live queue) → the stream body terminates after the handshake.
        with client.stream(
            "GET", "/api/runs/run-1/events/stream", headers={"Last-Event-ID": "2"}
        ) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            text = "".join(resp.iter_text())
        ids = [ln.split("id:", 1)[1].strip() for ln in text.splitlines() if ln.startswith("id:")]
        # seq 3 replayed (>2); seq 1,2 skipped; handshake carries the last replayed seq.
        assert "3" in ids and "1" not in ids and "2" not in ids
        assert "stream_attached" in text


# ════════════════════════════════════════════════════════════════════════════
# replay identity — the row's event_id/seq COLUMNS must reach the wire
# ════════════════════════════════════════════════════════════════════════════
class TestReplayIdentityProjection:
    """A replayed row must be served WITH its durable identity columns.

    The engine stamps ``seq`` + ``event_id`` INTO the payload at its single emit
    boundary, so an engine-authored row carries its identity twice. But four
    app-layer types are persisted by the app itself and embed NO identity in
    ``payload_json`` — ``chat_reply`` / ``chat_message`` / ``chat_usage`` /
    ``run_resuming``. For those rows the COLUMNS are the only identity that exists.

    Concretely, ``app/agents/chat_narrator.py::persist_milestone_card`` persists a
    narrator milestone card whose payload is exactly ``{pipeline_run_id, message_id,
    card_kind, text, deep_link}`` and mints the durable ``event_id`` COLUMN as
    ``chat_reply:{source_event_id}``. The frontend keys the assistant bubble on
    ``data.event_id`` (``useRunChat.ts::upsertNarratorMessage``) and otherwise falls
    back to ``chat-reply:{message_id}`` — a key the narrator's durable id can never
    equal. So a replay that drops the columns renders the card a SECOND time once the
    REST twin (``GET /api/runs/{id}/events``, which does merge the columns) backfills
    it. This pins the projection at the source.
    """

    def test_replayed_identity_less_chat_reply_carries_its_row_identity(self, db_session):
        _seed_run(db_session)
        _seed_events(
            db_session,
            [
                (1, "agent_start", {"seq": 1, "agent": "a"}),
                (
                    2,
                    "chat_reply",
                    {
                        "pipeline_run_id": "run-1",
                        "message_id": "m1",
                        "card_kind": "deliverable",
                        "text": "Delivered",
                    },
                ),
            ],
        )
        # _seed_events mints a fresh uuid4 per row, so the expected value must be read
        # back from the DB — a hardcoded literal would be wrong on every run.
        row_event_id = db_session.query(RunEvent).filter_by(run_id="run-1", seq=2).one().event_id

        frames = asyncio.run(
            _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=1, live_queue=None
                )
            )
        )
        replay = [p for p in (_parse(f) for f in frames) if p["type"] != "stream_attached"]
        assert [p["type"] for p in replay] == ["chat_reply"]

        data = replay[0]["data"]
        # The identity the payload never carried, taken from the row's COLUMNS.
        assert data.get("event_id") == row_event_id
        assert data.get("seq") == 2
        # ...and the persisted payload keys survive the merge unchanged.
        assert data["pipeline_run_id"] == "run-1"
        assert data["message_id"] == "m1"
        assert data["card_kind"] == "deliverable"
        assert data["text"] == "Delivered"


# ════════════════════════════════════════════════════════════════════════════
# attach — stream_attached handshake + live-queue drain
# ════════════════════════════════════════════════════════════════════════════
class TestAttach:
    def test_stream_attached_after_replay_marks_live_false_when_finished(self, db_session):
        _seed_run(db_session)
        _seed_events(db_session, [(1, "agent_start", {"seq": 1})])
        frames = asyncio.run(
            _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=0, live_queue=None
                )
            )
        )
        parsed = [_parse(f) for f in frames]
        # First frame AFTER the replay is stream_attached.
        handshake = next(p for p in parsed if p["type"] == "stream_attached")
        assert handshake["data"]["live"] is False
        assert handshake["data"]["replayed_through_seq"] == 1

    def test_attach_live_queue_drains_until_sentinel(self, db_session):
        _seed_run(db_session)
        _seed_events(db_session, [(1, "agent_start", {"seq": 1})])
        q: asyncio.Queue = asyncio.Queue()

        async def _drive():
            await q.put({"type": "agent_chunk", "data": {"seq": 2, "text": "live"}})
            await q.put({"type": "pipeline_complete", "data": {"seq": 3}})
            await q.put(None)  # sentinel
            return await _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=0, live_queue=q
                )
            )

        parsed = [_parse(f) for f in asyncio.run(_drive())]
        handshake = next(p for p in parsed if p["type"] == "stream_attached")
        assert handshake["data"]["live"] is True
        live_types = [p["type"] for p in parsed if p["id"] in ("2", "3")]
        assert live_types == ["agent_chunk", "pipeline_complete"]
        assert parsed[-1]["type"] == "pipeline_complete"  # terminal ends the drain


# ════════════════════════════════════════════════════════════════════════════
# live-drain terminals — BUG-016: approving a review gate must NOT close the
# stream (approve RESUMES the run on the same queue); only genuine terminals do.
# ════════════════════════════════════════════════════════════════════════════
class TestLiveDrainTerminals:
    def test_review_gate_approved_does_not_close_stream(self, db_session):
        """approve is a gate RESUMPTION, not a stream terminal — the drain keeps
        forwarding the post-approve events on the same queue (BUG-016)."""
        _seed_run(db_session)
        _seed_events(db_session, [(1, "agent_start", {"seq": 1})])
        q: asyncio.Queue = asyncio.Queue()

        async def _drive():
            await q.put({"type": "review_gate_approved", "data": {"seq": 2}})
            await q.put({"type": "agent_start", "data": {"seq": 3, "agent": "prototype-plan"}})
            await q.put(None)  # sentinel
            return await _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=0, live_queue=q
                )
            )

        parsed = [_parse(f) for f in asyncio.run(_drive())]
        # FAIL-BEFORE: review_gate_approved is in _GATE_RESOLUTION_TYPES, so the drain
        # returns right after yielding it → the post-approve agent_start (id "3") is
        # never yielded (RED). GREEN once :198 uses _STREAM_TERMINAL_TYPES.
        assert any(p["id"] == "2" and p["type"] == "review_gate_approved" for p in parsed)
        assert any(p["id"] == "3" and p["type"] == "agent_start" for p in parsed), (
            "post-approve agent_start dropped — approve wrongly closed the live stream"
        )

    def test_pipeline_complete_ends_the_drain(self, db_session):
        """CONTROL: a genuine terminal still ends the drain before any later event."""
        _seed_run(db_session)
        _seed_events(db_session, [(1, "agent_start", {"seq": 1})])
        q: asyncio.Queue = asyncio.Queue()

        async def _drive():
            await q.put({"type": "pipeline_complete", "data": {"seq": 2}})
            await q.put({"type": "agent_start", "data": {"seq": 3}})
            await q.put(None)  # sentinel
            return await _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=0, live_queue=q
                )
            )

        parsed = [_parse(f) for f in asyncio.run(_drive())]
        assert any(p["id"] == "2" and p["type"] == "pipeline_complete" for p in parsed)
        assert not any(p["id"] == "3" for p in parsed), (
            "pipeline_complete must end the drain before the post-terminal event"
        )


# ════════════════════════════════════════════════════════════════════════════
# owner — IDOR → 404 (never 403) + flag-off feature-absent
# ════════════════════════════════════════════════════════════════════════════
class TestOwnerScope:
    def test_cross_owner_is_404(self, api, db_session):
        client, state = api
        _seed_run(db_session, owner_id="owner")
        _seed_events(db_session, [(1, "agent_start", {"seq": 1})])
        state["user"] = _FakeUser(id="attacker")
        resp = client.get("/api/runs/run-1/events/stream")
        assert resp.status_code == 404, "IDOR: attacker streamed another owner's run"

    def test_missing_run_is_404(self, api):
        client, _ = api
        resp = client.get("/api/runs/nope/events/stream")
        assert resp.status_code == 404

    def test_never_403(self, api, db_session):
        client, state = api
        _seed_run(db_session, owner_id="owner")
        state["user"] = _FakeUser(id="attacker")
        resp = client.get("/api/runs/run-1/events/stream")
        assert resp.status_code != 403, "must never leak existence via 403"


# ════════════════════════════════════════════════════════════════════════════
# handshake — replayed_through_seq mirrors the last replayed seq
# ════════════════════════════════════════════════════════════════════════════
class TestHandshake:
    def test_replayed_through_seq_mirrors_last_seq(self, db_session):
        _seed_run(db_session)
        _seed_events(
            db_session,
            [(1, "a", {"seq": 1}), (2, "b", {"seq": 2}), (3, "c", {"seq": 3})],
        )
        frames = asyncio.run(
            _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=0, live_queue=None
                )
            )
        )
        handshake = next(_parse(f) for f in frames if _parse(f)["type"] == "stream_attached")
        assert handshake["data"]["replayed_through_seq"] == 3
        assert handshake["id"] == "3"  # cursor line does not advance past the tail

    def test_handshake_cursor_from_empty_replay_is_the_client_cursor(self, db_session):
        _seed_run(db_session)
        _seed_events(db_session, [(1, "a", {"seq": 1}), (2, "b", {"seq": 2})])
        # Client already past the tail → no replay, handshake mirrors the cursor.
        frames = asyncio.run(
            _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=2, live_queue=None
                )
            )
        )
        handshake = next(_parse(f) for f in frames if _parse(f)["type"] == "stream_attached")
        assert handshake["data"]["replayed_through_seq"] == 2


# ════════════════════════════════════════════════════════════════════════════
# rearm / gate — D-14g: re-emit review_gate_ready on attach while paused
# ════════════════════════════════════════════════════════════════════════════
class TestGateRearm:
    def test_paused_gate_reemits_review_gate_ready_on_attach(self, db_session):
        _seed_run(db_session, status="waiting_for_user")
        _seed_events(
            db_session,
            [
                (1, "agent_start", {"seq": 1}),
                (2, "agent_complete", {"seq": 2}),
                (3, "review_gate_ready", {"seq": 3, "agent_id": "prototype-specify", "gate_key": "gk"}),
            ],
        )
        # Client cursor already PAST the gate frame — without re-arm it would never
        # re-open. D-14g re-emits it from the owner-scoped durable log.
        frames = asyncio.run(
            _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=3, live_queue=None
                )
            )
        )
        parsed = [_parse(f) for f in frames]
        rearmed = [p for p in parsed if p["type"] == "review_gate_ready"]
        assert len(rearmed) == 1, "paused gate must be re-armed on attach (D-14g)"
        assert rearmed[0]["data"]["gate_key"] == "gk"

    def test_resolved_gate_does_not_rearm(self, db_session):
        _seed_run(db_session, status="running")
        _seed_events(
            db_session,
            [
                (1, "review_gate_ready", {"seq": 1, "gate_key": "gk"}),
                (2, "review_gate_approved", {"seq": 2}),
                (3, "agent_start", {"seq": 3}),
            ],
        )
        frames = asyncio.run(
            _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=3, live_queue=None
                )
            )
        )
        parsed = [_parse(f) for f in frames]
        # The gate is resolved (approved) → no re-arm frame beyond the handshake.
        rearmed = [p for p in parsed if p["type"] == "review_gate_ready"]
        assert rearmed == [], "a resolved gate must NOT re-arm"

    def test_terminal_run_does_not_rearm_even_with_a_dangling_gate(self, db_session):
        """FIX-240 (ISS-121): a run whose PERSISTED status is terminal must never re-arm
        a gate, however open the durable log looks.

        This is the shape of every run cancelled BEFORE FIX-240: the engine's terminal
        event lost a seq collision with the chat lane and was discarded, so the log still
        ends on an unresolved ``review_gate_ready``. Those rows are not retroactively
        recoverable and no synthetic event is back-filled — the persisted status is
        consulted at the app boundary instead.
        """
        _seed_run(db_session, status="cancelled")
        _seed_events(
            db_session,
            [
                (1, "agent_complete", {"seq": 1}),
                (2, "review_gate_ready", {"seq": 2, "gate_key": "gk"}),
                (3, "chat_message", {"seq": 3, "text": "Not what I wanted — stop."}),
                # seq 4 — pipeline_cancelled — is the row the collision destroyed.
            ],
        )
        frames = asyncio.run(
            _collect(
                _iter_sse_frames(
                    run_id="run-1",
                    store=_store(db_session),
                    after_seq=3,
                    live_queue=None,
                    run_is_terminal=True,
                )
            )
        )
        rearmed = [p for p in (_parse(f) for f in frames) if p["type"] == "review_gate_ready"]
        assert rearmed == [], "a terminal run must NOT re-arm a dangling gate"

    def test_rearm_is_read_only(self, db_session):
        """Re-arm reads gate state; it must not write/append any row (no mutation)."""
        _seed_run(db_session, status="waiting_for_user")
        _seed_events(
            db_session,
            [(1, "review_gate_ready", {"seq": 1, "gate_key": "gk"})],
        )
        before = db_session.query(RunEvent).count()
        asyncio.run(
            _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=0, live_queue=None
                )
            )
        )
        after = db_session.query(RunEvent).count()
        assert after == before, "gate re-arm must be read-only (no artifact/graph mutation)"

    def test_fresh_attach_does_not_double_emit_open_gate(self, db_session):
        """CR-01: a fresh attach (after_seq=0) to a run paused at an open gate must yield
        EXACTLY ONE review_gate_ready.

        after_seq=0 is every first-ever page load (no Last-Event-ID) — the single most
        common trigger for opening this endpoint. Step-1 durable replay (seq > 0) already
        yields the open gate row, so the D-14g re-arm must NOT emit a second, identical
        frame. Fails pre-fix (the unconditional re-arm double-emits → 2 frames); passes
        once the re-arm is guarded by ``dangling.seq <= after_seq``.
        """
        _seed_run(db_session, status="waiting_for_user")
        _seed_events(
            db_session,
            [
                (1, "agent_start", {"seq": 1}),
                (2, "agent_complete", {"seq": 2}),
                (3, "review_gate_ready", {"seq": 3, "gate_key": "gk"}),
            ],
        )
        frames = asyncio.run(
            _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=0, live_queue=None
                )
            )
        )
        parsed = [_parse(f) for f in frames]
        rearmed = [p for p in parsed if p["type"] == "review_gate_ready"]
        assert len(rearmed) == 1, (
            "fresh attach must yield exactly one review_gate_ready (durable replay only) "
            "— the re-arm must not double-emit a gate the replay already delivered"
        )
        assert rearmed[0]["data"]["gate_key"] == "gk"
        # The single frame carries the gate's own durable seq (id:) so a resume from it
        # re-reads nothing new (no phantom cursor advance).
        assert rearmed[0]["id"] == "3"


# ════════════════════════════════════════════════════════════════════════════
# M-18 — ScopedStore.last_event_of_types has no direct unit test. The D-14g gate
# re-arm (TestGateRearm above) exercises it only indirectly through
# ``_dangling_review_gate``. These tests bind the method itself: highest-seq
# match, the ``after_seq`` boundary, owner/workspace scoping, and the
# empty/no-match case — the exact contract its own docstring states as
# equivalent to ``max-by-seq of [r for r in read_events(...) if r.type in T]``.
# ════════════════════════════════════════════════════════════════════════════
class TestLastEventOfTypes:
    def test_returns_highest_seq_match_among_multiple(self, db_session):
        _seed_events(
            db_session,
            [
                (1, "review_gate_ready", {"seq": 1}),
                (2, "agent_start", {"seq": 2}),
                (3, "review_gate_ready", {"seq": 3}),
            ],
        )
        row = asyncio.run(
            _store(db_session).last_event_of_types(
                "run-1", {"review_gate_ready"}, after_seq=0
            )
        )
        assert row is not None
        assert row.seq == 3, "must return the HIGHEST-seq match, not the first"

    def test_matches_any_type_in_the_set(self, db_session):
        _seed_events(
            db_session,
            [
                (1, "review_gate_ready", {"seq": 1}),
                (2, "review_gate_approved", {"seq": 2}),
            ],
        )
        row = asyncio.run(
            _store(db_session).last_event_of_types(
                "run-1", {"review_gate_ready", "review_gate_approved"}, after_seq=0
            )
        )
        assert row is not None and row.seq == 2 and row.type == "review_gate_approved"

    def test_after_seq_excludes_rows_at_or_below_the_cursor(self, db_session):
        _seed_events(
            db_session,
            [
                (1, "review_gate_ready", {"seq": 1}),
                (2, "review_gate_ready", {"seq": 2}),
            ],
        )
        row = asyncio.run(
            _store(db_session).last_event_of_types(
                "run-1", {"review_gate_ready"}, after_seq=2
            )
        )
        assert row is None, "seq <= after_seq rows must be excluded (equivalence contract)"

    def test_returns_none_when_no_type_matches(self, db_session):
        _seed_events(db_session, [(1, "agent_start", {"seq": 1})])
        row = asyncio.run(
            _store(db_session).last_event_of_types(
                "run-1", {"review_gate_ready"}, after_seq=0
            )
        )
        assert row is None

    def test_returns_none_on_empty_log(self, db_session):
        row = asyncio.run(
            _store(db_session).last_event_of_types(
                "run-1", {"review_gate_ready"}, after_seq=0
            )
        )
        assert row is None

    def test_scoped_to_owner_and_workspace(self, db_session):
        """A row owned by a different principal must never be returned — the same
        default-deny boundary read_events enforces (§19)."""
        _seed_events(
            db_session,
            [(1, "review_gate_ready", {"seq": 1})],
            owner_id="owner",
            workspace_id="ws-1",
        )
        _seed_events(
            db_session,
            [(2, "review_gate_ready", {"seq": 2})],
            run_id="run-1",
            owner_id="other-owner",
            workspace_id="ws-2",
        )
        row = asyncio.run(
            _store(db_session, owner_id="owner", workspace_id="ws-1").last_event_of_types(
                "run-1", {"review_gate_ready"}, after_seq=0
            )
        )
        assert row is not None and row.seq == 1, (
            "must return only the caller's own scoped row, never the other owner's "
            "higher-seq row"
        )


# ════════════════════════════════════════════════════════════════════════════
# wire-parity — the endpoint's frames == the recorded /ws/chat frame sequence
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_endpoint_frames_satisfy_wire_parity(db_session):
    """The SSE endpoint's projected frames replay the recorded WS frame sequence
    identically — bound to the REAL 29-01 projection ``assert_wire_parity``.

    The endpoint re-implements the projection contract, so parity holds by
    construction; this test guards against an accidental divergence in the endpoint's
    rendering. Drives ``prototype_revision`` (the smallest golden pipeline) OFFLINE.
    """
    from tests.agents._scripted_model import _drive
    from tests.agents.characterization._sse_projection import (
        assert_wire_parity,
        run_events_from_engine_events,
        ws_frame_from_engine_event,
    )

    pipeline = "prototype_revision"
    events = await _drive(pipeline)
    assert events, f"{pipeline} produced no events"

    # The recorded WS frame sequence (the parity target) + the durable run_events rows.
    ws_frames = [ws_frame_from_engine_event(ev, section=pipeline) for ev in events]
    ref_rows = run_events_from_engine_events(events)  # {seq, type, payload}

    # Seed those durable rows so the endpoint replays them, then consume the endpoint.
    _seed_run(db_session, run_id="wp-run", status="completed")
    _seed_events(
        db_session,
        [(r["seq"], r["type"], r["payload"]) for r in ref_rows],
        run_id="wp-run",
    )
    frames = [
        f
        async for f in _iter_sse_frames(
            run_id="wp-run", store=_store(db_session), after_seq=0, live_queue=None
        )
    ]

    # Reconstruct run_events rows FROM the endpoint's emitted frames, dropping the
    # synthetic chat-lane handshake (stream_attached never appears in a WS golden).
    endpoint_rows = []
    for f in frames:
        p = _parse(f)
        if p["type"] == "stream_attached":
            continue
        endpoint_rows.append({"seq": int(p["id"]), "type": p["type"], "payload": p["data"]})

    # The binding gate: the endpoint-derived rows, reference-projected, == the recorded
    # WS frames. A dropped/added/mutated frame trips assert_wire_parity.
    assert endpoint_rows, "endpoint produced no replay frames (vacuous)"
    assert_wire_parity(ws_frames, endpoint_rows)


# ════════════════════════════════════════════════════════════════════════════
# A3 — _cleanup_pipeline must RELEASE an attached client, not just deregister
# the run. Nine of its twelve invocation paths (every resume / gate-re-arm path
# reaching it through engine._fire_resume_cleanup) pop the registry entry with
# NO prior None sentinel, so a client parked at `await live_queue.get()`
# (run_stream.py:197) hangs until its socket drops. The dict pop cannot reach it:
# the endpoint bound the queue OBJECT at run_stream.py:281 before the generator ran.
# ════════════════════════════════════════════════════════════════════════════
_CLEANUP_TIMEOUT_S = 2.0


@pytest.fixture
def registries():
    """Isolate the process-global per-run registries around each test."""
    from app.api import run_engine as run_engine_mod

    def _reset():
        run_engine_mod._PIPELINE_QUEUES.clear()
        run_engine_mod._PIPELINE_TASKS.clear()
        run_engine_mod._CANCEL_EVENTS.clear()
        run_engine_mod._SUBSCRIBERS.clear()
        for t, _gen in run_engine_mod._PUMP_TASKS.values():
            t.cancel()
        run_engine_mod._PUMP_TASKS.clear()
        run_engine_mod._QUEUE_GENERATIONS.clear()

    _reset()
    yield run_engine_mod
    _reset()


class TestCleanupSentinel:
    """A3 — ``_cleanup_pipeline`` releases an attached SSE client."""

    @pytest.mark.asyncio
    async def test_cleanup_without_prior_sentinel_releases_attached_client(
        self, db_session, registries
    ):
        """The resume early-return shape: pop with no sentinel. The client parked in
        the live drain must terminate, not hang."""
        _seed_run(db_session)
        _seed_events(db_session, [(1, "agent_start", {"seq": 1})])
        q = registries._get_or_create_queue("run-1")
        assert "run-1" in registries._PIPELINE_QUEUES

        client = asyncio.create_task(
            _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=0, live_queue=q
                )
            )
        )
        await asyncio.sleep(0.05)  # client reaches `await live_queue.get()`
        assert not client.done(), "precondition: the client must be parked in the drain"

        registries._cleanup_pipeline("run-1")

        frames = await asyncio.wait_for(client, timeout=_CLEANUP_TIMEOUT_S)
        assert [_parse(f)["type"] for f in frames] == ["agent_start", "stream_attached"]
        assert "run-1" not in registries._PIPELINE_QUEUES

    @pytest.mark.asyncio
    async def test_cleanup_releases_a_client_still_in_replay(self, db_session, registries):
        """The sentinel must not be lost when it lands while the client is still in the
        durable replay (step 1) rather than the live drain (step 4): the generator holds
        the queue OBJECT, so the pop does not detach it and the sentinel is consumed when
        the drain is finally reached."""

        class _SlowStore:
            def __init__(self, inner):
                self._inner = inner

            async def read_events(self, run_id, after_seq=0):
                await asyncio.sleep(0.10)
                return await self._inner.read_events(run_id, after_seq=after_seq)

        _seed_run(db_session)
        _seed_events(db_session, [(1, "agent_start", {"seq": 1})])
        q = registries._get_or_create_queue("run-1")

        client = asyncio.create_task(
            _collect(
                _iter_sse_frames(
                    run_id="run-1",
                    store=_SlowStore(_store(db_session)),
                    after_seq=0,
                    live_queue=q,
                )
            )
        )
        await asyncio.sleep(0)  # the client is inside the slow replay
        registries._cleanup_pipeline("run-1")

        frames = await asyncio.wait_for(client, timeout=_CLEANUP_TIMEOUT_S)
        assert [_parse(f)["type"] for f in frames] == ["agent_start", "stream_attached"]

    @pytest.mark.asyncio
    async def test_driver_sentinel_then_cleanup_does_not_truncate(
        self, db_session, registries
    ):
        """The launch/revision driver shape (`put(None)` then cleanup): the second
        sentinel queues BEHIND the tail, so nothing is truncated and the reader returns
        on the first one."""
        _seed_run(db_session)
        _seed_events(db_session, [(1, "agent_start", {"seq": 1})])
        q = registries._get_or_create_queue("run-1")

        client = asyncio.create_task(
            _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=0, live_queue=q
                )
            )
        )
        await asyncio.sleep(0.05)
        await q.put({"type": "agent_chunk", "data": {"seq": 2, "text": "tail"}})
        await q.put(None)  # the driver's own sentinel
        registries._cleanup_pipeline("run-1")  # adds a SECOND sentinel behind it

        frames = await asyncio.wait_for(client, timeout=_CLEANUP_TIMEOUT_S)
        assert [_parse(f)["type"] for f in frames] == [
            "agent_start",
            "stream_attached",
            "agent_chunk",
        ]

    def test_cleanup_is_idempotent_and_never_resurrects_the_queue(self, registries):
        """WR-01 (Phase 12): every exit path calls this, including paths that registered
        nothing. A second call must be a pure no-op -- it must not re-create the queue in
        order to sentinel it."""
        registries._get_or_create_queue("run-x")
        registries._cleanup_pipeline("run-x")
        registries._cleanup_pipeline("run-x")
        assert "run-x" not in registries._PIPELINE_QUEUES
        assert "run-x" not in registries._PIPELINE_TASKS
        assert "run-x" not in registries._CANCEL_EVENTS


# ════════════════════════════════════════════════════════════════════════════
# C-06 — the fan-out bus must actually have a producer. Before this fix, every
# real event producer wrote ONLY to `_PIPELINE_QUEUES`, `_dispatch_event_to_
# subscribers` (the only writer to `_SUBSCRIBERS`) had zero callers anywhere in
# the repo, and the SSE endpoint read ONLY from `_SUBSCRIBERS` — so a live
# attach replayed the durable tail, sent `stream_attached`, then hung forever.
# These tests drive the producer/consumer pair end-to-end through the real
# registries (no mocking of the bridge) to prove events actually cross from
# one side to the other.
# ════════════════════════════════════════════════════════════════════════════
class TestFanOutPump:
    """The pump (`_ensure_pump` / `_pump_run_events`) bridges `_PIPELINE_QUEUES`
    (producer side) into `_SUBSCRIBERS` (consumer side)."""

    @pytest.mark.asyncio
    async def test_producer_event_reaches_subscriber(self, registries):
        """An event put on the PRODUCER queue must be observable on the
        SUBSCRIBER queue — this is the exact wiring that was missing."""
        producer_q = registries._get_or_create_queue("run-1")
        registries._PIPELINE_TASKS["run-1"] = asyncio.current_task()  # any live sentinel

        sub_q = await registries._subscribe("run-1")
        try:
            producer_q.put_nowait({"type": "agent_start", "data": {"seq": 1}})
            event = await asyncio.wait_for(sub_q.get(), timeout=2.0)
            assert event == {"type": "agent_start", "data": {"seq": 1}}
        finally:
            await registries._unsubscribe("run-1", sub_q)
            registries._cleanup_pipeline("run-1")

    @pytest.mark.asyncio
    async def test_multiple_subscribers_all_receive_every_event(self, registries):
        """KAN-134's whole point: every subscriber sees every event (no
        round-robin partitioning across concurrent SSE clients)."""
        producer_q = registries._get_or_create_queue("run-1")
        registries._PIPELINE_TASKS["run-1"] = asyncio.current_task()

        sub_a = await registries._subscribe("run-1")
        sub_b = await registries._subscribe("run-1")
        try:
            producer_q.put_nowait({"type": "agent_chunk", "data": {"seq": 1}})
            ev_a = await asyncio.wait_for(sub_a.get(), timeout=2.0)
            ev_b = await asyncio.wait_for(sub_b.get(), timeout=2.0)
            assert ev_a == ev_b == {"type": "agent_chunk", "data": {"seq": 1}}
        finally:
            await registries._unsubscribe("run-1", sub_a)
            await registries._unsubscribe("run-1", sub_b)
            registries._cleanup_pipeline("run-1")

    @pytest.mark.asyncio
    async def test_producer_sentinel_closes_the_subscriber_queue(self, registries):
        """The driver's terminal ``put(None)`` must reach the subscriber so its
        SSE drain loop returns instead of hanging forever."""
        producer_q = registries._get_or_create_queue("run-1")
        registries._PIPELINE_TASKS["run-1"] = asyncio.current_task()

        sub_q = await registries._subscribe("run-1")
        producer_q.put_nowait(None)  # driver's own terminal sentinel
        event = await asyncio.wait_for(sub_q.get(), timeout=2.0)
        assert event is None

    @pytest.mark.asyncio
    async def test_cleanup_pipeline_sentinel_reaches_subscriber_via_pump(self, registries):
        """The resume/gate-re-arm teardown shape: `_cleanup_pipeline` sentinels the
        PRODUCER queue with no prior sentinel. The pump must forward that sentinel
        to the subscriber (this is the H-10-adjacent leak this bus must not have)."""
        registries._get_or_create_queue("run-1")
        registries._PIPELINE_TASKS["run-1"] = asyncio.current_task()

        sub_q = await registries._subscribe("run-1")
        registries._cleanup_pipeline("run-1")
        event = await asyncio.wait_for(sub_q.get(), timeout=2.0)
        assert event is None

    @pytest.mark.asyncio
    async def test_subscribe_to_a_run_with_no_producer_closes_immediately(self, registries):
        """A subscriber that attaches after the producer queue is already gone
        (the race between `_is_run_live` and `_subscribe`) must get a queue that
        resolves to the sentinel immediately, not one that hangs forever."""
        sub_q = await registries._subscribe("run-ghost")
        event = await asyncio.wait_for(sub_q.get(), timeout=2.0)
        assert event is None

    @pytest.mark.asyncio
    async def test_concurrent_subscribes_start_exactly_one_pump(self, registries):
        """Two SSE clients attaching to the same run concurrently must not spawn
        two pumps racing to drain the same producer queue (which would silently
        split events between them)."""
        registries._get_or_create_queue("run-1")
        registries._PIPELINE_TASKS["run-1"] = asyncio.current_task()

        await asyncio.gather(
            registries._subscribe("run-1"),
            registries._subscribe("run-1"),
        )
        assert len(registries._PUMP_TASKS) == 1
        registries._cleanup_pipeline("run-1")


# ════════════════════════════════════════════════════════════════════════════
# C-06a — the first subscriber must not receive an already-persisted event
# TWICE (once via durable replay, once via the live queue). The producer
# persists an event BEFORE it reaches the source queue, and the SSE endpoint
# subscribes to the live queue BEFORE the generator replays the durable tail —
# so an event committed in that window is both replayed AND live-forwarded.
# ════════════════════════════════════════════════════════════════════════════
class TestReplayLiveDedup:
    @pytest.mark.asyncio
    async def test_durable_row_plus_identical_queued_event_is_not_duplicated(
        self, db_session, registries
    ):
        """The exact repro from the bug report: one durable row + the SAME event
        (same event_id) sitting in the live queue must be yielded exactly once."""
        _seed_run(db_session)
        _seed_events(
            db_session,
            [(1, "agent_chunk", {"seq": 1, "event_id": "evt-1", "text": "hi"})],
            run_id="run-1",
        )
        # Patch the row's event_id to the known value the test asserts against
        # (``_seed_events`` mints a random uuid per row).
        row = db_session.query(RunEvent).filter(RunEvent.run_id == "run-1").one()
        row.event_id = "evt-1"
        db_session.commit()

        q: asyncio.Queue = asyncio.Queue()

        async def _drive():
            # The SAME event (same event_id) also sitting on the live queue — the
            # persist-before-queue race the fix targets.
            await q.put(
                {"type": "agent_chunk", "data": {"seq": 1, "event_id": "evt-1", "text": "hi"}}
            )
            await q.put(None)
            return await _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=0, live_queue=q
                )
            )

        parsed = [_parse(f) for f in await _drive()]
        chunk_frames = [p for p in parsed if p["type"] == "agent_chunk"]
        assert len(chunk_frames) == 1, (
            f"expected exactly one agent_chunk frame, got {len(chunk_frames)}: {chunk_frames}"
        )

    @pytest.mark.asyncio
    async def test_events_persisted_during_the_replay_window_are_not_duplicated(
        self, db_session, registries
    ):
        """A slow replay (store.read_events) racing a fast live producer: an event
        that lands on the live queue DURING replay, and is ALSO in the replayed
        rows, must still only be yielded once."""

        class _SlowStore:
            def __init__(self, inner):
                self._inner = inner

            async def read_events(self, run_id, after_seq=0):
                await asyncio.sleep(0.05)
                return await self._inner.read_events(run_id, after_seq=after_seq)

            async def last_event_of_types(self, *a, **k):
                return await self._inner.last_event_of_types(*a, **k)

        _seed_run(db_session)
        _seed_events(
            db_session,
            [(1, "agent_start", {"seq": 1, "event_id": "evt-a"})],
            run_id="run-1",
        )
        row = db_session.query(RunEvent).filter(RunEvent.run_id == "run-1").one()
        row.event_id = "evt-a"
        db_session.commit()

        q: asyncio.Queue = asyncio.Queue()
        await q.put({"type": "agent_start", "data": {"seq": 1, "event_id": "evt-a"}})
        await q.put(None)

        frames = await _collect(
            _iter_sse_frames(
                run_id="run-1",
                store=_SlowStore(_store(db_session)),
                after_seq=0,
                live_queue=q,
            )
        )
        parsed = [_parse(f) for f in frames]
        starts = [p for p in parsed if p["type"] == "agent_start"]
        assert len(starts) == 1

    @pytest.mark.asyncio
    async def test_two_real_subscribers_observe_identical_deduped_order(
        self, db_session, registries
    ):
        """Two subscribers attaching to the SAME run through the real fan-out bus
        must each see the SAME de-duplicated event order — no double-delivery for
        either one."""
        _seed_run(db_session)
        _seed_events(
            db_session,
            [(1, "agent_start", {"seq": 1, "event_id": "evt-1"})],
            run_id="run-1",
        )
        row = db_session.query(RunEvent).filter(RunEvent.run_id == "run-1").one()
        row.event_id = "evt-1"
        db_session.commit()

        producer_q = registries._get_or_create_queue("run-1")
        registries._PIPELINE_TASKS["run-1"] = asyncio.current_task()

        sub_a = await registries._subscribe("run-1")
        sub_b = await registries._subscribe("run-1")
        try:
            producer_q.put_nowait({"type": "agent_start", "data": {"seq": 1, "event_id": "evt-1"}})
            producer_q.put_nowait(None)

            frames_a = await _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=0, live_queue=sub_a
                )
            )
            frames_b = await _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_store(db_session), after_seq=0, live_queue=sub_b
                )
            )
            for frames in (frames_a, frames_b):
                starts = [p for p in (_parse(f) for f in frames) if p["type"] == "agent_start"]
                assert len(starts) == 1
        finally:
            registries._cleanup_pipeline("run-1")


# ════════════════════════════════════════════════════════════════════════════
# C-06b — a stale pump (bound to an OLD producer-queue generation) must not
# close a NEW generation's subscriber, nor swallow the new backlog.
# ════════════════════════════════════════════════════════════════════════════
class TestPumpGenerationSafety:
    @pytest.mark.asyncio
    async def test_new_generation_gets_its_own_pump_and_backlog_is_not_orphaned(
        self, registries
    ):
        """Sequence from the bug report: cleanup sentinels the OLD queue (old pump
        still draining, not yet done) -> a resume registers a NEW queue under the
        SAME run_id -> a NEW subscriber must get a pump bound to the NEW generation,
        and the new backlog must reach it (not be swallowed by the stale pump)."""
        old_queue = registries._get_or_create_queue("run-1")
        registries._PIPELINE_TASKS["run-1"] = asyncio.current_task()

        # Attach a subscriber to generation 1 and start its pump.
        old_sub = await registries._subscribe("run-1")
        assert len(registries._PUMP_TASKS) == 1

        # Old pump is draining `old_queue` but has NOT yet seen its sentinel (it's
        # blocked on `await queue.get()`), so it is still un-done() when cleanup runs.
        registries._cleanup_pipeline("run-1")  # pops old queue/task, sentinels old_queue

        # A resume installs a NEW producer queue under the SAME run_id -> new generation.
        new_queue = registries._get_or_create_queue("run-1")
        registries._PIPELINE_TASKS["run-1"] = asyncio.current_task()
        assert new_queue is not old_queue

        # New backlog appears on the new queue BEFORE any new subscriber attaches
        # (mirrors "new_source_backlog: 2" from the bug report).
        new_queue.put_nowait({"type": "agent_start", "data": {"seq": 10}})
        new_queue.put_nowait({"type": "agent_chunk", "data": {"seq": 11}})

        new_sub = await registries._subscribe("run-1")

        # The NEW subscriber must receive the NEW backlog -- not hang, not get the
        # stale pump's sentinel forwarded to it.
        ev1 = await asyncio.wait_for(new_sub.get(), timeout=2.0)
        ev2 = await asyncio.wait_for(new_sub.get(), timeout=2.0)
        assert ev1 == {"type": "agent_start", "data": {"seq": 10}}
        assert ev2 == {"type": "agent_chunk", "data": {"seq": 11}}

        # The OLD subscriber (generation 1) must eventually get its OWN generation's
        # sentinel (from the old pump forwarding the cleanup's sentinel) -- but the
        # new subscriber's queue must NOT have received it.
        old_event = await asyncio.wait_for(old_sub.get(), timeout=2.0)
        assert old_event is None
        assert new_sub.qsize() == 0

        registries._cleanup_pipeline("run-1")

    @pytest.mark.asyncio
    async def test_ensure_pump_replaces_a_stale_generation_without_double_pumping(
        self, registries
    ):
        """`_ensure_pump` must not treat an old-generation pump as "already
        covering" a new generation -- it must start exactly one NEW pump bound to
        the current generation."""
        registries._get_or_create_queue("run-1")
        registries._PIPELINE_TASKS["run-1"] = asyncio.current_task()
        await registries._ensure_pump("run-1")
        first_task, first_gen = registries._PUMP_TASKS["run-1"]

        # Simulate a stale pump: it is still running (not done), bound to the OLD
        # generation, while a new queue/generation is installed for the same run_id.
        registries._PIPELINE_QUEUES.pop("run-1", None)
        registries._QUEUE_GENERATIONS.pop("run-1", None)
        registries._get_or_create_queue("run-1")  # new generation, new queue object

        await registries._ensure_pump("run-1")
        second_task, second_gen = registries._PUMP_TASKS["run-1"]

        assert second_gen != first_gen
        assert second_task is not first_task
        assert not first_task.done() or first_task.cancelled() is False

        first_task.cancel()
        registries._cleanup_pipeline("run-1")


# ════════════════════════════════════════════════════════════════════════════
# H-09 — a subscriber queue at maxsize must be EVICTED (unsubscribed + closed),
# never silently drop the event/sentinel while staying registered.
# ════════════════════════════════════════════════════════════════════════════
class TestBoundedQueueEviction:
    @pytest.mark.asyncio
    async def test_full_queue_is_evicted_not_silently_dropped(self, registries):
        registries._get_or_create_queue("run-1")
        registries._PIPELINE_TASKS["run-1"] = asyncio.current_task()

        sub_q = await registries._subscribe("run-1", queue_maxsize=1)
        # Fill the subscriber queue to maxsize so the NEXT dispatch overflows it.
        generation = registries._QUEUE_GENERATIONS["run-1"]
        await registries._dispatch_event_to_subscribers(
            "run-1", {"type": "agent_chunk", "data": {"seq": 1}}, generation
        )
        assert sub_q.full()

        # This dispatch overflows the maxsize=1 queue -> must evict, not silently pass.
        await registries._dispatch_event_to_subscribers(
            "run-1", {"type": "agent_chunk", "data": {"seq": 2}}, generation
        )

        # The subscriber must be unsubscribed (evicted) from the registry...
        subs = [q for (q, _g) in registries._SUBSCRIBERS.get("run-1", ())]
        assert sub_q not in subs
        # ...and its drain loop must observe a close signal (a None slot), not hang.
        got_none = False
        while not sub_q.empty():
            item = sub_q.get_nowait()
            if item is None:
                got_none = True
        assert got_none, "evicted subscriber must see a closing sentinel, not silence"

        registries._cleanup_pipeline("run-1")

    @pytest.mark.asyncio
    async def test_full_queue_sentinel_forward_also_evicts(self, registries):
        """A full queue dropping the TERMINAL sentinel is the worse half of H-09
        (it can leave the stream hanging) -- eviction must apply here too."""
        registries._get_or_create_queue("run-1")
        registries._PIPELINE_TASKS["run-1"] = asyncio.current_task()

        sub_q = await registries._subscribe("run-1", queue_maxsize=1)
        generation = registries._QUEUE_GENERATIONS["run-1"]
        await registries._dispatch_event_to_subscribers(
            "run-1", {"type": "agent_chunk", "data": {"seq": 1}}, generation
        )
        assert sub_q.full()

        await registries._dispatch_sentinel_to_subscribers("run-1", generation)

        subs = [q for (q, _g) in registries._SUBSCRIBERS.get("run-1", ())]
        assert sub_q not in subs

        registries._cleanup_pipeline("run-1")


# ════════════════════════════════════════════════════════════════════════════
# H-10 — the subscriber queue must be released on EVERY exit path, not just the
# happy-path live drain: a replay error, a gate-re-arm error, or a client abort
# before the generator body starts must all unsubscribe.
# ════════════════════════════════════════════════════════════════════════════
class TestSubscriberLeakOnErrorPaths:
    @pytest.mark.asyncio
    async def test_replay_failure_still_unsubscribes(self, registries):
        class _BoomStore:
            async def read_events(self, run_id, after_seq=0):
                raise RuntimeError("simulated durable-read failure")

            async def last_event_of_types(self, *a, **k):
                return None

        registries._get_or_create_queue("run-1")
        registries._PIPELINE_TASKS["run-1"] = asyncio.current_task()
        sub_q = await registries._subscribe("run-1")

        with pytest.raises(RuntimeError):
            await _collect(
                _iter_sse_frames(
                    run_id="run-1", store=_BoomStore(), after_seq=0, live_queue=sub_q
                )
            )

        subs = [q for (q, _g) in registries._SUBSCRIBERS.get("run-1", ())]
        assert sub_q not in subs, "a replay failure must not leak the subscriber queue"

        registries._cleanup_pipeline("run-1")

    @pytest.mark.asyncio
    async def test_gate_rearm_failure_still_unsubscribes(self, registries, db_session):
        class _BoomOnRearmStore:
            def __init__(self, inner):
                self._inner = inner

            async def read_events(self, run_id, after_seq=0):
                return await self._inner.read_events(run_id, after_seq=after_seq)

            async def last_event_of_types(self, *a, **k):
                raise RuntimeError("simulated gate-re-arm read failure")

        _seed_run(db_session)
        _seed_events(db_session, [(1, "agent_start", {"seq": 1})])

        registries._get_or_create_queue("run-1")
        registries._PIPELINE_TASKS["run-1"] = asyncio.current_task()
        sub_q = await registries._subscribe("run-1")

        with pytest.raises(RuntimeError):
            await _collect(
                _iter_sse_frames(
                    run_id="run-1",
                    store=_BoomOnRearmStore(_store(db_session)),
                    after_seq=1,  # after_seq > 0 is required to reach the re-arm query
                    live_queue=sub_q,
                )
            )

        subs = [q for (q, _g) in registries._SUBSCRIBERS.get("run-1", ())]
        assert sub_q not in subs, "a gate-re-arm failure must not leak the subscriber queue"

        registries._cleanup_pipeline("run-1")



# ════════════════════════════════════════════════════════════════════════════
# SSE-002 (R-07, ISS-147) — verify backend's _STREAM_TERMINAL_TYPES stays in
# sync with frontend's STREAM_TERMINAL_TYPES (frontend/src/types/index.ts).
# ════════════════════════════════════════════════════════════════════════════
class TestSSETerminalTypesSyncWithFrontend:
    def test_backend_terminal_types_match_frontend_constant(self):
        """SSE-002: verify _STREAM_TERMINAL_TYPES (backend) matches the frontend's
        STREAM_TERMINAL_TYPES constant. Both must enumerate the exact same terminal
        event types that close the SSE stream."""
        from app.api.run_stream import _STREAM_TERMINAL_TYPES

        backend_terminals = _STREAM_TERMINAL_TYPES
        expected = {
            "pipeline_complete",
            "pipeline_cancelled",
            "pipeline_failed",
            "budget_aborted",
            "error",
            # 014-conditional-gates R-13: a `trigger: workflow` outcome ends the run
            # with this frame and no pipeline_complete, so it closes the stream too.
            "pipeline_diverted",
        }

        assert backend_terminals == frozenset(expected), (
            f"backend _STREAM_TERMINAL_TYPES does not match expected constant. "
            f"Expected: {expected}, Got: {backend_terminals}. "
            f"If you added/removed a terminal event type, you MUST update "
            f"frontend/src/types/index.ts::STREAM_TERMINAL_TYPES to match "
            f"(SSE-002, ISS-147, R-07)."
        )


# ════════════════════════════════════════════════════════════════════════════
# SSE-003 (R-07) — Parser edge-case coverage: OPEN GAPS
#
# Scope note: chunk-boundary splitting is NOT a backend concern. The backend
# hands whole frame dicts to sse-starlette, which renders them; it never
# re-assembles a partial frame. Every split-boundary case below is therefore a
# FRONTEND parser concern (useRunStream.ts) and cannot be tested from here.
# They are recorded in this file only because that is where the SSE contract is
# pinned; the tests themselves belong in useRunStream.test.ts.
#
# FIXED — CRLF terminator split across two network chunks.
#   useRunStream.ts previously did, per chunk:
#       buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n")
#   The `.replace()` ran BEFORE concatenation, so a chunk boundary landing between
#   the `\r` and the `\n` of a CRLF left that pair un-normalised (chunk A ends
#   `...\r`, chunk B starts `\n...`; neither holds the full pair for the regex).
#   Two frames then coalesced into one block and the first was lost. Now appends
#   raw and normalises the accumulated `buf`, closing the seam. Covered by
#   useRunStream.test.ts "re-assembles a frame terminator split between the CR and
#   the LF" — verified to fail against the old per-chunk form.
#
# COVERED — Multi-byte UTF-8 sequence split across chunks.
#   `{ stream: true }` was always the correct mechanism, so this was a latent
#   coverage hole rather than a defect: every test fed the body as ONE chunk via
#   `serveWire`, so no multi-chunk decode ran. Now exercised by a byte-level split
#   mid-code-point ("re-assembles a multi-byte UTF-8 character split across
#   chunks"), using the new `serveWireSplitAtBytes` helper. Regression guard, not a
#   bug repro — it passes against the old code too.
#
# OPEN GAP — Gate re-arm (D-14g) on reconnect. PARTIALLY covered, by `TestGateRearm`
#   in this file (the `_dangling_review_gate` derivation). The end-to-end
#   "reconnect with after_seq > 0 re-fires review_gate_ready through
#   _iter_sse_frames" path is not asserted.
#
# NOT a gap — exhaustive terminal types. Now covered, two ways:
#   * `TestSSETerminalTypesSyncWithFrontend` pins the MEMBERSHIP of
#     _STREAM_TERMINAL_TYPES (catches a member being added or removed).
#   * `TestStreamAttachedHandshakeConvergence
#      ::test_terminal_event_closes_stream_deterministically` is parametrised
#     over every member and pins the BEHAVIOUR (each one ends the live drain).
#   The split matters: the parametrised test derives its cases FROM the set, so
#   it alone cannot detect a member being deleted — the sync test is what does.
# ════════════════════════════════════════════════════════════════════════════



# ════════════════════════════════════════════════════════════════════════════
# SSE-004 (R-07) — stream_attached handshake contract + terminal convergence
# (no duplicate events on reconnect, deterministic closure)
# ════════════════════════════════════════════════════════════════════════════
class TestStreamAttachedHandshakeConvergence:
    """SSE-004: verify stream_attached handshake and terminal event convergence.
    
    The handshake must correctly indicate:
      1. live=true/false (whether a live queue is attached)
      2. replayed_through_seq reflects the actual replay boundary
    
    Reconnect must never emit duplicate events (C-06a: event_id dedup).
    Terminal events must deterministically close the stream.
    """

    @pytest.mark.asyncio
    async def test_fresh_attach_handshake_marks_terminal_run_as_nolive(self, db_session):
        """SSE-004: a fresh attach (no Last-Event-ID) to a TERMINAL run yields:
        - durable replay (all events, seq=0 not filtered)
        - stream_attached {live=false, replayed_through_seq=<max_seq>}
        - stream closes (no live queue)
        """
        from app.models.run_event import RunEvent

        run_id = f"terminal-fresh-{uuid.uuid4().hex[:8]}"
        owner_id = "owner"  # Match _store default
        ws_id = "ws-1"

        wr = WorkflowRun(
            id=run_id,
            user_id=owner_id,
            title="Terminal Fresh Attach",
            type="sample",
            status="pipeline_complete",  # Terminal
            input="test",
            owner_id=owner_id,
            workspace_id=ws_id,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(wr)
        db_session.flush()

        # Seed 3 events, last one is terminal.
        for i in range(1, 4):
            db_session.add(
                RunEvent(
                    run_id=run_id,
                    workspace_id=ws_id,
                    owner_id=owner_id,
                    event_id=f"e-{i}",
                    seq=i,
                    type="pipeline_complete" if i == 3 else "agent_start",
                    payload_json={"seq": i},
                )
            )
        db_session.commit()

        # Fresh attach: after_seq=0, no live queue (terminal run).
        frames = await _collect(
            _iter_sse_frames(
                run_id=run_id,
                store=_store(db_session),
                after_seq=0,
                live_queue=None,
                run_is_terminal=True,
            )
        )

        parsed = [_parse(f) for f in frames]

        # Expect: 3 durable events (all replayed) + stream_attached + nothing else.
        durable = [p for p in parsed if p["type"] in {"agent_start", "pipeline_complete"}]
        assert len(durable) == 3, f"Expected 3 durable events, got {len(durable)}: {parsed}"

        # stream_attached should mark live=false and replayed_through_seq=3 (the max).
        attach = [p for p in parsed if p["type"] == "stream_attached"]
        assert len(attach) == 1, f"Expected 1 stream_attached, got {len(attach)}: {parsed}"
        assert attach[0]["data"]["live"] is False, "Terminal run should have live=false"
        assert attach[0]["data"]["replayed_through_seq"] == 3, (
            f"Expected replayed_through_seq=3 (max), got {attach[0]['data']['replayed_through_seq']}"
        )

        # No frames after stream_attached (stream closed immediately).
        attach_idx = next((i for i, p in enumerate(parsed) if p["type"] == "stream_attached"), -1)
        frames_after_attach = parsed[attach_idx + 1 :]
        assert len(frames_after_attach) == 0, (
            f"Terminal run should close after handshake, got {len(frames_after_attach)} extra frames: {frames_after_attach}"
        )

    @pytest.mark.asyncio
    async def test_reconnect_after_partial_drain_replays_only_newer_events(self, db_session):
        """SSE-004: a reconnect with Last-Event-ID set correctly bounds the replay.
        
        If client last saw seq=2, a fresh connect (after_seq=2) should replay only seq > 2.
        The stream_attached handshake reflects the actual replay boundary.
        """
        from app.models.run_event import RunEvent

        run_id = f"reconnect-{uuid.uuid4().hex[:8]}"
        owner_id = "owner"  # Match _store default
        ws_id = "ws-1"

        wr = WorkflowRun(
            id=run_id,
            user_id=owner_id,
            title="Reconnect Test",
            type="sample",
            status="pipeline_complete",
            input="test",
            owner_id=owner_id,
            workspace_id=ws_id,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(wr)
        db_session.flush()

        # Seed 5 events.
        for i in range(1, 6):
            db_session.add(
                RunEvent(
                    run_id=run_id,
                    workspace_id=ws_id,
                    owner_id=owner_id,
                    event_id=f"e-{i}",
                    seq=i,
                    type="pipeline_complete" if i == 5 else "agent_start",
                    payload_json={"seq": i},
                )
            )
        db_session.commit()

        # Reconnect: client's Last-Event-ID was seq=2, so after_seq=2.
        # Should replay only seq > 2 (i.e., seq=3,4,5).
        frames = await _collect(
            _iter_sse_frames(
                run_id=run_id,
                store=_store(db_session),
                after_seq=2,
                live_queue=None,
                run_is_terminal=True,
            )
        )

        parsed = [_parse(f) for f in frames]

        # Expect: 3 replayed events (seq=3,4,5) + stream_attached.
        replayed = [p for p in parsed if p["type"] in {"agent_start", "pipeline_complete"}]
        assert len(replayed) == 3, (
            f"Expected 3 replayed events (seq > 2), got {len(replayed)}: {parsed}"
        )
        replayed_seqs = {p["data"].get("seq") for p in replayed if p.get("data")}
        assert replayed_seqs == {3, 4, 5}, (
            f"Expected seq {{3,4,5}}, got {replayed_seqs}"
        )

        # stream_attached should mark replayed_through_seq=5 (the max replayed).
        attach = [p for p in parsed if p["type"] == "stream_attached"]
        assert len(attach) == 1
        assert attach[0]["data"]["replayed_through_seq"] == 5, (
            f"Expected replayed_through_seq=5, got {attach[0]['data']['replayed_through_seq']}"
        )

    # EVERY member of _STREAM_TERMINAL_TYPES is exercised, not an arbitrary one.
    # ``sorted()`` matters: iterating a frozenset of str yields a DIFFERENT order per
    # process (PYTHONHASHSEED randomisation), so a ``next(iter(...))`` pick would test a
    # random type each run — the exact class of silent gap that let ISS-147 ship. Sorting
    # makes the id list stable and the parametrisation auto-scales if the set ever grows.
    @pytest.mark.parametrize("terminal_type", sorted(_STREAM_TERMINAL_TYPES))
    @pytest.mark.asyncio
    async def test_terminal_event_closes_stream_deterministically(
        self, db_session, terminal_type
    ):
        """SSE-004: a terminal event (each member of _STREAM_TERMINAL_TYPES) in the live
        queue deterministically closes the stream — no extra frames after it.

        This verifies the live-drain loop's `if event.get("type") in _STREAM_TERMINAL_TYPES:
        return` branch works correctly.
        """
        run_id = f"terminal-live-{uuid.uuid4().hex[:8]}"
        owner_id = "owner"  # Match _store default
        ws_id = "ws-1"

        wr = WorkflowRun(
            id=run_id,
            user_id=owner_id,
            title="Terminal Live Event",
            type="sample",
            status="running",
            input="test",
            owner_id=owner_id,
            workspace_id=ws_id,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(wr)
        db_session.flush()

        # One durable event.
        db_session.add(
            RunEvent(
                run_id=run_id,
                workspace_id=ws_id,
                owner_id=owner_id,
                event_id="e-1",
                seq=1,
                type="agent_start",
                payload_json={"seq": 1},
            )
        )
        db_session.commit()

        # Live queue: durable event already read, then a terminal event, then more events
        # (which should NOT be yielded because the stream closes on the terminal).
        live_queue = asyncio.Queue()

        await live_queue.put({"type": terminal_type, "event_id": f"terminal-{terminal_type}", "data": {"seq": 2}})
        await live_queue.put({"type": "agent_complete", "event_id": "e-after", "data": {"seq": 3}})  # Should NOT be yielded
        await live_queue.put(None)  # Sentinel

        frames = await _collect(
            _iter_sse_frames(
                run_id=run_id,
                store=_store(db_session),
                after_seq=0,
                live_queue=live_queue,
                run_is_terminal=False,
            )
        )

        parsed = [_parse(f) for f in frames]

        # Expect: 1 replayed (seq=1) + stream_attached + 1 terminal event, total 3.
        # The "agent_complete" event after the terminal should NOT appear.
        assert len(parsed) == 3, (
            f"Expected 3 frames (durable + attach + terminal), got {len(parsed)}: {parsed}"
        )

        # Verify the terminal is the last frame.
        last = parsed[-1]
        assert last["type"] == terminal_type, (
            f"Expected terminal type '{terminal_type}' as last frame, got {last['type']}"
        )

    # C-06a event_id dedup on reconnect is deliberately NOT re-tested here.
    # `TestReplayLiveDedup` (above) already covers it three ways, each stronger than
    # a single-queue restatement would be: the plain durable-row-plus-queued-event
    # repro, a `_SlowStore` variant that lands the event on the queue DURING the
    # replay window, and a real two-subscriber fan-out-bus variant asserting both
    # subscribers observe the same de-duplicated order. Adding a fourth, weaker
    # version here would be maintenance cost with no new signal.
