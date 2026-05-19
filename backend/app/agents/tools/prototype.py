"""Prototype tools for the html-prototype-builder deep agent.

These tools replicate what OpenDesign's agent does via the Read file tool
when executing the SKILL.md workflow:

  Step 0 — Pre-flight:
    1. Read assets/template.html            → read_template_seed()
    2. Read references/layouts.md           → read_layout_reference()
    3. Read references/checklist.md         → read_checklist()
    (DESIGN.md is already in the system prompt — no tool needed)

  Step 1 — Copy the seed
  Step 2 — Plan the section list            → todo_write()
  Step 3 — Paste and fill
  Step 4 — Self-check against checklist
  Step 5 — Emit artifact                    → emit_artifact()

The artifact accumulator is returned via ArtifactStore so the runner
can pull the final HTML after the agent finishes.
"""

from __future__ import annotations

import re
from pathlib import Path

from langchain_core.tools import tool

# Root of the opendesign template folder
_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "skills" / "opendesign" / "design-templates"
)


# ---------------------------------------------------------------------------
# Artifact store — collects the final HTML emitted by emit_artifact()
# ---------------------------------------------------------------------------


class ArtifactStore:
    """Accumulates the HTML artifact the agent writes via emit_artifact()."""

    def __init__(self) -> None:
        self._html: str = ""
        self._title: str = ""

    def set(self, html: str, title: str = "") -> None:
        self._html = html
        self._title = title

    @property
    def html(self) -> str:
        return self._html

    @property
    def title(self) -> str:
        return self._title

    def is_set(self) -> bool:
        return bool(self._html.strip())


# ---------------------------------------------------------------------------
# Tool factory
# ---------------------------------------------------------------------------


def make_prototype_tools(template_id: str, artifact_store: ArtifactStore) -> list:
    """Return prototype tools bound to the given template and artifact store."""

    def _read_template_file(relative_path: str) -> str:
        full_path = _TEMPLATES_DIR / template_id / relative_path
        if not full_path.is_file():
            return f"(file not found: {relative_path} in {template_id})"
        try:
            return full_path.read_text(encoding="utf-8")
        except OSError as exc:
            return f"(read error: {exc})"

    @tool
    def read_template_seed() -> str:
        """Read this template's starter HTML from assets/template.html.

        The SKILL.md Workflow Step 0 says 'Read assets/template.html end-to-end
        before writing anything.' Call this first. The seed contains the
        iPhone frame (mobile), the section class system (web-prototype), or
        the dashboard chrome — whatever structural scaffolding this template
        provides.

        Replace the :root design tokens in the seed with the active DESIGN.md
        tokens from your system prompt.
        """
        return _read_template_file("assets/template.html")

    @tool
    def read_layout_reference() -> str:
        """Read this template's layout library from references/layouts.md.

        Contains the paste-ready section skeletons. The SKILL.md Workflow
        says 'Read references/layouts.md so you know which section skeletons
        exist. Don't write a section type that isn't covered — pick the
        closest layout and adapt.'
        """
        return _read_template_file("references/layouts.md")

    @tool
    def read_checklist() -> str:
        """Read this template's self-review checklist from references/checklist.md.

        The SKILL.md Workflow Step 4 says 'Run through references/checklist.md
        top to bottom. Every P0 item must pass before you move on.'
        Call this before emitting the final artifact.
        """
        return _read_template_file("references/checklist.md")

    @tool
    def todo_write(tasks: list[str]) -> str:
        """Declare your section list before writing any HTML.

        The SKILL.md Workflow Step 2 says 'State the chosen list in one
        sentence to the user before writing — they can redirect cheaply now
        and not after 200 lines of HTML.'

        Example: todo_write(["1. Hero section", "2. Features grid", "3. CTA"])
        """
        if not tasks:
            return "(no tasks provided)"
        return "Tasks noted:\n" + "\n".join(f"  ☐ {t}" for t in tasks)

    @tool
    def emit_artifact(html: str, title: str = "Prototype") -> str:
        """Emit the final HTML artifact.

        Call this once when the prototype is complete and all P0 checklist
        items pass. The html argument must be a complete self-contained
        HTML document starting with <!doctype html>.

        This is equivalent to wrapping your output in <artifact> tags.
        """
        artifact_store.set(html.strip(), title)
        return f"✓ Artifact stored: {title} ({len(html):,} bytes)"

    return [read_template_seed, read_layout_reference, read_checklist,
            todo_write, emit_artifact]
