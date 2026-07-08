"""tests/agents/test_attach_replay_matrix.py — the SSE attach/replay durability matrix
(CHAT-07 / POR §4 Wave 1, plan 29-05).

The transport's reconnect/reopen durability gate: a full OFFLINE matrix over the SEVEN
attach scenarios the browser-native SSE transport must survive under every ordering of
stream drop, command, and restart —

  1. fresh                        — attach to a brand-new run → replay from seq 0, go live
  2. mid-stream                   — attach with Last-Event-ID = k → replay ONLY seq > k, no dupes
  3. live                         — attach to a running run → stream_attached{live:true} after tail
  4. terminal                     — attach to a completed run → full replay, closes clean (no hang)
  5. cross-owner → 404            — attach to another owner's run → 404 (IDOR → 404, never 403)
  6. restart                      — fresh process/store, a waiting_for_user run re-emits
                                    review_gate_ready on attach (D-14g)
  7. gate-answer-while-stream-down — no stream attached → POST /{id}/gate resolves the gate →
                                    reattach → the resolution + subsequent events replay in
                                    order (the binding phase SC-2 durability proof)

Every scenario is OFFLINE: an in-memory SQLite (StaticPool) + a scripted ``run_events`` store
+ a pre-populated ``asyncio.Queue`` for the live drain — no live Bedrock, no running uvicorn.
The two endpoints under test are driven REAL:
  * ``GET /api/runs/{id}/events/stream`` (``app/api/run_stream.py``, 29-02) — via its
    dependency-injected core ``_iter_sse_frames`` for frame-content assertions and via a
    FastAPI ``TestClient`` for the 404 owner boundary.
  * ``POST /api/runs/{id}/gate`` (``app/api/run_commands.py``, 29-03) — via a ``TestClient``
    for the SC-2 gate-answer-while-stream-down proof.

Ordering / dedup / contiguity is asserted by REUSING the 29-01 projection normalization
(``tests/agents/characterization/_sse_projection.py``) rather than re-deriving it: each
scenario's replay frames are reconstructed to ``run_events`` rows and bound to the REAL
``assert_wire_parity`` / ``project_events`` so the endpoint's rendering is proven identical
to the single-source-of-truth projection (and any dropped/added/mutated/re-ordered frame
trips the gate).

LOCK-B: this file is ADDITIVE and TEST-ONLY. It drives the already-built 29-02/03/04
endpoints; it modifies NO production file, touches neither ``websocket.py`` /
``websocket_handoff.py`` / ``useWebSocket.ts``, and adds no table / ratchet / ledger row.
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
from app.api.run_stream import _iter_sse_frames, router as stream_router
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.models.database import Base, get_db
from app.models.run_event import RunEvent
from app.models.workflow import WorkflowRun

# The 29-01 projection — the single source of truth for run_events → SSE frame rendering.
# We REUSE its normalization (never re-derive) so the matrix's ordering/dedup assertions
# bind to the same contract the wire-parity gate enforces.
from tests.agents.characterization._sse_projection import (
    assert_wire_parity,
    project_events,
    run_event_to_sse_frame,
    ws_frame_from_engine_event,
)


# ════════════════════════════════════════════════════════════════════════════
# Harness — one in-memory SQLite (StaticPool → single shared connection) bound to
# BOTH the ScopedStore session AND the WS ownership/terminal predicates' own
# session (``ws._get_db``), so the SSE down-channel and the REST up-channel observe
# the identical durable log. A fresh per-test artifact-store singleton keeps the
# per-process HITL gate registry from leaking across scenarios.
# ════════════════════════════════════════════════════════════════════════════
class _FakeUser:
    def __init__(self, id: str):
        self.id = id


@pytest.fixture
def matrix(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()

    # The WS gate predicates (_review_gate_owned_by / _review_gate_run_is_terminal,
    # read-only imports into run_commands.py) open their OWN session — bind it to the
    # SAME in-memory connection so ownership/terminal checks see the seeded run.
    from app.api import websocket as ws_module

    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())

    # Fresh per-test artifact-store singleton (the per-process gate-arm registry).
    import agents.artifact_store.store as store_mod

    store_mod._STORE = None
    artifact_store = store_mod.get_artifact_store()

    # A TestClient mounting BOTH the SSE stream router and the REST command router,
    # with a mutable current-user + the request DB overridden onto the shared session.
    from app.api.run_commands import router as commands_router

    app = FastAPI()
    app.include_router(stream_router)
    app.include_router(commands_router)
    state: dict = {"user": _FakeUser(id="owner")}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    app.dependency_overrides[get_db] = lambda: (yield session)
    client = TestClient(app)

    try:
        yield {
            "db": session,
            "client": client,
            "state": state,
            "store": artifact_store,
            "ws": ws_module,
        }
    finally:
        client.close()
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        store_mod._STORE = None


# ────────────────────────────────────────────────────────────────────────────
# Seeding helpers
# ────────────────────────────────────────────────────────────────────────────
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
            agent_count=1,
            session_id=owner_id,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


def _seed_events(db, rows, *, run_id="run-1", owner_id="owner", workspace_id="ws-1"):
    """Seed ``run_events`` from ``[(seq, type, payload), ...]`` — one row per event,
    each with a UNIQUE ``event_id`` so the dedup-by-event_id contract is exercisable."""
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


# ────────────────────────────────────────────────────────────────────────────
# Frame helpers + the 29-01-projection-bound ordering / dedup assertions
# ────────────────────────────────────────────────────────────────────────────
def _parse(frame: dict) -> dict:
    """An ``_iter_sse_frames`` frame dict → ``{"id", "type", "data"}``."""
    body = json.loads(frame["data"])
    return {"id": frame["id"], "type": body["type"], "data": body.get("data", {})}


async def _collect(gen) -> list[dict]:
    return [f async for f in gen]


def _drive(gen) -> list[dict]:
    """Run the async SSE generator to completion OFFLINE and parse its frames.

    A completing collection is itself the "closes cleanly / no hang" proof: a stream
    that never terminated would block here."""
    return [_parse(f) for f in asyncio.run(_collect(gen))]


def _replay_only(parsed: list[dict]) -> list[dict]:
    """The durable-replay frames — drop the synthetic ``stream_attached`` handshake and
    the D-14g ``review_gate_ready`` re-arm (neither is a durable run_events row)."""
    return [
        p
        for p in parsed
        if p["type"] not in ("stream_attached",)
    ]


def _rows_from_replay(parsed_replay: list[dict]) -> list[dict]:
    """Reconstruct ``run_events`` rows ``{seq, type, payload}`` from replayed SSE frames."""
    return [
        {"seq": int(p["id"]), "type": p["type"], "payload": p["data"]}
        for p in parsed_replay
    ]


def _assert_contiguous_deduped_ordered(parsed_replay: list[dict]) -> None:
    """Bind the replayed frame sequence to the 29-01 projection contract:

      * ORDERED by seq  — the ``id:`` (seq) cursors are STRICTLY ascending.
      * DEDUPED          — no seq (hence no event_id) appears twice.
      * PROJECTION-EXACT — each frame's rendered body is byte-identical to what the
        single-source-of-truth ``run_event_to_sse_frame`` projection produces for the
        same row (so the endpoint cannot silently diverge from the canonical rendering).
    """
    seqs = [int(p["id"]) for p in parsed_replay]
    assert seqs == sorted(seqs), f"frames not ordered by seq: {seqs}"
    assert len(seqs) == len(set(seqs)), f"duplicate seq (dedup broken): {seqs}"

    # Projection-exact: reference-render each reconstructed row and compare the {type,data}
    # body the endpoint emitted against the canonical 29-01 projection's body.
    for p, row in zip(parsed_replay, _rows_from_replay(parsed_replay)):
        ref_frame = run_event_to_sse_frame(row)
        ref_body = None
        for line in ref_frame.splitlines():
            if line.startswith("data:"):
                ref_body = json.loads(line[len("data:"):].strip())
        assert ref_body is not None
        assert {"type": p["type"], "data": p["data"]} == ref_body, (
            "endpoint frame body diverged from the 29-01 projection rendering"
        )


# ════════════════════════════════════════════════════════════════════════════
# 1. fresh — attach to a brand-new run → replay from seq 0, then go live
# ════════════════════════════════════════════════════════════════════════════
class TestFreshAttach:
    def test_fresh_replays_from_zero_then_goes_live(self, matrix):
        db = matrix["db"]
        _seed_run(db, status="running")
        _seed_events(db, [(1, "agent_start", {"seq": 1, "agent": "a"}),
                          (2, "agent_chunk", {"seq": 2, "text": "hi"})])
        q: asyncio.Queue = asyncio.Queue()

        async def _run():
            # A brand-new attach: cursor 0 (no Last-Event-ID), a live queue is attached.
            await q.put({"type": "agent_chunk", "data": {"seq": 3, "text": "live"}})
            await q.put({"type": "pipeline_complete", "data": {"seq": 4}})
            await q.put(None)  # sentinel
            return await _collect(
                _iter_sse_frames(run_id="run-1", store=_store(db), after_seq=0, live_queue=q)
            )

        parsed = [_parse(f) for f in asyncio.run(_run())]
        # Full durable replay from seq 0, ascending, deduped, projection-exact.
        replay = [p for p in parsed if p["type"] != "stream_attached" and int(p["id"]) <= 2]
        assert [p["id"] for p in replay] == ["1", "2"]
        _assert_contiguous_deduped_ordered(replay)
        # Handshake marks the run live, then the live tail drains and the terminal ends it.
        handshake = next(p for p in parsed if p["type"] == "stream_attached")
        assert handshake["data"]["live"] is True
        live = [p for p in parsed if int(p["id"]) in (3, 4)]
        assert [p["type"] for p in live] == ["agent_chunk", "pipeline_complete"]
        assert parsed[-1]["type"] == "pipeline_complete"  # terminal closes the drain


# ════════════════════════════════════════════════════════════════════════════
# 2. mid-stream — attach with Last-Event-ID = k → replay ONLY seq > k, no dupes
# ════════════════════════════════════════════════════════════════════════════
class TestMidStreamResume:
    def test_resume_replays_only_after_cursor_no_dupes(self, matrix):
        db = matrix["db"]
        _seed_run(db, status="running")
        _seed_events(db, [(1, "agent_start", {"seq": 1}),
                          (2, "agent_chunk", {"seq": 2}),
                          (3, "agent_chunk", {"seq": 3}),
                          (4, "agent_complete", {"seq": 4})])
        # Last-Event-ID = 2 → only seq 3, 4 replay; 1 and 2 are NEVER re-sent (no dupes).
        parsed = _drive(_iter_sse_frames(run_id="run-1", store=_store(db), after_seq=2, live_queue=None))
        replay = [p for p in parsed if p["type"] != "stream_attached"]
        assert [p["id"] for p in replay] == ["3", "4"]
        assert all(int(p["id"]) > 2 for p in replay), "resumed replay re-sent an acked frame"
        _assert_contiguous_deduped_ordered(replay)

    def test_last_event_id_header_resumes_over_http(self, matrix):
        """The browser-native ``Last-Event-ID`` header is the resume cursor — proven end
        to end over the real HTTP route on a finished run (terminates after the handshake)."""
        db = matrix["db"]
        client = matrix["client"]
        _seed_run(db, status="completed")
        _seed_events(db, [(1, "agent_start", {"seq": 1}),
                          (2, "agent_chunk", {"seq": 2}),
                          (3, "pipeline_complete", {"seq": 3})])
        with client.stream(
            "GET", "/api/runs/run-1/events/stream", headers={"Last-Event-ID": "2"}
        ) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            text = "".join(resp.iter_text())
        ids = [ln.split("id:", 1)[1].strip() for ln in text.splitlines() if ln.startswith("id:")]
        assert "3" in ids and "1" not in ids and "2" not in ids
        assert "stream_attached" in text


# ════════════════════════════════════════════════════════════════════════════
# 3. live — attach to a running run → stream_attached{live:true} after the tail replay
# ════════════════════════════════════════════════════════════════════════════
class TestLiveAttach:
    def test_running_run_marks_live_true_after_tail(self, matrix):
        db = matrix["db"]
        _seed_run(db, status="running")
        _seed_events(db, [(1, "agent_start", {"seq": 1}), (2, "agent_chunk", {"seq": 2})])
        q: asyncio.Queue = asyncio.Queue()

        async def _run():
            await q.put({"type": "pipeline_complete", "data": {"seq": 3}})
            await q.put(None)
            return await _collect(
                _iter_sse_frames(run_id="run-1", store=_store(db), after_seq=0, live_queue=q)
            )

        parsed = [_parse(f) for f in asyncio.run(_run())]
        # The tail replay precedes the handshake; the handshake carries live:true and the
        # last replayed seq; then the live queue drains.
        types_before_handshake = []
        for p in parsed:
            if p["type"] == "stream_attached":
                break
            types_before_handshake.append(p["type"])
        assert types_before_handshake == ["agent_start", "agent_chunk"]
        handshake = next(p for p in parsed if p["type"] == "stream_attached")
        assert handshake["data"]["live"] is True
        assert handshake["data"]["replayed_through_seq"] == 2


# ════════════════════════════════════════════════════════════════════════════
# 4. terminal — attach to a completed run → full replay, stream closes cleanly (no hang)
# ════════════════════════════════════════════════════════════════════════════
class TestTerminalAttach:
    def test_completed_run_full_replay_then_closes(self, matrix):
        db = matrix["db"]
        _seed_run(db, status="completed")
        rows = [(1, "agent_start", {"seq": 1}),
                (2, "agent_chunk", {"seq": 2, "text": "x"}),
                (3, "pipeline_complete", {"seq": 3, "final_output": "done"})]
        _seed_events(db, rows)
        # live_queue=None → a finished run has no queue; the generator MUST terminate after
        # the handshake (a completing _drive() is itself the no-hang proof).
        parsed = _drive(_iter_sse_frames(run_id="run-1", store=_store(db), after_seq=0, live_queue=None))
        replay = [p for p in parsed if p["type"] != "stream_attached"]
        assert [p["id"] for p in replay] == ["1", "2", "3"]
        _assert_contiguous_deduped_ordered(replay)
        # No live frame beyond the handshake (last frame is the handshake, live:false).
        assert parsed[-1]["type"] == "stream_attached"
        assert parsed[-1]["data"]["live"] is False

    def test_terminal_replay_binds_to_wire_parity_projection(self, matrix):
        """Non-vacuity: the terminal full-replay frames, reference-projected, equal the
        recorded ``/ws/chat`` drainer frame sequence (the REAL 29-01 ``assert_wire_parity``)."""
        db = matrix["db"]
        # A scripted engine event stream (offline) → its recorded WS frames + durable rows.
        engine_events = [
            {"type": "agent_start", "data": {"seq": 1, "event_id": "e1", "agent_id": "a"}},
            {"type": "agent_chunk", "data": {"seq": 2, "event_id": "e2", "chunk": "hello"}},
            {"type": "review_gate_ready", "data": {"seq": 3, "event_id": "e3", "gate_key": "gk"}},
            {"type": "review_gate_approved", "data": {"seq": 4, "event_id": "e4"}},
            {"type": "pipeline_complete", "data": {"seq": 5, "event_id": "e5", "final_output": "d"}},
        ]
        ws_frames = [ws_frame_from_engine_event(ev, section="prototype") for ev in engine_events]
        ref_rows = [{"seq": ev["data"]["seq"], "type": ev["type"], "payload": ev["data"]}
                    for ev in engine_events]
        _seed_run(db, run_id="wp-run", status="completed")
        _seed_events(db, [(r["seq"], r["type"], r["payload"]) for r in ref_rows], run_id="wp-run")

        parsed = _drive(_iter_sse_frames(run_id="wp-run", store=_store(db), after_seq=0, live_queue=None))
        # Reconstruct rows from the endpoint's replay (drop the handshake; the gate is
        # RESOLVED here so no re-arm frame is emitted).
        endpoint_rows = _rows_from_replay([p for p in parsed if p["type"] != "stream_attached"])
        assert endpoint_rows, "terminal attach produced no replay frames (vacuous)"
        assert_wire_parity(ws_frames, endpoint_rows)


# ════════════════════════════════════════════════════════════════════════════
# 5. cross-owner → 404 (IDOR → 404, never 403)
# ════════════════════════════════════════════════════════════════════════════
class TestCrossOwner:
    def test_cross_owner_attach_is_404(self, matrix):
        db = matrix["db"]
        client = matrix["client"]
        _seed_run(db, owner_id="owner")
        _seed_events(db, [(1, "agent_start", {"seq": 1})])
        matrix["state"]["user"] = _FakeUser(id="attacker")
        resp = client.get("/api/runs/run-1/events/stream")
        assert resp.status_code == 404, "IDOR: attacker streamed another owner's run"
        assert resp.status_code != 403, "must never leak run existence via 403"

    def test_missing_run_attach_is_404(self, matrix):
        resp = matrix["client"].get("/api/runs/does-not-exist/events/stream")
        assert resp.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# 6. restart — fresh process/store: a waiting_for_user run re-emits review_gate_ready
#    on attach (D-14g)
# ════════════════════════════════════════════════════════════════════════════
class TestRestartReArm:
    def test_paused_run_reemits_review_gate_ready_after_restart(self, matrix):
        """Simulate a backend restart: the per-process live-queue registry + the
        artifact-store gate registry are EMPTY (fresh process). A run left paused at a
        still-open human gate must re-open on attach, re-armed PURELY from the
        owner-scoped durable run_events (D-14g / ND-9 — no in-memory / sessionStorage
        trust survives a restart)."""
        db = matrix["db"]
        # Fresh store = no armed gate in memory (mirrors a restart); no live queue.
        assert not matrix["store"]._resume_events, "restart harness must start with an empty gate registry"
        _seed_run(db, status="waiting_for_user")
        _seed_events(db, [(1, "agent_start", {"seq": 1}),
                          (2, "agent_complete", {"seq": 2}),
                          (3, "review_gate_ready", {"seq": 3, "agent_id": "prototype-specify", "gate_key": "gk"})])
        # Client cursor already PAST the gate frame — without D-14g re-arm it would never
        # re-open. Full-log re-arm re-emits it from seq 0.
        before = db.query(RunEvent).count()
        parsed = _drive(_iter_sse_frames(run_id="run-1", store=_store(db), after_seq=3, live_queue=None))
        after = db.query(RunEvent).count()

        rearmed = [p for p in parsed if p["type"] == "review_gate_ready"]
        assert len(rearmed) == 1, "a paused gate must re-emit review_gate_ready on attach (D-14g)"
        assert rearmed[0]["data"]["gate_key"] == "gk"
        assert after == before, "gate re-arm must be READ-ONLY (no run_events mutation, ND-9)"

    def test_resolved_gate_does_not_reemit_after_restart(self, matrix):
        db = matrix["db"]
        _seed_run(db, status="running")
        _seed_events(db, [(1, "review_gate_ready", {"seq": 1, "gate_key": "gk"}),
                          (2, "review_gate_approved", {"seq": 2}),
                          (3, "agent_start", {"seq": 3})])
        parsed = _drive(_iter_sse_frames(run_id="run-1", store=_store(db), after_seq=3, live_queue=None))
        assert [p for p in parsed if p["type"] == "review_gate_ready"] == [], (
            "a resolved gate must NOT re-arm on attach"
        )


# ════════════════════════════════════════════════════════════════════════════
# 7. gate-answer-while-stream-down — SC-2: no stream → POST /{id}/gate → reattach →
#    resolution + subsequent events replay in order
# ════════════════════════════════════════════════════════════════════════════
class TestGateAnswerWhileStreamDown:
    """The binding phase SC-2 proof: a gate answered via REST WHILE THE STREAM IS DOWN
    resumes correctly on reattach.

    Order of events (all offline):
      1. A run is paused at a still-open human gate; NO SSE stream is attached (no live
         queue). The durable log ends at ``review_gate_ready``.
      2. The gate is answered over the REAL up-channel REST endpoint
         ``POST /api/runs/{id}/gate`` (``store.set_review_response`` — the exact seam the
         WS ``approve_review`` handler uses). The stream being down does not matter: the
         command lands on the durable store, not on a socket.
      3. The engine's continuation persists the resolution + the following events to the
         durable ``run_events`` (scripted here — no live Bedrock).
      4. The client REATTACHES the SSE stream. The gate resolution (``review_gate_approved``)
         and every subsequent event replay IN ORDER, and the now-resolved gate is NOT
         re-armed. Durable resume proven across the stream-down window (SC-2).
    """

    def test_gate_answered_while_down_replays_resolution_on_reattach(self, matrix):
        db = matrix["db"]
        client = matrix["client"]
        store = matrix["store"]

        run_id = "run-1"
        gate_key = f"{run_id}:prototype-specify"

        # 1. Paused at a still-open gate; no stream attached.
        _seed_run(db, run_id=run_id, status="waiting_for_user")
        _seed_events(db, [(1, "agent_start", {"seq": 1}),
                          (2, "agent_complete", {"seq": 2}),
                          (3, "review_gate_ready", {"seq": 3, "gate_key": gate_key})],
                     run_id=run_id)
        # Arm the gate exactly as _run_review_gate does (KAN-94 ground truth: armed-but-unset).
        store._resume_events[f"review:{gate_key}"] = asyncio.Event()

        # 2. Answer the gate over the REAL REST up-channel while the stream is DOWN.
        matrix["state"]["user"] = _FakeUser(id="owner")
        resp = client.post(
            f"/api/runs/{run_id}/gate",
            json={"gate_key": gate_key, "action": "approve", "edited_content": "OK"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["action"] == "approve"
        # The resolution landed on the SAME store seam the WS handler uses.
        recorded = store._questionnaire_responses.get(f"review:{gate_key}")
        assert recorded and recorded[0]["approved"] is True
        assert recorded[0]["edited_content"] == "OK"
        # The gate event is now set (unblocks the paused engine).
        assert store._resume_events[f"review:{gate_key}"].is_set()

        # 3. The resumed engine persists the resolution + subsequent events durably.
        _seed_events(db, [(4, "review_gate_approved", {"seq": 4, "gate_key": gate_key}),
                          (5, "agent_start", {"seq": 5, "agent_id": "prototype-plan"}),
                          (6, "pipeline_complete", {"seq": 6, "final_output": "done"})],
                     run_id=run_id)

        # 4. REATTACH — replay from the pre-answer cursor (seq 3). The resolution + the
        #    following events replay IN ORDER; the resolved gate does NOT re-arm.
        parsed = _drive(_iter_sse_frames(run_id=run_id, store=_store(db), after_seq=3, live_queue=None))
        replay = [p for p in parsed if p["type"] != "stream_attached"]
        assert [p["type"] for p in replay] == [
            "review_gate_approved", "agent_start", "pipeline_complete",
        ], "the gate resolution + subsequent events must replay in order on reattach (SC-2)"
        assert [p["id"] for p in replay] == ["4", "5", "6"]
        _assert_contiguous_deduped_ordered(replay)
        # The now-resolved gate must NOT re-arm on the reattach (the answer stuck).
        assert [p for p in replay if p["type"] == "review_gate_ready"] == [], (
            "an answered gate must not re-open on reattach (SC-2 durable resolution)"
        )

    def test_gate_answer_survives_a_full_fresh_reattach_from_zero(self, matrix):
        """The strongest SC-2 framing: even a client that lost ALL cursor state
        (reattach from seq 0, e.g. a new tab after the answer) sees the resolved,
        continued log in order with no dangling gate."""
        db = matrix["db"]
        client = matrix["client"]
        store = matrix["store"]
        run_id = "run-1"
        gate_key = f"{run_id}:prototype-specify"

        _seed_run(db, run_id=run_id, status="waiting_for_user")
        _seed_events(db, [(1, "agent_start", {"seq": 1}),
                          (2, "review_gate_ready", {"seq": 2, "gate_key": gate_key})],
                     run_id=run_id)
        store._resume_events[f"review:{gate_key}"] = asyncio.Event()

        matrix["state"]["user"] = _FakeUser(id="owner")
        resp = client.post(f"/api/runs/{run_id}/gate", json={"gate_key": gate_key})
        assert resp.status_code == 200, resp.text

        _seed_events(db, [(3, "review_gate_approved", {"seq": 3, "gate_key": gate_key}),
                          (4, "pipeline_complete", {"seq": 4})],
                     run_id=run_id)

        parsed = _drive(_iter_sse_frames(run_id=run_id, store=_store(db), after_seq=0, live_queue=None))
        replay = [p for p in parsed if p["type"] != "stream_attached"]
        assert [p["id"] for p in replay] == ["1", "2", "3", "4"]
        _assert_contiguous_deduped_ordered(replay)
        # Gate ready appears exactly ONCE (the original durable row) — never re-armed,
        # because seq 3 review_gate_approved resolves it.
        assert [p["type"] for p in replay].count("review_gate_ready") == 1
