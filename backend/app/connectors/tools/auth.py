"""``httpx.Auth`` that signs provider requests with the run user's access token.

Tools open a new MCP session or HTTP client per call, so a header frozen at bind
time would go stale. ``ConnectorAuth`` therefore asks the token provider for the
current token on every request, and after a 401 refreshes once (rejecting the
token version it just used) and retries once. It never loops.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from typing import Protocol

import httpx

from app.connectors.tokens import AccessToken


class AccessTokenSource(Protocol):
    """The slice of ``TokenProvider`` the auth flow needs."""

    async def access_token(
        self,
        user_id: str,
        connector_key: str,
        *,
        force_refresh: bool = False,
        rejected_version: int | None = None,
    ) -> AccessToken:
        """Return a valid access token for the user's connection."""
        ...


class ConnectorAuth(httpx.Auth):
    """Bearer auth for one (user, connector). Raises ``ConnectorError`` when no token can be had."""

    requires_response_body = False

    def __init__(
        self, user_id: str, connector_key: str, tokens: AccessTokenSource
    ) -> None:
        self._user_id = user_id
        self._connector_key = connector_key
        self._tokens = tokens

    def sync_auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        """Not supported: connector calls are asynchronous."""
        raise NotImplementedError("ConnectorAuth supports async clients only")

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        """Sign the request; on a 401 refresh once and retry once."""
        token = await self._tokens.access_token(self._user_id, self._connector_key)
        request.headers["Authorization"] = f"Bearer {token.token}"
        response = yield request
        if response.status_code != 401:
            return
        refreshed = await self._tokens.access_token(
            self._user_id,
            self._connector_key,
            force_refresh=True,
            rejected_version=token.version,
        )
        request.headers["Authorization"] = f"Bearer {refreshed.token}"
        yield request
