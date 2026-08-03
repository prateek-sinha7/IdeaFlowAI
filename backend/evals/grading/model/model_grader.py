"""Model-track orchestration: run stages, run rows, write artifacts.

Reads top to bottom as run_workflow -> run_stage -> run_row. Holds no parsing,
no path building and no statistics — those belong to config, artifacts and
scoring respectively.
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from evals.grading import artifacts, config, markdown_report
from evals.grading.code import code_grader
from evals.grading.model import (
    dispatch,
    judge,
    precheck,
    prompt_advisor,
    scoring,
    stage_input,
)

# A dry run composes real prompts but dispatches nothing, so a chained stage
# needs SOME upstream text to compose against. A stage whose output is PARSED
# downstream declares a `dry_run_sample` in workflow.yaml; this generic line
# stands in for the rest, where the text is only ever forwarded.
DRY_RUN_RESPONSE = "(dry run) {agent_id} produced no response for row {row_id}"

# stage_input marks a row skipped with this prefix when its adapter could not
# parse the upstream. A dry run undoes that so the cost estimate stays honest.
ADAPTER_FAILURE_PREFIX = "upstream could not be adapted"


async def run_workflow(
    run_config, *, dry_run: bool = False, replace: bool = False, on_event=None,
    rejudge: bool = False, dataset_run_id: str | None = None,
) -> dict:
    """Run every selected stage into one run folder, in workflow order.

    `agents: all` runs every stage with `status: implemented` and STOPS at the
    first that is not — never skips it and runs a later stage against an empty
    upstream. An explicit list runs that subset, always in workflow order, and a
    non-root first agent requires `from_run`.

    `rejudge` is the SAME run, minus the generation: each stage's rows are
    rebuilt from its captured run.json and the stored responses flow straight
    into precheck and the judge — no agent is dispatched, no sandbox is built.
    Everything downstream (scoring, run_summary, reports) is the ordinary path,
    so a rejudged folder never looks different from a judged one; the replaced
    artifacts are superseded exactly as `--replace` supersedes them.

    Writes the resolved run config BEFORE the first dispatch, and rewrites
    run_summary.json with `status: running` before each stage and again after, so
    a crash leaves a record of where it died.

    `on_event` is an optional callback taking one dict per progress event
    (`stage_start`, `row_start`, `row_done`, `stage_done`). This module never
    prints — the caller decides how, or whether, to show progress.
    """
    workflow = config.load_workflow(run_config.workflow)
    workflow_dir = Path(workflow["workflow_dir"])
    selected, not_run = _select_stages(workflow, run_config.agents)

    reference = _dataset_reference(run_config, workflow)
    dataset = _select_rows(
        config.load_dataset(
            reference, workflow_dir=workflow_dir, agent_id=workflow["stages"][0]["agent_id"]
        ),
        run_config,
    )
    # Minted here ONLY when the caller has not already minted one. The CLI runs
    # this function twice — once as a dry run to print the plan, then for real —
    # and a fresh timestamp on the second call made the run folder disagree with
    # the id the header had just announced, by however long the preflight took.
    dataset_run_id = (
        dataset_run_id
        or run_config.from_run
        or artifacts.new_dataset_run_id(dataset["dataset_id"])
    )
    if rejudge:
        _assert_rejudgeable(dataset_run_id, run_config, workflow_dir, dry_run=dry_run)
    run_dir = _open_run_folder(
        dataset_run_id, workflow_dir=workflow_dir, dry_run=dry_run, from_run=run_config.from_run
    )
    stored = _stored_stage_runs(run_dir, selected) if rejudge else {}
    if rejudge:
        selected, not_run = _restrict_to_captured(selected, not_run, stored, run_config.agents)
    if run_dir is not None:
        artifacts.write_resolved_config(run_dir, _resolved_config(run_config, reference))

    summary = _open_summary(run_dir, run_config, workflow, dataset, dataset_run_id, selected, not_run)
    produced: dict[str, dict] = {}
    results = []
    for stage in selected:
        agent_id = stage["agent_id"]
        rubric = _apply_judge_overrides(config.load_rubric(workflow_dir, agent_id), run_config)
        stored_runs = stored.get(agent_id)
        # A replayed stage composes nothing — its prompts are already in the
        # captured rows — so its upstreams are never read.
        upstreams = {} if stored_runs is not None else _resolve_upstreams(
            stage, run_dir=run_dir, produced=produced, from_run=run_config.from_run
        )

        _begin_stage(run_dir, summary, agent_id)
        result = await run_stage(
            stage,
            run_dir=run_dir,
            workflow_dir=workflow_dir,
            run_config=run_config,
            dataset=dataset,
            upstream_outputs=upstreams,
            rubric=rubric,
            dry_run=dry_run,
            # A rejudge always supersedes: the point is to replace the verdict.
            replace=replace or rejudge,
            on_event=on_event,
            stored_runs=stored_runs,
        )

        results.append(result)
        produced[agent_id] = result["output"]
        _end_stage(run_dir, summary, result)
        if result["aborted"]:
            break

    if dry_run:
        return _plan(run_config, dataset, dataset_run_id, results, not_run)

    summary["rows"] = _row_index(dataset, results, workflow["stages"])
    _write_summary(run_dir, summary, status=_terminal_status(results, selected))
    code = None
    if run_config.options.get("code_grading", True):
        code = await _auto_code_grade(run_dir, workflow_dir, results, on_event=on_event)
    # Advice reads the code findings as ground truth, so it follows the code
    # track; the report is rendered last so it can link the advice it now has.
    advice = None
    if run_config.options.get("advise", True):
        advice = await _auto_advise(run_dir, run_config, results, on_event=on_event)
    report_path = _write_markdown_report(run_dir)
    _sweep_sandboxes()
    return {
        "dataset_run_id": dataset_run_id,
        "run_dir": str(run_dir),
        "summary": summary,
        # The per-stage results, carrying each stage's score — the caller reads
        # these to print the report and to notice a stage whose judge died.
        "stages": results,
        "code": code,
        "advice": advice,
        "report_path": None if report_path is None else str(report_path),
    }


async def _auto_code_grade(run_dir, workflow_dir: Path, results: list[dict], *, on_event=None):
    """The free deterministic checks over the HTML this run just produced.

    Runs after the model track so the reports carry the judge score and the
    code score side by side without a second command. Grades only completed
    HTML stages that LACK findings: a fresh or --replace run always lacks them
    (its supersede swept the stale ones), while a rejudge keeps its still-valid
    findings and skips the browser pass.

    Runs in a WORKER THREAD: the code grader drives its own event loops
    (`asyncio.run` per browser check), which cannot nest inside the loop this
    coroutine is already running on — called inline, every check silently died
    with "coroutine was never awaited". Never load-bearing, but a failure is
    RETURNED, not swallowed: a silently absent code column is indistinguishable
    from one that was never asked for.
    """
    if run_dir is None:
        return None
    completed = {
        result["agent_id"] for result in results if result.get("status") == "completed"
    }
    wanted = [
        stage["agent_id"]
        for stage in code_grader.GRADED_STAGES
        if stage["agent_id"] in completed
        and not artifacts.artifact_path(
            run_dir, _agent_token(stage["agent_id"]), code_grader.FINDINGS_KIND
        ).exists()
    ]
    if not wanted:
        return None
    # This phase drives a real browser and is the slowest silent stretch of a
    # run. It is announced before it starts, so the terminal never looks hung.
    _emit(on_event, {"event": "phase_start", "phase": "code", "agent_ids": wanted})
    try:
        result = await asyncio.to_thread(
            code_grader.grade_run_folder,
            Path(run_dir).name,
            workflow_dir=workflow_dir,
            render=True,
            interactions=True,
            only=wanted,
        )
    except Exception as error:  # noqa: BLE001 - the free track must never fail the paid one
        result = {
            "status": "errored",
            "reason": f"{type(error).__name__}: {error}",
            "stages": [],
        }
    _emit(on_event, {"event": "phase_done", "phase": "code", "result": result})
    return result


async def _auto_advise(run_dir, run_config, results: list[dict], *, on_event=None):
    """Turn this run's own evidence into prompt advice, in the same pass.

    The improvement loop closed without a second command: the reports the run
    just wrote (judge weaknesses, per-dimension aggregates, the code track's
    browser findings) are handed straight back to a model, which returns the
    prompt delta as `reports/prompt_advice_<agent_token>.md`.

    LIVE — one model call per graded stage, on the judge model. Skipped when
    the run never judged (`no_judge` leaves nothing to advise on) and when no
    stage produced a score. A failure is RETURNED, never raised: advice is a
    proposal, and a run that spent real agent tokens must not be reported as
    failed because the advisor was rate-limited.
    """
    if run_dir is None or run_config.options.get("no_judge"):
        return None
    graded = [
        result["agent_id"]
        for result in results
        if (result.get("score") or {}).get("counts", {}).get("judged")
    ]
    if not graded:
        return None
    _emit(on_event, {"event": "phase_start", "phase": "advice", "agent_ids": graded})
    try:
        result = await prompt_advisor.advise_run(
            Path(run_dir).name,
            workflow_name=run_config.workflow,
            agents=graded,
            judge_overrides=run_config.judge,
            # Re-tagged, never forwarded raw: the advisor speaks the same
            # `stage_start` / `stage_done` vocabulary as a model stage, and a
            # printer that cannot tell them apart draws an empty stage header
            # with no rows under it for every advised stage.
            on_event=lambda event: _emit(on_event, _as_advice_event(event)),
        )
    except Exception as error:  # noqa: BLE001 - advice must never fail a paid run
        result = {
            "status": "errored",
            "reason": f"{type(error).__name__}: {error}",
            "stages": [],
        }
    _emit(on_event, {"event": "phase_done", "phase": "advice", "result": result})
    return result


def _as_advice_event(event: dict) -> dict:
    """One advisor progress event, renamed into the advice phase's vocabulary."""
    return {**event, "event": f"advice_{event.get('event')}", "phase": "advice"}


