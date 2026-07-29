"""Unit tests for evals.grading.compare — the "did my edit help?" layer
(task T10). Offline: plain dicts in, plain dicts out, no model and no network.

Run payloads are built by calling the real `scoring.summarize_stage`, so these
tests fail if the shape `compare.py` consumes ever drifts from the shape
`scoring.py` produces.
"""

from __future__ import annotations

import math

import pytest

from evals.grading.compare import compare_runs, group_by_prompt, noise_band
from evals.grading.scoring import summarize_stage

RUBRIC = {
    "dimensions": [
        {"id": "data_realism", "weight": 40},
        {"id": "brief_intent_match", "weight": 40},
        {"id": "design_system_coherence", "weight": 20},
    ]
}

# A judge threshold, only used to set each row's `passed` flag.
THRESHOLD = 70

# Half the spread between the two calibration repeats. With two samples the
# pooled stddev is spread/sqrt(2), so a 2-sigma threshold is spread*sqrt(2) —
# this value makes the band come out at exactly +/- 5 points.
SPREAD = 5.0 / math.sqrt(2)


def _row(row_id, *, realism=80, intent=80, coherence=80, precheck=True):
    """One row as the (run entry, grade entry) pair `summarize_stage` joins."""
    sub_scores = {
        "data_realism": realism,
        "brief_intent_match": intent,
        "design_system_coherence": coherence,
    }
    total = (40 * realism + 40 * intent + 20 * coherence) / 100.0
    run = {
        "scenario_id": row_id,
        "expect": "pass",
        "errored": False,
        "upstream_chain": [],
        "tokens_in": 10,
        "tokens_out": 100,
    }
    grade = {
        "scenario_id": row_id,
        "judged": True,
        "precheck_passed": precheck,
        "sub_scores": sub_scores,
        "score": total,
        "passed": total >= THRESHOLD,
        "weaknesses": [],
    }
    return run, grade


def _make_run(run_id, rows, *, timestamp="2026-07-29T10:00:00", config="cfg", prompt="p1"):
    """A whole run payload: identity plus its real `summarize_stage` summary."""
    runs = [entry[0] for entry in rows]
    grades = [entry[1] for entry in rows]
    return {
        "dataset_run_id": run_id,
        "timestamp": timestamp,
        "config_hash": config,
        "system_prompt_hash": prompt,
        "summary": summarize_stage(runs, grades, RUBRIC),
    }


def _flat_run(run_id, *, score=80, rows=3, timestamp="2026-07-29T10:00:00", prompt="p1"):
    """A run whose every row scores the same total, so its average is exact."""
    return _make_run(
        run_id,
        [
            _row(f"row_{index}", realism=score, intent=score, coherence=score)
            for index in range(rows)
        ],
        timestamp=timestamp,
        prompt=prompt,
    )


# ── per-row deltas ────────────────────────────────────────────────────────


def test_per_row_deltas_show_the_improved_and_the_regressed_row():
    """One row up, one row down, one flat — each reported with its own delta."""
    before = _make_run(
        "run-a",
        [_row("row_1", realism=80), _row("row_2", realism=80), _row("row_3", realism=80)],
    )
    after = _make_run(
        "run-b",
        [_row("row_1", realism=90), _row("row_2", realism=50), _row("row_3", realism=80)],
        prompt="p2",
    )

    rows = compare_runs([before, after])["comparisons"][0]["rows"]
    deltas = {row["row_id"]: row["delta"] for row in rows}

    assert deltas["row_1"] == pytest.approx(4.0)
    assert deltas["row_2"] == pytest.approx(-12.0)
    assert deltas["row_3"] == pytest.approx(0.0)


