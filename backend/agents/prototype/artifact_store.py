"""agents/prototype/artifact_store.py — Shared HTML artifact store for prototype pipeline."""

from __future__ import annotations


class PrototypeArtifactStore:
    """Shared artifact store for all four prototype pipeline agents.

    All four agents (specify, plan, build, validate) share the same store
    so emit_artifact() in one agent is readable by the next.
    """

    def __init__(self) -> None:
        self._html: str = ""
        self._title: str = ""
        self._completed_tasks: list[dict] = []

    def set(self, html: str, title: str = "") -> None:
        self._html = html.strip()
        self._title = title

    @property
    def html(self) -> str:
        return self._html

    @property
    def title(self) -> str:
        return self._title

    def is_set(self) -> bool:
        return bool(self._html)

    def mark_task_complete(self, task_number: int, task_title: str, summary: str = "") -> None:
        """Record task completion for progress display."""
        self._completed_tasks.append({
            "number": task_number,
            "title": task_title,
            "summary": summary,
        })

    @property
    def completed_tasks(self) -> list[dict]:
        return list(self._completed_tasks)

    @property
    def completed_task_count(self) -> int:
        return len(self._completed_tasks)

    def clear(self) -> None:
        self._html = ""
        self._title = ""
        self._completed_tasks = []


# Backward-compat alias
ArtifactStore = PrototypeArtifactStore
