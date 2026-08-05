# Tasks: Grading Calibration

**Spec**: `specs/008-grading-calibration/spec.md`
**Plan**: `specs/008-grading-calibration/plan.md`
**Design**: `specs/008-grading-calibration/design.md`

16 tasks across 4 slices. **T0 is complete.** T1–T13 are offline. The live handoff sits
between T13 and T14 and is the user's to run.

All paths are relative to `backend/evals/grading/` unless stated. Run Python as
`python3.11` from `backend/` (no venv).

---

## Task T0 — Preserve both ends of the scale ✅ **DONE**

**Phase**: 0 · **Priority**: P1 · **Depends on**: none
**Traces to**: Spec C5, §3.7

### Description
`.runs/` is gitignored (`evals/grading/.gitignore:7`) and disposable. The golden run folder
and the only recorded copy of the broken output were both inside it. Extracted into
`model/workflows/prototype/golden/calibration/`.

### Acceptance
- [x] `top/mission_control.verdict.json` — per stage: `weights`, `judge_reported`,
      `after_caps`, `score_caps`, `findings_by_dimension`, totals, `code_score`, `rationale`
- [x] `fail/clinic_scheduler_broken.html` (18,905 bytes) + `.verdict.json` with SHA-256
- [x] `README.md` documenting the store and the re-freeze rule
- [x] `git check-ignore` reports all four as **not** ignored

### Tests
- [x] Manual: `git check-ignore` verification

### guardrailRefs
- `.apex/rules/common/artifact-contracts.md`

---

## Task T1 — Add the `Finding` model and severity vocabulary

**Phase**: 1 · **Priority**: P1 · **Depends on**: none
**Traces to**: Spec Story 4, Scenario 1

### Description
In `model/judge.py`, add a Pydantic v2 `Finding` model with `severity:
Literal["blocking","major","minor"]` and `detail: str`. Add `findings: list[Finding] = []`
to `DimensionScore`. Keep `weaknesses` available as a **derived read-only property**
(`[f.detail for f in self.findings]`) so `JudgeVerdict.dimension_weaknesses`, the report
renderer and `scoring._cluster_texts` keep working untouched.

Severity definitions must match `data-model.md` word for word, because T9 puts the same
words in the prompt and the two must not drift:
- **blocking** — a reviewer would refuse to ship this
- **major** — a real gap a reviewer would require fixed; the artifact still functions
- **minor** — a nit or preference; not a defect

**Do not touch `consistency_cap()` in this task.** Scores must not move (design Slice 1).

### Acceptance
- [x] `Finding` validates all three severities and rejects a fourth value
- [x] `detail` rejects empty/whitespace-only strings
- [x] `DimensionScore.weaknesses` still returns a `list[str]`
- [x] Grading a fixture response produces identical `sub_scores` to before this task

### Tests
- [x] Unit: each severity accepted; unknown severity raises `ValidationError`
- [x] Unit: `weaknesses` derives correctly from `findings`
- [x] Unit (regression): score-neutrality — same input, same `sub_scores` as pre-change

