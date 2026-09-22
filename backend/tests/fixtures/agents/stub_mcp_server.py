"""In-repo stdio stub MCP server (09-05 / D-06) — the OFFLINE MCP-01/04 proof.

A tiny REAL MCP server on the reference ``mcp`` SDK's ``FastMCP`` over stdio,
exposing two trivial tools (``echo``, ``add``). ``test_mcp_client.py`` launches it
as a subprocess via ``MultiServerMCPClient`` ``{"command": "python3.11", "args":
[<this file>], "transport": "stdio"}`` and exercises the REAL stdio transport +
tool-binding fully offline (no network) — proving the live ``McpClientAdapter``
path without a remote server.

Run directly (``python3.11 stub_mcp_server.py``) it speaks MCP over stdio; it is
never imported by the client test (the client spawns it as a child process).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("stub")


@mcp.tool()
def echo(text: str) -> str:
    """Return the input text unchanged (the trivial round-trip proof)."""
    return text


@mcp.tool()
def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return a + b


if __name__ == "__main__":
    # stdio transport: reads/writes MCP JSON-RPC frames on stdin/stdout.
    mcp.run(transport="stdio")
