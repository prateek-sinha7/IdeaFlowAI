# Execution Design: Grading Calibration

**Spec**: `specs/008-grading-calibration/spec.md`
**Plan**: `specs/008-grading-calibration/plan.md`
**Created**: 2026-07-30
**Status**: Designed

---

## Build Slices

Four slices. Slice 0 is complete. Slices 1–3 are entirely offline; the single live handoff
sits between Slice 3 and Slice 4.

### Slice 0 — Evidence preservation ✅ **DONE**

Both ends of the scale extracted from gitignored `.runs/` into
`model/workflows/prototype/golden/calibration/`, `git check-ignore`-verified as tracked.
Everything downstream reads these files instead of a scratch folder.

**Delivered**: `README.md`, `top/mission_control.verdict.json`,
`fail/clinic_scheduler_broken.html` + `.verdict.json`.

---

### Slice 1 — Foundation: severity exists but changes nothing

Add the vocabulary before changing any arithmetic. `Finding`, `DimensionScore.findings`, the
legacy-shape lift, `JudgeVerdict.dimension_findings` / `severity_fallbacks`, and the prompt
text that asks for severities.

**Deliberately score-neutral.** `consistency_cap()` still runs, still keyed on
`len(findings)`, so this slice can land and be reviewed without any score moving. That
separation is the point: if a score changes in Slice 1, something is wrong.

**Tasks**: T1, T2, T3

---

### Slice 2 — Core logic: pricing and the band

The two arithmetic changes, each independently revertable.

`price_findings()` replaces `consistency_cap()`; `CODE_BAND` enters `blended_score`. Both
are pure functions with no I/O and no model call, so both are fully testable offline — and
both are strict tightenings in the sense that matters: pricing may only subtract, and the
band is a `min`.

The slice's keystone is the **golden replay test**: it reads
`top/mission_control.verdict.json` and asserts the five stages move from the capped column
toward the reported column. That single test is the executable form of this entire spec.

**Tasks**: T4, T5, T6, T7, T8

---

### Slice 3 — Interface: rubrics, the missing fixture, and `calibrate`

The prose the judge reads, the fixture that tests the half no checker can see, and the
command that ties known-good to known-bad.

`hollow_console.html` is the interesting piece of work here — it has to be *good enough to
pass every structural check* and *empty enough that a reader would reject it*. Getting that
balance right is what makes it a real test rather than decoration.

**Tasks**: T9, T10, T11, T12, T13

---

### ⏸ HANDOFF — `./grade.sh calibrate` (the user runs this)

The only step that spends tokens. Everything before it is offline; everything after it
consumes its output.

---

### Slice 4 — Verification and hardening

Re-pin the five baselines from observed numbers, re-freeze the top fixture under the new
scale, and correct the golden docs. Nothing here may be done from predicted values.

**Tasks**: T14, T15, T16

---

## Component Boundaries

```
                      ┌──────────────────────────────────────┐
                      │ model/judge.py                       │
   judge reply ──────►│  Finding / DimensionScore            │  Slice 1
                      │  price_findings()  ← pure            │  Slice 2
                      └──────────────┬───────────────────────┘
                                     │ sub_scores
                      ┌──────────────▼───────────────────────┐
                      │ model/scoring.py    UNTOUCHED        │
                      │  weighted_total(sub_scores, dims)    │
                      └──────────────┬───────────────────────┘
                                     │ row["score"]
                      ┌──────────────▼───────────────────────┐
   code_score ───────►│ code/code_grader.py                  │
                      │  blended_score()  ← CODE_BAND        │  Slice 2
                      └──────────────┬───────────────────────┘
                                     │ THE ONLY CHOKEPOINT
                      ┌──────────────▼───────────────────────┐
                      │ markdown_report.py                   │
                      │  compute_overall · phase table ·     │
                      │  per-row table — all 3 via blended   │
                      └──────────────────────────────────────┘

      grade_runner.calibrate ──reads──► golden/*  +  golden/calibration/fail/*
                              (committed files — never .runs/)
```

**Boundaries that must hold:**

| boundary | rule |
|---|---|
| `judge.py` ↔ `code_grader.py` | They never import each other. The cheap deterministic checks stay independent of the expensive model calls — this is why two independent defences are possible at all. |
| `scoring.py` | Imports nothing from the package. Weights are applied here, never baked into the judge schema, so a weight edit is recomputable over stored sub-scores without a re-run. **Not touched by this spec.** |
| `blended_score` | The single chokepoint. Keeping its signature stable is what guarantees no report path is left on the old arithmetic. |
| `price_findings` | Pure: no I/O, no model, no clock. Table-testable, and replayable over a stored fixture. |
| `artifacts.py` | Sole owner of every `.runs/` path. **Not touched** — the calibration reads committed files, not run folders. |

---

## State Transitions / Flows

### One dimension's score, end to end

```
judge returns  reported=92, findings=[minor, minor]
      │
      ▼  price_findings()
severe = 0 → −0
minor  = 2 → −2
blocking? no → no cap
      ▼
score = 90                                       (today: 74)
      │
      ▼  weighted_total() with weight 40
contributes 36.0 to the stage total
      │
      ▼  blended_score(judge_total, code_score=100)
0.7·93.15 + 0.3·100 = 95.2     min(95.2, 115) = 95.2
      │
      ▼  letter_grade()
A+                                               (today: B)
```

### Severity → outcome

