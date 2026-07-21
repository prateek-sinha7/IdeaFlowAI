# Grounded spec — Issue 2 part 2: "reading…" indicator + useSmoothText test (FE-only)

**Task:** 260719-rqo (continuation). Branch `feat/ui-2`. **FRONTEND-ONLY. No backend change, no restart.**
Part 1 (the typewriter, `useSmoothText`) is already committed (`312271aa`) and live-proven. This is the
remaining polish for Issue 2, which the user approved as "smooth typewriter + reading… indicator".

## Context — what's already true (verified by the orchestrator + investigation agent)
- The Concierge reply STREAMS as `chat_reply_chunk` frames → `useRunChat.upsertStreamingReply` grows the
  assistant bubble's `message.content` (bubble id `chat-reply:{message_id}`). The terminal `chat_reply`
  frame (`upsertNarratorMessage`) finalizes the SAME bubble.
- Live-measured cadence: the reply emits ~59 chars, then FREEZES for ~1.3s (the Concierge calls a READ
  tool — `read_events`/`list_refs` — to answer), then streams the answer. During that freeze NO
  `chat_reply_chunk` flows, so the reply looks stuck. The typewriter (part 1) smooths the bursts but has
  nothing to reveal during the freeze — so the freeze still reads as dead air. THIS TASK fills it.
- Key insight that makes this FE-only: a mid-reply freeze on the Concierge path is ALWAYS a read-tool
  call (preamble → read run data → answer). So the FE can show "reading run data…" during a chunk-gap
  WITHOUT the backend telling it — the wording is accurate for this path.

## Requirement A — a "reading run data…" indicator during the mid-reply freeze
When a Concierge reply is actively streaming but its text has NOT grown for a short window (~700ms) and
the reply has not finalized, show a subtle "reading run data…" indicator (reuse the existing
`TypingIndicator` animation with a label, or a small inline status line in/under the streaming bubble).
Clear it the instant more text arrives OR the reply finalizes.

Precise lifecycle (implement in the FE — you choose the cleanest home; `useRunChat` sees the frames,
`RunChatLane`/`ChatPanel` render):
1. A reply is "actively streaming" from the first `chat_reply_chunk` for a `message_id` until its
   terminal `chat_reply` lands (or an error terminal). Track this — e.g. in `useRunChat`, record the
   active streaming reply id + a `lastChunkAt` timestamp on each `chat_reply_chunk`, and clear it on the
   terminal `chat_reply`. Expose what the lane needs (an id + lastChunkAt, or a derived `isReading` hint).
2. In the lane, if a reply is actively streaming AND `Date.now() - lastChunkAt > 700` AND the reply has
   not finalized → render the "reading run data…" indicator. A short interval/timeout drives the re-check
   (the gap is detected by elapsed time, so you need a timer, not just a render).
3. Hide it as soon as the next chunk grows the content or the terminal finalizes. Never show it before
   the first chunk (that window is already covered by the existing send spinner / `replyPending` in
   `RunChatLane.tsx`) and never after the reply is done.
4. Do NOT double up with the existing pre-reply typing indicator (ChatPanel.tsx renders a
   `<TypingIndicator/>` when `isStreaming && last msg not assistant`). The reading indicator is a SEPARATE,
   mid-reply state.

Guardrails:
- Timers must be cleaned up on unmount / run-switch (no leaked intervals). Guard for the completed-run
  vs live-run lane the same way the existing code does.
- Keep it GENERIC (SC-001): no workflow-name/agent-id literal. "reading run data…" is a fixed UI string,
  fine.
- Purely additive to the transcript rendering — do NOT change `useSmoothText`, the reducer's message
  shape, the SSE transport, or anything backend.

## Requirement B — a vitest for `useSmoothText` (guard part 1)
`frontend/src/hooks/useSmoothText.ts` currently has no dedicated test. Add
`frontend/src/hooks/useSmoothText.test.ts` (renderHook from @testing-library/react) covering:
- Static target (never grows) → returns the target verbatim (no animation, no throw). This holds under
  jsdom whether or not requestAnimationFrame exists.
- `enabled=false` → returns the target verbatim even if it "grows" across rerenders.
- Growth WITH a mocked requestAnimationFrame (e.g. `vi.stubGlobal("requestAnimationFrame", cb => { cb(0);
  return 1 })` so a frame runs synchronously, plus `cancelAnimationFrame`): after rerendering with a
  longer target and flushing act(), the shown text is a PREFIX of the target and advances toward it (it
  reveals incrementally, not all-at-once on the first frame for a large delta — a single frame reveals
  ~1/6 of the buffer). Assert `target.startsWith(shown)` and `shown.length` is between the old length and
  the full length after one frame. Keep the assertions robust to the exact rate (assert bounds, not exact
  counts).

## Verify offline (report the actual output)
- Run vitest FROM `frontend/` (cwd-sensitive; NOT `--root frontend` from repo root): the new
  `useSmoothText.test.ts` + the ChatPanel/RunChatLane/useRunChat suites must be green. Show the counts.
- `npx tsc --noEmit` → 0. `npx eslint` on every file you touch → 0 errors (0 warnings preferred). NOTE:
  this repo's react-hooks lint is strict — do NOT write a ref during render, and do NOT call setState
  synchronously in an effect body (only inside callbacks/timers). See `useSmoothText.ts` for the pattern.
- Do NOT run live Bedrock, do NOT start/stop the backend (the orchestrator owns the running backend on
  :8000 and the live proof) or run Playwright. The orchestrator will live-verify the indicator.

## Constraints (verbatim)
Branch feat/ui-2 ONLY. NEVER push. NEVER `git stash`. NO commit trailer. FE-only. Worktrees OFF →
sequential. Commit atomically (one focused commit) with a clear conventional message. If STATE.md
progress resets, don't fight it.

## Output contract
Report: the commit SHA; files changed + line counts; the literal vitest summary; tsc + eslint results;
and confirm no push / no trailer / no live Bedrock / stayed on feat/ui-2. If you deviated from this spec
(e.g. chose a different home for the reading-state), say precisely what and why.
