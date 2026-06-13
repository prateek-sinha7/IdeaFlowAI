---
phase: 16-terminal-state-integrity-and-reconnect-frame-contract
plan: 03
subsystem: api
tags: [websocket, reconnect, replay, revision, frame-contract, owner-scoping]

# Dependency graph
requires:
  - phase: 16-02
    provides: cooperative cancel websocket.py edits (read current state, not reverted)
  - phase: 14
    provides: WR-03 live-attach _reattach_section (the contract this plan mirrors onto the replay branch) + WR-06 alias transform (the inverse used here)
provides:
  - "Durable-replay revision frames carry the real section via the WR-06 inverse (matching live-attach); non-revision replay stays section:None (byte-identical)"
  - "The live-attach pipeline_reconnected ack carries live:true (symmetric with the no-live-task live:false ack)"
  - "Handler-driven cluster-B contract tests (mirror of the WR-03 live-attach test onto the replay branch)"
affects: [frontend reconnect/revision routing, future reconnect-contract work]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Replay-branch section derived ONCE before the loop from the owner-scoped run row type (no per-event DB round-trip)"
    - "WR-06 inverse alias transform (removesuffix('_revision') + _output) reused — generic run_type suffix, never a workflow-name literal (SC-001)"

key-files:
  created: []
  modified:
    - backend/app/api/websocket.py
    - backend/tests/agents/test_ws_reconnect_replay.py

key-decisions:
  - "Derived _replay_section from an owner-scoped WorkflowRun.type lookup added to the SAME _ws_db session that recovers the workspace (RunEvent.type is the EVENT type, not the run type — so _run_evt_row could not be reused for the section); no new/unscoped DB session (T-16-03-TENANT preserved)"
  - "Cluster-B tests drive the REAL websocket_chat handler via a scripted-loop FakeWebSocket (mirror of the WR-03 live-attach harness) so they pin the actual emitted frames, not just the ScopedStore read contract"

patterns-established:
  - "Reconnect replay frames re-derive presentation-only fields (section) from the owner-scoped run row, matching the live-attach drainer — section is never persisted"

requirements-completed: [ISS-008, ISS-009]

# Metrics
duration: ~12min
completed: 2026-06-13
---

# Phase 16 Plan 03: Reconnect Frame-Contract (ISS-008 + ISS-009) Summary

**Durable-replay revision frames now carry the real `section` via the WR-06 inverse (matching live-attach) and the live-attach `pipeline_reconnected` ack carries `live:true` — closing cluster B in `websocket.py`.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-13T13:07:00Z
- **Completed:** 2026-06-13T13:19:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- ISS-008: the durable-replay loop derives `_replay_section` ONCE before the `for _r in _missed:` loop from the owner-scoped run row's `type` via the WR-06 inverse (`f"{run_type.removesuffix('_revision')}_output"` when `*_revision`, else `None`) and applies it at the replay `send_json` (was hardcoded `section:None`). A `*_revision` reconnect now stamps `section == "<base>_output"` exactly like the live-attach drainer; a non-revision run stays `section:None` (byte-identical).
- ISS-009: the live-attach `pipeline_reconnected` ack carries `"live": True`, symmetric with the no-live-task `live: False` ack. The FE keeps its tolerant `live !== false` guard.
- Cluster-B contract tests drive the real `websocket_chat` handler end-to-end (mirror of the WR-03 live-attach test onto the replay branch): revision-replay `section` + non-revision `section is None` control + live:true/false ack assertions.

## Task Commits

Each task was committed atomically:

1. **Task 1: Derive `_replay_section` in the replay branch + add `live:true` to the live-attach ack** - `3cd8e785` (fix)
2. **Task 2: Revision-replay section assertion + live:true/false ack assertion (mirror WR-03 contract)** - `28be4693` (test)

_TDD note: the production fix (Task 1) and the pinning tests (Task 2) were split per the plan's two-task structure; both verified GREEN against the existing replay suite and the new handler-driven tests._

