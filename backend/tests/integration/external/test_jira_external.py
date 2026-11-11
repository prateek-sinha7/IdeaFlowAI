"""Jira native tools end to end against an in-process fake Jira API.

The connection store is a real SQLite database: the site list and the encrypted token
come from the stored row, a 401 refreshes the stored token, and each call leaves an
audit row. Only the Jira and Atlassian networks are fake.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.tools import StructuredTool
from sqlalchemy import select

from agents.capabilities.connector_catalog import JIRA
from app.connectors.tools.jira import build_jira_tools
from app.connectors.tools.names import format_tool_name
from app.models.connector import ConnectorConnection
from tests.fakes.connector_sqlite import SqliteConnectors, sqlite_connectors
from tests.fakes.jira_api import FakeJiraApi, load_fixture, reply
from tests.fakes.oauth_provider import (
    ATLASSIAN_TOKEN_URL,
    atlassian_token_body,
    json_response,
)

USER = "user-a"
CONFIG = {"configurable": {"thread_id": "run-9:agent-j"}}
ALL_NAMES = {format_tool_name("jira", spec.name) for spec in JIRA.tooling.native_tools}


def _tools(env: SqliteConnectors, api: FakeJiraApi) -> dict[str, StructuredTool]:
    return build_jira_tools(
        runtime=env.tool_runtime(api.client_factory),
        definition=JIRA,
        user_id=USER,
        run_id="run-9",
        requested=ALL_NAMES,
    )


async def _call(tools: dict[str, StructuredTool], name: str, **arguments: Any) -> Any:
    return json.loads(await tools[f"jira__{name}"].ainvoke(arguments, config=CONFIG))


class TestJiraTools:
    @pytest.mark.asyncio
    async def test_every_tool_works_end_to_end_when_user_is_connected(self) -> None:
        api = FakeJiraApi()
        api.respond("POST", "/search/jql", (200, load_fixture("jira_search.json")))
        api.respond("GET", "/issue/ABC-1", (200, load_fixture("jira_issue.json")))
        api.respond("GET", "/project/search", (200, load_fixture("jira_projects.json")))
        api.respond(
            "GET", "/issue/ABC-1/comment", (200, load_fixture("jira_comments.json"))
        )
        api.respond(
            "GET",
            "/issue/ABC-1/transitions",
            (200, load_fixture("jira_transitions.json")),
        )
        api.respond("POST", "/issue", (201, {"id": "9", "key": "ABC-9"}))
        api.respond("PUT", "/issue/ABC-1", (204, None))
        api.respond("POST", "/issue/ABC-1/comment", (201, {"id": "5"}))
        api.respond("POST", "/issue/ABC-1/transitions", (204, None))
        api.respond("PUT", "/issue/ABC-1/assignee", (204, None))
        with sqlite_connectors([USER]) as env:
            env.connect(USER, "jira")
            tools = _tools(env, api)

            results = {
                "search": await _call(tools, "search_issues", jql="project = ABC"),
                "get": await _call(tools, "get_issue", issue_key="ABC-1"),
                "projects": await _call(tools, "list_projects"),
                "comments": await _call(tools, "get_comments", issue_key="ABC-1"),
                "transitions": await _call(
                    tools, "list_transitions", issue_key="ABC-1"
                ),
                "create": await _call(
                    tools,
                    "create_issue",
                    project_key="ABC",
                    issue_type="Task",
                    summary="s",
                ),
                "update": await _call(
                    tools, "update_issue", issue_key="ABC-1", labels=["x"]
                ),
                "comment": await _call(
                    tools, "add_comment", issue_key="ABC-1", body="hi"
                ),
                "transition": await _call(
                    tools, "transition_issue", issue_key="ABC-1", transition_id="31"
                ),
                "assign": await _call(
                    tools, "assign_issue", issue_key="ABC-1", account_id="acc-1"
                ),
            }
            rows = [r for r in env.audit_rows() if r.action == "tool_call"]

        assert all("error" not in value for value in results.values())
        assert results["create"]["key"] == "ABC-9"
        assert len(rows) == 10
        assert {r.outcome for r in rows} == {"ok"}
        assert {r.agent_ref for r in rows} == {"agent-j"}
        assert set(api.bearers()) == {"atl_access_initial"}

    @pytest.mark.asyncio
    async def test_search_returns_next_page_token_and_accepts_it_when_paginating(
        self,
    ) -> None:
        api = FakeJiraApi()
        api.respond(
            "POST",
            "/search/jql",
            (200, load_fixture("jira_search.json")),
            (200, {"issues": [], "isLast": True}),
        )
        with sqlite_connectors([USER]) as env:
            env.connect(USER, "jira")
            tools = _tools(env, api)

            first = await _call(tools, "search_issues", jql="x")
            second = await _call(
                tools,
                "search_issues",
                jql="x",
                next_page_token=first["next_page_token"],
            )

        assert first["next_page_token"] == "page-2-token"
        assert second == {"issues": [], "next_page_token": None}
        assert api.calls[1].body["nextPageToken"] == "page-2-token"

    @pytest.mark.asyncio
    async def test_call_returns_rate_limit_hint_when_jira_sends_429_with_retry_after(
        self,
    ) -> None:
        api = FakeJiraApi()
        api.respond("GET", "/issue/ABC-1", reply(429, {}, {"Retry-After": "42"}))
        with sqlite_connectors([USER]) as env:
            env.connect(USER, "jira")

            result = await _call(_tools(env, api), "get_issue", issue_key="ABC-1")

        assert result["error"]["code"] == "rate_limited"
        assert result["error"]["recoverable"] is True
        assert "42 seconds" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_call_rewrites_stored_token_when_jira_returns_401_once(self) -> None:
        api = FakeJiraApi()
        api.respond("GET", "/issue/ABC-1", (200, load_fixture("jira_issue.json")))
        api.reject_bearers.add("atl_access_initial")
        with sqlite_connectors([USER]) as env:
            env.connect(USER, "jira")
            env.provider.respond(
                "POST",
                ATLASSIAN_TOKEN_URL,
                json_response(
                    200,
                    atlassian_token_body(
                        access_token="atl_access_2", refresh_token="atl_refresh_2"
                    ),
                ),
            )

            result = await _call(_tools(env, api), "get_issue", issue_key="ABC-1")
            with env.factory() as session:
                row = session.scalars(select(ConnectorConnection)).one()
                stored = env.services.cipher.decrypt(row.access_token_ciphertext)
                refresh = env.services.cipher.decrypt(
                    row.refresh_token_ciphertext or ""
                )

        assert result["key"] == "ABC-1"
        assert (stored, refresh) == ("atl_access_2", "atl_refresh_2")
        assert api.bearers() == ["atl_access_initial", "atl_access_2"]

    @pytest.mark.asyncio
    async def test_call_reports_connection_missing_after_disconnect_when_run_continues(
        self,
    ) -> None:
        api = FakeJiraApi()
        with sqlite_connectors([USER]) as env:
            env.connect(USER, "jira")
            tools = _tools(env, api)
            env.services.oauth.disconnect(USER, "jira")

            result = await _call(tools, "get_issue", issue_key="ABC-1")

        assert result["error"]["code"] == "connection_missing"
        assert api.calls == []
