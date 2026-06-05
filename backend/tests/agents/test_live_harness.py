"""tests/agents/test_live_harness.py — OFFLINE self-test for the Phase-8 harness.

Proves the ``tests/agents/live_harness`` machinery is correct by driving all three
worlds with a ``ScriptedFakeChatModel`` (NOT live) — so it runs with **zero Bedrock
cost and no AWS credentials** and commits green. This is the foundation gate: if the
capture format / drivers are wrong here, every later Phase-8 task (validator, live
suite, resume) inherits the bug.

It asserts the :class:`~tests.agents.live_harness.CaptureResult` is WELL-FORMED for
each world:
  * engine (``user_stories`` — text-only, deterministic): ordered event vocabulary,
    bracketed agent envelopes, a non-empty deliverable, tokens summed from the
    scripted ``usage``, a per-agent breakdown, ``completed`` True, no error;
  * chat: the ``phase_start``/``stream``/``phase_end`` envelope + the trailing 10-key
    ``complete``, ``final_output`` is the 10-key dict, ``completed`` True;
  * handoff (``coding`` mode, agents scripted via the ``model`` switch): the full
    setup→clone→code→test→compliance→commit→push→PR stream, ``pipeline_complete``
    last, ``final_output`` carries ``resolved_mode``/``branch_name``/``pr_url``.

It does NOT run any live model (``RUN_LIVE_BEDROCK`` is never set here); the live
smoke is run separately by the orchestrator. A couple of light tests also assert the
opt-in gate + cost math behave without creds.
"""

from __future__ import annotations

import os

import pytest

from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn, _scripts_for
from tests.agents.live_harness import (
    CaptureResult,
    TokenTotals,
    cost_usd,
    drive_chat,
    drive_engine_pipeline,
    drive_handoff,
    live_enabled,
    live_skip_reason,
)


# ---------------------------------------------------------------------------
# Scripted models — a single shared instance is injected for ALL agents in a
# world (the documented single-instance contract). ScriptedFakeChatModel falls
# back to its LAST turn once the call index exceeds the turn list, so one
# text+usage turn serves every text-only agent in a pipeline deterministically.
# ---------------------------------------------------------------------------


def _text_model(t_in: int = 12, t_out: int = 7) -> ScriptedFakeChatModel:
    """A pure-text scripted model (one turn, with usage) reused by every agent."""
    return ScriptedFakeChatModel(
        [_ScriptedTurn(texts=["harness scripted output. ", "line two."], usage=(t_in, t_out))]
    )


# ===========================================================================
# World 1 — engine (user_stories): the canonical capture is well-formed.
# ===========================================================================


