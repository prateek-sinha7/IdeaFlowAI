---
phase: 31-chat-lane-mvp-a3
plan: 04
subsystem: ui
tags: [react, chat, composition-root, aria-live, deep-link, virtualization, sc-001, d-12]

# Dependency graph
requires:
  - phase: 31-chat-lane-mvp-a3 (plan 01)
    provides: "buildBlocks + ChatBlock/AgentEvent union — the agent-block render contract the lane dispatches on"
  - phase: 31-chat-lane-mvp-a3 (plan 02)
    provides: "renderToolBlock registry + useMeasuredVirtualWindow + ThinkingBlock/FileOpsSummary — the rendering mechanics"
  - phase: 31-chat-lane-mvp-a3 (plan 03)
    provides: "useRunChat transcript + ChatMessage extension + useTabDeepLink nonce'd seam (borrow #6)"
  - phase: 31-chat-lane-mvp-a3 (plan 05)
    provides: "InlineGateActions + InlineClarifyActions — the in-lane quick-actions"
  - phase: 31-chat-lane-mvp-a3 (plan 06)
    provides: "ChatAttachments + ChatTokenWidget + useChatAttachments (PendingAttachment)"
provides:
  - "RunChatLane — the run-screen left-column composition root: family-anchored transcript + narrator ResultCards + agent blocks + a D-12 mode-switched composer that absorbs the AgentProgressPanel controls (Stop/revise/suggestions)"
  - "ResultCard — narrator chat_reply card rendered by GENERIC cardKind (clarify/gate/pipeline/deliverable/spec_revision) with the nonce'd deep-link affordance (LOCK-F 'Deliverable', KAN-101 'Revising spec — cycle N')"
  - "Revived MessageBubble/ChatPanel: aria-live/role=log streaming transcript, plan-01 agent-block strip, plan-02 measured virtualizer (>80 msgs), react-markdown kept"
affects: [31-07-integration, chat-lane, 32-reskin]

# Tech tracking
tech-stack:
  added: []  # ZERO new deps — composes already-committed pieces + react-markdown/remark-gfm/lucide already in the kit
  patterns:
    - "Composition root pattern: RunChatLane owns NO transport/data logic — it wires the plan-01..06 pieces + the plan-03 data layer into one lane; plan 07 threads the live callbacks"
    - "D-12 composer-mode-per-state: a switch on the GENERIC runState selects the composer body (clarify/gate/building/complete/terminal/idle) — SC-001, never a workflow name"
    - "No dual composer: ChatPanel gains a hideComposer flag so the lane supplies its own unified, mode-switched composer instead of ChatInput"
    - "aria-live/role=log shipped on the transcript region from day one (the open-design documented a11y landmine, evidence 06 §7 — NOT repeated)"

key-files:
  created:
    - frontend/src/components/chat/ResultCard.tsx
    - frontend/src/components/chat/ResultCard.test.tsx
    - frontend/src/components/chat/RunChatLane.tsx
    - frontend/src/components/chat/RunChatLane.test.tsx
  modified:
    - frontend/src/components/chat/MessageBubble.tsx
    - frontend/src/components/chat/ChatPanel.tsx

key-decisions:
  - "ResultCard selects label + target tab from a SWITCH on the generic cardKind; an unknown/absent kind degrades to an inert generic card (T-31-04-T2) — no workflow-name branch (SC-001). react-markdown default renderer only (no rehype-raw / dangerouslySetInnerHTML — T-31-04-T)"
  - "MessageBubble gains optional events?/onRequestOpenTab? props (additive, tsc-identity): a narrator turn (generic cardKind) renders ResultCard; an assistant turn renders the plan-01 ChatBlock strip (thinking/tool/file_ops) above the KEPT react-markdown body + streaming-cursor. Text/usage blocks omitted from the strip (prose is the markdown body; usage rides the token widget)"
  - "ChatPanel gains hideComposer (lane supplies its own composer — no dual composer), onRequestOpenTab + eventsByMessageId threading, and role=log/aria-live/aria-relevant + data-testid=chat-transcript on the scroll region. The plan-02 measured virtual window engages >80 msgs via a MeasuredItem (ResizeObserver-guarded) + top/bottom spacers; the naive auto-scroll stays below threshold"
  - "RunChatLane composer mode keys off a GENERIC RunLaneState union (idle/building/clarify/gate/complete/terminal) — the D-12 live-state table. Free-text send -> transport-agnostic sendMessage; complete-mode free text -> onRevise (revision turn); quick-actions -> the shared plan-05 callbacks. Suggestions render as generic-id chips (SC-001)"

patterns-established:
  - "RunChatLane as the run-screen composition root that plan 07 mounts + wires live"
  - "hideComposer seam on ChatPanel for host-supplied composers"
  - "data-testids: run-chat-lane / chat-composer / chat-stop / chat-send / chat-suggestion-chip / chat-relaunch / chat-result-card(+link) / chat-transcript / chat-message"

