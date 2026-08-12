"""tests/unit/test_shutdown_reachability.py — ISS-088.

``tests/unit/test_run_shutdown.py`` covers the *body* of
``shutdown_run_infrastructure()``. Nothing covered whether that body is ever REACHED,
and that is exactly what broke: uvicorn's ``timeout_graceful_shutdown`` defaults to
``None`` (``uvicorn/config.py:215``), and ``H11Protocol.shutdown()`` does NOT close a
connection whose response is still streaming — it only clears keep_alive
(``uvicorn/protocols/http/h11_impl.py:328-337``). A live ``EventSourceResponse``
therefore never leaves ``server_state.connections``, ``_wait_tasks_to_complete()`` spins
forever (``uvicorn/server.py:294-310``), and ``await self.lifespan.shutdown()`` on line
292 is never reached. Measured before the fix: SIGTERM left the process alive past 30s
with only ``startup_complete`` written; SIGKILL was the only thing that ended it.

These tests pin the four things that keep that path honest:

  1. a real uvicorn SUBPROCESS, a live SSE stream and a real SIGTERM actually reach the
     lifespan shutdown half (the test that would have caught the defect);
  2. ``docker-entrypoint.sh`` still passes the flag that makes (1) true in production;
  3. the teardown budget still fits inside docker's ``stop_grace_period``;
  4. ``close_checkpointer()`` is wired exactly ONCE on the shutdown path.

(1) must be a subprocess, not the in-process ``uvicorn.Server`` of
``test_run_stream_pool_leak.py:196-238``: ``Server.capture_signals()`` installs its
handlers only when it is on the main thread, and the whole defect lives in the signal
path.
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

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
DOCKER_ENTRYPOINT = BACKEND_DIR / "docker-entrypoint.sh"
DOCKER_COMPOSE = REPO_ROOT / "docker-compose.yml"


# ════════════════════════════════════════════════════════════════════════════
# Single sources of truth — parsed, never hardcoded, so drift in either file
# fails these tests instead of silently changing the budget.
# ════════════════════════════════════════════════════════════════════════════
def _uvicorn_graceful_window_seconds() -> float:
    """The ``--timeout-graceful-shutdown`` uvicorn is launched with in production."""
    text = DOCKER_ENTRYPOINT.read_text()
    match = re.search(r"--timeout-graceful-shutdown\s+(\d+(?:\.\d+)?)", text)
    assert match, (
        "docker-entrypoint.sh no longer passes --timeout-graceful-shutdown. Without it "
        "uvicorn waits forever for a live SSE stream to close and the lifespan shutdown "
        "half never runs (ISS-088)."
    )
    return float(match.group(1))


def _stop_grace_period_seconds() -> float:
    """docker's hard SIGKILL ceiling for the backend service."""
    text = DOCKER_COMPOSE.read_text()
    match = re.search(r"stop_grace_period:\s*(\d+(?:\.\d+)?)s", text)
    assert match, "docker-compose.yml no longer declares stop_grace_period for the backend."
    return float(match.group(1))


# ════════════════════════════════════════════════════════════════════════════
# 1. Reachability — a real subprocess, a live stream, a real SIGTERM
# ════════════════════════════════════════════════════════════════════════════
# Deliberately NOT an import of app.main: booting the real application runs
# restore_non_terminal_runs() (main.py:238), which auto-resumes in-flight runs. This
# app mirrors only the shape under test — a lifespan whose shutdown half records that
# it ran, and the same sse_starlette.EventSourceResponse run_stream.py:421 uses.
_PROBE_APP_SOURCE = '''
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
'''


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
            sys.executable, "-m", "uvicorn", "reachability_probe_app:app",
            "--host", "127.0.0.1", "--port", str(port),
            "--timeout-graceful-shutdown", str(int(graceful)),
            "--log-level", "error",
        ],
        cwd=str(tmp_path), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
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
                f"stream was live. Markers written: {marker.read_text() if marker.exists() else '(none)'}"
            )
        elapsed = time.monotonic() - started
    finally:
        if stream_sock is not None:
            stream_sock.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)

    events = [line for line in marker.read_text().splitlines() if line.strip()]
    joined = "\n".join(events)
    assert "startup_complete" in joined, f"probe never started: {joined}"
    assert "lifespan_shutdown_entered" in joined, (
        "SIGTERM exited the process but the lifespan shutdown half never ran — the "
        f"Concierge drain, pump teardown and close_checkpointer() are all unreachable. "
        f"Markers: {joined}"
    )
    assert "shutdown_body_completed" in joined, (
        f"the lifespan shutdown body was entered but did not run to completion: {joined}"
    )
    assert elapsed < graceful + 20.0


# ════════════════════════════════════════════════════════════════════════════
# 2. The production launch flag must not silently regress
# ════════════════════════════════════════════════════════════════════════════
def test_docker_entrypoint_still_passes_timeout_graceful_shutdown():
    assert "--timeout-graceful-shutdown" in DOCKER_ENTRYPOINT.read_text()
    assert _uvicorn_graceful_window_seconds() > 0


