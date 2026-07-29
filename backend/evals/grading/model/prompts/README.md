# `grading/model/prompts/` — standalone agents

Agents that are **not part of a workflow** — invoked directly and independently,
with no upstream stage feeding them and no downstream stage consuming their
output. Free-chat agents and one-shot utility agents (title generation, and
similar) are the cases this exists for.

**Status: defined, empty.** No standalone agent has been onboarded yet.

## How this differs from `../workflows/`

Everything about grading one agent is identical. The only difference is that
there is **no chaining**, so two things drop out:

- **No `workflow.yaml`.** Nothing declares stage order or input composition,
  because there is no stage before or after.
- **No `<agent>_output.json` artifact.** An output artifact exists to become the
  next stage's input; with no next stage there is nothing to hand forward. The
  response still lands in `<agent>_run.json` as normal.

Each agent therefore has two agent-specific files, plus a dataset it names:

```
prompts/
├── datasets/<name>.json    ← the rows to run, addressed by path
├── <agent>_rubric.yaml     ← precheck config + judge rubric + baseline
└── <agent>_validate.py     ← the custom precheck hook (optional)
```

The file contract, naming rules, and artifact shapes are identical to the
workflow track — see [`../README.md`](../README.md). Start from
[`../_templates/`](../_templates/).

## Run output

`prompts/.runs/{YYMMDD-HHMMSS}-{dataset_id}/`, same shape as a workflow run,
except `artifacts/` holds only the one agent's files.

## A note on selection

Every agent with a `pipeline_type` in its `AGENT.md` belongs to a workflow and
goes in `../workflows/<pipeline_type>/` instead — that covers the entire
`agents/registry.py` roster today. An agent only lands here if it is genuinely
invoked outside the pipeline runtime. If you are unsure which applies, it is a
workflow agent.
