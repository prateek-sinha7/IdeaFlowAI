---
task: 260812-7sk
title: fix ISS-084 — make Stop actually stop a run
date: 2026-08-12
status: complete
commits:
  code: ebf83005
ids:
  fix: FIX-227
  test: TEST-011
  closed: [ISS-084]
  filed: [ISS-088, ISS-089]
branch: bugfix/spec-revision-context-loss
pushed: false
scope: backend (one frontend type widened)
---

# Quick task 260812-7sk — outcome

Stop works. A run that has crossed a backend restart now observes the cooperative cancel,
stops dispatching, emits `pipeline_cancelled`, and lands in a **terminal** row that the
next boot will not re-adopt.

## What was actually wrong

Not the guards — the value. `ExecutionEngine._drive_resumed_stream` is the **one funnel**
every resume driver (`resume_run` branch (b), `_rearm_gate_run` branch (a),
`_replay_clarify_run`, the user `POST /resume` wrapper) reaches `_execute_impl` through,
and it passed **no `cancel_event` kwarg at all**. The parameter bound its `None` default
(`engine.py:1096`), and every cooperative guard in the kernel is written
`if cancel_event and cancel_event.is_set()` — so with `None`, all twelve short-circuited.
Not one loop was ignoring the flag; the flag was never handed to them.

Independently, `run_engine._register_resume_task` minted an **orphan** `asyncio.Event`
into `_CANCEL_EVENTS` for exactly those runs, on a premise its own comment asserted and
that was false the day it was written. So `cancel_run` found one, `.set()` it, and
returned `cancelled: true` — reporting *"an Event object was in a dict and `.set()` did
not raise"* as *"the run was cancelled"*. That second defect is what turned a visible
failure into a silent one.

Measured on run `d5dbc9f2`: **16,530,718 tokens total, 7,510,082 (45%) billed AFTER the
API answered `cancelled: true`**, and **zero** `pipeline_cancelled` events on the run.

## The change

