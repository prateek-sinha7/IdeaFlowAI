"""agents/capabilities/hooks/write.py — the shared hook_runs write helper (08-07 / HOOK-04 / D-10).

Every EXECUTABLE ``HookHandler`` firing writes one owner/workspace-scoped
``hook_runs`` row (HOOK-04). The row is written through the ``ctx.runner``
(KernelServices) handle's ``record_hook_run`` so the hook impl never imports the
kernel or ``app.*`` (import-linter: the writer lives where the ScopedStore lives;
the hook reaches it dynamically off the object-typed handle — the same idiom the
gates use via ``record_gate_event``).

Best-effort: a missing handle (an offline unit test driving a hook with a fake
ctx) is a no-op, and a persist failure inside the handle degrades to ``None`` —
the audit write must NEVER abort a hook firing (INV-3: audit must not break the
live stream).
"""

from __future__ import annotations

from typing import Any


async def write_hook_run(
    ctx: Any, hook: str, event: str, outcome: str, detail: Any = None
) -> None:
    """Write one ``hook_runs`` row via ``ctx.runner.record_hook_run`` (best-effort)."""
    runner = getattr(ctx, "runner", None)
    if runner is None:
        return
    record = getattr(runner, "record_hook_run", None)
    if record is None:
        return
    await record(hook, event, outcome, detail)
