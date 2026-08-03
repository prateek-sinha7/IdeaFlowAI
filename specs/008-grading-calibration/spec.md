# Feature Specification: Grading Calibration — make the score track the artifact

**Spec ID**: 008-grading-calibration
**Created**: 2026-07-30
**Status**: Clarified — see [clarifications.md](clarifications.md) (C1–C4 resolved, 2 deferred)
**Stack**: Python 3.11 · pytest · Pydantic · LangChain (`evals/grading/`)

---

## 0. In plain English

Our verified-perfect golden artifact scored **80** on its build stage. Broken output has
scored in the 90s. The grader ranks bad work above good work, so none of its numbers mean
anything.

**Why**: the grader counts how many things the judge complained about and cuts the score by
that count. It never asks how *serious* the complaints were.

**How much this costs us** — measured across the whole preserved run, not one stage:

| | judge actually said | what we recorded | gap |
|---|---|---|---|
| average across 5 stages | **94.51** | **85.15** | **−9.36** |
| dimensions capped | | **11 of 15** | |

All five stages were capped. Not one cap was triggered by a defect — the triggering
sentences are things like *"node labels are 11.5px where body text is 14px"*.

**The fix**, four parts:

1. The judge labels each complaint **blocking / major / minor** instead of just listing them.
2. We price them: blocking forces a fail, major costs 8 points, a nitpick costs 1.
3. The browser puts a lid on the judge — it can't score more than 15 points above what the
   automated checks measured. Broken output can no longer be talked up to a passing grade.
4. A new `grade.sh calibrate` command proves known-good beats known-bad, every time we touch
   the rubric.

**Result on our golden**: build 80.0 → **95.2** (B → A+); run average 85.15 → **93.57** (measured).
**Result on broken output**: 63.0 (D) → **15.0 (F)**.

**Already done**: both ends of the scale have been rescued out of the disposable `.runs/`
folder into committed fixtures at
`backend/evals/grading/model/workflows/prototype/golden/calibration/` — see §3.7.

Plain-language walkthrough of every decision: [clarifications.md](clarifications.md).

---

## 1. Problem Statement

The prototype grading harness produces scores that do not rank artifacts correctly. A
hand-verified reference artifact (`golden/mission_control/`, code score **100**, all five
prechecks green, a 24-check behavioural sweep clean) was graded **B / 87.0** overall, with
its build stage at **80.0**. The eval cannot distinguish reference quality from broken
output, which makes every downstream use of it (baselines, `advise`, prompt A/B) unsound.

**The full measurement**, from the now-preserved run (`golden/calibration/top/`):

| stage | judge reported | after caps | code | dimensions capped |
|---|---|---|---|---|
| prototype-specify | 94.40 | **84.40** | — | 2 / 3 |
| prototype-plan | 91.60 | **84.40** | — | 2 / 3 |
| prototype-analyze | 97.45 | **88.00** | — | 2 / 3 |
| prototype-build | 94.55 | **80.00** | 100 | **3 / 3** |
| prototype-validate | 94.55 | **88.95** | 100 | 2 / 3 |
| **mean** | **94.51** | **85.15** | | **11 / 15** |

This is not a build-stage anomaly. Every stage was capped, and 11 of 15 dimensions.

**Root cause**: the judge's number is decided by the *count* of things it wrote down, not
by the *severity* of what it found, and the deterministic evidence the harness already has
is too weak to overrule it. `judge.consistency_cap()` (`model/judge.py:39-47`) caps a
dimension at 84 for one reported weakness and 74 for two, regardless of whether that
weakness is "the detail page is empty" or "node labels use 11.5px while body text is 14px".
On the build stage the judge reported **92 / 95 / 98** with the rationale *"exceptional …
near-flawless … minor nits … outweighed by the prototype's overall quality"*; the caps
rewrote that to **74 / 84 / 84**. Not one of the 11 caps was triggered by a defect.

The mechanism is also asymmetric in the wrong direction. A judge that reports nothing keeps
its 98; a judge that spots one cosmetic detail is cut to 84 — so the harness **penalises
judge thoroughness**. And it never fires on the pathological case it was built for, because
a judge that fails to *see* breakage reports no weaknesses and keeps its 90. It punishes
honesty and is blind to blindness.

