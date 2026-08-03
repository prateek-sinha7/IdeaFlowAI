"""Unit tests for evals.grading.grades — the run's blended-score arithmetic.

`grades` was extracted verbatim from `markdown_report` so that `site/` can
import the grade math without an import cycle. These tests pin the behaviour
that extraction must not have changed; `test_grading_markdown_report.py` is the
other half of the gate, and passes unmodified.
"""

from __future__ import annotations

import json

import pytest

from evals.grading import artifacts, grades, markdown_report


# ── the letter scale ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (100.0, "A++"),
        (97.0, "A++"),
        (96.9, "A+"),
        (93.0, "A+"),
        (92.9, "A"),
        (90.0, "A"),
        (89.9, "B"),
        (80.0, "B"),
        (79.9, "C"),
        (70.0, "C"),
        (69.9, "D"),
        (60.0, "D"),
        (59.9, "E"),
        (50.0, "E"),
        (49.9, "F"),
        (0.0, "F"),
    ],
)
def test_letter_grade_bands(score, expected):
    assert grades.letter_grade(score) == expected


def test_markdown_report_reexports_the_same_objects():
    """Every existing caller keeps working at its current import path."""
    assert markdown_report.letter_grade is grades.letter_grade
    assert markdown_report.compute_overall is grades.compute_overall
    assert markdown_report.GRADE_BANDS is grades.GRADE_BANDS
    assert markdown_report.FAIL_GRADE is grades.FAIL_GRADE


# ── one cell's contribution ───────────────────────────────────────────────


def test_cell_value_zero_for_a_dispatch_error():
    assert grades.cell_value({"errored": True, "score": 90}, None) == 0.0


def test_cell_value_zero_for_a_broken_chain():
    """precheck_passed is None means the row was never dispatched upstream."""
    assert grades.cell_value({"precheck_passed": None}, None) == 0.0


def test_cell_value_zero_for_a_failed_precheck():
    assert grades.cell_value({"precheck_passed": False, "score": 88}, None) == 0.0


def test_cell_value_none_when_nothing_graded_the_row():
    assert grades.cell_value({"precheck_passed": True, "score": None}, None) is None


def test_cell_value_blends_judge_and_code():
    value = grades.cell_value({"precheck_passed": True, "score": 90}, 80)
    assert value == pytest.approx(0.7 * 90 + 0.3 * 80)


def test_cell_value_uses_the_only_track_that_graded():
    assert grades.cell_value({"precheck_passed": True, "score": 74}, None) == 74.0


# ── the whole run ─────────────────────────────────────────────────────────


def _write_run(tmp_path, *, stages, findings=None):
    """A minimal run folder: a summary plus one score artifact per stage."""
    run_dir = tmp_path / "260730-120000-fixture"
    (run_dir / "artifacts").mkdir(parents=True)
    summary = {"stages": [{"agent_id": agent_id} for agent_id, _ in stages]}
    (run_dir / artifacts.RUN_SUMMARY_NAME).write_text(json.dumps(summary), encoding="utf-8")
    for agent_id, results in stages:
        token = agent_id.replace("-", "_")
        artifacts.artifact_path(run_dir, token, "score").write_text(
            json.dumps({"results": results}), encoding="utf-8"
        )
        if findings and agent_id in findings:
            artifacts.artifact_path(run_dir, token, "code_findings").write_text(
                json.dumps({"findings": findings[agent_id]}), encoding="utf-8"
            )
    return run_dir


def test_compute_overall_averages_every_graded_cell(tmp_path):
    run_dir = _write_run(
        tmp_path,
        stages=[
            ("stage-a", [
                {"row_id": "r1", "precheck_passed": True, "score": 90},
                {"row_id": "r2", "precheck_passed": True, "score": 80},
            ]),
            ("stage-b", [{"row_id": "r1", "precheck_passed": True, "score": 70}]),
        ],
    )
    overall = grades.compute_overall(run_dir)
    assert overall["counted"] == 3
    assert overall["score"] == pytest.approx((90 + 80 + 70) / 3)
    assert overall["grade"] == "B"
    assert overall["failed_cells"] == 0
    assert overall["stages"]["stage-a"]["effective"] == pytest.approx(85.0)


def test_compute_overall_counts_failures_as_zero(tmp_path):
    run_dir = _write_run(
        tmp_path,
        stages=[
            ("stage-a", [
                {"row_id": "r1", "precheck_passed": True, "score": 90},
                {"row_id": "r2", "errored": True},
            ]),
        ],
    )
    overall = grades.compute_overall(run_dir)
    assert overall["counted"] == 2
    assert overall["failed_cells"] == 1
    assert overall["score"] == pytest.approx(45.0)


def test_compute_overall_excludes_negative_tests(tmp_path):
    run_dir = _write_run(
        tmp_path,
        stages=[
            ("stage-a", [
                {"row_id": "r1", "precheck_passed": True, "score": 90},
                {"row_id": "r2", "expect": "fail", "precheck_passed": False},
            ]),
        ],
    )
    overall = grades.compute_overall(run_dir)
    assert overall["counted"] == 1
    assert overall["score"] == pytest.approx(90.0)


def test_compute_overall_is_none_when_nothing_was_gradable(tmp_path):
    run_dir = _write_run(
        tmp_path,
        stages=[("stage-a", [{"row_id": "r1", "precheck_passed": True, "score": None}])],
    )
    assert grades.compute_overall(run_dir) is None


def test_compute_overall_is_none_without_a_summary(tmp_path):
    assert grades.compute_overall(tmp_path / "nope") is None


def test_compute_overall_blends_the_code_track(tmp_path):
    run_dir = _write_run(
        tmp_path,
        stages=[("stage-a", [{"row_id": "r1", "precheck_passed": True, "score": 90}])],
        findings={"stage-a": {"r1": {"code_score": 80}}},
    )
    overall = grades.compute_overall(run_dir)
    assert overall["score"] == pytest.approx(0.7 * 90 + 0.3 * 80)


# ── the small helpers site/ shares ────────────────────────────────────────


def test_agent_token_is_the_artifact_file_name_form():
    assert grades.agent_token({"agent_id": "prototype-build"}) == "prototype_build"
    assert grades.agent_token({}) == ""


def test_stage_score_is_empty_when_the_stage_never_wrote_one(tmp_path):
    assert grades.stage_score(tmp_path, {"agent_id": "missing"}) == {}
