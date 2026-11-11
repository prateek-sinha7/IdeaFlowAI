"""Unit tests for the provider adapters (default behaviour, GitHub, Atlassian)."""

from __future__ import annotations

import httpx
import pytest

from agents.capabilities.connector_catalog import GITHUB, JIRA
from app.connectors.adapters import (
    ProviderAdapter,
    RevokeMaterial,
    get_adapter,
    split_scopes,
)
from app.connectors.adapters.atlassian import AtlassianAdapter
from app.connectors.adapters.github import GITHUB_API_VERSION, GitHubAdapter
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
_GRANT = "https://api.github.com/applications/cid/grant"


def _client(provider: FakeOAuthProvider) -> httpx.Client:
    return provider.http_factory()


# ---------------------------------------------------------------------------
# registry and defaults
# ---------------------------------------------------------------------------


def test_get_adapter_returns_specific_adapters_when_connector_known():
    # Act / Assert
    assert isinstance(get_adapter("github"), GitHubAdapter)
    assert isinstance(get_adapter("jira"), AtlassianAdapter)


def test_get_adapter_returns_default_behaviour_when_connector_has_no_adapter():
    # Act
    adapter = get_adapter("somethingnew")

    # Assert
    assert type(adapter) is ProviderAdapter


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ()),
        ("", ()),
        ("repo, user  repo", ("repo", "user")),
        ("read:jira-work write:jira-work", ("read:jira-work", "write:jira-work")),
    ],
)
def test_split_scopes_splits_on_commas_and_whitespace_when_given_scope_string(
    raw, expected
):
    # Act / Assert
    assert split_scopes(raw) == expected


class TestParseAccount:
    def test_parse_account_reads_spec_fields_and_scope_header_when_github_answer(self):
        # Arrange
        response = httpx.Response(
            200,
            json={"id": 7, "login": "octo", "name": " The Octo "},
            headers={"X-OAuth-Scopes": "repo, read:org"},
        )

        # Act
        account = GitHubAdapter().parse_account(GITHUB, response)

        # Assert
        assert account.account_id == "7"
        assert account.login == "octo"
        assert account.display_name == "The Octo"
        assert account.scopes == ("repo", "read:org")

    def test_parse_account_leaves_scopes_unset_when_header_absent(self):
        # Act
        account = ProviderAdapter().parse_account(
            JIRA, httpx.Response(200, json={"account_id": "a1", "name": "J"})
        )

        # Assert
        assert account.scopes is None
        assert account.login is None

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"id": None},
            {"id": True},
            {"id": ""},
            {"id": "x" * 129},
            {"id": [1]},
            [],
        ],
    )
    def test_parse_account_raises_malformed_when_account_id_unusable(self, body):
        # Act
        with pytest.raises(ProviderCallFailed) as raised:
            GitHubAdapter().parse_account(GITHUB, httpx.Response(200, json=body))

        # Assert
        assert raised.value.kind == "malformed"

    def test_parse_account_raises_rejected_when_status_is_error(self):
        # Act
        with pytest.raises(ProviderCallFailed) as raised:
            GitHubAdapter().parse_account(GITHUB, httpx.Response(401, json={"id": 1}))

        # Assert
        assert raised.value.kind == "rejected"


def test_revoke_material_repr_hides_tokens_when_formatted():
    # Act
    text = repr(RevokeMaterial(access_token="secret-a", refresh_token="secret-r"))

    # Assert
    assert "secret-a" not in text and "secret-r" not in text


def test_client_credentials_repr_hides_secret_when_formatted():
    # Act / Assert
    assert "csecret" not in repr(_CREDS)
