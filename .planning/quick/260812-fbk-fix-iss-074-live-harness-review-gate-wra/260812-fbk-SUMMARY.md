---
id: 260812-fbk
slug: fix-iss-074-live-harness-review-gate-wra
date: 2026-08-12
status: complete
issue: ISS-074
fix_id: FIX-231
test_id: TEST-015
filed: [ISS-094, ISS-095, ISS-096]
branch: bugfix/spec-revision-context-loss
base_commit: fab9b646
commits:
  - 3def9d1a  # test(agents): signature-drift guard (red, fail-before evidence)
  - f36c3a07  # fix(tests): forward the engine's gate kwargs (green)
---

# Summary — quick 260812-fbk (ISS-074)

## What was wrong

`tests/agents/live_harness.py:672` pinned `_run_review_gate`'s four-parameter shape from
2026-06-11 and installed the wrapper over `engine._run_review_gate` at `:683`
unconditionally. The engine takes **ten** parameters and **four** call sites pass them all by
keyword — `engine.py:3397`, `:3504`, `:4440`, and `kernel_services.py:1116` (the declared
`gates:[human]` / `approval` delegate, which the ISS-074 row missed). Every gated harness
drive raised `TypeError`.

The engine's per-agent error handler swallowed it, so the run reported
`gated=False, completed=True`: a **false-green HITL verification harness**, not a crash.
Red since `f18de868` (2026-06-30, `redoable`) — 43 days.

## The row's central claim was wrong

ISS-074 said the defect is "UNVERIFIABLE offline". Refuted: five offline tests were red at
HEAD in ~2s with no credentials and no Bedrock spend. The blocker was never credentials — it
was **coverage selection**. `.planning/TEST-REGISTER.md:85` excluded offline suites by
**filename** ("anything `*_live*`"), and both affected files are offline-safe:
`test_live_harness.py` has no module skip at all, and `test_phase8_live.py` gates only
`TestLiveHITL`/`TestLivePipelines`, leaving `TestOfflineHITL` ungated.

## What was done

1. **Part 2 first (red before the fix)** — forwarding assertions in
   `TestEngineGate::test_gate_on_pauses_then_auto_resumes_to_complete` reading
   `redoable`/`update_specs_eligible` off the `review_gate_ready` payload.
2. **Part 1** — new `tests/agents/test_gate_stub_signature_drift.py` (4 tests). AST-derives
   the engine's real parameter list, resolves every substitute for the method — monkeypatched
   names, factory-returned inner functions, and **class-based** doubles the assignment census
   cannot see — and asserts `inspect.Signature.bind` succeeds. Unresolvable stubs fail rather
   than skip; two floor tests plus a self-test keep it from degrading to a vacuous pass.
3. **The fix** — `**kwargs` on the wrapper's `def` **and** on the forwarded call.
4. **Widened `_FakeReviewEngine._run_review_gate`** (`test_gates.py:920`), which pinned 5 of
   10 with no `**kwargs` and was one forwarded parameter from the identical failure.
5. **Part 3, the actual root cause** — registered both offline-safe suites and the guard in
   `TEST-REGISTER.md` §1.6, and replaced the filename heuristic with "check the actual skip
   marks". Also recorded that `lint-imports` must run from `backend/` or it prints
   "Could not read any configuration" and reads as a false pass.

## Evidence

| Measurement | Before | After |
|---|---|---|
| `test_live_harness.py::TestEngineGate` + `test_phase8_live.py::TestOfflineHITL` | **5 failed, 3 passed** | **8 passed, 0 failed** |
| `test_gate_stub_signature_drift.py` | 1 failed, 2 passed (named both stubs) | **4 passed** |
| `test_live_harness.py` + `test_phase8_live.py` (newly registered) | — | 34 passed, 16 skipped |
| Characterization goldens (INV-3) | 10 passed | **10 passed** |
| Golden files modified | — | **0** |
| `lint-imports` (from `backend/`) | 4 kept, 0 broken | **4 kept, 0 broken** |
| Production modules modified | — | **0** |

Fail-before cause, verbatim:
`TypeError: drive_engine_pipeline.<locals>._auto_resume_review_gate() got an unexpected keyword argument 'redoable'`

**Both tokens proven load-bearing.** Def-only shadow fix measured: guard **3 passed** (arity
is blind to it) but the Part-2 assertion fails `assert False is True` on `redoable` — and
only **1 failed / 7 passed**, i.e. the shadow fix greens the entire pre-existing suite.

**Guard proven against the NEXT drift.** A throwaway stub pinning today's exact ten
parameters plus a temporary 11th engine parameter → guard RED naming
`_drift_probe_tmp.py:10` and `cannot accept: ['throwaway_drift_probe']`. Control: engine
reverted, probe retained → green. Both the probe and the engine edit were removed;
`git status` confirms 0 production modules changed.

Known pre-existing reds unchanged: `test_gates.py` 3 failed/39 passed,
`test_declared_gate_streaming.py` 3 failed, `test_wire_parity.py` 4 failed/2 passed.

## Bookkeeping

Allocated from the four-source sweep (register + card store + `git log --all` + card files):
**FIX-231**, **TEST-015**, **ISS-094/095/096**. Note the repo carries two disjoint `TEST-*`
namespaces — `FIX-TEST-REGISTER.md` uses zero-padded `TEST-0NN` (max 014), while
`.knowledge/cards/TEST-NN.md` is a separate series sourced from `TEST-REGISTER.md` (max 49).
Taking the naive max across both would have burned `TEST-050`.

## Findings filed separately (not fixed here)

- **ISS-094** — `test_gates.py` 3 reds, `_Ectx`/`_Ctx` **attribute** drift. Same family,
  different surface; the arity guard cannot catch it. Acknowledged in prose on the ISS-078 row
  but had no row of its own.
- **ISS-095** — `test_declared_gate_streaming.py` 3 reds. IMPLEMENTATION-REGISTER:4075 calls
  them "3 env-reds (sqlite FK, Postgres-gated)", but the observed failures assert a declared
  human gate never fired and a gate rejection did not cancel the run. Symptom mismatch; a
  mislabelled "environmental" red is how ISS-074 survived 43 days.
- **ISS-096** — `test_prompt_contracts.py::test_od_ppt_validator_deck_reemission_contract`,
  stale prompt pin (`"exactly ONE <artifact>"` no longer in the `od-ppt-validator` body). Found
  while sweeping `live_harness` consumers; **reproduced at `fab9b646` in a clean detached
  worktree**, so pre-existing and unrelated.

## Deferred

A real Bedrock gated drive through the repaired wrapper. Nothing downstream of the gate has
executed in a live harness drive since 2026-06-30, so further live-only rot may sit behind
this one. Belongs to the end-of-milestone live pass — **not** an `od_prototype` build; a
`user_stories` gated drive is the cheap probe.
