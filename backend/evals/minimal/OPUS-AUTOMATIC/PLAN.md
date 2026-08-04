# OPUS-AUTOMATIC — autonomous advise→run→judge loop, 3 cycles

Written 2026-08-03 19:0x, before execution. This is the contract for the run;
every later file in this folder reports against it.

---

## The loop

Three cycles of:

1. **Advise** — pool advice + read the previous cycle's opus findings, generalise
   per `ADVISE.md`, write the next prompt version, activate it.
2. **Run** — dispatch the target brief on Bedrock. **No judge**, no `--advise`.
3. **Judge** — score that run with `JUDGE.md` (opus, one fresh sub-agent per stage).
4. **Log** — diff against the previous cycle and the baseline; write findings.
5. **Repeat.**

## Target and baseline

**Brief: `configs/aws_3_permits.yaml`** — the lowest-scoring use case.

Baseline is run `260803-182408-prototype_aws_3_permits-opusjudge` (v2 prompts,
opus sub-agent panel). It is the **instrument-matched** baseline: same brief,
same judge model, same judging method. Every cycle below is judged identically,
so the comparison is valid — which is precisely what was missing from the
previous rounds (see `../RESEARCH_WHY_NO_IMPROVEMENT.md` §1).

| stage | baseline score | worst sub-dimension |
|---|---|---|
| specify | 46.2 | `spec_consistency_completeness` **7** |
| plan | 46.4 | `task_self_containment` **17** |
| analyze | 46.5 | `defect_detection` **16** |
| build | 39.3 | `page_completeness` **0** |
| validate | 18.4 | `page_completeness` **0**, `defect_repair_delta` **0** |
| **mean** | **39.4** | |

Deterministic checks at baseline: **build 0/1, validate 0/1** (both regressed
from v1's 1/1 — a real regression, not judge noise).

## What the baseline findings actually say

The four defects worth attacking first, all verified by the panel against the
artifact, all structural rather than domain-specific:

1. **Seed state does not satisfy its own predicate.** `filters: { type: "All
   types" }` against `filters.type === "" || filters.type === app.type` — the
   default landing page renders zero rows. Blocking, and it survived validate.
2. **Parameterised route unreachable.** `#/application/{id}` routed against a
   section named `application-detail`; the router matches the whole hash, so
   every detail link lands on a blank screen. Blocking, and it survived validate.
   *(Note: this is genuinely broken — not the `checks.py` first-segment false
   positive documented in `ADVISE.md` §4a. The panel confirmed a blank render.)*
3. **validate repaired nothing.** `defect_repair_delta` **0** — the byte diff
   build→validate touches one HTML attribute and one relocated listener. Both
   P0s above passed straight through.
4. **specify shipped its own deliberation.** Three irreconcilable Fees card sets
   as spec text. v2 already has a "no competing candidate values" rule, so by
   `ADVISE.md` §2 **that rule did not land and must be rewritten at cause level,
   not restated.**

## Per-cycle commands

Versions: cycle 1 → **v3**, cycle 2 → **v4**, cycle 3 → **v5**.

```bash
cd backend/evals/minimal

# 1. advise — edit prompts/agents/<agent>.v<N>.md, then:
cd prompts && ./activate.sh prototype v<N> && ./activate.sh status && cd ..

# 2. run — Bedrock, NO judge (this is why eval.sh is not used: it always
#    calls `cli score`, which judges via Mistral)
cd /Users/bilala/Developer/Projects/VELOCITY-AI/backend
python3.11 -m evals.minimal.cli run evals/minimal/configs/aws_3_permits.yaml
python3.11 -m evals.minimal.cli checks <RUN_ID> --stage <each stage>

# 3. judge — follow ../JUDGE.md for <RUN_ID> (clone to -opusjudge, 5 sub-agents)

# 4. log — write this folder's cycle files
```

## Files this folder will contain

| file | contents |
|---|---|
| `PLAN.md` | this file |
| `BASELINE.md` | the v2 baseline: scores, checks, mechanical counts, full findings |
| `cycle-1-advice.md` … `cycle-3-advice.md` | rules applied, rejected, the distinct-brief support for each, line deltas |
| `cycle-1-result.md` … `cycle-3-result.md` | run id, tokens, deterministic checks, mechanical metrics, opus scores, delta vs baseline and vs previous cycle |
| `SCORES.csv` | one row per cycle per stage — the whole experiment in a table |
| `FINDINGS.md` | running log of everything learned, appended each cycle |
| `SUMMARY.md` | final report: what moved, what didn't, what to do next |

## Measurement rules I will hold to

- **One instrument only.** Every cycle judged by the opus sub-agent panel via
  `JUDGE.md`. No Mistral, no Bedrock-haiku judge, no single-threaded opus. Cross-
  instrument numbers are not quoted anywhere in this folder.
- **Judges are told nothing.** Per `JUDGE.md` §0 no sub-agent learns the version
  under test, what changed, what I expect, what another stage scored, or what the
  deterministic checks said. Fresh general-purpose agents, never forks of my context.
- **Mechanical metrics recorded every cycle** — colour literals outside `:root`,
  `alert()` count, thin sections, JS function count, deterministic checks. These
  don't drift and don't saturate, and they carry the per-stage attribution that
  the score sweep loses.
- **n=1, noise floor ±4.** A single judge per stage gives a point, not a range. I
  will not call a movement under ~4 points real, and I will say so in the report
  rather than dressing up noise.

## Known limitation, stated up front

I sweep **all five agents each cycle**, because moving the aggregate in three
cycles is the goal. Stages feed each other, so **score movement cannot be
attributed to a single stage's prompt edit**. The mechanical metrics partially
recover this (a colour-literal count moves only from the build prompt; a
`defect_repair_delta` moves only from validate). Wherever I attribute, I will say
which evidence carries it.

## Scope — what I will not touch

Per `ADVISE.md` §0 and §9, the only files I edit are:

- `prompts/agents/<agent-id>.v3|v4|v5.md`
- `prompts/APPLIED.md`
- everything inside `OPUS-AUTOMATIC/`

**No changes to** `run.py`, `judge.py`, `cli.py`, `checks.py`, `eval.sh`, the
configs, the datasets, or anything under `backend/agents/`. If I find a harness
defect I write it in `FINDINGS.md` and leave it alone. Frontmatter of every new
version file is verified byte-identical to its parent before activation.

## Cost, time, failure handling

- ~5 Bedrock stages per cycle on `claude-haiku-4-5`; the v2 permits run spent
  ~78 k output tokens total. Three cycles is single-digit dollars.
- Estimated 20–30 min per cycle, 60–90 min overall.
- A stage that errors: retry the cycle's run **once**, then log the failure in
  `FINDINGS.md` and continue to the judge with whatever completed. A run where
  every stage errors ends the cycle and is reported, not silently retried.
- Final state of `activate.sh` will be **v5 active** unless a cycle regresses
  badly, in which case I leave the best-scoring version active and say so.

## Success criterion

Mean opus panel score across the five stages, judged by the same instrument,
against the 39.4 baseline — plus the deterministic checks returning to 1/1 on
build and validate, which is the outcome that does not depend on a judge at all.
