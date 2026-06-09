"""Prototype task generation — the ``prototype-plan`` agent is configured plan-only.

WHAT THIS PROVES
----------------
The build loop turns the Task Planner's output into N isolated build tasks by counting
``## Task N:`` headers and slicing each block. Post-07-05 that parsing logic lives in the
``heading_tasks`` task-parser capability (``agents/capabilities/task_parsers/heading_tasks.py``,
the verbatim lift of the deleted ``ExecutionEngine._count_plan_tasks`` /
``_extract_task_block`` staticmethods) — its dedicated coverage is
``tests/agents/test_heading_tasks_parser.py``. The engine-staticmethod parsing tests that
used to live here were RETIRED in 07-05 along with the deleted engine copies (L11).

REGRESSION GUARD (retained here)
--------------------------------
Earlier the planner *built an HTML ``<artifact>``* instead of emitting a task plan, so the
parser found 0 headers and the loop ran a single unfocused build pass — "no incremental
build, nothing in preview". The fix that is still pinned here: the ``prototype-plan`` agent
is configured plan-only (``tools: []`` + a preamble forbidding tool calls / HTML /
``<artifact>``), so it emits a plan the parser can split.
"""

from __future__ import annotations

from agents.loader import load_agent_spec


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
