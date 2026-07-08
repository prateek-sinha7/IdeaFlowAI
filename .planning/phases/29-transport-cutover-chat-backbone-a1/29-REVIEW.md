---
phase: 29-transport-cutover-chat-backbone-a1
reviewed: 2026-07-08T00:00:00Z
depth: deep
files_reviewed: 6
files_reviewed_list:
  - backend/app/api/run_stream.py
  - backend/app/api/run_commands.py
  - backend/app/api/chat_router.py
  - backend/app/agents/chat_narrator.py
  - backend/agents/execution_engine/context.py
  - backend/agents/execution_engine/engine.py
  - backend/app/core/config.py
  - backend/app/main.py
findings:
  critical: 3
  warning: 3
  info: 2
  total: 8
status: issues_found
---

# Phase 29: Code Review Report — Transport Cutover + Chat Backbone

**Reviewed:** 2026-07-08
**Depth:** deep (cross-file trace: run_commands.py ↔ websocket.py duplicated closures; run_stream.py replay/re-arm logic; chat_router.py/chat_narrator.py wiring into engine.py/context.py)
**Files Reviewed:** 8 (6 new/modified production files + the 2 read-only-imported websocket.py sections used as the "must match" baseline for the sanctioned duplication)
**Status:** issues_found

This review is **advisory only** per the task brief — it does not block phase completion. Per the brief's explicit allow-list, the following are **not** flagged: `/ws/chat` being untouched, the sanctioned launch/revision driver duplication as a *pattern* (only genuine *divergences* within that duplication are flagged below), `RunConnectionProvider` not yet mounted, and deferred live-Bedrock verification.

## Summary

The additive SSE/REST transport surface is well-scoped and the owner/IDOR posture is consistently correct everywhere it was checked (two-layer `user_id` → `ScopedStore.get_run` default-deny, 404-never-403, on every new endpoint). The KAN-100 terminal fence and KAN-94 armed-gate ground truth are applied correctly and consistently between `run_commands.py` and `chat_router.py`.

Three concrete correctness bugs were found, all with reasonably high confidence and reproducibility:

1. **`run_stream.py`'s D-14g gate re-arm double-emits `review_gate_ready`** on the single most common real-world path (a fresh page load — no `Last-Event-ID` — while the run is paused at a gate), because the re-arm doesn't check whether the durable replay already covered it.
2. **The "sanctioned duplication" of the WS launch driver has silently regressed**: `run_commands.py::_drive_launch_to_queue` drops four event-type handlers (`agent_input`, `agent_thinking`, `tool_call`, `tool_result`) and the corresponding `current_agent` scaffold fields that `websocket.py::_run_pipeline_to_queue` has — so every run launched via the new `POST /api/runs` REST endpoint persists a `WorkflowRun.agent_outputs` history silently missing tool-call/thinking/input-prompt data (the live stream itself is unaffected; only the persisted history is degraded).
3. **No atomic seq allocation for the new `run_events` writers.** `_persist_chat_message` (and the not-yet-wired `persist_milestone_card`) compute `seq = max(existing) + 1` via a plain read-then-write with no DB lock, no unique constraint, and no serialization against the engine's own concurrent event sink for the same `run_id`. This introduces a genuine cross-writer race that didn't previously exist (the engine was the sole sequential writer per run before this phase), and can produce duplicate `seq` values that break the phase's own Last-Event-ID dedup/replay guarantee.

