# Feature Specification: The Minimal Eval System

**Spec ID**: 007-minimal-eval
**Created**: 2026-07-31
**Status**: Specified — greenfield
**Root**: `backend/evals/minimal/`
**Budget**: 7 files · 1,500 lines · 5 commands

---

## 1. Problem

The previous system was 18,000 lines across three packages and seven specs. Asked one
question — *did this prompt edit help?* — it cost **10.3M tokens and four hours** to answer
**"within-noise."** It has been deleted.

Two things went wrong, and both are design constraints now:

**Every defect was an integration seam**, not a logic error — a report that crashed on a
sibling's schema change, a warning that fired because dispatch provenance wasn't recorded, an
applier that couldn't reach the file its advice targeted. Six of them in one day. That is the
signature of too many parts.

**The rigor was calibrated for a sample size that doesn't exist.** Baselines, verdicts,
consistency caps, `REFUSED` — built for statistical confidence, run against 1–5 rows. The
observed noise band was ±2.73 from two samples.

## 2. What it does

Run a workflow's agents on a set of briefs, score the output two ways, and tell you honestly
whether a change moved anything.

```
eval run <config> [--stage S] [--from RUN] [--repeats N]   # the only command that spends
eval score <run>                                            # re-judge stored responses (free)
eval checks <path|run>                                      # deterministic only (free, CI-able)
eval compare <a> <b>                                        # noise-guarded delta
eval report                                                 # rebuild report.html (free)
```

## 3. Requirements

- **R-01 — Stage isolation.** `--stage X --from <run>` works from the first commit. Without
  it every A/B re-runs the whole chain, upstream is re-sampled, and the delta is
  unattributable. This is what made the last comparison uninterpretable.
- **R-02 — Two tracks, one rule.** `checks.py` never imports `judge.py`. Deterministic checks
  are free and must never be hostage to the expensive, flaky judge.
- **R-03 — Checks gate, judge advises.** No blended score. Report three facts:
  `judge 91.1 (n=2)   checks 40.7 (n=3)   completed 2/5`. The old blend turned exactly this
  into a single "F" that read as quality when it was mostly attrition.
- **R-04 — Provenance on every row**: `origin: dispatched | replayed | seeded`. Its absence
  made zero tokens look like under-reporting on every seeded run.
- **R-05 — No delta without ≥2 samples per arm.** `compare` refuses rather than guessing.
- **R-06 — Rendering never breaks a run.** A report failure is a warning. A `KeyError` once
  took down a whole report and left a run folder disagreeing with itself.
- **R-07 — Append-only runs.** A re-run supersedes; captured responses are irrecoverable.
- **R-08 — One path owner.** Only `store.py` touches disk.
- **R-09 — Judge failures cost one row, not the run.** Return partial results; never raise.
- **R-10 — Budget is enforced by a test.** 7 files, 1,500 lines. A number nobody enforces is
  a wish.

## 4. Out of scope

Baselines · verdicts · consistency caps · `REFUSED` · the advisor · `apply-advice` · prompt
versioning · `calibrate` · per-run HTML pages · a second package · any report section beyond
the four in `plan.md`.

**Precheck** is a wrapper-shape check only. The old regex forbidden-list produced three false
failures out of six observations in a day — including failing a spec for the phrase
"no lorem ipsum" *in a statement of compliance*.

## 5. Acceptance

1. `eval run --stage build --from <run>` re-runs one stage against a stored upstream.
2. `eval checks <file.html>` scores an HTML file with no run folder and no model call.
3. `eval compare a b` prints `within-noise` when the delta sits inside the band, and refuses
   entirely when either arm has n<2.
4. A stage where the judge omits a dimension loses that row and completes.
5. `eval report` regenerates `report.html`; deleting a run's JSON degrades it to a warning.
6. `wc -l backend/evals/minimal/*.py` ≤ 1,500 across ≤ 7 files, asserted by a test.
