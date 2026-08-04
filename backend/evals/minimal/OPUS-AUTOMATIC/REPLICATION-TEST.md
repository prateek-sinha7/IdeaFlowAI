# Replication test — identical prompts, two consecutive runs

The most important result in this folder. Cycles 7 and 8 used **byte-identical
prompts** (v10, hashes verified before each dispatch). Everything that differs is
run-to-run plus judge variance.

## Result

| stage | cycle 7 | cycle 8 | Δ |
|---|---|---|---|
| specify | 63.3 | 58.6 | −4.7 |
| plan | **81.2** | **12.6** | **−68.6** |
| analyze | 63.5 | 50.6 | −12.9 |
| build | 67.2 | 69.5 | +2.3 |
| validate | 35.3 | 53.5 | +18.2 |
| **mean** | **62.1** | **49.0** | **−13.1** |

## What happened

`plan` emitted **one `## Task` header instead of eight.** It wrote Task 1 (the
shell) in full detail — all 27 design tokens, the routes table, the store schema —
then closed `</tasks>` and stopped at 1,066 output tokens. Every page-building task
and the final wiring task simply did not exist. Build received no per-page
instructions and fell back to reading `spec.md` directly.

Artifact sizes, same prompts:

| artifact | cycle 7 | cycle 8 |
|---|---|---|
| specify.md | 37,374 B | 22,902 B |
| **plan.md** | **24,807 B** | **3,098 B** |
| analyze.md | 23,605 B | 14,056 B |
| build.html | 92,594 B | 51,383 B |
| validate.html | 92,560 B | 51,383 B |

## Consequences — read these before drawing any conclusion from this folder

1. **The v10 result does not replicate.** Cycle 7's mean of 62.1 was reported as
   +8.1 over v8. Cycle 8, same prompt, scored 49.0 — *below* the v8 figure it was
   claimed to beat. **The +8.1 cannot be attributed to v10.**
2. **Run-to-run variance on the mean is at least ±13**, on top of the ±9 judge
   noise measured in `VARIANCE-TEST.md`. Combined, the uncertainty band is wider
   than the entire apparent improvement from baseline (39.4) to best (62.1).
3. **Generation variance can be catastrophic, not gradual.** A single stage moved
   68.6 points because the model stopped emitting mid-document. No amount of
   re-judging detects this; only re-running does.
4. **Almost every per-cycle conclusion in this folder is therefore unsafe.** The
   defect-class recurrence analysis and the deterministic checks remain valid —
   they do not depend on the score. The score deltas largely do not.

## The one actionable finding

v10's plan prompt rule 4b says *"Write every task heading and its one-line goal
FIRST, so the full set is on the page, then fill in detail."* On cycle 7 that
fired and produced 8 headers. On cycle 8 the model went straight into Task 1 at
full depth and never returned.

The instruction is correct but **nothing structural enforces it**. There is no
output scaffold that makes a missing header visible, and no downstream check that
rejects a plan with fewer tasks than the spec has pages. That is a real defect
with a real fix, and it is worth more than another prompt cycle:

- **In-prompt**: make the task list a fill-in scaffold — emit all N headers with
  `**Goal**:` lines before any detail, as a literal output template.
- **In-harness** (out of `ADVISE.md` scope, recorded not fixed): `cli checks`
  could assert `count("## Task ") == len(spec pages) + 2` and fail the run. This is
  a deterministic, free, judge-independent gate on exactly the failure that cost
  68.6 points.

## Method note

Any future comparison of two prompt versions needs **at least 3 runs per arm**,
medians reported with spread. One run per arm cannot distinguish a prompt effect
from what is documented above.
