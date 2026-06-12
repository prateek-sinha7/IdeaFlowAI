---
phase: 14-run-revision-real-revision-loop-f2-end-to-end
plan: 01
subsystem: agents
tags: [workflow-manifest, planner-skip, run_revision, parity-traps, scripted-model, pytest]

# Dependency graph
requires:
  - phase: 13-gap-closure
    provides: missing_template_context ingress guard (13-06) the design-wrinkle pin reasons about; FE run_revision routing fixes (13-05/WR-06)
  - phase: 07-capability-extraction
    provides: manifest-sourced planner flag (compiled.planner) + engine skip branch the data flip routes through
provides:
  - "ppt_revision + od_ppt_revision manifests declare planner: skip — run_revision dispatch bypasses planner LLM call AND the indefinite clarify event.wait() pause"
  - "_RUN_REVISION_DISPATCHED two-id carve-out pinned in BOTH planner parity traps (test_manifest_parity.py + test_id_alias_resolver.py)"
  - "Executable design-wrinkle pin: test_run_revision_revision_agents_declare_no_template_injects fails CI if a revision agent of either pipeline ever declares template/design_system injects"
  - "Deterministic _scripts_for branches for od-ppt-revision-agent, ppt-revision-agent, ppt-revision-assembler (Wave-0 harness for 14-03/14-04)"
affects: [14-02, 14-03, 14-04, run_revision, websocket-dispatch, revision-lineage]

# Tech tracking
tech-stack:
  added: []
  patterns: ["INV-5 data-only manifest flip: behavior change shipped as a one-key YAML edit routed through the existing engine skip branch — zero engine edits", "Sibling parity traps kept in lockstep via a shared frozenset constant duplicated with cross-citing comments"]

key-files:
  created: []
  modified:
    - backend/agents/workflows/ppt_revision/workflow.yaml
    - backend/agents/workflows/od_ppt_revision/workflow.yaml
    - backend/tests/agents/test_manifest_parity.py
    - backend/tests/agents/test_id_alias_resolver.py
    - backend/tests/agents/_scripted_model.py

key-decisions:
  - "test_id_alias_resolver.py gets its OWN _RUN_REVISION_DISPATCHED copy (with a lockstep comment citing the sibling trap) rather than importing from test_manifest_parity.py — keeps the pure-data test file import-independent"
  - "Carve-out folded into the existing parametrized trap PLUS a dedicated explicit skip-pin test (both shapes the plan allowed) — the parametrized trap guards every other id stays run, the explicit test names the contract"
  - "Manifest header comments reworded to avoid the literal 'planner: skip' string so the acceptance grep -c returns exactly 1 (the key itself)"

patterns-established:
  - "Design wrinkles settled in planning become executable pins: a test that fails loudly when the deferred prerequisite (template_id persistence on WorkflowRun, additive Q3) is needed"

requirements-completed: [F2]

# Metrics
duration: ~8min
completed: 2026-06-12
---

# Phase 14 Plan 01: planner:skip flip + parity-trap carve-outs + revision harness Summary

**ppt_revision and od_ppt_revision flipped to `planner: skip` (data-only, INV-5) so run_revision dispatch can never hang at the clarify event.wait(); both planner parity traps pin the two-id carve-out; the injects-free design wrinkle is now an executable test; the scripted-model harness drives all three revision agents deterministically.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-12T11:59:29Z
- **Completed:** 2026-06-12T12:07:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Both run_revision-dispatched manifests declare `planner: skip` — the engine's skip branch (engine.py:1198-1205) sets `gate_verdict="PROCEED"` with no planner events, so the indefinite clarify `event.wait()` (RESEARCH Pitfall 1) is never reached. Zero engine edits (SC-001/INV-5 held).
- Parity trap #1 in `test_manifest_parity.py` AND the second trap in `test_id_alias_resolver.py` (`test_compiled_planner_is_run_everywhere`) both carve out exactly `{"ppt_revision", "od_ppt_revision"}` — every other dispatchable manifest is still pinned to `planner: run`. Trap #2 (clarify-defaults) untouched and green (clarify block stays byte-identical in both manifests).
- The settled design wrinkle is executable: `test_run_revision_revision_agents_declare_no_template_injects` asserts no agent of either pipeline declares `template`/`design_system` injects, with the full evidence chain in its docstring (revision dispatch passes `od_context=None`, never traverses the 13-06 `missing_template_context` ingress guard; a future inject-declaring revision agent must first persist `template_id` on WorkflowRun).
- Three new deterministic `_scripts_for` branches: `od-ppt-revision-agent` and `ppt-revision-assembler` each emit exactly one `<artifact>`-wrapped REVISED deck (byte-distinct from the od-ppt-validator parent deck and from each other); `ppt-revision-agent` is narration-only. Wave-0 precondition for the 14-03/14-04 test rewrites delivered (`wave_0_complete` flips true).

