---
inclusion: manual
---

# /velocity-ai-fix — VelocityAI Deep Analysis + Fix Protocol

You have been invoked to investigate, diagnose, and fix an issue in the VelocityAI / Flowin codebase.

**STOP. The architecture must remain as designed. No shortcuts or hacks are allowed.**

> You MUST complete every step in order. Do not skip any step.

---

## Step 1 — Load Context: Always-On Steering

These are always loaded — confirm you have them:

- **`invariants.md`** — INV-1..INV-13, locked decisions, transport contract, "do not resurrect" table.
- **`project-index.md`** — key source files, migration chain, glossary.

Then load the **domain-specific steering file** for the area you are fixing:

| Area | Steering file |
|---|---|
| `execution_engine/` | `#backend-engine.md` |
| `capabilities/` | `#backend-capabilities.md` |
| `app/api/` | `#backend-api.md` |
| `app/models/`, `alembic/` | `#backend-models-migrations.md` |
| Run screen / preview / results | `#frontend-run-screen.md` |
| Chat, SSE, transport hooks | `#frontend-chat.md` |
| Workflow, catalog, composer | `#frontend-workflow.md` |
| Shell, settings, design tokens | `#frontend-shell.md` |

---

## Step 2 — Prime the Knowledge Store

Read these four files in order (~12.5K tokens total):

```
.knowledge/surface/ARCHITECTURE.md   ← milestone, phase, enforced boundaries, ADRs in force
.knowledge/INVARIANTS.md              ← project-wide constraints
.knowledge/surface/RULES.md           ← decisions in force
.knowledge/surface/INDEX.md           ← one line per fix / issue / phase
```

Check freshness:
```bash
python3 scripts/knowledge/check.py
```

**Do NOT load `.planning/FIX-REGISTER.md`, `ISSUES-REGISTER.md`, or `IMPLEMENTATION-REGISTER.md` in full.**

---

## Step 3 — Query the Knowledge Store

```bash
# Search by symptom — the primary lookup before diagnosing anything
python3 scripts/knowledge/ctx.py "<symptom words>"

# Find every rule and prior fix touching the file you are about to change
python3 scripts/knowledge/ctx.py --for <file path>

# Active decisions for an area
python3 scripts/knowledge/ctx.py --rules <area>

# Open a specific card in full
python3 scripts/knowledge/ctx.py --show FIX-NNN
```

- If a row in `INDEX.md` matches your symptom, use `--show FIX-NNN` for the full card.
- The **next sequential Fix ID** is in `INDEX.md` header (e.g. `532 cards · fixes 168 ...`). Add 1 to the highest FIX-NNN.
- **FIX-039** (`agent_start` accumulator reset) — verify every fix does not regress it.

If `ctx.py` cannot answer, use targeted grep:
```bash
grep_search query="<symptom>" includePattern="**/.planning/FIX-REGISTER.md"
```

Check existing test coverage to avoid duplication:
```bash
grep_search query="FIX-NNN" includePattern="**/.planning/FIX-TEST-REGISTER.md"
```

---

## Step 4 — Deep Codebase Investigation

**Investigation phase only — do NOT touch any code yet.**

### Key architectural entry points

| Area | Key files | Notes |
|---|---|---|
| Pipeline execution | `backend/agents/execution_engine/engine.py` | |
| SSE down-channel | `backend/app/api/run_stream.py` | Replaces deleted `websocket.py` |
| REST up-channel | `backend/app/api/run_commands.py` | Gate/cancel/answers/messages/revisions/resume |
| Shared run infra | `backend/app/api/run_engine.py` | Relocated from `websocket.py` |
| Handoff WebSocket | `backend/app/api/websocket_handoff.py` | Only remaining WS endpoint |
| Capability registry | `backend/agents/capabilities/registry.py` | |
| Model / Bedrock config | `backend/app/core/config.py`, `backend/app/agents/model_factory.py` | |
| Frontend SSE hook | `frontend/src/hooks/useRunStream.ts` | Replaces deleted `useWebSocket.ts` |
| Frontend connection provider | `frontend/src/providers/RunConnectionProvider.tsx` | |
| Frontend pipeline state | `frontend/src/hooks/useWorkflow.ts` | |
| Frontend run screen | `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | |
| Auth / entitlements | `backend/app/api/auth.py`, `backend/app/core/entitlements.py` | |
| DB / migrations | `backend/alembic/versions/`, `backend/app/models/` | Head: 0026 |
| Scoped store / IDOR | `backend/agents/authz.py` | |
| Concierge | `backend/app/agents/chat/concierge.py` | |
| Gate pendency | `backend/agents/capabilities/gate_pendency.py` | Resume gate re-entry |

> ⚠️ **Deleted files — do NOT read, reference, or recreate:**
> `websocket.py` · `useWebSocket.ts` · `PrototypePipelineView.tsx` · `ReviewGatePanel.tsx` · `QuestionnairePanel.tsx` · `AgentProgressPanel.tsx` · `WaveTreePanel.tsx`

---

## Step 5 — Root Cause Analysis

Write this before touching any code:

```
ISSUE TYPE: [backend error / SSE/transport / frontend visual / resume / other]

ROOT CAUSE:
- What is broken and exactly why
- File and line where failure originates
- Exact sequence of events

