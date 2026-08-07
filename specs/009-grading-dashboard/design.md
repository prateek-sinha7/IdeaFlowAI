# Execution Design: The Grading Dashboard

**Spec**: [`specs/009-grading-dashboard/spec.md`](spec.md)
**Plan**: [`specs/009-grading-dashboard/plan.md`](plan.md)
**Created**: 2026-07-30
**Status**: Designed

---

## 0. Design premise

Everything here follows from one property: **the dashboard owns no truth**. It reads files the
grading harness already wrote, imports every number from the module that owns it, and writes only
disposable HTML. That premise dictates the component boundaries (§2), makes every failure mode
recoverable by deleting output and rebuilding (§5), and reduces rollback to deleting a package
(§7).

The second-order constraint is the medium: these pages are opened by double-click from `file://`,
which forbids `fetch()`, external assets, and any secure-context API — and they render untrusted
HTML produced by the agents under test, which forbids unescaped interpolation anywhere.

---

## 1. Build Slices

Six slices, each independently verifiable. Slices 1–2 alone beat the markdown reports for daily
use; the analytics build on top.

### Slice 0 — Foundation: `grades.py` extraction

**Goal**: give `site/` the grade arithmetic without creating an import cycle.

Move `compute_overall`, `letter_grade`, `GRADE_BANDS`, `FAIL_GRADE`, `_cell_value` out of
`markdown_report.py` into `grades.py`, **verbatim**. `markdown_report` re-exports all five so no
existing import, call site, or test changes.

**Done when**: `test_grading_markdown_report.py` passes **unmodified**, and `site/` can import
`grades` with no cycle.

**Why first and alone**: it touches implemented, load-bearing code. Isolating it means a
regression here is unambiguous rather than tangled with new features.

---

### Slice 1 — Core logic: the read layer (`site/model.py`)

**Goal**: turn a `.runs/` tree into the view-model of [`data-model.md`](data-model.md), with no
HTML anywhere in the module.

- Discover workflows and runs; sort newest-first (folder names are timestamp-prefixed, so lexical
  descending *is* chronological).
- Classify each run — `error` → `copy` → `reference` → `partial` → `run`, in that order, each
  carrying its `class_reason`.
- Build `RunModel` / `StageModel` / `RowModel`, joining `score` ⇄ `grade` ⇄ `run` ⇄ `code_findings`
  by `row_id`, tolerating the three historical id field names.
- Derive `cell_kind` per row — the distinction four zero-scoring failures otherwise lose.
- Build `MatrixModel` at run scope, and aggregations (trend series, dimension grids, cost series,
  cross-run matrix) at workflow scope over `included` runs only.
- Wrap `compare.group_by_prompt()` / `noise_band()` into `PromptVersionModel` **without altering a
  value**.

**Done when**: fixture tests cover the happy path and every degenerate case; matrix cells are
proven equal to `compute_overall()`'s cells; prompt verdicts are proven to be pass-through.

---

### Slice 2 — Interface: run and stage pages (`site/pages.py`, `site/assets.py`)

**Goal**: the drill-down, and with it the feature's whole reason for existing — the judge's
criticism next to the thing being criticised.

- `_esc()` and the section builders every page and the export share.
- Run page: grade hero, phase table, stage × row matrix, warnings, not-run, signals, clusters,
  provenance, copy-able commands.
- Stage page: warnings, baseline, spread, dimensions, tokens, the rows table, expandable row
  detail (rationale, strengths, weaknesses, evidence, caps, code findings), sandboxed deliverable
  preview, escaped markdown, log link.
- CSS/JS: theme (pre-paint, no flash), sort, filter chips, search, expand, deep links, print.

**Done when**: Story 3 is demonstrable end-to-end on `golden-mission-control`, and the escaping,
determinism, and self-containment tests pass.

---

### Slice 3 — Interface: dashboard shell (`site/builder.py`, dashboard section of `pages.py`)

**Goal**: the entry point — every run, one page.

