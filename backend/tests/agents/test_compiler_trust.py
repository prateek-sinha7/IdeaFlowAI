"""Trust-context compile tests for the compiler (CAP-03 / D-02 / 08-01 Task 3).

The compiler validates EVERY declared capability reference against the registry
(INV-4). Phase 8 adds a trust context (``trust=file|builtin|user|db``): a TRUSTED
(file/builtin) manifest references any registered capability unrestricted (so the
15 file-backed manifests keep Phase-4/7 compile parity); an UNTRUSTED (user/db)
manifest is additionally checked against the per-capability ``user_allowed`` flag
— a not-user-allowed reference is a ``CompilerError`` NAMING the ``(kind, name)``.
This is the seam that keeps ``exec``/``secrets``/``spawn_subagents``/privileged
runtimes off the user palette.

These tests register throwaway capabilities (so they never depend on the live
trust flags of the built-ins) and snapshot/restore the process-global registry
maps around each test.
"""

from __future__ import annotations

import pytest

from agents.capabilities import registry as registry_mod
from agents.capabilities.registry import CapabilityRegistry, register
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.manifest import WorkflowManifest


@pytest.fixture()
def _clean_registry():
    """Snapshot + restore the process-global registry maps around a test."""
    registry_mod.discover()  # ensure built-ins are bound before snapshotting
    known = set(registry_mod._KNOWN)
    impls = dict(registry_mod._IMPLS)
    trust = dict(registry_mod._TRUST)
    discovered = registry_mod._DISCOVERED
    try:
        yield
    finally:
        registry_mod._KNOWN.clear()
        registry_mod._KNOWN.update(known)
        registry_mod._IMPLS.clear()
        registry_mod._IMPLS.update(impls)
        registry_mod._TRUST.clear()
        registry_mod._TRUST.update(trust)
        registry_mod._DISCOVERED = discovered


def _single_step_manifest(strategy: str) -> WorkflowManifest:
    """A minimal one-step manifest referencing exactly one declared capability."""
    return WorkflowManifest(
        id="trust-demo",
        steps=[{"agent": "demo-agent", "strategy": strategy}],
        deliverable={},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
    )


def _grant_step_manifest(
    *,
    strategy: str = "single_shot",
    tools: dict | None = None,
    gates: list[str] | None = None,
) -> WorkflowManifest:
    """A one-step manifest carrying a ``tools:`` grant + ``gates:`` (GRANT-PATH / D-01)."""
    step: dict = {"agent": "exec-agent", "strategy": strategy}
    if tools is not None:
        step["tools"] = tools
    if gates is not None:
        step["gates"] = gates
    return WorkflowManifest(
        id="exec-demo",
        steps=[step],
        deliverable={},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
    )


def test_user_trust_rejects_non_user_allowed_reference(_clean_registry) -> None:
    # Register a privileged (user_allowed=False) strategy and reference it from a
    # user-trust manifest → CompilerError naming the (kind, name).
    @register("strategy", "priv_strategy")  # default user_allowed=False
    class _PrivStrategy:
        name = "priv_strategy"

    manifest = _single_step_manifest("priv_strategy")

    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="user")

    msg = str(exc.value)
    # The message NAMES the offending (kind, name).
    assert "strategy" in msg and "priv_strategy" in msg


def test_db_trust_also_enforces_user_allowed(_clean_registry) -> None:
    @register("strategy", "priv_strategy")
    class _PrivStrategy:
        name = "priv_strategy"

    manifest = _single_step_manifest("priv_strategy")

    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="db")
    assert "priv_strategy" in str(exc.value)


def test_user_trust_allows_user_allowed_reference(_clean_registry) -> None:
    # A user-allowed capability compiles fine under a user-trust manifest.
    @register("strategy", "safe_strategy", user_allowed=True)
    class _SafeStrategy:
        name = "safe_strategy"

    manifest = _single_step_manifest("safe_strategy")
    compiled = WorkflowCompiler().compile(
        manifest, CapabilityRegistry(), trust="user"
    )
    assert [s.strategy for s in compiled.steps] == ["safe_strategy"]


def test_file_trust_compiles_non_user_allowed_reference(_clean_registry) -> None:
    # The SAME privileged reference compiles unrestricted under a file (trusted)
    # manifest — Phase-4/7 parity: a file manifest is never trust-restricted.
    @register("strategy", "priv_strategy")  # user_allowed=False
    class _PrivStrategy:
        name = "priv_strategy"

    manifest = _single_step_manifest("priv_strategy")
    compiled = WorkflowCompiler().compile(
        manifest, CapabilityRegistry(), trust="file"
    )
    assert [s.strategy for s in compiled.steps] == ["priv_strategy"]


