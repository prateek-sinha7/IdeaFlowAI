---
phase: 260716-heb
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/app/api/run_stream.py
  - backend/app/models/database.py
  - backend/tests/unit/test_run_stream_pool_leak.py
autonomous: true
requirements: [BUG-004]

must_haves:
  truths:
    - "Each live SSE stream on /api/runs/{id}/events/stream returns its DB connection to the pool after the generator is exhausted — no leak, no gc.collect() needed."
    - "The SSE frames, durable replay, stream_attached handshake, and D-14g gate re-arm stay byte/event-identical (INV-3 parity: characterization + wire_parity green)."
    - "A cross-owner or missing run still resolves to 404 (owner isolation, run_stream.py :220/:239, is preserved)."
    - "The regression test fails against the pre-fix run_stream.py (leak) and passes after (fail-before / pass-after)."
    - "The Postgres/prod engine gets explicit pool sizing; the SQLite dev/offline engine is byte-unchanged so offline test collection still imports database.py cleanly."
  artifacts:
    - path: "backend/app/api/run_stream.py"
      provides: "Session-less ScopedStore for the streaming generator (owned=True → closes per read)"
      contains: "_iter_sse_frames"
    - path: "backend/app/models/database.py"
      provides: "Explicit QueuePool sizing on the non-SQLite (Postgres) engine, pool_pre_ping retained"
      contains: "create_engine"
    - path: "backend/tests/unit/test_run_stream_pool_leak.py"
      provides: "Behavioral pool-checkout regression proving the SSE leak is closed"
      contains: "checkedout"
  key_links:
    - from: "backend/app/api/run_stream.py stream_run_events"
      to: "_iter_sse_frames"
      via: "session-less ScopedStore (no session= injected)"
      pattern: "ScopedStore\\(\\s*owner_id=current_user\\.id"
    - from: "agents/authz.py ScopedStore._acquire (owned=True)"
      to: "read_events finally: session.close()"
      via: "fresh SessionLocal per read, closed in finally"
      pattern: "if owned:\\s*session\\.close\\(\\)"
---

<objective>
Close BUG-004 — the SSE-stream DB connection leak activated by the Phase-44 WS→SSE cutover. `app/api/run_stream.py::stream_run_events` builds `ScopedStore(session=db)` and consumes it INSIDE the streaming generator `_iter_sse_frames` (`read_events` at `:145` replay + `:178` gate re-arm). FastAPI ≥0.106 tears down the `get_db` yield-dependency BEFORE the streaming body runs, so the generator re-acquires a fresh QueuePool connection on the already-closed session; `ScopedStore._acquire` reports `owned=False` (`authz.py:95-99`) so `read_events`'s `finally: if owned: session.close()` (`authz.py:328-330`) never releases it — one leaked connection per live SSE stream, reclaimed only by GC (proven in `/tmp/sse_pool_repro2.py`). Under EventSource reconnects/tabs the default `5+10` pool exhausts and `submit_answers` 500s.

Purpose: Restore connection hygiene on the sole run-event transport so multi-stream / reconnect load does not exhaust the pool, WITHOUT changing a single SSE frame (INV-3 byte/event parity is load-bearing).

Output:
- PRIMARY: the generator's store is constructed session-less (mirrors the safe `post_message` idiom, `run_commands.py:758`), so each `read_events` opens+closes its own `SessionLocal`.
- SECONDARY (defense-in-depth): explicit pool sizing on the Postgres engine.
- A behavioral regression test that fails before the fix and passes after.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/BUG-004-GROUNDED-CONTEXT.md
@.planning/STATE.md
@backend/CLAUDE.md

# Source under change + the anchors (already verified during planning):
@backend/app/api/run_stream.py
@backend/app/models/database.py

