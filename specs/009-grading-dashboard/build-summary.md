# Build Summary — 009-grading-dashboard

**Run**: 2026-07-30 · all 24 tasks (T1–T24) · **Status: complete**

> **Revised after your review.** The first build wrote a `run.html` plus a page per stage into
> every run folder — 161 generated files across 23 runs, sitting beside the markdown set and
> duplicating it. That was wrong: the instruction was one report for the whole evals tree.
> Reworked to consolidate every run's artifacts into **one dataset** (`.runs/evals_data.json`)
> rendered by **one report** (`.runs/report.html`), with drill-down happening in place. The
> superseded per-run pages are deleted on sight by the builder, so a tree built by the earlier
> version cleans itself up. See "The consolidation" below.

Every task in this feature is free and offline. Nothing in this build dispatched an agent, called
a judge, or spent a token. Verification ran against the **23 real run folders** in
`backend/evals/grading/.runs/prototype/` plus fixtures built in the test suite.

---

## Tasks completed

| Phase | Tasks | What landed |
|---|---|---|
| 1 Foundation | T1 | `grades.py` extracted from `markdown_report.py`, re-exported |
| 2 Read layer | T2–T6 | `site/model.py`, `site/aggregate.py` — discovery, classification, view-model, `cell_kind`, matrix, cross-run aggregation |
| 3 Drill-down | T7–T11 | `site/pages.py`, `site/assets.py` — `esc()`, shell, `run_panel`, stage sections, row detail, sandboxed previews |
| 4 Report | T12–T18 | `site/builder.py`, `site/dataset.py`, `site/views.py`, `site/charts.py` — consolidation, run list, all five views |
| 5 Export | T19 | `site/export.py` — one self-contained file per run, on demand, budgeted |
| 6 Wiring | T20–T24 | `grade.sh dashboard`, auto-rebuild, docs, acceptance |

One acceptance box is left **unchecked, deliberately**: `site/` coverage > 80% could not be
measured — neither `coverage` nor `pytest-cov` is installed in this environment. The suite itself
is 176 tests over the new code; the number is simply unverified, and is not claimed.

---

## Files changed

### New

| File | Lines | Purpose |
|---|---|---|
| `backend/evals/grading/grades.py` | 133 | The blended-score arithmetic, extracted so `site/` can import it without a cycle |
| `backend/evals/grading/site/__init__.py` | 27 | Public surface |
| `backend/evals/grading/site/model.py` | ~580 | One run folder → view-model; classification; `cell_kind`; matrix |
| `backend/evals/grading/site/aggregate.py` | ~450 | Trends, dimension grids, cross-run matrix, cost, prompt versions |
| `backend/evals/grading/site/dataset.py` | ~215 | Every run folded into the one `evals_data.json` |
| `backend/evals/grading/site/pages.py` | ~900 | `esc()`, page shell, `run_panel`, every shared section builder |
| `backend/evals/grading/site/views.py` | ~490 | The report: run list, five views, a panel per run |
| `backend/evals/grading/site/charts.py` | ~290 | Inline-SVG primitives, no library |
| `backend/evals/grading/site/export.py` | ~145 | Single-file export with a size budget, on demand |
| `backend/evals/grading/site/builder.py` | ~155 | Scan, consolidate, write the two files, remove superseded pages |
| `backend/evals/grading/site/assets.py` | ~470 | CSS + JS constants |
| `backend/evals/grading/site/README.md` | — | The package's rules (B1–B8) |

### Modified

| File | Change |
|---|---|
| `backend/evals/grading/markdown_report.py` | Imports/re-exports from `grades`; `write_report` now calls `site.builder.rebuild_for_run` (best-effort) at its end |
| `backend/evals/grading/grade_runner.py` | `webbrowser` import, `_add_dashboard_parser`, `run_dashboard()`, dispatch entry |
| `backend/evals/grading/grade.sh` | `dashboard)` case; header help lines; help range `2,57p` → `2,61p` |
| `backend/evals/grading/README.md` | New "The report" section |

**Not touched**: `scoring.py`, `judge.py`, `model_grader.py`, `code_grader.py`, `config.py`,
`calibrate.py`, any rubric, any dataset, any `AGENT.md`. **This feature changes no score.**

---

## Tests added

| File | Tests | Covers |
|---|---|---|
| `tests/unit/test_grading_grades.py` | 31 | The extraction is behaviour-preserving; bands; cell values; `compute_overall` |
| `tests/unit/test_grading_site_model.py` | 47 | Discovery, classification, view-model, degraded folders, `cell_kind`, matrix, aggregation |
| `tests/unit/test_grading_site_pages.py` | 60 | Escaping/injection, determinism, self-containment, sandboxing, run panel, stage sections, charts, all five views |
| `tests/unit/test_grading_site_export.py` | 11 | Export ≡ run panel fidelity, budget, placeholders, disclosure |
| `tests/unit/test_grading_site_builder.py` | 18 | Two-file output, no per-run pages, error isolation, legacy cleanup, determinism, auto-rebuild safety |