None of these are found in the `/ws/chat` path itself and none regress an existing characterization/wire-parity golden (those stay dormant/byte-identical, confirmed by the phase's own test runs) — they are new defects in the newly added code.

## Critical Issues

### CR-01: SSE gate re-arm double-emits `review_gate_ready` on a fresh/full-replay attach

**File:** `backend/app/api/run_stream.py:166-173` (see also `_dangling_review_gate`, `run_stream.py:109-123`)

**Issue:** The D-14g gate re-arm step re-emits the last still-open `review_gate_ready` **unconditionally**, without checking whether it was already delivered by the durable-replay loop two steps earlier in the same generator:

```python
# Step 1 (line ~145): rows = await store.read_events(run_id, after_seq=after_seq)
# for r in rows: yield _sse_frame(r.seq, r.type, r.payload_json)   # <-- already includes the gate row when after_seq < dangling.seq

# Step 3 (line ~170-173):
full_log = await store.read_events(run_id, after_seq=0)
dangling = _dangling_review_gate(full_log)
if dangling is not None:
    yield _sse_frame(dangling.seq, "review_gate_ready", dangling.payload_json)   # <-- re-emits it regardless
```

For **any** attach where the client's cursor (`after_seq`, from `Last-Event-ID` — 0 when absent, i.e. every first-ever page load) is **before** the open gate's `seq`, step 1's replay already yields that `review_gate_ready` row. Step 3 then yields the identical `(seq, type, payload)` frame a second time. The intended purpose of the re-arm (per its own docstring: "re-emits it — reads state; NEVER re-runs an agent... so a reload during a paused gate resumes correctly") only makes sense for the case where the client's cursor is **at or past** the gate's own seq (so step 1's `seq > after_seq` filter excludes it). That is exactly the only scenario the existing test (`TestGateRearm::test_paused_gate_reemits_review_gate_ready_on_attach`) exercises (`after_seq=3` == the gate's own seq); there is no test with `after_seq=0` (or `after_seq < gate_seq`) asserting the re-arm doesn't duplicate — `TestGateRearm::test_rearm_is_read_only` uses `after_seq=0` with exactly one `review_gate_ready` row and only asserts "no DB row was written," not "the frame wasn't duplicated," so the double-emission is untested and unnoticed.

**Impact:** Any client that opens/reloads a run's SSE stream while it is paused at a human-review gate (the single most common real trigger for opening this endpoint) receives the `review_gate_ready` frame **twice** in one response. A frontend gate handler that isn't defensively deduped (nothing in the wire contract requires the client to dedupe non-replay live frames by content) will double-render the gate modal / fire duplicate side effects.

**Fix:** Only re-arm when the durable replay in step 1 would **not** have already covered it:

```python
full_log = await store.read_events(run_id, after_seq=0)
dangling = _dangling_review_gate(full_log)
if dangling is not None and dangling.seq <= after_seq:
    yield _sse_frame(dangling.seq, "review_gate_ready", dangling.payload_json)
```
(Add a test with `after_seq=0` and an open gate asserting exactly one `review_gate_ready` frame total.)

---

### CR-02: REST launch driver silently drops 4 event-type handlers present in the WS original it "duplicates"

**File:** `backend/app/api/run_commands.py:799-983` (`_drive_launch_to_queue`), vs. the mirrored original `backend/app/api/websocket.py:2025-2283` (`_run_pipeline_to_queue`)

**Issue:** The module's own header explicitly claims this is "a sanctioned duplication of the WS `_run_pipeline_to_queue` closure body." Comparing them line-for-line:

- WS `agent_start` initializes `current_agent` with `"input_prompt": None, "context_sources": [], "tool_calls": [], "thinking_text": ""` (`websocket.py:2070-2078`). REST's `agent_start` (`run_commands.py:859-866`) omits all four keys.
- WS additionally handles `agent_input` (`websocket.py:2079-2081`), `agent_thinking` (`2082-2083`), `tool_call` (`2084-2090`), and `tool_result` (`2091-2095`) — populating `input_prompt`, `context_sources`, `thinking_text`, and `tool_calls` on `current_agent`.
- REST's `_drive_launch_to_queue` (`run_commands.py:857-896`) handles only `agent_start` / `agent_chunk` / `agent_complete` / `agent_error` / `pipeline_complete` / `pipeline_cancelled` — the four branches above are **entirely absent**.

**Impact:** The live event queue itself still carries every event untouched (`await event_queue.put({"type": update["type"], "data": update.get("data", {})})` is unconditional, so a live SSE/WS listener sees `tool_call`/`tool_result`/`agent_thinking`/`agent_input` in real time). But the **persisted** `WorkflowRun.agent_outputs` JSON blob (written at `run_commands.py:923-924`, consumed by the history/reopen Audit-tab view) is built from `agent_outputs_collector`, which is built from `current_agent` — so for **every run launched via the new `POST /api/runs` REST endpoint**, the persisted history permanently and silently lacks tool-call records, thinking text, the input prompt, and context sources for every agent. This is not covered by any existing test (`tests/unit/test_rest_run_launch.py` has zero references to `tool_call`/`agent_input`/`thinking_text`/`context_sources`), so it will ship undetected once the frontend is switched onto the REST launch path.

**Fix:** Port the four missing branches (and the four missing `current_agent` scaffold keys) verbatim from `websocket.py:2070-2095` into `run_commands.py::_drive_launch_to_queue`, exactly as the module's own stated duplication contract requires. (This is the concrete, actionable version of the plan's own "deferred de-dup follow-up" — until de-duped, the two copies must at least stay behaviorally identical.)

---

### CR-03: Unserialized `seq` allocation lets the new chat writers race the engine's own event sink (duplicate `seq`, duplicate idempotent rows)

