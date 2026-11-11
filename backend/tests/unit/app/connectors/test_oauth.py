"""Unit tests for ``app.connectors.oauth`` (authorize, callback, disconnect)."""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest

from app.connectors.errors import (
    CallbackReason,
    ConnectorNotConfigured,
    ConnectorNotFound,
    TooManyPendingAuthorizations,
)
from app.connectors.oauth import (
    MAX_PENDING_STATES,
    STATE_TTL_SECONDS,
    CallbackParams,
)
from app.connectors.pkce import code_challenge_s256, hash_state
from app.models.connector import CONNECTION_STATUS_ACTIVE
from tests.fakes.oauth_provider import (
    ATLASSIAN_ME_URL,
    ATLASSIAN_REVOKE_URL,
    ATLASSIAN_SITES_URL,
    ATLASSIAN_TOKEN_URL,
    GITHUB_GRANT_URL,
    GITHUB_TOKEN_URL,
    GITHUB_USER_URL,
    empty_response,
    github_token_body,
    jira_site,
    json_response,
    query_of,
    text_response,
    timeout_response,
)
from tests.unit.app.connectors.conftest import (
    CLIENT_SECRETS,
    REDIRECT_URI,
    USER_ID,
    Wired,
    make_settings,
    wire,
)

GITHUB_ISS = "https://github.com/login/oauth"
JIRA_ISS = "https://auth.atlassian.com"
GRANT_URL = GITHUB_GRANT_URL.format(client_id="github-client-id")


def _start(
    w: Wired, key: str = "github", user: str = USER_ID
) -> tuple[str, dict[str, str]]:
    start = w.oauth.start_authorization(user, key)
    query = query_of(start.authorization_url)
    return query["state"], query


def _callback(w: Wired, state: str, **overrides: str | None):
    params = {"state": state, "code": "auth-code-1", "iss": GITHUB_ISS, "error": None}
    params.update(overrides)
    return w.oauth.complete_callback(CallbackParams(**params))


# ---------------------------------------------------------------------------
# start_authorization
# ---------------------------------------------------------------------------


class TestStartAuthorization:
    def test_start_authorization_builds_github_url_when_configured(self, wired: Wired):
        # Act
        start = wired.oauth.start_authorization(USER_ID, "github")

        # Assert
        query = query_of(start.authorization_url)
        assert start.authorization_url.startswith(
            "https://github.com/login/oauth/authorize?"
        )
        assert query["response_type"] == "code"
        assert query["client_id"] == "github-client-id"
        assert query["redirect_uri"] == REDIRECT_URI
        assert query["scope"] == "repo offline_access"
        assert query["code_challenge_method"] == "S256"
        assert query["resource"] == "https://api.githubcopilot.com/mcp/"

    def test_start_authorization_adds_atlassian_params_when_connector_is_jira(
        self, wired: Wired
    ):
        # Act
        start = wired.oauth.start_authorization(USER_ID, "jira")

        # Assert
        query = query_of(start.authorization_url)
        assert query["audience"] == "api.atlassian.com"
        assert query["prompt"] == "consent"
        assert "resource" not in query
        assert query["scope"] == "read:jira-work write:jira-work read:me offline_access"

    def test_start_authorization_binds_challenge_to_stored_verifier_when_started(
        self, wired: Wired
    ):
        # Act
        state, query = _start(wired)

        # Assert
        stored = wired.store.states[hash_state(state)]
        verifier = wired.cipher.decrypt(stored["verifier"])
        assert query["code_challenge"] == code_challenge_s256(verifier)
        assert stored["user_id"] == USER_ID
        assert stored["connector_key"] == "github"
        assert stored["redirect_uri"] == REDIRECT_URI

    def test_start_authorization_stores_only_state_hash_and_encrypted_verifier_when_started(
        self, wired: Wired
    ):
        # Act
        state, _ = _start(wired)

        # Assert
        assert state not in wired.store.states
        stored = wired.store.states[hash_state(state)]
        assert wired.cipher.decrypt(stored["verifier"]) not in stored["verifier"]

    def test_start_authorization_expires_state_in_ten_minutes_when_started(
        self, wired: Wired
    ):
        # Act
        start = wired.oauth.start_authorization(USER_ID, "github")

        # Assert
        assert STATE_TTL_SECONDS == 600
        assert start.expires_at == wired.clock.now + timedelta(seconds=600)

    def test_start_authorization_writes_audit_row_when_started(self, wired: Wired):
        # Act
        wired.oauth.start_authorization(USER_ID, "jira")

        # Assert
        assert wired.store.audit_actions() == [("authorize_started", "ok", None)]

    def test_start_authorization_raises_not_found_when_connector_unknown(
        self, wired: Wired
    ):
        # Act / Assert
        with pytest.raises(ConnectorNotFound):
            wired.oauth.start_authorization(USER_ID, "slack")

    def test_start_authorization_raises_not_configured_when_secret_missing(self):
        # Arrange
        w = wire(make_settings(JIRA_OAUTH_CLIENT_SECRET=""))

        # Act / Assert
        with pytest.raises(ConnectorNotConfigured):
            w.oauth.start_authorization(USER_ID, "jira")
        assert w.store.states == {}

    def test_start_authorization_raises_too_many_pending_when_cap_reached(
        self, wired: Wired
    ):
        # Arrange
        for _ in range(MAX_PENDING_STATES):
            wired.oauth.start_authorization(USER_ID, "github")

        # Act / Assert
        with pytest.raises(TooManyPendingAuthorizations):
            wired.oauth.start_authorization(USER_ID, "github")

    def test_start_authorization_allows_other_user_when_first_user_at_cap(
        self, wired: Wired
    ):
        # Arrange
        for _ in range(MAX_PENDING_STATES):
            wired.oauth.start_authorization(USER_ID, "github")

        # Act
        start = wired.oauth.start_authorization("user-b", "github")

        # Assert
        assert start.authorization_url


