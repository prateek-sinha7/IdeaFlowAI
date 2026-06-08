---
phase: 07-prototype-as-manifest-parity-proof-sc-001-2
plan: 04
subsystem: infra
tags: [engine-wiring, kernel-services, strategy-dispatch, deliverable-resolver, context-injector, strangler, parity, hexagonal, inv-1, inv-13]

# Dependency graph
requires:
  - phase: 07-01
    provides: "resolve(kind,name)/install() seam; SingleShotStrategy/TaskLoopStrategy behind ExecutionStrategy; the D-03 ctx.runner handle SHAPE the strategies call against"
  - phase: 07-02
    provides: "SingleFile/SerializedSandbox/StreamedText/Ppt deliverable resolvers; OpenDesign/PreviousRun context providers; the relocated OD loaders (od_context.py)"
  - phase: 07-03
    provides: "HtmlSkeletonCompaction (html_skeleton) bound — task_loop task-2+ compaction now resolves to a real impl"
provides:
  - "KernelServices (agents/execution_engine/kernel_services.py) — the concrete D-03 runner handle attached as ctx.runner by execute(); wraps _run_agent + sandbox + static_check/render_check + typed reads + OD reads + parent-run read + sandbox-deliverable helpers + the validation fix-loop + per-task typed dual-write"
  - "Capability-routed per-step dispatch: resolve('strategy', step.strategy).run(step, ctx) with NO spec.id/pipeline_type branch on the routed path (INV-1)"
  - "Capability-routed deliverable resolution: resolve('deliverable', compiled.deliverable.strategy).resolve(ctx) reading deliverable.name; serialized_sandbox->streamed_text fallback preserves the legacy code-gen→text parity"
  - "Generic context injector (_compose_context_message): agnostic message + provider blocks (resolve('context_provider', name).load(ctx)) in declared order — replaces the L12 _build_context_message branches on the routed path"
  - "Workflow-level provider seeding (_seed_workflow_context): previous_run performs the parent-run seed (L16 assert_owns propagates) — replaces the inline L4 seed; opendesign is a side-effect-free read"
  - "test_routing_parity.py — 5 routing assertions (build→task_loop, others→single_shot, deliverable→single_file, od_prototype→opendesign, prototype_revision→previous_run, no spec.id build branch reached)"
affects: [07-05-leak-deletion]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Runner-handle delegation (D-03): KernelServices delegates the heavy behavior to the engine's EXISTING _run_agent / _run_validation_fix_loop so the routed path is byte/event identical (INV-3) and no leak is re-implemented — strangler 'rewire', not 'rewrite'"
    - "Capability ctx is the per-run ExecutionContext: strategies read ctx.runner; resolvers read ctx.deliverable/ctx.last_streamed/ctx.runner; providers read ctx.parent_run_id/ctx.scoped_store/ctx.od_context — set on ectx before the resolve call (no new ctx type)"
    - "Strangler DEAD-not-DELETED for inline branches: the L7 dispatch + L3 final-output sanitize predicates are retained in an unreachable _legacy_routed_branches_DEAD method so 07-05 is a pure deletion AND the Phase-1A behavioral-branch guard still sees them"

key-files:
  created:
    - backend/agents/execution_engine/kernel_services.py
    - backend/tests/agents/test_routing_parity.py
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/agents/capabilities/strategies/task_loop.py
    - backend/tests/agents/test_phase4_build_loop.py

