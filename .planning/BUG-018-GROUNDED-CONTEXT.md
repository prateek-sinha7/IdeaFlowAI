# BUG-018 — grounded fix spec (Concierge reply overwrites the user's question + footer takes over the last slot)

> **FRONTEND-ONLY.** Two parts. **Part A** (data/correctness, ~1 line + test): the reply must stop overwriting the user's question bubble. **Part B** (UI/design, per user 2026-07-17): collapse the run-summary footer (pipeline + deliverable cards) into a compact, animated, expandable strip pinned at the bottom, so the CONVERSATION takes visual priority and the newest reply reads as the last conversational item; the user can expand to see the generated artifacts. Root cause of Part A verified 3 ways (live DOM, DB, code). Executable spec for a `gsd-quick`.

## Background (verified this session)
The BUG-017 fix made the durable-only Concierge reply RENDER (was invisible). That EXPOSED two pre-existing presentation defects, both confirmed live on run `97a97b7b` ("an apple replica site"):
1. The reply REPLACES the user's question bubble in place (they never coexist).
2. The reply is not the last item — the pinned pipeline-mini + deliverable footer cards sit below it.

---

## PART A — stop the reply overwriting the user's question (the real bug)

**Root cause (verified):** the durable `chat_reply` row carries a DISTINCT `event_id` COLUMN (`chat-reply:{message_id}`), but its `payload_json` has NO `event_id` key — only `message_id`, which is IDENTICAL to the paired user `chat_message`'s `message_id` (both `client-1-…`; verified in `run_events`). `frontend/src/lib/api.ts::getRunEvents` (`:562-565`) maps each row to `{ type: row.type, data: row.payload_json }` — it DROPS `row.event_id` and `row.seq`. So on the FE re-fetch path `data.event_id` is undefined → `upsertNarratorMessage` (`frontend/src/hooks/useRunChat.ts:239-244`) falls back to `data.message_id` → `findIndex` (`:258`) matches the existing USER turn (same id) → `:261` overwrites it in place with `role:"assistant"`. The DEF-44-12-2 de-collision (which keys the reply on its distinct `event_id`) is DEFEATED because getRunEvents never surfaces `event_id` into the frame.

