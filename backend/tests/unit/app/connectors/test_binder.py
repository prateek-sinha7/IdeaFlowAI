"""Unit tests for ConnectorRunToolBinder: which tools a run gets and what is audited.

No network and no database. The fakes of ``tests/fakes`` stand in for the provider,
the in-process GitHub MCP server and the store. The binder must never raise, so each
stub path is covered, along with the failure paths that could turn into an exception.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from langchain_core.tools import BaseTool

from agents.capabilities.connector_catalog import GITHUB, JIRA
from agents.execution_engine.run_tools import RunToolRequest
from app.connectors import binder as binder_module
from app.connectors.binder import ConnectorRunToolBinder
from app.connectors.tools.names import format_tool_name
from app.connectors.tools.remote_mcp import (
    BoundRemoteTools,
    RemoteMcpBinder,
    RemoteMcpLister,
)
from app.models.connector import AUDIT_TOOLS_BOUND
from tests.fakes.connector_services import ConnectorWorld, build_world
from tests.fakes.connector_settings import make_settings
from tests.fakes.connector_tool_world import connect, tool_runtime
from tests.fakes.jira_api import FakeJiraApi
from tests.fakes.streamable_http_mcp import FakeGitHubMcpServer

USER = "user-a"
RUN = "run-1"
CONFIG = {"configurable": {"thread_id": "run-1:agent-a"}}
GITHUB_TOOL = format_tool_name("github", "list_issues")
JIRA_TOOL = format_tool_name("jira", "get_issue")
JIRA_ARGUMENTS = {"issue_key": "ABC-1"}


def _refuse_network(*_args: Any, **_kwargs: Any) -> httpx.AsyncClient:
    raise AssertionError("this test must not open a network connection")


def _unreachable_factory(*_args: Any, **kwargs: Any) -> httpx.AsyncClient:
    def _down(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    return httpx.AsyncClient(
        transport=httpx.MockTransport(_down),
        auth=kwargs.get("auth"),
        headers=kwargs.get("headers"),
    )


class _ExplodingRemote(RemoteMcpBinder):
    async def bind(self, *_args: Any, **_kwargs: Any) -> BoundRemoteTools:
        raise RuntimeError("boom")


def _request(names: set[str], user_id: str | None = USER) -> RunToolRequest:
    return RunToolRequest(run_id=RUN, user_id=user_id, tool_names=frozenset(names))


def _binder(
    world: ConnectorWorld,
    *,
    jira: FakeJiraApi | None = None,
    github: FakeGitHubMcpServer | None = None,
    mcp_factory: Callable[..., httpx.AsyncClient] | None = None,
    remote_cls: Callable[..., RemoteMcpBinder] = RemoteMcpBinder,
) -> ConnectorRunToolBinder:
    services = world.services
    if mcp_factory is None:
        mcp_factory = github.client_factory if github is not None else _refuse_network
    runtime = tool_runtime(
        world, jira.client_factory if jira is not None else _refuse_network
    )
    lister = RemoteMcpLister(
        registry=services.registry,
        tokens=services.tokens,
        cache=services.tool_cache,
        httpx_client_factory=mcp_factory,
        clock=world.clock,
    )
    remote = remote_cls(
        runtime=runtime, lister=lister, httpx_client_factory=mcp_factory
    )
    return ConnectorRunToolBinder(runtime=runtime, remote=remote)


def _settings_without(connector_key: str) -> Any:
    variable = (
        "GITHUB_OAUTH_CLIENT_ID"
        if connector_key == "github"
        else "JIRA_OAUTH_CLIENT_ID"
    )
    return make_settings(**{variable: ""})


def _bound_rows(world: ConnectorWorld) -> list[tuple[str, str, str | None]]:
    """``(connector, outcome, error_code)`` of every tools_bound row, sorted."""
    return sorted(
        (entry.connector_key, entry.outcome, entry.error_code)
        for entry in world.store.audit
        if entry.action == AUDIT_TOOLS_BOUND
    )


async def _invoke(tool: BaseTool, **arguments: Any) -> str:
    return await tool.ainvoke(arguments, config=CONFIG)


def _error_code(text: str) -> str:
    return json.loads(text)["error"]["code"]


class TestBoundTools:
    @pytest.mark.asyncio
    async def test_call_binds_real_github_tool_and_audits_ok_when_connected(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world()
            connect(world, USER, "github")

            tools = await _binder(world, github=server)(_request({GITHUB_TOOL}))
            await _invoke(tools[GITHUB_TOOL], query="x")

        assert set(tools) == {GITHUB_TOOL}
        assert tools[GITHUB_TOOL].metadata == {
            "connector": "github",
            "write_capable": False,
            "source_name": "list_issues",
        }
        assert server.requests
        assert _bound_rows(world) == [("github", "ok", None)]
        run_ids = {e.run_id for e in world.store.audit if e.action == AUDIT_TOOLS_BOUND}
        assert run_ids == {RUN}

    @pytest.mark.asyncio
    async def test_call_binds_real_jira_tools_and_audits_ok_when_connected(
        self,
    ) -> None:
        world = build_world()
        api = FakeJiraApi()
        connect(world, USER, "jira")

        tools = await _binder(world, jira=api)(_request({JIRA_TOOL}))

        assert set(tools) == {JIRA_TOOL}
        assert tools[JIRA_TOOL].metadata["write_capable"] is False
        assert _bound_rows(world) == [("jira", "ok", None)]

    @pytest.mark.asyncio
    async def test_call_binds_jira_tool_and_reports_missing_connection_when_not_connected(
        self,
    ) -> None:
        world = build_world()

        tools = await _binder(world, jira=FakeJiraApi())(_request({JIRA_TOOL}))
        reply = await _invoke(tools[JIRA_TOOL], **JIRA_ARGUMENTS)

        assert _error_code(reply) == "connection_missing"
        assert _bound_rows(world) == [("jira", "error", "connection_missing")]

    @pytest.mark.asyncio
    async def test_call_binds_jira_tool_and_reports_expired_connection_when_marked_expired(
        self,
    ) -> None:
        world = build_world()
        connect(world, USER, "jira")
        world.store.mark_expired(USER, "jira", "invalid_grant")

        tools = await _binder(world, jira=FakeJiraApi())(_request({JIRA_TOOL}))
        reply = await _invoke(tools[JIRA_TOOL], **JIRA_ARGUMENTS)

        assert _error_code(reply) == "connection_expired"
        assert _bound_rows(world) == [("jira", "error", "connection_expired")]

    @pytest.mark.asyncio
    async def test_call_writes_one_row_per_connector_when_two_connectors_requested(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world()
            connect(world, USER, "github")
            connect(world, USER, "jira")

            tools = await _binder(world, jira=FakeJiraApi(), github=server)(
                _request({GITHUB_TOOL, JIRA_TOOL})
            )

        assert set(tools) == {GITHUB_TOOL, JIRA_TOOL}
        assert _bound_rows(world) == [("github", "ok", None), ("jira", "ok", None)]

    @pytest.mark.asyncio
    async def test_call_binds_nothing_and_writes_no_row_when_no_names_requested(
        self,
    ) -> None:
        world = build_world()

        tools = await _binder(world)(_request(set()))

        assert tools == {}
        assert _bound_rows(world) == []

    @pytest.mark.asyncio
    async def test_call_skips_unknown_and_undeclared_names_when_requested(self) -> None:
        world = build_world()
        connect(world, USER, "jira")

        tools = await _binder(world, jira=FakeJiraApi())(
            _request({"bogus", "nosuch__tool", "jira__not_a_tool"})
        )

        assert tools == {}
        assert _bound_rows(world) == []


class TestStubPaths:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("connector", "setup", "user_id", "code"),
        [
            ("github", "not_configured", USER, "not_configured"),
            ("github", "anonymous", None, "sign_in_required"),
            ("github", "missing", USER, "connection_missing"),
            ("github", "expired", USER, "connection_expired"),
            ("jira", "not_configured", USER, "not_configured"),
            ("jira", "anonymous", None, "sign_in_required"),
        ],
    )
    async def test_call_binds_stubs_and_audits_error_when_connection_cannot_serve_tools(
        self,
        connector: str,
        setup: str,
        user_id: str | None,
        code: str,
    ) -> None:
        world = build_world(
            _settings_without(connector) if setup == "not_configured" else None
        )
        if setup == "expired":
            connect(world, USER, connector)
            world.store.mark_expired(USER, connector, "invalid_grant")
        name = GITHUB_TOOL if connector == "github" else JIRA_TOOL
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")

            tools = await _binder(world, jira=FakeJiraApi(), github=server)(
                _request({name}, user_id=user_id)
            )
            reply = await _invoke(tools[name])

        assert set(tools) == {name}
        assert _error_code(reply) == code
        assert server.requests == []
        expected_rows = [] if user_id is None else [(connector, "error", code)]
        assert _bound_rows(world) == expected_rows

    @pytest.mark.asyncio
    @pytest.mark.parametrize("connector", ["github", "jira"])
    async def test_call_stub_text_and_audit_hold_no_token_when_connection_expired(
        self, connector: str
    ) -> None:
        world = build_world()
        connect(world, USER, connector)
        record = world.store.get(USER, connector)
        assert record is not None
        token = world.services.cipher.decrypt(record.access_token_ciphertext)
        assert token
        world.store.mark_expired(USER, connector, "invalid_grant")
        name = GITHUB_TOOL if connector == "github" else JIRA_TOOL
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")

            tools = await _binder(world, jira=FakeJiraApi(), github=server)(
                _request({name})
            )
            arguments = JIRA_ARGUMENTS if connector == "jira" else {}
            reply = await _invoke(tools[name], **arguments)

        assert token not in reply
        assert token not in tools[name].description
        assert token not in repr(world.store.audit)
        assert _error_code(reply) == "connection_expired"

    @pytest.mark.asyncio
    async def test_call_binds_error_stub_and_audits_provider_unavailable_when_listing_fails(
        self,
    ) -> None:
        world = build_world()
        connect(world, USER, "github")

        tools = await _binder(world, mcp_factory=_unreachable_factory)(
            _request({GITHUB_TOOL})
        )
        reply = await _invoke(tools[GITHUB_TOOL])

        assert _error_code(reply) == "provider_unavailable"
        assert _bound_rows(world) == [("github", "error", "provider_unavailable")]


class TestNeverRaises:
    @pytest.mark.asyncio
    async def test_call_returns_stub_and_audits_internal_error_when_github_binding_raises(
        self,
    ) -> None:
        world = build_world()
        connect(world, USER, "github")

        tools = await _binder(world, remote_cls=_ExplodingRemote)(
            _request({GITHUB_TOOL})
        )
        reply = await _invoke(tools[GITHUB_TOOL])

        assert _error_code(reply) == "internal_error"
        assert _bound_rows(world) == [("github", "error", "internal_error")]

    @pytest.mark.asyncio
    async def test_call_returns_stub_and_audits_internal_error_when_jira_build_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(**_kwargs: Any) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(binder_module, "build_jira_tools", _boom)
        world = build_world()
        connect(world, USER, "jira")

        tools = await _binder(world)(_request({JIRA_TOOL}))
        reply = await _invoke(tools[JIRA_TOOL], **JIRA_ARGUMENTS)

        assert _error_code(reply) == "internal_error"
        assert _bound_rows(world) == [("jira", "error", "internal_error")]

    @pytest.mark.asyncio
    async def test_call_returns_no_tools_and_does_not_raise_when_registry_lookup_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = build_world()

        def _boom(_key: str) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(world.services.registry, "get", _boom)

        tools = await _binder(world)(_request({JIRA_TOOL}))

        assert tools == {}

    @pytest.mark.asyncio
    async def test_call_returns_tools_when_audit_insert_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = build_world()
        connect(world, USER, "jira")

        def _broken(_entry: object) -> None:
            raise RuntimeError("database is down")

        monkeypatch.setattr(world.store, "record_audit", _broken)

        tools = await _binder(world, jira=FakeJiraApi())(_request({JIRA_TOOL}))

        assert set(tools) == {JIRA_TOOL}


class TestServicesWiring:
    @pytest.mark.asyncio
    async def test_call_returns_stubs_for_anonymous_run_when_services_binder_is_used(
        self,
    ) -> None:
        world = build_world()

        tools = await world.services.binder(
            _request({GITHUB_TOOL, JIRA_TOOL}, user_id=None)
        )

        assert set(tools) == {GITHUB_TOOL, JIRA_TOOL}
        assert _error_code(await _invoke(tools[JIRA_TOOL])) == "sign_in_required"
        assert _error_code(await _invoke(tools[GITHUB_TOOL])) == "sign_in_required"
        assert _bound_rows(world) == []
