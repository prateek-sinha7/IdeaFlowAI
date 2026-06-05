"""tests/agents/test_phase8_resume.py — Phase-8 cross-process resume-after-kill.

The durability proof for the deepagents migration's Postgres checkpointer: a
LangGraph HITL interrupt persisted by ``AsyncPostgresSaver`` SURVIVES a real OS
process boundary (and a hard ``SIGKILL`` crash), so a FRESH process can resume the
paused run to completion. This is the one guarantee ``InMemorySaver`` structurally
cannot give — and the negative contrast in this file proves the test actually
exercises durability rather than a no-op.

WHY THIS IS AT THE RUNNER-GRAPH LEVEL (the critical design fact)
---------------------------------------------------------------
There are TWO HITL gate mechanisms in this system and only ONE is
checkpoint-durable (from the Phase-8 T1 survey):

  * The engine's inter-agent **"review gate"** (``review_gate_ready``) is NOT a
    LangGraph interrupt — the engine pauses by awaiting an in-memory
    ``asyncio.Event`` (``ArtifactStore.get_review_event(gate_key).wait()``). That
    is in-process only and CANNOT survive a process kill. It is deliberately NOT
    used here.
  * The **runner tool-level gate** — a ``DeepAgentRunner`` built with
    ``interrupt_on=[...]`` — IS a real LangGraph interrupt whose state the
    checkpointer persists. A Postgres checkpointer makes THAT durable across
    processes. This test drives exactly that mechanism (via the production
    ``create_runner`` → ``DeepAgentRunner`` → ``create_deep_agent`` graph + the
    production ``get_checkpointer`` factory + a stable ``thread_id``).

HOW THE CROSS-PROCESS KILL+RESUME IS STRUCTURED
-----------------------------------------------
A docker Postgres fixture (:func:`postgres_url`) starts ``postgres:16`` on a free
port, waits for readiness, yields the ``DATABASE_URL``, and ``docker rm -f``s it on
teardown (``pytest.skip`` if docker is unavailable). The proof is two SEPARATE OS
processes of :mod:`tests.agents._resume_child` (``subprocess.run`` — a real process
boundary, no shared memory):

  1. **Process A** (``--phase run-until-interrupt``) builds the runner with the
     Postgres checkpointer + the gated tool in ``interrupt_on`` + a stable
     ``thread_id``, drives it with a SCRIPTED model until the interrupt fires and
     the pause is committed to Postgres, prints ``INTERRUPTED <thread_id>`` and
     exits. (The test ALSO runs an explicit self-``SIGKILL`` variant to prove the
     write was durable even under a crash with no graceful teardown.)
  2. **Process B** (``--phase resume``, a fresh process; A is fully gone)
     reconstructs the runner with the SAME ``thread_id`` + the Postgres
     checkpointer, issues ``Command(resume={"decisions":[{"type":"approve"}]})``,
     runs to a terminal state, asserts the gated tool actually executed, and prints
     ``RESUMED_COMPLETE``.

THE NEGATIVE CONTRAST (proves the test isn't a no-op)
-----------------------------------------------------
:func:`test_inmemory_cross_process_resume_FAILS` runs the EXACT same two-process
flow with ``DATABASE_URL=sqlite:///...`` → the production factory returns
``InMemorySaver``. Process A still interrupts (in-process), but Process B starts
with an empty saver, so it does NOT see the pause and does NOT reach
``RESUMED_COMPLETE`` (the child reports ``RESUME_FAILED`` / exit 3). Postgres
resumes across the boundary; InMemory cannot — that delta IS the durability.

COST / DETERMINISM
------------------
Every run uses ``ScriptedFakeChatModel`` → **zero Bedrock cost**, fully
deterministic (no AWS, no network beyond the local docker Postgres).

VERIFY-ONLY: this file + ``_resume_child.py`` are the only new code; nothing under
``app/`` or ``agents/`` is modified.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

# The child subprocess entry point + the marker strings it prints. Kept in sync
# with ``_resume_child.py`` (the markers are this test's machine-readable contract).
_CHILD = Path(__file__).resolve().parent / "_resume_child.py"
_BACKEND_ROOT = Path(__file__).resolve().parents[2]

MARK_INTERRUPTED = "INTERRUPTED"
MARK_RESUMED = "RESUMED_COMPLETE"
MARK_RESUME_FAILED = "RESUME_FAILED"
MARK_CHECKPOINTER = "CHECKPOINTER"

# Generous but bounded subprocess timeout: graph construction + a scripted drive +
# (for resume) a Postgres round-trip. CI-safe; a hang fails fast rather than
# blocking the suite.
_CHILD_TIMEOUT_S = 180

# Docker image + readiness budget for the throwaway Postgres.
_PG_IMAGE = "postgres:16"
_PG_READY_TIMEOUT_S = 90


# ===========================================================================
# Docker availability + a free-port helper.
# ===========================================================================


def _docker_available() -> bool:
    """True iff the ``docker`` CLI is on PATH and the daemon answers ``docker info``."""
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=20,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _free_port() -> int:
    """Bind ``127.0.0.1:0`` to let the OS pick a free TCP port, then release it.

    A small TOCTOU window exists between releasing the port and docker binding it,
    but the port space is large and the fixture runs serially — acceptable for a
    local/CI durability test.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _wait_for_postgres(dsn: str, timeout_s: int) -> None:
    """Block until a psycopg connection to ``dsn`` succeeds, or raise on timeout.

    Polls ``SELECT 1`` once a second — the standard "is Postgres accepting
    connections yet" probe (the container is up before the server is ready).
    """
    import psycopg

    deadline = time.time() + timeout_s
    last_exc: Exception | None = None
    while time.time() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return
        except Exception as exc:  # not-ready: connection refused / starting up
            last_exc = exc
            time.sleep(1.0)
    raise TimeoutError(
        f"Postgres at {dsn} did not become ready within {timeout_s}s; "
        f"last error: {type(last_exc).__name__}: {last_exc}"
    )


