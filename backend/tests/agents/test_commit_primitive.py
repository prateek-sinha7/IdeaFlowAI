"""tests/agents/test_commit_primitive.py — unit + integration tests for commit_in_sandbox.

Tests for task 4.6 (sandbox-git-versioning-v2, Requirement 11).

Five scenarios verified against the ONE security-gated commit primitive:

1. has_git=False → ``no_change=True``, no commit attempted (gate on git presence).
2. Declared pre_commit hook returns BLOCK → ``blocked=True`` (block_reason
   ``pre_commit_hook_blocked``), diff stays in tree, no commit created.
3. Staged content containing a planted secret → mandatory scan BLOCKS commit
   (block_reason ``secret_detected``), commit NOT reachable from any ref.
4. Clean staged diff → successful result with a non-empty SHA.
5. A planted secret is unreachable from any git ref after a blocked commit.

All real-filesystem tests (2–5) operate a genuine git repository under
``tmp_path`` (no mocks for the git layer) so the assertions are grounded in
actual git history, not mock call counts.

Requirements: 11
"""

from __future__ import annotations

import io
import subprocess
import types
import uuid
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BACKEND_ROOT = Path(__file__).parent.parent.parent  # …/backend/


def _run_id() -> str:
    return f"cmt-test-{uuid.uuid4().hex[:8]}"


def _make_sandbox(tmp_path: Path, *, run_id: str | None = None, has_git: bool = True):
    """Create and provision a RunSandbox with a real git repo under tmp_path."""
    from app.agents.sandbox import RunSandbox

    rid = run_id or _run_id()
    sb = RunSandbox("test-user", rid, runs_root=str(tmp_path), has_git=has_git)
    sb.ensure()
    if has_git:
        sb._ws().git_init_sandbox()  # type: ignore[attr-defined]
    return sb


def _make_ectx(run_id: str | None = None):
    """Return a minimal ExecutionContext with the required scalar fields only."""
    from agents.execution_engine.context import ExecutionContext

    return ExecutionContext(
        run_id=run_id or _run_id(),
        owner_id="test-user",
    )


def _make_step(agent_id: str = "test-agent"):
    """Return a minimal step-like namespace accepted by commit_in_sandbox."""
    return types.SimpleNamespace(agent_id=agent_id, hooks=[], tools=None)


def _git(cwd: Path, *args: str) -> str:
    """Run a git command in *cwd* and return stdout. Raises on failure."""
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
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


# ---------------------------------------------------------------------------
# Test 1 — has_git=False returns no_change=True immediately
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_in_sandbox_returns_no_change_when_has_git_false(
    tmp_path: Path,
) -> None:
    """commit_in_sandbox with has_git=False must return no_change=True without staging.

    Requirement 11 AC 9: the primitive owns staging through commit.  When there
    is no git repo the entire chain is a no-op (matches the has_git=False path
    documented in the function contract).
    """
    from agents.execution_engine.engine import CommitInSandboxResult, commit_in_sandbox

    sb = _make_sandbox(tmp_path, has_git=False)
    ectx = _make_ectx()
    step = _make_step()

    result = await commit_in_sandbox(
        sb, "test: no-git", ectx, step, audit_operation=None
    )

    assert isinstance(result, CommitInSandboxResult)
    assert result.no_change is True, "has_git=False must yield no_change=True"
    assert result.blocked is False, "has_git=False must NOT set blocked"
    assert result.sha == "", "has_git=False must return empty SHA"


