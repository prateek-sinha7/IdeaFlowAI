---
phase: 14-run-revision-real-revision-loop-f2-end-to-end
plan: 03
subsystem: engine
tags: [run_revision, execute-dispatch, deepagents, derived_from-lineage, seq-stamping, scripted-model, pytest]

# Dependency graph
requires:
  - phase: 14-run-revision-real-revision-loop-f2-end-to-end (14-01)
    provides: "planner: skip on both run_revision manifests (no clarify hang) + deterministic _scripts_for revision-agent branches the rewritten suite drives"
  - phase: 14-run-revision-real-revision-loop-f2-end-to-end (14-02)
    provides: WS queue dispatch + terminal-status fidelity the forwarded execute() stream rides transparently
  - phase: 13-live-verification-gap-closure
    provides: FR-014 three-link chain + WR-06 alias transform + the 13-05 kind="deliverable" terminal ref the lineage write chains off
provides:
  - "_handle_revision dispatches the registry's REAL revision pipeline through execute(): get_pipeline_agents(<derived WR-06 alias>) agents on the deepagents runtime, events stamped (seq/event_id) + persisted by the chokepoint, forwarded verbatim through the RAW sender"
  - "Pre-dispatch ValueError for unmapped targets (empty get_pipeline_agents) -> WS revision_validation_error"
  - "Post-dispatch exact-kind lineage write guarded `final_output and not terminal_failed`: kind=target_artifact_type, content=final_output, derived_from=original.id, producer_agent=agents[-1].id, visibility=workspace (FR-014 chain link 1)"
  - "DELETED (INV-3/INV-12): _rev_sink/_rev_counter/_stamped_send duplicate stamping path, CR-01 scope-writeback/sink-arm block, fake pipeline_start/pipeline_complete pair (total_duration 0.0, revision-agent literals), stub content=revision_context write, planning_context_unavailable terminal key"
  - "Rewritten tests/unit/test_run_revision_fe_contract.py: real-dispatch contract incl. single-source seq contiguity trap + revision-of-revision via chain link 1"
affects: [14-04, run_revision, revision-lineage, websocket-dispatch]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Forward-and-capture dispatch: a handler coroutine consumes execute()'s async generator, captures terminal payload fields, and forwards every pre-stamped event verbatim through the caller's raw sender", "Test-derived expected bytes: the suite extracts the expected revised deck from the harness _scripts_for turn instead of duplicating literals"]

key-files:
  created: []
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/tests/unit/test_run_revision_fe_contract.py

key-decisions:
  - "od_context=None on dispatch (settled 14-01 design wrinkle): no revision agent declares injects; the 13-06 guard lives only at the run_pipeline ingress; the parent deck embedded in the composed context physically realizes the template"
  - "gate_agent_ids=[] (not None): suppress the static gate-set fallback — no inter-agent HITL pause on a panel revision"
  - "state_restoration_failed kept on lineage-persist failure, run NOT failed (RESEARCH Open Q2): the terminal-block kind=deliverable ref keeps chain link 2 functional"
  - "producer_agent=agents[-1].id derived from the resolved spec list (IN-05 spirit, no literal) — revision pipelines are 1-2 single_shot steps and the last agent's stream is the declared deliverable"
  - "Failed/empty dispatch writes NOTHING under the exact kind: a failed revision must never become a future revision parent via chain link 1 (composes with 14-02 status fidelity)"

patterns-established:
  - "Revision runs now gain execute()'s full organic envelope: own workspace mint, set_run_scope, run_capabilities (runtime=langchain_deepagents) audit row — INV-13 satisfied by construction"

requirements-completed: [F2]

# Metrics
duration: ~10min
completed: 2026-06-12
---

# Phase 14 Plan 03: Real execute() dispatch in _handle_revision + FE-exact real-dispatch contract Summary

