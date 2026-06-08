# Phase 7: Prototype as Manifest — Parity Proof (SC-001) [2] — Specification

**Created:** 2026-06-08
**Ambiguity score:** 0.08 (gate: ≤ 0.20)
**Requirements:** 11 locked

## Goal

The `prototype`, `od_prototype`, and `prototype_revision` workflows run with **all
capability behavior sourced from their compiled manifests** — `single_shot`/`task_loop`
strategies, `single_file`/`serialized_sandbox`/`streamed_text`/`ppt` resolvers, `opendesign`/
`previous_run` providers, `seed_files`, `heading_tasks` parser, and `html_skeleton` compaction
all implemented behind the existing capability ports — and the hardcoded kernel leaks **L1–L13
are deleted**, so `grep` for `if pipeline_type`/`spec.id ==` and the L1–L13 patterns returns **0
in the kernel** (`agents/execution_engine/`) while every pipeline stays at deliverable + semantic
event parity vs the post-0C baseline. **This is the SC-001 core-value proof: the kernel knows no
workflow by name.**

## Background

Phases 1–6 built the substrate. The manifests are already authored (Phase 4): `prototype/
workflow.yaml` declares `strategy: single_shot|task_loop`, `deliverable.strategy: single_file`,
`context_providers: [opendesign]`, `task_source.parser: heading_tasks`, `validators:
[html_static, html_render]`, `compaction: html_skeleton`; `prototype_revision` declares
`context_providers: [previous_run]` + `gates: [validation]`; `ppt` declares `deliverable.strategy:
ppt`. The capability **ports** exist (`agents/capabilities/base.py`: `ExecutionStrategy`,
`DeliverableResolver`, `ContextProvider`, `TaskParser`, `Validator`, `GateHandler` Protocols).
The capability **registry holds names only** (`agents/capabilities/registry.py`, 15 `(kind,name)`
pairs) — **no implementations**.

But the engine (`agents/execution_engine/engine.py`, 3592 lines) **still does the work via
hardcoded leaks**. `compile_for_run()` (engine.py:223) produces a `CompiledWorkflow` and the
engine reads membership/order/deliverable-name/clarify-defaults from it (Phase 4), yet the actual
behavior is hardcoded in **L1–L13**, all confirmed present:

| Leak | Construct | Location |
|------|-----------|----------|
| L1 | `_PPT_PIPELINE_TYPES` / `_PROTOTYPE_PIPELINE_TYPES` / `REVISION_FILE_NAME` | engine.py:165,177,182 |
| L2/L9 | `_resolve_final_output` (deliverable chooser) | engine.py:447 |
| L3 | `_sanitize_carousel_deck_html` / `_unwrap_artifact` (ppt) | engine.py:363,427 |
| L4/L8 | `prototype_revision` seeding + post-fix | engine.py:489–650,917–962 |
| L5 | `SKIP_PLANNER_FOR_PROTOTYPE` (defined in `agents/prototype/pipeline.py`) | engine.py:1077–1105 |
| L6 | `ALWAYS_CLARIFY` defaults dict | engine.py:153,1105 |
| L7 | `spec.id == "prototype-build"` dispatch | engine.py:3321,3404 |
| L10 | `pipeline_type in ("od_prototype","prototype")` HTML readback | engine.py:1902 |
| L11 | build-loop internals (`_run_build_task_loop`/`_write_build_reference_files`/`_count_plan_tasks`/`_extract_task_block`/`_run_validation_fix_loop`/`_load_template_example`) | engine.py:2072+ |
| L12 | `_build_context_message` per-pipeline od/ppt/build branches | engine.py:1586,2378+ |
| L13 | `_extract_html_skeleton` (0C compaction, wired inline) | engine.py:3514 |

