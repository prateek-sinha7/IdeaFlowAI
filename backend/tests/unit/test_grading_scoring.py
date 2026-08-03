"""Unit tests for evals.grading.scoring — the pure aggregation layer
(task T6). Offline: plain dicts in, plain dicts out, no model and no network.
Uses the real prototype_specify rubric and the real 11-row example-run
artifacts, so the constant-95 failure this folder exists to catch is reproduced
against the committed data rather than a hand-tuned fake.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from evals.grading.model.scoring import evaluate_baseline, summarize_stage, weighted_total

WORKFLOW_DIR = (
    Path(__file__).resolve().parents[2] / "evals/grading/model/workflows/prototype"
)
RUBRIC_PATH = WORKFLOW_DIR / "prototype_specify_rubric.yaml"
ARTIFACTS_DIR = WORKFLOW_DIR / "example-run/artifacts"

CALIBRATED_SET_FROM = {
    "dataset_run_id": "260730-000000-ten-industries",
    "config_hash": "sha256:config",
    "rubric_hash": "sha256:rubric",
    "dataset_hash": "sha256:dataset",
    "judge_resolved_model_id": "claude-sonnet-5",
}
CALIBRATED_HASHES = {
    "config_hash": "sha256:config",
    "rubric_hash": "sha256:rubric",
    "dataset_hash": "sha256:dataset",
    "judge_resolved_model_id": "claude-sonnet-5",
}


@pytest.fixture(scope="module")
def rubric() -> dict:
    """The real committed rubric — 40/40/20 dimensions and its baseline block."""
    return yaml.safe_load(RUBRIC_PATH.read_text())


@pytest.fixture(scope="module")
def dimensions(rubric) -> list[dict]:
    """The rubric's three real dimensions."""
    return rubric["dimensions"]


def _run(row_id, *, expect="pass", errored=False, chain=None, tokens_out=100,
         tokens_in=10) -> dict:
    """A minimal run.json entry."""
    return {
        "scenario_id": row_id,
        "expect": expect,
        "errored": errored,
        "upstream_chain": chain or [],
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }


def _grade(row_id, *, precheck=True, score=None, sub_scores=None, weaknesses=None) -> dict:
    """A minimal grade.json entry."""
    return {
        "scenario_id": row_id,
        "judged": score is not None or sub_scores is not None,
        "precheck_passed": precheck,
        "sub_scores": sub_scores,
        "score": score,
        "passed": score is not None and score >= 70,
        "weaknesses": weaknesses or [],
    }


# ── weighted_total ────────────────────────────────────────────────────────


def test_weighted_total_arithmetic(dimensions):
    """40/40/20 over 90/80/60 is 80, not the 76.7 unweighted mean."""
    sub_scores = {"data_realism": 90, "brief_intent_match": 80, "design_system_coherence": 60}
    assert weighted_total(sub_scores, dimensions) == pytest.approx(80.0)


def test_weighted_total_recomputes_after_a_weight_change(dimensions):
    """A weight edit is arithmetic over stored sub-scores — no re-run needed."""
    sub_scores = {"data_realism": 90, "brief_intent_match": 80, "design_system_coherence": 60}
    reweighted = [
        {"id": "data_realism", "weight": 20},
        {"id": "brief_intent_match", "weight": 40},
        {"id": "design_system_coherence", "weight": 40},
    ]
    assert weighted_total(sub_scores, reweighted) == pytest.approx(74.0)


def test_weighted_total_raises_on_a_missing_dimension(dimensions):
    """A sub-score set that does not cover the rubric is an error, not a zero."""
    with pytest.raises(ValueError, match="design_system_coherence"):
        weighted_total({"data_realism": 90, "brief_intent_match": 80}, dimensions)


# ── the real failure: a judge with no signal ──────────────────────────────


