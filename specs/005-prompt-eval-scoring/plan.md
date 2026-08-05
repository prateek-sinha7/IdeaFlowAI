# PLAN — building the `grading/` runner

Living reference for this folder, the way `specs/006-hybrid-eval-suite/` is for the deterministic
track. Records why the folder looks the way it does, what is built, and what is left.

**Status: BUILT.** The runner exists and is wired into `./evals/grading/grade.sh`. Twelve modules,
239 offline tests, `model_graded/` untouched and still green at 71. Config and documentation
complete for `prototype-specify`.

**Not yet done:** no live calibration run has been made, so `baseline.set_from` is still
uncalibrated and the judge is unverified against real output. Stages 2-5 of the prototype
workflow are declared but not onboarded. See TASKS.md for what remains (T17).

---

## Context

All grading logic currently lives in `evals/model_graded/` (6 modules, 1786 lines),
which parses the *old* layout.

**`model_graded/` must not be touched.** It stays exactly as it is. We copy the Python we
need out of it into `grading/`, adapt the copies to the new layout, and leave the original
running. Two parallel trees for now; retiring `model_graded/` is a later, separate decision.

The code must be **simple and easy to read**: `grade_runner.py` dispatches to a
`model_grader` or a `code_grader`; the model grader loads scenario files, builds the agent
runner, runs it, takes the output, and grades it. A reader should follow that chain without
a map.

