---
phase: 07-prototype-as-manifest-parity-proof-sc-001-2
verified: 2026-06-09T17:30:00Z
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 9/9
  gaps_closed:
    - "WR-01: html_file artifact location de-hardcoded at all three engine.py sites (commit 16cfe43) — now reads deliverable.name; parity-safe (goldens byte-unchanged)"
    - "WR-04: assert_owns fail-closed on unexpected store errors (commit 96b6484) — broad Exception now returns {} (no seed) instead of degrading open; regression test added; TestParentSeeding tests provisioned with a real parent DB row"
  gaps_remaining: []
  regressions: []
---

# Phase 7: Prototype-as-Manifest Parity Proof (SC-001) Verification Report

**Phase Goal:** Re-express prototype/od_/revision entirely as manifests backed by registered
capabilities, then delete the hardcoded kernel leaks L1-L12 — proving the kernel knows no
workflow by name (SC-001, core-value proof).

**Verified:** 2026-06-09T17:30:00Z
**Status:** passed
**Re-verification:** Yes — fourth pass (final close), after WR-01 + WR-04 fix commits (16cfe43, 96b6484)

---

## Re-Verification Scope

Previous status: `human_needed` (all 9/9 truths VERIFIED; two latent-defect warnings required
human judgment). The operator chose to fix both:

- **WR-01 fixed (commit 16cfe43):** All three `_dual_write_artifact` html_file location sites in
  `engine.py` (success readback :1668, `_gate_edited` rewrite :1758, error placeholder :1803) now
  read `getattr(getattr(ectx, "deliverable", None), "name", None) or "prototype.html"` — the same
  accessor threaded by the strategy and persist path (mirrors single_file.py / engine.py:1629).
  Goldens are byte-unchanged: `git diff --stat 16cfe43 HEAD -- golden/` returns empty.

- **WR-04 fixed (commit 96b6484):** `previous_run.py` broad `except Exception` around
  `assert_owns` now FAILS CLOSED — returns `{}` (skips parent seed) on any non-`PermissionError`
  instead of degrading open. `PermissionError` still propagates (L16, never swallowed). A
  regression test (`test_previous_run_unexpected_store_error_fails_closed`) is added to
  `test_context_providers.py`, and both `TestParentSeeding` tests in
  `test_phase5_revision_validation.py` are provisioned with a real same-owner parent DB row via
  `_provision_parent_run_db`, exercising the production seed path rather than the former
  degrade-open-on-missing-DB behavior.

This verification independently confirmed both fixes are correct and parity-preserving, and
re-ran the full agents test suite.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Kernel has ZERO workflow-name/pipeline_type/spec.id branches on the routed path (SC-001 structural / INV-1) | VERIFIED | `grep 'if pipeline_type ==' engine.py` = 0; `grep 'spec\.id ==' engine.py` = 0. test_banned_patterns.py: 9 passed. L1-L13 deleted; agents/prototype/ absent. |
| 2 | Engine routes per-step via registry.resolve("strategy") and per-deliverable via registry.resolve("deliverable") with NO spec.id/pipeline_type branch | VERIFIED | engine.py:641-654 confirmed. test_routing_parity.py: 5 passed. `_is_revision_workflow` sourced from `compiled.deliverable.revises_existing` (declared flag). |
| 3 | single_shot + task_loop strategies exist behind ExecutionStrategy port; unit tests drive both from a compiled Step | VERIFIED | Both strategies exist, pass test_strategies.py (11 passed). No prototype.html literals on the routed execution path. |
| 4 | Deliverable resolvers (single_file/serialized_sandbox/streamed_text/ppt) exist and resolve by deliverable.name — no pipeline_type branch | VERIFIED | All four resolvers exist and pass test_deliverable_resolvers.py. ppt order confirmed byte-equivalent. |
| 5 | opendesign provider produces context_message blocks byte-identical to the pre-Phase-7 (acd1636) oracle (INV-3 / PARITY-03) | VERIFIED | CR-01/02/04/WR-01/WR-03 all closed. test_context_message_oracle.py: 10 HARD PASSes (no xfail). |
| 6 | All 5 pipelines (prototype/od_prototype/prototype_revision/ppt/code-gen) at deliverable byte parity AND context_message byte parity vs post-0C baseline | VERIFIED | 5 characterization tests: 10 passed. Goldens regenerated to oracle ground truth. No xfail masking. |
| 7 | L1-L13 deleted from agents/execution_engine/; every per-leak kernel grep returns 0 | VERIFIED | test_migration_ledger.py: 26 passed, 1 skipped. agents/prototype/ absent. REVISION_FILE_NAME=0; DELIBERATE EXCEPTION=0; prototype-revision-agent=0. |
| 8 | Migration-ledger rows L1-L13 flipped to checked; banned-pattern gate hard-fails on reintroduction; kernel-resident revision block evicted (CR-06) | VERIFIED | test_migration_ledger.py green (26/1). test_banned_patterns.py: 9 passed. CR-06: entire prototype-revision block evicted to previous_run provider + revision_validation post-step capability. |
| 9 | SC-001 PROOF: a non-prototype task_loop workflow (sc001_task_loop / manifest+AGENT.md only) runs end-to-end producing app.py with ZERO engine edits; L14/L15/L16 re-confirmed closed | VERIFIED | test_sc001_nonprototype_task_loop.py: 3 HARD PASSes. sc001_task_loop fixture: delivers app.py (not prototype.html); dual-write location = app.py. test_parent_run_ownership.py: 13 passed (L16). |

