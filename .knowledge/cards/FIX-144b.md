---
id: FIX-144b
type: fix
date: 2026-07-30
status: done
area: [agents, artifacts]
summary: >-
  ext Received panel shows "artifact" instead of source labels — formatContextSource
  ignores label field and doesn't handle run_input/context_block types
source: .planning/FIX-REGISTER.md#fix-144
collision_of: FIX-144
ticket: KAN-129
status_detail: "Phase 22 (KAN-102 context_sources)"
---

# FIX-144b

> **Reused id.** The register uses `FIX-144` for more than one unrelated
> fix. This card is one of them; the suffix exists only here, so that one card
> means one fix. The register itself is unchanged — see `source:`.

**Phase / trigger:** "artifact". Backend emits "run_input" and "context_block" with a label` field (added by KAN-102) but FE type and function never accounted for them. Fix: extend ContextSource type, update formatContextSource to read label, change backend label from "User brief" to "prompt.md".

<!-- verbatim from the register -->

### FIX-144 — KAN-129: Context Received panel shows correct labels instead of "artifact"

**Date:** 2026-07-30
**Triggered by:** `/velocity-ai-fix KAN 129`

#### Root Cause

`formatContextSource` in `AgentDetailPanel.tsx` only handled `type === "summary"` (prior-agent outputs). Every other type fell through to `src.artifact_type || "artifact"`. KAN-102 added two new source types to the backend — `"run_input"` (user brief) and `"context_block"` (template/design system) — both with a `label` field (e.g. `"User brief"`, `"Template: ibm-carbon"`). The frontend type `ContextSource` in `types/index.ts` was never updated to include these types or the `label` field, and `formatContextSource` never read `label` at all. Result: every first-agent context source across all workflows displayed as `"artifact"`.

The backend also emitted `"label": "User brief"` for the user brief source. Since the product requirement was to show `"prompt.md"`, the backend label was changed to `"prompt.md"`. This is INV-3 safe: `context_sources` is in `_VOLATILE_STRIP_KEYS` in `_normalize.py`, so goldens are byte-identical.

#### Phase Context

- **Phase(s) involved:** Phase 22 (KAN-102 — introduced run_input/context_block source types), Phase 31/39 (AgentDetailPanel formatContextSource)
- **Deleted code verified (not resurrected):** No deleted code touched.
- **Locked decisions respected:** INV-12 — `formatContextSource` is the single derivation function; one fix, all consumers benefit. SC-001 — dispatch on generic `type` field, never a workflow/agent-name literal.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/types/index.ts` | Extended `ContextSource.type` union to include `"run_input"` and `"context_block"`; added `label?: string` and `size_chars?: number` fields | Type was stale; missing fields caused silent runtime mismatches |
| `frontend/src/components/results/AgentDetailPanel.tsx` | Updated `formatContextSource` to read `src.label` for `"run_input"` (fallback `"prompt.md"`) and `"context_block"` (fallback `"context"`); updated `rawSize` derivation to include `size_chars` for new types | Makes all 4 source types render their correct human-readable label and size |
| `backend/agents/execution_engine/engine.py` | Changed `"label": "User brief"` → `"label": "prompt.md"` on the `run_input` source in `_build_context_sources` | Product requirement: show `"prompt.md"` as the context name for the user brief; INV-3 safe since `context_sources` is in `_VOLATILE_STRIP_KEYS` |

#### Invariants Verified

- **INV-1** (no pipeline_type branches): Not affected — `formatContextSource` dispatches on `src.type` only (generic data field, never a pipeline/workflow name)
- **INV-3** (golden parity): Not affected — `context_sources` is in `_VOLATILE_STRIP_KEYS` in `characterization/_normalize.py`; the backend label change is golden-neutral
- **INV-12** (no duplication): `formatContextSource` is the single source; no new render function added
- **SC-001** (zero engine edits for new workflows): The engine edit (`_build_context_sources`) changes only a display label string — no routing, no capability, no strategy logic changed

#### Verification

- `tsc --noEmit` diagnostics: No errors on either changed FE file
- Trace: backend emits `{type: "run_input", label: "prompt.md", size_chars: N}` → `useWorkflow` stores as `contextSources` → `ContextReceivedPanel` calls `formatContextSource` → `src.type === "run_input"` → `src.label || "prompt.md"` → shows `"prompt.md"`
- PPT/Prototype: `{type: "context_block", label: "Template: ibm-carbon", ...}` → `src.label || "context"` → shows `"Template: ibm-carbon"`
- Prior-agent handoffs (`"summary"` type): unaffected — existing path unchanged

