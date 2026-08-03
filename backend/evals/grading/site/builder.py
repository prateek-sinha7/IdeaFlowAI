"""Read every run folder, consolidate it, and write the two files that result.

Exactly two artifacts are produced for the whole evals tree, both at the runs
root:

- `evals_data.json` — every run's artifacts folded into one dataset
- `report.html`     — the one report, rendering that dataset

Deliberately **not** one report per run. An earlier shape wrote a `run.html`
and a page per stage into every run folder, which put a second copy of the
markdown set's contents beside it — 161 generated files across 23 runs, and
nothing that could answer a question spanning two of them. Drill-down now
happens inside the single report.

Two guarantees this module owns:

- **A bad run folder never fails the build.** It is classified `error`, badged
  in the report, and the other runs render normally.
- **A failing build never fails a grading run**, or costs it its markdown
  report. A run that spent real tokens must not be reported as failed because
  a rendering helper raised.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from evals.grading.site import aggregate, dataset, model, views

logger = logging.getLogger(__name__)

REPORT_NAME = "report.html"

# Written by the superseded per-run shape. Removed on sight so a tree built by
# an older version does not keep serving stale pages beside the real report.
LEGACY_PAGES = ("run.html", "index.html")


@dataclass
class BuildReport:
    """What one build did — printed by the CLI, asserted by the tests."""

    report: Path | None = None
    data: Path | None = None
    scanned: int = 0
    included: int = 0
    errors: list[str] = field(default_factory=list)
    removed: int = 0

    def line(self) -> str:
        return (
            f"scanned {self.scanned} · counted {self.included} · "
            f"errors {len(self.errors)}"
            + (f" · removed {self.removed} stale page(s)" if self.removed else "")
        )


# ── the public surface ────────────────────────────────────────────────────


def build_site(runs_root: Path, *, force: bool = False) -> Path:
    """Rebuild the consolidated dataset and the one report. Returns `report.html`."""
    return build(runs_root, force=force).report


def build(runs_root: Path, *, force: bool = False) -> BuildReport:
    """The same build, with the counts a caller may want to print.

    `force` is accepted and ignored: there is one output file covering every
    run, so there is nothing to skip and no staleness to reason about. Keeping
    the flag means the CLI and its tests did not need a special case.
    """
    runs_root = Path(runs_root)
    site = model.discover(runs_root)
    report = BuildReport(
        scanned=len(site.all_runs),
        included=sum(len(workflow.included) for workflow in site.workflows),
        errors=[
            f"{run.dataset_run_id}: {run.class_reason}"
            for run in site.all_runs
            if run.run_class == model.CLASS_ERROR
        ],
    )

    aggregates = {
        workflow.name: aggregate.build(workflow) for workflow in site.workflows
    }
    report.data = dataset.write(site)
    path = runs_root / REPORT_NAME
    path.write_text(views.render_report(site, aggregates), encoding="utf-8")
    report.report = path
    report.removed = _remove_legacy_pages(site)
    return report


def rebuild_for_run(run_dir: Path) -> Path | None:
    """Refresh the whole report after one run finished, never raising.

    Called at the end of `markdown_report.write_report`, which is on the path
    of every run, rejudge and code pass. A reporting bug must never be able to
    fail work that already succeeded, so everything is caught here — the
    explicit `grade.sh dashboard` command is where errors are meant to surface.

    The report covers every run, so "for this run" means: rebuild the report
    that now includes it.
    """
    try:
        runs_root = _runs_root_of(Path(run_dir))
        return build(runs_root).report
    except Exception as error:  # noqa: BLE001 - reporting is never load-bearing
        logger.warning("report not rebuilt after %s: %s", run_dir, error)
        return None


def _runs_root_of(run_dir: Path) -> Path:
    """`<...>/.runs` for a run folder, whichever depth it sits at.

    A run normally lives at `.runs/<workflow>/<id>/`, but `rebuild_for_run` is
    also called for folders outside that layout (tests, rescued fixtures), so
    the parent is used when no `.runs` ancestor exists.
    """
    for parent in run_dir.parents:
        if parent.name == ".runs":
            return parent
    return run_dir.parent.parent


def _remove_legacy_pages(site: model.Site) -> int:
    """Delete the per-run pages the superseded shape wrote. Never fatal."""
    removed = 0
    for run in site.all_runs:
        reports = run.run_dir / "reports"
        if not reports.is_dir():
            continue
        stale = [reports / name for name in LEGACY_PAGES]
        stale += [
            reports / f"{stage.agent_token}.html" for stage in run.stages
        ]
        for path in stale:
            try:
                if path.is_file():
                    path.unlink()
                    removed += 1
            except OSError:  # a page we cannot delete is not worth failing over
                continue
    root_index = Path(site.runs_root) / "index.html"
    try:
        if root_index.is_file():
            root_index.unlink()
            removed += 1
    except OSError:
        pass
    return removed
