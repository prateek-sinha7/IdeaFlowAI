"""Unit tests for ``app.connectors.services.build_connector_services``."""

from __future__ import annotations

import pytest

from app.connectors.binder import ConnectorRunToolBinder
from app.connectors.crypto import TokenCipher
from app.connectors.errors import ConnectorNotConfigured
from app.connectors.services import build_connector_services
from tests.fakes.oauth_provider import FakeOAuthProvider
from tests.unit.app.connectors.conftest import make_settings


def _no_session():
    raise AssertionError("no database access expected")


def test_build_connector_services_wires_real_cipher_when_key_valid():
    # Act
    services = build_connector_services(make_settings(), _no_session)

    # Assert
    assert isinstance(services.cipher, TokenCipher)
    assert services.registry.is_configured("github")
    assert services.cipher.decrypt(services.cipher.encrypt("x")) == "x"


def test_build_connector_services_exposes_run_binder_when_built():
    # Act
    services = build_connector_services(make_settings(), _no_session)

    # Assert
    assert isinstance(services.binder, ConnectorRunToolBinder)


def test_build_connector_services_fails_closed_when_key_missing():
    # Act
    services = build_connector_services(
        make_settings(TOKEN_ENCRYPTION_KEY=""), _no_session
    )

    # Assert
    assert not services.registry.is_configured("github")
    with pytest.raises(ConnectorNotConfigured):
        services.cipher.encrypt("token")
    with pytest.raises(ConnectorNotConfigured):
        services.cipher.decrypt("ciphertext")


def test_build_connector_services_uses_injected_http_factory_when_given():
    # Arrange
    provider = FakeOAuthProvider()
    services = build_connector_services(
        make_settings(), _no_session, http_factory=provider.http_factory
    )

    # Act
    account = services.oauth_client.fetch_account(
        services.registry.get("github").definition,
        "tok",  # type: ignore[union-attr]
    )

    # Assert
    assert account.account_id == "4242"
    assert provider.requests[0].bearer == "tok"


def test_build_connector_services_applies_tuning_settings_when_built():
    # Act
    services = build_connector_services(
        make_settings(CONNECTOR_REFRESH_SKEW_SECONDS="60"), _no_session
    )

    # Assert
    assert services.tokens._skew.total_seconds() == 60
