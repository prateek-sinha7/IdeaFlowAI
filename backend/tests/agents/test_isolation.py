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

from agents.execution_engine.budget import BudgetManager
from agents.execution_engine.fanout import (
    _select_isolation_scope,
    run_fanout,
)
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


# ---------------------------------------------------------------------------
# Engine isolation-scope selection (INV-7 — engine-decided, NOT manifest)
# ---------------------------------------------------------------------------


def test_select_scope_worktree_when_has_git():
    base = SimpleNamespace(has_git=True)
    assert _select_isolation_scope(base) == "worktree"


def test_select_scope_sub_sandbox_when_no_git():
    base = SimpleNamespace(has_git=False)
    assert _select_isolation_scope(base) == "sub_sandbox"


def test_select_scope_defaults_to_sub_sandbox_when_attr_absent():
    # A workspace with no has_git attr (a non-git sandbox) → sub_sandbox.
    assert _select_isolation_scope(SimpleNamespace()) == "sub_sandbox"


class _IsolationFakeRunner:
    """A ctx.runner fake that exposes the FANOUT-05 alloc/reclaim seam + a base ws."""

    def __init__(self, *, has_git: bool, known_agents=None):
        self.run_id = "run-iso"
        self.allowed_workers = []
        self._known = set(known_agents or [])
        self.workspace = SimpleNamespace(has_git=has_git)
        self.allocated_calls: list[tuple] = []
        self.reclaimed: list = []
        self.spawned: list[dict] = []
        self.recorded_rows: list[dict] = []
        self.updated_rows: list[dict] = []
        self._row_seq = 0
        self.worker_workspaces: list = []

    def agent_exists(self, agent_id):
        return agent_id in self._known

    async def allocate_isolated_workspace(self, scope, step, *, worker_index):
        self.allocated_calls.append((scope, step, worker_index))
        # Return a marker workspace so run_fanout threads it into run_worker.
        return SimpleNamespace(scope=scope, step=step, worker_index=worker_index)

    async def reclaim_isolated_workspace(self, base_workspace, worker_ws):
        self.reclaimed.append(worker_ws)

    async def record_subagent_run(self, *, parent_step, worker_agent, depth, isolation, status, tokens=None, cost=None):
        self._row_seq += 1
        row_id = f"row-{self._row_seq}"
        self.recorded_rows.append(
            dict(id=row_id, parent_step=parent_step, worker_agent=worker_agent,
                 depth=depth, isolation=isolation, status=status)
        )
        return row_id

    async def update_subagent_run(self, row_id, *, status, tokens=None, cost=None):
        self.updated_rows.append(dict(id=row_id, status=status))

    async def run_worker(self, step, ctx, *, worker_index, thread_id, agent_id, input, workspace=None):
        self.spawned.append(dict(index=worker_index, agent_id=agent_id, workspace=workspace))
        self.worker_workspaces.append(workspace)
        yield {"type": "agent_chunk", "data": {"worker": worker_index}}


def _iso_ctx(runner):
    return SimpleNamespace(runner=runner, depth=0, budget=BudgetManager())


def _iso_step(agent_id="worker-a", *, mode="parallel"):
    fanout = SimpleNamespace(mode=mode, max_parallel=None, agent="self", count=None, workers=[])
    return SimpleNamespace(agent_id=agent_id, fanout=fanout)


async def _collect(gen):
    return [ev async for ev in gen]


@pytest.mark.asyncio
async def test_has_git_base_allocates_worktree_recorded_on_subagent_runs():
    runner = _IsolationFakeRunner(has_git=True, known_agents={"worker-a"})
    ctx = _iso_ctx(runner)
    step = _iso_step("worker-a")
    requests = [{"agent": "self", "input": f"t-{i}"} for i in range(2)]

    await _collect(run_fanout(requests, ctx, step=step))

    # Engine selected worktree (has_git) and allocated one per worker.
    assert [c[0] for c in runner.allocated_calls] == ["worktree", "worktree"]
    # The chosen scope is recorded on EACH child's subagent_runs.isolation.
    assert all(r["isolation"] == "worktree" for r in runner.recorded_rows)
    # Each worker bound its allocated isolated workspace.
    assert all(ws is not None and ws.scope == "worktree" for ws in runner.worker_workspaces)
    # Happy-path teardown reclaimed every allocated workspace.
    assert len(runner.reclaimed) == 2


@pytest.mark.asyncio
async def test_sandbox_base_allocates_sub_sandbox_recorded_on_subagent_runs():
    runner = _IsolationFakeRunner(has_git=False, known_agents={"worker-a"})
    ctx = _iso_ctx(runner)
    step = _iso_step("worker-a")
    requests = [{"agent": "self", "input": "t"}]

    await _collect(run_fanout(requests, ctx, step=step))

    assert [c[0] for c in runner.allocated_calls] == ["sub_sandbox"]
    assert all(r["isolation"] == "sub_sandbox" for r in runner.recorded_rows)
    assert runner.worker_workspaces[0].scope == "sub_sandbox"
    assert len(runner.reclaimed) == 1


@pytest.mark.asyncio
async def test_no_workspace_handle_degrades_to_shared_read():
    """An offline runner with no base workspace → shared_read (11-01 behavior)."""
    runner = _IsolationFakeRunner(has_git=True, known_agents={"worker-a"})
    runner.workspace = None  # no base workspace bound (offline / non-exec)
    ctx = _iso_ctx(runner)
    step = _iso_step("worker-a")

    await _collect(run_fanout([{"agent": "self", "input": "t"}], ctx, step=step))

    # No allocation, scope recorded as shared_read, no teardown.
    assert runner.allocated_calls == []
    assert all(r["isolation"] == "shared_read" for r in runner.recorded_rows)
    assert runner.reclaimed == []


def test_fanout_never_reads_isolation_scope_from_manifest():
    """INV-7: fanout.py reads mode/count/workers but NEVER an isolation scope (T-11-02-03)."""
    import pathlib

    fanout_src = (
        pathlib.Path(__file__).resolve().parents[2]
        / "agents" / "execution_engine" / "fanout.py"
    ).read_text(encoding="utf-8")
    # The scope is derived from base_workspace.has_git, never from step.fanout.
    assert "fanout.isolation" not in fanout_src
    assert "fanout.scope" not in fanout_src
    assert ".fanout.isolation" not in fanout_src
    # The selection helper keys SOLELY on has_git.
    assert "has_git" in fanout_src
