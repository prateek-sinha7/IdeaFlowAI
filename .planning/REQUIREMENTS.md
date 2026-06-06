# Requirements: Workflow Engine Decoupling & Universal Workflow Runtime

**Defined:** 2026-06-06
**Core Value:** A brand-new custom workflow can replicate `prototype` by manifest + AGENT.md only — zero engine edits (SC-001)

> Translated faithfully from `specs/003-workflow-engine-decoupling/plan.md`. IDs trace back to the plan's
> invariants (INV-#), locked additions (A#), Q&A decisions (Q#), leak map (L#/F#), and section numbers (§#).

## v1 Requirements

### Kernel decoupling (KERN)

- [ ] **KERN-01**: The kernel contains no `if pipeline_type in {...}` or `if spec.id == "..."` behavior branches; a workflow id appears only in the manifest loader (INV-1)
- [ ] **KERN-02**: All mutable run state lives on a per-run `ExecutionContext`; kernel instances are immutable after construction with no per-run attributes (INV-2, NFR-001, L14)
- [ ] **KERN-03**: The kernel imports only capability **ports** (Protocols); concrete capabilities are injected/registered — enforced by import-linter (INV-6, §32)
- [ ] **KERN-04**: `prototype` is fully reproducible through declarations (manifest + AGENT.md) with zero kernel edits (SC-001, Q4)

### Manifests & compiler (MANI)

- [ ] **MANI-01**: A file-backed, hand-authored `WorkflowManifest` compiles via a thin `WorkflowCompiler` to a validated typed `CompiledWorkflow`/`ExecutionPlan` with no DSL/control-flow in manifests (INV-5, Q5)
- [ ] **MANI-02**: Manifest validation rejects any unknown or not-allowed capability name; user/DB manifests are checked against per-capability `user_allowed` + the owner allow-list (INV-4, Q2, §7)
- [ ] **MANI-03**: Every existing pipeline (prototype/od_/revision/ppt/code-gen) runs from a compiled plan (Q7)

### Capabilities & registry (CAP)

- [ ] **CAP-01**: One `CapabilityRegistry` keyed by `(kind, name)` with trust flags; engineers register in code, manifests reference by name (INV-4, §7)
- [ ] **CAP-02**: Named `ExecutionStrategy` registry — `single_shot`, `task_loop`, `fanout_batch`, `wave_scheduler` (Q8/Q9)
- [ ] **CAP-03**: Deliverable-resolver registry replaces hardcoded final-output resolution — `single_file`/`serialized_sandbox`/`streamed_text`/`repo_diff` + custom resolvers (Q26/Q27, L2/L9)
- [ ] **CAP-04**: Context-provider registry — `opendesign`/`repo`/`previous_run`/`uploaded_files`/`memory`; seed files declared in the manifest (Q28/Q29, L12)
- [ ] **CAP-05**: Canonical `Task` schema + parser adapters (`heading_tasks`/`json_tasks`/`bracket_p`) (Q10/Q11, L11)
- [ ] **CAP-06**: Context-compaction strategy registry; `html_skeleton` is one implementation (Q35, Tier#1, L13)
- [ ] **CAP-07**: Planner/clarify behavior is manifest-declared — `planner: skip|run`, `clarify: always|gated|off`, `clarify_defaults` (Q30, L5/L6)

### Validation & gates (GATE)

- [ ] **GATE-01**: Validator registry; workflows list `validators: [...]` per step; `DeliverableContext` in, structured `Issue`s out (Q21/Q22)
- [ ] **GATE-02**: Generic configurable fix-loop — deliverable name, max attempts, fix-prompt from policy; default warn-noncritical / block-critical → `validation_warning` (Q23/Q25, L8/L11)
- [ ] **GATE-03**: Gate registry with first-class `human`/`validation`/`approval`/`security` handlers; the declared-but-unimplemented `Validation_Gate` is made real (A7, §9)
- [ ] **GATE-04**: Severity taxonomy — internal `P0/P1/P2/P3` mapped externally to `CRITICAL/HIGH/MEDIUM/LOW` (Q24)
- [ ] **GATE-05**: Tier #4/#5/#6 ship as registered validators — `spec_plan_coverage`, `task_done_when`, `design_quality` (Q38)

### Artifacts & lineage (ART)

- [ ] **ART-01**: A typed, content-addressed, owner-scoped `ArtifactGraph`/`ArtifactRef` replaces `accumulated_outputs: dict[str,str]` and the thin store (INV-10, §17, L15)
- [ ] **ART-02**: Every artifact records producer step/agent/task, content hash, version, parents, visibility, retention at write time (INV-10, A8)

### Persistence (PERS)

- [ ] **PERS-01**: Persistence schema (additive only) — `workflows`, extended `workflow_runs`, `artifact_refs`, `workspaces`, `repositories`, `subagent_runs`, `wave_runs`, `validation_results`, `gate_events` (A2, §18, Q3)
- [ ] **PERS-02**: Durable `run_events` with a monotonic per-run `seq` + `event_id` for replay/resume (§18/§21/§22)
- [ ] **PERS-03**: `run_capabilities` + `hook_runs` record what runtime/skills/hooks/MCP/`model_overrides` were active per run, and every hook firing (§18/§30)

### Authorization & multi-tenancy (AUTH)

- [ ] **AUTH-01**: Every workflow/run/artifact/workspace/repository/parent-run is scoped to `(owner_id, workspace_id)` with default-deny enforced at the store layer (INV-8, A3, §19)
- [ ] **AUTH-02**: `parent_run`/`source_run` seeding performs an explicit ownership check that rejects cross-owner access (L16, INV-8)
- [ ] **AUTH-03**: Anonymous runs get a synthetic `anon:<session_id>` owner — never `None` (§19)

### Tool permissions & security (SEC)

- [ ] **SEC-01**: Step-level least-privilege `ToolPermissions` (read/write/exec/git/network/secrets/spawn/mcp/integrations); `exec`/`network`/`secrets`/`spawn_subagents` default OFF; effective = intersection(owner, workflow, step) (INV-9, A4, §8)
- [ ] **SEC-02**: `ExecutionPolicy` enforces `exec`/`network`/`secrets` at runtime — command allow/deny, egress default-deny, resource caps (§8, N3)
- [ ] **SEC-03**: A `secret_scan` executable hook (blocking on `before_write`/`pre_commit`) complements the coarse `security` gate (R13, §30)

### Model policy (MODL)

- [ ] **MODL-01**: A `ModelResolver` applies resolution order user-override > step > agent > workflow > global (Haiku), with cost_class + ordered fallback chain (A10, §20, N11)
- [ ] **MODL-02**: Users pick any allowed model per agent in the composer; `model_overrides: {agent_id → model_id}` rides in the run payload, applied at the top of resolution, and is persisted per run (A12, §20)
- [ ] **MODL-03**: A registered `ModelCatalog` lists selectable models (label/provider/cost_class/context/`user_allowed`), surfaced via `/api/capabilities` (§20)

### Workspace / runtime & repos (RUNT)

- [ ] **RUNT-01**: `RuntimeEnvironment` + `Workspace` + `ExecutionPolicy` ports with a `LocalSandboxRuntime` impl; prototype's `RunSandbox` becomes a git-off, exec-off Workspace (Q-N1, §14, INV-6)
- [ ] **RUNT-02**: Repo context as first-class artifacts/providers — `RepoInventory`, `RepoIndex` (optional), `ContextPack` with ignore rules/binary skip/size caps/summaries (A5, §15)
- [ ] **RUNT-03**: A brownfield repo workflow runs end-to-end locally **without exec** — clone → branch → inventory → read/edit/search → `repo_diff` (file tree + diff) (Q-N7, §14 Phase 4A)
- [ ] **RUNT-04**: Safe local `exec` runs only behind the `security` gate + `ExecutionPolicy` after the N3 threat model, with compile/test/lint validators (§14 Phase 4B, N3)

### Fan-out & merge (FANO)

- [ ] **FANO-01**: Fan-out is engine-owned — an `spawn_subagents` tool (gated by `tools.spawn_subagents`) emits a request the kernel fulfils via `run_fanout`; agents never call the raw library task mechanism (INV-7, Q13, §6/§12)
- [ ] **FANO-02**: `IsolationProvider` (shared_read/sub_sandbox/worktree, writes isolated by default) + `MergeStrategy` + the merge-conflict flow with `on_conflict` policy (human_gate/merge_agent/partial/abort) (Q20/Q34, A6, §13)
- [ ] **FANO-03**: `BudgetManager` enforces caps for subagents, concurrency, tokens, cost, depth, and wall-clock; reserve-before-spawn; graceful abort with partial results (Q17/Q18/Q44, §23)

### Wave scheduler & durable resume (WAVE)

- [ ] **WAVE-01**: A `wave_scheduler` strategy topo-sorts tasks by `depends_on` + `conflict_keys` into waves and runs each wave via fan-out; prototype stays sequential; CP-SAT seam left (Q31/Q32/Q33)
- [ ] **WAVE-02**: Cancellation (cooperative, propagates to children), idempotent step retry, and durable resume — reconnect via `events?after=<seq>`, server restart resumes mid-wave (A9, §21)

### Agent runtime & capability layer (RUN)

- [ ] **RUN-01**: Every agent runs on the LangChain `deepagents` library; no hand-rolled deep agent, no local `deepagents`/`langchain_deepagents` module, no re-implemented loop — banned-pattern CI gate enforces it (INV-13, R15)
- [ ] **RUN-02**: An `AgentRuntimeAdapter` (`langchain_deepagents`) wraps `create_deep_agent`; `PromptAssemblyPolicy` makes the block order declared, not hardcoded (A11, §6/§30, F5/F1)
- [ ] **RUN-03**: Skills/hooks/MCP/integrations are registered, owned, allow-listed, permissioned capabilities — never free-form prompt text or unconstrained tools (INV-11, §30, F2/F3)
- [ ] **RUN-04**: Executable lifecycle/tool-call hooks (`HookHandler`) fire at defined points with `continue|warn|block` outcomes and are persisted to `hook_runs` (N12, §30)
- [ ] **RUN-05**: An `McpClientAdapter` consumes external MCP servers from an allow-listed catalog of famous servers, each with scoped per-owner creds behind the `security` gate (N13, §30)

### Migration discipline (MIG)

- [ ] **MIG-01**: Characterization tests recorded first — deliverable snapshot (byte-identical where deterministic) + semantic event snapshot (volatile fields normalized; `seq` asserted contiguous) for prototype/od_/revision/ppt/code-gen (INV-3, §24)
- [ ] **MIG-02**: Move-don't-copy — each capability extraction deletes the inline original in the same phase; one implementation per behavior; no legacy branch survives its phase (INV-12, §31)
- [ ] **MIG-03**: Per-phase deletion gates — banned-pattern grep (→ 0), dead-code scan, import-linter — plus the §31 migration ledger and its CI guard (`test_migration_ledger.py`); ratchet stays after deletion (INV-12, §31, R14)

### Dynamic API & frontend (API)

- [ ] **API-01**: Dynamic backend contract — `GET /api/workflows`, `/api/workflows/{id}`, `/api/capabilities`, `/api/runs/{id}/artifacts`, `/diff`, `/events?after=<seq>`, plus new run-stream events (subagent_*/wave_*/validator_result/validation_warning/merge_*/gate_*/budget_warning) (A1, §22, Q43)
- [ ] **API-02**: Dynamic composer + capability palette + per-agent model picker + validator/subagent/wave/artifact-diff panels (reusing app-builder `FilesTab`/`AppBuilderPreview`); existing workflows stay at semantic event parity (§22, R6)

## v2 Requirements

Deferred to future release. Tracked but not in the current roadmap.

### Infrastructure (INFRA)

- **INFRA-01**: `EcsRuntime` (and other remote runtimes) behind the unchanged `RuntimeEnvironment` port (Phase 7, §27)
- **INFRA-02**: Warm/dedicated containers, container networking, cloud secrets injection, lease/teardown management (§27)
- **INFRA-03**: Durable queue/worker substrate for long jobs (N8)
- **INFRA-04**: CP-SAT scheduling behind the topo-sort seam (Q32, N10)
- **INFRA-05**: PR/commit **push** + git-hosting integration (GitHub/GitLab) (N4, N5)

## Out of Scope

Explicitly excluded for this spec (designed-for via interfaces, not built). See plan §27.

| Feature | Reason |
|---------|--------|
| ECS/EC2 provisioning & remote containers | Premature infra; a backend swap behind the port, later |
| Untrusted end-user code execution | Highest-risk surface; engineer-only + `security`-gated until the N3 threat model |
| CP-SAT scheduling | Deterministic topo wave-builder is enough; leave a seam |
| Single-file fragment-merge parallelism | Prototype stays sequential (Q33) |
| PR / commit push | Diff-only until git-hosting integration (N4) |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| MIG-01, MIG-02, MIG-03 | Phase 0 | Pending |
| KERN-02 | Phase 0 | Pending |
| AUTH-02, AUTH-03 | Phase 0 | Pending |
| CAP-06 (initial wiring) | Phase 0 | Pending |
| RUN-01 (CI gate) | Phase 0 | Pending |
| MANI-01, MANI-02, MANI-03 | Phase 1 | Pending |
| ART-01, ART-02 | Phase 1 | Pending |
| PERS-01, PERS-02, PERS-03 | Phase 1 | Pending |
| AUTH-01 | Phase 1 | Pending |
| MODL-01, MODL-02, MODL-03 | Phase 1 | Pending |
| KERN-01, KERN-03, KERN-04 | Phase 2 | Pending |
| CAP-02, CAP-03, CAP-04, CAP-05, CAP-07 | Phase 2 | Pending |
| CAP-01 | Phase 3 | Pending |
| GATE-01, GATE-02, GATE-03, GATE-04, GATE-05 | Phase 3 | Pending |
| SEC-01, SEC-03 | Phase 3 | Pending |
| RUN-02, RUN-03, RUN-04 | Phase 3 | Pending |
| RUNT-01, RUNT-02, RUNT-03 | Phase 4 | Pending |
| RUNT-04, SEC-02 | Phase 4 | Pending |
| RUN-05 | Phase 4 | Pending |
| FANO-01, FANO-02, FANO-03 | Phase 5 | Pending |
| WAVE-01, WAVE-02 | Phase 6 | Pending |
| API-01, API-02 | Cross-cutting (parallel track, every phase) | Pending |

**Coverage:**
- v1 requirements: 46 total
- Mapped to phases: 46 (API-01/02 are a cross-cutting parallel track)
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-06*
*Last updated: 2026-06-06 after initialization (translated from specs/003-workflow-engine-decoupling/plan.md)*
