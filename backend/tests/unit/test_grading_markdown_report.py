"""Unit tests for evals.grading.markdown_report — the run-folder reports/ set.

Offline: builds a run folder on disk from plain dicts and asserts on the
rendered markdown — the top-level reports/report.md and the per-phase
reports/<agent_token>_report.md. Also renders the REAL committed example-run,
so a shape change in the artifacts breaks a test rather than a report someone
is reading.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.grading import markdown_report

EXAMPLE_RUN = (
    Path(__file__).resolve().parents[2]
    / "evals/grading/model/workflows/prototype/example-run"
)


def _write(path: Path, payload) -> None:
    """Write one JSON artifact into a fabricated run folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def run_dir(tmp_path) -> Path:
    """A minimal but complete run folder: one judged row, one failed judge."""
    run_dir = tmp_path / "260729-173145-ten-industries"
    _write(
        run_dir / "run_summary.json",
        {
            "dataset_run_id": "260729-173145-ten-industries",
            "dataset_id": "ten-industries",
            "workflow_id": "prototype",
            "run_id": "partial",
            "row_count": 2,
            "status": "completed",
            "created_at": "2026-07-29T15:31:45Z",
            "finished_at": "2026-07-29T15:33:39Z",
            "config": {"overrides": {}},
            "stages": [
                {
                    "agent_id": "prototype-specify",
                    "status": "completed",
                    "precheck_pass_rate": 1.0,
                    "average_all": 82.0,
                    "baseline_verdict": "PASS",
                    "distinct_score_count": 2,
                },
                {"agent_id": "prototype-plan", "status": "not_run"},
            ],
            "not_run": ["prototype-plan"],
        },
    )
    artifacts_dir = run_dir / "artifacts"
    _write(
        artifacts_dir / "prototype_specify_score.json",
        {
            "dataset_run_id": "260729-173145-ten-industries",
            "counts": {"rows": 2, "dispatched": 2, "judged": 1, "judge_errored": 1},
            "precheck_pass_rate": 1.0,
            "model_under_test": {"provider": "mistral", "model": "mistral-small-latest"},
            "judge": {"provider": "mistral", "model": "mistral-large-latest"},
            "hashes": {
                "rubric_hash": "sha256:f33c10a2c3c69ae5",
                "dataset_hash": "sha256:aca55f976aec3e76",
                "judge_resolved_model_id": "mistral-large-latest",
            },
            "scores": {"average_all": 82.0},
            "dimensions": {"data_realism": {"count": 1, "mean": 85.0}},
            "tokens": {
                "in": 12857,
                "out": 10430,
                "total": 23287,
                "agent": {"in": 8857, "out": 9930, "total": 18787},
                "judge": {"in": 4000, "out": 500, "total": 4500},
            },
            "recurring_weaknesses": [
                {"evidence": "invoice amounts are round numbers", "row_ids": ["billing_console"]}
            ],
            "warnings": ["JUDGE FAILED: 1 row(s) (healthcare_scheduling) ..."],
            "baseline": {"verdict": "PASS", "failures": []},
            "results": [
                {
                    "row_id": "billing_console",
                    "expect": "pass",
                    "precheck_passed": True,
                    "score": 82.0,
                    "passed": True,
                    "errored": False,
                },
                {
                    "row_id": "healthcare_scheduling",
                    "expect": "pass",
                    "precheck_passed": True,
                    "score": None,
                    "passed": None,
                    "errored": False,
                },
            ],
        },
    )
    _write(
        artifacts_dir / "prototype_specify_grade.json",
        [
            {
                "row_id": "billing_console",
                "judged": True,
                "score": 82.0,
                "sub_scores": {"data_realism": 85},
                "evidence": {"data_realism": "ACME Corp $12,480.00"},
                "rationale": "Solid, domain-specific detail throughout.",
                "strengths": ["realistic invoice table"],
                "weaknesses": ["invoice amounts are round numbers"],
                "precheck_reason": "generic: wrapper ok",
                "errored": False,
            },
            {
                "row_id": "healthcare_scheduling",
                "judged": False,
                "score": None,
                "errored": True,
                "error_reason": "3 validation errors for JudgeOutput\nrationale\n  missing",
            },
        ],
    )
    _write(
        artifacts_dir / "prototype_specify_run.json",
        [
            {"row_id": "billing_console", "prompt": "Build an internal admin console."},
            {"row_id": "healthcare_scheduling", "prompt": "Build a clinic scheduler."},
        ],
    )
    return run_dir