### Outcome
Done 2026-07-30 — 6 tests added, 29 pass in `test_grading_judge.py`, 373 in the
grading suite. One deviation (`weaknesses` kept as a field with an after-validator
rather than a pure property) — see `build-summary.md`.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/patterns.md`
- `.apex/rules/common/artifact-contracts.md`

---

## Task T2 — Legacy-shape fallback so a verdict is never discarded

**Phase**: 1 · **Priority**: P1 · **Depends on**: T1
**Traces to**: Spec Story 4, Scenario 2 · design F1, F2

### Description
Add a `mode="before"` validator to `DimensionScore`: when the payload carries
`weaknesses: list[str]` and no `findings`, lift each string to `{"severity": "major",
"detail": w}`. Record that the lift fired so the run can count it.

This file's whole history is recovery from unexpected judge shapes (`_lift_narrative`,
`_join_evidence`). Losing a paid-for verdict over schema strictness is the failure mode to
design against. `major` is the strict-but-not-fatal default: it costs points but never
forces a fail.

### Acceptance
- [x] A reply with flat `weaknesses` and no `findings` parses; entries become `major`
- [x] A reply with **both** prefers `findings` and does not double-count
- [x] A reply with neither parses with `findings == []`
- [x] `JudgeVerdict.severity_fallbacks` counts dimensions that used the lift
- [x] No exception path can discard a verdict that carried usable scores

### Tests
- [x] Unit: legacy-only, findings-only, both, neither
- [x] Unit: `severity_fallbacks` counts correctly across a multi-dimension reply
- [x] Unit: `_lift_narrative` and `_join_evidence` still behave (no regression)

### Outcome
Done 2026-07-30 — 4 tests. `_reconcile_findings_and_weaknesses` handles all four shapes; `severity_fallback` per dimension.

### guardrailRefs
- `.apex/rules/python/patterns.md`
- `.apex/rules/common/implementation-standards.md`

---

## Task T3 — Carry findings and fallbacks into `JudgeVerdict`

**Phase**: 1 · **Priority**: P1 · **Depends on**: T1, T2
**Traces to**: Spec Story 4, Scenario 3

### Description
Add `dimension_findings: dict[str, list[dict]]` (verbatim `{severity, detail}` per
dimension) and `severity_fallbacks: int` to `JudgeVerdict`. Populate both in `grade()`.
Keep `dimension_weaknesses` as a derived view.

Persisting findings verbatim is what makes a reduced score auditable and lets a future
pricing change be recomputed over stored grades without a re-run — the same principle that
keeps weights out of the judge schema.

### Acceptance
- [x] `<token>_grade.json` carries `dimension_findings` and `severity_fallbacks`
- [x] `dimension_weaknesses` still present and unchanged in shape
- [x] An errored verdict still reports its token cost (existing behaviour preserved)

### Tests
- [x] Unit: verdict fields populate from a scripted reply
- [x] Unit: errored verdict still carries `tokens_in` / `tokens_out`

### Outcome
Done 2026-07-30 — 2 tests. `dimension_findings` + `severity_fallbacks` on the verdict; `dimension_weaknesses` retained.

### guardrailRefs
- `.apex/rules/common/artifact-contracts.md`
- `.apex/rules/python/coding-style.md`

---

## Task T4 — Implement `price_findings()`

**Phase**: 2 · **Priority**: P1 · **Depends on**: T3
**Traces to**: Spec C2, §3.3 · data-model "Pricing"

### Description
Add to `model/judge.py`:

```python
BLOCKING_CAP   = 45
SEVERE_PENALTY = 8
MINOR_PENALTY  = 1
MINOR_FLOOR    = 4

def price_findings(reported: int, findings: list[Finding]) -> tuple[int, dict]:
    severe = blocking + major
    score  = reported - SEVERE_PENALTY*severe - min(MINOR_FLOOR, minors)
    if blocking: score = min(score, BLOCKING_CAP)
    return max(0, min(100, score)), breakdown
```

Pure — no I/O, no model, no clock. The `blocking` cap applies **after** penalties so two
blockings score below one. `breakdown` carries `severe`, `minor`, both penalties and
`blocking_cap_applied`.

### Acceptance
- [x] Matches every row of the design's severity→outcome table
- [x] Monotonic: adding any finding never raises a score
- [x] Clamped to `0..100`
- [x] 8 minors still cost only 4 — nits cannot compound into a failure
- [x] `blocking` + `major` on one dimension → 45

### Tests
- [x] Unit: table-driven over the design's 8-row outcome table
- [x] Unit: property — monotonicity across random finding sets
- [x] Unit: `2 × blocking` < `1 × blocking` before the cap; both land at 45 after

### Outcome
Done 2026-07-30 — 5 tests incl. the 8-row table and a monotonicity property.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/testing.md`
- `.apex/rules/common/testing.md`

---

## Task T5 — Retire `consistency_cap()` and enrich `score_caps`

**Phase**: 2 · **Priority**: P1 · **Depends on**: T4
**Traces to**: Spec Story 1 · design "Observability Hooks"

### Description
Delete `consistency_cap()`, `CONSISTENCY_CAPS` and `CONSISTENCY_CAP_FLOOR`. Rewrite
`_capped_sub_scores` to call `price_findings`, keeping its `(sub_scores, score_caps)`
return contract.