**Ledger state (`specs/003-workflow-engine-decoupling/migration-ledger.md`):** L14 (Phase 0B), L15
(Phase 1B), L16 (Phase 0B) are already `☑` done. **D1 is voided** — `_handle_revision` is the live
`run_revision` PPT-revision handler, not dead code. The remaining engine-leak rows are **L1–L13**.
The ledger ratchet (`tests/agents/test_migration_ledger.py`) runs `grep -rnE <pattern> backend/
--include=*.py` and asserts 0 matches for each `☑` grep row; the banned-pattern gate (Phase 1) holds
the L7/L10 `pipeline_type`/`spec.id` reservation as warn-only until this phase flips it to hard-fail.

**The gap:** implement the 9 declared capability families behind the ports, wire the engine to route
behavior *through* them (reading the compiled manifest), and delete L1–L13 — proving INV-1.

## Requirements

1. **Execution strategies (`single_shot` + `task_loop`)**: Both strategies implemented behind the
   `ExecutionStrategy` port; the engine routes every step through the strategy named in the compiled
   manifest.
   - Current: NAME-only in the registry; behavior hardcoded — build runs via `_run_build_task_loop`
     gated by `spec.id == "prototype-build"`; non-build steps run inline. The N=2 Both-validation
     fix-loop is `_run_validation_fix_loop`.
   - Target: `single_shot` (one agent run → deliverable) and `task_loop` (per-task sub-agent loop +
     `heading_tasks` parse + per-task `html_skeleton` compaction + **the validation + bounded N=2
     fix-loop behavior moved in**, calling the existing `static_check`/`render_check` functions
     inline). Engine dispatches on `step.strategy`, never on `spec.id`/`pipeline_type`.
   - Acceptance: prototype build step runs via the `task_loop` strategy with no `spec.id ==
     "prototype-build"` branch; a unit test drives both strategies from a compiled `Step`; the 0A
     prototype build semantic event snapshot holds.

2. **Deliverable resolvers (`single_file` / `serialized_sandbox` / `streamed_text`)**: Three
   `DeliverableResolver` implementations; the engine resolves the final deliverable via the resolver
   named in `deliverable.strategy`.
   - Current: `_resolve_final_output` (engine.py:447) hardcodes the chooser; the HTML readback is
     gated by `pipeline_type in ("od_prototype","prototype")` (engine.py:1902).
   - Target: `single_file` (read `deliverable.name`, e.g. `prototype.html`), `serialized_sandbox`
     (`serialize_sandbox_deliverable` → `filename:` blocks for code-gen), `streamed_text` (last
     streamed text). Resolution reads `deliverable.name` from the manifest — no name/id branch.
   - Acceptance: prototype/od_ resolve `prototype.html` via `single_file`; code-gen via
     `serialized_sandbox`; `_resolve_final_output` and the L10 readback branch deleted; deliverable
     byte-identical to the post-0C golden for each.

3. **PPT resolver + transform (`ppt`)**: The `ppt` deliverable handled by a `ppt` resolver plus a
   declared post-step transform/validator (PARITY-07 / L3).
   - Current: `_sanitize_carousel_deck_html` + `_unwrap_artifact` (engine.py:363,427) inline; applied
     at engine.py:1394.
   - Target: a `ppt` resolver wrapping the streamed-text read + carousel-sanitize transform as a
     declared capability (no inline call from the kernel).
   - Acceptance: ppt/od_ppt deliverable byte-identical to golden; `_sanitize_carousel_deck_html` /
     `_unwrap_artifact` deleted (L3 grep → 0 in the kernel).

4. **Context providers + seed_files + task parser (`opendesign` / `previous_run` / `heading_tasks`)**:
   The two providers + a generic context injector, declared `seed_files` (incl. `from_run`), and the
   `heading_tasks` parser implemented and used by the manifests (PARITY-03 / L11/L12).
   - Current: `_build_context_message` (engine.py:1586,2378+) holds per-pipeline od/ppt/build
     injection branches; heading parsing is inline in the build loop; revision seeding is inline
     (engine.py:489–650). The live OpenDesign template/example loaders are
     `agents/prototype/context.py` (`load_prototype_context`, `get_template_injection_parts`,
     `get_example_html`), imported directly by the engine.
   - Target: `opendesign` ContextProvider (**re-homes the live `agents/prototype/context.py`
     functions**), `previous_run` ContextProvider (seeds parent run spec/design/tasks), a generic
     declarative context injector replacing the per-pipeline branches, `heading_tasks` TaskParser,
     and `seed_files` materialization including `seed_files.from_run` for revision.
   - Acceptance: `_build_context_message` per-pipeline branches deleted (L12 grep → 0 in kernel);
     od_prototype injects template/design_system via the `opendesign` provider; prototype_revision
     seeds parent context via `previous_run` + `seed_files.from_run`; the context-message semantic
     snapshot holds.