requirements-completed: [CHATUI-01]

# Metrics
duration: 9min
completed: 2026-07-08
---

# Phase 31 Plan 04: Revived Chat Lane Composition Root (RunChatLane + ResultCard + revived kit) Summary

**The revived chat lane composes the plan-01..06 borrow pieces + the plan-03 data layer into one working CURRENT-SKIN surface: a family-anchored transcript with streaming markdown + `aria-live`/`role=log`, 5-kind narrator `ResultCard`s deep-linking via the nonce'd seam, plan-01/02 agent blocks + measured virtualizer (>80 msgs), and a D-12 composer-mode-per-state that absorbs the AgentProgressPanel Stop/revise/suggestions controls and mounts the plan-05 quick-actions + plan-06 attachments/token widget — 28 new green vitest cases, SC-001 grep 0, tsc identity, zero backend/e2e change (INV-3).**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-07-08T09:06:26Z
- **Completed:** 2026-07-08T09:15:33Z
- **Tasks:** 3
- **Files modified:** 4 created + 2 modified

## Accomplishments
- `ResultCard.tsx` — a narrator `chat_reply` card rendered BY its generic `cardKind` (a switch, never a workflow name — SC-001). Each kind shows the narrator markdown text + a deep-link affordance firing `onRequestOpenTab(tab)` (the plan-03 seam, borrow #6): `deliverable` → "Open in Preview" and labels the output **"Deliverable"** (LOCK-F); `spec_revision` → **"Revising spec — cycle N"** (KAN-101 loop-back, distinct from a family revision run per LIVE-STATE-CONTRACT §2b); clarify/gate/pipeline → Steps. An unknown/absent kind degrades to an inert generic card (T-31-04-T2).
- `MessageBubble.tsx` (revived) — a narrator turn renders `ResultCard`; an assistant turn renders the plan-01 `ChatBlock` strip (`buildBlocks` → `ThinkingBlock` / `renderToolBlock` / `FileOpsSummary`) ABOVE the KEPT react-markdown body + `streaming-cursor`. Additive `events?`/`onRequestOpenTab?` props (tsc-identity). `data-testid=chat-message` per bubble.
- `ChatPanel.tsx` (revived) — the scrollable transcript region now carries `role=log` + `aria-live=polite` + `aria-relevant="additions text"` + `data-testid=chat-transcript` (the open-design a11y landmine, shipped from day one). It delegates to the plan-02 measured virtual window above 80 messages (`MeasuredItem` + top/bottom spacers) and keeps the naive auto-scroll below it. `hideComposer` suppresses the built-in `ChatInput` so the lane owns the composer (no dual composer).
- `RunChatLane.tsx` — the left-column composition root: header (`ChatTokenWidget` + Stop) + `ChatPanel` transcript + a UNIFIED composer that switches mode on the GENERIC `RunLaneState` (D-12): `clarify` → `InlineClarifyActions`, `gate` → `InlineGateActions`, `building` → steering hint + free text, `complete` → revision textarea + suggestion chips, `terminal` → relaunch, `idle` → free text. Absorbs Stop (visible while running, hidden on terminal), revise-as-chat, and suggestions-as-chips. Free-text send → transport-agnostic `sendMessage`; complete-mode free text → `onRevise`; quick-actions → the shared plan-05 callbacks. Mounts the plan-06 `ChatAttachments`.

## Task Commits

Each task was committed atomically:

1. **Task 1: ResultCard — narrator cards (5 kinds) + nonce'd deep-link (borrow #6, LOCK-F)** — `9a945062` (feat)
2. **Task 2: revive the kit — aria-live/role=log transcript + agent-block rendering (D-09/D-15)** — `c45d13aa` (feat)
3. **Task 3: RunChatLane composition root — transcript + D-12 composer modes + absorbed controls** — `9bf65f27` (feat)

**Plan metadata:** _(this docs commit — SUMMARY + STATE + ROADMAP)_

_Opportunistic TDD (`tdd_mode=false`): each task committed component + suite together as one atomic unit (mirrors 31-01..03)._

## Files Created/Modified
- `frontend/src/components/chat/ResultCard.tsx` — narrator card, generic-cardKind switch + deep-link affordance (LOCK-F/KAN-101) (created)
- `frontend/src/components/chat/ResultCard.test.tsx` — 10 vitest cases (5 kinds render + deep-link tab, Deliverable label, cycle-N, deepLink override, unknown-kind degrade, SC-001 source grep) (created)
- `frontend/src/components/chat/RunChatLane.tsx` — the composition root (transcript + D-12 composer + absorbed controls) (created)
- `frontend/src/components/chat/RunChatLane.test.tsx` — 12 vitest cases (aria-live/role=log, narrator card, streaming cursor+markdown, agent block strip, clarify/gate/complete modes, Stop visible/hidden, free-text→sendMessage, complete→onRevise, SC-001 grep) (created)
- `frontend/src/components/chat/MessageBubble.tsx` — narrator→ResultCard + assistant agent-block strip + `data-testid=chat-message` (modified)
- `frontend/src/components/chat/ChatPanel.tsx` — aria-live/role=log transcript region + measured virtualizer (>80) + `hideComposer` + events/onRequestOpenTab threading + guarded auto-scroll (modified)

## Decisions Made
- **Composer mode keyed on a GENERIC `RunLaneState` union, not a workflow name (SC-001):** the D-12 live-state table maps cleanly to `idle/building/clarify/gate/complete/terminal`; the lane never inspects a pipeline_type. Suggestions carry a generic `id` the caller maps.
- **`hideComposer` seam over rewriting ChatInput:** the lane needs a unified, mode-switched composer that absorbs revise/suggestions, so ChatPanel suppresses its built-in `ChatInput` rather than the lane rendering two composers. Smallest correct diff, non-breaking (default renders the composer as before).
- **Agent-block strip omits text/usage:** the markdown body IS the prose (avoids a double render), and `usage` rides the plan-06 `ChatTokenWidget`; the strip surfaces only reasoning/tools/file-ops — the value the naive bubble lacked.
- **`events?` threaded via an `eventsByMessageId` map, not stored on ChatMessage:** plan 03 deliberately kept `ChatMessage` free of an events field; the lane supplies per-turn events through an optional map (the live wiring is plan 07).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Guarded `ChatPanel` auto-scroll for jsdom**
- **Found during:** Task 3 (first test render of the real `ChatPanel` via `RunChatLane`)
- **Issue:** `messagesEndRef.current?.scrollIntoView(...)` threw `TypeError: scrollIntoView is not a function` under jsdom (not implemented), failing every lane test that mounts the transcript.
- **Fix:** Guard the call with `typeof end.scrollIntoView === "function"` — degrade rather than throw. Behavior in the browser is unchanged.
- **Files modified:** frontend/src/components/chat/ChatPanel.tsx
- **Committed in:** `9bf65f27` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking). No scope creep — same components, same behavior; the guard only affects the non-browser test environment.

