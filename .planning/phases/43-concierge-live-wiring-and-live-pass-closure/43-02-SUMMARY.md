---
phase: 43-concierge-live-wiring-and-live-pass-closure
plan: 02
subsystem: ui
tags: [concierge, chat, run-lane, sendMessage, classifier, sse-dark, react, vitest]

# Dependency graph
requires:
  - phase: 43-concierge-live-wiring-and-live-pass-closure
    provides: "43-01 backend: POST {concierge:true} handling, durable-row confirm_proposal disposal (H1), drain_proposals — the wire contract this FE targets"
  - phase: 31-chat-backbone
    provides: "useRunChat transport-agnostic transcript hook + RunChatLane composition root + the RunChatLaneProps Concierge slots (proposals/onConfirmProposal/onRejectProposal/onCompact/compactAvailable)"
provides:
  - "SendMessageOptions type + the extended useRunChat.sendMessage(text, attachments?, options?) contract folding concierge/confirm_proposal onto the POST /messages payload (dormant when absent, INV-3)"
  - "A GENERIC ask-vs-change classifier (classifyFreeText) in RunChatLane.handleFreeText: a settled-run ASK is answered by the Concierge ({concierge:true}); a CHANGE REQUEST still launches the revision pipeline (onRevise). Change-intent weighed FIRST so a question-SHAPED change ('can you make the button bigger?') routes as a change"
  - "Concierge props wired at the DashboardLayout RunChatLane mount: proposals + onConfirmProposal (POST {concierge:true, confirm_proposal:{channel,params}}) + onRejectProposal + onCompact + compactAvailable via the options-capable runChatSend seam"
affects: [part-c-sse-cutover, concierge-live-qa-B3, 43-06-transport-cutover]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Optional trailing typed options on a transport-agnostic send seam (SendMessageOptions) — dormant/byte-identical payload when omitted (INV-3)"
    - "Generic text-only intent classifier keyed on the free text + runState, never a workflow-name/agent-id literal (SC-001/INV-1); change-intent weighed before question-shape to defeat the question-shaped-change trap"
    - "Presentational lane + caller-owned transport: RunChatLane calls onConfirmProposal(p); DashboardLayout constructs the confirm POST — same pattern as suggestion chips / gate actions"

key-files:
  created: []
  modified:
    - "frontend/src/hooks/useRunChat.ts"
    - "frontend/src/hooks/useRunChat.test.ts"
    - "frontend/src/components/chat/RunChatLane.tsx"
    - "frontend/src/components/chat/RunChatLane.test.tsx"
    - "frontend/src/components/layout/DashboardLayout.tsx"

key-decisions:
  - "The ask-vs-change classifier weighs change-intent verbs FIRST, then question-shape — a bare question-mark heuristic misroutes the trap 'can you make the button bigger?'; change-intent ('make') wins"
  - "Ambiguous settled-run free text falls through to the historical default (a revision/onRevise) — misclassification is bounded because the consequential path stays confirm-gated server-side (43-01 H1, T-43-02-ROUTE=accept)"
  - "The send seam is a single options-capable runChatSend wrapper (onRunChatSend else onSendMessage) so the lane's ASK send and the confirm round-trip share one path; the confirm carries the proposal's channel+params verbatim (the backend H1 fence disposes from its OWN durable row, never this client body)"
  - "LOCK-B honored: NEXT_PUBLIC_SSE_TRANSPORT stays OFF and RunConnectionProvider stays unmounted — this plan proves the routing DECISION + payload shape offline (unit tests), not a live round-trip; the transport flip is Part C (43-06)"

patterns-established:
  - "Generic intent classification (ask vs change) for a settled-run chat turn, INV-1-safe (no workflow-name literal), verified by a ≥5-case matrix incl. the question-shaped-change trap"
  - "Options-capable send contract that is dormant/unchanged when the options are absent"

requirements-completed: [A.1]

# Metrics
duration: 20min
completed: 2026-07-15
---

# Phase 43 Plan 02: Concierge FE Composer Re-routing (the A.1 CRUX) Summary

**A settled-run free-text turn is now CLASSIFIED offline: an ASK ("what's the status?") is answered by the Concierge via `sendMessage(..., { concierge: true })`, while a CHANGE REQUEST ("make it dark mode") still launches the revision pipeline (onRevise) — a generic, INV-1-safe classifier plus the Concierge props wired at the RunChatLane mount and an options-capable send contract, all tsc-clean with the SSE transport left dark (LOCK-B).**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-15
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- **Send contract (Task 1)** — `useRunChat.sendMessage` gained an optional trailing `SendMessageOptions` (`concierge?`, `confirm_proposal?: {channel, params}`). When present the fields fold onto the `POST /messages` payload with names matching the backend `MessageCommand` EXACTLY (`concierge` / `confirm_proposal`); when absent the payload is byte-identical to the pre-43-02 shape (dormant, INV-3). The legacy WS branch still emits `user_message` (the fields ride the payload but do not reach the Concierge until the Part-C SSE cutover — expected).
- **The CRUX (Task 2)** — `RunChatLane.handleFreeText` no longer treats every settled-run turn as a revision trigger. On a `complete` run it classifies the text: an ASK → `sendMessage(text, attachments, { concierge: true })`; a CHANGE REQUEST → `onRevise(text)` (unchanged). The classifier (`classifyFreeText`) keys ONLY on generic text — no workflow-name/agent-id literal (SC-001/INV-1) — and weighs change-intent verbs BEFORE question-shape so the trap "can you make the button bigger?" routes as a CHANGE.
- **Mount wiring (Task 2)** — the DashboardLayout RunChatLane mount now attaches `proposals`, `onConfirmProposal` (POSTs `{concierge:true, confirm_proposal:{channel,params}}` through the shared `runChatSend` seam), `onRejectProposal`, `onCompact`, and `compactAvailable`. The send seam became a single options-capable `runChatSend` wrapper so the lane's ASK send and the confirm round-trip share one path.

