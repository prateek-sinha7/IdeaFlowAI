"""View-models in, HTML out. No file is read or written here.

Every section is a function returning a fragment, and the export assembles the
same functions — two renderers that could disagree about a grade would be a
correctness bug, not a cosmetic one.

**Everything interpolated goes through `esc()`.** Judge rationales quote agent
output, and the agents under test produce HTML documents, so untrusted markup
is not a risk here but a certainty. The one place that rule is relaxed is
values this module built itself; those are marked at the call site.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from html import escape
from typing import Callable

from evals.grading import render
from evals.grading.site import assets, charts, issues as issues_mod, model

DASH = render.DASH

# What each cell kind looks like in the matrix. A glyph as well as a colour,
# because four different failures all score 0 and colour alone cannot say which
# is which — that distinction is the reason the matrix exists.
KIND_GLYPH = {
    model.KIND_OK: "",
    model.KIND_ERRORED: "✖",
    model.KIND_BROKEN_CHAIN: "⛓",
    model.KIND_PRECHECK_FAIL: "⊘",
    model.KIND_JUDGE_FAILED: "⚖",
    model.KIND_NEGATIVE: "∅",
    model.KIND_UNJUDGED: "·",
}
KIND_LABEL = {
    model.KIND_OK: "graded",
    model.KIND_ERRORED: "dispatch errored — scores 0",
    model.KIND_BROKEN_CHAIN: "never dispatched, upstream broke — scores 0",
    model.KIND_PRECHECK_FAIL: "failed precheck — scores 0",
    model.KIND_JUDGE_FAILED: "the judge failed on this row",
    model.KIND_NEGATIVE: "negative test — excluded from the average",
    model.KIND_UNJUDGED: "never judged — excluded from the average",
}


# ── escaping: the single choke point ──────────────────────────────────────


def esc(value) -> str:
    """The only way text reaches a page. Absent values become an em-dash."""
    if value is None:
        return DASH
    return escape(str(value), quote=True)


def json_block(element_id: str, payload) -> str:
    """Inline data for the page, neutralised so it cannot close its own script."""
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    text = text.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return f'<script type="application/json" id="{esc(element_id)}">{text}</script>'


# ── how a page reaches the run's files ────────────────────────────────────


@dataclass
class Links:
    """Where a page points for stages, deliverables and logs.

    The site links to real files; the export inlines them. Keeping the
    difference in one object is what lets every section builder be shared.
    """

    stage_href: Callable[[str], str] = lambda token: f"#stage-{token}"
    row_href: Callable[[str, str], str] = lambda token, row_id: f"#row={row_id}"
    src_prefix: str = ".."
    detached: bool = False
    preview: Callable[[model.Deliverable], str] | None = None
    # The consolidated report holds every run at once, so inlining each
    # deliverable's source would multiply one file by every artifact ever
    # built. Previews still render; the source is a click away on disk.
    show_source: bool = True

    def deliverable_href(self, row_id: str, filename: str) -> str:
        return f"{self.src_prefix}/src/{row_id}/{filename}"

    def log_href(self, row_id: str, token: str) -> str:
        return f"{self.src_prefix}/logs/{row_id}/{token}.log"


SITE_LINKS = Links()


# ── the page shell ────────────────────────────────────────────────────────


def page(
    *,
    title: str,
    heading: str,
    crumbs: str = "",
    subtitle: str = "",
    tabs=(),
    panels=(),
    body: str = "",
) -> str:
    """One complete document: inline CSS, inline JS, no external anything."""
    tab_bar = ""
    if tabs:
        buttons = "".join(
            f'<button role="tab" data-tab="{esc(key)}" '
            f'aria-selected="{"true" if index == 0 else "false"}">{esc(label)}</button>'
            for index, (key, label) in enumerate(tabs)
        )
        tab_bar = f'<nav class="tabs" role="tablist">{buttons}</nav>'
    panel_html = "".join(
        f'<div class="tabpanel{" active" if index == 0 else ""}" '
        f'data-tab="{esc(key)}" role="tabpanel">{content}</div>'
        for index, (key, content) in enumerate(panels)
    )
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(title)}</title>"
        f"<script>{assets.THEME_BOOTSTRAP}</script>"
        f"<style>{assets.CSS}</style>"
        "</head><body>"
        '<header class="top"><div class="inner">'
        f'<div><div class="crumbs">{crumbs}</div>'
        f"<h1>{esc(heading)}</h1>"
        f'<div class="muted small">{subtitle}</div></div>'
        '<div class="spacer"></div>'
        '<button class="ghost" id="theme-toggle" type="button">theme</button>'
        "</div>"
        f"{tab_bar}</header>"
        f'<div class="wrap">{body}{panel_html}</div>'
        f"<script>{assets.JS}</script>"
        "</body></html>\n"
    )


# ── shared atoms ──────────────────────────────────────────────────────────


def score_pill(value, *, suffix: str = "") -> str:
    """A score as a coloured pill that always carries its number."""
    if value is None:
        return f'<span class="pill flat">{DASH}</span>'
    return (
        f'<span class="pill {charts.band_class(value)}">'
        f"{render.score(round(float(value), 1))}{esc(suffix) if suffix else ''}</span>"
    )


def grade_pill(grade: str | None, score=None) -> str:
    if not grade:
        return f'<span class="pill flat">{DASH}</span>'
    return f'<span class="pill {charts.band_class(score)}">{esc(grade)}</span>'


def stat(label: str, value: str) -> str:
    return f'<div class="stat"><div class="label">{esc(label)}</div><div class="value">{value}</div></div>'


def callout(text: str, kind: str = "info") -> str:
    return f'<div class="callout {esc(kind)}">{text}</div>'


def command_block(command: str, note: str = "") -> str:
    """A shell command with a copy button — the site's only clipboard use."""
    return (
        f'<div class="small muted">{esc(note)}</div>'
        f'<pre class="block">{esc(command)}</pre>'
        f'<button class="ghost" type="button" data-copy="{esc(command)}">copy</button>'
    )


