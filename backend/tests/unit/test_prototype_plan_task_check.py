"""Unit tests for prototype-plan's ONE custom precheck hook (task-header
sequencing — the one check the generic model_graded/precheck.py config
cannot express: numbers must be sequential starting at 1, Task 1 must be
the HTML shell, the last task must be validation).
"""

from __future__ import annotations

from evals.model_graded.agents.prototype_plan.task_structure_check import check

GOOD_TASKS = """<tasks>
## Task 1: HTML Shell
Build the shell, sidebar nav, :root tokens, hash router, empty sections.

## Task 2: Dashboard Page
Full stat row and chart per spec.

## Task 3: Validation
Verify every section has content, tokens match DS, nav links correct.
</tasks>"""

OUT_OF_ORDER_TASKS = GOOD_TASKS.replace("## Task 1: HTML Shell", "## Task 2: HTML Shell").replace(
    "## Task 2: Dashboard Page", "## Task 1: Dashboard Page"
)

NO_SHELL_FIRST = """<tasks>
## Task 1: Dashboard Page
Full stat row and chart per spec.

## Task 2: HTML Shell
Build the shell, sidebar nav, :root tokens, hash router, empty sections.

## Task 3: Validation
Verify every section has content.
</tasks>"""

NO_VALIDATION_LAST = """<tasks>
## Task 1: HTML Shell
Build the shell, sidebar nav, :root tokens, hash router, empty sections.

## Task 2: Dashboard Page
Full stat row and chart per spec.
</tasks>"""

NO_HEADERS = "<tasks>\nJust some prose, no task headers at all.\n</tasks>"


def test_passes_on_sequential_shell_first_validation_last():
    passed, reason = check(GOOD_TASKS)
    assert passed is True
    assert "3 sequential tasks" in reason


def test_fails_on_out_of_order_numbering():
    passed, reason = check(OUT_OF_ORDER_TASKS)
    assert passed is False
    assert "not sequential" in reason


def test_fails_when_task_1_is_not_the_shell():
    passed, reason = check(NO_SHELL_FIRST)
    assert passed is False
    assert "shell" in reason


def test_fails_when_last_task_is_not_validation():
    passed, reason = check(NO_VALIDATION_LAST)
    assert passed is False
    assert "validation" in reason


def test_fails_when_no_task_headers_found():
    passed, reason = check(NO_HEADERS)
    assert passed is False
    assert "no '## Task N:' headers" in reason


def test_wrapper_missing_is_not_this_checks_job():
    """Division of labor: the custom hook only checks task-header
    sequencing — a missing <tasks> wrapper is the generic precheck's
    concern, not this one's."""
    unwrapped = GOOD_TASKS.replace("<tasks>\n", "").replace("\n</tasks>", "")
    passed, _ = check(unwrapped)
    assert passed is True
