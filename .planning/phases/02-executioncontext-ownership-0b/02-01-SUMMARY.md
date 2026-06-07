---
phase: 02-executioncontext-ownership-0b
plan: 01
subsystem: infra
tags: [execution-engine, dataclass, statelessness, refactor, concurrency, langgraph]

# Dependency graph
requires:
  - phase: 01-safety-net-deletion-guard-0a
    provides: "Phase 0A golden-snapshot characterization suite (deliverable byte + semantic event parity via _scripted_model._drive) — the CTX-05 zero-behavior-change gate; migration-ledger CI ratchet; import-linter kernel→ports scaffold"
provides:
  - "ExecutionContext per-run value object (agents/execution_engine/context.py) — the seam every later phase grows fields onto"
  - "Stateless ExecutionEngine kernel: only _resolver/_store/_state_machine remain on the singleton after __init__ (NFR-001 / INV-2)"
  - "Explicit ectx parameter threaded through _run_agent / _run_build_task_loop / _should_gate / _build_context_message / _write_build_reference_files (+ checkpointer into _run_validation_fix_loop)"
  - "L14 grep ratchet target met: self._(od_context|completed_tasks|current_task_block|revision_|gate_agent_ids) → 0 over backend/"
affects: [02-02, 02-03, "Phase 4 manifests/compiler", "Phase 5 store-layer authz", "Phase 7 kernel split + TaskLoopStrategy", "fan-out/wave phases"]

# Tech tracking
tech-stack:
  added: []   # stdlib dataclasses only — no new package installs
  patterns:
    - "Per-run value object threaded explicitly (D-03 — no contextvars / no ambient state)"
    - "Mutable @dataclass with field(default_factory=...) for all mutable defaults (factory.py::AgentContext idiom)"
    - "Kernel singleton holds construction-time singletons only; all run state on a threaded context"

key-files:
  created:
    - "backend/agents/execution_engine/context.py — ExecutionContext @dataclass (D-01 minimal field set)"
    - "backend/tests/agents/test_execution_context.py — context unit tests (offline, characterization job)"
  modified:
    - "backend/agents/execution_engine/engine.py — execute() constructs ectx; 6 read-site methods thread it; no per-run self._* write survives"
    - "backend/tests/agents/test_phase3_cutover_verify.py — thread ectx; read ectx.completed_tasks"
    - "backend/tests/agents/test_phase4_build_loop.py — _fresh_engine returns ectx; _run_loop + spy threaded"
    - "backend/tests/agents/test_phase5_revision_validation.py — capture baseline/instruction via fix-loop spy (not engine attrs)"
    - "backend/tests/unit/test_agent_input_event.py — _build_context_message calls thread a minimal ectx"

key-decisions:
  - "revision_* kept as FLAT fields on ExecutionContext (not a nested RevisionState) — keeps Task-2 consumer rewrites mechanical (call sites read each baseline/instruction separately)"
  - "current_task_block is a DELIBERATE Phase-7-TEMPORARY home on ExecutionContext (D-02) — Phase 7 reclaims it into TaskLoopStrategy"
  - "_checkpointer relocation: added a `checkpointer` keyword param to _run_validation_fix_loop and pass ectx.checkpointer at its 2 call sites (the fix-loop is not one of the 4 ectx-param methods, but needed the checkpointer off self)"
  - "owner_id = user_id or \"anon\" (D-04); RunSandbox(user_id or \"anon\", ...) keying left byte-identical (D-05)"
  - "Did NOT flip migration-ledger L14/D1 rows to ☑ — out of scope for 02-01 (D1 = _handle_revision deletion is plan 02-02); flipping now would break test_ledger_parses_and_all_phase1_rows_pending. L14 is enforced directly by the acceptance grep."

patterns-established:
  - "ExecutionContext threading: execute() builds one ectx right after RunSandbox and passes it down explicitly"
  - "White-box engine tests observe relocated run state through the threaded context / method args, not via engine singleton attributes"

requirements-completed: [CTX-01, CTX-02, CTX-05]

# Metrics
duration: ~75min
completed: 2026-06-07
---

# Phase 2 Plan 01: ExecutionContext State Lift Summary

**Introduced a per-run ExecutionContext value object and relocated every per-run `self._*` datum off the ExecutionEngine singleton onto it (threaded explicitly), making the kernel stateless after `__init__` with zero behavior change (268-test 0A suite green, L14 grep → 0).**

