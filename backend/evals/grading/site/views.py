"""The dashboard: the run list and the five cross-run views.

Each view answers a question the per-run reports structurally cannot:

- **trend** — are we getting better, and since when?
- **prompts** — did *that* edit help, or is it judge noise?
- **dimensions** — which paragraph of which AGENT.md is chronically weak?
- **matrix** — is a phase weak everywhere, or is one brief dragging it down?
- **cost** — what are we spending, and does the built artifact work?

Like `pages`, this reads and writes nothing: aggregates in, HTML out.
"""

from __future__ import annotations

from evals.grading import render
from evals.grading.site import aggregate, charts, model, pages

esc = pages.esc
DASH = pages.DASH

VIEWS = (
    ("runs", "Runs"),
    ("trend", "Quality trend"),
    ("prompts", "Prompt versions"),
    ("dimensions", "Dimensions"),
    ("matrix", "Stage × row"),
    ("cost", "Cost & code health"),
)

CLASS_HINT = {
    model.CLASS_REFERENCE: "a hand-placed reference — drawn as a ceiling line, not a trend point",
    model.CLASS_COPY: "a duplicate folder — listed, but never averaged",
    model.CLASS_PARTIAL: "incomplete — kept out of the trends",
    model.CLASS_ERROR: "could not be read",
}


def run_links(workflow: model.Workflow, run: model.Run) -> pages.Links:
    """How the one report reaches a given run's files on disk.

    Every path is relative to the report at the runs root, so the links resolve
    while it sits there and degrade to nothing worse than a dead link if the
    file is moved on its own.
    """
    return pages.Links(
        stage_href=lambda token: f"#stage-{token}-{run.dataset_run_id}",
        row_href=lambda token, row_id: f"#row={row_id}",
        src_prefix=f"{workflow.name}/{run.dataset_run_id}",
        show_source=False,
    )


def render_report(site: model.Site, aggregates_by_workflow: dict) -> str:
    """The whole evals tree as ONE page: six views, plus a panel per run.

    There is deliberately no second HTML file. Clicking a run opens its
    drill-down in place — overview, phase table, matrix, then every stage with
    its rows and the judge's reasoning — so the report is one artifact to open,
    keep and share rather than a folder of them.
    """
    workflows = site.workflows
    if not workflows:
        return pages.page(
            title="Grading dashboard",
            heading="Grading dashboard",
            subtitle="no runs yet",
            body=(
                '<section class="card"><h2>No runs found</h2>'
                '<p class="muted">Nothing has been graded into this folder yet. '
                "Run <code>./evals/grading/grade.sh plan smoke</code> to see what a run "
                "would do, or <code>./evals/grading/grade.sh runs</code> to list "
                "folders.</p></section>"
            ),
        )

    # One workflow is the normal case; the selector appears only when it earns
    # its place, but the axis exists from the start because retrofitting it
    # into every chart later is far more expensive than reserving it now.
    panels = []
    for key, label in VIEWS:
        blocks = []
        for workflow in workflows:
            result = aggregates_by_workflow[workflow.name]
            heading = (
                f"<h2>{esc(workflow.name)}</h2>" if len(workflows) > 1 else ""
            )
            blocks.append(heading + _view(key, workflow, result))
        panels.append((key, "".join(blocks)))

    # One panel per run, with no tab button of its own: reached by clicking the
    # run in the list, and left by the "all runs" link inside it.
    for workflow in workflows:
        for run in workflow.runs:
            panels.append((
                f"run:{run.dataset_run_id}",
                pages.run_panel(run, links=run_links(workflow, run)),
            ))

    total = len(site.all_runs)
    included = sum(len(workflow.included) for workflow in workflows)
    span = _date_span(site)
    return pages.page(
        title="Evals report",
        heading="Evals report",
        subtitle=(
            f"{esc(render.plural(total, 'run'))} across "
            f"{esc(render.plural(len(workflows), 'workflow'))} · "
            f"{esc(included)} counted in the trends · {esc(span)}"
        ),
        tabs=VIEWS,
        panels=panels,
    )


