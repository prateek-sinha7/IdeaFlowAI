# Implementation Plan: Grading Calibration

**Spec**: `specs/008-grading-calibration/spec.md`
**Created**: 2026-07-30
**Status**: Planned

---

## Technical Context

| | |
|---|---|
| **Runtime** | Python 3.11 (`python3.11`, no venv — project convention) |
| **Package** | `backend/evals/grading/` — the model track (`model/`), the code track (`code/`), shared I/O (`artifacts.py`, `config.py`), reporting (`markdown_report.py`), CLI (`grade_runner.py`, `grade.sh`) |
| **Structured output** | Pydantic v2 over LangChain `with_structured_output(..., include_raw=True)` |
| **Judge** | Mistral `mistral-large-latest`, pinned per rubric via `judge.resolve_judge_model` |
| **Tests** | pytest, `backend/tests/unit/test_grading_*.py` (14 files) |
| **Entry point** | `./grade.sh <subcommand>` → `grade_runner.py` |
| **Deployment** | None — a developer tool. No service, no migration, no API surface. |

**Working constraint**: every live-judge invocation (`calibrate`, `rejudge`, `run`) is the
user's to execute. Phases 0–4 below are entirely offline and unit-testable; Phase 5 is the
single handoff point.

---

## Architecture Decisions

### AD-1 — Severity is priced, not counted *(spec C2)*

`CONSISTENCY_CAPS` is deleted. `judge.price_findings()` replaces `judge.consistency_cap()`:
`blocking` forces a 45 ceiling, each blocking-or-major costs 8 points, each minor costs 1
to a −4 floor.

*Rationale*: counting is the wrong operation. A step function over a count has cliffs at
arbitrary boundaries and never reads what the finding says — which is exactly how 11 of 15
golden dimensions were capped by cosmetic remarks. Pricing is monotonic; the one deliberate
cliff (`blocking`) encodes a categorical judgement, not a quantity.

### AD-2 — The code track bounds the judge, it does not merely average with it *(spec C1)*

`blended_score` gains `effective = min(0.7·judge + 0.3·code, code + 15)`.

*Rationale*: the originally-specified floor gate (`code < 40`) is unreachable in practice —
`prototype_build_validate.check` already hard-fails on `not static_check(...).ok` and the
rubric sets `skip_on_precheck_failure: true`, so every judged row is structurally clean. The
band binds across the whole range instead of at an end already guarded, and it is a strict
tightening: it can only ever lower a score, never raise one.

### AD-3 — The severity schema degrades, never crashes

`DimensionScore` gains `findings: list[Finding]`; a `mode="before"` validator lifts a legacy
`weaknesses: list[str]` into `[{severity: "major", detail: …}]`.

*Rationale*: this file's entire history is recovery from judges that answered in an
unexpected shape (`_lift_narrative`, `_join_evidence`). Losing a paid-for verdict over
schema strictness is the failure mode to design against. `major` is the strict-but-not-fatal
default: an untagged finding costs points but does not force a fail.

### AD-4 — Signatures stay stable so call sites are untouched

`blended_score(judge, code)` keeps its two-argument shape; the band is internal.
`_capped_sub_scores` keeps returning `(sub_scores, score_caps)`.

*Rationale*: `markdown_report.py:126`, `:579` and `compute_overall` all consume
`blended_score`; an internal change propagates for free and cannot leave one report path on
the old arithmetic.

### AD-5 — Calibration reads committed fixtures, not run folders *(spec C5)*

`grade.sh calibrate` grades `golden/*` and `golden/calibration/fail/*` from the checked-in
tree.

*Rationale*: `.runs/` is gitignored and disposable. The fixtures were extracted on
2026-07-30 for exactly this reason (spec §3.7); a calibration that depended on a scratch
folder would break the first time someone cleaned up.

### AD-6 — Baselines are re-pinned once, at the end, from real output

