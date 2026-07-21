# Grounded spec — footer jitter (Run-summary card oscillates during a streamed reply). FE-only.

**Task:** 260719-rqo (continuation). Branch `feat/ui-2`. FRONTEND-ONLY. No backend, no restart.
Root-caused by a deep investigation agent + the orchestrator's live telemetry — CONFIRMED, mechanism fully
traced. This is a residual regression introduced by the typewriter (commit `312271aa`).

## Symptom + measured ground truth
The "Run summary" card pinned at the foot of the chat transcript JITTERS (oscillates up/down) while a
Concierge reply streams. Orchestrator live-measured the card's viewport-Y every 70ms during one reply:
**31 up/down direction reversals, up to 57px per jump**; the Y drifts DOWN (748→756→782→800) then SNAPS
back UP (→748), repeatedly.

## Root cause (CONFIRMED — do not re-investigate, implement the fix)
A two-clock scroll desync. The reply's RENDERED height grows on the **rAF typewriter clock**
(`useSmoothText` → `setShown` inside `MessageBubble`, added by 312271aa), but the auto-scroll "follow"
only fires on the **chunk clock** (`messages` updates). Between chunks the content grows unfollowed
(footer drifts down); each chunk fires one `scrollIntoView` that re-pins the bottom (footer snaps up).
- `ChatPanel.tsx` follow effect currently (VERIFIED line numbers):
  - `:139` the effect; `:141` scrollIntoView guard; `:155-159` the NEW-USER-TURN re-arm branch
    (force `scrollIntoView({behavior:"auto"})` + `stickToBottomRef.current = true`, then `return`);
    `:163-165` the CHUNK-FOLLOW branch (`if (stickToBottomRef.current) end.scrollIntoView({behavior:"auto"})`);
    `:166` deps `[messages, streamingContent, isStreaming]`.
  - `messagesEndRef` (`:426`) sits BELOW `{transcriptFooter}` (`:423`) inside the content wrapper.
- The typewriter's `setShown` is internal to `MessageBubble` → it does NOT change `messages` /
  `streamingContent` / `isStreaming`, so the follow effect does NOT fire on typewriter frames.

## The fix (RECOMMENDED — a ResizeObserver that follows the RENDERED height)
Drive continuous following off the actual rendered content height so chunk-growth AND typewriter-growth
pin the bottom through ONE path (no between-chunk drift → no snap).

In `frontend/src/components/chat/ChatPanel.tsx`:

1. Add a content ref next to the existing refs (near `:112-115`):
   ```ts
   const scrollContentRef = useRef<HTMLDivElement>(null);
   ```
2. Attach it to the OUTER transcript content wrapper — the `<div className="mx-auto max-w-4xl">` at
   **`:383`** (this wrapper contains the messages, the `{transcriptFooter}` and the `messagesEndRef`
   anchor, verified — so its height grows on every reveal):
   ```tsx
   <div ref={scrollContentRef} className="mx-auto max-w-4xl">
   ```
   (Attach ONLY to the `:383` wrapper — NOT the inner `:409` ProcessSteps wrapper.)
3. Add a ResizeObserver effect (mirror the guarded RO idiom already in this file at `~:58-64`):
   ```ts
   useEffect(() => {
     const content = scrollContentRef.current;
     const container = scrollContainerRef.current;
     if (!content || !container || typeof ResizeObserver === "undefined") return;
     const ro = new ResizeObserver(() => {
       // Follow the rendered height: pin the bottom on ANY content-height change
       // (chunk OR typewriter frame), but only while the user is following.
       if (stickToBottomRef.current) {
         container.scrollTop = container.scrollHeight;
       }
     });
     ro.observe(content);
     return () => ro.disconnect();
   }, [showGreeting]);
   ```
   (`showGreeting` is already computed at `:187` — re-attach when the wrapper mounts. In a run lane
   `hideComposer` makes `showGreeting` always false, so it attaches on mount.)
