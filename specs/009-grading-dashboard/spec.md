# Feature Specification: The Grading Dashboard — every run, one surface, drill-down to the artifact

**Spec ID**: 009-grading-dashboard
**Created**: 2026-07-30
**Status**: Clarified — see [clarifications.md](clarifications.md) (C1–C5 resolved, C6–C8 recommended)
**Stack**: Python 3.11, stdlib only for rendering · pytest · `evals/grading/` — no new dependency, no JS toolchain, no network, no server

---

## 0. In plain English

We have **20 completed grading runs** sitting in `backend/evals/grading/.runs/prototype/`. Every
one of them holds a full record: per-stage scores, per-row judge narratives, per-dimension
sub-scores, the captured system prompt that produced them, the built deliverables, and the
browser findings. Between them they know whether our prompt edits are working, which rubric
dimension has been weak for a week, which brief breaks the chain, and what any of it cost.

**None of that is readable.** Each run is a fan of seven markdown files, and there is no view
across runs at all — the cross-run knowledge exists only as `compare.py` functions whose output
nobody sees without constructing a CLI invocation.

This builds the surface those runs deserve:

```
.runs/index.html                          ← the dashboard: all runs, all trends
      └── <run>/reports/run.html          ← one run: grade, every stage, the row matrix
              └── reports/<stage>.html    ← one stage: every row, judge narrative,
                                             live preview of what was built, the markdown
```

Plus a **one-file export** per run, for sending to someone who has no repo.

Five views on the dashboard:

| View | Answers |
|---|---|
| **Quality trend** | Are we getting better, and since when? |
| **Prompt version history** | Did *that specific edit* help, or is it judge noise? |
| **Dimension heatmap** | Which paragraph of which `AGENT.md` is chronically weak? |
| **Stage × row matrix** | Is this phase weak everywhere, or is one brief dragging it down? |
| **Cost & code health** | What are we spending, and is the built artifact actually working? |

**The rule that keeps it honest**: the dashboard is a *rendering*, never a computation. Grades come
from `markdown_report.compute_overall()`. Prompt-version verdicts and the noise band come from
`compare.group_by_prompt()`. Code scores come from `code_grader`. Nothing is re-derived — a second
implementation of the grade arithmetic is precisely the class of bug this harness exists to catch.
No model is called. Any run folder can be re-rendered at any time, offline, for free.

---

## 1. Problem Statement

The grading harness produces high-value, structured evidence and then buries it. Within a run,
findings are spread across up to seven markdown files linked only by relative paths. Across runs
there is no view at all: the cross-run logic in `compare.py` — pairwise deltas with a noise guard,
and grouping by `system_prompt_hash` to show whether a prompt edit actually moved the score — is
reachable only through the terminal, one invocation at a time, and its output is retained nowhere a
person browses. Twenty runs of accumulated evidence therefore answer none of the questions they
contain. This feature renders that evidence as a browsable static site with cross-run analytics at
the top and, at the bottom of the drill-down, the actual artifact the agent produced.

---

## 2. User Scenarios & Acceptance Criteria

### Story 1 — See every run at once (Priority: P1)

An engineer opens `.runs/index.html` and sees all runs listed newest-first with grade, phase count,
row count, status, and class badge, above the five analytical views. No repo navigation, no CLI.

**Why P1**: this is the feature. There is no cross-run view of any kind today.

**Acceptance Scenarios**:
1. **Given** N run folders under `.runs/<workflow>/`, **When** `grade.sh dashboard` runs, **Then**
   `.runs/index.html` exists and lists all N, each linking to its run page.
2. **Given** a run classified `reference`, `copy`, or `partial` (per C3), **When** the dashboard
   renders, **Then** it is badged with its class and excluded from trend aggregates, with a "show
   excluded" toggle that reveals it in place — never silently dropped.
3. **Given** a run folder that fails to parse, **When** the dashboard renders, **Then** it appears
   with an error badge naming the failure and the rest of the dashboard renders normally.
