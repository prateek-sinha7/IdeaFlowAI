# Build Summary — 008-grading-calibration

Implementation handoff. One entry per `/apex:implement` run, newest last.

---

## Run 1 — 2026-07-30 · T1 (Slice 1)

### Tasks completed
- **T1** — Add the `Finding` model and severity vocabulary

### Files changed

| file | change |
|---|---|
| `backend/evals/grading/model/judge.py` | Added `Severity` Literal, `SEVERITY_GUIDANCE`, the `Finding` model, `DimensionScore.findings`, an after-validator mirroring findings into `weaknesses`, and the severity block in `build_judge_prompt` |
| `backend/tests/unit/test_grading_judge.py` | +6 tests under a `T1` section header |

### Tests added

| test | asserts |
|---|---|
| `test_finding_accepts_the_three_severities` | closed vocabulary — a fourth value raises |
| `test_finding_rejects_an_empty_detail` | `""`, `"   "`, `"\n\t "` all rejected |
| `test_findings_populate_weaknesses_so_every_existing_reader_keeps_working` | `weaknesses` stays `list[str]`, derived in order |
| `test_explicit_weaknesses_are_not_overwritten_by_the_sync` | an explicit list is never clobbered |
| `test_findings_do_not_change_any_score` | **the slice's guard** — findings and equivalent weakness strings price identically (both → 74) |
| `test_judge_prompt_defines_every_severity` | the prompt contains `SEVERITY_GUIDANCE` verbatim, so schema and prose cannot drift |

### Commands run

```bash
cd backend
python3.11 -m pytest tests/unit/test_grading_judge.py -q     # 29 passed
python3.11 -m pytest tests/unit/test_grading_*.py -q         # 373 passed, 7 skipped
```

TDD order was honoured: the six tests were written and observed failing
(`AttributeError: module ... has no attribute 'Finding'`) before any production code
was written.

### Deviation from plan/design

**`weaknesses` kept as a real field with an after-validator, not replaced by a
read-only property.**

`tasks.md` T1 and `data-model.md` both describe removing `weaknesses` from the schema
and deriving it. Doing that in T1 would have broken the task's own score-neutrality
requirement:

- Removing the field stops the judge being *asked* for `weaknesses`.
- The reverse lift (`weaknesses` → `findings`) is **T2**, so until it exists a judge
  answering in the old shape would yield `findings == []` → `weaknesses == []` →
  `consistency_cap(0) == 100`, i.e. every old-shape reply silently scoring higher.

Implemented instead: `findings` added alongside `weaknesses`, with a `mode="after"`
validator populating `weaknesses` from `findings` when only findings were sent, and
never overwriting an explicit list. Both shapes now produce identical scores, which is
exactly what T1 asked for. T2 adds the reverse direction plus `severity_fallbacks`;
T5 switches pricing to read `findings` directly, at which point `weaknesses` can
become fully derived.

**Also in scope, per design Slice 1, not spelled out in T1's description**: the
severity ask was added to `build_judge_prompt`. Without it the judge is never told the
new field exists. The *removal* of the cap-announcement prose (`"capped at 84…"`,
`"Scores above 90 should be rare"`) is deliberately **not** done here — it belongs with
T5/T9, once the caps it describes are actually gone.

### Blockers

None.

### Follow-ups

1. **Pre-existing test failure, unrelated to this work.**
   `tests/unit/test_grading_prompt_advice_json.py` — 3 failures. The file is
   **untracked** (`git status` → `??`), never committed, and fails on a filename
   convention mismatch: it expects `prompt_advice_prototype-build.md` (hyphen) while
   `prompt_advisor` writes `prompt_advice_prototype_build.md` (underscore, the agent
   *token*). Nothing to do with 008. Not fixed — out of scope for T1. Worth either
   fixing or deleting before it is mistaken for a regression from this spec.

2. **`judge.py` prompt still announces the caps.** Intentional until T5/T9, but it now
   sits a few lines below the new severity guidance and briefly contradicts it. Do not
   leave that state past Slice 2.

3. **Pyright reports `Import "pydantic" could not be resolved`** in the editor. Pre-existing
   — the LSP has no interpreter configured for this project's no-venv convention. Tests
   run fine under `python3.11`.

