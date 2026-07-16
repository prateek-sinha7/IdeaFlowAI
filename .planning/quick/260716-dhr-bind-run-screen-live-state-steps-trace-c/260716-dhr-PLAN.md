---
phase: 260716-dhr
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/lib/api.ts
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/hooks/useRunChat.ts
  - frontend/src/hooks/useRunChat.test.ts
  - frontend/e2e/fixtures/dashboard.ts
  - frontend/e2e/tests/ts-live-state.spec.ts
autonomous: true
requirements: [DEF-44-12-4, DEF-44-12-2]

must_haves:
  truths:
    - "Opening a still-running run from history renders its Steps pipeline trace (not the empty 'Start a pipeline…' placeholder)"
    - "Opening a terminal run renders its deliverable in Preview AND its prior chat turns in the transcript"
    - "Sending a Concierge turn on an opened run POSTs to /api/runs/{id}/messages and the reply renders as its OWN assistant turn (the user's question bubble is preserved, not overwritten)"
    - "The launch→watch flow still renders the launched run's live trace unchanged"
  artifacts:
    - path: "frontend/src/lib/api.ts"
      provides: "getRunEvents(token, runId, afterSeq) durable-events fetch helper mapping rows to { type, data } frames"
      contains: "export async function getRunEvents"
    - path: "frontend/src/app/dashboard/page.tsx"
      provides: "handleSelectWorkflowRun seeds the pipeline reducer + runInput + prior transcript on open"
      contains: "getRunEvents"
    - path: "frontend/src/hooks/useRunChat.ts"
      provides: "re-fetch-after-send + event_id-keyed assistant bubble + seedTranscript imperative"
      contains: "fetchEvents"
    - path: "frontend/e2e/fixtures/dashboard.ts"
      provides: "shared openHistory + stubRunEvents history-open helpers"
      contains: "openHistory"
    - path: "frontend/e2e/tests/ts-live-state.spec.ts"
      provides: "coverage for live-open trace, terminal-open deliverable+prior-chat+concierge-reply, launch→watch regression"
      contains: "renders its own turn"
  key_links:
    - from: "frontend/src/app/dashboard/page.tsx"
      to: "getRunEvents → handleWebSocketMessage"
      via: "fetch durable events on open, replay pipeline frames through the page router so seenEventIdsRef dedups the live tail"
      pattern: "getRunEvents\\("
    - from: "frontend/src/hooks/useRunChat.ts"
      to: "sendCommand → fetchEvents → handleFrame"
      via: "await the up-channel, then fetch events since last seq and fold each through handleFrame"
      pattern: "fetchEvents\\("
    - from: "frontend/src/hooks/useRunChat.ts"
      to: "upsertNarratorMessage id"
      via: "key the assistant bubble on data.event_id (chat-reply:{message_id}) instead of data.message_id"
      pattern: "event_id"
---

<objective>
Bind the run-screen live state — the Steps pipeline trace AND the chat transcript — to the run the user is VIEWING, not only the run they launched in-session. Today `handleSelectWorkflowRun` sets `contentSourceRunId` (drives Preview/Files/durable content) but never seeds or re-points the two live consumers (the pipeline reducer from `useWorkflow`, and the `useRunChat` transcript). Result: a history-opened running run shows the empty Steps placeholder, and a Concierge reply on an opened run never renders (durable-only persist, no queue → the SSE live-tail never carries it).

Fix is FRONTEND-ONLY, in three coordinated pieces over one shared primitive (a durable-events fetch helper), exactly as designed and root-caused in @.planning/DEF-44-12-4-GROUNDED-CONTEXT.md (verified to file:line by 4 investigation agents — do NOT re-investigate).

Purpose: closes DEF-44-12-4 (Steps trace on opened run) and subsumes DEF-44-12-2 (Concierge reply not rendering on opened run) — the class of FE run-state binding bugs the WS→SSE cutover exposed.
Output: `getRunEvents` helper; trace seed + transcript seed on open; Concierge reply render via re-fetch-after-send + assistant-id de-collision; lifted shared history-open e2e helpers + new coverage; established real green baseline.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/DEF-44-12-4-GROUNDED-CONTEXT.md
@CLAUDE.md
@backend/CLAUDE.md

