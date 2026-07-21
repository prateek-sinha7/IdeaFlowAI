---
phase: 36-home-history-my-workflows-b2
reviewed: 2026-07-09T03:41:17Z
depth: deep
diff_base: be505eb5..HEAD
files_reviewed: 12
files_reviewed_list:
  - backend/app/api/runs.py
  - backend/tests/unit/test_runs_api_summary.py
  - frontend/src/components/catalog/HomeLaunchGrid.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx
  - frontend/src/components/savedworkflows/SavedWorkflowsPage.test.tsx
  - frontend/src/lib/api.ts
  - frontend/src/lib/runStats.ts
  - frontend/src/lib/parseFailedAgents.ts
  - frontend/src/components/history/RunDetailPage.tsx
  - frontend/src/components/history/RunDetailPage.test.tsx
  - frontend/src/components/history/WorkflowHistory.tsx
  - frontend/src/components/history/RevisionFamilyView.tsx
  - frontend/src/components/history/WorkflowHistory.test.tsx
findings:
  critical: 0
  high: 2
  medium: 2
  low: 1
  total: 5
status: issues_found
---

# Phase 36: Code Review Report

**Reviewed:** 2026-07-09T03:41:17Z
**Depth:** deep
**Files Reviewed:** 12 source files (+ 2 supporting test/lib files traced across the boundary)
**Status:** issues_found

## Summary

The security-critical surface — the new owner-scoped `GET /api/runs/{id}/summary` endpoint — is **correct and thoroughly hardened**. The IDOR gate (`_owner_gate_or_404` on `WorkflowRun.user_id`, never the nullable `owner_id`), the reused `_owned_family_members` BFS (owner-filtered at root + every frontier, cycle-guarded), the try/except JSON parse with `[]`/`{}` fallback, and the `_SUMMARY_SAFE_AGENT_KEYS` projection (raw `output`/`input_prompt`/`thinking_text`/`tool_calls` never echoed) are all present and backed by direct unit tests (cross-owner→404, missing→404, malformed-JSON→200, foreign-parent walk termination, secret-non-echo). **No security defect found on the backend.**

The defects are all on the frontend detail-promotion (36-05), where retiring the in-panel detail in favor of `RunDetailPage` dropped two behaviors that the base commit had wired, and relocated coverage lost the ISS-024 case:

- **H-01** — version-switch desync: switching versions in the promoted `RunDetailPage` timeline updates only the left summary column, never the right deliverable/Files/Thinking/Audit column (`selectedRun` is no longer re-synced as it was at base via `handleSelectVersion → setSelectedRun`).
- **H-02** — the revision-instruction preview now renders empty quotes (`↳ revises vN — ''`) on every revision member, because `RunDetailPage` passes `activeInput=""` to `VersionTimeline`.

INV-12 (no dual implementation): the in-panel detail JSX and the retired formatters were genuinely removed — but `RevisionFamilyView.formatDuration` is a byte-identical duplicate of the new single-source `runStats.formatDuration` (M-02).

## High

### H-01: Version-switch desync — timeline updates the summary but not the deliverable

**File:** `frontend/src/components/history/WorkflowHistory.tsx:406-411` (mount) / `frontend/src/components/history/RunDetailPage.tsx:75-113,255-261,338-367`
**Issue:** In the history detail, the left column is `RunDetailPage` (KPI/agents/failure banner + `VersionTimeline`) and the right column (deliverable preview + Files/Thinking/Audit tabs) is keyed on `WorkflowHistory`'s `selectedRun`. When the user clicks a version chip, `RunDetailPage` calls its **internal** `setActiveVersionId`, which refetches only its own summary. There is **no callback threaded back to `WorkflowHistory`** to update `selectedRun` (`RunDetailPageProps` exposes only `runId`, `onBack`, `activeRunId`, `onViewRunningPipeline`). Result: after switching to v2, the left column shows v2's KPI/agents while the right column still shows v1's deliverable/output — two different versions on screen at once.

At base `be505eb5`, `VersionTimeline.onSelectVersion` was wired to `handleSelectVersion`, which did `getWorkflow(memberId) → setSelectedRun(full)` so **both columns switched together**. Promoting the timeline into `RunDetailPage` dropped that sync. The comment at `WorkflowHistory.tsx:518-520` ("Version switching lives in the RunDetailPage timeline on the left (single source)") documents the intent but the deliverable half of the switch is now non-functional.

**Fix:** Add an optional `onVersionChange?: (memberId: string) => void` prop to `RunDetailPage`, fire it from `setActiveVersionId`'s call sites (chip + timeline list), and in `WorkflowHistory` pass a handler that re-fetches the member and updates `selectedRun` (reinstating the base `handleSelectVersion` body):
```tsx
// RunDetailPage: replace bare setActiveVersionId in onSelectVersion / list onClick
const selectVersion = (id: string) => { setActiveVersionId(id); onVersionChange?.(id); };
// WorkflowHistory: <RunDetailPage ... onVersionChange={handleSelectVersion} />
```

### H-02: Revision-instruction preview always renders empty quotes

