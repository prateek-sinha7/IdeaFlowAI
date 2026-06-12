---
phase: 14-run-revision-real-revision-loop-f2-end-to-end
plan: 04
subsystem: tests
tags: [run_revision, real-dispatch, scripted-model, pytest, fr-014, seq-stamping, phase-gate]

# Dependency graph
requires:
  - phase: 14-run-revision-real-revision-loop-f2-end-to-end (14-01)
    provides: "planner: skip on both run_revision manifests + deterministic _scripts_for revision-agent branches (od-ppt-revision-agent / ppt-revision-agent / ppt-revision-assembler) the rewritten suite drives"
  - phase: 14-run-revision-real-revision-loop-f2-end-to-end (14-02)
    provides: WS queue dispatch + terminal-status fidelity (regression suite included in the phase-gate battery)
  - phase: 14-run-revision-real-revision-loop-f2-end-to-end (14-03)
    provides: "real execute() dispatch in _handle_revision (the contract under test) + the _dispatch_revision wiring shape this suite mirrors"
provides:
  - "Rewritten tests/unit/test_revision_intelligence.py (1032 lines, 17 tests): the SEEDED-parent matrix against the REAL dispatch — proceed-path tests drive scripted revision pipelines through _handle_revision -> execute(); zero stub semantics pinned anywhere (ROADMAP SC3 test half closed)"
  - "All 8 kept guards byte-meaning-identical (presence grep-pinned) + FR-014 message pinned byte-exact + NEW falsy-owner ValueError guard + events-empty proof on both cross-owner denials"
  - "Single-stamping regression trap: run_events asserted from execute()'s chokepoint — contiguous non-duplicated seq from 1, minted-workspace scope recovered from persisted rows (T-14-04-02)"
  - "Phase-14 gate: full targeted battery green in one session (226 passed, 7 skipped pre-existing) + lint-imports 4 kept + all SC-001/INV-3/INV-12 greps clean"
affects: [phase-14-close, run_revision, gsd-verify-work]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Suite-level division of labor: test_revision_intelligence.py owns the SEEDED-parent matrix (guards + each FR-014 chain link from hand-seeded refs); test_run_revision_fe_contract.py owns the ORGANIC-parent E2E + revision-of-revision", "Input-side contract assertions: composed-context contracts (three sections, planning prefix) asserted on the forwarded agent_input event's context_message, never on final_output"]

key-files:
  created: []
  modified:
    - backend/tests/unit/test_revision_intelligence.py

key-decisions:
  - "Proceed-path targets re-targeted from 'spec' to od_ppt_output/ppt_output only — the two flipped planner: skip manifests; any other *_output target derives a planner: run manifest and hangs at the clarify gate (RESEARCH Pitfall 1). Guard tests keep their original targets (they raise pre-dispatch)."
  - "test_planning_context_unavailable_when_no_planning_artifact renamed to test_planning_context_prefix_absent_when_no_planning_artifact: the behavior the old name described (the stub-only terminal payload key) was deleted in 14-03; what survives is the planning-prefix ABSENT/PRESENT contract on the dispatched input"
  - "run_events workspace scope recovered from the persisted rows (execute() mints the revision run's OWN workspace — never inherits the parent's); the /events endpoint mirror reads via ScopedStore(owner, minted_ws)"
  - "Expected revised-deck bytes DERIVED from _scripts_for (split on artifact tags) — the harness stays the single source; ppt_output targets assert the ASSEMBLER's deck (last agent of the 2-step ppt_revision pipeline)"

patterns-established:
  - "_dispatch_wiring contextmanager: RUNS_ROOT + dual create_runner patch (factory_mod AND engine_mod) + finally-restore, uuid4 run id per dispatch — the reusable scripted-dispatch idiom for any _handle_revision suite"

requirements-completed: [F2]

# Metrics
duration: ~13min
completed: 2026-06-12
---

# Phase 14 Plan 04: Revision intelligence suite on the real-dispatch contract + phase gate Summary