| findings on a dimension | reported 95 → | why |
|---|---|---|
| none | **95** | untouched |
| 4 × minor | **91** | −4, the minor floor |
| 8 × minor | **91** | still −4; nits cannot compound into a failure |
| 1 × major | **87** | −8 |
| 2 × major | **79** | −16 |
| 1 × blocking | **45** | −8 then capped |
| 2 × blocking | **45** | −16 → 79, capped to 45 |
| 1 blocking + 1 major | **45** | −16 → 79, capped to 45 |

### Baseline verdict across the phases

```
Slice 1  →  PASS   (nothing moved yet — by design)
Slice 2  →  PASS   (rubric_hash unchanged; only code changed)
Slice 3  →  REFUSED ← rubric edits change rubric_hash. CORRECT, expected, loud.
HANDOFF  →  REFUSED
Slice 4  →  PASS   (re-pinned from observed output, never predicted)
```

---

## Failure Modes

| # | Failure | Detection | Response |
|---|---|---|---|
| F1 | Judge omits `severity` or emits an unknown value | `mode="before"` validator | Lift to `major`; increment `severity_fallbacks`. **Never** discard a paid-for verdict — the failure `_lift_narrative` and `_join_evidence` already exist to prevent. |
| F2 | Fallback rate is high enough that severity is fiction | `severity_fallbacks / dimensions > 20%` | Emit a stage warning. A run where most findings defaulted to `major` is scoring by a different rule than the one documented, and must say so. |
| F3 | Judge inflates raw scores now that the cap prose is gone | Compare fresh `judge_reported` against the frozen column in `top/*.verdict.json` | The like-for-like comparison the fixture exists to enable (research U-2). Only measurable at the handoff. |
| F4 | Judge tags a cosmetic nit `blocking` | `calibrate` — golden drops below 90 | Fails loudly naming brief/stage/dimension/finding. Fix is prose (sharper severity definitions), not the cap. |
| F5 | `hollow_console.html` scores near the golden | `calibrate` invariant `≤ 50` | The rubric has stopped reading content. Escalate — this is a rubric problem, not a threshold to loosen. |
| F6 | `hollow_console.html` fails the code track | `calibrate` asserts `code_score ≥ 90` | It has become a structural fixture and no longer tests the judgement half. Rewrite it. |
| F7 | `clinic_scheduler_broken.html` drifts | SHA-256 mismatch against its verdict JSON | **Hard error, not a warning.** Either the file was edited or `static_check` changed under it; both need a human. |
| F8 | Someone deletes `golden/calibration/` | No automated guard | Documented in `README.md` and `quickstart.md` rollback notes. It was rescued from a gitignored folder precisely because it was fragile. |
| F9 | Baselines re-pinned from predicted rather than observed values | Review | Sequencing forbids it: Slice 4 runs only after the handoff. Pinning to predictions would defeat calibration entirely. |
| F10 | Chromium absent after the `render=True` default flip | `available: false` in findings | Already handled — `compute_code_score` subtracts nothing for a skipped check, keeping the score a lower bound on brokenness rather than a guess. |
| F11 | A report path silently keeps the old blend | Impossible by construction | All three consumers route through `blended_score`; the band is internal (AD-4). |
| F12 | Stored old-format `grade.json` breaks the renderer | `test_grading_markdown_report.py` over stored shapes | Readers accept both `score_caps` shapes, keyed on the presence of `final`; `dimension_weaknesses` is retained as a derived view. |

---

## Observability Hooks

Nothing to instrument — no service, no metrics backend. Observability here means **what the
artifacts and the terminal tell a human**.

| hook | where | answers |
|---|---|---|
| `score_caps` for **every** dimension | `<token>_grade.json` | "Why is this number what it is?" — previously absent entries were indistinguishable from unrecorded ones |
| `findings` verbatim with severity | `<token>_grade.json`, stage report | "Was this an actual defect or a nit?" — the field whose absence caused this whole spec |
| `severity_fallbacks` + >20% warning | stage summary | "Is severity real in this run, or mostly defaulted?" |
| band-bound marker on a cell | phase table, per-row table | "Did the browser overrule the judge here?" |
| `calibrate` invariant table | stdout, exit code | "Does the scale still rank good above bad?" |
| paste-ready `baseline:` block | `calibrate` stdout | Removes the temptation to hand-derive thresholds |
| frozen `top/*.verdict.json` | committed | The before/after record; survives `.runs/` cleanup |

**Explicitly not added**: silent truncation anywhere. If `calibrate` skips a brief or a
stage, it says so — a bounded run that reads as full coverage is the reporting failure this
package's own conventions warn against.

---

## Rollback Notes

| scenario | action | consequence |
|---|---|---|
| Slice 1 only | `git revert` | Clean. Nothing depends on `findings` yet. |
| Slice 2 only | `git revert` | Restores caps and the un-banded blend. Stored grades stay readable (F12). |
| Slice 3 only | `git revert` rubrics **and** the `calibrate` command together | Reverting rubrics alone leaves baselines pinned to a hash nothing produces → every run `REFUSED`. Loud and safe, but incomplete. |
| Slice 4 only | Re-pin to the previous `set_from` | Only valid alongside a Slice 2+3 revert; the old thresholds were calibrated on the capped scale. |
| Full revert | Revert Slices 1–4 | **Keep Slice 0.** The fixtures are evidence, not implementation — deleting them re-creates the original problem of a scoring bug with nothing to point at. |

No database, no service, no deployed artifact, no migration. Every change is source-level.

**One-way door**: none. The single irreversible risk is deleting `golden/calibration/`,
which is why it is called out in `README.md`, `quickstart.md` and here.
