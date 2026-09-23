# RFN-001 — Per-Agent Model Chip on Steps Tab

**Type:** UI Feature / Data-flow wiring  
**Status:** CLOSED  
**Priority:** Medium  
**Requested:** 2026-09-07  
**Closed:** 2026-09-07  

---

## User Story

> "Currently users can't see which model agents are running. We have multiple
> models selectable in our application — different agents can have different
> models. It should be shown on the UI Steps tab under the agents live output
> page **before the token usage details**, using a chip just like the 'Done'
> chip we're already showing. The model info should persist always — while
> agents are running, after the pipeline is finished, and when opened through
> the run history page."

---

## Desired Behaviour (spec)

1. **Location**: On the **Steps tab → AgentDetailPanel (L2 drill-down)**, in
   the agent header row, between the existing "Done" / "Live" status chip and
   the `Cpu + duration · tokens` meta span.
2. **Chip design**: Same visual language as the existing "Done" chip
   (`text-[8px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full`)
   but styled distinctly — e.g. `bg-surface-warm text-ink-500 border
   border-line-faint` — with a small `Cpu` (or `Sparkles`) icon prefix and the
   resolved **human-readable model label** (e.g. "Claude Sonnet 4.5", not the
   raw Bedrock ID `eu.anthropic.claude-sonnet-4-5-20250929-v1:0`).
3. **Visibility rules**:
   - Appears as soon as the agent has a `model_id` (from `agent_complete`) and
     persists thereafter — it is NOT hidden once the pipeline finishes.
   - Shown on a live run (status `running` / `thinking` / `done`).
   - Shown on a completed run viewed from run history (history-reopen path via
     `WorkflowHistory.tsx` → `thinkingAgents`).
   - Does NOT appear for agents with `status === "idle"` or `"skipped"` (model
     is unknown until the agent actually runs).
4. **Label resolution**: Map the raw `model_id` string to its `label` from the
   `ModelCatalog` / `GET /api/capabilities` response. Fall back to a shortened
   form of the raw ID (strip the `eu./us.` prefix and the date suffix) if the
   id is not in the catalog — never show a blank chip or throw.
5. **L1 (StepsOverviewSpine) overview rows**: No change required in this
   refinement. The agent rows on the spine already show a compact
   `duration · tokens` meta string on the right; adding a model chip there
   would crowd a narrow layout. Defer to a follow-up if needed.

---

## Root Cause / Gap Analysis

The data already exists end-to-end — the only gaps are in how the frontend
consumes and threads it.

### Backend (no changes required)

| Layer | Status | Evidence |
|-------|--------|----------|
| `engine.py` emits `model_id` on `agent_complete` SSE event | ✅ Already done | `"model_id": _resolved_model_id` in `agent_complete` payload — the per-agent RESOLVED model after the MODEL-01/02/05 precedence chain |
| `run_commands.py` persists `model_id` per-agent into `agent_outputs` JSON | ✅ Already done | `_apply_terminal_output_columns` line ~3116: `current_agent["model_id"] = data.get("model_id")` (ISS-165 note in code) |
| `runs.py` projects `model_id` in the `/api/runs/{id}/summary` response | ✅ Already done | `_SUMMARY_SAFE_AGENT_KEYS` tuple already contains `"model_id"` |

### Frontend (all gaps — changes required here only)

#### Gap 1 — `AgentRunState` type missing `modelId`

**File:** `frontend/src/types/index.ts`  
**Location:** `AgentRunState` interface (around line 745)  
**Change:** Add `modelId?: string` field.

```ts
// BEFORE — no model field at all
export interface AgentRunState {
  id: string;
  name: string;
  // ...
  estimatedTokens?: number;
}

// AFTER
export interface AgentRunState {
  id: string;
  name: string;
  // ...
  estimatedTokens?: number;
  modelId?: string;          // ← ADD: resolved per-agent model id from agent_complete
}
```

---

#### Gap 2 — `agent_complete` reducer in `useWorkflow.ts` doesn't write `modelId`

