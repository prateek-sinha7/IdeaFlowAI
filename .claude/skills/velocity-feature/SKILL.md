---
name: velocity-feature
description: Implement a new feature in VelocityAI/Flowin — deep investigation of existing extension points + design + implementation, following this repo's .planning/ workflow (registers/roadmap, quick-task or full-phase folder, IMPLEMENTATION-REGISTER.md/ROADMAP.md log). Use whenever asked to add a new feature, agent, pipeline, or capability to this repo.
origin: VelocityAI
---

# VelocityAI Feature-Implementation Workflow

You have been invoked to implement a new feature in the VelocityAI / Flowin codebase.

**STOP. The architecture must remain as designed. No shortcuts or hacks are allowed.**

> This skill combines deep investigation of existing extension points AND implementation in one
> workflow. It follows the same conventions already behind the 22+ completed phases in
> `.planning/IMPLEMENTATION-REGISTER.md` and the `phases/`/`quick/` folders — check the registers
> and roadmap first, plan (as a quick task or a full phase), implement using this repo's existing
> extension points, verify, and log the feature so the next person (human or agent) can find it
> before starting related work.
>
> Do not skip the register reads or the register write-back at the end — they are the entire
> point of this skill.

If the feature hasn't been described yet, ask for a description before proceeding — don't guess
at scope.

---

## Step 1 — Read the ground truth before designing anything

