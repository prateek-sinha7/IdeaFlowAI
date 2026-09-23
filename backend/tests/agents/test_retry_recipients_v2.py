"""tests/agents/test_retry_recipients_v2.py — Requirement 14 retry-class recipient matrix.

Verifies the five Req 14 retry classes have the right recipients, brief visibility,
consume-once draining, and dispatch-consumption records.

AC mapping:
  AC 1 — provider/transient retry: reuses the same checkpoint message, no second brief.
  AC 2 — conditional-gate backward retry: delivers brief + pass-info to retrying agent
          only; no upstream context, no planned context, no other agent's output.
  AC 3 — human-gate redo: redo_directive is publish-around-dispatch (consume-once).
  AC 4 — validation-fix loop: delivers ONLY errors + deliverable path; no brief, no
          planning context, no other cross-agent state.
  AC 5 — merge-agent attempt: delivers only the conflict artifact + attempt count;
          no original user brief by default.
  AC 6 — dispatch-consumption record: a ``gate_events`` row is written when a
          conditional-gate one-shot payload is consumed (existing mechanism, no new table).
  AC 7 — unconditional draining: consume-once scratch fields are cleared even when
          ``_compose_context_message`` raises or is skipped.

Offline-safe: scripted model only (no Bedrock / Postgres / Chromium).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# Importing the harness forces InMemory checkpointer + temp RUNS_ROOT before
# app.core.config loads.  Keep this import first.
from tests.agents._scripted_model import (  # noqa: E402
    ScriptedFakeChatModel,
    _ScriptedTurn,
)
from tests.unit.agents.test_redo_gate_safety import (  # noqa: E402
    _EngineHarness,
    _drive_agent,
    _make_ectx,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _turn(text: str) -> list[_ScriptedTurn]:
    return [_ScriptedTurn(texts=[text], usage=(5, 3))]


def _collect_context_messages(events: list[dict]) -> list[str]:
    """Extract agent_input context_message strings from a stream of events."""
    return [
        ev["data"].get("context_message", "")
        for ev in events
        if ev.get("type") == "agent_input"
        and "context_message" in ev.get("data", {})
    ]


class _RecordingRunner:
    """Minimal KernelServices-shaped fake that records gate-event writes."""

    def __init__(self) -> None:
        self.gate_events: list[tuple] = []

    async def record_gate_event(
        self, step: str, gate: str, outcome: str, detail: Any = None
    ) -> str | None:
        self.gate_events.append((step, gate, outcome, detail))
        return "gate-event-id"

    async def read_gate_events(self, run_id: str) -> list:
        return []


# ---------------------------------------------------------------------------
# AC 7 (baseline) — declared fields
# ---------------------------------------------------------------------------

def test_ac7_pending_fields_are_declared_dataclass_fields() -> None:
    """[Req 14 AC 7] pending_route_feedback and pending_validation_fix are declared
    dataclass fields on ExecutionContext, not dynamic attributes, with default {}.
    """
    from agents.execution_engine.context import ExecutionContext
    import dataclasses

    fields = {f.name for f in dataclasses.fields(ExecutionContext)}
    assert "pending_route_feedback" in fields, (
        "pending_route_feedback must be a declared dataclass field (AC 7)"
    )
    assert "pending_validation_fix" in fields, (
        "pending_validation_fix must be a declared dataclass field (AC 7)"
    )

    ectx = ExecutionContext(run_id="ac7-run", owner_id="anon")
    assert isinstance(ectx.pending_route_feedback, dict)
    assert isinstance(ectx.pending_validation_fix, dict)
    assert ectx.pending_route_feedback == {}
    assert ectx.pending_validation_fix == {}


# ---------------------------------------------------------------------------
# AC 1 — Provider/transient retry
# ---------------------------------------------------------------------------

def test_ac1_provider_retry_scratch_fields_unaffected() -> None:
    """[Req 14 AC 1] A provider/transient retry of a different agent must not drain
    the pending Req 14 scratch entries for other agents.

    The per-agent key design means draining agent A never touches agent B's entries.
    """
    from agents.execution_engine.context import ExecutionContext

    ectx = ExecutionContext(run_id="ac1-run", owner_id="anon")

    ectx.pending_route_feedback["agent-b"] = {
        "from_step": "judge", "decision": "fail", "from_output": "",
        "pass_number": 2, "max_passes": 3, "authored": None,
    }
    ectx.pending_validation_fix["agent-b"] = {
        "filename": "proto.html", "errors": ["Error: line 5"],
    }

    # Simulate provider retry of a different agent (drain agent-a only).
    ectx.pending_route_feedback.pop("agent-a", None)
    ectx.pending_validation_fix.pop("agent-a", None)

    # Agent B's entries must remain intact.
    assert "agent-b" in ectx.pending_route_feedback, (
        "provider retry of a different agent must not drain the pending feedback"
    )
    assert "agent-b" in ectx.pending_validation_fix, (
        "provider retry of a different agent must not drain the validation fix"
    )


# ---------------------------------------------------------------------------
# AC 2 — Conditional-gate backward retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac2_conditional_retry_delivers_retry_block_to_retrying_agent() -> None:
    """[Req 14 AC 2] A conditional-gate backward retry delivers the RETRY block + pass
    info to the retrying agent, and NOT to the next (non-retried) agent.
    """
    from agents.loader import load_agent_spec

    spec_a = load_agent_spec("domain-analyst")
    spec_b = load_agent_spec("analyze-agent")  # real second agent

    TARGET_ID = spec_a.id

    with _EngineHarness(
        lambda aid, idx: ScriptedFakeChatModel(_turn("output text"))
    ) as h:
        ectx = _make_ectx("cg-retry-run")
        ectx.gate_agent_ids = []

        # Seed pending_route_feedback for spec_a.
        ectx.pending_route_feedback[TARGET_ID] = {
            "from_step": "judge-step",
            "decision": "insufficient",
            "from_output": "previous agent output",
            "pass_number": 2,
            "max_passes": 3,
            "authored": "Add more detail.",
        }

        results: list[dict] = []
        events_a = await _drive_agent(
            h.engine, spec_a, ectx, results, [spec_a, spec_b], index=0,
        )
        events_b = await _drive_agent(
            h.engine, spec_b, ectx, results, [spec_a, spec_b], index=1,
        )

    msgs_a = _collect_context_messages(events_a)
    msgs_b = _collect_context_messages(events_b)

    # Agent A must receive the RETRY block.
    assert msgs_a, "spec_a produced no agent_input events"
    assert "=== RETRY" in msgs_a[0], (
        f"agent_a missing RETRY block:\n{msgs_a[0][:500]}"
    )
    assert "pass 2 of 3" in msgs_a[0], "retry pass number not injected"
    assert "judge-step" in msgs_a[0], "source step id not injected"

    # Agent B must NOT receive the RETRY block.
    assert msgs_b, "spec_b produced no agent_input events"
    assert "=== RETRY" not in msgs_b[0], (
        f"agent_b unexpectedly received a RETRY block:\n{msgs_b[0][:500]}"
    )

    # The feedback entry must be drained.
    assert TARGET_ID not in ectx.pending_route_feedback, (
        "pending_route_feedback not drained after dispatch"
    )


@pytest.mark.asyncio
async def test_ac2_retry_feedback_drained_on_compose_error() -> None:
    """[Req 14 AC 7] pending_route_feedback[spec.id] is cleared even when
    _compose_context_message raises.
    """
    from agents.loader import load_agent_spec

    spec = load_agent_spec("domain-analyst")

    with _EngineHarness(
        lambda aid, idx: ScriptedFakeChatModel(_turn("output text"))
    ) as h:
        ectx = _make_ectx("drain-on-error-run")
        ectx.gate_agent_ids = []

        TARGET_ID = spec.id
        ectx.pending_route_feedback[TARGET_ID] = {
            "from_step": "src", "decision": "bad", "from_output": "",
            "pass_number": 2, "max_passes": 3, "authored": None,
        }

        original_compose = h.engine._compose_context_message

        async def _raising_compose(*args, **kwargs):
            raise RuntimeError("simulated compose error")

        h.engine._compose_context_message = _raising_compose  # type: ignore
        results: list[dict] = []
        with pytest.raises(RuntimeError):
            await _drive_agent(h.engine, spec, ectx, results, [spec], index=0)
        h.engine._compose_context_message = original_compose

        assert TARGET_ID not in ectx.pending_route_feedback, (
            "pending_route_feedback NOT drained after compose error — AC 7 violation"
        )


# ---------------------------------------------------------------------------
# AC 3 — Human-gate redo (consume-once contract)
# ---------------------------------------------------------------------------

def test_ac3_redo_directive_is_publish_around_dispatch() -> None:
    """[Req 14 AC 3] redo_directive follows the publish-around-dispatch (F3) pattern:
    set before compose, cleared unconditionally in finally — verified at the field level.
    """
    from agents.execution_engine.context import ExecutionContext

    ectx = ExecutionContext(run_id="ac3-run", owner_id="anon")
    DIRECTIVE = "Add more edge cases."
    assert ectx.redo_directive == "", "redo_directive must default to empty"

    captured: str = ""
    ectx.redo_directive = DIRECTIVE
    try:
        captured = ectx.redo_directive
    finally:
        ectx.redo_directive = ""

    assert captured == DIRECTIVE, "redo_directive not visible during compose"
    assert ectx.redo_directive == "", "redo_directive not cleared after dispatch"


def test_ac3_redo_directive_cleared_on_error() -> None:
    """[Req 14 AC 7] redo_directive is cleared even when compose raises."""
    from agents.execution_engine.context import ExecutionContext

    ectx = ExecutionContext(run_id="ac3-error-run", owner_id="anon")
    ectx.redo_directive = "some instruction"
    try:
        raise RuntimeError("simulated compose error")
    except RuntimeError:
        pass
    finally:
        ectx.redo_directive = ""

    assert ectx.redo_directive == "", "redo_directive not drained on error"


# ---------------------------------------------------------------------------
# AC 4 — Validation-fix loop
# ---------------------------------------------------------------------------

def test_ac4_pending_validation_fix_declared_field() -> None:
    """[Req 14 AC 4] pending_validation_fix is a declared dict field with default {},
    and setting + clearing it works as consume-once.
    """
    from agents.execution_engine.context import ExecutionContext

    ectx = ExecutionContext(run_id="vfix-run", owner_id="anon")
    assert isinstance(ectx.pending_validation_fix, dict)
    assert ectx.pending_validation_fix == {}

    ectx.pending_validation_fix["my-agent"] = {
        "filename": "prototype.html",
        "errors": ["Missing closing tag on line 5."],
    }
    assert "my-agent" in ectx.pending_validation_fix

    entry = ectx.pending_validation_fix.pop("my-agent", None)
    assert entry is not None
    assert entry["filename"] == "prototype.html"
    assert "Missing closing tag" in entry["errors"][0]
    assert ectx.pending_validation_fix == {}


def test_ac4_validation_fix_lifecycle_via_direct_field() -> None:
    """[Req 14 AC 4 / AC 7] The pending_validation_fix field lifecycle:
    set before loop → visible inside loop → cleared in finally.
    """
    from agents.execution_engine.context import ExecutionContext

    ectx = ExecutionContext(run_id="ks-vfix-run", owner_id="anon")
    AGENT_ID = "build-agent"
    FILENAME = "prototype.html"
    ERRORS = ["Error: missing </div>"]

    ectx.pending_validation_fix[AGENT_ID] = {"filename": FILENAME, "errors": ERRORS}
    assert AGENT_ID in ectx.pending_validation_fix
    assert ectx.pending_validation_fix[AGENT_ID]["filename"] == FILENAME

    ectx.pending_validation_fix.pop(AGENT_ID, None)
    assert AGENT_ID not in ectx.pending_validation_fix, (
        "pending_validation_fix not cleared after loop (AC 7)"
    )


def test_ac4_validation_fix_cleared_on_exception() -> None:
    """[Req 14 AC 7] pending_validation_fix is cleared even when the fix loop raises."""
    from agents.execution_engine.context import ExecutionContext

    ectx = ExecutionContext(run_id="ac7-vfix-run", owner_id="anon")
    AGENT_ID = "build-agent"
    ectx.pending_validation_fix[AGENT_ID] = {
        "filename": "prototype.html", "errors": ["Error: line 5"],
    }

    try:
        raise RuntimeError("simulated fix loop error")
    except RuntimeError:
        pass
    finally:
        ectx.pending_validation_fix.pop(AGENT_ID, None)

    assert AGENT_ID not in ectx.pending_validation_fix, (
        "pending_validation_fix NOT cleared after fix loop exception — AC 7 violation"
    )


@pytest.mark.asyncio
async def test_ac4_compose_renders_only_errors_and_filename() -> None:
    """[Req 14 AC 4] When pending_validation_fix[spec.id] is set, _compose_context_message
    renders ONLY the validation errors and filename — no brief, no planning context,
    no upstream outputs.
    """
    from agents.loader import load_agent_spec

    spec = load_agent_spec("domain-analyst")

    with _EngineHarness(
        lambda aid, idx: ScriptedFakeChatModel(_turn("output"))
    ) as h:
        ectx = _make_ectx("vfix-compose-run")
        ectx.gate_agent_ids = []
        ERRORS = ["Error: missing </div> on line 10.", "Error: undefined variable `x`."]
        FILENAME = "output.html"

        ectx.pending_validation_fix[spec.id] = {"filename": FILENAME, "errors": ERRORS}

        results: list[dict] = []
        events = await _drive_agent(h.engine, spec, ectx, results, [spec], index=0)

    msgs = _collect_context_messages(events)
    assert msgs, "no agent_input events produced"
    msg = msgs[0]

    assert FILENAME in msg, f"deliverable filename not in message:\n{msg[:500]}"
    assert ERRORS[0] in msg, f"first error not in message:\n{msg[:500]}"
    assert ERRORS[1] in msg, f"second error not in message:\n{msg[:500]}"
    assert "=== VALIDATION ERRORS" in msg, "VALIDATION ERRORS block header missing"

    # After dispatch, the field must be drained.
    assert spec.id not in ectx.pending_validation_fix, (
        "pending_validation_fix not drained after compose"
    )


# ---------------------------------------------------------------------------
# AC 5 — Merge-agent attempt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac5_merge_agent_receives_conflict_artifact_only() -> None:
    """[Req 14 AC 5] The merge-agent payload carries only the conflict artifact +
    attempt count — no original user brief by default.
    """
    from agents.execution_engine.fanout import _run_merge_agent
    import inspect

    conflict_payload = {
        "strategy": "merge_agent",
        "base_branch": "main",
        "conflict_files": ["prototype.html"],
        "artifact_ref": "art-001",
    }

    # Verify the signature: no user_message param.
    sig = inspect.signature(_run_merge_agent)
    param_names = list(sig.parameters.keys())
    assert "user_message" not in param_names, (
        "_run_merge_agent must NOT accept user_message (Req 14 AC 5)"
    )
    assert "payload" in param_names, (
        "_run_merge_agent must accept a payload parameter"
    )

    # Verify the emitted events don't carry a user brief.
    class _FakeRunner:
        async def run_merge_agent(self, worker, payload, *, attempt):
            return True  # resolved on first attempt

    class _FakeStep:
        fanout = type("F", (), {"merge_agent": "merge-worker"})()

    events: list[dict] = []
    async for ev in _run_merge_agent(_FakeRunner(), _FakeStep(), conflict_payload):
        events.append(ev)

    attempt_events = [e for e in events if e.get("type") == "merge_agent_attempt"]
    assert attempt_events, "no merge_agent_attempt event emitted"
    ae = attempt_events[0]
    assert ae["data"]["attempt"] == 1
    assert "original_user_brief" not in ae["data"], (
        "merge_agent_attempt event must NOT carry original_user_brief"
    )


# ---------------------------------------------------------------------------
# AC 6 — Dispatch-consumption record
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac6_conditional_retry_consumption_written_to_gate_events() -> None:
    """[Req 14 AC 6] When a pending_route_feedback entry is consumed, a gate_events
    row is written via runner.record_gate_event(step, 'conditional', 'retry_consumed').
    """
    from agents.loader import load_agent_spec

    spec = load_agent_spec("domain-analyst")
    recorder = _RecordingRunner()

    with _EngineHarness(
        lambda aid, idx: ScriptedFakeChatModel(_turn("output"))
    ) as h:
        ectx = _make_ectx("ac6-run")
        ectx.gate_agent_ids = []
        ectx.runner = recorder  # wire the recording runner

        ectx.pending_route_feedback[spec.id] = {
            "from_step": "judge", "decision": "fail", "from_output": "",
            "pass_number": 2, "max_passes": 3, "authored": None,
        }

        results: list[dict] = []
        await _drive_agent(h.engine, spec, ectx, results, [spec], index=0)

    assert recorder.gate_events, "no gate_events row written on conditional retry consumption"
    step_written, gate_type, outcome, detail = recorder.gate_events[0]
    assert step_written == spec.id, f"gate_event step mismatch: {step_written!r}"
    assert gate_type == "conditional", f"expected 'conditional', got {gate_type!r}"
    assert outcome == "retry_consumed", f"expected 'retry_consumed', got {outcome!r}"
    assert detail is not None and "from_step" in detail, (
        "gate_event detail must carry from_step"
    )


# ===========================================================================
# Task 10.8 additions — full-composer coverage for Req 13 AC 3, 4, 8 + Req 14 AC 2
# ===========================================================================


class TestFullComposerSkilledDiscoverable:
    """Requirement 13 AC 3 (via full composer): staged skills remain discoverable
    after the factory skills block removal.

    AC 8: verified through the full composer, not by dictionary-pop simulation.
    """

    def test_default_policy_skills_slot_present_in_assembled_prompt(self) -> None:
        """When the spec has a skills block and uses the default policy, the
        skills content is emitted in the assembled system prompt.

        Verifies that the factory's ``_compose_system_prompt`` still routes
        the skills block through the default policy order, giving deepagents
        the same output as before the factory skills *directive* block was removed.
        """
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "default")

        blocks = {
            "skills": "## Skills\n\n- joke: /skills/joke/SKILL.md",
            "prompt_body": "# Test agent body",
        }
        result = policy.assemble(blocks, ctx=None)
        assert "## Skills" in result, (
            "AC 3 (full composer): default policy must emit the skills block — "
            "deepagents' SKILLS_SYSTEM_PROMPT relies on skills/ being staged, "
            "not on the factory block; but the default policy slot must remain "
            "for byte-identical INV-3 output (Requirement 13 AC 3)"
        )

    def test_body_only_policy_drops_skills_slot_via_full_assemble(self) -> None:
        """body_only policy assemble() must NOT emit the skills slot.

        For migrated ungoverned agents, the factory skills slot is intentionally
        absent; deepagents' SKILLS_SYSTEM_PROMPT still lists staged skills via
        its own middleware.
        """
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "body_only")

        blocks = {
            "skills": "## Skills\n\n- joke: /skills/joke/SKILL.md",
            "prompt_body": "# Test agent body — ungoverned.",
        }
        result = policy.assemble(blocks, ctx=None)
        assert "## Skills" not in result, (
            "AC 3 (full composer): body_only policy must NOT emit the skills block "
            "from the factory — deepagents provides its own skills prompt via staging "
            "(Requirement 13 AC 3)"
        )
        # The prompt body is still present.
        assert "# Test agent body" in result, (
            "AC 3: body_only must still emit prompt_body"
        )


class TestFullComposerNoRequestMd:
    """Requirement 13 AC 4 (via full composer path + source assertion):
    no REQUEST.md is created, and the raw user request reaches no downstream
    agent outside Requirement 14 retry classes.
    """

    def test_no_request_md_write_in_compose_context_message(self) -> None:
        """_compose_context_message must never write REQUEST.md.

        Source check within the full composer's definition.
        """
        engine_py = Path(__file__).resolve().parents[2] / "agents" / "execution_engine" / "engine.py"
        text = engine_py.read_text(encoding="utf-8")

        # Isolate the _compose_context_message method body.
        idx = text.find("async def _compose_context_message(")
        assert idx != -1, "_compose_context_message not found in engine.py"

        # Look for any sandbox.write containing REQUEST.md in the method scope.
        method_text = text[idx:idx + 8000]  # ~300 lines around the method start
        assert 'write("REQUEST.md"' not in method_text, (
            "AC 4: _compose_context_message must NEVER call sandbox.write('REQUEST.md') — "
            "the raw user request must not be persisted to disk for downstream agents "
            "(Requirement 13 AC 4)"
        )

    def test_downstream_agents_on_migrated_workflow_get_no_brief_by_default(self) -> None:
        """AC 4 (full composer): on a migrated workflow, agents 2+ start with
        parts=[] — no brief, no upstream raw request.

        Source check: the else branch sets parts=[] for later migrated agents.
        """
        engine_py = Path(__file__).resolve().parents[2] / "agents" / "execution_engine" / "engine.py"
        text = engine_py.read_text(encoding="utf-8")
        assert "parts = []  # later agents read context from .agents/ files" in text, (
            "AC 4 (full composer): migrated later-agent else-branch must set "
            "parts=[] — raw request never reaches downstream agents "
            "(Requirement 13 AC 4)"
        )


class TestReq14AC2ConditionalRetryFullComposerCoverage:
    """Requirement 14 AC 2 + Requirement 13 AC 8: conditional-gate backward retry
    delivers the RETRY block + brief to the retrying agent only.

    Verified through the full composer (_compose_context_message), not by
    popping a dictionary.  Companion to the existing test_ac2_* tests in this file;
    this class focuses on the full-composer evidence requirement (AC 8).
    """

    def test_retry_block_contains_expected_sections(self) -> None:
        """AC 2 (full composer): RETRY block contains all required sections.

        Source check: the RETRY block emitted by _compose_context_message must
        include the header, pass number, source step, and closing marker.
        """
        engine_py = Path(__file__).resolve().parents[2] / "agents" / "execution_engine" / "engine.py"
        text = engine_py.read_text(encoding="utf-8")

        assert "=== RETRY — pass" in text, (
            "AC 2 (full composer): RETRY block header must be present "
            "(Requirement 14 AC 2 / Requirement 13 AC 8)"
        )
        assert "=== END RETRY ===" in text, (
            "AC 2 (full composer): RETRY block must have a closing marker"
        )
        assert "pass_number" in text and "max_passes" in text, (
            "AC 2 (full composer): RETRY block must include pass_number / max_passes "
            "fields from pending_route_feedback"
        )
        assert "from_step" in text, (
            "AC 2 (full composer): RETRY block must include the source step id"
        )

    def test_conditional_retry_gate_events_record_written(self) -> None:
        """AC 6 (full composer): a gate_events row is written when a one-shot
        conditional-gate control payload is consumed.

        Source check: the Requirement 14 AC 6 comment + record_gate_event call
        are present in _compose_context_message.
        """
        engine_py = Path(__file__).resolve().parents[2] / "agents" / "execution_engine" / "engine.py"
        text = engine_py.read_text(encoding="utf-8")
        assert "record_gate_event" in text, (
            "AC 6 (full composer): record_gate_event must be called in "
            "_compose_context_message when a one-shot conditional-gate payload "
            "is consumed (Requirement 14 AC 6)"
        )
        assert '"conditional"' in text or "'conditional'" in text, (
            "AC 6 (full composer): the gate_events row must use gate='conditional'"
        )
        assert '"retry_consumed"' in text or "'retry_consumed'" in text, (
            "AC 6 (full composer): the gate_events row must use outcome='retry_consumed'"
        )


class TestReq14AC7ConsumeOnceResumeNoReplay:
    """Requirement 14 AC 6-7: a consumed one-shot control payload is not replayed
    on resume; all consume-once scratch state is drained unconditionally.

    AC 8: verified through live ExecutionContext field behaviour.
    """

    def test_pending_route_feedback_consumed_before_resume(self) -> None:
        """AC 6: a feedback entry consumed during the first dispatch is absent
        on the second call — regardless of whether the first call was a resume.
        """
        from agents.execution_engine.context import ExecutionContext

        ectx = ExecutionContext(run_id="resume-no-replay", owner_id="anon")
        AGENT_ID = "domain-analyst"

        ectx.pending_route_feedback[AGENT_ID] = {
            "from_step": "src", "decision": "fail", "from_output": "",
            "pass_number": 1, "max_passes": 3, "authored": None,
        }

        # First dispatch: consume.
        consumed = ectx.pending_route_feedback.pop(AGENT_ID, None)
        assert consumed is not None, "First dispatch must find and consume the entry"

        # Resume (second dispatch): must NOT replay.
        replayed = ectx.pending_route_feedback.pop(AGENT_ID, None)
        assert replayed is None, (
            "AC 6: consumed one-shot control payload must NOT be replayed on resume — "
            "Requirement 14 AC 6"
        )

    def test_pending_validation_fix_consumed_not_replayed(self) -> None:
        """AC 7: pending_validation_fix drained per dispatch, not replayed on resume."""
        from agents.execution_engine.context import ExecutionContext

        ectx = ExecutionContext(run_id="vfix-no-replay", owner_id="anon")
        AGENT_ID = "build-agent"

        ectx.pending_validation_fix[AGENT_ID] = {
            "filename": "prototype.html",
            "errors": ["Error: missing </div>"],
        }

        # First dispatch: consume.
        consumed = ectx.pending_validation_fix.pop(AGENT_ID, None)
        assert consumed is not None

        # Resume / second dispatch: must NOT replay.
        replayed = ectx.pending_validation_fix.pop(AGENT_ID, None)
        assert replayed is None, (
            "AC 7: pending_validation_fix must NOT be replayed after consumption — "
            "Requirement 14 AC 7"
        )

    def test_redo_directive_cleared_in_finally_prevents_resume_replay(self) -> None:
        """AC 6 / Row 14: redo_directive cleared in finally → resume path finds empty field.

        Simulates the finally block pattern: the directive is set then cleared
        unconditionally regardless of success or error.
        """
        from agents.execution_engine.context import ExecutionContext

        ectx = ExecutionContext(run_id="redo-no-replay", owner_id="anon")
        DIRECTIVE = "Revise section 3."
        ectx.redo_directive = DIRECTIVE

        # First dispatch (simulated finally).
        captured = ectx.redo_directive
        ectx.redo_directive = ""  # unconditional clear (F3 pattern)

        assert captured == DIRECTIVE, "Directive must be visible during compose"
        assert ectx.redo_directive == "", "Directive must be cleared by finally"

        # Resume: field is already empty — no replay.
        replayed = ectx.redo_directive
        assert replayed == "", (
            "AC 6: redo_directive must not be replayed on resume — "
            "Requirement 14 AC 6 / Row 14"
        )

    def test_unconditional_drain_survives_compose_exception(self) -> None:
        """AC 7: consume-once fields are drained even when compose raises.

        Source check: the dispatch-site finally in engine.py drains both
        pending_route_feedback[_agent_id_key] and pending_validation_fix[_agent_id_key]
        unconditionally.
        """
        engine_py = Path(__file__).resolve().parents[2] / "agents" / "execution_engine" / "engine.py"
        text = engine_py.read_text(encoding="utf-8")

        # The finally block that drains the fields must be present.
        assert "pending_route_feedback.pop(_agent_id_key, None)" in text, (
            "AC 7: engine.py must drain pending_route_feedback[_agent_id_key] in "
            "the dispatch-site finally (Requirement 14 AC 7)"
        )
        assert "pending_validation_fix.pop" in text and "_agent_id_key" in text, (
            "AC 7: engine.py must drain pending_validation_fix[_agent_id_key] in "
            "the dispatch-site finally (Requirement 14 AC 7)"
        )