**The Phase-3 echo stub is gone: `_handle_revision` now dispatches `get_pipeline_agents(<derived alias>)` through the normal `execute()` chokepoint (real deepagents runs, single-source seq stamping, organic workspace/scope/capabilities), persists the REVISED deck under the exact target kind with `derived_from`, and the rewritten FE-exact suite pins the whole contract including revision-of-revision via FR-014 chain link 1.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-12T12:24:37Z
- **Completed:** 2026-06-12T12:34:39Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- **Real dispatch (SC1, engine half):** after the kept FR-014 resolution + three-section context composition + WR-06 alias transform, `_handle_revision` resolves `agents = get_pipeline_agents(revision_pipeline_type)` (pre-dispatch ValueError when empty — Pitfall 7) and forwards `self.execute(agents=..., user_message=revision_context, pipeline_type=revision_pipeline_type, user_id=owner_id, od_context=None, gate_agent_ids=[], parent_run_id=...)` event-by-event through the RAW `websocket_send_fn`, capturing `final_output` from `pipeline_complete` and a `terminal_failed` flag from `pipeline_failed`. No fake event pair, no zero-duration completion — the terminal pair is execute()'s own.
- **INV-3/INV-12 deletion in the same change:** the `_rev_sink`/`_rev_counter`/`_raw_send_fn`/`_stamped_send` duplicate stamping path (and its WR-06 comment block), the CR-01 deferred sink-arm + `store._workspace_id` + `set_run_scope` writeback block, the fake `pipeline_start` (the `"revision-agent"`/`"Revision Agent"` literals), the stub `content=revision_context` write, the fake `pipeline_complete` (`total_duration: 0.0`) and its stub-only `planning_context_unavailable` payload key are ALL deleted. execute() owns workspace mint, run scope, stamping and run_events persistence.
- **Exact-kind lineage (SC2):** post-dispatch, guarded `if final_output and not terminal_failed:`, the repointed write persists `kind=target_artifact_type`, `content=final_output`, `derived_from=original.id`, `producer_agent=agents[-1].id`, `workspace_id=original.workspace_id`, `visibility="workspace"`; on persist failure the `state_restoration_failed` vocabulary is kept and the run is not failed.
- **Rewritten FE-exact suite (302 lines, 2 tests):** `test_fe_exact_run_revision_dispatches_real_pipeline` pins (a) no failure events, (b) `agent_start`/`agent_complete` for `od-ppt-revision-agent`, (c) exactly one real `pipeline_start`/`pipeline_complete` pair on the `od_ppt_revision` alias, (d) `final_output ==` the scripted REVISED deck unwrapped (raw HTML, no `<artifact>` wrapper, never the context blob, ≠ parent deliverable; instruction text never matched against final_output per Pitfall 5), (e) seq contiguous 1..N over ALL forwarded events (the double-stamp trap), (f) exactly one exact-kind ref with `content == final_output` and `derived_from ==` the parent's organically persisted deliverable ref id. `test_revision_of_revision_resolves_via_exact_kind_chain_link_1` proves chain link 1: the second revision's agent_input context embeds the FIRST revision's revised deck inside the ORIGINAL ARTIFACT section, and its lineage ref chains `derived_from` off the first revision's exact-kind ref.
- **Parity held (SC3, engine half):** 5 characterization suites byte/event-identical (zero golden re-baselines), banned-pattern + migration-ledger + revision-gating green, lint-imports 4 contracts kept, SC-001 grep over `agents/execution_engine/` returns 0 code matches for any revision workflow name.

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace the echo stub with real execute() dispatch + lineage write; delete the duplicate stamping path** - `8173a8e0` (feat)
2. **Task 2: Rewrite the FE-exact contract suite to the real-dispatch contract (incl. revision-of-revision)** - `10d712cc` (test)

## Files Created/Modified

