"""Render a finished run folder as one readable REPORT.md.

Reads only what the run already wrote to disk — run_summary plus each stage's
score/grade/run artifacts — so it can be regenerated at any time and never
needs a model. Every table here answers "which prompt do I fix next".
"""

from __future__ import annotations

from pathlib import Path

from evals.grading import artifacts, render, scoring

REPORT_NAME = "REPORT.md"

# Every row of a markdown table is padded to these, so the raw file is readable
# in a plain editor and not only after a renderer gets hold of it.
DASH = render.DASH


def write_report(run_dir: Path) -> Path:
    """Render the run folder to `REPORT.md` inside it and return the path."""
    run_dir = Path(run_dir)
    summary = artifacts.read_run_summary(run_dir)
    text = render_report(run_dir, summary)
    path = run_dir / REPORT_NAME
    path.write_text(text, encoding="utf-8")
    return path


def render_report(run_dir: Path, summary: dict) -> str:
    """Build the whole markdown document for one run."""
    blocks = [
        _header(run_dir, summary),
        _overview_table(summary),
        _not_run_section(summary),
    ]
    for stage in summary.get("stages") or []:
        if not _has_score(run_dir, stage):
            continue
        blocks.append(_stage_section(run_dir, stage))
    blocks.append(_reproduce_section(run_dir))
    return "\n".join(block for block in blocks if block).rstrip() + "\n"


# ── header and overview ───────────────────────────────────────────────────


def _header(run_dir: Path, summary: dict) -> str:
    """Title plus the run's identity and the settings that produced it."""
    config = artifacts.read_resolved_config(run_dir) if _has_config(run_dir) else {}
    under_test = config.get("agent_under_test") or {}
    judge = config.get("judge") or {}
    options = config.get("options") or {}
    lines = [
        f"# Grading run — {summary.get('dataset_run_id', run_dir.name)}",
        "",
        f"**Status:** `{summary.get('status', 'unknown')}` · "
        f"**Started:** {summary.get('created_at', DASH)} · "
        f"**Finished:** {summary.get('finished_at') or DASH}",
        "",
        "| | |",
        "|---|---|",
        f"| config `run_id` | `{summary.get('run_id', DASH)}` |",
        f"| workflow | `{summary.get('workflow_id', DASH)}` |",
        f"| dataset | `{summary.get('dataset_id', DASH)}` ({summary.get('row_count', DASH)} rows) |",
        f"| agent under test | {_model_code(under_test)} |",
        f"| judge | {_model_code(judge)} |",
        f"| concurrency / repeats | {options.get('concurrency', DASH)} / "
        f"{options.get('repeats', DASH)} |",
        f"| judging | {'DISABLED (`no_judge`)' if options.get('no_judge') else 'enabled'} |",
    ]
    overrides = (summary.get("config") or {}).get("overrides") or {}
    if overrides:
        listed = ", ".join(f"`{key}={value}`" for key, value in sorted(overrides.items()))
        lines.append(f"| CLI overrides | {listed} |")
        lines.append("")
        lines.append(
            "> ⚠️ This run's flags diverged from its config file, so re-running that "
            "config alone will **not** reproduce it."
        )
    lines.append("")
    return "\n".join(lines)


def _overview_table(summary: dict) -> str:
    """One line per stage that ran — the headline numbers, side by side."""
    stages = [
        stage for stage in summary.get("stages") or []
        if stage.get("status") not in (None, "not_run")
    ]
    if not stages:
        return ""
    # Scores use render.score and rates use render.number, exactly as the
    # terminal does — the two views must never disagree about one number.
    rows = [
        [
            f"`{stage.get('agent_id')}`",
            stage.get("status"),
            render.number(stage.get("precheck_pass_rate")),
            render.negative(stage.get("negative_rows_correct")),
            render.score(stage.get("average_all")),
            render.score(stage.get("average_precheck_passed")),
            render.score(stage.get("stddev")),
            stage.get("distinct_score_count", DASH),
            stage.get("baseline_verdict", DASH),
        ]
        for stage in stages
    ]
    headers = ["stage", "status", "precheck", "negative", "avg(all)", "avg(pass)",
               "stddev", "distinct", "baseline"]
    return "\n".join(
        ["## Overview", "", *render.md_table(headers, rows, "llrrrrrrl"), ""]
    )


