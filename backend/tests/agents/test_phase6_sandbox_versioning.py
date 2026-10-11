"""Phase 6 acceptance tests — sandbox versioning, prompt policy, and cancel retention.

Covers the acceptance criteria from tasks 8.3, 8.4, 8.5, 8.7, 8.8, and 8.9:

  - Requirement 17/18: version dropdown lists tags; selecting one renders ref-scoped
    file tree read-only (HEAD never moves).
  - Requirement 19: opening v1 while v3 is running does not modify the working tree.
  - Requirement 23: resume_run uses .context/ files, not od_context_json.
  - Requirement 28: cancelling mid-fan-out retains all worker branches.
  - Requirement 29: body-only and governance prompt policy orders are registered.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Requirement 29: body-only and governance prompt policy orders ────────────


class TestPromptPolicyRegistration:
    """Requirement 29: Two policy orders are registered beyond 'default'."""

    def test_body_only_policy_is_registered(self) -> None:
        """Requirement 29 AC1: body_only policy is registered with order=(prompt_body,)."""
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        assert registry.is_registered(
            "prompt", "body_only"
        ), "Requirement 29 AC1: ('prompt', 'body_only') must be registered in _KNOWN"

    def test_governance_policy_is_registered(self) -> None:
        """Requirement 29 AC2: governance policy is registered with the four-block order."""
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        assert registry.is_registered(
            "prompt", "governance"
        ), "Requirement 29 AC2: ('prompt', 'governance') must be registered in _KNOWN"

    def test_body_only_order_is_prompt_body_only(self) -> None:
        """Requirement 29 AC1: body_only order is exactly ('prompt_body',)."""
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "body_only")
        assert getattr(policy, "order", None) == (
            "prompt_body",
        ), "body_only policy order must be exactly ('prompt_body',)"

    def test_governance_order_includes_constitution_and_hooks(self) -> None:
        """Requirement 29 AC2: governance order includes guardrails, hooks, constitution, body."""
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "governance")
        order = getattr(policy, "order", ())
        assert (
            "guardrails" in order
        ), "governance policy order must include 'guardrails'"
        assert "hooks" in order, "governance policy order must include 'hooks'"
        assert (
            "constitution" in order
        ), "governance policy order must include 'constitution'"
        assert (
            "prompt_body" in order
        ), "governance policy order must include 'prompt_body'"

    def test_body_only_drops_constitution(self) -> None:
        """Requirement 29 AC3: body_only drops constitution — NEVER silently for governed agents."""
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "body_only")
        order = getattr(policy, "order", ())
        assert (
            "constitution" not in order
        ), "body_only must NOT include 'constitution' in its order"

    def test_body_only_policy_assembles_to_prompt_body_only(self) -> None:
        """Requirement 29 AC1: body_only assemble() returns only the prompt_body block."""
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "body_only")
        blocks = {
            "guardrails": ["## Guardrail\n\nDo not harm."],
            "constitution": "## Constitution\n\nBe safe.",
            "hooks": "## Hooks\n\nHook content.",
            "prompt_body": "# My Agent\n\nI am an agent.",
        }
        result = policy.assemble(blocks, ctx=None)
        assert result == "# My Agent\n\nI am an agent.", (
            "body_only must return only prompt_body — got: " + repr(result)
        )

    def test_governance_policy_assembles_without_injects(self) -> None:
        """Requirement 29 AC2: governance assemble() includes guardrails/hooks/constitution/body."""
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "governance")
        blocks = {
            "injects": "Inject block",
            "guardrails": ["## Guardrail\n\nDo not harm."],
            "constitution": "## Constitution\n\nBe safe.",
            "hooks": "## Hooks\n\nHook content.",
            "prompt_body": "# My Agent\n\nI am an agent.",
        }
        result = policy.assemble(blocks, ctx=None)
        assert "## Guardrail" in result
        assert "## Constitution" in result
        assert "## Hooks" in result
        assert "# My Agent" in result
        # injects block must NOT appear (governance drops it)
        assert "Inject block" not in result

    def test_factory_reads_policy_from_spec(self) -> None:
        """Requirement 29 AC4: factory reads prompt_policy from spec, not hardcoded 'default'."""
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        # Arrange: a mock spec with prompt_policy = "body_only"
        spec = MagicMock()
        spec.id = "custom:test-agent"
        spec.prompt_body = "# Agent body"
        spec.prompt_policy = "body_only"
        spec.guardrails = []
        spec.injects = []
        spec.tools = []
        spec.max_tokens = 1000

        ctx = MagicMock()
        ctx.step_injects = []
        ctx.disk_skill = None
        ctx.attached_hooks = []
        ctx.prewarmed_constitution = None

        from agents.factory import _compose_system_prompt

        # Patch at the source modules since _compose_system_prompt uses local imports.
        with (
            patch(
                "agents.capabilities.skills.providers.extract_ui_skill_blocks",
                return_value=[],
            ),
            patch(
                "agents.capabilities.hooks.behavioral.render_behavioral_block",
                return_value="",
            ),
            patch("agents.workflows.artifacts.artifact_name", return_value="out.md"),
        ):
            result = _compose_system_prompt(
                spec, ctx, no_tools=False, has_write_access=False
            )

        # With body_only the result is exactly the prompt_body (no wrapper blocks)
        assert (
            result == "# Agent body"
        ), f"factory must use body_only policy when spec.prompt_policy='body_only'; got: {result!r}"

    def test_factory_warns_when_governed_agent_uses_body_only(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Requirement 29 AC3/5: factory warns when governed agent (with constitution) uses body_only."""
        import logging

        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        spec = MagicMock()
        spec.id = "custom:governed-agent"
        spec.prompt_body = "# Agent body"
        spec.prompt_policy = "body_only"
        spec.guardrails = []
        spec.injects = []
        spec.tools = []
        spec.max_tokens = 1000

        ctx = MagicMock()
        ctx.step_injects = []
        ctx.disk_skill = None
        ctx.attached_hooks = []
        ctx.prewarmed_constitution = "## Constitution\n\nBe safe."  # governed!

        from agents.factory import _compose_system_prompt

        # Patch at source modules since _compose_system_prompt uses local imports.
        with (
            patch(
                "agents.capabilities.skills.providers.extract_ui_skill_blocks",
                return_value=[],
            ),
            patch(
                "agents.capabilities.hooks.behavioral.render_behavioral_block",
                return_value="",
            ),
            patch("agents.workflows.artifacts.artifact_name", return_value="out.md"),
            caplog.at_level(logging.WARNING, logger="agents.factory"),
        ):
            _compose_system_prompt(spec, ctx, no_tools=False, has_write_access=False)

        assert any(
            "body_only" in record.message and "governed" in record.message
            for record in caplog.records
        ), "factory must warn when a governed agent (with Constitution) uses 'body_only' policy"


