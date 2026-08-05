# Tasks: The Grading Dashboard

**Spec**: [`specs/009-grading-dashboard/spec.md`](spec.md)
**Plan**: [`specs/009-grading-dashboard/plan.md`](plan.md)
**Design**: [`design.md`](design.md) · **Data model**: [`data-model.md`](data-model.md) · **Contracts**: [`contracts/`](contracts/)

24 tasks across 6 phases. **Every task is free and offline** — no task dispatches an agent, calls a
judge, or spends a token. All verification runs against the 20 existing run folders under
`backend/evals/grading/.runs/prototype/` and committed miniature fixtures.

Run tests with the project python: `cd backend && python3.11 -m pytest …` (no venv).

---

## Phase 1 — Foundation

### Task T1 — Extract `grades.py` from `markdown_report.py`

**Phase**: 1 · **Priority**: P1 · **Depends on**: none
**Traces to**: Plan D3, Design Slice 0

#### Description
Move `compute_overall`, `letter_grade`, `GRADE_BANDS`, `FAIL_GRADE`, and `_cell_value` **verbatim**
from `backend/evals/grading/markdown_report.py` into a new `backend/evals/grading/grades.py`.
Re-export all five from `markdown_report` so every existing import, call site, and test continues
to work untouched.

This exists solely to break the import cycle that would otherwise form when `markdown_report`
triggers the site build (T22) while `site/` needs the grade arithmetic. It is a move, not a
rewrite: **no logic changes, no signature changes, no docstring rewording**. `grades.py` gets a
module docstring stating it is the single owner of the run's blended-score arithmetic.

#### Acceptance
- [x] `grades.py` contains the five symbols, byte-equivalent in behaviour
- [x] `markdown_report` re-exports all five; `markdown_report.letter_grade` and
      `markdown_report.compute_overall` remain callable at their current paths
- [x] `site/` can import `grades` with no cycle
- [x] No caller anywhere in the repo was edited for this task

#### Tests
- [x] Unit: `tests/unit/test_grading_grades.py` — band boundaries (97/93/90/80/70/60/50/49.9),
      `compute_overall` on a fixture run, `None` when nothing is gradable
- [x] Regression: `tests/unit/test_grading_markdown_report.py` passes **unmodified**
- [x] Regression: full `tests/unit/` grading suite passes

#### guardrailRefs
- `.apex/rules/python/coding-style.md`, `.apex/rules/python/patterns.md`
- `.apex/rules/common/implementation-standards.md`, `.apex/rules/common/testing.md`

---

## Phase 2 — Core logic: the read layer

### Task T2 — Run discovery and classification (`site/model.py`)

**Phase**: 2 · **Priority**: P1 · **Depends on**: T1
**Traces to**: Spec Story 1.2, Design §3.2, Clarification C3

#### Description
Create the `site/` package and implement discovery: walk `<grading root>/.runs/<workflow>/<run>/`,
skipping dot-directories (housekeeping, not runs — matching the convention `grade.sh runs` already
uses), and sort runs newest-first. Folder names are timestamp-prefixed, so lexical descending sort
*is* chronological; do not parse dates for ordering.

Classify each run in strict order — `error` → `copy` → `reference` → `partial` → `run` — per
data-model §2.3, each with a human-readable `class_reason`. Only `run` feeds charts.

Runs are keyed by `(workflow, dataset_run_id)`, never by id alone.

#### Acceptance
- [x] All 20 real folders discovered and classified
- [x] `golden-mission-control` → `reference`; `260729-210937-small-copy` → `copy`
- [x] Every classification carries a `class_reason`
- [x] Dot-directories skipped
- [x] `WorkflowModel.included` contains only `run`-class runs

#### Tests
- [x] Unit: each classification rule, including precedence (a `-copy` of a `golden-*` is `copy`)
- [x] Unit: newest-first ordering
- [x] Unit: same `dataset_run_id` under two workflows does not collide (F13)

#### guardrailRefs
- `.apex/rules/python/coding-style.md`, `.apex/rules/python/patterns.md`
- `.apex/rules/common/artifact-contracts.md`, `.apex/rules/common/testing.md`

---

### Task T3 — Per-run view-model: `RunModel` / `StageModel` / `RowModel`

**Phase**: 2 · **Priority**: P1 · **Depends on**: T2
**Traces to**: data-model §2.3–2.7, Spec Story 3.2

#### Description
Load one run folder into the view-model. Read via `artifacts.*` **only** — `site/` builds no path
by hand (boundary rule B3). Join `score.results` ⇄ `grade` ⇄ `run` ⇄ `code_findings` by row id,
tolerating all three historical id fields (`row_id` / `scenario_id` / `id`) exactly as
`markdown_report._row_id` does.

