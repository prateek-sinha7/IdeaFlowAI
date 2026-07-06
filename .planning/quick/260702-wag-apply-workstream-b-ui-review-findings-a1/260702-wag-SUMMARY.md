---
phase: 260702-wag
plan: 01
subsystem: ui
tags: [react, a11y, aria, listbox, radiogroup, revision-families, frontend, vitest]

# Dependency graph
requires:
  - phase: Workstream B (revision families FE)
    provides: RevisionFamilyView / LiveVersionChip / VersionTimeline + PreviewPanel & WorkflowHistory wiring
provides:
  - Keyboard-operable live version listbox (focus enters on open; Arrow/Enter/Space/Escape)
  - Keyboard-focusable history child version rows (native buttons + aria-label)
  - Deterministic (createdAt ASC, id ASC) family member ordering matching the backend /family contract
  - Unified lowercase "↳ revises v{n}" microcopy across list + timeline
  - Dev-observability console.warn on swallowed /family + version fetch failures
affects: [Workstream B a11y sign-off, Workstream C revision input parsing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "WAI-ARIA listbox: roving tabIndex on role=option buttons + declarative focus-in-effect keyed on the highlighted index (mirrors the VersionTimeline radiogroup)"

key-files:
  created: []
  modified:
    - frontend/src/components/preview/LiveVersionChip.tsx
    - frontend/src/components/history/RevisionFamilyView.tsx
    - frontend/src/components/history/WorkflowHistory.tsx
    - frontend/src/components/preview/PreviewPanel.tsx
    - frontend/src/components/preview/PreviewPanel.versionChip.test.tsx
    - frontend/src/components/history/WorkflowHistory.family.test.tsx

key-decisions:
  - "Declarative focus: focus the highlighted option from an effect keyed on highlightIdx (not focus-then-setState) so a subsequent re-render cannot blur it — mirrors VersionTimeline."
  - "Seed the highlight to the active version at open via openDropdown() (batched with setOpen) so the first render already has the correct roving tabIndex and focus target."
  - "String id compare via localeCompare (coincides with SQL byte-ordering for hex-UUID ids) as the createdAt tie-break."

patterns-established:
  - "Keyboard-operable dropdown listbox: roving tabIndex + per-option refs + focus-in-effect keyed on the active/highlighted index; keydown handled on the listbox container via bubbling."

requirements-completed: [UIREV-B-A11Y-LISTBOX, UIREV-B-A11Y-CHILDROWS, UIREV-B-CONSISTENCY-VNUM, UIREV-B-MICROCOPY, UIREV-B-OBSERVABILITY]

# Metrics
duration: ~35min
completed: 2026-07-02
---

# Phase 260702-wag Plan 01: Apply Workstream-B UI-Review Findings Summary

**Fixed the a11y sign-off blocker — the live version listbox is now keyboard-operable (focus enters on open; Arrow/Enter/Space/Escape) and history child rows are native buttons — plus deterministic cross-surface v-numbering, unified microcopy, and observable fetch failures, with zero backend edits and zero new visual language.**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-07-02T23:29Z (approx)
- **Completed:** 2026-07-02T23:38Z (approx)
- **Tasks:** 3
- **Files modified:** 6 (4 source, 2 test)

## Accomplishments

- **FIX 1 (BLOCK, §8):** `LiveVersionChip` listbox is fully keyboard-operable. Per-option refs + roving `tabIndex`; opening the dropdown seeds the highlight to the active version and moves keyboard focus onto that option; ArrowUp/ArrowDown move highlight+focus, Enter/Space select (loads read-only via `getWorkflow`), Escape closes and returns focus to the chip. Pointer path + every aria attribute preserved; no new styling.
- **FIX 2 (FLAG, §8):** Each expanded history child version row is now a native `<button type="button">` with `aria-label="Version {n}, {status}"`, keyboard-focusable/activatable; the exact row className is preserved (+`w-full text-left`), root family-card rows untouched (audit-scoped out).
- **FIX 3 (FLAG):** `groupRunsByFamily` now sorts members by `(createdAt ASC, id ASC)` — the same deterministic tie-break as the Workstream-A `/family` endpoint — with an inline comment citing the backend contract (revision_index == created_at-ASC rank, tie-broken by id) and the windowed-count caveat (POR §11 / B2 W3).
- **FIX 4 (FLAG):** Timeline context line is now lowercase "↳ revises v{n}", matching the list child-row form. Zero "Revises v" remaining.
- **FIX 5 (FLAG, LOW):** `console.warn("[revision-family] …")` added at the family-fetch, version-fetch (WorkflowHistory), and read-only-fetch (PreviewPanel) catch sites; graceful-degrade behavior and all aria unchanged; no UI added.
- Both existing specs EXTENDED (no parallel files) with real rendered-DOM `fireEvent.keyDown` behavior.

## Gate Results

- **tsc identity gate:** `GATE_OK` — COUNT==3 total `error TS` lines, FILT==0 after filtering the known `mockApi`/`IdeaInputPage` baseline. The edits introduce zero new type errors.
- **Full 11-suite regression set:** `11 passed (11)` files, **68 tests passed** — PreviewPanel.versionChip, WorkflowHistory.family, PreviewPanel.degraded, PreviewPanel.genericDeliverable, FilesTab.test, FilesTab.baseVersion, WorkflowHistory.{test,revise,genericReopen}, DashboardLayout.{catalogHome,waveMount}. No sibling regressed.
- **Task 1 grep gate:** `A11Y_WIRED`. **Task 2 grep gate:** `CONSISTENCY_OK`.
- **INV-3 by construction:** all 6 touched files are under `frontend/src/**`; zero backend edits.

## Task Commits

1. **Task 1: A11y keyboard-operability (FIX 1 + FIX 2)** — `933e6ce3` (feat)
2. **Task 2: Consistency + microcopy + observability (FIX 3/4/5)** — `1d509598` (feat)
3. **Task 3: Extend specs (real-DOM keyDown) + robust listbox focus** — `d8d813cd` (test)

_Docs (SUMMARY/STATE) intentionally not committed here — orchestrator handles docs._

## Files Created/Modified

- `frontend/src/components/preview/LiveVersionChip.tsx` — per-option refs + roving tabIndex; declarative focus-in-effect keyed on highlightIdx; `openDropdown()` seeds highlight to active version; Arrow handlers move highlight only.
- `frontend/src/components/history/RevisionFamilyView.tsx` — child rows → native buttons with aria-label; `(createdAt, id)` deterministic sort + backend-contract comment; lowercase timeline "revises" microcopy.
- `frontend/src/components/history/WorkflowHistory.tsx` — `console.warn("[revision-family] …")` in the family-fetch and version-fetch catch sites (graceful degrade unchanged).
- `frontend/src/components/preview/PreviewPanel.tsx` — `console.warn("[revision-family] …")` in the read-only `handleSelectVersion` catch (fallback unchanged).
- `frontend/src/components/preview/PreviewPanel.versionChip.test.tsx` — added keyboard-nav spec (open→focus-in-listbox→ArrowUp→Enter loads via getWorkflow→Escape closes+returns focus to chip).
- `frontend/src/components/history/WorkflowHistory.family.test.tsx` — added child-row keyboard spec (button named "Version 2, completed" opens the version) + unified lowercase "↳ revises v" timeline microcopy assertion.

## Decisions Made

- **Declarative focus over imperative focus-then-setState.** The plan's step-5 approach (setHighlightIdx(next) then `optionRefs.current[next]?.focus()`) was implemented first but the focus did not stick under a real render: the `setHighlightIdx` re-render churns the inline per-option ref callbacks and blurs the just-focused button (empirically confirmed — removing the setState made focus stick; `activeElement` was `BODY` otherwise). Resolved by driving focus from an effect keyed on `highlightIdx` and seeding the highlight at open via `openDropdown()` (batched with `setOpen`). This is exactly the robust idiom the auditor praised in VersionTimeline (`RevisionFamilyView.tsx:403-411`), so the fix stays reuse-first and the plan's intent (focus enters on open; Arrow moves highlight+focus; Enter selects; Escape closes+returns to chip) is fully met.
- **String `id` tie-break via `localeCompare`** (satisfies the Task-2 grep gate and coincides with SQL byte-ordering for hex-UUID ids).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Listbox focus-on-open/Arrow did not survive re-render**
- **Found during:** Task 3 (writing the real-DOM keyboard spec)
- **Issue:** The plan's imperative `setHighlightIdx(next); optionRefs.current[next]?.focus()` pattern (both on open and in the Arrow handlers) left `document.activeElement === BODY` — the state update's re-render re-created the inline option ref callbacks and blurred the focused button. The keyboard path (the FIX 1 BLOCK) would not actually work.
- **Fix:** Made focus declarative — a `useEffect` keyed on `[open, highlightIdx]` focuses `optionRefs.current[highlightIdx]`; the highlight is seeded to the active version at open via `openDropdown()` (batched with `setOpen`); Arrow handlers now only move `highlightIdx`. Same behavior contract, mirrors VersionTimeline's proven idiom.
- **Files modified:** frontend/src/components/preview/LiveVersionChip.tsx
- **Verification:** Isolated debug harness confirmed `activeElement` becomes the option button (`contains: true`) once the focus-then-setState churn was removed; the full keyboard spec (open→focus-in-listbox→ArrowUp→Enter→Escape+focus-to-chip) passes.
- **Committed in:** d8d813cd (Task 3 commit)

**2. [Rule 1 - Bug] Family child-row test asserted an unreachable `getWorkflow` call**
- **Found during:** Task 3
- **Issue:** The planned assertion `expect(mockGetWorkflow).toHaveBeenCalled()` after activating a child row can never fire: `handleSelectRun` short-circuits when the run already has non-empty `output` (the `familyRuns()` fixture members all carry `output`), so it opens the detail view directly without a fetch.
- **Fix:** Asserted the observable open-behavior instead — activating the child-row button opens the detail view and the family version timeline renders its 3 radio chips (`await waitFor(() => expect(screen.getAllByRole("radio")).toHaveLength(3))`). This still proves `onSelectRun(member)` fired and the version opened.
- **Files modified:** frontend/src/components/history/WorkflowHistory.family.test.tsx
- **Verification:** Spec passes; still real rendered-DOM behavior (no source-lock).
- **Committed in:** d8d813cd (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs)
**Impact on plan:** Both fixes were necessary for the plan to actually hold — the first makes the FIX 1 BLOCK genuinely keyboard-operable (the plan's exact behavior contract, achieved via the reuse-first VersionTimeline idiom the plan itself named as the reference); the second corrects a test assertion that the target code path makes unreachable. No scope creep, zero new visual language, zero backend edits.

## Issues Encountered

- Diagnosing the focus blur required an isolated debug harness (writing `document.activeElement` state to a temp file, since vitest suppresses `console.log`) to confirm the effect ran with the refs populated but a trailing re-render blurred the focused node. Root-caused to the inline ref-callback churn on `setHighlightIdx` re-render; resolved as documented above. Temp debug artifacts removed; source reverted to the committed baseline before applying the clean fix.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Workstream B a11y sign-off is unblocked: the live listbox keyboard path and history child-row focusability both meet the §8 mandate, verified by real rendered-DOM specs.
- Pixel/live-render fidelity remains deferred to an authenticated live pass (per the audit's code-only scope) — not a blocker for this a11y gate.

## Self-Check: PASSED

All 6 modified source/test files exist on disk; all 3 task commits (`933e6ce3`, `1d509598`, `d8d813cd`) are present in git history; SUMMARY.md written.

---
*Phase: 260702-wag*
*Completed: 2026-07-02*