The runner must support **both a full-workflow run** (all five prototype stages chained in
one go) **and a single-stage run** (one agent, optionally against a previous run's output).

### The goal this serves

**Find quality problems in a workflow's output, and improve the prompts that caused them.**
Scoring is the means, not the end. Every design decision below is answerable against one
question: *does this help someone decide which prompt to change, and tell them whether the
change worked?*

That framing has teeth. It is why the judge returns per-dimension sub-scores rather than one
number (a total cannot tell you which paragraph to rewrite); why the composed system prompt is
stored, not just its hash (a hash cannot be diffed); why every run emits a re-runnable config
(a fair before/after needs the prompt to be the only variable); and why `compare.py` exists at
all. A folder that produces a trustworthy score and stops there is only half the system —
see *Closing the loop*.

### How we got here

A review of the reorganised folder found the structure right in three ways — workflow-first
rather than agent-first, one dataset-keyed run folder shared by every stage, and
`output.json` as a first-class artifact — and identified gaps since fixed in config. Two
findings came out of the committed run data and drive several decisions below:

1. **The judge had no signal.** All 11 rows scored exactly 95 — `stddev 0.0`, one distinct
   value. That eval could not have detected any regression. Causes: a small judge model, a
   rubric asking for one 0–100 number with no per-dimension breakdown, and no calibration
   anchors.
2. **The precheck rejected correct specs.** `precheck_pass_rate` 0.36 — 7 of 11 rows — every
   one a false positive from bare-substring matching on `placeholder` and `stub`, which are
   legitimate UI vocabulary (`Search input placeholder: "Search waitlist..."`). Re-running
   the narrowed list against the same stored responses gives 11/11. And because
   `skip_on_precheck_failure` was false, those 7 wrongly-rejected rows were *also* judged at
   95 and folded into the headline average.

Both are written up in full in
[`model/workflows/prototype/example-run/README.md`](../../backend/evals/grading/model/workflows/prototype/example-run/README.md).

### Already done (config only — no code)

Naming rules and the three run-id concepts ([the operator runbook](../../backend/evals/grading/docs/README.md)); the `code/` track
contract; [`model/_templates/`](../../backend/evals/grading/model/_templates/); `workflow.yaml` declaring all five
prototype stages including the `prototype-analyze` fan-in; `prototype-specify`'s dataset,
rubric, and validate hook; and `example-run/` — the real run, reshaped, with both failures
written up.

### Decisions taken

| Question | Decision |
|---|---|
| First implementation scope | Model track, `prototype-specify` end-to-end. `code_grader.py` ships as a dispatchable skeleton. |
| Code track ↔ model run | Shares the run folder; reads its HTML from the same `dataset_run_id`. |
| HTML checks | Reuse `app/agents/static_check.py` + `render_check.py` rather than restating them. |

---

## Task 0 — one config bug left to fix

**`workflow.yaml`'s stage-4 `seed_files` lies.** It seeds `spec.md: prototype-specify` and
`design.md: prototype-specify` — byte-identical content under two filenames — while the
comment claims design.md is "derived from the spec's DS section." The schema cannot express
derivation. Either drop `design.md`, or allow a `seed_files` value to take the
`./file.py:func` form so the derivation is real code.

*(The second bug found in review — dimensions weighted 40/40/20 while anchors were keyed on a
0-100 scale — is already fixed: dimensions are now scored 0-100 and weighted in Python.)*

---

## Files

Twelve modules, flat, at `backend/evals/grading/`. Each readable in one sitting.

| File | Responsibility |
|---|---|
| `__init__.py` | Package marker + conventions docstring. |
| `grade_runner.py` | CLI: parse args, pick the track, print the human summary, set the exit code. |
| `model_grader.py` | Model-track orchestration only: `run_workflow → run_stage → run_row`. No parsing, no paths, no stats. |
| `code_grader.py` | Code-track entry: read a model-track run folder, run deterministic checks. Skeleton. **Must not import `judge.py`.** |
| `config.py` | Load + validate the four config kinds — run config, `workflow.yaml`, `*_rubric.yaml`, `datasets/*.json` — into frozen dataclasses; merge defaults/config/CLI overrides; assert against the registry and `AGENT.md`; compute run-config + rubric + dataset hashes. |
| `hooks.py` | Resolve `./file.py:func` relative to a config file — shared by `validate:` and `adapter:`. |
| `stage_input.py` | **Pure.** Per-row prompt composition: dataset / upstream / fan-in template / adapter / seed_files, plus the skip policy for failed and `expect: fail` rows. |
| `dispatch.py` | The only runtime-touching module: one row → agent → response, plus the composed system prompt used, sandbox seeding, deliverable read-back, log file. |
| `precheck.py` | Wrapper / section / forbidden-regex gate **and** the custom hook, combined here. |
| `judge.py` | Build the judge prompt from rubric+dimensions+anchors; one static structured-output schema; hard-fail on judge misconfiguration. |
| `scoring.py` | **Pure.** Sub-scores → weighted totals, **per-dimension aggregates**, expect-aware pass rates, clean-chain average, distinct/stddev, **clustered weaknesses**, baseline verdict, warnings. |
| `compare.py` | **Pure.** Two or more runs → per-row, per-dimension and per-prompt-version deltas, with a noise guard. The module that turns a score into a prompt decision. |
| `artifacts.py` | **Pure I/O.** Run-folder paths, run-id minting, read/write the four artifacts + `run_summary.json` + the resolved run config + the composed system prompts, the supersede policy, `compute_system_prompt_hash`. |

**Dependency direction** (assert in review, no cycles):
`grade_runner → {model_grader, code_grader, compare}`;
`model_grader → {config, stage_input, dispatch, precheck, judge, scoring, artifacts}`;
`config → hooks`; `stage_input → hooks`; `compare → scoring`;
`dispatch`, `scoring`, `artifacts` import nothing else in the package.

Four modules — `stage_input`, `scoring`, `compare`, `precheck` — are pure and testable in milliseconds
without a model call. That is deliberate: they hold the logic whose silent failure costs a
whole run.

### Why this shape rather than fewer files

- **`scoring.py` split from `artifacts.py`** because aggregation is where the content is (two
  averages, stddev, distinct count, the `expect` correction, clean-chain average, baseline
  verdict) and it is exactly what silently broke last time. One pure file you read to
  understand what a number means.
- **`stage_input.py` split from `model_grader.py`** because composition is ~150 lines of
  joining rules and orchestration is ~80 lines of loops. Split, `model_grader.py` reads
  `run_workflow → run_stage → run_row` top to bottom with no branching on input shapes.
- **`hooks.py` split from `config.py`** because `validate:` and `adapter:` use the identical
  `./file.py:func` convention and are needed by two different modules. Otherwise it is
  duplicated or `stage_input` imports `config` for a 20-line helper.
- **`dispatch.py`, not `agent_run.py`** — `agent_run_id` already means *one stage over all
  rows*. This module runs *one row*. Do not re-overload a term the README defines.

### What gets copied from `model_graded/` (read-only source)

| New file | Copied from | Change |
|---|---|---|
| `dispatch.py` | `driver.run_graded_scenario_once` + `GradedRunResult` | Preserve the dispatch body. Explicit args instead of `GradedScenario`; return `log_path` + the composed system prompt instead of `run_dir`. |
| `precheck.py` | `precheck.run_precheck`, `_closing_tag`, `validate_precheck_config`, `cli._combined_precheck` | `forbidden` becomes `[{pattern, reason}]` regexes; takes an already-resolved hook callable. |
| `judge.py` | `judge.grade_run`, `build_rubric_prompt`, `JudgeVerdict` | Static per-dimension schema; pinned `judge:` block; `skip_on_precheck_failure`; hard-fail on misconfiguration. |
| `scoring.py` | `report._summarize_group` | Add per-dimension aggregates and weakness clustering. |
| `compare.py` | `report.summarize(group_by=..., target=...)`, `report.worst` | **Do not drop this.** `summarize(group_by="system_prompt_hash")` already groups runs by prompt version chronologically with a met/not-met flag — that is the "did my edit help?" view, and it is the one existing capability that directly serves the goal. |
| `artifacts.py` | `report.compute_system_prompt_hash`, `write_score`, `cli._build_run_entry`, `cli._build_grade_entry` | New shapes and path scheme. |
| `config.py` | `scenario_discovery._resolve_agent_id`, the id-uniqueness validation | Everything else is new — no `_template.yaml`, no global scan, no dotted imports. |
| `grade_runner.py` | `cli._has_judge_credentials`, `_has_provider_credentials`, `_system_prompt_path`, the `sys.path` bootstrap (`parents[3]`) | Argparse surface is new. |

---

## Code style (binding for everything in `grading/`)

- **All imports at the top of the file.** No function-level or inline imports anywhere.
- **File docstring: 3–4 lines.** What the file does, concisely. Not an essay.
- **Every function gets a docstring** — one or two lines; the *why* only when non-obvious.
- **Simple, readable variable names.** `rows`, `stage`, `response` — not `sc`, `res`, `cfg`.
- **SOLID / YAGNI / DRY.** One job per module. Build only what the current scope needs.

Two mechanical consequences, since the source violates the first rule on purpose:

1. **`model_graded` imports inline** (`from agents.factory import create_runner` *inside* the
   function). A top-level `from ... import` would break
   `monkeypatch.setattr(factory_module, "create_runner", fake)`, which only works if the
   attribute is looked up at call time. So import the **module** at the top and call through
   it — verified to stay patchable, ~0.3s total import cost, no cycles:

   ```python
   import agents.factory          # top of file

   runner = agents.factory.create_runner(agent_id, ctx, thread_id=...)
   ```

2. **The `sys.path` bootstrap must run before any `agents.*` import**, so it lives in exactly
   one place — `grade_runner.py`, the only entry point. That keeps the `# noqa: E402` dance
   out of the other ten files.

---

## Behaviour to build

### Stage input composition (`stage_input.py`)

One public entry point, **pure** — takes loaded envelopes, returns dataclasses, no file I/O,
no model calls:

```python
build_stage_inputs(stage, *, dataset, upstream_outputs) -> list[StageInput]
```

`StageInput` carries `row_id, prompt, seed_files, deliverable_file, industry, tags, expect,
upstream_chain, skip_reason`. Rules it owns:

- `source: dataset` → one input per dataset row.
- `source: upstream`, one `from:` → that upstream's response verbatim.
- `source: upstream`, several `from:` + `template:` → **fan-in**, an *inner join on row id*.
  `len(from) > 1` **requires** `template` — error if absent, never fall back to concatenating
  in list order (`workflow.yaml` already says ordering is the template's). `{agent-id}`
  placeholders are validated against `from:` **at load time**. A row present in one upstream
  and missing from another emits a `StageInput` with `skip_reason` — never dropped silently,
  because silent drops are how `row_count` stops matching across stages.
- `adapter: ./file.py:func` applies *after* template composition. Signature pinned:
  `(row: dict, upstreams: dict[str, str]) -> str`.
- `seed_files: {filename: upstream_agent_id}` resolves to that upstream's text for the same
  row id.

### Full-workflow vs single-stage

- `--agents all` (the default) → run every stage with `status: implemented`, in order, into
  one run folder.
  **Stop at the first stage whose `status != implemented`** — do not skip it and run later
  stages against an empty upstream. Distinguish "declared not onboarded" from "rubric file
  missing".
- `--agents a,b` → that subset, always in workflow order. A non-root first agent requires
  `--from-run`, and the run **extends that folder**. Minting a new folder with a lineage pointer is rejected: the fan-in join is a
  lookup *within one `artifacts/` folder*, and a pointer chain breaks the README's central
  claim.
- A listed agent whose upstream never ran in `--from-run R` → fail listing the missing
  artifact paths. Never silently fall back to `source: dataset`.

### The run folder is append-only

Silent overwrite is the real failure mode here and it is unrecoverable — the response text is
gone.

- Existing `<agent_token>_run.json` → **hard error** naming the file, offering `--replace`.
- `--replace` moves the existing four artifacts to
  `artifacts/superseded/<agent_token>_a<N>_*.json` and appends to a `stage_runs: []` list in
  `run_summary.json`.
- Re-running stage N marks stages > N `status: stale` in `run_summary.json` rather than
  deleting them — their `output.json` input no longer exists on disk, so their artifacts look
  valid and are meaningless. Each stage records an `input_hash` (sha256 of its composed
  prompt set) so staleness is detectable, not inferred.
- `run_summary.json` gets `created_at` plus per-stage timestamps in `stage_runs` — a single
  dataset-level `started_at`/`finished_at` becomes a lie the moment a folder is extended.
- Surface each stage's `rubric_hash` in `run_summary.json` so a folder graded under two
  rubric versions is visible.

### Degraded, failed, and negative rows

- **Empty response is an error, not a precheck failure.** The driver returns `errored=False`
  with `response == ""` when the model yields nothing without an error event. Classify
  `not response.strip()` as errored *before* precheck, or it fails the wrapper check with a
  misleading reason and counts against `precheck_pass_rate`.
- An errored row is excluded from the next stage's input. A stage where *every* row errored
  aborts the remaining stages.
- **`on_upstream_failure: skip | run_anyway`** declared per stage in `workflow.yaml`, default
  `skip`. An *errored* dispatch is always `skip` — there is no text to forward. Today
  `output.json` carries `upstream_precheck_passed` but nothing says what the runner does with
  it; this decides it.
- Each downstream row carries `upstream_chain: [{agent, precheck_passed, score}]`, and
  `scoring.py` reports **`average_clean_chain`** alongside the two existing averages. Without
  it a stage-3 score drop is unattributable — you cannot tell whether analyze regressed or
  specify handed it garbage. This is the most likely way a multi-stage eval becomes
  uninterpretable.
- **`expect: fail` rows**: outcome is `correct = precheck_passed != (expect == "fail")`.
  Excluded from `precheck_pass_rate`, reported as a separate `negative_rows_correct: n/m`,
  gated by a new `baseline.min_negative_correct`. Critically, they are **excluded from
  `output.json` and skipped by the judge** — otherwise `underspecified_brief` propagates into
  every downstream stage of every future run.

### Judge sub-scores — one static schema, weights applied in Python

Do **not** build the Pydantic model dynamically from dimension ids. Two concrete reasons
beyond readability: YAML ids would become Python field names (identifier validation,
collisions, keywords), and `le=weight` bakes the weight into the JSON schema — drop
`data_realism` 40 → 20 and a judge returning 35 raises a validation error that `grade_run`
swallows into an errored verdict scoring 0. **A rubric weight edit would silently produce an
all-zero run** — the exact class of bug `min_distinct_scores` exists to catch, reintroduced
one layer down.

Instead:

- `DimensionScore{id: str, score: int 0-100, evidence: str}`;
  `JudgeOutput{dimensions: list[DimensionScore], rationale, strengths, weaknesses}`.
- Every dimension scored **0–100**, then `total = sum(score_i * weight_i) / 100` in
  `scoring.py`. This is also what fixes the anchors/weights incoherence in Task 0.
- Validate `{d.id returned} == {d.id in rubric}` in Python; precise errored verdict on
  mismatch. **Key by id, never by list index** — ordering is not guaranteed.
- `passed = total >= threshold`, computed by us. Never let the judge decide `passed`.
- Weight changes become re-weightable arithmetic over stored `sub_scores` — no re-run needed.

`grade.json` in `example-run/` already reserves `sub_scores: null`. This shape fills it.

### Judge misconfiguration is a hard failure

**Verified:** `build_model(model, *, provider)` only honours `"mistral"`.
`provider="anthropic"` — which this rubric pins — is silently ignored and falls through the
implicit chain (`ANTHROPIC_API_KEY` → Bedrock → Mistral). It resolves correctly *by
accident* where `ANTHROPIC_API_KEY` is set, and silently to another provider where it is not.

Since `model_graded` is frozen, the new `judge.py` resolves the provider itself and
**hard-fails** on an unsupported or unconfigured one — not an errored verdict, because that
yields 12 rows of score 0 that look like a catastrophic model regression. Then compare
`judge_resolved_model_id` against the pinned `model:`; on mismatch, warn into `score.json`
and **refuse to evaluate the baseline**. An uncalibrated-judge run must be non-comparable by
construction — precisely the failure the constant-95 run demonstrated.

### Hashes

`rubric_hash` over `precheck` + `judge` + `rubric` + `dimensions` + `anchors`, **excluding**
`baseline` — ratcheting a threshold must not look like a change to what a score means. Also
hash the **dataset rows**: changing a brief moves scores as much as changing the rubric, and
nothing currently records that. Refuse baseline evaluation when either hash differs from the
one recorded in `baseline.set_from`.

### Run config — `--config <path>`

A run must be reproducible from a file, not from remembering a flag combination. Every input
that affects a run's outcome lives in one YAML **run config**, loaded by `config.py` as its
fourth file kind:

```yaml
run_id: prototype-specify-baseline     # human label, not a dataset_run_id
track: model
workflow: prototype

dataset: datasets/ten-industries.json  # PATH, relative to the workflow folder
agents: all                            # `all`, or an explicit [a, b] subset
from_run: null                         # extend an existing run folder
rows: [billing_console, hr_ats]        # omit -> all rows
limit: null

agent_under_test:
  provider: null                       # null -> build_model's implicit chain
  model: null

judge:
  provider: anthropic                  # overrides the rubric's pinned judge
  model: claude-sonnet-5
  threshold: 70

options:
  concurrency: 3
  no_judge: false
  repeats: 1                           # N independent runs of the same config
```

Two fields carry the design weight:

- **`dataset` is a path, not an id.** Relative paths resolve against the workflow folder, so
  `datasets/ten-industries.json` is the normal form; an absolute path works for a scratch
  dataset outside the repo. The file carries its own `dataset_id`, which is what names the
  run folder. This replaces the old `<agent_token>_dataset.json` convention: a dataset is
  **not bound to an agent by its filename**, because a file generated by one stage is a valid
  input dataset for the next — the whole point of `output.json` sharing the dataset envelope.
  Binding happens in the run config instead. A dataset file may declare `for_agent:` as an
  advisory guard, validated when present, so handing plan's generated specs to specify fails
  loudly rather than producing nonsense.

- **`agents` is `all` or an explicit list.** `all` runs every stage with
  `status: implemented` in workflow order, stopping at the first that is not. A list runs
  that subset, always in **workflow order regardless of the order listed**. A listed agent's
  upstream must be satisfiable — either an earlier agent in the same run, or already present
  in the `from_run` folder — otherwise the run fails naming the missing artifacts. It never
  silently falls back to the dataset. This replaces the singular `agent:` field, whose
  omit-for-full-workflow behaviour left "which agents run" implicit.

Rules:

- **CLI flags override the config**, and every override is recorded in `run_summary.json`
  under `config.overrides` with a warning. A run whose flags diverged from its config is not
  reproducible *from that config*, and must say so rather than look identical to one that was.
- **Every run emits a re-runnable config into its own folder**, at
  `.runs/<workflow>/<dataset_run_id>/grade_config.resolved.yaml` — every value after defaults, config
  file, and CLI overrides are merged, so nothing is left implicit. Written **before the first
  dispatch**, not at the end, so a crashed or interrupted run is still re-runnable. It is a
  first-class artifact, not a log: a run folder is self-describing, and repeating a run is

  ```
  ./evals/grading/grade.sh --config .runs/<workflow>/<dataset_run_id>/grade_config.resolved.yaml
  ```

  with no reference to the original config file, which may since have changed. This is also
  what makes a fair prompt comparison possible: re-run the *identical* spec against the edited
  prompt, so the only variable is the prompt. A run started with no `--config` at all still
  emits one, so an ad-hoc CLI invocation becomes reproducible after the fact.
- **`config_hash` joins `rubric_hash` and `dataset_hash`** in `run_summary.json`, and baseline
  evaluation is refused when any of the three differs from what `baseline.set_from` recorded.
- The rubric's pinned `judge:` block remains the default; a run config overriding it is
  recorded as an override, for the same reason as any other.

**`repeats: N` is the point of "reproduce it multiple times."** N independent runs of one
config, each its own `dataset_run_id`, plus a variance report across them. An LLM run is not
deterministic — the config reproduces the *inputs*, never the outputs — so repeating a fixed
config is exactly how you measure judge and agent variance rather than mistaking one sample
for a measurement. Given the constant-95 history, that distinction matters here more than
usual.

### Closing the loop — from a score to a prompt change

**This is the point of the whole exercise.** Everything above produces a trustworthy number;
this section turns that number into a decision about which prompt to edit. Without it the
folder is a scoreboard, not an improvement loop.

**Per-dimension aggregates.** `scoring.py` reports mean/median/stddev/min/max **per
dimension**, not just for the total. The overall average says the output got worse; the
per-dimension breakdown says *which paragraph of the AGENT.md to rewrite* — "`data_realism`
averages 62 while `brief_intent_match` averages 88" is actionable in a way "average 74" never
is. Aggregating only the total discards the diagnostic value of sub-scores at the last step.

**Clustered weaknesses.** The judge already returns `weaknesses[]` and per-dimension
`evidence`; today they land in `grade.json` and stop. `scoring.py` groups them across rows
into a ranked `recurring_weaknesses` list in `<agent>_score.json`, with row ids and quoted
evidence. "7 of 12 rows were marked down for round-number invented data" is a prompt fix;
twelve separate JSON blobs are homework. This is what `--worst N` prints.

**`compare.py` — the "did my edit help?" module.** Pure, no I/O, no model. Takes two or more
runs and reports:

- per-row score deltas, and which rows flipped precheck or crossed the threshold;
- per-dimension deltas, so a regression is attributable to a specific rubric dimension;
- grouping by `system_prompt_hash` in chronological order, so a sequence of prompt edits reads
  as a trend rather than a pile of runs.

**A noise guard, because the opposite failure is just as easy.** With 12 rows and a
stochastic judge, a 3-point move in the average is probably nothing. `compare.py` reports a
delta **against observed run-to-run variance** — from `options.repeats`, or across prior runs
of the same config and prompt hash — and refuses to call a difference an improvement when it
sits inside the noise band. The constant-95 run was one failure mode; reading noise as
progress is the other, and it is more seductive because it looks like the loop is working.
`baseline` gains `max_expected_stddev` as the sibling of `min_distinct_scores`: a
suspiciously *tight* spread is as diagnostic as a suspiciously flat one.

**Capture the composed prompt, not just its hash.** A hash tells you two runs differed; it
never tells you *how*. `dispatch.py` already returns the composed system prompt — it has to,
so the judge grades the prompt the agent actually saw (see the `no_tools` bug) — so
`artifacts.py` writes it once per stage to `prompts/<agent_token>_system_prompt.md` in the
run folder. That captures guardrails, skills, and injections, i.e. the real composed prompt
rather than the `AGENT.md` body, which is what makes a diff between two runs possible at all.

Reuse rather than rebuild: **`evals/hybrid/dump_prompts.py` already exists** and describes
itself as *"the 'what does Haiku actually see' ground truth for prompt iteration — 0 tokens."*
It is the existing tool for this job and should be the model for the dump format.

**Feed the code track back in.** A `static_check` failure on the built HTML — a dangling
route, a missing `:root` token — is direct, free evidence about `prototype-build`'s prompt.
`code_grader.py` writes its findings into the same run folder keyed by row id, and
`compare.py` treats them as another per-row signal alongside judge scores. Otherwise the
cheapest and most precise quality signal available never reaches the person editing the
prompt.

### Registry assertion is mandatory

`config.py` asserts the `workflow.yaml` stage list equals
`agents.registry.get_pipeline_agents()` in membership *and* order, and that each stage's
`from:` equals that agent's real `consumes` frontmatter. ~15 lines. Both `workflow.yaml` and
`model/README.md` demand it; without it `workflow.yaml` becomes the drifting second source of
truth it explicitly warns against.

### Concurrency: rows, not stages

Stages are inherently sequential, so cross-stage concurrency buys nothing and creates three
writers to `run_summary.json`. Row-level concurrency within a stage is where the wall-clock
win is (12 rows × 2 model calls).

With that design there are **zero concurrent writers to any file**: each row writes only its
uniquely-named log; `run`/`grade`/`score`/`output`.json are written once from in-memory
results at end of stage; `run_summary.json` is rewritten once per stage. Bound it
(`--concurrency`, default 3 — the judge is `claude-sonnet-5` and the agent under test will
hit rate limits) and isolate per-row exceptions so one row cannot kill a stage.

Resumability then comes free at stage granularity. Write `run_summary.json` with
`status: running` *before* each stage and again after — today a crash mid-run leaves a folder
with no summary and no record of where it died.

---

## What changes in the copied dispatch path

1. **`run_dir` stops being per-dispatch.** Once several rows and stages share one folder, the
   old pattern of writing `run.json` into `Path(result.run_dir)` collides. `dispatch.py`
   returns `log_path`; `artifacts.py` owns every artifact path.

2. **One sandbox per row for the whole workflow**, `sandbox_run_id = f"{dataset_run_id}-{row_id}"`.
   `create_runner` shares one sandbox across every agent in a pipeline run (keyed on
   `ctx.run_id` only) — that is exactly how `prototype.html` survives build → validate in
   production. The old driver mints a fresh id per dispatch, so every stage got a fresh
   sandbox and the chain had to be *synthesised* via `seed_files` (which is why the fake
   `design.md` seed exists). One sandbox per row chains as production does, and `seed_files`
   is then needed only when starting mid-workflow via `--agent ... --from-run`.
   This also retires the fourth id scheme (`{ts}-graded-{id}-{uuid8}`) whose leakage the
   example run had to record as `legacy_scenario_run_id`.

   **Verified constraint:** `RunSandbox._safe_segment` truncates to 128 chars. The current id
   is 62, but a longer `dataset_id` + `row_id` would truncate and **collide two rows into one
   sandbox**. Assert the length.

3. **`thread_id` becomes `f"{sandbox_run_id}:{agent_id}"}`** — what the engine does. With one
   sandbox per row, the old `f"{run_id}:graded"` collides across stages. Harmless today with
   `checkpointer=None`; it is the documented contract and will bite the moment one is passed.

4. **Pass `run_sandbox=` explicitly.** Verified: `create_runner` accepts and honours it. The
   current seeding relies on the *coincidence* that a manually built `RunSandbox(user_id,
   run_id)` resolves to the same root as the internal one. Identical on-disk behaviour, and
   the load-bearing invariant becomes visible instead of a comment. Highest-value clarity
   change in the copied code.

5. **`dispatch.py` returns the composed system prompt it actually used**, and the judge uses
   *that*. `model_graded/judge.py` hardcodes `no_tools=True`; verified,
   `no_tools = exclude_builtin_tools and not custom_tools`, so for `prototype-build` and
   `prototype-validate` (which have tools) it is **False** — the judge would grade against a
   system prompt the agent never saw. Returning the real one eliminates the whole drift
   class, and means the judge automatically sees the real injected template/design system
   once `od_context` (the `known_gaps` entry in `workflow.yaml`) is populated.

6. **Token totals will under-report for build/validate.** `usage` is summed per model turn,
   but the build task loop runs sub-agents whose turns may not surface a `usage` event. State
   that in `score.json` rather than presenting `tokens.total` as exact.

**Checked and dismissed:** `RUN_DIR_TTL_HOURS` sweeping a sandbox mid-run. `sweep_expired`
has no callers anywhere outside its own definition, so nothing in the request path can
trigger it.

### Invariants that must survive verbatim

- `user_id = "eval-graded"` and the sandbox run id must match between the sandbox we build
  and the one the runner uses (now explicit via `run_sandbox=`).
- `provider is not None` → `ctx.model = build_model(model, provider=provider)` (an
  *instance*); else `ctx.model = model`. `DeepAgentRunner` does not forward `provider`.
- `resolved_model_id = getattr(runner, "model_id", None) or "unknown"`.
- `astream_events` **yields** errors, never raises. `usage` fires once per model turn and
  must be summed. Events: `chunk`, `usage`, `tool_call`, `tool_result`, `error`, `gate`,
  `done`.
- Deliverable read-back is skipped on error, and only replaces `response` when
  `sandbox.read()` returns non-`None`.

---

## CLI surface

```
./evals/grading/grade.sh full                       # reproducible run
./evals/grading/grade.sh --config .runs/<workflow>/<dataset_run_id>/grade_config.resolved.yaml   # re-run

./evals/grading/grade.sh model <workflow>                     # full workflow, new run folder
    --config <path>               load every setting below from a run config
    --agents all|a,b              which stages to run (default: all)
    --from-run <dataset_run_id>   resolve upstream from / write into that folder
    --replace                     supersede existing artifacts for that stage
    --rows a,b   --limit N        subset
    --no-judge                    precheck only (free)
    --dry-run                     compose prompts, print dispatch estimate, no calls
    --concurrency N               rows in flight within a stage (default 3)
    --dataset <name>              override the stage's dataset
    --provider/--model            agent under test
    --judge-provider/--judge-model/--judge-threshold    grader only

./evals/grading/grade.sh code  <workflow> --from-run <dataset_run_id>

# reading results — all free, no model calls
./evals/grading/grade.sh report  <dataset_run_id> [--worst N]   # per-dimension + recurring weaknesses
./evals/grading/grade.sh compare <run-a> <run-b>                # deltas, with the noise guard
./evals/grading/grade.sh compare --by-prompt <workflow> <agent> # every run grouped by prompt version
```

Named `grading`, **not** `grade` — `./evals/hybrid/eval.sh` already has a `graded)` arm bound to
`model_graded.cli`, and a one-character difference between two token-spending commands is a
footgun. `graded`, `dataset`, and `report` stay bound to the old package.

Add the `grading)` arm before the `*)` catch-all: `shift`, then
`exec "$PY" -m evals.grading.grade_runner "$@"`, plus a usage block in the header
comment in the same aligned style. Grading is **always live**, so it prints the token-spend
warning to stderr the way `benchmark` does rather than taking a `--live` flag.

**Blast radius**: `grading model prototype` is 12 rows × 5 stages × 2 model calls, two stages
tool-using. Someone will type it. Print the dispatch estimate before a full-workflow run;
`--dry-run`, `--limit`, `--rows`, and `--no-judge` exist for this reason.

**Standing rule: live runs are the developer's to execute.** No agent or automated process
invokes these.

---

## Tests

New files `backend/tests/unit/test_grading_*.py`. All offline — no model calls, no network.
The old package's 71 tests stay untouched and keep passing.

- `config.py` — envelope validation, the registry/`consumes` assertion, all three hashes, the
  unhonoured-provider hard-fail; run-config merge precedence (defaults < config < CLI), that
  every override is recorded, and that the resolved snapshot round-trips — loading a
  snapshot reproduces byte-identical resolved settings.
- `hooks.py` — path resolution relative to the config file; clear error on a missing function.
- `precheck.py` — regex forbidden list, and specifically that `placeholder` in
  `Search input placeholder: "..."` no longer fails.
- `stage_input.py` — the five input shapes; fan-in inner join by row id; missing-upstream
  skip reason; `len(from) > 1` without `template` errors; placeholder validation at load.
- `dispatch.py` — seeding lands before dispatch; deliverable read-back replaces the response;
  absent deliverable falls back to streamed text; empty response classified as errored
  (monkeypatch `create_runner`, as `test_model_graded_driver.py` does).
- `judge.py` — dimension-id mismatch produces a precise errored verdict; `passed` computed
  from the threshold, not the judge; weight change does not error.
- `scoring.py` — weighted total, two averages, clean-chain average, stddev/distinct,
  per-dimension aggregates, weakness clustering, inverted `expect: fail`, baseline verdict,
  baseline refused on hash mismatch.
- `compare.py` — per-row and per-dimension deltas; rows that flipped precheck; grouping by
  `system_prompt_hash` in chronological order; and specifically that a delta inside the noise
  band is **not** reported as an improvement.
- `artifacts.py` — path scheme, append-only guard, `--replace` supersede, stale marking.
- `model_grader.py` — full-workflow orchestration with a faked dispatch: one run folder,
  stages in order, chaining, all-errored stage aborts, stop at first non-implemented stage.

---

## Verification

1. **Offline, free** — `python3.11 -m pytest tests/unit/test_grading_*.py -v`, plus
   `python3.11 -m pytest tests/unit/test_model_graded_*.py -v` to prove the untouched package
   still passes.
2. **Config integrity, free** — every YAML/JSON parses; `workflow.yaml` stage order equals
   `get_pipeline_agents('prototype')`; each `from:` equals that agent's `consumes`; dimension
   weights sum to 100; every forbidden pattern compiles.
3. **Dry run, free** — `./evals/grading/grade.sh plan full` prints the resolved stage plan, row counts, dispatch estimate, and the models
   it *would* use. Re-running against the snapshot a real run wrote must print an identical
   plan — that is the reproducibility check, and it costs nothing.
4. **Replay, free** — point `code_grader` at `example-run/` and confirm it produces a verdict
   from committed data with no model call.
5. **Loop check, free** — `grading compare` two committed runs and confirm it reports
   per-dimension deltas and refuses to call a within-noise difference an improvement. Then
   confirm every run folder contains a `grade_config.resolved.yaml` that re-runs to an
   identical `--dry-run` plan.
6. **Live** — `./evals/grading/grade.sh full`. Success:
   one new `.runs/prototype/{timestamp}-ten-industries/` folder; four artifacts plus per-row logs;
   `precheck_pass_rate` near 1.0 on the positive rows; `negative_rows_correct` 1/1; and
   **`distinct_score_count > 1`** — the single most important signal, since its absence is
   what made the previous run worthless.
7. **Calibrate** — once a clean run exists, set `baseline.set_from` to that `dataset_run_id`
   and record both hashes. Until then the baseline is explicitly `NOT CALIBRATED`.

---

## Out of scope

Modifying `model_graded/` in any way; migrating its 39 scenario rows; onboarding
prototype-plan/analyze/build/validate (config-only work once this runner exists); the `ppt`
workflow; a real `code_grader` beyond the dispatchable skeleton; and running any live eval.
