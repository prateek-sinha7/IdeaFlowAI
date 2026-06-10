"""app-side MCP *client* layer (09-05 / MCP-01).

The backend was an inbound MCP *server* only (``app/api/mcp.py`` — a hand-rolled
JSON-RPC-over-HTTP endpoint, no SDK). This package is the OPPOSITE direction: an
OUTBOUND client (``McpClientAdapter`` over ``langchain-mcp-adapters``'s
``MultiServerMCPClient``) that connects to external MCP servers, lists their
tools, and binds the allowed ones INTO the deepagents tool set — they AUGMENT the
mandated ``deepagents`` runtime, they never replace it (INV-13).

App-side because it reaches the heavy ``langchain_mcp_adapters`` / ``mcp`` libs;
the kernel reaches it only via the prewarmed-tools handle stashed on the
``AgentContext`` (the ``prewarmed_constitution`` pattern), never by importing this
package.
"""

from app.agents.mcp.client import McpClientAdapter

__all__ = ["McpClientAdapter"]
