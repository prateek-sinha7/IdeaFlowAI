"""Unit tests for evals.model_graded.report — per-run-folder JSON
files (run.json/grade.json inside model_graded/logs/<run_id>/), the
summarize()/worst() view computed by scanning them (tasks T10-T11, revised
per user request: readable per-run files instead of one growing JSONL).
"""

from __future__ import annotations

import json

import pytest

from evals.model_graded import report as report_mod

VALID_RUN = {
    "timestamp": "2026-07-28T15:08:02Z",
    "run_id": "run-1",
    "scenario_id": "s1",
    "agent_id": "prototype-specify",
    "provider": None,
    "model": None,
    "resolved_model_id": "claude-haiku-4-5-20251001",
    "system_prompt_path": "x",
    "system_prompt_hash": "sha256:abc",
    "prompt": "brief",
    "response": "<spec>...</spec>",
    "precheck_passed": True,
    "precheck_reason": "ok",
    "tokens_in": 10,
    "tokens_out": 20,
}

VALID_GRADE = {
    "run_id": "run-1",
    "judge_provider": None,
    "judge_model": None,
    "judge_resolved_model_id": "claude-haiku-4-5-20251001",
    "judge_threshold": 70,
    "score": 80,
    "passed": True,
    "rationale": "good",
    "strengths": ["realistic invoice data"],
    "weaknesses": ["dashboard is generic"],
    "errored": False,
    "error_reason": None,
}


def test_write_run_missing_field_raises_and_does_not_write(tmp_path):
    bad = {k: v for k, v in VALID_RUN.items() if k != "response"}
    run_dir = tmp_path / "run-1"
    with pytest.raises(ValueError, match="missing required field"):
        report_mod.write_run(run_dir, bad)
    assert not (run_dir / "run.json").exists()


def test_write_run_is_pretty_printed_and_readable(tmp_path):
    run_dir = tmp_path / "run-1"
    report_mod.write_run(run_dir, VALID_RUN)
    content = (run_dir / "run.json").read_text()
    assert "\n" in content  # not a single-line blob
    assert json.loads(content)["prompt"] == "brief"


def test_write_grade_missing_field_raises(tmp_path):
    bad = {k: v for k, v in VALID_GRADE.items() if k != "score"}
    run_dir = tmp_path / "run-1"
    with pytest.raises(ValueError, match="missing required field"):
        report_mod.write_grade(run_dir, bad)
    assert not (run_dir / "grade.json").exists()


def test_load_run_entries_empty_when_logs_root_absent(tmp_path):
    assert report_mod.load_run_entries(logs_root=tmp_path / "nope") == []


def test_load_run_entries_merges_run_and_grade(tmp_path):
    run_dir = tmp_path / "run-1"
    report_mod.write_run(run_dir, VALID_RUN)
    report_mod.write_grade(run_dir, VALID_GRADE)

    entries = report_mod.load_run_entries(logs_root=tmp_path)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["prompt"] == "brief"
    assert entry["judge_score"] == 80
    assert entry["judge_strengths"] == ["realistic invoice data"]
    assert entry["judge_weaknesses"] == ["dashboard is generic"]


def test_load_run_entries_ungraded_run_has_none_judge_fields(tmp_path):
    run_dir = tmp_path / "run-1"
    report_mod.write_run(run_dir, VALID_RUN)  # no grade.json written

    entries = report_mod.load_run_entries(logs_root=tmp_path)
    assert entries[0]["judge_score"] is None


def test_load_run_entries_skips_folders_without_run_json(tmp_path):
    (tmp_path / "not-a-run").mkdir()
    (tmp_path / "not-a-run" / "log.txt").write_text("some transcript, no run.json")

    entries = report_mod.load_run_entries(logs_root=tmp_path)
    assert entries == []


def test_load_run_entries_sorted_oldest_first(tmp_path):
    for run_id, ts in [("run-b", "2026-07-02T00:00:00Z"), ("run-a", "2026-07-01T00:00:00Z")]:
        report_mod.write_run(tmp_path / run_id, {**VALID_RUN, "run_id": run_id, "timestamp": ts})

    entries = report_mod.load_run_entries(logs_root=tmp_path)
    assert [e["run_id"] for e in entries] == ["run-a", "run-b"]


def test_summarize_empty_entries_returns_clean_zero_result():
    summary = report_mod.summarize([])
    assert summary["total"] == 0
    assert summary["precheck_pass_rate"] is None
    assert summary["judge_pass_rate"] is None


def test_worst_orders_ascending_and_excludes_ungraded(tmp_path):
    for run_id, score in [("a", 90), ("b", 30), ("c", None), ("d", 60)]:
        report_mod.write_run(tmp_path / run_id, {**VALID_RUN, "run_id": run_id})
        if score is not None:
            report_mod.write_grade(tmp_path / run_id, {**VALID_GRADE, "run_id": run_id, "score": score})

    entries = report_mod.load_run_entries(logs_root=tmp_path)
    result = report_mod.worst(entries, 2)
    assert [e["run_id"] for e in result] == ["b", "d"]


def test_summarize_group_by_system_prompt_hash_chronological_with_target():
    entries = [
        {
            **VALID_RUN,
            "run_id": "a",
            "timestamp": "2026-07-01T00:00:00Z",
            "system_prompt_hash": "sha256:v1",
            "judge_score": 60,
            "judge_passed": False,
        },
        {
            **VALID_RUN,
            "run_id": "b",
            "timestamp": "2026-07-02T00:00:00Z",
            "system_prompt_hash": "sha256:v2",
            "judge_score": 95,
            "judge_passed": True,
        },
    ]
    summary = report_mod.summarize(entries, group_by="system_prompt_hash", target=90)
    keys = list(summary["groups"].keys())
    assert keys == ["sha256:v1", "sha256:v2"]
    assert summary["groups"]["sha256:v1"]["target_met"] is False
    assert summary["groups"]["sha256:v2"]["target_met"] is True


def test_compute_system_prompt_hash_reflects_file_content(tmp_path):
    f = tmp_path / "AGENT.md"
    f.write_text("v1")
    h1 = report_mod.compute_system_prompt_hash(str(f))
    f.write_text("v2")
    h2 = report_mod.compute_system_prompt_hash(str(f))
    assert h1 != h2
    assert h1.startswith("sha256:")
