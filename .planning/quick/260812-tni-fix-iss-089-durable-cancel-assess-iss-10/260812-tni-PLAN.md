---
id: 260812-tni
title: ISS-089 durable cancel (ship) + ISS-103 two-signal teardown (assess)
mode: quick
status: in-progress
date: 2026-08-12
branch: bugfix/spec-revision-context-loss
base_head: 2df5324b29b6ce23c85d2b14cd82a8ce8b6bc94f
---

# ISS-089 (primary) + ISS-103 (secondary)

## Shared root cause

`WorkflowRun.status` is a projection of an in-process asyncio task's lifetime, never a
durable record of what the system was asked to do. Every terminal-status write executes
inside a task; the HTTP command layer writes none.

The two rows pull **opposite ways on the same variable** and must NOT be unified:

| | ISS-089 | ISS-103 |
|---|---|---|
| trigger | a human asked | the process is stopping |
| correct outcome | this run becomes terminal | all runs stay non-terminal in prod (deploy invisibility) |
| must respect `SHUTDOWN_STOP_RUNS` | **no** | **yes** |

A single "make cancels durable at shutdown" fix would reopen the deploy-invisibility hole.

## Task 1 — extract `NON_TERMINAL` to one module constant (prerequisite, INV-12)

**Why load-bearing:** four different `file:line` values for this tuple have been recorded
in one week (`engine.py:5263`, `:5710-5713`, `:5838-5841`, `:5899-5902`) and the value at
this HEAD is **`:5921`** — a fifth. It is an inline literal inside an 8,000-line method and
it is copied a second time in `scripts/cutover_legacy_runs.py:28`. Copying it into
`run_commands.py` would make three.

- `agents/execution_engine/engine.py`: move the literal to module scope as
  `NON_TERMINAL_RUN_STATUSES`; `restore_non_terminal_runs` references the constant.
  Pure move — no logic change, no behaviour change.
- `scripts/cutover_legacy_runs.py`: import it instead of redefining it.
- **verify:** `tests/unit/test_rest_answers_cancel.py` source guard — an AST walk over
  `agents/`, `app/`, `scripts/` asserting exactly ONE assignment whose value is a
  collection equal to that status set, and that it lives in `engine.py` at module scope.
- **done:** guard passes; `restore_non_terminal_runs` behaviour byte-unchanged
  (`test_restart_resume.py` 66 passed).

## Task 2 — ISS-089: write the terminal status at cancel time (Option A)

**Rejected — Option B, the row's own proposal** (durable `cancel_requested` marker +
a new check inside `restore_non_terminal_runs`): needs a migration or a new event type,
edits the resume tier's most delicate three-branch classifier, **misses branch (a)**
(`waiting_for_user` never calls `_stamp_resume_marker` yet still spawns a driver via
`_rearm_gate_run`), and leaves the row lying `running` until the next boot — possibly
forever.

**Shipping — Option A.** `app/api/run_commands.py::cancel_run`, the not-live branch:

1. owner gate — already sufficient (`_review_gate_owned_by`, `run_engine.py:746`).
2. read the row. **Terminal ⇒ answer `not_running` byte-identically, write nothing.**
3. non-terminal ⇒
   a. append a durable `pipeline_cancelled` row via **`ScopedStore.append_event_at_or_after`**
      (`agents/authz.py:522`) — the collision-safe append (FIX-240/ISS-121 proved a
      `uq_run_events_scope_seq` collision here is silently swallowed). Best-effort:
      audit + replay only.
   b. write `status="cancelled"` + `completed_at` by **reusing `_persist_resume_status`**
      (`run_commands.py:692` — the shared terminal-status persist idiom, INV-12).
      **Authoritative: it must succeed**, so a failure answers a 500 `cancel_not_persisted`
      rather than inheriting `_reconcile_terminal_status`'s best-effort degrade.
   c. answer `accepted:true, cancelled:true, status:"cancelled"`.

