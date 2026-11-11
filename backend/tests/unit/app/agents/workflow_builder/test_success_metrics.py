"""Unit tests for the builder success metrics (task 16.8, Req 44.6).

Worked examples and edge cases; the generated-facts check is Property 29 in
``tests/property/app/agents/workflow_builder/test_success_metrics_properties.py``.
"""

from __future__ import annotations

import pytest

from app.agents.workflow_builder.success_metrics import (
    SessionFact,
    SuccessMetrics,
    TurnGateFact,
    compute_success_metrics,
    first_call_gate_pass_rate,
    median_turns_before_first_save,
    session_save_rate,
)


def _sessions(*turns_before_save: int | None) -> list[SessionFact]:
    return [SessionFact(f"s-{i}", n) for i, n in enumerate(turns_before_save)]


def _turns(*passed: bool) -> list[TurnGateFact]:
    return [TurnGateFact(f"t-{i}", ok) for i, ok in enumerate(passed)]


def test_session_save_rate_returns_share_of_saved_sessions() -> None:
    assert session_save_rate(_sessions(2, None, 0, None)) == 0.5


def test_session_save_rate_returns_none_when_there_are_no_sessions() -> None:
    assert session_save_rate([]) is None


def test_session_save_rate_returns_zero_not_none_when_no_session_saved() -> None:
    assert session_save_rate(_sessions(None, None)) == 0.0


def test_first_call_gate_pass_rate_returns_share_of_turns_that_passed_first_call() -> (
    None
):
    assert first_call_gate_pass_rate(_turns(True, False, True, True)) == 0.75


def test_first_call_gate_pass_rate_returns_none_when_no_turn_proposed() -> None:
    assert first_call_gate_pass_rate([]) is None


def test_median_turns_before_first_save_ignores_unsaved_sessions() -> None:
    assert median_turns_before_first_save(_sessions(1, None, 5, None, 3)) == 3.0


def test_median_turns_before_first_save_averages_the_middle_pair_when_even() -> None:
    assert median_turns_before_first_save(_sessions(1, 2, 4, 10)) == 3.0


def test_median_turns_before_first_save_returns_none_when_no_session_saved() -> None:
    assert median_turns_before_first_save(_sessions(None, None)) is None
    assert median_turns_before_first_save([]) is None


def test_median_turns_before_first_save_counts_a_save_on_zero_turns() -> None:
    # A seeded edit session saved before any turn is a save with 0 turns, not "unsaved".
    assert median_turns_before_first_save(_sessions(0)) == 0.0


def test_session_fact_saved_is_true_only_when_a_turn_count_is_present() -> None:
    assert SessionFact("s", 0).saved is True
    assert SessionFact("s").saved is False


def test_session_fact_rejects_negative_turn_count() -> None:
    with pytest.raises(ValueError, match="negative"):
        SessionFact("s", -1)


def test_compute_success_metrics_returns_all_three_metrics_with_counts() -> None:
    metrics = compute_success_metrics(_sessions(1, None, 3), _turns(True, False))

    assert metrics == SuccessMetrics(
        session_save_rate=2 / 3,
        first_call_gate_pass_rate=0.5,
        median_turns_before_first_save=2.0,
        session_count=3,
        saved_session_count=2,
        propose_turn_count=2,
        first_call_passed_count=1,
    )


def test_compute_success_metrics_returns_none_metrics_and_zero_counts_when_empty() -> (
    None
):
    metrics = compute_success_metrics([], [])

    assert metrics.session_save_rate is None
    assert metrics.first_call_gate_pass_rate is None
    assert metrics.median_turns_before_first_save is None
    assert (metrics.session_count, metrics.propose_turn_count) == (0, 0)


def test_compute_success_metrics_accepts_one_shot_iterators() -> None:
    metrics = compute_success_metrics(iter(_sessions(2, None)), iter(_turns(True)))

    assert metrics.session_count == 2
    assert metrics.session_save_rate == 0.5
    assert metrics.median_turns_before_first_save == 2.0
    assert metrics.first_call_gate_pass_rate == 1.0


def test_success_metrics_as_dict_lists_every_field_json_safe() -> None:
    data = compute_success_metrics(_sessions(4), _turns(False)).as_dict()

    assert data == {
        "session_save_rate": 1.0,
        "first_call_gate_pass_rate": 0.0,
        "median_turns_before_first_save": 4.0,
        "session_count": 1,
        "saved_session_count": 1,
        "propose_turn_count": 1,
        "first_call_passed_count": 0,
    }
