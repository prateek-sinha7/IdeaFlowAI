# `prototype` workflow — model grading

Grades the five-stage prototype pipeline: a product brief becomes a spec, a task
list, an analysis, built HTML, and a validated deliverable.

```
prototype/
├── workflow.yaml                     ← stage order + how each stage's input is built
├── datasets/ten-industries.json      ← 12 rows (11 real briefs + 1 negative test)
├── prototype_specify_rubric.yaml     ← precheck + judge + rubric + baseline
├── prototype_specify_validate.py     ← nav-target cross-reference check
├── example-run/                      ← one real run, committed as reference
└── .runs/                            ← real run output (gitignored)
```

## Status

| Stage | Agent | Onboarded |
|---|---|---|
| 1 | `prototype-specify` | ✅ dataset, rubric, validate hook |
| 2 | `prototype-plan` | declared in `workflow.yaml`, no files yet |
| 3 | `prototype-analyze` | declared (fan-in), no files yet |
| 4 | `prototype-build` | declared (adapter + seeding), no files yet |
| 5 | `prototype-validate` | declared (seeding), no files yet |

`prototype-specify` is the worked example. All five stages are declared in
`workflow.yaml` because the chaining — especially the stage-3 fan-in — is the
thing that had to be designed up front; adding stages 2–5 is then three files
each with no structural decisions left to make.

## Adding the next stage

1. Copy the rubric and validate templates from
   [`../../_templates/`](../../_templates/) and rename to the agent's file token
   (`prototype-plan` → `prototype_plan`).
2. Do **not** hand-write a dataset. Stage 2's input is stage 1's output — see
   `input:` for that stage in `workflow.yaml`. To bootstrap before the runner
   supports chaining, copy `example-run/artifacts/prototype_specify_output.json`
   to `datasets/ten-industries-specs.json`, drop the
   `source_agent`/`dataset_run_id`/`upstream_*` keys, and it is a valid dataset
   file (same envelope, deliberately).
3. Keep row ids identical to stage 1's. Never suffix them per agent — see
   [`example-run/logs/README.md`](example-run/logs/README.md) for why that
   convention was removed.
4. Write the rubric's `precheck` block for structure only, and put anything
   requiring judgement in `dimensions`.
5. Leave `baseline.set_from` as uncalibrated until you have one clean run.

## Stage-specific notes

**`prototype-analyze` is a fan-in.** Its `AGENT.md` declares
`consumes: [prototype-specify, prototype-plan]` — it needs the spec *and* the
tasks, for the same row. `workflow.yaml` composes both into one prompt via a
`template`. This is the case that motivated the shared, dataset-keyed run folder:
both upstream outputs sit in the same `artifacts/` directory under the same row
id, so the join is a lookup.

**`prototype-build` and `prototype-validate` are tool-using.** They read files
from the sandbox rather than the prompt, and write their deliverable to
`prototype.html` instead of the stream. So `workflow.yaml` declares `seed_files`
(written before dispatch) and `deliverable_file` (read back after) — and the
graded response is that file, not the streamed text, which is only a confirmation
sentence.

**`prototype-build`'s prompt is transformed, not forwarded.** The real engine
never hands the agent `tasks.md` wholesale — `_run_build_task_loop` runs one
sub-agent per task with that task wrapped in a `=== CURRENT TASK ===` block.
Grading the raw task list would grade a prompt shape the agent never sees, so
`workflow.yaml` names an `adapter` to build the real one.

## Known gap affecting every stage

All five agents declare `injects: [template, design_system, ...]` in their
`AGENT.md`, composed at runtime from `AgentContext.od_context`. The grading
driver does not populate it, so **no agent here is currently graded with a real
template or design system attached** — scores reflect no-template behaviour only.
Recorded in full under `known_gaps` in `workflow.yaml`.

## Before reading any score from this workflow

Read [`example-run/README.md`](example-run/README.md). The one run on record
failed its baseline in two ways — a judge that returned a constant, and a
precheck that rejected correct specs — and both are the reason several parts of
the current config look the way they do.
