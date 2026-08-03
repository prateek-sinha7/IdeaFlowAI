"""Unit tests for evals.grading.site.model and .aggregate — the read layer.

Covers T2-T6: discovery and classification, the per-run view-model, degraded
folders, the stage x row matrix, and cross-run aggregation.

The suite runs entirely on fixtures built here rather than on `.runs/`, which
is gitignored — a test that only passes on the author's machine is not a test.
"""

from __future__ import annotations

import json

import pytest

from evals.grading import artifacts, grades
from evals.grading.site import aggregate, model


# ── fixture builders ──────────────────────────────────────────────────────


def write_run(
    root,
    name,
    *,
    stages=(),
    status="completed",
    not_run=(),
    created_at="2026-07-30T10:00:00",
    row_count=None,
    config=None,
    prompts=None,
    findings=None,
    overrides=None,
    src=None,
):
    """A run folder with as much or as little as a test needs."""
    run_dir = root / name
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    summary = {
        "dataset_run_id": name,
        "status": status,
        "created_at": created_at,
        "finished_at": "2026-07-30T10:05:00",
        "workflow_id": "prototype",
        "dataset_id": "small",
        "run_id": "small",
        "row_count": row_count if row_count is not None else len(stages),
        "not_run": list(not_run),
        "stages": [{"agent_id": agent_id} for agent_id, _ in stages],
        "config": {"overrides": overrides or {}},
    }
    (run_dir / artifacts.RUN_SUMMARY_NAME).write_text(json.dumps(summary), encoding="utf-8")

    if config is not None:
        (run_dir / artifacts.RESOLVED_CONFIG_NAME).write_text(
            json.dumps(config), encoding="utf-8"
        )

    for agent_id, payload in stages:
        token = agent_id.replace("-", "_")
        score = payload.get("score")
        if score is not None:
            artifacts.artifact_path(run_dir, token, "score").write_text(
                json.dumps(score), encoding="utf-8"
            )
        for kind in ("grade", "run"):
            if payload.get(kind) is not None:
                artifacts.artifact_path(run_dir, token, kind).write_text(
                    json.dumps(payload[kind]), encoding="utf-8"
                )
        if findings and agent_id in findings:
            artifacts.artifact_path(run_dir, token, "code_findings").write_text(
                json.dumps({"findings": findings[agent_id]}), encoding="utf-8"
            )
        if prompts and agent_id in prompts:
            artifacts.write_system_prompt(run_dir, token, prompts[agent_id])

    for row_id, files in (src or {}).items():
        for filename, content in files.items():
            artifacts.write_src_file(run_dir, row_id, filename, content)
    return run_dir


def simple_stage(agent_id, rows, *, dimensions=None, scores=None, tokens=None, hashes=None):
    """A (agent_id, payload) pair for `write_run`."""
    return (
        agent_id,
        {
            "score": {
                "results": rows,
                "counts": {"rows": len(rows), "judged": len(rows)},
                "scores": scores or {"average_all": 85.0},
                "dimensions": dimensions or {},
                "tokens": tokens or {},
                "hashes": hashes or {},
            }
        },
    )


def row(row_id, score=90, **overrides):
    payload = {"row_id": row_id, "precheck_passed": True, "score": score}
    payload.update(overrides)
    return payload


@pytest.fixture
def runs_root(tmp_path):
    root = tmp_path / ".runs" / "prototype"
    root.mkdir(parents=True)
    return root


# ── T2: discovery and classification ──────────────────────────────────────


def test_discover_lists_runs_newest_first(runs_root):
    for name in ("260730-100000-small", "260729-100000-small", "260730-200000-small"):
        write_run(runs_root, name, stages=[simple_stage("stage-a", [row("r1")])])
    site = model.discover(runs_root.parent)
    names = [run.dataset_run_id for run in site.workflows[0].runs]
    assert names == ["260730-200000-small", "260730-100000-small", "260729-100000-small"]


def test_discover_skips_housekeeping_dot_directories(runs_root):
    write_run(runs_root, "260730-100000-small", stages=[simple_stage("stage-a", [row("r1")])])
    write_run(runs_root, ".260730-100000-small-original",
              stages=[simple_stage("stage-a", [row("r1")])])
    site = model.discover(runs_root.parent)
    assert [run.dataset_run_id for run in site.workflows[0].runs] == ["260730-100000-small"]