**176 new tests**, all passing.

---

## Commands run

```bash
cd backend

# every grading test, including the untouched markdown-report regression gate
python3.11 -m pytest tests/unit/ -q -k grading
# → 671 passed, 7 skipped, 2 failed (both pre-existing — see below)

# acceptance, against the 23 real run folders
./evals/grading/grade.sh dashboard
./evals/grading/grade.sh dashboard --export golden-mission-control   # opt-in extra
```

### Measured results (after the consolidation)

| Check | Target | Measured |
|---|---|---|
| Files generated for the whole tree | one report | **2** — `report.html` + `evals_data.json` |
| HTML left in any run folder | none | **0** (117 superseded pages removed on first rebuild) |
| Build, 23 runs | < 10 s | **0.60 s** |
| Determinism | byte-identical | **✓** report and dataset both, across rebuilds |
| Self-containment | zero external refs | **✓** 0 violations |
| Sandboxing | every preview | **✓** 173 iframes, all `sandbox`, none with `allow-scripts` |
| Report size | reasonable | **2.3 MB** (dataset 2.5 MB) |
| Export size | ≤ 8 MB | **4.0 MB**, 10 previews inlined |
| Grade fidelity | HTML ≡ markdown | **✓** golden: `compute_overall` 92.537 → **A / 92.5** in `report.md` and `report.html` |
| Generated output tracked by git | none | **✓** 0 |

---

## Deviations from plan / design

1. **`grades.cell_value` is public** (design called it `_cell_value`). `site/` needs it, and a
   cross-package import of a private name is worse than renaming. `_cell_value` remains as an
   alias so nothing that reached for it breaks.

2. **`site/views.py` and `site/dataset.py` were split out** (design listed six modules; there are
   eight). `pages.py` reached ~930 lines carrying both the drill-down and the dashboard, against a
   coding-style cap of 800; `dataset.py` came from the consolidation. Both splits are along real
   seams: `pages` renders one run, `views` renders across runs, `dataset` owns the one structure
   they share.

3. **The auto-rebuild uses a call-time import** inside `write_report`. `site` imports
   `markdown_report`'s siblings, so a module-level import would re-introduce a cycle even after
   the `grades` extraction. The import sits at the single call site, commented.

4. **The `grade.sh` help range needed updating** (`sed -n '2,57p'` → `2,61p`). Not in the plan —
   adding four header lines would silently have truncated the help output.

5. **No incremental rebuild, and `--force` is now a no-op.** The design specified an mtime-based
   skip per run; with one output file spanning every run there is nothing to skip. The flag is
   accepted and ignored so the CLI and its tests needed no special case. The whole build is 0.6 s.

6. **Spec §3 and the contracts still describe the per-run site.** They are the record of what was
   designed, and this summary is the record of what shipped; `spec.md` should be reconciled before
   the next spec builds on it.

---

## Two defects found and fixed during the build

**The prompt-version view was empty on real data.** `system_prompt_hash` is stamped on each
dispatched **row** (`<token>_run.json`), not on the stage's `score.hashes` where the design
assumed it lived. Reading only `score.hashes` made all 13 counted runs collapse into one
`unknown` version, which silently emptied the entire did-my-edit-help view — the feature's
headline capability. `model._prompt_hash` now reads it from the run entries, preferring a value
on the score artifact if a future run records one there. Regression tests added.

> Worth knowing: `markdown_report._first_prompt_hash` reads the same missing key, so the
> markdown report's "system prompt" row has always rendered as a dash. **Left alone** — it is
> outside this spec's scope and changes an implemented report — but it is a real, separate bug.

**A captured prompt could be attached to the wrong version.** Several run folders record the
sha256 of the *empty string* as their prompt hash while still holding a real captured prompt
file. Pairing them by folder would have shown two unrelated prompts as "what changed between
these versions" — a confident, wrong answer. `aggregate._prompt_texts` now admits a text only
when re-hashing it reproduces the version's hash; otherwise the diff control is disabled with the
reason stated on the page.

Also fixed while building: an unreachable string continuation in `code_findings_block`; nested
f-strings with backslashes (invalid on Python 3.11); the export's "skipped previews" note being
composed before the previews that fill it; and the diff picker defaulting both selects to the
same version, which opened it on an empty panel.

---

## Blockers and follow-ups