def _sweep_sandboxes() -> None:
    """Remove EXPIRED agent sandboxes under `<RUNS_ROOT>/` at end of run.

    Dispatch builds one RunSandbox per row (`runs/eval-graded/<run>-<row>/`) —
    the disk the agents really write to, kept so a fresh run can be inspected.
    In the app the server sweeps them on a TTL; grading has no server, so
    without this call every eval sandbox since forever accumulates. The sweep
    is the runtime's own (`RUN_DIR_TTL_HOURS`, default 48h): THIS run's
    sandboxes survive for debugging, old ones go.
    """
    try:
        dispatch.sweep_expired_sandboxes()
    except Exception:  # noqa: BLE001 - housekeeping is never load-bearing
        pass


def _write_markdown_report(run_dir) -> Path | None:
    """Render REPORT.md into the run folder, never failing the run over it.

    A report is a convenience; a run that spent real tokens must not be
    reported as failed because a rendering helper raised.
    """
    if run_dir is None:
        return None
    try:
        return markdown_report.write_report(Path(run_dir))
    except Exception:  # noqa: BLE001 - reporting is never load-bearing
        return None


async def run_stage(
    stage,
    *,
    run_dir: Path,
    workflow_dir: Path,
    run_config,
    dataset,
    upstream_outputs,
    rubric,
    dry_run: bool = False,
    replace: bool = False,
    on_event=None,
    stored_runs: dict | None = None,
) -> dict:
    """Run one stage over all its rows, then write its four artifacts once.

    Rows run concurrently up to `options.concurrency`; stages never do. Per-row
    exceptions are isolated so one row cannot kill a stage. Artifacts are written
    once from in-memory results at end of stage, which is why there are zero
    concurrent writers to any file. Aborts the remaining stages if EVERY row
    errored — there is nothing to chain forward.

    `stored_runs` (row_id -> captured run entry) switches the stage to REPLAY:
    the rows are rebuilt from the entries and each dispatch is answered from
    the stored response instead of an agent. Every step after the dispatch is
    the identical code path.
    """
    agent_id = stage["agent_id"]
    ids = _stage_ids(run_dir, agent_id, dry_run=dry_run)
    propagate = bool(run_config.options.get("propagate_negative"))
    if dry_run:
        inputs, note = _planned_inputs(
            stage, dataset, upstream_outputs, workflow_dir, propagate=propagate
        )
        return _stage_plan(stage, inputs, ids, run_config, dataset, rubric, note=note)
    if stored_runs is not None:
        inputs = _replay_inputs(stored_runs)
        stored_prompt = _captured_prompt(run_dir, ids["agent_token"])
    else:
        inputs = stage_input.build_stage_inputs(
            stage, dataset=dataset, upstream_outputs=upstream_outputs,
            config_dir=workflow_dir, propagate_expected_fail=propagate,
        )
        stored_prompt = ""

    artifacts.guard_append_only(
        run_dir, ids["agent_token"], replace=replace,
        # A replay's responses are unchanged, so the deterministic code
        # findings over them are still true and stay in place.
        keep=("code_findings",) if stored_runs is not None else (),
    )
    _emit(on_event, {"event": "stage_start", "agent_id": agent_id, "rows": len(inputs)})
    semaphore = asyncio.Semaphore(run_config.options["concurrency"])
    pairs = await asyncio.gather(
        *(
            _guarded_row(
                row,
                semaphore=semaphore,
                stage=stage,
                run_dir=run_dir,
                run_config=run_config,
                rubric=rubric,
                ids=ids,
                on_event=on_event,
                position=(index, len(inputs)),
                stored_entry=None if stored_runs is None else stored_runs.get(row.row_id),
                stored_prompt=stored_prompt,
            )
            for index, row in enumerate(inputs, start=1)
        )
    )

    runs = [run for run, _ in pairs]
    grades = [grade for _, grade in pairs]
    artifacts.write_system_prompt(run_dir, ids["agent_token"], _take_system_prompt(runs))
    score = _stage_score(runs, grades, rubric, run_config, dataset, ids)
    output = _stage_output(runs, dataset, ids, agent_id, include_negative=propagate)
    artifacts.write_stage(
        run_dir, ids["agent_token"], runs=runs, grades=grades, score=score, output=output
    )
    _emit(on_event, {
        "event": "stage_done",
        "agent_id": agent_id,
        "status": "aborted" if _all_errored(runs) else "completed",
        "score": score,
    })
    return {
        "agent_id": agent_id,
        "order": stage.get("order"),
        "agent_run_id": ids["agent_run_id"],
        "status": "aborted" if _all_errored(runs) else "completed",
        "score": score,
        "output": output,
        "aborted": _all_errored(runs),
    }


