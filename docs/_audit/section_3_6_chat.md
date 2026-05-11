# Phase B Audit — §3.6 Chat & Streaming (W42-W49)

Scope: chat conversation workflow (NOT pipeline). Files audited:
- `frontend/src/components/chat/*` (ChatPanel, ChatInput, MessageBubble, ErrorMessage, TypingIndicator, ProcessSteps, ArtifactCard)
- `frontend/src/hooks/useWebSocket.ts`, `useSpeechRecognition.ts`
- `frontend/src/app/dashboard/page.tsx` (the consumer of chat state)
- `backend/app/api/websocket.py` chat path (lines 271-436, ~723-779)
- `backend/app/agents/orchestrator.py` (chat orchestrator)
- `backend/app/agents/llm_errors.py`, `modes.py`, `base.py`, `discovery.py`

---

## CRITICAL

### C1. **The entire chat conversation UI is dead code — not rendered anywhere**
`frontend/src/components/chat/ChatPanel.tsx:53` is exported but **never imported** outside the chat folder. `frontend/src/components/layout/DashboardLayout.tsx:50-492` renders only `CreationHub`, `LibraryPage`, `WorkflowHistory`, `AccountSettings`, `IdeaInputPage`, `AgentProgressPanel`, `PreviewPanel`, `QuestionnairePanel` — no ChatPanel, no MessageBubble, no ChatInput.

Evidence:
```
$ grep -rn "from.*chat/ChatPanel\|<ChatPanel" frontend/src --include="*.tsx"
(nothing)
```

`frontend/src/components/sidebar/Sidebar.tsx:59` is also exported and unused. `frontend/src/components/chat/MessageBubble.tsx`, `ChatInput.tsx`, `TypingIndicator.tsx`, `ErrorMessage.tsx`, `ProcessSteps.tsx`, `ArtifactCard.tsx` — all rendered only by `ChatPanel`, therefore all dead.

Yet the `dashboard/page.tsx` still maintains `messages`, `isStreaming`, `streamingContent`, `processSteps`, `chatTitleUpdate` state (`page.tsx:25,27,28,35,34`), still handles every WS chat event type (`page.tsx:73-302`), still calls `handleSendMessage`/`handleSendMessageWithMode` (`page.tsx:322-427`), and still forwards all of it to `DashboardLayout` (`page.tsx:578-619`) which ignores it.

This means the entire chat orchestrator pipeline runs server-side every time, billing Bedrock for output that nothing renders. The receive path's W42 (markdown render), W44 (streaming cursor), W47 (history loader), W48 (retry), W49 (TTS/copy/regenerate) are all unreachable in the running app.

Action expected: either re-wire ChatPanel into DashboardLayout (looks like the post-refactor was the workflow-first rewrite from `WORKFLOWS.md:593`), or formally delete the chat UI + WS chat handling. Half-deleting it left a ~30KB dead path in both bundles.

### C2. **Chat orchestrator runs the full 7-phase pipeline on every chat message**
`backend/app/agents/orchestrator.py:293-449` (`AgentOrchestrator.astream_execute`) is the **chat** path entry point, but its body sequentially runs:
- Phase 0 Discovery → Phase 1 Requirements → Phase 2 routing → Phases 3-7 (user_stories / ppt / prototype / ui_design / preview)

For a one-line user message like "hello", the WS handler at `websocket.py:365-373` calls this and the user pays for 5-7 Bedrock LLM calls plus a final `_compile_final_output` JSON dump (`orchestrator.py:441,448`). The discovery agent's system prompt (`discovery.py:5-28`) is explicitly "ask one question at a time", so it returns a *clarifying question*, then the orchestrator ignores that and immediately runs requirements + every selected output phase against the SAME unchanged user_message (`orchestrator.py:271,404`).

Cost impact: per chat message the user is billed for ~5x more LLM time than the chat UI shows (only Phase 0/1 stream visibly; the rest stream into `section: "ppt"` / `"prototype"` etc. which the dashboard routes silently to invisible ref buffers — `page.tsx:120-128`).

There is no early-exit, no token budget, no recognition that "this is a one-off chat reply, not a project initiation". The chat path was never re-scoped after the pipeline path (orchestrator_v2) took over real generation.

