"""Unit tests for ``app.connectors.adapters.atlassian``."""

from __future__ import annotations

import pytest

from agents.capabilities.connector_catalog import JIRA
from app.connectors.adapters import RevokeMaterial
from app.connectors.adapters.atlassian import AtlassianAdapter
from app.connectors.http import ProviderCallFailed
from app.connectors.registry import ClientCredentials
from tests.fakes.oauth_provider import (
    ATLASSIAN_SITES_URL,
    FakeOAuthProvider,
    empty_response,
    jira_site,
    json_response,
)

_CREDS = ClientCredentials(client_id="cid", client_secret="csecret")


def _client(provider: FakeOAuthProvider):
    return provider.http_factory()


class TestAtlassianAdapter:
    def _run(self, provider: FakeOAuthProvider):
        return AtlassianAdapter().post_connect(_client(provider), JIRA, "tok")

    def test_post_connect_keeps_only_sites_with_jira_read_scope_when_listed(self):
        # Arrange
        provider = FakeOAuthProvider()
        provider.respond(
            "GET",
            ATLASSIAN_SITES_URL,
            json_response(
                200,
                [
                    jira_site(),
                    jira_site(id="c2", scopes=["read:confluence-content.all"]),
                    jira_site(id="c3", url="http://insecure.example"),
                    jira_site(id="", name="No id"),
                    "not-a-dict",
                ],
            ),
        )

        # Act
        result = self._run(provider)

        # Assert
        assert result.usable
        assert result.metadata == {
            "sites": [
                {"id": "cloud-1", "name": "Acme", "url": "https://acme.atlassian.net"}
            ]
        }
        (call,) = provider.calls("GET", ATLASSIAN_SITES_URL)
        assert call.bearer == "tok"

    def test_post_connect_is_unusable_when_no_site_has_jira_scope(self):
        # Arrange
        provider = FakeOAuthProvider()
        provider.respond("GET", ATLASSIAN_SITES_URL, json_response(200, []))

        # Act
        result = self._run(provider)

        # Assert
        assert not result.usable
        assert result.metadata == {"sites": []}

    def test_post_connect_caps_site_count_when_provider_lists_many(self):
        # Arrange
        provider = FakeOAuthProvider()
        sites = [jira_site(id=f"c{i}", name=f"S{i}") for i in range(80)]
        provider.respond("GET", ATLASSIAN_SITES_URL, json_response(200, sites))

        # Act
        result = self._run(provider)

        # Assert
        assert result.metadata is not None and len(result.metadata["sites"]) == 50

    @pytest.mark.parametrize(
        ("responder", "kind"),
        [
            (empty_response(401), "rejected"),
            (json_response(200, {"not": "a list"}), "malformed"),
            (empty_response(503), "unavailable"),
        ],
    )
    def test_post_connect_raises_when_provider_answer_unusable(self, responder, kind):
        # Arrange
        provider = FakeOAuthProvider()
        provider.respond("GET", ATLASSIAN_SITES_URL, responder)

        # Act
        with pytest.raises(ProviderCallFailed) as raised:
            self._run(provider)

        # Assert
        assert raised.value.kind == kind

    def test_revoke_prefers_refresh_token_when_both_available(self):
        # Arrange
        provider = FakeOAuthProvider()

        # Act
        outcome = AtlassianAdapter().revoke(
            _client(provider),
            JIRA,
            _CREDS,
            RevokeMaterial(access_token="acc", refresh_token="ref"),
        )

        # Assert
        assert outcome == "revoked"
        (call,) = provider.calls("POST", "https://auth.atlassian.com/oauth/revoke")
        assert call.json_body is not None
        assert call.json_body["token"] == "ref"
        assert call.json_body["client_secret"] == "csecret"