**No migration. No new table/column/event type. No engine logic edit.** `cancelled` is
already outside `NON_TERMINAL` and `POST /resume` already accepts it, so
`restore_non_terminal_runs` consults the decision implicitly through its existing filter.

**Scope boundary (record on the row):** single-process-safe only. `_is_run_live` is
process-local; today the deployment is single-process (`exec uvicorn`, no `--workers`, no
replicas) so "not live here" == "not live anywhere". The locked to-be architecture is ECS
Fargate, where a Stop hitting instance B would mark a row cancelled while instance A keeps
billing. Not multi-instance-safe; neither option is.

**FE is safe:** both `postCancel` call sites (`DashboardLayout.tsx:1654`, `:1788`) are
`void ….catch(console.error)` — the response body is never read.

### Tests — each seen RED first by reverting the endpoint edit

1. non-live + non-terminal → `status == "cancelled"`, `completed_at` set, response
   `accepted:true/cancelled:true`.
2. **the boot-scan test**: that run then survives a fresh `restore_non_terminal_runs()`
   asserting **zero driver tasks created** (`asyncio.create_task` spy), not "no exception".
   Non-vacuous because the run is seeded resumable-in-flight, so pre-fix it takes branch
   (b) and DOES create a driver task.
3. already-terminal → byte-identical `not_running` response, **no write**.
4. the durable `pipeline_cancelled` **row** exists with a non-colliding seq —
   mutation-tested against a pre-occupied seq.
5. cross-owner → 404, no write (IDOR / INV-8).
6. source guard: `NON_TERMINAL` has exactly one definition.

### Reconciles (changed behaviour, not loosened tests)

`test_cancel_does_not_claim_success_without_a_live_driver` and
`test_cancel_is_idempotent_with_no_active_event` both seed `status="running"` and assert
`accepted:false`. That assertion IS the defect. Both are retargeted at a **terminal** run,
which preserves their exact ISS-084 anti-lie invariant (no unearned `cancelled:true` when
nothing can be done) in the case where it still holds, and the non-terminal case is covered
by the new tests.

## Task 3 — ISS-103: assess, retag, ship only if clean

Direction is fixed: **SIGINT must be made to match SIGTERM, never the reverse.** The
reverse cancels every run on every deploy (rejected at `config.py:206-211`,
`run_shutdown.py:26-36`) and pushes the teardown budget from 24 s to 30 s, at the SIGKILL
line.

**Retag `major` → `minor`:** production never sends SIGINT (`exec uvicorn` ⇒ PID 1;
`docker stop`/ECS send SIGTERM; no `StopSignal` override anywhere), and FIX-234 already
defused it locally (`ENV=development` ⇒ `SHUTDOWN_STOP_RUNS=True` ⇒ drivers are cancelled
cooperatively inside the lifespan before the accidental path runs). Residual window: SIGINT
with the flag explicitly forced off, or a non-development `ENV` receiving SIGINT.

Ship only if the alignment is clean; if it entangles, document precisely and defer. Do NOT
add a second terminal-write path beside `_drain_then_cancel` (`run_shutdown.py:222-259`),
which is deliberately the only escalation policy.

**Checkpoint probe:** does anything on a driver's cancellation unwind write a LangGraph
checkpoint? Answer on a throwaway uvicorn (port 8099) or report as unanswered.

## Money rules in force

Never launch/resume/approve any run. Never signal :8010. Run `41f77342` untouched.
dev.db snapshot taken before work: 21 runs, statuses sha256
`ed90b0bb1c036eecdf544f1f2ba309635e999a68c94007291fe9aba7176fa504`, 233,574 run_events —
re-verified at the end.

## Baselines (measured BEFORE, at `2df5324b`)

goldens **10 passed** / 0 golden files moved · `lint-imports` **4 kept / 0 broken** ·
`test_run_shutdown.py` **9** · `test_shutdown_reachability.py` **8** ·
`test_restart_resume.py` **66** · `test_fanout_cancel.py` **9** ·
`test_rest_gate_commands.py` **28** · `test_rest_answers_cancel.py` **10**.
