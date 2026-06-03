"""app/agents/tools/runner_tools.py — store-free runner tools (Phase 2 additive).

These are the LangChain tools for the `deepagents`-based `DeepAgentRunner` world,
where there is no `PrototypeArtifactStore`. Unlike the store-coupled versions in
`agents/prototype/tools.py` (which stay live for the current factory/engine path
until the Phase 3 cutover), the tools here carry no state: they return only their
confirmation string.

`report_task_complete` keeps the EXACT name, signature, docstring, and return value
of the live tool so model behavior is unchanged. Phase 3's engine derives
`task_progress` from this tool's call/result events — it reads `task_number` /
`task_title` from the tool-call args — so the tool itself does not need to record
anything.

Wired NOWHERE in Phase 2. #34 (`_build_runner_tools`) will import
`report_task_complete` from here; this module is additive prep only.
"""

from __future__ import annotations

from langchain_core.tools import tool


@tool
def report_task_complete(task_number: int, task_title: str, summary: str = "") -> str:
    """Report that a build task has been completed.

    Args:
        task_number: The task number (1, 2, 3, ...).
        task_title: The task title.
        summary: Brief summary of what was built (optional).
    """
    return f"✓ Task {task_number} complete: {task_title}"


def make_runner_prototype_tools() -> list:
    """Return the store-free runner tool set for prototype agents.

    Currently just [report_task_complete]; the runner writes `prototype.html`
    via the native `deepagents` filesystem tools (no `emit_artifact`).
    """
    return [report_task_complete]


__all__ = ["report_task_complete", "make_runner_prototype_tools"]
