---
phase: 07-prototype-as-manifest-parity-proof-sc-001-2
reviewed: 2026-06-09T13:36:00Z
depth: standard
files_reviewed: 21
files_reviewed_list:
  - backend/agents/capabilities/base.py
  - backend/agents/capabilities/registry.py
  - backend/agents/capabilities/context_providers/opendesign.py
  - backend/agents/capabilities/context_providers/previous_run.py
  - backend/agents/capabilities/deliverables/ppt.py
  - backend/agents/capabilities/post_steps/__init__.py
  - backend/agents/capabilities/post_steps/revision_validation.py
  - backend/agents/capabilities/strategies/task_loop.py
  - backend/agents/execution_engine/context.py
  - backend/agents/execution_engine/engine.py
  - backend/agents/execution_engine/kernel_services.py
  - backend/agents/workflows/compiler.py
  - backend/agents/workflows/plan.py
  - backend/tests/agents/characterization/oracle/legacy_context_message.py
  - backend/tests/agents/test_context_message_oracle.py
  - backend/tests/agents/test_sc001_nonprototype_task_loop.py
  - backend/tests/agents/test_revision_gating.py
  - backend/agents/workflows/prototype/workflow.yaml
  - backend/agents/workflows/prototype_revision/workflow.yaml
  - backend/tests/agents/fixtures/sc001_task_loop/workflow.yaml
findings:
  critical: 0
  warning: 5
  info: 5
  total: 10
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-06-09T13:36:00Z
**Depth:** standard
**Files Reviewed:** 21 (20 in scope + heading_tasks/single_shot/_artifact/sandbox cross-referenced)
**Status:** issues_found

## Summary

The gap-closure changes (07-07..07-11) hold up well against the phase's core invariants. I traced the routed prototype/revision path end-to-end and ran the three load-bearing test suites (`test_context_message_oracle.py`, `test_revision_gating.py`, `test_sc001_nonprototype_task_loop.py`): **all 20 tests pass, with NO active `xfail`/`skip` markers masking divergence** (the only `xfail` references are in docstrings describing 07-08 history). The oracle byte-equality tests are now hard `assert ==` PASSes.

Verified positives:
- **INV-1 / SC-001 clean on the routed path.** No `spec.id == "..."` / `pipeline_type == "..."` behavioral branch survives in routed dispatch. The opendesign builder/inject gates key off the opaque tool-set + threaded injects (`current_spec_tools` / `current_spec_injects`), not a name. The revision setup keys off the declared `deliverable.revises_existing` flag (compiler.py:229), not the `previous_run`-provider proxy. `test_revision_gating.py` proves exactly one of the five `previous_run` workflows is classified in-place.
- **Oracle internal consistency.** The PINNED-BYTES blocks (DS preamble, bare END markers, RAW injection parts, skeleton wrapper, unconditional TEMPLATE COMPLIANCE) are byte-consistent with the routed `_compose_context_message` + opendesign provider assembly. The DS preamble `\n` join, the `[:8000]` + `...[truncated]` truncation, and the END-marker paren/colon stripping all match.
- **CR-02 example gate intact.** `example_html` is gated on `is_builder` (opendesign.py:111) and only emitted inside `not is_build_task_2_plus` + `"template" in injects`; planning agents (`tools=[]`) never see it. `test_oracle_planning_agents_get_no_example_html` locks it.
- **L16 ownership gate.** `assert_owns` runs before any parent read; `PermissionError` propagates and is never swallowed (previous_run.py:160-161); all other errors degrade. Test-proven.

The findings below are all latent-but-real de-hardcoding gaps and test blind spots — none currently breaks prototype parity (because every prototype default coincides with the declared value), but several directly contradict the stated CR-05 "de-hardcode" fix and would silently misbehave for the very non-prototype workflows SC-001 promises to support.

## Warnings

### WR-01: Typed-artifact `location` is still hardcoded `"prototype.html"` — CR-05 de-hardcoding incomplete

**File:** `backend/agents/execution_engine/engine.py:1661-1665`, `:1755-1759`, `:1798-1800`
**Issue:** All three `_dual_write_artifact` call sites in `_run_agent` hardcode the persisted `location` to the literal `"prototype.html"` whenever `_kind == "html_file"`, instead of reading the declared `ectx.deliverable.name`:
```python
_location = ("prototype.html" if _kind == "html_file" else f"artifact_refs/{spec.id}")
```
This is the SAME hardcoding CR-05 claims to have removed everywhere else (task_loop threads `filename`; `persist_task_html` threads `filename`). The per-agent dual-write here still pins `prototype.html`. It is currently benign only because `_AGENT_KIND_MAP` (engine.py:2584) maps `html_file` to exactly one agent id — `prototype-build` — whose declared name happens to be `prototype.html`. The sc001 fixture escapes the bug solely because `sc001-build` is unmapped and falls to `kind="summary"` → the `else` branch. A future non-prototype HTML workflow mapped to `html_file` would persist its typed artifact under the wrong location and `_latest_typed_content`/compaction lineage would diverge silently. This is why the SC-001 proof passes despite the gap — the proof never exercises an `html_file`-kinded non-prototype agent.
**Fix:** Use the declared deliverable name for the html_file location, mirroring the strategy/handle de-hardcoding:
```python
_html_loc = (getattr(getattr(ectx, "deliverable", None), "name", None) or "prototype.html")
_location = (_html_loc if _kind == "html_file" else f"artifact_refs/{spec.id}")
```
Apply at all three sites (the success readback 1661, the `_gate_edited` rewrite 1755, and the error placeholder 1798).

