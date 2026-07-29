"""Unit tests for evals.grading.grade_runner — the CLI entry point.

Offline only: `dispatch.run_row`, `judge.grade` and `judge.resolve_judge_model`
are monkeypatched, so no model and no network are ever touched. The real
workflow folder is copied into tmp_path, so no run folder lands in the repo.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pathlib

import pytest
import yaml

from evals.grading import (
    artifacts,
    config,
    dispatch,
    grade_runner,
    judge,
    model_grader,
)

GRADING_DIR = Path(__file__).resolve().parents[2] / "evals" / "grading"
REAL_WORKFLOW_DIR = GRADING_DIR / "model" / "workflows" / "prototype"
CONFIGS_DIR = GRADING_DIR / "configs"
SMOKE_CONFIG = str(CONFIGS_DIR / "smoke.yaml")


def _row_count(config_path: str) -> int:
    """How many rows a config actually selects — derived, never hardcoded.

    Configs are edited: smoke's dataset and row limit have both changed. A test
    that hardcodes "2" fails on an intentional edit instead of on a defect.
    """
    settings = yaml.safe_load(Path(config_path).read_text())
    dataset = json.loads(
        (REAL_WORKFLOW_DIR / settings["dataset"]).read_text(encoding="utf-8")
    )
    rows = dataset["rows"]
    if settings.get("rows"):
        rows = [row for row in rows if row["id"] in settings["rows"]]
    if settings.get("limit"):
        rows = rows[: settings["limit"]]
    return len(rows)


def _expected_estimate(config_path: str, *, stages: int = 1) -> str:
    """The dispatch-estimate line a SINGLE-STAGE run of this config should produce.

    Only models one stage: a chained run drops the negative row after the root,
    so the per-stage counts differ and are not worth reproducing here — the plan
    itself is the thing under test elsewhere.
    """
    settings = yaml.safe_load(Path(config_path).read_text())
    rows = _row_count(config_path) * stages
    judge_calls = 0 if (settings.get("options") or {}).get("no_judge") else rows
    total = rows + judge_calls
    return (
        f"{rows} AI calls to do the work + {judge_calls} to grade it "
        f"= {total} AI call{'' if total == 1 else 's'} in total"
    )
CALIBRATION_CONFIG = str(CONFIGS_DIR / "partial.yaml")
FULL_CONFIG = str(CONFIGS_DIR / "full.yaml")
SPECIFY = "prototype-specify"

GOOD_SPEC = """<spec>
# Prototype Specification

| Page | Route | Purpose |
| Dashboard | `#/dashboard` | overview |
| Invoices | `#/invoices` | invoice history |
| Accounts | `#/accounts` | account list |
| Settings | `#/settings` | preferences |

### Dashboard (`#/dashboard`)
Monthly recurring revenue of $48,210 across 312 active subscriptions.

### Invoices (`#/invoices`)
Invoice INV-20418 for Northwind Traders, $1,240.00, paid 2026-03-04.

### Accounts (`#/accounts`)
Northwind Traders on the Scale plan since 2024-11-02.