| file | lines | change |
|---|---|---|
| `backend/agents/execution_engine/engine.py` | 65-78, 889-896, 8100-8116, 8347-8364 | `ResumeCancelEvent` alias · `_resume_cancel_event` slot beside the five existing resume hooks · `_resolve_resume_cancel_event` (mirrors `_fire_resume_cleanup`'s best-effort shape) · **resolve at the funnel and pass `cancel_event=` to `_execute_impl`** |
| `backend/app/api/run_engine.py` | 503-521, 524-541 | `_resume_cancel_event` — get-or-create, the ONLY resume-path mint site; `_register_resume_task` delegates to it; its false comment corrected |
| `backend/app/main.py` | 211-218 | one wiring line at the single wiring site |
| `backend/app/api/run_commands.py` | 318-337, 342-386 | honest ack (`accepted`/`status`) gated on `_is_run_live`; `_arm_cancel_escalation` |
| `backend/app/api/run_shutdown.py` | 219-258, 284, 287-330 | `_drain_then_cancel` extracted from `stop_pipeline_drivers` and shared with the new per-run `stop_run_driver`, which reconciles the terminal row afterwards |
| `frontend/src/lib/api.ts` | 717-746 | `postCancel`'s return type widened to `accepted`/`status`, with an explicit "do not branch on `cancelled`" note. No caller reads the body |

## Decisions worth not re-litigating

1. **Resolve at the funnel, not as a parameter on the four drivers.** One site, and any
   future resume driver inherits the fix instead of re-opening the hole. A parameter would
   be a second mechanism and three more places to forget.
2. **An injected hook, never an import.** The kernel must not import `app.api`. This is the
   sixth callback in the established pattern; `lint-imports` staying **4 kept / 0 broken**
   is the proof, not the intention. Hook unset ⇒ `cancel_event=None` ⇒ INV-3 dormancy,
   which is what keeps the goldens at 10/10.
3. **One registry, one object.** Get-or-create is load-bearing twice: the engine resolving
   later gets the object the endpoint already holds (asserted by **object identity**), and
   a double-register cannot reset an Event a Stop has already set.
4. **The ack is an acceptance, never a claim.** Liveness (`_is_run_live`, the driver task)
   is the truth condition. `cancelled` is retained for wire compatibility and is never
   `true` — it used to be `true` in exactly the case where cancelling was impossible.
5. **The destructive escalation is a fallback, strictly after the cooperative signal had
   its drain budget.** Unconditional `task.cancel()` was **rejected** as the primary fix:
   it reintroduces the ISS-007 delivery race, leaves the row non-terminal, and would leave
   `cancel_event=None` in place for the next reader to inherit.
6. **A cancel that leaves the row non-terminal is not a cancel — it is a delayed re-run.**
   That is why `stop_run_driver` calls the existing `_reconcile_terminal_status` once the
   driver is provably gone.

## Evidence

- **RED before / GREEN after, 9 new backend cases (TEST-011).** The two end-to-end tests
  were proven RED by **mutating the single root-cause line back** (`cancel_event=None`),
  which reproduces the production symptom verbatim:
  `a cancelled resume kept dispatching agents: {'a': 2, 'b': 2} -> {'a': 4, 'b': 4, 'c': 2, 'd': 2}`
  and `the next boot re-adopted a run the owner paid to stop: ['stamp:iss084-…', 'resume_run:iss084-…']`.
  The escalation and anti-lie tests were proven RED the same way (short-circuiting
  `stop_run_driver`; disabling the liveness gate). `test_resume_funnel_is_dormant_when_the_hook_is_unset`
  was RED on first run without any mutation (`assert 'MISSING' is None`).
- **Terminal state, asserted on a real row.** The e2e test drives the real `resume_run`
  over a real in-memory-SQLite `ScopedStore`, then asserts zero agents dispatched, exactly
  one `pipeline_cancelled` in `run_events`, and `WorkflowRun.status == "cancelled"`. A
  second test runs a fresh `restore_non_terminal_runs()` and asserts it adopts nothing.
- **Suites.** 5/5 `test_cancel_stops_resumed_run.py` · 7/7 `test_run_shutdown.py` · 10/10
  `test_rest_answers_cancel.py` · **99 passed** across the whole changed area.
- **Goldens 10 passed / 0 failed** and **lint-imports 4 kept / 0 broken**, both identical
  to the pre-change commit `1ed94666`. No golden regenerated (`git status` on
  `characterization/` clean).
- **ISS-053/052 suites 29/29.** `tests/agents/test_restart_resume.py` held at its
  **7 failed / 48 passed** ISS-078 baseline — neither fixed nor worsened.
- **"Pre-existing" claimed with a SHA.** The 4 reds in `test_rest_run_launch.py` /
  `test_rest_revisions.py` (`'_FakeUser' object has no attribute 'tier'`) were re-measured
  in a detached worktree at `1ed94666` and fail identically there.
- `tsc --noEmit` unchanged at its 2 pre-existing errors, neither in `api.ts`.

## No money was spent

No run was launched, resumed or gate-approved, and no browser was driven. This defect was
found because a resumed build burned 16.5M tokens; verifying it live would have been the
same mistake. The entire proof is offline — the investigation said it could be, and it
was. The backend on `:8010` was left running and untouched.

## Filed, not fixed

- **ISS-088** (major) — the local uvicorn runs without `--timeout-graceful-shutdown` (only
  `docker-entrypoint.sh:35` passes it), so SIGTERM never reaches `lifespan.shutdown()`
  while an SSE stream is live and no local shutdown behaviour has ever been exercised the
  way production exercises it; plus `SHUTDOWN_STOP_RUNS` defaults `False`. Verified by
  `ps` on the live pid, not inferred. Operational — it changes how the process is launched.
- **ISS-089** (major) — a cancel is still purely in-process. A Stop arriving with no live
  driver is now answered *honestly* (`accepted: false`) rather than falsely, but the run
  stays non-terminal and the next boot auto-resumes it. Closing it needs a **durable**
  `cancel_requested` marker checked by `restore_non_terminal_runs` before it adopts.
- **Not touched, deliberately** (one variable at a time — ISS-078's territory): the four
  loops that read no cancel flag at all — `engine.py:2492` (strategy-event forwarding),
  `:3318` (the `_run_agent` redo `while`), `task_loop.py:492` (validator), and the fan-out
  family (`fanout_batch`, `run_fanout`/`run_worker`, `wave_scheduler`). They only become
  visible now that the signal actually arrives, and bundling them would have made this fix
  unreviewable.

## Test-gap note

`test_rest_answers_cancel.py:210-224` seeded `_CANCEL_EVENTS` **itself** and asserted the
endpoint had set it — the one thing that still worked. The test and the bug were the same
shape. It was **reconciled, not deleted**: it now seeds the driver task too, making its own
docstring premise ("a live run has an armed cancel event") true, and asserts the honest
`accepted` acknowledgement.

## Not done

Nothing in scope was skipped. Live verification was deliberately withheld and the reason is
recorded above; ISS-088 and ISS-089 are filed rather than fixed, with their reasoning.
