---
phase: quick-260719-m0o
plan: 02
type: execute
wave: 2
depends_on: ["01"]
files_modified:
  - frontend/src/hooks/useRunChat.ts
  - frontend/src/hooks/useRunChat.test.ts
  - frontend/src/lib/sseFrame.ts
  - frontend/src/lib/sseFrame.test.ts
  - frontend/src/hooks/useRunStream.ts
  - frontend/src/providers/RunConnectionProvider.tsx
  - frontend/src/providers/RunConnectionProvider.test.tsx
autonomous: true
requirements: [QUICK-260719-m0o-FE]
must_haves:
  truths:
    - "Streamed chat_reply_chunk deltas render as a single growing assistant bubble in the run-screen chat lane"
    - "The terminal chat_reply finalizes the same bubble with the authoritative full text, with no duplicate turn"
    - "The li0 typing indicator hides the instant the first chunk lands (the streaming text replaces it)"
    - "A streamed text/event-stream POST response is parsed and fan-out-dispatched to the transcript on BOTH live and completed runs, with no SSE re-attach"
    - "A JSON /messages response and the launch (POST /api/runs) response take their unchanged paths"
  artifacts:
    - path: "frontend/src/hooks/useRunChat.ts"
      provides: "chat_reply_chunk accumulation into one assistant turn keyed by message_id, finalized by the terminal chat_reply"
      contains: "chat_reply_chunk"
    - path: "frontend/src/lib/sseFrame.ts"
      provides: "shared parseSseBlock(rawBlock) -> {type,data}|null (single SSE parser, reused by useRunStream + sendCommand)"
      contains: "parseSseBlock"
    - path: "frontend/src/providers/RunConnectionProvider.tsx"
      provides: "sendCommand reads a text/event-stream POST body and dispatches each frame through fanout"
      contains: "text/event-stream"
  key_links:
    - from: "frontend/src/providers/RunConnectionProvider.tsx"
      to: "frontend/src/hooks/useRunChat.ts"
      via: "fanout(frame) -> subscribersRef -> useRunChat.handleFrame"
      pattern: "fanout\\("
    - from: "frontend/src/providers/RunConnectionProvider.tsx"
      to: "frontend/src/lib/sseFrame.ts"
      via: "parseSseBlock(rawBlock)"
      pattern: "parseSseBlock"
    - from: "frontend/src/hooks/useRunStream.ts"
      to: "frontend/src/lib/sseFrame.ts"
      via: "parseSseBlock in dispatchBlock"
      pattern: "parseSseBlock"
---

<objective>
Stream the Concierge chat reply on the run-screen left lane — FRONTEND half. Consume the `chat_reply_chunk` frames Plan 01 streams: accumulate the deltas into one growing assistant bubble, finalize on the terminal `chat_reply`, and teach the POST up-channel (`sendCommand`) to READ a streamed `text/event-stream` response and dispatch its frames through the existing subscriber fan-out — so the reply streams on BOTH live and completed runs with no SSE re-attach.

Purpose: the user sees the reply grow token-by-token (the li0 typing indicator yields to it on the first chunk), including the common "what's the status" on a *completed* run — without any dependence on `AUTO_STREAM_STATUSES` (BUG-013) or `_PIPELINE_QUEUES`.

Output: `useRunChat` gains a `chat_reply_chunk` accumulation case; the SSE block parser is extracted to one shared helper; `sendCommand` content-negotiates and drains a streamed POST body into the transcript. The durable `chat_reply` + the li0 spinner safety-net remain the recovery net for a mid-stream drop.

## Consumes from Plan 01 (real shapes — do not re-derive)
- `chat_reply_chunk` frame: `{ type: "chat_reply_chunk", data: { pipeline_run_id, message_id, delta } }` — transient (never persisted), NO event_id, NO real seq, delivered exactly once in the POST body.
- Terminal `chat_reply` frame: `{ type: "chat_reply", data: { pipeline_run_id, message_id, text, seq, proposals } }` — the durable full-text record; its `event_id` is `chat-reply:{message_id}` (unchanged from today).
- The fresh-Concierge POST response has `content-type: text/event-stream`; every other `/messages` response stays `application/json`; the launch `POST /api/runs` stays JSON.
</objective>

<execution_context>
Standing constraints (BINDING for every task in this plan):
- Branch **feat/ui-2**. Commit with the FE convention (`feat(chat): ...`) — **NO trailers, NEVER push**.
- Run FE tooling **from** `/Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend` (vitest/tsc are cwd-sensitive; cwd resets between calls — always `cd` there in the same command).
- A live backend runs on **:8000** and Next on **:3000** — do **NOT** restart, bind, or touch them.
- FE-only: no backend change, no migration. Re-verify every line anchor before editing (line numbers drift).
- INV-12: reuse ONE SSE parser and the existing transcript/fan-out seams — no third streaming path, no dual parser.
</execution_context>