### C3. **Mid-stream WebSocket disconnect → assistant message permanently lost**
`websocket.py:363-373` runs `async for stream_msg in orchestrator.astream_execute(...)` in the **receive loop directly** (not in a background task — unlike the pipeline path at `:234-239`). The chunks are buffered into `assistant_chunks` (`:356,372`). The DB-write block is at `:405-436`, AFTER the orchestrator loop completes.

If the client disconnects (or the connection drops) during `async for`, `WebSocketDisconnect` propagates from `websocket.send_json(stream_msg)` (`:373`) → bypasses the `try: ... except AgentConfigurationError / Exception:` siblings (which don't catch WebSocketDisconnect) → bypasses the DB block at `:405-436` → caught by the outer `except WebSocketDisconnect:` at `:438`. Result: the user's message is persisted (`:307-318`) but the assistant's partial answer — possibly thousands of tokens — is never saved. When the user reconnects and opens the same chat, they see only their own message hanging in midair.

The pipeline path (`_handle_pipeline_execution`) handles this correctly via `asyncio.CancelledError` (`:604-648`) and persists partial agent outputs. The chat path has no equivalent.

### C4. **`<!--steps:...-->` marker mechanism is double-dead on the chat path**
- Backend: `websocket.py:357` declares `collected_steps: list[dict] = []` and never appends to it. The `if collected_steps:` at `:413` is therefore always false, and `<!--steps:JSON-->` is never written to the DB (despite the comment at `:411` claiming "Embed steps as a hidden marker at the start of content"). Confirmed by `grep "collected_steps\." websocket.py` returning only the init + the dead-branch read.
- Frontend: the regex parser at `dashboard/page.tsx:446-452` runs on every loaded chat message but, because no message will ever start with `<!--steps:`, the `steps` field of `ChatMessage` is forever `undefined`.
- This is the §3.2 finding restated for the chat path: the persisted-step marker pipeline is unreachable from end to end. Combined with C1, this means `<ProcessSteps>` rendered inside `<MessageBubble>` (`MessageBubble.tsx:279-284`) is triple-dead.

The marker mechanism only existed as a bridge from the FE "step" event handler (`page.tsx:283-300`) — which is itself fed by **zero** backend code paths (see C5 below).

### C5. **"step" event type — backend emits zero, frontend handles it**
Phase A flagged this. Confirmed:
```
$ grep -rn '"step"\|type.*step' backend/app/agents backend/app/api/websocket.py
(nothing — no producer)
$ grep -rn 'case "step"' frontend/src
frontend/src/app/dashboard/page.tsx:283:      case "step":
```
The `case "step"` handler at `page.tsx:283-300` mutates `processStepsRef`. That ref is read at `:145` in the `"complete"` handler and stuffed onto an assistant message's `steps` field at `:198`. With no producer, the `steps` field is always empty, the `ProcessStep[]` typing is always satisfied vacuously, and `ProcessSteps` (`chat/ProcessSteps.tsx:97-115`) is never given any input.

Cost of leaving it: 20+ lines of FE state machinery (`processSteps`, `processStepsRef`, `setProcessSteps`, the StreamMessage type union at `types/index.ts:36`) maintained for nothing. Type union `"step"` member dangles in the public WS protocol shape (`types/index.ts:36`).

---

## HIGH

### H1. **Title generation blocks chat response start by one full LLM round-trip**
`websocket.py:323-353`: when `needs_title` is true, the WS handler awaits `title_agent.run(content)` (`:333`) BEFORE entering the orchestrator stream loop at `:363`. This is a non-streaming Bedrock `ainvoke` — typical 800-2500 ms latency. The user sees `isStreaming=true` from `page.tsx:353,406` and the `TypingIndicator` (when ChatPanel rendered) but no streaming text for the duration.

The 3 trigger conditions: `chat_session.title in ("New Chat", "")` OR `chat_session.title == content[:50]` (`:317`). The third branch (`content[:50]` match) catches an edge: when frontend auto-creates a chat with `createChat(currentToken, content.slice(0, 50))` (`page.tsx:334,388`), the title is the first 50 chars. The second user-message therefore also satisfies `needs_title` and re-triggers title generation — even though the title has already been replaced once. This redoubles cost for every chat created via the auto-create path until either: (a) the title agent rewrites the title to something OTHER than the user's first message's first 50 chars, or (b) the user manually renames. Best case: every 2nd-message-of-chat costs an extra title LLM call.

### H2. **In-flight chat cannot be cancelled**
The pipeline path supports `cancel_pipeline` (`websocket.py:243-262`) because it runs in `current_pipeline_task` (`:234`). The chat path runs `orchestrator.astream_execute` inline in the receive loop (`:365`), so:
- The receive loop is blocked on the async-for during a chat — no further messages dequeue
- There's no `cancel_chat` message type (`grep -n "cancel_chat" websocket.py` returns nothing)
- The user has no way to stop a hanging Bedrock response except by closing the tab (which triggers C3 — losing the message entirely)

A chat that hits a slow Bedrock model can consume several minutes with no cancel affordance.

### H3. **Per-phase errors in chat orchestrator each emit a separate `error` event**
`orchestrator.py:341-351, 373-383, 427-437` each yield an `{type: "error"}` envelope on phase-level exceptions. The orchestrator then continues to the next phase. The dashboard handler at `page.tsx:223-255` reacts to every error event by appending a `<ErrorMessage>` to `messages` and setting `isStreaming=false`.

Two consequences:
- Multiple consecutive `<ErrorMessage>` bubbles appear if multiple phases fail
- `isStreaming` is set to false on the FIRST error, but the orchestrator keeps streaming subsequent phases — `stream` events arrive but `isLastAssistant` (`ChatPanel.tsx:196-199`) is now false because a non-assistant ErrorMessage was appended, so streaming text routes to nothing.

The retry button (`ChatPanel.tsx:235-247`) walks back to the previous user message — works correctly for the first error but each subsequent error has its own retry button that *also* walks back to the same user message; clicking either re-fires the same request.

### H4. **No infinite-retry guard on the W48 retry pattern**
`ChatPanel.tsx:235-247`: clicking "Try Again" calls `onSendMessage(messages[i].content)` for the previous user message. There is no retry counter, no exponential backoff, and no detection that the same prompt has already failed N times. A consistently-failing prompt + an aggressive user = unbounded Bedrock retries (each running the C2 7-phase pipeline). Combined with C2 this is a 7× cost amplifier.

The retry also re-creates a new user `ChatMessage` (`page.tsx:344-351`) so the message thread grows with every retry. After 5 retries on the same prompt: 5 duplicate user messages + 5 error bubbles.

### H5. **WS reconnect drops the in-flight assistant message and the FE never tells the BE**
`useWebSocket.ts:145-158`: on close (non-4001), exponential backoff retry, max 5 attempts. After reconnect:
- The new WS connection has no association with the previous chat in flight
- No "resume" envelope sent to BE
- Any chunks that arrived between the disconnect and the FE realizing it are lost (`onmessage` only fires for live messages; nothing buffered)
- The BE side already lost the assistant message per C3
- `streamingContent` retains the partial text on the FE (`page.tsx:28`), `isStreaming` is never explicitly reset on disconnect — the `TypingIndicator` keeps spinning forever until the next user action.

### H6. **Title generation: no DB transaction over the cross-session window**
`websocket.py:307-344` uses three separate sessions: `db` for user_msg+last_activity (`:307-318`), implicit no-db block during `title_agent.run` (`:323-336`), `db2` for title update (`:337-344`). If the chat_session is deleted by the user (via another tab) between these:
- The user_msg was persisted at `:318` (orphan when chat is deleted; but `delete_chat` at `chats.py:155` deletes messages first so OK)
- The title update at `:341` would silently no-op (`cs is None` at `:340`)
- The orchestrator at `:365` keeps running anyway — wasting LLM budget on a chat that no longer exists
- The final db block at `:405-436` queries the (now-deleted) chat_session and silently no-ops at `:429` — assistant message is also persisted at `:421` (db.add succeeded already) but commit at `:434` happens regardless. Actually: `chat_session = db.query(...).first()` returns None, the `if chat_session:` skips, but `db.commit()` is INSIDE the if at `:434` — so the assistant_msg added at `:421` is **never committed** if chat_session is gone.

That's a partial corruption: user_msg present, assistant_msg lost.

### H7. **Frontend `<!--steps:...-->` regex breaks on `-->` inside JSON**
`page.tsx:446-452`. Regex `/^<!--steps:(.*?)-->/` is non-greedy, anchored. If any `ProcessStep.detail` or `label` ever contains the substring `-->` (e.g. a step labeled "Run --> command"), `JSON.stringify` yields `"Run --> command"` and the regex matches at the first `-->`. The capture group is truncated invalid JSON → `JSON.parse` throws → caught silently → but the content cleanup `content.replace(/^<!--steps:.*?-->/, "")` runs anyway and only strips up to the first `-->`, leaving the latter half of the marker visible inline in the rendered message.

Currently inert because C4 means the marker is never written, but the moment someone wires up `collected_steps`, this regex breaks.

### H8. **Mode value from JSON is not type-validated**
`websocket.py:207`: `mode = message_data.get("mode", "default")`. If the client sends `{"mode": {}}` or `{"mode": ["thinking"]}`, `mode` becomes a dict/list. Then `get_mode_prompt(mode)` at `:361` calls `CHAT_MODES.get(mode, "")` (`modes.py:48`) which raises `TypeError: unhashable type: 'dict'` for dict, or returns `""` for list (lookup miss). Dict path crashes the chat handler; the outer `except Exception:` at `:451` closes the WS with code 1011 ("Internal server error"). A malicious or buggy client can disconnect itself by sending the wrong mode shape.

### H9. **Chat session list and message history have no pagination**
- `chats.py:74-89` (`GET /api/chats`): returns ALL chat sessions for a user, no `limit`/`offset`. The FE has no pagination either.
- `chats.py:92-129` (`GET /api/chats/{id}`): returns ALL messages in a session in one response. For a chat with hundreds of messages, this is a single multi-MB JSON.
- `dashboard/page.tsx:441-462`: loads all messages into state with no virtualization. Combined with the `<!--steps:...-->` regex parse on every message (`:446`), a long history becomes an N-multiplied parse pass.
- No search within a session is implemented.

### H10. **W47 history reload re-renders entire ReactMarkdown tree per message — no memoization safeguard**
`MessageBubble.tsx:96-101` uses `useMemo` keyed on `displayContent` and `isAssistant`, but `displayContent` (`:90-93`) is recomputed every render. The streaming-cursor className change on `isStreaming` (`:321`) forces a re-render of the parent which re-renders `ReactMarkdown` (`:322`) on every chunk during streaming. For long messages this becomes noticeable jank (large markdown trees re-parsed token-by-token).

When ChatPanel is eventually rewired (C1), expect ~50ms jank per chunk on multi-paragraph responses with code blocks or tables.

### H11. **No token usage tracking despite Bedrock providing it**
`langchain_aws.ChatBedrockConverse` returns `usage_metadata` on the final chunk (input_tokens, output_tokens, total_tokens). `base.py:170-176` (`astream`) consumes chunks via `_extract_text` (`:107-132`) which only pulls text blocks; usage metadata on the final AIMessageChunk is discarded. Grep confirms no `usage_metadata`/`input_tokens`/`output_tokens` anywhere in `backend/app`. For a Bedrock-billed product, this is a cost-observability gap — there's no way to see what a chat costs after the fact, and no rate-limiting handle.

---

## MEDIUM

### M1. **`StreamMessageModel` is exported but never validates outgoing messages**
`backend/app/models/schemas.py:71-77` defines `StreamMessageModel` with `type: Literal["stream", "complete", "error", "phase_start", "phase_end"]`. The actual WS handler sends `title_update`, `questionnaire`, `pipeline_*`, `agent_*`, `workflow_title_update`, `pipeline_cancelled` — none of which would pass this schema's Literal validation. The schema is referenced only in a docstring (`orchestrator.py:308`) and re-exported in `models/__init__.py`. It's stale documentation pretending to be a type contract.

### M2. **`phase_end` without `phase_start` reordering — unhandled**
Both `phase_start` and `phase_end` are handled as no-ops in `dashboard/page.tsx:135-141`. There's no state tracking that depends on their order. So reordering is currently a non-issue, but the events are also useless. If the FE chat UI ever wanted to track active phases, the current zero-handling would be the starting point.

### M3. **`activePreviewSectionRef` carries pipeline-related routing into chat path**
`dashboard/page.tsx:147-148, 178-184`: The "complete" handler uses `activePreviewSectionRef` to attach a `user-stories | ppt | prototype` artifact card to the chat's assistant message. This ref is set by stream events arriving from the chat orchestrator at `:119,124,128`. Because the chat orchestrator runs phases like `ppt` and `prototype` (see C2), an artifact card claiming to be a PPT/prototype is attached to a chat response — but the actual PPT/prototype generation in the chat path is incomplete (it's a single-pass agent, not the multi-agent pipeline). The artifact preview will fail or render half-baked.

