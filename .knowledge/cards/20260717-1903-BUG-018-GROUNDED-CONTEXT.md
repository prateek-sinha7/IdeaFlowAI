---
id: BUG-018-GROUNDED-CONTEXT
type: bug
kind: event
title: BUG-018 — grounded fix spec
status: resolved
applies_to:
  phases: []
  modules:
  - ArtifactCard
  - Card
  - ChatPanel
  - Match
  - RunChatLane
  - RunEvent
  - ThinkingBlock
  - User
  - agents
  - api
  - app
  - chat
  - useRunChat
  - useRunChat.test
  - useRunStream
  globs:
  - frontend/src/hooks/useRunChat.ts
  - useRunChat.test.ts
  - ChatPanel.tsx
  - src/components/chat/ThinkingBlock.tsx
  - ArtifactCard.tsx
  - frontend/src/lib/api.ts
  - frontend/src/components/chat/RunChatLane.tsx
  - page.tsx
  requirements: []
locked_constraints: []
verification:
  type: test
  status: passed
  test_files:
    - frontend/src/components/chat/RunChatLane.reducedMotion.test.tsx
compact_summary: 'getRunEvents dropped row.event_id so replies collided with the user turn''s message_id and overwrote it; merging event_id/seq into the frame fixed it.'
last_updated: '2026-10-01'
author: 'Bilal Arshad <bilala@hexaware.com>'
author_source: applies-to-glob
---

<!-- RELATED -->

## Related

**Referenced by:** [FIX-686](20261001-2130-FIX-686.md), [ISS-889](20261001-2117-ISS-889.md), [ISS-890](20261001-2117-ISS-890.md)

<!-- /RELATED -->

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

---

## Validation 2026-10-01 — QA-KB-001 (footer ignores prefers-reduced-motion) — CONFIRMED 3/3 (static)

Reproduction mode Static (no browser). Three cold runs of `grep -n "motion/react\|useReducedMotion\|reducedMotion\|duration: 0.22" frontend/src/components/chat/RunChatLane.tsx` gave identical results each time:
- `RunChatLane.tsx:35` `import { motion } from "motion/react";` (no `useReducedMotion`)
- `RunChatLane.tsx:829` (SettledSummaryStrip `lane-adornments` panel) `transition={{ duration: 0.22, ease: "easeOut" }}` with unconditional `animate={{ height: open ? "auto" : 0, opacity: ... }}`
- `RunChatLane.tsx:2144` a second unconditional `duration: 0.22` transition.
- `grep -rl "prefers-reduced-motion\|useReducedMotion\|MotionConfig" frontend/src` returns nothing: no reduced-motion gate anywhere in the frontend, although the spec above says the animation MUST be gated by `prefers-reduced-motion: reduce`.
Note: line 2144 was not named in the report; the analyzer should check whether it needs the same gate. Status of this card stays open until fixed.

## Analysis (QA-KB-001, 2026-10-01)

The validator section above is **CONFIRMED**, with one correction to the agreed fix's reasoning and one gap in its scope (both below). Every `file:line` cited was read on HEAD 024c03ef (branch feat/user-stories-v2); INFERRED items are marked. Besides source reads and `git log`, the analyzer ran a scratch jsdom harness outside the repo (session scratchpad; no file under `frontend/` was changed): a stand-in panel built like `RunChatLane.tsx:821-831`, and scratch copies of `RunChatLane.tsx` with the fix applied. Those runs are not repo tests.

### Root cause (CONFIRMED): the footer is ungated, and so is everything else

Three layers, each read:

1. **Library default.** `motion` 12.38.0's context defaults to `reducedMotion: "never"` (`framer-motion/dist/es/context/MotionConfigContext.mjs:10`); every element copies it from context (`framer-motion/dist/es/motion/utils/use-visual-element.mjs:17,40`) and `"never"` pins `shouldReduceMotion = false` (`motion-dom/dist/es/render/VisualElement.mjs:206-207`). A bare `motion.div` never consults the OS setting.
2. **The app never opts in.** `grep -rn -i -E "prefers-reduced-motion|useReducedMotion|MotionConfig|reducedMotion|motion-safe|motion-reduce"` over `frontend/` (excluding node_modules, .next, .git) matches nothing (exit 1).
3. **The site.** `RunChatLane.tsx:35` imports `{ motion }` only. The `lane-adornments` panel (`:821-831`) animates `animate={{ height: open ? "auto" : 0, opacity: open ? 1 : 0 }}` (`:828`) with the constant `transition={{ duration: 0.22, ease: "easeOut" }}` (`:829`).