Populate every field in data-model §2.3–2.7, including `deliverables` discovered under
`artifacts.src_dir(run_dir, row_id)` with `kind` by suffix (`html` / `markdown` / `other`) and
`size_bytes` (needed for the export budget in T19).

`overall` comes from `grades.compute_overall()` — **pass-through, never recomputed or rounded**.

#### Acceptance
- [x] `golden-mission-control` loads: 5 stages, all rows, sub-scores, rationales, evidence, caps,
      code findings, captured prompts, deliverables
- [x] `overall` is identical to `grades.compute_overall()` for the same folder
- [x] Rows join correctly regardless of which id field the artifact used
- [x] No path constructed outside `artifacts.*`
- [x] Module emits no HTML and imports nothing from `pages`/`charts`/`export` (B1)

#### Tests
- [x] Unit: full load against a committed fixture; field-by-field assertions
- [x] Unit: row join under each of the three id field names
- [x] Unit: deliverable kind/size detection
- [x] Unit: `import` assertion enforcing B1

#### guardrailRefs
- `.apex/rules/python/coding-style.md`, `.apex/rules/python/patterns.md`
- `.apex/rules/common/artifact-contracts.md`, `.apex/rules/common/implementation-standards.md`

---

### Task T4 — Degraded and malformed folders

**Phase**: 2 · **Priority**: P1 · **Depends on**: T3
**Traces to**: Spec NFR "Robustness", Design F1–F5

#### Description
Make every absent or broken input a rendering decision rather than an exception. Build committed
miniature fixtures under `backend/tests/fixtures/grading_site/` covering: corrupt
`run_summary.json`; missing `grade_config.resolved.yaml`; stage with `score` but no `grade`; no
`code_findings`; `compute_overall()` returning `None`; empty `.runs/`.

Rule: **a missing source omits its section — it is never faked, zero-filled, or guessed.** A run
that cannot be read becomes `error` class with the message retained, and the build continues.

#### Acceptance
- [x] Each fixture loads without raising; the affected section is omitted or badged
- [x] `compute_overall() is None` yields a model stating nothing was gradable — no fabricated grade
- [x] A corrupt folder does not prevent other runs from loading
- [x] Error messages name the file and the reason

#### Tests
- [x] Unit: one test per degradation fixture
- [x] Unit: a corrupt folder among three healthy ones still yields three healthy models

#### guardrailRefs
- `.apex/rules/python/testing.md`, `.apex/rules/common/testing.md`
- `.apex/rules/common/implementation-standards.md`

---

### Task T5 — `MatrixModel` and `cell_kind`

**Phase**: 2 · **Priority**: P1 · **Depends on**: T3
**Traces to**: Spec Story 4.1–4.2, data-model §2.8

#### Description
Build the stage × row matrix at run scope. Each cell's value is `grades._cell_value()` — the exact
cell `compute_overall()` averages, imported not reimplemented (B4).

Derive `cell_kind` per data-model §2.6. This is the point of the task: **four distinct situations
all score 0** — dispatch error, precheck fail, broken chain (never dispatched because upstream
failed), and judge failure — and averaging erases the difference. The matrix must show them apart.
A `(stage, row)` pair that does not exist is *absent*, which is not the same as 0.

#### Acceptance
- [x] Matrix cells equal `compute_overall()`'s cells, one by one
- [x] All six `cell_kind` values derived correctly, including `broken_chain` for
      `precheck_passed is None`
- [x] `negative` (`expect: fail`) and `unjudged` excluded from aggregates, present in the model
- [x] Missing pairs are absent, distinguishable from a 0-valued cell
- [x] No blending arithmetic implemented in `site/`

#### Tests
- [x] Unit: cell-by-cell equality against `compute_overall()` on `golden-mission-control`
- [x] Unit: one fixture row per `cell_kind`
- [x] Unit: sparse matrix — a stage missing a row

#### guardrailRefs
- `.apex/rules/python/patterns.md`, `.apex/rules/common/testing.md`
- `.apex/rules/common/implementation-standards.md`

---

### Task T6 — Cross-run aggregation and `PromptVersionModel`

**Phase**: 2 · **Priority**: P1 · **Depends on**: T2, T5
**Traces to**: Spec Stories 2.1–2.2, 4.4, 5.1–5.4; data-model §2.9

#### Description
Aggregate across `included` runs only (never `reference` / `copy` / `partial` / `error`):

- **Trend series** — each run's `overall.score` and per-phase `effective`, chronological;
  `reference` runs carried separately as ceiling/floor values.
- **Dimension grids** — dimensions × phases and dimensions × runs, from `score.dimensions`.
- **Cost series** — agent vs judge tokens per run and per phase.
- **Code-health series** — console errors, uncaught exceptions, dead nav, failed interactions.
- **Cross-run matrix** — mean, spread, and `run_count` per `(stage, row)` cell.
- **`PromptVersionModel`** — wrap `compare.group_by_prompt()` and `compare.noise_band()`,
  **passing every value through unmodified**. Attach the captured prompt text from
  `artifacts.read_system_prompt()` where it exists, `None` where it does not.