**File:** `frontend/src/components/history/RunDetailPage.tsx:256-261` (see `RevisionFamilyView.tsx:534,569-573`)
**Issue:** `RunDetailPage` hardcodes `activeInput=""` on `VersionTimeline`. For any revision member (`activeMember.parent_run_id` truthy), `VersionTimeline` renders the context line `↳ revises v{currentIdx} — '{instructionPreview}'` where `instructionPreview = extractRevisionInstructionPreview("")` → `""`. So every revision family shows a visibly broken `↳ revises vN — ''` with empty quotes. At base, `WorkflowHistory` passed `activeInput={selectedRun.input}`, so the actual revision instruction appeared. The regression is structural: `getRunSummary` deliberately omits `input` (secret-leak guard), so `RunDetailPage` has no instruction text to pass.
**Fix:** Either (a) stop rendering the instruction clause when `activeInput` is empty (guard the `<p>` on a non-empty `instructionPreview` in `VersionTimeline`), or (b) thread the instruction into `RunDetailPage` from the already-fetched `selectedRun.input` (the parent has it) via a new prop. Option (a) is the minimal correctness fix:
```tsx
{activeMember && activeMember.parent_run_id && instructionPreview && (
  <p ...>↳ revises v{currentIdx} — &lsquo;{instructionPreview}&rsquo;</p>
)}
```

## Medium

### M-01: ISS-024 raw-id fallback lost its only test (genuine coverage loss)

**File:** `frontend/src/components/history/RunDetailPage.test.tsx:81-97,136-147` and `frontend/src/components/history/WorkflowHistory.test.tsx:219-253`
**Issue:** The 36-05 rewrite removed the base test at `be505eb5:WorkflowHistory.test.tsx:239` — "reopening a FAILED run whose agentOutputs DON'T name a failed id falls back to the raw id (ISS-024, never blank)" (asserted `screen.getByText("ghost-agent")`). Neither replacement covers it: the new `FAILED`/`summaryFor` fixtures always include an agent whose `agent_id` matches the failed id and carries a `name`, so only the **name-resolved** path is exercised. The raw-id fallback path (`resolveAgentNames` → raw id when `nameById[id]` is missing, `parseFailedAgents.ts:56-62`) still exists in code but is now **untested** at every layer — and there is no direct unit test for `parseFailedAgentIds` / `buildAgentNameById` / `resolveAgentNames`. A future refactor that regresses the fallback to blank would ship green.
**Fix:** Add one `RunDetailPage.test.tsx` case with `error: "...agent(s) failed: prototype-build, ghost-agent"` and an `agents` list that omits `ghost-agent`, asserting `getByText("ghost-agent")` (raw id) appears alongside the resolved name. Optionally add a focused `parseFailedAgents.test.ts` unit for the marker parse + fallback.

### M-02: `RevisionFamilyView.formatDuration` duplicates the new single-source `runStats.formatDuration` (INV-12)

**File:** `frontend/src/components/history/RevisionFamilyView.tsx:57-61` vs `frontend/src/lib/runStats.ts:12-16`
**Issue:** This phase created `runStats.ts` as "the SINGLE source for the duration + token formatters (D-15 / no dual implementation)." `RevisionFamilyView.formatDuration` is a **byte-identical** re-implementation of `runStats.formatDuration`. The in-file comment (`RevisionFamilyView.tsx:24-27`) justifies the copy to avoid "a circular import back into WorkflowHistory" — but `runStats.ts` is a leaf lib with no such cycle, so the justification does not hold for it. This is exactly the dual-implementation the phase's own D-15 goal set out to eliminate.
**Fix:** `import { formatDuration } from "@/lib/runStats";` in `RevisionFamilyView.tsx` and delete the local copy (the widened `seconds?: number | null` signature is a superset, so no call-site change). `formatDate` is unique to this module and stays.

## Low

### L-01: Dead import + unused helper in SavedWorkflowsPage

**File:** `frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx:8,59-64`
**Issue:** `Calendar` (imported line 8) and `formatFullDate` (defined lines 59-64) are never referenced anywhere in the component. Dead code left over from the reskin.
**Fix:** Remove the `Calendar` import and the `formatFullDate` function.

---

## Notes (verified, not defects)

- **Backend IDOR / DoS / info-disclosure (focus area 1):** verified correct and test-backed. `get_run_summary` gates via `_owner_gate_or_404(... current_user.id)` on `WorkflowRun.user_id`; `_owned_family_members` filters `user_id == user_id` at the root resolve, every BFS frontier, with a `visited` cycle guard; both stored blobs parse under try/except with type-checked `[]`/`{}` fallback; `_SUMMARY_SAFE_AGENT_KEYS` whitelists identity+KPI only. `test_runs_api_summary.py` proves cross-owner→404 (≠403), missing→404, malformed+wrong-shape JSON→200 empty, foreign-parent walk termination with no leak, and raw-secret non-echo.
- **`_owner_gate_or_404` defined (line 1200) after its use in `get_run_summary` (line 1099):** not a bug — Python resolves the name at call time, and both live in the same module loaded before any request.
- **RunDetailPage cancellable mount-fetch (focus area 4):** correct. The `cancelled` flag guards every `set*` in `then/catch/finally`; the render-phase `runId !== prevRunId` reset re-seeds `activeVersionId` so the `[activeVersionId]` effect refetches; no stale set after unmount.
- **Generic-keyed rendering (SC-001):** `RunDetailPage` keys terminal-failure / KPI / agent rendering on `status`/`agents`/`token_usage`, never a workflow-name branch. `HomeLaunchGrid` and the fused-Home launcher route by generic `WorkflowType` / `CHAIN_OPTIONS`, not names.
- **token_usage key contract:** `RunDetailPage` reads `total_tokens` / `total_input_tokens` / `total_output_tokens`, which match the keys the engine/websocket/run_commands persist — verified.
- **Pre-existing dead HomeLaunchGrid "Your workflows (Phase 21)" test failures:** confirmed out of scope per the task's known-context (section moved to SavedWorkflowsPage in a prior phase; failing at base).

---

_Reviewed: 2026-07-09T03:41:17Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
