# Roadmap: Workflow Engine Decoupling & Universal Workflow Runtime

## Overview

A strangler/incremental migration (Q39) that turns the prototype-coupled `ExecutionEngine` into a workflow-agnostic kernel driven by declarative manifests. Each phase is independently shippable and **keeps prototype working throughout** — abstractions are introduced behind existing behavior, prototype is migrated to declarations, then hardcoded leaks are deleted. The journey: lock behavior with characterization tests → lift per-run state into `ExecutionContext` → trim tokens → introduce manifests/compiler → typed artifacts + persistence + ownership → model policy → **prove parity (SC-001) by re-expressing prototype as a manifest and deleting L1–L12** → harden the capability registry, gates, tool-permissions, runtime adapter (delete F1–F5) → local Workspace runtime + repo workflows → safe gated exec → engine-owned fan-out + merge → wave scheduler + durable resume. ECS/EC2 (plan Phase 7) is deferred to a separate spec.

The plan sub-phases (0A/0B/0C, 1A/1B/1C, 4A/4B) are mapped to sequential GSD phases 1–12; each phase name carries its plan id `[0A]…[6]` so it traces directly to `specs/003-workflow-engine-decoupling/plan.md §25`.

**Global invariants (success constraints on every phase):** INV-1 (kernel knows no workflow by name) · INV-2 (no per-run state on the singleton) · INV-3 (semantic event parity; deliverables byte-identical where deterministic) · INV-12 (move-don't-copy; deletion is an exit gate) · INV-13 (LangChain `deepagents` only — never hand-rolled).

## Phases

**Phase Numbering:** Integer phases map 1:1 to the plan's §25 sub-phases. Strangler order is strictly sequential — each phase depends on the prior.

- [x] **Phase 1: Safety Net + Deletion Guard [0A]** - Characterization snapshots + ledger/import-linter/banned-pattern CI gates; no behavior change (completed 2026-06-06)
- [x] **Phase 2: ExecutionContext + Ownership [0B]** - Lift all `self._*` run state into a per-run `ExecutionContext`; explicit parent-run ownership check; no behavior change (completed 2026-06-07)
- [x] **Phase 3: Token-Trim (measured change) [0C]** - Wire the dead `_extract_html_skeleton` as build compaction; gated on semantic snapshot + measured token delta (completed 2026-06-07)
- [ ] **Phase 4: Manifest + Compiler [1A]** - File-backed manifests → thin compiler → typed `CompiledWorkflow`; pipelines run from compiled plans
- [ ] **Phase 5: Typed Artifacts + Persistence + Ownership [1B]** - `ArtifactGraph`/`ArtifactRef` + schema (§18); dual-write then delete the legacy mirror; authz denial tests
- [ ] **Phase 6: Model Policy [1C]** - `ModelResolver` (resolution order + fallback + cost_class) + `ModelCatalog` + per-agent overrides
- [ ] **Phase 7: Prototype as Manifest — Parity Proof (SC-001) [2]** - Strategies/resolvers/providers/parsers/compaction; delete kernel leaks L1–L12; zero name/id branches
- [ ] **Phase 8: Capabilities Hardened — Registry, Gates, Tool Perms, Runtime [3]** - CapabilityRegistry + trust; gate registry; least-privilege; AgentRuntimeAdapter + PromptAssemblyPolicy; delete F1–F5
- [ ] **Phase 9: Local Workspace Runtime + Repo Workflows (no exec) [4A]** - `RuntimeEnvironment` port + `LocalSandboxRuntime`; repo inventory/index/context-pack + `repo_diff`; MCP client + integrations
- [ ] **Phase 10: Safe Local Exec (gated on N3) [4B]** - Constrained `exec` behind the `security` gate + `ExecutionPolicy`; compile/test/lint validators
- [ ] **Phase 11: Engine-Owned Fan-Out + Merge [5]** - `spawn_subagents` + kernel `run_fanout`; isolation + merge-conflict flow; `BudgetManager`; subagent persistence
- [ ] **Phase 12: Wave Scheduler + Durable Resume [6]** - Topo wave scheduler; `wave_runs`; resume mid-wave; prototype stays sequential

> **Deferred (plan Phase 7, OUT OF SCOPE this milestone):** ECS/EC2 runtime behind the unchanged `RuntimeEnvironment` port — a separate spec (§27). Tracked as v2 in REQUIREMENTS.md (ECS-01/02).

## Phase Details

### Phase 1: Safety Net + Deletion Guard [0A]

**Goal**: Lock current behavior with characterization snapshots and stand up the CI gates that enforce the migration discipline — before any refactor touches the engine.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: SAFE-01, SAFE-02, SAFE-03, SAFE-04, SAFE-05, SAFE-06, SAFE-07, DEL-01, DEL-02, DEL-03, DEL-04
**Success Criteria** (what must be TRUE):

  1. Deliverable byte-snapshots + semantic event snapshots recorded and green for prototype, od_prototype, prototype_revision, ppt/od_ppt, and one code-gen pipeline (driven by the scripted model)
  2. The migration-ledger CI guard, import-linter contract, and hand-rolled-deep-agent banned-pattern gate all run in CI (start green/empty, tighten as items delete)
  3. Per-run event `seq` asserted contiguous; no runtime behavior change

**Plans**: 4 plans (3 waves)

Plans:

- [x] 01-01-PLAN.md — Extend `_scripts_for` (PPT) + deliverable byte-snapshot characterization tests for 5 pipelines (SAFE-01) [wave 1] ✅ 2026-06-06
- [x] 01-02-PLAN.md — `_normalize()` + semantic event-stream snapshots + contiguous `seq` assertion (SAFE-02, SAFE-03) [wave 2]
- [x] 01-03-PLAN.md — `migration-ledger.md` mirror of §31 + `test_migration_ledger.py` ratchet (DEL-01..04, SAFE-04) [wave 1] ✅ 2026-06-06
- [x] 01-04-PLAN.md — import-linter + vulture (SAFE-05) + banned-pattern gate (SAFE-06) + CI wiring (SAFE-07) [wave 3]

### Phase 2: ExecutionContext + Ownership [0B]

**Goal**: Extract every per-run `self._*` attribute into a per-run `ExecutionContext`, make the kernel singleton stateless/immutable, and add the explicit parent-run ownership check — with no behavior change.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: CTX-01, CTX-02, CTX-03, CTX-04, CTX-05
**Success Criteria** (what must be TRUE):

  1. All `self._*` run state (`_od_context`/`_completed_tasks`/`_current_task_block`/`_revision_*`/`_gate_agent_ids`/`_user_id`/`_checkpointer`) lives on `ExecutionContext`; kernel has no per-run attributes (NFR-001); ledger L14 grep gate returns 0
  2. Cross-owner `parent_run` seeding is rejected by an explicit ownership check (L16 denial test passes)
  3. ~~Dead `_handle_revision` deleted (D1)~~ **[VOIDED 2026-06-07 — `_handle_revision` is live (the `run_revision` PPT-revision handler); D1 deferred, see CTX-04]**; deliverable snapshots byte-identical and event snapshots at semantic parity

**Plans**: 3 plans (3 waves — strangler chain, each wave leaves the 0A suite green)
Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Introduce `ExecutionContext` (context.py, D-01 field set) + relocate all `self._*` per-run state onto it + thread `ectx` through the 6 read-sites; kernel stateless; L14 grep → 0 (CTX-01, CTX-02, CTX-05) [wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md — **[RE-SCOPED 2026-06-07]** ~~Delete dead `_handle_revision` (D1)~~ (voided — live `run_revision` handler) + flip migration-ledger row **L14** to ☑ (arm the grep ratchet; fixed the ledger parser to handle alternation patterns); D1 deferred (CTX-05; CTX-04 deferred) [wave 2]

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-03-PLAN.md — `assert_owns` ownership helper (authz.py) + explicit cross-owner check above the seed try/except + denial/degrade/anon tests + record L16 (CTX-03, CTX-05) [wave 3]

**Cross-cutting constraints:**

- Phase 0A characterization snapshots stay byte-identical and at semantic-event parity

### Phase 3: Token-Trim (measured change) [0C]

**Goal**: Wire the dead `_extract_html_skeleton` as build-task-2+ context compaction (Tier#1) — the one sanctioned non-byte-identity change, gated on the semantic snapshot plus a measured token reduction.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: COMPACT-01, COMPACT-02, COMPACT-03
**Success Criteria** (what must be TRUE):

  1. `_extract_html_skeleton` is wired into build-task-2+ prompts (L13 now live)
  2. Semantic snapshot holds (same pages/routes, equal-or-better validation pass rate) — gated on semantics, not byte-identity
  3. A measured token/cost reduction is demonstrated on a multi-task build

**Plans**: 2 plans (2 waves)
Plans:
**Wave 1**

- [x] 03-01-PLAN.md — Wire `_extract_html_skeleton` into `_build_context_message` task-2+ + deterministic offline ≥50% reduction CI gate + read_file-access assert (COMPACT-01, COMPACT-03) [wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-02-PLAN.md — Re-baseline prototype/od_prototype deliverable goldens (hold semantic snapshots) + pages/routes + equal-or-better-validation parity assertion + opt-in live token-delta evidence → SUMMARY (COMPACT-02, COMPACT-03) [wave 2]

### Phase 4: Manifest + Compiler [1A]

**Goal**: Introduce hand-authored file-backed workflow manifests and a thin compiler (no DSL) that produces a typed `CompiledWorkflow`; run every existing pipeline from a compiled plan while artifacts still flow via the legacy mirror.
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: MAN-01, MAN-02, MAN-03, MAN-04, MAN-05, API-01
**Success Criteria** (what must be TRUE):

  1. `WorkflowManifest` (schema + loader/validator) and `WorkflowCompiler` compile a YAML manifest to a validated typed `CompiledWorkflow`/`ExecutionPlan` with no control flow in manifests (INV-5)
  2. Every current pipeline runs from a compiled plan; snapshots green; `accumulated_outputs` mirror still used (no schema change yet)
  3. Compiler rejects unknown/not-allowed capability references (INV-4); `GET /api/workflows[/{id}]` returns manifest-derived metadata

**Plans**: 5 plans
Plans:
**Wave 1**

- [x] 04-01-PLAN.md — Capability ports (`base.py`) + name registry (`registry.py`, 14 names) + id-alias resolver [MAN-03]
- [x] 04-02-PLAN.md — `plan.py` (CompiledWorkflow/Step/Task §6 contract) + `manifest.py` loader/validator [MAN-01]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 04-03-PLAN.md — `compiler.py` (thin, no-DSL, name-resolve) + the 15 `workflow.yaml` manifests + coverage/parity tests [MAN-02, MAN-03, MAN-04]

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 04-04-PLAN.md — Engine routing seam + id-alias (run from CompiledWorkflow) + characterization parity gate [MAN-04, MAN-05]
- [ ] 04-05-PLAN.md — `/api/workflows` definitions rewrite + `/api/runs` relocation + 10 frontend repoints [API-01]

### Phase 5: Typed Artifacts + Persistence + Ownership [1B]

**Goal**: Replace the untyped `accumulated_outputs` handoff with a typed, content-addressed, owner-scoped `ArtifactGraph`; land the persistence schema (§18) and default-deny ownership enforcement; dual-write then delete the legacy mirror.
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: ART-01, ART-02, ART-03, ART-04, PERSIST-01, PERSIST-02, PERSIST-03, AUTHZ-01, AUTHZ-02, AUTHZ-03, AUTHZ-04, CAPRUN-01, API-04, API-05
**Success Criteria** (what must be TRUE):

  1. Artifacts are typed + lineage-tracked (producer step/agent/task, content hash, version, parents, visibility, retention) and persisted; the `accumulated_outputs` mirror is deleted (L15 gate; only typed reads remain)
  2. Additive migrations add `artifact_refs`, extend `workflow_runs`, add `workspaces`/`run_events`/`run_capabilities`; every table carries `owner_id` + `workspace_id`
  3. Default-deny store-layer scoping enforced; cross-owner authz denial tests pass; `anon:<session_id>` owner used for unauthenticated runs; snapshots green
  4. `GET /api/runs/{id}/artifacts` returns the typed lineage tree; `GET /api/runs/{id}/events?after=<seq>` replays the durable log

**Plans**: TBD

Plans:

- [ ] 05-01: `ArtifactGraph`/`ArtifactRef` (artifacts/) + typed produces/consumes routing
- [ ] 05-02: Migrations §18 (artifact_refs, workflow_runs extend, workspaces, run_events, run_capabilities)
- [ ] 05-03: `authz.py` ownership-scoped store helper (default-deny) + denial tests
- [ ] 05-04: Dual-write → migrate reads → delete `accumulated_outputs` mirror
- [ ] 05-05: `run_capabilities` persistence + `/api/runs/{id}/artifacts` + events replay endpoint

### Phase 6: Model Policy [1C]

**Goal**: Implement model resolution with the full precedence order, fallback chains, cost classes, a `ModelCatalog`, and persisted per-agent overrides — global default stays Haiku.
**Mode:** mvp
**Depends on**: Phase 5
**Requirements**: MODEL-01, MODEL-02, MODEL-03, MODEL-04, MODEL-05
**Success Criteria** (what must be TRUE):

  1. `ModelResolver` applies user-override > step > agent > workflow > global(Haiku); per-step/workflow model honored; global default unchanged
  2. `ModelPolicy` (model id, max_tokens doc-only, cost_class, ordered fallback) drives `model_factory.build_model`; fallback fires on throttle/error
  3. `ModelCatalog` capability lists selectable models (label/provider/cost_class/window/user_allowed); per-agent `model_overrides` applied at the top of the order and persisted per run

**Plans**: TBD

Plans:

- [ ] 06-01: `ModelResolver` + resolution order on `ExecutionContext`
- [ ] 06-02: `ModelCatalog` capability + fallback chain + cost_class budget tie-in
- [ ] 06-03: Per-agent `model_overrides` in the run payload, persisted to `run_capabilities`

### Phase 7: Prototype as Manifest — Parity Proof (SC-001) [2]

**Goal**: Re-express prototype/od_/revision entirely as manifests backed by registered capabilities, then delete the hardcoded kernel leaks L1–L12 — proving the kernel knows no workflow by name. **This is the core-value proof.**
**Mode:** mvp
**Depends on**: Phase 6
**Requirements**: PARITY-01, PARITY-02, PARITY-03, PARITY-04, PARITY-05, PARITY-06, PARITY-07, PARITY-08, PARITY-09
**Success Criteria** (what must be TRUE):

  1. `single_shot` + `task_loop` strategies, `single_file`/`serialized_sandbox`/`streamed_text` + `ppt` resolvers, `opendesign` provider, declared `seed_files`, `heading_tasks` parser, and `html_skeleton` `CompactionStrategy` all implemented and registered
  2. prototype, od_prototype (alias), and prototype_revision (from_run + previous_run + post-edit validation gate) run purely from manifests
  3. Kernel leaks L1–L12 deleted; grep gate for `if pipeline_type`/`spec.id ==` and the L1/L2/L5/L6/L7/L10/L11/L12 patterns return 0 (INV-1)
  4. prototype/od_/revision/ppt/code-gen at deliverable parity + semantic event parity vs the post-0C baseline

**Plans**: TBD

Plans:

- [ ] 07-01: `single_shot` + `task_loop` strategies + `heading_tasks` parser
- [ ] 07-02: Deliverable resolvers (single_file/serialized_sandbox/streamed_text/ppt) + `opendesign` context provider + seed_files
- [ ] 07-03: `html_skeleton` CompactionStrategy (re-express 0C behind the capability)
- [ ] 07-04: prototype/od_prototype/prototype_revision manifests + parity verification
- [ ] 07-05: Delete L1–L12 kernel branches; ledger gates green; INV-1 grep gate

### Phase 8: Capabilities Hardened — Registry, Gates, Tool Perms, Runtime [3]

**Goal**: Formalize the capability registry + trust flags, make gates first-class (incl. a real `validation` gate), enforce least-privilege tool permissions, and lift the factory's hardcoded runtime/tools/prompt-order into adapters/registries/policy — deleting F1–F5 and fixing the constitution no-op (R12).
**Mode:** mvp
**Depends on**: Phase 7
**Requirements**: CAP-01, CAP-02, CAP-03, GATE-01, GATE-02, GATE-03, TOOLPERM-01, TOOLPERM-02, TOOLPERM-03, VALID-01, VALID-02, VALID-03, VALID-04, VALID-05, AGENTRT-01, AGENTRT-02, AGENTRT-03, AGENTRT-04, AGENTRT-05, AGENTRT-06, SKILL-01, HOOK-01, HOOK-02, HOOK-03, HOOK-04, OBS-02, API-02, API-03, API-06
**Success Criteria** (what must be TRUE):

  1. `CapabilityRegistry` (self-registering, trust flags) drives all capability lookups; `GateHandler` registry implements human/validation/approval/security and makes `Validation_Gate` real
  2. `ToolPermissions` enforced at `factory._build_runner_tools` + `ExecutionPolicy` (least-privilege; exec/network/secrets/spawn default OFF); validators + generic fix-loop + P0–P3→severity mapping migrated; Tier#4/5/6 validators land
  3. `AgentRuntimeAdapter` (`langchain_deepagents`), `PromptAssemblyPolicy`, `tool_provider`/`skill_provider`/`hook_provider` replace the inline factory code; F1–F5 deleted; constitution-injected-in-prod test passes (R12)
  4. Executable lifecycle hooks (secret_scan/otel_tracing/pre-post_commit/post_task) fire and persist to `hook_runs`; `/api/capabilities` returns the dynamic palette; new validator/gate events surface at semantic parity for existing workflows

**Plans**: TBD

Plans:

- [ ] 08-01: `CapabilityRegistry` (registry.py) + `base.py` ports + self-registering `discover()` + trust flags
- [ ] 08-02: `GateHandler` registry (human/validation/approval/security); make `Validation_Gate` real
- [ ] 08-03: `ToolPermissions` resolution + enforcement (factory + ExecutionPolicy); delete F2 switch
- [ ] 08-04: Validator registry + generic fix-loop + severity mapping + Tier#4/5/6 validators (migrate html_static/html_render)
- [ ] 08-05: `AgentRuntimeAdapter` + `PromptAssemblyPolicy`; delete F1/F5; skill_provider/hook_provider (delete F3)
- [ ] 08-06: Fix constitution no-op (F4/R12, sync-safe load)
- [ ] 08-07: Executable `HookHandler` framework + canonical hooks + `hook_runs`; otel tracing hook
- [ ] 08-08: `/api/capabilities` palette + dynamic composer/model-picker/validator-panel wiring

### Phase 9: Local Workspace Runtime + Repo Workflows (no exec) [4A]

**Goal**: Introduce the `RuntimeEnvironment`/`Workspace` ports with a `LocalSandboxRuntime`, and deliver the first brownfield repo workflow end-to-end locally without execution (clone → branch → inventory → read/edit/search → diff) — plus the MCP client and integration providers.
**Mode:** mvp
**Depends on**: Phase 8
**Requirements**: RUNTIME-01, RUNTIME-02, RUNTIME-03, REPO-01, REPO-02, REPO-03, REPO-04, REPO-05, MCP-01, MCP-02, MCP-03, MCP-04, INTEG-01, INTEG-02
**Success Criteria** (what must be TRUE):

  1. `RuntimeEnvironment` port + `LocalSandboxRuntime`; one `Workspace` abstraction (prototype = `has_git=False, exec=off`) with no engine fork repo-vs-artifact; `repositories`/`workspaces` rows persisted
  2. `RepoInventory` (tree/lang/deps/ignore-rules/binary-skip/summaries), optional `RepoIndex`, and per-task `ContextPack` produced; `repo_diff` resolver yields a file tree + per-file diff
  3. A sample repo workflow runs end-to-end locally with **no exec** and surfaces a diff; prototype unaffected
  4. `McpClientAdapter` + allow-listed famous-server catalog (scoped per-owner creds, security-gated for powerful servers); compiler validates `tools.mcp`; integration providers reachable from the unified runner path

**Plans**: TBD

Plans:

- [ ] 09-01: `RuntimeEnvironment`/`Workspace`/`ExecutionPolicy` ports (runtime/base.py) + `LocalSandboxRuntime` (local.py)
- [ ] 09-02: `repositories`/`workspaces` rows; RunSandbox → git-off Workspace
- [ ] 09-03: `RepoInventory` + `RepoIndex` (grep default) + `ContextPack` + `repo` context provider
- [ ] 09-04: `repo_diff` deliverable resolver + sample brownfield workflow (no exec)
- [ ] 09-05: `McpClientAdapter` + server catalog + `McpCapabilityRegistry` validation
- [ ] 09-06: `integration_provider` capabilities (gitlab/github/jira/slack) + `integrations` scopes

### Phase 10: Safe Local Exec (gated on N3) [4B]

**Goal**: After the N3 threat model is decided, enable a constrained `exec` profile behind the `security` gate with command allow/deny, default-deny egress, resource caps, and ephemeral creds — plus compile/test/lint validators.
**Mode:** mvp
**Depends on**: Phase 9 (and the N3 threat-model decision)
**Requirements**: EXEC-01, EXEC-02
**Success Criteria** (what must be TRUE):

  1. `exec` runs only under the `security` gate + `ExecutionPolicy` (command allow/deny, resource caps, ephemeral creds); network egress denied by default
  2. compile/test/lint validators land and a sample compile/test validator passes

**Plans**: TBD

Plans:

- [ ] 10-01: Resolve N3 threat model; constrained `exec` profile behind the security gate
- [ ] 10-02: compile/test/lint validators using gated exec

### Phase 11: Engine-Owned Fan-Out + Merge [5]

**Goal**: Implement engine-owned fan-out (declarative + `spawn_subagents` tool) with isolation, merge-conflict handling, budgets, depth/concurrency caps, subagent persistence, and cancellation propagation — the engine alone decides isolation/caps/merge (INV-7).
**Mode:** mvp
**Depends on**: Phase 9
**Requirements**: FANOUT-01, FANOUT-02, FANOUT-03, FANOUT-04, FANOUT-05, FANOUT-06, FANOUT-07, FANOUT-08, FANOUT-09, FANOUT-10, FANOUT-11, OBS-01, RESUME-01
**Success Criteria** (what must be TRUE):

  1. A granted step fans out N workers (self-copies or named workers) under `max_concurrency`, parallel or sequential; both declarative and tool entry points funnel through kernel `run_fanout`
  2. `IsolationProvider` (shared_read/sub_sandbox/worktree, writes isolated) + `MergeStrategy` merge fragments deterministically; conflicts follow `on_conflict` (human_gate/merge_agent/partial/abort) with a `merge_conflict` artifact + event
  3. `BudgetManager` reserves-before-spawn and enforces subagents/concurrency/tokens/cost/wall-clock/depth (per-run + per-workspace); `BudgetExceeded` aborts gracefully with partial results; cancellation propagates to children
  4. Each child → a `subagent_runs` row; `subagent_*`/`merge_*` events emitted

**Plans**: TBD

Plans:

- [ ] 11-01: Kernel `run_fanout` (fanout.py) + `spawn_subagents` tool (gated) + declarative `step.fanout`
- [ ] 11-02: `IsolationProvider` (sub_sandbox/worktree) + worker selection + parallel/sequential modes
- [ ] 11-03: `MergeStrategy` + merge-conflict flow (§13) + `on_conflict` policies
- [ ] 11-04: `BudgetManager` (budget.py) caps + reserve-before-spawn + graceful abort
- [ ] 11-05: `subagent_runs` persistence + `subagent_*`/`merge_*` events + cancellation propagation

### Phase 12: Wave Scheduler + Durable Resume [6]

**Goal**: Add a deterministic topological wave scheduler that runs disjoint tasks in parallel waves via fan-out, with durable mid-wave resume; prototype stays sequential and a CP-SAT seam is left.
**Mode:** mvp
**Depends on**: Phase 11
**Requirements**: WAVE-01, WAVE-02, WAVE-03, RESUME-02, RESUME-03, RESUME-04
**Success Criteria** (what must be TRUE):

  1. `wave_scheduler` strategy topo-sorts by `depends_on` + `conflict_keys` into waves and runs each wave via fan-out; a multi-file workflow runs disjoint tasks in parallel waves; prototype stays sequential; CP-SAT seam left
  2. `wave_runs` persisted; a server restart resumes mid-wave via `subagent_runs`/`wave_runs`; idempotent step retry reuses artifacts on content-hash match
  3. Reconnect replays from the durable `run_events` log (`after=<seq>`, idempotent by `event_id`); `restore_non_terminal_runs` resumes at step granularity (waiting_for_user gates resume on user action)

**Plans**: TBD

Plans:

- [ ] 12-01: `wave_scheduler` strategy (topo by depends_on + conflict_keys) + `wave_runs` persistence
- [ ] 12-02: Idempotent step retry (content-hash keyed) + mid-wave resume
- [ ] 12-03: Durable event replay + step-granular `restore_non_terminal_runs`

## Progress

**Execution Order:**
Phases execute sequentially: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Safety Net + Deletion Guard [0A] | 4/4 | Complete   | 2026-06-06 |
| 2. ExecutionContext + Ownership [0B] | 3/3 | Complete    | 2026-06-07 |
| 3. Token-Trim [0C] | 2/2 | Complete    | 2026-06-07 |
| 4. Manifest + Compiler [1A] | 4/5 | In Progress|  |
| 5. Typed Artifacts + Persistence [1B] | 0/5 | Not started | - |
| 6. Model Policy [1C] | 0/3 | Not started | - |
| 7. Prototype as Manifest (Parity Proof) [2] | 0/5 | Not started | - |
| 8. Capabilities Hardened [3] | 0/8 | Not started | - |
| 9. Local Runtime + Repo (no exec) [4A] | 0/6 | Not started | - |
| 10. Safe Local Exec [4B] | 0/2 | Not started | - |
| 11. Fan-Out + Merge [5] | 0/5 | Not started | - |
| 12. Wave Scheduler + Resume [6] | 0/3 | Not started | - |

---
*Roadmap created: 2026-06-06*
*Source: specs/003-workflow-engine-decoupling/plan.md §25 (12 active phases; plan Phase 7 / ECS deferred to v2)*
