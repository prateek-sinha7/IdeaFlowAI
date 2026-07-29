# `grading/model/` — LLM-as-judge grading

Grades output a script cannot assess — a spec, a task list, an analysis — by
running the agent for real and scoring its response with a judge model against a
committed rubric.

Every response passes **two** gates, in order:

1. **Precheck** (deterministic, free) — is this response even well-formed?
   Wrapper tags, section count, forbidden strings, plus one optional custom hook.
   Config-driven, in `<agent>_rubric.yaml`.
2. **Judge** (a model, costs tokens) — given it is well-formed, is it *good*?
   Scored 0–100 across explicit rubric dimensions.

The precheck exists so the judge is never asked to assess something malformed,
and so obvious structural regressions are caught for free.

## Files per agent

```
workflows/<workflow>/
├── workflow.yaml                 ← one per workflow: stage order + input composition
├── datasets/<name>.json          ← the rows to run, addressed by path
├── <agent>_rubric.yaml           ← precheck config + judge rubric + baseline
└── <agent>_validate.py           ← the custom precheck hook (optional)
```

Standalone agents live in [`prompts/`](prompts/) and have no `workflow.yaml`.
Start any new agent by copying [`_templates/`](_templates/).

### `datasets/<name>.json`

```json
{
  "dataset_id": "ten-industries",
  "rows": [{ "id": "billing_console", "industry": "SaaS Billing",
             "tags": ["admin-console"], "prompt": "..." }]
}
```

`dataset_id` names the *dataset*; each row's `id` names the *row*. They were both
called `id` before, which made the run folder name ambiguous. Row ids must be
stable across every stage of the workflow.

### `<agent>_rubric.yaml`

Holds four blocks: `precheck`, `judge`, `rubric`, `baseline`. See
[`_templates/agent_rubric.yaml.template`](_templates/agent_rubric.yaml.template)
for the annotated contract, and
[`workflows/prototype/prototype_specify_rubric.yaml`](workflows/prototype/prototype_specify_rubric.yaml)
for a real one.

Two things worth knowing up front:

- **The validate hook is referenced by path, not dotted module** —
  `validate: ./prototype_specify_validate.py:check`. Relative to the rubric file.
  This keeps rubric and hook genuinely co-located and means these folders need no
  `__init__.py` and no import-path bookkeeping when a file moves.
- **`baseline:` is excluded from the rubric hash.** The hash covers `precheck`,
  `judge`, and `rubric` only — the things that change what a score *means*.
  Ratcheting a threshold must not look like a rubric change.

## How a stage's input is built

`workflow.yaml` declares, per stage, where that stage's prompt comes from. Three
shapes cover everything the prototype workflow needs:

- **`dataset`** — the first stage, reads the dataset file named by the run config.
- **`from: [<agent>]`** — a linear chain; the upstream stage's output, verbatim.
- **`from: [<agent>, <agent>]` + `template`** — a fan-in join; several upstream
  outputs composed into one prompt. This is what `prototype-analyze` needs
  (`<spec>` *and* `<tasks>`), and it is the case the previous layout could not
  express at all.

Plus `adapter:` when a stage needs its prompt *transformed* rather than
concatenated, and `seed_files:` for tool-using agents that read files from the
sandbox instead of the prompt.

A `seed_files` value is either an **upstream agent id** (that agent's response for
this row, verbatim) or a **`./file.py:func` derivation hook** — the same path
convention as `adapter:` and a rubric's `validate:`. It is never a second copy of
another seed: seeding identical content under two filenames asserts a derivation
the schema cannot express.

The authority on which agents exist and in what order is
`agents.registry.get_pipeline_agents()`, and on what each consumes, the
`produces`/`consumes` frontmatter in `agents/prompts/<agent-id>/AGENT.md`.
`workflow.yaml` **mirrors** those and adds only what is eval-specific (wrapping,
adapters, seeding). It must not become a second, drifting source of truth — a
loader should assert its stage list matches the registry, exactly as
`engine.py` already asserts the manifest against `PIPELINE_AGENTS`.

## Artifacts a run produces

```
.runs/{YYMMDD-HHMMSS}-{dataset_id}/
├── grade_config.resolved.yaml          ← re-run this exact run: --config <this file>
├── run_summary.json                    ← all stages, one file
├── artifacts/
│   ├── <agent>_run.json                ← one entry per row: prompt, response, precheck
│   ├── <agent>_grade.json              ← one entry per row: score, sub-scores, rationale
│   ├── <agent>_score.json              ← aggregate, per-dimension, recurring weaknesses
│   └── <agent>_output.json             ← this stage's rows, as the next stage's input
├── prompts/<agent>_system_prompt.md    ← the composed prompt the agent actually saw
└── logs/<agent>_<scenario>.log         ← raw transcript per dispatch
```

`grade_config.resolved.yaml` is written **before the first dispatch**, so even a crashed run
is reproducible. `prompts/` stores the fully composed system prompt — guardrails, skills and
injections included, not just the `AGENT.md` body — because a `system_prompt_hash` tells you
two runs differed but never *how*.

All four artifact files are indexed by the same stable row `id`, and every stage
of the run writes into the same `artifacts/` folder. That is what makes fan-in
possible and lets `run_summary.json` show a row degrading across stages.

`<agent>_output.json` uses the **same envelope as a dataset file**, so promoting a
generated output to a checked-in dataset is a copy — no reshaping. It adds
`source_agent`, `dataset_run_id`, and a per-row `upstream_precheck_passed` flag so
a degraded row stays visibly degraded downstream instead of silently poisoning
the next stage.

See [`workflows/prototype/example-run/`](workflows/prototype/example-run/) for a
real one.

## Reading a score

`<agent>_score.json` reports **two** averages — over rows that passed precheck,
and over all rows — because they answer different questions and averaging a
malformed response's score into the headline number makes it meaningless. It also
reports `stddev` and `distinct_scores`, because a judge returning the same number
for every row is the most common way this kind of eval silently stops working,
and a bare average hides it completely.

`baseline` in the rubric turns the aggregate into a verdict. Without a committed
baseline the numbers are unfalsifiable — which defeats the point.
