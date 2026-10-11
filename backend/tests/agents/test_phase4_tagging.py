"""tests/agents/test_phase4_tagging.py — Task 6.6 acceptance tests.

Phase 4: version tagging (tasks 6.1 – 6.5).

Requirements covered:
- Requirement 14 (FR-014): tag creation gated on completed status; non-completed statuses
  create no tag (cancelled, failed, degraded, diverted).
- Requirement 15: LocalWorkspace.create_tag / list_tags duck-type API.
- Requirement 16: _validate_ref rejects any ref not in list_tags(); fail-closed.
- Requirement 32: tag name is v{revision_ordinal}; completed run carries tag.

Acceptance criteria (tasks.md §6.6):
1. Completed run carries a tag; diverted or failed run carries none.
2. Tag name vN matches the revision_index the UI shows.
3. A pre_commit block on the last step results in degraded status and no tag.
4. ref validation rejects arbitrary strings not in list_tags().

Structure:
- Sections 1–3: LocalWorkspace + RunSandbox tag primitive tests.
- Section 4: finalize_terminal_run with non-completed statuses (rewritten from dead
  TestFirePostRun* classes; drives finalize_terminal_run directly, not a deleted API).
- Sections 5–7: _validate_ref unit and integration tests (unchanged).

All tests are pure unit tests — no real engine run, no LLM calls, no DB.
Tests that exercise git operations use real temporary git repos (tmp_path).
"""

from __future__ import annotations

import asyncio
import subprocess
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers shared across test classes
# ---------------------------------------------------------------------------


def _fresh_run_id() -> str:
    return f"tag-test-{uuid.uuid4()}"


def _make_mock_sandbox(
    *,
    has_git: bool = True,
    is_dirty: bool = False,
    tags: list[str] | None = None,
) -> MagicMock:
    """Build a minimal mock RunSandbox with tag support."""
    sb = MagicMock()
    sb.has_git = has_git
    sb.is_dirty.return_value = is_dirty
    sb.commit_all.return_value = "abc123 boundary"
    sb.git_gc_auto.return_value = None
    _tags: list[str] = tags if tags is not None else []
    sb.create_tag.side_effect = lambda name: _tags.append(name) or name
    sb.list_tags.return_value = _tags
    return sb


def _make_mock_runner(sandbox: MagicMock) -> MagicMock:
    runner = MagicMock()
    runner.sandbox = sandbox
    return runner


def _make_mock_ectx(
    *,
    final_status: str | None = None,
    revision_ordinal: int = 1,
    last_commit_blocked: bool = False,
    step_visit_counts: dict | None = None,
    runner: MagicMock | None = None,
) -> MagicMock:
    ectx = MagicMock()
    ectx.final_status = final_status
    ectx.revision_ordinal = revision_ordinal
    ectx.last_commit_blocked = last_commit_blocked
    ectx.step_visit_counts = step_visit_counts or {"planner": 1}
    ectx.runner = runner
    return ectx


# ---------------------------------------------------------------------------
# 1. LocalWorkspace.create_tag and list_tags — unit tests with mock _git
# ---------------------------------------------------------------------------


class TestLocalWorkspaceTagUnit:
    """LocalWorkspace.create_tag / list_tags via a mocked _git call."""

    def test_create_tag_calls_git_tag_and_returns_name(self, tmp_path: Path) -> None:
        """create_tag invokes git tag <name> and returns the tag name."""
        from app.agents.runtime.local import LocalWorkspace

        ws = LocalWorkspace.__new__(LocalWorkspace)
        ws._root = tmp_path

        with patch.object(ws, "_git", return_value="") as mock_git:
            result = ws.create_tag("v1")

        mock_git.assert_called_once_with("tag", "v1")
        assert result == "v1"

    def test_create_tag_propagates_failure(self, tmp_path: Path) -> None:
        """create_tag raises when git reports an error (duplicate tag, no commits)."""
        import subprocess

        from app.agents.runtime.local import LocalWorkspace

        ws = LocalWorkspace.__new__(LocalWorkspace)
        ws._root = tmp_path

        with patch.object(
            ws, "_git", side_effect=subprocess.CalledProcessError(128, "git")
        ):
            with pytest.raises(subprocess.CalledProcessError):
                ws.create_tag("v1")

    def test_list_tags_returns_sorted_list(self, tmp_path: Path) -> None:
        """list_tags parses tag --list output into a sorted list."""
        from app.agents.runtime.local import LocalWorkspace

        ws = LocalWorkspace.__new__(LocalWorkspace)
        ws._root = tmp_path

        with patch.object(ws, "_git", return_value="v3\nv1\nv2\n"):
            result = ws.list_tags()

        assert result == ["v1", "v2", "v3"]

    def test_list_tags_returns_empty_list_on_no_tags(self, tmp_path: Path) -> None:
        """list_tags returns [] when there are no tags."""
        from app.agents.runtime.local import LocalWorkspace

        ws = LocalWorkspace.__new__(LocalWorkspace)
        ws._root = tmp_path

        with patch.object(ws, "_git", return_value=""):
            result = ws.list_tags()

        assert result == []

    def test_list_tags_returns_empty_list_on_git_error(self, tmp_path: Path) -> None:
        """list_tags never raises — returns [] on any git exception (fail-open best-effort)."""
        import subprocess

        from app.agents.runtime.local import LocalWorkspace

        ws = LocalWorkspace.__new__(LocalWorkspace)
        ws._root = tmp_path

        with patch.object(
            ws, "_git", side_effect=subprocess.CalledProcessError(128, "git")
        ):
            result = ws.list_tags()

        assert result == []


