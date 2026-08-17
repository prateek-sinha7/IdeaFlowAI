"""agents/capabilities/gates/human.py — the ``human`` gate (08-02 / GATE-03 / §9).

Routes a declared ``gates: [human]`` step through the EXISTING engine
``_run_review_gate`` (via the ``ctx.runner.run_human_gate`` handle delegate) so the
emitted ``review_gate_*`` event sequence stays byte/event-identical — GATE-03
parity. This gate adds NO new HITL behavior and NO second HITL mechanism: it
DELEGATES to the unchanged review-gate path. The existing inline ``_should_gate``
→ ``_run_review_gate`` flow in ``_run_agent`` (the prototype/od_* human gates) is
untouched; this registered ``human`` gate is the additive registry-driven entry
point for a manifest that declares ``gates:[human]`` explicitly.

The internal ``_gate_rejected`` signal maps to a ``block`` outcome; otherwise the
gate passes. The ``review_gate_*`` events are surfaced unchanged (the kernel
yields them); the internal ``_gate_*`` signals are NOT re-surfaced as gate events.

Registered ``user_allowed=True`` (D-01/D-02): a human review gate is a safe,
user-grantable control.

Import purity (import-linter): registry decorator + outcome contract only; the
review gate is reached through ``ctx.runner`` — NO kernel/app import.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from agents.capabilities.gates.base import (
    GATE_BLOCK,
    GATE_PASS,
    GATE_WAIT_HUMAN,
    GateOutcome,
)
from agents.capabilities.gates.write import write_gate_event
from agents.capabilities.registry import register

# Engine-internal review-gate signals (NOT surfaced as gate events — they drive
# the outcome only). Kept in sync with engine._run_review_gate.
_REJECTED = "_gate_rejected"
_EDITED = "_gate_edited"
# REDO-GATE F1a: the shared _run_review_gate may now emit _gate_redo. The DECLARED
# human-gate path is NOT wired for redo in v1 (it is a PRE-step gate over the
# PREVIOUS step's output — a different mechanism, the documented follow-up), so a
# stray _gate_redo here (e.g. a scripted client sending action:"redo") MUST be
# CONSUMED — never re-surfaced to the wire, never mapped to GATE_PASS. The FE never
# offers Redo on a declared gate (review_gate_ready.redoable is False off this path).
_REDO = "_gate_redo"
# ISS-053: the same is true of ``_gate_update_specs``. A declared gate passes
# ``update_specs_eligible=False``, so the shared primitive now refuses that action and
# keeps waiting — but this branch is what makes a signal arriving by any OTHER route
# safe. Without it the event hit the ``yield event`` fall-through below: an internal
# ``_gate_*`` signal on the SSE wire (backend-engine.md §39 forbids that) AND a
# fall-through to GATE_PASS, i.e. a declared step signing itself off on an action the
# user never took.
_UPDATE_SPECS = "_gate_update_specs"


@register(
    "gate",
    "human",
    user_allowed=True,
    description="Pause the run for a human review gate (HITL) and resume on approval.",
)
class HumanGate:
    """HITL review gate (``name='human'``) delegating to the unchanged review gate.

    Satisfies the ``GateHandler`` port structurally (``name`` + ``async evaluate``).
    """

    name = "human"

    async def evaluate_stream(
        self, step: Any, ctx: Any
    ) -> AsyncGenerator[Any, None]:
        """Stream the review-gate events AS PRODUCED, then a terminal ``GateOutcome``.

        F1 fix (Phase 13): the delegate (``run_human_gate`` → ``_run_review_gate``)
        yields ``review_gate_ready`` BEFORE it awaits the approval response. By
        re-yielding each public event immediately (no list buffering), the ready
        event flows up the generator chain to the engine's dispatch loop — and thus
        the WS consumer — while the run is still PAUSED at ``await event.wait()``,
        matching the working inline ``_should_gate`` → ``_run_review_gate`` ordering.

        Protocol: yields zero or more public gate event dicts, then exactly one
        terminal ``GateOutcome`` (with ``events=[]`` — the events were already
        streamed; no double emission). Internal ``_gate_rejected`` / ``_gate_edited``
        signals are consumed (they drive the outcome) and never re-surfaced.
        """
        step_id = getattr(step, "agent_id", None) or "?"
        runner = getattr(ctx, "runner", None)
        delegate = getattr(runner, "run_human_gate", None)
        if delegate is None:
            # No HITL surface available (offline / no handle) → pause for human.
            await write_gate_event(ctx, step_id, "human", GATE_WAIT_HUMAN, None)
            yield GateOutcome(outcome=GATE_WAIT_HUMAN)
            return

        # The step's deliverable output drives the review payload (parity with the
        # inline path, which passes the agent's output). Sourced from ctx when set.
        output = getattr(ctx, "last_streamed", "") or ""

        rejected = False
        unwired_action_seen = False
        edited_content: str | None = None
        async for event in delegate(step, output=output):
            etype = event.get("type")
            if etype == _REJECTED:
                rejected = True
                # internal signal — not re-surfaced as a gate event
                continue
            if etype in (_REDO, _UPDATE_SPECS):
                # REDO-GATE F1a / ISS-053: consume the signal — never yield it (no wire
                # leak via _evaluate_gates), never let it fall through to GATE_PASS.
                unwired_action_seen = True
                continue
            if etype == _EDITED:
                # WR-04 (13 review fix): the user approved WITH edits. The edit
                # used to be consumed and dropped here — silent loss of user
                # input while the engine confirmed ``edited: true``. Capture it
                # and thread it on the terminal outcome ``detail`` so the kernel
                # can apply it to the upstream artifact (inline-path parity).
                # Still not a public gate event (parity — the inline path emits
                # no extra event for an edit either).
                edited_content = event.get("edited_content")
                continue
            # review_gate_ready / review_gate_approved flow through UNCHANGED (parity)
            # — yielded IMMEDIATELY so ready reaches the consumer pre-await (F1).
            yield event

        # REDO-GATE F1a: a stray redo on the (un-wired) declared path maps to a
        # NON-PASS outcome — GATE_WAIT_HUMAN ("still needs a human"), so the step does
        # NOT silently advance. Reject still wins (GATE_BLOCK). This also writes an
        # HONEST audit row (F9) instead of a misleading GATE_PASS.
        outcome = (
            GATE_BLOCK if rejected
            else (GATE_WAIT_HUMAN if unwired_action_seen else GATE_PASS)
        )
        # The audit row keeps a CONTENT-FREE detail (no user payload persisted in
        # gate_events); the edited content itself rides the GateOutcome only.
        await write_gate_event(
            ctx, step_id, "human", outcome,
            {"edited": True} if (edited_content and not rejected) else None,
        )
        detail = (
            {"edited_content": edited_content}
            if (edited_content and not rejected)
            else None
        )
        yield GateOutcome(outcome=outcome, events=[], detail=detail)

    async def evaluate(self, step: Any, ctx: Any) -> GateOutcome:
        """Thin collector over ``evaluate_stream`` (INV-12 single implementation).

        Preserves the pre-streaming contract exactly: returns one ``GateOutcome``
        whose ``events`` list carries every public event the stream produced.
        """
        events: list[dict] = []
        terminal: GateOutcome | None = None
        async for item in self.evaluate_stream(step, ctx):
            if isinstance(item, dict):
                events.append(item)
            else:
                terminal = item
        if terminal is None:  # defensive — the stream always yields one terminal
            terminal = GateOutcome(outcome=GATE_PASS)
        return GateOutcome(
            outcome=terminal.outcome, events=events, detail=terminal.detail
        )
