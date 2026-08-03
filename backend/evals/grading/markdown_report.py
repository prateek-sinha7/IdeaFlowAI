"""Render a finished run folder as the `reports/` document set.

Reads only what the run already wrote to disk — run_summary plus each stage's
score/grade/run artifacts (and the code track's findings when it ran) — so it
can be regenerated at any time and never needs a model.

The set is layered by how much the reader wants to know:

- `reports/report.md` — the top level: one score per phase, the clustered
  strengths and weaknesses across the whole run, and the command that
  re-judges it without re-generating anything.
- `reports/<agent_token>_report.md` — one phase in full: spread statistics,
  per-dimension aggregates, every row's sub-scores, and the judge's narrative.
- `reports/code_report.md` — the deterministic code track's findings, when it ran.
"""

from __future__ import annotations

from pathlib import Path

from evals.grading import artifacts, grades, render
from evals.grading.code import code_grader
from evals.grading.model import scoring

TOP_REPORT_NAME = "report.md"
CODE_REPORT_NAME = "code_report.md"

DASH = render.DASH

# The grade arithmetic lives in `grades` so the HTML dashboard can import it
# without importing this module. Re-exported here because every existing
# caller and test reaches for it at this path.
GRADE_BANDS = grades.GRADE_BANDS
FAIL_GRADE = grades.FAIL_GRADE
letter_grade = grades.letter_grade
compute_overall = grades.compute_overall
_cell_value = grades.cell_value


def write_report(run_dir: Path) -> Path:
    """Render the whole `reports/` set for one run and return the top-level path."""
    run_dir = Path(run_dir)
    summary = artifacts.read_run_summary(run_dir)
    reports = artifacts.reports_dir(run_dir)

    stages = [
        stage for stage in summary.get("stages") or [] if _has_score(run_dir, stage)
    ]
    for stage in stages:
        token = _token(stage)
        path = reports / f"{token}_report.md"
        path.write_text(_stage_report(run_dir, stage, summary), encoding="utf-8")

    code_stages = _code_findings(run_dir, stages)
    if code_stages:
        (reports / CODE_REPORT_NAME).write_text(
            _code_report(summary, code_stages), encoding="utf-8"
        )

    top = reports / TOP_REPORT_NAME
    top.write_text(_top_report(run_dir, summary, stages, code_stages), encoding="utf-8")

    # The HTML dashboard is regenerated from the same artifacts, here rather
    # than at each caller, so a caller added later cannot silently skip it.
    # Imported at call time: `site` imports this module's siblings, and this
    # keeps the dependency one-directional at import time.
    from evals.grading.site import builder

    builder.rebuild_for_run(run_dir)
    return top


# ── the top-level report ──────────────────────────────────────────────────


def _top_report(run_dir: Path, summary: dict, stages: list, code_stages: dict) -> str:
    """The whole run on one page: phase scores, strengths, weaknesses, rejudge."""
    blocks = [
        _header(run_dir, summary),
        _phase_table(run_dir, stages, code_stages),
        _not_run_section(summary),
        _signals_section(stages),
        _narrative_section(run_dir, stages, "recurring_strengths", "Strengths"),
        _narrative_section(run_dir, stages, "recurring_weaknesses", "Weaknesses"),
        _phase_links(stages, code_stages, artifacts.reports_dir(run_dir)),
        _rejudge_section(run_dir),
    ]
    return "\n".join(block for block in blocks if block).rstrip() + "\n"