### M4. **Speech recognition errors not surfaced to UI**
`useSpeechRecognition.ts:94-99`: on error, only logs to console and sets `isListening=false` (except for `no-speech` which is filtered out). Browser permission errors (`not-allowed`, `service-not-allowed`) are silent to the user — they tap the mic, nothing happens, no toast, no message. The mic button just looks unresponsive.

`ChatInput.tsx:204-217`: `title={!speechSupported ? "Speech recognition not supported" : ...}` only covers the unsupported case, not the denied-permission case.

### M5. **STT transcript completely overwrites textarea content**
`ChatInput.tsx:52`: `useEffect(() => { if (transcript) setValue(transcript); }, [transcript])`. The transcript REPLACES the typed value. If the user types "I want to" then taps mic and says "build an app", the textarea becomes only "build an app" — the typed prefix is lost. Should append, not replace.

### M6. **Title generation: stripping single chars is too aggressive**
`websocket.py:335`: `generated_title.strip().strip('"').strip("'").strip(".")[:60]`. Each `strip(...)` removes the char from both ends — so a Claude response like `"Build the AI...today."` ends up as `Build the AI...today`. But strip() removes ALL leading/trailing matching chars — `'''Build'''` would become `Build`, which is fine, but `"Build "..."Today"` would have all trailing quotes/dots removed including legitimate ones. Mostly cosmetic.