### WR-02: Silent `prototype.html` fallback masks a missing/misconfigured `deliverable.name`

**File:** `backend/agents/capabilities/strategies/task_loop.py:83,160`; `backend/agents/capabilities/context_providers/previous_run.py:73,236`; `backend/agents/capabilities/post_steps/revision_validation.py:36,60`; `backend/agents/execution_engine/engine.py:1629`
**Issue:** Six de-hardcoded sites all resolve the artifact filename as `getattr(deliverable, "name", None) or "prototype.html"`. The review mandate is explicit: "a missing thread should be a loud error, not a silent prototype fallback." As written, a non-prototype `task_loop`/`single_file` workflow that omits `deliverable.name` will SILENTLY build, validate, seed, and read back `prototype.html` — producing a wrong-named deliverable with no diagnostic. The docstrings justify the fallback as serving "unit-test fakes that set only `ctx.runner`," but that convenience leaks into the production path: the only thing standing between a misconfigured manifest and a silent prototype-named output is the manifest author remembering to set `name`.
**Fix:** Distinguish "no deliverable bound at all" (test fake — fallback OK) from "deliverable bound but `name` is None/empty" (real misconfiguration — should warn loudly or raise). At minimum log a `logger.warning` when a `deliverable` object IS present but its `name` is falsy, e.g.:
```python
deliverable = getattr(ctx, "deliverable", None)
name = getattr(deliverable, "name", None)
if deliverable is not None and not name:
    logger.warning("task_loop: deliverable bound but name is empty — defaulting to prototype.html (likely a manifest misconfiguration)")
filename = name or _DEFAULT_DELIVERABLE_NAME
```

### WR-03: `previous_run.load` is re-invokable per-agent and would re-seed / re-run `assert_owns`

**File:** `backend/agents/execution_engine/engine.py:2828-2840` (the per-agent provider loop) vs `:988` (`_seed_workflow_context` at run entry)
**Issue:** `previous_run.load(ctx)` has run-entry side effects (it slims `runner.user_message`, seeds the existing artifact, runs `assert_owns`, and seeds parent files). It is invoked once at run entry via `_seed_workflow_context`. But `_compose_context_message` ALSO calls `provider.load(ectx)` for every declared `context_provider` whenever the consuming agent declares any `injects` (engine.py:2828-2840). If a `previous_run`-declaring workflow ever had an agent with non-empty `injects`, `previous_run.load` would fire a SECOND time per that agent: re-running `assert_owns` (extra DB round-trip), re-seeding parent files, and re-stashing `revision_*`. The artifact re-extraction is idempotent only because the message was already slimmed (markers gone), but the re-`assert_owns` and re-seed are not free and the design relies on an undocumented coincidence.
**Why it's currently dead (not a BLOCKER):** I verified none of the five `previous_run` workflows has an agent declaring `injects` (the revision agents declare `tools: [workspace]`, no `injects`), and only `prototype_revision` even passes the `revises_existing` short-circuit. So the double-invocation cannot fire today.
**Fix:** Make the seeding side effects idempotent within a run (guard on a `ctx`-stashed `_previous_run_seeded` flag), or have `_compose_context_message` skip providers whose effect is run-entry-only. Document the contract that `previous_run.load` is run-entry-only.

### WR-04: `assert_owns` lookup swallows broad `Exception` and degrades OPEN to seeding

**File:** `backend/agents/capabilities/context_providers/previous_run.py:162-167`
**Issue:** Only `PermissionError` propagates; any OTHER exception from `scoped_store.assert_owns` (a DB error, a schema mismatch, a transient store outage, an unexpected store bug) is caught by `except Exception` and the provider then PROCEEDS to seed the parent run's spec/design/tasks ("degrading to same-owner seed"). If `assert_owns` raises a non-`PermissionError` for a reason that actually masks an authorization-relevant failure, the code degrades OPEN — it seeds parent content without a confirmed ownership check. The comment frames this as CTX-05 graceful-degrade parity, but the blast radius is cross-run data exposure, not a cosmetic degrade.
**Fix:** Narrow the swallowed set to the specific recoverable conditions (parent-run-not-found / TTL-swept) and let unexpected store errors propagate, or fail CLOSED (skip the parent seed) on any non-`PermissionError` rather than fail open. At minimum, do not perform the parent-file seed when the ownership check could not be completed.

