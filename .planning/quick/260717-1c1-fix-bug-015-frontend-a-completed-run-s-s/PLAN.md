---
phase: quick-260717-1c1
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/hooks/useRunStream.ts
  - frontend/src/hooks/useRunStream.test.ts
  - frontend/src/providers/RunConnectionProvider.tsx
  - frontend/src/providers/RunConnectionProvider.test.tsx
  - frontend/src/app/dashboard/page.tsx
  - backend/app/api/run_stream.py
  - backend/tests/unit/test_sse_stream.py
autonomous: true
requirements:
  - BUG-015
  - BUG-016
must_haves:
  truths:
    - "BUG-015: after a NON-live stream closes (`stream_attached` with `data.live !== true` then the connection ends), useRunStream does NOT schedule a reconnect and settles to a quiescent phase (`disconnected`) with no `Reconnecting…` banner — so a completed, still-viewed run no longer re-replays ~14k events in a loop."
    - "BUG-015 (no regression): a GENUINE live drop (`stream_attached{live:true}` then the connection ends) STILL reconnects — the `sawNonLiveAttachRef` is reset to false at the top of every `connect()`, so liveness is judged per-connection."
    - "BUG-015: RunConnectionProvider exposes `detachRun(runId)` that clears `focusedRunIdRef` (only when it matches) and recomputes `liveRunIds`, dropping the id from the streamed set; a non-focused id is a no-op. The context type + the no-provider default stub carry it too (tsc clean)."
    - "BUG-015: dashboard `page.tsx` calls `detachRun(completingRunId)` for the TRACKED (non-foreign) completing run inside the `pipeline_complete` handler, unmounting the finished run's `RunStreamConnection` — reached via a ref (the handler is a `useCallback([])`), never a direct `runConnection` reference (which would break the empty-deps design)."
    - "BUG-016: approving a review gate no longer closes the live SSE stream — the live-drain loop treats `review_gate_approved` as NON-terminal (it resumes the build), so post-approve `generating` frames keep flowing; genuine terminals (`pipeline_complete`/`pipeline_cancelled`/`pipeline_failed`/`budget_aborted`/`error`) still end the drain."
    - "BUG-016 (no regression): `_dangling_review_gate` (the D-14g durable re-arm derivation) still treats `review_gate_approved` as gate-resolved — `_GATE_RESOLUTION_TYPES` and its :121 use are unchanged, so `test_resolved_gate_does_not_rearm` and the fresh-attach/re-arm tests stay green."
  artifacts:
    - path: "frontend/src/hooks/useRunStream.ts"
      provides: "sawNonLiveAttachRef (reset per connect, set from stream_attached liveness); close branch skips scheduleReconnect + setPhase('disconnected') when the last attach was non-live"
      contains: "sawNonLiveAttachRef"
    - path: "frontend/src/hooks/useRunStream.test.ts"
      provides: "RED->GREEN: non-live attach+close → no reconnect / phase disconnected (fail-before: reconnecting); control live attach+close → still reconnecting"
      contains: "stream_attached"
    - path: "frontend/src/providers/RunConnectionProvider.tsx"
      provides: "detachRun(runId) on the context value + type + DEFAULT_VALUE stub; mirrors attachRun, clears the sticky focus"
      contains: "detachRun"
    - path: "frontend/src/providers/RunConnectionProvider.test.tsx"
      provides: "RED->GREEN: detachRun clears focus + drops the id from liveRunIds; non-focused id is a no-op"
      contains: "detachRun"
    - path: "frontend/src/app/dashboard/page.tsx"
      provides: "detachRunRef synced from runConnection.detachRun; called for the tracked completing run in the pipeline_complete handler"
      contains: "detachRun"
    - path: "backend/app/api/run_stream.py"
      provides: "_STREAM_TERMINAL_TYPES = _GATE_RESOLUTION_TYPES - {review_gate_approved}; used at the live-drain terminal check (:198)"
      contains: "_STREAM_TERMINAL_TYPES"
    - path: "backend/tests/unit/test_sse_stream.py"
      provides: "RED->GREEN: live queue review_gate_approved then agent_start → BOTH yielded; control pipeline_complete then agent_start → only pipeline_complete yielded"
      contains: "review_gate_approved"
  key_links:
    - from: "useRunStream connect() close branch (:370-372)"
      to: "scheduleReconnect() vs setPhase('disconnected')"
      via: "&& !sawNonLiveAttachRef.current guard (ref reset at connect top, set in dispatchBlock on stream_attached)"
      pattern: "sawNonLiveAttachRef"
    - from: "dashboard pipeline_complete handler (page.tsx:537-554)"
      to: "RunConnectionProvider.detachRun"
      via: "detachRunRef.current?.(completingRunId) for the non-foreign tracked run (ref idiom, mirrors handlePipelineMsgRef)"
      pattern: "detachRun"
    - from: "run_stream.py live-drain loop (:198)"
      to: "return (close the stream) ONLY on a true terminal"
      via: "event.get('type') in _STREAM_TERMINAL_TYPES (review_gate_approved excluded)"
      pattern: "_STREAM_TERMINAL_TYPES"
