"""agents/capabilities/prompt/policy.py — the default PromptAssemblyPolicy (08-05 / F1 / §30).

Lifts the factory's hardcoded ``blocks.append`` order (F1) into a registered
``PromptAssemblyPolicy`` capability. The factory's ``_compose_system_prompt`` joined a
FIXED block order with ``"\\n\\n"``:

    injects → guardrails → skills → hooks → constitution → prompt_body

(see ``backend/CLAUDE.md`` § "Skills vs Guardrails vs Hooks"). This policy reproduces
that order + join BYTE-IDENTICALLY so the composed prompt is unchanged for every
existing agent (the 5 characterization snapshots gate it — RESEARCH Pitfall 2; NEVER
re-baseline).

Block model
-----------
``assemble(blocks, ctx)`` takes a mapping ``category -> block(s)`` where each value is
either a single ``str`` block or a ``list[str]`` of blocks (skills/guardrails can be
multiple). Blocks are emitted in ``DEFAULT_ORDER``; an absent/empty category contributes
NOTHING (it was simply not appended in the inline path), EXCEPT ``prompt_body``, which
the inline path ALWAYS appended (even when empty) — so it is always emitted to preserve
the exact join. Empty-string blocks inside a list are dropped (mirroring the inline
``if content:`` guards). The present blocks are joined with ``"\\n\\n"`` — byte-identical
to ``"\\n\\n".join(blocks)``.

The constitution slot (F4) plugs in here in 08-06; this plan feeds it the factory's
existing ``_inject_constitution`` output unchanged.

Import purity (import-linter): imports ONLY the registry decorator + stdlib typing.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.registry import register

# The fixed prompt-block order (F1). MUST stay byte-identical to the factory's inline
# ``_compose_system_prompt`` order (backend/CLAUDE.md / RESEARCH Pitfall 2). 08-06's
# constitution fix plugs into the ``constitution`` slot — already present here.
DEFAULT_ORDER: tuple[str, ...] = (
    "injects",
    "guardrails",
    "skills",
    "hooks",
    "constitution",
    "prompt_body",
)

# The block join separator — the inline path used ``"\n\n".join(blocks)``.
_JOIN = "\n\n"


@register("prompt", "default", user_allowed=True)
class DefaultPromptAssemblyPolicy:
    """The default ``PromptAssemblyPolicy`` — fixed order, ``"\\n\\n"`` join (``name='default'``).

    Reproduces the factory's inline ``blocks.append`` composition byte-for-byte:
    emits the present blocks in ``DEFAULT_ORDER`` joined with ``"\\n\\n"``. The
    ``prompt_body`` category is ALWAYS emitted (the inline path always appended it);
    every other category is emitted only when it carries a non-empty block (mirroring
    the inline ``if content:`` / ``if injects`` guards).
    """

    name = "default"
    order = DEFAULT_ORDER

    def assemble(self, blocks: dict[str, Any], ctx: Any) -> str:
        """Compose the final system prompt from a ``category -> block(s)`` mapping.

        Byte-identical to the inline ``"\\n\\n".join(blocks)`` over the same ordered,
        present blocks. ``blocks[category]`` may be a ``str`` or a ``list[str]``;
        ``None``/empty entries are skipped (except ``prompt_body``, always emitted).
        """
        ordered: list[str] = []
        for category in self.order:
            value = blocks.get(category)
            if category == "prompt_body":
                # The inline path ALWAYS appended spec.prompt_body (even if empty),
                # so emit it unconditionally to preserve the exact join boundary.
                ordered.append("" if value is None else _as_one(value))
                continue
            if value is None:
                continue
            for block in _iter_blocks(value):
                if block:  # mirror the inline ``if content:`` / non-empty guards
                    ordered.append(block)
        return _JOIN.join(ordered)


def _iter_blocks(value: Any) -> list[str]:
    """Normalise a block value to a list of string blocks (single str → one-item list)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [b for b in value]
    return [str(value)]


def _as_one(value: Any) -> str:
    """Collapse a (possibly multi-block) value into a single string for prompt_body."""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return _JOIN.join(b for b in value if b)
    return str(value)
