# `evals/grading/` — agent output grading

Grading answers one question: **is this agent's output good?** — as opposed to
`evals/hybrid/workflow/` and `evals/hybrid/engine/`, which answer *did the machinery run
correctly?*

The point is not the score. The point is **finding quality problems in a workflow's output and
improving the prompts that caused them**. Scoring is how you tell whether an edit helped.

Two tracks, split by *how* output is judged. One workflow normally uses both, at different
stages.

| Track | Judges | Verdict | Cost |
|---|---|---|---|
| [`model/`](../model/) | Prose an LLM must read — a spec, a plan, an analysis | 0–100 + rationale from a judge model | tokens |
| [`code/`](../code/) | The built HTML, after the build stage | pass/fail from executable checks | free |

They stay separate because their failure modes differ. `model/` is flaky, costly, and needs
calibration; `code/` is deterministic and should run on every commit. Mixing them makes the
cheap checks hostage to the expensive ones.

---

## Quickstart

`grade.sh` is the CLI for this package and nothing else. It resolves its own location, so it
works from any directory.

```bash
# 1. See what a run would do. Free — composes every prompt, dispatches nothing.
./evals/grading/grade.sh plan prototype_smoke

# 2. Cheap smoke run: precheck only, zero judge tokens.
./evals/grading/grade.sh prototype_smoke

# 3. The debugging loop: 3 short rows, judged end to end.
./evals/grading/grade.sh prototype_small

# 4. A full judged run — the one whose scores mean something.
./evals/grading/grade.sh full

# 5. Read the result. Free.
./evals/grading/grade.sh runs                      # find the run id
./evals/grading/grade.sh report <run-id> --worst 3
```

Config names are fuzzy-matched, so `plan prototype_smoke` finds `prototype_smoke.yaml`. An **ambiguous** fragment is
refused rather than guessed — `plan sm` now matches both `prototype_small.yaml` and `smoke.yaml` and
errors, because silently picking one of two token-spending runs is not a convenience.

## Commands

| Command | Costs tokens? | |
|---|---|---|
| `grade.sh plan <config>` | no | Resolved plan + dispatch estimate. Dispatches nothing. |
| `grade.sh run <config>` | **yes** | Run from a config. The normal way. |
| `grade.sh prototype_smoke` | **yes** (3 calls) | 3 rows, no judge — the cheapest real run |
| `grade.sh prototype_small` | **yes** (5 calls) | 3 short rows, judged — the debugging loop. **Scores not comparable to `full`.** |
| `grade.sh prototype_full` | **yes** (111 calls) | All 5 stages, every row, judged |
| `grade.sh prototype_partial` | **yes** | The config you edit — pick agents/rows |
| `grade.sh apply-advice <run-id> --agent <id>` | no | Apply that run's advice to `AGENT.md`, archiving the old body to `AGENT.vN.md` |
| `grade.sh revert <agent>` | no | Restore the newest archived body; repeated calls walk back |
| `grade.sh report <run-id> [--worst N]` | no | Per-dimension scores + recurring weaknesses |
| `grade.sh compare <a> <b>` | no | Deltas between two runs, with the noise guard |
| `grade.sh history <agent>` | no | Every run grouped by prompt version |
| `grade.sh code <run-id>` | no | Deterministic HTML checks over a run's build output |
| `grade.sh runs` | no | List run folders, newest first — with the **config** that produced each |
| `grade.sh configs` | no | List available run configs |
| `grade.sh check` | no | Config integrity + dry-run every config |
| `grade.sh test` | no | The package's own unit tests (280, all offline) |

Anything else passes straight through to the runner, so the full CLI stays reachable:

```bash
./evals/grading/grade.sh model prototype --agents prototype-specify --limit 3 --dry-run
```

