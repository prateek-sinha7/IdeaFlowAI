"""tests/agents/test_phase1_chain.py — Phase 1 tests for sandbox-git-versioning.

Covers three acceptance criteria from Task 3.6:

  1. ``.chain/{run_id}/`` is written on the terminal path for all five terminal
     statuses (Requirement 20 AC 1–4).

  2. ``.chain/`` is excluded from the deliverable walk and listed in
     ``list_files`` (Requirement 20 AC 5).

  3. Smoke-test that ``_is_reserved`` already blocks ``.chain/`` entries in
     ``previous_run.py`` (Requirement 21 AC 1 — the detailed tests live in
     ``test_context_providers.py``).

All tests are pure unit/integration tests — no real engine run, no database,
no LLM calls.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_sandbox(tmp_path: Path, *, user_id: str = "user-1", run_id: str = "run-1"):
    """Create and ensure a RunSandbox under tmp_path."""
    from app.agents.sandbox import RunSandbox

    sb = RunSandbox(user_id, run_id, runs_root=str(tmp_path))
    sb.ensure()
    return sb


def _write(root: Path, relpath: str, content: str = "content") -> None:
    """Write a file inside root, creating parents as needed."""
    p = root / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


# ===========================================================================
# 1. ``.chain/`` is excluded from the deliverable walk, listed in list_files
# ===========================================================================


class TestChainPrefixDeliverableExclusion:
    """Requirement 20 AC 5: .chain/ is listed but never delivered."""

    def test_is_deliverable_relpath_rejects_chain_file(self) -> None:
        """A path under .chain/ is NOT a deliverable."""
        from app.agents.sandbox import is_deliverable_relpath

        assert not is_deliverable_relpath(".chain/some-run/summary.md")
        assert not is_deliverable_relpath(".chain/")
        assert not is_deliverable_relpath(".chain/abc-123/logs/run.jsonl")

    def test_is_deliverable_relpath_accepts_normal_files(self) -> None:
        """Normal deliverable files are NOT blocked by the chain guard."""
        from app.agents.sandbox import is_deliverable_relpath

        assert is_deliverable_relpath("prototype.html")
        assert is_deliverable_relpath("src/app.py")
        assert is_deliverable_relpath("README.md")

    def test_serialize_excludes_chain_files(self, tmp_path: Path) -> None:
        """serialize_sandbox_deliverable must not include any .chain/ content."""
        from app.agents.sandbox import serialize_sandbox_deliverable

        root = tmp_path / "sandbox"
        root.mkdir()

        # Write a real deliverable and a chain file side-by-side.
        _write(root, "prototype.html", "<html>delivered</html>")
        _write(root, ".chain/run-abc/summary.md", "# Chain summary")
        _write(root, ".chain/run-abc/logs/run-abc.jsonl", '{"event":"step"}')

        out = serialize_sandbox_deliverable(root)

        assert "prototype.html" in out
        assert "<html>delivered</html>" in out
        assert ".chain" not in out
        assert "Chain summary" not in out

    def test_serialize_sentinel_when_only_chain_files(self, tmp_path: Path) -> None:
        """A sandbox containing only .chain/ content reports no deliverable."""
        from app.agents.sandbox import serialize_sandbox_deliverable

        root = tmp_path / "sandbox-chain-only"
        root.mkdir()
        _write(root, ".chain/run-xyz/summary.md", "# summary")

        assert serialize_sandbox_deliverable(root) == "(no files written)"

    def test_list_files_includes_chain_files(self, tmp_path: Path) -> None:
        """list_files MUST list .chain/ files (workspace tab shows them)."""
        sb = _mk_sandbox(tmp_path, run_id="run-list")

        # Write a deliverable and a chain file.
        sb.write("output.html", "<h1>Hello</h1>")
        chain_path = sb.root / ".chain" / "run-abc" / "summary.md"
        chain_path.parent.mkdir(parents=True, exist_ok=True)
        chain_path.write_text("# Chain summary\n", encoding="utf-8")

        files, truncated = sb.list_files()
        paths = [f["path"] for f in files]

        assert ".chain/run-abc/summary.md" in paths, (
            ".chain/ files must appear in list_files output"
        )
        assert "output.html" in paths

    def test_count_excludes_chain_files(self, tmp_path: Path) -> None:
        """count_sandbox_deliverables must not count .chain/ files."""
        from app.agents.sandbox import count_sandbox_deliverables

        root = tmp_path / "sandbox-count"
        root.mkdir()
        _write(root, "output.html", "<h1>hello</h1>")
        _write(root, ".chain/run-abc/summary.md", "# summary")
        _write(root, ".chain/run-abc/logs/trace.jsonl", '{"e":"ok"}')

        # Only output.html counts — the two .chain/ files must not.
        assert count_sandbox_deliverables(root) == 1


# ===========================================================================
# 3. .chain/ payload written for every terminal status
# ===========================================================================


class TestChainPayloadWrittenForAllTerminalStatuses:
    """Requirement 20 AC 1–4: payload written for all five terminal statuses.

    These tests call ``_write_chain_payload`` directly with a mock runner/sandbox
    so no real engine run is needed. We verify that summary.md is written and
    contains the expected status field for each of the five terminal statuses.
    """

    _TERMINAL_STATUSES = ("completed", "cancelled", "failed", "degraded", "diverted")

    def _make_ectx_with_sandbox(self, tmp_path: Path, run_id: str, status: str):
        """Build a mock ExecutionContext wired to a real RunSandbox."""
        sb = _mk_sandbox(tmp_path, run_id=run_id)

        runner = MagicMock()
        runner.sandbox = sb

        ectx = MagicMock()
        ectx.runner = runner
        ectx.final_status = status
        ectx.revision_ordinal = 1
        ectx.completed_tasks = []
        ectx.git_tag = None
        ectx.deliverable = None

        return ectx, sb

    @pytest.mark.parametrize("status", _TERMINAL_STATUSES)
    def test_chain_dir_created_for_status(self, tmp_path: Path, status: str) -> None:
        """Per-run .chain/{run_id}/ directory is created for every terminal status."""
        from agents.execution_engine.engine import _write_chain_payload

        run_id = f"run-{status}"
        ectx, sb = self._make_ectx_with_sandbox(tmp_path, run_id, status)

        _write_chain_payload(run_id, ectx)

        chain_run_dir = sb.root / ".chain" / run_id
        assert chain_run_dir.is_dir(), (
            f".chain/{run_id}/ must be created for terminal status '{status}'"
        )

    @pytest.mark.parametrize("status", _TERMINAL_STATUSES)
    def test_summary_md_written_for_status(self, tmp_path: Path, status: str) -> None:
        """summary.md is written with the correct status for every terminal status."""
        from agents.execution_engine.engine import _write_chain_payload

        run_id = f"run-summary-{status}"
        ectx, sb = self._make_ectx_with_sandbox(tmp_path, run_id, status)

        _write_chain_payload(run_id, ectx)

        summary_path = sb.root / ".chain" / run_id / "summary.md"
        assert summary_path.is_file(), (
            f"summary.md must exist in .chain/{run_id}/ for status '{status}'"
        )
        content = summary_path.read_text(encoding="utf-8")
        assert f"**status**: {status}" in content, (
            f"summary.md must record the terminal status '{status}'"
        )
        assert f"**run_id**: {run_id}" in content, (
            "summary.md must record the run_id"
        )

    @pytest.mark.parametrize("status", _TERMINAL_STATUSES)
    def test_logs_subdir_created_for_status(self, tmp_path: Path, status: str) -> None:
        """.chain/{run_id}/logs/ subdirectory is created for every terminal status."""
        from agents.execution_engine.engine import _write_chain_payload

        run_id = f"run-logs-{status}"
        ectx, sb = self._make_ectx_with_sandbox(tmp_path, run_id, status)

        _write_chain_payload(run_id, ectx)

        logs_dir = sb.root / ".chain" / run_id / "logs"
        assert logs_dir.is_dir(), (
            f".chain/{run_id}/logs/ must be created for terminal status '{status}'"
        )

    def test_payload_written_per_run_never_flat(self, tmp_path: Path) -> None:
        """Payload is per-run subdirectory — never a flat .chain/ layout.

        Writing two runs must produce .chain/run-A/ and .chain/run-B/,
        not a single flat payload that the second call would overwrite.
        """
        from agents.execution_engine.engine import _write_chain_payload

        for i, run_id in enumerate(("run-A", "run-B")):
            ectx, sb = self._make_ectx_with_sandbox(tmp_path, run_id, "completed")
            _write_chain_payload(run_id, ectx)

        # Both per-run dirs must exist under the same sandbox.
        # (Both use the same tmp_path root, different run_ids.)
        sb_a = _mk_sandbox(tmp_path, run_id="run-A")
        sb_b = _mk_sandbox(tmp_path, run_id="run-B")

        assert (sb_a.root / ".chain" / "run-A").is_dir()
        assert (sb_b.root / ".chain" / "run-B").is_dir()

    def test_writer_is_best_effort_no_sandbox(self) -> None:
        """_write_chain_payload must never raise when runner has no sandbox."""
        from agents.execution_engine.engine import _write_chain_payload

        ectx = MagicMock()
        ectx.runner = MagicMock(sandbox=None)

        # Must not raise (Requirement 20 AC 4).
        _write_chain_payload("run-no-sandbox", ectx)

    def test_writer_is_best_effort_no_runner(self) -> None:
        """_write_chain_payload must never raise when ectx has no runner."""
        from agents.execution_engine.engine import _write_chain_payload

        ectx = MagicMock()
        ectx.runner = None

        # Must not raise (Requirement 20 AC 4).
        _write_chain_payload("run-no-runner", ectx)

    def test_run_log_copied_when_present(self, tmp_path: Path) -> None:
        """If .logs/{run_id}.jsonl exists, it is copied into .chain/{run_id}/logs/."""
        from agents.execution_engine.engine import _write_chain_payload

        run_id = "run-with-log"
        ectx, sb = self._make_ectx_with_sandbox(tmp_path, run_id, "completed")

        # Seed a run log in the expected location.
        log_content = '{"event": "step_start"}\n{"event": "step_end"}\n'
        log_dir = sb.root / ".logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"{run_id}.jsonl").write_text(log_content, encoding="utf-8")

        _write_chain_payload(run_id, ectx)

        copied_log = sb.root / ".chain" / run_id / "logs" / f"{run_id}.jsonl"
        assert copied_log.is_file(), (
            "Run log must be copied into .chain/{run_id}/logs/"
        )
        assert copied_log.read_text(encoding="utf-8") == log_content

    def test_agent_transcripts_copied_when_present(self, tmp_path: Path) -> None:
        """Agent transcripts under .agents/ are copied into .chain/{run_id}/logs/."""
        from agents.execution_engine.engine import _write_chain_payload

        run_id = "run-with-agents"
        ectx, sb = self._make_ectx_with_sandbox(tmp_path, run_id, "completed")

        # Seed a transcript.
        agents_dir = sb.root / ".agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "01-my-agent.md").write_text(
            "# My Agent\n\nI did some work.\n", encoding="utf-8"
        )

        _write_chain_payload(run_id, ectx)

        copied = sb.root / ".chain" / run_id / "logs" / "01-my-agent.md"
        assert copied.is_file(), (
            ".agents/ transcript must be copied into .chain/{run_id}/logs/"
        )


# ===========================================================================
# 4. Reserved-prefix guard smoke test (Requirement 21 AC 1)
# ===========================================================================
# The full test suite for this guard lives in test_context_providers.py.
# Here we just assert that `.chain/` is recognised as reserved, giving a
# concise Phase 1 smoke test without duplicating the detailed coverage.


class TestReservedPrefixGuardSmoke:
    """Smoke-level check that .chain/ is blocked by the reserved-prefix guard."""

    def test_chain_is_reserved(self) -> None:
        from agents.capabilities.context_providers.previous_run import _is_reserved

        assert _is_reserved(".chain/"), ".chain/ must be a reserved prefix"
        assert _is_reserved(".chain/run-abc/summary.md"), (
            "nested .chain/ path must also be reserved"
        )

    def test_all_eight_prefixes_are_reserved(self) -> None:
        """All eight documented reserved prefixes are blocked."""
        from agents.capabilities.context_providers.previous_run import (
            _RESERVED_PREFIXES,
            _is_reserved,
        )

        expected = {
            ".chain/",
            ".context/",
            ".uploads/",
            ".logs/",
            ".verify/",
            ".browser/",
            ".agents/",
            "skills/",
        }
        for prefix in expected:
            assert _is_reserved(prefix), (
                f"{prefix!r} must be blocked by _is_reserved"
            )
        # No unexpected removals from the canonical set.
        assert expected <= _RESERVED_PREFIXES | {p.rstrip("/") for p in _RESERVED_PREFIXES}

    def test_normal_seed_files_are_not_reserved(self) -> None:
        from agents.capabilities.context_providers.previous_run import _is_reserved

        assert not _is_reserved("spec.md")
        assert not _is_reserved("design.md")
        assert not _is_reserved("tasks.md")
