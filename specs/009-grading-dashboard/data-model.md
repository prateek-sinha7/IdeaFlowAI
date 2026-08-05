# Data Model: The Grading Dashboard

## 0. Persisted schema changes: **NONE**

This feature adds no database table, no new artifact, no field to any existing artifact, and no
migration. It is a **read-only renderer** over files the grading harness already writes.

What follows is therefore the **view-model**: the in-memory shapes `site/model.py` builds from
those files and hands to the page builders. It is documented to the same standard as a persisted
schema because it is the contract between the read layer and every page, and the fidelity tests
assert against it.

---

## 1. Sources (read-only inputs)

| # | File | Reader | Cardinality |
|---|---|---|---|
| I1 | `run_summary.json` | `artifacts.read_run_summary` | 1 per run |
| I2 | `grade_config.resolved.yaml` | `artifacts.read_resolved_config` | 0–1 per run |
| I3 | `artifacts/<token>_score.json` | `artifacts.read_stage_artifact` | 1 per graded stage |
| I4 | `artifacts/<token>_grade.json` | ″ | 0–1 per stage |
| I5 | `artifacts/<token>_run.json` | ″ | 0–1 per stage |
| I6 | `artifacts/<token>_code_findings.json` | `code_grader.read_findings` | 0–1 per stage |
| I7 | `prompts/<token>_system_prompt.md` | `artifacts.read_system_prompt` | 0–1 per stage |
| I8 | `src/<row_id>/*` | `artifacts.src_dir` | 0–N per row |
| I9 | `logs/<row_id>/<token>.log` | `artifacts.log_path` | 0–1 per (row, stage) |
| I10 | `reports/prompt_advice_<token>.{md,json}` | path existence | 0–1 per stage |

**Invariant**: `site/` never constructs a path under a run folder. Every one comes from
`artifacts.*`. Adding a path helper there is preferable to building one here.

---

## 2. Entities

### 2.1 `SiteModel` — the whole `.runs/` tree

| Field | Type | Notes |
|---|---|---|
| `runs_root` | `Path` | `<grading root>/.runs/` |
| `workflows` | `list[WorkflowModel]` | Sorted by name; usually one (`prototype`) |
| `generated_from` | `str` | Absolute root path — **no timestamp** (determinism, D7) |

### 2.2 `WorkflowModel`

| Field | Type | Notes |
|---|---|---|
| `name` | `str` | Directory name under `.runs/` |
| `runs` | `list[RunModel]` | **Newest first**, by `dataset_run_id` (timestamp-prefixed ⇒ lexical sort is chronological) |
| `included` | `list[RunModel]` | `runs` filtered to `class == "run"` — the only ones feeding charts |
| `references` | `list[RunModel]` | Drawn as ceiling/floor lines, never trend points |

### 2.3 `RunModel` — one run folder

| Field | Type | Source | Notes |
|---|---|---|---|
| `dataset_run_id` | `str` | folder name | Primary key within a workflow |
| `run_dir` | `Path` | — | |
| `run_class` | `enum` | derived | `run` \| `reference` \| `copy` \| `partial` \| `error` |
| `class_reason` | `str \| None` | derived | Shown in the badge tooltip — a classification must always explain itself |
| `status` | `str` | I1 `status` | |
| `created_at` / `finished_at` | `str \| None` | I1 | Displayed verbatim; never parsed for sorting |
| `workflow_id` / `dataset_id` / `run_id` | `str` | I1 | `run_id` is the **config** id, not the folder |
| `row_count` | `int` | I1 | |
| `not_run` | `list[str]` | I1 | Stages that never ran |
| `overrides` | `dict` | I1 `config.overrides` | Non-empty ⇒ reproducibility warning |
| `model_under_test` / `judge` | `dict` | I2 | `{provider, model}` |
| `options` | `dict` | I2 | `concurrency`, `repeats`, `no_judge` |
| `overall` | `OverallModel \| None` | `grades.compute_overall()` | **`None` is legal** — nothing gradable |
| `stages` | `list[StageModel]` | I3–I7 | Only stages that wrote a `score` |
| `matrix` | `MatrixModel` | derived | §2.8 |
| `errors` | `list[str]` | derived | Per-file read failures; presence ⇒ `run_class == "error"` |

**Classification rules** (C3), evaluated in order:

| Order | Class | Rule |
|---|---|---|
| 1 | `error` | Any unreadable required file (`run_summary.json` missing or corrupt) |
| 2 | `copy` | Folder name ends `-copy` |
| 3 | `reference` | Folder name has no `YYMMDD-HHMMSS-` prefix (e.g. `golden-mission-control`), or sits under a `calibration/` fixture path |
| 4 | `partial` | `status` not complete, **or** any stage `stale` / `not_run`, **or** `overall is None` |
| 5 | `run` | otherwise |

### 2.4 `OverallModel`

Pass-through of `grades.compute_overall()`. **Not recomputed, not rounded, not adjusted.**

| Field | Type | Notes |
|---|---|---|
| `score` | `float` | 0–100 blended |
| `grade` | `str` | A++ … F |
| `counted` | `int` | Cells averaged |
| `failed_cells` | `int` | Cells scoring 0 |
| `stages` | `dict[str, {effective, cells, failed}]` | Per-phase view of the same arithmetic |

### 2.5 `StageModel`

| Field | Type | Source |
|---|---|---|
| `agent_id` / `agent_token` | `str` | I1 (`token = agent_id.replace("-", "_")`) |
| `counts` | `dict` | I3 — rows, dispatched, judged, judge_errored |
| `scores` | `dict` | I3 — average_all, average_precheck_passed, median, stddev, min, max, distinct_score_count |
| `dimensions` | `dict[str, {count, mean, median, stddev, min, max}]` | I3 |
| `tokens` | `{agent, judge, in, out, total}` | I3 |
| `hashes` | `{rubric_hash, dataset_hash, judge_resolved_model_id, system_prompt_hash}` | I3 |
| `warnings` | `list[str]` | I3 — rendered **above** the numbers |
| `baseline` | `{verdict, failures[]}` | I3 |
| `recurring_strengths` / `recurring_weaknesses` | `list[{evidence, row_ids[]}]` | I3 |
| `rows` | `list[RowModel]` | I3 `results` joined to I4/I5/I6 |
| `system_prompt` | `str \| None` | I7 — absent on older folders |
| `advice_path` | `Path \| None` | I10 |

### 2.6 `RowModel` — one (stage, row) cell

| Field | Type | Source |
|---|---|---|
| `row_id` | `str` | I3 (`row_id` \| `scenario_id` \| `id`) |
| `expect` | `"pass" \| "fail"` | I3 |
| `precheck_passed` | `bool \| None` | I3 — **`None` means never dispatched (broken chain)** |
| `precheck_reason` | `str \| None` | I4 |
| `errored` | `bool` | I3 |
| `judge_score` | `float \| None` | I3 |
| `code_score` | `float \| None` | I6 |
| `combined` | `float \| None` | `code_grader.blended_score()` |
| `cell_value` | `float \| None` | `grades._cell_value()` — **the matrix cell** |
| `cell_kind` | `enum` | `ok` \| `precheck_fail` \| `errored` \| `broken_chain` \| `judge_failed` \| `negative` \| `unjudged` |
| `passed` | `bool \| None` | I3 |
| `sub_scores` | `dict[str, float]` | I4 |
| `rationale` / `strengths` / `weaknesses` / `evidence` | `str` / `list` / `list` / `dict` | I4 |
| `score_caps` | `dict[str, {reported, capped_to, weaknesses}]` | I4 |
| `judge_error` | `str \| None` | `scoring.judge_error_reason()` |
| `skipped_reason` | `str \| None` | I4 |
| `brief` | `str` | I5 `prompt` |
| `deliverables` | `list[Deliverable]` | I8 |
| `log_path` | `Path \| None` | I9 |

`cell_kind` exists because **four distinct situations all score 0** and an average erases the
difference. The matrix must distinguish them (Story 4.2):

| `cell_kind` | Condition | Value |
|---|---|---|
| `errored` | `errored is True` | 0.0 |
| `broken_chain` | `precheck_passed is None` (never dispatched — upstream broke) | 0.0 |
| `precheck_fail` | `precheck_passed is False` | 0.0 |
| `negative` | `expect == "fail"` | excluded |
| `unjudged` | passed precheck, no judge and no code score | excluded |
| `ok` | otherwise | `blended_score(judge, code)` |
| `judge_failed` | overlay flag from `scoring.judge_errored()` | as above |

### 2.7 `Deliverable`

