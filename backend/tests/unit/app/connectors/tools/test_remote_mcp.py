"""``RemoteMcpLister``: listing, filtering, caching and failure mapping.

The MCP client code runs unmodified against an in-process stub server
(``FakeGitHubMcpServer``, no sockets). Tokens come from the real ``TokenProvider``
over the in-memory store and fake OAuth provider.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from agents.capabilities.connector_catalog import GITHUB
from app.connectors.errors import (
    ConnectorError,
    ConnectorNotConfigured,
    ConnectorNotFound,
    ToolErrorCode,
)
from app.connectors.oauth import CallbackParams
from app.connectors.pkce import hash_state
from app.connectors.tools import remote_mcp
from app.connectors.tools.remote_mcp import (
    MAX_DESCRIPTION_LENGTH,
    NON_TEXT_NOTICE,
    BoundRemoteTools,
    RemoteMcpBinder,
    RemoteMcpLister,
    build_connection,
    clean_text,
    is_write_capable,
    join_content,
)
from app.connectors.tools.schema_cache import ToolListing
from tests.fakes.connector_services import ConnectorWorld, build_world
from tests.fakes.connector_settings import make_settings
from tests.fakes.connector_tool_world import tool_runtime
from tests.fakes.oauth_provider import (
    GITHUB_TOKEN_URL,
    github_token_body,
    json_response,
    query_of,
)
from tests.fakes.streamable_http_mcp import MCP_URL, FakeGitHubMcpServer

USER = "user-a"
ISSUER = "https://github.com/login/oauth"


def _connect_github(world: ConnectorWorld, user_id: str = USER) -> None:
    services = world.services
    started = services.oauth.start_authorization(user_id, "github")
    state = query_of(started.authorization_url)["state"]
    assert hash_state(state) in world.store.states
    outcome = services.oauth.complete_callback(
        CallbackParams(state=state, code="auth-code", iss=ISSUER)
    )
    assert outcome.connected


def _lister(world: ConnectorWorld, server: FakeGitHubMcpServer) -> RemoteMcpLister:
    services = world.services
    return RemoteMcpLister(
        registry=services.registry,
        tokens=services.tokens,
        cache=services.tool_cache,
        httpx_client_factory=server.client_factory,
        clock=world.clock,
    )


class TestListTools:
    @pytest.mark.asyncio
    async def test_list_tools_returns_sorted_namespaced_tools_when_server_lists_them(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues", "List issues")
            server.add_write_tool("create_issue")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)

            listing = await _lister(world, server).list_tools(USER, "github", ("repo",))

        assert [t.name for t in listing.tools] == [
            "github__create_issue",
            "github__list_issues",
        ]
        by_source = {t.source_name: t for t in listing.tools}
        assert by_source["list_issues"].write_capable is False
        assert by_source["create_issue"].write_capable is True
        assert by_source["list_issues"].title == "list_issues"
        assert listing.listed_at == world.clock()

    @pytest.mark.asyncio
    async def test_list_tools_sends_users_bearer_on_every_request_when_listing(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)

            await _lister(world, server).list_tools(USER, "github", ("repo",))

        assert server.requests
        assert set(server.bearers()) == {"gho_access_initial"}
        assert len(server.bearers()) == len(server.requests)

    @pytest.mark.asyncio
    async def test_list_tools_serves_second_call_from_cache_when_within_ttl(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)
            lister = _lister(world, server)

            first = await lister.list_tools(USER, "github", ("repo",))
            requests_after_first = len(server.requests)
            second = await lister.list_tools(USER, "github", ("repo",))

        assert second is first
        assert len(server.requests) == requests_after_first

    @pytest.mark.asyncio
    async def test_list_tools_fetches_again_when_scopes_changed(self) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)
            lister = _lister(world, server)

            first = await lister.list_tools(USER, "github", ("repo",))
            second = await lister.list_tools(USER, "github", ("repo", "read:org"))

        assert second is not first

    @pytest.mark.asyncio
    async def test_list_tools_fetches_again_when_connection_changed(self) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)
            lister = _lister(world, server)
            first = await lister.list_tools(USER, "github", ("repo",))

            _connect_github(world)  # a reconnect invalidates the user's cached list
            second = await lister.list_tools(USER, "github", ("repo",))

        assert second is not first

    @pytest.mark.asyncio
    async def test_list_tools_drops_tool_and_warns_when_bound_name_too_long(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        long_name = "t" * 60
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool(long_name)
            server.add_read_tool("ok_tool")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)

            with caplog.at_level(logging.WARNING, logger="app.connectors.tools"):
                listing = await _lister(world, server).list_tools(
                    USER, "github", ("repo",)
                )

        assert [t.source_name for t in listing.tools] == ["ok_tool"]
        assert any("naming rule" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_list_tools_refreshes_once_and_succeeds_when_server_rejects_first_token(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)
            world.provider.respond(
                "POST",
                GITHUB_TOKEN_URL,
                json_response(200, github_token_body(access_token="gho_access_2")),
            )
            server.reject_bearers.add("gho_access_initial")

            listing = await _lister(world, server).list_tools(USER, "github", ("repo",))

        assert [t.name for t in listing.tools] == ["github__list_issues"]
        assert "gho_access_initial" in server.bearers()
        assert "gho_access_2" in server.bearers()
        stored = world.store.get(USER, "github")
        assert stored is not None and stored.token_version == 2

    @pytest.mark.asyncio
    async def test_list_tools_raises_connection_expired_when_server_keeps_rejecting(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)
            world.provider.respond(
                "POST",
                GITHUB_TOKEN_URL,
                json_response(200, github_token_body(access_token="gho_access_2")),
            )
            server.reject_bearers.update({"gho_access_initial", "gho_access_2"})

            with pytest.raises(ConnectorError) as excinfo:
                await _lister(world, server).list_tools(USER, "github", ("repo",))

        assert excinfo.value.code is ToolErrorCode.CONNECTION_EXPIRED

    @pytest.mark.asyncio
    async def test_list_tools_raises_provider_unavailable_when_transport_fails(
        self,
    ) -> None:
        def _factory(*_a: object, **_k: object) -> httpx.AsyncClient:
            def _boom(request: httpx.Request) -> httpx.Response:
                raise httpx.ConnectError("down", request=request)

            return httpx.AsyncClient(transport=httpx.MockTransport(_boom))

        world = build_world(mcp_http_client_factory=_factory)
        _connect_github(world)
        lister = RemoteMcpLister(
            registry=world.services.registry,
            tokens=world.services.tokens,
            cache=world.services.tool_cache,
            httpx_client_factory=_factory,
        )

        with pytest.raises(ConnectorError) as excinfo:
            await lister.list_tools(USER, "github", ("repo",))

        assert excinfo.value.code is ToolErrorCode.PROVIDER_UNAVAILABLE
        assert len(world.services.tool_cache) == 0

    @pytest.mark.asyncio
    async def test_list_tools_raises_connection_missing_when_user_has_no_connection(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world(mcp_http_client_factory=server.client_factory)

            with pytest.raises(ConnectorError) as excinfo:
                await _lister(world, server).list_tools(USER, "github", ("repo",))

        assert excinfo.value.code is ToolErrorCode.CONNECTION_MISSING

    @pytest.mark.asyncio
    async def test_list_tools_raises_not_found_when_connector_unknown(self) -> None:
        world = build_world()

        with pytest.raises(ConnectorNotFound):
            await world.services.tool_listing._remote_mcp.list_tools(USER, "nope", ())

    @pytest.mark.asyncio
    async def test_list_tools_raises_not_configured_when_credentials_missing(
        self,
    ) -> None:
        world = build_world(make_settings(GITHUB_OAUTH_CLIENT_ID=""))

        with pytest.raises(ConnectorNotConfigured):
            await world.services.tool_listing._remote_mcp.list_tools(USER, "github", ())


class TestFilteringAndShaping:
    @staticmethod
    def _tool(name: str, **fields: object) -> SimpleNamespace:
        return SimpleNamespace(
            name=name,
            title=fields.get("title"),
            description=fields.get("description", ""),
            annotations=fields.get("annotations"),
        )

    def test_shape_applies_deny_patterns_when_definition_denies(self) -> None:
        tooling = dataclasses.replace(GITHUB.tooling, tool_deny=("delete_*",))
        definition = dataclasses.replace(GITHUB, tooling=tooling)

        shaped = RemoteMcpLister._shape(
            definition, [self._tool("delete_repo"), self._tool("get_repo")]
        )

        assert [t.source_name for t in shaped] == ["get_repo"]

    def test_shape_applies_allow_patterns_when_definition_allows_subset(self) -> None:
        tooling = dataclasses.replace(GITHUB.tooling, tool_allow=("get_*",))
        definition = dataclasses.replace(GITHUB, tooling=tooling)

        shaped = RemoteMcpLister._shape(
            definition, [self._tool("create_x"), self._tool("get_x")]
        )

        assert [t.source_name for t in shaped] == ["get_x"]

    def test_shape_lists_every_tool_when_default_definition_used(self) -> None:
        shaped = RemoteMcpLister._shape(
            GITHUB, [self._tool("delete_repo"), self._tool("get_repo")]
        )

        assert [t.source_name for t in shaped] == ["delete_repo", "get_repo"]

    def test_shape_skips_tool_when_name_has_characters_outside_the_rule(self) -> None:
        shaped = RemoteMcpLister._shape(
            GITHUB, [self._tool("bad name"), self._tool("good")]
        )

        assert [t.source_name for t in shaped] == ["good"]

    def test_shape_marks_write_capable_when_definition_lists_extra_write_tool(
        self,
    ) -> None:
        tooling = dataclasses.replace(GITHUB.tooling, write_tools=("get_repo",))
        definition = dataclasses.replace(GITHUB, tooling=tooling)
        annotated = SimpleNamespace(readOnlyHint=True, title=None)

        shaped = RemoteMcpLister._shape(
            definition, [self._tool("get_repo", annotations=annotated)]
        )

        assert shaped[0].write_capable is True

    def test_shape_uses_annotation_title_when_tool_has_no_title(self) -> None:
        annotated = SimpleNamespace(readOnlyHint=True, title="Get a repo")

        shaped = RemoteMcpLister._shape(
            GITHUB, [self._tool("get_repo", annotations=annotated)]
        )

        assert shaped[0].title == "Get a repo"

    def test_clean_text_removes_control_characters_and_cuts_when_too_long(
        self,
    ) -> None:
        text = "a\x00b\x07c\n" + "x" * (MAX_DESCRIPTION_LENGTH + 50)

        cleaned = clean_text(text, MAX_DESCRIPTION_LENGTH)

        assert cleaned.startswith("abc\n")
        assert len(cleaned) == MAX_DESCRIPTION_LENGTH
        assert "\x00" not in cleaned

    def test_clean_text_returns_empty_when_value_is_not_text(self) -> None:
        assert clean_text(None, 10) == ""
        assert clean_text(5, 10) == ""

    @pytest.mark.parametrize(
        ("hint", "expected"), [(True, False), (False, True), (None, True)]
    )
    def test_is_write_capable_follows_read_only_hint_when_annotated(
        self, hint: bool | None, expected: bool
    ) -> None:
        tool = SimpleNamespace(name="t", annotations=SimpleNamespace(readOnlyHint=hint))

        assert is_write_capable(GITHUB, tool) is expected

    def test_is_write_capable_is_true_when_tool_has_no_annotations(self) -> None:
        assert is_write_capable(GITHUB, SimpleNamespace(name="t", annotations=None))


class TestBuildConnection:
    def test_build_connection_has_streamable_http_settings_when_github(self) -> None:
        world = build_world()

        connection = build_connection(GITHUB, USER, world.services.tokens)

        assert connection["transport"] == "streamable_http"
        assert connection["url"] == MCP_URL
        assert connection["terminate_on_close"] is True
        assert "authorization" not in {k.lower() for k in connection["headers"]}

    def test_build_connection_raises_when_connector_is_not_remote_mcp(self) -> None:
        from agents.capabilities.connector_catalog import JIRA

        with pytest.raises(ValueError, match="not a remote MCP connector"):
            build_connection(JIRA, USER, build_world().services.tokens)


def test_tool_listing_dataclass_is_frozen_when_constructed() -> None:
    listing = ToolListing(tools=(), listed_at=build_world().clock())

    with pytest.raises(dataclasses.FrozenInstanceError):
        listing.tools = ()  # type: ignore[misc]


def _binder(world: ConnectorWorld, server: FakeGitHubMcpServer) -> RemoteMcpBinder:
    return RemoteMcpBinder(
        runtime=tool_runtime(world, server.client_factory),
        lister=_lister(world, server),
        httpx_client_factory=server.client_factory,
    )


async def _bind(
    world: ConnectorWorld,
    server: FakeGitHubMcpServer,
    names: set[str],
    *,
    user_id: str | None = USER,
) -> BoundRemoteTools:
    return await _binder(world, server).bind(
        definition=GITHUB, user_id=user_id, run_id="run-1", requested=names
    )


async def _invoke(tool: Any, **arguments: Any) -> str:
    return await tool.ainvoke(
        arguments, config={"configurable": {"thread_id": "run-1:agent-a"}}
    )


def _error_of(text: str) -> dict[str, Any]:
    return json.loads(text)["error"]


class TestBind:
    @pytest.mark.asyncio
    async def test_bind_returns_namespaced_real_tools_that_call_the_server_when_connected(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            server.add_write_tool("create_issue")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)

            bound = await _bind(
                world, server, {"github__list_issues", "github__create_issue"}
            )
            result = await _invoke(bound.tools["github__list_issues"], query="open")

        assert bound.outcome == "ok"
        assert set(bound.tools) == {"github__list_issues", "github__create_issue"}
        assert result == "list_issues:open"
        assert server.calls == [("list_issues", {"query": "open"})]
        flags = {n: t.metadata["write_capable"] for n, t in bound.tools.items()}
        assert flags == {"github__list_issues": False, "github__create_issue": True}

    @pytest.mark.asyncio
    async def test_bind_sends_users_bearer_and_selected_tools_header_when_calling(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            server.add_read_tool("get_issue")
            server.add_read_tool("other_tool")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)

            bound = await _bind(
                world, server, {"github__list_issues", "github__get_issue"}
            )
            before = len(server.requests)
            await _invoke(bound.tools["github__get_issue"], query="1")

        call_requests = server.requests[before:]
        assert call_requests
        assert {r["authorization"] for r in call_requests} == {
            "Bearer gho_access_initial"
        }
        assert {r.get("x-mcp-tools") for r in call_requests} == {
            "get_issue,list_issues"
        }

    @pytest.mark.asyncio
    async def test_bind_counts_unannotated_tool_as_write_when_server_gives_no_hint(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_unannotated_tool("mystery")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)

            bound = await _bind(world, server, {"github__mystery"})

        assert bound.tools["github__mystery"].metadata["write_capable"] is True

    @pytest.mark.asyncio
    async def test_bind_returns_unavailable_stub_when_requested_tool_is_not_listed(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)

            bound = await _bind(
                world, server, {"github__list_issues", "github__renamed_upstream"}
            )
            reply = await _invoke(bound.tools["github__renamed_upstream"])

        assert bound.outcome == "ok"
        assert _error_of(reply)["code"] == "tool_unavailable"
        assert "renamed_upstream" in _error_of(reply)["message"]
        assert server.calls == []

    @pytest.mark.asyncio
    async def test_bind_ignores_other_connectors_and_invalid_names_when_requested(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)

            bound = await _bind(
                world, server, {"jira__get_issue", "list_issues", "github__"}
            )

        assert bound.tools == {}
        assert bound.outcome == "ok"
        assert server.requests == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("setup", "user_id", "code"),
        [
            ("none", USER, "connection_missing"),
            ("expired", USER, "connection_expired"),
            ("connected", None, "sign_in_required"),
            ("unconfigured", USER, "not_configured"),
        ],
    )
    async def test_bind_returns_stubs_without_network_when_connection_cannot_be_used(
        self, setup: str, user_id: str | None, code: str
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            settings = (
                make_settings(GITHUB_OAUTH_CLIENT_ID="")
                if setup == "unconfigured"
                else None
            )
            world = build_world(settings, mcp_http_client_factory=server.client_factory)
            if setup in {"expired", "connected"}:
                _connect_github(world)
            if setup == "expired":
                world.store.mark_expired(USER, "github", "invalid_grant")

            bound = await _bind(world, server, {"github__list_issues"}, user_id=user_id)
            reply = await _invoke(bound.tools["github__list_issues"], query="x")

        assert bound.outcome == "error"
        assert bound.error_code == code
        assert _error_of(reply)["code"] == code
        assert server.requests == []

    @pytest.mark.asyncio
    async def test_bind_returns_provider_unavailable_stubs_and_does_not_raise_when_listing_fails(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world(mcp_http_client_factory=_raising_factory)
            _connect_github(world)
            services = world.services
            binder = RemoteMcpBinder(
                runtime=tool_runtime(world, _raising_factory),
                lister=RemoteMcpLister(
                    registry=services.registry,
                    tokens=services.tokens,
                    cache=services.tool_cache,
                    httpx_client_factory=_raising_factory,
                    clock=world.clock,
                ),
                httpx_client_factory=_raising_factory,
            )

            bound = await binder.bind(
                definition=GITHUB,
                user_id=USER,
                run_id="run-1",
                requested={"github__list_issues"},
            )
            reply = await _invoke(bound.tools["github__list_issues"])

        assert bound.outcome == "error"
        assert bound.error_code == "provider_unavailable"
        assert _error_of(reply)["recoverable"] is True

    @pytest.mark.asyncio
    async def test_invoke_refreshes_once_and_retries_when_server_rejects_first_token(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)
            bound = await _bind(world, server, {"github__list_issues"})
            world.provider.respond(
                "POST",
                GITHUB_TOKEN_URL,
                json_response(200, github_token_body(access_token="gho_access_2")),
            )
            server.reject_bearers.add("gho_access_initial")

            result = await _invoke(bound.tools["github__list_issues"], query="q")

        assert result == "list_issues:q"
        assert "gho_access_2" in server.bearers()

    @pytest.mark.asyncio
    async def test_invoke_returns_connection_expired_when_server_keeps_rejecting(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)
            bound = await _bind(world, server, {"github__list_issues"})
            world.provider.respond(
                "POST",
                GITHUB_TOKEN_URL,
                json_response(200, github_token_body(access_token="gho_access_2")),
            )
            server.reject_bearers.update({"gho_access_initial", "gho_access_2"})

            result = await _invoke(bound.tools["github__list_issues"])

        assert _error_of(result)["code"] == "connection_expired"

    @pytest.mark.asyncio
    async def test_invoke_returns_connection_missing_when_user_disconnects_after_bind(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)
            bound = await _bind(world, server, {"github__list_issues"})
            world.store.delete(USER, "github")
            before = len(server.requests)

            result = await _invoke(bound.tools["github__list_issues"])

        assert _error_of(result)["code"] == "connection_missing"
        assert len(server.requests) == before

    @pytest.mark.asyncio
    async def test_invoke_returns_provider_error_when_server_reports_tool_failure(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_failing_tool("search_code", "rate   limited\nby upstream")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)
            bound = await _bind(world, server, {"github__search_code"})

            result = await _invoke(bound.tools["github__search_code"], query="x")

        error = _error_of(result)
        assert error["code"] == "provider_error"
        assert "rate limited by upstream" in error["message"]

    @pytest.mark.asyncio
    async def test_invoke_audits_each_call_without_arguments_when_tool_runs(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)
            bound = await _bind(world, server, {"github__list_issues"})

            await _invoke(bound.tools["github__list_issues"], query="very-secret-query")

        (entry,) = [a for a in world.store.audit if a.action == "tool_call"]
        assert (entry.connector_key, entry.tool_name, entry.outcome) == (
            "github",
            "github__list_issues",
            "ok",
        )
        assert entry.agent_ref == "agent-a"
        assert "very-secret-query" not in repr(world.store.audit)

    @pytest.mark.asyncio
    async def test_invoke_does_not_pass_model_supplied_runtime_argument_when_schema_lacks_it(
        self,
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)
            bound = await _bind(world, server, {"github__list_issues"})

            result = await _invoke(
                bound.tools["github__list_issues"], query="q", runtime="evil"
            )

        assert result == "list_issues:q"

    @pytest.mark.asyncio
    async def test_call_returns_provider_unavailable_when_remote_call_exceeds_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues")
            world = build_world(mcp_http_client_factory=server.client_factory)
            _connect_github(world)
            real_convert = remote_mcp.convert_mcp_tool_to_langchain_tool

            def _convert_with_stalled_call(*args: Any, **kwargs: Any) -> Any:
                inner = real_convert(*args, **kwargs)

                async def _never_answers(**_arguments: Any) -> Any:
                    await asyncio.sleep(10)

                inner.coroutine = _never_answers
                return inner

            monkeypatch.setattr(
                remote_mcp,
                "convert_mcp_tool_to_langchain_tool",
                _convert_with_stalled_call,
            )
            monkeypatch.setattr(remote_mcp, "REMOTE_TOOL_CALL_TIMEOUT_SECONDS", 0.01)
            bound = await _bind(world, server, {"github__list_issues"})

            reply = await _invoke(bound.tools["github__list_issues"], query="q")

        assert _error_of(reply)["code"] == "provider_unavailable"
        (entry,) = [a for a in world.store.audit if a.action == "tool_call"]
        assert entry.outcome == "error"


def _raising_factory(*_args: Any, **_kwargs: Any) -> httpx.AsyncClient:
    def _boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    return httpx.AsyncClient(transport=httpx.MockTransport(_boom))


class TestJoinContent:
    def test_join_content_joins_text_and_notes_other_blocks_when_mixed(self) -> None:
        content = [
            {"type": "text", "text": "a"},
            {"type": "image", "base64": "xx", "mime_type": "image/png"},
            "b",
        ]

        assert join_content(content) == f"a\n{NON_TEXT_NOTICE}\nb"

    def test_join_content_returns_string_as_is_when_content_is_text(self) -> None:
        assert join_content("plain") == "plain"

    def test_join_content_notes_omission_when_content_is_unknown_type(self) -> None:
        assert join_content(object()) == NON_TEXT_NOTICE
