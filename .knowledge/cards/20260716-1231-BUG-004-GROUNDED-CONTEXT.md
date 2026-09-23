---
id: BUG-004-GROUNDED-CONTEXT
type: bug
kind: event
title: BUG-004 — SSE stream DB connection leak
status: done
applies_to:
  phases: []
  modules:
  - ScopedStore
  - agents
  - api
  - app
  - chat
  - dependencies
  - install
  - models
  - run_engine
  - run_stream
  globs:
  - .planning/SSE-QA-BUG-LOG.md
  - authz.py
  - /tmp/sse_pool_repro2.py
  - database.py
  - run_engine.py
  - run_stream.py
  - run_commands.py
  - backend/app/api/run_stream.py
  - backend/app/models/database.py
  - runs.py
  - prototype_templates.py
  - test_wire_parity.py
  requirements: []
locked_constraints:
- INV-3
- INV-13
verification:
  type: test
  status: passed
  test_files:
    - backend/tests/unit/test_run_stream_pool_leak.py
compact_summary: 'FastAPI tears down Depends(get_db) before the SSE generator body runs, so read_events opens a fresh pooled connection per stream that ScopedStore never closes, leaking one per live stream.'
last_updated: '2026-08-31'
author: 'Imran Yousaf <imrany@hexaware.com>'
author_source: applies-to-glob
---

<!-- RELATED -->

## Related

**Depends on:** [FIX-440](20260831-2002-FIX-440.md)

<!-- /RELATED -->

# BUG-004 — SSE stream DB connection leak (grounded fix spec)

> Backend fix for a **connection leak** on the SSE run-event endpoint, activated by the Phase-44 WS→SSE cutover (SSE became the sole run-event transport 2026-07-15). Root cause verified to file:line + empirically reproduced by an investigation agent. **Full root cause: `.planning/SSE-QA-BUG-LOG.md` → BUG-004 (read it first).** This file is the executable spec for a `gsd-quick --validate`.

## The bug (one paragraph)
`app/api/run_stream.py::stream_run_events` (the SSE down-channel, sole run-event transport since 44-07) declares `db: Session = Depends(get_db)` (`:208`), builds `store = ScopedStore(..., session=db)` (`:233-237`), and calls `store.read_events(...)` **inside** the streaming generator `_iter_sse_frames` (`:145` replay, `:178` gate re-arm). FastAPI ≥0.106 (installed 0.115.6) tears down `yield`-dependencies **before** the streaming body runs, so `get_db`'s `finally: db.close()` fires first; the generator's query then re-acquires a **fresh** QueuePool connection on the closed session, and `ScopedStore._acquire` sees `owned=False` (`authz.py:95-99`) → `read_events`'s `finally: if owned: session.close()` (`authz.py:328-330`) does NOT close it. **Each live SSE stream leaks 1 connection** (reclaimed only by GC — proven in `/tmp/sse_pool_repro2.py`: `checkedout` stays 1 through + after the stream, drops to 0 only on `gc.collect()`). Default pool `5+10=15` (`database.py:12`, no sizing) + EventSource reconnects/tabs → exhaustion → `submit_answers → _review_gate_owned_by` (`run_engine.py:344`) blocks 30s and 500s. **Checkpointer is NOT involved** (separate psycopg pool). **Only `run_stream.py` has this pattern** — the chat SSE (`run_commands.py:1819`, opens its own `_get_db()` + `finally close`) and non-streaming `ScopedStore(session=db)` sites (`runs.py:838/888`) are SAFE. The correct idiom is `post_message`'s (`run_commands.py:758` — `ScopedStore` with NO injected session).

## The fix (backend only)

### PRIMARY — remove the leak (the actual fix)
In `backend/app/api/run_stream.py`: the store consumed **inside** `_iter_sse_frames` must be constructed **without** the request session, so each `read_events` opens+closes its own `SessionLocal` (`authz.py:95-99` owned=True → `:328-330` closes) and nothing is held during the idle live-drain loop:
- Build the generator's store as `ScopedStore(owner_id=current_user.id, workspace_id=workflow_run.workspace_id)` (session **omitted / None**) instead of `session=db` (`:233-237`).
- Keep the request `db = Depends(get_db)` ONLY for the pre-stream Layer-1/Layer-2 owner checks (`:220`, `:239`) — those run in request scope and return normally.
- Mirror the safe pattern already used by `post_message` (`run_commands.py:758`) and the chat SSE. (A `try/finally: db.close()` wrapper is a WEAKER alternative — it still holds one connection idle for the whole stream; prefer the session-less store.)

### SECONDARY — right-size the pool (defense-in-depth; pre-existing config)
`backend/app/models/database.py:12` — add explicit sizing to `create_engine` (keeps `pool_pre_ping=True`), e.g. `pool_size=20, max_overflow=40, pool_timeout=30, pool_recycle=1800` (tune to expected concurrency). **Sizing alone does NOT fix the leak** — it only delays exhaustion; #1 is the real fix, #2 is warranted regardless for multi-run scale.

