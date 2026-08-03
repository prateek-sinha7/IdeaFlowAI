"""The grading dashboard: every run in `.runs/` as one browsable static site.

A rendering, never a computation. Every number shown here is imported from the
module that owns it — `grades` for the blended score, `compare` for prompt
version verdicts, `code_grader` for the code track — because a harness whose
purpose is catching scoring inconsistency cannot ship two implementations of
its own scoring.

Free and offline: no model is called, no network request is made, and no page
this package writes loads anything external.

**One report for the whole tree**, not one per run: `.runs/report.html`, built
from `.runs/evals_data.json` — every run's artifacts consolidated into a single
dataset. Clicking a run drills into it in place.

Layers, and the rules that keep them apart:

- `model` / `aggregate` — read and classify run folders. **No HTML.**
- `dataset` — fold every run into the one serialisable structure.
- `charts` / `pages` / `views` — view-models in, strings out. **No file I/O.**
- `export` — one run as a self-contained file, on demand only.
- `builder` — scans, consolidates, and does all the writing.
"""

from evals.grading.site.builder import build_site, rebuild_for_run
from evals.grading.site.dataset import build as build_dataset
from evals.grading.site.export import export_run

__all__ = ["build_site", "rebuild_for_run", "build_dataset", "export_run"]
