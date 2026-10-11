"""tests/agents/test_merge_worktree_acceptance.py — ship-blocker acceptance tests
for the fixed merge_worktree + git_3way inter-fragment commit (task 1.3).

These are integration-level tests that operate a REAL git repository on disk
(via tmp_path) — no mocks, no fakes for the git layer.

Two invariants asserted here:

  1. Two fan-out workers writing DISJOINT files both survive in the base tree
     after the full merge sequence.  Before the fix (FR-034 / Requirement 7),
     the second ``git merge`` was REFUSED because MERGE_HEAD was still set from
     the first fragment; ``git merge --abort`` silently destroyed the first
     fragment's work, leaving NEITHER file in the base.

  2. A refused merge (git refuses to START, e.g. dirty index) is reported as
     ``MergeRefusedError``, NEVER as ``{"conflicts": []}``.  The false-clean-merge
     defect was: a ``CalledProcessError`` with empty ``--diff-filter=U`` output was
     treated as a clean merge.

Requirements: 7, 25
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.runtime.local import (
    LocalExecutionPolicy,
    LocalSandboxRuntime,
    LocalWorkspace,
    MergeRefusedError,
)
from app.agents.sandbox import RunSandbox


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    """Run a git command in ``cwd`` and return stdout.  Raises on failure."""
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Flowin Test",
            "-c",
            "user.email=test@flowin.local",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "init.defaultBranch=main",
            *args,
        ],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _make_workspace(tmp_path: Path, *, run_id: str = "run-test") -> LocalWorkspace:
    """Provision a LocalWorkspace rooted under a tmp dir."""
    import app.core.config as config_module

    config_module.settings.RUNS_ROOT = str(tmp_path / "runs")
    sandbox = RunSandbox("anon", run_id, runs_root=config_module.settings.RUNS_ROOT)
    sandbox.ensure()

    policy = LocalExecutionPolicy(exec=False, network=False, secrets=[])
    runtime = LocalSandboxRuntime()
    ws = LocalWorkspace(
        owner_id="anon",
        workspace_id=run_id,
        runtime=runtime,
        policy=policy,
        sandbox=sandbox,
        has_git=True,
    )
    return ws


def _init_git_repo(ws: LocalWorkspace) -> None:
    """Initialise a real git repo in ``ws._root`` with an initial commit.

    Mirrors task 2.1: ``git init`` + initial commit so worktree allocation
    and spawn-point capture work (no unborn-HEAD edge).
    """
    root = ws._root
    _git(root, "init")
    (root / ".gitignore").write_text("# placeholder\n", encoding="utf-8")
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-m", "initial commit")


# ---------------------------------------------------------------------------
# Acceptance test 1 — disjoint fan-out workers both survive the merge
# ---------------------------------------------------------------------------


def test_disjoint_workers_both_files_present_after_merge(tmp_path: Path) -> None:
    """Both fan-out workers' files appear in the base tree after the full merge.

    Before the fix (FR-034):
     - worker 0 merges cleanly via ``git merge --no-ff --no-commit``; MERGE_HEAD
       is set but NOT committed (``--no-commit`` flag leaves it staged).
     - worker 1's ``git merge`` is REFUSED (MERGE_HEAD still set from worker 0).
     - Without the classification fix (task 1.1): ``--diff-filter=U`` finds nothing
       (no conflict markers) so the code returned ``conflicts: []`` — a false-clean
       result — and then ran ``git merge --abort``, wiping worker 0's staged work.
     - Neither file survives.

    After the fix (tasks 1.1 + 1.2):
     - ``git_3way.merge()`` calls ``workspace.commit_all()`` after each clean
       fragment, clearing MERGE_HEAD before the next fragment starts.
     - ``merge_worktree`` raises ``MergeRefusedError`` (never ``conflicts: []``)
       when git refuses to start a merge.

    Requirement: 7, 25
    """
    ws = _make_workspace(tmp_path, run_id="run-fanout")
    _init_git_repo(ws)

    spawn = ws.spawn_point_commit()
    assert spawn, "spawn_point_commit must return a non-empty SHA after git init"

    # ── Worker 0: allocate worktree, write file, commit ─────────────────────
    wt0 = ws.allocate_worktree("build", 0)
    wt0.write_file("worker0.txt", "output from worker 0")
    wt0.commit_all("worker 0 output")
    branch0 = wt0._worktree_branch

    # ── Worker 1: allocate worktree, write a DIFFERENT file, commit ──────────
    wt1 = ws.allocate_worktree("build", 1)
    wt1.write_file("worker1.txt", "output from worker 1")
    wt1.commit_all("worker 1 output")
    branch1 = wt1._worktree_branch

    assert branch0 and branch1, "worktree branches must be set"

    # ── Merge fragment 0 ─────────────────────────────────────────────────────
    result0 = ws.merge_worktree(branch0, spawn)
    assert (
        result0["conflicts"] == []
    ), f"disjoint worker 0 must merge cleanly, got: {result0['conflicts']}"

    # The inter-fragment commit (task 1.2): clear MERGE_HEAD so fragment 1 can merge.
    ws.commit_all(f"merge: {branch0}")

    # ── Merge fragment 1 ─────────────────────────────────────────────────────
    # Before the fix this either returned conflicts: [] (false clean) or raised
    # due to the refused merge being misclassified, then --abort wiped fragment 0's work.
    result1 = ws.merge_worktree(branch1, spawn)
    assert (
        result1["conflicts"] == []
    ), f"disjoint worker 1 must merge cleanly, got: {result1['conflicts']}"

    # Commit the second merge so the working tree is fully clean.
    ws.commit_all(f"merge: {branch1}")

    # ── Assert BOTH files are present in the base working tree ───────────────
    base_root = ws._root
    assert (base_root / "worker0.txt").is_file(), (
        "worker0.txt missing — the first fragment's work was destroyed "
        "(false-clean-merge defect: merge --abort ran unconditionally)"
    )
    assert (base_root / "worker1.txt").is_file(), (
        "worker1.txt missing — the second fragment was never merged "
        "(refused merge was not detected)"
    )

    assert (base_root / "worker0.txt").read_text(
        encoding="utf-8"
    ) == "output from worker 0"
    assert (base_root / "worker1.txt").read_text(
        encoding="utf-8"
    ) == "output from worker 1"

    # Tear down worktrees (post-merge cleanup).
    ws.remove_worktree(wt0)
    ws.remove_worktree(wt1)


# ---------------------------------------------------------------------------
# Acceptance test 2 — refused merge raises MergeRefusedError, never conflicts: []
# ---------------------------------------------------------------------------


def test_refused_merge_raises_merge_refused_error_not_clean(tmp_path: Path) -> None:
    """A merge git refuses to START raises MergeRefusedError — NEVER ``conflicts: []``.

    The pre-fix path: CalledProcessError with no --diff-filter=U output was
    classified as a clean merge (conflicts: []), masking the real failure.

    We force a refusal by making the working tree dirty (an untracked file that
    would be overwritten by the merge) before calling merge_worktree.  Git
    refuses to start the merge with exit 128 and does NOT write MERGE_HEAD —
    the classification in the fixed merge_worktree checks for MERGE_HEAD presence
    and raises MergeRefusedError when it is absent.

    Requirement: 7
    """
    ws = _make_workspace(tmp_path, run_id="run-refused")
    _init_git_repo(ws)

    spawn = ws.spawn_point_commit()

    # ── Worker: writes a file and commits on a branch ────────────────────────
    wt = ws.allocate_worktree("s", 0)
    wt.write_file("conflict.txt", "from worker")
    wt.commit_all("worker writes conflict.txt")
    branch = wt._worktree_branch

    # ── Plant an untracked file in the base tree that git will refuse to clobber
    # when the merge tries to create it.  Git exits 128 WITHOUT writing MERGE_HEAD.
    (ws._root / "conflict.txt").write_text("dirty untracked content", encoding="utf-8")

    # Confirm MERGE_HEAD is absent (no in-progress merge).
    assert not (
        ws._root / ".git" / "MERGE_HEAD"
    ).exists(), "test setup error: MERGE_HEAD must not exist before the refused merge"

    # The fixed code: CalledProcessError + no MERGE_HEAD → MergeRefusedError.
    # The pre-fix code: CalledProcessError + empty --diff-filter=U → conflicts: [].
    with pytest.raises(MergeRefusedError) as exc_info:
        ws.merge_worktree(branch, spawn)

    err = exc_info.value
    assert (
        err.branch == branch
    ), f"MergeRefusedError.branch must be {branch!r}, got {err.branch!r}"
    assert branch in str(err), f"branch name missing from error str: {err}"


# ---------------------------------------------------------------------------
# Acceptance test 3 — Git3WayMerge strategy end-to-end with real worktrees
# ---------------------------------------------------------------------------


class _RealGitRunner:
    """A minimal runner shim that delegates git_3way_merge to ws.merge_worktree.

    The Git3WayMerge capability calls ``runner.git_3way_merge(branch, base)``
    via ``KernelServices.git_3way_merge``, which itself delegates to
    ``workspace.merge_worktree``.  For the acceptance test we wire this shim
    directly to the LocalWorkspace without needing KernelServices.
    """

    def __init__(self, workspace: LocalWorkspace) -> None:
        self._ws = workspace

    def git_3way_merge(self, branch: str, base_commit: str) -> dict:
        return self._ws.merge_worktree(branch, base_commit)


async def test_git_3way_strategy_disjoint_workers_via_real_git(tmp_path: Path) -> None:
    """Git3WayMerge.merge() produces a clean result with real git worktrees.

    This validates the full end-to-end path of the capability:
     - The strategy calls runner.git_3way_merge() for each fragment.
     - git_3way_merge delegates to LocalWorkspace.merge_worktree.
     - The inter-fragment commit_all (task 1.2) on base keeps MERGE_HEAD clear
       so the second fragment merges without refusal.
     - Both files land in the base working tree after the strategy runs.

    Requirement: 7, 25
    """
    from agents.capabilities.merge.git_3way import Git3WayMerge

    ws = _make_workspace(tmp_path, run_id="run-3way")
    _init_git_repo(ws)

    spawn = ws.spawn_point_commit()

    # Worker 0
    wt0 = ws.allocate_worktree("step", 0)
    wt0.write_file("alpha.txt", "alpha content")
    wt0.commit_all("worker 0")
    branch0 = wt0._worktree_branch

    # Worker 1
    wt1 = ws.allocate_worktree("step", 1)
    wt1.write_file("beta.txt", "beta content")
    wt1.commit_all("worker 1")
    branch1 = wt1._worktree_branch

    # The runner shim: routes git_3way_merge → ws.merge_worktree.
    runner = _RealGitRunner(ws)

    # Fragments shaped like the engine passes them (runner + branch + base_commit).
    frag0 = SimpleNamespace(runner=runner, branch=branch0, base_commit=spawn)
    frag1 = SimpleNamespace(runner=runner, branch=branch1, base_commit=spawn)

    strat = Git3WayMerge()
    # base=ws so commit_all is called between fragments (task 1.2 inter-fragment commit).
    result = await strat.merge(base=ws, fragments=[frag0, frag1])

    assert result.clean, f"expected clean merge of two disjoint workers, got conflicts: {result.conflicts}"
    assert set(result.applied) == {
        branch0,
        branch1,
    }, f"both branches must appear in applied: {result.applied}"

    # Both files must be present in the base working tree.
    base_root = ws._root
    assert (base_root / "alpha.txt").is_file(), "alpha.txt missing after Git3WayMerge"
    assert (base_root / "beta.txt").is_file(), "beta.txt missing after Git3WayMerge"
    assert (base_root / "alpha.txt").read_text(encoding="utf-8") == "alpha content"
    assert (base_root / "beta.txt").read_text(encoding="utf-8") == "beta content"

    # Clean up.
    ws.remove_worktree(wt0)
    ws.remove_worktree(wt1)
