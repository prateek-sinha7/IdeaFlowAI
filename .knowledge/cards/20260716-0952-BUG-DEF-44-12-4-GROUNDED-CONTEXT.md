---
id: BUG-DEF-44-12-4-GROUNDED-CONTEXT
type: bug
kind: event
title: DEF-44-12-4 — Bind the run-screen live state to the VIEWED run
status: open
applies_to:
  phases: []
  modules:
  - RunConnectionProvider
  - AgentThinkingTab
  - Base
  - Card
  - DashboardLayout
  - ResultCard
  - RunChatLane
  - RunEvent
  - WorkflowRun
  - agents
  - api
  - app
  - chat
  - core
  - getToken
  - revisionFamilyLinkage.source.test
  - run_stream
  - useRunChat
  - useRunChat.test
  - useRunStream
  - useWorkflow
  globs:
  - page.tsx
  - useWorkflow.ts
  - RunConnectionProvider.tsx
  - useRunStream.ts
  - AgentThinkingTab.tsx
  - DashboardLayout.tsx
  - useRunChat.ts
  - useRunChat.test.ts
  - run_commands.py
  - agents/authz.py
  - engine.py
  - run_stream.py
  - frontend/src/lib/api.ts
  - backend/app/api/runs.py
  - frontend/src/hooks/useRunChat.ts
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/hooks/useWorkflow.ts
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/lib/wsReplayState.ts
  - frontend/e2e/tests/ts-u.revisions.spec.ts
  - frontend/src/app/dashboard/revisionFamilyLinkage.source.test.ts
  - frontend/src/hooks/useRunChat.test.ts
  - frontend/e2e/fixtures/dashboard.ts
  - ts-t.history.spec.ts
  requirements: []
locked_constraints: []
verification:
  type: manual
  status: required
  test_files: []
compact_summary: 'Opened-from-history runs show an empty Steps trace and non-rendering Concierge reply because the reducer only seeds agents[] from pipeline_start, never re-seeded on view switch.'
last_updated: '2026-08-14'
author: 'Bilal Arshad <bilala@hexaware.com>'
author_source: applies-to-glob
---

# DEF-44-12-4 — Bind the run-screen live state to the VIEWED run (grounded context)

> Product of 4 read-only investigation agents (2026-07-16) + orchestrator spot-checks against source on `feat/ui-2`. Every file:line below was verified. This is the executable grounding for a `gsd:quick --validate` task. **Subsumes DEF-44-12-2** (Concierge reply not rendering on an opened run).

## Symptoms (both reproduced live this session, real browser + Bedrock)
1. **Empty Steps trace on a history-opened run** — open a still-running run from history/recents → the Steps tab shows the empty "Pipeline trace / Start a pipeline…" placeholder, even though the SSE stream is now attached (DEF-44-12-3 fix, `0563afad`, made `refreshLiveRuns` attach it — 4 `/events/stream` requests fire for the run).
2. **Concierge reply does not render on an opened run** — ask the Concierge on an opened run; the send correctly POSTs to `/api/runs/{id}/messages` (DEF-44-12-1 fix, `f4df5be1`) and the backend persists a grounded `chat_reply`, but only the optimistic question shows.

Both are **FE state-binding defects the WS→SSE cutover exposed**, NOT transport defects. The SSE-only transport is proven clean (0 `/ws/chat`; SSE attaches + delivers).

---

## Root cause (VERIFIED) — two independent halves, one shared cause

The run screen was built assuming **the run you launched == the run you're viewing**. True only for the in-session launch→watch flow. Opening a *different* run from history sets `contentSourceRunId` (`page.tsx:1181` in `handleSelectWorkflowRun`) — which correctly drives Preview/Files/durable content — but **never seeds or re-points the two live consumers** (the pipeline reducer and the chat transcript).

