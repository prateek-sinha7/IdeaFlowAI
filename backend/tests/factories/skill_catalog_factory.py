"""Builders for on-disk global Skills catalog folders (``<root>/<id>/SKILL.md``)."""

from __future__ import annotations

import textwrap
from pathlib import Path


def write_catalog_skill(
    root: Path, skill_id: str, *, siblings: dict[str, str] | None = None
) -> Path:
    """Create ``<root>/<skill_id>/SKILL.md`` (+ optional sibling files); return the dir."""
    skill_dir = root / skill_id
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {skill_id}
            description: A test skill.
            ---
            Body of {skill_id}.
            """
        ),
        encoding="utf-8",
    )
    for name, text in (siblings or {}).items():
        (skill_dir / name).write_text(text, encoding="utf-8")
    return skill_dir
