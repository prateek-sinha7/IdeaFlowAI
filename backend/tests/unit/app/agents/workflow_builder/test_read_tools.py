"""Unit tests for ``app.agents.workflow_builder.read_tools``.

Covers the six placeholder tools: names, binding to the caller's ``user_id`` and
``tier``, fixed output fields, bounded lists, and the ``available: false`` answer
of ``PlaceholderReadPort`` (decision 13.8, pending Q-18).

Requirements: 27.7, 27.8, 39.5, 49.2.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.tools import BaseTool

from app.agents.workflow_builder.model_catalog_view import (
    BuilderModelView,
    builder_models,
)
from app.agents.workflow_builder.read_tools import (
    MAX_AGENTS,
    MAX_CONNECTORS,
    MAX_HANDOFF_TARGETS,
    MAX_SKILLS,
    MAX_SKILLS_PER_AGENT,
    MAX_SUMMARY_CHARS,
    MAX_WORKFLOW_NAMES,
    NOT_AVAILABLE_MESSAGE,
    AgentFact,
    ConnectorFact,
    PlaceholderReadPort,
    ReadNotAvailableError,
    SkillFact,
    WorkflowFact,
    build_read_tools,
)
from app.agents.workflow_builder.stages import READ_TOOL_NAMES

USER = "user-1"
TIER = "enterprise"


class _RecordingPort:
    """A port with canned facts that records the user id and tier it is asked for."""

    def __init__(self) -> None:
        self.agents: list[AgentFact] = [AgentFact("writer", "Writes text.", ("s1",))]
        self.skills: list[SkillFact] = [SkillFact("pdf", "global")]
        self.names: list[str] = ["alpha", "beta"]
        self.connectors: list[ConnectorFact] = [ConnectorFact("github")]
        self.targets: list[WorkflowFact] = [WorkflowFact("prototype", "Prototype")]
        self.calls: list[tuple[str, str]] = []

    def my_agents(self, user_id: str) -> list[AgentFact]:
        self.calls.append(("my_agents", user_id))
        return self.agents

    def my_skills(self, user_id: str) -> list[SkillFact]:
        self.calls.append(("my_skills", user_id))
        return self.skills

    def my_workflow_names(self, user_id: str) -> list[str]:
        self.calls.append(("my_workflow_names", user_id))
        return self.names

    def my_connectors(self, user_id: str) -> list[ConnectorFact]:
        self.calls.append(("my_connectors", user_id))
        return self.connectors

    def handoff_targets(self, tier: str) -> list[WorkflowFact]:
        self.calls.append(("handoff_targets", tier))
        return self.targets

    def builder_models(self, tier: str) -> BuilderModelView:
        self.calls.append(("builder_models", tier))
        return builder_models(tier)


def _tools(port: Any, *, user_id: str = USER, tier: str = TIER) -> dict[str, BaseTool]:
    return {t.name: t for t in build_read_tools(port, user_id=user_id, tier=tier)}


def _run(tools: dict[str, BaseTool], name: str) -> dict[str, Any]:
    return json.loads(tools[name].invoke({}))


def test_build_read_tools_returns_the_six_tools_when_called() -> None:
    tools = build_read_tools(_RecordingPort(), user_id=USER, tier=TIER)

    assert {t.name for t in tools} == READ_TOOL_NAMES
    assert len(tools) == 6


def test_build_read_tools_takes_no_arguments_when_tools_are_bound_to_the_caller() -> (
    None
):
    for tool in build_read_tools(_RecordingPort(), user_id=USER, tier=TIER):
        assert tool.args == {}, tool.name


def test_tools_pass_bound_user_id_and_tier_to_port_when_invoked() -> None:
    port = _RecordingPort()
    tools = _tools(port, user_id="u-42", tier="pro")

    for name in sorted(READ_TOOL_NAMES):
        tools[name].invoke({})

    assert sorted(port.calls) == [
        ("builder_models", "pro"),
        ("handoff_targets", "pro"),
        ("my_agents", "u-42"),
        ("my_connectors", "u-42"),
        ("my_skills", "u-42"),
        ("my_workflow_names", "u-42"),
    ]


def test_list_my_agents_returns_fixed_fields_when_agent_exists() -> None:
    result = _run(_tools(_RecordingPort()), "list_my_agents")

    assert result == {
        "available": True,
        "agents": [
            {"name": "writer", "prompt_summary": "Writes text.", "skills": ["s1"]}
        ],
        "count": 1,
        "truncated": False,
    }


def test_list_my_agents_bounds_output_when_data_is_large() -> None:
    port = _RecordingPort()
    port.agents = [
        AgentFact(
            f"a{i}",
            "x" * 1000,
            tuple(f"s{n}" for n in range(MAX_SKILLS_PER_AGENT + 5)),
        )
        for i in range(MAX_AGENTS + 3)
    ]

    result = _run(_tools(port), "list_my_agents")

    assert result["count"] == MAX_AGENTS
    assert result["truncated"] is True
    first = result["agents"][0]
    assert len(first["prompt_summary"]) <= MAX_SUMMARY_CHARS
    assert first["prompt_summary"].endswith("\u2026")
    assert len(first["skills"]) == MAX_SKILLS_PER_AGENT


def test_list_my_skills_returns_id_and_source_only_when_skills_exist() -> None:
    result = _run(_tools(_RecordingPort()), "list_my_skills")

    assert result["skills"] == [{"id": "pdf", "source": "global"}]
    assert result["truncated"] is False


def test_list_my_skills_truncates_when_over_limit() -> None:
    port = _RecordingPort()
    port.skills = [SkillFact(f"s{i}", "user") for i in range(MAX_SKILLS + 1)]

    result = _run(_tools(port), "list_my_skills")

    assert (result["count"], result["truncated"]) == (MAX_SKILLS, True)


def test_list_my_workflow_names_drops_duplicates_when_names_repeat() -> None:
    port = _RecordingPort()
    port.names = ["alpha", "beta", "alpha"]

    result = _run(_tools(port), "list_my_workflow_names")

    assert result["names"] == ["alpha", "beta"]
    assert result["count"] == 2


def test_list_my_workflow_names_truncates_when_over_limit() -> None:
    port = _RecordingPort()
    port.names = [f"n{i}" for i in range(MAX_WORKFLOW_NAMES + 1)]

    result = _run(_tools(port), "list_my_workflow_names")

    assert (result["count"], result["truncated"]) == (MAX_WORKFLOW_NAMES, True)


def test_list_my_connectors_returns_server_name_only_when_connector_exists() -> None:
    result = _run(_tools(_RecordingPort()), "list_my_connectors")

    assert result["connectors"] == [{"server_name": "github"}]


def test_list_my_connectors_truncates_when_over_limit() -> None:
    port = _RecordingPort()
    port.connectors = [ConnectorFact(f"c{i}") for i in range(MAX_CONNECTORS + 1)]

    result = _run(_tools(port), "list_my_connectors")

    assert (result["count"], result["truncated"]) == (MAX_CONNECTORS, True)


def test_list_handoff_targets_returns_id_and_display_name_when_target_exists() -> None:
    result = _run(_tools(_RecordingPort()), "list_handoff_targets")

    assert result["targets"] == [{"id": "prototype", "display_name": "Prototype"}]


def test_list_handoff_targets_truncates_when_over_limit() -> None:
    port = _RecordingPort()
    port.targets = [
        WorkflowFact(f"w{i}", f"W{i}") for i in range(MAX_HANDOFF_TARGETS + 1)
    ]

    result = _run(_tools(port), "list_handoff_targets")

    assert (result["count"], result["truncated"]) == (MAX_HANDOFF_TARGETS, True)


def test_get_builder_models_lists_catalog_models_when_port_serves_catalog() -> None:
    view = builder_models(TIER)

    result = _run(_tools(PlaceholderReadPort()), "get_builder_models")

    assert result["available"] is True
    assert [m["id"] for m in result["chat"]] == [e.id for e in view.chat]
    assert [m["id"] for m in result["step"]] == [e.id for e in view.step]
    assert result["default_chat_id"] == view.default_chat_id
    assert result["chat"], "the enterprise tier must offer at least one chat model"
    assert set(result["chat"][0]) == {"id", "label", "cost_class", "levels"}
    assert isinstance(result["chat"][0]["levels"], list)


def test_placeholder_port_binds_only_get_builder_models_when_tools_are_built() -> None:
    names = {
        t.name for t in build_read_tools(PlaceholderReadPort(), user_id=USER, tier=TIER)
    }

    assert names == {"get_builder_models"}


def test_placeholder_port_raises_not_available_when_user_data_is_read() -> None:
    port = PlaceholderReadPort()

    with pytest.raises(ReadNotAvailableError, match=NOT_AVAILABLE_MESSAGE):
        port.my_agents(USER)
    with pytest.raises(ReadNotAvailableError):
        port.my_skills(USER)
    with pytest.raises(ReadNotAvailableError):
        port.my_workflow_names(USER)
    with pytest.raises(ReadNotAvailableError):
        port.my_connectors(USER)
    with pytest.raises(ReadNotAvailableError):
        port.handoff_targets(TIER)


def test_placeholder_port_returns_catalog_view_when_models_are_read() -> None:
    assert PlaceholderReadPort().builder_models(TIER) == builder_models(TIER)