---

<objective>
Fix two SSE reconnect bugs exposed by the BUG-014-B parser repair. Implement EXACTLY the
grounded spec in `.planning/BUG-015-016-GROUNDED-CONTEXT.md` — root causes are
agent + orchestrator verified. Do NOT re-investigate.

BUG-015 (FRONTEND) — a completed, still-viewed run reconnects forever. When a launched run
goes terminal it stays the FE's focused/attached run; the backend closes a terminal run's
stream after replay (`stream_attached{live:false}` then close, no `event: done`); `useRunStream`
reconnects on ANY close with no terminal check → re-replay ~13,928 events → close → loop → the
phase-driven "Reconnecting…" banner flaps. Fix (frontend only): (1) `useRunStream.ts` tracks
per-connection attach liveness in `sawNonLiveAttachRef` (reset at each `connect()`), and the
close branch skips `scheduleReconnect()` + settles quiescent when the last attach was non-live —
a genuine live drop still reconnects; (2) `RunConnectionProvider.tsx` adds `detachRun(runId)`
(clears the sticky focus + recomputes); (3) `page.tsx` calls it for the tracked completing run
so the dead `RunStreamConnection` unmounts.

BUG-016 (BACKEND) — approving a review gate wrongly closes the live stream. The live-drain loop
treats `review_gate_approved` as a stream terminal (`run_stream.py:198` checks
`_GATE_RESOLUTION_TYPES`, which lists `review_gate_approved`), but approve RESUMES the run on the
same queue → the stream closes on approve → the FE reconnects. Fix (~2 lines): a new
`_STREAM_TERMINAL_TYPES = _GATE_RESOLUTION_TYPES - {"review_gate_approved"}` used at :198;
`_GATE_RESOLUTION_TYPES` and its :121 `_dangling_review_gate` use stay unchanged (approve is
still a gate-resolution for the D-14g durable re-arm).

Purpose: stop the terminal-run reconnect loop and the approve-closes-the-stream reconnect, both
without weakening genuine reconnect-on-real-drop.
Output: the `useRunStream` liveness guard + `detachRun` + the `page.tsx` wiring + the backend
`_STREAM_TERMINAL_TYPES` split, each with a RED->GREEN test, plus a regression gate.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@.planning/BUG-015-016-GROUNDED-CONTEXT.md

# BUG-015 PRIMARY — the hook under change. dispatchBlock is :217-273 (stream_attached
# handling :267-268), connect() top is :290-301 (reset point), the close/reconnect branch is
# :370-372, scheduleReconnect is :275-288. The refs live at :146-154 (add sawNonLiveAttachRef here).
@frontend/src/hooks/useRunStream.ts

# The EXISTING useRunStream test harness to EXTEND (do not rewrite): serveWire()/wireStream()
# stream the exact backend bytes then CLOSE — this is precisely the non-live-attach-then-close
# shape BUG-015 needs. vi.mock("@/lib/api") provides getToken. Add the two BUG-015 cases here.
@frontend/src/hooks/useRunStream.test.ts

# BUG-015 COMPLEMENTARY — add detachRun (mirror attachRun :331-338), expose on the context
# TYPE (:73-102, after attachRun :92), the DEFAULT_VALUE stub (:109-117, after attachRun :114),
# and the value useMemo + deps (:380-383). focusedRunIdRef :228, recomputeLiveRunIds :234-245.
@frontend/src/providers/RunConnectionProvider.tsx

