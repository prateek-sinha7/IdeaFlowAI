"""agents/capabilities/validators/backlog_plan_coverage.py — the ``backlog_plan_coverage`` validator.

Runs after the Backlog Planner. Every coverage item — counted with the SAME
``collect_coverage_items`` the final assembly measures coverage on — must be in some
epic's ``covers`` or in ``"unassigned"``, and every item an epic covers must be named by
one of its slice tasks in ``build/story-tasks.json`` (the writers only see what a task
names). Run 3976f8ce's planner paged endpoints.json only to ~line 3000: API-34..API-76
were in no epic, its own check compared against its own short list and passed, and the
run failed at its last step at 83% coverage.

A gap is CRITICAL, so a step declaring ``fix: {max_attempts: N}`` is re-run with these
messages as its guidance; after the attempts the run fails at this step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.capabilities.backlog_assemble import (
    BACKLOG_PLAN_PATH,
    SOLUTION_DIR,
    SOLUTION_KINDS,
    STORY_TASKS_PATH,
    _parse_json,
    collect_coverage_items,
    parse_backlog_plan,
    parse_solution_kind,
)
from agents.capabilities.backlog_prep import _ITEM_ID_RE
from agents.capabilities.registry import register
from agents.capabilities.validators.severity import map_severity

_NAME = "backlog_plan_coverage"


@dataclass
class Issue:
    severity: str
    message: str
    validator: str = _NAME


def _unassigned_ids(unassigned: list) -> set[str]:
    ids: set[str] = set()
    for entry in unassigned or []:
        if isinstance(entry, str):
            ids.add(entry)
        elif isinstance(entry, dict):
            ids.update(
                v for v in (entry.get("id"), entry.get("item")) if isinstance(v, str)
            )
    return ids


def plan_coverage_gaps(sandbox: Any) -> tuple[list[str], list[str]]:
    """(ids in no epic and not unassigned, ids an epic covers but no slice task names)."""
    solution = {
        kind: parse_solution_kind(sandbox.read(f"{SOLUTION_DIR}/{kind}.json"))
        for kind in SOLUTION_KINDS
    }
    items = collect_coverage_items(solution)
    plan = parse_backlog_plan(sandbox.read(BACKLOG_PLAN_PATH))
    covered: set[str] = set()
    for epic in plan["epics"]:
        if isinstance(epic, dict):
            covered.update(c for c in epic.get("covers") or [] if isinstance(c, str))
    placed = covered | _unassigned_ids(plan["unassigned"])
    tasks = _parse_json(sandbox.read(STORY_TASKS_PATH))
    named: set[str] = set()
    for task in (tasks.get("tasks") if isinstance(tasks, dict) else None) or []:
        if isinstance(task, dict):
            named.update(_ITEM_ID_RE.findall(str(task.get("body") or "")))
            named.update(c for c in task.get("covers") or [] if isinstance(c, str))
    missing = [i for i in items if i not in placed]
    untasked = [i for i in items if i in covered and i not in named]
    return missing, untasked


@register(
    "validator",
    _NAME,
    user_allowed=True,
    description="Check that the backlog plan places every coverage item in an epic (or unassigned) and in a slice task.",
)
class BacklogPlanCoverageValidator:
    name = _NAME

    async def validate(self, target: Any) -> list[Issue]:
        sandbox = getattr(getattr(target, "runner", None), "sandbox", None)
        issues: list[Issue] = []
        if sandbox is None:
            return issues
        if sandbox.read(BACKLOG_PLAN_PATH) is None:
            issues.append(
                Issue(
                    "P0",
                    f"{BACKLOG_PLAN_PATH} was not written. Write it, and "
                    f"{STORY_TASKS_PATH}, as your prompt describes.",
                )
            )
        else:
            missing, untasked = plan_coverage_gaps(sandbox)
            if missing:
                issues.append(
                    Issue(
                        "P0",
                        (
                            f"{len(missing)} coverage item(s) are in no epic's covers and not in "
                            f"\"unassigned\": {', '.join(missing)}. Add each to the \"covers\" of the epic "
                            f"that builds it in {BACKLOG_PLAN_PATH}, and name it in one of that epic's slice "
                            f"tasks in {STORY_TASKS_PATH}. Both files exist: change them with edit_file. "
                            f"The complete list is build/coverage-items.json."
                        ),
                    )
                )
            if untasked:
                issues.append(
                    Issue(
                        "P0",
                        (
                            f"{len(untasked)} coverage item(s) are in an epic's covers but no slice task in "
                            f"{STORY_TASKS_PATH} names them: {', '.join(untasked)}. Add each to a slice task "
                            f"of its epic (its body's Cover list) with edit_file."
                        ),
                    )
                )
        await _record(target, issues)
        return issues


async def _record(target: Any, issues: list[Issue]) -> None:
    """Write a ``validation_results`` row via the handle (best-effort, D-10)."""
    record = getattr(getattr(target, "runner", None), "record_validation_result", None)
    if record is None:
        return
    worst = next(
        (
            map_severity(s)
            for s in ("P0", "P1", "P2", "P3")
            if any(i.severity == s for i in issues)
        ),
        None,
    )
    attempt = int((getattr(target, "task_meta", None) or {}).get("attempt", 0))
    await record(
        getattr(target, "step", "") or "",
        _NAME,
        severity=worst,
        attempt=attempt,
        issues=[{"severity": i.severity, "message": i.message} for i in issues],
    )
