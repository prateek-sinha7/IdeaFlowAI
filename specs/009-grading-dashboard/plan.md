# Implementation Plan: The Grading Dashboard

**Spec**: [`specs/009-grading-dashboard/spec.md`](spec.md)
**Clarifications**: [`clarifications.md`](clarifications.md) (C1–C5 resolved, C6–C8 recommended)
**Created**: 2026-07-30
**Status**: Planned

---

## 1. Technical Context

| | |
|---|---|
| **Runtime** | Python 3.11, invoked via `./evals/grading/grade.sh` (no venv — project python3.11) |
| **Package** | `backend/evals/grading/` — currently 8,572 LOC across `model/`, `code/`, and the shared root |
| **New code** | `backend/evals/grading/site/` (new package) + `grades.py` (extraction) |
| **Dependencies** | **None added.** `html.escape`, `json`, `pathlib`, `difflib`, `statistics` — all stdlib |
| **Frontend** | Hand-emitted HTML5 + CSS + vanilla ES2020 + inline SVG, embedded as Python string constants |
| **Database** | None. Inputs are JSON/YAML/markdown files already on disk under `.runs/` |
| **Deployment** | None. Output is static files opened via `file://` |
| **Tests** | pytest, `backend/tests/unit/`, following `test_grading_markdown_report.py` |
| **Live model calls** | **Zero.** Every code path in this feature is free and offline |

**Real data available now**: 20 run folders under `backend/evals/grading/.runs/prototype/`, including
`golden-mission-control` (5 stages, full artifact set, captured prompts, `src/mission_control/`
deliverables, code findings). Development and testing run against these; no new run is needed, and
none should be triggered.

---

## 2. Architecture Decisions

### D1 — A new `site/` package, peer to the existing renderers

`markdown_report.py` (839 LOC) is already at the edge of comfortable. The dashboard is a larger
surface with a different output medium, so it gets its own package rather than growing that file.
It sits at the same architectural layer: **pure functions over on-disk artifacts, no model calls,
regenerable at any time** — the contract `markdown_report` already states in its module docstring.

**Rationale**: same layer, different medium. Sharing a file would force every markdown change to
re-read HTML concerns and vice versa.

### D2 — Every number is imported, never re-derived

The dashboard computes **no** grade, blend, cap, or noise verdict of its own:

| Value | Owner |
|---|---|
| Blended grade, letter, per-phase `effective`, per-cell values | `compute_overall()` / `letter_grade()` / `GRADE_BANDS` |
| Prompt-version grouping, deltas, met/not-met | `compare.group_by_prompt()` / `noise_band()` |
| Code score, blend of judge+code | `code_grader.read_findings()` / `blended_score()` |
| Judge failure detection | `scoring.judge_errored()` / `judge_error_reason()` |
| Number formatting | `render.py` |
| Every path under a run folder | `artifacts.*` |

**Rationale**: a harness whose purpose is catching scoring inconsistency cannot ship two
implementations of its own scoring. Enforced by fidelity tests (§5), not by convention.

The **only** new arithmetic is aggregation *across* runs — means, spreads, chronological grouping —
which no existing module owns. It lives in `site/model.py` and is fixture-tested.

### D3 — Extract `grades.py`, then hang the auto-rebuild off `write_report`

`site` needs `compute_overall()`, which currently lives in `markdown_report`. If `markdown_report`
is also to trigger the site build, that is an import cycle.

**Decision**: extract `compute_overall`, `letter_grade`, `GRADE_BANDS`, `FAIL_GRADE`, and
`_cell_value` into a new `grades.py`; `markdown_report` **re-exports them** so every existing
import and test keeps working unchanged. `site` imports `grades`. `markdown_report` then imports
`site` with no cycle.

**Why this over the alternatives**:

| Option | Rejected because |
|---|---|
| Update the 3 call sites to a new `reports.write_all()` | A 4th call site added later silently skips the dashboard — the exact staleness this feature exists to remove |
| Function-level (deferred) import inside `write_report` | Works, but hides a real layering problem instead of fixing it |