async def run_row(
    stage_input_row, *, stage, run_dir: Path, run_config, rubric, ids,
    on_event=None, position=(0, 0), stored_entry=None, stored_prompt="",
) -> tuple[dict, dict]:
    """Dispatch one row, precheck it, judge it; return its run + grade entries.

    A skipped row (skip_reason set) is recorded without dispatching. Judging is
    skipped when the row failed precheck and the rubric sets
    `skip_on_precheck_failure`, and for `expect: fail` rows, which are also kept
    out of the stage's output.json.

    `stored_entry` replays a captured row: the generation step is answered from
    the stored response and everything after it runs unchanged.
    """
    agent_id = stage["agent_id"]
    if stage_input_row.skip_reason:
        return _row_entries(stage_input_row, agent_id=agent_id, run_config=run_config, ids=ids)

    def phase(name: str) -> None:
        """Announce which step of the row is running — the slow ones are visible."""
        _emit(on_event, {
            "event": "row_phase", "phase": name, "agent_id": agent_id,
            "row_id": stage_input_row.row_id,
            "index": position[0], "total": position[1],
        })

    under_test = run_config.agent_under_test
    if stored_entry is not None:
        result = _replay_result(stage_input_row, agent_id, stored_entry, stored_prompt)
    else:
        phase("generating")
        result = await dispatch.run_row(
            stage_input_row,
            agent_id=agent_id,
            sandbox_run_id=f"{ids['dataset_run_id']}-{stage_input_row.row_id}",
            log_path=artifacts.log_path(run_dir, ids["agent_token"], stage_input_row.row_id),
            provider=under_test.get("provider"),
            model=under_test.get("model"),
        )
    # The stage's document, written where a human reads it. Every stage has one:
    # a text agent streams it, a tool agent has it read back from the sandbox.
    artifacts.write_src_file(
        run_dir, stage_input_row.row_id, stage.get("output_file"), result.response
    )
    signal = _extract_signal(stage.get("output_signal"), result.response)
    if result.errored:
        return _row_entries(
            stage_input_row, agent_id=agent_id, run_config=run_config, ids=ids, result=result
        )

    phase("precheck")
    passed, reason = precheck.run(
        result.response, rubric.get("precheck") or {}, hook=rubric.get("validate_hook")
    )
    verdict = None
    if _should_judge(stage_input_row, passed, rubric, run_config):
        phase("judging")
        verdict = await judge.grade(
            result.response,
            rubric=rubric,
            system_prompt=result.system_prompt,
            prompt=stage_input_row.prompt,
            precheck_reason=reason,
        )
    return _row_entries(
        stage_input_row,
        agent_id=agent_id,
        run_config=run_config,
        ids=ids,
        result=result,
        precheck_result=(passed, reason),
        verdict=verdict,
        rubric=rubric,
        signal=signal,
    )


# ── stage selection and inputs ────────────────────────────────────────────


def _select_stages(workflow: dict, agents) -> tuple[list, list]:
    """The stages to run, always in workflow order, and the ones that will not.

    `all` takes the implemented PREFIX — a stage that is not implemented stops
    the run rather than being skipped over. An explicit list is honoured as
    given, so a deliberately named stage still runs (and fails loudly if its
    rubric is missing).
    """
    stages = workflow["stages"]
    if agents == "all":
        selected = _implemented_prefix(stages)
    else:
        known = {stage["agent_id"] for stage in stages}
        unknown = [agent for agent in agents if agent not in known]
        if unknown:
            raise ValueError(
                f"run config: agents {unknown} are not stages of workflow "
                f"'{workflow.get('workflow_id')}' ({sorted(known)})"
            )
        selected = [stage for stage in stages if stage["agent_id"] in set(agents)]

    chosen = {stage["agent_id"] for stage in selected}
    if not selected:
        raise ValueError(
            f"workflow '{workflow.get('workflow_id')}' has no stage to run for agents={agents!r}"
        )
    return selected, [stage for stage in stages if stage["agent_id"] not in chosen]