Why the gate went missing (`git log` / `git show`): commit `23a7cd2ad` (2026-07-17, "collapse settled run-summary footer into an expandable strip (BUG-018 Part B)") added the `motion/react` import and `SettledSummaryStrip`; neither its message nor its diff mentions reduced motion (`git show 23a7cd2ad | grep -i -E "reduced|prefers-reduced|useReducedMotion"` exits 1). Part B above specified a CSS-only animation ("CSS-only (no lib available — verified: no framer-motion/radix) ... MUST be gated by prefers-reduced-motion: reduce") and also said "Match the existing collapse idiom in `ThinkingBlock.tsx` / `ArtifactCard.tsx` for visual + interaction consistency". Those two files are `motion/react` components, and the "no lib" premise was already false: `motion` was a dependency (`git show 23a7cd2ad:frontend/package.json`, line 19, `"motion": "^12.38.0"`) and `ThinkingBlock.tsx` had imported `motion/react` since 2026-07-08 (`21159d917`). The implementer followed the idiom (docstring at `RunChatLane.tsx:767-771`: "animates open via the house motion/react idiom (mirrors ThinkingBlock/ArtifactCard)"). A CSS media query cannot reach motion's JS-driven inline-style tween, so the CSS-shaped requirement fell out. INFERRED: that this was an oversight rather than a decision (the commit says neither). Nothing enforces it today: no test mentions `matchMedia` (`grep -rln matchMedia frontend/src frontend/e2e` finds nothing), and the existing strip test (`RunChatLane.test.tsx:890-927`) asserts aria/inert state, which flips regardless of animation.

### The validator's second site (CONFIRMED) -> [ISS-889](20261001-2117-ISS-889.md)

`RunChatLane.tsx:2141-2147`, the live Pipeline mini's collapse panel, has `transition={{ duration: 0.22, ease: "easeOut" }}` at `:2144`. These are the only two `duration: 0.22` literals in `frontend/src`. It comes from `5818cdcca` (2026-08-11), not from BUG-018, and the `replyPending` effect (`:1224-1226`) collapses it automatically on every chat send, so a reduced-motion user hits it without clicking.

### Blast radius

CONFIRMED by grep and reads:

- Footer: the 2 panels above, mounted only through `renderTranscriptFooter()` (`:1991`, called at `:2280`) inside `RunChatLane`, which is rendered only by `DashboardLayout.tsx:3282`, i.e. every run screen.
- Same file, same flaw, different shape: 4 infinite opacity pulses (`:360`, `:1711`, `:2035`, `:2100`) and one Tailwind `animate-pulse` (`:2136`).
- Rest of the app: 50 non-test files import `motion` (174 `<motion.*>` elements, 9 infinite loops); `globals.css:344-440` has 7 keyframes and 7 `animation:` declarations; 114 `animate-*` and about 540 `transition*` utilities. All tracked in [ISS-890](20261001-2117-ISS-890.md).
- Tests that render the real `RunChatLane`: `RunChatLane.test.tsx` (55 tests), `__tests__/RunChatLane.terminal.test.tsx` (12), `RunChatLane.fix192.test.tsx` (14). Only `fix192` replaces `motion/react` with a factory (`:59-69`, exports `motion` and `AnimatePresence` only), and it also mocks `ChatPanel`, so footer components never mount there. The six `DashboardLayout.*` tests mock `motion/react` but stub `RunChatLane`.
- SC-001 guard: `RunChatLane.test.tsx:1089-1093` regexes the whole of `RunChatLane.tsx` for `"prototype"|od_ppt|app_builder|user_stories`. Any text added to the file must avoid them.

INFERRED: browser behaviour matches what jsdom showed. Reason: the reduced-motion decision is taken in `animateTarget` before any animation object exists (`motion-dom/dist/es/animation/interfaces/visual-element-target.mjs:76-78`), independent of the WAAPI/JS split that differs between a browser and jsdom. What would settle it: Chrome DevTools > Rendering > emulate `prefers-reduced-motion: reduce`, expand the strip, watch the 220 ms tween.

### Library behaviour, observed

OS preference stubbed to reduce (`useReducedMotion()` returned true), stand-in panel built like `RunChatLane.tsx:821-831`. Height is numeric because jsdom has no layout, so `height: "auto"` reads `auto` in every case.

| Scenario | height 0 to 100px | opacity 0 to 1 |
|---|---|---|
| today's code, default config | ramps 10px to 100px over ~225 ms | ramps 0.10 to 1.00 |
| only `<MotionConfig reducedMotion="user">` | 100px at the first sample | still ramps 0.10 to 1.00 over ~214 ms |
| per-site `transition={{ duration: 0 }}` | 100px at the first sample | 1.00 at the first sample |
| `<MotionConfig skipAnimations>` | not measured | 1.00 at the first sample |
| per-site gate, OS reduce OFF | ramps to 100px over ~250 ms | ramps 0.01 to 1.00 (no regression) |