Worse: there's no fallback if the model returns an empty string or only whitespace; the `if generated_title:` at `:336` skips the update silently but `needs_title` was already true. The chat keeps its default "New Chat" title and on the next message will retry. This is benign infinite retry on title gen specifically.

### M7. **`createChat` race in `handleSendMessage` is guarded only by 500ms timeout**
`dashboard/page.tsx:320-376`: `sendingRef` is set immediately and released via `setTimeout(..., 500)` at `:373`. If `createChat` (a network call) takes longer than 500ms and then the user clicks send again before the orchestrator finishes, a new `createChat` will fire — creating a second chat session with the same first message. The auto-create gates only the first message, but a fast double-click before completion is the failure mode.

### M8. **`isStreaming` toggling races: lifecycle**
`dashboard/page.tsx:111,144,224`: `setIsStreaming` is set TRUE in `case "stream"` (line 111), FALSE in `case "complete"` (line 144), FALSE in `case "error"` (line 224). But: the orchestrator first emits `phase_start` (`orchestrator.py:319`) which is a no-op on the FE (`page.tsx:135`), then a `stream` event. So between the user clicking send (which sets isStreaming=true at `:353`) and the first stream event, there's a window where `phase_start` is received but isStreaming stays true via the optimistic update — fine. But: when an error happens DURING streaming, `isStreaming=false` is set but the orchestrator continues. Subsequent `stream` events flip it back to `true` (`:111`). The TypingIndicator (`ChatPanel.tsx:275-279`) flickers off then back on.

