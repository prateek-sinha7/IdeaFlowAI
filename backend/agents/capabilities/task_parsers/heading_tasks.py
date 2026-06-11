"""agents/capabilities/task_parsers/heading_tasks.py — the ``heading_tasks`` parser.

The ``HeadingTasksParser`` satisfies the ``TaskParser`` port (``capabilities.base``):
``parse(text) -> list[Task]``. It is a clean verbatim lift of the engine's two
pure staticmethods — ``ExecutionEngine._count_plan_tasks`` (the ``## Task N:`` /
``<tasks>…</tasks>`` header detection) and ``ExecutionEngine._extract_task_block``
(per-block header→next-``##`` slicing) — so the byte-identical task wording the
prototype build loop relied on is preserved (INV-3 / INV-12 move-don't-copy).

Import purity (import-linter): this module imports only stdlib + the pure typed
``agents.workflows.plan`` (``Task``) — NEVER ``agents.execution_engine`` or
``app.*``. The parser itself is pure ``text -> list[Task]`` (no engine state, no
I/O), so the build loop AND its unit tests share the exact same detection logic.
"""

from __future__ import annotations

import re

from agents.capabilities.registry import register
from agents.workflows.plan import Task


def _count_plan_tasks(plan_output: str) -> tuple[int, str]:
    """Count ``## Task N:`` headers in the planner output → ``(count, task_source)``.

    Looks for top-level ``## Task N:`` headers directly; if none are present,
    falls back to the content inside a ``<tasks>…</tasks>`` wrapper and counts
    there. The returned ``count`` is the RAW number of task headers found —
    ``0`` means the planner did NOT emit a task plan. ``task_source`` is the text
    the headers were found in (the whole output, or the unwrapped ``<tasks>``
    body) so :func:`_extract_task_block` slices each ``## Task N:`` block from the
    right text.

    Lifted verbatim from ``ExecutionEngine._count_plan_tasks`` (pure — no I/O, no
    engine state).
    """
    text = plan_output or ""
    task_matches = re.findall(r"^##\s+Task\s+(\d+)", text, re.MULTILINE)
    task_source = text
    if not task_matches:
        tasks_section = re.search(r"<tasks>([\s\S]*?)</tasks>", text, re.IGNORECASE)
        if tasks_section:
            task_source = tasks_section.group(1)
            task_matches = re.findall(r"^##\s+Task\s+(\d+)", task_source, re.MULTILINE)
    return len(task_matches), task_source


def _extract_task_block(task_source: str, task_num: int) -> str:
    """Return the full ``## Task {n}: …`` block (header + body) from the plan.

    The block runs from its ``## Task {n}:`` header up to (but not including)
    the next ``## Task`` / ``## `` header or end-of-text. Returns ``""`` when
    the numbered task can't be located.

    Lifted verbatim from ``ExecutionEngine._extract_task_block``.
    """
    m = re.search(
        rf"^##\s+Task\s+{task_num}\b.*$",
        task_source or "",
        re.MULTILINE,
    )
    if not m:
        return ""
    start = m.start()
    # End at the next top-level "## " heading (the next task or any ## section).
    nxt = re.search(r"^##\s+", task_source[m.end():], re.MULTILINE)
    end = m.end() + nxt.start() if nxt else len(task_source)
    return task_source[start:end].strip()


def _extract_task_title(block: str, task_num: int) -> str:
    """Best-effort title from the ``## Task {n}: <title>`` header line.

    Pure, non-load-bearing helper for ``Task.title`` (the byte-identical contract
    is ``Task.body`` == the ``_extract_task_block`` slice). Returns the text after
    the colon on the header line; falls back to ``Task {n}`` when absent.
    """
    if not block:
        return f"Task {task_num}"
    first_line = block.splitlines()[0] if block.splitlines() else ""
    if ":" in first_line:
        title = first_line.split(":", 1)[1].strip()
        if title:
            return title
    return f"Task {task_num}"


@register("task_parser", "heading_tasks", user_allowed=True)
class HeadingTasksParser:
    """``## Task N:`` (with ``<tasks>`` fallback) plan-text → ``list[Task]`` parser.

    Satisfies the ``TaskParser`` port structurally (``name`` + ``parse``). Pure:
    no engine state, no I/O. Each returned ``Task.body`` is byte-identical to the
    engine's ``_extract_task_block`` slice (INV-3).
    """

    name = "heading_tasks"

    def parse(self, text: str) -> list[Task]:
        """Parse ``text`` into a list of canonical ``Task`` objects.

        Returns ``[]`` when no ``## Task N:`` headers are found (the caller — the
        build loop — then runs a single fallback pass, exactly as today).
        """
        count, task_source = _count_plan_tasks(text or "")
        tasks: list[Task] = []
        for task_num in range(1, count + 1):
            block = _extract_task_block(task_source, task_num)
            tasks.append(
                Task(
                    id=str(task_num),
                    title=_extract_task_title(block, task_num),
                    body=block,
                )
            )
        return tasks