def _view(key: str, workflow: model.Workflow, result: aggregate.Aggregates) -> str:
    if key == "runs":
        return run_list(workflow)
    if key == "trend":
        return trend_view(result)
    if key == "prompts":
        return prompt_view(result)
    if key == "dimensions":
        return dimension_view(result)
    if key == "matrix":
        return matrix_view(result, workflow)
    return cost_view(result)


def _date_span(site: model.Site) -> str:
    stamps = sorted(run.created_at for run in site.all_runs if run.created_at)
    if not stamps:
        return "no dates recorded"
    return f"{stamps[0][:10]} → {stamps[-1][:10]}"


# ── the run list ──────────────────────────────────────────────────────────


def run_list(workflow: model.Workflow) -> str:
    """Every run, newest first. Excluded ones are badged, never dropped."""
    rows = []
    for run in workflow.runs:
        href = f"#run={run.dataset_run_id}"
        badge = (
            ""
            if run.charted
            else f' <span class="badge {esc(run.run_class)}" title="'
                 f'{esc(run.class_reason)}">{esc(run.run_class)}</span>'
        )
        flags = [] if run.charted else ["excluded"]
        rows.append((
            f' id="run-{esc(run.dataset_run_id)}" data-flags="{esc(" ".join(flags))}"'
            f' data-search="{esc(run.dataset_run_id)} {esc(run.dataset_id)} '
            f'{esc(run.status)} {esc(run.run_class)}"',
            [
                pages.cell(
                    f'<a href="{esc(href)}" data-open-run="{esc(run.dataset_run_id)}">'
                    f"<code>{esc(run.dataset_run_id)}</code></a>{badge}",
                    sort=run.dataset_run_id,
                ),
                pages.cell(pages.grade_pill(run.grade, run.score), sort=run.score),
                pages.cell(
                    esc(render.score(round(run.score, 1)) if run.score is not None else DASH),
                    sort=run.score, align="num",
                ),
                pages.cell(esc(run.dataset_id), sort=run.dataset_id),
                pages.cell(esc(run.row_count), sort=run.row_count, align="num"),
                pages.cell(esc(len(run.stages)), sort=len(run.stages), align="num"),
                pages.cell(esc(run.status), sort=run.status),
                pages.cell(esc(run.created_at), sort=run.created_at or ""),
            ],
        ))
    headers = [("run", ""), ("grade", ""), ("score", "num"), ("dataset", ""),
               ("rows", "num"), ("phases", "num"), ("status", ""), ("started", "")]
    errored = [run for run in workflow.runs if run.run_class == model.CLASS_ERROR]
    notice = (
        pages.callout(
            "<b>Unreadable folders:</b> "
            + ", ".join(f"<code>{esc(run.dataset_run_id)}</code> — {esc(run.class_reason)}"
                        for run in errored),
            "bad",
        )
        if errored
        else ""
    )
    legend = " · ".join(
        f'<span class="badge {esc(name)}">{esc(name)}</span> {esc(hint)}'
        for name, hint in CLASS_HINT.items()
    )
    return (
        f'<section class="card" data-filterscope="1">{notice}'
        '<div class="controls">'
        '<button class="chip" type="button" data-filter="excluded" aria-pressed="false">'
        "show excluded only</button>"
        '<input type="search" placeholder="search runs… ( / )" aria-label="search runs">'
        '<span class="count"></span></div>'
        + pages.table(headers, rows, sortable=True, filterable=True)
        + f'<p class="muted small" style="margin-top:8px">{legend}</p></section>'
    )


# ── V1 quality trend ──────────────────────────────────────────────────────