def _not_run_section(summary: dict) -> str:
    """Name the stages that never ran, so an empty report is never mysterious."""
    not_run = summary.get("not_run") or []
    if not not_run:
        return ""
    listed = ", ".join(f"`{agent_id}`" for agent_id in not_run)
    return f"**Not run:** {listed}\n"


# ── one stage ─────────────────────────────────────────────────────────────


def _stage_section(run_dir: Path, stage: dict) -> str:
    """Everything known about one stage: aggregates, rows, and judge detail."""
    token = str(stage["agent_id"]).replace("-", "_")
    score = artifacts.read_stage_artifact(run_dir, token, "score")
    grades = _read(run_dir, token, "grade")
    runs = _read(run_dir, token, "run")
    return "\n".join(
        block
        for block in (
            f"## `{stage['agent_id']}`\n",
            _identity_table(score, grades),
            _warnings_block(score),
            _baseline_block(score),
            _tokens_table(score.get("tokens") or {}),
            _dimensions_table(score.get("dimensions") or {}),
            _rows_table(score, grades),
            _weaknesses_block(score.get("recurring_weaknesses") or []),
            _row_detail_block(grades, runs),
        )
        if block
    )


def _identity_table(score: dict, grades: list) -> str:
    """The models and hashes that make this stage comparable to another run.

    The judge-error count falls back to the grade artifacts, so a run recorded
    before that count existed still reports its failures here rather than
    claiming zero while the rows table below says otherwise.
    """
    hashes = score.get("hashes") or {}
    counts = score.get("counts") or {}
    judge_errors = counts.get("judge_errored")
    if judge_errors is None:
        judge_errors = sum(1 for grade in grades if scoring.judge_errored(grade))
    return "\n".join(
        [
            "| | |",
            "|---|---|",
            f"| rows | {counts.get('rows', DASH)} dispatched {counts.get('dispatched', DASH)}, "
            f"judged {counts.get('judged', 0)}, judge errors {judge_errors} |",
            f"| model under test | {_model_code(score.get('model_under_test') or {})} |",
            f"| judge | {_model_code(score.get('judge') or {})} "
            f"→ resolved `{hashes.get('judge_resolved_model_id', DASH)}` |",
            f"| rubric hash | `{render.short_hash(hashes.get('rubric_hash'))}` |",
            f"| dataset hash | `{render.short_hash(hashes.get('dataset_hash'))}` |",
            f"| system prompt | `{render.short_hash(_first_prompt_hash(score))}` |",
            "",
        ]
    )


def _warnings_block(score: dict) -> str:
    """Warnings first and unmissable — they say which numbers not to trust."""
    warnings = score.get("warnings") or []
    if not warnings:
        return ""
    lines = ["### ⚠️ Warnings", ""]
    lines.extend(f"- {warning}" for warning in warnings)
    lines.append("")
    return "\n".join(lines)


def _baseline_block(score: dict) -> str:
    """The pass/fail verdict and, when it is not a pass, exactly why."""
    baseline = score.get("baseline") or {}
    if not baseline:
        return ""
    lines = [f"**Baseline:** `{baseline.get('verdict', DASH)}`", ""]
    for failure in baseline.get("failures") or []:
        lines.append(f"- {failure}")
    if baseline.get("failures"):
        lines.append("")
    return "\n".join(lines)