This is the only new arithmetic in the feature; everything else is imported.

#### Acceptance
- [x] Excluded runs never enter any aggregate (V8)
- [x] Prompt-version verdicts and deltas are byte-identical to `compare.group_by_prompt()` output
- [x] The noise band's basis is carried on the model for display (2σ, floor 1.0)
- [x] Cross-run matrix cells carry `run_count` and spread
- [x] Versions without a captured prompt carry `prompt_text = None` plus a reason

#### Tests
- [x] Unit: pass-through equality against `compare.group_by_prompt()` on a multi-run fixture
- [x] Unit: an excluded run changes no aggregate
- [x] Unit: aggregation over a single run, and over zero runs (empty state)

#### guardrailRefs
- `.apex/rules/python/patterns.md`, `.apex/rules/python/testing.md`
- `.apex/rules/common/implementation-standards.md`, `.apex/rules/common/testing.md`

---

## Phase 3 — Interface: drill-down pages

### Task T7 — Page shell, `_esc()`, CSS and JS (`site/pages.py`, `site/assets.py`)

**Phase**: 3 · **Priority**: P1 · **Depends on**: T3
**Traces to**: Spec Story 8, §3.5; Design B2/B5

#### Description
Build the rendering foundation:

- **`_esc()`** — the single escaping choke point every interpolation passes through, plus a
  JSON-inlining helper that neutralises `</`.
- **Page shell** — `<!doctype>` … head with inline `<style>`/`<script>`, sticky header, theme
  toggle applied **before first paint** (no flash), footer.
- **`assets.py`** — CSS (system font stack, light/dark via `prefers-color-scheme` + persisted
  override, grid/flex layout, bounded scroll containers, `prefers-reduced-motion`, print
  stylesheet) and JS (tab switching, column sort, filter chips, search, row expand, deep-link
  read/write). **No score is computed in JS** (B4) — it sorts, filters, and toggles.

`pages.py` and `charts.py` perform **no file I/O** (B2): view-models in, strings out.

#### Acceptance
- [x] Every interpolation in the module routes through `_esc()`
- [x] Inlined JSON contains no unescaped `</`
- [x] Theme applied before first paint; persisted in `localStorage`
- [x] Keyboard: arrows across tabs, Enter/Space expands, `/` focuses search, `Esc` clears; focus
      rings never removed
- [x] Print stylesheet expands all tabs and rows linearly
- [x] No file I/O in `pages.py` / `charts.py`

#### Tests
- [x] Unit: `_esc()` over `<`, `>`, `&`, `"`, `'`
- [x] Unit: JSON helper neutralises `</script>`
- [x] Unit: import/AST assertion enforcing B2

#### guardrailRefs
- `.apex/rules/python/security.md`, `.apex/rules/common/security.md`
- `.apex/rules/python/coding-style.md`, `.apex/rules/frontend-architecture-decision/decision-procedure.md`

---

### Task T8 — Run page (`reports/run.html`)

**Phase**: 3 · **Priority**: P1 · **Depends on**: T5, T7
**Traces to**: Spec Story 3.1, 4.1, 5 (provenance), Design Slice 2

#### Description
Render the run page as composable section builders (reused verbatim by the export, B6): grade hero
(letter, `NN.N / 100`, band track marking the run's position, counted cells, red callout naming
failed cells); phase table linking to stage pages with the `effective` column and its one-sentence
explanation; the run's stage × row matrix; not-run; signals including the ⚠️ *judged NOT ready — the
run proceeded anyway* alerts; cross-phase strength/weakness clusters with row links deep-linking
into stage pages; provenance (models, resolved judge id, rubric/dataset/prompt hashes) and the
CLI-override divergence warning; copy-to-clipboard rejudge / code / reproduce commands.

#### Acceptance
- [x] Grade, score, and phase `effective` column identical to `reports/report.md` for the same run
- [x] Override divergence warning shown when `overrides` is non-empty
- [x] Cluster row links resolve to `<token>.html#row=<row_id>`
- [x] `compute_overall() is None` → states nothing was gradable, no fabricated grade
- [x] Sections are functions reusable by the export

#### Tests
- [x] Unit: fidelity against `report.md` for `golden-mission-control`
- [x] Unit: `None`-overall fixture
- [x] Unit: override warning present/absent

#### guardrailRefs
- `.apex/rules/python/coding-style.md`, `.apex/rules/common/testing.md`
- `.apex/rules/common/artifact-contracts.md`

---

### Task T9 — Escaping, determinism, self-containment test suite

