# Quick 260719-m0o Plan 01 — Stream the Concierge reply (BACKEND) Summary

## One-liner
Taught `converse` an optional `on_chunk` streaming seam over the runner's
`astream_events`, and changed ONLY the fresh-Concierge branch of
`POST /api/runs/{id}/messages` to return an `EventSourceResponse` that streams
transient `chat_reply_chunk` deltas then a terminal durable `chat_reply` — while the
durable `chat_reply` row + held proposal rows land in a background task regardless of
client consumption. Two TDD tasks, RED captured for both, atomic commits
`42e92efd` (BE-1) + `ce67d00c` (BE-2) on `feat/ui-2`. FE consumption is Plan 02.

## Tasks

### BE-1 — `converse` streams ordered deltas via `astream_events` + optional `on_chunk`
`backend/app/agents/chat/concierge.py`

The blocking `answer = await runner.run(user_message)` (concierge.py:295) was replaced
with an inline drain of `runner.astream_events(user_message)` that mirrors
`DeepAgentRunner.run()` exactly for the `on_chunk=None` case. Signature widened to
`async def converse(self, ctx, user_message, on_chunk=None)`. Exact loop:

```python
full_output = ""
async for event in runner.astream_events(user_message):
    if event["type"] != "chunk":
        continue
    delta = event["chunk"]
    full_output += delta
    if on_chunk is not None:
        res = on_chunk(delta)
        if inspect.isawaitable(res):
            await res
answer = full_output
```

- `on_chunk=None` accumulates every `chunk` event and returns the join — byte-identical
  to today's `runner.run()` (all non-chunk events ignored for output; exceptions
  propagate identically — no new try/except).
- A supplied `on_chunk` receives ONLY ordered text deltas; awaited iff awaitable
  (`inspect.isawaitable`), so a sync sink AND the BE-2 async queue sink both work.
- Proposal capture (`collected` / `_collecting_proposal_tools` / `ctx.proposals`) is
  untouched. No `converse_stream` method added (INV-12 — converse is the single seam).
  Added `import inspect`.

### BE-2 — stream the fresh-Concierge POST as `EventSourceResponse`
`backend/app/api/run_commands.py`

The fresh free-form Concierge branch (the `elif dispatch.channel == CHANNEL_CONCIERGE:`
path after the `if body.confirm_proposal:` block) now returns an `EventSourceResponse`.
Generator/driver structure:

```python
frame_q: asyncio.Queue = asyncio.Queue()

async def _on_chunk(delta):
    await frame_q.put(_sse_frame(0, "chat_reply_chunk",
        {"pipeline_run_id": run_id, "message_id": body.message_id, "delta": delta}))

async def _drive():
    answer_text = ""; reply_seq = None; held = []; errored = False
    try:
        answer_text = await concierge.converse(ctx, body.text, on_chunk=_on_chunk) or ""
    except Exception:
        logger.exception(...); errored = True
    try:
        _created, reply_seq = await store.append_event_next_seq(
            run_id, event_id=f"chat-reply:{body.message_id}", type="chat_reply",
            payload_json={"pipeline_run_id": run_id, "message_id": body.message_id,
                          "text": answer_text or ""})
        for intent in _drain_concierge_proposals(concierge, ctx):
            held.append(await _dispose_concierge_proposal(intent, confirmed=False, ...))
    except Exception:
        logger.exception(...); errored = True
    finally:
        terminal = {"pipeline_run_id": run_id, "message_id": body.message_id,
                    "text": answer_text or "", "seq": reply_seq, "proposals": held}
        if errored: terminal["error"] = True
        await frame_q.put(_sse_frame(reply_seq or 0, "chat_reply", terminal))
        await frame_q.put(None)  # sentinel

drive_task = asyncio.create_task(_drive())
_CONCIERGE_STREAM_TASKS.add(drive_task)
drive_task.add_done_callback(_CONCIERGE_STREAM_TASKS.discard)

async def _stream_frames():
    while True:
        frame = await frame_q.get()
        if frame is None:
            return
        yield frame

return EventSourceResponse(_stream_frames(),
    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})
```

Correctness pins honored:
- Durable side-effects run in `asyncio.create_task(_drive())`, NOT cancelled on client
  disconnect — the `chat_reply` row + proposal drain/disposal land even if the streamed
  body is dropped. A module-level `_CONCIERGE_STREAM_TASKS` set holds a strong reference
  (discard-on-done) so the task is never GC'd. The generator only drains `frame_q` to the
  None sentinel. Because `_drive` puts the terminal frame + sentinel in its `finally`
  (after the durable writes), the durable rows are committed before the stream ends.
- `chat_reply_chunk` frames are TRANSIENT — streamed in the POST body only, NEVER
  `append_event_next_seq`. The terminal durable `chat_reply` stays the single canonical
  record. `chat_reply_chunk` is a generic data type — no workflow/agent-name literal
  (INV-1/SC-001). Model reached only via the runner inside `converse` (INV-13). No
  `_PIPELINE_QUEUES` touch, no migration, no new table/status.
- `store` here is the session-less/owned `ScopedStore` built after `db.close()`, so each
  `append_event_next_seq` opens+closes its own SessionLocal — the background task reuses
  `store`/`art_store` safely (BUG-004 request-session-teardown trap does not apply).
