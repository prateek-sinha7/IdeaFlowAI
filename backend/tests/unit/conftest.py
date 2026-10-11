"""Shared fixtures for the unit suite.

Core concerns:
1. Keep the LangGraph checkpointer from leaking across event loops (per-test in-memory).
2. Make real I/O impossible: a database connection, a subprocess, or an outbound socket
   fails loudly and names the suite the test belongs in instead.

Why the guard intercepts at the connect/spawn layer (``_unit_io_guard``) and not by name:
``monkeypatch.setattr(sqlalchemy, "create_engine", ...)`` rebinds an ATTRIBUTE, so a
module that did ``from sqlalchemy import create_engine`` at import time already holds the
original function and sails straight past it. That is not hypothetical — it is how ~45
files in this suite were building real engines, and how the whole of
``tests/unit/agents/`` did until Batch 6. The by-name patches below are kept anyway:
when the by-name path IS the one taken they produce a much clearer message, and they
cost nothing.

Opting out requires an explicit reason: ``@pytest.mark.allow_io("why")``. Audit those
regularly — each one is a test that is not really a unit test.
"""

from __future__ import annotations

import socket
import subprocess
import threading

import pytest
import sqlalchemy
from sqlalchemy.engine import Engine


class UnitIsolationError(RuntimeError):
    """A unit test attempted real I/O. Move it to tests/integration/."""