def test_precheck_flips_are_reported_in_both_directions():
    """A row that started passing precheck and one that started failing."""
    before = _make_run(
        "run-a",
        [_row("row_1", precheck=True), _row("row_2", precheck=False), _row("row_3")],
    )
    after = _make_run(
        "run-b",
        [_row("row_1", precheck=False), _row("row_2", precheck=True), _row("row_3")],
        prompt="p2",
    )

    comparison = compare_runs([before, after])["comparisons"][0]
    flips = {row["row_id"]: row["precheck_flip"] for row in comparison["precheck_flips"]}

    assert flips == {"row_1": "pass->fail", "row_2": "fail->pass"}
    unflipped = [row for row in comparison["rows"] if row["row_id"] == "row_3"]
    assert unflipped[0]["precheck_flip"] is None


def test_threshold_crossings_are_reported_in_both_directions():
    """`passed` moving in either direction is a crossing, not just a delta."""
    high = {"realism": 90, "intent": 90, "coherence": 90}
    low = {"realism": 50, "intent": 50, "coherence": 50}
    before = _make_run("run-a", [_row("row_1", **high), _row("row_2", **low)])
    after = _make_run("run-b", [_row("row_1", **low), _row("row_2", **high)], prompt="p2")

    crossings = compare_runs([before, after])["comparisons"][0]["threshold_crossings"]

    assert {row["row_id"]: row["threshold_cross"] for row in crossings} == {
        "row_1": "pass->fail",
        "row_2": "fail->pass",
    }


def test_rows_present_in_only_one_run_are_reported_not_dropped():
    """A dataset that gained and lost a row must say so, never silently skip."""
    before = _make_run("run-a", [_row("row_1"), _row("row_2")])
    after = _make_run("run-b", [_row("row_1"), _row("row_3")], prompt="p2")

    comparison = compare_runs([before, after])["comparisons"][0]

    assert comparison["only_in_baseline"] == ["row_2"]
    assert comparison["only_in_run"] == ["row_3"]
    assert [row["row_id"] for row in comparison["rows"]] == ["row_1"]


# ── per-dimension deltas: the headline capability ─────────────────────────


def _calibrated_pair(spread=SPREAD):
    """Two repeats of one identical spec, differing only by judge noise."""
    return [
        _flat_run("run-cal-1", score=80, timestamp="2026-07-29T09:00:00"),
        _flat_run("run-cal-2", score=80 + spread, timestamp="2026-07-29T09:30:00"),
    ]


def test_a_dimension_regression_is_isolated_while_the_total_barely_moves():
    """`data_realism` -20 while the weighted total moves -2 and stays in noise.

    This is the whole point of the module: the average says "nothing happened",
    the per-dimension breakdown names the paragraph of the AGENT.md to rewrite.
    """
    repeats = [
        _flat_run("run-cal-1", score=80, timestamp="2026-07-29T09:00:00"),
        _flat_run("run-cal-2", score=82, timestamp="2026-07-29T09:30:00"),
    ]
    edited = _make_run(
        "run-edit",
        [
            _row(f"row_{index}", realism=60, intent=90, coherence=90)
            for index in range(3)
        ],
        timestamp="2026-07-29T10:00:00",
        prompt="p2",
    )

    report = compare_runs([*repeats, edited])
    comparison = report["comparisons"][1]

    assert comparison["run_id"] == "run-edit"
    assert comparison["aggregates"]["average_all"]["delta"] == pytest.approx(-2.0)
    assert comparison["aggregates"]["average_all"]["verdict"] == "within-noise"
    assert comparison["dimensions"]["data_realism"]["delta"] == pytest.approx(-20.0)
    assert comparison["dimensions"]["data_realism"]["verdict"] == "regressed"
    assert comparison["dimensions"]["brief_intent_match"]["verdict"] == "improved"


# ── the noise guard ───────────────────────────────────────────────────────


def test_noise_band_is_derived_from_repeats_of_one_identical_spec():
    """Two repeats of one config+prompt give a +/-5 band at two sigma."""
    band = noise_band(_calibrated_pair())

    assert band["verdict"] == "ok"
    assert band["band"]["threshold"] == pytest.approx(5.0)
    assert band["band"]["samples"] == 2
    assert band["repeat_groups"][0]["runs"] == ["run-cal-1", "run-cal-2"]