4. DELETE the now-superseded chunk-follow branch (`:163-165`) — the RO owns continuous following (no
   dual follow paths, INV-12). KEEP the new-user-turn re-arm branch (`:155-159`) unchanged — the RO
   cannot do it (a fresh send must force-scroll + re-arm even when `stickToBottom` is false). After the
   deletion the follow effect's deps reduce to `[messages]` (it only scans `messages` for the last user
   turn now); update the deps array accordingly.
5. Do NOT touch the scroll LISTENER (`:120-129`, maintains `stickToBottomRef`) — the RO only reads it, so
   a user who scrolled up is still never yanked (near-bottom <120px gate intact).

Why no RO feedback loop: writing `container.scrollTop` changes scroll position, not the observed
element's SIZE, so the RO does not re-trigger itself. (A benign "ResizeObserver loop" console line is
possible but harmless; do not add hacks for it.)

## Tests (RED→GREEN where achievable; jsdom limits the visual proof — orchestrator owns the live proof)
Rework `frontend/src/components/chat/ChatPanel.test.tsx`:
- KEEP: "every rendered transcript row exposes data-message-id"; "does not throw when scrollIntoView is
  unavailable"; the NEW-USER-TURN re-arm test (`forces scroll-to-bottom + re-arms following on a NEW user
  turn even after a scroll-up`) — the new-turn branch is unchanged, so it must still pass (it asserts
  `scrollIntoView({behavior:"auto"})` on a new user message).
- REWORK "follows the stream INSTANTLY …" — the follow is now the RO, not a chunk `scrollIntoView`.
  Mock `ResizeObserver` (`vi.stubGlobal("ResizeObserver", class { constructor(cb){ROcb=cb} observe(){}
  disconnect(){}})` capturing the callback), render a streaming reply, set the scroll container geometry
  via `Object.defineProperty` (scrollHeight > clientHeight, scrollTop 0 so the listener keeps
  stickToBottom true — dist 0<120 under jsdom zeros is fine), invoke the captured RO callback, and assert
  the container's `scrollTop` was set to `scrollHeight` (the pin). 
- ADD a **fail-before/pass-after** guard for THIS bug: simulate a TYPEWRITER FRAME — the rendered height
  grows WITHOUT a `messages`/`streamingContent` change (i.e. only the RO callback fires, no rerender of
  ChatPanel's props) — and assert the bottom is pinned (`scrollTop === scrollHeight`). Before the fix
  nothing follows a typewriter frame (RED); after, the RO pins it (GREEN). (If driving "no props change"
  is awkward in RTL, at minimum assert the RO callback pins when `stickToBottom` is true and does NOT when
  false — that is the behavioural contract that fixes the jitter.)
- The "does NOT follow after the user scrolls up" contract should be preserved via the RO path: with
  stickToBottom cleared, invoking the RO callback must NOT change scrollTop. Reconcile that test to the RO.

## Verify offline (report ACTUAL output)
- vitest FROM `frontend/` (cwd-sensitive; NOT `--root frontend`): ChatPanel + RunChatLane + useRunChat +
  useSmoothText suites green. Show counts.
- `npx tsc --noEmit` → 0. `npx eslint <changed files>` → 0 errors (this repo's react-hooks lint is strict:
  no ref writes during render; setState/DOM writes only in callbacks — the RO callback is a callback, fine).
- Do NOT run live Bedrock / start-stop the backend (orchestrator owns the running :8000/:3000 + the live
  footer-Y proof). Do NOT run Playwright.

## Constraints (verbatim)
Branch feat/ui-2 ONLY. NEVER push. NEVER `git stash`. NO commit trailer. FE-only. Worktrees OFF →
sequential. One atomic commit, clear conventional message (e.g. `fix(chat): follow rendered height via
ResizeObserver so the run-summary footer stops jittering`). If STATE.md resets, don't fight it.

## Output contract
Report: commit SHA; files changed + line counts; literal vitest summary; tsc + eslint results; confirm no
push / no trailer / no live Bedrock / stayed on feat/ui-2. If you deviate from the RO design, say exactly
what and why.