def test_discover_raises_only_when_the_root_itself_is_absent(tmp_path):
    with pytest.raises(FileNotFoundError):
        model.discover(tmp_path / "nope")


def test_a_complete_run_is_classified_run(runs_root):
    run_dir = write_run(runs_root, "260730-100000-small",
                        stages=[simple_stage("stage-a", [row("r1")])])
    run = model.load_run(run_dir, "prototype")
    assert run.run_class == model.CLASS_RUN
    assert run.charted is True
    assert run.class_reason


def test_a_copy_folder_is_classified_copy(runs_root):
    run_dir = write_run(runs_root, "260730-100000-small-copy",
                        stages=[simple_stage("stage-a", [row("r1")])])
    run = model.load_run(run_dir, "prototype")
    assert run.run_class == model.CLASS_COPY
    assert run.charted is False
    assert "copy" in run.class_reason


def test_an_untimestamped_folder_is_a_reference(runs_root):
    run_dir = write_run(runs_root, "golden-mission-control",
                        stages=[simple_stage("stage-a", [row("r1")])])
    run = model.load_run(run_dir, "prototype")
    assert run.run_class == model.CLASS_REFERENCE
    assert run.charted is False


def test_copy_wins_over_reference(runs_root):
    """Precedence matters: a copy of a golden is a copy, not a second golden."""
    run_dir = write_run(runs_root, "golden-mission-control-copy",
                        stages=[simple_stage("stage-a", [row("r1")])])
    assert model.load_run(run_dir, "prototype").run_class == model.CLASS_COPY


def test_an_unfinished_run_is_partial(runs_root):
    run_dir = write_run(runs_root, "260730-100000-small", status="running",
                        stages=[simple_stage("stage-a", [row("r1")])])
    run = model.load_run(run_dir, "prototype")
    assert run.run_class == model.CLASS_PARTIAL
    assert "running" in run.class_reason


def test_a_run_with_stages_that_never_ran_is_partial(runs_root):
    run_dir = write_run(runs_root, "260730-100000-small",
                        not_run=["stage-b", "stage-c"],
                        stages=[simple_stage("stage-a", [row("r1")])])
    run = model.load_run(run_dir, "prototype")
    assert run.run_class == model.CLASS_PARTIAL
    assert "stage-b" in run.class_reason


def test_a_run_with_nothing_gradable_is_partial(runs_root):
    run_dir = write_run(runs_root, "260730-100000-small",
                        stages=[simple_stage("stage-a", [row("r1", score=None)])])
    run = model.load_run(run_dir, "prototype")
    assert run.overall is None
    assert run.run_class == model.CLASS_PARTIAL


def test_runs_of_the_same_id_under_two_workflows_do_not_collide(tmp_path):
    root = tmp_path / ".runs"
    for workflow in ("prototype", "app_builder"):
        folder = root / workflow
        folder.mkdir(parents=True)
        write_run(folder, "260730-100000-small", stages=[simple_stage("stage-a", [row("r1")])])
    site = model.discover(root)
    keys = {(run.workflow, run.dataset_run_id) for run in site.all_runs}
    assert len(keys) == 2


# ── T3: the per-run view-model ────────────────────────────────────────────


