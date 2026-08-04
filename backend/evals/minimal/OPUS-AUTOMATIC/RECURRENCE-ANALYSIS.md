# Cross-run defect recurrence — 6 runs, same brief, same instrument

Every `judge.json` from the baseline through cycle 5, all on `aws_3_permits`, all
scored by the opus sub-agent panel. This is the generality signal `advices.json`
structurally cannot give: its 149 entries are all `count: 1` because it clusters by
exact string.

**Method caveat, stated up front.** Findings are clustered by regex over the
finding text against 13 hand-written defect signatures drawn from defects actually
observed in these runs. Patterns overlap — "renders an empty table" matches both
*empty/thin section* and *filter empty-state* — so column totals are indicative,
not exact. The **run-count** column (how many of six runs contain the class at
all) is robust; the per-run counts are not precise. Six runs of **one brief**, so
"appears in all six" means systematic *for this brief*, not proven cross-domain.

## Recurrence table

| defect class | base | c1 | c2 | c3 | c4 | c5 | runs |
|---|---|---|---|---|---|---|---|
| empty/thin section or unrendered page | 17 | 14 | 15 | 11 | 10 | 14 | **6** |
| arithmetic: asserted total ≠ sum of its rows | 6 | 8 | 4 | 5 | 7 | 6 | **6** |
| membership: entity in 2 groups or in none | 3 | 3 | 6 | 7 | 6 | 5 | **6** |
| false/unearned Clear, or fabricated finding | 4 | 4 | 7 | 2 | 5 | 8 | **6** |
| colour literal outside `:root` | 3 | 5 | 3 | 3 | 5 | 4 | **6** |
| filter/empty-state: zero matches mishandled | 2 | 1 | 2 | 1 | 2 | 3 | **6** |
| inert control: rendered, no handler | 2 | 1 | 5 | 1 | 0 | 3 | 5 |
| spec ships deliberation / superseded figures | 4 | 0 | 3 | 1 | 1 | 1 | 5 |
| JS serialised into an HTML attribute | 0 | 0 | 4 | 2 | 1 | 2 | 4 |
| undeclared CSS class used at runtime | 5 | 3 | 0 | 0 | 1 | 4 | 4 |
| generated data (`Math.random`/index arithmetic) | 0 | 4 | 5 | 0 | 1 | 4 | 4 |
| no validation task / plan incomplete | 0 | 1 | 0 | 2 | 1 | 1 | 4 |
| detail data seeded for 1 of N entities | 0 | 1 | 2 | 0 | 0 | 2 | 3 |

## Volume and severity

| run | findings | blocking | major | minor | **total cost** |
|---|---|---|---|---|---|
| base (v2) | 68 | 8 | 28 | 32 | **992** |
| c1 (v3) | 71 | 4 | 26 | 41 | 812 |
| c2 (v4) | 61 | 7 | 24 | 30 | 867 |
| c3 (v5) | 67 | 3 | 27 | 37 | 769 |
| c4 (v6) | 67 | 7 | 22 | 38 | 863 |
| c5 (v7) | 81 | **1** | 36 | 44 | 869 |

## What this says

**1. Six defect classes have survived every prompt generation, and not one is
trending down.** Empty/thin sections, arithmetic, membership, unearned Clears,
colour literals and empty-state handling appear in all six runs at roughly
constant rates. Five prompt generations of cause-level rules have not eliminated a
single recurring class.

**2. Total defect cost is flat.** 992 → 812 → 867 → 769 → 863 → 869. Cycle 1 took
out ~180 points of cost; nothing since has moved it. The mean score's apparent
climb to 61.3 and fall to 48.0 happens *inside* a constant defect volume — it is
severity tagging and per-stage weighting moving, not the artifact getting better.

**3. What genuinely improved is severity, not quantity.** Blocking findings
8 → 1 while total findings went 68 → 81. The prompts have been converting
catastrophic defects into cosmetic ones. That is real and worth having — a
prototype with 81 minor problems is usable and one with 8 blocking ones is not —
but it is a different claim from "the prototypes are getting better", and the
score does not distinguish them.

**4. Three classes were *introduced* by my own edits.** `Math.random`/index-
generated data (0 at baseline, 4–5 in c1/c2/c5), JS-in-attribute (0 at baseline,
peaking at 4 in c2) and "no validation task" (0 at baseline) did not exist before
this loop. Rules that told the plan to bound its dataset and the build to be
economical pushed both agents toward generating data and skipping the final task.
Each was then fixed by a later rule — but they were self-inflicted, and they cost
cycles.

**5. The dominant defect is the one least addressed.** Empty/thin sections is the
largest class in every single run (10–17 findings) and has moved least. Its root
is not prompt wording: build one-shots six pages against a 32 768-token cap in a
prompt written for a per-task loop the eval never invokes. **This is where the
remaining points are, and it is not reachable from the prompt files.**

## Recommendation

Stop tuning specify/plan/analyze — their classes are flat and their weight in the
mean is already earned. The remaining leverage, in order:

1. **Inject `=== CURRENT TASK ===` in the eval** so build renders one page per
   call instead of seven in one breath. Directly attacks the largest defect class.
   *(Harness change — out of `ADVISE.md` scope, needs your go-ahead.)*
2. **Enable thinking** (`THINKING_BUDGET_TOKENS`, currently 0). The three
   arithmetic/membership/unearned-Clear classes are all "hold several facts and
   compare them" work — exactly what a scratchpad buys. One env var.
3. **Judge with K=3 medians** before trusting any further delta (see
   `VARIANCE-TEST.md`).
