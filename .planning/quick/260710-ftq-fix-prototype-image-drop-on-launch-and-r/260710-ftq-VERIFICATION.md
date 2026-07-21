---
phase: quick-260710-ftq
verified: 2026-07-10T11:40:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
---

# Quick 260710-ftq: Fix Prototype Image Drop on Launch + Home Recents Chip — Verification Report

**Task Goal:** Fix two FE wiring defects found via live UI testing — (1) attached images dropped on the prototype/ppt launch because the FE state-setters in `dashboard/page.tsx` omitted `images`; (2) Home recents chips were dead links because `DashboardLayout.tsx:1525` omitted `setMainView("execution")`.
**Verified:** 2026-07-10T11:40:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Prototype (od_prototype) launch with an attached image carries `images` on the outbound frame | ✓ VERIFIED | `page.tsx:1011` — length-guarded `images` spread inside `setPendingOdProtoParams` (line 996-1012), immediately after the `agentIds` spread (1010). Downstream extraParams guard at `DashboardLayout.tsx:757` consumes `pendingOdProtoParams.images` (unmodified). |
| 2 | PPT (od_ppt) launch with an attached image carries `images` on the outbound frame | ✓ VERIFIED | `page.tsx:1084` — same length-guarded `images` spread inside `setPendingOdPptParams` (line 1069-1085), after the `agentIds` spread (1083). Downstream guard at `DashboardLayout.tsx:805` consumes `pendingOdPptParams.images` (unmodified). |
| 3 | Image-LESS launch is byte-identical (no `images` key — INV-3 dormancy) | ✓ VERIFIED | Both spreads are length-guarded: `...(pending.images && pending.images.length > 0 ? { images: pending.images } : {})`. When empty/absent the spread contributes `{}` → no `images` key. Not unconditional. |
| 4 | Clicking a Home 'Recent runs' chip loads the run AND switches shell to execution view | ✓ VERIFIED | `DashboardLayout.tsx:1525` — `onClick={() => { onSelectWorkflowRun?.(run); setMainView("execution"); }}`. `setMainView` already in scope (used at 736, 785, 941, etc.). grep count = 1. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `frontend/src/app/dashboard/page.tsx` | images spread in BOTH launch setters | ✓ VERIFIED | grep count of `pending.images && pending.images.length > 0 ? { images: pending.images }` = **2** (lines 1011 proto, 1084 ppt). |
| `frontend/src/components/layout/DashboardLayout.tsx` | recents chip calls `setMainView("execution")` | ✓ VERIFIED | grep count of `onSelectWorkflowRun?.(run); setMainView("execution")` = **1** (line 1525). |
| `frontend/src/app/dashboard/launchImageAndRecents.source.test.ts` | source-lock proving both wirings | ✓ VERIFIED | File exists (2048 bytes). `npx vitest run` → 3/3 tests passing. Asserts images spread appears exactly twice + recents chip calls setMainView. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| page.tsx `setPendingOdProtoParams`/`setPendingOdPptParams` | `pendingOd*Params.images` | length-guarded images spread after agentIds | ✓ WIRED | Both setters populate `images` (1011, 1084). |
| DashboardLayout extraParams guard (757/805) | WS run_pipeline `images` field | consumes `pendingOd*Params.images` — now populated | ✓ WIRED (UNCHANGED) | Guard lines 757/805 present and NOT modified by these commits (commit `ba159678` changed exactly 1 line — the recents chip). |
| DashboardLayout recents chip onClick (1525) | execution view | `onSelectWorkflowRun?.(run); setMainView("execution")` | ✓ WIRED | Exact pattern present at line 1525. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| No new type errors from the 2 files | `npx tsc --noEmit \| grep -v mockApi.ts \| grep -c "error TS"` | `0` | ✓ PASS |
| No tsc error references touched files | `npx tsc --noEmit \| grep -E "page.tsx\|DashboardLayout.tsx"` | NONE | ✓ PASS |
| Source-lock test | `npx vitest run launchImageAndRecents.source.test.ts` | 3/3 passing | ✓ PASS |

### Scope / Anti-Pattern Scan

| Check | Result | Status |
| --- | --- | --- |
| Files changed by commits `a4a00682` + `ba159678` | exactly `page.tsx`, `DashboardLayout.tsx`, new test | ✓ In-scope |
| Backend / manifest / AGENT.md / golden touched | none | ✓ Clean |
| Commit trailer on the 2 commits | NO `Co-Authored-By` / `Generated with` | ✓ Clean (per plan) |
| extraParams image-guard (757/805) modified | not modified — still consumes `pendingOd*Params.images` | ✓ Preserved |

### Gaps Summary

No gaps. Both defects are fixed in the actual codebase, not just claimed:

- DEFECT 1: length-guarded `images` spread present in BOTH `setPendingOdProtoParams` (page.tsx:1011) and `setPendingOdPptParams` (page.tsx:1084) — grep == 2, guarded (not unconditional), so image-less launches remain byte-identical (INV-3 dormancy preserved).
- DEFECT 2: recents chip `onClick` at DashboardLayout.tsx:1525 now calls `setMainView("execution")` alongside `onSelectWorkflowRun?.(run)` — grep == 1.

Scope is confined to 3 files (2 source + 1 new test); the pre-existing extraParams image-guard was left untouched; no commit trailers; `tsc --noEmit` shows 0 new errors and none attributable to the touched files; the source-lock test is green (3/3).

The live Bedrock proof (outbound `run_pipeline` frame carrying `images:[1]` + recents chip mounting the run screen) is performed separately by the orchestrator and was not required for this code-level verification.

---

_Verified: 2026-07-10T11:40:00Z_
_Verifier: Claude (gsd-verifier)_
