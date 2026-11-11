"""Connected-app grants in ``WorkflowCompiler`` (design 5.5 layers 1 and 2).

Covers ``_validate_connector_grant`` (predefined refusal naming the step, name
shape, length, unknown connector, undeclared Jira tool, de-duplication), the
``admits_connector_grants`` plan flag per trust level, and that the unchanged
``tools.mcp`` slot is still validated beside ``tools.connectors``.
"""

from __future__ import annotations

import pytest

from agents.capabilities.registry import CapabilityRegistry, discover
from agents.workflows.compiler import (
    CompilerError,
    ConnectorGrantsNotAllowed,
    WorkflowCompiler,
)
from agents.workflows.manifest import WorkflowManifest

_JIRA = "jira__get_issue"
_GITHUB = "github__list_issues"


@pytest.fixture(autouse=True)
def _discovered() -> None:
    discover()


def _manifest(*steps: dict) -> WorkflowManifest:
    return WorkflowManifest(
        id="connector-demo",
        steps=list(steps),
        deliverable={},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
    )


def _step(agent: str = "demo-agent", **tools: object) -> dict:
    step: dict = {"agent": agent, "strategy": "single_shot"}
    if tools:
        step["tools"] = dict(tools)
    return step


def _compile(manifest: WorkflowManifest, trust: str):
    return WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust=trust)


class TestPredefinedRefusal:
    @pytest.mark.parametrize("trust", ["file", "builtin"])
    def test_compile_raises_naming_step_when_predefined_manifest_names_connectors(
        self, trust: str
    ) -> None:
        manifest = _manifest(_step("demo-agent", connectors=[_JIRA]))

        with pytest.raises(ConnectorGrantsNotAllowed) as excinfo:
            _compile(manifest, trust)

        message = str(excinfo.value)
        assert "predefined workflows cannot use connected apps" in message
        assert "save the workflow as your own" in message
        assert "demo-agent" in message

    def test_compile_raises_when_trust_is_unknown(self) -> None:
        manifest = _manifest(_step(connectors=[_JIRA]))

        with pytest.raises(ConnectorGrantsNotAllowed):
            _compile(manifest, "somebody-else")

    def test_connector_grants_not_allowed_is_a_compiler_error_when_raised(self) -> None:
        assert issubclass(ConnectorGrantsNotAllowed, CompilerError)

    @pytest.mark.parametrize("trust", ["file", "builtin", "db", "user"])
    def test_compile_succeeds_when_connectors_list_is_empty(self, trust: str) -> None:
        plan = _compile(_manifest(_step(connectors=[])), trust)

        assert plan.steps[0].tools.connectors == []


class TestAdmittedTrust:
    @pytest.mark.parametrize("trust", ["db", "user"])
    def test_compile_keeps_grant_on_step_when_trust_is_user_authored(
        self, trust: str
    ) -> None:
        plan = _compile(_manifest(_step(connectors=[_JIRA, _GITHUB])), trust)

        assert plan.steps[0].tools.connectors == [_JIRA, _GITHUB]

    def test_compile_removes_duplicates_in_order_when_grant_repeats_names(self) -> None:
        grant = [_GITHUB, _JIRA, _GITHUB, _JIRA, "jira__search_issues"]

        plan = _compile(_manifest(_step(connectors=grant)), "user")

        assert plan.steps[0].tools.connectors == [_GITHUB, _JIRA, "jira__search_issues"]

    def test_compile_accepts_any_github_tool_name_when_shape_is_valid(self) -> None:
        # GitHub tools are discovered at run time, so only the shape is checked.
        plan = _compile(_manifest(_step(connectors=["github__brand_new_tool"])), "user")

        assert plan.steps[0].tools.connectors == ["github__brand_new_tool"]

    def test_compile_accepts_exactly_sixty_four_entries_when_at_the_limit(self) -> None:
        names = [f"github__tool_{i}" for i in range(64)]

        plan = _compile(_manifest(_step(connectors=names)), "user")

        assert len(plan.steps[0].tools.connectors) == 64


class TestRejectedGrants:
    @pytest.mark.parametrize(
        "bad",
        [
            "jira",
            "jira__",
            "__get_issue",
            "Jira__get_issue",
            "jira_get_issue",
            "jira__get issue",
            "j__get_issue",
            "jira__-leading_dash",
            "jira__get_issue\n",
            "jira.get_issue",
        ],
    )
    def test_compile_raises_when_entry_does_not_match_the_name_shape(
        self, bad: str
    ) -> None:
        with pytest.raises(CompilerError, match="not a valid tool name"):
            _compile(_manifest(_step(connectors=[bad])), "user")

    def test_compile_raises_when_entry_is_longer_than_sixty_four_characters(
        self,
    ) -> None:
        name = "github__" + "a" * 57  # 65 characters

        with pytest.raises(CompilerError, match="not a valid tool name"):
            _compile(_manifest(_step(connectors=[name])), "user")

    def test_compile_raises_when_more_than_sixty_four_entries_are_listed(self) -> None:
        names = [f"github__tool_{i}" for i in range(65)]

        with pytest.raises(CompilerError, match="at most 64"):
            _compile(_manifest(_step(connectors=names)), "user")

    def test_compile_raises_when_connector_key_is_unknown(self) -> None:
        with pytest.raises(CompilerError, match="unknown connector 'slack'"):
            _compile(_manifest(_step(connectors=["slack__post_message"])), "user")

    def test_compile_raises_when_jira_tool_is_not_declared(self) -> None:
        with pytest.raises(CompilerError, match="not a tool of connector 'jira'"):
            _compile(_manifest(_step(connectors=["jira__delete_project"])), "user")

    @pytest.mark.parametrize("value", ["jira__get_issue", 5, {"a": 1}, [1, 2], [None]])
    def test_compile_raises_when_connectors_is_not_a_list_of_strings(
        self, value: object
    ) -> None:
        with pytest.raises(CompilerError, match="list of tool-name strings"):
            _compile(_manifest(_step(connectors=value)), "user")


class TestAdmitsFlag:
    @pytest.mark.parametrize(
        ("trust", "expected"),
        [
            ("db", True),
            ("user", True),
            ("file", False),
            ("builtin", False),
            ("unknown", False),
        ],
    )
    def test_compile_stamps_admits_flag_when_compiled_at_trust(
        self, trust: str, expected: bool
    ) -> None:
        plan = _compile(_manifest(_step()), trust)

        assert plan.admits_connector_grants is expected

    def test_admits_connector_grants_defaults_false_when_plan_is_built_directly(
        self,
    ) -> None:
        from agents.workflows.plan import CompiledWorkflow

        assert CompiledWorkflow(id="x").admits_connector_grants is False


class TestMcpSlotUnchanged:
    def test_compile_validates_mcp_and_accepts_connectors_when_both_are_declared(
        self,
    ) -> None:
        plan = _compile(
            _manifest(
                _step(mcp=["jira.search_issues"], connectors=[_JIRA]),
            ),
            "db",
        )

        assert plan.steps[0].tools.connectors == [_JIRA]
        # tools.mcp still compiles and is capped to nothing, exactly as before.
        assert plan.steps[0].tools.mcp == []

    def test_compile_still_rejects_unknown_mcp_tool_when_connectors_are_declared(
        self,
    ) -> None:
        manifest = _manifest(_step(mcp=["github.delete_repo"], connectors=[_JIRA]))

        with pytest.raises(CompilerError):
            _compile(manifest, "user")