def _implemented_prefix(stages: list) -> list:
    """Every leading stage marked `status: implemented`, stopping at the first that is not."""
    prefix = []
    for stage in stages:
        if stage.get("status") != "implemented":
            break
        prefix.append(stage)
    return prefix


def _dataset_reference(run_config, workflow: dict) -> str:
    """The run's dataset path — empty in the run config means the workflow's default."""
    reference = run_config.dataset or workflow.get("default_dataset")
    if not reference:
        raise ValueError(
            f"run config declares no dataset and workflow "
            f"'{workflow.get('workflow_id')}' declares no default_dataset"
        )
    return reference


def _select_rows(dataset: dict, run_config) -> dict:
    """Apply the run config's `rows` and `limit` subsets to the loaded dataset."""
    rows = dataset.get("rows") or []
    if run_config.rows:
        wanted = list(run_config.rows)
        missing = [row_id for row_id in wanted if row_id not in {row["id"] for row in rows}]
        if missing:
            raise ValueError(f"run config: rows {missing} are not in dataset '{dataset['dataset_id']}'")
        rows = [row for row in rows if row["id"] in set(wanted)]
    if run_config.limit:
        rows = rows[: run_config.limit]
    return {**dataset, "rows": rows}


def _upstream_agents(stage: dict) -> list[str]:
    """Every agent this stage reads: its `from:` agents, then its seed-file agents."""
    stage_config = stage.get("input") or {}
    agents = list(stage_config.get("from") or [])
    for value in (stage_config.get("seed_files") or {}).values():
        if ":" not in str(value) and value not in agents:
            agents.append(value)
    return agents


def _resolve_upstreams(stage: dict, *, run_dir, produced: dict, from_run) -> dict:
    """Gather every upstream output this stage needs, from this run or the extended folder."""
    resolved = {}
    for agent_id in _upstream_agents(stage):
        if agent_id in produced:
            resolved[agent_id] = produced[agent_id]
        else:
            resolved[agent_id] = _read_upstream(
                agent_id, stage["agent_id"], run_dir=run_dir, from_run=from_run
            )
    return resolved


def _read_upstream(agent_id: str, consumer_id: str, *, run_dir, from_run) -> dict:
    """Read one upstream's output.json, or fail naming the artifact that is missing."""
    detail = f"there is no run folder to read {_agent_token(agent_id)}_output.json from"
    try:
        if run_dir is None:
            raise FileNotFoundError(detail)
        return artifacts.read_stage_output(run_dir, _agent_token(agent_id))
    except FileNotFoundError as error:
        raise ValueError(
            f"stage '{consumer_id}' consumes '{agent_id}', which did not run in this "
            f"selection: {error}. Pass from_run naming a run folder that already contains "
            f"that artifact (from_run is {from_run!r}); a missing upstream is never "
            "silently replaced by the dataset."
        ) from error


# ── rejudge replay ────────────────────────────────────────────────────────


def _assert_rejudgeable(dataset_run_id: str, run_config, workflow_dir: Path, *, dry_run: bool) -> None:
    """A rejudge must land on an existing folder — never mint one from a typo.

    Checked BEFORE `_open_run_folder`, which creates directories on sight.
    """
    if dry_run:
        return
    if not run_config.from_run:
        raise ValueError("rejudge extends an existing run: from_run must name the folder to re-judge")
    run_dir = artifacts.runs_root(workflow_dir) / dataset_run_id
    if not run_dir.is_dir():
        raise ValueError(f"no run folder '{dataset_run_id}' under {artifacts.runs_root(workflow_dir)}")


def _stored_stage_runs(run_dir, selected: list) -> dict[str, dict[str, dict]]:
    """Each selected stage's captured rows, keyed agent_id -> row_id -> entry."""
    if run_dir is None:
        return {}
    found: dict[str, dict[str, dict]] = {}
    for stage in selected:
        try:
            runs = artifacts.read_stage_artifact(run_dir, _agent_token(stage["agent_id"]), "run")
        except FileNotFoundError:
            continue
        found[stage["agent_id"]] = {run["row_id"]: run for run in runs}
    return found


def _restrict_to_captured(selected: list, not_run: list, stored: dict, agents) -> tuple[list, list]:
    """Keep only the stages whose responses this folder actually captured.

    An explicitly named stage with nothing captured is an error — there is
    nothing to re-judge and silently skipping it would report a run that never
    happened. Under `agents: all` the uncaptured tail just moves to not_run.
    """
    captured = [stage for stage in selected if stage["agent_id"] in stored]
    missing = [stage for stage in selected if stage["agent_id"] not in stored]
    if agents != "all" and missing:
        raise ValueError(
            f"stage(s) {[stage['agent_id'] for stage in missing]} have no captured run "
            "artifact in this folder — run the model track for them first"
        )
    if not captured:
        raise ValueError(
            "this run folder contains no stage with captured responses to re-judge. "
            "Stage artifacts are written once, at end of stage — a run that crashed or "
            "was interrupted mid-stage leaves none (its run_summary.json will say "
            "'running'). Re-run it first: "
            "grade.sh run <run folder>/grade_config.resolved.yaml"
        )
    return captured, not_run + missing


def _replay_inputs(stored_runs: dict[str, dict]) -> list:
    """Rows rebuilt from a previous run's captured entries, in stored order.

    The prompt is the one the agent really received — composed once, then
    frozen in run.json — so replay never re-runs the upstream join.
    """
    return [
        stage_input.StageInput(
            row_id=entry["row_id"],
            prompt=entry.get("prompt") or "",
            industry=entry.get("industry") or "",
            tags=list(entry.get("tags") or []),
            expect=entry.get("expect") or "pass",
            upstream_chain=list(entry.get("upstream_chain") or []),
            skip_reason=entry.get("skip_reason"),
        )
        for entry in stored_runs.values()
    ]


def _replay_result(row, agent_id: str, entry: dict, system_prompt: str):
    """A DispatchResult answered from the captured entry — nothing is dispatched.

    Tokens and model id are the ORIGINAL spend, kept so the rewritten run.json
    still states what the responses cost; only the judge's spend is new.
    """
    return dispatch.DispatchResult(
        row_id=row.row_id,
        agent_id=agent_id,
        response=entry.get("response") or "",
        system_prompt=system_prompt,
        errored=bool(entry.get("errored")),
        error_reason=entry.get("error_reason"),
        tokens_in=entry.get("tokens_in") or 0,
        tokens_out=entry.get("tokens_out") or 0,
        resolved_model_id=entry.get("resolved_model_id") or "unknown",
        log_path=entry.get("log_path") or "",
        sandbox_run_id="",
        seed_files=entry.get("seed_files") or {},
    )