## Performance

- **Duration:** ~75 min
- **Tasks:** 2 (both TDD)
- **Files modified:** 7 (1 new module + 1 new test + engine.py + 4 test files updated)

## Accomplishments
- New `ExecutionContext` `@dataclass` (`context.py`) carrying the D-01 minimal field set; stdlib-only imports (import-direction clean); mutable defaults via `field(default_factory=...)`.
- `execute()` constructs ONE `ectx` per run (right after `RunSandbox`) and threads it through the call tree; every per-run `self._*` write DELETED from the singleton (INV-3 — no dual implementations).
- Kernel singleton is now stateless after `__init__` — only `_resolver`/`_store`/`_state_machine` remain (NFR-001 / INV-2; removes the concurrency hazard blocking the fan-out phases).
- L14 grep `self._(od_context|completed_tasks|current_task_block|revision_|gate_agent_ids)` over `backend/` → **0**; the non-L14 attrs (`_user_id`/`_checkpointer`/`_parent_run_id`/`_disk_skills`) also relocated.
- CTX-05 proven: full Phase 0A characterization suite green (268 passed, 18 skipped) — deliverable bytes identical, semantic event parity, `seq` contiguous, sandbox keying byte-identical.

## Final ExecutionContext field layout (D-01)

Flat `@dataclass` (NOT frozen), required fields first:

| Field | Type / default | Notes |
|-------|----------------|-------|
| `run_id` | `str` (required) | pipeline_run_id |
| `owner_id` | `str` (required) | `user_id or "anon"` (D-04) |
| `od_context` | `dict \| None = None` | flows engine → AgentContext per agent |
| `completed_tasks` | `list[dict] = field(default_factory=list)` | RUN-LEVEL cumulative task list |
| `gate_agent_ids` | `list[str] \| None = None` | per-run HITL gate selection |
| `parent_run_id` | `str \| None = None` | prototype_revision parent-seed source |
| `checkpointer` | `object \| None = None` | process-wide LangGraph checkpointer ref |
| `current_task_block` | `str = ""` | **D-02 TEMPORARY home — Phase 7 → TaskLoopStrategy** |
| `revision_original_html` | `str = ""` | flat revision group |
| `revision_instruction` | `str \| None = None` | flat |
| `revision_baseline_static` | `set[str] = field(default_factory=set)` | flat |
| `revision_baseline_console` | `set[str] = field(default_factory=set)` | flat |
| `accumulated_outputs` | `dict[str, str] = field(default_factory=dict)` | sanctioned legacy mirror |
| `cancel_event` | `object \| None = None` | cooperative cancel signal |
| `disk_skills` | `dict = field(default_factory=dict)` | per-user SKILL.md overrides |
| `depth` | `int = 0` | reserved for fan-out phases |

