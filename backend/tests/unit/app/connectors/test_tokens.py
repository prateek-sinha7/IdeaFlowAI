"""Unit tests for ``app.connectors.tokens.TokenProvider``."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import timedelta

import pytest

from app.connectors.errors import (
    ConnectorError,
    ConnectorNotConfigured,
    ConnectorNotFound,
    ToolErrorCode,
)
from app.connectors.store import ConnectionRecord
from app.connectors.tokens import AccessToken
from tests.fakes.connector_store import T0
from tests.fakes.oauth_provider import (
    GITHUB_TOKEN_URL,
    atlassian_token_body,
    empty_response,
    github_token_body,
    json_response,
    slow_response,
    timeout_response,
)
from tests.unit.app.connectors.conftest import (
    USER_ID,
    Wired,
    make_settings,
    wire,
)


def _seed(
    w: Wired,
    *,
    key: str = "github",
    expires_in: float | None = 28800,
    refresh: str | None = "refresh-1",
    **overrides,
) -> ConnectionRecord:
    """Insert an active connection whose access token expires ``expires_in`` s from now."""
    base = ConnectionRecord(
        id="c1",
        user_id=USER_ID,
        connector_key=key,
        status="active",
        provider_account_id="1",
        provider_account_login=None,
        provider_account_name=None,
        granted_scopes=("repo",),
        provider_metadata=None,
        access_token_expires_at=(
            None if expires_in is None else w.clock.now + timedelta(seconds=expires_in)
        ),
        refresh_token_expires_at=None,
        token_version=1,
        last_refreshed_at=None,
        last_error_code=None,
        created_at=T0,
        updated_at=T0,
        access_token_ciphertext=w.cipher.encrypt("access-1"),
        refresh_token_ciphertext=w.cipher.encrypt(refresh) if refresh else None,
    )
    return w.store.seed(replace(base, **overrides))


def _stored_access(w: Wired, key: str = "github") -> str:
    record = w.store.get(USER_ID, key)
    assert record is not None
    return w.cipher.decrypt(record.access_token_ciphertext)


async def test_access_token_returns_stored_token_without_refresh_when_far_from_expiry(
    wired: Wired,
):
    # Arrange
    _seed(wired, expires_in=301)

    # Act
    token = await wired.tokens.access_token(USER_ID, "github")

    # Assert
    assert token == AccessToken(token="access-1", version=1)
    assert wired.provider.requests == []


async def test_access_token_returns_stored_token_when_provider_issued_no_expiry(
    wired: Wired,
):
    # Arrange
    _seed(wired, expires_in=None)
    wired.clock.advance(10**7)

    # Act
    token = await wired.tokens.access_token(USER_ID, "github")

    # Assert
    assert token.token == "access-1"
    assert wired.provider.requests == []


async def test_access_token_refreshes_and_persists_rotation_when_within_skew(
    wired: Wired,
):
    # Arrange
    _seed(wired, expires_in=299)
    wired.provider.respond(
        "POST",
        GITHUB_TOKEN_URL,
        json_response(
            200,
            github_token_body(
                access_token="access-2", refresh_token="refresh-2", expires_in=28800
            ),
        ),
    )

    # Act
    token = await wired.tokens.access_token(USER_ID, "github")

    # Assert
    assert token == AccessToken(token="access-2", version=2)
    (call,) = wired.provider.calls("POST", GITHUB_TOKEN_URL)
    assert call.form_body is not None
    assert call.form_body["grant_type"] == "refresh_token"
    assert call.form_body["refresh_token"] == "refresh-1"
    record = wired.store.get(USER_ID, "github")
    assert record is not None
    assert record.token_version == 2
    assert wired.cipher.decrypt(record.access_token_ciphertext) == "access-2"
    assert record.refresh_token_ciphertext is not None
    assert wired.cipher.decrypt(record.refresh_token_ciphertext) == "refresh-2"
    assert record.last_refreshed_at == wired.clock.now
    assert ("refreshed", "ok", None) in wired.store.audit_actions()


async def test_access_token_keeps_old_refresh_token_when_provider_does_not_rotate(
    wired: Wired,
):
    # Arrange
    _seed(wired, expires_in=10)
    wired.provider.respond(
        "POST",
        GITHUB_TOKEN_URL,
        json_response(200, {"access_token": "access-2", "token_type": "bearer"}),
    )

    # Act
    await wired.tokens.access_token(USER_ID, "github")

    # Assert
    record = wired.store.get(USER_ID, "github")
    assert record is not None and record.refresh_token_ciphertext is not None
    assert wired.cipher.decrypt(record.refresh_token_ciphertext) == "refresh-1"
    assert record.access_token_expires_at is None


async def test_access_token_makes_one_refresh_when_twenty_callers_race(wired: Wired):
    # Arrange
    _seed(wired, expires_in=10)
    wired.provider.respond(
        "POST",
        GITHUB_TOKEN_URL,
        json_response(
            200, github_token_body(access_token="access-2", refresh_token="refresh-2")
        ),
    )

    # Act
    tokens = await asyncio.gather(
        *(wired.tokens.access_token(USER_ID, "github") for _ in range(20))
    )

    # Assert
    assert len(wired.provider.calls("POST", GITHUB_TOKEN_URL)) == 1
    assert {t.token for t in tokens} == {"access-2"}
    assert {t.version for t in tokens} == {2}


async def test_access_token_skips_refresh_when_rejected_version_already_replaced(
    wired: Wired,
):
    # Arrange
    _seed(wired, expires_in=28800, token_version=2)

    # Act
    token = await wired.tokens.access_token(
        USER_ID, "github", force_refresh=True, rejected_version=1
    )

    # Assert
    assert token == AccessToken(token="access-1", version=2)
    assert wired.provider.requests == []


async def test_access_token_refreshes_when_forced_with_current_version(wired: Wired):
    # Arrange
    _seed(wired, expires_in=28800)

    # Act
    token = await wired.tokens.access_token(
        USER_ID, "github", force_refresh=True, rejected_version=1
    )

    # Assert
    assert token.version == 2
    assert len(wired.provider.calls("POST", GITHUB_TOKEN_URL)) == 1


async def test_access_token_expires_connection_when_refresh_token_rejected(
    wired: Wired,
):
    # Arrange
    _seed(wired, expires_in=10)
    wired.provider.respond(
        "POST", GITHUB_TOKEN_URL, json_response(200, {"error": "bad_refresh_token"})
    )

    # Act
    with pytest.raises(ConnectorError) as raised:
        await wired.tokens.access_token(USER_ID, "github")

    # Assert
    assert raised.value.code is ToolErrorCode.CONNECTION_EXPIRED
    record = wired.store.get(USER_ID, "github")
    assert record is not None
    assert record.status == "expired"
    assert record.last_error_code == "bad_refresh_token"
    assert (
        "refresh_failed",
        "error",
        "bad_refresh_token",
    ) in wired.store.audit_actions()


async def test_access_token_does_not_call_provider_again_when_connection_already_expired(
    wired: Wired,
):
    # Arrange
    _seed(wired, status="expired")

    # Act
    with pytest.raises(ConnectorError) as raised:
        await wired.tokens.access_token(USER_ID, "github")

    # Assert
    assert raised.value.code is ToolErrorCode.CONNECTION_EXPIRED
    assert wired.provider.requests == []


async def test_access_token_expires_connection_when_no_refresh_token_stored(
    wired: Wired,
):
    # Arrange
    _seed(wired, expires_in=28800, refresh=None)

    # Act
    with pytest.raises(ConnectorError) as raised:
        await wired.tokens.access_token(USER_ID, "github", force_refresh=True)

    # Assert
    assert raised.value.code is ToolErrorCode.CONNECTION_EXPIRED
    record = wired.store.get(USER_ID, "github")
    assert record is not None and record.last_error_code == "no_refresh_token"
    assert wired.provider.requests == []


async def test_access_token_reports_client_misconfigured_and_keeps_row_when_client_refused(
    wired: Wired, caplog: pytest.LogCaptureFixture
):
    # Arrange
    _seed(wired, expires_in=10)
    wired.provider.respond(
        "POST", GITHUB_TOKEN_URL, json_response(401, {"error": "invalid_client"})
    )

    # Act
    with caplog.at_level(logging.ERROR), pytest.raises(ConnectorError) as raised:
        await wired.tokens.access_token(USER_ID, "github")

    # Assert
    assert raised.value.code is ToolErrorCode.CLIENT_MISCONFIGURED
    record = wired.store.get(USER_ID, "github")
    assert record is not None and record.status == "active"
    assert "GITHUB_OAUTH_CLIENT_SECRET" in caplog.text


@pytest.mark.parametrize("responder", [timeout_response, empty_response(503)])
async def test_access_token_reports_unavailable_and_keeps_row_when_provider_down(
    wired: Wired, responder
):
    # Arrange
    _seed(wired, expires_in=10)
    wired.provider.respond("POST", GITHUB_TOKEN_URL, responder)

    # Act
    with pytest.raises(ConnectorError) as raised:
        await wired.tokens.access_token(USER_ID, "github")

    # Assert
    assert raised.value.code is ToolErrorCode.PROVIDER_UNAVAILABLE
    assert raised.value.recoverable
    record = wired.store.get(USER_ID, "github")
    assert (
        record is not None and record.status == "active" and record.token_version == 1
    )


async def test_access_token_reports_provider_error_when_refresh_answer_malformed(
    wired: Wired,
):
    # Arrange
    _seed(wired, expires_in=10)
    wired.provider.respond(
        "POST", GITHUB_TOKEN_URL, json_response(200, {"token_type": "bearer"})
    )

    # Act
    with pytest.raises(ConnectorError) as raised:
        await wired.tokens.access_token(USER_ID, "github")

    # Assert
    assert raised.value.code is ToolErrorCode.PROVIDER_ERROR


async def test_access_token_returns_no_token_when_commit_fails_after_rotation(
    wired: Wired, caplog: pytest.LogCaptureFixture
):
    # Arrange
    _seed(wired, expires_in=10)
    wired.store.fail_commit = True

    # Act
    with caplog.at_level(logging.ERROR), pytest.raises(ConnectorError) as raised:
        await wired.tokens.access_token(USER_ID, "github")

    # Assert
    assert raised.value.code is ToolErrorCode.PROVIDER_UNAVAILABLE
    assert _stored_access(wired) == "access-1"
    assert any(r.levelno == logging.ERROR for r in caplog.records)
    assert "gho_access_initial" not in caplog.text


async def test_access_token_reports_unavailable_when_refresh_exceeds_time_bound():
    # Arrange
    w = wire(refresh_timeout_seconds=0.05)
    _seed(w, expires_in=10)
    w.provider.respond(
        "POST",
        GITHUB_TOKEN_URL,
        slow_response(json_response(200, github_token_body()), 0.4),
    )

    # Act
    with pytest.raises(ConnectorError) as raised:
        await w.tokens.access_token(USER_ID, "github")

    # Assert
    assert raised.value.code is ToolErrorCode.PROVIDER_UNAVAILABLE
    await asyncio.sleep(0.5)  # let the abandoned worker thread finish


async def test_access_token_raises_connection_missing_with_reconnect_hint_when_no_row(
    wired: Wired,
):
    # Act
    with pytest.raises(ConnectorError) as raised:
        await wired.tokens.access_token(USER_ID, "jira")

    # Assert
    assert raised.value.code is ToolErrorCode.CONNECTION_MISSING
    assert str(raised.value) == "Jira connection missing, reconnect in Connectors"


async def test_access_token_raises_not_found_when_connector_unknown(wired: Wired):
    # Act / Assert
    with pytest.raises(ConnectorNotFound):
        await wired.tokens.access_token(USER_ID, "slack")


async def test_access_token_raises_not_configured_when_connector_unconfigured():
    # Arrange
    w = wire(make_settings(JIRA_OAUTH_CLIENT_ID=""))

    # Act / Assert
    with pytest.raises(ConnectorNotConfigured):
        await w.tokens.access_token(USER_ID, "jira")


async def test_access_token_expires_connection_when_ciphertext_undecryptable(
    wired: Wired,
):
    # Arrange
    _seed(wired, access_token_ciphertext="garbage")

    # Act
    with pytest.raises(ConnectorError) as raised:
        await wired.tokens.access_token(USER_ID, "github")

    # Assert
    assert raised.value.code is ToolErrorCode.CONNECTION_EXPIRED
    record = wired.store.get(USER_ID, "github")
    assert record is not None
    assert record.status == "expired" and record.last_error_code == "undecryptable"


async def test_access_token_serves_each_user_their_own_token_when_two_users_connected(
    wired: Wired,
):
    # Arrange
    _seed(wired)
    other = wired.store.get(USER_ID, "github")
    assert other is not None
    wired.store.seed(
        replace(
            other,
            id="c2",
            user_id="user-b",
            access_token_ciphertext=wired.cipher.encrypt("access-b"),
        )
    )

    # Act
    mine = await wired.tokens.access_token(USER_ID, "github")
    theirs = await wired.tokens.access_token("user-b", "github")

    # Assert
    assert (mine.token, theirs.token) == ("access-1", "access-b")


async def test_access_token_uses_json_refresh_request_when_connector_is_jira(
    wired: Wired,
):
    # Arrange
    _seed(wired, key="jira", expires_in=10)
    wired.provider.respond(
        "POST",
        "https://auth.atlassian.com/oauth/token",
        json_response(200, atlassian_token_body(access_token="jira-2")),
    )

    # Act
    token = await wired.tokens.access_token(USER_ID, "jira")

    # Assert
    assert token.token == "jira-2"
    (call,) = wired.provider.calls("POST", "https://auth.atlassian.com/oauth/token")
    assert call.json_body is not None
    assert call.json_body["grant_type"] == "refresh_token"
    assert "resource" not in call.json_body


def test_access_token_blocking_refreshes_when_within_skew(wired: Wired):
    # Arrange
    _seed(wired, expires_in=10)

    # Act
    token = wired.tokens.access_token_blocking(USER_ID, "github")

    # Assert
    assert token.version == 2
    assert len(wired.provider.calls("POST", GITHUB_TOKEN_URL)) == 1


def test_fresh_access_token_returns_plain_string_when_token_current(wired: Wired):
    # Arrange
    _seed(wired)

    # Act / Assert
    assert wired.tokens.fresh_access_token(USER_ID, "github") == "access-1"


def test_access_token_repr_hides_token_value_when_formatted():
    # Act
    text = repr(AccessToken(token="super-secret-token", version=3))

    # Assert
    assert "super-secret-token" not in text
    assert "version=3" in text


def test_refresh_skew_follows_setting_when_provider_built_from_settings():
    # Arrange
    w = wire(skew_seconds=60)
    _seed(w, expires_in=120)

    # Act
    w.tokens.access_token_blocking(USER_ID, "github")

    # Assert
    assert w.provider.requests == []
