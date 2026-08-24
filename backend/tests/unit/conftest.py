"""Shared fixtures for the unit suite.

Currently one concern: keeping the LangGraph checkpointer from leaking across
event loops. See ``_in_process_checkpointer`` below.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _in_process_checkpointer(monkeypatch):
    """Give every unit test its own in-memory checkpointer.

    ``get_checkpointer()`` caches a PROCESS-WIDE singleton (``_checkpointer`` /
    ``_pool`` module globals). With a Postgres ``DATABASE_URL`` — which is what a
    developer's ``backend/.env`` points at — that singleton is an
    ``AsyncPostgresSaver`` over an async pool, and the pool's ``asyncio.Lock``
    objects bind to the event loop that created them.

    pytest-asyncio gives each test function a FRESH event loop. So the first test
    to drive an agent built the saver and bound its locks to that loop; every later
    test reused the cached instance from a different loop and died with::

        RuntimeError: <asyncio.locks.Lock object at 0x…> is bound to a
                      different event loop

    which the runner swallowed into an ``agent_error``, so the tests failed with a
    bare ``assert [] == [...]`` — no completion events — and the real cause was only
    visible in the captured log. Six tests failed this way
    (``test_revision_intelligence`` ×5, ``test_deliverable_mimetype``), every one of
    them passing when run alone.

    ``tests/agents/conftest.py`` already solves this with ``in_process_checkpointer``,
    which is why the agents suite was immune; ``tests/unit`` had no conftest at all.

    This is deliberately NARROWER than the agents version: that one also repoints
    ``settings.DATABASE_URL`` at sqlite, which would pull the rug from under the unit
    tests that assert against the real database (``..._on_real_db``). Here only the
    checkpointer is redirected — nothing else observes the change.

    Correct dependency, not a compromise: no unit test asserts anything about
    checkpoint durability. Cross-restart persistence is covered by
    ``tests/agents/test_phase8_resume.py``, which runs its own Postgres in
    subprocesses.
    """
    from langgraph.checkpoint.memory import InMemorySaver

    from app.agents import checkpointer as checkpointer_module

    # Fresh saver per test, bound to this test's loop; the monkeypatch teardown
    # restores the previous globals so ordering cannot leak one either way.
    monkeypatch.setattr(checkpointer_module, "_checkpointer", InMemorySaver())
    monkeypatch.setattr(checkpointer_module, "_pool", None)
    yield
