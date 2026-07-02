---
phase: 260702-vff
plan: 01
subsystem: ui
tags: [react, revision-families, preview-panel, files-tab, motion, aria, vitest]

# Dependency graph
requires:
  - phase: 260702-u2o (Workstream B1)
    provides: "getRunFamily fetcher, WorkflowRun.parentRunId/rootRunId, RunFamily/FamilyMember types, contentSourceRunId linkage"
  - phase: 260702-uos (Workstream B2)
    provides: "statusDotClass (inherited status→dot map), RevisionFamilyView presentational-sibling pattern, controlled-chevron W2 lesson"
provides:
  - "LiveVersionChip.tsx: presentational v{n} ▾ chip + version dropdown (listbox) + amber read-only banner — all styling inherited per UI-SPEC Surface 3"
  - "PreviewPanel live version chip: optional runFamily/liveRunId props, viewingVersion/pulse state, getWorkflow read-only older-version override, revise-suppression while read-only"
  - "DashboardLayout getRunFamily fetch keyed on contentSourceRunId, threading runFamily + liveRunId into PreviewPanel"
  - "FilesTab base-version 'From v{n-1}' collapsed section with lazy getWorkflow(parentRunId) fetch; module-level deriveDeliverableFiles helper (INV-12 net-negative extraction)"
