---
id: BUG-017-GROUNDED-CONTEXT
type: bug
kind: event
title: BUG-017 — grounded fix spec
status: open
applies_to:
  phases: []
  modules:
  - RunConnectionProvider
  - agents
  - api
  - app
  - chat
  - useRunChat
  - useRunChat.test
  globs:
  - backend/app/api/run_commands.py
  - frontend/src/hooks/useRunChat.ts
  - frontend/src/app/dashboard/page.tsx
  - useRunChat.ts
  - page.tsx
  - frontend/src/providers/RunConnectionProvider.tsx
  - run_commands.py
  - useRunChat.test.ts
  - backend/app/agents/chat/concierge.py
  requirements: []
locked_constraints: []
verification:
  type: manual
  status: required
  test_files: []
compact_summary: 'page.tsx voided the sendCommand promise so the re-fetch raced ahead of the persisted chat_reply; awaiting it fixed delivery.'
last_updated: '2026-08-14'
author: 'Bilal Arshad <bilala@hexaware.com>'
author_source: applies-to-glob
---

# BUG-017 — grounded fix spec (Concierge chat reply never renders on a completed run)

> **FRONTEND-ONLY, ~1 line + a RED->GREEN test.** Root cause verified to file:line by a deep-investigation agent (LIVE-REPRODUCED: Concierge POST measured 11.15s; the re-fetch measured firing at +0.34s) AND re-confirmed by the orchestrator against the current source. Executable spec for a `gsd-quick --validate`. This fixes **delivery** (the reply becomes visible). The separate **grounding** issue (a completed run described as "in progress") + the ~11s latency are OUT OF SCOPE here (see "Explicitly out of scope").

## The bug (verified against live source)
Asking a question in the left chat on a **completed** run (e.g. "what is the status") shows **no answer**. The Concierge's reply IS produced and IS saved — it is a complete answer persisted durably (`backend/app/api/run_commands.py:988` `store.append_event_next_seq(run_id, event_id="chat-reply:{message_id}", type="chat_reply", text=answer)`, measured 1690 chars). It is persisted **durable-only, with no live-queue push**, so the frontend's sole delivery path is the DEF-44-12-2 **re-fetch-after-send** in `frontend/src/hooks/useRunChat.ts:365-375` (`await sendCommand(runId, payload)` then `fetchEvents(runId, lastSeq)` folded via `handleFrame`, idempotent by `event_id`).

**Root cause — a delivery race, one line.** `frontend/src/app/dashboard/page.tsx:1027-1029` wires the `sendCommand` prop that `useRunChat` consumes as:
```ts
sendCommand: (runId, payload) => {
  void runConnection.sendCommand(runId, payload);
},
```
It **`void`s the async POST promise and returns `undefined`**. So the hook's `await sendCommand(runId, payload)` (`useRunChat.ts:366`) awaits `undefined` and resolves **immediately**; the re-fetch fires (measured +0.34s) **before** the Concierge POST completes (measured 11.15s) and the `chat_reply` is persisted. No `chat_reply` exists yet, nothing folds in, and **no second re-fetch is ever triggered** — so the reply never renders (it only appears if the run is later reopened, whose `seedTranscript` re-fetches all durable events, `page.tsx:1319`). This defeats DEF-44-12-2's explicit "await the up-channel THEN re-fetch" contract (that ticket flagged "live proof pending B3/B5" — this IS that failure).

`runConnection.sendCommand` (`frontend/src/providers/RunConnectionProvider.tsx:362-393`) is `async` and awaits the POST; for a `/messages` turn it resolves only **after** the backend responds (i.e. after the reply is persisted, `run_commands.py:987-988`). Awaiting it is exactly what makes the re-fetch land after the reply exists.

## The fix (FE-only)
**Single edit — `frontend/src/app/dashboard/page.tsx:1027-1029`:** make the adapter await and return the promise instead of voiding it:
```ts
sendCommand: async (runId, payload) => {
  await runConnection.sendCommand(runId, payload);
},
```
Now `await sendCommand(...)` in `useRunChat` waits for the POST (which resolves only after the reply is persisted) -> the re-fetch fires **after** the `chat_reply` exists -> it folds and renders as its own turn.

