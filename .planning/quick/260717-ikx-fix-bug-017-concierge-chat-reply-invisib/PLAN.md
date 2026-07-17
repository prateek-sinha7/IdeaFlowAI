---
phase: quick-260717-ikx
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/hooks/useRunChat.test.ts
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/hooks/useRunChat.ts
autonomous: true
requirements:
  - BUG-017
must_haves:
  truths:
    - "BUG-017: the dashboard chat `sendCommand` adapter (page.tsx:1027-1029) AWAITS the underlying `runConnection.sendCommand` POST instead of `void`-ing it — so `useRunChat.sendMessage`'s `await sendCommand(...)` (useRunChat.ts:366) resolves only AFTER the Concierge POST completes and the `chat_reply` is persisted, and the DEF-44-12-2 re-fetch (useRunChat.ts:368-370) lands AFTER the reply exists → the reply folds and renders as its own assistant turn on a completed run (no reopen needed)."
    - "BUG-017 (no regression): the adapter still returns `Promise<void>` and still DISCARDS `runConnection.sendCommand`'s resolved value (the launched run_id the W1/44-01 launch->attach path uses); the chat up-channel ignores that value exactly as before. The optimistic user bubble + synchronous `return messageId` (useRunChat.ts:377) are unaffected — Test 5 send-routing (useRunChat.test.ts:140-143) stays green."
    - "BUG-017 (ordering guard): a NEW vitest proves the contract the fix restores — given a `sendCommand` that resolves on a DEFERRED promise, `useRunChat` invokes `fetchEvents` ONLY AFTER `sendCommand` resolves; the CURRENT void-adapter shape (a sync-resolving adapter) calls `fetchEvents` before the send settles (the RED fail-before). The existing DEF-44-12-2 re-fetch test (Test 13) stays green."
    - "BUG-017 (scope): FRONTEND-ONLY — no backend/engine/queue change; no live-queue push added for the Concierge reply (durable-only persist + re-fetch is the intended design). Only the adapter (and, if strictly required for tsc, the `sendCommand` prop type) is touched. The BUG-014-B parser, BUG-015 detach/reconnect logic, and the reducer are untouched. Concierge mis-grounding + ~11s latency are OUT OF SCOPE."
  artifacts:
    - path: "frontend/src/app/dashboard/page.tsx"
      provides: "sendCommand adapter that awaits runConnection.sendCommand (returns Promise<void>, discards the resolved run_id) instead of voiding it"
      contains: "await runConnection.sendCommand"
    - path: "frontend/src/hooks/useRunChat.test.ts"
      provides: "RED->GREEN ordering test: deferred sendCommand + fetchEvents spy; fetchEvents fires ONLY after sendCommand resolves (fail-before: void/sync adapter fires it early). Existing Test 5 + Test 13 stay green."
      contains: "fetchEvents"
  key_links:
    - from: "dashboard chat config sendCommand adapter (page.tsx:1027-1029)"
      to: "runConnection.sendCommand POST (RunConnectionProvider.tsx:362-393, resolves after the reply is persisted)"
      via: "await (not void) — the adapter returns the awaited Promise<void>"
      pattern: "await runConnection\\.sendCommand"
    - from: "useRunChat.sendMessage await sendCommand (useRunChat.ts:366)"
      to: "the DEF-44-12-2 re-fetch fetchEvents(runId, lastSeq) (useRunChat.ts:368-370)"
      via: "the awaited adapter now blocks until the reply is persisted, so the re-fetch lands after chat_reply exists"
      pattern: "await sendCommand"
---

<objective>
Fix BUG-017 — the Concierge chat reply never renders on a COMPLETED run. Implement EXACTLY
the grounded spec in `.planning/BUG-017-GROUNDED-CONTEXT.md` — the root cause is verified to
file:line AND live-reproduced (Concierge POST 11.15s; re-fetch fired at +0.34s). Do NOT
re-investigate or re-debug.

The bug is a FRONTEND delivery race, ~1 line. The Concierge reply IS produced and IS persisted
durably (`run_commands.py:988`, ~1690 chars), durable-only with NO live-queue push — so the sole
delivery path is the DEF-44-12-2 re-fetch-after-send in `useRunChat.ts:365-375`. But the dashboard
adapter that wires `sendCommand` (`page.tsx:1027-1029`) `void`s the async POST promise and returns
`undefined`, so the hook's `await sendCommand(...)` (useRunChat.ts:366) resolves IMMEDIATELY and the
re-fetch fires (+0.34s) BEFORE the POST completes (11.15s) and the `chat_reply` is persisted →
nothing folds in, no second re-fetch is ever triggered, the reply never renders (only a later reopen
re-fetches all durable events and surfaces it).

