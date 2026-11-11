"""Security: provider tokens, codes, verifiers and keys never leave the server.

A full lifecycle (authorize, callback, list, tools, refresh, disconnect, account
deletion) runs with seeded sentinel values for every secret. None of them may appear
in an API response body or header, a log record (root logger at DEBUG), an audit
row, or a ciphertext column. The OAuth ``state`` is the one exception: it must reach
the browser inside ``authorization_url`` (the provider echoes it back), and nowhere
else.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import asdict
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.connectors.account_deletion import AccountDeletion, CollectedGrant
from app.connectors.errors import ConnectorError, ToolErrorCode
from app.connectors.store import ConnectionRecord
from tests.fakes.connector_app import (
    CurrentUser,
    connect_through_api,
    make_connector_app,
    make_user,
)
from tests.fakes.connector_services import ConnectorWorld, build_world
from tests.fakes.connector_settings import make_settings
from tests.fakes.oauth_provider import (
    ATLASSIAN_TOKEN_URL,
    GITHUB_TOKEN_URL,
    atlassian_token_body,
    github_token_body,
    json_response,
    query_of,
)

USER = "user-a"
CODE = "authcode-sentinel-1234"

GH_ACCESS, GH_REFRESH = "gho_access_sentinel", "ghr_refresh_sentinel"
JIRA_ACCESS, JIRA_REFRESH = "atl_access_sentinel", "atl_refresh_sentinel"
JIRA_ACCESS_2, JIRA_REFRESH_2 = "atl_access_sentinel_2", "atl_refresh_sentinel_2"


@pytest.fixture
def world() -> ConnectorWorld:
    """The connectors runtime with sentinel tokens at both providers."""
    built = build_world(make_settings())
    built.provider.respond(
        "POST",
        GITHUB_TOKEN_URL,
        json_response(
            200, github_token_body(access_token=GH_ACCESS, refresh_token=GH_REFRESH)
        ),
    )
    built.provider.respond(
        "POST",
        ATLASSIAN_TOKEN_URL,
        json_response(
            200,
            atlassian_token_body(access_token=JIRA_ACCESS, refresh_token=JIRA_REFRESH),
        ),
        json_response(
            200,
            atlassian_token_body(
                access_token=JIRA_ACCESS_2, refresh_token=JIRA_REFRESH_2
            ),
        ),
    )
    return built


@pytest.fixture
def client(world: ConnectorWorld) -> Iterator[TestClient]:
    """A client over the connectors router, signed in as ``user-a``."""
    with TestClient(
        make_connector_app(world, CurrentUser(make_user(USER)))
    ) as test_client:
        yield test_client


def _secrets(world: ConnectorWorld) -> dict[str, str]:
    """Every value that must stay server-side, by name."""
    verifiers = {
        f"verifier-{i}": (call.json_body or call.form_body or {}).get(
            "code_verifier", ""
        )
        for i, call in enumerate(
            world.provider.calls("POST", ATLASSIAN_TOKEN_URL)
            + world.provider.calls("POST", GITHUB_TOKEN_URL)
        )
    }
    values = {
        "github access": GH_ACCESS,
        "github refresh": GH_REFRESH,
        "jira access": JIRA_ACCESS,
        "jira refresh": JIRA_REFRESH,
        "jira access 2": JIRA_ACCESS_2,
        "jira refresh 2": JIRA_REFRESH_2,
        "authorization code": CODE,
        "github client secret": "github-secret-sentinel",
        "jira client secret": "jira-secret-sentinel",
        "encryption key": world.settings.TOKEN_ENCRYPTION_KEY,
        **{k: v for k, v in verifiers.items() if v},
    }
    assert all(values.values())
    return values


def _assert_absent(text: str, secrets: dict[str, str], where: str) -> None:
    for name, value in secrets.items():
        assert value not in text, f"{name} leaked into {where}"


def test_secrets_stay_out_of_responses_logs_and_audit_when_full_lifecycle_runs(
    client: TestClient,
    world: ConnectorWorld,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="app")
    responses: list[str] = []
    states: list[str] = []

    def _record(response) -> None:  # type: ignore[no-untyped-def]
        responses.append(f"{response.headers}\n{response.text}")

    for key in ("github", "jira"):
        started = client.post(f"/api/connectors/{key}/authorize")
        _record(started)
        state = query_of(started.json()["authorization_url"])["state"]
        states.append(state)
        params = {"state": state, "code": CODE}
        if key == "github":
            params["iss"] = "https://github.com/login/oauth"
        callback = client.get(
            "/api/connectors/oauth/callback", params=params, follow_redirects=False
        )
        _record(callback)
    _record(client.get("/api/connectors"))
    _record(client.get("/api/connectors/jira/tools"))

    # Force a refresh of the Jira token (rotation), then read the list again.
    world.clock.advance(3600)
    world.services.tokens.access_token_blocking(USER, "jira")
    _record(client.get("/api/connectors"))
    _record(client.delete("/api/connectors/github"))
    _record(client.delete("/api/connectors/jira"))

    secrets = _secrets(world)
    # The lifecycle really rotated the Jira tokens (code exchange, then one refresh).
    assert len(world.provider.calls("POST", ATLASSIAN_TOKEN_URL)) == 2
    for body in responses:
        _assert_absent(body, secrets, "an API response")
    _assert_absent(caplog.text, secrets, "a log record")
    for state in states:
        assert state not in caplog.text, "an OAuth state leaked into a log record"
    audit_text = repr([asdict(entry) for entry in world.store.audit])
    _assert_absent(audit_text, secrets, "an audit row")
    assert not any(state in audit_text for state in states)


def test_state_appears_only_in_authorization_url_when_authorize_responds(
    client: TestClient,
) -> None:
    started = client.post("/api/connectors/jira/authorize")
    state = query_of(started.json()["authorization_url"])["state"]

    body = dict(started.json())
    url = body.pop("authorization_url")

    assert state in url
    assert state not in str(body)
    assert state not in str(started.headers)


def test_ciphertext_columns_never_contain_plaintext_when_connection_stored(
    client: TestClient, world: ConnectorWorld
) -> None:
    connect_through_api(client, "github", code=CODE)
    connect_through_api(client, "jira", code=CODE)

    for record in world.store.connections.values():
        assert isinstance(record, ConnectionRecord)
        for plaintext in (GH_ACCESS, GH_REFRESH, JIRA_ACCESS, JIRA_REFRESH):
            assert plaintext not in record.access_token_ciphertext
            assert plaintext not in (record.refresh_token_ciphertext or "")
        assert "sentinel" not in repr(record)


def test_oauth_state_rows_hold_no_plaintext_state_or_verifier_when_authorize_runs(
    client: TestClient, world: ConnectorWorld
) -> None:
    started = client.post("/api/connectors/jira/authorize")
    state = query_of(started.json()["authorization_url"])["state"]

    assert state not in world.store.states  # keyed by hash
    for row in world.store.states.values():
        assert state not in repr(row)
        assert len(row["verifier"]) > 86  # a Fernet token, not the 86-char verifier


def test_account_deletion_logs_and_events_hold_no_secrets_when_revokes_fail(
    world: ConnectorWorld, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="app")
    deletion: AccountDeletion = world.services.account_deletion
    world.provider.respond(
        "DELETE",
        "https://api.github.com/applications/github-client-id/grant",
        json_response(500, {"message": f"token {GH_ACCESS} rejected"}),
    )
    world.provider.respond(
        "POST", "https://auth.atlassian.com/oauth/revoke", json_response(500, {})
    )
    grants = [
        CollectedGrant(
            "github",
            attemptable=True,
            access_token=GH_ACCESS,
            refresh_token=GH_REFRESH,
            access_token_expires_at=world.clock() + timedelta(hours=1),
        ),
        CollectedGrant(
            "jira",
            attemptable=True,
            access_token=JIRA_ACCESS,
            refresh_token=JIRA_REFRESH,
        ),
    ]

    outcome = deletion.revoke(USER, grants)

    assert outcome == {"github": "failed", "jira": "failed"}
    secrets = {
        "github access": GH_ACCESS,
        "github refresh": GH_REFRESH,
        "jira access": JIRA_ACCESS,
        "jira refresh": JIRA_REFRESH,
        "github client secret": "github-secret-sentinel",
        "jira client secret": "jira-secret-sentinel",
    }
    _assert_absent(caplog.text, secrets, "a log record")
    _assert_absent(repr(outcome), secrets, "the revocation outcome")
    _assert_absent(repr(grants), secrets, "a grant repr")


def test_refresh_failure_logs_no_provider_body_when_provider_rejects_token(
    client: TestClient, world: ConnectorWorld, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="app")
    connect_through_api(client, "jira", code=CODE)
    world.provider.respond(
        "POST",
        ATLASSIAN_TOKEN_URL,
        json_response(
            400,
            {
                "error": "invalid_grant",
                "error_description": "refresh token atl_refresh_sentinel is revoked",
            },
        ),
    )
    world.clock.advance(7200)

    with pytest.raises(ConnectorError) as excinfo:
        world.services.tokens.access_token_blocking(USER, "jira")

    assert excinfo.value.code is ToolErrorCode.CONNECTION_EXPIRED
    assert "refresh rejected" in caplog.text  # the failure was logged, and cleanly
    assert "atl_refresh_sentinel" not in str(excinfo.value)
    assert "is revoked" not in caplog.text
    assert "atl_refresh_sentinel" not in caplog.text