class TestEngineWorldOffline:
    @pytest.mark.asyncio
    async def test_user_stories_capture_is_well_formed(self) -> None:
        result = await drive_engine_pipeline(
            "user_stories",
            model=_text_model(),
            fake_planner=True,  # skip the planner LLM call (offline self-test)
        )

        # ── Shape: it's a CaptureResult for the engine world. ────────────────
        assert isinstance(result, CaptureResult)
        assert result.world == "engine"
        assert result.label == "user_stories"
        assert result.run_id and result.run_id.startswith("harness-user_stories-")

        # ── Events captured, in order, with a sane vocabulary. ───────────────
        assert result.events, "no engine events captured"
        types = result.event_types()
        assert types[0] == "workflow_validated"
        assert "pipeline_start" in types
        assert types[-1] == "pipeline_complete"
        # Every agent_start pairs with an agent_complete (text pipeline → no errors).
        assert types.count("agent_start") == types.count("agent_complete") > 0

        # ── Completion + no error. ──────────────────────────────────────────
        assert result.completed is True
        assert result.error is None
        assert result.raised is None
        assert result.gated is False  # no gate_agent_ids supplied

        # ── Deliverable present (the final_output string). ──────────────────
        assert result.deliverable is not None
        assert isinstance(result.deliverable, str) and result.deliverable.strip()
        assert result.final_output == result.deliverable

        # ── Tokens summed from the scripted usage; per-agent breakdown present. ─
        assert result.tokens.total == result.tokens.input + result.tokens.output
        assert result.tokens.total > 0, "scripted usage must sum to a non-zero total"
        assert result.per_agent_tokens, "expected a per-agent token breakdown"
        # The per-agent totals reconcile to the run total.
        agg_in = sum(t.input for t in result.per_agent_tokens.values())
        agg_out = sum(t.output for t in result.per_agent_tokens.values())
        assert (agg_in, agg_out) == (result.tokens.input, result.tokens.output)
        # One entry per pipeline agent (user_stories has 6).
        assert len(result.per_agent_tokens) == result.event_types().count("agent_complete")

        # ── Cost is computed from tokens at Haiku pricing (non-negative). ────
        assert result.cost_usd() >= 0.0

    @pytest.mark.asyncio
    async def test_globals_restored_after_engine_drive(self) -> None:
        """The drive restores ALL patched globals (it runs repeatedly per process)."""
        import agents.execution_engine.engine as engine_mod
        import agents.factory as factory_mod
        from app.core.config import settings

        before = {
            "factory_create_runner": factory_mod.create_runner,
            "engine_create_runner": engine_mod.create_runner,
            "always_clarify": engine_mod.ALWAYS_CLARIFY,
            "runs_root": settings.RUNS_ROOT,
        }

        await drive_engine_pipeline("user_stories", model=_text_model(), fake_planner=True)

        assert factory_mod.create_runner is before["factory_create_runner"]
        assert engine_mod.create_runner is before["engine_create_runner"]
        assert engine_mod.ALWAYS_CLARIFY == before["always_clarify"]
        assert settings.RUNS_ROOT == before["runs_root"]

    @pytest.mark.asyncio
    async def test_repeated_drives_are_independent(self) -> None:
        """Two drives in one process yield distinct run ids + independent captures."""
        r1 = await drive_engine_pipeline("user_stories", model=_text_model(), fake_planner=True)
        r2 = await drive_engine_pipeline("user_stories", model=_text_model(), fake_planner=True)
        assert r1.run_id != r2.run_id
        assert r1.completed and r2.completed
        # The state machine is a per-run singleton — a leaked/reused id would error.
        assert r2.error is None and r2.raised is None

    @pytest.mark.asyncio
    async def test_prototype_via_per_agent_model_factory(self) -> None:
        """A PER-AGENT model factory drives a HETEROGENEOUS pipeline (prototype).

        ``prototype-build`` needs a tool-calling script while the others are
        text-only — the ``model=(agent_id)->BaseChatModel`` callable reuses
        ``_scripts_for`` so each agent gets its own script. Exercises the richer
        engine path: ``tool_call`` + ``task_progress`` + a disk deliverable
        (``prototype.html``) read back at the end.
        """
        result = await drive_engine_pipeline(
            "prototype",
            model=lambda aid: ScriptedFakeChatModel(_scripts_for(aid)),
            fake_planner=True,
        )
        assert result.completed is True
        assert result.error is None
        types = result.event_types()
        assert "tool_call" in types
        assert "task_progress" in types
        assert types[-1] == "pipeline_complete"
        # The deliverable is the prototype.html read back from the run sandbox.
        assert result.deliverable and "<" in result.deliverable
        # All four prototype agents contributed tokens.
        assert {"prototype-specify", "prototype-plan", "prototype-build", "prototype-validate"} <= set(
            result.per_agent_tokens
        )


# ===========================================================================
# Engine inter-agent gate — pause (review_gate_ready) → auto-resume → complete.
# Proves the concurrency seam T3 builds its gate-on scenario on.
# ===========================================================================


class TestEngineGate:
    @pytest.mark.asyncio
    async def test_gate_on_pauses_then_auto_resumes_to_complete(self) -> None:
        """gate_agent_ids gates an agent → review_gate_ready fires → approve → complete."""
        result = await drive_engine_pipeline(
            "user_stories",
            model=_text_model(),
            fake_planner=True,
            gate_agent_ids=["domain-analyst"],  # gate the first agent
        )
        types = result.event_types()
        # The gate FIRED (pause) ...
        assert result.gated is True
        assert types.count("review_gate_ready") == 1
        # ... and was APPROVED (resume) ...
        assert types.count("review_gate_approved") == 1
        # ... and the run still reached completion.
        assert result.completed is True
        assert types[-1] == "pipeline_complete"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_gates_off_never_gates(self) -> None:
        """Empty gate_agent_ids ⇒ no review gate fires (the gates-off scenario)."""
        result = await drive_engine_pipeline(
            "user_stories", model=_text_model(), fake_planner=True, gate_agent_ids=()
        )
        types = result.event_types()
        assert result.gated is False
        assert "review_gate_ready" not in types
        assert result.completed is True

    @pytest.mark.asyncio
    async def test_custom_approver_is_honoured(self) -> None:
        """A caller-supplied approver is consulted for each gate (records the call)."""
        seen: list[str] = []

        def _approver(gate_key: str, data: dict):
            seen.append(gate_key)
            return True, None

        result = await drive_engine_pipeline(
            "user_stories",
            model=_text_model(),
            fake_planner=True,
            gate_agent_ids=["domain-analyst"],
            gate_approver=_approver,
        )
        assert result.completed is True
        assert seen and seen[0].endswith(":domain-analyst")


# ===========================================================================
# World 2 — chat (ChatRunner): the capture is well-formed.
# ===========================================================================


