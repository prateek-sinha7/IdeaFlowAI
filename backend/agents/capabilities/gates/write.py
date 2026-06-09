"""agents/capabilities/gates/write.py — the shared gate_events write helper (08-02 / D-10).

Every ``GateHandler`` firing writes one owner/workspace-scoped ``gate_events`` row
(GATE-01..03). The row is written through the ``ctx.runner`` (KernelServices)
handle's ``record_gate_event`` so the gate impl never imports the kernel or
``app.*`` (import-linter: the writer lives where the ScopedStore lives; the gate
reaches it dynamically off the object-typed handle).

Best-effort: a missing handle (an offline unit test driving a gate with a fake
ctx) is a no-op, and a persist failure inside the handle degrades to ``None`` —
the audit write must NEVER abort a gate evaluation (INV-3: audit must not break
the live stream).
"""

from __future__ import annotations

from typing import Any


async def write_gate_event(
    ctx: Any, step: str, gate: str, outcome: str, detail: Any = None
) -> None:
    """Write one ``gate_events`` row via ``ctx.runner.record_gate_event`` (best-effort)."""
    runner = getattr(ctx, "runner", None)
    if runner is None:
        return
    record = getattr(runner, "record_gate_event", None)
    if record is None:
        return
    await record(step, gate, outcome, detail)
