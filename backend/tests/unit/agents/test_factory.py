"""Unit tests for agents/factory.py::_resolve_step_skills against the catalog root."""

from __future__ import annotations

import pytest

from types import SimpleNamespace

import pytest

import app.agents.skills_catalog as skills_catalog
from agents.factory import AgentContext, _resolve_runner_tools, _resolve_step_skills
from agents.workflows.plan import ToolPermissions
from tests.factories.skill_catalog_factory import write_catalog_skill


@pytest.fixture(autouse=True)
def _cold_catalog_cache():
    """Empty the process-wide catalog cache around each test so no scan leaks across."""
    skills_catalog.clear_cache()
    yield
    skills_catalog.clear_cache()


def test_agent_context_run_tools_defaults_empty_and_unshared_when_two_contexts_built() -> (
    None
):
    """``AgentContext.run_tools`` defaults to an empty, per-instance mapping."""
    first = AgentContext(user_request="a")
    second = AgentContext(user_request="b")

    first.run_tools["jira__get_issue"] = object()  # type: ignore[index]

    assert dict(second.run_tools) == {}
    assert first.run_tools is not second.run_tools


def test_resolve_step_skills_returns_payload_when_catalog_served_from_baked_root(
    tmp_path, monkeypatch
):
    # Arrange
    write_catalog_skill(tmp_path, "alpha")
    monkeypatch.setattr(skills_catalog, "_GLOBAL_SKILL_DIR", tmp_path)

    # Act
    resolved = _resolve_step_skills(["alpha"])

    # Assert
    assert resolved == [{"id": "alpha", "name": "alpha", "content": "Body of alpha."}]


def test_resolve_step_skills_raises_assertion_when_id_absent_from_catalog(
    tmp_path, monkeypatch
):
    # Arrange — an unresolvable manifest skill stays a loud failure, never a silent drop.
    monkeypatch.setattr(skills_catalog, "_GLOBAL_SKILL_DIR", tmp_path)

    # Act / Assert
    with pytest.raises(AssertionError, match="unresolvable step skill id: ghost"):
        _resolve_step_skills(["ghost"])


class _TextOnlySpec:
    """A text-only agent: no declared tool set, so only step grants can bind tools."""

    tools: list = []


class _Sandbox:
    root = "/tmp/nowhere"


def _connector_tool(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


class TestConnectorToolBinding:
    """The factory gives each step only the connector tools its own grant names."""

    def test_resolve_runner_tools_binds_only_granted_connector_tools_when_pool_holds_more(
        self,
    ) -> None:
        jira = _connector_tool("jira__get_issue")
        github = _connector_tool("github__list_issues")
        ctx = AgentContext(
            user_request="x",
            step_tools=ToolPermissions(connectors=["jira__get_issue"]),
            run_tools={"jira__get_issue": jira, "github__list_issues": github},
        )

        tools, _ = _resolve_runner_tools(_TextOnlySpec(), ctx)

        assert [t.name for t in tools] == ["jira__get_issue"]
        assert tools[0] is jira

    def test_resolve_runner_tools_binds_grant_in_grant_order_when_step_lists_several(
        self,
    ) -> None:
        jira = _connector_tool("jira__get_issue")
        github = _connector_tool("github__list_issues")
        ctx = AgentContext(
            user_request="x",
            step_tools=ToolPermissions(
                connectors=["github__list_issues", "jira__get_issue"]
            ),
            run_tools={"jira__get_issue": jira, "github__list_issues": github},
        )

        tools, _ = _resolve_runner_tools(_TextOnlySpec(), ctx)

        assert [t.name for t in tools] == ["github__list_issues", "jira__get_issue"]

    def test_resolve_runner_tools_binds_nothing_when_step_grants_no_connector(
        self,
    ) -> None:
        ctx = AgentContext(
            user_request="x",
            step_tools=ToolPermissions(connectors=[]),
            run_tools={"jira__get_issue": _connector_tool("jira__get_issue")},
        )

        tools, _ = _resolve_runner_tools(_TextOnlySpec(), ctx)

        assert tools == []

    def test_resolve_runner_tools_binds_nothing_when_no_compiled_step_is_bound(
        self,
    ) -> None:
        ctx = AgentContext(
            user_request="x",
            step_tools=None,
            run_tools={"jira__get_issue": _connector_tool("jira__get_issue")},
        )

        tools, _ = _resolve_runner_tools(_TextOnlySpec(), ctx)

        assert tools == []

    def test_resolve_runner_tools_skips_granted_name_when_pool_lacks_it(self) -> None:
        ctx = AgentContext(
            user_request="x",
            step_tools=ToolPermissions(connectors=["jira__search_issues"]),
            run_tools={"jira__get_issue": _connector_tool("jira__get_issue")},
        )

        tools, _ = _resolve_runner_tools(_TextOnlySpec(), ctx)

        assert tools == []

    def test_resolve_runner_tools_keeps_declared_tools_and_appends_connector_tools_when_both_present(
        self,
    ) -> None:
        jira = _connector_tool("jira__get_issue")
        ctx = AgentContext(
            user_request="x",
            step_tools=ToolPermissions(
                tool_sets=["file_extract"], connectors=["jira__get_issue"]
            ),
            run_tools={"jira__get_issue": jira},
        )

        tools, _ = _resolve_runner_tools(_TextOnlySpec(), ctx, sandbox=_Sandbox())

        names = [
            getattr(t, "name", None) or getattr(t, "__name__", None) for t in tools
        ]
        assert {"extract_text", "file_info", "file_find", "file_page_image"} <= set(
            names
        )
        assert names.count("jira__get_issue") == 1
        assert tools[-1] is jira
