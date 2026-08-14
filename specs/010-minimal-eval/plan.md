# Implementation Plan: The Minimal Eval System

**Created**: 2026-07-30
**Status**: **OBSOLETE (2026-08-10).** This is the earlier draft of the same system.
It was never executed under this number; the work shipped as
[007-minimal-eval](../007-minimal-eval/spec.md), which is built and live at
`backend/evals/minimal/`. Kept for the reasoning in §1, which the shipped spec does not repeat.
Do not execute this plan.
**Replaces**: `evals/grading/` (13,538 LOC), `evals/hybrid/` (2,481), `evals/model_graded/` (2,033)
**Budget**: **7 files · 1,500 lines · 5 commands.** Exceeding it is a bug, not a feature.

---

## 1. Why

The current system is 18,000 lines of source and 10,000 of tests across three packages
and seven specs. On 2026-07-30 it was used to answer one question — *did this prompt edit
help?* — and it cost **10.3M tokens and roughly four hours** to return **"within-noise."**

The line count is not the problem. The failure pattern is. Every defect found that day was
an **integration seam**, not a logic error:

| Defect | Seam |
|---|---|
| `rejudge` re-scored but never regenerated reports — terminal said A, file said B | runner ↔ report |
| `markdown_report` raised `KeyError: 'capped_to'` and took the whole report down | report ↔ judge schema |
| "TOKENS UNDER-REPORTED" fired on every stage of every rejudge of a seeded run | scoring ↔ dispatch provenance |
| `TypeError: 'NoneType'` on `--agents X --from-run Y` | grader ↔ summary |
| A spec failed precheck for the phrase "no lorem ipsum" *in a compliance statement* | precheck ↔ reality |
| `apply-advice` could not apply a single real edit | advisor ↔ prompt composition |

Six defects, all "module A assumed something about module B." That is the signature of too
many parts, not bad code — each piece is well written, which is exactly what makes it hard
to see.

**The deeper mismatch**: the rigor machinery is calibrated for a sample size that does not
exist. Baselines, verdicts, consistency caps, `REFUSED`, `distinct_score_count` gates — all
built for statistical confidence, run against 1–5 rows. That day's noise band was **±2.73
derived from two samples**, and every verdict printed was `FAIL` or `REFUSED`. None of them
informed a decision.

## 2. What survives, verbatim

Three things earned their keep and are **ported unchanged, not rewritten**:

1. **`compare.py`'s noise guard.** The only component that refused to say what the operator
   wanted to hear — it correctly called a 19-point grade swing `within-noise`. Port it whole.
2. **`code_grader.check_html()` and its reuse of the production validators.**
   `app.agents.static_check` and `app.agents.render_check` are the same checks the engine runs
   in its per-task fix loop, so the eval measures exactly what production enforces rather than
   a parallel reimplementation that drifts. Every true signal that day came from here — the
   `store` initialization error, the dead `#/berth` nav link, code 42 → 97.
3. **`artifacts.py`'s single-path-owner discipline.** One module owns every path. Keep the
   rule even as the module shrinks.

## 3. Architecture

```
evals/
├── store.py       150   Owns every path + all JSON read/write. Nothing else touches disk.
├── run.py         250   Dispatch: one row → agent → response → artifact. Stage-isolated.
├── judge.py       150   response + rubric → per-dimension sub-scores. One model call.
├── checks.py      200   Deterministic output checks. Free, no model. Never imports judge.
├── score.py       250   PURE. Aggregate; compare two runs with a noise band. Zero I/O.
├── report.py      300   Builds .runs/report.html from stored JSON. Never breaks a run.
├── cli.py         200   Parse, dispatch, print. No logic of its own.
├── rubrics/*.yaml       Dimensions + judge config, per stage.
└── datasets/*.json      Briefs. Data, not code.
                 ─────
                 1,500
```

### The one structural decision everything else follows from

**Separate the expensive part (dispatch) from the cheap parts (score, compare, render), and
make every stage independently runnable against a stored upstream.**

