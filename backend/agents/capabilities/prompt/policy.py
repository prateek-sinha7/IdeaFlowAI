"""agents/capabilities/prompt/policy.py — PromptAssemblyPolicy registry (08-05 / F1 / §30).

Lifts the factory's hardcoded inline block-append order (F1) into registered
``PromptAssemblyPolicy`` capabilities.  Three policies ship here:

``default``
    The full 7-block order — byte-identical to the old inline path for every
    existing agent.  The 5 characterization snapshots gate it (NEVER re-baseline).

``body_only`` (Requirement 29 AC1)
    Emits ONLY ``prompt_body`` — the system prompt is exactly the agent's AGENT.md.
    Drops six blocks: ``tool_availability``, ``injects``, ``guardrails``, ``skills``,
    ``hooks``, ``constitution``.  Losing the Constitution as a side effect of a
    formatting change is NOT acceptable — governed agents must use ``governance``
    instead (Requirement 29 AC3).

``governance`` (Requirement 29 AC2)
    A curated four-block order for agents that carry a Constitution or behavioral
    hooks: ``guardrails → hooks → constitution → prompt_body``.  Retains the
    three blocks that comprise governed-agent behaviour while still dropping the
    injection boilerplate (injects / skills / tool_availability) that Seam-2
    removal makes redundant.

Seam 1 vs Seam 2 (Phase Z, GAPS §0.3 step N+1)
    This module governs **seam 1 only** — the per-agent SYSTEM PROMPT assembled
    by ``assemble()`` above. ``prompt_policy`` (``default`` / ``body_only`` /
    ``governance``) still selects a real, distinct order here for every agent.
    **Seam 2** — the per-agent CONTEXT MESSAGE built by
    ``ExecutionEngine._compose_context_message`` — no longer varies by
    ``prompt_policy`` at all: Phase Z deleted every ``if not _is_migrated:``
    world-block branch there, so every agent gets the same (brief-to-first-
    agent-only, no pasted world state) treatment regardless of which policy
    named here it carries. ``default`` stays a valid, live policy name for THIS
    module; it no longer means anything for seam 2.

Block model
-----------
``assemble(blocks, ctx)`` takes a mapping ``category -> block(s)`` where each value is
either a single ``str`` block or a ``list[str]`` of blocks (skills/guardrails can be
multiple). Blocks are emitted in the policy's ``order`` tuple; an absent/empty category
contributes NOTHING, EXCEPT ``prompt_body`` in ``default``, which the old inline path
ALWAYS appended (even when empty).

Import purity (import-linter): imports ONLY the registry decorator + stdlib typing.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.registry import register

# The fixed prompt-block order (F1). MUST stay byte-identical to the factory's inline
# ``_compose_system_prompt`` order (backend/CLAUDE.md / RESEARCH Pitfall 2). 08-06's
# constitution fix plugs into the ``constitution`` slot — already present here.
#
# ``tool_availability`` (13-02 / F4) is FIRST: the anti-fabrication no-tools preamble
# must frame everything that follows. The factory emits the block ONLY for agents
# resolved to zero callable tools, so every tool-having agent's composition is
# byte-identical (its blocks dict never contains the key).
#
# ``skill_directive`` (spec 012 / R-13) used to sit alongside it. It is GONE: the
# deepagents SKILLS_SYSTEM_PROMPT already names every staged skill and its exact
# read path, so the factory block was a second, vaguer instruction about the same
# files. Removed from the order rather than left as an unused slot, so nothing can
# quietly start emitting it again.
DEFAULT_ORDER: tuple[str, ...] = (
    "tool_availability",
    "injects",
    "guardrails",
    "skills",
    "hooks",
    "constitution",
    "prompt_body",
)

# body_only — AGENT.md is the whole system prompt (Requirement 29 AC1).
# Dropping all six wrapper blocks means the Constitution is also absent — that is
# intentional for *ungoverned* agents, and the compiler warns when a governed agent
# (one with guardrails, hooks, or a Constitution) picks this order (Req 29 AC3/5).
BODY_ONLY_ORDER: tuple[str, ...] = ("prompt_body",)

# governance — preserves the three blocks that define governed-agent behaviour while
# dropping the Seam-2 injection boilerplate (Requirement 29 AC2).
GOVERNANCE_ORDER: tuple[str, ...] = (
    "guardrails",
    "hooks",
    "constitution",
    "prompt_body",
)

# The block join separator — the inline path used ``"\n\n".join(blocks)``.
_JOIN = "\n\n"


class _BasePolicy:
    """Shared ``assemble`` implementation for all policies.

    Subclasses set ``order`` and whether ``prompt_body`` is always emitted.
    """

    #: Ordered tuple of block-category names this policy emits.
    order: tuple[str, ...] = DEFAULT_ORDER
    #: When True the policy always emits ``prompt_body`` (even when absent/empty),
    #: matching the old inline path that unconditionally appended it.
    always_emit_body: bool = True

    def assemble(self, blocks: dict[str, Any], ctx: Any) -> str:
        """Compose the final system prompt from a ``category -> block(s)`` mapping.

        Emits categories from ``self.order`` in order; absent or empty entries are
        skipped (except ``prompt_body`` when ``always_emit_body`` is True).
        ``blocks[category]`` may be a ``str`` or a ``list[str]``.
        """
        ordered: list[str] = []
        for category in self.order:
            value = blocks.get(category)
            if category == "prompt_body" and self.always_emit_body:
                # The old inline path ALWAYS appended spec.prompt_body (even if empty),
                # so emit it unconditionally to preserve the exact join boundary.
                ordered.append("" if value is None else _as_one(value))
                continue
            if value is None:
                continue
            for block in _iter_blocks(value):
                if block:  # mirror the inline ``if content:`` / non-empty guards
                    ordered.append(block)
        return _JOIN.join(ordered)


@register(
    "prompt",
    "default",
    user_allowed=True,
    description=(
        "The default prompt-assembly policy "
        "(tool_availability, injects, guardrails, skills, hooks, constitution, body)."
    ),
)
class DefaultPromptAssemblyPolicy(_BasePolicy):
    """Full 7-block order — byte-identical to the pre-08-05 inline path.

    The 5 characterization snapshots gate this output; NEVER re-baseline.
    """

    name = "default"
    order = DEFAULT_ORDER
    always_emit_body = True


@register(
    "prompt",
    "body_only",
    user_allowed=True,
    description=(
        "Body-only prompt policy — system prompt is exactly the agent's AGENT.md. "
        "Do NOT use for governed agents (use 'governance' to retain the Constitution)."
    ),
)
class BodyOnlyPromptAssemblyPolicy(_BasePolicy):
    """Body-only policy: ``prompt_body`` is the entire system prompt (Requirement 29 AC1).

    Emits ONLY ``prompt_body`` — six blocks are dropped: ``tool_availability``,
    ``injects``, ``guardrails``, ``skills``, ``hooks``, ``constitution``.
    The compiler warns when a governed agent (one with ``guardrails``, ``hooks``, or
    a ``constitution`` in its build context) selects this policy (Req 29 AC3/5).
    """

    name = "body_only"
    order = BODY_ONLY_ORDER
    always_emit_body = True


@register(
    "prompt",
    "governance",
    user_allowed=True,
    description=(
        "Governance prompt policy for agents with a Constitution or behavioral hooks "
        "(guardrails, hooks, constitution, body)."
    ),
)
class GovernancePromptAssemblyPolicy(_BasePolicy):
    """Governance policy: retains the three governed-agent blocks (Requirement 29 AC2).

    Order: ``guardrails → hooks → constitution → prompt_body``.  Drops the Seam-2
    injection boilerplate (``injects``, ``skills``, ``tool_availability``) while
    preserving every block that defines governed-agent behaviour.
    """

    name = "governance"
    order = GOVERNANCE_ORDER
    always_emit_body = True


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
