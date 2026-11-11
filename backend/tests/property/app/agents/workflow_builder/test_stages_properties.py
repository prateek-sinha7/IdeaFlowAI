"""Property tests for ``derive_stage``.

# Feature: ai-workflow-builder, Property 13: Stage derivation follows the table

For any sequence of tool, thinking, text and gate signals, the derived stage
after each signal equals the stage table's mapping (or stays the same for
signals the table does not name), and a ``stage`` event is emitted if and only
if the stage changed.

``derive_stage`` returns ``None`` when the stage does not change (task 8.1), so
"a stage event is emitted" is "the result is not ``None``".

**Validates: Requirements 39.2, 39.3, 39.4, 39.5, 39.6, 39.7, 39.8, 39.9, 39.10**

The expected stage comes from ``_expected_stage`` below, which restates the
table from design section 3.3.3 with plain comparisons. It does not call the
production helpers.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder.stages import (
    READ_TOOL_NAMES,
    DryRunStarted,
    GateAccepted,
    Signal,
    Stage,
    TextDelta,
    ThinkingDelta,
    ToolStarted,
    TurnAccepted,
    derive_stage,
)

_READ_TOOLS = sorted(READ_TOOL_NAMES)
_UNLISTED_TOOLS = ["ls", "glob", "grep", "write_todos", "unknown_tool"]
_TOOL_NAMES = [
    "read_file",
    "write_file",
    "edit_file",
    "propose_draft",
    "run_skill_script",
    *_READ_TOOLS,
    *_UNLISTED_TOOLS,
]
_PATHS = [
    None,
    "/skills/workflow-builder/SKILL.md",
    "/skills/workflow-builder/references/schema.md",
    "/workflows/draft.workflow.json",
    "/workflows/draft.json",
    "/workflows/notes.md",
    "/notes.txt",
]
_SCRIPTS = [
    None,
    "catalog_lookup.py",
    "validate_manifest.py",
    "selftest.py",
    "refresh_catalog.py",
    "schema_sync.py",
    "export_manifest.py",
    "other_script.py",
]
_SUBCOMMANDS = [None, "agents", "models", "examples"]

_tool_signals = st.builds(
    ToolStarted,
    name=st.sampled_from(_TOOL_NAMES),
    path=st.sampled_from(_PATHS),
    script=st.sampled_from(_SCRIPTS),
    subcommand=st.sampled_from(_SUBCOMMANDS),
    check=st.booleans(),
)
_signals: st.SearchStrategy[Signal] = st.one_of(
    st.just(TurnAccepted()),
    st.builds(ThinkingDelta, tool_running=st.booleans()),
    st.builds(TextDelta, tool_running=st.booleans()),
    _tool_signals,
    st.just(DryRunStarted()),
    st.just(GateAccepted()),
)
_current_stage = st.one_of(st.none(), st.sampled_from(list(Stage)))


def _expected_stage(signal: Signal) -> Stage | None:
    """Return the table's stage for ``signal``, or ``None`` if it names none."""
    if isinstance(signal, TurnAccepted):
        return Stage.STARTING
    if isinstance(signal, ThinkingDelta):
        return None if signal.tool_running else Stage.THINKING
    if isinstance(signal, TextDelta):
        return None if signal.tool_running else Stage.RESPONDING
    if isinstance(signal, DryRunStarted):
        return Stage.PLATFORM_CHECK
    if isinstance(signal, GateAccepted):
        return Stage.APPLYING
    name, path, script = signal.name, signal.path, signal.script
    if name == "read_file":
        return Stage.READING if path and path.startswith("/skills/") else None
    if name in ("write_file", "edit_file"):
        return Stage.WRITING if path and path.endswith(".workflow.json") else None
    if name == "propose_draft":
        return Stage.PLATFORM_CHECK
    if name in _READ_TOOLS:
        return Stage.LOOKING_UP
    if name == "run_skill_script":
        if script == "catalog_lookup.py":
            return Stage.LOOKING_UP
        if script in ("validate_manifest.py", "selftest.py"):
            return Stage.CHECKING
        if script in ("refresh_catalog.py", "schema_sync.py") and signal.check:
            return Stage.CHECKING
    return None


@settings(max_examples=100)
@given(signals=st.lists(_signals, max_size=30))
def test_derive_stage_tracks_table_and_emits_only_on_change_when_signals_arrive_in_sequence(
    signals: list[Signal],
) -> None:
    current: Stage | None = None
    for signal in signals:
        previous = current
        expected = _expected_stage(signal)

        result = derive_stage(signal, previous)
        if result is not None:
            current = result

        # The stage after the signal is the table's stage, or unchanged.
        assert current == (expected if expected is not None else previous)
        # A stage event is emitted if and only if the stage changed.
        assert (result is not None) == (current != previous)


@settings(max_examples=100)
@given(signal=_signals, current=_current_stage)
def test_derive_stage_returns_none_when_signal_maps_to_current_stage_or_no_stage(
    signal: Signal, current: Stage | None
) -> None:
    expected = _expected_stage(signal)
    result = derive_stage(signal, current)

    if expected is None or expected == current:
        assert result is None
    else:
        assert result == expected


@settings(max_examples=100)
@given(signal=_signals, current=_current_stage)
def test_derive_stage_returns_same_result_when_called_twice_with_same_inputs(
    signal: Signal, current: Stage | None
) -> None:
    assert derive_stage(signal, current) == derive_stage(signal, current)