---

## 2. User Scenarios & Acceptance Criteria

### Story 1 — A reference artifact scores like a reference artifact (Priority: P1)

An engineer grades the golden artifacts to sanity-check the rubric. The golden is
independently verified: code score 100, every precheck green, every interactive flow
exercised. It should land at the top of the scale, and the only things that may pull it
down are defects a reviewer would actually require fixed.

**Why P1**: This is the golden set's stated purpose (`golden/README.md`: *"if the judge
gives the golden 89 and a broken run 91, the rubric — not the agent — is what needs
fixing"*). Until the ceiling is real, no threshold below it means anything.

**Acceptance Scenarios**:
1. **Given** `golden/mission_control/` graded end-to-end, **When** the judge reports only
   cosmetic findings (font-size drift, "could contextualise the metric"), **Then** no
   dimension is capped below 90 and the run's overall grade is **A or better (≥ 90)**.
2. **Given** the same run, **When** the report is read, **Then** every score reduction is
   attributable to a finding the judge tagged `blocking` or `major`, listed by name in
   `score_caps`.
3. **Given** all six golden briefs, **When** each is graded, **Then** every one scores
   ≥ 90 overall and none is capped by a `minor`-only finding set.
4. **Given** the frozen `top/mission_control.verdict.json` (§3.7), **When** the golden is
   re-graded under the new scale, **Then** the recorded per-stage totals move from the
   capped column toward the reported column — mean **85.15 → 93.57** (measured) — and the count of
   capped dimensions falls from **11 of 15** to zero, because no finding in that file is
   `blocking` or `major`.

---

### Story 2 — Verifiably broken output cannot be rescued by judge prose (Priority: P1)

A run produces HTML whose routes do not resolve and which throws uncaught exceptions.
The code track rates it 0. No amount of judge enthusiasm should let that reach a passing
grade.

**Why P1**: This is the other half of the observed inversion and the reason the caps were
added in the first place; it must be solved by the deterministic evidence rather than by
penalising the judge's honesty.

**Acceptance Scenarios**:
1. **Given** a row whose `code_score` is 0, **When** the judge scores it 90, **Then** the
   cell's effective score is **15.0** (`min(63.0, 0+15)`) and the stage grade is **F**, not the D the raw blend gives. *(C1)*
2. **Given** a row whose `code_score` is 100 and whose judge score is 92, **Then** the
   effective value is unchanged from today's `0.7·judge + 0.3·code` arithmetic — the
   ceiling band binds only where the code track found something. *(C1)*
3. **Given** a row that passes every precheck but has three dead navs (`code_score` 70),
   **When** the judge scores it 92, **Then** the effective score is **85**, not the 85.4 the
   raw blend would give — the band, not the blend, decides the ceiling. *(C1)*
4. **Given** a judge that reports a `blocking` finding on a dimension, **When** it also
   scores that dimension 90, **Then** the dimension is capped to **45** and the report names
   the finding that caused it. *(C2)*

---

### Story 3 — The inversion can never silently return (Priority: P1)

After any rubric, anchor, cap-table or prompt edit, an engineer runs one command and is
told whether the scale still ranks known-good above known-bad.

**Why P1**: The inversion existed for weeks because nothing checked for it. A rubric change
that re-introduces it must fail loudly at edit time, not be discovered by reading a report.

**Acceptance Scenarios**:
1. **Given** the calibration command, **When** it runs, **Then** it grades the golden set
   and the committed `golden/calibration/fail/` fixtures and asserts
   `min(golden) − max(fail) ≥ 25`.
2. **Given** a cap table edited so the golden drops below 90, **When** calibration runs,
   **Then** it exits non-zero naming the golden brief, the stage and the capped dimension.
3. **Given** calibration passes, **When** it completes, **Then** it writes the observed
   golden ceiling into a report an engineer can paste into a `baseline:` block.

---

### Story 4 — A judge finding says how bad it is (Priority: P1)

The judge distinguishes "must be fixed before shipping" from "I would have done this
differently", and the harness prices each accordingly.

