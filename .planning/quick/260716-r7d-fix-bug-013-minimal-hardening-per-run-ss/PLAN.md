---
phase: quick-260716-r7d
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/providers/RunConnectionProvider.tsx
  - frontend/src/lib/api.ts
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/providers/RunConnectionProvider.test.tsx
  - frontend/src/lib/api.requestTimeout.test.ts
  - frontend/src/app/dashboard/attachRunOnOpen.source.test.ts
autonomous: true
requirements:
  - BUG-013
must_haves:
  truths:
    - "With >=6 non-terminal runs, opening a clarify-parked run no longer hangs (only builds + the focused run hold SSE streams)."
    - "A BACKGROUND parked run (waiting_for_user/clarifying) that is NOT the focused run holds no SSE stream."
    - "A building run (running/planning/analyzing/generating/revising) always holds a stream regardless of focus."
    - "The viewed/launched run is the single focused run and streams even while parked; opening a second run replaces the focus (no accumulation)."
    - "A hung/starved REST call rejects with a typed error after ~30s instead of hanging into a silent idle screen."
  artifacts:
    - path: "frontend/src/providers/RunConnectionProvider.tsx"
      provides: "AUTO_STREAM_STATUSES filter + single sticky focusedRunId unioned into liveRunIds"
      contains: "AUTO_STREAM_STATUSES"
    - path: "frontend/src/lib/api.ts"
      provides: "AbortController timeout on request()"
      contains: "AbortController"
    - path: "frontend/src/providers/RunConnectionProvider.test.tsx"
      provides: "RED->GREEN: parked excluded, builds+focus attached, second attachRun replaces focus"
    - path: "frontend/src/lib/api.requestTimeout.test.ts"
      provides: "RED->GREEN: never-resolving fetch rejects after the timeout"
  key_links:
    - from: "RunConnectionProvider.refreshLiveRuns"
      to: "AUTO_STREAM_STATUSES union focusedRunIdRef"
      via: "recomputeLiveRunIds with the :236-239 identity guard on the UNION"
      pattern: "AUTO_STREAM_STATUSES"
    - from: "page.tsx handleSelectWorkflowRun"
      to: "runConnection.attachRun"
      via: "attachRun(fullRun.id) right after setContentSourceRunId(fullRun.id)"
      pattern: "attachRun\\(fullRun\\.id\\)"
    - from: "api.ts request()"
      to: "fetch(url, { signal })"
      via: "AbortController + setTimeout(abort, 30000) + clearTimeout on settle"
      pattern: "AbortController"
---

<objective>
Fix BUG-013 (per-run SSE streams exhaust the browser's ~6-connections-per-origin pool ->
the reopen `GET /api/runs/{id}` and launch `POST /api/runs` hang forever -> clarify/launch
renders a silent idle screen). Implement EXACTLY the two-part minimal+hardening fix from
`.planning/BUG-013-GROUNDED-CONTEXT.md`:

- Part A: stop auto-streaming BACKGROUND parked runs; keep active builds + a single sticky
  focused (viewed/launched) run streamed.
- Part B: wrap the REST client `request()` fetch in a ~30s AbortController timeout so a
  starved call fails fast with a typed error instead of hanging.

Root cause is RUNTIME-PROVEN and the design is user-chosen. Do NOT re-investigate and do
NOT propose the durable-transport rework.

Purpose: bound concurrent SSE streams under the HTTP/1.1 connection cap so reopen/launch
always have a free socket; fail-fast if one is ever starved.
Output: two behavior fixes + one wiring one-liner + three tests (RED->GREEN).
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@.planning/BUG-013-GROUNDED-CONTEXT.md

# Source under change
@frontend/src/providers/RunConnectionProvider.tsx
@frontend/src/lib/api.ts

# Test idioms to clone
@frontend/src/lib/api.getRunArtifacts.test.ts
@frontend/src/app/dashboard/contentSourceRunType.source.test.ts
</context>