**The fix — `frontend/src/lib/api.ts::getRunEvents` (`:562-565`):** merge the row's authoritative `event_id` + `seq` into the frame data:
```ts
return (res?.events ?? []).map((row) => ({
  type: row.type,
  data: { ...(row.payload_json ?? {}), event_id: row.event_id, seq: row.seq },
}));
```
This aligns the code with the getRunEvents docstring intent (`:548-551`: "consumers key on the snake_case `event_id`/`seq` inside it"). Effect: `data.event_id` = `chat-reply:{message_id}` (distinct from the user turn's `message_id`) → `upsertNarratorMessage` keys on it → the reply APPENDS as its own turn BELOW the question (the intended behavior, per the comment at useRunChat.ts:233-238); the question survives. Also `data.seq` now advances the re-fetch cursor (`lastSeqRef`, handleFrame useRunChat.ts:289-291) correctly.

**Why safe:** the column value wins over any same-named payload key (spread order) — correct, the column is authoritative. This only affects the durable re-fetch path (getRunEvents); the SSE live path (useRunStream) is a separate mapping, untouched. Consumers already READ `data.event_id`/`data.seq` (page `seenEventIdsRef` dedup + useRunChat) — we're supplying what they already expect.

**RED→GREEN test (`useRunChat.test.ts`):** fold a durable USER frame `{type:"chat_message", data:{message_id:"X", text:"Q"}}` then a durable REPLY frame `{type:"chat_reply", data:{event_id:"chat-reply:X", message_id:"X", text:"A"}}`; assert the transcript has TWO messages (a `role:"user"` "Q" AND a `role:"assistant"` "A") in that order — NOT one overwritten bubble. Fail-before: with the reply frame lacking `event_id` (the old getRunEvents shape) the reply overwrites the user turn (1 message, role assistant). (A parallel getRunEvents unit test can assert the mapped frame's `data.event_id`/`data.seq` are populated from the row.)

---

## PART B — collapse the run-summary footer to a compact animated strip (user's design)

**User's ask (verbatim intent):** "animate and collapse the sticky to bottom, so that conversation takes importance and if user wants to see generated ones, user can then see." So the pinned run-summary adornments must default to a COLLAPSED compact strip; the conversation leads; the user expands to reveal the generated artifacts.

**Where:** `frontend/src/components/chat/RunChatLane.tsx::renderTranscriptFooter` (`:1021-1051`). For `runState === "complete" || "idle"` it currently returns an always-open block:
```tsx
<div data-testid="lane-adornments" className="flex flex-col gap-4">
  {clarifyCount > 0 && <ClarifyCountRow .../>}
  {agents.length > 0 && <PipelineMini agents={agents} onOpen={goSteps} />}
  {dFilename && <DeliverableCard filename={dFilename} version={dVersion} onOpen={goPreview} />}
</div>
```
`ChatPanel.tsx` renders `{messages}` then `{transcriptFooter}` then the scroll anchor (`:358/:377`), so these adornments are always the last DOM children (below every reply).

**The change — make the settled adornments a COLLAPSIBLE, animated, expandable strip (collapsed by default):**
- **Collapsed (default):** a compact full-width toggle row pinned at the foot of the transcript (still above the composer) — a `<button>` showing a short summary + a chevron, e.g. `Run summary` with tiny meta (`{agents.length} agents · {dFilename}`). `data-testid="lane-adornments-toggle"`. When collapsed, the conversation (messages) is the dominant content and the newest reply is the last conversational element above this thin strip.
- **Expanded:** animate open to reveal the existing `ClarifyCountRow` + `PipelineMini` + `DeliverableCard` (unchanged, same `onOpen` deep-links `goSteps`/`goPreview`). Chevron rotates.
- **Animation:** CSS-only (no lib available — verified: no framer-motion/radix). Use a height/opacity transition (e.g. the `grid-template-rows: 0fr → 1fr` reveal trick, or `max-height` + `opacity`), ~200-250ms ease. **MUST** be gated by `prefers-reduced-motion: reduce` (no transition → instant open/close). Match the existing collapse idiom in `src/components/chat/ThinkingBlock.tsx` / `ArtifactCard.tsx` for visual + interaction consistency.
- **A11y:** the toggle is a real `<button>` with `aria-expanded={open}` + `aria-controls` pointing at the panel id; visible keyboard focus; the panel gets `role="region"` (or is `hidden`/`inert` when collapsed so it's out of the tab order).
- **State:** local `useState` (default collapsed). Persistence across renders is fine but NOT required; do NOT add global/route state.
- Keep `data-testid="lane-adornments"` on the EXPANDED panel (so existing selectors that target it still resolve once expanded), and add `lane-adornments-toggle` for the collapsed handle.
- The `clarify` / other live runStates in renderTranscriptFooter (`:1053+`) are UNCHANGED — this only affects the settled (`complete`/`idle`) adornments.

**At-risk tests (Part B changes visible-by-default behavior — RECONCILE, do NOT delete):** any mocked Playwright / vitest that asserts `lane-pipeline-mini`, `lane-deliverable`, or `lane-adornments` are VISIBLE on a settled run will now need to first click `lane-adornments-toggle` to expand (or assert the collapsed strip). Grep the e2e + component tests for those testids (`ts-chat`, `ts-t.history`, `ts-j.streaming`, and any RunChatLane/ChatPanel vitest) and update them to expand-then-assert. This is legitimate changed-behavior reconciliation.

---

## Scope fences (STRICT)
- **Frontend only.** Part A: `frontend/src/lib/api.ts` (getRunEvents) + `useRunChat.test.ts` (+ optionally an api.ts unit test). Part B: `frontend/src/components/chat/RunChatLane.tsx` (renderTranscriptFooter) + possibly a small new local sub-component/file for the collapsible + its test + reconciled e2e/vitest.
- Do NOT change the backend, the queue, or the durable persist (event_id already stored correctly in the column). Do NOT add a live-queue push.
- Do NOT touch the BUG-014-B SSE parser, the BUG-015 detach/reconnect logic, the reducer, or the BUG-017 page.tsx adapter.
- Part A must not alter the SSE live-path mapping (useRunStream) — only getRunEvents.

## Constraints
- Branch **feat/ui-2** (NEVER main/staging). Worktrees OFF → sequential. **NO commit trailer** (no Co-Authored-By / Claude-Session). **NEVER push.**
- FE cwd-sensitive: run vitest/Playwright from inside `frontend/`; kill :3000 before mocked Playwright. **Use `localhost:3000` (NOT 127.0.0.1) for any browser check** — the Turbopack dev server does not hydrate on 127.0.0.1.
- SC-001: keep any guarded component free of workflow-name literals; `page.tsx` is exempt (not touched here anyway).
- Do NOT run a live Bedrock run in the executor — the orchestrator does the live proof after (send a question on a completed run → the question AND the reply both render, in order, question then reply; the footer is collapsed by default and expands on click).

## Verification (RED→GREEN + reconcile)
- `npx tsc --noEmit` clean (from `frontend/`).
- vitest: Part A `useRunChat` overwrite test RED→GREEN (question + reply coexist, ordered); existing send-routing (:140-143), re-fetch (:282-323), Test 14 ordering (BUG-017) stay green. Part B: a RunChatLane/collapsible test — collapsed by default (panel not visible / `aria-expanded=false`), clicking the toggle reveals the pipeline-mini + deliverable (`aria-expanded=true`); prefers-reduced-motion path doesn't error.
- Mocked Playwright from inside `frontend/` (kill :3000 first): reconcile the footer-visibility specs; ts-chat, ts-chat-cards, ts-sse, ts-sse-resilience, ts-s.reconnect, ts-j.streaming, ts-t.history, ts-u.revisions green after reconciliation. Establish the REAL before/after green counts (the 132/0 baseline is stale).
