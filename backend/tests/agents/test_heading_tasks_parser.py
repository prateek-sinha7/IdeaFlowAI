"""Wave-0 unit tests for the ``heading_tasks`` task parser (07-01 / PARITY-01).

The ``HeadingTasksParser`` is a verbatim lift of the engine's pure
``_count_plan_tasks`` / ``_extract_task_block`` staticmethods. These cases port
the build-loop task-detection cases (``test_phase4_build_loop.py``) and assert
the parser returns ``Task`` objects whose ``body`` is byte-identical to the
``_extract_task_block`` slice.
"""

from __future__ import annotations

from agents.capabilities.task_parsers.heading_tasks import (
    HeadingTasksParser,
    _count_plan_tasks,
    _extract_task_block,
)
from agents.workflows.plan import Task


def _parser() -> HeadingTasksParser:
    return HeadingTasksParser()


def test_name_is_heading_tasks() -> None:
    assert _parser().name == "heading_tasks"


def test_two_top_level_tasks() -> None:
    text = (
        "## Task 1: Build the shell\n"
        "Write the HTML shell.\n\n"
        "## Task 2: Add the dashboard\n"
        "Add a dashboard page.\n"
    )
    tasks = _parser().parse(text)
    assert len(tasks) == 2
    assert all(isinstance(t, Task) for t in tasks)
    assert tasks[0].id == "1"
    assert tasks[1].id == "2"
    assert tasks[0].title == "Build the shell"
    assert tasks[1].title == "Add the dashboard"


def test_task_body_is_byte_identical_to_extract_task_block() -> None:
    text = (
        "## Task 1: Foo\n"
        "Body of foo.\n\n"
        "## Task 2: Bar\n"
        "Body of bar.\n"
    )
    _count, task_source = _count_plan_tasks(text)
    tasks = _parser().parse(text)
    assert tasks[0].body == _extract_task_block(task_source, 1)
    assert tasks[1].body == _extract_task_block(task_source, 2)


def test_tasks_wrapper_fallback() -> None:
    # No top-level ## Task headings; tasks live inside a <tasks>…</tasks> wrapper.
    text = (
        "Here is the plan.\n\n"
        "<tasks>\n"
        "## Task 1: Inner one\n"
        "do the thing\n\n"
        "## Task 2: Inner two\n"
        "do the other thing\n"
        "</tasks>\n"
    )
    tasks = _parser().parse(text)
    assert len(tasks) == 2
    assert tasks[0].title == "Inner one"
    # The body comes from the unwrapped <tasks> body, not the whole text.
    _count, task_source = _count_plan_tasks(text)
    assert tasks[0].body == _extract_task_block(task_source, 1)


def test_empty_or_no_task_text_returns_empty_list() -> None:
    assert _parser().parse("") == []
    assert _parser().parse("Just some prose with no task headings.") == []
    assert _parser().parse(None) == []  # type: ignore[arg-type]


def test_count_matches_parse_length() -> None:
    text = "## Task 1: a\nx\n## Task 2: b\ny\n## Task 3: c\nz\n"
    count, _src = _count_plan_tasks(text)
    assert count == 3
    assert len(_parser().parse(text)) == 3
