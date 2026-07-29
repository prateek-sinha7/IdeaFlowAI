# `configs/` — run configs

One YAML file per reproducible grading run. Everything that affects a run's outcome —
dataset, row subset, agent scope, models, judge, concurrency — lives in the file rather than
in a flag combination someone has to remember.

```bash
./evals/grading/grade.sh plan prototype_full   # free preview
./evals/grading/grade.sh prototype_full        # LIVE
```

## Why configs live here and not inside a workflow

Considered and rejected: moving these under `model/workflows/<workflow>/configs/`, next to that
workflow's datasets and rubrics. Two reasons it is the wrong shape.

**A config is not owned by one track.** Each file names its own `track:` — `model` grades prose
with a judge, `code` runs free deterministic checks over a finished run. Workflows live under
`model/`, so filing configs there would put `code`-track configs inside the model tree. The
track split is the load-bearing one: it is what keeps the free checks from being hostage to the
expensive ones.

**A config is also not owned by one workflow — it *names* one.** `workflow: prototype` is a
field, and the same file shape works for any workflow. Nesting would turn one flat, listable
set of runnable configs into a tree you have to walk.

Today it also simply does not matter: one workflow, four configs, no collisions. `grade.sh
configs` shows the binding, so nothing is hidden:

```
  config                  run_id      workflow
  prototype_smoke.yaml    smoke       prototype
```

**When to revisit.** The real problem arrives with the second workflow's first config, because
`prototype_smoke.yaml` cannot mean both prototype-smoke and ppt-smoke.

The answer then is a **workflow prefix in the filename** — `prototype_smoke.yaml`,
`ppt_smoke.yaml` — keeping this folder flat. Preferred over a `configs/<workflow>/` subfolder:
the listing stays one flat sorted set that groups by workflow for free, `check` and `configs`
keep their simple globs, and shell completion still works. A subfolder would buy separation
this package is nowhere near needing at four files.

Two things make that a pure rename whenever you want it:

- `_config_path` tries an exact match first and falls back to a **unique fragment** match, so
  `grade.sh plan prototype_smoke` finds `prototype_smoke.yaml` on its own. Once two workflows both have a
  `smoke`, the fragment is ambiguous and is refused rather than guessed — you type
  `prototype_smoke`, which is the right amount of friction before a token-spending run.
- The `smoke|small|full|partial` shortcut arm now passes `$name` rather than `$name.yaml`.
  With the extension the fragment glob became `*smoke.yaml*.yaml`, which matches nothing — so
  the LIVE `grade.sh prototype_smoke` would have broken under a rename while the free
  `grade.sh plan prototype_smoke` kept working. That asymmetry is the worst possible one, and it is gone.

Do it when the second workflow lands, not now: `ppt/` currently holds nothing but a README.

| File | Runs | Cost |
|---|---|---|
| `prototype_smoke.yaml` | 3 rows, no judge — prove the dispatch path works | **3 calls** |
| `prototype_small.yaml` | 3 short rows, judged — **the debugging loop** | **5 calls** |
| `prototype_full.yaml` | All **5** stages, every row, judged | **111 calls** |
| `prototype_partial.yaml` | **The one you edit** — pick agents and/or rows | depends |

`small` is the one to reach for while changing the *harness* — a rubric, a hook, the judge
schema, a new stage. It exercises the whole judged path on briefs that cap their own length,
so a cycle is quick and cheap. **Its scores are not comparable to anything else**: the briefs
order the agent to be brief, which is not what the real prompt is being asked to do. Prove the
machinery works with `prototype_small`; judge whether a prompt improved with `prototype_full`.

All four pin **Mistral** (`mistral-small-latest` under test, `mistral-large-latest` judging).
That is deliberate: leaving `provider: null` means "walk `ANTHROPIC_API_KEY` → Bedrock →
Mistral and stop at the first that *looks* configured", and Bedrock looks configured even with
an expired token — so an unpinned run silently never reaches Mistral. Pinning is the only way
to know which model actually ran.