# ════════════════════════════════════════════════════════════════════════════
# 3. Budget arithmetic — the teardown must finish before docker SIGKILLs
# ════════════════════════════════════════════════════════════════════════════
def _teardown_budget_seconds(*, stop_runs: bool) -> float:
    """Worst-case wall time from SIGTERM to process exit.

    Every wait on the path, in order:
      uvicorn graceful window        docker-entrypoint.sh
      Concierge drain                run_shutdown.py:101-103
      Concierge cancel-and-wait      run_shutdown.py:124
      pump drain                     run_shutdown.py:161-163
      pump cancel-and-wait           run_shutdown.py:174-176
      [stop-runs] driver drain       run_shutdown.py:233-235   (only when SHUTDOWN_STOP_RUNS)
      [stop-runs] driver escalation  run_shutdown.py:247-249   (only when SHUTDOWN_STOP_RUNS)
    """
    from app.core.config import settings

    concierge = settings.SHUTDOWN_CONCIERGE_DRAIN_SECONDS
    task = settings.SHUTDOWN_TASK_DRAIN_SECONDS
    total = _uvicorn_graceful_window_seconds() + concierge + task + task + task
    if stop_runs:
        total += 2 * task
    return total


def test_production_teardown_budget_fits_inside_stop_grace_period():
    """The production configuration must finish teardown before docker SIGKILLs it."""
    grace = _stop_grace_period_seconds()
    budget = _teardown_budget_seconds(stop_runs=False)
    assert budget < grace, (
        f"worst-case teardown is {budget}s against a {grace}s stop_grace_period — docker "
        "would SIGKILL mid-teardown, leaving some runs cancelled, some non-terminal and "
        "no shutdown summary logged."
    )


def test_production_leaves_shutdown_stop_runs_off():
    """The budget above only holds because production does not stop runs on shutdown.

    Turning it on adds a drain plus an escalation and reaches the SIGKILL line, so this
    pins the production default rather than trusting a prose comment.
    """
    from app.core.config import Settings

    prod = Settings(
        _env_file=None,
        ENV="production",
        SECRET_KEY="p" * 64,
    )
    assert prod.SHUTDOWN_STOP_RUNS is False

    grace = _stop_grace_period_seconds()
    assert _teardown_budget_seconds(stop_runs=True) >= grace, (
        "stop-runs no longer reaches the SIGKILL line — the drain budgets changed, so the "
        "reason production keeps it off needs re-deriving (and this test updating)."
    )


def test_development_defaults_shutdown_stop_runs_on(monkeypatch):
    """A developer restarting the backend to stop an expensive run expects it to stop."""
    from app.core.config import Settings

    monkeypatch.delenv("SHUTDOWN_STOP_RUNS", raising=False)
    dev = Settings(_env_file=None, ENV="development")
    assert dev.SHUTDOWN_STOP_RUNS is True


@pytest.mark.parametrize("env_name,explicit,expected", [
    ("development", "false", False),
    ("production", "true", True),
])
def test_explicit_shutdown_stop_runs_always_wins(env_name, explicit, expected):
    """The env-differentiated default must never override an operator's explicit value."""
    from app.core.config import Settings

    settings_obj = Settings(
        _env_file=None,
        ENV=env_name,
        SECRET_KEY="p" * 64,
        SHUTDOWN_STOP_RUNS=explicit,
    )
    assert settings_obj.SHUTDOWN_STOP_RUNS is expected


# ════════════════════════════════════════════════════════════════════════════
# 4. close_checkpointer() is wired exactly ONCE on the shutdown path (INV-12)
# ════════════════════════════════════════════════════════════════════════════
def test_close_checkpointer_is_awaited_exactly_once_on_the_shutdown_path():
    """Two call sites made the documented ordering guarantee false.

    ``run_shutdown.py``'s module docstring promises ``close_checkpointer()`` runs "LAST
    among the awaits … Steps 1-3 may still hold a pooled connection, so this runs after
    them". ``main.py`` also closed the pool BEFORE ``shutdown_run_infrastructure()`` ran,
    so in practice it closed FIRST. It is idempotent, so nothing crashed — but with
    SHUTDOWN_STOP_RUNS on, ``stop_pipeline_drivers()`` would drive runs against a pool
    that is already closed (``get_checkpointer()`` raises after close).
    """
    main_src = (BACKEND_DIR / "app" / "main.py").read_text()
    shutdown_src = (BACKEND_DIR / "app" / "api" / "run_shutdown.py").read_text()

    main_calls = main_src.count("await close_checkpointer()")
    shutdown_calls = shutdown_src.count("await close_checkpointer()")

    assert main_calls == 0, (
        f"main.py awaits close_checkpointer() {main_calls} time(s). The single wiring "
        "site is run_shutdown.py step 4, which must run LAST among the awaits; closing "
        "from main.py runs it FIRST, before the Concierge and pump drains."
    )
    assert shutdown_calls == 1, (
        f"run_shutdown.py awaits close_checkpointer() {shutdown_calls} time(s); expected "
        "exactly 1 (step 4)."
    )