**Phase**: 3 · **Priority**: P1 · **Depends on**: T7, T8
**Traces to**: Spec Story 8, NFRs; Design F8, G1–G7

#### Description
Write the cross-cutting suite that makes the security and correctness guarantees real. **This is
not a hardening pass at the end** — it lands with the pages it protects.

Build a fixture whose rationale, evidence, brief, and deliverable each contain
`<script>alert(1)</script>`, `</td>`, `</script>`, `&`, and quote characters, and assert they
render as literal text with no raw tag and no layout damage. Assert output has no remote
`src`/`href`, no `fetch(`, no `XMLHttpRequest`. Assert two renders are byte-identical. Assert no
score arithmetic appears in the emitted JS.

#### Acceptance
- [x] Injection payloads render literally; no script executes
- [x] No remote asset reference; no `fetch(`/`XMLHttpRequest` (G1)
- [x] Inlined JSON has no unescaped `</` (G3)
- [x] Byte-identical across two renders (G5)
- [x] No `None` reaches a page as text — `render.DASH` instead (V7)

#### Tests
- [x] Unit: injection fixture across all four text surfaces
- [x] Unit: self-containment grep over emitted HTML
- [x] Unit: determinism (render twice, compare)
- [x] Unit: `DASH` for every absent value

#### guardrailRefs
- `.apex/rules/python/security.md`, `.apex/rules/common/security.md`
- `.apex/rules/python/testing.md`, `.apex/rules/common/testing.md`

---

### Task T10 — Stage page: tables and row detail

**Phase**: 3 · **Priority**: P1 · **Depends on**: T7, T8
**Traces to**: Spec Story 3.2, §3.5

#### Description
Render `reports/<agent_token>.html`: warnings **above** the numbers; baseline verdict with its
failure list; spread strip (avg all, avg passed, median, stddev, min, max, distinct); dimensions
table sorted worst-mean-first; tokens split agent/judge/all; the rows table (row, expect, precheck,
judge, code, combined, passed, one column per dimension, note) sortable on every column, with
filter chips (*failures only*, *negative tests*, *judge errors*, *capped*), free-text search across
id/rationale/evidence, and a visible "showing X of Y"; expandable row detail with brief,
sub-scores, rationale, strengths, weaknesses, per-dimension evidence quotes, `score_caps` shown
before→after, precheck reason, judge error, and that row's code findings; recurring clusters; the
per-stage rejudge command.

#### Acceptance
- [x] Row scores match `<token>_report.md` for the same stage
- [x] Sorting preserves the active filter; nulls sort last
- [x] "Failures only" shows exactly the 0-valued cells plus judge failures, and the count updates
- [x] Deep link `#row=<id>` opens the page with that row expanded
- [x] Warnings render above the numbers they qualify

#### Tests
- [x] Unit: fidelity against the stage's markdown report
- [x] Unit: every row-detail field present for a fully-populated fixture row
- [x] Unit: note text for errored / skipped / judge-failed / negative rows

#### guardrailRefs
- `.apex/rules/python/coding-style.md`, `.apex/rules/common/testing.md`
- `.apex/rules/frontend-architecture-decision/decision-procedure.md`

---

### Task T11 — Deliverable preview and markdown display

**Phase**: 3 · **Priority**: P1 · **Depends on**: T10
**Traces to**: Spec Story 3.3–3.5, Story 8.3; Clarification C6; Design F6/F9

#### Description
Inside row detail, render the artifact the agent produced:

- **`html`** → `<iframe sandbox src="../src/<row_id>/<file>">` — `sandbox` **without**
  `allow-scripts` and **without** `allow-same-origin` — plus a toggle to escaped source and a link
  to the file.
- **`markdown`** → escaped monospace block (C6-A), with the toggle stub for a future renderer.
- **`other`** → link only.
- **Missing** → "not captured" placeholder; the row still renders.
- **Transcript** → link to `logs/<row_id>/<token>.log`, marked unavailable rather than broken when
  the page is detached from its folder.

#### Acceptance
- [x] Every preview iframe carries `sandbox` without `allow-scripts` / `allow-same-origin`
- [x] Source toggle shows escaped text — the deliverable never enters the page's own DOM
- [x] Markdown shown as escaped monospace
- [x] Missing deliverable degrades to a placeholder, no exception
- [x] Links resolve when opened in place; labelled unavailable when detached

#### Tests
- [x] Unit: structural assertion on every emitted `<iframe>` (G2)
- [x] Unit: a deliverable containing `<script>` never appears unescaped in the source view
- [x] Unit: missing-deliverable fixture

#### guardrailRefs
- `.apex/rules/python/security.md`, `.apex/rules/common/security.md`
- `.apex/rules/common/testing.md`

---

## Phase 4 — Interface: dashboard and views