5. **`html_skeleton` CompactionStrategy (re-express 0C)**: The Phase 0C build compaction registered as
   a `CompactionStrategy` and applied by `task_loop` via `compaction: html_skeleton` (PARITY-04 / L13).
   - Current: `_extract_html_skeleton` (engine.py:3514) wired inline into build task-2+ context (0C).
   - Target: an `html_skeleton` `CompactionStrategy` capability; `task_loop` applies it via the
     declared `compaction` field — behavior-preserving vs 0C.
   - Acceptance: build task-2+ compaction routed through the capability; `_extract_html_skeleton`
     deleted (L13 grep → 0 in kernel); the 0C deterministic **≥50% reduction** CI gate still passes.

6. **Minimal capability name→impl resolution**: A thin lookup/factory binds each declared capability
   name to its implementation, over the existing name registry as source of truth.
   - Current: `CapabilityRegistry.is_registered` is pure name membership; no name→impl resolution
     exists.
   - Target: a minimal resolution seam (lookup/factory keyed by `(kind, name)`) the engine uses to
     obtain a capability instance for a compiled step. **NOT** self-registration decorators / startup
     `discover()` / trust flags (those stay Phase 8).
   - Acceptance: the engine obtains every strategy/resolver/provider/parser/compaction via the
     resolution seam (no direct hardcoded construction by name); no `@register` decorator or
     `discover()` machinery added; `registry.py`'s "names only" scope note remains accurate.

7. **Three workflows run purely from manifests**: `prototype`, `od_prototype` (alias + OpenDesign
   provider), and `prototype_revision` (`seed_files.from_run` + `previous_run` provider + post-edit
   validation gate behavior) execute end-to-end with capability behavior sourced only from the
   compiled manifest (PARITY-05).
   - Current: manifests authored, but behavior comes from the L1–L13 leaks; the engine still branches
     on `pipeline_type`/`spec.id`.
   - Target: all three produce their deliverable + event stream with the kernel reading only the
     compiled manifest's declared capabilities — including the revision post-edit validation behavior
     (preserved, not the formal GateHandler registry).
   - Acceptance: prototype, od_prototype, and prototype_revision are at deliverable + semantic event
     parity with the post-0C baseline, with no kernel code reading their names.

