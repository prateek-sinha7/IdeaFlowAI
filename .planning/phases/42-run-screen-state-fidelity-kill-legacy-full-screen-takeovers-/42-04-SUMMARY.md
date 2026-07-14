---
phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-
plan: 04
subsystem: ui
tags: [react, vitest, dead-code, INV-12, run-screen]

# Dependency graph
requires:
  - phase: 42-02
    provides: "Removed the three legacy full-screen takeover branches from the DashboardLayout cascade, unshadowing the inline Steps surfaces."
provides:
  - "AgentProgressPanel deleted (controls already absorbed into RunChatLane; zero production mount)."
  - "TodoCard deleted (no `todo` block kind emitted — ISS-037; only importer was its own block test)."
  - "WaveTreePanel deleted (superseded by AgentDetailPanel's inline construction/wave tree, Phase 39; its keep-alive test retired)."
  - "Stale comments corrected to name AgentDetailPanel's inline construction/wave tree as the live wave renderer."
affects: [42-run-screen dead-code follow-up]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pre-delete grep guard (real import + JSX mount) gating each component deletion; a found importer aborts the delete pending reconciliation (T-42-04-01 mitigation)."

key-files:
  created: []
  modified:
    - frontend/src/components/chat/blocks/blocks.test.tsx
    - frontend/src/components/layout/DashboardLayout.tsx
    - frontend/src/components/preview/PreviewPanel.tsx
    - frontend/src/app/dashboard/page.tsx
    - frontend/src/types/index.ts
  deleted:
    - frontend/src/components/workflow/AgentProgressPanel.tsx
    - frontend/src/components/workflow/AgentProgressPanel.test.tsx
    - frontend/src/components/workflow/WaveTreePanel.tsx
    - frontend/src/components/layout/DashboardLayout.waveMount.test.tsx
    - frontend/src/components/chat/blocks/TodoCard.tsx

key-decisions:
  - "WaveTreePanel initially blocked by a keep-alive test (DashboardLayout.waveMount.test.tsx) that stubbed PreviewPanel to render the real component — a fiction; the orchestrator confirmed WaveTreePanel is production-dead (live wave tree is AgentDetailPanel's inline construction block, Phase 39) and directed retirement of the test. Removed."
  - "Now-stale comments implying a live WaveTreePanel mount were rewritten to name AgentDetailPanel's inline construction/wave tree; AgentDetailPanel.tsx's 'former/retired' history comments left intact (accurate)."

patterns-established:
  - "Guard-before-delete: verify zero real importers/mounts per component; a keep-alive test whose only subject is the deleted component is retired with it."

requirements-completed: [RUNUI-06]

# Metrics
duration: 30min
completed: 2026-07-15
---

# Phase 42 Plan 04: Delete dead code (Group E, INV-12) Summary

**Removed the three superseded run-screen components — AgentProgressPanel, WaveTreePanel, TodoCard — plus their tests, and corrected the stale comments so the live wave renderer (AgentDetailPanel's inline construction tree) is named correctly. Group E fully done; INV-12 one-implementation-per-behavior holds.**

## Performance

- **Duration:** ~30 min (two sessions — initial partial + blocker resolution)
- **Tasks:** 2 of 2 complete (Group E)
- **Files:** 5 deleted, 5 modified

## Accomplishments
- Deleted `components/workflow/AgentProgressPanel.tsx` + its test — controls already absorbed into RunChatLane (zero production import/mount).
- Deleted `components/chat/blocks/TodoCard.tsx` and retired its `describe("TodoCard")` case in `blocks.test.tsx` — no `todo` block kind is emitted (ISS-037).
- Deleted `components/workflow/WaveTreePanel.tsx` and retired its keep-alive test `DashboardLayout.waveMount.test.tsx` — the live wave/subagent tree is AgentDetailPanel's inline construction block (Phase 39; the separate panel was already retired, INV-12).
- Corrected 6 stale comments across 4 files to name AgentDetailPanel's inline construction/wave tree as the live renderer (kept the data-flow description; left AgentDetailPanel's accurate "former/retired" history).
- `WaveGroup` type in `types/index.ts` and its legitimate type-importers untouched.

