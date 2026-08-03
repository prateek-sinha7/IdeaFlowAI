# `site/` — the grading dashboard

Consolidates every run folder under `.runs/` into **two files, for the whole evals tree**:

```
.runs/evals_data.json   every run's artifacts folded into one dataset
.runs/report.html       the one report, rendering that dataset
```

Nothing is written into a run folder. Clicking a run in the report opens its drill-down in
place — overview, phase table, stage × row matrix, then every stage with its rows, the judge's
reasoning, and a sandboxed preview of what was built.

Build it with `./evals/grading/grade.sh dashboard`. **Free**: it reads artifacts already on
disk, calls no model, and dispatches nothing. It also rebuilds automatically at the end of any
run / rejudge / code pass, so it is never stale.

`grade.sh dashboard --export <run-id>` additionally writes one run as a standalone file, for
sending to someone with no repo. That is opt-in and the only other artifact this package can
produce.

## The rules this package must not break

Each is enforced by a test in `backend/tests/unit/test_grading_site_*.py`, not by convention.

| # | Rule | Why |
|---|---|---|
| **B1** | `model.py` / `aggregate.py` emit no HTML | The read layer is testable without parsing markup |
| **B2** | `pages.py` / `charts.py` / `views.py` do no file I/O | View-models in, strings out; only `builder` and `export` write |
| **B3** | Every path under a run folder comes from `artifacts.*` | One owner of run paths; hand-built paths are how `report` lost track of runs once before |
| **B4** | No grade, blend, cap or noise verdict is computed here or in JavaScript | A harness for catching scoring inconsistency cannot ship two implementations of its own scoring |
| **B5** | Every interpolated value passes `pages.esc()` | Judge rationales quote agent output, and the agents emit HTML documents — untrusted markup is a certainty here, not a risk |
| **B6** | The report and the export call the same section builders | Two renderers that could disagree about a grade would be a correctness bug |
| **B7** | Output is byte-deterministic — no render timestamps, no counter IDs | Two builds of unchanged runs produce identical bytes, so any diff is a real change |
| **B8** | No `fetch()`, no external asset, no remote reference | These pages open by double-click from `file://`, where `fetch()` is blocked outright |
| **B9** | One report for the tree — never a page per run | An earlier shape wrote 161 files across 23 runs, duplicating the markdown set and answering nothing that spanned two runs |

## Where the numbers come from

Nothing here is re-derived:

| Value | Owner |
|---|---|
| Blended grade, letter, per-cell values | `grades.compute_overall` / `letter_grade` / `cell_value` |
| Prompt-version grouping, deltas, noise band | `compare.group_by_prompt` / `noise_band` |
| Code score, judge+code blend | `code_grader.read_findings` / `blended_score` |
| Judge-failure detection | `model.scoring.judge_errored` / `judge_error_reason` |
| Number formatting | `render.py` |

The only arithmetic this package owns is aggregation *across* runs — means, spreads, and
chronological grouping, in `aggregate.py`.

## Modules

| File | Does |
|---|---|
| `model.py` | Reads and classifies one run folder into the view-model; derives `cell_kind` |
| `dataset.py` | Folds every run into the one serialisable dataset written as `evals_data.json` |
| `aggregate.py` | Trends, dimension grids, the cross-run matrix, cost, prompt versions |
| `charts.py` | Hand-emitted inline SVG: line, bar, distribution, grade-band track, heat cells |
| `pages.py` | `esc()`, the page shell, and every section builder — including `run_panel` |
| `views.py` | The report: the run list, the five cross-run views, and a panel per run |
| `export.py` | One run as one self-contained file, under a size budget |
| `builder.py` | Scans, consolidates, writes the two files, and removes pages left by the superseded per-run shape |
| `assets.py` | The CSS and JS, as string constants |

## Two things worth knowing

**`cell_kind` is the point of the matrix.** Four distinct failures all score 0 —
a dispatch error, a failed precheck, a chain broken upstream, and a judge that fell over — and an
average erases the difference. `model.cell_kind` separates them and the matrix draws each with
its own glyph, so a phase that scored 0 because its *upstream* broke is never mistaken for one
whose output was bad.

**The prompt hash lives on the run entries, not the score artifact.** `system_prompt_hash` is
stamped on each dispatched row (`<token>_run.json`), so `model._prompt_hash` reads it from there.
And a captured prompt is only attached to a version when re-hashing the text reproduces that
version's hash — a folder can hold a prompt whose hash is not the one its rows recorded, and
showing it anyway would present two unrelated prompts as "what changed between these versions".

## Rollback

Generated output is disposable:

```bash
rm -f .runs/report.html .runs/evals_data.json
```

Nothing else in a run folder is ever written, moved or deleted by this package.