Scan, classify, render the run list (sortable, filterable, searchable, "show excluded"), badge
non-`run` classes, isolate unreadable folders behind an error badge.

**Done when**: all 20 real folders list correctly, with `golden-mission-control` badged
`reference` and the `-copy` folder badged `copy`.

---

### Slice 4 — Interface: the five views (`site/charts.py` + dashboard sections)

Ordered by what nothing else in the repo can answer:

| Order | View | Why here |
|---|---|---|
| 4a | **V2 Prompt version history** + prompt diff | Answers *did my edit help* — the loop the harness feeds |
| 4b | **V4 Stage × row matrix** (cross-run) | Separates a weak prompt from a weak brief |
| 4c | **V1 Quality trend** | References as ceiling/floor lines, not trend points |
| 4d | **V3 Dimension heatmap** | Chronic weakness, worst first |
| 4e | **V5 Cost & code health** | Agent/judge tokens; browser findings trended |

`charts.py` lands with 4a and is extended per view: line, bar, heatmap cell, distribution strip,
grade-band track. Every charted value is also emitted as text.

---

### Slice 5 — Interface: the one-file export (`site/export.py`)

Assemble the **same section builders** into one file, with in-page tabs and `srcdoc` previews
inside the size budget, value-ordered, over-budget previews becoming labelled placeholders. State
on the page that it embeds captured system prompts.

**Done when**: an export opened from an unrelated directory with no network shows grade, phase
table, and row scores **identical** to that run's `run.html` — asserted, not eyeballed.

---

### Slice 6 — Verification and hardening: wiring

`grade.sh dashboard` (+ `--force`, `--export`, `--open`), the `grade_runner` subparser, the
best-effort call at the end of `write_report`, incremental mtime skip, path printing in run/code/
report output, README updates, `.gitignore` confirmation.

**Done when**: a `report` pass on an existing folder rebuilds the site and prints its paths; an
induced exception in the site build leaves the run successful and the markdown written; a full
`--force` rebuild of 20 runs completes under 10 s.

---

## 2. Component Boundaries

```
              ┌──────────────────────── existing, unmodified ────────────────────────┐
              │ artifacts.py   render.py   compare.py   code_grader.py   scoring.py  │
              └───────┬─────────────┬───────────┬──────────────┬──────────────┬──────┘
                      │             │           │              │              │
   grades.py ◀── extracted from markdown_report (re-exported there)           │
        │             │             │           │              │              │
        ▼             ▼             ▼           ▼              ▼              ▼
   ┌───────────────────────────────────────────────────────────────────────────────┐
   │ site/model.py    — reads, classifies, aggregates.  NO HTML.                   │
   ├───────────────────────────────────────────────────────────────────────────────┤
   │ site/charts.py   — view-model ➜ inline SVG.        NO file I/O.               │
   │ site/pages.py    — view-model ➜ HTML fragments.    NO file I/O. Owns _esc().  │
   │ site/assets.py   — CSS/JS constants.               NO logic.                  │
   ├───────────────────────────────────────────────────────────────────────────────┤
   │ site/export.py   — same fragments ➜ one file.                                 │
   │ site/builder.py  — scan, incremental decision, orchestrate, write.            │
   └───────────────────────────────────────────────────────────────────────────────┘
                      ▲                                   ▲
          markdown_report.write_report()          grade_runner "dashboard"
             (best-effort, at its end)                 grade.sh dashboard
```

**Rules that make the boundaries real** — each is enforced by a test, not by convention:

| # | Rule |
|---|---|
| B1 | `model.py` emits no HTML and imports nothing from `pages`/`charts`/`export` |
| B2 | `pages.py` and `charts.py` perform **no file I/O** — they take view-models and return strings. Only `builder.py` and `export.py` write |
| B3 | Every path under a run folder comes from `artifacts.*`; `site/` builds none by hand |
| B4 | No grade, blend, cap, or noise verdict is computed in `site/` or in JavaScript |
| B5 | Every interpolated string passes through the single `_esc()` in `pages.py` |
| B6 | The site and the export call the same section builders |