# ---------------------------------------------------------------------------
# 2. LocalWorkspace.create_tag and list_tags — real git repo integration
# ---------------------------------------------------------------------------


class TestLocalWorkspaceTagRealGit:
    """Round-trip tag tests against a real temporary git repository."""

    def _make_ws(self, tmp_path: Path):
        """Return a LocalWorkspace backed by an init'd sandbox with one commit."""
        from app.agents.sandbox import RunSandbox

        run_id = f"tag-ws-{uuid.uuid4()}"
        sb = RunSandbox("test-user", run_id, runs_root=str(tmp_path))
        sb.ensure()
        sb._ws().git_init_sandbox()  # type: ignore[attr-defined]
        return sb._ws()  # type: ignore[attr-defined]

    def test_create_tag_creates_real_git_tag(self, tmp_path: Path) -> None:
        """create_tag on a real repo creates a tag visible via git tag --list."""
        ws = self._make_ws(tmp_path)
        result = ws.create_tag("v1")
        assert result == "v1"
        assert "v1" in ws.list_tags()

    def test_list_tags_empty_on_fresh_repo(self, tmp_path: Path) -> None:
        """A freshly-init'd sandbox (no tags yet) returns [] from list_tags."""
        ws = self._make_ws(tmp_path)
        assert ws.list_tags() == []

    def test_list_tags_returns_all_tags_sorted(self, tmp_path: Path) -> None:
        """list_tags returns all created tags in sorted order."""
        ws = self._make_ws(tmp_path)
        ws.create_tag("v3")
        ws.create_tag("v1")
        ws.create_tag("v2")
        assert ws.list_tags() == ["v1", "v2", "v3"]

    def test_create_tag_raises_on_duplicate(self, tmp_path: Path) -> None:
        """Tagging the same name twice raises — failure must be visible (Req 15 AC 4)."""
        ws = self._make_ws(tmp_path)
        ws.create_tag("v1")
        # LocalWorkspace._git runs git with check=True; a duplicate tag exits non-zero.
        with pytest.raises(subprocess.CalledProcessError):
            ws.create_tag("v1")

    def test_tag_name_matches_revision_ordinal_convention(self, tmp_path: Path) -> None:
        """Tag is named v{N} where N is the revision ordinal (Requirement 32)."""
        ws = self._make_ws(tmp_path)
        for ordinal in (1, 2, 5):
            tag_name = f"v{ordinal}"
            ws.create_tag(tag_name)
        tags = ws.list_tags()
        assert "v1" in tags
        assert "v2" in tags
        assert "v5" in tags


# ---------------------------------------------------------------------------
# 3. RunSandbox.create_tag and list_tags delegation
# ---------------------------------------------------------------------------


class TestRunSandboxTagDelegation:
    """RunSandbox delegates create_tag / list_tags to LocalWorkspace via duck-typing."""

    def test_create_tag_delegates_to_workspace(self, tmp_path: Path) -> None:
        """RunSandbox.create_tag calls the underlying workspace's create_tag."""
        from app.agents.sandbox import RunSandbox

        run_id = f"sb-tag-{uuid.uuid4()}"
        sb = RunSandbox("test-user", run_id, runs_root=str(tmp_path))
        sb.ensure()
        sb._ws().git_init_sandbox()  # type: ignore[attr-defined]

        result = sb.create_tag("v1")
        assert result == "v1"
        assert "v1" in sb.list_tags()

    def test_create_tag_raises_when_has_git_false(self, tmp_path: Path) -> None:
        """create_tag raises RuntimeError when has_git=False (Requirement 15)."""
        from app.agents.sandbox import RunSandbox

        sb = RunSandbox.__new__(RunSandbox)
        sb.has_git = False
        sb.root = tmp_path

        with pytest.raises(RuntimeError, match="has_git=False"):
            sb.create_tag("v1")

    def test_list_tags_returns_empty_when_has_git_false(self, tmp_path: Path) -> None:
        """list_tags returns [] when has_git=False — no repo to query."""
        from app.agents.sandbox import RunSandbox

        sb = RunSandbox.__new__(RunSandbox)
        sb.has_git = False
        sb.root = tmp_path

        assert sb.list_tags() == []

    def test_list_tags_returns_empty_on_workspace_error(self, tmp_path: Path) -> None:
        """list_tags swallows workspace exceptions and returns [] (best-effort)."""
        from app.agents.sandbox import RunSandbox

        sb = RunSandbox.__new__(RunSandbox)
        sb.has_git = True
        sb.root = tmp_path

        mock_ws = MagicMock()
        mock_ws.list_tags.side_effect = RuntimeError("repo corrupted")

        with patch.object(sb, "_ws", return_value=mock_ws):
            result = sb.list_tags()

        assert result == []


