"""agents/capabilities/hooks/base.py — executable-hook outcome + binding contract (08-07 / HOOK-01..04 / §30).

The shared vocabulary every EXECUTABLE ``HookHandler`` impl returns + the
permission-gated binding helper the engine dispatch uses. An executable hook's
``handle(event, ctx)`` returns a ``HookOutcome`` carrying:

  * ``outcome`` ∈ ``continue | warn | block`` — the kernel acts on this at the
    firing point (a ``block`` HALTS the offending action ADDITIVELY: it emits NO
    existing event, it just stops the write/step — RESEARCH Pitfall 6);
  * ``detail`` — the audit payload written to the ``hook_runs`` row.

Permission gating (HOOK-02): a hook declares ``events`` (the lifecycle/tool-call
events it binds to) + ``required_permission`` (``read_files`` for a scanner,
``git`` for a git hook, ``exec`` for a command hook, or ``None``). ``is_bound``
returns ``True`` iff the step's EFFECTIVE permissions (08-03 — ``step.tools``, the
``intersect_permissions`` result) grant the hook's required permission. A hook
whose permission is OFF this phase (``git`` / ``exec``) is NOT bound — its
``handle`` never fires.

The wildcard ``*`` event binds the hook to EVERY firing point (otel_tracing). A
hook is fired for an event ``E`` iff ``E in hook.events`` OR ``"*" in
hook.events`` — AND it is permission-bound.

Keeping the hook a plain ``async`` function (returning a value, not an async
generator) keeps the impls simple + testable; the kernel owns the firing-point
dispatch + the halt decision. The outcome strings are the SINGLE source — hooks +
the engine seam import them here.

Import purity (import-linter): imports ONLY stdlib typing. No kernel/app import —
the engine reaches these helpers via a normal kernel→ports import (the legal
direction); the hook impls reach the ``hook_runs`` writer through ``ctx.runner``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# The three hook outcomes (HOOK-01). Single source — hooks + the engine seam
# import these. ``block`` halts the offending action; ``warn`` records a warning
# row but proceeds; ``continue`` is the clean pass.
HOOK_CONTINUE = "continue"
HOOK_WARN = "warn"
HOOK_BLOCK = "block"

# The wildcard event — a hook declaring it binds to EVERY firing point.
HOOK_WILDCARD = "*"


@dataclass
class HookOutcome:
    """The result of an executable hook firing (HOOK-01).

    ``outcome`` drives the kernel's firing-point decision (a ``block`` halts the
    offending action additively); ``detail`` is the audit payload written to the
    ``hook_runs`` row.
    """

    outcome: str = HOOK_CONTINUE
    detail: dict | None = None


def hook_fires_for(hook: Any, event: str) -> bool:
    """Return ``True`` iff ``hook`` declares ``event`` (or the ``*`` wildcard)."""
    events = list(getattr(hook, "events", None) or [])
    return event in events or HOOK_WILDCARD in events


def is_bound(hook: Any, perms: Any) -> bool:
    """Return ``True`` iff the step's EFFECTIVE ``perms`` grant the hook's permission (HOOK-02).

    A hook declaring ``required_permission=None`` is always bound (no privilege
    needed). Otherwise the named permission must be granted on the step's effective
    ``ToolPermissions`` (``perms``): ``read_files`` (ON by default) binds a scanner;
    ``git`` / ``exec`` (OFF this phase) leave a git/command hook UNBOUND so it never
    fires (HOOK-02 / T-08-07-EoP). A missing ``perms`` (offline unit ctx) is treated
    as the least-privilege default (read_files ON, everything else OFF).
    """
    required = getattr(hook, "required_permission", None)
    if not required:
        return True
    if perms is None:
        # Least-privilege default: only read_files is granted with no perms object.
        return required == "read_files"
    return bool(getattr(perms, required, False))


def bound_hooks(hooks: Any, event: str, perms: Any) -> list[Any]:
    """Return the hooks that FIRE for ``event`` under the step's ``perms`` (HOOK-01/02).

    A hook fires iff it declares the event (or ``*``) AND its required permission is
    granted — the single binding predicate the engine dispatch uses at every firing
    point. Preserves the input order so dispatch is deterministic.
    """
    return [h for h in (hooks or []) if hook_fires_for(h, event) and is_bound(h, perms)]
