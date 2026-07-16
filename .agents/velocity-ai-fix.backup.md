---
inclusion: manual
---

# /velocity-ai-fix — VelocityAI Deep Analysis + Fix Protocol

You have been invoked to investigate, diagnose, and fix an issue in the VelocityAI / Flowin codebase.

**STOP. The architecture must remain as designed. No shortcuts or hacks are allowed.**

> **This command combines deep investigation AND code fixing in one workflow.**
> You MUST complete every step in order. Do not skip any step.
> Read every file completely — do not truncate or skim.

---

## Step 1 — Read the Full Implementation Register

Read the complete Implementation Register below. It contains the full history of all phases, every file touched, every decision locked, and every piece of code deliberately deleted. This is mandatory — it tells you what was intentional vs accidental, what exists vs what was removed, and what constraints bind every fix.

#[[file:.planning/IMPLEMENTATION-REGISTER.md]]

---

## Step 2 — Deep Codebase Investigation

**This is the investigation phase. Use ALL available read tools. Do not touch any code yet.**

Based on the user's issue, investigate the codebase deeply:

- **Read files** — read every source file relevant to the problem
- **Search for patterns** — grep across multiple files for function calls, imports, class usages
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
- INV-1: [not affected / explain if affected]
- INV-3: [not affected / explain if affected — will goldens change?]
- INV-12: [no duplication needed / what existing capability to reuse]
- SC-001: [not affected / explain if engine edit needed]
- Architecture: The fix must follow the established pattern. No shortcuts or hacks.
```

---

## Step 4 — Fix Plan

State exactly what will change before writing any code:

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
5. **Preserve invariants** — after every change, mentally verify INV-1/3/12/13 and SC-001 still hold

---

## Step 6 — Verify the Fix

After applying the fix, verify it is correct:

- **Read the changed file(s)** — confirm the edit looks right in context
- **Trace the fix** — mentally walk through the execution path with the fix applied
- **Check for regressions** — does this change affect any other code path?
- **Backend restart needed?** — if backend files changed, restart the server

---

## Step 7 — Register the Fix

Append an entry to `.planning/FIX-REGISTER.md`.

**First**, add a row to the summary table (next sequential FIX-NNN number):
```
| FIX-<NNN> | YYYY-MM-DD | <one-line description> | <root cause summary> | <files changed, comma-separated> | Phase <N> | INV-1/3/12/SC-001 ✅ | Done |
```

**Then**, append a detailed entry under `## Detailed Fix Entries`:

```markdown
### FIX-<NNN> — <Short Title>

**Date:** YYYY-MM-DD
**Triggered by:** `#velocity-ai-fix <user's original request>`

#### Root Cause
<Specific explanation — file, line, why it fails, the exact trace>

#### Phase Context
- **Phase(s) involved:** Phase <N> — <name>
- **Relevant register section:** `_register-parts/<NN>-<name>.md` §<N>
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

---

## Hard Constraints (apply to EVERY fix — never violate)

**Architecture invariants:**
- **INV-1** — The engine kernel contains NO `if pipeline_type ==` / `if spec.id ==` branches
- **INV-3** — The 5 characterization golden snapshots remain byte-identical
- **INV-12** — Move-don't-copy. Do NOT duplicate code that already exists as a registered capability
- **INV-13** — Every agent runs on LangChain `deepagents`. Never hand-roll an agent loop
- **SC-001** — A new workflow = manifest + AGENT.md only, zero engine edits

**Security:**
- AWS credentials come from `os.environ` (mirrored from `Settings` in `config.py`)
- Sandbox path checks use `os.sep` (not `/`) for Windows compatibility
- Every new DB table carries `owner_id` + `workspace_id`

**Migrations:**
- Additive only — no DROP, no ALTER of existing columns
- Current schema head is `0023`. Any new migration must chain from `0023`

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