<context>
@.planning/CONCIERGE-STREAMING-SCOPE.md
@.planning/quick/260719-li0-concierge-chat-lane-show-a-typing-thinki/SUMMARY.md
@.planning/quick/260719-m0o-stream-the-concierge-reply-converse-astr/01-PLAN.md
@frontend/src/hooks/useRunChat.ts
@frontend/src/hooks/useRunStream.ts
@frontend/src/providers/RunConnectionProvider.tsx
@frontend/src/components/chat/RunChatLane.tsx
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task FE-1: useRunChat accumulates chat_reply_chunk into one assistant turn; terminal chat_reply finalizes it</name>
  <files>frontend/src/hooks/useRunChat.ts, frontend/src/hooks/useRunChat.test.ts</files>
  <behavior>
    - N chat_reply_chunk frames with the same message_id produce exactly ONE assistant turn whose content is the concatenation of the deltas (grows per chunk).
    - The terminal chat_reply (event_id chat-reply:{message_id}, text = full answer) finalizes the SAME bubble — still exactly one assistant turn, content = the authoritative full text, no duplicate.
    - Chunk frames carry no event_id, so they bypass the top-of-handler dedup and always append (the POST body delivers them once).
  </behavior>
  <action>
    Add a `case "chat_reply_chunk":` to `handleFrame`'s switch (useRunChat.ts:293). It calls a new pure `upsertStreamingReply(prev, data)` that mirrors the `agent_chunk` idempotent-accumulation PATTERN (useWorkflow.ts:337) inside the transcript:
    - Derive the bubble id as `chat-reply:{message_id}` — the SAME id the terminal `chat_reply` uses (upsertNarratorMessage:239-244 keys on `data.event_id === "chat-reply:{message_id}"`), so the terminal merges the SAME bubble rather than appending a second turn.
    - If a message with that id exists, return a copy with `content: existing.content + delta`. If absent, append a new assistant `ChatMessage` `{ id, role: "assistant", content: delta, chatSessionId, runId, threadId, createdAt }` (reuse the field shape from upsertNarratorMessage).
    - `delta` = `typeof data.delta === "string" ? data.delta : ""`; `message_id` = `typeof data.message_id === "string" ? data.message_id : ""` (skip if empty — never key a bubble on an empty id).
    Do NOT change the top-of-handler event_id dedup or the cursor advance — chunk frames have no event_id (fall through undeduped) and no real seq (cursor untouched). Leave `chat_message` / `chat_reply` / `stream_attached` cases unchanged; the terminal `chat_reply` continues through `upsertNarratorMessage`, which finds the same idx and overwrites `content` with the authoritative `data.text` (accumulated == full text → seamless finalize).

    Spinner: no extra wiring needed — the FIRST chunk makes an assistant turn the transcript tail, which fires the li0 clear-effect in RunChatLane (the transcript `useEffect` that sets `replyPending=false` when the last message is an assistant, per the li0 SUMMARY), so the typing indicator yields to the streaming text. Confirm this by reading RunChatLane's clear-effect; do NOT duplicate it here.

    Test: add to useRunChat.test.ts — (1) feed three chat_reply_chunk frames (`He`,`ll`,`o`, same message_id) → assert exactly one assistant message, content `Hello`; (2) after the chunks, feed the terminal chat_reply (event_id `chat-reply:{id}`, text `Hello`) → assert still exactly one assistant message, content `Hello` (no duplicate turn). Drive through the hook's real `subscribe` fan-out (the test's existing harness for feeding frames).
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend &amp;&amp; npx vitest run src/hooks/useRunChat.test.ts</automated>
  </verify>
  <done>Streamed chat_reply_chunk deltas render as one growing assistant bubble; the terminal chat_reply finalizes the same bubble with no duplicate; useRunChat suite green. RED evidence recorded: without the chat_reply_chunk case, the chunk frames fall through `default` and produce zero assistant turns → the accumulation assertion fails.</done>
</task>

