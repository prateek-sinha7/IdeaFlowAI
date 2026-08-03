"""Advise track: ingest a run's reports and propose edits to the agent prompt.

The improvement loop's last mile. A finished run holds everything needed to
say WHY an agent under-scored: the composed system prompt it really saw, the
judge's clustered weaknesses with row ids, the per-dimension aggregates, and
the code track's deterministic findings. This module hands all of that to a
model and asks for the one thing the reports stop short of: where the output
deviated from the prompt's intent, and a concrete delta — what to add, what to
remove, what to reword — with the strengths an edit must not lose.

LIVE: each advised stage is one model call (the judge model by default).
Advice is written to `reports/prompt_advice_<agent_token>.md`; nothing in the
run's artifacts is modified — advice is a proposal, never a grade.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from evals.grading import artifacts, config, render
from evals.grading.code import code_grader
from evals.grading.model import judge

# How many of the lowest-scoring rows are quoted to the advisor in full.
WORST_ROWS = 3
# Advice quality depends on the real prompt, but a prompt is bounded so one
# pathological stage cannot blow the context.
MAX_PROMPT_CHARS = 40_000
MAX_RESPONSE_EXCERPT = 1_500


class Deviation(BaseModel):
    """One place the agent's output drifted from what the prompt intended."""

    description: str = Field(description="What the agent did, versus what the prompt intended.")
    row_ids: list[str] = Field(default_factory=list, description="The rows showing it.")
    prompt_gap: str = Field(
        description="The specific prompt passage (or absence) that allowed this — "
        "quote it when it exists, say 'not covered' when it does not."
    )


class PromptEdit(BaseModel):
    """One concrete edit to the agent's prompt."""

    action: str = Field(description="One of: add, remove, modify.")
    section: str = Field(description="Where in the prompt this applies (heading or anchor text).")
    current_text: str = Field(
        default="", description="The verbatim prompt text to remove or modify; empty for add."
    )
    proposed_text: str = Field(
        default="", description="The exact replacement or addition; empty for remove."
    )
    reason: str = Field(description="Which observed deviation or weakness this fixes.")


class PromptAdvice(BaseModel):
    """The advisor's structured reply for one stage."""

    summary: str = Field(description="Two or three sentences: the prompt's main gap.")
    deviations: list[Deviation]
    edits: list[PromptEdit]
    keep: list[str] = Field(
        default_factory=list,
        description="Observed strengths the edits must not regress, as flat strings.",
    )


async def advise_run(
    dataset_run_id: str,
    *,
    workflow_name: str = "prototype",
    agents: list[str] | None = None,
    judge_overrides: dict | None = None,
    on_event=None,
) -> dict:
    """Advise every graded stage of one run folder (or the named subset)."""
    workflow = config.load_workflow(workflow_name)
    workflow_dir = Path(workflow["workflow_dir"])
    run_dir = artifacts.runs_root(workflow_dir) / dataset_run_id
    if not run_dir.is_dir():
        raise ValueError(
            f"no run folder '{dataset_run_id}' under {artifacts.runs_root(workflow_dir)}"
        )

    stages = _select_stages(run_dir, workflow, agents)
    results = []
    for stage in stages:
        result = await _advise_stage(
            stage, run_dir=run_dir, workflow_dir=workflow_dir,
            judge_overrides=judge_overrides or {}, on_event=on_event,
        )
        results.append(result)
    return {"dataset_run_id": dataset_run_id, "run_dir": str(run_dir), "stages": results}


def _select_stages(run_dir: Path, workflow: dict, agents: list[str] | None) -> list[dict]:
    """The stages with something to advise on: a score artifact in this folder."""
    known = {stage["agent_id"] for stage in workflow["stages"]}
    if agents:
        unknown = [agent for agent in agents if agent not in known]
        if unknown:
            raise ValueError(
                f"agents {unknown} are not stages of workflow "
                f"'{workflow.get('workflow_id')}' ({sorted(known)})"
            )
    selected = [
        stage
        for stage in workflow["stages"]
        if (not agents or stage["agent_id"] in set(agents))
        and artifacts.artifact_path(run_dir, _token(stage["agent_id"]), "score").exists()
    ]
    if not selected:
        raise ValueError(
            f"run folder '{run_dir.name}' contains no graded stage"
            + (f" among {agents}" if agents else "")
        )
    return selected


