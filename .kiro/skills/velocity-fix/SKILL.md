---
name: velocity-fix
description: Fix a bug in VelocityAI/Flowin — deep investigation + root-cause + fix, following this repo's .planning/ workflow (registers, quick-task folder, FIX-REGISTER.md log). Use whenever asked to fix a bug, defect, or regression in this repo.
compatibility: Kiro workspace skill requiring read/write access to the Flowin repository (backend Python/FastAPI/LangGraph deepagents runtime; frontend Next.js/React/TypeScript).
metadata:
  origin: VelocityAI
  version: "1.0"
---

# VelocityAI Deep Analysis + Fix Protocol

You have been invoked to investigate, diagnose, and fix an issue in the VelocityAI / Flowin
codebase.

**STOP. The architecture must remain as designed. No shortcuts or hacks are allowed.**

> **This skill combines deep investigation AND code fixing in one workflow.**
> You MUST complete every step in order. Do not skip any step.
> Read every file completely — do not truncate or skim.
> Do not skip the register reads or the register write-back at the end — they are the entire
> point of this skill: the next person (human or agent) must be able to find what you did without
> re-deriving it, and must not accidentally re-fix or contradict it.

If the bug hasn't been described yet (no repro, symptom, or ticket ID given), ask for one before
proceeding — don't guess at what's broken.

---

## Step 1 — Read the ground truth before touching anything

