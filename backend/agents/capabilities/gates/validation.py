"""agents/capabilities/gates/validation.py — the real ``Validation_Gate`` (08-02 / GATE-02 / §9).

Makes the declared-but-dead ``Validation_Gate`` real (GATE-02 / D-03 / D-06). At a
step declaring ``gates: [validation]`` it:

  1. resolves the step's declared ``validators: [...]`` from the registry
     (``resolve("validator", name)``, reached through the registry) and runs each
     validator's ``validate(target)`` (the target is the ExecutionContext — the
     validators reach the deliverable through ``ctx.runner``);
  2. maps each issue's internal P0–P3 severity through the SHARED ``map_severity``
     IMPORTED from ``agents.capabilities.validators.severity`` (VALID-03 single
     source — NOT a local table, NOT a stub: the one canonical function from
     08-01) to its UI label (CRITICAL/HIGH/MEDIUM/LOW);
  3. applies the policy (Q25): a CRITICAL issue → ``block``; otherwise any residual
     non-critical issue → emit a ``validation_warning`` (additive) and ``pass``;
  4. writes a ``gate_events`` row with the outcome (D-10).

At 08-02 execution time no ``validator`` impls are registered (those land in
08-04); the WIRING above (``resolve("validator", …)`` + the imported
``map_severity`` + the policy) is the contract this gate owns. The real
html_static/html_render/Tier validators flow through this same path in 08-04.

Import purity (import-linter): the registry + the gate-outcome contract + the
single ``map_severity`` only; the ``gate_events`` write + the deliverable target
are reached through ``ctx.runner`` — NO kernel/app import.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.capabilities.gates.base import GATE_BLOCK, GATE_PASS, GateOutcome
from agents.capabilities.gates.write import write_gate_event
from agents.capabilities.registry import register
# THE single canonical severity mapping (VALID-03 / 08-01) — IMPORTED, never
# re-defined and never stubbed here. validators.severity is import-clean of any
# @register/discover() side-effect, so importing it at gate-module import is safe.
from agents.capabilities.validators.severity import map_severity

logger = logging.getLogger(__name__)

# The UI label that blocks (P0 → CRITICAL). Block-critical / warn-non-critical.
_CRITICAL_LABEL = "CRITICAL"


@register("gate", "validation", user_allowed=True)
class ValidationGate:
    """Runs declared validators + applies block-critical/warn-non-critical (``name='validation'``).

    Satisfies the ``GateHandler`` port structurally (``name`` + ``async evaluate``).
    """

    name = "validation"

    async def evaluate(self, step: Any, ctx: Any) -> GateOutcome:
        """Run the step's declared validators and apply the failure policy (GATE-02)."""
        from agents.capabilities.registry import CapabilityRegistry

        registry = CapabilityRegistry()
        validator_names = list(getattr(step, "validators", None) or [])
        step_id = getattr(step, "agent_id", None) or "?"

        # Collect every issue, mapped to its UI label via the SHARED map_severity.
        labelled: list[dict] = []
        for vname in validator_names:
            validator = registry.resolve("validator", vname)
            issues = await validator.validate(ctx)
            for issue in issues or []:
                internal = getattr(issue, "severity", None)
                try:
                    label = map_severity(internal)
                except ValueError:
                    # An unknown internal severity is a validator bug — surface it
                    # as a residual (non-blocking) warning rather than crashing the
                    # gate; the validator owns the contract (08-04).
                    logger.warning(
                        "validation gate: validator %s emitted unknown severity %r",
                        vname, internal,
                    )
                    label = "LOW"
                labelled.append(
                    {
                        "validator": vname,
                        "severity": label,
                        "message": getattr(issue, "message", ""),
                    }
                )

        criticals = [i for i in labelled if i["severity"] == _CRITICAL_LABEL]
        residuals = [i for i in labelled if i["severity"] != _CRITICAL_LABEL]

        # Block-critical: any CRITICAL issue halts the step.
        if criticals:
            detail = {"issues": labelled, "blocking": criticals}
            await write_gate_event(ctx, step_id, "validation", GATE_BLOCK, detail)
            return GateOutcome(
                outcome=GATE_BLOCK,
                events=[
                    {
                        "type": "gate_blocked",
                        "data": {
                            "step": step_id,
                            "gate": "validation",
                            "issues": criticals,
                        },
                    }
                ],
                detail=detail,
            )

        # Warn-non-critical: residual P1–P3 issues emit a validation_warning + proceed.
        events: list[dict] = []
        detail = {"issues": labelled}
        if residuals:
            events.append(
                {
                    "type": "validation_warning",
                    "data": {"step": step_id, "issues": residuals},
                }
            )
        await write_gate_event(ctx, step_id, "validation", GATE_PASS, detail)
        return GateOutcome(outcome=GATE_PASS, events=events, detail=detail)