# ---------------------------------------------------------------------------
# Test 2 — declared pre_commit hook BLOCK leaves diff in tree, no commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_blocked_by_declared_pre_commit_hook(
    tmp_path: Path,
) -> None:
    """A declared pre_commit hook returning BLOCK must block the commit.

    The function must return CommitInSandboxResult(blocked=True,
    block_reason='pre_commit_hook_blocked').  The diff must remain in the
    working tree (the file written before the call is still staged but no
    commit is created on the branch).

    Requirement 11 AC 9–10 (V2-Q12): every commit path is security-gated;
    a declared hook can block but must leave the diff uncommitted.
    """
    from agents.capabilities.hooks.base import HOOK_BLOCK
    from agents.execution_engine.engine import CommitInSandboxResult, commit_in_sandbox

    sb = _make_sandbox(tmp_path)
    ectx = _make_ectx()
    step = _make_step()

    # Plant a file so there is something to stage and diff.
    (sb.root / "work.txt").write_text("some work output", encoding="utf-8")

    # Build the registry + engine stubs so the declared pre_commit hook path fires
    # and returns HOOK_BLOCK.  registry must be non-None to activate step 3.
    registry = MagicMock()
    mock_engine = MagicMock()
    mock_engine._fire_hooks = AsyncMock(return_value=HOOK_BLOCK)
    mock_runner = MagicMock()
    mock_runner.engine = mock_engine
    ectx.runner = mock_runner

    result = await commit_in_sandbox(
        sb, "test: hook blocked", ectx, step, audit_operation=None, registry=registry
    )

    assert isinstance(result, CommitInSandboxResult)
    assert result.blocked is True, "pre_commit BLOCK must yield blocked=True"
    assert result.block_reason == "pre_commit_hook_blocked"
    assert result.sha == "", "blocked commit must have empty SHA"

    # The diff must remain in the working tree — no commit was created.
    git_log = _git(sb.root, "log", "--oneline")
    # git_init_sandbox creates the initial empty commit; there must be NO second commit.
    commit_count = len([line for line in git_log.splitlines() if line.strip()])
    assert commit_count == 1, (
        f"blocked commit must NOT create a new commit; found {commit_count} commit(s): "
        f"{git_log!r}"
    )

    # ectx.last_commit_blocked must be set True by the primitive.
    assert (
        ectx.last_commit_blocked is True
    ), "commit_in_sandbox must set ectx.last_commit_blocked=True on block"


# ---------------------------------------------------------------------------
# Test 3 — staged secret is blocked by mandatory scan; no commit created
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_blocked_by_mandatory_secret_scan(
    tmp_path: Path,
) -> None:
    """A staged file containing a secret must be blocked by the mandatory scan.

    The commit primitive's Step 4 runs scan_for_secret on the REAL staged diff
    (D5 fix).  A file containing a recognisable secret pattern must cause the
    commit to be blocked with block_reason 'secret_detected' and the secret
    must NOT reach any commit in the git tree.

    Requirement 11 AC 4 (D5 fix) and AC 9 (V2-Q12): mandatory scan always runs
    on the real staged content; a hit blocks the commit.
    """
    from agents.execution_engine.engine import CommitInSandboxResult, commit_in_sandbox

    sb = _make_sandbox(tmp_path)
    ectx = _make_ectx()
    step = _make_step()

    # Plant a file with a recognisable secret pattern that scan_for_secret catches.
    # The AWS access key id pattern: AKIA followed by 16 uppercase alnum chars.
    secret_value = "AKIAIOSFODNN7EXAMPLE"
    (sb.root / "config.txt").write_text(
        f"aws_access_key_id = {secret_value}\n", encoding="utf-8"
    )

    # No registry — mandatory scan runs regardless (V2-Q12).
    result = await commit_in_sandbox(
        sb, "test: secret staged", ectx, step, audit_operation=None, registry=None
    )

    assert isinstance(result, CommitInSandboxResult)
    assert result.blocked is True, "staged secret must trigger a block"
    assert result.block_reason == "secret_detected"
    assert result.sha == "", "blocked commit must have empty SHA"
    assert ectx.last_commit_blocked is True

    # The secret must be unreachable from any commit in git history.
    _assert_secret_unreachable_from_git(sb.root, secret_value)


# ---------------------------------------------------------------------------
# Test 4 — clean staged diff produces a successful commit with a SHA
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_succeeds_with_clean_staged_diff(
    tmp_path: Path,
) -> None:
    """A clean (secret-free) staged diff must produce a successful commit.

    The result must have a non-empty SHA, blocked=False, and no_change=False.
    The commit must be reachable from HEAD.

    Requirement 11 AC 9 (happy path): a clean diff proceeds through staging,
    scan, and commit.
    """
    from agents.execution_engine.engine import CommitInSandboxResult, commit_in_sandbox

    sb = _make_sandbox(tmp_path)
    ectx = _make_ectx()
    step = _make_step()

    (sb.root / "output.md").write_text(
        "# Analysis\n\nHere is a clean deliverable with no secrets.\n",
        encoding="utf-8",
    )

    result = await commit_in_sandbox(
        sb, "step: writer-agent", ectx, step, audit_operation=None, registry=None
    )

    assert isinstance(result, CommitInSandboxResult)
    assert result.blocked is False, "clean diff must not be blocked"
    assert result.no_change is False, "committed diff must not be no_change"
    assert result.sha, "successful commit must return a non-empty SHA"

    # The SHA must be reachable from HEAD.
    head_sha = _git(sb.root, "rev-parse", "HEAD").strip()
    assert (
        result.sha == head_sha
    ), f"returned SHA {result.sha!r} must equal HEAD {head_sha!r}"