# The EXISTING provider test to EXTEND. useRunStream is fully mocked; RUNS fixture has
# build-run/gen-run (auto-streamed) + parked-A/parked-B (NOT auto-streamed — use a parked id as
# the focus so detachRun's effect on liveRunIds is isolated). act()+toContain idiom at :85-115.
@frontend/src/providers/RunConnectionProvider.test.tsx

# BUG-015 wiring — the pipeline_complete handler :537-554 (completingRunId :549, the
# isForeignCompletion/trackedRunIdRef gate :550-554). LOAD-BEARING WRINKLE: this handler lives
# inside handleWebSocketMessage, a useCallback([]) that captures INITIAL state (see the :492-496
# comment) and reaches live values ONLY through refs (handlePipelineMsgRef.current?.(...) at :531,
# trackedRunIdRef). runConnection is declared LATER at :935 — a direct runConnection.detachRun
# reference would break the empty-deps design, so wire it through a ref (mirror handlePipelineMsgRef).
@frontend/src/app/dashboard/page.tsx

# BUG-016 — the backend under change. _GATE_RESOLUTION_TYPES :68-77 (review_gate_approved :70),
# _dangling_review_gate uses it at :121 (LEAVE UNCHANGED), the live-drain terminal check at :198
# (change to _STREAM_TERMINAL_TYPES). The drain loop is :188-199.
@backend/app/api/run_stream.py

# The EXISTING backend SSE test to EXTEND. _iter_sse_frames is driven directly with a scripted
# ScopedStore + a pre-populated asyncio.Queue: test_attach_live_queue_drains_until_sentinel
# (:244-264) is the exact drain harness to clone; test_resolved_gate_does_not_rearm (:356-376) +
# the re-arm tests MUST stay green (they exercise the unchanged _GATE_RESOLUTION_TYPES path).
@backend/tests/unit/test_sse_stream.py
</context>