`run.py --stage build --from <run-id>` must work from the first commit. Its absence is what
cost the most: every A/B had to re-run the whole chain, so upstream was re-sampled per arm and
the delta became unattributable. On 2026-07-30 the arms differed by one guardrail line, yet
`specify`/`plan`/`analyze` — which do not use that guardrail — moved from 3/5 to 5/5 graded,
and that variance drove the entire headline change from F 40.5 to E 59.0.

### Two tracks, one package, one rule

`checks.py` **must never import `judge.py`.** This is today's rule and it is correct: the
tracks have different failure modes, different costs and different cadences. The cheap,
deterministic checks must never become hostage to the expensive, flaky judge. What changes is
not the split but the **blend** — see §5.

## 4. File contracts

### `store.py` — the only module that touches disk

```
run_dir(run_id) -> Path                 mint/resolve a run folder
write(run_id, stage, kind, payload)     append-only; never overwrite
read(run_id, stage, kind) -> dict
list_runs() -> list[str]                newest first
snapshot_config(run_id, config)         written BEFORE the first dispatch
```

Append-only. A re-run supersedes rather than deletes — captured response text is
irrecoverable and a crashed run must stay readable.

### `run.py` — dispatch

One row → agent → response → artifact. The only module that touches the agent runtime.

```
run(config, *, stage=None, from_run=None, repeats=1) -> run_id
```

- `stage=` runs exactly one stage; `from_run=` seeds its upstream from a stored run.
- Records per row: `response`, `tokens_in`, `tokens_out`, `model_id`,
  `system_prompt_hash`, **`origin: dispatched | replayed | seeded`**.
- `origin` exists because its absence caused a false "tokens under-reported" warning on every
  stage of every rejudge of a seeded run: zero tokens were read as under-reporting when in
  fact nothing had been dispatched at all.

### `judge.py` — the model track

`judge(response, rubric) -> {dimension: score, rationale, evidence}`. One model call. Returns
partial results rather than raising — a judge that omits a dimension should cost one row, not
the run. (Observed twice in one day: *"judge returned missing dimension ids"* silently burned
paid rows.)

### `checks.py` — the code track

Thin wrapper over the production validators. Two entry points:

```
check_html(html: str) -> findings      # pure; works on ANY html, no run folder needed
check_run(run_id, stage) -> findings   # the run-folder wrapper
```

`check_html` taking a raw string is what makes "runs on every commit" real — today the
capability exists but only `check_run` is exposed on the CLI, so it can never run in CI.

### `score.py` — pure

```
aggregate(rows) -> {mean, median, stddev, n, distinct}
compare(run_a, run_b) -> {deltas, noise_band, verdict}
```

No I/O, no imports from this package, no model calls. This is where the logic whose silent
failure costs a whole run lives, and purity makes it testable in milliseconds.

**`compare` refuses to print a delta when either arm has fewer than 2 samples.** A tool that
lets you ask for a comparison it cannot support will keep producing confident nonsense.

### `report.py` — one `report.html` for the whole tree

Replaces `site/` (**4,299 lines**). This is the largest regrowth risk in the plan and the file
most likely to blow the budget — it ballooned once already.

**Hard constraints:**
- **One page**, `.runs/report.html`, over all runs. Not one per run (an earlier shape wrote
  `run.html` per run and was abandoned).
- **Self-contained**: inline CSS, inline SVG, no CDN, no framework, no build step.
- **Reads only stored JSON.** Never re-computes a score — imports `score.aggregate`.
- **A rendering failure is a warning, never an exception.** A `KeyError` in a renderer once
  took down an entire report and left a run folder disagreeing with itself.

**Content, in order:**
1. Runs table — newest first: run id, grade, per-stage score, completed/total, tokens, date.
2. Trend — one inline-SVG line per stage across runs.
3. Per-run drill-down — stage rows with judge score, checks score, completed/total.
4. Row detail — response excerpt, judge rationale, check findings.

Anything beyond those four sections is out of budget.

### `cli.py` — five commands

```
eval run <config> [--stage S] [--from RUN] [--repeats N]   # the only command that spends
eval score <run>                                            # re-judge stored responses (free)
eval checks <path|run>                                      # deterministic only (free, CI-able)
eval compare <a> <b>                                        # noise-guarded delta
eval report                                                 # rebuild .runs/report.html (free)
```

