---
phase: 29-transport-cutover-chat-backbone-a1
plan: 01
subsystem: transport / characterization-harness
tags: [CHAT-07, wire-parity, SSE, characterization, INV-3, LOCK-B]
requires:
  - "The 5 INV-3 characterization goldens + scripted harness (_drive)"
  - "characterization/_normalize.py (_VOLATILE_STRIP_KEYS + _canonical_order)"
provides:
  - "characterization/_sse_projection.py — the pure run_events->SSE projection contract 29-02 mounts"
  - "test_wire_parity.py — the CHAT-07 binding wire-parity gate (offline, non-vacuous)"
  - "5 *.wsframes.json goldens — the recorded volatile-stripped WS frame sequences"
affects:
  - "29-02 (SSE stream endpoint) imports the projection; 29-03/29-04 cite the gate as their exit contract"
tech-stack:
  added: []
  patterns:
    - "run_events->SSE projection as a pure, app/kernel-free test-support module (import-linter 4/0)"
    - "order-canonical multiset parity (reuses the characterization normalizer, never copies the strip list)"
    - "non-vacuity via injected drift (extra key / changed type / empty projection) — mirrors assert_seq_contiguous"
key-files:
  created:
    - backend/tests/agents/characterization/_sse_projection.py
    - backend/tests/agents/test_wire_parity.py
    - backend/tests/agents/characterization/golden/prototype.wsframes.json
    - backend/tests/agents/characterization/golden/od_prototype.wsframes.json
    - backend/tests/agents/characterization/golden/od_ppt.wsframes.json
    - backend/tests/agents/characterization/golden/prototype_revision.wsframes.json
    - backend/tests/agents/characterization/golden/app_builder.wsframes.json
  modified: []
decisions:
  - "Parity is on the {type,data} payload core (the FE reducer contract); chunk (always None) + section (transport envelope) are excluded from the compare so the SSE endpoint sets its own envelope."
  - "run_events rows derived from the yielded engine event stream (payload == event.data, seq embedded) — the durable RunEvent.payload_json is that same dict; avoids a live DB (offline, LOCK-B)."
  - "Goldens recorded as volatile-stripped, order-canonical WS frame sequences via SNAPSHOT_UPDATE, mirroring the existing characterization event-golden convention."
metrics:
  duration: "~25 min"
  completed: "2026-07-08"
  tasks: 3
  files: 7
---

# Phase 29 Plan 01: Wire-Parity Characterization Harness Summary

The CHAT-07 binding gate for the transport cutover: a pure `run_events`->SSE projection
(`_sse_projection.py`) proven to replay the recorded `/ws/chat` outbound frame sequences
identically (volatile-stripped, order-canonical) for the 5 golden pipelines, plus a
non-vacuity case that makes the comparator raise on injected drift — all offline via the
scripted harness, entirely additive under LOCK-B (test files only).

## What was built

- **`characterization/_sse_projection.py`** — the projection contract 29-02 mounts into the
  live SSE endpoint. Exports:
  - `ws_frame_from_engine_event(event, section)` — reproduces the live WS drainer 4-key
    wrapping `{type, chunk:None, section, data}` (`app/api/websocket.py:2325-2328`).
  - `run_events_from_engine_events(events)` — derives the durable `{seq, type, payload}`
    rows from a captured engine stream (payload == `event.data`, with `seq`/`event_id`
    embedded — exactly what `RunEvent.payload_json` persists).
  - `run_event_to_sse_frame(row)` — renders the SSE text form: an `id: {seq}` line (browser
    `Last-Event-ID` resume cursor) + a single `data: {json}` line ({type,data} body) + blank
    terminator.
  - `project_events(rows)` — yields SSE frames in ascending `seq`.
  - `assert_wire_parity(ws_frames, run_events)` — reduces both sides to their `{type,data}`
    core, normalizes through the SHARED `_VOLATILE_STRIP_KEYS` + `_canonical_order`, and
    raises on any residual drift (with an anti-vacuity guard on both sides).
  - Dependency-free of `app.*` / the `agents.*` kernel — imports ONLY the characterization
    normalizer, so import-linter stays 4 kept / 0 broken and the strip list is never copied.
- **5 `*.wsframes.json` goldens** — the recorded volatile-stripped, order-canonical WS frame
  sequences for `prototype` (45 frames), `od_prototype` (45), `od_ppt` (19),
  `prototype_revision` (13), `app_builder` (85). Chat-dormant by construction.