**Why P1**: Severity is the missing input. Every other change in this spec depends on it.

**Acceptance Scenarios**:
1. **Given** the judge schema, **When** the judge returns a dimension, **Then** each finding
   carries `severity ∈ {blocking, major, minor}` and a one-line description.
2. **Given** a judge that returns the old flat `weaknesses: list[str]` shape (an older model,
   a fallback path), **Then** the verdict still parses and every entry is treated as `major`
   — the strict-but-not-fatal reading, so a schema miss degrades rather than crashes.
3. **Given** a graded row, **When** `grade.json` is read, **Then** the findings and their
   severities are stored verbatim so a capped score stays auditable and a cap-table change is
   recomputable over stored grades without a re-run.

---

### Story 5 — The document stages have a deterministic anchor too (Priority: P2)

`prototype-specify`, `-plan` and `-analyze` are judged with nothing to check the judge
against; only the two HTML stages have a code track. Their scores drift unobserved.

**Why P2**: Real, but the inversion is demonstrated on the HTML stages; this widens the fix
rather than delivering it.

**Acceptance Scenarios**:
1. **Given** a `spec.md`/`tasks.md`/`analysis.md` response, **When** the code track runs,
   **Then** a deterministic `doc_score` is produced from checkable facts (required sections
   present, promised page count matches the section count, task numbers referenced by
   `analysis.md` resolve to tasks that exist, no unresolved `⚠️`/`TBD` rows in a report
   claiming READY).
2. **Given** a run of all five stages, **When** the top report is written, **Then** no phase
   shows `—` in the `effective` column.

---

### Story 6 — Judge variance is measured, not assumed away (Priority: P2)

`options.repeats` is validated by `config.py:272` and read by nobody — it is a no-op that
looks like a variance control.

**Why P2**: Single-sample judging is a genuine source of inconsistency, but it multiplies
cost and is not the cause of the reported inversion.

**Acceptance Scenarios**:
1. **Given** `options.repeats: 3`, **When** a row is judged, **Then** the judge is called
   three times and the **median** per-dimension sub-score is used.
2. **Given** repeats > 1, **When** the stage summary is written, **Then** it reports the
   observed per-dimension spread so instability is visible rather than averaged away.
3. **Given** repeats is not implemented in this phase, **Then** `config.py` rejects
   `repeats > 1` with an explicit "not implemented" error rather than silently ignoring it.

---

## 3. Technical Design

### 3.1 Tech Stack Context

From `.apex/stack.json`:
- **Language**: Python 3.11 (project convention: `python3.11`, no venv)
- **Framework**: Pydantic v2 structured output over LangChain `with_structured_output`
- **Judge provider**: Mistral (`mistral-large-latest`), pinned per rubric
- **Test**: pytest — `backend/tests/unit/test_grading_*.py`
- **Version constraints**: Pydantic v2 validators only (`field_validator` / `model_validator`,
  `mode="before"`); no v1 `@validator`.

### 3.2 Architecture Fit

All changes land inside `backend/evals/grading/`, on the existing single pipeline — no
sibling implementation (per the standing project constraint that grading features extend
`run_workflow` rather than fork it):

| File | Change |
|---|---|
| `model/judge.py` | severity-tagged findings in the schema; severity penalty model |
| `code/code_grader.py` | ceiling band in `blended_score`; default `render`/`interactions` to `True` |
| `markdown_report.py` | render findings-with-severity; surface the band in the phase table |
| `model/workflows/prototype/*_rubric.yaml` | anchors + scoring-discipline prose aligned to severity; baselines re-pinned |
| `grade_runner.py` | new `calibrate` subcommand |
| `grade.sh` | `calibrate` passthrough |
| `…/golden/calibration/top/mission_control.verdict.json` | ✅ **written** — the frozen graded verdict of the golden run *(C5, §3.7)* |
| `…/golden/calibration/fail/clinic_scheduler_broken.html` | ✅ **written** — real broken output recovered from run `260730-012401-small` (`code_score` 0.0, 7 static issues); fails precheck |
| `…/golden/calibration/fail/hollow_console.html` | **new, still to author** — passes every precheck and `static_check` but its pages are a heading over a near-empty shell. The only defect class the code track structurally cannot see *(C4)* |

