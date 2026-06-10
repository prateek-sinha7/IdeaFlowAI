"""agents/capabilities/mcp_servers/catalog.py — the allow-listed MCP server catalog (MCP-02 / D-05).

Each catalog entry is a module-level class registered via
``@register("mcp_server", "<name>", user_allowed=<bool>)`` — the decorator adds the
``("mcp_server", "<name>")`` pair to ``_KNOWN`` (so the compiler can validate a
``server.tool`` reference) and records the ``user_allowed`` trust flag (so a
user/db manifest can only reference the read-scoped servers, MCP-03). The class
carries, as DATA only:

  * ``transport`` — the connection shape (``stdio`` / ``streamable_http`` / ``sse``);
  * ``exposed_tools`` — the per-server exposed-tool allow-list (a manifest may only
    name a ``server.tool`` whose tool is in this set — the MCP-03 compile gate +
    the bind-time defence in ``McpClientAdapter.get_tools(allowed=...)``);
  * ``scope`` — the granted scope (``gitlab_read`` etc.) used by the MCP-04 gating;
  * ``powerful`` — whether the server is write/powerful (filesystem/postgres) → the
    security gate + secrets permission is required to bind it (MCP-04).

Kernel-side, DATA ONLY — NO ``app.*`` / engine import (import-linter). This module
holds NO client; the live ``McpClientAdapter`` (app-side) is handed the transport
config at run entry. ``user_allowed`` is the single trust source the compiler reads.
"""

from __future__ import annotations

from agents.capabilities.registry import register


class _McpServerBase:
    """Shared catalog-entry shape. Subclasses set the data attributes only.

    ``config()`` returns the transport-config map fragment the run-entry host merges
    into the ``McpClientAdapter`` server-config dict. ``command``/``args`` (stdio) or
    ``url`` (http/sse) are supplied per-run by the host (the catalog declares the
    transport KIND + the allow-list, not the live endpoint/credential).
    """

    name: str = ""
    transport: str = "stdio"
    exposed_tools: frozenset[str] = frozenset()
    scope: str | None = None
    powerful: bool = False  # write/powerful → MCP-04 security gate + secrets required

    def is_tool_exposed(self, tool: str) -> bool:
        """True iff ``tool`` is in this server's exposed-tool allow-list (MCP-03)."""
        return tool in self.exposed_tools


# ---------------------------------------------------------------------------
# user_allowed=True — read-scoped, on the user palette
# ---------------------------------------------------------------------------


@register("mcp_server", "github", user_allowed=True)
class GithubMcpServer(_McpServerBase):
    """GitHub MCP server — read-scoped (issues / PRs / repo metadata)."""

    name = "github"
    transport = "streamable_http"
    exposed_tools = frozenset({"list_issues", "get_issue", "list_pull_requests", "get_repository"})
    scope = "github_read"
    powerful = False


@register("mcp_server", "gitlab", user_allowed=True)
class GitlabMcpServer(_McpServerBase):
    """GitLab MCP server — read-scoped."""

    name = "gitlab"
    transport = "streamable_http"
    exposed_tools = frozenset({"list_issues", "get_issue", "list_merge_requests", "get_project"})
    scope = "gitlab_read"
    powerful = False


@register("mcp_server", "jira", user_allowed=True)
class JiraMcpServer(_McpServerBase):
    """Jira MCP server — read-scoped (issues / projects)."""

    name = "jira"
    transport = "streamable_http"
    exposed_tools = frozenset({"search_issues", "get_issue", "list_projects"})
    scope = "jira_read"
    powerful = False


@register("mcp_server", "slack", user_allowed=True)
class SlackMcpServer(_McpServerBase):
    """Slack MCP server — post-scoped (the one write the user palette allows)."""

    name = "slack"
    transport = "streamable_http"
    exposed_tools = frozenset({"post_message", "list_channels"})
    scope = "slack_post"
    powerful = False


# ---------------------------------------------------------------------------
# user_allowed=False — powerful/write, OFF the user palette (MCP-04)
# ---------------------------------------------------------------------------


@register("mcp_server", "filesystem", user_allowed=False)
class FilesystemMcpServer(_McpServerBase):
    """Filesystem MCP server — POWERFUL (read/write disk). security gate + secrets (MCP-04)."""

    name = "filesystem"
    transport = "stdio"
    exposed_tools = frozenset({"read_file", "write_file", "list_directory"})
    scope = "filesystem"
    powerful = True


@register("mcp_server", "postgres", user_allowed=False)
class PostgresMcpServer(_McpServerBase):
    """Postgres MCP server — POWERFUL (arbitrary SQL). security gate + secrets (MCP-04)."""

    name = "postgres"
    transport = "stdio"
    exposed_tools = frozenset({"query", "execute"})
    scope = "postgres"
    powerful = True


# A read-only view the compiler/gating consults: name → entry instance. The
# registry already binds these via @register; this map is a convenience for the
# compile-validation loop (exposed-tool allow-list lookup) + the gating check
# (powerful flag) without re-resolving through the registry per reference.
CATALOG: dict[str, _McpServerBase] = {
    "github": GithubMcpServer(),
    "gitlab": GitlabMcpServer(),
    "jira": JiraMcpServer(),
    "slack": SlackMcpServer(),
    "filesystem": FilesystemMcpServer(),
    "postgres": PostgresMcpServer(),
}
