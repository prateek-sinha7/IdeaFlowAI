"""Outbound HTTP for provider calls (token endpoints, account lookups, revokes).

Every client verifies TLS against ``default_ssl_context()``, never follows
redirects (a provider endpoint that redirects is treated as a failure instead of
forwarding credentials elsewhere) and identifies itself with one fixed
``User-Agent``. Tests inject a factory built on ``httpx.MockTransport``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Literal

import httpx

from app.core.http_client import default_ssl_context

USER_AGENT = "flowin-connectors"

#: Builds a synchronous client for one operation; the caller closes it.
HttpClientFactory = Callable[[], httpx.Client]

FailureKind = Literal["unavailable", "rejected", "client", "malformed"]

_ERROR_CODE_RE = re.compile(r"^[a-z_]{1,64}$")


class ProviderCallFailed(Exception):
    """A provider call failed. Carries a kind and a sanitized code, never a response body.

    ``unavailable``: timeout, network error, 5xx or 429 (worth retrying).
    ``rejected``: the provider refused the request (bad code, bad refresh token).
    ``client``: the provider refused our client credentials (operator problem).
    ``malformed``: the provider answered with something unusable.
    """

    def __init__(
        self,
        kind: FailureKind,
        error_code: str | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(
            f"provider call failed kind={kind} code={error_code} status={status}"
        )
        self.kind = kind
        self.error_code = error_code
        self.status = status


def safe_error_code(value: object) -> str | None:
    """Return ``value`` when it is a plain OAuth error code, else ``None``.

    Provider error strings are untrusted; only ``[a-z_]{1,64}`` ever reaches a
    log line, an audit row or a column.
    """
    if isinstance(value, str) and _ERROR_CODE_RE.match(value):
        return value
    return None


def send(client: httpx.Client, method: str, url: str, **kwargs: Any) -> httpx.Response:
    """Send one request; a transport failure, 5xx or 429 raises ``ProviderCallFailed("unavailable")``."""
    try:
        response = client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise ProviderCallFailed("unavailable", type(exc).__name__) from exc
    if response.status_code >= 500 or response.status_code == 429:
        raise ProviderCallFailed("unavailable", status=response.status_code)
    return response


def json_object(response: httpx.Response) -> dict[str, Any]:
    """Return the JSON object in ``response`` or raise ``ProviderCallFailed("malformed")``."""
    try:
        body = response.json()
    except ValueError as exc:
        raise ProviderCallFailed("malformed", status=response.status_code) from exc
    if not isinstance(body, dict):
        raise ProviderCallFailed("malformed", status=response.status_code)
    return body


def mcp_client_factory(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """Build the ``httpx.AsyncClient`` an MCP connection uses (the adapter's factory shape).

    Same TLS and redirect policy as the provider clients above: verification against
    ``default_ssl_context()``, no redirects. The adapter's own default follows
    redirects, which would forward the bearer token to another host.
    """
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, **(headers or {})},
        timeout=timeout if timeout is not None else httpx.Timeout(30.0),
        auth=auth,
        verify=default_ssl_context(),
        follow_redirects=False,
    )


def default_http_client_factory(timeout_seconds: float) -> HttpClientFactory:
    """Return a factory of provider clients with the given per-request timeout."""

    def _factory() -> httpx.Client:
        return httpx.Client(
            timeout=timeout_seconds,
            verify=default_ssl_context(),
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        )

    return _factory
