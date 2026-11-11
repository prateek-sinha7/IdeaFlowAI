"""Unit tests for ``agents.capabilities.connector_catalog`` (the connector data source)."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from agents.capabilities import connector_catalog
from agents.capabilities.connector_catalog import (
    CONNECTOR_KEY_PATTERN,
    CONNECTORS,
    RESERVED_CONNECTOR_KEYS,
    connector_keys,
    get_connector,
)
from app.core.config import Settings

_TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_MAX_BOUND_TOOL_NAME_LENGTH = 64


def _jira_native_tools():
    jira = get_connector("jira")
    assert jira is not None
    return jira.tooling.native_tools


def test_connectors_lists_github_then_jira_when_catalog_loaded():
    # Act
    keys = connector_keys()

    # Assert
    assert keys == ("github", "jira")


@pytest.mark.parametrize("definition", CONNECTORS, ids=lambda d: d.key)
def test_connector_key_matches_pattern_and_is_not_reserved_when_defined(definition):
    # Assert
    assert CONNECTOR_KEY_PATTERN.fullmatch(definition.key)
    assert definition.key not in RESERVED_CONNECTOR_KEYS


def test_connector_keys_are_unique_when_catalog_loaded():
    # Act
    keys = connector_keys()

    # Assert
    assert len(set(keys)) == len(keys)


def test_oauth_is_reserved_when_checking_route_words():
    # Assert: "oauth" names the /api/connectors/oauth/callback route segment.
    assert "oauth" in RESERVED_CONNECTOR_KEYS


@pytest.mark.parametrize("definition", CONNECTORS, ids=lambda d: d.key)
def test_every_endpoint_uses_https_when_connector_defined(definition):
    # Arrange
    urls = [
        definition.docs_url,
        definition.oauth.authorize_url,
        definition.oauth.token_url,
        definition.oauth.issuer,
        definition.revoke.url,
        definition.account.url,
    ]
    if definition.tooling.mcp_url:
        urls.append(definition.tooling.mcp_url)
    if definition.oauth.resource_indicator:
        urls.append(definition.oauth.resource_indicator)

    # Assert
    for url in urls:
        assert urlsplit(url).scheme == "https", url


@pytest.mark.parametrize("definition", CONNECTORS, ids=lambda d: d.key)
def test_credential_env_names_are_settings_fields_when_connector_defined(definition):
    # Act
    fields = set(Settings.model_fields)

    # Assert
    assert definition.client_id_env in fields
    assert definition.client_secret_env in fields
    assert definition.client_id_env != definition.client_secret_env


def test_pkce_is_enabled_for_every_connector_when_defined():
    # Assert
    assert all(definition.oauth.pkce for definition in CONNECTORS)


def test_every_connector_requests_a_refresh_token_scope_when_defined():
    # Assert
    assert all("offline_access" in definition.oauth.scopes for definition in CONNECTORS)


def test_github_requires_iss_and_pins_resource_when_defined():
    # Arrange
    github = get_connector("github")

    # Assert
    assert github is not None
    assert github.oauth.iss_param == "required"
    assert github.oauth.resource_indicator == github.tooling.mcp_url
    assert github.tooling.mode == "remote_mcp"
    assert github.tooling.tool_allow == ("*",)
    assert github.tooling.tool_deny == ()


def test_jira_accepts_missing_iss_and_declares_native_tools_when_defined():
    # Arrange
    jira = get_connector("jira")

    # Assert
    assert jira is not None
    assert jira.oauth.iss_param == "if_present"
    assert jira.oauth.resource_indicator is None
    assert jira.tooling.mode == "native_api"
    assert jira.post_connect == "atlassian_accessible_resources"


def test_jira_native_tool_names_are_unique_and_valid_when_declared():
    # Arrange
    names = [tool.name for tool in _jira_native_tools()]

    # Assert
    assert len(names) == 10
    assert len(set(names)) == len(names)
    assert all(_TOOL_NAME_PATTERN.fullmatch(name) for name in names)


def test_jira_flags_exactly_the_five_write_tools_when_declared():
    # Act
    writers = {tool.name for tool in _jira_native_tools() if tool.write_capable}

    # Assert
    assert writers == {
        "create_issue",
        "update_issue",
        "add_comment",
        "transition_issue",
        "assign_issue",
    }


def test_jira_write_tools_need_write_scope_and_read_tools_need_read_scope_when_declared():
    # Assert
    for tool in _jira_native_tools():
        expected = ("write:jira-work",) if tool.write_capable else ("read:jira-work",)
        assert tool.required_scopes == expected, tool.name


def test_jira_required_scopes_are_requested_scopes_when_declared():
    # Arrange
    jira = get_connector("jira")
    assert jira is not None

    # Assert
    for tool in jira.tooling.native_tools:
        assert set(tool.required_scopes) <= set(jira.oauth.scopes), tool.name


def test_bound_tool_names_fit_the_length_limit_when_native_tools_declared():
    # Assert: bound name is f"{key}__{name}", at most 64 characters.
    for definition in CONNECTORS:
        for tool in definition.tooling.native_tools:
            assert len(f"{definition.key}__{tool.name}") <= _MAX_BOUND_TOOL_NAME_LENGTH


def test_get_connector_returns_none_when_key_unknown():
    # Assert
    assert get_connector("nope") is None


def test_catalog_imports_only_stdlib_when_module_loaded():
    # Arrange
    source = Path(connector_catalog.__file__).read_text(encoding="utf-8")
    imports = re.findall(r"^(?:from|import)\s+([\w.]+)", source, flags=re.MULTILINE)

    # Assert: no app.* and no kernel import (INV capability boundary).
    assert not [name for name in imports if name.split(".")[0] in {"app", "agents"}]