### Settings (`#/settings`)
Dunning retry schedule and notification recipients.
</spec>
"""


@pytest.fixture
def workflow_dir(tmp_path, monkeypatch):
    """The real workflow folder copied into tmp_path, so runs never touch the repo."""
    copy = tmp_path / "prototype"
    shutil.copytree(
        REAL_WORKFLOW_DIR,
        copy,
        ignore=shutil.ignore_patterns("__pycache__", "example-run", ".runs"),
    )
    loaded = config.load_workflow("prototype")
    monkeypatch.setattr(
        config, "load_workflow", lambda workflow: {**loaded, "workflow_dir": str(copy)}
    )
    return copy


@pytest.fixture
def any_agent_rubric(workflow_dir, monkeypatch):
    """Serve the real prototype-specify rubric for every stage.

    Only prototype-specify has a rubric today, so exercising a second stage —
    which is what proves subset selection and the missing-upstream error — needs
    one to stand in.
    """
    rubric = config.load_rubric(workflow_dir, SPECIFY)
    monkeypatch.setattr(config, "load_rubric", lambda directory, agent_id: rubric)
    return rubric


@pytest.fixture
def credentials(monkeypatch):
    """A provider credential in the environment, so the coarse gate passes."""
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key-not-real")


@pytest.fixture
def dispatches(monkeypatch):
    """Record every agent dispatch and reply with a good spec."""
    recorded = []

    async def fake_run_row(row, *, agent_id, sandbox_run_id, log_path, provider=None, model=None):
        recorded.append({"row_id": row.row_id, "agent_id": agent_id})
        return dispatch.DispatchResult(
            row_id=row.row_id,
            agent_id=agent_id,
            response=GOOD_SPEC,
            system_prompt=f"composed system prompt for {agent_id}",
            errored=False,
            error_reason=None,
            tokens_in=10,
            tokens_out=20,
            resolved_model_id="fake-model",
            log_path=str(log_path),
            sandbox_run_id=sandbox_run_id,
        )

    monkeypatch.setattr(dispatch, "run_row", fake_run_row)
    return recorded


@pytest.fixture
def judge_calls(monkeypatch):
    """Record every judge resolution; the judge itself never runs."""
    recorded = []

    def fake_resolve(judge_config):
        recorded.append(dict(judge_config))
        return object()

    monkeypatch.setattr(judge, "resolve_judge_model", fake_resolve)
    return recorded


@pytest.fixture
def failing_judge(monkeypatch):
    """A judge that cannot be resolved — the live misconfiguration, offline."""

    def fake_resolve(judge_config):
        raise judge.JudgeConfigurationError(
            f"judge provider {judge_config.get('provider')!r} is pinned but "
            "ANTHROPIC_API_KEY is not set."
        )

    monkeypatch.setattr(judge, "resolve_judge_model", fake_resolve)


@pytest.fixture
def workflow_calls(monkeypatch):
    """Record every run_workflow call, so a dispatching run is visible as such."""
    recorded = []
    real = model_grader.run_workflow

    async def recording(run_config, *, dry_run=False, replace=False):
        recorded.append({"run_config": run_config, "dry_run": dry_run, "replace": replace})
        return await real(run_config, dry_run=dry_run, replace=replace)

    monkeypatch.setattr(model_grader, "run_workflow", recording)
    return recorded


def stub_workflow(monkeypatch, result):
    """Replace run_workflow entirely: a real dry-run plan, then a canned result."""
    recorded = []
    real = model_grader.run_workflow

    async def stubbed(run_config, *, dry_run=False, replace=False, on_event=None):
        recorded.append({"run_config": run_config, "dry_run": dry_run, "replace": replace})
        if dry_run:
            return await real(run_config, dry_run=True)
        return result

    monkeypatch.setattr(model_grader, "run_workflow", stubbed)
    return recorded


def make_result(verdict: str) -> dict:
    """A finished run whose single stage came back with the given baseline verdict."""
    return {
        "dataset_run_id": "260729-000000-ten-industries",
        "run_dir": "/tmp/does-not-matter",
        "summary": {
            "status": "completed",
            "stages": [
                {
                    "agent_id": SPECIFY,
                    "status": "completed",
                    "precheck_pass_rate": 0.9,
                    "average_all": 74.0,
                    "average_precheck_passed": 80.0,
                    "stddev": 3.0,
                    "baseline_verdict": verdict,
                    "warnings": [],
                }
            ],
        },
    }


# ── dry run and blast radius ──────────────────────────────────────────────


def test_dry_run_prints_the_plan_and_dispatches_nothing(workflow_dir, dispatches, capsys):
    """--dry-run states the blast radius and makes zero model calls."""
    code = grade_runner.main(["--config", SMOKE_CONFIG, "model", "--dry-run"])
    output = capsys.readouterr().out

    assert code == grade_runner.EXIT_OK
    assert dispatches == []
    assert "AI call" in output, "the plan states what it would spend"
    assert "nothing ran and nothing was spent" in output
    assert SPECIFY in output


def test_dry_run_leaves_no_run_folder_behind(workflow_dir, dispatches):
    """A dry run that extends nothing mints nothing."""
    grade_runner.main(["--config", SMOKE_CONFIG, "model", "--dry-run"])
    assert not (workflow_dir / artifacts.RUNS_DIR_NAME).exists()


def test_the_bare_config_form_accepts_dry_run(workflow_dir, dispatches, capsys):
    """`--config <path> --dry-run` — the documented short form — must be previewable."""
    code = grade_runner.main(["--config", SMOKE_CONFIG, "--dry-run"])
    output = capsys.readouterr().out

    assert code == grade_runner.EXIT_OK
    assert dispatches == []
    assert "AI call" in output, "the plan states what it would spend"
    assert "nothing ran and nothing was spent" in output


def test_the_bare_config_form_prints_the_plan_before_dispatching(
    workflow_dir, credentials, monkeypatch, capsys
):
    """The blast radius is stated first, on every path — not only under `model`."""
    events = []
    real_print = grade_runner.print_plan_header

    def recording_print(plan):
        events.append("plan")
        real_print(plan)

    async def recording_dispatch(row, *, agent_id, sandbox_run_id, log_path, provider=None, model=None):
        events.append("dispatch")
        return dispatch.DispatchResult(
            row_id=row.row_id, agent_id=agent_id, response=GOOD_SPEC,
            system_prompt="composed", errored=False, error_reason=None,
            tokens_in=1, tokens_out=1, resolved_model_id="fake",
            log_path=str(log_path), sandbox_run_id=sandbox_run_id,
        )

    monkeypatch.setattr(grade_runner, "print_plan_header", recording_print)
    monkeypatch.setattr(dispatch, "run_row", recording_dispatch)

    code = grade_runner.main(["--config", SMOKE_CONFIG])

    assert code == grade_runner.EXIT_OK
    assert events[0] == "plan"
    assert events.count("dispatch") >= 1, "the plan printed and then it really ran"


def test_the_bare_config_form_runs_the_judge_preflight(
    workflow_dir, failing_judge, dispatches, capsys
):
    """The short form is exactly as protected as the subcommand form."""
    code = grade_runner.main(["--config", CALIBRATION_CONFIG])

    assert code == grade_runner.EXIT_JUDGE_PREFLIGHT
    assert dispatches == []
    assert "judge preflight FAILED" in capsys.readouterr().err


def test_both_invocation_forms_plan_identically(workflow_dir, dispatches, capsys):
    """One config, two spellings, one plan — otherwise a preview proves nothing."""
    grade_runner.main(["--config", SMOKE_CONFIG, "--dry-run"])
    bare = _plan_lines(capsys.readouterr().out)

    grade_runner.main(["model", "--config", SMOKE_CONFIG, "--dry-run"])
    subcommand = _plan_lines(capsys.readouterr().out)

    assert bare == subcommand


def _plan_lines(output: str) -> list[str]:
    """The plan's lines minus any minted run id, which is a fresh timestamp.

    Matched by SHAPE, not by label: keying on the old `dataset_run_id` prefix
    meant a renamed label silently stopped filtering, and the test then failed
    only when two invocations straddled a second boundary.
    """
    return [
        line for line in output.splitlines() if not re.search(r"\d{6}-\d{6}-", line)
    ]


def test_all_shipped_configs_parse_through_the_cli(workflow_dir, any_agent_rubric, dispatches):
    """Every committed run config loads and plans without a model call."""
    for path in (SMOKE_CONFIG, CALIBRATION_CONFIG, FULL_CONFIG):
        assert grade_runner.main(["model", "--config", path, "--dry-run"]) == grade_runner.EXIT_OK
    assert dispatches == []


# ── the judge preflight ───────────────────────────────────────────────────


def test_judge_preflight_failure_dispatches_nothing(
    workflow_dir, failing_judge, dispatches, workflow_calls, capsys
):
    """THE headline: an unresolvable judge stops the run before it spends anything."""
    code = grade_runner.main(["--config", CALIBRATION_CONFIG, "model"])
    error = capsys.readouterr().err

    assert code == grade_runner.EXIT_JUDGE_PREFLIGHT
    assert dispatches == []
    assert [call["dry_run"] for call in workflow_calls] == [True]
    assert "judge preflight FAILED" in error
    # Names whichever provider the config actually pins, not a hardcoded one —
    # the message is useless if it does not say what was asked for.
    pinned = yaml.safe_load(pathlib.Path(CALIBRATION_CONFIG).read_text())["judge"]["provider"]
    assert f"'{pinned}'" in error
    assert "configured here" in error


def test_the_plan_reports_the_overridden_judge_not_the_rubric_pin(workflow_dir, capsys):
    """The plan the preflight reads shows the judge the RUN would really use."""
    grade_runner.main(
        [
            "--config",
            CALIBRATION_CONFIG,
            "model",
            "--judge-provider",
            "mistral",
            "--judge-model",
            "mistral-large-latest",
            "--dry-run",
        ]
    )
    plan_output = capsys.readouterr().out

    assert "mistral/mistral-large-latest" in plan_output


def test_preflight_asserts_the_overridden_provider(
    workflow_dir, judge_calls, credentials, monkeypatch
):
    """An override reaches resolve_judge_model — the rubric pin never does."""
    recorded = stub_workflow(monkeypatch, make_result("PASS"))
    code = grade_runner.main(
        [
            "--config",
            CALIBRATION_CONFIG,
            "model",
            "--judge-provider",
            "mistral",
            "--judge-model",
            "mistral-large-latest",
        ]
    )

    assert code == grade_runner.EXIT_OK
    assert [call["dry_run"] for call in recorded] == [True, False]
    assert judge_calls and judge_calls[0]["provider"] == "mistral"
    assert judge_calls[0]["model"] == "mistral-large-latest"


def test_no_judge_skips_the_preflight_and_still_runs(
    workflow_dir, failing_judge, credentials, dispatches, capsys
):
    """--no-judge grades on precheck alone, so an unresolvable judge is irrelevant."""
    code = grade_runner.main(["--config", SMOKE_CONFIG, "model"])
    output = capsys.readouterr().out

    assert code == grade_runner.EXIT_OK
    assert len(dispatches) >= 1
    assert "Full details" in output


# ── flags, overrides and the two model axes ───────────────────────────────


def test_cli_flags_override_the_config_and_are_reported(workflow_dir, dispatches, capsys):
    """A flag that diverges from the config is applied AND stated."""
    grade_runner.main(["--config", SMOKE_CONFIG, "model", "--limit", "1", "--dry-run"])
    output = capsys.readouterr().out

    assert "overrides" in output
    assert "limit: None -> 1" in output
    assert "1 brief" in output


def test_provider_and_judge_provider_land_on_different_axes(workflow_dir, monkeypatch):
    """--provider is the agent under test; --judge-provider is the grader. No crossover."""
    recorded = stub_workflow(monkeypatch, make_result("PASS"))
    grade_runner.main(
        [
            "--config",
            SMOKE_CONFIG,
            "model",
            "--provider",
            "mistral",
            "--model",
            "agent-model",
            "--judge-provider",
            "mistral",
            "--judge-model",
            "judge-model",
            "--judge-threshold",
            "70",
            "--dry-run",
        ]
    )

    run_config = recorded[0]["run_config"]
    assert run_config.agent_under_test == {"provider": "mistral", "model": "agent-model"}
    assert run_config.judge == {"provider": "mistral", "model": "judge-model", "threshold": 70.0}


def test_agents_all_and_an_explicit_subset(workflow_dir, any_agent_rubric, dispatches, capsys):
    """`all` takes the implemented prefix; a list takes exactly what it names."""
    grade_runner.main(["model", "prototype", "--agents", "all", "--dry-run"])
    all_output = capsys.readouterr().out

    grade_runner.main(
        [
            "model",
            "prototype",
            "--agents",
            f"{SPECIFY},prototype-plan",
            "--rows",
            "billing_console",
            "--dry-run",
        ]
    )
    subset_output = capsys.readouterr().out

    assert "prototype-plan" in all_output
    assert "prototype-plan" in subset_output
    assert "AI calls in total" in subset_output
    assert dispatches == []


def test_rows_and_limit_subset_the_dataset(workflow_dir, capsys):
    """--rows names rows; --limit truncates them."""
    grade_runner.main(
        ["model", "prototype", "--rows", "billing_console,hr_ats", "--dry-run"]
    )
    assert "2 briefs" in capsys.readouterr().out

    grade_runner.main(["model", "prototype", "--limit", "3", "--dry-run"])
    assert "3 briefs" in capsys.readouterr().out


def test_non_root_agent_without_from_run_is_a_usage_error(
    workflow_dir, any_agent_rubric, dispatches, capsys
):
    """A stage whose upstream never ran fails naming from_run — it never falls back."""
    code = grade_runner.main(["model", "prototype", "--agents", "prototype-plan", "--dry-run"])
    error = capsys.readouterr().err

    assert code == grade_runner.EXIT_USAGE
    assert "from_run" in error
    assert dispatches == []


def test_replace_reaches_run_workflow_as_a_keyword(workflow_dir, credentials, monkeypatch):
    """--replace is a run_workflow keyword, not a run-config option."""
    recorded = stub_workflow(monkeypatch, make_result("PASS"))
    code = grade_runner.main(["--config", SMOKE_CONFIG, "model", "--replace"])

    assert code == grade_runner.EXIT_OK
    assert recorded[-1]["replace"] is True
    assert recorded[-1]["dry_run"] is False


# ── exit codes ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "verdict,expected",
    [("PASS", grade_runner.EXIT_OK), ("FAIL", grade_runner.EXIT_BASELINE_FAIL)],
)
def test_baseline_verdict_sets_the_exit_code(
    workflow_dir, credentials, monkeypatch, verdict, expected
):
    """A stage that failed its committed baseline exits non-zero."""
    stub_workflow(monkeypatch, make_result(verdict))
    code = grade_runner.main(["--config", SMOKE_CONFIG, "model"])

    assert code == expected


def test_a_run_that_did_not_complete_exits_non_zero(workflow_dir, credentials, monkeypatch, capsys):
    """An aborted run is a failure — CI must never read it as a success."""
    aborted = make_result("PASS")
    aborted["summary"]["status"] = "aborted"
    stub_workflow(monkeypatch, aborted)

    code = grade_runner.main(["--config", SMOKE_CONFIG])

    assert code == grade_runner.EXIT_RUN_FAILED
    assert "status aborted" in capsys.readouterr().err


def test_a_bad_config_path_is_a_usage_error(workflow_dir, capsys):
    """A config that does not exist is a usage error, distinct from a run failure."""
    code = grade_runner.main(["--config", "/nowhere/missing.yaml", "model", "--dry-run"])

    assert code == grade_runner.EXIT_USAGE
    assert "does not exist" in capsys.readouterr().err


def test_no_arguments_prints_help(capsys):
    """A bare invocation explains itself rather than starting a live run."""
    code = grade_runner.main([])

    assert code == grade_runner.EXIT_USAGE
    assert "model" in capsys.readouterr().out


# ── report and compare, over synthetic run folders ────────────────────────


def write_run_folder(workflow_dir, dataset_run_id, *, score, runs=None, grades=None):
    """Write a minimal run folder — the shape report and compare read back."""
    run_dir = artifacts.run_folder(dataset_run_id, workflow_dir=workflow_dir)
    artifacts.write_stage(
        run_dir,
        "prototype_specify",
        runs=runs or [],
        grades=grades or [],
        score=score,
        output={"rows": []},
    )
    return run_dir


def make_score(dataset_run_id, *, average, config_hash="sha256:config-a", finished_at="2026-07-29T10:00:00Z"):
    """A score.json payload with one dimension and one clustered weakness."""
    return {
        "dataset_run_id": dataset_run_id,
        "agent_id": SPECIFY,
        "agent_token": "prototype_specify",
        "finished_at": finished_at,
        "counts": {"total": 2},
        "precheck_pass_rate": 1.0,
        "scores": {
            "average_all": average,
            "average_precheck_passed": average,
            "average_clean_chain": average,
            "stddev": 2.0,
            "distinct_score_count": 2,
        },
        "dimensions": {
            "data_realism": {"count": 2, "mean": average - 10, "median": average - 10,
                             "stddev": 1.0, "min": average - 12, "max": average - 8}
        },
        "recurring_weaknesses": [
            {"row_ids": ["billing_console", "hr_ats"], "evidence": "round-number invented data"}
        ],
        "hashes": {"config_hash": config_hash, "rubric_hash": "sha256:rubric"},
        "baseline": {"verdict": "PASS", "failures": []},
        "results": [
            {"row_id": "billing_console", "score": average + 5, "precheck_passed": True, "passed": True},
            {"row_id": "hr_ats", "score": average - 5, "precheck_passed": True, "passed": True},
        ],
    }


def make_runs(prompt_hash="sha256:prompt-a"):
    """Run entries carrying the composed-prompt hash compare groups on."""
    return [
        {"row_id": "billing_console", "system_prompt_hash": prompt_hash},
        {"row_id": "hr_ats", "system_prompt_hash": prompt_hash},
    ]


def test_report_prints_dimensions_and_recurring_weaknesses(workflow_dir, capsys):
    """report reads one run back: per-dimension aggregates plus the weakness clusters."""
    write_run_folder(workflow_dir, "run-a", score=make_score("run-a", average=74.0))

    code = grade_runner.main(["report", "run-a"])
    output = capsys.readouterr().out

    assert code == grade_runner.EXIT_OK
    assert "data_realism" in output
    assert "round-number invented data" in output
    assert "baseline   PASS" in output


def test_report_worst_prints_the_lowest_rows_with_the_judge_rationale(workflow_dir, capsys):
    """--worst N is the drill-down from an aggregate to a specific weak response."""
    grades = [
        {
            "row_id": "hr_ats",
            "rationale": "invented every figure",
            "weaknesses": ["round numbers throughout"],
            "evidence": {"data_realism": "revenue of $100,000"},
        }
    ]
    write_run_folder(
        workflow_dir, "run-a", score=make_score("run-a", average=74.0), grades=grades
    )

    grade_runner.main(["report", "run-a", "--worst", "1"])
    output = capsys.readouterr().out

    assert "worst 1 rows" in output
    assert "invented every figure" in output
    assert "revenue of $100,000" in output


def test_report_on_a_missing_run_folder_is_a_usage_error(workflow_dir, capsys):
    """Reading a run that does not exist never mints an empty folder for it."""
    code = grade_runner.main(["report", "no-such-run"])

    assert code == grade_runner.EXIT_USAGE
    assert not (workflow_dir / artifacts.RUNS_DIR_NAME / "no-such-run").exists()


def test_compare_never_calls_a_within_noise_delta_an_improvement(workflow_dir, capsys):
    """The printing layer prints the guard's verdict; it never decides for itself."""
    write_run_folder(
        workflow_dir,
        "run-a",
        score=make_score("run-a", average=74.0, finished_at="2026-07-29T10:00:00Z"),
        runs=make_runs(),
    )
    write_run_folder(
        workflow_dir,
        "run-b",
        score=make_score("run-b", average=74.5, finished_at="2026-07-29T11:00:00Z"),
        runs=make_runs(),
    )

    code = grade_runner.main(["compare", "run-a", "run-b"])
    output = capsys.readouterr().out

    assert code == grade_runner.EXIT_OK
    assert "within-noise" in output
    assert "improved" not in output


