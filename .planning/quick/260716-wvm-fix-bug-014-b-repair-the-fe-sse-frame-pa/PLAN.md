---
phase: quick-260716-wvm
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/hooks/useRunStream.ts
  - frontend/src/hooks/useRunStream.test.ts
  - frontend/e2e/fixtures/mockSse.ts
  - frontend/e2e/tests/ts-sse-resilience.spec.ts
autonomous: true
requirements:
  - BUG-014-B
must_haves:
  truths:
    - "The FE SSE parser splits frames on the REAL backend wire: a chunk `id: N\\r\\ndata: {...}\\r\\n\\r\\n` boundary-matches (CRLF normalized to LF before the `indexOf(\"\\n\\n\")` split) → dispatchBlock runs per frame on a held-open live stream, not only on close."
    - "dispatchBlock is envelope-aware: when the parsed `data:` JSON is the real `{type, data}` envelope (no `event:` line), it dispatches `{ type: parsed.type, data: parsed.data }` so `questionnaire_ready` / `review_gate_ready` / every case fires (msg.type !== \"\")."
    - "The parser stays TOLERANT of the legacy shape (`\\n\\n` frames + an `event:` type line + flat data) — that path still parses unchanged, so nothing that relied on it silently breaks."
    - "The seq cursor (Last-Event-ID resume) still advances after the type moved into the envelope: it reads `data.seq` (inner payload) with the `id:` line as fallback — both intact."
    - "mockSse.ts emits the REAL wire (`id: N\\r\\ndata: {\"type\":\"<t>\",\"data\":{...}}\\r\\n\\r\\n`) so the full mocked SSE/streaming/chat/reconnect/history/revisions e2e exercise the true format and stay green (no more false-green against the wrong wire)."
  artifacts:
    - path: "frontend/src/hooks/useRunStream.ts"
      provides: "CRLF-tolerant frame split (:341) + envelope-aware type/data in dispatchBlock, tolerant of both wire shapes"
      contains: "replace(/\\r\\n/g"
    - path: "frontend/src/hooks/useRunStream.test.ts"
      provides: "RED->GREEN unit test feeding the ACTUAL backend wire: single-frame envelope (fires once, type=questionnaire_ready), multi-frame \\r\\n\\r\\n (2 dispatches), legacy \\n\\n+event: (tolerance, green both ways)"
      contains: "questionnaire_ready"
    - path: "frontend/e2e/fixtures/mockSse.ts"
      provides: "serialize() emits the real `id: N\\r\\ndata: {type,data}\\r\\n\\r\\n` envelope wire"
      contains: "\\\\r\\\\n"
    - path: "frontend/e2e/tests/ts-sse-resilience.spec.ts"
      provides: "fetchSse() inline consumer updated to parse the real wire (CRLF normalize + envelope-aware), tolerant — so the resilience specs stay green"
      contains: "parsed.type"
  key_links:
    - from: "useRunStream.connect() decode loop (:341)"
      to: "dispatchBlock via indexOf(\"\\n\\n\") split (:343)"
      via: "buf += decoder.decode(...).replace(/\\r\\n/g, \"\\n\")"
      pattern: "replace\\(/\\\\r\\\\n/g"
    - from: "dispatchBlock JSON.parse of the data: line"
      to: "RunStreamMessage { type, data } → onMessageRef (reducer)"
      via: "if parsed.type is a string → type=parsed.type, data=parsed.data; else legacy typeLine + parsed-as-data"
      pattern: "parsed\\.type"
---

<objective>
Fix BUG-014-B: the FE SSE frame parser never parses ANY live frame, so all live streaming
is dead (a fresh top-level launch sits at "Pipeline running · 0/0 · BUILDING" with no
clarify, no gate, no progress, no working Stop; only REST reopen limps along). Two coupled
defects in `frontend/src/hooks/useRunStream.ts`:

1. The frame split at `:343` uses `buf.indexOf("\n\n")` (LF-LF), but the backend
   (`sse-starlette==3.0.2`) serializes frames with CRLF separators — `id: N\r\ndata: {...}\r\n\r\n`.
   `"\r\n\r\n".indexOf("\n\n") === -1` → the split loop NEVER runs → dispatchBlock is never
   called for a held-open live stream → ZERO live frames reach the reducer.