# Source the tasks edit (anchors verified to hold on feat/ui-2):
@frontend/src/lib/api.ts
@frontend/src/app/dashboard/page.tsx
@frontend/src/hooks/useRunChat.ts
@frontend/src/hooks/useRunChat.test.ts
@frontend/src/lib/wsReplayState.ts
@frontend/src/components/layout/DashboardLayout.tsx
@frontend/e2e/fixtures/dashboard.ts
@frontend/e2e/tests/ts-t.history.spec.ts

# Read-only reference (the durable endpoint the helper hits — NO change):
@backend/app/api/runs.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Establish the real green baseline, then add the getRunEvents durable-events fetch helper</name>
  <files>frontend/src/lib/api.ts</files>
  <action>
FIRST, from inside `frontend/` with any dev server on port 3000 killed (Playwright starts its own), run the affected mocked specs ONCE and record the pass/skip counts as the pre-edit baseline (the "132/0" figure is STALE — do not trust it): `ts-j.streaming`, `ts-sse`, `ts-sse-resilience`, `ts-s.reconnect`, `ts-chat`, `ts-chat-cards`, `ts-t.history`, `ts-u.revisions`. Also record the vitest baseline for `useRunChat`, `useWorkflow*`, `RunChatLane`, `revisionFamilyLinkage.source`, `AgentThinkingTab`. Note the exact numbers in the SUMMARY — the final verify must match-or-exceed them.

THEN add `export async function getRunEvents(token: string, runId: string, afterSeq = 0)` to `frontend/src/lib/api.ts`, following the EXISTING `getRunFamily`/`getRunSummary` shape (`request<T>(path, { method: "GET", headers: authHeaders(token) })`). It hits the durable endpoint `GET /api/runs/{id}/events?after={afterSeq}` (owner-scoped, backend `runs.py:858-909`, read-only) whose response is `{ workflow_id, after, events: [{ seq, event_id, type, payload_json }] }` — the SAME rows the SSE replays. Return an array of frames shaped `{ type: string; data: Record<string, unknown> }`, mapping each row to `{ type: row.type, data: row.payload_json }`. DEFENSIVELY tolerate a missing/empty `events` array (map over `events ?? []`) so the mock catch-all's `{}` (and any legacy shape) yields `[]` rather than throwing. Add a typed response interface mirroring the wire shape (unnormalized snake_case, like the neighbours). Do NOT normalize payloads — downstream consumers dedup by `event_id`, so a fresh fetch at `after=0` returning full history is idempotent by design.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit</automated>
  </verify>
  <done>Baseline pass/skip counts recorded in the working notes; `getRunEvents` exported from api.ts, returns `{ type, data }[]`, tolerates an empty/absent `events`, and `npx tsc --noEmit` is clean.</done>
</task>

<task type="auto">
  <name>Task 2: Piece 1 — seed the Steps trace + runInput on open (Half A)</name>
  <files>frontend/src/app/dashboard/page.tsx, frontend/src/components/layout/DashboardLayout.tsx</files>
  <action>
