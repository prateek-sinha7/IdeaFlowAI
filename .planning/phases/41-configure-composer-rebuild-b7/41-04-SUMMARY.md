---
phase: 41-configure-composer-rebuild-b7
plan: 04
subsystem: ui
tags: [react, nextjs, composer, workflow-authoring, agents-popup, motion, fidelity-oracle]

# Dependency graph
requires:
  - phase: 41-configure-composer-rebuild-b7
    provides: "AgentsPopup shared data model (pipelineAgents + SelectionsMap + declaredCapabilities) and its exported sub-components (AdvancedExpander / CapabilityPaletteSection / SkillsHooksTab / AgentPromptSection); the retained modal wrapper (LaunchWizard + IdeaInputPage callers)"
provides:
  - "Full-page Composer surface (mainView='composer') — the mock-fidelity Simple view: header + Simple⇄Canvas toggle, identity card (read-only Deliverable-type), reorderable agent rows, Capability palette, Skills & hooks, sticky Summary rail"
  - "composer/ComposerPage.tsx + AgentRow.tsx + IdentityCard.tsx + SummaryRail.tsx — additive components that REUSE the AgentsPopup sub-components (INV-3, not a dual implementation)"
  - "DashboardLayout mainView='composer' surface + entry from Home's 'Compose a custom workflow' card and edit-from-My-Workflows (pre-loaded)"
  - "ND-AK registered (per-agent lever depth); re-anchored ts-e.model-picker onto the composer's inline model picker"
affects: [41-05-canvas, 41-06-run-wiring, composer, agents-popup]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive surface reusing exported shared sub-components (INV-3): distinct entry/purpose, single shared data model — not a fork"
    - "Reused-lever depth: mock's inline dropdown/toggles are the collapsed row presentation; the actual SelectionsMap levers open the reused AdvancedExpander one expand deeper (ND-AK)"

key-files:
  created:
    - frontend/src/components/workflow/composer/ComposerPage.tsx
    - frontend/src/components/workflow/composer/AgentRow.tsx
    - frontend/src/components/workflow/composer/IdentityCard.tsx
    - frontend/src/components/workflow/composer/SummaryRail.tsx
    - frontend/src/components/workflow/composer/ComposerPage.test.tsx
  modified:
    - frontend/src/components/workflow/AgentsPopup.tsx
    - frontend/src/components/layout/DashboardLayout.tsx
    - frontend/e2e/tests/ts-e.model-picker.spec.ts
    - frontend/e2e/tests/zzz-shell-baseline.spec.ts
    - frontend/e2e/fidelity/assemble-phase41-gallery.mjs

key-decisions:
  - "Composer is ADDITIVE: the AgentsPopup modal wrapper is RETAINED (LaunchWizard + IdeaInputPage still use it); the composer only reuses its exported sub-components (INV-3)"
  - "Per-agent levers reuse AdvancedExpander + AgentPromptSection rather than re-implementing the mock's inline dropdown/toggles (ND-AK)"
  - "Home's custom-compose entry + edit-from-My-Workflows repointed to the composer via the centralized DashboardLayout handlers (handleSelectFeature custom→composer, handleLaunchSaved generic→composer), not by editing HomeLaunchGrid/SavedWorkflowsPage"

patterns-established:
  - "mainView union surface addition: add member + centralized handler branch + render block; entry components untouched (they already call the shared handlers)"
  - "Fidelity capture: a guarded SHELL_CAPTURE spec drives the surface into a POPULATED state; the assembler prefers the populated shot when present"

requirements-completed: [CMPUI-01, CMPUI-02]

# Metrics
duration: ~130min
completed: 2026-07-14
---

# Phase 41 Plan 04: Full-page Composer Simple view Summary

**A new full-page `mainView='composer'` authoring surface — mock-fidelity Simple view (header + Simple⇄Canvas toggle, identity card with read-only Deliverable-type, reorderable agent rows with an inline model pill + Validator/Gate/Retry chips + Custom-prompt, Capability palette, Skills & hooks, sticky Summary rail) — built ADDITIVELY by reusing the AgentsPopup shared data model + exported sub-components, with the modal wrapper retained (INV-3).**

## Performance

- **Duration:** ~130 min (across the build + two fidelity-checkpoint iterations)
- **Completed:** 2026-07-14
- **Tasks:** 2 (Task 1 autonomous build; Task 2 blocking fidelity checkpoint — human-approved)
- **Files modified:** 10 (5 created, 5 modified)

