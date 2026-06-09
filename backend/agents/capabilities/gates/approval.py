"""agents/capabilities/gates/approval.py — the ``approval`` gate (08-02 / D-03 / §9).

Requires an explicit human sign-off before a sensitive action proceeds: it returns
``wait_human`` to pause the step for approval. No sensitive action exists to
trigger it until P9/P10, so it is exercised by a test manifest declaring
``gates: [approval]`` (the WIRING — registry resolution + the ``wait_human``
outcome + the ``gate_events`` row — is proven now).

Registered ``user_allowed=False`` (D-01/D-02): approval is an engineer-declared
control, not a user-grantable palette capability.

Import purity (import-linter): registry decorator + outcome contract only; the
``gate_events`` write goes through ``ctx.runner`` — NO kernel/app import.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.gates.base import GATE_WAIT_HUMAN, GateOutcome
from agents.capabilities.gates.write import write_gate_event
from agents.capabilities.registry import register


@register("gate", "approval", user_allowed=False)
class ApprovalGate:
    """Explicit sign-off gate (``name='approval'``) → ``wait_human``.

    Satisfies the ``GateHandler`` port structurally (``name`` + ``async evaluate``).
    """

    name = "approval"

    async def evaluate(self, step: Any, ctx: Any) -> GateOutcome:
        """Pause for explicit human sign-off (``wait_human``)."""
        step_id = getattr(step, "agent_id", None) or "?"
        detail = {"reason": "explicit human sign-off required before this step"}
        await write_gate_event(ctx, step_id, "approval", GATE_WAIT_HUMAN, detail)
        return GateOutcome(
            outcome=GATE_WAIT_HUMAN,
            events=[
                {
                    "type": "gate_wait_human",
                    "data": {"step": step_id, "gate": "approval"},
                }
            ],
            detail=detail,
        )