Every rubric edit changes `rubric_hash`, flipping all five baselines to `REFUSED`. That is
correct behaviour and is left in place until Phase 5 produces observed numbers.

*Rationale*: pinning to predicted numbers would defeat the purpose of the calibration run.
`REFUSED` between Phase 3 and Phase 5 is the system working.

---

## Delivery Strategy

Six phases. **0 is complete.** 1–4 are offline; 5 is the user's to run; 6 closes the loop.

### Phase 0 — Preserve the evidence ✅ **DONE**

Both ends of the scale extracted from gitignored `.runs/` into
`model/workflows/prototype/golden/calibration/`, `git check-ignore`-verified as tracked.

### Phase 1 — Severity in the judge schema *(offline)*

`Finding` model; `DimensionScore.findings`; legacy-shape validator; `JudgeVerdict.
dimension_findings`; `dimension_weaknesses` retained as a derived view so stored grades and
the report renderer keep working. `build_judge_prompt` asks for severities and drops the
self-contradictory "scores above 90 should be rare" / cap-announcement prose.

*Exit*: `test_grading_judge.py` covers each severity, the legacy-shape lift, and a mixed
reply. No behavioural change to scores yet.

### Phase 2 — Price the findings *(offline)*

`price_findings()` in; `consistency_cap()` / `CONSISTENCY_CAPS` out. `_capped_sub_scores`
records the per-severity breakdown and the triggering findings inside each `score_caps`
entry. The stale `89.5` citation in the module docstring block is corrected — it is not
reproducible from the run it names (spec §6) — and replaced with the reproducible
11-of-15 figure and a pointer to `golden/calibration/top/`.

*Exit*: table-driven tests over every severity combination, plus a **regression test that
replays `top/mission_control.verdict.json`** and asserts the new pricing lifts the five
stages from the capped column toward the reported column.

### Phase 3 — The ceiling band + honest defaults *(offline)*

`CODE_BAND = 15` in `blended_score`. `grade_run_folder`'s `render` / `interactions`
defaults flip `False` → `True`, so a caller that forgets the flags no longer silently grades
on static checks alone and inflates `code_score`.

*Exit*: boundary tests at the band edge; `test_grading_markdown_report.py` confirms
`compute_overall`, the phase table and the per-row table all move together.

### Phase 4 — Rubrics, prose, and the missing fixture *(offline)*

All five `*_rubric.yaml`: scoring-discipline prose aligned to severity, anchors re-read for
consistency. Author `golden/calibration/fail/hollow_console.html` — passes every precheck
and `static_check`, empty inside. Implement `run_calibration()` + the `calibrate`
subcommand in `grade_runner.py` / `grade.sh`.

*Exit*: `./grade.sh check` passes; `hollow_console.html` verified to pass precheck and score
~100 on the code track (that is the point of it); `calibrate` runs end-to-end against a
stubbed judge in tests.

### Phase 5 — Calibrate for real *(USER RUNS THIS)*

```bash
./backend/evals/grading/grade.sh calibrate
```

Live judge calls across the golden set and both fail fixtures. Produces the observed ceiling
and a paste-ready `baseline:` block.

### Phase 6 — Re-pin and record *(offline, after Phase 5)*

Re-pin all five `set_from` blocks with the new `rubric_hash` and re-derive
`min_average_score` (~20 below the observed golden ceiling). Re-freeze
`calibration/top/mission_control.verdict.json` under the new scale, in the same commit.
Update `golden/README.md` and `golden/report.md` with the corrected scores.

---

## File Changes

