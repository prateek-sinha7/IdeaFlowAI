---
phase: quick-260719-m0o
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/app/agents/chat/concierge.py
  - backend/app/api/run_commands.py
  - backend/tests/agents/test_concierge_capability.py
  - backend/tests/unit/test_chat_messages_endpoint.py
autonomous: true
requirements: [QUICK-260719-m0o-BE]
must_haves:
  truths:
    - "converse yields ordered text deltas to a provided on_chunk callback and returns the full concatenated text"
    - "converse with on_chunk=None is byte-behaviorally identical to today (accumulate + return)"
    - "the fresh-Concierge POST streams chat_reply_chunk frames in order, then a terminal chat_reply carrying the full text"
    - "the durable chat_reply row and the drained proposal rows persist regardless of whether the client consumes the streamed body"
    - "every non-Concierge POST branch (plain / answers / gate / revision / confirm) still returns the same JSON contract"
  artifacts:
    - path: "backend/app/agents/chat/concierge.py"
      provides: "converse(ctx, user_message, on_chunk=None) streaming seam over runner.astream_events"
      contains: "on_chunk"
    - path: "backend/app/api/run_commands.py"
      provides: "fresh-Concierge branch returns an EventSourceResponse streaming chat_reply_chunk + terminal chat_reply"
      contains: "chat_reply_chunk"
  key_links:
    - from: "backend/app/api/run_commands.py"
      to: "backend/app/agents/chat/concierge.py"
      via: "converse(ctx, body.text, on_chunk=_on_chunk)"
      pattern: "converse\\(.*on_chunk"
    - from: "backend/app/agents/chat/concierge.py"
      to: "backend/app/agents/deep_agent_runner.py"
      via: "runner.astream_events(user_message)"
      pattern: "astream_events"
---

