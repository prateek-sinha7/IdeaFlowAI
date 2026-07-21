# Grounded context — streaming chat scroll glitches (FE-only)

**Task:** 260719-nwe. Fix TWO user-reported glitches in the run-screen left chat lane that
appeared when the Concierge reply started streaming (quick 260719-m0o, commits e4fc6dbf/ec1847c3):

1. **Footer glitch** — "the bottom run summary shows glitches as the stream makes the scroll."
2. **Question disappears** — "my message got disappeared and only llm message i can see."

Both are ONE root cause. FE-only. NOT golden-covered (chat is not in the characterization
goldens, INV-3). No backend change. No new dependency.

---

## Root cause (verified by the orchestrator via live DOM check + code read)

`frontend/src/components/chat/ChatPanel.tsx`, the auto-scroll effect (currently lines 116-121):

```tsx
// Auto-scroll to bottom during streaming and when new messages arrive.
useEffect(() => {
  const end = messagesEndRef.current;
  if (end && typeof end.scrollIntoView === "function") {
    end.scrollIntoView({ behavior: "smooth" });
  }
}, [messages, streamingContent, isStreaming]);
```

- It fires on **every** `[messages, streamingContent, isStreaming]` change. During a streamed
  Concierge reply the assistant message content grows chunk-by-chunk (~192 chunks live-observed),
  so this effect runs ~192 times in a couple of seconds.
- Each run does `scrollIntoView({ behavior: "smooth" })`. ~192 stacked *smooth* scroll
  animations, each interrupting the last → visible jank on whatever sits at the foot, i.e. the
  **Run-summary card** (`transcriptFooter`, ChatPanel.tsx:377). **← glitch #1.**
- The anchor `messagesEndRef` (ChatPanel.tsx:380) sits **below** `transcriptFooter`, so every
  scroll goes to the very bottom (past the footer). The user's own question is pushed up and off
  the top of the lane. **← glitch #2.**

**Verified NOT a deletion.** Orchestrator live DOM check: after the reply renders, the user's
message text is still present in the DOM (1 occurrence) and becomes visible again when the lane
is scrolled to the top. So the message is scrolled off-screen, never removed. Do NOT touch the
transcript/reducer logic in `useRunChat.ts` — the bug is purely scroll behavior in ChatPanel.

## Structure facts (verified — do not re-derive)

- Scroll container: `scrollContainerRef` (ChatPanel.tsx:112) is attached to the
  `flex-1 overflow-y-auto` div (ChatPanel.tsx:216, className at :222). `scrollContainerRef.current`
  IS the scrollable element (has scrollTop/scrollHeight/clientHeight).
- `messagesEndRef` (:111) → `<div ref={messagesEndRef} />` at :380, **after** `{transcriptFooter}`
  (:377). Keep it; it stays the bottom-follow anchor.
- Message rows render via `renderMessage(message, index)` (:140), keyed `key={message.id}` but with
  **no** `data-message-id` attribute → not queryable today. You will add one.
- Virtualization: `useMeasuredVirtualWindow` engages only above `VIRTUALIZE_THRESHOLD` (80) messages
  (:131-137, `isVirtualized` :138). The Concierge chat is far below 80, so the naive effect owns
  scrolling. Your new logic must be correct for the non-virtualized path; the near-bottom fallback
  keeps it safe if virtualization ever engages.
- Props already in scope: `messages` (ChatMessage[] with `.id` and `.role`), `streamingContent`,
  `isStreaming`.
- User-message id: the optimistic user turn is keyed on the client-minted `message_id`
  (useRunChat.ts upsert, id = `data.message_id`) — a plain uuid-ish string, safe inside a quoted
  attribute selector. The streaming assistant bubble is keyed `chat-reply:{message_id}` (different id).

---

## Target behavior (implement exactly this)

Standard streaming-chat scroll: **pin the question near the top on a new turn; only follow the
bottom when the user is already there; never use smooth during streaming.**

