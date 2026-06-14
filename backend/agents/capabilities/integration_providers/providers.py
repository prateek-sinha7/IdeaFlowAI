"""agents/capabilities/integration_providers/providers.py — the integration bridge (INTEG-01 / D-08).

Four ``@register("integration_provider", "github"|"gitlab"|"jira"|"slack")`` capabilities,
each a THIN MCP-backed bridge: it takes the matching catalog ``mcp_server`` (09-05) + an
``integrations`` scope (``github_read``/``gitlab_read``/``jira_read``/``slack_post``) and
surfaces that server's tools into ``create_runner`` via the SAME factory seam the MCP tools
use — ``AgentContext.prewarmed_mcp_tools`` unioned in ``_resolve_runner_tools`` (the engine
awaits the bind ONCE at run-entry; the sync factory only reads + unions, no double-loop).

ONE mechanism (MCP), NO parallel vendor-SDK path (D-08): there is NO direct vendor client
library import here. The bridge is pure DATA + a config-composition helper — it maps a
GRANTED ``integrations`` scope onto the catalog server's transport config + exposed-tool
allow-list, which the engine run-entry hands to the SAME ``McpClientAdapter`` the 09-05 MCP
prewarm uses. The catalog (``agents/capabilities/mcp_servers/catalog.py``) is the single
source of the transport KIND + the exposed-tool allow-list + the scope string.

Kernel-side, DATA ONLY — NO ``app.*`` / ``agents.execution_engine`` import (the import-linter
pins the kernel→ports direction). The live ``McpClientAdapter`` is app-side; this module only
declares which catalog server a granted scope activates + composes the config fragment.

Scope semantics (INTEG-02): ``integrations`` defaults to NONE — a step that grants no scope
activates ZERO integration providers (binds zero integration tools). Granting ``gitlab_read``
activates ONLY the gitlab provider (whose catalog server exposes the read tools), binding only
those read tools. The effective-perms intersection (08-03 ``intersect_permissions``) is what
gates which scopes are granted; this bridge only translates a GRANTED scope into an MCP config.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.mcp_servers.catalog import CATALOG, _McpServerBase
from agents.capabilities.registry import register


class _IntegrationProviderBase:
    """Shared bridge shape: a granted ``integrations`` scope → its catalog MCP server.

    Subclasses set ``name`` (== the catalog server name) and ``scope`` (the
    ``integrations`` permission string that activates this provider). The bridge
    reaches the catalog server's transport KIND + exposed-tool allow-list via
    ``catalog_entry`` — it holds NO live client and imports NO SDK (D-08).
    """

    name: str = ""
    scope: str = ""

    @property
    def catalog_entry(self) -> _McpServerBase:
        """The matching ``mcp_server`` catalog entry (09-05) this provider bridges.

        The catalog is the single source of the transport KIND + the exposed-tool
        allow-list — the bridge surfaces THAT server's tools, never a parallel
        vendor-client path (D-08).
        """
        return CATALOG[self.name]

    @property
    def exposed_tools(self) -> frozenset[str]:
        """The catalog server's exposed-tool allow-list (the bind-time defence)."""
        return self.catalog_entry.exposed_tools

    def server_config(self, host_config: dict[str, Any]) -> dict[str, Any]:
        """Compose the MCP server-config fragment for the engine run-entry prewarm.

        ``host_config`` is the live transport detail supplied per-run by the host
        (the endpoint/url/command + the scoped credential — the §15 injection seam,
        exactly like the 09-04 RepoSpec / the 09-05 ``mcp_server_configs``). The
        catalog supplies the transport KIND as the default; the host overlays the
        live endpoint/credential. The result drops straight into the SAME
        ``McpClientAdapter`` server-config map the MCP prewarm builds (one mechanism).
        """
        merged: dict[str, Any] = {"transport": self.catalog_entry.transport}
        merged.update(host_config or {})
        return merged


# ---------------------------------------------------------------------------
# The four integration providers — each user_allowed=True (read-scoped, on the
# user palette); the effective-perms intersection still gates the scope grant.
# ---------------------------------------------------------------------------


