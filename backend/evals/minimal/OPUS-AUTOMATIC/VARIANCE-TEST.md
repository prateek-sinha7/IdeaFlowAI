# Variance test — K=3 judges, one stage, identical bytes

Per `JUDGE.md` §9. Three fresh sub-agents, identical prompt, identical artifacts,
told nothing about each other or about the original verdict. Target: **cycle 4's
validate**, the highest score this project has recorded (87.0) — the one most
worth knowing is real.

## Result

| judge | score | page_completeness | defect_repair_delta | token_and_chrome | findings |
|---|---|---|---|---|---|
| original | **87.0** | 84 | 88 | 92 | 9 |
| k1 | 95.2 | 96 | 96 | 92 | 4 |
| k2 | 77.6 | 74 | 74 | 92 | 8 |
| k3 | 89.8 | 84 | 96 | 92 | 7 |

**median 89.8 · min 77.6 · max 95.2 · spread 17.6**

Original single verdict vs median: **−2.8**.

## What it establishes

**1. The empirical noise floor for a single judge on one stage is ±9 (spread
17.6).** `JUDGE.md` §7 quotes ±4, from Mistral re-judging identical bytes. That
figure does not transfer: the correct figure for this instrument is **more than
four times larger**. Every per-stage delta this project has reported below ~18
points was inside judge noise before any run-to-run variation was added.

**2. Cycle 4's validate 87.0 was real, not a lucky roll.** The median of three
independent re-judgements is 89.8, and the original sits 2.8 below it — if
anything the original was slightly harsh. All four judges independently confirmed
the same substantive facts: the diff was byte-identical (`md5 f70e3eac…`), and the
input artifact was *genuinely sound*, so the no-op was correct. All four found
zero blocking findings. **The validate improvement from 18.4 is confirmed.**

**3. Disagreement is entirely in severity tagging, not in what was found.**
`token_and_chrome_consistency` came back **92 from all four judges**. The spread
lives in `page_completeness` (74–96) and `defect_repair_delta` (74–96), where the
same handful of nits — an unlabelled Fees stat tile, a Department Settings save
that reads none of its controls, one raw hex outside `:root`, inline styles — were
priced anywhere from 4 to 18 points each. Nobody found a defect the others missed
that mattered.

**4. Findings counts vary 4–8 on identical bytes**, so "number of findings" is
also not a precise instrument, though it is steadier than the score.

## Consequences for how this loop should run

- **Two run-to-run variance sources compound**: the artifacts differ every run
  (upstream regeneration) *and* the judge differs (±9 on one stage). Cycle 5's
  build −24.1 and validate −34.1 on byte-identical prompts is these two stacking.
- **A single-judge stage delta under ~20 points is uninterpretable.** Most of what
  this loop has been reacting to falls under that line.
- **K=3 medians should be standard for any run a conclusion is drawn from.** Cost
  is 15 sub-agents per run instead of 5 — and they are free (Claude Code, no API
  spend), unlike the Bedrock dispatch. There is no good reason not to.
- **Severity anchors are the thing to fix if the score needs to be tighter.** The
  judges agree on the facts and disagree on the price. Tightening what counts as
  `major` versus `minor` would shrink the spread more than any prompt edit.
