# Cycle 11 — v10 + thinking, run 3 of 3

Run: `260804-024305-prototype_aws_3_permits`
Judged: `260804-025349-prototype_aws_3_permits-opusjudge`
Prompts unchanged from cycles 9-10 (v10, all five overrides verified byte-identical).
`THINKING_BUDGET_TOKENS=10000`.

## Scores

| stage | judges | median | spread |
|---|---|---|---|
| specify | 65.6 | **65.6** | K=1 |
| plan | 55.6 | **55.6** | K=1 |
| analyze | 58.8 / 60.2 / 61.4 | **60.2** | 2.6 |
| build | 54.7 / 57.9 / 66.5 | **57.9** | 11.8 |
| validate | 84.5 / 87.0 / 88.4 | **87.0** | 3.9 |
| **mean** | | **65.3** | |

## TWO INSTRUMENT CHANGES — the comparability seam is here

Cycle 11 is the first run judged with a corrected instrument. Both changes were made
in response to cycle 10's findings, and both are changes to the *judge dispatch*, not
to any prompt or any harness file.

1. **Validate judges are told the prior artifact is missing from their prompt and are
   instructed to recover it** from the sibling `judge_prompts/build.txt` and diff it.
   `defect_repair_delta` is therefore scored on measured evidence for the first time.
2. **All judges are instructed to verify mechanical claims** (syntax errors, dead
   links, undefined variables) against the actual text before tagging them. This
   answers cycle 10's fabricated "blocking unescaped-quote syntax error", which
   `node --check` disproved and which alone cost analyze 12.8 points of median.

Consequence: cycle 11's validate and analyze numbers are **more correct but not
directly comparable** to cycles 7-10. Treat cycle 11 as the first point of a new,
trustworthy series rather than the third point of the old one.

## The instrument fix is the result

| stage | c10 spread | c11 spread | change |
|---|---|---|---|
| analyze | 18.9 | **2.6** | 7.3x tighter |
| validate | 22.6 | **3.9** | 5.8x tighter |
| build | 5.6 | 11.8 | wider |

`defect_repair_delta`, the same dimension, on comparable artifacts:

| run | judges' scores | basis |
|---|---|---|
| c10 | 56 / 56 / 19 | blind — no prior artifact in the prompt |
| c11 | 96 / 96 / 92 | measured — judges diffed against build.txt |

Analyze and validate tightened where judges make *verifiable mechanical* claims.
Build widened, and build is where the disagreement is inherently subjective —
`data_realism` ranged 38 to 70 across three judges on identical bytes. The fix works
on falsifiable claims and does nothing for taste. That boundary is worth remembering
before trying to drive build's variance down the same way.

## The pipeline caught and repaired its own defect

This is the first run in the series where the five stages behaved as a pipeline
rather than five independent scores.

| | c10 | c11 |
|---|---|---|
| build render gate | PASS | **FAIL** (1/5 nav links dead) |
| build median | 71.0 | 57.9 |
| validate edits | none (byte-identical) | **11 lines, 3 hunks** |
| validate median | 70.5 (blind) | 87.0 (measured) |
| gate after validate | — | **PASS** |

Build shipped three real defects. Validate found and fixed all three, regressing
nothing:

```diff
-    .section {                →  +    .page {              # dead selector: sections
-    .section.is-active {      →  +    .page.is-active {    # carry class="page", so
                                                            # pre-fix ALL SIX pages
                                                            # rendered stacked
-  <a href="#/queues" ...>     →  +  <a href="#/review-queues" ...>   # dead route

+  if (payload.page === "application-detail" && payload.applicationId) {
+    window.location.hash = "#/application/" + payload.applicationId;
+  } else { window.location.hash = "#/" + payload.page; }   # brief's #/application/:id
```

The third hunk implements the exact requirement cycle 10's judges flagged as
"never implemented". All three validate judges independently produced the same
account of the same three hunks.

**Revision to cycle 10's write-up:** I concluded there that validate might be a
passthrough stage banking 65% of its weight for free. That reading was wrong.
Cycle 10's validate did nothing because it received a cleaner artifact; cycle 11's
did substantial work when there was work to do. Cycle 9's 85.3 now looks plausible
rather than suspect — though it was still measured blind and cannot be verified
retroactively.

## Stage findings that persist

**plan — trapped between two rubric dimensions, second confirmation.**

| dimension | c10 | c11 |
|---|---|---|
| page_coverage | 100 | 96 |
| task_self_containment | **29** | **15** |
| build_order_coherence | 78 | 56 |

c11 judge: "all seed data deferred to spec.md — no permit number, address or valuation
anywhere". That deferral is the v6 cite-`spec.md`-don't-copy rule, which was introduced
to stop plan truncating and now reliably draws a blocking self-containment finding.
Copy inline -> truncation kills `page_coverage`. Cite -> `task_self_containment`
collapses. Untried third option: emit the records once, compactly, in the single task
that needs them.

**analyze — under-detection is stable and is not a verbosity problem.**

| dimension | c10 (3 judges) | c11 (3 judges) |
|---|---|---|
| cross_artifact_grounding | 64-78 | 74-78 |
| defect_detection | **0-25** | **29-38** |
| verdict_coherence | 78-96 | 64-82 |

Six judges across two runs agree. The c11 report was 40% shorter (10,875 vs 17,856
chars) and detection did not improve materially — so length is not the lever. Analyze
writes a grounded, coherent report and does not enumerate defects. Detection did rise
somewhat once judges stopped inventing findings, which suggests part of c10's 0-25 was
instrument, not artifact.

**specify — same two weak dimensions every run.** `spec_consistency_completeness` 44
and `interaction_specification` 52. New catch this run: absolute seed dates break the
today-relative "days in stage" and "Completed This Month" figures, a data-modelling
defect that propagates into every downstream stage.

## Standing across the series

| cycle | prompts | thinking | mean | instrument |
|---|---|---|---|---|
| 7 | v10 | no | 62.1 | blind validate, unguarded judges |
| 8 | v10 | no | 49.0 | blind validate, unguarded judges |
| 9 | v10 | yes | 63.1 | blind validate, unguarded judges |
| 10 | v10 | yes | 67.5 | blind validate, unguarded judges |
| 11 | v10 | yes | 65.3 | **corrected** |

Thinking arm: 63.1, 67.5, 65.3 (mean 65.3, range 4.4).
No-thinking arm: 62.1, 49.0 (mean 55.6, range 13.1).

All three thinking runs land above both no-thinking runs, and the thinking arm's range
is a third of the control's. On this evidence thinking helps, and helps most by
reducing run-to-run collapse — cycle 8's 49.0, driven by plan emitting a single task,
has no counterpart in the thinking arm.

Caveat that must travel with these means: cycles 7-10 include validate numbers measured
through a broken instrument, so the arm comparison is sounder on specify/plan/analyze/
build than on the means themselves.
