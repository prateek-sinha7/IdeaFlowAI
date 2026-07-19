# Quick 260719-li0 — Concierge chat lane: show a thinking indicator

## One-liner
Give `RunChatLane` its own lane-local "reply pending" flag so a settled-run
Concierge ASK surfaces the EXISTING `TypingIndicator` while its blocking backend
reply is in flight, then auto-hides it the instant the `chat_reply` renders —
FE-only, viewed-run-scoped, RED->GREEN, atomic commit `7dbf2d9d` on `feat/ui-2`.

## The problem (verified)
On the run screen the left chat lane answered a Concierge ASK ("what's the
status") via a BLOCKING backend round-trip (`POST /api/runs/{id}/messages` ->
`concierge.converse` -> `runner.run()`, non-streaming) that emits ONE late
`chat_reply` after 2-8s — and showed NOTHING meanwhile. `ChatPanel` already
renders a `TypingIndicator`, gated on `isStreaming` (`ChatPanel.tsx:369-372`),
but `RunChatLane`'s `isStreaming` prop is bound by `DashboardLayout` to the
PIPELINE stream, which is `false` on a settled/idle run — so the indicator never
fired for a Concierge ask.

## The fix (as-designed — lane-local reply-in-flight state)
`frontend/src/components/chat/RunChatLane.tsx`:

1. State — `const [replyPending, setReplyPending] = useState(false);` added
   right after the `heldRefinement` state (~:775).
2. Set it on the ASK branch ONLY — in `handleFreeText`, the
   `runState === "complete" && classifyFreeText(text) === "ask"` path (the
   `sendMessage(text, attachments, { concierge: true })` call): `setReplyPending(true)`
   immediately before the send. The plain-`sendMessage` and revise/held-refinement
   paths are untouched (they already have the pipeline stream / confirm chip).
3. Feed the existing indicator — the `<ChatPanel ...>` render now passes
   `isStreaming={isStreaming || replyPending}` (was `isStreaming`). ChatPanel's
   existing gate (`isStreaming && (messages.length === 0 || last.role !== "assistant")`)
   shows the indicator while pending and AUTO-hides it the instant the assistant
   `chat_reply` is the tail — so a stuck spinner is impossible even if the flag
   lingers.

`frontend/src/components/chat/TypingIndicator.tsx`:
- Added a stable `data-testid="typing-indicator"` on the root (minimal,
  backward-compatible — nothing queried it before).

### sendMessage is NOT thenable -> cleared by the transcript, not a promise
The plan's preferred `.finally` form does not apply: `useRunChat.sendMessage`
returns the client `message_id` (a `string`) SYNCHRONOUSLY; its up-channel POST
is fire-and-forget internally (`useRunChat.ts:365` `void (async () => ...)()`), and
the `RunChatLane` prop type is `(...) => void`. So per the plan's stated fallback
the flag is cleared by a transcript `useEffect`:

    useEffect(() => {
      if (!replyPending) return;
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") setReplyPending(false);
    }, [messages, replyPending]);

When the late `chat_reply` lands as an assistant tail, both this effect AND the
ChatPanel gate drop the indicator.

### Run-binding guard (which case applied)
`RunChatLane` does NOT remount per run — `DashboardLayout` mounts it with NO
`key` and NO `runId` prop (`DashboardLayout.tsx:1758-1765`); it persists across
run switches and only the `messages`/`pipelineState` props swap. So a run switch
BEFORE the reply lands could leak a stale spinner (the BUG-001/005 run-binding
class). Added a reset effect keyed on the viewed run identity — the SAME
`pipelineState.pipelineRunId` signal the parent uses to detect a genuinely new
run (`DashboardLayout.tsx:358-360`):

    const viewedRunId = pipelineState?.pipelineRunId;
    useEffect(() => { setReplyPending(false); }, [viewedRunId]);

### Reused isStreaming vs. a dedicated typing prop
Reused `isStreaming` (`isStreaming || replyPending`) rather than threading a
dedicated typing-only prop through ChatPanel. `isStreaming` also flows to
`ChatInput` (`ChatPanel.tsx:388`), so this disables the composer while a
Concierge reply is pending — which is DESIRABLE (prevents double-sends) and is
the smaller, cleaner diff. No dedicated prop was warranted.

## The test (RED->GREEN, vitest — component-level)
`frontend/src/components/chat/RunChatLane.test.tsx` — 3 new tests co-located with
the existing chat-lane suite, driving the REAL `handleFreeText` concierge path
(type an ask on a `runState="complete"` lane, click send):

1. `settled-run ASK shows the TypingIndicator while the Concierge reply is pending`
2. `the ASK TypingIndicator auto-hides once the assistant chat_reply is the tail`
3. `a pending ASK indicator does NOT leak across a viewed-run switch (run-binding guard)`

RED evidence: with the core change reverted (`isStreaming || replyPending` ->
`isStreaming`), all 3 fail with `Unable to find an element by:
[data-testid="typing-indicator"]` at the first `getByTestId("typing-indicator")`
assertion — `1 failed | 37 skipped`.

GREEN evidence: after the change, `RunChatLane.test.tsx` -> `Tests 40 passed (40)`.

## Verify (offline)
- `npx tsc --noEmit` (from `frontend/`) -> EXIT 0, no new type errors.
- `npx vitest run src/components/chat/RunChatLane.test.tsx` -> 40 passed.
- `npx vitest run src/components/chat` -> 14 files, 151 passed — no existing
  chat test broken.
- FE-only: NO backend change, NO new event, NO migration. Did not touch the live
  backend (:8000) or the Next dev server (:3000).

## Files
- `frontend/src/components/chat/RunChatLane.tsx` (state + ASK-branch set + reset/clear effects + ChatPanel prop)
- `frontend/src/components/chat/TypingIndicator.tsx` (data-testid)
- `frontend/src/components/chat/RunChatLane.test.tsx` (3 new tests)

## Commit
- `7dbf2d9d` — feat(chat): show a thinking indicator while a Concierge ASK reply is in flight (feat/ui-2, no trailer, NOT pushed)

## Deviations from plan
None material. The plan's preferred `.finally(...)` clear was inapplicable
(`sendMessage` is not thenable — verified) so the plan's own stated fallback
(transcript `useEffect`) was used. Run-switch guard: the "does NOT remount"
case applied -> added the `pipelineRunId`-keyed reset effect.

## Self-Check: PASSED
- Commit `7dbf2d9d` present in git log on `feat/ui-2`.
- All 3 modified files exist and are committed.
