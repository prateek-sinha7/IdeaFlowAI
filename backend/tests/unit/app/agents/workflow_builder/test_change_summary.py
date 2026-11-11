"""Unit tests for ``app.agents.workflow_builder.change_summary``.

Requirements: 7.7, 23.17 (the summary of what a Draft changed), 49.2.
"""

from __future__ import annotations

from typing import Any

from app.agents.workflow_builder.change_summary import summarize
from app.agents.workflow_builder.events import ChangeSummary

_EMPTY = ChangeSummary(
    added=[],
    removed=[],
    reordered=False,
    gates_changed=[],
    validators_changed=[],
    models_changed=[],
    prompts_changed=0,
)


def _manifest(*steps: dict[str, Any]) -> dict[str, Any]:
    return {"steps": list(steps)}


def _a(**fields: Any) -> dict[str, Any]:
    return {"agent": "agent-a", **fields}


def _b(**fields: Any) -> dict[str, Any]:
    return {"agent": "agent-b", **fields}


def test_summarize_is_empty_when_manifests_are_equal() -> None:
    manifest = _manifest(_a(prompt="p"), _b())

    assert summarize(manifest, manifest) == _EMPTY


def test_summarize_adds_every_step_when_baseline_is_empty() -> None:
    summary = summarize({}, _manifest(_a(), _b()))

    assert summary.added == ["agent-a", "agent-b"]
    assert summary.removed == []
    assert summary.reordered is False


def test_summarize_removes_every_step_when_draft_is_empty() -> None:
    summary = summarize(_manifest(_a(), _b()), {})

    assert summary.removed == ["agent-a", "agent-b"]
    assert summary.added == []


def test_summarize_lists_added_and_removed_when_steps_differ() -> None:
    summary = summarize(_manifest(_a(), _b()), _manifest(_b(), {"agent": "agent-c"}))

    assert summary.added == ["agent-c"]
    assert summary.removed == ["agent-a"]
    assert summary.reordered is False


def test_summarize_marks_reordered_when_shared_steps_swap_places() -> None:
    summary = summarize(_manifest(_a(), _b()), _manifest(_b(), _a()))

    assert summary.reordered is True
    assert summary.added == []
    assert summary.removed == []


def test_summarize_keeps_reordered_false_when_a_step_is_only_inserted() -> None:
    summary = summarize(_manifest(_a(), _b()), _manifest(_a(), {"agent": "c"}, _b()))

    assert summary.reordered is False
    assert summary.added == ["c"]


def test_summarize_keys_custom_agent_by_instance_id_when_agent_is_custom() -> None:
    before = _manifest({"agent": "custom-agent", "instance_id": "x1"})
    after = _manifest({"agent": "custom-agent", "instance_id": "x2"})

    summary = summarize(before, after)

    assert summary.added == ["x2"]
    assert summary.removed == ["x1"]


def test_summarize_keys_nested_step_by_path_when_step_is_under_subagents() -> None:
    def parent(child: dict[str, Any]) -> dict[str, Any]:
        return _manifest(_a(subagents={"agent": "self", "steps": [child]}))

    summary = summarize(parent(_b()), parent({"agent": "agent-c"}))

    assert summary.added == ["agent-a/agent-c"]
    assert summary.removed == ["agent-a/agent-b"]


def test_summarize_keeps_both_steps_when_a_key_repeats() -> None:
    summary = summarize(_manifest(_a()), _manifest(_a(), _a()))

    assert summary.added == ["agent-a#2"]


def test_summarize_keys_by_position_when_step_has_no_agent() -> None:
    summary = summarize({}, _manifest({"prompt": "p"}))

    assert summary.added == ["step-1"]


def test_summarize_reports_field_changes_per_step_when_fields_differ() -> None:
    before = _manifest(
        _a(prompt="old", gates=["g"], validators=["v"], model={"model": "m1"}),
        _b(prompt="same"),
    )
    after = _manifest(
        _a(prompt="new", gates=["h"], validators=["w"], model={"model": "m2"}),
        _b(prompt="same"),
    )

    summary = summarize(before, after)

    assert summary.gates_changed == ["agent-a"]
    assert summary.validators_changed == ["agent-a"]
    assert summary.models_changed == ["agent-a"]
    assert summary.prompts_changed == 1
    assert summary.added == []
    assert summary.removed == []


def test_summarize_counts_prompts_across_steps_when_several_prompts_change() -> None:
    before = _manifest(_a(prompt="1"), _b(prompt="2"))
    after = _manifest(_a(prompt="3"), _b(prompt="4"))

    assert summarize(before, after).prompts_changed == 2


def test_summarize_ignores_unshared_steps_when_comparing_fields() -> None:
    before = _manifest(_a(prompt="1"))
    after = _manifest(_b(prompt="2"))

    summary = summarize(before, after)

    assert summary.prompts_changed == 0
    assert summary.models_changed == []


def test_summarize_ignores_composer_defaults_when_draft_writes_them() -> None:
    before = _manifest(_a())
    after = _manifest(
        _a(gates=[], tools={"exec": False, "read_files": True, "write_files": True})
    )

    assert summarize(before, after) == _EMPTY


def test_summarize_ignores_null_values_when_draft_writes_them() -> None:
    before = _manifest(_a())
    after = _manifest(_a(model=None, prompt=None))

    assert summarize(before, after) == _EMPTY


def test_summarize_ignores_key_order_when_fields_are_equal() -> None:
    before = _manifest({"agent": "agent-a", "prompt": "p", "gates": ["g"]})
    after = _manifest({"gates": ["g"], "prompt": "p", "agent": "agent-a"})

    assert summarize(before, after) == _EMPTY


def test_summarize_counts_gate_order_as_change_when_gates_are_reordered() -> None:
    before = _manifest(_a(gates=["g1", "g2"]))
    after = _manifest(_a(gates=["g2", "g1"]))

    assert summarize(before, after).gates_changed == ["agent-a"]


def test_summarize_does_not_change_inputs_when_called() -> None:
    before = _manifest(_a(gates=[]))
    after = _manifest(_a(gates=[], model=None))
    snapshot = (repr(before), repr(after))

    summarize(before, after)

    assert (repr(before), repr(after)) == snapshot
