"""Unit tests for evals.grading.markdown_report — the run-folder REPORT.md.

Offline: builds a run folder on disk from plain dicts and asserts on the
rendered markdown. Also renders the REAL committed example-run, so a shape
change in the artifacts breaks a test rather than a report someone is reading.
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


def test_write_report_lands_in_the_run_folder(run_dir):
    path = markdown_report.write_report(run_dir)

    assert path == run_dir / "REPORT.md"
    assert path.read_text(encoding="utf-8").startswith("# Grading run — ")


def test_report_leads_with_identity_and_the_models_that_produced_it(run_dir):
    text = markdown_report.write_report(run_dir).read_text(encoding="utf-8")

    assert "`mistral/mistral-small-latest`" in text
    assert "`mistral/mistral-large-latest`" in text
    assert "ten-industries" in text
    assert "**Not run:** `prototype-plan`" in text


def test_report_carries_scores_dimensions_and_tokens(run_dir):
    text = markdown_report.write_report(run_dir).read_text(encoding="utf-8")

    assert "| `prototype-specify` | completed | 1.00 |" in text
    assert "| `data_realism` | 1 | 85.00 |" in text
    assert "| agent | 8857 | 9930 | 18787 |" in text
    assert "| judge | 4000 | 500 | 4500 |" in text
    assert "**23287**" in text, "the headline total covers agent AND judge"


def test_report_shows_a_failed_judge_on_the_row_that_failed(run_dir):
    text = markdown_report.write_report(run_dir).read_text(encoding="utf-8")

    assert "**judge failed**" in text
    assert "3 validation errors for JudgeOutput" in text
    assert "⚠️ Warnings" in text
    assert "\n" not in _row_line(text, "healthcare_scheduling"), "one row, one line"


def test_report_carries_the_judges_narrative_per_row(run_dir):
    text = markdown_report.write_report(run_dir).read_text(encoding="utf-8")

    assert "Solid, domain-specific detail throughout." in text
    assert "- realistic invoice table" in text
    assert "`data_realism` — ACME Corp $12,480.00" in text
    assert "Recurring weaknesses" in text


def test_report_names_the_command_that_reproduces_the_run(run_dir):
    text = markdown_report.write_report(run_dir).read_text(encoding="utf-8")

    assert "grade_config.resolved.yaml" in text


def test_cli_overrides_are_flagged_as_breaking_reproducibility(run_dir):
    summary = json.loads((run_dir / "run_summary.json").read_text())
    summary["config"]["overrides"] = {"limit": 2}
    (run_dir / "run_summary.json").write_text(json.dumps(summary), encoding="utf-8")

    text = markdown_report.write_report(run_dir).read_text(encoding="utf-8")

    assert "`limit=2`" in text
    assert "will **not** reproduce it" in text


def test_a_pre_split_run_attributes_flat_tokens_to_the_agent(run_dir):
    """Legacy score.json has no breakdown; a zero agent row would contradict the total."""
    path = run_dir / "artifacts" / "prototype_specify_score.json"
    score = json.loads(path.read_text())
    score["tokens"] = {"in": 8857, "out": 9930, "total": 18787}
    path.write_text(json.dumps(score), encoding="utf-8")

    text = markdown_report.write_report(run_dir).read_text(encoding="utf-8")

    assert "| agent | 8857 | 9930 | 18787 |" in text
    assert "| judge | 0 | 0 | 0 |" in text


def test_a_pre_split_run_still_counts_judge_errors_from_the_grades(run_dir):
    path = run_dir / "artifacts" / "prototype_specify_score.json"
    score = json.loads(path.read_text())
    del score["counts"]["judge_errored"]
    path.write_text(json.dumps(score), encoding="utf-8")

    text = markdown_report.write_report(run_dir).read_text(encoding="utf-8")

    assert "judge errors 1 |" in text


@pytest.mark.skipif(not EXAMPLE_RUN.exists(), reason="example-run not present")
def test_the_committed_example_run_renders(tmp_path):
    """The real 11-row artifacts render end to end — the shape is not invented."""
    import shutil

    run_dir = tmp_path / "example-run"
    shutil.copytree(EXAMPLE_RUN, run_dir)

    text = markdown_report.render_report(
        run_dir, json.loads((run_dir / "run_summary.json").read_text())
    )

    assert text.startswith("# Grading run — ")
    assert "prototype-specify" in text
    assert "## Reproduce" in text


def _row_line(text: str, row_id: str) -> str:
    """The single rows-table line for one row id."""
    return next(line for line in text.splitlines() if line.startswith(f"| `{row_id}`"))
