# Why the scores aren't moving — findings, 2026-08-03

Research pass over the 15 run folders in `.runs/`, the v1→v2 prompt sweep, and the
advice pool. Everything below is derived mechanically from the run store; nothing is
inferred from a judge's prose.

**Headline: the v2 prompt sweep *did* work on the things it targeted. You cannot see it
because every "before vs after" number you have been reading compares two different
judging instruments.**

---

## 1. The runs, correctly classified

`system_prompt_hash` on the specify row separates the two prompt generations cleanly:
`sha256:d0362e2a…` = v1/canonical, `sha256:b82864e1…` = v2.

| run | prompts | judge | method |
|---|---|---|---|
| `260803-155235-*` ×3 | **v1** | bedrock `claude-haiku-4-5` | API judge |
| `260803-160333-*` ×3 | **v1** | `mistral-large-latest` | API judge |
| `260803-162918/162919-*` ×3 | **v1** | opus | **single-threaded** (`OPUS_JUDGE.md`) |
| `260803-175841-…fraud_review-opusjudge` | **v2** | opus | **single-threaded** |
| `260803-175841-…fraud_review-subagent-opusjudge` | **v2** | — | **no `judge.json` — never finished** |
| `260803-180943-…reservations` | **v2** | mistral | API judge |
| `260803-180943-…reservations-opusjudge` | **v2** | opus | **sub-agent panel** (`JUDGE.md`) |
| `260803-182408-…permits-opusjudge` | **v2** | opus | **sub-agent panel** |
| `260803-182408-…permits` | **v2** | — | no `judge.json` |

### The valid before/after pairs are only these two

Same judge, same method, same brief — everything else is noise across instruments:

**Mistral × reservations**

| stage | v1 | v2 | Δ |
|---|---|---|---|
| specify | 92.8 | 93.0 | +0.2 |
| plan | 96.8 | 96.8 | 0 |
| analyze | 91.3 | 91.3 | 0 |
| build | 90.4 | **59.8** | **−30.6** |
| validate | 90.5 | 96.8 | +6.3 |

**Opus single-threaded × fraud_review**

| stage | v1 | v2 | Δ |
|---|---|---|---|
| specify | 38.45 | 70.7 | **+32.3** |
| plan | 48.8 | 89.6 | **+40.8** |
| analyze | 39.1 | 77.5 | **+38.4** |
| build | 33.0 | 72.8 | **+39.8** |
| validate | 11.2 | 93.4 | **+82.2** |

That is a **+47 average improvement**, on the only stage-complete same-instrument pair
that exists. There is **no v1 baseline at all for the opus sub-agent panel**, which is
the instrument that produced the low numbers (24–49) you have been reading as "still
red". Those numbers have never been compared to anything.

**The `-subagent-opusjudge` clone of the v2 fraud_review run has no `judge.json`** — the
one run that would have given the sub-agent panel a matched pair was started and never
finished.

## 2. The judges disagree more than the prompt change does

Three judges, byte-identical v1 fraud_review artifacts (md5-verified):

| stage | bedrock-haiku | mistral | opus-single |
|---|---|---|---|
| specify | 49.45 | 95.4 | 38.45 |
| plan | 43.2 | 81.6 | 48.8 |
| analyze | 49.2 | 94.6 | 39.1 |
| build | **87.1** | **91.4** | **33.0** |
| validate | **75.35** | **96.8** | **11.2** |

Spread on identical bytes: **58 points on build, 86 on validate.** Any prompt effect is
buried unless the instrument is held fixed.

Mistral is additionally **saturated** — it returned *identical* scores (96.8 plan, 91.3
analyze) on reservations for two runs whose artifacts have different md5s and differ by
47 KB. It is not measuring; it is awarding a house number in the low 90s. Do not use it
for deltas.

## 3. The judge-independent evidence: v2 worked

Measured directly off `artifacts/build.html` — no judge involved.

| metric | fraud v1→v2 | reservations v1→v2 | permits v1→v2 |
|---|---|---|---|
| colour literals outside `:root` | 20 → **8** | 28 → **2** | 37 → **7** |
| `alert()` calls | 0 → 0 | 0 → 0 | 8 → **0** |
| thin/empty `<section data-page>` | 0 → 0 | 3 → **6** | 3 → **1** |
| deterministic checks (build) | 0/1 → 0/1 | 1/1 → 1/1 | 1/1 → **0/1** |
| build `tokens_out` | 20 807 → 27 031 | 23 394 → **8 765** | 25 295 → **40 524** |

The two cause-level fixes recorded in `APPLIED.md` — *tint tokens* and *`alert()` is not
an implementation* — **landed hard and unambiguously**: literals fell 60–93 %, `alert()`
went to zero. Those were the two rules written against a mechanism rather than restated
louder, and they are the two that moved.

Section completeness went the other way on reservations, for the reason in §4.

## 4. The real ceiling: the eval measures a code path production never runs

`prototype-build.v2.md` opens with:

> You run as an **isolated per-task sub-agent**: a fresh invocation for a single task…
> The engine calls you once per task… Read `=== CURRENT TASK ===`

That is production (`ExecutionEngine._run_build_task_loop`, one sub-agent per task).
**The eval never does this.** `run.py::_dispatch_row_async` makes exactly **one**
`runner.astream_events` call per stage. No `=== CURRENT TASK ===` block is ever
injected, so build falls into its own fallback branch:

> **If `=== CURRENT TASK ===` is empty or absent:** Read `spec.md` and build a complete
> `prototype.html` from scratch following ALL pages in the spec.

Consequences, all confirmed:

1. **One-shot whole-document emission.** A 6-page, 80 KB prototype must come out of a
   single `write_file` call — ~22–25 k output tokens in one assistant message against
   `MAX_OUTPUT_TOKENS = 32768`. permits spent **40 524** output tokens on build; that is
   over the single-call cap, so it took several calls and was already fighting the
   ceiling. reservations spent **8 765** and quit — it wrote a shell and stopped, which
   is exactly the 22 KB artifact with **6 of 6 sections thin**.
2. **`design.md` is never seeded.** The config's `seed_as` writes only `spec.md`,
   `tasks.md`, `analysis.md`. Build's step 2 — `read_file("design.md")` — fails on every
   eval run. The prompt spends a paragraph on TEMPLATE SEED / blank-canvas branching that
   can only ever take the blank-canvas branch.
3. **Roughly half of a 15 856-char system prompt is inapplicable** — the per-task loop
   protocol, the golden rule ("NEVER rebuild from scratch"), the scope rule ("never
   expand beyond your task"), the `edit_file`-only instruction for tasks ≥2. In one-shot
   mode these are at best dead weight competing for attention, and at worst actively
   contradictory: the prompt tells the model both *"execute ONLY that task, nothing
   else"* and *"build ALL pages in the spec"*.

**This is the single largest thing missing on our end.** Any prompt tuning done against
eval scores is being tuned against a dispatch mode production doesn't use, on a prompt
whose majority is addressed to a mode the eval doesn't use.

## 5. The advice pool gives no generality signal at all

`prompts/advices.json`, rebuilt 17:32 today from 9 run dirs:

| stage | entries | count distribution |
|---|---|---|
| specify | 52 | **all count=1** |
| plan | 39 | **all count=1** |
| analyze | 28 | **all count=1** |
| build | 19 | **all count=1** |
| validate | 11 | **all count=1** |
| **total** | **149** | **0 entries span more than one run** |

Two independent causes:

- The pool clusters by **exact string**. The same defect phrased three ways is three
  count-1 entries. `count`/`runs` can therefore never rise above 1 in practice, and
  `ADVISE_AND_PROMOTE.md` §2 tells you to use it as "your generality signal" — that
  instruction is unusable as written.
- The 9 "runs" are **3 briefs × 3 judges over byte-identical artifacts**. Distinct rows
  available: **3**. The pool is 3× redundant before clustering.

## 6. Model configuration

- Build/validate run on `eu.anthropic.claude-haiku-4-5-20251001-v1:0` via Bedrock.
- `THINKING_BUDGET_TOKENS = 0` → **extended thinking is off**. The plumbing exists
  (`model_factory.build_model` lines 66–72, 145–164) and is one env var away.
- `MAX_OUTPUT_TOKENS = 32768`.

So yes: the artifact producer is a small non-thinking model asked to emit a 6-page
document in one shot, ~70 % of the way to its own output ceiling.

---

## What this means for the loop

**Nothing is wrong with the prompt edits.** The two cause-level rules produced large,
verifiable mechanical improvements. What is broken is the *measurement* and the
*dispatch mode*:

| problem | fix |
|---|---|
| Cross-instrument comparison | Freeze one judge + one method. Every v2 run needs a v1 run judged the same way, or the delta is meaningless. |
| No v1 baseline for the sub-agent panel | Re-judge the three v1 runs with `JUDGE.md`, or stop reading the panel's v2 numbers as a regression. |
| Mistral saturates | Drop it from delta work; keep it only as a cheap smoke test. |
| Build prompt addresses the wrong mode | Either inject `=== CURRENT TASK ===` in the eval (measure what production runs), or give build a real one-shot branch instead of a fallback paragraph. |
| `design.md` never seeded | Add it to `seed_as`, or delete the branch from the prompt. |
| One-shot output cap | Page-at-a-time dispatch, or raise the cap, or accept thin sections as a ceiling artefact rather than a prompt defect. |
| Advice pool has no recurrence signal | Cluster semantically, not by exact string; count **distinct briefs**, not runs. |

### Prompt-shape question (non-thinking haiku)

The evidence in this pool is consistent and points one way. Of the rules that changed
between v1 and v2, the ones that moved a mechanical metric were the ones that named a
**decision procedure at the moment of the decision** —

> the moment you are about to write a colour literal anywhere outside `:root`, define a
> token instead

— and the ones that **replaced a satisfiable proxy with a property** —

> `alert()` is not an implementation … a control must read its own current value and
> re-render what it governs

Both give a non-thinking model something to check *while emitting the next token*. The
rules that did not move anything are the ones phrased as goals to be held in mind across
a whole document ("every page MUST have real tables ≥5 rows"), which is precisely what a
model with no scratchpad cannot do at 25 k tokens of output. That is a testable
hypothesis, not a conclusion — but it matches every data point here, and it argues for
**structural scaffolding over more prose**: fewer, shorter rules; per-page emission so
the checklist applies to a 3 KB unit instead of an 80 KB one; and a fill-in-the-blank
output skeleton rather than remembered constraints.