### 3.3 Data Model Changes

**New** — `judge.Finding`:

| field | type | meaning |
|---|---|---|
| `severity` | `Literal["blocking","major","minor"]` | how bad |
| `detail` | `str` | one self-contained sentence |

`DimensionScore.weaknesses: list[str]` becomes `findings: list[Finding]`, with a
`mode="before"` validator that lifts a legacy `weaknesses: list[str]` into
`[{severity: "major", detail: …}]`. `JudgeVerdict` gains `dimension_findings:
dict[str, list[dict]]`; `dimension_weaknesses` is retained as a derived view so stored
grades and the report renderer keep working.

**Replaced** — `CONSISTENCY_CAPS = {0:100, 1:84, 2:74}` / floor 64 becomes a **severity
penalty model with one cap reserved for `blocking`** *(C2)*. Counting was the wrong
operation: a step function on a count has cliffs at arbitrary boundaries and never reads
what the findings say.

```python
BLOCKING_CAP   = 45   # a must-fix defect is a failing dimension, not a B
SEVERE_PENALTY = 8    # per blocking or major finding
MINOR_PENALTY  = 1    # per minor finding
MINOR_FLOOR    = 4    # total deduction from minors, capped

severe = blocking_count + major_count
score  = reported - SEVERE_PENALTY * severe - min(MINOR_FLOOR, minor_count)
if blocking_count:
    score = min(score, BLOCKING_CAP)
score = max(0, score)
```

Smooth and monotonic everywhere; the only cliff is the `blocking` one, which is deliberate
— "a reviewer would refuse to ship this" is categorical, not a quantity. A blocking finding
also counts as severe, so two blockings score worse than one.

Applied to the golden's actual mission_control verdict (0 blocking, 0 major; 2 / 1 / 1
minor findings, all cosmetic):

| dimension | reported | minors | scored | today |
|---|---|---|---|---|
| data_realism (w40) | 92 | 2 | **90** | 74 |
| page_completeness (w35) | 95 | 1 | **94** | 84 |
| visual_coherence (w25) | 98 | 1 | **97** | 84 |

Weighted **93.15** → blended with code 100 → **95.2** → **A+**, against today's 80.0.

**New** — the code/judge **ceiling band** in `blended_score` *(C1)*. The originally
proposed floor gate at `code < 40` was found to be near-dead code: the precheck's
`validate:` hook already calls production's `static_check` and fails the row on
`not result.ok`, and `skip_on_precheck_failure: true` means the judge never sees a
structurally broken document. What is unguarded is the middle of the range.

```python
CODE_BAND = 15
effective = min(blended, code_score + CODE_BAND)   # when code_score is not None
```

| code | judge | blended | effective |
|---|---|---|---|
| 100 | 92 | 94.4 | **94.4** (unconstrained — the golden is unaffected) |
| 85 | 92 | 89.9 | **89.9** |
| 70 | 92 | 85.4 | **85.0** (bound by the code track) |
| 0 | 90 | 63.0 | **15.0** (F — today it is 63.0, a D) |

The two defences are independent: the penalty model reads the judge's own words, the band
reads the browser.

### 3.4 API Design

No HTTP surface. CLI:

```
grade.sh calibrate [--workflow prototype]
```

Grades `golden/*` and `golden/calibration/fail/*` through the real precheck + judge + code tracks,
then asserts three invariants and exits non-zero on any failure:

| invariant | default |
|---|---|
| `min(golden overall)` | ≥ 90 |
| `clinic_scheduler_broken` overall | ≤ 20 |
| `hollow_console` overall | ≤ 50 |
| separation `min(golden) − max(negative)` | ≥ 25 |

`hollow_console` is the fixture that keeps the penalty model honest: it is the row where a
judge *should* report majors and score in the 40s with nothing deterministic to back that
up. If it ever scores near the golden, the rubric has stopped reading content.

Output is a report naming, per failure, the brief, the stage, the dimension and the
finding that caused it — plus a ready-to-paste `baseline:` block reflecting the observed
ceiling.

