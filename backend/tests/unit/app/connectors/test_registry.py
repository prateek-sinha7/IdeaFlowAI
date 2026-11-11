"""Unit tests for ``app.connectors.registry.ConnectorRegistry``."""

from __future__ import annotations

import logging

import pytest
from cryptography.fernet import Fernet

from agents.capabilities.connector_catalog import CONNECTORS
from app.connectors.errors import ConnectorNotConfigured
from app.connectors.registry import ClientCredentials, ConnectorRegistry
from app.core.config import Settings

_JIRA_SECRET = "jira-secret-sentinel"


def _settings(**overrides: str) -> Settings:
    values: dict[str, str] = {
        "ENV": "development",
        "APP_BASE_URL": "http://localhost:3000",
        "PUBLIC_BASE_URL": "http://localhost:3000",
        "OAUTH_REDIRECT_PATH": "/api/connectors/oauth/callback",
        "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "JIRA_OAUTH_CLIENT_ID": "jira-client-id",
        "JIRA_OAUTH_CLIENT_SECRET": _JIRA_SECRET,
        "GITHUB_OAUTH_CLIENT_ID": "github-client-id",
        "GITHUB_OAUTH_CLIENT_SECRET": "github-secret-sentinel",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_all_lists_catalog_connectors_in_order_when_registry_built():
    # Act
    registry = ConnectorRegistry(_settings())

    # Assert
    assert [entry.definition for entry in registry.all()] == list(CONNECTORS)


def test_every_connector_is_configured_when_settings_complete():
    # Act
    registry = ConnectorRegistry(_settings())

    # Assert
    assert all(entry.configured and entry.issues == () for entry in registry.all())
    assert registry.is_configured("jira")
    assert registry.is_configured("github")


def test_only_jira_is_not_configured_when_jira_secret_missing():
    # Act
    registry = ConnectorRegistry(_settings(JIRA_OAUTH_CLIENT_SECRET=""))

    # Assert
    assert not registry.is_configured("jira")
    assert registry.is_configured("github")
    jira = registry.get("jira")
    assert jira is not None
    assert jira.issues == ("JIRA_OAUTH_CLIENT_SECRET is not set",)


def test_no_connector_is_configured_when_encryption_key_missing():
    # Act
    registry = ConnectorRegistry(_settings(TOKEN_ENCRYPTION_KEY=""))

    # Assert
    assert not any(entry.configured for entry in registry.all())
    assert all("TOKEN_ENCRYPTION_KEY" in " ".join(e.issues) for e in registry.all())


def test_no_connector_is_configured_when_base_url_invalid():
    # Act
    registry = ConnectorRegistry(_settings(APP_BASE_URL="http://localhost:3000/app"))

    # Assert
    assert not any(entry.configured for entry in registry.all())
    assert registry.redirect_uri is None


def test_redirect_uri_joins_base_url_and_path_when_valid():
    # Act
    registry = ConnectorRegistry(_settings(APP_BASE_URL="http://localhost:3000/"))

    # Assert
    assert (
        registry.redirect_uri == "http://localhost:3000/api/connectors/oauth/callback"
    )


def test_redirect_uri_falls_back_to_public_base_url_when_app_base_url_empty():
    # Act
    registry = ConnectorRegistry(
        _settings(APP_BASE_URL="", PUBLIC_BASE_URL="http://localhost:4000")
    )

    # Assert
    assert (
        registry.redirect_uri == "http://localhost:4000/api/connectors/oauth/callback"
    )


def test_get_returns_none_when_key_unknown():
    # Act
    registry = ConnectorRegistry(_settings())

    # Assert
    assert registry.get("slack") is None
    assert not registry.is_configured("slack")


def test_client_credentials_come_from_the_named_settings_fields_when_configured():
    # Act
    credentials = ConnectorRegistry(_settings()).client_credentials("jira")

    # Assert
    assert credentials == ClientCredentials("jira-client-id", _JIRA_SECRET)


def test_client_credentials_hide_secret_when_repr_taken():
    # Act
    text = repr(ConnectorRegistry(_settings()).client_credentials("jira"))

    # Assert
    assert _JIRA_SECRET not in text
    assert "jira-client-id" in text


def test_client_credentials_raise_not_configured_when_connector_unconfigured():
    # Arrange
    registry = ConnectorRegistry(_settings(JIRA_OAUTH_CLIENT_ID=""))

    # Act / Assert
    with pytest.raises(ConnectorNotConfigured):
        registry.client_credentials("jira")


def test_client_credentials_raise_key_error_when_connector_unknown():
    # Act / Assert
    with pytest.raises(KeyError):
        ConnectorRegistry(_settings()).client_credentials("slack")


def test_log_status_logs_one_info_line_per_connector_without_secrets_when_called(
    caplog,
):
    # Arrange
    registry = ConnectorRegistry(_settings(GITHUB_OAUTH_CLIENT_ID=""))

    # Act
    with caplog.at_level(logging.INFO, logger="app.connectors.registry"):
        registry.log_status()

    # Assert
    lines = [
        record.getMessage()
        for record in caplog.records
        if record.name == "app.connectors.registry"
    ]
    assert lines == [
        "connectors: github configured=false redirect_uri="
        "http://localhost:3000/api/connectors/oauth/callback",
        "connectors: jira configured=true redirect_uri="
        "http://localhost:3000/api/connectors/oauth/callback",
    ]
    assert _JIRA_SECRET not in caplog.text
