---
phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto
plan: 02
subsystem: ui
tags: [react, vitest, run-chat, revision, confirm-chip, sse]

# Dependency graph
requires:
  - phase: 43-02
    provides: "the generic settled-run ask-vs-change classifier (classifyFreeText) + Concierge routing"
  - phase: 33-03
    provides: "the confirm-chip render path (LaneProposal Card + confirm/reject buttons)"
provides:
  - "A confirm-first refinement chip: a settled-run CHANGE request is held behind a 'Run a refinement with this change?' chip; onRevise fires only on explicit confirm"
  - "Regression-locking vitest coverage for the confirm-gate (confirm launches once / dismiss launches nothing / ask stays Concierge / no-onRevise fallback)"
affects: [44-03, 44-04, w4-de-flag, run-revision-retirement]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Held-refinement-as-local-proposal: a settled-run change is parked in local state and rendered via the existing proposal-chip Card+confirm pattern, gating the consequential launch behind explicit user intent"

key-files:
  created: []
  modified:
    - frontend/src/components/chat/RunChatLane.tsx
    - frontend/src/components/chat/RunChatLane.test.tsx

key-decisions:
  - "Reused the proposal-chip Card+confirm pattern rather than inventing a component — a held refinement is structurally a local proposal (per plan)"
  - "Kept the terminal-lane handleTerminalRevise path unchanged (only the settled-run change branch is confirm-gated)"

patterns-established:
  - "Consequential settled-run launches (revisions) are confirm-gated, not auto-fired — removes the accidental auto-launch surface (T-44-02-01)"

requirements-completed: [W3, "SC-001", "INV-1"]

# Metrics
duration: 15 min
completed: 2026-07-15
---

# Phase 44 Plan 02: Confirm-First Refinement Chip Summary

**A settled-run change request in the chat lane now surfaces a "Run a refinement with this change?" confirm chip; the `*_revision` run launches only after the user confirms — replacing today's auto-launch at `handleFreeText → onRevise`.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-15T17:48:00Z
- **Completed:** 2026-07-15T18:03:12Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `handleFreeText` on a settled run (`runState === "complete"`) now parks a CHANGE request in local `heldRefinement` state instead of calling `onRevise(text)` immediately.
- A confirm chip ("Run a refinement with this change?") renders above the settled composer, reusing the existing proposal-chip Card+confirm pattern; Confirm launches `onRevise` exactly once, Dismiss clears the hold and launches nothing.
- ASK turns are untouched — still routed to the Concierge via `sendMessage(text, attachments, { concierge: true })` with no chip.
- The classifier + chip stay GENERIC (no workflow-name/agent-id literal) — SC-001/INV-1 preserved and grep-asserted.
- Behavior regression-locked by 5 new vitest cases plus an updated settled-route matrix.

## Task Commits

1. **Task 1: Hold settled-run change requests behind a confirm chip** - `9b313a02` (feat)
2. **Task 2: Cover the confirm-gate behavior in the mocked lane test** - `04732d61` (test)

**Plan metadata:** (docs commit — this SUMMARY)

## Files Created/Modified
- `frontend/src/components/chat/RunChatLane.tsx` - Added `heldRefinement` state + `confirmRefinement`/`dismissRefinement` handlers; `handleFreeText` change branch now sets the hold instead of calling `onRevise`; added `renderHeldRefinement()` (confirm chip) wired into the composer above `renderComposerBody()`.
- `frontend/src/components/chat/RunChatLane.test.tsx` - Replaced the old immediate-`onRevise` test with the confirm-gate matrix; updated the settled-route change branch to assert the held chip.

## Decisions Made
- Reused the proposal-chip Card+confirm render pattern (distinct testids `chat-refinement-chip` / `chat-refinement-confirm` / `chat-refinement-dismiss`) rather than adding a new component — a held refinement is structurally a local proposal, per the plan.
- Preserved both existing fallbacks: a settled change with no `onRevise` prop falls back to a plain `sendMessage`; the terminal-lane `handleTerminalRevise` path is unchanged.

## Deviations from Plan

None - plan executed exactly as written.

## Verification

- `cd frontend && npx tsc --noEmit` → clean (exit 0).
- `cd frontend && npx vitest run src/components/chat/RunChatLane.test.tsx` → 36/36 pass, including:
  - change → chip → confirm → `onRevise` (exactly once)
  - change → chip → dismiss → no launch
  - change with no `onRevise` → plain `sendMessage` fallback (no chip)
  - ask → Concierge unchanged, no chip
- `cd frontend && npx vitest run src/components/chat` → 14 files / 146 tests pass (no sibling regression).
- INV-1 grep-assert: `grep -nEi '"prototype"|od_ppt|od_prototype|app_builder|user_stories|ppt_revision' RunChatLane.tsx` → NONE. The in-source SC-001 test (`/"prototype"|od_ppt|app_builder|user_stories/`) still green.
- AC1 grep: `onRevise(` appears only in `confirmRefinement` (the confirm handler) and the unchanged `handleTerminalRevise` — never in `handleFreeText`'s change branch.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- W3a (confirm-first refinement UX) is complete and file-disjoint from the pipeline/command rewire (W1/W2/W3b). The Strategy-A `run_revision` retirement (rewiring `handleRevisePpt` to REST `/revisions` + deletions) remains for the other wave-1/W3 plans.

## Self-Check: PASSED
- `frontend/src/components/chat/RunChatLane.tsx` modified — verified on disk.
- `frontend/src/components/chat/RunChatLane.test.tsx` modified — verified on disk.
- Commits `9b313a02` (feat) and `04732d61` (test) present in `git log`.

---
*Phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto*
*Completed: 2026-07-15*