---

## 3. State Transitions / Flows

### 3.1 Build flow

```
build_site(runs_root, force)
  ├─ discover workflows                      → sorted
  ├─ for each run folder
  │    ├─ classify                           → error | copy | reference | partial | run
  │    ├─ needs_render?  (artifacts/summary/prompts mtime > run.html) or force
  │    │     ├─ no  → skip, count it
  │    │     └─ yes → model.load_run() → pages.render_run() + render_stage()×N → write
  │    └─ read failure → class=error, record message, CONTINUE
  ├─ aggregate over included runs            → trend, prompts, dimensions, matrix, cost
  ├─ pages.render_dashboard()                → always re-rendered
  └─ write index.html                        → return path
```

### 3.2 Run classification (ordered; first match wins)

```
run_summary.json missing/corrupt ──────────────► error
name ends "-copy" ─────────────────────────────► copy
name lacks YYMMDD-HHMMSS- prefix ──────────────► reference
status incomplete | stage stale/not_run |
  compute_overall() is None ───────────────────► partial
otherwise ─────────────────────────────────────► run   (the only class feeding charts)
```

### 3.3 Cell kind (per `(stage, row)`, mirroring `grades._cell_value`)

```
errored ─────────────────────────► errored        0.0    counted
precheck_passed is None ─────────► broken_chain   0.0    counted   (upstream broke)
precheck_passed is False ────────► precheck_fail  0.0    counted
expect == "fail" ────────────────► negative       —      excluded
no judge score and no code score ► unjudged       —      excluded
otherwise ───────────────────────► ok        blended     counted
  + scoring.judge_errored(grade) ► judge_failed overlay
```

### 3.4 Reader flow (the URL fragment is the state)

```
index.html
  ├─ #view=<id>                     select a view
  └─ #run=<id>          ──► run.html
                              ├─ phase table / matrix cell
                              └──► <token>.html#row=<row_id>
                                      └─ row expanded, preview or markdown shown
```

Fragments are read on load and written on interaction, so any reachable state is linkable. Unknown
or stale values are ignored silently.

---

## 4. Failure Modes

| # | Failure | Detection | Behaviour | Test |
|---|---|---|---|---|
| F1 | Corrupt/missing `run_summary.json` | `json.JSONDecodeError` / `FileNotFoundError` | Run classified `error`, badged with the message; **build continues** | T4 |
| F2 | Missing `grade_config.resolved.yaml` | path check | Provenance section omitted; run still renders | T4 |
| F3 | Stage has `score` but no `grade` | `FileNotFoundError` | Rows render without narrative; no fabricated text | T4 |
| F4 | No code findings | falsy `read_findings` | Code columns and tab omitted; blended = judge alone | T4 |
| F5 | `compute_overall()` returns `None` | `is None` | "Nothing gradable" stated; **never** a fabricated grade | T4 |
| F6 | Deliverable missing from `src/` | path check | Preview replaced by "not captured"; row still renders | T11 |
| F7 | Captured prompt missing (older folder) | path check | Version row keeps scores; diff control disabled **with the reason** | T14 |
| F8 | Model text contains HTML/`</script>` | — | `_esc()` + `</`-neutralised JSON; renders literally, executes nothing | T9 |
| F9 | Deliverable HTML runs scripts | — | `sandbox` without `allow-scripts`/`allow-same-origin` | T11 |
| F10 | Site build raises during a run | `try/except` in `write_report` **and** at the three existing call sites | Warning logged; **run still succeeds, markdown still written** | T22 |
| F11 | Export exceeds budget | byte accounting | Value-ordered inlining; remainder become labelled placeholders | T19 |
| F12 | Stale page after artifacts change | mtime comparison | Re-rendered; `--force` overrides | T21 |
| F13 | Two runs share a `dataset_run_id` across workflows | keyed by (workflow, id) | No collision — paths are workflow-scoped | T2 |
| F14 | Empty `.runs/` | no folders | Dashboard renders with an empty-state message, exit 0 | T20 |

