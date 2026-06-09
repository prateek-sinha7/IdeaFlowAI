"""agents/capabilities/gates/security.py — the ``security`` gate (08-02 / D-03 / §9).

Default-denies a step that requests a privileged permission
(``exec`` / ``network`` / ``secrets``) — all of which stay OFF this phase
(exec=Phase 10/N3, network/secrets later). A step requesting them under a
``security`` gate returns ``block``; otherwise ``pass``. This is the coarse trust
enforcement the threat model needs (T-08-02-EoP) before any exec/runtime lands.

Registered ``user_allowed=False`` (D-01/D-02): the security gate is engineer-only;
it is never user-grantable (it is the seam keeping exec off the user palette).

Import purity (import-linter): imports only the registry decorator + the gate
outcome contract; reaches the ``gate_events`` writer through ``ctx.runner`` — NO
kernel/app import.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.gates.base import GATE_BLOCK, GATE_PASS, GateOutcome
from agents.capabilities.gates.write import write_gate_event
from agents.capabilities.registry import register


@register("gate", "security", user_allowed=False)
class SecurityGate:
    """Default-deny gate for privileged permissions (``name='security'``).

    Satisfies the ``GateHandler`` port structurally (``name`` + ``async evaluate``).
    """

    name = "security"

    async def evaluate(self, step: Any, ctx: Any) -> GateOutcome:
        """Block iff the step requests exec/network/secrets (all OFF this phase)."""
        tools = getattr(step, "tools", None)
        wants_exec = bool(getattr(tools, "exec", False))
        wants_network = bool(getattr(tools, "network", False))
        wants_secrets = bool(getattr(tools, "secrets", None))

        requested = [
            label
            for label, wanted in (
                ("exec", wants_exec),
                ("network", wants_network),
                ("secrets", wants_secrets),
            )
            if wanted
        ]

        step_id = getattr(step, "agent_id", None) or "?"
        if requested:
            detail = {
                "denied": requested,
                "reason": "privileged permissions are OFF this phase (default-deny)",
            }
            await write_gate_event(ctx, step_id, "security", GATE_BLOCK, detail)
            return GateOutcome(
                outcome=GATE_BLOCK,
                events=[
                    {
                        "type": "gate_blocked",
                        "data": {
                            "step": step_id,
                            "gate": "security",
                            "denied": requested,
                        },
                    }
                ],
                detail=detail,
            )

        await write_gate_event(ctx, step_id, "security", GATE_PASS, None)
        return GateOutcome(outcome=GATE_PASS)