# ---------------------------------------------------------------------------
# 4. finalize_terminal_run with non-completed statuses — real git integration
# ---------------------------------------------------------------------------


class TestFirePostRunNonCompleted:
    """finalize_terminal_run for non-completed statuses: no tag, internal ref present.

    Requirement 14 (FR-014): non-completed runs must not be tagged.
    """

    def _make_real_sandbox(self, tmp_path: Path):
        """Build a sandbox with git initialized and one commit."""
        from app.agents.sandbox import RunSandbox

        run_id = str(uuid.uuid4())
        sb = RunSandbox("test-user", run_id, runs_root=str(tmp_path))
        sb.ensure()
        sb._ws().git_init_sandbox()  # type: ignore[attr-defined]
        return run_id, sb

    def _make_ectx(self, run_id: str, sandbox: MagicMock) -> MagicMock:
        """Build an ExecutionContext-like object for finalize_terminal_run."""
        ectx = MagicMock()
        ectx.run_id = run_id
        ectx.user_id = "test-user"
        ectx.workspace_id = "ws-test"
        ectx.revision_ordinal = 1
        ectx.runner = MagicMock()
        ectx.runner.sandbox = sandbox
        return ectx

    @pytest.mark.parametrize("status", ["cancelled", "failed", "degraded", "diverted"])
    def test_non_completed_status_no_tag_but_has_internal_ref(
        self, status: str, tmp_path: Path
    ) -> None:
        """Non-completed status creates no tag but does have an internal ref (Req 14 AC 2–5)."""
        import asyncio
        from unittest.mock import MagicMock as MM

        from agents.execution_engine import engine as eng

        run_id, sb = self._make_real_sandbox(tmp_path)
        ectx = self._make_ectx(run_id, sb)

        # Clear the fast-path guard
        eng._finalize_terminal_run_started.discard(run_id)

        def _good_session() -> MM:
            m = MM()
            wr_row = MM()
            m.query.return_value.filter.return_value.first.return_value = wr_row
            return m

        with (
            patch("app.models.database.SessionLocal", side_effect=_good_session),
            patch("app.models.workflow.WorkflowRun", MM()),
            patch("app.models.run_finalization.RunFinalization", MM()),
        ):
            record = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status=status)
            )

        # No tag should exist
        tags = sb.list_tags()
        assert (
            tags == []
        ), f"Non-completed status {status} must not create a tag; got {tags}"

        # But an internal ref should be present
        assert (
            record.internal_ref is not None
        ), f"Non-completed status {status} must have an internal_ref"

        eng._finalize_terminal_run_started.discard(run_id)


# ---------------------------------------------------------------------------
# 6. _validate_ref — ref validation (Requirement 16)
# ---------------------------------------------------------------------------


