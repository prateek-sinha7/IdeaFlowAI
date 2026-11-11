"""Remote MCP connectors (GitHub): the connection, the tool list and run binding.

This module builds the Streamable HTTP connection for one verified user, lists the
tools the server offers (filtered by the definition's allow and deny rules, cached
per connector, user and scope fingerprint) and binds the requested ones to a run
as namespaced ``github__<tool>`` tools. A tool that cannot be real at bind time
(no connection, expired, not configured, not listed) becomes a stub that answers
every call with the matching error envelope, so a run never fails at bind.

Nothing here logs a token, a header value or a provider response body.
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import re
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, cast

import httpx
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import Connection, McpHttpClientFactory
from langchain_mcp_adapters.tools import convert_mcp_tool_to_langchain_tool

from agents.capabilities.connector_catalog import ConnectorDefinition
from app.connectors.errors import (
    ConnectorError,
    ConnectorNotConfigured,
    ConnectorNotFound,
    ToolErrorCode,
)
from app.connectors.http import mcp_client_factory
from app.connectors.registry import ConnectorRegistry
from app.connectors.store import ConnectionRecord, utcnow
from app.connectors.tools.auth import AccessTokenSource, ConnectorAuth
from app.connectors.tools.base import (
    PERMISSIVE_SCHEMA,
    ToolIdentity,
    ToolRuntime,
    make_connector_tool,
    make_stub_tool,
)
from app.connectors.tools.names import format_tool_name, parse_tool_name
from app.connectors.tools.schema_cache import (
    CacheKey,
    ListedTool,
    ToolListing,
    ToolSchemaCache,
    scope_fingerprint,
)

logger = logging.getLogger("app.connectors.tools.remote_mcp")

#: Upper bounds on one listing (a runaway server cannot grow it without limit).
MAX_PAGES = 20
MAX_LISTED_TOOLS = 500
MAX_DESCRIPTION_LENGTH = 2000
MAX_TITLE_LENGTH = 200

#: Upper bound on one remote MCP tool call. The streamable-HTTP connection allows 30 s to
#: open and initialize, and 120 s for the response read window (``sse_read_timeout``
#: above). A call still running after 150 s is reported as ``provider_unavailable``.
REMOTE_TOOL_CALL_TIMEOUT_SECONDS = 150.0

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: object, limit: int) -> str:
    """Return ``value`` as text without control characters, cut to ``limit`` characters."""
    if not isinstance(value, str):
        return ""
    return _CONTROL_CHARS.sub("", value).strip()[:limit]


def build_connection(
    definition: ConnectorDefinition,
    user_id: str,
    tokens: AccessTokenSource,
    *,
    httpx_client_factory: McpHttpClientFactory = mcp_client_factory,
    extra_headers: dict[str, str] | None = None,
) -> Connection:
    """Return the Streamable HTTP connection of ``definition`` for ``user_id``.

    The bearer token is not in the connection: ``ConnectorAuth`` reads it from the
    token provider on every request.
    """
    tooling = definition.tooling
    if tooling.mode != "remote_mcp" or tooling.mcp_url is None:
        raise ValueError(f"{definition.key} is not a remote MCP connector")
    headers = {**dict(tooling.mcp_headers), **(extra_headers or {})}
    connection: dict[str, Any] = {
        "transport": "streamable_http",
        "url": tooling.mcp_url,
        "headers": headers,
        "timeout": timedelta(seconds=30),
        "sse_read_timeout": timedelta(seconds=120),
        "terminate_on_close": True,
        "auth": ConnectorAuth(user_id, definition.key, tokens),
        "httpx_client_factory": httpx_client_factory,
    }
    return cast(Connection, connection)


def is_write_capable(definition: ConnectorDefinition, tool: Any) -> bool:
    """Whether ``tool`` can change data: no ``readOnlyHint`` counts as a write."""
    annotations = getattr(tool, "annotations", None)
    read_only = getattr(annotations, "readOnlyHint", None) is True
    return (not read_only) or tool.name in definition.tooling.write_tools


def _allowed(definition: ConnectorDefinition, source_name: str) -> bool:
    tooling = definition.tooling
    if not any(fnmatch.fnmatchcase(source_name, p) for p in tooling.tool_allow):
        return False
    return not any(fnmatch.fnmatchcase(source_name, p) for p in tooling.tool_deny)


def _flatten(exc: BaseException) -> list[BaseException]:
    """Return the leaf exceptions of ``exc`` (anyio wraps errors in exception groups)."""
    if isinstance(exc, BaseExceptionGroup):
        leaves: list[BaseException] = []
        for inner in exc.exceptions:
            leaves.extend(_flatten(inner))
        return leaves
    return [exc]


class RemoteMcpLister:
    """Lists and caches the tools of remote MCP connectors."""

    def __init__(
        self,
        *,
        registry: ConnectorRegistry,
        tokens: AccessTokenSource,
        cache: ToolSchemaCache,
        httpx_client_factory: McpHttpClientFactory = mcp_client_factory,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._registry = registry
        self._tokens = tokens
        self._cache = cache
        self._httpx_client_factory = httpx_client_factory
        self._clock = clock

    async def list_tools(
        self, user_id: str, connector_key: str, granted_scopes: tuple[str, ...]
    ) -> ToolListing:
        """Return the user's tool list for ``connector_key`` (cached).

        Raises:
            ConnectorNotFound: unknown connector.
            ConnectorNotConfigured: the connector is not configured on this server.
            ConnectorError: ``connection_missing`` / ``connection_expired`` from the
                token provider, or ``provider_unavailable`` for any other failure.
        """
        entry = self._registry.get(connector_key)
        if entry is None:
            raise ConnectorNotFound(connector_key)
        if not entry.configured:
            raise ConnectorNotConfigured(connector_key)
        definition = entry.definition
        key = CacheKey(connector_key, user_id, scope_fingerprint(granted_scopes))
        return await self._cache.get_or_load(
            key, lambda: self._fetch(definition, user_id)
        )

    async def _fetch(
        self, definition: ConnectorDefinition, user_id: str
    ) -> ToolListing:
        connection = build_connection(
            definition,
            user_id,
            self._tokens,
            httpx_client_factory=self._httpx_client_factory,
        )
        client = MultiServerMCPClient({definition.key: connection})
        try:
            async with client.session(definition.key) as session:
                raw_tools = await self._collect(session)
        except Exception as exc:
            raise self._to_connector_error(exc, definition) from exc
        tools = self._shape(definition, raw_tools)
        return ToolListing(tools=tools, listed_at=self._clock())

    @staticmethod
    async def _collect(session: Any) -> list[Any]:
        collected: list[Any] = []
        cursor: str | None = None
        for _ in range(MAX_PAGES):
            page = await session.list_tools(cursor)
            collected.extend(page.tools)
            cursor = page.nextCursor
            if not cursor or len(collected) >= MAX_LISTED_TOOLS:
                break
        return collected[:MAX_LISTED_TOOLS]

    @staticmethod
    def _shape(
        definition: ConnectorDefinition, raw_tools: list[Any]
    ) -> tuple[ListedTool, ...]:
        shaped: dict[str, ListedTool] = {}
        for tool in raw_tools:
            source_name = tool.name
            if not isinstance(source_name, str) or not _allowed(
                definition, source_name
            ):
                continue
            try:
                bound = format_tool_name(definition.key, source_name)
            except ValueError:
                logger.warning(
                    "connector tool dropped, its bound name breaks the naming rule "
                    "connector=%s name=%r",
                    definition.key,
                    source_name[:80],
                )
                continue
            annotations = getattr(tool, "annotations", None)
            title = (
                clean_text(getattr(tool, "title", None), MAX_TITLE_LENGTH)
                or clean_text(getattr(annotations, "title", None), MAX_TITLE_LENGTH)
                or source_name
            )
            shaped[bound] = ListedTool(
                source_name=source_name,
                name=bound,
                title=title,
                description=clean_text(
                    getattr(tool, "description", None), MAX_DESCRIPTION_LENGTH
                ),
                write_capable=is_write_capable(definition, tool),
                definition=tool,
            )
        return tuple(shaped[name] for name in sorted(shaped))

    @staticmethod
    def _to_connector_error(
        exc: Exception, definition: ConnectorDefinition
    ) -> ConnectorError:
        leaves = _flatten(exc)
        for leaf in leaves:
            if isinstance(leaf, ConnectorError):
                return leaf
        for leaf in leaves:
            # The server still refused the token after the one refresh and retry.
            if (
                isinstance(leaf, httpx.HTTPStatusError)
                and leaf.response.status_code == 401
            ):
                return ConnectorError(
                    ToolErrorCode.CONNECTION_EXPIRED,
                    f"{definition.display_name} connection expired, "
                    "reconnect in Connectors",
                    connector=definition.key,
                )
        logger.warning(
            "tool listing failed connector=%s error=%s",
            definition.key,
            ",".join(sorted({type(leaf).__name__ for leaf in leaves})),
        )
        return ConnectorError(
            ToolErrorCode.PROVIDER_UNAVAILABLE,
            f"{definition.display_name} is temporarily unavailable",
            connector=definition.key,
        )


# ---- binding a run ----------------------------------------------------------

NON_TEXT_NOTICE = "[non-text content omitted]"


def join_content(content: object) -> str:
    """Flatten an MCP tool result to text: text blocks joined, other blocks noted."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return NON_TEXT_NOTICE
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            parts.append(text if isinstance(text, str) else "")
        else:
            parts.append(NON_TEXT_NOTICE)
    return "\n".join(parts)