In `handleSelectWorkflowRun` (`page.tsx:1159-1253`), AFTER `setContentSourceRunId(fullRun.id)` (`:1181`), add a trace-seed step GUARDED on `fullRun.id !== pipelineState.pipelineRunId`. When (and only when) the opened run differs from the live launched run:
  1. Reset the per-run FE replay state via the EXISTING `resetReplayState({ seen: seenEventIdsRef.current, setLastSeq: (n) => { lastSeqRef.current = n; }, setWaveGroups })` (the same primitive fired on `pipeline_start` at `page.tsx:462-470`) so the prior run's seen-set / cursor / wave groups do not poison the new view. Also call `resetPipeline()` so the reducer's `agents[]` starts empty before the seed (mirrors the launch path's `startPipeline` reset at `useWorkflow.ts:59-70`).
  2. Fetch `getRunEvents(currentToken, fullRun.id)` and replay each frame through the page's `handleWebSocketMessage({ type: frame.type, data: frame.data } as StreamMessage)` — NOT the bare reducer — so each `event_id` lands in `seenEventIdsRef` (`page.tsx:322` `shouldApplyEvent`) and the subsequently-attached live SSE tail is deduped (no double-count). This reconstructs `pipelineState` deterministically: the seeded `pipeline_start` builds `agents[]`, then the `agent_*` frames fill it. Works for BOTH a live-opened run (durable seed + live tail continues) and a terminal-opened run (durable seed is the whole trace, no tail).
Wrap the fetch/replay in the existing try/catch (log-and-continue on failure — a fetch error must not break the reopen content path already set above).

For `runInput`: wire the VIEWED run's brief into the Steps surface. On the history-open path (`fullRun.id !== pipelineState.pipelineRunId`), set the launched-brief state to the viewed run's input — `setSubmittedBrief(fullRun.input ?? "")` — so `DashboardLayout.tsx:1798` (`runInput={submittedBrief}`) and `AgentThinkingTab`'s `hasAnyData` gate reflect the opened run, not a stale launched brief. Do NOT change the `runInput` prop wiring in DashboardLayout unless a cleaner viewed-input thread is warranted; prefer the minimal `setSubmittedBrief` set (single source, already the "current run's brief" on the live path). If DashboardLayout is touched, keep it workflow-name-literal-free per SC-001 (it is a guarded/generic layout) — this task adds no such literal.

CRITICAL — `handleSelectWorkflowRun` currently closes over an empty dep array (`page.tsx:1252`). Adding references to `pipelineState.pipelineRunId`, `resetPipeline`, `setWaveGroups`, `handleWebSocketMessage`, `seenEventIdsRef`/`lastSeqRef` (refs are stable) means the `useCallback` deps MUST be updated so the closure sees current values — add the non-ref values (`pipelineState.pipelineRunId`, `resetPipeline`, `setWaveGroups`, `handleWebSocketMessage`, `setSubmittedBrief`) to the dependency array. Verify no stale-closure bug: the guard compares against the CURRENT `pipelineState.pipelineRunId`.

Do NOT re-seed when `fullRun.id === pipelineState.pipelineRunId` (the live launched run already holds the trace; a re-seed would replay-from-0 over live progress and wipe gate/questionnaire state via the `pipeline_start` reset side effects at `page.tsx:462-483`). page.tsx is SC-001 EXEMPT.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit</automated>
  </verify>
  <done>Opening a run whose id differs from `pipelineState.pipelineRunId` resets replay state, fetches `getRunEvents`, replays every frame through `handleWebSocketMessage`, and sets `submittedBrief` to `fullRun.input`; the same-id (live launched) case is skipped; `useCallback` deps updated; tsc clean. Behavioral proof lands in Task 5 coverage (a).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Piece 2 — render the Concierge reply on an opened run (Half B = DEF-44-12-2)</name>
  <files>frontend/src/hooks/useRunChat.ts, frontend/src/hooks/useRunChat.test.ts, frontend/src/app/dashboard/page.tsx</files>
  <behavior>
    - De-collision: a `chat_reply` frame whose `data.event_id` ("chat-reply:{id}") differs from a prior user turn's `message_id` (== the reply's `data.message_id`) appends as its OWN assistant turn — the user question bubble is preserved (role stays "user", text intact). A reply with no `event_id` still folds by `message_id` (family-anchoring Test 6 at useRunChat.test.ts:154-168 stays green).
    - Re-fetch-after-send: `sendMessage` still returns the client message_id synchronously and still calls `sendCommand(runId, { text, message_id, … })` with the same args (Test 5 :126-152, at-risk :140-143 stays green). When a `fetchEvents` is provided, after the up-channel resolves it fetches events since the last seen seq and folds each through `handleFrame`; the per-hook `event_id` dedup makes it idempotent (no duplicate reply, no duplicate echo).
    - `fetchEvents` absent (existing tests that omit it) → behaviour is byte-identical to today (no crash).
  </behavior>
  <action>
