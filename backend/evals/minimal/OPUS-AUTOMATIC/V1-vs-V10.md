# v1 vs v10, both with thinking, both judged on the fixed instrument

The first controlled comparison in this project. Everything before it was either
cross-instrument or single-run.

- Same brief (`aws_3_permits`), same provider (Bedrock haiku-4-5), same
  `THINKING_BUDGET_TOKENS=10000`, 3 runs per arm.
- Both arms judged with the corrected judge instrument (upstream artifacts supplied,
  rubric-scoped) and the anti-false-positive calibration.
- v1 activated via `activate.sh prototype v1` and verified by content hash; v1 carries
  no version marker, so identity was confirmed against `prototype-*.v1.md` bodies.
- K=1 per stage. Per-stage judge spread measured earlier is 8-17 points; treat
  individual cells as ±8 and only trust gaps that exceed the run-to-run range.

## Result

| stage | v1 runs | v1 median | v10 runs | v10 median | gap | ranges overlap? |
|---|---|---|---|---|---|---|
| specify | 40.8 / 25.4 / 28.3 | 28.3 | 49.7 / 70.4 / 68.7 | 68.7 | **+40.4** | no |
| plan | 51.4 / 68.8 / 69.2 | 68.8 | 71.2 / 65.6 / 52.0 | 65.6 | -3.2 | **YES** |
| analyze | 44.0 / 56.3 / 52.8 | 52.8 | 68.3 / 81.5 / 76.7 | 76.7 | **+23.9** | no |
| build | 12.3 / 24.1 / 52.0 | 24.1 | 74.7 / 85.6 / 71.4 | 74.7 | **+50.6** | no |
| validate | 33.9 / 52.5 / 35.7 | 35.7 | 73.6 / 78.0 / 57.6 | 73.6 | **+37.9** | no |
| **run mean** | 36.5 / 45.4 / 47.6 | **45.4** | 67.5 / 76.2 / 65.3 | **67.5** | **+22.1** | no |

**The prompt work is worth roughly +22 points on the mean.** The arms do not overlap
on run means (v1 max 47.6 < v10 min 65.3), and the gap is ~2x the observed run-to-run
range. This is the only finding in the project that clears that bar comfortably.

## Where the gain is, and is not

Four of five stages improved with no overlap. **plan did not.** v1's plan is marginally
ahead (68.8 vs 65.6, inside noise, ranges almost fully overlapping).

## The mechanism: v1 defers implementation to validate

This is not a uniform quality difference. The two prompt sets divide the work
differently, and v1's division is fragile.

| | v1 | v10 |
|---|---|---|
| build output | 7.5k / 10.9k / 24.7k tokens | ~21k every run |
| build artifact | 17.9k / 29.2k / ~59k chars | 56-82k chars |
| build `page_completeness` | **0 / 0 / 30** | 74 / 84 / 52 |
| validate delta | 1027 / 711 / 70 lines | 0-11 lines |
| render gate failures | **2 of 3 runs** | 0 of 3 |

v1's build ships **placeholder stubs** — a validate judge found the delta was "exactly
the six `console.log` render stubs plus the '(Placeholders)' banner" — and leaves
validate to implement six pages blind in one pass. That is where v1's breakage comes
from:

- run 1: rewrite dropped the `</style>` terminator -> page renders nothing
- run 2: rewrite introduced 15 uncaught exceptions, 15/20 nav links dead
- run 3: build itself failed the gate, 16/20 nav links dead

v10's build implements directly, so validate only patches (0-11 lines) and never
gambles.

**v1's build is bimodal**, which is the sharper statement: twice it stubbed
(`page_completeness` 0), once it implemented (30). v10's build implements every time.
The prompt work did not make build better at building — it made build reliably
*decide to build at all*.

## Stage findings, restated against the control

**analyze `defect_detection`** — v1: 1 / 0 / 6 (median 1). v10: 34 / 62 / 38
(median 38). Clean separation, no overlap. v10's detection is weak in absolute terms
AND ~37 points better than the prompt it replaced. Both true; only the control shows it.

**specify `spec_consistency_completeness`** — v1: 0 / 0 / 0. v10: 11 / 34 / 38.
The dimension I spent the night calling v10's persistent weakness scored zero in every
v1 run.

**plan `task_self_containment`** — v1: 38 / 46 / 38. v10: 48 / 25 / 0. v10 is somewhat
worse here, offset by `page_coverage` (v10 96-100 vs v1 74-96), netting to a wash.

## Claims I made earlier tonight that this control corrected

| claim | status |
|---|---|
| v6 cite-`spec.md` rule was "the strongest finding", worth 25-40 pts to reverse | **wrong both ways.** Plan is the one stage the prompt work bought nothing on; v1 edges it by 3.2, inside noise. Reverting toward v1's approach gains nothing. |
| "validate is a passthrough banking free weight" | half right. The rubric flaw is real (a v10 no-op scored 78.0), but validate's *behaviour* is far better than v1's, which rewrites wholesale and breaks the file 2 runs in 3. |
| "analyze reliably under-detects — it's the artifact" | right that it's the artifact, wrong that it's a v10 failure. It is a 37-point v10 *improvement* over v1. |
| deterministic render gate is ground truth | **false negative found.** v1 run 1's validate dropped `</style>` (verified: `<style>`=1, `</style>`=0) and the gate passed it 100.0. |

The common cause: judging v10's weak dimensions against an imagined better alternative
instead of against the prompt that actually lacks the change. Three of the four would
have misdirected v11.

## Harness defects found (recorded, not fixed)

- **`checks.py` render gate false negative** — passes a file with an unterminated
  `<style>` block that renders nothing. Complements the known false positive on
  parameterised hash routes (`#/application/:id`).
- **Mistral judge calibration** — scored a v1 prototype **95.0** while the same run's
  deterministic checks read 0.0 with 15 uncaught exceptions and 15/20 nav links dead.