**Why it is safe**: all three call sites —
`grade_runner.py:1250` (code), `grade_runner.py:1549` (report), and
`model_grader._write_markdown_report` — **already wrap `write_report` in `try/except` with an
explicit "rendering is never load-bearing" comment.** The auto-rebuild therefore inherits
best-effort semantics at every call site without touching one of them. The site build additionally
catches its own exceptions, so it degrades to a warning rather than losing the markdown report.

**Extraction is behaviour-preserving**: `grades.py` is a move, not a rewrite. The existing
`test_grading_markdown_report.py` assertions on `letter_grade` and `compute_overall` are the
regression test, and must pass untouched.

### D4 — No `fetch()`, ever: every page inlines its own data

Chrome blocks `fetch()` / `XMLHttpRequest` against `file://` origins. A page that loads a sibling
`data.json` is broken on double-click — the primary way these will be opened.

**Decision**: each page carries its own data in `<script type="application/json">`, `</`-neutralised.
No shared data file. Accepted cost: the dashboard's inlined data is duplicated in nothing else, and
run pages carry only their own run.

### D5 — Site and export share section builders

`pages.py` exposes section builders returning HTML fragments. Both the multi-page site and the
single-file export assemble those same fragments, differing only in:

| | Site | Export |
|---|---|---|
| Navigation | Links between files | In-page tabs |
| Previews | `<iframe src="../src/…">` | `<iframe srcdoc="…">` within the size budget |
| Data | Per page | All in one |

**Rationale**: two renderers that can disagree about a grade is a correctness bug, not a cosmetic
one. A test asserts identical grade / phase table / row scores between `run.html` and the export.

### D6 — Classification drives the charts, and is always visible

Run classes (`run` / `reference` / `copy` / `partial` / `error`, per C3) are computed once in
`model.py` and carried on the view-model. Charts consume only `run`; everything else is listed,
badged, and revealed by a "show excluded" toggle.

**Rationale**: `golden-mission-control` and `260729-210937-small-copy` would otherwise silently
distort every trend line. A chart that drops data without saying so is worse than no chart.

### D7 — Determinism as an enabling constraint, not a nicety

No render timestamps, no counter-derived element IDs, no `Math.random`, no dict-order dependence
(all iteration explicitly sorted). IDs derive from run/stage/row identifiers.

**Rationale**: determinism is what makes the incremental rebuild (D8) sound and any diff-based
review of generated output possible.

### D8 — Incremental rebuild keyed on artifact mtimes