**Runner flags** — `--config` · `--agents all\|a,b` · `--from-run ID` · `--replace` ·
`--rows a,b` · `--limit N` · `--no-judge` · `--dry-run` · `--concurrency N` ·
`--dataset PATH` · `--provider`/`--model` · `--judge-provider`/`--judge-model`/`--judge-threshold`

`--provider`/`--model` move the **agent under test**. `--judge-*` move the **grader**. They are
strictly separate axes — conflating them is how you end up grading one model's output with a
rubric calibrated for another.

### `grade.sh check` — the free pre-flight for config edits

```
  every YAML/JSON parses
  prototype: stage order matches the registry
  prototype_specify_rubric.yaml: weights sum 100, all patterns compile
  --- dry-running every shipped config ---
  full.yaml    dispatch estimate: 12 agent calls + 11 judge calls = 23 model calls
```

The registry assertion is the valuable one: it fails if `workflow.yaml` has drifted from the
real agent roster in `agents/registry.py`, which is how a stale eval silently grades the wrong
pipeline.

### The neighbouring eval CLIs

Each eval package owns its own script and they share no entry point. The old `run-eval.sh`
router was deleted on 2026-07-29 — use the owner directly:

| Script | Answers | Cost |
|---|---|---|
| `./evals/grading/grade.sh` | is this agent's output good? | always live |
| `./evals/hybrid/eval.sh` | did the machinery run right? | offline by default |
| `./evals/model_graded/model-graded.sh` | — **frozen**, reads back old runs only | — |

`model-graded.sh` is the previous generation of this package; its scores were not reproducible.
Do not calibrate against them.

## Safety: the model track is always live

There is no `--live` flag, because dispatching real agents *is* the job. Three things protect
you instead:

1. **It prints its blast radius before spending** — stages, rows, dispatch estimate, and the
   models it will actually use.
2. **`--dry-run` stops right there**, having composed every prompt and dispatched nothing.
3. **It preflights the judge before the first dispatch.** A misconfigured judge costs zero
   instead of failing after every agent call has been paid for.

```
grading ────────────────────────────────────────────────────────────────────────────────
  run        small  ·  prototype  ·  260729-182649-small
  models     mistral/mistral-small-latest  →  judged by mistral/mistral-large-latest
  dataset    small  ·  3 rows selected

  stage                rows  dispatch  judge  status
  prototype-specify       3         3      2  ready
  prototype-plan          —         —      —  not run (not_yet_onboarded)
  prototype-analyze       —         —      —  not run (not_yet_onboarded)
  prototype-build         —         —      —  not run (not_yet_onboarded)
  prototype-validate      —         —      —  not run (not_yet_onboarded)

  spend      3 agent + 2 judge = 5 model calls
```

### Why a preview can chain at all

A dry run dispatches nothing, so a later stage has no upstream text to compose against. For a
stage that just *forwards* its input that does not matter. `prototype-build` is different: it
**parses** the plan for `## Task N:` headers to build its `=== CURRENT TASK ===` block, so a
placeholder string made every single preview report an adapter failure that could not happen in
a live run.

Stages whose output is parsed downstream therefore declare a **`dry_run_sample`** in
`workflow.yaml` — real-shaped output used only to let a preview compose. It is never
dispatched, judged or scored, and `grade.sh check` asserts it **passes that agent's own
precheck**, so it cannot rot into something the real agent would never emit.

A note about composition is now *actionable*: it means the sample is missing or stale, not
that previews are inherently unable to chain.

Anything a stage needs to say about its rows prints **below** the table under a `notes`
heading, indented deeper than a table row — a note beginning with an agent id used to read as a
second row for a stage that already had one. Notes wrap rather than truncate, and one row
skipped for one reason across several stages is reported once:

```
  notes
    underspecified_brief skipped in 4 stage(s) — expect: fail row is not propagated to
      a downstream stage
```

