# Outstanding — product decisions awaiting an answer

Open questions that need a **product judgement**, not an engineering fix. Each one is
something I deliberately did *not* decide, because deciding it silently would change what a
score means or what the eval is measuring.

Engineering defects do not belong here — those get fixed. This is for "what should the
behaviour be?", where the answer is yours.

**Format:** each item states the question, the evidence, the options, and my recommendation.
When you answer one, record the decision inline and move it to *Decided* at the bottom.

| # | Question | Blocks |
|---|---|---|
| [1](#1-the-negative-test-row-cannot-fail-a-structural-precheck) | Should a vague brief be refused, or invented from? | the `negative` metric |
| ~~2~~ | ~~Which judge is the reference?~~ | **DECIDED — mistral-large** |
| [3](#3-should-agents-be-graded-with-the-real-design-system-attached) | Grade with real template/design-system injection? | what specify/build scores mean |
| [4](#4-when-is-a-score-a-measurement-repeats) | How many repeats before trusting a delta? | cost vs. confidence |
| [5](#5-onboarding-order-for-stages-25) | Which stage next? | coverage beyond stage 1 |
| [6](#6-the-judges-resolution-depends-on-the-dataset) | What should 70 and 50 actually mean? | whether any score is a measurement |
| [7](#7-nothing-acts-on-the-analysers-verdict) | Should a "NEEDS REVISION" stop the run? | what stages 4-5 are even measuring |

---

## 1. The negative-test row cannot fail a structural precheck

**Status:** open · **Raised:** 2026-07-29 from run `260729-172444-ten-industries`

### The question
`prototype-specify` is given the brief **"Build me an app."** Should it refuse / ask for
detail, or invent a plausible product? Today it invents, confidently.

### The evidence
That four-word brief produced **16,506 characters** of impeccably structured spec:

```
# Prototype Specification: ShipShape — SaaS Analytics & Issue Tracker
### Dashboard   ### Issues   ### Issue Detail
### Analytics   ### Team     ### Settings
```

The dataset row is marked `expect: fail`, so it is supposed to be rejected. It was not —
because every precheck rule passed: wrapper ✅, 6 sections ≥ 4 ✅, no forbidden patterns ✅,
all 5 nav routes cross-referenced ✅.

**The precheck is behaving correctly.** It is deliberately structure-only — a precheck that
guesses at quality produces false failures, which is exactly the bug that made the original
run reject 7 of 11 good specs. Invention is a *content* defect, not a *shape* defect, so no
structural rule can catch it.

The row therefore reports a permanent `negative 0/1`, which reads like a defect but is an
unsatisfiable expectation.

### Options
1. **Widen `expect: fail`** so a negative row counts as correct if it fails *either* gate —
   precheck **or** the judge threshold. A judged run could then catch it, since "does this
   serve the brief?" should score near zero when there is no brief. *(Smoke would still show
   `0/1`, honestly, because no judge runs there.)*
2. **Drop `expect: fail`** and let it be an ordinary row whose low `brief_intent_match` score
   carries the signal.
3. **Leave it** as a standing reminder and accept a permanent `0/1`.

### Recommendation
**Option 1.** It makes a negative test mean "this row should be rejected by *something*",
which is what you actually want. Small change to `scoring.evaluate_baseline`. Not done
unilaterally because widening a metric's definition makes past and future runs incomparable
without anyone noticing.

### Worth knowing either way
The containment guard worked: `underspecified_brief` was excluded from `output.json`, so the
fabricated spec never propagates to a downstream stage.

---

## 2. Which judge should the baseline be calibrated on?

**Status:** DECIDED 2026-07-29 — **mistral-large-latest**, pinned in every rubric.

### The decision
All five rubrics now pin `provider: mistral, model: mistral-large-latest`. The
`claude-sonnet-5` pin is gone.

### Why
The pin was **unreachable**: `ANTHROPIC_API_KEY` is empty and the Bedrock token is expired, so
`build_model` silently fell through the implicit chain. Worse, `build_model` only *honours*
`provider: mistral` — `anthropic` was never an instruction, only a no-op that happened to work
where a key existed. Every config therefore overrode it, and the override made
`judge_resolved_model_id != judge_pinned_model_id`, which is one of the refusal conditions. So
the pin bought nothing and cost **every baseline verdict**, permanently.

Mistral-large also has evidence behind it now: run `260729-182649` produced sub-scores
`[70, 85, 90]` with both resolution warnings silent — it discriminates. See
[item 6](#6-the-judges-resolution-depends-on-the-dataset) for where it still does not.

### What changed
- five rubrics repinned; configs already named the same model, so they now **agree** with the
  pin rather than override it,
- a test asserts every shipped rubric pins a provider `build_model` actually honours, so an
  unreachable pin fails the suite instead of surfacing as a permanent `REFUSED`.

### Still REFUSED, for the other reason
`baseline.set_from` is still prose, not a record of a calibration run. That is deliberate — see
item 6: do not calibrate until the judge's resolution is settled.

---

## 3. Should agents be graded with the real design system attached?

**Status:** open · **Recorded as** `known_gaps.od_context_not_populated` in `workflow.yaml`

### The question
Every prototype agent declares `injects: [template, design_system, ...]`, composed at runtime
from `AgentContext.od_context`. The grading driver never populates it, so **no agent is
currently graded with a real template or design system attached.** Scores reflect
no-template behaviour only.

### Why it is a product question
It changes what the eval measures. Grading without injection asks "can this agent invent a
coherent design system?"; grading with it asks "does this agent honour the one it was given?"
Those are different capabilities and the rubric's `design_system_coherence` dimension is
currently written for the first.

### Options
1. Populate `od_context` from a per-row field and rewrite that dimension for conformance.
2. Keep grading no-template mode, and cover injection separately.
3. Both, as two datasets against the same agent.

### Recommendation
Defer until stage-1 scores are trustworthy. It is a real gap, but chasing it before the judge
is calibrated means changing two variables at once.

---

## 4. When is a score a measurement? (`repeats`)

**Status:** open · **Affects:** every `compare`

### The question
All three configs ship `repeats: 1`. With no repeat data, `compare` reports
`unknown-variance` and **refuses to call any delta an improvement** — by design, because
reading noise as progress is the failure mode that looks most like success.

Turning that guard on costs 3× per run (`repeats: 3` ⇒ ~69 model calls for `full`).

### The question for you
Is the guard worth 3× on every calibration run, or only when you are about to act on a
prompt change?

### Recommendation
Keep `repeats: 1` for exploratory runs; set `repeats: 3` for the run you intend to compare
against. Cheapest path to a real noise band without paying for it continuously.

---

## 5. Onboarding order for stages 2–5

**Status:** open

### The question
Only `prototype-specify` is onboarded. `plan`, `analyze`, `build`, `validate` are declared in
`workflow.yaml` — including the analyze fan-in and build's adapter/seeding — but have no
rubric, hook or dataset.

### Trade-offs
- **`plan` next** is the cheapest: linear hop, text output, reuses everything.
- **`analyze` next** exercises the fan-in join, the hardest untested path.
- **`build`/`validate`** exercise sandbox seeding and file read-back, and are the only stages
  the `code/` track can grade — but they are also where `od_context` (item 3) bites hardest.

### Recommendation
`plan`, then `analyze`. Get the chaining proven on the cheap stages before the tool-using
ones.

---

## 6. The judge's resolution depends on the dataset

**Status:** open · **Raised:** 2026-07-29 from runs `260729-174919` and `260729-175607`

### The question
The anchors are `90 / 70 / 50 / 30`. The judge only ever uses the top one. What should a 70
or a 50 actually describe, such that a real spec lands there?

### The evidence
Across both runs — 4 rows × 3 dimensions = **12 sub-scores** — the judge emitted exactly
**two distinct values: 90 and 95.**

| run | billing_console | healthcare_scheduling |
|---|---|---|
| `260729-174919` | 90 / 90 / 95 → **91** | 90 / 90 / 95 → **91** |
| `260729-175607` | 95 / 90 / 95 → **93** | 90 / 95 / 90 → **92** |

**Then the `small` dataset changed the picture.** Run `260729-182649`, same judge, same
config shape, briefs that cap their own length:

| row | data_realism | brief_intent | design_system | total |
|---|---:|---:|---:|---:|
| `tiny_inventory` | **70** | 90 | 90 | **82** |
| `tiny_helpdesk` | 90 | 90 | 85 | **89** |

Vocabulary `[70, 85, 90]` — three values, a real 70, and a 7-point spread. Both automatic
warnings correctly stayed silent. **So the judge can discriminate; on long ten-industries
specs it stops doing so.**

The likely mechanism: a 16,000-character spec is impressive enough in aggregate that every
dimension reads as excellent, while a deliberately terse one exposes its weak parts — the
`tiny_inventory` data really was `8, 3, 42`, and the judge said so with a 70. If that holds,
the ceiling is a property of *what is being graded*, not only of the model or the anchors.

Two things follow from the ten-industries runs, and they compound:

**The totals overstate the resolution.** 93 and 92 look like a judge making fine
distinctions. It is not: 40/40/20 weighting turns a two-value vocabulary into several
distinct totals. `distinct_score_count: 2` was passed by a near-binary instrument.

**Noise already exceeds signal.** Same config, same rows, run twice: `billing_console`
moved **+2** and `healthcare_scheduling` **+1**. The spread *between* the two rows in the
second run was **1**. Run-to-run movement on one row is larger than the difference between
two different industries — so no ranking these rows produces is trustworthy yet.

Everything also passes: threshold 70, lowest score 90. There is no headroom to reward an
improvement, and a prompt regression would have to be catastrophic to show up.

### Why it is a product question
The fix is to say what the bands mean, and only you can. The current rubric anchors describe
quality in the abstract; the judge reads a competent spec and reasonably calls it excellent.
To get spread you have to define a 70 that a *good* spec actually lands on — which means
deciding what "merely good" looks like for a prototype spec.

### Options
1. **Rewrite the anchors as forced distinctions** — describe 70 as the *expected* output and
   reserve 90+ for something specific and rare, so the judge has to justify the top band.
2. **Score comparatively** — grade a row against a stored reference response rather than in
   the abstract. Much better spread; costs a curated reference per row.
3. **Keep absolute scores for regression detection only** and treat `recurring_weaknesses` as
   the real product signal.
4. **Try a stronger judge first** — anchor-snapping may be a small-model trait rather than a
   rubric flaw. Cheapest to test, and it is entangled with [item 2](#2-which-judge-should-the-baseline-be-calibrated-on).

### Recommendation
**Run `full` first — it is now the cheapest way to discriminate between the hypotheses.**
Twelve long briefs on the same judge that just produced a 70 on a short one. If the ceiling
returns at 12 rows, it is length-driven and option 1 (rewrite the anchors so a *good* spec
lands on 70) is the fix. If it does not, there was never a rubric problem and the earlier runs
were a 2-row sample.

Either way, do not set `baseline.set_from` yet: a baseline calibrated on a coarse judge locks
in an instrument that cannot detect the regressions it exists to catch.

### Worth knowing either way
**The diagnostic half already works.** The clustered weaknesses from run `175607` are
genuinely actionable prompt fixes — "Recent Activity is not requested in the brief" on 2/2
rows, "utility classes are generic", "company names lean on pop culture (Stark Industries,
Wayne Enterprises)". That is the eval doing its job. It is the *number* that is not yet a
measurement, which is an argument for weighting option 3 more heavily than it first looks.

---

## 7. Nothing acts on the analyser's verdict

**Status:** open · **Raised:** 2026-07-29 from a live `small` run

### The question
`prototype-analyze` decides whether the spec and plan are fit to build — `READY TO BUILD` /
`READY WITH CAUTION` / `NEEDS REVISION`. When it says NEEDS REVISION, should the harness stop,
or build anyway?

### The evidence
**No agent consumes `prototype-analyze`.** Checked against every `AGENT.md`:

```
prototype-analyze   consumes=[specify, plan]   gate=Human_Gate
prototype-build     consumes=[plan]            gate=None
```

Its only consumer in production is the **human gate** — a person reads the analysis and decides
whether to send the spec back. The harness has no person. So on a live run the analyser said the
spec needed revision, the run scored that opinion, threw it away, and built from the unrevised
plan regardless. The built HTML then had exactly the defects the analysis predicted.

The chain is faithful to production's *data* flow and unfaithful to its *control* flow, and the
gap is invisible in the numbers: every stage reported `well-formed 1.00`.

### Why it is a product question
Halting changes what stages 4–5 measure. Today they answer *"can build cope with whatever plan
it is given?"* — arguably the more useful question, since production's gate is not guaranteed to
catch everything. Halting would make them answer *"can build cope with a plan a reviewer
approved?"*, which is closer to production but leaves the recovery path ungraded.

### Options
1. **Report only** (what it does now): count the verdicts, print the alert, keep building. The
   run stays comparable and nothing is hidden.
2. **Halt the row** on NEEDS REVISION — that row stops before build, marked skipped with the
   analyser's reason. Faithful to the gate; costs you the build-stage signal for exactly the
   rows most likely to expose a build weakness.
3. **Make it a scored expectation**: a dataset row declares the verdict it *should* receive, and
   disagreement is a scored failure of the analyser. Grades the analyser properly, still builds.
4. **Feed it forward** — add the analysis to build's prompt so it can act on it. This is a
   change to the PRODUCT, not the eval: it would need `consumes` to change in `AGENT.md`.

### Recommendation
**Option 1 now, then 3.** Reporting is already in and costs nothing. Option 3 is the one that
makes the analyser accountable — right now a lazy `READY TO BUILD` on a broken spec scores the
same as a correct one, which is the deeper problem. Do not do option 2 until the judge is
calibrated: skipping rows would change what the build scores mean at the same time as the
scores themselves become trustworthy, and you would not be able to attribute the difference.

Option 4 is worth raising with whoever owns the pipeline — an analysis nobody reads is worth
asking about independently of this harness.

---

## Decided

*(nothing yet — move items here with the decision and date once answered)*
