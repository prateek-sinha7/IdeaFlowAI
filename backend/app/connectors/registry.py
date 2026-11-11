"""Connector registry: catalog definitions plus their configured status.

The pure-data catalog lives in ``agents/capabilities/connector_catalog.py``. This
app-side registry adds what needs Settings: whether each connector is configured,
its client credentials and the OAuth redirect URI. The kernel never reads Settings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from agents.capabilities.connector_catalog import (
    CONNECTORS,
    ConnectorDefinition,
    get_connector,
)
from app.connectors.errors import ConnectorNotConfigured
from app.core.config import Settings

logger = logging.getLogger("app.connectors.registry")


@dataclass(frozen=True)
class ClientCredentials:
    """The OAuth client id and secret of one connector. The secret never appears in a repr."""

    client_id: str
    client_secret: str = field(repr=False)


@dataclass(frozen=True)
class RegisteredConnector:
    """One catalog definition with its status on this server.

    ``issues`` names the variables that block it (never values); it is empty exactly
    when ``configured`` is true.
    """

    definition: ConnectorDefinition
    configured: bool
    issues: tuple[str, ...] = ()


class ConnectorRegistry:
    """Catalog definitions with their configured status, taken from one Settings snapshot."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        config_issues = settings.connector_config_issues()
        entries: list[RegisteredConnector] = []
        for definition in CONNECTORS:
            issues = config_issues.for_connector(definition.key)
            entries.append(
                RegisteredConnector(
                    definition=definition, configured=not issues, issues=issues
                )
            )
        self._entries: tuple[RegisteredConnector, ...] = tuple(entries)
        # The redirect URI is only meaningful when the base URL and path are valid.
        self._redirect_uri: str | None = (
            None if config_issues.shared else settings.connector_redirect_uri
        )

    @property
    def redirect_uri(self) -> str | None:
        """The exact redirect URI to register at the providers, or ``None`` when it is invalid."""
        return self._redirect_uri

    def all(self) -> tuple[RegisteredConnector, ...]:
        """Return every connector in catalog order."""
        return self._entries

    def get(self, key: str) -> RegisteredConnector | None:
        """Return the connector registered under ``key``, or ``None`` when unknown."""
        if get_connector(key) is None:
            return None
        return next(entry for entry in self._entries if entry.definition.key == key)

    def is_configured(self, key: str) -> bool:
        """Return whether ``key`` names a known connector that is usable on this server."""
        entry = self.get(key)
        return entry is not None and entry.configured

    def client_credentials(self, key: str) -> ClientCredentials:
        """Return the OAuth client credentials of connector ``key``.

        Raises:
            KeyError: ``key`` is not a catalog connector.
            ConnectorNotConfigured: the connector's settings are missing or invalid.
        """
        entry = self.get(key)
        if entry is None:
            raise KeyError(key)
        if not entry.configured:
            raise ConnectorNotConfigured(key)
        definition = entry.definition
        return ClientCredentials(
            client_id=getattr(self._settings, definition.client_id_env),
            client_secret=getattr(self._settings, definition.client_secret_env),
        )

    def log_status(self) -> None:
        """Log one INFO line per connector so an operator can compare the redirect URI
        with the provider console. Nothing secret is logged."""
        for entry in self._entries:
            logger.info(
                "connectors: %s configured=%s redirect_uri=%s",
                entry.definition.key,
                str(entry.configured).lower(),
                self._redirect_uri or "<invalid>",
            )