**A live run and `plan` print exactly this same block** — a preview whose shape differs from
the real run is not a preview. Stages that will not run are listed rather than counted,
because *"why did stage 4 produce nothing?"* is the question this table exists to answer
before you ask it. `status` reads `ready`, or names that stage's own models when its rubric
pins a different judge from the rest.

(11 judge calls, not 12: the `expect: fail` negative-test row is never judged — and it never propagates downstream, which is why every stage after the root is one row lighter.)

`code`, `report` and `compare` make no model calls at all.

### Live progress

A judged run takes minutes, so it reports as it goes rather than sitting silent behind the
plan table. Rows run concurrently, so a row's start and finish do not always adjoin — each
line carries the row id and its position:

```
prototype-specify  ·  4 rows ─────────────────────────────────────────────
  ⋯ 1/4    billing_console         generating…
  ⋯ 1/4    billing_console         judging…
  ✔ 1/4    billing_console             82   agent 4.2k · judge 6.5k
  ✖ 2/4    healthcare_scheduling        —                              ERROR AccessDeniedException: Bearer T…
  ✖ 3/4    fleet_ops                    —   agent 5.1k · judge 4.2k    JUDGE FAILED 3 validation errors fo…
  · 4/4    hr_ats                       —                              skipped — upstream 'prototype-plan'…
```

The glyph carries the verdict, so the ordinary case needs no words: **✔** graded, **✖**
something failed, **·** dispatched but deliberately not judged. Tokens are split because the
two halves are billed differently — and on a judged row the judge routinely costs more than
the agent.

Each row announces the phase it is in — `generating` (the agent under test) then `judging`
(the grader). Only those two print, because they are the ones that take real time; the
precheck is sub-millisecond and its verdict shows up in the finished row. With
`no_judge: true` you will only ever see `generating`.

### The closing summary

When the run finishes it prints per-stage headlines, the total spend split agent-vs-judge, and
**the path to `REPORT.md`** — nothing more. The dimension tables, per-row sub-scores and the
judge's full narrative live in that file, because printing them buried the two numbers that
decide what you do next.

```
results ────────────────────────────────────────────────────────────────────────────────
  stage                rows  judged  precheck  negative    avg  stddev  distinct  baseline
  prototype-specify       3       2      1.00       0/1   85.5     3.5         2  REFUSED

  ⚠  prototype-specify — LOW JUDGE RESOLUTION: across 2 rows the judge used only 2
     distinct sub-score value(s) — [85, 90]. …

  tokens     33.7k total  ·  agent 19.9k  ·  judge 13.8k
  status     completed

  Full report ready at:
  …/.runs/prototype/260729-182649-small/REPORT.md
```

One line per stage, so a five-stage workflow stays scannable. What each column means:

| column | question it answers |
|---|---|
| `rows` / `judged` | how many were dispatched, and how many reached the judge |
| `precheck` | fraction whose output was **well-formed** — structure only, no quality |
| `negative` | how many `expect: fail` rows were correctly rejected |
| `avg` | mean weighted score across judged rows — **the quality number** |
| `stddev` | how much those scores varied. `0.00` means the judge said the same thing about every row |
| `distinct` | how many different totals came back. `1` is a dead instrument |
| `baseline` | `PASS` / `FAIL` / `REFUSED` (see below) |

Warnings are **wrapped, never truncated** — the sentence that says what to do about one is
never in its first 60 characters.

`distinct_score_count` alone is **not** proof of a working judge — weighting turns a two-value judgement into several
distinct totals. Two warnings in the report catch that:

- **`LOW JUDGE RESOLUTION`** — the judge used fewer than 3 distinct *sub-score* values across
  the run, so the varied-looking totals are arithmetic rather than judgement.
- **`SCORE CEILING`** — every sub-score sits in the rubric's top anchor band, so nothing
  distinguishes good from excellent and an improvement has no room to show.

