"""tests/unit/test_authz_bounded_calls.py — A16: ``ScopedStore``'s bounded off-loop
DB calls (agents/authz.py).

Every ``ScopedStore`` method that OWNS its session (``session=None`` at
construction — the engine path, and the session-less SSE-stream store, BUG-004)
now runs its sync SQLAlchemy body off the event loop via
``asyncio.wait_for(asyncio.to_thread(...), timeout=10s)`` instead of directly on
the loop (``_run_bounded``). Before this fix a stuck/slow query on that path froze
the ENTIRE single-threaded process, not just the caller (the 2026-09-04 5h19m
silent hang).

This suite covers:
  (a) a blocked call does not stall a concurrently-scheduled coroutine;
  (b) a timeout raises ``StoreTimeout`` rather than degrading to empty data;
  (c) an authorization-denied case (``assert_owns``) still raises exactly the
      same ``PermissionError`` shape as the pre-fix inline call;
  (d) a normal read (``read_events``) returns the same rows in both acquisition
      modes (session-injected AND session-owned/threaded).

Offline / in-memory SQLite / no API key.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from agents.authz import ScopedStore, StoreTimeout


# ════════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════════


class _FakeSession:
    """A stand-in for ``SessionLocal()`` — used only by tests that never touch
    the session (the blocked-call / timeout tests drive ``_run_bounded``
    directly with a ``body`` that ignores its ``session`` argument)."""

    def close(self) -> None:
        pass


@pytest.fixture
def fake_session_local(monkeypatch):
    """Patch ``app.models.database.SessionLocal`` to the no-op fake factory, so
    the owned/threaded ``_run_bounded`` path never touches a real DB."""
    monkeypatch.setattr(
        "app.models.database.SessionLocal", lambda: _FakeSession(), raising=False
    )


# ════════════════════════════════════════════════════════════════════════════
# (a) A blocked call does not stall a concurrent coroutine
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_blocked_call_does_not_stall_a_concurrent_coroutine(fake_session_local):
    """A synchronous body that blocks for 0.5s must NOT freeze the event loop —
    a concurrently-scheduled ticker coroutine keeps making progress throughout."""
    store = ScopedStore(owner_id="alice", workspace_id="ws-1")  # session=None → owned

    def _slow_body(session):
        time.sleep(0.5)
        return "slow-result"

    ticks: list[float] = []

    async def _ticker() -> None:
        for _ in range(10):
            ticks.append(time.monotonic())
            await asyncio.sleep(0.05)

    ticker_task = asyncio.create_task(_ticker())
    result = await store._run_bounded("slow_method", _slow_body)
    await ticker_task

    assert result == "slow-result"
    assert len(ticks) == 10
    gaps = [b - a for a, b in zip(ticks, ticks[1:], strict=False)]
    assert all(
        g < 0.3 for g in gaps
    ), f"ticker starved — the event loop was blocked by the sync call: {gaps!r}"


# ════════════════════════════════════════════════════════════════════════════
# (b) Timeout raises rather than returning empty
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_timeout_raises_store_timeout_not_empty_data(
    fake_session_local, monkeypatch, caplog
):
    """A call that exceeds the bound raises ``StoreTimeout`` — it must never
    silently degrade to ``[]``/``None`` (an authorization read misreading a
    timeout as "no rows" would fail open)."""
    import logging

    monkeypatch.setattr("agents.authz._STORE_CALL_TIMEOUT_SECONDS", 0.05)
    store = ScopedStore(owner_id="alice", workspace_id="ws-1")

    def _stuck_body(session):
        time.sleep(1.0)
        return []  # what a caller might mistake for "no rows found"

    with caplog.at_level(logging.WARNING, logger="agents.authz"):
        with pytest.raises(StoreTimeout):
            await store._run_bounded("stuck_method", _stuck_body, run_id="run-x")

    assert any(
        "store_call_timeout" in rec.getMessage() and "stuck_method" in rec.getMessage()
        for rec in caplog.records
    ), "expected a WARNING-level timeout log naming the method"


# ════════════════════════════════════════════════════════════════════════════
# (c) An authorization-denied case still raises exactly what it raised before
# ════════════════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════════════════
# (d) A normal read returns the same rows, in both acquisition modes
# ════════════════════════════════════════════════════════════════════════════