Read, in this order (skim for relevance, don't dump full contents into your response):

1. `.planning/PROJECT.md` — does this feature already exist as a `[ ]` (planned but not built) or
   `[x]` (already built) requirement? Don't re-plan something already tracked — extend it.
2. `.planning/ROADMAP.md` — is there already a phase (in progress or planned) that owns this area?
   Check the "Global invariants" section too — every new feature must not violate INV-1 (kernel/
   engine stays workflow-agnostic — no `if pipeline_type == "..."` branches), INV-2 (no per-run
   state on the singleton), INV-3 (behavior/event parity for anything not intentionally changed),
   INV-12 (move-don't-copy — don't fork code to add a variant), INV-13 (deepagents only — never
   hand-rolled), or SC-001 (a new workflow = manifest + AGENT.md only, zero engine edits).
3. `.planning/IMPLEMENTATION-REGISTER.md` (Overview + the relevant phase's `_register-parts/
   <NN-slug>.md`) — what capability/registry/manifest surface already exists that this feature
   should plug into, rather than duplicate? This repo is built around a capability-registry /
   declarative-manifest pattern (see `backend/CLAUDE.md`) specifically so new features are
   additive (new `AGENT.md` + `workflow.yaml` entries, new registered capability) rather than new
   kernel branches.
4. `.planning/STATE.md` — what's the current milestone and active phase? A large new feature
   mid-milestone may need to be sequenced, not just bolted on.
5. `backend/CLAUDE.md` (or the relevant subsystem's `CLAUDE.md`) — read "Adding an Agent" /
   "Adding a Pipeline" / "Adding a Guardrail" if this feature is agent-runtime shaped; it
   documents the exact required steps (AGENT.md schema, registry.py wiring, workflow.yaml
   manifest, test coverage) so you don't reinvent or half-implement the extension pattern.

If Step 1 shows this is already planned, already built, or would violate a locked invariant —
**stop and tell the user** before writing a plan. If mid-Step-1 you discover this "new feature"
is actually a bug fix to existing behavior, use the `velocity-fix` skill instead.

---

## Step 2 — Deep Investigation of Existing Extension Points

**This is the investigation phase. Use ALL available read tools before designing anything.**

Read the actual source of the extension points this feature will plug into — don't assume from
names. Search across multiple files for the registry/manifest pattern already in use; trace how
an existing, similar feature was wired end-to-end (registry entry → manifest → AGENT.md/component
→ FE consumer, if applicable).

### Investigation depth guide

| Feature type | Files to always read | Additional files to trace |
|---|---|---|
| New agent | `backend/CLAUDE.md` §"Adding an Agent"; an existing `AGENT.md` in the same pipeline | `agents/registry.py`'s `PIPELINE_AGENTS`; the workflow's `workflow.yaml` |
| New pipeline | `backend/CLAUDE.md` §"Adding a Pipeline"; `agents/registry.py`'s `SUPPORTED_PIPELINE_TYPES` | The nearest existing `agents/workflows/<id>/workflow.yaml` as a template |
| New guardrail | `backend/CLAUDE.md` §"Adding a Guardrail"; `tests/agents/test_guardrails.py` | An existing guardrail file (structural constraints: <60 lines, no fenced code blocks, no frontmatter) |
| New capability / registry surface | `backend/agents/capabilities/registry.py` | The capability port/interface it should implement; existing sibling capabilities |
| Frontend surface | The nearest existing component with the same shape | `frontend/src/hooks/useWorkflow.ts`, `useWebSocket.ts` for pipeline-state wiring |

### Key architectural entry points

| Area | Key files |
|---|---|
| Pipeline execution | `backend/agents/execution_engine/engine.py` |
| WebSocket / pipeline dispatch | `backend/app/api/websocket.py` |
| Capability registry | `backend/agents/capabilities/registry.py` |
| Model / Bedrock config | `backend/app/core/config.py`, `backend/app/agents/model_factory.py` |
| Sandbox / file isolation | `backend/app/agents/sandbox.py` |
| Workflow manifests | `backend/agents/workflows/<name>/workflow.yaml` |
| Frontend pipeline state | `frontend/src/hooks/useWorkflow.ts`, `frontend/src/hooks/useWebSocket.ts` |
| Frontend rendering | `frontend/src/components/preview/PreviewPanel.tsx` |
| Auth / entitlements | `backend/app/api/auth.py`, `backend/app/core/entitlements.py` |
| DB / migrations | `backend/alembic/versions/`, `backend/app/models/` |
| Artifact graph | `backend/agents/artifacts/graph.py` |

---

## Step 3 — Extension-Point Analysis

Before writing a plan, state explicitly which existing surface this feature extends and why
nothing needs to be duplicated:

```
FEATURE TYPE: [new agent / new pipeline / new guardrail / new capability / FE surface / other]

EXTENSION POINT:
- The existing registry/manifest/capability this plugs into, and why (cite file:line)
- The closest existing analog already wired end-to-end (name it)

CONSTRAINTS ON THE DESIGN:
- INV-1 (kernel knows no workflow by name): [not affected / explain if affected]
- INV-2 (no per-run state on the singleton): [not affected / explain if affected]
- INV-3 (event/behavior parity for unrelated flows): [not affected / explain if affected]
- INV-12 (move-don't-copy — no forked variant of existing code): [confirmed clean / what's reused]
- INV-13 (deepagents only, never hand-rolled): [not affected / explain if affected]
- SC-001 (manifest + AGENT.md only, zero engine edits): [confirmed / engine edit justified — why]
```

Do not add speculative flexibility beyond what this feature needs (no unused config flags, no
half-wired abstractions "for later").

---

## Step 4 — Decide scope, then write the plan

- **Quick task** (`.planning/quick/`): a self-contained feature addition that plugs into
  existing capabilities/registries with no new roadmap phase needed — e.g. a new agent in an
  existing pipeline, a new guardrail, a new API endpoint reusing existing patterns. Most feature
  work should be this.
- **Full phase** (`.planning/phases/`): a multi-plan body of work that earns its own place in
  `.planning/ROADMAP.md`'s phase table — new subsystem, new workflow type, cross-cutting
  architecture change. Only choose this if the feature genuinely doesn't fit in one focused
  quick task. If unsure, default to quick task and say so — it's reversible; a premature phase
  is not.

### If quick task — create the folder

```bash
DATE=$(date +%y%m%d)
ID=$(python3 -c "import random,string;print(''.join(random.choices(string.ascii_lowercase+string.digits,k=3)))")
SLUG="<short-kebab-slug-of-the-feature>"
DIR=".planning/quick/${DATE}-${ID}-${SLUG}"
mkdir -p "$DIR"
```

### If full phase — create the folder and reserve the number

```bash
NEXT=$(ls .planning/phases | grep -oE '^[0-9]+' | sort -n | tail -1)
NEXT=$(printf "%02d" $((10#$NEXT + 1)))
SLUG="<short-kebab-slug-of-the-feature>"
DIR=".planning/phases/${NEXT}-${SLUG}"
mkdir -p "$DIR"
```
You'll also add a row to `.planning/ROADMAP.md`'s Phases table and create
`.planning/_register-parts/${NEXT}-${SLUG}.md` in Step 7.

Write the `PLAN.md` (same structure `.planning/quick/*/PLAN.md` already uses — mirror it exactly,
see an existing one for the literal format. For a full phase, one `PLAN.md` per plan/wave,
numbered `01`, `02`, ... under the phase folder):

```yaml
---
phase: quick-{DATE}-{ID}          # or phases/{NEXT}-{slug}, plan: 01 for the first plan
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - <every file you expect to touch or create>
autonomous: true
requirements: [<requirement/ticket IDs this feature satisfies>]

must_haves:
  truths:
    - "<a concrete, checkable statement of what 'done' means for this feature>"
  artifacts:
    - path: "<file>"
      provides: "<what it provides>"
      contains: "<grep-able proof>"
  key_links:
    - from: "<the new capability>"
      to: "<what consumes/registers it>"
      via: "<the wiring mechanism — e.g. registry.py entry, workflow.yaml step>"
      pattern: "<grep-able pattern>"
---

<objective>
<what this feature is, why (link back to the REQUIREMENTS.md/PROJECT.md item or ticket), and
what "done" looks like>
</objective>

<context>
@backend/CLAUDE.md
@.planning/IMPLEMENTATION-REGISTER.md
@.planning/ROADMAP.md
<@ every file you'll read or create/edit — for agent-runtime features this typically includes
  the relevant agents/prompts/*/AGENT.md, agents/registry.py, agents/workflows/*/workflow.yaml>
</context>

<facts_verified_during_planning>
- "<what you confirmed in Steps 1-3, so execution doesn't re-derive it>"
</facts_verified_during_planning>
```

---

## Step 5 — Implement

Follow this repo's extension patterns rather than inventing new ones:

- **New agent** → `backend/CLAUDE.md` §"Adding an Agent" (AGENT.md schema, `context_from`/
  `produces`/`consumes`, then wire into `registry.py`'s `PIPELINE_AGENTS`).
- **New pipeline** → `backend/CLAUDE.md` §"Adding a Pipeline" (`SUPPORTED_PIPELINE_TYPES`,
  `PIPELINE_AGENTS` entry, **required** `agents/workflows/<id>/workflow.yaml` manifest — the
  engine raises `FileNotFoundError` without it).
- **New guardrail** → `backend/CLAUDE.md` §"Adding a Guardrail" (structural constraints: <60
  lines, no fenced code blocks, no frontmatter — enforced by `test_guardrails.py`).
- **New capability/registry surface** (engine-level) → check `INV-1`/`INV-4` in
  `.planning/ROADMAP.md` first: the kernel must stay name-free; the feature should be a
  registered capability, not a new `if pipeline_type ==` branch.

One change at a time; match the surrounding code's existing style; no new abstractions unless the
feature specifically requires one; no collateral cleanup of unrelated code.

### Hard Constraints (apply to EVERY feature — never violate)

**Architecture invariants:**
- **INV-1** — The engine kernel contains NO `if pipeline_type ==` / `if spec.id ==` branches
- **INV-2** — No per-run state lives on the singleton engine
- **INV-3** — Behavior/event parity is preserved for anything not intentionally changed
- **INV-12** — Move-don't-copy. Do NOT duplicate code that already exists as a registered capability
- **INV-13** — Every agent runs on LangChain `deepagents`. Never hand-roll an agent loop
- **SC-001** — A new workflow = manifest + AGENT.md only, zero engine edits

**Security:**
- AWS credentials come from `os.environ` (mirrored from `Settings` in `config.py`)
- Sandbox path checks use `os.sep` (not `/`) for Windows compatibility
- Every new DB table carries `owner_id` + `workspace_id`

**Migrations:**
- Additive only — no DROP, no ALTER of existing columns
- Check the current Alembic head before chaining a new migration:
  `cd backend && python3.11 -m alembic heads`

---

## Step 6 — Verify

Read the changed/new file(s) back and confirm they look right in context; trace how the new
capability gets discovered/dispatched end-to-end; check for regressions in the extension point
you plugged into.

```bash
cd backend
python3.11 -m pytest tests/agents/ -v     # new agent/registry/guardrail work
python3.11 -m pytest tests/unit/ -v       # engine/API/manifest work
```

Add tests for the new behavior (schema validation, registry ordering, guardrail structure, or
engine/manifest behavior as applicable) rather than relying on manual verification alone.

Write `{DATE}-{ID}-VERIFICATION.md` (mirror `.planning/quick/*/*-VERIFICATION.md` or a phase's own
verification doc): frontmatter (`phase`, `verified: <date>`, `status: passed|failed`), a
Truths-verified table (one row per `must_haves.truths` entry with the evidence that proves it),
and a Gaps Summary (state "No gaps" explicitly if none).

Then write `{DATE}-{ID}-SUMMARY.md` (mirror `.planning/quick/*/*-SUMMARY.md` or the phase's own
summary convention): frontmatter (`phase`, `plan`, `subsystem`, `tags`, `affects`, `key-files`,
`decisions`, `metrics`), a one-paragraph summary, a Tasks table (task → commit → files), "What
changed", and "Deviations from Plan" (state "None" if the plan executed as written).

---

## Step 7 — Register the feature

**If quick task:** append an entry summarizing the addition to
`.planning/IMPLEMENTATION-REGISTER.md` under the nearest relevant phase section (or as a
"post-milestone quick addition" note if it doesn't belong to any existing phase) — follow that
phase's existing 8-part format (goal, per-plan table, capabilities added, deletions, locked
decisions, verification, gotchas, file index) at whatever level of detail fits a quick addition.

**If full phase:**
1. Add a row to `.planning/ROADMAP.md`'s Phases table, following the existing `[x]`/`[ ]`
   checkbox + one-line description + completion-date convention.
2. Create `.planning/_register-parts/${NEXT}-${slug}.md` following the existing 8-part phase
   format (see any existing file in `.planning/_register-parts/` for the literal structure).
3. Add the corresponding row to `.planning/IMPLEMENTATION-REGISTER.md`'s "Phase Navigation"
   table pointing at that new `_register-parts` file.
4. Update `.planning/STATE.md`'s progress counters (`total_phases`/`completed_phases`/
   `total_plans`/`completed_plans`) and `last_activity` if this phase is now complete.
5. If the feature satisfies a `[ ]` item in `.planning/PROJECT.md`'s Active requirements list,
   flip it to `[x]`.

Never mark this step optional — an unregistered feature is, by this repo's own stated convention,
effectively undiscoverable to the next person who checks the roadmap/register before starting
related work.

---

## Step 8 — Commit convention

If `backend/CLAUDE.md` is in scope, use its scoped format: `feat(<scope>): <description>` where
`<scope>` is one of `agents/engine/runner/prompts/guardrails/loader/factory/registry/tools/
sandbox/tests`. Otherwise use plain conventional-commit `feat(<area>): <description>`. **Only
commit if the user asked you to** — otherwise present the diff + register entry and let them
decide. Never commit directly to `main` — this repo's convention is PR + review.

---

## Guardrails for this skill

- Never skip Step 1 — building a feature that already exists (or contradicts a locked decision
  in `IMPLEMENTATION-REGISTER.md`) is the exact failure this register is designed to prevent.
- Prefer the smallest extension point this repo already exposes (new `AGENT.md` /
  `workflow.yaml` / guardrail / registered capability) over new engine branches — this is a
  hard architectural invariant here (INV-1), not a style preference.
- Never leave a full phase un-registered — `ROADMAP.md`, `_register-parts/`, and
  `IMPLEMENTATION-REGISTER.md`'s navigation table must all point at each other consistently.
- If mid-Step-1 you discover this "new feature" is actually a bug fix to existing behavior,
  use the `velocity-fix` skill instead.