**File:** `backend/app/api/run_commands.py:354-390` (`_persist_chat_message`); same pattern in `backend/app/agents/chat_narrator.py:234-268` (`persist_milestone_card`, not yet wired to a live caller but shares the identical bug)

**Issue:** Both functions implement idempotency and seq-assignment as **read-then-decide-then-write**, with no transactional/locking guard and no DB-level uniqueness backstop:

```python
event_id = _chat_event_id(body.message_id)
existing = await store.read_events(run_id, after_seq=0)       # read
for row in existing:
    if getattr(row, "event_id", None) == event_id:
        return False, ...                                     # decide (no-op)
next_seq = (max((int(getattr(r, "seq", 0) or 0) for r in existing), default=0)) + 1
...
await store.append_event(run_id, seq=next_seq, event_id=event_id, ...)   # write
```

`RunEvent` (`app/models/run_event.py`) has only a non-unique `Index("ix_run_events_run_seq", "run_id", "seq")` — no `UniqueConstraint` on `(run_id, seq)` nor on `(run_id, event_id)`. `ScopedStore.append_event`/`read_events` (`agents/authz.py:284-329`) do no locking (`SELECT ... FOR UPDATE` or equivalent) either.

Before this phase, `run_events` for a given `run_id` had exactly **one** writer: the engine's own sequential event sink (`_RunEventSink` / `_stamp_resume_marker`, which use the identical `max(seq)+1` pattern — safe there only because it is a single coroutine's sequential loop). This phase adds a **second, independent, concurrently-scheduled writer** for the same `run_id`: the `POST /{run_id}/messages` endpoint, which runs in a separate request-handling coroutine that executes **concurrently** with the run's own background `engine.execute()` task (e.g., a user sends a steering note at the moment the running agent's own `agent_complete`/gate event is being persisted). Two coroutines computing `next_seq` from a stale `existing` read before either commits will both succeed with **the same `seq`** for **different** rows (no DB error, since there's no unique constraint to catch it).

Independently, the exact same check-then-act shape means a **duplicate/retried `message_id`** submitted twice in quick succession (double-click, browser retry) can race past the "already exists" check on both requests before either commits, producing **two** `chat_message` rows for what the API contract (D-01, T-29-09-2, "a replayed `message_id` is a no-op") explicitly promises is idempotent.

**Impact:** A duplicate `seq` breaks the Last-Event-ID replay contract this phase is built around: `run_stream.py`'s replay filters `seq > after_seq`, so if two rows share a `seq` and a client's cursor lands on that value, one of the two rows can never be replayed again (permanently dropped on any future reconnect past that cursor). A duplicate `chat_message` row for one retried submission also directly violates the phase's own stated idempotency guarantee.

**Fix:** At minimum, add a DB-level `UniqueConstraint("run_id", "event_id")` on `run_events` so a racing duplicate insert fails loudly (409/500, recoverable via retry) instead of silently succeeding twice; for `seq`, either serialize allocation (e.g., `SELECT ... FOR UPDATE` on a per-run counter row, or a Postgres sequence/identity per run) or accept the race and have the reader re-derive the *effective* sequence purely from insertion order (e.g., a global identity/serial primary key) rather than trusting an app-computed `max+1`.

## Warnings

### WR-01: Steering-channel dispatch is a silent no-op with no caller-visible signal

**File:** `backend/app/api/run_commands.py:515-522`

**Issue:** When `route_chat_turn` returns `CHANNEL_STEERING` (the run is actively "running"), `post_message`'s handling is:

```python
elif dispatch.channel == CHANNEL_STEERING:
    # ... apply_steering is never called; only the durable chat_message row above is the record ...
    pass
```

This is a documented, intentional deferral (`DEF-29-09-1` in `deferred-items.md` / `29-09-SUMMARY.md`), not a silent regression — but the API response is indistinguishable from a fully-delivered command: `{"ok": true, "run_id": ..., "seq": ..., "persisted": true, "channel": "steering"}`. A caller has no way to tell "your steering note was durably recorded but NOT delivered to the live running agent" from "your steering note is now live." Given `context.py`'s own comment states delivery is only re-derived at `resume_run` (a backend-restart resume), a steering note sent to a run that is running and never restarts is never actually consumed by `_compose_context_message` in this shipped state.

**Fix:** Either surface a `delivered: false` / `note: "queued, live delivery pending engine-side wiring"` field in the response so the frontend/caller can differentiate, or (preferably) land the deferred engine-side drain before exposing `CHANNEL_STEERING` as a "successful" response shape to real users.

### WR-02: `chat_narrator`'s deep-link nonce registry is a global, unbounded, unpersisted, unscoped set

**File:** `backend/app/agents/chat_narrator.py:109-129`

**Issue:** `_ISSUED_NONCES: set[str] = set()` is a bare module-level global with three compounding problems once this module is wired into a live endpoint (Phase 31/32, per its own summary):

1. **No expiry / unbounded growth**: a nonce is only ever removed by being consumed. Any card a user never clicks (the common case for most milestone cards) leaves its nonce in the set for the lifetime of the process.
2. **Not persisted / not shared across workers or restarts**: unlike the durable `chat_reply` row itself, `_ISSUED_NONCES` lives only in this one process's memory. Any backend restart (a routine deploy) or any multi-worker deployment invalidates every previously-issued, still-unconsumed nonce — `consume_deep_link` cannot distinguish "never issued" from "issued by a different worker/before a restart," so a legitimate first-time click on an old-but-valid deep link silently fails (`False`) with no way to recover, even though the card and its target are still fully valid and present in `run_events`.
3. **No ownership binding**: `consume_deep_link(nonce)` takes no `run_id`/`owner_id` — it is a pure global-nonce check. This is fine only as long as every caller independently re-verifies ownership of `target` before trusting a `True` result; the module itself provides no such guarantee, so a future caller that trusts `consume_deep_link(nonce) == True` as "this resolves for this user" without an independent owner check would have a cross-tenant hole.

**Impact:** Currently this module is not called from any production endpoint (verified — only referenced from `tests/unit/test_chat_narrator.py`), so there is no live exposure today. This is flagged as forward-looking: it will ship as-is into Phase 31/32's wiring unless revisited before then.

**Fix:** Back the nonce state by something that survives restarts/works across workers (a DB column/table row alongside the `chat_reply` event, or at minimum a documented single-process assumption matching `ArtifactStore`'s explicit HITL precedent) and require/verify a `run_id` at consumption time rather than a bare global set.

### WR-03: Chat-turn-routed gate actions can never carry `edited_content`

**File:** `backend/app/api/run_commands.py:501-514`, contrast with the direct `POST /gate` endpoint at `run_commands.py:218-238`

**Issue:** `route_chat_turn`'s `Dispatch` / `ChatTurn` dataclasses (`chat_router.py`) never carry an `edited_content` field, so when a gate action is routed through `/messages` (`CHANNEL_GATE`), every call to `art_store.set_review_response(...)` omits `edited_content` entirely — whereas the dedicated `POST /{run_id}/gate` endpoint forwards `body.edited_content` on `approve`/`reject`. This is a quiet feature-parity gap between the two ways of resolving a gate (chat-turn vs. direct REST), not a security or data-loss issue.

**Fix:** Either thread an `edited_content` field through `ChatTurn`/`Dispatch` for parity, or explicitly document that gate edits are only supported via the dedicated `/gate` endpoint (not the chat surface) so this isn't rediscovered as a "missing feature" bug later.

## Info

### IN-01: `SSE_STREAM_IDLE_TIMEOUT_SECONDS` is declared but never read anywhere in the codebase

**File:** `backend/app/core/config.py:135`

**Issue:** `SSE_STREAM_IDLE_TIMEOUT_SECONDS: int = 300` is documented as "the idle-timeout floor MUST exceed the ping" for ops-configured ingress, but no code in this repo reads/validates/enforces it — it exists purely as documentation-by-variable-name. Harmless, but it's dead configuration that could drift silently out of sync with whatever the actual ingress config uses.

**Fix:** Either wire it into an actual runtime check (e.g., assert at startup that `SSE_KEEPALIVE_PING_SECONDS < SSE_STREAM_IDLE_TIMEOUT_SECONDS`) or move the value into ops documentation instead of `Settings`.

### IN-02: `_gate_is_pending` reaches into `store._resume_events`, a private attribute, from two separate call sites

**File:** `backend/app/api/run_commands.py:133-145` and its second call site at `run_commands.py:461`

**Issue:** Both `resolve_gate` and `post_message` read `store._resume_events.get(f"review:{gate_key}")` directly off `ArtifactStore`'s "private" (underscore-prefixed) attribute rather than through a public accessor. This mirrors an existing pattern elsewhere in the codebase, so it's consistent rather than novel, but it does mean `ArtifactStore`'s internal dict shape is now depended on from two additional call sites outside `agents/artifact_store/store.py`.

**Fix:** Consider exposing a small public `ArtifactStore.is_review_pending(gate_key) -> bool` helper so the KAN-94 "armed-but-unset" check has one owner instead of being re-implemented via a private-attribute reach from two REST call sites.

---

_Reviewed: 2026-07-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