async def _advise_stage(
    stage: dict, *, run_dir: Path, workflow_dir: Path, judge_overrides: dict, on_event=None
) -> dict:
    """One stage: gather its evidence, ask the model, write the advice file."""
    agent_id = stage["agent_id"]
    token = _token(agent_id)
    _emit(on_event, {"event": "stage_start", "agent_id": agent_id, "rows": 1})

    rubric = config.load_rubric(workflow_dir, agent_id)
    judge_config = {**(rubric.get("judge") or {}), **_clean(judge_overrides)}
    evidence = _gather_evidence(run_dir, token)
    prompt = _build_advisor_prompt(agent_id, evidence)

    model = judge.resolve_judge_model(judge_config)
    structured = model.with_structured_output(PromptAdvice, include_raw=True)
    reply = await structured.ainvoke(prompt)
    parsed, error, tokens_in, tokens_out = judge._unpack_reply(reply)

    result = {
        "agent_id": agent_id,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "errored": False,
        "error_reason": None,
        "advice_path": None,
    }
    if error is not None or parsed is None:
        result["errored"] = True
        result["error_reason"] = error or "advisor returned no parsable structured output"
        _emit(on_event, {
            "event": "stage_done", "agent_id": agent_id, "status": "errored",
            "error_reason": result["error_reason"],
        })
        return result

    artifacts.reports_dir(run_dir)  # ensure reports/ exists before either write
    path = artifacts.advice_markdown_path(run_dir, token)
    path.write_text(_render_advice(agent_id, run_dir, parsed), encoding="utf-8")
    # The same advice, unrendered: markdown is for a reader, this is what
    # `apply-advice` applies. Written from one object so they cannot disagree.
    artifacts.write_advice_json(run_dir, token, parsed.model_dump())
    result["advice_path"] = str(path)
    result["edits"] = len(parsed.edits)
    result["deviations"] = len(parsed.deviations)
    # The done event carries the counts and the path: a progress line that says
    # only "advised" tells the reader nothing they could act on.
    _emit(on_event, {
        "event": "stage_done", "agent_id": agent_id, "status": "advised",
        "edits": result["edits"], "deviations": result["deviations"],
        "advice_path": result["advice_path"],
        "tokens_in": tokens_in, "tokens_out": tokens_out,
    })
    return result


# ── evidence gathering ────────────────────────────────────────────────────


def _gather_evidence(run_dir: Path, token: str) -> dict:
    """Everything the advisor reads, pulled once from the run folder."""
    score = artifacts.read_stage_artifact(run_dir, token, "score")
    grades = _read(run_dir, token, "grade")
    runs = _read(run_dir, token, "run")
    return {
        "system_prompt": _captured_prompt(run_dir, token),
        "score": score,
        "worst_rows": _worst_rows(score, grades, runs),
        "code": code_grader.read_findings(run_dir, token),
    }


def _worst_rows(score: dict, grades: list, runs: list) -> list[dict]:
    """The lowest-scoring rows with the judge's narrative and a response excerpt."""
    grades_by_id = {grade.get("row_id"): grade for grade in grades}
    runs_by_id = {run.get("row_id"): run for run in runs}
    scored = [row for row in score.get("results") or [] if row.get("score") is not None]
    worst = sorted(scored, key=lambda row: row["score"])[:WORST_ROWS]
    detailed = []
    for row in worst:
        grade = grades_by_id.get(row["row_id"]) or {}
        run = runs_by_id.get(row["row_id"]) or {}
        detailed.append({
            "row_id": row["row_id"],
            "score": row["score"],
            "brief": render.truncate(run.get("prompt"), limit=400),
            "response_excerpt": (run.get("response") or "")[:MAX_RESPONSE_EXCERPT],
            "rationale": grade.get("rationale") or "",
            "weaknesses": grade.get("weaknesses") or [],
            "evidence": grade.get("evidence") or {},
        })
    return detailed


# ── the advisor prompt ────────────────────────────────────────────────────


