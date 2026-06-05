"""Prototype task generation — planner output → discrete build tasks.

WHAT THIS PROVES
----------------
The build loop turns the Task Planner's output into N isolated build tasks by
counting ``## Task N:`` headers (``ExecutionEngine._count_plan_tasks``) and
slicing each block (``_extract_task_block``).

REGRESSION GUARD
----------------
Earlier the planner *built an HTML ``<artifact>``* instead of emitting a task
plan, so ``_count_plan_tasks`` found 0 headers and the loop ran a single
unfocused build pass — "no incremental build, nothing in preview". Two things fix
that and are pinned here:
  1. the parser counts real ``## Task`` headers and reports 0 for HTML/artifact
     output (so the degenerate case is detectable), and
  2. the ``prototype-plan`` agent is configured plan-only (``tools: []`` + a
     preamble forbidding tool calls / HTML / ``<artifact>``), so it emits a plan.
"""

from __future__ import annotations

from agents.execution_engine.engine import ExecutionEngine
from agents.loader import load_agent_spec

# A well-formed 7-task plan (1 shell + 5 pages + 1 validation), headers at line start.
PLAN_7 = "\n".join(
    f"## Task {i}: Page {i}\n**Goal**: build page {i}\nbody text for task {i}\n"
    for i in range(1, 8)
)


# ---------------------------------------------------------------------------
# _count_plan_tasks
# ---------------------------------------------------------------------------


def test_counts_seven_top_level_task_headers():
    count, source = ExecutionEngine._count_plan_tasks(PLAN_7)
    assert count == 7
    assert source == PLAN_7


def test_counts_tasks_inside_tasks_wrapper():
    wrapped = f"Here is the plan:\n<tasks>\n{PLAN_7}\n</tasks>\n"
    count, _source = ExecutionEngine._count_plan_tasks(wrapped)
    assert count == 7


def test_degenerate_html_plan_counts_zero():
    """THE REGRESSION: the planner built HTML instead of planning tasks."""
    html = "<!doctype html>\n<html><body>" + ("<div>x</div>" * 100) + "</body></html>"
    count, _source = ExecutionEngine._count_plan_tasks(html)
    assert count == 0


def test_degenerate_artifact_plan_counts_zero():
    out = '<artifact identifier="p" type="text/html"><!doctype html><html></html></artifact>'
    count, _source = ExecutionEngine._count_plan_tasks(out)
    assert count == 0


def test_empty_or_none_plan_counts_zero():
    assert ExecutionEngine._count_plan_tasks("") == (0, "")
    assert ExecutionEngine._count_plan_tasks(None) == (0, "")


def test_tasks_wrapper_without_headers_unwraps_and_counts_zero():
    """The <tasks> fallback unwraps the body even when it carries no task headers."""
    out = "<tasks>\njust prose, no task headers\n</tasks>"
    count, source = ExecutionEngine._count_plan_tasks(out)
    assert count == 0
    assert source == "\njust prose, no task headers\n"


# ---------------------------------------------------------------------------
# _extract_task_block
# ---------------------------------------------------------------------------


def test_extract_task_block_returns_single_task():
    block = ExecutionEngine._extract_task_block(PLAN_7, 3)
    assert block.startswith("## Task 3: Page 3")
    assert "body text for task 3" in block
    assert "## Task 4" not in block  # stops at the next header
    assert "## Task 2" not in block  # doesn't bleed into the previous one


def test_extract_first_and_last_task_blocks():
    first = ExecutionEngine._extract_task_block(PLAN_7, 1)
    assert first.startswith("## Task 1: Page 1")
    assert "## Task 2" not in first

    last = ExecutionEngine._extract_task_block(PLAN_7, 7)
    assert last.startswith("## Task 7: Page 7")
    assert "body text for task 7" in last


def test_extract_missing_task_returns_empty():
    assert ExecutionEngine._extract_task_block(PLAN_7, 99) == ""
    assert ExecutionEngine._extract_task_block("", 1) == ""


# ---------------------------------------------------------------------------
# prototype-plan agent is configured plan-only (guards the preamble fix)
# ---------------------------------------------------------------------------


def test_prototype_plan_agent_is_configured_plan_only():
    spec = load_agent_spec("prototype-plan")

    # No tools → a pure-text planner; nothing to build with.
    assert spec.tools == []
    # The documented planner ceiling — NOT the 32768 build ceiling.
    assert spec.max_tokens <= 8000

    body = spec.prompt_body.lower()
    # The plan-only preamble that stops it from BUILDING:
    assert "planning mode" in body
    assert "no need to browse" in body
    # It must instruct the ## Task N: output format the parser reads:
    assert "## task" in body
    # …and explicitly forbid emitting an <artifact>/HTML build:
    assert "artifact" in body
