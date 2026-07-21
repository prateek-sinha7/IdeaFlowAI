---
phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-
plan: 05
subsystem: ui
tags: [react, vitest, tdd, INV-12, SC-001, run-screen, artifact-preview]

# Dependency graph
requires:
  - phase: 42-02
    provides: "Removed the ReviewGatePanel cascade branch + import from DashboardLayout, leaving the panel file production-dead and extractable."
provides:
  - "Shared components/results/artifactPreview.tsx module: discriminateArtifact() + read-only SpecPreview/TasksPreview/AnalysisPreview — one implementation per behavior (INV-12)."
  - "discriminateArtifact(output, artifactKind) — the name-free artifact discriminator (SC-001), the contract the W4 consumers (42-08 gate plan-preview, 42-09 settled cards) build against."
  - "ReviewGatePanel.tsx + ReviewGatePanel.test.tsx deleted; parsers/discriminator survive in exactly one copy."
affects: [42-08 gate plan-preview, 42-09 settled artifact cards]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Interface-first extraction: pull the shared discriminator + parsers into a reusable module BEFORE deleting the source file, so no parser logic is stranded (INV-12)."
    - "Name-free artifact discrimination: card/preview kind keyed ONLY on (output, artifactKind) via wrapper-tag sniff + declared kind, never a workflow/agent-name literal (SC-001)."

key-files:
  created:
    - frontend/src/components/results/artifactPreview.tsx
    - frontend/src/components/results/artifactPreview.test.tsx
  modified:
    - frontend/src/components/layout/DashboardLayout.catalogHome.test.tsx
  deleted:
    - frontend/src/components/preview/ReviewGatePanel.tsx
    - frontend/src/components/preview/ReviewGatePanel.test.tsx

key-decisions:
  - "TasksPreview dropped its onTasksChange edit affordance (and the per-task delete button) — the shared module is read-only; the editable gate path stays separate via InlineGateActions."
  - "The doc-comment token 'dangerouslySetInnerHTML' was reworded to 'raw HTML injection' so the SC-guard grep (== 0) reads a true zero rather than tripping on a negation in prose."
  - "The orphaned vi.mock('@/components/preview/ReviewGatePanel') stub in DashboardLayout.catalogHome.test.tsx was removed with the delete — DashboardLayout stopped importing ReviewGatePanel in 42-02, the stub's data-testid was never asserted, so it was dead and would dangle a resolve against a deleted module."

patterns-established:
  - "RED-first characterization port: write the discriminator/parser tests against the new module path, confirm they fail (module unresolved), then GREEN by creating the module."

requirements-completed: [RUNUI-06, RUNUI-08]

# Metrics
duration: 20min
completed: 2026-07-15
---

# Phase 42 Plan 05: Extract shared artifactPreview module, delete ReviewGatePanel Summary

**The name-free artifact discriminator and the Spec/Tasks/Analysis parsers now live once, in `components/results/artifactPreview.tsx`, as the contract the two W4 consumers (42-08 gate plan-preview, 42-09 settled cards) build against — and `ReviewGatePanel.tsx` is deleted with zero orphaned logic and zero live imports (INV-12 lynchpin).**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-15T01:12Z
- **Completed:** 2026-07-15T01:16Z
- **Tasks:** 2
- **Files:** 2 created, 1 modified, 2 deleted

## Accomplishments

### Task 1 — Create the shared artifactPreview module (TDD)
- Wrote `artifactPreview.test.tsx` first (19 characterization cases: discriminator precedence spec→tasks→analysis, artifactKind-authoritative + wrapper-tag fallback, case-insensitive tags, null generic-degrade; the three parsers incl. verdict READY/CAUTION/NEEDS-REVISION classification and raw-`<pre>` fallbacks). Confirmed RED (module unresolved), then GREEN.
- Created `artifactPreview.tsx` exporting `discriminateArtifact`, `SpecPreview`, `TasksPreview`, `AnalysisPreview` — the three previews moved verbatim from ReviewGatePanel (SpecPreview :57-102, TasksPreview :104-160, AnalysisPreview :174-200), TasksPreview made read-only.
- `discriminateArtifact` factored from ReviewGatePanel's discriminator (:270-273); keys ONLY on `(output, artifactKind)`.

### Task 2 — Delete ReviewGatePanel (completes §A4)
- Re-grepped for real importers: the only live code reference was an orphaned `vi.mock` stub (DashboardLayout no longer imports ReviewGatePanel after 42-02). Removed the dead stub, then deleted `ReviewGatePanel.tsx` + `ReviewGatePanel.test.tsx`.
- Grep-confirmed 0 live `ReviewGatePanel` import / `vi.mock` / JSX references (13 remaining matches are all comments/docstrings — historical, permitted).

## Verification

- **`discriminateArtifact` export count:** 1 (INV-12, one implementation).
- **SC-001 name-literal grep** (`pipeline_type|spec.id ==|prototype-|/build|construct/`): 0.
- **`dangerouslySetInnerHTML` grep:** 0 (parsers render escaped React text; T-42-05-01 mitigated).
- **`npx tsc --noEmit`:** clean (0 `error TS`, excluding the pre-existing mockApi noise).
- **`npx vitest run`:** 8 failed / 679 passed. The 8 failures are EXACTLY the pre-existing baseline — `PreviewPanel.switcher` ×3, `PreviewPanel.degraded` ×1, `HomeLaunchGrid.inspect` ×2, `FilesTab.runInput` ×2 — zero net-new. The 19 new `artifactPreview` tests are GREEN; deleting `ReviewGatePanel.test.tsx` retired its 7 Redo-control tests (expected).
- **Fidelity harness** (`FIDELITY_CAPTURE=1 npx playwright test zzz-baseline`): 8/8 passed.

## Deviations from Plan

**None materially.** Two minor in-scope adjustments, both tracked here:
1. **[Rule 3 - Blocking]** Removed the orphaned `vi.mock` for ReviewGatePanel in `DashboardLayout.catalogHome.test.tsx` — a dead stub for a no-longer-imported module that would dangle a resolve against the deleted file. Removal keeps the delete clean and the catalogHome test green (2/2).
2. **[Rule 1 - Correctness]** Reworded a doc-comment so the `dangerouslySetInnerHTML == 0` guard reads a true zero rather than matching the word inside a "no ..." negation.

## Threat Flags

None — no new network endpoint, auth path, file-access pattern, or schema surface introduced. The extracted parsers consume in-state agent output only (no new fetch/data source) and render escaped React text.

## Commits

- `0571950f` feat(42-05): extract shared artifactPreview module (discriminator + Spec/Tasks/Analysis previews)
- `f7052874` refactor(42-05): delete ReviewGatePanel; parsers now live only in artifactPreview (INV-12)

## Self-Check: PASSED

- FOUND: frontend/src/components/results/artifactPreview.tsx
- FOUND: frontend/src/components/results/artifactPreview.test.tsx
- DELETED (ok): frontend/src/components/preview/ReviewGatePanel.tsx
- DELETED (ok): frontend/src/components/preview/ReviewGatePanel.test.tsx
- FOUND commit: 0571950f
- FOUND commit: f7052874
