"""In-memory Jira Cloud REST API for connector tool tests.

``FakeJiraApi`` answers the calls the Jira tools make through an
``httpx.MockTransport``; the tool code, ``ConnectorAuth`` and the HTTP client run
unmodified. Routes are keyed by method and the path below
``/ex/jira/<cloud id>/rest/api/3``. Each route holds a queue of responders and the
last one repeats. A request to an unscripted route answers 404.

``client_factory`` has the shape of the MCP adapter's ``httpx_client_factory`` (the
shape ``ToolRuntime.async_client_factory`` expects).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

import httpx

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "connectors"
API_PREFIX = "/ex/jira/"

Responder = Callable[[httpx.Request], httpx.Response]


def load_fixture(name: str) -> Any:
    """Load a static provider payload from ``tests/fixtures/connectors``."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@dataclass(frozen=True)
class JiraCall:
    """One request the fake received."""

    method: str
    cloud_id: str
    path: str
    params: dict[str, str]
    body: Any
    bearer: str | None


def reply(
    status: int = 200, body: Any = None, headers: dict[str, str] | None = None
) -> Responder:
    """A responder that answers with ``status`` and a JSON ``body`` (none for ``None``)."""

    def _respond(_request: httpx.Request) -> httpx.Response:
        if body is None:
            return httpx.Response(status, headers=headers)
        return httpx.Response(status, json=body, headers=headers)

    return _respond


class FakeJiraApi:
    """A scriptable Jira REST API."""

    def __init__(self) -> None:
        self.calls: list[JiraCall] = []
        self.reject_bearers: set[str] = set()
        self._routes: dict[tuple[str, str], list[Responder]] = {}

    def respond(
        self, method: str, path: str, *responders: Responder | tuple[int, Any]
    ) -> None:
        """Script the answers for ``method path``; the last repeats.

        A ``(status, body)`` tuple is shorthand for ``reply(status, body)``.
        """
        queue = [r if callable(r) else reply(*r) for r in responders]
        self._routes[(method.upper(), path)] = queue

    def calls_to(self, method: str, path: str) -> list[JiraCall]:
        """The recorded calls to ``method path``."""
        return [c for c in self.calls if c.method == method.upper() and c.path == path]

    def bearers(self) -> list[str]:
        """The bearer token of every recorded request that carried one."""
        return [c.bearer for c in self.calls if c.bearer]

    def _handle(self, request: httpx.Request) -> httpx.Response:
        raw_path = request.url.path
        assert raw_path.startswith(API_PREFIX), raw_path
        cloud_id, _, rest = raw_path.removeprefix(API_PREFIX).partition("/rest/api/3")
        auth = request.headers.get("authorization", "")
        bearer = auth.removeprefix("Bearer ") if auth.startswith("Bearer ") else None
        body: Any = None
        if request.content:
            body = json.loads(request.content)
        self.calls.append(
            JiraCall(
                method=request.method,
                cloud_id=cloud_id,
                path=rest,
                params=dict(parse_qsl(request.url.query.decode())),
                body=body,
                bearer=bearer,
            )
        )
        if bearer in self.reject_bearers:
            return httpx.Response(401, json={"message": "Unauthorized"})
        queue = self._routes.get((request.method, rest))
        if not queue:
            return httpx.Response(404, json={"errorMessages": ["not scripted"]})
        responder = queue[0] if len(queue) == 1 else queue.pop(0)
        return responder(request)

    @property
    def client_factory(self) -> Callable[..., httpx.AsyncClient]:
        """An ``httpx_client_factory`` whose clients talk to this fake."""

        def _factory(
            headers: dict[str, str] | None = None,
            timeout: httpx.Timeout | None = None,
            auth: httpx.Auth | None = None,
        ) -> httpx.AsyncClient:
            return httpx.AsyncClient(
                transport=httpx.MockTransport(self._handle),
                headers=headers,
                timeout=timeout if timeout is not None else httpx.Timeout(10.0),
                auth=auth,
                follow_redirects=False,
            )

        return _factory