**The 792-line stub-pinning suite is rewritten to the real-dispatch contract (17 tests, all green first run): guards kept byte-meaning-identical, proceed-paths drive scripted revision pipelines through execute() and assert the three-section/planning-prefix contracts on the dispatched agent INPUT, run_events pinned at the chokepoint with the single-stamping seq trap — and the full Phase-14 targeted battery is green in one session (226 passed, lint 4 kept, all invariant greps clean), closing the 14-03 intra-phase intermediate and ROADMAP SC2/SC3 test halves.**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-06-12T12:45:03Z
- **Completed:** 2026-06-12T12:58:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- **SC3 test half closed (the documented 14-03 intermediate):** the suite no longer pins any stub semantics — no `===` section markers in `final_output`, no context-blob ref content, no deleted-payload-key assertion, no duplicate-stamping-path ledger test. RED baseline (8 failed / 8 passed) → 17 passed.
- **Guards survived byte-meaning-identical:** `test_empty_instruction_raises`, `test_whitespace_only_instruction_raises`, `test_nonexistent_artifact_raises` (FR-014 ValueError now pinned BYTE-EXACT to engine.py's f-string), `test_cross_owner_revision_denied` + `test_fe_target_cross_owner_still_denied_on_realistic_parent` (PermissionError BEFORE any event — now executable via `assert events == []`), `test_fe_target_still_raises_fr014_when_no_chain_link_matches`, `test_summary_fallback_all_error_placeholders_raises_fr014`, `test_clarifications_round_trip_via_artifact_refs`. NEW: `test_falsy_owner_raises` (AUTHZ-03 ValueError for `owner_id=None` and `""`).
- **Proceed-paths on real dispatch (SC2 test half):** `test_revision_stores_new_version_with_lineage` seeds an exact-kind parent (chain link 1), dispatches `od_ppt_revision`, and asserts the NEW exact-kind ref: `content == final_output == EXPECTED_OD_REVISED_DECK` (harness-derived, unwrapped), `derived_from ==` the seeded original id, `run_id ==` the revision run, `visibility="workspace"`, owner/workspace stamped from the original.
- **Three-section contract moved to the INPUT:** `test_revision_contains_three_separate_inputs` asserts the forwarded `agent_input.context_message` carries ORIGINAL ARTIFACT / VERSION HISTORY / REVISION INSTRUCTION in order with the seeded content and instruction INSIDE their sections; planning-prefix ABSENT/PRESENT covered by the renamed pair (prefix precedes the original-artifact section when present).
- **run_events at the chokepoint (T-14-04-02):** rows persisted for the revision run with `seq == range(1, N+1)` (contiguous, no duplicates — a reintroduced second counter fails it), terminal `pipeline_complete` row present, minted workspace recovered from the rows (never the parent's WS), run row stamped via set_run_scope, and the /events-endpoint mirror (`ScopedStore(owner, minted_ws)`) resolves + replays identically.
- **FR-014 chain proof via the dispatched input:** deliverable-link / summary-fallback / placeholder-filter tests keep the `_seed_realistic_parent` matrix and prove WHICH content resolved inside the `=== ORIGINAL ARTIFACT ===` section of the agent input (`ppt_output` → 2-step `ppt_revision`; `final_output ==` the ASSEMBLER's scripted deck); `"2 version(s) exist"` kept via the context_message.
- **Phase gate green (SC3a/SC3d):** full targeted battery — 5 characterization suites (zero golden re-baselines) + banned-patterns + migration-ledger + manifest-parity + id-alias-resolver + revision-gating + the 5 unit suites — **226 passed, 7 skipped (pre-existing)** in one 40s session; `lint-imports` 4 contracts kept / 0 broken.

## Task Commits

1. **Task 1: Rewrite the proceed-path tests onto scripted dispatch; keep every guard byte-meaning-identical** - `2f45ee54` (test)
2. **Task 2: Phase-gate battery + SC-001/INV-3 grep sweep + SC4 deferral recording** - no code changes (gate-only task: battery + greps all clean, no residue to fix; records live in this SUMMARY, committed with the plan-completion docs commit)

## Files Created/Modified

- `backend/tests/unit/test_revision_intelligence.py` - rewritten to the real-dispatch contract (1032 lines, 17 tests): `_dispatch_wiring` contextmanager + `_dispatch_revision`/`_context_message`/`_original_section` helpers, all model imports registered on Base.metadata before create_all (run_events/run_capabilities/workspaces now touched by dispatch), guards verbatim, proceed-paths re-targeted to the two dispatchable kinds.

## Phase-Gate Battery Results (Task 2)

| Suite group | Result |
|---|---|
| 5 characterization suites (prototype, od_prototype, od_ppt, app_builder, prototype_revision) | green — zero golden re-baselines (`git status --porcelain tests/agents/characterization/golden/` empty) |
| test_banned_patterns.py + test_migration_ledger.py | green |
| test_manifest_parity.py + test_id_alias_resolver.py + test_revision_gating.py | green |
| test_revision_intelligence.py (17) + test_run_revision_fe_contract.py (2) + test_run_revision_ws_dispatch.py (6) + test_run_pipeline_validation.py + test_pipeline_failure_semantics.py | green |
| **Single-session total** | **226 passed, 7 skipped (pre-existing), 40.06s** |
| /opt/homebrew/bin/lint-imports | 4 contracts kept, 0 broken |

**Invariant grep sweep:**

| Grep | Expected | Actual |
|---|---|---|
| `if pipeline_type ==` in `agents/execution_engine/` (non-comment) | 0 | 0 |
| `ppt_revision\|od_ppt_revision\|ppt_output` in kernel (non-comment code) | 0 | 0 (SC-001) |
| golden dir porcelain | empty | empty (INV-3) |
| `_stamped_send\|_rev_sink` in engine.py | 0 | 0 (INV-12) |

## Decisions Made

- Re-targeting decision and the planning-prefix rename recorded in frontmatter key-decisions (both plan-prescribed).
- Acceptance-grep interpretation: `grep -oE '"[a-z_]+_output"'` on the suite also matches `"final_output"` — the `pipeline_complete` payload KEY, not a revision target (the pre-14 suite matched it too). Proceed-path TARGETS are limited to `"ppt_output"`/`"od_ppt_output"` exactly as the criterion intends.
- Task 2's gate found no residue: no test-file fixes needed, no engine regression (nothing to re-open in 14-03 scope).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical guard coverage] Added `test_falsy_owner_raises`**
- **Found during:** Task 1
- **Issue:** the plan's must_haves truth and threat model T-14-04-01 list the falsy-owner ValueError among guards that must survive "byte-meaning-unchanged", but no such test existed anywhere in the repo (verified by grep) — the engine guard (`_handle_revision requires a real owner_id (AUTHZ-03)`) was untested.
- **Fix:** added the guard test (raises for `owner_id=None` and `""`, zero events emitted).
- **Files modified:** backend/tests/unit/test_revision_intelligence.py
- **Commit:** 2f45ee54

**2. [Rule 2 - Strengthening, kept-assertions untouched] Made two declared truths executable**
- **Found during:** Task 1
- **Issue:** (a) "cross-owner PermissionError BEFORE any event" was implicit (both cross-owner tests collected events but never checked them); (b) the acceptance criterion requires the FR-014 message assertion byte-identical to engine.py's, but the kept test only regex-matched `"No artifact"`.
- **Fix:** added `assert events == []` to both cross-owner denials; `test_nonexistent_artifact_raises` now additionally pins `str(excinfo.value)` byte-exact. All pre-existing assertions preserved unchanged.
- **Files modified:** backend/tests/unit/test_revision_intelligence.py
- **Commit:** 2f45ee54

## Deferred (live-environment items — milestone-end live pass)

Per project convention (defer-live-verification-to-milestone-end), recorded — not blocking phase close:

- **ROADMAP SC4:** FE-exact `run_revision` frame → genuinely revised deck in the preview on real Bedrock (live model + FE preview; the offline harness cannot observe real model output).
- **14-02 live cancel/reconnect:** `cancel_pipeline`/`reconnect_pipeline` during a real (minutes-long) revision model run — offline cancellation is pinned by the ws_dispatch suite's event-driven scenario (f).
- **14-01 A1 assumption:** the FE revision panel UX does not want a clarifying questionnaire on revisions (`planner: skip` is the desired product behavior, including the legacy `run_pipeline` fallback path of ppt_revision/od_ppt_revision losing its planner overlay). Confirmable on the live pass.

## Implementation Register Note

The IMPLEMENTATION-REGISTER Phase-13 "deferred feature" entry — *"the `run_revision` DeepAgent revision loop — F2 routes the revision to the FE but its deliverable is still a Phase-3 stub"* (register lines 33/35/62) — is **SUPERSEDED by Phase 14**: `_handle_revision` now dispatches the real registry revision pipeline through `execute()` (14-03) with WS queue dispatch + terminal-status fidelity (14-02), `planner: skip` manifests + scripted harness (14-01), and both suites pinning the real-dispatch contract (14-03/14-04). Flag for the register's Phase-14 entry when it is generated.

## Verification Evidence

- RED baseline confirmed pre-rewrite: 8 failed / 8 passed (exactly the 14-03 documented intermediate).
- Task 1 quick run: `test_revision_intelligence.py + test_run_revision_fe_contract.py + test_manifest_parity.py` — **51 passed** (first run, `-x -q`).
- Task 1 acceptance: all 8 kept guard names present by grep + falsy-owner guard; `planning_context_unavailable` 0 occurrences; `_stamped_send` 0; seq assertions present (10 matches); targets grep yields only `od_ppt_output`/`ppt_output` (+ the `final_output` payload key, see Decisions); 1032 lines (>= 500).
- Task 2: battery 226 passed / 7 skipped in one session; lint-imports 4 kept / 0 broken; all four invariant greps clean (table above).

## Next Phase Readiness

- Phase 14 is complete on offline evidence: SC1 (engine+WS halves, 14-02/14-03), SC2 (lineage + revision-of-revision + scope, 14-03/14-04), SC3 (both suites real-dispatch, goldens identical, no kernel literal, import boundaries kept), SC4 deferred as recorded. Ready for `/gsd-verify-work`.
- No blockers.

---
*Phase: 14-run-revision-real-revision-loop-f2-end-to-end*
*Completed: 2026-06-12*

## Self-Check: PASSED

- backend/tests/unit/test_revision_intelligence.py and 14-04-SUMMARY.md exist on disk
- Task commit 2f45ee54 present in git log