def test_a_small_delta_inside_the_band_is_not_called_an_improvement():
    """+2 against a +/-5 band is noise, and must never read as progress."""
    edited = _flat_run("run-edit", score=82, timestamp="2026-07-29T10:00:00", prompt="p2")

    report = compare_runs([*_calibrated_pair(), edited])
    aggregate = report["comparisons"][1]["aggregates"]["average_all"]

    assert aggregate["delta"] == pytest.approx(2.0)
    assert aggregate["verdict"] == "within-noise"
    assert report["comparisons"][1]["verdict"] == "within-noise"


def test_a_large_delta_outside_the_same_band_is_called_an_improvement():
    """+12 against the identical +/-5 band clears it, and is real."""
    edited = _flat_run("run-edit", score=92, timestamp="2026-07-29T10:00:00", prompt="p2")

    report = compare_runs([*_calibrated_pair(), edited])
    aggregate = report["comparisons"][1]["aggregates"]["average_all"]

    assert aggregate["delta"] == pytest.approx(12.0)
    assert aggregate["verdict"] == "improved"


def test_a_large_negative_delta_outside_the_band_is_called_a_regression():
    """The guard is two-sided — it does not only suppress good news."""
    edited = _flat_run("run-edit", score=60, timestamp="2026-07-29T10:00:00", prompt="p2")

    report = compare_runs([*_calibrated_pair(), edited])

    assert report["comparisons"][1]["aggregates"]["average_all"]["verdict"] == "regressed"


def test_without_repeats_the_variance_is_unknown_and_no_delta_is_an_improvement():
    """No two runs share a spec, so the band is null and says so explicitly."""
    before = _flat_run("run-a", score=70)
    after = _flat_run("run-b", score=82, timestamp="2026-07-29T11:00:00", prompt="p2")

    report = compare_runs([before, after])
    aggregate = report["comparisons"][0]["aggregates"]["average_all"]

    assert report["noise"]["band"] is None
    assert report["noise"]["verdict"] == "unknown-variance"
    assert "variance" in report["noise"]["reason"]
    assert aggregate["delta"] == pytest.approx(12.0)
    assert aggregate["verdict"] == "unknown-variance"


def test_a_flat_metric_still_gets_a_floor_so_a_tiny_move_is_not_signal():
    """Two identical repeats do not prove a zero-variance judge."""
    repeats = [
        _flat_run("run-cal-1", score=80, timestamp="2026-07-29T09:00:00"),
        _flat_run("run-cal-2", score=80, timestamp="2026-07-29T09:30:00"),
    ]
    edited = _flat_run("run-edit", score=80.5, timestamp="2026-07-29T10:00:00", prompt="p2")

    report = compare_runs([*repeats, edited])

    assert report["noise"]["band"]["stddev"] == pytest.approx(0.0)
    assert report["noise"]["band"]["threshold"] == pytest.approx(1.0)
    assert report["comparisons"][1]["aggregates"]["average_all"]["verdict"] == "within-noise"


# ── degenerate inputs ─────────────────────────────────────────────────────


def test_identical_runs_produce_zero_deltas_and_a_stable_verdict():
    """Nothing changed, so nothing may be reported as having changed."""
    before = _flat_run("run-a", score=80)
    after = _flat_run("run-b", score=80, timestamp="2026-07-29T11:00:00")

    comparison = compare_runs([before, after])["comparisons"][0]

    assert all(row["delta"] == 0 for row in comparison["rows"])
    assert all(row["precheck_flip"] is None for row in comparison["rows"])
    assert all(entry["delta"] == 0 for entry in comparison["dimensions"].values())
    assert comparison["aggregates"]["average_all"]["verdict"] == "stable"
    assert comparison["verdict"] == "stable"


