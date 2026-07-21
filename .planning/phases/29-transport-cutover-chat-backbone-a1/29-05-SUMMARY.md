---
phase: 29-transport-cutover-chat-backbone-a1
plan: 05
subsystem: transport / test-durability-gate
tags: [CHAT-07, SC-2, sse, attach-replay, durability, LOCK-B, test-only, offline]
requires: [29-01, 29-02, 29-03, 29-04]
provides:
  - "backend/tests/agents/test_attach_replay_matrix.py — the SSE attach/replay durability + resilience gate (7 scenarios, incl. the binding SC-2 proof)"
affects: []
tech-stack:
  added: []
  patterns:
    - "Combined offline harness: one StaticPool in-memory SQLite bound to BOTH the ScopedStore session AND ws._get_db (the read-only WS gate predicates), so the SSE down-channel and the REST up-channel observe the identical durable run_events log"
    - "SC-2 seam-level durable-resume proof: answer a paused gate over REAL POST /gate with NO active stream, script the engine continuation into run_events, then reattach via _iter_sse_frames and assert ordered replay + no re-arm"
    - "Reuse the 29-01 projection (_sse_projection) for ordering/dedup/projection-exact assertions rather than re-deriving; bind the terminal replay to the real assert_wire_parity for non-vacuity"
key-files:
  created:
    - backend/tests/agents/test_attach_replay_matrix.py
  modified: []
decisions:
  - "SC-2 proven at the SEAM level offline: the REST gate command lands on store.set_review_response (durable), the engine's continuation is scripted into run_events (no live Bedrock), and reattach replays it in order — the durable-resume property holds independent of the live engine loop"
  - "restart = fresh process/store: assert the artifact-store gate registry starts EMPTY, so the D-14g review_gate_ready re-arm is proven to derive purely from the owner-scoped durable log (ND-9), not surviving in-memory state"
metrics:
  duration: ~10 min
  tasks: 1
  files: 1
  tests_added: 12
  completed: 2026-07-08
---

# Phase 29 Plan 05: Attach/Replay Matrix (Transport Durability Gate) Summary

The seven-scenario SSE attach/replay matrix — a test-only, fully-offline durability + resilience gate that proves the browser-native reconnect/reopen transport is correct under every ordering of stream drop, command, and restart, including the binding phase **SC-2** case (a gate answered via REST while the stream is down resumes correctly on reattach).

## What was built

`backend/tests/agents/test_attach_replay_matrix.py` (12 tests across the 7 required scenarios), driving the REAL 29-02/03/04 endpoints:

| # | Scenario | Proof |
|---|----------|-------|
| 1 | **fresh** | Attach to a brand-new run (cursor 0) → full durable replay ascending, then `stream_attached{live:true}`, then the live queue drains to the terminal (`pipeline_complete`) and closes |
| 2 | **mid-stream** | Attach with `Last-Event-ID = k` → replay ONLY `seq > k`, no dupes (acked frames never re-sent); + an end-to-end HTTP proof over the real route |
| 3 | **live** | Attach to a running run → tail replay precedes the handshake; `stream_attached{live:true, replayed_through_seq}` |
| 4 | **terminal** | Attach to a completed run (no queue) → full replay, generator TERMINATES (a completing `_drive()` is the no-hang proof); + bound to the real `assert_wire_parity` projection for non-vacuity |
| 5 | **cross-owner → 404** | Attacker attach → 404 (IDOR → 404, never 403); missing run → 404 |
| 6 | **restart** | Fresh process/store (empty gate registry) → a `waiting_for_user` run re-emits `review_gate_ready` on attach (D-14g), read-only (no run_events mutation); a resolved gate does NOT re-arm |
| 7 | **gate-answer-while-stream-down (SC-2)** | No stream attached → real `POST /api/runs/{id}/gate` resolves the paused gate via `store.set_review_response` → engine continuation scripted into `run_events` → REATTACH replays the resolution + subsequent events IN ORDER with no re-arm; + a full fresh-reattach-from-zero variant |

Each replay assertion binds to the **29-01 projection normalization** (`_sse_projection`): frames are asserted contiguous (strictly-ascending seq), deduped (unique seq/event_id), ordered by seq, and **projection-exact** (each emitted body byte-identical to `run_event_to_sse_frame`). The terminal scenario additionally runs the real `assert_wire_parity` against a recorded WS frame sequence.

## Verification (offline, python3.11, no venv)

```
$ python3.11 -m pytest backend/tests/agents/test_attach_replay_matrix.py -x -q
12 passed, 1 warning in 0.45s
```

- 7 scenarios green (12 test cases). SC-2 (gate-answer-while-stream-down) and restart (`review_gate_ready` re-emit) explicitly proven.

```
$ cd backend && /opt/homebrew/bin/lint-imports
Contracts: 4 kept, 0 broken.
```

TestClient + scripted store only — no live Bedrock, no running uvicorn.

## LOCK-B confirmation (git diff --name-only)

```
backend/tests/agents/test_attach_replay_matrix.py      (+ this SUMMARY + STATE/ROADMAP planning docs)
```

- Only `test_attach_replay_matrix.py` changed. Grep for `websocket.py` / `websocket_handoff.py` / `useWebSocket.ts` / `run_stream.py` / `run_commands.py` in the diff → **absent** (LOCK-B OK: no production files in diff).
- Zero new tables, zero ratchet arms, zero ledger rows. Additive, test-only.

## Deviations from Plan

None — plan executed exactly as written. Task 1 (`tdd="true"`) is a test-only artifact proving already-built endpoints; the suite went green against the 29-02/03/04 production code with no production edits (no RED-requiring implementation gap, as expected for a durability-gate plan).

## DEFERRED-to-live

- **SC-2 engine continuation**: the durable resume is proven at the SEAM level offline — the REST gate command lands on `store.set_review_response` (real endpoint), and the resumed engine's follow-on `run_events` are scripted (no live Bedrock). The end-to-end paused-run → REST answer → live engine-resume → real persisted continuation is covered by the consolidated milestone-end live pass (D-24), consistent with 29-03/29-04 deferrals. Evidence: the seam (`set_review_response` recorded response + gate event set) is asserted here; the replay-order contract over the continued log is asserted here.

## Self-Check: PASSED

- `backend/tests/agents/test_attach_replay_matrix.py` — FOUND
- Commit `d9c94ce7` — FOUND (test suite)