2. Even once frames split, `dispatchBlock` reads the event type from an `event:` line
   (`:224`), but the backend emits NO `event:` line — it nests the envelope inside the
   `data:` JSON as `{"type": "...", "data": {...}}`. So type stays `""` → every reducer
   case (`questionnaire_ready` …) silently no-ops.

Implement EXACTLY the grounded fix from `.planning/BUG-014-B-GROUNDED-CONTEXT.md`. Root
cause is runtime-proven (raw-wire hexdump) + orchestrator-verified. Do NOT re-investigate.
Keep the parser TOLERANT of both the real wire (`\r\n\r\n` + `{type,data}` envelope) and the
legacy shape (`\n\n` + `event:` line + flat data). Update the e2e mock to emit the real wire
(so the mocked specs stop being false-green), and update the one hand-rolled inline SSE
consumer that reads the mock's raw body (`ts-sse-resilience.spec.ts`) to match.

Purpose: repair the sole live run transport so live clarify / gates / progress stream again.
Output: two parser fixes (useRunStream.ts) + a new RED->GREEN unit test + the mock wire
rewrite + the resilience-spec inline-parser update; the FULL mocked SSE/streaming/chat/
reconnect/history e2e stay green against the true format.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@.planning/BUG-014-B-GROUNDED-CONTEXT.md

# The parser under change (the ONLY production file). The split loop is :338-350
# (decode :341, `while ((idx = buf.indexOf("\n\n")) !== -1)` :343); dispatchBlock is
# :217-263 (event: line :224, data: line :225, seq-cursor advance :238-252,
# keepalive skip :255, stream_attached{live:true} :258).
@frontend/src/hooks/useRunStream.ts

# The e2e mock's frame builder to rewrite — serialize() at :431-442 currently emits the
# WRONG wire (`id: N\nevent: <t>\ndata: <flat>\n\n`). Its header "Wire model" doc (:30-35)
# documents that wrong shape too.
@frontend/e2e/fixtures/mockSse.ts

# Hook-test idioms to clone (renderHook + vi.mock; this project has @testing-library/react
# renderHook, jsdom env, vitest.setup.ts). useRunChat.test.ts shows the frame/renderHook style.
@frontend/src/hooks/useRunChat.test.ts

# The ONLY other consumer that parses the mock's RAW serialized body (a hand-rolled inline
# fetch consumer, `fetchSse` :40-67, splitting `\n\n` + reading an `event:` line). It WILL
# break when the mock wire changes unless updated in lockstep — this is the load-bearing wrinkle.
@frontend/e2e/tests/ts-sse-resilience.spec.ts
</context>

