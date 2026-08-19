---
id: BUG-013-GROUNDED-CONTEXT
type: bug
kind: event
title: BUG-013 — grounded fix spec
status: open
applies_to:
  phases: []
  modules:
  - RunConnectionProvider
  - RunChatLane
  - RunEvent
  - User
  - WorkflowRun
  - api
  - app
  - useRunChat
  - useWorkflow
  globs:
  - page.tsx
  - frontend/src/providers/RunConnectionProvider.tsx
  - frontend/src/lib/api.ts
  - RunConnectionProvider.tsx
  - api.ts
  requirements: []
locked_constraints: []
verification:
  type: manual
  status: required
  test_files: []
compact_summary: 'One EventSource per non-terminal run saturates the browser''s ~6-connection-per-origin limit, hanging fetches; fix stops auto-streaming parked runs, adds an AbortController timeout to the REST client.'
last_updated: '2026-08-14'
author: 'Bilal Arshad <bilala@hexaware.com>'
author_source: applies-to-glob
---

# BUG-013 — grounded fix spec (per-run SSE streams exhaust the browser connection pool → clarify/launch hangs)

> Frontend-only. Root cause RUNTIME-PROVEN (deep-investigation agent + orchestrator independent repro). User chose the **minimal + hardening** fix. Executable spec for a `gsd-quick`.

## The bug (VERIFIED — connection-pool exhaustion, NOT a state/render bug)
The FE opens **one long-lived EventSource SSE stream per non-terminal run**, all to the single origin `localhost:8000` (dev). With ≥6 non-terminal runs, the browser's **HTTP/1.1 ~6-connections-per-origin limit** is saturated. The next request to that origin — the reopen's `GET /api/runs/{id}` (`page.tsx:1246` → `getWorkflow` → `request()` bare `fetch`, **no timeout**) or a launch's `POST /api/runs` — has no free socket and **hangs forever** → `setContentSourceRunId`/the durable-replay/the questionnaire never run → the lane renders the initial **idle** state with the stale `workflowType="user_stories"` label, and clarify questions never appear.

**Orchestrator proof (independent):** with the dashboard open (12 EventSource streams to `localhost:8000` — 6 runs ×2 StrictMode), an in-page `fetch("http://localhost:8000/api/runs")` → **AbortError @8002 ms (hung)**; the identical `fetch("http://127.0.0.1:8000/api/runs")` → **200 @86 ms**. Same backend, same instant — only the origin (⇒ connection pool) differs. This is why every `curl`/`127.0.0.1` probe always worked while the app hangs.

**Regression:** Phase 44 (`a931c066`/`f6ce1142`) replaced the single multiplexed WebSocket with one EventSource per run; **DEF-44-12-3 (`0563afad`, this session)** added `waiting_for_user`+`clarifying` to the auto-streamed statuses, so idle gate-paused runs now each hold a connection. NOT the BUG-005 state-wipe (that needs a *building* foreign run + is already fixed) — this is transport-layer.

## The fix (chosen: minimal + hardening) — bound concurrent streams + fail-fast on starvation

