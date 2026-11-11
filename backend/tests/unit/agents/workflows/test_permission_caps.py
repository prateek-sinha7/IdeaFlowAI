"""Unit tests for the connected-app decisions in ``agents.workflows.permission_caps``.

Pure data: no registry, no kernel, no app import. Covers the trust decision, the
cap application, the run-level union, the per-step filter and the two helpers the
selections overlay uses (design 5.5 layers 2 and 3).
"""

from __future__ import annotations

import dataclasses

import pytest

from agents.workflows import permission_caps as caps
from agents.workflows.plan import CompiledWorkflow, Step, ToolPermissions


def _step(agent_id: str, connectors: list[str] | None = None) -> Step:
    return Step(
        agent_id=agent_id,
        tools=ToolPermissions(connectors=list(connectors or [])),
    )


def _plan(*steps: Step, admits: bool = True) -> CompiledWorkflow:
    return CompiledWorkflow(
        id="demo", steps=list(steps), admits_connector_grants=admits
    )


class TestConnectorGrantsPermitted:
    @pytest.mark.parametrize("trust", ["db", "user"])
    def test_connector_grants_permitted_true_when_trust_is_user_authored(
        self, trust: str
    ) -> None:
        assert caps.connector_grants_permitted(trust) is True

    @pytest.mark.parametrize("trust", ["file", "builtin", "", None, "admin", "DB"])
    def test_connector_grants_permitted_false_when_trust_is_predefined_or_unknown(
        self, trust: str | None
    ) -> None:
        assert caps.connector_grants_permitted(trust) is False

    def test_connector_grant_trust_levels_is_exactly_db_and_user(self) -> None:
        assert caps.CONNECTOR_GRANT_TRUST_LEVELS == frozenset({"db", "user"})


class TestApplyCap:
    @pytest.mark.parametrize("trust", ["db", "user"])
    def test_apply_cap_keeps_connectors_when_trust_is_user_authored(
        self, trust: str
    ) -> None:
        grant = ToolPermissions(connectors=["jira__get_issue", "github__list_issues"])

        effective = caps.apply_cap(grant, trust)

        assert effective.connectors == ["jira__get_issue", "github__list_issues"]

    @pytest.mark.parametrize("trust", ["file", "builtin", "nonsense", None])
    def test_apply_cap_drops_connectors_when_trust_is_predefined_or_unknown(
        self, trust: str | None
    ) -> None:
        grant = ToolPermissions(connectors=["jira__get_issue"])

        effective = caps.apply_cap(grant, trust)

        assert effective.connectors == []

    def test_apply_cap_returns_a_copy_when_connectors_are_kept(self) -> None:
        grant = ToolPermissions(connectors=["jira__get_issue"])

        effective = caps.apply_cap(grant, "user")
        effective.connectors.append("jira__create_issue")

        assert grant.connectors == ["jira__get_issue"]

    @pytest.mark.parametrize("cap_key", sorted(caps.PERMISSION_CAP_INDEX))
    def test_cap_rows_carry_empty_connector_mcp_and_integration_lists_when_listed(
        self, cap_key: str
    ) -> None:
        row = caps.PERMISSION_CAP_INDEX[cap_key]

        assert row.connectors == []
        assert row.mcp == []
        assert row.integrations == []

    @pytest.mark.parametrize("trust", ["file", "builtin", "db", "user"])
    def test_apply_cap_gives_empty_mcp_and_integrations_when_requested(
        self, trust: str
    ) -> None:
        grant = ToolPermissions(mcp=["jira.search_issues"], integrations=["jira_read"])

        effective = caps.apply_cap(grant, trust)

        assert effective.mcp == []
        assert effective.integrations == []


class TestVocabulary:
    def test_connectors_is_a_grant_list_field_beside_mcp_and_integrations(self) -> None:
        assert "connectors" in caps.GRANT_LIST_FIELDS
        assert {"mcp", "integrations"} <= set(caps.GRANT_LIST_FIELDS)
        assert "connectors" in caps.ALLOWED_GRANT_KEYS

    def test_parse_grant_reads_connectors_when_declared(self) -> None:
        grant = caps.parse_grant({"connectors": ["jira__get_issue"]})

        assert grant.connectors == ["jira__get_issue"]

    def test_tool_permissions_defaults_to_no_connectors_when_undeclared(self) -> None:
        assert ToolPermissions().connectors == []


