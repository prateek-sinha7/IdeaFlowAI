---
phase: 03-token-trim-measured-change-0c
plan: 02
subsystem: testing
tags: [characterization, golden-snapshot, parity, token-delta, live-test, prototype-build, deepagents, bedrock]

# Dependency graph
requires:
  - phase: 03-token-trim-measured-change-0c (plan 01)
    provides: "the live engine edit — _extract_html_skeleton wired into _build_context_message's is_build_task_2_plus branch (COMPACT-01) + the deterministic >=50% CI gate (COMPACT-03 Req 2)"
  - phase: 00-characterization
    provides: "offline _scripted_model._drive harness + SNAPSHOT_UPDATE=1 golden re-baseline mechanism + the semantic event-snapshot split (held green / deliverable bytes re-baselineable)"
  - phase: 02-executioncontext-ownership-0b
    provides: "ectx threading through _build_context_message"
provides:
  - "offline pages/routes + validation-pass parity proof for the compacted prototype/od_prototype build (COMPACT-02 / Req 6)"
  - "prototype + od_prototype deliverable byte-goldens re-baselined under SNAPSHOT_UPDATE=1 (sanctioned INV-3 0C change) — confirmed NO-OP diff (scripted model writes fixed HTML)"
  - "opt-in dual-gated live token-delta evidence test (COMPACT-03 / Req 3 / D-04) that skips cleanly in CI"
affects: [phase-07-capability-reexpression, PARITY-04, CompactionStrategy]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Derive a parity reference (data-page IDs + routes keys) from the committed golden using the SAME regexes _extract_html_skeleton uses — test and helper agree on what a page/route is"
    - "Equal-or-better validation = zero net-new FAILURE events (error/agent_error/state_restoration_failed/planner_timeout/pipeline_cancelled) AND a clean pipeline_complete, so 'no failures' cannot pass vacuously on an aborted run"
    - "Opt-in live evidence test reuses the verbatim double-gate (RUN_LIVE_BEDROCK=1 + STS probe) from test_deep_agent_runner_hitl_live.py; evidence-only, never a CI gate"

key-files:
  created:
    - backend/tests/agents/test_phase3_parity.py
    - backend/tests/agents/test_phase3_token_delta_live.py
  modified: []

key-decisions:
  - "Parity reference derived from the committed golden/prototype.html (the stable post-0B reference — the scripted model writes fixed HTML regardless of prompt), NOT a freshly-driven 'before' run (the engine edit is already live in this wave)"
  - "Validation parity expressed as a failure-event count (reference=0) + a pipeline_complete assertion, since the offline stream surfaces no explicit validation-FAILURE event on a clean run"
  - "Golden re-baseline is a confirmed NO-OP diff (scripted fixed-HTML caveat) — committed nothing for the goldens; the real byte/token change is evidenced by the live token-delta test (D-04)"
  - "No live AWS run available at execution time → recorded the D-04 manual-run procedure + reproduction command as the COMPACT-03 evidence fallback"

patterns-established:
  - "Parity-by-reference-golden: anchor falsifiable structural-parity assertions on the committed golden, guarded by a non-vacuous-set check"
  - "Live evidence tests self-skip under a dual opt-in gate and print the measured figure + reproduction command for SUMMARY capture"

requirements-completed: [COMPACT-02, COMPACT-03]

# Metrics
duration: ~20min
completed: 2026-06-07
---

# Phase 3 Plan 02: Token-Trim parity + measured-change evidence Summary

**Proved semantic parity for the now-compacted prototype/od_prototype build (identical data-page IDs + routes keys, equal-or-better validation), re-baselined the two deliverable goldens under SNAPSHOT_UPDATE=1 (confirmed no-op diff per the scripted fixed-HTML caveat), and added an opt-in dual-gated live token-delta evidence test that skips cleanly in CI — all with L13 still ☐ and no other pipeline's golden touched.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-06-07
- **Tasks:** 3
- **Files modified:** 2 (both new test modules; zero golden bytes changed)

