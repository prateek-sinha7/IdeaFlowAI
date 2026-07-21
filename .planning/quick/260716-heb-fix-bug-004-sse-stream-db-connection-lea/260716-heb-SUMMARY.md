---
phase: 260716-heb
plan: 01
subsystem: backend/api (SSE run-event transport) + db engine
tags: [bug-fix, sse, connection-pool, inv-3-parity, bug-004]
requires: [run_stream.py, agents/authz.py ScopedStore, app/models/database.py]
provides: [session-less SSE generator store, Postgres pool sizing, pool-leak regression]
affects: [app/api/run_stream.py, app/models/database.py, tests/unit/test_sse_stream.py]
tech-stack:
  added: []
  patterns: [session-less ScopedStore (owned=True per-read close), gated QueuePool sizing]
key-files:
  created:
    - backend/tests/unit/test_run_stream_pool_leak.py
  modified:
    - backend/app/api/run_stream.py
    - backend/app/models/database.py
    - backend/tests/unit/test_sse_stream.py
decisions:
  - "Generator uses a SEPARATE session-less ScopedStore; the request-session store stays for the two pre-stream owner checks (owner isolation byte-identical)."
  - "Pool sizing gated to the non-SQLite branch (SingletonThreadPool rejects max_overflow/pool_timeout) so the offline engine is byte-unchanged."
  - "test_sse_stream.py api fixture must redirect module SessionLocal onto the harness engine (prod shares one engine; the harness overrode only get_db)."
metrics:
  duration: ~7m
  completed: 2026-07-16
---

# Phase 260716-heb Plan 01: BUG-004 SSE Stream DB Connection Leak Summary

**One-liner:** Closed the per-stream DB connection leak on `/api/runs/{id}/events/stream` by backing the streaming generator with a session-less `ScopedStore` (opens+closes its own `SessionLocal` per read), plus explicit Postgres pool sizing — with zero SSE wire change (INV-3 parity green).

## What was built

- **PRIMARY leak fix** (`app/api/run_stream.py`): `stream_run_events` now constructs a second, **session-less** `ScopedStore` (`stream_store`, no `session=db`) and passes it into `_iter_sse_frames`. Each `read_events` inside the generator hits `_acquire`'s `owned=True` branch (`authz.py:95-99`) and its `finally: session.close()` (`authz.py:328-330`) returns the connection to the pool — nothing is held during the idle live-drain loop. The original request-session store is retained UNCHANGED for the two pre-stream owner checks (Layer-1 ORM filter + Layer-2 `get_run`), which run in request scope and return normally — owner isolation (IDOR→404) stays byte-identical.
- **SECONDARY pool sizing** (`app/models/database.py`): the non-SQLite (Postgres/prod) `create_engine` now gets `pool_size=20, max_overflow=40, pool_timeout=30, pool_recycle=1800` via a `_pool_kwargs` mapping gated on `_sqlite`; `pool_pre_ping=True` retained. The SQLite dev/offline engine is byte-unchanged (empty `_pool_kwargs`) because SingletonThreadPool rejects those kwargs.
- **Regression test** (`tests/unit/test_run_stream_pool_leak.py`): a QueuePool-backed offline regression with three tests — the mechanism (injected+closed session leaks, reclaimed only by gc), the fix idiom (session-less store returns its connection per read, no gc), and THE endpoint guard driving `stream_run_events` end-to-end through an in-process uvicorn server (the `/tmp/sse_pool_repro2.py` variant known to reproduce the FastAPI≥0.106 teardown-before-streaming ordering).

## Fail-before / pass-after evidence (Task 1 → Task 2)

- **RED (pre-fix tree, commit `e0e4c3e8`):** `test_stream_endpoint_returns_connections` FAILED — `AssertionError: SSE stream leaked 1 DB connection(s) ... assert 1 == 0`. The two mechanism/idiom tests passed. Observed leak count = **1** connection per stream, exactly as the grounded spec predicted.
- **GREEN (post-fix, commit `d418b5a1`):** all 3 pool-leak tests pass — the endpoint returns every checked-out connection to the pool without `gc.collect()`.