### Next task

**T2** — Legacy-shape fallback so a verdict is never discarded (`weaknesses` →
`findings` as `major`, plus the `severity_fallbacks` counter).

---

## Run 2 — 2026-07-30 · T2–T13 (Slices 1–3 complete)

Everything offline is done. The only remaining work is the live handoff
(`./grade.sh calibrate`) and the three tasks that consume its output.

### Tasks completed
**T2, T3** (Slice 1) · **T4, T5, T6, T7, T8** (Slice 2) · **T9, T10, T11, T12, T13** (Slice 3)

### The headline

The golden replays from **85.15 → 93.57**, with **0 of 15** dimensions capped
(was 11 of 15). Per stage, measured — not predicted:

| stage | was | now | judge actually said |
|---|---|---|---|
| prototype-specify | 84.40 | **93.40** | 94.40 |
| prototype-plan | 84.40 | **90.60** | 91.60 |
| prototype-analyze | 88.00 | **96.70** | 97.45 |
| prototype-build | 80.00 | **93.15** | 94.55 |
| prototype-validate | 88.95 | **94.00** | 94.55 |
| **mean** | **85.15** | **93.57** | 94.51 |

Every stage sits just below what the judge itself reported — shaded only by the
minor findings it raised, which is the intended behaviour.

### Files changed

| file | change |
|---|---|
| `evals/grading/model/judge.py` | `_reconcile_findings_and_weaknesses` (both directions); `dimension_findings` + `severity_fallbacks` on `JudgeVerdict`; `price_findings()` replacing `consistency_cap()`; `score_caps` per dimension; cap-announcement prose removed from `build_judge_prompt`; the unverifiable `89.5` citation replaced |
| `evals/grading/code/code_grader.py` | `CODE_BAND = 15` inside `blended_score`; `render`/`interactions` defaults `False` → `True` |
| `evals/grading/calibrate.py` | **new** — the whole calibration command |
| `evals/grading/grade_runner.py` | `calibrate` subparser + dispatch + import |
| `evals/grading/grade.sh` | `calibrate` case with a LIVE banner, plus help text |
| `…/prototype_{specify,plan,analyze,build,validate}_rubric.yaml` | REPORTING FINDINGS block; stale-baseline comment flagged |
| `…/golden/calibration/fail/hollow_console.html` + `.verdict.json` | **new** — the judgement-half fixture |
| `tests/unit/test_grading_judge.py` | +22 tests; 2 rewritten; `_FakeDimension` mirrors the real reconciliation |
| `tests/unit/test_grading_code_grader.py` | +5 tests; 3 made explicit about static-only |
| `tests/unit/test_grading_calibrate.py` | **new** — 17 tests |

### Commands run

```bash
python3.11 -m pytest tests/unit/test_grading_*.py -q   # 485 passed, 7 skipped
./evals/grading/grade.sh check                          # green
./evals/grading/grade.sh help                           # calibrate listed
```

TDD held throughout: every batch of tests was written and observed failing before
the production change.

### Corrections to the planning documents

1. **`blended_score(90, 0)` is 15.0, not 0.0.** `min(63, 0+15) = 15`. The spec,
   design, clarifications and quickstart all tabulated 0.0 — my arithmetic error,
   now corrected in all four. The *claim* is unaffected (15 is an F where 63 was a
   D), but the number was wrong.
2. **The golden recovery is 93.57, not "~94.5".** Predicted figures replaced with
   measured ones throughout.
3. **`hollow_console`'s band moved 50 → 55**, with the arithmetic recorded in its
   verdict JSON. With `CODE_WEIGHT = 0.3` and a clean code track, a structurally
   perfect document has an **arithmetic floor of 30**, so an overall ≤ 50 would
   demand a judge sub-score below 28.6. The build rubric's own `30` anchor — *"data
   interchangeable with any other industry, most pages a heading over a near-empty
   shell"* — describes this file exactly, and `0.7·30 + 30 = 51`. A band of 50
   would have failed a correctly-anchored judge.

### Deviations from plan/design