def _build_advisor_prompt(agent_id: str, evidence: dict) -> str:
    """Assemble the advisor's one-shot prompt from the gathered evidence."""
    score = evidence["score"]
    stats = score.get("scores") or {}
    dimension_lines = [
        f"- {name}: mean {render.number(stat.get('mean'))} "
        f"(min {render.number(stat.get('min'))}, max {render.number(stat.get('max'))})"
        for name, stat in (score.get("dimensions") or {}).items()
    ]
    weakness_lines = [
        f"- [{len(cluster.get('row_ids') or [])} row(s): "
        f"{', '.join(str(r) for r in cluster.get('row_ids') or [])}] {cluster.get('evidence')}"
        for cluster in score.get("recurring_weaknesses") or []
    ]
    strength_lines = [
        f"- [{len(cluster.get('row_ids') or [])} row(s)] {cluster.get('evidence')}"
        for cluster in score.get("recurring_strengths") or []
    ]
    worst_blocks = [
        (
            f"--- row {row['row_id']} (score {render.number(row['score'])}) ---\n"
            f"brief: {row['brief']}\n"
            f"judge rationale: {row['rationale']}\n"
            f"judge weaknesses: {'; '.join(row['weaknesses'])}\n"
            f"response excerpt:\n{row['response_excerpt']}\n"
        )
        for row in evidence["worst_rows"]
    ]
    return (
        "You are a prompt engineer improving an AI agent's system prompt, using "
        "the evidence from an automated grading run of that agent. Identify where "
        "the agent's OUTPUT deviated from the prompt's INTENT, decide what in the "
        "prompt caused or permitted each deviation, and propose a concrete prompt "
        "delta.\n\n"
        f"Agent under review: {agent_id}\n\n"
        "=== THE AGENT'S CURRENT SYSTEM PROMPT (verbatim, as dispatched) ===\n"
        f"{evidence['system_prompt'][:MAX_PROMPT_CHARS]}\n"
        "=== END SYSTEM PROMPT ===\n\n"
        "=== GRADING SUMMARY ===\n"
        f"average score: {render.number(stats.get('average_all'))} over "
        f"{(score.get('counts') or {}).get('judged', 0)} judged row(s); "
        f"stddev {render.number(stats.get('stddev'))}\n"
        "per-dimension:\n" + ("\n".join(dimension_lines) or "(none)") + "\n"
        "=== END SUMMARY ===\n\n"
        "=== RECURRING WEAKNESSES (judge criticisms clustered across rows) ===\n"
        + ("\n".join(weakness_lines) or "(none)") + "\n"
        "=== END WEAKNESSES ===\n\n"
        "=== RECURRING STRENGTHS (behaviour an edit must NOT lose) ===\n"
        + ("\n".join(strength_lines) or "(none)") + "\n"
        "=== END STRENGTHS ===\n\n"
        "=== WORST ROWS (judge narrative + response excerpts) ===\n"
        + ("\n".join(worst_blocks) or "(none)") + "\n"
        "=== END WORST ROWS ===\n\n"
        + _code_evidence_block(evidence.get("code")) +
        "Return structured advice:\n"
        "- `deviations`: each observed drift from the prompt's intent, with the "
        "row ids showing it and the prompt passage (quoted) that allowed it — or "
        "'not covered' when the prompt is silent.\n"
        "- `edits`: the prompt delta. Each edit has `action` (add / remove / "
        "modify), `section` (the heading or anchor text locating it), "
        "`current_text` (verbatim, for remove/modify), `proposed_text` (the exact "
        "new wording, for add/modify) and `reason` (the deviation it fixes). "
        "Propose the SMALLEST set of edits that addresses the recurring "
        "weaknesses; do not rewrite the prompt wholesale.\n"
        "- `keep`: the strengths the edits must not regress.\n"
        "- `summary`: two or three sentences naming the prompt's main gap."
    )


def _code_evidence_block(code: dict | None) -> str:
    """The code track's findings for this stage, when it ran — else nothing."""
    if not code or not code.get("findings"):
        return ""
    lines = []
    for row_id, finding in code["findings"].items():
        problems = list(finding.get("issues") or [])
        rendered = finding.get("render") or {}
        problems += rendered.get("console_errors") or []
        problems += rendered.get("page_errors") or []
        problems += [
            f"dead nav {nav.get('href')}"
            for nav in rendered.get("nav_results") or []
            if not nav.get("ok")
        ]
        interactions = finding.get("interactions") or {}
        problems += [
            f"{failure.get('action')} {failure.get('target')} raised: "
            f"{'; '.join(failure.get('errors') or [])}"
            for failure in interactions.get("failures") or []
        ]
        if problems:
            lines.append(f"- {row_id} (code score {render.number(finding.get('code_score'))}):")
            lines.extend(f"  - {render.truncate(problem)}" for problem in problems)
    if not lines:
        return ""
    return (
        "=== DETERMINISTIC CODE FINDINGS (verified in a real browser — treat as "
        "ground truth, not opinion) ===\n" + "\n".join(lines) +
        "\n=== END CODE FINDINGS ===\n\n"
    )