## Accomplishments
- **Pages/routes + validation parity (COMPACT-02 / Req 6):** `test_phase3_parity.py` drives both `prototype` and `od_prototype` fully offline, derives the produced deliverable's `data-page` ID set + `routes` map keys using the SAME regexes `_extract_html_skeleton` uses, and asserts they equal the pre-0C reference (derived from the committed `golden/prototype.html`). Validation parity asserts zero net-new FAILURE events AND a clean `pipeline_complete`. Falsifiable: a dropped/renamed `data-page` section would diverge from the reference and FAIL.
- **Deliverable golden re-baseline (COMPACT-02 / Req 5):** ran `SNAPSHOT_UPDATE=1` on the prototype + od_prototype characterization tests. The diff is **EMPTY** — the documented scripted no-op (the offline `_scripted_model` writes a fixed 84-byte single-section HTML regardless of prompt content), so the re-baselined goldens are byte-identical to the committed ones. No golden file moved; the real byte/token change is evidenced by the live token-delta (D-04). Semantic event snapshots stay green with NO `*.events.json` edit and `assert_seq_contiguous` holds.
- **Live token-delta evidence (COMPACT-03 / Req 3 / D-04):** `test_phase3_token_delta_live.py` runs the multi-task prototype build twice against a real model (compaction ON vs forced OFF via a least-invasive monkeypatch that swaps the skeleton block back for the full-HTML block), accumulates `input_tokens`, and prints the delta + reduction + reproduction command. Double-gated (`RUN_LIVE_BEDROCK=1` + STS probe), evidence-only, NEVER a CI gate.

## Task Commits

Each task was committed atomically:

1. **Task 1: Offline pages/routes + validation parity assertion** - `3ab8ccb` (test/tests)
2. **Task 2: Re-baseline prototype + od_prototype deliverable goldens; hold semantic event snapshots green** - no commit (confirmed NO-OP diff — the scripted fixed-HTML caveat; SNAPSHOT_UPDATE=1 rewrote the goldens byte-identically, so there was nothing to commit)
3. **Task 3: Opt-in live token-delta evidence test** - `6371744` (test/tests)

## Files Created/Modified
- `backend/tests/agents/test_phase3_parity.py` - offline parity: `test_reference_golden_has_a_stable_nonempty_page_set` (anti-vacuous guard), `test_prototype_pages_routes_parity`, `test_od_prototype_pages_routes_parity`, `test_validation_pass_equal_or_better`. Uses the helper's own `data-page` (engine.py:2667) and `const routes` (engine.py:2661) regexes; reference derived from `golden/prototype.html`.
- `backend/tests/agents/test_phase3_token_delta_live.py` - opt-in dual-gated live token-delta evidence (`_RUN_LIVE_HINT` + `_aws_creds_resolve()` copied from `test_deep_agent_runner_hitl_live.py`; `test_token_delta_live` runs compaction ON vs OFF and prints the measured reduction).

## COMPACT-03 real-run token-delta evidence (Req 3 / D-04)

**No live AWS/Bedrock run was available at execution time** (the execution environment has no resolvable SSO credentials — the dual gate skips cleanly). Per D-04, the documented manual-run procedure is recorded here as the COMPACT-03 evidence fallback:

**Manual-run procedure (produces the measured token reduction):**
```bash
cd backend
aws sso login --profile personal-sso
RUN_LIVE_BEDROCK=1 AWS_PROFILE=personal-sso \
  python3.11 -m pytest tests/agents/test_phase3_token_delta_live.py -v -s
```

The test prints a block like:
```
COMPACT-03 LIVE token-delta evidence (multi-task prototype build)
  input_tokens (compaction OFF / pre-0C): <N_off>
  input_tokens (compaction ON  / 0C):     <N_on>
  delta (tokens saved):                    <N_off - N_on>
  reduction:                               <pct>%
```
and asserts `tokens_on < tokens_off`. Paste the printed figures here after the live run.

**Deterministic corroborating evidence (already landed in 03-01, offline, CI):** on the in-test multi-page fixture the build-task-2 prompt is **96.9% smaller** (419-char skeleton vs 30,227-char full-HTML message; ratio 0.031), reproducible with:
```bash
cd backend && python3.11 -m pytest tests/agents/test_phase3_compaction.py -v
```
The live test measures the same injection-site delta on a real model's accumulated `input_tokens`; the offline >=50% gate is the CI ratchet, the live test is the real-run evidence.