def test_default_trust_is_file(_clean_registry) -> None:
    # No trust arg → defaults to file (trusted) so existing callers keep parity.
    @register("strategy", "priv_strategy")
    class _PrivStrategy:
        name = "priv_strategy"

    manifest = _single_step_manifest("priv_strategy")
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
    assert [s.strategy for s in compiled.steps] == ["priv_strategy"]


# ---------------------------------------------------------------------------
# GRANT-PATH (EXEC-01) — trust-conditional exec ceiling + user/db hard-fail.
# ---------------------------------------------------------------------------


def _register_user_allowed_exec_palette() -> None:
    """Register user-allowed strategy + security/approval gates.

    Lets a user/db exec test reach the tool-grant guard (so it is the GRANT, not
    the strategy/gate trust, that fails — isolating the user/db exec/network/secrets
    CompilerError).
    """
    @register("strategy", "ua_strategy", user_allowed=True)
    class _UAStrategy:
        name = "ua_strategy"

    @register("gate", "ua_security", user_allowed=True)
    class _UASecurity:
        name = "ua_security"

    @register("gate", "ua_approval", user_allowed=True)
    class _UAApproval:
        name = "ua_approval"


def test_file_trust_exec_grant_survives_the_ceiling(_clean_registry) -> None:
    # file-trust + tools.exec:true + gates:[security,approval] → Step.tools.exec True.
    manifest = _grant_step_manifest(
        tools={"exec": True}, gates=["security", "approval"]
    )
    compiled = WorkflowCompiler().compile(
        manifest, CapabilityRegistry(), trust="file"
    )
    assert compiled.steps[0].tools.exec is True


def test_builtin_trust_exec_grant_survives_the_ceiling(_clean_registry) -> None:
    manifest = _grant_step_manifest(
        tools={"exec": True}, gates=["security", "approval"]
    )
    compiled = WorkflowCompiler().compile(
        manifest, CapabilityRegistry(), trust="builtin"
    )
    assert compiled.steps[0].tools.exec is True


def test_user_trust_exec_grant_raises_compiler_error(_clean_registry) -> None:
    _register_user_allowed_exec_palette()
    manifest = _grant_step_manifest(
        strategy="ua_strategy",
        tools={"exec": True},
        gates=["ua_security", "ua_approval"],
    )
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="user")
    msg = str(exc.value)
    # The message NAMES the grant + the step.
    assert "exec" in msg and "exec-agent" in msg


def test_db_trust_exec_grant_raises_compiler_error(_clean_registry) -> None:
    _register_user_allowed_exec_palette()
    manifest = _grant_step_manifest(
        strategy="ua_strategy",
        tools={"exec": True},
        gates=["ua_security", "ua_approval"],
    )
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="db")
    assert "exec" in str(exc.value)


def test_user_trust_network_grant_raises_compiler_error(_clean_registry) -> None:
    _register_user_allowed_exec_palette()
    manifest = _grant_step_manifest(strategy="ua_strategy", tools={"network": True})
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="user")
    assert "network" in str(exc.value)


def test_user_trust_secrets_grant_raises_compiler_error(_clean_registry) -> None:
    _register_user_allowed_exec_palette()
    manifest = _grant_step_manifest(
        strategy="ua_strategy", tools={"secrets": ["DEPLOY_KEY"]}
    )
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="user")
    assert "secrets" in str(exc.value)


def test_user_trust_spawn_subagents_grant_raises_compiler_error(_clean_registry) -> None:
    """WR-01: spawn_subagents is engineer-only — a user/db grant fails LOUD (named)."""
    _register_user_allowed_exec_palette()
    manifest = _grant_step_manifest(
        strategy="ua_strategy", tools={"spawn_subagents": True}
    )
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="user")
    assert "spawn_subagents" in str(exc.value)


def test_file_trust_spawn_subagents_grant_survives_the_ceiling(_clean_registry) -> None:
    """The engineer-authored grant still binds True under file trust (parity)."""
    manifest = _grant_step_manifest(tools={"spawn_subagents": True})
    compiled = WorkflowCompiler().compile(
        manifest, CapabilityRegistry(), trust="file"
    )
    assert compiled.steps[0].tools.spawn_subagents is True


# ---------------------------------------------------------------------------
# D-01 — an exec-granting step MUST declare gates: [security, approval].
# ---------------------------------------------------------------------------


def test_d01_exec_missing_approval_gate_raises(_clean_registry) -> None:
    manifest = _grant_step_manifest(tools={"exec": True}, gates=["security"])
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="file")
    msg = str(exc.value)
    assert "approval" in msg and "exec-agent" in msg


def test_d01_exec_missing_security_gate_raises(_clean_registry) -> None:
    manifest = _grant_step_manifest(tools={"exec": True}, gates=["approval"])
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="file")
    msg = str(exc.value)
    assert "security" in msg and "exec-agent" in msg