def test_compare_reports_row_and_dimension_deltas(workflow_dir, capsys):
    """A delta with no observed variance is unknown-variance, never an improvement."""
    write_run_folder(
        workflow_dir,
        "run-a",
        score=make_score("run-a", average=60.0, config_hash="sha256:config-a"),
        runs=make_runs("sha256:prompt-a"),
    )
    write_run_folder(
        workflow_dir,
        "run-b",
        score=make_score("run-b", average=90.0, config_hash="sha256:config-b"),
        runs=make_runs("sha256:prompt-b"),
    )

    grade_runner.main(["compare", "run-a", "run-b"])
    output = capsys.readouterr().out

    assert "unknown-variance" in output
    assert "data_realism" in output
    assert "improved" not in output


def test_compare_by_prompt_groups_every_run_of_one_agent(workflow_dir, capsys):
    """--by-prompt reads a series of edits as a trend rather than a pile of runs."""
    write_run_folder(
        workflow_dir,
        "run-a",
        score=make_score("run-a", average=74.0, finished_at="2026-07-29T10:00:00Z"),
        runs=make_runs("sha256:prompt-a"),
    )
    write_run_folder(
        workflow_dir,
        "run-b",
        score=make_score("run-b", average=80.0, finished_at="2026-07-29T11:00:00Z"),
        runs=make_runs("sha256:prompt-b"),
    )

    code = grade_runner.main(["compare", "--by-prompt", "prototype", SPECIFY])
    output = capsys.readouterr().out

    assert code == grade_runner.EXIT_OK
    assert "sha256:prompt-a" in output
    assert "sha256:prompt-b" in output
    assert "2 runs" in output


