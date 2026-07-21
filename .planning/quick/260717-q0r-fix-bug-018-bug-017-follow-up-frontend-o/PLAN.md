---
phase: quick-260717-q0r
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/lib/api.ts
  - frontend/src/lib/api.test.ts
  - frontend/src/hooks/useRunChat.test.ts
  - frontend/src/components/chat/RunChatLane.tsx
  - frontend/src/components/chat/RunChatLane.test.tsx
autonomous: true
requirements:
  - BUG-018
must_haves:
  truths:
    - "BUG-018 Part A (data): `getRunEvents` (api.ts:562-565) merges the durable row's authoritative `event_id` + `seq` COLUMNS into the mapped frame's `data` — so a durable Concierge `chat_reply` (whose `payload_json` has NO `event_id`, only a `message_id` IDENTICAL to the paired user turn's) surfaces its DISTINCT `event_id` (`chat-reply:{message_id}`) to `upsertNarratorMessage` (useRunChat.ts:239-244), which then keys on it and APPENDS the reply as its OWN assistant turn BELOW the question instead of matching-and-overwriting the user's question bubble in place."
    - "BUG-018 Part A (no regression): the SSE live path (`useRunStream` mapping) is UNTOUCHED — only the durable re-fetch path (`getRunEvents`) changes. Existing useRunChat cases (Test 12 DEF-44-12-2 de-collision :251, the send-routing :140-143, the re-fetch/Test 14 ordering) stay green. The column value wins over any same-named payload key (spread order — the column is authoritative), and `data.seq` now advances the re-fetch cursor (`lastSeqRef`) correctly."
    - "BUG-018 Part B (UI): the SETTLED (`complete`/`idle`) run-summary footer in `RunChatLane.renderTranscriptFooter` (:1036-1050) is a COLLAPSED-BY-DEFAULT, CSS-animated, expandable strip — a real `<button>` (`lane-adornments-toggle`, `aria-expanded`/`aria-controls`, visible focus) that reveals the existing `ClarifyCountRow` + `PipelineMini` + `DeliverableCard` panel (`data-testid=\"lane-adornments\"`, unchanged deep-links) on expand; so the conversation leads visually and the newest reply reads as the last conversational item above the thin strip."
    - "BUG-018 Part B (no regression + a11y): animation is CSS-only (grid-template-rows 0fr→1fr reveal), gated by `prefers-reduced-motion` via Tailwind `motion-reduce:` (NO JS matchMedia → reduced-motion path cannot throw); the `clarify`/`gate`/`building`/`terminal` live branches (:1053+) are UNCHANGED (they never rendered `lane-adornments`); only the settled branch collapses."
    - "BUG-018 (scope): FRONTEND-ONLY — no backend / queue / durable-persist change (the `event_id` column is already stored correctly); no live-queue push; the BUG-014-B SSE parser, BUG-015 detach/reconnect logic, the reducer, and the BUG-017 page.tsx adapter are all untouched."
  artifacts:
    - path: "frontend/src/lib/api.ts"
      provides: "getRunEvents maps each durable row to { type, data: { ...payload_json, event_id: row.event_id, seq: row.seq } } — the column event_id/seq now reach consumers"
      contains: "event_id: row.event_id"
    - path: "frontend/src/lib/api.test.ts"
      provides: "NEW getRunEvents unit test — the direct RED->GREEN gate: a mocked request returns a durable reply row (event_id COLUMN set, payload_json WITHOUT event_id); the mapped frame's data.event_id === row.event_id AND data.seq === row.seq (RED before: undefined)"
      contains: "getRunEvents"
    - path: "frontend/src/hooks/useRunChat.test.ts"
      provides: "RED->GREEN behavioral test: a durable USER frame + a durable REPLY frame (both message_id X) built via the REAL getRunEvents (mocked request) emit through the hook and fold into TWO ordered turns (user 'Q' then assistant 'A'); fail-before (event_id stripped) = 1 overwritten assistant bubble"
      contains: "chat-reply"
    - path: "frontend/src/components/chat/RunChatLane.tsx"
      provides: "settled renderTranscriptFooter returns a collapsed-by-default CSS-animated strip: <button lane-adornments-toggle aria-expanded/aria-controls> + an inert/aria-hidden-when-collapsed lane-adornments panel wrapping the unchanged ClarifyCountRow/PipelineMini/DeliverableCard"
      contains: "lane-adornments-toggle"
    - path: "frontend/src/components/chat/RunChatLane.test.tsx"
      provides: "NEW collapse test (collapsed by default: toggle aria-expanded=false + panel inert; click reveals lane-pipeline-mini + lane-deliverable; reduced-motion render doesn't throw) + the two existing settled cases (:554-581, :627-661) reconciled to expand-then-assert"
      contains: "lane-adornments-toggle"
  key_links:
    - from: "getRunEvents row mapping (api.ts:562-565)"
      to: "DurableFrame.data.event_id / data.seq"
      via: "spread merge of the RunEventRow event_id + seq COLUMNS over payload_json (column authoritative)"
      pattern: "event_id: row\\.event_id"
    - from: "upsertNarratorMessage id selection (useRunChat.ts:239-244)"
      to: "an appended assistant turn (distinct from the user turn keyed on message_id)"
      via: "data.event_id ('chat-reply:{message_id}') now present → keyed distinctly → findIndex misses → append"
      pattern: "data\\.event_id"
    - from: "RunChatLane settled renderTranscriptFooter (:1036-1050)"
      to: "the lane-adornments panel (PipelineMini + DeliverableCard)"
      via: "a lane-adornments-toggle button gating a CSS grid-rows collapse (collapsed by default)"
      pattern: "lane-adornments-toggle"
