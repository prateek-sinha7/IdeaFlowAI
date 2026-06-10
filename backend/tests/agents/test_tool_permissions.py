"""tests/agents/test_tool_permissions.py — least-privilege ToolPermissions (08-03 / D-07).

Proves TOOLPERM-01/02/03 (INV-9): effective tool permissions are the
``intersection(owner_allow_list, workflow_ceiling, step_grant)`` — a permission is
ON only if granted at ALL THREE levels — and an ``AGENT.md`` default may only LOWER
a permission, never raise one its step did not grant. Also proves the §8 defaults
(``read_files`` ON; ``write_files``/``git``/``spawn_subagents``/``exec``/``network``
OFF; ``secrets``/``mcp``/``integrations`` none).

The runtime exec/network/secrets default-deny enforcement point is the single live
surface ``LocalExecutionPolicy.allows`` (``app/agents/runtime/local.py``, exercised by
``tests/agents/test_local_runtime.py``); the former ``plan.py:ExecutionPolicy``
forward-surface helper was deleted in 10-02 (INV-12 dual-surface resolution).

These are pure-data tests: ``ToolPermissions``/``intersect_permissions`` are
stdlib-only dataclasses + functions (no registry side effect, no kernel/app import).
"""

from __future__ import annotations

from agents.workflows.plan import (
    ToolPermissions,
    intersect_permissions,
)


# ---------------------------------------------------------------------------
# Defaults — the §8 least-privilege posture.
# ---------------------------------------------------------------------------


def test_defaults_are_least_privilege() -> None:
    """An ungranted step's defaults: read_files ON, everything else OFF/none."""
    perms = ToolPermissions()
    assert perms.read_files is True
    assert perms.write_files is False
    assert perms.git is False
    assert perms.spawn_subagents is False
    assert perms.exec is False
    assert perms.network is False
    # none-valued slots default empty (secrets/mcp/integrations).
    assert perms.secrets == []
    assert perms.mcp == []
    assert perms.integrations == []


def test_mcp_and_integrations_are_default_none_slots() -> None:
    """The mcp/integrations slots exist and default to none (empty) — no client."""
    perms = ToolPermissions()
    assert perms.mcp == []
    assert perms.integrations == []


# ---------------------------------------------------------------------------
# Intersection — effective = owner ∩ workflow ∩ step.
# ---------------------------------------------------------------------------


def test_intersection_requires_grant_at_all_three_levels() -> None:
    """write_files is effective ONLY if granted at owner AND workflow AND step."""
    owner = ToolPermissions(write_files=True)
    workflow = ToolPermissions(write_files=True)
    step = ToolPermissions(write_files=True)
    eff = intersect_permissions(owner, workflow, step)
    assert eff.write_files is True

    # Drop the grant at any single level → effective off.
    assert intersect_permissions(
        ToolPermissions(write_files=False), workflow, step
    ).write_files is False
    assert intersect_permissions(
        owner, ToolPermissions(write_files=False), step
    ).write_files is False
    assert intersect_permissions(
        owner, workflow, ToolPermissions(write_files=False)
    ).write_files is False


def test_ungranted_step_yields_no_privileged_perms() -> None:
    """A step with default ToolPermissions binds no write/exec/network/spawn."""
    eff = intersect_permissions(
        ToolPermissions(), ToolPermissions(), ToolPermissions()
    )
    assert eff.read_files is True  # the one default-ON permission
    assert eff.write_files is False
    assert eff.git is False
    assert eff.spawn_subagents is False
    assert eff.exec is False
    assert eff.network is False


def test_exec_network_secrets_spawn_unbindable_by_default() -> None:
    """Even if the step REQUESTS exec/network/secrets/spawn, an owner/workflow that
    does not grant them keeps them OFF (intersection)."""
    greedy_step = ToolPermissions(
        exec=True,
        network=True,
        secrets=["AWS_KEY"],
        spawn_subagents=True,
    )
    # Owner + workflow are the default least-privilege ceilings (all OFF).
    eff = intersect_permissions(ToolPermissions(), ToolPermissions(), greedy_step)
    assert eff.exec is False
    assert eff.network is False
    assert eff.spawn_subagents is False
    assert eff.secrets == []  # list slot intersects to empty


def test_list_slots_intersect_to_common_members() -> None:
    """secrets/mcp/integrations list slots intersect to the members granted at all levels."""
    owner = ToolPermissions(secrets=["A", "B"], mcp=["m1", "m2"])
    workflow = ToolPermissions(secrets=["B", "C"], mcp=["m2", "m3"])
    step = ToolPermissions(secrets=["B"], mcp=["m2"])
    eff = intersect_permissions(owner, workflow, step)
    assert eff.secrets == ["B"]
    assert eff.mcp == ["m2"]


# ---------------------------------------------------------------------------
# AGENT.md may only LOWER, never raise.
# ---------------------------------------------------------------------------


def test_agent_md_may_lower_a_granted_permission() -> None:
    """An AGENT.md default that turns read_files OFF LOWERS the effective set."""
    granted = intersect_permissions(
        ToolPermissions(write_files=True),
        ToolPermissions(write_files=True),
        ToolPermissions(write_files=True),
    )
    assert granted.write_files is True
    # AGENT.md lowers read_files (a default-ON perm) — applies as an AND mask.
    lowered = granted.lowered_by(ToolPermissions(read_files=False, write_files=True))
    assert lowered.read_files is False
    # It did not drop write_files (still requested True there) — still effective.
    assert lowered.write_files is True


def test_agent_md_cannot_raise_a_permission_its_step_did_not_grant() -> None:
    """An AGENT.md declaring exec where the step grant lacks it does NOT raise it."""
    # The step did not grant exec → effective exec is OFF.
    effective = intersect_permissions(
        ToolPermissions(), ToolPermissions(), ToolPermissions()
    )
    assert effective.exec is False
    # AGENT.md declares exec=True — lowering can only AND-mask, never raise.
    after_agent_md = effective.lowered_by(ToolPermissions(exec=True))
    assert after_agent_md.exec is False  # stays OFF — AGENT.md cannot raise it


def test_agent_md_cannot_raise_write_files() -> None:
    """An AGENT.md write_files=True over an ungranted step stays OFF (no raise)."""
    effective = intersect_permissions(
        ToolPermissions(), ToolPermissions(), ToolPermissions()
    )
    after = effective.lowered_by(ToolPermissions(write_files=True))
    assert after.write_files is False


# ---------------------------------------------------------------------------
# Runtime exec/network/secrets default-deny — the single live enforcement point.
# ---------------------------------------------------------------------------
# The former ``plan.py:ExecutionPolicy`` forward-surface tests were removed in
# 10-02 (INV-12 dual-surface deletion). The live runtime exec/network/secrets
# decision is ``LocalExecutionPolicy.allows`` + the pre-spawn allow/deny check in
# ``app/agents/runtime/local.py`` — exercised by ``tests/agents/test_local_runtime.py``.
