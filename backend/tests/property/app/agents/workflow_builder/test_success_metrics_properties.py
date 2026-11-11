"""Property tests for the Builder success metrics.

# Feature: ai-workflow-builder, Property 29: Success metrics match their definitions

For any generated set of sessions, turns, gate checks and saves, the three
success metrics equal a direct reference computation of their definitions.

**Validates: Requirements 44.6**

The reference values below restate the definitions from Requirement 44.6 with
plain counting and an explicit sorted-list median. They do not call the
production helpers or ``statistics``.
"""

from __future__ import annotations

import random
from fractions import Fraction

from hypothesis import given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder.success_metrics import (
    SessionFact,
    TurnGateFact,
    compute_success_metrics,
    first_call_gate_pass_rate,
    median_turns_before_first_save,
    session_save_rate,
)

_TURN_COUNTS = st.one_of(st.none(), st.integers(min_value=0, max_value=500))


@st.composite
def _sessions(draw: st.DrawFn) -> list[SessionFact]:
    """Draw sessions with unique ids, some saved and some not."""
    counts = draw(st.lists(_TURN_COUNTS, max_size=40))
    return [
        SessionFact(session_id=f"s{index}", turns_before_first_save=count)
        for index, count in enumerate(counts)
    ]


@st.composite
def _turns(draw: st.DrawFn) -> list[TurnGateFact]:
    """Draw propose_draft turns with unique ids and a first-call verdict each."""
    verdicts = draw(st.lists(st.booleans(), max_size=40))
    return [
        TurnGateFact(turn_id=f"t{index}", first_call_passed=verdict)
        for index, verdict in enumerate(verdicts)
    ]


def _reference_save_rate(sessions: list[SessionFact]) -> float | None:
    if not sessions:
        return None
    saved = len([s for s in sessions if s.turns_before_first_save is not None])
    return float(Fraction(saved, len(sessions)))


def _reference_pass_rate(turns: list[TurnGateFact]) -> float | None:
    if not turns:
        return None
    passed = len([t for t in turns if t.first_call_passed])
    return float(Fraction(passed, len(turns)))


def _reference_median(sessions: list[SessionFact]) -> float | None:
    counts = sorted(
        s.turns_before_first_save
        for s in sessions
        if s.turns_before_first_save is not None
    )
    if not counts:
        return None
    middle = len(counts) // 2
    if len(counts) % 2 == 1:
        return float(counts[middle])
    return float(Fraction(counts[middle - 1] + counts[middle], 2))


@settings(max_examples=100, deadline=None)
@given(sessions=_sessions())
def test_session_save_rate_matches_definition_when_sessions_generated(
    sessions: list[SessionFact],
) -> None:
    assert session_save_rate(sessions) == _reference_save_rate(sessions)


@settings(max_examples=100, deadline=None)
@given(turns=_turns())
def test_first_call_gate_pass_rate_matches_definition_when_turns_generated(
    turns: list[TurnGateFact],
) -> None:
    assert first_call_gate_pass_rate(turns) == _reference_pass_rate(turns)


@settings(max_examples=100, deadline=None)
@given(sessions=_sessions())
def test_median_turns_before_first_save_matches_definition_when_sessions_generated(
    sessions: list[SessionFact],
) -> None:
    assert median_turns_before_first_save(sessions) == _reference_median(sessions)


@settings(max_examples=100, deadline=None)
@given(sessions=_sessions(), turns=_turns())
def test_compute_success_metrics_matches_definitions_when_facts_generated(
    sessions: list[SessionFact], turns: list[TurnGateFact]
) -> None:
    metrics = compute_success_metrics(iter(sessions), iter(turns))

    assert metrics.session_save_rate == _reference_save_rate(sessions)
    assert metrics.first_call_gate_pass_rate == _reference_pass_rate(turns)
    assert metrics.median_turns_before_first_save == _reference_median(sessions)
    assert metrics.session_count == len(sessions)
    assert metrics.saved_session_count == len(
        [s for s in sessions if s.turns_before_first_save is not None]
    )
    assert metrics.propose_turn_count == len(turns)
    assert metrics.first_call_passed_count == len(
        [t for t in turns if t.first_call_passed]
    )
    assert metrics.as_dict()["session_save_rate"] == metrics.session_save_rate


@settings(max_examples=100, deadline=None)
@given(sessions=_sessions(), turns=_turns(), seed=st.integers(0, 2**32 - 1))
def test_compute_success_metrics_is_unchanged_when_facts_are_reordered(
    sessions: list[SessionFact], turns: list[TurnGateFact], seed: int
) -> None:
    shuffled_sessions = list(sessions)
    shuffled_turns = list(turns)
    rng = random.Random(seed)
    rng.shuffle(shuffled_sessions)
    rng.shuffle(shuffled_turns)

    assert compute_success_metrics(shuffled_sessions, shuffled_turns) == (
        compute_success_metrics(sessions, turns)
    )


@settings(max_examples=100, deadline=None)
@given(turns=_turns())
def test_success_metrics_are_none_when_population_is_empty(
    turns: list[TurnGateFact],
) -> None:
    metrics = compute_success_metrics([], turns)

    assert metrics.session_save_rate is None
    assert metrics.median_turns_before_first_save is None
    assert (metrics.first_call_gate_pass_rate is None) == (not turns)