def test_the_repo_workflow_folder_holds_no_run_folder(workflow_dir, dispatches, credentials):
    """Nothing this suite does may leave a .runs folder in the repository.

    Asserts no NEW run folder appeared, rather than that `.runs/` is absent — a
    developer's own real runs live there legitimately, and asserting absence
    would turn the suite red the first time someone actually used the tool.
    """
    runs_root = REAL_WORKFLOW_DIR / artifacts.RUNS_DIR_NAME
    before = set(runs_root.iterdir()) if runs_root.exists() else set()

    grade_runner.main(["--config", SMOKE_CONFIG, "model", "--dry-run"])

    after = set(runs_root.iterdir()) if runs_root.exists() else set()
    assert after == before, f"the suite created run folder(s): {sorted(p.name for p in after - before)}"


# ── a dead judge must be visible and must not exit 0 ──────────────────────
#
# Regression from run 260729-173145: the judge failed on every row, the run
# printed "completed, no judge", and the process exited 0.


def _stage(agent_id="prototype-specify", *, judged=0, judge_errored=0, rows=2) -> dict:
    """One entry of run_workflow's `stages` list, carrying only the counts."""
    return {
        "agent_id": agent_id,
        "score": {"counts": {"rows": rows, "judged": judged, "judge_errored": judge_errored}},
    }