def _tokens_table(tokens: dict) -> str:
    """What the stage cost, split by who spent it.

    A run recorded before the split has no breakdown; its flat totals were
    agent-only, so attribute them there rather than printing a zero row that
    contradicts the total beside it.
    """
    if not tokens:
        return ""
    agent = tokens.get("agent") or {
        "in": tokens.get("in", 0), "out": tokens.get("out", 0), "total": tokens.get("total", 0)
    }
    judge = tokens.get("judge") or {"in": 0, "out": 0, "total": 0}
    return "\n".join(
        [
            "### Tokens",
            "",
            "| spender | in | out | total |",
            "|---|---:|---:|---:|",
            f"| agent | {agent.get('in', 0)} | {agent.get('out', 0)} | {agent.get('total', 0)} |",
            f"| judge | {judge.get('in', 0)} | {judge.get('out', 0)} | {judge.get('total', 0)} |",
            f"| **all** | **{tokens.get('in', 0)}** | **{tokens.get('out', 0)}** "
            f"| **{tokens.get('total', 0)}** |",
            "",
        ]
    )


def _dimensions_table(dimensions: dict) -> str:
    """Per-dimension aggregates — which paragraph of the AGENT.md is weak."""
    if not dimensions:
        return ""
    lines = [
        "### Dimensions",
        "",
        "| dimension | n | mean | median | stddev | min | max |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, stats in dimensions.items():
        lines.append(
            f"| `{name}` | {stats.get('count', 0)} | {render.number(stats.get('mean'))} "
            f"| {render.number(stats.get('median'))} | {render.number(stats.get('stddev'))} "
            f"| {render.number(stats.get('min'))} | {render.number(stats.get('max'))} |"
        )
    lines.append("")
    return "\n".join(lines)


def _rows_table(score: dict, grades: list) -> str:
    """Every row on one line, with its per-dimension sub-scores spread out."""
    results = score.get("results") or []
    if not results:
        return ""
    dimension_ids = list((score.get("dimensions") or {}).keys())
    grades_by_id = {_row_id(grade): grade for grade in grades}
    headers = ["row", "expect", "precheck", "score", "passed"]
    headers.extend(f"`{name}`" for name in dimension_ids)
    headers.append("note")
    lines = [
        "### Rows",
        "",
        "| " + " | ".join(headers) + " |",
        "|" + "---|" * 3 + "---:|" + "---|" + "---:|" * len(dimension_ids) + "---|",
    ]
    for row in results:
        grade = grades_by_id.get(row.get("row_id")) or {}
        sub_scores = grade.get("sub_scores") or {}
        cells = [
            f"`{row.get('row_id')}`",
            str(row.get("expect", DASH)),
            render.flag(row.get("precheck_passed")),
            render.number(row.get("score")),
            render.flag(row.get("passed")),
        ]
        cells.extend(str(sub_scores.get(name, DASH)) for name in dimension_ids)
        cells.append(_row_note(row, grade))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def _row_note(row: dict, grade: dict) -> str:
    """Why a row has no score: it errored, was skipped, or the judge failed."""
    if row.get("errored"):
        return "dispatch errored"
    if grade.get("skipped_reason"):
        return f"skipped — {grade['skipped_reason']}"
    if scoring.judge_errored(grade):
        return f"**judge failed** — {render.truncate(scoring.judge_error_reason(grade))}"
    if row.get("expect") == "fail":
        return "negative test"
    return ""


def _weaknesses_block(clusters: list) -> str:
    """The judge's criticisms clustered across rows — the prompt-fix shortlist."""
    if not clusters:
        return ""
    rows = []
    for cluster in clusters:
        row_ids = cluster.get("row_ids") or []
        rows.append([
            len(row_ids),
            render.truncate(cluster.get("evidence")),
            ", ".join(f"`{row_id}`" for row_id in row_ids),
        ])
    return "\n".join(
        ["### Recurring weaknesses", "",
         *render.md_table(["rows", "weakness", "affected"], rows, "rll"), ""]
    )


def _row_detail_block(grades: list, runs: list) -> str:
    """Per-row judge narrative, worst first — the part you actually read."""
    judged = [grade for grade in grades if grade.get("judged") or scoring.judge_errored(grade)]
    if not judged:
        return ""
    prompts = {_row_id(run): run.get("prompt", "") for run in runs}
    judged.sort(key=lambda grade: (grade.get("score") is None, grade.get("score") or 0))
    lines = ["### Row detail", ""]
    for grade in judged:
        row_id = _row_id(grade)
        lines.append(f"<details><summary><b>{row_id}</b> — {_detail_summary(grade)}</summary>\n")
        lines.append(f"**Brief:** {render.truncate(prompts.get(row_id), limit=400)}\n")
        if scoring.judge_error_reason(grade):
            lines.append(f"**Judge error:** `{render.truncate(scoring.judge_error_reason(grade))}`\n")
        if grade.get("precheck_reason"):
            lines.append(f"**Precheck:** {grade['precheck_reason']}\n")
        if grade.get("rationale"):
            lines.append(f"**Rationale:** {grade['rationale']}\n")
        lines.extend(_bullets("Strengths", grade.get("strengths")))
        lines.extend(_bullets("Weaknesses", grade.get("weaknesses")))
        lines.extend(_evidence_lines(grade.get("evidence") or {}))
        lines.append("</details>\n")
    return "\n".join(lines)


def _detail_summary(grade: dict) -> str:
    """The one-line headline on a collapsed row-detail block."""
    if scoring.judge_errored(grade):
        return "judge failed"
    score = grade.get("score")
    return f"score {render.number(score)}" if score is not None else "not scored"


def _bullets(title: str, items) -> list[str]:
    """A titled bullet list, or nothing when there is nothing to list."""
    if not items:
        return []
    return [f"**{title}:**", "", *[f"- {item}" for item in items], ""]


def _evidence_lines(evidence: dict) -> list[str]:
    """The judge's quoted evidence, per dimension."""
    if not evidence:
        return []
    lines = ["**Evidence:**", ""]
    lines.extend(f"- `{name}` — {quote}" for name, quote in evidence.items())
    lines.append("")
    return lines


def _reproduce_section(run_dir: Path) -> str:
    """The exact command that re-runs this run's resolved spec."""
    return "\n".join(
        [
            "---",
            "",
            "## Reproduce",
            "",
            "```bash",
            f"./evals/grading/grade.sh run {run_dir}/grade_config.resolved.yaml",
            "```",
            "",
            "The resolved config is the run's own frozen settings, so this stays exact even "
            "if the config file in `configs/` has changed since.",
        ]
    )


# ── small helpers ─────────────────────────────────────────────────────────


def _model_code(spec) -> str:
    """`provider/model` as inline code — markdown's own wrapper on render's label."""
    label = render.model_label(spec)
    return label if label == DASH else f"`{label}`"


def _has_score(run_dir: Path, stage: dict) -> bool:
    """Whether this stage actually wrote a score artifact to read."""
    token = str(stage.get("agent_id", "")).replace("-", "_")
    return bool(token) and artifacts.artifact_path(run_dir, token, "score").exists()


def _has_config(run_dir: Path) -> bool:
    """Whether the resolved config snapshot exists — it does for any real run."""
    return (Path(run_dir) / "grade_config.resolved.yaml").exists()


def _read(run_dir: Path, token: str, kind: str) -> list:
    """One artifact list, or empty when this run never wrote that kind."""
    try:
        return artifacts.read_stage_artifact(run_dir, token, kind) or []
    except FileNotFoundError:
        return []


def _row_id(entry: dict) -> str:
    """The join key of a run or grade entry, tolerating either id field name."""
    return entry.get("row_id") or entry.get("scenario_id") or entry.get("id") or ""


def _first_prompt_hash(score: dict) -> str | None:
    """The system-prompt hash this stage graded, when the score carries one."""
    return (score.get("hashes") or {}).get("system_prompt_hash")






