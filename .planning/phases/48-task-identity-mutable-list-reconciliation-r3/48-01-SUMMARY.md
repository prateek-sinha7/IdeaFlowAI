---
phase: 48-task-identity-mutable-list-reconciliation-r3
plan: 01
subsystem: infra
tags: [execution-engine, resume, task-identity, sha256, content-addressing, kernel]

# Dependency graph
requires:
  - phase: 46-per-task-capture-resume
    provides: "_compute_resume_completed_task_ids cursor, persist_task_html capture seam, subagent_runs.task_id stamping, _rematerialize_artifacts_to_disk"
  - phase: 12-durable-resume
    provides: "_compute_step_input_hash canonical-JSON hash discipline (sorted, no ts/uuid)"
provides:
  - "Pure agents/capabilities/task_identity.py: normalize_task_content / occurrence_ordinals / compute_task_key (content-addressed task_key = sha256(upstream · normalized · ordinal), RESUME-14)"
  - "Single upstream-context-hash home: _upstream_content_hashes (the ONE produces∩consumes scan) + _compute_upstream_context_hash digest, both reused by input_hash (INV-12)"
  - "runner.upstream_context_hash(step) KernelServices handle (per-step digest for strategies)"
  - "Write-path switch: persist_task_html + wave requests stamp the task_key into the task_id slots (positions retired); legacy positional rows still readable (fail-safe re-run)"
