"""Property tests for the canonical manifest form.

# Feature: ai-workflow-builder, Property 30: The canonical manifest form is stable

For any manifest, normalising twice gives the same result as normalising once,
key order does not change the canonical hash, and two manifests that differ
only in the documented composer defaults have the same hash.

**Validates: Requirements 10.9, 37.2**

The "defaults" property builds a minimal manifest and a decorated copy with
plain dict code in this file. The expected sequential ``depends_on`` is
restated here (previous step's backend id) and does not call the production
helpers. The decorated manifests use only top-level steps with no routes or
sub-agents, so the sequential order is simply "the step before". Their leaf
steps also get the apply-and-save defaults ``name == instance_id`` and
``strategy: "single_shot"``; the parent-only ``tools.spawn_subagents: false``
default is covered by the unit tests and the shared parity cases.
"""

from __future__ import annotations

import copy
import random
import re
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder.canonical import (
    canonical_hash,
    canonical_json,
    canonicalize,
)

_HEX_64 = re.compile(r"[0-9a-f]{64}")

# --- generic strategies -----------------------------------------------------

_KEYS = st.text(min_size=1, max_size=6)
_JSON_LEAVES = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-1000, max_value=1000),
    st.text(max_size=8),
)
_JSON_VALUES = st.recursive(
    _JSON_LEAVES,
    lambda children: st.one_of(
        st.lists(children, max_size=3),
        st.dictionaries(_KEYS, children, max_size=3),
    ),
    max_leaves=8,
)

_TOOLS = st.dictionaries(
    st.sampled_from(["exec", "read_files", "write_files", "other"]),
    st.one_of(st.none(), st.booleans(), st.integers(min_value=0, max_value=1)),
    max_size=4,
)
_IDS = st.text(alphabet="abcdef-", min_size=1, max_size=6)
_ID_LISTS = st.lists(_IDS, max_size=3)


def _arbitrary_step(children: st.SearchStrategy[Any]) -> st.SearchStrategy[Any]:
    """A step mapping with the keys the normaliser looks at, plus noise."""
    return st.fixed_dictionaries(
        {},
        optional={
            "agent": st.one_of(_IDS, st.none()),
            "instance_id": st.one_of(_IDS, st.none()),
            "tools": st.one_of(_TOOLS, st.none()),
            "gates": st.one_of(_ID_LISTS, st.none()),
            "depends_on": st.one_of(_ID_LISTS, st.none()),
            "description": st.one_of(st.text(max_size=8), st.none()),
            "extra": _JSON_VALUES,
            "subagents": st.one_of(
                st.fixed_dictionaries(
                    {"steps": st.lists(children, max_size=2)},
                    optional={"note": _JSON_VALUES},
                ),
                st.none(),
            ),
        },
    )


_LEAF_STEP = _arbitrary_step(st.just({"agent": "leaf"}))
_ARBITRARY_STEPS = st.lists(_arbitrary_step(_LEAF_STEP), max_size=4)

_ARBITRARY_MANIFESTS = st.fixed_dictionaries(
    {},
    optional={
        "steps": _ARBITRARY_STEPS,
        "name": st.one_of(st.text(max_size=8), st.none()),
        "meta": _JSON_VALUES,
        "unicode": st.text(alphabet="éß日本🙂 ", max_size=5),
    },
)

# --- minimal / decorated manifest pair --------------------------------------

_NON_DEFAULT_TOOLS = st.fixed_dictionaries(
    {},
    optional={
        "exec": st.just(True),
        "read_files": st.just(False),
        "write_files": st.just(False),
    },
)
_TOOL_DEFAULTS = {"exec": False, "read_files": True, "write_files": True}
_EXPLICIT_DEPENDS_ON = ["other:dep"]  # never equals a sequential list


@st.composite
def _minimal_steps(draw: st.DrawFn) -> list[dict[str, Any]]:
    """Steps that carry no composer default and no ``null`` value."""
    tokens = draw(st.lists(_IDS, min_size=1, max_size=5, unique=True))
    steps: list[dict[str, Any]] = []
    for token in tokens:
        if draw(st.booleans()):
            step: dict[str, Any] = {"agent": "custom", "instance_id": token}
        else:
            step = {"agent": token}
        tools = draw(st.one_of(st.none(), _NON_DEFAULT_TOOLS))
        if tools:
            step["tools"] = tools
        gates = draw(st.one_of(st.none(), st.lists(_IDS, min_size=1, max_size=2)))
        if gates:
            step["gates"] = gates
        if draw(st.booleans()):
            step["depends_on"] = list(_EXPLICIT_DEPENDS_ON)
        steps.append(step)
    return steps


