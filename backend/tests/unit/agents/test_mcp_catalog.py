"""MCP-02 Wave-0 acceptance: the mcp_server catalog trust flags.

* the catalog registers github/gitlab/jira/slack (user_allowed=True) +
  filesystem/postgres (user_allowed=False); the trust flags are read off the
  registry (the single trust source the compiler consults);
* the exposed-tool allow-list gates what a manifest may name.

The scoped-credential half (real rows, encryption at rest, cross-owner denial) moved
to ``tests/integration/repositories/test_mcp_credentials_db.py`` in Batch 6.
"""

from __future__ import annotations

from agents.capabilities.registry import CapabilityRegistry, discover


# ---------------------------------------------------------------------------
# MCP-02 — catalog trust flags
# ---------------------------------------------------------------------------


def test_catalog_user_allowed_flags() -> None:
    discover()
    r = CapabilityRegistry()
    # Read-scoped servers are on the user palette.
    for name in ("github", "gitlab", "jira", "slack"):
        assert r.is_registered("mcp_server", name)
        assert (
            r.is_user_allowed("mcp_server", name) is True
        ), f"{name} should be user_allowed"
    # Powerful/write servers are OFF the user palette.
    for name in ("filesystem", "postgres"):
        assert r.is_registered("mcp_server", name)
        assert (
            r.is_user_allowed("mcp_server", name) is False
        ), f"{name} must NOT be user_allowed"


def test_catalog_exposed_tools_and_powerful_flags() -> None:
    from agents.capabilities.mcp_servers.catalog import CATALOG

    # The read-scoped servers are not powerful; the FS/PG servers are.
    assert CATALOG["gitlab"].powerful is False
    assert CATALOG["filesystem"].powerful is True
    assert CATALOG["postgres"].powerful is True
    # The exposed-tool allow-list gates what a manifest may name.
    assert CATALOG["gitlab"].is_tool_exposed("list_issues") is True
    assert CATALOG["gitlab"].is_tool_exposed("delete_everything") is False


# ---------------------------------------------------------------------------
# MCP-02 — scoped per-owner credential (encrypted, cross-owner denied)
# ---------------------------------------------------------------------------
