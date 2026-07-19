---
phase: quick-260719-m0o
plan: 02
subsystem: frontend / run-screen chat lane
tags: [sse, streaming, concierge, chat, INV-12, SC-001]
requires:
  - "Plan 01 (backend): fresh-Concierge POST /api/runs/{id}/messages returns text/event-stream (chat_reply_chunk frames + terminal chat_reply)"
provides:
  - "useRunChat chat_reply_chunk accumulation into one assistant bubble keyed chat-reply:{message_id}"
  - "src/lib/sseFrame.ts parseSseBlock — the single shared SSE block parser"
  - "sendCommand content-negotiated streamed-body drain into the existing subscriber fan-out"
affects:
  - frontend/src/hooks/useRunChat.ts
  - frontend/src/hooks/useRunStream.ts
  - frontend/src/providers/RunConnectionProvider.tsx
tech-stack:
  added: []
  patterns: ["agent_chunk idempotent-accumulation reused for chat_reply_chunk", "content-negotiated streamed POST drain reusing the SSE reader-loop shape"]
key-files:
  created:
    - frontend/src/lib/sseFrame.ts
    - frontend/src/lib/sseFrame.test.ts
  modified:
    - frontend/src/hooks/useRunChat.ts
    - frontend/src/hooks/useRunChat.test.ts
    - frontend/src/hooks/useRunStream.ts
    - frontend/src/providers/RunConnectionProvider.tsx
    - frontend/src/providers/RunConnectionProvider.test.tsx
decisions:
  - "Bubble keyed chat-reply:{message_id} so the terminal chat_reply (event_id chat-reply:{message_id}) finalizes the SAME turn — no duplicate."
  - "Branch STRICTLY on res.headers.get('content-type') including 'text/event-stream', never on a concierge literal (SC-001)."
  - "ONE parser (parseSseBlock) reused by useRunStream + sendCommand (INV-12, no dual parse); id: line stays hook-local for the cursor fallback."
metrics:
  duration: ~20m
  completed: 2026-07-19
  tasks: 2
  files: 7
---

# Phase quick-260719-m0o Plan 02: Stream the Concierge reply (FRONTEND) Summary

FE consumes Plan 01's streamed `chat_reply_chunk` frames — deltas accumulate into one growing assistant bubble finalized by the terminal `chat_reply`, and the POST up-channel now content-negotiates and drains a `text/event-stream` body into the existing subscriber fan-out, so the reply streams live on BOTH live and completed runs with no SSE re-attach.

## What was built

### Task FE-1 — `useRunChat` accumulates `chat_reply_chunk`
New pure reducer `upsertStreamingReply(prev, data)` (mirrors the `agent_chunk` accumulation pattern):
- `message_id = typeof data.message_id === "string" ? data.message_id : ""`; empty → return prev unchanged (never key on an empty id).
- `delta = typeof data.delta === "string" ? data.delta : ""`; bubble id = `chat-reply:{message_id}`.
- Existing turn with that id → `{ ...prev[idx], content: prev[idx].content + delta }` (grows). Absent → append a new assistant `ChatMessage` `{ id, chatSessionId: threadId ?? runId ?? "", role: "assistant", content: delta, createdAt, runId, threadId }`.
- New `case "chat_reply_chunk":` added to `handleFrame`'s switch; the top-of-handler `event_id` dedup and the `seq` cursor are untouched (chunks carry neither). The terminal `chat_reply` continues through `upsertNarratorMessage`, which finds the same idx (`chat-reply:{message_id}`) and overwrites `content` with the authoritative `data.text` — seamless finalize, no duplicate turn.
- Spinner: no new wiring — the first chunk makes an assistant turn the transcript tail, firing RunChatLane's existing clear-effect (`useRunChat`/RunChatLane.tsx:800-804 sets `replyPending=false` when the last message is an assistant). Confirmed by reading the effect; not duplicated.

### Task FE-2 — one shared `parseSseBlock` + streamed-body drain in `sendCommand`
- `src/lib/sseFrame.ts` exports pure `parseSseBlock(rawBlock): { type, data } | null`, lifted verbatim from `useRunStream.dispatchBlock` (the event/data line-split + `{type,data}` envelope-unwrap; null on empty/malformed). `dispatchBlock` refactored to call it, keeping the hook-local concerns (the `id:` line cursor fallback, keepalive drop, `stream_attached` liveness, `onMessageRef`) around it — behavior-identical (its own suite stays green).
- `RunConnectionProvider.sendCommand`: when `runId` is set, `const contentType = res.headers.get("content-type") ?? "";` — if `res.ok && res.body && contentType.includes("text/event-stream")`, drain with the SAME reader-loop shape as `useRunStream` (`res.body.getReader()` + `TextDecoder`, `buf += decode(...).replace(/\r\n/g,"\n")`, split on `"\n\n"`, `parseSseBlock` each block, `fanout(frame)` each non-null non-keepalive, flush the trailing block), then `return null`. Otherwise the unchanged `return null` per-run path. The launch (`runId == null`) `res.json()` path is byte-identical. `fanout` added to the `useCallback` deps.
- Frames reach the transcript through the EXISTING `fanout → subscribersRef → useRunChat.handleFrame` seam; FE-1's `chat_reply_chunk` case consumes them. `useRunChat.sendMessage`'s `fetchEvents`-after-send left IN PLACE (durable-reply recovery on a mid-stream drop; `event_id` dedup prevents a double render).

## RED evidence (both tasks)

- **FE-1:** with no `chat_reply_chunk` case, three chunk frames fall through `handleFrame`'s `default` → zero assistant turns. `Test 17` failed: `expect(replies).toHaveLength(1)` (received 0). (Test 18's no-duplicate finalize passes both ways — the terminal alone yields one turn — so it guards the GREEN side.)
- **FE-2:** `sseFrame.test.ts` failed to resolve `./sseFrame` (parser did not exist). `RunConnectionProvider` `Test 5` failed: before the change `sendCommand` returned null without reading the body → the subscriber received `[]` (expected 3 ordered frames). Test 6 (JSON path) passed both ways.

## Verification (offline, from `frontend/`)

- `npx vitest run src/hooks/useRunChat.test.ts src/lib/sseFrame.test.ts src/hooks/useRunStream.test.ts src/providers/RunConnectionProvider.test.tsx` → **34 passed (34)**.
- `npx vitest run src/components/chat src/providers src/hooks` → **215 passed (25 files)** — the li0 chat-lane suite and useRunStream stay green, no regression.
- `npx tsc --noEmit` → exit 0, clean.

## Deviations from Plan

None — plan executed exactly as written. FE-only; no backend change, no migration. The live Bedrock re-proof (incremental streaming on live + completed runs, durable persistence, mid-stream-drop degradation) is orchestrator-owned and not run here.

## Commits

- `e4fc6dbf` feat(chat): accumulate chat_reply_chunk deltas into one streaming assistant bubble (FE-1)
- `ec1847c3` feat(chat): sendCommand drains a streamed POST body via one shared parseSseBlock (FE-2)

## Self-Check: PASSED
- FOUND: frontend/src/lib/sseFrame.ts
- FOUND: frontend/src/lib/sseFrame.test.ts
- FOUND commit e4fc6dbf, ec1847c3