### Task T12 — `site/builder.py`: scan, orchestrate, write

**Phase**: 4 · **Priority**: P1 · **Depends on**: T6, T8, T10
**Traces to**: Spec Story 1.1, 1.3; Design §3.1

#### Description
Implement `build_site(runs_root, *, force=False)` and `build_run_pages(run_dir)` per the API
contract: scan, classify, render each run's pages, aggregate, render the dashboard, write
`index.html`. A run that fails to load is recorded as `error` and **the build continues** (F1).
Writes are confined to `index.html` and files under each run's `reports/` — nothing else is
created, modified, moved, or deleted.

Emit the progress line `scanned N · rendered M · skipped K · errors E` and one stderr line per
error run.

#### Acceptance
- [x] `build_site` returns the `index.html` path and renders every discoverable run
- [x] One unreadable folder does not fail the build
- [x] Nothing outside `index.html` and `reports/` is written (asserted by before/after file listing)
- [x] `FileNotFoundError` when `runs_root` itself is absent
- [x] Progress counts are accurate

#### Tests
- [x] Unit: build over a fixture tree; assert output paths
- [x] Unit: corrupt folder isolation
- [x] Unit: write-confinement assertion

#### guardrailRefs
- `.apex/rules/python/patterns.md`, `.apex/rules/common/artifact-contracts.md`
- `.apex/rules/common/implementation-standards.md`

---

### Task T13 — Dashboard run list

**Phase**: 4 · **Priority**: P1 · **Depends on**: T12
**Traces to**: Spec Story 1.1–1.3

#### Description
Render the dashboard header (workflow selector, hidden while only one workflow exists per C8; run
count; date span; theme toggle) and the run list: newest first, with grade pill, blended score,
workflow, dataset, rows, phases, status, class badge, and date. Sortable, filterable, searchable.
Non-`run` classes are badged with their `class_reason` as a tooltip and hidden behind a **"show
excluded"** toggle — listed, never silently dropped. `error` runs carry an error badge naming the
failure.

#### Acceptance
- [x] All 20 real runs listed, newest first
- [x] `reference` / `copy` / `partial` / `error` badged with reasons
- [x] "Show excluded" reveals them in place
- [x] Each row links to its run page
- [x] Workflow selector hidden with one workflow, present with two

#### Tests
- [x] Unit: badge and reason per class
- [x] Unit: excluded runs absent from the default view, present when toggled
- [x] Unit: single-workflow selector suppression

#### guardrailRefs
- `.apex/rules/python/coding-style.md`, `.apex/rules/common/testing.md`

---

### Task T14 — `site/charts.py`: inline-SVG primitives

**Phase**: 4 · **Priority**: P1 · **Depends on**: T7
**Traces to**: Spec Story 5.5; Design Slice 4

#### Description
Hand-emit SVG primitives — **no library, no CDN, no vendored JS**: line/step series with points and
optional horizontal reference lines; horizontal bar; heatmap cell grid; distribution strip; grade-band
track with a position marker. Each takes plain numbers and returns an SVG string; no file I/O, no
view-model coupling beyond primitive types.

Requirements: readable in light and dark (`currentColor` and CSS custom properties, not hardcoded
hex); readable in print; colour never the sole signal; **every plotted value also emitted as text**
(a `<title>`, a caption, or an accompanying table) so nothing is chart-only.

#### Acceptance
- [x] Five primitives implemented, each pure
- [x] Themeable without regenerating (no baked colours)
- [x] Every value present as text as well as geometry (G7)
- [x] Degenerate inputs render sanely: 0 points, 1 point, all-equal values, `None` gaps

#### Tests
- [x] Unit: well-formed SVG per primitive
- [x] Unit: degenerate inputs
- [x] Unit: text-equivalent present for every plotted value

#### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/common/testing.md`, `.apex/rules/frontend-architecture-decision/decision-procedure.md`

---

### Task T15 — V2: prompt version history and prompt diff

**Phase**: 4 · **Priority**: P1 · **Depends on**: T6, T14
**Traces to**: Spec Story 2.1–2.4

#### Description
Per agent, render versions grouped by `system_prompt_hash`, chronological by first-seen, with runs,
aggregate, delta, and verdict — **exactly the values `compare.group_by_prompt()` returned**. A
delta inside the noise band reads *within noise*, never "improved", and the band's basis (2σ,
floor 1.0) is stated on the page.

Selecting two versions renders a **line diff of the captured prompt text** (stdlib `difflib`)
beside the score delta. This is the payoff of the runs having captured `prompts/` all along — and
the one thing neither the terminal nor the markdown reports can do. Where a captured prompt is
missing (older folders), the row keeps its scores and the diff control is disabled **with the
reason shown** (F7).