> Per the standing constraint, `calibrate` is **run by the user**, never by the assistant:
> it makes live judge calls.

### 3.5 Component / Module Design

- `judge.price_findings(reported, findings) -> (score, breakdown)` — pure, unit-testable
  without a model. Named for what it does: it prices findings, it no longer returns a cap.
- `judge._capped_sub_scores` keeps its contract (returns `sub_scores`, `score_caps`) and
  gains the triggering findings and the per-severity breakdown inside each entry.
- `code_grader.blended_score` keeps its two-argument signature; the band is internal, so
  every call site (`markdown_report.py:126`, `:579`, `compute_overall`) picks it up for free.
- `grade_runner.run_calibration(workflow)` — new, reusing `run_workflow` for the grading
  itself rather than re-implementing dispatch.

### 3.6 Prompt changes (`*_rubric.yaml`)

The scoring-discipline block currently contains two instructions that contradict the
anchors and each other: *"a dimension where you report one weakness is capped at 84"* and
*"Scores above 90 should be rare"*, against a `95` anchor defined as reference quality.
Together they made 84 the effective ceiling for any artifact a thorough judge inspected.
Replace with: report every finding, tag its severity honestly, and score the dimension on
the anchors — stinginess is now enforced by severity, not by asking the judge to be
generally harsh.

### 3.7 The calibration fixture store *(C5 — already implemented)*

`.runs/` is gitignored (`evals/grading/.gitignore:7`) and disposable. Both ends of the
scale were extracted from it on 2026-07-30 into a committed folder, verified with
`git check-ignore` as tracked:

```
model/workflows/prototype/golden/calibration/
├── README.md
├── top/mission_control.verdict.json
└── fail/clinic_scheduler_broken.html
    fail/clinic_scheduler_broken.verdict.json
```

**`top/mission_control.verdict.json`** — the artifacts were already committed at
`golden/mission_control/`; the *graded verdict* was not. Per stage it records:

| field | why |
|---|---|
| `weights` | the totals are recomputable if a weight changes |
| `judge_reported` / `after_caps` | the two numbers whose divergence is the defect |
| `score_caps` | which cap fired, with the reported value and weakness count |
| `findings_by_dimension` | the verbatim sentence that triggered each cap — the proof they were cosmetic |
| `reported_total` / `capped_total` | per-stage weighted totals |
| `code_score`, `precheck_passed`, `rationale` | the corroborating evidence |

Plus a `headline` block: mean reported 94.51, mean capped 85.15, 11 of 15 dimensions capped.

**`fail/clinic_scheduler_broken.html`** — 18,905 bytes of real agent output, with a
companion JSON recording `code_score` 0.0, the 7 static issues verbatim, `precheck_passed:
false`, and a SHA-256 so silent modification is detectable.

**Maintenance rule**: re-freeze `top/` whenever the golden artifacts change, the rubric
weights change, or a new calibration run is recorded — in the same commit, so the fixture
and the scale it calibrates cannot drift apart.

---

## 4. Non-Functional Requirements

| Requirement | Target | Measurement |
|---|---|---|
| Backward compatibility | every existing `grade.json` in `.runs/` still renders | `markdown_report.write_report` over each stored run folder |
| Determinism | `severity_cap` and `blended_score` are pure functions | unit tests, no model calls |
| Recomputability | a cap-table change is replayable over stored grades | findings + severities persisted in `grade.json` |
| Cost | calibration ≤ one judge call per (golden brief × stage) | run report token totals |
| Test Coverage | >80% on changed modules; every cap-table row and the gate boundary explicitly tested | pytest + coverage |
| Auditability | no score reduction without a named finding in the report | `calibrate` report inspection |

---

## 5. Out of Scope

- Re-scoring or rewriting the golden artifacts themselves — they are verified correct;
  this spec changes the scale, not the ceiling.
- Changing `CODE_WEIGHT` (0.3) or the `PENALTIES` table — the blend is sound above the gate.
- Changing `GRADE_BANDS` — A++ ≥ 97 becomes genuinely reachable once caps stop forcing 84,
  which is the intended behaviour, not a bug to fix.
