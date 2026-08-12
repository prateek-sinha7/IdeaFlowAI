---
id: 260812-hsx
slug: iss-088-shutdown-reachability-stop-runs
description: "ISS-088 — make the graceful-shutdown path reachable on a developer machine (uvicorn launch flag), remove the double close_checkpointer(), correct the teardown budget, and give SHUTDOWN_STOP_RUNS an env-differentiated default (owner decision D3)"
date: 2026-08-12
status: planned
issue: ISS-088
branch: bugfix/spec-revision-context-loss
base_commit: 9df9c1c8
---

# Quick Task 260812-hsx — ISS-088: shutdown reachability + env-differentiated stop-runs

## Problem (reproduced at HEAD `9df9c1c8`, offline, on a throwaway uvicorn on port 8099)

A SIGTERM to the local backend does not stop it while any SSE stream is live, and the
FastAPI lifespan's shutdown half never runs at all.

`uvicorn/protocols/http/h11_impl.py:328-337` — `H11Protocol.shutdown()` closes the
transport only when `self.cycle is None or self.cycle.response_complete`. An
`EventSourceResponse` has `response_complete == False` for its whole life, so the `else`
branch runs (`self.cycle.keep_alive = False`) and the connection never leaves
`server_state.connections`. `uvicorn/server.py:301-305` then does
`asyncio.wait_for(self._wait_tasks_to_complete(), timeout=self.config.timeout_graceful_shutdown)`
with `timeout=None` (the default, `uvicorn/config.py:215`), so the wait is unbounded and
line 292's `await self.lifespan.shutdown()` is never reached.

Measured myself, both runs on port 8099:

```
[probe:mynoflag] started throwaway uvicorn pid=95390 extra=''
[probe:mynoflag] RESULT exited_within_30s=no elapsed=31.25s
{"event": "startup_complete", "t": 1786531348.221144, "pid": 95390}     <- the ONLY marker
INFO:     Waiting for connections to close. (CTRL+C to force quit)      <- server.py:297

[probe:myflag5] started throwaway uvicorn pid=95523 extra='--timeout-graceful-shutdown 5'
[probe:myflag5] RESULT exited_within_30s=yes elapsed=5.82s
{"event": "startup_complete",                      "t": 1786531389.556082}
{"event": "lifespan_shutdown_entered",             "t": 1786531398.0193348}
{"event": "sse_generator_finally",                 "t": 1786531398.019713, "ticks": 9}
{"event": "shutdown_run_infrastructure_completed", "t": 1786531398.222181, "slept_ms": 200}
INFO:     Application shutdown complete.
```

Production already passes the flag (`backend/docker-entrypoint.sh:35`). **No in-repo
document tells a developer to.** The command appears nine different ways across the repo
and none matches what actually runs.

Two further defects found in the same path:

- **`close_checkpointer()` is called twice, in the order the docstring forbids.**
  `main.py:302-307` closes the pool, then `main.py:320` runs
  `shutdown_run_infrastructure()`, whose step 4 (`run_shutdown.py:189-195`) calls it again
  where the module docstring promises it happens "LAST among the awaits … Steps 1-3 may
  still hold a pooled connection, so this runs after them." The second call is a no-op
  (`checkpointer.py` one-way `_closed` latch), so the documented ordering guarantee is
  false in production too, and `main.py:296` still claims to be "the SINGLE wiring site".
  Live INV-12 violation, and a real hazard the moment stop-runs is on:
  `stop_pipeline_drivers()` would drive runs against an already-closed pool.
- **The budget comment under-counts.** `config.py:199-201` says "10 + 3 + 5 for the
  checkpointer, keep the total under 25s". It omits both cancel-and-wait escalations and
  the pump drain entirely, and it cites `docker-compose.yml:138` for a value that lives at
  `docker-compose.yml:75`.

## The open question — SETTLED, and the answer reverses the investigation's guess

**Question:** does `asyncio.run`'s loop teardown already mark in-flight runs `cancelled`
via the launch driver's `except asyncio.CancelledError` handler
(`run_commands.py:2424-2435`), making `SHUTDOWN_STOP_RUNS=False` a lie?

**Answer: NO under SIGTERM. YES under SIGINT.** Settled empirically with a probe that
models the driver task and its handler faithfully (`probe_step3_app.py`), on two different
launch paths, plus the mechanism read in source.

```
SIGTERM:  {"event": "shutdown_run_infrastructure_completed", "driver_done": [false]}
          (no driver_wrote_status_cancelled, no driver_finally, no after_server_run_returned)

SIGINT:   {"event": "shutdown_run_infrastructure_completed", "driver_done": [false]}
          {"event": "driver_wrote_status_cancelled", "run_id": "probe-run-1"}
          {"event": "driver_finally",                "run_id": "probe-run-1"}
```