Fix (FE-only, single edit): make the adapter AWAIT and return the POST promise instead of voiding
it. `runConnection.sendCommand` (RunConnectionProvider.tsx:362-393) is `async` and for a `/messages`
turn resolves only after the backend persists the reply — awaiting it is exactly what makes the
re-fetch land after the reply exists, so it folds and renders as its own assistant turn.

Purpose: the reply becomes visible on a completed run without a reopen.
Output: the one-line page.tsx adapter edit (`void` → `await`, still returns `Promise<void>`, still
discards the resolved run_id) plus a RED->GREEN vitest proving the send-then-fetch ordering, plus a
regression pass over the chat + transport mocked e2e.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@.planning/BUG-017-GROUNDED-CONTEXT.md

# THE FIX SITE. The chat config passed to useRunChat: runId precedence :1022, the sendCommand
# adapter :1027-1029 (the ONLY line to change — void -> await), the comment above it :1024-1026,
# and the DEF-44-12-2 fetchEvents wiring :1033-1038. runConnection is the RunConnectionProvider
# value consumed here. Do NOT touch the fetchEvents wiring or any other config field.
@frontend/src/app/dashboard/page.tsx

# THE CONSUMER (do NOT change beyond the contingent prop type). sendMessage awaits the up-channel
# THEN re-fetches: `await sendCommand(runId, payload)` :366, `fetchEvents(...)` folded via handleFrame
# :368-370, `return messageId` :377 (synchronous, unaffected). The sendCommand prop type is ALREADY
# `Promise<void> | void` (:61-64) — so an awaiting adapter returning Promise<void> is already
# assignable and tsc SHOULD be clean; only widen this type if tsc actually complains.
@frontend/src/hooks/useRunChat.ts

# THE TEST HARNESS to EXTEND (do NOT rewrite existing cases). makeConn() (:26-43) gives a
# controllable subscribe + a `sendCommand = vi.fn(async () => {})` spy. Test 5 (:126-152, the send-
# routing assertion at :140-143) and Test 13 (:282-323, the DEF-44-12-2 re-fetch/fold) MUST stay
# green. Model the new ordering test on Test 13 (it already wires fetchEvents + await act).
@frontend/src/hooks/useRunChat.test.ts

# THE UP-CHANNEL the adapter wraps (context only — do NOT edit). sendCommand is `async` and for a
# /messages turn resolves only AFTER the backend responds (i.e. after the reply is persisted). It
# resolves to the launched run_id (W1/44-01), which the chat adapter discards.
@frontend/src/providers/RunConnectionProvider.tsx
</context>

<constraints>
- Branch feat/ui-2. Verify with `git rev-parse --abbrev-ref HEAD`; DO NOT switch. NO commit trailer
  (no Co-Authored-By / Claude-Session). NEVER push. Worktrees OFF (sequential).
- STRICT SCOPE — touch ONLY: `page.tsx` (the sendCommand adapter at :1027-1029) and
  `useRunChat.test.ts` (add the ordering test). `useRunChat.ts` is touched ONLY IF `tsc` complains
  about the `Promise<void>` return (widen the prop return type at :61-64 to `void | Promise<void>`,
  do NOT change the `await` call site) — the prop type is already `Promise<void> | void`, so this is
  NOT expected to be needed; leave `useRunChat.ts` untouched if tsc is clean.
- Do NOT refactor `useRunChat.sendMessage`, the re-fetch block, `handleFrame`, or the fetchEvents
  wiring. Do NOT touch the BUG-014-B parser (CRLF split + envelope unwrap), the BUG-015
  `detachRun`/reconnect logic, or the reducer (`useWorkflow.ts` / `handlePipelineMessage`).
- Do NOT add a live-queue push for the Concierge reply — it would create an orphan queue that falsely
  marks a terminal run live; the durable-only persist + re-fetch is the intended design.
- OUT OF SCOPE (separate follow-ups, do NOT do here): Concierge mis-grounding (a completed run
  described as "IN PROGRESS", backend `concierge.py` read_events); the ~11s Concierge latency; an
  optional pending/spinner state on the ASK turn.
- SC-001: `page.tsx` is exempt; keep any change workflow-name-literal-free (the test keys on chat
  frame types / run-id strings only).
- FE is cwd-sensitive: run all `tsc` / vitest / Playwright from INSIDE `frontend/`. Kill anything on
  :3000 before mocked Playwright (`lsof -ti:3000 | xargs kill -9 2>/dev/null || true`).
  `npm run e2e` = `playwright test --project=mocked`.
