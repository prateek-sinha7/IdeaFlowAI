"""In-process Streamable HTTP MCP server for connector tests.

``FakeGitHubMcpServer`` wraps a ``FastMCP`` server (the installed ``mcp`` package) in
stateless JSON mode and serves it through ``httpx.ASGITransport``: no sockets, the
real MCP client code runs unmodified. It records the ``Authorization`` header of
every request, so tests can assert which bearer reached the server.

Use it as an async context manager; ``client_factory`` has the shape of the MCP
adapter's ``httpx_client_factory`` (and of ``app.connectors.http.mcp_client_factory``).
"""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

MCP_URL = "https://api.githubcopilot.com/mcp/"


class _Recorder(BaseHTTPMiddleware):
    def __init__(
        self,
        app: Any,
        sink: list[dict[str, str]],
        reject: set[str],
        challenge: set[str],
    ) -> None:
        super().__init__(app)
        self._sink = sink
        self._reject = reject
        self._challenge = challenge

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        self._sink.append(
            {k.lower(): v for k, v in request.headers.items()}
            | {"x-method": request.method}
        )
        bearer = request.headers.get("authorization", "").removeprefix("Bearer ")
        if bearer in self._reject:
            return Response(status_code=401)
        if bearer in self._challenge:
            return Response(
                status_code=403,
                headers={
                    "WWW-Authenticate": (
                        'Bearer error="insufficient_scope", scope="read:org"'
                    )
                },
            )
        return await call_next(request)


class FakeGitHubMcpServer:
    """A stub MCP server with a configurable tool list."""

    def __init__(self) -> None:
        self.requests: list[dict[str, str]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.reject_bearers: set[str] = set()
        self.scope_challenge_bearers: set[str] = set()
        self._mcp = FastMCP(
            "fake-github",
            stateless_http=True,
            json_response=True,
            streamable_http_path="/mcp/",
            # In-process transport: the Host header is the real URL's host.
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=False
            ),
        )
        self._app: Starlette | None = None
        self._lifespan: Any = None

    def add_read_tool(self, name: str, description: str = "") -> None:
        """Register a tool annotated ``readOnlyHint=True`` that echoes its arguments."""
        self._add(name, description, ToolAnnotations(readOnlyHint=True))

    def add_write_tool(self, name: str, description: str = "") -> None:
        """Register a tool annotated ``readOnlyHint=False``."""
        self._add(name, description, ToolAnnotations(readOnlyHint=False))

    def add_unannotated_tool(self, name: str, description: str = "") -> None:
        """Register a tool without annotations."""
        self._add(name, description, None)

    def _add(
        self, name: str, description: str, annotations: ToolAnnotations | None
    ) -> None:
        def _tool(query: str = "") -> str:
            self.calls.append((name, {"query": query}))
            return f"{name}:{query}"

        self._mcp.add_tool(
            _tool, name=name, description=description, annotations=annotations
        )

    def add_failing_tool(self, name: str, message: str = "boom") -> None:
        """Register a read-only tool whose call fails (the server answers ``isError``)."""

        def _tool(query: str = "") -> str:
            self.calls.append((name, {"query": query}))
            raise ValueError(message)

        self._mcp.add_tool(
            _tool, name=name, annotations=ToolAnnotations(readOnlyHint=True)
        )

    def bearers(self) -> list[str]:
        """The bearer token of every recorded request that carried one."""
        out = []
        for request in self.requests:
            value = request.get("authorization", "")
            if value.startswith("Bearer "):
                out.append(value.removeprefix("Bearer "))
        return out

    async def __aenter__(self) -> FakeGitHubMcpServer:
        app = self._mcp.streamable_http_app()
        app.add_middleware(
            _Recorder,
            sink=self.requests,
            reject=self.reject_bearers,
            challenge=self.scope_challenge_bearers,
        )
        self._app = app
        self._lifespan = app.router.lifespan_context(app)
        await self._lifespan.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._lifespan.__aexit__(exc_type, exc, tb)

    @property
    def client_factory(
        self,
    ) -> Callable[..., httpx.AsyncClient]:
        """An ``httpx_client_factory`` whose clients talk to this server in-process."""
        assert self._app is not None, "use the server as an async context manager"
        app = self._app

        def _factory(
            headers: dict[str, str] | None = None,
            timeout: httpx.Timeout | None = None,
            auth: httpx.Auth | None = None,
        ) -> httpx.AsyncClient:
            return httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                headers=headers,
                timeout=timeout if timeout is not None else httpx.Timeout(10.0),
                auth=auth,
                follow_redirects=False,
            )

        return _factory