## Accomplishments
- Full-page Composer Simple view bound to the shared data model (pipelineAgents order + SelectionsMap + declaredCapabilities), reusing `AdvancedExpander` / `CapabilityPaletteSection` / `SkillsHooksTab` / `AgentPromptSection` (added `export` to the latter two + `getRole` / `getAgentInitials` / `PIPELINE_LABEL`).
- Header Simple⇄Canvas toggle (Simple active; Canvas placeholder until 41-05); identity card with read-only Deliverable-type (ND-AH); Summary rail with live est. duration and NO est. cost, Save-to-catalogue primary (ND-AG).
- `mainView='composer'` surface wired in DashboardLayout, reachable from Home's "Compose a custom workflow" card and edit-from-My-Workflows (pre-loaded), with the AgentsPopup modal retained for the wizard/input inline-edit flow.
- Re-anchored `ts-e.model-picker` onto the composer's inline model picker (new TS-E-05) + reconciled TS-E-02 to the whole-catalog reality + re-anchored the custom/no-agents case onto the composer.
- Human-approved fidelity checkpoint via a populated-state gallery capture; registered ND-AK for the reused-lever interaction depth.

## Task Commits
1. **Task 1: Full-page Composer Simple view (TDD: RED test observed, then GREEN)** — `e1490fad` (feat)
2. **Task 2 support: populated fidelity capture harness** — `3e517e7a` (test)

**Plan metadata (this closeout):** the `docs(41-04): close out Composer Simple view — register ND-AK + SUMMARY + STATE` commit on feat/ui-2 (this commit; a commit cannot embed its own hash).

## Files Created/Modified
- `frontend/src/components/workflow/composer/ComposerPage.tsx` — full-page surface: header + Simple⇄Canvas toggle + Simple view bound to the shared data model; Save-to-catalogue via NameWorkflowModal→createUserWorkflow; Add agent via reused AgentLibrary.
- `frontend/src/components/workflow/composer/AgentRow.tsx` — reorderable row (▲▼ + index + avatar + name + Core badge via getRole + role + inline model pill + Validator/Gate/Retry chips + Custom-prompt + remove); reuses AdvancedExpander (SelectionsMap) + AgentPromptSection.
- `frontend/src/components/workflow/composer/IdentityCard.tsx` — Name + Description editable; Deliverable-type read-only (ND-AH).
- `frontend/src/components/workflow/composer/SummaryRail.tsx` — agents · review-gates · strategy · live est. duration · declared caps · Save-to-catalogue; Run-once inert (41-06); no est. cost (ND-AG).
- `frontend/src/components/workflow/composer/ComposerPage.test.tsx` — 10 behavior tests + INV-3 source guards.
- `frontend/src/components/workflow/AgentsPopup.tsx` — added `export` to getRole, getAgentInitials, PIPELINE_LABEL, AgentPromptSection, SkillsHooksTab (modal wrapper unchanged/retained).
- `frontend/src/components/layout/DashboardLayout.tsx` — MainView += "composer"; ComposerPage import + render block; handleSelectFeature (custom→composer) + handleLaunchSaved (generic→composer) repoint; savedComposition carries name/description.
- `frontend/e2e/tests/ts-e.model-picker.spec.ts` — TS-E-02 reconciled (whole catalog); TS-E-01b-noagents re-anchored onto the composer; new TS-E-05 (composer inline model picker).
- `frontend/e2e/tests/zzz-shell-baseline.spec.ts` — guarded populated-composer capture (5 agents + active Gate chip).
- `frontend/e2e/fidelity/assemble-phase41-gallery.mjs` — ND-AK registered; composer-simple prefers the populated shot when present.

## Decisions Made
- **Additive, not dual (INV-3):** the composer reuses the AgentsPopup sub-components; the modal wrapper stays for the wizard/input inline-edit flow (distinct entry/purpose).
- **Reused-lever depth (ND-AK):** the mock's inline model dropdown + directly-toggling chips are the collapsed row presentation; the real Model/Validator/Gate/Retry levers + Custom-prompt open the reused AdvancedExpander + AgentPromptSection one expand deeper — reuse over re-implementation.
- **Centralized entry repoint:** the Home custom card and My-Workflows launch route to the composer via the shared DashboardLayout handlers, so HomeLaunchGrid/SavedWorkflowsPage were not edited (smaller diff, no fork).

## Deviations from Plan

### Non-auto-fix deviations (design choices, human-approved)

