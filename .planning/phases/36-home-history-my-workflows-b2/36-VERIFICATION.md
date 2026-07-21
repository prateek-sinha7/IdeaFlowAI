---
phase: 36-home-history-my-workflows-b2
verified: 2026-07-09T04:06:55Z
status: passed
score: 4/4 success criteria verified (all supporting truths VERIFIED)
overrides_applied: 0
re_verification:
  previous_status: null   # initial verification (no prior 36-VERIFICATION.md)
warnings:
  - item: "5 pre-existing dead tests in HomeLaunchGrid.test.tsx assert the removed 'Your workflows' saved-row section"
    severity: warning
    disposition: "NOT a Phase-36 regression — red at base 92af09ec (WorkflowCatalog.tsx already had 0 saved-workflow rendering). Functionality moved to SavedWorkflowsPage, whose own test (SavedWorkflowsPage.test.tsx) PASSES. Documented in deferred-items.md. Recommend retargeting/removing now that SavedWorkflowsPage.test.tsx exists (project rule: never delete a failing test to go green)."
deferred:
  - item: "L-01 — dead `Calendar` import + unused `formatFullDate` in SavedWorkflowsPage.tsx"
    reason: "Cosmetic Low, unfixed; no behavioral impact"
  - item: "Mocked-Playwright e2e (History/Home flows)"
    reason: "Offline webServer timeout — live-deferred to milestone-end; baseline captured"
  - item: "Live KAN-96 SSE (running→live view transition over real transport)"
    reason: "Live-transport verification routed to Phase 34"
---

# Phase 36: Home + History + My Workflows [B2] — Verification Report

**Phase Goal:** The three restructured list surfaces + the new Run detail page.
**Verified:** 2026-07-09T04:06:55Z
**Status:** passed
**Re-verification:** No — initial verification.
**Branch/HEAD:** `feat/ui-2` @ `6eefa3f1` (working tree clean throughout).

Every gate below was independently RE-RUN by the verifier. SUMMARY claims were not trusted.

## Goal Achievement

### Observable Truths (merged: ROADMAP SC + 5 plan frontmatters)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | **SC-1 Fused Home** — prompt launcher + deliverable grid + recents in one view | VERIFIED | `DashboardLayout.tsx:1446` fused-home block: prompt launcher (`home-launch-prompt` label:1460) + `HomeLaunchGrid` mount (import:9) + recents strip from threaded `recentRuns` prop (68/283). No new fetch. |
| 2 | **SC-001 rename** — `WorkflowCatalog`→`HomeLaunchGrid` complete incl. vi.mock paths | VERIFIED | `grep -rn WorkflowCatalog frontend/src` = **0** (incl. mock paths + stub keys). Component + `HomeLaunchGridProps` renamed. |
| 3 | MainView page-keys stay generic — no route/page-key renamed to a workflow name (SC-001/INV-1) | VERIFIED | `type MainView` page-keys generic (`home`/`input`/`history`/`saved`); no workflow-name branch. |
| 4 | **SC-2 History** — Today/Earlier/Older grouping + token/duration sort | VERIFIED | `bucketAndSortFamilies` (WorkflowHistory:746) over `RevisionFamilyView` helpers (`DateBucketLabel`/`BUCKET_ORDER`:144-154; Today=same day, Earlier=≤7d, Older=beyond). Sort keys `tokens`/`duration`/`recent` (819-820). |
| 5 | Real delete removes a run; revision families intact | VERIFIED | `handleDeleteConfirm`→`deleteWorkflow` (WorkflowHistory:249) + optimistic filter (250). `groupRunsByFamily` (RevisionFamilyView:101) intact. |
| 6 | **KAN-96** — running click→live view, terminal click→RunDetailPage | VERIFIED | `handleSelectRun`:158 `if (activeRunId && run.id===activeRunId && onViewRunningPipeline) → onViewRunningPipeline()`; else `getWorkflow`→`setSelectedRun`→RunDetailPage. |
| 7 | **KAN-92** — real async `run.title` rendered, never `Revision:` placeholder | VERIFIED | `selectedRun.title` rendered (WorkflowHistory:545); search on `r.title` (265). No `Revision:` literal title. |
| 8 | **SC-3 My Workflows** — "Catalogue" gone, heading reads "My Workflows" | VERIFIED | `SavedWorkflowsPage.tsx:230` `<h1>My Workflows`. `SavedWorkflowsPage.test.tsx:98-99` asserts `queryByText(/Catalogue/i)===null`. Residual "Catalogue" hits are agent-description domain content (AgentLibraryData/IdeaInputPage taglines) + negative test assertions — not the page label. |
| 9 | Kebab actions Rename/Duplicate/Delete real + a11y | VERIFIED | Wired to `(rename\|create\|delete)UserWorkflow`; SavedWorkflowsPage suite 5/5 pass. |
| 10 | **SC-4 RunDetailPage** off `GET /api/runs/{id}/summary`, generic-keyed | VERIFIED | `RunDetailPage.tsx` fetches `getRunSummary` (102), keyed on status/agents/tokens (177-199), no workflow-name branch. `getRunSummary` client + `RunSummary` type (api.ts:384/408). |
| 11 | RunDetailPage REUSES shared surfaces — no dual impl (D-15/INV-12) | VERIFIED | Imports `VersionTimeline`, `DegradedRunAffordance`, `parseFailedAgentIds`/`buildAgentNameById`, `formatDuration`/`formatTokenCount` (RunDetailPage:12-17). |
| 12 | In-panel hand-rolled detail retired — RunDetailPage single source (INV-12) | VERIFIED | WorkflowHistory does NOT import DegradedRunAffordance/VersionTimeline directly; the 3 "per-agent/KPI" hits are comments (27/402/419) explaining RunDetailPage owns them. Left column = RunDetailPage; right column = deliverable only. |

