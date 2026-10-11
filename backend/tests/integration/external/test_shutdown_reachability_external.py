"""tests/integration/external/test_shutdown_reachability_external.py — ISS-088, real process.

A real uvicorn SUBPROCESS, a live SSE stream and a real SIGTERM must reach the
lifespan shutdown half. Split out of ``tests/unit/services/test_shutdown_reachability.py``:
it spawns a process and opens sockets, which the unit I/O guard
(``tests/unit/conftest.py``) correctly refuses. The config/budget/wiring checks stay
in the unit module. The test body is byte-identical to its original.
"""

from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_DIR = REPO_ROOT / "backend"
DOCKER_ENTRYPOINT = BACKEND_DIR / "docker-entrypoint.sh"
DOCKER_COMPOSE = REPO_ROOT / "docker-compose.yml"


# ════════════════════════════════════════════════════════════════════════════
# Single sources of truth — parsed, never hardcoded, so drift in either file
# fails these tests instead of silently changing the budget.
# ════════════════════════════════════════════════════════════════════════════
def _uvicorn_graceful_window_seconds() -> float:
    """The ``--timeout-graceful-shutdown`` uvicorn is launched with in production."""
    text = DOCKER_ENTRYPOINT.read_text(encoding="utf-8")
    match = re.search(r"--timeout-graceful-shutdown\s+(\d+(?:\.\d+)?)", text)
    assert match, (
        "docker-entrypoint.sh no longer passes --timeout-graceful-shutdown. Without it "
        "uvicorn waits forever for a live SSE stream to close and the lifespan shutdown "
        "half never runs (ISS-088)."
    )
    return float(match.group(1))


# ════════════════════════════════════════════════════════════════════════════
# 1. Reachability — a real subprocess, a live stream, a real SIGTERM
# ════════════════════════════════════════════════════════════════════════════
# Deliberately NOT an import of app.main: booting the real application runs
# restore_non_terminal_runs() (main.py:238), which auto-resumes in-flight runs. This
# app mirrors only the shape under test — a lifespan whose shutdown half records that
# it ran, and the same sse_starlette.EventSourceResponse run_stream.py:421 uses.
_PROBE_APP_SOURCE = """
import asyncio, json, os, time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sse_starlette import EventSourceResponse

MARKER = os.environ["PROBE_MARKER"]


def _stamp(event):
    with open(MARKER, "a") as fh:
        fh.write(json.dumps({"event": event, "t": time.time()}) + "\\n")


@asynccontextmanager
async def lifespan(app):
    _stamp("startup_complete")
    yield
    # stands in for main.py's shutdown half -> shutdown_run_infrastructure()
    _stamp("lifespan_shutdown_entered")
    await asyncio.sleep(0.2)
    _stamp("shutdown_body_completed")


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/stream")
async def stream():
    async def gen():
        while True:
            yield {"data": json.dumps({"type": "tick"})}
            await asyncio.sleep(0.5)

    return EventSourceResponse(gen(), ping=15)
"""


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for_health(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5) as sock:
                sock.sendall(
                    b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
                )
                if b"200" in sock.recv(256):
                    return True
        except OSError:
            pass
        time.sleep(0.2)
    return False


def _open_live_stream(port: int) -> socket.socket:
    """Open an SSE stream and leave it open — the connection uvicorn must not wait on."""
    sock = socket.create_connection(("127.0.0.1", port), timeout=5.0)
    sock.sendall(b"GET /stream HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
    first = sock.recv(4096)
    assert b"200" in first, f"stream did not start: {first!r}"
    return sock


@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "SIGTERM/graceful-shutdown semantics under test are POSIX-specific "
        "(uvicorn signal handling + docker stop_grace_period target Linux "
        "production); this is REL-001's Linux-only reliability case, not a "
        "portable one — see task.md R-08/REL-001."
    ),
)
def test_sigterm_reaches_the_lifespan_shutdown_half_while_a_stream_is_live(tmp_path):
    """SIGTERM with a live SSE stream must exit AND run the lifespan shutdown body.

    Fail-before: drop ``--timeout-graceful-shutdown`` from ``extra_args`` and this test
    hangs to the wait budget and fails with only ``startup_complete`` recorded — which is
    the defect ISS-088 describes.
    """
    app_file = tmp_path / "reachability_probe_app.py"
    app_file.write_text(_PROBE_APP_SOURCE)
    marker = tmp_path / "markers.jsonl"

    graceful = _uvicorn_graceful_window_seconds()
    port = _free_port()
    env = {**os.environ, "PROBE_MARKER": str(marker), "PYTHONPATH": str(tmp_path)}

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "reachability_probe_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--timeout-graceful-shutdown",
            str(int(graceful)),
            "--log-level",
            "error",
        ],
        cwd=str(tmp_path),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    stream_sock = None
    try:
        assert _wait_for_health(port, timeout=30.0), "probe server never became healthy"
        stream_sock = _open_live_stream(port)
        time.sleep(1.0)  # let the stream produce, so it is unambiguously mid-response

        # The graceful window bounds uvicorn's wait; the lifespan body then runs
        # unbounded, so allow generous headroom before calling it a hang.
        wait_budget = graceful + 20.0
        started = time.monotonic()
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=wait_budget)
        except subprocess.TimeoutExpired:
            pytest.fail(
                f"uvicorn did not exit within {wait_budget}s of SIGTERM while an SSE "
                f"stream was live. Markers written: {marker.read_text(encoding='utf-8') if marker.exists() else '(none)'}"
            )
        elapsed = time.monotonic() - started
    finally:
        if stream_sock is not None:
            stream_sock.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)

    events = [
        line for line in marker.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    joined = "\n".join(events)
    assert "startup_complete" in joined, f"probe never started: {joined}"
    assert "lifespan_shutdown_entered" in joined, (
        "SIGTERM exited the process but the lifespan shutdown half never ran — the "
        f"Concierge drain, pump teardown and close_checkpointer() are all unreachable. "
        f"Markers: {joined}"
    )
    assert (
        "shutdown_body_completed" in joined
    ), f"the lifespan shutdown body was entered but did not run to completion: {joined}"
    assert elapsed < graceful + 20.0
