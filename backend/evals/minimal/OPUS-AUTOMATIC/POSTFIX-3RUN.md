# Post-fix set — v10 + thinking, corrected judge instrument, 3 runs

Runs: `260804-030808`, `260804-032024`, `260804-033458` (cycles 12-14 in SCORES.csv)
Prompts: v10, unchanged and verified byte-identical to source before dispatch.
`THINKING_BUDGET_TOKENS=10000`.
Judging: run 1 at K=3 on analyze/build/validate; runs 2-3 at K=1. Run 1's spreads
(8.6-17.2) apply to the K=1 numbers too — treat them as ±8 or so.

## Scores

| stage | r1 | r2 | r3 | median | range |
|---|---|---|---|---|---|
| specify | 49.7 | 70.4 | 68.7 | 68.7 | 20.7 |
| plan | 71.2 | 65.6 | 52.0 | 65.6 | 19.2 |
| analyze | 68.3 | 81.5 | 76.7 | 76.7 | 13.2 |
| build | 74.7 | 85.6 | 71.4 | 74.7 | 14.2 |
| validate | 73.6 | 78.0 | 57.6 | 73.6 | 20.4 |
| **mean** | **67.5** | **76.2** | **65.3** | **67.5** | 10.9 |

## The headline is the variance, not the mean

Per-stage range across three runs of IDENTICAL prompts: 13.2 to 20.7 points.
`specify` is the cleanest control in the project — it takes no upstream evidence, so
the instrument fix did not touch its prompt at all — and it moved 49.7 -> 70.4 between
consecutive runs. Nothing changed but the sampling.

This is large enough to manufacture a convincing trend from any two runs, and it did,
repeatedly, over the course of this work. Three conclusions drawn earlier in the
session had to be withdrawn when a third run arrived:

| claim | drawn from | killed by |
|---|---|---|
| "instrument fix collapsed spread 7x" | c11 analyze spread 2.6 | post-fix r1 spread 17.2 |
| "validate is a passthrough banking free weight" | c10 zero-edit run | c11 repairing three P0s |
| "analyze reliably under-detects, it's the artifact" | 10 judgements at 0-48 | r2 `defect_detection` 62 |

Standard going forward, and the one the v1 comparison must be held to: no claim from
fewer than three runs; per-stage differences under ~15 points are noise unless they
repeat.

## What the instrument fix actually bought

Not stability — correctness, and a better class of disagreement.

All three run-1 validate judges produced *byte-identical factual accounts* of the
repair: the same two changed lines, the same P0, the same
`querySelector('section[data-page="applications"]')` diagnosis. They then priced it
73.6 / 72.8 / 86.7. Evidence eliminated factual disagreement and left severity
disagreement untouched. That is the honest description; "variance collapsed" was not.

Dimensions that moved once evidence was supplied — these were being docked for
evidence the judge never had:

| dimension | blind | with evidence |
|---|---|---|
| plan `page_coverage` | scored by guessing the spec | 100, 100, 100 (verified) |
| analyze `cross_artifact_grounding` | 56-88 | 92, 96 |
| validate `defect_repair_delta` | 19-56 on real repairs | measured per-run |

Verification that is only possible post-fix: an analyze judge caught the report
miscounting CSS classes (33 vs 34) and a $2,739,500 / $2,442,500 arithmetic
contradiction between Task 6 and Task 8 — by checking against the real spec.

## RUBRIC DEFECT: validate's score is dominated by the artifact it receives

Two runs where validate changed NOTHING (byte-identical output, confirmed by md5 and
`diff` by the judges themselves):

| run | validate | page_completeness (45%) | defect_repair_delta (35%) | token (20%) |
|---|---|---|---|---|
| r2 | **78.0** | 92 | 52 | 92 |
| r3 | **57.6** | 60 | 37 | 88 |

Same behaviour — a no-op — scored 20.4 points apart, because `page_completeness` and
`token_and_chrome_consistency` (65% of the weight combined) are inherited wholesale
from whatever build handed over. `defect_repair_delta` correctly priced both as
failures; it is outvoted.

So validate's number mostly reports build's quality, not validate's contribution. A
no-op on a good build (78.0) outscores a genuine 3xP0 repair on a weak one. This is a
rubric design flaw, not a prompt problem, and it is now measured rather than suspected
— the earlier blind instrument could not have shown it.

## Stage findings that survive the variance bar

**plan `task_self_containment` — the strongest finding in the project.**
Five judgements, four runs, two instruments: **29, 15, 48, 25, 0** (median 25, never
above 48). Against `page_coverage` at 96-100 every single run.

The mechanism is identified and it is self-inflicted: the v6 cite-`spec.md`-don't-copy
rule, added to stop plan truncating. It fixed truncation and traded away a 40%-weight
dimension. Copy inline -> truncation kills `page_coverage`; cite -> self-containment
collapses. The untried third option is to emit the seed records once, compactly, in
the single task that consumes them.

Worth ~25-40 points on a 40%-weight dimension. Highest-value prompt fix available.

**specify `spec_consistency_completeness` — consistently its weakest.**
11, 34, 38 post-fix; 44, 48 in cycles 10-11. Never once the strongest dimension.

**analyze `defect_detection` — lowest-scoring but NOT reliable.**
0 to 62 observed. Still the lowest of analyze's three dimensions on average, so still
the right target, but "analyze reliably fails to detect" is not supportable.

## Series to date

| cycle | prompts | mean |
|---|---|---|
| 0 | v2 | 39.4 |
| 4 | v6 | 61.3 |
| 7 | v10 | 62.1 |
| 8 | v10 (replication of 7) | 49.0 |
| 9-11 | v10+think | 63.1, 67.5, 65.3 |
| 12-14 | v10+think, fixed judge | 67.5, 76.2, 65.3 |

Cycles 7 and 8 are the same prompts 13 points apart — the scale against which every
other delta here should be read.

What survives that bar: v2-era runs never reached the v10+thinking band, and the
39.4 -> mid-60s span is far outside ±13. **The cumulative prompt work bought something
real; almost none of the individual version-to-version deltas claimed along the way
were distinguishable from noise.**

## Outstanding

v1 + thinking baseline, to test the cumulative claim against the true original.
Blocked: the AWS bearer token expired mid-run (third expiry of the session, ~60-90 min
after refresh each time). v1 was activated and verified before the failure; two stages
completed (specify 9,348 tok, plan 11,282 tok) before `AccessDeniedException`.