8. **Delete kernel leaks L1–L13 + drop the dead legacy module**: Each leak moved-then-deleted
   (INV-12 move-don't-copy); the dead `agents/prototype/pipeline.py` removed (PARITY-06).
   - Current: L1–L13 all present in `engine.py`; `agents/prototype/pipeline.py` (dead in live code —
     only `tests/agents/test_manifest_parity.py` imports `SKIP_PLANNER_FOR_PROTOTYPE` from it) carries
     `PROTOTYPE_PIPELINE_TYPES`, `is_prototype_pipeline`, a `pipeline_type == "prototype_revision"`
     branch, and the L5 constant.
   - Target: L1–L13 deleted from the kernel; `agents/prototype/pipeline.py` deleted; ledger rows
     L1–L13 flipped to `☑` with kernel-scoped grep patterns; `test_manifest_parity.py` updated to not
     import the deleted constant. `agents/prototype/context.py` is **re-homed** (Req 4), not dropped.
   - Acceptance: each ledger L1–L13 grep pattern returns 0 within the kernel (`agents/
     execution_engine/`); `agents/prototype/pipeline.py` no longer exists; the migration-ledger
     ratchet test is green; D1 remains voided (`_handle_revision` retained).

9. **Kernel has zero workflow-name/agent-id branches (INV-1)**: The `if pipeline_type`/`spec.id ==`
   grep gate returns 0 **in the kernel**, and the banned-pattern gate flips to hard-fail (PARITY-08).
   - Current: name/id dispatch branches live in `engine.py`; the L7/L10 banned-pattern reservation is
     warn-only.
   - Target: kernel (`agents/execution_engine/`) has zero name/id dispatch; the banned-pattern gate
     hard-fails on reintroduction. Legitimate **non-kernel** references (registry
     `REVISION_BASE_MAP`/`PIPELINE_AGENTS`, `app/core/entitlements.py`, `app/api/runs.py` display
     logic, tests) are retained — INV-1 is a kernel property and these are out of scope.
   - Acceptance: `grep -rnE 'if pipeline_type|spec\.id ==' agents/execution_engine/ --include=*.py`
     returns 0; the banned-pattern CI gate is green and hard-fails if a kernel name/id branch
     reappears.

10. **Re-verify L14/L15/L16 still closed**: The previously-closed ledger rows are re-asserted as Phase
    7 acceptance (belt-and-suspenders, per the decision to honor plan.md's "L1–L16" literally).
    - Current: L14/L15/L16 are `☑`; their gates pass in CI today.
    - Target: their grep/CHECK gates re-confirmed green as part of Phase 7's exit checks.
    - Acceptance: L14 pattern (`self\._(od_context|completed_tasks|current_task_block|revision_|
      gate_agent_ids)`) and L15 pattern (`accumulated_outputs`) return 0 in `backend/`; the L16
      cross-owner denial test passes.

11. **Deliverable + semantic event parity (PARITY-09)**: prototype, od_prototype, prototype_revision,
    ppt, and code-gen at deliverable parity (byte-identical where deterministic) + semantic event
    parity vs the post-0C baseline.
    - Current: 0A characterization snapshots exist; post-0C deliverable goldens were re-baselined in
      Phase 3.
    - Target: all five pipelines pass the deliverable byte-snapshot (where deterministic) and the
      normalized semantic event-stream multiset vs the post-0C baseline, after the refactor.
    - Acceptance: the 5-pipeline characterization suite is green; no net-new failure events; clean
      pipeline-complete for each.

## Boundaries

**In scope:**
- `single_shot` + `task_loop` `ExecutionStrategy` implementations (incl. moving the per-task
  validation + bounded N=2 fix-loop **behavior** into `task_loop`, calling existing `static_check`/
  `render_check` inline).
- `single_file` / `serialized_sandbox` / `streamed_text` / `ppt` `DeliverableResolver` implementations
  (+ the ppt carousel-sanitize transform as a declared capability).
- `opendesign` + `previous_run` `ContextProvider` implementations + a generic declarative context
  injector; re-homing `agents/prototype/context.py`'s OpenDesign loaders into `opendesign`.
- `heading_tasks` `TaskParser`; declared `seed_files` materialization incl. `seed_files.from_run`.
- `html_skeleton` `CompactionStrategy` (re-express Phase 0C, behavior-preserving).
- Minimal capability name→impl resolution seam (thin lookup/factory over the existing name registry).
- Wire the engine to route all of the above through the compiled manifest.
- Delete kernel leaks **L1–L13** (move-don't-copy); flip ledger rows L1–L13 to `☑`; kernel-scope each
  grep pattern; flip the banned-pattern gate to hard-fail.
- Delete the dead `agents/prototype/pipeline.py`; update `test_manifest_parity.py`.
- prototype / od_prototype / prototype_revision run purely from manifests.
- Parity verification (deliverable + semantic event) for prototype/od_/revision/ppt/code-gen.
- Re-verify L14/L15/L16 closure.

**Out of scope:**
- Self-registering `CapabilityRegistry` (`@register` + `discover()`) + trust flags — Phase 8
  (CAP-01/CAP-02). Phase 7 uses minimal name→impl resolution only.
- Formal `Validator` registry + generic fix-loop + severity mapping + Tier#4/5/6 validators — Phase 8
  (VALID-*/08-04). Phase 7 only preserves the existing validation **behavior** inside `task_loop`.
- Formal `GateHandler` registry + making `Validation_Gate` first-class — Phase 8 (GATE-*/08-02). Phase
  7 preserves the post-edit revision validation **behavior** only.
- `ToolPermissions`, `PromptAssemblyPolicy`, `AgentRuntimeAdapter`, F1–F5 factory deletions — Phase 8.
- `_handle_revision` / the `run_revision` PPT-revision handler — **D1 voided** (live handler, not dead
  code); not touched.
- Non-kernel `pipeline_type`/name references (registry `REVISION_BASE_MAP`/`PIPELINE_AGENTS`,
  `app/core/entitlements.py`, `app/api/runs.py`, `app/api/websocket.py` display strings, tests) —
  retained; INV-1 is a kernel property — because removing them would couple this phase to unrelated
  subsystems for no parity benefit.
- `agents/prototype/context.py` deletion — its functions are live and get **re-homed** (Req 4), not
  dropped.
- `RuntimeEnvironment`/`Workspace`, repo workflows, `exec`, fan-out, wave scheduler — Phases 9–12.
- Any new DB table / schema migration — Phase 7 is engine-internal + capability code, additive-only.
- New behavior — Phase 7 is parity-only (the one sanctioned non-byte change, 0C compaction, already
  landed in Phase 3 and is merely re-expressed here behind `html_skeleton`).

## Constraints

- **INV-1**: the kernel (`agents/execution_engine/`) knows no workflow by name — zero `if
  pipeline_type`/`spec.id ==` branches (kernel-scoped grep gate).
- **INV-3**: semantic event parity for all pipelines; deliverables byte-identical where deterministic,
  vs the post-0C baseline.
- **INV-12**: move-don't-copy — deletion of L1–L13 is the exit gate; no dual implementations (a
  capability that doesn't delete the leak it supersedes is not done).
- **INV-13**: every agent runs on LangChain `deepagents` (`create_deep_agent`); no hand-rolled loop.
- **Hexagonal (§31)**: the kernel depends only on the capability ports (`agents/capabilities/base.py`);
  concrete impls do not pull the kernel into an import cycle — import-linter contract stays green.
- **Strangler discipline**: prototype stays working throughout; each plan leaves the 0A
  characterization suite green.
- **Grep-gate scoping**: the L1–L13 ledger patterns must be scoped/refined to the kernel/leak
  construct so they assert kernel-leak deletion without false-matching legitimate non-kernel
  references (consistent with the existing banned-pattern single-file allow-list precedent).
- **No DSL (INV-5)**: control flow lives inside strategies, not in manifests.

## Acceptance Criteria

- [ ] `single_shot` + `task_loop` implemented behind `ExecutionStrategy`; engine routes every step
      through the manifest-declared `step.strategy` (no `spec.id`/`pipeline_type` dispatch).
- [ ] `task_loop` owns the per-task sub-agent loop + `heading_tasks` parse + `html_skeleton`
      compaction + the validation + bounded N=2 fix-loop behavior (inline `static_check`/`render_check`).
- [ ] `single_file` / `serialized_sandbox` / `streamed_text` / `ppt` resolvers implemented; engine
      resolves the deliverable via `deliverable.strategy` + `deliverable.name`.
- [ ] `opendesign` + `previous_run` providers + generic context injector + `heading_tasks` parser +
      `html_skeleton` compaction + `seed_files` (incl. `from_run`) implemented and used by the manifests.
- [ ] `agents/prototype/context.py` OpenDesign loaders re-homed into the `opendesign` provider.
- [ ] Capability name→impl resolution seam wired; no `@register`/`discover()` machinery added.
- [ ] `grep -rnE '_PROTOTYPE_PIPELINE_TYPES|_PPT_PIPELINE_TYPES'` → 0 in the kernel (L1).
- [ ] `grep -rnE '_resolve_final_output'` → 0 in the kernel (L2/L9).
- [ ] `grep -rnE '_sanitize_carousel_deck_html|_unwrap_artifact'` → 0 in the kernel (L3).
- [ ] `grep -rnE 'prototype_revision'` → 0 in the kernel (L4/L8), kernel-scoped.
- [ ] `grep -rnE 'SKIP_PLANNER_FOR_PROTOTYPE'` → 0 in the kernel (L5); `agents/prototype/pipeline.py`
      deleted.
- [ ] `grep -rnE 'ALWAYS_CLARIFY'` → 0 in the kernel (L6).
- [ ] `grep -rnE 'spec\.id == "prototype-build"'` → 0 in the kernel (L7).
- [ ] `grep -rnE 'pipeline_type in \("od_prototype", ?"prototype"\)'` → 0 in the kernel (L10).
- [ ] `grep -rnE '_run_build_task_loop|_write_build_reference_files|_count_plan_tasks|_extract_task_block|_run_validation_fix_loop|_load_template_example'` → 0 in the kernel (L11).
- [ ] `grep -rnE '_build_context_message'` → 0 in the kernel (L12).
- [ ] `grep -rnE '_extract_html_skeleton'` → 0 in the kernel (L13).
- [ ] `grep -rnE 'if pipeline_type|spec\.id =='` → 0 in `agents/execution_engine/`; banned-pattern
      gate hard-fails on reintroduction (INV-1 / PARITY-08).
- [ ] migration-ledger ratchet test green with L1–L13 flipped to `☑`; L14/L15/L16 gates re-confirmed
      green; D1 stays voided.
- [ ] prototype, od_prototype, prototype_revision run purely from their compiled manifests.
- [ ] prototype / od_prototype / prototype_revision / ppt / code-gen at deliverable parity (byte where
      deterministic) + semantic event parity vs the post-0C baseline (5-pipeline characterization suite
      green).
- [ ] 0C ≥50% compaction reduction gate still passes (html_skeleton behavior-preserving).
- [ ] import-linter contract green (kernel → ports only).

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                                        |
|--------------------|-------|------|--------|--------------------------------------------------------------|
| Goal Clarity       | 0.93  | 0.75 | ✓      | Measurable: kernel grep → 0 + 5-pipeline parity green        |
| Boundary Clarity   | 0.92  | 0.70 | ✓      | 4 Phase 7/8 seams locked; legacy-module scope precise        |
| Constraint Clarity | 0.90  | 0.65 | ✓      | INV-1/3/12/13 + kernel-scoped grep gate + additive-only      |
| Acceptance Criteria| 0.90  | 0.70 | ✓      | Per-leak grep gates + parity suite — all pass/fail           |
| **Ambiguity**      | 0.08  | ≤0.20| ✓      | Plan-authoritative; 2 interview rounds locked the 4 seams    |

Status: ✓ = met minimum, ⚠ = below minimum (planner treats as assumption)

## Interview Log

| Round | Perspective              | Question summary                                    | Decision locked                                                                 |
|-------|--------------------------|-----------------------------------------------------|---------------------------------------------------------------------------------|
| 1     | Researcher/Boundary Keeper | Validation + fix-loop split (Phase 7 vs Phase 8)?   | Behavior-preserving move: `task_loop` absorbs validation+N=2 fix-loop behavior (inline static/render); formal Validator/GateHandler registries stay Phase 8 |
| 1     | Boundary Keeper          | Capability registry mechanism scope?                | Minimal name→impl resolution in Phase 7; self-registration/`discover()`/trust stay Phase 8 |
| 1     | Boundary Keeper          | Deletion scope — plan's "L1–L16" vs ledger reality? | Delete L1–L13 **and** re-verify L14/L15/L16 still closed; D1 stays voided        |
| 2     | Seed Closer              | Grep-gate scope + deletion blast radius?            | Kernel-scoped gates + INV-1 proof; retain legitimate non-kernel refs; **additionally drop the dead `agents/prototype/pipeline.py`** (re-home its live sibling `context.py`) |

---

*Phase: 07-prototype-as-manifest-parity-proof-sc-001-2*
*Spec created: 2026-06-08*
*Next step: /gsd-discuss-phase 7 — implementation decisions (capability module layout, resolution seam shape, per-leak deletion sequencing)*