### WR-05: `KernelServices.run_agent` mutates shared `ectx` build scratch without a re-entrancy guard

**File:** `backend/agents/execution_engine/kernel_services.py:239-271`
**Issue:** `run_agent` saves and restores `ectx.build_task_number` / `build_task_total` / `current_task_block` / `current_prototype_skeleton` around the `_run_agent` call using a save-set-finally-restore pattern on the SHARED per-run `ExecutionContext`. This is correct for sequential task loops but is not re-entrancy-safe: if a strategy ever drives two `run_agent` calls concurrently against the same `ectx` (the fan-out phases this kernel is explicitly being designed for — `ExecutionContext.depth`, `FanoutSpec`), the save/restore would interleave and clobber each other's task counters, corrupting the `=== CURRENT TASK ===` block injected into a sibling task's prompt. The `ExecutionContext` docstring (context.py:5-9) calls out exactly this INV-2 hazard for the singleton; the same hazard now exists at the build-scratch level.
**Fix:** Thread the per-task counters/block/skeleton as explicit parameters into `_compose_context_message` (via `_run_agent`) rather than stashing on the shared `ectx`, OR document and assert that `run_agent` is single-flight per `ectx` until the fan-out phases add task-local scoping. Not a blocker today (task_loop is strictly sequential), but it is a latent correctness trap directly contradicting the per-run-isolation rationale.

## Info

### IN-01: Byte-equality oracle tests are partially tautological on the planning/consumed sub-blocks

**File:** `backend/tests/agents/test_context_message_oracle.py:221-224, 269-272`
**Issue:** `test_routed_build_prompt_equals_oracle_byte_for_byte` extracts `planning_block` and `consumed_block` FROM the routed message and feeds them back into `build_oracle_message`. The full-message `assert routed[0] == oracle_t1` therefore verifies the POSITION/ordering/join-math of those blocks (genuinely useful) but NOT their internal content — drift inside the planning or consumed region would be copied into the oracle and pass. Acceptable (those regions are declared workflow-agnostic, out of cluster-C scope) but a real blind spot worth recording: the oracle proves the cluster-C contract (DS/template/example/parts/skeleton/compliance) byte-for-byte, not the agnostic regions.
**Fix:** None required for this phase; note it for the milestone-end live pass.

### IN-02: Oracle skeleton content is fed back from the routed message (not independently pinned)

**File:** `backend/tests/agents/test_context_message_oracle.py:266-281`; `backend/tests/agents/characterization/oracle/legacy_context_message.py:109-113`
**Issue:** `inner_skeleton` is sliced out of the routed task-2 message and passed to the oracle, so only the skeleton WRAPPER bytes + position are verified, not the skeleton-extraction algorithm. The oracle docstring is explicit this is intentional (the extractor is engine-internal, tested elsewhere). Recording it so a future reader does not mistake the PASS for proof of the compaction/extraction output.
**Fix:** None required; ensure `_extract_html_skeleton` retains independent coverage.

### IN-03: Dead computation — `_count_plan_tasks` result discarded

**File:** `backend/agents/capabilities/strategies/task_loop.py:193`
**Issue:** `_, _src = _count_plan_tasks(plan_output)` computes and discards both return values inside the `total_tasks == 0` branch; only the subsequent `logger.warning` runs. The call has no effect.
**Fix:** Drop the line; the warning already carries `len(plan_output)`.

### IN-04: `is_design_system_required` suppress branch is uncovered by the reviewed tests

**File:** `backend/agents/capabilities/context_providers/opendesign.py:84-87`; oracle `ORACLE_OD_CONTEXT` (`None`) vs `_HARNESS_OD_CONTEXT` (`True`)
**Issue:** The DS-inclusion gate `include_ds = True if is_deck_conditional is None else bool(is_deck_conditional)` is exercised only with `None`/`True` inputs across the reviewed tests — both include. The `False` (deck-conditional-suppress) branch is never hit. Not a defect (prototype always requires DS) but the suppress path is uncovered.
**Fix:** Optional — add a unit case feeding `is_design_system_required: False` to lock the suppress branch.

### IN-05: `test_sc001_proof_required_zero_engine_edits` docstring header overstates rigor

**File:** `backend/tests/agents/test_sc001_nonprototype_task_loop.py:35, 346-391`
**Issue:** The module docstring (line 35) describes assertion (5) as "a `git diff` containment check," but the implemented test only asserts the 5 proof artifacts exist and live outside `backend/agents/execution_engine/` — it runs no `git diff`. The test body's own docstring (348-360) is honest that the kernel WAS edited once (the de-hardcoding) and that this test checks only that the proof artifacts are test-scoped. The header sentence overstates. The substance (SC-001 proven by the end-to-end `_drive_sc001` run + `app.py` assertions) is sound.
**Fix:** Reword the module docstring line 35 to match the implemented check (artifact-location containment, not a git diff), so a future reader does not trust a guarantee the test does not provide.

---

_Reviewed: 2026-06-09T13:36:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