Mechanism, read in the installed code: under `"user"`, a key in `positionalKeys` becomes `{ type: false }` (`motion-dom/dist/es/animation/interfaces/visual-element-target.mjs:76-78`); `positionalKeys` is width, height, top, left, right, bottom plus every transform key (`motion-dom/dist/es/render/utils/keys-position.mjs:3-11`), and `opacity` is not in it. `duration: 0` takes the instant path (`motion-dom/dist/es/animation/interfaces/motion-value.mjs:65-66`) and applies the final keyframe on the next frame (`:91`).

### Fix

#### The agreed minimal fix (BUGS.md QA-KB-001 Notes): ACCEPTED, with three corrections

Accepted as written for the strip: import `useReducedMotion` (`RunChatLane.tsx:35`), `const reduce = useReducedMotion();` after `useId()` in `SettledSummaryStrip` (`:789`), and `transition={reduce ? { duration: 0 } : { duration: 0.22, ease: "easeOut" }}` at `:829`. Verified on a scratch copy: under reduce the panel is at its final value at the first sample, and without reduce it tweens as before.

1. **Reasoning refuted, conclusion kept.** The note says `MotionConfig reducedMotion="user"` "only disables transform and layout animations, not height or opacity". It does cover `height` (table above; `keys-position.mjs:3-11`); it does not cover `opacity`. Not using it for THIS bug is still right, for the corrected reason: the panel would snap open but fade in over 220 ms, and the stated expectation is "instantly (duration 0)". It is the right instrument for the app-wide policy ([ISS-890](20261001-2117-ISS-890.md)).
2. **Scope too narrow.** The note edits only `:829`. The live panel at `:2144` ([ISS-889](20261001-2117-ISS-889.md)) is the same defect in the same footer; fixing one leaves a building run animating.
3. **The optional test is non-discriminating.** "mocks matchMedia for reduce, clicks the toggle, and asserts aria-expanded is true with no error" passes on today's broken code (`aria-expanded` flips regardless; the scratch run saw the tween play with aria-expanded true). Use the contract test below.

#### Where the hook goes

`renderTranscriptFooter` is a plain function (`:1991`, invoked at `:2280`), so a hook cannot sit inside its branches. Two shapes, both type-checked (`tsc` strict with the frontend tsconfig, exit 0; a deliberately broken control failed TS2322) and run on scratch copies:

- **Y (recommended): one local component owns the gate.** +24 net lines, no test edits. Existing tests against the Y copy: `RunChatLane.test.tsx` 55/55, `terminal` 12/12, `fix192` 14/14 with its mock unchanged. Behaviour: reduce ON, both panels at final opacity at the first sample (`[1]`, `[0]`) with `aria-expanded` still flipping; OFF, both tween as before.
- **X: the agreed hook in `SettledSummaryStrip` plus `useReducedMotion()` at the top of `RunChatLane` (next to `:1213`).** +2 net lines. `RunChatLane.test.tsx` 55/55 and `terminal` 12/12, but **`fix192` fails all 14** with `Error: [vitest] No "useReducedMotion" export is defined on the "motion/react" mock`, so its factory at `RunChatLane.fix192.test.tsx:59-69` must gain `useReducedMotion: () => false`.

Control: the same three test files, copied against an untouched scratch copy, passed 55/12/14, so the copying is not what fails X.

```tsx
// RunChatLane.tsx:35
import { motion, useReducedMotion } from "motion/react";

// above the SettledSummaryStrip docblock (~:760)
/** The lane's single collapse panel: height/opacity reveal, INSTANT under reduced motion. */
function CollapsePanel({
  open,
  children,
  ...rest
}: {
  open: boolean;
  children: ReactNode;
  id?: string;
  role?: string;
  inert?: boolean;
  "aria-hidden"?: boolean;
  "data-testid"?: string;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      {...rest}
      initial={false}
      animate={{ height: open ? "auto" : 0, opacity: open ? 1 : 0 }}
      transition={reduce ? { duration: 0 } : { duration: 0.22, ease: "easeOut" }}
      className="overflow-hidden"
    >
      {children}
    </motion.div>
  );
}
```

Then replace the strip's `<motion.div ...>...</motion.div>` (`:821-845`) with `<CollapsePanel id={panelId} data-testid="lane-adornments" role="region" aria-hidden={!open} inert={!open ? true : undefined} open={open}>...</CollapsePanel>`, and the live panel's (`:2141-2156`) with `<CollapsePanel open={!pipelineMiniCollapsed} aria-hidden={pipelineMiniCollapsed}>...</CollapsePanel>`. `motion` stays imported (the four dot loops use it).

Static re-check after the fix (the QA-KB-001 Static mode): `grep -n 'transition={{ duration: 0.22' frontend/src/components/chat/RunChatLane.tsx` returns nothing, `useReducedMotion` is imported, and the new contract test is green.