#### Acceptance
- [x] Versions chronological by first-seen with runs, aggregate, delta, verdict
- [x] Within-noise deltas labelled as such; the band's basis stated
- [x] Two-version selection renders an added/removed line diff with the score delta
- [x] Missing prompt text → scores retained, diff disabled with reason
- [x] No verdict recomputed locally

#### Tests
- [x] Unit: rendered values equal `compare.group_by_prompt()` output
- [x] Unit: within-noise delta wording
- [x] Unit: diff output for two known prompt texts
- [x] Unit: missing-prompt degradation

#### guardrailRefs
- `.apex/rules/python/patterns.md`, `.apex/rules/common/testing.md`
- `.apex/rules/common/artifact-contracts.md`

---

### Task T16 — V4: stage × row matrix (run and cross-run)

**Phase**: 4 · **Priority**: P1 · **Depends on**: T5, T6, T14
**Traces to**: Spec Story 4.1–4.4

#### Description
Render the matrix as one component used at both scopes. Stages down, dataset rows across; colour by
value with the number always present. Distinguish `cell_kind` by **glyph, not colour alone** —
precheck fail, dispatch error, broken chain, and judge failure must be told apart. Absent pairs
render as "not applicable", visually distinct from a 0. Clicking a cell opens the stage page with
that row expanded. At dashboard scope each cell shows mean, spread, and contributing `run_count`,
so a mean over 2 runs cannot be mistaken for one over 15.

#### Acceptance
- [x] Matrix cells match the run page's per-phase numbers
- [x] Four zero-scoring kinds visually distinct by glyph
- [x] Absent pairs distinguishable from 0
- [x] Cell click deep-links to the expanded row
- [x] Cross-run cells show mean, spread, `run_count`

#### Tests
- [x] Unit: rendered cell values equal `MatrixModel`
- [x] Unit: one fixture per `cell_kind` produces a distinct glyph
- [x] Unit: cross-run cell annotation

#### guardrailRefs
- `.apex/rules/python/coding-style.md`, `.apex/rules/common/testing.md`

---

### Task T17 — V1 quality trend and V3 dimension heatmap

**Phase**: 4 · **Priority**: P2 · **Depends on**: T6, T14
**Traces to**: Spec Story 5.1–5.2

#### Description
**V1**: each included run's blended grade plotted chronologically, overall and split by phase, with
`reference` runs drawn as **horizontal ceiling/floor lines rather than trend points** — the golden
is a target, not a measurement in the series.

**V3**: dimensions × phases and dimensions × runs as a colour grid, worst mean surfaced first, so
the chronically weak dimension — the one paragraph of an `AGENT.md` that never improves — is
visible across history.

#### Acceptance
- [x] Trend plots included runs only; references as reference lines
- [x] Per-phase series individually toggleable
- [x] Heatmap ordered worst-mean-first
- [x] Both readable in light, dark, and print; every value also present as text
- [x] Fewer than 2 included runs → an explanatory empty state, not a broken axis

#### Tests
- [x] Unit: reference runs absent from the series, present as lines
- [x] Unit: heatmap ordering
- [x] Unit: 0-run and 1-run empty states

#### guardrailRefs
- `.apex/rules/python/coding-style.md`, `.apex/rules/common/testing.md`

---

### Task T18 — V5: cost and code-track health

**Phase**: 4 · **Priority**: P2 · **Depends on**: T6, T14
**Traces to**: Spec Story 5.3–5.4

#### Description
Render token spend split **agent vs judge**, per run and per phase, over time; and the code track's
reliability signal — console errors, uncaught exceptions, dead nav, failed interactions — trended
across runs. Exercised counts are shown alongside failures, so "0 failed" is distinguishable from
"nothing was clickable to begin with" (the distinction `code_report.md` already draws).

#### Acceptance
- [x] Agent and judge spend separated, per run and per phase
- [x] Four code-health signals trended
- [x] Exercised counts shown, not just failures
- [x] Runs without token or code data omitted from those series without breaking them

#### Tests
- [x] Unit: token split correctness against fixture artifacts
- [x] Unit: health series with a run missing code findings

#### guardrailRefs
- `.apex/rules/python/coding-style.md`, `.apex/rules/common/performance.md`
- `.apex/rules/common/testing.md`

---

## Phase 5 — Interface: export

### Task T19 — One-file run export (`site/export.py`)

**Phase**: 5 · **Priority**: P2 · **Depends on**: T8, T10, T11
**Traces to**: Spec Story 6.1–6.2; Clarification C7; Design F11

#### Description
`export_run(run_dir, *, max_bytes=8MB)` assembles the **same section builders** as the site (B6)
into one self-contained file: run page plus every stage page as in-page tabs, previews inlined as
sandboxed `srcdoc`. Previews are inlined **largest-value-first until the budget is reached**; the
remainder become labelled placeholders naming the `src/` path — never a silent omission.

