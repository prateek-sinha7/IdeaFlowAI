---
phase: 260702-wwx
plan: 01
subsystem: frontend
tags: [run-inputs, parser, artifacts-fetcher, clarify, retention, INV-12]
requires:
  - Workstream A `?kind=` filter on GET /api/runs/{id}/artifacts (260702-s3p)
  - B2 RevisionFamilyView.extractRevisionInstructionPreview shim
provides:
  - "lib/runInput.ts parseRunInput — single project-wide FE marker parser"
  - "api.getRunArtifacts fetcher + RunArtifactsResponse/ArtifactNode types"
  - "types ClarifyRound + PipelineRunState.clarifications?"
  - "useWorkflow.retainClarifyRound (live clarify retention, reset per run)"
  - "page.tsx submittedBrief capture on launch"
affects:
  - Workstream C2 (StartingPointCard + ClarificationsCard + Files rows) — consumes all of the above
tech-stack:
  added: []
  patterns:
    - "URLSearchParams query composition (mirrors getWorkflows)"
    - "raw-wire-shape fetcher (unnormalized, like getRunFamily/getChainContext)"
    - "run-scoped React state folded before panel unmount"
key-files:
  created:
    - frontend/src/lib/runInput.ts
    - frontend/src/lib/runInput.test.ts
    - frontend/src/lib/api.getRunArtifacts.test.ts
    - frontend/src/hooks/useWorkflow.clarifyRetention.test.ts
  modified:
    - frontend/src/components/history/RevisionFamilyView.tsx
    - frontend/src/lib/api.ts
    - frontend/src/types/index.ts
    - frontend/src/hooks/useWorkflow.ts
    - frontend/src/components/layout/DashboardLayout.tsx
    - frontend/src/app/dashboard/page.tsx
decisions:
  - "parseRunInput matches the ASYMMETRIC EXISTING open/close labels independently (no backreference), and treats REVISION REQUEST as format-tolerant (unclosed → EOF/next-marker)."
  - "safeCleanBrief IIFEs + the shim's manual marker scan deleted — one parser project-wide (INV-12 net-negative)."
  - "clarifications live in PipelineRunState; startPipeline fresh-state is the single per-run reset boundary (pipeline_start WS echo spreads prev so the reset holds)."
metrics:
  duration: ~26m
  completed: 2026-07-03
---

# Phase 260702-wwx Plan 01: Workstream C1 — Run-Inputs Foundation Summary

parseRunInput single-parser + getRunArtifacts fetcher + ClarifyRound types + live clarify/brief retention — the FRONTEND-ONLY plumbing C2 consumes, shipped with zero backend edits and a net-negative parser consolidation.

## What was built

**Task 1 — Shared parser + shim delegation (commit 1360f1ab)**
- `lib/runInput.ts`: `parseRunInput(input) → { brief, attachments[], revisionInstruction?, existingArtifactBlock?, chainContext?, preferences? }`. Exact (non-heuristic) string-slicing over six FE-composed marker families. Handles both checker-flagged gotchas: the ASYMMETRIC `=== EXISTING {X} ===` / `=== END EXISTING {Y} ===` open/close (matched independently, no backreference), and the tolerant UNCLOSED `=== REVISION REQUEST ===` (closes at `=== END REQUEST ===`, the next `===`-line, or EOF).
- `runInput.test.ts`: 7 pure-lib cases (plain, instruction-only, 2×attachments, inline-revision blob, unclosed revision, chain, preferences).
- `RevisionFamilyView.extractRevisionInstructionPreview` now DELEGATES to `parseRunInput` (keeps only the first-meaningful-line + 60-char clamp formatting; `MARKER = ` scan deleted). The B2 test still passes.

**Task 2 — Fetcher + types (commit 4a9ba122)**
- `api.getRunArtifacts(token, runId, {kind?, includeContent?})` → `GET /api/runs/{id}/artifacts` with `URLSearchParams`-composed `?kind=`/`?include=content`, Bearer auth, returns the raw `{ workflow_id, artifacts }` wire shape (unnormalized). First FE consumer of Workstream-A's kind filter.
- `RunArtifactsResponse`/`ArtifactNode` interfaces (no `created_at`, mirrors backend node shape).
- `ClarifyRound` type + `PipelineRunState.clarifications?`.

**Task 3 — Live retention + chain-site rewire (commit def5e2f4)**
- `useWorkflow.retainClarifyRound(round)` appends to `pipelineState.clarifications`; `INITIAL_STATE` + `startPipeline` fresh-state reset `clarifications: []` (the single per-run boundary).
- `DashboardLayout.handleQuestionnaireSubmit` folds an answered `ClarifyRound` (from `questionnaireQuestions` + built responses) via `onRetainClarifyRound` BEFORE `setQuestionnaireQuestions([])`.
- Both DashboardLayout chain sites rewired to `parseRunInput`; the two `safeCleanBrief` IIFEs deleted (INV-12 net-negative).
- `page.tsx` captures `submittedBrief` on every launch and threads `onRetainClarifyRound={retainClarifyRound}` down.

## Verification results

- **tsc identity gate:** `total=3 new=0` → **GATE_OK** (the 3 pre-existing mockApi/IdeaInputPage errors persist unchanged, zero new).
- **New specs:** 3 files / 10 tests green (runInput, api.getRunArtifacts, useWorkflow.clarifyRetention).
- **6-suite regression guard:** **6 files / 30 tests all green** — WorkflowHistory.{family,test,revise,genericReopen} + DashboardLayout.{catalogHome,waveMount}.
- **INV-12 net-negative:** `NET_NEGATIVE_OK` + `INV12_OK` (safeCleanBrief count 0, `MARKER = ` count 0, parseRunInput wired in both DashboardLayout + RevisionFamilyView, onRetainClarifyRound + submittedBrief present).
- **INV-3 by construction:** zero files under `backend/` across all 3 commits.

## Deviations from Plan

None — plan executed exactly as written. One in-flight correction: the initial chain-site rewrite reused the local variable name `safeCleanBrief`, which the INV-12 grep gate (count must be 0) rejected; renamed the locals to `chainBrief`/`historyBrief` before Task 3 commit. Not a behavior change, caught by the gate as intended.

## Known Stubs

None. `submittedBrief` is captured-only (not yet read) by design — C2's StartingPointCard is its consumer per the plan's C1/C2 scope split; this is documented intent, not a stub (tsc `noUnusedLocals` is off so no error).

## Self-Check: PASSED
- Created files present: runInput.ts, runInput.test.ts, api.getRunArtifacts.test.ts, useWorkflow.clarifyRetention.test.ts — all FOUND.
- Commits present: 1360f1ab, 4a9ba122, def5e2f4 — all FOUND.
