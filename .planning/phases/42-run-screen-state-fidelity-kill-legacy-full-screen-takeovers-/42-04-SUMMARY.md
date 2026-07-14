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
  - "blocks.test.tsx TodoCard coverage retired."
affects: [42-run-screen dead-code follow-up, WaveTreePanel removal (blocked)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pre-delete grep guard (real import + JSX mount) gating each component deletion; a found importer aborts the delete (T-42-04-01 mitigation)."

key-files:
  created: []
  modified:
    - frontend/src/components/chat/blocks/blocks.test.tsx
  deleted:
    - frontend/src/components/workflow/AgentProgressPanel.tsx
    - frontend/src/components/workflow/AgentProgressPanel.test.tsx
    - frontend/src/components/chat/blocks/TodoCard.tsx

key-decisions:
  - "WaveTreePanel NOT deleted — a real importer/mount was found (DashboardLayout.waveMount.test.tsx), contradicting the plan's zero-mounts precondition. Guard fired; component retained."
  - "Task 2 (stale-comment cleanup) is a no-op: the WaveTreePanel relocation comments describe LIVE behavior since WaveTreePanel survives; editing them would misrepresent the code."

patterns-established:
  - "Guard-before-delete: verify zero real importers/mounts per component; STOP-and-flag on any real importer even in a test."

requirements-completed: []  # RUNUI-06 NOT fully satisfied — WaveTreePanel removal blocked.

# Metrics
duration: 18min
completed: 2026-07-15
---

# Phase 42 Plan 04: Delete dead code (Group E, INV-12) Summary

**AgentProgressPanel and TodoCard deleted as confirmed-dead surfaces; WaveTreePanel deletion blocked by a live importer/mount in DashboardLayout.waveMount.test.tsx (guard fired).**

## Performance

- **Duration:** ~18 min
- **Tasks:** 1 of 2 partially complete (Task 1 partial; Task 2 no-op due to blocker)
- **Files modified:** 1 modified, 3 deleted

## Accomplishments
- Deleted `components/workflow/AgentProgressPanel.tsx` + its test — its Stop/revise/suggestion controls were already absorbed into RunChatLane (verified: zero production import, zero JSX mount).
- Deleted `components/chat/blocks/TodoCard.tsx` and retired its `describe("TodoCard")` case in `blocks.test.tsx` — no `todo` block kind is emitted (ISS-037); the only importer was that test.
- Verified `WaveGroup` type in `types/index.ts` and its legitimate type-importers are untouched.

## Task Commits

1. **Task 1 (partial): Delete AgentProgressPanel + TodoCard** — `23e05167` (refactor)

WaveTreePanel deletion (part of Task 1) and Task 2 (comment cleanup) were NOT committed — see Blocker below.

## Files Created/Modified
- `frontend/src/components/workflow/AgentProgressPanel.tsx` — DELETED (dead: controls absorbed into RunChatLane)
- `frontend/src/components/workflow/AgentProgressPanel.test.tsx` — DELETED (test for deleted component)
- `frontend/src/components/chat/blocks/TodoCard.tsx` — DELETED (dead: no `todo` block kind — ISS-037)
- `frontend/src/components/chat/blocks/blocks.test.tsx` — MODIFIED (removed TodoCard import + describe block)

## Safety Guard — grep proof of zero live importers (per component)

Precise grep over `frontend/src` for real `import` statements and JSX mounts (`<Name`), excluding comments and `WaveGroup` type-imports from `types/index`:

- **AgentProgressPanel** — real import + JSX mount only in `AgentProgressPanel.test.tsx` (deleted with the component). No production importer. The two `vi.mock("@/components/workflow/AgentProgressPanel", …)` stubs in `DashboardLayout.waveMount.test.tsx:82` and `DashboardLayout.catalogHome.test.tsx:70` are inert (DashboardLayout no longer imports the path). **Empirically verified:** after deletion, both files pass (6/6 tests) — Vitest's factory `vi.mock` does not require the module to exist when nothing imports it. → SAFE, deleted.
- **TodoCard** — real import + JSX mount only in `blocks.test.tsx` (in-scope; retired). No production importer. → SAFE, deleted.
- **WaveTreePanel** — **REAL importer/mount found**: `DashboardLayout.waveMount.test.tsx:91` does `const { WaveTreePanel } = await import("@/components/workflow/WaveTreePanel")` and line 95 renders `<WaveTreePanel waves={waves ?? []} />`, with 4 live tests asserting its rendered output ("Wave / Subagent Tree", "Wave 0", "wave-worker-alpha", "No waves running."). → **GUARD FIRED — NOT deleted.**

## Verification

- **tsc:** `npx tsc --noEmit` → 0 errors (excluding the known `mockApi` noise).
- **blocks vitest:** `blocks.test.tsx` → 5 passed (TodoCard case retired; ThinkingBlock ×4 + FileOpsSummary ×1).
- **Out-of-scope vi.mock tests:** `DashboardLayout.waveMount` + `DashboardLayout.catalogHome` → 6 passed after AgentProgressPanel deletion (no mock-resolution breakage).
- **Full suite:** `npx vitest run` → 671 passed, 8 failed (4 files). **Net-new failures = 0.** The 8 failures are all pre-existing branch drift:
  - `PreviewPanel.switcher.test.tsx` ×3 + `PreviewPanel.degraded.test.tsx` ×1 — the 4 the plan named.
  - `HomeLaunchGrid.inspect.test.tsx` ×2 + `FilesTab.runInput.test.tsx` ×2 — **verified pre-existing at `HEAD~1`** via a throwaway worktree run (same 4 failed before my commit). These files have zero references to any deleted module (grep-confirmed). The plan's "4 pre-existing" count was written against an earlier branch state that has since drifted to 8.
- **Fidelity harness:** not run (heavy playwright capture). Justified: both deleted components had zero JSX mounts, so rendered DOM is byte-identical; the only e2e references to them are historical comments ("the retired AgentProgressPanel…"), no live selectors or imports. Harness is unaffected.

## Decisions Made
- **WaveTreePanel retained.** The plan's precondition ("all three have zero mounts") is false for WaveTreePanel: it is dynamically imported and rendered by `DashboardLayout.waveMount.test.tsx` (a maintained DashboardLayout relocation test proving the `waves` passthrough reaches PreviewPanel). Deleting it would break 4 tests in an out-of-scope file (net-new failures, violating the hard verification constraint), and rewriting that test is out of the declared scope. Per the mandatory pre-delete guard, deletion was aborted and flagged.
- **Task 2 is a no-op.** Task 2 targets the WaveTreePanel relocation comments (`DashboardLayout.tsx:1702-1705`, referenced as :1781-1784 in the plan's stale line numbers) and `app/dashboard/page.tsx:115`. Because WaveTreePanel survives, those comments describe LIVE behavior (the below-the-fold→PreviewPanel relocation is the current mount, proven by `waveMount.test.tsx`). They are not dangling references to a deleted symbol; editing them would misrepresent the code. No comment change made.

## Deviations from Plan

### Blocker (guard fired — component retained)

**1. [Guard/STOP-and-flag] WaveTreePanel has a live importer/mount — NOT deleted**
- **Found during:** Task 1 (pre-delete safety grep).
- **Issue:** `frontend/src/components/layout/DashboardLayout.waveMount.test.tsx:91` dynamically imports the real `WaveTreePanel` and mounts it (`:95` `<WaveTreePanel waves={waves ?? []} />`); 4 tests (`:172,185,195,203`) assert its rendered output. The plan/CONTEXT §E asserted "zero mounts" — contradicted.
- **Action:** Aborted the WaveTreePanel file-delete per the mandatory guard; retained the component. This cascades: Task 2's WaveTreePanel comment cleanup becomes invalid (comments now describe live behavior) → no comment change.
- **Resolution required (out of this plan's scope):** Either (a) reconcile `DashboardLayout.waveMount.test.tsx` to no longer render WaveTreePanel (rewrite the relocation assertion against PreviewPanel's current wave surface / AgentDetailPanel inline tree per CONTEXT §E), then delete WaveTreePanel + its comments; or (b) confirm WaveTreePanel is still the intended wave-tree host and drop it from Group E. This is a planning/scope decision (touches an out-of-scope behavior test).

---

**Total deviations:** 1 blocker (guard fired). 0 auto-fixes.
**Impact on plan:** 2 of the 3 dead components removed cleanly with zero net-new failures. WaveTreePanel removal + its comment cleanup remain open, pending reconciliation of an out-of-scope DashboardLayout test.

## Issues Encountered
- The plan's cited line numbers for the stale comments (`DashboardLayout.tsx:1781-1784`) are stale; the actual WaveTreePanel relocation comments are at `:1702-1705`. Moot given the blocker (no edit made).

## Next Phase Readiness
- AgentProgressPanel + TodoCard removal is complete and green.
- **Blocked:** WaveTreePanel deletion + comment cleanup (RUNUI-06 not fully satisfied). Requires a decision on `DashboardLayout.waveMount.test.tsx` (out-of-scope test with a live WaveTreePanel mount) before the component can be removed.

## Self-Check: PASSED
- GONE: AgentProgressPanel.tsx, AgentProgressPanel.test.tsx, TodoCard.tsx
- RETAINED (correct, guard fired): WaveTreePanel.tsx
- Commit `23e05167` present on feat/ui-2
- SUMMARY present on disk

---
*Phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-*
*Completed (partial): 2026-07-15*
