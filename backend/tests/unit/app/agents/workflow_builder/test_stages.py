"""Unit tests for the stage labels in ``app.agents.workflow_builder.stages``.

Requirements: 39.1 (the stage is derived from actions and shown with a
plain-language label).
"""

from __future__ import annotations

import pytest

from app.agents.workflow_builder.stages import (
    STAGE_LABELS,
    Stage,
    label_for,
)

_EXPECTED_LABELS = {
    Stage.STARTING: "Starting",
    Stage.THINKING: "Thinking",
    Stage.READING: "Reading the workflow guide",
    Stage.LOOKING_UP: "Looking up agents, models and examples",
    Stage.WRITING: "Writing the workflow",
    Stage.CHECKING: "Checking the workflow",
    Stage.PLATFORM_CHECK: "Checking with the platform",
    Stage.APPLYING: "Updating the canvas",
    Stage.RESPONDING: "Writing the reply",
}


@pytest.mark.parametrize("stage", list(Stage), ids=lambda s: s.value)
def test_label_for_returns_pinned_label_when_stage_given(stage: Stage) -> None:
    assert label_for(stage) == _EXPECTED_LABELS[stage]


def test_stage_labels_cover_every_stage_when_table_is_built() -> None:
    assert set(STAGE_LABELS) == set(Stage)
    assert set(_EXPECTED_LABELS) == set(Stage)


def test_stage_labels_are_distinct_and_non_empty_when_table_is_built() -> None:
    labels = list(STAGE_LABELS.values())
    assert all(label.strip() for label in labels)
    assert len(set(labels)) == len(labels)


def test_stage_values_are_wire_names_when_enum_is_serialised() -> None:
    assert [stage.value for stage in Stage] == [
        "starting",
        "thinking",
        "reading",
        "looking_up",
        "writing",
        "checking",
        "platform_check",
        "applying",
        "responding",
    ]