def test_constant_95_run_has_no_judge_signal(rubric):
    """11 rows all scoring 95: zero variance, one distinct value, baseline FAIL.

    This is run 260729-083126-ten-industries — the bug this folder exists for.
    """
    row_ids = [f"row_{index}" for index in range(11)]
    runs = [_run(row_id) for row_id in row_ids]
    grades = [_grade(row_id, score=95) for row_id in row_ids]

    summary = summarize_stage(runs, grades, rubric)

    assert summary["counts"]["rows"] == 11
    assert summary["scores"]["stddev"] == 0
    assert summary["scores"]["distinct_score_count"] == 1
    assert summary["scores"]["distinct_scores"] == [95]
    assert any("NO JUDGE SIGNAL" in warning for warning in summary["warnings"])

    verdict = evaluate_baseline(summary, rubric["baseline"], CALIBRATED_HASHES)
    assert verdict["verdict"] == "REFUSED"  # the committed rubric is uncalibrated

    calibrated = {**rubric["baseline"], "set_from": CALIBRATED_SET_FROM}
    verdict = evaluate_baseline(summary, calibrated, CALIBRATED_HASHES)
    assert verdict["verdict"] == "FAIL"
    assert any("distinct_score_count 1 < 3" in failure for failure in verdict["failures"])


@pytest.mark.skipif(not ARTIFACTS_DIR.exists(), reason="the committed example-run fixture is not on disk")
def test_real_example_run_artifacts_summarize(rubric):
    """The committed 11-row artifacts (score 95, sub_scores null) aggregate cleanly."""
    runs = json.loads((ARTIFACTS_DIR / "prototype_specify_run.json").read_text())
    grades = json.loads((ARTIFACTS_DIR / "prototype_specify_grade.json").read_text())

    summary = summarize_stage(runs, grades, rubric)

    assert summary["counts"]["rows"] == 11
    assert summary["counts"]["precheck_passed"] == 4
    assert summary["counts"]["precheck_failed"] == 7
    assert summary["scores"]["average_all"] == 95
    assert summary["scores"]["distinct_score_count"] == 1
    assert all(stats["count"] == 0 for stats in summary["dimensions"].values())
    assert any("SUB-SCORES ABSENT" in warning for warning in summary["warnings"])
    assert any("PRECHECK-FAILED" in warning for warning in summary["warnings"])
    assert summary["recurring_weaknesses"], "the real grades carry weaknesses to cluster"


# ── the three averages ────────────────────────────────────────────────────


def test_three_averages_differ_by_precheck_and_chain(rubric):
    """A precheck failure and a dirty upstream chain each move a different average."""
    runs = [
        _run("clean", chain=[{"agent": "specify", "precheck_passed": True}]),
        _run("dirty", chain=[{"agent": "specify", "precheck_passed": False}]),
        _run("failed", chain=[{"agent": "specify", "precheck_passed": True}]),
    ]
    grades = [
        _grade("clean", score=90),
        _grade("dirty", score=60),
        _grade("failed", precheck=False, score=30),
    ]

    scores = summarize_stage(runs, grades, rubric)["scores"]

    assert scores["average_all"] == pytest.approx(60.0)
    assert scores["average_precheck_passed"] == pytest.approx(75.0)
    assert scores["average_clean_chain"] == pytest.approx(60.0)
    assert scores["median"] == 60
    assert scores["min"] == 30
    assert scores["max"] == 90


# ── negative rows ─────────────────────────────────────────────────────────


def test_negative_row_correctly_rejected_is_excluded_from_pass_rate(rubric):
    """An `expect: fail` row the precheck rejects never touches precheck_pass_rate."""
    runs = [_run("good"), _run("underspecified_brief", expect="fail")]
    grades = [_grade("good", score=90), _grade("underspecified_brief", precheck=False)]

    summary = summarize_stage(runs, grades, rubric)

    assert summary["precheck_pass_rate"] == 1.0
    assert summary["negative_rows_correct"] == {"correct": 1, "total": 1, "rate": 1.0}


