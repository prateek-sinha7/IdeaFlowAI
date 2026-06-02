"""Unit tests for agents/factory.py — create_agent, _compose_system_prompt, _build_tools.

Tests cover:
  - create_agent with tools: [] → DeepAgent has empty tools list
  - create_agent with tools: ["workspace"] → workspace tools only
  - create_agent with tools: ["prototype"] → prototype tools only
  - create_agent with tools: ["workspace", "prototype"] → union of both sets
  - create_agent with unknown tool name → ValueError with tool name and agent ID
  - create_agent with unknown agent ID → FileNotFoundError propagated
  - Missing guardrail file → warning logged, agent still runs with empty guardrail block
  - _compose_system_prompt composition order (guardrails before skills before hooks before body)

Requirements: 4.4, 4.5, 4.6, 4.7, 4.9, 4.10, 4.11, 3.3
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.factory import AgentContext, _build_tools, _compose_system_prompt, create_agent
from agents.loader import AgentSpec

from tests.agents.conftest import create_agent_file, make_agent_md


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(
    *,
    agent_id: str = "test-agent",
    tools: list[str] | None = None,
    guardrails: list[str] | None = None,
    prompt_body: str = "You are a test agent.",
    max_tokens: int = 4000,
) -> AgentSpec:
    """Build a minimal AgentSpec for use in factory tests."""
    return AgentSpec(
        id=agent_id,
        name="Test Agent",
        role="Testing",
        pipeline_type="user_stories",
        order=1,
        max_tokens=max_tokens,
        prompt_body=prompt_body,
        tools=tools if tools is not None else [],
        guardrails=guardrails if guardrails is not None else [],
    )


def _make_ctx(**kwargs) -> AgentContext:
    """Build a minimal AgentContext."""
    defaults = dict(
        user_request="Build me something",
        agent_outputs={},
        attached_skills=[],
        attached_hooks=[],
        workspace=None,
    )
    defaults.update(kwargs)
    return AgentContext(**defaults)


# ---------------------------------------------------------------------------
# create_agent — tool list wiring (Requirements 4.4, 4.5, 4.6, 4.7)
# ---------------------------------------------------------------------------


class TestCreateAgentToolWiring:
    """Verify that create_agent passes the correct tool list to DeepAgent.

    DeepAgent is imported lazily inside create_agent(), so we patch it at its
    source module path: "app.agents.deep_agent.DeepAgent".
    """

    _DEEP_AGENT_PATCH = "app.agents.deep_agent.DeepAgent"

    def test_empty_tools_passes_empty_list_to_deep_agent(self, tmp_agent_dir):
        """Requirement 4.4: tools: [] → DeepAgent instantiated with empty tools list."""
        agent_id = "no-tools-agent"
        content = make_agent_md(id=agent_id, tools=[])
        create_agent_file(tmp_agent_dir, agent_id, content)
        ctx = _make_ctx()

        with patch(self._DEEP_AGENT_PATCH) as MockDeepAgent:
            create_agent(agent_id, ctx)

        call_kwargs = MockDeepAgent.call_args.kwargs
        assert call_kwargs["tools"] == []

    def test_workspace_tools_only(self, tmp_agent_dir):
        """Requirement 4.5: tools: ["workspace"] → only workspace tools passed."""
        agent_id = "workspace-agent"
        content = make_agent_md(id=agent_id, tools=["workspace"])
        create_agent_file(tmp_agent_dir, agent_id, content)
        ctx = _make_ctx()

        fake_ws_tools = [MagicMock(name="write_file"), MagicMock(name="read_file"), MagicMock(name="list_workspace_files")]

        with patch(self._DEEP_AGENT_PATCH) as MockDeepAgent:
            with patch("app.agents.tools.workspace.make_workspace_tools", return_value=fake_ws_tools):
                create_agent(agent_id, ctx)

        tools_passed = MockDeepAgent.call_args.kwargs["tools"]
        assert tools_passed == fake_ws_tools

    def test_prototype_tools_only(self, tmp_agent_dir):
        """Requirement 4.6: tools: ["prototype"] → only prototype tools passed."""
        agent_id = "prototype-agent"
        content = make_agent_md(id=agent_id, tools=["prototype"])
        create_agent_file(tmp_agent_dir, agent_id, content)
        ctx = _make_ctx()

        fake_proto_tools = [
            MagicMock(name="read_template_seed"),
            MagicMock(name="read_layout_reference"),
            MagicMock(name="read_checklist"),
            MagicMock(name="todo_write"),
            MagicMock(name="emit_artifact"),
        ]

        with patch(self._DEEP_AGENT_PATCH) as MockDeepAgent:
            with patch("app.agents.tools.prototype.make_prototype_tools", return_value=fake_proto_tools):
                create_agent(agent_id, ctx)

        tools_passed = MockDeepAgent.call_args.kwargs["tools"]
        assert tools_passed == fake_proto_tools

    def test_workspace_and_prototype_tools_union(self, tmp_agent_dir):
        """Requirement 4.7: tools: ["workspace", "prototype"] → union of both sets."""
        agent_id = "full-tools-agent"
        content = make_agent_md(id=agent_id, tools=["workspace", "prototype"])
        create_agent_file(tmp_agent_dir, agent_id, content)
        ctx = _make_ctx()

        fake_ws_tools = [MagicMock(name="write_file"), MagicMock(name="read_file"), MagicMock(name="list_workspace_files")]
        fake_proto_tools = [
            MagicMock(name="read_template_seed"),
            MagicMock(name="read_layout_reference"),
            MagicMock(name="read_checklist"),
            MagicMock(name="todo_write"),
            MagicMock(name="emit_artifact"),
        ]

        with patch(self._DEEP_AGENT_PATCH) as MockDeepAgent:
            with patch("app.agents.tools.workspace.make_workspace_tools", return_value=fake_ws_tools):
                with patch("app.agents.tools.prototype.make_prototype_tools", return_value=fake_proto_tools):
                    create_agent(agent_id, ctx)

        tools_passed = MockDeepAgent.call_args.kwargs["tools"]
        assert tools_passed == fake_ws_tools + fake_proto_tools

    def test_unknown_tool_name_raises_value_error(self, tmp_agent_dir):
        """Requirement 4.11: unknown tool name → ValueError with tool name and agent ID."""
        agent_id = "bad-tools-agent"
        content = make_agent_md(id=agent_id, tools=["unknown_tool"])
        create_agent_file(tmp_agent_dir, agent_id, content)
        ctx = _make_ctx()

        # ValueError is raised before DeepAgent is instantiated, so no need to patch it
        with pytest.raises(ValueError) as exc_info:
            create_agent(agent_id, ctx)

        error_msg = str(exc_info.value)
        assert "unknown_tool" in error_msg
        assert agent_id in error_msg

    def test_unknown_agent_id_propagates_file_not_found(self, tmp_agent_dir):
        """Requirement 4.9: unknown agent_id → FileNotFoundError propagated from loader."""
        ctx = _make_ctx()

        # FileNotFoundError is raised before DeepAgent is instantiated
        with pytest.raises(FileNotFoundError):
            create_agent("nonexistent-agent-xyz", ctx)


# ---------------------------------------------------------------------------
# _build_tools — direct unit tests (Requirements 4.4, 4.5, 4.6, 4.7, 4.11)
# ---------------------------------------------------------------------------


class TestBuildTools:
    """Direct tests for the _build_tools helper."""

    def test_empty_tools_returns_empty_list(self):
        """Requirement 4.4: spec.tools == [] → empty list returned."""
        spec = _make_spec(tools=[])
        ctx = _make_ctx()

        result = _build_tools(spec, ctx)

        assert result == []

    def test_workspace_tools_returns_three_tools(self):
        """Requirement 4.5: spec.tools == ["workspace"] → 3 workspace tools."""
        spec = _make_spec(tools=["workspace"])
        ctx = _make_ctx()

        fake_ws_tools = [MagicMock(), MagicMock(), MagicMock()]

        with patch("app.agents.tools.workspace.make_workspace_tools", return_value=fake_ws_tools) as mock_ws:
            result = _build_tools(spec, ctx)

        assert result == fake_ws_tools
        mock_ws.assert_called_once()

    def test_prototype_tools_returns_five_tools(self):
        """Requirement 4.6: spec.tools == ["prototype"] → 5 prototype tools."""
        spec = _make_spec(tools=["prototype"])
        ctx = _make_ctx()

        fake_proto_tools = [MagicMock() for _ in range(5)]

        with patch("app.agents.tools.prototype.make_prototype_tools", return_value=fake_proto_tools) as mock_proto:
            result = _build_tools(spec, ctx)

        assert result == fake_proto_tools
        mock_proto.assert_called_once()

    def test_workspace_and_prototype_returns_union(self):
        """Requirement 4.7: both tool sets → union (workspace first, then prototype)."""
        spec = _make_spec(tools=["workspace", "prototype"])
        ctx = _make_ctx()

        fake_ws_tools = [MagicMock(name="ws_tool")]
        fake_proto_tools = [MagicMock(name="proto_tool")]

        with patch("app.agents.tools.workspace.make_workspace_tools", return_value=fake_ws_tools):
            with patch("app.agents.tools.prototype.make_prototype_tools", return_value=fake_proto_tools):
                result = _build_tools(spec, ctx)

        assert result == fake_ws_tools + fake_proto_tools

    def test_unknown_tool_raises_value_error_with_details(self):
        """Requirement 4.11: unrecognized tool name → ValueError with name and agent ID."""
        spec = _make_spec(agent_id="my-agent", tools=["super_tool"])
        ctx = _make_ctx()

        with pytest.raises(ValueError) as exc_info:
            _build_tools(spec, ctx)

        error_msg = str(exc_info.value)
        assert "super_tool" in error_msg
        assert "my-agent" in error_msg

    def test_workspace_uses_ctx_workspace_when_provided(self):
        """When ctx.workspace is set, _build_tools passes it to make_workspace_tools."""
        from app.agents.tools.workspace import AgentWorkspace
        ws = AgentWorkspace()
        spec = _make_spec(tools=["workspace"])
        ctx = _make_ctx(workspace=ws)

        with patch("app.agents.tools.workspace.make_workspace_tools", return_value=[]) as mock_ws:
            _build_tools(spec, ctx)

        mock_ws.assert_called_once_with(ws)

    def test_workspace_creates_transient_workspace_when_none(self):
        """When ctx.workspace is None, _build_tools creates a transient AgentWorkspace."""
        spec = _make_spec(tools=["workspace"])
        ctx = _make_ctx(workspace=None)

        with patch("app.agents.tools.workspace.make_workspace_tools", return_value=[]) as mock_ws:
            _build_tools(spec, ctx)

        mock_ws.assert_called_once()
        # The argument should be an AgentWorkspace instance
        from app.agents.tools.workspace import AgentWorkspace
        passed_ws = mock_ws.call_args.args[0]
        assert isinstance(passed_ws, AgentWorkspace)


# ---------------------------------------------------------------------------
# _compose_system_prompt — composition order (Requirements 3.2, 3.3, 4.3)
# ---------------------------------------------------------------------------


class TestComposeSystemPrompt:
    """Tests for _compose_system_prompt composition order and content."""

    def test_prompt_body_only_when_no_guardrails_skills_hooks(self):
        """With no guardrails, skills, or hooks, result is just the prompt body."""
        spec = _make_spec(guardrails=[], prompt_body="Body text here.")
        ctx = _make_ctx(attached_skills=[], attached_hooks=[])

        result = _compose_system_prompt(spec, ctx)

        assert result == "Body text here."

    def test_guardrails_appear_before_prompt_body(self, tmp_path):
        """Requirement 3.2: guardrail content precedes the prompt body."""
        spec = _make_spec(guardrails=["agile"], prompt_body="## Main Prompt")
        ctx = _make_ctx()

        guardrail_content = "- Follow agile principles."
        guardrail_file = tmp_path / "agile.md"
        guardrail_file.write_text(guardrail_content, encoding="utf-8")

        with patch("agents.factory._GUARDRAILS_DIR", tmp_path):
            result = _compose_system_prompt(spec, ctx)

        guardrail_pos = result.index("agile")
        body_pos = result.index("## Main Prompt")
        assert guardrail_pos < body_pos

    def test_guardrail_heading_format(self, tmp_path):
        """Requirement 3.2: each guardrail block is preceded by ## Guardrail: {name}."""
        spec = _make_spec(guardrails=["typescript"], prompt_body="Body.")
        ctx = _make_ctx()

        guardrail_file = tmp_path / "typescript.md"
        guardrail_file.write_text("Use strict TypeScript.", encoding="utf-8")

        with patch("agents.factory._GUARDRAILS_DIR", tmp_path):
            result = _compose_system_prompt(spec, ctx)

        assert "## Guardrail: typescript" in result

    def test_skills_appear_after_guardrails_before_body(self, tmp_path):
        """Requirement 4.3: guardrails → skills → hooks → body."""
        spec = _make_spec(guardrails=["agile"], prompt_body="BODY")
        ctx = _make_ctx(
            attached_skills=[{"name": "skill1", "content": "SKILL_CONTENT"}],
            attached_hooks=[],
        )

        guardrail_file = tmp_path / "agile.md"
        guardrail_file.write_text("GUARDRAIL_CONTENT", encoding="utf-8")

        with patch("agents.factory._GUARDRAILS_DIR", tmp_path):
            result = _compose_system_prompt(spec, ctx)

        guardrail_pos = result.index("GUARDRAIL_CONTENT")
        skill_pos = result.index("SKILL_CONTENT")
        body_pos = result.index("BODY")

        assert guardrail_pos < skill_pos < body_pos

    def test_hooks_appear_after_skills_before_body(self, tmp_path):
        """Requirement 4.3: hooks appear after skills and before body."""
        spec = _make_spec(guardrails=[], prompt_body="BODY")
        ctx = _make_ctx(
            attached_skills=[{"name": "skill1", "content": "SKILL_CONTENT"}],
            attached_hooks=[{"name": "hook1", "event": "on_start", "content": "HOOK_CONTENT"}],
        )

        with patch("agents.factory._GUARDRAILS_DIR", tmp_path):
            result = _compose_system_prompt(spec, ctx)

        skill_pos = result.index("SKILL_CONTENT")
        hook_pos = result.index("HOOK_CONTENT")
        body_pos = result.index("BODY")

        assert skill_pos < hook_pos < body_pos

    def test_full_composition_order_guardrails_skills_hooks_body(self, tmp_path):
        """Requirement 4.3: full order — guardrails before skills before hooks before body."""
        spec = _make_spec(guardrails=["react"], prompt_body="BODY")
        ctx = _make_ctx(
            attached_skills=[{"content": "SKILL"}],
            attached_hooks=[{"content": "HOOK"}],
        )

        guardrail_file = tmp_path / "react.md"
        guardrail_file.write_text("GUARDRAIL", encoding="utf-8")

        with patch("agents.factory._GUARDRAILS_DIR", tmp_path):
            result = _compose_system_prompt(spec, ctx)

        g_pos = result.index("GUARDRAIL")
        s_pos = result.index("SKILL")
        h_pos = result.index("HOOK")
        b_pos = result.index("BODY")

        assert g_pos < s_pos < h_pos < b_pos

    def test_multiple_guardrails_injected_in_order(self, tmp_path):
        """Requirement 3.5: multiple guardrails injected in the order they appear in spec."""
        spec = _make_spec(guardrails=["agile", "typescript"], prompt_body="BODY")
        ctx = _make_ctx()

        (tmp_path / "agile.md").write_text("AGILE_CONTENT", encoding="utf-8")
        (tmp_path / "typescript.md").write_text("TS_CONTENT", encoding="utf-8")

        with patch("agents.factory._GUARDRAILS_DIR", tmp_path):
            result = _compose_system_prompt(spec, ctx)

        agile_pos = result.index("AGILE_CONTENT")
        ts_pos = result.index("TS_CONTENT")
        body_pos = result.index("BODY")

        assert agile_pos < ts_pos < body_pos

    def test_missing_guardrail_file_logs_warning_and_continues(self, tmp_path, caplog):
        """Requirement 3.3: missing guardrail file → warning logged, agent still runs."""
        spec = _make_spec(guardrails=["nonexistent_guardrail"], prompt_body="BODY")
        ctx = _make_ctx()

        with patch("agents.factory._GUARDRAILS_DIR", tmp_path):
            with caplog.at_level(logging.WARNING, logger="agents.factory"):
                result = _compose_system_prompt(spec, ctx)

        # Agent still runs — result contains the prompt body
        assert "BODY" in result
        # Warning was logged
        assert any("nonexistent_guardrail" in record.message for record in caplog.records)

    def test_missing_guardrail_file_produces_no_guardrail_block(self, tmp_path):
        """Requirement 3.3: missing guardrail → empty block (no ## Guardrail heading injected)."""
        spec = _make_spec(guardrails=["missing_one"], prompt_body="BODY")
        ctx = _make_ctx()

        with patch("agents.factory._GUARDRAILS_DIR", tmp_path):
            result = _compose_system_prompt(spec, ctx)

        # The guardrail heading should NOT appear since content is empty
        assert "## Guardrail: missing_one" not in result
        assert "BODY" in result

    def test_guardrail_content_appears_verbatim(self, tmp_path):
        """Requirement 3.2: guardrail file content appears verbatim in system prompt."""
        verbatim_content = "- Rule 1: Do this.\n- Rule 2: Don't do that.\n- Rule 3: Always check."
        spec = _make_spec(guardrails=["rules"], prompt_body="BODY")
        ctx = _make_ctx()

        (tmp_path / "rules.md").write_text(verbatim_content, encoding="utf-8")

        with patch("agents.factory._GUARDRAILS_DIR", tmp_path):
            result = _compose_system_prompt(spec, ctx)

        assert verbatim_content in result

    def test_skills_with_empty_content_are_skipped(self):
        """Skills with empty content key do not add blank blocks."""
        spec = _make_spec(prompt_body="BODY")
        ctx = _make_ctx(
            attached_skills=[{"name": "empty_skill", "content": ""}],
        )

        result = _compose_system_prompt(spec, ctx)

        # Should just be the body with no extra separators from empty skill
        assert result == "BODY"

    def test_hooks_with_empty_content_are_skipped(self):
        """Hooks with empty content key do not add blank blocks."""
        spec = _make_spec(prompt_body="BODY")
        ctx = _make_ctx(
            attached_hooks=[{"name": "empty_hook", "content": ""}],
        )

        result = _compose_system_prompt(spec, ctx)

        assert result == "BODY"

    def test_blocks_joined_with_double_newline(self, tmp_path):
        """All blocks are joined with double newlines."""
        spec = _make_spec(guardrails=["agile"], prompt_body="BODY")
        ctx = _make_ctx(attached_skills=[{"content": "SKILL"}])

        (tmp_path / "agile.md").write_text("GUARDRAIL", encoding="utf-8")

        with patch("agents.factory._GUARDRAILS_DIR", tmp_path):
            result = _compose_system_prompt(spec, ctx)

        # Blocks should be separated by \n\n
        assert "\n\n" in result