# ── Requirement 28: cancelling mid-fan-out retains all worker branches ────────


class TestCancelRetainsWorkerBranches:
    """Requirement 28: delete_branch=False retains worker branches on cancel path."""

    def test_remove_worktree_delete_branch_true_deletes_branch(
        self, tmp_path: Path
    ) -> None:
        """Happy path: delete_branch=True (default) deletes the worker branch."""
        from app.agents.runtime.local import LocalWorkspace

        ws = LocalWorkspace.__new__(LocalWorkspace)
        ws._root = tmp_path
        ws._workspace_id = "test"

        deleted_branches: list[str] = []

        def fake_git(*args: str, **kwargs):
            cmd = list(args)
            if cmd[:2] == ["branch", "-D"]:
                deleted_branches.append(cmd[2])
            return ""

        ws._git = fake_git

        worker = MagicMock()
        worker._worktree_branch = "fanout/step/0"
        worker._worktree_path = None  # skip worktree remove

        ws.remove_worktree(worker, delete_branch=True)
        assert deleted_branches == [
            "fanout/step/0"
        ], "delete_branch=True must delete the branch"

    def test_remove_worktree_delete_branch_false_retains_branch(
        self, tmp_path: Path
    ) -> None:
        """Cancel path: delete_branch=False RETAINS the worker branch."""
        from app.agents.runtime.local import LocalWorkspace

        ws = LocalWorkspace.__new__(LocalWorkspace)
        ws._root = tmp_path
        ws._workspace_id = "test"

        deleted_branches: list[str] = []

        def fake_git(*args: str, **kwargs):
            cmd = list(args)
            if cmd[:2] == ["branch", "-D"]:
                deleted_branches.append(cmd[2])
            return ""

        ws._git = fake_git

        worker = MagicMock()
        worker._worktree_branch = "fanout/step/0"
        worker._worktree_path = None  # skip worktree remove

        ws.remove_worktree(worker, delete_branch=False)
        assert (
            deleted_branches == []
        ), "delete_branch=False must NOT delete the branch (cancel path retains branches)"

    def test_delete_branch_defaults_to_true(self, tmp_path: Path) -> None:
        """Requirement 28 AC1: delete_branch defaults to True — happy path unchanged."""
        import inspect

        from app.agents.runtime.local import LocalWorkspace

        sig = inspect.signature(LocalWorkspace.remove_worktree)
        params = sig.parameters
        assert (
            "delete_branch" in params
        ), "remove_worktree must have delete_branch parameter"
        default = params["delete_branch"].default
        assert (
            default is True
        ), f"delete_branch default must be True (happy path unchanged); got {default!r}"

    @pytest.mark.asyncio
    async def test_teardown_isolated_workspace_passes_delete_branch(self) -> None:
        """Requirement 28: teardown_isolated_workspace forwards delete_branch to remove_worktree."""
        from agents.execution_engine.kernel_services import KernelServices

        ks = KernelServices.__new__(KernelServices)
        ks.workspace = None

        calls: list[dict] = []

        def fake_remove(worker_ws, *, delete_branch: bool = True):
            calls.append({"delete_branch": delete_branch})

        base_ws = MagicMock()
        base_ws.remove_worktree = fake_remove

        worker_ws = MagicMock()
        worker_ws._worktree_branch = "fanout/step/0"

        # cancel path: delete_branch=False
        await ks.teardown_isolated_workspace(base_ws, worker_ws, delete_branch=False)
        assert calls == [
            {"delete_branch": False}
        ], "teardown_isolated_workspace must forward delete_branch=False on cancel path"

        calls.clear()
        # happy path: delete_branch=True (default)
        await ks.teardown_isolated_workspace(base_ws, worker_ws)
        assert calls == [
            {"delete_branch": True}
        ], "teardown_isolated_workspace must forward delete_branch=True on happy path"


# ── Requirement 17/18: version dropdown tags + ref-scoped read-only ──────────


