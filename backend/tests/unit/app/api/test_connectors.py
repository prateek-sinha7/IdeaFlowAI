"""Connectors router: status codes, error envelope, headers and callback redirects.

The router runs over the in-memory connectors runtime (fake store, fake provider);
the caller is switchable. Real-database behaviour is in
``tests/integration/api/test_connectors_api.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from app.models.connector import CONNECTION_STATUS_EXPIRED
from tests.fakes.connector_app import (
    CurrentUser,
    connect_through_api,
    make_connector_app,
    make_user,
)
from tests.fakes.connector_services import ConnectorWorld, build_world
from tests.fakes.connector_settings import make_settings
from tests.fakes.oauth_provider import GITHUB_GRANT_URL, empty_response
from tests.fakes.streamable_http_mcp import FakeGitHubMcpServer

USER = "user-a"


@pytest.fixture
def world() -> ConnectorWorld:
    """The connectors runtime on fakes, every connector configured."""
    return build_world()


@pytest.fixture
def current() -> CurrentUser:
    """The switchable caller, signed in as ``user-a``."""
    return CurrentUser(make_user(USER))


@pytest.fixture
def client(world: ConnectorWorld, current: CurrentUser) -> Iterator[TestClient]:
    """A test client over the connectors router."""
    with TestClient(make_connector_app(world, current)) as test_client:
        yield test_client


def _location(response: httpx.Response) -> tuple[str, dict[str, str]]:
    parts = urlsplit(response.headers["location"])
    return parts.path, {k: v[0] for k, v in parse_qs(parts.query).items()}


class TestListConnectors:
    def test_list_connectors_returns_catalog_order_when_nothing_connected(
        self, client: TestClient
    ) -> None:
        response = client.get("/api/connectors")

        assert response.status_code == 200
        body = response.json()["connectors"]
        assert [c["key"] for c in body] == ["github", "jira"]
        assert {c["status"] for c in body} == {"not_connected"}
        assert body[0]["mode"] == "remote_mcp"
        assert body[1]["mode"] == "native_api"
        assert body[1]["requested_scopes"] == [
            "read:jira-work",
            "write:jira-work",
            "read:me",
            "offline_access",
        ]

    def test_list_connectors_sets_no_store_when_called(
        self, client: TestClient
    ) -> None:
        response = client.get("/api/connectors")

        assert response.headers.get_list("cache-control") == ["no-store"]

    def test_list_connectors_reports_account_and_sites_when_jira_connected(
        self, client: TestClient
    ) -> None:
        connect_through_api(client, "jira")

        body = client.get("/api/connectors").json()["connectors"]

        jira = next(c for c in body if c["key"] == "jira")
        assert jira["status"] == "connected"
        assert jira["account"] == {
            "id": "acc-1",
            "display_name": "Jane Doe",
            "login": None,
        }
        assert jira["sites"] == [
            {"id": "cloud-1", "name": "Acme", "url": "https://acme.atlassian.net"}
        ]
        assert jira["connected_at"] is not None
        assert "token" not in client.get("/api/connectors").text.lower()

    def test_list_connectors_reports_expired_when_row_is_expired(
        self, client: TestClient, world: ConnectorWorld
    ) -> None:
        connect_through_api(client, "jira")
        world.store.mark_expired(USER, "jira", "invalid_grant")

        body = client.get("/api/connectors").json()["connectors"]

        assert next(c for c in body if c["key"] == "jira")["status"] == "expired"
        assert world.store.get(USER, "jira").status == CONNECTION_STATUS_EXPIRED  # type: ignore[union-attr]

    def test_list_connectors_reports_not_configured_when_credentials_missing(
        self, current: CurrentUser
    ) -> None:
        unconfigured = build_world(make_settings(JIRA_OAUTH_CLIENT_ID=""))
        with TestClient(make_connector_app(unconfigured, current)) as test_client:
            body = test_client.get("/api/connectors").json()["connectors"]

        statuses = {c["key"]: c["status"] for c in body}
        assert statuses == {"github": "not_connected", "jira": "not_configured"}

    def test_list_connectors_answers_401_when_anonymous(
        self, client: TestClient, current: CurrentUser
    ) -> None:
        current.user = None

        assert client.get("/api/connectors").status_code == 401


class TestAuthorize:
    def test_authorize_returns_https_url_when_connector_configured(
        self, client: TestClient
    ) -> None:
        response = client.post("/api/connectors/jira/authorize")

        assert response.status_code == 200
        body = response.json()
        assert body["authorization_url"].startswith(
            "https://auth.atlassian.com/authorize?"
        )
        assert body["expires_at"]
        assert response.headers.get_list("cache-control") == ["no-store"]

    @pytest.mark.parametrize("key", ["nope", "oauth", "JIRA", "j", "jira;x"])
    def test_authorize_answers_404_when_key_unknown_or_invalid(
        self, client: TestClient, key: str
    ) -> None:
        response = client.post(f"/api/connectors/{key}/authorize")

        assert response.status_code in (404, 405)
        if response.status_code == 404:
            assert response.json()["detail"]["code"] == "connector_not_found"

    def test_authorize_answers_409_when_connector_not_configured(
        self, current: CurrentUser
    ) -> None:
        unconfigured = build_world(make_settings(GITHUB_OAUTH_CLIENT_ID=""))
        with TestClient(make_connector_app(unconfigured, current)) as test_client:
            response = test_client.post("/api/connectors/github/authorize")

        assert response.status_code == 409
        assert response.json()["detail"] == {
            "error": "Connector is not configured on this server",
            "code": "connector_not_configured",
            "recoverable": False,
        }

    def test_authorize_answers_429_when_too_many_pending(
        self, client: TestClient
    ) -> None:
        for _ in range(5):
            assert client.post("/api/connectors/jira/authorize").status_code == 200

        response = client.post("/api/connectors/jira/authorize")

        assert response.status_code == 429
        detail = response.json()["detail"]
        assert detail["code"] == "too_many_pending_authorizations"
        assert detail["recoverable"] is True

    def test_authorize_answers_401_when_anonymous(
        self, client: TestClient, current: CurrentUser
    ) -> None:
        current.user = None

        assert client.post("/api/connectors/jira/authorize").status_code == 401


class TestCallback:
    def test_callback_redirects_connected_when_flow_completes(
        self, client: TestClient
    ) -> None:
        response = connect_through_api(client, "jira")

        assert response.status_code == 303
        path, query = _location(response)
        assert path == "/connectors/oauth-complete"
        assert query == {"connector": "jira", "result": "connected"}

    def test_callback_sets_no_store_and_no_referrer_when_redirecting(
        self, client: TestClient
    ) -> None:
        response = connect_through_api(client, "jira")

        assert response.headers.get_list("cache-control") == ["no-store"]
        assert response.headers["pragma"] == "no-cache"
        assert response.headers["referrer-policy"] == "no-referrer"

    def test_callback_redirects_invalid_state_when_state_unknown(
        self, client: TestClient
    ) -> None:
        response = client.get(
            "/api/connectors/oauth/callback",
            params={"state": "x" * 43, "code": "abc"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert _location(response) == (
            "/connectors/oauth-complete",
            {"result": "error", "reason": "invalid_state"},
        )

    def test_callback_redirects_invalid_state_when_no_parameters(
        self, client: TestClient
    ) -> None:
        response = client.get("/api/connectors/oauth/callback", follow_redirects=False)

        assert response.status_code == 303
        assert _location(response)[1]["reason"] == "invalid_state"

    def test_callback_redirects_access_denied_when_user_declines(
        self, client: TestClient
    ) -> None:
        response = connect_through_api(
            client, "jira", error="access_denied", error_description="no thanks"
        )

        assert response.status_code == 303
        path, query = _location(response)
        assert query == {
            "connector": "jira",
            "result": "error",
            "reason": "access_denied",
        }
        assert "no thanks" not in response.headers["location"]

    def test_callback_redirects_issuer_mismatch_when_iss_differs(
        self, client: TestClient
    ) -> None:
        response = connect_through_api(client, "github", iss="https://evil.example")

        assert response.status_code == 303
        assert _location(response)[1] == {
            "connector": "github",
            "result": "error",
            "reason": "issuer_mismatch",
        }

    def test_callback_answers_303_never_422_when_values_are_oversized(
        self, client: TestClient
    ) -> None:
        response = client.get(
            "/api/connectors/oauth/callback",
            params={"state": "s" * 5000, "code": "c" * 9000, "iss": "i" * 3000},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert _location(response)[1]["reason"] == "invalid_state"

    def test_callback_needs_no_bearer_when_anonymous(
        self, client: TestClient, current: CurrentUser
    ) -> None:
        current.user = None

        response = client.get("/api/connectors/oauth/callback", follow_redirects=False)

        assert response.status_code == 303

    def test_callback_never_puts_code_or_state_in_location_when_redirecting(
        self, client: TestClient
    ) -> None:
        response = connect_through_api(client, "jira", code="secret-code-value")

        assert "secret-code-value" not in response.headers["location"]
        assert "state" not in response.headers["location"]


class TestDisconnect:
    def test_disconnect_revokes_and_deletes_when_connected(
        self, client: TestClient, world: ConnectorWorld
    ) -> None:
        connect_through_api(client, "jira")

        response = client.delete("/api/connectors/jira")

        assert response.status_code == 200
        assert response.json() == {
            "status": "disconnected",
            "provider_revocation": "revoked",
        }
        assert world.store.get(USER, "jira") is None

    def test_disconnect_is_idempotent_when_nothing_connected(
        self, client: TestClient
    ) -> None:
        response = client.delete("/api/connectors/jira")

        assert response.status_code == 200
        assert response.json() == {
            "status": "disconnected",
            "provider_revocation": "not_attempted",
        }

    def test_disconnect_reports_failed_but_deletes_when_provider_down(
        self, client: TestClient, world: ConnectorWorld
    ) -> None:
        connect_through_api(client, "jira")
        world.provider.respond(
            "POST", "https://auth.atlassian.com/oauth/revoke", empty_response(503)
        )

        response = client.delete("/api/connectors/jira")

        assert response.json()["provider_revocation"] == "failed"
        assert world.store.get(USER, "jira") is None

    def test_disconnect_revokes_github_grant_when_github_connected(
        self, client: TestClient, world: ConnectorWorld
    ) -> None:
        connect_through_api(client, "github")

        response = client.delete("/api/connectors/github")

        assert response.json()["provider_revocation"] == "revoked"
        assert world.provider.calls(
            "DELETE", GITHUB_GRANT_URL.format(client_id="github-client-id")
        )

    def test_disconnect_answers_404_when_connector_unknown(
        self, client: TestClient
    ) -> None:
        response = client.delete("/api/connectors/nope")

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "connector_not_found"

    def test_disconnect_answers_401_when_anonymous(
        self, client: TestClient, current: CurrentUser
    ) -> None:
        current.user = None

        assert client.delete("/api/connectors/jira").status_code == 401


class TestListTools:
    def test_list_tools_returns_ten_declared_tools_when_jira_not_connected(
        self, client: TestClient
    ) -> None:
        response = client.get("/api/connectors/jira/tools")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "not_connected"
        assert body["listed_at"] is None
        names = [t["name"] for t in body["tools"]]
        assert names == sorted(names)
        assert len(names) == 10
        assert all(n.startswith("jira__") for n in names)
        writes = {t["name"] for t in body["tools"] if t["write_capable"]}
        assert writes == {
            "jira__create_issue",
            "jira__update_issue",
            "jira__add_comment",
            "jira__transition_issue",
            "jira__assign_issue",
        }

    def test_list_tools_reports_connected_status_when_jira_connected(
        self, client: TestClient
    ) -> None:
        connect_through_api(client, "jira")

        assert client.get("/api/connectors/jira/tools").json()["status"] == "connected"

    def test_list_tools_answers_409_not_connected_when_github_has_no_row(
        self, client: TestClient
    ) -> None:
        response = client.get("/api/connectors/github/tools")

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "connector_not_connected"

    def test_list_tools_answers_409_expired_when_github_row_expired(
        self, client: TestClient, world: ConnectorWorld
    ) -> None:
        connect_through_api(client, "github")
        world.store.mark_expired(USER, "github", "invalid_grant")

        response = client.get("/api/connectors/github/tools")

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "connector_expired"

    def test_list_tools_answers_409_when_connector_not_configured(
        self, current: CurrentUser
    ) -> None:
        unconfigured = build_world(make_settings(JIRA_OAUTH_CLIENT_SECRET=""))
        with TestClient(make_connector_app(unconfigured, current)) as test_client:
            response = test_client.get("/api/connectors/jira/tools")

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "connector_not_configured"

    def test_list_tools_answers_404_when_connector_unknown(
        self, client: TestClient
    ) -> None:
        assert client.get("/api/connectors/nope/tools").status_code == 404


class TestListGithubTools:
    """GitHub's list comes from the MCP server: async tests share one event loop with it."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_server_tools_when_github_connected(
        self, current: CurrentUser
    ) -> None:
        async with FakeGitHubMcpServer() as server:
            server.add_read_tool("list_issues", "List issues\x00 in a repo")
            server.add_write_tool("create_issue")
            server.add_unannotated_tool("mystery")
            world = build_world(mcp_http_client_factory=server.client_factory)
            app = make_connector_app(world, current)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as http:
                connect_response = await _connect_async(http, "github")
                assert connect_response.status_code == 303

                response = await http.get("/api/connectors/github/tools")

            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "connected"
            assert body["listed_at"] is not None
            assert [t["name"] for t in body["tools"]] == [
                "github__create_issue",
                "github__list_issues",
                "github__mystery",
            ]
            by_name = {t["source_name"]: t for t in body["tools"]}
            assert by_name["list_issues"]["write_capable"] is False
            assert by_name["create_issue"]["write_capable"] is True
            assert by_name["mystery"]["write_capable"] is True
            assert by_name["list_issues"]["description"] == "List issues in a repo"
            assert set(server.bearers()) == {"gho_access_initial"}

    @pytest.mark.asyncio
    async def test_list_tools_answers_502_when_server_unreachable(
        self, current: CurrentUser
    ) -> None:
        def _refuse(*_args: object, **_kwargs: object) -> httpx.AsyncClient:
            def _handler(request: httpx.Request) -> httpx.Response:
                raise httpx.ConnectError("down", request=request)

            return httpx.AsyncClient(transport=httpx.MockTransport(_handler))

        world = build_world(mcp_http_client_factory=_refuse)
        app = make_connector_app(world, current)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            await _connect_async(http, "github")

            response = await http.get("/api/connectors/github/tools")

        assert response.status_code == 502
        assert response.json()["detail"] == {
            "error": "The provider is temporarily unavailable",
            "code": "provider_unavailable",
            "recoverable": True,
        }


async def _connect_async(http: httpx.AsyncClient, key: str) -> httpx.Response:
    started = await http.post(f"/api/connectors/{key}/authorize")
    state = parse_qs(urlsplit(started.json()["authorization_url"]).query)["state"][0]
    return await http.get(
        "/api/connectors/oauth/callback",
        params={
            "state": state,
            "code": "auth-code",
            "iss": "https://github.com/login/oauth",
        },
    )