def test_stage_with_dead_judge_names_the_stage():
    result = {"stages": [_stage(judge_errored=2)]}

    assert grade_runner._stage_with_dead_judge(result) == "prototype-specify"


def test_no_judge_configured_is_not_a_dead_judge():
    result = {"stages": [_stage(judged=0, judge_errored=0)]}

    assert grade_runner._stage_with_dead_judge(result) is None


def test_partially_failing_judge_is_not_a_dead_judge():
    """Some rows scored — the aggregates mean something, so the run still passes."""
    result = {"stages": [_stage(judged=1, judge_errored=1)]}

    assert grade_runner._stage_with_dead_judge(result) is None


def test_row_line_reports_a_failed_judge_instead_of_a_clean_pass():
    line = grade_runner._row_line(
        {
            "index": 1, "total": 3, "row_id": "billing_console",
            "precheck_passed": True,
            "score": None,
            "judge_errored": True,
            "judge_error_reason": "3 validation errors for JudgeOutput\nrationale\n  missing",
            "agent_tokens": 8055,
            "judge_tokens": 4200,
        }
    )

    assert "✖" in line
    assert "JUDGE FAILED" in line
    assert "3 validation errors" in line
    assert "\n" not in line, "one row is one line, whatever the exception looked like"


def _result(*, judged, judge_errored, warnings=(), report="/runs/x/REPORT.md") -> dict:
    """A run_workflow result carrying one finished stage."""
    counts = {"rows": 2, "judged": judged, "judge_errored": judge_errored}
    score = {
        "counts": counts,
        "tokens": {"agent": {"total": 20689}, "judge": {"total": 14078}},
    }
    return {
        "run_dir": "/runs/x",
        "report_path": report,
        "summary": {
            "status": "completed",
            "stages": [
                {
                    "agent_id": "prototype-specify",
                    "status": "completed",
                    "precheck_pass_rate": 1.0,
                    "average_all": 89.0,
                    "stddev": 1.0,
                    "distinct_score_count": 2,
                    "baseline_verdict": "REFUSED",
                    "warnings": list(warnings),
                }
            ],
        },
        "stages": [{"agent_id": "prototype-specify", "score": score}],
    }