# ---------------------------------------------------------------------------
# complete_callback: success
# ---------------------------------------------------------------------------


class TestCompleteCallbackSuccess:
    def test_complete_callback_connects_github_when_code_valid(self, wired: Wired):
        # Arrange
        state, _ = _start(wired)

        # Act
        outcome = _callback(wired, state)

        # Assert
        assert outcome.connected
        assert outcome.connector_key == "github"
        record = wired.store.get(USER_ID, "github")
        assert record is not None
        assert record.status == CONNECTION_STATUS_ACTIVE
        assert record.provider_account_id == "4242"
        assert record.provider_account_login == "octocat"
        assert record.provider_account_name == "The Octocat"
        assert record.granted_scopes == ("repo",)
        assert record.access_token_expires_at == wired.clock.now + timedelta(
            seconds=28800
        )

    def test_complete_callback_encrypts_tokens_when_stored(self, wired: Wired):
        # Arrange
        state, _ = _start(wired)

        # Act
        _callback(wired, state)

        # Assert
        record = wired.store.get(USER_ID, "github")
        assert record is not None
        assert record.access_token_ciphertext != "gho_access_initial"
        assert (
            wired.cipher.decrypt(record.access_token_ciphertext) == "gho_access_initial"
        )
        assert record.refresh_token_ciphertext is not None
        assert (
            wired.cipher.decrypt(record.refresh_token_ciphertext)
            == "ghr_refresh_initial"
        )

    def test_complete_callback_sends_stored_redirect_and_verifier_when_exchanging_code(
        self, wired: Wired
    ):
        # Arrange
        state, query = _start(wired)
        verifier = wired.cipher.decrypt(
            wired.store.states[hash_state(state)]["verifier"]
        )

        # Act
        _callback(wired, state)

        # Assert
        (call,) = wired.provider.calls("POST", GITHUB_TOKEN_URL)
        assert call.form_body is not None
        assert call.form_body["code"] == "auth-code-1"
        assert call.form_body["code_verifier"] == verifier
        assert call.form_body["redirect_uri"] == REDIRECT_URI
        assert call.form_body["grant_type"] == "authorization_code"
        assert call.form_body["client_id"] == "github-client-id"
        assert (
            call.form_body["client_secret"]
            == CLIENT_SECRETS["GITHUB_OAUTH_CLIENT_SECRET"]
        )
        assert call.form_body["resource"] == "https://api.githubcopilot.com/mcp/"
        assert call.headers["accept"] == "application/json"
        assert query["state"] == state

    def test_complete_callback_sends_json_token_request_when_connector_is_jira(
        self, wired: Wired
    ):
        # Arrange
        state, _ = _start(wired, "jira")

        # Act
        outcome = _callback(wired, state, iss=None)

        # Assert
        assert outcome.connected
        (call,) = wired.provider.calls("POST", ATLASSIAN_TOKEN_URL)
        assert call.json_body is not None
        assert (
            call.json_body["client_secret"]
            == CLIENT_SECRETS["JIRA_OAUTH_CLIENT_SECRET"]
        )
        assert "resource" not in call.json_body

    def test_complete_callback_stores_jira_sites_and_scopes_when_connected(
        self, wired: Wired
    ):
        # Arrange
        wired.provider.respond(
            "GET",
            ATLASSIAN_SITES_URL,
            json_response(
                200,
                [
                    jira_site(),
                    jira_site(
                        id="cloud-2", name="Other", url="https://o.atlassian.net/"
                    ),
                    jira_site(
                        id="cloud-3",
                        name="Confluence only",
                        scopes=["read:confluence-content.all"],
                    ),
                ],
            ),
        )
        state, _ = _start(wired, "jira")

        # Act
        _callback(wired, state, iss=JIRA_ISS)

        # Assert
        record = wired.store.get(USER_ID, "jira")
        assert record is not None
        assert record.provider_account_id == "acc-1"
        assert record.provider_account_login is None
        assert record.provider_metadata == {
            "sites": [
                {"id": "cloud-1", "name": "Acme", "url": "https://acme.atlassian.net"},
                {"id": "cloud-2", "name": "Other", "url": "https://o.atlassian.net"},
            ]
        }
        assert "write:jira-work" in record.granted_scopes

    def test_complete_callback_increments_version_when_reconnecting(self, wired: Wired):
        # Arrange
        _callback(wired, _start(wired)[0])

        # Act
        _callback(wired, _start(wired)[0])

        # Assert
        record = wired.store.get(USER_ID, "github")
        assert record is not None
        assert record.token_version == 2

    def test_complete_callback_writes_connected_audit_row_when_connected(
        self, wired: Wired
    ):
        # Arrange
        state, _ = _start(wired)

        # Act
        _callback(wired, state)

        # Assert
        assert ("connected", "ok", None) in wired.store.audit_actions()

    def test_complete_callback_accepts_missing_iss_when_connector_is_jira(
        self, wired: Wired
    ):
        # Arrange
        state, _ = _start(wired, "jira")

        # Act
        outcome = _callback(wired, state, iss=None)

        # Assert
        assert outcome.connected