---

<objective>
Fix BUG-018 (a BUG-017 follow-up) — the durable Concierge chat reply OVERWRITES the user's
question bubble, and the run-summary footer cards sit BELOW the reply instead of the conversation
leading. Implement EXACTLY the grounded spec in `.planning/BUG-018-GROUNDED-CONTEXT.md` — the root
cause of Part A is verified three ways (live DOM, DB, code). Do NOT re-investigate or re-debug.

FRONTEND-ONLY, two parts:

PART A (data/correctness, ~1 line + tests): `getRunEvents` (api.ts:562-565) maps each durable
`run_events` row to `{ type, data: row.payload_json }` and DROPS the row's `event_id`/`seq`
COLUMNS. The durable Concierge `chat_reply` carries a DISTINCT `event_id` column
(`chat-reply:{message_id}`) but its `payload_json` has NO `event_id` — only a `message_id` that is
IDENTICAL to the paired user `chat_message`'s. So on the re-fetch path `data.event_id` is undefined
→ `upsertNarratorMessage` (useRunChat.ts:239-244) falls back to `message_id` → `findIndex` (:258)
matches the existing USER turn → :261 overwrites it in place with `role:"assistant"`. The
DEF-44-12-2 de-collision is DEFEATED because getRunEvents never surfaces the column `event_id`. Fix:
merge the row's authoritative `event_id` + `seq` into the frame `data` (column wins over any
same-named payload key). Effect: the reply keys on its distinct `event_id` and APPENDS as its own
turn below the question; the question survives; `data.seq` advances the re-fetch cursor correctly.

PART B (UI/design, per the user 2026-07-17): collapse the SETTLED run-summary footer
(`RunChatLane.renderTranscriptFooter` :1036-1050 — the `lane-adornments` block: `PipelineMini` +
`DeliverableCard` (+ `ClarifyCountRow`)) into a COMPACT, ANIMATED, EXPANDABLE strip that is
COLLAPSED BY DEFAULT, so the conversation takes visual priority and the newest reply reads as the
last conversational item; expanding reveals the existing cards. CSS-only animation gated by
`prefers-reduced-motion`; a real `<button>` toggle with `aria-expanded`/`aria-controls` + visible
focus; mirror the collapse idiom in `src/components/chat/blocks/ThinkingBlock.tsx`. Only the
`complete`/`idle` settled branch changes; the live branches (:1053+) are untouched.

