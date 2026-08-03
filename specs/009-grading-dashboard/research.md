# Research Notes: The Grading Dashboard

Everything below was verified against the code and the run folders on disk on 2026-07-30, not
assumed. Line references are to `backend/evals/grading/`.

---

## 1. What the run folders actually contain

`.runs/prototype/` holds **20 folders**: 19 timestamped runs (`260729-184718-small` …
`260730-173912-prototype_small`) plus `golden-mission-control`, and one `-copy`. A complete folder
(verified on `golden-mission-control`):

```
run_summary.json                       stages, status, not_run, ids, overrides
grade_config.resolved.yaml             every resolved setting — models, concurrency, no_judge
artifacts/<token>_{run,grade,score,output}.json
artifacts/<token>_code_findings.json   where the code track ran
artifacts/superseded/                  prior attempts, kept by the append-only guard
prompts/<token>_system_prompt.md       the composed prompt, verbatim   ← enables version diffs
src/<row_id>/…                         the actual deliverables         ← enables previews
logs/<row_id>/<token>.log              per-dispatch transcripts
reports/*.md                           the existing markdown set
```

Both features that make this dashboard more than a prettier table — **prompt-version diffs** and
**live deliverable previews** — are possible only because the runs already captured `prompts/` and
`src/`. Nothing new has to be recorded.

---

## 2. Decision Log

### DL1 — Where the grade arithmetic lives

- **Options**: (a) reimplement per-cell blending in `site/`; (b) import `markdown_report`;
  (c) extract to a neutral `grades.py` imported by both.
- **Chosen**: **(c)**.
- **Rationale**: (a) is disqualified outright — a grading harness cannot ship two implementations of
  its own scoring. (b) creates an import cycle once `markdown_report` triggers the site build.
  (c) is a verbatim move with a re-export, so `test_grading_markdown_report.py` is the regression
  gate and nothing downstream changes.

### DL2 — How the auto-rebuild is triggered

- **Options**: (a) update the three `write_report` call sites; (b) trigger from inside
  `write_report`; (c) a config hook.
- **Chosen**: **(b)**.
- **Rationale**: the requirement is that the dashboard is *never* stale, and (a) fails the moment a
  fourth call site appears. Crucially, all three existing call sites —
  `grade_runner.py:1250`, `grade_runner.py:1549`, `model_grader._write_markdown_report` — already
  wrap the call in `try/except` with an explicit *"rendering is never load-bearing"* comment, so
  (b) inherits best-effort semantics without editing any of them. (c) was rejected: `hooks.py` is
  the `./file.py:func` resolver for rubric `validate:` / stage `adapter:` references, a different
  mechanism entirely — reusing it here would overload a well-scoped abstraction.

### DL3 — Single file vs static site

- **Options**: single self-contained file; static site; hybrid.
- **Chosen**: **hybrid** (C1).
- **Rationale**: previews of built prototypes across 20 runs cannot fit one file, and previews are
  the drill-down's whole point. The site gets them via relative `iframe src`; the export exists for
  sharing outward and inlines what fits within a budget.

### DL4 — `fetch()` for page data

- **Options**: sibling `data.json` fetched at load; inline JSON per page.
- **Chosen**: **inline**.
- **Rationale**: **verified constraint** — Chrome treats `file://` documents as opaque origins and
  blocks `fetch()`/XHR against sibling files. A dashboard that only works behind `python -m
  http.server` fails the "double-click it" requirement. Cost: some duplication across pages;
  acceptable, and it makes each page independently portable.

### DL5 — Charting

- **Options**: Chart.js/D3 via CDN; vendored JS library; hand-emitted inline SVG; no charts.
- **Chosen**: **hand-emitted inline SVG**.
- **Rationale**: CDN is impossible (no network, and the file must work standalone). Vendoring
  contradicts the stdlib-only constraint that keeps this package cheap. The chart types needed —
  line, bar, heatmap grid, distribution strip, band track — are each a few dozen lines of SVG and
  are trivially theme- and print-aware, which library canvases are not. Every plotted value is also
  emitted as text so nothing is chart-only.

### DL6 — Markdown deliverable rendering

- **Options**: escaped monospace; minimal built-in renderer; vendored JS markdown library.
- **Chosen**: **escaped monospace for v1** (C6-A), toggle stub for a later renderer.
- **Rationale**: these are our own agents' `spec.md` / `tasks.md` / `design.md`, read for content.
  A subset renderer that silently mis-renders a table is worse than one that never pretends. The
  vendored option is declined on the same dependency grounds as DL5.

### DL7 — Fixtures for the test suite

