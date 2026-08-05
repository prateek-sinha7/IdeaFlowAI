# Research Notes: Grading Calibration

Investigation performed 2026-07-30 against the live tree and the run folders under
`backend/evals/grading/.runs/prototype/`. Every number below was read from a file, not
estimated.

---

## Decision Log

### D-1 — How should the deterministic code score constrain the judge?

**Options**
- **A** — ceiling band: `effective ≤ code + 15`
- **B** — floor gate: bound the cell only when `code_score < 40`
- **C** — both

**Chosen: A.**

**Rationale.** B was the original proposal and investigation killed it. The precheck's
`validate:` hook (`prototype_build_validate.py:check`) calls production's `static_check` and
returns `False` on `not result.ok`; the rubric sets `judge.skip_on_precheck_failure: true`.
So **a structurally broken document never reaches the judge**, and every judged row starts
from a `code_score` of 100 minus only `static_warning` (−3 each) and render/interaction
penalties. Reaching below 40 would need six independent render failures on a structurally
clean page.

Confirmed empirically on `260730-012401-small`: the `code_score 0.0` row has
`precheck_passed: false` and `judged: false`. The floor would have been dead code.

The unguarded region is the middle: three dead navs (code 70) plus a judge score of 92
blends to 85.4 today — a B for a page whose navigation is a third broken. The band binds
there. It is also a strict tightening (`min` of the two), so it can only lower a score.

---

### D-2 — How much should a `major` finding cost?

**Options**
- **A** — lenient caps 88 / 78 / 68
- **B** — strict caps 84 / 72 / 60
- **C** — no cap on majors; price them linearly

**Chosen: C** — `blocking` caps at 45; `−8` per blocking-or-major; `−1` per minor to a
`−4` floor.

**Rationale.** A and B both preserve the defect in milder form: a step function over a
*count*, with cliffs at boundaries, that never reads what the finding says. The original
`CONSISTENCY_CAPS` was not wrong in its numbers — it was wrong in its operation. Pricing is
monotonic and explainable; the single `blocking` cliff is deliberate, because "a reviewer
would refuse to ship this" is categorical rather than quantitative.

Blocking findings are also counted as severe, so two blockings score below one.

---

### D-3 — Scope for this phase

**Options**: (A) P1 only; (B) P1 + reject `repeats` loudly; (C) everything including
`doc_score` and median repeats.

**Chosen: A.** Stories 1–4 plus `calibrate` and re-pinned baselines fully close the reported
inversion. Stories 5 and 6 are deferred with rationale (spec §8), not dropped.

---

### D-4 — Where do the known-bad fixtures come from?

**Options**: (A) real broken output only; (B) real + one synthetic "passes checks, empty
inside"; (C) synthetic only.

**Chosen: B.**

**Rationale.** The real file is load-bearing — a synthetic-only suite proves only that the
harness catches defects chosen in advance to be catchable. But the real file **fails the
precheck**, so it never reaches the judge and tests only the deterministic half of the
scale. `hollow_console.html` covers the other half: the defect class no automated check can
see, where the judge is the only detector.

---

### D-5 — Where does the evidence live?

**Chosen: a committed `golden/calibration/` folder. Already implemented.**

**Rationale.** `git check-ignore -v` confirms `.runs/` is ignored via
`backend/evals/grading/.gitignore:7`. The golden run folder and the only recorded copy of
the broken output were both inside it — one cleanup from gone, leaving a scoring bug with
nothing to point at. Extracted 2026-07-30; `git check-ignore` re-run against the new paths
returns "NOT IGNORED".

---

## What the investigation found

### F-1 — The defect is systemic, not build-stage-local

Reconstructed from `golden-mission-control` and frozen at
`golden/calibration/top/mission_control.verdict.json`:

| stage | reported | after caps | dimensions capped |
|---|---|---|---|
| prototype-specify | 94.40 | 84.40 | 2 / 3 |
| prototype-plan | 91.60 | 84.40 | 2 / 3 |
| prototype-analyze | 97.45 | 88.00 | 2 / 3 |
| prototype-build | 94.55 | 80.00 | 3 / 3 |
| prototype-validate | 94.55 | 88.95 | 2 / 3 |
| **mean** | **94.51** | **85.15** | **11 / 15** |

Sample triggering findings, verbatim from the frozen file — none is a defect:

- *"Some metrics (e.g. 1,800 TPS, 0.01% reconciliation variance) could be further
  contextualized with industry benchmarks."*
- *"The report could have explicitly named the page numbers from the spec … This is a minor
  nit, as the content is already highly specific."*
- *"The `gate-detail` page uses a hardcoded checkmark symbol (`&#10003;`) instead of the
  existing `fg-green` class."*