<constraints>
- Branch feat/ui-2. Verify with `git rev-parse --abbrev-ref HEAD`; DO NOT switch. NO commit trailer. NEVER push.
- FRONTEND ONLY. Four files, no more: `useRunStream.ts`, `useRunStream.test.ts` (new), `mockSse.ts`, `ts-sse-resilience.spec.ts`. Do NOT touch the backend SSE (`run_stream.py`/sse-starlette — the wire is CORRECT), the reducer (`useWorkflow.ts`/`handlePipelineMessage`), `RunConnectionProvider.tsx` (BUG-013), or the j1u/lb6/n2d/o6z/r7d/sml/uhe fixes.
- Keep the parser TOLERANT of BOTH wire shapes. The envelope discriminator is safe: no reducer reads `data.type` and no flat payload carries a top-level `type` key (verified) — so "parsed has a string `type` field" cleanly distinguishes the real `{type,data}` envelope from a legacy flat payload.
- Implement the two useRunStream fixes EXACTLY as the spec states (CRLF normalize on decode, keeping the `indexOf("\n\n")` split; envelope-aware type/data in dispatchBlock). Preserve the seq-cursor advance, the keepalive skip (`pipeline_heartbeat`/`pong`), and `stream_attached{live:true} → setPhase("live")`.
- SC-001: the parser keys on FRAME STRUCTURE (CRLF, `id:`/`data:` lines, the `{type,data}` envelope) — introduce NO workflow-name literal in the fix, the mock, or the tests.
- FE is cwd-sensitive: run all tsc / vitest / Playwright from `frontend/`. Kill anything on :3000 before mocked Playwright. `npm run e2e` = `playwright test --project=mocked`.
- Tests RED->GREEN then the FULL mocked transport suite green: ts-sse, ts-sse-resilience, ts-s.reconnect, ts-j.streaming, ts-chat, ts-chat-cards, ts-t.history, ts-u.revisions, ts-y.* + useRunStream/useWorkflow/useRunChat/RunChatLane vitest. The 8 pre-Phase-42 vitest reds in UNTOUCHED files are NOT regressions. Executor does NOT run live Bedrock (the orchestrator live-proves the fresh-launch → live-clarify → live-gate flow).
</constraints>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — new useRunStream unit test feeding the ACTUAL backend wire (never parses today)</name>
  <files>frontend/src/hooks/useRunStream.test.ts</files>
  <behavior>
    Create `frontend/src/hooks/useRunStream.test.ts`. Render the hook with `renderHook` from
    `@testing-library/react` and drive it through a mocked `fetch` whose response body is a
    `ReadableStream` yielding the wire bytes, exactly mirroring the hook's real transport.

    Harness (clone the vi.mock/renderHook idiom):
    - `vi.mock("@/lib/api", () => ({ getToken: () => "t.t.t", setToken: vi.fn(), clearToken: vi.fn() }))`
      so `connect()` passes the token guard. (`@/lib/env` can stay real — `ENV.API_URL` only
      shapes the URL string.)
    - Helper `wireStream(text: string)` → `new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode(text)); c.close(); } })`.
    - `beforeEach`: `global.fetch = vi.fn(async () => ({ status: 200, ok: true, body: wireStream(WIRE) } as unknown as Response))`
      (set WIRE per test). Restore in `afterEach`.
    - Mount: `renderHook(() => useRunStream({ runId: "r", token: "t.t.t", onMessage, enabled: true }))`
      with `const onMessage = vi.fn()`. Await delivery with `await waitFor(() => expect(onMessage)...)`
      from `@testing-library/react` (the read loop + dispatch are async).

    Test (a) — PRIMARY (the real single frame, RED today):
    - WIRE = `"id: 1\r\ndata: {\"type\":\"questionnaire_ready\",\"data\":{\"pipeline_run_id\":\"r\",\"questions\":[{\"question_id\":\"q1\",\"question_text\":\"Q?\"}]}}\r\n\r\n"`.
    - Assert `onMessage` fires ONCE with `{ type: "questionnaire_ready", data: { pipeline_run_id: "r", questions: [{ question_id: "q1", question_text: "Q?" }] } }`.
    - FAIL-BEFORE: the CRLF split never matches, so only the on-close flush fires dispatchBlock
      once on the whole buffer, with NO `event:` line → it dispatches `{ type: "", data: <the {type,data} envelope, un-unwrapped> }`. So `toHaveBeenCalledWith(...the questionnaire envelope...)` is RED (type is "" and data is the wrong nesting). GREEN after both fixes.

    Test (b) — MULTI-FRAME (two frames in one chunk):
    - WIRE = frame(seq 1, questionnaire_ready) + frame(seq 2, review_gate_ready) each terminated
      by `\r\n\r\n`, concatenated. Assert `await waitFor(() => expect(onMessage).toHaveBeenCalledTimes(2))`
      and the two calls carry `type: "questionnaire_ready"` then `type: "review_gate_ready"`.
    - FAIL-BEFORE: no `\n\n` boundary → the loop never runs → the on-close flush dispatches the
      whole two-frame buffer as ONE malformed block → 1 call (not 2), type "". GREEN after.

    Test (c) — LEGACY TOLERANCE (must stay green BOTH ways, not RED):
    - WIRE = `"id: 1\nevent: agent_start\ndata: {\"agent_id\":\"a1\",\"seq\":1,\"event_id\":\"e1\"}\n\n"`.
    - Assert `onMessage` fires once with `{ type: "agent_start", data: { agent_id: "a1", seq: 1, event_id: "e1" } }`.
    - This PASSES before (the shape the old parser was built for) AND after (tolerance guard) —
      it proves the fix does not drop the legacy path.

    Optionally assert the seq-cursor path survives the envelope move: after Test (b), the hook's
    returned `cursor` (or the last `onCursor` value if you pass one) is 2 — proving the cursor
    still advances from `id:`/`data.seq` when the type lives in the envelope.
  </behavior>
  <action>Write the new test file per the behavior block. Do NOT modify useRunStream.ts in this task — Tests (a) and (b) MUST be RED against current source, failing on the SPECIFIED assertions (wrong envelope / call count), not on compile or import errors; Test (c) MUST be green. SC-001: the wire fixtures key on frame structure + event-type strings that are pipeline event names (not workflow names) — no workflow-name literal.</action>
  <verify>
    <automated>cd frontend && npx vitest --run src/hooks/useRunStream.test.ts 2>&1 | tail -35</automated>
  </verify>
  <done>useRunStream.test.ts exists with three cases. (a) single-frame envelope and (b) multi-frame are RED against current code (a: dispatched type==="" / wrong data nesting; b: 1 call not 2), failing on the specified assertions — not compile errors. (c) legacy `\n\n`+`event:` is GREEN. No workflow-name literal.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — CRLF-tolerant split + envelope-aware dispatch (useRunStream.ts), real-wire mock (mockSse.ts), and the resilience-spec inline parser (ts-sse-resilience.spec.ts)</name>
  <files>frontend/src/hooks/useRunStream.ts, frontend/e2e/fixtures/mockSse.ts, frontend/e2e/tests/ts-sse-resilience.spec.ts</files>
  <behavior>Task-1 (a) and (b) go GREEN and (c) stays GREEN; `npx tsc --noEmit` is clean; the targeted vitest (useRunStream, useWorkflow.*, useRunChat, RunChatLane) stays green; and ts-sse-resilience's inline consumer parses the new wire so its four resilience tests stay green.</behavior>
  <action>