**A judge that fails is never reported as "no judge."** Those two look identical in the
aggregates — both leave every score null — but one is a config choice and the other means the
grading half of a paid run produced nothing. A failed judge marks the row **✖ JUDGE
FAILED**, raises a warning in the closing summary and in the artifacts, and **exits 6** when no
row on a stage got a verdict. `no_judge: true` costs nothing and exits 0.

`model_grader` emits these as events and never prints. `grade_runner` decides **what** to
show; [`render.py`](../render.py) decides **how it looks** — every number format, the token
abbreviation, the column widths, and both table builders live there.

That split matters because there are two renderers over the same data: the terminal and the
run folder's `REPORT.md`. They had already drifted — one printed `85.5`, the other `85.50` for
the same score — because each kept its own `_number`. A test now asserts neither module owns a
private formatter, so changing a style is one edit in `render.py` and both views move together.

**Exit codes** — `0` ok · `2` usage/config · `3` baseline FAIL · `4` judge preflight ·
`5` no credentials · `6` run did not complete.

## Reproducing a run

A run config carries everything that affects the outcome, so a run is reproducible from a
file rather than a remembered flag combination. Every run writes
`.runs/<workflow>/<dataset_run_id>/grade_config.resolved.yaml` — the fully merged settings — **before the
first dispatch**, so even a crashed run is re-runnable:

```bash
./evals/grading/grade.sh run <path-to>/.runs/<workflow>/<dataset_run_id>/grade_config.resolved.yaml
```

CLI flags override config values, and every override is recorded — a run whose flags diverged
says so rather than looking identical to one that didn't.

**A config reproduces the *inputs*, never the *outputs*.** Two runs of one config will differ,
because the model is not deterministic. That is worth measuring, not engineering away — set
`options.repeats: N` to run one config N times and get the variance. See
[`configs/README.md`](../configs/README.md).

## The improvement loop

The whole reason this exists:

1. **Run** a config. One command does the whole loop — dispatch, judge, code checks, prompt
   advice — and leaves all of it under **`.runs/<workflow>/<id>/reports/`**: `report.md` for the
   headline grade and per-phase scores, `<agent>_report.md` for one phase in full (dimension
   aggregates, every row's sub-scores, the judge's rationale and quoted evidence),
   `code_report.md` for the browser findings, and `prompt_advice_<agent>.md` for the proposed
   prompt delta. `grade.sh report <run-id> --worst 3` re-prints and regenerates it all, free.
2. **Diagnose** with the per-dimension scores. "`data_realism` averages 62 while
   `brief_intent_match` averages 88" tells you *which paragraph* of the `AGENT.md` to rewrite;
   an overall average of 74 tells you nothing. `recurring_weaknesses` clusters the judge's
   complaints across rows — "7 of 12 rows marked down for round-number invented data" is a
   prompt fix. The advice file has already done this pass for you and proposed wording; treat
   it as a starting point to review, not an instruction to apply.
3. **Edit** `agents/prompts/<agent-id>/AGENT.md` — by hand, or let the advice apply itself:

   ```bash
   ./evals/grading/grade.sh apply-advice <run-id> --agent prototype-build
   ```

   Free — the advice was written by a run that already happened. The current body is archived
   to `AGENT.vN.md` **before** `AGENT.md` is touched, the edits are applied, and the diff is
   printed. Review it with `git diff`; if it reads badly,
   `grade.sh revert prototype-build` puts it back.

   Three things it will not do. It never edits the **frontmatter** — that is the engine's
   contract (`pipeline_type`, `order`, `produces`/`consumes`, `tools`, `gate`), and an advisor
   edit aimed at it is refused by name while the rest still apply. It never applies an edit
   whose quoted text is missing or appears twice — the command fails, exit 9, and **nothing is
   written**. And it never appends to the end of the file when it cannot place an addition: a
   misplaced edit looks applied and is invisible to a skimmed diff.

4. **Re-run** the identical config, so the prompt is the only variable.
5. **Compare** — `./evals/grading/grade.sh compare <old> <new>`, or
   `grade.sh history <agent>` to see every version as a trend.

