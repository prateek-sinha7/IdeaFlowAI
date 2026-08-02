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
from app.api.run_stream import _iter_sse_frames, router
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
        assert replay[0]["data"] == {"seq": 2, "text": "hi"}

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
        for t in run_engine_mod._PUMP_TASKS.values():
            t.cancel()
        run_engine_mod._PUMP_TASKS.clear()

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