4. **Given** the page is opened from `file://` with no network, **When** it loads, **Then** it
   renders fully — no external stylesheet, script, font, or image, and **no `fetch()`** (blocked for
   `file://` origins; all data is inlined).

---

### Story 2 — Know whether the last prompt edit worked (Priority: P1)

The engineer opens the **prompt version history** view for `prototype-build`, sees each version's
`system_prompt_hash`, how many runs used it, its aggregate, the delta against the baseline, and
whether that delta clears the noise band. Selecting two versions shows the **actual diff of the
captured prompt text** beside the score delta.

**Why P1**: this is the loop the whole harness feeds, and today it produces a terminal table nobody
keeps.

**Acceptance Scenarios**:
1. **Given** runs spanning ≥2 distinct `system_prompt_hash` values for one agent, **When** the view
   renders, **Then** versions appear chronologically by first-seen with runs, aggregate, delta, and
   a met/not-met verdict — the values returned by `compare.group_by_prompt()`, unmodified.
2. **Given** a delta inside the noise band, **When** it renders, **Then** it is shown as *within
   noise*, not as an improvement, and the band's basis (2σ, floor 1.0) is stated on the page.
3. **Given** two versions are selected and both captured prompts exist under `prompts/`, **When**
   the diff renders, **Then** added/removed lines are shown with the score delta beside them.
4. **Given** a version whose captured prompt file is missing (an older folder), **When** it renders,
   **Then** the row still shows scores and the diff control is disabled with the reason.

---

### Story 3 — Drill from a grade to the artifact that earned it (Priority: P1)

From the dashboard the engineer clicks a run → sees all five stages with the grade hero and the
stage × row matrix → clicks the weakest stage → sees every row with the judge's rationale,
weaknesses, evidence, sub-scores, and code findings → expands the worst row and **sees the
prototype that was actually built**, rendered, next to the criticism of it.

**Why P1**: the top of the funnel is worthless without the bottom. Reading a rationale about a
layout while looking at that layout is the thing markdown structurally cannot do.

**Acceptance Scenarios**:
1. **Given** a run page, **When** it renders, **Then** it shows the letter grade and blended score
   identical to `compute_overall()`, a phase table whose `effective` column matches `report.md`, and
   links to each stage page.
2. **Given** a stage page, **When** a row is expanded, **Then** it shows brief, judge score,
   per-dimension sub-scores, rationale, strengths, weaknesses, per-dimension evidence quotes,
   `score_caps` with before→after values, precheck reason, and that row's code findings.
3. **Given** a row whose deliverable is `src/<row_id>/prototype.html`, **When** it is expanded,
   **Then** a **sandboxed iframe with scripts disabled** renders it in place, with a toggle to the
   escaped source and a link to the file.
4. **Given** a row whose deliverable is markdown (`spec.md`, `tasks.md`, `design.md`), **When** it is
   expanded, **Then** its content is shown per C6 (escaped monospace in v1).
5. **Given** the run's transcripts at `logs/<row_id>/<stage>.log`, **When** a row is expanded,
   **Then** a link is offered, marked unavailable rather than broken when the page is viewed
   detached from its folder.

---

### Story 4 — Tell a weak phase from a weak brief (Priority: P1)

The engineer looks at the **stage × row matrix**: stages down, dataset rows across, each cell the
blended score for that pair. A uniformly low matrix row means the prompt is wrong. A low column
means one brief breaks everything downstream.

**Why P1**: a per-stage average actively hides this, and it changes what you go and fix.

**Acceptance Scenarios**:
1. **Given** a run with S stages and R rows, **When** the matrix renders, **Then** it has S×R cells
   whose values are the same `(stage, row)` cells `compute_overall()` averages — verified by test
   against that function's output.
2. **Given** cells that scored 0, **When** they render, **Then** the *kind* is distinguishable —
   precheck fail, dispatch error, broken chain, judge failure — by glyph, not merged into one
   colour.
3. **Given** a cell is clicked, **When** it resolves, **Then** the stage page opens with that row
   expanded.
