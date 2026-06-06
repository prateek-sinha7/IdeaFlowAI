# Roadmap: Workflow Engine Decoupling & Universal Workflow Runtime

## Overview

A strangler migration (Q39) that turns the prototype-coupled `ExecutionEngine` into a workflow-agnostic kernel
driven by declarative manifests. Each phase is independently shippable and keeps `prototype` working throughout.
**Phase 0** lays the safety net (characterization snapshots + deletion ledger) and extracts per-run state with no
behavior change. **Phase 1** adds manifests, typed artifacts + persistence, and model policy. **Phase 2** proves the
decoupling by re-expressing prototype as a manifest and deleting the L1–L16 kernel branches (SC-001). **Phase 3**
hardens the capability layer (registry, gates, tool permissions, runtime adapter). **Phase 4** adds the local
Workspace runtime and brownfield repo workflows (then gated exec). **Phases 5–6** add engine-owned fan-out/merge and
the wave scheduler with durable resume. **Phase 7** (ECS) is deferred to a separate spec. The dynamic API/frontend
contract (§22) is a parallel track touched every phase.

> **Definition of Done includes deletion (INV-12 / §31):** a phase that adds an abstraction without deleting the code
> it supersedes — and proving it via the grep/dead-code/import-linter gate — is **not done**.

## Phases

**Phase Numbering:**
- Integer phases (0, 1, 2…): planned milestone work (Phase 0 = pre-refactor foundations, no behavior change)
- Plan letters from the source doc (0A/0B/0C, 1A/1B/1C, 4A/4B) map to GSD plan numbers (00-01/02/03, etc.)

- [ ] **Phase 0: Decouple Foundations** - Safety net + `ExecutionContext` + token-trim (no behavior change)
- [ ] **Phase 1: Manifest, Typed Artifacts & Model Policy** - Declarative plans, lineage-tracked artifacts, model resolution
- [ ] **Phase 2: Prototype as Manifest (Parity Proof)** - SC-001; delete L1–L16 kernel branches
- [ ] **Phase 3: Capabilities Hardened** - Registry + gates + tool permissions + runtime adapter
- [ ] **Phase 4: Local Workspace Runtime & Repo Workflows** - Brownfield repos (no exec), then safe gated exec
- [ ] **Phase 5: Engine-Owned Fan-Out & Merge** - `spawn_subagents` + isolation + merge-conflict flow + budgets
- [ ] **Phase 6: Wave Scheduler & Durable Resume** - Parallel waves + cancellation/retry/resume
- [ ] **Phase 7: ECS/EC2 Runtime (Deferred)** - Remote runtime behind the unchanged port — separate spec

## Phase Details

### Phase 0: Decouple Foundations
**Goal**: Establish the migration safety net and extract all per-run state into `ExecutionContext`, with no behavior change (deliverables byte-identical), so the refactor can proceed safely.
**Depends on**: Nothing (first phase)
**Requirements**: MIG-01, MIG-02, MIG-03, KERN-02, AUTH-02, AUTH-03, CAP-06, RUN-01
**Success Criteria** (what must be TRUE):
  1. Characterization snapshots (deliverable + semantic-event) recorded and green for prototype/od_/revision/ppt/code-gen
  2. The migration-ledger CI guard (`test_migration_ledger.py`) + import-linter contract run in CI (start green/empty)
  3. The kernel has no per-run attributes (NFR-001) — all `self._*` run state moved to `ExecutionContext`
  4. Cross-owner `parent_run` seeding is rejected by an explicit ownership check
  5. Token-trim (`html_skeleton` compaction) shows a measured token reduction with equal-or-better validation pass rate
**Plans**: 3 plans

Plans:
- [ ] 00-01: 0A — Safety net + deletion guard (characterization snapshots + ledger CI guard + import-linter; no runtime change)
- [ ] 00-02: 0B — `ExecutionContext` + ownership (extract `self._*` run state [L14]; explicit `parent_run` ownership check [L16]; delete dead `_handle_revision` [D1])
- [ ] 00-03: 0C — Token-trim (wire the dead `_extract_html_skeleton` as build-task-2+ compaction; gated on semantic snapshot + measured token delta)