def test_results_block_surfaces_a_judge_failure_warning(capsys):
    """A dead judge must never be silent just because the summary got shorter."""
    grade_runner.print_run_result(
        _result(judged=0, judge_errored=2, warnings=["JUDGE FAILED: 2 row(s) (a, b) ..."])
    )

    printed = capsys.readouterr().out
    assert "JUDGE FAILED" in printed
    assert "⚠" in printed


def test_results_block_reports_total_spend_split_by_who_paid(capsys):
    grade_runner.print_run_result(_result(judged=2, judge_errored=0))

    printed = capsys.readouterr().out
    assert "34.8k tokens" in printed
    assert "20.7k doing the work" in printed
    assert "14.1k grading it" in printed


def test_results_block_ends_by_naming_the_report(capsys):
    """The detail moved to REPORT.md, so the run has to say where that is."""
    grade_runner.print_run_result(_result(judged=2, judge_errored=0))

    printed = capsys.readouterr().out
    assert "Full details" in printed
    assert printed.rstrip().endswith("/runs/x/REPORT.md")


def test_results_block_does_not_print_the_full_stage_report(capsys):
    """Dimensions and weaknesses belong in the file, not in the terminal."""
    grade_runner.print_run_result(_result(judged=2, judge_errored=0))

    printed = capsys.readouterr().out
    assert "recurring weaknesses" not in printed
    assert "dimension" not in printed
    assert len(printed.splitlines()) < 24, "the closing summary stays scannable"


