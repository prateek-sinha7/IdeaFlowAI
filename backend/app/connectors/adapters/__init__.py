"""Provider adapters: what differs per provider beyond the catalog's data.

``ProviderAdapter`` implements the common behaviour driven by the catalog's
``AccountSpec`` and ``RevokeSpec``: account parsing and an RFC 7009 revoke.
GitHub and Atlassian override only what differs (request headers, grant
revocation, Jira site discovery). A connector whose behaviour matches the
defaults needs no adapter; ``get_adapter`` falls back to the base class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from agents.capabilities.connector_catalog import ConnectorDefinition
from app.connectors.http import ProviderCallFailed, json_object, send
from app.connectors.registry import ClientCredentials

RevocationOutcome = Literal["revoked", "failed"]

_MAX_ACCOUNT_ID = 128
_MAX_TEXT = 255


@dataclass(frozen=True)
class AccountInfo:
    """The provider account behind an access token."""

    account_id: str
    display_name: str | None
    login: str | None
    #: Scopes the provider reports on the account response (GitHub ``X-OAuth-Scopes``).
    scopes: tuple[str, ...] | None = None


@dataclass(frozen=True)
class PostConnectResult:
    """Provider-specific data stored with the connection (for example Jira sites).

    ``usable`` is false when the grant gives nothing to work with (no Jira site),
    in which case nothing is stored.
    """

    metadata: dict[str, Any] | None = None
    usable: bool = True


@dataclass(frozen=True)
class RevokeMaterial:
    """The decrypted tokens a revoke may need. Hidden from ``repr``."""

    access_token: str = field(repr=False)
    refresh_token: str | None = field(default=None, repr=False)


def _text(value: object, limit: int = _MAX_TEXT) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()[:limit]
    return None


def split_scopes(raw: str | None) -> tuple[str, ...]:
    """Split a scope string on commas and whitespace, dropping blanks and duplicates."""
    if not raw:
        return ()
    seen: dict[str, None] = {}
    for part in raw.replace(",", " ").split():
        seen.setdefault(part, None)
    return tuple(seen)


class ProviderAdapter:
    """Default provider behaviour, driven by the catalog definition."""

    #: Whether revoking needs a current access token (GitHub) instead of the refresh token.
    revoke_needs_access_token: bool = False

    def account_headers(self) -> dict[str, str]:
        """Headers for the account lookup request (the bearer is added by the caller)."""
        return {"Accept": "application/json"}

    def parse_account(
        self, definition: ConnectorDefinition, response: httpx.Response
    ) -> AccountInfo:
        """Turn the account response into an ``AccountInfo``.

        Raises:
            ProviderCallFailed: non-2xx status, or a body without a usable account id.
        """
        if response.status_code >= 400:
            raise ProviderCallFailed("rejected", status=response.status_code)
        body = json_object(response)
        spec = definition.account
        raw_id = body.get(spec.id_field)
        if isinstance(raw_id, bool) or not isinstance(raw_id, (str, int)):
            raise ProviderCallFailed("malformed", status=response.status_code)
        account_id = str(raw_id).strip()
        if not account_id or len(account_id) > _MAX_ACCOUNT_ID:
            raise ProviderCallFailed("malformed", status=response.status_code)
        scopes: tuple[str, ...] | None = None
        if spec.scopes_header:
            header = response.headers.get(spec.scopes_header)
            if header is not None:
                scopes = split_scopes(header)
        return AccountInfo(
            account_id=account_id,
            display_name=_text(body.get(spec.name_field)),
            login=_text(body.get(spec.login_field)) if spec.login_field else None,
            scopes=scopes,
        )

    def post_connect(
        self,
        client: httpx.Client,
        definition: ConnectorDefinition,
        access_token: str,
    ) -> PostConnectResult:
        """Collect provider-specific data after the account lookup. Default: none."""
        return PostConnectResult()

    def revoke(
        self,
        client: httpx.Client,
        definition: ConnectorDefinition,
        credentials: ClientCredentials,
        material: RevokeMaterial,
    ) -> RevocationOutcome:
        """Revoke the grant with an RFC 7009 request (refresh token preferred)."""
        token = material.refresh_token or material.access_token
        hint = "refresh_token" if material.refresh_token else "access_token"
        payload = {
            "token": token,
            "token_type_hint": hint,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
        }
        url = definition.revoke.url
        try:
            if definition.oauth.token_request_encoding == "json":
                response = send(client, "POST", url, json=payload)
            else:
                response = send(client, "POST", url, data=payload)
        except ProviderCallFailed:
            return "failed"
        return "revoked" if 200 <= response.status_code < 300 else "failed"


_ADAPTERS: dict[str, ProviderAdapter] = {}


def register_adapter(connector_key: str, adapter: ProviderAdapter) -> None:
    """Register ``adapter`` for ``connector_key`` (called by the adapter modules)."""
    _ADAPTERS[connector_key] = adapter


def get_adapter(connector_key: str) -> ProviderAdapter:
    """Return the adapter for ``connector_key``, or the default behaviour."""
    # Imported here so the adapter modules can import this module's classes.
    from app.connectors.adapters import atlassian, github  # noqa: F401

    return _ADAPTERS.get(connector_key, _DEFAULT_ADAPTER)


_DEFAULT_ADAPTER = ProviderAdapter()