@register(
    "integration_provider",
    "github",
    user_allowed=True,
    description="GitHub integration provider bridging the github catalog MCP server (github_read).",
)
class GithubIntegrationProvider(_IntegrationProviderBase):
    """GitHub integration — bridges the ``github`` catalog MCP server (github_read)."""

    name = "github"
    scope = "github_read"


@register(
    "integration_provider",
    "gitlab",
    user_allowed=True,
    description="GitLab integration provider bridging the gitlab catalog MCP server (gitlab_read).",
)
class GitlabIntegrationProvider(_IntegrationProviderBase):
    """GitLab integration — bridges the ``gitlab`` catalog MCP server (gitlab_read)."""

    name = "gitlab"
    scope = "gitlab_read"


@register(
    "integration_provider",
    "jira",
    user_allowed=True,
    description="Jira integration provider bridging the jira catalog MCP server (jira_read).",
)
class JiraIntegrationProvider(_IntegrationProviderBase):
    """Jira integration — bridges the ``jira`` catalog MCP server (jira_read)."""

    name = "jira"
    scope = "jira_read"


@register(
    "integration_provider",
    "slack",
    user_allowed=True,
    description="Slack integration provider bridging the slack catalog MCP server (slack_post).",
)
class SlackIntegrationProvider(_IntegrationProviderBase):
    """Slack integration — bridges the ``slack`` catalog MCP server (slack_post)."""

    name = "slack"
    scope = "slack_post"


# A read-only view keyed by scope string — the run-entry bridge consults it to map
# a GRANTED ``integrations`` scope onto its provider (and thence the catalog server).
PROVIDERS: dict[str, _IntegrationProviderBase] = {
    GithubIntegrationProvider.scope: GithubIntegrationProvider(),
    GitlabIntegrationProvider.scope: GitlabIntegrationProvider(),
    JiraIntegrationProvider.scope: JiraIntegrationProvider(),
    SlackIntegrationProvider.scope: SlackIntegrationProvider(),
}

# scope → catalog server name (for run_capabilities recording + the prewarm map keys).
SCOPE_TO_SERVER: dict[str, str] = {scope: p.name for scope, p in PROVIDERS.items()}


def resolve_integration_scopes(
    granted_scopes: list[str],
    host_configs: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, set[str]]]:
    """Map GRANTED ``integrations`` scopes → the MCP prewarm inputs (INTEG-01/02).

    Returns ``(mcp_server_configs, mcp_exposed_tools)`` — the EXACT two inputs the
    engine run-entry MCP prewarm consumes (``ectx.mcp_server_configs`` /
    ``ectx.mcp_exposed_tools``, 09-05). This is the bridge that surfaces an
    integration's tools into ``create_runner`` through the SAME mechanism the MCP
    catalog uses — no parallel path (D-08).

    Default-none semantics (INTEG-02): an empty / unknown ``granted_scopes`` yields
    EMPTY maps → the prewarm binds ZERO integration tools (graceful no-op). Granting
    ``gitlab_read`` yields ONLY the gitlab server-config + its read-tool allow-list,
    so only the gitlab read tools bind. ``host_configs`` supplies the per-run live
    transport/credential keyed by server name (the §15 injection seam); absent it the
    catalog transport KIND is used as a placeholder (the prewarm is then a no-op
    against a server with no live endpoint).

    A granted scope with no registered provider is silently skipped (the
    effective-perms intersection already constrains the grant set; an unknown scope is
    not an integration this kernel knows).
    """
    host_configs = host_configs or {}
    server_configs: dict[str, dict[str, Any]] = {}
    exposed: dict[str, set[str]] = {}
    for scope in granted_scopes or ():
        provider = PROVIDERS.get(scope)
        if provider is None:
            continue
        server_configs[provider.name] = provider.server_config(
            host_configs.get(provider.name, {})
        )
        exposed[provider.name] = set(provider.exposed_tools)
    return server_configs, exposed
