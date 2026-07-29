"""The custom precheck hook for prototype-plan.

The structural checks the config-driven `precheck` block in
prototype_plan_rubric.yaml cannot express: the `## Task N:` numbers must form a
complete 1..N sequence, and the last task must be the validation task. A count
of headers cannot see a gap, a duplicate, or what the final task is.

Both are real downstream breaks. The engine iterates the parsed tasks one
sub-agent at a time, so a gap or a duplicate number means a page is silently
never built, and a plan that does not end in validation ships a prototype whose
routes, tokens and handlers were never checked.

Referenced from the rubric as `./prototype_plan_validate.py:check`.
"""

from __future__ import annotations

import re

# A task header, split into its number and its title:
#   "## Task 2: Dashboard (`#/dashboard`)"  ->  ("2", "Dashboard (`#/dashboard`)")
_TASK_HEADER_RE = re.compile(r"^## Task (\d+):[ \t]*(.*)$", re.MULTILINE)

# AGENT.md names the final task "Final Wiring & Validation"; the invariant it
# states is that a validation task is always last. Match the word, not a title.
_VALIDATION_RE = re.compile(r"(?i)valid")


def check(response: str) -> tuple[bool, str]:
    """Verify the task numbers are a complete 1..N run and the last is validation.

    Returns (passed, reason). The reason is recorded on pass as well as fail —
    on pass it names the sequence length and the final task actually inspected,
    which is how you confirm the check is running rather than silently matching
    nothing.
    """
    headers = _TASK_HEADER_RE.findall(response)

    # Matching nothing must FAIL, never silently pass. A plan with no parseable
    # headers is exactly the CRITICAL FAILURE AGENT.md describes — the build
    # agent receives nothing — and "no tasks" must never read as "no gaps".
    if not headers:
        return False, "no `## Task N:` headers found"

    numbers = [int(number) for number, _ in headers]
    sequence_failure = _sequence_failure(numbers)
    if sequence_failure is not None:
        return False, sequence_failure

    last_title = headers[-1][1].strip()
    if not _VALIDATION_RE.search(last_title):
        return False, f"last task is {last_title!r}, not the required validation task"

    return (
        True,
        f"tasks numbered 1..{len(numbers)} with no gaps or duplicates, "
        f"last task {last_title!r} is the validation task",
    )


def _sequence_failure(numbers: list[int]) -> str | None:
    """Return a failure reason unless `numbers` is exactly 1, 2, ... len(numbers)."""
    expected = list(range(1, len(numbers) + 1))
    if numbers == expected:
        return None

    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    if duplicates:
        return f"duplicate task number(s) {duplicates} in {numbers}"
    missing = sorted(set(expected) - set(numbers))
    if missing:
        return f"task numbering has gap(s) — missing {missing} from {numbers}"
    return f"task numbering is out of order or does not start at 1: {numbers}"
