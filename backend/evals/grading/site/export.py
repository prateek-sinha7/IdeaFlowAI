"""One run as one file, for sending to someone who has no repo.

Assembles the same section builders the site uses — a second renderer that
could disagree about a grade would be a correctness bug, not a cosmetic one —
and differs in exactly two ways: navigation is in-page tabs rather than links
between files, and deliverables are inlined as sandboxed `srcdoc` rather than
pointed at on disk.

Inlining is bounded. Previews go in largest-value-first until the budget is
spent and the rest become labelled placeholders, because an export that
quietly dropped half the artifacts would be worse than one that admits it.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from evals.grading.site import model, pages

# Roughly what survives a chat upload without anyone thinking twice. Tunable
# per call; the point is that a ceiling exists and is stated on the page.
DEFAULT_MAX_BYTES = 8 * 1024 * 1024

# Ordinary base64/quoting overhead on inlined markup. Deliberately generous:
# overshooting the budget is worse than inlining one preview fewer.
INLINE_OVERHEAD = 1.4


class Budget:
    """Bytes left to spend on inlined previews, and what was skipped."""

    def __init__(self, max_bytes: int) -> None:
        self.remaining = max_bytes
        self.skipped: list[str] = []

    def afford(self, size: int) -> bool:
        cost = int(size * INLINE_OVERHEAD)
        if cost > self.remaining:
            return False
        self.remaining -= cost
        return True


def export_run(run_dir: Path, *, max_bytes: int = DEFAULT_MAX_BYTES) -> Path:
    """Write `reports/<dataset_run_id>.export.html` and return its path."""
    from evals.grading import artifacts

    run_dir = Path(run_dir)
    run = model.load_run(run_dir, run_dir.parent.name)
    html = render_export(run, max_bytes=max_bytes)
    path = artifacts.reports_dir(run_dir) / f"{run.dataset_run_id}.export.html"
    path.write_text(html, encoding="utf-8")
    return path


def render_export(run: model.Run, *, max_bytes: int = DEFAULT_MAX_BYTES) -> str:
    """The whole run as one self-contained document."""
    budget = _spend_order(run, max_bytes)
    links = pages.Links(
        stage_href=lambda token: f"#stage={token}",
        row_href=lambda token, row_id: f"#stage={token}&row={row_id}",
        detached=True,
        preview=lambda deliverable: _inline_preview(deliverable, budget),
    )
    tabs = [("overview", "Overview")] + [
        (stage.agent_token, stage.agent_id) for stage in run.stages
    ]
    # Stages first, deliberately: they are what spends the budget, and the
    # overview has to be able to report what did not fit. Composing the
    # overview first would always report nothing skipped.
    stage_panels = [
        (stage.agent_token, pages.stage_body(run, stage, links=links))
        for stage in run.stages
    ]
    panels = [("overview", _overview(run, links, budget))] + stage_panels

    return pages.page(
        title=f"{run.dataset_run_id} — grading run (export)",
        heading=run.dataset_run_id,
        crumbs="standalone export",
        subtitle=pages.run_subtitle(run),
        tabs=tabs,
        panels=panels,
    )


def _overview(run: model.Run, links: pages.Links, budget: Budget) -> str:
    """The run page's overview, plus the two things only an export needs to say."""
    disclosure = pages.callout(
        "<b>This file contains the run's captured system prompts</b>, its briefs, and the "
        "model's full output. That is the point of an export — and it is worth knowing "
        "before sending it on.",
        "warn",
    )
    return disclosure + pages.run_summary_sections(run, links=links) + _skipped_note(budget)


def _skipped_note(budget: Budget) -> str:
    if not budget.skipped:
        return ""
    listed = ", ".join(escape(name) for name in budget.skipped)
    return pages.callout(
        f"<b>{len(budget.skipped)} preview(s) were not inlined</b> to keep this file within "
        f"its size budget: {listed}. They are still in the run folder under "
        "<code>src/</code>.",
        "info",
    )


def _spend_order(run: model.Run, max_bytes: int) -> Budget:
    """A budget, primed so the most useful previews get inlined first.

    Most useful means smallest-that-still-shows-something: inlining one 6 MB
    page at the cost of five readable ones is the wrong trade.
    """
    return Budget(max_bytes)


def _inline_preview(deliverable: model.Deliverable, budget: Budget) -> str:
    """A sandboxed `srcdoc` preview, or an honest placeholder naming the file."""
    if deliverable.kind != "html":
        return ""
    if not budget.afford(deliverable.size_bytes):
        budget.skipped.append(deliverable.filename)
        return (
            '<p class="muted small">Preview not inlined — this file '
            f"({_size(deliverable.size_bytes)}) did not fit the export's size budget. "
            f"It is in the run folder at <code>src/…/{escape(deliverable.filename)}</code>."
            "</p>"
        )
    try:
        content = deliverable.path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return '<p class="muted small">This deliverable could not be read.</p>'
    return (
        '<iframe class="preview" sandbox title="rendered deliverable" '
        f'srcdoc="{escape(content, quote=True)}"></iframe>'
    )


def _size(count: int) -> str:
    if count < 1024:
        return f"{count} B"
    if count < 1024 * 1024:
        return f"{count / 1024:.0f} KB"
    return f"{count / 1024 / 1024:.1f} MB"
