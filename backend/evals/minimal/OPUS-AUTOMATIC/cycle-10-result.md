# Cycle 10 — v10 + thinking, run 2 of 3

Run: `260804-022332-prototype_aws_3_permits`
Judged: `260804-024020-prototype_aws_3_permits-opusjudge`
Config unchanged from cycles 7-9. `THINKING_BUDGET_TOKENS=10000`, `MAX_OUTPUT_TOKENS`
unset (32768). All five active overrides verified byte-identical to the v10 sources
before dispatch, each carrying its `[PROMPT_VERSION: ... v10 ...]` marker.

## Scores

| stage | judges | median | spread | vs c9 |
|---|---|---|---|---|
| specify | 70.9 | **70.9** | K=1 | +7.5 |
| plan | 67.2 | **67.2** | K=1 | +3.2 |
| analyze | 45.1 / 57.9 / 64.0 | **57.9** | 18.9 | +29.8 |
| build | 69.1 / 71.0 / 74.7 | **71.0** | 5.6 | -3.9 |
| validate | 48.6 / 70.5 / 71.3 | **70.5** | 22.6 | -14.8 |
| **mean** | | **67.5** | | **+4.4** |

Highest mean recorded. Prior: c7 62.1, c8 49.0, c9 63.1.

## Token costs

| stage | c9 | c10 |
|---|---|---|
| specify | 11,244 | 10,477 |
| plan | 6,788 | 6,877 |
| analyze | 11,325 | 13,789 |
| build | 23,154 | 21,372 |
| validate | 9,240 | 5,873 |

## The instrument defect that invalidates the validate series

`judge_prompts/validate.txt` contains no pre-fix artifact. Rendered section sizes:

```
AGENT SYSTEM PROMPT       29 chars   (empty)
BRIEF                    840
RESPONSE              65,431
RUBRIC                 2,281
DIMENSIONS             1,362
```

`build_judge_prompt` is called with `prompt=row["prompt"]`; for validate that row's
prompt is the brief alone. The build artifact validate was asked to audit and repair
never enters the prompt. So `defect_repair_delta` — 35% of validate's weight — has
been scored blind in every run.

Found independently by validate k1 and k2, who each recovered the prior artifact from
the sibling `build.txt` and diffed it rather than guess. Confirmed by direct inspection.

**This retroactively undermines cycle 9's validate 85.3**, which was the single source
of cycle 9's 63.1 being the then-highest mean. It also undermines the v3
`defect_repair_delta` 0 -> 92 result that the "write the audit before you edit anything"
rule was credited with landing.

Recorded in APPLIED.md, not fixed — ADVISE.md scopes this work to prompts.

## validate did nothing this run

`build.html` and `validate.html` are byte-identical (65,419 bytes; `diff` reports zero
changed lines). All three judges established this independently and all three priced
`defect_repair_delta` as a failure — 56 / 56 / 19. Validate's output dropped to 5,873
tokens, consistent with writing an audit and repairing nothing.

That the stage still scored 70.5 is the instrument's doing: `page_completeness` (45%)
and `token_and_chrome_consistency` (20%) are both inherited wholesale from build's
output, so a pure passthrough banks 65% of the weight for free.

## analyze: a reproducible, actionable diagnosis

| dimension | k1 | k2 | k3 |
|---|---|---|---|
| cross_artifact_grounding | 74 | 78 | 64 |
| defect_detection | **15** | **25** | **0** |
| verdict_coherence | 92 | 96 | 78 |

Three independent judges converge: analyze writes a coherent, well-grounded report
that fails to find the defects that are demonstrably present — the build panel flagged
a major plus several minors in each of build's three dimensions on this same artifact.
Analyze is under-detecting, not hallucinating, and it is spending more tokens than ever
(13,789) to do it. That points at prompt steering toward narrative over enumeration.

## A judge finding that was simply false

analyze k3 priced `defect_detection` at 0 on a *blocking* finding: an "unescaped-quote
syntax error in the INS-007 seed" that analyze had certified clear. `node --check` on
the artifact's only script block passes. The defect does not exist. k3's 45.1 is
understated and it is the sole reason analyze's spread is 18.9.

Judges raise confident false mechanical claims. Verify before acting.

## plan is trapped between two rubric dimensions

plan k1 priced a **blocking** `task_self_containment` failure (29/100) for deferring all
12 application and 7 inspection records to `spec.md`. That deferral is the direct result
of the v6 cite-`spec.md`-don't-copy rule, which was introduced to stop plan truncating.

- Copy the data inline -> plan truncates, `page_coverage` collapses.
- Cite `spec.md` -> `task_self_containment` takes a 45-point blocking hit.

v10 sits on the citing side. This is the likely cause of plan's violent cross-run range
(12.6 to 81.2) — it is not sampling noise, it is which of two failures the run lands in.
A prompt that emits the records once, compactly, in the task that needs them is the
obvious third option and has not been tried.

## Standing

| run | thinking | mean |
|---|---|---|
| c7 | no | 62.1 |
| c8 | no | 49.0 |
| c9 | yes | 63.1 |
| c10 | yes | 67.5 |

Two thinking runs (63.1, 67.5) both sit above both no-thinking runs (49.0, 62.1).
Cycle 11 pending for the third.

Caveat that must travel with these numbers: validate contributes a fifth of every mean
above and its largest-weighted judged dimension was measured blind throughout, so the
thinking-vs-not comparison is cleaner on specify/plan/analyze/build than on the mean.