| File | Action | Purpose |
|---|---|---|
| `…/golden/calibration/README.md` | ✅ **added** | Documents the fixture store and the re-freeze rule |
| `…/golden/calibration/top/mission_control.verdict.json` | ✅ **added** | Frozen golden verdict: 94.51 reported → 85.15 recorded, 11/15 capped |
| `…/golden/calibration/fail/clinic_scheduler_broken.html` | ✅ **added** | Real broken output, `code_score` 0.0, 7 static issues |
| `…/golden/calibration/fail/clinic_scheduler_broken.verdict.json` | ✅ **added** | Its code score, issues, precheck result, SHA-256 |
| `model/judge.py` | modify | `Finding` + severity; `price_findings()` replaces `consistency_cap()`; prompt prose; correct the stale citation |
| `code/code_grader.py` | modify | `CODE_BAND` in `blended_score`; `render`/`interactions` default `True` |
| `markdown_report.py` | modify | Render findings with severity; show when the band bound a cell |
| `model/workflows/prototype/prototype_specify_rubric.yaml` | modify | Severity prose; re-pin baseline (Phase 6) |
| `…_plan_rubric.yaml` | modify | ditto |
| `…_analyze_rubric.yaml` | modify | ditto |
| `…_build_rubric.yaml` | modify | ditto |
| `…_validate_rubric.yaml` | modify | ditto |
| `…/golden/calibration/fail/hollow_console.html` | **add** | Passes every check, empty inside — the judgement-half fixture |
| `grade_runner.py` | modify | `run_calibration()` + `calibrate` argument parsing |
| `grade.sh` | modify | `calibrate` subcommand + help text (LIVE warning, like `rejudge`) |
| `tests/unit/test_grading_judge.py` | modify | Replace `test_consistency_caps_bind_scores_to_reported_weaknesses` (lines 502–508); add severity + legacy-shape + golden-replay tests |
| `tests/unit/test_grading_code_grader.py` | modify | Extend `test_blended_score_prefers_whichever_exists` (line 207) with band cases |
| `tests/unit/test_grading_markdown_report.py` | modify | Band propagation through `compute_overall` and both tables |
| `tests/unit/test_grading_runner.py` | modify | `calibrate` wiring against a stubbed judge |
| `…/golden/README.md` | modify | Point at `calibration/`; corrected scores (Phase 6) |
| `…/golden/report.md` | modify | Corrected scorecard (Phase 6) |

**Not touched**: `scoring.py` (weighting and baselines are sound), `precheck.py`,
`dispatch.py`, `artifacts.py`, `config.py`, the `PENALTIES` table, `CODE_WEIGHT`,
`GRADE_BANDS`.

---

## Risks & Mitigations

| Risk | L | I | Mitigation |
|---|---|---|---|
| All five baselines flip to `REFUSED` mid-work | **Certain** | High | Expected and correct. Phases 1–4 land with baselines refused; Phase 6 re-pins from Phase 5's observed output. Do not pin to predicted numbers. |
| Pricing majors instead of capping re-opens "90 with issues" | Medium | High | Two independent defences replace the cap: the `blocking` ceiling reads the judge's words, the band reads the browser. `hollow_console.html` is the fixture that asserts the case only the judge can catch. |
| Mistral does not reliably emit the severity enum | Medium | Medium | AD-3's legacy lift treats untagged findings as `major`; a run where >20% of dimensions fall back emits a summary warning so silent degradation is visible. |
| `min_average_score: 70` was calibrated on the capped scale | **Certain** | Medium | Re-derive in Phase 6 from `calibrate` output, ~20 below the observed ceiling. |
| Flipping `render`/`interactions` to `True` slows or breaks CI without Chromium | Low | Low | `_render_findings` / `_interaction_findings` already degrade to `available: false` and subtract nothing when the browser is absent. |
| `top/…verdict.json` drifts from the live rubric after a weight edit | Medium | Low | The fixture stores the `weights` it was scored under, so staleness is detectable; §3.7 states the re-freeze rule and Phase 6 executes it. |
| The stale `89.5` citation gets copied forward | Medium | Low | Phase 2 explicitly corrects it. It is not reproducible from `260730-012401-small` (both rows `precheck_passed: false`, no judge score). |
| `options.repeats` remains a silent no-op | **Certain** | Low | Deferred by decision (spec §8), recorded as a known lie. Must be built or deleted before anyone treats it as a variance control. |