FIX 1 — CRLF-tolerant frame split (useRunStream.ts:341). Change
  `buf += decoder.decode(value, { stream: true });`
to
  `buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");`
Keep the `while ((idx = buf.indexOf("\n\n")) !== -1)` split at :343 UNCHANGED. (This targets only
line-ending CRLF; JSON string data escapes newlines as literal `\n`, never raw `\r\n`, so payloads
are untouched.)

FIX 2 — Envelope-aware type/data in dispatchBlock (useRunStream.ts:217-263). Today (:222-235) it
reads `event:`/`data:` lines, sets `const type = typeLine ?? ""`, and `data = JSON.parse(dataLine)`.
Change `const type` to `let type = typeLine ?? "";` and, inside the `if (dataLine)` try-block, after
`JSON.parse`, branch on the parsed shape:
  - Real envelope: if the parsed value is an object with a string `type` field (i.e.
    `typeof parsed.type === "string"`), set `type = parsed.type` and
    `data = (parsed.data as Record<string, unknown>) ?? {}`.
  - Legacy/mock flat shape: otherwise keep `type = typeLine ?? ""` and `data = parsed` (the whole
    parsed object is the payload) — the existing behavior.
Keep the malformed-JSON `catch { return; }`. Leave EVERYTHING after it unchanged — the seq-cursor
advance (:238-252, reads `data.seq` with the `id:` line fallback — both still present under the
envelope), the keepalive skip (`pipeline_heartbeat`/`pong`, :255), and the
`stream_attached && data.live === true → setPhase("live")` promotion (:258). Do NOT place any fenced
code in the file beyond the actual edit; change no other lines, no other file logic.

FIX 3 — Real-wire mock (mockSse.ts serialize(), :431-442). Rewrite the returned frame string from
the wrong `id: ${seq}\nevent: ${type}\ndata: ${flat}\n\n` to the REAL wire: build the envelope
`JSON.stringify({ type: f.type, data: dataObj })` (where `dataObj` is the existing
`{ ...f.data, ...extras }`, so `chunk`/`section` from `emitStream` land INSIDE the inner data,
and `event_id`/`seq` stay in the inner data), and emit
  `` `id: ${f.data.seq}\r\ndata: ${envelope}\r\n\r\n` ``
