---
phase: 31-chat-lane-mvp-a3
plan: 05
subsystem: ui
tags: [react, chat, quick-actions, gate, clarify, testids, sc-001]

# Dependency graph
requires:
  - phase: 31-chat-lane-mvp-a3 (plan 03)
    provides: useRunChat transcript reducer + ChatMessage contract the lane consumes
  - phase: 28-chat-contracts-guards-a0
    provides: LIVE-STATE-CONTRACT §1 (single approve_review / submit_questionnaire channel either way)
provides:
  - InlineGateActions — compact in-lane gate quick-actions (approve / reject-confirm / redo+instructions / update_specs) firing the shared approve_review channel
  - InlineClarifyActions — in-lane clarify quick-reply chips + option picker + freeform firing the shared submit_questionnaire channel
  - First data-testids on the chat gate/clarify surfaces (chat-gate-*, chat-clarify-*)
affects: [31-04 (mounts these into the lane), 32 (reskin — behavior stays), chat-lane]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Presentational callback-driven in-lane mirror: emits the SAME backend command the Steps panel does; no second command channel"
    - "Generic caller-supplied eligibility flag (updateSpecsEligible) drives an action instead of a workflow/agent-name literal (SC-001)"
    - "Source-level SC-001 assertion: a vitest reads its own component source and greps for banned workflow-name literals"

key-files:
  created:
    - frontend/src/components/chat/InlineGateActions.tsx
    - frontend/src/components/chat/InlineGateActions.test.tsx
    - frontend/src/components/chat/InlineClarifyActions.tsx
    - frontend/src/components/chat/InlineClarifyActions.test.tsx
  modified: []

key-decisions:
  - "InlineGateActions takes a generic updateSpecsEligible flag + optional approveLabel from the caller — no prototype-analyze/specify literal in new code (SC-001)"
  - "InlineClarifyActions emits the canonical [{question_id, answer}] shape directly (multi joined by ', ', freeform as question_id 'freeform') — identical to DashboardLayout.handleQuestionnaireSubmit's mapping"
  - "Reused the existing ClarifyQuestion type from QuestionnairePanel instead of minting a second question type (no dual type, INV-3 spirit)"
  - "KAN-98 retained edit modeled by resetting local edit state only on a fresh gate (new output/gateKey), so a no-echo re-render with the same output keeps the edit"

patterns-established:
  - "In-lane quick-action = standalone presentational component with the SAME callback props the full overlay receives (one backend channel either way)"
  - "One-action submit latch prevents double-send on both gate and clarify surfaces"

requirements-completed: [CHATUI-02]

# Metrics
duration: 5min
completed: 2026-07-08
---

# Phase 31 Plan 05: In-Lane Gate + Clarify Quick-Actions Summary

**In-lane gate quick-actions (approve / reject-confirm / redo+instructions / update_specs) and clarify chips + option picker that mirror the Steps panels through the SAME approve_review / submit_questionnaire channel — four gate actions, terminal fence, and retained edit, all SC-001-safe (no new workflow-name literal).**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-07-08T08:47:55Z
- **Completed:** 2026-07-08T08:52:54Z
- **Tasks:** 2
- **Files modified:** 4 (all created)

## Accomplishments
- `InlineGateActions` — compact chat-card gate surface rendering four actions when applicable: Approve (caller-relabelable to "Accept & continue to build"), Reject via a two-step confirm (KAN-95), Redo with free-text instructions, and "Update the Specs" (KAN-101). Fires the exact `onApprove/onReject/onRedo/onUpdateSpecs` callbacks the Steps `ReviewGatePanel` receives — one `approve_review` channel either way.
- KAN-100 terminal fence: `!isPipelineRunning` renders nothing. KAN-98 retained edit: an edit is kept in local state and survives a no-echo re-render (same output/gateKey), resetting only on a genuinely fresh gate.
- SC-001 safety: the fourth `update_specs` action is driven by a GENERIC caller-supplied `updateSpecsEligible` flag — no `prototype-analyze`/`prototype-specify`/workflow-name literal appears in either new file (grep = 0, plus a source-reading vitest assertion in each suite).
- `InlineClarifyActions` — in-lane clarify surface with single/multi quick-reply chips, "Use recommended", per-question skip, and a global freeform box; submits the canonical `[{question_id, answer}]` array (multi joined by `", "`, freeform as `question_id: "freeform"`) through the shared `submit_questionnaire` channel — identical to the Steps mapping.
- First `data-testid`s on the chat gate/clarify surfaces: `chat-gate-actions/approve/reject/redo/update-specs`, `chat-clarify-actions/chip/submit`.