## Files Created/Modified
- `backend/app/api/websocket.py` - replay branch derives `_replay_section` from the owner-scoped run-row type (WR-06 inverse) and applies it at the replay send (was `section:None`); live-attach ack gains `"live": True`.
- `backend/tests/agents/test_ws_reconnect_replay.py` - adds a scripted-loop handler harness + 3 cluster-B tests (revision-replay section, non-revision section:None control, live:true/false acks).

## Decisions Made
- **Run-type source:** `RunEvent.type` is the EVENT type (e.g. `agent_chunk`), NOT the WorkflowRun `type`, so `_run_evt_row.type` could not feed the section derivation. Instead an owner-scoped `WorkflowRun.type` lookup (`owner_id == user.id`) was added to the SAME `_ws_db` session block that already recovers the workspace — no new/unscoped DB session, preserving the T-16-03-TENANT owner-scoping (a cross-owner reconnect resolves ∅ → `_replay_section` stays `None`).
- **Handler-driven tests:** the existing replay tests exercised only the `ScopedStore` read contract; the new cluster-B tests drive the real `websocket_chat` handler (scripted-loop FakeWebSocket, the WR-03 idiom: `_get_db` + `app.models.database.SessionLocal` both wired to the in-memory test DB) so the assertions pin the actual emitted frames.

## Deviations from Plan

None - plan executed exactly as written. The plan anticipated that the run row "is already loaded" via `_run_evt_row`/`get_run`; in practice `RunEvent.type` is the event type, so an owner-scoped `WorkflowRun.type` lookup was added in the same already-open `_ws_db` session (still no second DB round-trip per event, still owner-scoped) — consistent with the plan's intent (derive once, before the loop, owner-scoped) rather than a deviation from it.

## Issues Encountered
- A first draft of the test seeding helper used `asyncio.get_event_loop().run_until_complete()` inside an async test (loop-already-running error); fixed by making `_seed_run_and_events` an `async` helper awaited within each test. Caught and resolved before any commit.

## User Setup Required
None - no external service configuration required.

## INV-3 Parity Proof
- 5 characterization goldens (prototype/od_prototype/prototype_revision/od_ppt/app_builder) + `test_banned_patterns` + `test_migration_ledger`: **44 passed, 7 skipped** (byte/event-identical, no SNAPSHOT_UPDATE) — run after both tasks.
- `/opt/homebrew/bin/lint-imports`: **4 kept / 0 broken**.
- Zero new tables/migrations (`git status --porcelain` showed only the two target files; `RunEvent` gains no `section` column).
- `tests/agents/test_ws_reconnect_replay.py`: **10 passed** (7 existing + 3 new cluster-B).
- SC-001: the `_replay_section` transform keys on the generic `run_type` `_revision` suffix (the same WR-06 inverse already at the gate-restore / live-attach sites); no workflow-name literal introduced (`grep -c "removesuffix('_revision')"` = 3).

## Next Phase Readiness
- This is the LAST plan of Phase 16 — all 4 plans (16-01 ISS-016, 16-04 ISS-017, 16-02 ISS-007/002, 16-03 ISS-008/009) are now executed.
- Phase 16 success criteria 4 + 5 are satisfied by this plan; SC1–SC3 by the earlier plans. Ready for phase verification.
- Deferred per convention: a live Bedrock re-check of the reconnect frame contract (next live pass — defer-live-verification convention).

## Self-Check: PASSED

- FOUND: backend/app/api/websocket.py
- FOUND: backend/tests/agents/test_ws_reconnect_replay.py
- FOUND: .planning/phases/16-terminal-state-integrity-and-reconnect-frame-contract/16-03-SUMMARY.md
- FOUND commit: 3cd8e785 (Task 1)
- FOUND commit: 28be4693 (Task 2)

---
*Phase: 16-terminal-state-integrity-and-reconnect-frame-contract*
*Completed: 2026-06-13*
