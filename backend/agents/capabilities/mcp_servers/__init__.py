"""agents/capabilities/mcp_servers/ — the allow-listed MCP server catalog (09-05 / MCP-02).

Kernel-side, registration-DATA-only capability package (D-05). Importing it fires
the ``@register("mcp_server", "<name>")`` decorators in ``catalog`` so
``discover()`` binds the six catalog pairs:

  * ``github`` / ``gitlab`` / ``jira`` / ``slack`` — ``user_allowed=True`` (read-scoped,
    on the user palette);
  * ``filesystem`` / ``postgres`` — ``user_allowed=False`` (powerful/write, OFF the
    user palette — the security gate + secrets permission required, MCP-04).

Each registered class carries the transport shape + the exposed-tool allow-list +
the scope as DATA only — NO ``app.*`` / engine import (the import-linter pins the
kernel→ports direction; this package is data, reached at compile time via the
registry trust read and at bind time via the catalog config the run-entry host
hands to ``McpClientAdapter``).
"""

from __future__ import annotations

from . import catalog  # noqa: F401 — import for the @register side effect

__all__ = ["catalog"]