def test_negative_row_wrongly_passing_is_counted_incorrect(rubric):
    """A negative row the precheck lets through is wrong, and still not in the rate."""
    runs = [_run("good"), _run("underspecified_brief", expect="fail")]
    grades = [_grade("good", score=90), _grade("underspecified_brief", precheck=True)]

    summary = summarize_stage(runs, grades, rubric)

    assert summary["precheck_pass_rate"] == 1.0
    assert summary["negative_rows_correct"] == {"correct": 0, "total": 1, "rate": 0.0}

    calibrated = {**rubric["baseline"], "set_from": CALIBRATED_SET_FROM}
    verdict = evaluate_baseline(summary, calibrated, CALIBRATED_HASHES)
    assert any("negative_rows_correct 0/1" in failure for failure in verdict["failures"])


# ── per-dimension aggregates ──────────────────────────────────────────────


def test_per_dimension_aggregates_and_recomputed_totals(rubric):
    """Sub-scores drive both the per-dimension stats and each row's total."""
    runs = [_run("a"), _run("b")]
    grades = [
        _grade(
            "a",
            sub_scores={
                "data_realism": 60,
                "brief_intent_match": 90,
                "design_system_coherence": 80,
            },
        ),
        _grade(
            "b",
            sub_scores={
                "data_realism": 40,
                "brief_intent_match": 90,
                "design_system_coherence": 60,
            },
        ),
    ]

    summary = summarize_stage(runs, grades, rubric)

    realism = summary["dimensions"]["data_realism"]
    assert realism == {
        "count": 2,
        "mean": 50.0,
        "median": 50.0,
        "stddev": 10.0,
        "min": 40.0,
        "max": 60.0,
    }
    assert summary["dimensions"]["brief_intent_match"]["stddev"] == 0.0
    assert summary["scores"]["min"] == pytest.approx(64.0)
    assert summary["scores"]["max"] == pytest.approx(76.0)


# ── weakness clustering ───────────────────────────────────────────────────


def test_recurring_weaknesses_cluster_across_rows(rubric):
    """The same criticism, phrased differently, ranks first with its row ids."""
    runs = [_run("a"), _run("b"), _run("c")]
    grades = [
        _grade(
            "a",
            score=70,
            weaknesses=["Invented amounts are round numbers, e.g. $1,000 and $2,000."],
        ),
        _grade(
            "b",
            score=72,
            weaknesses=[
                "Amounts invented here are round numbers again ($5,000), not realistic.",
                "Navigation omits the settings destination entirely.",
            ],
        ),
        _grade(
            "c",
            score=74,
            weaknesses=["The invented amounts are round numbers throughout the tables."],
        ),
    ]

    clusters = summarize_stage(runs, grades, rubric)["recurring_weaknesses"]

    assert clusters[0]["count"] == 3
    assert clusters[0]["row_ids"] == ["a", "b", "c"]
    assert "round" in clusters[0]["keywords"]
    assert clusters[0]["evidence"].startswith("Invented amounts are round numbers")
    assert [cluster["count"] for cluster in clusters[1:]] == [1]


# ── baseline verdicts ─────────────────────────────────────────────────────


def _healthy_summary(rubric) -> dict:
    """A summary that clears every threshold in the real baseline."""
    row_ids = [f"row_{index}" for index in range(10)]
    runs = [_run(row_id) for row_id in row_ids]
    grades = [_grade(row_id, score=80 + index) for index, row_id in enumerate(row_ids)]
    runs.append(_run("underspecified_brief", expect="fail"))
    grades.append(_grade("underspecified_brief", precheck=False))
    return summarize_stage(runs, grades, rubric)


def test_pass_on_a_clean_summary(rubric):
    """Everything above threshold, hashes matching: PASS with no failures."""
    calibrated = {**rubric["baseline"], "set_from": CALIBRATED_SET_FROM}

    verdict = evaluate_baseline(_healthy_summary(rubric), calibrated, CALIBRATED_HASHES)

    assert verdict["verdict"] == "PASS"
    assert verdict["failures"] == []
    assert verdict["max_expected_stddev"] is None


@pytest.mark.parametrize("key", ["config_hash", "rubric_hash", "dataset_hash"])
def test_refused_on_each_hash_mismatch(rubric, key):
    """Any input hash differing from the calibration run makes the run non-comparable."""
    calibrated = {**rubric["baseline"], "set_from": CALIBRATED_SET_FROM}
    hashes = {**CALIBRATED_HASHES, key: "sha256:changed"}

    verdict = evaluate_baseline(_healthy_summary(rubric), calibrated, hashes)

    assert verdict["verdict"] == "REFUSED"
    assert any(key in failure for failure in verdict["failures"])


