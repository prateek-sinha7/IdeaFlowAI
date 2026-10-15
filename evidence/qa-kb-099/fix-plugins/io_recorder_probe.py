"""Scratch pytest plugin (QA-KB-099 fix probe): RECORD, never deny, every DB connect,
socket connect and subprocess spawn made by a test, so the allow_io reasons can be checked.

Imports neither app nor the engine (a plugin that does binds the live Postgres).
"""

import json
import os
import socket
import subprocess

import pytest
import sqlalchemy
from sqlalchemy.engine import Engine

_LOG = os.environ["IO_PROBE_LOG"]


def _rec(test, kind, detail):
    with open(_LOG, "a") as fh:
        fh.write(json.dumps({"test": test, "kind": kind, "detail": detail}) + "\n")


@pytest.fixture(autouse=True)
def _io_recorder(request, monkeypatch):
    name = request.node.name

    def on_connect(dbapi_conn, record):
        _rec(name, "db_connect", repr(dbapi_conn)[:200])

    sqlalchemy.event.listen(Engine, "connect", on_connect)
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_init = subprocess.Popen.__init__

    def rec_connect(self, address, *a, **k):
        _rec(name, "socket_connect", repr(address))
        return real_connect(self, address, *a, **k)

    def rec_connect_ex(self, address, *a, **k):
        _rec(name, "socket_connect_ex", repr(address))
        return real_connect_ex(self, address, *a, **k)

    def rec_popen(self, *a, **k):
        argv = a[0] if a else k.get("args")
        _rec(name, "popen", repr(argv)[:200])
        return real_init(self, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", rec_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", rec_connect_ex)
    monkeypatch.setattr(subprocess.Popen, "__init__", rec_popen)
    try:
        yield
    finally:
        sqlalchemy.event.remove(Engine, "connect", on_connect)