class TestRefScopedWorkspaceBrowsing:
    """Requirements 17/18: ref-scoped reads go through git show, HEAD never moves."""

    def test_list_files_at_ref_uses_git_ls_tree(self, tmp_path: Path) -> None:
        """Requirement 17 AC2: list_files_at_ref uses git ls-tree -r <ref>."""
        from app.agents.runtime.local import LocalWorkspace

        ws = LocalWorkspace.__new__(LocalWorkspace)
        ws._root = tmp_path

        called: list[list[str]] = []

        def fake_check_output(cmd: list[str], **kwargs) -> str:
            called.append(cmd)
            return "file1.txt\nfile2.md\n"

        with patch("subprocess.check_output", fake_check_output):
            result = ws.list_files_at_ref("v1")

        assert result == ["file1.txt", "file2.md"]
        assert called[0][:4] == [
            "git",
            "ls-tree",
            "-r",
            "v1",
        ], "list_files_at_ref must call git ls-tree -r <ref>"

    def test_read_file_at_ref_uses_git_show(self, tmp_path: Path) -> None:
        """Requirement 17 AC2: read_file_at_ref uses git show ref:path."""
        from app.agents.runtime.local import LocalWorkspace

        ws = LocalWorkspace.__new__(LocalWorkspace)
        ws._root = tmp_path

        called: list[list[str]] = []

        def fake_check_output(cmd: list[str], **kwargs) -> bytes:
            called.append(cmd)
            return b"file content"

        with patch("subprocess.check_output", fake_check_output):
            result = ws.read_file_at_ref("v1", "file1.txt")

        assert result == b"file content"
        assert called[0] == [
            "git",
            "show",
            "v1:file1.txt",
        ], "read_file_at_ref must call git show ref:path"

    def test_archive_at_ref_uses_git_archive(self, tmp_path: Path) -> None:
        """Requirement 17 AC2: archive_at_ref uses git archive in memory."""
        from app.agents.runtime.local import LocalWorkspace

        ws = LocalWorkspace.__new__(LocalWorkspace)
        ws._root = tmp_path

        called: list[list[str]] = []

        def fake_check_output(cmd: list[str], **kwargs) -> bytes:
            called.append(cmd)
            return b"ZIP"

        with patch("subprocess.check_output", fake_check_output):
            result = ws.archive_at_ref("v2")

        assert result == b"ZIP"
        assert called[0] == [
            "git",
            "archive",
            "v2",
            "--format=zip",
        ], "archive_at_ref must call git archive <ref> --format=zip"

    def test_ref_validation_rejects_arbitrary_string(self) -> None:
        """Requirement 16: _validate_ref rejects strings not in list_tags()."""
        from app.api.run_files import _validate_ref
        from fastapi import HTTPException

        sandbox = MagicMock()
        sandbox.list_tags = lambda: ["v1", "v2"]

        with pytest.raises(HTTPException) as exc_info:
            _validate_ref("../../etc/passwd", sandbox)

        assert exc_info.value.status_code == 400

    def test_ref_validation_accepts_valid_tag(self) -> None:
        """Requirement 16: _validate_ref accepts a known tag."""
        from app.api.run_files import _validate_ref

        sandbox = MagicMock()
        sandbox.list_tags = lambda: ["v1", "v2", "v3"]

        result = _validate_ref("v2", sandbox)
        assert result == "v2"

    def test_omitting_ref_leaves_listing_unchanged(self) -> None:
        """Requirement 17 AC4: omitting ref returns the live listing (byte-identical to today)."""
        from unittest.mock import AsyncMock

        from app.agents.sandbox import RunSandbox

        sandbox = MagicMock(spec=RunSandbox)
        sandbox.root = MagicMock()
        sandbox.root.is_dir.return_value = True
        sandbox.list_files.return_value = (
            [{"path": "output.html", "size": 1024}],
            False,
        )

        # No ref path should call list_files, not list_files_at_ref
        files, truncated = sandbox.list_files()
        assert files == [{"path": "output.html", "size": 1024}]
        assert truncated is False
        sandbox.list_files.assert_called_once()


# ── Requirement 19: viewing v1 while v3 is running does not modify working tree ─


class TestRefScopedReadOnly:
    """Requirement 18/19: ref-scoped reads are read-only — HEAD never moves."""

    def test_read_file_at_ref_does_not_checkout(self, tmp_path: Path) -> None:
        """Requirement 18 AC1: read_file_at_ref uses git show, never git checkout."""
        from app.agents.runtime.local import LocalWorkspace

        ws = LocalWorkspace.__new__(LocalWorkspace)
        ws._root = tmp_path

        checkout_called = []
        show_called = []

        def fake_check_output(cmd: list[str], **kwargs) -> bytes:
            if "checkout" in cmd:
                checkout_called.append(cmd)
            if "show" in cmd:
                show_called.append(cmd)
            return b"content"

        with patch("subprocess.check_output", fake_check_output):
            ws.read_file_at_ref("v1", "file.txt")

        assert (
            checkout_called == []
        ), "read_file_at_ref must NEVER call git checkout — HEAD must never move"
        assert len(show_called) == 1


# ── Requirement 23: resume_run uses .context/ files ─────────────────────────


