"""Gate-before-irreversible-step check for builder drafts (intake flag on).

The skill's ground rule: every step that posts, sends or writes outside the run
(a Slack post, an integration or connector write, ``exec``) has a person's gate
directly before it. :func:`check` finds the steps that break it. The Server_Gate
runs it only when ``BUILDER_INTAKE_V2_ENABLED`` is on, so a refused draft goes
back to the builder through the normal ``propose_draft`` rejection.

"Directly before" means one of the skill's two forms:

1. the step itself has ``before-human`` (or ``approval``, the exec form) in
   ``gates``; or
2. a step it names in ``depends_on`` has ``human`` in ``gates``. A root step
   with no ``depends_on`` runs after the root step before it, so that step counts.

The module is pure: no I/O, no ``app.api`` import. Messages name step ids and
tool names only, never prompt text, and only when they look like identifiers.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Final

from app.agents.workflow_builder.ports import GateIssue, GateRule

__all__ = ["RULE", "check", "irreversible_tools"]

RULE: Final[GateRule] = "irreversible_gate"

# A tool whose action part starts with one of these verbs writes outside the run.
_WRITE_VERB_RE: Final = re.compile(
    r"^(?:post|send|create|update|add|delete|remove|write|execute|merge|close|"
    r"comment|transition|assign|publish|upload|edit|set)",
    re.IGNORECASE,
)
_WRITE_SCOPE_RE: Final = re.compile(r"(?:_post|_write|_send)$", re.IGNORECASE)
_SAFE_ID: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_BEFORE_GATES: Final = frozenset({"before-human", "approval"})


def _action(tool: str) -> str:
    """``slack.post_message`` -> ``post_message``; ``jira__create_issue`` -> ``create_issue``."""
    for separator in ("__", "."):
        if separator in tool:
            return tool.rsplit(separator, 1)[-1]
    return tool


def _shown(value: str) -> str:
    return value if _SAFE_ID.match(value) else "<not shown>"


def irreversible_tools(step: Mapping[str, Any]) -> list[str]:
    """The step's grants that post, send or write outside the run (empty when none)."""
    tools = step.get("tools")
    if not isinstance(tools, Mapping):
        return []
    found: list[str] = []
    if tools.get("exec") is True:
        found.append("exec")
    for key in ("mcp", "connectors"):
        for name in tools.get(key) or []:
            if isinstance(name, str) and _WRITE_VERB_RE.match(_action(name)):
                found.append(name)
    for scope in tools.get("integrations") or []:
        if isinstance(scope, str) and _WRITE_SCOPE_RE.search(scope):
            found.append(scope)
    return found


def _gates(step: Mapping[str, Any]) -> set[str]:
    gates = step.get("gates")
    return (
        {g for g in gates if isinstance(g, str)} if isinstance(gates, list) else set()
    )


def _walk(
    steps: Sequence[Any], prefix: str
) -> list[tuple[str, Mapping[str, Any], Mapping[str, Any] | None]]:
    """``(path, step, previous sibling)`` for every step, nested ones included."""
    out: list[tuple[str, Mapping[str, Any], Mapping[str, Any] | None]] = []
    previous: Mapping[str, Any] | None = None
    for index, step in enumerate(steps):
        if not isinstance(step, Mapping):
            continue
        path = f"{prefix}[{index}]"
        out.append((path, step, previous))
        children = (
            (step.get("subagents") or {}).get("steps")
            if isinstance(step.get("subagents"), Mapping)
            else None
        )
        if isinstance(children, list):
            out += _walk(children, f"{path}.subagents.steps")
        previous = step
    return out


def _compiled_id(step: Mapping[str, Any]) -> str:
    return f"{step.get('agent')}:{step.get('instance_id')}"


def check(manifest: Mapping[str, Any]) -> list[GateIssue]:
    """One issue per step that writes outside the run with no gate directly before it."""
    roots = manifest.get("steps")
    if not isinstance(roots, list):
        return []
    walked = _walk(roots, "steps")
    by_id = {_compiled_id(step): step for _, step, _ in walked}
    issues: list[GateIssue] = []
    for path, step, previous in walked:
        writes = irreversible_tools(step)
        if not writes:
            continue
        if _gates(step) & _BEFORE_GATES:
            continue
        depends = [d for d in step.get("depends_on") or [] if isinstance(d, str)]
        upstream = [by_id[d] for d in depends if d in by_id]
        if not depends and previous is not None:
            upstream = [previous]
        if any("human" in _gates(up) for up in upstream):
            continue
        step_id = _shown(str(step.get("instance_id", "")))
        tools = ", ".join(_shown(t) for t in writes)
        issues.append(
            GateIssue(
                RULE,
                path,
                f"step '{step_id}' posts or writes outside the run ({tools}) with no "
                'gate directly before it. Add "gates": ["before-human"] to this '
                'step, or "gates": ["human"], "redoable": true, "reply": '
                '"last_message" to the step it names in depends_on. A person must '
                "approve before every post or write outside the run.",
            )
        )
    return issues
