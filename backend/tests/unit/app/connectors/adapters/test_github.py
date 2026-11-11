"""Unit tests for ``app.connectors.adapters.github``."""

from __future__ import annotations

import pytest

from agents.capabilities.connector_catalog import GITHUB
from app.connectors.adapters import RevokeMaterial
from app.connectors.adapters.github import GITHUB_API_VERSION, GitHubAdapter
from app.connectors.registry import ClientCredentials
from tests.fakes.oauth_provider import FakeOAuthProvider, empty_response

_CREDS = ClientCredentials(client_id="cid", client_secret="csecret")
_GRANT = "https://api.github.com/applications/cid/grant"


def _client(provider: FakeOAuthProvider):
    return provider.http_factory()


class TestGitHubAdapter:
    def test_account_headers_pin_api_version_when_requested(self):
        # Act
        headers = GitHubAdapter().account_headers()

        # Assert
        assert headers["X-GitHub-Api-Version"] == GITHUB_API_VERSION
        assert headers["Accept"] == "application/vnd.github+json"

    def test_revoke_needs_access_token_is_true_when_github(self):
        # Assert
        assert GitHubAdapter.revoke_needs_access_token is True

    @pytest.mark.parametrize("status", [204, 404, 422])
    def test_revoke_returns_revoked_when_grant_deleted_or_already_gone(self, status):
        # Arrange
        provider = FakeOAuthProvider("cid")
        provider.respond("DELETE", _GRANT, empty_response(status))

        # Act
        outcome = GitHubAdapter().revoke(
            _client(provider), GITHUB, _CREDS, RevokeMaterial(access_token="tok")
        )

        # Assert
        assert outcome == "revoked"
        (call,) = provider.calls("DELETE", _GRANT)
        assert call.json_body == {"access_token": "tok"}
        assert call.headers["authorization"].startswith("Basic ")
        assert call.headers["x-github-api-version"] == GITHUB_API_VERSION

    @pytest.mark.parametrize("status", [400, 401, 403, 500])
    def test_revoke_returns_failed_when_provider_refuses(self, status):
        # Arrange
        provider = FakeOAuthProvider("cid")
        provider.respond("DELETE", _GRANT, empty_response(status))

        # Act
        outcome = GitHubAdapter().revoke(
            _client(provider), GITHUB, _CREDS, RevokeMaterial(access_token="tok")
        )

        # Assert
        assert outcome == "failed"