## Task Commits

1. **Task 1a: Delete AgentProgressPanel + TodoCard** — `23e05167` (refactor)
2. **Task 1b: Delete WaveTreePanel + retire keep-alive test + fix stale comments** — `d0679f13` (refactor)

**Plan metadata:** `b73fd6a5` (docs: interim partial summary) + this final summary update.

## Files Created/Modified
- `frontend/src/components/workflow/AgentProgressPanel.tsx` — DELETED (controls absorbed into RunChatLane)
- `frontend/src/components/workflow/AgentProgressPanel.test.tsx` — DELETED (test for deleted component)
- `frontend/src/components/workflow/WaveTreePanel.tsx` — DELETED (superseded by AgentDetailPanel inline tree, Phase 39)
- `frontend/src/components/layout/DashboardLayout.waveMount.test.tsx` — DELETED (keep-alive test; sole subject was WaveTreePanel)
- `frontend/src/components/chat/blocks/TodoCard.tsx` — DELETED (no `todo` block kind — ISS-037)
- `frontend/src/components/chat/blocks/blocks.test.tsx` — MODIFIED (removed TodoCard import + describe block)
- `frontend/src/components/layout/DashboardLayout.tsx` — MODIFIED (2 stale comments corrected)
- `frontend/src/components/preview/PreviewPanel.tsx` — MODIFIED (1 stale comment corrected)
- `frontend/src/app/dashboard/page.tsx` — MODIFIED (1 stale comment corrected)
- `frontend/src/types/index.ts` — MODIFIED (2 stale comments corrected)

## Safety Guard — grep proof of zero live importers (per component)

Precise grep over `frontend/src` for real `import` statements and JSX mounts (`<Name`), excluding comments and `WaveGroup` type-imports from `types/index`:

- **AgentProgressPanel** — real import + JSX mount only in its own test (deleted). No production importer. Two inert `vi.mock(".../AgentProgressPanel")` stubs in `DashboardLayout.waveMount.test.tsx` (since also deleted) and `catalogHome.test.tsx` (DashboardLayout no longer imports the path); catalogHome still passes after deletion. → DELETED.
- **TodoCard** — real import + JSX mount only in `blocks.test.tsx` (retired). No production importer. → DELETED.
- **WaveTreePanel** — after deletion, `grep -rn "import.*WaveTreePanel\|<WaveTreePanel" src` → **0 live references.** The only initial "importer", `DashboardLayout.waveMount.test.tsx`, stubbed PreviewPanel to `await import(".../WaveTreePanel")` and render it — a fiction (the real PreviewPanel never mounts WaveTreePanel; the live wave tree is AgentDetailPanel's inline block). Confirmed production-dead by the orchestrator; the test was retired with its subject. 4 remaining textual mentions (`AgentDetailPanel.tsx:12,266`, `StepsDrilldown.test.tsx:13`, `PreviewPanel.tsx:337`) are all accurate "former/retired" history. → DELETED.

## Verification

- **tsc:** `npx tsc --noEmit` → **0 errors** (excl. known `mockApi` noise).
- **blocks vitest:** `blocks.test.tsx` → 5 passed (TodoCard case retired).
- **Full suite:** `npx vitest run` → **667 passed, 8 failed** (96 files). **Net-new failures = 0.** The 8 are the confirmed pre-existing baseline (verified failing at the pre-Phase-42 commit `8c2f0b9d`):
  - `PreviewPanel.switcher.test.tsx` ×3
  - `PreviewPanel.degraded.test.tsx` ×1
  - `HomeLaunchGrid.inspect.test.tsx` ×2
  - `FilesTab.runInput.test.tsx` ×2
  Passing count dropped 671→667 — exactly the 4 `waveMount.test.tsx` tests removed with the retired file (expected). Test-file count 97→96 (waveMount removed).
- **Live-reference grep:** `import.*WaveTreePanel|<WaveTreePanel` → 0 across `frontend/src`.
- **Fidelity harness:** not run (heavy playwright capture); justified — all three deleted components had zero JSX mounts, so rendered DOM is byte-identical; the only e2e references are historical comments, not live selectors. The waves→construction-tree forwarding stays covered by the AgentDetailPanel/AgentThinkingTab construction tests + the fidelity harness.

## Decisions Made
- **WaveTreePanel removed after blocker resolution.** The initial pre-delete guard flagged `DashboardLayout.waveMount.test.tsx` as a live importer/mount. The orchestrator verified WaveTreePanel is production-dead (every non-test `frontend/src` reference is a comment; the live wave tree is AgentDetailPanel's inline construction block, Phase 39 — which explicitly retired the separate panel, INV-12) and that the keep-alive test was asserting against a fiction (a stubbed PreviewPanel importing + rendering the real component, which the production PreviewPanel never does). Directed: delete the component + retire the test exactly as AgentProgressPanel.test.tsx was retired with its component.
- **Stale comments corrected, history preserved.** Comments implying a *live* WaveTreePanel mount (`DashboardLayout.tsx:~152, ~1702`, `PreviewPanel.tsx:~336`, `app/dashboard/page.tsx:~115`, `types/index.ts:~86, ~135`) were rewritten to name AgentDetailPanel's inline construction/wave tree, keeping the data-flow description. `AgentDetailPanel.tsx:12,266` and `StepsDrilldown.test.tsx:13` were left as-is — they already describe WaveTreePanel as the FORMER/retired component (accurate history).

## Deviations from Plan

### Blocker — RESOLVED

**1. [Guard/STOP-and-flag → resolved] WaveTreePanel keep-alive test**
- **Found during:** Task 1 (pre-delete safety grep).
- **Issue:** `DashboardLayout.waveMount.test.tsx` dynamically imported and rendered the real `WaveTreePanel` via a PreviewPanel stub, with 4 assertions on its output — a live importer that contradicted the "zero mounts" precondition and would have produced net-new failures if the component were deleted blind.
- **Resolution:** Orchestrator confirmed WaveTreePanel is production-dead and the test asserts against a fiction. Deleted `WaveTreePanel.tsx` + retired `DashboardLayout.waveMount.test.tsx` (subject deleted), then corrected the now-stale comments. Grep confirms 0 live references; the 8-failure baseline held with 0 net-new.

---

**Total deviations:** 1 blocker (raised in session 1, resolved by orchestrator in session 2). 0 auto-fixes.
**Impact on plan:** Group E fully delivered — all three dead components removed with zero net-new failures and one wave-tree implementation (INV-12). RUNUI-06 satisfied.

## Issues Encountered
- The plan's cited line numbers for the stale comments (`DashboardLayout.tsx:1781-1784`) were stale; the actual WaveTreePanel relocation comment is at `:1702-1705`. Located and corrected by content, not line number.

## Next Phase Readiness
- Group E (dead-code removal) complete: AgentProgressPanel, WaveTreePanel, TodoCard and their tests removed; INV-12 one-implementation-per-behavior holds on the run screen.
- No blockers remaining for this plan.

## Self-Check: PASSED
- GONE: AgentProgressPanel.tsx, AgentProgressPanel.test.tsx, TodoCard.tsx, WaveTreePanel.tsx, DashboardLayout.waveMount.test.tsx
- 0 live (import/JSX) WaveTreePanel references in frontend/src
- Commits `23e05167` + `d0679f13` present on feat/ui-2
- tsc clean; vitest 8-failure baseline held (0 net-new)

---
*Phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-*
*Completed: 2026-07-15*