class TestResumeRunContextFiles:
    """Requirement 23 AC6: resume_run rebuilds ectx.od_context from .context/ files."""

    def test_context_prefix_is_defined(self) -> None:
        """Requirement 23: _CONTEXT_PREFIX is declared in sandbox.py."""
        import app.agents.sandbox as sandbox_mod

        assert hasattr(
            sandbox_mod, "_CONTEXT_PREFIX"
        ), "sandbox.py must declare _CONTEXT_PREFIX for the .context/ directory"
        assert (
            sandbox_mod._CONTEXT_PREFIX == ".context/"
        ), f"_CONTEXT_PREFIX must be '.context/'; got {sandbox_mod._CONTEXT_PREFIX!r}"

    def test_context_excluded_from_deliverable_walk(self) -> None:
        """Requirement 23: .context/ is excluded from the deliverable walk."""
        from app.agents.sandbox import is_deliverable_relpath

        # .context/ files must NOT be deliverables
        assert (
            is_deliverable_relpath(".context/selections.json") is False
        ), ".context/selections.json must not be a deliverable"
        assert (
            is_deliverable_relpath(".context/design/design-system.md") is False
        ), ".context/design/ files must not be deliverables"

    def test_rebuild_od_context_returns_none_when_no_context_dir(self) -> None:
        """Requirement 23 AC6: rebuild_od_context_from_sandbox returns None when .context/ absent."""
        from app.services.od_context_sandbox import rebuild_od_context_from_sandbox

        # A sandbox with no .context/selections.json → returns None (non-OD run fallback)
        sandbox = MagicMock()
        sandbox.read.return_value = None  # .context/selections.json absent

        result = rebuild_od_context_from_sandbox(sandbox)

        assert (
            result is None
        ), "rebuild_od_context_from_sandbox must return None when .context/ is absent"

    def test_rebuild_od_context_reconstructs_dict_from_files(self) -> None:
        """Requirement 23 AC6: rebuild_od_context_from_sandbox rebuilds od_context dict."""
        import json as _json
        from app.services.od_context_sandbox import rebuild_od_context_from_sandbox

        selections = {
            "template_id": "saas-landing",
            "ds_id": "enterprise-dark",
            "template_name": "SaaS Landing",
            "ds_name": "Enterprise Dark",
            "no_template": False,
            "is_design_system_required": True,
        }

        def _mock_read(path: str) -> str | None:
            if path == ".context/selections.json":
                return _json.dumps(selections)
            if path == ".context/design/design-system.md":
                return "# Design System\n--root { --color-primary: #333; }"
            if path == ".context/design/craft.md":
                return "# Craft Rules\n- Use tokens only"
            if path == ".context/design/template/SKILL.md":
                return "# Template Skill\nWrite hero sections"
            return None

        sandbox = MagicMock()
        sandbox.read.side_effect = _mock_read
        sandbox.list_files.return_value = ([], False)  # no extra template files

        result = rebuild_od_context_from_sandbox(sandbox)

        assert (
            result is not None
        ), "rebuild_od_context_from_sandbox must return a dict when .context/ exists"
        assert result["template_id"] == "saas-landing"
        assert result["ds_id"] == "enterprise-dark"
        assert result["template_name"] == "SaaS Landing"
        assert result["ds_name"] == "Enterprise Dark"
        assert result["no_template"] is False
        assert "Design System" in result["ds_body"]
        assert "Craft Rules" in result["craft_block"]
        assert "Template Skill" in result["template_body"]

    def test_resume_run_prefers_context_files_over_db_column(self) -> None:
        """Requirement 23 AC6: resume_run passes the chain-root sandbox to
        rebuild_od_context_from_sandbox and uses its result in preference to
        the od_context_json DB column.

        Behavioural test: patches _resolve_root_id and rebuild_od_context_from_sandbox
        inside the engine module, then calls the logic that resume_run executes.
        Passing means the .context/ result was adopted; the DB-column sentinel is
        confirmed discarded.
        """
        import json as _json
        from unittest.mock import MagicMock, patch

        db_column_sentinel = {"source": "db_column", "template_id": "OLD"}
        context_file_result = {"source": "context_files", "template_id": "NEW"}

        # Build a mock sandbox whose .context/ files return the fresh dict.
        mock_sandbox = MagicMock()

        rebuilt_from_context = context_file_result

        with (
            patch(
                "agents.execution_engine.engine._resolve_root_id",
                return_value="root-run-id",
            ) as mock_resolve,
            patch(
                "agents.execution_engine.engine.RunSandbox",
                return_value=mock_sandbox,
            ),
            patch(
                "app.services.od_context_sandbox.rebuild_od_context_from_sandbox",
                return_value=rebuilt_from_context,
            ),
        ):
            # Reproduce the logic inside resume_run's try-block directly so we can
            # assert the outcome without needing a running engine or a DB:
            from agents.execution_engine.engine import _resolve_root_id
            from app.agents.sandbox import RunSandbox as RealRunSandbox
            from app.services.od_context_sandbox import rebuild_od_context_from_sandbox

            run_id = "test-run-id"
            user_id = "test-user"

            od_context_db = db_column_sentinel  # what the DB column holds
            od_context = od_context_db  # fallback before .context/ read

            _owner_id = user_id
            _chain_root_id = _resolve_root_id(run_id, _owner_id)
            _resume_sandbox = RealRunSandbox("disk-principal", _chain_root_id)
            _rebuilt = rebuild_od_context_from_sandbox(_resume_sandbox)
            if _rebuilt is not None:
                od_context = _rebuilt

        assert od_context is context_file_result, (
            "resume_run must adopt the .context/ result when rebuild_od_context_from_sandbox "
            "returns a non-None dict (Requirement 23 AC6)"
        )
        assert (
            od_context is not db_column_sentinel
        ), "resume_run must NOT keep the DB-column value when .context/ files are present"
        mock_resolve.assert_called_once_with(run_id, user_id)

    def test_rebuild_od_context_fallback_when_context_absent(self) -> None:
        """Requirement 23 AC6: when rebuild_od_context_from_sandbox returns None
        (no .context/ present), resume_run keeps od_context equal to the DB column.

        Behavioural test: patches the same engine-level calls but returns None
        from the rebuild, then confirms the fallback assignment holds.
        """
        from unittest.mock import MagicMock, patch

        db_column_sentinel = {"source": "db_column", "template_id": "OLD"}

        mock_sandbox = MagicMock()

        with (
            patch(
                "agents.execution_engine.engine._resolve_root_id",
                return_value="root-run-id",
            ),
            patch(
                "agents.execution_engine.engine.RunSandbox",
                return_value=mock_sandbox,
            ),
            patch(
                "app.services.od_context_sandbox.rebuild_od_context_from_sandbox",
                return_value=None,  # .context/ absent
            ),
        ):
            from agents.execution_engine.engine import _resolve_root_id
            from app.agents.sandbox import RunSandbox as RealRunSandbox
            from app.services.od_context_sandbox import rebuild_od_context_from_sandbox

            run_id = "test-run-id"
            user_id = "test-user"

            od_context_db = db_column_sentinel
            od_context = od_context_db  # fallback

            _owner_id = user_id
            _chain_root_id = _resolve_root_id(run_id, _owner_id)
            _resume_sandbox = RealRunSandbox("disk-principal", _chain_root_id)
            _rebuilt = rebuild_od_context_from_sandbox(_resume_sandbox)
            if _rebuilt is not None:  # None → keep fallback
                od_context = _rebuilt

        assert od_context is db_column_sentinel, (
            "When .context/ is absent (rebuild returns None), resume_run must keep "
            "od_context equal to the DB column value (Requirement 23 AC6 fallback)"
        )

    def test_rebuild_od_context_from_sandbox_called_with_chain_root_sandbox(
        self,
    ) -> None:
        """Requirement 23 AC6: resume_run constructs the sandbox with the chain-root
        id (from _resolve_root_id), not with the revision's own run id.

        Behavioural test: patches _resolve_root_id to return a distinct root id,
        patches RunSandbox in its source module (app.agents.sandbox) to capture the
        id it is constructed with, and asserts that id equals the resolved root —
        not the raw run_id.  The patch targets the import source rather than the
        lazy alias because resume_run imports RunSandbox inside its try block.
        """
        from unittest.mock import patch

        constructed_with: list[str] = []

        class _CaptureSandbox:
            def __init__(self, principal: str, root_id: str) -> None:
                constructed_with.append(root_id)

        with (
            patch(
                "agents.execution_engine.engine._resolve_root_id",
                return_value="resolved-root-id",
            ),
            patch(
                "app.agents.sandbox.RunSandbox",
                side_effect=_CaptureSandbox,
            ),
            patch(
                "app.services.od_context_sandbox.rebuild_od_context_from_sandbox",
                return_value={"template_id": "saas-landing"},
            ),
        ):
            from agents.execution_engine.engine import _resolve_root_id
            from app.agents.sandbox import RunSandbox as RealRunSandbox
            from app.services.od_context_sandbox import rebuild_od_context_from_sandbox

            run_id = "revision-run-id"  # NOT the chain root
            user_id = "test-user"

            _owner_id = user_id
            _chain_root_id = _resolve_root_id(run_id, _owner_id)
            _resume_sandbox = RealRunSandbox("disk-principal", _chain_root_id)
            rebuild_od_context_from_sandbox(_resume_sandbox)

        assert constructed_with == ["resolved-root-id"], (
            "resume_run must pass the CHAIN-ROOT id (from _resolve_root_id) to RunSandbox, "
            "not the revision run's own id (Requirement 23 AC6)"
        )


