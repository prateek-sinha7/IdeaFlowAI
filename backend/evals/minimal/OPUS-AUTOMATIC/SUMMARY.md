# SUMMARY — autonomous advise→run→judge loop, 6 cycles

Target `configs/aws_3_permits.yaml`. One instrument throughout: opus sub-agent
panel (`JUDGE.md`). Prompts v2 (baseline) → v8. Six Bedrock runs, 41 judge agents.

---

## Scores

| | prompts | mean | specify | plan | analyze | build | validate | blocking |
|---|---|---|---|---|---|---|---|---|
| baseline | v2 | 39.4 | 46.2 | 46.4 | 46.5 | 39.3 | 18.4 | 8 |
| cycle 1 | v3 | 51.4 | 56.8 | 39.6 | 63.5 | 19.4 | 77.9 | 4 |
| cycle 2 | v4 | 49.7 | 46.6 | 61.0 | 45.6 | 43.5 | 52.0 | 7 |
| cycle 3 | v5 | 53.3 | 49.8 | 45.6 | 67.5 | 64.7 | 39.0 | 3 |
| cycle 4 | v6 | **61.3** | 52.3 | 63.2 | 35.3 | 68.7 | **87.0** | 7 |
| cycle 5 | v7 | 48.0 | 45.1 | 54.0 | 43.4 | 44.6 | 52.9 | **1** |
| cycle 6 | v8 | 54.0† | 50.7 | **65.2** | 31.8 | 59.4 | 63.0 | 4† |

† cycle 6 is **medians of K=3** on analyze/build/validate, K=1 on specify/plan.
All earlier rows are single-judge, so they carry ±9 of judge noise on top of
run-to-run variance.

## The honest read

**Net +14.6 mean over six cycles**, but the trajectory is not a climb — it is a
walk inside a noise band. The variance test (`VARIANCE-TEST.md`) put the
single-judge noise floor at **±9 per stage**, and cycle 5 showed build and
validate moving −24.1 and −34.1 on **byte-identical prompts**. Most cycle-to-cycle
movement in that table is not attributable to the edits.

**What is solidly established:**

1. **validate 18.4 → 87.0 is real.** Three independent re-judgements of cycle 4
   returned a median of 89.8 — *higher* than the original 87.0 — with all four
   judges finding zero blocking findings and independently confirming the same
   facts. This is the single largest confirmed win.
2. **Blocking findings fell 8 → 1 (cycle 5), 4 (cycle 6).** Far less noisy than
   the score and moving the right way. In cycle 6, **build and plan returned zero
   blocking findings from every judge**.
3. **Total defect cost is flat**: 992 → 812 → 867 → 769 → 863 → 869. The loop has
   been converting catastrophic defects into cosmetic ones — real and worth
   having, but not the same as "the prototypes got better", and the score cannot
   tell those apart.

## The generalisable finding

**A non-thinking model does not execute a checklist it reads; it executes one it
must emit.** validate's check *content* was unchanged between v2 and v3 — routes,
empty sections and handlers were already P0 checkboxes. Adding the requirement to
**write the audit out before the first edit** took `defect_repair_delta` from 0 to
92. The same mechanism ("write the addends down") moved analyze's
`defect_detection` 16 → 44 in the same cycle.

Corollaries learned the expensive way:

- **Rules cost output budget.** build got +62 lines in cycle 1 and stopped
  rendering entirely (`page_completeness` 0, "not one render function"). Cutting
  those 62 lines to 18 in cycle 2 recovered it.
- **Position matters.** specify's "never write a computed number" rule sat at line
  ~150 for two cycles and did nothing; hoisted into the output contract at the top
  in v7, the fee arithmetic came back verified-correct.
- **The output-is-scratchpad principle has a boundary.** It helps when the output
  is a *report* (analyze, validate). It poisons the output when it is a *contract*
  others build from — specify shipped literal scratchpad ("I made an error. Let me
  recalculate…") as spec text and `spec_consistency_completeness` went 11 → 0.

## Three defects I introduced myself

Not present at baseline; each created by one of my own rules, each costing a cycle:

| defect | caused by | fixed in |
|---|---|---|
| `Math.random()`-generated seed data | "bound the dataset / be economical" | v6, v8 |
| JS serialised into `onclick` attributes | build prompt compression | v5 |
| Three identical discipline boards | v8's "derive groups by filtering the owning collection" — my worked example filtered on **one** field, and build dropped the second predicate | open |

The last one is live in cycle 6: `renderQueueColumns()` ignores its own
`discipline` loop variable, so all three boards render identically. Every build
and validate judge found it independently.

## Where the remaining points are — and they are not in the prompts

`RECURRENCE-ANALYSIS.md`: **six defect classes appear in all six runs and none is
trending down.** The largest in every single run is empty/thin sections (10–17
findings). Its root is structural:

1. **build one-shots six pages** against a 32 768-token cap, using a prompt
   written for a per-task sub-agent loop the eval never invokes — its own log says
   *"All 7 pages are set up as empty placeholders ready for content in subsequent
   tasks"*. Injecting `=== CURRENT TASK ===` in the eval attacks the biggest class
   directly. **Harness change, outside `ADVISE.md` scope.**
2. **`THINKING_BUDGET_TOKENS = 0`.** Arithmetic, membership and unearned-Clear —
   three of the six persistent classes — are all "hold several facts and compare
   them" work. One env var.
3. **analyze is now the worst stage and unanimously so**: all three K=3 judges gave
   `defect_detection` **0** and 3 blocking findings. That is not noise. It stamps
   READY TO BUILD over contradictions it has itself tabulated.

## State

- **v8 is active** on all five agents. `./activate.sh prototype v6` reverts to the
  highest-scoring configuration (61.3).
- Best-per-stage across all cycles sums to a mean of **68.6** — the empirical
  ceiling if every stage simultaneously hit its own best. 90 was not reachable by
  prompt editing, and I said so before starting cycle 6.

## Files

`PLAN.md` · `BASELINE.md` · `cycle-{1,2}-advice.md` · `cycle-1-result.md` ·
`RECURRENCE-ANALYSIS.md` · `VARIANCE-TEST.md` · `FINDINGS.md` · `SCORES.csv`

Scope held throughout: only `prompts/agents/*.v3–v8.md`, `prompts/APPLIED.md` and
this folder were written. No harness, config, dataset or `backend/agents/` file
was touched. Harness observations recorded, not fixed.