def test_refused_when_the_judge_resolved_to_another_model(rubric):
    """An unpinned judge is a refusal, not a score."""
    calibrated = {**rubric["baseline"], "set_from": CALIBRATED_SET_FROM}
    hashes = {**CALIBRATED_HASHES, "judge_resolved_model_id": "mistral-small-latest"}

    verdict = evaluate_baseline(_healthy_summary(rubric), calibrated, hashes)

    assert verdict["verdict"] == "REFUSED"
    assert any("mistral-small-latest" in failure for failure in verdict["failures"])


def test_refused_when_the_rubric_drifts_from_the_calibrated_pin(rubric):
    """The committed baseline pins a rubric hash; a different one must REFUSE.

    The committed set_from is calibrated against the golden artifacts, so a
    summary carrying some OTHER rubric hash is not comparable to it.
    """
    verdict = evaluate_baseline(_healthy_summary(rubric), rubric["baseline"], CALIBRATED_HASHES)

    assert verdict["verdict"] == "REFUSED"
    assert any("rubric_hash" in failure for failure in verdict["failures"])


def test_max_expected_stddev_flags_an_implausibly_wide_spread(rubric):
    """The tight-spread sibling check fires only when it is configured."""
    row_ids = ["a", "b", "c", "d"]
    runs = [_run(row_id) for row_id in row_ids]
    grades = [
        _grade(row_id, score=score) for row_id, score in zip(row_ids, [95, 90, 85, 80])
    ]
    summary = summarize_stage(runs, grades, rubric)
    calibrated = {
        **rubric["baseline"],
        "set_from": CALIBRATED_SET_FROM,
        "max_expected_stddev": 2.0,
    }

    verdict = evaluate_baseline(summary, calibrated, CALIBRATED_HASHES)

    assert verdict["verdict"] == "FAIL"
    assert any("max_expected_stddev" in failure for failure in verdict["failures"])


# ── degenerate inputs ─────────────────────────────────────────────────────


def test_empty_input_does_not_raise(rubric):
    """No rows: every aggregate is None or empty, and the baseline still evaluates."""
    summary = summarize_stage([], [], rubric)

    assert summary["counts"]["rows"] == 0
    assert summary["precheck_pass_rate"] is None
    assert summary["scores"]["average_all"] is None
    assert summary["scores"]["distinct_scores"] == []
    assert summary["recurring_weaknesses"] == []

    calibrated = {**rubric["baseline"], "set_from": CALIBRATED_SET_FROM}
    verdict = evaluate_baseline(summary, calibrated, CALIBRATED_HASHES)
    # With zero judged rows the sample-size-gated distinct guard stays unarmed
    # and no threshold has data — the run is empty, not failing. Emptiness is
    # caught upstream (the dead-judge exit code and the JUDGE FAILED warning).
    assert verdict["verdict"] == "PASS"
    assert verdict["failures"] == []


def test_all_errored_rows_do_not_raise(rubric):
    """Every row errored: counted, never scored, and the pass rate is honest."""
    runs = [_run("a", errored=True, tokens_out=0), _run("b", errored=True, tokens_out=0)]
    grades = [
        {"scenario_id": "a", "errored": True, "judged": False},
        {"scenario_id": "b", "errored": True, "judged": False},
    ]

    summary = summarize_stage(runs, grades, rubric)

    assert summary["counts"]["errored"] == 2
    assert summary["counts"]["judged"] == 0
    assert summary["precheck_pass_rate"] == 0.0
    assert summary["scores"]["average_all"] is None
    assert summary["tokens"]["out"] == 0


# ── judge failure is not "no judge" (regression: run 260729-173145) ────────


def _failed_grade(row_id, reason="3 validation errors for JudgeOutput") -> dict:
    """A grade entry for a row whose judge was asked and returned nothing usable."""
    return {
        "scenario_id": row_id,
        "judged": False,
        "precheck_passed": True,
        "sub_scores": None,
        "score": None,
        "passed": None,
        "weaknesses": [],
        "errored": True,
        "error_reason": reason,
    }


