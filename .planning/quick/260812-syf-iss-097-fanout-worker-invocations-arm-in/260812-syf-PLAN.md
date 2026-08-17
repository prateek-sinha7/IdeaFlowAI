---
id: 260812-syf
title: "ISS-097 — fan-out worker invocations arm invisible inline review gates"
status: in-progress
date: 2026-08-12
branch: bugfix/spec-revision-context-loss
base_head: eb12bc7e8fee4ef137ae2338032747048b2091bc
severity: critical
---

# ISS-097 — a gated fan-out step hangs the run at a gate nobody can see

## Defect (verified at HEAD `eb12bc7e`)

`_should_gate` (`engine.py:4908-4925`) is a per-**invocation** predicate on `spec.id`,
but `gate_agent_ids` is a per-**step** selection ("checked agents pause the pipeline
after they finish"). Those readings were identical until fan-out made one step produce
N invocations of one agent id.

A self×N fan-out therefore arms N inline gates, all on the ONE gate key
`f"{run_id}:{agent_id}"` (`engine.py:5705`). Worse: `fanout.py:414-429` consumes every
worker event and forwards **nothing** (it reads only `agent_complete` for token
accounting), so **zero** `review_gate_ready` frames reach the emit boundary, **zero**
rows land in durable `run_events`, `derive_open_gate` returns `(None, None)`, and the
run stops dead at a HITL pause the user cannot see, discover or resolve —
`workflow_runs.status` reads `waiting_for_user` indefinitely.

Measured RED on `sample_wave` (single-wave plan, 4 workers,
`gate_agent_ids=["sample-wave-worker"]`): **4 gate arms, 0 frames on the wire, run
hung at the 20 s timeout.**

Reachable through the shipped builder-composed fan-out (Phase 51): the gate picker
lists every pipeline agent with no filter and the composer's fan-out toggle is one
click away in the same UI; a saved workflow replays `gateAgentIds` on every launch.

## Fix — one keyword-only invocation-scope flag

`invocation_gated: bool = True`, threaded from the two kernel sites that create
non-step invocations into the one predicate:

| file | change |
|---|---|
| `engine.py::_should_gate` | keyword-only `invocation_gated=True`; narrow the existing predicate in place (`invocation_gated and selected`) — INV-12, no second predicate |
| `engine.py::_run_agent` | keyword-only `invocation_gated=True`; forwarded to all three inline `_should_gate` sites (`:3440` restart re-entry, `:3556` revision re-open, `:4492` live post-stream) |
| `kernel_services.py::run_agent` | keyword-only `invocation_gated=True`; forwarded to `_run_agent` |
| `kernel_services.py::run_worker` | passes `invocation_gated=False` — a worker is an invocation, not a step |
| `kernel_services.py::run_merge_agent` | passes `invocation_gated=False` — identical invisible-hang shape (events consumed with a bare `pass`) |

Default `True` ⇒ every non-worker path is byte-unchanged (INV-3, argued from dormancy,
not from goldens — `_scripted_model.py:649` drives all 10 goldens with
`gate_agent_ids=[]`, so no golden contains a single gate event).

SC-001/INV-1: no agent-name literal, no workflow-name literal, no workflow-type branch.
`gate_agent_ids` stays the generic discriminator; the flag is stamped by a structural
call site, exactly like the existing `redoable` / `update_specs_eligible` booleans.

### Designs rejected (do not retry)

- **`_should_gate` reads `step.gates`** — cannot work: `kernel_services.py:992-993`
  reuses the **parent step object, gates included**, whenever the worker is
  `agent: self` with no isolated workspace. Also a different mechanism (step-boundary
  `_evaluate_gates`) and would be the dual implementation INV-12 forbids.
- **Park the flag on `ExecutionContext`** — N workers share one `ectx` under
  `asyncio.gather`; a save/restore boolean would race.
- **Rename worker agent ids** — breaks `_spec_for`, `allowed_workers`, fragment
  provenance and the wave resume cursor.

## Tasks

1. **Test first, RED.** Add `test_fanout_workers_do_not_arm_the_inline_review_gate` +
   `test_selecting_a_non_fanout_agent_still_opens_its_inline_gate` to
   `tests/agents/test_restart_resume.py`. **Both must `del engine._run_review_gate`** —
   `make_engine` (`:360-365`) installs an empty async generator as an *instance*
   attribute that silently shadows the real method; without the `del` the test passes
   green in ~1 s while the defect is fully present (proven by experiment).
2. **Apply the flag** across the five sites in the table above.
3. **Verify.** New tests GREEN; every baseline re-measured before *and* after.

## Baselines (measured at `eb12bc7e`, before any edit)

| gate | before |
|---|---|
| goldens (5 characterization files) | **10 passed**, 15 golden files hashed |
| `lint-imports` (from `backend/`) | **4 kept / 0 broken** |
| `tests/agents/test_restart_resume.py` | **64 passed** |
| `tests/agents/test_fanout_cancel.py` | **9 passed** |
| `tests/unit/test_rest_gate_commands.py` | **28 passed** |
| fan-out suites (sc001 / composed / sample_wave / fanout / merge_conflict / budget / isolation) | **108 passed** |

## Out of scope — file, do not fold

- The **task-loop sibling**: ticking a task-loop agent gives N *visible* sequential
  gates on one key (real but lesser; partly known via ISS-090).
- The **blanket worker-event swallow** at `fanout.py:414-429` — the amplifier that
  turns a gate into an invisible hang.
- The **shared-`ectx` scratch mutation** under parallel fan-out
  (`kernel_services.py:1254-1291`) — believed safe only because `_run_agent` consumes
  the scratch before its first `await`; undocumented and fragile.
- The **declared-gate dedupe residual**: `engine.py:2470` passes
  `inline_gated=self._should_gate(spec, ectx)` at the step boundary. Post-fix a
  fan-out step whose agent is ticked AND which declares `gates:[human]` would dedupe
  its declared gate against an inline gate that no longer fires. Left byte-unchanged
  deliberately (INV-3); correcting it needs the strategy to declare whether it runs
  its agent inline, which the kernel must not infer from a strategy-name list.