### Phase 1: Manifest, Typed Artifacts & Model Policy
**Goal**: Introduce file-backed manifests + a thin compiler, a typed lineage-tracked artifact graph with persistence (dual-write), and the model-resolution policy — running every existing pipeline from a compiled plan.
**Depends on**: Phase 0
**Requirements**: MANI-01, MANI-02, MANI-03, ART-01, ART-02, PERS-01, PERS-02, PERS-03, AUTH-01, MODL-01, MODL-02, MODL-03
**Success Criteria** (what must be TRUE):
  1. Every current pipeline runs from a compiled `ExecutionPlan` (snapshots green)
  2. Artifacts are typed, lineage-tracked, and persisted; the `accumulated_outputs` mirror is deleted once reads migrate
  3. Authz cross-owner denial tests pass (artifact/run reads go through the scoped store layer)
  4. Per-step / per-workflow model selection is honored; the global default (Haiku) is unchanged
  5. Per-agent `model_overrides` apply at the top of the resolution order and persist per run
**Plans**: 3 plans

Plans:
- [ ] 01-01: 1A — `WorkflowManifest` (hand-authored) + `WorkflowCompiler` → `CompiledWorkflow`; pipelines run from compiled plans via the legacy `accumulated_outputs` mirror
- [ ] 01-02: 1B — `ArtifactGraph`/`ArtifactRef` + persistence schema (§18); dual-write then delete the mirror [L15]; `run_events`/`run_capabilities`/`hook_runs`; authz denial tests
- [ ] 01-03: 1C — `ModelResolver` (order + fallback + cost_class) + `ModelCatalog` + per-agent `model_overrides`

### Phase 2: Prototype as Manifest (Parity Proof)
**Goal**: Re-express prototype/od_/revision/ppt/code-gen as manifests using `single_shot` + `task_loop` strategies, deliverable resolvers, the `opendesign` provider, `seed_files`, the `heading_tasks` parser, and `html_skeleton` compaction — and delete the L1–L16 kernel branches. This is the SC-001 success test.
**Depends on**: Phase 1
**Requirements**: KERN-01, KERN-03, KERN-04, CAP-02, CAP-03, CAP-04, CAP-05, CAP-07
**Success Criteria** (what must be TRUE):
  1. `prototype` is reproduced by manifest + AGENT.md only, with zero engine edits (SC-001)
  2. prototype/od_/revision/ppt/code-gen hold deliverable parity + semantic event parity vs the post-0C baseline
  3. The kernel has zero name/id behavior branches (grep gate, INV-1)
  4. L1–L16 are deleted from the kernel and their banned-pattern gates return 0
**Plans**: 1 plan

Plans:
- [ ] 02-01: Prototype family as manifests + `single_shot`/`task_loop` strategies + `single_file`/`serialized_sandbox`/`streamed_text` resolvers + `opendesign` provider + `seed_files` + `heading_tasks` parser + `html_skeleton` compaction; delete L1–L16

### Phase 3: Capabilities Hardened
**Goal**: Formalize the `CapabilityRegistry` + trust flags, the gate registry (`human`/`validation`/`approval`/`security`, making `Validation_Gate` real), least-privilege `ToolPermissions` enforcement, the `AgentRuntimeAdapter` + `PromptAssemblyPolicy`, and migrated validators + generic fix-loop + severity mapping.
**Depends on**: Phase 2
**Requirements**: CAP-01, GATE-01, GATE-02, GATE-03, GATE-04, GATE-05, SEC-01, SEC-03, RUN-02, RUN-03, RUN-04
**Success Criteria** (what must be TRUE):
  1. Validators and gates are registry-driven; `Validation_Gate` is implemented and fires
  2. Least-privilege tool permissions are enforced at `factory._build_runner_tools` (exec/net/secrets/spawn default OFF)
  3. The `AgentRuntimeAdapter` wraps `create_deep_agent` [F5] and `PromptAssemblyPolicy` replaces the inline block order [F1]
  4. Constitution injection works in production (R12/F4 fixed)
  5. Tier #4/#5/#6 land as registered validators; executable hooks (incl. `secret_scan`) fire and persist
**Plans**: 3 plans

Plans:
- [ ] 03-01: `CapabilityRegistry` + trust flags (§7) + `GateHandler` registry (human/validation/approval/security; make `Validation_Gate` real)
- [ ] 03-02: `ToolPermissions` enforcement (§8) + `AgentRuntimeAdapter` + `PromptAssemblyPolicy` + constitution fix [F1–F5]; executable hooks + `secret_scan` + `hook_runs`
- [ ] 03-03: Migrate `html_static`/`html_render` validators + generic fix-loop + severity mapping + Tier #4/#5/#6 validators