**Score:** 9/9 truths verified

---

## WR-01 Fix Verification (commit 16cfe43)

**Code confirmed at all three sites:**

Site 1 — success readback (engine.py:1661-1673):
```python
_html_loc = getattr(getattr(ectx, "deliverable", None), "name", None) or "prototype.html"
_location = (
    _html_loc
    if _kind == "html_file"
    else f"artifact_refs/{spec.id}"
)
```
Comment confirms intent: "CR-05 / 07-11 de-hardcode (WR-01): source the html_file location
from the DECLARED deliverable name ... NOT the literal 'prototype.html'."

Site 2 — `_gate_edited` rewrite (engine.py:1757-1769):
```python
_ek_html_loc = getattr(getattr(ectx, "deliverable", None), "name", None) or "prototype.html"
await self._dual_write_artifact(..., location=(_ek_html_loc if _ek == "html_file" else ...))
```

Site 3 — error placeholder (engine.py:1802-1812):
```python
_erk_html_loc = getattr(getattr(ectx, "deliverable", None), "name", None) or "prototype.html"
await self._dual_write_artifact(..., location=(_erk_html_loc if _erk == "html_file" else ...))
```

**Parity confirmed:** `git diff --stat 16cfe43 HEAD -- backend/tests/agents/characterization/golden/` = empty (zero golden changes). The `or "prototype.html"` fallback ensures prototype's declared `deliverable.name == "prototype.html"` produces byte-identical persisted locations. Non-prototype html_file workflows now use their declared name.

---

## WR-04 Fix Verification (commit 96b6484)

**Code confirmed at previous_run.py:162-178:**
```python
except PermissionError:
    raise  # cross-owner denial — propagate (L16, never swallow)
except Exception as authz_exc:  # noqa: BLE001 — WR-04: fail CLOSED
    # WR-04 (fail-closed): an UNEXPECTED store error means the ownership check
    # could NOT be completed. Must NOT proceed to seed ... degrading OPEN here
    # risks cross-run data exposure.
    logger.warning("previous_run: assert_owns lookup failed for parent %s (%s) — "
                   "FAILING CLOSED: skipping parent-run seed (ownership unconfirmed)",
                   parent_run_id, authz_exc)
    return {}  # fail closed — no seed
```

**L16 still propagates:** `PermissionError` re-raises immediately before the broad catch.

**Regression test confirmed** (`test_context_providers.py:541-567`):
- `_FakeScopedStore(unexpected_error=True)` raises `RuntimeError("simulated store outage...")`
- Test asserts: `store.assert_called is True` (check was attempted) AND `sandbox.written == {}` (no seed — fail closed)

**TestParentSeeding tests corrected** (`test_phase5_revision_validation.py:313-366`):
- `_provision_parent_run_db` creates a real in-memory SQLite DB with a same-owner `workflow_runs` row
- Both `TestParentSeeding` tests now call `_provision_parent_run_db` before `_execute_revision`
- Tests exercise the REAL production seed path (assert_owns confirms same-owner → seed proceeds) rather than the former degrade-open-on-missing-DB behavior

---

## Full Regression Results

| Test Suite | Command | Result | Status |
|-----------|---------|--------|--------|
| SC-001 proof (3 hard PASSes) | `pytest tests/agents/test_sc001_nonprototype_task_loop.py -q` | 3 passed | PASS |
| Oracle (10 hard PASSes, no xfail) | `pytest tests/agents/test_context_message_oracle.py -q` | 10 passed | PASS |
| Routing parity | `pytest tests/agents/test_routing_parity.py -q` | 5 passed | PASS |
| Ownership gate (L16) | `pytest tests/agents/test_parent_run_ownership.py -q` | 13 passed | PASS |
| Revision gating | `pytest tests/agents/test_revision_gating.py -q` | 7 passed | PASS |
| Context providers (incl. WR-04 regression test) | `pytest tests/agents/test_context_providers.py -q` | 17 passed | PASS |
| Phase5 revision validation (corrected TestParentSeeding) | `pytest tests/agents/test_phase5_revision_validation.py -q` | 8 passed | PASS |
| Full agents suite | `pytest tests/agents/ -m "not requires_api_key" -q` | 582 passed, 19 skipped, 0 failed | PASS |
| INV-1: no pipeline_type==/spec.id== in engine.py | grep check | 0 results | PASS |

