---
id: 260812-hsx
slug: iss-088-shutdown-reachability-stop-runs
description: "ISS-088 — make the graceful-shutdown path reachable on a developer machine, remove the double close_checkpointer(), correct the teardown budget, and give SHUTDOWN_STOP_RUNS an env-differentiated default"
date: 2026-08-12
status: complete
issue: ISS-088
branch: bugfix/spec-revision-context-loss
base_commit: 9df9c1c8
commits:
  - f87b92d9  fix(sandbox): close_checkpointer() runs once, LAST, on the shutdown path
  - d9692ec8  feat(config): env-differentiated SHUTDOWN_STOP_RUNS + corrected teardown budget
  - 3a6b972d  test(tests): pin shutdown reachability, the teardown budget and both stop-runs branches
  - 1de7a24e  docs: the documented local run command needs --timeout-graceful-shutdown
---

# Summary — 260812-hsx (ISS-088)

## What shipped, in the owner's mandated order (D3)

**1. The double `close_checkpointer()` is gone (prerequisite).** `main.py:302-307` deleted;
`run_shutdown.py:195` step 4 is now the single wiring site its docstring always claimed to
be. Also moved `"🔴 Shut down complete."` after the teardown body — it was logged *before*
`shutdown_run_infrastructure()` ran — and dropped the false "SINGLE wiring site" comment.

**2. The launch flag is in every developer-facing document.** Ten locations updated with
`--timeout-graceful-shutdown 5`, `--reload` dropped. Three classes of location deliberately
left (dated report / product content / preview fixture), plus the `.planning/phases/**` and
`.knowledge` point-in-time artifacts. The two out-of-repo memory notes (`dev-runtime.md`,
`local-run-bedrock.md`) were updated too — they carry the command agents actually use.

**3. The open question is settled: NO** (see below). That opened the Step 5 gate.

**4. The budget comment is correct and now has a test.** 24s with stop-runs off, 30s with it
on against a 30s `stop_grace_period`. The test parses both numbers from `docker-compose.yml`
and `docker-entrypoint.sh` rather than hardcoding them.

**5. `SHUTDOWN_STOP_RUNS` is env-differentiated.** Declared default stays `False`; a
`model_validator` promotes it to `True` only for `ENV=development` and only when the operator
supplied no value. Production is unchanged.

## The settled question — and it reverses the investigation's hypothesis

**Does `asyncio.run`'s loop teardown already mark in-flight runs `cancelled`?**

**No — not under SIGTERM. Yes under SIGINT.**

Probed on a throwaway server with a driver task and CancelledError handler modelled on
`run_commands.py:2424-2435` (`await` on an unbounded queue, then a synchronous status write,
not re-raised):

```
SIGTERM: {"event": "shutdown_run_infrastructure_completed", "driver_done": [false]}
         — driver_wrote_status_cancelled ABSENT, driver_finally ABSENT
SIGINT:  {"event": "driver_wrote_status_cancelled", "run_id": "probe-run-1"}
         {"event": "driver_finally",                "run_id": "probe-run-1"}
```

The mechanism is `uvicorn/server.py:312-330`. `capture_signals()` restores the original
handlers and then `signal.raise_signal(captured_signal)` — **inside `serve()`, i.e. still
inside `asyncio.run(...)`**. With SIGTERM's default disposition restored the process dies
there, so `asyncio.run` never returns and `Runner.close()` → `_cancel_all_tasks(loop)`
never runs. A control probe with no uvicorn confirms plain asyncio *does* run the handler,
so uvicorn's re-raise is the entire difference. A second instrumented run that stamps a
marker after `server.run()` returns never wrote it, confirming `server.run()` does not return.

**Consequences.** `SHUTDOWN_STOP_RUNS=False` delivers exactly what it documents under SIGTERM
(`docker stop`, systemd, `kill`), so it is not effectively `True` and the default was safe to
make environment-differentiated. But Ctrl-C on a dev machine has *always* cancelled in-flight
runs, by an uncontrolled path that runs after the lifespan — filed as a new issue.

## Measurements I took myself (throwaway uvicorn, port 8099)

| Scenario | Result |
|---|---|
| SSE live, no flag | still alive at **31.25s**; marker had ONLY `startup_complete`; SIGKILL required |
| SSE live, `--timeout-graceful-shutdown 5` | exit **5.82s**; `lifespan_shutdown_entered` → `sse_generator_finally` → `shutdown_run_infrastructure_completed` |
| `--reload`, no flag | parent 96488 + child both alive after 20s — **two** stuck processes; `using StatReload` (watchfiles absent) |

## Tests, each seen RED first

| Test | RED evidence |
|---|---|
| reachability (SIGTERM + live stream) | flag omitted → `Failed: uvicorn did not exit within 25.0s of SIGTERM while an SSE stream was live. Markers written: {"event": "startup_complete", ...}` |
| `close_checkpointer` wired once | `main.py awaits close_checkpointer() 1 time(s)` / `assert 1 == 0` |
| dev default on | `assert False is True` |
| stop-runs ON branch | guard forced `False` → `assert 0 == 1` |
| stop-runs OFF branch | guard forced `True` → `assert 1 == 0` |

The entrypoint-flag and budget tests are guards over parsed files; they pass at HEAD by
construction and fail on drift in either source file.

## Baselines — before and after, unchanged

| Baseline | Before (9df9c1c8) | After |
|---|---|---|
| characterization goldens | 10 passed | **10 passed**, 0 golden files moved |
| `lint-imports` from `backend/` | 4 kept, 0 broken | **4 kept, 0 broken** |
| known pre-existing reds (4 suites) | 11 failed, 54 passed | **11 failed, 54 passed** (same IDs) |
| `tests/unit/test_run_shutdown.py` | 7 passed | **9 passed** (+2 new) |
| `tests/unit/test_shutdown_reachability.py` | — | **8 passed** (new) |
| resume/cancel/restart suites | — | 73 passed |

**Two pre-existing red suites not in the brief**, verified pre-existing by running them at
`9df9c1c8` in a throwaway worktree — identical 8 failures, same IDs:
`test_model_factory.py` (6, all Mistral-fallback) and `test_rest_run_launch.py` (2).

## Honest limitation

**This does not close the money hole.** A *production* run still resumes and finishes after a
restart: `SHUTDOWN_STOP_RUNS` stays `False` there by design, so in-flight runs are left
non-terminal and the next boot's `restore_non_terminal_runs` adopts and completes them. That
is **ISS-089** (durable cancel), judged worth more money than ISS-088. ISS-088 makes the
shutdown path *reachable*; only ISS-089 makes a Stop *survive* the process.

Second limitation: dev and production now differ by one guarded branch (step 3). The
*reachability* path — the thing ISS-088 is about — is identical in both.

## New findings filed, not folded

- The SIGTERM/SIGINT divergence above (Ctrl-C already cancels runs, after the pool closes).
- Stale line-number citations in shutdown-path comments (`docker-entrypoint.sh:27`,
  `run_shutdown.py:30/97-98/275`).
- The SSE-generator-unwind race: `lifespan.shutdown()` is entered *before* the stream
  generators finish unwinding (reproduced twice — `lifespan_shutdown_entered` stamps 0.4ms
  before `sse_generator_finally`), because `server.py:287-292` cancels the connection tasks
  and calls `lifespan.shutdown()` without awaiting them.

## Safety

No Bedrock call, no browser, no run launched/resumed/gated. The owner's backend (pid 91032,
port 8010) was never signalled — still up since Wed Aug 12 05:03:34. Every probe process was
a throwaway on port 8099 started and reaped by me; port 8099 is free and no strays remain.
