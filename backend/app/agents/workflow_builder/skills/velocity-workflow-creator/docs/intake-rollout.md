# Builder intake: rollout notes

## What the intake does

On the first message of a new session (no accepted draft, not an edit session), one model
call with no tools (`app/agents/workflow_builder/intake.py`, prompt `prompts/intake.v5.md`)
fills the Brief as slots (`docs/intake-slots.md`). If a blocking slot is open, its numbered
questions are the reply and the builder does not run. When the readiness rule
(`scripts/intake_readiness.py`) says ready, the builder runs with an `<intake_brief>` block
and the reply ends with a code-rendered Assumptions block; the Server_Gate also refuses an
ungated outside write and a draft that drops a stated fact. The old path still owns edit
sessions, continuing an accepted draft, and any turn whose intake call fails (logged).

## Settings (`app/core/config.py`)

| Setting | Default | Meaning |
|---|---|---|
| `BUILDER_INTAKE_V2_ENABLED` | `true` | Intake on. `false` is the rollback. |
| `BUILDER_INTAKE_MAX_ROUNDS` | `2` | Question rounds; reaching the limit means "use the defaults". |
| `BUILDER_INTAKE_EFFORT` | `default` | `default` uses the turn's effort; `highest` cost about 7x. |

**Rollback:** set `BUILDER_INTAKE_V2_ENABLED=false` and restart; nothing to migrate (the
intake state is the sandbox file `intake/state.json`, which the old path ignores).

## What to watch in week 1

| Signal | Source | Act when |
|---|---|---|
| Asked first | `builder.turn` metric: first turns whose `prompt_version` starts `intake.` | share drops 10+ points below day 1 |
| Fallback to the old path | WARNING `builder intake failed (...)` per first turn | > 2% of first turns |
| Gate rejections | `builder.gate_rejection` metric on intake sessions | > 5% of drafts, or any withheld draft reported by a user |
| Repairs | WARNING `intake repair: <slot>: <what>` | > 10% of intake calls |

## Follow-up: the builder's prompts contradict a slot the intake recorded

Pre-flip eval (Haiku): 5 of 44 manifests scored 3 on critic requirement coverage. Accepted; fix separately.

- H2 status report: the user asked for Blocked and Planned sections; the writer prompt forbids them.
- vague-b PDF summary: the user said some files are scans; the manifest keeps OCR off.
- vague-c Slack post: the brief fixes one channel; the intake step still asks for it each run.