### Half A — Steps trace (the empty placeholder)
- `pipelineState` comes from `useWorkflow()` (`page.tsx:887`); its `agents[]` is built **only** by the `pipeline_start` handler (`useWorkflow.ts:226-251`). Every other event handler keys by `agent_id` and **early-returns if the agent isn't already present** (`agent_start` `useWorkflow.ts:271-272`, `agent_chunk` `:342-343`, `agent_complete` `:368-369`). So with an empty `agents[]`, all later per-agent events are dropped.
- The launch path seeds it: `startPipeline(...)` resets the reducer (`useWorkflow.ts:59-70`) then the live `pipeline_start` fills `agents[]`; `runConnection.attachRun(launchedRunId)` (`page.tsx:1375`) attaches the stream. The reducer starts from cursor 0 and sees `pipeline_start`.
- `handleSelectWorkflowRun` (`page.tsx:1159-1253`) sets `contentSourceRunId` but **touches `pipelineState` nowhere** — no `startPipeline`, no reset, no seed (verified across the whole handler).
- The attached live tail **cannot** rescue it: the SSE re-attach resumes from a **persisted per-run sessionStorage cursor** (`readCursor`→`afterSeq`, `RunConnectionProvider.tsx:185`; `Last-Event-ID`, `useRunStream.ts:299-301`). `refreshLiveRuns` boot-attaches every non-terminal run (`RunConnectionProvider.tsx:222-244`), advancing the run's cursor **past `pipeline_start`** before the user ever opens it → later replays start after `pipeline_start` → reducer drops them (`agentIdx === -1`).
- Render gate: `AgentThinkingTab.tsx:103-107` `hasAnyData` reads `pipelineState.agents` + `runInput`; with empty agents + `runInput={submittedBrief}` (the **launched** brief, `DashboardLayout.tsx:1798`) → EmptyState.

### Half B — Concierge reply (durable-only delivery gap) — **spot-checked, hypothesis of "FE filter" REFUTED**
- The transcript applies **no run-id filter**: `useRunChat.handleFrame` folds every `chat_reply` it receives (`useRunChat.ts:248-276`); its `runId` is used only for the send up-channel. Proven by `useRunChat.test.ts:154-168` (a child-run reply is intentionally folded into a parent-run hook).
- The reply is **persisted durable-only, never queued**: `run_commands.py:988-997` does `await store.append_event_next_seq(run_id, event_id="chat-reply:{message_id}", type="chat_reply", payload_json=…)`; `append_event_next_seq` (`agents/authz.py:332-374`) inserts ONE `run_events` row and commits — **no `_PIPELINE_QUEUES` / `.put()`**. Contrast: every live emitter enqueues (`run_commands.py:1357/1651/1685`, engine milestone cards `engine.py:991-1010`). The Concierge reply is the only `chat_reply` producer that skips the queue.
- The SSE stream (`run_stream.py:129-199`) = **durable replay once** (`store.read_events(run_id, after_seq)`, `:144-149`) **then live-tail** the in-memory queue (`:186-199`, only if `run_id ∈ _PIPELINE_QUEUES`, `:259`). The reply is appended **after** the initial replay ran, and never hits the queue → the live tail never carries it. Terminal runs have no queue at all (replay+close).
- **Terminal-opened run** additionally attaches **no stream** — `handleSelectWorkflowRun` never calls `attachRun`, and `refreshLiveRuns` only attaches `NON_TERMINAL_STATUSES` (`RunConnectionProvider.tsx:60-68`). So there is no delivery channel at all.

### Landmine the fix MUST handle (spot-checked, CONFIRMED)
The reply payload sets `message_id: body.message_id` — **the same id as the user turn** (`run_commands.py:994`). `upsertNarratorMessage` keys the assistant bubble `id` on `data.message_id` (`useRunChat.ts:211-214`) and merges in place via `findIndex(m => m.id === id)` (`:228-234`). A delivered reply would therefore **match and overwrite the user's question bubble** (role flips to assistant, question text lost). Masked today only because the reply never arrives.

---

## The fix (frontend-only; no backend/queue/engine change) — 3 coordinated pieces

### Shared primitive — a durable-events fetch helper
Add `getRunEvents(token, runId, afterSeq = 0)` to `frontend/src/lib/api.ts`, hitting the existing durable endpoint `GET /api/runs/{id}/events?after=N` (`backend/app/api/runs.py:858-909`, owner-scoped, returns `{ events: [{ seq, event_id, type, payload_json }] }` — the SAME rows the SSE replays). Map each row to a frame `{ type, data: payload_json }`. A fresh fetch at `after=0` returns the full history; idempotency is guaranteed downstream by `event_id` dedup.