Read, in this order (skim for relevance, don't dump full contents into your response):

1. `.planning/FIX-REGISTER.md` — has this exact bug (or its root cause) already been fixed?
   Search it for keywords from the bug description before reading it fully.
2. `.planning/ISSUES-REGISTER.md` — is this a known, already-triaged issue (OPEN / DEFERRED /
   MONITORING / WONTFIX)? If it's DEFERRED or WONTFIX, stop and surface that to the user instead
   of re-opening it silently.
3. `.planning/IMPLEMENTATION-REGISTER.md` — read it in full. It contains the full history of all
   phases, every file touched, every decision locked, and every piece of code deliberately
   deleted. This is mandatory — it tells you what was intentional vs. accidental, what exists vs.
   what was removed, and what constraints bind every fix.
4. `backend/CLAUDE.md` (or the relevant subsystem's `CLAUDE.md`) if the bug touches backend
   agents/engine/runner code — it documents the live architecture and commit-scope conventions
   you'll need in Step 8.

If this step turns up an existing fix or a locked decision that blocks the obvious fix, **stop
and tell the user** before writing any plan.

---

## Step 2 — Deep Codebase Investigation

**This is the investigation phase. Use ALL available read tools. Do not touch any code yet.**

Based on the user's issue, investigate the codebase deeply:

- **Read files** — read every source file relevant to the problem
- **Search for patterns** — search across multiple files for function calls, imports, class usages
- **Trace call chains** — follow the execution path from trigger to the failure point
- **Cross-reference** — check both frontend and backend when the issue spans both
- **Check logs** — if backend/frontend logs are available, read them first

### Investigation depth guide

| Issue type | Files to always read | Additional files to trace |
|---|---|---|
| Backend error / exception | The file named in the traceback | Callers of the failing function; imports; test files |
| Pipeline / agent failure | `backend/agents/execution_engine/engine.py` | The relevant capability, AGENT.md, manifest YAML |
| Frontend visual bug | The relevant component (`PreviewPanel`, `PPTPreview`, etc.) | The backend deliverable resolver, `websocket.py` |
| WebSocket / connection | `backend/app/api/websocket.py` | `frontend/src/hooks/useWebSocket.ts`, `useWorkflow.ts` |
| Model / Bedrock error | `backend/app/agents/model_factory.py`, `config.py` | The agent that failed, `entitlements.py` |
| DB / migration error | `backend/alembic/versions/` | The relevant model file |
| Prompt / output wrong | The relevant `AGENT.md` | The deliverable resolver, `_artifact.py` |

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
| OD context / template loading | `backend/agents/execution_engine/od_context.py` |
| Context providers | `backend/agents/capabilities/context_providers/` |

Do not patch symptoms. Reproduce or trace the failure to the specific file(s)/line(s)
responsible, the way every `FIX-REGISTER.md` entry does (each detailed entry states a root
cause, not just a symptom) — cite `file:line` throughout.

---

## Step 3 — Root Cause Analysis

Before writing a single line of code, write a structured root cause analysis:

```
ISSUE TYPE: [backend error / pipeline failure / frontend visual / prompt/output / other]

ROOT CAUSE:
- What is broken and exactly why
- The specific file and line where the failure originates
- The exact sequence of events that leads to the failure

EVIDENCE:
- File: <path> Line: <N> — <the specific code / log line that proves the cause>
- Trace: <entry point> → <function A> → <function B> → [FAILURE HERE] → <outcome>

PHASE CONTEXT:
- Which phase(s) own the affected files
- Any locked decisions that constrain the fix
- Any deleted code that must NOT be resurrected

CONSTRAINTS ON THE FIX:
- INV-1 (kernel knows no workflow by name): [not affected / explain if affected]
- INV-2 (no per-run state on the singleton): [not affected / explain if affected]
- INV-3 (golden parity): [not affected / explain if affected — will goldens change?]
- INV-12 (no duplication): [not affected / what existing capability to reuse]
- INV-13 (deepagents only, never hand-rolled): [not affected / explain if affected]
- SC-001 (not affected / explain if engine edit needed)
- Architecture: The fix must follow the established pattern. No shortcuts or hacks.
```

---

## Step 4 — Fix Plan

State exactly what will change before writing any code — this doubles as the scope decision and
the quick-task record.

**Decide scope:** almost every bug fix is a **quick task** (small, few files, no multi-plan
roadmap phase needed). Only escalate to a `phases/` entry if the fix is large enough to need its
own roadmap phase (rare — ask the user if genuinely unsure).

If quick task, build the folder path `.planning/quick/<YYMMDD>-<id>-<slug>`:
- `<YYMMDD>` — today's date.
- `<id>` — a random 3-character lowercase alphanumeric string. List `.planning/quick/` first so
  it doesn't collide with an existing folder.
- `<slug>` — a short kebab-case slug of the bug (e.g. `router-guardrail-data-page-link-conflict`).

Create the folder with your file-writing tool directly — don't assume a specific shell or
scripting language is available.

Write `{DATE}-{ID}-PLAN.md` inside that folder, mirroring the structure already used across
`.planning/quick/*/`:

```yaml
---
phase: quick-{DATE}-{ID}
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - <every file you expect to touch>
autonomous: true
requirements: [<ticket IDs if known, else omit or use ad-hoc tags like the bug's keyword>]

must_haves:
  truths:
    - "<a concrete, checkable statement of what 'fixed' means>"
  artifacts:
    - path: "<file>"
      provides: "<what this file's change provides>"
      contains: "<a grep-able string that proves the fix landed>"
  key_links:
    - from: "<the buggy code path>"
      to: "<the corrected behavior/consumer>"
      via: "<the mechanism of the fix>"
      pattern: "<grep-able pattern>"
---

<objective>
<what's broken, why (root cause from Step 3), and what "fixed" means concretely>
</objective>

<context>
@backend/CLAUDE.md
@.planning/IMPLEMENTATION-REGISTER.md
<@ every file you'll read or edit>
</context>

<facts_verified_during_planning>
- "<fact confirmed in Steps 1-3>, confirmed by <how you confirmed it>"
</facts_verified_during_planning>
```

Then restate the concrete fix plan:

```
FILES TO CHANGE:
- <path> — <what changes and exactly why>

WHAT IS NOT CHANGING:
- <list files/components that are deliberately left untouched>

DELETED CODE CHECK:
- <confirm no Phase X deliberately deleted code is being resurrected>

LOCKED DECISIONS RESPECTED:
- <decision from the register §5> — <how the fix honours it>
```

---

## Step 5 — Apply the Fix

Now apply the fix. Follow these rules:

1. **One change at a time** — make each edit surgical; change only what the root cause requires
2. **Match existing patterns** — read the surrounding code and follow its style exactly
3. **No new abstractions** — don't introduce new classes/modules unless the root cause specifically requires it
4. **No collateral cleanup** — do not refactor unrelated code while fixing
5. **Preserve invariants** — after every change, mentally verify INV-1/2/3/12/13/SC-001 still hold

### Hard Constraints (apply to EVERY fix — never violate)

**Architecture invariants:**
- **INV-1** — The engine kernel contains NO `if pipeline_type ==` / `if spec.id ==` branches
- **INV-2** — No per-run state lives on the singleton engine
- **INV-3** — The characterization golden snapshots remain byte-identical (unless the fix
  intentionally changes output — if so, say so explicitly)
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
  `cd backend && uv run alembic heads`

---

## Step 6 — Verify the Fix

After applying the fix, verify it is correct:

- **Read the changed file(s)** — confirm the edit looks right in context
- **Trace the fix** — mentally walk through the execution path with the fix applied
- **Check for regressions** — does this change affect any other code path?
- **Backend restart needed?** — if backend files changed and a dev server is running, tell the
  user to restart it manually (never launch a long-running dev server yourself)

Identify and run the narrowest real test suite that exercises the change. From `backend/`:

```
uv run pytest tests/agents/ -v                    # agent-runtime changes
uv run pytest tests/unit/ -v                       # engine/API/registry changes
uv run pytest tests/agents/test_guardrails.py -v   # guardrail-file changes
```

Use single-pass runs only — never `--watch` or a long-running variant.

If no automated test covers this behavior yet, add one (prefer extending an existing test file
over creating a new one) — do not close the fix out on manual verification alone if a test is
feasible.

Write `{DATE}-{ID}-VERIFICATION.md` in the quick-task folder (mirror
`.planning/quick/*/*-VERIFICATION.md`): frontmatter (`phase`, `verified: <date>`,
`status: passed|failed`), a Truths-verified table (one row per `must_haves.truths` entry, with the
command/output that proves it), and a Gaps Summary (state "No gaps" explicitly if none).

Then write `{DATE}-{ID}-SUMMARY.md` (mirror `.planning/quick/*/*-SUMMARY.md`): frontmatter
(`phase`, `plan`, `subsystem`, `tags`, `affects`, `key-files`, `decisions`, `metrics`), a
one-paragraph summary, a Tasks table (task → commit hash → files), a "What changed" section, and
"Deviations from Plan" (state "None" if the plan executed as written).

---

## Step 7 — Register the Fix

Read `.planning/FIX-REGISTER.md`'s `## Fix Log` table and find the highest existing `FIX-NNN`
number to determine the next sequential ID.

**First**, add a row to the `## Fix Log` summary table (next sequential FIX-NNN number), using the
exact same columns as the existing entries:

```
| FIX-<NNN> | YYYY-MM-DD | <one-line description> | <root cause summary> | <files changed, comma-separated> | Phase <N> | INV-1/3/12/SC-001 ✅ | Done |
```

- **Description**: one line, ticket-ID-prefixed if you have one (e.g. `"KAN-123: ..."`).
- **Root Cause**: the Step 3 finding, stated precisely (this is what future searches will match on).
- **Files Changed**: every file from `files_modified`.
- **Phase Involved**: the relevant `phases/` entry if the bug lives in code that phase shipped,
  else the `quick-{DATE}-{ID}` id itself.
- **Invariants**: reuse this repo's existing invariant tags (`INV-1/3/12/SC-001` etc.) or "N/A".
- **Status**: `Done`.

**Then**, append a detailed entry under `## Detailed Fix Entries`:

```markdown
### FIX-<NNN> — <Short Title>

**Date:** YYYY-MM-DD
**Triggered by:** `velocity-fix <user's original request>`

#### Root Cause
<Specific explanation — file, line, why it fails, the exact trace>

#### Phase Context
- **Phase(s) involved:** Phase <N> — <name>
- **Relevant register section:** `_register-parts/<NN-name>.md` §<N>
- **Deleted code verified (not resurrected):** <yes/no — what was checked>
- **Locked decisions respected:** <list any §5 decisions that constrained the fix>

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `<path>` | <what changed> | <rationale> |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): <not affected / verified clean>
- **INV-3** (golden parity): <not affected / verified — output unchanged>
- **INV-12** (no duplication): <verified — used existing capability X / not applicable>
- **SC-001** (zero engine edits for new workflows): <not affected / engine edit justified>

#### Verification
<How was the fix confirmed correct?>

#### Notes
<Gotchas, follow-up items, things to watch in future fixes.>
```

Never mark this step optional — an unregistered fix is, by this repo's own stated convention,
effectively undiscoverable to the next person who searches `FIX-REGISTER.md` before starting
similar work.

---

## Step 8 — Commit convention

If `backend/CLAUDE.md` is in scope (backend agent-runtime changes), use its scoped format:
`fix(<scope>): <description>` where `<scope>` is one of `agents/engine/runner/prompts/guardrails/
loader/factory/registry/tools/sandbox/tests` (see `backend/CLAUDE.md`'s Commit Conventions table).
Otherwise use a plain conventional-commit `fix(<area>): <description>`. **Only commit if the user
asked you to** — otherwise present the diff + register entry and let them decide.

---

## Reference Shortcuts

| Need | Where to look |
|---|---|
| Which capability handles X? | Phase 4 §3 (registry names), Phase 7–8 §3 (impls) |
| Sandbox / RUNS_ROOT behaviour | Phase 9 §5 + `backend/app/agents/sandbox.py` |
| AWS credential mirroring | Phase 9 §7 + `backend/app/core/config.py` bottom block |
| WebSocket / pipeline dispatch | Phase 16 §3 + `backend/app/api/websocket.py` |
| DB models & migrations | Phase 5 §3 (0014–0015), Phase 9 (0017), Phase 10 (0018), Phase 11 (0019), Phase 12 (0020), Phase 21 (0021), Phase 22 (0022), Phase 22 WR-02 (0023) |
| Frontend WS hook | Phase 12 §3 + `frontend/src/hooks/useWebSocket.ts` |
| Deleted code (F1–F5) | Phase 8 §4 — do not re-add inline factory code |
| Deleted kernel leaks (L1–L13) | Phase 7 §4 — do not re-add `if pipeline_type` branches |
| OD template / context loading | `backend/agents/execution_engine/od_context.py` |
| PPT / prototype deliverable | `backend/agents/capabilities/deliverables/ppt.py`, `_artifact.py` |
| Live verification evidence | `.planning/live-verification/` |

---

## Guardrails for this skill

- Never invent a Fix ID or quick-task ID that collides with an existing one — always check first.
- Never skip Step 1 — the registers exist specifically to prevent duplicate/contradictory fixes.
- Never mark Step 7 (register append) optional.
- If the "bug" turns out to be a locked, intentional decision (per Step 1), say so and stop — do
  not fix around a locked decision without flagging it.