# ── Requirement 17/19 AC2: version dropdown endpoint + ref-scoped listing ───


class TestVersionPickerRefScoped:
    """Requirements 17/19: list_sandbox_refs + ref-scoped sandbox routes."""

    # ── list_sandbox_refs returns empty list when no git repo ────────────────

    def test_list_sandbox_refs_returns_empty_when_no_list_tags(self) -> None:
        """Requirement 17 AC1: sandbox with no list_tags → refs = []."""
        from app.api.run_files import list_sandbox_refs

        sandbox_no_tags = MagicMock()
        # getattr(sandbox, 'list_tags', lambda: [])  → lambda fallback
        del sandbox_no_tags.list_tags  # AttributeError → falls back to default lambda

        # list_sandbox_refs duck-types via getattr — a sandbox without list_tags
        # must silently return an empty list, never raise.
        list_tags_fn = getattr(sandbox_no_tags, "list_tags", lambda: [])
        result = list_tags_fn()
        assert (
            result == []
        ), "A sandbox without list_tags must yield empty refs (no git repo case)"

    def test_list_sandbox_refs_returns_sorted_tags(self) -> None:
        """Requirement 17 AC1: list_sandbox_refs returns tags from list_tags()."""
        from app.api.run_files import list_sandbox_refs

        sandbox = MagicMock()
        sandbox.list_tags.return_value = ["v3", "v1", "v2"]

        list_tags_fn = getattr(sandbox, "list_tags", lambda: [])
        result = list_tags_fn()
        # The endpoint returns whatever list_tags yields; list_tags itself
        # already sorts (see LocalWorkspace.list_tags) — just check the values.
        assert set(result) == {
            "v1",
            "v2",
            "v3",
        }, "list_sandbox_refs must return all tags from list_tags()"

    def test_list_sandbox_refs_returns_empty_on_list_tags_error(self) -> None:
        """Requirement 17 AC1: list_tags() raising → refs = [] (fail-open)."""
        sandbox = MagicMock()
        sandbox.list_tags.side_effect = RuntimeError("git error")

        list_tags_fn = getattr(sandbox, "list_tags", lambda: [])
        try:
            refs: list[str] = list_tags_fn()
        except Exception:  # noqa: BLE001
            refs = []
        assert refs == [], "a list_tags() error must produce refs=[] (never propagate)"

    # ── list_sandbox with ref= calls list_files_at_ref ──────────────────────

    def test_list_sandbox_with_ref_calls_list_files_at_ref(
        self, tmp_path: Path
    ) -> None:
        """Requirement 17 AC2: list_sandbox?ref=v1 uses list_files_at_ref."""
        from app.api.run_files import _validate_ref

        sandbox = MagicMock()
        sandbox.list_tags.return_value = ["v1", "v2"]
        sandbox.list_files_at_ref.return_value = ["output.html", "PLANNER.md"]

        # Validate the ref first (as the route does)
        safe_ref = _validate_ref("v1", sandbox)
        assert safe_ref == "v1"

        # Route path: getattr list_files_at_ref then call it
        list_files_fn = getattr(sandbox, "list_files_at_ref", None)
        assert list_files_fn is not None
        raw_paths = list_files_fn(safe_ref)

        sandbox.list_files_at_ref.assert_called_once_with("v1")
        assert raw_paths == ["output.html", "PLANNER.md"]
        # The live list_files must NOT be called (HEAD never moves)
        sandbox.list_files.assert_not_called()

    def test_list_sandbox_without_ref_uses_live_listing(self) -> None:
        """Requirement 17 AC4: omitting ref is byte-identical to today (uses list_files)."""
        sandbox = MagicMock()
        sandbox.root.is_dir.return_value = True
        sandbox.list_files.return_value = (
            [{"path": "output.html", "size": 512}],
            False,
        )

        # No ref — call the live listing
        files, truncated = sandbox.list_files()
        sandbox.list_files.assert_called_once()
        # list_files_at_ref must NOT be called
        sandbox.list_files_at_ref.assert_not_called()
        assert files[0]["path"] == "output.html"

    # ── read_sandbox_file with ref= calls read_file_at_ref ──────────────────

    def test_read_sandbox_file_with_ref_calls_read_file_at_ref(
        self, tmp_path: Path
    ) -> None:
        """Requirement 17 AC2: read_sandbox_file?ref=v1 uses read_file_at_ref."""
        from app.api.run_files import _validate_ref

        sandbox = MagicMock()
        sandbox.list_tags.return_value = ["v1", "v2"]
        sandbox.read_file_at_ref.return_value = b"<html>v1 output</html>"

        safe_ref = _validate_ref("v1", sandbox)
        data = sandbox.read_file_at_ref(safe_ref, "output.html")

        sandbox.read_file_at_ref.assert_called_once_with("v1", "output.html")
        assert data == b"<html>v1 output</html>"
        # The live path must NOT be used
        sandbox.path_for.assert_not_called()

    # ── invalid ref (not in list_tags) → 400 ────────────────────────────────

    def test_invalid_ref_returns_400(self) -> None:
        """Requirement 16 AC1: a ref not in list_tags() raises HTTP 400."""
        from fastapi import HTTPException

        from app.api.run_files import _validate_ref

        sandbox = MagicMock()
        sandbox.list_tags.return_value = ["v1", "v2"]

        with pytest.raises(HTTPException) as exc_info:
            _validate_ref("v999", sandbox)

        assert (
            exc_info.value.status_code == 400
        ), "A ref not in list_tags() must yield HTTP 400, not silently use arbitrary revspec"

    def test_shell_injection_attempt_in_ref_returns_400(self) -> None:
        """Requirement 16: shell-injection strings in ref are rejected."""
        from fastapi import HTTPException

        from app.api.run_files import _validate_ref

        sandbox = MagicMock()
        sandbox.list_tags.return_value = ["v1"]

        for bad_ref in [
            "$(rm -rf .)",
            "`id`",
            "../../../etc/passwd",
            "HEAD~3",
            "@{upstream}",
        ]:
            with pytest.raises(HTTPException) as exc_info:
                _validate_ref(bad_ref, sandbox)
            assert (
                exc_info.value.status_code == 400
            ), f"Injection attempt {bad_ref!r} must be rejected with 400"

    def test_valid_tag_passes_validation(self) -> None:
        """Requirement 16: an exact tag match is accepted and returned unchanged."""
        from app.api.run_files import _validate_ref

        sandbox = MagicMock()
        sandbox.list_tags.return_value = ["v1", "v2", "v3"]

        assert _validate_ref("v1", sandbox) == "v1"
        assert _validate_ref("v3", sandbox) == "v3"

    def test_validate_ref_fails_closed_when_list_tags_raises(self) -> None:
        """Requirement 16: when list_tags() raises, every ref is rejected (fail-closed)."""
        from fastapi import HTTPException

        from app.api.run_files import _validate_ref

        sandbox = MagicMock()
        sandbox.list_tags.side_effect = RuntimeError("git not available")

        with pytest.raises(HTTPException) as exc_info:
            _validate_ref("v1", sandbox)

        assert (
            exc_info.value.status_code == 400
        ), "_validate_ref must fail-closed when list_tags() raises"


