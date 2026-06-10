"""INTEG-01 Wave-0 acceptance: the integration providers resolve from create_runner.

Proves the github/gitlab/jira/slack ``integration_provider`` capabilities are reachable
from the UNIFIED ``create_runner`` path (not only the handoff pipeline) — each a THIN
MCP-backed bridge onto the 09-05 ``mcp_server`` catalog (ONE mechanism, no parallel SDK
path — D-08):

  * all four register + resolve from the CapabilityRegistry (user_allowed=True);
  * a granted ``integrations`` scope is translated by ``resolve_integration_scopes`` into
    the EXACT MCP prewarm inputs (server-config map + exposed-tool allow-list) the engine
    run-entry hands to ``McpClientAdapter`` — the SAME seam the MCP tools use;
  * the bridged tools surface into ``create_runner`` via ``ctx.prewarmed_mcp_tools`` and
    union into the factory tool set (the github path no longer requires the bypass);
  * NO PyGithub / python-gitlab / slack_sdk import anywhere in the bridge (one mechanism).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agents.capabilities.registry import CapabilityRegistry, discover

_STUB = str(Path(__file__).resolve().parent / "fixtures" / "stub_mcp_server.py")
_PROVIDER_NAMES = ("github", "gitlab", "jira", "slack")


def _text_of(result) -> str:
    if isinstance(result, list):
        return "".join(b.get("text", "") for b in result if isinstance(b, dict))
    return str(result)


# ---------------------------------------------------------------------------
# INTEG-01 — the four providers register + resolve from the unified registry
# ---------------------------------------------------------------------------


def test_all_four_integration_providers_register() -> None:
    discover()
    r = CapabilityRegistry()
    for name in _PROVIDER_NAMES:
        assert r.is_registered("integration_provider", name), f"{name} not registered"
        # On the user palette (read-scoped); the effective-perms intersection still gates.
        assert r.is_user_allowed("integration_provider", name) is True
        # Resolves to a real impl from the unified registry path.
        impl = r.resolve("integration_provider", name)
        assert impl.name == name


def test_provider_bridges_the_matching_catalog_mcp_server() -> None:
    """Each provider surfaces the matching catalog server's tools — no parallel SDK (D-08)."""
    from agents.capabilities.integration_providers.providers import PROVIDERS
    from agents.capabilities.mcp_servers.catalog import CATALOG

    for provider in PROVIDERS.values():
        # The bridge reaches the catalog server (the single source of transport +
        # exposed-tool allow-list), not a hand-rolled SDK client.
        assert provider.catalog_entry is CATALOG[provider.name]
        assert provider.exposed_tools == CATALOG[provider.name].exposed_tools


def test_scope_resolution_default_none_binds_nothing() -> None:
    """INTEG-01/02: no granted scope ⇒ empty MCP prewarm inputs (graceful no-op)."""
    from agents.capabilities.integration_providers.providers import (
        resolve_integration_scopes,
    )

    configs, exposed = resolve_integration_scopes([])
    assert configs == {}
    assert exposed == {}


@pytest.mark.parametrize("provider_name,scope", [
    ("github", "github_read"),
    ("gitlab", "gitlab_read"),
    ("jira", "jira_read"),
    ("slack", "slack_post"),
])
@pytest.mark.asyncio
async def test_integration_resolves_from_create_runner_path(provider_name, scope) -> None:
    """A granted scope surfaces the integration's tools into the unified create_runner seam.

    The bridge composes the MCP server-config from the granted scope; the SAME
    ``McpClientAdapter`` the 09-05 prewarm uses connects to the in-repo stub stdio
    server and binds its tools — the runner GAINS the integration's tools (the github
    path no longer requires the handoff bypass). We point the bridge's host-config at the
    stub server so the bind is exercised fully offline.
    """
    from agents.capabilities.integration_providers.providers import (
        resolve_integration_scopes,
    )
    from agents.factory import AgentContext, _resolve_runner_tools
    from app.agents.mcp.client import McpClientAdapter

    # Host-injected per-run transport/credential keyed by server name (the §15 seam),
    # pointed at the offline stub so the bridge binds real tools.
    host_configs = {
        provider_name: {
            "command": sys.executable,
            "args": [_STUB],
            "transport": "stdio",
        }
    }
    configs, exposed = resolve_integration_scopes([scope], host_configs)
    assert provider_name in configs, "the granted scope must activate its provider"
    assert configs[provider_name]["command"] == sys.executable

    # The SAME MCP prewarm mechanism binds the tools (no parallel SDK path).
    adapter = McpClientAdapter(configs)
    # The stub exposes echo/add; the bridge's exposed-tool allow-list is the catalog's
    # (which the stub does not implement), so prove the unfiltered bind surfaces tools and
    # that those tools drop into the unified factory union path.
    mcp_tools = await adapter.get_tools()
    assert mcp_tools, "the bridge must surface the integration's tools"

    # The runner GAINS the tools via the unified create_runner seam (the prewarm union),
    # NOT a handoff-only pipeline path.
    ctx = AgentContext(user_request="x", prewarmed_mcp_tools=list(mcp_tools))

    class _Spec:
        tools: list = []

    custom_tools, exclude_builtin = _resolve_runner_tools(_Spec(), ctx)
    assert all(t in custom_tools for t in mcp_tools), "integration tools must union in"
    assert exclude_builtin is False  # the agent needs the native surface to call them


def test_no_parallel_sdk_import_in_the_bridge() -> None:
    """One mechanism (MCP) — the bridge package imports no vendor SDK (D-08).

    Scans only the executable IMPORT statements (not prose) of every module in the
    integration_providers package for a parallel vendor-client import — the
    acceptance-grep intent without a false-positive on the design rationale.
    """
    import ast

    import agents.capabilities.integration_providers as integ_pkg

    pkg_root = Path(integ_pkg.__file__).resolve().parent
    banned_modules = {"github", "gitlab", "slack_sdk", "slack", "jira", "PyGithub"}
    for py in pkg_root.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top not in banned_modules, f"{py.name} imports vendor SDK {top!r}"
            elif isinstance(node, ast.ImportFrom):
                top = (node.module or "").split(".")[0]
                assert top not in banned_modules, f"{py.name} imports vendor SDK {top!r}"