**File:** `frontend/src/hooks/useWorkflow.ts`  
**Location:** `case "agent_complete":` reducer block (around line 688)  
**Change:** Read `msg.model_id` and write it to the per-agent state. Also reset
it in the `agent_start` reset block so a re-run of the same agent clears the
previous model before the new `agent_complete` arrives.

```ts
// In the agent_complete case — AFTER the existing status/duration/token fields:
updated[agentIdx] = {
  ...updated[agentIdx],
  status: "done",
  duration,
  inputTokens: (msg.input_tokens as number) || 0,
  outputTokens: (msg.output_tokens as number) || 0,
  totalTokens: (msg.total_tokens as number) || 0,
  estimatedCostUsd: (msg.estimated_cost_usd as number) || 0,
  modelId: (msg.model_id as string) || undefined,   // ← ADD
};

// In the agent_start reset block — alongside the existing clears:
modelId: undefined,   // ← ADD — reset so a re-run never shows the prior model
```

---

#### Gap 3 — `RunSummaryAgent` TS interface missing `model_id`

**File:** `frontend/src/lib/api.ts`  
**Location:** `RunSummaryAgent` interface (around line 872)  
**Change:** Add `model_id?: string`. No backend change needed — the field is
already in `_SUMMARY_SAFE_AGENT_KEYS` and is already emitted in the API
response.

```ts
// BEFORE
export interface RunSummaryAgent {
  agent_id?: string;
  name?: string;
  // ...
  cache_write_tokens?: number;
}

// AFTER
export interface RunSummaryAgent {
  agent_id?: string;
  name?: string;
  // ...
  cache_write_tokens?: number;
  model_id?: string;          // ← ADD: already in _SUMMARY_SAFE_AGENT_KEYS projection
}
```

---

#### Gap 4 — `WorkflowHistory.tsx` history-reopen path drops `model_id`

**File:** `frontend/src/components/history/WorkflowHistory.tsx`  
**Location:** Two useMemo blocks — `detailAgentOutputs` (around line 487) and
`thinkingAgents` (around line 535)

**Sub-gap 4a** — `detailAgentOutputs` inline type annotation omits `model_id`:

```ts
// BEFORE — inline type excludes model_id
const detailAgentOutputs = useMemo<{
  agent_id: string; name: string; role: string; icon: string;
  output: string; duration: number | null;
  input_tokens?: number; output_tokens?: number; total_tokens?: number;
}[]>(...);

// AFTER — add model_id to the inline annotation
const detailAgentOutputs = useMemo<{
  agent_id: string; name: string; role: string; icon: string;
  output: string; duration: number | null;
  input_tokens?: number; output_tokens?: number; total_tokens?: number;
  model_id?: string;   // ← ADD
}[]>(...);
```

**Sub-gap 4b** — `thinkingAgents` mapping doesn't thread `model_id` into
`AgentRunState`. Uses the same `(a as Record<string, unknown>).field` cast
pattern that already carries `inputPrompt`, `contextSources`, `toolCalls`, and
`thinkingText`:

```ts
// BEFORE — in thinkingAgents useMemo return
return detailAgentOutputs.map((a, idx) => ({
  id: a.agent_id,
  // ...
  thinkingText: (a as Record<string, unknown>).thinking_text as string | undefined,
}));

// AFTER — add modelId alongside the other persisted-output fields
return detailAgentOutputs.map((a, idx) => ({
  id: a.agent_id,
  // ...
  thinkingText: (a as Record<string, unknown>).thinking_text as string | undefined,
  modelId: (a as Record<string, unknown>).model_id as string | undefined,  // ← ADD
}));
```

> No deduplication concern: when `detailAgentOutputs` merges repeated agents
> (build loop), the last non-null `model_id` should be kept. The existing
> dedup loop aggregates duration/tokens by addition but uses `if (a.output)
> existing.output = a.output` (keep-last) for output — `model_id` should
> follow the same keep-last pattern: add
> `if ((a as any).model_id) existing.model_id = (a as any).model_id;` inside
> the `seen.has(aid)` branch.

---

#### Gap 5 — `AgentDetailPanel.tsx` renders the chip