**1. HomeLaunchGrid.tsx / SavedWorkflowsPage.tsx not edited directly (plan listed them in files_modified)**
- **Reason:** the repoint is centralized in DashboardLayout's `handleSelectFeature` (`custom`→`composer`) and `handleLaunchSaved` (generic saved→`composer`), the handlers already wired to those components' `onSelectFeature("custom")` / `onLaunchSaved` props. Smaller diff, no fork.
- **Impact:** none — both entries reach the composer; verified via ts-e + capture navigation.

**2. Interim run-entry semantics (flagged, approved)**
- **Change:** `SavedWorkflowsPage` "Run workflow" on a custom/generic saved workflow now opens the Composer pre-loaded instead of running directly; the composer's Run-once is inert until 41-06. PPT/prototype saved workflows still route to their wizard unchanged.
- **Rationale:** follows the instruction "repoint onLaunchSaved — edit pre-loads the saved workflow"; the direct-run of saved custom workflows returns in 41-06.

**3. ts-e reconciliation**
- TS-E-02 was a pre-existing flagged red ("will FAIL until reconciled to the whole-catalog reality") — reconciled to the whole-catalog reality (Opus 4.6 offered, 6 options). TS-E-01b-noagents re-anchored onto the composer (custom→composer). Added TS-E-05 (composer inline model picker).

---

**Total deviations:** 3 design/harness deviations (no Rule 1–3 auto-fixes were needed). **Impact:** no scope creep; the composer is additive and the shared data model / tested modal path are unchanged.

## Issues Encountered

**Pre-existing React "setState-in-render" error in the reused AdvancedExpander (diagnosed; follow-up).**
- **Exact message:** `Cannot update a component (ComposerPage) while rendering a different component (AdvancedExpander). To locate the bad setState() call inside AdvancedExpander, follow the stack trace ... ComposerPage AdvancedExpander AdvancedExpander` (React `link/setstate-in-render`).
- **Cause:** in `AgentsPopup.tsx` `AdvancedExpander.updateLever`, the parent notify `onSelectionsChange?.(next)` is called INSIDE the `setSelections((prev) => { … })` state-updater. Calling a parent `setState` from within a child's state-updater is the "setState while rendering" anti-pattern. This is PRE-EXISTING shared behavior (the modal path uses the same code); it surfaced now because the composer mounts AdvancedExpander per row. 41-05 (Canvas) reuses the same per-node AdvancedExpander and would inherit it.
- **Fix status:** NOT fixed — it is not a trivial one-liner and the code is shared with the tested modal + IdeaInputPage run path (ts-e TS-E-03/04 assert the exact `selections` reach `run_pipeline`, an INV-3 byte-identical contract). Fixing it safely requires re-verifying that contract, which is out of 41-04's bounded scope.
- **Proposed follow-up fix:** move the parent notify OUT of the state-updater in `updateLever` — either compute `next` from the `selections` render closure and call `setSelections(next); onSelectionsChange?.(next);` in the event handler, or drop the inline call and report upward via `useEffect(() => onSelectionsChange?.(selections), [selections])`. Then re-run `ts-e.model-picker` + `AgentsPopup.reskin` + `ComposerPage` suites to prove the byte-identical `selections` contract holds. Recommended before 41-05.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- **41-05 (Canvas):** the `mainView='composer'` surface + the Simple⇄Canvas toggle are in place (Canvas branch renders a placeholder); Canvas mounts here. It reuses the same per-node AdvancedExpander — apply the ND-AK reuse pattern and address the AdvancedExpander setState-in-render follow-up above.
- **41-06 (Run wiring):** the Summary rail's Run-once button is present but inert (`onRunOnce={undefined}`); wire it to the real `onStartPipeline` seam.
- **Verification proven:** `tsc --noEmit` clean (excl. pre-existing mockApi.ts); `ComposerPage.test.tsx` 10/10; `ts-e.model-picker` 7 passed / 1 fixme; modal retained + sub-components reused (grep); fidelity human-approved.

## Self-Check: PASSED
- Created files exist: ComposerPage.tsx, AgentRow.tsx, IdentityCard.tsx, SummaryRail.tsx, ComposerPage.test.tsx — all FOUND.
- Commits exist: e1490fad (feat), 3e517e7a (test capture) — both FOUND in git log.
- ND-AK registered in assemble-phase41-gallery.mjs; ND range refs updated to ND-AE..AK.

---
*Phase: 41-configure-composer-rebuild-b7*
*Completed: 2026-07-14*