In `frontend/src/hooks/useRunChat.ts`:
  1. De-collide the assistant bubble id in `upsertNarratorMessage` (`:207-235`): key the message `id` on the frame's DISTINCT `data.event_id` when present, falling back to `data.message_id` (then a minted id) — `id = (typeof data.event_id === "string" && data.event_id) ? data.event_id : (message_id ?? mint)`. This is ALSO the correct idempotency key (the same one `handleFrame` dedups on at `:250-253`), so the reply appends instead of matching-and-overwriting the user's question (the landmine: the reply carries `message_id === body.message_id`, `run_commands.py:994`). Do NOT change `upsertUserMessage` — the user echo must still reconcile by `message_id` (Test 5).
  2. Add an OPTIONAL `fetchEvents?: (runId: string | null, afterSeq: number) => Promise<RunChatFrame[]>` to `UseRunChatConfig` and destructure it. Track a per-hook `lastSeqRef` (a `useRef<number>(0)`) advanced inside `handleFrame` from `data.seq` when it is a larger number (mirrors the page's `lastSeqRef` at `page.tsx:328-331`).
  3. Re-fetch-after-send in `sendMessage` (`:280-325`): keep the synchronous optimistic render and the synchronous `return messageId`. Replace `void sendCommand(runId, payload)` (`:320`) with a fire-and-forget async that awaits the up-channel and THEN, IF `fetchEvents` is defined, awaits `fetchEvents(runId, lastSeqRef.current)` and folds each returned frame through `handleFrame` (dedup guarantees idempotency; covers BOTH terminal and live opened runs — the reply is durably persisted either way, so NO backend queue-put is needed). The `legacyWsSend` branch is unchanged. `sendCommand`/`fetchEvents` must be included in the `sendMessage` `useCallback` deps.
In `frontend/src/app/dashboard/page.tsx`: pass `fetchEvents: (runId, afterSeq) => getRunEvents(getToken() ?? "", runId ?? "", afterSeq)` into the existing `useRunChat({ … })` config (`:925-944`), returning the frame array (the page already imports the token accessor; import `getRunEvents`). Keep the existing `sendCommand` wrapper (`:938-940`) and `runId` precedence (`:933`) intact.
Add vitest cases to `frontend/src/hooks/useRunChat.test.ts`: (a) a `chat_reply` with `event_id` distinct from a prior user turn's `message_id` appends a 2nd turn and leaves the user turn's role/text unchanged; (b) `sendMessage` with a stubbed `fetchEvents` returning a `chat_reply` folds it through `handleFrame` after send, and a second identical fetch is deduped by `event_id`.
  </action>
  <verify>
    <automated>cd frontend && npx vitest run src/hooks/useRunChat.test.ts && npx tsc --noEmit</automated>
  </verify>
  <done>New de-collision + re-fetch-after-send vitest cases pass; existing Test 5 (send routing :140-143) and Test 6 (family anchoring :154-168) stay green; page wires `fetchEvents` to `getRunEvents`; tsc clean.</done>
</task>

<task type="auto">
  <name>Task 4: Piece 3 — seed the prior transcript on open (imperative, family-anchoring-safe)</name>
  <files>frontend/src/hooks/useRunChat.ts, frontend/src/app/dashboard/page.tsx</files>
  <action>
Seed the prior chat turns when a DIFFERENT run is opened from history — WITHOUT introducing a runId-effect reset (a naive "reset messages whenever the hook runId changes" would wipe the parent transcript on a live revision-child launch and break family anchoring, Test 6). Instead expose an IMPERATIVE, invoked ONLY from the explicit history-open action:
  1. In `useRunChat.ts`, add `seedTranscript(frames: RunChatFrame[])` to `UseRunChatReturn`: it clears `seenRef` and `lastSeqRef`, resets `messages` to `[]`, then folds each frame through the existing `handleFrame` (which re-populates `seenRef`/`lastSeqRef` and appends `chat_message`/`chat_reply` turns; non-chat frames are ignored by `handleFrame`'s default branch at `:271-274`). Because it is imperative and only fired on a deliberate view-change, a live revision (which never calls it) keeps accumulating — family anchoring preserved.
  2. In `page.tsx` `handleSelectWorkflowRun`, reuse the events ALREADY fetched in Task 2 (do not fetch twice — capture the `getRunEvents` result once, replay pipeline frames through `handleWebSocketMessage`, and pass the SAME array to `seedTranscript`). Call `seedTranscript(events)` inside the same `fullRun.id !== pipelineState.pipelineRunId` guard, so the terminal/live-opened run shows its prior `chat_message`/`chat_reply` history and Task 3's re-fetch-after-send then pulls only newer events (via the seeded `lastSeqRef` cursor). Wire the `sendMessage`/`seedTranscript` handle out of the `useRunChat` destructure (`:925`) and add it to the `handleSelectWorkflowRun` `useCallback` deps.
This is the highest-risk piece; keep it a SEPARATE atomic commit so it can be reverted independently without losing Pieces 1+2. Do NOT add a per-run message filter to `handleFrame` (the transcript is intentionally unfiltered — Test 6); the reset+seed is scoped by the imperative, not by a filter.
  </action>
  <verify>
    <automated>cd frontend && npx vitest run src/hooks/useRunChat.test.ts src/components/chat/RunChatLane.test.tsx && npx tsc --noEmit</automated>
  </verify>
  <done>`seedTranscript` resets + folds the seeded chat rows; `handleSelectWorkflowRun` calls it with the once-fetched events under the same-id guard; family-anchoring Test 6 and RunChatLane vitest stay green; tsc clean. Behavioral proof lands in Task 5 coverage (b).</done>
</task>

<task type="auto">
  <name>Task 5: Lift shared history-open e2e helpers + add coverage; run full verify against the recorded baseline</name>
  <files>frontend/e2e/fixtures/dashboard.ts, frontend/e2e/tests/ts-live-state.spec.ts</files>
  <action>
Lift the history-open helpers into the SHARED page object so specs stop duplicating them: add `openHistory()` (port the profile-dropdown → "Run History" menuitem flow from `ts-t.history.spec.ts:24-34`) and a `stubRunEvents(runId, events)` helper to `frontend/e2e/fixtures/dashboard.ts` (`DashboardPage`). `stubRunEvents` registers `page.route("**/api/runs/*/events", …)` returning `{ workflow_id, after: 0, events }` (the durable, NON-stream endpoint — distinct from the mockSse `/events/stream`; the mockApi catch-all otherwise returns `{}`), mirroring the per-test `stubRunSummary` LIFO pattern at `ts-t.history.spec.ts:44-65`. Do NOT edit `mockApi.ts` — use per-route stubs.

Create `frontend/e2e/tests/ts-live-state.spec.ts` with three cases (use the mocked project):
  (a) LIVE-open trace: seed a non-terminal run in history; `stubRunEvents` returns a `pipeline_start` (with `agents`) + `agent_start`/`agent_complete` frames carrying `seq`/`event_id`; open it from history; open the Steps tab; assert the pipeline trace renders (agent rows present) rather than the empty "Start a pipeline…" placeholder — guards Half A + DEF-44-12-3.
  (b) TERMINAL-open deliverable + prior chat + Concierge reply: seed a completed run with a deliverable; `stubRunEvents` returns prior `chat_message` + `chat_reply` rows; open it — assert the deliverable in Preview AND the prior chat turns in the transcript; then send a Concierge turn — assert a POST to `/api/runs/{id}/messages` is recorded (closes the missing DEF-44-12-1 e2e), and that the `chat_reply` (returned by the re-fetch, with `event_id` = `chat-reply:{message_id}` and `message_id` == the sent turn's id) renders as its OWN assistant turn while the question bubble is preserved (closes DEF-44-12-2 + the id-collision). Stub the message POST and the follow-up `getRunEvents` fetch so the reply is delivered durably.
  (c) launch→watch regression: a normal `runWith(...)` launch renders the launched run's live trace unchanged (primary-flow guard) — keep `ts-sse`/`ts-j` semantics; this may assert the launched trace via the existing mockSse flow.

Keep the at-risk tests GREEN (update consciously ONLY if truly necessary, and document why in the SUMMARY): `ts-u.revisions.spec.ts:86` (`parent_run_id` === on-screen run — the `page.tsx:496` launched→`contentSourceRunId` on completion is untouched by this plan), `revisionFamilyLinkage.source.test.ts:27-28,42` (keep the literal `postRevision(getToken() ?? "", contentSourceRunId,` and `contentSourceRunId={contentSourceRunId}` tokens verbatim), `useRunChat.test.ts:140-143`.

THEN run the FULL verify from inside `frontend/` (kill any :3000 dev server first): `npx tsc --noEmit`; the affected mocked specs (`ts-j.streaming`, `ts-sse`, `ts-sse-resilience`, `ts-s.reconnect`, `ts-chat`, `ts-chat-cards`, `ts-t.history`, `ts-u.revisions`) + the new `ts-live-state`; and vitest `useRunChat`, `useWorkflow*`, `RunChatLane`, `revisionFamilyLinkage.source`, `AgentThinkingTab`. Compare pass/skip counts against the Task-1 baseline — every previously-green spec MUST stay green and the three new cases MUST pass. Do NOT run a live Bedrock run (the orchestrator performs the live proof afterward).
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit && npx playwright test --project=mocked e2e/tests/ts-live-state.spec.ts e2e/tests/ts-t.history.spec.ts e2e/tests/ts-sse.spec.ts e2e/tests/ts-j.streaming.spec.ts e2e/tests/ts-chat.spec.ts e2e/tests/ts-chat-cards.spec.ts e2e/tests/ts-s.reconnect.spec.ts e2e/tests/ts-sse-resilience.spec.ts e2e/tests/ts-u.revisions.spec.ts && npx vitest run src/hooks/useRunChat.test.ts src/hooks/useWorkflow.clarifyRetention.test.ts src/hooks/useWorkflow.reconnect.test.ts src/components/chat/RunChatLane.test.tsx src/app/dashboard/revisionFamilyLinkage.source.test.ts src/components/results/AgentThinkingTab.test.tsx</automated>
  </verify>
  <done>`openHistory`/`stubRunEvents` live in the shared fixture; `ts-live-state.spec.ts` (a)(b)(c) pass; all listed mocked specs + vitest suites match-or-exceed the Task-1 baseline; at-risk tokens/tests unchanged; tsc clean.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser → FE (viewed-run selection) | User picks which owned run to view; no new untrusted input beyond a run id already used by the reopen path |
| FE → backend GET /api/runs/{id}/events | Existing owner-scoped read (JWT); `after` int-coerced server-side; cross-owner/missing → 404. NO backend change |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-dhr-01 | Information Disclosure | `getRunEvents` reading another owner's run events | accept | Endpoint is already owner-gated by JWT + `user_id` filter (`runs.py:872-894`), returns 404 cross-owner; FE adds no bypass — it reuses the same JWT the reopen path uses |
| T-dhr-02 | Tampering | Replaying durable frames double-counts against the live SSE tail | mitigate | Frames replay through the page router so each `event_id` lands in `seenEventIdsRef`/per-hook `seenRef`; the live tail is then deduped (`shouldApplyEvent` / `handleFrame` dedup) — idempotent by design |
| T-dhr-03 | Tampering | Concierge reply overwrites the user's question bubble (id collision) | mitigate | Key the assistant bubble on the distinct `data.event_id` (`chat-reply:{id}`) not `data.message_id`; the reply appends as its own turn |
| T-dhr-04 | Denial of Service | Seeding a live launched run replays-from-0 over live progress and wipes gate/questionnaire state | mitigate | Hard guard `fullRun.id !== pipelineState.pipelineRunId` skips the entire seed for the live launched run |
| T-dhr-05 | Tampering | Transcript reset breaks family anchoring on a live revision child | mitigate | Reset is an IMPERATIVE (`seedTranscript`) fired only on the explicit history-open action — a live revision never calls it, so accumulation/family anchoring is preserved (Test 6 green) |

No package installs — no legitimacy gate required (frontend-only, no new dependencies).
</threat_model>

<verification>
- `cd frontend && npx tsc --noEmit` → clean.
- Affected mocked Playwright specs run from INSIDE `frontend/` (kill any :3000 dev server first): `ts-j.streaming`, `ts-sse`, `ts-sse-resilience`, `ts-s.reconnect`, `ts-chat`, `ts-chat-cards`, `ts-t.history`, `ts-u.revisions` — all match-or-exceed the Task-1 baseline; the new `ts-live-state` (a)(b)(c) pass.
- vitest `useRunChat`, `useWorkflow*`, `RunChatLane`, `revisionFamilyLinkage.source`, `AgentThinkingTab` → green.
- At-risk tokens intact: `postRevision(getToken() ?? "", contentSourceRunId,`, `contentSourceRunId={contentSourceRunId}`, `page.tsx:496` launched→`contentSourceRunId`, useRunChat send routing.
- NO backend/engine/queue change; NO queue-put for the Concierge reply; global fan-out multi-run scoping left as-is (out of scope). Branch `feat/ui-2`; sequential; NO commit trailer; NEVER push. Executor does NOT run a live Bedrock run.
</verification>

<success_criteria>
- Opening a still-running run from history renders its Steps trace (not the empty placeholder).
- Opening a terminal run renders its deliverable in Preview AND its prior chat turns in the transcript.
- A Concierge turn on an opened run POSTs to `/api/runs/{id}/messages` and the reply renders as its OWN assistant turn (question preserved).
- launch→watch still renders the launched run's trace unchanged.
- `getRunEvents` helper exists; three pieces wired; shared `openHistory`/`stubRunEvents` helpers + `ts-live-state` coverage added; real green baseline established and matched-or-exceeded; tsc clean.
</success_criteria>

<output>
Create `.planning/quick/260716-dhr-bind-run-screen-live-state-steps-trace-c/260716-dhr-SUMMARY.md` when done (record: the baseline pass/skip counts, whether Piece 3 shipped or was deferred, any at-risk-test note, and the commit shas).
</output>