# ---------------------------------------------------------------------------
# complete_callback: state handling
# ---------------------------------------------------------------------------


class TestCompleteCallbackState:
    def test_complete_callback_rejects_replay_when_state_already_used(
        self, wired: Wired
    ):
        # Arrange
        state, _ = _start(wired)
        _callback(wired, state)

        # Act
        second = _callback(wired, state)

        # Assert
        assert second.reason is CallbackReason.INVALID_STATE
        assert second.connector_key is None
        assert len(wired.provider.calls("POST", GITHUB_TOKEN_URL)) == 1
        record = wired.store.get(USER_ID, "github")
        assert record is not None and record.token_version == 1

    @pytest.mark.parametrize(
        "state", [None, "", "short", "a" * 19, "a" * 129, "bad state with spaces!!"]
    )
    def test_complete_callback_rejects_state_when_shape_invalid(
        self, wired: Wired, state
    ):
        # Act
        outcome = wired.oauth.complete_callback(CallbackParams(state=state, code="c"))

        # Assert
        assert outcome.reason is CallbackReason.INVALID_STATE
        assert wired.provider.requests == []

    def test_complete_callback_rejects_unknown_state_when_never_issued(
        self, wired: Wired
    ):
        # Act
        outcome = _callback(wired, "u" * 43)

        # Assert
        assert outcome.reason is CallbackReason.INVALID_STATE
        assert wired.provider.requests == []

    def test_complete_callback_rejects_state_when_expired(self, wired: Wired):
        # Arrange
        state, _ = _start(wired)
        wired.clock.advance(STATE_TTL_SECONDS + 1)

        # Act
        outcome = _callback(wired, state)

        # Assert
        assert outcome.reason is CallbackReason.INVALID_STATE
        assert wired.provider.requests == []
        assert wired.store.get(USER_ID, "github") is None

    def test_complete_callback_links_initiating_user_only_when_another_browser_loads_it(
        self, wired: Wired
    ):
        # Arrange
        state, _ = _start(wired, user="user-a")

        # Act
        _callback(wired, state)

        # Assert
        assert wired.store.get("user-a", "github") is not None
        assert wired.store.get("user-b", "github") is None

    def test_complete_callback_sweeps_old_states_when_called(self, wired: Wired):
        # Arrange
        old, _ = _start(wired)
        wired.clock.advance(STATE_TTL_SECONDS + 25 * 3600)
        fresh, _ = _start(wired, user="user-b")

        # Act
        _callback(wired, fresh)

        # Assert
        assert hash_state(old) not in wired.store.states

    def test_complete_callback_logs_hash_prefix_only_when_state_unknown(
        self, wired: Wired, caplog: pytest.LogCaptureFixture
    ):
        # Arrange
        state = "q" * 43

        # Act
        with caplog.at_level(logging.DEBUG):
            _callback(wired, state)

        # Assert
        assert state not in caplog.text
        assert hash_state(state)[:8] in caplog.text
        assert hash_state(state) not in caplog.text