# ===========================================================================
# The docker Postgres fixture — yields a DATABASE_URL, force-removes on teardown.
# ===========================================================================


@pytest.fixture(scope="module")
def postgres_url():
    """Start ``postgres:16`` on a free port; yield its ``DATABASE_URL``; rm -f after.

    ``pytest.skip`` if docker is unavailable, so the suite is safe on a box without
    docker. Module-scoped: one container serves both the positive and (cheap)
    contrast tests — each test uses unique ``thread_id``/``run_id`` so they never
    collide on a checkpoint row.
    """
    if not _docker_available():
        pytest.skip("docker is not available — skipping cross-process Postgres resume test.")

    port = _free_port()
    name = f"flowin-phase8-pg-{uuid.uuid4().hex[:8]}"
    run = subprocess.run(
        [
            "docker", "run", "-d",
            "--name", name,
            "-p", f"{port}:5432",
            "-e", "POSTGRES_PASSWORD=postgres",
            _PG_IMAGE,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if run.returncode != 0:
        pytest.skip(
            f"could not start docker Postgres ({_PG_IMAGE}): {run.stderr.strip() or run.stdout.strip()}"
        )
    container_id = run.stdout.strip()

    dsn = f"postgresql://postgres:postgres@127.0.0.1:{port}/postgres"
    try:
        _wait_for_postgres(dsn, _PG_READY_TIMEOUT_S)
        yield dsn
    finally:
        # Force-remove the container (kills + deletes) so nothing leaks even if a
        # test failed mid-way. Best-effort: a teardown error must not mask a test
        # failure.
        subprocess.run(
            ["docker", "rm", "-f", container_id or name],
            capture_output=True,
            timeout=60,
        )


# ===========================================================================
# Subprocess driver.
# ===========================================================================


def _run_child(phase: str, thread_id: str, run_id: str, database_url: str, *, kill: bool = False):
    """Run ``_resume_child.py`` as a REAL subprocess and return the CompletedProcess.

    The child is a separate OS process with ``DATABASE_URL`` (+ ``ENV``) injected
    via the environment — exactly how the production ``settings`` singleton (and so
    ``get_checkpointer``'s provider choice) reads them on import. ``PYTHONPATH`` is
    set to the backend root so ``import app.*`` / ``import tests.*`` resolve when the
    child is launched as a bare path.
    """
    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    env["ENV"] = "development"
    # Ensure the backend root is importable in the child (it inserts this itself,
    # but PYTHONPATH makes ``tests.agents._scripted_model`` resolve cleanly too).
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{_BACKEND_ROOT}{os.pathsep}{existing_pp}" if existing_pp else str(_BACKEND_ROOT)
    )
    # A writable RUNS_ROOT for the child's RunSandbox (the real /app/runs is absent).
    env.setdefault("RUNS_ROOT", str(Path(env.get("TMPDIR", "/tmp")) / "phase8-resume-runs"))

    cmd = [
        sys.executable,
        str(_CHILD),
        "--phase", phase,
        "--thread-id", thread_id,
        "--run-id", run_id,
    ]
    if kill:
        cmd.append("--kill-after-interrupt")

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        timeout=_CHILD_TIMEOUT_S,
    )


