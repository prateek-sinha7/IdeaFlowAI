# Phase 7: Prototype as Manifest — Parity Proof (SC-001) [2] - Context

**Gathered:** 2026-06-08
**Status:** Ready for planning
**Mode:** Recommended options locked (gray-area question dismissed — user chose "lock all to recommendations", mirroring Phases 1/2/4/5/6). Every decision below is the plan.md-grounded recommendation (§10/§11/§30/§31/§32). Review/edit this file before planning if any needs changing.

<domain>
## Phase Boundary

Make the **declared-but-unimplemented** capabilities (Phase 4 registered names only) **live**, then **delete the kernel leaks they supersede** — proving SC-001: a workflow runs entirely from its compiled manifest and the kernel knows no workflow by name (INV-1).

Concretely: implement `single_shot` + `task_loop` `ExecutionStrategy`; `single_file`/`serialized_sandbox`/`streamed_text`/`ppt` `DeliverableResolver`; `opendesign` + `previous_run` `ContextProvider` (+ a generic context injector); `heading_tasks` `TaskParser`; declared `seed_files` (incl. `seed_files.from_run`); `html_skeleton` `CompactionStrategy` (re-express Phase 0C). Wire the engine to route every step's behavior **through these capabilities** sourced from the `CompiledWorkflow`, then **delete L1–L13** from the kernel (move-don't-copy, INV-12) so prototype/od_prototype/prototype_revision run purely from manifests at deliverable + semantic event parity vs the post-0C baseline.

**Backend-kernel only this phase.** The per-task validation + bounded N=2 fix-loop **behavior** moves into `task_loop` (calling the existing `static_check`/`render_check` directly); the formal Validator/GateHandler registries + generic fix-loop + self-registration/`discover()`/trust stay **Phase 8**. INV-1's grep gate + the L1–L13 deletion gates are **kernel-scoped** (`agents/execution_engine/`); the dead `agents/prototype/pipeline.py` is dropped.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**11 requirements are locked.** See `07-SPEC.md` for full requirements (PARITY-01..09 + the four interview-locked boundary seams), boundaries, and acceptance criteria.