<constraints>
- Branch feat/ui-2. Verify with `git rev-parse --abbrev-ref HEAD`; DO NOT switch. NO commit trailer. NEVER push.
- SEVEN files, no more: `useRunStream.ts` + `.test.ts`, `RunConnectionProvider.tsx` + `.test.tsx`, `page.tsx` (BUG-015); `run_stream.py` + `tests/unit/test_sse_stream.py` (BUG-016). Do NOT touch the BUG-014-B parser fix (the CRLF split + envelope unwrap), the reducer (`useWorkflow.ts`/`handlePipelineMessage`), or the j1u/lb6/n2d/o6z/r7d/sml/uhe fixes.
- Preserve GENUINE reconnect: a live `stream_attached{live:true}` stream that drops MUST still reconnect. This is exactly why `sawNonLiveAttachRef` resets to false at the top of every `connect()`.
- Implement each fix EXACTLY as the grounded spec states. BUG-016 is ~2 lines: define `_STREAM_TERMINAL_TYPES` and use it at :198 only; leave `_GATE_RESOLUTION_TYPES` and its :121 use untouched (approve stays gate-resolved for D-14g re-arm).
- SC-001: key on EVENT-TYPE strings that are pipeline event names (`stream_attached`, `review_gate_approved`, `pipeline_complete`, `agent_start`) and on frame structure — introduce NO workflow-name literal in any fix or test.
- FE is cwd-sensitive: run all tsc / vitest / Playwright from `frontend/`. Kill anything on :3000 before mocked Playwright. `npm run e2e` = `playwright test --project=mocked`.
- Backend: `python3.11` no venv. The FULL backend suite HANGS offline (Chromium/Bedrock/Postgres-gated) — run ONLY `tests/unit/test_sse_stream.py` (and, if you touch nothing else, `tests/unit/test_run_stream_pool_leak.py`). Do NOT delete or loosen `test_resolved_gate_does_not_rearm` or `test_attach_live_queue_drains_until_sentinel`.
- Executor does NOT run live Bedrock and does NOT restart the backend — the orchestrator restarts + live-proves (approve → stream stays open → build resumes → NO "Reconnecting…"; a run reaching completion → NO reconnect-loop banner).
</constraints>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — BUG-015 unit tests (useRunStream non-live-close + live-close control; provider detachRun)</name>
  <files>frontend/src/hooks/useRunStream.test.ts, frontend/src/providers/RunConnectionProvider.test.tsx</files>
  <behavior>
    EXTEND both existing test files (do not rewrite the existing cases).

    A) `useRunStream.test.ts` — add a describe block driving the hook through the EXISTING
       `serveWire`/`wireStream` harness (a ReadableStream that enqueues the wire bytes then CLOSES —
       exactly the "non-live attach then stream closes" shape). Reuse the file's `vi.mock("@/lib/api")`,
       `serveWire`, `wireStream`, and the `renderHook` + `waitFor` idiom.

       Test A1 — PRIMARY (RED today): a non-live attach that closes must NOT reconnect.
       - WIRE = one frame: `id: 5\r\ndata: {"type":"stream_attached","data":{"pipeline_run_id":"r","live":false,"replayed_through_seq":5}}\r\n\r\n`.
       - Render `useRunStream({ runId: "r", token: "t.t.t", onMessage: vi.fn(), enabled: true })`.
       - Assert `await waitFor(() => expect(result.current.phase).toBe("disconnected"))` AND
         `expect(result.current.lastError ?? "").not.toMatch(/Reconnecting/i)`.
       - FAIL-BEFORE: on close the branch runs `scheduleReconnect()`, which SYNCHRONOUSLY sets
         phase `"reconnecting"` + a `Reconnecting…` lastError → the waitFor never sees `"disconnected"`
         (RED). GREEN once the close branch skips reconnect for a non-live attach and settles quiescent.

       Test A2 — CONTROL (green both ways): a live attach that drops STILL reconnects.
       - WIRE = one frame with `"live":true`: `id: 5\r\ndata: {"type":"stream_attached","data":{"pipeline_run_id":"r","live":true,"replayed_through_seq":5}}\r\n\r\n`.
       - Assert `await waitFor(() => expect(result.current.phase).toBe("reconnecting"))`. (scheduleReconnect
         sets `"reconnecting"` synchronously before its 1s timer, so waitFor resolves immediately — the
         actual delayed reconnect never fires within the test; cleanup aborts it. Optionally wrap this
         test in `vi.useFakeTimers()`/`vi.useRealTimers()` to be fully deterministic.)
       - Proves the fix judges liveness per-connection (the ref reset) and does not kill genuine reconnect.

    B) `RunConnectionProvider.test.tsx` — add a test for `detachRun`, cloning the Test-2 `act()`+`toContain`
       idiom (:85-115). Use a PARKED id (`parked-A`, not in the auto-streamed set) as the focus so its
       presence in `liveRunIds` comes ONLY from the focus and detach is observable in isolation.
       - `act(() => result.current.attachRun("parked-A"))` → `expect(liveRunIds).toContain("parked-A")`.
       - `act(() => result.current.detachRun("gen-run"))` (a NON-focused id) →
         `expect(liveRunIds).toContain("parked-A")` (no-op; the focus is untouched).
       - `act(() => result.current.detachRun("parked-A"))` (the focus) →
         `expect(liveRunIds).not.toContain("parked-A")` (focus cleared, id dropped).
       - FAIL-BEFORE: `result.current.detachRun` does not exist → calling it throws
         `detachRun is not a function` (RED). GREEN once detachRun is on the context value. (vitest/esbuild
         strips types without type-checking, so the test RUNS and fails at runtime even before the type exists.)
  </behavior>
  <action>Extend the two test files per the behavior block. Do NOT modify any production source in this task — A1 and the detachRun test MUST be RED against current code (A1: phase settles `reconnecting`, not `disconnected`; detachRun: not a function), failing on the SPECIFIED assertions, not on import/compile errors. A2 MUST be green. SC-001: fixtures key on `stream_attached`/`live` and run-id/status strings only — no workflow-name literal.</action>
  <verify>
    <automated>cd frontend && npx vitest --run src/hooks/useRunStream.test.ts src/providers/RunConnectionProvider.test.tsx 2>&1 | tail -40</automated>
  </verify>
  <done>useRunStream.test.ts A1 (non-live close → expect `disconnected`) is RED (currently `reconnecting`); A2 (live close → `reconnecting`) is GREEN. RunConnectionProvider.test.tsx detachRun test is RED (`detachRun is not a function`). Failures are on the specified assertions, not compile/import errors. No workflow-name literal.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — BUG-015 fixes (useRunStream liveness guard, RunConnectionProvider.detachRun, page.tsx wiring)</name>
  <files>frontend/src/hooks/useRunStream.ts, frontend/src/providers/RunConnectionProvider.tsx, frontend/src/app/dashboard/page.tsx</files>
  <behavior>Task-1 A1 and the detachRun test go GREEN, A2 stays GREEN; `npx tsc --noEmit` is clean.</behavior>
  <action>
