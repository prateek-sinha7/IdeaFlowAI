---
id: 260812-tni
title: ISS-089 durable cancel (shipped) + ISS-103 two-signal teardown (reassessed, deferred)
status: complete
date: 2026-08-12
branch: bugfix/spec-revision-context-loss
base_head: 2df5324b29b6ce23c85d2b14cd82a8ce8b6bc94f
code_commit: 8d84b1a6
fix_ids: [FIX-243]
test_ids: [TEST-027]
issues_closed: [ISS-089]
issues_retagged: [ISS-103]
issues_filed: [ISS-133, ISS-134]
---

# 260812-tni — a Stop that survives the process

## Outcome

**ISS-089 is fixed and closed** (FIX-243 / TEST-027, commit `8d84b1a6`).
**ISS-103 is reassessed**: direction fixed, severity lowered `major → minor`, code change
**deferred with a mechanical reason**, and its one open question **answered by probe**.
Two new rows filed: **ISS-133**, **ISS-134**.

## ISS-089 — what was wrong

`POST /api/runs/{id}/cancel` wrote **no status at all** in the not-live branch. It set an
in-memory `asyncio.Event` and armed an in-process escalation task, both of which die with
the process. So a Stop that arrived with no live driver — after a restart, during a deploy,
or on any resumed run whose Event was an orphan — was lost, the row stayed inside
`restore_non_terminal_runs`' non-terminal filter, and the next boot re-adopted the run and
drove it to completion at the owner's expense.

## What shipped, and what was rejected

**Rejected — the row's own Option B** (a durable `cancel_requested` marker checked inside
`restore_non_terminal_runs`): needs a migration or a new event type, edits the resume tier's
most delicate three-branch classifier, **misses branch (a)** (`waiting_for_user` spawns
`_rearm_gate_run` without ever calling `_stamp_resume_marker`), and leaves the row reading
`running` until the next boot — possibly forever.

**Shipped — Option A, write the terminal status at cancel time.** One function:

- terminal (or absent) row ⇒ the pre-existing `not_running` ack, **byte-identical**, no write;
- non-terminal ⇒ a durable `pipeline_cancelled` row via the **collision-safe**
  `ScopedStore.append_event_at_or_after` (best-effort audit/replay) **+**
  `status="cancelled"` + `completed_at` via `_persist_resume_status` (**authoritative** —
  a failure answers HTTP 500 `cancel_not_persisted`, it does not inherit
  `_reconcile_terminal_status`'s degrade) **+** `accepted:true, cancelled:true,
  status:"cancelled"`.

**No migration, no new table/column/event type, and no change to
`restore_non_terminal_runs`** — `cancelled` is already outside the non-terminal set and
`POST /resume` already accepts it, so the boot scan consults the decision through the filter
it already has. The run moves from **automatic** resume to **explicit, owner-authenticated**
resume.

**INV-12 prerequisite:** the non-terminal status tuple — cited by **five** different wrong
`file:line` values in one week and copied into `scripts/cutover_legacy_runs.py` — is now one
module constant `NON_TERMINAL_RUN_STATUSES`, pinned by an AST source guard that matches on
the **value**, so a copy under any name is caught.

## Proof

- **The money assertion is a task count.** At `2df5324b` the boot-scan test observed
  `ExecutionEngine.restore_non_terminal_runs.<locals>._admitted_resume` spawned for a run
  whose Stop had just answered `not_running`. Post-fix: zero tasks.
- Every new case seen **RED first** in a detached worktree at `2df5324b` — never a stash.
- The source guard **mutation-tested** against the surviving duplicate
  (`defined 2 times: ['agents/execution_engine/engine.py:478', 'scripts/cutover_legacy_runs.py:28']`).
- The seq-collision case is a real race mutation, asserted on the landed seq.
- Two existing cases **reconciled, not loosened**: both asserted `accepted:false` for a
  `running` run — that assertion **is** the defect — and now seed a terminal run, preserving
  ISS-084's anti-lie invariant where it still holds.

Baselines vs `2df5324b`: goldens **10 passed / 0 of 15 golden files moved**, lint-imports
**4 kept / 0 broken**, `test_run_shutdown` 9, `test_shutdown_reachability` 8,
`test_restart_resume` 66, `test_fanout_cancel` 9, `test_rest_gate_commands` 28 — all
unchanged. `test_rest_answers_cancel` 10 → 20. The **32-id pre-existing-red set is unchanged
by ID**; a 12-suite blast-radius sweep is 138 passed / 3 failed, those 3 being the ISS-093
stale clarify-round tests re-measured at `2df5324b` as the same ids.

## ISS-103 — reassessed

- **Direction fixed: SIGINT must be made to match SIGTERM, never the reverse.** The reverse
  cancels every run on every deploy and pushes the teardown budget from 24 s to 30 s, onto
  the SIGKILL line.
- **Severity `major → minor`.** Production never sends SIGINT (`exec uvicorn` ⇒ PID 1;
  `docker stop`/ECS send SIGTERM; zero `StopSignal`/`stopSignal`/`stop_signal` hits
  repo-wide), and FIX-234 already defused it locally (`settings.SHUTDOWN_STOP_RUNS` verified
  `True` at HEAD under `ENV=development`).
- **Code change deferred, with a mechanical reason.** uvicorn 0.34.0's `capture_signals()`
  snapshots the original handlers and reinstalls **that snapshot** before `raise_signal`, so
  any handler the app installs is discarded — and the snapshot is taken **before our code
  exists**, because `serve()` is `with self.capture_signals(): await self._serve(...)` and
  `_serve` is what calls `config.load()`, the call that imports `app.main`. There is no
  in-process seam. The only clean alternative changes the production start command. **No
  second terminal-write path was added beside `_drain_then_cancel`.**
- **Open question answered by probe: 0 LangGraph checkpoint writes after a cancel** (both
  `astream_events` and `ainvoke`; 5 writes total, all before). Sub-claim (b) stays latent —
  now by measurement.

## Cost framing, corrected and independently verified

Measured read-only from `backend/dev.db`: ceiling **37,327,891 tokens / $7.07** (run
`6e38b9a7`); the `d5dbc9f2` incident **$3.58**, ≈**$1.61 (45%)** after the cancel; all **14**
metered runs total **78,203,819 tokens / $17.75**; cache reads are 35.8M of the largest run's
37.3M. **A correctness-and-trust defect first, a cost defect second** on Haiku — about an
order of magnitude worse on an Opus-tier model.

## Money-rule compliance

No run launched, resumed, cancelled or gate-approved. Port **8010 never signalled** (pid
1848, uptime predating the session). Nothing started on port 8099; no long-lived process
started at all. `dev.db` snapshotted before and re-verified after: 21 runs, status sha256
`ed90b0bb1c036eecdf544f1f2ba309635e999a68c94007291fe9aba7176fa504`, 233,574 `run_events` —
unchanged, with run `41f77342` still `waiting_for_user`.
