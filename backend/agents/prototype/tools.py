"""agents/prototype/tools.py — LangChain tools for prototype agents."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from agents.prototype.artifact_store import PrototypeArtifactStore

# Root of the OpenDesign template folder
_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[3] / "skills" / "opendesign" / "design-templates"
)


def make_prototype_tools(template_id: str, artifact_store: PrototypeArtifactStore) -> list:
    """Return the full 6-tool set (used by legacy agents)."""

    def _read_template_file(relative_path: str) -> str:
        full_path = _TEMPLATES_DIR / template_id / relative_path
        if not full_path.is_file():
            return f"(file not found: {relative_path} in template '{template_id}')"
        try:
            return full_path.read_text(encoding="utf-8")
        except OSError as exc:
            return f"(read error: {exc})"

    @tool
    def read_template_seed() -> str:
        """Read this template's starter HTML from assets/template.html.
        NOTE: Pre-injected into context as '=== TEMPLATE SEED ==='.
        """
        return _read_template_file("assets/template.html")

    @tool
    def read_layout_reference() -> str:
        """Read this template's layout library from references/layouts.md.
        NOTE: Pre-injected into context as '=== TEMPLATE REFERENCE (layouts.md) ==='.
        """
        return _read_template_file("references/layouts.md")

    @tool
    def read_checklist() -> str:
        """Read this template's self-review checklist from references/checklist.md.
        NOTE: Pre-injected into context as '=== TEMPLATE REFERENCE (checklist.md) ==='.
        """
        return _read_template_file("references/checklist.md")

    @tool
    def todo_write(tasks: list[str]) -> str:
        """Declare your section/page plan before writing any HTML."""
        if not tasks:
            return "(no tasks provided)"
        return "Section plan noted:\n" + "\n".join(f"  ☐ {t}" for t in tasks)

    @tool
    def emit_artifact(html: str, title: str = "Prototype") -> str:
        """Emit the final HTML artifact.

        Call this ONCE after completing all tasks.
        The html must be the COMPLETE document (<!doctype html>...).
        """
        artifact_store.set(html.strip(), title)
        return f"✓ Artifact stored: {title!r} ({len(html):,} chars)"

    @tool
    def report_task_complete(task_number: int, task_title: str, summary: str = "") -> str:
        """Report that a build task has been completed.

        Args:
            task_number: The task number (1, 2, 3, ...).
            task_title: The task title.
            summary: Brief summary of what was built.
        """
        artifact_store.mark_task_complete(task_number, task_title, summary)
        return f"✓ Task {task_number} complete: {task_title}"

    return [read_template_seed, read_layout_reference, read_checklist,
            todo_write, emit_artifact, report_task_complete]


def make_prototype_emit_only_tools(artifact_store: PrototypeArtifactStore) -> list:
    """Minimal 2-tool set for build and validate agents."""

    @tool
    def emit_artifact(html: str, title: str = "Prototype") -> str:
        """Emit the complete HTML prototype artifact.

        Call this ONCE after building/validating. The html must start with <!doctype html>.

        Args:
            html: Complete HTML document.
            title: Human-readable title for the prototype.
        """
        artifact_store.set(html.strip(), title)
        return f"✓ Artifact stored: {title!r} ({len(html):,} chars)"

    @tool
    def report_task_complete(task_number: int, task_title: str, summary: str = "") -> str:
        """Report that a build task has been completed.

        Args:
            task_number: The task number (1, 2, 3, ...).
            task_title: The task title.
            summary: Brief summary of what was built (optional).
        """
        artifact_store.mark_task_complete(task_number, task_title, summary)
        return f"✓ Task {task_number} complete: {task_title}"

    return [report_task_complete, emit_artifact]