affects: [48-02-reconciler-cumulative, 48-03-reconciler-waves-sc001, resume, reconciliation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Content-addressed task identity (sha256 of upstream·normalized·ordinal) replacing positional task ids"
    - "Extract-shared-helper for the upstream scan: one home reused by input_hash + task_key (INV-12)"
    - "Pure capability-package module (stdlib-only, no engine/app import) importable by both strategies and kernel"

key-files:
  created:
    - backend/agents/capabilities/task_identity.py
    - backend/tests/agents/test_task_identity.py
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/agents/execution_engine/kernel_services.py
    - backend/agents/capabilities/strategies/task_loop.py
    - backend/agents/capabilities/strategies/wave_scheduler.py
    - backend/tests/agents/test_restart_resume.py
    - backend/tests/agents/test_strategies.py
    - backend/tests/agents/test_subagent_runs.py

key-decisions:
  - "Three-helper factoring (_upstream_content_hashes owns the ONE scan; _compute_upstream_context_hash + _compute_step_input_hash both reuse it) to satisfy BOTH INV-12 single-scan AND input_hash byte-identity simultaneously"
  - "normalize_task_content folds title + ordinal-stripped body + sorted forward fields (targets/depends_on/conflict_keys) per RESEARCH so json-wave workers with different targets do not collide"
  - "persist_task_html task_key is OPTIONAL (falls back to positional str(task_num)) so the untouched per_task_capture direct-seam suite stays byte-identical"
  - "wave-event/wave_runs task_ids stay AUTHOR ids; only the request/subagent_runs task_id + the skip become keys (goldens read no task_id but wave events DO carry task_ids plural)"

patterns-established:
  - "task_identity single home: every task-identity primitive lives in one pure module; strategies + kernel import it, never re-derive"
  - "Upstream-context-hash single home: the produces∩consumes scan exists exactly once (grep-pinned)"

requirements-completed: [RESUME-14]

# Metrics
duration: 45min
completed: 2026-07-19
---

# Phase 48 Plan 01: Task Identity & Upstream-Hash Single Home Summary

**Content-addressed `task_key = sha256(upstream_context_hash · normalized_task_content · occurrence_ordinal)` in a pure `task_identity` module, the upstream-context-hash factored to ONE reusable engine home (INV-12), and the three physical write sites switched from positional ids to keys — proven byte/event-neutral on 10/10 goldens.**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-07-19
- **Completed:** 2026-07-19
- **Tasks:** 3
- **Files modified:** 7 (2 created, 5 modified)

## Accomplishments
- New pure `agents/capabilities/task_identity.py` (stdlib-only; no engine/app import; zero workflow-name literals) implementing reorder-safe, edit-sensitive, duplicate-disambiguated, upstream-aware, cross-restart-deterministic keys — 21 unit cases.
- Factored the upstream half of `_compute_step_input_hash` into a single `_upstream_content_hashes` scan reused by both `input_hash` and the new `_compute_upstream_context_hash` digest (INV-12 one home), with a `runner.upstream_context_hash(step)` strategy handle — `input_hash` stays byte-identical to HEAD (goldens neutral).
- Switched the durable write-path (`persist_task_html` html_file + file_bundle slots, wave `requests[].task_id`) from positions to keys; `write_fragment_artifact` (worker_index) and `build_waves`/DAG/dup-guard (author `t.id`) left untouched per Pitfall 7.

## Task Commits

1. **Task 1: Pure task_identity module** — `f0417127` (feat, TDD RED→GREEN in one commit)
2. **Task 2: Extract _compute_upstream_context_hash + runner handle** — `7c3100e9` (feat)
3. **Task 3: Write-path switch positions→keys + contract-test updates** — `934e5577` (feat)

_TDD RED was observed failing before each GREEN (module import error for T1; AttributeError for T2; positional-vs-key skip failures for T3)._

## Files Created/Modified
- `backend/agents/capabilities/task_identity.py` — pure normalize/ordinal/compute_task_key (RESUME-14 identity core)
- `backend/tests/agents/test_task_identity.py` — 21 pure unit cases
- `backend/agents/execution_engine/engine.py` — `_upstream_content_hashes` (the ONE scan) + `_compute_upstream_context_hash` digest; `_compute_step_input_hash` rewritten to reuse the scan (byte-identical payload)
- `backend/agents/execution_engine/kernel_services.py` — `persist_task_html` gains optional `task_key` (both write slots); `upstream_context_hash(step)` handle
- `backend/agents/capabilities/strategies/task_loop.py` — per-task keys after parse; key-based resume skip; `task_key=` at both persist calls
- `backend/agents/capabilities/strategies/wave_scheduler.py` — `key_by_id` after parse; request `task_id` + skip use keys; `task_ids`/DAG stay author ids
- `backend/tests/agents/test_restart_resume.py` — new `test_upstream_context_hash_single_home_stable`; 3 identity-contract tests re-seeded to keys; `_WorkerCursorFakeRunner` gains `upstream_context_hash`
- `backend/tests/agents/test_strategies.py` — `_FakeRunner` gains `upstream_context_hash` + `task_key` param (test infra)
- `backend/tests/agents/test_subagent_runs.py` — `test_wave_requests_carry_task_id` re-seeded to keys

## Decisions Made
- **Three-helper factoring for the upstream hash.** The plan/PATTERNS said `_compute_upstream_context_hash` returns a digest AND that `_compute_step_input_hash` stays byte-identical to HEAD — mutually exclusive if input_hash simply swaps the sorted list for a digest. Resolved by putting the ONE produces∩consumes scan in a private `_upstream_content_hashes(step, ectx) -> list[str]` that both callers reuse: `_compute_step_input_hash` folds the raw sorted list (byte-identical), `_compute_upstream_context_hash` digests it. Satisfies every measurable gate: `def _compute_upstream_context_hash`==1, scan-token==1, input_hash unchanged, goldens 10/10.
- **normalize_task_content includes forward fields.** Per RESEARCH §Normalization, the canonical content folds title + ordinal-stripped body + sorted(targets/depends_on/conflict_keys) so same-titled json-wave workers with different targets do not collide and target edits rotate the key. Heading tasks carry empty forward fields → reorder-stability preserved.
- **`task_key` optional on `persist_task_html`.** Direct-seam unit callers (per_task_capture) pass no key; the fallback to positional `str(task_num)` keeps that untouched suite byte-identical while production (task_loop) always passes the real key.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Contract test the plan's classification missed] Updated `test_wave_requests_carry_task_id`**
- **Found during:** Task 3 (write-path switch)
- **Issue:** The plan/RESEARCH listed `test_subagent_runs.py` (18) as byte-neutral / untouched, but `test_wave_requests_carry_task_id` asserts the wave **request** `task_id` equals the author id `{"ta","tb"}` — the exact value the RESUME-14 write-switch changes to the content-addressed key. Leaving it would either force a wrong (unweakened) failure or block the switch.
- **Fix:** Re-seeded the assertion to the computed keys (upstream `""` since the fake exposes no handle; distinct content → ordinal 0), preserving the real contract (each request carries a distinct stable identity aligned one-to-one with its body). Not a weakening — the identity is now the key that wraps the author id.
- **Files modified:** backend/tests/agents/test_subagent_runs.py
- **Verification:** test_subagent_runs 18/18 green; goldens 10/10 unchanged.
- **Committed in:** 934e5577

**2. [Rule 2 - Required for correctness] task_loop resume skip made key-consistent**
- **Found during:** Task 3
- **Issue:** After the write-switch, `_compute_resume_completed_task_ids` reads `artifact_refs.task_id` (now keys). The task_loop skip still compared `str(task_num)` — positional vs keys would NEVER match → all tasks re-run → a Phase-46 resume-skip regression (a regression-floor violation). The plan's prose scoped only the write path for task_loop but its `<done>` requires the contract test GREEN with keys.
- **Fix:** The task_loop skip now compares `_task_keys[task_num-1]` (per-key set membership). 48-02 refines this to the cumulative common-prefix rule.
- **Files modified:** backend/agents/capabilities/strategies/task_loop.py
- **Verification:** `test_task_loop_skips_completed_tasks_on_resume_cursor` GREEN with keys; restart_resume 17/1 (KAN-88 sole red).
- **Committed in:** 934e5577

**3. [Rule 3 - Blocking test infra] Fakes gained the new handle**
- **Found during:** Task 3
- **Issue:** The strategies now call `runner.upstream_context_hash(step)` and pass `task_key=`; `_FakeRunner` / `_WorkerCursorFakeRunner` lacked both → the task_loop/wave unit tests would crash.
- **Fix:** Added `upstream_context_hash` (fixed `"u-fake"`) + a `task_key` param to the fakes. Non-breaking test-infra plumbing.
- **Files modified:** backend/tests/agents/test_strategies.py, backend/tests/agents/test_restart_resume.py
- **Verification:** test_strategies + restart_resume green (KAN-88 aside).
- **Committed in:** 934e5577

---

**Total deviations:** 3 auto-fixed (1 contract test the plan mis-classified, 1 correctness/floor fix, 1 blocking test-infra). **Doc-alignment note:** the plan's verify command listed stale characterization filenames (`test_characterization_ppt/user_stories/code_gen.py`); the actual 5 golden files (`prototype`, `od_ppt`, `od_prototype`, `prototype_revision`, `app_builder`) were run via the `test_characterization_*` glob the verification section uses — 10/10.
**Impact on plan:** All auto-fixes necessary for correctness / to avoid regressing the Phase-46 resume floor. No scope creep — `write_fragment_artifact`, `build_waves`/DAG, the Phase-45 completeness tests, and the byte-neutral suites are untouched.

## Issues Encountered
- The RESEARCH "golden neutrality — PROVEN" grep searched `"task_id"` (singular) and so missed `"task_ids"` (plural) in the `wave_started`/`wave_completed`/`wave_failed` event payloads. Confirmed those event `task_ids` still carry AUTHOR ids (only the request/subagent_runs `task_id` + skip became keys), so goldens stayed 10/10 — no event payload changed.

## Verification (verify-by-delta against the 48-VALIDATION baseline)
- `test_task_identity.py` — **21 passed** (new pure module)
- `test_restart_resume.py` — **17 passed / 1 failed** (KAN-88 `test_waiting_for_user_run_is_rearmed_not_driven` = SOLE pre-existing red, untouched; +1 new upstream_context_hash pass)
- per_task_capture **4**, wave_scheduler **10**, json_tasks **12**, subagent_runs **18** — all held
- Goldens (5 characterization files, `SNAPSHOT_UPDATE` unset) — **10 passed**
- INV-1: `grep -cE 'pipeline_type ==|spec.id ==' engine.py` → **0**
- INV-12: `grep -c 'def _compute_upstream_context_hash' engine.py` → **1**; scan-token `grep -c 'set(getattr(upstream, "produces", \[\])) & consumes'` → **1**
- lint-imports → **4 kept / 0 broken**
- redo_gate_safety → **4 passed / 3 failed** (pre-existing scripted-model harness drift, held — not this phase)
- `write_fragment_artifact` still `task_id=str(worker_index)` (Site C untouched)

## Next Phase Readiness
- The identity substrate is in place for **48-02** (cumulative `task_loop` common-prefix reconcile + gate-Edit `derived_from` gap-close) and **48-03** (independent wave reconcile + orphan exclusion + SC-001 synthetic proof + update_specs compose). The cursor already returns keys (identity-agnostic read); 48-02 extends it to emit ordered keys and refines the task_loop skip from per-key set membership to the common-prefix rule.
- No blockers.

## Self-Check: PASSED

- Files exist: task_identity.py, test_task_identity.py, 48-01-SUMMARY.md — all FOUND
- Commits exist: f0417127, 7c3100e9, 934e5577 — all FOUND

---
*Phase: 48-task-identity-mutable-list-reconciliation-r3*
*Completed: 2026-07-19*
