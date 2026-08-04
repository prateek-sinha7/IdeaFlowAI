# Baseline — v2 prompts, permits brief, opus sub-agent panel

Run: `260803-182408-prototype_aws_3_permits` (judged as `…-opusjudge`)
Prompts: **v2** (specify hash `sha256:b82864e1…`)
Instrument: opus sub-agent panel via `JUDGE.md` — one fresh judge per stage.

Every cycle in this folder is judged by this same instrument, so all deltas
against this table are valid comparisons.

## Scores

| stage | score | sub-scores |
|---|---|---|
| specify | 46.2 | data_realism 74, brief_intent_match 60, design_system_coherence 74, **spec_consistency_completeness 7**, interaction_specification 24 |
| plan | 46.4 | page_coverage 82, **task_self_containment 17**, build_order_coherence 34 |
| analyze | 46.5 | cross_artifact_grounding 56, **defect_detection 16**, verdict_coherence 74 |
| build | 39.3 | data_realism 52, **page_completeness 0**, visual_coherence 74 |
| validate | 18.4 | **page_completeness 0**, **defect_repair_delta 0**, token_and_chrome_consistency 92 |
| **mean** | **39.4** | |

## Deterministic checks

| stage | rows_ok / rows_checked |
|---|---|
| build | **0 / 1** |
| validate | **0 / 1** |

Both regressed from v1's 1/1. Judge-independent, so this is the single most
trustworthy signal in the baseline.

## Mechanical metrics

| metric | build.html | validate.html |
|---|---|---|
| bytes | 80 571 | 80 563 |
| sections | 6 | 6 |
| thin sections | 1 (`review-queues`) | 1 (`review-queues`) |
| colour literals outside `:root` | 7 | 7 |
| `alert()` | 0 | 0 |
| JS functions | 6 | 6 |

Output tokens: specify 14 470 · plan 11 548 · analyze 5 548 · build 40 524 ·
validate 6 912.

Note validate's 6 912 output tokens against build's 40 524, and the two files
differing by 8 bytes. That is the numeric shape of `defect_repair_delta = 0`:
the stage read the file and changed essentially nothing.

## The four defects targeted in cycle 1

All structural, none domain-specific, all confirmed by the panel against the artifact.

1. **Seed state does not satisfy its own predicate.** `filters: { type: "All
   types" }` tested by `filters.type === "" || filters.type === app.type` — the
   default landing page renders zero rows. `blocking`, survived validate.
2. **Parameterised route unreachable.** `#/application/{id}` matched against the
   whole hash, so no section is found and every detail link opens blank.
   `blocking`, survived validate. *(Genuinely broken — not the `checks.py`
   first-segment false positive; the panel confirmed a blank render.)*
3. **validate repaired nothing.** `defect_repair_delta` **0**; the diff touches
   one HTML attribute and one relocated listener.
4. **specify shipped its own deliberation.** Three irreconcilable Fees summary
   card sets as spec text (`$8,742,500` / `$8,188,000` / a "Card 3b
   (alternative)"), plus the asserted total `$8,188,000` against an actual
   itemisation of `$8,148,000`. v2 already carried a "no competing candidate
   values" rule, so by `ADVISE.md` §2 **that rule did not land** and required a
   cause-level rewrite rather than restatement.

Supporting sub-defects also used: fields written but never created in the store
(`appState.inspections`), tasks deferring content to "the spec" instead of
specifying it, runtime-generated badge class names with no CSS rule, and a
terminal stage whose action button is undefined.