**The load-bearing one is F10.** A reporting feature that can fail a token-spending run is a worse
outcome than no reporting feature. Defence is layered: the site build catches its own exceptions,
and the three call sites already wrap `write_report` in `try/except` with an explicit *"rendering
is never load-bearing"* comment.

---

## 5. Observability Hooks

No telemetry, no logging framework, no metrics backend. Observability is **stdout, the page
itself, and determinism**.

| Signal | Where | Purpose |
|---|---|---|
| `scanned N · rendered M · skipped K · errors E` | stdout, `grade.sh dashboard` | Incremental behaviour visible; a wrong skip is obvious |
| One line per `error` run, naming file and reason | stderr | Never silently dropped |
| `index.html` / export paths | stdout, all commands | Discoverability |
| Class badge + `class_reason` tooltip | every run row | A classification always explains itself |
| Error badge on the run row | dashboard | A folder excluded by failure says so on the page |
| "showing X of Y" | every filterable table | Filter state never hidden |
| `run_count` + spread on cross-run matrix cells | dashboard | A mean over 2 runs must not look like one over 15 |
| Warnings rendered **above** a phase's numbers | stage page | Which numbers not to trust, before the numbers |
| Override-divergence warning | run page | Run not reproducible from its config |
| Byte-determinism | — | `shasum` twice is a complete regression check on any render |

**Deliberate non-signal**: no render timestamp anywhere. It would break determinism, and the
artifact mtimes already carry the truth.

---

## 6. Performance Design

| Concern | Design |
|---|---|
| Full rebuild, 20 runs | Target < 10 s. Each run reads ~15 small JSON files; cost is I/O-bound and linear |
| Incremental | Skip when `reports/run.html` is newer than `artifacts/` + `run_summary.json` + `prompts/`. Sound because output is deterministic |
| Dashboard aggregation | Always recomputed — one page, and any run's change can move a trend |
| Deliverable bytes | **Never read into memory for the site** — previews are `iframe src`. Only the export reads them, under a budget |
| Page weight | Row detail rendered inline but collapsed; long text in bounded scroll containers; no per-row deliverable inlined on the site |
| JS cost | Sort/filter over pre-rendered DOM rows. No parsing, no computation, no framework |

---

## 7. Rollback Notes

**Granularity**: each slice is independently revertible; only S0 touches existing code.

| Level | Action | Consequence |
|---|---|---|
| Output only | `rm .runs/index.html .runs/*/*/reports/*.html` | Nothing lost — regenerate with `grade.sh dashboard` |
| Disable auto-rebuild | Remove the one call at the end of `write_report` | Site still buildable by command; runs unaffected |
| Remove the feature | Delete `site/`, revert `markdown_report.py` / `grade_runner.py` / `grade.sh` | Harness returns to current behaviour exactly |
| Revert S0 | Fold `grades.py` back into `markdown_report.py` | Pure inverse of a verbatim move |

**What makes rollback safe**: this feature writes **only** `index.html` and files under each run's
`reports/`. No artifact, no `superseded/` entry, no `src/` file, no log, no existing markdown
report is ever modified. It changes no score, no rubric, and no schema. There is nothing to
migrate back.

---

## 8. Traceability

| Spec story | Slice | Tasks |
|---|---|---|
| S1 — See every run at once | 3 | T12, T13, T20 |
| S2 — Did the prompt edit work | 4a | T14, T15 |
| S3 — Drill to the artifact | 2 | T7, T8, T10, T11 |
| S4 — Weak phase vs weak brief | 1, 4b | T5, T16 |
| S5 — Trend, weakness, cost | 4c–4e | T17, T18 |
| S6 — Share one run | 5 | T19 |
| S7 — Never stale | 6 | T21, T22, T23 |
| S8 — Never break/lie/execute | 2 | T9, T11, cross-cutting |