- Do NOT run a live Bedrock run and do NOT restart the backend — the ORCHESTRATOR does the live proof
  after (send a chat ASK on a completed run; the reply must render without a reopen).
- The "132/0" mocked baseline is STALE — establish the REAL green count by RUNNING the listed specs
  BEFORE and AFTER the change; a spec green-before / red-after is the only regression signal.
- STATE.md quirk: prefer the quick-task table; if `progress:` gets clobbered, restore
  `total_phases:37 completed_phases:35 total_plans:208 completed_plans:207 percent:95`.
</constraints>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — ordering vitest (fetchEvents fires only AFTER sendCommand resolves)</name>
  <files>frontend/src/hooks/useRunChat.test.ts</files>
  <behavior>
    EXTEND `useRunChat.test.ts` (do NOT rewrite existing cases). Add ONE test that proves the
    send-then-fetch ORDERING contract BUG-017 restores. Model it on Test 13 (:282-323), which already
    wires `fetchEvents` + `await act`.

    Test 14 — the ordering guard (RED today against the current void-adapter shape):
      - Build a DEFERRED up-channel: a `deferred()` helper returning `{ promise, resolve }`; an
        `innerSend = vi.fn(() => deferred.promise)` that mimics `runConnection.sendCommand` (resolves
        ONLY when the test calls `resolve()`).
      - Pass `sendCommand` as an ADAPTER that mirrors page.tsx. For the RED run, wire the adapter in
        the CURRENT (buggy) shape: `sendCommand: (r, p) => { void innerSend(r, p); }` — it voids the
        deferred and returns `undefined`.
      - Wire a `fetchEvents = vi.fn(async () => [])` spy and render
        `useRunChat({ runId: "run-9", subscribe: conn.subscribe, sendCommand, fetchEvents })`.
      - Drive: `await act(async () => { result.current.sendMessage("ask the concierge"); await Promise.resolve(); })`
        (flush a microtask WITHOUT resolving the deferred).
      - ASSERT (the ordering): `expect(innerSend).toHaveBeenCalledTimes(1)` AND — the load-bearing
        assertion — `expect(fetchEvents).not.toHaveBeenCalled()` (the send has NOT settled, so the
        re-fetch must NOT have run yet).
      - Then `await act(async () => { deferred.resolve(); await deferred.promise; })` and assert
        `expect(fetchEvents).toHaveBeenCalled()` (the re-fetch runs ONLY after the send resolves).
      - FAIL-BEFORE (RED): with the void/sync adapter shape, the hook's `await sendCommand(...)`
        awaits `undefined` and resolves immediately → `fetchEvents` is called on the first microtask,
        BEFORE `deferred.resolve()` → `expect(fetchEvents).not.toHaveBeenCalled()` FAILS. This is
        exactly the page.tsx bug reproduced in miniature.

    Existing cases stay green: Test 5 send-routing (:140-143) and Test 13 re-fetch/fold (:282-323).
  </behavior>
  <action>Add Test 14 to `useRunChat.test.ts` per the behavior block, wiring the `sendCommand` adapter
in the CURRENT page.tsx shape (`(r, p) => { void innerSend(r, p); }`) so the ordering assertion is RED
against today's code. Do NOT edit any production source in this task — the failure MUST be on the
`expect(fetchEvents).not.toHaveBeenCalled()` assertion, NOT on an import/compile error. SC-001: the
test keys on chat frame types / run-id strings only — no workflow-name literal.</action>
  <verify>
    <automated>cd frontend && npx vitest --run src/hooks/useRunChat.test.ts 2>&1 | tail -40</automated>
  </verify>
  <done>Test 14 is RED — it fails on `expect(fetchEvents).not.toHaveBeenCalled()` (fetchEvents fired before the deferred send resolved), NOT on a compile/import error. Test 5 (:140-143) and Test 13 (:282-323) are GREEN. No workflow-name literal.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — one-line page.tsx adapter fix (void → await) + flip the test adapter + verify</name>
  <files>frontend/src/app/dashboard/page.tsx, frontend/src/hooks/useRunChat.test.ts, frontend/src/hooks/useRunChat.ts</files>
  <behavior>Test 14 goes GREEN (fetchEvents fires only after the deferred send resolves), Test 5 + Test 13 stay GREEN, `npx tsc --noEmit` is clean.</behavior>
  <action>
FIX — `page.tsx:1027-1029`, the sendCommand adapter. Change it from voiding the POST promise to
awaiting and returning it (still `Promise<void>`, still discarding the resolved run_id):
  FROM  `sendCommand: (runId, payload) => { void runConnection.sendCommand(runId, payload); },`
  TO    `sendCommand: async (runId, payload) => { await runConnection.sendCommand(runId, payload); },`
