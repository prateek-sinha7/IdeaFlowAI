"""Unit tests for evals.grading.model_grader — the workflow orchestrator.

Offline only: `dispatch.run_row` and `judge.grade` are monkeypatched, so no model
and no network are ever touched. The real workflow.yaml, rubric and dataset are
used, copied into tmp_path so every run folder is written there.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from evals.grading import artifacts, config
from evals.grading.model import dispatch, judge, model_grader

REAL_WORKFLOW_DIR = (
    Path(__file__).resolve().parents[2]
    / "evals"
    / "grading"
    / "model"
    / "workflows"
    / "prototype"
)
SPECIFY = "prototype-specify"
PLAN = "prototype-plan"

GOOD_SPEC = """<spec>
# Prototype Specification

| Page | Route | Purpose |
| Dashboard | `#/dashboard` | overview |
| Invoices | `#/invoices` | invoice history |
| Accounts | `#/accounts` | account list |
| Settings | `#/settings` | preferences |

### Dashboard (`#/dashboard`)
**Components**:
  - MRR summary: monthly recurring revenue of $48,210 across 312 active subscriptions.
**Interactions**:
  - nav link → navigates to `#/dashboard`

### Invoices (`#/invoices`)
**Components**:
  - Invoice table: INV-20418 for Northwind Traders, $1,240.00, paid 2026-03-04.
**Interactions**:
  - invoice row → navigates to `#/invoices`

### Accounts (`#/accounts`)
**Components**:
  - Account list: Northwind Traders on the Scale plan since 2024-11-02.
**Interactions**:
  - account row → navigates to `#/accounts`

### Settings (`#/settings`)
**Components**:
  - Dunning retry schedule and notification recipients form.
**Interactions**:
  - save button → shows the inline confirmation
</spec>
"""

BAD_SPEC = "Here is the spec you asked for, without any wrapper at all."

# Every stage is onboarded now, so a chained fake dispatch has to answer in the
# SHAPE each stage's downstream expects — prototype-build parses `## Task N:`
# headers out of the plan and raises on anything else. One generic response for
# all five stages stopped being a faithful stand-in the moment plan landed.
GOOD_TASKS = """<tasks>
## Task 1: HTML Shell & Navigation Chrome
Create prototype.html with :root tokens and a nav for all four pages.

## Task 2: Dashboard Page
Fill `#/dashboard` with the MRR summary and a six-point chart.

## Task 3: Invoices Page
Fill `#/invoices` with a five-row invoice table.

## Task 4: Final Wiring & Validation
Verify every nav link resolves and no section is empty.
</tasks>
"""

GOOD_ANALYSIS = """<analysis>
## Spec Kit Analysis Report

### Summary
The spec and task list agree on all four pages and are ready to build.

### Findings

| # | Category | Status | Detail |
|---|----------|--------|--------|
| 1 | Consistency | \u2705 Clear | All four spec pages map to Tasks 2-3 and the shell. |
| 2 | Coverage gaps | \u26a0\ufe0f Partial | Accounts and Settings share Task 3. |

### Issues requiring attention
Accounts and Settings are covered by one task; the build sub-agent sees both at once.

### Risk register
Task 3 \u2014 Invoices Page: the five-row table is the densest page in the plan.

### Suggested next actions
1. **Split Task 3** \u2014 give Accounts and Settings their own tasks.
2. **Confirm routes** \u2014 check every nav target resolves after the shell task.

