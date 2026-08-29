"""skills_catalog.py — folder-scan loader for the global Skills catalog.

Distinct from ``app/agents/skills.py`` (per-agent runtime skill *injection* —
one skill slot per agent_id, resolved user-override -> admin-global ->
DEFAULT_SKILLS). This module serves the browsable Skills *catalog* shown in
the Library UI: independent, attachable skill entries (ECC/Superpowers), each
optionally compatible with many agents or none.

Each skill lives in ``skills/global/{skill_id}/SKILL.md`` with YAML
frontmatter for metadata and a markdown body for the skill's content — same
convention as ``agents/prompts/{agent_id}/AGENT.md`` (see agents/loader.py).
Adding a new skill is a folder-drop: no registry, no code change, no restart-
time list to maintain. The catalog is scanned fresh on first request and
cached; call ``clear_cache()`` (e.g. in tests) to force a re-scan.

``skills/global/`` holds the real, canonical skill packages (migrated
verbatim from the top-level ``skills/{ecc,superpowers,gsd,opendesign}/``
source) — only ``name`` + ``description`` are guaranteed there, matching the
real Claude-Code skill format. ``title``/``source``/``sourceLabel``/
``category``/``tags`` are UI-filter metadata the
frontend catalog historically assigned; present when a skill has been fully
migrated (see backend/skills/global/{accessibility,api-design,brainstorming,
systematic-debugging} for the pattern), optional otherwise — an absent or
blank ``category`` loads as ``uncategorized`` so the skill still has a pill
of its own to be filtered by (ISS-329).

``display_name`` mirrors the workflow catalog's ``display_name`` field
(app/api/workflows.py) — the UI label, distinct from ``name`` (the real
slug/id-ish value from the skill's own frontmatter). Falls back to ``name``
when absent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter  # python-frontmatter

logger = logging.getLogger(__name__)

# backend/ root (this file lives in backend/app/agents/)
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_GLOBAL_SKILL_DIR = _BACKEND_DIR / "skills" / "global"


@dataclass
class GlobalSkillEntry:
    id: str
    name: str
    display_name: str
    description: str
    content: str
    isBeta: bool
    category: str = ""
    tags: list[str] = field(default_factory=list)
    compatible_agents: list[str] = field(default_factory=list)


class GlobalSkillError(Exception):
    """Raised when a SKILL.md file has invalid or missing fields."""


_GLOBAL_SKILL_CACHE: list[GlobalSkillEntry] | None = None


def clear_cache() -> None:
    global _GLOBAL_SKILL_CACHE
    _GLOBAL_SKILL_CACHE = None


# Map skill categories to Lucide icon names (frontend renders these as components)
_CATEGORY_TO_ICON = {
    "collaboration": "Users",
    "debugging": "Bug",
    "meta": "Settings",
    "planning": "Map",
    "research": "Lightbulb",
    "security": "Shield",
    "specialist": "Award",
    "testing": "TestTube",
    "workflow": "GitBranch",
}


def _get_icon_for_category(category: str) -> str:
    """Resolve a skill category to its Lucide icon name, defaulting to Award."""
    return _CATEGORY_TO_ICON.get(category, "Award")


def _load_one(skill_dir: Path) -> GlobalSkillEntry:
    skill_id = skill_dir.name
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        raise GlobalSkillError(f"SKILL.md not found: {skill_file}")

    post = frontmatter.loads(skill_file.read_text(encoding="utf-8"))
    metadata = post.metadata

    required = ("name", "description")
    missing = [f for f in required if f not in metadata]
    if missing:
        raise GlobalSkillError(
            f"{skill_id}: SKILL.md missing required field(s): {missing}"
        )

    return GlobalSkillEntry(
        id=skill_id,
        name=metadata["name"],
        display_name=metadata.get("display_name", metadata["name"]),
        description=metadata["description"],
        content=post.content,
        # ISS-329: an absent (or blank) category used to become "", which
        # app/api/skills.py drops out of the pill list it derives — the card
        # then renders a blank badge and no category pill can ever select it.
        # A real value keeps every skill reachable through a pill of its own.
        category=metadata.get("category") or "uncategorized",
        isBeta=metadata.get("isBeta", False),
        tags=list(metadata.get("tags", [])),
        compatible_agents=list(metadata.get("compatible_agents", [])),
    )


def list_global_skills() -> list[GlobalSkillEntry]:
    """Scan skills/global/ for every {skill_id}/SKILL.md and return parsed entries.

    Results are cached in-process after the first scan; call clear_cache() to
    force a re-scan (e.g. after adding a skill folder in a running dev server,
    or between test cases).
    """
    global _GLOBAL_SKILL_CACHE
    if _GLOBAL_SKILL_CACHE is not None:
        return _GLOBAL_SKILL_CACHE

    if not _GLOBAL_SKILL_DIR.exists():
        logger.warning("Skills catalog directory not found: %s", _GLOBAL_SKILL_DIR)
        _GLOBAL_SKILL_CACHE = []
        return _GLOBAL_SKILL_CACHE

    entries = []
    for skill_dir in sorted(_GLOBAL_SKILL_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        try:
            entries.append(_load_one(skill_dir))
        except GlobalSkillError:
            logger.exception("Skipping invalid skill catalog entry: %s", skill_dir.name)

    _GLOBAL_SKILL_CACHE = entries
    return _GLOBAL_SKILL_CACHE