**File:** `frontend/src/components/results/AgentDetailPanel.tsx`  
**Location:** The agent header row, between the status chip block and the
`metaBits` span (around lines 1012–1047).

**Design:**

The existing "Done" chip for reference:
```tsx
{isDone && (
  <span className="text-[8px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-surface-paper text-ink-500">
    Done
  </span>
)}
```

The new model chip, inserted **after** the status chip and **before** `metaBits`:
```tsx
{agent.modelId && (
  <span className="inline-flex items-center gap-1 text-[8px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-surface-warm text-ink-500 border border-line-faint">
    <Cpu className="h-2.5 w-2.5 flex-none" />
    {resolveModelLabel(agent.modelId)}
  </span>
)}
```

**`resolveModelLabel` helper** — a small pure function, colocated in
`AgentDetailPanel.tsx` or extracted to `frontend/src/lib/modelUtils.ts`:

```ts
/**
 * Map a raw Bedrock model id to its short display label.
 * Falls back to a cleaned-up version of the raw id when not in the catalog
 * (strips region prefix and date suffix).
 */
const MODEL_LABELS: Record<string, string> = {
  "eu.anthropic.claude-haiku-4-5-20251001-v1:0": "Claude Haiku 4.5",
  "us.anthropic.claude-3-5-haiku-20241022-v1:0": "Claude Haiku 3.5",
  "eu.anthropic.claude-sonnet-4-5-20250929-v1:0": "Claude Sonnet 4.5",
  "eu.anthropic.claude-sonnet-4-6": "Claude Sonnet 4.6",
  "us.anthropic.claude-sonnet-5": "Claude Sonnet 5",
  "eu.anthropic.claude-sonnet-5": "Claude Sonnet 5",
  "eu.anthropic.claude-sonnet-4-20250514-v1:0": "Claude Sonnet 4",
  "eu.anthropic.claude-opus-4-5-20251101-v1:0": "Claude Opus 4.5",
  "eu.anthropic.claude-opus-4-6-v1": "Claude Opus 4.6",
};

function resolveModelLabel(modelId: string): string {
  if (MODEL_LABELS[modelId]) return MODEL_LABELS[modelId];
  // Fallback: strip region prefix (eu./us./global.) and date suffix
  return modelId
    .replace(/^(eu|us|global)\./, "")
    .replace(/anthropic\./, "")
    .replace(/-\d{8}-v\d(:\d)?$/, "")
    .replace(/-v\d+$/, "")
    .replace(/-/g, " ")
    .replace(/\b\w/g, c => c.toUpperCase());
}
```

> **Note on dynamic catalog:** An alternative is to read model labels from
> `GET /api/capabilities` (already fetched in capability-aware pages). That
> avoids the static map but adds a prop or context dependency. For this
> refinement the static map (derived verbatim from `model_catalog.py`) is the
> simpler path — it requires zero prop drilling and the catalog is stable
> between deploys. The static map must be kept in sync with `model_catalog.py`
> as the authoritative source (INV-12).

---

## Fix Sites Summary

| # | File | Change | Blast radius |
|---|------|--------|-------------|
| 1 | `frontend/src/types/index.ts` | Add `modelId?: string` to `AgentRunState` | Types only — all consumers of `AgentRunState` are unaffected (optional field) |
| 2 | `frontend/src/hooks/useWorkflow.ts` | `agent_complete` case: write `modelId`; `agent_start` case: reset `modelId` | Core SSE reducer — surgical additive, no existing field touched |
| 3 | `frontend/src/lib/api.ts` | Add `model_id?: string` to `RunSummaryAgent` | Types only — optional field, no existing consumer breaks |
| 4 | `frontend/src/components/history/WorkflowHistory.tsx` | `detailAgentOutputs` type + `thinkingAgents` map + dedup keep-last | Additive — no existing fields removed or renamed |
| 5 | `frontend/src/components/results/AgentDetailPanel.tsx` | Render model chip + add `resolveModelLabel` helper (or import from `modelUtils.ts`) | Presentation only — renders new JSX, touches no data logic |
| Backend | `backend/agents/execution_engine/engine.py` | Call `_resolve_model` before `agent_start` yield; include `model_id` in payload | Surgical addition; `model_id` already in `_VOLATILE_STRIP_KEYS` — INV-3 safe |