The judge flagged its own findings as nits — in the finding text — and the harness had no
field in which to hear it.

### F-2 — The cap is asymmetric against judge honesty

`consistency_cap(0) == 100`, `consistency_cap(1) == 84`. A judge that writes nothing keeps
98; a judge that notes one cosmetic detail is cut to 84. The prompt simultaneously pleads
*"List every real weakness anyway — hiding one to protect a score defeats the eval"* while
the code punishes exactly that. The incentive and the instruction point in opposite
directions.

### F-3 — The cited evidence for the caps does not reproduce

`model/judge.py:32-38` justifies the caps with *"run 260730-012401 scored HTML the code
track rated 0 at 89.5+"*. In that run folder both build rows show `precheck_passed: false`
with no judge score, and `artifacts/superseded/` holds only `prototype_specify_a1_*`. The
broken file is real (now preserved); the 89.5 figure is not reproducible from the run it
names and must be corrected rather than carried forward.

### F-4 — The two gates disagree at the margin

Also in `260730-012401-small`: `expense_approvals` scored `code_score 97.0` with zero static
issues **and still failed the precheck**. A good code score does not imply a passing
precheck, and neither substitutes for the other. Relevant to any future attempt to collapse
the two.

### F-5 — `options.repeats` is a no-op

`config.py:51` defaults it, `config.py:272` validates it positive, `markdown_report.py:193`
prints it. **No code reads it to do anything.** Anyone setting `repeats: 3` gets one judge
call and no warning. Deferred by decision, recorded as a known lie.

### F-6 — The code track's own defaults under-report brokenness

`code_grader.grade_run_folder(render=False, interactions=False)` — a caller that omits the
flags grades on `static_check` alone, and since the precheck already requires
`static_check.ok`, such a row scores ~100 by construction. The model track's auto-call
(`model_grader.py:198-199`) passes `True`, so the live path is correct, but the default is
a trap. Flipped in Phase 3.

---

## Unknowns

| # | Question | Resolution path |
|---|---|---|
| U-1 | Does `mistral-large-latest` reliably emit a three-value severity enum inside a nested list? | Phase 1 ships the legacy-shape fallback regardless; Phase 5's calibrate run measures the actual fallback rate. |
| U-2 | Will the judge's *raw* scores shift once the cap-announcement prose leaves the prompt? The current text tells the judge caps exist, which may itself depress reported numbers. | Only measurable live. Phase 5 compares fresh reported scores against the frozen `judge_reported` column — a like-for-like comparison the fixture exists to enable. |
| U-3 | What is the real golden ceiling under the new scale? Predicted ~94.5; `min_average_score` must be re-derived from the observed value, not the prediction. | Phase 5 output → Phase 6 re-pin. |
| U-4 | Does `hollow_console.html` actually score low from the judge, or does a plausible-looking empty page fool it? | This is the fixture's purpose. If it scores near the golden, the rubric — not this spec — needs another pass. |
| U-5 | Do the other five golden briefs also clear 90, or was mission_control's margin unusual? | Phase 5 grades all six. |

---

## References

**Code**
- `backend/evals/grading/model/judge.py:32-47` — `CONSISTENCY_CAPS`, `consistency_cap()`
- `backend/evals/grading/model/judge.py:219-237` — the scoring-discipline prompt block
- `backend/evals/grading/model/judge.py:305-324` — `_capped_sub_scores`
- `backend/evals/grading/code/code_grader.py:41-63` — `PENALTIES`, `CODE_WEIGHT`, `blended_score`
- `backend/evals/grading/markdown_report.py:30-126` — `GRADE_BANDS`, `compute_overall`, `_cell_value`
- `backend/evals/grading/model/scoring.py:64-80` — `weighted_total`
- `backend/evals/grading/model/workflows/prototype/prototype_build_validate.py:33-64` — the precheck hook that calls `static_check`

**Fixtures (committed 2026-07-30)**
- `…/golden/calibration/top/mission_control.verdict.json`
- `…/golden/calibration/fail/clinic_scheduler_broken.html` + `.verdict.json`
- `…/golden/calibration/README.md`

**Tests to revise**
- `backend/tests/unit/test_grading_judge.py:502-508` — asserts the old cap table directly
- `backend/tests/unit/test_grading_code_grader.py:207-211` — asserts the un-banded blend
- `backend/tests/unit/test_grading_markdown_report.py:302` — headline blended score

**Related specs**
- `specs/005-prompt-eval-scoring/spec.md` — the harness this calibrates ("Built, uncalibrated")
- `specs/007-prompt-versioning/spec.md` — its verdict trust is gated on this spec
- `backend/evals/grading/model/workflows/prototype/golden/README.md` — *"if the judge gives
  the golden 89 and a broken run 91, the rubric — not the agent — is what needs fixing"*