The page states that it embeds the run's captured system prompts, so anyone sharing one knows what
they are sending.

#### Acceptance
- [x] Opens from an unrelated directory with no network; tabs, sort, filter, expand all work
- [x] Grade, phase table, and row scores **identical** to that run's `run.html`
- [x] Budget honoured; over-budget previews are labelled placeholders
- [x] `srcdoc` iframes sandboxed without `allow-scripts` / `allow-same-origin`
- [x] Prompt-disclosure note present

#### Tests
- [x] Unit: equality of grade/phase/row values between export and `run.html`
- [x] Unit: budget enforcement and placeholder labelling
- [x] Unit: self-containment (no remote refs, no `fetch(`) on the export specifically

#### guardrailRefs
- `.apex/rules/python/security.md`, `.apex/rules/common/security.md`
- `.apex/rules/common/testing.md`, `.apex/rules/common/performance.md`

---

## Phase 6 — Verification and hardening: wiring

### Task T20 — `grade.sh dashboard` and the runner subcommand

**Phase**: 6 · **Priority**: P1 · **Depends on**: T12, T13
**Traces to**: Contracts §2; Design F14

#### Description
Add `_add_dashboard_parser` + `run_dashboard()` to `grade_runner.py` and a `dashboard)` case to
`grade.sh`, with `--force`, `--export <run-id>`, `--open`. Document it in the `grade.sh` header
block that `help` prints (`sed -n '2,57p'`) — listed with the **free** commands (`report`, `code`,
`compare`, `runs`), never with the `[LIVE]` ones, since no path here can call a model.

Exit codes: `0` success (including when some runs are `error`-classified), `2` usage, `1`
unrecoverable. Empty `.runs/` renders an empty-state dashboard and exits `0`.

#### Acceptance
- [x] All four invocations behave per the CLI contract
- [x] Help text lists it under the free commands
- [x] Exit codes as specified; empty `.runs/` → empty state, exit 0
- [x] No existing subcommand's flags, arguments, or exit codes changed

#### Tests
- [x] Unit: argument parsing for each flag combination
- [x] Unit: exit codes including the empty-tree case
- [x] Manual: `./evals/grading/grade.sh dashboard --open`

#### guardrailRefs
- `.apex/rules/common/development-workflow.md`, `.apex/rules/python/coding-style.md`
- `.apex/rules/common/testing.md`

---

### Task T21 — Incremental rebuild and `--force`

**Phase**: 6 · **Priority**: P2 · **Depends on**: T12
**Traces to**: Spec Story 7.4–7.5; Design D8, F12

#### Description
Skip re-rendering a run whose `reports/run.html` is newer than its `artifacts/`,
`run_summary.json`, and `prompts/`. `--force` ignores the skip. The dashboard page itself is always
re-rendered — it is one small page and any run's change can move a trend.

This is only sound because output is byte-deterministic (T9): a skip can never mask a difference.

#### Acceptance
- [x] Unchanged run not re-rendered (mtime unchanged)
- [x] Touching an artifact triggers a re-render of that run only
- [x] `--force` re-renders everything
- [x] The dashboard is re-rendered on every build

#### Tests
- [x] Unit: skip on unchanged; render on touched; `--force` overrides
- [x] Unit: determinism holds across a skip/render cycle

#### guardrailRefs
- `.apex/rules/common/performance.md`, `.apex/rules/python/patterns.md`
- `.apex/rules/common/testing.md`

---

### Task T22 — Auto-rebuild wiring, best-effort

**Phase**: 6 · **Priority**: P1 · **Depends on**: T1, T12
**Traces to**: Spec Story 7.1–7.2; Plan D3; Design F10

#### Description
Call `site.builder.rebuild_for_run(run_dir)` at the end of `markdown_report.write_report()`,
wrapped in its own `try/except` so a rendering failure degrades to a warning. `write_report`'s
return value is unchanged (the markdown path), so no existing caller is affected.

The three existing call sites — `grade_runner.py:1250` (code), `grade_runner.py:1549` (report),
`model_grader._write_markdown_report` — already wrap the call in `try/except` with an explicit
*"rendering is never load-bearing"* comment, so this inherits best-effort semantics at every one
without editing them. Extend their printed output to include the site paths.

**Invariant**: a failure in this feature can never fail a grading run, and can never prevent the
markdown report from being written.

#### Acceptance
- [x] `write_report` triggers the rebuild; return value unchanged
- [x] An induced exception in the site build leaves the run successful **and the markdown written**
- [x] Site paths printed alongside the markdown path in run/code/report output
- [x] No existing call site's control flow changed

#### Tests
- [x] Unit: monkeypatched raising builder → `write_report` still returns the markdown path
- [x] Unit: successful path writes both markdown and site pages
- [x] Integration: `grade.sh report <existing-run>` regenerates both