`revision_*` is **flat**, not a nested `RevisionState` (Claude's-discretion D-07 — chosen to keep consumer rewrites mechanical). No speculative later-phase fields (`plan`/`workspace`/`artifacts`/`budget`/`models`/`workspace_id`) — INV-12.

## D-02 flag for Phase 7

`current_task_block` is a **deliberate temporary home** on `ExecutionContext` (the only field that is known-temporary). Strategy-local scratch ultimately belongs IN the strategy, not on ctx — but no strategy exists in 0B, and getting it off the singleton (the L14 grep gate) requires parking it on the context now. **Phase 7 [2] must reclaim `current_task_block` into `TaskLoopStrategy`.**

## New `ectx` parameter added (for the source-grounding pass)

- `_run_agent(..., cancel_event, ectx)` — positional, last
- `_run_build_task_loop(..., cancel_event, ectx)` — positional, last
- `_should_gate(self, spec, ectx)` — positional
- `_build_context_message(..., planning_context, ectx)` — positional, last
- `_write_build_reference_files(self, sandbox, accumulated_outputs, ectx)` — positional, last (private helper, threaded for its `od_context` read)
- `_run_validation_fix_loop(..., checkpointer=None)` — keyword-only `checkpointer` added (NOT a full `ectx` param — the fix-loop already receives `baseline_*`/`user_instruction`/`ctx: AgentContext` explicitly; only the relocated `_checkpointer` read needed a new arg). Named `ectx` everywhere to avoid shadowing the existing `ctx: AgentContext` param.

## Task Commits

1. **Task 1: Create ExecutionContext (context.py) + tests** — `5a71931` (feat) — TDD: test written failing (import error), then context.py made it green.
2. **Task 2: Construct ectx in execute(), relocate all per-run state, thread it** — `8b90fd2` (refactor) — 0A suite re-run green after the lift.

**Plan metadata:** _(final docs commit — see below)_

## Decisions Made
See `key-decisions` frontmatter. Summary: flat `revision_*`; `current_task_block` temporary (D-02); `checkpointer` threaded as a keyword arg into the fix-loop; ledger rows intentionally NOT flipped (out of 02-01 scope).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] White-box tests broke on the relocated state / changed signatures**
- **Found during:** Task 2 (verification — full `tests/agents/` run)
- **Issue:** Ten tests across `test_phase3_cutover_verify.py`, `test_phase4_build_loop.py`, `test_phase5_revision_validation.py` (and 3 calls in `tests/unit/test_agent_input_event.py`) directly poked the OLD per-run engine attributes (`engine._completed_tasks`, `engine._revision_baseline_static`, `engine._revision_instruction`, `engine._od_context`) and/or called the now-`ectx`-threaded methods (`_run_build_task_loop`, `_build_context_message`) with their pre-lift signatures. The relocation (the unit under test) necessarily breaks those introspections.
- **Fix:** Threaded `ectx` into the test call sites; updated the `_build_context_message` spy signature; switched the phase5 baseline test to observe `baseline_static`/`user_instruction` via a `_run_validation_fix_loop` spy (the args carry `ectx.revision_*`) instead of reading singleton attributes; read `ectx.completed_tasks` instead of `engine._completed_tasks`. Behaviour assertions unchanged.
- **Files modified:** the 4 test files listed in `key-files.modified`.
- **Verification:** all 24 of the 3 phase suites pass; `tests/unit/test_agent_input_event.py` 7/7; full `tests/agents/` 268 passed.
- **Committed in:** `8b90fd2` (Task 2 commit).

---

**Total deviations:** 1 auto-fixed (Rule 3 — blocking test updates required by the API change). No scope creep — assertions preserve the same observable behavior through the new seam.

## Issues Encountered
- A vendored venv (`backend/backend/.local/`, gitignored) shows `self._revision_map` matches for the L14 grep when scanning the whole `backend/` tree; the gate is over project source (git-tracked) and returns **0** there. The migration-ledger ratchet uses `--include=*.py` and is not yet armed for L14 (row stays `☐` until plan 02-02/02-03 flip it).
- Two pre-existing, unrelated test failures (`tests/unit/test_logout.py` x7, `tests/unit/test_pipeline_cancel.py::test_cancel_marks_workflow_cancelled_and_sends_ack`) — environment/credential-driven (expired AWS Bedrock token; JWT auth/DB). The cancel test patches the engine with a `_StubEngine`, so the real `execute()` is never invoked; `test_logout` has zero engine references. Logged to `deferred-items.md` (SCOPE BOUNDARY — not fixed).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The `ExecutionContext` seam is in place and threaded; plans 02-02 (migrate-complete + delete dead `_handle_revision`) and 02-03 (parent-run ownership check + denial test) can build directly on it.
- Phase 7 owes the `current_task_block` → `TaskLoopStrategy` reclaim (D-02).
- Migration-ledger L14/D1 rows remain `☐` (to be flipped by 02-02/02-03 with their verbatim grep patterns once the dead-code deletion + ownership check land).

## Known Stubs
None — no stub/placeholder data introduced. `ExecutionContext.depth` and `accumulated_outputs` are real fields with backing (depth=0 default; accumulated_outputs is the sanctioned legacy mirror), not UI-facing stubs.

## Self-Check: PASSED

- `backend/agents/execution_engine/context.py` — FOUND
- `backend/tests/agents/test_execution_context.py` — FOUND
- `.planning/phases/02-executioncontext-ownership-0b/02-01-SUMMARY.md` — FOUND
- Commit `5a71931` (Task 1) — FOUND
- Commit `8b90fd2` (Task 2) — FOUND
- L14 grep over project source — 0 matches
- Statelessness grep — only the 3 `__init__` singletons remain
- Phase 0A characterization suite — 268 passed, 18 skipped (green)

---
*Phase: 02-executioncontext-ownership-0b*
*Completed: 2026-06-07*
