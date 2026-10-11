"""tests/agents/test_cancel_paths_v3.py — Requirement 28/29/42 cancel-path verification.

V8 verification debt closure: FR-059/AC-28, FR-060/AC-29, FR-042.

Three scenarios verified via a real git sandbox:

1. **FR-059 / AC-28: cancel mid-fan-out retains branches**
   Drives the real `agents.execution_engine.fanout.run_fanout` cancel path (a
   fake `ctx.runner` + a real `asyncio.Event`): `_cancel_active` at the
   `finally` teardown becomes True, so `_teardown_allocated` is called with
   `delete_branch=False`. That teardown is wired to the REAL
   `LocalWorkspace.remove_worktree` against a real `git worktree`, so the
   retained-branch assertion is a fact about the app's own code, not a
   hand-rolled `git worktree remove`.

2. **FR-060 / AC-29: last commit blocked → degraded and untagged**
   When the last (terminal) commit is blocked by a hook, the run is degraded
   and no tag is created, even if the candidate_status would otherwise be
   "completed". A paired control (`last_commit_blocked=False` → completed +
   `v1` tag) proves the assertion discriminates the FR-060 gate itself,
   rather than an unrelated `FakeSandbox` fixture gap forcing every run to
   degrade regardless of the flag.

3. **FR-042: cancel never resets (HEAD unchanged, one new commit)**
   Drives the real `finalize_terminal_run(candidate_status="cancelled")`
   against a dirty real sandbox and spies (without replacing) the real
   `commit_in_sandbox` to pin the git state around the cancel's own WIP
   commit: its parent is the pre-cancel HEAD (no reset) and it adds exactly
   one commit.

Offline-safe: real git sandbox (tmp_path), scripted model only (no Bedrock / DB).

FR mapping:
  FR-059: Cancel mid-fan-out end to end → delete_branch=False (branches retained).
  FR-060: Last commit blocked → degraded, untagged.
  FR-042: Cancel never resets (HEAD unchanged, exactly one new commit).

AC mapping:
  AC-28: Cancel still leaves branches listed in git.
  AC-29: Last commit blocked → degraded status, no tag created.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import types
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Importing the harness forces InMemory checkpointer + temp RUNS_ROOT before
# app.core.config loads.  Keep this import first.
from tests.agents._scripted_model import (
    ScriptedFakeChatModel,
)

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

BACKEND_ROOT = Path(__file__).parent.parent.parent  # …/backend/
sys.path.insert(0, str(BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Helpers — real-git sandbox fixture
# ---------------------------------------------------------------------------

_USER_ID = "test-user-cancel"
_WORKSPACE_ID = "ws-test-cancel"


def _run_git(*args: str, cwd: Path, check: bool = True) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Flowin Test",
            "-c",
            "user.email=test@flowin.local",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=str(cwd),
        check=check,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _git_init(repo: Path) -> None:
    """Initialize a git repository with standard test config."""
    _run_git("init", "-b", "main", cwd=repo)
    _run_git("config", "user.email", "test@test.test", cwd=repo)
    _run_git("config", "user.name", "Test Bot", cwd=repo)
    # Seed .gitignore with reserved paths
    reserved = "\n".join(
        [
            ".uploads/",
            ".logs/",
            ".verify/",
            ".browser/",
            ".agents/",
            ".chain/",
            ".context/",
            "skills/",
            "conversation_history/",
            ".chain-legacy/",
        ]
    )
    (repo / ".gitignore").write_text(reserved + "\n", encoding="utf-8")
    _run_git("add", ".gitignore", cwd=repo)
    _run_git("commit", "-m", "chore: init", cwd=repo)


def _make_run_id() -> str:
    """Generate a unique run id."""
    return f"cancel-test-{uuid.uuid4().hex[:8]}"


@dataclass
class FakeSandbox:
    """Minimal sandbox facade backed by a real git repo for testing."""

    root: Path
    run_id: str
    has_git: bool = True

    def _ws(self) -> Any:
        """Return self."""
        return self

    def _git(self, *args: str) -> str:
        return _run_git(*args, cwd=self.root)

    @property
    def run_log_path(self) -> Path:
        return self.root / ".logs" / f"{self.run_id}.jsonl"

    def reset_index(self) -> None:
        """Reset the git index."""
        if self.has_git:
            _run_git("reset", "HEAD", cwd=self.root)

    def is_dirty(self) -> bool:
        """Return True when the working tree has uncommitted changes."""
        if not self.has_git:
            return False
        return bool(_run_git("status", "--porcelain", cwd=self.root))

    def head_commit(self) -> str:
        """Return the current HEAD commit SHA."""
        if self.has_git:
            return _run_git("rev-parse", "HEAD", cwd=self.root)
        return ""

    def git_init_sandbox(self) -> None:
        """Initialize git in the sandbox."""
        if self.has_git:
            _git_init(self.root)

    def commit_all(
        self,
        message: str,
        *,
        paths: list[str] | None = None,
        force_add: frozenset[str] | None = None,
    ) -> str:
        """Stage and commit all working-tree changes, gated on has_git."""
        if not self.has_git:
            return ""

        try:
            # Force-add the explicitly allowed paths first (e.g., .chain/)
            if force_add:
                for path in force_add:
                    _run_git("add", "-f", path, cwd=self.root, check=False)

            # Stage changes: specific paths or all if paths is None
            if paths:
                for path in paths:
                    _run_git("add", path, cwd=self.root)
            else:
                _run_git("add", "-A", cwd=self.root)

            # Check if there's anything staged
            diff_output = _run_git("diff", "--cached", "--name-only", cwd=self.root)
            if not diff_output:
                # Nothing to commit
                return ""

            # Commit
            _run_git("commit", "-m", message, cwd=self.root)
            # Return the new HEAD SHA
            return _run_git("rev-parse", "HEAD", cwd=self.root)
        except Exception:
            # If commit fails, return empty SHA
            return ""

    def create_tag(self, name: str) -> None:
        """Create a git tag."""
        _run_git("tag", name, cwd=self.root)

    def list_tags(self) -> list[str]:
        """List all tags."""
        out = _run_git("tag", cwd=self.root)
        return [line.strip() for line in out.splitlines() if line.strip()]

    def list_branches(self) -> list[str]:
        """List all branches."""
        out = _run_git("branch", "-a", cwd=self.root)
        return [line.strip() for line in out.splitlines() if line.strip()]

    def create_run_ref(self, run_id: str) -> Any:
        """Create/refresh the internal per-run ref at HEAD.

        Mirrors ``test_finalizer_v2.py``'s ``FakeSandbox`` — the finalizer's
        ref-creation step (``engine.py:1980``) calls this unconditionally on
        any ``has_git=True`` sandbox reaching that step, both on the
        completed and the degraded (metadata-only) path.
        """
        from app.agents.runtime.local import RefResult  # noqa: PLC0415

        ref_name = f"refs/ideaflow/runs/{run_id}"
        head_sha = _run_git("rev-parse", "HEAD", cwd=self.root)
        try:
            existing_sha = _run_git("rev-parse", ref_name, cwd=self.root)
        except subprocess.CalledProcessError:
            existing_sha = None
        if existing_sha is not None:
            if existing_sha == head_sha:
                return RefResult(
                    state="idempotent", name=ref_name, sha=head_sha, existing=None
                )
            return RefResult(
                state="conflict", name=ref_name, sha=head_sha, existing=existing_sha
            )
        _run_git("update-ref", "--create-reflog", ref_name, head_sha, cwd=self.root)
        return RefResult(state="created", name=ref_name, sha=head_sha, existing=None)

    def resolve_ref_commit(self, ref: str) -> str | None:
        """Resolve a ref name to its commit SHA, or None if absent."""
        try:
            return _run_git("rev-parse", ref, cwd=self.root)
        except subprocess.CalledProcessError:
            return None

    def stage_exact(self, paths: list[str]) -> None:
        """Force-stage exactly these paths (used for the `.chain/` allowlist)."""
        for p in paths:
            _run_git("add", "--force", "--", p, cwd=self.root)

    def tracked_chain_paths(self) -> list[str]:
        """List tracked paths under `.chain/` (stale-basename reconciliation)."""
        try:
            out = _run_git("ls-files", "--cached", ".chain/", cwd=self.root)
            return [p for p in out.splitlines() if p]
        except subprocess.CalledProcessError:
            return []

    def git_rm_cached(self, path: str) -> None:
        """Untrack a path from the git index without touching the worktree."""
        _run_git("rm", "--cached", "--ignore-unmatch", path, cwd=self.root)

    def atomic_replace_dir(self, src: Path, dst: Path) -> None:
        """Atomically replace ``dst`` with ``src`` (used for `.chain/` staging swap)."""
        if dst.exists():
            shutil.rmtree(dst)
        shutil.move(str(src), str(dst))


def _make_sandbox(
    tmp_path: Path, *, run_id: str | None = None
) -> tuple[FakeSandbox, str]:
    """Create and provision a sandbox with a real git repo under tmp_path."""
    rid = run_id or _make_run_id()
    sandbox_root = tmp_path / "runs" / rid
    sandbox_root.mkdir(parents=True, exist_ok=True)
    sb = FakeSandbox(root=sandbox_root, run_id=rid, has_git=True)
    sb.git_init_sandbox()
    return sb, rid


def _make_ectx(
    run_id: str,
    sandbox: FakeSandbox,
    *,
    final_status: str = "completed",
    deliverable_name: str | None = "output.html",
    revision_ordinal: int = 1,
) -> Any:
    """Return a minimal ExecutionContext-like namespace for testing."""
    deliverable = None
    if deliverable_name:
        deliverable = types.SimpleNamespace(name=deliverable_name)
    return types.SimpleNamespace(
        run_id=run_id,
        user_id=_USER_ID,
        owner_id=_USER_ID,
        workspace_id=_WORKSPACE_ID,
        runner=types.SimpleNamespace(sandbox=sandbox, registry=None, engine=None),
        final_status=final_status,
        deliverable=deliverable,
        revision_ordinal=revision_ordinal,
        step_visit_counts={"step-1": 1},
        last_commit_blocked=False,
        completed_tasks=[],
        run_trace=None,
    )


def _make_step(agent_id: str = "test-agent") -> Any:
    """Return a minimal step-like namespace."""
    return types.SimpleNamespace(
        agent_id=agent_id,
        hooks=[],
        tools=None,
        id=agent_id,
    )


def _git_log_oneline(repo: Path) -> list[str]:
    """Return the git log as a list of one-liners (most recent first)."""
    out = _run_git("log", "--oneline", cwd=repo, check=False)
    if not out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Test AC-28: cancel retains branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac28_cancel_retains_branches(tmp_path: Path) -> None:
    """FR-059 / AC-28: cancel mid-fan-out retains git branches.

    Drives the REAL cancel path in ``agents.execution_engine.fanout.run_fanout``:
    a worker blocks mid-flight, the run's ``cancel_event`` fires, and the
    ``finally`` block's ``_cancel_active`` (fanout.py:782-788) becomes True — so
    ``_teardown_allocated`` is invoked with ``delete_branch=False``. The fake
    ``ctx.runner``'s ``teardown_isolated_workspace`` is wired to the REAL
    ``LocalWorkspace.remove_worktree`` (the git owner Requirement 28 targets),
    operating on a real ``git worktree`` — so the branch-retention assertion
    below is a fact about the app's own code path, not a hand-rolled
    ``git worktree remove``.
    """
    if not shutil.which("git"):
        pytest.skip("git not available")

    from agents.execution_engine.budget import BudgetManager
    from agents.execution_engine.fanout import run_fanout
    from app.agents.runtime.local import LocalWorkspace

    sandbox, run_id = _make_sandbox(tmp_path)

    branch = "fanout/worker-a/0"
    worktree_path = sandbox.root / ".worktrees" / "worker-a" / "0"
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    _run_git("worktree", "add", "-b", branch, str(worktree_path), cwd=sandbox.root)
    assert branch in _run_git("branch", "-a", cwd=sandbox.root)

    # ``remove_worktree`` only reads ``self._root`` — a bare instance rooted at
    # the sandbox runs the REAL app method (not a re-implementation) against
    # the real repo.
    base_ws = LocalWorkspace.__new__(LocalWorkspace)
    base_ws._root = sandbox.root
    worker_ws = types.SimpleNamespace(
        _worktree_branch=branch, _worktree_path=worktree_path
    )

    release = asyncio.Event()
    teardown_delete_branch: list[bool] = []

    class _CancelFanoutRunner:
        def __init__(self) -> None:
            self.run_id = run_id
            self.workspace = types.SimpleNamespace(has_git=True)  # -> worktree scope

        def agent_exists(self, agent_id: str) -> bool:
            return True

        async def allocate_isolated_workspace(self, scope, step, *, worker_index):
            return worker_ws

        async def teardown_isolated_workspace(
            self, base_workspace, ws, *, delete_branch=True
        ):
            # The real fanout.py finally-block call this test proves happens
            # with delete_branch=False on cancel.
            teardown_delete_branch.append(delete_branch)
            base_ws.remove_worktree(ws, delete_branch=delete_branch)

        async def record_subagent_run(self, **kwargs):
            return "row-0"

        async def update_subagent_run(self, row_id, *, status, tokens=None, cost=None):
            return None

        async def run_worker(
            self,
            step,
            ctx,
            *,
            worker_index,
            thread_id,
            agent_id,
            input,
            workspace=None,
            **kw,
        ):
            await release.wait()  # blocks until cancelled mid-flight
            yield {"type": "agent_chunk", "data": {}}

    runner = _CancelFanoutRunner()
    cancel_event = asyncio.Event()
    ctx = types.SimpleNamespace(
        runner=runner,
        depth=0,
        budget=BudgetManager(),
        cancel_event=cancel_event,
    )
    fanout_spec = types.SimpleNamespace(
        mode="parallel", max_parallel=None, agent="self", count=None, workers=[]
    )
    step = types.SimpleNamespace(agent_id="worker-a", fanout=fanout_spec)
    requests = [{"agent": "self", "input": "t-0"}]

    async def _drive() -> None:
        with pytest.raises(asyncio.CancelledError):
            async for _ev in run_fanout(requests, ctx, step=step):
                pass

    task = asyncio.ensure_future(_drive())
    await asyncio.sleep(0.05)  # let the worker enter run_worker before cancelling
    cancel_event.set()
    await task

    assert teardown_delete_branch == [False], (
        f"cancel must tear down with delete_branch=False (Requirement 28); "
        f"got {teardown_delete_branch}. AC-28 violation."
    )
    assert not worktree_path.exists(), "the worktree dir should have been removed"
    branches_after_cancel = _run_git("branch", "-a", cwd=sandbox.root)
    assert branch in branches_after_cancel, (
        "Branch should be retained after cancel (delete_branch=False). "
        "AC-28 violation: branch deleted on cancel."
    )


# ---------------------------------------------------------------------------
# Test AC-29: last commit blocked → degraded and untagged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac29_last_commit_blocked_degraded_untagged(tmp_path: Path) -> None:
    """FR-060 / AC-29: last commit blocked → run degraded, no tag.

    Scenario:
    1. Create a sandbox with a deliverable file
    2. Set ectx.last_commit_blocked = True
    3. Call finalize_terminal_run with candidate_status="completed"
    4. Verify:
       - The record's published_status is degraded (not completed)
       - No tag is created (because degraded runs don't get tagged)
       - The run is marked as non-chainable
    """
    if not shutil.which("git"):
        pytest.skip("git not available")

    sandbox, run_id = _make_sandbox(tmp_path)

    # Create output file (deliverable)
    (sandbox.root / "output.html").write_text("<html>output</html>", encoding="utf-8")
    # Create logs directory and file
    (sandbox.root / ".logs").mkdir(exist_ok=True)
    sandbox.run_log_path.write_text('{"event":"terminal"}\n', encoding="utf-8")

    ectx = _make_ectx(run_id, sandbox, final_status="completed")
    # Mark that the last commit was blocked by a hook
    ectx.last_commit_blocked = True  # type: ignore[attr-defined]

    # Mock DB to avoid real database operations
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    from agents.execution_engine import engine as eng

    # Clear the guard so we can call finalize_terminal_run
    eng._finalize_terminal_run_started.discard(run_id)

    with (
        patch("app.models.database.SessionLocal", return_value=mock_db),
        patch("app.models.workflow.WorkflowRun", MagicMock()),
        patch("app.models.run_finalization.RunFinalization", MagicMock()),
    ):
        record = await eng.finalize_terminal_run(
            run_id, ectx, candidate_status="completed"
        )

    # Verify the run was degraded (not completed)
    assert record is not None, "Finalization record should be returned"
    assert record.published_status == "degraded", (
        f"When last_commit_blocked=True, published_status should be degraded, "
        f"got {record.published_status}. AC-29 violation."
    )

    # Verify no tag was created
    tags = sandbox.list_tags()
    assert len(tags) == 0, (
        f"No tag should be created when run is degraded. "
        f"Found tags: {tags}. AC-29 violation."
    )


@pytest.mark.asyncio
async def test_ac29_control_unblocked_completes_and_tags(tmp_path: Path) -> None:
    """FR-060 / AC-29 control: last_commit_blocked=False → completed + tagged.

    Discriminates the FR-060 gate from an unrelated fixture gap: without this
    control, a ``FakeSandbox`` missing methods the finalizer calls
    unconditionally (``create_run_ref``, ``stage_exact``, ``tracked_chain_paths``,
    ``git_rm_cached``, ``atomic_replace_dir``) would force every run to
    ``degraded`` via caught ``AttributeError``s regardless of
    ``last_commit_blocked`` — making the blocked-case test above pass even if
    the real FR-060 gate were removed. Mirrors the working
    ``test_finalizer_v2.py::test_a5_full_success_then_idempotent_reentry``
    pattern (a DB session whose ``.first()`` returns a truthy row).
    """
    if not shutil.which("git"):
        pytest.skip("git not available")

    sandbox, run_id = _make_sandbox(tmp_path)
    (sandbox.root / "output.html").write_text("<html>output</html>", encoding="utf-8")
    (sandbox.root / ".logs").mkdir(exist_ok=True)
    sandbox.run_log_path.write_text('{"event":"terminal"}\n', encoding="utf-8")

    ectx = _make_ectx(run_id, sandbox, final_status="completed")
    assert ectx.last_commit_blocked is False

    def _good_session() -> MagicMock:
        m = MagicMock()
        m.query.return_value.filter.return_value.first.return_value = MagicMock()
        return m

    from agents.execution_engine import engine as eng

    eng._finalize_terminal_run_started.discard(run_id)

    with (
        patch("app.models.database.SessionLocal", side_effect=_good_session),
        patch("app.models.workflow.WorkflowRun", MagicMock()),
        patch("app.models.run_finalization.RunFinalization", MagicMock()),
    ):
        record = await eng.finalize_terminal_run(
            run_id, ectx, candidate_status="completed"
        )

    assert record is not None
    assert record.published_status == "completed", (
        "AC-29 control: with last_commit_blocked=False the run must complete "
        f"and tag, got published_status={record.published_status!r} "
        f"(degraded_reason={getattr(record, 'degraded_reason', None)!r}). "
        "If this fails, the AC-29 blocked-case test above is not discriminating "
        "the FR-060 gate from a fixture defect."
    )
    tags = sandbox.list_tags()
    assert "v1" in tags, f"Expected v1 tag on the un-blocked control run; tags={tags}"


# ---------------------------------------------------------------------------
# Test FR-042: cancel never resets (HEAD unchanged, one new commit)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fr042_cancel_commits_forward_never_resets(tmp_path: Path) -> None:
    """FR-042: the cancel path commits forward — it never resets.

    Drives the REAL engine cancel path end to end: a dirty real sandbox +
    ``finalize_terminal_run(candidate_status="cancelled")`` reaches the
    "Step 2: Non-success WIP reconcile" block (engine.py ~1724-1769), which
    calls the real ``commit_in_sandbox`` with the real
    ``wip: cancelled at step {id}`` message (engine.py:1738).

    ``commit_in_sandbox`` is wrapped (not replaced) with a spy so the assertion
    can pin down the git state immediately before/after THAT specific call —
    the positive, git-level proof the row asks for: the new commit's parent is
    the pre-cancel HEAD (ancestry intact — no ``git reset --hard`` happened)
    and exactly one commit was added by it.

    Note: ``finalize_terminal_run`` also makes a second, unrelated "chore:
    terminal snapshot" commit later (Step 6) for EVERY terminal status
    (completed/cancelled/failed/...) — that is the payload/snapshot bookkeeping
    FR-009/FR-037 own, not the cancel mechanism FR-042/FR-055 are about. This
    test therefore scopes "exactly one new commit" to the cancel's own WIP
    commit, not the whole finalizer call.
    """
    if not shutil.which("git"):
        pytest.skip("git not available")

    sandbox, run_id = _make_sandbox(tmp_path)
    head_before = sandbox.head_commit()

    # Dirty the working tree — leftover in-flight work at cancel time.
    (sandbox.root / "abandoned_work.md").write_text(
        "partial output\n", encoding="utf-8"
    )
    assert sandbox.is_dirty() is True

    (sandbox.root / ".logs").mkdir(exist_ok=True)
    sandbox.run_log_path.write_text('{"event":"terminal"}\n', encoding="utf-8")

    ectx = _make_ectx(run_id, sandbox, final_status="cancelled")
    ectx.step_visit_counts = {"planner": 1, "builder": 2}  # type: ignore[attr-defined]

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    from agents.execution_engine import engine as eng

    eng._finalize_terminal_run_started.discard(run_id)

    real_commit_in_sandbox = eng.commit_in_sandbox
    calls: list[tuple[str, str, str]] = []

    async def _spy_commit_in_sandbox(sandbox_arg, message, *args, **kwargs):
        before = sandbox.head_commit()
        result = await real_commit_in_sandbox(sandbox_arg, message, *args, **kwargs)
        after = sandbox.head_commit()
        calls.append((message, before, after))
        return result

    with (
        patch("app.models.database.SessionLocal", return_value=mock_db),
        patch("app.models.workflow.WorkflowRun", MagicMock()),
        patch("app.models.run_finalization.RunFinalization", MagicMock()),
        patch(
            "agents.execution_engine.engine.commit_in_sandbox",
            AsyncMock(side_effect=_spy_commit_in_sandbox),
        ),
    ):
        await eng.finalize_terminal_run(run_id, ectx, candidate_status="cancelled")

    assert (
        calls
    ), "commit_in_sandbox was never called — the WIP reconcile path did not run"
    wip_message, wip_before, wip_after = calls[0]

    assert (
        wip_message == "wip: cancelled at step builder"
    ), f"expected the real engine WIP message, got {wip_message!r}. FR-042 violation."
    assert wip_before == head_before, (
        "the WIP commit must be created directly on top of the pre-cancel HEAD "
        f"(no reset happened before it): expected parent {head_before!r}, "
        f"commit_in_sandbox saw {wip_before!r}. FR-042 violation."
    )
    assert wip_after != wip_before, (
        "the WIP commit must produce a new commit, not leave HEAD untouched. "
        "FR-042 violation."
    )
    assert sandbox._git("rev-parse", f"{wip_after}^") == head_before, (
        "the WIP commit's parent must be exactly the pre-cancel HEAD — i.e. "
        "cancel commits ONE commit forward, it never resets. FR-042 violation."
    )
    final_log = _git_log_oneline(sandbox.root)
    assert head_before in sandbox._git("log", "--format=%H"), (
        "the pre-cancel commit must still be reachable in history (no rewrite/"
        f"reset destroyed it): log={final_log}. FR-042 violation."
    )