## Issues Encountered
None beyond the jsdom `scrollIntoView` guard noted above (surfaced by the Task-3 suite, fixed before commit).

## Known Stubs
None. The lane composes real, test-proven pieces. The LIVE mounting + transport wiring (threading the real `useRunChat`/`RunConnectionProvider` callbacks and the per-turn `eventsByMessageId`) is the declared **plan 31-07** boundary — an interface-complete composition root here, consumed there. This is the plan's stated scope split, not a stub.

## Verification Evidence (offline)
- `npx vitest run src/components/chat/` → **12 files, 96/96 passed** (28 new this plan: 10 ResultCard + 12 RunChatLane + the revived-kit behaviors exercised through the lane suite).
- `npx vitest run src/components/chat/ResultCard.test.tsx` → 10 passed; `RunChatLane.test.tsx` → 12 passed.
- a11y (POR §7 landmine): `grep -q 'role="log"'` + `grep -q 'aria-live'` on `ChatPanel.tsx` → both present; asserted in the lane suite (role=log + aria-live=polite on `chat-transcript`).
- `npx tsc --noEmit` (excluding the known `e2e/fixtures/mockApi.ts` baseline) → **0 new `error TS`** (tsc identity held; baseline was 0).
- SC-001: `grep -cE '"prototype"|od_ppt|app_builder|user_stories|ppt_revision'` on `ResultCard.tsx` and `RunChatLane.tsx` → **0** each (both key on generic card kinds / runState only).
- INV-3 + FIX-039: `git diff --name-only HEAD~3..HEAD` → all 6 files under `frontend/src/components/chat/`; no backend, no golden fixture, no `frontend/e2e/**`, no `useWorkflow.ts` touched.

## Next Phase Readiness
- `RunChatLane` is the interface-complete composition root plan **31-07** mounts into the run screen and wires to the live `useRunChat` transcript + `RunConnectionProvider` transport + the per-turn `eventsByMessageId`, then adds the e2e specs (mock-SSE driver + MOCKWS-CHAT-DRIVER).
- Live end-to-end (streaming SSE, multimodal send) remains milestone-end live-deferred (DEF-29-09-1) — unchanged by this FE-only plan.
- No blockers.

## Self-Check: PASSED

All 4 created files present on disk; both modified files carry the plan changes; all three task commits (`9a945062`, `c45d13aa`, `9bf65f27`) present in git history.

---
*Phase: 31-chat-lane-mvp-a3*
*Completed: 2026-07-08*