FIX 1 — useRunStream.ts liveness guard.
  a. Declare `const sawNonLiveAttachRef = useRef(false);` alongside the other refs (near :146-154, component-body level so it persists across the connect loop).
  b. In `dispatchBlock`, at the `stream_attached` handling (:267-268), record the attach liveness:
     set `sawNonLiveAttachRef.current = data.live !== true;` whenever `type === "stream_attached"`.
     KEEP the existing `if (type === "stream_attached" && data.live === true) setPhase("live");`.
  c. At the TOP of `connect()` (:290, before/right after the token guard, on every connect INCLUDING
     reconnects), reset `sawNonLiveAttachRef.current = false;` — so a genuine live drop still reconnects.
  d. In the response-ended/close branch (:370-372), gate the reconnect on the ref and settle quiescent
     otherwise:
       when `!stoppedRef.current && !controller.signal.aborted`: if `sawNonLiveAttachRef.current` is true,
       call `setPhase("disconnected")` (do NOT set an error banner, do NOT call scheduleReconnect); else
       call `scheduleReconnect()` as today.
  Change NOTHING else in the hook — the BUG-014-B CRLF split (:356) + envelope unwrap (:229-245), the
  seq-cursor advance, the keepalive skip, and the auth/refresh paths stay untouched.

FIX 2 — RunConnectionProvider.tsx detachRun (mirror attachRun :331-338).
  a. Add to the context TYPE `RunConnectionContextValue` (after `attachRun`, ~:92):
     `detachRun: (runId: string) => void;` with a one-line doc (releases the sticky focus for a completed run).
  b. Add to `DEFAULT_VALUE` (~:114): `detachRun: () => {},`.
  c. Add the callback (near attachRun :331-338):
     `const detachRun = useCallback((runId: string) => { if (focusedRunIdRef.current === runId) { focusedRunIdRef.current = null; recomputeLiveRunIds(); } }, [recomputeLiveRunIds]);`
     — clears the focus ONLY when it matches (a non-focused id is a no-op), then re-materializes the union.
  d. Add `detachRun` to the value useMemo object AND its deps array (:380-383).

