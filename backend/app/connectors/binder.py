"""Run-time binding of connector tools: the engine's ``RunToolBinder``.

``ConnectorRunToolBinder`` answers the engine's request at run entry (design 5.1). It
turns the run's granted tool names into tools for the run's verified user.

Per connector named in the grants:

* GitHub (remote MCP) is bound by ``RemoteMcpBinder``. The user's active connection
  gives real tools. Without one, every requested tool is a stub that answers with the
  matching error, because the server's tool schemas need a token.
* Jira (native API) gets its real tools whenever it is configured and a user is
  signed in. Each Jira tool checks the connection at call time, so a missing or
  expired connection is reported by the next call, and a connection made during the
  run works from then on. Jira stubs are used only for a connector that is not
  configured and for anonymous runs.

Each connector bound for a signed-in user writes one ``tools_bound`` audit row. Its
outcome is ``ok``, or ``error`` with the code the binding reported.

The binder never raises. A connector that fails gets stubs for its own tools only, and
a failure outside that leaves the run with no tools. Nothing here reads, logs or
returns a token.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Mapping
from typing import Any

from langchain_core.tools import BaseTool

from agents.capabilities.connector_catalog import ConnectorDefinition
from agents.execution_engine.run_tools import RunToolRequest
from app.connectors.errors import ToolErrorCode
from app.connectors.registry import RegisteredConnector
from app.connectors.tools.base import ToolIdentity, ToolRuntime, make_stub_tool
from app.connectors.tools.jira import build_jira_tools
from app.connectors.tools.names import format_tool_name, parse_tool_name
from app.connectors.tools.remote_mcp import BoundRemoteTools, RemoteMcpBinder

logger = logging.getLogger("app.connectors.binder")


def _group_by_connector(names: Iterable[str]) -> dict[str, set[str]]:
    """Group bound names by connector key. A name that is not a bound name is skipped."""
    grouped: dict[str, set[str]] = {}
    for name in names:
        parsed = parse_tool_name(name)
        if parsed is None:
            logger.warning("connector tool name skipped: not a bound name")
            continue
        grouped.setdefault(parsed[0], set()).add(name)
    return grouped


def _names_the_connector_declares(
    definition: ConnectorDefinition, names: set[str]
) -> set[str]:
    """Return the names this connector can serve.

    A remote MCP connector checks names against the server's own list, so every name
    passes here. A native connector serves only the tools its definition declares.
    """
    if definition.tooling.mode == "remote_mcp":
        return names
    declared = {
        format_tool_name(definition.key, spec.name)
        for spec in definition.tooling.native_tools
    }
    unknown = names - declared
    if unknown:
        logger.warning(
            "connector tools skipped: %d not declared by connector=%s",
            len(unknown),
            definition.key,
        )
    return names & declared


class ConnectorRunToolBinder:
    """Binds the granted connector tools of one run for its verified user."""

    def __init__(self, *, runtime: ToolRuntime, remote: RemoteMcpBinder) -> None:
        self._runtime = runtime
        self._remote = remote

    async def __call__(self, request: RunToolRequest) -> Mapping[str, Any]:
        """Return the tools for ``request.tool_names``, keyed by bound name. Never raises."""
        bound: dict[str, BaseTool] = {}
        try:
            for key, names in sorted(_group_by_connector(request.tool_names).items()):
                bound.update(await self._bind_connector(request, key, names))
        except Exception as exc:  # noqa: BLE001 - binding never breaks a run
            logger.error(
                "connector tool binding failed run=%s error=%s",
                request.run_id,
                type(exc).__name__,
            )
        return bound

    async def _bind_connector(
        self, request: RunToolRequest, key: str, names: set[str]
    ) -> dict[str, BaseTool]:
        entry = self._runtime.registry.get(key)
        if entry is None:
            logger.warning("connector tools skipped: unknown connector=%s", key)
            return {}
        definition = entry.definition
        wanted = _names_the_connector_declares(definition, names)
        if not wanted:
            return {}
        identity = ToolIdentity(
            connector_key=key,
            display_name=definition.display_name,
            user_id=request.user_id,
            run_id=request.run_id,
        )
        try:
            result = await self._bind(entry, identity, wanted)
        except Exception as exc:  # noqa: BLE001 - only this connector falls back to stubs
            logger.error(
                "connector tool binding failed connector=%s error=%s",
                key,
                type(exc).__name__,
            )
            result = BoundRemoteTools(
                tools=self._stubs(
                    identity,
                    definition,
                    wanted,
                    ToolErrorCode.INTERNAL_ERROR,
                    f"{definition.display_name} tools could not be loaded",
                ),
                outcome="error",
                error_code=ToolErrorCode.INTERNAL_ERROR.value,
            )
        await self._audit(identity, result)
        return result.tools

    async def _bind(
        self, entry: RegisteredConnector, identity: ToolIdentity, names: set[str]
    ) -> BoundRemoteTools:
        definition = entry.definition
        if definition.tooling.mode == "remote_mcp":
            return await self._remote.bind(
                definition=definition,
                user_id=identity.user_id,
                run_id=identity.run_id,
                requested=names,
            )
        return await self._bind_native(entry, identity, names)

    async def _bind_native(
        self, entry: RegisteredConnector, identity: ToolIdentity, names: set[str]
    ) -> BoundRemoteTools:
        definition = entry.definition
        if not entry.configured:
            return self._stub_result(
                identity,
                definition,
                names,
                ToolErrorCode.NOT_CONFIGURED,
                f"{definition.display_name} is not configured on this server",
            )
        if identity.user_id is None:
            return self._stub_result(
                identity,
                definition,
                names,
                ToolErrorCode.SIGN_IN_REQUIRED,
                "Connected apps need a signed-in user",
            )
        record = await asyncio.to_thread(
            self._runtime.store.get, identity.user_id, definition.key
        )
        tools: dict[str, BaseTool] = {
            **build_jira_tools(
                runtime=self._runtime,
                definition=definition,
                user_id=identity.user_id,
                run_id=identity.run_id,
                requested=names,
            )
        }
        if record is None:
            return BoundRemoteTools(
                tools=tools,
                outcome="error",
                error_code=ToolErrorCode.CONNECTION_MISSING.value,
            )
        if not record.is_active:
            return BoundRemoteTools(
                tools=tools,
                outcome="error",
                error_code=ToolErrorCode.CONNECTION_EXPIRED.value,
            )
        return BoundRemoteTools(tools=tools, outcome="ok")

    def _stub_result(
        self,
        identity: ToolIdentity,
        definition: ConnectorDefinition,
        names: set[str],
        code: ToolErrorCode,
        message: str,
    ) -> BoundRemoteTools:
        return BoundRemoteTools(
            tools=self._stubs(identity, definition, names, code, message),
            outcome="error",
            error_code=code.value,
        )

    def _stubs(
        self,
        identity: ToolIdentity,
        definition: ConnectorDefinition,
        names: set[str],
        code: ToolErrorCode,
        message: str,
    ) -> dict[str, BaseTool]:
        """One stub per name. Each answers every call with the same fixed error."""
        declared = {
            format_tool_name(definition.key, spec.name): spec
            for spec in definition.tooling.native_tools
        }
        stubs: dict[str, BaseTool] = {}
        for name in sorted(names):
            spec = declared.get(name)
            parsed = parse_tool_name(name)
            source = spec.name if spec is not None else (parsed[1] if parsed else name)
            stubs[name] = make_stub_tool(
                name=name,
                description=f"{definition.display_name} tool {source}. Unavailable: {message}",
                identity=identity,
                audit=self._runtime.audit,
                code=code,
                message=message,
                write_capable=spec.write_capable if spec is not None else True,
                source_name=source,
            )
        return stubs

    async def _audit(self, identity: ToolIdentity, result: BoundRemoteTools) -> None:
        if identity.user_id is None:
            return  # the audit row belongs to a user; an anonymous run has none
        try:
            await self._runtime.audit.record_tools_bound(
                user_id=identity.user_id,
                connector_key=identity.connector_key,
                outcome=result.outcome,
                error_code=result.error_code,
                run_id=identity.run_id,
            )
        except Exception as exc:  # noqa: BLE001 - auditing never fails a run
            logger.warning(
                "tools_bound audit failed connector=%s error=%s",
                identity.connector_key,
                type(exc).__name__,
            )
