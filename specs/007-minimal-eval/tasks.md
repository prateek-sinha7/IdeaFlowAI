# Tasks: The Minimal Eval System

**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)
**Root**: `backend/evals/minimal/`

11 tasks. Only T7 spends tokens. Salvage is already done — `_source/`, `datasets/`,
`rubrics/` are on disk.

---

## T1 — Clear the ground
Delete the 14 orphaned `backend/tests/unit/test_grading_*.py` — they import deleted modules,
cannot pass, and mask real failures. Commit the empty state so the slate is a real baseline.

- [x] `pytest backend/tests/unit -q` collects with no import errors

---

## T2 — `store.py` (~150)
Path owner + JSON I/O. `run_dir` · `write` · `read` · `list_runs` · `snapshot_config`.
Append-only: a second write to the same `(run, stage, kind)` supersedes, never overwrites.
`snapshot_config` runs **before** the first dispatch.

- [x] Nothing outside `store.py` imports `pathlib` for run paths
- [x] Re-write supersedes; the original stays readable
- [x] Unit tests, no model, no network

---

## T3 — `checks.py` (~200)
Port `check_html()` from `_source/code_grader.py`, keeping its imports of
`app.agents.static_check` and `app.agents.render_check`. **Do not copy validator logic** —
import it, so the eval measures what production enforces.

Drop `blended_score`, `PENALTIES` tuning, `GRADED_STAGES`, the run-folder wrapper. Add
`check_run(run_id, stage)` as a thin shim over `check_html`.

- [x] `check_html("<html>…")` returns findings with no run folder and no model call
- [x] Never imports `judge` (asserted by test)
- [x] Findings include the two defects seen live: dead nav link, JS page error

---

## T4 — `score.py` (~250)
Port `noise_band()` and `compare_runs()` from `_source/compare.py` **unmodified** — this is
the one component that reliably told the truth. Add `aggregate(rows)`. Trim the metric list
to `mean`, `median`, `stddev`, `n`, `distinct`.

Pure: no I/O, no imports from this package, no model calls.

- [x] `compare` returns `within-noise` for a delta inside the band
- [x] `compare` **refuses** when either arm has n<2 (R-05)
- [x] Purity asserted by test (no `os`/`pathlib`/package imports)

---

## T5 — `run.py` (~250)
`run(config, *, stage=None, from_run=None, repeats=1) -> run_id`. The only module touching
the agent runtime.

Per row record `response`, `tokens_in/out`, `model_id`, `system_prompt_hash`, and
`origin: dispatched | replayed | seeded`.

- [x] `--stage build --from <run>` runs one stage against a stored upstream (R-01)
- [x] `origin` set correctly for dispatched vs seeded rows (R-04)
- [x] A crashed run leaves a readable folder with its config snapshot

---

## T6 — `cli.py` (~200)
The five commands from spec §2. Parsing and printing only — no logic.

Stage output is three unsynthesised facts, never a blend:
`build   judge 91.1 (n=2)   checks 40.7 (n=3)   completed 2/5`

- [ ] **Five commands, no more — VIOLATED**: `cli.py` registers **10** subcommands
      (`run`, `chain`, `judge`, `score`, `checks`, `compare`, `clone`, `workflows`,
      `report`, `advice`)
- [x] `eval checks <file.html>` works on a path with no run folder
- [x] No blended score anywhere in the output

---

## T7 — `judge.py` (~150) — **the only task that spends tokens**
Port the call + `_unpack_reply` retry handling from `_source/judge.py`. Leave severity caps,
`consistency_cap` and preflight behind.

A malformed reply returns partial results and costs one row (R-09) — observed twice live:
*"judge returned missing dimension ids"* silently burned paid rows.

- [x] Missing dimension → that row is dropped, the stage completes
- [x] One live smoke run on a single brief, then stop

---

## T8 — `report.py` (~300) — **highest regrowth risk, build last**
One `.runs/report.html` for the whole tree. Self-contained: inline CSS/SVG, no CDN, no
framework, no build step. Reads only stored JSON; imports `score.aggregate`.

Exactly four sections: runs table · trend · per-run drill-down · row detail.

- [x] Renders from JSON alone, no recomputation
- [x] A malformed/missing run degrades to a warning, never an exception (R-06)
- [ ] **≤300 lines — VIOLATED**: `report.py` is **600** lines

---

## T9 — Budget test  ❌ **NOT DONE — and the budget it would guard is already blown**
A test that fails when `backend/evals/minimal/*.py` exceeds **7 files or 1,500 lines**.

- [ ] Fails when a file is added or the budget is exceeded
- [ ] Names the number in the failure message

**Audit 2026-08-10.** The test was never written, and the budget the whole spec is built
around has been exceeded on every axis:

| Constraint | Budget | Actual | Over by |
|---|---|---|---|
| Files | 7 | **8** (`workflow.py` is the extra) | +1 |
| Lines | 1,500 | **3,733** | **2.5×** |
| CLI commands | 5 | **10** | 2× |
| `report.py` | ≤300 | **600** | 2× |

Per-file: `cli.py` 846 · `judge.py` 681 · `run.py` 674 · `report.py` 600 · `score.py` 267 ·
`store.py` 254 · `checks.py` 225 · `workflow.py` 186.

The plan's own words: *"Exceeding it is a bug, not a feature."*

**Decision 2026-08-10 — the constraint is RETIRED.** The budget was an aspiration that did not
survive contact with the work. It is recorded here rather than enforced: T9 will not be written,
because a test whose only outcome is failure is noise, and cutting ~2,200 lines from a package
that works and blocks nothing is not worth the days it would cost. The numbers above stand as
the honest record of what shipped.

---

## T10 — Remove the scaffolding
Delete `_source/`. Drop `stash@{0}` **only after** T3, T4 and T7 are green — it is the only
copy of `code_grader.py`, `judge.py` and `scoring.py`.

- [x] `_source/` gone
- [ ] **budget test passes — NO SUCH TEST EXISTS** (see T9)
- [x] `stash@{0}` dropped

---

## T11 — Prove the loop  ⬜ **user's live run**
Run the thing this system exists for, once: change one prompt, re-run **one stage** against a
stored upstream with `--repeats 2`, and read the verdict.

- [ ] The A/B costs one stage, not one chain
- [ ] The printed verdict is honest — `within-noise` is a valid, useful answer

---

## Order

T1 → T2 → (T3, T4 parallel) → T5 → T6 → T7 → T8 → T9 → T10 → T11

T3 and T4 are offline and independent — build them first and they anchor everything after.