FIX 3 — page.tsx wiring (the LOAD-BEARING WRINKLE). The pipeline_complete handler (:537-554) is inside
  `handleWebSocketMessage`, a `useCallback([])` that reaches live values ONLY through refs
  (`handlePipelineMsgRef.current?.(...)` at :531). `runConnection` is declared later at :935, so do NOT
  reference it directly here (it would force it into the empty deps and break the stale-closure design).
  Instead mirror the ref idiom:
  a. Declare `const detachRunRef = useRef<((runId: string) => void) | null>(null);` near the other refs
     (with trackedRunIdRef / handlePipelineMsgRef).
  b. After `runConnection` is defined (~:935), sync it:
     `useEffect(() => { detachRunRef.current = runConnection.detachRun; }, [runConnection.detachRun]);`
  c. In the pipeline_complete handler, in the NON-foreign branch (where `completingRunId && !isForeignCompletion`
     is true, alongside `setContentSourceRunId(completingRunId)` at :554), call
     `detachRunRef.current?.(completingRunId);` — release the focus so the finished run's RunStreamConnection
     unmounts (no reconnect, no ~14k re-replay). This does NOT remove the rendered preview/content (already in state).
  Do NOT put any fenced code in the source beyond these edits; touch no other logic.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | tail -15</automated>
    <automated>cd frontend && npx vitest --run src/hooks/useRunStream.test.ts src/providers/RunConnectionProvider.test.tsx 2>&1 | tail -30</automated>
  </verify>
  <done>`tsc --noEmit` clean. useRunStream.test.ts A1 GREEN (non-live close → `disconnected`, no Reconnecting banner) and A2 GREEN (live close → `reconnecting`). RunConnectionProvider.test.tsx detachRun GREEN (clears focus + drops the id; non-focused id no-op). page.tsx calls `detachRunRef.current?.(completingRunId)` for the tracked completing run via a ref (not a direct runConnection reference). No workflow-name literal.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: BUG-016 backend RED->GREEN — _STREAM_TERMINAL_TYPES (approve no longer closes the live stream)</name>
  <files>backend/tests/unit/test_sse_stream.py, backend/app/api/run_stream.py</files>
  <behavior>
    STEP 1 (RED) — EXTEND `test_sse_stream.py` (clone the `test_attach_live_queue_drains_until_sentinel`
    harness :244-264: `_seed_run`, one durable `agent_start`, an `asyncio.Queue`, `_drive`, `_collect`, `_parse`).
    Add a class (e.g. `TestLiveDrainTerminals`) with two tests:

      T1 — RED today: `review_gate_approved` does NOT close the live stream.
      - Seed run (status "running") + durable `[(1, "agent_start", {"seq": 1})]`.
      - Queue: put `{"type": "review_gate_approved", "data": {"seq": 2}}`, then
        `{"type": "agent_start", "data": {"seq": 3, "agent": "prototype-plan"}}`, then `None`.
      - Collect `_iter_sse_frames(run_id="run-1", store=_store(db), after_seq=0, live_queue=q)`.
      - Assert BOTH a `review_gate_approved` frame (id "2") AND an `agent_start` frame (id "3") are yielded.
      - FAIL-BEFORE: `review_gate_approved` is in `_GATE_RESOLUTION_TYPES`, so the drain `return`s right
        after yielding it → the `agent_start` frame is never yielded → RED. GREEN once `:198` uses
        `_STREAM_TERMINAL_TYPES` (which excludes `review_gate_approved`).

      T2 — CONTROL (green both ways): `pipeline_complete` DOES end the drain.
      - Same seed; Queue: put `{"type": "pipeline_complete", "data": {"seq": 2}}`, then
        `{"type": "agent_start", "data": {"seq": 3}}`, then `None`.
      - Assert a `pipeline_complete` frame (id "2") IS yielded and NO `agent_start` frame (id "3") is —
        the terminal ends the drain before the post-terminal event. Proves the fix keeps genuine terminals closing.

    STEP 2 (GREEN) — apply the run_stream.py fix, then re-run: T1 goes GREEN, T2 stays GREEN, and the existing
    suite (rearm/gate/replay/attach) stays green.
  </behavior>
  <action>
STEP 1: Write T1 + T2 first and run them — T1 MUST be RED (agent_start frame absent), T2 GREEN.

STEP 2: Fix `backend/app/api/run_stream.py`:
  - Immediately AFTER the `_GATE_RESOLUTION_TYPES` frozenset (:68-77), define:
    `_STREAM_TERMINAL_TYPES = _GATE_RESOLUTION_TYPES - frozenset({"review_gate_approved"})`
    with a short comment: the live-drain stream terminals — approve RESUMES the run (engine keeps
    building on the same queue), so it is NOT a stream terminal here; only pipeline_complete /
    pipeline_cancelled / pipeline_failed / budget_aborted / error close the drain.
  - Change the live-drain terminal check at `:198` from `if event.get("type") in _GATE_RESOLUTION_TYPES:`
    to `if event.get("type") in _STREAM_TERMINAL_TYPES:`.
  - LEAVE `_GATE_RESOLUTION_TYPES` (:68-77) and its `_dangling_review_gate` use (:121) UNCHANGED —
    approve is still a gate-resolution for the D-14g durable re-arm derivation.
  SC-001: no workflow-name literal (keys on pipeline event-type strings only).
  </action>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/unit/test_sse_stream.py -v 2>&1 | tail -40</automated>
  </verify>
  <done>run_stream.py defines `_STREAM_TERMINAL_TYPES = _GATE_RESOLUTION_TYPES - frozenset({"review_gate_approved"})` and uses it at :198; `_GATE_RESOLUTION_TYPES` + :121 unchanged. T1 GREEN (both review_gate_approved AND agent_start yielded — stream stays open on approve); T2 GREEN (pipeline_complete ends the drain, agent_start not yielded). `test_resolved_gate_does_not_rearm`, `test_attach_live_queue_drains_until_sentinel`, and the re-arm/replay tests all still pass. No workflow-name literal.</done>