def test_judge_errors_are_counted_separately_from_dispatch_errors(rubric):
    summary = summarize_stage(
        [_run("a"), _run("b")],
        [_failed_grade("a"), _failed_grade("b")],
        rubric,
    )

    assert summary["counts"]["errored"] == 0, "the AGENT dispatched fine"
    assert summary["counts"]["judge_errored"] == 2
    assert summary["counts"]["judged"] == 0


def test_judge_failure_raises_a_warning_naming_the_rows(rubric):
    summary = summarize_stage(
        [_run("billing_console"), _run("healthcare_scheduling")],
        [_failed_grade("billing_console"), _failed_grade("healthcare_scheduling")],
        rubric,
    )

    failures = [w for w in summary["warnings"] if "JUDGE FAILED" in w]
    assert len(failures) == 1
    assert "billing_console" in failures[0] and "healthcare_scheduling" in failures[0]
    assert "JudgeOutput" in failures[0], "the first reason is carried, not swallowed"


def test_no_judge_run_at_all_raises_no_judge_failure_warning(rubric):
    """`no_judge: true` leaves the same empty aggregates and must stay quiet."""
    summary = summarize_stage(
        [_run("a"), _run("b")],
        [_grade("a"), _grade("b")],
        rubric,
    )

    assert summary["counts"]["judge_errored"] == 0
    assert not [w for w in summary["warnings"] if "JUDGE FAILED" in w]


def test_stage_tokens_include_the_judge_and_stay_attributable(rubric):
    runs = [_run("a", tokens_out=900), _run("b", tokens_out=1100)]
    grades = [_grade("a", score=80), _grade("b", score=90)]
    for grade in grades:
        grade["judge_tokens_in"] = 4000
        grade["judge_tokens_out"] = 500

    tokens = summarize_stage(runs, grades, rubric)["tokens"]

    assert tokens["agent"] == {"in": 20, "out": 2000, "total": 2020}
    assert tokens["judge"] == {"in": 8000, "out": 1000, "total": 9000}
    assert tokens["total"] == 11020, "the headline total is the WHOLE stage"


def test_judge_error_is_read_under_either_key_spelling():
    """Folders written before the rename used a bare `errored` on grade entries."""
    from evals.grading.model import scoring as scoring_module

    old = {"errored": True, "error_reason": "validation failed"}
    new = {"judge_errored": True, "judge_error_reason": "validation failed"}

    for grade in (old, new):
        assert scoring_module.judge_errored(grade) is True
        assert scoring_module.judge_error_reason(grade) == "validation failed"
    assert scoring_module.judge_errored({}) is False
    assert scoring_module.judge_error_reason({}) is None


def test_a_dispatch_error_is_never_mistaken_for_a_judge_error(rubric):
    """`errored` on a RUN entry means the agent failed — a different failure."""
    from evals.grading.model import scoring as scoring_module

    assert scoring_module.judge_errored({"judged": True, "score": 80}) is False

    summary = summarize_stage([_run("a", errored=True)], [_grade("a")], rubric)
    assert summary["counts"]["errored"] == 1
    assert summary["counts"]["judge_errored"] == 0


# ── judge resolution (regression: run 260729-175607) ──────────────────────
#
# Two sub-score values weighted 40/40/20 produce several distinct TOTALS, so
# `distinct_score_count` read healthy while the judge was choosing between
# exactly "90" and "95".


def _sub(row_id, data_realism, brief_intent_match, design_system_coherence) -> dict:
    """A grade entry carrying explicit per-dimension sub-scores."""
    return _grade(
        row_id,
        sub_scores={
            "data_realism": data_realism,
            "brief_intent_match": brief_intent_match,
            "design_system_coherence": design_system_coherence,
        },
    )