# ---------------------------------------------------------------------------
# complete_callback: provider and parameter failures
# ---------------------------------------------------------------------------


class TestCompleteCallbackFailures:
    @pytest.mark.parametrize(
        ("error", "reason"),
        [
            ("access_denied", CallbackReason.ACCESS_DENIED),
            ("server_error", CallbackReason.PROVIDER_ERROR),
            ("Bad Value!", CallbackReason.PROVIDER_ERROR),
        ],
    )
    def test_complete_callback_maps_provider_error_when_error_param_present(
        self, wired: Wired, error, reason
    ):
        # Arrange
        state, _ = _start(wired)

        # Act
        outcome = _callback(wired, state, code=None, error=error)

        # Assert
        assert outcome.reason is reason
        assert outcome.connector_key == "github"
        assert wired.provider.calls("POST", GITHUB_TOKEN_URL) == []
        assert wired.store.get(USER_ID, "github") is None

    def test_complete_callback_consumes_state_when_provider_returned_error(
        self, wired: Wired
    ):
        # Arrange
        state, _ = _start(wired)
        _callback(wired, state, code=None, error="access_denied")

        # Act
        retry = _callback(wired, state)

        # Assert
        assert retry.reason is CallbackReason.INVALID_STATE

    def test_complete_callback_rejects_missing_iss_when_connector_requires_it(
        self, wired: Wired
    ):
        # Arrange
        state, _ = _start(wired)

        # Act
        outcome = _callback(wired, state, iss=None)

        # Assert
        assert outcome.reason is CallbackReason.ISSUER_MISSING
        assert wired.provider.calls("POST", GITHUB_TOKEN_URL) == []

    @pytest.mark.parametrize(
        "iss",
        ["https://evil.example", GITHUB_ISS + "/", GITHUB_ISS.upper(), "x" * 300],
    )
    def test_complete_callback_rejects_issuer_when_not_exactly_equal(
        self, wired: Wired, iss
    ):
        # Arrange
        state, _ = _start(wired)

        # Act
        outcome = _callback(wired, state, iss=iss)

        # Assert
        assert outcome.reason is CallbackReason.ISSUER_MISMATCH
        assert wired.provider.calls("POST", GITHUB_TOKEN_URL) == []

    def test_complete_callback_rejects_wrong_issuer_when_connector_is_jira(
        self, wired: Wired
    ):
        # Arrange
        state, _ = _start(wired, "jira")

        # Act
        outcome = _callback(wired, state, iss=GITHUB_ISS)

        # Assert
        assert outcome.reason is CallbackReason.ISSUER_MISMATCH

    @pytest.mark.parametrize("code", [None, "", "has space", "x" * 2049, "caf\u00e9"])
    def test_complete_callback_rejects_missing_code_when_code_absent_or_malformed(
        self, wired: Wired, code
    ):
        # Arrange
        state, _ = _start(wired)

        # Act
        outcome = _callback(wired, state, code=code)

        # Assert
        assert outcome.reason is CallbackReason.MISSING_CODE
        assert wired.provider.calls("POST", GITHUB_TOKEN_URL) == []

    @pytest.mark.parametrize(
        "responder",
        [
            json_response(200, {"error": "bad_verification_code"}),
            json_response(400, {"error": "invalid_grant"}),
            json_response(401, {"message": "no error field"}),
            text_response(400, "not json"),
            json_response(200, {"token_type": "bearer"}),
            json_response(200, github_token_body(token_type="mac")),
            json_response(200, github_token_body(expires_in="soon")),
            json_response(200, ["unexpected"]),
        ],
    )
    def test_complete_callback_fails_exchange_and_stores_nothing_when_answer_unusable(
        self, wired: Wired, responder
    ):
        # Arrange
        wired.provider.respond("POST", GITHUB_TOKEN_URL, responder)
        state, _ = _start(wired)

        # Act
        outcome = _callback(wired, state)

        # Assert
        assert outcome.reason is CallbackReason.TOKEN_EXCHANGE_FAILED
        assert wired.store.get(USER_ID, "github") is None
        assert wired.provider.calls("GET", GITHUB_USER_URL) == []

    def test_complete_callback_logs_env_names_without_values_when_client_refused(
        self, wired: Wired, caplog: pytest.LogCaptureFixture
    ):
        # Arrange
        wired.provider.respond(
            "POST",
            GITHUB_TOKEN_URL,
            json_response(200, {"error": "incorrect_client_credentials"}),
        )
        state, _ = _start(wired)

        # Act
        with caplog.at_level(logging.DEBUG):
            outcome = _callback(wired, state)

        # Assert
        assert outcome.reason is CallbackReason.TOKEN_EXCHANGE_FAILED
        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert any("GITHUB_OAUTH_CLIENT_ID" in r.getMessage() for r in errors)
        assert CLIENT_SECRETS["GITHUB_OAUTH_CLIENT_SECRET"] not in caplog.text

    @pytest.mark.parametrize(
        "responder", [timeout_response, empty_response(503), empty_response(429)]
    )
    def test_complete_callback_reports_provider_error_when_token_endpoint_unavailable(
        self, wired: Wired, responder
    ):
        # Arrange
        wired.provider.respond("POST", GITHUB_TOKEN_URL, responder)
        state, _ = _start(wired)

        # Act
        outcome = _callback(wired, state)

        # Assert
        assert outcome.reason is CallbackReason.PROVIDER_ERROR
        assert wired.store.get(USER_ID, "github") is None

    @pytest.mark.parametrize(
        "responder",
        [
            empty_response(401),
            timeout_response,
            json_response(200, {"login": "no-id"}),
            json_response(200, {"id": True}),
            json_response(200, {"id": "x" * 129}),
            text_response(200, "<html>"),
        ],
    )
    def test_complete_callback_stores_nothing_when_account_lookup_fails(
        self, wired: Wired, responder
    ):
        # Arrange
        wired.provider.respond("GET", GITHUB_USER_URL, responder)
        state, _ = _start(wired)

        # Act
        outcome = _callback(wired, state)

        # Assert
        assert outcome.reason is CallbackReason.ACCOUNT_LOOKUP_FAILED
        assert wired.store.get(USER_ID, "github") is None

    def test_complete_callback_reports_no_sites_when_no_jira_site_granted(
        self, wired: Wired
    ):
        # Arrange
        wired.provider.respond(
            "GET",
            ATLASSIAN_SITES_URL,
            json_response(200, [jira_site(scopes=["read:confluence-content.all"])]),
        )
        state, _ = _start(wired, "jira")

        # Act
        outcome = _callback(wired, state, iss=None)

        # Assert
        assert outcome.reason is CallbackReason.NO_ACCESSIBLE_SITES
        assert wired.store.get(USER_ID, "jira") is None

    def test_complete_callback_reports_lookup_failure_when_sites_call_fails(
        self, wired: Wired
    ):
        # Arrange
        wired.provider.respond("GET", ATLASSIAN_SITES_URL, empty_response(403))
        state, _ = _start(wired, "jira")

        # Act
        outcome = _callback(wired, state, iss=None)

        # Assert
        assert outcome.reason is CallbackReason.ACCOUNT_LOOKUP_FAILED
        assert wired.provider.calls("GET", ATLASSIAN_ME_URL)

    def test_complete_callback_reports_server_error_and_keeps_key_when_store_fails(
        self, wired: Wired
    ):
        # Arrange
        wired.store.fail_upsert = True
        state, _ = _start(wired)

        # Act
        outcome = _callback(wired, state)

        # Assert
        assert outcome.reason is CallbackReason.SERVER_ERROR
        assert outcome.connector_key == "github"

    def test_complete_callback_reports_not_configured_when_connector_lost_its_secret(
        self, wired: Wired
    ):
        # Arrange
        state, _ = _start(wired)
        broken = wire(make_settings(GITHUB_OAUTH_CLIENT_SECRET=""))
        broken.store.states = wired.store.states
        broken.cipher = wired.cipher

        # Act
        outcome = _callback(broken, state)

        # Assert
        assert outcome.reason is CallbackReason.NOT_CONFIGURED
        assert outcome.connector_key == "github"

    def test_complete_callback_never_raises_when_store_breaks_unexpectedly(
        self, wired: Wired, monkeypatch: pytest.MonkeyPatch
    ):
        # Arrange
        state, _ = _start(wired)

        def explode(_hash: str):
            raise RuntimeError("database gone")

        monkeypatch.setattr(wired.store, "consume_state", explode)

        # Act
        outcome = _callback(wired, state)

        # Assert
        assert outcome.reason is CallbackReason.SERVER_ERROR
        assert outcome.connector_key is None

    def test_complete_callback_reports_server_error_when_verifier_undecryptable(
        self, wired: Wired
    ):
        # Arrange
        state, _ = _start(wired)
        wired.store.states[hash_state(state)]["verifier"] = "garbage"

        # Act
        outcome = _callback(wired, state)

        # Assert
        assert outcome.reason is CallbackReason.SERVER_ERROR
        assert wired.provider.calls("POST", GITHUB_TOKEN_URL) == []

    def test_complete_callback_writes_failed_audit_row_without_secrets_when_exchange_fails(
        self, wired: Wired
    ):
        # Arrange
        wired.provider.respond(
            "POST",
            GITHUB_TOKEN_URL,
            json_response(200, {"error": "bad_verification_code"}),
        )
        state, _ = _start(wired)

        # Act
        _callback(wired, state)

        # Assert
        assert (
            "connect_failed",
            "error",
            "bad_verification_code",
        ) in wired.store.audit_actions()
        assert "auth-code-1" not in repr(wired.store.audit)