def _captured_prompt(run_dir, agent_token: str) -> str:
    """The composed prompt the agent really saw; empty when never captured.

    The judge grades against the captured prompt, not a re-composition — the
    AGENT.md may have changed since, and grading old responses against a new
    prompt would blame the response for instructions it was never given.
    """
    try:
        return artifacts.read_system_prompt(run_dir, agent_token)
    except FileNotFoundError:
        return ""


# ── per-row execution ─────────────────────────────────────────────────────


async def _guarded_row(
    row, *, semaphore, on_event=None, position=(0, 0), **kwargs
) -> tuple[dict, dict]:
    """Run one row under the concurrency bound, converting any exception into an errored row."""
    agent_id = kwargs["stage"]["agent_id"]
    index, total = position
    async with semaphore:
        _emit(on_event, {
            "event": "row_start", "agent_id": agent_id, "row_id": row.row_id,
            "index": index, "total": total, "skipped": bool(row.skip_reason),
        })
        try:
            pair = await run_row(row, on_event=on_event, position=position, **kwargs)
        except Exception as error:  # noqa: BLE001 - one row must never kill a stage
            pair = _row_entries(
                row,
                agent_id=agent_id,
                run_config=kwargs["run_config"],
                ids=kwargs["ids"],
                result=_raised_result(row, agent_id, error),
            )
        run_entry, grade_entry = pair
        _emit(on_event, {
            "event": "row_done", "agent_id": agent_id, "row_id": row.row_id,
            "index": index, "total": total,
            "skipped": bool(row.skip_reason), "skip_reason": row.skip_reason,
            "errored": run_entry.get("errored"),
            "error_reason": run_entry.get("error_reason"),
            "precheck_passed": run_entry.get("precheck_passed"),
            "score": (grade_entry or {}).get("score"),
            "judge_errored": scoring.judge_errored(grade_entry or {}),
            "judge_error_reason": scoring.judge_error_reason(grade_entry or {}),
            # Split, not summed: the two halves are billed at different rates
            # and a row where the judge cost more than the agent is worth seeing.
            "agent_tokens": (run_entry.get("tokens_in") or 0)
            + (run_entry.get("tokens_out") or 0),
            "judge_tokens": ((grade_entry or {}).get("judge_tokens_in") or 0)
            + ((grade_entry or {}).get("judge_tokens_out") or 0),
        })
        return pair


def _emit(on_event, event: dict) -> None:
    """Hand one progress event to the caller's callback, if it wants them.

    Never lets a broken callback take down a run that is spending real money.
    """
    if on_event is None:
        return
    try:
        on_event(event)
    except Exception:  # noqa: BLE001 - progress reporting is never load-bearing
        pass


def _raised_result(row, agent_id: str, error: Exception):
    """A DispatchResult standing in for a row whose dispatch raised."""
    return dispatch.DispatchResult(
        row_id=row.row_id,
        agent_id=agent_id,
        response="",
        system_prompt="",
        errored=True,
        error_reason=f"{type(error).__name__}: {error}",
        tokens_in=0,
        tokens_out=0,
        resolved_model_id="unknown",
        log_path="",
        sandbox_run_id="",
    )


def _should_judge(row, precheck_passed: bool, rubric: dict, run_config) -> bool:
    """Judge unless the run says no, the row is a negative test, or precheck gates it."""
    if run_config.options.get("no_judge"):
        return False
    if row.expect == "fail":
        return False
    judge_config = rubric.get("judge") or {}
    return precheck_passed or not judge_config.get("skip_on_precheck_failure")


def _row_entries(
    row, *, agent_id, run_config, ids, result=None, precheck_result=(None, None),
    verdict=None, rubric=None, signal=None,
) -> tuple[dict, dict]:
    """Build this row's run.json and grade.json entries, keyed by `row_id`."""
    precheck_passed, precheck_reason = precheck_result
    total, passed = _row_score(verdict, rubric)
    judge_config = (rubric or {}).get("judge") or {}
    common = {
        "dataset_run_id": ids["dataset_run_id"],
        "agent_run_id": ids["agent_run_id"],
        "row_id": row.row_id,
        "precheck_passed": precheck_passed,
        "precheck_reason": precheck_reason,
    }
    run_entry = {
        **common,
        "agent_id": agent_id,
        "industry": row.industry,
        "tags": list(row.tags),
        "expect": row.expect,
        "timestamp": _now(),
        "provider": run_config.agent_under_test.get("provider"),
        "model": run_config.agent_under_test.get("model"),
        "resolved_model_id": getattr(result, "resolved_model_id", None),
        "system_prompt": getattr(result, "system_prompt", ""),
        "system_prompt_hash": artifacts.compute_system_prompt_hash(
            getattr(result, "system_prompt", "") or ""
        ),
        "prompt": row.prompt,
        "response": getattr(result, "response", ""),
        "seed_files": sorted(getattr(result, "seed_files", None) or row.seed_files),
        "upstream_chain": list(row.upstream_chain),
        "skip_reason": row.skip_reason,
        "tokens_in": getattr(result, "tokens_in", 0),
        "tokens_out": getattr(result, "tokens_out", 0),
        "errored": bool(getattr(result, "errored", False)),
        "error_reason": getattr(result, "error_reason", None),
        "log_path": getattr(result, "log_path", None),
        # A verdict this stage declared but nothing downstream consumes.
        "signal": signal,
    }
    grade_entry = {
        **common,
        "judged": verdict is not None and not verdict.errored,
        "skipped_reason": row.skip_reason,
        "judge_provider": judge_config.get("provider"),
        "judge_model": judge_config.get("model"),
        "judge_resolved_model_id": getattr(verdict, "resolved_model_id", None),
        "judge_threshold": judge_config.get("threshold"),
        "sub_scores": getattr(verdict, "sub_scores", None) or None,
        # The judge's own per-dimension findings and any consistency caps they
        # triggered — what makes a capped score auditable in the reports.
        "dimension_weaknesses": getattr(verdict, "dimension_weaknesses", None) or {},
        "score_caps": getattr(verdict, "score_caps", None) or {},
        "evidence": getattr(verdict, "evidence", None) or {},
        "judge_tokens_in": getattr(verdict, "tokens_in", 0) or 0,
        "judge_tokens_out": getattr(verdict, "tokens_out", 0) or 0,
        "score": total,
        "passed": passed,
        "rationale": getattr(verdict, "rationale", ""),
        "strengths": list(getattr(verdict, "strengths", []) or []),
        "weaknesses": list(getattr(verdict, "weaknesses", []) or []),
        # Named for the JUDGE, not shared with run.json's `errored`. The same
        # key meaning two different failures on two files joined by row id is
        # what let a total judge failure read as a clean run.
        "judge_errored": bool(getattr(verdict, "errored", False)),
        "judge_error_reason": getattr(verdict, "error_reason", None),
    }
    return run_entry, grade_entry


