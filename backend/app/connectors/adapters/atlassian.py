"""Atlassian adapter: Jira site discovery after connecting.

Atlassian OAuth tokens are valid for every site the user granted. After the
account lookup the adapter lists the accessible sites and keeps those that grant
the Jira read scope. A connection with no such site is not stored.
"""

from __future__ import annotations

from typing import Any

import httpx

from agents.capabilities.connector_catalog import ConnectorDefinition
from app.connectors.adapters import (
    PostConnectResult,
    ProviderAdapter,
    register_adapter,
)
from app.connectors.http import ProviderCallFailed, send

ACCESSIBLE_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
JIRA_READ_SCOPE = "read:jira-work"
_MAX_SITES = 50


def _site(item: object) -> dict[str, Any] | None:
    """Return ``{"id", "name", "url"}`` for a Jira site entry, or ``None``."""
    if not isinstance(item, dict):
        return None
    scopes = item.get("scopes")
    if not isinstance(scopes, list) or JIRA_READ_SCOPE not in scopes:
        return None
    site_id, name, url = item.get("id"), item.get("name"), item.get("url")
    if not all(isinstance(value, str) and value for value in (site_id, name, url)):
        return None
    if not str(url).startswith("https://"):
        return None
    return {"id": site_id, "name": name, "url": str(url).rstrip("/")}


class AtlassianAdapter(ProviderAdapter):
    """Collects the Jira sites a user granted."""

    def post_connect(
        self,
        client: httpx.Client,
        definition: ConnectorDefinition,
        access_token: str,
    ) -> PostConnectResult:
        response = send(
            client,
            "GET",
            ACCESSIBLE_RESOURCES_URL,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
        )
        if response.status_code >= 400:
            raise ProviderCallFailed("rejected", status=response.status_code)
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderCallFailed("malformed", status=response.status_code) from exc
        if not isinstance(body, list):
            raise ProviderCallFailed("malformed", status=response.status_code)
        sites = [site for item in body if (site := _site(item)) is not None]
        sites = sites[:_MAX_SITES]
        return PostConnectResult(metadata={"sites": sites}, usable=bool(sites))


register_adapter("jira", AtlassianAdapter())