def test_two_sub_score_values_are_flagged_despite_distinct_totals(rubric):
    """The exact 260729-175607 shape: totals 93 and 92, vocabulary {90, 95}."""
    summary = summarize_stage(
        [_run("billing_console"), _run("healthcare_scheduling")],
        [_sub("billing_console", 95, 90, 95), _sub("healthcare_scheduling", 90, 95, 90)],
        rubric,
    )

    assert summary["scores"]["distinct_score_count"] == 2, "totals look varied"
    resolution = [w for w in summary["warnings"] if "LOW JUDGE RESOLUTION" in w]
    assert len(resolution) == 1
    assert "[90, 95]" in resolution[0]


def test_a_judge_using_a_real_range_raises_no_resolution_warning(rubric):
    summary = summarize_stage(
        [_run("a"), _run("b"), _run("c")],
        [_sub("a", 88, 72, 91), _sub("b", 64, 80, 55), _sub("c", 45, 91, 70)],
        rubric,
    )

    assert not [w for w in summary["warnings"] if "LOW JUDGE RESOLUTION" in w]
    assert not [w for w in summary["warnings"] if "SCORE CEILING" in w]


def test_every_sub_score_in_the_top_band_is_flagged_as_a_ceiling(rubric):
    """The top band is 95 (reference quality) since the anchors re-band."""
    summary = summarize_stage(
        [_run("a"), _run("b")],
        [_sub("a", 95, 96, 100), _sub("b", 97, 98, 99)],
        rubric,
    )

    ceiling = [w for w in summary["warnings"] if "SCORE CEILING" in w]
    assert len(ceiling) == 1
    assert ">= 95" in ceiling[0], "the top anchor comes from the rubric, not a constant"


def test_one_scored_row_raises_no_resolution_warning(rubric):
    """A single row has no vocabulary to speak of — the warning would be noise."""
    summary = summarize_stage([_run("a")], [_sub("a", 95, 95, 95)], rubric)

    assert not [w for w in summary["warnings"] if "LOW JUDGE RESOLUTION" in w]


# ── a verdict nothing consumes ────────────────────────────────────────────


def test_a_stage_verdict_is_counted_even_though_nothing_reads_it(rubric):
    """prototype-analyze decides readiness; no agent consumes it.

    Its only consumer in production is a human gate, which does not exist here —
    so a NEEDS REVISION used to be produced, graded and silently discarded while
    the run marched on to build.
    """
    runs = [_run("a"), _run("b")]
    runs[0]["signal"] = {"name": "readiness", "value": "NEEDS REVISION", "alert": True}
    runs[1]["signal"] = {"name": "readiness", "value": "READY TO BUILD", "alert": False}

    signals = summarize_stage(runs, [_grade("a"), _grade("b")], rubric)["signals"]

    assert signals["name"] == "readiness"
    assert signals["counts"] == {"NEEDS REVISION": 1, "READY TO BUILD": 1}
    assert signals["alert_rows"] == ["a"], "only the rows that raised an alert"


def test_a_stage_with_no_declared_signal_reports_none(rubric):
    assert summarize_stage([_run("a")], [_grade("a")], rubric)["signals"] == {}


def test_a_dispatched_row_with_no_output_tokens_warns(rubric):
    """The real case the warning is for: input was billed, output went uncounted."""
    summary = summarize_stage(
        [_run("billing_console", tokens_in=5830, tokens_out=0)],
        [_grade("billing_console", score=90)],
        rubric,
    )

    assert [w for w in summary["warnings"] if "TOKENS UNDER-REPORTED" in w]


def test_a_row_that_was_never_dispatched_does_not_warn(rubric):
    """A seeded/replayed row has no token counts at all — nothing is under-reported.

    `golden-mission-control` is built from committed responses rather than a live
    dispatch, so every row carries `tokens_in == tokens_out == 0` while holding a
    136 KB response. `rejudge` never dispatches, so those zeros can never be
    filled in — the old predicate fired on all five stages of every rejudge,
    claiming rows were "dispatched" when they never were.
    """
    summary = summarize_stage(
        [_run("mission_control", tokens_in=0, tokens_out=0)],
        [_grade("mission_control", score=92)],
        rubric,
    )

    assert not [w for w in summary["warnings"] if "TOKENS UNDER-REPORTED" in w]