class TestChatWorldOffline:
    @pytest.mark.asyncio
    async def test_chat_capture_is_well_formed(self) -> None:
        # Discovery text mentions every deliverable keyword so _parse_output_selection
        # activates all phases (deterministic, exercises the full envelope).
        msg = "Build a full product with user stories, ppt, prototype and ui design."
        result = await drive_chat(msg, mode="default", model=_text_model())

        assert isinstance(result, CaptureResult)
        assert result.world == "chat"
        assert result.label == "default"

        # ── Envelope: phase_start/stream/phase_end then a single trailing complete. ─
        types = result.event_types()
        assert types, "no chat events captured"
        assert "phase_start" in types
        assert "stream" in types
        assert "phase_end" in types
        assert types[-1] == "complete"
        assert types.count("complete") == 1

        # ── completed + the structured 10-key final output. ─────────────────
        assert result.completed is True
        assert result.error is None
        assert isinstance(result.final_output, dict)
        assert set(result.final_output.keys()) == {
            "auth", "realtime", "dashboard", "discovery", "requirements",
            "user_stories", "ppt", "prototype", "ui_design", "ui_preview",
        }
        # Chat's artifact is the dict, not a string deliverable.
        assert result.deliverable is None

        # ── Tokens captured via the astream_with_usage tap. ─────────────────
        # The scripted model reports usage on each phase → the run total is > 0,
        # and the per-agent breakdown reconciles to it.
        assert result.tokens.total == result.tokens.input + result.tokens.output
        assert result.tokens.total > 0, "chat token tap must sum scripted usage"
        agg = sum(t.total for t in result.per_agent_tokens.values())
        assert agg == result.tokens.total

    @pytest.mark.asyncio
    async def test_chat_stream_events_carry_chunk_text(self) -> None:
        """``stream`` events carry chunk text; non-stream events have chunk=None."""
        result = await drive_chat(
            "stories and a prototype please", mode="default", model=_text_model()
        )
        for ev in result.events:
            assert set(ev.keys()) == {"type", "chunk", "section", "data"}
            if ev["type"] == "stream":
                assert ev["chunk"]
            else:
                assert ev["chunk"] is None


# ===========================================================================
# World 3 — handoff (run_handoff_pipeline, agents scripted via the model switch).
# ===========================================================================


class TestHandoffWorldOffline:
    @pytest.mark.asyncio
    async def test_handoff_coding_capture_is_well_formed(self) -> None:
        # A scripted model signals "run offline" → the 4 handoff agents are mocked
        # and handoff_github is faked (no network, no real git).
        result = await drive_handoff(mode="coding", model=_text_model())

        assert isinstance(result, CaptureResult)
        assert result.world == "handoff"
        assert result.label == "coding"  # resolved_mode off pipeline_complete

        # ── The full coding stream, terminating in pipeline_complete. ───────
        types = result.event_types()
        assert types, "no handoff events captured"
        assert types[-1] == "pipeline_complete"
        # The event vocabulary is the handoff WS envelope set.
        assert set(types) <= {
            "phase_start", "phase_end", "agent_thinking", "agent_complete",
            "agent_error", "pr_created", "pipeline_complete",
        }
        # Coding mode reaches the PR branch.
        assert "pr_created" in types

        # ── completed + the structured pipeline_output. ─────────────────────
        assert result.completed is True
        assert result.error is None
        assert result.raised is None
        assert isinstance(result.final_output, dict)
        out = result.final_output
        assert out["resolved_mode"] == "coding"
        assert out["branch_name"]
        assert out["pr_url"] and out["pr_number"]
        # Handoff cost is asserted by deliverable validity, not tokens.
        assert result.tokens == TokenTotals()

        # ── Every event is the WS envelope; handoff never token-streams. ────
        for ev in result.events:
            assert set(ev.keys()) == {"type", "chunk", "section", "data"}
            assert ev["chunk"] is None

    @pytest.mark.asyncio
    async def test_handoff_test_mode_omits_pr(self) -> None:
        """``test`` mode → no coding/commit/PR; pipeline_output omits PR fields."""
        result = await drive_handoff(mode="test", model=_text_model())
        assert result.completed is True
        types = result.event_types()
        assert "pr_created" not in types
        out = result.final_output
        assert out["resolved_mode"] == "test"
        assert out["edit_results"] == []
        assert "pr_url" not in out and "pr_number" not in out


# ===========================================================================
# Runner-level (tool) gate — capture_runner_stream + resume_paused_run.
# The Command(resume=…) seam T3 uses for tool-level HITL (distinct from the
# engine inter-agent gate above).
# ===========================================================================