- The judge provider, model pinning, or rate-limit retry path.
- `evals/hybrid/` and the legacy eval suites.
- **Deferred, not dropped** *(C3)* — Story 5 (`doc_score` for the three document stages)
  and Story 6 (`options.repeats`). See §8.

---

## 6. Dependencies & Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Every rubric edit changes `rubric_hash`, flipping all baselines to `REFUSED` | **Certain** | High | Sequence the work: land code + rubric changes, run `calibrate`, then re-pin all five `set_from` blocks in one commit. Baselines are expected to be REFUSED in between. |
| Dropping caps on majors re-opens the "90 with issues" pathology | Medium | High | Two independent defences replace it: the `blocking` cap (45) reads the judge's own words, and the ceiling band reads the browser. Neither depends on the judge being stingy. `hollow_console` is the fixture that asserts the case where only the judge can catch the defect. |
| Mistral does not reliably emit the severity enum | Medium | Medium | Legacy-shape fallback treats untagged findings as `major`; a run where >20% of dimensions fall back emits a summary warning. |
| Committed negative fixtures rot as `static_check` evolves | Low | Medium | Fixtures assert a **score band**, not an exact number, and `calibrate` prints the observed value. |
| The evidence for this whole spec lives in a gitignored folder | ~~High~~ | ~~High~~ | **Closed** — `.runs/` is disposable, so both ends of the scale were extracted into `golden/calibration/` before anything else (C5, §3.7). |
| `top/mission_control.verdict.json` drifts from the live rubric after a weight edit | Medium | Low | The fixture stores the `weights` it was scored under, so a stale comparison is detectable rather than silently wrong; §3.7 states the re-freeze rule. |
| Baseline `min_average_score: 70` was calibrated on the capped scale | **Certain** | Medium | Re-derive from the `calibrate` output; the floor should sit ~20 below the observed golden ceiling. |
| `options.repeats` stays a silent no-op through this phase *(C3)* | **Certain** | Low | Recorded in §8 as a known lie. It is validated by `config.py:272` and read by nothing, so anyone setting it believes they have a variance control they do not have. Must be implemented or removed before it is relied on. |
| The `89.5` figure cited in `judge.py:32-38` is not reproducible from the run it names | **Certain** | Low | Both build rows in `260730-012401-small` show `precheck_passed: false` with no judge score. The inversion is real and evidenced by the mission_control grade; that specific citation must be corrected or dropped when `judge.py` is edited, not carried forward unverified. |

---

## 7. Sequencing

Scope is **P1 only** *(C3)*.

0. ✅ **Done** — both calibration fixtures extracted from `.runs/` and committed (C5, §3.7).
1. **P1a** — `Finding` + severity in the judge schema, with the legacy fallback (Story 4).
2. **P1b** — `price_findings()` severity penalty model replacing `CONSISTENCY_CAPS` (Story 1).
3. **P1c** — ceiling band in `blended_score`; `render`/`interactions` default `True` (Story 2).
4. **P1d** — rubric prose + anchors aligned; `hollow_console.html` authored into
   `golden/calibration/fail/`.
5. **P1e** — `grade.sh calibrate`; **user runs it**; baselines re-pinned from its output (Story 3).

Steps 1–4 are offline and fully unit-testable. Step 5 is the only one requiring live judge
calls, and it is the user's to run.

---

## 8. Deferred

| item | why deferred | why not dropped |
|---|---|---|
| **Story 5 — `doc_score` for specify/plan/analyze** | The inversion is demonstrated and fixed on the HTML stages; a new deterministic checker widens the change surface without making the fix more correct. | Those three stages have no anchor at all — the judge grades them unchecked, and their `effective` column has already shown `—`. The C1 ceiling band cannot protect a stage with no code score. |
| **Story 6 — `options.repeats`** | Medians triple judge cost on every run, and single-sample variance did not cause the reported inversion. | `repeats` is validated by `config.py:272` and read by **nothing** — a config key that silently lies about what it does. It must be implemented or removed before anyone relies on it. |

Neither deferral blocks `calibrate`: it grades whatever stages the run produced.