Now `useRunChat.sendMessage`'s `await sendCommand(...)` (:366) blocks until the POST resolves (after
the reply is persisted) → the DEF-44-12-2 re-fetch (:368-370) lands after `chat_reply` exists → it
folds via handleFrame and renders as its own assistant turn. Change NOTHING else in the config — the
runId precedence (:1022), the comment (:1024-1026 — you may update its wording to reflect the await),
and the fetchEvents wiring (:1033-1038) stay as-is.

TEST — update Test 14's adapter mirror to the SHIPPED shape so it verifies the restored contract:
  change the test's `sendCommand` adapter from `(r, p) => { void innerSend(r, p); }` to
  `async (r, p) => { await innerSend(r, p); }` (mirrors the page.tsx fix). Test 14 now goes GREEN:
  fetchEvents is NOT called until `deferred.resolve()`, then IS called. Leave the assertions unchanged.

TYPE (CONTINGENT — likely unneeded): run `npx tsc --noEmit`. The `sendCommand` prop type is already
`Promise<void> | void` (useRunChat.ts:61-64), so an awaiting adapter returning `Promise<void>` is
already assignable and tsc should be clean. ONLY IF tsc complains about the `Promise<void>` return,
widen that prop return type to `void | Promise<void>` — do NOT change the `await` call site (:366),
which already tolerates both. If tsc is clean, leave `useRunChat.ts` untouched.

Do NOT put fenced code in the source beyond these edits; touch no other logic; do NOT add a live-queue
push. SC-001: no workflow-name literal.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | tail -15</automated>
    <automated>cd frontend && npx vitest --run src/hooks/useRunChat.test.ts 2>&1 | tail -30</automated>
  </verify>
  <done>`page.tsx:1027-1029` reads `sendCommand: async (runId, payload) => { await runConnection.sendCommand(runId, payload); }` (returns Promise<void>, discards the run_id). `tsc --noEmit` clean (useRunChat.ts untouched unless tsc forced the prop-type widen). Test 14 GREEN (fetchEvents only after the deferred send resolves); Test 5 (:140-143) + Test 13 (:282-323) GREEN. No workflow-name literal. No file outside the declared scope changed.</done>
</task>

<task type="auto">
  <name>Task 3: Regression gate — tsc + useRunChat vitest + mocked chat/transport e2e green</name>
  <files>(no source edits — acceptance gate)</files>
  <action>
Prove the one-line fix delivers the reply without regressing the chat up-channel or the SSE transport.
Do NOT edit source; a real red here signals a problem to report, not to force green.

FRONTEND (from `frontend/`): `npx tsc --noEmit` clean; `npx vitest --run src/hooks/useRunChat.test.ts`
green (Test 14 + Test 5 + Test 13 + all others). Then KILL :3000
(`lsof -ti:3000 | xargs kill -9 2>/dev/null || true`) and run the mocked chat + transport e2e:
ts-chat, ts-chat-cards, ts-sse, ts-sse-resilience, ts-s.reconnect, ts-j.streaming, ts-t.history,
ts-u.revisions. Establish the REAL green count by comparing to a pre-change run of the SAME specs
(the 132/0 baseline is stale). A spec green-before / red-after is the ONLY regression signal.

If a spec goes RED: (1) selector/text-drift flake unrelated to the change → note it + re-run to
confirm it is pre-existing (green-before AND red-after on the current commit vs the pre-change commit);
(2) a REAL chat-delivery / transport failure → the fix is wrong, investigate and fix within the
declared scope — do NOT delete, loosen, or `.fixme` any spec to force green.

Executor does NOT run live Bedrock and does NOT restart the backend — the ORCHESTRATOR owns the live
proof (send a chat ASK on a completed run; the reply renders as its own turn without a reopen).
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | tail -10 && npx vitest --run src/hooks/useRunChat.test.ts 2>&1 | tail -20</automated>
    <automated>cd frontend && (lsof -ti:3000 | xargs kill -9 2>/dev/null || true) && npx playwright test --project=mocked e2e/tests/ts-chat.spec.ts e2e/tests/ts-chat-cards.spec.ts e2e/tests/ts-sse.spec.ts e2e/tests/ts-sse-resilience.spec.ts e2e/tests/ts-s.reconnect.spec.ts e2e/tests/ts-j.streaming.spec.ts e2e/tests/ts-t.history.spec.ts e2e/tests/ts-u.revisions.spec.ts 2>&1 | tail -40</automated>
  </verify>
  <done>tsc clean; useRunChat vitest all green (Test 14 GREEN, Test 5 + Test 13 green); the eight mocked chat/transport e2e (ts-chat, ts-chat-cards, ts-sse, ts-sse-resilience, ts-s.reconnect, ts-j.streaming, ts-t.history, ts-u.revisions) are no worse than the pre-change run of the same specs. No spec deleted / loosened / fixme'd. No file outside the declared scope changed.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| dashboard chat adapter (`page.tsx` sendCommand) → `runConnection.sendCommand` REST POST | The adapter mediates the chat up-channel; voiding the async POST promise decouples the hook's `await` from actual POST completion, so the durable-only re-fetch races ahead of the persisted reply |