<objective>
Stream the Concierge chat reply on the run-screen left lane instead of delivering it as one blob — BACKEND half. Teach `converse` to emit ordered text deltas through an optional `on_chunk` callback (driven by the runner's existing `astream_events`), and change ONLY the fresh-Concierge branch of `POST /api/runs/{id}/messages` to stream those deltas to the client as `chat_reply_chunk` SSE frames followed by a terminal `chat_reply` — while keeping every durable side-effect (the `chat_reply` row + held proposal rows) exactly as today.

Purpose: the reply text must grow token-by-token in the chat bubble as it generates (matching how pipeline agent output already streams on the Steps tab), on BOTH live and completed runs, with zero change to the durable event contract that history/replay/BUG-017/the li0 spinner depend on.

Output: `converse` gains an `on_chunk` seam; the fresh-Concierge POST returns a streamed `text/event-stream` response; the durable `chat_reply` + proposal drain are preserved. FE consumption is Plan 02.

## Delivery decision (the crux) — Option B: stream the POST response body

Weighed A/B/C/D from the scope. **Chosen: (B) stream the `/messages` POST response itself** (as `text/event-stream`), NOT (A) register a live `_PIPELINE_QUEUES` entry for the turn. Verified reasons:

- **B sidesteps the completed-run queue lifecycle entirely.** The chunks ride the POST the FE already makes, so nothing is pushed to `_PIPELINE_QUEUES` and no completed-run SSE re-attach is needed. "what's the status" on a *completed* run (the common case, BUG-013: terminal runs don't auto-attach SSE) works via the same POST as a live run.
- **A's blast radius is real and sharp** (why it's the fallback, not the pick). Putting a settled run into `_PIPELINE_QUEUES` trips THREE membership consumers (verified this session):
  1. `resume_run_endpoint` overlap mutex — `run_commands.py:382` `if run_id in _PIPELINE_TASKS or run_id in _PIPELINE_QUEUES: → 409 pipeline_already_running`. Reachable for a **failed** run: a Concierge ask would register a queue and block a legitimate resume for the turn's duration.
  2. `stream_run_events` — `run_stream.py:281` `live_queue = _get_or_create_queue(id) if id in _PIPELINE_QUEUES else None` → the `stream_attached {live:true}` handshake would misreport a settled run as live to the FE connection state machine (`useRunStream.ts:276-279` `sawNonLiveAttachRef` / reconnect logic).
  3. **No cleanup owner** — `_cleanup_pipeline` is only called by a pipeline driver's `finally`; a Concierge-turn queue has no driver task, so a forgotten pop leaves the run "live" forever (resume permanently blocked, SSE always live).
  Option B touches NONE of these.
- **The durable record is unchanged either way.** `store.append_event_next_seq` only PERSISTS (it does not push to the live queue), so today's Concierge `chat_reply` already reaches the FE via the awaited POST + BUG-017 `fetchEvents`-after-send, never via a live drain. Option B keeps that durable persist verbatim and adds the transient streamed chunks in the POST body.
- **Proposals need no redesign.** The FE proposal surface is a `[]` stub (`RUN_CONCIERGE_PROPOSALS`, `DashboardLayout.tsx:185`) — the FE does not consume POST-body proposals today. So Option B preserves the server-side proposal drain/disposal verbatim; the terminal frame carries `proposals` for forward-compat only.

**Chunk persistence: TRANSIENT (not persisted).** The durable terminal `chat_reply` (full text) stays the single canonical record — history/reopen shows one clean turn. Chunks stream in the POST body only (never `append_event_next_seq`), so they are never replayed and can never double-count. This matches the scope's "terminal chat_reply remains canonical; chunks transient-on-replay" and is the cheapest option (no new rows).
</objective>

<execution_context>
Standing constraints (BINDING for every task in this plan):
- Branch **feat/ui-2**. Commit with the backend convention (`fix(...)/feat(...)`) — **NO trailers, NEVER push**.
- Python **python3.11**, **no venv**. Run backend commands with an **absolute** `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend` (cwd resets between calls).
- A live backend runs on **:8000** and Next on **:3000** — do **NOT** restart, bind, or touch them.
- **NO live Bedrock** in executors — the offline scripted-model path proves behavior; the orchestrator owns the live re-proof.
- Additive only — **no migration**, no new table, no new status.
- Re-verify every line anchor below before editing (line numbers drift).
</execution_context>

<context>
@.planning/CONCIERGE-STREAMING-SCOPE.md
@.planning/quick/260719-li0-concierge-chat-lane-show-a-typing-thinki/SUMMARY.md
@backend/CLAUDE.md
@backend/app/agents/chat/concierge.py
@backend/app/agents/deep_agent_runner.py
@backend/app/api/run_commands.py
@backend/app/api/run_stream.py
@backend/tests/agents/test_concierge_capability.py
@backend/tests/agents/_scripted_model.py
@backend/tests/unit/test_chat_messages_endpoint.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task BE-1: converse streams ordered deltas via astream_events + optional on_chunk (on_chunk=None preserves today)</name>
  <files>backend/app/agents/chat/concierge.py, backend/tests/agents/test_concierge_capability.py</files>
  <behavior>
    - With on_chunk=None: converse returns the scripted model's full text, byte-for-byte identical to today's `runner.run()` result (the proposal drain + ctx.proposals contract unchanged).
    - With an on_chunk callback: converse invokes it once per text delta, IN ORDER; the concatenation of the deltas equals the returned full text; more than one delta is observed (the scripted `_stream` yields multiple AIMessageChunks).
    - on_chunk works whether it is sync (returns None) or async (returns an awaitable) — converse awaits it iff awaitable.
  </behavior>
  <action>
    Replace the blocking `answer = await runner.run(user_message)` at concierge.py:295 with an inline drain of `runner.astream_events(user_message)` that mirrors `DeepAgentRunner.run()` (deep_agent_runner.py:807) EXACTLY for the on_chunk=None case: accumulate `full_output` from every event whose `type == "chunk"` (append `event["chunk"]`), ignore all other event types (`usage`/`tool_call`/`tool_result`/`done`/`gate`/`error`) for output purposes, and return the CHUNK-accumulated `full_output` (not the `done` event's output — run() returns the chunk join, so returning it keeps parity and avoids the done-event xml-sanitize divergence). Let exceptions propagate exactly as run() does (the runner already re-raises transient throttles at deep_agent_runner.py:603 and turns everything else into an `error` event that simply ends the loop with partial text — no new try/except here).

    Extend the method signature to `async def converse(self, ctx, user_message, on_chunk=None)`. For each chunk, if `on_chunk is not None`, call `on_chunk(delta)`; if the result is awaitable (`inspect.isawaitable(res)`), `await res` — so a sync test sink AND the async queue sink in BE-2 both work. `on_chunk` receives ONLY text deltas (no tool/usage events — the "state messages" stretch is explicitly out of scope for this task).

    Keep the per-request proposal capture untouched: `collected` / `_collecting_proposal_tools` / `ctx.proposals = collected` / `drain_proposals` all stay as-is (the tools append during the stream, exactly as before). The duck-typed port contract `converse(ctx, user_message) -> str` still holds because `on_chunk` is keyword-optional. Do NOT add a `converse_stream` method — converse IS the single seam (INV-12).

    Test: extend `test_converse_runs_scripted_model_through_runner_offline` (test_concierge_capability.py:240) to assert the on_chunk=None return equals the scripted full text (unchanged), and add a new `test_converse_streams_deltas_to_on_chunk_in_order` that passes a list-appending on_chunk and asserts `"".join(collected_deltas) == returned_text`, `len(collected_deltas) > 1`, and order preserved. Use the existing `ScriptedFakeChatModel` (tests/agents/_scripted_model.py) injected via `ctx.model` (its `_stream` yields multiple AIMessageChunks offline).
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend &amp;&amp; python3.11 -m pytest tests/agents/test_concierge_capability.py -q</automated>
  </verify>
  <done>converse yields ordered deltas to a provided on_chunk and returns the full concatenated text; on_chunk=None is byte-behaviorally identical to today; proposal drain unchanged; the concierge-capability suite is green. RED evidence recorded: with converse still on `runner.run()`, the new streams-in-order test fails (collected list empty).</done>
</task>

<task type="auto" tdd="true">
  <name>Task BE-2: stream the fresh-Concierge POST as EventSourceResponse (chat_reply_chunk + terminal chat_reply); durable row + proposals still land</name>
  <files>backend/app/api/run_commands.py, backend/tests/unit/test_chat_messages_endpoint.py</files>
  <behavior>
    - A fresh-Concierge POST (concierge=True, non-confirm) responds with content-type text/event-stream.
    - The streamed body carries the model's text deltas as `chat_reply_chunk` frames IN ORDER, then exactly one terminal `chat_reply` frame whose `data.text` is the full concatenated answer.
    - The durable `chat_reply` row (event_id `chat-reply:{message_id}`, seq present) is persisted, AND held proposals are drained/disposed, EVEN IF the client never reads the streamed body (durable side-effects run in a background task, not gated on client consumption).
    - The confirm branch and every non-Concierge channel (answers/gate/revision/steering/plain) return the SAME JSON contract as today (all existing endpoint tests stay green).
  </behavior>
  <action>
    In the fresh free-form Concierge branch of `post_message` (run_commands.py:1187-1230, the `elif dispatch.channel == CHANNEL_CONCIERGE:` path AFTER the `if body.confirm_proposal:` block), replace the blocking `answer = await concierge.converse(...)` + single `append_event_next_seq` + return-dict with an `EventSourceResponse` (import `from sse_starlette import EventSourceResponse`, the same class run_stream.py:283 uses) whose generator streams the turn:

    - Reuse the wire shape from `run_stream.py`: import/reuse `_sse_body` (the `{type, data}` single-line JSON body builder behind `_sse_frame`, run_stream.py:102) so streamed frames boundary-match the FE SSE reader's envelope. Each `chat_reply_chunk` frame = `_sse_frame(seq=0, "chat_reply_chunk", {"pipeline_run_id": run_id, "message_id": body.message_id, "delta": delta})` — carries NO real seq and NO event_id (transient: never persisted → never replayed → never deduped-away; the FE appends them). Do NOT invent a workflow/agent-name literal — `chat_reply_chunk` is a generic data type (INV-1/SC-001).
    - Build `frame_q: asyncio.Queue`. Define `async def _on_chunk(delta): await frame_q.put(<chat_reply_chunk frame>)`.
    - Define `async def _drive():` that: (1) `answer = await concierge.converse(ctx, body.text, on_chunk=_on_chunk)`; (2) persists the durable terminal EXACTLY as today — `await store.append_event_next_seq(run_id, event_id=f"chat-reply:{body.message_id}", type="chat_reply", payload_json={"pipeline_run_id": run_id, "message_id": body.message_id, "text": answer or ""})` capturing the returned seq; (3) drains + disposes proposals EXACTLY as today (`_drain_concierge_proposals(concierge, ctx)` → `_dispose_concierge_proposal(..., confirmed=False, ...)` loop → `held`); (4) `await frame_q.put(<terminal chat_reply frame carrying {pipeline_run_id, message_id, text: answer, seq, proposals: held}>)`. Wrap (1)-(4) so that on Exception it still puts a terminal `chat_reply` frame with the partial/empty text + an `"error"` marker AND still attempts the durable persist of whatever text was produced (history stays consistent). `finally: await frame_q.put(None)` (sentinel).
    - CRITICAL correctness pin: run `_drive()` as `asyncio.create_task(_drive())` so its durable side-effects (persist + proposal disposal) complete INDEPENDENTLY of client consumption. Do NOT cancel `_drive()` on generator teardown / client disconnect — the durable `chat_reply` + proposal rows must land even if the SSE body is dropped mid-stream. The response generator only drains `frame_q` (yield until the None sentinel).
    - Session safety: `store` here is ALREADY the session-less/owned `ScopedStore` built at run_commands.py:~975 AFTER `db.close()` — each `append_event_next_seq` opens+closes its own SessionLocal. So `_drive()` reuses `store` + `art_store` safely (same idiom as today's line 1209 persist); the BUG-004 request-session-teardown trap does NOT apply. Verify this before relying on it.
    - Return `EventSourceResponse(<generator>, headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})` (mirror run_stream.py:296). `post_message`'s return type widens to `dict | EventSourceResponse` (FastAPI honors a returned Response). Leave the `if body.confirm_proposal:` block and ALL other channel branches returning their JSON dicts UNCHANGED.

    Test: add to test_chat_messages_endpoint.py a fresh-Concierge streaming test. Monkeypatch `_resolve_concierge` with a fake capability whose `converse(ctx, text, on_chunk=None)` calls `await on_chunk("Hel"); await on_chunk("lo")` then returns `"Hello"` (and surfaces one proposal on ctx so `held` is non-empty). POST `{text, message_id, concierge: True}` on a settled run and assert: `resp.headers["content-type"]` startswith `text/event-stream`; the parsed streamed frames are `chat_reply_chunk("Hel")`, `chat_reply_chunk("lo")`, then a terminal `chat_reply` with `data.text == "Hello"` and a non-empty `proposals`; a follow-up owner-scoped events read shows a persisted `chat_reply` row (event_id `chat-reply:{message_id}`, seq present). Keep every existing endpoint test unchanged/green (assert one non-Concierge branch, e.g. `test_plain_running_turn_stays_steering` region, still returns JSON with `content-type: application/json`).
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend &amp;&amp; python3.11 -m pytest tests/unit/test_chat_messages_endpoint.py tests/unit/test_concierge_escalation.py tests/unit/test_concierge_proposal_channels.py -q</automated>
  </verify>
  <done>The fresh-Concierge POST streams ordered chat_reply_chunk frames then a terminal chat_reply; the durable chat_reply row + proposal rows persist regardless of client consumption; non-Concierge branches are unchanged JSON; the endpoint + escalation + proposal-channel suites are green. RED evidence recorded: before the change the response content-type is application/json and no chat_reply_chunk frames appear.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| run content → Concierge model | Untrusted run events/artifacts are surfaced to the model via owner-scoped read tools; unchanged by streaming. |
| Concierge output → streamed to client | The model's text now reaches the browser incrementally over the POST body instead of one durable event. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-m0o-01 | Information disclosure | streamed `chat_reply_chunk` frames | mitigate | The stream rides the SAME already-authenticated `POST /api/runs/{id}/messages` handler and its two-layer owner check (user_id ORM filter → 404, then default-deny `ScopedStore.get_run` → 404). No new endpoint, no new auth surface. |
| T-m0o-02 | Denial of service | `_drive()` background task / frame_q | accept | One task per Concierge turn on the existing single event loop, bounded by the model turn; the queue is drained by the same response. No unbounded fan-out; consistent with today's per-turn awaited converse. |
| T-m0o-03 | Tampering | proposal disposal moved into `_drive()` | mitigate | Proposal drain/disposal is byte-for-byte the existing `_dispose_concierge_proposal(..., confirmed=False, ...)` call (still HELD behind a confirm chip, never auto-executed); only its call-site moved into the background task. No change to the H1 server-enforced confirm-hold. |
| T-m0o-SC | Tampering | package installs | mitigate | NONE — no new dependency; `sse_starlette` (EventSourceResponse) is already imported by run_stream.py. |
</threat_model>

<verification>
Offline, from `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend` (python3.11, no venv, no live Bedrock):

1. `python3.11 -m pytest tests/agents/test_concierge_capability.py tests/unit/test_chat_messages_endpoint.py tests/unit/test_concierge_escalation.py tests/unit/test_concierge_proposal_channels.py -q` — all green (BE-1 + BE-2 behavior).
2. Goldens untouched (chat is NOT golden-covered per INV-3; assert anyway):
   `python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py -q` — the 5 characterization golden suites stay 10/10.
3. Import-linter contracts intact: `/opt/homebrew/bin/lint-imports` — 4 kept / 0 broken (concierge stays app-side; no new kernel edge).
4. Banned-pattern gate: `python3.11 -m pytest tests/agents/test_banned_patterns.py -q` — the model is still reached ONLY through DeepAgentRunner (INV-13); no new deepagents import.
</verification>

<success_criteria>
- `converse(ctx, user_message, on_chunk=None)` returns the full text unchanged; with an on_chunk it emits ordered deltas whose join equals the return value.
- The fresh-Concierge POST returns `text/event-stream`, streaming `chat_reply_chunk` frames then a terminal `chat_reply`; every other branch returns its unchanged JSON.
- The durable `chat_reply` row and held proposal rows persist even if the client never reads the body.
- No `_PIPELINE_QUEUES` touch, no migration, no new table, no new status.
- Goldens 10/10, lint-imports 4/0, banned-pattern gate green.
</success_criteria>

<output>
Create `.planning/quick/260719-m0o-stream-the-concierge-reply-converse-astr/01-SUMMARY.md` when done. Record: the exact converse loop change, the EventSourceResponse generator structure, the RED evidence for both tasks, and confirmation that goldens/lint/banned-pattern gates held.
</output>