- The `if body.confirm_proposal:` block and every other channel branch (answers / gate /
  revision / steering / plain) return their UNCHANGED JSON dicts. `post_message` has no
  return annotation, so FastAPI honors the returned `EventSourceResponse` directly.

## RED evidence (both tasks)

**BE-1** — with `converse` still on `runner.run()` (signature accepted `on_chunk` but the
body ignored it), the two new tests failed with the collected-delta list EMPTY:
```
test_converse_streams_deltas_to_on_chunk_in_order:
    AssertionError: assert '' == 'Hello, world'
test_converse_awaits_async_on_chunk_sink:
    AssertionError: assert '' == 'abc'
```
After swapping to the `astream_events` drain: all 14 concierge-capability tests green
(the scripted 3-piece turn produced >1 delta, confirming one chunk per AIMessageChunk).

**BE-2** — the new streaming endpoint test run against the PRE-change (committed HEAD)
`run_commands.py` failed exactly as predicted — the response content-type was
`application/json`, no `chat_reply_chunk` frames:
```
test_fresh_concierge_post_streams_chunks_then_terminal_reply:
    assert resp.headers["content-type"].startswith("text/event-stream")
    AssertionError: assert False
      where False = ...('text/event-stream')
      where ... = 'application/json'.startswith
```
(RED captured by copying the new file aside, `git show HEAD:./...` into place, running the
test, then restoring — no `git stash`.) After the change: green.

## Verification results (all offline; live Bedrock re-proof owned by the orchestrator)

- `tests/agents/test_concierge_capability.py` — 14 passed (incl. parity + 2 new streaming
  tests + async-sink test).
- `tests/unit/test_chat_messages_endpoint.py` — 16 passed (2 new: streaming endpoint +
  non-Concierge-stays-JSON).
- `tests/unit/test_concierge_escalation.py` — 13 passed (pure router; unaffected).
- `tests/unit/test_concierge_proposal_channels.py` — 19 passed (reconciled 2 fresh-ask
  tests to the streamed body; `_FakeConcierge.converse` gained `on_chunk`).
- 5 characterization goldens (`SNAPSHOT_UPDATE` unset) — 10/10.
- `/opt/homebrew/bin/lint-imports` — 4 kept / 0 broken.
- `tests/agents/test_banned_patterns.py` — 11 passed (no new deepagents import; model via
  the runner only).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added `review_event_pending` to the `_SpyArtStore` test fake**
- **Found during:** BE-2 (running the required `test_concierge_proposal_channels.py` suite).
- **Issue:** 5 `TestGateDisposal::*` tests failed with
  `AttributeError: '_SpyArtStore' object has no attribute 'review_event_pending'`. Proven
  PRE-EXISTING at HEAD (42e92efd) — they fail identically before any BE-2 change. The
  IN-02 refactor made `_gate_is_pending` read the public `store.review_event_pending`
  accessor, but this test fake (which still has `_resume_events` + `arm()`) was never
  updated. Unrelated to streaming, but the plan requires this suite green.
- **Fix:** Added `review_event_pending(self, gate_key)` to `_SpyArtStore` mirroring the
  real `ArtifactStore.review_event_pending` byte-for-byte (armed-but-not-set event =
  pending). No test loosened; no production code touched.
- **Files modified:** `backend/tests/unit/test_concierge_proposal_channels.py`
- **Commit:** `ce67d00c`

**2. [Reconcile - Changed behavior] Updated two fresh-ask endpoint tests to the streamed contract**
- **Found during:** BE-2.
- **Issue:** `test_fresh_ask_projects_chat_reply` and
  `test_surfaced_consequential_proposal_is_held` read `resp.json()` on the fresh-Concierge
  POST — which now streams `text/event-stream`. This is the intended contract change, so
  the tests were reconciled (not loosened): they now parse the SSE frames and assert the
  terminal `chat_reply` text / held proposals, while KEEPING the durable-row assertions
  (`chat_reply` row count + text, `concierge_proposal` row). `_FakeConcierge.converse`
  gained an `on_chunk=None` param that streams the answer as a single delta.
- **Files modified:** `backend/tests/unit/test_concierge_proposal_channels.py`
- **Commit:** `ce67d00c`

## Commits
- `42e92efd` — feat(agents): add converse on_chunk streaming seam over astream_events
- `ce67d00c` — feat(engine): stream the fresh-Concierge POST as EventSourceResponse

## Not done (out of scope — Plan 02)
FE consumption of the streamed `chat_reply_chunk` frames (the run-screen left-lane
token-by-token render) is Plan 02 (wave 2), to run after the orchestrator live-verifies
this backend on Bedrock. This plan did NOT start the frontend and did NOT touch the live
:8000 / :3000 servers.

## Self-Check: PASSED
- `backend/app/agents/chat/concierge.py` — modified (converse `on_chunk` seam), FOUND.
- `backend/app/api/run_commands.py` — modified (EventSourceResponse branch +
  `_CONCIERGE_STREAM_TASKS`), FOUND.
- `backend/tests/agents/test_concierge_capability.py` — 2 new tests, FOUND.
- `backend/tests/unit/test_chat_messages_endpoint.py` — 2 new tests, FOUND.
- `backend/tests/unit/test_concierge_proposal_channels.py` — reconciled + fake fix, FOUND.
- Commit `42e92efd` — FOUND in `git log`.
- Commit `ce67d00c` — FOUND in `git log`.