### M9. **`message_data.get("mode")` validation in chat orchestrator bypasses pydantic**
The chat path's WS message schema is implicit (`websocket.py:204-207`) — direct dict.get with no Pydantic model wrapping the inbound payload. Compare to typical FastAPI patterns. There's no max content length, no role check (e.g. only "user_message" is valid but other fields like `pipeline_type` are also accepted alongside it).

### M10. **`handleSelectChat` clears preview content when no `final_output` exists, but mid-stream-recovered sessions never get one persisted**
`dashboard/page.tsx:480-484`: if `chatDetail.final_output` is null, preview content (user_stories, ppt, prototype) is cleared. Combined with C3 (assistant message lost on disconnect), reopening a chat that was disconnected mid-stream → user sees only their own message + no preview. Even if the BE somehow got partway through `_compile_final_output`, that path only runs on the `complete` event (`websocket.py:432`), so partial generation is also lost.

---

## LOW

### L1. **Streaming cursor `▊` appears after the entire markdown block, not at the text caret**
`globals.css:99-106`: `.streaming-cursor::after` puts a `▊` glyph as a pseudo-element of the DIV at `MessageBubble.tsx:321`. With markdown content ending in a `<p>`, `<pre>`, `<ul>`, `<table>` (block-level), the cursor renders on a NEW line below the last paragraph, not adjacent to the streaming text. The cursor jumps as new block elements close.