1. **New user turn → pin the question to the top.** When the newest `role:"user"` message has an id
   we haven't handled yet, scroll THAT message to the top of the container
   (`scrollIntoView({ behavior: "smooth", block: "start" })`) and mark follow OFF. The question then
   stays visible while the reply streams in below it (fixes glitch #2). For the Concierge's short
   replies the question + full reply both fit and both stay visible.
2. **Streaming growth / narrator updates → follow bottom ONLY if the user is already near it.** Track
   a `stickToBottom` boolean via a scroll listener on `scrollContainerRef` (near-bottom = distance
   from bottom < 120px). If true, scroll `messagesEndRef` with **`behavior: "auto"`** (instant — no
   stacked animations, fixes glitch #1). If false (user scrolled up, or we just pinned a new turn),
   do nothing — never yank them.
3. Initialize `stickToBottom = true` (a fresh lane is at the bottom).

### Exact implementation

Replace the effect at ChatPanel.tsx:114-121 with:

```tsx
const stickToBottomRef = useRef(true);
const handledTurnRef = useRef<string | null>(null);

// Follow-intent: the user is "following" only while near the bottom. A single
// scroll up flips this off so streaming never yanks them back down.
useEffect(() => {
  const container = scrollContainerRef.current;
  if (!container) return;
  const onScroll = () => {
    const dist =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    stickToBottomRef.current = dist < 120;
  };
  container.addEventListener("scroll", onScroll, { passive: true });
  return () => container.removeEventListener("scroll", onScroll);
}, []);

// Auto-scroll: pin a new question to the top; otherwise follow the bottom only
// when the user is already there. Instant (never smooth) during streaming so
// rapid chunks don't stack animations (which janks the Run-summary footer).
useEffect(() => {
  const container = scrollContainerRef.current;
  const end = messagesEndRef.current;
  if (!container) return;

  let lastUser: ChatMessage | undefined;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") {
      lastUser = messages[i];
      break;
    }
  }
  const turnId = lastUser?.id ?? null;

  if (turnId && turnId !== handledTurnRef.current) {
    handledTurnRef.current = turnId;
    const node = container.querySelector(
      `[data-message-id="${turnId}"]`,
    );
    if (node instanceof HTMLElement && typeof node.scrollIntoView === "function") {
      node.scrollIntoView({ behavior: "smooth", block: "start" });
      stickToBottomRef.current = false; // let the reply grow below the pinned question
      return;
    }
  }

  if (
    stickToBottomRef.current &&
    end &&
    typeof end.scrollIntoView === "function"
  ) {
    end.scrollIntoView({ behavior: "auto" });
  }
}, [messages, streamingContent, isStreaming]);
```

Notes:
- `scrollContainerRef` / `messagesEndRef` / `useRef` are already imported and in scope. Reuse them.
- The reverse-scan for the last user message avoids allocating a reversed copy each render.
- The quoted attribute selector is safe for uuid-ish ids; no `CSS.escape` needed. Guard
  `scrollIntoView` existence (jsdom has no scrollIntoView — the effect must not throw under vitest).

### Make rows queryable (the pin needs it)

In `renderMessage` (ChatPanel.tsx:140+), add `data-message-id={message.id}` to the OUTERMOST
element each branch returns (narrator card / bubble / error banner). Do NOT introduce a new wrapping
`<div>` — that would break `MeasuredItem` height measurement and the layout. Add the attribute to
the existing top-level node of each returned branch. If a branch returns a component that doesn't
forward arbitrary DOM props, add the attribute to the nearest DOM element it wraps, or wrap it in a
`display:contents` span only as a last resort (prefer the existing node).

---

## Tests

Realistic note: jsdom stubs `scrollIntoView` as a no-op and does not lay out scroll geometry, so a
vitest cannot prove the *visual* scroll. Do the achievable RED→GREEN + rely on the orchestrator's
live screenshot proof:

- **Vitest (ChatPanel):** add/extend a test that (a) renders with a `role:"user"` message then flips
  in a streaming assistant message, and asserts the effect does not throw and that each rendered row
  exposes `data-message-id` matching its message id (query `[data-message-id]` count === messages
  length). This locks in the queryable-rows change. If you can spy on `Element.prototype.scrollIntoView`,
  assert it is called with `block:"start"` on the new user turn and with `behavior:"auto"` (NOT
  "smooth") on a subsequent streaming update — that is the regression guard for both glitches.
- Run the existing ChatPanel/RunChatLane suites — must stay green.
- The orchestrator owns the live proof (send a Concierge ask on a completed run, screenshot: question
  stays visible at top, reply streams below, footer does not jitter).

## Constraints (verbatim — always in force)

- Branch **feat/ui-2** ONLY. NEVER main/dev/staging. NEVER push. NEVER `git stash`.
- NO commit trailer (no Co-Authored-By / Claude-Session lines).
- FE-only. Do NOT touch backend, the reducer (`useRunChat.ts`), or the SSE transport.
- Worktrees OFF → sequential. Frontend tests run from the `frontend/` dir (cwd-sensitive), not
  `--root frontend` from repo root.
- Do NOT run live Bedrock — the orchestrator owns live proofs. Verify offline (vitest + `npm run build`
  / typecheck + lint).
- Commit atomically with a clear message; update the quick-task STATE table (STATE.md may not persist
  progress here — do not fight it).