def test_complete_callback_logs_no_secret_values_when_flow_succeeds(
    wired: Wired, caplog: pytest.LogCaptureFixture
):
    # Arrange
    with caplog.at_level(logging.DEBUG):
        state, _ = _start(wired)
        verifier = wired.cipher.decrypt(
            wired.store.states[hash_state(state)]["verifier"]
        )

        # Act
        _callback(wired, state)

    # Assert
    for secret in (
        state,
        verifier,
        "auth-code-1",
        "gho_access_initial",
        "ghr_refresh_initial",
        CLIENT_SECRETS["GITHUB_OAUTH_CLIENT_SECRET"],
    ):
        assert secret not in caplog.text


def test_callback_params_repr_hides_code_and_state_when_formatted():
    # Act
    text = repr(CallbackParams(state="s" * 43, code="secret-code"))

    # Assert
    assert "secret-code" not in text
    assert "s" * 43 not in text


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------


def _connect(w: Wired, key: str = "github") -> None:
    state, _ = _start(w, key)
    outcome = _callback(w, state, iss=GITHUB_ISS if key == "github" else None)
    assert outcome.connected


class TestDisconnect:
    def test_disconnect_revokes_github_grant_and_deletes_row_when_connected(
        self, wired: Wired
    ):
        # Arrange
        _connect(wired)

        # Act
        outcome = wired.oauth.disconnect(USER_ID, "github")

        # Assert
        assert outcome.provider_revocation == "revoked"
        assert outcome.was_connected
        assert wired.store.get(USER_ID, "github") is None
        (call,) = wired.provider.calls("DELETE", GRANT_URL)
        assert call.json_body == {"access_token": "gho_access_initial"}
        assert call.headers["authorization"].startswith("Basic ")
        assert ("disconnected", "ok", None) in wired.store.audit_actions()

    def test_disconnect_refreshes_expired_github_token_first_when_token_expired(
        self, wired: Wired
    ):
        # Arrange
        _connect(wired)
        wired.clock.advance(28800 + 60)
        wired.provider.respond(
            "POST",
            GITHUB_TOKEN_URL,
            json_response(
                200,
                github_token_body(
                    access_token="gho_access_new", refresh_token="ghr_new"
                ),
            ),
        )

        # Act
        outcome = wired.oauth.disconnect(USER_ID, "github")

        # Assert
        assert outcome.provider_revocation == "revoked"
        (call,) = wired.provider.calls("DELETE", GRANT_URL)
        assert call.json_body == {"access_token": "gho_access_new"}

    def test_disconnect_reports_failed_and_still_deletes_row_when_refresh_fails(
        self, wired: Wired
    ):
        # Arrange
        _connect(wired)
        wired.clock.advance(28800 + 60)
        wired.provider.respond(
            "POST", GITHUB_TOKEN_URL, json_response(200, {"error": "bad_refresh_token"})
        )

        # Act
        outcome = wired.oauth.disconnect(USER_ID, "github")

        # Assert
        assert outcome.provider_revocation == "failed"
        assert wired.store.get(USER_ID, "github") is None
        assert wired.provider.calls("DELETE", GRANT_URL) == []
        assert (
            "revoke_failed",
            "error",
            "revoke_failed",
        ) in wired.store.audit_actions()

    @pytest.mark.parametrize(
        ("responder", "expected"),
        [
            (empty_response(204), "revoked"),
            (empty_response(404), "revoked"),
            (empty_response(422), "revoked"),
            (empty_response(500), "failed"),
            (empty_response(403), "failed"),
            (timeout_response, "failed"),
        ],
    )
    def test_disconnect_maps_github_revoke_answer_when_provider_responds(
        self, wired: Wired, responder, expected
    ):
        # Arrange
        _connect(wired)
        wired.provider.respond("DELETE", GRANT_URL, responder)

        # Act
        outcome = wired.oauth.disconnect(USER_ID, "github")

        # Assert
        assert outcome.provider_revocation == expected
        assert wired.store.get(USER_ID, "github") is None

    def test_disconnect_revokes_refresh_token_with_json_when_connector_is_jira(
        self, wired: Wired
    ):
        # Arrange
        _connect(wired, "jira")

        # Act
        outcome = wired.oauth.disconnect(USER_ID, "jira")

        # Assert
        assert outcome.provider_revocation == "revoked"
        (call,) = wired.provider.calls("POST", ATLASSIAN_REVOKE_URL)
        assert call.json_body is not None
        assert call.json_body["token"] == "atl_refresh_initial"
        assert call.json_body["token_type_hint"] == "refresh_token"

    def test_disconnect_reports_failed_when_jira_revoke_returns_error(
        self, wired: Wired
    ):
        # Arrange
        _connect(wired, "jira")
        wired.provider.respond("POST", ATLASSIAN_REVOKE_URL, empty_response(400))

        # Act
        outcome = wired.oauth.disconnect(USER_ID, "jira")

        # Assert
        assert outcome.provider_revocation == "failed"

    def test_disconnect_reports_not_attempted_and_deletes_row_when_token_undecryptable(
        self, wired: Wired
    ):
        # Arrange
        _connect(wired)
        record = wired.store.get(USER_ID, "github")
        assert record is not None
        from dataclasses import replace

        wired.store.seed(replace(record, access_token_ciphertext="garbage"))

        # Act
        outcome = wired.oauth.disconnect(USER_ID, "github")

        # Assert
        assert outcome.provider_revocation == "not_attempted"
        assert wired.store.get(USER_ID, "github") is None
        assert wired.provider.calls("DELETE", GRANT_URL) == []

    def test_disconnect_reports_not_attempted_when_connector_not_configured(
        self, wired: Wired
    ):
        # Arrange
        _connect(wired)
        broken = wire(make_settings(GITHUB_OAUTH_CLIENT_SECRET=""))
        broken.store.connections = wired.store.connections

        # Act
        outcome = broken.oauth.disconnect(USER_ID, "github")

        # Assert
        assert outcome.provider_revocation == "not_attempted"
        assert broken.store.get(USER_ID, "github") is None

    def test_disconnect_is_a_no_op_when_nothing_connected(self, wired: Wired):
        # Act
        outcome = wired.oauth.disconnect(USER_ID, "github")

        # Assert
        assert outcome.provider_revocation == "not_attempted"
        assert not outcome.was_connected
        assert wired.provider.requests == []

    def test_disconnect_raises_not_found_when_connector_unknown(self, wired: Wired):
        # Act / Assert
        with pytest.raises(ConnectorNotFound):
            wired.oauth.disconnect(USER_ID, "slack")

    def test_disconnect_leaves_other_users_connection_when_one_user_disconnects(
        self, wired: Wired
    ):
        # Arrange
        _connect(wired)
        state, _ = _start(wired, user="user-b")
        _callback(wired, state)

        # Act
        wired.oauth.disconnect(USER_ID, "github")

        # Assert
        assert wired.store.get("user-b", "github") is not None