## Task Commits

Each task was committed atomically:

1. **Task 1: Flip ppt_revision + od_ppt_revision to planner: skip and update both planner parity traps + add the design-wrinkle pin** - `22e10df0` (feat)
2. **Task 2: Add deterministic scripted-model turns for the three revision agents** - `25f02ae1` (test)

## Files Created/Modified

- `backend/agents/workflows/ppt_revision/workflow.yaml` - `planner: run` → `skip` (one key); header comment documents the Phase-14 flip rationale
- `backend/agents/workflows/od_ppt_revision/workflow.yaml` - same one-key flip + comment
- `backend/tests/agents/test_manifest_parity.py` - `_RUN_REVISION_DISPATCHED` constant, trap #1 carve-out, explicit skip-pin test, design-wrinkle pin test, module docstring updated
- `backend/tests/agents/test_id_alias_resolver.py` - same two-id carve-out in `test_compiled_planner_is_run_everywhere` with sibling-trap lockstep comment
- `backend/tests/agents/_scripted_model.py` - three additive `_scripts_for` branches adjacent to the od-ppt block (fixed text + usage, sanitizer pass-through markup)

## Decisions Made

- `test_id_alias_resolver.py` keeps its own `_RUN_REVISION_DISPATCHED` copy (plan allowed copy or import) — the file is a pure-data suite; a cross-test-module import would couple it to `test_manifest_parity.py` collection. Lockstep comments cite each sibling.
- Shipped BOTH carve-out shapes the plan offered: the parametrized trap asserts the per-id expected value (skip vs run), plus a dedicated `test_run_revision_manifests_declare_planner_skip` naming the contract explicitly.
- Manifest header comments avoid the literal `planner: skip`/`planner: run` strings (phrased "planner flip (run -> skip)") so the acceptance criterion `grep -c "planner: skip" == 1` holds — the single match is the key itself.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. First comment draft inflated the `grep -c "planner: skip"` acceptance count to 3; reworded before commit.

## Verification Evidence

- Task 1 battery: `test_manifest_parity.py + test_id_alias_resolver.py + test_revision_gating.py + test_characterization_prototype_revision.py` — 101 passed; `lint-imports` 4 contracts kept.
- Task 2: source asserts green (artifact tags present/absent per agent, decks distinct); `test_characterization_od_ppt.py + test_run_revision_fe_contract.py` — 3 passed, zero golden files modified.
- Wave gate (14-VALIDATION.md battery): 5 characterization suites + banned-patterns + migration-ledger + revision-gating + both parity suites — 143 passed, 7 skipped (pre-existing); `lint-imports` 4 kept.
- INV-3 scope: `git diff --name-only HEAD~2 HEAD` contains no file under `backend/agents/execution_engine/` and no characterization golden; `prototype_revision`/`user_stories_revision`/`app_builder_revision` manifests untouched.
- Live-Bedrock confirmation of the flipped flow (ROADMAP SC4) recorded as **DEFERRED** to the milestone-end live pass (project convention: defer-live-verification-to-milestone-end) — not blocking.

## Next Phase Readiness

- 14-02 (WS dispatch refactor) can proceed: a dispatched revision through `execute()` no longer risks the clarify hang.
- 14-03/14-04 test rewrites have their deterministic harness (three scripted revision-agent branches) and both parity traps already pin the new planner contract.
- No blockers.

---
*Phase: 14-run-revision-real-revision-loop-f2-end-to-end*
*Completed: 2026-06-12*

## Self-Check: PASSED

- All modified files exist on disk
- Task commits 22e10df0 and 25f02ae1 present in git log