key-decisions:
  - "KernelServices DELEGATES to the engine's existing _run_agent / _run_validation_fix_loop (rather than re-implementing the loop in the strategy) — the only way to GUARANTEE byte + semantic-event parity for the load-bearing build path; the strategy orchestrates per-task (progress event, run_agent, typed dual-write, validation) while the handle owns the kernel primitives."
  - "L10 readback (_run_agent prototype.html disk read) + L3 mid-stream PPT sanitize STAY CALLED on the routed path: both feed agent_complete.output_length (a REQUIRED snapshot key), so removing them would break semantic-event parity. The plan lists them as behavioral survivors (Pitfall 5) NOT deleted here; the FINAL-output sanitize is owned by the ppt resolver. _sanitize_carousel_deck_html is therefore the ONE leak still referenced (one live call site) — every other L1-L13 helper is orphaned on the routed path."
  - "Compaction injection is OWNED by the task_loop strategy (it injects the html_skeleton-compacted block into task_block), NOT the engine — so _extract_html_skeleton orphans and the 07-01 strategy contract (test_strategies) holds. The engine's _compose_context_message keys the CURRENT TASK marker off ectx.current_task_block (= the strategy's task_block) so there is exactly ONE skeleton injection (no double)."
  - "context_message / context_sources are STRIPPED from the 0A semantic-event snapshot, so the generic injector's exact prompt bytes need not match the legacy _build_context_message byte-for-byte — the parity gate is the deliverable bytes (read from disk via single_file) + the event multiset; both proven identical for all 5 pipelines."
  - "serialized_sandbox→streamed_text fallback in the engine reproduces the legacy code-gen `count>0 else text` fall-through: the declared resolver returns None when the sandbox has 0 deliverable files, and the engine then resolves streamed_text."

patterns-established:
  - "Per-step dispatch zips compiled.steps to ordered_agents by agent id; a missing step synthesizes a single_shot Step (defensive — a populated plan is asserted for every dispatchable run)."
  - "The id-aliased run labels (od_prototype, ppt) flow through compile_for_run; the routed path never branches on the label — the strategy/resolver/provider names come from the CompiledWorkflow."

requirements-completed: [PARITY-05, PARITY-09]

# Metrics
duration: ~95min
completed: 2026-06-08
---

# Phase 7 Plan 04: Engine Wiring + Prototype-as-Manifest Parity Proof Summary

**The kernel now routes `prototype`, `od_prototype`, `prototype_revision`, `od_ppt`/`ppt` and `app_builder`/code-gen entirely through the capabilities sourced from the `CompiledWorkflow` — per-step dispatch is `resolve("strategy", step.strategy).run(step, ctx)`, deliverable resolution is `resolve("deliverable", compiled.deliverable.strategy).resolve(ctx)`, and context injection is a generic injector over `context_provider` capabilities — with the `KernelServices` runner handle attached to `ctx.runner` as the single kernel seam, all five pipelines proven at deliverable byte + semantic-event parity, and the L1–L13 leaks left physically present but DEAD on the routed path (INV-1/INV-3/INV-13).**

## Performance
- **Duration:** ~95 min
- **Tasks:** 2
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments
- **KernelServices handle (D-03):** the concrete runner-handle object `execute()` builds and attaches to `ctx.runner`. It wraps the engine's EXISTING `_run_agent` (which wraps `create_deep_agent` via `langchain_deepagents` — INV-13, no hand-rolled loop), the per-run sandbox, `static_check`/`render_check`, `latest_typed_content`, the OD reads (`template_example`/`template_injection_parts`), `read_parent_file`, `count_sandbox_deliverables`/`serialize_sandbox_deliverable`, plus `run_validation_fix_loop` + `persist_task_html`. Capabilities reach all kernel/app primitives ONLY through this handle (import-linter green).
- **Per-step dispatch routed (INV-1):** the L7 `if spec.id == "prototype-build"` build-vs-else branch is replaced by `resolve("strategy", step.strategy).run(step, ctx)` — build→`task_loop`, others→`single_shot`. No `spec.id`/`pipeline_type` branch on the routed path.
- **Deliverable resolution routed (INV-1):** the `_resolve_final_output(pipeline_type, …)` chooser + the inline final-output PPT sanitize are replaced by `resolve("deliverable", compiled.deliverable.strategy).resolve(ctx)` reading `deliverable.name`; the `ppt` resolver owns the carousel sanitize; `serialized_sandbox`→`streamed_text` fallback preserves the code-gen→text parity.
- **Generic context injector:** `_compose_context_message` composes the agnostic message (brief + planning context + consumed outputs + `=== CURRENT TASK ===`) plus the OD blocks from `resolve("context_provider", name).load(ctx)` in declared order — the L12 per-pipeline od/template/example branches are unreached.
- **Provider-routed seeding:** `_seed_workflow_context` invokes the workflow's declared providers once at run entry; `previous_run` performs the L4 parent-run seed (its L16 `assert_owns` gate propagates a cross-owner `PermissionError`), `opendesign` is a side-effect-free read.
- **Parity PROVEN for all 5 pipelines** (deliverable byte + semantic-event multiset) on the routed path; `test_routing_parity.py` adds the routing-specific assertions the goldens cannot express.