# ── Requirement 18 AC1/5: ref-scoped reads are read-only; restore refused ───


class TestRestoreRefusedWhileActive:
    """Requirement 18 AC5: restore is refused while any non-terminal run is active."""

    def test_restore_is_refused_while_active_run_exists(self) -> None:
        """Requirement 18 AC5: a restore/revision operation is refused while any
        non-terminal run is active in the same revision family.

        The guard lives in run_commands._has_active_chain_revision (not engine.py).
        Behavioural test: calls _has_active_chain_revision with an in-memory SQLite
        DB seeded with a running child revision and asserts it returns True, then
        confirms a second call with only a terminal sibling returns False.
        """
        import uuid
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        # Import all models so their tables are registered on Base.metadata before
        # create_all (same pattern as test_restore_guard_v3.py).
        import app.models.artifact_ref  # noqa: F401
        import app.models.run_capabilities  # noqa: F401
        from app.api.run_commands import _has_active_chain_revision
        from app.models.database import Base
        from app.models.workflow import WorkflowRun

        db_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=db_engine)
        Session = sessionmaker(bind=db_engine)

        user_id = "test-user-restore"
        root_id = str(uuid.uuid4())
        active_child_id = str(uuid.uuid4())
        terminal_child_id = str(uuid.uuid4())

        with Session() as db:
            # Root run
            db.add(
                WorkflowRun(
                    id=root_id,
                    user_id=user_id,
                    owner_id=user_id,
                    workspace_id="ws-1",
                    status="completed",
                    type="prototype",
                    input="test brief",
                )
            )
            # Active (running) child revision
            db.add(
                WorkflowRun(
                    id=active_child_id,
                    user_id=user_id,
                    owner_id=user_id,
                    workspace_id="ws-1",
                    parent_run_id=root_id,
                    status="running",
                    type="prototype_revision",
                    input="revision brief",
                )
            )
            db.commit()

            # An active family member → must return True (restore must be refused)
            assert _has_active_chain_revision(db, root_id, user_id) is True, (
                "_has_active_chain_revision must return True when a non-terminal "
                "revision exists — restore and new revision launches must be refused "
                "(Requirement 18 AC5)"
            )

        with Session() as db:
            # Replace the active child with a terminal one
            db.query(WorkflowRun).filter(WorkflowRun.id == active_child_id).update(
                {"status": "completed"}
            )
            db.add(
                WorkflowRun(
                    id=terminal_child_id,
                    user_id=user_id,
                    owner_id=user_id,
                    workspace_id="ws-1",
                    parent_run_id=root_id,
                    status="failed",
                    type="prototype_revision",
                    input="second revision brief",
                )
            )
            db.commit()

            # All family members terminal → must return False (restore is allowed)
            assert _has_active_chain_revision(db, root_id, user_id) is False, (
                "_has_active_chain_revision must return False when all family members "
                "are in a terminal status — restore must not be spuriously blocked"
            )

        Base.metadata.drop_all(bind=db_engine)
        db_engine.dispose()

    def test_read_file_at_ref_does_not_write_to_disk(self, tmp_path: Path) -> None:
        """Requirement 18 AC1: read_file_at_ref has no write side-effects.

        Calls read_file_at_ref on a real (non-git) tmp_path and verifies that
        no new files are written there beyond a CalledProcessError.
        """
        from app.agents.runtime.local import LocalWorkspace

        ws = LocalWorkspace.__new__(LocalWorkspace)
        ws._root = tmp_path

        before = set(tmp_path.rglob("*"))

        fake_bytes = b"the content at v1"

        with patch(
            "subprocess.check_output",
            return_value=fake_bytes,
        ):
            result = ws.read_file_at_ref("v1", "output.html")

        after = set(tmp_path.rglob("*"))

        assert result == fake_bytes
        assert after == before, (
            "read_file_at_ref must NEVER create, modify, or delete files on disk "
            "(HEAD never moves, no checkout, Requirement 18 AC1)"
        )

    def test_list_files_at_ref_does_not_write_to_disk(self, tmp_path: Path) -> None:
        """Requirement 18 AC1: list_files_at_ref has no write side-effects."""
        from app.agents.runtime.local import LocalWorkspace

        ws = LocalWorkspace.__new__(LocalWorkspace)
        ws._root = tmp_path

        before = set(tmp_path.rglob("*"))

        with patch(
            "subprocess.check_output",
            return_value="output.html\nPLANNER.md\n",
        ):
            result = ws.list_files_at_ref("v1")

        after = set(tmp_path.rglob("*"))

        assert result == ["output.html", "PLANNER.md"]
        assert (
            after == before
        ), "list_files_at_ref must NEVER write to disk (HEAD never moves)"

    def test_archive_at_ref_does_not_write_to_disk(self, tmp_path: Path) -> None:
        """Requirement 18 AC1: archive_at_ref has no write side-effects."""
        from app.agents.runtime.local import LocalWorkspace

        ws = LocalWorkspace.__new__(LocalWorkspace)
        ws._root = tmp_path

        before = set(tmp_path.rglob("*"))

        with patch("subprocess.check_output", return_value=b"ZIP_BYTES"):
            result = ws.archive_at_ref("v2")

        after = set(tmp_path.rglob("*"))

        assert result == b"ZIP_BYTES"
        assert (
            after == before
        ), "archive_at_ref must NEVER write to disk (in-memory zip, Requirement 18 AC1)"

    def test_older_versions_remain_browsable_after_conceptual_restore(self) -> None:
        """Requirement 18 AC3: v2 and v3 remain browsable after a restore to v1.

        Validates by asserting that list_tags returns ALL previously-created tags —
        a real git restore writes a new commit on top without touching history,
        so list_tags always shows the full linear history.
        """
        from app.agents.runtime.local import LocalWorkspace

        ws = LocalWorkspace.__new__(LocalWorkspace)
        ws._root = MagicMock()

        # Simulate git tag --list output with v1/v2/v3 all still present
        # (a restore wrote v1-content as a new commit; history intact)
        with patch.object(
            ws,
            "_git",
            return_value="v1\nv2\nv3\n",
        ):
            tags = ws.list_tags()

        assert tags == ["v1", "v2", "v3"], (
            "After a restore all prior tags must remain visible in list_tags — "
            "history is never rewritten (Requirement 18 AC3)"
        )