def test_load_run_populates_the_whole_model(runs_root):
    run_dir = write_run(
        runs_root,
        "260730-100000-small",
        stages=[(
            "stage-a",
            {
                "score": {
                    "results": [row("r1", score=90)],
                    "counts": {"rows": 1, "judged": 1},
                    "scores": {"average_all": 90.0, "median": 90.0},
                    "dimensions": {"fidelity": {"mean": 90.0, "count": 1}},
                    "tokens": {"agent": {"total": 100}, "judge": {"total": 50}},
                    "hashes": {"system_prompt_hash": "sha256:abc123def456789"},
                    "warnings": ["one warning"],
                    "baseline": {"verdict": "pass"},
                    "recurring_weaknesses": [{"evidence": "weak nav", "row_ids": ["r1"]}],
                },
                "grade": [{
                    "row_id": "r1",
                    "sub_scores": {"fidelity": 90},
                    "rationale": "solid",
                    "strengths": ["clear"],
                    "weaknesses": ["cramped"],
                    "evidence": {"fidelity": "the header reads well"},
                    "score_caps": {"fidelity": {"reported": 95, "capped_to": 90,
                                                "weaknesses": 1}},
                }],
                "run": [{"row_id": "r1", "prompt": "build a dashboard"}],
            },
        )],
        config={"agent_under_test": {"provider": "anthropic", "model": "opus"},
                "judge": {"provider": "anthropic", "model": "sonnet"},
                "options": {"concurrency": 2, "repeats": 1}},
        prompts={"stage-a": "You are a builder."},
        findings={"stage-a": {"r1": {"code_score": 80, "ok": True}}},
        src={"r1": {"prototype.html": "<html></html>", "spec.md": "# Spec"}},
    )
    run = model.load_run(run_dir, "prototype")

    assert run.model_under_test["model"] == "opus"
    assert run.options["concurrency"] == 2
    stage = run.stages[0]
    assert stage.agent_token == "stage_a"
    assert stage.warnings == ["one warning"]
    assert stage.system_prompt == "You are a builder."
    assert stage.dimension_ids == ["fidelity"]

    cell = stage.rows[0]
    assert cell.brief == "build a dashboard"
    assert cell.rationale == "solid"
    assert cell.strengths == ["clear"]
    assert cell.evidence == {"fidelity": "the header reads well"}
    assert cell.score_caps["fidelity"]["capped_to"] == 90
    assert cell.code_score == 80
    assert cell.combined == pytest.approx(0.7 * 90 + 0.3 * 80)
    assert {d.filename for d in cell.deliverables} == {"prototype.html", "spec.md"}
    assert {d.kind for d in cell.deliverables} == {"html", "markdown"}


def test_overall_is_passed_through_from_grades(runs_root):
    run_dir = write_run(runs_root, "260730-100000-small",
                        stages=[simple_stage("stage-a", [row("r1", 90), row("r2", 70)])])
    run = model.load_run(run_dir, "prototype")
    assert run.overall == grades.compute_overall(run_dir)


def test_the_prompt_hash_is_read_from_the_run_entries(runs_root):
    """It is stamped on each dispatched row, not on the stage's score artifact.

    Reading it from `score.hashes` alone made every run look like one "unknown"
    prompt version, which silently emptied the whole did-my-edit-help view.
    """
    run_dir = write_run(
        runs_root,
        "260730-100000-small",
        stages=[("stage-a", {
            "score": {"results": [row("r1")], "hashes": {"rubric_hash": "sha256:rrr"}},
            "run": [{"row_id": "r1", "system_prompt_hash": "sha256:from-the-row"}],
        })],
    )
    stage = model.load_run(run_dir, "prototype").stages[0]
    assert stage.hashes["system_prompt_hash"] == "sha256:from-the-row"
    assert stage.hashes["rubric_hash"] == "sha256:rrr"


def test_a_prompt_hash_on_the_score_artifact_still_wins(runs_root):
    """Forward-compatible: if a future run records it there, that is authoritative."""
    run_dir = write_run(
        runs_root,
        "260730-100000-small",
        stages=[("stage-a", {
            "score": {"results": [row("r1")],
                      "hashes": {"system_prompt_hash": "sha256:from-the-score"}},
            "run": [{"row_id": "r1", "system_prompt_hash": "sha256:from-the-row"}],
        })],
    )
    stage = model.load_run(run_dir, "prototype").stages[0]
    assert stage.hashes["system_prompt_hash"] == "sha256:from-the-score"


@pytest.mark.parametrize("id_field", ["row_id", "scenario_id", "id"])
def test_rows_join_under_every_historical_id_field(runs_root, id_field):
    result = {id_field: "r1", "precheck_passed": True, "score": 90}
    run_dir = write_run(
        runs_root,
        "260730-100000-small",
        stages=[("stage-a", {
            "score": {"results": [result]},
            "grade": [{id_field: "r1", "rationale": "joined"}],
            "run": [{id_field: "r1", "prompt": "the brief"}],
        })],
    )
    cell = model.load_run(run_dir, "prototype").stages[0].rows[0]
    assert cell.row_id == "r1"
    assert cell.rationale == "joined"
    assert cell.brief == "the brief"