1. **`calibrate` does not reuse `run_workflow`.** The plan said to. It cannot:
   `run_workflow` dispatches an agent, and calibration grades documents that
   already exist on disk. There is no `golden` provider in `dispatch.py` — the
   `provider: golden` label in the old `golden-mission-control` run config was
   one I wrote by hand when populating that folder, not a real code path. What
   *is* reused is everything downstream of dispatch: the same rubric loader,
   precheck (generic gate + `validate:` hook), judge and code track.
2. **The cap prose was in `judge.py`, not the rubric YAMLs.** Spec §3.6 located
   it in `*_rubric.yaml`. `build_judge_prompt` is where it actually lived, so T5
   removed it there; T9 added the severity vocabulary to the five rubrics so a
   judge reading either surface sees the same words.
3. **`grade_document` runs the code checks via `asyncio.to_thread`.** The render
   and interaction sweeps call `asyncio.run` internally, which raises inside a
   running loop. Not a design change — a necessary detail the plan did not cover.
4. **`code_score_fn` is injectable.** The end-to-end calibration tests would
   otherwise drive Chromium across twelve HTML stages and take minutes. The real
   browser path is still exercised for real, on one document, in
   `test_the_hollow_fixture_passes_every_automated_check`.

### Blockers

None.

### Follow-ups

1. **Baselines now read `REFUSED`.** T9 changed `rubric_hash` on all five rubrics.
   Expected and correct (design "Baseline verdict across the phases"); T14 re-pins
   from the calibration output. Do not pin to predicted numbers.
2. **Coverage was not measured** — `pytest-cov` is not installed in this
   environment, so T13's ">80% on changed modules" is unverified. The suite is
   green; the coverage figure specifically is unproven.
3. **`tests/unit/test_grading_prompt_advice_json.py` now passes** (13/13, three
   consecutive runs). It failed 3/13 earlier in this session on a hyphen vs
   underscore filename assertion. I did not change it or `prompt_advisor.py`, and
   I cannot account for the change — worth a look before trusting it, and it is
   still untracked in git.
4. **The separation invariant is currently redundant.** With the golden floor at
   90 and the hollow band at 55, a 35-point gap is already implied by the
   per-fixture checks. It is kept because it is the only invariant that still
   binds if either band is loosened. Noted in the test that covers it.
5. **`options.repeats` remains a silent no-op** — deferred by decision (spec §8).

### Next step

**The live handoff — yours to run:**

```bash
./backend/evals/grading/grade.sh calibrate
```

Then T14 (re-pin baselines from its output), T15 (re-freeze the top fixture),
T16 (correct the golden docs).

---

## Run 3 — 2026-07-30 · T14, T15, T16 — **all 16 tasks complete**

### Tasks completed
**T15, T16** (offline) · **T14** (after the live calibration run)

### The live calibration result

Run with the user's explicit one-time authorization, overriding their standing
"never run live evals yourself" rule and the spec's own HANDOFF decision.

```
  fixture                   kind       overall   stages
  clinic_scheduler          golden       91.12   89 87 91 96 93
  expense_approvals         golden       91.98   94 89 89 96 93
  fleet_dispatch            golden       92.01   89   ? 93   ? 94
  mission_control           golden       92.48   95 85 91 94 97
  property_ops              golden       91.21   89 85 93 94 95
  shelter_ops               golden       90.96   89 88 86 96 96
  clinic_scheduler_broken   fail          0.00   0
  hollow_console            fail         53.62   54

  golden ceiling   90.96 (worst brief) · threshold >= 90.0
  separation       37.34 · threshold >= 25.0
  severity tagged  87/87 dimensions
```

**Every golden brief cleared 90. Separation 37.34. Zero severity fallbacks** —
the judge tagged all 87 dimensions itself; none defaulted to `major`.

The run exits 1 on two ungradable `fleet_dispatch` stages (a persistent
dimension-shape failure and a 429 after three attempts each). Those are judge
infrastructure, not the scale: every invariant about the scale itself passed.

### Two things the live run proved that the offline replay could not

