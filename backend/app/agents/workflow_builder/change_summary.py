"""Change summary between two manifests (design section 3.5.4, Req 7.7, 23.17).

``summarize(baseline, draft)`` reports what a Draft changed compared with the
Canvas state the Turn started from [pending G-08]. Steps are matched by key:

- a ``custom-agent`` step is keyed by its ``instance_id``;
- every other step is keyed by its ``agent``;
- a step nested under ``subagents.steps`` is keyed by its path, the parent key
  and the child key joined with ``/``.

Both manifests go through :func:`canonicalize` first, so composer defaults,
``null`` values and key order never show up as a change.

The module is pure: no I/O and no ``app.api`` imports.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agents.workflow_builder.canonical import canonicalize
from app.agents.workflow_builder.events import ChangeSummary

__all__ = ["summarize"]

_CUSTOM_AGENT = "custom-agent"
_PATH_SEPARATOR = "/"


def summarize(baseline: Mapping[str, Any], draft: Mapping[str, Any]) -> ChangeSummary:
    """Compare ``draft`` with ``baseline`` and describe the difference.

    Args:
        baseline: The manifest the Turn started from (the Canvas state). An
            empty mapping reads as "no steps", so every draft step is added.
        draft: The manifest the Server_Gate accepted.

    Returns:
        A :class:`ChangeSummary`. ``added`` lists draft keys missing from the
        baseline, in draft order. ``removed`` lists baseline keys missing from
        the draft, in baseline order. ``reordered`` is true when the keys both
        sides share appear in a different relative order. ``gates_changed``,
        ``validators_changed`` and ``models_changed`` list the shared keys, in
        draft order, whose ``gates``, ``validators`` or ``model`` differ.
        ``prompts_changed`` counts shared keys whose ``prompt`` differs.
    """
    before = _index_steps(canonicalize(baseline))
    after = _index_steps(canonicalize(draft))

    added = [key for key in after if key not in before]
    removed = [key for key in before if key not in after]
    common = [key for key in after if key in before]

    before_order = [key for key in before if key in after]
    reordered = before_order != common

    return ChangeSummary(
        added=added,
        removed=removed,
        reordered=reordered,
        gates_changed=_changed(common, before, after, "gates"),
        validators_changed=_changed(common, before, after, "validators"),
        models_changed=_changed(common, before, after, "model"),
        prompts_changed=len(_changed(common, before, after, "prompt")),
    )


def _changed(
    keys: list[str],
    before: Mapping[str, Mapping[str, Any]],
    after: Mapping[str, Mapping[str, Any]],
    field: str,
) -> list[str]:
    """Keys whose ``field`` differs between the two canonical steps."""
    return [key for key in keys if before[key].get(field) != after[key].get(field)]


def _index_steps(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Map step key to step for a canonical manifest, in depth-first order.

    A parent comes before its nested steps. A key that repeats gets ``#2``,
    ``#3`` and so on from its second use, so no step is lost.
    """
    index: dict[str, Mapping[str, Any]] = {}
    steps = manifest.get("steps")
    if isinstance(steps, list):
        _collect(steps, "", index)
    return index


def _collect(
    steps: list[Any], parent_key: str, index: dict[str, Mapping[str, Any]]
) -> None:
    """Add ``steps`` and their nested steps to ``index``."""
    for position, step in enumerate(steps):
        if not isinstance(step, Mapping):
            continue
        own = _step_key(step, position)
        key = f"{parent_key}{_PATH_SEPARATOR}{own}" if parent_key else own
        key = _unique(key, index)
        index[key] = step

        subagents = step.get("subagents")
        inner = subagents.get("steps") if isinstance(subagents, Mapping) else None
        if isinstance(inner, list):
            _collect(inner, key, index)


def _step_key(step: Mapping[str, Any], position: int) -> str:
    """Key of one step: ``instance_id`` for ``custom-agent``, else ``agent``."""
    agent = step.get("agent")
    if agent == _CUSTOM_AGENT:
        instance_id = step.get("instance_id")
        if isinstance(instance_id, str) and instance_id:
            return instance_id
    if isinstance(agent, str) and agent:
        return agent
    return f"step-{position + 1}"


def _unique(key: str, index: Mapping[str, object]) -> str:
    """Return ``key``, or ``key#n`` for the first free ``n`` from 2."""
    if key not in index:
        return key
    count = 2
    while f"{key}#{count}" in index:
        count += 1
    return f"{key}#{count}"