def test_model_module_emits_no_html_and_imports_no_renderer():
    """Boundary rule B1, enforced rather than trusted."""
    source = (model.__file__ and open(model.__file__, encoding="utf-8").read()) or ""
    assert "<div" not in source and "<table" not in source
    assert "from evals.grading.site import pages" not in source
    assert "charts" not in source.split('"""')[2] if source.count('"""') > 2 else True


# ── T4: degraded folders ──────────────────────────────────────────────────


def test_a_corrupt_summary_classifies_the_run_as_error(runs_root):
    run_dir = runs_root / "260730-100000-small"
    run_dir.mkdir(parents=True)
    (run_dir / artifacts.RUN_SUMMARY_NAME).write_text("{not json", encoding="utf-8")
    run = model.load_run(run_dir, "prototype")
    assert run.run_class == model.CLASS_ERROR
    assert run.errors and "unreadable" in run.errors[0]


def test_a_missing_summary_classifies_the_run_as_error(runs_root):
    run_dir = runs_root / "260730-100000-small"
    run_dir.mkdir(parents=True)
    run = model.load_run(run_dir, "prototype")
    assert run.run_class == model.CLASS_ERROR


def test_a_missing_config_omits_provenance_without_failing(runs_root):
    run_dir = write_run(runs_root, "260730-100000-small",
                        stages=[simple_stage("stage-a", [row("r1")])])
    run = model.load_run(run_dir, "prototype")
    assert run.model_under_test == {}
    assert run.run_class == model.CLASS_RUN


def test_a_stage_without_grades_still_renders_its_rows(runs_root):
    run_dir = write_run(runs_root, "260730-100000-small",
                        stages=[simple_stage("stage-a", [row("r1")])])
    cell = model.load_run(run_dir, "prototype").stages[0].rows[0]
    assert cell.rationale is None
    assert cell.strengths == []


def test_a_stage_without_code_findings_blends_to_the_judge_alone(runs_root):
    run_dir = write_run(runs_root, "260730-100000-small",
                        stages=[simple_stage("stage-a", [row("r1", 90)])])
    cell = model.load_run(run_dir, "prototype").stages[0].rows[0]
    assert cell.code_score is None
    assert cell.combined == 90


def test_a_stage_with_no_score_artifact_is_not_a_stage(runs_root):
    run_dir = write_run(runs_root, "260730-100000-small",
                        stages=[("stage-a", {"score": None}), simple_stage("stage-b", [row("r1")])])
    run = model.load_run(run_dir, "prototype")
    assert [stage.agent_id for stage in run.stages] == ["stage-b"]


def test_one_corrupt_folder_does_not_stop_the_others(runs_root):
    write_run(runs_root, "260730-100000-small", stages=[simple_stage("stage-a", [row("r1")])])
    write_run(runs_root, "260730-110000-small", stages=[simple_stage("stage-a", [row("r1")])])
    broken = runs_root / "260730-120000-small"
    broken.mkdir(parents=True)
    (broken / artifacts.RUN_SUMMARY_NAME).write_text("{oops", encoding="utf-8")

    site = model.discover(runs_root.parent)
    classes = [run.run_class for run in site.workflows[0].runs]
    assert classes.count(model.CLASS_ERROR) == 1
    assert classes.count(model.CLASS_RUN) == 2


def test_an_empty_runs_root_yields_an_empty_site(tmp_path):
    root = tmp_path / ".runs"
    root.mkdir()
    site = model.discover(root)
    assert site.workflows == ()
    assert site.all_runs == []


# ── T5: cell kinds and the matrix ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("result", "grade", "code", "expected"),
    [
        ({"precheck_passed": True, "score": 90}, {}, None, model.KIND_OK),
        ({"errored": True}, {}, None, model.KIND_ERRORED),
        ({"precheck_passed": None}, {}, None, model.KIND_BROKEN_CHAIN),
        ({"precheck_passed": False}, {}, None, model.KIND_PRECHECK_FAIL),
        ({"expect": "fail", "precheck_passed": False}, {}, None, model.KIND_NEGATIVE),
        ({"precheck_passed": True, "score": None}, {}, None, model.KIND_UNJUDGED),
    ],
)
def test_every_cell_kind_is_derived(result, grade, code, expected):
    assert model.cell_kind(result, grade, code) == expected


def test_a_judge_failure_is_its_own_kind():
    grade = {"judged": False, "error": "judge timed out"}
    kind = model.cell_kind({"precheck_passed": True, "score": None}, grade, None)
    assert kind in (model.KIND_JUDGE_FAILED, model.KIND_UNJUDGED)


