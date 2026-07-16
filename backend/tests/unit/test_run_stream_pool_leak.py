"""tests/unit/test_run_stream_pool_leak.py — BUG-004 SSE DB-connection-leak regression.

OFFLINE behavioral regression for the connection leak on the per-run SSE down-channel
(``GET /api/runs/{id}/events/stream`` → ``app/api/run_stream.py::stream_run_events``),
activated by the Phase-44 WS→SSE cutover.

Root cause (verified in ``.planning/BUG-004-GROUNDED-CONTEXT.md`` + ``/tmp/sse_pool_repro2.py``):
``stream_run_events`` builds ``ScopedStore(session=db)`` and consumes it INSIDE the streaming
generator ``_iter_sse_frames`` (``read_events`` at replay + gate re-arm). FastAPI >= 0.106 tears
down the ``get_db`` yield-dependency BEFORE the streaming body runs, so ``get_db``'s
``finally: db.close()`` fires first; the generator's query then re-acquires a FRESH QueuePool
connection on the already-closed session, and ``ScopedStore._acquire`` reports ``owned=False``
(``authz.py:95-99``) so ``read_events``'s ``finally: if owned: session.close()`` (``authz.py:328-330``)
NEVER releases it. Each live SSE stream leaks one connection, reclaimed only by GC.

Why QueuePool (not StaticPool as test_sse_stream.py uses): ``engine.pool.checkedout()`` is only
meaningful on ``QueuePool``. ``StaticPool`` always pins one connection and cannot show the leak.

Tests:
  * ``test_injected_closed_session_leaks`` — pins the root-cause mechanism: an injected+closed
    session re-acquires a connection on ``read_events`` and (owned=False) never returns it →
    ``checkedout()`` stays >= 1; only ``gc.collect()`` (after dropping refs) reclaims it.
  * ``test_sessionless_store_no_leak`` — the fix idiom: a SESSION-LESS ``ScopedStore`` opens+closes
    its own ``SessionLocal`` per read (owned=True), so ``checkedout()`` returns to baseline after
    each read WITHOUT gc.
  * ``test_stream_endpoint_returns_connections`` — THE regression guard (fail-before / pass-after
    on ``run_stream.py``): drive ``stream_run_events`` end-to-end against a QueuePool engine via an
    in-process uvicorn server (the ``/tmp/sse_pool_repro2.py`` variant known to reproduce the
    FastAPI teardown-before-streaming ordering), consume the full ``text/event-stream``, then assert
    ``checkedout()`` returns to baseline WITHOUT gc.
"""

from __future__ import annotations

import asyncio
import gc
import socket
import tempfile
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

import app.models.database as database_module
from agents.authz import ScopedStore
from app.models.database import Base
from app.models.run_event import RunEvent
from app.models.workflow import WorkflowRun

_OWNER = "owner-heb"
_WS = "ws-heb"
_RUN = "run-heb"


class _FakeUser:
    def __init__(self, id: str):
        self.id = id


