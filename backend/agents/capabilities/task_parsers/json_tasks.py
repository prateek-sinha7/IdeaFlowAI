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
    NAMING the offending task and the unknown dependency BEFORE any wave is built;
  * a wrapper object's ``contract.task_count`` (if present) must match the actual task count.

``parse_preferring_target(reply_text, sandbox=, target=, fallback_targets=)`` (A2) is an
ADDITIONAL entry point — ``parse(text)`` itself is unchanged for every existing caller. A
producing agent (plan-lead / review-planner / review-verdict) sometimes narrates the
finished plan instead of emitting the fence, even though it already wrote the SAME JSON to
disk; this prefers that on-disk file (the declared ``task_source.target``, then
``build/tasks.json``) over the reply text, so a perfect file on disk no longer loses to a
narrating reply.

Import purity (import-linter): this module imports ONLY stdlib (``json``, ``typing``) + the
``register`` decorator + the pure typed ``agents.workflows.plan`` (``Task``) — NEVER
``agents.execution_engine`` or ``app.*``. ``sandbox`` is accepted structurally (``Any``,
duck-typed ``.read(name) -> str | None``) so this module never imports the concrete
``RunSandbox`` class. The parser is pure ``text -> list[Task]`` (no engine state, no I/O of
its own — ``sandbox.read`` is the caller's I/O, reached only through the passed-in handle).
"""

from __future__ import annotations

import json
import re
from typing import Any, Sequence

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
    # EVERY fence is a candidate, not just the first. `search` took only the
    # leading fence, so a reply that opened with any other fenced block — an
    # echoed example from its own prompt, a snippet of prose, a stray ``` run —
    # handed that block to json.loads and failed with a perfect task list
    # sitting further down the same reply. Try each fence in order and keep the
    # first that actually parses; fall back to the first fence's content so the
    # error message still quotes something the author can recognise.
    first: str | None = None
    for m in _FENCE_RE.finditer(stripped):
        candidate = m.group(1).strip()
        if first is None:
            first = candidate
        if not candidate:
            continue
        try:
            json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        return candidate
    if first is not None:
        return first
    return stripped


@register(
    "task_parser",
    "json_tasks",
    user_allowed=True,
    description="Uses the task list an agent wrote as JSON, including which tasks depend on which. Independent tasks run in parallel waves; dependent ones wait their turn.",
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

        # Live run 692ca4ad: the Planner wrote 11 of 58 tasks, the scheduler built on
        # incomplete data. Check contract.task_count to catch partial plans at parse time.
        # Backward-compatible: only validates when the wrapper has a contract dict with a task_count.
        if isinstance(parsed, dict):
            contract = parsed.get("contract")
            if isinstance(contract, dict):
                task_count = contract.get("task_count")
                if task_count is not None:
                    # Accept an int or a numeric string (e.g. "58"); a float or a bool
                    # is not a count and is ignored rather than silently truncated.
                    expected = None
                    if isinstance(task_count, int) and not isinstance(task_count, bool):
                        expected = task_count
                    elif isinstance(task_count, str) and task_count.strip().isdigit():
                        expected = int(task_count)
                    if expected is not None and expected != len(tasks):
                        raise ValueError(
                            f"json_tasks: plan incomplete - contract.task_count={expected} "
                            f"but {len(tasks)} task(s) present"
                        )

        return tasks

    def parse_preferring_target(
        self,
        reply_text: str,
        *,
        sandbox: Any = None,
        target: str | None = None,
        fallback_targets: Sequence[str] = ("build/tasks.json",),
    ) -> list[Task]:
        """Parse the task list, preferring the file already written to disk (A2).

        The producing agent (plan-lead / review-planner / review-verdict) sometimes
        narrates the finished plan in its reply instead of emitting the ```json
        fence, even though it already wrote the SAME JSON to disk — the step's
        declared ``task_source.target`` (e.g. ``repair-tasks.md``) or the documented
        ``build/tasks.json``. A perfect file must not lose to a narrating reply.

        Tries, in order: ``target``, each of ``fallback_targets``, then
        ``reply_text`` (today's ``parse`` behaviour — unchanged for every existing
        caller). The first source that both exists (a non-empty ``sandbox.read``)
        and parses wins; each shape ``parse`` accepts (plain array / fenced / a
        ``{"tasks": [...]}`` wrapper) is reused via ``parse`` itself.

        Raises the same ``ValueError`` as ``parse`` once every source is
        exhausted, but the message now NAMES every source tried and why each
        failed — the plain ``parse`` error only ever reports the last one.
        """
        attempts: list[str] = []
        seen: set[str] = set()
        candidates: list[str] = []
        for name in ([target] if target else []) + list(fallback_targets):
            if name and name not in seen:
                seen.add(name)
                candidates.append(name)

        if sandbox is not None:
            for name in candidates:
                try:
                    content = sandbox.read(name)
                except Exception as exc:  # noqa: BLE001 — a bad sandbox must never crash the parse
                    attempts.append(f"{name}: could not read — {exc}")
                    continue
                if not content or not content.strip():
                    attempts.append(f"{name}: absent or empty")
                    continue
                try:
                    return self.parse(content)
                except ValueError as exc:
                    attempts.append(f"{name}: {exc}")

        try:
            return self.parse(reply_text)
        except ValueError as exc:
            attempts.append(f"reply text: {exc}")
            raise ValueError(
                "json_tasks: could not parse a task list from any source — "
                + "; ".join(attempts)
            ) from exc
