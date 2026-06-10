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

The factory's tool resolution imports `report_task_complete` from here for the
prototype tool sets (08-03 routes it through the ``tool_provider`` registry).
"""

from __future__ import annotations

import json

from langchain_core.tools import tool

# The stable custom-tool KEY for the fan-out request emitter (Phase 11 / FANOUT-01).
# The kernel-side capability provider emits this key; the factory resolves it to the
# concrete tool below. A module constant so the provider + factory never drift.
TOOL_SPAWN_SUBAGENTS = "spawn_subagents"


@tool
def report_task_complete(task_number: int, task_title: str, summary: str = "") -> str:
    """Report that a build task has been completed.

    Args:
        task_number: The task number (1, 2, 3, ...).
        task_title: The task title.
        summary: Brief summary of what was built (optional).
    """
    return f"✓ Task {task_number} complete: {task_title}"


@tool
def spawn_subagents(tasks: list, mode: str = "parallel") -> str:
    """Request that the engine fan out the given tasks to worker sub-agents.

    This tool SPAWNS NOTHING (FANOUT-01): it is a store-free / spawn-free request
    EMITTER. It returns a structured JSON request string ONLY; the engine derives
    the request from this tool's result event and fulfils it via the SINGLE kernel
    fan-out spawn path (the model emits an untrusted REQUEST; the kernel — not the
    tool — decides what spawns, T-11-01-04). The tool body imports no concurrency
    primitives, no spawn coroutine, and no kernel module.

    Args:
        tasks: The list of task inputs to fan out (one worker per task).
        mode: ``"parallel"`` (default) or ``"sequential"``.
    """
    return json.dumps({"fanout_request": list(tasks), "mode": mode})


def make_runner_prototype_tools() -> list:
    """Return the store-free runner tool set for prototype agents.

    Currently just [report_task_complete]; the runner writes `prototype.html`
    via the native `deepagents` filesystem tools (no `emit_artifact`).
    """
    return [report_task_complete]


__all__ = [
    "report_task_complete",
    "make_runner_prototype_tools",
    "spawn_subagents",
    "TOOL_SPAWN_SUBAGENTS",
]