| # | Item | Status |
|---|---|---|
| 1 | `tests/unit/test_grading_config.py` — 2 failures (`test_small_dataset_is_two_interaction_briefs`, `..._says_its_scores_are_not_comparable`) | **Pre-existing, not caused by this work.** `prototype_small.json` in the working tree now has 3 rows; the test still asserts 2. It is an in-progress dataset change of yours. Untouched. |
| 2 | Full `tests/unit/` run | **Completed: 1807 passed, 54 failed, 7 skipped (883 s).** All 54 are **pre-existing and unrelated** — see the attribution below. |
| 3 | `site/` coverage | **Unmeasured** — no `coverage` / `pytest-cov` in this environment. |
| 4 | `markdown_report._first_prompt_hash` reads a key that is never present | Real bug, out of scope, left as found. |
| 5 | C6 (markdown deliverables as escaped monospace) | Shipped as recommended. A rendered-markdown toggle remains a later option. |

---

## The 54 full-suite failures — attributed

The full `tests/unit/` run finished at **1807 passed, 54 failed, 7 skipped (883 s)**. None are
caused by this feature, established three ways rather than assumed:

1. **No import path exists.** Every failing module (`test_run_pipeline_validation.py`,
   `test_user_workflows.py`, `test_workflows_api.py`, `test_run_revision_fe_contract.py`, …) is
   part of the agent-pipeline / workflow-API layer. None of them import `evals` at all, so no
   code path reaches anything this build touched.

2. **They already fail on clean `HEAD`.** A throwaway worktree at `HEAD` (no `site/` package, none
   of this work present) runs the same four modules to **15 failed / 86 passed**. The failures are
   there before this feature exists. Sample: `test_list_carries_launchable_flags` asserts
   `user_stories` carries display name `"User Stories"` and gets `"Generate product requirements"`
   — an authored-metadata mismatch, nothing to do with grading.

3. **The change footprint is confined.** `git status` shows this work touched only
   `backend/evals/grading/**`, `backend/tests/unit/test_grading_*`, and `specs/009-*`.

The same four modules run **17 failed / 84 passed** in the working tree versus **15 / 86** on
clean `HEAD` — a 2-test delta, both in `test_run_revision_fe_contract.py`. Those are attributable
to your other uncommitted changes (`prototype-revision-agent/AGENT.md`, `tests/agents/conftest.py`,
`tests/agents/test_loader.py` — 121 lines across the three), not to this feature.

Also worth recording: those modules take **3.35 s on clean `HEAD` and 123 s in the working tree**.
That is the same `.env`/Postgres slowdown documented on spec 007 (2.6 s vs 482 s), and it is why
the first full-suite attempt looked like a hang rather than a long run.

---

## The consolidation (revision)

| | Before | Now |
|---|---|---|
| Files generated | 161 across 23 run folders | **2**, both at `.runs/` |
| Per run | `run.html` + one page per stage | nothing — run folders hold only their markdown |
| Data | each page re-read the artifacts it needed | one `evals_data.json` every view projects from |
| Drill-down | navigate between files | in place: click a run → phases → rows → preview |
| Cross-run questions | not answerable from a run page | the five views, on the same page as the runs |

**Why one dataset matters beyond tidiness**: a page that re-reads artifacts is a page that can
disagree with its neighbours about what a run scored. Consolidating first makes every view — the
trend, the matrix, the row detail — a projection of exactly the same numbers.

New module `site/dataset.py` builds and writes it; `builder.py` now produces only those two files
and removes any page left by the earlier shape. `pages.render_run_page` / `render_stage_page` were
deleted rather than left as dead code; `pages.run_panel` renders the drill-down as a fragment of
the one report.

Deliverable **source** is no longer inlined in the report (previews still render, and the file is
one click away): with every run in one file, inlining each artifact's text would have multiplied
the report by every prototype ever built. The single-run `--export` still inlines everything,
under its budget.

Measured after the rework, on your 23 real runs:

| Check | Result |
|---|---|
| Files generated | **2** — `report.html` (2.3 MB), `evals_data.json` (2.5 MB) |
| Stale per-run pages removed on first rebuild | **117** |
| HTML left in any run folder | **0** |
| Build time | **0.60 s** |
| Determinism | byte-identical across rebuilds (report and dataset) |
| Run panels / stage sections / expandable rows / previews | 23 / 93 / 165 / 173 |
| External references | **0** |
| Grade fidelity | golden: `compute_overall` 92.537 → **A / 92.5** in both `report.md` and `report.html` |
| Grading tests | **671 passed** (2 pre-existing dataset failures) |

---

## How to see it

```bash
cd backend
./evals/grading/grade.sh dashboard --open
```

One file opens. Pick a run from the list → it drills in place → scroll to the weakest phase →
click a row id. The judge's criticism and the prototype it is criticising are on the same screen.