<constraints>
- Branch feat/ui-2. Verify with `git rev-parse --abbrev-ref HEAD`; DO NOT switch. NO commit trailer. NEVER push.
- Frontend only. Do NOT touch the backend/SSE wire, the reducer, `useRunStream`, or the durable-replay reopen seed at page.tsx:1264-1301 (only ADD the one `attachRun` call before it, at :1250).
- FE is cwd-sensitive: run all vitest/tsc/Playwright from `frontend/`. Kill anything on :3000 before mocked Playwright.
- SC-001: key on run STATUS strings and run IDs only. No workflow-name (`WorkflowType`) literal in the fix or its tests.
- Timeout is ~30s (generous — must NOT abort legitimately-slow brief-ingest / large-deliverable calls). Not seconds.
- The "132/0" mocked-e2e baseline is stale; the 8 pre-Phase-42 vitest reds in untouched files are NOT regressions. Executor does NOT run live Bedrock (orchestrator does the live proof).
</constraints>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — provider filter/focus test, request() timeout test, page-wiring source-lock</name>
  <files>frontend/src/providers/RunConnectionProvider.test.tsx, frontend/src/lib/api.requestTimeout.test.ts, frontend/src/app/dashboard/attachRunOnOpen.source.test.ts</files>
  <behavior>
    Provider test (RunConnectionProvider.test.tsx) via `renderHook(() => useRunConnection(), { wrapper: RunConnectionProvider })`:
    - Mock `@/hooks/useRunStream` -> `{ phase: "live", reconnect: () => {} }` so RunStreamConnection mounts without a real EventSource.
    - Mock `@/lib/api` (partial via importOriginal) so `getToken` -> "tok" and `getWorkflows` -> a fixed list mixing PARKED (`waiting_for_user`, `clarifying`) and BUILDING (`running`, `generating`) runs. Cast parked statuses `as unknown as WorkflowRun` (the FE `WorkflowStatus` union is narrow and omits them; the runtime backend emits them — mirrors the existing `NON_TERMINAL_STATUSES` `Set<string>.has` reliance).
    - Test 1: after `waitFor`, `result.current.liveRunIds` contains ONLY the building ids; parked ids EXCLUDED. FAIL-BEFORE: current code attaches every non-terminal run -> parked present -> RED.
    - Test 2: `act(() => attachRun("parked-A"))` makes parked-A the single focused id in liveRunIds; then `act(() => attachRun("parked-B"))` REPLACES it (parked-B present, parked-A absent). FAIL-BEFORE: current attachRun APPENDS -> both remain -> RED.
    - Test 3: a BUILDING id survives `attachRun("other")` (builds stay via AUTO_STREAM_STATUSES independent of focus).

    Timeout test (api.requestTimeout.test.ts) — clone the fetch-mock idiom from api.getRunArtifacts.test.ts:
    - `vi.useFakeTimers()`; stub global fetch -> a promise that NEVER resolves.
    - Call `getWorkflow("tok","run-x")` (hits `request()`); `await vi.advanceTimersByTimeAsync(30000)`; `await expect(promise).rejects.toThrow(/timeout|aborted/i)`.
    - FAIL-BEFORE: no timeout in `request()` -> promise stays pending -> assertion fails on a modest per-test timeout (set `{ timeout: 3000 }` so RED is fast, not a 30s hang). Restore timers + unstub in afterEach.

    Page-wiring source-lock (attachRunOnOpen.source.test.ts) — clone contentSourceRunType.source.test.ts: `readFileSync` page.tsx and assert it calls `attachRun(fullRun.id)` adjacent to `setContentSourceRunId(fullRun.id)`. FAIL-BEFORE: the call does not exist -> RED.
  </behavior>
  <action>Create the three test files per the behavior block. Do NOT modify production source in this task — the three tests MUST be RED against current code (specified assertions/timeouts, not import/compile errors). Keep SC-001: fixtures key on status/id, never a workflow-name literal. Use `renderHook`/`act`/`waitFor` from `@testing-library/react` (see src/hooks/useRunChat.test.ts) and `vi.stubGlobal("fetch", ...)` (see api.getRunArtifacts.test.ts).</action>
  <verify>
    <automated>cd frontend && npx vitest --run src/providers/RunConnectionProvider.test.tsx src/lib/api.requestTimeout.test.ts src/app/dashboard/attachRunOnOpen.source.test.ts 2>&1 | tail -30</automated>
  </verify>
  <done>All three test files exist and FAIL against current code (parked attached; append not replace; no request timeout; no attachRun on reopen) — the failures are the specified assertions/timeouts, not compile errors.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — Part A (provider focus+filter) + Part B (request timeout) + page wiring</name>
  <files>frontend/src/providers/RunConnectionProvider.tsx, frontend/src/lib/api.ts, frontend/src/app/dashboard/page.tsx</files>
  <behavior>The three Task-1 tests now pass; at-risk specs unaffected.</behavior>
  <action>
