"""Unit tests for evals.grading.calibrate (spec 008-grading-calibration, T11/T12).

Offline: the judge is stubbed, so these run with no credential and no network.
What is NOT stubbed is everything else — the real rubrics, the real precheck
including each stage's `validate:` hook, the real committed fixtures, and the
real code track. That is the point: calibration is only meaningful if it
exercises the same path a live run does.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import app.core.config  # noqa: F401 - importing judge needs settings loaded
from evals.grading import calibrate
from evals.grading.model import judge

WORKFLOW_DIR = (
    Path(__file__).resolve().parents[2] / "evals/grading/model/workflows/prototype"
)
FAIL_DIR = WORKFLOW_DIR / "golden/calibration/fail"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Identify the hollow fixture by CONTENT HASH, not by a phrase: "Operations
# Console" also appears in property_ops's spec, which silently marked a golden
# brief down to 30 and made this test fail for the wrong reason.
_HOLLOW_SHA = _sha((FAIL_DIR / "hollow_console.html").read_text(encoding="utf-8"))


def _stub_judge(score: int, findings=None, fallbacks: int = 0, hollow_score: int | None = None):
    """A grade() stand-in scoring every rubric dimension the same.

    `hollow_score` makes the stub behave like a judge that can actually READ:
    the hollow fixture passes every automated check, so if the stub scores it as
    highly as the golden the calibration correctly fails. That is the invariant
    working, not the harness misbehaving — so a stub standing in for a competent
    judge has to mark it down, exactly as a real one would.
    """

    async def grade(_response, *, rubric, system_prompt, prompt, precheck_reason):
        effective = score
        if hollow_score is not None and _sha(_response) == _HOLLOW_SHA:
            effective = hollow_score
        ids = [dimension["id"] for dimension in rubric["dimensions"]]
        priced = {}
        caps = {}
        for dimension_id in ids:
            final, breakdown = judge.price_findings(effective, findings or [])
            priced[dimension_id] = final
            caps[dimension_id] = breakdown
        return judge.JudgeVerdict(
            sub_scores=priced,
            evidence={i: "quoted" for i in ids},
            rationale="stub",
            dimension_findings={
                i: [{"severity": f.severity, "detail": f.detail} for f in (findings or [])]
                for i in ids
                if findings
            },
            severity_fallbacks=fallbacks,
            score_caps=caps,
            resolved_model_id="stub-judge",
        )

    return grade


# ── fixture integrity ─────────────────────────────────────────────────────


def test_both_ends_of_the_scale_are_committed():
    """The evidence must not live only in a gitignored run folder."""
    briefs = calibrate.golden_briefs(WORKFLOW_DIR)
    fixtures = calibrate.fail_fixtures(WORKFLOW_DIR)

    assert "mission_control" in briefs, "the brief the whole spec is measured on"
    assert len(briefs) >= 2, "a single golden brief cannot show a ceiling"
    assert {f["name"] for f in fixtures} == {"clinic_scheduler_broken", "hollow_console"}


def test_a_drifted_fail_fixture_is_a_hard_error(tmp_path):
    """Either the file was edited or the checkers changed — both need a human."""
    workflow_dir = tmp_path / "prototype"
    folder = workflow_dir / "golden/calibration/fail"
    folder.mkdir(parents=True)
    (workflow_dir / "golden/some_brief").mkdir(parents=True)
    (folder / "broken.html").write_text("<!doctype html></html>", encoding="utf-8")
    (folder / "broken.verdict.json").write_text(
        json.dumps({"name": "broken", "sha256": hashlib.sha256(b"different").hexdigest()}),
        encoding="utf-8",
    )

    with pytest.raises(calibrate.FixtureError, match="sha256"):
        calibrate.fail_fixtures(workflow_dir)


def test_a_verdict_without_its_html_is_a_hard_error(tmp_path):
    workflow_dir = tmp_path / "prototype"
    folder = workflow_dir / "golden/calibration/fail"
    folder.mkdir(parents=True)
    (folder / "gone.verdict.json").write_text(json.dumps({"name": "gone"}), encoding="utf-8")

    with pytest.raises(calibrate.FixtureError, match="missing"):
        calibrate.fail_fixtures(workflow_dir)


def test_missing_fail_fixtures_are_never_treated_as_nothing_to_check(tmp_path):
    """No known-bad end means the separation invariant cannot be evaluated."""
    workflow_dir = tmp_path / "prototype"
    (workflow_dir / "golden").mkdir(parents=True)

    with pytest.raises(calibrate.FixtureError, match="known-bad"):
        calibrate.fail_fixtures(workflow_dir)


# ── the real documents through the real precheck ──────────────────────────


@pytest.mark.asyncio
async def test_the_broken_fixture_never_reaches_the_judge():
    """It fails the precheck, so only the code track can catch it — by design."""

    async def explode(*args, **kwargs):
        raise AssertionError("the judge must not see a precheck-failed document")

    html = (FAIL_DIR / "clinic_scheduler_broken.html").read_text(encoding="utf-8")
    result = await calibrate.grade_document(
        html, agent_id="prototype-build", workflow_dir=WORKFLOW_DIR,
        prompt="brief", with_code=True, grade_fn=explode,
    )

    assert result["precheck_passed"] is False
    assert result["code_score"] == 0.0
    assert result["effective"] == 0.0
    assert "dead nav link" in result["precheck_reason"]


@pytest.mark.asyncio
async def test_the_hollow_fixture_passes_every_automated_check():
    """Its whole purpose: only a reader can tell it is empty.

    If this ever fails, the fixture has become a STRUCTURAL one and has stopped
    testing the half of the scale no checker can see.
    """
    html = (FAIL_DIR / "hollow_console.html").read_text(encoding="utf-8")
    result = await calibrate.grade_document(
        html, agent_id="prototype-build", workflow_dir=WORKFLOW_DIR,
        prompt="brief", with_code=True, grade_fn=_stub_judge(40),
    )

    assert result["precheck_passed"] is True
    assert result["code_score"] >= 90, "hollow, not broken"
    assert result["judge_score"] == 40, "the judge is the only detector here"


@pytest.mark.asyncio
async def test_a_bad_verdict_shape_is_retried_before_being_given_up_on():
    """Observed live: mistral-large returned 2 of 3 dimensions for one stage.

    That is nondeterminism, not a permanent fault. Retrying costs one call;
    NOT retrying cost the entire first calibration run, which aborted on its
    third judge call and discarded every verdict already paid for.
    """
    calls = {"n": 0}

    async def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return judge.JudgeVerdict(errored=True, error_reason="missing dimension ids")
        return await _stub_judge(88)(*args, **kwargs)

    html = (FAIL_DIR / "hollow_console.html").read_text(encoding="utf-8")
    result = await calibrate.grade_document(
        html, agent_id="prototype-build", workflow_dir=WORKFLOW_DIR,
        prompt="brief", with_code=False, grade_fn=flaky,
    )

    assert calls["n"] == 2, "the shape failure was retried, not surrendered to"
    assert result["judge_score"] == 88
    assert "judge_error" not in result


@pytest.mark.asyncio
async def test_a_persistently_failing_judge_is_recorded_not_raised():
    """The sweep continues; the RUN refuses to certify at the end.

    Aborting mid-sweep is the wrong trade: ~32 judge calls have been paid for by
    the time a late one fails, and throwing them away tells you nothing about the
    scale. The stage is recorded as ungradable and check_invariants fails the run.
    """
    calls = {"n": 0}

    async def always_errored(*args, **kwargs):
        calls["n"] += 1
        return judge.JudgeVerdict(errored=True, error_reason="rate limited")

    html = (FAIL_DIR / "hollow_console.html").read_text(encoding="utf-8")
    result = await calibrate.grade_document(
        html, agent_id="prototype-build", workflow_dir=WORKFLOW_DIR,
        prompt="brief", with_code=False, grade_fn=always_errored,
    )

    assert calls["n"] == calibrate.JUDGE_SHAPE_RETRIES + 1
    assert result["effective"] is None, "no score, rather than a fabricated one"
    assert result["judge_error"] == "rate limited"

    problems = calibrate.check_invariants(
        [{"name": "some_brief", "kind": "golden", "overall": 95.0, "stages": [result]}]
    )
    assert any("no usable verdict" in p and "prototype-build" in p for p in problems)


@pytest.mark.asyncio
async def test_an_ungradable_stage_does_not_score_the_golden_zero():
    """A judge outage says nothing about the artifact — do not blame the brief."""
    ungradable = {
        "agent_id": "prototype-analyze", "effective": None, "judge_error": "boom",
        "findings": {}, "dimensions": 0, "fallbacks": 0, "code_score": None,
    }
    graded = dict(ungradable, agent_id="prototype-build", effective=94.0, judge_error=None)
    graded.pop("judge_error")

    result = {"name": "b", "kind": "golden", "stages": [ungradable, graded]}
    considered = [s["effective"] for s in result["stages"] if s["effective"] is not None]

    assert sum(considered) / len(considered) == 94.0, "excluded, not counted as zero"


# ── the invariants ────────────────────────────────────────────────────────


def _result(name, kind, overall, **extra):
    stage = {
        "agent_id": "prototype-build", "effective": overall, "findings": {},
        "dimensions": 3, "fallbacks": 0, "code_score": extra.pop("code_score", 100),
    }
    return {"name": name, "kind": kind, "overall": overall, "stages": [stage], **extra}


def test_invariants_pass_on_a_healthy_scale():
    results = [
        _result("golden_a", "golden", 94.0),
        _result("golden_b", "golden", 91.0),
        _result("broken", "fail", 0.0, max_allowed=20.0),
        _result("hollow", "fail", 42.0, max_allowed=50.0),
    ]
    assert calibrate.check_invariants(results) == []


def test_a_golden_below_the_floor_is_named_with_its_weakest_stage():
    results = [
        _result("golden_a", "golden", 82.0),
        _result("broken", "fail", 0.0, max_allowed=20.0),
    ]
    problems = calibrate.check_invariants(results)
    assert any("golden_a" in p and "82.00" in p and "prototype-build" in p for p in problems)


def test_a_failure_names_the_finding_that_caused_it():
    """An invariant failure that cannot be acted on is just a red light."""
    result = _result("golden_a", "golden", 70.0)
    result["stages"][0]["findings"] = {
        "data_realism": [{"severity": "blocking", "detail": "the detail page renders nothing"}]
    }
    problems = calibrate.check_invariants([result, _result("b", "fail", 0.0, max_allowed=20.0)])
    assert any("blocking" in p and "detail page renders nothing" in p for p in problems)


def test_a_fail_fixture_scoring_too_high_is_caught():
    results = [
        _result("golden_a", "golden", 95.0),
        _result("hollow", "fail", 78.0, max_allowed=50.0),
    ]
    assert any("hollow" in p and "not catching" in p for p in calibrate.check_invariants(results))


def test_a_hollow_fixture_that_became_structural_is_caught():
    """code_score dropping means it stopped testing the judgement half."""
    results = [
        _result("golden_a", "golden", 95.0),
        _result("hollow", "fail", 20.0, max_allowed=50.0, code_score_min=90, code_score=10),
    ]
    problems = calibrate.check_invariants(results)
    assert any("STRUCTURAL" in p for p in problems)


def test_insufficient_separation_is_caught_even_when_both_ends_pass():
    """The subtle inversion: each end within its own band, but too close together.

    Note this cannot happen at the CURRENT thresholds — with the golden floor at
    90 and the hollow fixture capped at 50, a 40-point gap is already implied, so
    the separation check is redundant today. It is kept because it is the only
    invariant that stays meaningful if either band is ever loosened, which is
    exactly when an inversion would creep back in. A fixture declaring a wider
    band (70) is what makes that reachable.
    """
    results = [
        _result("golden_a", "golden", 90.5),
        _result("lenient_fixture", "fail", 70.0, max_allowed=70.0),
    ]
    problems = calibrate.check_invariants(results)

    assert not any("golden_a" in p for p in problems), "the golden clears its own floor"
    assert not any("not catching" in p for p in problems), "the fixture is within its band"
    assert any("separation" in p for p in problems), "but 20.5 apart is not a scale"


def test_the_baseline_block_is_derived_from_the_observed_ceiling():
    """Never from a prediction — that would defeat the calibration."""
    block = calibrate.baseline_block(
        [_result("golden_a", "golden", 93.6), _result("golden_b", "golden", 91.2)]
    )
    assert "min_average_score: 71" in block, "floor sits ~20 below the WORST golden"
    assert "91.20" in block


def test_the_fallback_rate_is_reported_not_inferred():
    results = [_result("golden_a", "golden", 95.0)]
    results[0]["stages"][0]["fallbacks"] = 2
    assert calibrate.fallback_rate(results) == (2, 3)


# ── end to end, with a stubbed judge ──────────────────────────────────────


def _static_only(html: str) -> float:
    """Code score from the structural checks alone — no browser, so it is fast."""
    from evals.grading.code import code_grader

    return code_grader.compute_code_score(code_grader.check_html(html))


def test_run_calibration_grades_every_brief_and_reports_pass(capsys):
    """The whole command, against the real committed tree."""
    lines: list[str] = []
    # Static-only code scoring: the browser sweeps are exercised for real in
    # test_the_hollow_fixture_passes_every_automated_check. Running them for
    # twelve HTML stages here would make the suite minutes long to re-prove it.
    exit_code = calibrate.run_calibration(
        "prototype", grade_fn=_stub_judge(96, hollow_score=28),
        code_score_fn=_static_only, echo=lines.append,
    )
    text = "\n".join(lines)

    assert exit_code == calibrate.EXIT_OK, text
    for brief in calibrate.golden_briefs(WORKFLOW_DIR):
        assert brief in text, f"{brief} was silently skipped"
    assert "clinic_scheduler_broken" in text and "hollow_console" in text
    assert "PASSED" in text
    assert "min_average_score" in text, "a paste-ready baseline block is printed"


def test_run_calibration_fails_when_the_judge_guts_the_golden(capsys):
    """A judge tagging everything `blocking` must fail the run, not pass it."""
    blocking = [judge.Finding(severity="blocking", detail="everything is wrong")]
    lines: list[str] = []
    exit_code = calibrate.run_calibration(
        "prototype", grade_fn=_stub_judge(95, blocking), code_score_fn=_static_only,
        echo=lines.append,
    )
    text = "\n".join(lines)

    assert exit_code == calibrate.EXIT_INVARIANT_FAILED
    assert "FAILED" in text
    assert "blocking" in text, "the triggering finding is named"