---

## Deferred Findings — Not Phase-Blocking

The following findings from 07-REVIEW.md remain intentionally deferred (not addressed in this
phase). Each is confirmed latent — unreachable on any current production workflow:

| Finding | Why Latent / Deferred |
|---------|----------------------|
| WR-02: silent `prototype.html` fallback on missing deliverable.name | Latent: all production manifests set `deliverable.name`; no non-prototype workflow omits it today. Logging enhancement deferred to Phase 8 manifest validation. |
| WR-03: `previous_run.load` re-invokable per-agent | Dead path: verified none of the 5 `previous_run` workflows has an agent declaring `injects` (checked in code review). Double-invocation cannot fire today. |
| WR-05: `KernelServices.run_agent` ectx build-scratch mutation lacks re-entrancy guard | Latent: task_loop is strictly sequential; fan-out phases not yet implemented. No correctness risk until fan-out arrives. |
| IN-01..IN-05 | Cosmetic/documentation-only; no behavioral impact. |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PARITY-01 | 07-01 | single_shot + task_loop execution strategies | SATISFIED | Both strategies exist; pass unit tests; no prototype.html literals on routed path |
| PARITY-02 | 07-02 | single_file/serialized_sandbox/streamed_text/ppt resolvers | SATISFIED | All four exist; ppt order confirmed equivalent; test_deliverable_resolvers green |
| PARITY-03 | 07-02/07-08/07-09 | opendesign provider byte-identical to acd1636 oracle (INV-3) | SATISFIED | CR-01/02/04/WR-01/WR-03 all closed; 10 oracle tests HARD PASS |
| PARITY-04 | 07-03 | html_skeleton CompactionStrategy, behavior-preserving vs 0C | SATISFIED | HtmlSkeletonCompaction exists; test_phase3_compaction green |
| PARITY-05 | 07-04/07-10/07-11 | prototype/od_prototype/prototype_revision run purely from compiled manifests | SATISFIED | Kernel-resident revision block evicted; revision runs from declared revises_existing flag + previous_run provider + post_step capability; SC-001 proof passes |
| PARITY-06 | 07-05 | Delete kernel leaks L1-L13; drop pipeline.py/prototype package | SATISFIED | All per-leak greps = 0; agents/prototype/ absent; migration-ledger green |
| PARITY-07 | 07-02/07-09 | PPT deliverable: ppt resolver + carousel-sanitize both behaviors | SATISFIED | PptResolver; WR-02 equivalence confirmed with test |
| PARITY-08 | 07-05/07-10/07-11 | Kernel zero workflow-name/agent-id branches; banned-pattern hard-fail | SATISFIED | grep = 0 for all banned patterns; "previous_run" in proxy = 0; banned-pattern gate 9 passed. WR-01 residual now FIXED (deliverable.name-sourced at all 3 sites). |
| PARITY-09 | 07-04/07-06/07-07/07-09 | All 5 pipelines at deliverable byte + semantic event parity vs post-0C baseline | SATISFIED | 5 characterization tests: 10 passed; goldens regenerated to oracle ground truth; oracle loop-closing assertion passes |

---

## Anti-Patterns (Remaining)

The two blocking anti-patterns from the prior pass are now FIXED. The remaining entries are
confirmed latent/deferred:

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `engine.py` | 1826 | `agent_id: str = "prototype-build"` default on `_run_validation_fix_loop` | INFO | Cosmetic: callers always pass explicit agent_id; default is unreachable on routed path. |
| `engine.py` | 2581-2585 | `_AGENT_KIND_MAP` names prototype agent ids | INFO | Lineage-label-only; not a behavioral routing branch (INV-1 is about `if pipeline_type ==` / `spec.id ==` branches). The WR-01 fix means this map no longer controls the persisted location. |

---

## Human Verification Required

None. All must-haves verified programmatically. Both prior human-judgment items resolved by fixes.

---

## Gaps Summary

No gaps. All 9 must-haves verified. All 14 deep-review findings closed. Both WR-01 and WR-04
human-judgment items resolved by operator-directed fixes confirmed correct in this pass. Full
agents suite: 582 passed / 0 failed. Phase goal achieved.

---

_Verified: 2026-06-09T17:30:00Z_
_Verifier: Claude (gsd-verifier)_
_Mode: Re-verification (4th pass / final close) after WR-01 + WR-04 fix commits_