A run's pages are re-rendered only when its `artifacts/` + `run_summary.json` + `prompts/` are newer
than its `reports/run.html`, or under `--force`. The dashboard itself is always re-rendered (it is
one small page, and any run's change can move a trend).

### D9 — Security posture: escape everything, sandbox previews

One `_esc()` choke point in `pages.py`; every interpolation goes through it. Inlined JSON is
`</`-neutralised. Previews are `<iframe sandbox>` **without** `allow-scripts` and **without**
`allow-same-origin`. Deliverable markdown is escaped monospace (C6-A).

**Rationale**: the reference snippet that motivated this work interpolates model output into an
f-string unescaped, and our payloads are literally HTML documents. This is a certainty, not a risk.

---

## 3. Delivery Strategy

Six slices. Each is independently verifiable, and slices 1–2 alone already beat the markdown
reports for daily use.

| # | Slice | Delivers | Depends on |
|---|---|---|---|
| **S0** | `grades.py` extraction + re-export | Nothing user-visible; unblocks everything | — |
| **S1** | `site/model.py` — read + classify + aggregate | Fixture-tested view-model, no HTML | S0 |
| **S2** | Run page + stage pages (incl. preview, row detail) | **Story 3** — drill-down to the artifact, usable on its own | S1 |
| **S3** | Dashboard shell + run list | **Story 1** — the central entry point | S1 |
| **S4** | The five views (V2, V4 first) | **Stories 2, 4, 5** | S3 + `charts.py` |
| **S5** | One-file export | **Story 6** | S2 |
| **S6** | Wiring: `grade.sh dashboard`, auto-rebuild, incremental | **Story 7** | S2, S3 |

**Sequencing rationale**: S2 before S3 because the drill-down is the part that cannot be
approximated by any existing tool, and it validates the view-model against real artifacts before
any aggregation is layered on. Within S4, **V2 (prompt version history)** and **V4 (stage × row
matrix)** come first — they answer questions nothing in the repo answers today; V1/V3/V5 are
valuable but are prettier renderings of things `report.md` already states.

**Cross-cutting tests are written with S1–S2, not appended**: escaping, determinism, and fidelity
are the acceptance criteria of those slices.

**Verification substrate**: the 20 real run folders. `golden-mission-control` is the primary
fixture (complete, 5 stages, code findings, captured prompts, real `src/` deliverables); a
committed miniature fixture covers the degenerate cases (missing config, no grades, corrupt JSON,
`compute_overall() is None`) so the suite does not depend on gitignored `.runs/` content.

---

## 4. File Changes

| File | Action | Purpose |
|---|---|---|
| `backend/evals/grading/grades.py` | **new** | `compute_overall`, `letter_grade`, `GRADE_BANDS`, `FAIL_GRADE`, `_cell_value` moved verbatim from `markdown_report` |
| `backend/evals/grading/markdown_report.py` | modify | Import + re-export from `grades`; call `site.builder.rebuild_for_run()` best-effort at the end of `write_report` |
| `backend/evals/grading/site/__init__.py` | **new** | Public surface: `build_site`, `build_run_pages`, `export_run` |
| `backend/evals/grading/site/model.py` | **new** | Run discovery, classification, per-run view-model, cross-run aggregation, stage × row matrix |
| `backend/evals/grading/site/pages.py` | **new** | `_esc()` choke point + shared section builders + dashboard/run/stage assembly |
| `backend/evals/grading/site/charts.py` | **new** | Inline-SVG primitives: line, bar, heatmap cell, distribution strip, grade-band track |
| `backend/evals/grading/site/export.py` | **new** | Single-file export; size budget, value-ordered preview inlining, labelled placeholders |
| `backend/evals/grading/site/builder.py` | **new** | Scan `.runs/`, incremental decision, orchestrate, best-effort auto path |
| `backend/evals/grading/site/assets.py` | **new** | CSS + JS string constants (theme, tabs, sort, filter, search, deep links) |
| `backend/evals/grading/site/README.md` | **new** | What this package is and the rules it must not break (matches the `code/`, `docs/` convention) |
| `backend/evals/grading/grade_runner.py` | modify | `dashboard` subparser + `run_dashboard()`; print site paths in run/code/report output |
| `backend/evals/grading/grade.sh` | modify | `dashboard)` case + header usage lines (the `sed -n '2,57p'` help block) |
| `backend/evals/grading/README.md` | modify | Document the dashboard and the drill-down layout |
| `backend/tests/unit/test_grading_site_model.py` | **new** | Discovery, classification, view-model, aggregation, matrix correctness |
| `backend/tests/unit/test_grading_site_pages.py` | **new** | Escaping/injection, determinism, self-containment, structure, degraded folders |
| `backend/tests/unit/test_grading_site_export.py` | **new** | Export ≡ run page fidelity, size budget, placeholder labelling |
| `backend/tests/unit/test_grading_site_builder.py` | **new** | Incremental skip, `--force`, bad folder isolation, auto-rebuild never fails a run |
| `backend/tests/unit/test_grading_grades.py` | **new** | The extraction is behaviour-preserving (alongside the untouched markdown-report suite) |
| `backend/tests/fixtures/grading_site/` | **new** | Miniature run folders for degenerate cases |
| `.gitignore` | check | Confirm generated `index.html` / `reports/*.html` under `.runs/` stay ignored |

**Not touched**: `scoring.py`, `judge.py`, `model_grader.py`, `code_grader.py`, `config.py`,
`calibrate.py`, any rubric, any dataset, any `AGENT.md`. This feature changes no score.

---

## 5. Test Strategy

| Class | Asserts | Where |
|---|---|---|
| **Fidelity** | Dashboard, run page, and export agree with `compute_overall()` and `report.md` for the same folder | `test_grading_site_export.py`, `test_grading_site_pages.py` |
| **Matrix correctness** | Every matrix cell equals the corresponding `compute_overall()` cell | `test_grading_site_model.py` |
| **Noise honesty** | Prompt-version verdicts pass `compare.group_by_prompt()` through unmodified | `test_grading_site_model.py` |
| **Injection** | `<script>`, `</td>`, `&`, quotes in rationale/evidence/brief/deliverable appear literally; no raw tag; no unescaped `</` in inlined JSON | `test_grading_site_pages.py` |
| **Self-containment** | No remote `src`/`href`; no `fetch(` / `XMLHttpRequest`; iframes carry `sandbox` without `allow-scripts` | `test_grading_site_pages.py` |
| **Determinism** | Two renders byte-identical | `test_grading_site_pages.py` |
| **Degradation** | Corrupt JSON, missing config, missing grades, missing code findings, `compute_overall() is None` → section omitted or badged, never a traceback | `test_grading_site_pages.py` |
| **Robustness** | A raising site build inside a successful run leaves the run successful and the markdown written | `test_grading_site_builder.py` |
| **Incremental** | Unchanged run not re-rendered; `--force` re-renders | `test_grading_site_builder.py` |
| **Extraction** | `letter_grade` / `compute_overall` behaviour unchanged; existing markdown-report suite passes untouched | `test_grading_grades.py` + existing suite |
| **Budget** | Export ≤ budget; over-budget previews become labelled placeholders | `test_grading_site_export.py` |

Coverage target: **>80% of `site/`**.

---

## 6. Risks & Mitigations

| Risk | L | I | Mitigation | Slice |
|---|---|---|---|---|
| Unescaped model output breaks or hijacks a page | High | High | Single `_esc()`; `</`-neutralised JSON; sandboxed script-less iframes; injection test | S2 |
| `grades.py` extraction changes behaviour | Low | High | Verbatim move + re-export; existing suite is the regression gate; ship as its own slice (S0) | S0 |
| Site and export drift | Medium | High | Shared section builders; equality test on grade/phase/rows | S5 |
| Numbers drift from markdown/terminal | Medium | High | D2 — all arithmetic imported; fidelity tests | S1–S2 |
| Auto-rebuild fails a completed run | Medium | High | Inherits the existing `try/except` at all 3 call sites, plus its own; best-effort test | S6 |
| Rebuild slows as runs accumulate | Medium | Medium | Incremental (D8); `--force` escape hatch; timed test (<10 s for 20 runs) | S6 |
| Export bloats to tens of MB | Medium | Medium | Hard budget, value-ordered inlining, labelled placeholders (C7) | S5 |
| Hand-written CSS/JS rots | Medium | Low | Small and boring; structural tests over emitted HTML | S2–S4 |
| Tests coupled to gitignored `.runs/` content | Medium | Medium | Committed miniature fixtures for the suite; real runs used for manual verification only | S1 |
| Scope creep into a product | Medium | Medium | Spec §5 is binding; comparison UI and prompt editing are separate specs | — |

---

## 7. Definition of Done

- `./evals/grading/grade.sh dashboard` renders all 20 real run folders in under 10 seconds, free and
  offline, with zero model calls.
- `.runs/index.html` opens by double-click and drills down to a rendered prototype sitting beside
  the judge's criticism of it.
- The prompt-version view shows, for `prototype-build`, each captured version's score and the actual
  text diff between two of them.
- Grades shown anywhere match `report.md` exactly.
- Full existing grading suite still passes, unmodified.
- Coverage of `site/` above 80%.

---

**Next**: `/apex:design` to generate the execution design and `tasks.md`.