@dataclass(frozen=True)
class BoundRemoteTools:
    """The tools bound for one connector and run, and how binding went.

    ``outcome`` is ``ok`` when the tools are real and ``error`` when they are stubs
    (``error_code`` names why). A real tool list with some unlisted names is ``ok``;
    only those names are stubs.
    """

    tools: dict[str, BaseTool]
    outcome: Literal["ok", "error"]
    error_code: str | None = None


class RemoteMcpBinder:
    """Binds the requested tools of a remote MCP connector to one run and user."""

    def __init__(
        self,
        *,
        runtime: ToolRuntime,
        lister: RemoteMcpLister,
        httpx_client_factory: McpHttpClientFactory = mcp_client_factory,
    ) -> None:
        self._runtime = runtime
        self._lister = lister
        self._httpx_client_factory = httpx_client_factory

    async def bind(
        self,
        *,
        definition: ConnectorDefinition,
        user_id: str | None,
        run_id: str | None,
        requested: Collection[str],
    ) -> BoundRemoteTools:
        """Return one tool per requested ``<key>__<tool>`` name. Never raises."""
        sources = _requested_sources(definition.key, requested)
        if not sources:
            return BoundRemoteTools(tools={}, outcome="ok")
        identity = ToolIdentity(
            connector_key=definition.key,
            display_name=definition.display_name,
            user_id=user_id,
            run_id=run_id,
        )
        try:
            failure, record = await self._precheck(definition, identity)
            if failure is not None or record is None or user_id is None:
                code, message = failure or (
                    ToolErrorCode.CONNECTION_MISSING,
                    f"{definition.display_name} connection missing, reconnect in Connectors",
                )
                return self._stubs(identity, sources, code, message)
            listing = await self._lister.list_tools(
                user_id, definition.key, record.granted_scopes
            )
        except ConnectorError as exc:
            return self._stubs(identity, sources, exc.code, str(exc))
        except Exception as exc:  # noqa: BLE001 - binding never breaks a run
            logger.error(
                "remote tool binding failed connector=%s error=%s",
                definition.key,
                type(exc).__name__,
            )
            return self._stubs(
                identity,
                sources,
                ToolErrorCode.INTERNAL_ERROR,
                f"{definition.display_name} tools could not be loaded",
            )
        return self._bind_listed(definition, identity, sources, listing)

    async def _precheck(
        self, definition: ConnectorDefinition, identity: ToolIdentity
    ) -> tuple[tuple[ToolErrorCode, str] | None, ConnectionRecord | None]:
        """Return ``(failure, record)``: the stub code and message when binding cannot
        reach the server, else the user's active connection."""
        name = definition.display_name
        entry = self._runtime.registry.get(definition.key)
        if entry is None or not entry.configured:
            return (
                ToolErrorCode.NOT_CONFIGURED,
                f"{name} is not configured on this server",
            ), None
        if identity.user_id is None:
            return (
                ToolErrorCode.SIGN_IN_REQUIRED,
                "Connected apps need a signed-in user",
            ), None
        record = await asyncio.to_thread(
            self._runtime.store.get, identity.user_id, definition.key
        )
        if record is None:
            return (
                ToolErrorCode.CONNECTION_MISSING,
                f"{name} connection missing, reconnect in Connectors",
            ), None
        if not record.is_active:
            return (
                ToolErrorCode.CONNECTION_EXPIRED,
                f"{name} connection expired, reconnect in Connectors",
            ), None
        return None, record

    def _bind_listed(
        self,
        definition: ConnectorDefinition,
        identity: ToolIdentity,
        sources: dict[str, str],
        listing: ToolListing,
    ) -> BoundRemoteTools:
        by_source = {tool.source_name: tool for tool in listing.tools}
        found = {
            name: by_source[src] for name, src in sources.items() if src in by_source
        }
        header = definition.tooling.selected_tools_header
        extra = (
            {header: ",".join(sorted(tool.source_name for tool in found.values()))}
            if header and found
            else None
        )
        assert identity.user_id is not None
        connection = build_connection(
            definition,
            identity.user_id,
            self._runtime.tokens,
            httpx_client_factory=self._httpx_client_factory,
            extra_headers=extra,
        )
        tools: dict[str, BaseTool] = {}
        for name, source in sources.items():
            listed = found.get(name)
            if listed is None:
                tools[name] = self._stub(
                    identity,
                    name,
                    source,
                    ToolErrorCode.TOOL_UNAVAILABLE,
                    f"{definition.display_name} tool {source} is not available for this account",
                    write=True,
                )
                continue
            tools[name] = self._real_tool(definition, identity, connection, listed)
        return BoundRemoteTools(tools=tools, outcome="ok")

    def _real_tool(
        self,
        definition: ConnectorDefinition,
        identity: ToolIdentity,
        connection: Connection,
        listed: ListedTool,
    ) -> BaseTool:
        inner = convert_mcp_tool_to_langchain_tool(
            None, listed.definition, connection=connection, server_name=definition.key
        )
        coroutine = inner.coroutine  # type: ignore[attr-defined]
        schema = getattr(listed.definition, "inputSchema", None)
        schema = schema if isinstance(schema, dict) else dict(PERMISSIVE_SCHEMA)
        declared = schema.get("properties")
        accepts_runtime = isinstance(declared, dict) and "runtime" in declared

        async def _body(arguments: dict[str, Any]) -> str:
            args = dict(arguments)
            if not accepts_runtime:
                args.pop("runtime", None)  # the adapter's own injected argument
            try:
                content, _artifact = await asyncio.wait_for(
                    coroutine(**args), timeout=REMOTE_TOOL_CALL_TIMEOUT_SECONDS
                )
            except TimeoutError as exc:
                raise ConnectorError(
                    ToolErrorCode.PROVIDER_UNAVAILABLE,
                    f"{definition.display_name} did not answer in time; try again",
                    connector=definition.key,
                ) from exc
            return join_content(content)

        return make_connector_tool(
            name=listed.name,
            description=listed.description,
            args_schema=schema,
            identity=identity,
            body=_body,
            audit=self._runtime.audit,
            write_capable=listed.write_capable,
            source_name=listed.source_name,
        )

    def _stubs(
        self,
        identity: ToolIdentity,
        sources: dict[str, str],
        code: ToolErrorCode,
        message: str,
    ) -> BoundRemoteTools:
        tools = {
            name: self._stub(identity, name, source, code, message, write=True)
            for name, source in sources.items()
        }
        return BoundRemoteTools(tools=tools, outcome="error", error_code=code.value)

    def _stub(
        self,
        identity: ToolIdentity,
        name: str,
        source: str,
        code: ToolErrorCode,
        message: str,
        *,
        write: bool,
    ) -> BaseTool:
        return make_stub_tool(
            name=name,
            description=f"{identity.display_name} tool {source}. Unavailable: {message}",
            identity=identity,
            audit=self._runtime.audit,
            code=code,
            message=message,
            write_capable=write,
            source_name=source,
        )


def _requested_sources(
    connector_key: str, requested: Collection[str]
) -> dict[str, str]:
    """Map each valid requested bound name of ``connector_key`` to its source name."""
    sources: dict[str, str] = {}
    for name in sorted(requested):
        parsed = parse_tool_name(name)
        if parsed is not None and parsed[0] == connector_key:
            sources[name] = parsed[1]
    return sources