Step 5 has a guard worth knowing about. With 12 rows and a stochastic judge, a 3-point move is
probably nothing. `compare` measures observed run-to-run variance and **refuses to call a delta
an improvement when it sits inside the noise band**; with no repeat data it reports
`unknown-variance` rather than assuming. Reading noise as progress is the failure mode that
looks most like success.

Each run also stores the **composed** system prompt at
`.runs/<workflow>/<id>/prompts/<agent>_system_prompt.md` — guardrails and injections included, not just
the `AGENT.md` body. A `system_prompt_hash` proves two runs differed; only the text shows how.

---

## Layout

```
grading/
├── grade.sh                     ← the CLI (location-independent)
├── docs/                        ← you are here
├── configs/                     ← run configs: one file per reproducible run
├── .runs/<workflow>/            ← ALL run output (gitignored)
├── code/                        ← deterministic HTML grading (post-build)
└── model/                       ← LLM-as-judge grading
    ├── _templates/              ← copy-me starting points for a new agent
    ├── prompts/                 ← agents that belong to no workflow
    └── workflows/<workflow>/    ← agents that belong to a workflow  (config only)
        ├── workflow.yaml        ← stage order + how each stage's input is built
        ├── datasets/*.json      ← the rows to run (addressed by path)
        ├── <agent>_rubric.yaml  ← precheck + judge + rubric + baseline
        ├── <agent>_validate.py  ← custom precheck hook (optional)
        └── example-run/         ← one committed real run, as reference
```

Run output lives at the **grading root**, not inside the workflow folder. That folder is
checked-in config; mixing gitignored artifacts into it would force every loader, glob and doc
tool to special-case skipping `.runs`. It also gives the code track somewhere to write, since
both tracks share a run folder keyed by `dataset_run_id`.

The runner is split by track. Everything that touches a model lives in `model/`
(`model_grader` the orchestrator, `dispatch`, `judge`, `precheck`, `stage_input`, `scoring`,
`prompt_advisor`) beside the model track's config tree; the free deterministic track lives in
`code/` (`code_grader`). The shared plumbing stays flat at the grading root: `grade_runner`
(the only entry point), `config`, `hooks`, `artifacts`, `compare`, plus two presentation
leaves — `render` (how every value and table looks) and `markdown_report` (the run folder's
`reports/` set). See [`build-summary.md`](../../../../specs/005-prompt-eval-scoring/build-summary.md)
for what each does and [`plan.md`](../../../../specs/005-prompt-eval-scoring/plan.md) for why.

## Naming rules

Conventions a loader relies on — keep them exact.

**Agent file token.** An agent id is kebab-case (`prototype-specify`); its file token replaces
hyphens with underscores (`prototype_specify`). Every *agent-specific* file is
`<token>_<kind>.<ext>`. Underscores everywhere.

**Datasets are the exception — addressed by path, not by agent.** They live in
`datasets/<name>.json` with a free-form name and carry their own `dataset_id`; a run config
names the file it wants. A dataset is not owned by one agent: the `output.json` one stage
generates is a valid input dataset for the next, and tying datasets to agent filenames would
make that promotion a rename. A dataset may declare `for_agent:` as an advisory guard.

**Row ids are stable across stages.** A row keeps the same `id` (`billing_console`) at every
stage. Never suffix per agent (`billing_console_plan`) — the agent belongs in the *filename*.
Stable ids are what let you join a row across stages and say "billing_console degraded at
analyze."

**Three distinct run ids**, which all previously collided under the name "run_id":

| Name | Scope | Format |
|---|---|---|
| `dataset_run_id` | one invocation, all stages | `{YYMMDD-HHMMSS}-{dataset_id}` (the run folder) |
| `agent_run_id` | one stage within it | `{dataset_run_id}-{agent_token}` |
| `scenario_run_id` | one dispatch of one row | `{agent_run_id}-{row_id}` |