def test_d01_exec_both_gates_present_compiles_clean(_clean_registry) -> None:
    manifest = _grant_step_manifest(
        tools={"exec": True}, gates=["security", "approval"]
    )
    compiled = WorkflowCompiler().compile(
        manifest, CapabilityRegistry(), trust="file"
    )
    assert compiled.steps[0].tools.exec is True


def test_no_grant_parity_holds_across_trust(_clean_registry) -> None:
    # A no-grant step binds read_files ON / rest OFF regardless of trust — the
    # trust-conditional ceiling must NOT perturb the un-granted path (parity).
    manifest = _grant_step_manifest()  # no tools block
    for trust in ("file", "builtin"):
        compiled = WorkflowCompiler().compile(
            manifest, CapabilityRegistry(), trust=trust
        )
        tools = compiled.steps[0].tools
        assert tools.read_files is True
        assert tools.exec is False
        assert tools.write_files is False
        assert tools.network is False
        assert tools.secrets == []


# ---------------------------------------------------------------------------
# Trust-conditional Limits (FANOUT-09 / OBS-01) — file may RAISE, user/db only LOWER.
# ---------------------------------------------------------------------------


def _limits_manifest(limits: dict, *, strategy: str = "single_shot") -> WorkflowManifest:
    """A one-step manifest carrying a workflow-level ``limits:`` block."""
    return WorkflowManifest(
        id="limits-demo",
        steps=[{"agent": "demo-agent", "strategy": strategy}],
        deliverable={},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
        limits=limits,
    )


def _register_user_allowed_strategy() -> None:
    """Register a user-allowed strategy so the Limits trust rule (not the strategy
    trust) is what a user/db Limits test exercises."""
    @register("strategy", "ua_limits_strategy", user_allowed=True)
    class _UALimitsStrategy:
        name = "ua_limits_strategy"


def test_no_limits_block_compiles_to_empty_limits(_clean_registry) -> None:
    # Parity: an existing manifest with no limits block → an empty Limits (every cap
    # None → run_fanout falls back to the module-constant defaults).
    manifest = _single_step_manifest("single_shot")
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="file")
    assert compiled.limits.max_subagents is None
    assert compiled.limits.max_depth is None
    assert compiled.limits.wall_clock_seconds is None


def test_file_trust_may_raise_a_limits_cap_above_the_ceiling(_clean_registry) -> None:
    # A file (trusted) manifest may RAISE max_subagents above the default ceiling (8).
    manifest = _limits_manifest({"max_subagents": 32, "max_depth": 5})
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="file")
    assert compiled.limits.max_subagents == 32
    assert compiled.limits.max_depth == 5


def test_builtin_trust_may_raise_a_limits_cap(_clean_registry) -> None:
    manifest = _limits_manifest({"wall_clock_seconds": 3600})
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="builtin")
    assert compiled.limits.wall_clock_seconds == 3600


def test_user_trust_raising_max_subagents_is_a_compiler_error(_clean_registry) -> None:
    # A user manifest RAISING max_subagents above the default ceiling (8) is rejected.
    _register_user_allowed_strategy()
    manifest = _limits_manifest({"max_subagents": 16}, strategy="ua_limits_strategy")
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="user")
    assert "max_subagents" in str(exc.value)


def test_db_trust_raising_max_depth_is_a_compiler_error(_clean_registry) -> None:
    _register_user_allowed_strategy()
    manifest = _limits_manifest({"max_depth": 4}, strategy="ua_limits_strategy")
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="db")
    assert "max_depth" in str(exc.value)


def test_user_trust_lowering_a_limits_cap_is_allowed(_clean_registry) -> None:
    # A user manifest may only LOWER — max_subagents=4 (≤ ceiling 8) compiles fine.
    _register_user_allowed_strategy()
    manifest = _limits_manifest(
        {"max_subagents": 4, "max_depth": 1}, strategy="ua_limits_strategy"
    )
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="user")
    assert compiled.limits.max_subagents == 4
    assert compiled.limits.max_depth == 1


def test_user_trust_max_tokens_is_not_a_raise(_clean_registry) -> None:
    # max_tokens has no module-constant ceiling — a user manifest declaring it only
    # constrains itself, so it is NEVER a "raise above the ceiling" rejection.
    _register_user_allowed_strategy()
    manifest = _limits_manifest({"max_tokens": 1_000_000}, strategy="ua_limits_strategy")
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="user")
    assert compiled.limits.max_tokens == 1_000_000


def test_unknown_limits_key_is_rejected(_clean_registry) -> None:
    manifest = _limits_manifest({"max_subagents": 4, "fork_bomb": True})
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="file")
    assert "fork_bomb" in str(exc.value)