Purpose: the user's question and the Concierge answer both render, in order, and the conversation
leads; the generated-artifact cards are one click away.
Output: the one-line api.ts merge + a getRunEvents unit test + a useRunChat durable-fold test (Part
A); the RunChatLane collapsible footer + a collapse vitest + the two reconciled settled cases (Part
B); a reconciliation sweep; a regression gate. Playwright + the live proof are DEFERRED to the
orchestrator (see the verification section — :3000 is the user's).
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@.planning/BUG-018-GROUNDED-CONTEXT.md

# PART A FIX SITE. getRunEvents is :553-566; the row->frame map is :562-565 (the ONLY production
# line to change — merge the row's event_id + seq columns into `data`). The row type RunEventRow
# (:519-524) carries `seq: number` + `event_id: string` + `payload_json`; DurableFrame.data
# (:535-538) is Record<string, unknown> — the merge is type-safe. The docstring (:548-551) already
# states the intent ("consumers key on the snake_case event_id/seq inside it"). There is currently
# NO src/lib/api.test.ts — create it for the getRunEvents unit test. Do NOT touch any other export.
@frontend/src/lib/api.ts

# PART A CONSUMER (context — do NOT change). upsertNarratorMessage (:229-265) selects the fold id at
# :239-244: data.event_id first, else message_id, else minted. The Concierge collision comment is at
# :233-238; the overwrite is :258-262. handleFrame routes chat_message->upsertUserMessage (:294-295)
# and chat_reply->upsertNarratorMessage (:297-298), dedups on data.event_id (:284-288), advances
# lastSeqRef from data.seq (:289-292). upsertUserMessage (:185-223) keys the USER turn on message_id
# (:189-192). These are the behaviors the Part A test exercises; do NOT edit useRunChat.ts.
@frontend/src/hooks/useRunChat.ts

# PART A TEST HARNESS to EXTEND (do NOT rewrite existing cases). The `frame(type,data)` helper (:47)
# AUTO-INJECTS event_id/seq — so the new durable-fold test must build RAW frames via the REAL
# getRunEvents (see Task 1). Test 1 (:55) shows the conn.emit path; Test 12 (:251-...) is the
# already-green live-path de-collision; the re-fetch/Test 14 (:282-...) shows fetchEvents wiring.
# All existing cases MUST stay green.
@frontend/src/hooks/useRunChat.test.ts

# PART B FILE. renderTranscriptFooter is :1021-...; the SETTLED branch is :1024-1051 (the
# lane-adornments block :1036-1050 is what collapses); the live clarify/gate/building/terminal
# branches (:1053+) are UNCHANGED. `useState` is already imported (:30); add ChevronDown/ChevronRight
# from lucide-react. ClarifyCountRow / PipelineMini / DeliverableCard render UNCHANGED inside the
# expanded panel with the same goSteps/goPreview deep-links (:1015-1016).
@frontend/src/components/chat/RunChatLane.tsx

# PART B AT-RISK TESTS to RECONCILE (do NOT delete). Two settled cases assert the footer cards are
# VISIBLE on a `runState:"complete"` run and WILL break when collapsed-by-default:
#   - "settled state renders the pipeline mini from live agents" (:554-581) -> getByTestId("lane-pipeline-mini")
#   - "settled: renders the deliverable card..." (:627-661) -> getByTestId("lane-deliverable")
# Reconcile BOTH to click `lane-adornments-toggle` first (expand-then-assert). The "building state
# renders the live pipeline mini" case (:521-552, runState:"building") is a DIFFERENT branch — do
# NOT touch it. The attachments case (:663-678, lane-run-attach-chip) is composer chips — untouched.
@frontend/src/components/chat/RunChatLane.test.tsx

# PART B COLLAPSE IDIOM to MIRROR (context — do NOT edit). blocks/ThinkingBlock.tsx: collapsed-by-
# default `useState(false)`, a real <button aria-expanded aria-controls> with ChevronRight (collapsed)
# / ChevronDown (expanded), a bodyId panel. NOTE: it uses motion/react — but this repo's spec LOCKS
# CSS-only for the footer (see the constraints); reuse only its button/aria/chevron structure, NOT
# its motion.div animation.
@frontend/src/components/chat/blocks/ThinkingBlock.tsx
</context>

<constraints>
- Branch feat/ui-2. Verify with `git rev-parse --abbrev-ref HEAD`; DO NOT switch. NO commit trailer
  (no Co-Authored-By / Claude-Session). NEVER push. Worktrees OFF (sequential).
- STRICT SCOPE — Part A touches ONLY `frontend/src/lib/api.ts` (the getRunEvents map at :562-565),
  `frontend/src/lib/api.test.ts` (NEW), and `frontend/src/hooks/useRunChat.test.ts` (add one case).
  Part B touches ONLY `frontend/src/components/chat/RunChatLane.tsx` (the settled footer branch) and
  `frontend/src/components/chat/RunChatLane.test.tsx` (one new case + two reconciled cases). Task 3
  may EDIT any additional test that asserts the footer testids (grep first) — but grep currently
  shows NONE in e2e/tests/.
- Part A must NOT alter the SSE live-path mapping (`useRunStream`) — only `getRunEvents`. Do NOT touch
  the BUG-014-B SSE parser, the BUG-015 detach/reconnect logic, the reducer (`useWorkflow.ts`), or the
  BUG-017 `page.tsx` sendCommand adapter. Do NOT change the backend, the queue, or the durable persist
  (the `event_id` column is already stored correctly); do NOT add a live-queue push.
- Part B animation is CSS-ONLY (grid-template-rows 0fr->1fr reveal, ~200-250ms ease), gated by
  `prefers-reduced-motion` via the Tailwind `motion-reduce:` variant — do NOT use `motion/react` for
  this footer, and do NOT add a JS `matchMedia`/`useReducedMotion` call (so the reduced-motion path
  has no JS to throw). NOTE: `motion/react` DOES exist in the repo (ThinkingBlock/ArtifactCard use it)
  — the spec's "no lib" claim is imprecise, but its CSS-only + reduced-motion mandate is a LOCKED
  decision; honor it. Keep `data-testid="lane-adornments"` on the EXPANDED panel; add
  `lane-adornments-toggle` for the handle. Collapsed by default; local `useState` only — NO global/
  route state.
- SC-001: keep guarded components (RunChatLane is guarded) workflow-name-literal-free — key on the
  generic `runState` + pipelineState (never a workflow name). The Part A test keys on chat frame
  types / message-id strings only.
- FE is cwd-sensitive: run all `tsc` / vitest from INSIDE `frontend/`.
- :3000 IS CURRENTLY IN USE BY THE USER. The executor MUST NOT run the mocked Playwright suite (it
  needs :3000) and MUST NOT kill :3000. Verify ONLY with `npx tsc --noEmit` + vitest (jsdom, no
  server). The executor EDITS e2e specs for reconciliation but does NOT run them. Running the full
  Playwright suite + the live Bedrock proof is DEFERRED to the orchestrator (after the user finishes
  checking the app). Use `localhost:3000` (NOT 127.0.0.1) in any browser note.
- STATE.md quirk: prefer the quick-task table; if `progress:` gets clobbered, restore
  `total_phases:37 completed_phases:35 total_plans:208 completed_plans:207 percent:95`.
</constraints>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: PART A — RED->GREEN getRunEvents merge (surface event_id/seq) so the reply stops overwriting the question</name>
  <files>frontend/src/lib/api.ts, frontend/src/lib/api.test.ts, frontend/src/hooks/useRunChat.test.ts</files>
  <behavior>
    Two RED tests, then one production line flips both GREEN; all existing cases stay green.

    RED-1 — NEW `src/lib/api.test.ts`, the DIRECT gate for the fix. Mock the module's `request`
    (`vi.mock("./request-...")` or spy the exported request helper `getRunEvents` calls) so it returns
    a `RunEventsResponse` with ONE durable reply row: `{ seq: 7, event_id: "chat-reply:X", type:
    "chat_reply", payload_json: { message_id: "X", text: "A" } }` (NOTE payload_json has NO event_id).
    Call `getRunEvents("t.t.t", "run-1", 0)`; assert the single mapped frame has `data.event_id ===
    "chat-reply:X"` AND `data.seq === 7` AND `data.message_id === "X"` (payload preserved).
    FAIL-BEFORE: today's map (`data: row.payload_json ?? {}`) yields `data.event_id === undefined` and
    `data.seq === undefined` → RED on those two assertions (not a compile/import error).

    RED-2 — `useRunChat.test.ts`, the behavioral proof (build frames via the REAL getRunEvents so the
    api.ts fix flips this too). Do NOT use the file's `frame()` helper (it auto-injects event_id).
    Instead: mock `request` to return TWO durable rows in order — a USER row
    `{ seq: 6, event_id: "user-evt:X", type: "chat_message", payload_json: { message_id: "X", text:
    "Q", run_id: "run-9" } }` then the REPLY row `{ seq: 7, event_id: "chat-reply:X", type:
    "chat_reply", payload_json: { message_id: "X", text: "A", run_id: "run-9" } }`. Import the REAL
    `getRunEvents`, call it to obtain the mapped frames, then emit them in order through the hook's
    connection (`conn.emit(userFrame); conn.emit(replyFrame)` — the Test 1 idiom). Assert the transcript
    has TWO messages IN ORDER: `[0]` `role:"user"`, content "Q"; `[1]` `role:"assistant"`, content "A".
    FAIL-BEFORE: with today's getRunEvents the reply frame has no `event_id` → `upsertNarratorMessage`
    keys on `message_id "X"` → matches the user turn → overwrites in place → ONE message (role
    assistant) → RED on `expect(messages).toHaveLength(2)` and the role/order assertions.
    (If wiring the real getRunEvents into the hook test is awkward, the equivalent is to emit two raw
    frames constructed by calling getRunEvents on the two rows above — the point is the api.ts fix, not
    the hook, decides whether the reply frame carries `event_id`.)

    GREEN — after the api.ts merge (below), RED-1 and RED-2 both pass; Test 12 (:251), the send-routing
    (:140-143), and the re-fetch/Test 14 (:282-...) stay green; `npx tsc --noEmit` clean.
  </behavior>
  <action>
Write RED-1 (`src/lib/api.test.ts`) and RED-2 (`useRunChat.test.ts`) per the behavior block and run
them FIRST — both MUST be RED on the SPECIFIED assertions (data.event_id/data.seq undefined; reply
overwrites → 1 message), NOT on compile/import errors.

Then apply the ONE-LINE production fix in `src/lib/api.ts`, the getRunEvents row map (:562-565):
  FROM  `data: row.payload_json ?? {},`
  TO    `data: { ...(row.payload_json ?? {}), event_id: row.event_id, seq: row.seq },`
This spreads the payload first, then overrides with the row's authoritative `event_id` (string) +
`seq` (number) COLUMNS (RunEventRow :519-524) — the column wins over any same-named payload key, which
is correct (the column is authoritative). DurableFrame.data is `Record<string, unknown>` so this is
type-safe. Change NOTHING else in api.ts — no other export, no signature, no docstring rewrite
(optionally tighten the :548 "data = payload_json" line to note the merge).

Re-run: RED-1 + RED-2 GREEN, all existing useRunChat cases green, tsc clean. SC-001: the tests key on
chat frame types + message-id strings only — no workflow-name literal.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | tail -15</automated>
    <automated>cd frontend && npx vitest --run src/lib/api.test.ts src/hooks/useRunChat.test.ts 2>&1 | tail -40</automated>
  </verify>
  <done>api.ts:562-565 reads `data: { ...(row.payload_json ?? {}), event_id: row.event_id, seq: row.seq }`. RED-1 (getRunEvents unit: data.event_id/data.seq populated from the row) GREEN. RED-2 (useRunChat: durable user+reply frames fold into TWO ordered turns — user "Q" then assistant "A") GREEN; both were RED before the fix on the specified assertions. Test 12 + send-routing + re-fetch cases stay green. tsc clean. No SSE/useRunStream/backend change. No workflow-name literal.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: PART B — collapse the settled footer into a CSS-animated, collapsed-by-default strip + vitest + reconcile the two settled cases</name>
  <files>frontend/src/components/chat/RunChatLane.tsx, frontend/src/components/chat/RunChatLane.test.tsx</files>
  <behavior>
    A collapse vitest (RED against today's always-open footer), then the RunChatLane change makes it
    GREEN; the two existing settled cases are reconciled to expand-then-assert; no other case regresses.

    NEW collapse test (`RunChatLane.test.tsx`) on a `runState:"complete"` run with a PipelineMini
    (agents) + a DeliverableCard (deliverableFilename/version) in pipelineState (model on the :554/:627
    settled cases):
      - COLLAPSED BY DEFAULT: `getByTestId("lane-adornments-toggle")` has `aria-expanded="false"`, and
        the `lane-adornments` panel is present but `inert`/`aria-hidden="true"` (out of the tab order).
        Because jsdom has no layout, assert the collapsed state via `aria-expanded`/`inert`, NOT via
        testid absence.
      - EXPAND: `fireEvent.click(getByTestId("lane-adornments-toggle"))` → the toggle now
        `aria-expanded="true"`, the panel is no longer inert/aria-hidden, and `getByTestId(
        "lane-pipeline-mini")` + `getByTestId("lane-deliverable")` are present with their existing text
        ("Pipeline · N agents", the filename). Clicking a card still deep-links (goSteps/goPreview).
      - REDUCED-MOTION: because the animation is pure CSS (`motion-reduce:` variant, no JS matchMedia),
        the component renders without throwing — a plain render assertion suffices (no matchMedia mock).
      FAIL-BEFORE: today the settled footer renders `lane-adornments` always-open with NO toggle →
      `getByTestId("lane-adornments-toggle")` throws → RED.

    RECONCILE (same file) the two existing settled cases so they click-to-expand first:
      - "settled state renders the pipeline mini from live agents" (:554-581): insert
        `fireEvent.click(screen.getByTestId("lane-adornments-toggle"))` BEFORE the `getByTestId(
        "lane-pipeline-mini")` assertion.
      - "settled: renders the deliverable card..." (:627-661): insert the same expand click BEFORE the
        `getByTestId("lane-deliverable")` assertion.
      This is legitimate changed-behavior reconciliation (Part B intentionally hides the cards by
      default) — do NOT delete, loosen, or `.fixme` them. Do NOT touch the "building state" case
      (:521-552, a different branch) or the attachments case (:663-678, composer chips).
  </behavior>
  <action>
STEP 1 (RED): write the NEW collapse test per the behavior block and run it — it MUST be RED because
`lane-adornments-toggle` does not exist yet (getByTestId throws), NOT a compile error.

STEP 2 (GREEN): change ONLY the SETTLED branch of `renderTranscriptFooter` (RunChatLane.tsx
:1024-1051). Recommended shape (choose the cleaner of a co-located sub-component vs top-level state,
but keep React hook rules — useState must NOT be called inside the render function):
  - Add a co-located sub-component (e.g. `SettledSummaryStrip`) in RunChatLane.tsx that owns
    `const [open, setOpen] = useState(false)` and receives the already-computed `clarifyCount`,
    `agents`, `dFilename`, `dVersion`, `goSteps`, `goPreview` as props. Render:
    * a real `<button data-testid="lane-adornments-toggle" type="button" aria-expanded={open}
      aria-controls={panelId} onClick={() => setOpen(v => !v)}>` showing a compact summary + a chevron
      (ChevronRight collapsed / ChevronDown expanded, mirroring ThinkingBlock) — e.g. a short label
      plus tiny meta (`{agents.length} agents` and the deliverable filename when present). Visible
      keyboard focus (Tailwind focus-visible ring consistent with the kit).
    * the panel: `<div id={panelId} data-testid="lane-adornments" role="region" aria-hidden={!open}
      {...(!open ? { inert: "" } : {})} className="...">` wrapping the UNCHANGED `ClarifyCountRow` +
      `PipelineMini` + `DeliverableCard` (same props, same goSteps/goPreview). Animate with a CSS
      grid-rows reveal: an outer wrapper `grid transition-[grid-template-rows] duration-200 ease-out
      motion-reduce:transition-none` whose rows go `grid-rows-[0fr]` when collapsed and `grid-rows-[1fr]`
      when open, with an inner `overflow-hidden min-h-0` holding the panel. (Equivalent max-height +
      opacity is acceptable; the `motion-reduce:` gate is MANDATORY.)
  - In the settled branch, replace the always-open `<div data-testid="lane-adornments">...</div>`
    (:1036-1050) with `<SettledSummaryStrip .../>`; keep the early `return null` when
    `clarifyCount === 0 && agents.length === 0 && !dFilename` (:1033-1035) UNCHANGED. Do NOT touch the
    live branches (:1053+). Add `ChevronDown, ChevronRight` to the lucide-react import (:32).
  Then flip the two existing settled cases to expand-then-assert per the behavior block.

SC-001: no workflow-name literal (the strip keys on the generic runState/pipelineState + counts).
Do NOT use motion/react; do NOT add matchMedia/useReducedMotion.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | tail -15</automated>
    <automated>cd frontend && npx vitest --run src/components/chat/RunChatLane.test.tsx 2>&1 | tail -40</automated>
  </verify>
  <done>The settled footer is a collapsed-by-default strip: `lane-adornments-toggle` (a real button, aria-expanded=false initially, aria-controls the panel), the `lane-adornments` panel inert/aria-hidden when collapsed and revealing the unchanged PipelineMini + DeliverableCard on click via a CSS grid-rows reveal gated by `motion-reduce:`. The NEW collapse test is GREEN (RED before); the two settled cases (:554-581, :627-661) reconciled to expand-then-assert and GREEN; building/attachments/live cases untouched and green. tsc clean. No motion/react, no matchMedia. No workflow-name literal.</done>
</task>

<task type="auto">
  <name>Task 3: Reconciliation sweep — grep every footer-testid assertion; reconcile (EDIT-only) or record none; NO Playwright run</name>
  <files>(grep + edit-only; Playwright NOT run — :3000 is the user's)</files>
  <action>
Catch any OTHER test (beyond the two already reconciled in Task 2) that asserts the settled footer
cards are visible-by-default. From `frontend/`:
  - `grep -rn "lane-adornments\|lane-pipeline-mini\|lane-deliverable" e2e/ src/` — enumerate every
    assertion. (Current grep shows ZERO references in `e2e/tests/`; the only asserters are
    RunChatLane.tsx (source) + RunChatLane.test.tsx (reconciled in Task 2).)
  - For any mocked-Playwright spec OR vitest that asserts one of these testids is VISIBLE on a SETTLED
    (`complete`/`idle`) run: EDIT it to first click/`getByTestId("lane-adornments-toggle")` and expand,
    THEN assert (expand-then-assert). This is legitimate changed-behavior reconciliation — do NOT
    delete, loosen, or `.fixme` any spec. Ignore live-run branches (building/clarify/gate) — those
    never rendered `lane-adornments`.
  - The executor MUST NOT run the Playwright suite (it needs :3000, which the user is using) and MUST
    NOT kill :3000. Edit the e2e specs in place; DEFER running them to the orchestrator. Vitest edits
    (if any) are verified with vitest (jsdom, no server).
Record in the SUMMARY the exact list of files edited (or "no e2e/vitest beyond RunChatLane.test.tsx
asserts the footer testids — nothing further to reconcile").
  </action>
  <verify>
    <automated>cd frontend && grep -rn "lane-adornments\|lane-pipeline-mini\|lane-deliverable" e2e/ src/ 2>/dev/null | grep -v "RunChatLane" || echo "NO footer-testid asserters outside RunChatLane — nothing further to reconcile"</automated>
  </verify>
  <done>Every test asserting `lane-adornments`/`lane-pipeline-mini`/`lane-deliverable` visibility on a settled run either reconciled to expand-then-assert or confirmed absent. Any e2e spec edits are made in place but NOT run (Playwright deferred to the orchestrator; :3000 untouched). No spec deleted/loosened/fixme'd. SUMMARY records the edited-files list (or "none beyond RunChatLane.test.tsx").</done>
</task>

<task type="auto">
  <name>Task 4: Regression gate — tsc + targeted vitest green; Playwright + live proof DEFERRED to the orchestrator</name>
  <files>(no source edits — acceptance gate; vitest only, NO Playwright)</files>
  <action>
Prove Part A + Part B without regressing chat delivery or the settled lane, using vitest ONLY (jsdom,
needs no server). Do NOT edit source; a real red here is a problem to report, not to force green.

From `frontend/`:
  - `npx tsc --noEmit` clean.
  - `npx vitest --run src/lib/api.test.ts src/hooks/useRunChat.test.ts src/components/chat/RunChatLane.test.tsx`
    — all green (Part A getRunEvents + durable-fold; Part B collapse + the two reconciled settled
    cases; all pre-existing cases). Note: the ~8 pre-Phase-42 vitest reds in UNTOUCHED files are NOT
    regressions — do not chase them.

DO NOT run the mocked Playwright suite and DO NOT kill :3000 — the user is on :3000. Running the full
Playwright transport/chat suite (ts-chat, ts-chat-cards, ts-sse, ts-sse-resilience, ts-s.reconnect,
ts-j.streaming, ts-t.history, ts-u.revisions) + establishing the real before/after green counts +
the live Bedrock proof are ALL DEFERRED to the ORCHESTRATOR (done after the user finishes checking the
app). The orchestrator's live proof: on a COMPLETED run, send a chat question → the question AND the
Concierge reply BOTH render, in order (question then reply), NOT one overwritten bubble; the run-summary
footer is COLLAPSED by default and expands on clicking `lane-adornments-toggle`.

If a vitest goes RED: (1) a flake in an untouched pre-Phase-42 file → note it as pre-existing;
(2) a REAL Part A/B failure → the fix is incomplete, investigate within the declared scope — do NOT
delete/loosen/fixme any test.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | tail -10 && npx vitest --run src/lib/api.test.ts src/hooks/useRunChat.test.ts src/components/chat/RunChatLane.test.tsx 2>&1 | tail -30</automated>
  </verify>
  <done>tsc clean; the three targeted vitest files all green (Part A getRunEvents + durable-fold; Part B collapse + reconciled settled cases). Playwright + live proof explicitly DEFERRED to the orchestrator — the executor did NOT run Playwright and did NOT touch :3000. No file outside the declared scope changed; no test deleted/loosened/fixme'd.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| durable `run_events` read (`GET /api/runs/{id}/events`) → FE `getRunEvents` mapping | The mapping is the identity boundary for durable frames; dropping the authoritative `event_id` column collapses two distinct events (a user turn + its reply) onto one `message_id` key downstream |
| settled run-summary footer (`RunChatLane` render) → the conversation transcript's visual priority | The always-open footer occupies the last DOM slot below every reply; collapsing it is a presentation change that must not remove the cards, only defer them behind an accessible toggle |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-q0r-01 | Tampering (data collision) | `getRunEvents` (api.ts:562-565) — dropping the row `event_id`/`seq` columns lets the durable Concierge `chat_reply` (message_id === the user turn's) key on `message_id` and OVERWRITE the user's question bubble | mitigate | Merge the authoritative `event_id` + `seq` columns into the frame `data` (column wins over any same-named payload key) so `upsertNarratorMessage` keys on the distinct `chat-reply:{id}` and appends; guarded by the getRunEvents unit RED->GREEN + the useRunChat durable-fold RED->GREEN |
| T-q0r-02 | Tampering (regression) | the SSE live path (`useRunStream`) + the re-fetch cursor | accept | The change is confined to `getRunEvents`; the live mapping is a separate code path (untouched), and `data.seq` now advances `lastSeqRef` correctly. Existing Test 12 + re-fetch cases guard the fold; no backend/queue change |
| T-q0r-03 | Denial of Service (a11y lockout) | the collapsed footer panel — a keyboard/AT user could be blocked from the generated-artifact cards | mitigate | The toggle is a real `<button>` with `aria-expanded`/`aria-controls` + visible focus; the panel is `role="region"`, inert/aria-hidden only while collapsed and fully reachable on expand; animation gated by `prefers-reduced-motion` (CSS `motion-reduce:`) — the collapse test asserts the aria/inert transitions |
| T-q0r-04 | Information disclosure (hidden deliverable) | collapsing could make the deliverable card appear lost | accept | The card is not removed — it renders unchanged inside the expandable panel with its existing deep-link; the collapsed strip surfaces a summary (agent count + filename) so the artifact is discoverable one click away |
| T-q0r-SC | Tampering | npm/pip installs | accept | No new dependencies — a one-line map edit + one new vitest file + a co-located sub-component using existing lucide-react + Tailwind; `motion/react` deliberately NOT used |
</threat_model>

<verification>
- `cd frontend && npx tsc --noEmit` clean (no useRunStream / backend change).
- PART A: the getRunEvents unit test (data.event_id/data.seq populated from the row) RED before the
  api.ts merge, GREEN after; the useRunChat durable-fold test (user "Q" + assistant "A" fold into TWO
  ordered turns) RED before (1 overwritten bubble), GREEN after. Test 12, send-routing (:140-143),
  and the re-fetch/Test 14 cases stay green.
- PART B: the collapse test (collapsed by default — toggle aria-expanded=false + panel inert; click
  reveals lane-pipeline-mini + lane-deliverable; reduced-motion render doesn't throw) RED before,
  GREEN after; the two settled cases (:554-581, :627-661) reconciled to expand-then-assert and green;
  building/attachments/live cases untouched.
- Reconciliation sweep: every `lane-adornments`/`lane-pipeline-mini`/`lane-deliverable` visibility
  assertion reconciled or confirmed absent (grep shows none in e2e/tests/). Any e2e edits made in
  place but NOT run.
- SC-001: no workflow-name literal in any fix or test.
- :3000 IS THE USER'S — the executor does NOT run the mocked Playwright suite and does NOT kill :3000.
  The full Playwright transport/chat suite (ts-chat, ts-chat-cards, ts-sse, ts-sse-resilience,
  ts-s.reconnect, ts-j.streaming, ts-t.history, ts-u.revisions) + the real before/after green counts +
  the LIVE Bedrock proof are ALL DEFERRED to the ORCHESTRATOR (after the user finishes checking the
  app). Live proof: on a COMPLETED run, send a question → the question AND the reply both render, in
  order (question then reply); the footer is collapsed by default and expands on click. If it still
  fails, report it — do not silently pass.
</verification>

<success_criteria>
- api.ts:562-565: `data: { ...(row.payload_json ?? {}), event_id: row.event_id, seq: row.seq }` — the
  durable frame carries the authoritative column `event_id` + `seq`; the Concierge reply appends as its
  own assistant turn below the surviving user question, and `lastSeqRef` advances correctly.
- RunChatLane settled footer is a collapsed-by-default, CSS-animated (grid-rows, `motion-reduce:`
  gated), keyboard-accessible expandable strip (`lane-adornments-toggle` button + `lane-adornments`
  panel) revealing the unchanged PipelineMini/DeliverableCard; live branches untouched.
- Part A: getRunEvents unit + useRunChat durable-fold tests RED->GREEN; Part B: collapse test
  RED->GREEN + two settled cases reconciled; all pre-existing targeted vitest green; tsc clean.
- Exactly five files changed (api.ts, api.test.ts, useRunChat.test.ts, RunChatLane.tsx,
  RunChatLane.test.tsx) plus any e2e spec found by the grep sweep (currently none); branch stays
  feat/ui-2; no push; no commit trailer.
- No backend/queue/durable-persist change; no live-queue push; useRunStream / BUG-014-B parser /
  BUG-015 detach / reducer / BUG-017 page.tsx adapter untouched.
- Playwright + the live proof DEFERRED to the orchestrator; :3000 never touched by the executor.
</success_criteria>

<output>
Create `.planning/quick/260717-q0r-fix-bug-018-bug-017-follow-up-frontend-o/SUMMARY.md` when done.
</output>
