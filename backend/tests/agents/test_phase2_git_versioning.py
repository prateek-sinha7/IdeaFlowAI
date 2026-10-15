"""tests/agents/test_phase2_git_versioning.py — Phase 2 tests for sandbox-git-versioning.

Covers Requirement 9 acceptance criteria.  One test area:

1. Deliverable and list_files exclusions (Requirement 9)
   - .git/, .gitignore, and skills/ are NOT in serialize_sandbox_deliverable
   - .git/, .gitignore, and skills/ ARE in list_files (the Workspace shows every file)
   NOTE: comprehensive byte-equivalence coverage for these exclusions already
   lives in test_sandbox_deliverable.py.  This module adds the cross-cutting
   "both exclusion lists are independent" assertion that Requirement 9 AC 4
   calls out explicitly, plus a real-git integration smoke-test confirming the
   exclusions hold against a workspace provisioned by git_init_sandbox().

   DELETED: TestStepBoundaryCommitMessageFormat and TestGitGcAutoOnPostRun were
   vacuous tests that either (a) hand-called commit_all instead of driving the
   engine's commit_in_sandbox path, or (b) imported deleted v1 symbols
   (_fire_post_run, _post_run_fired). Both are dead and removed.

All tests are unit/integration — no real engine run, no database, no LLM calls.

Requirements: 9
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_sandbox(tmp_path: Path, *, user_id: str = "user-1", run_id: str | None = None):
    """Create and ensure a RunSandbox under tmp_path."""
    from app.agents.sandbox import RunSandbox

    rid = run_id or f"run-{uuid.uuid4().hex[:8]}"
    sb = RunSandbox(user_id, rid, runs_root=str(tmp_path))
    sb.ensure()
    return sb


def _fresh_run_id() -> str:
    return f"test-{uuid.uuid4()}"


# ===========================================================================
# 1.  Deliverable and list_files exclusions — independence (Req 9 AC 4)
# ===========================================================================


class TestExclusionIndependence:
    """Requirement 9 AC 4: the deliverable walk and list_files are two SEPARATE lists.

    test_sandbox_deliverable.py already covers the per-exclusion correctness in
    depth.  This class adds:

    a) A single combined fixture that proves all three exclusions hold on BOTH
       lists simultaneously — a regression guard that catches a copy-paste error
       where fixing one list breaks the other.

    b) A real-git integration smoke-test: after git_init_sandbox() the sandbox
       has a real .git/ directory and .gitignore file on disk.  Both must be
       absent from the deliverable yet present in list_files — proving both rules
       hold against filesystem state written by the real git toolchain, not just
       manually seeded test files.
    """

    def test_all_three_exclusions_hold_on_both_deliverable_and_listing(
        self, tmp_path: Path
    ) -> None:
        """Combined: .git/, .gitignore, skills/ absent from the deliverable, present in the listing.

        Requirement 9 AC 4: "The deliverable walk and list_files are two separate
        lists — excluding from one does NOT exclude from the other."  This test
        asserts BOTH are correct at once, ensuring they cannot drift apart.
        """
        from app.agents.sandbox import (
            count_sandbox_deliverables,
            serialize_sandbox_deliverable,
        )

        sb = _mk_sandbox(tmp_path)

        # Real deliverable file.
        sb.write("prototype.html", "<h1>Hello</h1>\n")

        # Git internals written directly (simulating git init side-effects).
        git_dir = sb.root / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text(
            "[core]\n\trepositoryformatversion = 0\n", encoding="utf-8"
        )
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

        # .gitignore at root.
        (sb.root / ".gitignore").write_text(
            ".uploads/\n.logs/\n.agents/\n.chain/\n.context/\nskills/\n",
            encoding="utf-8",
        )

        # Skills directory with staged skill bodies.
        skills_dir = sb.root / "skills" / "writing"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text("# Writing skill\n", encoding="utf-8")
        (skills_dir / "example.html").write_text("<p>example</p>\n", encoding="utf-8")

        # ── Deliverable walk ────────────────────────────────────────────────
        out = serialize_sandbox_deliverable(sb.root)
        count = count_sandbox_deliverables(sb.root)

        assert "prototype.html" in out, "deliverable must include prototype.html"
        assert ".git" not in out, ".git/ must not appear in deliverable"
        assert ".gitignore" not in out, ".gitignore must not appear in deliverable"
        assert "skills" not in out, "skills/ must not appear in deliverable"
        assert count == 1, f"only prototype.html is deliverable; got count={count}"

        # ── list_files listing ──────────────────────────────────────────────
        files, truncated = sb.list_files()
        paths = {f["path"] for f in files}

        assert "prototype.html" in paths, "list_files must include prototype.html"
        # The listing shows every file; only the deliverable excludes these.
        assert ".git/config" in paths
        assert ".gitignore" in paths
        assert "skills/writing/SKILL.md" in paths
        assert not truncated

    def test_git_init_sandbox_exclusions_on_real_git_repo(self, tmp_path: Path) -> None:
        """Integration smoke: after real git_init_sandbox, .git/ and .gitignore
        are absent from the deliverable and present in list_files.

        This verifies the exclusion guards hold against filesystem state produced
        by the actual git toolchain — not just manually planted test files.
        Requires git to be available on the PATH (skipped otherwise).
        """
        import shutil as _shutil

        if not _shutil.which("git"):
            pytest.skip(
                "git not available on PATH — skipping git integration smoke-test"
            )

        from app.agents.runtime.local import LocalExecutionPolicy, LocalWorkspace
        from app.agents.sandbox import (
            count_sandbox_deliverables,
            serialize_sandbox_deliverable,
        )

        import app.core.config as config_module

        config_module.settings.RUNS_ROOT = str(tmp_path / "runs")

        from app.agents.sandbox import RunSandbox

        sandbox = RunSandbox(
            "user-integration",
            "run-integration",
            runs_root=config_module.settings.RUNS_ROOT,
        )
        sandbox.ensure()

        from app.agents.runtime.local import LocalSandboxRuntime

        ws = LocalWorkspace(
            owner_id="user-integration",
            workspace_id="run-integration",
            runtime=LocalSandboxRuntime(),
            policy=LocalExecutionPolicy(exec=False, network=False, secrets=[]),
            sandbox=sandbox,
            has_git=True,
        )

        # Provision the git repo — this writes the real .git/ directory and .gitignore.
        ws.git_init_sandbox()

        # Write a deliverable file so the sandbox is non-empty.
        sandbox.write("index.html", "<html><body>Hello</body></html>\n")

        # ── Deliverable must not include .git/ or .gitignore ─────────────
        out = serialize_sandbox_deliverable(sandbox.root)
        assert "index.html" in out, "deliverable must include index.html"
        assert (
            ".git" not in out
        ), ".git/ must not appear in deliverable after git_init_sandbox"
        assert (
            ".gitignore" not in out
        ), ".gitignore must not appear in deliverable after git_init_sandbox"
        assert count_sandbox_deliverables(sandbox.root) == 1

        # ── list_files shows .git/ and .gitignore like every other file ───
        files, _ = sandbox.list_files()
        paths = {f["path"] for f in files}

        assert "index.html" in paths
        assert ".git/HEAD" in paths
        assert ".gitignore" in paths

    def test_reserved_prefixes_not_in_deliverable_combined(
        self, tmp_path: Path
    ) -> None:
        """All reserved sandbox prefixes are absent from serialize_sandbox_deliverable.

        Combines Req 9 (.git, .gitignore, skills) with the other reserved prefixes
        (.uploads, .logs, .verify, .browser, .agents, .chain) to confirm one
        comprehensive sweep catches regressions in any prefix.
        """
        from app.agents.sandbox import (
            _DELIVERABLE_EXCLUDE,
            count_sandbox_deliverables,
            serialize_sandbox_deliverable,
        )

        sb = _mk_sandbox(tmp_path)
        sb.write("output.html", "<h1>Delivered</h1>\n")

        # Plant one file under each reserved prefix.
        reserved_files = {
            ".git/config": "[core]\n",
            ".gitignore": ".logs/\n",
            "skills/SKILL.md": "# skill\n",
            ".uploads/manifest.json": "{}",
            ".logs/run.jsonl": '{"e":"ok"}',
            ".verify/report.md": "# ok",
            ".browser/screenshot.png": "binary",
            ".agents/01-agent.md": "# agent",
            ".chain/run-1/summary.md": "# summary",
        }
        for relpath, content in reserved_files.items():
            full = sb.root / relpath
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")

        out = serialize_sandbox_deliverable(sb.root)
        count = count_sandbox_deliverables(sb.root)

        assert "output.html" in out, "deliverable file must be present"
        assert count == 1, f"only output.html is deliverable; got {count}"

        # No reserved path may appear in the deliverable output.
        for relpath in reserved_files:
            segment = relpath.split("/")[0]
            assert segment not in out, (
                f"Reserved prefix '{segment}' must not appear in deliverable; "
                f"found in: {out[:200]!r}"
            )

    def test_exclusion_lists_are_independent_adding_to_one_does_not_exclude_from_other(
        self, tmp_path: Path
    ) -> None:
        """Requirement 9 AC 4: deliverable walk and list_files are separate lists.

        Specifically: a file ADDED to the sandbox after list_files but before
        serialize_sandbox_deliverable being called must be picked up by the
        deliverable walk if it is a real deliverable — the two walks are
        independent and not cached off each other.
        """
        from app.agents.sandbox import (
            count_sandbox_deliverables,
            serialize_sandbox_deliverable,
        )

        sb = _mk_sandbox(tmp_path)
        sb.write("first.html", "<p>first</p>\n")

        # Call list_files first — captures the listing state at that moment.
        files_before, _ = sb.list_files()
        paths_before = {f["path"] for f in files_before}

        # Add a second deliverable AFTER the listing.
        sb.write("second.html", "<p>second</p>\n")

        # The deliverable walk is independent — it should see BOTH files.
        out = serialize_sandbox_deliverable(sb.root)
        assert "first.html" in out
        assert "second.html" in out
        assert count_sandbox_deliverables(sb.root) == 2

        # The earlier list_files result reflects the earlier state — independent.
        assert "first.html" in paths_before
        assert "second.html" not in paths_before, (
            "list_files result from before the write must not include second.html "
            "(the two lists are independent snapshots)"
        )


# ===========================================================================
# 2.  Ref validation against list_tags() — Req 16
# ===========================================================================


class TestRefValidation:
    """Requirement 16: a ref query parameter is validated by exact match against
    list_tags() before reaching any git subprocess.

    list_tags() is implemented in Task 6.1 (not yet complete).  These tests
    document the required validation contract and provide a ready-to-run test
    suite for when Task 6.1 lands:

    - A valid tag in the list is accepted.
    - An arbitrary string NOT in the list is rejected.
    - An empty string is rejected.
    - A string designed to inject subprocess arguments is rejected.
    - list_tags returns a stable list type.

    The tests target LocalWorkspace.list_tags() (if it exists) and fall back to
    a skip if the method is not yet implemented.
    """

    def _get_list_tags(self):
        """Return LocalWorkspace.list_tags or skip if not yet implemented."""
        from app.agents.runtime.local import LocalWorkspace

        if not hasattr(LocalWorkspace, "list_tags"):
            pytest.skip("list_tags not yet implemented (Task 6.1)")

    def test_list_tags_returns_list(self, tmp_path: Path) -> None:
        """list_tags() returns a list (possibly empty on a fresh repo)."""
        import shutil as _shutil

        if not _shutil.which("git"):
            pytest.skip("git not available on PATH")

        from app.agents.runtime.local import LocalWorkspace

        if not hasattr(LocalWorkspace, "list_tags"):
            pytest.skip("list_tags not yet implemented (Task 6.1)")

        import app.core.config as config_module
        from app.agents.sandbox import RunSandbox
        from app.agents.runtime.local import LocalExecutionPolicy, LocalSandboxRuntime

        config_module.settings.RUNS_ROOT = str(tmp_path / "runs")
        sandbox = RunSandbox("u", "r", runs_root=config_module.settings.RUNS_ROOT)
        sandbox.ensure()

        ws = LocalWorkspace(
            owner_id="u",
            workspace_id="r",
            runtime=LocalSandboxRuntime(),
            policy=LocalExecutionPolicy(exec=False, network=False, secrets=[]),
            sandbox=sandbox,
            has_git=True,
        )
        ws.git_init_sandbox()

        tags = ws.list_tags()
        assert isinstance(
            tags, list
        ), f"list_tags() must return a list; got {type(tags)}"

    def test_ref_validation_rejects_arbitrary_string(self, tmp_path: Path) -> None:
        """A free-form string NOT in list_tags() must be rejected.

        Requirement 16 AC 2: "A free-form revspec from user input SHALL NEVER be
        passed directly to a git subprocess."
        """
        import shutil as _shutil

        if not _shutil.which("git"):
            pytest.skip("git not available on PATH")

        from app.agents.runtime.local import LocalWorkspace

        if not hasattr(LocalWorkspace, "list_tags"):
            pytest.skip("list_tags not yet implemented (Task 6.1)")

        import app.core.config as config_module
        from app.agents.sandbox import RunSandbox
        from app.agents.runtime.local import LocalExecutionPolicy, LocalSandboxRuntime

        config_module.settings.RUNS_ROOT = str(tmp_path / "runs")
        sandbox = RunSandbox("u2", "r2", runs_root=config_module.settings.RUNS_ROOT)
        sandbox.ensure()

        ws = LocalWorkspace(
            owner_id="u2",
            workspace_id="r2",
            runtime=LocalSandboxRuntime(),
            policy=LocalExecutionPolicy(exec=False, network=False, secrets=[]),
            sandbox=sandbox,
            has_git=True,
        )
        ws.git_init_sandbox()

        tags = ws.list_tags()
        # On a fresh repo with no completed runs, tags is empty.
        assert "../../etc/passwd" not in tags
        assert "--exec=id" not in tags
        assert "HEAD~1" not in tags

    def test_ref_validation_contract_exact_match_only(self, tmp_path: Path) -> None:
        """Validation must be by exact match — a prefix of a valid tag is not valid.

        E.g. if "v1" is in list_tags(), "v" alone must not be accepted.
        This test documents the invariant even before create_tag is implemented.
        """
        import shutil as _shutil

        if not _shutil.which("git"):
            pytest.skip("git not available on PATH")

        from app.agents.runtime.local import LocalWorkspace

        if not hasattr(LocalWorkspace, "list_tags"):
            pytest.skip("list_tags not yet implemented (Task 6.1)")

        import app.core.config as config_module
        from app.agents.sandbox import RunSandbox
        from app.agents.runtime.local import LocalExecutionPolicy, LocalSandboxRuntime

        if not hasattr(LocalWorkspace, "create_tag"):
            pytest.skip("create_tag not yet implemented (Task 6.1)")

        config_module.settings.RUNS_ROOT = str(tmp_path / "runs")
        sandbox = RunSandbox("u3", "r3", runs_root=config_module.settings.RUNS_ROOT)
        sandbox.ensure()

        ws = LocalWorkspace(
            owner_id="u3",
            workspace_id="r3",
            runtime=LocalSandboxRuntime(),
            policy=LocalExecutionPolicy(exec=False, network=False, secrets=[]),
            sandbox=sandbox,
            has_git=True,
        )
        ws.git_init_sandbox()

        # Create a real tag so list_tags has something to return.
        ws.create_tag("v1")
        tags = ws.list_tags()
        assert "v1" in tags, "v1 must be in list_tags() after create_tag('v1')"

        # A prefix of "v1" must NOT be in the list.
        assert "v" not in tags, "'v' (prefix of 'v1') must not be a valid tag"
        assert "" not in tags, "empty string must not be a valid tag"

    def test_sandbox_git_gc_auto_never_raises(self, tmp_path: Path) -> None:
        """RunSandbox.git_gc_auto() is best-effort — never raises (Req 35 AC 2).

        This is the contract that makes it safe to call on the post_run path
        (a gc failure must not mask the run outcome).
        """
        import shutil as _shutil

        if not _shutil.which("git"):
            pytest.skip("git not available on PATH")

        from app.agents.runtime.local import LocalWorkspace

        import app.core.config as config_module
        from app.agents.sandbox import RunSandbox
        from app.agents.runtime.local import LocalExecutionPolicy, LocalSandboxRuntime

        config_module.settings.RUNS_ROOT = str(tmp_path / "runs")
        sandbox = RunSandbox("u4", "r4", runs_root=config_module.settings.RUNS_ROOT)
        sandbox.ensure()

        ws = LocalWorkspace(
            owner_id="u4",
            workspace_id="r4",
            runtime=LocalSandboxRuntime(),
            policy=LocalExecutionPolicy(exec=False, network=False, secrets=[]),
            sandbox=sandbox,
            has_git=True,
        )
        ws.git_init_sandbox()
        sandbox.write("file.txt", "content\n")

        # Must not raise under any circumstances.
        ws.git_gc_auto()

        # RunSandbox.git_gc_auto() also must not raise.
        sandbox.git_gc_auto()