# The safe idioms to mirror (READ ONLY — do NOT edit these):
#   agents/authz.py :87-99 (_acquire owned semantics), :315-330 (read_events finally close)
#   app/api/run_commands.py :758 (post_message — session-less ScopedStore, the correct pattern)
# Test harness reference (seed WorkflowRun/RunEvent, get_current_user override, router):
#   backend/tests/unit/test_sse_stream.py
# Empirical repro of the leak (reuse the QueuePool + checkedout() accounting pattern):
#   /tmp/sse_pool_repro2.py   (rebuild from the pattern if swept)
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write the failing pool-leak regression test (RED)</name>
  <files>backend/tests/unit/test_run_stream_pool_leak.py</files>
  <behavior>
    - test_injected_closed_session_leaks (mechanism / documents the bug): with a QueuePool-backed file-SQLite engine whose sessionmaker is monkeypatched onto `app.models.database.SessionLocal`, open `db = SessionLocal()`, run a query, then `db.close()` (mimics get_db's finally). Build `ScopedStore(owner_id, workspace_id, session=db)` and `await store.read_events(run_id, after_seq=0)`. Assert `engine.pool.checkedout()` stays >= 1 (leak, NO gc). Then assert `gc.collect()` reclaims it back to baseline — this pins the root-cause mechanism.
    - test_sessionless_store_no_leak (the fix idiom): build `ScopedStore(owner_id, workspace_id)` (NO session). `await store.read_events(...)` several times. Assert `engine.pool.checkedout()` returns to baseline after each call WITHOUT gc.collect().
    - test_stream_endpoint_returns_connections (THE regression guard, fail-before/pass-after on run_stream.py): drive `stream_run_events` end-to-end against a QueuePool engine with `get_db` + `get_current_user` overridden; seed a WorkflowRun (matching owner_id/workspace_id) + a couple RunEvent rows; ensure `workflow_id` is NOT in `_PIPELINE_QUEUES` (finished run → live_queue is None → generator does replay+handshake then returns). Fully consume the SSE response, then assert `engine.pool.checkedout() == baseline` WITHOUT gc.collect().
  </behavior>
  <action>Create backend/tests/unit/test_run_stream_pool_leak.py as an OFFLINE behavioral regression for BUG-004. Use a real QueuePool-backed file-SQLite engine (poolclass=QueuePool, pool_size=1, max_overflow=2, pool_timeout=2 — the /tmp/sse_pool_repro2.py pattern) because `engine.pool.checkedout()` is only meaningful on QueuePool (StaticPool, used by test_sse_stream.py, always pins one connection and cannot show the leak). Monkeypatch `app.models.database.SessionLocal` to this engine's sessionmaker so the session-less `ScopedStore._acquire` path opens connections on the instrumented pool. Import `_iter_sse_frames`, `stream_run_events`/`router` from app.api.run_stream, `ScopedStore` from agents.authz, and reuse the WorkflowRun/RunEvent seeding + `get_current_user` override shape from tests/unit/test_sse_stream.py. For test_stream_endpoint_returns_connections, prefer driving the ASGI app in-process (httpx ASGITransport or the FastAPI TestClient) consuming the full text/event-stream body; if that transport does NOT reproduce the FastAPI>=0.106 teardown-before-streaming ordering (i.e. the leak does not appear pre-fix), fall back to an in-process uvicorn server exactly as /tmp/sse_pool_repro2.py does — that variant is known to reproduce. The whole point is to OBSERVE RED before the run_stream.py fix; do not proceed until you have seen the endpoint assertion fail on the current (unfixed) tree. Do NOT touch run_stream.py or database.py in this task. Do NOT run the full backend pytest (it hangs offline) — scope to this file only.</action>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/unit/test_run_stream_pool_leak.py -q 2>&1 | tail -20  # EXPECT RED: test_stream_endpoint_returns_connections FAILS (checkedout stays 1) on the pre-fix tree — record the observed leak count</automated>
  </verify>
  <done>The test file exists and runs offline; test_stream_endpoint_returns_connections is observed FAILING against the current unfixed run_stream.py (connection not returned without gc), while test_sessionless_store_no_leak and test_injected_closed_session_leaks pass. The RED is recorded in the summary.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: PRIMARY fix — session-less ScopedStore for the SSE generator (GREEN)</name>
  <files>backend/app/api/run_stream.py</files>
  <behavior>
    - After the fix, driving stream_run_events to completion returns every checked-out connection to the pool without gc.collect() (test_stream_endpoint_returns_connections flips to GREEN).
    - The two owner checks still 404 a cross-owner / missing run.
    - The SSE frames (durable replay, stream_attached, D-14g gate re-arm) are byte/event-identical (INV-3 parity oracles stay green).
  </behavior>
  <action>In backend/app/api/run_stream.py::stream_run_events, keep the request-session store (`ScopedStore(owner_id=current_user.id, workspace_id=workflow_run.workspace_id, session=db)` at :233-237) UNCHANGED for the Layer-2 owner check `store.get_run(workflow_id)` at :239 — that runs in request scope and returns normally, so leave the owner-isolation path byte-identical (D-13 IDOR→404). Then, after the Layer-2 check block, construct a SEPARATE session-less store — `ScopedStore(owner_id=current_user.id, workspace_id=workflow_run.workspace_id)` with NO `session=` — and pass THAT store into `_iter_sse_frames(...)` (change the `store=store` argument in the EventSourceResponse construction to the new session-less store). Rationale: the generator's `read_events` (:145, :178) then hits `_acquire`'s owned=True branch (authz.py:95-99 → :328-330 closes), so no connection is held during the idle live-drain loop — the exact safe idiom `post_message` uses (run_commands.py:758). Do NOT wrap the request `db` in a try/finally instead — that still pins one connection idle for the whole stream; the session-less store is the correct fix per the grounded spec. Change ONLY the store's session-acquisition mode: do not alter frame content, event ordering, the handshake, the gate re-arm, the queue attach, or the owner checks. Do NOT touch database.py in this task and do NOT edit any SAFE sibling (run_commands.py, runs.py, prototype_templates.py).</action>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/unit/test_run_stream_pool_leak.py -q 2>&1 | tail -5  # EXPECT: all pass — endpoint now returns connections without gc</automated>
    <automated>cd backend && python3.11 -m pytest tests/agents/ -k characterization -q --continue-on-collection-errors 2>&1 | tail -5  # EXPECT: 10 passed (INV-3 frame parity unchanged)</automated>
    <automated>cd backend && python3.11 -m pytest tests/agents/test_wire_parity.py -q 2>&1 | tail -5  # EXPECT: 6 passed (SSE wire parity oracle)</automated>
  </verify>
  <done>test_run_stream_pool_leak.py is fully green (leak closed, no gc needed); the characterization suite (10 passed) and test_wire_parity.py (6 passed) stay green, proving the SSE frames are byte/event-identical; the cross-owner 404 assertions still pass.</done>
</task>

<task type="auto">
  <name>Task 3: SECONDARY — right-size the Postgres pool + full INV-3 gate</name>
  <files>backend/app/models/database.py</files>
  <action>In backend/app/models/database.py, add explicit pool sizing to the `create_engine(...)` call at :12, but ONLY for the non-SQLite branch — mirror the existing `_sqlite` conditional used for `connect_args`. Build a `_pool_kwargs` mapping that is empty when `_sqlite` is true and otherwise sets `pool_size=20, max_overflow=40, pool_timeout=30, pool_recycle=1800`, then spread it into `create_engine(...)` alongside the existing args; keep `pool_pre_ping=True` and the SQLite `connect_args`/foreign-keys hook exactly as-is. WHY SQLite is excluded: the dev/offline `DATABASE_URL` is `sqlite:///./dev.db` (config.py:212) and a `:memory:` SQLite engine uses SingletonThreadPool, which rejects `max_overflow`/`pool_timeout`; gating the sizing to Postgres keeps the offline engine byte-unchanged so test collection still imports database.py cleanly and INV-3 parity is untouched. Sizing alone does NOT fix the leak (Task 2 does) — this only raises the exhaustion ceiling for multi-run/prod scale. Do NOT change `SessionLocal`, `get_db`, `Base`, or the sqlite FK hook. Then run the FULL offline verification gate below (targeted suites only — never the full backend pytest, it hangs offline).</action>
  <verify>
    <automated>cd backend && python3.11 -c "import app.models.database as d; assert d.engine is not None; print('database import OK, pool_pre_ping retained')"  # EXPECT: clean import under sqlite dev URL (no TypeError from pool kwargs)</automated>
    <automated>cd backend && python3.11 -m pytest tests/unit/test_run_stream_pool_leak.py -q 2>&1 | tail -5  # EXPECT: all pass (leak still closed)</automated>
    <automated>cd backend && python3.11 -m pytest tests/agents/ -k characterization -q --continue-on-collection-errors 2>&1 | tail -5  # EXPECT: 10 passed</automated>
    <automated>cd backend && python3.11 -m pytest tests/agents/test_wire_parity.py -q 2>&1 | tail -5  # EXPECT: 6 passed</automated>
    <automated>cd backend && /opt/homebrew/bin/lint-imports 2>&1 | tail -5  # EXPECT: 4 contracts kept, 0 broken</automated>
  </verify>
  <done>database.py imports cleanly under the sqlite dev URL with `pool_pre_ping` retained and Postgres pool sizing applied only in the non-sqlite branch; the pool-leak regression, characterization (10 passed), wire_parity (6 passed), and lint-imports (4 kept / 0 broken) are ALL green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser → SSE endpoint | Untrusted: EventSource auto-reconnects and multiple tabs open many concurrent streams; `Last-Event-ID` header is client-controlled. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-heb-01 | Denial of Service | run_stream.py `stream_run_events` / `_iter_sse_frames` pool usage | mitigate | PRIMARY: session-less generator store returns its connection per `read_events` (owned=True closes). SECONDARY: explicit Postgres pool sizing raises the exhaustion ceiling. Regression test asserts `checkedout()` returns to baseline without gc. |
| T-heb-02 | Information Disclosure / Spoofing | run_stream.py owner checks (`:220` ORM filter, `:239` `store.get_run`) | mitigate | Owner-isolation path left byte-identical (request-session store still backs the Layer-2 check); regression + characterization assert cross-owner/missing → 404 (IDOR → 404, never 403). |
| T-heb-SC | Tampering (supply chain) | package installs | accept | No npm/pip/cargo installs in this fix; no new dependency introduced. |
</threat_model>

<verification>
Run from `backend/` (python3.11, no venv), targeted suites only — the FULL backend pytest HANGS offline (Chromium/Bedrock/Postgres-gated); never run it.

1. `python3.11 -m pytest tests/unit/test_run_stream_pool_leak.py -q` → all pass (leak closed; endpoint returns connections without gc).
2. `python3.11 -m pytest tests/agents/ -k characterization -q --continue-on-collection-errors` → 10 passed (INV-3 frame parity).
3. `python3.11 -m pytest tests/agents/test_wire_parity.py -q` → 6 passed (SSE wire-parity oracle). NOTE: the oracle lives at `tests/agents/test_wire_parity.py` (the grounded-constraint's `tests/unit/…` path is wrong — verified during planning).
4. `/opt/homebrew/bin/lint-imports` → 4 contracts kept, 0 broken.
5. `python3.11 -c "import app.models.database"` → clean import under the sqlite dev URL.

Fail-before/pass-after evidence: Task 1 records the endpoint assertion RED on the pre-fix tree; Task 2 flips it GREEN.
</verification>

<success_criteria>
- BUG-004 leak is closed: the SSE stream endpoint returns every checked-out DB connection to the pool after the generator is exhausted, with no gc.collect() (behavioral regression green).
- Zero SSE wire change: characterization (10) + wire_parity (6) stay green — durable replay, `stream_attached`, and D-14g gate re-arm are byte/event-identical (INV-3).
- Owner isolation preserved: cross-owner / missing run still → 404.
- Postgres engine right-sized (defense-in-depth); SQLite dev/offline engine byte-unchanged.
- lint-imports 4 kept / 0 broken; only the three declared files touched; no SAFE sibling edited.

HANDOFF (orchestrator, post-fix — NOT part of executor scope): the definitive LIVE proof requires a backend RESTART (the pool-sizing change needs it; `--reload` alone won't re-create the engine). After restart, open many concurrent SSE streams, watch `engine.pool.checkedout()` stay near 0, and confirm a concurrent `submit_answers` returns 200. The executor must NOT run this live multi-stream Bedrock load test.
</success_criteria>

<output>
Create `.planning/quick/260716-heb-fix-bug-004-sse-stream-db-connection-lea/260716-heb-SUMMARY.md` when done.

Constraints reminder: branch feat/ui-2 (NEVER main); worktrees OFF → sequential; NO commit trailer (no Co-Authored-By / Claude-Session); NEVER push.
</output>