def table(headers, rows, *, sortable=False, filterable=False, classes="") -> str:
    """A table. `rows` are pre-rendered cell strings — every one already escaped."""
    head = "".join(
        f'<th class="{"sortable " if sortable else ""}{align}">{label}</th>'
        for label, align in headers
    )
    body = "".join(
        f'<tr{attrs}>' + "".join(cells) + "</tr>" for attrs, cells in rows
    )
    flags = (' data-sortable="1"' if sortable else "") + (
        ' data-filterable="1"' if filterable else ""
    )
    return (
        f'<div class="tablewrap"><table class="{esc(classes)}"{flags}>'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def cell(content: str, *, sort=None, align: str = "") -> str:
    attr = "" if sort is None else f' data-sort="{esc(sort)}"'
    return f'<td class="{align}"{attr}>{content}</td>'


# ── run page ──────────────────────────────────────────────────────────────


def run_subtitle(run: model.Run) -> str:
    return (
        f"status <code>{esc(run.status)}</code> · started {esc(run.created_at)} · "
        f"finished {esc(run.finished_at)} · dataset <code>{esc(run.dataset_id)}</code>"
    )


def run_summary_sections(run: model.Run, *, links: Links = SITE_LINKS) -> str:
    """The dashboard half of a run: provenance, phases, rows, clusters.

    Shared verbatim by the run panel and the standalone export. Two renderers
    that could disagree about a grade would be a correctness bug, so there is
    one ordering and one set of sections.
    """
    return "".join(
        block
        for block in (
            run_class_notice(run),
            grade_hero(run),
            override_warning(run),
            provenance_section(run),
            phase_table(run, links=links),
            rows_overview(run, links=links),
            not_run_section(run),
            clusters_section(run, links=links),
        )
        if block
    )


def run_class_notice(run: model.Run) -> str:
    """Say plainly when a run is not a normal measurement."""
    if run.run_class == model.CLASS_RUN:
        return ""
    kind = "bad" if run.run_class == model.CLASS_ERROR else "warn"
    return callout(
        f"<b>{esc(run.run_class)}</b> — {esc(run.class_reason)}. "
        "This run is listed on the dashboard but kept out of the trends.",
        kind,
    )


def grade_hero(run: model.Run) -> str:
    """The one-line answer, with the arithmetic behind it stated, not implied."""
    overall = run.overall
    if not overall:
        return (
            '<section class="card">'
            "<h2>No grade</h2>"
            '<p class="muted">Nothing in this run was gradable — every row either failed '
            "before dispatch or was never judged. There is no score to show, and none has "
            "been invented.</p></section>"
        )
    failed = overall["failed_cells"]
    failed_note = (
        callout(
            f"<b>{failed} of {overall['counted']} cells failed outright</b> — a precheck "
            "failure, a dispatch error, or a chain broken upstream. Each scores 0.",
            "bad",
        )
        if failed
        else ""
    )
    from evals.grading import grades

    return (
        '<section class="card"><div class="hero">'
        f'<div class="grade-badge {charts.band_class(overall["score"])}">'
        f'{esc(overall["grade"])}</div>'
        "<div>"
        f'<div class="grade-score">{overall["score"]:.1f} <span class="muted">/ 100</span></div>'
        f'<div class="muted small">judge and code blended over '
        f'{esc(render.plural(overall["counted"], "graded cell"))}'
        f'{", none failed" if not failed else ""}</div>'
        "</div></div>"
        f'<div style="margin-top:12px">{charts.band_track(overall["score"], grades.GRADE_BANDS)}</div>'
        f"{failed_note}</section>"
    )


def override_warning(run: model.Run) -> str:
    """A run whose flags diverged from its config cannot be reproduced from it."""
    if not run.overrides:
        return ""
    listed = ", ".join(
        f"<code>{esc(key)}={esc(value)}</code>" for key, value in sorted(run.overrides.items())
    )
    return callout(
        f"This run's flags diverged from its config file ({listed}), so re-running that "
        "config alone will <b>not</b> reproduce it.",
        "warn",
    )


def phase_table(run: model.Run, *, links: Links = SITE_LINKS) -> str:
    """One line per phase, ending in the column the headline grade averages."""
    if not run.stages:
        return ""
    rows = []
    for stage in run.stages:
        judge = (stage.scores or {}).get("average_all")
        code_scores = [row.code_score for row in stage.rows if row.code_score is not None]
        code = sum(code_scores) / len(code_scores) if code_scores else None
        rows.append((
            "",
            [
                cell(f'<a href="{esc(links.stage_href(stage.agent_token))}">'
                     f"<code>{esc(stage.agent_id)}</code></a>"),
                cell(esc((stage.counts or {}).get("rows", DASH)), align="num"),
                cell(esc((stage.counts or {}).get("judged", 0)), align="num"),
                cell(score_pill(judge), align="num"),
                cell(score_pill(code), align="num"),
                cell(
                    score_pill(stage.effective)
                    + (f' <span class="small muted">({stage.failed_cells} failed)</span>'
                       if stage.failed_cells else ""),
                    align="num",
                ),
                cell(esc((stage.baseline or {}).get("verdict", DASH))),
            ],
        ))
    if run.overall:
        rows.append((
            ' style="font-weight:650"',
            [
                cell(f'overall — grade {esc(run.overall["grade"])}'),
                cell(esc(run.overall["counted"]), align="num"),
                cell(DASH, align="num"), cell(DASH, align="num"), cell(DASH, align="num"),
                cell(f'<b>{run.overall["score"]:.1f}</b>', align="num"),
                cell(DASH),
            ],
        ))
    headers = [("phase", ""), ("rows", "num"), ("graded", "num"), ("judge", "num"),
               ("code", "num"), ("effective", "num"), ("baseline", "")]
    return (
        '<section class="card"><h2>Phase scores</h2>'
        + table(headers, rows)
        + '<p class="muted small" style="margin-top:8px"><code>effective</code> = judge '
        "blended with code per row (0.7 / 0.3, whichever exists when only one does); a row "
        "that failed counts <b>0</b>. The overall row is the mean of every phase's rows — "
        "the headline grade above.</p></section>"
    )


def matrix_section(matrix: model.Matrix, *, links: Links, token_of, title: str,
                   note: str = "") -> str:
    """Stages down, rows across. The picture a per-phase average cannot show."""
    if not matrix.stage_ids or not matrix.row_ids:
        return ""
    note_html = f'<p class="muted small">{esc(note)}</p>' if note else ""
    header_cells = "".join(f"<th>{esc(row_id)}</th>" for row_id in matrix.row_ids)
    body = []
    for stage_id in matrix.stage_ids:
        cells = [f"<th><code>{esc(stage_id)}</code></th>"]
        for row_id in matrix.row_ids:
            found = matrix.cell(stage_id, row_id)
            if found is None:
                cells.append(f'<td class="na" title="not applicable">{DASH}</td>')
                continue
            glyph = KIND_GLYPH.get(found.kind, "")
            label = KIND_LABEL.get(found.kind, found.kind)
            value = (
                render.score(round(found.value, 1)) if found.value is not None else DASH
            )
            spread = (
                f" ± {found.spread:.1f} over {found.run_count} runs"
                if found.spread is not None
                else ""
            )
            href = links.row_href(token_of(stage_id), row_id)
            kind_span = (
                f'<span class="kind">{esc(glyph)}</span>' if glyph else ""
            )
            cells.append(
                f'<td class="cell" style="{charts.heat_style(found.value)}" '
                f'title="{esc(stage_id)} × {esc(row_id)}: {esc(label)}{esc(spread)}">'
                f'<a href="{esc(href)}">{value}</a>'
                f"{kind_span}</td>"
            )
        body.append("<tr>" + "".join(cells) + "</tr>")
    legend = " · ".join(
        f"{esc(KIND_GLYPH[kind])} {esc(KIND_LABEL[kind])}"
        for kind in (model.KIND_ERRORED, model.KIND_BROKEN_CHAIN,
                     model.KIND_PRECHECK_FAIL, model.KIND_JUDGE_FAILED)
    )
    return (
        f'<section class="card"><h2>{esc(title)}</h2>'
        f"{note_html}"
        '<div class="tablewrap"><table class="matrix">'
        f"<thead><tr><th></th>{header_cells}</tr></thead>"
        f'<tbody>{"".join(body)}</tbody></table></div>'
        f'<p class="muted small" style="margin-top:8px">A low <b>row</b> is a prompt '
        "problem; a low <b>column</b> is a brief that breaks the chain. "
        f"{legend}</p></section>"
    )


def not_run_section(run: model.Run) -> str:
    if not run.not_run:
        return ""
    listed = ", ".join(f"<code>{esc(agent)}</code>" for agent in run.not_run)
    return callout(f"<b>Not run:</b> {listed}", "warn")


def clusters_section(run: model.Run, *, links: Links) -> str:
    """Recurring strengths and weaknesses across every phase, widest first."""
    blocks = []
    for key, title in (("recurring_weaknesses", "Weaknesses"),
                       ("recurring_strengths", "Strengths")):
        rows = []
        for stage in run.stages:
            for cluster in getattr(stage, key) or []:
                row_ids = cluster.get("row_ids") or []
                links_html = ", ".join(
                    f'<a href="{esc(links.row_href(stage.agent_token, row_id))}">'
                    f"<code>{esc(row_id)}</code></a>"
                    for row_id in row_ids
                )
                rows.append((len(row_ids), (
                    "",
                    [
                        cell(f"<code>{esc(stage.agent_id)}</code>"),
                        cell(esc(len(row_ids)), sort=len(row_ids), align="num"),
                        cell(esc(render.truncate(cluster.get("evidence"), limit=260))),
                        cell(links_html or DASH),
                    ],
                )))
        if not rows:
            continue
        rows.sort(key=lambda pair: -pair[0])
        headers = [("phase", ""), ("rows affected", "num"), ("description", ""), ("rows", "")]
        blocks.append(
            f'<section class="card"><h2>{esc(title)}</h2>'
            + table(headers, [entry for _, entry in rows], sortable=True)
            + "</section>"
        )
    return "".join(blocks)


def provenance_section(run: model.Run) -> str:
    """The settings that produced these numbers — a grade without them is a rumour."""
    hashes = run.stages[0].hashes if run.stages else {}
    rows = [
        ("config <code>run_id</code>", f"<code>{esc(run.config_run_id)}</code>"),
        ("workflow", f"<code>{esc(run.workflow_id)}</code>"),
        ("dataset", f"<code>{esc(run.dataset_id)}</code> ({esc(run.row_count)} rows)"),
        ("agent under test", f"<code>{esc(render.model_label(run.model_under_test))}</code>"),
        ("judge", f"<code>{esc(render.model_label(run.judge))}</code> → resolved "
                  f"<code>{esc(hashes.get('judge_resolved_model_id', DASH))}</code>"),
        ("concurrency / repeats",
         f"{esc((run.options or {}).get('concurrency', DASH))} / "
         f"{esc((run.options or {}).get('repeats', DASH))}"),
        ("judging", "DISABLED (<code>no_judge</code>)"
         if (run.options or {}).get("no_judge") else "enabled"),
        ("rubric hash", f"<code>{esc(render.short_hash(hashes.get('rubric_hash')))}</code>"),
        ("dataset hash", f"<code>{esc(render.short_hash(hashes.get('dataset_hash')))}</code>"),
    ]
    body = "".join(f"<tr><td>{esc(label)}</td><td>{value}</td></tr>" for label, value in rows)
    return (
        '<section class="card"><h2>Provenance</h2>'
        f'<div class="tablewrap"><table><tbody>{body}</tbody></table></div></section>'
    )


def commands_section(run: model.Run) -> str:
    """Everything you might want to do to this run next, ready to paste."""
    name = run.dataset_run_id
    return (
        '<section class="card"><h2>Re-run this</h2>'
        + command_block(
            f"./evals/grading/grade.sh rejudge {name}",
            "Re-score the stored responses with the judge — no agent is dispatched. LIVE: "
            "judge tokens only.",
        )
        + command_block(
            f"./evals/grading/grade.sh code {name}",
            "Re-run the deterministic browser checks. Free.",
        )
        + command_block(
            f"./evals/grading/grade.sh run {run.run_dir}/grade_config.resolved.yaml",
            "Reproduce the whole run from its own frozen settings. LIVE.",
        )
        + "</section>"
    )


# ── stage page ────────────────────────────────────────────────────────────


def run_panel(run: model.Run, *, links: Links, back_to: str = "runs") -> str:
    """One run as a dashboard: provenance, phases, rows, then a tab per phase.

    Ordered by what a reader needs first — what produced these numbers, how the
    phases compare, which rows carried them — and only then the per-phase
    detail, behind tabs so one run is one screen rather than a scroll.
    """
    scope = run.dataset_run_id
    buttons = "".join(
        f'<button type="button" data-phasetab="{esc(stage.agent_token)}" '
        f'aria-pressed="{"true" if index == 0 else "false"}">'
        f"<span>{esc(stage.agent_id)}</span>{_issue_badge(stage)}</button>"
        for index, stage in enumerate(run.stages)
    )
    panels = "".join(
        f'<div data-phasepanel="{esc(stage.agent_token)}" '
        f'class="{"" if index == 0 else "hidden"}" '
        f'id="stage-{esc(stage.agent_token)}-{esc(scope)}">'
        + stage_body(run, stage, links=links)
        + "</div>"
        for index, stage in enumerate(run.stages)
    )
    phases = (
        f'<section class="card" data-phasescope="{esc(scope)}">'
        "<h2>Phase detail</h2>"
        f'<div class="phasetabs">{buttons}</div>{panels}</section>'
        if run.stages
        else ""
    )
    return (
        f'<p><a href="#" data-back="{esc(back_to)}">&larr; all runs</a></p>'
        f"<h1>{esc(run.dataset_run_id)}</h1>"
        f'<p class="muted small">{run_subtitle(run)}</p>'
        + run_summary_sections(run, links=links)
        + phases
        + commands_section(run)
    )


def _issue_badge(stage: model.Stage) -> str:
    """Problems and strengths as two numbers on the tab itself.

    The point of putting them here is deciding *not* to open a tab: a phase
    with nothing wrong should say so before anyone clicks it.
    """
    summary = issues_mod.summarize(stage)
    problems = summary.problem_count
    band = "high" if not problems else (
        "low" if problems > 2 * max(1, summary.rows_total) else "mid"
    )
    return (
        '<span class="tabcount">'
        f'<span class="pill {band}" title="weaknesses and code findings">{problems}</span>'
        f'<span class="pill high" title="strengths">{summary.strength_count}</span>'
        "</span>"
    )


def rows_overview(run: model.Run, *, links: Links) -> str:
    """Every dataset row as one line, scored across every phase.

    The stage x row matrix as a sortable table: a row that is weak in every
    column is a brief that breaks the chain, not a phase that misbehaved.
    """
    matrix = run.matrix
    if not matrix.row_ids or not matrix.stage_ids:
        return ""
    tokens = {stage.agent_id: stage.agent_token for stage in run.stages}
    body = []
    for row_id in matrix.row_ids:
        cells = [cell(f"<code>{esc(row_id)}</code>", sort=row_id)]
        values = []
        for stage_id in matrix.stage_ids:
            found = matrix.cell(stage_id, row_id)
            if found is None:
                cells.append(cell(f'<span class="muted">{DASH}</span>'))
                continue
            if found.value is not None:
                values.append(found.value)
            glyph = KIND_GLYPH.get(found.kind, "")
            label = KIND_LABEL.get(found.kind, found.kind)
            token = tokens.get(stage_id, stage_id.replace("-", "_"))
            shown = score_pill(found.value) if found.value is not None else esc(DASH)
            cells.append(cell(
                f'<a href="{esc(links.row_href(token, row_id))}" title="{esc(label)}">'
                f"{shown}{esc(glyph)}</a>",
                sort=found.value,
            ))
        mean = sum(values) / len(values) if values else None
        cells.append(cell(score_pill(mean), sort=mean))
        body.append(("", cells))
    headers = [("row", "")] + [(stage_id, "num") for stage_id in matrix.stage_ids]
    headers.append(("mean", "num"))
    return (
        '<section class="card"><h2>Rows</h2>'
        + table(headers, body, sortable=True)
        + '<p class="muted small" style="margin-top:8px">One line per brief, scored by every '
        "phase. A row weak all the way across is the brief, not the prompt. Click a score to "
        "open that row in its phase.</p></section>"
    )


def stage_body(run: model.Run, stage: model.Stage, *, links: Links = SITE_LINKS) -> str:
    return "".join(
        block
        for block in (
            warnings_block(stage),
            baseline_block(stage),
            # What went wrong, grouped and counted, before any per-row detail:
            # the reader should learn the shape of the damage before reading
            # five variations of the same complaint.
            issues_section(stage),
            stage_summary(stage),
            dimensions_block(stage),
            tokens_block(stage),
            rows_section(stage, links=links),
            stage_commands(run, stage),
        )
        if block
    )


def warnings_block(stage: model.Stage) -> str:
    """Warnings come first: they say which numbers below not to trust."""
    if not stage.warnings:
        return ""
    items = "".join(f"<li>{esc(warning)}</li>" for warning in stage.warnings)
    return callout(f"<b>Warnings</b><ul>{items}</ul>", "warn")


def baseline_block(stage: model.Stage) -> str:
    baseline = stage.baseline or {}
    if not baseline:
        return ""
    failures = "".join(f"<li>{esc(failure)}</li>" for failure in baseline.get("failures") or [])
    verdict = baseline.get("verdict", DASH)
    kind = "bad" if str(verdict).lower() not in ("pass", "ok") else "info"
    return callout(
        f"<b>Baseline:</b> <code>{esc(verdict)}</code>"
        + (f"<ul>{failures}</ul>" if failures else ""),
        kind,
    )


def stage_summary(stage: model.Stage) -> str:
    """The spread statistics, with the distribution drawn beside them."""
    scores = stage.scores or {}
    if not scores:
        return ""
    values = [row.judge_score for row in stage.rows if row.judge_score is not None]
    stats = "".join([
        stat("avg (all)", render.score(scores.get("average_all"))),
        stat("avg (passed)", render.score(scores.get("average_precheck_passed"))),
        stat("median", render.score(scores.get("median"))),
        stat("stddev", render.score(scores.get("stddev"))),
        stat("min", render.score(scores.get("min"))),
        stat("max", render.score(scores.get("max"))),
        stat("distinct", esc(scores.get("distinct_score_count", DASH))),
    ])
    strip = charts.distribution(values, label="score distribution") if values else ""
    return f'<section class="card"><h2>Score</h2><div class="stats">{stats}</div>{strip}</section>'


def dimensions_block(stage: model.Stage) -> str:
    """Per-dimension aggregates, weakest first — which paragraph to rewrite."""
    if not stage.dimensions:
        return ""
    ordered = sorted(
        stage.dimensions.items(),
        key=lambda pair: (pair[1].get("mean") is None, pair[1].get("mean") or 0),
    )
    rows = [
        ("", [
            cell(f"<code>{esc(name)}</code>"),
            cell(esc(stats.get("count", 0)), sort=stats.get("count", 0), align="num"),
            cell(score_pill(stats.get("mean")), sort=stats.get("mean"), align="num"),
            cell(esc(render.number(stats.get("median"))), align="num"),
            cell(esc(render.number(stats.get("stddev"))), align="num"),
            cell(esc(render.number(stats.get("min"))), align="num"),
            cell(esc(render.number(stats.get("max"))), align="num"),
        ])
        for name, stats in ordered
    ]
    headers = [("dimension", ""), ("n", "num"), ("mean", "num"), ("median", "num"),
               ("stddev", "num"), ("min", "num"), ("max", "num")]
    chart = charts.bar_chart(
        [(name, stats.get("mean")) for name, stats in ordered], label="dimension means"
    )
    return (
        '<section class="card"><h2>Dimensions</h2>'
        '<p class="muted small">Weakest first — the order to read them in.</p>'
        f"{chart}{table(headers, rows, sortable=True)}</section>"
    )


def tokens_block(stage: model.Stage) -> str:
    tokens = stage.tokens or {}
    if not tokens:
        return ""
    agent = tokens.get("agent") or {}
    judge = tokens.get("judge") or {}
    rows = [
        ("", [cell("agent"), cell(esc(agent.get("in", 0)), align="num"),
              cell(esc(agent.get("out", 0)), align="num"),
              cell(esc(agent.get("total", 0)), align="num")]),
        ("", [cell("judge"), cell(esc(judge.get("in", 0)), align="num"),
              cell(esc(judge.get("out", 0)), align="num"),
              cell(esc(judge.get("total", 0)), align="num")]),
        ("", [cell("<b>all</b>"), cell(esc(tokens.get("in", 0)), align="num"),
              cell(esc(tokens.get("out", 0)), align="num"),
              cell(f'<b>{esc(tokens.get("total", 0))}</b>', align="num")]),
    ]
    headers = [("spender", ""), ("in", "num"), ("out", "num"), ("total", "num")]
    return f'<section class="card"><h2>Tokens</h2>{table(headers, rows)}</section>'


def issues_section(stage: model.Stage) -> str:
    """What to fix, what not to break, and what the browser found — apart.

    One merged list buries the actionable half, so weaknesses, strengths and
    code findings each get their own counted table. Every row is a group: the
    same defect across several briefs is one line, not five.
    """
    summary = issues_mod.summarize(stage)
    stats = "".join([
        stat("score", render.score(round(stage.effective, 1))
             if stage.effective is not None else DASH),
        stat("rows", str(summary.rows_total)),
        stat("weaknesses", str(summary.weakness_count)),
        stat("code findings", str(summary.code_count)),
        stat("strengths", str(summary.strength_count)),
        stat("clean rows", f"{summary.clean_rows} / {summary.rows_total}"),
    ])
    return (
        f'<div class="stats">{stats}</div>'
        + _finding_table(
            "Weaknesses", summary.weaknesses, "low",
            "What to fix, widest first. A line covering several rows is one defect, "
            "not several.",
        )
        + _finding_table(
            "Code findings", summary.code, "low",
            "The deterministic browser sweep — reproducible for free, and not a matter "
            "of opinion.",
        )
        + _finding_table(
            "Strengths", summary.strengths, "high",
            "What a prompt edit must not break.",
        )
    )


def _finding_table(title: str, groups, band: str, note: str) -> str:
    """One counted table of grouped findings, or a one-line 'none'."""
    total = sum(group.count for group in groups)
    heading = (
        f'<h3 class="sechead">{esc(title)}'
        f'<span class="pill {band if total else "flat"}">{total}</span></h3>'
    )
    if not groups:
        return (
            f'<section class="card">{heading}'
            '<p class="muted small">None recorded.</p></section>'
        )
    rows = [
        ("", [
            cell(esc(group.count), sort=group.count, align="num"),
            cell(esc(render.truncate(group.detail, limit=200))),
            cell(", ".join(f"<code>{esc(row_id)}</code>" for row_id in group.row_ids)),
        ])
        for group in groups
    ]
    return (
        f'<section class="card">{heading}'
        f'<p class="muted small">{esc(note)}</p>'
        + table([("rows", "num"), (title.rstrip("s"), ""), ("affected", "")], rows,
                sortable=True)
        + "</section>"
    )


def rows_section(stage: model.Stage, *, links: Links) -> str:
    """Every row, filterable and sortable, each expanding into its full detail."""
    if not stage.rows:
        return ""
    dimension_ids = stage.dimension_ids
    headers = [("row", ""), ("expect", ""), ("precheck", ""), ("judge", "num")]
    has_code = any(row.code_score is not None for row in stage.rows)
    if has_code:
        headers += [("code", "num"), ("combined", "num")]
    headers += [("passed", "")] + [(name, "num") for name in dimension_ids] + [("note", "")]

    body = []
    for row in stage.rows:
        cells = [
            cell(f'<span data-expand="{esc(row.row_id)}" aria-expanded="false" '
                 f'id="row-{esc(row.row_id)}"><code>{esc(row.row_id)}</code></span>',
                 sort=row.row_id),
            cell(esc(row.expect or DASH)),
            cell(render.flag(row.precheck_passed)),
            cell(score_pill(row.judge_score), sort=row.judge_score),
        ]
        if has_code:
            cells.append(cell(score_pill(row.code_score), sort=row.code_score))
            cells.append(cell(score_pill(row.combined), sort=row.combined))
        cells.append(cell(render.flag(row.passed)))
        cells.extend(
            cell(esc(row.sub_scores.get(name, DASH)), sort=row.sub_scores.get(name),
                 align="num")
            for name in dimension_ids
        )
        cells.append(cell(esc(row_note(row))))
        attrs = (
            f' data-flags="{esc(" ".join(row_flags(row)))}"'
            f' data-search="{esc(row_haystack(row))}"'
        )
        body.append((attrs, cells))
        body.append((
            ' class="detail hidden" id="detail-' + esc(row.row_id) + '"',
            [f'<td colspan="{len(headers)}">{row_detail(stage, row, links=links)}</td>'],
        ))

    chips = "".join(
        f'<button class="chip" type="button" data-filter="{esc(flag)}" '
        f'aria-pressed="false">{esc(label)}</button>'
        for flag, label in (("failed", "failures only"), ("negative", "negative tests"),
                            ("judge-failed", "judge errors"), ("capped", "capped"))
    )
    return (
        '<section class="card" data-filterscope="1"><h2>Rows</h2>'
        f'<div class="controls">{chips}'
        '<input type="search" placeholder="search rows, rationale, evidence… ( / )" '
        'aria-label="search rows">'
        '<span class="count"></span></div>'
        + table(headers, body, sortable=True, filterable=True)
        + '<p class="muted small" style="margin-top:8px">Click a row id to open the judge\'s '
        "reasoning and what was built.</p></section>"
    )


def row_flags(row: model.Row) -> list[str]:
    flags = []
    if row.failed:
        flags.append("failed")
    if row.cell_kind == model.KIND_NEGATIVE:
        flags.append("negative")
    if row.cell_kind == model.KIND_JUDGE_FAILED or row.judge_error:
        flags.append("judge-failed")
    if row.score_caps:
        flags.append("capped")
    return flags


def row_haystack(row: model.Row) -> str:
    """What the search box matches against — id, reasoning, and evidence."""
    parts = [row.row_id, row.rationale or "", " ".join(str(w) for w in row.weaknesses)]
    parts.extend(str(value) for value in (row.evidence or {}).values())
    return render.truncate(" ".join(parts), limit=400)


def row_note(row: model.Row) -> str:
    """Why a row has no score — never left to be inferred from a blank cell."""
    if row.errored:
        return "dispatch errored"
    if row.skipped_reason:
        return f"skipped — {row.skipped_reason}"
    if row.judge_error:
        return f"judge failed — {render.truncate(row.judge_error, 80)}"
    if row.cell_kind == model.KIND_BROKEN_CHAIN:
        return "never dispatched — upstream broke"
    if row.cell_kind == model.KIND_NEGATIVE:
        return "negative test"
    return ""


def row_detail(stage: model.Stage, row: model.Row, *, links: Links) -> str:
    """The judge's criticism, next to the thing being criticised."""
    blocks = []
    if row.brief:
        blocks.append(
            f"<h3>Brief</h3><pre class='block'>{esc(render.truncate(row.brief, 700))}</pre>"
        )
    if row.precheck_reason:
        blocks.append(f"<p><b>Precheck:</b> {esc(row.precheck_reason)}</p>")
    if row.judge_error:
        blocks.append(callout(f"<b>Judge failed:</b> {esc(row.judge_error)}", "bad"))
    if row.rationale:
        blocks.append(f"<h3>Rationale</h3><p>{esc(row.rationale)}</p>")
    if row.score_caps:
        # Both cap schemas exist in committed run folders — the severity-priced
        # judge writes `final` plus severity counts, the older count-based one
        # wrote `capped_to`. `markdown_report` already owns that reconciliation,
        # so it is reused rather than reimplemented with a second convention.
        from evals.grading import markdown_report

        summary = markdown_report._caps_summary(row.score_caps)
        if summary != "none":
            blocks.append(f"<p><b>Score reductions:</b> {esc(summary)}</p>")
    if row.evidence:
        listed = "".join(
            f"<li><code>{esc(name)}</code> — {esc(quote)}</li>"
            for name, quote in row.evidence.items()
        )
        blocks.append(f"<h3>Evidence</h3><ul>{listed}</ul>")
    if row.sub_scores:
        listed = " · ".join(
            f"<code>{esc(name)}</code> {esc(value)}" for name, value in row.sub_scores.items()
        )
        blocks.append(f"<p class='small'>{listed}</p>")
    code_block = code_findings_block(row)
    if code_block:
        blocks.append(code_block)
    blocks.append(deliverables_block(row, stage, links=links))
    return "".join(blocks)


def code_findings_block(row: model.Row) -> str:
    """What the browser found on this row — free, reproducible, and specific."""
    finding = row.code_finding or {}
    if not finding:
        return ""
    rendered = finding.get("render") or {}
    interactions = finding.get("interactions") or {}
    items = []
    items += [f"<li><b>static issue</b> — {esc(issue)}</li>"
              for issue in finding.get("issues") or []]
    items += [f"<li>static warning — {esc(warning)}</li>"
              for warning in finding.get("warnings") or []]
    items += [f"<li><b>console error</b> — {esc(render.truncate(error))}</li>"
              for error in rendered.get("console_errors") or []]
    items += [f"<li><b>uncaught exception</b> — {esc(render.truncate(error))}</li>"
              for error in rendered.get("page_errors") or []]
    items += [
        f"<li><b>dead nav</b> — <code>{esc(nav.get('href'))}</code> expected "
        f"<code>{esc(nav.get('expected'))}</code>, activated "
        f"<code>{esc(nav.get('activated'))}</code></li>"
        for nav in rendered.get("nav_results") or [] if not nav.get("ok")
    ]
    items += [
        f"<li><b>interaction failure</b> — {esc(failure.get('action'))} "
        f"<code>{esc(failure.get('target'))}</code>: "
        f"{esc(render.truncate('; '.join(failure.get('errors') or [])))}</li>"
        for failure in interactions.get("failures") or []
    ]
    header = f"<h3>Code track — score {render.score(finding.get('code_score'))}</h3>"
    if not items:
        return header + (
            "<p class='muted small'>No findings: this row passed every deterministic "
            "check.</p>"
        )
    return header + f"<ul>{''.join(items)}</ul>"


def deliverables_block(row: model.Row, stage: model.Stage, *, links: Links) -> str:
    """What the agent actually produced — rendered, not merely referenced."""
    parts = []
    if not row.deliverables:
        parts.append("<p class='muted small'>No deliverable was captured for this row.</p>")
    for deliverable in row.deliverables:
        href = links.deliverable_href(row.row_id, deliverable.filename)
        source_id = f"src-{row.row_id}-{deliverable.filename.replace('.', '-')}"
        head = (
            f"<h3>{esc(deliverable.filename)} "
            f"<span class='muted small'>{esc(_size(deliverable.size_bytes))}</span></h3>"
        )
        if deliverable.kind == "html":
            preview = links.preview(deliverable) if links.preview else _iframe(href)
            source = (
                f"<button class='ghost' type='button' "
                f"data-toggle-target='{esc(source_id)}'>show source</button>"
                if links.show_source else ""
            )
            body = (
                f"<pre class='block hidden' id='{esc(source_id)}'>"
                f"{esc(_read_text(deliverable))}</pre>"
                if links.show_source else ""
            )
            parts.append(
                head
                + "<div class='controls'>"
                + source
                + ("" if links.detached
                   else f"<a class='small' href='{esc(href)}'>open the file</a>")
                + "</div>"
                + preview
                + body
            )
        elif deliverable.kind == "markdown":
            shown = (
                f"<pre class='block'>{esc(_read_text(deliverable))}</pre>"
                if links.show_source
                else "<p class='muted small'>Markdown deliverable — open the file to read it.</p>"
            )
            parts.append(
                head + shown
                + ("" if links.detached
                   else f"<a class='small' href='{esc(href)}'>open the file</a>")
            )
        else:
            parts.append(
                head + ("<p class='muted small'>Not previewable.</p>" if links.detached
                        else f"<p><a href='{esc(href)}'>{esc(deliverable.filename)}</a></p>")
            )
    if row.log_path is not None and not links.detached:
        parts.append(
            f"<p class='small'><a href='{esc(links.log_href(row.row_id, stage.agent_token))}'>"
            "dispatch transcript</a></p>"
        )
    elif row.log_path is not None:
        parts.append(
            "<p class='small muted'>A dispatch transcript exists in the run folder "
            "(not available from this standalone file).</p>"
        )
    return "".join(parts)


def _iframe(href: str) -> str:
    """A preview that cannot run scripts and cannot reach its parent."""
    return (
        f'<iframe class="preview" sandbox loading="lazy" src="{esc(href)}" '
        'title="rendered deliverable"></iframe>'
    )


def _read_text(deliverable: model.Deliverable, limit: int = 200_000) -> str:
    """The deliverable's source, bounded. Escaped by the caller, always."""
    try:
        return deliverable.path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return "(could not be read)"


def _size(count: int) -> str:
    if count < 1024:
        return f"{count} B"
    if count < 1024 * 1024:
        return f"{count / 1024:.0f} KB"
    return f"{count / 1024 / 1024:.1f} MB"



def stage_commands(run: model.Run, stage: model.Stage) -> str:
    return (
        '<section class="card"><h2>Re-judge just this phase</h2>'
        + command_block(
            f"./evals/grading/grade.sh rejudge {run.dataset_run_id} "
            f"--agents {stage.agent_id}",
            "Re-scores this phase's stored responses only. LIVE: judge tokens.",
        )
        + "</section>"
    )


# ── prompt diff ───────────────────────────────────────────────────────────


def prompt_diff(before: str, after: str, *, before_label: str, after_label: str) -> str:
    """A line diff of two captured prompts — what a score delta actually was."""
    lines = list(
        difflib.unified_diff(
            before.splitlines(), after.splitlines(),
            fromfile=before_label, tofile=after_label, lineterm="", n=2,
        )
    )
    if not lines:
        return "<p class='muted small'>These two versions are byte-identical.</p>"
    out = []
    for line in lines[:600]:
        if line.startswith("+"):
            out.append(f'<span class="add">{esc(line)}</span>')
        elif line.startswith("-"):
            out.append(f'<span class="del">{esc(line)}</span>')
        else:
            out.append(f'<span class="ctx">{esc(line)}</span>')
    return f'<pre class="block diff">{"".join(out)}</pre>'