def trend_view(result: aggregate.Aggregates) -> str:
    if not result.trend:
        return _empty_view("No completed runs to trend yet.")
    points = [(point.dataset_run_id[:13], point.score) for point in result.trend]
    references = [(line.dataset_run_id, line.score) for line in result.references]
    overall = charts.line_chart(points, label="overall grade by run", references=references)

    per_stage = []
    for stage_id in result.stage_ids:
        series = [
            (point.dataset_run_id[:13], point.per_stage.get(stage_id))
            for point in result.trend
        ]
        if all(value is None for _, value in series):
            continue
        per_stage.append(
            f'<section class="card"><h3><code>{esc(stage_id)}</code></h3>'
            + charts.line_chart(series, label=f"{stage_id} by run")
            + "</section>"
        )

    note = (
        "" if result.has_trend
        else pages.callout(
            "Only one run counts toward the trend so far — a line needs two points. "
            "Every completed run added from here on will extend it.", "info")
    )
    table = _trend_table(result)
    return (
        f'<section class="card"><h2>Overall grade</h2>{note}{overall}'
        '<p class="muted small">Reference runs are drawn as dashed lines: a golden is a '
        "target to clear, not a measurement in the series.</p>"
        f"{table}</section>" + "".join(per_stage)
    )


def _trend_table(result: aggregate.Aggregates) -> str:
    """The same numbers as text — nothing on this page is chart-only."""
    rows = [
        ("", [
            pages.cell(f"<code>{esc(point.dataset_run_id)}</code>"),
            pages.cell(esc(point.created_at)),
            pages.cell(pages.grade_pill(point.grade, point.score)),
            pages.cell(
                esc(render.score(round(point.score, 1)) if point.score is not None else DASH),
                align="num",
            ),
        ])
        for point in reversed(result.trend)
    ]
    headers = [("run", ""), ("started", ""), ("grade", ""), ("score", "num")]
    return pages.table(headers, rows, sortable=True)


# ── V2 prompt version history ─────────────────────────────────────────────


def prompt_view(result: aggregate.Aggregates) -> str:
    """Which prompt version each run used, and whether the edit actually moved it."""
    if not result.prompt_history:
        return _empty_view("No prompt hashes were recorded in these runs.")
    blocks = []
    for history in result.prompt_history:
        blocks.append(_prompt_history_block(history))
    return "".join(blocks)


def _prompt_history_block(history: aggregate.PromptHistory) -> str:
    band = history.noise_band
    rows = []
    for version in history.versions:
        noisy = aggregate.within_noise(version.delta, band)
        verdict = "within noise" if noisy and not version.is_baseline else version.verdict
        pill = {
            "baseline": "flat", "within noise": "flat",
            "improved": "high", "held": "mid", "regressed": "low", "unknown": "flat",
        }.get(verdict, "flat")
        delta = (
            DASH if version.delta is None
            else f"{version.delta:+.1f}"
        )
        rows.append((
            "",
            [
                pages.cell(f"<code>{esc(version.short_hash)}</code>"),
                pages.cell(esc(version.first_seen)),
                pages.cell(esc(version.run_count), sort=version.run_count, align="num"),
                pages.cell(pages.score_pill(version.average_score),
                           sort=version.average_score, align="num"),
                pages.cell(esc(delta), sort=version.delta, align="num"),
                pages.cell(f'<span class="pill {pill}">{esc(verdict)}</span>'),
                pages.cell(", ".join(f"<code>{esc(run_id)}</code>"
                                     for run_id in version.run_ids)),
            ],
        ))
    headers = [("prompt", ""), ("first seen", ""), ("runs", "num"), ("average", "num"),
               ("delta", "num"), ("verdict", ""), ("used by", "")]

    band_note = (
        f"Deltas within <b>±{band:.2f}</b> of the baseline are inside the observed "
        "run-to-run noise band (2σ over repeats of one config and prompt, floored at 1.0) "
        "and are reported as <i>within noise</i>, not as an improvement."
        if band is not None
        else "No two runs share a config and prompt hash, so run-to-run variance was never "
             "observed and no delta here can be called real yet."
    )
    return (
        f'<section class="card"><h2><code>{esc(history.agent_id)}</code></h2>'
        + pages.table(headers, rows, sortable=True)
        + f'<p class="muted small" style="margin-top:8px">{band_note}</p>'
        + _diff_picker(history)
        + "</section>"
    )