# Re-entrancy counter for the ``socket.socketpair`` exemption below. Thread-local because
# the connect happens on whichever thread called socketpair (asyncio builds its self-pipe
# on the thread creating the loop), and a plain bool would race under a threadpool.
_SOCKETPAIR_DEPTH = threading.local()


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
    visible in the captured log.

    ``tests/plugins/agents_fixtures.py`` carries a suite-wide autouse equivalent; this
    one is deliberately NARROWER (it repoints only the checkpointer, not
    ``settings.DATABASE_URL``) so unit tests that assert against the configured URL are
    unaffected.
    """
    from langgraph.checkpoint.memory import InMemorySaver

    from app.agents import checkpointer as checkpointer_module

    # Fresh saver per test, bound to this test's loop; the monkeypatch teardown
    # restores the previous globals so ordering cannot leak one either way.
    monkeypatch.setattr(checkpointer_module, "_checkpointer", InMemorySaver())
    monkeypatch.setattr(checkpointer_module, "_pool", None)
    yield


def _deny_db_connect(dbapi_connection, connection_record):  # noqa: ARG001
    """SQLAlchemy ``connect`` event listener — refuses every real DBAPI connection."""
    raise UnitIsolationError(
        "Unit test opened a real database connection. Move it to "
        "tests/integration/<mirror>/ (the hermetic in-memory SQLite db_session fixture "
        "lives in tests/integration/repositories/conftest.py), or mock the Session with "
        "MagicMock(spec=Session) / AsyncMock(spec=AsyncSession). "
        'Deliberate exception: @pytest.mark.allow_io("reason").'
    )


@pytest.fixture(autouse=True)
def _unit_io_guard(request, monkeypatch):
    """Fail loudly on any database connection, subprocess spawn, or outbound socket.

    Intercepts at the connect/spawn layer, so a by-value ``from x import y`` cannot
    bypass it:

    1. **Database** — a SQLAlchemy ``Engine``-level ``connect`` event listener fires for
       every engine in the process no matter how ``create_engine`` was imported, and for
       SQLite as much as Postgres (a file- or memory-backed SQLite engine is still a real
       DBAPI connection, and a unit test has no business opening one).
    2. **Subprocess** — ``subprocess.run`` / ``call`` / ``check_output`` / ``Popen`` all
       funnel through ``Popen.__init__``.
    3. **Network** — ``socket.connect`` / ``connect_ex`` is the layer where a real
       connection is attempted. Creating a socket object is harmless and stays allowed;
       ASGI transports and respx/httpx mock transports never reach this layer at all.

       ONE exemption, and it is not optional: on Windows ``ProactorEventLoop.__init__``
       builds its self-pipe with ``socket.socketpair()``, which is implemented in pure
       Python as bind/listen/**connect**/accept. Blocking that breaks event-loop creation
       for every async test in the suite (observed: 17 setup errors in three files). So
       ``socket.socketpair`` is wrapped and connects made INSIDE it are allowed. A pair
       can only ever talk to itself, so this cannot become an escape hatch to a real
       service.

    ``event.remove`` runs in a ``finally`` so a test that ERRORS cannot leak the listener
    into the next test.
    """
    marker = request.node.get_closest_marker("allow_io")
    if marker is not None:
        yield
        return

    sqlalchemy.event.listen(Engine, "connect", _deny_db_connect)

    real_popen_init = subprocess.Popen.__init__

    def _deny_popen(self, *args, **kwargs):
        argv = args[0] if args else kwargs.get("args")
        raise UnitIsolationError(
            f"Unit test spawned a subprocess: {argv!r}. Move it to "
            "tests/integration/ (suffix _external), or assert against the command it "
            "would have built instead of running it. "
            'Deliberate exception: @pytest.mark.allow_io("reason").'
        )

    monkeypatch.setattr(subprocess.Popen, "__init__", _deny_popen)

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_socketpair = socket.socketpair

    def _in_socketpair() -> bool:
        return getattr(_SOCKETPAIR_DEPTH, "value", 0) > 0

    def _guarded_socketpair(*args, **kwargs):
        _SOCKETPAIR_DEPTH.value = getattr(_SOCKETPAIR_DEPTH, "value", 0) + 1
        try:
            return real_socketpair(*args, **kwargs)
        finally:
            _SOCKETPAIR_DEPTH.value -= 1

    def _deny_connect(self, address, *args, **kwargs):
        if _in_socketpair():
            return real_connect(self, address, *args, **kwargs)
        raise UnitIsolationError(
            f"Unit test opened a network socket to {address!r}. Mock the client "
            "(respx / httpx MockTransport / ASGITransport), or move the test to "
            'tests/integration/. Deliberate exception: @pytest.mark.allow_io("reason").'
        )

    def _deny_connect_ex(self, address, *args, **kwargs):
        if _in_socketpair():
            return real_connect_ex(self, address, *args, **kwargs)
        raise UnitIsolationError(
            f"Unit test probed a network socket at {address!r}. Mock the client, or "
            'move the test to tests/integration/. Exception: @pytest.mark.allow_io("…").'
        )

    monkeypatch.setattr(socket, "socketpair", _guarded_socketpair)
    monkeypatch.setattr(socket.socket, "connect", _deny_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _deny_connect_ex)

    try:
        yield
    finally:
        sqlalchemy.event.remove(Engine, "connect", _deny_db_connect)
        # monkeypatch restores Popen.__init__ and the socket methods itself; keep the
        # real reference alive so a traceback can still show what was patched out.
        del real_popen_init


@pytest.fixture(autouse=True)
def _forbid_real_database_access(monkeypatch):
    """Clearer message for the COMMON case: the DB seam reached by name.

    Redundant with ``_unit_io_guard`` by design — this one fires earlier (at
    ``create_engine`` / ``get_db`` / ``SessionLocal``, before any connection is
    attempted) and can therefore say exactly which seam was used. It is NOT sufficient
    on its own: patching a module attribute cannot touch a name that was imported
    by value, which is what ``_unit_io_guard`` exists to cover.
    """
    import sqlalchemy as sa
    from sqlalchemy.ext import asyncio as sa_asyncio

    def forbidden_create_engine(*args, **kwargs):
        """Raise immediately if a unit test tries to build a real connection."""
        raise UnitIsolationError(
            "❌ Unit tests must not call create_engine(). "
            "If you need a real database, move this test to tests/integration/. "
            "For unit tests, mock the Session/AsyncSession using MagicMock(spec=Session). "
            "See tests/unit/conftest.py and the test-structure guide."
        )

    def forbidden_async_create_engine(*args, **kwargs):
        """Raise immediately if a unit test tries to build a real async connection."""
        raise UnitIsolationError(
            "❌ Unit tests must not call create_async_engine(). "
            "If you need a real database, move this test to tests/integration/. "
            "For unit tests, mock the AsyncSession using AsyncMock(spec=AsyncSession). "
            "See tests/unit/conftest.py and the test-structure guide."
        )

    def forbidden_get_db():
        """Raise immediately if a unit test tries to use get_db() dependency."""
        raise UnitIsolationError(
            "❌ Unit tests must not call get_db(). "
            "If you need a real database, move this test to tests/integration/. "
            "For unit tests, override get_db with a mock Session via app.dependency_overrides. "
            "See tests/unit/conftest.py and the test-structure guide."
        )

    def forbidden_session_local():
        """Raise immediately if a unit test tries to instantiate SessionLocal."""
        raise UnitIsolationError(
            "❌ Unit tests must not instantiate SessionLocal(). "
            "If you need a real database, move this test to tests/integration/. "
            "For unit tests, mock the Session using MagicMock(spec=Session). "
            "See tests/unit/conftest.py and the test-structure guide."
        )

    # Patch at the sqlalchemy module level (handles import-time calls)
    monkeypatch.setattr(sa, "create_engine", forbidden_create_engine)
    monkeypatch.setattr(
        sa_asyncio, "create_async_engine", forbidden_async_create_engine
    )

    # Patch at the dependency injection level (handles FastAPI app.dependency_overrides)
    try:
        import app.core.dependencies as deps_module

        monkeypatch.setattr(deps_module, "get_db", forbidden_get_db)
    except (ImportError, AttributeError):
        pass  # Module may not exist in all environments

    # Patch at the session factory level (handles direct SessionLocal() calls)
    try:
        import app.models.database as db_module

        monkeypatch.setattr(db_module, "SessionLocal", forbidden_session_local)
    except (ImportError, AttributeError):
        pass  # SessionLocal may not be exposed in all environments

    yield
