"""tests/unit/test_checkpointer_shutdown_budget.py — ISS-106.

``close_checkpointer()`` (``app/agents/checkpointer.py``) is step 4 of
``shutdown_run_infrastructure()`` and runs AFTER the 24s of bounded drains
FIX-234 documented, sitting between the application and process exit. It
awaits ``pool_to_close.close()`` with no timeout, so a Postgres pool that is
slow to close (wedged socket, unresponsive server) pushes total teardown past
``stop_grace_period`` (30s) and docker SIGKILLs mid-teardown — the exact
failure the drain budget exists to prevent.

This test stands in a fake pool whose ``close()`` hangs forever and asserts
``close_checkpointer()`` still returns within a short bound. It fails today
because there is no timeout wrapper around ``pool_to_close.close()``.
"""

from __future__ import annotations

import asyncio

import pytest

import app.agents.checkpointer as checkpointer_mod


class _HangingPool:
    """A pool whose close() never returns, standing in for a wedged Postgres
    connection close."""

    async def close(self) -> None:
        await asyncio.sleep(3600)


@pytest.fixture(autouse=True)
def _isolate_checkpointer_globals(monkeypatch):
    """Point the module's globals at a hanging pool and reset the close latch,
    without touching a real Postgres connection."""
    monkeypatch.setattr(checkpointer_mod, "_pool", _HangingPool())
    monkeypatch.setattr(checkpointer_mod, "_checkpointer", object())
    monkeypatch.setattr(checkpointer_mod, "_closed", False)
    yield


@pytest.mark.issue("ISS-106")
@pytest.mark.asyncio
async def test_close_checkpointer_is_bounded_when_pool_close_hangs():
    """ISS-106 — close_checkpointer() must not be able to hang indefinitely
    just because pool.close() does; it must return within the shutdown
    budget, not push teardown past docker's SIGKILL deadline."""
    try:
        await asyncio.wait_for(checkpointer_mod.close_checkpointer(), timeout=2.0)
    except asyncio.TimeoutError:
        pytest.fail(
            "close_checkpointer() did not return within the shutdown budget "
            "when pool.close() hung — it has no internal timeout wrapper "
            "(checkpointer.py:140-144)."
        )