def _diff_picker(history: aggregate.PromptHistory) -> str:
    """Two versions, side by side — the text behind the number.

    Only versions whose prompt text was captured can be diffed. Older folders
    predate prompt capture, so the control says so rather than disappearing.
    """
    withtext = [version for version in history.versions if version.prompt_text]
    missing = [version for version in history.versions if not version.prompt_text]
    notes = ""
    if missing:
        listed = ", ".join(f"<code>{esc(version.short_hash)}</code>" for version in missing)
        notes = (
            f'<p class="muted small">No captured prompt for {listed} — '
            f"{esc(missing[0].missing_reason)}.</p>"
        )
    if len(withtext) < 2:
        return notes + (
            '<p class="muted small">Two captured prompts are needed to show a diff.</p>'
        )

    def options(selected: str) -> str:
        return "".join(
            f'<option value="{esc(version.short_hash)}"'
            f'{" selected" if version.short_hash == selected else ""}>'
            f"{esc(version.short_hash)} ({esc(version.first_seen[:10])})</option>"
            for version in withtext
        )

    # Default to oldest → newest. Defaulting both selects to the same version
    # would open the control on an empty panel, which reads as broken.
    oldest, newest = withtext[0], withtext[-1]
    panels = []
    for before in withtext:
        for after in withtext:
            if before is after:
                continue
            key = f"{before.short_hash}::{after.short_hash}"
            delta = (
                DASH
                if before.average_score is None or after.average_score is None
                else f"{after.average_score - before.average_score:+.1f}"
            )
            panels.append(
                f'<div data-diffpair="{esc(key)}" class="hidden">'
                f'<p class="small">score delta <b>{esc(delta)}</b> '
                f"({esc(before.short_hash)} → {esc(after.short_hash)})</p>"
                + pages.prompt_diff(
                    before.prompt_text or "", after.prompt_text or "",
                    before_label=before.short_hash, after_label=after.short_hash,
                )
                + "</div>"
            )
    return (
        notes
        + '<div data-diffscope="1"><h3>What changed between versions</h3>'
        '<div class="controls">'
        '<label class="small muted">from</label>'
        f'<select data-role="left" aria-label="diff from">{options(oldest.short_hash)}</select>'
        '<label class="small muted">to</label>'
        f'<select data-role="right" aria-label="diff to">{options(newest.short_hash)}</select>'
        "</div>"
        + "".join(panels)
        + "</div>"
    )


# ── V3 dimension heatmap ──────────────────────────────────────────────────


def dimension_view(result: aggregate.Aggregates) -> str:
    if not result.dimensions_by_stage:
        return _empty_view("No per-dimension scores were recorded in these runs.")
    return (
        _heatmap(result.dimensions_by_stage, result.stage_ids, "Dimensions × phases",
                 "Weakest first. A row that is dark all the way across is a paragraph of an "
                 "AGENT.md that never improves.")
        + _heatmap(
            result.dimensions_by_run,
            tuple(_run_columns(result.dimensions_by_run)),
            "Dimensions × runs",
            "The same weakness over time — is it getting better?",
        )
    )


def _run_columns(grid: dict) -> list[str]:
    seen: list[str] = []
    for by_run in grid.values():
        for run_id in by_run:
            if run_id not in seen:
                seen.append(run_id)
    return sorted(seen)


def _heatmap(grid: dict, columns, title: str, note: str) -> str:
    if not grid or not columns:
        return ""
    ordered = aggregate.worst_first(grid)
    header = "".join(f"<th>{esc(str(column)[:14])}</th>" for column in columns)
    body = []
    for name in ordered:
        cells = [f"<th><code>{esc(name)}</code></th>"]
        for column in columns:
            value = grid[name].get(column)
            text = render.score(round(value, 1)) if value is not None else DASH
            cells.append(
                f'<td style="{charts.heat_style(value)}" '
                f'title="{esc(name)} × {esc(column)}: {esc(text)}">{esc(text)}</td>'
            )
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (
        f'<section class="card"><h2>{esc(title)}</h2>'
        f'<p class="muted small">{esc(note)}</p>'
        '<div class="tablewrap"><table class="matrix">'
        f"<thead><tr><th></th>{header}</tr></thead>"
        f'<tbody>{"".join(body)}</tbody></table></div></section>'
    )