def test_runs_root_resolves_to_the_grading_root_not_the_workflow_folder(tmp_path):
    """`report`/`compare`/`code` read through here; a private copy of this path
    silently stopped finding runs when `.runs/` moved to the grading root."""
    grading_root = tmp_path / "grading"
    (grading_root / "configs").mkdir(parents=True)
    (grading_root / "model").mkdir()
    workflow_dir = grading_root / "model" / "workflows" / "prototype"
    workflow_dir.mkdir(parents=True)

    root = grade_runner._runs_root({"workflow_dir": str(workflow_dir)})

    assert root == grading_root / ".runs" / "prototype"
    assert root == artifacts.runs_root(workflow_dir), "must not diverge from artifacts"


def test_report_still_succeeds_when_the_markdown_cannot_be_rendered(workflow_dir, capsys):
    """The printed report is the deliverable; REPORT.md is only a convenience.

    A run folder with no run_summary.json cannot render — `report` must still
    print its aggregates and exit 0 rather than dying on the extra file.
    """
    write_run_folder(workflow_dir, "run-a", score=make_score("run-a", average=74.0))

    code = grade_runner.main(["report", "run-a"])

    captured = capsys.readouterr()
    assert code == grade_runner.EXIT_OK
    assert "data_realism" in captured.out, "the real report still printed"
    assert "markdown        not written" in captured.err


def test_report_writes_the_markdown_beside_the_artifacts(workflow_dir, capsys):
    write_run_folder(workflow_dir, "run-a", score=make_score("run-a", average=74.0))
    run_dir = grade_runner._runs_root({"workflow_dir": str(workflow_dir)}) / "run-a"
    (run_dir / "run_summary.json").write_text(
        json.dumps(
            {
                "dataset_run_id": "run-a",
                "status": "completed",
                "stages": [{"agent_id": "prototype-specify", "status": "completed"}],
            }
        ),
        encoding="utf-8",
    )

    code = grade_runner.main(["report", "run-a"])

    assert code == grade_runner.EXIT_OK
    assert (run_dir / "REPORT.md").exists()
    assert "markdown        not written" not in capsys.readouterr().err


def test_the_estimate_line_stays_greppable_for_grade_sh_check(workflow_dir, capsys):
    """`grade.sh check` greps this line out of every config's dry run.

    It is a text contract between two files, so a wording change here shows up
    as every config reporting FAILED rather than as a test failure.
    """
    grade_runner.main(["--config", SMOKE_CONFIG, "--dry-run"])
    output = capsys.readouterr().out

    pattern = (GRADING_DIR / "grade.sh").read_text().split("| grep '")[1].split("'")[0]
    assert pattern in output, (
        f"grade.sh check greps for {pattern!r}, which the plan no longer prints"
    )


