"""McpClientAdapter — the app-side OUTBOUND MCP client (09-05 / MCP-01).

Wraps ``langchain_mcp_adapters.client.MultiServerMCPClient``: constructs from a
catalog server-config map (the stdio/SSE/HTTP shape the catalog carries as data),
``await get_tools()`` to obtain LangChain-compatible tools, and (optionally)
filters them down to a per-server exposed-tool allow-list before they are bound
into the deepagents tool set.

**The async→sync binding mechanism (RESEARCH R-D, RESOLVED).** ``get_tools()`` is
async; the factory (``create_runner``/``_resolve_runner_tools``) is SYNC and runs
under the engine's already-running event loop. We therefore mirror the proven
``prewarmed_constitution`` pattern: the engine awaits ``bind_tools_for_scopes`` /
``get_tools`` ONCE at the async run-entry, stashes the bound tool list on
``AgentContext.prewarmed_mcp_tools``, and the sync factory only READS that list and
UNIONS it into ``custom_tools`` — never ``await``/``asyncio.run`` inside the running
loop (the double-loop hazard, Pitfall 3).

**INV-13.** The returned tools are LangChain ``BaseTool``s — they drop straight
into the sanctioned deepagents adapter's tool set; they AUGMENT the deepagents
runtime, never replace it. This module performs no agent-loop construction and
never builds a deep-agent graph itself (that stays in the allow-listed
``app/agents/deep_agent_runner.py``).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class McpClientAdapter:
    """Adapter over ``MultiServerMCPClient`` (app-side, async ``get_tools``).

    Construct from a ``{server_name: server_config}`` map where each config is the
    transport shape the catalog carries as data, e.g. the stdio shape::

        {"github": {"command": "python3.11", "args": ["server.py"], "transport": "stdio"}}

    The adapter is otherwise a thin pass-through: the underlying client is stateless
    by default (each tool invocation opens/cleans up its own ``ClientSession``), so
    there is no long-lived connection to thread through the sync factory path.
    """

    def __init__(self, server_configs: dict[str, dict[str, Any]]) -> None:
        # Defer the heavy import to construction (keeps a bare ``import client``
        # cheap and lets discover()/import-linter reason about the boundary).
        from langchain_mcp_adapters.client import MultiServerMCPClient

        self._server_configs = dict(server_configs)
        self._client = MultiServerMCPClient(self._server_configs)

    @property
    def server_names(self) -> list[str]:
        """The configured server names (declaration order)."""
        return list(self._server_configs.keys())

    async def get_tools(self, *, allowed: dict[str, set[str]] | None = None) -> list:
        """Connect, list tools, and return LangChain-compatible tools.

        ``allowed`` (optional) is a per-server exposed-tool allow-list
        ``{server_name: {tool_name, ...}}``. When supplied, only tools whose
        ``name`` is in that server's allow-list survive — the binding-seam
        enforcement that a manifest can only surface the catalog-declared tools
        (the compile-validation MCP-03 is the first gate; this is the defence in
        depth at bind time). When ``None`` every connected tool is returned.

        Async (``await``) — call ONCE at the engine run-entry and stash the result
        on ``AgentContext.prewarmed_mcp_tools`` (the ``prewarmed_constitution``
        pattern). NEVER call from the sync factory under the running loop.
        """
        tools = await self._client.get_tools()
        if allowed is None:
            return list(tools)

        # Match on the BARE MCP tool name robustly: langchain-mcp-adapters tool
        # naming is version-dependent (bare name today; some versions/adapters
        # emit a server-prefixed alias such as ``server.tool``, ``server__tool``,
        # ``server-tool`` or ``server:tool``). Strip a known server prefix before
        # comparing so an alternate adapter version cannot silently drop every
        # tool (WR-05).
        permitted_bare: set[str] = set()
        for names in allowed.values():
            permitted_bare.update(names)
        _PREFIX_SEPS = ("__", ".", "-", ":")

        def _is_permitted(tool_name: str | None) -> bool:
            if not tool_name:
                return False
            if tool_name in permitted_bare:
                return True
            for server, names in allowed.items():
                for sep in _PREFIX_SEPS:
                    prefix = f"{server}{sep}"
                    if tool_name.startswith(prefix) and tool_name[len(prefix):] in names:
                        return True
            return False

        bound = [t for t in tools if _is_permitted(getattr(t, "name", None))]
        dropped = len(tools) - len(bound)
        if tools and not bound:
            # A TOTAL over-drop is indistinguishable from "no scope active" at
            # INFO — surface it loudly so a naming-scheme drift in the adapter
            # (every connected tool filtered out) is visible (WR-05).
            logger.warning(
                "McpClientAdapter.get_tools: allow-list filtered out ALL %d "
                "connected tool(s) (allowed=%s, connected=%s) — the run proceeds "
                "with ZERO MCP tools; check for an adapter tool-naming mismatch",
                len(tools),
                {s: sorted(n) for s, n in allowed.items()},
                sorted(getattr(t, "name", "?") for t in tools),
            )
        elif dropped:
            logger.info(
                "McpClientAdapter.get_tools: filtered %d tool(s) not in the "
                "exposed-tool allow-list (kept %d)",
                dropped,
                len(bound),
            )
        return bound