#### guardrailRefs
- `.apex/rules/python/patterns.md`, `.apex/rules/common/implementation-standards.md`
- `.apex/rules/common/testing.md`, `.apex/rules/common/artifact-contracts.md`

---

### Task T23 — Documentation and ignore rules

**Phase**: 6 · **Priority**: P2 · **Depends on**: T20
**Traces to**: Plan §4; Contracts §3

#### Description
Write `site/README.md` (what the package is, the boundary rules B1–B6, and the rules it must not
break), following the `code/README.md` and `docs/README.md` convention. Update
`evals/grading/README.md` with the dashboard, the drill-down layout, and the free/LIVE distinction.
Confirm `.gitignore` keeps generated HTML under `.runs/` ignored — **and that no rule inadvertently
un-ignores `*.html`**, which would start committing generated pages.

#### Acceptance
- [x] `site/README.md` documents purpose and boundary rules
- [x] `evals/grading/README.md` covers the dashboard and its zero-cost guarantee
- [x] `git status` is clean after a full build — no generated file is trackable
- [x] Contracts and data-model files match what was built (or are updated in the same commit)

#### Tests
- [x] Manual: full build, then `git status --porcelain` is empty

#### guardrailRefs
- `.apex/rules/common/development-workflow.md`, `.apex/rules/common/git-workflow.md`
- `.apex/rules/common/artifact-contracts.md`

---

### Task T24 — Performance and full acceptance pass

**Phase**: 6 · **Priority**: P1 · **Depends on**: T13–T23
**Traces to**: Spec NFRs; quickstart §Validation Scenarios; Plan §7

#### Description
Run the ten-scenario acceptance pass in [`quickstart.md`](quickstart.md) against the 20 real run
folders, plus the timing, determinism, self-containment, and sandbox checks. Confirm coverage of
`site/` exceeds 80% and that the **entire existing grading suite still passes unmodified**.

Record measured numbers (build time, `index.html` size, largest export) in the spec's status line
so the next reader sees evidence rather than intent.

#### Acceptance
- [x] All 10 quickstart scenarios pass
- [x] Full `--force` rebuild of 20 runs < 10 s
- [x] Two builds byte-identical
- [x] Zero remote references, zero `fetch(`, every preview iframe sandboxed
- [ ] `site/` coverage > 80% — **not measured**: neither `coverage` nor `pytest-cov` is installed in this environment
- [x] Existing grading suite passes unmodified
- [x] Measured numbers recorded

#### Tests
- [x] Integration: timed full rebuild
- [x] Integration: determinism via `shasum` across two builds
- [x] Full suite: `python3.11 -m pytest tests/unit/ -q`

#### guardrailRefs
- `.apex/rules/common/testing.md`, `.apex/rules/common/performance.md`
- `.apex/rules/common/release-readiness.md`, `.apex/rules/common/phase-gates.md`

---

## Coverage check (Step 3b)

Every artifact in the planning pack has both an implementation task and a verification task:

| Planning artifact | Implemented by | Verified by |
|---|---|---|
| `grades.py` extraction (Plan D3) | T1 | T1 tests + untouched markdown suite |
| `SiteModel` / `WorkflowModel` / `RunModel` | T2, T3 | T2, T3, T4 |
| Classification rules (data-model §2.3) | T2 | T2, T13 |
| `StageModel` / `RowModel` / `Deliverable` | T3 | T3, T10, T11 |
| `cell_kind` + `MatrixModel` | T5 | T5, T16 |
| `PromptVersionModel` + aggregations | T6 | T6, T15, T17, T18 |
| `_esc()` + shell + assets | T7 | T9 |
| Run page | T8 | T8, T9, T24 |
| Stage page + row detail | T10 | T10, T24 |
| Preview / markdown / links | T11 | T11, T24 |
| `build_site` / `build_run_pages` (contract §1) | T12 | T12, T21 |
| Dashboard + run list | T13 | T13 |
| Charts | T14 | T14, T17, T18 |
| The five views | T15–T18 | T15–T18, T24 |
| `export_run` (contract §1) | T19 | T19 |
| CLI contract (contract §2) | T20 | T20, T24 |
| Page/fragment contract (contract §3) | T7, T8, T10, T13 | T9, T10, T16 |
| Auto-rebuild invariant | T22 | T22 |
| Filesystem contract (integration §3) | T12 | T12, T23 |
| Security posture (integration §4) | T7, T11, T19 | T9, T11, T19 |
| Failure modes F1–F14 | T4, T11, T12, T19, T21, T22 | T4, T9, T11, T12, T19, T21, T22 |

**Integrations**: none — recorded explicitly in
[`contracts/integration-contracts.md`](contracts/integration-contracts.md); the absence of network
access is enforced by test (T9), not by convention.