Downstream agents MUST read `07-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- `single_shot` + `task_loop` `ExecutionStrategy` impls (incl. moving the per-task validation + bounded N=2 fix-loop **behavior** into `task_loop`, inline `static_check`/`render_check`)
- `single_file` / `serialized_sandbox` / `streamed_text` / `ppt` `DeliverableResolver` impls (+ the ppt carousel-sanitize transform as a declared capability)
- `opendesign` + `previous_run` `ContextProvider` impls + a generic declarative context injector; re-homing `agents/prototype/context.py`'s OpenDesign loaders into `opendesign`
- `heading_tasks` `TaskParser`; declared `seed_files` materialization incl. `seed_files.from_run`
- `html_skeleton` `CompactionStrategy` (re-express Phase 0C, behavior-preserving)
- Minimal capability name→impl resolution seam (thin lookup/factory over the existing name registry)
- Wire the engine to route all of the above through the compiled manifest
- Delete kernel leaks **L1–L13** (move-don't-copy); flip ledger rows L1–L13 to ☑; kernel-scope each grep pattern; flip the banned-pattern gate to hard-fail
- Delete the dead `agents/prototype/pipeline.py`; update `test_manifest_parity.py`
- prototype / od_prototype / prototype_revision run purely from manifests
- Parity verification (deliverable + semantic event) for prototype/od_/revision/ppt/code-gen
- Re-verify L14/L15/L16 closure

**Out of scope (from SPEC.md):**
- Self-registering `CapabilityRegistry` (`@register` + `discover()`) + trust flags — Phase 8 (CAP-01/02). Phase 7 uses minimal name→impl resolution only.
- Formal `Validator` registry + generic fix-loop + severity mapping + Tier#4/5/6 validators — Phase 8 (08-04). Phase 7 only preserves the validation **behavior** inside `task_loop`.
- Formal `GateHandler` registry + making `Validation_Gate` first-class — Phase 8 (08-02). Phase 7 preserves the revision post-edit validation **behavior** only.
- `ToolPermissions`, `PromptAssemblyPolicy`, `AgentRuntimeAdapter`, F1–F5 factory deletions — Phase 8
- `_handle_revision` / `run_revision` PPT-revision handler — **D1 voided** (live handler); not touched
- Non-kernel `pipeline_type`/name references (registry `REVISION_BASE_MAP`/`PIPELINE_AGENTS`, `app/core/entitlements.py`, `app/api/runs.py`, `app/api/websocket.py` display strings, tests) — retained; INV-1 is a kernel property
- `agents/prototype/context.py` deletion — re-homed (live), not dropped
- `RuntimeEnvironment`/`Workspace`, repo workflows, `exec`, fan-out, wave scheduler — Phases 9–12
- New DB table / schema migration — engine-internal + capability code, additive-only
- New behavior — parity-only (the one sanctioned 0C compaction change already landed in Phase 3)

</spec_lock>

<decisions>
## Implementation Decisions

> SPEC locked the 11 requirements (WHAT) at ambiguity 0.08, including the four interview-locked boundary seams (behavior-preserving validation move; minimal name→impl resolution; delete L1–L13 + re-verify L14/15/16, D1 voided; kernel-scoped gates + drop legacy `pipeline.py`). These are the five HOW forks (module layout, resolution seam, `task_loop`↔kernel coupling, opendesign re-homing, plan sequencing), each **locked to the plan.md-grounded recommendation** per the standing directive ("honor plan.md, nothing dropped"), plus the mechanical decisions they imply.

### Area A — Capability module layout (§32)

- **D-01: Adopt §32's subpackage tree under `agents/capabilities/`.** Create `capabilities/strategies/` (`single_shot.py`, `task_loop.py`), `capabilities/deliverables/` (`single_file.py`, `serialized_sandbox.py`, `streamed_text.py`, `ppt.py`), `capabilities/context_providers/` (`opendesign.py`, `previous_run.py`), `capabilities/task_parsers/` (`heading_tasks.py`), `capabilities/compaction/` (`html_skeleton.py`). One impl per module, each satisfying its `base.py` Protocol port; consistent snake_case `name` == registry key == manifest reference (§32 "one name everywhere").
  - **Heavy-dep impls stay in `app/agents/` (§32:1079, 1085):** `static_check.py` / `render_check.py` remain under `app/agents/` (Chromium/stdlib deps) and are called **directly** by `task_loop` this phase (NOT wrapped as registered `Validator`s — that is Phase 8 / 08-04). The kernel still imports only `capabilities.base` ports + the resolution seam.
  - *Rationale:* §32 is the canonical end-state layout Phase 8 builds on; the subpackage tree is where `@register`/`discover()` will later attach. Phase 6 put `model_catalog.py` flat because it was a single data module; Phase 7 introduces real capability families, so the subpackage structure earns its keep now.
  - **Researcher directive:** confirm the import-linter contract permits `agents/capabilities/<kind>/*.py` to import `agents/workflows/plan.py` (typed `Step`/`Task`/`CompiledWorkflow`) + `agents/execution_engine/context.py` (`ExecutionContext`) and be imported by the kernel; confirm `app/agents/static_check.py`/`render_check.py` are importable from `capabilities/strategies/task_loop.py` without violating kernel→ports (they may need to be reached via the runner handle in D-03, since the kernel must not import `app.*`).

### Area B — Name→impl resolution seam (evolution of Phase 4 D-07)

- **D-02: Extend `CapabilityRegistry` with a `(kind, name)→impl` map + `resolve(kind, name)`, populated by an explicit startup registration call.** The existing name-only registry (`is_registered`, `_KNOWN`) gains an impl map and a `resolve()` accessor. Population is an **explicit `install()/_register_builtins()`-style call** that imports the capability modules and binds each instance — NOT the `@register` decorator + startup `discover()` machinery (those stay Phase 8). The registry stays a **module-level singleton** (capabilities are stateless; per-run state stays on `ExecutionContext`).
  - *Rejected:* a separate parallel resolver module (the registry already owns `(kind,name)` membership — adding the impl map there keeps one home, avoids a second source of truth); riding the registry on `ExecutionContext` (capabilities are run-invariant; only the resolved instances' *inputs* are per-run).
  - *Evolution, not dual-impl (INV-12):* Phase 8 swaps the explicit registration for `@register(kind,name)` + `discover()` + `user_allowed` trust — exactly the path Phase 4 D-07 and Phase 6 D-03 framed for every capability.
  - **Researcher directive:** confirm whether `is_registered` (compiler's INV-4 validation, pure membership) and `resolve` (engine's impl lookup) should share `_KNOWN` (resolve asserts the name is known AND has an impl) or stay separate; confirm where `install()` is invoked (engine module import vs `execute()` entry) so the compiler's name-validation path is unaffected.

### Area C — `task_loop` ↔ kernel coupling (the deepest fork — §10/§11 L11)

- **D-03: `ExecutionStrategy.run(step, ctx)` owns the step's run loop; the kernel's per-agent run primitive + sandbox are exposed to the strategy via a narrow runner handle on `ExecutionContext`.** `task_loop.run(step, ctx)` owns: parse tasks (`heading_tasks` via the resolved `TaskParser`), per-task sub-agent invocation, per-task `html_skeleton` compaction (task-2+), and the Both-validation (`static_check` + `render_check`) + bounded N=2 fix-loop — yielding the engine's event dicts so the WS vocabulary is unchanged. `single_shot.run(step, ctx)` is the trivial one-agent case (run the agent, yield events). The kernel keeps a thin per-step dispatch that looks up `step.strategy` via the D-02 resolver and delegates to `strategy.run(step, ctx)` — **no `spec.id`/`pipeline_type` branch**.
  - **The runner handle:** the engine's per-agent primitive (`_run_agent` and its sandbox/`create_runner` access) is exposed to strategies through `ctx` (e.g. `ctx.run_agent` / a `KernelServices`-style handle carried on `ExecutionContext`, typed `object` to keep `context.py` import-pure — the Phase 5/6 `scoped_store`/`model_resolver` pattern). The strategy reaches `static_check`/`render_check` through this handle (kernel must not import `app.*` directly).
  - **`current_task_block` reclaim:** the Phase-2 D-02 temporary home (`ExecutionContext.current_task_block`, parked for Phase 7) is reclaimed **into `TaskLoopStrategy`** — the per-task injection state belongs to the loop, not the context. (STATE.md: "Phase 7 reclaims it into TaskLoopStrategy".)
  - *Rejected:* the kernel keeping the loop and the strategy being a thin config object (defeats INV-1 — the loop *is* the per-pipeline behavior that must leave the kernel); the strategy importing engine internals directly (breaks the import-linter kernel→ports direction).
  - **Researcher directive (HIGH — backbone of the phase):** (1) inventory the exact `_run_agent` call shape the build loop uses today (engine.py `_run_build_task_loop` ~2072, `_run_agent` ~1532, the sandbox/`create_runner`/checkpointer thread-id `<run>:<agent>:task`) and design the narrow handle the strategy needs; (2) execute the Phase-4 D-09 directive — classify all `pipeline_type`/`spec.id ==` occurrences in `engine.py` as **routing** (already sourced from `CompiledWorkflow`) vs **behavioral** (the L1–L13 set this phase deletes); (3) confirm `single_shot` reproduces today's non-build single-agent path byte/event-identically (the ppt/specify/plan/validate steps).

### Area D — `opendesign` provider re-homing (move-don't-copy, INV-12 / L12)

- **D-04: Physically relocate `agents/prototype/context.py`'s three live functions into `capabilities/context_providers/opendesign.py`; rewire all importers; then drop `agents/prototype/`.** `load_prototype_context`, `get_template_injection_parts`, `get_example_html` move into the `opendesign` provider (the provider's `load(ctx)` composes the template_body + design_system + craft blocks the L12 branches inject today). Rewire the importers: `agents/execution_engine/od_context.py:19`, `engine.py:3373/3384/3508`. The generic context injector consumes the provider's `{block-name → content}` output (replacing the per-pipeline `_build_context_message` od/ppt/build branches, L12). `previous_run` provider seeds the parent run's spec/design/tasks (revision, replacing L4 seeding) — ownership-checked via the Phase-5 `ScopedStore`/`assert_owns` (INV-8).
  - **After relocation:** `agents/prototype/` retains only the dead `pipeline.py` (dropped per SPEC) + `__init__.py` + `README.md` + the emptied `context.py` → the package is removed once `context.py` is empty and `pipeline.py` is gone. `od_context.py` (in `execution_engine/`) is rewired to the provider or relocated — planner's call.
  - *Rationale:* INV-12 move-don't-copy — the provider must be the single home, not a wrapper around the old location (a wrapper is the exact dual-impl the ledger forbids). `od_prototype` flavor becomes fully declarative (`context_providers: [opendesign]`), closing the Phase-4 D-04 note "injection stays in the surviving L12 branch until Phase 7".
  - **Researcher directive:** confirm `agents/prototype/context.py`'s dependency surface (`od_loader`, template/example disk reads) is kernel-importable or must ride in `app/agents/` (heavy deps → reached via the D-03 handle); confirm no other live importer of `agents/prototype/*` beyond the 4 sites grepped.

### Area E — Plan sequencing / strangler safety (ROADMAP 07-01…05 / §31)

- **D-05: Follow the ROADMAP's 5-plan split; deletion is the final plan, after the engine routes through the capabilities.** (1) **07-01** `single_shot` + `task_loop` strategies + `heading_tasks` parser (+ the D-03 runner handle + D-02 resolution seam). (2) **07-02** `single_file`/`serialized_sandbox`/`streamed_text`/`ppt` resolvers + `opendesign`/`previous_run` providers + `seed_files`. (3) **07-03** `html_skeleton` CompactionStrategy (re-express 0C behind the capability). (4) **07-04** wire the engine to route prototype/od_prototype/prototype_revision through the capabilities + **prove parity while L1–L13 still physically present but now dead**. (5) **07-05** delete L1–L13 + drop `pipeline.py` + flip ledger rows + kernel-scope the grep gates + flip the banned-pattern gate to hard-fail + re-verify L14/15/16 + INV-1 gate.
  - *Rationale:* strangler discipline (§31 wrap→rewire→delete) — each plan leaves the 0A/0C suites green; the engine routes through the new capabilities **before** any deletion, so 07-05 is pure removal of now-unreachable code. This is the safest ordering for the core-value proof.
  - **Critical sequencing constraint:** the L4/L8 revision seeding + L10 HTML readback + L7 build dispatch are deleted only **after** the manifest path (`previous_run`/`seed_files.from_run`, `single_file` resolver, `task_loop`) is proven at parity in 07-04 — never before.
  - **Researcher directive:** confirm the parity harness (`tests/agents/test_characterization_*.py` + the 5-pipeline deliverable/event snapshots) can run against the **routed-but-not-yet-deleted** state in 07-04 (the capabilities produce the output; the leaks are dead) so 07-05's deletion is gated on green.

### Claude's Discretion
- Exact name/shape of the runner handle on `ExecutionContext` (D-03) — `ctx.run_agent` callable vs a `KernelServices` dataclass; method signatures (`resolve` returns the impl vs a thin wrapper).
- Whether `install()` (D-02) lives in `capabilities/registry.py`, a `capabilities/__init__.py` discover-lite, or is called from engine import — provided no `@register`/`discover()` machinery and the compiler's name-validation path is unchanged.
- Whether `od_context.py` is rewired in place or relocated into the `opendesign` provider (D-04).
- The exact kernel-scoping mechanism for each L1–L13 grep gate (refine pattern to the leak construct vs `--include` path scope vs the existing banned-pattern single-file allow-list) — provided the gate asserts kernel-leak deletion without false-matching legitimate non-kernel refs.
- Plan-task granularity / split within the 5-plan frame (D-05) — e.g. whether the resolution seam + runner handle land in 07-01 or a 07-00 scaffolding plan.
- Whether the §32 `engine.py`→`kernel.py` rename happens this phase or is deferred (cosmetic; not required for parity/INV-1).
- Whether `previous_run` and `opendesign` providers share a base or are independent modules.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked requirements (read FIRST)
- `.planning/phases/07-prototype-as-manifest-parity-proof-sc-001-2/07-SPEC.md` — the 11 locked requirements (PARITY-01..09 + the four interview-locked boundary seams), boundaries, acceptance criteria. **Locked requirements — MUST read before planning.**

### The specification (authoritative — `specs/003-workflow-engine-decoupling/plan.md`)
- **§6 (lines 324–516)** — Core abstractions / contracts: the capability ports (`ExecutionStrategy`/`DeliverableResolver`/`ContextProvider`/`TaskParser`/`Validator`/`GateHandler`), `Step`/`Task`/`CompiledWorkflow`/`ExecutionContext`. The fields this phase makes live (`strategy`, `task_source`, `validators`, `fix`, `compaction`, `seed_files`, `deliverable`, `context_providers`).
- **§10 (lines 572–607)** — Prototype re-expressed as a manifest (the parity proof). **Parity trap:** §10's illustrative YAML shows `planner: skip` + `clarify.mode: always`, but the **authored** `prototype/workflow.yaml` correctly uses `planner: run` + `clarify.mode: auto` (SKIP_PLANNER_FOR_PROTOTYPE=False today). Honor the authored manifest, not the illustrative one.
- **§11 (lines 609–628)** — Leak → new-home mapping (every L# → its capability). The backbone of what moves where.
- **§30 (lines 921–988)** — Capability kinds grounded in code; `agent_runtime`/`tool_provider`/skills/hooks are **Phase 3/8**, not this phase.
- **§31 (lines 989–1024)** — Migration & deletion ledger + the wrap→rewire→delete rule + the deletion-is-an-exit-gate definition of done. L1–L13 are Phase 2 (roadmap Phase 7).
- **§32 (lines 1027–1098)** — Target directory structure (D-01 capability subpackage layout) + Ports & Adapters patterns + import-linter direction. `static_check`/`render_check` stay in `app/agents/validators/` (heavy deps; registered as Validators in Phase 8).

### Project planning
- `.planning/REQUIREMENTS.md` — PARITY-01..09 (lines 68–76) with plan anchors; the Phase 7 traceability row (line 232).
- `.planning/ROADMAP.md` § Phase 7 — goal, success criteria, the 07-01…07-05 candidate plan breakdown (D-05).
- `.planning/PROJECT.md` — invariants (INV-1 no name branches, INV-3 parity, INV-5 thin compiler, INV-12 move-don't-copy/deletion-is-DoD, INV-13 deepagents-only); the §4 leak map (16 couplings L1–L16); "nothing from plan.md dropped".
- `specs/003-workflow-engine-decoupling/migration-ledger.md` — operational mirror of §31; CI-asserted. **L1–L13 grep patterns + verbatim gate cells** (the exact patterns to flip to ☑); L14/L15/L16 already ☑ (re-verify); **D1 voided** (live `_handle_revision`).
- `.planning/phases/04-manifest-compiler-1a/04-CONTEXT.md` — D-06 (the inert §6 fields this phase makes live); D-07 (name-only registry → the D-02 evolution); **D-09 (classify the 44 `pipeline_type`/`spec.id` occurrences routing-vs-behavioral — the behavioral set is what Phase 7 deletes)**.
- `.planning/phases/06-model-policy-1c/06-CONTEXT.md` — the per-run-helper-on-`ExecutionContext` pattern (D-01); the "evolution not dual-impl" framing for capabilities (D-03).
- `.planning/phases/03-token-trim-measured-change-0c/03-CONTEXT.md` — the 0C `_extract_html_skeleton` behavior + the ≥50% reduction gate `html_skeleton` must preserve (PARITY-04).

### Code to read (targets / assets)
- `backend/agents/execution_engine/engine.py` (3592 lines) — the leaks to delete: **L1** `_PPT_PIPELINE_TYPES`/`_PROTOTYPE_PIPELINE_TYPES`/`REVISION_FILE_NAME` (:165,177,182); **L2/L9** `_resolve_final_output` (:447); **L3** `_sanitize_carousel_deck_html`/`_unwrap_artifact` (:363,427; applied :1394); **L4/L8** revision seeding/post-fix (:489–650,917–962); **L5** `SKIP_PLANNER_FOR_PROTOTYPE` (:1077–1105); **L6** `ALWAYS_CLARIFY` (:153,1105); **L7** `spec.id == "prototype-build"` (:3321,3404); **L10** `pipeline_type in (...)` readback (:1902); **L11** build-loop internals (`_run_build_task_loop` :2072, `_run_validation_fix_loop` :1334, `_count_plan_tasks` :2114, `_write_build_reference_files` :2134, `_extract_task_block`, `_load_template_example`); **L12** `_build_context_message` (:1586,2378+); **L13** `_extract_html_skeleton` (:3514). `compile_for_run` (:223) + `execute()` routing seam (:1006) — the consumer to wire through capabilities.
- `backend/agents/capabilities/base.py` — the 6 Protocol ports (impl targets).
- `backend/agents/capabilities/registry.py` — the name-only `CapabilityRegistry` + `_KNOWN` (15 pairs) to extend with the D-02 resolve seam.
- `backend/agents/workflows/plan.py` — `Step`/`Task`/`CompiledWorkflow` (the inert `strategy`/`task_source`/`validators`/`fix`/`compaction`/`seed_files`/`deliverable`/`context_providers` fields → live).
- `backend/agents/workflows/prototype/workflow.yaml` · `prototype_revision/workflow.yaml` · `ppt/workflow.yaml` — the authored manifests this phase runs purely from (no `od_prototype` manifest — id-alias → `prototype`).
- `backend/app/agents/static_check.py` · `render_check.py` — the Both-validation called directly by `task_loop` (stay in `app/agents/`; formal Validators = Phase 8).
- `backend/app/agents/sandbox.py` — `RunSandbox` + `serialize_sandbox_deliverable()` (the `single_file` reads `prototype.html`; `serialized_sandbox` → `filename:` blocks).
- `backend/agents/prototype/context.py` — the 3 LIVE OpenDesign fns to relocate into `opendesign` (D-04); `pipeline.py` — DEAD, dropped (carries `PROTOTYPE_PIPELINE_TYPES`, `is_prototype_pipeline`, the `prototype_revision` branch, `SKIP_PLANNER_FOR_PROTOTYPE`).
- `backend/agents/execution_engine/od_context.py` (:19) — imports `load_prototype_context` (rewire per D-04).
- `backend/agents/execution_engine/context.py` — `ExecutionContext` (the runner handle + reclaimed `current_task_block` ride here, typed `object`).
- `backend/tests/agents/test_characterization_*.py` + `test_characterization_prototype_revision.py` + the 5-pipeline deliverable/event snapshots — the parity gate (MUST stay green).
- `backend/tests/agents/test_migration_ledger.py` — the ratchet (`grep -rnE <pattern> backend/ --include=*.py`); flip L1–L13 to ☑, kernel-scope the patterns.
- `backend/tests/agents/test_banned_patterns.py` — the INV-1 / L7-L10 reservation gate (warn-only → hard-fail this phase).
- `backend/tests/agents/test_manifest_parity.py` (:26) — imports `SKIP_PLANNER_FOR_PROTOTYPE` from the dropped `pipeline.py` (update).
- `backend/tests/agents/_scripted_model.py` — the offline `BaseChatModel` that drives the deepagents loop (sets `ALWAYS_CLARIFY=False`; will need rewiring when L6 deletes).
- `backend/CLAUDE.md` — engine = deterministic sequencer; the prototype build-loop description; commit scopes (`engine`/`registry`/`factory`/`tests`); dev runtime `python3.11`, no venv; PR off `feature/003-workflow-engine-decoupling`, never `main`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`agents/capabilities/base.py`** — the 6 Protocol ports already authored (Phase 4); impls satisfy them structurally (`name` attr + the one method each).
- **`agents/capabilities/registry.py`** — `CapabilityRegistry` + `_KNOWN` (15 names) is the seam D-02 extends with `(kind,name)→impl` + `resolve()`. `resolve_alias` (od_prototype→prototype) already lives here.
- **The authored manifests** (`agents/workflows/<id>/workflow.yaml`) — already declare every capability name + `deliverable.name`/`clarify.defaults`/`seed_files`/`task_source`/`validators`/`compaction`; Phase 7 implements the behavior behind them (no manifest re-authoring needed for parity — they were authored faithfully in Phase 4).
- **`app/agents/static_check.py` + `render_check.py`** — the Both-validation `task_loop` calls directly (behavior-preserving; the bounded N=2 fix-loop wraps them).
- **`app/agents/sandbox.py`** — `RunSandbox` (per-run disk, shared across agents) + `serialize_sandbox_deliverable()` — the deliverable resolvers read from here.
- **`ExecutionContext` per-run-helper pattern** (Phase 5/6 `scoped_store`/`artifacts`/`model_resolver`, typed `object`) — the D-03 runner handle + reclaimed `current_task_block` ride the same way, import-pure.
- **`agents/prototype/context.py`** — the 3 OpenDesign loaders to **relocate** (not wrap) into the `opendesign` provider (D-04).
- **The 0A/0C characterization harness** (`tests/agents/test_characterization_*.py`, `_scripted_model.py`) — the deliverable byte-snapshot + semantic event multiset that gates every plan (parity).

### Established Patterns
- **The engine is a deterministic sequencer** — it reads the ordered steps from `CompiledWorkflow` (Phase 4); Phase 7 makes the per-step *behavior* a registry lookup by declared `strategy`/`deliverable`/etc. name (INV-1), never an `if pipeline_type`/`spec.id` branch.
- **Evolution not dual-impl (Phase 4 D-07 / 6 D-03)** — name-only registry now → `@register`/`discover()`/trust in Phase 8. D-02 follows this exactly (explicit registration now, decorator later).
- **Move-don't-copy + deletion-is-an-exit-gate (INV-12 / §31)** — a capability that doesn't delete its leak is **not done**; the ledger grep ratchet + import-linter + banned-pattern gate enforce it.
- **Snapshot model** — deliverable byte snapshot (deterministic) + semantic event snapshot (order-canonical multiset, volatile fields normalized). BOTH stay green for prototype/od_/revision/ppt/code-gen.
- **Ports & Adapters / import-linter** — kernel imports only `capabilities.base` ports + the resolve seam; heavy-dep impls (`static_check`/`render_check`) reached via the D-03 handle, never a direct `app.*` import from the kernel.
- **Dev runtime** — `python3.11`, no venv; `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v`; commit scopes per `backend/CLAUDE.md`; PR off `feature/003-workflow-engine-decoupling`, never `main`.

### Integration Points
- **Net-new:** `agents/capabilities/{strategies,deliverables,context_providers,task_parsers,compaction}/*.py` (the impl modules); the D-02 resolve seam in `registry.py`; the D-03 runner handle on `ExecutionContext`.
- **Grows:** `engine.py` (per-step dispatch → `resolve(step.strategy).run(step,ctx)`; deliverable → `resolve(deliverable.strategy).resolve(ctx)`; context → generic injector over providers); `context.py` (+runner handle, +reclaimed `current_task_block`); `registry.py` (+impl map +resolve); the 4 `agents/prototype/context` importers (rewire).
- **Shrinks → deleted:** L1–L13 in `engine.py`; `agents/prototype/pipeline.py`.
- **CI gates that constrain the work:** 0A/0C characterization snapshots (parity), migration-ledger ratchet (flip L1–L13, kernel-scoped; don't regress L14/15), import-linter (kernel→ports), banned-pattern (INV-1 hard-fail + deepagents-only).

</code_context>

<specifics>
## Specific Ideas

- **Standing project directive (init):** "everything from plan.md must be honored — nothing dropped." Every lock above takes the plan-faithful option (§32 subpackages; registry-resolve evolution; strategy-owns-the-loop; move-don't-copy opendesign; ROADMAP 5-plan sequencing).
- **Mode:** the user dismissed per-area discussion (mirrors Phases 1/2/4/5/6 "lock all to recommendations"). Treat D-01..D-05 as locked unless this file is edited before planning.
- **SPEC interview already locked** (do not re-litigate): behavior-preserving validation move (formal Validator/Gate registries → Phase 8); minimal name→impl resolution (self-registration → Phase 8); delete L1–L13 + re-verify L14/15/16 (D1 voided); kernel-scoped INV-1 gates + drop the dead `pipeline.py`.
- **The deepest research risk (D-03):** the `task_loop`↔kernel runner-handle shape — how the strategy reaches `_run_agent`/sandbox/`static_check`/`render_check` without the kernel importing `app.*`. This is the backbone the researcher must resolve before planning task granularity.
- **Parity trap #1 (carried from the manifest comments):** `planner: run`, NOT `planner: skip` — `SKIP_PLANNER_FOR_PROTOTYPE` is False today. **Parity trap #2:** `prototype_revision` clarify.defaults fall to the `custom` pipeline defaults. Honor the authored manifests.
- **L4/L8 grep nuance (kernel-scoping):** the bare token `prototype_revision` legitimately appears in `.py` outside the kernel (`registry.py` REVISION_BASE_MAP/PIPELINE_AGENTS, `entitlements.py`, `runs.py`, tests) — the gate must target the kernel revision block, not all of `backend/` (SPEC interview round 2).

</specifics>

<deferred>
## Deferred Ideas

- **Self-registration (`@register`/`discover()`) + `user_allowed` trust flags + owner allow-list** — Phase 8 (CAP-01/02). D-02's explicit registration is the evolution precursor.
- **Formal `Validator` registry + generic fix-loop + P0–P3 severity mapping + Tier#4/5/6 validators + migrating `html_static`/`html_render` into the registry** — Phase 8 (08-04). Phase 7 keeps the validation behavior inline in `task_loop`.
- **Formal `GateHandler` registry + making `Validation_Gate` first-class (`human`/`validation`/`approval`/`security`)** — Phase 8 (08-02). Phase 7 preserves the revision post-edit validation behavior only.
- **`fanout_batch` / `wave_scheduler` strategies** — Phases 11/12. Phase 7 implements only `single_shot` + `task_loop`.
- **`repo_diff` deliverable + `repo`/`uploaded_files`/`memory` context providers** — Phases 9+.
- **`json_tasks` / `bracket_p` task parsers** — later (only `heading_tasks` needed for prototype parity).
- **`engine.py` → `kernel.py` rename (§32)** — cosmetic; planner's call whether this phase or later (not required for INV-1/parity).
- **PromptAssemblyPolicy / AgentRuntimeAdapter / ToolPermissions / F1–F5 factory deletions** — Phase 8.

None of these are scope creep — all are explicitly later-phase per ROADMAP.md / the §31 ledger / the SPEC boundary.

</deferred>

---

*Phase: 7-prototype-as-manifest-parity-proof-sc-001-2*
*Context gathered: 2026-06-08*