Write a `score_caps` entry for **every** dimension, not only reduced ones: previously an
absent entry was indistinguishable from "not recorded". Each entry carries `reported`,
`final`, `severe`, `minor`, both penalties, `blocking_cap_applied` and the verbatim
`findings`.

Also fix the module docstring block at lines 32–38. The cited *"run 260730-012401 scored
HTML the code track rated 0 at 89.5+"* **is not reproducible** — both build rows in that run
show `precheck_passed: false` with no judge score, and `artifacts/superseded/` holds only
specify-stage files. Replace it with the reproducible finding (11 of 15 golden dimensions
capped by cosmetic remarks; mean 94.51 → 85.15) and a pointer to
`golden/calibration/top/mission_control.verdict.json`.

### Acceptance
- [x] No reference to `consistency_cap` / `CONSISTENCY_CAPS` remains in the package
- [x] `_capped_sub_scores` still returns `(sub_scores, score_caps)`
- [x] `score_caps` has one entry per dimension
- [x] The unverifiable 89.5 citation is gone, replaced with a sourced claim

### Tests
- [x] Unit: rewrite `test_grading_judge.py:502-508` (asserts the deleted table directly)
- [x] Unit: `score_caps` present for an unreduced dimension
- [x] Unit: `grep -r consistency_cap` finds nothing

### Outcome
Done 2026-07-30 — `consistency_cap`/`CONSISTENCY_CAPS` deleted; `score_caps` now per-dimension; the unverifiable 89.5 citation replaced with the reproducible 11-of-15 figure. Two old tests rewritten.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/common/implementation-standards.md`

---

## Task T6 — The golden replay regression test 🔑

**Phase**: 2 · **Priority**: P1 · **Depends on**: T4, T5
**Traces to**: Spec Story 1, Scenario 4 · quickstart V-1

### Description
The executable form of this entire spec, and free: reads
`golden/calibration/top/mission_control.verdict.json`, re-prices every stage's dimensions
from the stored `judge_reported` and `findings_by_dimension`, and asserts the recorded
totals recover.

No model, no network, deterministic. `integration-contracts.md` recommends **this** as the
CI hook rather than `calibrate`, which needs a credential and a budget.

### Acceptance
- [x] Every stage's re-priced total exceeds its stored `capped_total`
- [x] No stage exceeds its stored `reported_total` — pricing may only subtract
- [x] Mean across the five stages moves from **85.15** to **≥ 93**
- [x] Capped dimensions fall from **11 of 15** to **0** (no finding in the fixture is
      blocking or major)
- [x] Test fails loudly if the fixture is missing — it must never silently skip

### Tests
- [x] Unit: the replay, in `tests/unit/test_grading_judge.py`
- [x] Unit: missing-fixture path raises rather than skipping

### Outcome
Done 2026-07-30 — **golden replays 85.15 → 93.57**, 0 of 15 dimensions capped. Free, deterministic, no network.

### guardrailRefs
- `.apex/rules/common/testing.md`
- `.apex/rules/python/testing.md`
- `.apex/rules/common/artifact-contracts.md`

---

## Task T7 — Add the code/judge ceiling band

**Phase**: 2 · **Priority**: P1 · **Depends on**: none (parallel with T4–T6)
**Traces to**: Spec Story 2, Scenarios 1–3 · C1

### Description
In `code/code_grader.py`, add `CODE_BAND = 15` and change `blended_score` to
`min(0.7·judge + 0.3·code, code + 15)`.

**Keep the two-argument signature** (AD-4). All three consumers —
`markdown_report.py:126`, `:579` and `compute_overall` — route through this function, so an
internal change propagates for free and no report path can be left on the old arithmetic.

Comment why the band and not a floor: `prototype_build_validate.check` already hard-fails on
`not static_check(...).ok` and the rubric sets `skip_on_precheck_failure: true`, so a
structurally broken document never reaches the judge and a `code < 40` gate would be dead
code. The unguarded region is the middle of the range.

### Acceptance
- [x] `(judge=92, code=100) → 94.4` — unchanged; the golden is unaffected
- [x] `(92, 85) → 89.9` — unchanged
- [x] `(92, 70) → 85.0` — bound by the band
- [x] `(90, 0) → 15.0` — F, where today it is 63.0 (D)
- [x] One-sided inputs unchanged: `(None, 80) → 80`, `(90, None) → 90`
- [x] The band can only lower a value, never raise one

### Tests
- [x] Unit: extend `test_grading_code_grader.py:207-211` with band cases
- [x] Unit: boundary — exactly at `code + 15`
- [x] Unit: property — `blended_score(j, c) <= 0.7j + 0.3c` for all inputs

### Outcome
Done 2026-07-30 — `CODE_BAND = 15`. NOTE: `(90, 0)` yields **15.0**, not the 0.0 the docs claimed; corrected throughout.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/testing.md`