— i.e. DROP the `event:` line, wrap the payload in the `{type,data}` envelope, and use `\r\n`
separators (matching sse-starlette). Also update the header "Wire model" doc comment (:30-35) to
describe the real `id: {seq}` + `data: {"type","data":{…}}` envelope instead of the retired
`event:` line, so the fixture doc is not misleading.

FIX 4 — Resilience inline consumer (ts-sse-resilience.spec.ts fetchSse, :45-64). This hand-rolled
in-page consumer reads the mock's RAW body and today splits `text.split("\n\n")` + reads an
`event:` line — it will break on the new `\r\n\r\n` + envelope wire. Update it to mirror the hook:
normalize CRLF first (`text.replace(/\r\n/g, "\n")`) before the `.split("\n\n")`, and after
`JSON.parse(dataLine)` apply the same tolerant branch — if `typeof parsed.type === "string"` use
`type = parsed.type` + `data = parsed.data`, else fall back to the `event:`-line `type` + `parsed`
as data. Keep pushing `{ seq: Number(id), type, data }`. This preserves every existing resilience
assertion (they read `e.seq` from the `id:` line and `e.data.event_id`/`e.data.seq` from the inner
payload — both intact). Change nothing else in the spec.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | tail -15</automated>
    <automated>cd frontend && npx vitest --run src/hooks/useRunStream.test.ts src/hooks/useWorkflow.reconnect.test.ts src/hooks/useWorkflow.clarifyRetention.test.ts src/hooks/__tests__/useWorkflow.pipelineCancelled.test.ts src/hooks/useRunChat.test.ts src/components/chat/RunChatLane.test.tsx 2>&1 | tail -30</automated>
  </verify>
  <done>`tsc --noEmit` clean. useRunStream.test.ts all green: (a) single-frame envelope dispatches `{type:"questionnaire_ready", data:{…questions…}}`; (b) two dispatches; (c) legacy tolerance still parses; cursor advances to 2. useWorkflow.*/useRunChat/RunChatLane vitest stay green. mockSse.serialize emits `id: N\r\ndata: {type,data}\r\n\r\n`; ts-sse-resilience's fetchSse parses it. No workflow-name literal (SC-001).</done>
</task>

<task type="auto">
  <name>Task 3: Regression gate — full mocked SSE/streaming/chat/reconnect/history/revisions e2e green against the REAL wire</name>
  <files>(no source edits — acceptance gate)</files>
  <action>
Run the full mocked transport e2e suite from `frontend/` against the now-real mock wire. Kill any
process on :3000 first (`lsof -ti:3000 | xargs kill -9 2>/dev/null || true`). Then run the SSE /
streaming / chat / reconnect / history / revisions specs:
  `npx playwright test --project=mocked e2e/tests/ts-sse.spec.ts e2e/tests/ts-sse-resilience.spec.ts e2e/tests/ts-s.reconnect.spec.ts e2e/tests/ts-j.streaming.spec.ts e2e/tests/ts-chat.spec.ts e2e/tests/ts-chat-cards.spec.ts e2e/tests/ts-t.history.spec.ts e2e/tests/ts-u.revisions.spec.ts e2e/tests/ts-y.resilience.spec.ts e2e/tests/ts-y.run-scope-clarify.spec.ts`