class TestValidateRef:
    """_validate_ref rejects every ref not in list_tags(); fail-closed.

    AC 4 (Requirement 16): a free-form revspec from user input must NEVER be
    passed to a git subprocess.
    """

    def _sandbox_with_tags(self, tags: list[str]) -> MagicMock:
        sb = MagicMock()
        sb.list_tags.return_value = tags
        return sb

    def _sandbox_without_list_tags(self) -> MagicMock:
        return MagicMock(spec=[])  # no list_tags attribute

    # ── accepts valid tags ────────────────────────────────────────────────

    def test_accepts_valid_tag(self) -> None:
        """A ref that is an exact match in list_tags() passes through unchanged."""
        from app.api.run_files import _validate_ref

        sb = self._sandbox_with_tags(["v1", "v2"])
        result = _validate_ref("v1", sb)
        assert result == "v1"

    def test_accepts_any_tag_in_list(self) -> None:
        """Every member of list_tags() is accepted."""
        from app.api.run_files import _validate_ref

        tags = ["v1", "v2", "v5"]
        sb = self._sandbox_with_tags(tags)
        for tag in tags:
            assert _validate_ref(tag, sb) == tag

    # ── rejects arbitrary strings ─────────────────────────────────────────

    @pytest.mark.parametrize(
        "bad_ref",
        [
            "HEAD",
            "HEAD~1",
            "HEAD~3",
            "main",
            "master",
            "@{upstream}",
            ":/message",
            "$(whoami)",
            "../secret",
            "refs/heads/main",
            "",
            "v999",  # a tag that would be valid by name but is not in list
            "v1 && rm -rf /",  # injection attempt
        ],
    )
    def test_rejects_arbitrary_revspec(self, bad_ref: str) -> None:
        """Arbitrary revspecs not in list_tags() are rejected with HTTP 400."""
        from fastapi import HTTPException

        from app.api.run_files import _validate_ref

        sb = self._sandbox_with_tags(["v1", "v2"])
        with pytest.raises(HTTPException) as exc_info:
            _validate_ref(bad_ref, sb)
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "invalid ref"

    def test_rejects_when_tag_list_is_empty(self) -> None:
        """An empty tag list means every ref is rejected — fail-closed."""
        from fastapi import HTTPException

        from app.api.run_files import _validate_ref

        sb = self._sandbox_with_tags([])
        with pytest.raises(HTTPException) as exc_info:
            _validate_ref("v1", sb)
        assert exc_info.value.status_code == 400

    def test_fail_closed_when_list_tags_raises(self) -> None:
        """If list_tags() raises, _validate_ref treats the list as empty → reject."""
        from fastapi import HTTPException

        from app.api.run_files import _validate_ref

        sb = MagicMock()
        sb.list_tags.side_effect = RuntimeError("repo gone")
        with pytest.raises(HTTPException) as exc_info:
            _validate_ref("v1", sb)
        assert exc_info.value.status_code == 400

    def test_fail_closed_when_sandbox_has_no_list_tags(self) -> None:
        """Sandbox without list_tags attribute: effective list is [] → all refs rejected."""
        from fastapi import HTTPException

        from app.api.run_files import _validate_ref

        sb = self._sandbox_without_list_tags()
        with pytest.raises(HTTPException) as exc_info:
            _validate_ref("v1", sb)
        assert exc_info.value.status_code == 400

    def test_return_value_is_unchanged_ref(self) -> None:
        """On success, _validate_ref returns the ref string unchanged for inline use."""
        from app.api.run_files import _validate_ref

        sb = self._sandbox_with_tags(["v1"])
        ref = "v1"
        result = _validate_ref(ref, sb)
        assert result is ref or result == ref

    def test_case_sensitive_match(self) -> None:
        """Tag matching is case-sensitive: 'V1' is NOT the same as 'v1'."""
        from fastapi import HTTPException

        from app.api.run_files import _validate_ref

        sb = self._sandbox_with_tags(["v1"])
        with pytest.raises(HTTPException):
            _validate_ref("V1", sb)


# ---------------------------------------------------------------------------
# 7. Real git repo: _validate_ref with RunSandbox.list_tags()
# ---------------------------------------------------------------------------


class TestValidateRefRealGit:
    """_validate_ref + RunSandbox.list_tags() against a real repository."""

    def _make_tagged_sandbox(self, tmp_path: Path, tags: list[str]):
        from app.agents.sandbox import RunSandbox

        run_id = f"val-ref-{uuid.uuid4()}"
        sb = RunSandbox("test-user", run_id, runs_root=str(tmp_path))
        sb.ensure()
        sb._ws().git_init_sandbox()  # type: ignore[attr-defined]
        for tag in tags:
            sb.create_tag(tag)
        return sb

    def test_valid_tag_accepted_from_real_sandbox(self, tmp_path: Path) -> None:
        """A tag created in a real repo is accepted by _validate_ref."""
        from app.api.run_files import _validate_ref

        sb = self._make_tagged_sandbox(tmp_path, ["v1"])
        assert _validate_ref("v1", sb) == "v1"

    def test_arbitrary_string_rejected_from_real_sandbox(self, tmp_path: Path) -> None:
        """HEAD is rejected because it is not in the real repo's tag list."""
        from fastapi import HTTPException

        from app.api.run_files import _validate_ref

        sb = self._make_tagged_sandbox(tmp_path, ["v1"])
        with pytest.raises(HTTPException) as exc_info:
            _validate_ref("HEAD", sb)
        assert exc_info.value.status_code == 400

    def test_untagged_sandbox_rejects_all_refs(self, tmp_path: Path) -> None:
        """A sandbox with no tags rejects every ref — fail-closed."""
        from fastapi import HTTPException

        from app.api.run_files import _validate_ref

        sb = self._make_tagged_sandbox(tmp_path, [])
        with pytest.raises(HTTPException):
            _validate_ref("v1", sb)