# ---------------------------------------------------------------------------
# create_agent — error propagation (Requirements 4.9, 4.10)
# ---------------------------------------------------------------------------


class TestCreateAgentErrorPropagation:
    """Verify that create_agent propagates loader errors without swallowing them."""

    def test_file_not_found_propagated(self, tmp_agent_dir):
        """Requirement 4.9: FileNotFoundError from loader is propagated."""
        ctx = _make_ctx()

        with pytest.raises(FileNotFoundError):
            create_agent("does-not-exist-at-all", ctx)

    def test_agent_spec_error_propagated(self, tmp_agent_dir):
        """Requirement 4.10: AgentSpecError from loader is propagated."""
        from agents.loader import AgentSpecError

        # Write an AGENT.md with an invalid pipeline_type to trigger AgentSpecError
        bad_content = make_agent_md(pipeline_type="not_a_valid_pipeline_type")
        create_agent_file(tmp_agent_dir, "bad-spec-agent", bad_content)
        ctx = _make_ctx()

        with pytest.raises(AgentSpecError):
            create_agent("bad-spec-agent", ctx)

    def test_create_agent_returns_deep_agent_instance(self, tmp_agent_dir):
        """create_agent returns a DeepAgent when everything is valid."""
        agent_id = "valid-agent"
        content = make_agent_md(id=agent_id, tools=[])
        create_agent_file(tmp_agent_dir, agent_id, content)
        ctx = _make_ctx()

        with patch("app.agents.deep_agent.DeepAgent") as MockDeepAgent:
            mock_instance = MagicMock()
            MockDeepAgent.return_value = mock_instance
            result = create_agent(agent_id, ctx)

        assert result is mock_instance
        MockDeepAgent.assert_called_once()

    def test_create_agent_passes_max_tokens_to_deep_agent(self, tmp_agent_dir):
        """create_agent passes spec.max_tokens to DeepAgent."""
        agent_id = "tokens-agent"
        content = make_agent_md(id=agent_id, max_tokens=8192, tools=[])
        create_agent_file(tmp_agent_dir, agent_id, content)
        ctx = _make_ctx()

        with patch("app.agents.deep_agent.DeepAgent") as MockDeepAgent:
            create_agent(agent_id, ctx)

        call_kwargs = MockDeepAgent.call_args.kwargs
        assert call_kwargs.get("max_tokens") == 8192