# ---------------------------------------------------------------------------
# Test 5 — planted secret is unreachable from any commit after a blocked commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_planted_secret_unreachable_from_git_after_block(
    tmp_path: Path,
) -> None:
    """After a blocked commit, the secret must be absent from all git objects.

    This is the property that guards against information leakage: even if the
    caller re-uses the sandbox, the blocked file's content must never have
    entered the object store via a completed commit on the real git tree.

    Requirement 11 AC 9–10 (V2-Q12): a block leaves the diff in the working
    tree and does NOT create a commit; the secret is never persisted to history.
    """
    from agents.execution_engine.engine import commit_in_sandbox

    sb = _make_sandbox(tmp_path)
    ectx = _make_ectx()
    step = _make_step()

    # Plant a secret — OpenAI/Anthropic style key prefix.
    secret_value = "sk-" + "A" * 24  # matches the sk-[A-Za-z0-9]{20,} pattern
    (sb.root / "leaked.txt").write_text(f"token = '{secret_value}'\n", encoding="utf-8")

    await commit_in_sandbox(
        sb, "test: should be blocked", ectx, step, audit_operation=None, registry=None
    )

    _assert_secret_unreachable_from_git(sb.root, secret_value)


# ---------------------------------------------------------------------------
# Test 6 — has_git=True, nothing staged warns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_has_git_true_nothing_staged_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """When has_git=True but nothing is staged, commit_in_sandbox must log a warning.

    Requirement 11 (FR-011): when a git-enabled commit no-ops (nothing staged),
    a warning must be logged including the run_id and step_id to alert on a
    missed write or unexpected empty output.
    """
    from agents.execution_engine.engine import CommitInSandboxResult, commit_in_sandbox

    sb = _make_sandbox(tmp_path, has_git=True)
    ectx = _make_ectx()
    step = _make_step()

    # Call commit_in_sandbox without creating any changes to stage.
    # This triggers the no_change early return at line 659-660.
    result = await commit_in_sandbox(
        sb, "test: no changes", ectx, step, audit_operation=None
    )

    # Assert the result is correct (no_change=True, no error).
    assert isinstance(result, CommitInSandboxResult)
    assert result.no_change is True, "empty tree should return no_change=True"
    assert result.blocked is False, "empty tree should NOT be blocked"
    assert result.sha == "", "empty tree should return empty SHA"

    # Assert the warning was logged with the run_id and step_id.
    caplog.clear()
    result = await commit_in_sandbox(
        sb, "test: no changes", ectx, step, audit_operation=None
    )

    # Capture the warning message and verify it includes run_id and step_id.
    assert any(
        "no changes staged" in record.message
        and ectx.run_id in record.message
        and step.agent_id in record.message
        for record in caplog.records
        if record.levelname == "WARNING"
    ), (
        f"Expected warning with 'no changes staged', run_id={ectx.run_id}, "
        f"and step_id={step.agent_id} but got: {[r.message for r in caplog.records]}"
    )


# ---------------------------------------------------------------------------
# Private helper — assert a string is absent from all reachable git objects
# ---------------------------------------------------------------------------


def _assert_secret_unreachable_from_git(repo_root: Path, secret: str) -> None:
    """Assert that *secret* does not appear in any git commit reachable from any ref.

    We grep the text of every commit object reachable from all refs.  A blocked
    commit leaves NO new commit object, so the secret cannot be reached via the
    normal ``git log`` graph.  This does NOT check loose object files (a packed
    or loose object that was never committed would not be reachable from any ref
    either, so we rely on the ``--all`` walk covering the reachable closure).
    """
    try:
        # git log --all -p streams the full diff of every reachable commit.
        result = subprocess.run(
            ["git", "log", "--all", "-p", "--no-color"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
        history_text = result.stdout
    except subprocess.CalledProcessError:
        # If there are no commits at all, there is nothing to check.
        return

    assert secret not in history_text, (
        f"Secret value {secret!r} was found in git history — "
        "the blocked commit should not have created a reachable commit object."
    )
