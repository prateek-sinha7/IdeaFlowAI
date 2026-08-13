---
phase: quick-260812-ppu
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/agents/authz.py
  - backend/agents/execution_engine/engine.py
  - backend/app/api/run_stream.py
  - backend/tests/unit/test_run_events.py
autonomous: true
requirements: [ISS-121]
must_haves:
  truths:
    - "A run_events row rejected by the (run_id, owner_id, workspace_id, seq) UNIQUE constraint is RE-APPENDED past the racing writer's tail, never discarded."
    - "The seq the row ACTUALLY landed on is re-stamped onto data['seq'] before the event is yielded, so row.seq and data['seq'] never diverge (the SSE Last-Event-ID cursor stays correct)."
    - "A rejection that is NOT a seq collision (FK violation — the offline characterization harness) still degrades to a warning and does NOT re-stamp, so assert_seq_contiguous keeps seeing deltas == 1."
    - "The D-14g SSE gate re-arm never re-arms a review gate on a run whose persisted WorkflowRun.status is terminal."
    - "agents/capabilities/gate_pendency.py stays PURE — no app.* import, no status check inside it (import-linter contract)."
    - "FIX-232's dispatch-loop terminal observation (engine.py:2546-2556) is untouched."
    - "Characterization goldens stay 10 passed and no golden file moves; lint-imports stays 4 kept / 0 broken."
  artifacts:
    - path: "backend/agents/authz.py"
      provides: "ScopedStore.append_event_at_or_after — retry-past-a-raced-seq allocation returning the seq actually used"
      contains: "async def append_event_at_or_after"
    - path: "backend/agents/execution_engine/engine.py"
      provides: "_RunEventSink.persist returns the actual seq; both drive loops re-stamp"
      contains: "actual_seq = await sink.persist("
    - path: "backend/app/api/run_stream.py"
      provides: "Terminal-status guard on the D-14g gate re-arm"
      contains: "run_is_terminal"
    - path: "backend/tests/unit/test_run_events.py"
      provides: "The RED proof — the engine sink's lost event, asserted as a ROW"
      contains: "test_engine_sink_survives_a_raced_seq_instead_of_losing_the_event"
  key_links:
    - from: "backend/agents/execution_engine/engine.py:_RunEventSink.persist"
      to: "backend/agents/authz.py:ScopedStore.append_event_at_or_after"
      via: "the sink delegates seq arbitration to the store"
      pattern: "append_event_at_or_after"
---

<objective>
Stop the engine's durable `run_events` sink silently destroying an event whose `seq` was taken
by a racing app-layer writer (ISS-121).

**Purpose:** Two writers allocate from ONE per-run `seq` space with TWO algorithms.
`ScopedStore.append_event_next_seq` (`authz.py:433-491`, the chat lane) allocates `max(seq)+1`
and **retries past `IntegrityError`**. The engine's `_RunEventSink.persist`
(`engine.py:429-453`) uses a fixed in-memory counter and **swallows the collision**: it catches
`SQLAlchemyError`, and `IntegrityError` is one, so a production seq collision takes the branch
written for "the offline harness has no schema" and is indistinguishable in the logs.
`authz.py:462-465` documents this as an accepted trade-off and calls the collision "rare". It is
not rare — it fires on **every chat turn during a live run**, and the victim is whatever the
engine emits next. At a gate the engine is idle, so the victim is deterministically the terminal
frame; `derive_open_gate` then reports an OPEN review gate on a cancelled run.
</objective>

## Root cause

| Writer | Allocator | On `(run_id, …, seq)` collision |
|---|---|---|
| app (`_persist_chat_message` → `authz.py:474`) | `max(seq)+1` | **retries** past the new tail |
| engine (`execute()` → `engine.py:1058/1065`) | fixed in-memory counter | **discards the event** (warning only) |

## Tasks

### 1 — `backend/agents/authz.py`
Add `ScopedStore.append_event_at_or_after(run_id, seq, event_id, type, payload_json)` next to
`append_event_next_seq`. It appends at `seq`, and on an `IntegrityError` re-derives the tail
via a bounded `MAX(seq)` index probe (`_max_event_seq`) and retries at `tail + 1`. When the
tail does **not** reach the attempted seq the rejection was not a seq collision (FK / event_id)
— re-raise immediately so the caller's degrade path handles it. Returns the seq actually used.
`append_event` itself is UNCHANGED (it must keep raising, because `append_event_next_seq`
depends on that). Correct the now-false "the loser is arbitrated by the constraint" note at
`:462-465`.

**Rejected:** calling `append_event_next_seq` per engine event — it materialises the whole log
per write and the corpus already holds a 36k-row run.

### 2 — `backend/agents/execution_engine/engine.py`
`_RunEventSink.persist` returns `int | None` (the seq actually used; `None` when unarmed or
degraded) and delegates to `append_event_at_or_after`. BOTH drive loops — `execute()` (~1058)
and the resume driver `_drive_resumed_stream` (~8529) — re-stamp `data["seq"]` and advance
`next_seq` past the actual seq, byte-for-byte the idiom already at `engine.py:1078-1079`.

**The re-stamp is mandatory, not cosmetic:** `run_stream.py:198` emits the SSE `id:` cursor from
`row.seq` on replay and `:264` from `data["seq"]` live. Divergence corrupts `Last-Event-ID`.

### 3 — `backend/app/api/run_stream.py`
Skip the D-14g gate re-arm when the run's persisted `WorkflowRun.status` is terminal. Reuses the
exported `chat_router.TERMINAL_STATUSES` frozenset (no third restatement). Data repair only —
already-lost rows are not retroactively recoverable and **no synthetic event is back-filled**.
`gate_pendency` stays pure (import-linter forbids `agents.capabilities` importing `app.*`).

### 4 — `backend/tests/unit/test_run_events.py`
Add the missing half of the existing pair. `test_append_event_next_seq_retries_past_a_raced_seq`
(`:285-322`) proves only that the chat writer WINS; nothing asks what happened to the loser.
That gap is why this shipped. The new test asserts the **ROW** exists (not that the frame was
yielded — the distinction three offline probes missed) and that `derive_open_gate(rows)` is
`(None, None)` for the cancelled run.

## Verification

| Gate | Baseline at 9e3dc9b0 | Must hold |
|---|---|---|
| characterization goldens | 10 passed | 10 passed, `git status` clean under `golden/` |
| `lint-imports` (from `backend/`) | 4 kept / 0 broken | unchanged |
| `tests/unit/test_run_events.py` | green | green + the new test |
| known pre-existing reds | see ISSUES-REGISTER | same failing IDs, same counts |

Money guard: every pytest run is prefixed
`env -u AWS_PROFILE -u AWS_REGION -u RUN_LIVE_BEDROCK ANTHROPIC_API_KEY=""`.
