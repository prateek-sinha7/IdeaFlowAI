"""The unit suite's I/O guard must actually fire — and must be escapable on purpose.

A guard with no test is a guard that rots: the previous name-level sentinel was bypassed
by every ``from sqlalchemy import create_engine`` in the suite for months, and the
network half was a no-op on Windows (it allowed every AF_INET SOCK_STREAM socket to be
created, which is all of them). These tests pin the three interception layers in
``tests/unit/conftest.py::_unit_io_guard`` at the layer that cannot be bypassed by how a
name was imported.

Nothing here performs real I/O: every attempt is refused by the guard under test, which
is exactly what makes these tests hermetic.
"""

from __future__ import annotations

import socket
import subprocess

import pytest

# Imported BY VALUE at module scope on purpose: this is the exact pattern that defeats a
# `monkeypatch.setattr(sqlalchemy, "create_engine", ...)` sentinel, so the connect-layer
# guard has to be what catches it.
from sqlalchemy import create_engine

from tests.unit.conftest import UnitIsolationError


def test_database_connection_is_refused_even_when_create_engine_was_imported_by_value():
    """The Engine-level connect listener fires however create_engine was imported."""
    engine = create_engine("sqlite://")  # constructing is allowed; connecting is not
    with pytest.raises(UnitIsolationError, match="real database connection"):
        engine.connect()


def test_sqlite_file_database_is_refused_too(tmp_path):
    """A file-backed SQLite engine is still a real DBAPI connection, so still refused.

    Deliberate: "it's only SQLite in tmp_path" is the most common way a persistence test
    ends up in the unit suite.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'x.db'}")
    with pytest.raises(UnitIsolationError):
        engine.connect()


def test_subprocess_run_is_refused():
    """subprocess.run funnels through Popen.__init__, which the guard replaces."""
    with pytest.raises(UnitIsolationError, match="spawned a subprocess"):
        subprocess.run(["git", "--version"], capture_output=True)


def test_subprocess_popen_is_refused():
    with pytest.raises(UnitIsolationError, match="spawned a subprocess"):
        subprocess.Popen(["git", "--version"])


def test_outbound_socket_connect_is_refused():
    """No unit test may reach a real endpoint. 10.255.255.1 is never dialled."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(UnitIsolationError, match="network socket"):
            sock.connect(("10.255.255.1", 80))
    finally:
        sock.close()


def test_outbound_socket_connect_ex_is_refused():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(UnitIsolationError, match="network socket"):
            sock.connect_ex(("10.255.255.1", 80))
    finally:
        sock.close()


def test_socketpair_still_works_so_async_tests_can_build_an_event_loop():
    """The one exemption: a self-connected pair, which asyncio needs on Windows.

    ``ProactorEventLoop.__init__`` builds its self-pipe with ``socket.socketpair()``,
    implemented in pure Python as bind/listen/connect/accept. Without this exemption every
    async test in the suite fails at fixture setup.
    """
    left, right = socket.socketpair()
    try:
        left.send(b"ok")
        assert right.recv(2) == b"ok"
    finally:
        left.close()
        right.close()


@pytest.mark.asyncio
async def test_async_tests_still_get_an_event_loop():
    """End-to-end proof of the exemption: an async test runs at all."""
    import asyncio

    await asyncio.sleep(0)
    assert asyncio.get_running_loop() is not None


@pytest.mark.allow_io(
    "proves the documented escape hatch works; the I/O performed is an in-memory "
    "SQLite connection that reaches no external service"
)
def test_allow_io_marker_opts_a_test_out_of_the_guard():
    """``@pytest.mark.allow_io(reason)`` disables the guard for that test only.

    This is the suite's ONLY allow_io marker. Any other one is a test that should have
    moved to tests/integration/ instead.
    """
    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        from sqlalchemy import text

        assert conn.execute(text("select 1")).scalar() == 1
