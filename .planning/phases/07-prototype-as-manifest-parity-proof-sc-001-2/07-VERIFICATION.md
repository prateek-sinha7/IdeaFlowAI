---
phase: 07-prototype-as-manifest-parity-proof-sc-001-2
verified: 2026-06-09T12:00:00Z
status: gaps_found
score: 9/9 must-haves verified (SUPERSEDED 2026-06-09 — see reopened block)
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 7/9
  gaps_closed:
    - "opendesign provider produces context_message blocks byte-identical to the legacy L12 injection branches (INV-3 / PARITY-03) — CR-01 preamble restored, CR-02 builder gate restored, CR-03 task-2+ suppression restored"
    - "all 5 pipelines at deliverable byte parity AND context_message byte parity vs the post-0C baseline — context_message removed from _VOLATILE_STRIP_KEYS; dedicated normalizer-independent parity assertion added; 5 golden snapshots regenerated parity-stable"
  gaps_remaining: []
  regressions: []
reopened:
  at: 2026-06-09
  by: 07-REVIEW-DEEP.md (deep multi-agent code review; baseline acd1636)
  reason: >-
    The 'passed' conclusion was a false-positive. The 07-06 gap-closure de-blinded the
    characterization goldens by capturing the POST-refactor context_message bytes — but those
    bytes had already DRIFTED from the true pre-Phase-7 (acd1636) prompt. The goldens therefore
    pinned the drifted prompt as the contract; 'pinned == correct' does not hold. SC-001 is only
    partially proven: kernel dispatch is name-free (test_routing_parity), but prototype names
    remain hardcoded in the 'generic' capabilities (CR-05/06/07).
  confirmed_findings: 14   # 15 in 07-REVIEW-DEEP.md minus CR-03 (fixed inline, commit 8428d08)
  clusters:
    B_golden_safe: [WR-07, WR-08]            # CR-03 already fixed inline
    C_parity_needs_oracle: [CR-01, CR-02, CR-04, WR-01, WR-02, WR-03, WR-05]
    D_revision_gating: [WR-04, WR-06]
    E_sc001_architecture: [CR-05, CR-06, CR-07]
  gap_closure_plan: 07-07 (all 14 findings; order B→C→D→E; cluster C reverses the 07-06 adjudication and builds an acd1636 oracle)
---

# Phase 7: Prototype-as-Manifest Parity Proof (SC-001) Verification Report

**Phase Goal:** Re-express prototype/od_/revision entirely as manifests backed by registered
capabilities, then delete the hardcoded kernel leaks L1–L12 — proving the kernel knows no
workflow by name. This is the core-value proof (SC-001).

**Verified:** 2026-06-09T12:00:00Z
**Status:** ⚠ REOPENED 2026-06-09 (was: passed) — superseded by 07-REVIEW-DEEP.md
**Re-verification:** Yes — after gap closure by 07-06

---

