"""tests/agents/test_stale_file_reconciliation_v3.py — FR-033 declarative
stale-file reconciliation (sandbox-git-versioning P0 #2).

A step MAY declare ``outputs: [...]`` (the surface it owns) and
``replaces: true`` (it owns that surface completely). When ``replaces`` is
truthy, the step-boundary commit removes every tracked path under the
declared ``outputs`` surface that THIS pass did not write — determined from
``changed_since(spawn_point)`` — so a leaner later pass sheds an earlier
pass's leftover file instead of silently accumulating it (requirements.md
§33/34, plan.py:522-537, compiler.py:1108-1116, engine.py
``_reconcile_replaces_surface`` + its step-boundary call site).

Both scenarios drive the REAL functions against a real git repo under
``tmp_path`` — no mocks for the git layer — exactly the way the step-boundary
dispatch loop pairs them (``_reconcile_replaces_surface`` immediately before
``commit_in_sandbox``).
"""

from __future__ import annotations

import subprocess
import types
import uuid
from pathlib import Path

import pytest

from agents.workflows.plan import Step

BACKEND_ROOT = Path(__file__).parent.parent.parent  # …/backend/


# ---------------------------------------------------------------------------
# Helpers (mirrors tests/agents/test_commit_primitive.py)
# ---------------------------------------------------------------------------


def _run_id() -> str:
    return f"reconcile-test-{uuid.uuid4().hex[:8]}"


def _make_sandbox(tmp_path: Path, *, run_id: str | None = None):
    """Create and provision a RunSandbox with a real git repo under tmp_path."""
    from app.agents.sandbox import RunSandbox

    rid = run_id or _run_id()
    sb = RunSandbox("test-user", rid, runs_root=str(tmp_path), has_git=True)
    sb.ensure()
    sb._ws().git_init_sandbox()  # type: ignore[attr-defined]
    return sb


def _make_ectx(run_id: str | None = None):
    from agents.execution_engine.context import ExecutionContext

    return ExecutionContext(
        run_id=run_id or _run_id(),
        owner_id="test-user",
    )


def _git(cwd: Path, *args: str) -> str:
    """Run a git command in *cwd* and return stdout. Raises on failure."""
    result = subprocess.run(
        [
            "git",
            "-c", "user.name=Flowin Test",
            "-c", "user.email=test@flowin.local",
            "-c", "commit.gpgsign=false",
            *args,
        ],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


async def _step_boundary_commit(sandbox, ectx, step, message: str):
    """Reproduce the engine's step-boundary pairing (engine.py call site):
    reconcile FIRST, then commit — so a removal lands in the same commit.
    """
    from agents.execution_engine.engine import _reconcile_replaces_surface, commit_in_sandbox

    _reconcile_replaces_surface(sandbox, step)
    return await commit_in_sandbox(sandbox, message, ectx, step, audit_operation=None)


# ---------------------------------------------------------------------------
# Test 1 — replaces: true removes a stale file the second pass did not write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replaces_true_removes_stale_file_second_pass(tmp_path: Path) -> None:
    """Two passes of one step declaring ``replaces: true``: pass 2 writes only
    one of the two files pass 1 wrote. After pass 2's commit, the file pass 2
    did not rewrite must be gone from the working tree AND from
    ``git ls-files`` — not merely uncommitted.
    """
    sb = _make_sandbox(tmp_path)
    ectx = _make_ectx()
    step = Step(agent_id="reconciler", outputs=["out/"], replaces=True)

    out_dir = sb.root / "out"
    out_dir.mkdir()

    # ── Pass 1: writes a.txt and b.txt ────────────────────────────────────
    (out_dir / "a.txt").write_text("pass 1 a\n", encoding="utf-8")
    (out_dir / "b.txt").write_text("pass 1 b\n", encoding="utf-8")
    result1 = await _step_boundary_commit(sb, ectx, step, "step: reconciler (pass 1)")
    assert result1.sha, "pass 1 must produce a commit"

    tracked_after_pass1 = _git(sb.root, "ls-files", "out/").splitlines()
    assert sorted(tracked_after_pass1) == ["out/a.txt", "out/b.txt"]

    # ── Pass 2: rewrites a.txt only — b.txt is NOT touched this pass ──────
    (out_dir / "a.txt").write_text("pass 2 a (changed)\n", encoding="utf-8")
    result2 = await _step_boundary_commit(sb, ectx, step, "step: reconciler (pass 2)")
    assert result2.sha, "pass 2 must produce a commit (a.txt changed + b.txt removed)"
    assert result2.blocked is False

    # b.txt must be gone from the working tree...
    assert not (out_dir / "b.txt").exists(), "stale b.txt must be removed from the tree"
    # ...and from git's tracked-file list.
    tracked_after_pass2 = _git(sb.root, "ls-files", "out/").splitlines()
    assert tracked_after_pass2 == ["out/a.txt"], (
        f"stale out/b.txt must be gone from git ls-files, got {tracked_after_pass2!r}"
    )
    # a.txt (written this pass) must survive with its new content.
    assert (out_dir / "a.txt").read_text(encoding="utf-8") == "pass 2 a (changed)\n"

    # The removal must be part of pass 2's own commit, not a separate one.
    log = _git(sb.root, "log", "--oneline").splitlines()
    assert len(log) == 3, f"expected init + pass1 + pass2 commits, got {log!r}"
    stat = _git(sb.root, "show", "--stat", "HEAD")
    assert "b.txt" in stat, "the removal of b.txt must appear in pass 2's own commit"


# ---------------------------------------------------------------------------
# Test 2 — a step without replaces (default False) keeps the stale file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replaces_false_keeps_stale_file(tmp_path: Path) -> None:
    """The same two-pass shape, but the step never declares ``replaces: true``
    (the dataclass default, ``False``). b.txt must survive untouched — no
    reconciliation runs at all for a step that did not opt in (INV-3 parity).
    """
    sb = _make_sandbox(tmp_path)
    ectx = _make_ectx()
    step = Step(agent_id="accumulator", outputs=["out/"])  # replaces defaults to False
    assert step.replaces is False

    out_dir = sb.root / "out"
    out_dir.mkdir()

    (out_dir / "a.txt").write_text("pass 1 a\n", encoding="utf-8")
    (out_dir / "b.txt").write_text("pass 1 b\n", encoding="utf-8")
    result1 = await _step_boundary_commit(sb, ectx, step, "step: accumulator (pass 1)")
    assert result1.sha

    (out_dir / "a.txt").write_text("pass 2 a (changed)\n", encoding="utf-8")
    result2 = await _step_boundary_commit(sb, ectx, step, "step: accumulator (pass 2)")
    assert result2.sha

    # b.txt must still be present — no reconciliation for a non-replaces step.
    assert (out_dir / "b.txt").exists(), "b.txt must survive when replaces is False"
    tracked = _git(sb.root, "ls-files", "out/").splitlines()
    assert sorted(tracked) == ["out/a.txt", "out/b.txt"]
