"""tests/agents/test_isolation.py — Phase-11 fan-out isolation scopes (FANOUT-05).

Drives the two engine-selected isolation scopes fully OFFLINE:

  * ``sub_sandbox`` (``LocalWorkspace.allocate_sub_sandbox``) — an isolated child dir
    ``{run}/subagents/{step}/{i}/`` under the run root; owner/workspace stamped; two
    workers writing the SAME relpath land in DISTINCT dirs (no cross-contamination,
    T-11-02-02 / T-11-02-05).
  * ``worktree`` (``LocalWorkspace.allocate_worktree`` / ``spawn_point_commit`` /
    ``remove_worktree``) — a git worktree on a per-worker branch ``fanout/{step}/{i}``;
    the spawn-point commit is captured; ``remove_worktree`` leaves ZERO orphans in
    ``git worktree list`` (T-11-02-04). Skipped if ``git`` is unavailable.

  * engine scope selection (``fanout._select_isolation_scope``) — ``has_git=True`` base
    → ``worktree``; sandbox (``has_git=False``) base → ``sub_sandbox``; the scope is
    recorded on the child's ``subagent_runs.isolation``; ``step.fanout`` can NEVER
    influence the scope (INV-7 — engine-decided).
"""

from __future__ import annotations

import shutil
import subprocess
from types import SimpleNamespace

import pytest

from app.agents.runtime.local import LocalSandboxRuntime
from app.agents.sandbox import RunSandbox


_GIT = shutil.which("git")
requires_git = pytest.mark.skipif(_GIT is None, reason="git not available")


@pytest.fixture()
def runs_root(tmp_path, monkeypatch):
    """A writable RUNS_ROOT under tmp (the default /app/runs is not writable locally)."""
    monkeypatch.setattr("app.core.config.settings.RUNS_ROOT", str(tmp_path))
    return str(tmp_path)


def _base_workspace(runs_root, *, has_git: bool):
    rt = LocalSandboxRuntime()
    return rt.create_workspace(
        owner_id="owner-1", workspace_id="ws-run-1", has_git=has_git, exec=False
    )


def _init_repo(ws) -> None:
    """Seed a one-commit git repo at the workspace root (for the worktree scope)."""
    root = str(ws._sandbox.root)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.local"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    ws.write_file("seed.txt", "base\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=root, check=True)


# ---------------------------------------------------------------------------
# sub_sandbox scope
# ---------------------------------------------------------------------------


def test_sub_sandbox_creates_distinct_child_dir(runs_root):
    base = _base_workspace(runs_root, has_git=False)
    child = base.allocate_sub_sandbox(step="build", worker_index=0)

    # The child roots UNDER {run}/subagents/build/0/ and is distinct from the parent.
    child_root = child._sandbox.root
    assert child_root != base._sandbox.root
    assert child_root.parts[-3:] == ("subagents", "build", "0")
    assert str(child_root).startswith(str(base._sandbox.root) + "/")


def test_sub_sandbox_stamps_owner_and_workspace(runs_root):
    base = _base_workspace(runs_root, has_git=False)
    child = base.allocate_sub_sandbox(step="build", worker_index=2)
    # owner/workspace stamped from the parent (T-11-02-05).
    assert child.owner_id == base.owner_id == "owner-1"
    assert child.workspace_id == base.workspace_id == "ws-run-1"
    # has_git=False / exec=off inherited (the no-git fan-out default).
    assert child.policy.allows("exec") is False


def test_two_sub_sandbox_workers_same_filename_no_cross_contamination(runs_root):
    """Two workers writing the SAME relpath land in DISTINCT dirs (T-11-02-02)."""
    base = _base_workspace(runs_root, has_git=False)
    w0 = base.allocate_sub_sandbox(step="build", worker_index=0)
    w1 = base.allocate_sub_sandbox(step="build", worker_index=1)

    w0.write_file("out.txt", "worker-0")
    w1.write_file("out.txt", "worker-1")

    # Distinct child dirs.
    assert w0._sandbox.root != w1._sandbox.root
    # No cross-contamination — each read returns its OWN write.
    assert w0.read_file("out.txt") == "worker-0"
    assert w1.read_file("out.txt") == "worker-1"


def test_sub_sandbox_rejects_path_escape(runs_root):
    base = _base_workspace(runs_root, has_git=False)
    child = base.allocate_sub_sandbox(step="build", worker_index=0)
    with pytest.raises(ValueError):
        child.write_file("../escape.txt", "nope")


