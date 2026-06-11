---
phase: 13-live-verification-gap-closure
plan: 05
subsystem: execution-engine
tags: [revision, fr-014, artifact-refs, deliverable, gap-closure, f2]
requires:
  - "13-01 (gate streaming branch in _evaluate_gates — engine.py diff base)"
  - "05-06 (visibility=workspace producer-write policy for cross-run reads)"
provides:
  - "kind='deliverable' member of the ARTIFACT_KINDS closed vocabulary"
  - "completion-time deliverable artifact_ref persist in execute() terminal block"
  - "FR-014 fallback lookup chain (exact -> deliverable -> summary) in _handle_revision"
  - "FE-exact run_revision regression test against an organically-persisted parent"
affects:
  - "13-06 (all-agents-failed hardening — the deliverable write is guarded out of that path)"
tech-stack:
  added: []
  patterns:
    - "generic-kind fallback chain (no workflow literal in the kernel, SC-001)"
    - "organic-persistence regression test (drive public execute(), seed nothing)"
key-files:
  created:
    - backend/tests/unit/test_run_revision_fe_contract.py
  modified:
    - backend/agents/artifacts/graph.py
    - backend/agents/execution_engine/engine.py
    - backend/tests/unit/test_revision_intelligence.py
decisions:
  - "Deliverable persist guarded on `final_output and results` — no write on empty deliverable or zero completed agents (keeps the all-agents-failed path 13-06 hardens write-free, and characterization streams byte/event-identical)"
  - "producer_agent for the completion ref = ordered_agents[-1].id (generic position, not a literal); producer_step='deliverable'"
  - "version_history is the MATCHED chain link's refs list, not unconditionally the exact-kind list"
  - "Chain-link resolution surfaced as ONE INFO log (target kind, resolved kind, ref id) — no new WS event, stream parity held"
metrics:
  duration: ~8 min
  tasks: 3
  files: 4
  completed: 2026-06-11
---

# Phase 13 Plan 05: run_revision FE Contract Gap Closure (F2) Summary

Completion-time `kind="deliverable"` artifact_ref + a 3-link FR-014 fallback chain (exact → deliverable → summary) so the FE's exact `run_revision` payload (`ppt_output`/`od_ppt_output`) resolves against both new and pre-fix completed runs — zero workflow literals in the kernel.

## What was done

### Task 1 — Persist a deliverable-kind artifact_ref at run completion (6276c92f)

- Added `"deliverable"` to the `ARTIFACT_KINDS` closed vocabulary in `backend/agents/artifacts/graph.py` (with a comment naming its 13-05/F2 role).
- In `ExecutionEngine.execute()`'s terminal block — after the deliverable resolver (and its streamed_text fallback) and before the `pipeline_complete` yield — the run's resolved `final_output` is dual-written as `kind="deliverable"`, `producer_step="deliverable"`, `producer_agent=ordered_agents[-1].id` (fallback literal `"deliverable"` when empty), `location="artifact_refs/deliverable"`, `visibility="workspace"` (05-06 policy so the same-owner cross-run `_handle_revision` read passes the owner+visibility scope filter).
- Guard: `if final_output and results:` — a run with no completed agents or an empty deliverable writes nothing.
- SC-001: the only new literal is the generic kind `"deliverable"`; the revision-side write (`kind=target_artifact_type`) untouched, so revision-of-revision keeps working via chain link 1.

### Task 2 — FR-014 fallback lookup chain in `_handle_revision` (a76dad36)

- Replaced the single exact-kind lookup with a deterministic chain, `assert_owns` staying FIRST (T-5-SEED untouched):
  1. exact `target_artifact_type` kind (preserves revision-of-revision + existing exact-kind tests)
  2. `kind="deliverable"` (the Task-1 completion ref — every NEW run)
  3. `kind="summary"` (pre-fix legacy runs: the final agent's output under the `_AGENT_KIND_MAP` fallback)
- All links empty → the FR-014 `ValueError`, byte-unchanged (greps exactly once in engine.py). Latest-by-version stays `_refs[-1]`.
- `version_history` is the matched link's refs list. One INFO log names the resolving link; no new WS event.

### Task 3 — De-masked seed tests + FE-exact regression test (f0474384)

- `test_revision_intelligence.py`: kept all exact-kind tests (now chain link 1 coverage) and added a realistic-persistence block seeding what the run path ACTUALLY persists (per-agent `summary` refs + `planning_context` + optional `deliverable`):
  - (a) FE target `"ppt_output"` + deliverable ref → proceeds, resolves the deliverable content
  - (b) same parent WITHOUT the deliverable (legacy) → summary fallback resolves the latest-version (final agent) summary; `version_history` proven to be the matched link's list ("2 version(s) exist")
  - (c) planning_context-only parent → FR-014 `ValueError` still raises (guard not weakened)
  - (d) cross-owner replay of (a) → `PermissionError` propagates (L16)
- New `backend/tests/unit/test_run_revision_fe_contract.py`: completes a scripted `od_ppt` run end-to-end through the PUBLIC `execute()` against a monkeypatched in-memory SQLite (so the ScopedStore writes persist instead of degrading), then calls `_handle_revision` with the FE-exact frame (`target_artifact_type="od_ppt_output"`). Asserts: no `state_restoration_failed`; exactly one `pipeline_complete` with `pipeline_type == "od_ppt_output_revision"`; the revision context embeds the parent deliverable. The parent deliverable ref is produced ORGANICALLY by the run path — the file contains no manual `kind="deliverable"` seed (grep-verified 0). Chain-link log confirmed `resolved_kind='deliverable'`.

## Verification results

| Check | Result |
|-------|--------|
| `tests/unit/test_revision_intelligence.py` (10 existing + 4 de-masked) | 14 passed |
| `tests/unit/test_run_revision_fe_contract.py` | 1 passed (resolves via the deliverable link) |
| `tests/agents/test_characterization_prototype_revision.py` | passed, no golden re-baseline |
| `tests/agents/test_characterization_prototype.py` + `test_characterization_od_ppt.py` | passed, no golden modified |
| `tests/unit/test_artifact_store.py` | passed |
| `/opt/homebrew/bin/lint-imports` | 4 contracts kept, 0 broken |
| SC-001: `grep -r "ppt_output\|od_ppt_output" agents/execution_engine/` | 0 matches |
| FR-014 message byte-unchanged (greps exactly once in engine.py) | confirmed |

## Deviations from Plan

None - plan executed exactly as written. (No test pinned the exact set of refs a completed run persists, so the Task-1 step-4 expectation-extension was a no-op.)

## Known Stubs

None — the `_handle_revision` body's pre-existing "Phase 3: store the instruction + context as the revision artifact" placeholder (no DeepAgent revision loop) predates this plan and is out of its scope; this plan's contract (FR-014 resolution + revision proceed) is fully wired.

## Threat Flags

None — no new surface beyond the plan's `<threat_model>`: T-13-05-01 mitigated (assert_owns first + cross-owner test d), T-13-05-02/03 accepted per register.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 6276c92f | feat(13-05): persist a deliverable-kind artifact_ref at run completion (F2) |
| 2 | a76dad36 | fix(13-05): FR-014 fallback lookup chain in _handle_revision (F2) |
| 3 | f0474384 | test(13-05): de-mask revision seeds + FE-exact run_revision regression (F2) |

## Self-Check: PASSED

- backend/tests/unit/test_run_revision_fe_contract.py — FOUND
- Commits 6276c92f / a76dad36 / f0474384 — FOUND
