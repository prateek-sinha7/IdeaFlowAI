"""agents/capabilities/integration_providers/ — the integration bridge (09-06 / INTEG-01).

Kernel-side, registration-DATA-only capability package (D-08). Importing it fires the
``@register("integration_provider", "<name>")`` decorators in ``providers`` so
``discover()`` binds the four bridge pairs:

  * ``github`` / ``gitlab`` / ``jira`` / ``slack`` — ``user_allowed=True`` (read-scoped,
    on the user palette; the effective-perms intersection still gates the scope grant).

Each provider is a THIN MCP-backed bridge onto the 09-05 ``mcp_server`` catalog — ONE
mechanism (MCP), NO parallel SDK path (D-08). It maps a granted ``integrations`` scope onto
the matching catalog server's transport config + exposed-tool allow-list, which the engine
run-entry hands to the SAME ``McpClientAdapter`` the MCP prewarm uses, surfacing the tools
into ``create_runner`` via the ``prewarmed_mcp_tools`` seam.

NO ``app.*`` / engine import (the import-linter pins the kernel→ports direction; this package
is data, reached at compile time via the registry trust read and at run-entry via
``resolve_integration_scopes`` which composes the MCP prewarm inputs).
"""

from __future__ import annotations

from . import providers  # noqa: F401 — import for the @register side effect

__all__ = ["providers"]
