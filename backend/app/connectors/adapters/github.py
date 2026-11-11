"""GitHub adapter: API headers and grant revocation.

GitHub revokes the whole OAuth App grant of a user with
``DELETE /applications/{client_id}/grant`` (Basic auth with the client
credentials, the access token in the JSON body). A 404 or 422 with a current
token means the grant is already gone.
"""

from __future__ import annotations

import httpx

from agents.capabilities.connector_catalog import ConnectorDefinition
from app.connectors.adapters import (
    ProviderAdapter,
    RevocationOutcome,
    RevokeMaterial,
    register_adapter,
)
from app.connectors.http import ProviderCallFailed, send
from app.connectors.registry import ClientCredentials

GITHUB_API_VERSION = "2022-11-28"
_GITHUB_ACCEPT = "application/vnd.github+json"


class GitHubAdapter(ProviderAdapter):
    """GitHub-specific request headers and grant revocation."""

    revoke_needs_access_token = True

    def account_headers(self) -> dict[str, str]:
        return {"Accept": _GITHUB_ACCEPT, "X-GitHub-Api-Version": GITHUB_API_VERSION}

    def revoke(
        self,
        client: httpx.Client,
        definition: ConnectorDefinition,
        credentials: ClientCredentials,
        material: RevokeMaterial,
    ) -> RevocationOutcome:
        url = definition.revoke.url.format(client_id=credentials.client_id)
        try:
            response = send(
                client,
                "DELETE",
                url,
                json={"access_token": material.access_token},
                auth=(credentials.client_id, credentials.client_secret),
                headers=self.account_headers(),
            )
        except ProviderCallFailed:
            return "failed"
        if response.status_code in (204, 404, 422):
            return "revoked"
        return "failed"


register_adapter("github", GitHubAdapter())