Timestamp-first so runs sort chronologically.

## All five stages are onboarded

As of 2026-07-29 every `prototype` stage has a rubric, a validate hook and `status:
implemented`, so `agents: all` runs the whole chain. Each stage grades a different artifact:

| stage | wrapper | what the judge reads | dimensions |
|---|---|---|---|
| `prototype-specify` | `<spec>` | the spec prose | data realism · brief intent · design-system coherence |
| `prototype-plan` | `<tasks>` | `## Task N:` blocks | page coverage · task self-containment · build order |
| `prototype-analyze` | `<analysis>` | the cross-artifact report | grounding · defect detection · verdict coherence |
| `prototype-build` | `<!doctype html>` | **the built `prototype.html`** | data realism · page completeness · visual coherence |
| `prototype-validate` | `<!doctype html>` | **the fixed `prototype.html`** | page completeness · repair delta · token consistency |

Three things worth knowing before reading a score from stages 4 and 5:

**`full` now costs 111 model calls, not 23.** Five stages over 12 rows. Preview with
`grade.sh plan full` before running it, and use `small` or `partial` while iterating.

**`prototype-build` is graded in ONE dispatch, not per task.** Production runs one isolated
sub-agent per task (`_run_build_task_loop`); this harness dispatches once per row. The adapter
reproduces the `=== CURRENT TASK ===` block *shape*, so the score reads as *"can this agent
build the whole prototype in one pass"* — **not** *"does the per-task loop work"*. The
incremental-edit behaviour that loop exists to exercise is not covered.

**`prototype-validate` is the only stage graded on a delta.** Its prompt is the pre-fix HTML
and its response is the post-fix HTML, so the judge sees both and can score the repair. The
precheck hook cannot — it is handed one string — so it grades absolute state only.

Stage 5's rubric also deliberately does **not** score design-system conformance: `od_context`
is never populated during grading, so there is no injected design system to conform to
(`known_gaps.od_context_not_populated`). Scoring it would penalise an agent for a capability it
was never given.

## Open product decisions

Some behaviour is a judgement call, not a defect — whether a vague brief should be refused or
invented from, which judge the baseline is calibrated on, whether agents are graded with a
real design system attached. Those are logged in
[`outstanding.md`](../../../../specs/005-prompt-eval-scoring/outstanding.md) with the evidence and the options, rather than decided
silently. Read it before acting on a score that surprises you.

## Troubleshooting

**`judge preflight FAILED ... exit 4`** — the rubric pins a judge provider that
`app/agents/model_factory.build_model` cannot honour, or whose credential is missing. Note
`build_model` only honours `provider: mistral`; **anything else, including
`anthropic` and `bedrock`, is silently ignored** and falls through an implicit chain
(`ANTHROPIC_API_KEY` → Bedrock → mistral). The message names what is configured on your
machine. Fix by setting the credential, or grade with a configured provider:
`--judge-provider mistral --judge-model mistral-large-latest`.

**`exit 5`, no credentials** — none of `ANTHROPIC_API_KEY`, `AWS_BEARER_TOKEN_BEDROCK`,
`AWS_ACCESS_KEY_ID`, `AWS_PROFILE`, `MISTRAL_API_KEY` resolves.

**`exit 3`, baseline FAIL** — the run did not meet the rubric's committed `baseline`. Read
`report` to see which check failed. `distinct_score_count` below the minimum means the judge
returned near-identical scores for every row, i.e. **the eval had no signal** — treat that as
a broken instrument, not a result.

### `baseline REFUSED` — what it means

**Not a failure, and not a score.** The three verdicts are:

| verdict | meaning |
|---|---|
| `PASS` | this run met every threshold the rubric committed to |
| `FAIL` | it did not — the specific checks are listed |
| `REFUSED` | **the comparison was declined**, because this run is not comparable to the run the baseline was calibrated on |