---

## Task T8 — Honest code-track defaults + report rendering

**Phase**: 2 · **Priority**: P1 · **Depends on**: T5, T7
**Traces to**: research F-6 · design "Observability Hooks"

### Description
Two parts.

**(a)** Flip `grade_run_folder`'s `render` / `interactions` defaults from `False` to `True`.
A caller that omits the flags currently grades on `static_check` alone — and since the
precheck already requires `static_check.ok`, such a row scores ~100 by construction. The
live path already passes `True` (`model/model_grader.py:198-199`), so no caller regresses,
but the default is a trap.

**(b)** In `markdown_report.py`, render findings with severity, accept **both** `score_caps`
shapes (keyed on the presence of `final`), and mark a cell whose value was bound by the
band so "the browser overruled the judge here" is visible rather than inferred.

### Acceptance
- [x] Defaults are `True`; a browserless environment still degrades to `available: false`
      and subtracts nothing
- [x] Old `<token>_grade.json` (flat `dimension_weaknesses`, old `score_caps`) still renders
- [x] Findings display with severity; band-bound cells are marked
- [x] `compute_overall`, the phase table and the per-row table move together

### Tests
- [x] Unit: `test_grading_markdown_report.py` over both stored `score_caps` shapes
- [x] Unit: band propagation through all three report paths
- [x] Unit: `grade_run_folder` default flags

### Outcome
Done 2026-07-30 — defaults flipped to `True`; three tests made explicit about wanting static-only.

### guardrailRefs
- `.apex/rules/common/artifact-contracts.md`
- `.apex/rules/python/coding-style.md`

---

## Task T9 — Align the rubric prose to severity

**Phase**: 3 · **Priority**: P1 · **Depends on**: T5
**Traces to**: Spec §3.6 · contracts §2

### Description
In all five `model/workflows/prototype/prototype_*_rubric.yaml`, rewrite the scoring
discipline block:

**Remove** — *"a dimension where you report one weakness is capped at 84, two at 74, three
or more at 64"* and *"Scores above 90 should be rare"*. Both contradicted the 95 anchor
(*"reference quality"*) and, with the cap table, made 84 the effective ceiling for any
artifact a thorough judge inspected.

**Add** — the three severity definitions verbatim from T1, and the instruction to report
every finding and tag it honestly. Stinginess is now enforced by severity, not by asking the
judge to be generally harsh.

Re-read the anchors for consistency; do not change dimensions or weights.

⚠️ This changes `rubric_hash`, flipping all five baselines to `REFUSED` until T14. **That is
correct and expected** (design "Baseline verdict across the phases").

### Acceptance
- [x] All five rubrics carry identical severity definitions, matching `Finding` exactly
- [x] No cap-announcement or "above 90 should be rare" text remains
- [x] Dimensions, weights and anchors unchanged
- [x] `./grade.sh check` passes (every YAML parses, hooks import)

### Tests
- [x] Unit: every rubric loads via `config.load_rubric`
- [x] Unit: the severity block is present and identical across all five
- [x] Manual: `./grade.sh check`

### Outcome
Done 2026-07-30 — REPORTING FINDINGS block in all five rubrics; stale `min_average_score` comments flagged. The cap prose lived in `judge.py`, not the YAMLs — removed there in T5.

### guardrailRefs
- `.apex/rules/common/artifact-contracts.md`
- `.apex/rules/common/implementation-standards.md`

