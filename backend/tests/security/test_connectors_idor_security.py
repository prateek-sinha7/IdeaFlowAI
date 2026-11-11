"""Security: authentication and per-user isolation on every ``/api/connectors`` route.

Anonymous callers get 401 everywhere except the OAuth callback (whose credential is
the state). Alice and Bob each see and delete only their own connection, and the
GitHub tool list is fetched with the caller's own token only.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.fakes.connector_app import (
    CurrentUser,
    connect_through_api,
    make_connector_app,
    make_user,
)
from tests.fakes.connector_services import ConnectorWorld, build_world
from tests.fakes.oauth_provider import (
    GITHUB_TOKEN_URL,
    github_token_body,
    json_response,
)
from tests.fakes.streamable_http_mcp import FakeGitHubMcpServer

ALICE = "alice"
BOB = "bob"

ANONYMOUS_ROUTES = [
    ("GET", "/api/connectors"),
    ("POST", "/api/connectors/jira/authorize"),
    ("DELETE", "/api/connectors/jira"),
    ("GET", "/api/connectors/jira/tools"),
    ("GET", "/api/connectors/github/tools"),
]


@pytest.fixture
def world() -> ConnectorWorld:
    """The connectors runtime on fakes."""
    return build_world()


@pytest.fixture
def current() -> CurrentUser:
    """The caller; tests switch it between Alice, Bob and nobody."""
    return CurrentUser(make_user(ALICE))


@pytest.fixture
def client(world: ConnectorWorld, current: CurrentUser) -> Iterator[TestClient]:
    """A client over the connectors router."""
    with TestClient(make_connector_app(world, current)) as test_client:
        yield test_client


@pytest.mark.parametrize(("method", "path"), ANONYMOUS_ROUTES)
def test_route_answers_401_when_caller_is_anonymous(
    client: TestClient, current: CurrentUser, method: str, path: str
) -> None:
    current.user = None

    response = client.request(method, path)

    assert response.status_code == 401


def test_callback_needs_no_bearer_when_caller_is_anonymous(
    client: TestClient, current: CurrentUser
) -> None:
    current.user = None

    response = client.get("/api/connectors/oauth/callback", follow_redirects=False)

    assert response.status_code == 303


def test_list_shows_only_own_connection_when_two_users_connected(
    client: TestClient, current: CurrentUser
) -> None:
    connect_through_api(client, "jira")
    current.user = make_user(BOB)

    bob_view = client.get("/api/connectors").json()["connectors"]

    jira = next(c for c in bob_view if c["key"] == "jira")
    assert jira["status"] == "not_connected"
    assert jira["account"] is None
    assert jira["sites"] == []


def test_disconnect_deletes_only_own_connection_when_other_user_calls_it(
    client: TestClient, world: ConnectorWorld, current: CurrentUser
) -> None:
    connect_through_api(client, "jira")
    current.user = make_user(BOB)

    response = client.delete("/api/connectors/jira")

    assert response.json()["provider_revocation"] == "not_attempted"
    assert world.store.get(ALICE, "jira") is not None


def test_disconnect_does_not_call_provider_when_caller_has_no_connection(
    client: TestClient, world: ConnectorWorld, current: CurrentUser
) -> None:
    connect_through_api(client, "jira")
    world.provider.requests.clear()
    current.user = make_user(BOB)

    client.delete("/api/connectors/jira")

    assert world.provider.requests == []


def test_tools_status_follows_caller_when_two_users_differ(
    client: TestClient, current: CurrentUser
) -> None:
    connect_through_api(client, "jira")
    current.user = make_user(BOB)

    bob = client.get("/api/connectors/jira/tools").json()
    current.user = make_user(ALICE)
    alice = client.get("/api/connectors/jira/tools").json()

    assert (alice["status"], bob["status"]) == ("connected", "not_connected")


def test_github_tools_answer_409_when_other_user_has_no_connection(
    client: TestClient, current: CurrentUser
) -> None:
    connect_through_api(client, "github")
    current.user = make_user(BOB)

    response = client.get("/api/connectors/github/tools")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "connector_not_connected"


@pytest.mark.asyncio
async def test_github_tool_listing_uses_only_callers_token_when_two_users_list(
    current: CurrentUser,
) -> None:
    async with FakeGitHubMcpServer() as server:
        server.add_read_tool("list_issues")
        world = build_world(mcp_http_client_factory=server.client_factory)
        app = make_connector_app(world, current)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            # Alice and Bob get different GitHub tokens from the provider.
            tokens = {ALICE: "gho_alice_token", BOB: "gho_bob_token"}
            for user_id, token in tokens.items():
                current.user = make_user(user_id)
                world.provider.respond(
                    "POST",
                    GITHUB_TOKEN_URL,
                    json_response(200, github_token_body(access_token=token)),
                )
                await _connect(http)
            server.requests.clear()

            seen: dict[str, set[str]] = {}
            for user_id in (BOB, ALICE):
                current.user = make_user(user_id)
                before = len(server.requests)
                response = await http.get("/api/connectors/github/tools")
                assert response.status_code == 200
                seen[user_id] = {
                    req["authorization"].removeprefix("Bearer ")
                    for req in server.requests[before:]
                }

    assert seen == {BOB: {"gho_bob_token"}, ALICE: {"gho_alice_token"}}


async def _connect(http: httpx.AsyncClient) -> None:
    started = await http.post("/api/connectors/github/authorize")
    state = parse_qs(urlsplit(started.json()["authorization_url"]).query)["state"][0]
    params: dict[str, Any] = {
        "state": state,
        "code": "code-1",
        "iss": "https://github.com/login/oauth",
    }
    response = await http.get("/api/connectors/oauth/callback", params=params)
    assert response.status_code == 303