def _extract_signal(config: dict | None, response: str) -> dict | None:
    """Lift a stage's declared verdict out of its own output.

    A stage can produce a judgement that nothing downstream reads —
    prototype-analyze's readiness verdict is consumed only by a human gate that
    does not exist here. Recording it is the difference between "the analyser
    said NEEDS REVISION" being visible and being thrown away.
    """
    if not config or not response:
        return None
    match = re.search(config["pattern"], response)
    if match is None:
        return {"name": config["name"], "value": None, "alert": False}
    value = match.group(1) if match.groups() else match.group(0)
    return {
        "name": config["name"],
        "value": value,
        "alert": value in (config.get("alert") or []),
    }


def _row_score(verdict, rubric) -> tuple[float | None, bool | None]:
    """The row's weighted total and pass flag — computed here, never by the judge."""
    if verdict is None or verdict.errored or not rubric:
        return None, None
    total = scoring.weighted_total(verdict.sub_scores, rubric.get("dimensions") or [])
    threshold = (rubric.get("judge") or {}).get("threshold")
    return total, None if threshold is None else total >= threshold


# ── stage artifacts ───────────────────────────────────────────────────────


def _stage_ids(run_dir, agent_id: str, *, dry_run: bool) -> dict:
    """The identifiers every artifact of this stage carries."""
    dataset_run_id = "(dry-run)" if run_dir is None else Path(run_dir).name
    token = _agent_token(agent_id)
    return {
        "dataset_run_id": dataset_run_id,
        "agent_token": token,
        "agent_run_id": f"{dataset_run_id}-{token}",
    }


def _take_system_prompt(runs: list[dict]) -> str:
    """Pop the composed prompt off every run entry, returning the one to capture.

    It is identical for every row of a stage, so it is written once to
    `prompts/` rather than repeated in each of run.json's entries.
    """
    prompts = [run.pop("system_prompt", "") for run in runs]
    return next((prompt for prompt in prompts if prompt), "")


def _stage_score(runs, grades, rubric, run_config, dataset, ids) -> dict:
    """This stage's score.json: the aggregates plus who produced them."""
    hashes = config.compute_hashes(run_config, rubric, dataset)
    hashes["judge_resolved_model_id"] = next(
        (grade["judge_resolved_model_id"] for grade in grades if grade["judge_resolved_model_id"]),
        None,
    )
    hashes["judge_pinned_model_id"] = (rubric.get("judge") or {}).get("model")
    summary = scoring.summarize_stage(runs, grades, rubric)
    return {
        **ids,
        "dataset_id": dataset["dataset_id"],
        "finished_at": _now(),
        "model_under_test": dict(run_config.agent_under_test),
        "judge": dict(rubric.get("judge") or {}),
        "hashes": hashes,
        **summary,
        "baseline": scoring.evaluate_baseline(summary, rubric.get("baseline") or {}, hashes),
    }


def _stage_output(
    runs: list[dict], dataset: dict, ids: dict, agent_id: str, *, include_negative: bool = False
) -> dict:
    """The dataset envelope this stage hands downstream, in `id` (dataset) keying.

    Errored rows and `expect: fail` rows are EXCLUDED: there is nothing to
    forward for the first, and a row meant to be rejected must never propagate —
    unless the run opted into `propagate_negative` to watch the chain digest it.
    """
    rows = []
    for run in runs:
        if run["errored"] or run["skip_reason"]:
            continue
        if run["expect"] == "fail" and not include_negative:
            continue
        rows.append(
            {
                "id": run["row_id"],
                "industry": run["industry"],
                "tags": run["tags"],
                "upstream_precheck_passed": run["precheck_passed"],
                "upstream_score": None,
                "prompt": run["response"],
            }
        )
    return {
        "dataset_id": dataset["dataset_id"],
        "description": f"Generated by {agent_id}. Each row's prompt is that row's response.",
        "source_agent": agent_id,
        **ids,
        "rows": rows,
    }


def _all_errored(runs: list[dict]) -> bool:
    """True when no row produced text to chain forward — the rest of the run is pointless."""
    return bool(runs) and all(run["errored"] for run in runs)


# ── run summary ───────────────────────────────────────────────────────────


def _open_run_folder(dataset_run_id: str, *, workflow_dir: Path, dry_run: bool, from_run):
    """The run folder for this run — `from_run` EXTENDS one rather than minting another.

    A dry run that is not extending an existing folder mints nothing: it writes
    no artifacts, so creating a folder would leave an empty one behind.
    """
    if dry_run and not from_run:
        return None
    return artifacts.run_folder(dataset_run_id, workflow_dir=workflow_dir)


def _open_summary(run_dir, run_config, workflow, dataset, dataset_run_id, selected, not_run) -> dict:
    """Load the extended run's summary, or start one; every stage listed up front."""
    summary = _read_summary(run_dir)
    stages = {stage["agent_id"]: stage for stage in summary.get("stages") or []}
    chosen = {stage["agent_id"] for stage in selected}
    summary.update(
        {
            "dataset_run_id": dataset_run_id,
            "dataset_id": dataset["dataset_id"],
            "workflow_id": workflow.get("workflow_id"),
            "run_id": run_config.run_id,
            "created_at": summary.get("created_at") or _now(),
            "row_count": len(dataset.get("rows") or []),
            "config": {"overrides": run_config.overrides},
            "stages": [
                _stage_summary_entry(stage, stages, selected=stage["agent_id"] in chosen)
                for stage in workflow["stages"]
            ],
            "not_run": [stage["agent_id"] for stage in not_run],
        }
    )
    return summary


