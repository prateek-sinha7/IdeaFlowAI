"""agents/capabilities/skills/providers.py — the skill_provider capabilities (08-05 / F3 / SKILL-01).

Lifts the factory's inline flattened skill list (F3) into registered ``SkillProvider``
capabilities with a provider INTERFACE + VERSION metadata (SKILL-01). The inline path was:

    for skill in ctx.attached_skills:
        content = skill.get("content", "")
        if content:
            blocks.append(content)

i.e. a flattened list of content strings with NO version notion. The lift replaces that
with four registered providers — ``ui`` / ``disk`` / ``template`` / ``repo`` — each
returning a list of ``SkillBlock`` descriptors carrying ``content`` + ``version``:

  * ``ui``       — the LIVE source: ``ctx.attached_skills`` (UI-attached per request).
                   Reads each skill's ``content`` and ``version`` (defaulting to
                   ``"ui"`` when the UI omits one). This is the ONLY source that
                   contributes blocks for existing agents → byte-identical composition.
  * ``disk`` /
    ``template`` /
    ``repo``     — forward sources (inert until a backing store is wired). They return
                   an EMPTY list today, so they contribute nothing to the composed
                   prompt — preserving byte-identity (parity). The provider interface +
                   versioning is in place for when those sources land.

The factory flattens ``[b.content for b in provider.provide(ctx) if b.content]`` into the
prompt ``skills`` slot — byte-identical to the inline flattened content list (the 5
characterization snapshots gate it; NEVER re-baseline).

Import purity (import-linter): imports ONLY the registry decorator + stdlib typing — NO
``app.*`` import, NO kernel import.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.capabilities.registry import register

# The default version label for a UI-attached skill that omits an explicit version.
_UI_DEFAULT_VERSION = "ui"


@dataclass(frozen=True)
class SkillBlock:
    """A versioned skill block (SKILL-01).

    Replaces the bare content string the inline flattened skill list produced: carries
    the ``content`` injected into the prompt PLUS a ``version`` notion (and the
    originating ``source`` / ``name`` when known) so a stale skill block is detectable.
    The factory consumes ``content`` for the prompt; ``version``/``source``/``name`` are
    the SKILL-01 metadata.
    """

    content: str
    version: str = _UI_DEFAULT_VERSION
    name: str = ""
    source: str = ""


@register("skill", "ui", user_allowed=True)
class UiSkillProvider:
    """The LIVE skill source — UI-attached skills (``name='ui'``).

    Reads ``ctx.attached_skills`` (the per-request UI attachments, the only source today)
    and returns a ``SkillBlock`` per skill carrying its ``content`` + ``version``. Skills
    with empty content are dropped (mirroring the inline ``if content:`` guard), so the
    flattened content list is byte-identical to the inline path for existing agents.
    """

    name = "ui"

    async def provide(self, ctx: Any) -> list[SkillBlock]:
        attached = getattr(ctx, "attached_skills", None) or []
        blocks: list[SkillBlock] = []
        for skill in attached:
            content = skill.get("content", "") if isinstance(skill, dict) else ""
            if not content:
                continue  # mirror the inline ``if content:`` guard (byte-parity)
            blocks.append(
                SkillBlock(
                    content=content,
                    version=str(skill.get("version", _UI_DEFAULT_VERSION)),
                    name=str(skill.get("name", "")),
                    source="ui",
                )
            )
        return blocks


class _EmptyForwardSkillProvider:
    """Base for the inert forward skill sources (disk/template/repo).

    These sources have no backing store wired yet, so they contribute NOTHING to the
    composed prompt — preserving byte-identity for existing agents. The provider
    interface + versioning is in place for when each source lands (SKILL-01)."""

    name = ""

    async def provide(self, ctx: Any) -> list[SkillBlock]:
        return []


@register("skill", "disk", user_allowed=True)
class DiskSkillProvider(_EmptyForwardSkillProvider):
    """Disk-backed skills (``name='disk'``) — inert until a disk source is wired."""

    name = "disk"


@register("skill", "template", user_allowed=True)
class TemplateSkillProvider(_EmptyForwardSkillProvider):
    """Template-bundled skills (``name='template'``) — inert until wired."""

    name = "template"


@register("skill", "repo", user_allowed=True)
class RepoSkillProvider(_EmptyForwardSkillProvider):
    """Repo-backed skills (``name='repo'``) — inert until a repo source is wired."""

    name = "repo"