class TestConnectorToolGrants:
    def test_connector_tool_grants_returns_union_when_plan_admits(self) -> None:
        plan = _plan(
            _step("a", ["jira__get_issue", "github__list_issues"]),
            _step("b", ["jira__get_issue", "jira__search_issues"]),
        )

        assert caps.connector_tool_grants(plan) == frozenset(
            {"jira__get_issue", "github__list_issues", "jira__search_issues"}
        )

    def test_connector_tool_grants_is_empty_when_plan_does_not_admit(self) -> None:
        plan = _plan(_step("a", ["jira__get_issue"]), admits=False)

        assert caps.connector_tool_grants(plan) == frozenset()

    def test_connector_tool_grants_is_empty_when_no_step_grants(self) -> None:
        assert caps.connector_tool_grants(_plan(_step("a"), _step("b"))) == frozenset()

    def test_connector_tool_grants_is_empty_when_plan_has_no_steps(self) -> None:
        assert caps.connector_tool_grants(_plan()) == frozenset()


class TestBoundConnectorTools:
    def test_bound_connector_tools_returns_nothing_when_step_tools_is_none(
        self,
    ) -> None:
        assert caps.bound_connector_tools(None, {"jira__get_issue": object()}) == []

    def test_bound_connector_tools_returns_nothing_when_pool_is_empty(self) -> None:
        grant = ToolPermissions(connectors=["jira__get_issue"])

        assert caps.bound_connector_tools(grant, {}) == []
        assert caps.bound_connector_tools(grant, None) == []

    def test_bound_connector_tools_skips_names_missing_from_pool_when_granted(
        self,
    ) -> None:
        tool = object()
        grant = ToolPermissions(connectors=["jira__missing", "jira__get_issue"])

        assert caps.bound_connector_tools(grant, {"jira__get_issue": tool}) == [tool]

    def test_bound_connector_tools_follows_grant_order_when_pool_order_differs(
        self,
    ) -> None:
        first, second = object(), object()
        pool = {"github__b": second, "jira__a": first}
        grant = ToolPermissions(connectors=["jira__a", "github__b"])

        assert caps.bound_connector_tools(grant, pool) == [first, second]

    def test_bound_connector_tools_never_returns_ungranted_pool_entries_when_pooled(
        self,
    ) -> None:
        granted, other = object(), object()
        pool = {"jira__get_issue": granted, "jira__create_issue": other}
        grant = ToolPermissions(connectors=["jira__get_issue"])

        assert caps.bound_connector_tools(grant, pool) == [granted]

    def test_bound_connector_tools_returns_each_tool_once_when_grant_has_duplicates(
        self,
    ) -> None:
        tool = object()
        grant = ToolPermissions(connectors=["jira__get_issue", "jira__get_issue"])

        assert caps.bound_connector_tools(grant, {"jira__get_issue": tool}) == [tool]


class TestOverlayToolSlots:
    def test_overlay_tool_slots_keeps_connectors_when_plan_admits(self) -> None:
        named = {"write_files": True, "connectors": ["jira__get_issue"]}

        assert caps.overlay_tool_slots(named, admits=True) == named

    def test_overlay_tool_slots_drops_connectors_when_plan_does_not_admit(self) -> None:
        named = {"write_files": True, "connectors": ["jira__get_issue"]}

        assert caps.overlay_tool_slots(named, admits=False) == {"write_files": True}

    def test_overlay_tool_slots_does_not_mutate_input_when_dropping(self) -> None:
        named = {"connectors": ["jira__get_issue"]}

        caps.overlay_tool_slots(named, admits=False)

        assert named == {"connectors": ["jira__get_issue"]}


class TestWithoutConnectorGrants:
    def test_without_connector_grants_clears_the_slot_when_step_has_grants(
        self,
    ) -> None:
        step = _step("a", ["jira__get_issue"])

        stripped = caps.without_connector_grants(step)

        assert stripped.tools.connectors == []
        assert step.tools.connectors == ["jira__get_issue"]

    def test_without_connector_grants_keeps_other_permissions_when_clearing(
        self,
    ) -> None:
        step = dataclasses.replace(
            _step("a", ["jira__get_issue"]),
            tools=ToolPermissions(write_files=True, connectors=["jira__get_issue"]),
        )

        assert caps.without_connector_grants(step).tools.write_files is True

    def test_without_connector_grants_returns_same_step_when_already_empty(
        self,
    ) -> None:
        step = _step("a")

        assert caps.without_connector_grants(step) is step
