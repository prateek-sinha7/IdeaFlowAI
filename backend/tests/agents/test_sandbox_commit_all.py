"""tests/agents/test_sandbox_commit_all.py — unit tests for RunSandbox.commit_all.

Tests for task 4.2 (Requirement 10 AC 5):

  1. has_git=False short-circuits immediately — returns "" without delegating.
  2. Delegation: commit_all delegates to LocalWorkspace.commit_all.
  3. Successful commit returns the SHA string and emits no warning.
  4. Empty result + .git/ absent → warning distinguishing "not a git repo".
  5. Empty result + .git/ present → warning distinguishing "nothing to commit".

All tests use monkeypatching / lightweight stubs rather than spinning up a real
git repo — the git-on-disk layer is covered by test_git_init_acceptance.py.
Requirements: 10
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sandbox(tmp_path: Path, *, has_git: bool = True):
    """Return a RunSandbox rooted under tmp_path."""
    from app.agents.sandbox import RunSandbox

    sb = RunSandbox("user-test", "run-test", runs_root=str(tmp_path), has_git=has_git)
    sb.ensure()
    return sb


# ---------------------------------------------------------------------------
# Test 1 — has_git=False returns "" without touching LocalWorkspace
# ---------------------------------------------------------------------------


def test_commit_all_returns_empty_when_has_git_false(tmp_path: Path) -> None:
    """has_git=False must short-circuit and return "" without delegating.

    Requirement 10 AC 1: commit gated on has_git.  When has_git=False the
    sandbox is not a git repo; no commit should be attempted and the return
    value must be "" (the standard "nothing committed" sentinel).
    """
    sb = _make_sandbox(tmp_path, has_git=False)

    # Patch _ws to ensure it is never called.
    with patch.object(sb, "_ws", side_effect=AssertionError("_ws must not be called when has_git=False")):
        result = sb.commit_all("step: some-agent")

    assert result == "", "has_git=False must return '' immediately"


# ---------------------------------------------------------------------------
# Test 2 — successful commit delegates to LocalWorkspace and returns its result
# ---------------------------------------------------------------------------


def test_commit_all_delegates_to_workspace_and_returns_sha(tmp_path: Path) -> None:
    """commit_all must delegate to LocalWorkspace.commit_all and return its result.

    When the workspace returns a non-empty SHA the sandbox must return it
    verbatim.  No warning should be logged.
    """
    sb = _make_sandbox(tmp_path, has_git=True)

    fake_ws = MagicMock()
    fake_ws.commit_all.return_value = "abc1234"

    with patch.object(sb, "_ws", return_value=fake_ws):
        with patch.object(type(sb), "_ws") as _ws_prop:
            # Use a simpler approach: patch _workspace directly so _ws() returns fake_ws
            sb._workspace = fake_ws
            result = sb.commit_all("step: writer-agent")

    fake_ws.commit_all.assert_called_once_with("step: writer-agent")
    assert result == "abc1234", "must return the SHA from LocalWorkspace.commit_all"


# ---------------------------------------------------------------------------
# Test 3 — empty result + .git/ absent → "not a git repo" warning
# ---------------------------------------------------------------------------


def test_commit_all_warns_not_a_git_repo_when_git_dir_missing(
    tmp_path: Path, caplog
) -> None:
    """Empty result when .git/ is absent must log a 'not a git repo' warning.

    Requirement 10 AC 5: distinguish "not a git repo" from "nothing to commit".
    When .git/ does not exist, the sandbox is not a repository at all — this is
    a provisioning failure and the warning text must reflect that.
    """
    sb = _make_sandbox(tmp_path, has_git=True)

    # .git/ does not exist — no git init was called.
    assert not (sb.root / ".git").is_dir(), "pre-condition: .git/ must not exist"

    fake_ws = MagicMock()
    fake_ws.commit_all.return_value = ""  # nothing committed
    sb._workspace = fake_ws

    with caplog.at_level(logging.WARNING, logger="app.agents.sandbox"):
        result = sb.commit_all("step: some-agent")

    assert result == ""
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("not a git repo" in m for m in warning_messages), (
        "Expected a 'not a git repo' warning when .git/ is absent; "
        f"got warnings: {warning_messages}"
    )
    # Must NOT say "nothing to commit" — the two cases must be distinct.
    assert not any("nothing to commit" in m for m in warning_messages), (
        "Must NOT emit 'nothing to commit' warning when .git/ is absent; "
        f"got warnings: {warning_messages}"
    )


# ---------------------------------------------------------------------------
# Test 4 — empty result + .git/ present → "nothing to commit" warning
# ---------------------------------------------------------------------------


def test_commit_all_warns_nothing_to_commit_when_git_dir_present(
    tmp_path: Path, caplog
) -> None:
    """Empty result when .git/ IS present must log a 'nothing to commit' warning.

    Requirement 10 AC 5: distinguish "not a git repo" from "nothing to commit".
    When .git/ exists the repository is valid; an empty commit at a step
    boundary is unusual and warrants a different warning.
    """
    sb = _make_sandbox(tmp_path, has_git=True)

    # Simulate a provisioned repo: create .git/ so the check passes.
    (sb.root / ".git").mkdir()

    fake_ws = MagicMock()
    fake_ws.commit_all.return_value = ""  # nothing to stage
    sb._workspace = fake_ws

    with caplog.at_level(logging.WARNING, logger="app.agents.sandbox"):
        result = sb.commit_all("step: no-write-agent")

    assert result == ""
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("nothing to commit" in m for m in warning_messages), (
        "Expected a 'nothing to commit' warning when .git/ is present but commit is no-op; "
        f"got warnings: {warning_messages}"
    )
    # Must NOT say "not a git repo" — the two cases must be distinct.
    assert not any("not a git repo" in m for m in warning_messages), (
        "Must NOT emit 'not a git repo' warning when .git/ is present; "
        f"got warnings: {warning_messages}"
    )


# ---------------------------------------------------------------------------
# Test 5 — successful commit emits no warning
# ---------------------------------------------------------------------------


def test_commit_all_no_warning_on_successful_commit(tmp_path: Path, caplog) -> None:
    """A successful commit (non-empty return) must not emit any warnings.

    The warning is only for the empty-result case (Req 10 AC 5). A normal
    step commit must be silent.
    """
    sb = _make_sandbox(tmp_path, has_git=True)

    fake_ws = MagicMock()
    fake_ws.commit_all.return_value = "deadbeef"
    sb._workspace = fake_ws

    with caplog.at_level(logging.WARNING, logger="app.agents.sandbox"):
        result = sb.commit_all("step: normal-agent")

    assert result == "deadbeef"
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert not warning_messages, (
        "A successful commit must not emit any warnings; "
        f"got: {warning_messages}"
    )


# ---------------------------------------------------------------------------
# Test 6 — message is forwarded verbatim to LocalWorkspace.commit_all
# ---------------------------------------------------------------------------


def test_commit_all_forwards_message_verbatim(tmp_path: Path) -> None:
    """The message argument must be forwarded verbatim to LocalWorkspace.commit_all."""
    sb = _make_sandbox(tmp_path, has_git=True)

    fake_ws = MagicMock()
    fake_ws.commit_all.return_value = "sha999"
    sb._workspace = fake_ws

    sb.commit_all("step: my-special-agent [pass 2]")
    fake_ws.commit_all.assert_called_once_with("step: my-special-agent [pass 2]")
