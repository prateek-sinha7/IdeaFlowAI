"""tests/agents/test_tool_permissions.py — least-privilege ToolPermissions (08-03 / D-07).

Proves TOOLPERM-01/02/03 (INV-9): effective tool permissions are the
``intersection(owner_allow_list, workflow_ceiling, step_grant)`` — a permission is
ON only if granted at ALL THREE levels — and an ``AGENT.md`` default may only LOWER
a permission, never raise one its step did not grant. Also proves the §8 defaults
(``read_files`` ON; ``write_files``/``git``/``spawn_subagents``/``exec``/``network``
OFF; ``secrets``/``mcp``/``integrations`` none) and the ``ExecutionPolicy``
enforcement-point seam that default-denies ``exec``/``network``/``secrets`` even with
no runtime host attached (the ``LocalSandboxRuntime`` it gates is Phase 9).

These are pure-data tests: ``ToolPermissions``/``intersect_permissions``/
``ExecutionPolicy`` are stdlib-only dataclasses + functions (no registry side
effect, no kernel/app import).
"""

from __future__ import annotations

from agents.workflows.plan import (
    ExecutionPolicy,
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
# ExecutionPolicy — the default-deny enforcement point (exec/network/secrets).
# ---------------------------------------------------------------------------


def test_execution_policy_denies_exec_by_default() -> None:
    """The ExecutionPolicy default-denies exec with no runtime host attached."""
    policy = ExecutionPolicy()
    allowed, reason = policy.check("exec", ToolPermissions())
    assert allowed is False
    assert "exec" in reason


def test_execution_policy_denies_network_and_secrets() -> None:
    """network and secrets are denied by default (default-deny seam)."""
    policy = ExecutionPolicy()
    assert policy.check("network", ToolPermissions())[0] is False
    assert policy.check("secrets", ToolPermissions())[0] is False


def test_execution_policy_denies_exec_even_when_step_requests_it() -> None:
    """A step REQUESTING exec is denied regardless (security default-OFF, Phase 9 runtime)."""
    policy = ExecutionPolicy()
    requesting = ToolPermissions(exec=True, network=True, secrets=["X"])
    assert policy.check("exec", requesting)[0] is False
    assert policy.check("network", requesting)[0] is False
    assert policy.check("secrets", requesting)[0] is False


def test_execution_policy_allows_read_files() -> None:
    """read_files is not a privileged runtime action — the policy permits it."""
    policy = ExecutionPolicy()
    allowed, _ = policy.check("read_files", ToolPermissions(read_files=True))
    assert allowed is True
