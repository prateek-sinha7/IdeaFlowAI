---
phase: 04-manifest-compiler-1a
plan: 03
subsystem: engine
tags: [workflow-compiler, manifests, capability-registry, yaml, dataclass, parity, no-dsl]

# Dependency graph
requires:
  - phase: 04-01
    provides: "agents/capabilities/{base,registry} — CapabilityRegistry.is_registered + the 14 known (kind,name) capability names"
  - phase: 04-02
    provides: "agents/workflows/{plan,manifest} — CompiledWorkflow/Step/Task typed contract + WorkflowManifest loader (strict-key, MAN-01/D-08)"
provides:
  - "WorkflowCompiler.compile(manifest, registry) -> CompiledWorkflow — thin no-DSL name-resolve + topo-validate (MAN-02/MAN-03/INV-1/INV-4/INV-5)"
  - "15 hand-authored workflow.yaml manifests (one per PIPELINE_AGENTS key; no od_prototype dir — alias only)"
  - "Coverage + the two parity-trap tests (planner: run everywhere; clarify.defaults == engine _pipeline_defaults verbatim)"
affects: [04-04, phase-05, phase-06, phase-07, routing-seam, api-01]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Thin no-DSL compiler: pure data transform, name-resolution against a (kind,name) registry, no workflow-name branch, no eval/exec"
    - "Hand-authored manifests grounded in PIPELINE_AGENTS order; capability references validated at compile time"
    - "Parity locked by dedicated unit tests (not snapshots) for the two routing concerns snapshots cannot catch"

key-files:
  created:
    - backend/agents/workflows/compiler.py
    - backend/agents/workflows/{user_stories,user_stories_revision,ppt,ppt_revision,od_ppt,od_ppt_revision,prototype,prototype_revision,app_builder,app_builder_revision,mulesoft_to_springboot,dotnet_to_azure,custom,reverse_engineer,chat}/workflow.yaml
    - backend/tests/agents/test_compiler.py
    - backend/tests/agents/test_manifest_coverage.py
    - backend/tests/agents/test_manifest_parity.py
    - backend/tests/agents/test_edge_manifests.py
  modified: []

key-decisions:
  - "Step-order coverage assertion compares against get_pipeline_agents(id) when non-empty, else PIPELINE_AGENTS[id] — the ppt agents declare pipeline_type: od_ppt (shared), so get_pipeline_agents('ppt') is empty while PIPELINE_AGENTS['ppt'] has 3"
  - "clarify.defaults hard-copied verbatim into a test constant with engine.py:752-761 citation (the engine dict is function-local, not importable)"
  - "No `description:` key in the reverse_engineer/chat manifests — it is not in the manifest strict-key allow-list (would be rejected); 'agents TBD' lives in a comment instead"
  - "Inlined per-kind is_registered calls in the compiler (vs one helper) so the validation surface is auditable and satisfies the >=5 is_registered acceptance grep"

patterns-established:
  - "Compiler = name-resolve + topo-validate only; unknown reference -> CompilerError naming the bad ref"
  - "Every dispatchable manifest declares planner: run because SKIP_PLANNER_FOR_PROTOTYPE=False"

requirements-completed: [MAN-02, MAN-03, MAN-04]

# Metrics
duration: 7min
completed: 2026-06-07
---

# Phase 4 Plan 03: Thin no-DSL WorkflowCompiler + 15 manifests + parity tests Summary

**Thin no-DSL WorkflowCompiler (name-resolve every capability ref against CapabilityRegistry + topo-validate the Step DAG, zero workflow-name branches) plus all 15 hand-authored workflow.yaml manifests grounded in PIPELINE_AGENTS, with the two parity traps (planner: run everywhere; clarify.defaults == engine _pipeline_defaults verbatim) locked by dedicated tests.**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-06-07T16:15:21Z
- **Completed:** 2026-06-07T16:22:04Z
- **Tasks:** 3
- **Files modified:** 20 (compiler + 15 manifests + 4 test files)