## Task Commits

Each task was committed atomically (no trailer, per feat/ui-2 policy):

1. **Task 1: extend the useRunChat send contract (concierge/confirm_proposal options)** — `436ea1eb` (feat)
2. **Task 2: re-route settled-run free text to Concierge + attach mount props** — `7cf574d1` (feat)

**Plan metadata:** this SUMMARY commit (docs).

## Files Created/Modified
- `frontend/src/hooks/useRunChat.ts` — exported `SendMessageOptions`; `sendMessage` accepts an optional third `options` arg and folds `concierge` / `confirm_proposal` onto the payload only when present; `UseRunChatReturn.sendMessage` type widened.
- `frontend/src/hooks/useRunChat.test.ts` — Tests 9/10/11: concierge-flag fold, exact confirm_proposal fold, and the dormant no-options case (no `concierge` key).
- `frontend/src/components/chat/RunChatLane.tsx` — `classifyFreeText` generic ask-vs-change classifier; `handleFreeText` re-routed on a settled run; `sendMessage` prop signature widened to carry options; `SendMessageOptions` imported.
- `frontend/src/components/chat/RunChatLane.test.tsx` — the ≥5-case settled-run routing matrix (incl. the question-shaped-change trap), driven off a data table.
- `frontend/src/components/layout/DashboardLayout.tsx` — `runChatSend` options-capable send seam; `handleConfirmProposal` / `handleRejectProposal` / `handleCompact`; `RUN_CONCIERGE_PROPOSALS` stable empty holds list; `onRunChatSend` prop type widened; the five Concierge props attached at the mount.

## Decisions Made
- Change-intent is weighed BEFORE question-shape in the classifier (defeats the trap; a bare `?` heuristic would misroute "can you make the button bigger?").
- Ambiguous settled free text defaults to a revision (historical behavior); the consequential path stays confirm-gated server-side (43-01 H1), so a misclassification is bounded (T-43-02-ROUTE=accept).
- One shared `runChatSend` seam for both the ASK send and the confirm round-trip; the confirm carries the proposal's channel+params verbatim (the backend fence disposes from its durable row, never the client body).
- LOCK-B honored — SSE flag OFF, `RunConnectionProvider` unmounted; the routing decision is proven offline by unit tests.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs
- `frontend/src/components/layout/DashboardLayout.tsx` — `RUN_CONCIERGE_PROPOSALS` is a stable EMPTY held-proposal list, and `handleRejectProposal` / `handleCompact` are documented no-ops. **Intentional and sequenced:** `concierge_proposal` holds arrive on the transcript only once the Part-C SSE transport (43-06) is live (LOCK-B keeps it dark this plan); wiring the confirm chip + the send seam NOW makes that flip a data change, not a re-wire. `compactAvailable={false}` reflects the absence of a backend compaction trigger (no invented call). No stub blocks A.1's goal — the ask-vs-change re-route (the CRUX) is fully live-offline and unit-proven.

## Issues Encountered
- One transient `tsc` error in `useRunChat.test.ts` (tuple-index typing on the shared zero-arg `sendCommand` mock in Test 11). Fixed by casting the recorded call to `unknown[]` before indexing. tsc clean thereafter.

## User Setup Required
None - no external service configuration required. (Live Concierge Q&A — B.3 — is verified DURING the supervised Part-C SSE cutover per the A.0 decision, not in this offline plan.)

## Next Phase Readiness
- The FE half of the A.1 CRUX is offline-correct: the ask-vs-change re-route + Concierge mount props + the extended send contract are wired and unit-proven; combined with 43-01 the whole A.1 CRUX is offline-complete.
- Nothing flips live here: `NEXT_PUBLIC_SSE_TRANSPORT` stays OFF; `RunConnectionProvider` unmounted. The live round-trip (concierge fields actually reaching the Concierge, the held-proposal surface, the compaction trigger) rides the Part-C SSE cutover (43-06) + B.3.

---
*Phase: 43-concierge-live-wiring-and-live-pass-closure*
*Completed: 2026-07-15*

## Self-Check: PASSED
- `frontend/src/hooks/useRunChat.ts`, `frontend/src/components/chat/RunChatLane.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` all FOUND (modified).
- Commits FOUND: `436ea1eb` (Task 1), `7cf574d1` (Task 2).
- `cd frontend && npx tsc --noEmit` → clean (0 errors). Touched vitest: useRunChat 11/11, RunChatLane suite 37/37 (incl. the 5-case routing matrix + the SC-001 source assertion), DashboardLayout 2/2.
- INV-1 grep: 0 workflow-name literals in `RunChatLane.tsx`. Mount grep: `proposals` / `onConfirmProposal` / `onRejectProposal` / `onCompact` / `compactAvailable` all present. LOCK-B: no `NEXT_PUBLIC_SSE_TRANSPORT` / `RunConnectionProvider` change. FE-only diff confirmed.