</task>

<task type="auto">
  <name>Task 4: Regression gate — full mocked transport/gate e2e + targeted vitest + backend SSE pytest green</name>
  <files>(no source edits — acceptance gate)</files>
  <action>
Prove neither fix regressed the live transport. Do NOT edit source; a red here signals a real problem to report.

FRONTEND (from `frontend/`): `npx tsc --noEmit` clean; the targeted transport vitest green
(useRunStream, RunConnectionProvider, useWorkflow.reconnect, useWorkflow.clarifyRetention,
__tests__/useWorkflow.pipelineCancelled, useRunChat, RunChatLane); then kill :3000
(`lsof -ti:3000 | xargs kill -9 2>/dev/null || true`) and run the full mocked SSE / streaming / chat /
reconnect / gate / questionnaire e2e: ts-sse, ts-sse-resilience, ts-s.reconnect, ts-j.streaming,
ts-chat, ts-chat-cards, ts-m.questionnaire, ts-n.review-gate, ts-g.review-gates. They MUST pass.
The 8 pre-Phase-42 vitest reds in UNTOUCHED files are NOT regressions.

BACKEND (from `backend/`): `python3.11 -m pytest tests/unit/test_sse_stream.py tests/unit/test_run_stream_pool_leak.py -v` green. Do NOT run the full backend suite (it hangs offline).

If a spec goes RED: (1) selector/text-drift flake unrelated to the change → note + re-run to confirm;
(2) a REAL transport/parse/drain failure → a fix is incomplete, investigate and fix the seven in-scope
files — do NOT delete, loosen, or `.fixme` any spec to force green. Executor does NOT run live Bedrock /
does NOT restart the backend — the orchestrator owns the live proof.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | tail -10 && npx vitest --run src/hooks/useRunStream.test.ts src/providers/RunConnectionProvider.test.tsx src/hooks/useWorkflow.reconnect.test.ts src/hooks/useWorkflow.clarifyRetention.test.ts src/hooks/__tests__/useWorkflow.pipelineCancelled.test.ts src/hooks/useRunChat.test.ts src/components/chat/RunChatLane.test.tsx 2>&1 | tail -25</automated>
    <automated>cd frontend && (lsof -ti:3000 | xargs kill -9 2>/dev/null || true) && npx playwright test --project=mocked e2e/tests/ts-sse.spec.ts e2e/tests/ts-sse-resilience.spec.ts e2e/tests/ts-s.reconnect.spec.ts e2e/tests/ts-j.streaming.spec.ts e2e/tests/ts-chat.spec.ts e2e/tests/ts-chat-cards.spec.ts e2e/tests/ts-m.questionnaire.spec.ts e2e/tests/ts-n.review-gate.spec.ts e2e/tests/ts-g.review-gates.spec.ts 2>&1 | tail -40</automated>
    <automated>cd backend && python3.11 -m pytest tests/unit/test_sse_stream.py tests/unit/test_run_stream_pool_leak.py -v 2>&1 | tail -40</automated>
  </verify>
  <done>tsc clean; the targeted transport vitest green; the nine mocked transport/gate/questionnaire e2e all pass against the real wire; backend test_sse_stream.py + test_run_stream_pool_leak.py green. No spec deleted / loosened / fixme'd. No file outside the seven-file scope changed.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| backend SSE down-channel (`GET /api/runs/{id}/events/stream`) → FE `useRunStream` reconnect logic | The connection-close signal drives an auto-reconnect loop; a terminal-run close must NOT be treated as a recoverable drop, and a genuine mid-build drop MUST still recover |
