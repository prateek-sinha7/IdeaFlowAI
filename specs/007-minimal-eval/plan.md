# Implementation Plan: The Minimal Eval System

**Spec**: [spec.md](spec.md) · **Tasks**: [tasks.md](tasks.md)
**Created**: 2026-07-31
**Root**: `backend/evals/minimal/`

---

## 1. Salvage — already done

The old package is deleted. `code_grader.py`, `judge.py` and `scoring.py` were **never
committed**, so the stash was their only copy. Everything needed is now on disk:

```
backend/evals/minimal/
├── _source/            TEMPORARY — delete at the end of the build
│   ├── compare.py      378   the noise guard
│   ├── code_grader.py  497   check_html + production-validator reuse
│   ├── judge.py        576   judge call + retry/unpack
│   └── artifacts.py    301   path discipline
├── datasets/prototype.json   34 briefs
└── rubrics/{specify,plan,analyze,build,validate}.yaml
```

Nothing else from the old system is needed. `stash@{0}` can be dropped once `_source/` is
consumed.

## 2. Architecture

```
backend/evals/minimal/
├── store.py       150   Owns every path + all JSON read/write. Nothing else touches disk.
├── run.py         250   Dispatch: one row → agent → response → artifact. Stage-isolated.
├── judge.py       150   response + rubric → sub-scores. One model call.
├── checks.py      200   Deterministic checks. Free. Never imports judge.
├── score.py       250   PURE. Aggregate + noise-guarded compare. Zero I/O.
├── report.py      300   Builds .runs/report.html from stored JSON.
├── cli.py         200   Parse, dispatch, print. No logic.
├── datasets/*.json      Briefs. Data, not code.
└── rubrics/*.yaml       Dimensions + judge config, per stage.
                 ─────
                 1,500
```

## 3. What to take from `_source/`, and what to leave

| From | Take | Leave |
|---|---|---|
| `compare.py` → `score.py` | `noise_band()`, `compare_runs()` **untouched** — the only component that refused to say what the operator wanted to hear | `group_by_prompt`, the metric zoo; keep 2–3 metrics |
| `code_grader.py` → `checks.py` | `check_html()` and its imports of `app.agents.static_check` / `render_check` — **the production validators**, so the eval measures what production enforces | `blended_score`, `PENALTIES` tuning, `GRADED_STAGES`, the run-folder wrapper |
| `judge.py` → `judge.py` | the call + `_unpack_reply` retry handling | severity caps, `consistency_cap`, preflight machinery |
| `artifacts.py` → `store.py` | the one-path-owner rule, append-only guard | superseded-attempt numbering, per-kind helpers |

Rewrite rather than trim where trimming would keep more than half the original.

## 4. File contracts

**`store.py`** — `run_dir` · `write` (append-only) · `read` · `list_runs` · `snapshot_config`
(written *before* the first dispatch, so a crashed run is still readable).

**`run.py`** — `run(config, *, stage=None, from_run=None, repeats=1) -> run_id`. Records per
row: `response`, `tokens_in/out`, `model_id`, `system_prompt_hash`, `origin`.

**`judge.py`** — `judge(response, rubric) -> {dimension: score, rationale, evidence}`. Partial
results on a malformed reply; never raises.

**`checks.py`** — `check_html(html: str) -> findings` (pure, any HTML, CI-able) and
`check_run(run_id, stage)`. The string entry point is what makes "runs on every commit" real.

**`score.py`** — `aggregate(rows)` · `compare(a, b)`. No I/O, no package imports, no model calls.

**`report.py`** — one `.runs/report.html` for the whole tree. Self-contained: inline CSS/SVG,
no CDN, no framework, no build step. Reads only stored JSON; imports `score.aggregate` rather
than recomputing. Four sections and no more:

1. Runs table, newest first — run id, per-stage score, completed/total, tokens, date
2. Trend — one inline-SVG line per stage across runs
3. Per-run drill-down — judge, checks, completed/total
4. Row detail — response excerpt, judge rationale, check findings

**`cli.py`** — the five commands in spec §2. Parsing and printing only.

## 5. Build order

| # | Deliverable | Milestone |
|---|---|---|
| 1 | `store.py`, `checks.py`, `score.py` from `_source/` | offline tests pass with no model, no runtime |
| 2 | `run.py` + `cli.py` | `eval run` on one row; `eval checks` on its output |
| 3 | `judge.py` + `eval compare` | two runs compared, noise verdict printed |
| 4 | `report.py` | `report.html` renders; a deleted run degrades to a warning |
| 5 | budget test; delete `_source/`; drop `stash@{0}` | ≤7 files, ≤1,500 lines |

**Do not start step 4 before step 3 works.** The old system had a 4,299-line dashboard over a
loop that could not answer its own question.

## 6. Risks

| Risk | Mitigation |
|---|---|
| `report.py` regrows — `site/` hit 4,299 lines | Four sections, hard budget, built last |
| Judge flakiness eats rows silently | R-09 partial results; `completed/total` on every stage |
| Small-n deltas read as real | `compare` refuses below n=2; noise verdict printed verbatim |
| `_source/` lingers and doubles the package | Step 5 deletes it; budget test would fail anyway |
| Reimplementing the production validators | `checks.py` imports `app.agents.*`; never copies logic |