4. **Given** the dashboard-level matrix across runs, **When** it renders, **Then** each cell shows
   the mean over included runs plus its spread, and names how many runs contributed.

---

### Story 5 — See the trend, the chronic weakness, and the cost (Priority: P2)

The engineer scans the quality trend, the dimension heatmap, and the cost/code-health view to answer
*are we improving*, *what is always weak*, and *what is this costing*.

**Why P2**: high value, but Stories 1–4 are what make the dashboard load-bearing.

**Acceptance Scenarios**:
1. **Given** ≥2 included runs, **When** the trend renders, **Then** each run's blended grade is
   plotted chronologically, split by phase, with `reference` runs drawn as horizontal ceiling/floor
   lines rather than trend points.
2. **Given** stages carrying `dimensions` aggregates, **When** the heatmap renders, **Then**
   dimensions × phases and dimensions × runs are shown, with the worst mean surfaced first.
3. **Given** stages carrying `tokens`, **When** the cost view renders, **Then** agent and judge
   spend are split, per run and per phase.
4. **Given** code findings exist, **When** the health view renders, **Then** console errors,
   uncaught exceptions, dead nav, and failed interactions are trended across runs.
5. **Given** every chart, **When** it renders, **Then** it is **inline SVG with no library**, is
   readable in both themes and in print, and every plotted value is also present as text (a table or
   a title) so nothing is chart-only.

---

### Story 6 — Send one run to someone with no repo (Priority: P2)

The engineer exports a single run as one self-contained HTML file and sends it over Slack.

**Acceptance Scenarios**:
1. **Given** `grade.sh dashboard --export <run-id>`, **When** it completes, **Then**
   `reports/<dataset_run_id>.export.html` exists, opens on a machine with no repo and no network,
   and its grade, phase table, and row scores are **identical to that run's `run.html`** (asserted by
   test — the two paths share their section builders).
2. **Given** inlined previews would exceed the size budget (C7, default 8 MB), **When** the export is
   written, **Then** previews are inlined largest-value-first until the budget is reached and the
   remainder become labelled placeholders naming the `src/` path — never a silent omission.

---

### Story 7 — It stays current without being remembered (Priority: P1)

**Acceptance Scenarios**:
1. **Given** any `run` / `rejudge` / `code` pass completes, **When** it finishes, **Then** the
   dashboard and that run's pages are rebuilt and their paths printed alongside the markdown path.
2. **Given** the auto-rebuild raises, **When** the run finishes, **Then** the run still reports
   success and the failure is a logged warning — a reporting bug must never fail a completed run.
3. **Given** `grade.sh dashboard`, **When** invoked on any existing folder, **Then** everything is
   rebuilt from stored artifacts with **no model call and no dispatch**, and errors surface normally.
4. **Given** an unchanged run folder, **When** a rebuild runs, **Then** its pages are not re-rendered
   (incremental), and a forced full rebuild is available via `--force`.
5. **Given** the same inputs, **When** rendered twice, **Then** the output is **byte-identical** — no
   render timestamps, no counter-derived IDs.

---

### Story 8 — Never break, never lie, never execute (Priority: P1)

Judge rationales quote agent output. Agent output *is* HTML.

**Why P1**: the reference snippet that prompted this work fails here — it interpolates model text
into an f-string unescaped. At our payloads that is a certainty, not a risk.

**Acceptance Scenarios**:
1. **Given** a rationale containing `<script>alert(1)</script>`, `</td>`, `&`, or quotes, **When** any
   page renders it, **Then** the characters appear as literal text, no script executes, and the
   layout is intact.
2. **Given** data inlined for the charts, **When** it is emitted, **Then** `</` sequences are
   neutralised so the payload cannot terminate its own `<script>` block.
3. **Given** a deliverable preview, **When** it renders, **Then** it is inside a `sandbox`ed iframe
   with scripts disabled — never injected into the page's own DOM.
4. **Given** any missing or `None` field, **When** it renders, **Then** it uses `render.py`'s em-dash
   convention and no literal `None` reaches the page.

---

## 3. Technical Design

### 3.1 Tech Stack Context