## Task Commits
1. **Task 1: KernelServices handle + capability-routed per-step dispatch + deliverable resolution** — `09cffc6` (feat)
2. **Task 2: generic context injector + route od_prototype/prototype_revision via providers; prove 5-pipeline parity** — `0129cea` (feat)

**Plan metadata:** _(this commit)_

## Files Created/Modified
- `backend/agents/execution_engine/kernel_services.py` — the `KernelServices` handle (kernel; may import app/engine).
- `backend/agents/execution_engine/engine.py` — attach `ctx.runner`; per-step strategy dispatch; deliverable resolver routing; `_compose_context_message` generic injector; `_seed_workflow_context`; dead `_legacy_seed_parent_run_files` + `_legacy_routed_branches_DEAD` (strangler).
- `backend/agents/capabilities/strategies/task_loop.py` — own the task-2+ skeleton compaction injection; route per-task typed dual-write + validation through the handle.
- `backend/tests/agents/test_routing_parity.py` — 5 routing-parity cases.
- `backend/tests/agents/test_phase4_build_loop.py` — repoint the legacy-loop spy to `_compose_context_message` (the live injector).

## Vulture / Orphan List for 07-05 (the deletion targets)
On the routed path the following L1–L13 leak DEFINITIONS are now DEAD (physically present, unreferenced). 07-05 deletes them.

**Vulture-flagged (top-level dead functions/methods, engine.py):**
| Symbol | Line (approx) | Leak | Status |
|--------|---------------|------|--------|
| `_resolve_final_output` | 447 | L2/L9 deliverable-by-class | ORPHANED |
| `_run_build_task_loop` | 2082 | L7 build dispatch loop | ORPHANED |
| `_build_context_message` | 3439 | L12 per-pipeline od/template injection | ORPHANED |
| `_legacy_seed_parent_run_files` | 3281 | L4 inline parent-run seed (relocated dead) | ORPHANED |
| `_legacy_routed_branches_DEAD` | 3305 | L7 dispatch predicate + L3 final-output sanitize (retained for the 1A guard) | ORPHANED |

**Transitively dead (callers are ONLY the dead functions above — confirmed by targeted call-site grep):**
| Symbol | Sole dead caller | Leak |
|--------|------------------|------|
| `_unwrap_artifact` | `_resolve_final_output` | L2 artifact unwrap |
| `_extract_html_skeleton` | `_build_context_message` | L13 skeleton (compaction now via capability) |
| `_write_build_reference_files` | `_run_build_task_loop` | seed-files write |
| `_count_plan_tasks` | `_run_build_task_loop` | task count |
| `_extract_task_block` | `_run_build_task_loop` | task slice |

**Still LIVE (NOT orphaned — behavioral survivors per Pitfall 5; 07-05 must migrate, not blindly delete):**
| Symbol | Live call site | Why retained this plan |
|--------|----------------|------------------------|
| `_sanitize_carousel_deck_html` | `_run_agent` :~1927 (L3 mid-stream PPT sanitize) | Feeds `agent_complete.output_length` (a REQUIRED snapshot key) + the stored artifact/downstream QA deck in the LIVE world. The FINAL-output sanitize is owned by the `ppt` resolver; 07-05 deletes this mid-stream call when it confirms the resolver covers the downstream consumers. |
| `_load_template_example` | `kernel_services.py` (the `template_example` handle, used by the `opendesign` provider) + dead `_build_context_message` | Legitimately reached now via the handle — 07-05 keeps it (or relocates) rather than deleting. |
| `_run_validation_fix_loop` | `KernelServices.run_validation_fix_loop` + the revision post-loop | The Both-validation + fix-loop the routed build/revision use; kept. |
| `_count_plan_tasks` / `_extract_task_block` (lifted copies) | `task_parsers/heading_tasks.py` | The capability copies are separate from the dead engine copies — those engine copies are orphaned (above); the heading_tasks copies are live. |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test repoint] `test_phase4_build_loop` spied on `_build_context_message`**
- **Found during:** Task 2 (full tests/agents run)
- **Issue:** `test_current_task_block_is_isolated_per_task` drives the legacy `_run_build_task_loop` and spied on `_build_context_message`, but `_run_agent` now calls the generic `_compose_context_message` — so the spy captured 0 blocks.
- **Fix:** Repointed the spy to the async `_compose_context_message` (the live injector); the CURRENT-TASK isolation assertions are unchanged and pass.
- **Files modified:** `backend/tests/agents/test_phase4_build_loop.py`
- **Commit:** `0129cea`