## Task Commits

Each task was committed atomically:

1. **Task 1: InlineGateActions — 4 actions + terminal fence + retained edit (SC-001-safe)** - `c4745578` (feat)
2. **Task 2: InlineClarifyActions — quick-reply chips + option picker on the shared answer channel** - `46462181` (feat)

_Task 2's commit also carried a one-line tsc-identity fix to `InlineGateActions.test.tsx` (typed the props spread) — see Deviations._

## Files Created/Modified
- `frontend/src/components/chat/InlineGateActions.tsx` - Compact in-lane gate quick-actions mirroring ReviewGatePanel; four actions, terminal fence (KAN-100), retained edit (KAN-98), reject-confirm (KAN-95), generic update_specs flag (KAN-101/SC-001).
- `frontend/src/components/chat/InlineGateActions.test.tsx` - 12 specs: each action fires once with the right payload, reject-confirm, terminal fence renders nothing, updateSpecsEligible={false} hides only that action, redoable={false} hides redo, retained-edit-across-rerender, double-send latch, source-level SC-001 grep.
- `frontend/src/components/chat/InlineClarifyActions.tsx` - In-lane clarify chips + option picker + freeform; emits the canonical submit_questionnaire response array; reuses the ClarifyQuestion type.
- `frontend/src/components/chat/InlineClarifyActions.test.tsx` - 8 specs: chip+submit payload, Use recommended, multi-select accumulation, per-question skip omission, freeform append, empty-questions renders nothing, double-send latch, source-level SC-001 grep.

## Decisions Made
- Drove the `update_specs` affordance (and an optional `approveLabel`) off caller-supplied generic props rather than any agent-id comparison, so the new components add no SC-001 leak (the existing ReviewGatePanel `prototype-*` literals are generalized separately in Phase 32).
- Modeled the clarify callback as the canonical backend `[{question_id, answer}]` array (not the Steps panel's `(Record, freeform)` intermediate) because the plan pins this component to the `submit_questionnaire` channel shape; multi joined by `", "` and freeform as `question_id: "freeform"` matches the existing DashboardLayout mapping exactly.
- Reused `ClarifyQuestion` from `QuestionnairePanel` to avoid a second question type.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] tsc-identity regression from a `props as never` spread in the Task 1 test**
- **Found during:** Task 2 (tsc identity verification)
- **Issue:** The Task 1 test helper spread props via `{...(props as never)}`, which tsc rejected with TS2698 "Spread types may only be created from object types" — a NEW error violating tsc-identity.
- **Fix:** Typed the spread as `React.ComponentProps<typeof InlineGateActions>`.
- **Files modified:** frontend/src/components/chat/InlineGateActions.test.tsx
- **Verification:** `npx tsc --noEmit` shows zero errors outside the known `e2e/fixtures/mockApi.ts` baseline; 20/20 specs still green.
- **Committed in:** 46462181 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary to hold the tsc-identity gate. No scope creep — same components, same behavior.

## Issues Encountered
- The in-suite SC-001 assertion initially failed twice: (1) `import.meta.url` is not a file-scheme URL under this vitest runtime — switched to `join(process.cwd(), …)`; (2) the component's own docstring quoted the banned `prototype-analyze/specify` tokens, tripping the grep — reworded the comment to "workflow/agent-name literal". Both resolved before the Task 1 commit.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan 04 can mount `InlineGateActions` and `InlineClarifyActions` into the chat lane, wiring the existing gate/answer callbacks (the same ones the Steps panels already receive) — no new command channel needed.
- Behavior is current-skin; the Phase 32 reskin keeps behavior and restyles (D-15).
- No live-backend verification was attempted (offline-only phase, by design).

## Self-Check: PASSED

All four created files and both task commits (c4745578, 46462181) verified present on disk / in git history.

---
*Phase: 31-chat-lane-mvp-a3*
*Completed: 2026-07-08*