Preview any of them for free before spending:

```bash
./evals/grading/grade.sh plan prototype_smoke     # or full / partial
```

---

# Schema

A minimal config needs only `track`, `workflow` and `dataset` — every other key has a default
(shown below). Unknown keys are **rejected**, not ignored, so a typo fails at load rather than
silently doing nothing.

```yaml
run_id: my-run-name                    # label for this config
track: model                           # model | code
workflow: prototype                    # folder under model/workflows/

dataset: datasets/ten-industries.json  # path, relative to the workflow folder
agents: all                            # all | [agent-id, ...]
from_run: null                         # extend an existing run folder
rows: null                             # [row-id, ...] — subset by name
limit: null                            # first N rows

agent_under_test:                      # the agent being GRADED
  provider: null
  model: null

judge:                                 # the model doing the GRADING
  provider: null
  model: null
  threshold: null

options:
  concurrency: 3
  no_judge: false
  repeats: 1
```

## Top level

### `run_id` — *string, default `"adhoc"`*
A human label for this config, recorded in `run_summary.json`. **Not** the run folder name:
that is minted per run as `{YYMMDD-HHMMSS}-{dataset_id}`. Two runs of the same config share a
`run_id` and have different folder names — which is exactly what makes them comparable.

### `track` — *`model` | `code`, default `model`*
`model` runs the agents and grades their prose with a judge model (costs tokens). `code` runs
deterministic HTML checks over a finished run's built artifacts (free). Any other value is
rejected.

### `workflow` — *string, required in practice, default `prototype`*
Names the folder under `model/workflows/`. Its `workflow.yaml` supplies the stage order and
how each stage's input is composed.

### `dataset` — *path, default `""`*
**A path, not an id.** Relative paths resolve against the workflow folder, so
`datasets/ten-industries.json` is the normal form; an absolute path works for a scratch
dataset outside the repo. Empty means "use the workflow's own `default_dataset`".

The file carries its own `dataset_id`, and *that* is what names the run folder. A dataset is
not owned by one agent — the `output.json` one stage produces is a valid input dataset for the
next — so the binding happens here rather than in the filename.

### `agents` — *`"all"` | list of agent ids, default `"all"`*
Which stages run. Never implicit.

```yaml
agents: all                                  # every implemented stage, in workflow order
agents: [prototype-specify]                  # one stage
agents: [prototype-specify, prototype-plan]  # a subset
```

`all` **stops at the first stage that is not `status: implemented`** rather than skipping it —
running stage 5 against an empty upstream would produce artifacts that look valid and mean
nothing. A list always executes in **workflow order**, whatever order you write it in.

Every listed agent's upstream must be satisfiable: either an earlier agent in the same run, or
already present in the `from_run` folder. Otherwise the run fails naming the missing artifact
paths — it never quietly falls back to reading the dataset.

### `from_run` — *dataset_run_id or null, default `null`*
Resolve upstream inputs from an existing run folder, **and write into it**. Required whenever
the first agent to run is not the workflow's root stage — otherwise there is no upstream to
read. Use it to run specify, inspect the result, then run plan against that same output.

The folder is append-only: re-running a stage that already has artifacts is a hard error
unless `--replace` is passed on the CLI, because silently overwriting destroys the captured
response text irrecoverably.

### `rows` — *list of row ids or null, default `null`*
Run only these dataset rows. `null` runs all of them. Row ids are the `id` field of each
dataset row (`billing_console`), stable across every stage.

### `limit` — *positive integer or null, default `null`*
Run only the first N rows. `rows` wins if both are given. Both exist to keep an exploratory
run cheap.

## `agent_under_test` — the agent being graded

```yaml
agent_under_test:
  provider: mistral
  model: mistral-small-latest
```

`null`/`null` uses `build_model`'s implicit fallback chain: `ANTHROPIC_API_KEY` → Bedrock →
Mistral.