#### Notes

- Backend restart required since `engine.py` was changed.
- The `size_chars` field is now displayed in the meta line (e.g. "48.3k") for `run_input` and `context_block` sources, matching the pattern for `"summary"` sources.

---



**Date:** 2026-07-29
**Triggered by:** `/velocity-ai-fix still showing the same issue for ppt and prototype`

#### Root Cause

FIX-141 introduced `laneActiveContent` to select the right content for `deriveDeliverableFilename`, but it keyed on `workflowType` (DashboardLayout's local state) instead of `effectiveReviseType`.

`workflowType` is a local `useState` inside DashboardLayout:
- It defaults to `"user_stories"` unless a wizard explicitly calls `setWorkflowType()`
- It's set to `"ppt"` / `"prototype"` when the respective wizard launches a run
- **It stays stale at `"user_stories"` when a completed run is opened from history**

`effectiveReviseType` is computed correctly for ALL cases:
```ts
const viewedRunType = contentSourceRunType ?? (!isPipelineRunning && contentSourceRunId != null ? recentRuns.find(...)?.type : undefined);
const effectiveReviseType = viewedRunType ?? workflowType;
```

For a history-reopened `"od_ppt"` run: `contentSourceRunType = "od_ppt"` → `effectiveReviseType = "od_ppt"`. But `workflowType` stays `"user_stories"`.

So `laneActiveContent` was checking `workflowType === "ppt"` → `false` → fell through to `userStoryContent = ""` → `deriveDeliverableFilename("user_stories", "", fallback)` → returned the static fallback `"presentation.pptx"`.

`PreviewPanel` was already correct because it uses `workflowType={effectiveReviseType}` (line ~2049). Only `laneActiveContent` was wrong.

#### Phase Context

- **Phase(s) involved:** Phase 31 (CHATUI-01 RunChatLane), Phase 39 (RUNUI-06 DeliverableCard), follow-up to FIX-141
- **Deleted code verified (not resurrected):** No deleted code touched.
- **Locked decisions respected:** SC-001 — no workflow-name literal; dispatch keys on the existing `effectiveReviseType` variable.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/layout/DashboardLayout.tsx` | Replaced `workflowType` with `effectiveReviseType` in the `laneActiveContent` dispatch AND in the `deriveDeliverableFilename` first argument | `effectiveReviseType` is the authoritative type for the viewed run (incorporates `contentSourceRunType` for history-reopened runs); `workflowType` is stale for reopened runs |

#### Invariants Verified

- **INV-1** (no pipeline_type branches): Not affected — FE-only
- **INV-3** (golden parity): Not affected — FE-only, no backend/golden impact
- **INV-12** (no duplication): Uses the existing `effectiveReviseType` variable already computed above
- **SC-001** (zero engine edits): Not affected

#### Verification

- `tsc --noEmit`: No errors on `DashboardLayout.tsx`
- Trace for PPT: `contentSourceRunType = "od_ppt"` → `effectiveReviseType = "od_ppt"` → `laneActiveContent = pptContent` (the HTML deck) → `deriveDeliverableFilename("od_ppt", "<html><title>GitHub OAuth Authentication</title>...", fallback)` → `"github-oauth-authentication.html"` ✅
- Trace for Prototype: `contentSourceRunType = "od_prototype"` → `effectiveReviseType = "od_prototype"` → `laneActiveContent = prototypeContent` → `deriveDeliverableFilename("od_prototype", "<html><title>To Do App</title>...", fallback)` → `"to-do-app.html"` ✅
- Trace for live PPT launch: `workflowType = "ppt"`, `contentSourceRunType = null` → `effectiveReviseType = "ppt"` → same as before ✅

#### Notes

This is the definitive fix for the chat panel filename issue. The root cause was a two-level bug:
1. FIX-141 wired the infrastructure but used the wrong type variable (`workflowType` vs `effectiveReviseType`)
2. FIX-142 fixed the extension (`.pptx` → `.html`) for the `"ppt"` normalised alias

With FIX-143, both live runs and history-reopened runs will show the correct content-derived filename in the chat panel for all workflow types.

---