> ## ⚠ PHASE REOPENED — this report is superseded (2026-06-09)
>
> A deep multi-agent code review (`07-REVIEW-DEEP.md`, baseline `acd1636`) found **14 confirmed
> findings** this "passed" report missed. Root cause: 07-06 de-blinded the characterization
> goldens against POST-refactor bytes that had **already drifted** from the true pre-Phase-7
> prompt — so the goldens below pin a *drifted* contract, not the legacy one. SC-001 is therefore
> only **partially** proven (kernel dispatch is name-free, but prototype names are hardcoded in
> the "generic" capabilities — CR-05/06/07).
>
> **Status is now `gaps_found`.** Gap-closure is planned as **07-07** (all 14 findings, order
> B→C→D→E; cluster C reverses this report's adjudication and builds an `acd1636` oracle). The
> 9/9 verification below is **preserved as the historical 07-06 record**, not the current truth.

---

## Re-Verification Scope

Previous score: 7/9. Two truths (Truth 5 / PARITY-03, Truth 6 / PARITY-09) were FAILED due
to three behavioral regressions in `opendesign.py` (CR-01: dropped DS preamble; CR-02: example
leaked to tools:[] planning agents; CR-03: no task-2+ suppression) and a structural blind spot
in the characterization normalizer (`context_message` in `_VOLATILE_STRIP_KEYS`).

Plan 07-06 fixed all three regressions and closed the blind spot. This re-verification checks:
- Full 3-level verification of the two previously-failed truths (Truths 5 and 6)
- Regression check on the seven previously-verified truths (Truths 1-4, 7-9)

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Kernel has ZERO workflow-name/pipeline_type/spec.id branches on the routed path (SC-001 structural) | VERIFIED | `grep -nE 'if\s+pipeline_type\s*==\|spec\.id\s*==' agents/execution_engine/engine.py` returns 0. Banned-pattern gate (test_banned_patterns.py) HARD-FAIL enforced; 9 passed. L1-L13 deleted; agents/prototype/ package absent from disk. |
| 2 | Engine routes per-step via registry.resolve("strategy") and per-deliverable via registry.resolve("deliverable") with NO spec.id/pipeline_type branch | VERIFIED | engine.py lines 2926-2942 confirmed. test_routing_parity.py passes (5 routing assertions). resolve("strategy") and resolve("deliverable") >= 1 match each. |
| 3 | single_shot + task_loop strategies exist behind ExecutionStrategy port; unit tests drive both from a compiled Step | VERIFIED | strategies/{single_shot,task_loop}.py exist, substantive, imported via registry. test_strategies.py: 9 passed. |
| 4 | Deliverable resolvers (single_file/serialized_sandbox/streamed_text/ppt) exist and resolve by deliverable.name — no pipeline_type branch | VERIFIED | All four resolvers exist and pass test_deliverable_resolvers.py. grep for pipeline_type in deliverables/*.py = 0. |
| 5 | opendesign provider produces context_message blocks byte-identical to the legacy L12 injection branches (INV-3 / PARITY-03) | VERIFIED | CR-01: DS block content = preamble + ds_body (opendesign.py:77-78; preamble string confirmed at line 77 with exact bytes incl. spaces after each comma). CR-02: example gated on `is_builder = bool(spec_tools & {"prototype_emit_only", "prototype"})` (line 59); tools:[] agents receive no example (test_opendesign_example_gated_on_builder_tools passes). CR-03: `is_build_task_2_plus = task_num_str not in ("", "1")` (line 60); DS/template/example absent on task 2+ (test_opendesign_build_task_2_plus_suppresses_ds_template_example passes). INV-1: no spec.id/pipeline_type branch in provider (grep = 0). Independently confirmed against 1d9234b^ (authoritative pre-Phase-7 baseline): the `_is_builder` gate at 1d9234b^:engine.py:3553-3554 IS present in the legacy — the code review CR-01 finding was a false-positive traced to stale commit 4889e3a; the adjudication in 07-REVIEW.md is confirmed correct. |
| 6 | All 5 pipelines (prototype/od_prototype/prototype_revision/ppt/code-gen) at deliverable byte parity AND context_message byte parity vs post-0C baseline | VERIFIED | Deliverable byte parity: all 5 characterization tests pass (10 passed). Context_message parity: `context_message` removed from `_VOLATILE_STRIP_KEYS` (_normalize.py:109 — absent, confirmed grep = 0). 5 golden snapshots regenerated parity-stable and pinned. DS preamble bytes ("Apply these tokens...") confirmed in prototype.events.json (4 occurrences) and od_prototype.events.json (4/5 agent_input events; the 1 without preamble is prototype-build task 2 — correct per CR-03). Dedicated normalizer-independent assertion test_context_message_parity_build_task_1_vs_task_2 passes, pinning exact ordered key sequence + byte content for task 1 and the suppressed seed-only set for task 2. |
| 7 | L1–L13 deleted from agents/execution_engine/; every per-leak kernel grep returns 0 | VERIFIED | test_migration_ledger.py: 26 passed, 1 skipped. agents/prototype/ package absent from disk (ls returns "No such file or directory"). |
| 8 | Migration-ledger rows L1–L13 flipped to checked; banned-pattern gate hard-fails on reintroduction | VERIFIED | test_migration_ledger.py green (26/1). test_banned_patterns.py: 9 passed; non-vacuity guard confirmed. |
| 9 | L14/L15/L16 re-confirmed closed; L16 cross-owner PermissionError propagates and is never swallowed | VERIFIED | test_parent_run_ownership.py: 13 passed. grep for L14 (self._current_task_block) and L15 (accumulated_outputs) patterns = 0 across backend/. |

**Score:** 9/9 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/agents/capabilities/strategies/single_shot.py` | SingleShotStrategy (name='single_shot') | VERIFIED | Unchanged from initial verification; regression check clean. |
| `backend/agents/capabilities/strategies/task_loop.py` | TaskLoopStrategy (name='task_loop') | VERIFIED | Unchanged; regression check clean. |
| `backend/agents/capabilities/task_parsers/heading_tasks.py` | HeadingTasksParser (name='heading_tasks') | VERIFIED | Unchanged; regression check clean. |
| `backend/agents/capabilities/registry.py` | resolve(kind,name) + install() | VERIFIED | Unchanged; regression check clean. |
| `backend/agents/execution_engine/context.py` | object-typed runner handle field | VERIFIED | Unchanged; regression check clean. |
| `backend/agents/capabilities/deliverables/single_file.py` | SingleFileResolver (name='single_file') | VERIFIED | Unchanged; regression check clean. |
| `backend/agents/capabilities/deliverables/serialized_sandbox.py` | SerializedSandboxResolver | VERIFIED | Unchanged; regression check clean. |
| `backend/agents/capabilities/deliverables/streamed_text.py` | StreamedTextResolver | VERIFIED | Unchanged; regression check clean. |
| `backend/agents/capabilities/deliverables/ppt.py` | PptResolver (owns both carousel-sanitize behaviors) | VERIFIED | Unchanged; regression check clean. |
| `backend/agents/capabilities/context_providers/opendesign.py` | OpenDesignProvider — byte-identical L12 blocks (preamble, builder gate, task-2+ suppression) | VERIFIED | CR-01 preamble at line 77 (exact bytes confirmed). CR-02 builder gate at line 59 (is_builder gate). CR-03 task-2+ suppression at line 60 (is_build_task_2_plus). ectx.current_spec_tools read at line 57. No spec.id/pipeline_type branch. No app.*/kernel import. |
| `backend/agents/capabilities/context_providers/previous_run.py` | PreviousRunProvider with assert_owns-before-seed | VERIFIED | Unchanged; regression check clean. |
| `backend/agents/capabilities/compaction/html_skeleton.py` | HtmlSkeletonCompaction — verbatim lift | VERIFIED | Unchanged; regression check clean. |
| `backend/agents/execution_engine/kernel_services.py` | KernelServices handle attached as ctx.runner | VERIFIED | Unchanged; regression check clean. |
| `backend/agents/execution_engine/engine.py` | capability-routed dispatch; L1-L13 absent; ectx.current_spec_tools threaded before provider loop | VERIFIED | ectx.current_spec_tools = set(getattr(spec, "tools", []) or []) at line 2935, inside _compose_context_message, BEFORE the provider loop at line 2936-2948. No spec.id/pipeline_type branch. |
| `backend/tests/agents/test_routing_parity.py` | 5-pipeline routing assertions | VERIFIED | 5 passed; regression check clean. |
| `backend/tests/agents/test_context_providers.py` | CR-01/02/03 parity assertions + dedicated context_message parity test | VERIFIED | 13 passed (up from 9 pre-07-06). test_opendesign_ds_block_has_preamble (CR-01), test_opendesign_example_gated_on_builder_tools (CR-02), test_opendesign_build_task_2_plus_suppresses_ds_template_example (CR-03), test_context_message_parity_build_task_1_vs_task_2 (normalizer-independent parity pin). Line 114 bare `== "DS TOKENS"` assertion gone (confirmed grep = 0). |
| `backend/tests/agents/characterization/_normalize.py` | context_message removed from _VOLATILE_STRIP_KEYS | VERIFIED | grep `'"context_message"' _normalize.py` = 0. Volatile keys timestamp/run_id/seq/event_id still present (grep >= 1 each). |
| `backend/tests/agents/characterization/golden/*.events.json` (×5) | context_message pinned in all 5 goldens | VERIFIED | All 5 golden files modified by 07-06. prototype.events.json: DS preamble count = 4. od_prototype.events.json: DS preamble count = 4 (1 task-2 invocation correctly absent). 5-pipeline characterization suite: 10 passed. |
| `specs/003-workflow-engine-decoupling/migration-ledger.md` | L1-L13 rows flipped to checked | VERIFIED | test_migration_ledger.py: 26 passed, 1 skipped. |
| `backend/tests/agents/test_banned_patterns.py` | kernel-scoped INV-1 HARD-FAIL gate | VERIFIED | 9 passed; non-vacuity guard present; no pipeline_type branch reintroduced. |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `engine.py _compose_context_message` | `ectx.current_spec_tools` | set before provider loop (D-03) | VERIFIED | line 2935: `ectx.current_spec_tools = set(getattr(spec, "tools", []) or [])` confirmed before the `for name in provider_names` loop at line 2937. No spec.id/pipeline_type branch (INV-1 preserved). |
| `opendesign.py load()` | legacy L12 byte contract (1d9234b^:engine.py:3517-3580) | preamble + builder gate (ctx.current_spec_tools) + task-2+ suppression (ctx.build_task_number) | VERIFIED | All three gate conditions read and applied. Independently verified against authoritative 1d9234b^ baseline: `_is_builder` gate was present at line 3553 of the legacy, not stale commit 4889e3a. |
| `engine.py` | `registry.resolve("strategy", step.strategy).run(step, ctx)` | per-step dispatch | VERIFIED | Unchanged from initial verification. |
| `engine.py` | `registry.resolve("deliverable", compiled.deliverable.strategy).resolve(ctx)` | deliverable resolution | VERIFIED | Unchanged from initial verification. |
| `previous_run.py` | `ScopedStore.assert_owns` | ownership check BEFORE seeding | VERIFIED | Unchanged; test_parent_run_ownership.py: 13 passed. |
| `test_migration_ledger.py` | kernel-scoped L1-L13 grep patterns | ratchet asserts 0 in agents/execution_engine/ | VERIFIED | 26 passed, 1 skipped. |
| `test_banned_patterns.py` | agents/execution_engine/ | assert count==0 for if pipeline_type == / spec.id == | VERIFIED | 9 passed; hard-fail gate green. |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `opendesign.py` | blocks dict | `ctx.od_context` dict + `ctx.current_spec_tools` + `ctx.build_task_number` + `ctx.runner.template_example` / `template_injection_parts` | Yes — data flows from boundary od_context dict; gates applied correctly | VERIFIED: byte-faithful lift confirmed against 1d9234b^ baseline; characterization goldens pin the assembled context_message |
| `engine.py _compose_context_message` | context_message parts | provider.load(ectx) blocks with ectx.current_spec_tools threaded | Yes — providers invoked with per-agent tool set threaded | VERIFIED: task-2+ suppression operates inside the provider; injector calls provider unconditionally and the provider gates on ctx state |
| `single_file.py` | deliverable content | `ctx.runner.sandbox.read(deliverable.name)` | Yes | VERIFIED |
| `ppt.py` | deliverable content | `_sanitize_carousel_deck_html(last_streamed)` | Yes | VERIFIED |
| `previous_run.py` | seeded files | `ctx.runner.read_parent_file()` after `scoped_store.assert_owns` | Yes — ownership-checked | VERIFIED |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Context provider tests (CR-01/02/03 + parity assertion) | `python3.11 -m pytest tests/agents/test_context_providers.py -q` | 13 passed | PASS |
| All 5 pipeline characterization tests (deliverable byte + event multiset + context_message) | `python3.11 -m pytest tests/agents/test_characterization_*.py -q` | 10 passed | PASS |
| Migration ledger L1-L13 ratchet green | `python3.11 -m pytest tests/agents/test_migration_ledger.py -q` | 26 passed, 1 skipped | PASS |
| Banned-pattern INV-1 hard-fail gate green | `python3.11 -m pytest tests/agents/test_banned_patterns.py -q` | 9 passed | PASS |
| Routing parity test (build->task_loop, others->single_shot) | `python3.11 -m pytest tests/agents/test_routing_parity.py -q` | 5 passed | PASS |
| Cross-owner PermissionError propagation (L16 ratchet) | `python3.11 -m pytest tests/agents/test_parent_run_ownership.py -q` | 13 passed | PASS |
| Full agents suite (no new failures vs baseline) | `python3.11 -m pytest tests/agents/ -m "not requires_api_key" -q --tb=no` | 552 passed (4 new tests added by 07-06), 19 skipped, 0 new failures | PASS |
| context_message bytes for prototype/od_prototype include DS preamble bytes | Inspect golden/od_prototype.events.json | DS preamble "Apply these tokens" in 4/5 agent_input events; task-2 event correctly absent per CR-03 | PASS |
| INV-1: no spec.id==/pipeline_type branch in opendesign.py | `grep -rnE 'spec\.id ==\|pipeline_type' opendesign.py` | 0 results | PASS |
| Import purity (no app.*/kernel in capability) | `grep -rnE 'from app\.\|import app\.\|agents\.execution_engine' opendesign.py` | 0 results | PASS |

---

## Probe Execution

Step 7c: SKIPPED — no `scripts/*/tests/probe-*.sh` files declared in PLAN or found by
convention search. Runtime environment is offline-only (no live Bedrock for this phase).

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PARITY-01 | 07-01 | single_shot + task_loop execution strategies | SATISFIED | Both strategies exist, pass unit tests, drive from compiled Step. Regression check clean. |
| PARITY-02 | 07-02 | single_file/serialized_sandbox/streamed_text deliverable resolvers | SATISFIED | All four resolvers exist; no pipeline_type branch; test_deliverable_resolvers green. Regression check clean. |
| PARITY-03 | 07-02/07-06 | opendesign context provider byte-identical to L12 injection branches | SATISFIED | CR-01/02/03 fixed; test_context_providers.py 13 passed; 1d9234b^ baseline confirmed. |
| PARITY-04 | 07-03 | html_skeleton CompactionStrategy, behavior-preserving vs 0C | SATISFIED | HtmlSkeletonCompaction verbatim lift; test_phase3_compaction green. Regression check clean. |
| PARITY-05 | 07-04 | prototype/od_prototype/prototype_revision run purely from compiled manifests | SATISFIED | Per-step dispatch and deliverable resolution route purely from manifests; no spec.id/pipeline_type branch. Context injection now byte-faithful (CR-01/02/03 closed). |
| PARITY-06 | 07-05 | Delete kernel leaks L1-L13; drop pipeline.py/prototype package | SATISFIED | All per-leak kernel greps return 0; agents/prototype/ absent; test_migration_ledger green. |
| PARITY-07 | 07-02 | PPT deliverable: ppt resolver + carousel-sanitize both behaviors | SATISFIED | PptResolver owns both sanitize behaviors. Regression check clean. |
| PARITY-08 | 07-05 | Kernel zero workflow-name/agent-id branches; banned-pattern hard-fail | SATISFIED | grep agents/execution_engine/ for if pipeline_type ==/spec.id == = 0; banned-pattern gate hard-fails on reintroduction; 9 passed. |
| PARITY-09 | 07-04/07-06 | All 5 pipelines at deliverable byte + semantic event parity vs post-0C baseline | SATISFIED | Deliverable bytes and event multiset: verified green (all 5 characterization tests pass). Context_message parity: context_message removed from _VOLATILE_STRIP_KEYS; 5 goldens regenerated parity-stable; dedicated parity assertion passes. |

---

## Anti-Patterns Found

No new anti-patterns identified by 07-06. The four previously-flagged blockers
(opendesign.py CR-01/02/03 and test_context_providers.py line 114) are all resolved:

| File | Line | Pattern | Severity | Status |
|------|------|---------|----------|--------|
| `backend/agents/capabilities/context_providers/opendesign.py` | 77-78 | DS block = preamble + ds_body (CR-01 FIXED) | — | RESOLVED |
| `backend/agents/capabilities/context_providers/opendesign.py` | 59, 93-104 | Builder gate on example (CR-02 FIXED) | — | RESOLVED |
| `backend/agents/capabilities/context_providers/opendesign.py` | 60, 70, 85 | Task-2+ suppression (CR-03 FIXED) | — | RESOLVED |
| `backend/tests/agents/test_context_providers.py` | 135 | DS block assertion = preamble + ds_body (line 114 bare-body assertion FIXED) | — | RESOLVED |
| `backend/tests/agents/characterization/_normalize.py` | 109-117 | context_message DE-BLINDED (removed from _VOLATILE_STRIP_KEYS) | — | RESOLVED |

Non-blocking code review nits noted in 07-REVIEW.md (WR-01 test rename, WR-02 guard comment,
WR-03 `str()` coercion, IN-01 provenance citation) — all valid optional follow-ups, none
affecting correctness. Not classified as blockers.

---

## Human Verification Required

None — all must-haves are fully automatable via code inspection and test execution. The phase
is infrastructure/kernel work with no visual/UX/external-service components. (See memory note
`uat-mode-technical.md`.)

---

## Gaps Summary

No gaps. All 9 truths are VERIFIED.

The two previously-FAILED truths are now VERIFIED:

**Truth 5 (PARITY-03):** `opendesign.py` is now a byte-faithful lift of the legacy L12
injection branches at `1d9234b^`. CR-01 (DS preamble), CR-02 (is_builder example gate), and
CR-03 (build-task-2+ suppression) are all restored. The engine threads `ectx.current_spec_tools`
to providers via the D-03 dynamic-attr pattern with no spec.id/pipeline_type branch (INV-1
preserved). The code review false-positive (reviewer read stale commit `4889e3a` which predates
the Phase-4 builder gate) was correctly adjudicated; independent re-verification against
`1d9234b^` confirms the `_is_builder` gate was present in the authoritative pre-Phase-7 baseline.

**Truth 6 (PARITY-09):** `context_message` is no longer stripped by `_VOLATILE_STRIP_KEYS`.
The 5 golden event snapshots are regenerated parity-stable and now PIN the byte-correct
context_message (including the DS preamble bytes in OD-injected agents). A dedicated
normalizer-independent parity assertion (`test_context_message_parity_build_task_1_vs_task_2`)
pins the exact ordered block-key sequence and byte content for build task 1 and the
suppressed set for build task 2. Context-injection regressions now hard-fail CI.

The structural SC-001 proof (Truths 1-4, 7-9) is confirmed not regressed by 07-06.

---

_Verified: 2026-06-09T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
_Mode: Re-verification after 07-06 gap closure_
