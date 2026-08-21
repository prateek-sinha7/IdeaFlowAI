"""agents/capabilities/gates/base.py — gate outcome contract (08-02 / D-03 / §9).

The shared vocabulary every ``GateHandler`` impl returns. A gate's
``evaluate(step, ctx)`` returns a ``GateOutcome`` carrying:

  * ``outcome`` ∈ ``pass | block | wait_human`` — the kernel acts on this at the
    step boundary (a ``block`` / ``wait_human`` halts the step additively);
  * ``events`` — additive engine event dicts (``{"type": ..., "data": {...}}``)
    the kernel yields verbatim through the generic forward (``websocket.py``),
    e.g. the validation gate's ``validation_warning`` and the new ``gate_*``
    events. NEVER renames/removes an existing event (INV-3 additive-only).

Keeping the gate a plain ``async`` function (returning a value, not an async
generator) keeps the impls simple and testable; the kernel owns the yield. The
outcome strings are the SINGLE source — gates + the engine seam import them here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The three gate outcomes (§9). Single source — gates + the engine seam import these.
GATE_PASS = "pass"
GATE_BLOCK = "block"
GATE_WAIT_HUMAN = "wait_human"
GATE_ROUTE = "route"


@dataclass
class GateOutcome:
    """The result of a gate evaluation (D-03).

    ``outcome`` drives the kernel's step-boundary decision; ``events`` are the
    additive event dicts the kernel yields (a ``block`` event, a residual
    ``validation_warning``). ``detail`` is the audit payload written to the
    ``gate_events`` row.
    """

    outcome: str
    events: list[dict] = field(default_factory=list)
    detail: dict | None = None