> ⚠️ **`build_model` only honours `provider: mistral`.** Any other value —
> including `anthropic` and `bedrock` — is **silently ignored** and falls through the chain
> above. Setting `provider: anthropic` is not an error and not an instruction; it is a no-op
> that happens to work wherever `ANTHROPIC_API_KEY` is set. Whatever you write, the artifacts
> record `resolved_model_id`, the model that actually ran.

## `judge` — the model doing the grading

```yaml
judge:
  provider: mistral
  model: mistral-large-latest
  threshold: null
```

Leave all three `null` to use the judge **pinned in the agent's rubric**, which is what keeps
runs comparable by default. Setting them overrides that pin, and the override is recorded.

- `provider` / `model` — same honoured-provider caveat as above.
- `threshold` — the per-row pass mark, 0–100. `null` uses the rubric's (70 today). Distinct
  from `baseline`, which is a per-*run* expectation.

Every rubric now pins **`mistral / mistral-large-latest`**, and these configs name the same
model — so they *agree* with the pin rather than override it. That is the point: the judge is
declared once, in the rubric, and a config repeating it is a readable no-op.

> **Overriding the judge has a consequence worth knowing.** When the judge resolves to a model
> other than the rubric's pin, the baseline verdict comes back **`REFUSED`** rather than
> PASS/FAIL — the run is not comparable to a baseline calibrated on a different judge. You
> still get every score, every per-dimension aggregate, and the recurring-weakness clustering;
> only the pass/fail is withheld. To calibrate on a different judge, pin it in the rubric
> instead and record the run id in `baseline.set_from`.
>
> This is exactly what the old `claude-sonnet-5` pin did: unreachable here, overridden by every
> config, and therefore refusing every verdict. A test now fails if any rubric pins a provider
> `build_model` does not honour.

## `options`

### `concurrency` — *positive integer, default `3`*
How many **rows** run at once within a stage. Stages themselves are always sequential — each
one needs the previous stage's output — so this is the only place parallelism helps.

Keep it modest. Every row is two model calls, and providers rate-limit; a 429 mid-run costs a
whole stage. The Mistral config uses `2` for that reason.

### `no_judge` — *boolean, default `false`*
Run the agents and the deterministic precheck, but skip the judge entirely. **Zero judge
tokens** — though the agent dispatches still cost. Also skips the judge preflight. This is
what makes the smoke config cheap.

### `repeats` — *positive integer, default `1`*
Run this exact config N times, each as its own run folder, and report the variance across
them.

This is the point of "reproduce it multiple times". A config fixes the **inputs**; it cannot
fix the **outputs**, because the model is not deterministic. Repeating is how you find out how
much a score moves on its own — and therefore whether a later difference means anything.

With `repeats: 1` there is no variance data, so `compare` reports `unknown-variance` and
**refuses to call any delta an improvement**. Set this to 3 when you want that guard armed. It
triples the cost, and it is what turns a score into a measurement.

---

## Precedence and overrides

```
defaults  <  config file  <  CLI flags
```

Every CLI value that differs from the config is recorded in `run_summary.json` under
`config.overrides`. A run whose flags diverged from its config is **not reproducible from that
config**, and says so rather than looking identical to one that was.

## The resolved snapshot

Every run writes `.runs/<workflow>/<dataset_run_id>/grade_config.resolved.yaml` — the fully merged final
settings, with nothing left implicit. It is written **before the first dispatch**, so even a
crashed run stays reproducible:

```bash
./evals/grading/grade.sh run .runs/prototype/260729-083126-ten-industries/grade_config.resolved.yaml
```

That is exact even if the original config in this folder has since changed, which is what
makes a fair before/after comparison possible: re-run the identical spec against an edited
prompt so the prompt is the only variable.

## Starting a new one

Copy [`../model/_templates/grade_config.yaml.template`](../model/_templates/grade_config.yaml.template),
which carries the same documentation inline. Then check it without spending anything:

```bash
./evals/grading/grade.sh plan <your-config>   # resolved plan + dispatch estimate
./evals/grading/grade.sh check                # every config parses and dry-runs
```