**Why this is safe (each verified):**
- The adapter returns `Promise<void>` — it still **discards** `runConnection.sendCommand`'s resolved value (the launched run_id the W1/44-01 launch->attach path uses); the chat up-channel ignores that value, exactly as the current comment at `page.tsx:1024-1026` states.
- The **only** consumer of this adapter is `useRunChat`, which already `await`s it at `useRunChat.ts:366` and returns `messageId` synchronously **before** the awaited work (the optimistic user bubble + `return messageId` at `:377` are unaffected — verify the send-routing test still passes).
- The launch->attach path (W1, runId null) calls `runConnection.sendCommand` at a **different** call site (not through `useRunChat.sendMessage`), so it is untouched.
- Type: if `tsc` complains that `Promise<void>` is not assignable to the `sendCommand` prop type (`useRunChat.ts:61-66`), widen that prop's return type to `void | Promise<void>` (do NOT change the call site's `await`, which already tolerates both). Keep the change minimal.

## Verification (RED->GREEN required)
- **Unit (vitest), the race — RED before / GREEN after:** in `useRunChat`'s test, wire a `sendCommand` that resolves on a **deferred** promise (does NOT resolve synchronously) and a `fetchEvents` spy; assert `fetchEvents` is called **only after** `sendCommand`'s promise resolves (i.e. ordering: send resolves -> then fetch). With the current `void` adapter shape the equivalent (sync-resolving) wiring calls `fetchEvents` before the send settles — encode that as the fail-before. Reuse the existing `useRunChat.test.ts` harness (send-routing tests at `:140-143` must stay green).
- **tsc** clean.
- **Mocked Playwright (from inside `frontend/`, kill :3000 first):** the chat specs stay green — `ts-chat`, `ts-chat-cards`; plus `ts-sse`, `ts-sse-resilience`, `ts-s.reconnect`, `ts-j.streaming`, `ts-t.history`, `ts-u.revisions` (the live-transport + reopen suites) must not regress. If a mocked spec can assert it: a Concierge ASK turn whose reply arrives only in the post-send re-fetch now renders as its own assistant turn (was absent).
- The "132/0" mocked baseline is STALE — establish the real green count by RUNNING the suite before/after; don't trust a number.

## Scope fences (STRICT)
- **Frontend only.** No backend/engine/queue change. Do NOT add a live-queue push for the Concierge reply (it would create an orphan queue that falsely marks a terminal run live — the durable-only persist + re-fetch is the intended design).
- Touch **only** the `sendCommand` adapter at `page.tsx:1027-1029` (and, if strictly required for tsc, the `sendCommand` prop type in `useRunChat.ts`). Do NOT refactor `useRunChat.sendMessage`, the re-fetch block, or `handleFrame`.
- Do NOT touch the BUG-014-B parser, the BUG-015 `detachRun`/reconnect logic, or the reducer.

## Explicitly OUT OF SCOPE (separate follow-ups, do NOT do here)
- **Concierge mis-grounding** (a completed run described as "IN PROGRESS") — caused by `read_events` (`backend/app/agents/chat/concierge.py:353-357`) returning ALL events from seq 0 so the terminal `pipeline_complete` is buried. The right fix is NOT a naive tail-cap (that would break "what did agent X say" questions) — prefer injecting the run's current status into the Concierge system prompt. Backend, needs a restart, needs a design decision. Deferred.
- **Concierge ~11s latency.** Deferred with the above.
- **Optional** pending/spinner state on the ASK turn. Deferred.

## Constraints
- Branch **feat/ui-2** (NEVER main/staging). Worktrees OFF -> sequential. **NO commit trailer** (no Co-Authored-By / Claude-Session). **NEVER push.**
- FE cwd-sensitive: run vitest/Playwright from inside `frontend/`; kill :3000 before mocked Playwright.
- SC-001: `page.tsx` is exempt; keep any guarded component workflow-name-literal-free.
- Do NOT run a live Bedrock run in the executor — the orchestrator does the live proof after (send a chat ASK on a completed run; the reply must render without a reopen).
- STATE.md quirk: prefer the quick-task table; if `progress:` gets clobbered, restore `total_phases:37 completed_phases:35 total_plans:208 completed_plans:207 percent:95`.