Five, not fifteen. Parsing and printing only — no logic.

## 5. Scoring: three facts, no synthesis

**Delete `blended_score` (`0.7 × judge + 0.3 × code`).** It produced the most misleading
output observed: build showed judge **91.05**, code **40.67**, effective **17.2**, headline
**F** — three different impressions of one stage, and the number people read (F) was mostly
*attrition*, not quality.

Report three unsynthesised facts:

```
build   judge 91.1 (n=2)   checks 40.7 (n=3)   completed 2/5
```

You see immediately that the judge number rests on two rows, that the checks disagree with it,
and that three rows never finished. The blend hid all three.

**Checks are the gate; the judge is advisory.** Checks are deterministic, free and CI-able.
The judge grades prose and is labelled noisy.

**No baselines, no verdicts, no consistency caps, no `REFUSED`.** Print the score, the spread,
and the noise verdict. A human decides.

**Precheck is a wrapper-shape check only** — does the output have the expected envelope and
sections? The regex forbidden-list produced three false failures out of roughly six
observations in a day, including failing a spec for the phrase "no lorem ipsum" *in a statement
of compliance*.

## 6. Deleted

| What | LOC | Why |
|---|---|---|
| `evals/model_graded/` | 2,033 | Frozen; spec 005 records it as dead |
| `evals/grading/site/` | 4,299 | Replaced by `report.py` (300) |
| `evals/hybrid/` | 2,481 | Integration testing — belongs in `tests/agents/`, not an eval CLI |
| `calibrate.py` | 478 | Calibration against an n that cannot support it |
| `prompt_advisor.py` + `prompt_edits.py` + `apply-advice`/`revert` | ~900 | See §7 |
| baselines / verdicts / caps in `scoring.py` | ~250 | §5 |
| `markdown_report.py` | 782 | Superseded by `report.py` |

## 7. The advisor: not in v1

The advisor proposed four edits for `prototype-build`; **all four belonged in
`agents/guardrails/html-prototype.md`, not `AGENT.md`** — because it reads the *composed*
prompt (`tool_availability + injects + guardrails + skills + hooks + constitution +
prompt_body`) while `apply-advice` could only edit the body. It could not apply a single real
edit.

If an advisor returns later it needs one thing this one lacks: **the file map** — which file
each block of the composed prompt came from. Without that, advice lands in a file the applier
cannot reach. Build the map first, the advisor second.

## 8. Migration sequence

| Phase | Work | Risk |
|---|---|---|
| **0** | Guard `score is None` in `model_grader._summary_stage_fields`. ~3 lines. Unblocks `--stage`/`--from`, cutting A/B cost ~60% and holding upstream constant | none |
| **1** | Commit the tree first. Then delete `model_graded/`, `site/`, `calibrate.py` (~6,800 LOC) | none — dead or replaced |
| **2** | Port `compare.py`, `check_html`, `artifacts` path discipline into the new layout | low — mechanical |
| **3** | Write `run.py`/`store.py`/`cli.py` around them; run both systems on one dataset and diff | medium |
| **4** | Write `report.py` to the §4 constraints | **highest regrowth risk** |
| **5** | Fold `hybrid/` scenarios into `tests/agents/`; delete the package | low |

**Phase 0 first, before any deletion.** Cheap runs are the only real fix for the noise
problem — you cannot shrink a ±2.73 band by reasoning about it, only by running more.

**Commit before Phase 1.** 65+ files were uncommitted across two concurrent sessions when this
was written; deleting 6,800 lines into that state is how work gets lost.

## 9. The ceiling

**One directory. Seven files. 1,500 lines. Five commands.**

The current system did not grow through bad decisions — every spec was individually
reasonable. It grew because **nothing capped the total**. Specs 008 and 009 landed while 007
was still being built.

Add a test that fails when the package exceeds its budget. A number nobody enforces is a wish.

## 10. Explicitly not built

Baselines · verdicts · consistency caps · `REFUSED` · a second or third package · the advisor ·
`apply-advice` · per-run HTML pages · `calibrate` · prompt versioning · a dashboard beyond the
four sections in §4.

Each of these was a reasonable idea. Together they cost 10.3M tokens to say *within-noise*.
