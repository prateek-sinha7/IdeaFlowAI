# BUG-014-B — grounded fix spec (FE SSE parser never parses ANY live frame → all live streaming dead)

> Frontend-only. Root cause runtime-proven by a deep-investigation agent + orchestrator spot-checks (raw-wire hexdump + source). **High-impact, app-wide:** repair the FE SSE frame parser. Executable spec for a `gsd-quick --validate`.

## The bug (VERIFIED — no live SSE frame is ever parsed)
The backend serves SSE via `sse-starlette==3.0.2` (`backend/requirements.txt`), whose default frame separator is **`\r\n`**, so the wire is `id: N\r\ndata: {...}\r\n\r\n` (orchestrator hexdump of a live stream: bytes `69 64 3a 20 31 0d 0a 64 61 74 61 3a` = `id: 1\r\ndata:`, frames separated by `\r\n\r\n`). The FE parser `frontend/src/hooks/useRunStream.ts:343` splits frames with `while ((idx = buf.indexOf("\n\n")) !== -1)` — an **LF-LF** boundary. `"\r\n\r\n".indexOf("\n\n") === -1` → the split loop NEVER runs → `dispatchBlock` is NEVER called for a held-open live stream (the trailing flush at `:350` only fires on close, which never happens live). **Result: ZERO live frames reach the reducer.** Runtime fail-before/pass-after (agent, instrumentation reverted): a temp `.replace(/\r/g,"")` flipped dispatch **0 → 9** frames instantly.

**Secondary defect (latent behind the primary):** even once frames split, `dispatchBlock` derives the event type from an `event:` line (`useRunStream.ts:224`/`:227`), but the backend emits NO `event:` line — it nests the envelope inside the `data:` JSON as `{"type": "...", "data": {...}}` (`backend/.../run_stream.py` `_sse_body`; confirmed on the wire: `data: {"data": {...}, "type": ...}`). So a boundary-only fix still yields `type=""` → `handleWebSocketMessage` gets `msg.type===""` → the `questionnaire_ready`/every case never fires. **Both defects must be fixed.**

## Why this explains everything the user hit
- Fresh top-level launch → 0 live frames → lane sits at "**Pipeline running · 0/0 · BUILDING**" (`isRunning` is set optimistically at launch, `useWorkflow.ts:60`) with no clarify, no gate, no progress, no working Stop.
- **Reopen works** because it replays durable events over **REST** (`getRunEvents` → flat `payload_json`, no line-parsing) straight through `handleWebSocketMessage` — bypassing the broken SSE parser.
- Runs still build (backend fine); the FE limps on optimistic launch state + REST reopen + `/api/runs` list polling.
- The "stream cancelled" the user saw = dev-only React-StrictMode double-mount (red herring).

## Regression: PRE-EXISTING, activated by the Phase 44 SSE cutover
The `\n\n` split + `event:`-line parse date to `0429faef` (Phase 29-07, 2026-07-08), shipped behind `NEXT_PUBLIC_SSE_TRANSPORT` (default OFF → WebSocket was the real transport, no line-parsing exercised). `f6ce1142` (44-06, 2026-07-15) removed the flag → SSE became the sole transport → activated the dormant bug ~1 day before this QA campaign. **Not introduced by this session's work** (r7d/dhr/j1u/etc.). The mock `frontend/e2e/mocks/mockSse.ts` encodes the parser's WRONG expectation (`event:` line, flat data, `\n\n`), so all mocked e2e pass while the live wire never parses — a false-green.

## The fix (repair the FE parser; the backend wire is correct — do NOT change it)
`frontend/src/hooks/useRunStream.ts`:
1. **CRLF-tolerant frame split.** Normalize line endings on decode so `\r\n\r\n` frames boundary-match. At `:341` change `buf += decoder.decode(value, { stream: true });` to also strip `\r`: `buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");` (targets only line-ending CRLF; JSON string data escapes newlines as `\n` literals, never raw `\r\n`, so payloads are untouched). Keep the `indexOf("\n\n")` split.
2. **Envelope-aware type/data.** In `dispatchBlock` (`:217-263`), after `JSON.parse` of the `data:` line, if the parsed object has a `type` field (the `{type, data}` envelope), use `type = parsed.type` and `data = parsed.data`; otherwise fall back to the existing `event:`-line `typeLine` + the parsed object as `data` (tolerant of both the real wire and the legacy/mock flat shape). Preserve seq-cursor advance, keepalive skip (`pipeline_heartbeat`/`pong`), and `stream_attached{live:true}→setPhase("live")`.

`frontend/e2e/mocks/mockSse.ts`: emit the **real wire** — `id: N\r\ndata: {"type":"<t>","data":{...}}\r\n\r\n` — so the mocked e2e exercise the true format (else this fix is unguarded and the e2e stay false-green). Update the mock's frame builder accordingly; the fixed parser must make the existing mocked SSE specs pass against the real format.

## Scope fences (STRICT)
- **Frontend only.** Files: `useRunStream.ts`, `mockSse.ts`, + tests. Do NOT change the backend SSE (`run_stream.py`/sse-starlette — the wire is correct), the reducer, `RunConnectionProvider.tsx` (BUG-013 focus), or the j1u/lb6/n2d/o6z/r7d/sml/uhe fixes.
- Keep the parser tolerant of BOTH wire shapes (real `\r\n\r\n`+envelope AND legacy `\n\n`+`event:`) so nothing else silently breaks.

## Constraints
- Branch **feat/ui-2**. NO trailer. NEVER push. FE cwd-sensitive (from `frontend/`; kill :3000 before mocked Playwright). SC-001: parser keys on frame structure, no workflow-name literal.
- **This is the core live-transport parser — run the FULL mocked SSE/streaming/chat/reconnect e2e + useRunStream unit suite; they MUST stay green** (ts-sse, ts-sse-resilience, ts-s.reconnect, ts-j.streaming, ts-chat, ts-chat-cards, ts-t.history, ts-u.revisions, ts-y; useRunStream/useWorkflow/RunChatLane vitest). The 8 pre-Phase-42 vitest reds in untouched files are NOT regressions.

## Verification (executor)
- `npx tsc --noEmit` clean.
- **Core RED→GREEN (new useRunStream unit test):** feed the parser the ACTUAL backend wire — a chunk `"id: 1\r\ndata: {\"type\":\"questionnaire_ready\",\"data\":{\"pipeline_run_id\":\"r\",\"questions\":[{\"question_id\":\"q1\",\"question_text\":\"Q?\"}]}}\r\n\r\n"` — and assert `onMessage` fires once with `{type:"questionnaire_ready", data:{...questions...}}`. RED before (0 calls / type===""), GREEN after. Add a second case for a multi-frame chunk (`\r\n\r\n`×2) → 2 dispatches, and a legacy `\n\n`+`event:` case → still parses (tolerance).
- **Mock parity:** update `mockSse.ts` to the real wire; the full mocked SSE/streaming/chat/reconnect e2e stay green (now testing the true format).
- Executor does NOT run live Bedrock. **Orchestrator live-proof (the acceptance):** fresh top-level prototype launch → clarify surfaces on the LIVE screen within ~30s (no reopen) → answer → build progress streams live → review gate surfaces LIVE → approve → continues; live agent progress increments (not "0/0").