affects: [Workstream C (parseRunInput would supply richer read-only banner instruction text if ever needed)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "REUSE-FIRST: every visual node inherits an existing analog (file:line) — no new hex/radii/font-size/motion-curve; the only hex literal is the inherited #1B2A4A"
    - "Presentational sibling extraction (LiveVersionChip mirrors B2's RevisionFamilyView) — PreviewPanel owns state + the one on-demand getWorkflow read-only fetch"
    - "Lazy-on-first-expand fetch guarded by a baseFetched ref (no fetch while collapsed)"
    - "INV-12 net-negative: deriveDeliverableFiles extracted + deleted from the FilesTab body, reused by the base-version section"

key-files:
  created:
    - frontend/src/components/preview/LiveVersionChip.tsx
    - frontend/src/components/preview/PreviewPanel.versionChip.test.tsx
    - frontend/src/components/results/FilesTab.baseVersion.test.tsx
  modified:
    - frontend/src/components/preview/PreviewPanel.tsx
    - frontend/src/components/layout/DashboardLayout.tsx
    - frontend/src/components/results/FilesTab.tsx

key-decisions:
  - "DashboardLayout owns the getRunFamily fetch (it already receives contentSourceRunId + mounts PreviewPanel) — the minimal seam, no page.tsx pass-through prop"
  - "PreviewPanel owns the ONE on-demand getWorkflow read-only fetch + the renderType→slot mapping so no override content is duplicated up to DashboardLayout"
  - "Local formatRelativeTime helper + local WorkflowStatus cast in LiveVersionChip (import only statusDotClass from RevisionFamilyView) — avoids an import cycle; FamilyMember.status is string so cast as WorkflowStatus exactly as RevisionFamilyView.tsx:464"
  - "Base-version section uses the plain uppercase SectionHeader label variant + a controlled chevron rotate (NOT group-open — the B2 W2 lesson)"

requirements-completed: [POR-5-D5, POR-5-D6]

# Metrics
duration: ~20min
completed: 2026-07-02
---

# Phase 260702-vff Plan 01: Workstream B3 — Live version chip in PreviewPanel + base-version Files section

**The live dashboard preview now carries a v{n} ▾ version chip that opens a listbox of the on-screen content's revision family and loads older versions read-only via getWorkflow (amber "Back to latest →" banner, revise actions suppressed), and the Files tab gains a collapsed "From v{n-1}" section that lazily fetches the parent run's files — frontend-only, zero backend edits, every visual node inheriting an existing analog. This CLOSES Workstream B.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 3
- **Files:** 6 (3 created, 3 modified)

## Accomplishments

- **Deliverable 5 (live version chip):** `LiveVersionChip.tsx` renders the `v{n} ▾` toggle-pill (PrototypePreview analog) + a `role="listbox"` dropdown (WorkflowHistory row-menu analog, outside-click catcher + Escape/Arrow-key nav) + the amber `ReadOnlyVersionBanner` (ReviewGatePanel analog). The chip is absent for standalone / single-member content and appears only for a ≥2-member family. Selecting an older version fetches it read-only via `getWorkflow`, routes its `.output` into the renderType-matched slot, shows the amber "Viewing v{k} (read-only) — Back to latest →" banner + the chip amber sub-dot, and suppresses `onRevise*`. "Back to latest →" restores the live content. When the threaded family grows the chip label ticks `v{n}→v{n+1}` with a one-shot `animate-pulse`; a new `liveRunId` resets any read-only view.
- **DashboardLayout fetch seam:** a `getRunFamily` effect keyed on `contentSourceRunId` (with a `.catch` that never throws) threads `runFamily` + `liveRunId` into PreviewPanel as new OPTIONAL props.
- **Deliverable 6 (base-version Files section):** the `user_stories/custom/ppt/prototype` single-deliverable branches were extracted into a module-level `deriveDeliverableFiles` helper and DELETED from the FilesTab body (INV-12 net-negative; FilesTab.test.tsx stayed green, proving byte-identical behaviour). A collapsed "From v{n-1}" section (gated on a non-null `parentRunId`) lazily fetches the parent run's files via `getWorkflow` on first expand only (guarded by a `baseFetched` ref), reusing `renderFileRow`; `aria-expanded` + `aria-busy` + the existing row-spinner idiom; a non-revision run shows no section.
- **6 real rendered-DOM vitest specs** covering chip visibility, dropdown + read-only load + banner + Back-to-latest, chip label tick, a11y roles, base-section presence + lazy fetch, and absence.

## Task Commits

Each task committed atomically (code + its tests):

1. **Task 1: Deliverable 5 — live version chip + DashboardLayout family fetch seam** — `c5d8e444` (feat)
2. **Task 2: Deliverable 6 — base-version Files section + parentRunId thread** — `2f4a7f84` (feat)
3. **Task 3: vitest real-DOM specs + regression audit** — `53e1e258` (test)

## Verification Results

- **tsc identity gate (hard):** `COUNT=3 NEW=0 → GATE_OK`. Exactly the 3 known pre-existing reds (`mockApi.ts` ×2, `IdeaInputPage.tsx(738,9)`); zero new-file regressions (verified by filename filter, not a file:line grep — the B2 lesson).
- **Full 11-suite regression command (2 new + 9 pre-existing):** `Test Files 11 passed (11) / Tests 66 passed (66)`. Green suites: PreviewPanel.versionChip (new), FilesTab.baseVersion (new), PreviewPanel.degraded, PreviewPanel.genericDeliverable, FilesTab, WorkflowHistory, WorkflowHistory.revise, WorkflowHistory.family, WorkflowHistory.genericReopen, DashboardLayout.catalogHome, DashboardLayout.waveMount. No pre-existing suite required an edit (all new props optional; the api-mock surface already exported the referenced fetchers).
- **INV-3 by construction:** `git diff --name-only c5d8e444~1 HEAD -- backend/` is empty — FRONTEND-ONLY, zero engine/websocket/manifest/migration edits.

## Deviations from Plan

None — plan executed exactly as written. One trivial in-task fix during Task 1's tsc gate: added `useRef` to the PreviewPanel React import (the new pulse-tracking ref referenced it) — a Rule 3 blocking-import fix, folded into the Task 1 commit before it landed.

## Known Stubs

None. No hardcoded empty values, placeholder text, or unwired data sources introduced. The read-only banner deliberately carries no revision-instruction text (per the plan / UI-SPEC — no parser is authored in Workstream B; Workstream C owns `parseRunInput`), which is a scope boundary, not a stub.

## Self-Check: PASSED

- `frontend/src/components/preview/LiveVersionChip.tsx` — FOUND
- `frontend/src/components/preview/PreviewPanel.versionChip.test.tsx` — FOUND
- `frontend/src/components/results/FilesTab.baseVersion.test.tsx` — FOUND
- Commit `c5d8e444` (Task 1), `2f4a7f84` (Task 2), `53e1e258` (Task 3) — all FOUND
- Backend scope fence: `git diff --name-only c5d8e444~1 HEAD -- backend/` empty — INV-3 by construction

---
*Phase: 260702-vff*
*Completed: 2026-07-02*