- `backend/agents/execution_engine/engine.py` - `_handle_revision` only (docstring + body): real dispatch + pre-dispatch guard + guarded exact-kind lineage write; stub/sink/fake-pair/scope-writeback deleted. Diff hunks confined to the method (Pitfall 8 scope held — zero edits to execute()/_execute_impl/providers/deliverable resolvers).
- `backend/tests/unit/test_run_revision_fe_contract.py` - rewritten to the real-dispatch contract: shared `_dispatch_revision` helper mirroring the `_scripted_model` wiring (RUNS_ROOT + both `create_runner` names patched/restored, unique uuid4 run ids), 2 tests, `kind="deliverable"` appears once (read-side lookup only — nothing seeded).

## Decisions Made

- Dispatch passes `od_context=None` and `gate_agent_ids=[]` with WHY comments at the call site (settled design wrinkle + no-HITL-on-panel-revision rationale).
- Lineage-persist failure keeps the `state_restoration_failed` event vocabulary but never fails the completed run (RESEARCH Open Q2 resolution, adopted as planned).
- The expected revised-deck bytes in the suite are DERIVED from `_scripts_for("od-ppt-revision-agent")` (split on the artifact tags) rather than duplicated as a literal — the harness stays the single source of the scripted deck.
- Stale comments referencing the deleted sink-arm/scope-writeback (falsy-owner guard comment, ScopedStore construction comment) were updated for accuracy; the guard raises and the FR-014 ValueError message stay byte-identical (test-pinned).

## Deviations from Plan

None - plan executed exactly as written.

## Known Intermediate (vetted intra-phase gap, plan-documented)

- `tests/unit/test_revision_intelligence.py` is RED (8 failed / 8 passed) — it pins stub semantics (final_output == context blob, `_stamped_send` ledger path, `planning_context_unavailable` on pipeline_complete). Plan 14-04 (Wave 3) rewrites it to the real-dispatch contract. Excluded from this plan's verify commands exactly as specified; every other touched suite is green (`test_run_revision_ws_dispatch.py` 6 passed unaffected).

## Verification Evidence

- Task 1 battery: 5 characterization suites + banned-patterns + migration-ledger + revision-gating — **51 passed, 7 skipped (pre-existing)**; `lint-imports` 4 contracts kept, 0 broken; `git status --porcelain tests/agents/characterization/golden/` empty (zero re-baselines).
- Task 1 acceptance greps: `_stamped_send` 0, `_rev_sink` 0, `"revision-agent"` 0, `"total_duration": 0.0` 0, FR-014 ValueError message exactly 1, `get_pipeline_agents(revision_pipeline_type)` present; diff hunks all inside `_handle_revision` (old lines 3666-3943).
- Task 2: `test_run_revision_fe_contract.py` — **2 passed** (first run); `test_characterization_od_ppt.py + test_banned_patterns.py` — 13 passed. Acceptance greps: agent_start 3 / agent_complete 3 / od-ppt-revision-agent 8 / derived_from 7 / seq 6 / revision_of_revision 1; 302 lines (>= 150).
- Wave gate: quick run (fe_contract + manifest_parity) 34 passed; full battery 51 passed + lint 4 kept + goldens clean.
- SC-001 sweep: `grep -rn "ppt_revision\|od_ppt_revision" backend/agents/execution_engine/` (comment-filtered) — **0 code matches**.
- Live Bedrock confirmation (FE-exact frame → revised deck in the preview, ROADMAP SC4): **DEFERRED** to the milestone-end live pass per project convention (defer-live-verification-to-milestone-end) — not blocking.

## Next Phase Readiness

- 14-04 (Wave 3) can rewrite `test_revision_intelligence.py` against the now-real dispatch: the harness wiring shape it needs is demonstrated in the rewritten FE-exact suite (`_dispatch_revision` helper), and all eight kept guards (instruction/owner/FR-014/cross-owner) are untouched in the engine.
- No blockers.

---
*Phase: 14-run-revision-real-revision-loop-f2-end-to-end*
*Completed: 2026-06-12*

## Self-Check: PASSED

- backend/agents/execution_engine/engine.py and backend/tests/unit/test_run_revision_fe_contract.py exist on disk
- Task commits 8173a8e0 and 10d712cc present in git log