<task type="auto" tdd="true">
  <name>Task FE-2: sendCommand drains a streamed POST response into the fan-out (completed-run lifecycle); extract one shared SSE parser</name>
  <files>frontend/src/lib/sseFrame.ts, frontend/src/lib/sseFrame.test.ts, frontend/src/hooks/useRunStream.ts, frontend/src/providers/RunConnectionProvider.tsx, frontend/src/providers/RunConnectionProvider.test.tsx</files>
  <behavior>
    - parseSseBlock(rawBlock) returns {type,data} for both wire shapes: the real backend `data: {"type":..,"data":..}` envelope (unwrapped) and the legacy/mock flat shape; malformed → null. Behavior-identical to today's useRunStream.dispatchBlock parse.
    - sendCommand, given a text/event-stream /messages response, reads the streamed body and dispatches each parsed frame through fanout IN ORDER (chunks then the terminal), then returns null.
    - sendCommand, given a JSON /messages response, dispatches nothing and returns null (unchanged). The launch POST /api/runs still parses res.json() for the run_id (unchanged).
  </behavior>
  <action>
    Step 1 — extract the parser (INV-12, one parser): create `frontend/src/lib/sseFrame.ts` exporting a pure `parseSseBlock(rawBlock: string): { type: string; data: Record<string, unknown> } | null`, lifting the id/event/data line-split + `{type,data}` envelope-unwrap logic from `useRunStream.dispatchBlock` (useRunStream.ts:223-251) verbatim (return null on empty/malformed). Refactor `dispatchBlock` to call `parseSseBlock` and keep the hook-local concerns (cursor advance from `data.seq`/id line, keepalive drop, `stream_attached` liveness, `onMessageRef`) around it — behavior-identical (its own test suite must stay green).

    Step 2 — teach sendCommand to drain a streamed body: in `RunConnectionProvider.sendCommand` (RunConnectionProvider.tsx:362), the per-run branch currently does `if (runId) return null;` (line 380-381) WITHOUT reading the body. Before that early return, when `runId` is set, check `res.headers.get("content-type")?.includes("text/event-stream")`. If YES: drain the stream with the EXACT reader loop shape from useRunStream.ts:360-380 — `res.body.getReader()` + `TextDecoder`, `buf += decode(...).replace(/\r\n/g,"\n")`, split on `"\n\n"`, `parseSseBlock` each block, and for each non-null parsed frame call `fanout(frame)` (the existing subscriber fan-out at line 307; drop keepalives — `pipeline_heartbeat`/`pong` — for parity). Flush a trailing block after the reader ends. Then `return null`. If NOT event-stream: keep today's exact `if (runId) return null;`. Guard `res.ok` and `res.body` (bail to `return null` if absent). The launch path (`runId == null`, line 382-392) is UNCHANGED.

    Keep this GENERIC: branch on content-type, never on a `concierge` literal (SC-001). Do NOT change the `sendCommand`/`useRunChat` public signatures — the streamed frames reach `useRunChat.handleFrame` through the SAME `fanout → subscribersRef` path SSE frames already use, and FE-1's `chat_reply_chunk` case consumes them. Leave `useRunChat.sendMessage`'s `fetchEvents`-after-send (useRunChat.ts:365-375) IN PLACE — it re-pulls the durable `chat_reply` and the per-hook event_id dedup drops it (no double-render), and it RECOVERS the reply if the POST stream drops before the terminal (belt-and-suspenders for a mid-stream drop; the li0 45s safety-net clears the spinner in that case).

    Tests: (a) `sseFrame.test.ts` — round-trip parseSseBlock for the nested-envelope shape and the flat shape, and null for malformed (proves the extraction is behavior-identical). (b) add to `RunConnectionProvider.test.tsx`: mock `fetch` to resolve a Response with `headers: { "content-type": "text/event-stream" }` and a `ReadableStream` body emitting two `chat_reply_chunk` blocks then a terminal `chat_reply` block; register a subscriber via `subscribe`; call `sendCommand(runId, {concierge:true,...})`; assert the subscriber received the three frames in order. (c) a second case: `fetch` resolves `content-type: application/json` → assert the subscriber received nothing and sendCommand returned null (JSON path unchanged).
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend &amp;&amp; npx vitest run src/lib/sseFrame.test.ts src/hooks/useRunStream.test.ts src/providers/RunConnectionProvider.test.tsx &amp;&amp; npx tsc --noEmit</automated>
  </verify>
  <done>A streamed text/event-stream POST response is parsed by the single shared parseSseBlock and fan-out-dispatched to the transcript on both live and completed runs; the JSON and launch paths are unchanged; useRunStream still passes with the extracted parser; tsc clean. RED evidence recorded: before the change, sendCommand returns null without reading the body → the subscriber receives no frames → the ordered-frames assertion fails.</done>
</task>

</tasks>

<risk_audit>
## The biggest risk and how the plan contains it

**Risk: `sendCommand` is a SHARED up-channel used by every send** (plain messages, launch, revision, confirm, concierge). Making it read a streamed body must not break the JSON path or the launch path.
- Containment: branch STRICTLY on `res.headers.get("content-type")`. Only the fresh-Concierge branch (Plan 01) returns `text/event-stream`; all other responses stay `application/json` and take today's exact `return null` / `res.json()` paths. Verified content-negotiated, no concierge literal in the FE. Tests (b)+(c) pin both paths.

