"""INTEG-02 Wave-0 acceptance: the ``integrations`` tool-permission scopes.

Proves the scope semantics + the per-run ``run_capabilities`` recording:

  * ``integrations`` defaults to NONE — a step with no grant activates ZERO integration
    providers (binds zero integration tools);
  * granting ``gitlab_read`` activates ONLY the gitlab provider, binding only its read
    tools (the catalog read-tool allow-list), NOT github/jira/slack;
  * the effective-perms intersection (08-03) is what gates a scope grant — an
    ``integrations`` scope absent from BOTH the workflow ceiling and the step grant is
    not effective (least-privilege).

The per-run ``run_capabilities`` recording (CAPRUN-01) moved to
``tests/integration/repositories/test_run_capabilities_db.py`` in Batch 6 — it seeds a
parent run row and asserts on persisted columns.
"""

from __future__ import annotations

from agents.capabilities.integration_providers.providers import (
    resolve_integration_scopes,
)
from agents.workflows.plan import ToolPermissions, intersect_permissions


# ---------------------------------------------------------------------------
# INTEG-02 — default none; gitlab_read binds only gitlab read tools
# ---------------------------------------------------------------------------


def test_default_none_binds_zero_integration_tools() -> None:
    """A step with no ``integrations`` grant activates ZERO providers (binds nothing)."""
    configs, exposed = resolve_integration_scopes([])
    assert configs == {}
    assert exposed == {}


def test_gitlab_read_binds_only_gitlab_read_tools() -> None:
    """Granting ``gitlab_read`` activates ONLY gitlab — its read tools, nothing else."""
    configs, exposed = resolve_integration_scopes(["gitlab_read"])

    # Only the gitlab server is activated (not github/jira/slack).
    assert set(configs) == {"gitlab"}
    assert set(exposed) == {"gitlab"}

    # The bound tools are exactly the gitlab catalog read-tool allow-list.
    from agents.capabilities.mcp_servers.catalog import CATALOG

    assert exposed["gitlab"] == set(CATALOG["gitlab"].exposed_tools)
    # The gitlab allow-list is read-only (no write/delete tool leaks in).
    assert exposed["gitlab"] == {
        "list_issues",
        "get_issue",
        "list_merge_requests",
        "get_project",
    }


def test_intersection_gates_an_ungranted_integration_scope() -> None:
    """The 08-03 effective-perms intersection is what gates a scope grant (least-privilege).

    An ``integrations`` scope present on the step grant but ABSENT from the workflow
    ceiling is NOT effective — the intersection drops it, so no provider activates.
    """
    owner = ToolPermissions(integrations=["github_read", "gitlab_read"])
    workflow = ToolPermissions(
        integrations=["gitlab_read"]
    )  # ceiling omits github_read
    step = ToolPermissions(integrations=["github_read", "gitlab_read"])

    effective = intersect_permissions(owner, workflow, step)
    # Only gitlab_read survives all three levels.
    assert effective.integrations == ["gitlab_read"]

    configs, _ = resolve_integration_scopes(effective.integrations)
    assert set(configs) == {"gitlab"}  # github_read was gated out → no github provider


def test_no_grant_means_empty_effective_integrations() -> None:
    """Default-none: an empty step grant ⇒ empty effective ⇒ zero providers."""
    effective = intersect_permissions(
        ToolPermissions(), ToolPermissions(), ToolPermissions()
    )
    assert effective.integrations == []
    configs, exposed = resolve_integration_scopes(effective.integrations)
    assert configs == {} and exposed == {}


# ---------------------------------------------------------------------------
# CAPRUN-01 — run_capabilities records the active scopes + servers + runtime
# ---------------------------------------------------------------------------
