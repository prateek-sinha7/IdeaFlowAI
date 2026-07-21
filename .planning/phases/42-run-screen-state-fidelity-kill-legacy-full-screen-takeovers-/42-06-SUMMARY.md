---
phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-
plan: 06
subsystem: run-screen-frontend
tags: [run-ui, steps, clarify, mock-fidelity, sc-001]
requires:
  - 42-02 (Cancel-Workflow re-home into InlineClarifyActions)
provides:
  - Steps-overview phase pill + label (CLARIFY/REVIEW/BUILDING) keyed on generic run state
  - Violet running-row highlight + node glow on the Steps spine (Zap badge dropped)
  - Single-submit clarify ("Submit answers & start the build") with mock-omitted affordances removed
affects:
  - frontend/src/components/results/StepsOverviewSpine.tsx
  - frontend/src/components/chat/InlineClarifyActions.tsx
tech-stack:
  added: []
  patterns:
    - Generic-state → phase-pill derivation (no workflow-name literal, SC-001)
    - Mock brand tokens via existing brand-fill/brand/brand-border Tailwind classes
key-files:
  created: []
  modified:
    - frontend/src/components/results/StepsOverviewSpine.tsx
    - frontend/src/components/chat/InlineClarifyActions.tsx
    - frontend/src/components/chat/InlineClarifyActions.test.tsx
decisions:
  - "onSkipClarify upstream plumbing (DashboardLayout→PreviewPanel→AgentThinkingTab) left intact; only the onSkipAll boundary + its StepsOverviewSpine mount wiring removed, per the plan's 'only the skip-all wiring' narrowing. handleQuestionnaireSkip still serves RunChatLane."
metrics:
  duration: ~15m
  completed: 2026-07-15
---

# Phase 42 Plan 06: Steps header phase pill/label + violet running-row + clarify single-submit Summary

Added the Live-mock's Steps-overview phase pill + label and violet running-row highlight (SC-001, generic state only), and collapsed the inline clarify to a single "Submit answers & start the build" — removing the per-question skip, recommended-answer fill/badge, freeform block, and skip-all — while preserving the submit_questionnaire channel and the re-homed Cancel-Workflow affordance.

## What Was Built

### Task 1 — Steps overview phase pill + label + violet running-row (`StepsOverviewSpine.tsx`)
- Derived a `phase` object from the generic run signals (`clarifyQuestions`/`laneGate`/`isRunning`) — no workflow-name literal:
  - clarify awaiting → pill **CLARIFY**, label "Waiting on your answers"
  - active review gate → pill **REVIEW**, label "Paused for your approval"
  - running (no clarify/gate) → pill **BUILDING**, label "Pipeline running · N / M" with live `completedCount`/`total`
  - failed/complete keep the plain `statusLabel`.
- Pill styled with the mock brand tokens (`text-brand bg-brand-fill border border-brand-border`, accent #3C2CDA), with a pulsing dot only in the BUILDING (live) state.
- Running spine row now uses the mock violet highlight `bg-[#F4F2FB] border-[#DED9F7]` + node glow `shadow-[0_0_0_4px_rgba(60,44,218,0.15)]`; the Zap "Live" text badge is removed from the overview spine (the L2 detail LIVE pill is untouched).
- Removed the now-unused `Zap` import; unwired the removed `onSkipAll` from the InlineClarifyActions mount.

### Task 2 — Clarify submit copy + drop extra affordances (`InlineClarifyActions.tsx`)
- Submit copy "Send answers" → **"Submit answers & start the build"** (Live mock :229).
- Removed the mock-omitted affordances: per-question Skip toggle, "Use recommended" button, "Rec." badge, "Anything else?" freeform block, and "Skip all" (plus the `onSkipAll` prop, `skipped`/`freeform` state, and `useRecommended`/`skipQuestion`/`recommendedFor` helpers and their now-unused icon imports).
- Preserved the core answer flow (render questions → collect answers → single submit firing the unchanged `onSubmitAnswers` / submit_questionnaire channel) and the re-homed Cancel-Workflow affordance.
- Updated the test file: dropped the recommended/skip/freeform assertions; added assertions for the new submit copy and the absence of every removed affordance.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Acceptance grep tripped by an explanatory comment**
- **Found during:** Task 2 verification
- **Issue:** The docstring naming the removed affordances ("Use recommended" / "Rec." / "Skip all" / "Anything else?") tripped the `grep -Ec "Use recommended|Anything else|Skip all|Rec\."` == 0 acceptance check.
- **Fix:** Reworded the comment to describe the removals without the literal phrases; grep now returns 0.
- **Files modified:** frontend/src/components/chat/InlineClarifyActions.tsx
- **Commit:** 9b5cae2e

**Scoping note (not a deviation):** Per the plan's "only the skip-all wiring, not the cancel wiring", the removal is bounded to the `onSkipAll` prop on `InlineClarifyActions` and its `StepsOverviewSpine` mount wiring. The upstream optional `onSkipClarify` passthrough (DashboardLayout → PreviewPanel → AgentThinkingTab) is left intact because the same `handleQuestionnaireSkip` handler still serves RunChatLane; tsconfig has no `noUnusedLocals`, so the untouched passthrough compiles clean and introduces no tsc/vitest regression.

## Verification

- `npx tsc --noEmit` — **0 errors** (excluding pre-existing mockApi noise).
- `npx vitest run` — **8 failed | 679 passed**; the failing set is EXACTLY the pre-existing baseline (PreviewPanel.switcher×3, PreviewPanel.degraded×1, HomeLaunchGrid.inspect×2, FilesTab.runInput×2). **Zero net-new failures.**
- `npx vitest run StepsDrilldown` — 8/8 green.
- `npx vitest run InlineClarifyActions` — 10/10 green.
- Acceptance greps: phase pill present (5), running-row highlight (1), no name literal (0), no Zap (0); submit copy (1), extras removed (0), cancel preserved (4), onSkipAll gone (0).
- Fidelity harness `FIDELITY_CAPTURE=1 npx playwright test zzz-baseline` — **8/8 passed**. Per-state screenshot human-check deferred to 42-11.
- Backend pytest NOT run (out of scope, per constraints).

## Confirmation of Intent
- Phase pill + label landed on the Steps overview header, keyed on generic state (SC-001).
- Violet running-row highlight + node glow landed; Zap badge dropped from the overview spine; L2 detail LIVE pill unchanged.
- Clarify submit reads "Submit answers & start the build".
- The five extra clarify affordances are removed; the submit_questionnaire channel and the Cancel-Workflow affordance are intact.
- KEEP items (§4) — highlight ring, "Awaiting you" badge, "Review gate — approved" strip — untouched.

## Self-Check: PASSED
- Files: StepsOverviewSpine.tsx, InlineClarifyActions.tsx, 42-06-SUMMARY.md — all present.
- Commits: 35a97705, 9b5cae2e — both in history.