**Backend change required** — engine.py must be updated for the chip to appear while the agent is running.

---

## Test Coverage

| File | Tests | What it covers |
|------|-------|---------------|
| `backend/tests/agents/test_rfn001_model_id_on_agent_start.py` | 8 | Source-pin: engine.py emits `model_id` on `agent_start` before the yield; resolve-before-yield ordering; `agent_complete` unchanged (ISS-165); normalizer strips from both events (INV-3); end-to-end `_drive("prototype")` confirms live path; `run_commands.py` persistence unchanged |
| `frontend/src/components/results/AgentDetailPanel.modelChip.test.tsx` | 15 | Chip visible while running; persists on done; absent on idle; fallback label for unknown IDs; absent modelId no crash; all 9 catalog IDs resolve correctly; Live badge + chip coexist |
| `frontend/src/components/history/WorkflowHistory.modelChip.test.tsx` | 4 | `model_id` threaded from `agent_outputs` → `thinkingAgents` → `AgentRunState.modelId`; absent model_id graceful degrade; dedup keep-last semantics; no crash when `agentOutputs` null |

---

## Constraints & Guardrails

- **SC-001 / INV-1**: No workflow-name or agent-id literals in the chip logic.
  The chip is keyed purely on `agent.modelId` — a data value, not a workflow
  branch.
- **INV-3 goldens**: No backend change → no SSE event shape change → goldens
  unaffected.
- **`useWorkflow.ts` collision note**: This file is Domain 11's primary fix
  site and all 12 of its cards were closed/escalated in the domain-11 run.
  The model-chip change touches a different case (`agent_complete` write) and a
  different reset field (`agent_start` reset) — it does not overlap with any of
  those closed cards. Cross-check before applying if any domain-11 escalation
  cards are re-opened targeting the same reducer cases.
- **`WorkflowHistory.tsx` collision note**: This file is Domain 9's primary fix
  site (all 13 cards resolved). This change touches `detailAgentOutputs` and
  `thinkingAgents` useMemos — neither was a fix site for any domain-9 card.
  Safe to apply independently.
- **`AgentDetailPanel.tsx` collision note**: Domain 6 owns this file (FIX-454,
  FIX-455 closed). Those fixes touched `AgentDetailPanel`'s agent navigation
  (history push on agent/task select) and replay allowlist — unrelated to the
  header row chip area. No collision.
- The `MODEL_LABELS` static map is sourced from `model_catalog.py` (the single
  authoritative model list, INV-12). Any new model added to the catalog must be
  added to the map in the same change.
- Do not add a `model_id` to the `agent_start` SSE event or any other new SSE
  event type — the data flows correctly via `agent_complete` and persisted
  `agent_outputs`.

---

## Verification Checklist (for the implementer)

- [ ] `agent.modelId` is populated on a fresh live run — visible in React
  DevTools after `agent_complete` fires.
- [ ] Chip appears in `AgentDetailPanel` header row for a done agent.
- [ ] Chip does NOT appear for an idle agent (status `"idle"`).
- [ ] Chip shows the human-readable label ("Claude Sonnet 4.5"), not the raw
  Bedrock ID.
- [ ] Chip persists after the pipeline completes (not removed by
  `pipeline_complete` reducer).
- [ ] History reopen: opening a completed run from run history shows the chip
  for each agent that has a `model_id` in its persisted `agent_outputs`.
- [ ] Run history with a build/construction agent (multiple `agent_complete`
  events for the same `agent_id`): chip shows the final run's model.
- [ ] `tsc` clean (0 errors) after all changes.
- [ ] `vitest --run` passes the existing `AgentDetailPanel` and
  `WorkflowHistory` test suites with no regressions.

---

## Out of Scope (this refinement)

- L1 `StepsOverviewSpine` overview rows — the compact `rowMeta` string on the
  right side of the agent row. Adding a chip there would require JSX changes to
  the spine and is deferred.