## Accomplishments
- `WorkflowCompiler.compile` resolves strategy/validators/gates/task_parser/compaction/context_provider/deliverable names against the registry (7 `is_registered` call sites), names the bad reference on failure (INV-4), topo-validates the Step DAG (duplicate-agent + Kahn cycle check), and contains no `pipeline_type`/workflow-name branch and no eval/exec (INV-1/INV-5).
- All 15 manifests authored in `get_pipeline_agents`/`PIPELINE_AGENTS` order; the `prototype` SC-001 manifest has the `task_loop` build step (heading_tasks parser, html_static/html_render validators, html_skeleton compaction) and `gates: [human]` on specify/plan.
- Both parity traps locked: every dispatchable manifest declares `planner: run`; each manifest's `clarify.defaults` equals the engine `_pipeline_defaults` entry verbatim (revisions/edge ids reuse the `custom` list).
- Edge cases: `reverse_engineer` compiles to an empty plan (`steps: []`); `chat` compiles (7 agents) and is engine-non-dispatchable (`_INTERNAL_PIPELINES`, `allowed_custom_agent_ids("chat") == set()`).

## Task Commits

Each task was committed atomically:

1. **Task 1: WorkflowCompiler — name-resolve + topo-validate, no DSL** - `77a2ae6` (feat) — test + impl (TDD: RED via missing module, then GREEN)
2. **Task 2: Hand-author the 15 workflow.yaml manifests** - `f116c3a` (feat)
3. **Task 3: Coverage + parity + edge-case tests** - `21693cf` (test)

_Task 1 was authored test-first; the test file and implementation landed in one commit after RED was confirmed (ModuleNotFoundError) and GREEN reached (11 passed)._

## Files Created/Modified
- `backend/agents/workflows/compiler.py` - `WorkflowCompiler` + `CompilerError`; thin no-DSL compile (name-resolve + topo-validate)
- `backend/agents/workflows/*/workflow.yaml` (15 dirs) - one manifest per PIPELINE_AGENTS key; pure data, no DSL
- `backend/tests/agents/test_compiler.py` - clean compile, unknown-ref naming (6 kinds), DSL rejection, no-name-branch structure, empty plan (11 tests)
- `backend/tests/agents/test_manifest_coverage.py` - all 15 load+compile + step-order equality (16 tests)
- `backend/tests/agents/test_manifest_parity.py` - planner: run parity + clarify.defaults verbatim parity (26 tests)
- `backend/tests/agents/test_edge_manifests.py` - reverse_engineer empty plan + chat non-dispatchable (2 tests)

## Decisions Made
- **ppt step-order source:** the ppt agents physically declare `pipeline_type: od_ppt`, so `get_pipeline_agents("ppt")` returns `[]`. The coverage assertion uses `get_pipeline_agents(id)` when non-empty and `PIPELINE_AGENTS[id]` otherwise — verified the two agree everywhere `get_pipeline_agents` is non-empty (only `ppt` differs).
- **clarify.defaults parity source:** the engine `_pipeline_defaults` dict is local to `execute()` and not importable; the test hard-copies the lists verbatim with an `engine.py:752-761` citation and a "keep in lockstep" comment.
- **No `description:` key** in the stub manifests — it is not in `_ALLOWED_TOP_KEYS`; the plan's illustrative `description: "agents TBD"` would be strict-key-rejected, so the note lives in a comment.
- **Inlined `is_registered` calls** per capability kind in the compiler (rather than one private helper) so the validation surface is explicit/auditable and meets the `>=5` acceptance grep.

## Deviations from Plan

None - plan executed exactly as written. (The two clarifications above — `ppt` step-order source and the no-`description` strict-key reality — are faithful reconciliations of the plan against the actual 04-01/04-02 code, not behavior changes.)

## Issues Encountered
- `get_pipeline_agents("ppt")` returns empty (shared od_ppt agents). Resolved by sourcing the coverage step-order expectation from `PIPELINE_AGENTS[id]` when `get_pipeline_agents(id)` is empty, with a citation comment.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The `CompiledWorkflow` + 15 compiled manifests are ready for 04-04 to route `execute()` off (replacing the four routing concerns: agent list, clarify defaults, planner skip, od_prototype alias).
- Parity is provable before the engine routes off the plan (the #1 parity risk per RESEARCH) — both traps have dedicated guards.
- `lint-imports` green (1 contract kept, 0 broken); `test_migration_ledger.py` green (no behavioral engine line touched).

## Self-Check: PASSED

- All 5 created source/test files exist on disk.
- All 15 `workflow.yaml` manifests present; no `od_prototype` dir.
- All 3 task commits (`77a2ae6`, `f116c3a`, `21693cf`) exist in git.
- Plan verification suite: 59 passed. `lint-imports`: 1 kept / 0 broken. `test_migration_ledger.py`: 4 passed / 1 skipped.

---
*Phase: 04-manifest-compiler-1a*
*Completed: 2026-06-07*
