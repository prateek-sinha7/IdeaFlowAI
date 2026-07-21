---
phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-
plan: 08
subsystem: frontend-run-screen
tags: [run-screen, gate, fidelity, artifactPreview, INV-12, SC-001]
requires:
  - "42-05 artifactPreview (discriminateArtifact + Tasks/Spec/AnalysisPreview)"
provides:
  - "2-button review gate ('Approve & build' / 'Request changes') + reused plan preview"
affects:
  - frontend/src/components/chat/InlineGateActions.tsx
tech-stack:
  added: []
  patterns:
    - "Collapse secondary gate actions under a single expandable affordance while preserving every underlying channel"
    - "Reuse the shared artifactPreview discriminator/renderers for a second consumer (no re-parse, INV-12)"
key-files:
  created: []
  modified:
    - frontend/src/components/chat/InlineGateActions.tsx
    - frontend/src/components/chat/InlineGateActions.test.tsx
    - frontend/src/components/results/__tests__/StepsDrilldown.test.tsx
decisions:
  - "Kept the internal shield header + Edit affordance (approve-with-edits / KAN-98 channel is orthogonal to the redo/update-specs/reject collapse)"
  - "Plan preview keys on discriminateArtifact(output) with no artifactKind (GateContext carries none) — content-tag sniff, SC-001 generic"
  - "Preview hidden while the Edit textarea is open to avoid a duplicated content surface"
metrics:
  duration: ~20m
  completed: 2026-07-15
---

# Phase 42 Plan 08: Review Gate — 2 Buttons + Task-Plan Preview Summary

Collapsed the review gate from 4–5 controls to the mock's **two primary buttons** ("Approve & build" / "Request changes") plus a **task-plan preview** block that reuses the shared `artifactPreview` module — with every underlying redo / update-specs / reject channel preserved under "Request changes".

## What changed

- **`InlineGateActions.tsx`** restructured to the mock (`Hexaware Run - Live.dc.html:269-278`, detail `:482-491`):
  - Two primary buttons in a flex row: **"Approve & build"** (`data-testid="chat-gate-approve"` → `handleApprove` → `approve_review approved:true`; honors `approveLabel`, shows "Approve with edits & build" when `hasEdits`) and **"Request changes"** (`data-testid="chat-gate-request-changes"`, toggles an expandable panel).
  - The **redo / update-specs / reject** sub-controls now live inside the "Request changes" panel, each wired to its **exact existing handler** (`handleRedo` / `handleUpdateSpecs` / `handleReject`) with the same `canRedo` / `canUpdateSpecs` gating and the KAN-95 two-step reject confirm — presentation-only restructure, **no channel dropped**.
  - New **plan-preview block** (`data-testid="chat-gate-preview"`) rendering `discriminateArtifact(output)` → `TasksPreview` / `SpecPreview` / `AnalysisPreview` imported from `@/components/results/artifactPreview` (INV-12: no second parser). Hidden while the Edit textarea is open.
  - Kept the internal shield header, the "Edit" affordance, KAN-98 retained-edit, KAN-100 terminal fence, and the one-action `submitted` latch.
- **Tests reconciled** (not deleted) to the 2-button structure: `InlineGateActions.test.tsx` (now asserts two primary buttons + that "Request changes" reveals the three channels + that the preview renders via artifactPreview) and `StepsDrilldown.test.tsx` (the two Update-the-Specs gate tests now open "Request changes" first).

## Commits

| Hash | Message |
|------|---------|
| `5e5efd48` | feat(42-08): collapse review gate to 2 buttons + reused plan preview |

## Verification

- **`npx tsc --noEmit`** — clean (0 `error TS`, excluding the pre-existing `mockApi` filter).
- **`npx vitest run` (full suite)** — **8 failed / 681 passed**; the failure set is EXACTLY the documented pre-existing baseline (`PreviewPanel.switcher`×3, `PreviewPanel.degraded`×1, `HomeLaunchGrid.inspect`×2, `FilesTab.runInput`×2). **Zero net-new failures.** The one net-new failure introduced mid-work (`StepsDrilldown` update-specs) was reconciled, not suppressed.
- **`npx vitest run InlineGateActions`** — 14/14 green (approve fires `approve_review approved:true`; redo/update-specs/reject reachable under "Request changes"; preview renders via artifactPreview).
- **Fidelity harness** (`FIDELITY_CAPTURE=1 playwright zzz-baseline`, from `frontend/`) — **8/8 passed** (gate-awaiting captures + the settled/live flows that approve via the preserved `chat-gate-approve` testid).
- **Acceptance greps** on `InlineGateActions.tsx`: two-buttons=8 (≥2), channels=6 (≥3), artifactPreview-reuse=8 (≥1), SC-001 workflow-name literal=0.

## Confirmations

- The gate now shows **exactly two primary buttons** ("Approve & build" / "Request changes") plus a **task-plan preview** rendered through the reused `artifactPreview` module.
- The **redo / update-specs / reject channels are preserved** — collapsed under "Request changes", each still firing its original handler over the unchanged `approve_review {approved, action}` channel. Approve still fires the approve path.
- The plan preview **reuses** `discriminateArtifact` + `Tasks/Spec/AnalysisPreview` (no second parser, INV-12).
- **SC-001** honored: preview discrimination keys only on the output's wrapper tag; no workflow/agent-name literal added.

## Deviations from Plan

None — plan executed as written. The plan's acceptance criteria referenced `npx vitest run InlineGateActions`; the sibling `StepsDrilldown.test.tsx` also exercises the gate through `AgentThinkingTab` → `InlineGateActions`, so its two Update-the-Specs assertions were reconciled to open "Request changes" first (Rule 1 — a test broken by the intended restructure, updated to match, not deleted).

## Self-Check: PASSED

- `frontend/src/components/chat/InlineGateActions.tsx` — FOUND (modified)
- Commit `5e5efd48` — FOUND on `feat/ui-2`