def test_results_table_is_one_line_per_stage(capsys):
    """A 5-stage workflow has to stay scannable — one row each, aligned."""
    result = _result(judged=2, judge_errored=0)
    result["summary"]["stages"].append(
        {
            "agent_id": "prototype-plan", "status": "completed",
            "precheck_pass_rate": 0.92, "average_all": 74.0, "stddev": 8.25,
            "distinct_score_count": 7, "baseline_verdict": "PASS", "warnings": [],
        }
    )
    result["stages"].append(
        {"agent_id": "prototype-plan", "score": {"counts": {"rows": 12, "judged": 12}}}
    )

    grade_runner.print_run_result(result)

    lines = capsys.readouterr().out.splitlines()
    specify = next(line for line in lines if "prototype-specify" in line)
    plan = next(line for line in lines if "prototype-plan" in line)
    assert specify.rstrip().endswith("REFUSED")
    assert plan.rstrip().endswith("PASS")
    header = next(line for line in lines if "spread" in line and "verdict" in line)
    assert header.index("verdict") > header.index("spread"), "columns keep their order"


def test_results_table_shows_scores_without_false_precision(capsys):
    """`85.5` and `74`, never `85.50` and `74.00`."""
    result = _result(judged=2, judge_errored=0)
    result["summary"]["stages"][0]["average_all"] = 85.5
    result["summary"]["stages"][0]["stddev"] = 3.5

    grade_runner.print_run_result(result)

    line = next(
        row for row in capsys.readouterr().out.splitlines() if "prototype-specify" in row
    )
    assert "85.5" in line and "85.50" not in line
    assert "3.5" in line and "3.50" not in line


def test_a_single_row_run_is_described_in_the_singular(workflow_dir, capsys):
    """The plan, the estimate and the stage header all count the same rows."""
    # One stage, one row — the only shape whose counts are all singular.
    grade_runner.main([
        "--config", SMOKE_CONFIG, "--agents", "prototype-specify", "--limit", "1", "--dry-run",
    ])
    output = capsys.readouterr().out

    assert "1 brief" in output
    assert "= 1 AI call in total" in output
    assert "1 briefs" not in output


# ── the notes block is not the table ──────────────────────────────────────


def _plan_with(stages, not_run=()):
    """A dry-run plan payload carrying the given stages."""
    return {
        "run_id": "small", "workflow": "prototype", "dataset_id": "small",
        "row_count": 3, "dataset_run_id": "260729-191717-small",
        "stages": stages, "not_run": list(not_run),
        "dispatch_estimate": {"agent_calls": 11, "judge_calls": 10, "total": 21},
    }


def _stage_entry(agent_id, *, skipped=(), note=None):
    """One stage's plan entry. Skips here are by design — a negative-test row."""
    return {
        "agent_id": agent_id, "rows": 3, "dispatches": 2, "judge_calls": 2,
        "skipped": [{"row_id": r, "reason": why, "by_design": True} for r, why in skipped],
        "note": note,
        "model_under_test": {"provider": "mistral", "model": "m-small"},
        "judge": {"provider": "mistral", "model": "m-large"},
    }


def test_notes_are_separated_from_the_table_by_a_heading(capsys):
    """A note line starting with an agent id read as a second row for that stage."""
    grade_runner.print_plan_header(
        _plan_with([
            _stage_entry("prototype-specify"),
            _stage_entry("prototype-plan", note="something needs attention"),
        ])
    )

    lines = capsys.readouterr().out.splitlines()
    heading = lines.index("  notes")
    assert lines[heading - 1] == "", "a blank line separates the table from its notes"
    table_end = next(i for i, line in enumerate(lines) if "prototype-plan " in line)
    assert table_end < heading, "the table comes first"
    # Notes are indented deeper than table rows, so neither can be read as the other.
    assert lines[heading + 1].startswith("    ")


def test_a_negative_test_row_is_explained_once_in_plain_words(capsys):
    """Four steps withholding one row is ONE fact, and it is not a warning.

    It used to print four times under `notes`, which put the eval working as
    designed in the block reserved for things needing attention.
    """
    skip = [("underspecified_brief", "expect: fail row is not propagated")]
    grade_runner.print_plan_header(
        _plan_with([_stage_entry(name, skipped=skip) for name in ("a", "b", "c", "d")])
    )

    printed = capsys.readouterr().out
    assert printed.count("underspecified_brief") == 1
    assert "deliberately bad brief" in printed
    assert "notes" not in printed, "expected behaviour is not a note"


def test_a_long_note_wraps_instead_of_truncating(capsys):
    """The clause saying what to do about a note is routinely past column 80."""
    note = (
        "upstream could not be adapted: no parseable '## Task N:' headers — expected on "
        "synthetic upstream text; these rows ARE counted in the estimate because a real "
        "run composes them"
    )
    grade_runner.print_plan_header(_plan_with([_stage_entry("prototype-build", note=note)]))

    printed = capsys.readouterr().out
    assert "…" not in printed, "wrapped, never truncated"
    assert "because a real run composes them" in printed
    assert all(len(line) <= 90 for line in printed.splitlines())


def test_no_notes_heading_when_there_is_nothing_to_note(capsys):
    grade_runner.print_plan_header(_plan_with([_stage_entry("prototype-specify")]))

    assert "notes" not in capsys.readouterr().out