### Phase 4: Local Workspace Runtime & Repo Workflows
**Goal**: Add the `RuntimeEnvironment`/`Workspace` ports + `LocalSandboxRuntime`, repo inventory/index/context-pack, and the `repo_diff` resolver for a brownfield workflow end-to-end locally **without exec**; then enable a safe, gated `exec` profile after the N3 threat model.
**Depends on**: Phase 3
**Requirements**: RUNT-01, RUNT-02, RUNT-03, RUNT-04, SEC-02, RUN-05
**Success Criteria** (what must be TRUE):
  1. A sample repo workflow produces a diff locally (clone → branch → inventory → read/edit/search → diff) with no `exec`
  2. `prototype` is unaffected (snapshots still green)
  3. `exec` runs only under the `security` gate + `ExecutionPolicy`; outbound network is denied by default
  4. A sample compile/test/lint validator passes under the gated exec profile
  5. An `McpClientAdapter` connects to an allow-listed server with scoped per-owner creds
**Plans**: 2 plans

Plans:
- [ ] 04-01: 4A — `RuntimeEnvironment` + `LocalSandboxRuntime` + `Workspace`/`ExecutionPolicy` (exec off) + `repositories`/`workspaces` rows + repo inventory/index/context-pack + `repo_diff` (no exec)
- [ ] 04-02: 4B — Safe local `exec` behind the `security` gate (N3: command allow/deny, egress default-deny, resource caps, ephemeral creds) + compile/test/lint validators; MCP client + catalog

### Phase 5: Engine-Owned Fan-Out & Merge
**Goal**: Add the gated `spawn_subagents` tool + kernel `run_fanout`, `IsolationProvider` (sub_sandbox/worktree) + `MergeStrategy` + the merge-conflict flow, the `BudgetManager` with depth/concurrency caps, `subagent_runs` persistence, and cancellation propagation.
**Depends on**: Phase 4
**Requirements**: FANO-01, FANO-02, FANO-03
**Success Criteria** (what must be TRUE):
  1. An agent fans out N workers under enforced caps (subagents/concurrency/tokens/cost/depth/wall-clock)
  2. Results merge deterministically; conflicts follow the step's `on_conflict` policy
  3. Budgets abort gracefully and surface partial results; cancellation propagates to children
**Plans**: 1 plan

Plans:
- [ ] 05-01: `spawn_subagents` (gated) + `run_fanout` + `IsolationProvider` + `MergeStrategy` + merge-conflict flow (§13) + `BudgetManager` + `subagent_runs` + cancellation propagation

### Phase 6: Wave Scheduler & Durable Resume
**Goal**: Add the `wave_scheduler` strategy (topo-sort by `depends_on` + `conflict_keys` into waves, run each wave via fan-out), `wave_runs` persistence, and resume mid-wave — enabled for multi-file workflows while prototype stays sequential.
**Depends on**: Phase 5
**Requirements**: WAVE-01, WAVE-02
**Success Criteria** (what must be TRUE):
  1. A multi-file workflow runs disjoint tasks in parallel waves
  2. A server restart resumes the run mid-wave (durable step/subagent/wave records + event replay by `seq`)
  3. `prototype` stays sequential; the CP-SAT seam is left for later (Q32)
**Plans**: 1 plan

Plans:
- [ ] 06-01: `wave_scheduler` strategy + `wave_runs` persistence + mid-wave durable resume + cancellation/retry hardening

### Phase 7: ECS/EC2 Runtime (Deferred)
**Goal**: Implement a remote `EcsRuntime` behind the unchanged `RuntimeEnvironment` port. **Deferred to a separate spec** (§27) — designed-for here via the port, not built.
**Depends on**: Phase 4 (the runtime port)
**Requirements**: INFRA-01 (v2)
**Success Criteria** (what must be TRUE):
  1. A remote runtime backs a `Workspace` with no kernel/engine changes (pure backend swap)
**Plans**: TBD (separate spec)

Plans:
- [ ] 07-01: (Deferred — tracked in a future spec)

## Progress

**Execution Order:**
Phases execute in numeric order: 0 → 1 → 2 → 3 → 4 → 5 → 6 → (7 deferred)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 0. Decouple Foundations | 0/3 | Not started | - |
| 1. Manifest, Typed Artifacts & Model Policy | 0/3 | Not started | - |
| 2. Prototype as Manifest (Parity Proof) | 0/1 | Not started | - |
| 3. Capabilities Hardened | 0/3 | Not started | - |
| 4. Local Workspace Runtime & Repo Workflows | 0/2 | Not started | - |
| 5. Engine-Owned Fan-Out & Merge | 0/1 | Not started | - |
| 6. Wave Scheduler & Durable Resume | 0/1 | Not started | - |
| 7. ECS/EC2 Runtime | 0/1 | Deferred | - |
