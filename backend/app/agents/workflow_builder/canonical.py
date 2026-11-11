"""Canonical manifest form (design section 3.10.8) [pending G-34].

Saving an unedited AI draft must give a payload equivalent to the one
``export_manifest.py --save-payload`` produces, even though the composer canvas
writes defaults that the exporter leaves out. Both sides are normalised to one
canonical form before they are compared or hashed. The TypeScript port in
``frontend/src/lib/canonicalManifest.ts`` must agree with this module; the
shared cases file pins that.

Normalisation, applied to every step (top level and ``subagents.steps``):

1. Drop keys whose value is ``null``, at any depth. List items are kept.
2. Remove keys that equal the composer default: ``tools.exec: false``,
   ``tools.read_files: true``, ``tools.write_files: true``, ``gates: []`` and
   ``depends_on`` when it equals the sequential order the canvas derives.
   A ``tools`` mapping that is empty after this removal is removed too.
   Apply-and-save also writes three keys that carry no information, so they
   are defaults as well: ``name`` on a custom step when it equals the step's
   ``instance_id``, ``strategy: "single_shot"`` on a leaf step (one with no
   ``subagents`` key) and ``tools.spawn_subagents: false`` on a parent step
   (one with a ``subagents`` key). A ``name`` that differs from the instance
   id, any other strategy and ``spawn_subagents: true`` are kept.
3. Serialise with sorted keys, compact separators and UTF-8, with no ASCII
   escaping.

List order is never changed. ``agent_ids`` and ``steps`` order is the step
order, so it counts.

The module is pure: no I/O, standard library only.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["canonical_hash", "canonical_json", "canonicalize"]

_CUSTOM_AGENT_PREFIX = "custom-agent:"

_TOOL_DEFAULTS: Mapping[str, bool] = {
    "exec": False,
    "read_files": True,
    "write_files": True,
}

# Defaults that only apply to a parent step (one that has ``subagents``).
_PARENT_TOOL_DEFAULTS: Mapping[str, bool] = {"spawn_subagents": False}

_LEAF_DEFAULT_STRATEGY = "single_shot"


def canonicalize(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return the canonical form of ``manifest`` as a new JSON-compatible dict.

    The input is not modified. Steps under ``steps`` and, recursively,
    ``subagents.steps`` have the composer defaults removed, then ``null``
    values are dropped from the whole structure.

    Args:
        manifest: A workflow manifest, normally ``{"steps": [...], ...}``.

    Returns:
        The normalised manifest. Mapping key order is not significant here;
        :func:`canonical_json` sorts keys on output.
    """
    # Nulls go first so a ``tools`` mapping holding only defaults and nulls
    # is judged empty and removed.
    cleaned = _drop_nulls(manifest)
    return _strip_manifest_defaults(cleaned)