### L2. **`crypto.randomUUID` used without browser-support check**
`dashboard/page.tsx:193,246,345,398`: uses `crypto.randomUUID()` without fallback. Modern browsers support it but Safari < 15.4 and old WebViews don't. The error envelope (`:246`) and the assistant fallback message (`:193`) would fail and the chat handler would silently drop the message.

### L3. **The `case "step"` handler in `dashboard/page.tsx:283-300` is keyed on `id` and `status` which aren't on the StreamMessage `data` type guard**
`if (msg.data && "id" in msg.data && "status" in msg.data)` — the StreamMessage `data` is typed as `FinalOutput | ErrorDetail | ProcessStep | Record<string, unknown>` (`types/index.ts:39`). `"id"` and `"status"` are also on FinalOutput-related and pipeline messages. If anything else with an `id` and a `status` field arrives (which won't happen on chat, but would on pipeline if routing changes), it'd be silently appended to `processSteps`.

### L4. **TypingIndicator visibility logic uses two checks that don't compose**
`ChatPanel.tsx:275-279`:
```
isStreaming && (messages.length === 0 || messages[messages.length - 1].role !== "assistant")
```
Combined with the optimistic user-message append in `handleSendMessage` (`page.tsx:344-351`), the indicator shows DURING streaming-of-first-chunk because last message is user. Good. But the very moment the first stream chunk arrives, the chat orchestrator emits with `section="discovery"` (`orchestrator.py:325`) — `streamingContent` populates, no assistant message exists yet, indicator continues. The check is correct but the comment at `:274` "Typing indicator when streaming but no assistant message yet" is the design intent, not a guarantee — there's no race here, just a confusing nest.

### L5. **`speak()` in MessageBubble does not stop other instances**
`MessageBubble.tsx:131-137`: `useTextToSpeech` is per-component, so each rendered MessageBubble has its own `isSpeaking`. Clicking "read aloud" on message A then on message B starts two utterances simultaneously (browser may queue or overlap, depending on `speechSynthesis` impl).

### L6. **`activeMode` is reset to `"default"` on send, even if send fails**
`ChatInput.tsx:71-72`: `setActiveMode("default")` runs unconditionally after `onSendMessageWithMode(trimmed, activeMode)`. If the underlying `send()` returns false (`useWebSocket.ts:162-169`, WS disconnected), the user's selected mode is silently cleared and they have to reselect it.

### L7. **Title gen is on the critical path; no backoff or skip for chronic Bedrock throttling**
`websocket.py:323-353`: title gen wraps a generic `except Exception` (`:352`) that logs a warning and continues. Good resilience. But every subsequent message in a chat that's still titled "New Chat" will retry title gen. If Bedrock is throttling, every message in every untitled chat retries — there's no negative caching for failed title generation. The title-attempt counter doesn't exist.

### L8. **The "Coming Soon" toast in ChatInput uses a 2.5s timer with no cleanup on unmount**
`ChatInput.tsx:62-64`: the setTimeout for "📎 File uploads coming soon" returns a cleanup, but only if `showComingSoon` was already true. Standard React pattern, but the toast persists if the component unmounts mid-display — minor.

### L9. **`onSelectChat` doesn't clear `messageMode`**
`dashboard/page.tsx:431-490`: clears `streamingContent`, `isStreaming`, `processSteps`. Does NOT reset `currentMode`. If the user was in "thinking" mode in session A and switches to session B, the mode persists and the next message in session B is sent with the previous mode.

### L10. **`onclose` event handler is bound to `null`-out before `close()` is called**
`useWebSocket.ts:58-65`: `cleanup` nulls onopen/onclose/etc. THEN calls `wsRef.current.close()`. The close() call therefore fires no callbacks — the onclose flow's intentional-close handling at `:139-142` only triggers when close is called BEFORE the handler is nulled. The current order means cleanup-driven closes don't go through the intentional-close branch at all; they're invisible. Probably fine but not what the code at `:139` suggests.

### L11. **`stripping` of single quotes etc. in title cleanup eats legitimate openings**
`websocket.py:335`: `generated_title.strip().strip('"').strip("'").strip(".")`. A title like `'Imran's project` (single quote inside) would lose the leading single quote: `Imran's project`. Mostly cosmetic.

### L12. **No `aria-live` region for chat message updates**
A11y: streaming text updates the `MessageBubble` content (`:321-323`) but there's no `aria-live="polite"` to announce updates to screen readers. The "What can I help you with?" greeting is the only labeled element. A screen-reader user gets no narration of streaming reply.

---

## TF concerns (Technical Foundations / Architectural)

### TF1. **Two orchestrators with overlapping logic (W42-W49 vs W33-W41)**
`backend/app/agents/orchestrator.py` (17.4KB, `AgentOrchestrator`) for chat, `backend/app/agents/orchestrator_v2.py` (19.2KB, `WorkflowOrchestrator`) for pipelines. They share:
- Phase-iteration patterns (orchestrator.py:391-438 vs orchestrator_v2 agent loop)
- Skill/agent loading
- LLM error mapping (`llm_errors.py` imported by both)
- Streaming envelope shape conventions (mostly compatible but divergent — chat uses `{type, chunk, section, data}`, pipeline uses `{type, data}` with section hardcoded in WS)

Maintaining two diverging orchestrators with the same Bedrock concerns will rot. Phase A's "structural duplication" flag is real; this is the canonical case.

### TF2. **The chat path's contract is the multi-phase pipeline, which is wrong for chat**
As detailed in C2: the chat orchestrator's design assumes the user is initiating a discovery → requirements → deliverables flow. But the actual user-visible UI for that is **the pipeline path** (CreationHub → IdeaInputPage → AgentProgressPanel → PreviewPanel). The chat path's 7-phase execution exists only because the original v0 design assumed chat WAS the pipeline. The post-refactor split kept the v0 orchestrator on the chat handler. There is no plausible UX where a free-form chat should generate a PPT — that's what `run_pipeline` is for.

Either: (a) replace `AgentOrchestrator.astream_execute` with a thin single-agent chat completion that doesn't run any phases, or (b) delete the chat path entirely (per C1, it's already invisible). Status quo is ~5x Bedrock spend per chat message routed through invisible UI.

