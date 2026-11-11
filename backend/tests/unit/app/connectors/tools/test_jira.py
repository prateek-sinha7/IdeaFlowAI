"""Jira native tools against an in-memory Jira API (``FakeJiraApi``)."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest
from langchain_core.tools import StructuredTool

from agents.capabilities.connector_catalog import JIRA
from app.connectors.tools.jira import (
    TOOL_TABLE,
    JiraSite,
    build_jira_tools,
    resolve_site,
)
from app.connectors.errors import ConnectorError, ToolErrorCode
from app.connectors.tools.names import format_tool_name
from tests.fakes.connector_services import ConnectorWorld, build_world
from tests.fakes.connector_settings import make_settings
from tests.fakes.connector_tool_world import connect, tool_runtime
from tests.fakes.jira_api import FakeJiraApi, load_fixture, reply
from tests.fakes.oauth_provider import (
    ATLASSIAN_SITES_URL,
    ATLASSIAN_TOKEN_URL,
    atlassian_token_body,
    jira_site,
    json_response,
)

USER = "user-a"
CONFIG = {"configurable": {"thread_id": "run-1:agent-a"}}
ALL_NAMES = {format_tool_name("jira", spec.name) for spec in JIRA.tooling.native_tools}


def _setup(
    *, connected: bool = True, world: ConnectorWorld | None = None
) -> tuple[ConnectorWorld, FakeJiraApi, dict[str, StructuredTool]]:
    world = world or build_world()
    api = FakeJiraApi()
    if connected:
        connect(world, USER, "jira")
    tools = build_jira_tools(
        runtime=tool_runtime(world, api.client_factory),
        definition=JIRA,
        user_id=USER,
        run_id="run-1",
        requested=ALL_NAMES,
    )
    return world, api, tools


async def _call(tools: dict[str, StructuredTool], name: str, **arguments: Any) -> Any:
    raw = await tools[f"jira__{name}"].ainvoke(arguments, config=CONFIG)
    return json.loads(raw)


class TestBuildJiraTools:
    def test_build_jira_tools_returns_only_requested_tools_when_subset_requested(
        self,
    ) -> None:
        world = build_world()
        runtime = tool_runtime(world, FakeJiraApi().client_factory)

        tools = build_jira_tools(
            runtime=runtime,
            definition=JIRA,
            user_id=USER,
            run_id=None,
            requested={"jira__get_issue", "github__list_issues", "jira__nope"},
        )

        assert set(tools) == {"jira__get_issue"}

    def test_build_jira_tools_covers_every_declared_tool_when_all_requested(
        self,
    ) -> None:
        _world, _api, tools = _setup(connected=False)

        assert set(tools) == ALL_NAMES
        assert {spec.name for spec in JIRA.tooling.native_tools} == set(TOOL_TABLE)

    def test_build_jira_tools_flags_exactly_the_write_tools_when_built(self) -> None:
        _world, _api, tools = _setup(connected=False)

        writes = {
            name
            for name, tool in tools.items()
            if tool.metadata and tool.metadata["write_capable"]
        }

        assert writes == {
            "jira__create_issue",
            "jira__update_issue",
            "jira__add_comment",
            "jira__transition_issue",
            "jira__assign_issue",
        }

    def test_build_jira_tools_makes_no_network_call_when_built(self) -> None:
        _world, api, _tools = _setup()

        assert api.calls == []


class TestReadTools:
    @pytest.mark.asyncio
    async def test_search_issues_returns_compact_issues_when_jira_answers(self) -> None:
        world, api, tools = _setup()
        api.respond("POST", "/search/jql", (200, load_fixture("jira_search.json")))

        result = await _call(tools, "search_issues", jql="project = ABC", max_results=2)

        assert result == {
            "issues": [
                {
                    "key": "ABC-1",
                    "summary": "Login page returns 500",
                    "status": "In Progress",
                    "assignee": "Ada Lovelace",
                    "updated": "2026-05-01T10:00:00.000+0000",
                    "url": "https://acme.atlassian.net/browse/ABC-1",
                },
                {
                    "key": "ABC-2",
                    "summary": "Update onboarding copy",
                    "status": "To Do",
                    "assignee": None,
                    "updated": "2026-05-02T09:30:00.000+0000",
                    "url": "https://acme.atlassian.net/browse/ABC-2",
                },
            ],
            "next_page_token": "page-2-token",
        }
        (call,) = api.calls
        assert call.cloud_id == "cloud-1"
        assert call.body["jql"] == "project = ABC"
        assert call.body["maxResults"] == 2
        assert "nextPageToken" not in call.body
        assert call.bearer == "atl_access_initial"
        assert world.store.audit[-1].tool_name == "jira__search_issues"

    @pytest.mark.asyncio
    async def test_search_issues_sends_page_token_and_default_limit_when_given(
        self,
    ) -> None:
        _world, api, tools = _setup()
        api.respond("POST", "/search/jql", (200, {"issues": []}))

        result = await _call(tools, "search_issues", jql="a", next_page_token="tok")

        assert result == {"issues": [], "next_page_token": None}
        assert api.calls[0].body["nextPageToken"] == "tok"
        assert api.calls[0].body["maxResults"] == 20

    @pytest.mark.asyncio
    async def test_get_issue_returns_detail_with_plain_text_description_when_found(
        self,
    ) -> None:
        _world, api, tools = _setup()
        api.respond("GET", "/issue/ABC-1", (200, load_fixture("jira_issue.json")))

        result = await _call(tools, "get_issue", issue_key="ABC-1")

        assert result["key"] == "ABC-1"
        assert result["issue_type"] == "Bug"
        assert result["priority"] == "High"
        assert result["reporter"] == "Grace Hopper"
        assert result["labels"] == ["backend", "login"]
        assert result["description"].startswith("Users see a 500 after sign in.")
        assert "- Check the auth logs" in result["description"]
        assert "fields" in api.calls[0].params
        assert result["url"] == "https://acme.atlassian.net/browse/ABC-1"

    @pytest.mark.asyncio
    async def test_get_issue_reports_not_found_with_key_when_jira_answers_404(
        self,
    ) -> None:
        _world, api, tools = _setup()
        api.respond(
            "GET", "/issue/ABC-9", (404, {"errorMessages": ["Issue does not exist"]})
        )

        result = await _call(tools, "get_issue", issue_key="ABC-9")

        assert result["error"]["code"] == "not_found"
        assert result["error"]["message"] == "Jira issue ABC-9 was not found"

    @pytest.mark.asyncio
    async def test_list_projects_returns_projects_when_jira_answers(self) -> None:
        _world, api, tools = _setup()
        api.respond("GET", "/project/search", (200, load_fixture("jira_projects.json")))

        result = await _call(tools, "list_projects", query="ops", max_results=5)

        assert result["projects"][1] == {
            "key": "OPS",
            "name": "Operations",
            "type": "business",
        }
        assert api.calls[0].params == {"maxResults": "5", "query": "ops"}

    @pytest.mark.asyncio
    async def test_get_comments_returns_plain_text_bodies_when_jira_answers(
        self,
    ) -> None:
        _world, api, tools = _setup()
        api.respond(
            "GET", "/issue/ABC-1/comment", (200, load_fixture("jira_comments.json"))
        )

        result = await _call(tools, "get_comments", issue_key="ABC-1")

        assert result["comments"] == [
            {
                "id": "20001",
                "author": "Grace Hopper",
                "created": "2026-05-01T11:00:00.000+0000",
                "body": "Seen on staging\nand in production",
            }
        ]

    @pytest.mark.asyncio
    async def test_list_transitions_returns_ids_and_targets_when_jira_answers(
        self,
    ) -> None:
        _world, api, tools = _setup()
        api.respond(
            "GET",
            "/issue/ABC-1/transitions",
            (200, load_fixture("jira_transitions.json")),
        )

        result = await _call(tools, "list_transitions", issue_key="ABC-1")

        assert result["transitions"][0] == {
            "id": "31",
            "name": "Start progress",
            "to": "In Progress",
        }


class TestWriteTools:
    @pytest.mark.asyncio
    async def test_create_issue_sends_adf_description_and_returns_url_when_created(
        self,
    ) -> None:
        _world, api, tools = _setup()
        api.respond(
            "POST", "/issue", (201, {"id": "10050", "key": "ABC-50", "self": "x"})
        )

        result = await _call(
            tools,
            "create_issue",
            project_key="ABC",
            issue_type="Task",
            summary="Write docs",
            description="First line\n\nSecond",
            labels=["docs", "p2"],
        )

        assert result == {
            "key": "ABC-50",
            "id": "10050",
            "url": "https://acme.atlassian.net/browse/ABC-50",
        }
        fields = api.calls[0].body["fields"]
        assert fields["project"] == {"key": "ABC"}
        assert fields["issuetype"] == {"name": "Task"}
        assert fields["labels"] == ["docs", "p2"]
        assert fields["description"]["type"] == "doc"
        assert len(fields["description"]["content"]) == 2

    @pytest.mark.asyncio
    async def test_create_issue_omits_description_when_it_is_blank(self) -> None:
        _world, api, tools = _setup()
        api.respond("POST", "/issue", (201, {"id": "1", "key": "ABC-1"}))

        await _call(
            tools,
            "create_issue",
            project_key="ABC",
            issue_type="Bug",
            summary="s",
            description="  ",
        )

        assert "description" not in api.calls[0].body["fields"]

    @pytest.mark.asyncio
    async def test_update_issue_sends_only_given_fields_when_partial_update(
        self,
    ) -> None:
        _world, api, tools = _setup()
        api.respond("PUT", "/issue/ABC-1", (204, None))

        result = await _call(
            tools, "update_issue", issue_key="ABC-1", summary="New title"
        )

        assert result["updated"] is True
        assert api.calls[0].body == {"fields": {"summary": "New title"}}

    @pytest.mark.asyncio
    async def test_update_issue_rejects_call_when_nothing_to_change(self) -> None:
        _world, api, tools = _setup()

        result = await _call(tools, "update_issue", issue_key="ABC-1")

        assert result["error"]["code"] == "invalid_arguments"
        assert api.calls == []

    @pytest.mark.asyncio
    async def test_add_comment_sends_adf_body_when_commenting(self) -> None:
        _world, api, tools = _setup()
        api.respond("POST", "/issue/ABC-1/comment", (201, {"id": "777"}))

        result = await _call(tools, "add_comment", issue_key="ABC-1", body="Looks good")

        assert result["comment_id"] == "777"
        assert (
            api.calls[0].body["body"]["content"][0]["content"][0]["text"]
            == "Looks good"
        )

    @pytest.mark.asyncio
    async def test_transition_issue_sends_transition_id_when_moving_issue(self) -> None:
        _world, api, tools = _setup()
        api.respond("POST", "/issue/ABC-1/transitions", (204, None))

        result = await _call(
            tools, "transition_issue", issue_key="ABC-1", transition_id="31"
        )

        assert result["transitioned"] is True
        assert api.calls[0].body == {"transition": {"id": "31"}}

    @pytest.mark.asyncio
    async def test_assign_issue_sends_null_account_when_unassigning(self) -> None:
        _world, api, tools = _setup()
        api.respond("PUT", "/issue/ABC-1/assignee", (204, None))

        result = await _call(tools, "assign_issue", issue_key="ABC-1", account_id=None)

        assert result["assignee"] is None
        assert api.calls[0].body == {"accountId": None}

    @pytest.mark.asyncio
    async def test_assign_issue_requires_account_id_field_when_omitted(self) -> None:
        _world, api, tools = _setup()

        result = await _call(tools, "assign_issue", issue_key="ABC-1")

        assert result["error"]["code"] == "invalid_arguments"
        assert api.calls == []


class TestArgumentLimits:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("tool", "arguments"),
        [
            ("get_issue", {"issue_key": "abc-1"}),
            ("get_issue", {"issue_key": "ABC-0"}),
            ("get_issue", {"issue_key": "ABC-1/../../x"}),
            ("get_issue", {"issue_key": "ABC-1", "extra": 1}),
            ("search_issues", {"jql": ""}),
            ("search_issues", {"jql": "x" * 2001}),
            ("search_issues", {"jql": "a", "max_results": 51}),
            ("search_issues", {"jql": "a", "max_results": 0}),
            ("search_issues", {"jql": "a", "next_page_token": "t" * 513}),
            ("list_projects", {"query": "q" * 201}),
            ("get_comments", {"issue_key": "ABC-1", "max_results": 100}),
            (
                "create_issue",
                {"project_key": "a", "issue_type": "Task", "summary": "s"},
            ),
            (
                "create_issue",
                {"project_key": "ABC", "issue_type": "Task", "summary": " "},
            ),
            (
                "create_issue",
                {"project_key": "ABC", "issue_type": "Task", "summary": "s" * 256},
            ),
            (
                "create_issue",
                {
                    "project_key": "ABC",
                    "issue_type": "T",
                    "summary": "s",
                    "labels": ["has space"],
                },
            ),
            (
                "create_issue",
                {
                    "project_key": "ABC",
                    "issue_type": "T",
                    "summary": "s",
                    "labels": ["l"] * 11,
                },
            ),
            ("add_comment", {"issue_key": "ABC-1", "body": ""}),
            ("add_comment", {"issue_key": "ABC-1", "body": "b" * 32001}),
            ("transition_issue", {"issue_key": "ABC-1", "transition_id": "3x"}),
            ("assign_issue", {"issue_key": "ABC-1", "account_id": "a" * 129}),
        ],
    )
    async def test_call_returns_invalid_arguments_without_request_when_argument_breaks_limit(
        self, tool: str, arguments: dict[str, Any]
    ) -> None:
        _world, api, tools = _setup()

        result = await _call(tools, tool, **arguments)

        assert result["error"]["code"] == "invalid_arguments"
        assert result["error"]["recoverable"] is True
        assert api.calls == []


class TestSites:
    def _two_sites_world(self) -> ConnectorWorld:
        world = build_world()
        world.provider.respond(
            "GET",
            ATLASSIAN_SITES_URL,
            json_response(
                200,
                [
                    jira_site(),
                    jira_site(
                        id="cloud-2", name="Beta Co", url="https://beta.atlassian.net"
                    ),
                ],
            ),
        )
        return world

    @pytest.mark.asyncio
    async def test_call_uses_first_site_when_site_is_not_given(self) -> None:
        _world, api, tools = _setup(world=self._two_sites_world())
        api.respond("GET", "/project/search", (200, {"values": []}))

        await _call(tools, "list_projects")

        assert api.calls[0].cloud_id == "cloud-1"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("selector", ["cloud-2", "beta co", "BETA.atlassian.net"])
    async def test_call_uses_named_site_when_site_matches_id_name_or_host(
        self, selector: str
    ) -> None:
        _world, api, tools = _setup(world=self._two_sites_world())
        api.respond("GET", "/project/search", (200, {"values": []}))

        await _call(tools, "list_projects", site=selector)

        assert api.calls[0].cloud_id == "cloud-2"

    @pytest.mark.asyncio
    async def test_call_lists_available_sites_when_site_is_unknown(self) -> None:
        _world, api, tools = _setup(world=self._two_sites_world())

        result = await _call(tools, "list_projects", site="nowhere")

        assert result["error"]["code"] == "invalid_arguments"
        assert "Acme (acme.atlassian.net)" in result["error"]["message"]
        assert "Beta Co (beta.atlassian.net)" in result["error"]["message"]
        assert api.calls == []

    def test_resolve_site_reports_expired_when_no_site_is_stored(self) -> None:
        with pytest.raises(ConnectorError) as raised:
            resolve_site([], None, "jira")

        assert raised.value.code is ToolErrorCode.CONNECTION_EXPIRED

    def test_resolve_site_returns_first_when_site_is_none(self) -> None:
        first = JiraSite("a", "A", "https://a.atlassian.net")

        assert (
            resolve_site(
                [first, JiraSite("b", "B", "https://b.atlassian.net")], None, "jira"
            )
            is first
        )


class TestConnectionErrors:
    @pytest.mark.asyncio
    async def test_call_reports_connection_missing_when_user_never_connected(
        self,
    ) -> None:
        _world, api, tools = _setup(connected=False)

        result = await _call(tools, "get_issue", issue_key="ABC-1")

        assert result["error"]["code"] == "connection_missing"
        assert (
            result["error"]["message"]
            == "Jira connection missing, reconnect in Connectors"
        )
        assert api.calls == []

    @pytest.mark.asyncio
    async def test_call_works_when_user_connects_after_tools_were_bound(self) -> None:
        world, api, tools = _setup(connected=False)
        api.respond("GET", "/issue/ABC-1", (200, load_fixture("jira_issue.json")))
        assert (await _call(tools, "get_issue", issue_key="ABC-1"))["error"]

        connect(world, USER, "jira")

        assert (await _call(tools, "get_issue", issue_key="ABC-1"))["key"] == "ABC-1"

    @pytest.mark.asyncio
    async def test_call_reports_connection_expired_when_connection_is_marked_expired(
        self,
    ) -> None:
        world, api, tools = _setup()
        world.store.mark_expired(USER, "jira", "invalid_grant")

        result = await _call(tools, "get_issue", issue_key="ABC-1")

        assert result["error"]["code"] == "connection_expired"
        assert api.calls == []

    @pytest.mark.asyncio
    async def test_call_reports_not_configured_when_connector_settings_are_missing(
        self,
    ) -> None:
        world = build_world(make_settings(JIRA_OAUTH_CLIENT_ID=""))
        _world, api, tools = _setup(connected=False, world=world)

        result = await _call(tools, "get_issue", issue_key="ABC-1")

        assert result["error"]["code"] == "not_configured"
        assert result["error"]["message"] == "Jira is not configured on this server"

    @pytest.mark.asyncio
    async def test_call_reports_sign_in_required_when_run_has_no_user(self) -> None:
        world = build_world()
        api = FakeJiraApi()
        tools = build_jira_tools(
            runtime=tool_runtime(world, api.client_factory),
            definition=JIRA,
            user_id=None,
            run_id="run-1",
            requested=ALL_NAMES,
        )

        result = await _call(tools, "get_issue", issue_key="ABC-1")

        assert result["error"]["code"] == "sign_in_required"
        assert world.store.audit == []

    @pytest.mark.asyncio
    async def test_call_reports_insufficient_scope_when_write_scope_was_not_granted(
        self,
    ) -> None:
        world, api, tools = _setup()
        record = world.store.get(USER, "jira")
        assert record is not None
        world.store.seed(
            dataclasses.replace(record, granted_scopes=("read:jira-work", "read:me"))
        )

        write = await _call(tools, "add_comment", issue_key="ABC-1", body="hi")
        api.respond("GET", "/issue/ABC-1", (200, load_fixture("jira_issue.json")))
        read = await _call(tools, "get_issue", issue_key="ABC-1")

        assert write["error"]["code"] == "insufficient_scope"
        assert "write:jira-work" in write["error"]["message"]
        assert read["key"] == "ABC-1"

    @pytest.mark.asyncio
    async def test_call_uses_only_the_run_users_token_when_two_users_are_connected(
        self,
    ) -> None:
        world, api, tools = _setup()
        world.provider.respond(
            "POST",
            ATLASSIAN_TOKEN_URL,
            json_response(200, atlassian_token_body(access_token="atl_access_b")),
        )
        connect(world, "user-b", "jira")
        api.respond("GET", "/issue/ABC-1", (200, load_fixture("jira_issue.json")))

        await _call(tools, "get_issue", issue_key="ABC-1")

        assert api.bearers() == ["atl_access_initial"]


class TestProviderErrors:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status", "headers", "code", "recoverable"),
        [
            (403, None, "permission_denied", False),
            (429, {"Retry-After": "30"}, "rate_limited", True),
            (500, None, "provider_unavailable", True),
            (400, None, "provider_error", False),
        ],
    )
    async def test_call_maps_status_to_code_when_jira_answers_with_error(
        self, status: int, headers: dict[str, str] | None, code: str, recoverable: bool
    ) -> None:
        _world, api, tools = _setup()
        api.respond(
            "GET",
            "/issue/ABC-1",
            reply(status, {"errorMessages": ["Field 'x' is bad"]}, headers),
        )

        result = await _call(tools, "get_issue", issue_key="ABC-1")

        assert result["error"]["code"] == code
        assert result["error"]["recoverable"] is recoverable

    @pytest.mark.asyncio
    async def test_call_includes_provider_message_when_jira_rejects_with_400(
        self,
    ) -> None:
        _world, api, tools = _setup()
        api.respond(
            "POST", "/issue", (400, {"errors": {"summary": "Summary is required"}})
        )

        result = await _call(
            tools, "create_issue", project_key="ABC", issue_type="Task", summary="s"
        )

        assert result["error"]["message"] == (
            "Jira rejected the request (HTTP 400): Summary is required"
        )

    @pytest.mark.asyncio
    async def test_call_reports_wait_seconds_when_rate_limited(self) -> None:
        _world, api, tools = _setup()
        api.respond("GET", "/issue/ABC-1", reply(429, {}, {"Retry-After": "30"}))

        result = await _call(tools, "get_issue", issue_key="ABC-1")

        assert (
            result["error"]["message"]
            == "Jira rate limit reached; try again in 30 seconds"
        )

    @pytest.mark.asyncio
    async def test_call_refreshes_token_once_and_retries_when_jira_answers_401(
        self,
    ) -> None:
        world, api, tools = _setup()
        world.provider.respond(
            "POST",
            ATLASSIAN_TOKEN_URL,
            json_response(200, atlassian_token_body(access_token="atl_access_2")),
        )
        api.reject_bearers.add("atl_access_initial")
        api.respond("GET", "/issue/ABC-1", (200, load_fixture("jira_issue.json")))

        result = await _call(tools, "get_issue", issue_key="ABC-1")

        assert result["key"] == "ABC-1"
        assert api.bearers() == ["atl_access_initial", "atl_access_2"]

    @pytest.mark.asyncio
    async def test_call_does_not_loop_and_reports_expired_when_token_is_rejected_twice(
        self,
    ) -> None:
        world, api, tools = _setup()
        world.provider.respond(
            "POST",
            ATLASSIAN_TOKEN_URL,
            json_response(200, atlassian_token_body(access_token="atl_access_2")),
        )
        api.reject_bearers.update({"atl_access_initial", "atl_access_2"})

        result = await _call(tools, "get_issue", issue_key="ABC-1")

        assert result["error"]["code"] == "connection_expired"
        assert len(api.calls) == 2

    @pytest.mark.asyncio
    async def test_call_reports_provider_error_when_jira_returns_garbage_body(
        self,
    ) -> None:
        _world, api, tools = _setup()

        def garbage(_request: Any) -> Any:
            import httpx

            return httpx.Response(200, content=b"<html>not json</html>")

        api.respond("GET", "/issue/ABC-1", garbage)

        result = await _call(tools, "get_issue", issue_key="ABC-1")

        assert result["error"]["code"] == "provider_error"

    @pytest.mark.asyncio
    async def test_call_audits_each_call_without_arguments_when_tools_run(self) -> None:
        world, api, tools = _setup()
        api.respond("GET", "/issue/ABC-1", (200, load_fixture("jira_issue.json")))

        await _call(tools, "get_issue", issue_key="ABC-1")
        await _call(tools, "get_issue", issue_key="bad")

        outcomes = [
            (a.action, a.outcome, a.error_code)
            for a in world.store.audit
            if a.action == "tool_call"
        ]
        assert outcomes == [
            ("tool_call", "ok", None),
            ("tool_call", "error", "invalid_arguments"),
        ]
        assert all("ABC-1" not in repr(a) for a in world.store.audit)