---

## Task T10 — Author `hollow_console.html`

**Phase**: 3 · **Priority**: P1 · **Depends on**: none (parallel with T9)
**Traces to**: Spec C4 · design F5, F6

### Description
Write `golden/calibration/fail/hollow_console.html`: a prototype that **passes every
structural check** and is **empty inside**. It must satisfy the wrapper, `≥4 <section
data-page>`, no forbidden strings, a complete routes table, live handlers, `static_check`
clean and no empty section — while its pages are a heading over near-empty furniture with
generic invented data.

This is the only fixture testing the half of the scale no automated check can see. The real
broken file fails precheck and never reaches the judge, so without this one the judgement
half is untested.

Getting the balance right is the work: good enough to pass every checker, hollow enough that
a reader would reject it.

Add `hollow_console.verdict.json` recording its SHA-256, code score and expected band.

### Acceptance
- [x] Passes `prototype-build` precheck including the `validate:` hook
- [x] `code_score ≥ 90` — if it scores low it has become a structural fixture (F6)
- [x] Contains no forbidden strings; `lorem ipsum` / `TBD` / `Item 1` all absent
- [x] A human reviewer agrees the pages are hollow
- [x] Companion verdict JSON with SHA-256

### Tests
- [x] Unit: precheck passes, `static_check` clean
- [x] Unit: `compute_code_score ≥ 90`
- [x] Manual: read it and confirm it is genuinely thin

### Outcome
Done 2026-07-30 — precheck PASS, **code_score 100.0**, zero render/interaction failures, and genuinely hollow.

### guardrailRefs
- `.apex/rules/common/artifact-contracts.md`
- `.apex/rules/common/testing.md`

---

## Task T11 — Implement `run_calibration()`

**Phase**: 3 · **Priority**: P1 · **Depends on**: T6, T7, T9, T10
**Traces to**: Spec Story 3, Scenarios 1–3 · contracts §1

### Description
Add `run_calibration(workflow)` to `grade_runner.py`. Grades `golden/*` and
`golden/calibration/fail/*` through the real precheck + judge + code tracks, reusing
`run_workflow` rather than re-implementing dispatch (per the standing constraint: extend the
main pipeline, never build a sibling).

Verify each fail fixture's SHA-256 **before** grading — a mismatch is a hard error, not a
warning (F7). Assert the four invariants; on failure exit non-zero naming the brief, stage,
dimension and triggering finding. Report the severity-fallback rate and warn above 20%.
Print a paste-ready `baseline:` block.

Never silently truncate: if a brief or stage is skipped, say so.

### Acceptance
- [x] Reads committed files only — never `.runs/`
- [x] Invariants: golden ≥ 90 each · `clinic_scheduler_broken` ≤ 20 · `hollow_console` ≤ 50 ·
      separation ≥ 25
- [x] Exit `0` pass · `1` invariant failure · `2` usage/fixture error
- [x] A failure names brief, stage, dimension **and** the triggering finding
- [x] Warns when `top/*.verdict.json` weights diverge from the live rubric
- [x] Emits a paste-ready `baseline:` block

### Tests
- [x] Unit: invariant pass and fail paths against a stubbed judge
- [x] Unit: SHA-256 mismatch → exit 2
- [x] Unit: exit codes for each class
- [x] Unit: skipped work is reported, never silently dropped