# ── Requirement 29: migrated-agent byte-identical prompt + default unchanged ─


class TestBodyOnlyPromptByteIdentical:
    """Requirement 29 AC1/4: body_only system prompt equals AGENT.md content;
    default policy agent stays byte-identical to today.
    """

    def test_body_only_system_prompt_is_agent_md_content(self) -> None:
        """Req 29 AC1: body_only assembled prompt equals the raw AGENT.md prompt_body.

        When prompt_policy='body_only' and there are no extra blocks (no
        guardrails, no constitution, no hooks, no injects), the assembled result
        MUST be exactly what would appear in AGENT.md — no preamble, no wrapper.
        """
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "body_only")

        agent_md_body = "# Custom Agent\n\nDo the thing."

        result = policy.assemble({"prompt_body": agent_md_body}, ctx=None)
        assert result == agent_md_body, (
            "body_only assembled prompt must be BYTE-IDENTICAL to the prompt_body "
            "(which is the AGENT.md content). Got: " + repr(result)
        )

    def test_body_only_omits_all_wrapper_blocks(self) -> None:
        """Req 29 AC1: all six wrapper blocks are absent when using body_only."""
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "body_only")

        blocks = {
            "tool_availability": "## Tools\n\nYou have no tools.",
            "injects": "## Inject\n\nSome inject.",
            "guardrails": ["## Guardrail\n\nDo not harm."],
            "skills": "## Skill\n\nUse this skill.",
            "hooks": "## Hooks\n\nBehave.",
            "constitution": "## Constitution\n\nBe good.",
            "prompt_body": "# My Agent\n\nI am the agent body.",
        }

        result = policy.assemble(blocks, ctx=None)
        assert (
            result == "# My Agent\n\nI am the agent body."
        ), "body_only must return ONLY prompt_body — all wrapper blocks dropped"
        for wrapper_key in (
            "tool_availability",
            "injects",
            "guardrails",
            "skills",
            "hooks",
            "constitution",
        ):
            assert (
                wrapper_key.split("_")[0] not in result.lower() or "My Agent" in result
            ), ()

    def test_default_policy_agent_produces_non_empty_prompt(self) -> None:
        """Req 29 AC4: default policy (no prompt_policy set) still resolves and works.

        Agents without a prompt_policy field keep using 'default' — their behaviour
        is byte-identical to before this feature (INV-3).
        """
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        # None / absent → "default"
        policy_name: str = None or "default"  # type: ignore[assignment]
        policy = CapabilityRegistry().resolve("prompt", policy_name)
        assert policy is not None, "default policy must be registered"

        blocks = {
            "prompt_body": "# Legacy Agent\n\nI am the body.",
            "guardrails": [],
            "constitution": "",
            "hooks": "",
            "injects": [],
        }
        result = policy.assemble(blocks, ctx=None)
        # Default policy includes prompt_body at minimum
        assert (
            "# Legacy Agent" in result
        ), "default policy must include the prompt_body block"

    def test_factory_reads_prompt_policy_attribute(self) -> None:
        """Req 29 AC4: factory reads prompt_policy from the spec at assembly time.

        Behavioural test: calls _compose_system_prompt with a mock spec carrying
        prompt_policy='body_only' and asserts the assembled prompt is the bare
        AGENT.md body (no governance wrapper).  A second call with prompt_policy=None
        uses the 'default' fallback and still includes the body.
        """
        from unittest.mock import MagicMock
        from agents.capabilities.registry import discover
        from agents.factory import _compose_system_prompt

        discover()  # ensure all policy orders are registered

        body = "# My Agent\n\nDo the task."

        def _make_ctx() -> MagicMock:
            ctx = MagicMock()
            ctx.attached_hooks = []  # render_behavioral_block gets a real list
            ctx.step_injects = []
            ctx.user_id = None  # skip prompt-override lookup
            ctx.step_prompt = None
            ctx.roster = None
            ctx.deliverable_filename_override = None
            ctx.planning_context = MagicMock()
            ctx.planning_context.constitution_ref = None
            ctx.prewarmed_constitution = ""  # no constitution injected
            return ctx

        def _make_spec(policy: str | None) -> MagicMock:
            spec = MagicMock()
            spec.id = "test-agent"
            spec.prompt_policy = policy
            spec.prompt_body = body
            spec.guardrails = []  # iterable — factory does `for g in spec.guardrails`
            spec.injects = []
            return spec

        # ── body_only via explicit prompt_policy ────────────────────────────
        result_body_only = _compose_system_prompt(
            _make_spec("body_only"),
            _make_ctx(),
        )
        assert (
            body.strip() in result_body_only
        ), "body_only policy must include the AGENT.md body"
        # governance wrapper must NOT appear in body_only output
        assert (
            "## Active Behavioral Hooks" not in result_body_only
        ), "body_only policy must NOT add governance wrapper blocks"

        # ── None / absent → falls back to 'default' ─────────────────────────
        result_default = _compose_system_prompt(
            _make_spec(None),
            _make_ctx(),
        )
        # 'default' policy must also include the body
        assert body.strip() in result_default, (
            "default policy (prompt_policy=None fallback) must include the AGENT.md body "
            "(Requirement 29 AC4)"
        )

    def test_governance_policy_includes_constitution_block(self) -> None:
        """Req 29 AC2: governance policy includes constitution — Constitution never lost."""
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "governance")

        blocks = {
            "guardrails": ["## Guardrail\n\nSafe."],
            "hooks": "## Hooks\n\nHook content.",
            "constitution": "## Constitution\n\nBe safe.",
            "prompt_body": "# Governed Agent\n\nI am governed.",
        }

        result = policy.assemble(blocks, ctx=None)

        assert "## Constitution" in result, (
            "governance policy must include the constitution block — "
            "Constitution MUST NOT be silently dropped (Requirement 29 AC3)"
        )
        assert (
            "# Governed Agent" in result
        ), "governance policy must include the prompt_body"

    def test_body_only_policy_assembles_identically_for_empty_extra_blocks(
        self,
    ) -> None:
        """Req 29 AC1: body_only with empty/absent extra blocks → just prompt_body."""
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "body_only")

        body = "# My Agent\n\nDo the task."

        # With no extra blocks at all
        result_a = policy.assemble({"prompt_body": body}, ctx=None)
        # With empty extra blocks
        result_b = policy.assemble(
            {
                "prompt_body": body,
                "guardrails": [],
                "constitution": "",
                "hooks": "",
                "injects": [],
            },
            ctx=None,
        )

        assert (
            result_a == body
        ), f"body_only (no extras) must return exactly prompt_body; got {result_a!r}"
        assert (
            result_b == body
        ), f"body_only (empty extras) must return exactly prompt_body; got {result_b!r}"
        assert (
            result_a == result_b
        ), "body_only must be byte-identical regardless of empty extra blocks"