A baseline is a promise of the form *"a healthy run scores at least this much"*. That promise
only means something relative to a specific calibration run — same rubric, same dataset, same
judge. If any of those differ, the same number no longer describes the same thing, so the
verdict is withheld rather than issued misleadingly. **Every score, aggregate and weakness is
still reported.** Only the pass/fail is suppressed.

Today every run reports:

```
baseline REFUSED
  baseline is not calibrated: set_from is 'NOT CALIBRATED — pending one clean
  run on the fixed precheck + pinned judge', not a record of the calibration
  run's hashes
```

That is the **first** refusal reason: `baseline.set_from` in the rubric is still prose, not a
record. No calibration run has been nominated yet, so there is nothing to compare against.

The other refusal reasons, once one is nominated:

- **a hash differs** — `rubric_hash`, `dataset_hash` or `config_hash` moved, so you changed
  what is being measured. (`baseline` itself is excluded from `rubric_hash`: ratcheting a
  threshold must not look like a change to what a score means.)
- **the judge resolved to a different model than the calibrated one** — which is the live
  reason here, since the rubric pins `claude-sonnet-5` and the configs override to
  `mistral-large-latest`.

**To clear it:** get a run you trust, then record its `dataset_run_id` and hashes in the
rubric's `baseline.set_from`. Do not do that yet — see
[outstanding items 2 and 6](../../../../specs/005-prompt-eval-scoring/outstanding.md): the judge's resolution is still
unproven — it has produced runs with only two distinct sub-scores — and calibrating on a
coarse instrument locks in one that cannot detect the regressions the baseline exists to
catch.

**"row not found in upstream" / missing artifacts** — you asked for a non-root stage without
`--from-run`, or that run folder never ran the upstream stage. The error names the exact
missing artifact paths; it never silently falls back to the dataset.

## `src/` — the documents, as files

`artifacts/` holds JSON for machines. `src/` holds the same work as **real files, one folder
per brief**, because spec.md, tasks.md and prototype.html for one brief are one project and
get read together:

```
.runs/prototype/<run-id>/
├── artifacts/       ← run / grade / score / output JSON
├── logs/            ← the full tool-call transcript per row
├── prompts/         ← the composed system prompt per stage
└── src/
    └── tiny_inventory/
        ├── spec.md               ← prototype-specify
        ├── tasks.md              ← prototype-plan
        ├── analysis.md           ← prototype-analyze
        ├── prototype.html        ← prototype-build
        └── prototype.final.html  ← prototype-validate
```

Each stage declares its filename as `output_file:` in `workflow.yaml`. Build and validate both
produce HTML and are deliberately kept apart: one filename would mean the last writer wins, and
the before/after — the only way to see what the final gate actually changed — would be lost.

Writing these never fails a run: a run that spent real tokens is not failed because a file
could not be written.

## Where run output goes

A run folder is named `{YYMMDD-HHMMSS}-{dataset_id}` — **for its dataset, not its config**.
Two configs reading one dataset therefore produce folders that differ only by timestamp:
running `smoke` against `small.json` writes `260729-184807-small`, same shape as a `small`
run. `grade.sh runs` prints the config alongside, which is the only way to tell them apart:

```
  run                           workflow    config      status
  260729-184807-small           prototype   smoke       completed
  260729-184737-small           prototype   small       completed
```

The dataset keys the folder because a run's *inputs* are what make it comparable to another —
but that means the config is not recoverable from the name alone. It is recorded in
`run_summary.json` and in `grade_config.resolved.yaml`.


`evals/grading/.runs/<workflow>/<dataset_run_id>/`, gitignored. `example-run/` is one real run committed
deliberately as reference documentation for the artifact shapes — not a fixture, not
regenerated. Read [`example-run/README.md`](../model/workflows/prototype/example-run/README.md)
before trusting any number from it: it failed its baseline in two instructive ways.