# ── V4 stage x row matrix ─────────────────────────────────────────────────


def matrix_view(result: aggregate.Aggregates, workflow: model.Workflow) -> str:
    if not result.matrix.cells:
        return _empty_view("No graded cells across these runs yet.")
    newest = workflow.included[0] if workflow.included else None
    links = pages.Links(
        row_href=lambda token, row_id: (
            f"#run={newest.dataset_run_id}&row={row_id}" if newest else "#"
        ),
    )
    tokens = {stage.agent_id: stage.agent_token for run in workflow.included
              for stage in run.stages}
    return pages.matrix_section(
        result.matrix,
        links=links,
        token_of=lambda agent_id: tokens.get(agent_id, agent_id.replace("-", "_")),
        title="Stage × row, averaged across runs",
        note=(
            f"Mean over the {result.included_count} counted runs. Each cell says how many "
            "runs it stands on — an average over two runs and one over fifteen are not the "
            "same evidence. Links open the newest run's row."
        ),
    )


# ── V5 cost and code health ───────────────────────────────────────────────


def cost_view(result: aggregate.Aggregates) -> str:
    if not result.tokens:
        return _empty_view("No token counts were recorded in these runs.")
    agent_series = [(entry["dataset_run_id"][:13], entry["agent"]) for entry in result.tokens]
    judge_series = [(entry["dataset_run_id"][:13], entry["judge"]) for entry in result.tokens]
    ceiling = max([entry["total"] for entry in result.tokens] + [1])

    token_rows = [
        ("", [
            pages.cell(f"<code>{esc(entry['dataset_run_id'])}</code>"),
            pages.cell(esc(render.tokens(entry["agent"])), sort=entry["agent"], align="num"),
            pages.cell(esc(render.tokens(entry["judge"])), sort=entry["judge"], align="num"),
            pages.cell(esc(render.tokens(entry["total"])), sort=entry["total"], align="num"),
        ])
        for entry in reversed(result.tokens)
    ]
    health_rows = [
        ("", [
            pages.cell(f"<code>{esc(entry['dataset_run_id'])}</code>"),
            pages.cell(esc(entry["console_errors"]), sort=entry["console_errors"], align="num"),
            pages.cell(esc(entry["page_errors"]), sort=entry["page_errors"], align="num"),
            pages.cell(esc(entry["dead_navs"]), sort=entry["dead_navs"], align="num"),
            pages.cell(
                esc(f'{entry["interaction_failures"]} / {entry["interactions_exercised"]}'),
                sort=entry["interaction_failures"], align="num",
            ),
            pages.cell(esc(entry["static_issues"]), sort=entry["static_issues"], align="num"),
        ])
        for entry in reversed(result.code_health)
    ]
    return (
        '<section class="card"><h2>Tokens by run</h2>'
        + charts.line_chart(agent_series, label="agent tokens by run", y_max=ceiling)
        + '<p class="muted small">Agent spend. Judge spend below.</p>'
        + charts.line_chart(judge_series, label="judge tokens by run", y_max=ceiling)
        + pages.table(
            [("run", ""), ("agent", "num"), ("judge", "num"), ("total", "num")],
            token_rows, sortable=True,
        )
        + "</section>"
        + '<section class="card"><h2>Code-track health</h2>'
        '<p class="muted small">Failures with the counts they were drawn from — '
        '"0 failed" and "nothing was clickable" are not the same result.</p>'
        + pages.table(
            [("run", ""), ("console errors", "num"), ("uncaught", "num"), ("dead nav", "num"),
             ("interaction fails / tried", "num"), ("static issues", "num")],
            health_rows, sortable=True,
        )
        + "</section>"
    )


def _empty_view(message: str) -> str:
    return f'<section class="card"><p class="muted">{esc(message)}</p></section>'