def _read_summary(run_dir) -> dict:
    """The existing run_summary.json when extending a folder, else an empty one."""
    if run_dir is None:
        return {}
    try:
        return artifacts.read_run_summary(run_dir)
    except FileNotFoundError:
        return {}


def _stage_summary_entry(stage: dict, previous: dict, *, selected: bool) -> dict:
    """One stage's line in run_summary.json, carrying a previous run's result forward."""
    if not selected and stage["agent_id"] in previous:
        return previous[stage["agent_id"]]
    return {
        "agent_id": stage["agent_id"],
        "order": stage.get("order"),
        "declared_status": stage.get("status"),
        "status": "not_run",
    }


def _begin_stage(run_dir, summary: dict, agent_id: str) -> None:
    """Record `status: running` before dispatching, so a crash says where it died."""
    if run_dir is None:
        return
    _mark_stage(summary, agent_id, {"status": "running"})
    _write_summary(run_dir, summary, status="running")


def _end_stage(run_dir, summary: dict, result: dict) -> None:
    """Fold a finished stage into the summary and rewrite it, marking later stages stale."""
    if run_dir is None:
        return
    _mark_stage(summary, result["agent_id"], _summary_stage_fields(result))
    artifacts.mark_stale_after(summary, result["agent_id"])
    artifacts.append_stage_run(summary, _stage_run_entry(result))
    _write_summary(run_dir, summary, status="running")


def _mark_stage(summary: dict, agent_id: str, fields: dict) -> None:
    """Update one stage's entry in the summary, in place."""
    for stage in summary["stages"]:
        if stage["agent_id"] == agent_id:
            stage.update(fields)


def _summary_stage_fields(result: dict) -> dict:
    """The headline numbers a stage contributes to run_summary.json."""
    score = result["score"]
    stats = score["scores"]
    return {
        "status": result["status"],
        "agent_run_id": result["agent_run_id"],
        "precheck_pass_rate": score["precheck_pass_rate"],
        "negative_rows_correct": score.get("negative_rows_correct"),
        "average_precheck_passed": stats["average_precheck_passed"],
        "average_all": stats["average_all"],
        "average_clean_chain": stats["average_clean_chain"],
        "stddev": stats["stddev"],
        "distinct_score_count": stats["distinct_score_count"],
        "rubric_hash": score["hashes"]["rubric_hash"],
        "baseline_verdict": score["baseline"]["verdict"],
        "signals": score.get("signals") or {},
        "tokens_total": score["tokens"]["total"],
        "warnings": score["warnings"],
    }


def _stage_run_entry(result: dict) -> dict:
    """The append-only `stage_runs` record: which stage ran, when, and how it ended."""
    return {
        "agent_id": result["agent_id"],
        "agent_run_id": result["agent_run_id"],
        "status": result["status"],
        "at": _now(),
    }


def _row_index(dataset: dict, results: list[dict], stages: list[dict]) -> list[dict]:
    """Per-row view across stages — the cross-stage join the run folder exists for."""
    by_stage = {
        result["agent_id"]: {row["row_id"]: row for row in result["score"]["results"]}
        for result in results
    }
    index = []
    for row in dataset.get("rows") or []:
        cells = {}
        for stage in stages:
            found = by_stage.get(stage["agent_id"], {}).get(row["id"])
            cells[stage["agent_id"]] = (
                None
                if found is None
                else {"precheck_passed": found["precheck_passed"], "score": found["score"]}
            )
        index.append({"id": row["id"], "stages": cells})
    return index


def _terminal_status(results: list[dict], selected: list) -> str:
    """How the run ended: aborted on a dead stage, partial when a stage never ran."""
    if any(result["aborted"] for result in results):
        return "aborted"
    return "completed" if len(results) == len(selected) else "partial"


def _write_summary(run_dir, summary: dict, *, status: str) -> None:
    """Write run_summary.json at this point in the run — `running` means mid-stage."""
    if run_dir is None:
        return
    summary["status"] = status
    summary["finished_at"] = None if status == "running" else _now()
    artifacts.write_run_summary(run_dir, summary)


# ── dry run ───────────────────────────────────────────────────────────────


def _planned_inputs(
    stage: dict, dataset: dict, upstream_outputs, workflow_dir, *, propagate: bool = False
) -> tuple[list, str | None]:
    """Compose a dry run's inputs, surviving an adapter that needs real upstream text.

    A dry run chains stages on a synthetic stand-in response, so a stage whose
    adapter PARSES its upstream (prototype-build reads `## Task N:` headers out
    of the plan) cannot compose one. In a real run that is one row's problem and
    the row is skipped — but counting it as skipped HERE would quote a cheaper
    run than the one you are about to pay for. So the skip is undone for the
    estimate and stated as a note instead.
    """
    try:
        inputs = stage_input.build_stage_inputs(
            stage, dataset=dataset, upstream_outputs=upstream_outputs,
            config_dir=workflow_dir, propagate_expected_fail=propagate,
        )
    except Exception as error:  # noqa: BLE001 - a preview never fails on synthetic input
        rows = _rows_from_upstream(stage, dataset, upstream_outputs)
        return rows, f"input not composable from a dry-run stand-in: {error}"

    note = None
    composed = []
    for row in inputs:
        if row.skip_reason and row.skip_reason.startswith(ADAPTER_FAILURE_PREFIX):
            # Lead with the classification, not the exception: this note said
            # "could not be adapted …" first and "expected, nothing is wrong"
            # last, so it read as a failure until you got to the end of it.
            # This now means the upstream stage's `dry_run_sample` is wrong or
            # missing — NOT that previews cannot compose. That distinction is
            # the whole point: a note here is now actionable rather than noise.
            note = note or (
                "the upstream stage's `dry_run_sample` in workflow.yaml is missing or no "
                "longer matches what that agent emits, so this stage's input could not be "
                f"composed for the preview. The live run is unaffected. ({row.skip_reason})"
            )
            # StageInput is frozen on purpose, so this is a replacement, not a mutation.
            row = dataclasses.replace(
                row, skip_reason=None, prompt="(not composable in a dry run)"
            )
        composed.append(row)
    return composed, note