def test_comparing_a_run_against_itself_does_not_crash():
    """The same payload twice is a degenerate but legal input."""
    run = _flat_run("run-a", score=80)

    comparison = compare_runs([run, run])["comparisons"][0]

    assert comparison["run_id"] == comparison["against"] == "run-a"
    assert comparison["verdict"] == "stable"
    assert comparison["only_in_baseline"] == comparison["only_in_run"] == []


def test_fewer_than_two_runs_is_an_error():
    """One run is not a comparison — say so rather than return empty deltas."""
    with pytest.raises(ValueError, match="at least two runs"):
        compare_runs([_flat_run("run-a")])


def test_three_or_more_runs_are_each_compared_against_the_baseline():
    """Every later run gets its own comparison against runs[0]."""
    runs = [
        _flat_run("run-a", score=70, timestamp="2026-07-29T09:00:00"),
        _flat_run("run-b", score=75, timestamp="2026-07-29T10:00:00", prompt="p2"),
        _flat_run("run-c", score=85, timestamp="2026-07-29T11:00:00", prompt="p3"),
        _flat_run("run-d", score=65, timestamp="2026-07-29T12:00:00", prompt="p4"),
    ]

    report = compare_runs(runs)

    assert report["baseline"]["run_id"] == "run-a"
    assert [comparison["run_id"] for comparison in report["comparisons"]] == [
        "run-b",
        "run-c",
        "run-d",
    ]
    assert all(comparison["against"] == "run-a" for comparison in report["comparisons"])
    assert [
        comparison["aggregates"]["average_all"]["delta"] for comparison in report["comparisons"]
    ] == pytest.approx([5.0, 15.0, -5.0])


# ── grouping by prompt version ────────────────────────────────────────────


def test_group_by_prompt_orders_versions_chronologically_by_first_seen():
    """Three runs, two prompt versions, given out of order — trend, not pile."""
    runs = [
        _flat_run("run-c", score=90, timestamp="2026-07-29T12:00:00", prompt="p1"),
        _flat_run("run-b", score=60, timestamp="2026-07-29T11:00:00", prompt="p2"),
        _flat_run("run-a", score=80, timestamp="2026-07-29T10:00:00", prompt="p1"),
    ]

    grouped = group_by_prompt(runs)

    assert grouped["order"] == ["p1", "p2"]
    assert list(grouped["groups"]) == ["p1", "p2"]
    assert grouped["groups"]["p1"]["first_seen"] == "2026-07-29T10:00:00"
    assert grouped["groups"]["p1"]["runs"] == ["run-a", "run-c"]
    assert grouped["groups"]["p1"]["total_runs"] == 2


def test_group_by_prompt_flags_each_version_against_the_baseline_version():
    """The earliest prompt version is the target; later ones met it or did not."""
    runs = [
        _flat_run("run-a", score=80, timestamp="2026-07-29T10:00:00", prompt="p1"),
        _flat_run("run-b", score=60, timestamp="2026-07-29T11:00:00", prompt="p2"),
        _flat_run("run-c", score=95, timestamp="2026-07-29T12:00:00", prompt="p3"),
    ]

    grouped = group_by_prompt(runs)

    assert grouped["baseline"] == "p1"
    assert grouped["target"] == pytest.approx(80.0)
    assert grouped["groups"]["p1"]["target_met"] is True
    assert grouped["groups"]["p2"]["target_met"] is False
    assert grouped["groups"]["p3"]["target_met"] is True
    assert grouped["groups"]["p3"]["average_score"] == pytest.approx(95.0)


def test_group_by_prompt_averages_every_run_of_one_version():
    """A version's aggregate spans all its runs, not just the first."""
    runs = [
        _flat_run("run-a", score=80, timestamp="2026-07-29T10:00:00", prompt="p1"),
        _flat_run("run-b", score=90, timestamp="2026-07-29T11:00:00", prompt="p1"),
    ]

    grouped = group_by_prompt(runs)

    assert grouped["groups"]["p1"]["average_score"] == pytest.approx(85.0)
    assert grouped["groups"]["p1"]["precheck_pass_rate"] == pytest.approx(1.0)