- **Language**: Python 3.11 — `html.escape`, `json.dumps`, `pathlib`, f-strings. Nothing else.
- **Frontend**: hand-written HTML5 + CSS + vanilla ES2020, inlined. Charts are **hand-emitted inline
  SVG**. No React, no bundler, no CDN, no charting library, no vendored JS.
- **Testing**: pytest, following `tests/unit/test_grading_markdown_report.py`.
- **Hard constraint**: `fetch()` against `file://` is blocked by browser origin rules. Every page
  inlines its own data. There is no shared `data.json`.

### 3.2 Architecture Fit

New package `backend/evals/grading/site/`, a peer of the existing renderers — model-free, pure
functions over on-disk artifacts, regenerable at any time:

```
evals/grading/site/
  __init__.py
  builder.py     # scan .runs/, classify runs, orchestrate the build
  model.py       # load one run folder -> the typed view-model every page renders
  pages.py       # dashboard / run / stage page assembly (shared section builders)
  export.py      # the one-file export (same sections, srcdoc previews, in-page tabs)
  charts.py      # inline-SVG primitives: line, bar, heatmap cell, distribution strip
  assets.py      # the CSS and JS, as string constants
```

**Everything numeric is imported, never re-derived**:

| Needed | Comes from |
|---|---|
| Blended grade, per-phase `effective`, per-cell values | `markdown_report.compute_overall()`, `letter_grade()`, `GRADE_BANDS` |
| Prompt-version grouping + noise band verdicts | `compare.group_by_prompt()`, `noise_band()`, `SIGMA_MULTIPLIER`, `MIN_THRESHOLD` |
| Code scores and findings | `code_grader.read_findings()`, `blended_score()` |
| Judge-failure detection | `scoring.judge_errored()`, `judge_error_reason()` |
| Every path under a run folder | `artifacts.*` — no path is built by hand |
| Number formatting | `render.py` — `score`, `number`, `flag`, `model_label`, `short_hash`, `truncate`, `plural`, `DASH` |

The **only** new arithmetic is aggregation *across* runs (means, spreads, chronological grouping)
that no existing module owns; it lives in `model.py` and is unit-tested against fixtures.

**Wiring** (C4): the auto-rebuild hangs off the existing report path — `markdown_report`'s
`write_report` callers (`grade_runner`'s run/rejudge/report paths, and
`model_grader._write_markdown_report`) — so no new call site needs keeping in sync, consistent with
the standing rule that features extend the main pipeline rather than growing a sibling. The auto
path is best-effort and swallows its own errors; the explicit command does not.

### 3.3 Data Model Changes

**None.** No new artifact, no schema change, no migration. Inputs, all already written:

| Source | Read via | Supplies |
|---|---|---|
| `run_summary.json` | `artifacts.read_run_summary` | stages, `not_run`, status, timings, ids, overrides |
| `grade_config.resolved.yaml` | `artifacts.read_resolved_config` | models, concurrency, repeats, `no_judge` |
| `artifacts/<token>_score.json` | `artifacts.read_stage_artifact` | stats, dimensions, results, clusters, warnings, baseline, hashes, tokens |
| `artifacts/<token>_grade.json` | ″ | rationale, sub-scores, strengths, weaknesses, evidence, caps, skips |
| `artifacts/<token>_run.json` | ″ | per-row brief |
| `artifacts/<token>_code_findings.json` | `code_grader.read_findings` | code score, static issues, JS errors, nav, interactions |
| `prompts/<token>_system_prompt.md` | `artifacts.read_system_prompt` | prompt-version text and diffs |
| `src/<row_id>/*` | `artifacts.src_dir` | deliverables — previews and markdown |
| `logs/<row_id>/<token>.log` | `artifacts.log_path` | transcript links |
| `reports/prompt_advice_<token>.md` | filesystem presence | the advice section, where it exists |

Any section whose source is absent is **omitted, not faked** — older folders render fine.

### 3.4 API Design

No HTTP surface. Python:

```python
def build_site(runs_root: Path, *, force: bool = False) -> Path:
    """Rebuild the dashboard and every run/stage page. Returns index.html."""

def build_run_pages(run_dir: Path) -> Path:
    """Render one run's run.html + stage pages. Returns run.html."""

def export_run(run_dir: Path, *, max_bytes: int = 8 * 1024**2) -> Path:
    """One self-contained file for one run. Returns the export path."""
```

CLI — one new free subcommand, described in `grade.sh` the way `code` and `report` already are:

```bash
./grade.sh dashboard                      # rebuild everything (free)
./grade.sh dashboard --force              # ignore the incremental skip
./grade.sh dashboard --export <run-id>    # + the one-file export
./grade.sh dashboard --open               # open index.html in the browser
```

### 3.5 Page Design

**Dashboard — `.runs/index.html`**
Header: workflow selector (hidden while only one exists, per C8), run count, date span, theme
toggle. Then:
- **Run list** — newest first: grade pill, blended score, workflow, dataset, rows, phases, status,
  class badge, date. Sortable, filterable, searchable; "show excluded" reveals references/copies.
- **V1 Quality trend** — chronological blended grade, overall and per phase; references as horizontal
  ceiling/floor lines.
- **V2 Prompt version history** — per agent, versions by `system_prompt_hash` with runs, aggregate,
  delta, noise verdict; two-version prompt-text diff.
- **V3 Dimension heatmap** — dimensions × phases and dimensions × runs; worst first.
- **V4 Stage × row matrix** — aggregated across included runs; cell = mean + spread + contributing
  run count.
- **V5 Cost & code health** — agent/judge tokens per run and phase; console errors, uncaught
  exceptions, dead nav, failed interactions trended.

**Run page — `<run>/reports/run.html`**
Grade hero (letter, `NN.N / 100`, the band scale with the run's position marked, counted cells, and a
red callout naming failed cells). Phase table linking to stage pages. **Stage × row matrix for this
run.** Warnings, not-run, signals (including the ⚠️ *judged NOT ready — the run proceeded anyway*
alerts), cross-phase strength/weakness clusters with row links that deep-link into stage pages.
Provenance table with model IDs, resolved judge id, rubric/dataset/prompt hashes, and the
CLI-override divergence warning. Copy-to-clipboard rejudge / code / reproduce commands.

**Stage page — `<run>/reports/<agent_token>.html`**
Warnings first, then baseline verdict and its failure list. Spread strip (avg all, avg passed,
median, stddev, min, max, distinct). Dimensions table, worst-mean first. Tokens. **Rows table** —
row, expect, precheck, judge, code, combined, passed, one column per dimension, note — sortable on
every column, filter chips (*failures only*, *negative tests*, *judge errors*, *capped*), free-text
search across id/rationale/evidence, and a visible "showing X of Y". Each row expands into the detail
of Story 3, including the sandboxed preview and the markdown. Recurring clusters. Per-stage rejudge
command.

**Export — `<run>/reports/<id>.export.html`**
The run page and all its stage pages as in-page tabs, previews inlined as sandboxed `srcdoc` within
the C7 budget, nothing external.

**Cross-cutting**
Deep links `#run=<id>&stage=<token>&row=<row_id>` restore state on load. System font stack; light and
dark via `prefers-color-scheme` plus a persisted toggle applied before first paint. Tables scroll
inside their own container so the body never scrolls horizontally. Long text lives in bounded,
wrapping, scrollable blocks. Keyboard: arrow keys across tabs, Enter/Space to expand, `/` focuses
search, `Esc` clears; focus rings never removed. `prefers-reduced-motion` respected; WCAG AA contrast
in both themes; colour never the sole signal. Print stylesheet expands everything linearly.

### 3.6 What we deliberately do not do

- No framework, no build step, no `node_modules`, no vendored JS (C6 option C is declined).
- **No score computed in JavaScript.** JS sorts and filters values Python already produced.
- No replacement of the markdown reports — `report.md` stays the diffable, greppable form.
- No writing to run folders beyond `reports/`. The artifacts are the record; this only renders.