### Piece 1 — Seed the Steps trace on open (Half A)
In `handleSelectWorkflowRun` (`page.tsx:1159-1253`), after `setContentSourceRunId(fullRun.id)`, when `fullRun.id !== pipelineState.pipelineRunId`:
- Reset replay state for the view change (reuse the existing `resetReplayState`, currently fired only on `pipeline_start` at `page.tsx:462-470`) so the prior run's seen-set / cursor / wave groups don't poison the new run.
- Fetch `getRunEvents(token, fullRun.id)` and replay each frame **through the page's `handleWebSocketMessage`** (NOT the bare reducer) so each `event_id` lands in `seenEventIdsRef` (`page.tsx:322`) → the subsequently-attached live tail is deduped, no double-count. This reconstructs `pipelineState` deterministically (`pipeline_start`→`agents[]`, then `agent_*` fill it) for both live-opened and terminal-opened runs.
- Wire the **viewed** run's input into `runInput` for the history path (use `fullRun.input` rather than `submittedBrief` at `DashboardLayout.tsx:1798`) so `hasAnyData`/header are correct.
- **Guard:** skip the whole seed when `fullRun.id === pipelineState.pipelineRunId` (the live launched run already holds it; re-seeding would replay-from-0 over live progress and wipe gate/questionnaire state via the `pipeline_start` reset side effects at `page.tsx:462-483`).

### Piece 2 — Render the Concierge reply on an opened run (Half B, = DEF-44-12-2)
In `useRunChat` (`frontend/src/hooks/useRunChat.ts`):
- **Re-fetch-after-send** (covers terminal AND live — the reply is durably persisted either way, so no backend queue-put is needed): inject a `fetchEvents(runId, afterSeq)` alongside `subscribe`/`sendCommand` (wired in `page.tsx` to `getRunEvents`). Make `sendMessage` await the up-channel (today `void sendCommand(...)` at `useRunChat.ts:319-321`; the page wrapper `page.tsx:938-940` discards the promise — return it), then fetch new events since the last seen `seq` and fold each through the existing `handleFrame`. The per-hook `seenRef`/`event_id` dedup (`useRunChat.ts:251-253`) makes it idempotent.
- **De-collide the assistant bubble id (required companion):** in `upsertNarratorMessage`, key the assistant message `id` on the frame's distinct `data.event_id` (`chat-reply:{message_id}`) instead of `data.message_id`, so the reply appends as its own turn instead of overwriting the question. (This is also the correct idempotency key — the same one `handleFrame` dedups on.)

### Piece 3 — Seed the prior transcript on open (coherent with Piece 1; keeps the mechanism consistent)
On open, also fold the durable `chat_message`/`chat_reply` rows (already fetched in Piece 1) through `useRunChat.handleFrame`, tracking the max `seq` seen so Piece 2's re-fetch pulls only newer events. This requires **resetting `useRunChat.messages` on view change** (today it is never reset — a pre-existing cross-run accumulation bug). Do this carefully (see at-risk tests). If the planner judges the reset too risky to couple here, Piece 3 may be deferred as an explicit follow-up, but Pieces 1+2 are the required core.

---

## Scope fences
**IN:** the 3 pieces above + the `getRunEvents` helper + tests. Frontend-only. Files most likely touched: `frontend/src/app/dashboard/page.tsx`, `frontend/src/hooks/useRunChat.ts`, `frontend/src/lib/api.ts`, possibly `frontend/src/hooks/useWorkflow.ts` (if a seed action is cleaner) and `frontend/src/components/layout/DashboardLayout.tsx` (`runInput` for history) + `frontend/src/lib/wsReplayState.ts` (reuse `resetReplayState`).

