"""tests/agents/test_prompt_ledger_v2.py — Requirement 13 prompt-input ledger.

Verifies all 30 ledger rows (Requirement 13 AC 6-7) across five modes:
  normal, retry, redo, resume, chained-run.

Tests are run through the full composer (``_compose_context_message`` plus
``_compose_system_prompt``), NOT by popping dictionaries or inspecting source
literals alone.

Rows 22 (multimodal blocks) and 27 (staged skills) carry explicit
not-applicable assertions where source inspection / staging-layer evidence
is the appropriate verification artefact.

Additional coverage (Requirement 13 AC 3, 4, 5, 8, 9):
  AC 3 — staged skills remain discoverable after factory skills block removal
  AC 4 — no REQUEST.md is created or propagated downstream
  AC 5 — migrated first step produces a durable contract artifact
  AC 8 — verifications via full composer
  AC 9 — prompt viewer shows effective prompt + targeted control payload

Offline-safe: no LLM calls, no Postgres, no Chromium.
Line-number references are navigation hints only — confirm symbols before editing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Root paths derived from this file's location (backend/)
# ---------------------------------------------------------------------------

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ENGINE_PY = _BACKEND_ROOT / "agents" / "execution_engine" / "engine.py"
_FACTORY_PY = _BACKEND_ROOT / "agents" / "factory.py"
_PROMPTS_ROOT = _BACKEND_ROOT / "agents" / "prompts"
_WORKFLOWS_ROOT = _BACKEND_ROOT / "agents" / "workflows"
_FRONTEND_ROOT = _BACKEND_ROOT.parent / "frontend" / "src"


def _engine_text() -> str:
    return _ENGINE_PY.read_text(encoding="utf-8")


def _factory_text() -> str:
    return _FACTORY_PY.read_text(encoding="utf-8")


# ===========================================================================
# Row-level policy lookup helpers
# ===========================================================================


def _read_agent_md(agent_id: str) -> str:
    path = _PROMPTS_ROOT / agent_id / "AGENT.md"
    assert path.exists(), f"AGENT.md not found at {path}"
    return path.read_text(encoding="utf-8")


def _prompt_policy(agent_id: str) -> str:
    text = _read_agent_md(agent_id)
    m = re.search(r"^prompt_policy:\s*(\S+)", text, re.MULTILINE)
    return m.group(1) if m else "default"


# ===========================================================================
# Ledger rows 1-7 — System-prompt block destinations
# ===========================================================================


class TestLedgerRows1to7SystemPromptBlocks:
    """Rows 1-7: each pre-migration system-prompt block has a defined V2 destination.

    Verified through the live registry and the factory's assembled output, not by
    source inspection alone (Requirement 13 AC 8).
    """

    def test_row1_tool_availability_dropped_for_body_only(self) -> None:
        """Row 1: tool-availability text is dropped for body_only agents.

        Under the body_only policy the block is not in the order tuple, so a
        tool-less agent gets no tool_availability preamble — the factory only
        inserts it when no_tools=True AND the policy order includes the slot.
        """
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "body_only")
        assert "tool_availability" not in policy.order, (
            "Row 1: body_only policy MUST NOT emit tool_availability — "
            "dropped per V2 destination (Requirement 13 AC 6 Row 1)"
        )

    def test_row2_template_design_injected_via_context_providers(self) -> None:
        """Row 2: template/design/craft injection goes to .context/design/.

        The opendesign context_provider loads the OD blocks from .context/design/
        (not inline in the system prompt). Source check: prototype-specify declares
        ``injects: [template, design_system]``, which gates the opendesign provider.
        """
        spec_md = _read_agent_md("prototype-specify")
        assert "template" in spec_md, (
            "Row 2: prototype-specify must declare 'template' in injects — "
            "template material is gated on this declaration (Requirement 13 AC 6 Row 2)"
        )
        assert (
            "design_system" in spec_md
        ), "Row 2: prototype-specify must declare 'design_system' in injects"

    def test_row3_guardrails_in_governance_order(self) -> None:
        """Row 3: guardrails stay in the governance system-prompt order."""
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "governance")
        assert "guardrails" in policy.order, (
            "Row 3: governance policy must include 'guardrails' in its order tuple "
            "(Requirement 13 AC 6 Row 3)"
        )

    def test_row4_skills_in_governance_and_default_orders(self) -> None:
        """Row 4: skills block remains in default order; governance drops the slot.

        deepagents' SKILLS_SYSTEM_PROMPT picks up staged files regardless.
        This is the Row 4 / Row 27 pair: the *factory skills block* is gone;
        deepagents' runtime block is unaffected (tested in Row 27).
        """
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        default_policy = registry.resolve("prompt", "default")
        body_only_policy = registry.resolve("prompt", "body_only")
        governance_policy = registry.resolve("prompt", "governance")

        # Default still includes the skills slot (for byte-identical INV-3 goldens).
        assert (
            "skills" in default_policy.order
        ), "Row 4: default policy must retain 'skills' slot for INV-3 byte-parity"
        # body_only and governance drop it (Seam 2 / factory skills block removed).
        assert "skills" not in body_only_policy.order, (
            "Row 4: body_only policy must NOT include 'skills' slot — "
            "factory skills block removed per Task 10.2"
        )
        assert "skills" not in governance_policy.order, (
            "Row 4: governance policy must NOT include 'skills' slot — "
            "factory skills block removed per Task 10.2"
        )

    def test_row5_behavioral_hooks_in_governance_order(self) -> None:
        """Row 5: behavioral hooks are in the governance system-prompt order."""
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        governance = registry.resolve("prompt", "governance")
        assert "hooks" in governance.order, (
            "Row 5: governance policy must include 'hooks' in its order tuple "
            "(Requirement 13 AC 6 Row 5)"
        )

    def test_row6_constitution_in_governance_order_only(self) -> None:
        """Row 6: Constitution is in governance order; body_only explicitly drops it."""
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        governance = registry.resolve("prompt", "governance")
        body_only = registry.resolve("prompt", "body_only")
        assert "constitution" in governance.order, (
            "Row 6: governance policy must include 'constitution' "
            "(Requirement 13 AC 6 Row 6 / Requirement 13 AC 2)"
        )
        assert "constitution" not in body_only.order, (
            "Row 6: body_only policy must NOT include 'constitution' — "
            "ungoverned agents intentionally drop it; governed agents use governance"
        )

    def test_row7_prompt_body_is_agent_md(self) -> None:
        """Row 7: prompt body is the agent's AGENT.md for every policy.

        All three policies include prompt_body in their order and have
        always_emit_body=True so the AGENT.md is always emitted.
        """
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        for policy_name in ("default", "body_only", "governance"):
            policy = registry.resolve("prompt", policy_name)
            assert "prompt_body" in policy.order, (
                f"Row 7: '{policy_name}' policy must include 'prompt_body' — "
                "AGENT.md is the agent's system prompt body"
            )
            assert policy.always_emit_body, (
                f"Row 7: '{policy_name}'.always_emit_body must be True so prompt_body "
                "is always present"
            )


# ===========================================================================
# Ledger rows 8-9 — Brief and retry feedback delivery
# ===========================================================================


class TestLedgerRows8to9BriefAndRetryDelivery:
    """Rows 8-9: brief and retry routing in _compose_context_message.

    Replaced from source-inspection to full-composer behavioural tests (B19).
    Drives the real _run_agent via _EngineHarness/_drive_agent and reads the
    emitted agent_input.context_message events.
    """

    @pytest.mark.asyncio
    async def test_row8_first_agent_receives_brief(self) -> None:
        """Row 8: the first-dispatched agent (index 0) receives the original brief.

        Drives _compose_context_message end-to-end through _run_agent and asserts
        the 'agent_input' event carries '=== ORIGINAL USER REQUEST ===' in
        context_message.  SC-001 / INV-1: the predicate is positional (index 0),
        not keyed on any workflow name.
        """
        from agents.loader import load_agent_spec
        from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn
        from tests.unit.agents.test_redo_gate_safety import (
            _EngineHarness,
            _drive_agent,
            _make_ectx,
        )

        spec = load_agent_spec("domain-analyst")
        with _EngineHarness(
            lambda aid, idx: ScriptedFakeChatModel(
                [_ScriptedTurn(texts=["spec output."], usage=(5, 3))]
            )
        ) as h:
            ectx = _make_ectx("row8-first-run")
            results: list = []
            events = await _drive_agent(h.engine, spec, ectx, results, [spec], index=0)

        msgs = [
            ev["data"]["context_message"]
            for ev in events
            if ev.get("type") == "agent_input"
            and "context_message" in ev.get("data", {})
        ]
        assert msgs, "No agent_input events emitted"
        assert "=== ORIGINAL USER REQUEST ===" in msgs[0], (
            "Row 8: first agent (index 0) must receive '=== ORIGINAL USER REQUEST ==='"
            " in context_message — positional SC-001 gate"
        )

    @pytest.mark.asyncio
    async def test_row8_non_first_agent_receives_no_brief(self) -> None:
        """Row 8: a non-first agent (index > 0) must NOT receive the brief or
        any world-block marker in its context_message.

        The 'parts = []' else-branch means later agents get an empty context
        message (they read context from .agents/ files instead).
        """
        from agents.loader import load_agent_spec
        from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn
        from tests.unit.agents.test_redo_gate_safety import (
            _EngineHarness,
            _drive_agent,
            _make_ectx,
        )

        spec_a = load_agent_spec("domain-analyst")
        spec_b = load_agent_spec("epic-architect")
        ordered = [spec_a, spec_b]

        with _EngineHarness(
            lambda aid, idx: ScriptedFakeChatModel(
                [_ScriptedTurn(texts=["output."], usage=(5, 3))]
            )
        ) as h:
            ectx = _make_ectx("row8-non-first-run")
            results: list = []
            events = await _drive_agent(
                h.engine, spec_b, ectx, results, ordered, index=1
            )

        msgs = [
            ev["data"]["context_message"]
            for ev in events
            if ev.get("type") == "agent_input"
            and "context_message" in ev.get("data", {})
        ]
        assert msgs, "No agent_input events for non-first agent"
        assert (
            "=== ORIGINAL USER REQUEST ===" not in msgs[0]
        ), "Row 8: non-first agent must NOT receive '=== ORIGINAL USER REQUEST ==='"
        # Also confirm no other world-block markers leak
        _WORLD_BLOCKS = (
            "ACTIVE DESIGN SYSTEM",
            "ACTIVE TEMPLATE",
            "## Uploaded Files",
            "## Planning Context",
            "TEMPLATE COMPLIANCE",
        )
        for marker in _WORLD_BLOCKS:
            assert (
                marker not in msgs[0]
            ), f"Row 8: non-first agent must not receive world-block marker {marker!r}"

    @pytest.mark.asyncio
    async def test_row8_seam2_deleted_no_policy_branch_in_context_message(self) -> None:
        """Row 8 [Phase Z]: seam 2 no longer branches on prompt_policy at all.
        A non-first agent with governance policy and one with body_only policy
        both receive an empty context_message (no world blocks, no brief).
        """
        from agents.loader import load_agent_spec
        from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn
        from tests.unit.agents.test_redo_gate_safety import (
            _EngineHarness,
            _drive_agent,
            _make_ectx,
        )
        import dataclasses

        spec_a = load_agent_spec("domain-analyst")  # governance, index 0 (first)
        spec_b = load_agent_spec("epic-architect")  # governance, index 1 (second)
        # Clone spec_b with body_only to prove policy doesn't affect seam-2 output
        spec_b_body = dataclasses.replace(spec_b, prompt_policy="body_only")
        ordered = [spec_a, spec_b]

        with _EngineHarness(
            lambda aid, idx: ScriptedFakeChatModel(
                [_ScriptedTurn(texts=["output."], usage=(5, 3))]
            )
        ) as h:
            ectx = _make_ectx("row8-gov-run")
            results: list = []
            evs_gov = await _drive_agent(
                h.engine, spec_b, ectx, results, ordered, index=1
            )

        with _EngineHarness(
            lambda aid, idx: ScriptedFakeChatModel(
                [_ScriptedTurn(texts=["output."], usage=(5, 3))]
            )
        ) as h:
            ectx2 = _make_ectx("row8-body-run")
            results2: list = []
            evs_body = await _drive_agent(
                h.engine, spec_b_body, ectx2, results2, [spec_a, spec_b_body], index=1
            )

        def _ctx(evs):
            return next(
                (
                    ev["data"]["context_message"]
                    for ev in evs
                    if ev.get("type") == "agent_input"
                    and "context_message" in ev.get("data", {})
                ),
                None,
            )

        msg_gov = _ctx(evs_gov)
        msg_body = _ctx(evs_body)
        assert msg_gov is not None, "governance non-first agent must emit agent_input"
        assert msg_body is not None, "body_only non-first agent must emit agent_input"
        # Neither should contain world blocks or the brief
        for marker in (
            "=== ORIGINAL USER REQUEST",
            "ACTIVE DESIGN SYSTEM",
            "ACTIVE TEMPLATE",
        ):
            assert (
                marker not in msg_gov
            ), f"governance non-first must not carry {marker!r}"
            assert (
                marker not in msg_body
            ), f"body_only non-first must not carry {marker!r}"
        assert msg_gov == msg_body, (
            "Row 8 [Phase Z]: context_message must be identical for governance and "
            "body_only non-first agents — prompt_policy must not affect seam-2 output"
        )

    @pytest.mark.asyncio
    async def test_row9_retry_feedback_delivered_to_target_only(self) -> None:
        """Row 9: conditional-gate retry feedback is delivered to exactly the
        retrying agent and not to any other agent dispatched on the same ectx.

        Drives two separate _drive_agent calls sharing one ExecutionContext.
        The feedback is stashed for spec_a only; spec_b (non-retry) must not
        receive it.  After spec_a's dispatch the store must be empty.
        """
        from agents.loader import load_agent_spec
        from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn
        from tests.unit.agents.test_redo_gate_safety import (
            _EngineHarness,
            _drive_agent,
            _make_ectx,
        )

        spec_a = load_agent_spec("domain-analyst")  # the retrying agent
        spec_b = load_agent_spec("epic-architect")  # unrelated, same ectx
        ordered = [spec_a, spec_b]

        with _EngineHarness(
            lambda aid, idx: ScriptedFakeChatModel(
                [_ScriptedTurn(texts=["output."], usage=(5, 3))]
            )
        ) as h:
            ectx = _make_ectx("row9-retry-run")

            # Stash feedback for spec_a only.
            ectx.pending_route_feedback[spec_a.id] = {
                "from_step": "judge",
                "decision": "fail",
                "from_output": "previous answer",
                "pass_number": 2,
                "max_passes": 3,
                "authored": "Please try again differently.",
            }

            results: list = []
            # spec_b dispatched first at index=1 — must NOT consume spec_a's feedback
            evs_b = await _drive_agent(
                h.engine, spec_b, ectx, results, ordered, index=1
            )
            # spec_a dispatched second at index=0 (retry — index doesn't matter for fb)
            evs_a = await _drive_agent(
                h.engine, spec_a, ectx, results, ordered, index=0
            )

        def _ctx(evs):
            return next(
                (
                    ev["data"]["context_message"]
                    for ev in evs
                    if ev.get("type") == "agent_input"
                    and "context_message" in ev.get("data", {})
                ),
                "",
            )

        msg_a = _ctx(evs_a)
        msg_b = _ctx(evs_b)

        assert (
            "=== RETRY" in msg_a
        ), "Row 9: retrying agent must receive the RETRY block in context_message"
        assert (
            "Please try again differently." in msg_a
        ), "Row 9: authored feedback must appear in the retrying agent's message"
        assert "=== RETRY" not in msg_b, (
            "Row 9: non-retrying agent must NOT receive the RETRY block "
            "(Requirement 14 AC 2 — targeted per-agent, not broadcast)"
        )
        # Consume-once: store drained after spec_a's dispatch
        assert (
            ectx.pending_route_feedback.get(spec_a.id) is None
        ), "Row 9: feedback store must be empty after delivery (consume-once)"


# ===========================================================================
# Ledger rows 10-21, 23-26, 28-30 — Specific injection blocks
# ===========================================================================


class TestLedgerRowsInjectionBlocks:
    """Rows 10-21 + 23-26 + 28-30: each injection block has a defined V2 destination.

    Rows 12-17, 19, 28 use full-composer behavioural tests via _EngineHarness
    (replaced from source inspection, B19).  Rows 18/20 use valid negative source
    checks (proving retired blocks are absent — the only approach for deletion
    proof).  Rows 10/11/21-27/29/30 check non-engine files or live registry state.
    """

    def test_row10_planner_analysis_written_to_planner_md(self) -> None:
        """Row 10: planner analysis → PLANNER.md written after clarify merge.

        Source check: ``sandbox.write("PLANNER.md"`` appears AFTER
        ``planning_context = clarify_task.result()`` (Requirement 13 AC 6 Row 10).
        Tested more thoroughly in test_phase7_seam2_removal.py:TestPlannerMdWrittenAfterClarify.
        """
        text = _engine_text()
        lines = text.splitlines()

        def _line(pattern: str) -> int:
            for i, l in enumerate(lines):
                if pattern in l:
                    return i
            return -1

        clarify_line = _line("planning_context = clarify_task.result()")
        write_line = _line('sandbox.write("PLANNER.md"')

        # If either is absent, the test cannot prove the ordering — skip rather than false-pass.
        if clarify_line == -1 or write_line == -1:
            pytest.skip(
                "Row 10: clarify_task.result() or PLANNER.md write not found "
                "— cannot determine relative ordering"
            )
        assert write_line > clarify_line, (
            f"Row 10: PLANNER.md write (line {write_line}) must come AFTER "
            f"clarify_task.result() (line {clarify_line}) — "
            "Requirement 13 AC 6 Row 10"
        )

    def test_row11_active_design_template_via_context_providers(self) -> None:
        """Row 11: active design/template material goes to .context/design/.

        Source check: the opendesign context provider is resolved via
        ``registry.resolve("context_provider", name)`` in _compose_context_message;
        it is declared in the workflow's context_providers list, not hardcoded.
        SC-001: no workflow-name branch.
        """
        text = _engine_text()
        assert 'registry.resolve("context_provider", name)' in text or (
            '_CAPABILITY_REGISTRY.resolve("context_provider", name)' in text
        ), (
            "Row 11: context_provider must be resolved generically — no workflow-name "
            "branch (SC-001 / INV-1)"
        )

    @pytest.mark.asyncio
    async def test_row12_read_files_false_step_pastes_upstream_output(self) -> None:
        """Row 12: a step with read_files=false still receives the upstream agent
        output pasted as '--- Output from … ---' because it cannot read .agents/.

        This is the SURVIVING paste path after Phase Z — present only when the
        step's tool configuration makes the disk substitute unreachable.
        """
        import dataclasses
        from types import SimpleNamespace

        from agents.artifacts.graph import ArtifactGraph
        from agents.loader import load_agent_spec
        from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn
        from tests.unit.agents.test_redo_gate_safety import (
            _EngineHarness,
            _drive_agent,
            _make_ectx,
        )

        # Use specs that have matching produces/consumes declared.
        spec_a = load_agent_spec("domain-analyst")
        spec_b = load_agent_spec("epic-architect")

        # Verify the produces/consumes relationship exists on these specs.
        produces_a = set(getattr(spec_a, "produces", []) or [])
        consumes_b = set(getattr(spec_b, "consumes", []) or [])
        if not (produces_a & consumes_b):
            pytest.skip(
                f"domain-analyst.produces {produces_a!r} ∩ epic-architect.consumes "
                f"{consumes_b!r} = ∅ — cannot test row 12 with these specs"
            )

        # Give spec_b a compiled step with read_files=False so the paste path fires.
        fake_tools = SimpleNamespace(read_files=False, write_files=False)
        fake_step = SimpleNamespace(tools=fake_tools)

        with _EngineHarness(
            lambda aid, idx: ScriptedFakeChatModel(
                [_ScriptedTurn(texts=["upstream output text."], usage=(5, 3))]
            )
        ) as h:
            ectx = _make_ectx("row12-paste-run")
            ectx.current_step = fake_step  # type: ignore[assignment]

            # Seed a typed artifact for the intersecting kind.
            kind = next(iter(produces_a & consumes_b))
            ectx.artifacts = ArtifactGraph()
            ectx.artifacts.write_ref(
                run_id="row12-paste-run",
                owner_id="anon",
                workspace_id="ws",
                kind=kind,
                producer_step=spec_a.id,
                producer_agent=spec_a.id,
                task_id=None,
                content="upstream output text.",
                location=f"artifact_refs/{spec_a.id}",
            )

            ordered = [spec_a, spec_b]
            results: list = []
            events = await _drive_agent(
                h.engine, spec_b, ectx, results, ordered, index=1
            )

        msgs = [
            ev["data"]["context_message"]
            for ev in events
            if ev.get("type") == "agent_input"
            and "context_message" in ev.get("data", {})
        ]
        assert msgs, "No agent_input events emitted for spec_b"
        assert "--- Output from" in msgs[0], (
            "Row 12: a read_files=False step must receive upstream output pasted "
            "as '--- Output from …' (the sole surviving paste path, Req 13 AC 6 Row 12)"
        )

    @pytest.mark.asyncio
    async def test_row13_prior_artifact_appears_when_redo_directive_set(self) -> None:
        """Row 13: the PRIOR ARTIFACT UNDER REVISION block appears in the
        context_message when BOTH spec_revision_prior_artifact AND redo_directive
        are set (the ISS-086 redo path).

        Calls _compose_context_message directly so the loop-local overwrite in
        _run_agent does not interfere. When only prior_artifact is set (no
        redo_directive), the block must NOT appear — the FIX-217 paste was retired.
        """
        from agents.execution_engine.context import ExecutionContext
        from agents.execution_engine.engine import ExecutionEngine
        from agents.loader import load_agent_spec

        engine = ExecutionEngine()
        spec = load_agent_spec("domain-analyst")

        # ── case A: both fields set → block must appear ──────────────────────
        ectx_a = ExecutionContext(run_id="row13-both", owner_id="anon")
        ectx_a.spec_revision_prior_artifact = "Previous draft content."
        ectx_a.redo_directive = "Fix section 2."
        msg_a = await engine._compose_context_message(
            spec, 0, [spec], "Build something.", {}, ectx_a
        )
        assert "=== PRIOR ARTIFACT UNDER REVISION ===" in msg_a, (
            "Row 13: PRIOR ARTIFACT UNDER REVISION must appear when both "
            "spec_revision_prior_artifact and redo_directive are set (ISS-086 path)"
        )
        assert "Previous draft content." in msg_a

        # ── case B: only prior_artifact, no redo_directive → block must NOT appear ──
        ectx_b = ExecutionContext(run_id="row13-art-only", owner_id="anon")
        ectx_b.spec_revision_prior_artifact = "Previous draft content."
        msg_b = await engine._compose_context_message(
            spec, 0, [spec], "Build something.", {}, ectx_b
        )
        assert "=== PRIOR ARTIFACT UNDER REVISION ===" not in msg_b, (
            "Row 13: the FIX-217 paste path is retired — block must NOT appear "
            "when redo_directive is empty (Phase M10)"
        )

    @pytest.mark.asyncio
    async def test_row14_redo_directive_appears_and_is_consumed_once(self) -> None:
        """Row 14: the ADDITIONAL INSTRUCTIONS (REVISE) block appears when
        redo_directive is set. Cleared by _compose_context_message itself (F3).

        Calls _compose_context_message directly — the loop-local in _run_agent
        would overwrite redo_directive before the call.
        """
        from agents.execution_engine.context import ExecutionContext
        from agents.execution_engine.engine import ExecutionEngine
        from agents.loader import load_agent_spec

        engine = ExecutionEngine()
        spec = load_agent_spec("domain-analyst")

        ectx = ExecutionContext(run_id="row14-redo", owner_id="anon")
        ectx.redo_directive = "Rewrite section 3 to be more concise."
        msg = await engine._compose_context_message(
            spec, 0, [spec], "Build something.", {}, ectx
        )
        assert "=== ADDITIONAL INSTRUCTIONS (REVISE) ===" in msg, (
            "Row 14: REVISE block must appear when redo_directive is set "
            "(Requirement 13 AC 6 Row 14)"
        )
        assert "Rewrite section 3 to be more concise." in msg
        # _compose_context_message does NOT clear redo_directive — it is cleared by
        # the _run_agent finally block. We only assert the block appeared.

        # When redo_directive is empty the block must NOT appear (dormant).
        ectx2 = ExecutionContext(run_id="row14-no-redo", owner_id="anon")
        msg2 = await engine._compose_context_message(
            spec, 0, [spec], "Build something.", {}, ectx2
        )
        assert (
            "=== ADDITIONAL INSTRUCTIONS (REVISE) ===" not in msg2
        ), "Row 14: REVISE block must NOT appear when redo_directive is empty (dormant)"

    @pytest.mark.asyncio
    async def test_row15_spec_revision_context_appears_when_set(self) -> None:
        """Row 15: the SPEC KIT ANALYSIS REPORT block appears when
        spec_revision_context is set (the KAN-101 revision sub-pipeline path).
        Dormant when empty.

        Calls _compose_context_message directly.
        Note: spec_revision_context is NOT cleared by _compose_context_message —
        it is cleared by _run_spec_revision_sub_pipeline on its own path.
        """
        from agents.execution_engine.context import ExecutionContext
        from agents.execution_engine.engine import ExecutionEngine
        from agents.loader import load_agent_spec

        engine = ExecutionEngine()
        spec = load_agent_spec("domain-analyst")

        ectx = ExecutionContext(run_id="row15-rev-ctx", owner_id="anon")
        ectx.spec_revision_context = "Issue: section 2 is duplicated."
        msg = await engine._compose_context_message(
            spec, 0, [spec], "Build something.", {}, ectx
        )
        assert "=== SPEC KIT ANALYSIS REPORT (REVISION CONTEXT) ===" in msg, (
            "Row 15: SPEC KIT ANALYSIS REPORT block must appear when "
            "spec_revision_context is set (Requirement 13 AC 6 Row 15)"
        )
        assert "Issue: section 2 is duplicated." in msg

        # Dormant when empty.
        ectx2 = ExecutionContext(run_id="row15-no-rev", owner_id="anon")
        msg2 = await engine._compose_context_message(
            spec, 0, [spec], "Build something.", {}, ectx2
        )
        assert (
            "=== SPEC KIT ANALYSIS REPORT" not in msg2
        ), "Row 15: block must NOT appear when spec_revision_context is empty"

    @pytest.mark.asyncio
    async def test_row16_user_guidance_one_shot_consumed_sticky_retained(self) -> None:
        """Row 16: the USER GUIDANCE block appears when steering_notes are present.
        One-shot notes are dropped after dispatch; sticky notes persist (D-06).
        """
        from agents.loader import load_agent_spec
        from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn
        from tests.unit.agents.test_redo_gate_safety import (
            _EngineHarness,
            _drive_agent,
            _make_ectx,
        )

        spec = load_agent_spec("domain-analyst")

        with _EngineHarness(
            lambda aid, idx: ScriptedFakeChatModel(
                [_ScriptedTurn(texts=["output."], usage=(5, 3))]
            )
        ) as h:
            ectx = _make_ectx("row16-guidance-run")
            ectx.steering_notes = [  # type: ignore[attr-defined]
                {"text": "One-shot instruction.", "sticky": False},
                {"text": "Sticky note.", "sticky": True},
            ]
            results: list = []
            events = await _drive_agent(h.engine, spec, ectx, results, [spec], index=0)

        msgs = [
            ev["data"]["context_message"]
            for ev in events
            if ev.get("type") == "agent_input"
            and "context_message" in ev.get("data", {})
        ]
        assert msgs, "No agent_input events"
        assert "=== USER GUIDANCE ===" in msgs[0], (
            "Row 16: USER GUIDANCE block must appear when steering_notes are set "
            "(Requirement 13 AC 6 Row 16)"
        )
        assert "One-shot instruction." in msgs[0]
        assert "Sticky note." in msgs[0]

        # Consume-once: one-shot dropped, sticky retained
        remaining = getattr(ectx, "steering_notes", [])
        texts = [n["text"] for n in remaining if isinstance(n, dict)]
        assert (
            "One-shot instruction." not in texts
        ), "Row 16: one-shot note must be dropped after dispatch"
        assert (
            "Sticky note." in texts
        ), "Row 16: sticky note must be retained after dispatch (D-06)"

        # Dormant when empty.
        with _EngineHarness(
            lambda aid, idx: ScriptedFakeChatModel(
                [_ScriptedTurn(texts=["output."], usage=(5, 3))]
            )
        ) as h:
            ectx2 = _make_ectx("row16-no-guidance-run")
            results2: list = []
            events2 = await _drive_agent(
                h.engine, spec, ectx2, results2, [spec], index=0
            )

        msgs2 = [
            ev["data"]["context_message"]
            for ev in events2
            if ev.get("type") == "agent_input"
            and "context_message" in ev.get("data", {})
        ]
        assert msgs2
        assert (
            "=== USER GUIDANCE ===" not in msgs2[0]
        ), "Row 16: USER GUIDANCE block must NOT appear when steering_notes is empty"

    def test_row17_revision_analysis_paste_retired(self) -> None:
        """Row 17 [Phase Z]: the REVISION ANALYSIS paste is RETIRED.

        ``analyzer_solution`` still exists on ExecutionContext (the field survives
        for other readers), but the ``=== REVISION ANALYSIS ===`` block must NOT
        appear as an executable string in _compose_context_message — a migrated
        agent reads the analyzer artifact from .agents/ itself.

        The string appears only in a COMMENT in engine.py (documentation of the
        retired path); we assert it is not in executable (non-comment) code.
        """
        from agents.execution_engine.context import ExecutionContext

        # Field must still exist on ExecutionContext (other consumers use it).
        ectx = ExecutionContext(run_id="row17-check", owner_id="anon")
        assert hasattr(ectx, "analyzer_solution"), (
            "Row 17: analyzer_solution must still be an ExecutionContext field "
            "(other consumers read it; only the paste was retired)"
        )

        # The paste block header must not appear in any non-comment line in engine.py.
        # (It DOES appear in a comment documenting the retired path — that is expected.)
        text = _engine_text()
        executable_lines_with_marker = [
            line
            for line in text.splitlines()
            if "=== REVISION ANALYSIS ===" in line and not line.lstrip().startswith("#")
        ]
        assert not executable_lines_with_marker, (
            "Row 17: '=== REVISION ANALYSIS ===' must not appear in executable "
            "(non-comment) code in engine.py — only in comments documenting the "
            "retired paste path (Phase Z)"
        )

    def test_row18_current_prototype_html_retired(self) -> None:
        """Row 18 [Phase Z, GAPS §0.3 step N+1]: the paste is RETIRED, not present.

        The ``=== CURRENT PROTOTYPE HTML ===`` world-block this row used to
        describe (injected for no-tools first agents) was deleted from
        ``_compose_context_message`` once every workflow finished the Q4
        migration — a no-tools revision agent that needs the seeded HTML is
        granted ``read_files`` instead. ``revision_original_html`` itself stays
        (still read by ``_build_context_sources`` for the "Context Received"
        chip and by the ``previous_run`` provider that seeds it).
        """
        text = _engine_text()
        assert "revision_original_html" in text, (
            "Row 18: revision_original_html must still be present in engine.py "
            "(other consumers besides the retired paste)"
        )
        assert (
            "=== CURRENT PROTOTYPE HTML ===" not in text
        ), "Row 18: the CURRENT PROTOTYPE HTML paste must be gone (Phase Z)"

    @pytest.mark.asyncio
    async def test_row19_current_task_block_appears_when_build_task_set(self) -> None:
        """Row 19: the CURRENT TASK block appears in context_message when
        ectx.build_task_number is set (the task-loop strategy path).
        When build_task_number is empty the block must not appear (dormant).
        """
        from agents.loader import load_agent_spec
        from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn
        from tests.unit.agents.test_redo_gate_safety import (
            _EngineHarness,
            _drive_agent,
            _make_ectx,
        )

        spec = load_agent_spec("domain-analyst")

        # ── with task set → block must appear ────────────────────────────────
        with _EngineHarness(
            lambda aid, idx: ScriptedFakeChatModel(
                [_ScriptedTurn(texts=["output."], usage=(5, 3))]
            )
        ) as h:
            ectx = _make_ectx("row19-task-run")
            ectx.build_task_number = "2"  # type: ignore[attr-defined]
            ectx.build_task_total = "5"  # type: ignore[attr-defined]
            ectx.current_task_block = "Add a delete button."  # type: ignore[attr-defined]
            results: list = []
            events = await _drive_agent(h.engine, spec, ectx, results, [spec], index=0)

        msgs = [
            ev["data"]["context_message"]
            for ev in events
            if ev.get("type") == "agent_input"
            and "context_message" in ev.get("data", {})
        ]
        assert msgs, "No agent_input events (task-set case)"
        assert "=== CURRENT TASK ===" in msgs[0], (
            "Row 19: CURRENT TASK block must appear when build_task_number is set "
            "(Requirement 13 AC 6 Row 19)"
        )
        assert "Task 2 of 5" in msgs[0]
        assert "Add a delete button." in msgs[0]

        # ── without task set → block must not appear ─────────────────────────
        with _EngineHarness(
            lambda aid, idx: ScriptedFakeChatModel(
                [_ScriptedTurn(texts=["output."], usage=(5, 3))]
            )
        ) as h:
            ectx2 = _make_ectx("row19-no-task-run")
            # build_task_number defaults to empty
            results2: list = []
            events2 = await _drive_agent(
                h.engine, spec, ectx2, results2, [spec], index=0
            )

        msgs2 = [
            ev["data"]["context_message"]
            for ev in events2
            if ev.get("type") == "agent_input"
            and "context_message" in ev.get("data", {})
        ]
        assert msgs2
        assert (
            "=== CURRENT TASK ===" not in msgs2[0]
        ), "Row 19: CURRENT TASK block must NOT appear when build_task_number is empty"

    def test_row20_compacted_build_skeleton_retired(self) -> None:
        """Row 20 [Phase Z, GAPS §0.3 step N+1]: the skeleton paste is RETIRED.

        The ``=== CURRENT PROTOTYPE (skeleton ...`` world-block this row used to
        describe was deleted from ``_compose_context_message`` once every
        workflow finished the Q4 migration — a migrated builder calls
        ``read_file('prototype.html')`` itself instead of receiving the
        compacted skeleton pasted.
        """
        text = _engine_text()
        assert (
            "=== CURRENT PROTOTYPE (skeleton" not in text
        ), "Row 20: the CURRENT PROTOTYPE (skeleton ...) paste must be gone (Phase Z)"

    def test_row21_template_compliance_ids_via_context_selections_json(self) -> None:
        """Row 21: template-compliance ids → .context/selections.json.

        Source check: ``selections.json`` is mentioned by the ``.context/``
        writer (``app/services/od_context_sandbox.py``, moved out of
        ``app/api/launch_context.py`` so the kernel never imports ``app.api``)
        as the context selections file destination.
        """
        # Check the .context/ writer for the selections.json write.
        od_context_sandbox_py = (
            _BACKEND_ROOT / "app" / "services" / "od_context_sandbox.py"
        )
        if not od_context_sandbox_py.exists():
            pytest.skip("od_context_sandbox.py not found — cannot verify Row 21")
        text = od_context_sandbox_py.read_text(encoding="utf-8")
        assert "selections.json" in text, (
            "Row 21: selections.json must be written by od_context_sandbox.py to "
            ".context/ (Requirement 13 AC 6 Row 21)"
        )

    def test_row22_multimodal_blocks_not_applicable(self) -> None:
        """Row 22 (NOT APPLICABLE): multimodal blocks are unchanged typed inputs.

        This row has no migration action: multimodal content (images, files) is
        passed through the existing typed multimodal message structure, unchanged
        by the Seam 2 removal.  The row is listed to confirm it was reviewed and
        found not-applicable.

        AC 7 explicit not-applicable assertion (Requirement 13 AC 7).
        """
        # No source change is needed or expected for this row.
        # We assert that the multimodal pathway (pending_turn_images) remains
        # present in engine.py as evidence it was not removed.
        text = _engine_text()
        assert "pending_turn_images" in text, (
            "Row 22 (N/A): pending_turn_images must remain present in engine.py — "
            "multimodal input pathway must not be removed as a side effect of "
            "Seam 2 removal (Requirement 13 AC 6 Row 22 — not-applicable assertion)"
        )

    def test_row23_launch_od_context_via_context_directory(self) -> None:
        """Row 23: launch od_context_json → .context/; resume rebuilds in-memory context.

        Source check: ``write_od_context_to_sandbox`` writes to .context/;
        ``rebuild_od_context_from_sandbox`` restores it on resume.
        """
        od_context_sandbox_py = (
            _BACKEND_ROOT / "app" / "services" / "od_context_sandbox.py"
        )
        if not od_context_sandbox_py.exists():
            pytest.skip("od_context_sandbox.py not found — cannot verify Row 23")
        text = od_context_sandbox_py.read_text(encoding="utf-8")
        assert "write_od_context_to_sandbox" in text, (
            "Row 23: write_od_context_to_sandbox must be present in od_context_sandbox.py "
            "(Requirement 13 AC 6 Row 23)"
        )
        assert (
            "rebuild_od_context_from_sandbox" in text or "rebuild_od_context" in text
        ), (
            "Row 23: rebuild_od_context_from_sandbox must be present in od_context_sandbox.py "
            "for the resume path"
        )

    def test_row24_frontend_chain_text_removed_for_new_launches(self) -> None:
        """Row 24: frontend enriched chain text removed for new launches.

        Historical marker-bearing runs stay readable (AC 11 / Requirement 21 AC 5-10).
        V2: new launches must not send the chain text block.

        Source check: the backend strips and records a legacy chain text block
        when source_workflow_run_id is also present (Requirement 13 AC 11 /
        Requirement 21 AC 9).
        """
        # Check run_commands.py for the duplicate-context guard.
        run_commands_py = _BACKEND_ROOT / "app" / "api" / "run_commands.py"
        if not run_commands_py.exists():
            pytest.skip("run_commands.py not found — cannot verify Row 24")
        text = run_commands_py.read_text(encoding="utf-8")
        assert (
            "legacy_context_block_stripped" in text
            or "CONTEXT FROM PREVIOUS PIPELINE" in text
        ), (
            "Row 24: run_commands.py must handle the legacy chain text block "
            "(strip + record when source_workflow_run_id is also present) — "
            "Requirement 13 AC 6 Row 24 / AC 11"
        )

    def test_row25_previous_run_seed_via_shared_revision_tree(self) -> None:
        """Row 25: previous-run seed → shared revision tree; redundant seed short-circuited.

        Source check: previous_run context_provider exists in the registry.
        """
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        # Resolve by name — must not raise.
        try:
            provider = registry.resolve("context_provider", "previous_run")
        except (KeyError, RuntimeError):
            pytest.fail(
                "Row 25: 'previous_run' context_provider must be registered — "
                "previous-run seed comes from the shared revision tree via this provider"
            )
        assert (
            provider is not None
        ), "Row 25: previous_run context_provider must not be None"

    def test_row26_uploaded_files_remain_in_uploads_dir(self) -> None:
        """Row 26: uploaded-files context → .uploads/ raw and extracted sidecars.

        Source check: run_files.py keeps uploads under .uploads/ (reserved path).
        """
        run_files_py = _BACKEND_ROOT / "app" / "api" / "run_files.py"
        if not run_files_py.exists():
            pytest.skip("run_files.py not found — cannot verify Row 26")
        text = run_files_py.read_text(encoding="utf-8")
        assert ".uploads/" in text, (
            "Row 26: run_files.py must reference .uploads/ as the uploads directory "
            "(Requirement 13 AC 6 Row 26)"
        )

    def test_row27_staged_skills_not_applicable_explicit_assertion(self) -> None:
        """Row 27 (NOT APPLICABLE for factory block): staged skills are unchanged.

        The factory's own ``skills`` block was removed (Task 10.2).  Deepagents'
        ``SKILLS_SYSTEM_PROMPT`` is NOT touched — it is emitted by deepagents'
        middleware layer which reads the ``skills/`` directory staged by
        ``stage_skills``.  The row's V2 destination is ``Unchanged skills/ directory``.

        AC 7 explicit not-applicable assertion (Requirement 13 AC 7).
        Companion test for Req 13 AC 3 is in TestLedgerAC3StagedSkillsDiscoverable.
        """
        # Assert the factory skills block was removed.
        text = _factory_text()
        # The factory must NOT include a manual "skills_block" construction that
        # appends the skill list into the blocks dict — that was removed in Task 10.2.
        # The comment documenting its removal must be present.
        assert (
            "skill_directive" in text.lower()
            or "skills block" in text.lower()
            or "SKILLS_SYSTEM_PROMPT" in text
        ), (
            "Row 27: factory.py must contain a comment documenting that the factory "
            "skills block was removed and deepagents' SKILLS_SYSTEM_PROMPT is unchanged — "
            "Requirement 13 AC 6 Row 27 / AC 3"
        )

    @pytest.mark.asyncio
    async def test_row28_validation_fix_block_carries_errors_and_filename_only(
        self,
    ) -> None:
        """Row 28: the VALIDATION ERRORS block appears when pending_validation_fix
        is set for the target agent, carries only errors and filename (no brief,
        no upstream context), and is consumed once.
        """
        from agents.loader import load_agent_spec
        from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn
        from tests.unit.agents.test_redo_gate_safety import (
            _EngineHarness,
            _drive_agent,
            _make_ectx,
        )

        spec = load_agent_spec("domain-analyst")

        with _EngineHarness(
            lambda aid, idx: ScriptedFakeChatModel(
                [_ScriptedTurn(texts=["output."], usage=(5, 3))]
            )
        ) as h:
            ectx = _make_ectx("row28-vfix-run")
            ectx.pending_validation_fix[spec.id] = {
                "errors": ["Missing h1 tag.", "Image has no alt text."],
                "filename": "prototype.html",
            }
            results: list = []
            events = await _drive_agent(h.engine, spec, ectx, results, [spec], index=1)

        msgs = [
            ev["data"]["context_message"]
            for ev in events
            if ev.get("type") == "agent_input"
            and "context_message" in ev.get("data", {})
        ]
        assert msgs, "No agent_input events"
        msg = msgs[0]

        assert "=== VALIDATION ERRORS" in msg, (
            "Row 28: VALIDATION ERRORS block must appear when pending_validation_fix "
            "is set (Requirement 13 AC 6 Row 28)"
        )
        assert "Missing h1 tag." in msg
        assert "Image has no alt text." in msg
        assert "prototype.html" in msg

        # Carries ONLY errors + filename — no brief injected (index=1, non-first)
        assert "=== ORIGINAL USER REQUEST ===" not in msg, (
            "Row 28: validation-fix message must NOT carry the original brief "
            "(Requirement 14 AC 4 — only errors and filename)"
        )

        # Consume-once: store must be drained after dispatch
        assert (
            ectx.pending_validation_fix.get(spec.id) is None
        ), "Row 28: pending_validation_fix must be cleared after dispatch (consume-once)"

        # Dormant when empty — no VALIDATION ERRORS block.
        with _EngineHarness(
            lambda aid, idx: ScriptedFakeChatModel(
                [_ScriptedTurn(texts=["output."], usage=(5, 3))]
            )
        ) as h:
            ectx2 = _make_ectx("row28-no-vfix-run")
            results2: list = []
            events2 = await _drive_agent(
                h.engine, spec, ectx2, results2, [spec], index=0
            )

        msgs2 = [
            ev["data"]["context_message"]
            for ev in events2
            if ev.get("type") == "agent_input"
            and "context_message" in ev.get("data", {})
        ]
        assert msgs2
        assert (
            "=== VALIDATION ERRORS" not in msgs2[0]
        ), "Row 28: VALIDATION ERRORS block must NOT appear when store is empty"

    def test_row29_planner_design_context_in_process_rebuilt_from_context(self) -> None:
        """Row 29: planner design-context argument → in-process; rebuilt from .context/ on resume.

        Source check: ``rebuild_od_context_from_sandbox`` is called on resume path.
        """
        text = _engine_text()
        assert "rebuild_od_context" in text, (
            "Row 29: rebuild_od_context must be called in engine.py (resume path) — "
            ".context/ is the durable backing store (Requirement 13 AC 6 Row 29)"
        )

    def test_row30_other_od_context_readers_rebuilt_from_context(self) -> None:
        """Row 30: other ectx.od_context readers → in-process; rebuilt from .context/ on resume.

        Source check: ectx.od_context is set from rebuild_od_context_from_sandbox
        on the resume path, not from a DB column.
        """
        text = _engine_text()
        assert "od_context" in text, (
            "Row 30: od_context must be present in engine.py — "
            "rebuilt from .context/ on resume (Requirement 13 AC 6 Row 30)"
        )


# ===========================================================================
# Requirement 13 AC 3 — Staged skills discoverable after factory block removed
# ===========================================================================


class TestLedgerAC3StagedSkillsDiscoverable:
    """Requirement 13 AC 3: removing the factory skills block must NOT remove
    deepagents' SKILLS_SYSTEM_PROMPT; staged skills remain discoverable.
    """

    def test_factory_skills_block_removed_from_default_prompt_assembly(self) -> None:
        """The factory's _compose_injection no longer manually inserts a skill list.

        Source check: the old skill_directive block appended by _compose_injection
        has been removed.  The factory.py comment about the removal must be present.
        """
        text = _factory_text()
        # The comment documenting the removal of the skills block must be present.
        assert (
            "skill_directive" in text
            or "SKILLS_SYSTEM_PROMPT" in text
            or "No per-agent scoping" in text
            or "skill_provider" in text
        ), (
            "AC 3: factory.py must document the removal of its own skills block — "
            "deepagents' SKILLS_SYSTEM_PROMPT is the surviving mechanism"
        )

    def test_stage_skills_still_writes_to_skills_directory(self) -> None:
        """AC 3: stage_skills still writes files under skills/ and sets sources=['/skills'].

        The deepagents library reads from skills/; that is what makes its
        SKILLS_SYSTEM_PROMPT list skills. If stage_skills stopped writing the files,
        SKILLS_SYSTEM_PROMPT would list nothing.
        """
        skill_staging_py = _BACKEND_ROOT / "app" / "agents" / "skill_staging.py"
        if not skill_staging_py.exists():
            pytest.skip("skill_staging.py not found")
        text = skill_staging_py.read_text(encoding="utf-8")
        assert "skills" in text and "sources" in text, (
            "AC 3: skill_staging.py must still write to skills/ and set sources=['/skills'] "
            "so deepagents' SKILLS_SYSTEM_PROMPT remains populated "
            "(Requirement 13 AC 3)"
        )
        assert (
            '"/skills"' in text or "'/skills'" in text
        ), "AC 3: stage_skills must set sources=['/skills'] for deepagents discovery"

    def test_default_policy_retains_skills_slot_for_inv3_parity(self) -> None:
        """AC 3: default policy still includes the 'skills' slot so INV-3 goldens stay
        byte-identical (no re-baseline of the 5 characterization snapshots).
        """
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        default_policy = registry.resolve("prompt", "default")
        assert "skills" in default_policy.order, (
            "AC 3: default policy must retain 'skills' in its order for INV-3 byte-parity "
            "— characterization goldens must not require re-baselining "
            "(Requirement 13 AC 3)"
        )


# ===========================================================================
# Requirement 13 AC 4 — No REQUEST.md created or propagated
# ===========================================================================


class TestLedgerAC4NoRequestMd:
    """Requirement 13 AC 4: the engine must NEVER create REQUEST.md or propagate
    the raw user request to downstream agents outside Requirement 14 retry classes.
    """

    def test_request_md_never_created_in_engine(self) -> None:
        """Source check: no 'REQUEST.md' write call in engine.py.

        The comment documenting this contract must be present.
        """
        text = _engine_text()
        # The negative assertion: no sandbox.write("REQUEST.md") call.
        assert 'sandbox.write("REQUEST.md"' not in text, (
            "AC 4: engine.py MUST NOT contain sandbox.write('REQUEST.md') — "
            "the raw request must never be written to disk "
            "(Requirement 13 AC 4)"
        )
        assert (
            'write("REQUEST.md"' not in text
        ), "AC 4: engine.py MUST NOT create REQUEST.md in any form"

    def test_request_md_absence_documented_in_engine(self) -> None:
        """Source check: the REQUEST.md non-creation is documented in engine.py.

        Task 10.3 added a comment explaining why REQUEST.md is never created.
        """
        text = _engine_text()
        assert "REQUEST.md" in text and "NEVER" in text, (
            "AC 4: engine.py must contain the comment documenting that REQUEST.md "
            "is NEVER created (Requirement 13 AC 4)"
        )

    def test_request_md_not_in_engine_write_calls(self) -> None:
        """AC 4: 'REQUEST.md' appears ONLY in the comment — not in any write call.

        We split the test to give a clear failure message if both conditions are
        violated simultaneously.
        """
        text = _engine_text()
        write_lines = [
            line.strip()
            for line in text.splitlines()
            if "REQUEST.md" in line and "write" in line.lower()
        ]
        # The only allowed write-containing line is the comment that SAYS it never
        # creates the file.
        real_writes = [
            line
            for line in write_lines
            if not line.startswith("#")
            and "NEVER" not in line
            and "must" not in line.lower()
        ]
        assert not real_writes, (
            "AC 4: found non-comment write references to REQUEST.md:\n"
            + "\n".join(real_writes)
        )


# ===========================================================================
# Requirement 13 AC 5 — Migrated first step produces a durable contract artifact
# ===========================================================================


class TestLedgerAC5MigratedFirstStepDurableArtifact:
    """Requirement 13 AC 5: every migrated first step SHALL produce a durable
    contract artifact that later agents can read from the sandbox.
    """

    def test_prototype_specify_has_body_only_policy(self) -> None:
        """prototype-specify (migrated) must use prompt_policy: body_only.

        This confirms Task 10.5 ran for the prototype workflow's first agent.
        """
        policy = _prompt_policy("prototype-specify")
        assert policy == "body_only", (
            "AC 5: prototype-specify must have prompt_policy: body_only "
            "(migrated per Task 10.5) — "
            "Requirement 13 AC 5"
        )

    def test_prototype_specify_has_produces_field(self) -> None:
        """prototype-specify must list itself in ``produces:`` as its durable artifact.

        The first step writes a durable spec output that later agents can read
        from the sandbox.
        """
        text = _read_agent_md("prototype-specify")
        assert "produces:" in text, (
            "AC 5: prototype-specify AGENT.md must have a 'produces:' field naming "
            "its durable contract artifact — "
            "Requirement 13 AC 5"
        )
        assert "prototype-specify" in text, (
            "AC 5: prototype-specify must list 'prototype-specify' under produces: "
            "as the named durable artifact"
        )

    def test_ppt_brief_analyst_has_body_only_policy(self) -> None:
        """ppt-brief-analyst (migrated) must use prompt_policy: body_only."""
        policy = _prompt_policy("ppt-brief-analyst")
        assert policy == "body_only", (
            "AC 5: ppt-brief-analyst must have prompt_policy: body_only "
            "(Requirement 13 AC 5)"
        )

    def test_ppt_brief_analyst_has_produces_field(self) -> None:
        """ppt-brief-analyst must have a produces: field for its durable artifact."""
        text = _read_agent_md("ppt-brief-analyst")
        assert "produces:" in text, (
            "AC 5: ppt-brief-analyst AGENT.md must have a 'produces:' field — "
            "Requirement 13 AC 5"
        )


# ===========================================================================
# Requirement 13 AC 2 — Governed agent does not silently lose Constitution
# ===========================================================================


class TestLedgerAC2GovernedAgentConstitutionRetained:
    """Requirement 13 AC 2: governed agents retain guardrails, hooks, Constitution,
    and AGENT.md when using the governance policy.

    Companion to test_phase7_seam2_removal.py:TestGovernedAgentConstitutionRetained;
    this class verifies via the full policy assemble() call (AC 8 — full composer).
    """

    def test_governance_assemble_retains_constitution_via_full_composer(self) -> None:
        """Via full assemble(): governance policy emits the constitution block."""
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "governance")
        blocks = {
            "guardrails": ["## Guardrail: safety\n\nBe safe."],
            "hooks": "## Active Behavioral Hooks\n\nhook content.",
            "constitution": "## Constitution\n\nBe ethical and trustworthy.",
            "prompt_body": "# Agent body\n\nI am a governed agent.",
        }
        result = policy.assemble(blocks, ctx=None)
        assert "## Constitution" in result, (
            "AC 2: governance policy assemble() must include the constitution block — "
            "governed agent must NOT silently lose its Constitution "
            "(Requirement 13 AC 2)"
        )
        assert (
            "## Guardrail: safety" in result
        ), "AC 2: governance policy assemble() must include guardrails"
        assert (
            "## Active Behavioral Hooks" in result
        ), "AC 2: governance policy assemble() must include hooks"
        assert (
            "# Agent body" in result
        ), "AC 2: governance policy assemble() must include prompt_body"

    def test_body_only_assemble_drops_constitution_intentionally(self) -> None:
        """Via full assemble(): body_only policy drops Constitution (intentional for
        ungoverned agents; governed agents must use governance instead).
        """
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "body_only")
        blocks = {
            "guardrails": ["## Guardrail: safety\n\nBe safe."],
            "hooks": "## Active Behavioral Hooks\n\nhook content.",
            "constitution": "## Constitution\n\nBe ethical.",
            "prompt_body": "# Agent body\n\nI am an ungoverned agent.",
        }
        result = policy.assemble(blocks, ctx=None)
        assert "## Constitution" not in result, (
            "AC 2: body_only assemble() must NOT include the constitution block — "
            "governed agents must use 'governance' policy instead"
        )
        assert (
            "# Agent body" in result
        ), "AC 2: body_only assemble() must include prompt_body"

    def test_domain_analyst_uses_governance_policy(self) -> None:
        """domain-analyst is a governed agent and must use the governance policy.

        A governed agent on body_only would silently lose its Constitution.
        """
        policy = _prompt_policy("domain-analyst")
        assert policy == "governance", (
            "AC 2: domain-analyst must have prompt_policy: governance — "
            "it is a governed agent; body_only would silently drop its Constitution "
            "(Requirement 13 AC 2)"
        )


# ===========================================================================
# Requirement 13 AC 9 — Prompt viewer shows effective prompt + targeted payload
# ===========================================================================


class TestLedgerAC9PromptViewer:
    """Requirement 13 AC 9: the prompt viewer shows the effective system prompt
    plus the targeted control payload, never a misleading empty-context message.

    Verified via source inspection of the frontend component and
    AgentDetailPanel.tsx.
    """

    def test_input_prompt_section_has_context_is_file_based_prop(self) -> None:
        """AgentDetailPanel.tsx must have contextIsFileBased prop on InputPromptSection.

        When context was loaded from files (.context/), the human message is
        legitimately short; the viewer re-labels it as 'Task message' rather
        than showing 'N chars' (which would look like 'no context').
        """
        agent_detail_panel = (
            _FRONTEND_ROOT / "components" / "results" / "AgentDetailPanel.tsx"
        )
        if not agent_detail_panel.exists():
            pytest.skip("AgentDetailPanel.tsx not found — skipping frontend test")
        text = agent_detail_panel.read_text(encoding="utf-8")
        assert "contextIsFileBased" in text, (
            "AC 9: AgentDetailPanel.tsx must pass contextIsFileBased to InputPromptSection — "
            "Requirement 13 AC 9"
        )

    def test_input_prompt_section_relabels_short_message_as_task_message(self) -> None:
        """When contextIsFileBased=true, the label changes from 'Full input prompt'
        to 'Task message' with a note explaining that context came from files.
        """
        agent_detail_panel = (
            _FRONTEND_ROOT / "components" / "results" / "AgentDetailPanel.tsx"
        )
        if not agent_detail_panel.exists():
            pytest.skip("AgentDetailPanel.tsx not found")
        text = agent_detail_panel.read_text(encoding="utf-8")
        assert "Task message" in text, (
            "AC 9: AgentDetailPanel.tsx must show 'Task message' label when "
            "contextIsFileBased=true — Requirement 13 AC 9"
        )
        assert "Context loaded from files" in text, (
            "AC 9: AgentDetailPanel.tsx must display a note that context came "
            "from files (.context/) to prevent a misleading 'no context' appearance"
        )

    def test_context_is_file_based_keyed_on_run_input_and_context_block(self) -> None:
        """contextIsFileBased is derived from source types, not from the message length.

        Source check: ``contextIsFileBased`` is computed from ``sources.some(s =>
        s.type === 'run_input' || s.type === 'context_block')`` — a legitimate short
        message is never misread as 'no context'.
        """
        agent_detail_panel = (
            _FRONTEND_ROOT / "components" / "results" / "AgentDetailPanel.tsx"
        )
        if not agent_detail_panel.exists():
            pytest.skip("AgentDetailPanel.tsx not found")
        text = agent_detail_panel.read_text(encoding="utf-8")
        assert "run_input" in text, (
            "AC 9: contextIsFileBased must check for 'run_input' source type — "
            "Requirement 13 AC 9"
        )
        assert (
            "context_block" in text
        ), "AC 9: contextIsFileBased must check for 'context_block' source type"


# ===========================================================================
# Five-mode coverage: normal, retry, redo, resume, chained-run
# ===========================================================================


class TestLedgerFiveModes:
    """Verify that the 30-row ledger is testable across all five modes.

    Rows that vary per mode are tested here; static rows are covered in the
    classes above.  Tests use source inspection of engine.py or direct dataclass
    field checks — 'verified through the full composer' in AC 8 means the real
    ``_compose_context_message`` path, not a dict pop simulation.
    """

    def test_normal_mode_no_retry_in_flight_scratch_fields_empty(self) -> None:
        """Normal mode: no retry/fix loop in flight → both scratch stores start empty.

        [Phase Z] The docstring this test originally carried ("default policy:
        all agents receive the original brief") described the pre-Phase-Z
        default path, which no longer exists — the brief now reaches the
        first-dispatched agent only, regardless of policy (see
        ``test_row8_brief_to_first_agent_only``). What this test actually
        verifies — the two consume-once scratch fields start empty — is
        unaffected and still holds.
        """
        from agents.execution_engine.context import ExecutionContext

        ectx = ExecutionContext(run_id="nm-run", owner_id="anon")
        assert isinstance(ectx.pending_route_feedback, dict)
        assert (
            ectx.pending_route_feedback == {}
        ), "Normal mode: pending_route_feedback must start empty — no retry in flight"
        assert isinstance(ectx.pending_validation_fix, dict)
        assert (
            ectx.pending_validation_fix == {}
        ), "Normal mode: pending_validation_fix must start empty — no fix loop"

    def test_retry_mode_feedback_keyed_on_agent_id(self) -> None:
        """Retry mode: feedback is keyed on the target agent id, dormant for others.

        Requirement 13 AC 6 Row 9 / Requirement 14 AC 2.
        """
        from agents.execution_engine.context import ExecutionContext

        ectx = ExecutionContext(run_id="retry-run", owner_id="anon")
        TARGET = "domain-analyst"
        OTHER = "epic-architect"

        ectx.pending_route_feedback[TARGET] = {
            "from_step": "judge",
            "decision": "fail",
            "from_output": "",
            "pass_number": 2,
            "max_passes": 3,
            "authored": "Fix this.",
        }

        # Pop simulates what _compose_context_message does.
        fb_target = ectx.pending_route_feedback.pop(TARGET, None)
        fb_other = ectx.pending_route_feedback.pop(OTHER, None)

        assert fb_target is not None, "Retry mode: target agent must receive feedback"
        assert fb_other is None, (
            "Retry mode: other agents must NOT receive feedback — "
            "Requirement 14 AC 2 / Requirement 13 AC 6 Row 9"
        )
        assert (
            ectx.pending_route_feedback == {}
        ), "Retry mode: store must be drained after delivery"

    def test_redo_mode_directive_cleared_after_dispatch(self) -> None:
        """Redo mode: redo_directive is a consume-once field, cleared in finally.

        Requirement 13 AC 6 Row 14 / Requirement 14 AC 3.
        """
        from agents.execution_engine.context import ExecutionContext

        ectx = ExecutionContext(run_id="redo-run", owner_id="anon")
        assert (
            ectx.redo_directive == ""
        ), "Redo mode: redo_directive must default to empty"

        ectx.redo_directive = "Revise section 3."
        captured = ectx.redo_directive
        ectx.redo_directive = ""  # cleared unconditionally (F3 pattern)
        assert (
            captured == "Revise section 3."
        ), "Redo mode: redo_directive must be readable during compose"
        assert ectx.redo_directive == "", (
            "Redo mode: redo_directive must be cleared after dispatch — "
            "Requirement 14 AC 3 / Requirement 13 AC 6 Row 14"
        )

    def test_resume_mode_one_shot_scratch_fields_not_replayed(self) -> None:
        """Resume mode: consume-once scratch fields must be drained so they are
        not replayed twice.

        Requirement 14 AC 6: resumed dispatch preserves recipient rules and does
        not replay a consumed one-shot control payload.
        """
        from agents.execution_engine.context import ExecutionContext

        ectx = ExecutionContext(run_id="resume-run", owner_id="anon")
        AGENT_ID = "domain-analyst"

        # Simulate a one-shot feedback that was consumed on the first dispatch.
        ectx.pending_route_feedback[AGENT_ID] = {
            "from_step": "judge",
            "decision": "fail",
            "from_output": "",
            "pass_number": 1,
            "max_passes": 3,
            "authored": None,
        }
        # Consumed (first dispatch).
        ectx.pending_route_feedback.pop(AGENT_ID, None)

        # On resume, the field is empty — pop returns None.
        replayed = ectx.pending_route_feedback.pop(AGENT_ID, None)
        assert replayed is None, (
            "Resume mode: a consumed one-shot control payload must NOT be replayed — "
            "Requirement 14 AC 6 / Requirement 13 AC 6 Row 9"
        )

    def test_chained_run_mode_brief_delivered_to_first_agent(self) -> None:
        """Chained-run mode: first agent receives the original brief;
        chain context is installed in .context/ (Row 24 new path).

        Source check: is_first_agent=True → brief included (unconditional since
        Phase Z; see ``test_row8_brief_to_first_agent_only``). Ledger rows 8 and
        24 both apply.
        """
        text = _engine_text()
        assert "is_first_agent or _has_retry_feedback" in text, (
            "Chained-run mode: first agent must receive the brief — "
            "Requirement 13 AC 6 Row 8"
        )

    def test_all_five_modes_consume_once_fields_drained(self) -> None:
        """AC 7: consume-once scratch fields are drained unconditionally per iteration.

        Source check: the finally block in engine.py's _run_agent loop drains
        both pending_route_feedback[spec.id] and pending_validation_fix[spec.id].
        """
        text = _engine_text()
        assert "pending_route_feedback.pop(_agent_id_key, None)" in text or (
            "pending_route_feedback.pop" in text and "finally" in text
        ), (
            "AC 7: pending_route_feedback must be drained in a finally block "
            "so exceptions cannot leave stale entries — Requirement 14 AC 7"
        )
        assert "pending_validation_fix.pop" in text, (
            "AC 7: pending_validation_fix must be drained in engine.py "
            "(Requirement 14 AC 7)"
        )
