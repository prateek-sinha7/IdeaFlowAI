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

from typing import Any

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


@register("gate", "human", user_allowed=True)
class HumanGate:
    """HITL review gate (``name='human'``) delegating to the unchanged review gate.

    Satisfies the ``GateHandler`` port structurally (``name`` + ``async evaluate``).
    """

    name = "human"

    async def evaluate(self, step: Any, ctx: Any) -> GateOutcome:
        """Route through the existing ``_run_review_gate`` (GATE-03 parity)."""
        step_id = getattr(step, "agent_id", None) or "?"
        runner = getattr(ctx, "runner", None)
        delegate = getattr(runner, "run_human_gate", None)
        if delegate is None:
            # No HITL surface available (offline / no handle) → pause for human.
            await write_gate_event(ctx, step_id, "human", GATE_WAIT_HUMAN, None)
            return GateOutcome(outcome=GATE_WAIT_HUMAN)

        # The step's deliverable output drives the review payload (parity with the
        # inline path, which passes the agent's output). Sourced from ctx when set.
        output = getattr(ctx, "last_streamed", "") or ""

        events: list[dict] = []
        rejected = False
        async for event in delegate(step, output=output):
            etype = event.get("type")
            if etype == _REJECTED:
                rejected = True
                # internal signal — not re-surfaced as a gate event
                continue
            if etype == _EDITED:
                # internal edit signal — not a public gate event
                continue
            # review_gate_ready / review_gate_approved flow through UNCHANGED (parity)
            events.append(event)

        outcome = GATE_BLOCK if rejected else GATE_PASS
        await write_gate_event(ctx, step_id, "human", outcome, None)
        return GateOutcome(outcome=outcome, events=events)