- **Options**: test against the real `.runs/` folders; commit miniature fixtures; both.
- **Chosen**: **both, with different jobs**. Committed miniatures are the suite's substrate (`.runs/`
  is gitignored and would make tests machine-dependent and CI-hostile); the 20 real folders,
  especially `golden-mission-control`, are the manual verification substrate and the performance
  benchmark.

### DL8 — Run classification

- **Options**: include everything; exclude non-runs; classify and badge.
- **Chosen**: **classify and badge** (C3).
- **Rationale**: `golden-mission-control` is a hand-verified reference (central to spec 008) and
  belongs on the charts as a **ceiling line**, not as a trend point; `-copy` folders are duplicates
  that would double-count. Silently excluding either produces a chart that lies by omission.

### DL9 — Incremental rebuild

- **Options**: always full rebuild; mtime-based skip; content-hash manifest.
- **Chosen**: **mtime-based skip**, `--force` to override.
- **Rationale**: with byte-deterministic output (D7) a skip can never mask a difference. A hash
  manifest is a new artifact to keep correct for a rebuild that is already sub-10-second.

---

## 3. Reused machinery — verified, not assumed

| Capability | Where | Notes |
|---|---|---|
| Blended grade, letter, per-cell rules | `markdown_report.compute_overall()`, `letter_grade()`, `GRADE_BANDS` (A++ ≥97 … F <50) | `_cell_value` encodes the rules the matrix must show: errored → 0, precheck `None` (broken chain) → 0, precheck `False` → 0, `expect: fail` excluded, judged-never → excluded |
| Prompt versions + noise | `compare.group_by_prompt()`, `noise_band()`, `SIGMA_MULTIPLIER = 2.0`, `DEFAULT_MIN_THRESHOLD = 1.0`, `MIN_THRESHOLD = {"precheck_pass_rate": 0.01}` | Grouping is by `system_prompt_hash`, chronological by first-seen — exactly V2 |
| Aggregate metrics | `compare.AGGREGATE_METRICS`, `HEADLINE_METRIC = "average_all"` | All "higher is better", so delta sign reads directly |
| Code track | `code_grader.read_findings()`, `blended_score()` (0.7 judge / 0.3 code) | Findings carry `issues`, `warnings`, `render.{console_errors,page_errors,nav_results,coverage_errors}`, `interactions.{actions,failures,available}` |
| Judge failures | `scoring.judge_errored()`, `judge_error_reason()` | Distinguishes "not judged" from "judge broke" |
| Paths | `artifacts.runs_root()`, `run_folder()`, `artifact_path()`, `reports_dir()`, `src_dir()`, `log_path()`, `read_system_prompt()` | Sole owner of run-folder paths — `site/` builds none by hand |
| Formatting | `render.py` — `score`, `number`, `flag`, `model_label`, `short_hash`, `truncate`, `plural`, `DASH` | Keeps a number identical across terminal, markdown, and HTML |

`runs_root()` is already **keyed per workflow** (`<grading root>/.runs/<workflow>/`), which is why
C8 (workflow-awareness from the start) costs almost nothing.

---

## 4. Unknowns

| # | Question | Resolution path | Blocking? |
|---|---|---|---|
| U1 | Do rows differ across runs enough that the cross-run stage × row matrix has sparse columns? | Inspect dataset ids across the 20 folders during S1; if sparse, show per-dataset matrices | No — per-run matrix is unaffected |
| U2 | Total size of `src/` deliverables per run, for the export budget | Measure during S5; adjust the 8 MB default if it turns out to be miscalibrated | No |
| U3 | Do older folders carry `system_prompt_hash` in `score.hashes` consistently? | Survey during S1; versions without it group under "unknown", diff control disabled | No — spec already requires graceful degradation |
| U4 | Whether `-copy` is the only duplicate convention in use | Survey folder names in S1; classification rules extended if others appear | No |
| U5 | Interaction between the append-only `superseded/` artifacts and "latest" values | Read only current artifacts in v1; surface superseded attempts as a later enhancement | No |

None blocks the start of S0/S1.

---

## 5. References

- [`spec.md`](spec.md), [`clarifications.md`](clarifications.md), [`plan.md`](plan.md)
- [005-prompt-eval-scoring](../005-prompt-eval-scoring/spec.md) — the grading harness this renders
- [007-prompt-versioning](../007-prompt-versioning/spec.md) — `AGENT.vN.md` archives, the committed
  counterpart of the captured `prompts/` this dashboard diffs
- [008-grading-calibration](../008-grading-calibration/spec.md) — severity pricing and the code
  ceiling band; the golden/broken fixtures that appear as reference lines on the trend view
- `backend/evals/grading/README.md`, `docs/README.md`, `code/README.md` — the package's own docs
- `backend/tests/unit/test_grading_markdown_report.py` — the test conventions this follows