---

## 4. Non-Functional Requirements

| Requirement | Target | Measurement |
|---|---|---|
| Self-containment | Zero external requests, zero `fetch()` | Test asserts no remote `src`/`href` and no `fetch(`/`XMLHttpRequest` in output |
| Escaping | 100% of interpolated model text escaped | Test injects `<script>`, `</td>`, `&`, quotes into rationale/evidence/brief/deliverable and asserts literal presence, no raw tag, no unescaped `</` in JSON |
| Determinism | Byte-identical on re-render | Test renders twice, compares |
| Fidelity | Dashboard, run page, and export agree with `compute_overall()` and `report.md` | Test cross-checks all three for one fixture run |
| Matrix correctness | Cells equal `compute_overall()`'s cells | Test compares cell-by-cell |
| Noise honesty | Prompt-version verdicts equal `compare.group_by_prompt()` | Test asserts pass-through, no re-derivation |
| Build time | Full rebuild of 20 runs < 10 s | Timed test on the fixture set |
| Incremental | Unchanged run not re-rendered | Test asserts mtime unchanged without `--force` |
| Export size | ≤ 8 MB default, never silently truncated | Test asserts budget honoured and placeholders labelled |
| Robustness | One bad run folder never fails the build; auto-rebuild never fails a run | Tests for corrupt JSON, missing config, missing grades, missing code findings, `compute_overall() is None`, and a raising rebuild inside a successful run |
| Accessibility | WCAG 2.1 AA, full keyboard operation | Contrast check both themes; tab/expand/search without a mouse |
| Test coverage | >80% of `site/` | pytest coverage |

---

## 5. Out of Scope

- An HTML face for `grade.sh compare`'s pairwise report (V2 answers the question that matters).
- Editing prompts from the dashboard — `apply-advice` / `revert` stay CLI-owned (spec 007).
- HTTP serving, hosting, auth, or an index across machines.
- Live/streaming updates during a run.
- Any change to scoring, rubrics, or artifact schemas.
- Replacing or deprecating the markdown reports.

---

## 6. Dependencies & Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Unescaped model output breaks or hijacks a page | High — payloads *are* HTML | High | Single `_esc()` choke point + injection test; `</`-neutralised JSON; sandboxed iframes, scripts disabled |
| Site and export drift in what they claim | Medium | High | Shared section builders; test asserts identical grade/phase/row values |
| Numbers drift from the markdown / terminal | Medium | High | All arithmetic imported from `compute_overall`, `compare`, `code_grader`; fidelity tests |
| Auto-rebuild fails a successful run | Medium | High | Best-effort with caught exceptions; explicit command surfaces errors |
| Rebuild slows as runs accumulate | Medium | Medium | Incremental skip on unchanged folders; `--force` escape hatch; timed test |
| Export bloats to tens of MB | Medium | Medium | Hard budget, value-ordered inlining, labelled placeholders (C7) |
| Hand-written CSS/JS rots | Medium | Low | Keep it small and boring; structural tests over emitted HTML |
| Scope creep into a product | Medium | Medium | §5 is binding; comparison UI and prompt editing are separate specs |

---

## 7. Task Planning Requirements

`/apex:plan` should slice this so each slice is independently verifiable and lands value early:

1. **Read layer** — `model.py`: load and classify a run folder into the view-model; aggregation across
   runs. Pure functions, fixture-tested, no HTML.
2. **Run + stage pages** — the drill-down, including previews and row detail. Delivers Story 3 on its
   own.
3. **Dashboard shell + run list** — Story 1.
4. **The five views** — one slice per view; V2 (prompt history) and V4 (matrix) first, as the two that
   answer questions nothing else can.
5. **Export** — Story 6, reusing the section builders.
6. **Wiring** — `grade.sh dashboard`, auto-rebuild, incremental, `--force`, `--open`.

Escaping, determinism, and fidelity tests are written **with** slices 1–2, not appended at the end.

---

**Next**: `/apex:plan` to generate `tasks.md`. C6–C8 carry stated defaults and need no further input
to start.
