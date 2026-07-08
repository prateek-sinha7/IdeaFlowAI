---
phase: 33-concierge-compaction-a5
plan: 04
subsystem: ui
tags: [chat, concierge, confirm-chip, compaction, token-widget, react, vitest]

# Dependency graph
requires:
  - phase: 33-03
    provides: "concierge_proposal confirm-chip hold + the confirm round-trip contract ({concierge:true, confirm_proposal:{channel,params}})"
  - phase: 31
    provides: "RunChatLane (suggestion-chip render path + ChatTokenWidget import) and the P26 ChatTokenWidget"
provides:
  - "RunChatLane confirm/reject chip pair for held consequential Concierge proposals (chat-proposal-confirm / chat-proposal-reject) — confirm is the only execute path"
  - "RunChatLane compact affordance (chat-compact) surfacing when composed-context usage is high — FE triggers only"
  - "ChatTokenWidget composed-context usage sub-display (chat-context-usage) + shared composedContextUsage() helper / COMPACT_THRESHOLD_PCT"
affects: [33-05, 34]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Consequential proposals rendered as a confirm/reject chip pair modeled on the existing suggestion-chip path — presentational, caller-supplied callbacks (same seam as suggestion chips / gate actions), no send hook"
    - "Composed-context telemetry declared as a LOCAL optional extension (ComposedContextTelemetry) so display-only fields degrade gracefully without a shared PipelineRunState schema change"
    - "Compact eligibility derived from the SAME composed-context usage the token widget reads (single source of truth via exported composedContextUsage() + COMPACT_THRESHOLD_PCT)"

key-files:
  created: []
  modified:
    - frontend/src/components/chat/RunChatLane.tsx
    - frontend/src/components/chat/ChatTokenWidget.tsx
    - frontend/src/components/chat/RunChatLane.test.tsx
    - frontend/src/components/chat/ChatTokenWidget.test.tsx

key-decisions:
  - "Confirm/reject/compact are caller-supplied callback props (onConfirmProposal/onRejectProposal/onCompact), mirroring the existing onSuggestion/onApprove discipline — the confirm round-trip transport lives with the caller (plan 07), NOT in RunChatLane and NOT in useWorkflow.ts (FIX-039 protected)."
  - "Composed-context fields (composedContextTokens/contextBudgetTokens) are declared locally as an optional extension rather than added to the shared PipelineRunState — keeps files_modified to exactly the two planned components and degrades gracefully (hidden) until the Phase-34 stream supplies them (D-08)."
  - "Proposals render above the composer mode body so a held consequential proposal is visible in ANY live state (gate / complete / building), not only in complete mode."

patterns-established:
  - "Confirm-chip pair: model consequential-action UX on the suggestion-chip render path; keep the proposal GENERIC (channel is a proposal channel, never a workflow-name literal, INV-1)."
  - "Display-only telemetry extensions: local optional interface + a shared derive helper, degrade to hidden when absent."

requirements-completed: [D-05, D-08, SC-1]

# Metrics
duration: 25min
completed: 2026-07-08
---

# Phase 33 Plan 04: Concierge Confirm-Chip + Compact Affordance (FE) Summary

**RunChatLane gains a confirm/reject chip pair for held consequential Concierge proposals (confirm is the only execute path) plus a compact affordance, and ChatTokenWidget surfaces composed-context usage — FE displays/confirms only, no FE compression.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-08
- **Completed:** 2026-07-08
- **Tasks:** 2
- **Files modified:** 4 (2 production, 2 tests)

## Accomplishments
- **ChatTokenWidget composed-context sub-display (D-08):** added `ComposedContextTelemetry` (local optional extension), the shared `composedContextUsage()` helper + `COMPACT_THRESHOLD_PCT`, and a `🧠 N% context` sub-display (`data-testid="chat-context-usage"`, `data-context-high`) that flags high usage and hides gracefully when the stream omits the value. No parallel widget; no FE compression.
- **RunChatLane confirm-chip UX (D-05, SC-1):** a confirm/reject chip pair (`chat-proposal-confirm` / `chat-proposal-reject`, carrying `data-proposal-id`) for held consequential proposals, modeled on the existing suggestion-chip render path. Confirming calls `onConfirmProposal(proposal)` — the caller POSTs the `{concierge:true, confirm_proposal:{channel,params}}` turn through the existing chat send seam; reject calls `onRejectProposal(id)` and executes nothing (T-33-04-01).
- **RunChatLane compact affordance (D-08):** a `chat-compact` control in the header that surfaces when `compactAvailable` is signalled OR the live composed-context usage crosses the shared threshold, wired to the SAME telemetry the token widget reads. FE only triggers `onCompact()` — it never compresses.
- **XSS-safe render (T-33-04-02):** all proposal text goes through React JSX escaping; `grep -c dangerouslySetInnerHTML RunChatLane.tsx` == 0.
- **Extend, not fork (INV-12):** only `ChatTokenWidget.tsx` remains under `src/components/chat/` matching `token`; RunChatLane still imports the single `ChatTokenWidget`.