1. **Judge scores are ~2 points lower live than the replay predicted** (golden
   mean ≈ 91.6 vs the replay's 93.57). Research U-2 predicted exactly this
   uncertainty: the old prompt *told* the judge caps existed, and removing that
   text changes how it scores. This is why baselines had to be pinned from a live
   run — the replay isolates the scale change but cannot capture judge behaviour
   under the new prompt.
2. **The `hollow_console` band correction was load-bearing.** It scored **53.62**.
   Against the original band of 50 the calibration would have failed on a
   correctly-behaving judge; against the corrected 55 it passes with little room
   to spare. The arithmetic reasoning recorded in its verdict JSON (a clean code
   track puts a floor of 30 under any structurally sound document) was right.

### Files changed

| file | change |
|---|---|
| `…/golden/calibration/top/mission_control.verdict.json` | `replayed_under_severity_pricing` block; `headline` annotated as the deliberate pre-fix record |
| `…/golden/README.md` | Records that its own stated failure mode occurred; documents `calibration/` and `grade.sh calibrate` |
| `…/golden/report.md` | judge-reported / recorded-then / recorded-now table |
| `…/prototype_*_rubric.yaml` (×5) | `rubric_hash` re-pinned; `calibrated:` records the run and its observed numbers; STALE flags replaced |
| `evals/grading/calibrate.py` | `_judge_with_retry`; ungradable stages recorded not raised; excluded from the mean rather than zeroed |
| `tests/unit/test_grading_judge.py` | +12 tests (baseline pinning, provenance, PASS-not-REFUSED, floor headroom); 1 rewritten |
| `tests/unit/test_grading_calibrate.py` | +3 tests for the retry / record-and-continue behaviour; 1 replaced |

### Commands run

```bash
./backend/evals/grading/grade.sh calibrate       # LIVE, twice — see below
python3.11 -m pytest tests/unit/test_grading_*.py -q   # 532 passed, 7 skipped, 2 failed
./evals/grading/grade.sh check                    # clean
```

### A bug the live run found in my own code

The **first** calibration run made real judge calls and then **aborted on its
third**, because `mistral-large` returned 2 of 3 dimensions for
`prototype-analyze` and I had written `grade_document` to raise on any judge
error. It discarded every verdict already paid for and produced no result.

Wrong trade for a ~32-call sweep, and contrary to a principle this package
applies everywhere else (`_lift_narrative`, `_join_evidence`, the rate-limit
retry — all built so a paid-for verdict is never thrown away). Fixed:

- `_judge_with_retry` — a bad *shape* is retried twice; nondeterminism costs one
  call, surrendering to it cost the run.
- A persistent failure is **recorded and the sweep continues**; the stage shows
  `?` and `check_invariants` fails the run at the end naming it.
- An ungradable stage is **excluded from the golden's mean, not scored zero** — a
  judge outage says nothing about the artifact.

That hardening is why the second run produced a complete table despite two
stages failing, instead of nothing.

### Blockers

None.

### Follow-ups

1. **Two test failures that are NOT from this work.**
   `test_grading_config.py::test_small_dataset_is_two_interaction_briefs` and
   `::test_small_dataset_says_its_scores_are_not_comparable`. Someone added a
   third row (`warehouse_slotting`) to `datasets/prototype_small.json` at
   20:10 today, outside this session — the file is `AM` in git and the suite was
   green at 485 passed before it changed. Either the dataset change or the two
   assertions needs updating; both are the author's call, not mine, so I left
   them alone.
2. **Re-run `calibrate` when convenient.** It exits 1 on the two ungradable
   `fleet_dispatch` stages (429 + shape failure). Nothing about the scale is in
   doubt, but a fully green run is worth having on record — and with the retry
   hardening in place a re-run should now clear them.
3. **The golden ceiling is 90.96, tighter than the ~93.6 replay suggested.**
   `shelter_ops` is the worst brief at 90.96, less than a point above the floor
   that fails it. Worth watching: one bad judge draw on that brief would fail a
   calibration for reasons unrelated to any code change.
4. **Coverage still unmeasured** — `pytest-cov` is not installed.
5. **`options.repeats` remains a no-op** — deferred by decision (spec §8). Given
   finding 3, implementing it (median of N) would directly reduce the risk of a
   single bad draw failing calibration.
