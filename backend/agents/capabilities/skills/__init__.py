"""agents/capabilities/skills/ — the SkillProvider capability package (08-05 / F3 / SKILL-01 / §30).

Importing this package imports ``providers``, firing each
``@register("skill", <kind>)`` decorator so ``discover()`` (which best-effort imports
this package) binds every skill provider into the registry.

F3 lift (D-08 / SKILL-01): the factory's inline flattened skill list (the inline loop
that appended each ``ctx.attached_skills`` entry's ``content`` to the prompt blocks)
becomes registered ``SkillProvider`` capabilities with a provider INTERFACE + VERSION
metadata. The four
sources are ``ui`` (the live UI-attached skills — today's only source), ``disk``,
``template``, and ``repo`` (forward sources, inert until wired — they contribute nothing
for existing agents, so composition stays byte-identical).

Each ``provide(ctx)`` returns a list of ``SkillBlock`` descriptors carrying ``content``
+ ``version`` (so a stale skill block is detectable — SKILL-01) instead of a bare
content string. The factory flattens ``[b.content for b in blocks if b.content]`` into
the prompt's ``skills`` slot — byte-identical to the inline flattened list for existing
agents.

Import purity (import-linter): imports ONLY the registry decorator + stdlib typing.
"""

from __future__ import annotations

from agents.capabilities.skills import providers  # noqa: F401 — import side effect: @register
from agents.capabilities.skills.providers import SkillBlock

__all__ = ["providers", "SkillBlock"]