**Mechanism** — `uvicorn/server.py:312-330`, `capture_signals()`:

```python
        original_handlers = {sig: signal.signal(sig, self.handle_exit) for sig in HANDLED_SIGNALS}
        try:
            yield
        finally:
            for sig, handler in original_handlers.items():
                signal.signal(sig, handler)
        for captured_signal in reversed(self._captured_signals):
            signal.raise_signal(captured_signal)
```

This runs **inside** `serve()`, i.e. still inside `asyncio.run(...)` (`server.py:64-66`).
It restores SIGTERM's default disposition and then re-raises it, so the process dies right
there: `asyncio.run` never returns, `Runner.close()` → `_cancel_all_tasks(loop)`
(`asyncio/runners.py:193-201`) never runs, and no driver handler is ever invoked. A
control run with no uvicorn (`isolate_cancel_all_tasks.py`) confirms plain asyncio *does*
run the handler, so uvicorn's re-raise is the whole difference. SIGINT differs only because
its restored handler raises `KeyboardInterrupt` in Python, which unwinds through
`asyncio.run` normally.

**Consequences.** `SHUTDOWN_STOP_RUNS=False` delivers exactly what it documents under
SIGTERM (`docker stop`, systemd, `kill`) — runs stay non-terminal for the next boot's
`restore_non_terminal_runs`. It is **not** effectively `True`. So the Step 5 gate is open.

## Scope — the owner's decision D3, in its mandated order

D3 is locked: env-differentiated `SHUTDOWN_STOP_RUNS` (ON locally, OFF in production),
with the launch flag and the double-close landing **first**.

### Task 1 — remove the double `close_checkpointer()` (prerequisite, lands first)

- Delete the superseded close at `backend/app/main.py:302-307`. `run_shutdown.py:195`
  becomes the single site, which is what its docstring already promises.
- Rewrite the `main.py:292-296` comment: it claims to be "the SINGLE wiring site" and it
  is not.
- Move `logger.info("🔴 Shut down complete.")` after the teardown body — today it is
  logged *before* `shutdown_run_infrastructure()` runs.
- INV-12: this is the deletion, not an addition.

### Task 2 — the launch flag, in every dev-facing document

Add `--timeout-graceful-shutdown 5` and drop `--reload`.

**Edit (10):** `README.txt:78`, `README.txt:114`,
`docs/PRODUCTION_DEPLOYMENT_GUIDE.md:166`, `:178`, `docs/FLOWIN_HANDOFF.md:284`,
`frontend/e2e/README.md:37`, `frontend/e2e/tests/ts-v.per-workflow.live.spec.ts:15`,
`frontend/e2e/tests/ts-w.model-override.live.spec.ts:16`, `.planning/TEST-REGISTER.md:42`,
`.planning/RESUME-QA-TEST-SHEET.md:26`.

**Leave, with reason:**
- `docs/LOCALSTACK_SMOKE_REPORT.md:23,178` — a dated smoke *report*, a record of what was
  run that day, not an instruction.
- `frontend/src/data/skills.ts:25635` and `skills/ecc/flox-environments/SKILL.md:398` —
  seeded user-facing **product content** (a "skill" document a user reads), not this
  repo's dev docs. Rewriting it would change product data to fix a dev-runtime issue.
- `frontend/src/app/test-preview/page.tsx:118,286,1894,2115` — a preview **fixture**;
  the strings are sample output for a UI page.
- `.knowledge/cards/TEST-1-1.md:16` and every `.planning/phases/**` artifact —
  point-in-time records of what a phase did.

**Port: stays 8000.** The repo's canonical default is 8000 in three committed sources —
`frontend/src/lib/env.ts:37` (`return "http://localhost:8000";`),
`env-templates/.env.frontend:7`, and `frontend/e2e/fixtures/live.ts:13`
(`process.env.E2E_API_URL || "http://localhost:8000"`). This machine runs 8010 (verified:
`ps` on pid 91032), which is a local override, not the repo default. Moving the docs to
8010 without moving those three would create a *new* inconsistency and break the
documented default; moving those three is out of scope for ISS-088 and would change the
owner's working setup. The 8010 convention is recorded where it belongs — in the memory
notes, which describe this machine.

**`--reload`: not recommended, removed from the documented commands.** Measured myself:
untreated it produces **two** stuck processes, not one — the reloader parent hangs on
`self.process.join()` (`uvicorn/supervisors/basereload.py:100-105`) while the child hangs
on the same unbounded wait:

```
[reload:myreload-noflag] parent(reloader)=96488 child(server)=96491
[reload:myreload-noflag] after 20s: parent_exited=no child_exited=no
INFO:     Started reloader process [96488] using StatReload
```

