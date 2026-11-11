"""Unit tests for ``app.agents.workflow_builder.canonical``.

One test per documented composer default (including the apply-and-save
``name``, ``strategy`` and ``spawn_subagents`` defaults), plus ``agent_ids`` order, null
dropping, serialisation and the hash.

Requirements: 10.9 (the canonical form), 37.2 (the canvas hash).
"""

from __future__ import annotations

import copy
import re
from typing import Any

from app.agents.workflow_builder.canonical import (
    canonical_hash,
    canonical_json,
    canonicalize,
)


def _steps(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = canonicalize(manifest)["steps"]
    return result


def test_canonicalize_removes_exec_false_when_tools_exec_is_default() -> None:
    manifest = {"steps": [{"agent": "a", "tools": {"exec": False, "other": 1}}]}

    assert _steps(manifest)[0]["tools"] == {"other": 1}


def test_canonicalize_keeps_exec_true_when_tools_exec_is_enabled() -> None:
    manifest = {"steps": [{"agent": "a", "tools": {"exec": True}}]}

    assert _steps(manifest)[0]["tools"] == {"exec": True}


def test_canonicalize_removes_read_files_true_when_value_is_default() -> None:
    manifest = {"steps": [{"agent": "a", "tools": {"read_files": True, "exec": True}}]}

    assert _steps(manifest)[0]["tools"] == {"exec": True}


def test_canonicalize_keeps_read_files_false_when_value_is_not_default() -> None:
    manifest = {"steps": [{"agent": "a", "tools": {"read_files": False}}]}

    assert _steps(manifest)[0]["tools"] == {"read_files": False}


def test_canonicalize_removes_write_files_true_when_value_is_default() -> None:
    manifest = {"steps": [{"agent": "a", "tools": {"write_files": True, "exec": True}}]}

    assert _steps(manifest)[0]["tools"] == {"exec": True}


def test_canonicalize_keeps_write_files_false_when_value_is_not_default() -> None:
    manifest = {"steps": [{"agent": "a", "tools": {"write_files": False}}]}

    assert _steps(manifest)[0]["tools"] == {"write_files": False}


def test_canonicalize_removes_tools_when_only_defaults_remain() -> None:
    manifest = {
        "steps": [
            {
                "agent": "a",
                "tools": {"exec": False, "read_files": True, "write_files": True},
            }
        ]
    }

    assert "tools" not in _steps(manifest)[0]


def test_canonicalize_treats_integer_flags_as_non_default_when_not_bool() -> None:
    manifest = {"steps": [{"agent": "a", "tools": {"exec": 0, "read_files": 1}}]}

    assert _steps(manifest)[0]["tools"] == {"exec": 0, "read_files": 1}


def test_canonicalize_removes_name_when_it_equals_the_instance_id() -> None:
    manifest = {"steps": [{"agent": "custom-agent", "instance_id": "i1", "name": "i1"}]}

    assert "name" not in _steps(manifest)[0]


def test_canonicalize_keeps_name_when_it_differs_from_the_instance_id() -> None:
    manifest = {
        "steps": [
            {"agent": "custom-agent", "instance_id": "i1", "name": "Writer"},
            {"agent": "custom-agent", "instance_id": "i2", "name": "I2"},
        ]
    }

    assert [step["name"] for step in _steps(manifest)] == ["Writer", "I2"]


def test_canonicalize_keeps_name_when_step_has_no_usable_instance_id() -> None:
    manifest = {
        "steps": [
            {"agent": "b", "name": "b"},
            {"agent": "d", "instance_id": "", "name": ""},
        ]
    }

    assert [step["name"] for step in _steps(manifest)] == ["b", ""]


def test_canonicalize_removes_strategy_when_leaf_step_uses_single_shot() -> None:
    manifest = {"steps": [{"agent": "a", "strategy": "single_shot"}]}

    assert "strategy" not in _steps(manifest)[0]


def test_canonicalize_keeps_strategy_when_leaf_step_uses_another_value() -> None:
    manifest = {"steps": [{"agent": "a", "strategy": "wave_scheduler"}]}

    assert _steps(manifest)[0]["strategy"] == "wave_scheduler"


def test_canonicalize_keeps_strategy_when_parent_step_declares_single_shot() -> None:
    manifest = {
        "steps": [
            {
                "agent": "p",
                "strategy": "single_shot",
                "subagents": {"steps": [{"agent": "k", "strategy": "single_shot"}]},
            }
        ]
    }

    parent = _steps(manifest)[0]

    assert parent["strategy"] == "single_shot"
    assert parent["subagents"]["steps"] == [{"agent": "k"}]


def test_canonicalize_removes_spawn_subagents_false_when_step_is_a_parent() -> None:
    manifest = {
        "steps": [
            {
                "agent": "p",
                "tools": {"spawn_subagents": False, "read_files": False},
                "subagents": {"steps": []},
            },
            {
                "agent": "q",
                "tools": {"spawn_subagents": False},
                "subagents": {"steps": []},
            },
        ]
    }

    steps = _steps(manifest)

    assert steps[0]["tools"] == {"read_files": False}
    assert "tools" not in steps[1]


def test_canonicalize_keeps_spawn_subagents_when_true_or_not_a_boolean() -> None:
    manifest = {
        "steps": [
            {
                "agent": "p",
                "tools": {"spawn_subagents": True},
                "subagents": {"steps": []},
            },
            {
                "agent": "q",
                "tools": {"spawn_subagents": 0},
                "subagents": {"steps": []},
            },
        ]
    }

    steps = _steps(manifest)

    assert steps[0]["tools"] == {"spawn_subagents": True}
    assert steps[1]["tools"] == {"spawn_subagents": 0}


def test_canonicalize_keeps_spawn_subagents_false_when_step_is_a_leaf() -> None:
    manifest = {
        "steps": [
            {"agent": "a", "tools": {"spawn_subagents": False}},
            {"agent": "b", "tools": {"spawn_subagents": False}, "subagents": None},
        ]
    }

    steps = _steps(manifest)

    assert steps[0]["tools"] == {"spawn_subagents": False}
    assert steps[1]["tools"] == {"spawn_subagents": False}


def test_canonical_hash_matches_when_apply_and_save_adds_only_defaults() -> None:
    draft = {
        "steps": [
            {
                "agent": "custom-agent",
                "instance_id": "p",
                "subagents": {
                    "steps": [{"agent": "custom-agent", "instance_id": "p-k"}]
                },
            }
        ]
    }
    saved = {
        "steps": [
            {
                "agent": "custom-agent",
                "instance_id": "p",
                "name": "p",
                "gates": [],
                "tools": {"exec": False, "spawn_subagents": False},
                "subagents": {
                    "steps": [
                        {
                            "agent": "custom-agent",
                            "instance_id": "p-k",
                            "name": "p-k",
                            "strategy": "single_shot",
                        }
                    ]
                },
            }
        ]
    }

    assert canonical_hash(saved) == canonical_hash(draft)


def test_canonicalize_removes_gates_when_list_is_empty() -> None:
    manifest = {"steps": [{"agent": "a", "gates": []}]}

    assert "gates" not in _steps(manifest)[0]


def test_canonicalize_keeps_gates_when_list_is_not_empty() -> None:
    manifest = {"steps": [{"agent": "a", "gates": [{"type": "review"}]}]}

    assert _steps(manifest)[0]["gates"] == [{"type": "review"}]


def test_canonicalize_removes_depends_on_when_it_is_the_sequential_order() -> None:
    manifest = {
        "steps": [
            {"agent": "a", "depends_on": []},
            {"agent": "b", "depends_on": ["a"]},
            {"agent": "c", "depends_on": ["b"]},
        ]
    }

    assert all("depends_on" not in step for step in _steps(manifest))


def test_canonicalize_uses_custom_agent_id_when_step_has_instance_id() -> None:
    manifest = {
        "steps": [
            {"agent": "custom-agent", "instance_id": "i1"},
            {"agent": "b", "depends_on": ["custom-agent:i1"]},
        ]
    }

    assert "depends_on" not in _steps(manifest)[1]


def test_canonicalize_keeps_depends_on_when_it_differs_from_sequential() -> None:
    manifest = {
        "steps": [
            {"agent": "a"},
            {"agent": "b"},
            {"agent": "c", "depends_on": ["a"]},
        ]
    }

    assert _steps(manifest)[2]["depends_on"] == ["a"]


def test_canonicalize_removes_nested_defaults_when_subagents_have_steps() -> None:
    manifest = {
        "steps": [
            {
                "agent": "parent",
                "depends_on": ["child"],
                "subagents": {
                    "steps": [{"agent": "child", "gates": [], "tools": {"exec": False}}]
                },
            }
        ]
    }

    parent = _steps(manifest)[0]

    assert "depends_on" not in parent
    assert parent["subagents"]["steps"] == [{"agent": "child"}]


def test_canonicalize_drops_null_values_when_present_at_any_depth() -> None:
    manifest = {
        "name": None,
        "steps": [{"agent": "a", "model": None, "extra": {"k": None, "v": 1}}],
    }

    assert canonicalize(manifest) == {
        "steps": [{"agent": "a", "extra": {"v": 1}}],
    }


def test_canonicalize_keeps_list_items_when_items_are_null() -> None:
    manifest = {"steps": [], "values": [None, 1]}

    assert canonicalize(manifest)["values"] == [None, 1]


def test_canonicalize_keeps_agent_ids_order_when_ids_are_unsorted() -> None:
    manifest = {"agent_ids": ["zeta", "alpha", "mid"], "steps": []}

    assert canonicalize(manifest)["agent_ids"] == ["zeta", "alpha", "mid"]
    assert '"agent_ids":["zeta","alpha","mid"]' in canonical_json(manifest)


def test_canonicalize_keeps_step_order_when_steps_are_unsorted() -> None:
    manifest = {"steps": [{"agent": "z"}, {"agent": "a"}]}

    assert [s["agent"] for s in _steps(manifest)] == ["z", "a"]


def test_canonicalize_does_not_modify_input_when_defaults_are_present() -> None:
    manifest = {"steps": [{"agent": "a", "gates": [], "tools": {"exec": False}}]}
    before = copy.deepcopy(manifest)

    canonicalize(manifest)

    assert manifest == before


def test_canonical_json_sorts_keys_with_compact_separators_when_called() -> None:
    assert canonical_json({"b": 1, "a": [1, 2]}) == '{"a":[1,2],"b":1}'


def test_canonical_json_keeps_non_ascii_when_text_has_unicode() -> None:
    assert canonical_json({"name": "café ✓"}) == '{"name":"café ✓"}'


def test_canonical_hash_returns_sha256_hex_when_called() -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", canonical_hash({"steps": []}))


def test_canonical_hash_ignores_defaults_nulls_and_key_order_when_equivalent() -> None:
    explicit = {
        "steps": [
            {
                "agent": "a",
                "gates": [],
                "tools": {"exec": False, "read_files": True},
                "model": None,
            }
        ],
        "name": "w",
    }
    bare = {"name": "w", "steps": [{"agent": "a"}]}

    assert canonical_hash(explicit) == canonical_hash(bare)


def test_canonical_hash_differs_when_agent_ids_order_differs() -> None:
    assert canonical_hash({"agent_ids": ["a", "b"]}) != canonical_hash(
        {"agent_ids": ["b", "a"]}
    )