def canonical_json(manifest: Mapping[str, Any]) -> str:
    """Serialise the canonical form of ``manifest`` to a string.

    Keys are sorted, separators are compact (``,`` and ``:``) and non-ASCII
    characters are written as they are (``ensure_ascii=False``).

    Raises:
        ValueError: If the manifest holds ``NaN`` or an infinity.
        TypeError: If the manifest holds a value JSON cannot represent.
    """
    return json.dumps(
        canonicalize(manifest),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_hash(manifest: Mapping[str, Any]) -> str:
    """Return the SHA-256 of the canonical JSON as 64 lowercase hex digits.

    Two manifests that differ only by the documented composer defaults, by
    ``null`` values or by key order have the same hash.

    Raises:
        ValueError: If the manifest holds ``NaN`` or an infinity.
        TypeError: If the manifest holds a value JSON cannot represent.
    """
    return hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()


def _strip_manifest_defaults(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Copy ``manifest`` with composer defaults removed from every step."""
    result: dict[str, Any] = dict(manifest)
    steps = result.get("steps")
    if isinstance(steps, list):
        result["steps"] = _strip_steps(steps, top_level=True)
    return result


def _strip_steps(steps: Sequence[Any], *, top_level: bool) -> list[Any]:
    """Copy a step list, removing defaults from each step mapping."""
    route_targets = _route_target_ids(steps) if top_level else frozenset[str]()
    stripped: list[Any] = []
    for index, step in enumerate(steps):
        if not isinstance(step, Mapping):
            stripped.append(step)
            continue
        previous = steps[index - 1] if top_level and index > 0 else None
        expected = _sequential_depends_on(step, previous, route_targets)
        stripped.append(_strip_step(step, expected))
    return stripped


def _strip_step(
    step: Mapping[str, Any], expected_depends_on: list[str]
) -> dict[str, Any]:
    """Copy one step with the documented defaults removed."""
    result: dict[str, Any] = dict(step)
    is_parent = "subagents" in result

    instance_id = result.get("instance_id")
    if (
        isinstance(instance_id, str)
        and instance_id
        and result.get("name") == instance_id
    ):
        del result["name"]

    if not is_parent and result.get("strategy") == _LEAF_DEFAULT_STRATEGY:
        del result["strategy"]

    tools = result.get("tools")
    if isinstance(tools, Mapping):
        defaults = {**_TOOL_DEFAULTS, **(_PARENT_TOOL_DEFAULTS if is_parent else {})}
        kept = {
            key: value
            for key, value in tools.items()
            if not (key in defaults and _is_same_bool(value, defaults[key]))
        }
        if kept:
            result["tools"] = kept
        else:
            del result["tools"]

    gates = result.get("gates")
    if isinstance(gates, list) and not gates:
        del result["gates"]

    depends_on = result.get("depends_on")
    if isinstance(depends_on, list) and list(depends_on) == expected_depends_on:
        del result["depends_on"]

    subagents = result.get("subagents")
    if isinstance(subagents, Mapping):
        inner = subagents.get("steps")
        if isinstance(inner, list):
            result["subagents"] = {
                **subagents,
                "steps": _strip_steps(inner, top_level=False),
            }
    return result


def _is_same_bool(value: object, default: bool) -> bool:
    """True when ``value`` is the boolean ``default`` (``0`` and ``1`` are not)."""
    return isinstance(value, bool) and value is default


def _step_agent_id(step: object) -> str:
    """Backend agent id of a step, as the composer derives it.

    ``custom-agent:<instance_id>`` when the step has an ``instance_id``,
    otherwise its ``agent`` value, otherwise an empty string.
    """
    if not isinstance(step, Mapping):
        return ""
    instance_id = step.get("instance_id")
    if instance_id and isinstance(instance_id, str):
        return f"{_CUSTOM_AGENT_PREFIX}{instance_id}"
    agent = step.get("agent")
    return agent if isinstance(agent, str) else ""


def _route_target_ids(steps: Sequence[Any]) -> frozenset[str]:
    """Targets of every ``route.outcomes`` entry whose trigger is ``step``."""
    targets: set[str] = set()
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        route = step.get("route")
        outcomes = route.get("outcomes") if isinstance(route, Mapping) else None
        if not isinstance(outcomes, Mapping):
            continue
        for outcome in outcomes.values():
            if not isinstance(outcome, Mapping):
                continue
            target = outcome.get("target")
            if outcome.get("trigger") == "step" and target and isinstance(target, str):
                targets.add(target)
    return frozenset(targets)


def _sequential_depends_on(
    step: Mapping[str, Any],
    previous: object,
    route_targets: frozenset[str],
) -> list[str]:
    """The ``depends_on`` list the composer canvas derives for ``step``.

    A step lists the ids of its own sub-agents first. A top-level step that is
    not the first and is not the target of a ``step`` route also lists the id
    of the step before it. ``previous`` is ``None`` for the first top-level
    step and for every nested step.
    """
    expected: list[str] = []

    subagents = step.get("subagents")
    if isinstance(subagents, Mapping):
        inner = subagents.get("steps")
        if isinstance(inner, list):
            expected.extend(filter(None, (_step_agent_id(child) for child in inner)))

    if previous is not None:
        own_id = _step_agent_id(step)
        instance_id = step.get("instance_id")
        is_route_target = own_id in route_targets or (
            isinstance(instance_id, str)
            and bool(instance_id)
            and instance_id in route_targets
        )
        previous_id = _step_agent_id(previous)
        if not is_route_target and previous_id:
            expected.append(previous_id)
    return expected


def _drop_nulls(value: Any) -> Any:
    """Copy ``value`` without ``None`` mapping values, at any depth."""
    if isinstance(value, Mapping):
        return {
            key: _drop_nulls(item) for key, item in value.items() if item is not None
        }
    if isinstance(value, list):
        return [_drop_nulls(item) for item in value]
    return value
