# Scope — Stream the Concierge reply (left chat lane)

**Status:** SCOPE / design-only (not implemented). Companion to the shipped spinner (quick 260719-li0).
**Author:** orchestrator, 2026-07-19 (grounded in a live code trace).
**One-line:** turn the Concierge's single-blob reply into a live token stream on the run-screen chat lane, reusing the SSE transport + `astream_events` + the `agent_chunk` render path that already exist.

---

## 1. Problem & goal

Today a Concierge "ask" (e.g. "what's the status") on the left lane shows nothing for 2–8 s, then the whole reply appears at once. The **spinner** task (260719-li0) fixes "is anything happening?" with a typing indicator. This task is the bigger UX win: **stream the reply token-by-token** as it generates, and (stretch) surface the Concierge's internal tool-calls as live "state" lines ("reading run status…", "checking events…").

**Goal:** the reply text grows incrementally in the chat bubble as tokens arrive, matching how pipeline agent output already streams on the Steps tab.

---

## 2. Current architecture (as-is, file:line)

**Reply is produced as ONE blob:**
- `app/agents/chat/concierge.py:295` — `answer = await runner.run(user_message)`. `DeepAgentRunner.run()` is the **non-streaming** variant: it blocks until Haiku finishes the entire reply, returns a `str`.
- `converse` returns that string (`concierge.py:266,303`).

**Delivered as ONE event, over a BLOCKING POST:**
- `app/api/run_commands.py:1208` — `answer = await concierge.converse(ctx, body.text)` (the POST handler `post_message` blocks here for the full reply).
- `run_commands.py:1209-1218` — the whole `answer` is written as a single `chat_reply` event via `store.append_event_next_seq(...)`.
- `run_commands.py:1219-1230` — end-of-turn **proposals** (gate/revision confirm chips) are drained AFTER the text and returned in the POST body; the POST returns `{ok, reply:true, proposals, …}` (NOT the text — the text is only in the `chat_reply` event).

