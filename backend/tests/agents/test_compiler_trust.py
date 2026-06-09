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
