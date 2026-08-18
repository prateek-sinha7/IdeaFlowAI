---
id: 260812-g1c
slug: iss-091-gate-reject-stops-pipeline
description: "ISS-091 — a review-gate rejection now STOPS the run instead of executing every remaining step and reporting completion"
date: 2026-08-12
status: complete
issue: ISS-091
branch: bugfix/spec-revision-context-loss
base_commit: c0bbb6e2
commits:
  - 4f058f9a  test(agents): a gate rejection must stop the run (ISS-091, red)
  - 3f37bea4  fix(engine): a review-gate rejection terminates the run (ISS-091)
  - 6df1f1a0  fix(engine): the fan-out boundary honours run terminality, not just Stop (ISS-091)
---

# Summary — ISS-091

## What was wrong

Rejecting at an inline human review gate emitted `pipeline_cancelled` and then let
**every remaining step run**, terminating on `pipeline_complete`.

Two-part root cause, both confirmed at `c0bbb6e2`:

1. `engine.py:2523` — the dispatch loop observed **only** `agent_error`. The gate's
   reject handler cancels the run, yields `pipeline_cancelled` and `return`s, but a
   generator `return` only ends *that step*; the terminal event was forwarded and
   ignored and the outer per-step loop advanced.
2. `engine.py:2381` — the only step-boundary termination check reads `cancel_event`,
   and a gate rejection sets none. (This is why FIX-227 was orthogonal.)

**The severity was never token spend.** Every post-rejection worker short-circuits on
`_run_agent`'s terminal guard (`:3329`) and bills nothing. The damage was the *durable
record*: each no-op worker was written `subagent_runs.status='complete'` and each wave
`wave_runs.status='completed'`, and `wave_scheduler.py:251-256` skips completed waves on
resume. Reject → restart → resume therefore skipped every wave, produced **zero** files,
and recorded the run `completed` — silent, permanent loss of a fan-out run's entire
output, on a live user-facing feature (Phase 51 builder-composed fan-out).

## What changed

**Primary** — `engine.py:2523-2530`. A terminal-event observation symmetric to the
existing `agent_error` one, ending in `return`. It is the exact sibling of the
declared-gate handler **WR-03** (`:2454-2479`), whose own comment describes this defect
verbatim: the declared path stopped the run, the inline path did not.

`return`, not `break` — `break` falls through to the Step-5 terminal block which still
emits `pipeline_complete`. Flag-then-return rather than breaking mid-generator, so the
producer's `finally` blocks keep their normal path.

**Secondary** — `fanout.py::_check_cancel` + a new `KernelServices.is_run_terminal()`.
Widens the *single existing* fan-out cancel boundary to consult run terminality as well
as `cancel_event`. Deliberately **not** in `wave_scheduler.py`: a capability may not
import the execution kernel (import-linter), a check there would need a new port, and it
would be a second cancel implementation (INV-12) that still missed `fanout_batch` and the
`spawn_subagents` tool.

## Rejected alternatives

| Shortcut | Why rejected |
|---|---|
| `break` instead of `return` | Falls through to Step 5 and still emits `pipeline_complete`. |
| Make the gate rejection call `cancel_event.set()` | Inverts app/kernel ownership of `_CANCEL_EVENTS`; flips the outer `except asyncio.CancelledError` re-raise decision FIX-227 depends on; double-emits. |
| Guard Step 5 on terminal state only | Fixes the event, not the work — the data loss is untouched. |
| "Nothing runs anyway, so it's cosmetic" | Refuted by the resume data loss: the no-op guard is precisely what turns a wasted run into an unrecoverable one. |
| Degrade `is_run_terminal()` defensively | Would make broken engine wiring read as "not terminal", hiding the bug class the check exists to catch. The under-specified thing was two test doubles, which were completed instead. |

## Proof

| | Before (`c0bbb6e2`) | After |
|---|---|---|
| Events after the cancel | 17, terminal `pipeline_complete` | **0**, terminal `pipeline_cancelled` |
| `wave_runs` | `[(0,'completed'),(1,'completed')]` | `[]` |
| `subagent_runs` | 4 x `'complete'` (tokens `None`) | `[]` |
| Reject → restart → resume | files `[]`, worker calls `{}`, run `completed` | `part_a/b/c/d.txt`, worker calls `{a:2,b:2,c:2,d:2}` |
| Stop mid-wave (probe 3) | honoured | **unchanged** |

