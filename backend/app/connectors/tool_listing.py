"""The tool list of one connector for ``GET /api/connectors/{key}/tools``.

Native connectors (Jira) list the tools their definition declares, connected or not,
so the Tools tab can show which ones a workflow has switched on. Remote MCP
connectors (GitHub) need an active connection and ask the server, through the
per-user cache.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from agents.capabilities.connector_catalog import ConnectorDefinition
from app.connectors.errors import (
    ConnectorError,
    ConnectorNotConfigured,
    ConnectorNotFound,
    ToolErrorCode,
)
from app.connectors.registry import ConnectorRegistry
from app.connectors.store import ConnectionStore
from app.connectors.tools.names import format_tool_name
from app.connectors.tools.remote_mcp import RemoteMcpLister, clean_text

MAX_LISTED = 500

ListingStatus = Literal["connected", "not_connected", "expired"]


@dataclass(frozen=True)
class ListedConnectorTool:
    """One tool as the API returns it."""

    name: str
    source_name: str
    title: str
    description: str
    write_capable: bool


@dataclass(frozen=True)
class ConnectorToolsView:
    """The result of a tool listing."""

    connector_key: str
    status: ListingStatus
    tools: tuple[ListedConnectorTool, ...]
    listed_at: datetime | None


class ConnectorNotConnected(ConnectorError):
    """A remote MCP connector has no connection for the user."""

    def __init__(self, connector: str) -> None:
        super().__init__(
            ToolErrorCode.CONNECTION_MISSING,
            "not connected",
            connector=connector,
        )


class ConnectorExpired(ConnectorError):
    """A remote MCP connector's connection is marked expired."""

    def __init__(self, connector: str) -> None:
        super().__init__(
            ToolErrorCode.CONNECTION_EXPIRED,
            "connection expired",
            connector=connector,
        )


class ToolListingService:
    """Lists the tools of a connector for a verified user."""

    def __init__(
        self,
        *,
        registry: ConnectorRegistry,
        store: ConnectionStore,
        remote_mcp: RemoteMcpLister,
    ) -> None:
        self._registry = registry
        self._store = store
        self._remote_mcp = remote_mcp

    async def list_tools(self, user_id: str, connector_key: str) -> ConnectorToolsView:
        """Return the tools of ``connector_key`` for ``user_id``.

        Raises:
            ConnectorNotFound: unknown connector.
            ConnectorNotConfigured: the connector is not configured on this server.
            ConnectorNotConnected: remote MCP connector without a connection.
            ConnectorExpired: remote MCP connector whose connection expired.
            ConnectorError: ``provider_unavailable`` and other provider failures.
        """
        entry = self._registry.get(connector_key)
        if entry is None:
            raise ConnectorNotFound(connector_key)
        if not entry.configured:
            raise ConnectorNotConfigured(connector_key)
        definition = entry.definition
        record = await asyncio.to_thread(self._store.get, user_id, connector_key)
        status: ListingStatus
        if record is None:
            status = "not_connected"
        elif record.is_active:
            status = "connected"
        else:
            status = "expired"

        if definition.tooling.mode == "native_api":
            return ConnectorToolsView(
                connector_key=connector_key,
                status=status,
                tools=_native_tools(definition),
                listed_at=None,
            )

        if record is None:
            raise ConnectorNotConnected(connector_key)
        if not record.is_active:
            raise ConnectorExpired(connector_key)
        try:
            listing = await self._remote_mcp.list_tools(
                user_id, connector_key, record.granted_scopes
            )
        except ConnectorError as exc:
            # A token problem found while listing reads as the matching status.
            if exc.code is ToolErrorCode.CONNECTION_MISSING:
                raise ConnectorNotConnected(connector_key) from exc
            if exc.code is ToolErrorCode.CONNECTION_EXPIRED:
                raise ConnectorExpired(connector_key) from exc
            raise
        tools = tuple(
            ListedConnectorTool(
                name=tool.name,
                source_name=tool.source_name,
                title=tool.title,
                description=tool.description,
                write_capable=tool.write_capable,
            )
            for tool in listing.tools[:MAX_LISTED]
        )
        return ConnectorToolsView(
            connector_key=connector_key,
            status="connected",
            tools=tools,
            listed_at=listing.listed_at,
        )


def _native_tools(definition: ConnectorDefinition) -> tuple[ListedConnectorTool, ...]:
    tools = [
        ListedConnectorTool(
            name=format_tool_name(definition.key, spec.name),
            source_name=spec.name,
            title=clean_text(spec.title, 200) or spec.name,
            description=clean_text(spec.description, 2000),
            write_capable=spec.write_capable,
        )
        for spec in definition.tooling.native_tools
    ]
    return tuple(sorted(tools, key=lambda tool: tool.name))