### TF3. **No WS-level message framing or sequence numbers**
The protocol is "JSON per send_text", no chunking metadata, no sequence numbers, no resume cookies. The frontend cannot tell:
- If chunks arrived out of order (theoretical but real over flaky networks)
- If chunks were dropped (no acks, no idempotency)
- If a reconnect should resume or restart

For a streaming-first product, this is a fragility floor. Any future work on partial-result restoration (e.g. "you lost connection; here's what we had") needs this primitive.

### TF4. **`StreamMessage` discriminated union has 18 members in one type, no per-type data narrowing**
`types/index.ts:35-40`: `StreamMessage` lists every event type as a union of string literals but `data` is `FinalOutput | ErrorDetail | ProcessStep | Record<string, unknown>` for ALL of them. The result is that `msg.data` is structurally `Record<string, unknown>` in all handlers (`page.tsx:73-302`). Type guards like `"error" in msg.data` (`:230`) and `"questions" in msg.data` (`:277`) are runtime hatch checks because the compile-time type doesn't narrow. A real discriminated-union would catch missing handlers and prevent the C5 "step" gap from existing.

### TF5. **WebSocket auth subprotocol carries the JWT in `Sec-WebSocket-Protocol`**
`useWebSocket.ts:84-98`: the JWT is shipped as `bearer.<jwt>` in the second arg to `new WebSocket()`. This avoids URL leak (good) but means the JWT is in browser dev tools "Frames" panel forever for that WS session. The backend echoes back the **other** subprotocol entry `flowin.v1` (`websocket.py:156-158`), so server side never logs the credential. Client side, the subprotocol is logged by some monitoring tools. Minor compared to `?token=` in URL, but worth knowing.

### TF6. **`final_output` is stored as a JSON-encoded string in a TEXT column**
`websocket.py:433`: `chat_session.final_output = json.dumps(stream_msg["data"])`. The schema (`chats.py:43`) types it as `Optional[str]`. On read, `dashboard/page.tsx:465-479` JSON.parses again. This is a JSON-in-string-in-row pattern. PostgreSQL supports JSONB natively. Storage as TEXT means no indexing, no querying, no validation. Combined with C2 (chat path generates full FinalOutput unnecessarily), every chat message overwrites this with a fresh-generated FinalOutput — so the chat session's `final_output` reflects the LAST message's pipeline output, not the conversation's accumulated state. Stale-by-design.

---

## Summary of file-line references