Seven tests, each seen red first with its real failure output. T1-T3 in
`test_restart_resume.py`; T4 is the WR-03 guard (green by design — its teeth proven by
deleting WR-03's `return` and watching it fail); three in `test_fanout_cancel.py` for the
secondary fix.

| Gate | Before | After |
|---|---|---|
| Characterization goldens | 10 passed, 0 files moved | **10 passed, 0 files moved** |
| `lint-imports` | 4 kept / 0 broken | **4 kept / 0 broken** |
| `test_restart_resume.py` | 60 passed | **64 passed** |
| `test_fanout_cancel.py` | 6 passed | **9 passed** |
| fan-out / wave / kernel-services / budget sweep | — | **141 passed, 3 skipped** |
| Every other real-`KernelServices` double site | — | **130 passed** |
| Known pre-existing reds | 11 failed / 54 passed | **11 failed / 54 passed, identical ids** |

**Honest limitation:** the goldens compile `gate_agent_ids=[]` (`_scripted_model.py:649`),
so no golden contains a single gate event. They **cannot** detect this change; they prove
only that nothing else moved. The seven tests are the only real oracle.

## Q1 — is an empty `wr.output` acceptable for a gate-rejected run?

**Yes, and it is not even a new row shape.** `status='cancelled'` with a null/empty
`output` is what the Stop button already produces today (`engine.py:2381-2404` returns
*before* deliverable resolution, so `_apply_terminal_output_columns` never sees a
`pipeline_complete` and `run_commands.py:2085-2086`'s `if final_output:` never fires), and
what the declared-gate reject at `:2454-2479` has always produced.

The frontend handles it deliberately, not incidentally:
`PreviewPanel.tsx:620-643` computes `showCancelledAffordance`, and `:424-432` renders
purpose-written copy — *"This run was cancelled / The run was stopped before producing a
deliverable."* `page.tsx:2367-2369` excludes `cancelled` from `isContentTerminal` **and**
truthiness-guards `fullRun.output`, so no renderer ever receives it. The history list
never receives `output` at all (`runs.py:145-176` omits it from the list schema). Existing
coverage already pins this shape: `WorkflowHistory.test.tsx:246-253` uses
`status:"cancelled", output:""`, and `e2e/tests/ts-t.history.spec.ts:37-63` seeds a
cancelled run with `output: null`.

**Behaviour change to note for the owner:** previously a rejected run published the
*rejected* artifact as its deliverable (`final_output` = the rejected planner's text).
It no longer does. That is the intended outcome, and it is user-visible in history.

## Filed, not folded

- **ISS-097** — `run_worker` builds its worker step with `gates=[]` but `_should_gate`
  reads `ectx.gate_agent_ids`, so gating a fan-out step's own agent may open an inline
  review gate in *every worker*.
- **ISS-098** — a mid-wave `CancelledError` leaves a `wave_runs` row `running`, because
  `wave_scheduler.py`'s `except Exception:` cannot catch a `BaseException`.
- **ISS-099** — with `step.retry.max_attempts > 0`, `_dispatch_step_with_retry` yields
  `step_completed` after a `pipeline_cancelled`, recording a cancelled step as reusable.
  Dormant: no shipped manifest declares `retry`.

## Invariants

- **INV-3** held — goldens 10/10, zero golden files modified.
- **INV-12** held — the primary fix *adds* a missing observation; nothing superseded, so
  nothing deleted. FIX-229's `resume_supersedes` logic was **not** touched: it still
  governs already-persisted tails and the genuine multi-attempt resume case.
- **SC-001 / INV-1** held — keyed on the generic event type; no workflow name, no
  agent-id literal, no strategy branch.
- **Ports & Adapters** held — `lint-imports` 4 kept / 0 broken; the secondary fix lives
  kernel-side precisely so no capability imports the kernel.

No live/Bedrock run, no browser, no golden regenerated, no test deleted or loosened.
