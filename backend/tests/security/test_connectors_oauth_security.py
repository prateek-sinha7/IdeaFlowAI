"""Security: the OAuth authorize/callback flow of ``/api/connectors``.

The state is the callback's only credential, so these tests attack it: replay,
expiry, another user's browser, a forged landing URL, a mismatched issuer and a
smuggled redirect parameter. They also pin PKCE (S256, verifier bound to the
challenge) and the exact redirect URI. The runtime is real; providers are fake.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Iterator
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.fakes.connector_app import (
    GITHUB_ISSUER,
    CurrentUser,
    connect_through_api,
    make_connector_app,
    make_user,
)
from tests.fakes.connector_services import ConnectorWorld, build_world
from tests.fakes.connector_settings import REDIRECT_URI
from tests.fakes.oauth_provider import ATLASSIAN_TOKEN_URL, GITHUB_TOKEN_URL, query_of

ALICE = "alice"
BOB = "bob"


@pytest.fixture
def world() -> ConnectorWorld:
    """The connectors runtime on fakes."""
    return build_world()


@pytest.fixture
def current() -> CurrentUser:
    """The caller, signed in as Alice."""
    return CurrentUser(make_user(ALICE))


@pytest.fixture
def client(world: ConnectorWorld, current: CurrentUser) -> Iterator[TestClient]:
    """A client over the connectors router."""
    with TestClient(make_connector_app(world, current)) as test_client:
        yield test_client


def _reason(response: httpx.Response) -> str | None:
    query = parse_qs(urlsplit(response.headers["location"]).query)
    return query.get("reason", [None])[0]


def _authorize(client: TestClient, key: str = "jira") -> str:
    started = client.post(f"/api/connectors/{key}/authorize")
    assert started.status_code == 200, started.text
    return started.json()["authorization_url"]


def test_callback_rejects_second_use_of_state_when_callback_is_replayed(
    client: TestClient, world: ConnectorWorld
) -> None:
    state = query_of(_authorize(client))["state"]
    params = {"state": state, "code": "code-1"}
    first = client.get(
        "/api/connectors/oauth/callback", params=params, follow_redirects=False
    )
    token_calls_after_first = len(world.provider.calls("POST", ATLASSIAN_TOKEN_URL))
    stored_after_first = world.store.get(ALICE, "jira")

    second = client.get(
        "/api/connectors/oauth/callback", params=params, follow_redirects=False
    )

    assert _reason(first) is None
    assert _reason(second) == "invalid_state"
    assert (
        len(world.provider.calls("POST", ATLASSIAN_TOKEN_URL))
        == token_calls_after_first
    )
    assert world.store.get(ALICE, "jira") == stored_after_first


def test_callback_links_initiators_account_when_another_users_browser_loads_it(
    client: TestClient, world: ConnectorWorld, current: CurrentUser
) -> None:
    state = query_of(_authorize(client))["state"]
    current.user = make_user(BOB)  # Bob's browser follows Alice's redirect

    response = client.get(
        "/api/connectors/oauth/callback",
        params={"state": state, "code": "code-1"},
        follow_redirects=False,
    )

    assert _reason(response) is None
    assert world.store.get(ALICE, "jira") is not None
    assert world.store.get(BOB, "jira") is None


def test_callback_rejects_state_when_it_expired(
    client: TestClient, world: ConnectorWorld
) -> None:
    state = query_of(_authorize(client))["state"]
    world.clock.advance(601)

    response = client.get(
        "/api/connectors/oauth/callback",
        params={"state": state, "code": "code-1"},
        follow_redirects=False,
    )

    assert _reason(response) == "invalid_state"
    assert world.provider.calls("POST", ATLASSIAN_TOKEN_URL) == []
    assert world.store.get(ALICE, "jira") is None


def test_callback_accepts_state_when_ten_minutes_minus_one_second_passed(
    client: TestClient, world: ConnectorWorld
) -> None:
    state = query_of(_authorize(client))["state"]
    world.clock.advance(599)

    response = client.get(
        "/api/connectors/oauth/callback",
        params={"state": state, "code": "code-1"},
        follow_redirects=False,
    )

    assert _reason(response) is None


def test_callback_rejects_unknown_state_when_state_is_guessed(
    client: TestClient, world: ConnectorWorld
) -> None:
    _authorize(client)

    response = client.get(
        "/api/connectors/oauth/callback",
        params={"state": "A" * 43, "code": "code-1"},
        follow_redirects=False,
    )

    assert _reason(response) == "invalid_state"
    assert world.provider.requests == []


def test_callback_stores_nothing_when_landing_url_is_forged(
    client: TestClient, world: ConnectorWorld
) -> None:
    forged = client.get(
        "/api/connectors/oauth/callback",
        params={"connector": "jira", "result": "connected"},
        follow_redirects=False,
    )

    statuses = {
        c["key"]: c["status"]
        for c in client.get("/api/connectors").json()["connectors"]
    }
    assert _reason(forged) == "invalid_state"
    assert statuses == {"github": "not_connected", "jira": "not_connected"}
    assert world.store.connections == {}


def test_callback_rejects_wrong_issuer_without_redeeming_code_when_iss_differs(
    client: TestClient, world: ConnectorWorld
) -> None:
    response = connect_through_api(
        client, "github", iss="https://evil.example/login/oauth"
    )

    assert _reason(response) == "issuer_mismatch"
    assert world.provider.calls("POST", GITHUB_TOKEN_URL) == []
    assert world.store.get(ALICE, "github") is None


def test_callback_rejects_github_flow_when_iss_is_missing(
    client: TestClient, world: ConnectorWorld
) -> None:
    state = query_of(_authorize(client, "github"))["state"]

    response = client.get(
        "/api/connectors/oauth/callback",
        params={"state": state, "code": "code-1"},
        follow_redirects=False,
    )

    assert _reason(response) == "issuer_missing"
    assert world.provider.calls("POST", GITHUB_TOKEN_URL) == []


def test_callback_uses_connector_of_state_when_other_providers_issuer_is_sent(
    client: TestClient, world: ConnectorWorld
) -> None:
    state = query_of(_authorize(client, "jira"))["state"]

    response = client.get(
        "/api/connectors/oauth/callback",
        params={"state": state, "code": "code-1", "iss": GITHUB_ISSUER},
        follow_redirects=False,
    )

    assert _reason(response) == "issuer_mismatch"
    assert world.provider.calls("POST", ATLASSIAN_TOKEN_URL) == []
    assert world.provider.calls("POST", GITHUB_TOKEN_URL) == []


def test_callback_answers_with_no_store_and_no_referrer_when_redirecting(
    client: TestClient,
) -> None:
    response = client.get("/api/connectors/oauth/callback", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers.get_list("cache-control") == ["no-store"]
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_callback_redirects_to_same_origin_path_when_redirect_params_are_smuggled(
    client: TestClient,
) -> None:
    state = query_of(_authorize(client))["state"]

    response = client.get(
        "/api/connectors/oauth/callback",
        params={
            "state": state,
            "code": "code-1",
            "return_to": "https://evil.example/steal",
            "redirect_uri": "https://evil.example/steal",
            "next": "https://evil.example/steal",
        },
        follow_redirects=False,
    )

    location = response.headers["location"]
    assert location.startswith("/connectors/oauth-complete?")
    assert "evil.example" not in location


def test_authorize_ignores_redirect_parameters_when_caller_sends_them(
    client: TestClient,
) -> None:
    started = client.post(
        "/api/connectors/jira/authorize",
        params={
            "return_to": "https://evil.example",
            "redirect_uri": "https://evil.example",
        },
        json={"redirect_uri": "https://evil.example"},
    )

    assert started.status_code == 200
    query = query_of(started.json()["authorization_url"])
    assert query["redirect_uri"] == REDIRECT_URI
    assert "evil.example" not in started.text


def test_authorize_url_carries_s256_challenge_and_exact_redirect_uri_when_started(
    client: TestClient,
) -> None:
    query = query_of(_authorize(client, "github"))

    assert query["code_challenge_method"] == "S256"
    assert len(query["code_challenge"]) == 43
    assert query["redirect_uri"] == REDIRECT_URI
    assert query["response_type"] == "code"
    assert len(query["state"]) >= 43


def test_token_request_sends_verifier_matching_challenge_when_code_redeemed(
    client: TestClient, world: ConnectorWorld
) -> None:
    challenge = query_of(_authorize(client, "jira"))
    state_query = challenge
    client.get(
        "/api/connectors/oauth/callback",
        params={"state": state_query["state"], "code": "code-1"},
        follow_redirects=False,
    )

    (call,) = world.provider.calls("POST", ATLASSIAN_TOKEN_URL)

    verifier = (call.json_body or {})["code_verifier"]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    assert expected == state_query["code_challenge"]
    assert (call.json_body or {})["redirect_uri"] == REDIRECT_URI
    assert (call.json_body or {})["code"] == "code-1"


def test_authorize_answers_429_when_user_opens_six_authorizations(
    client: TestClient,
) -> None:
    for _ in range(5):
        _authorize(client)

    assert client.post("/api/connectors/jira/authorize").status_code == 429


def test_authorization_states_differ_between_calls_when_started_twice(
    client: TestClient,
) -> None:
    states = {query_of(_authorize(client))["state"] for _ in range(3)}

    assert len(states) == 3