class TestRunnerLevelGate:
    @pytest.mark.asyncio
    async def test_capture_then_resume_executes_gated_tool(self) -> None:
        import json

        from langchain_core.messages import ToolMessage
        from langchain_core.tools import tool
        from langgraph.checkpoint.memory import InMemorySaver

        from app.agents.deep_agent_runner import DeepAgentRunner
        from tests.agents.live_harness import capture_runner_stream, resume_paused_run

        @tool
        def report_task_complete(task_number: int, task_title: str, summary: str = "") -> str:
            """Report a task complete (gated for HITL in this test)."""
            return f"done {task_number} {task_title}"

        script = [
            _ScriptedTurn(
                texts=["working "],
                tool_calls=[
                    (
                        "report_task_complete",
                        json.dumps({"task_number": 1, "task_title": "Shell", "summary": "x"}),
                        "c1",
                    )
                ],
                usage=(11, 7),
            ),
            _ScriptedTurn(texts=["all done"], usage=(13, 5)),
        ]
        runner = DeepAgentRunner(
            system_prompt="worker",
            tools=[report_task_complete],
            model=ScriptedFakeChatModel(script),
            checkpointer=InMemorySaver(),
            thread_id="harness-runner-gate",
            interrupt_on={"report_task_complete": True},
        )

        # capture_runner_stream returns the events + the first gate event.
        events, gate = await capture_runner_stream(runner, "go")
        assert gate is not None, "armed runner must PAUSE at the gated tool"
        types = [e["type"] for e in events]
        assert "gate" in types and "done" not in types  # mutually exclusive

        # resume_paused_run issues Command(resume) (auto-counting the decisions).
        final = await resume_paused_run(runner)
        tool_msgs = [
            m
            for m in final.get("messages", [])
            if isinstance(m, ToolMessage) and getattr(m, "name", "") == "report_task_complete"
        ]
        assert tool_msgs, "the approved gated tool must execute after resume"
        state = await runner._graph.aget_state(runner.config)
        assert state.next == (), "resumed graph must reach a terminal state"


# ===========================================================================
# Opt-in gate + cost math — behave correctly WITHOUT credentials.
# ===========================================================================


class TestOptInAndCost:
    def test_live_disabled_without_opt_in(self) -> None:
        """With RUN_LIVE_BEDROCK unset, the live path is disabled with a reason."""
        # The harness must never have flipped the opt-in on import.
        assert os.getenv("RUN_LIVE_BEDROCK") != "1"
        assert live_enabled() is False
        reason = live_skip_reason()
        assert reason is not None
        assert "RUN_LIVE_BEDROCK" in reason

    def test_cost_usd_haiku_pricing(self) -> None:
        """cost_usd uses $0.25/M input + $1.25/M output (accepts TokenTotals or dict)."""
        # 1M input + 1M output = 0.25 + 1.25 = 1.50 USD.
        assert cost_usd(TokenTotals(input=1_000_000, output=1_000_000, total=2_000_000)) == pytest.approx(1.50)
        # Same via a plain dict (composes with CaptureResult.tokens.as_dict()).
        assert cost_usd({"input": 1_000_000, "output": 0}) == pytest.approx(0.25)
        assert cost_usd({"input": 0, "output": 1_000_000}) == pytest.approx(1.25)
        assert cost_usd(TokenTotals()) == 0.0


# ===========================================================================
# Regression — a CLARIFY_REQUIRED planner is auto-answered headlessly (no hang).
# This guards the exact failure the first live smoke surfaced: the REAL planner
# returned CLARIFY_REQUIRED, the engine ran ClarifyEngine, and (with no headless
# answerer) it blocked on the resume event for ~2h. drive_engine_pipeline now
# auto-answers questionnaire_ready with each question's recommended default.
# ===========================================================================


class TestClarifyAutoAnswerOffline:
    @pytest.mark.asyncio
    async def test_planner_clarify_required_is_auto_answered(self) -> None:
        """A forced CLARIFY_REQUIRED planner verdict is auto-answered → the run
        proceeds to completion instead of blocking on ClarifyEngine's resume
        event (deterministic, scripted model, zero Bedrock)."""
        from agents.execution_engine.engine import ExecutionEngine

        ctx = ExecutionEngine()._default_planning_context(
            "Build user stories for a task-management web app."
        )
        ctx["pipeline_type"] = "user_stories"
        ctx["execution_gate"] = "CLARIFY_REQUIRED"
        ctx["missing_information"] = ["topic", "target_audience"]

        result = await drive_engine_pipeline(
            "user_stories",
            model=lambda aid: ScriptedFakeChatModel(_scripts_for(aid)),
            planner_result=(ctx, "CLARIFY_REQUIRED"),
            auto_answer_clarify=True,
        )

        types = result.event_types()
        # Clarify actually fired AND was auto-answered (not skipped, not hung).
        assert "questionnaire_ready" in types, "clarify did not trigger"
        assert "questionnaire_complete" in types, "clarify was not auto-answered"
        # And the pipeline proceeded past the gate to completion.
        assert result.completed is True, f"run did not complete (error={result.error})"
        assert result.deliverable