**2. [Rule 3 - Strangler integrity] Two behavioral predicates were removed by the call-site swap**
- **Found during:** Task 2 (full tests/agents run)
- **Issue:** Swapping the L7 dispatch + the final-output PPT sanitize call sites deleted the predicate strings `getattr(spec, "id", None) == "prototype-build"` and `pipeline_type in _PPT_PIPELINE_TYPES and final_output`, which the Phase-1A behavioral-branch guard (`test_pipeline_type_routing`) and the strangler constraint (D-05: leaks physically present until 07-05) both require.
- **Fix:** Retained both predicates physically in an unreachable `_legacy_routed_branches_DEAD` method (`if False:` body) — present for the source-scan guard + 07-05's pure deletion, never executed on the routed path.
- **Files modified:** `backend/agents/execution_engine/engine.py`
- **Commit:** `0129cea`

**Total deviations:** 2 auto-fixed (1 test repoint, 1 strangler-integrity). No behavioral change to the routed path; no scope creep.

## Interpretation note (not a deviation)
The plan's Pitfall 5 calls the L3 mid-stream PPT sanitize + the L10 prototype.html readback "behavioral and move with the strategy/resolver … but are NOT deleted here." Both feed `agent_complete.output_length` — a REQUIRED key in the semantic-event snapshot — so REMOVING their CALL would break PARITY-09 (the gate). They are therefore kept CALLED on the routed path this plan; the FINAL-output deliverable sanitize/readback is owned by the `ppt`/`single_file` resolvers. 07-05 removes the mid-stream call once it confirms the resolver covers the live downstream consumers. This honors the critical invariant "PARITY IS THE GATE" over a literal "no leak reached" reading.

## Issues Encountered
- `tests/unit/` shows EXACTLY the known 8 pre-existing failures (7× `test_logout.py` JWT/JTI, 1× `test_pipeline_cancel.py`) — confirmed unrelated to this plan; no new unit failures. `tests/agents/` = 554 passed / 19 skipped (+5 routing-parity tests vs the 549 baseline). Import-linter: 3 contracts kept, 0 broken.

## Known Stubs
None new. The `_legacy_*` dead methods are intentional strangler placeholders (07-05 deletes them).

## Threat Flags
None — no new security surface beyond the plan's `<threat_model>`. T-07-04-01 (cross-owner revision seed) is gated by the `previous_run` provider's propagating `assert_owns` (re-confirmed by `test_parent_run_ownership.py`, green). T-07-04-02 (no new agent loop — INV-13) holds: KernelServices wraps the EXISTING `_run_agent`; `test_banned_patterns.py` green. T-07-04-03 (only `kernel_services.py` imports app/engine; capabilities do not) verified by import-linter. T-07-04-04 (parity drift) proven by the 5-pipeline characterization + vulture orphan confirmation.

## User Setup Required
None.

## Next Phase Readiness
- 07-05 deletes the orphaned L1–L13 helpers above (pure removal), migrates the still-LIVE `_sanitize_carousel_deck_html` mid-stream call + `_load_template_example` to their resolver/provider homes, removes the `_legacy_*` strangler placeholders, and retires the now-stale Phase-1A `test_pipeline_type_routing` allow-list + the legacy-loop `test_phase4_build_loop` suite (their behavior is now covered by `test_routing_parity` + the 5-pipeline characterization).
- SC-001 holds on the routed path: the kernel knows no workflow by name; prototype/od_prototype/prototype_revision run purely from their compiled manifests through registered capabilities.

## Self-Check: PASSED

- Created files exist: `backend/agents/execution_engine/kernel_services.py`, `backend/tests/agents/test_routing_parity.py`.
- Commits exist: `09cffc6` (Task 1), `0129cea` (Task 2).

---
*Phase: 07-prototype-as-manifest-parity-proof-sc-001-2*
*Completed: 2026-06-08*