# ---------------------------------------------------------------------------
# worktree scope
# ---------------------------------------------------------------------------


@requires_git
def test_worktree_creates_branch_and_dir(runs_root):
    base = _base_workspace(runs_root, has_git=True)
    _init_repo(base)

    wt = base.allocate_worktree(step="build", worker_index=0)

    # A per-worker branch fanout/build/0 exists.
    branches = subprocess.run(
        ["git", "branch", "--list", "fanout/build/0"],
        cwd=str(base._sandbox.root), check=True, capture_output=True, text=True,
    ).stdout
    assert "fanout/build/0" in branches
    # The worktree dir exists + is rooted under the run dir.
    assert wt._sandbox.root.is_dir()
    assert str(wt._sandbox.root).startswith(str(base._sandbox.root) + "/")


@requires_git
def test_worktree_captures_spawn_point_commit(runs_root):
    base = _base_workspace(runs_root, has_git=True)
    _init_repo(base)
    commit = base.spawn_point_commit()
    # A full SHA (40 hex) captured at spawn for the 11-03 merge-base.
    assert commit and len(commit) == 40
    assert all(c in "0123456789abcdef" for c in commit)


@requires_git
def test_remove_worktree_leaves_no_orphan(runs_root):
    base = _base_workspace(runs_root, has_git=True)
    _init_repo(base)

    wt = base.allocate_worktree(step="build", worker_index=0)
    # Sanity: the worktree is registered before removal.
    listed = subprocess.run(
        ["git", "worktree", "list"], cwd=str(base._sandbox.root),
        check=True, capture_output=True, text=True,
    ).stdout
    assert str(wt._sandbox.root) in listed or "fanout/build/0" in listed

    base.remove_worktree(wt)

    # Zero orphan worktrees + the per-worker branch is deleted.
    listed_after = subprocess.run(
        ["git", "worktree", "list"], cwd=str(base._sandbox.root),
        check=True, capture_output=True, text=True,
    ).stdout
    assert str(wt._sandbox.root) not in listed_after
    branches = subprocess.run(
        ["git", "branch", "--list", "fanout/build/0"],
        cwd=str(base._sandbox.root), check=True, capture_output=True, text=True,
    ).stdout
    assert "fanout/build/0" not in branches


@requires_git
def test_two_worktree_workers_isolated(runs_root):
    """Two worktree workers on distinct branches do not see each other's writes."""
    base = _base_workspace(runs_root, has_git=True)
    _init_repo(base)

    w0 = base.allocate_worktree(step="build", worker_index=0)
    w1 = base.allocate_worktree(step="build", worker_index=1)
    w0.write_file("out.txt", "worker-0")
    w1.write_file("out.txt", "worker-1")

    assert w0._sandbox.root != w1._sandbox.root
    assert w0.read_file("out.txt") == "worker-0"
    assert w1.read_file("out.txt") == "worker-1"

    base.remove_worktree(w0)
    base.remove_worktree(w1)


# ---------------------------------------------------------------------------
# git is NOT shelled capability-side (Phase-9 D-10)
# ---------------------------------------------------------------------------


def test_git_ops_are_not_capability_side():
    """No git-worktree shelling / subprocess SPAWN lives under agents/capabilities/.

    Phase-9 D-10: ``LocalWorkspace`` is the SINGLE git-subprocess owner — the Phase-11
    worktree add/remove + branch delete live there, NEVER capability-side. This guard
    is the FANOUT-05 boundary: no ``git worktree`` token and no process SPAWN
    (``subprocess.run`` / ``subprocess.Popen`` / ``subprocess.call``) capability-side.

    NB: the 10-04 code validators legitimately reference ``subprocess.TimeoutExpired``
    (an exception TYPE) while reaching exec through the runner/workspace handle — they
    spawn nothing themselves, so a bare ``subprocess`` import / exception reference is
    NOT a leak; only an actual spawn or a ``git worktree`` shell is.
    """
    import pathlib

    cap_dir = pathlib.Path(__file__).resolve().parents[2] / "agents" / "capabilities"
    spawn_tokens = (
        "subprocess.run(",
        "subprocess.Popen(",
        "subprocess.call(",
        "subprocess.check_output(",
        "git worktree",
    )
    offenders = []
    for py in cap_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if any(tok in text for tok in spawn_tokens):
            offenders.append(str(py))
    assert offenders == [], f"git spawn leaked capability-side: {offenders}"
