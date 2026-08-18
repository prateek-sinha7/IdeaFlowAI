---
id: 260812-syf
title: "ISS-097 — the fan-out review gate nobody could see"
status: complete
date: 2026-08-12
branch: bugfix/spec-revision-context-loss
base_head: eb12bc7e8fee4ef137ae2338032747048b2091bc
code_commit: 91a1a1fa
fix_id: FIX-242
test_id: TEST-026
closes: [ISS-097]
files: [ISS-129, ISS-130, ISS-131, ISS-132]
severity_change: "ISS-097 major -> critical"
---

# Outcome

**ISS-097 is CLOSED by FIX-242 / TEST-026 (commit `91a1a1fa`), and its severity was RAISED
`major` → `critical`.** The row's predicted consequence was wrong in the direction that
matters: not N visible gates, but an invisible, unresolvable hang on a shipped user-facing
feature.

## What was wrong

`gate_agent_ids` was designed as a per-**step** selection — the UI's own words are "Checked
agents pause the pipeline for your review after they finish" — but `_should_gate` implements
it as a per-**invocation** predicate on `spec.id`. Identical readings until fan-out made one
step produce N invocations of one agent id (`agent: self` resolves to `step.agent_id`).

Every worker's `review_gate_ready` was then consumed and **discarded** by `run_fanout`'s
worker loop, which reads only `agent_complete` for token accounting and forwards nothing. So
zero gate frames reached the SSE stream, zero rows reached durable `run_events`,
`derive_open_gate` returned `(None, None)`, and the run stopped dead with
`workflow_runs.status` = `waiting_for_user` indefinitely. All N workers shared ONE gate key
`f"{run_id}:{agent_id}"` — N arms of one slot, not N gates.

**Measured at `eb12bc7e`** (`sample_wave`, single-wave plan, 4 workers,
`gate_agent_ids=["sample-wave-worker"]`): `_run_review_gate` entered **4×**, **1** gate key,
**0** frames on the wire, **HUNG** at the 20 s timeout. Control with `[]` completes.

Reachable and sticky: the gate picker lists every pipeline agent with no filter, the visual
composer's fan-out toggle is one click away in the same launch UI, and a saved workflow
replays `gateAgentIds` on every subsequent launch.

## The fix

One keyword-only invocation-scope flag, `invocation_gated`, threaded from the two kernel sites
that create invocations which are **not steps** — `run_worker` and `run_merge_agent` — through
`run_agent` into `_run_agent`, reaching all three inline gate sites. The existing predicate is
**narrowed in place** (`return invocation_gated and selected`, both original branches verbatim)
— INV-12: one predicate, no parallel rule, nothing superseded left behind. Default `True`, so
every step-shaped invocation is byte-unchanged.

Rejected and recorded so they are not retried: reading `step.gates` (the worker reuses the
**parent step object, gates included**, for `agent: self` with no isolated workspace); parking
the flag on `ExecutionContext` (N workers share one `ectx` under `asyncio.gather` — it would
race); renaming worker agent ids (breaks `_spec_for`, `allowed_workers`, fragment provenance,
the wave resume cursor).

## Proof

- **RED first**, then **re-proven by mutation** after the tests reached their final shape:
  removing the two opt-outs turned 3 of 4 tests red, the hang test reporting `4 gate arm(s) on
  ['sample-wave-worker'], 0 review_gate_ready frame(s) on the wire`.
- **The harness lies unless un-shadowed.** `make_engine` shadows `_run_review_gate` with an
  instance attribute; with the `del` removed the identical test passes **GREEN in 1.07 s**
  against a live 4-arm hang — measured, and the reason this was nearly filed "not reachable".
- `test_gate_stub_signature_drift.py` rejected a first attempt that patched the gate at CLASS
  level with an unbindable signature; the test was rewritten to the file's instance-patch
  idiom with `*a, **kw`. The guard is green.

## Baselines — before → after (all vs `eb12bc7e`)

| gate | before | after |
|---|---|---|
| goldens | 10 passed | **10 passed, 0 of 15 golden files moved** (sha256-identical) |
| `lint-imports` (from `backend/`) | 4 kept / 0 broken | **4 kept / 0 broken** |
| `test_restart_resume.py` | 64 passed | **66 passed** (+2 new) |
| `test_fanout_cancel.py` | 9 passed | **9 passed** (FIX-232 undisturbed) |
| `test_rest_gate_commands.py` | 28 passed | **28 passed** |
| 7 fan-out suites | 108 passed | **109 passed** (+1 new) |
| 12 seam-adjacent suites | — | **93 passed** |
| `test_gate_stub_signature_drift.py` | 4 passed | **4 passed** |
| 10 briefed pre-existing-red suites | 27 failed / 159 passed | **identical ID set** |
| 5 seam-adjacent reds | 5 failed / 38 passed @ `eb12bc7e` (detached worktree) | **5 failed / 38 passed, same ids** |

Goldens are the **neutrality** gate only: `_scripted_model.py:649` is literally
`gate_agent_ids=[],  # suppress all gates`, so no golden contains a gate event and none could
ever have detected this. INV-3 is argued from the flag's default-`True` dormancy.

Live verification deliberately not run — the offline harness reproduces the full defect path
through the real kernel at zero model spend.

## Filed, not folded

| id | sev | what |
|---|---|---|
| **ISS-129** | major | `run_fanout` swallows *every* worker event including `agent_error` / `pipeline_cancelled` — the amplifier; that half is still live |
| **ISS-130** | minor | `run_agent` mutates shared `ExecutionContext` scratch under parallel fan-out; believed safe only because the scratch is consumed before `_run_agent`'s first `await` — **believed, not verified** |
| **ISS-131** | minor | this fix's own residual: a fan-out step's *declared* human gate is now deduped against an inline gate that no longer fires |
| **ISS-132** | minor | the task-loop sibling — N *visible* sequential gates on one key; suppressing it is a product decision |
