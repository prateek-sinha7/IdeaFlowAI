"""agents/capabilities/gates/ — the GateHandler capability package (08-02 / D-03 / §9).

Importing this package imports each gate impl module, firing its
``@register("gate", …)`` decorator so ``discover()`` (which imports this package)
binds all five gates into the registry. The gate kinds:

  * ``human``       — routes to the existing ``_run_review_gate`` (GATE-03 parity)
  * ``validation``  — runs declared validators, block-critical/warn-non-critical (GATE-02)
  * ``approval``    — explicit sign-off → wait_human
  * ``security``    — default-denies exec/network/secrets (T-08-02-EoP)
  * ``conditional`` — routes to a declared step or triggers another workflow based on
    a step's typed decision (spec 014 / R-05b)

Each gate writes a ``gate_events`` row on firing (D-10) and returns a
``GateOutcome`` (``pass | block | wait_human | route`` + additive events). The shared
outcome contract lives in ``gates.base``; the ``gate_events`` write helper in
``gates.write``.
"""

from __future__ import annotations

from agents.capabilities.gates import (  # noqa: F401 — import side effect: @register
    approval,
    conditional,
    human,
    security,
    validation,
)
from agents.capabilities.gates.base import (  # noqa: F401 — re-export the contract
    GATE_BLOCK,
    GATE_PASS,
    GATE_WAIT_HUMAN,
    GateOutcome,
)

__all__ = [
    "GATE_BLOCK",
    "GATE_PASS",
    "GATE_WAIT_HUMAN",
    "GateOutcome",
]
