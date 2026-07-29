"""The ONE narrow custom precheck hook for prototype-plan — the single check
the generic, config-driven model_graded/precheck.py cannot express: the
``## Task N:`` headers must be sequentially numbered starting at 1, the
first task must be the HTML shell, and the last task must be validation.
This needs real parsing (splitting the response by header, inspecting the
first/last chunks), not a count/substring check.

Everything else about grading a prototype-plan response is data (the
scenario YAML's precheck:/rubric: blocks) — this is the only Python file in
this agent's folder.
"""

from __future__ import annotations

import re

_TASK_HEADER_RE = re.compile(r"^## Task (\d+):", re.MULTILINE)
_TASK_SPLIT_RE = re.compile(r"(?=^## Task \d+:)", re.MULTILINE)


def check(response: str) -> tuple[bool, str]:
    """Verify ``## Task N:`` headers are sequential starting at 1, Task 1
    builds the HTML shell, and the last task is validation."""
    numbers = [int(n) for n in _TASK_HEADER_RE.findall(response)]
    if not numbers:
        return False, "no '## Task N:' headers found"

    expected = list(range(1, len(numbers) + 1))
    if numbers != expected:
        return False, f"task numbers not sequential starting at 1: {numbers}"

    # _TASK_SPLIT_RE splits BEFORE every header, so chunk[0] is whatever
    # precedes the first "## Task" (the "<tasks>" wrapper open, normally) —
    # drop anything that isn't itself a task chunk before taking first/last.
    chunks = [c for c in _TASK_SPLIT_RE.split(response) if c.lstrip().startswith("## Task")]
    first, last = chunks[0], chunks[-1]

    if "shell" not in first.lower():
        return False, "Task 1 does not mention the HTML shell"
    if "valid" not in last.lower():
        return False, f"last task (Task {numbers[-1]}) does not mention validation"

    return True, f"{len(numbers)} sequential tasks, shell-first, validation-last"