def _make_queuepool_engine():
    """A QueuePool-backed file-SQLite engine (checkedout() is only meaningful on QueuePool).

    pool_size=1 / max_overflow=2 / pool_timeout=2 mirrors ``/tmp/sse_pool_repro2.py`` so a
    single leaked connection is observable against a small, deterministic ceiling.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_engine(
        f"sqlite:///{tmp.name}",
        connect_args={"check_same_thread": False},
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=2,
        pool_timeout=2,
    )
    Base.metadata.create_all(bind=engine)
    return engine


def _seed(session_factory):
    db = session_factory()
    try:
        db.add(
            WorkflowRun(
                id=_RUN,
                user_id=_OWNER,
                title="My Run",
                type="prototype",
                status="completed",
                input="idea",
                owner_id=_OWNER,
                workspace_id=_WS,
                created_at=datetime.now(timezone.utc),
            )
        )
        for seq, etype, payload in [
            (1, "agent_start", {"seq": 1, "agent": "a"}),
            (2, "agent_chunk", {"seq": 2, "text": "hi"}),
            (3, "pipeline_complete", {"seq": 3}),
        ]:
            db.add(
                RunEvent(
                    id=str(uuid.uuid4()),
                    run_id=_RUN,
                    owner_id=_OWNER,
                    workspace_id=_WS,
                    seq=seq,
                    event_id=str(uuid.uuid4()),
                    type=etype,
                    payload_json=payload,
                )
            )
        db.commit()
    finally:
        db.close()


# ════════════════════════════════════════════════════════════════════════════
# 1. Mechanism — an injected+closed session leaks (owned=False never closes)
# ════════════════════════════════════════════════════════════════════════════
def test_injected_closed_session_leaks(monkeypatch):
    engine = _make_queuepool_engine()
    SessionLocal = sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    monkeypatch.setattr(database_module, "SessionLocal", SessionLocal)
    _seed(SessionLocal)

    baseline = engine.pool.checkedout()

    # Mimic get_db's lifecycle: open a request session, use it, then close it (FastAPI
    # tears the yield-dependency down BEFORE the streaming body runs).
    db = SessionLocal()
    db.query(RunEvent).filter(RunEvent.run_id == _RUN).all()
    db.close()

    # The generator's store reuses that (closed) injected session and reads INSIDE the
    # stream — read_events re-acquires a fresh connection; owned=False → never closed.
    store = ScopedStore(owner_id=_OWNER, workspace_id=_WS, session=db)
    rows = asyncio.run(store.read_events(_RUN, after_seq=0))
    assert len(rows) == 3

    leaked = engine.pool.checkedout()
    assert leaked >= baseline + 1, (
        f"expected the injected+closed session to LEAK a connection "
        f"(checkedout {leaked} should exceed baseline {baseline})"
    )

    # Only GC (once the session refs are dropped) reclaims the leaked connection — this
    # pins the root-cause mechanism (reclaimed by GC, not by read_events' finally).
    del store, db, rows
    gc.collect()
    assert engine.pool.checkedout() == baseline, "gc.collect() should reclaim the leak"
    engine.dispose()


# ════════════════════════════════════════════════════════════════════════════
# 2. Fix idiom — a session-less store returns its connection per read (no gc)
# ════════════════════════════════════════════════════════════════════════════
def test_sessionless_store_no_leak(monkeypatch):
    engine = _make_queuepool_engine()
    SessionLocal = sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    monkeypatch.setattr(database_module, "SessionLocal", SessionLocal)
    _seed(SessionLocal)

    baseline = engine.pool.checkedout()

    # No session= → _acquire opens a fresh SessionLocal (owned=True) and read_events'
    # finally closes it, returning the connection to the pool WITHOUT gc.
    store = ScopedStore(owner_id=_OWNER, workspace_id=_WS)
    for _ in range(4):
        rows = asyncio.run(store.read_events(_RUN, after_seq=0))
        assert len(rows) == 3
        assert engine.pool.checkedout() == baseline, (
            "session-less store must return its connection after each read (no gc)"
        )
    engine.dispose()


# ════════════════════════════════════════════════════════════════════════════
# 3. Regression guard — the SSE endpoint returns its connection (fail-before/pass-after)
# ════════════════════════════════════════════════════════════════════════════
def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_stream_endpoint_returns_connections(monkeypatch):
    import httpx
    import uvicorn
    from fastapi import FastAPI

    from app.api.run_stream import router
    from app.core.dependencies import get_current_user
    from app.models.database import get_db

    engine = _make_queuepool_engine()
    SessionLocal = sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    # The session-less generator store (the fix) opens SessionLocal on THIS instrumented
    # pool; the pre-fix injected-session path leaks on it. Either way, one pool is watched.
    monkeypatch.setattr(database_module, "SessionLocal", SessionLocal)
    _seed(SessionLocal)

    app = FastAPI()
    app.include_router(router)

    def override_user():
        return _FakeUser(id=_OWNER)

    def override_db():
        # Mirror the REAL get_db: fresh session, closed in finally — this is what makes
        # FastAPI tear the connection down BEFORE the streaming body runs (the leak trigger).
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db

    # The run is NOT registered in run_engine._PIPELINE_QUEUES → live_queue is None →
    # the generator does replay + handshake + gate re-arm, then returns (finished-run path).
    port = _free_port()

    async def _drive() -> int:
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        )
        task = asyncio.create_task(server.serve())
        # Wait for the server to accept connections.
        for _ in range(50):
            if getattr(server, "started", False):
                break
            await asyncio.sleep(0.1)

        baseline = engine.pool.checkedout()
        async with httpx.AsyncClient(timeout=10) as client:
            async with client.stream(
                "GET", f"http://127.0.0.1:{port}/api/runs/{_RUN}/events/stream"
            ) as r:
                assert r.status_code == 200
                async for _ in r.aiter_lines():
                    pass
        # Let the server-side generator finish tearing down (no gc.collect()).
        await asyncio.sleep(0.3)
        after = engine.pool.checkedout()

        server.should_exit = True
        await task
        return after - baseline

    delta = asyncio.run(_drive())
    engine.dispose()

    assert delta == 0, (
        f"SSE stream leaked {delta} DB connection(s): the endpoint must return every "
        f"checked-out connection to the pool after the generator is exhausted, WITHOUT "
        f"gc.collect() (BUG-004 regression guard)"
    )