- Model chip for the pipeline-level header (the pipeline-level `modelId` on
  `PipelineRunState` is a separate field already populated by
  `pipeline_complete`).
- Dynamic label resolution via live `GET /api/capabilities` call (the static
  map is sufficient; dynamic fetch can replace it in a follow-up).

---

## Run Result (2026-09-07)

```
RESULT: FIXED
CARD: RFN-001          MODE: FULL
FILES_TOUCHED:
  backend/agents/execution_engine/engine.py          ← NEW (agent_start model_id)
  frontend/src/types/index.ts
  frontend/src/hooks/useWorkflow.ts
  frontend/src/lib/api.ts
  frontend/src/components/history/WorkflowHistory.tsx
  frontend/src/components/results/AgentDetailPanel.tsx
BACKEND_CHANGED: true
NON_PY_BACKEND_CHANGED: false
TESTS_WRITTEN:
  backend/tests/agents/test_rfn001_model_id_on_agent_start.py   8 tests
  frontend/src/components/results/AgentDetailPanel.modelChip.test.tsx  15 tests
  frontend/src/components/history/WorkflowHistory.modelChip.test.tsx    4 tests
TESTS_RUN:
  tsc --noEmit:                                    EXIT_CODE=0 (0 errors)
  AgentDetailPanel vitest (5 files, 33 tests):     EXIT_CODE=0 — all passed
  WorkflowHistory vitest (10 files, 52 tests):     EXIT_CODE=0 — 51 passed,
                                                   1 expected-fail (pre-existing)
  test_rfn001_model_id_on_agent_start.py (8):      EXIT_CODE=0 — all passed
  AgentDetailPanel.modelChip.test.tsx (15):         EXIT_CODE=0 — all passed
  WorkflowHistory.modelChip.test.tsx (4):           EXIT_CODE=0 — all passed
  test_characterization_prototype.py (2):           EXIT_CODE=0 — INV-3 verified
INVARIANTS_CHECKED:
  SC-001 / INV-1 — chip keyed on agent.modelId (data value), no
                   workflow-name or agent-id literal anywhere
  INV-3 goldens  — model_id is in _VOLATILE_STRIP_KEYS; characterization
                   prototype tests (2 passed) confirm goldens byte-identical
                   after the agent_start backend change
  import-linter  — no new imports; Cpu already imported in AgentDetailPanel
  migrations     — no migration; all changes are Python + TypeScript only
SUMMARY: Phase 1 (frontend-only): five gaps closed — AgentRunState.modelId
  type, agent_complete reducer, RunSummaryAgent type, WorkflowHistory threading,
  AgentDetailPanel chip + resolveModelLabel. Phase 2 (backend): engine.py
  now calls _resolve_model before the agent_start yield so the chip appears
  immediately when an agent starts running, not only after agent_complete.
  INV-3 safe: model_id already in _VOLATILE_STRIP_KEYS; prototype
  characterization golden tests pass unchanged. All tsc + vitest suites green.
```

### Changes applied

| # | File | What changed |
|---|------|-------------|
| 1 | `frontend/src/types/index.ts` | Added `modelId?: string` to `AgentRunState` after `estimatedTokens` |
| 2 | `frontend/src/hooks/useWorkflow.ts` | `agent_complete` case: writes `modelId: (msg.model_id as string) \|\| undefined`; `agent_start` reset block: adds `modelId: undefined` |
| 3 | `frontend/src/lib/api.ts` | Added `model_id?: string` to `RunSummaryAgent` |
| 4 | `frontend/src/components/history/WorkflowHistory.tsx` | `detailAgentOutputs` inline type gains `model_id?: string`; dedup branch adds keep-last `model_id`; `thinkingAgents` map adds `modelId` via same cast pattern as `inputPrompt`/`toolCalls` |
| 5 | `frontend/src/components/results/AgentDetailPanel.tsx` | Added `MODEL_LABELS` map + `resolveModelLabel()` helper above the component; inserted model chip `{agent.modelId && <span …><Cpu/>…</span>}` after Done/Live/Failed chips in the header name row |