def _rows_from_upstream(stage: dict, dataset: dict, upstream_outputs) -> list:
    """Bare rows for a stage whose real composition could not run — counts only.

    The dispatch estimate stays correct (one row in, one row out) even though
    the prompt text could not be built.
    """
    sources = (stage.get("input") or {}).get("from") or []
    upstream = upstream_outputs.get(sources[0]) if sources else None
    row_ids = [row["id"] for row in (upstream or {}).get("rows", [])] or [
        row["id"] for row in dataset["rows"]
    ]
    return [
        stage_input.StageInput(row_id=row_id, prompt="(not composable in a dry run)")
        for row_id in row_ids
    ]


def _stage_plan(
    stage: dict, inputs: list, ids: dict, run_config, dataset: dict, rubric: dict,
    *, note: str | None = None,
) -> dict:
    """What this stage WOULD do: row counts, dispatch estimate, and the models it would use.

    Returns a stand-in output so a chained stage's prompts still compose, which
    is what makes a dry run of a full workflow report real per-stage row counts.
    """
    dispatched = [row for row in inputs if not row.skip_reason]
    judged = [row for row in dispatched if _should_judge(row, True, rubric, run_config)]
    agent_id = stage["agent_id"]
    plan = {
        "agent_id": agent_id,
        "order": stage.get("order"),
        "rows": len(inputs),
        "dispatches": len(dispatched),
        "judge_calls": len(judged),
        "skipped": [
            {
                "row_id": row.row_id,
                "reason": row.skip_reason,
                "by_design": row.skip_reason == stage_input.EXPECTED_FAIL_SKIP,
            }
            for row in inputs
            if row.skip_reason
        ],
        "model_under_test": dict(run_config.agent_under_test),
        "judge": dict(rubric.get("judge") or {}),
        "note": note,
    }
    return {
        "agent_id": agent_id,
        "order": stage.get("order"),
        "agent_run_id": ids["agent_run_id"],
        "status": "planned",
        "score": None,
        "plan": plan,
        "output": _planned_output(
            dispatched, dataset, ids, agent_id, stage.get("dry_run_sample")
        ),
        "aborted": False,
    }


def _planned_output(
    dispatched: list, dataset: dict, ids: dict, agent_id: str, sample: str | None = None
) -> dict:
    """A stand-in output envelope so a dry run can chain without dispatching.

    `sample` is the stage's declared `dry_run_sample` — real-shaped output for a
    stage whose text a downstream adapter PARSES. Without it, prototype-build's
    adapter reported a failure on every single preview, which is noise that
    trains you to ignore the notes block.
    """
    return {
        "dataset_id": dataset["dataset_id"],
        "description": f"(dry run) planned output of {agent_id}",
        "source_agent": agent_id,
        **ids,
        "rows": [
            {
                "id": row.row_id,
                "industry": row.industry,
                "tags": list(row.tags),
                "upstream_precheck_passed": True,
                "upstream_score": None,
                "prompt": sample
                or DRY_RUN_RESPONSE.format(agent_id=agent_id, row_id=row.row_id),
            }
            for row in dispatched
        ],
    }


def _not_run_reason(stage: dict, agents) -> str:
    """Why this stage is not in the run — the config, or the stage itself.

    Both used to print as the stage's declared status, so a fully onboarded
    stage left out by `agents: [x]` reported "not run (implemented)", which
    reads as a contradiction rather than an explanation.
    """
    if stage.get("status") != "implemented":
        return "not set up yet"
    if agents != "all":
        return "not chosen in this config"
    return "comes after a step that is not set up yet"


def _plan(run_config, dataset: dict, dataset_run_id: str, results: list[dict], not_run: list) -> dict:
    """The whole run's plan — what a `--dry-run` prints instead of spending tokens."""
    stages = [result["plan"] for result in results]
    return {
        "dry_run": True,
        "run_id": run_config.run_id,
        "workflow": run_config.workflow,
        "dataset_id": dataset["dataset_id"],
        "dataset_run_id": dataset_run_id,
        "row_count": len(dataset.get("rows") or []),
        "stages": stages,
        "not_run": [
            {
                "agent_id": stage["agent_id"],
                "declared_status": stage.get("status"),
                "reason": _not_run_reason(stage, run_config.agents),
            }
            for stage in not_run
        ],
        # The advise step is LIVE and spends: one call per stage that will be
        # judged. Left out of the estimate it would be spend the preview never
        # mentioned, which is the one thing a cost preview must not do.
        "dispatch_estimate": {
            "agent_calls": sum(stage["dispatches"] for stage in stages),
            "judge_calls": sum(stage["judge_calls"] for stage in stages),
            "advice_calls": _planned_advice_calls(run_config, stages),
            "total": sum(stage["dispatches"] + stage["judge_calls"] for stage in stages)
            + _planned_advice_calls(run_config, stages),
        },
    }


def _planned_advice_calls(run_config, stages: list[dict]) -> int:
    """How many advisor calls this run will make: one per stage it will judge."""
    if not run_config.options.get("advise", True) or run_config.options.get("no_judge"):
        return 0
    return sum(1 for stage in stages if stage.get("judge_calls"))


# ── small shared helpers ──────────────────────────────────────────────────


def _apply_judge_overrides(rubric: dict, run_config) -> dict:
    """Overlay the run config's judge settings onto the rubric's pinned block."""
    overrides = {key: value for key, value in run_config.judge.items() if value is not None}
    return {**rubric, "judge": {**(rubric.get("judge") or {}), **overrides}}


def _resolved_config(run_config, reference: str) -> dict:
    """The re-runnable snapshot: every merged value, in run-config shape."""
    resolved = asdict(run_config)
    resolved.pop("overrides")
    resolved["dataset"] = reference
    return resolved


def _agent_token(agent_id: str) -> str:
    """`prototype-specify` -> `prototype_specify`, the artifact file-name form."""
    return agent_id.replace("-", "_")


def _now() -> str:
    """UTC timestamp in the artifacts' `2026-07-29T08:31:58Z` form."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
