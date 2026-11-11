"""GitHub remote MCP tools over Streamable HTTP, against an in-process stub server.

The MCP client code runs unmodified against ``FakeGitHubMcpServer`` (no sockets). The
connection store is a real SQLite database, so tokens come out of encrypted columns,
a refresh rewrites the row, and every call leaves an audit row.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import select

from agents.capabilities.connector_catalog import GITHUB
from app.connectors.tools.remote_mcp import (
    BoundRemoteTools,
    RemoteMcpBinder,
    RemoteMcpLister,
)
from app.models.connector import ConnectorConnection
from tests.fakes.connector_sqlite import SqliteConnectors, sqlite_connectors
from tests.fakes.oauth_provider import (
    GITHUB_TOKEN_URL,
    github_token_body,
    json_response,
)
from tests.fakes.streamable_http_mcp import FakeGitHubMcpServer

USER = "user-a"
OTHER = "user-b"
CONFIG = {"configurable": {"thread_id": "run-7:agent-x"}}


async def _bind(
    env: SqliteConnectors,
    server: FakeGitHubMcpServer,
    names: set[str],
    user_id: str = USER,
) -> BoundRemoteTools:
    services = env.services
    binder = RemoteMcpBinder(
        runtime=env.tool_runtime(server.client_factory),
        lister=RemoteMcpLister(
            registry=services.registry,
            tokens=services.tokens,
            cache=services.tool_cache,
            httpx_client_factory=server.client_factory,
        ),
        httpx_client_factory=server.client_factory,
    )
    return await binder.bind(
        definition=GITHUB, user_id=user_id, run_id="run-7", requested=names
    )


async def _call(tool: Any, **arguments: Any) -> str:
    return await tool.ainvoke(arguments, config=CONFIG)


class TestRemoteMcpTools:
    @pytest.mark.asyncio
    async def test_call_sends_stored_token_on_every_request_when_tool_runs(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues", "List issues")
            with sqlite_connectors(
                [USER], mcp_http_client_factory=server.client_factory
            ) as env:
                env.connect(USER, "github")

                bound = await _bind(env, server, {"github__list_issues"})
                result = await _call(bound.tools["github__list_issues"], query="open")

        assert result == "list_issues:open"
        assert server.requests
        assert set(server.bearers()) == {"gho_access_initial"}
        assert len(server.bearers()) == len(server.requests)

    @pytest.mark.asyncio
    async def test_call_writes_audit_row_with_run_and_agent_when_tool_runs(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            with sqlite_connectors(
                [USER], mcp_http_client_factory=server.client_factory
            ) as env:
                env.connect(USER, "github")
                bound = await _bind(env, server, {"github__list_issues"})

                await _call(
                    bound.tools["github__list_issues"], query="token-like-argument"
                )
                rows = [r for r in env.audit_rows() if r.action == "tool_call"]

        (row,) = rows
        assert (row.user_id, row.connector_key, row.tool_name, row.outcome) == (
            USER,
            "github",
            "github__list_issues",
            "ok",
        )
        assert (row.run_id, row.agent_ref) == ("run-7", "agent-x")
        assert "token-like-argument" not in repr(vars(row))

    @pytest.mark.asyncio
    async def test_call_refreshes_stored_token_once_and_retries_when_server_returns_401(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            with sqlite_connectors(
                [USER], mcp_http_client_factory=server.client_factory
            ) as env:
                env.connect(USER, "github")
                bound = await _bind(env, server, {"github__list_issues"})
                env.provider.respond(
                    "POST",
                    GITHUB_TOKEN_URL,
                    json_response(
                        200,
                        github_token_body(
                            access_token="gho_access_2", refresh_token="ghr_refresh_2"
                        ),
                    ),
                )
                server.reject_bearers.add("gho_access_initial")

                result = await _call(bound.tools["github__list_issues"], query="q")
                with env.factory() as session:
                    row = session.scalars(select(ConnectorConnection)).one()
                    stored = env.services.cipher.decrypt(row.access_token_ciphertext)
                    version = row.token_version

        assert result == "list_issues:q"
        assert stored == "gho_access_2"
        assert version == 2
        assert server.bearers()[-1] == "gho_access_2"

    @pytest.mark.asyncio
    async def test_call_returns_insufficient_scope_when_server_challenges_for_scope(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            with sqlite_connectors(
                [USER], mcp_http_client_factory=server.client_factory
            ) as env:
                env.connect(USER, "github")
                bound = await _bind(env, server, {"github__list_issues"})
                server.scope_challenge_bearers.add("gho_access_initial")

                result = await _call(bound.tools["github__list_issues"], query="q")

        error = json.loads(result)["error"]
        assert error["code"] == "insufficient_scope"
        assert error["recoverable"] is False

    @pytest.mark.asyncio
    async def test_call_returns_provider_error_when_server_reports_is_error(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_failing_tool("search_code", "query too broad")
            with sqlite_connectors(
                [USER], mcp_http_client_factory=server.client_factory
            ) as env:
                env.connect(USER, "github")
                bound = await _bind(env, server, {"github__search_code"})

                result = await _call(bound.tools["github__search_code"], query="*")

        error = json.loads(result)["error"]
        assert error["code"] == "provider_error"
        assert "query too broad" in error["message"]

    @pytest.mark.asyncio
    async def test_call_uses_each_users_own_token_when_two_users_are_connected(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            with sqlite_connectors(
                [USER, OTHER], mcp_http_client_factory=server.client_factory
            ) as env:
                env.connect(USER, "github")
                env.provider.respond(
                    "POST",
                    GITHUB_TOKEN_URL,
                    json_response(200, github_token_body(access_token="gho_access_b")),
                )
                env.connect(OTHER, "github")

                mine = await _bind(env, server, {"github__list_issues"}, USER)
                theirs = await _bind(env, server, {"github__list_issues"}, OTHER)
                server.requests.clear()
                await _call(mine.tools["github__list_issues"], query="a")
                a_bearers = set(server.bearers())
                server.requests.clear()
                await _call(theirs.tools["github__list_issues"], query="b")
                b_bearers = set(server.bearers())

        assert a_bearers == {"gho_access_initial"}
        assert b_bearers == {"gho_access_b"}