**Score: 4/4 success criteria verified** (12/12 supporting truths VERIFIED).

### Post-Review FIX Verification

| Fix | Claim | Status | Evidence |
|-----|-------|--------|----------|
| **H-01** | version-chip click re-syncs BOTH detail columns | VERIFIED | `RunDetailPage.onSelectVersion={handleSelectVersion}` (WorkflowHistory:429). `handleSelectVersion`:184-190 → `getWorkflow(memberId)`→`setSelectedRun(full)`+`setSelectedOutput` (right column) AND re-keys RunDetailPage runId → left summary refetches. |
| **H-02** | no empty-quote previews; RunDetailPage supplies real `summary.input` | VERIFIED | `VersionTimeline`:570 renders `— '…'` suffix ONLY `{instructionPreview ? … : null}`; whole `↳ revises` line gated on `activeMember.parent_run_id` (567). RunDetailPage passes `activeInput={summary.input ?? ""}` (265). |
| **M-02** | single-source `formatDuration` (INV-12) | VERIFIED | Only definition: `runStats.ts:12`. `RevisionFamilyView.tsx:24 import { formatDuration } from "@/lib/runStats"`. No dual impl. |
| **M-01** | ISS-024 raw-id fallback test restored | VERIFIED | `RunDetailPage.test.tsx:159` "failed run whose error names an agent id absent from agents[] falls back to the RAW id (never blank)". Plus PreviewPanel.degraded.test.tsx:127/218. |

### Invariant Verification

