"""In-memory GitHub and Atlassian OAuth endpoints for connector tests.

``FakeOAuthProvider`` answers the provider calls the connectors runtime makes
(token endpoints, account lookups, Jira site discovery, revokes) through an
``httpx.MockTransport``. The runtime code runs unmodified; only the network is
replaced. Every request is recorded (secrets are included on purpose: tests assert
that the right value was sent, and these objects never reach a log).

Each route has a queue of responders; the last one repeats. ``respond`` replaces a
route's queue, so a test scripts exactly the answers it needs.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_GRANT_URL = "https://api.github.com/applications/{client_id}/grant"
ATLASSIAN_TOKEN_URL = "https://auth.atlassian.com/oauth/token"
ATLASSIAN_REVOKE_URL = "https://auth.atlassian.com/oauth/revoke"
ATLASSIAN_ME_URL = "https://api.atlassian.com/me"
ATLASSIAN_SITES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"

Responder = Callable[[httpx.Request], httpx.Response]


@dataclass(frozen=True)
class RecordedRequest:
    """One request the fake received."""

    method: str
    url: str
    headers: dict[str, str]
    json_body: dict[str, Any] | None
    form_body: dict[str, str] | None

    @property
    def bearer(self) -> str | None:
        """The bearer token of the ``Authorization`` header, if any."""
        value = self.headers.get("authorization", "")
        return value.removeprefix("Bearer ") if value.startswith("Bearer ") else None


def json_response(
    status: int = 200, body: Any = None, headers: dict[str, str] | None = None
) -> Responder:
    """A responder that always returns ``body`` as JSON."""

    def _respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body, headers=headers, request=request)

    return _respond


def empty_response(status: int) -> Responder:
    """A responder that returns ``status`` with no body."""

    def _respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, request=request)

    return _respond


def text_response(status: int, text: str) -> Responder:
    """A responder that returns a non-JSON body."""

    def _respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=text, request=request)

    return _respond


def timeout_response(request: httpx.Request) -> httpx.Response:
    """A responder that simulates a connect timeout."""
    raise httpx.ConnectTimeout("simulated timeout", request=request)


def slow_response(inner: Responder, seconds: float) -> Responder:
    """Delay ``inner`` by ``seconds`` (a slow provider for concurrency tests)."""

    def _respond(request: httpx.Request) -> httpx.Response:
        time.sleep(seconds)
        return inner(request)

    return _respond


def github_token_body(**overrides: Any) -> dict[str, Any]:
    """A successful GitHub token answer."""
    body: dict[str, Any] = {
        "access_token": "gho_access_initial",
        "token_type": "bearer",
        "scope": "repo",
        "expires_in": 28800,
        "refresh_token": "ghr_refresh_initial",
        "refresh_token_expires_in": 15897600,
    }
    body.update(overrides)
    return body


def atlassian_token_body(**overrides: Any) -> dict[str, Any]:
    """A successful Atlassian token answer."""
    body: dict[str, Any] = {
        "access_token": "atl_access_initial",
        "token_type": "Bearer",
        "scope": "read:jira-work write:jira-work read:me offline_access",
        "expires_in": 3600,
        "refresh_token": "atl_refresh_initial",
    }
    body.update(overrides)
    return body


def jira_site(**overrides: Any) -> dict[str, Any]:
    """One accessible-resources entry."""
    site: dict[str, Any] = {
        "id": "cloud-1",
        "name": "Acme",
        "url": "https://acme.atlassian.net",
        "scopes": ["read:jira-work", "write:jira-work"],
    }
    site.update(overrides)
    return site


class FakeOAuthProvider:
    """GitHub and Atlassian endpoints behind one ``httpx.MockTransport``."""

    def __init__(self, github_client_id: str = "github-client-id") -> None:
        self.requests: list[RecordedRequest] = []
        self.unexpected: list[str] = []
        self._queues: dict[tuple[str, str], list[Responder]] = {}
        self.respond("POST", GITHUB_TOKEN_URL, json_response(200, github_token_body()))
        self.respond(
            "GET",
            GITHUB_USER_URL,
            json_response(
                200,
                {"id": 4242, "login": "octocat", "name": "The Octocat"},
                {"X-OAuth-Scopes": "repo"},
            ),
        )
        self.respond(
            "DELETE",
            GITHUB_GRANT_URL.format(client_id=github_client_id),
            empty_response(204),
        )
        self.respond(
            "POST", ATLASSIAN_TOKEN_URL, json_response(200, atlassian_token_body())
        )
        self.respond(
            "GET",
            ATLASSIAN_ME_URL,
            json_response(200, {"account_id": "acc-1", "name": "Jane Doe"}),
        )
        self.respond("GET", ATLASSIAN_SITES_URL, json_response(200, [jira_site()]))
        self.respond("POST", ATLASSIAN_REVOKE_URL, json_response(200, {}))

    def respond(self, method: str, url: str, *responders: Responder) -> None:
        """Replace the answers of ``method url``; the last responder repeats."""
        self._queues[(method.upper(), url)] = list(responders)

    def http_factory(self) -> httpx.Client:
        """A provider client on the fake transport (the ``HttpClientFactory`` shape)."""
        return httpx.Client(
            transport=httpx.MockTransport(self._handle), follow_redirects=False
        )

    def calls(self, method: str, url: str) -> list[RecordedRequest]:
        """Every recorded request to ``method url`` (query string ignored)."""
        wanted = (method.upper(), url)
        return [
            call
            for call in self.requests
            if (call.method, call.url.split("?", 1)[0]) == wanted
        ]

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(self._record(request))
        route = (request.method.upper(), str(request.url).split("?", 1)[0])
        queue = self._queues.get(route)
        if not queue:
            self.unexpected.append(f"{route[0]} {route[1]}")
            return httpx.Response(404, request=request)
        responder = queue[0] if len(queue) == 1 else queue.pop(0)
        return responder(request)

    @staticmethod
    def _record(request: httpx.Request) -> RecordedRequest:
        content_type = request.headers.get("content-type", "")
        body = request.content.decode("utf-8") if request.content else ""
        json_body: dict[str, Any] | None = None
        form_body: dict[str, str] | None = None
        if body and "json" in content_type:
            parsed = json.loads(body)
            json_body = parsed if isinstance(parsed, dict) else None
        elif body and "x-www-form-urlencoded" in content_type:
            form_body = {k: v[0] for k, v in parse_qs(body).items()}
        return RecordedRequest(
            method=request.method.upper(),
            url=str(request.url),
            headers={k.lower(): v for k, v in request.headers.items()},
            json_body=json_body,
            form_body=form_body,
        )


def query_of(url: str) -> dict[str, str]:
    """The single-valued query parameters of ``url``."""
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
