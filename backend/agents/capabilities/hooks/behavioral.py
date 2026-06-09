"""agents/capabilities/hooks/behavioral.py — the behavioral hook_provider (08-05 / F3 / §30).

Lifts the factory's inline hook injection (F3) into a registered ``HookProvider``
capability of the ``behavioral`` (non-executable) sub-type. The inline path synthesized a
single ``## Active Behavioral Hooks`` block from ``ctx.attached_hooks``:

    if ctx.attached_hooks:
        hook_lines = []
        for hook in ctx.attached_hooks:
            name, event, trigger, description = ...
            if name:
                hook_lines.append(f"- **{name}** ({event}): {description or trigger}")
        if hook_lines:
            append "## Active Behavioral Hooks\\n\\n" + ... + "\\n".join(hook_lines)

This provider reproduces that block BYTE-IDENTICALLY (the legacy prompt-only hook
SURVIVES as a ``kind: behavioral`` NON-executable sub-type — F3 / HOOK-01). The ``##
Active Behavioral Hooks`` block STILL RENDERS for attached behavioral hooks; the factory
feeds the returned block(s) into the prompt's ``hooks`` slot — byte-identical to the
inline path (the 5 characterization snapshots gate it; NEVER re-baseline).

NOTE (08-07 / Wave 5): this package is EXTENDED with EXECUTABLE ``HookHandler`` hooks
(``secret_scan`` / ``otel_tracing``). The behavioral sub-type here is the
NON-executable companion — leave it intact.

Import purity (import-linter): imports ONLY the registry decorator + stdlib typing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.capabilities.registry import register

# The behavioral block header + preamble — VERBATIM from the inline factory path. Any
# byte change here drifts the composed prompt (RESEARCH Pitfall 2). Do NOT edit.
_BEHAVIORAL_HEADER = "## Active Behavioral Hooks"
_BEHAVIORAL_PREAMBLE = (
    "The following behavioral guidelines are active for this run. "
    "Apply them throughout your response:"
)


@dataclass(frozen=True)
class HookBlock:
    """A hook descriptor returned by a ``HookProvider`` (F3 / HOOK-01).

    ``kind`` distinguishes the NON-executable ``behavioral`` sub-type (a prompt-only
    rendered block) from the executable ``HookHandler`` hooks 08-07 adds. ``content`` is
    the rendered prompt block (empty for an executable hook descriptor)."""

    kind: str
    content: str = ""


@register("hook", "behavioral", user_allowed=True)
class BehavioralHookProvider:
    """The ``behavioral`` non-executable hook sub-type (``name='behavioral'``).

    Renders the legacy ``## Active Behavioral Hooks`` block from ``ctx.attached_hooks``
    BYTE-IDENTICALLY to the inline factory path. Returns a single ``HookBlock`` (kind
    ``behavioral``) when at least one attached hook has a ``name``; an empty list
    otherwise (no attached behavioral hooks ⇒ no block, mirroring the inline
    ``if hook_lines:`` guard → byte-parity)."""

    name = "behavioral"

    async def provide(self, ctx: Any) -> list[HookBlock]:
        attached = getattr(ctx, "attached_hooks", None) or []
        block = render_behavioral_block(attached)
        if not block:
            return []
        return [HookBlock(kind="behavioral", content=block)]


def render_behavioral_block(attached_hooks: Any) -> str:
    """Render the ``## Active Behavioral Hooks`` block from attached hooks (byte-parity).

    Reproduces the inline factory synthesis exactly: one ``- **{name}** ({event}):
    {description or trigger}`` line per hook that carries a ``name``; the header +
    preamble + ``"\\n".join(lines)``. Returns ``""`` when no hook carries a name (the
    inline path appended nothing in that case)."""
    if not attached_hooks:
        return ""
    hook_lines: list[str] = []
    for hook in attached_hooks:
        if not isinstance(hook, dict):
            continue
        name = hook.get("name", "")
        event = hook.get("event", "")
        trigger = hook.get("trigger", "")
        description = hook.get("description", "")
        if name:
            hook_lines.append(f"- **{name}** ({event}): {description or trigger}")
    if not hook_lines:
        return ""
    return (
        f"{_BEHAVIORAL_HEADER}\n\n"
        f"{_BEHAVIORAL_PREAMBLE}\n\n"
        + "\n".join(hook_lines)
    )