def _header(run_dir: Path, summary: dict) -> str:
    """Title plus the run's identity and the settings that produced it."""
    config = artifacts.read_resolved_config(run_dir) if _has_config(run_dir) else {}
    under_test = config.get("agent_under_test") or {}
    judge = config.get("judge") or {}
    options = config.get("options") or {}
    lines = [
        f"# Grading run — {summary.get('dataset_run_id', run_dir.name)}",
        "",
        *_grade_lines(run_dir),
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


def _grade_lines(run_dir: Path) -> list[str]:
    """The one-line answer at the top: the blended score and its letter grade."""
    overall = compute_overall(run_dir)
    if overall is None:
        return []
    failed = overall["failed_cells"]
    detail = (
        f"judge and code blended over {render.plural(overall['counted'], 'graded cell')}"
        + (f", of which **{failed} failed outright** (precheck fail, error, or a "
           "broken chain — each scores 0)" if failed else ", none failed")
    )
    return [
        f"## Grade: {overall['grade']} — {overall['score']:.1f} / 100",
        "",
        f"> {detail}.",
        "> Scale: A++ ≥97 · A+ ≥93 · A ≥90 · B ≥80 · C ≥70 · D ≥60 · E ≥50 · **F <50 = fail**.",
        "",
    ]


def _phase_table(run_dir: Path, stages: list, code_stages: dict) -> str:
    """One line per phase, ending in the column the headline grade averages.

    `judge` and `code` are what each track measured; `effective` is the grade
    arithmetic made visible — judge blended with code per row, a failed row
    counting 0 — and the **overall** footer row is the mean of every phase's
    cells, i.e. exactly the headline number. Spread statistics live in the
    phase reports.
    """
    if not stages:
        return ""
    overall = compute_overall(run_dir) or {}
    per_stage = overall.get("stages") or {}
    rows = []
    for stage in stages:
        agent_id = stage.get("agent_id")
        # The score ARTIFACT is the source of truth; summaries written by older
        # versions carried nulls where the artifact has the real averages.
        score = _stage_score(run_dir, stage)
        stats = score.get("scores") or {}
        judge_avg = (
            stats.get("average_all")
            if stats.get("average_all") is not None
            else stats.get("average_clean_chain")
        )
        code_avg = (code_stages.get(agent_id) or {}).get("average_code_score")
        effective = (per_stage.get(agent_id) or {}).get("effective")
        failed = (per_stage.get(agent_id) or {}).get("failed") or 0
        counts = score.get("counts") or {}
        rows.append([
            f"[`{agent_id}`]({_token(stage)}_report.md)",
            counts.get("rows", DASH),
            counts.get("judged", 0),
            render.score(judge_avg),
            render.score(code_avg),
            render.score(effective) + (f" ({failed} failed)" if failed else ""),
            stage.get("baseline_verdict", DASH),
        ])
    if overall:
        rows.append([
            f"**overall — grade {overall['grade']}**",
            overall["counted"],
            DASH, DASH, DASH,
            f"**{overall['score']:.1f}**",
            DASH,
        ])
    headers = ["phase", "rows", "graded", "judge", "code", "effective", "baseline"]
    lines = ["## Phase scores", "", *render.md_table(headers, rows, "lrrrrrl"), ""]
    lines.append(
        "`effective` = judge score blended with code score per row (0.7 / 0.3, "
        "whichever exists when only one does); a row that failed — precheck fail, "
        "error, or a chain broken upstream — counts **0**. The **overall** row is "
        "the mean of every phase's rows, and is the headline grade above."
    )
    lines.append("")
    return "\n".join(lines)


def _stage_score(run_dir: Path, stage: dict) -> dict:
    """One stage's stored score artifact, or empty when it never wrote one."""
    return grades.stage_score(run_dir, stage)


def _not_run_section(summary: dict) -> str:
    """Name the stages that never ran, so a short table is never mysterious."""
    not_run = summary.get("not_run") or []
    if not not_run:
        return ""
    listed = ", ".join(f"`{agent_id}`" for agent_id in not_run)
    return f"**Not run:** {listed}\n"


def _signals_section(stages: list) -> str:
    """Any verdict a stage declared that nothing downstream consumes."""
    lines = []
    for stage in stages:
        signals = stage.get("signals") or {}
        if not signals:
            continue
        counts = ", ".join(f"{count}× {value}" for value, count in signals["counts"].items())
        lines.append(f"- `{stage.get('agent_id')}` says: {counts}")
        for row_id in signals.get("alert_rows") or []:
            lines.append(f"  - ⚠️ `{row_id}` judged NOT ready — the run proceeded anyway")
    if not lines:
        return ""
    return "\n".join(["## Signals", "", *lines, ""])


def _narrative_section(run_dir: Path, stages: list, key: str, title: str) -> str:
    """One clustered narrative table across every phase — strengths or weaknesses.

    Columns answer the improvement loop's questions in order: which phase's
    prompt, how widespread (rows affected), what exactly, and which rows to
    open to see it.
    """
    rows = []
    for stage in stages:
        try:
            score = artifacts.read_stage_artifact(run_dir, _token(stage), "score")
        except FileNotFoundError:
            continue
        for cluster in score.get(key) or []:
            row_ids = cluster.get("row_ids") or []
            rows.append([
                f"`{stage.get('agent_id')}`",
                len(row_ids),
                render.truncate(cluster.get("evidence"), limit=220),
                ", ".join(f"`{row_id}`" for row_id in row_ids),
            ])
    if not rows:
        return ""
    # Most widespread first, across phases — a weakness on every row of one
    # phase outranks a one-row nitpick on another.
    rows.sort(key=lambda row: -row[1])
    headers = ["phase", "rows affected", "description", "rows"]
    return "\n".join([f"## {title}", "", *render.md_table(headers, rows, "lrll"), ""])


def _phase_links(stages: list, code_stages: dict, reports: Path | None = None) -> str:
    """Where the detail lives — one line per phase report plus the code report.

    Prompt advice is listed only where the file exists: it is written by the
    advise step of the run, so an older folder (or a `--no-advise` run) links
    nothing rather than linking a 404.
    """
    if not stages:
        return ""
    lines = ["## Phase reports", ""]
    lines.extend(
        f"- [`{stage.get('agent_id')}`]({_token(stage)}_report.md)" for stage in stages
    )
    if code_stages:
        lines.append(f"- [code track]({CODE_REPORT_NAME})")
    advice = [
        f"- [`{stage.get('agent_id')}`](prompt_advice_{_token(stage)}.md)"
        for stage in stages
        if reports is not None and (reports / f"prompt_advice_{_token(stage)}.md").exists()
    ]
    if advice:
        lines.extend([
            "",
            "### Prompt advice",
            "",
            "Proposed edits to each agent's prompt, derived from this run's evidence — "
            "a proposal, never a grade.",
            "",
            *advice,
        ])
    lines.append("")
    return "\n".join(lines)


def _rejudge_section(run_dir: Path) -> str:
    """The command that re-grades this run's stored outputs without re-generating them."""
    return "\n".join(
        [
            "---",
            "",
            "## Rejudge this run",
            "",
            "Re-score every stored response with the judge — the same run, minus the "
            "generation, so nothing is dispatched to an agent and judge tokens are the "
            "only spend. This report is regenerated in place; the superseded artifacts "
            "are kept under `artifacts/superseded/`.",
            "",
            "```bash",
            f"./evals/grading/grade.sh rejudge {run_dir.name}",
            "```",
            "",
            "To re-run the deterministic code checks (free):",
            "",
            "```bash",
            f"./evals/grading/grade.sh code {run_dir.name}",
            "```",
            "",
            "The full generation is reproducible from the run's own frozen settings:",
            "",
            "```bash",
            f"./evals/grading/grade.sh run {run_dir}/grade_config.resolved.yaml",
            "```",
        ]
    )


# ── one phase's report ────────────────────────────────────────────────────


def _stage_report(run_dir: Path, stage: dict, summary: dict) -> str:
    """Everything known about one phase: spread, dimensions, rows, judge detail."""
    token = _token(stage)
    score = artifacts.read_stage_artifact(run_dir, token, "score")
    grades = _read(run_dir, token, "grade")
    runs = _read(run_dir, token, "run")
    blocks = [
        f"# `{stage['agent_id']}` — {summary.get('dataset_run_id', run_dir.name)}\n",
        _identity_table(score, grades),
        _spread_table(score),
        _warnings_block(score),
        _baseline_block(score),
        _tokens_table(score.get("tokens") or {}),
        _dimensions_table(score.get("dimensions") or {}),
        _rows_table(run_dir, score, grades, stage),
        _clusters_block(score.get("recurring_strengths") or [], "Recurring strengths"),
        _clusters_block(score.get("recurring_weaknesses") or [], "Recurring weaknesses"),
        _row_detail_block(grades, runs),
        _stage_rejudge_section(run_dir, stage),
    ]
    return "\n".join(block for block in blocks if block).rstrip() + "\n"


def _identity_table(score: dict, grades: list) -> str:
    """The models and hashes that make this phase comparable to another run."""
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


def _spread_table(score: dict) -> str:
    """The spread statistics the top-level table deliberately leaves out."""
    stats = score.get("scores") or {}
    if not stats:
        return ""
    headers = ["avg(all)", "avg(passed)", "median", "stddev", "min", "max", "distinct"]
    row = [
        render.score(stats.get("average_all")),
        render.score(stats.get("average_precheck_passed")),
        render.score(stats.get("median")),
        render.score(stats.get("stddev")),
        render.score(stats.get("min")),
        render.score(stats.get("max")),
        stats.get("distinct_score_count", DASH),
    ]
    return "\n".join(["### Score", "", *render.md_table(headers, [row], "rrrrrrr"), ""])


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
    """What the phase cost, split by who spent it."""
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


def _rows_table(run_dir: Path, score: dict, grades: list, stage: dict) -> str:
    """Every row on one line, with its per-dimension sub-scores spread out."""
    results = score.get("results") or []
    if not results:
        return ""
    dimension_ids = list((score.get("dimensions") or {}).keys())
    grades_by_id = {_row_id(grade): grade for grade in grades}
    code = code_grader.read_findings(run_dir, _token(stage)) or {}
    code_findings = code.get("findings") or {}
    headers = ["row", "expect", "precheck", "score"]
    if code_findings:
        headers += ["code", "combined"]
    headers += ["passed", *[f"`{name}`" for name in dimension_ids], "note"]
    aligns = "lll" + "r" * (3 if code_findings else 1) + "l" + "r" * len(dimension_ids) + "l"
    rows = []
    for row in results:
        grade = grades_by_id.get(row.get("row_id")) or {}
        sub_scores = grade.get("sub_scores") or {}
        cells = [
            f"`{row.get('row_id')}`",
            str(row.get("expect", DASH)),
            render.flag(row.get("precheck_passed")),
            render.number(row.get("score")),
        ]
        if code_findings:
            code_score = (code_findings.get(row.get("row_id")) or {}).get("code_score")
            cells.append(render.score(code_score))
            cells.append(render.score(code_grader.blended_score(row.get("score"), code_score)))
        cells.append(render.flag(row.get("passed")))
        cells.extend(str(sub_scores.get(name, DASH)) for name in dimension_ids)
        cells.append(_row_note(row, grade))
        rows.append(cells)
    return "\n".join(["### Rows", "", *render.md_table(headers, rows, aligns), ""])


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


def _clusters_block(clusters: list, title: str) -> str:
    """One clustered narrative list — the prompt-fix (or must-keep) shortlist."""
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
        [f"### {title}", "",
         *render.md_table(["rows", "description", "affected"], rows, "rll"), ""]
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
        caps = grade.get("score_caps") or {}
        if caps:
            lines.append(f"**Score reductions:** {_caps_summary(caps)}\n")
        lines.extend(_bullets("Strengths", grade.get("strengths")))
        lines.extend(_bullets("Weaknesses", grade.get("weaknesses")))
        lines.extend(_evidence_lines(grade.get("evidence") or {}))
        lines.append("</details>\n")
    return "\n".join(lines)


def _caps_summary(caps: dict) -> str:
    """Render per-dimension score reductions across both cap schemas.

    The severity-priced judge writes `final` plus severity counts; the older
    count-based judge wrote `capped_to` plus `weaknesses`. Both shapes exist in
    committed run folders, and a rendering crash on either one takes down the
    whole report — which is how a run folder ends up with fresh artifacts and a
    stale `report.md` still showing the previous grade. Missing keys degrade to
    a bare arrow rather than raising.
    """
    parts = []
    for dim, cap in caps.items():
        before = cap.get("reported", "?")
        after = cap.get("final", cap.get("capped_to", "?"))
        if before == after:
            continue
        counts = [
            f"{cap[key]} {label}"
            for key, label in (
                ("blocking", "blocking"),
                ("severe", "severe"),
                ("major", "major"),
                ("minor", "minor"),
                ("weaknesses", "weakness(es)"),
            )
            if cap.get(key)
        ]
        detail = f" ({', '.join(counts)})" if counts else ""
        parts.append(f"`{dim}` {before}→{after}{detail}")
    return "; ".join(parts) if parts else "none"


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


def _stage_rejudge_section(run_dir: Path, stage: dict) -> str:
    """The command that re-judges JUST this phase's stored outputs."""
    return "\n".join(
        [
            "---",
            "",
            "```bash",
            f"./evals/grading/grade.sh rejudge {run_dir.name} --agents {stage['agent_id']}",
            "```",
        ]
    )


# ── the code report ───────────────────────────────────────────────────────


def _code_findings(run_dir: Path, stages: list) -> dict:
    """Every stage's stored code findings, keyed by agent id."""
    findings = {}
    for stage in stages:
        found = code_grader.read_findings(run_dir, _token(stage))
        if found and found.get("findings"):
            findings[stage.get("agent_id")] = found
    return findings


def _code_report(summary: dict, code_stages: dict) -> str:
    """The deterministic track on its own page: per-row scores and every finding."""
    lines = [
        f"# Code grading — {summary.get('dataset_run_id', DASH)}",
        "",
        "Deterministic checks over the built HTML: structure (`static_check`), a "
        "headless render with every nav target clicked (`render_check`), and an "
        "interaction sweep over buttons and filter inputs. No judge model — every "
        "finding below is reproducible for free.",
        "",
    ]
    for agent_id, result in code_stages.items():
        lines.append(f"## `{agent_id}` — `{result.get('deliverable_file', DASH)}`")
        lines.append("")
        rows = []
        for row_id, finding in (result.get("findings") or {}).items():
            rendered = finding.get("render") or {}
            interactions = finding.get("interactions") or {}
            nav = rendered.get("nav_results") or []
            nav_summary = (
                f"{sum(1 for n in nav if n.get('ok'))}/{len(nav)} ok" if nav else DASH
            )
            # Exercised counts, not just failures: "0 failed" must be
            # distinguishable from "nothing was clickable to begin with".
            if interactions.get("available"):
                exercised = len(interactions.get("actions") or []) + len(
                    interactions.get("failures") or []
                )
                probes = f"{exercised - len(interactions.get('failures') or [])}/{exercised} ok"
            else:
                probes = DASH
            rows.append([
                f"`{row_id}`",
                render.score(finding.get("code_score")),
                render.flag(finding.get("ok")),
                nav_summary,
                len(rendered.get("console_errors") or []) + len(rendered.get("page_errors") or [])
                if rendered.get("available") else DASH,
                probes,
            ])
        headers = ["row", "code score", "static ok", "nav", "js errors", "interactions"]
        lines.extend(render.md_table(headers, rows, "lrlrrr"))
        lines.append("")
        lines.append(
            "Full per-row transcripts — every route driven and every control probed, "
            f"outcome by outcome — are in `logs/<row_id>/{_token({'agent_id': agent_id})}"
            "_code_checks.log`.\n"
        )
        lines.extend(_code_row_details(result))
    return "\n".join(lines).rstrip() + "\n"


def _code_row_details(result: dict) -> list[str]:
    """Every concrete finding, per row — the evidence behind the table above."""
    lines = []
    for row_id, finding in (result.get("findings") or {}).items():
        details = _code_finding_lines(finding)
        if not details:
            continue
        lines.append(f"<details><summary><b>{row_id}</b> — findings</summary>\n")
        lines.extend(details)
        lines.append("</details>\n")
    return lines


def _code_finding_lines(finding: dict) -> list[str]:
    """One row's findings as bullets; empty when the row is clean."""
    lines = []
    for issue in finding.get("issues") or []:
        lines.append(f"- **static issue** — {issue}")
    for warning in finding.get("warnings") or []:
        lines.append(f"- static warning — {warning}")
    rendered = finding.get("render") or {}
    for error in rendered.get("console_errors") or []:
        lines.append(f"- **console error** — {render.truncate(error)}")
    for error in rendered.get("page_errors") or []:
        lines.append(f"- **uncaught exception** — {render.truncate(error)}")
    for nav in rendered.get("nav_results") or []:
        if not nav.get("ok"):
            lines.append(
                f"- **dead nav** — `{nav.get('href')}` expected `{nav.get('expected')}`, "
                f"activated `{nav.get('activated')}`"
            )
    for error in rendered.get("coverage_errors") or []:
        lines.append(f"- **nav coverage** — {render.truncate(error)}")
    interactions = finding.get("interactions") or {}
    for failure in interactions.get("failures") or []:
        errors = "; ".join(failure.get("errors") or [])
        lines.append(
            f"- **interaction failure** — {failure.get('action')} "
            f"`{failure.get('target')}`: {render.truncate(errors)}"
        )
    if lines:
        lines.append("")
    return lines


# ── small helpers ─────────────────────────────────────────────────────────


def _model_code(spec) -> str:
    """`provider/model` as inline code — markdown's own wrapper on render's label."""
    label = render.model_label(spec)
    return label if label == DASH else f"`{label}`"


def _token(stage: dict) -> str:
    """`prototype-specify` -> `prototype_specify`, the artifact file-name form."""
    return grades.agent_token(stage)


def _has_score(run_dir: Path, stage: dict) -> bool:
    """Whether this stage actually wrote a score artifact to read."""
    token = _token(stage)
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