**Mid-stream drop / error surfacing (the completed-run correctness question).**
- The durable side-effects live in Plan 01's `_drive()` background task, NOT gated on client consumption — so a dropped POST stream still persists the `chat_reply` row + proposal rows server-side. On the FE, the existing `fetchEvents`-after-send (useRunChat.ts:365-375) re-pulls that durable `chat_reply` and the event_id dedup renders it exactly once; if nothing arrives at all, the li0 45s safety-net (RunChatLane addendum, commit 87f843a4) clears the "generating…" indicator so it never sticks. Net: worst case degrades to today's non-streamed behavior (one late blob), never a stuck spinner or a lost reply.

**Why NOT Option A (the queue) — the completed-run lifecycle audit.** Option B was chosen precisely to avoid `_PIPELINE_QUEUES`. For the record, a completed/failed-run queue would trip all three membership consumers enumerated in Plan 01's objective: the `resume_run_endpoint` overlap mutex (run_commands.py:382), the `stream_run_events` is-live handshake (run_stream.py:281 → useRunStream liveness), and the missing cleanup owner (`_cleanup_pipeline` never fires for a driver-less queue). Option B (this plan) opens NO queue and needs NO SSE re-attach on a completed run — the chunks ride the POST the FE already makes (BUG-013 `AUTO_STREAM_STATUSES` is irrelevant because we never rely on an auto-attached stream).

**Proposals.** Out of scope for the FE by construction: `RUN_CONCIERGE_PROPOSALS` (DashboardLayout.tsx:185) is a `[]` stub — the FE does not consume POST-body proposals today. Plan 01 preserves the server-side drain/disposal verbatim and carries `proposals` on the terminal frame for forward-compat; this plan does not wire them (no scope creep).
</risk_audit>

<invariants>
- **INV-1 / SC-001:** `chat_reply_chunk` is a generic data type; no workflow-name/agent-id literal in the reducer or the transport. `sendCommand` content-negotiates on `text/event-stream`, never on a `concierge` literal.
- **INV-12:** ONE SSE parser (`parseSseBlock`) reused by `useRunStream` and `sendCommand` (no dual parse); the streamed frames reach the transcript through the EXISTING `fanout → subscribersRef → useRunChat.handleFrame` seam and the EXISTING `agent_chunk` accumulation pattern (no third streaming path); FE-1 keeps the terminal `chat_reply` finalize path (`upsertNarratorMessage`) intact.
- **INV-3:** chat is not golden-covered, but nothing here touches the pipeline reducer or the durable `chat_reply` shape — the terminal event stays stable (history/replay/BUG-017/li0 spinner unaffected). The Plan-01 backend goldens stay 10/10.
- **INV-13:** FE-only — the model is never reached from here; the runner seam is untouched.
</invariants>

<verification>
Offline, `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend` (no live backend/Bedrock, do not touch :3000/:8000):

1. `npx vitest run src/hooks/useRunChat.test.ts src/lib/sseFrame.test.ts src/hooks/useRunStream.test.ts src/providers/RunConnectionProvider.test.tsx` — all green (FE-1 + FE-2 behavior; the extracted parser leaves useRunStream green).
2. `npx vitest run src/components/chat src/providers src/hooks` — no existing chat/provider/hook test broken (the li0 chat-lane suite, 152 across 14 files, stays green).
3. `npx tsc --noEmit` — exit 0, no new type errors.

## Live re-proof (orchestrator-owned — NOT an executor step)
On real Bedrock (feat/ui-2, live :8000 + :3000, QA login), attach the run screen and observe the Concierge reply arriving as INCREMENTAL `chat_reply_chunk` frames (text grows token-by-token; the typing indicator yields on the first chunk), on BOTH:
  (a) a LIVE/running run — ask "what's the status" mid-run; and
  (b) a COMPLETED run opened from history — ask "what's the status" after it settles.
Confirm the durable `chat_reply` persists (reopen the run → one clean assistant turn), proposals still surface behind the confirm chip where applicable, and a forced mid-stream drop degrades to the durable reply (no stuck spinner). Capture screenshots per the fidelity method.
</verification>

<success_criteria>
- Concierge reply text grows incrementally in one assistant bubble; the terminal `chat_reply` finalizes it with no duplicate turn; the li0 indicator hides on the first chunk.
- Streaming works on live AND completed runs via the POST body — no SSE re-attach, no `_PIPELINE_QUEUES`.
- The JSON `/messages` path and the launch path are unchanged; one shared `parseSseBlock`; `useRunStream` unaffected.
- vitest suites green, `tsc --noEmit` clean, no existing chat/provider test broken.
</success_criteria>

<output>
Create `.planning/quick/260719-m0o-stream-the-concierge-reply-converse-astr/02-SUMMARY.md` when done. Record: the `upsertStreamingReply` shape, the parseSseBlock extraction + the sendCommand content-type branch, the RED evidence for both tasks, and confirmation that useRunStream + the chat/provider suites + tsc stayed green.
</output>