def _dump(label: str, proc: subprocess.CompletedProcess) -> str:
    """Compact, copy-pasteable rendering of a child run (for assertion messages)."""
    return (
        f"\n--- {label} (exit={proc.returncode}) ---\n"
        f"STDOUT:\n{proc.stdout}\n"
        f"STDERR (tail):\n{proc.stderr[-1500:]}\n"
        f"--- end {label} ---\n"
    )


# ===========================================================================
# Sanity guard — the child must import & be runnable at all (fails loudly if a
# refactor breaks the entry point, independent of docker).
# ===========================================================================


def test_child_entry_point_exists() -> None:
    """The subprocess entry point exists and exposes its CLI (``--help`` exits 0).

    A fast, docker-free guard: if ``_resume_child.py`` fails to import (e.g. a
    broken sys.path bootstrap or an import error), this catches it before the
    heavier docker tests, with the traceback in the message.
    """
    assert _CHILD.is_file(), f"missing subprocess child: {_CHILD}"
    proc = subprocess.run(
        [sys.executable, str(_CHILD), "--help"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(_BACKEND_ROOT)},
        timeout=60,
    )
    assert proc.returncode == 0, f"child --help failed: {_dump('child --help', proc)}"
    assert "run-until-interrupt" in proc.stdout and "resume" in proc.stdout


# ===========================================================================
# THE PROOF — Postgres resumes across a real process boundary (and a crash).
# ===========================================================================