**OUT (do NOT do — note as follow-ups):**
- Per-run scoping of the global unfiltered fan-out (`RunConnectionProvider.tsx:275-283`) — with multiple live runs the reducer can be updated by another run's events (trace events carry `agent_id` but no run id — verified `engine.py:2931-3694`). Pre-existing; do not fix here.
- Any backend change. The durable-only Concierge persist is FINE — we read it via `GET /events`. Do NOT add a queue-put for the reply (Agent B: a queue-put on a terminal run would create an orphan queue that falsely marks the run "live" to `run_stream.py:259`).
- Stamping a distinct `message_id` server-side (the FE `event_id` keying is preferred and self-contained).

---

## Constraints & at-risk tests
- Branch **`feat/ui-2`** (NEVER main/staging). Worktrees OFF → sequential. **NO commit trailer** (no Co-Authored-By/Claude-Session). **Never push.**
- **Keep the primary launch→watch flow green** — it is unaffected by design (launched==viewed); prove it stays so.
- **At-risk tests that encode launched==viewed — keep GREEN (update consciously only if truly necessary):**
  - `frontend/e2e/tests/ts-u.revisions.spec.ts:86` — `expect(frame.parent_run_id).toBe(mockSse.currentRunId)` (the on-screen run). Preserve `page.tsx:496` (launched run → `contentSourceRunId` on completion).
  - `frontend/src/app/dashboard/revisionFamilyLinkage.source.test.ts:27-28,42` — literal source-string asserts `postRevision(getToken() ?? "", contentSourceRunId,` and `contentSourceRunId={contentSourceRunId}`. Keep these tokens verbatim.
  - `frontend/src/hooks/useRunChat.test.ts:140-143` — DEF-44-12-1 send routing to the hook's `runId`. The re-fetch fix must keep send routing intact.
- **SC-001 (no workflow-name literals in guarded/generic paths):** `page.tsx` is EXEMPT (it legitimately holds `od_prototype`/`od_ppt`/`user_stories`/`ppt` literals for content routing) and is under no SC-001 vitest guard. If you touch a guarded component (e.g. `RunChatLane`, `AgentThinkingTab`, `ResultCard`) keep it workflow-name-literal-free (per-component vitest source-scans enforce this). `frontend/e2e` is excluded from the SSE-cutover banned-pattern scan.
- **Baseline is NOT 132/0** (that figure is stale — Phase 42). The current mocked project is ~161-169 active specs + ~32-35 skip/fixme. **Establish the real green baseline by RUNNING the suite before and after** — do not trust a number.

## Verification (executor scope)
- `cd frontend && npx tsc --noEmit` → clean.
- Run the affected mocked Playwright specs from **inside `frontend/`** (cwd-sensitive; kill any :3000 dev server first so Playwright starts its own): `ts-j.streaming`, `ts-sse`, `ts-sse-resilience`, `ts-s.reconnect`, `ts-chat`, `ts-chat-cards`, `ts-t.history`, `ts-u.revisions` → all previously-green stay green.
- Run vitest for `useRunChat`, `useWorkflow*`, `RunChatLane`, `revisionFamilyLinkage.source`, `AgentThinkingTab` → green.
- **Add coverage** (page-object needs history methods — none exist in `frontend/e2e/fixtures/dashboard.ts` today; lift `openHistory`/`stubRunSummary` from `ts-t.history.spec.ts:24-65`):
  - (a) open a LIVE (non-terminal) run from history → its streaming trace renders (guards Half A + DEF-44-12-3).
  - (b) open a TERMINAL run → deliverable in Preview + prior chat in transcript; then send a Concierge turn → assert POST `/api/runs/{id}/messages` (closes the missing DEF-44-12-1 e2e) → the `chat_reply` **renders as its own turn** (closes DEF-44-12-2 + the id-collision).
  - (c) launch→watch still renders the launched run's trace (primary-flow regression guard) — keep `ts-sse`/`ts-j` green.
- **Do NOT run a live Bedrock run in the executor.** The definitive LIVE proof (open a live run from history → trace renders; Concierge on an opened run → reply renders as a distinct turn; 0 `/ws/chat`) is performed by the ORCHESTRATOR after execution.

## Continue-the-investigation handles (if deeper detail is needed)
Trace binding agent `a64acae3f73de9801`; transcript agent `a507e7246d5113365`; SSE/backend agent `a0e79baf7bd8ec216`; test-surface agent `a0ac91c33369171a6`.