`using StatReload` is the second reason: `watchfiles` is **not installed** in this Python
3.11 environment (verified), so `--reload` silently degrades to polling. The third is that
it masks crashes, which `.planning/RESUME-QA-TEST-SHEET.md:20` already says. The process
that actually runs here uses no `--reload`.

**Out-of-repo memory notes** (agents read these, so the fix does not take effect without
them): `~/.claude/projects/-Users-1000060523-Documents-Work-UKI-Flowin-flowin/memory/dev-runtime.md`
and `.../memory/local-run-bedrock.md:13`.

### Task 3 — correct the budget comment and pin it with a test

`config.py:195-201` — count every wait and fix the `docker-compose.yml:138` → `:75` cite:

| Step | Source | Seconds |
|---|---|---|
| uvicorn graceful window | `docker-entrypoint.sh:35` | 5 |
| Concierge drain | `run_shutdown.py:101-103` | 10 |
| Concierge cancel-and-wait | `run_shutdown.py:124` | 3 |
| Pump drain | `run_shutdown.py:161-163` | 3 |
| Pump cancel-and-wait | `run_shutdown.py:174-176` | 3 |
| **Total, stop-runs OFF** | | **24** |
| `stop_pipeline_drivers` drain + escalate | `run_shutdown.py:233-249` | +3 +3 |
| **Total, stop-runs ON** | | **30** |

30 against `stop_grace_period: 30s` is at the SIGKILL line. That is the arithmetic reason
production stays OFF, and the test must encode it rather than a prose claim.

### Task 4 — env-differentiated `SHUTDOWN_STOP_RUNS`

Declared default stays `False`; a `model_validator(mode="after")` promotes it to `True`
only when `ENV` is `development` **and** the field was not explicitly provided. Verified
semantics on the installed pydantic 2.12.5 / pydantic-settings 2.7.1:

```
default(dev):        True     ENV=production:      False
env FLAG=false dev:  False    env FLAG=true prod:  True
```

An explicit `SHUTDOWN_STOP_RUNS` env var always wins, in both directions — the switch stays
operable, and production (`ENV != development`) resolves `False`.

## Tests — each seen RED before it is trusted

1. **`test_shutdown_reachability.py`** — the test that would have caught this. Spawns a
   real uvicorn **subprocess** on an ephemeral port serving a minimal app with an
   `EventSourceResponse` and a lifespan that touches a marker file, opens a stream, sends
   SIGTERM, and asserts the process exits within the budget **and** the marker records that
   the lifespan shutdown body ran. A subprocess is required, not the in-process
   `uvicorn.Server` of `test_run_stream_pool_leak.py:196-238`: `capture_signals()` binds
   handlers only on the main thread, and the defect is in the signal path.
   RED proof: run the same scenario with the flag omitted.
2. **Budget arithmetic** — parses `stop_grace_period` from `docker-compose.yml` and the
   graceful window from `docker-entrypoint.sh` (nothing hardcoded, so drift in either file
   is caught) and asserts the production teardown sum stays under it.
3. **`docker-entrypoint.sh` still passes `--timeout-graceful-shutdown`** — one line,
   prevents a silent regression to the pre-KAN-151 state.
4. **`close_checkpointer()` is wired exactly once** on the shutdown path — pins Task 1's
   deletion by counting call sites in `main.py` + `run_shutdown.py`.

## Baselines — must not move

Measured by me at `9df9c1c8` before any edit:

- characterization goldens: **10 passed** (0 golden files may move)
- `lint-imports` from `backend/`: **4 kept, 0 broken**
- known pre-existing reds (`test_gates.py` 3, `test_declared_gate_streaming.py` 3,
  `test_wire_parity.py` 4, `test_prompt_contracts.py` 1): **11 failed, 54 passed**
- `tests/unit/test_run_shutdown.py`: **7 passed**

## Honest limitation, to be recorded on the ISS-088 row

**This does not close the money hole.** A restart still lets a *production* run resume and
finish: `SHUTDOWN_STOP_RUNS` stays `False` there by design, so in-flight runs are left
non-terminal and the next boot's `restore_non_terminal_runs` adopts and completes them.
That is **ISS-089** (durable cancel), which the investigation judged worth more money than
ISS-088. ISS-088 makes the shutdown path *reachable*; only ISS-089 makes a Stop *survive*
the process.

## Not in scope

- Making `sse-starlette`'s own graceful-shutdown hook work. It patches
  `uvicorn.main.Server.handle_exit` at import time, but uvicorn binds its signal handler in
  `capture_signals()` **before** `config.load()` imports the app, so the patch can never be
  live for a string-loaded app (proved: `PATCH_IS_LIVE_IN_HANDLER = False`). The uvicorn
  flag is the only lever.
- Any live/Bedrock run, browser drive, or restart of the owner's backend (pid 91032).