| `useRunChat.sendMessage` await → the DEF-44-12-2 durable re-fetch | The re-fetch is the SOLE delivery path for the durable-only Concierge reply; if it fires before the reply is persisted, nothing folds and no retry occurs |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-ikx-01 | Denial of Service (lost delivery) | `page.tsx:1027-1029` sendCommand adapter — `void`ing the POST promise makes `await sendCommand` resolve immediately, so the re-fetch (+0.34s) races the persisted reply (11.15s) and the Concierge answer never renders on a completed run | mitigate | Make the adapter `async` and `await runConnection.sendCommand(...)` so the hook's `await` blocks until the reply is persisted; the re-fetch then lands after `chat_reply` exists and folds. Guarded by the Test 14 ordering RED->GREEN |
| T-ikx-02 | Tampering (regression) | the launch->attach (W1/44-01) path that reads `runConnection.sendCommand`'s resolved run_id | accept | The adapter still returns `Promise<void>` and still DISCARDS the resolved value; the launch->attach path calls `runConnection.sendCommand` at a DIFFERENT call site (not through `useRunChat.sendMessage`), so it is untouched. Test 5 send-routing guards the synchronous optimistic path |
| T-ikx-03 | Tampering (orphan liveness) | the terminal run's SSE liveness — an accidental live-queue push for the Concierge reply would falsely mark a completed run live | accept | Scope fence forbids any queue/backend change; delivery stays durable-only + re-fetch (the intended design). No code path added |
| T-ikx-SC | Tampering | npm/pip installs | accept | No new dependencies; a one-line adapter edit + one new vitest (+ a contingent one-line prop-type widen only if tsc forces it) |
</threat_model>

<verification>
- `cd frontend && npx tsc --noEmit` clean (useRunChat.ts untouched unless tsc forced the contingent prop-type widen).
- BUG-017 ordering: Test 14 RED before Task 2 (fetchEvents fires before the deferred send resolves), GREEN after (fetchEvents fires ONLY after the send resolves).
- No regression: Test 5 send-routing (:140-143) and Test 13 DEF-44-12-2 re-fetch (:282-323) stay green.
- Regression gate: the eight mocked chat/transport e2e (ts-chat, ts-chat-cards, ts-sse, ts-sse-resilience, ts-s.reconnect, ts-j.streaming, ts-t.history, ts-u.revisions) are no worse than a pre-change run of the SAME specs (the 132/0 baseline is stale — measure before/after).
- SC-001: no workflow-name literal in the fix or the test.
- Live proof is the ORCHESTRATOR's (after applying the fix): send a chat ASK on a COMPLETED run → the Concierge reply renders as its own assistant turn WITHOUT a reopen. If it still fails, report it — do not silently pass.
</verification>

<success_criteria>
- `page.tsx:1027-1029`: `sendCommand: async (runId, payload) => { await runConnection.sendCommand(runId, payload); }` — awaits and returns the POST promise (Promise<void>), still discards the resolved run_id.
- `useRunChat`'s `await sendCommand(...)` now blocks until the reply is persisted, so the DEF-44-12-2 re-fetch lands after `chat_reply` exists and the reply folds/renders on a completed run.
- Test 14 (deferred sendCommand + fetchEvents spy) proves fetchEvents fires ONLY after sendCommand resolves — RED before the fix, GREEN after; Test 5 + Test 13 stay green.
- Exactly two files changed (page.tsx + useRunChat.test.ts); useRunChat.ts touched ONLY if tsc forced the prop-type widen; branch stays feat/ui-2; no push; no commit trailer.
- No backend/queue change; no live-queue push; the BUG-014-B parser, BUG-015 detach logic, and the reducer untouched; Concierge mis-grounding + latency deferred.
</success_criteria>

<output>
Create `.planning/quick/260717-ikx-fix-bug-017-concierge-chat-reply-invisib/SUMMARY.md` when done.
</output>