- **`test_wire_parity.py`** — parametrized 5-pipeline parity gate + 1 non-vacuity case
  (6 tests). Asserts each golden carries a `type`, contains no `chat_message`/`chat_reply`/
  `stream_attached` (INV-3), and that the fresh SSE projection matches the recorded golden.

## How it works (parity by construction)

The engine stamps a monotonic per-run `seq` + uuid `event_id` into every event's `data` at
the single `execute()` emit boundary; the WS drainer frame's `data` and the durable
`run_events.payload_json` are that SAME dict. So the SSE projection of `run_events` and the
WS frame for the same event carry identical payloads — parity is a real, deterministic
property (the scripted harness is fixed), proven as an order-canonical multiset (robust to
the engine's nondeterministic `tool_result`/`task_progress` interleaving, per the normalizer's
ORDERING NOTE). 29-02 mounts the same `_sse_projection.py`, so the live SSE stream inherits
the proof.

## Verification (actual offline output)

- `python3.11 -m pytest backend/tests/agents/test_wire_parity.py -x -q` → **6 passed** (5
  parity + 1 non-vacuity) in ~20s.
- `/opt/homebrew/bin/lint-imports` → **Contracts: 4 kept, 0 broken.**
- 5 `*.wsframes.json` goldens exist, parse, are non-empty, each frame has `{type,chunk,section,data}`,
  and none contains `chat_message`/`chat_reply`/`stream_attached`.
- INV-3 regression: the 5 existing `test_characterization_*.py` → **10 passed** (byte/event-
  identical, no `SNAPSHOT_UPDATE`, no golden regen).

## LOCK-B confirmation (`git diff --name-only HEAD~3 HEAD`)

```
backend/tests/agents/characterization/_sse_projection.py
backend/tests/agents/characterization/golden/app_builder.wsframes.json
backend/tests/agents/characterization/golden/od_ppt.wsframes.json
backend/tests/agents/characterization/golden/od_prototype.wsframes.json
backend/tests/agents/characterization/golden/prototype.wsframes.json
backend/tests/agents/characterization/golden/prototype_revision.wsframes.json
backend/tests/agents/test_wire_parity.py
```

- ALL changes are under `backend/tests/` — additive, test-only. **Zero production files touched.**
- `app/api/websocket.py`, `app/api/websocket_handoff.py`, `frontend/src/hooks/useWebSocket.ts`
  are **NOT** in the diff (explicitly checked).
- No `/ws/chat` handler deleted, no deletion grep-ratchet armed, no migration-ledger deletion
  row added, zero new DB tables. Import-linter 4 kept / 0 broken. INV-3 goldens untouched; no
  chat events in the new `*.wsframes.json` goldens.

## Deviations from Plan

None — plan executed exactly as written. The three tasks (projection module, goldens,
binding gate) landed in order, each committed atomically.

Note on the run_events source: the plan mentioned capturing rows "from the in-memory
ScopedStore". Offline, the `ScopedStore` durable-log write is best-effort and degrades (the
harness has no `workflow_runs` row → FK constraint, logged and swallowed by PERSIST-03). The
rows are therefore derived from the yielded engine event stream, whose `data` is exactly the
`payload_json` the sink would persist (`seq`/`event_id` embedded) — the faithful, DB-free
capture the plan's offline mandate requires. This is a design clarification, not a behavior
deviation.

## Commits

- `8aadb3b0` — test(29-01): add run_events->SSE projection + wire-parity contract (`_sse_projection.py`)
- `dd1c7078` — test(29-01): record 5 volatile-stripped WS frame goldens (`*.wsframes.json`)
- `1ee4fc9e` — test(29-01): add the CHAT-07 wire-parity binding gate (`test_wire_parity.py`)

## Deferred-to-live checks

None. The entire harness is offline-runnable via the scripted model — there is no server /
Bedrock / SSO dependency in this plan, so nothing is deferred to the live pass.

## Self-Check: PASSED

- Created files verified present on disk: `_sse_projection.py`, `test_wire_parity.py`, all 5
  `*.wsframes.json` goldens.
- Commits verified in `git log`: `8aadb3b0`, `dd1c7078`, `1ee4fc9e`.
