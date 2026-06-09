"""Pre-Phase-7 context_message ORACLE (07-08, cluster C step 1).

This package holds the engine-INDEPENDENT ground truth for the assembled
``context_message`` bytes that the pre-Phase-7 ``ExecutionEngine._build_context_message``
produced for the ``prototype`` / ``od_prototype`` agent classes, captured verbatim from
baseline ``acd1636`` (``git show acd1636:backend/agents/execution_engine/engine.py``
lines 3243-3470 + ``git show acd1636:backend/agents/prototype/context.py``).

WHY AN ORACLE (07-REVIEW-DEEP.md systemic[0]):
The 07-06 gap-closure de-blinded the five characterization goldens by removing
``context_message`` from ``_VOLATILE_STRIP_KEYS`` and regenerating with
``SNAPSHOT_UPDATE=1``. But ``SNAPSHOT_UPDATE`` captures the CURRENT routed bytes — which
had ALREADY drifted from the true pre-Phase-7 prompt (CR-01/CR-02/CR-04 dropped the
unconditional TEMPLATE COMPLIANCE block, leaked the DS block past the per-``injects``
gate, and double-wrapped the injection parts). So the goldens pin the DRIFTED prompt as
the contract; "pinned == correct" is FALSE.

This oracle is the only correct measuring stick: it reconstructs the TRUE acd1636 bytes
INDEPENDENTLY of the live engine (so it cannot drift with the refactor), and a companion
test (``tests/agents/test_context_message_oracle.py``) pins the oracle AND proves today's
routed message diverges from it. That divergence is the acceptance target 07-09 closes.

Public surface:
    build_oracle_message(agent_class, *, task="")  — the assembled legacy context_message
    AGENT_CLASSES                                   — the four captured agent classes
    ORACLE_OD_CONTEXT                               — the deterministic repro od_context
"""

from __future__ import annotations

from tests.agents.characterization.oracle.legacy_context_message import (
    AGENT_CLASSES,
    ORACLE_OD_CONTEXT,
    build_oracle_message,
)

__all__ = [
    "AGENT_CLASSES",
    "ORACLE_OD_CONTEXT",
    "build_oracle_message",
]