def _top(run_dir) -> str:
    """Render and read the top-level report."""
    return markdown_report.write_report(run_dir).read_text(encoding="utf-8")


def _stage(run_dir, token: str = "prototype_specify") -> str:
    """Render and read one phase's report."""
    markdown_report.write_report(run_dir)
    return (run_dir / "reports" / f"{token}_report.md").read_text(encoding="utf-8")


def test_write_report_lands_in_the_reports_folder(run_dir):
    path = markdown_report.write_report(run_dir)

    assert path == run_dir / "reports" / "report.md"
    assert path.read_text(encoding="utf-8").startswith("# Grading run — ")
    assert (run_dir / "reports" / "prototype_specify_report.md").exists()


def test_top_report_scores_without_spread_statistics(run_dir):
    """The phase table carries THE score; stddev/min/max live in the phase report."""
    text = _top(run_dir)

    line = next(l for l in text.splitlines() if "prototype-specify" in l and l.startswith("|"))
    assert " 82 " in line
    assert "stddev" not in text
    assert "prototype_specify_report.md" in line, "the phase links to its own report"


def test_top_report_ends_with_the_rejudge_command(run_dir):
    text = _top(run_dir)

    assert "## Rejudge this run" in text
    assert f"grade.sh rejudge {run_dir.name}" in text


def test_top_report_tabulates_weaknesses_with_rows_affected(run_dir):
    text = _top(run_dir)

    assert "## Weaknesses" in text
    line = next(l for l in text.splitlines() if "invoice amounts are round numbers" in l)
    assert "`prototype-specify`" in line
    assert "`billing_console`" in line
    assert "| 1 |" in line


def test_report_leads_with_identity_and_the_models_that_produced_it(run_dir):
    top = _top(run_dir)
    stage = _stage(run_dir)

    assert "ten-industries" in top
    assert "**Not run:** `prototype-plan`" in top
    # The models are per-stage facts and live in the phase report's identity table.
    assert "`mistral/mistral-small-latest`" in stage
    assert "`mistral/mistral-large-latest`" in stage


def test_phase_report_carries_scores_dimensions_and_tokens(run_dir):
    text = _stage(run_dir)

    assert "| `data_realism` | 1 | 85.00 |" in text
    assert "| agent | 8857 | 9930 | 18787 |" in text
    assert "| judge | 4000 | 500 | 4500 |" in text
    assert "**23287**" in text, "the headline total covers agent AND judge"


def test_report_shows_a_failed_judge_on_the_row_that_failed(run_dir):
    text = _stage(run_dir)

    assert "**judge failed**" in text
    assert "3 validation errors for JudgeOutput" in text
    assert "⚠️ Warnings" in text
    assert "\n" not in _row_line(text, "healthcare_scheduling"), "one row, one line"


def test_report_carries_the_judges_narrative_per_row(run_dir):
    text = _stage(run_dir)

    assert "Solid, domain-specific detail throughout." in text
    assert "- realistic invoice table" in text
    assert "`data_realism` — ACME Corp $12,480.00" in text
    assert "Recurring weaknesses" in text


def test_report_names_the_command_that_reproduces_the_run(run_dir):
    text = _top(run_dir)

    assert "grade_config.resolved.yaml" in text


def test_cli_overrides_are_flagged_as_breaking_reproducibility(run_dir):
    summary = json.loads((run_dir / "run_summary.json").read_text())
    summary["config"]["overrides"] = {"limit": 2}
    (run_dir / "run_summary.json").write_text(json.dumps(summary), encoding="utf-8")

    text = _top(run_dir)

    assert "`limit=2`" in text
    assert "will **not** reproduce it" in text