## Scope fences (STRICT)
- **Backend only.** Touch ONLY `backend/app/api/run_stream.py` (leak fix) + `backend/app/models/database.py` (pool sizing) + a new test. Do NOT touch the SAFE siblings (`run_commands.py` chat SSE / `post_message`, `runs.py`, `prototype_templates.py`) — they already use the correct idiom.
- **Do NOT change the SSE frame content / event vocabulary / ordering.** The fix changes only the store's session-acquisition mode; the events read (durable replay `:145`, gate re-arm `:178`) and the frames emitted must be **byte-identical** (INV-3 parity). The owner-scoped reads use the same `ScopedStore` — only its session mode changes.
- No engine/manifest/AGENT.md/golden edits. No migration (Q3 additive-only — n/a here). INV-13 (deepagents) not relevant.

## Constraints
- Branch **feat/ui-2** (NEVER main/staging). Worktrees OFF → sequential. **NO commit trailer** (no Co-Authored-By / Claude-Session). **NEVER push.**
- Runtime: **python3.11, no venv** (backend). Live uvicorn uses `--reload`.
- The backend is currently running (pid ~17295, Bedrock env); `--reload` will pick up the src change, but the pool-sizing change needs a **restart** to take effect (note this for the live check).

## Verification (executor scope)
- **INV-3 must stay green** (the fix must not alter the wire): from `backend/`, `python3.11 -m pytest tests/agents/ -k characterization -q --continue-on-collection-errors` → **10 passed**; and the SSE frame-parity oracle `python3.11 -m pytest tests/unit/test_wire_parity.py -q` → **6 passed**. Both must stay green (they prove the SSE frames are unchanged).
- **lint-imports** from `backend/`: `/opt/homebrew/bin/lint-imports` → 4 kept / 0 broken.
- **NEW regression test proving the leak is closed** (fail-before / pass-after). Two viable approaches — pick the one that runs offline reliably:
  - (a) **Behavioral (preferred if a sync SQLAlchemy engine can be stood up in-test):** drive `_iter_sse_frames` (or the endpoint) against a QueuePool-backed engine, assert `engine.pool.checkedout()` returns to baseline after the generator is exhausted **without** `gc.collect()` (fails before the fix — stays at 1; passes after — drops to 0). Reference repro: `/tmp/sse_pool_repro2.py` (rebuild if swept).
  - (b) **Structural/source-lock (always offline-safe):** assert `run_stream.py`'s generator store is constructed WITHOUT the request session (no `session=db` reaches `_iter_sse_frames`) — a source-scan test in the spirit of the existing SC-001 source-lock tests. Weaker but deterministic.
  - Prefer (a) if feasible; else (a)-as-a-narrow-unit with a fake/counting pool, plus (b) as a source-lock guard.
- **Offline-suite gotcha:** the FULL backend pytest hangs offline (Chromium/Bedrock/Postgres-gated) — do NOT run it; scope to the targeted suites above + the new test.
- **Do NOT run a live multi-stream Bedrock load test in the executor.** The definitive LIVE proof (open many SSE streams, watch `engine.pool.checkedout()` stay near 0, concurrent `submit_answers` returns 200) is the ORCHESTRATOR's post-fix pass after a backend restart.

## At-risk / no-regression
- The SSE endpoint's two owner checks (`:220`, `:239`) must STILL 404 cross-owner (owner isolation).
- Durable replay (`:145`) + D-14g gate re-arm (`:178`) must still deliver the same events. `test_wire_parity.py` + the characterization goldens are the oracle.

## Test-writer confirmation (2026-08-31)
- The PRIMARY (session-less generator store, `run_stream.py:465-468`) and SECONDARY (pool
  sizing, `database.py:19-27`) fixes are both already present in code — landed in commit
  `d027f16bd` ("bug-hunter: close 80 bugs from the parallel validate/analyze/test/fix/verify
  batch"), which pre-dates this bookkeeping pass. `backend/tests/unit/test_run_stream_pool_leak.py`
  (also from that batch) is the exact regression suite this card asked for — it pins the leak
  mechanism (`test_injected_closed_session_leaks`), the fix idiom
  (`test_sessionless_store_no_leak`), and the endpoint-level fail-before/pass-after guard
  (`test_stream_endpoint_returns_connections`). Ran it standalone: `cd backend && python3.11 -m
  pytest tests/unit/test_run_stream_pool_leak.py -q` → **3 passed**. Because the fix is already
  shipped, a fresh "red today" run against `run_stream.py`/`database.py` is not obtainable
  without reverting application source (out of scope for a test-writer) — `observedRed` is
  reported `false` for that reason, not because the test is unproven: it is a real,
  currently-green oracle covering this exact defect, not a vacuous pass. No new test needed.