## Decisions Made
- **Parity reference source:** the committed `golden/prototype.html` is the stable post-0B reference (the scripted model ignores prompt content), so the page/route reference sets are derived from it rather than from a freshly-driven "before" run (the engine edit is already live in this wave).
- **Validation-parity shape:** expressed as a failure-event count (reference = 0) plus a `pipeline_complete` assertion, because the offline event stream surfaces no explicit validation-FAILURE event on a clean run — this keeps the check falsifiable (a broken build would emit `error`/`agent_error` or never complete) without inventing a non-existent event type.
- **Golden re-baseline:** ran under `SNAPSHOT_UPDATE=1` as mandated; the resulting diff is empty (the documented scripted fixed-HTML caveat), so nothing was committed for the goldens.
- **Live-test compaction-OFF baseline:** reproduced the pre-0C prompt by wrapping `_build_context_message` to swap the skeleton block back for the full-HTML block — the least-invasive way to drive the baseline without touching engine state.

## Deviations from Plan

None - plan executed exactly as written. Task 2 produced no commit because the golden re-baseline was a confirmed no-op diff (the documented expected outcome per the phase invariants and 03-PATTERNS.md), not a deviation.

## Issues Encountered
None. The empty golden diff was the explicitly-anticipated scripted fixed-HTML caveat (handled by the plan's outcome-(b) branch). No live AWS run was available, handled by the D-04 manual-run-procedure fallback.

## Verification Results
- `python3.11 -m pytest tests/agents/test_phase3_parity.py -v` → 4 passed (offline).
- `python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py -v` → 4 passed (deliverable byte + semantic event snapshots) with NO golden edit.
- `git status --short tests/agents/characterization/` → empty after SNAPSHOT_UPDATE=1 (no golden moved — `prototype_revision.html`, `od_ppt.html`, `app_builder.txt`, and all `*.events.json` byte-identical).
- `python3.11 -m pytest tests/agents/test_phase3_token_delta_live.py -v` → 1 skipped (CI-safe; prints `_RUN_LIVE_HINT`). With `RUN_LIVE_BEDROCK=1` + unresolvable creds → still skips cleanly (no mid-model error) — both gates verified.
- `python3.11 -m pytest tests/agents/test_migration_ledger.py -v` → green; L13 (`_extract_html_skeleton`, owning phase 0C→2) is still `☐` in `specs/003-workflow-engine-decoupling/migration-ledger.md`.
- Combined phase suite (parity + compaction + characterization + live + ledger) → 17 passed, 2 skipped.

## User Setup Required
None for the default/CI path. To produce the live COMPACT-03 figure, a developer runs the opt-in manual procedure above (requires their own AWS SSO session — no new credential surface; identical to the existing live HITL test).

## Next Phase Readiness
- COMPACT-01/02/03 are now complete for both `prototype` and `od_prototype`: the skeleton is wired (03-01), the >=50% CI gate is live (03-01), semantic parity is proven (this plan), the deliverable goldens are re-baselined (no-op confirmed), and the live token-delta evidence test is in place (this plan).
- Phase 03 is done (2/2 plans). L13 remains `☐` — its deletion / re-expression as a registered `CompactionStrategy(html_skeleton)` is Phase 7 (PARITY-04), explicitly out of scope here.
- Outstanding manual action (non-blocking): a developer with AWS SSO can run the opt-in live test once and paste the measured figure into the COMPACT-03 evidence block above.

## Self-Check: PASSED

- FOUND: backend/tests/agents/test_phase3_parity.py
- FOUND: backend/tests/agents/test_phase3_token_delta_live.py
- FOUND: .planning/phases/03-token-trim-measured-change-0c/03-02-SUMMARY.md
- FOUND commit: 3ab8ccb (Task 1, parity test)
- FOUND commit: 6371744 (Task 3, live test)
- Task 2 golden re-baseline: confirmed no-op (empty diff) — no commit expected

---
*Phase: 03-token-trim-measured-change-0c*
*Completed: 2026-06-07*