| ID | Location |
|----|----------|
| C1 | `frontend/src/components/chat/ChatPanel.tsx:53`, `frontend/src/components/layout/DashboardLayout.tsx:50-492` |
| C2 | `backend/app/agents/orchestrator.py:293-449`, `discovery.py:5-28`, `websocket.py:365-373` |
| C3 | `backend/app/api/websocket.py:363-373, 405-436, 438-450` |
| C4 | `backend/app/api/websocket.py:357, 413-415`, `frontend/src/app/dashboard/page.tsx:446-452` |
| C5 | `frontend/src/app/dashboard/page.tsx:283-300`, `frontend/src/types/index.ts:36` |
| H1 | `backend/app/api/websocket.py:317, 323-353` |
| H2 | `backend/app/api/websocket.py:243-262, 365-373` |
| H3 | `backend/app/agents/orchestrator.py:341-351, 373-383, 427-437`, `frontend/src/app/dashboard/page.tsx:223-255, 235-247` |
| H4 | `frontend/src/components/chat/ChatPanel.tsx:235-247` |
| H5 | `frontend/src/hooks/useWebSocket.ts:145-158`, `frontend/src/app/dashboard/page.tsx:28` |
| H6 | `backend/app/api/websocket.py:307-344, 429-434` |
| H7 | `frontend/src/app/dashboard/page.tsx:446-452` |
| H8 | `backend/app/api/websocket.py:207, 361`, `backend/app/agents/modes.py:39-48` |
| H9 | `backend/app/api/chats.py:74-89, 92-129`, `frontend/src/app/dashboard/page.tsx:441-462` |
| H10 | `frontend/src/components/chat/MessageBubble.tsx:90-101, 321-323` |
| H11 | `backend/app/agents/base.py:107-132, 170-176` |
| M1 | `backend/app/models/schemas.py:71-77` |
| M2 | `frontend/src/app/dashboard/page.tsx:135-141` |
| M3 | `frontend/src/app/dashboard/page.tsx:115-128, 147, 178-184` |
| M4 | `frontend/src/hooks/useSpeechRecognition.ts:94-99`, `frontend/src/components/chat/ChatInput.tsx:204-217` |
| M5 | `frontend/src/components/chat/ChatInput.tsx:52` |
| M6 | `backend/app/api/websocket.py:335-344` |
| M7 | `frontend/src/app/dashboard/page.tsx:320-376` |
| M8 | `frontend/src/app/dashboard/page.tsx:111, 144, 224, 353, 406` |
| M9 | `backend/app/api/websocket.py:204-207` |
| M10 | `frontend/src/app/dashboard/page.tsx:480-484`, `backend/app/api/websocket.py:432` |
| L1 | `frontend/src/styles/globals.css:99-106`, `frontend/src/components/chat/MessageBubble.tsx:321` |
| L2 | `frontend/src/app/dashboard/page.tsx:193, 246, 345, 398` |
| L3 | `frontend/src/app/dashboard/page.tsx:283-300`, `frontend/src/types/index.ts:39` |
| L4 | `frontend/src/components/chat/ChatPanel.tsx:275-279` |
| L5 | `frontend/src/components/chat/MessageBubble.tsx:131-137`, `frontend/src/hooks/useTextToSpeech.ts` |
| L6 | `frontend/src/components/chat/ChatInput.tsx:71-72`, `frontend/src/hooks/useWebSocket.ts:162-169` |
| L7 | `backend/app/api/websocket.py:323-353` |
| L8 | `frontend/src/components/chat/ChatInput.tsx:62-64` |
| L9 | `frontend/src/app/dashboard/page.tsx:431-490` |
| L10 | `frontend/src/hooks/useWebSocket.ts:58-65, 139-142` |
| L11 | `backend/app/api/websocket.py:335` |
| L12 | `frontend/src/components/chat/MessageBubble.tsx:321-323` |
| TF1 | `backend/app/agents/orchestrator.py`, `backend/app/agents/orchestrator_v2.py` |
| TF2 | `backend/app/agents/orchestrator.py:293-449` |
| TF3 | `backend/app/api/websocket.py`, `frontend/src/hooks/useWebSocket.ts` |
| TF4 | `frontend/src/types/index.ts:35-40` |
| TF5 | `frontend/src/hooks/useWebSocket.ts:84-98`, `backend/app/api/websocket.py:156-158` |
| TF6 | `backend/app/api/websocket.py:433`, `backend/app/api/chats.py:43`, `frontend/src/app/dashboard/page.tsx:465-479` |