They MUST all pass — they now exercise the TRUE `\r\n\r\n` + `{type,data}` envelope through the
mounted app's real `useRunStream` parser (previously false-green against the wrong wire).
If a spec goes RED: (1) if it is a selector/text-drift flake unrelated to the wire, note it and
re-run to confirm; (2) if it is a REAL parse/transport failure, the fix is incomplete — investigate
and fix the parser/mock, do NOT delete, loosen, or `.fixme` the spec to force green. Do NOT touch
any file outside the four in scope; a red in an unrelated surface signals a genuine problem to report.
Executor does NOT run live Bedrock — the orchestrator owns the live proof.
  </action>
  <verify>
    <automated>cd frontend && (lsof -ti:3000 | xargs kill -9 2>/dev/null || true) && npx playwright test --project=mocked e2e/tests/ts-sse.spec.ts e2e/tests/ts-sse-resilience.spec.ts e2e/tests/ts-s.reconnect.spec.ts e2e/tests/ts-j.streaming.spec.ts e2e/tests/ts-chat.spec.ts e2e/tests/ts-chat-cards.spec.ts e2e/tests/ts-t.history.spec.ts e2e/tests/ts-u.revisions.spec.ts e2e/tests/ts-y.resilience.spec.ts e2e/tests/ts-y.run-scope-clarify.spec.ts 2>&1 | tail -40</automated>
  </verify>
  <done>All ten mocked transport specs pass against the real-wire mock (ts-sse, ts-sse-resilience, ts-s.reconnect, ts-j.streaming, ts-chat, ts-chat-cards, ts-t.history, ts-u.revisions, ts-y.resilience, ts-y.run-scope-clarify). No spec deleted / loosened / fixme'd. No file outside the four-file scope changed.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| backend SSE down-channel (`GET /api/runs/{id}/events/stream`) → FE `useRunStream` parser | Untrusted-length, chunked `text/event-stream` bytes cross into the client frame parser; a malformed / partial frame must not crash the reducer or advance the resume cursor incorrectly |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-wvm-01 | Denial of Service | useRunStream frame split (:341-350) — CRLF wire never boundary-matches → live stream permanently stalls (0 frames) | mitigate | Normalize `\r\n`→`\n` on decode so `\r\n\r\n` frames split; the on-close flush already backstops a trailing block |
| T-wvm-02 | Tampering | dispatchBlock JSON.parse of the `data:` line | mitigate | Keep the existing `catch { return; }` — a malformed envelope is discarded (WS-path parity), never dispatched; the tolerant branch only unwraps when `parsed.type` is a string |
| T-wvm-03 | Spoofing/Repudiation | seq resume cursor (Last-Event-ID) after the type moved into the envelope | mitigate | Cursor advance reads `data.seq` (inner payload) with the `id:` line as fallback — both preserved, so replay-from-cursor stays idempotent (dedup by event_id downstream) |
| T-wvm-SC | Tampering | npm installs | accept | No new dependencies; four-file frontend-only edit (parser + new unit test + e2e mock + one e2e spec) |
</threat_model>

<verification>
- `cd frontend && npx tsc --noEmit` clean.
- useRunStream.test.ts: (a) real single-frame envelope + (b) multi-frame are RED before Task 2, GREEN after; (c) legacy `\n\n`+`event:` green throughout; cursor advances under the envelope.
- Targeted vitest (useWorkflow.*, useRunChat, RunChatLane) stays green.
- Full mocked transport e2e (ts-sse, ts-sse-resilience, ts-s.reconnect, ts-j.streaming, ts-chat, ts-chat-cards, ts-t.history, ts-u.revisions, ts-y.*) green against the REAL wire.
- SC-001: no workflow-name literal in the fix, the mock, or the tests (keys on frame structure only).
- The 8 pre-Phase-42 vitest reds in UNTOUCHED files are NOT regressions.
- Live proof is the ORCHESTRATOR's: a fresh top-level prototype launch → clarify surfaces on the LIVE screen within ~30s (no reopen) → answer → build progress streams live (agent count increments, not "0/0") → review gate surfaces LIVE → approve → continues. If live streaming still fails for a top-level run after this fix, a separate live-binding bug exists — report it, do not silently pass.
</verification>

<success_criteria>
- useRunStream.ts:341 normalizes CRLF so `\r\n\r\n` backend frames split; the `indexOf("\n\n")` split is retained.
- dispatchBlock unwraps the real `{type,data}` envelope (type=parsed.type, data=parsed.data) AND still parses the legacy `event:`-line + flat-data shape (tolerant of both).
- The seq-cursor advance, keepalive skip, and `stream_attached{live:true}→setPhase("live")` are preserved.
- mockSse.ts emits the real `id: N\r\ndata: {"type":"<t>","data":{...}}\r\n\r\n` wire; ts-sse-resilience's inline `fetchSse` consumer parses it; all mocked transport e2e stay green.
- Exactly four files changed; branch stays feat/ui-2; no push; no commit trailer.
</success_criteria>

<output>
Create `.planning/quick/260716-wvm-fix-bug-014-b-repair-the-fe-sse-frame-pa/SUMMARY.md` when done.
</output>