| review-gate approve (up-channel REST) → backend live-drain loop | An approve RESUMES the run on the same live queue; misclassifying it as a stream terminal silently drops the post-approve event stream |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-1c1-01 | Denial of Service | useRunStream close branch (:370-372) — reconnect-on-any-close re-replays ~14k events per cycle for a completed, still-focused run → CPU/network loop + flapping banner | mitigate | `sawNonLiveAttachRef` (reset per `connect()`, set from the last `stream_attached` liveness) suppresses reconnect after a non-live close and settles to a quiescent `disconnected` phase; `detachRun` unmounts the dead connection at completion |
| T-1c1-02 | Denial of Service | run_stream.py live-drain (:198) — approve wrongly closes the stream → FE reconnect + full replay on every gate approval | mitigate | `_STREAM_TERMINAL_TYPES` excludes `review_gate_approved` so the open stream keeps delivering post-approve `generating` frames; genuine terminals still close the drain |
| T-1c1-03 | Tampering | availability of genuine reconnect (a real live drop must still recover) | mitigate | `sawNonLiveAttachRef` resets to false at the top of every `connect()`, so liveness is judged per-connection — a `stream_attached{live:true}` drop still reconnects (control test A2 guards this) |
| T-1c1-04 | Repudiation | D-14g durable gate re-arm (`_dangling_review_gate`, :121) must still treat approve as gate-resolved | accept | `_GATE_RESOLUTION_TYPES` and its :121 use are unchanged by this fix; `test_resolved_gate_does_not_rearm` + the re-arm tests guard it |
| T-1c1-SC | Tampering | npm/pip installs | accept | No new dependencies; a seven-file in-place edit (2 FE prod + 2 FE test + 1 FE wiring + 1 backend prod + 1 backend test) |
</threat_model>

<verification>
- `cd frontend && npx tsc --noEmit` clean.
- BUG-015 useRunStream: A1 (non-live attach + close → `disconnected`, no Reconnecting banner) RED before Task 2, GREEN after; A2 (live attach + close → `reconnecting`) green throughout.
- BUG-015 RunConnectionProvider: detachRun clears focus + drops the id from liveRunIds; a non-focused id is a no-op — RED before Task 2, GREEN after.
- BUG-016 backend: T1 (approve then agent_start → BOTH yielded) RED before the fix, GREEN after; T2 (pipeline_complete ends the drain) green both ways. `test_resolved_gate_does_not_rearm` + `test_attach_live_queue_drains_until_sentinel` stay green.
- Regression: the targeted transport vitest + the nine mocked SSE/streaming/chat/reconnect/gate/questionnaire e2e + backend test_sse_stream.py/test_run_stream_pool_leak.py all green.
- SC-001: no workflow-name literal in any fix or test.
- The 8 pre-Phase-42 vitest reds in UNTOUCHED files are NOT regressions.
- Live proof is the ORCHESTRATOR's (after applying + restarting the backend): approve a review gate → the stream stays open, build resumes, NO "Reconnecting…"; a run reaching completion → NO reconnect-loop banner. If either still fails, report it — do not silently pass.
</verification>

<success_criteria>
- useRunStream.ts: `sawNonLiveAttachRef` (reset per connect, set from `stream_attached` liveness) makes the close branch skip `scheduleReconnect()` + settle `disconnected` after a non-live close, while a live drop still reconnects.
- RunConnectionProvider.tsx: `detachRun(runId)` on the context value + type + default stub clears the sticky focus (match-only) and recomputes liveRunIds.
- page.tsx: the pipeline_complete handler releases the tracked completing run's focus via a ref (`detachRunRef.current?.(completingRunId)`), not a direct runConnection reference.
- run_stream.py: `_STREAM_TERMINAL_TYPES = _GATE_RESOLUTION_TYPES - frozenset({"review_gate_approved"})` used at :198; `_GATE_RESOLUTION_TYPES` + :121 unchanged.
- Exactly seven files changed; branch stays feat/ui-2; no push; no commit trailer.
</success_criteria>

<output>
Create `.planning/quick/260717-1c1-fix-bug-015-frontend-a-completed-run-s-s/SUMMARY.md` when done.
</output>