### Readiness verdict
READY WITH CAUTION
The plan builds every page, but one task covers two of them.
</analysis>
"""

GOOD_HTML = """<!doctype html>
<html><head><style>:root{--bg:#fff;--fg:#111;}</style></head><body>
<nav><a href="#/dashboard">Dashboard</a><a href="#/invoices">Invoices</a>
<a href="#/accounts">Accounts</a><a href="#/settings">Settings</a></nav>
<section data-page="dashboard" class="is-active"><h1>Dashboard</h1><p>MRR $48,210 across 312 subscriptions.</p></section>
<section data-page="invoices"><h1>Invoices</h1><table><tr><td>INV-20418</td><td>$1,240.00</td></tr></table></section>
<section data-page="accounts"><h1>Accounts</h1><p>Northwind Traders, Scale plan.</p></section>
<section data-page="settings"><h1>Settings</h1><p>Dunning retry schedule.</p></section>
<script>function route(){}</script></body></html>
"""

# What each stage's fake dispatch answers with, keyed by agent id.
STAGE_RESPONSES = {
    "prototype-specify": GOOD_SPEC,
    "prototype-plan": GOOD_TASKS,
    "prototype-analyze": GOOD_ANALYSIS,
    "prototype-build": GOOD_HTML,
    "prototype-validate": GOOD_HTML,
}


def implemented_stages() -> list[str]:
    """Every `status: implemented` agent id, in workflow order — read, not hardcoded.

    Onboarding a stage is a config edit; a test that hardcodes the roster turns
    that edit into a red suite about something unrelated.
    """
    workflow = config.load_workflow("prototype")
    return [s["agent_id"] for s in workflow["stages"] if s["status"] == "implemented"]


def make_run_config(**overrides):
    """A RunConfig for the real prototype workflow and its committed dataset."""
    return config.load_run_config(
        None,
        {
            "workflow": "prototype",
            "dataset": "datasets/ten-industries.json",
            **overrides,
        },
    )


def make_result(row, agent_id, *, response=None, errored=False):
    """A DispatchResult standing in for one real agent dispatch."""
    if response is None:
        response = STAGE_RESPONSES.get(agent_id, GOOD_SPEC)
    return _make_result(row, agent_id, response=response, errored=errored)


def _make_result(row, agent_id, *, response, errored):
    """A DispatchResult standing in for one real agent dispatch."""
    return dispatch.DispatchResult(
        row_id=row.row_id,
        agent_id=agent_id,
        response="" if errored else response,
        system_prompt=f"composed system prompt for {agent_id}",
        errored=errored,
        error_reason="dispatch failed" if errored else None,
        tokens_in=10,
        tokens_out=20,
        resolved_model_id="fake-model",
        log_path=str(row.row_id),
        sandbox_run_id=f"sandbox-{row.row_id}",
    )


def make_verdict(rubric=None):
    """A JudgeVerdict scoring every dimension of whichever rubric it is given.

    Derived, not hardcoded: pinning specify's three dimension ids made every
    other stage's rows fail scoring and abort the chain, which read as "the
    workflow stops after stage 1" rather than as a broken test fake.
    """
    dimensions = (rubric or {}).get("dimensions") or [
        {"id": "data_realism"}, {"id": "brief_intent_match"}, {"id": "design_system_coherence"}
    ]
    return judge.JudgeVerdict(
        sub_scores={d["id"]: 80 for d in dimensions},
        evidence={"data_realism": "INV-20418"},
        rationale="plausible billing data",
        strengths=["specific invoice ids"],
        weaknesses=["round numbers in the dashboard"],
        resolved_model_id="fake-judge",
    )


@pytest.fixture
def workflow_dir(tmp_path, monkeypatch):
    """The real workflow folder copied into tmp_path, so runs write there."""
    copy = tmp_path / "prototype"
    shutil.copytree(
        REAL_WORKFLOW_DIR,
        copy,
        ignore=shutil.ignore_patterns("__pycache__", "example-run", ".runs"),
    )
    loaded = config.load_workflow("prototype")
    monkeypatch.setattr(config, "load_workflow", lambda workflow: {**loaded, "workflow_dir": str(copy)})
    return copy


@pytest.fixture
def any_agent_rubric(workflow_dir):
    """Each stage's OWN committed rubric — no stand-in.

    This used to serve prototype-specify's rubric for every stage, because only
    that stage had one. Every stage is onboarded now, so standing in would grade
    a plan against a spec's precheck and hide exactly the mismatches these tests
    exist to catch.
    """
    return config.load_rubric(workflow_dir, SPECIFY)


@pytest.fixture
def dispatches(monkeypatch):
    """Record every dispatch and reply with a good spec; tests can retune it."""
    recorded = []

    async def fake_run_row(row, *, agent_id, sandbox_run_id, log_path, provider=None, model=None):
        recorded.append({"row_id": row.row_id, "agent_id": agent_id, "prompt": row.prompt})
        return make_result(row, agent_id)

    monkeypatch.setattr(dispatch, "run_row", fake_run_row)
    return recorded


@pytest.fixture
def judgements(monkeypatch):
    """Record every judge call and reply with a full set of sub-scores."""
    recorded = []

    async def fake_grade(response, *, rubric, system_prompt, prompt, precheck_reason):
        recorded.append({"response": response, "precheck_reason": precheck_reason})
        return make_verdict(rubric)

    monkeypatch.setattr(judge, "grade", fake_grade)
    return recorded


def run_folders(workflow_dir: Path) -> list[Path]:
    """Every run folder that exists under the workflow copy."""
    return sorted(path for path in (workflow_dir / ".runs").glob("*") if path.is_dir())


def test_full_workflow_writes_one_run_folder_with_every_artifact(
    workflow_dir, any_agent_rubric, dispatches, judgements
):
    """A full workflow run lands in ONE folder with all four artifacts plus the prompt."""
    result = asyncio.run(model_grader.run_workflow(make_run_config(rows=["billing_console"])))

    folders = run_folders(workflow_dir)
    assert len(folders) == 1
    run_dir = folders[0]
    assert run_dir.name == result["dataset_run_id"]
    for kind in ("run", "grade", "score", "output"):
        assert artifacts.read_stage_artifact(run_dir, "prototype_specify", kind) is not None
    assert artifacts.read_system_prompt(run_dir, "prototype_specify").startswith("composed")
    assert artifacts.read_resolved_config(run_dir)["workflow"] == "prototype"
    # One dispatch and one judge call PER IMPLEMENTED STAGE — derived, so
    # onboarding a stage does not fail a test about run-folder layout.
    assert len(dispatches) == len(implemented_stages())
    assert len(judgements) == len(implemented_stages())


def test_agents_all_runs_every_implemented_stage_in_workflow_order(
    workflow_dir, any_agent_rubric, dispatches, judgements
):
    """`all` runs the implemented PREFIX, in the order workflow.yaml declares."""
    result = asyncio.run(model_grader.run_workflow(make_run_config(rows=["billing_console"])))

    summary = result["summary"]
    ran = [stage["agent_id"] for stage in summary["stages"] if stage["status"] == "completed"]
    assert ran == implemented_stages()
    assert summary["not_run"] == []
    assert [call["agent_id"] for call in dispatches] == implemented_stages()


def test_agents_all_stops_at_the_first_unimplemented_stage(
    workflow_dir, any_agent_rubric, dispatches, judgements, monkeypatch
):
    """`all` takes the implemented PREFIX — it never skips a gap and runs past it.

    Exercised against a doctored workflow rather than the real one: every real
    stage is now onboarded, and the rule still has to hold for the next
    workflow that is only half-built.
    """
    real_load = config.load_workflow
    every_stage = implemented_stages()  # captured BEFORE the workflow is doctored

    def half_built(name):
        workflow = real_load(name)
        for stage in workflow["stages"][2:]:
            stage["status"] = "not_yet_onboarded"
        return workflow

    monkeypatch.setattr(config, "load_workflow", half_built)
    result = asyncio.run(model_grader.run_workflow(make_run_config(rows=["billing_console"])))

    summary = result["summary"]
    ran = [stage["agent_id"] for stage in summary["stages"] if stage["status"] == "completed"]
    assert ran == every_stage[:2]
    assert summary["not_run"] == every_stage[2:]


def test_explicit_agent_list_runs_in_workflow_order_when_listed_reversed(
    workflow_dir, any_agent_rubric, dispatches, judgements
):
    """A reversed `agents:` list still runs in the order workflow.yaml declares."""
    asyncio.run(
        model_grader.run_workflow(
            make_run_config(agents=[PLAN, SPECIFY], rows=["billing_console"])
        )
    )

    assert [call["agent_id"] for call in dispatches] == [SPECIFY, PLAN]


def test_non_root_agent_without_from_run_fails_naming_the_missing_artifact(
    workflow_dir, any_agent_rubric, dispatches
):
    """Running a downstream stage alone must name what is missing, not read the dataset."""
    with pytest.raises(ValueError) as error:
        asyncio.run(
            model_grader.run_workflow(make_run_config(agents=[PLAN], rows=["billing_console"]))
        )

    message = str(error.value)
    assert "prototype_specify_output.json" in message
    assert "from_run" in message
    assert dispatches == []


def test_from_run_extends_the_existing_folder(
    workflow_dir, any_agent_rubric, dispatches, judgements
):
    """`from_run` writes the second stage into the first run's folder, not a new one."""
    first = asyncio.run(
        model_grader.run_workflow(make_run_config(agents=[SPECIFY], rows=["billing_console"]))
    )
    asyncio.run(
        model_grader.run_workflow(
            make_run_config(agents=[PLAN], rows=["billing_console"], from_run=first["dataset_run_id"])
        )
    )

    folders = run_folders(workflow_dir)
    assert len(folders) == 1
    assert artifacts.read_stage_output(folders[0], "prototype_plan")["source_agent"] == PLAN


def test_second_stage_receives_the_first_stages_output_as_upstream(
    workflow_dir, any_agent_rubric, dispatches, judgements
):
    """Chaining: the plan stage's prompt IS the spec stage's captured response."""
    asyncio.run(
        model_grader.run_workflow(
            make_run_config(agents=[SPECIFY, PLAN], rows=["billing_console"])
        )
    )

    plan_call = next(call for call in dispatches if call["agent_id"] == PLAN)
    assert plan_call["prompt"] == GOOD_SPEC


def test_all_errored_stage_aborts_the_remaining_stages(
    workflow_dir, any_agent_rubric, monkeypatch, judgements
):
    """A stage where every row errored has nothing to chain, so the run stops."""

    async def erroring(row, *, agent_id, sandbox_run_id, log_path, provider=None, model=None):
        return make_result(row, agent_id, errored=True)

    monkeypatch.setattr(dispatch, "run_row", erroring)
    result = asyncio.run(
        model_grader.run_workflow(
            make_run_config(agents=[SPECIFY, PLAN], rows=["billing_console", "hr_ats"])
        )
    )

    assert result["summary"]["status"] == "aborted"
    with pytest.raises(FileNotFoundError):
        artifacts.read_stage_artifact(Path(result["run_dir"]), "prototype_plan", "run")


def test_one_row_raising_does_not_kill_the_stage(
    workflow_dir, any_agent_rubric, monkeypatch, judgements
):
    """A row whose dispatch raises is recorded as errored; the other rows complete."""

    async def sometimes_raising(row, *, agent_id, sandbox_run_id, log_path, provider=None, model=None):
        if row.row_id == "hr_ats":
            raise RuntimeError("sandbox exploded")
        return make_result(row, agent_id)

    monkeypatch.setattr(dispatch, "run_row", sometimes_raising)
    result = asyncio.run(
        model_grader.run_workflow(
            make_run_config(agents=[SPECIFY], rows=["billing_console", "hr_ats"])
        )
    )

    runs = artifacts.read_stage_artifact(Path(result["run_dir"]), "prototype_specify", "run")
    by_id = {run["row_id"]: run for run in runs}
    assert by_id["hr_ats"]["errored"] is True
    assert "sandbox exploded" in by_id["hr_ats"]["error_reason"]
    assert by_id["billing_console"]["errored"] is False


def test_errored_and_expect_fail_rows_are_excluded_from_output(
    workflow_dir, any_agent_rubric, monkeypatch, judgements
):
    """output.json carries only rows a downstream stage may legitimately consume."""

    async def one_error(row, *, agent_id, sandbox_run_id, log_path, provider=None, model=None):
        return make_result(row, agent_id, errored=row.row_id == "hr_ats")

    monkeypatch.setattr(dispatch, "run_row", one_error)
    result = asyncio.run(
        model_grader.run_workflow(
            make_run_config(
                agents=[SPECIFY], rows=["billing_console", "hr_ats", "underspecified_brief"]
            )
        )
    )

    output = artifacts.read_stage_output(Path(result["run_dir"]), "prototype_specify")
    assert [row["id"] for row in output["rows"]] == ["billing_console"]


def test_judge_is_skipped_when_precheck_fails_and_the_rubric_says_so(
    workflow_dir, any_agent_rubric, monkeypatch, judgements
):
    """The shipped rubric sets skip_on_precheck_failure, so a malformed row is not graded."""

    async def malformed(row, *, agent_id, sandbox_run_id, log_path, provider=None, model=None):
        return make_result(row, agent_id, response=BAD_SPEC)

    monkeypatch.setattr(dispatch, "run_row", malformed)
    result = asyncio.run(
        model_grader.run_workflow(make_run_config(agents=[SPECIFY], rows=["billing_console"]))
    )

    grades = artifacts.read_stage_artifact(Path(result["run_dir"]), "prototype_specify", "grade")
    assert grades[0]["precheck_passed"] is False
    assert grades[0]["judged"] is False
    assert judgements == []


def test_no_judge_option_skips_the_judge_entirely(
    workflow_dir, any_agent_rubric, dispatches, judgements
):
    """`options.no_judge` runs the precheck and spends nothing on grading."""
    result = asyncio.run(
        model_grader.run_workflow(
            make_run_config(
                agents=[SPECIFY], rows=["billing_console"], options={"no_judge": True}
            )
        )
    )

    grades = artifacts.read_stage_artifact(Path(result["run_dir"]), "prototype_specify", "grade")
    assert grades[0]["precheck_passed"] is True
    assert grades[0]["score"] is None
    assert judgements == []


def test_dry_run_dispatches_nothing_and_returns_a_plan(
    workflow_dir, any_agent_rubric, dispatches, judgements
):
    """A dry run resolves and composes everything, and touches no model and no disk."""
    plan = asyncio.run(model_grader.run_workflow(make_run_config(), dry_run=True))

    assert plan["dry_run"] is True
    assert plan["row_count"] == 12
    assert [stage["agent_id"] for stage in plan["stages"]] == implemented_stages()
    assert plan["stages"][0]["rows"] == 12
    # The ROOT stage dispatches all 12 rows; the negative row is never judged and
    # never propagates, so every later stage is one row lighter. Summed, not
    # hardcoded, so onboarding a stage changes the estimate without a red test.
    assert plan["dispatch_estimate"]["agent_calls"] == sum(
        stage["dispatches"] for stage in plan["stages"]
    )
    assert plan["stages"][0]["judge_calls"] == 11, "the expect:fail row is never judged"
    assert plan["not_run"] == []
    assert dispatches == [] and judgements == []
    assert not (workflow_dir / ".runs").exists()


def test_resolved_config_is_written_before_the_first_dispatch(
    workflow_dir, any_agent_rubric, monkeypatch, judgements
):
    """A crash mid-run must still leave a re-runnable config behind."""
    seen = {}

    async def checking(row, *, agent_id, sandbox_run_id, log_path, provider=None, model=None):
        # logs/<row_id>/<agent>.log — the run dir is three levels up.
        run_dir = Path(log_path).parents[2]
        seen["config"] = artifacts.read_resolved_config(run_dir)
        return make_result(row, agent_id)

    monkeypatch.setattr(dispatch, "run_row", checking)
    asyncio.run(model_grader.run_workflow(make_run_config(rows=["billing_console"])))

    assert seen["config"]["dataset"] == "datasets/ten-industries.json"
    assert seen["config"]["agents"] == "all"


def test_run_summary_is_running_mid_stage_and_terminal_after(
    workflow_dir, any_agent_rubric, monkeypatch, judgements
):
    """`status: running` before each stage means a crash records where it died."""
    seen = {}

    async def checking(row, *, agent_id, sandbox_run_id, log_path, provider=None, model=None):
        # FIRST dispatch only: by the last one the first stage has finished, so
        # overwriting would assert about the end of the run, not the middle.
        run_dir = Path(log_path).parents[2]
        seen.setdefault("mid", artifacts.read_run_summary(run_dir))
        return make_result(row, agent_id)

    monkeypatch.setattr(dispatch, "run_row", checking)
    result = asyncio.run(model_grader.run_workflow(make_run_config(rows=["billing_console"])))

    assert seen["mid"]["status"] == "running"
    assert seen["mid"]["finished_at"] is None
    stage = next(entry for entry in seen["mid"]["stages"] if entry["agent_id"] == SPECIFY)
    assert stage["status"] == "running"
    assert result["summary"]["status"] == "completed"
    assert result["summary"]["finished_at"] is not None


def test_concurrency_is_bounded_by_the_option(
    workflow_dir, any_agent_rubric, monkeypatch, judgements
):
    """No more rows are ever in flight at once than `options.concurrency`."""
    inflight = {"now": 0, "max": 0}

    async def counting(row, *, agent_id, sandbox_run_id, log_path, provider=None, model=None):
        inflight["now"] += 1
        inflight["max"] = max(inflight["max"], inflight["now"])
        await asyncio.sleep(0.01)
        inflight["now"] -= 1
        return make_result(row, agent_id)

    monkeypatch.setattr(dispatch, "run_row", counting)
    asyncio.run(
        model_grader.run_workflow(make_run_config(agents=[SPECIFY], options={"concurrency": 2}))
    )

    assert inflight["max"] == 2


def test_an_unparseable_upstream_skips_its_row_not_the_run(
    workflow_dir, any_agent_rubric, judgements, monkeypatch
):
    """A malformed upstream is a RESULT to record, not a usage error that aborts.

    Every stage answering with a spec means prototype-build's adapter cannot
    parse the plan. That used to raise out of the run and exit 2.
    """
    async def always_a_spec(row, *, agent_id, sandbox_run_id, log_path, provider=None, model=None):
        return _make_result(row, agent_id, response=GOOD_SPEC, errored=False)

    monkeypatch.setattr(dispatch, "run_row", always_a_spec)
    result = asyncio.run(model_grader.run_workflow(make_run_config(rows=["billing_console"])))

    assert result["summary"]["status"] in ("completed", "partial")
    build = next(s for s in result["summary"]["stages"] if s["agent_id"] == "prototype-build")
    assert build["status"] != "aborted"


def test_a_declared_dry_run_sample_lets_downstream_adapters_compose(workflow_dir, any_agent_rubric):
    """A preview must not report a failure that cannot happen in a live run.

    prototype-build parses `## Task N:` headers out of the plan. Before plan
    declared a real-shaped `dry_run_sample`, EVERY preview reported an adapter
    failure — noise that trains you to stop reading the notes block.
    """
    plan = asyncio.run(model_grader.run_workflow(make_run_config(), dry_run=True))

    build = next(s for s in plan["stages"] if s["agent_id"] == "prototype-build")
    assert build["note"] is None, f"a clean preview must have nothing to say: {build['note']}"
    assert build["dispatches"] > 0


def test_a_stale_dry_run_sample_still_reports_a_note(workflow_dir, any_agent_rubric, monkeypatch):
    """The note is not suppressed — it now means the SAMPLE is wrong."""
    real_load = config.load_workflow

    def stale_sample(name):
        workflow = real_load(name)
        for stage in workflow["stages"]:
            if stage["agent_id"] == "prototype-plan":
                stage["dry_run_sample"] = "a plan with no task headers at all"
        return workflow

    monkeypatch.setattr(config, "load_workflow", stale_sample)
    plan = asyncio.run(model_grader.run_workflow(make_run_config(), dry_run=True))

    build = next(s for s in plan["stages"] if s["agent_id"] == "prototype-build")
    assert build["note"] and "dry_run_sample" in build["note"]
    assert build["dispatches"] > 0, "still counted — a live run would pay for these rows"


def test_every_stage_writes_its_document_into_src(
    workflow_dir, any_agent_rubric, dispatches, judgements
):
    """`src/<brief>/` holds the brief's whole document set, as real files.

    Keyed by BRIEF, not by agent: spec.md, tasks.md and prototype.html for one
    brief are one project and get read together. This used to copy the sandbox
    instead, which only tool-using stages ever touch — so the three text stages
    produced empty folders and the documents existed only inside JSON.
    """
    result = asyncio.run(model_grader.run_workflow(make_run_config(rows=["billing_console"])))

    src = Path(result["run_dir"]) / "src" / "billing_console"
    assert sorted(p.name for p in src.iterdir()) == [
        "analysis.md", "prototype.final.html", "prototype.html", "spec.md", "tasks.md"
    ]
    assert src.joinpath("spec.md").read_text().startswith("<spec>")
    assert src.joinpath("tasks.md").read_text().startswith("<tasks>")
    assert src.joinpath("prototype.html").read_text().startswith("<!doctype html>")


def test_build_and_validate_do_not_overwrite_each_other(
    workflow_dir, any_agent_rubric, dispatches, judgements
):
    """Both produce HTML; the final gate's version is kept separately.

    One filename would mean the last writer wins and the before/after — the only
    way to see what prototype-validate actually changed — is lost.
    """
    result = asyncio.run(model_grader.run_workflow(make_run_config(rows=["billing_console"])))

    src = Path(result["run_dir"]) / "src" / "billing_console"
    assert src.joinpath("prototype.html").exists()
    assert src.joinpath("prototype.final.html").exists()


def test_a_failed_write_never_fails_the_run(tmp_path):
    """A run that spent real tokens is not failed because a file could not be written."""
    assert artifacts.write_src_file(None, "row", "spec.md", "x") is None
    assert artifacts.write_src_file(tmp_path, "row", "", "x") is None
    assert artifacts.write_src_file(tmp_path, "row", "spec.md", "") is None


# ── rejudge: the main run minus the generation ─────────────────────────────


def _first_run(workflow_dir) -> str:
    """One scripted run of the first stage, returning its dataset_run_id."""
    result = asyncio.run(
        model_grader.run_workflow(
            make_run_config(agents=[SPECIFY], rows=["billing_console"])
        )
    )
    return result["dataset_run_id"]


def test_rejudge_replays_stored_responses_and_never_dispatches(
    workflow_dir, any_agent_rubric, dispatches, judgements, monkeypatch
):
    """A rejudge re-scores the captured responses; the agent is never called."""
    run_id = _first_run(workflow_dir)

    async def no_dispatch(*args, **kwargs):
        raise AssertionError("rejudge must never dispatch an agent")

    rejudged_calls = []

    async def stricter_grade(response, *, rubric, system_prompt, prompt, precheck_reason):
        rejudged_calls.append({"response": response, "system_prompt": system_prompt})
        return judge.JudgeVerdict(
            sub_scores={d["id"]: 60 for d in rubric["dimensions"]},
            resolved_model_id="fake-judge-v2",
        )

    monkeypatch.setattr(dispatch, "run_row", no_dispatch)
    monkeypatch.setattr(judge, "grade", stricter_grade)

    result = asyncio.run(
        model_grader.run_workflow(
            make_run_config(agents=[SPECIFY], from_run=run_id), rejudge=True
        )
    )

    run_dir = Path(result["run_dir"])
    # The judge saw the ORIGINAL response and the CAPTURED prompt, verbatim.
    assert rejudged_calls[0]["response"] == GOOD_SPEC
    assert rejudged_calls[0]["system_prompt"] == f"composed system prompt for {SPECIFY}"
    # The new verdict replaced the old one, through the ordinary scoring path.
    score = artifacts.read_stage_artifact(run_dir, "prototype_specify", "score")
    assert score["scores"]["average_all"] == 60.0
    assert score["hashes"]["judge_resolved_model_id"] == "fake-judge-v2"
    # The captured response survives, and the replaced artifacts are superseded.
    runs = artifacts.read_stage_artifact(run_dir, "prototype_specify", "run")
    assert runs[0]["response"] == GOOD_SPEC
    superseded = run_dir / "artifacts" / "superseded"
    assert list(superseded.glob("prototype_specify_a1_*")), "old verdict is kept"
    # The reports regenerate in place — one set, no rejudge-specific copies.
    assert (run_dir / "reports" / "report.md").exists()
    assert result["summary"]["status"] == "completed"


def test_rejudge_all_restricts_itself_to_the_captured_stages(
    workflow_dir, any_agent_rubric, dispatches, judgements
):
    """`agents: all` re-judges what the folder holds and lists the rest as not run."""
    run_id = _first_run(workflow_dir)

    result = asyncio.run(
        model_grader.run_workflow(make_run_config(from_run=run_id), rejudge=True)
    )

    ran = [stage["agent_id"] for stage in result["stages"]]
    assert ran == [SPECIFY]
    assert PLAN in result["summary"]["not_run"]


def test_rejudge_of_an_uncaptured_stage_is_an_error(
    workflow_dir, any_agent_rubric, dispatches, judgements
):
    """Naming a stage with nothing captured must fail loudly, not silently skip."""
    run_id = _first_run(workflow_dir)

    with pytest.raises(ValueError, match="no captured run artifact"):
        asyncio.run(
            model_grader.run_workflow(
                make_run_config(agents=[PLAN], from_run=run_id), rejudge=True
            )
        )


def test_rejudge_without_an_existing_folder_is_an_error(
    workflow_dir, any_agent_rubric, dispatches, judgements
):
    """A typo'd run id must not mint an empty folder."""
    with pytest.raises(ValueError, match="no run folder"):
        asyncio.run(
            model_grader.run_workflow(
                make_run_config(from_run="260101-000000-nope"), rejudge=True
            )
        )
    assert not (workflow_dir / ".runs" / "260101-000000-nope").exists()


def test_rejudge_keeps_code_findings_in_place(
    workflow_dir, any_agent_rubric, dispatches, judgements
):
    """The replayed responses are unchanged, so the code findings over them stay valid."""
    run_id = _first_run(workflow_dir)
    run_dir = run_folders(workflow_dir)[0]
    findings = run_dir / "artifacts" / "prototype_specify_code_findings.json"
    findings.write_text('{"findings": {"billing_console": {"ok": true}}}', encoding="utf-8")

    asyncio.run(
        model_grader.run_workflow(
            make_run_config(agents=[SPECIFY], from_run=run_id), rejudge=True
        )
    )

    assert findings.exists(), "a rejudge must not supersede still-valid code findings"
    superseded = run_dir / "artifacts" / "superseded"
    assert not list(superseded.glob("*code_findings*"))
    assert list(superseded.glob("prototype_specify_a1_grade.json"))


# ── automatic code grading after the model track ───────────────────────────


@pytest.fixture(autouse=True)
def code_grading_stub(monkeypatch):
    """Record the auto code-grade call; unit tests never launch a browser."""
    calls = []

    def fake(dataset_run_id, *, workflow_dir, render=False, interactions=False, only=None):
        calls.append({
            "run": dataset_run_id, "only": only,
            "render": render, "interactions": interactions,
        })
        return {"dataset_run_id": dataset_run_id, "status": "graded", "stages": []}

    monkeypatch.setattr(model_grader.code_grader, "grade_run_folder", fake)
    return calls


def test_code_grading_runs_automatically_after_the_html_stages(
    workflow_dir, any_agent_rubric, dispatches, judgements, code_grading_stub
):
    """A full run grades its HTML stages' output without a second command."""
    result = asyncio.run(model_grader.run_workflow(make_run_config(rows=["billing_console"])))

    assert len(code_grading_stub) == 1
    call = code_grading_stub[0]
    assert call["only"] == ["prototype-build", "prototype-validate"]
    assert call["render"] is True and call["interactions"] is True
    assert result["code"]["status"] == "graded"


def test_code_grading_can_be_disabled_per_run(
    workflow_dir, any_agent_rubric, dispatches, judgements, code_grading_stub
):
    asyncio.run(
        model_grader.run_workflow(
            make_run_config(rows=["billing_console"], options={"code_grading": False})
        )
    )
    assert code_grading_stub == []


def test_a_run_with_no_html_stage_skips_code_grading(
    workflow_dir, any_agent_rubric, dispatches, judgements, code_grading_stub
):
    asyncio.run(
        model_grader.run_workflow(
            make_run_config(agents=[SPECIFY], rows=["billing_console"])
        )
    )
    assert code_grading_stub == []


# ── automatic prompt advice after the code track ───────────────────────────


def _emit_all(on_event, events) -> None:
    """Push a list of progress events through a callback that may be absent."""
    for event in events:
        if on_event is not None:
            on_event(event)


@pytest.fixture(autouse=True)
def advise_stub(monkeypatch):
    """Record the auto-advise call; unit tests never reach a real advisor.

    Autouse and unconditional: the advise step is LIVE, so an unstubbed test
    would spend tokens. `_auto_advise` swallows failures by design, which means
    a missing stub would not fail loudly — it would just quietly call out.
    """
    calls = []

    async def fake(dataset_run_id, *, workflow_name, agents, judge_overrides, on_event=None):
        calls.append({
            "run": dataset_run_id, "workflow": workflow_name,
            "agents": agents, "judge": judge_overrides,
        })
        # The real advisor speaks the model-stage vocabulary; emitting it here is
        # what proves model_grader re-tags it before the printer ever sees it.
        for agent in agents:
            _emit_all(on_event, [
                {"event": "stage_start", "agent_id": agent, "rows": 1},
                {"event": "stage_done", "agent_id": agent, "status": "advised", "edits": 1},
            ])
        return {
            "dataset_run_id": dataset_run_id,
            "stages": [{"agent_id": agent, "edits": 1, "errored": False} for agent in agents],
        }

    monkeypatch.setattr(model_grader.prompt_advisor, "advise_run", fake)
    return calls


def test_advice_runs_automatically_over_the_graded_stages(
    workflow_dir, any_agent_rubric, dispatches, judgements, advise_stub
):
    """One live run closes the whole loop: judge, code checks, then advice."""
    result = asyncio.run(model_grader.run_workflow(make_run_config(rows=["billing_console"])))

    assert len(advise_stub) == 1
    assert advise_stub[0]["agents"] == [
        SPECIFY, "prototype-plan", "prototype-analyze", "prototype-build", "prototype-validate",
    ]
    assert [stage["agent_id"] for stage in result["advice"]["stages"]] == advise_stub[0]["agents"]


def test_every_post_model_phase_reports_its_progress(
    workflow_dir, any_agent_rubric, dispatches, judgements, advise_stub
):
    """Both silent phases announce themselves, and advice never masquerades as a stage.

    The advisor emits `stage_start`/`stage_done` exactly like a model stage.
    Forwarded raw, the printer drew an empty titled rule per advised stage at
    the end of a finished run; re-tagging is what stops that.
    """
    events = []
    asyncio.run(
        model_grader.run_workflow(
            make_run_config(rows=["billing_console"]), on_event=events.append
        )
    )

    phases = [event["phase"] for event in events if event["event"] == "phase_start"]
    assert phases == ["code", "advice"], "each post-model phase announces itself, in order"
    assert {event["event"] for event in events} >= {
        "phase_start", "phase_done", "advice_stage_start", "advice_stage_done",
    }
    advised = [event for event in events if event["event"].startswith("advice_")]
    assert advised and all(event["phase"] == "advice" for event in advised)
    # No advisor event may reach the printer wearing a model stage's name.
    after_model = events[events.index(next(e for e in events if e["event"] == "phase_start")):]
    assert not [event for event in after_model if event["event"] in ("stage_start", "stage_done")]


def test_advice_can_be_disabled_per_run(
    workflow_dir, any_agent_rubric, dispatches, judgements, advise_stub
):
    asyncio.run(
        model_grader.run_workflow(
            make_run_config(rows=["billing_console"], options={"advise": False})
        )
    )
    assert advise_stub == []


def test_a_run_that_never_judged_has_nothing_to_advise_on(
    workflow_dir, any_agent_rubric, dispatches, judgements, advise_stub
):
    """`no_judge` leaves no weaknesses, so advising would be a call for nothing."""
    asyncio.run(
        model_grader.run_workflow(
            make_run_config(rows=["billing_console"], options={"no_judge": True})
        )
    )
    assert advise_stub == []


def test_a_failing_advisor_never_fails_the_run(
    workflow_dir, any_agent_rubric, dispatches, judgements, monkeypatch
):
    """Advice is a proposal — a paid run must not be reported as failed over it."""
    async def boom(*args, **kwargs):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(model_grader.prompt_advisor, "advise_run", boom)

    result = asyncio.run(model_grader.run_workflow(make_run_config(rows=["billing_console"])))

    assert result["summary"]["status"] == "completed"
    assert result["advice"]["status"] == "errored"
    assert "rate limited" in result["advice"]["reason"]


def test_the_plan_counts_the_advice_calls_it_will_make(
    workflow_dir, any_agent_rubric, dispatches, judgements
):
    """The cost preview names the advisor's spend rather than hiding it."""
    plan = asyncio.run(
        model_grader.run_workflow(make_run_config(rows=["billing_console"]), dry_run=True)
    )
    estimate = plan["dispatch_estimate"]

    assert estimate["advice_calls"] == 5, "one advisor call per judged stage"
    assert estimate["total"] == (
        estimate["agent_calls"] + estimate["judge_calls"] + estimate["advice_calls"]
    )


def test_a_plan_with_advice_off_estimates_no_advisor_spend(
    workflow_dir, any_agent_rubric, dispatches, judgements
):
    plan = asyncio.run(
        model_grader.run_workflow(
            make_run_config(rows=["billing_console"], options={"advise": False}), dry_run=True
        )
    )

    assert plan["dispatch_estimate"]["advice_calls"] == 0


def test_rejudge_regrades_only_the_stages_missing_findings(
    workflow_dir, any_agent_rubric, dispatches, judgements, code_grading_stub
):
    """A rejudge keeps valid findings; only a stage without any gets the browser pass."""
    result = asyncio.run(model_grader.run_workflow(make_run_config(rows=["billing_console"])))
    run_dir = Path(result["run_dir"])
    code_grading_stub.clear()
    # The build stage already has findings; validate does not.
    (run_dir / "artifacts" / "prototype_build_code_findings.json").write_text(
        '{"findings": {"billing_console": {"ok": true}}}', encoding="utf-8"
    )

    asyncio.run(
        model_grader.run_workflow(
            make_run_config(from_run=result["dataset_run_id"]), rejudge=True
        )
    )

    assert [call["only"] for call in code_grading_stub] == [["prototype-validate"]]