## Verification results (all from `backend/`, python3.11, no venv)

| Gate | Command | Result |
|------|---------|--------|
| Pool-leak regression | `pytest tests/unit/test_run_stream_pool_leak.py -q` | **3 passed** (leak closed, no gc) |
| INV-3 characterization | `pytest tests/agents/ -k characterization -q --continue-on-collection-errors` | **10 passed** |
| SSE wire-parity oracle | `pytest tests/agents/test_wire_parity.py -q` | **6 passed** |
| lint-imports | `/opt/homebrew/bin/lint-imports` | **4 kept / 0 broken** |
| DB import (sqlite dev URL) | `python3.11 -c "import app.models.database ..."` | clean import, `pool_pre_ping` retained |
| SSE endpoint suite (owner 404 + frame parity) | `pytest tests/unit/test_sse_stream.py -q` | **15 passed** (after harness fix) |

INV-3 parity is preserved: characterization (10) + wire_parity (6) stay green, proving the SSE frames, durable replay, `stream_attached` handshake, and D-14g gate re-arm are byte/event-identical. Only the store's session-acquisition mode changed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Redirected module `SessionLocal` in the `test_sse_stream.py` `api` fixture**
- **Found during:** Task 2 (after applying the run_stream.py fix)
- **Issue:** The PRIMARY fix makes the streaming generator use a session-less store, which opens `app.models.database.SessionLocal` per read. The existing `test_sse_stream.py::api` fixture overrode only `get_db` (onto an in-memory StaticPool engine) but left the module-level `SessionLocal` pointing at the real dev DB — so `test_last_event_id_header_resumes_from_cursor` (a full-endpoint TestClient test) regressed: the generator read the empty dev DB instead of the seeded rows (`assert '3' in ['2']`). In production `SessionLocal` and `get_db` share one engine, so this gap is a test-harness artifact my fix surfaced.
- **Fix:** Added `monkeypatch` to the `api` fixture and redirected `app.models.database.SessionLocal` onto the harness engine (`db_session.get_bind()`). Non-behavioral test-harness correctness; no production code affected.
- **Files modified:** `backend/tests/unit/test_sse_stream.py`
- **Commit:** `d418b5a1` (bundled with the Task 2 fix that necessitated it)
- **Scope note:** This touches a fourth file beyond the three declared. It is a test file (not a SAFE production sibling) and the edit is directly caused by the Task 2 fix; the strict scope fence's intent (no SAFE production-sibling edits) is preserved.

## Threat surface

No new security-relevant surface introduced. The owner-isolation path (T-heb-02) is byte-identical (request-session store still backs the Layer-1/Layer-2 checks); cross-owner/missing → 404 asserted green. No package installs (T-heb-SC accept).

## Known Stubs

None.

## Handoff (orchestrator — NOT executor scope)

The definitive LIVE proof requires a backend **restart** (the pool-sizing change needs a fresh engine; `--reload` alone won't re-create it). After restart: open many concurrent SSE streams, watch `engine.pool.checkedout()` stay near 0, and confirm a concurrent `submit_answers` returns 200. The executor did NOT run this live multi-stream Bedrock load test (per constraints).

## Commits

- `e0e4c3e8` — `test(tests): add failing SSE pool-leak regression for BUG-004` (Task 1, RED)
- `d418b5a1` — `fix(api): session-less ScopedStore for the SSE generator (BUG-004 leak)` (Task 2, GREEN + harness fix)
- `56deb5c4` — `fix(sandbox): right-size the Postgres connection pool (BUG-004 defense-in-depth)` (Task 3)

## Self-Check: PASSED

All created/modified files exist on disk; all three CODE commits (`e0e4c3e8`, `d418b5a1`, `56deb5c4`) are present in the git log. SUMMARY.md is intentionally left untracked (docs committed by the orchestrator, per plan constraints).