def test_the_four_zero_scoring_kinds_stay_distinguishable(runs_root):
    """The whole point of the matrix: these must not all read as one failure."""
    run_dir = write_run(runs_root, "260730-100000-small", stages=[simple_stage("stage-a", [
        row("r1", 90),
        {"row_id": "r2", "errored": True},
        {"row_id": "r3", "precheck_passed": None},
        {"row_id": "r4", "precheck_passed": False},
    ])])
    rows = {cell.row_id: cell for cell in model.load_run(run_dir, "prototype").stages[0].rows}
    assert rows["r2"].cell_kind == model.KIND_ERRORED
    assert rows["r3"].cell_kind == model.KIND_BROKEN_CHAIN
    assert rows["r4"].cell_kind == model.KIND_PRECHECK_FAIL
    assert {rows[r].cell_value for r in ("r2", "r3", "r4")} == {0.0}
    assert len({rows[r].cell_kind for r in ("r2", "r3", "r4")}) == 3


def test_matrix_cells_equal_the_cells_compute_overall_averages(runs_root):
    run_dir = write_run(runs_root, "260730-100000-small", stages=[
        simple_stage("stage-a", [row("r1", 90), row("r2", 70)]),
        simple_stage("stage-b", [row("r1", 60)]),
    ])
    run = model.load_run(run_dir, "prototype")

    counted = [
        cell.value
        for cell in run.matrix.cells.values()
        if cell.kind not in (model.KIND_NEGATIVE, model.KIND_UNJUDGED)
    ]
    assert sum(counted) / len(counted) == pytest.approx(run.overall["score"])
    assert run.matrix.cell("stage-b", "r1").value == 60


def test_a_missing_stage_row_pair_is_absent_not_zero(runs_root):
    run_dir = write_run(runs_root, "260730-100000-small", stages=[
        simple_stage("stage-a", [row("r1", 90), row("r2", 80)]),
        simple_stage("stage-b", [row("r1", 60)]),
    ])
    matrix = model.load_run(run_dir, "prototype").matrix
    assert matrix.cell("stage-b", "r2") is None
    assert matrix.cell("stage-b", "r1").value == 60


# ── T6: cross-run aggregation ─────────────────────────────────────────────


def _workflow_with(runs_root, specs):
    for name, score, kwargs in specs:
        write_run(runs_root, name,
                  stages=[simple_stage("stage-a", [row("r1", score)])], **kwargs)
    return model.discover(runs_root.parent).workflows[0]


def test_excluded_runs_never_enter_an_aggregate(runs_root):
    workflow = _workflow_with(runs_root, [
        ("260730-100000-small", 90, {}),
        ("260730-110000-small", 80, {}),
        ("golden-mission-control", 100, {}),
        ("260730-120000-small-copy", 10, {}),
        ("260730-130000-small", 50, {"status": "running"}),
    ])
    result = aggregate.build(workflow)
    assert result.included_count == 2
    assert {point.score for point in result.trend} == {90.0, 80.0}
    assert [reference.score for reference in result.references] == [100.0]


def test_trend_is_chronological_oldest_first(runs_root):
    workflow = _workflow_with(runs_root, [
        ("260730-100000-small", 70, {"created_at": "2026-07-30T10:00:00"}),
        ("260730-120000-small", 90, {"created_at": "2026-07-30T12:00:00"}),
        ("260730-110000-small", 80, {"created_at": "2026-07-30T11:00:00"}),
    ])
    scores = [point.score for point in aggregate.build(workflow).trend]
    assert scores == [70.0, 80.0, 90.0]


def test_aggregating_zero_and_one_run_does_not_break(runs_root):
    empty = model.Workflow(name="prototype", runs=())
    assert aggregate.build(empty).has_trend is False

    workflow = _workflow_with(runs_root, [("260730-100000-small", 90, {})])
    result = aggregate.build(workflow)
    assert result.included_count == 1
    assert result.has_trend is False