# ── rendering ─────────────────────────────────────────────────────────────


def _render_advice(agent_id: str, run_dir: Path, advice: PromptAdvice) -> str:
    """The advice as one markdown page next to the run's other reports."""
    lines = [
        f"# Prompt advice — `{agent_id}`",
        "",
        f"Run `{run_dir.name}` · generated {_now()} · "
        "a **proposal** derived from this run's evidence, not a grade.",
        "",
        "## Summary",
        "",
        advice.summary,
        "",
        "## Deviations from prompt intent",
        "",
    ]
    if advice.deviations:
        rows = [
            [
                render.truncate(deviation.description, limit=220),
                ", ".join(f"`{row_id}`" for row_id in deviation.row_ids) or render.DASH,
                render.truncate(deviation.prompt_gap, limit=220),
            ]
            for deviation in advice.deviations
        ]
        lines.extend(render.md_table(["deviation", "rows", "prompt gap"], rows, "lll"))
    else:
        lines.append("(none reported)")
    lines.extend(["", "## Proposed prompt delta", ""])
    if not advice.edits:
        lines.append("(no edits proposed)")
    for index, edit in enumerate(advice.edits, start=1):
        lines.append(f"### {index}. {edit.action.upper()} — {edit.section}")
        lines.append("")
        lines.append(f"**Why:** {edit.reason}")
        lines.append("")
        if edit.current_text:
            lines.extend(["**Remove / replace:**", "", "```", edit.current_text, "```", ""])
        if edit.proposed_text:
            lines.extend(["**With:**", "", "```", edit.proposed_text, "```", ""])
    if advice.keep:
        lines.extend(["## Do not regress", ""])
        lines.extend(f"- {item}" for item in advice.keep)
        lines.append("")
    lines.extend([
        "---",
        "",
        "Apply these edits (free — archives the current prompt to `AGENT.vN.md` first):",
        "",
        "```bash",
        f"./evals/grading/grade.sh apply-advice {run_dir.name} --agent {agent_id}",
        "```",
        "",
        "Then verify the change:",
        "",
        "```bash",
        f"./evals/grading/grade.sh run {run_dir}/grade_config.resolved.yaml"
        f" --agents {agent_id} --from-run {run_dir.name} --replace",
        "```",
        "",
        f"then `./evals/grading/grade.sh history {agent_id}` to see the prompt "
        f"version's effect across runs. To undo: "
        f"`./evals/grading/grade.sh revert {agent_id}`.",
    ])
    return "\n".join(lines).rstrip() + "\n"


# ── small helpers ─────────────────────────────────────────────────────────


def _clean(overrides: dict) -> dict:
    """Only the judge keys actually set — an unset flag is not an override."""
    return {
        key: value
        for key, value in (overrides or {}).items()
        if key in ("provider", "model", "threshold") and value is not None
    }


def _captured_prompt(run_dir: Path, token: str) -> str:
    """The composed prompt the agent really saw; empty when never captured."""
    try:
        return artifacts.read_system_prompt(run_dir, token)
    except FileNotFoundError:
        return "(system prompt was not captured for this run)"


def _read(run_dir: Path, token: str, kind: str) -> list:
    """One artifact list, or empty when this run never wrote that kind."""
    try:
        return artifacts.read_stage_artifact(run_dir, token, kind) or []
    except FileNotFoundError:
        return []


def _emit(on_event, event: dict) -> None:
    """Hand one progress event to the caller, never letting it break the advice."""
    if on_event is None:
        return
    try:
        on_event(event)
    except Exception:  # noqa: BLE001 - progress reporting is never load-bearing
        pass


def _token(agent_id: str) -> str:
    """`prototype-specify` -> `prototype_specify`, the artifact file-name form."""
    return agent_id.replace("-", "_")


def _now() -> str:
    """UTC timestamp in the artifacts' `2026-07-29T08:31:58Z` form."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