def test_a_pre_split_run_attributes_flat_tokens_to_the_agent(run_dir):
    """Legacy score.json has no breakdown; a zero agent row would contradict the total."""
    path = run_dir / "artifacts" / "prototype_specify_score.json"
    score = json.loads(path.read_text())
    score["tokens"] = {"in": 8857, "out": 9930, "total": 18787}
    path.write_text(json.dumps(score), encoding="utf-8")

    text = _stage(run_dir)

    assert "| agent | 8857 | 9930 | 18787 |" in text
    assert "| judge | 0 | 0 | 0 |" in text


def test_a_pre_split_run_still_counts_judge_errors_from_the_grades(run_dir):
    path = run_dir / "artifacts" / "prototype_specify_score.json"
    score = json.loads(path.read_text())
    del score["counts"]["judge_errored"]
    path.write_text(json.dumps(score), encoding="utf-8")

    text = _stage(run_dir)

    assert "judge errors 1 |" in text


@pytest.mark.skipif(not EXAMPLE_RUN.exists(), reason="example-run not present")
def test_the_committed_example_run_renders(tmp_path):
    """The real 11-row artifacts render end to end — the shape is not invented."""
    import shutil

    run_dir = tmp_path / "example-run"
    shutil.copytree(EXAMPLE_RUN, run_dir)

    text = markdown_report.write_report(run_dir).read_text(encoding="utf-8")

    assert text.startswith("# Grading run — ")
    assert "prototype-specify" in text
    assert "## Rejudge this run" in text
    assert (run_dir / "reports" / "prototype_specify_report.md").exists()


def _row_line(text: str, row_id: str) -> str:
    """The single rows-table line for one row id."""
    return next(line for line in text.splitlines() if line.startswith(f"| `{row_id}`"))


def test_letter_grade_bands():
    """A++ is above the top anchor band; F is a fail, not just a low mark."""
    assert markdown_report.letter_grade(98.0) == "A++"
    assert markdown_report.letter_grade(95.0) == "A+"
    assert markdown_report.letter_grade(91.0) == "A"
    assert markdown_report.letter_grade(85.0) == "B"
    assert markdown_report.letter_grade(72.5) == "C"
    assert markdown_report.letter_grade(64.0) == "D"
    assert markdown_report.letter_grade(50.0) == "E"
    assert markdown_report.letter_grade(49.9) == "F"


def test_top_report_leads_with_the_grade(run_dir):
    """The blended score and letter grade sit at the top of report.md."""
    text = _top(run_dir)

    # The fixture has one judged row at 82 and one judge-failure row (excluded:
    # it passed precheck and carries no quality signal) -> overall 82.0, grade B.
    assert "## Grade: B — 82.0 / 100" in text
    assert "F <50 = fail" in text
    overall = markdown_report.compute_overall(run_dir)
    assert overall == {
        "score": 82.0, "grade": "B", "counted": 1, "failed_cells": 0,
        "stages": {"prototype-specify": {"effective": 82.0, "cells": 1, "failed": 0}},
    }
    # The table's overall footer carries the same number as the headline.
    assert "**overall — grade B**" in text
    assert "**82.0**" in text


def test_the_report_links_prompt_advice_when_the_run_produced_it(run_dir):
    """Advice written by the run's advise step is reachable from the top report."""
    reports = run_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "prompt_advice_prototype_specify.md").write_text("# advice", encoding="utf-8")

    text = _top(run_dir)

    assert "### Prompt advice" in text
    assert "(prompt_advice_prototype_specify.md)" in text


def test_a_run_without_advice_links_none(run_dir):
    """No advice file, no link — a 404 in a report is worse than an absence."""
    text = _top(run_dir)

    assert "Prompt advice" not in text


def test_failed_cells_score_zero_in_the_overall(run_dir):
    """A precheck-failed row drags the grade down instead of shrinking the mean."""
    import json as _json
    path = run_dir / "artifacts" / "prototype_specify_score.json"
    score = _json.loads(path.read_text())
    score["results"][1]["precheck_passed"] = False
    path.write_text(_json.dumps(score), encoding="utf-8")

    overall = markdown_report.compute_overall(run_dir)

    assert overall["counted"] == 2 and overall["failed_cells"] == 1
    assert overall["score"] == 41.0  # (82 + 0) / 2
    assert overall["grade"] == "F"