| Field | Type | Notes |
|---|---|---|
| `filename` | `str` | e.g. `prototype.html`, `spec.md` |
| `path` | `Path` | Under `src/<row_id>/` |
| `kind` | `enum` | `html` \| `markdown` \| `other` (by suffix) |
| `size_bytes` | `int` | Drives the export budget ordering (C7) |
| `relative_href` | `str` | From the page's own location — how the site iframes it |

`html` ⇒ sandboxed iframe preview + escaped source toggle. `markdown` ⇒ escaped monospace (C6-A).
`other` ⇒ link only.

### 2.8 `MatrixModel` — stage × row

| Field | Type | Notes |
|---|---|---|
| `stage_ids` | `list[str]` | Matrix rows, in pipeline order |
| `row_ids` | `list[str]` | Matrix columns, union across stages, sorted |
| `cells` | `dict[(stage_id, row_id), MatrixCell]` | Sparse — a missing pair renders as "not applicable", distinct from a 0 |

`MatrixCell`: `{value: float|None, kind: cell_kind, run_count: int, spread: float|None}`.

At run scope `run_count == 1` and `spread is None`. At dashboard scope `value` is the mean over
included runs, `spread` its stddev, and `run_count` how many contributed — a mean over 2 runs and
one over 15 must not look alike.

### 2.9 `PromptVersionModel` — V2

| Field | Type | Source |
|---|---|---|
| `agent_id` | `str` | — |
| `versions` | `list[PromptVersion]` | `compare.group_by_prompt()`, **unmodified** |
| `noise` | `dict` | `compare.noise_band()` |

`PromptVersion`: `{hash, short_hash, first_seen, run_ids[], run_count, aggregate, delta,
verdict, prompt_text|None}`.

`verdict` ∈ `{improved, regressed, within_noise, baseline}` — **taken from `compare`, never
re-derived here**. `prompt_text` is `None` for folders predating prompt capture; the diff control
is then disabled with that reason shown (Story 2.4).

---

## 3. Relationships

```
SiteModel 1─n WorkflowModel 1─n RunModel
RunModel  1─1 OverallModel?          (None when nothing was gradable)
RunModel  1─n StageModel 1─n RowModel 1─n Deliverable
RunModel  1─1 MatrixModel            (cells keyed by (stage_id, row_id))
WorkflowModel 1─n PromptVersionModel (one per agent_id, across runs)
```

Join keys: **stage** by `agent_id` ⇄ `agent_token`; **row** by `row_id`, tolerating the three
historical id field names (`row_id` / `scenario_id` / `id`) exactly as `markdown_report._row_id`
already does.

---

## 4. Migrations

**None.** No persisted state exists to migrate.

Generated output is disposable and reproducible:

| Path | Lifecycle |
|---|---|
| `.runs/index.html` | Rewritten on every build |
| `<run>/reports/run.html`, `<run>/reports/<token>.html` | Rewritten when the run's artifacts are newer, or under `--force` |
| `<run>/reports/<id>.export.html` | Written on `--export` only |

Deleting any of them loses nothing — `grade.sh dashboard` reconstructs them. Nothing else under a
run folder is ever written, moved, or deleted by this feature.

---

## 5. Validation Rules

| # | Rule | On violation |
|---|---|---|
| V1 | Every interpolated string passes `_esc()` | Build-time invariant; injection test |
| V2 | Inlined JSON contains no unescaped `</` | Neutralise before embedding |
| V3 | `compute_overall()` may return `None` | Render "nothing gradable", never a fabricated grade |
| V4 | A stage without a `score` artifact is not a stage | Omitted from tabs and the matrix |
| V5 | Missing optional artifact | Section omitted, never faked or zero-filled |
| V6 | Corrupt JSON in one run | That run → `run_class == "error"` with the message; build continues |
| V7 | `None` never reaches the page as text | `render.DASH` |
| V8 | Excluded runs never enter an aggregate | Charts consume `WorkflowModel.included` only |
| V9 | Matrix cells equal `compute_overall()`'s cells | Cell-by-cell test |
| V10 | Prompt-version verdicts equal `compare`'s output | Pass-through test |
| V11 | Output is byte-deterministic | Sorted iteration; identifier-derived IDs; no render timestamp |
| V12 | Preview iframes carry `sandbox` without `allow-scripts` / `allow-same-origin` | Structural test |