| Invariant | Status | Evidence |
|-----------|--------|----------|
| **SC-001** list/detail keyed on generic run data | VERIFIED | RunDetailPage + WorkflowHistory branch on status/agents/tokens; no workflow-name branch. Page-keys generic. |
| **INV-3** run-summary endpoint additive READ-only; 5 goldens byte-identical | VERIFIED | Endpoint reads only existing `WorkflowRun` columns + reused family walk; zero new tables/migrations. 5 goldens **10/10 pass** SNAPSHOT_UPDATE unset; **git tree CLEAN** after run (no golden bytes rewritten). |
| **Owner-scoped endpoint** — cross-owner→404, no secret echo | VERIFIED | `_owner_gate_or_404` on `WorkflowRun.user_id` (runs.py:1100/1206). `RunSummaryResponse.input = run.input` (owner's own, owner-gated:1148). Per-agent projection limited to `_SUMMARY_SAFE_AGENT_KEYS` (995-1007: id/name/role/icon/duration/error/token counts) — NO output/input_prompt/thinking/tool_calls. Tests: `test_cross_owner_summary_is_404_never_403`, `test_missing_run_summary_is_404`, `test_raw_agent_content_is_never_echoed`, `test_foreign_parent_terminates_walk_no_leak` — all PASS. |
| **INV-12** in-panel detail retired, no dual impl | VERIFIED | See truth #12 + M-02. |
| **Token gate** retired-palette=0 per touched FE file | VERIFIED | `#1B2A4A/#2563eb/#f5f5f0/Fraunces/JetBrains/Inter(font)` = 0 across all 8 touched files. |
| **KAN-96 / KAN-92** | VERIFIED | Truths #6/#7; history suite (genericReopen/family/revise) 36/36 pass. |
| **LOCK-B** no transport touch | VERIFIED | import-linter transport contracts KEPT; backend change is additive read endpoint only. |
| **import-linter 4/0** | VERIFIED | `4 kept, 0 broken` (206 files, 495 deps). |

### Re-Run Gate Results

| Gate | Command | Result |
|------|---------|--------|
| Backend owner-gate/secret/family | `pytest tests/unit/test_runs_api_summary.py test_runs_api_family.py -q` | **16 passed** (0.41s) |
| 5 characterization goldens (INV-3) | `pytest test_characterization_{prototype,prototype_revision,od_ppt,od_prototype,app_builder}.py` (SNAPSHOT_UPDATE unset) | **10 passed** (35.1s); **git clean after** |
| Frontend history suite | `vitest run src/components/history/` | **36 passed** (7 files) |
| TypeScript identity | `tsc --noEmit` | **exit 0** (clean) |
| import-linter | `lint-imports` (from backend/) | **4 kept / 0 broken** |
| Retired-palette grep | per touched FE file | **0 hits** all files |
| Savedworkflows suite | `vitest run src/components/savedworkflows/` | SavedWorkflowsPage.test.tsx **5/5 pass** |

### Behavioral Spot-Checks

| Behavior | Check | Status |
|----------|-------|--------|
| Summary endpoint owner-gate | pytest 404 cases | PASS |
| Summary secret non-echo | pytest raw-agent-content | PASS |
| Goldens byte-identical | git status post-run | PASS (clean) |
| tsc type identity | tsc --noEmit | PASS |

### Anti-Patterns / Warnings

| Item | Severity | Impact |
|------|----------|--------|
| `HomeLaunchGrid.test.tsx` — 5 failing "Your workflows" tests | WARNING (non-blocking) | Assert the saved-row section that was moved to SavedWorkflowsPage. **Red at base `92af09ec`** (WorkflowCatalog.tsx already had 0 saved-workflow rendering) → NOT a Phase-36 regression; inherited via the `git mv` rename. Functionality is present + tested in SavedWorkflowsPage (5/5 pass). Documented in `deferred-items.md`. Recommend retargeting/removing these stale tests in a follow-up now that `SavedWorkflowsPage.test.tsx` exists. |
| `SavedWorkflowsPage.tsx` dead `Calendar` import + `formatFullDate` (L-01) | INFO / deferred | Cosmetic, no behavior impact. |

### Human / Live Verification (deferred to milestone-end, per established technical-UAT stance)

No `<human-check>` blocks were declared in any Phase-36 plan. Consistent with prior phases in this milestone (all-infra, technical UAT), the following are deferred, NOT blockers:

1. **Live KAN-96 SSE** — running→live-view transition over real transport → Phase 34.
2. **Mocked-Playwright e2e** — offline `webServer` timeout; live-deferred, baseline captured.
3. **Visual reskin fidelity** — token gate is automated (retired-palette=0); pixel review folds into milestone-end UAT.

### Gaps Summary

**No genuine gaps.** All 4 ROADMAP success criteria and all supporting truths are VERIFIED in code, and every gate was independently re-run green: backend 16/16, goldens 10/10 (byte-identical, git clean), history vitest 36/36, tsc clean, import-linter 4/0, retired-palette 0, cross-owner→404 + secret-non-echo proven. The four post-review fixes (H-01, H-02, M-01, M-02) each deliver as claimed in the actual code. The sole WARNING (5 stale HomeLaunchGrid tests) is a documented pre-existing failure — red at base, functionality relocated + tested elsewhere — and does not block the phase goal.

---

_Verified: 2026-07-09T04:06:55Z_
_Verifier: Claude (gsd-verifier) — goal-backward, gates independently re-run_
