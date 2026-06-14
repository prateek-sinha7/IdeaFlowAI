"""agents/capabilities/task_parsers/json_tasks.py — the ``json_tasks`` parser.

The ``JsonTasksParser`` satisfies the ``TaskParser`` port (``capabilities.base``):
``parse(text) -> list[Task]``. Unlike ``heading_tasks`` (which slices ``## Task N:``
markdown headers), ``json_tasks`` parses a STRUCTURED JSON task list that carries the
forward scheduling surface the wave scheduler consumes — ``depends_on`` /
``conflict_keys`` / ``targets`` (Q11 / WAVE-02). It is the DEFAULT parser for the
``wave_scheduler`` strategy.

Accepted shapes (all → a list of ``Task``):
  * a plain JSON array of task objects ``[{...}, {...}]``;
  * a fenced ```json … ``` block wrapping the array (the fence is stripped first);
  * a wrapper object ``{"tasks": [...]}`` (the ``tasks`` key is used).

Validation (T-12-01-INPUT — untrusted agent-emitted JSON crosses into the scheduler):
  * malformed JSON raises a clear ``ValueError`` (no crash / bare stack);
  * a ``depends_on`` entry referencing an unknown task id raises a ``ValueError``
    NAMING the offending task and the unknown dependency BEFORE any wave is built.

Import purity (import-linter): this module imports ONLY stdlib (``json``) + the
``register`` decorator + the pure typed ``agents.workflows.plan`` (``Task``) — NEVER
``agents.execution_engine`` or ``app.*``. The parser is pure ``text -> list[Task]``
(no engine state, no I/O).
"""

from __future__ import annotations

import json
import re

from agents.capabilities.registry import register
from agents.workflows.plan import Task

# A fenced ```json … ``` (or bare ``` … ```) block, anywhere in the text. The agent may
# wrap its JSON plan in prose ("Here is the plan: ```json … ```"), so the fence is
# extracted from WITHIN the surrounding text, not just stripped when leading.
_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)


def _strip_json_fence(text: str) -> str:
    """Extract a fenced ```json … ``` (or bare ``` … ```) block, anywhere in ``text``.

    Tolerant: a non-fenced payload passes through unchanged (whitespace-stripped). When
    a fence is present (even amid prose) its inner content is returned for ``json.loads``.
    """
    stripped = (text or "").strip()
    m = _FENCE_RE.search(stripped)
    if m:
        return m.group(1).strip()
    return stripped


@register(
    "task_parser",
    "json_tasks",
    user_allowed=True,
    description="Parse a structured JSON task list with dependencies (drives the wave scheduler).",
)
class JsonTasksParser:
    """Structured JSON task-list → ``list[Task]`` parser (depends_on/conflict_keys/targets).

    Satisfies the ``TaskParser`` port structurally (``name`` + ``parse``). Pure: no
    engine state, no I/O. Carries the forward scheduling surface the wave scheduler
    consumes (WAVE-02).
    """

    name = "json_tasks"

    def parse(self, text: str) -> list[Task]:
        """Parse ``text`` into a list of canonical ``Task`` objects.

        Accepts a plain array, a fenced ```json block, or a ``{"tasks": [...]}``
        wrapper. Raises ``ValueError`` on malformed JSON or an unknown ``depends_on``
        ref (named) — BEFORE returning any task (so the scheduler never spawns on a
        bad plan). Returns ``[]`` for an empty payload.
        """
        payload = _strip_json_fence(text or "")
        if not payload:
            return []

        try:
            parsed = json.loads(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(
                f"json_tasks: could not parse task list as JSON — {exc}"
            ) from exc

        # Accept either a top-level list or a {"tasks": [...]} wrapper object.
        if isinstance(parsed, dict):
            raw_tasks = parsed.get("tasks")
            if raw_tasks is None:
                raise ValueError(
                    "json_tasks: a top-level object must carry a 'tasks' array"
                )
        else:
            raw_tasks = parsed

        if not isinstance(raw_tasks, list):
            raise ValueError(
                "json_tasks: expected a JSON array of task objects, "
                f"got {type(raw_tasks).__name__}"
            )

        tasks: list[Task] = []
        for entry in raw_tasks:
            if not isinstance(entry, dict):
                raise ValueError(
                    f"json_tasks: each task must be a JSON object, got {entry!r}"
                )
            if "id" not in entry:
                raise ValueError("json_tasks: every task must carry an 'id'")
            tid = str(entry["id"])
            tasks.append(
                Task(
                    id=tid,
                    title=str(entry.get("title", tid)),
                    body=str(entry.get("body", "")),
                    targets=[str(t) for t in (entry.get("targets") or [])],
                    depends_on=[str(d) for d in (entry.get("depends_on") or [])],
                    conflict_keys=[str(c) for c in (entry.get("conflict_keys") or [])],
                    done_when=[str(w) for w in (entry.get("done_when") or [])],
                )
            )

        # Reject DUPLICATE task ids BEFORE returning (WR-05 / T-12-06-INPUT). The wave
        # builder's ``by_id`` map is last-wins, so a duplicate would silently drop the
        # earlier task and can drive in-degrees negative — untrusted agent JSON must not
        # do that. Named ValueError pre-spawn (zero wave_runs/subagent_runs rows), placed
        # BEFORE the depends_on validation so the duplicate is reported first.
        seen_ids: set[str] = set()
        for t in tasks:
            if t.id in seen_ids:
                raise ValueError(f"json_tasks: duplicate task id '{t.id}'")
            seen_ids.add(t.id)

        # Validate every depends_on ref against the known task ids BEFORE returning
        # (named ValueError pre-spawn — the scheduler never sees a dangling dep).
        ids = {t.id for t in tasks}
        for t in tasks:
            for dep in t.depends_on:
                if dep not in ids:
                    raise ValueError(
                        f"json_tasks: task '{t.id}' depends_on unknown task id '{dep}'"
                    )

        return tasks
