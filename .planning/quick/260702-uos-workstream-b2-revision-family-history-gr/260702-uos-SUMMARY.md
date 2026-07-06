---
phase: 260702-uos
plan: 01
subsystem: ui
tags: [react, revision-families, workflow-history, motion, aria, vitest]

# Dependency graph
requires:
  - phase: 260702-u2o (Workstream B1)
    provides: "getRunFamily fetcher, WorkflowRun.parentRunId/rootRunId, RunFamily/FamilyMember types, history-revision parent linkage"
provides:
  - "History list grouped by rootRunId — one FamilyGroupCard per family root (v{N} pill + latest status, expandable version rows)"
  - "Detail version-timeline chip row (radiogroup) above the tab bar; click loads a version via getWorkflow with an AnimatePresence cross-fade"
  - "RevisionFamilyView.tsx: groupRunsByFamily, FamilyGroupCard, VersionTimeline, statusDotClass, baseWorkflowType, extractRevisionInstructionPreview (preview-only shim)"
affects: [Workstream B3 (deliverable 5 live PreviewPanel chip, deliverable 6 Files base-version section), Workstream C (parseRunInput replaces the B2 preview shim)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "REUSE-FIRST: every visual node inherits an existing analog (file:line) — no new hex/radii/font-size/motion-curve"
    - "Client-side family grouping on the server-supplied rootRunId (no workflow-name branching, SC-001)"
    - "Roving-tabindex radiogroup with managed focus (focus only moves after a user-initiated switch)"

key-files:
  created:
    - frontend/src/components/history/RevisionFamilyView.tsx
    - frontend/src/components/history/WorkflowHistory.family.test.tsx
  modified:
    - frontend/src/components/history/WorkflowHistory.tsx

key-decisions:
  - "Duplicated the tiny presentational helpers (TYPE_META, formatDate, formatDuration) into RevisionFamilyView instead of importing them from WorkflowHistory — avoids a circular import while WorkflowHistory imports the family components back"
  - "Distributed the UI-SPEC radiogroup border-b onto the outer strip wrapper (identical inherited token) so a revision context line sits cleanly beneath the chips without an internal divider"
  - "extractRevisionInstructionPreview is a preview-only slice shim, flagged for retirement to Workstream C parseRunInput (INV-12)"

patterns-established:
  - "FamilyGroupCard threads openMenuId/onToggleMenu/onDeleteClick through props so the extracted row keeps delete-from-history without referencing WorkflowHistory-local state (W1)"
  - "Controlled chevron rotate via ${expanded ? 'rotate-90' : ''} (NOT group-open, which only fires inside a native <details>) (W2)"

requirements-completed: [POR-5-D3, POR-5-D4]

# Metrics
duration: ~15min
completed: 2026-07-02
---

# Phase 260702-uos Plan 01: Workstream B2 — Revision-family history grouping + detail version timeline

**History runs now group by rootRunId into one expandable family card (v{N} pill + chronological version rows), and the run-detail view gains a keyboard-navigable version-timeline chip row that cross-fades between versions — frontend-only, zero backend edits, every node inheriting an existing analog.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-02T22:14:00Z (approx)
- **Completed:** 2026-07-02T22:29:00Z (approx)
- **Tasks:** 3
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments
- **Deliverable 3 (history grouping):** the flat run list groups by `rootRunId`; multi-member families render one root card with a `v{N}` pill + the latest member's status, expandable into chronological version rows with `↳ revises v{n}` microcopy. Single-member (and legacy NULL-parent) families are byte-identical to today's flat row — including the threaded delete menu (zero regression). Type-filter tabs count each family once under its base type.
- **Deliverable 4 (detail version timeline):** opening a run fetches its family via `getRunFamily(token, rootRunId)` and renders a `VersionTimeline` chip row above the tab bar ONLY for families with ≥2 members. Clicking a chip loads that version via `getWorkflow` into the same detail surface (tab-preserving), cross-fading all tabs via `AnimatePresence mode="wait"` keyed on `selectedRun.id`. Revision versions show a `↳ Revises v{n-1} — '{preview}'` context line; the chip row is a `role="radiogroup"` with Arrow-key nav, roving tabindex, and managed focus.
- **5 real rendered-DOM vitest specs** — grouping, single-member, timeline render, version switch, a11y — all green.

## Task Commits

Each task was committed atomically (code + its tests):

1. **Task 1: Deliverable 3 — History family grouping** - `f0a4ccd1` (feat)
2. **Task 2: Deliverable 4 — Detail version timeline** - `916ed97a` (feat)
3. **Task 3: vitest behavior specs** - `0fe3c908` (test)

## Files Created/Modified
- `frontend/src/components/history/RevisionFamilyView.tsx` (new) — `groupRunsByFamily`, `FamilyGroupCard`, `VersionTimeline`, `statusDotClass`, `baseWorkflowType`, `extractRevisionInstructionPreview`. All styling inherited per WORKSTREAM-B-UI-SPEC (cited inline).
- `frontend/src/components/history/WorkflowHistory.tsx` (modified) — list view: `matchesFilter` predicate, `expandedFamilies` state, `groupRunsByFamily(runs)` render, family-once `typeCounts`. Detail view: `getRunFamily` fetch keyed on stable `rootRunId`, `handleSelectVersion`, `VersionTimeline` above the tab bar, content region wrapped in `AnimatePresence mode="wait"`.
- `frontend/src/components/history/WorkflowHistory.family.test.tsx` (new) — 5 behavior specs cloning the B1 revise scaffold + `getRunFamily` mock.

## Decisions Made
- **Helper duplication over circular import:** `TYPE_META`/`formatDate`/`formatDuration` are small presentational utilities re-declared in `RevisionFamilyView` (with a comment) rather than exported from `WorkflowHistory` — because `WorkflowHistory` imports `FamilyGroupCard`/`VersionTimeline` back, and a mutual import would be a runtime-fragile cycle. These are view formatters, not the engine dual-impl INV-3 targets.
- **Border placement:** the UI-SPEC-cited radiogroup `border-b border-gray-100 bg-white` token is applied on the outer version-strip wrapper so a revision's context line renders beneath the chips without an internal divider — same inherited token, cleaner stack before the tab bar.

## Deviations from Plan

None — plan executed exactly as written. The 4 folded-in plan-check fixes (W1 delete-menu prop-threading, W2 controlled chevron rotate, W3 defensive v{N} window-count note, I1 id-keyed getWorkflow mock) were implemented as specified in the plan text.

## Known Stubs

- **`extractRevisionInstructionPreview` (RevisionFamilyView.tsx)** — an *intentional*, documented preview-only slice shim (UI-SPEC "Revision-instruction display" micro-contract). It carries an inline INV-12 hand-off comment: Workstream C (§6.1) replaces this single call site with `parseRunInput(input).revisionInstruction`. It is NOT a defect — it returns a real, correctly-extracted ≤60-char preview for the context line today; B deliberately does not author a second marker-family parser. Resolved by Workstream C.

## Issues Encountered
None. All gates passed first try — tsc introduced zero new errors (only the 3 known pre-existing reds: `mockApi.ts` ×2 TS2352, `IdeaInputPage.tsx:738` TS17001), and all 5 vitest specs were green on first run.

_Note: the plan's tsc verify grep filter (`IdeaInputPage.tsx:738`) does not match tsc's actual `IdeaInputPage.tsx(738,9)` line format, so the literal command counts 1 rather than 0. Verified by filename filter instead: `grep -vE 'mockApi\.ts|IdeaInputPage\.tsx'` yields zero lines, and the total error count is exactly 3 (the known baseline)._

## User Setup Required
None — no external service configuration required. Frontend-only change reusing existing dependencies (motion/react, lucide-react, existing fetchers). Zero new packages.

## Next Phase Readiness
- B3 (deliverable 5 live PreviewPanel version chip; deliverable 6 Files base-version section) is unblocked — `statusDotClass`, `extractRevisionInstructionPreview`, and the family-grouping/timeline patterns are reusable analogs.
- Workstream C should replace the `extractRevisionInstructionPreview` call site in `VersionTimeline` with `parseRunInput(...).revisionInstruction` and delete the shim.
- INV-3 held by construction: zero backend/engine/websocket/manifest/migration edits — the golden battery + semantic-event parity are untouched.

## Self-Check: PASSED

- `frontend/src/components/history/RevisionFamilyView.tsx` — FOUND
- `frontend/src/components/history/WorkflowHistory.family.test.tsx` — FOUND
- `.planning/quick/260702-uos-.../260702-uos-SUMMARY.md` — FOUND
- Commit `f0a4ccd1` (Task 1), `916ed97a` (Task 2), `0fe3c908` (Task 3) — all FOUND
- Backend scope fence: `git diff --name-only 260c4dd6 HEAD -- backend/` empty — INV-3 by construction

---
*Phase: 260702-uos*
*Completed: 2026-07-02*