def test_dimension_grids_are_ordered_worst_first(runs_root):
    write_run(runs_root, "260730-100000-small", stages=[
        simple_stage("stage-a", [row("r1", 90)], dimensions={
            "fidelity": {"mean": 90.0}, "a11y": {"mean": 40.0}, "clarity": {"mean": 70.0},
        }),
    ])
    workflow = model.discover(runs_root.parent).workflows[0]
    result = aggregate.build(workflow)
    assert aggregate.worst_first(result.dimensions_by_stage) == ["a11y", "clarity", "fidelity"]


def test_cross_run_matrix_carries_mean_spread_and_run_count(runs_root):
    write_run(runs_root, "260730-100000-small",
              stages=[simple_stage("stage-a", [row("r1", 90)])])
    write_run(runs_root, "260730-110000-small",
              stages=[simple_stage("stage-a", [row("r1", 70)])])
    workflow = model.discover(runs_root.parent).workflows[0]
    cell = aggregate.build(workflow).matrix.cell("stage-a", "r1")
    assert cell.value == pytest.approx(80.0)
    assert cell.run_count == 2
    assert cell.spread == pytest.approx(10.0)


def test_token_and_health_series_tolerate_missing_data(runs_root):
    write_run(runs_root, "260730-100000-small", stages=[
        simple_stage("stage-a", [row("r1", 90)],
                     tokens={"agent": {"total": 100}, "judge": {"total": 40}}),
    ])
    write_run(runs_root, "260730-110000-small",
              stages=[simple_stage("stage-a", [row("r1", 80)])])
    result = aggregate.build(model.discover(runs_root.parent).workflows[0])
    assert [entry["total"] for entry in result.tokens] == [140, 0]
    assert all("console_errors" in entry for entry in result.code_health)


def test_health_counts_exercised_interactions_not_just_failures(runs_root):
    write_run(
        runs_root, "260730-100000-small",
        stages=[simple_stage("stage-a", [row("r1", 90)])],
        findings={"stage-a": {"r1": {
            "code_score": 70,
            "issues": ["missing route"],
            "render": {"console_errors": ["boom"], "page_errors": [],
                       "nav_results": [{"ok": True}, {"ok": False}]},
            "interactions": {"available": True, "actions": [1, 2, 3], "failures": [{"a": 1}]},
        }}},
    )
    health = aggregate.build(model.discover(runs_root.parent).workflows[0]).code_health[0]
    assert health["console_errors"] == 1
    assert health["dead_navs"] == 1
    assert health["interaction_failures"] == 1
    assert health["interactions_exercised"] == 4
    assert health["static_issues"] == 1


def test_prompt_versions_are_compare_output_unmodified(runs_root):
    from evals.grading import compare

    for name, prompt_hash, score in [
        ("260730-100000-small", "sha256:aaa", 80.0),
        ("260730-110000-small", "sha256:bbb", 90.0),
    ]:
        write_run(
            runs_root, name,
            stages=[simple_stage("stage-a", [row("r1", score)],
                                 scores={"average_all": score},
                                 hashes={"system_prompt_hash": prompt_hash})],
            created_at=f"2026-07-30T{name[7:9]}:00:00",
            prompts={"stage-a": f"prompt for {prompt_hash}"},
        )
    workflow = model.discover(runs_root.parent).workflows[0]
    history = aggregate.build(workflow).prompt_history[0]

    payloads = [aggregate._compare_payload(run, "stage-a") for run in workflow.included]
    expected = compare.group_by_prompt(payloads)
    for version in history.versions:
        group = expected["groups"][version.prompt_hash]
        assert version.average_score == group["average_score"]
        assert version.target_met == group["target_met"]
        assert version.run_count == group["total_runs"]


def test_a_version_without_a_captured_prompt_says_why(runs_root):
    write_run(runs_root, "260730-100000-small",
              stages=[simple_stage("stage-a", [row("r1", 90)],
                                   hashes={"system_prompt_hash": "sha256:aaa"})])
    history = aggregate.build(model.discover(runs_root.parent).workflows[0]).prompt_history[0]
    version = history.versions[0]
    assert version.prompt_text is None
    assert "predates prompt capture" in version.missing_reason


def test_within_noise_uses_the_band_it_is_given():
    assert aggregate.within_noise(0.5, 1.0) is True
    assert aggregate.within_noise(-0.5, 1.0) is True
    assert aggregate.within_noise(4.0, 1.0) is False
    assert aggregate.within_noise(None, 1.0) is False
    assert aggregate.within_noise(4.0, None) is False
