"""Wiring tests: every chainable manifest declares chain_context in context_providers.

BUG-125 (B23) root cause: ChainContextProvider is registered and unit-tested but
no chainable manifest named it in context_providers, so _seed_workflow_context
never called load() and every chained run started with an empty .context/.

These tests use compile_for_run() against real manifests so the compiler's own
name-validation (compiler.py:322 — raises CompilerError on unknown provider name)
acts as a secondary guard.  They will also catch a future manifest regression where
someone removes chain_context from a chainable workflow.

FIX-515 / BUG-125 (B23).
"""

from __future__ import annotations

import pathlib
import sys

import pytest

BACKEND_ROOT = pathlib.Path(__file__).parent.parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# The three built-in workflows that declare chains_from: true.
_CHAINABLE_WORKFLOWS = ["prototype", "ppt_v2", "user_stories"]


class TestChainableManifestsDeclareChainContextProvider:
    """Every manifest with chains_from=True must list chain_context in context_providers.

    This is the wiring test BUG-125 identified as missing: the existing suite
    tested ChainContextProvider in isolation but never verified that a chainable
    manifest actually invokes it via the engine's _seed_workflow_context loop.
    """

    @pytest.mark.parametrize("pipeline_type", _CHAINABLE_WORKFLOWS)
    def test_chainable_manifest_declares_chain_context_provider(
        self, pipeline_type: str
    ) -> None:
        """compile_for_run(<chainable>) succeeds and compiled.context_providers includes chain_context.

        Drives the real compiler so CompilerError fires if chain_context is
        somehow de-registered from the capability registry (compiler.py:322).
        This means the test has two independent failure modes:
          1. CompilerError  — chain_context is not registered (registry.py broke)
          2. AssertionError — chain_context is registered but missing from the manifest
        """
        try:
            from agents.execution_engine.engine import compile_for_run
        except ImportError:
            pytest.skip("agents.execution_engine not importable in this environment")

        try:
            compiled = compile_for_run(pipeline_type)
        except FileNotFoundError:
            pytest.skip(f"{pipeline_type}/workflow.yaml not found on this machine")

        assert compiled.deliverable.chains_from is True, (
            f"{pipeline_type} must declare chains_from: true — "
            "this test is only meaningful for chainable workflows"
        )
        assert "chain_context" in (compiled.context_providers or []), (
            f"{pipeline_type} declares chains_from=True but does not list "
            "'chain_context' in context_providers — ChainContextProvider.load() "
            "will never run and the receiving run starts with an empty .context/ "
            "(BUG-125 / B23 regression)"
        )

    @pytest.mark.parametrize("pipeline_type", _CHAINABLE_WORKFLOWS)
    def test_chain_context_comes_after_opendesign_when_both_declared(
        self, pipeline_type: str
    ) -> None:
        """chain_context must follow opendesign in the provider list.

        opendesign writes .context/design/ and .context/selections.json at run
        entry.  chain_context merges its payload into .context/ second.  If
        chain_context ran first on a workflow that also declares opendesign, the
        opendesign seed would not yet exist and would overwrite the chain payload
        (ordering is preserved verbatim by the compiler and run sequentially by
        the engine loop at engine.py:13812).
        """
        try:
            from agents.execution_engine.engine import compile_for_run
        except ImportError:
            pytest.skip("agents.execution_engine not importable in this environment")

        try:
            compiled = compile_for_run(pipeline_type)
        except FileNotFoundError:
            pytest.skip(f"{pipeline_type}/workflow.yaml not found on this machine")

        providers = list(compiled.context_providers or [])
        if "opendesign" not in providers:
            # No ordering constraint applies, but this is still a chainable
            # workflow: assert the invariant this class guards instead of
            # skipping (a skip fails the mandatory offline partition in CI).
            assert "chain_context" in providers, (
                f"{pipeline_type} declares neither opendesign nor chain_context — "
                "a chainable workflow must list chain_context in context_providers"
            )
            return

        od_idx = providers.index("opendesign")
        cc_idx = (
            providers.index("chain_context") if "chain_context" in providers else -1
        )
        assert cc_idx > od_idx, (
            f"{pipeline_type}: chain_context (index {cc_idx}) must come AFTER "
            f"opendesign (index {od_idx}) in context_providers — "
            "opendesign must seed .context/design/ before chain_context merges the payload"
        )

    def test_non_chainable_manifests_need_not_declare_chain_context(self) -> None:
        """A non-chainable workflow must not be required to list chain_context.

        Documents the negative: chain_context is only meaningful on workflows
        that declare chains_from=True.  Compiling a non-chainable workflow must
        succeed without chain_context in its context_providers.
        """
        try:
            from agents.execution_engine.engine import compile_for_run
        except ImportError:
            pytest.skip("agents.execution_engine not importable in this environment")

        # 'custom' is non-chainable by design (no chains_from declaration).
        try:
            compiled = compile_for_run("custom")
        except FileNotFoundError:
            pytest.skip("custom/workflow.yaml not found on this machine")

        chains_from = getattr(compiled.deliverable, "chains_from", False)
        assert not chains_from, (
            "custom must not declare chains_from: true — "
            "test precondition failed; choose a different non-chainable workflow"
        )
        # chain_context absence on a non-chainable workflow is correct by design.
        # No assertion on its presence — just confirming the compiler accepts it.