**Rendered whole on the FE:**
- The run screen consumes `chat_reply` frames (`frontend/src/app/dashboard/page.tsx:368`) and appends the full text as one assistant turn in `RunChatLane` → `ChatPanel`.
- On a **completed** run the lane is not live-streaming (terminal runs don't auto-attach SSE — the `AUTO_STREAM_STATUSES`/BUG-013 behavior in `RunConnectionProvider.tsx`); the reply is picked up by the awaited POST + a targeted refetch (the BUG-017 fix).

---

## 3. Why it's MEDIUM, not hard — the building blocks already exist

1. **The runner already streams.** `DeepAgentRunner.astream_events()` (`app/agents/deep_agent_runner.py`) is exactly what every pipeline agent uses to emit `agent_chunk`s. `converse` just needs to consume it instead of `runner.run()`.
2. **The down-channel already exists.** `chat_reply` already flows through `append_event_next_seq` → the SSE reader (`app/api/run_stream.py`). Emitting incremental `chat_reply_chunk` events needs no new transport.
3. **The FE already renders streamed chunks.** `dashboard/page.tsx` already appends `agent_chunk` deltas into a growing text block for the Steps tab; the same reducer pattern applies to the chat bubble.
4. **There's a working reference in-repo.** The legacy free-chat `ChatPanel` already streams with a `TypingIndicator` (`ChatPanel.tsx:368-388`, `isStreaming`) — the streaming-render pattern is proven, just not wired to this lane's Concierge turn.

---

## 4. Proposed design

**Backend (the core change):**
- Add a streaming path to the Concierge. `converse` (or a new `converse_stream`) consumes `runner.astream_events(user_message)` and, per text delta, emits a `chat_reply_chunk` event (`{message_id, delta}`) via `append_event_next_seq` under the same owner-scoped store as today. On completion emit a terminal `chat_reply` (the existing type — carries the FINAL full text so replay/history is a single durable turn, and non-streaming clients still work). Proposals drain exactly as now, after the stream.
- **Idempotent + durable:** each chunk is a seq-numbered event (so SSE replay / Last-Event-ID works). The terminal `chat_reply` remains the canonical durable record (chunks can be treated as transient-on-replay, mirroring `agent_chunk` handling), so history/reopen shows one clean assistant turn, not N fragments.

**FE:**
- Handle `chat_reply_chunk` in the same reducer that handles `agent_chunk`: append `delta` to the in-progress assistant turn keyed by `message_id`; the terminal `chat_reply` finalizes it. Reuse the existing chunk-accumulation + the spinner's `replyPending` (hide the typing indicator once the first chunk lands).
- No new component — `ChatPanel` already renders a growing assistant bubble.

**Transport / lifecycle:**
- Keep the POST as the trigger; the reply arrives over SSE (chunks), the POST resolves when the stream completes (carrying proposals). On a **completed** run, hold a short-lived SSE attach for the turn's duration (see wrinkle 3).

---

## 5. Wrinkles / decisions to make (each is a real fork)

1. **POST-blocking vs fire-and-forget.** Cleanest & lowest-risk: keep the POST alive for the turn, emit chunks to SSE *during* converse, resolve the POST at completion with the proposals (matches today's shape; the FE reads text from SSE, proposals from the POST body). Alternative (fire-and-forget: return POST immediately, stream in a background task) needs its own task lifecycle + error surfacing — more moving parts. **Recommend the former.**
2. **End-of-turn proposals.** The gate/revision confirm chips are produced AFTER the text (`run_commands.py:1220`). Streaming the text doesn't change this — proposals still land at completion (POST body or a terminal event). No redesign.
3. **Completed-run lane isn't live (BUG-013).** Terminal runs don't auto-attach SSE (`RunConnectionProvider` `AUTO_STREAM_STATUSES`). Streaming a Concierge reply on a *completed* run needs the lane to hold a short-lived stream for the turn (attach on send, detach on terminal `chat_reply`) — or a chunk-polling fallback. This is the main FE lifecycle work; get it right or the stream only works on live runs.
4. **"State" messages (the stretch goal).** The Concierge does READ tool-calls inside the runner (`concierge.py:283` read tools). `astream_events` also yields `tool_call`/`tool_result` — emit those as lightweight `chat_status` lines ("reading run status…") to get the richer activity feed the user asked about. Optional; do text-streaming first.
5. **Not golden-covered.** Chat is NOT in the characterization goldens (INV-3 asserts pipeline deliverable bytes + the event multiset, not chat). So this path is freer to change than the pipeline — but still keep the `chat_reply` terminal event stable (history/replay + the spinner + BUG-017 refetch depend on it).
6. **Caching/cost.** P26 prompt-caching is inherited by the Concierge runner; streaming doesn't change token accounting, but confirm the chunk emit doesn't double-count usage.

---

## 6. Task breakdown (suggested)

- **BE-1** `converse` streaming: consume `astream_events`, emit `chat_reply_chunk` per delta + terminal `chat_reply` (concierge.py + run_commands.py:1208-1218). Keep proposals drain.
- **BE-2** event type: register `chat_reply_chunk` (+ optional `chat_status`) — additive, no new transport.
- **FE-1** reducer: handle `chat_reply_chunk` (append by `message_id`) + finalize on `chat_reply`; reuse the `agent_chunk` accumulation in `dashboard/page.tsx`.
- **FE-2** completed-run lifecycle: short-lived SSE attach for the turn on a terminal run (wrinkle 3).
- **FE-3** (stretch) render `chat_status` lines as inline activity.
- **Tests:** BE unit (chunks emitted in order + terminal event carries full text); FE reducer test (chunks accumulate → one turn); a mocked-SSE Playwright pass. INV-3 goldens unaffected (assert them anyway). Live re-proof on real Bedrock (orchestrator).

---

## 7. Effort & sequencing

- **Text streaming (BE-1/BE-2 + FE-1 + FE-2):** ~1–3 days. BE-1 and FE-1 are small (the machinery exists); FE-2 (completed-run lifecycle) is the trickiest piece.
- **State messages (FE-3 + the tool-call emit):** +0.5–1 day, optional.
- **Sequencing:** ship the spinner (done, 260719-li0) → text streaming → state messages. Each is independently shippable.

## 8. Out of scope
- The legacy free-chat `user_message`/`AgentOrchestrator` path (separate subsystem, mid-migration — see backend/CLAUDE.md "The free-chat path").
- Any change to the pipeline agent stream (this is the Concierge chat turn only).
- Streaming the deliverable/preview (unrelated).
