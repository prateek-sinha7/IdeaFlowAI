"""tests/agents/test_git_init_acceptance.py — ship-blocker acceptance tests
for git_init_sandbox (tasks 2.1 + 2.2).

These are integration-level tests that operate a REAL git repository on disk
(via tmp_path) — no mocks, no fakes for the git layer.

Three invariants asserted here:

  1. ``git_init_sandbox()`` is idempotent — calling it twice on the same
     workspace raises no error and leaves a valid ``.git/`` directory.
     (Requirement 6 AC 1)

  2. After ``git_init_sandbox()``, a fan-out worktree allocation and merge
     succeed without encountering an "unborn HEAD" error. Without an initial
     commit the ``git merge --no-ff`` into HEAD exits non-zero with a
     "unborn HEAD" message — that error was previously laundered into a
     falsely reported clean merge.
     (Requirement 6 AC 2-3)

  3. ``git show --stat HEAD`` after provision contains NONE of the eight
     gitignored paths — those paths cannot appear in the committed tree
     because they are covered by ``.gitignore``. The ``.gitignore`` file
     itself IS committed and contains all eight paths.
     (Requirement 8 AC 1-4)

Requirements: 6, 8
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.agents.runtime.local import (
    LocalExecutionPolicy,
    LocalSandboxRuntime,
    LocalWorkspace,
)
from app.agents.sandbox import RunSandbox


# ---------------------------------------------------------------------------
# Helpers (mirrors test_merge_worktree_acceptance.py)
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    """Run a git command in ``cwd`` and return stdout. Raises on failure."""
    result = subprocess.run(
        [
            "git",
            "-c", "user.name=Flowin Test",
            "-c", "user.email=test@flowin.local",
            "-c", "commit.gpgsign=false",
            "-c", "init.defaultBranch=main",
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


# The eight reserved paths defined by Requirement 8 AC 1.
_GITIGNORED_PATHS = (
    ".uploads/",
    ".logs/",
    ".verify/",
    ".browser/",
    ".agents/",
    ".chain/",
    ".context/",
    "skills/",
)


# ---------------------------------------------------------------------------
# Acceptance test 1 — git_init_sandbox is idempotent
# ---------------------------------------------------------------------------


def test_git_init_sandbox_is_idempotent(tmp_path: Path) -> None:
    """Calling git_init_sandbox() twice must not raise and must leave a valid repo.

    Requirement 6 AC 1: "idempotently — if .git/ already exists, the call is
    a no-op."

    After the second call the repository must still be healthy (git status must
    succeed) and HEAD must still point to a valid commit (not be unborn).
    """
    ws = _make_workspace(tmp_path, run_id="run-idempotent")

    # First call — initialises the repo and makes the initial commit.
    ws.git_init_sandbox()

    git_dir = ws._root / ".git"
    assert git_dir.is_dir(), ".git/ must exist after first git_init_sandbox()"

    # Capture the HEAD commit after the first call.
    head_after_first = _git(ws._root, "rev-parse", "HEAD").strip()
    assert head_after_first, "HEAD must be a valid commit after first git_init_sandbox()"

    # Second call — must be a no-op: no exception, no new commit.
    ws.git_init_sandbox()  # must not raise

    assert git_dir.is_dir(), ".git/ must still exist after second git_init_sandbox()"

    # HEAD must be the SAME commit — the second call must not have created a new one.
    head_after_second = _git(ws._root, "rev-parse", "HEAD").strip()
    assert head_after_second == head_after_first, (
        "HEAD must not change on the second (idempotent) git_init_sandbox() call; "
        f"before={head_after_first!r}, after={head_after_second!r}"
    )

    # The repo must still be usable (git status must succeed, nothing unexpected).
    _git(ws._root, "status")


# ---------------------------------------------------------------------------
# Acceptance test 2 — fan-out on step 1 merges without unborn HEAD
# ---------------------------------------------------------------------------


def test_fanout_merge_succeeds_after_git_init_no_unborn_head(tmp_path: Path) -> None:
    """A fan-out worktree allocation and merge succeed after git_init_sandbox().

    Without the initial commit that Requirement 6 AC 2 mandates, git merge
    --no-ff into an unborn HEAD exits non-zero, and the pre-fix code laundered
    that error into a falsely clean merge (conflicts: []).  After the fix both
    the initial commit and the merge classification are correct, so this test
    confirms end-to-end that no "unborn HEAD" failure occurs.

    Requirement 6 AC 2-3.
    """
    ws = _make_workspace(tmp_path, run_id="run-unborn")
    ws.git_init_sandbox()

    # Confirm HEAD is born (not unborn) before attempting the fan-out.
    spawn = ws.spawn_point_commit()
    assert spawn, (
        "spawn_point_commit() must return a non-empty SHA — "
        "git_init_sandbox() must have made an initial commit"
    )

    # Allocate a worktree for step 1 (worker index 0).
    wt = ws.allocate_worktree("step1", 0)
    wt.write_file("result.txt", "step 1 output")
    wt.commit_all("step 1 worker output")
    branch = wt._worktree_branch
    assert branch, "worktree branch must be stamped after allocate_worktree"

    # Merge the worker branch back into the base — must not raise CalledProcessError
    # due to an unborn HEAD, and must not return a false-clean result.
    result = ws.merge_worktree(branch, spawn)

    assert result["conflicts"] == [], (
        f"single disjoint worker must merge cleanly; got conflicts: {result['conflicts']}"
    )

    # Commit the merge so the working tree is clean.
    ws.commit_all("merge: step1 worker 0")

    # The file written by the worker must be present in the base tree.
    assert (ws._root / "result.txt").is_file(), (
        "result.txt must be present in the base tree after the merge"
    )
    assert (ws._root / "result.txt").read_text(encoding="utf-8") == "step 1 output"

    # Tear down the worktree.
    ws.remove_worktree(wt)


# ---------------------------------------------------------------------------
# Acceptance test 3 — git show --stat HEAD contains none of the 8 gitignored paths
# ---------------------------------------------------------------------------


def test_gitignore_seeded_and_reserved_paths_not_committed(tmp_path: Path) -> None:
    """After git_init_sandbox(), none of the 8 reserved paths appear in the commit.

    Three sub-assertions:

    a) git show --stat HEAD lists only .gitignore (or is empty for --allow-empty
       fallback) — none of the eight reserved directory names appear in the
       committed tree.

    b) The committed .gitignore contains all eight reserved paths exactly.

    c) Creating the reserved directories after init and running git add -A does
       NOT stage them (gitignore is effective).

    Requirement 8 AC 1-4.
    """
    ws = _make_workspace(tmp_path, run_id="run-gitignore")
    ws.git_init_sandbox()

    # ── (a) git show --stat HEAD must not mention reserved paths ─────────────
    try:
        show_stat = _git(ws._root, "show", "--stat", "HEAD")
    except subprocess.CalledProcessError as exc:
        pytest.fail(f"git show --stat HEAD failed: {exc.stderr}")

    for reserved in _GITIGNORED_PATHS:
        # Strip trailing slash so we match directory names in path segments.
        name = reserved.rstrip("/")
        assert name not in show_stat, (
            f"Reserved path {reserved!r} must NOT appear in git show --stat HEAD; "
            f"found {name!r} in:\n{show_stat}"
        )

    # ── (b) .gitignore must contain all eight reserved paths ─────────────────
    gitignore_path = ws._root / ".gitignore"
    assert gitignore_path.is_file(), ".gitignore must exist after git_init_sandbox()"

    gitignore_content = gitignore_path.read_text(encoding="utf-8")
    for reserved in _GITIGNORED_PATHS:
        assert reserved in gitignore_content, (
            f"Reserved path {reserved!r} must be in .gitignore; "
            f"actual .gitignore:\n{gitignore_content}"
        )

    # ── (c) reserved directories created after init must not be staged ───────
    # Materialise each reserved directory with a file inside it.
    for reserved in _GITIGNORED_PATHS:
        dir_path = ws._root / reserved.rstrip("/")
        dir_path.mkdir(parents=True, exist_ok=True)
        (dir_path / "probe.txt").write_text("should be ignored", encoding="utf-8")

    # git add -A should NOT pick up anything inside the ignored directories.
    _git(ws._root, "add", "-A")
    status_output = _git(ws._root, "status", "--porcelain")

    for reserved in _GITIGNORED_PATHS:
        name = reserved.rstrip("/")
        assert name not in status_output, (
            f"Reserved path {reserved!r} must not be staged by git add -A; "
            f"found {name!r} in git status output:\n{status_output}"
        )
