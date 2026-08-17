---
id: 260812-fbk
slug: fix-iss-074-live-harness-review-gate-wra
date: 2026-08-12
status: in-progress
issue: ISS-074
branch: bugfix/spec-revision-context-loss
base_commit: fab9b646
---

# Quick 260812-fbk — ISS-074: live-harness review-gate wrapper signature drift

## Problem

`backend/tests/agents/live_harness.py:672` defines the auto-resume wrapper with a stale
four-parameter signature and installs it over `engine._run_review_gate` at `:683`
(unconditionally — even when `auto_resume_gates=False`). The engine's real method
(`engine.py:5594-5606`) takes **ten** parameters, and **four** call sites pass them all by
keyword: `engine.py:3397`, `:3504`, `:4440`, and `kernel_services.py:1116` (the declared
`gates:[human]` / `approval` delegate). Result: `TypeError`.

The observable damage is worse than a crash: the `TypeError` is swallowed by the engine's
per-agent error handler, so a gated harness drive reports `gated=False, completed=True` —
a **false-green HITL verification harness**.

Red since `f18de868` (2026-06-30), when `redoable` landed. 43 days invisible because
`.planning/TEST-REGISTER.md:85` excludes offline suites by **filename** (`anything *_live*`),
and both affected files are offline-safe despite their names.

The ISS-074 row claims the defect is "UNVERIFIABLE offline". That is **refuted** — five
offline tests are red at HEAD in ~2s with no credentials.

## The trap

`**kwargs` on the `def` **alone** turns all five tests green while silently discarding all six
extra arguments — including `cancel_event` (a gate that cannot honour Stop) and
`redoable` / `update_specs_eligible` (the SC-001 name-free discriminators). Both tokens are
load-bearing: the `def` **and** the forwarded call.

## Tasks

1. **Part 2 first** — add forwarding assertions to
   `test_live_harness.py::TestEngineGate::test_gate_on_pauses_then_auto_resumes_to_complete`
   that read `redoable` / `update_specs_eligible` off the `review_gate_ready` payload. Written
   BEFORE the fix so they cannot be shaped to match it. These are what reject the def-only
   shadow fix.
2. **Part 1** — new `backend/tests/agents/test_gate_stub_signature_drift.py`: AST-derives the
   engine's real `_run_review_gate` signature (never hand-copied), resolves every stub that
   substitutes it (assignment stubs, factory-returned stubs, and **class-based** stubs such as
   `test_gates.py:920` that the assignment census misses), and asserts
   `inspect.Signature.bind` succeeds against the full real call. Fails loudly on any stub it
   cannot resolve — never silently skips.
3. **The fix** — two tokens in `live_harness.py` (`**kwargs` on def @672 and on the forward
   @673). Keep the four named parameters: the body reads `pipeline_run_id` / `agent_id` by
   name at `:677`.
4. **Widen the one class-based stub** — `_FakeReviewEngine._run_review_gate`
   (`test_gates.py:920`) pins 5 of 10 params with no `**kwargs`; strictly widening it is
   required for the Part-1 guard to be green and closes the same latent hazard.
5. **Part 3 (the actual root cause)** — register both offline-safe suites in
   `.planning/TEST-REGISTER.md` §1.6 and correct the filename-based `*_live*` avoid-rule that
   hid them.

## Proof obligations

- Fail-before captured verbatim (5 failed / 3 passed).
- Part-1 guard observed RED at HEAD before the fix.
- After: 8 passed / 0 failed.
- Guard proven to catch the **next** drift: temporarily add a throwaway parameter to the engine
  signature, observe the guard go red naming every affected stub, revert.
- Def-only shadow fix proven rejected by the Part-2 assertions.
- Invariants unchanged: characterization goldens **10 passed** with no golden file modified
  (INV-3); `lint-imports` **4 kept / 0 broken** run from `backend/`.
- Known pre-existing reds unchanged: `test_gates.py` 3, `test_declared_gate_streaming.py` 3,
  `test_wire_parity.py` 4 failed / 2 passed.

## Constraints

- Test-only. **No production module edits** (Ports & Adapters untouched).
- No live/Bedrock run, no browser, no prototype launch.
- Never `git stash`; never loosen or delete a failing test; never regenerate a golden.

## Out of scope — file as new ISS rows, do not fold in

- `test_gates.py` 3 reds: `_Ectx`/`_Ctx` **attribute** drift (`artifacts`, `gate_agent_ids`).
  Same family, but the drifting surface is an attribute, so the Part-1 guard cannot catch it.
- `test_declared_gate_streaming.py` 3 reds: IMPLEMENTATION-REGISTER calls them
  "3 env-reds (sqlite FK, Postgres-gated)", but the observed failures are assertions that a
  declared human gate never fired and that a gate rejection did not cancel the run. File the
  symptom mismatch; do not root-cause here.