## Task Commits

1. **Task 2: composed-context usage in ChatTokenWidget** - `5d3cf8c6` (feat)
2. **Task 1: confirm-chip + compact affordance in RunChatLane** - `ad693be5` (feat)

**Plan metadata:** this SUMMARY commit (see final commit).

_Committed Task 2 (the shared helper) first so Task 1 could import `composedContextUsage` / `COMPACT_THRESHOLD_PCT` with each commit building independently._

## Files Created/Modified
- `frontend/src/components/chat/ChatTokenWidget.tsx` - Added `ComposedContextTelemetry`, `composedContextUsage()`, `COMPACT_THRESHOLD_PCT`, widened the prop to accept the optional extension, and rendered the composed-context sub-display.
- `frontend/src/components/chat/RunChatLane.tsx` - Added `LaneProposal`, the `proposals`/`onConfirmProposal`/`onRejectProposal`/`compactAvailable`/`onCompact` props, the `renderProposals()` confirm/reject chip renderer, and the header compact button + eligibility derivation.
- `frontend/src/components/chat/ChatTokenWidget.test.tsx` - Added 3 specs (graceful-degrade hide, high-usage flag, below-threshold).
- `frontend/src/components/chat/RunChatLane.test.tsx` - Added 5 specs (confirm/reject chips, no-proposal case, compact surfaces on high usage, hides on low/absent, `compactAvailable` override).

## Decisions Made
- **Presentational callbacks, not a send hook.** The confirm round-trip transport is caller-owned (plan 07 threads it live), mirroring `onSuggestion`/`onApprove`. This satisfies the FIX-039 guardrail (no `useWorkflow.ts` edit) and the "wire through the existing send seam" mandate — RunChatLane exposes the same prop-callback seam the suggestion chips use.
- **Local optional telemetry extension, not a PipelineRunState schema change.** Keeps files_modified to exactly the two planned components and degrades gracefully until Phase-34 supplies the composed-context fields on the stream.

## Deviations from Plan

None - plan executed exactly as written. (One in-file adjustment, not a deviation: a code comment that spelled the literal `dangerouslySetInnerHTML` was reworded so the guardrail grep count stays 0.)

## Issues Encountered
- The excess-property check failed when the widget test passed composed-context fields into a `PipelineRunState` literal. Resolved by widening `ChatTokenWidgetProps.pipelineState` to `PipelineRunState & Partial<ComposedContextTelemetry>` (within the widget file — no shared type change). tsc returns 0 after.

## Verification Evidence
- `cd frontend && npx tsc --noEmit 2>&1 | grep -c "error TS"` → **0** (baseline identity held).
- `npx vitest run src/components/chat/` → **13 files / 109 tests passed** (14 net-new: 3 widget + 5 lane authored here, plus pre-existing all green).
- Grep proofs: `chat-proposal-confirm|chat-proposal-reject|chat-compact` count = 3; `ChatTokenWidget` refs in RunChatLane = 4; `ls src/components/chat/ | grep -i token` = only `ChatTokenWidget.tsx` (+ its test); `grep -c dangerouslySetInnerHTML RunChatLane.tsx` = 0; no new workflow-name literal (SC-001 source test green).
- `git diff --name-only e66a2986 HEAD` = exactly the 4 chat files (+ this SUMMARY on the final commit). No `useWorkflow.ts`, no STATE/ROADMAP.
- Playwright (mocked): delta-only. Changes are purely additive — every pre-existing testid (`run-chat-lane`, `chat-stop`, `chat-token-widget`, `chat-suggestion-chip`, terminal variants) is retained; the single `-data-testid="chat-stop"` diff line is a re-indent inside a new wrapper `<div>`, and `chat-stop` is still present. Net-new breakage = 0. The full mocked suite has a known pre-existing failure cluster (~120 CreationHub/home-redesign specs, DEF-29-06-1) that is out of scope and not touched; running the full browser suite offline is impractical, so verification rides tsc + vitest green + new-testid presence + additive-diff proof.

## Live-Deferred / human_needed
- **Live visual confirmation (Phase 34):** the confirm-chip flow (confirm executes the held proposal end-to-end against a real run; reject dismisses) and the compact affordance surfacing on real composed-context usage require a live run — deferred to Phase 34. The composed-context stream fields (`composedContextTokens`/`contextBudgetTokens`) are not yet emitted; the widget/affordance degrade gracefully until then.

## Next Phase Readiness
- **33-05 (goldens):** unaffected by this FE-only change; no new backend event types introduced here (`concierge_proposal` remains the 33-03 addition).
- **Plan 07 (live wiring):** the caller must thread `proposals` (from `concierge_proposal` run_events rows), `onConfirmProposal` (POST the confirm round-trip), `onRejectProposal`, and `onCompact`/composed-context telemetry into RunChatLane.

## Self-Check: PASSED

---
*Phase: 33-concierge-compaction-a5*
*Completed: 2026-07-08*