def _backend_id(step: dict[str, Any]) -> str:
    """Backend agent id of a minimal step."""
    if "instance_id" in step:
        return f"custom-agent:{step['instance_id']}"
    return str(step["agent"])


def _decorate(steps: list[dict[str, Any]], *, with_nulls: bool) -> list[dict[str, Any]]:
    """Copy ``steps`` and write back every documented composer default."""
    decorated: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        copy_ = copy.deepcopy(step)
        tools = copy_.setdefault("tools", {})
        for key, default in _TOOL_DEFAULTS.items():
            tools.setdefault(key, default)
        copy_.setdefault("gates", [])
        # Apply-and-save also writes the instance id as the name of a custom
        # step and the default strategy on a leaf step (these steps have no
        # sub-agents, so all of them are leaves).
        if "instance_id" in copy_:
            copy_.setdefault("name", copy_["instance_id"])
        copy_.setdefault("strategy", "single_shot")
        if "depends_on" not in copy_:
            copy_["depends_on"] = [_backend_id(steps[index - 1])] if index else []
        if with_nulls:
            copy_["description"] = None
        decorated.append(copy_)
    return decorated


def _reorder_keys(value: Any, rng: random.Random) -> Any:
    """Copy ``value`` with every mapping's keys in a random order."""
    if isinstance(value, dict):
        keys = list(value)
        rng.shuffle(keys)
        return {key: _reorder_keys(value[key], rng) for key in keys}
    if isinstance(value, list):
        return [_reorder_keys(item, rng) for item in value]
    return value


# --- properties -------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(manifest=_ARBITRARY_MANIFESTS)
def test_canonicalize_is_idempotent_when_applied_twice(
    manifest: dict[str, Any],
) -> None:
    once = canonicalize(manifest)
    twice = canonicalize(once)

    assert twice == once
    assert canonical_hash(twice) == canonical_hash(manifest)


@settings(max_examples=100, deadline=None)
@given(manifest=_ARBITRARY_MANIFESTS)
def test_canonicalize_leaves_input_unchanged_when_called(
    manifest: dict[str, Any],
) -> None:
    before = copy.deepcopy(manifest)

    canonicalize(manifest)

    assert manifest == before


@settings(max_examples=100, deadline=None)
@given(manifest=_ARBITRARY_MANIFESTS, seed=st.integers(min_value=0, max_value=10_000))
def test_canonical_hash_ignores_key_order_when_keys_are_shuffled(
    manifest: dict[str, Any], seed: int
) -> None:
    shuffled = _reorder_keys(manifest, random.Random(seed))

    assert canonical_json(shuffled) == canonical_json(manifest)
    assert canonical_hash(shuffled) == canonical_hash(manifest)


@settings(max_examples=100, deadline=None)
@given(
    steps=_minimal_steps(),
    with_nulls=st.booleans(),
    seed=st.integers(min_value=0, max_value=10_000),
)
def test_canonical_hash_matches_when_manifests_differ_only_by_composer_defaults(
    steps: list[dict[str, Any]], with_nulls: bool, seed: int
) -> None:
    minimal = {"steps": steps}
    decorated = {"steps": _decorate(steps, with_nulls=with_nulls)}
    if with_nulls:
        decorated["version"] = None
    decorated = _reorder_keys(decorated, random.Random(seed))

    assert canonical_json(decorated) == canonical_json(minimal)
    assert canonical_hash(decorated) == canonical_hash(minimal)


@settings(max_examples=100, deadline=None)
@given(manifest=_ARBITRARY_MANIFESTS)
def test_canonical_hash_returns_lowercase_hex_when_given_any_manifest(
    manifest: dict[str, Any],
) -> None:
    assert _HEX_64.fullmatch(canonical_hash(manifest))


@settings(max_examples=100, deadline=None)
@given(steps=_minimal_steps())
def test_canonical_hash_differs_when_step_order_changes(
    steps: list[dict[str, Any]],
) -> None:
    reversed_steps = list(reversed(steps))
    if reversed_steps == steps:
        return  # a single step has no other order

    assert canonical_hash({"steps": reversed_steps}) != canonical_hash({"steps": steps})