### Part A — stop auto-streaming BACKGROUND parked runs; keep the viewed/launched run + active builds streamed
`frontend/src/providers/RunConnectionProvider.tsx`:
- `refreshLiveRuns` (`:222-244`) currently attaches a stream for EVERY run whose status is in `NON_TERMINAL_STATUSES` (`:60-68`, includes `clarifying`+`waiting_for_user`) — `runs.filter((r) => NON_TERMINAL_STATUSES.has(r.status))` (`:232`).
- **Design:** split the status set. Introduce `AUTO_STREAM_STATUSES` = the actively-emitting subset **excluding the parked ones**: `running, planning, analyzing, generating, revising` (NOT `waiting_for_user`, NOT `clarifying`). `refreshLiveRuns` filters by `AUTO_STREAM_STATUSES`.
- **Keep the viewed/launched run streamed even when parked** via a single "focused run" that is always unioned into `liveRunIds`:
  - The provider already exposes `attachRun` (`:305`, imperative append) used by the launch flow (W1/R4). Make `attachRun(runId)` set a **single sticky `focusedRunId`** (a ref/state) — a NEW focus REPLACES the prior (so opening run B drops run A's parked stream; no accumulation).
  - `refreshLiveRuns` computes `liveRunIds = union(autoIds, focusedRunId ? [focusedRunId] : [])` (preserve the set-diff/identity guard at `:236-239` so unchanged sets don't remount).
  - The page attaches the VIEWED run on reopen: call `attachRun(fullRun.id)` inside `handleSelectWorkflowRun` (`page.tsx`, right after `setContentSourceRunId(fullRun.id)` `:1250`). The launch path already `attachRun`s the created run (keep it — it becomes the focused run).
- **Net concurrent streams** = (active building runs) + (1 focused viewed run) — well under the 6-per-origin cap for any realistic run count. Background parked runs stream nothing (they emit no events while parked) so excluding them loses ZERO live updates; the viewed parked run's clarify still renders from the durable `getRunEvents` replay (`page.tsx:1287`), and it now also has a live stream (via focus) for multi-round clarify + the resume→build transition.

### Part B — hardening: fail-fast timeout on the REST client
`frontend/src/lib/api.ts` `request()` (`:80-95`): wrap the `fetch` (`:85`) in an `AbortController` with a timeout (default ~30 s; `clearTimeout` on settle) so a starved/hung REST call **rejects with a clear error** instead of hanging into an invisible idle screen. This is the central path for 38 callers incl. `getWorkflow` (`:409`, the starved reopen call) — one edit covers them. Throw a typed/again-catchable error (reuse `ApiError` or an `AbortError`); the reopen catch (`page.tsx:1375`) then surfaces it instead of the silent hang.

## Scope fences (STRICT)
- **Frontend only.** Files: `RunConnectionProvider.tsx`, `api.ts`, `page.tsx` (the `attachRun`-on-open one-liner), + tests. Do NOT change the SSE wire/backend, the reducer, `RunStreamConnection`, or the j1u/lb6/n2d/o6z fixes. Do NOT touch the durable-replay reopen seed (`page.tsx:1264-1301`) beyond adding the `attachRun` call.
- Preserve the launch→watch flow: a launched run is the focused run → streams → its `questionnaire_ready` arrives live → clarify renders. Building runs still auto-stream (live progress unchanged).
- The timeout must be generous enough not to abort legitimately-slow calls (brief ingest / large deliverable fetch) — ~30 s, not a few seconds.

## Constraints
- Branch **feat/ui-2**. NO commit trailer. NEVER push. FE cwd-sensitive (from `frontend/`; kill :3000 before mocked Playwright). SC-001: keys on run status/id, no workflow-name literal. The "132/0" baseline is stale; the 8 pre-Phase-42 vitest reds in untouched files are NOT regressions.
- Keep at-risk green: the SSE/reconnect specs (`ts-sse`, `ts-sse-resilience`, `ts-s.reconnect`, `ts-j`), `ts-t.history`, `ts-u.revisions`, `ts-y.run-scope-clarify`, `RunChatLane`/`useRunChat`/`useWorkflow` vitest, `contentSourceRunType.source`/`contentSourceRunScope.source`/`revisionFamilyLinkage.source`.

## Verification (executor)
- `npx tsc --noEmit` clean.
- **Part A fail-before/pass-after:** a `RunConnectionProvider` unit/source test — given a run list with `waiting_for_user`/`clarifying` runs + `running` runs, `refreshLiveRuns` attaches ONLY the building ones + the focused run (assert parked BACKGROUND runs are excluded; fail-before: all attached). Plus a test that `attachRun(id)` makes `id` the single focused run (a second `attachRun` replaces the first as the parked-focus). A source-lock is acceptable where rendering the provider is impractical.
- **Part B fail-before/pass-after:** a `request()`/api test — a `fetch` that never resolves rejects after the timeout (fake timers / mocked fetch) with the typed error (fail-before: hangs).
- **No-regression:** launch→watch still streams (focused run attaches); the SSE reconnect/resilience specs green; reopening a terminal run unaffected.
- Executor does NOT run live Bedrock — the orchestrator does the live proof: with ≥6 non-terminal runs present, reopen a clarify-paused run → the 6 questions render (no hang); launch a no-template prototype → clarify renders.