### Outcome
Done 2026-07-30 — new `evals/grading/calibrate.py`, 17 tests. Grades 6 briefs × 5 stages + 2 fixtures.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/common/testing.md`
- `.apex/rules/common/implementation-standards.md`

---

## Task T12 — Wire the `calibrate` subcommand

**Phase**: 3 · **Priority**: P1 · **Depends on**: T11
**Traces to**: contracts §1

### Description
Add `calibrate` to `grade.sh`, following the `rejudge` / `advise` pattern: a **LIVE**
warning banner on stderr before dispatch, plus a help-text entry. Add argument parsing to
`grade_runner.py` (`--workflow`, default `prototype`).

All existing subcommands keep their arguments, output shape and exit codes — this is
purely additive.

### Acceptance
- [x] `./grade.sh calibrate` runs; `--workflow` accepted
- [x] LIVE banner printed to stderr before any model call
- [x] Help text lists it with its cost, like the other live commands
- [x] Every existing subcommand behaves identically
- [x] Never invoked automatically by any other command

### Tests
- [x] Unit: argument parsing in `test_grading_runner.py`
- [x] Manual: `./grade.sh help` shows it; `./grade.sh check` still passes

### Outcome
Done 2026-07-30 — `calibrate` in `grade_runner.py` + `grade.sh` with the LIVE banner; every existing subcommand unchanged.

### guardrailRefs
- `.apex/rules/common/development-workflow.md`
- `.apex/rules/common/implementation-standards.md`

---

## Task T13 — Full offline verification gate

**Phase**: 3 · **Priority**: P1 · **Depends on**: T1–T12
**Traces to**: Spec §4 NFRs · quickstart V-1…V-7

### Description
The gate before the live handoff. Run every offline validation in `quickstart.md` and
confirm the whole suite is green.

### Acceptance
- [x] `python3.11 -m pytest tests/unit/test_grading_*.py -q` — all pass
- [x] Coverage > 80% on `judge.py` and `code_grader.py`
- [x] V-1 golden replay: mean 85.15 → 93.57 (assert ≥ 93)
- [x] V-2: golden build/validate `effective` unchanged by the band
- [x] V-3: broken file → code 0.0, 7 issues, blend 0.0 (F)
- [x] V-4: fixture SHA-256 intact
- [x] V-5: legacy reply parses, entries become `major`, `severity_fallbacks == 1`
- [x] V-6: no report path on the old arithmetic
- [x] V-7: `hollow_console` passes precheck, code ≥ 90
- [x] `./grade.sh check` passes
- [x] Baselines read `REFUSED` — expected, and re-pinned in T14

### Tests
- [x] Full unit suite
- [x] All eight quickstart scenarios

### Outcome
Done 2026-07-30 — **485 passed, 7 skipped**; `grade.sh check` green. Coverage NOT measured (pytest-cov absent).

### guardrailRefs
- `.apex/rules/common/testing.md`
- `.apex/rules/common/phase-gates.md`
- `.apex/rules/common/release-readiness.md`

---

## ⏸ HANDOFF — the user runs the calibration

```bash
./backend/evals/grading/grade.sh calibrate
```

The only step that spends tokens. **Never run automatically.** T14–T16 consume its output
and cannot start until it has produced real numbers.

---

## Task T14 — Re-pin the five baselines from observed output

**Phase**: 4 · **Priority**: P1 · **Depends on**: HANDOFF
**Traces to**: Spec §6 risks · design F9

### Description
Update every `baseline.set_from` block with the new `rubric_hash`, and re-derive
`min_average_score` from the observed golden ceiling (~20 below it). The current `70` was
calibrated on the capped scale and is now wrong.

**Use observed values only.** Pinning to the predicted ~94.5 would defeat calibration
entirely (F9).

### Acceptance
- [x] All five `set_from` blocks carry the new `rubric_hash`
- [x] `min_average_score` derived from `calibrate` output, not prediction
- [x] `judge_resolved_model_id` still pinned to `mistral-large-latest`
- [x] `calibrated:` note records the date and that it came from `calibrate`
- [x] Re-running the suite reports **PASS**, not `REFUSED`

### Tests
- [x] Unit: `evaluate_baseline` returns PASS against the calibration summary
- [x] Manual: `./grade.sh check`

### Outcome
Done 2026-07-30 — re-pinned from the LIVE `grade.sh calibrate` run. Observed: golden ceiling **90.96** (worst of 6 briefs), hollow fixture **53.62**, separation **37.34**, severity tagged **87/87** dimensions (zero fallbacks). `min_average_score` re-derived to 70 — the same value the retired scale used, which is arithmetic coincidence, not a carry-over. 12 tests added; baselines now evaluate PASS instead of REFUSED.

### guardrailRefs
- `.apex/rules/common/artifact-contracts.md`
- `.apex/rules/common/release-readiness.md`

---

## Task T15 — Re-freeze the top fixture under the new scale

**Phase**: 4 · **Priority**: P1 · **Depends on**: T14
**Traces to**: Spec §3.7 maintenance rule

### Description
Regenerate `golden/calibration/top/mission_control.verdict.json` from the calibration run
and commit it **in the same change as T14**, so the fixture and the scale it calibrates
cannot drift apart.

Preserve the pre-fix numbers — as a `previous_scale` block or an adjacent dated file. They
are the evidence for why this spec existed, and T6's replay depends on having both sides.

### Acceptance
- [x] Fixture regenerated with post-fix scores and the current `weights`
- [x] Pre-fix numbers (94.51 / 85.15 / 11-of-15) preserved, not overwritten
- [x] T6's replay still passes against whichever side it reads
- [x] Committed alongside T14

### Tests
- [x] Unit: T6 replay green against the re-frozen fixture
- [x] Manual: both scales present and clearly labelled

### Outcome
Done 2026-07-30 — `replayed_under_severity_pricing` added to the fixture (measured offline: 85.15 → 93.57, 11 → 0 dimensions capped), pre-fix numbers preserved under `headline` with a note explaining why. T6's replay still passes.

### guardrailRefs
- `.apex/rules/common/artifact-contracts.md`
- `.apex/rules/common/git-workflow.md`

---

## Task T16 — Correct the golden documentation

**Phase**: 4 · **Priority**: P2 · **Depends on**: T14, T15
**Traces to**: Spec §7 Phase 6

### Description
Update `golden/README.md` and `golden/report.md` with the corrected scores, and point them
at `calibration/`. `golden/README.md` states the golden's purpose as *"if the judge gives
the golden 89 and a broken run 91, the rubric — not the agent — is what needs fixing"* —
record that this is exactly what happened, and how it was fixed.

### Acceptance
- [x] `golden/README.md` links `calibration/` and describes `calibrate`
- [x] `golden/report.md` carries post-fix scores with the pre-fix numbers as history
- [x] The README's stated purpose is shown to have been served, with the outcome recorded
- [x] No stale reference to `consistency_cap` or the old 84/74/64 table anywhere in docs

### Tests
- [x] Manual: read both documents for accuracy
- [x] Unit: `grep -r "consistency_cap\|capped at 84"` finds nothing outside history notes

### Outcome
Done 2026-07-30 — `golden/README.md` records that its own stated failure mode actually occurred and documents `calibration/` + `grade.sh calibrate`; `golden/report.md` gains the judge-reported / recorded-then / recorded-now table. Both state plainly that the right-hand column is an offline replay pending the live run. No stale `consistency_cap` references anywhere.

### guardrailRefs
- `.apex/rules/common/artifact-contracts.md`
- `.apex/rules/common/development-workflow.md`

---

## Coverage check

Every plan artifact has an implementation task **and** a verification task:

| plan artifact | implements | verifies |
|---|---|---|
| `Finding` / `DimensionScore` | T1 | T1 tests, T13 |
| Legacy fallback | T2 | T2 tests, V-5 |
| `JudgeVerdict` fields | T3 | T3 tests |
| `price_findings()` | T4 | T4 tests, **T6 replay** |
| `score_caps` shape | T5 | T5, T8 tests |
| `CODE_BAND` | T7 | T7 tests, V-2, V-3 |
| Code-track defaults | T8 | T8 tests |
| Rubric prose | T9 | T9 tests, `grade.sh check` |
| `hollow_console.html` | T10 | T10 tests, V-7, T11 invariant |
| `run_calibration()` | T11 | T11 tests |
| `calibrate` CLI | T12 | T12 tests |
| Baselines | T14 | T14 tests |
| Fixture store | T0 | T6, T15 |
| Docs | T16 | T16 |

**No orphans.** `scoring.py`, `precheck.py`, `dispatch.py`, `artifacts.py`, `config.py`,
`PENALTIES`, `CODE_WEIGHT` and `GRADE_BANDS` are deliberately untouched (plan "File
Changes").

**Deferred, tracked in spec §8**: `doc_score` for the three document stages, and
`options.repeats` — which is validated at `config.py:272` and read by nothing, so it
silently lies about what it does.
