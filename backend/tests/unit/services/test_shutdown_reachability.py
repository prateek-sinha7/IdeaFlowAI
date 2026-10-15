"""tests/unit/services/test_shutdown_reachability.py — ISS-088.

``tests/unit/app/test_run_shutdown.py`` covers the *body* of
``shutdown_run_infrastructure()``. Nothing covered whether that body is ever REACHED,
and that is exactly what broke: uvicorn's ``timeout_graceful_shutdown`` defaults to
``None``, and ``H11Protocol.shutdown()`` does NOT close a connection whose response is
still streaming — it only clears keep_alive. A live ``EventSourceResponse`` therefore
never leaves ``server_state.connections``, ``_wait_tasks_to_complete()`` spins forever,
and ``await self.lifespan.shutdown()``, the last statement of ``uvicorn.Server.shutdown``,
is never reached. Measured before the fix: SIGTERM left the process alive past 30s
with only ``startup_complete`` written; SIGKILL was the only thing that ended it.

These tests pin the four things that keep that path honest:

  1. a real uvicorn SUBPROCESS, a live SSE stream and a real SIGTERM actually reach the
     lifespan shutdown half (the test that would have caught the defect);
  2. ``docker-entrypoint.sh`` still passes the flag that makes (1) true in production;
  3. the teardown budget still fits inside docker's ``stop_grace_period``;
  4. ``close_checkpointer()`` is wired exactly ONCE on the shutdown path.

(1) must be a subprocess, not the in-process ``uvicorn.Server`` that
``tests/unit/app/test_run_stream_pool_leak.py`` starts in
``test_stream_endpoint_returns_connections``: ``Server.capture_signals()`` installs its
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


def _stop_grace_period_seconds() -> float:
    """docker's hard SIGKILL ceiling for the backend service."""
    text = DOCKER_COMPOSE.read_text(encoding="utf-8")
    match = re.search(r"stop_grace_period:\s*(\d+(?:\.\d+)?)s", text)
    assert (
        match
    ), "docker-compose.yml no longer declares stop_grace_period for the backend."
    return float(match.group(1))


# ════════════════════════════════════════════════════════════════════════════
# 1. Reachability — moved to tests/integration/external/
#    test_shutdown_reachability_external.py (it spawns a uvicorn subprocess, so it
#    belongs under the integration external suite, README rule 8).
# ════════════════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════════════════
# 2. The production launch flag must not silently regress
# ════════════════════════════════════════════════════════════════════════════
def test_docker_entrypoint_still_passes_timeout_graceful_shutdown():
    assert "--timeout-graceful-shutdown" in DOCKER_ENTRYPOINT.read_text(
        encoding="utf-8"
    )
    assert _uvicorn_graceful_window_seconds() > 0


# ════════════════════════════════════════════════════════════════════════════
# 3. Budget arithmetic — the teardown must finish before docker SIGKILLs
# ════════════════════════════════════════════════════════════════════════════
def _teardown_budget_seconds(*, stop_runs: bool) -> float:
    """Worst-case wall time from SIGTERM to process exit.

    Every wait on the path, in order:
      uvicorn graceful window        docker-entrypoint.sh
      Concierge drain                run_shutdown.py step 1
      Concierge cancel-and-wait      run_shutdown.py step 1 escalation
      pump drain                     run_shutdown.py step 2b
      pump cancel-and-wait           run_shutdown.py step 2b escalation
      [stop-runs] driver drain       _drain_then_cancel first wait    (only when SHUTDOWN_STOP_RUNS)
      [stop-runs] driver escalation  _drain_then_cancel second wait   (only when SHUTDOWN_STOP_RUNS)
      checkpointer pool close        close_checkpointer's wait_for    (ISS-106)

    Every wait on the path is bounded, so this really is the worst case: ISS-106 wrapped
    step 4's pool.close() in asyncio.wait_for(SHUTDOWN_CHECKPOINTER_CLOSE_SECONDS), which
    was previously untimeouted and invisible to this arithmetic.
    """
    from app.core.config import settings

    concierge = settings.SHUTDOWN_CONCIERGE_DRAIN_SECONDS
    task = settings.SHUTDOWN_TASK_DRAIN_SECONDS
    checkpointer_close = settings.SHUTDOWN_CHECKPOINTER_CLOSE_SECONDS
    total = (
        _uvicorn_graceful_window_seconds()
        + concierge
        + task
        + task
        + task
        + checkpointer_close
    )
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
        # Cognito-only auth migration (.kiro/specs/login/prompt.md Phase 1):
        # _validate_cognito_config is unconditional outside development, so
        # constructing a "production" Settings without these three now
        # raises CognitoMisconfigured before SHUTDOWN_STOP_RUNS is ever
        # reached -- unrelated to what this test actually pins, but a
        # precondition of building Settings("production", ...) at all.
        COGNITO_USER_POOL_ID="eu-central-1_testpool",
        COGNITO_CLIENT_ID="test-client-id",
        COGNITO_CLIENT_SECRET="test-client-secret",
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


@pytest.mark.parametrize(
    "env_name,explicit,expected",
    [
        ("development", "false", False),
        ("production", "true", True),
    ],
)
def test_explicit_shutdown_stop_runs_always_wins(env_name, explicit, expected):
    """The env-differentiated default must never override an operator's explicit value."""
    from app.core.config import Settings

    # See the comment on test_production_leaves_shutdown_stop_runs_off: any
    # non-development ENV now requires the Cognito trio to construct Settings
    # at all (Cognito-only auth migration Phase 1). Harmless for the
    # "development" parametrization, which never reaches that check.
    cognito_kwargs = (
        {}
        if env_name == "development"
        else {
            "COGNITO_USER_POOL_ID": "eu-central-1_testpool",
            "COGNITO_CLIENT_ID": "test-client-id",
            "COGNITO_CLIENT_SECRET": "test-client-secret",
        }
    )

    settings_obj = Settings(
        _env_file=None,
        ENV=env_name,
        SECRET_KEY="p" * 64,
        SHUTDOWN_STOP_RUNS=explicit,
        **cognito_kwargs,
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
    main_src = (BACKEND_DIR / "app" / "main.py").read_text(encoding="utf-8")
    shutdown_src = (BACKEND_DIR / "app" / "api" / "run_shutdown.py").read_text(
        encoding="utf-8"
    )

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