# ---------------------------------------------------------------------------
# Task 19.3 — Factory smoke test: first agent per pipeline has non-empty system_prompt
# ---------------------------------------------------------------------------


class TestFactorySmokeTest:
    """Smoke test: create_agent for the first agent (by order) of each pipeline type.

    Mocks DeepAgent to capture the system_prompt argument.
    Asserts the system_prompt is non-empty.
    Requirements: 9.2
    """

    _DEEP_AGENT_PATCH = "app.agents.deep_agent.DeepAgent"

    def _get_first_agent_per_pipeline(self) -> dict[str, str]:
        """Return {pipeline_type: first_agent_id} for all pipelines with agents."""
        from agents.loader import list_agent_ids, SUPPORTED_PIPELINE_TYPES

        result: dict[str, str] = {}
        for pipeline_type in sorted(SUPPORTED_PIPELINE_TYPES):
            ids = list_agent_ids(pipeline_type)
            if ids:
                result[pipeline_type] = ids[0]
        return result

    def test_first_agent_per_pipeline_has_non_empty_system_prompt(self):
        """For the first agent of each pipeline, create_agent must produce a non-empty system_prompt."""
        first_agents = self._get_first_agent_per_pipeline()
        assert first_agents, "No pipeline agents found — check agents/prompts/ directory"

        # Agents that declare an `injects` capability (prototype / od_ppt) require
        # an od_context with template/design-system content — the real engine
        # always supplies one for those pipelines. Provide a minimal stub here so
        # the smoke test exercises the injection path instead of tripping the
        # FR-008 missing-template guard.
        from agents.loader import load_agent_spec

        stub_od_context = {
            "template_id": "smoke-template",
            "template_body": "SMOKE TEMPLATE SKILL BODY",
            "ds_id": "smoke-ds",
            "ds_body": "SMOKE DESIGN TOKENS",
            "craft_block": "SMOKE CRAFT RULES",
            "is_design_system_required": True,
        }

        for pipeline_type, agent_id in first_agents.items():
            spec = load_agent_spec(agent_id)
            needs_od = bool(getattr(spec, "injects", []))
            ctx = AgentContext(
                user_request="Smoke test request",
                od_context=stub_od_context if needs_od else None,
            )
            captured: dict = {}

            def _make_capture(cap: dict):
                def _capture_deep_agent(system_prompt, tools, max_tokens, **kwargs):
                    cap["system_prompt"] = system_prompt
                    return MagicMock()
                return _capture_deep_agent

            with patch(self._DEEP_AGENT_PATCH, side_effect=_make_capture(captured)):
                create_agent(agent_id, ctx)

            assert "system_prompt" in captured, (
                f"Pipeline {pipeline_type!r}: DeepAgent was not instantiated"
            )
            assert captured["system_prompt"], (
                f"Pipeline {pipeline_type!r}, agent {agent_id!r}: system_prompt is empty"
            )
            assert captured["system_prompt"].strip(), (
                f"Pipeline {pipeline_type!r}, agent {agent_id!r}: system_prompt is blank"
            )
