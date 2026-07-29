"""Compose the prompt prototype-build actually receives, from the plan's tasks.

The build agent never sees the raw `<tasks>` document. Production injects ONE
task at a time under a `=== CURRENT TASK ===` block, so forwarding the plan
verbatim would grade a prompt shape the agent has never been given.

Referenced from workflow.yaml as `./prototype_build_input.py:build_prompt`.

KNOWN LIMITATION — ONE DISPATCH, ALL TASKS
------------------------------------------
Production (`engine._run_build_task_loop`) runs N isolated sub-agents, one per
task, each with a single `## Task N:` body in the block. This harness dispatches
exactly one model call per dataset row: `model_grader.run_stage` builds one
`StageInput` per row (`stage_input.build_stage_inputs`) and hands it to
`dispatch.run_row`, which reads `prototype.html` back once at the end. There is
no fan-out from one row to N calls anywhere in that path.

So this adapter reproduces the block SHAPE (delimiters, `Task X of N` header,
`## Task N:` bodies) but NOT the dispatch count: every task goes into a single
block, executed in one call. Read a score from this stage as "can the agent
build the whole prototype in one pass from this task list", NOT as "does the
per-task loop work". The incremental-edit behaviour the loop exists to exercise
(`write_file` on task 1, `edit_file` after, never rebuilding) is NOT covered
here and must not be inferred from a passing score. Fixing this needs a
per-row fan-out in the runner, not a change to this file.
"""

from __future__ import annotations

import re

# A task header in the plan's `<tasks>` document: "## Task 3: Build the Roster page".
# Anchored at line start so a task title merely MENTIONING "## Task" in prose
# cannot open a new block.
TASK_HEADER = re.compile(r"^##\s+Task\s+(\d+)\s*:", re.MULTILINE)

# The plan's wrapper. Its closing tag would otherwise ride along on the last
# task's body, handing the build agent a stray `</tasks>` inside its own block.
TASKS_CLOSE = re.compile(r"</tasks>\s*$", re.IGNORECASE)

BLOCK_TEMPLATE = (
    "=== CURRENT TASK ===\n"
    "Tasks 1-{total} of {total}\n"
    "Execute every task below, in order, in this single call.\n\n"
    "{bodies}\n"
    "=== END CURRENT TASK ==="
)


def build_prompt(row: dict, upstreams: dict[str, str]) -> str:
    """Wrap the upstream plan's tasks in the `=== CURRENT TASK ===` block.

    Signature is fixed by `stage_input._compose_prompt`, which calls
    `adapter(row, upstreams)` where `upstreams` maps each `from:` agent id to
    its text for THIS row. `row` is the dataset row; it is unused because the
    build agent's whole input is the plan plus the seeded `spec.md`.

    Raises ValueError when the plan has no parseable task headers. Failing loud
    at prompt-composition time is deliberate: an unparseable plan is an upstream
    or harness defect, and dispatching an empty/taskless prompt would score it
    as a BUILD failure — attributing someone else's break to this agent, which
    is exactly the mis-grading this harness exists to prevent.
    """
    plan = upstreams.get("prototype-plan", "")
    tasks = extract_tasks(plan)
    if not tasks:
        raise ValueError(
            f"row {row.get('id', '?')!r}: upstream 'prototype-plan' has no parseable "
            f"'## Task N:' headers ({len(plan)} chars) — cannot compose the "
            "=== CURRENT TASK === block prototype-build is dispatched with"
        )

    return BLOCK_TEMPLATE.format(total=len(tasks), bodies="\n\n".join(tasks))


def extract_tasks(plan: str) -> list[str]:
    """Split the plan into one text block per `## Task N:` header.

    Each block runs from its header to the next header (or end of text), so a
    task's bullets, tables and acceptance notes travel with it. Returns [] when
    the document has no headers at all, which the caller treats as fatal.
    """
    body = TASKS_CLOSE.sub("", plan.strip())
    starts = [match.start() for match in TASK_HEADER.finditer(body)]
    if not starts:
        return []

    bounds = starts + [len(body)]
    return [body[bounds[i] : bounds[i + 1]].strip() for i in range(len(starts))]