### For the test-writer

Put it in a NEW file, e.g. `frontend/src/components/chat/RunChatLane.reducedMotion.test.tsx`. Do not add the `motion/react` mock to `RunChatLane.test.tsx`: that file runs against the real library, and a file-wide factory would change its other 55 tests. Fixtures: settled is `runState: "complete"` with `pipelineState` carrying `deliverableFilename`/`deliverableVersion` and 2 done agents (`RunChatLane.test.tsx:870-891`); live is `runState: "building"`, `isRunning: true`, 5 agents (`:725-742`; the `ps` builder is at `:665-673`).

Deterministic contract test. Observed RED on today's code (the two "instant when OS=reduce" cases fail, receiving `{"duration":0.22,"ease":"easeOut"}`) and GREEN on both variants (4/4):

```tsx
const osReduce = vi.hoisted(() => ({ value: false }));
vi.mock("motion/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("motion/react")>();
  const React = await import("react");
  const Div = React.forwardRef<HTMLDivElement, Record<string, unknown>>(function Probe(props, ref) {
    const { animate: _a, initial: _i, transition, ...rest } = props;
    return React.createElement("div", { ref, "data-transition": JSON.stringify(transition), ...rest });
  });
  return {
    ...actual,
    useReducedMotion: () => osReduce.value,
    motion: new Proxy(actual.motion, { get: (t, k) => (k === "div" ? Div : (t as never)[k as never]) }),
  };
});
// settled: osReduce.value = true; render the complete state;
//   expect(screen.getByTestId("lane-adornments").getAttribute("data-transition")).toBe('{"duration":0}')
// live: osReduce.value = true; render the building state;
//   expect(screen.getByTestId("lane-pipeline-mini-toggle").nextElementSibling!.getAttribute("data-transition")).toBe('{"duration":0}')
// and the same two with osReduce.value = false -> '{"duration":0.22,"ease":"easeOut"}' (regression guard)
```

If a real `matchMedia` stub is preferred, two traps, both observed:

- The stub needs `addEventListener`/`removeEventListener`. A bare `{ matches: true }` makes `initPrefersReducedMotion()` throw `TypeError: motionMediaQuery.addEventListener is not a function` (`motion-dom/dist/es/render/utils/reduced-motion/index.mjs:11`); React recovers, the listener flag is already set, so `useReducedMotion()` returns `null`, vitest reports an Unhandled Error, and the test looks green while exercising nothing.
- Install it before the first `useReducedMotion()` call in the file: the preference is read once per module instance (`framer-motion/dist/es/utils/reduced-motion/use-reduced-motion.mjs:36-37`), and a stub installed after an earlier call stays `false`. jsdom has no `matchMedia` and `vitest.setup.ts` does not polyfill one.

A timing variant also works (sample `panel.style.opacity` every ~12 ms after the click: under reduce the first sample is already final, `1` or `0`; otherwise mid-flight values appear), but it can false-pass on a slow machine, so keep it as a second layer at most. Playwright: no config sets `reducedMotion`, so e2e is unaffected; a browser repro needs DevTools emulation.

### Siblings

- [ISS-889](20261001-2117-ISS-889.md): the live Pipeline mini panel (`RunChatLane.tsx:2141-2156`). Same file, same idiom, own origin commit; fix it in the same change.
- [ISS-890](20261001-2117-ISS-890.md): no reduced-motion policy anywhere else (49 other motion files, CSS keyframes, Tailwind utilities, smooth scroll). INFERRED per component; the absence of any gate is CONFIRMED.

Considered and not minted: the strip's `inert`/`aria-hidden` handling (unrelated to motion), and per-file cards for the other 49 `motion/react` files (one policy card covers them; the CSS side and the opacity pulses are listed in it).

## Fix (QA-KB-001, 2026-10-01): [FIX-686](20261001-2130-FIX-686.md)

Part B's reduced-motion gate now exists. I applied variant Y from the analysis above as written:
`RunChatLane.tsx:35` imports `useReducedMotion`, and the new local `CollapsePanel`
(`RunChatLane.tsx:760-786`) sets `transition={reduce ? { duration: 0 } : { duration: 0.22, ease: "easeOut" }}`.
Both the settled strip (`:849-870`) and the live Pipeline mini ([ISS-889](20261001-2117-ISS-889.md),
`:2166-2175`) render through it. `RunChatLane.reducedMotion.test.tsx` was 2 passed | 2 expected fail before the change.
After it, both `it.fails` flipped ("Expect test to fail") and both guards stayed green. The existing
55/12/14 RunChatLane tests are all green, and the `fix192` mock is unchanged. The app-wide policy
([ISS-890](20261001-2117-ISS-890.md)) stays open. The full coverage block is on the FIX card.
