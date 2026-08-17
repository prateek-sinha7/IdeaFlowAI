---
phase: quick-260812-ppu
status: complete
date: 2026-08-12
commit: 88521920
branch: bugfix/spec-revision-context-loss
baseline_sha: 9e3dc9b0
closes: [ISS-121]
files: [FIX-240, TEST-024]
files_filed: [ISS-123, ISS-124, ISS-125, ISS-126]
pushed: false
---

# quick-260812-ppu — the engine event the chat lane destroyed (FIX-240 / TEST-024)

## Outcome

`ISS-121` is **FIXED**, and its stated root cause was **wrong and is corrected in place**.

The row read *"`pipeline_cancelled` is NEVER WRITTEN to the durable `run_events` log … the fix is
to make the reopen path consult `GET /api/runs/{id}`"*. Every **measurement** in that row is
correct; the causal claim built on top of them is not.

`pipeline_cancelled` is written by all eight engine terminal emitters. On run `808612bf` the
INSERT was **attempted, rejected by `uq_run_events_scope_seq`, and silently swallowed**. Two
writers shared one per-run `seq` space with two different algorithms:

| Writer | Allocator | On a `(run_id, …, seq)` collision |
|---|---|---|
| chat lane — `ScopedStore.append_event_next_seq` | `max(seq)+1` | **retries** past the new tail |
| engine — `_RunEventSink.persist` | fixed in-memory counter | **discarded the event** (warning only) |

`persist` caught `SQLAlchemyError`; `IntegrityError` is one; so a production seq collision took
the branch written for *"the offline harness has no schema"* and was indistinguishable from it in
the logs. `authz.py:462-465` documented this as an accepted trade-off and called the collision
**"rare"** — it fires on **every chat turn during a live run**, and the victim is whatever the
engine emits next. At a gate the engine is idle, so the victim is deterministically the terminal
frame, which is exactly why the symptom looked like "cancelled is never persisted".

**The fingerprint.** The log does not end at `review_gate_ready` (seq 278). Seq 279 is a narrator
card, 280 the user's `chat_message`, and **281 a narrator card reading "Cancelled by you"** —
projected from the very event whose row is missing, because the narrator projects from the *live*
event while only the DB write was rejected. A milestone card whose preceding row is a
`chat_message` is structurally impossible otherwise.

## What shipped

**(a) The root fix.** `ScopedStore.append_event_at_or_after` re-appends past the racing writer and
returns the seq the row actually landed on; `_RunEventSink.persist` returns it; **both** engine
drive loops (`execute()` and `_drive_resumed_stream`) re-stamp `data["seq"]` and advance the
allocator past it, reusing the idiom already at `engine.py:1078-1079`.

The re-stamp is **mandatory, not cosmetic**: `run_stream.py:198` renders the SSE `id:` cursor from
`row.seq` on replay and `:264` from `data["seq"]` live, so retrying without re-stamping would
corrupt `Last-Event-ID` resumption — a worse bug than the original.

**(b) Data repair only.** The D-14g SSE gate re-arm consults the persisted `WorkflowRun.status`,
reusing the exported `TERMINAL_STATUSES`. `gate_pendency` stays pure (import-linter forbids
`agents.capabilities` importing `app.*`). **No synthetic event is back-filled.**

## Decisions worth keeping

- **Rejected: allocate through `append_event_next_seq` per engine event.** It calls
  `read_events(run_id, after_seq=0)` — the whole log, per write — and the corpus holds a 26k-row
  and a 36k-row run. Replaced with a `func.max` probe over `uq_run_events_scope_seq` that runs
  only on a rejection.
- **The retry discriminator was measured, not reasoned.** A rejection is retried only when the
  measured tail actually reaches the attempted seq. This matters because the characterization
  harness's persist failure was captured directly and is an `IntegrityError` **FOREIGN KEY**
  violation (the `workflow_runs` parent row is absent) — **not** the `OperationalError` the
  degrade branch's own comment implies. A naive "retry on IntegrityError" would have burned 8
  attempts per event across every golden *and* re-stamped `data["seq"]`.
- **The claimed INV-3 hazard is refuted; the real one is `assert_seq_contiguous`.** Goldens
  snapshot the *yielded* stream and deliverable bytes, run with no DB, strip `seq`/`event_id`, and
  contain zero `review_gate_ready` / zero `pipeline_cancelled` (`gate_agent_ids=[]`). Row is not
  frame. The live constraint is `_normalize.py:297-320`, which pins `data["seq"]` DELTAS at
  exactly 1 on the **raw** pre-normalize stream — safe under retry-and-re-stamp, unsafe under any
  pre-allocate or reserve-gaps design.
- **`run_commands.py:1257` deliberately left alone.** It is already fenced by KAN-100 through
  `route_chat_turn`'s `dispatch.fenced`; a second guard there would be the duplication this fix
  exists to remove.

## Verification

3 new backend unit tests, **all seen RED at `9e3dc9b0`**, all asserting the durable **ROW** rather
than the yielded frame — the live stream is intact on every path, which is why ISS-091's three
offline probes could not have seen this.

The first RED surfaces as a `PendingRollbackError` (the rejected flush poisons the shared test
session) naming `UNIQUE constraint failed: run_events.run_id, run_events.owner_id,
run_events.workspace_id, run_events.seq`. Because that is not the assertion firing, each test was
**additionally** proven to discriminate by mutating the shipped code:

- retry disabled → `the engine's terminal event was silently DROPPED by the seq collision`, and
  `assert 'pipeline_cancelled' in {'agent_chunk': 3, 'chat_message': 2, 'review_gate_ready': 1}`
  (also the direct evidence that **exactly one** event dies per collision).
- terminal guard removed → `a terminal run must NOT re-arm a dangling gate`.

Both mutations reverted; reverted state re-verified (`55 passed`).

| Gate | At `9e3dc9b0` | At `88521920` |
|---|---|---|
| characterization goldens | 10 passed | **10 passed**, 0 golden files moved |
| `lint-imports` (from `backend/`) | 4 kept / 0 broken | **4 kept / 0 broken** |
| 9-file pre-existing-red sweep | 22 failed / 176 passed | **22 failed / 176 passed, identical ID set** |
| `test_run_events.py` | 10 passed | **12 passed** |
| `test_sse_stream.py` | 42 passed | **43 passed** |
| `test_restart_resume.py` + `test_resumability.py` | green | **green** |
| frontend | — | **0 files changed** |

Baselines were re-measured in a **detached worktree** at `9e3dc9b0`, never a stash.
`test_mechanical_router.py`'s 3 reds — absent from the briefed pre-existing list — were verified
pre-existing by the same method. FIX-232 is untouched.

No run launched, resumed or gate-approved; no Bedrock token spent.

## Filed, not folded

| ID | What |
|---|---|
| ISS-123 | Up to **29 already-destroyed engine events across 10 runs**; not retroactively recoverable, and back-filling synthetic rows was considered and rejected. |
| ISS-124 | `run_commands.py:2435` / `:2666` synthesise a terminal frame with no `seq`, no `event_id` and no durable row at all — same symptom, different cause, bypasses the engine entirely. |
| ISS-125 | `_stamp_resume_marker` (`engine.py:6309-6311`) still reads the entire log to derive one integer and appends at a fixed seq through the non-retrying primitive. |
| ISS-126 | Part (b) covers only the **cursored** reattach. A fresh reopen sends no `Last-Event-ID`, so on already-corrupted runs the symptom comes from the durable replay itself and needs an FE-side fix. |