Part A — RunConnectionProvider.tsx:
  1. REPLACE the `NON_TERMINAL_STATUSES` declaration (:60-68) with `AUTO_STREAM_STATUSES = new Set(["running","planning","analyzing","generating","revising"])` — drop `waiting_for_user` and `clarifying`. Do not leave the old const (no-unused/no-shadow: single source of truth). Update the doc comment: parked runs emit no events while parked, so excluding them loses zero live updates and bounds concurrent streams under the ~6-per-origin cap; the viewed/launched run stays streamed via the sticky focus below.
  2. Add `const focusedRunIdRef = useRef<string | null>(null)` and `const autoIdsRef = useRef<string[]>([])`.
  3. Add a `recomputeLiveRunIds` useCallback that reads BOTH refs and computes `union = focus ? [...autoIds.filter(id => id !== focus), focus] : autoIds`, then calls setLiveRunIds with the EXISTING :236-239 identity guard applied to the UNION (length + positional equality; return prev when unchanged so no remount). CRITICAL: apply the guard to the union, not to autoIds alone — else the focused run is dropped on every refresh.
  4. `refreshLiveRuns`: filter by `AUTO_STREAM_STATUSES`, set `autoIdsRef.current = ids`, then call `recomputeLiveRunIds()` (remove the inline setLiveRunIds-of-ids guard — it now lives in recompute). Keep the token-empty early return that clears liveRunIds.
  5. `attachRun`: set `focusedRunIdRef.current = runId` (a NEW focus REPLACES the prior), then `recomputeLiveRunIds()`. Update its docstring (now sets the single sticky focus; a still-building prior run is retained via AUTO_STREAM_STATUSES regardless of focus). Add `recomputeLiveRunIds` to its useCallback deps.
  Do NOT change RunStreamConnection, useRunStream, sendCommand, cursor persistence, or the wake/online effect.

Part B — api.ts `request()` (:80-95): wrap the fetch (:85) in an AbortController — `const controller = new AbortController()`, `const timer = setTimeout(() => controller.abort(), 30_000)`, pass `signal: controller.signal` on the fetch options, `clearTimeout(timer)` in a `finally`. No current `request()` caller passes its own signal (verified) so a direct assignment is safe. On abort the fetch throws a DOMException AbortError — translate it to a typed, catchable error (reuse `ApiError` with status 0, e.g. `new ApiError(0, "Request timed out after 30000ms")`, or a named TimeoutError) so it matches the Task-1 `/timeout|aborted/i` assertion and the reopen catch (page.tsx:1375) surfaces it instead of hanging. Keep the `!response.ok -> ApiError` path intact.

Page wiring — page.tsx `handleSelectWorkflowRun`: add `runConnection.attachRun(fullRun.id);` on the line immediately AFTER `setContentSourceRunId(fullRun.id);` (:1250) so the VIEWED run becomes the focused stream on reopen. Add `runConnection` to the useCallback dep array (:1381). Do NOT alter the durable-replay seed block (:1264-1301) otherwise. The launch path already attachRuns the created run (:1508) — leave it; it now sets the focus.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | tail -15 && npx vitest --run src/providers/RunConnectionProvider.test.tsx src/lib/api.requestTimeout.test.ts src/app/dashboard/attachRunOnOpen.source.test.ts 2>&1 | tail -20</automated>
  </verify>
  <done>`tsc --noEmit` clean; all three Task-1 tests GREEN. `AUTO_STREAM_STATUSES` is the only status set (no leftover NON_TERMINAL_STATUSES); parked excluded, builds+focus attached, second attachRun replaces focus; `request()` aborts+rejects at 30s; page.tsx calls attachRun(fullRun.id) on reopen.</done>