EVIDENCE:
- File: <path> Line: <N> — <code / log>
- Trace: entry → A → B → [FAILURE] → outcome

PRIOR FIXES CHECKED:
- ctx.py "<symptom>" returned: [FIX-NNN, FIX-NNN, ...]
- FIX-039 status: confirmed not regressed

CONSTRAINTS:
- INV-1: [not affected / explain]
- INV-3: [not affected / goldens will stay clean]
- INV-12: [what existing code to reuse]
- SC-001: [not affected / explain if engine edit needed]
- Transport: [SSE + REST only — no WS run frames]
```

---

## Step 6 — Fix Plan

State what will change **before writing any code**:

```
FILES TO CHANGE:
- <path> — <what and why>

NOT CHANGING:
- <deliberately untouched files>

DELETED CODE CHECK:
- <confirmed nothing from invariants.md "What NOT to Resurrect" is being revived>

LOCKED DECISIONS RESPECTED:
- <cite from loaded steering file> — <how the fix honours it>
```

---

## Step 7 — Apply the Fix

1. One change at a time — surgical, only what the root cause requires
2. Match existing patterns — follow the surrounding code style
3. No new abstractions unless the root cause specifically requires them
4. No collateral cleanup — do not refactor unrelated code
5. Transport rule — any new run-event code uses `run_stream.py` + `run_commands.py`, never `/ws/chat`

---

## Step 8 — Verify the Fix

- Read the changed files — confirm the edit looks right in context
- Trace the fix — mentally walk the execution path
- INV-3 check: `git status --porcelain tests/agents/characterization/golden/` → empty
- Lint check: `lint-imports` still 4 kept / 0 broken (if capabilities changed)
- **FIX-039 check**: if `useWorkflow.ts` was touched, confirm `agent_start` still resets all accumulators
- Backend restart needed? Restart if backend files changed.

---

## Step 9 — Register the Fix

### 9a — Write the card (replaces manual archive-file append)

The fix entry must already be in `FIX-REGISTER.md`'s summary table. Then:
```bash
python3 scripts/knowledge/extract.py fixes --only FIX-NNN
python3 scripts/knowledge/build_index.py
python3 scripts/knowledge/check.py
```

The card is now in `.knowledge/cards/FIX-NNN.md` and searchable via `ctx.py`.

### 9b — Add a summary row to FIX-REGISTER.md

Append to the `## Fix Log` table only (no detailed entry needed — the card IS the detailed entry):
```
| FIX-<NNN> | YYYY-MM-DD | <description> | <root cause> | `<files>` | <Phase N> | INV-1/3/12/SC-001 ✅ | Done |
```

### 9c — Update the next Fix ID

Check the current highest ID in `.knowledge/surface/INDEX.md` (the `## Fixes` section lists them newest-first). The next ID = highest shown + 1.

> **Note:** The detailed `### FIX-NNN` prose entry used to go into `FIX-REGISTER.md` or a fix-archive file. It now lives in the card (`.knowledge/cards/FIX-NNN.md`) and is loaded on demand via `ctx.py --show FIX-NNN`. The monolith grows by one summary row only.

---

## Hard Constraints

**Architecture invariants (full list in `invariants.md` and `.knowledge/INVARIANTS.md`):**
- **INV-1** — kernel has NO `if pipeline_type ==` / `if spec.id ==` branches
- **INV-3** — 5 characterization golden snapshots remain byte-identical
- **INV-12** — move-don't-copy, no dual implementations
- **INV-13** — every agent on LangChain `deepagents`, never hand-rolled
- **SC-001** — new workflow = manifest + AGENT.md only, zero engine edits

**Transport:** SSE + REST is the sole run transport. `/ws/chat` is DELETED. `/ws/handoff` STAYS.

**Migrations:** Additive only. Head = **0026**. Every new table: `owner_id` + `workspace_id` NOT NULL.

**Security:** Owner-scoping key = `WorkflowRun.user_id` (NOT nullable `owner_id`). Cross-owner → 404, never 403.

---

## Reference Shortcuts

| Need | Command |
|---|---|
| Prior fixes by symptom | `python3 scripts/knowledge/ctx.py "<symptom>"` |
| Rules for a file | `python3 scripts/knowledge/ctx.py --for <path>` |
| Full card detail | `python3 scripts/knowledge/ctx.py --show FIX-NNN` |
| Current milestone/phase | `.knowledge/surface/ARCHITECTURE.md` |
| All decisions in force | `.knowledge/surface/RULES.md` |
| Full fix index | `.knowledge/surface/INDEX.md` |
| Next FIX-ID | Count from `.knowledge/surface/INDEX.md` `## Fixes` section (highest shown + 1) |
| Concurrent run / run-binding bugs | `ctx.py "concurrent run"` or `ctx.py --for dashboard/page.tsx` |
| Chat / revision / narrator bugs | `ctx.py "narrator"` or `ctx.py "revision chat"` |
| FIX-039 (CRITICAL — agent accumulator) | `ctx.py --show FIX-039` |
| Resume engine rules | `#backend-engine.md` + `ctx.py --type phase "resume"` |
| Deleted kernel leaks (L1–L13) | `ctx.py --show PHASE-07` |
| Prompt contracts | `ctx.py --show PHASE-15` |
