"""INTEG-01 Wave-0 acceptance — the stub-MCP-server (subprocess) half.

Split out of ``tests/unit/agents/test_integration_providers.py``: this test binds
real tools by launching the in-repo stdio stub MCP server
(``tests/fixtures/agents/stub_mcp_server.py``) as a SUBPROCESS via
``McpClientAdapter``. The unit-isolation guard in ``tests/unit/conftest.py``
rejects spawned processes and names this exact remedy — "Move it to
tests/integration/ (suffix _external), or assert against the command it would
have built instead of running it." We keep the real bind (that is the point of
the acceptance test) and move it here.

The registry/scope-resolution assertions that need no subprocess stay in the unit
suite alongside the D-08 no-parallel-SDK import scan.

Offline — the stub server is in-repo, so there is no network egress; but a real
child process IS spawned, so this is not a unit test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# tests/integration/agents/<file>.py → parents[2] == tests/ (same depth as the
# unit location this was split from, so the fixture path is unchanged).
_STUB = str(
    Path(__file__).resolve().parents[2] / "fixtures" / "agents" / "stub_mcp_server.py"
)


@pytest.mark.parametrize(
    "provider_name,scope",
    [
        ("github", "github_read"),
        ("gitlab", "gitlab_read"),
        ("jira", "jira_read"),
        ("slack", "slack_post"),
    ],
)
@pytest.mark.asyncio
async def test_integration_resolves_from_create_runner_path(
    provider_name, scope
) -> None:
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