</task>

<task type="auto">
  <name>Task 3: Regression gate — at-risk vitest + mocked SSE/history/revision Playwright</name>
  <files>(no source changes — verification only)</files>
  <action>Run the at-risk suites green. If a genuine regression appears, fix it in the three files already in scope; do NOT expand scope or touch the fenced-off files. Kill any process on :3000 before Playwright.</action>
  <verify>
    <automated>cd frontend && npx vitest --run src/hooks/useRunChat.test.ts src/hooks/useWorkflow.imagePayload.test.ts src/app/dashboard/contentSourceRunType.source.test.ts src/app/dashboard/contentSourceRunScope.source.test.ts src/app/dashboard/revisionFamilyLinkage.source.test.ts 2>&1 | tail -20</automated>
    <automated>cd frontend && (lsof -ti:3000 | xargs kill -9 2>/dev/null || true) && npx playwright test --project=mocked ts-sse ts-sse-resilience ts-s.reconnect ts-j.streaming ts-t.history ts-u.revisions ts-y.run-scope-clarify 2>&1 | tail -25</automated>
  </verify>
  <done>At-risk vitest specs stay green. Mocked Playwright ts-sse / ts-sse-resilience / ts-s.reconnect / ts-j.streaming / ts-t.history / ts-u.revisions / ts-y.run-scope-clarify stay green (launch->watch still streams via focus; reopen no longer hangs). No NEW vitest reds beyond the 8 known pre-Phase-42 reds in untouched files.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser -> origin (localhost:8000 dev) | HTTP/1.1 ~6-connections-per-origin cap; SSE streams + REST share the pool |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-r7d-01 | Denial of Service | RunConnectionProvider per-run SSE fan-out | mitigate | Bound concurrent streams to (active builds + 1 focused run) via AUTO_STREAM_STATUSES + single sticky focus; parked BACKGROUND runs hold no stream |
| T-r7d-02 | Denial of Service | api.ts request() (starved/hung REST call) | mitigate | ~30s AbortController timeout -> typed rejection instead of an infinite hang / silent idle screen |
| T-r7d-SC | Tampering | npm installs | accept | No new dependencies; frontend-only edits to existing files |
</threat_model>

<verification>
- `cd frontend && npx tsc --noEmit` clean.
- The three new tests are RED before Task 2, GREEN after.
- At-risk vitest + mocked Playwright specs stay green (Task 3).
- SC-001: no workflow-name literal introduced (the change keys on run status/id only).
- Live proof is the orchestrator's, not the executor's: with >=6 non-terminal runs, reopen a clarify-paused run -> the 6 questions render (no hang); launch a no-template prototype -> clarify renders.
</verification>

<success_criteria>
- Part A: refreshLiveRuns filters by AUTO_STREAM_STATUSES and unions a single sticky focusedRunId; attachRun sets/replaces the focus; the :236-239 identity guard preserved on the UNION; NON_TERMINAL_STATUSES gone.
- Part B: request() aborts after ~30s and rejects with a typed, catchable error; clearTimeout on settle.
- Wiring: handleSelectWorkflowRun calls attachRun(fullRun.id) right after setContentSourceRunId(fullRun.id); launch path unchanged.
- Launch->watch + building-run streaming byte-behavior preserved; only BACKGROUND parked runs stop streaming.
- Branch stays feat/ui-2; no push; no commit trailer.
</success_criteria>

<output>
Create `.planning/quick/260716-r7d-fix-bug-013-minimal-hardening-per-run-ss/SUMMARY.md` when done.
</output>
