---
inclusion: fileMatch
fileMatchPattern: "frontend/src/components/chat/**,frontend/src/hooks/useRunChat.ts,frontend/src/hooks/useRunStream.ts,frontend/src/providers/RunConnectionProvider.tsx"
---

# Frontend — Chat & Transport Domain

> Loaded when editing chat components, the run-chat hook, the SSE stream hook, or the connection provider. See `invariants.md` for hard constraints.

---

## Transport Architecture

```
page.tsx
  └── RunConnectionProvider (SSE down + REST up)
      ├── useRunStream (EventSource-like, fetch + ReadableStream)
      └── sendCommand → POST /api/runs/{id}/gate|answers|cancel|messages|revisions
```

`useWebSocket.ts` is **deleted** (Phase 44 LOCK-B). Only `useHandoffSocket.ts` (for `/ws/handoff`) remains.

---

## SSE Frame Parser Rules (BUG-014-B fix)

The real backend wire format is CRLF:
```
id: {seq}\r\n
data: {"type":..., "data":{...}}\r\n
\r\n
```

The parser in `useRunStream.ts`:
1. CRLF-normalizes on decode (`.replace(/\r\n/g, "\n")`)
2. Unwraps the envelope: `if (typeof parsed.type === "string") { type = parsed.type; data = parsed.data }`
3. Is **tolerant** of the legacy `\n\n` + `event:` line shape

**Do NOT change the backend SSE wire** — `run_stream.py` + sse-starlette are correct.

---

## `RunConnectionProvider` Rules

- Mounted in `frontend/src/app/layout.tsx` (Phase 43).
- `AUTO_STREAM_STATUSES = {running, planning, analyzing, generating, revising}` — excludes `waiting_for_user` / `clarifying` (parked runs emit nothing while parked).
- Max concurrent streams = `AUTO_STREAM_STATUSES` runs + one focused run (`focusedRunIdRef`).
- `attachRun(id)` sets/REPLACES the focused run — no accumulation (BUG-013 fix).
- On terminal run: `detachRun(id)` clears the focus (BUG-015 fix).
- `sendCommand` content-negotiates: `text/event-stream` → reader loop + `parseSseBlock`; else `res.json()`.
- `sendCommand` MUST be `await`-ed by callers so re-fetches land after the POST completes (BUG-017).

## `useRunStream` Reconnect Rules

- `sawNonLiveAttachRef`: if the last `stream_attached` had `live: false`, the next close → `disconnected` (not `reconnecting`) — prevents the completed-run reconnect loop (BUG-015 fix).
- `stickToBottomRef`: tracks whether the user has scrolled up (< 120px from bottom = stick).
- Exponential-backoff reconnect capped at 30s.
- `REQUEST_TIMEOUT_MS = 30_000` on all `api.ts` fetch calls (BUG-013 hardening).

---

## `useRunChat` Rules

- Family-anchored (D-02): a revision run's frames stitch into the SAME transcript via `runId`/`threadId`.
- `event_id` dedup — `upsertNarratorMessage` keys on `chat-reply:{message_id}` **before** `message_id` to prevent a streaming reply overwriting the user's question bubble (BUG-018 fix).
- `seedTranscript(frames)` clears seen-set + messages then folds frames — idempotent.
- `seedRunChatTranscript([])` on fresh non-revision launch (BUG-021, must be inside `if (!isRevision)`).
- Re-fetch after `sendMessage`: awaits the up-channel POST, then fetches events since `lastSeq` cursor.
- `getRunEvents` maps each durable row to `data: { ...(row.payload_json ?? {}), event_id: row.event_id, seq: row.seq }` — the row's column `event_id` wins over any same-named payload key (BUG-018 fix).

---

## `RunChatLane` Rules

- **SC-001**: every branch keys on `runState` / `laneGate` / generic discriminators — never a workflow/agent-name literal.
- `classifyFreeText(text)` → `"ask"` | `"change"` — change-intent checked BEFORE question-shape (trap: "can you make the button bigger?" is change, not ask).
- ASK → `sendMessage(..., { concierge: true })` + `setReplyPending(true)` (typing indicator).
- CHANGE → show `heldRefinement` confirm chip; `onRevise` fires only on explicit confirm.
- `replyPending` safety-net: 45s timeout clears it if the reply never arrives.
- `viewedRunId`-keyed reset prevents stale spinner leaking to a new run.
- Chain suggestion chips rendered in complete state — `onSuggestion(id)` routes to the wizard.

## Chat Scroll Rules (Phases nwe/rqo)

- A `ResizeObserver` drives continuous scroll-following (not the chunk clock) — `stickToBottomRef` gates it.
- Instant (`behavior:"auto"`) during streaming — never `"smooth"` (stacked smooth animations jank).
- `stickToBottomRef` is cleared when the user scrolls up (< 120px gate).
- Fresh-user-turn re-arms `stickToBottomRef=true` and force-scrolls `messagesEndRef`.
- **Do NOT reintroduce** the pin-by-selector logic (`scrollIntoView({block:"start"})` on the user turn) — user rejected it.

## Streaming Reply Rules (Phase m0o)

- `converse` on `ConciergeCapability` streams via `on_chunk` callback — the endpoint returns `EventSourceResponse`.
- FE folds `chat_reply_chunk` deltas into the growing bubble keyed `chat-reply:{message_id}`.
- Terminal `chat_reply` (same key) overwrites with authoritative text — no duplicate turn.
- `chat_reply_chunk` frames are **transient** — never `append_event_next_seq`, never replayed.

## "Reading Run Data" Indicator (Phase rqo)

- `isReading` state in `RunChatLane` — set after `READING_GAP_MS = 700` chunk gap, cleared on next chunk or finalize.
- `READING_MAX_MS = 15_000` caps a pathological stall (safety-net, mirrors `replyPending` timeout).
- Mid-reply chunk-gap on the Concierge path = a read-tool call — the indicator is honest.

---

## Open-Design Borrow (Phase 31 — Apache-2.0 attribution required)

7 mechanisms reimplemented from nexu-io/open-design:
1. `partial-json.ts` — tolerant truncated-JSON repair
2. `streaming-json.ts` — single named-string-field streaming extractor
3. `blocks.types.ts` — `AgentEvent`/`ChatBlock` unions
4. `buildBlocks.ts` — pure events→blocks coalescing reducer
5. `useMeasuredVirtualWindow.ts` — measured virtual window
6. `useTabDeepLink.ts` — nonce'd deep-link seam
7. `ThinkingBlock`, `TodoCard`, `FileOpsSummary` blocks

Attribution in `frontend/NOTICE` + `frontend/THIRD-PARTY-NOTICES.md` + per-file headers.  
**No new npm dependencies** — all reimplemented from scratch.

`TodoCard` is **deleted** (Phase 42) — no `"todo"` block kind is emitted.

---

## `parseSseBlock` — Shared SSE Parser

Located in `frontend/src/lib/sseFrame.ts`. Used by **both** `useRunStream` and `RunConnectionProvider.sendCommand`. Do not duplicate. Any change must be verified against both consumers.

---

## Chat Event Types (Phase 28 — vocabulary guard)

These are in `_DOCUMENTED_EVENT_TYPES` (test_phase3_cutover_verify.py):
- `chat_message` — user turn echo
- `chat_reply` — narrator cards / Concierge answer
- `stream_attached` — reattach handshake (replaces `pipeline_reconnected` for chat)

`message_id` and `replayed_through_seq` are in `_VOLATILE_STRIP_KEYS`.