class TestCrossProcessResumeAfterKill:
    """Postgres checkpointer survives a process kill → fresh process resumes."""

    @pytest.mark.parametrize(
        "kill",
        [
            pytest.param(False, id="cleanexit-then-resume"),
            pytest.param(True, id="SIGKILL-crash-then-resume"),
        ],
    )
    def test_postgres_cross_process_resume(self, postgres_url: str, kill: bool) -> None:
        """Process A persists a HITL pause to Postgres; a FRESH Process B resumes it.

        Two parametrizations of the SAME proof:
          * ``cleanexit-then-resume`` — A drives to the gate and exits 0 (the
            graceful producer); B (fresh process) resumes from the Postgres row.
          * ``SIGKILL-crash-then-resume`` — A hard-``SIGKILL``s itself the instant
            the gate fires (a crash with NO pool flush / NO graceful teardown,
            exit 137); B still resumes — proving the write was durably committed to
            Postgres before the crash, not merely buffered in the producer.

        Asserts: A interrupted (``INTERRUPTED`` marker; on the kill variant the OS
        exit code is 137 = SIGKILL); B chose the ``AsyncPostgresSaver``, SAW the
        persisted pause, reached ``RESUMED_COMPLETE`` (exit 0), and the gated tool
        executed in the resumed graph. This is the cross-process resume-after-kill
        proof against real Postgres.
        """
        # Unique ids per parametrization so the two runs never share a checkpoint
        # row (the container is module-scoped / reused).
        suffix = uuid.uuid4().hex[:8]
        thread_id = f"t-pg-{'kill' if kill else 'clean'}-{suffix}"
        run_id = f"r-pg-{'kill' if kill else 'clean'}-{suffix}"

        # ── Process A: drive to the interrupt, persisting it to Postgres. ──────
        a = _run_child("run-until-interrupt", thread_id, run_id, postgres_url, kill=kill)

        # A must have reached the gate and announced it (before any self-kill).
        assert f"{MARK_INTERRUPTED} {thread_id}" in a.stdout, (
            "Process A must drive to the HITL gate and print the INTERRUPTED marker "
            f"(the pause is then persisted to Postgres).{_dump('process A', a)}"
        )
        # A must have used the real Postgres saver (not a silent InMemory fallback).
        assert f"{MARK_CHECKPOINTER} AsyncPostgresSaver" in a.stdout, (
            "Process A must use the production AsyncPostgresSaver for a Postgres "
            f"DATABASE_URL.{_dump('process A', a)}"
        )
        if kill:
            # A real hard crash: SIGKILL → exit code 137 (128 + SIGKILL(9)).
            assert a.returncode == -signal_or_137(), (
                "the --kill-after-interrupt producer must die by SIGKILL "
                f"(exit 137 / -9), proving no graceful teardown ran.{_dump('process A', a)}"
            )
        else:
            assert a.returncode == 0, (
                f"the clean producer must exit 0 after pausing.{_dump('process A', a)}"
            )

        # ── Process B: a FRESH process resumes from the Postgres checkpoint. ───
        b = _run_child("resume", thread_id, run_id, postgres_url)

        assert b.returncode == 0, (
            "Process B (fresh process) must resume the persisted pause to completion "
            f"and exit 0.{_dump('process B', b)}"
        )
        assert f"{MARK_CHECKPOINTER} AsyncPostgresSaver" in b.stdout, (
            f"Process B must also use the AsyncPostgresSaver.{_dump('process B', b)}"
        )
        # The fresh process SAW the persisted pause (the durability signal).
        assert "PRE_RESUME_STATE next=['HumanInTheLoopMiddleware.after_model']" in b.stdout, (
            "the fresh process must SEE the persisted HITL pause read back from "
            f"Postgres (a non-empty `next`).{_dump('process B', b)}"
        )
        # …and ran to completion with the gated tool executed.
        assert f"{MARK_RESUMED} {thread_id}" in b.stdout, (
            "Process B must reach a terminal state with the gated tool executed "
            f"(RESUMED_COMPLETE).{_dump('process B', b)}"
        )
        # Proof the REAL gated tool body ran (production report_task_complete returns
        # a "✓ Task N complete: …" string) — not a synthetic respond/reject message.
        assert "GATED_TOOL_RESULT" in b.stdout and "Task 1 complete" in b.stdout, (
            "the approved gated tool's real body must have executed on resume "
            f"(its ToolMessage content is echoed as GATED_TOOL_RESULT).{_dump('process B', b)}"
        )

    # -----------------------------------------------------------------------
    # NEGATIVE CONTRAST — InMemory cannot cross the process boundary.
    # -----------------------------------------------------------------------

    def test_inmemory_cross_process_resume_FAILS(self) -> None:
        """Contrast: with InMemory saver, a fresh process CANNOT resume the pause.

        Runs the IDENTICAL two-process flow but with ``DATABASE_URL=sqlite:///…``
        so the production factory returns ``InMemorySaver``. Process A still
        interrupts (in-process), but Process B starts with an empty saver — the
        pause never crossed the process boundary — so it does NOT reach
        ``RESUMED_COMPLETE`` and reports ``RESUME_FAILED`` (exit 3).

        This is the control that proves the Postgres test above is exercising real
        DURABILITY: same code path, same scripted model, same markers — the ONLY
        difference is the checkpointer provider, and only Postgres resumes across
        the boundary. Requires NO docker (sqlite → InMemory).
        """
        suffix = uuid.uuid4().hex[:8]
        thread_id = f"t-mem-{suffix}"
        run_id = f"r-mem-{suffix}"
        sqlite_url = "sqlite:///./dev.db"  # → _is_postgres() False → InMemorySaver

        # Process A: interrupts in-process (the InMemory pause lives in A's heap).
        a = _run_child("run-until-interrupt", thread_id, run_id, sqlite_url)
        assert a.returncode == 0, f"InMemory Process A should pause cleanly.{_dump('process A', a)}"
        assert f"{MARK_CHECKPOINTER} InMemorySaver" in a.stdout, (
            "a non-Postgres DATABASE_URL must select InMemorySaver (the dev path)."
            f"{_dump('process A', a)}"
        )
        assert f"{MARK_INTERRUPTED} {thread_id}" in a.stdout, (
            f"InMemory Process A still interrupts within its own process.{_dump('process A', a)}"
        )

        # Process B: a fresh process with a brand-new (empty) InMemory saver.
        b = _run_child("resume", thread_id, run_id, sqlite_url)

        # The core negative assertion: B did NOT resume to completion.
        assert f"{MARK_RESUMED}" not in b.stdout, (
            "REGRESSION: an InMemory checkpoint must NOT be resumable from a fresh "
            "process — if this resumed, the test is no longer proving durability."
            f"{_dump('process B', b)}"
        )
        # And it reported the expected, well-defined failure (no persisted pause).
        assert f"{MARK_RESUME_FAILED}" in b.stdout and b.returncode == 3, (
            "InMemory fresh-process resume must report RESUME_FAILED (exit 3) — the "
            f"pause did not cross the process boundary.{_dump('process B', b)}"
        )
        # Concretely: the fresh process saw NO pending pause (empty `next`).
        assert "PRE_RESUME_STATE next=[] interrupts=False" in b.stdout, (
            "the fresh InMemory process must see an EMPTY state for the thread "
            f"(no `next`, no interrupts) — nothing was persisted.{_dump('process B', b)}"
        )


def signal_or_137() -> int:
    """Return the SIGKILL number (9) so ``-signal_or_137()`` is the POSIX exit code.

    ``subprocess`` reports a signal-terminated child's ``returncode`` as the
    NEGATIVE signal number (``-9`` for SIGKILL). We compare against ``-9`` (which
    surfaces in shells as exit 137 = 128 + 9). Wrapped in a tiny helper purely so
    the assertion reads ``a.returncode == -signal_or_137()`` with an explanatory name.
    """
    import signal as _signal

    return int(_signal.SIGKILL)
