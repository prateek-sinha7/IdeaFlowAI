# Requirements: Workflow Engine Decoupling & Universal Workflow Runtime

**Defined:** 2026-06-06
**Core Value:** A brand-new custom workflow can replicate `prototype` by manifest + AGENT.md only — with zero engine edits (SC-001).
**Source of truth:** `specs/003-workflow-engine-decoupling/plan.md` — every requirement below traces to it; nothing in the plan is omitted.

> Legend: each requirement notes its plan anchor (L# leak, F# factory, INV# invariant, A#/Q#/N# decision, §section, Tier#).
> Internal severity P0–P3 maps externally to CRITICAL/HIGH/MEDIUM/LOW (Q24).

## v1 Requirements

### Safety Net & Migration Discipline (Phase 0A)

- [x] **SAFE-01**: Characterization tests record deliverable byte-snapshots (deterministic output) for `prototype`, `od_prototype`, `prototype_revision`, `ppt`/`od_ppt`, and one code-gen pipeline, driven by a scripted model (`tests/agents/_scripted_model.py`) (§24) ✅ 01-01
- [x] **SAFE-02**: Semantic event-stream snapshots assert event types, order, required fields, and final result, with volatile fields normalized out (timestamps, chunk boundaries, generated IDs, token/usage counts, durations) (INV-3 / §24)
- [x] **SAFE-03**: Monotonic per-run event `seq` is asserted contiguous (not by absolute value) in snapshots (§21/§24)
- [x] **SAFE-04**: Migration-ledger CI guard `tests/test_migration_ledger.py` asserts each `☑` ledger item's banned grep-pattern returns 0 (§31)
- [x] **SAFE-05**: Import-linter contract enforces the kernel imports only capability ports — never legacy `engine`/`factory` internals (§31/§32)
- [x] **SAFE-06**: Banned-pattern CI gate blocks hand-rolled deep agents — `class DeepAgent` / `def deep_agent` / a new `deepagents`/`langchain_deepagents` module / bespoke `for _ in range(max_iterations)` loops outside the adapter (INV-13 / R15)
- [x] **SAFE-07**: Ledger guard + import-linter + banned-pattern gates run in CI and start green/empty, tightening as items delete (§31)

### Per-Run Execution Context & Ownership (Phase 0B)

- [x] **CTX-01**: All `self._*` per-run state (`_od_context`, `_completed_tasks`, `_current_task_block`, `_revision_*`, `_gate_agent_ids`, `_user_id`, `_checkpointer`) moves to a per-run `ExecutionContext` (L14 / INV-2)
- [x] **CTX-02**: The kernel singleton holds no per-run attributes and is immutable after construction (NFR-001 / INV-2)
- [x] **CTX-03**: `parent_run` seeding performs an explicit ownership check that rejects cross-owner access (L16 / INV-8)
- [~] **CTX-04**: ~~Dead `_handle_revision` (`engine.py:2138-2251`) is deleted (D1)~~ — **VOIDED/DEFERRED (2026-06-07): `_handle_revision` is LIVE — the frontend `run_revision` PPT-revision handler (`app/api/websocket.py:625`), not dead. Deletion would break PPT revision (CTX-05). Deferred pending a product decision on retiring `run_revision`. See Phase 2 `02-02-SUMMARY.md`.**
- [x] **CTX-05**: No behavior change — deliverable snapshots stay byte-identical and event snapshots stay at semantic parity (INV-3)

### Context Compaction / Token-Trim (Phase 0C)

- [x] **COMPACT-01**: The dead `_extract_html_skeleton` is wired as build-task-2+ context compaction (Tier#1 / L13)
- [x] **COMPACT-02**: The change is gated on the semantic snapshot (same pages/routes, equal-or-better validation pass) plus a measured token/cost delta — not byte-identity (the sanctioned INV-3 exception)
- [x] **COMPACT-03**: A measured token reduction is demonstrated on a multi-task build (Accept criterion)

### Manifests & Compiler (Phase 1A)

- [ ] **MAN-01**: `WorkflowManifest` schema + loader/validator reads hand-authored file-backed YAML manifests (one per workflow) (Q5/Q7 / §32)
- [ ] **MAN-02**: `WorkflowCompiler` compiles a manifest to a validated typed `CompiledWorkflow` / `ExecutionPlan` (DAG of `Step`s) — thin, no DSL, no control flow in manifests (INV-5)
- [x] **MAN-03**: Compiler validates every capability reference against the `CapabilityRegistry` + trust + owner allow-list; unknown/not-allowed names → compile error (INV-4)
- [ ] **MAN-04**: Every current pipeline runs from a compiled plan; artifacts still flow via the legacy `accumulated_outputs` mirror (no schema change yet) (Phase 1A Accept)
- [ ] **MAN-05**: `pipeline_type` retained only as a temporary migration alias (Q1)

### Typed Artifacts, Lineage & Persistence (Phase 1B)

- [ ] **ART-01**: `ArtifactGraph` + `ArtifactRef` — typed, content-addressed, owner-scoped DAG replaces loose `accumulated_outputs: dict[str,str]` (L15 / §17 / INV-10)
- [ ] **ART-02**: Every artifact write records producer step/agent/task, content hash, location, version, parents, visibility, retention (INV-10)
- [ ] **ART-03**: Typed `produces`/`consumes` routing replaces string matching; revision lineage tracked via `parents`/`derived_from` (§17)
- [ ] **ART-04**: Default retention `run_ttl` (= 48h sandbox TTL); `keep`/`days:N` overrides (N9 — confirm)
- [ ] **PERSIST-01**: Migration adds `artifact_refs`, extends `workflow_runs` (+ workspace_id, owner_id, parent_run_id, source_run_id, plan_id, status, budget_snapshot_json), adds `workspaces`, `run_events` — additive only, every table carries `owner_id` + `workspace_id` (§18 / Q3)
- [ ] **PERSIST-02**: Dual-write typed refs alongside the legacy mirror; reads migrate incrementally; the `accumulated_outputs` mirror is deleted in this phase once reads migrate (L15 / §31)
- [ ] **PERSIST-03**: `run_events` rows carry monotonic per-run `seq` + `event_id` for durable replay/resume; index (run_id, seq) (§18/§21)
- [ ] **AUTHZ-01**: Ownership model `user → workspace → (repository|project) → run → {artifacts, subagent_runs}`; everything carries `owner_id` + `workspace_id` (INV-8 / §19)
- [ ] **AUTHZ-02**: Default-deny store-layer scoped-query helper; all artifact/run reads go through it; no cross-owner read/write (§19)
- [ ] **AUTHZ-03**: Anonymous runs get a synthetic `anon:<session_id>` owner — never `None` (§19)
- [ ] **AUTHZ-04**: Authz-denial tests (cross-owner parent/artifact access) pass (Phase 1B Accept / R8)

### Model Policy & Per-Agent Selection (Phase 1C)

- [ ] **MODEL-01**: `ModelResolver` on `ExecutionContext` applies resolution order (highest wins): user per-agent override > `step.model` > agent default (AGENT.md) > `workflow.model` > global default (Haiku) (§20 / A10)
- [ ] **MODEL-02**: `ModelPolicy` carries model id, `max_tokens` (doc-only; runtime caps at `MAX_OUTPUT_TOKENS`), `cost_class` (cheap/standard/premium), ordered `fallback` chain on throttle/error (§20)
- [ ] **MODEL-03**: User per-agent `model_overrides: {agent_id → model_id}` applied at the top of the order and persisted per run (A12 / §18 `run_capabilities`)
- [ ] **MODEL-04**: `ModelCatalog` registered capability lists selectable models (label, provider, cost_class, context window, `user_allowed`); surfaced via `/api/capabilities` (§20)
- [ ] **MODEL-05**: Global default stays Haiku; per-step/workflow model honored (Phase 1C Accept / N11 — confirm premium policy + fallback chain)

### Prototype as Manifest — Parity Proof (Phase 2)

- [ ] **PARITY-01**: Implement `single_shot` + `task_loop` execution strategies (Q8/L7)
- [ ] **PARITY-02**: Implement `single_file` / `serialized_sandbox` / `streamed_text` deliverable resolvers (L2/L9/L10)
- [ ] **PARITY-03**: Implement the `opendesign` context provider + declared `seed_files` + `heading_tasks` task parser (L11/L12/Q11)
- [ ] **PARITY-04**: `html_skeleton` registered as a `CompactionStrategy`, re-expressing Phase 0C behind the capability (behavior-preserving vs 0C) (Q35 / L13)
- [ ] **PARITY-05**: `prototype`, `od_prototype` (alias + OpenDesign provider), and `prototype_revision` (variant: `seed_files.from_run` + `previous_run` provider + post-edit `validation` gate) all expressed as manifests (§10)
- [ ] **PARITY-06**: Delete kernel leaks L1–L12 — `_PPT_PIPELINE_TYPES`/`_PROTOTYPE_PIPELINE_TYPES`/`REVISION_FILE_NAME`, `_resolve_final_output`, `_sanitize_carousel_deck_html`/`_unwrap_artifact`, revision seeding/post-fix, `SKIP_PLANNER_FOR_PROTOTYPE`, `ALWAYS_CLARIFY` defaults, `spec.id == "prototype-build"`, HTML readback branch, build-loop internals (`_run_build_task_loop`/`_write_build_reference_files`/`_count_plan_tasks`/`_extract_task_block`/`_run_validation_fix_loop`/`_load_template_example`), `_build_context_message` per-pipeline branches (§4/§31)
- [ ] **PARITY-07**: PPT deliverable handled by a `ppt` resolver + post-step transform/validator (L3)
- [ ] **PARITY-08**: Kernel has zero workflow-name/agent-id branches — grep gate `if pipeline_type`/`spec.id ==` returns 0 (INV-1)
- [ ] **PARITY-09**: prototype/od_/revision/ppt/code-gen at deliverable parity + semantic event parity vs the post-0C baseline (Phase 2 Accept)

### Capability Registry, Gates & Tool Permissions (Phase 3)

- [ ] **CAP-01**: One `CapabilityRegistry` keyed by `(kind, name)` for all capability kinds (strategies, validators, deliverables, context providers, gates, isolation, merge, task parsers, worker agents, runtimes, skills, hooks, tools, MCP, integrations) (§7 / INV-4)
- [ ] **CAP-02**: Self-registering plugins (`@register(kind, name)`) + a startup `discover()` imports all capability packages — no central if/elif (§32)
- [ ] **CAP-03**: Trust model — built-in/file manifests reference any registered capability; user/DB manifests validated against per-capability `user_allowed` + owner allow-list (§7 / Q2/Q27)
- [ ] **GATE-01**: `GateHandler` registry with `human`, `validation`, `approval`, `security` gates, declared per step (ordered), evaluated at the step boundary; outcome ∈ pass|block|wait_human (§9 / A7)
- [ ] **GATE-02**: `validation` gate makes the declared-but-unimplemented `Validation_Gate` real — runs validators, blocks on policy, emits `validation_warning` on residuals (§9)
- [ ] **GATE-03**: `human` gate preserves semantic event parity (existing `_run_review_gate` + `review_gate_*`) (INV-3)
- [ ] **TOOLPERM-01**: `ToolPermissions` least-privilege grant set: read_files (ON), write_files/git/spawn_subagents (OFF), exec/network (OFF), secrets/mcp/integrations (none) (§8 / INV-9)
- [ ] **TOOLPERM-02**: Effective perms = intersection(owner_allow_list, workflow_ceiling, step_grant); AGENT.md may only lower a default, never raise (§8)
- [ ] **TOOLPERM-03**: Enforcement at `factory._build_runner_tools` (binds only granted tool sets) and `Workspace.ExecutionPolicy` (runtime exec/network/secrets gating) (§8)
- [ ] **VALID-01**: `Validator` registry; manifest lists `validators: [...]` per step; `DeliverableContext` carries path/content/Workspace/task-meta and may request browser/compile/test/static-analysis runners (Q21/Q22)
- [ ] **VALID-02**: Generic fix-loop (deliverable name + max_attempts + fix-prompt template from `FixPolicy`); default warn-non-critical / block-critical, then `validation_warning` with residuals (Q23/Q25)
- [ ] **VALID-03**: Severity P0–P3 internal with one mapping function to CRITICAL/HIGH/MEDIUM/LOW for the UI (Q24)
- [ ] **VALID-04**: Migrate `html_static`/`html_render` to registered validators; each run/attempt → `validation_results` row (§16/§18)
- [ ] **VALID-05**: Tier#4/#5/#6 ship as registered validators — `spec_plan_coverage` (pre-build analyze), `task_done_when` (per-task acceptance), `design_quality` (tokens/placeholder/a11y, warnings-first) (Q38)
- [ ] **AGENTRT-01**: `AgentRuntimeAdapter` wraps `create_deep_agent`; `langchain_deepagents` is the mandated adapter; future `claude_code_cli`/`custom_runner` slot in without kernel edits (§6/§30 / INV-13)
- [ ] **AGENTRT-02**: `create_deep_agent` is called only inside the `langchain_deepagents` adapter (F5 deletion gate)
- [ ] **AGENTRT-03**: `PromptAssemblyPolicy` promotes the hardcoded block order (`factory.py:174-255`: injects→guardrails→skills→hooks→constitution→body) to a declared, registry-resolved policy (F1 / §6/§30)
- [ ] **AGENTRT-04**: `tool_provider` registry replaces the closed `_build_runner_tools` switch (`factory.py:384-446`) (F2)
- [ ] **AGENTRT-05**: `skill_provider` / `hook_provider` replace inline skills/hooks injection (`factory.py:220-245`); behavioral hook becomes a non-executable provider sub-type (F3)
- [ ] **AGENTRT-06**: Constitution injection made sync-safe / pre-warmed so a Postgres-stored Constitution is injected in production; constitution-injected-in-prod test passes (R12 / F4)

### Local Workspace Runtime & Repo Workflows — No Exec (Phase 4A)

- [ ] **RUNTIME-01**: `RuntimeEnvironment` port (read/write/search/exec_command/clone_repo/create_branch/git_diff/teardown) + `LocalSandboxRuntime` impl over the per-run disk dir (§6/§14)
- [ ] **RUNTIME-02**: One `Workspace` abstraction (fs + optional git + optional exec + `ExecutionPolicy`); prototype's `RunSandbox` becomes a `has_git=False, exec=off` Workspace — no engine fork repo-vs-artifact (R3/§14)
- [ ] **RUNTIME-03**: `repositories` + `workspaces` rows persisted (§18)
- [ ] **REPO-01**: `RepoInventory` (`kind=repo_inventory`) — file tree, language stats, dependency graph, ignore rules (`.gitignore` + `.flowinignore`), binary-file skip, size caps, optional summaries (§15)
- [ ] **REPO-02**: `RepoIndex` (optional, large repos) behind a port; default grep/glob for small repos; threshold = N6 (§15 — confirm N6/N10)
- [ ] **REPO-03**: `ContextPack` (`kind=context_pack`) — targeted per-task subset via a `context_selector` capability, lineage-tracked; surfaced via the `repo` context provider (§15)
- [ ] **REPO-04**: `repo_diff` `DeliverableResolver` produces app-builder-style file tree + per-file diff (Q-N7 — confirm N5/N7)
- [ ] **REPO-05**: A sample brownfield workflow runs end-to-end locally without execution (clone → branch → inventory → agents read/edit/search → diff surface); prototype unaffected (Phase 4A Accept)

### Safe Local Exec — Gated on N3 (Phase 4B)

- [ ] **EXEC-01**: A constrained `exec` profile runs only behind the `security` gate + `ExecutionPolicy` — command allow/deny, network default-deny, resource caps (cpu_seconds/mem_mb), ephemeral creds (§8/§14 / N3 ⚠️ — own threat model first)
- [ ] **EXEC-02**: compile/test/lint validators land; a sample compile/test validator passes; egress denied by default (Phase 4B Accept)

### Engine-Owned Fan-Out & Merge (Phase 5)

- [ ] **FANOUT-01**: `spawn_subagents(tasks=[{agent,input}], mode=…)` tool bound only to steps granted `tools.spawn_subagents`; it emits a structured request — the kernel fulfils it (INV-7 / §6/§12)
- [ ] **FANOUT-02**: Kernel `run_fanout(requests, ctx)` funnels both declarative (`step.fanout`) and runtime (tool) entry points (§12)
- [ ] **FANOUT-03**: Worker selection — `agent="self"` (N copies) or a named worker from `allowed_workers` + registry (Q14)
- [ ] **FANOUT-04**: Mode parallel (capped `asyncio.gather`) or sequential; engine enforces `max_concurrency` (Q15)
- [ ] **FANOUT-05**: `IsolationProvider.allocate(scope)` → shared_read | sub_sandbox | worktree; writes default isolated (Q20/Q34 — confirm N2)
- [ ] **FANOUT-06**: Results return both files/artifacts and a structured summary (Q16)
- [ ] **FANOUT-07**: `MergeStrategy` integrates fragments (copy_disjoint/git_3way/json/html_fragment) (§13)
- [ ] **FANOUT-08**: Merge-conflict flow — write a `merge_conflict` artifact + emit event; resolve per `on_conflict` policy (human_gate default | merge_agent (bounded) | partial | abort) (§13 / A6)
- [ ] **FANOUT-09**: `BudgetManager` reserves-before-spawn and enforces total subagents, concurrency, tokens, cost, wall-clock, recursion, fan-out depth (`ctx.depth`); `BudgetExceeded` aborts gracefully with partial results (Q17/Q18/Q44)
- [ ] **FANOUT-10**: Each child → a `subagent_runs` row; events `subagent_spawned`/`subagent_result`/`merge_*` (§12/§18)
- [ ] **FANOUT-11**: Fan-out cancellation propagates to children (§21)

### Wave Scheduler & Durable Resume (Phase 6)

- [ ] **WAVE-01**: `wave_scheduler` strategy topo-sorts by `depends_on` + `conflict_keys` into waves, runs each wave via fan-out; deterministic builder, CP-SAT seam left (Q31/Q32)
- [ ] **WAVE-02**: `wave_runs` persistence; a multi-file workflow runs disjoint tasks in parallel waves; prototype stays sequential (Q33 / Phase 6 Accept)
- [ ] **WAVE-03**: Resume mid-wave via `subagent_runs`/`wave_runs` records after a restart (§21 / N8 — confirm)

### Cancellation, Retry & Resume (cross-cutting; basic in Phase 0, hardened 5–6)

- [ ] **RESUME-01**: Cooperative `cancel_event` checked per-chunk and at step/gate/fanout/wave boundaries; on cancel → mark `cancelled`, preserve partial artifacts, `teardown()` isolated workspaces, emit `pipeline_cancelled` (§21)
- [ ] **RESUME-02**: Idempotent per-step retry `retry: {max, on}` for transient errors, keyed by `(run_id, step_id, input content_hash)`; reuses the existing artifact on hash match — distinct from the validator fix-loop (§21)
- [ ] **RESUME-03**: Reconnect = durable replay from `run_events` via `after=<last_seq>`, idempotent by `event_id` (§21/§22)
- [ ] **RESUME-04**: Server restart = `restore_non_terminal_runs` extended to step granularity; `waiting_for_user` gates resume on user action; in-flight steps resume from checkpoint or re-run idempotently (§21)

### Agent Runtime, Skills, Hooks, MCP & Integrations (§30; lands across Phases 1B/3/4+)

- [ ] **HOOK-01**: `HookHandler` executable lifecycle/tool-call hooks bound to events (before/after run·step·tool_call·write, post_task, pre/post_commit, on_validation, before/after_merge, or `*`); outcome continue|warn|block; blocking hooks halt the offending action (N12 / §30)
- [ ] **HOOK-02**: Canonical hooks — `secret_scan` (before_write/pre_commit, blocking), `otel_tracing`/logging (`*`, non-blocking → observability), pre/post_commit, post_task (§30/§23)
- [ ] **HOOK-03**: Hooks are permissioned (a command-running hook needs `exec`, a git hook needs `git`, a scanner needs `read_files`); engineer-registered, users attach allow-listed only (INV-9/§30)
- [ ] **HOOK-04**: Every hook firing → a `hook_runs` row for replay/debug; legacy prompt-only hook survives as a `kind: behavioral` non-executable sub-type (§18/§30)
- [ ] **MCP-01**: `McpClientAdapter` (e.g. `langchain-mcp-adapters` `MultiServerMCPClient`) connects to external MCP servers (stdio/SSE/HTTP), lists tools/resources/prompts, binds allowed ones into the agent tool set (N13 / §30)
- [ ] **MCP-02**: Allow-listed famous-server catalog (GitHub, GitLab, Jira/Atlassian, Confluence, Slack, Notion, Linear, Sentry, Figma, Filesystem, Postgres, Google Drive, web-search, Playwright, …), each with transport + exposed tools + scoped per-owner creds + `user_allowed` (§30)
- [ ] **MCP-03**: `McpCapabilityRegistry` — compiler validates `tools.mcp` only names tools from servers the step + owner may reach; unknown `server.tool` → compile error (§7/§30)
- [ ] **MCP-04**: Powerful servers (Filesystem/Postgres/write/network) sit behind the `security` gate + scoped creds + `secrets` permission (R13/§30)
- [ ] **INTEG-01**: `integration_provider` capabilities (GitHub/GitLab/Jira/Slack/Confluence/Figma/OpenDesign) make repo/GitHub reachable from the unified `create_runner` path, not only the handoff pipeline (§30)
- [ ] **INTEG-02**: `integrations` tool-permission scopes (e.g. `gitlab_read`, `jira_read`) default none; scoped per-owner creds (§8/§30/R13)
- [ ] **SKILL-01**: `skill_provider` capabilities (ui · disk · template · repo) with a provider interface + versioning replace the flattened skill content list (§30)
- [ ] **CAPRUN-01**: `run_capabilities` persistence records the active runtime + resolved skill/hook/integration/MCP names + versions + `model_overrides` per run for replay/debug (§18/§30)

### Dynamic API / Frontend Contract (parallel track, §22)

- [ ] **API-01**: `GET /api/workflows` → list + metadata; `GET /api/workflows/{id}` → full step configs, gates, validators, deliverable, declared capabilities (§22)
- [ ] **API-02**: `GET /api/capabilities` → registry palette (kind, name, `user_allowed`, config schema) incl. runtimes, skills, hooks, MCP servers, integrations, model catalog — with required auth + permission scopes (§22/§7/§30)
- [ ] **API-03**: Run stream (WS/ndjson) emits existing events + new (`subagent_*`, `wave_*`, `validator_result`, `validation_warning`, `merge_*`, `budget_warning`, `gate_*`); existing-workflow contract stays at semantic parity (Q43/INV-3)
- [ ] **API-04**: `GET /api/runs/{id}/artifacts` → typed artifact tree (lineage); `GET /api/runs/{id}/diff` → repo diff (§22)
- [ ] **API-05**: `GET /api/runs/{id}/events?after=<seq>` → durable event replay (monotonic seq + event_id) for reconnect/resume (§22/§21)
- [ ] **API-06**: Dynamic composer + capability palette + per-agent model picker; validator/issue panel; subagent + wave tree; artifact/diff viewer (reuse app-builder `FilesTab`/`AppBuilderPreview`) — additive panels (§22)

### Budgets & Observability (cross-cutting, §23)

- [ ] **OBS-01**: `BudgetManager` enforces per-run AND per-workspace ceilings (tokens, €, subagents, depth, concurrency, wall-clock); reserve-before-spawn; graceful abort; snapshot persisted on the run (§23/§18)
- [ ] **OBS-02**: Logging/tracing hooks bound to `*` emit OpenTelemetry-style spans/logs per lifecycle event → native observability; each firing lands in `hook_runs` (§23/§30)

### Anti-Duplication & Deletion Ledger (cross-cutting, INV-12/§31)

- [x] **DEL-01**: Every legacy element follows wrap → rewire call-sites → delete, completed within the phase that supersedes it; one implementation per behavior (INV-12)
- [x] **DEL-02**: Each phase ships a banned-pattern test (grep → 0 for deleted symbols/branches), a dead-code scan (ruff/vulture), and the import-linter rule as exit gates; Definition of Done = behavior moved + call-sites rewired + legacy deleted + gates green + snapshots green (§31) — _ledger ratchet (01-03) + banned-pattern test + vulture dead-code scan + import-linter contract (01-04) all shipped and green_
- [x] **DEL-03**: Banned-pattern tests are ratchets — a deleted symbol's reintroduction fails CI (§31)
- [x] **DEL-04**: The `specs/003-…/migration-ledger.md` mirrors the §31 ledger operationally (L1–L16, F1–F5, D1) with status + deleting commit SHA, asserted by CI (§31)

## v2 Requirements

Deferred to a future milestone; tracked but not in this roadmap.

### Remote Runtime

- **ECS-01**: `EcsRuntime` behind the unchanged `RuntimeEnvironment` port (Phase 7, separate spec; §27)
- **ECS-02**: Warm/dedicated containers, container networking, cloud secrets injection, teardown/lease management (§27)

### Advanced Scheduling & Git

- **SCHED-01**: CP-SAT scheduling (topo seam left in Phase 6; §27/Q32)
- **MERGE-01**: Single-file fragment-merge parallelism (prototype stays sequential; §27/Q33)
- **GIT-01**: PR/commit push to git hosting (diff-only until N4; §27)
- **WF-DB-01**: DB-backed user-authored workflows (file-backed manifests only for now; Q5)

## Out of Scope

Explicitly excluded this milestone (designed-for via interfaces, not built).

| Feature | Reason |
|---------|--------|
| ECS/EC2 provisioning, warm/dedicated containers | Backend swap behind `RuntimeEnvironment` port — Phase 7 / separate spec (§27 / N1) |
| Container networking & cloud secrets injection, prod teardown/lease | Infra follow-up; local runtime only this milestone (§27) |
| CP-SAT scheduling | Deterministic topo wave-builder sufficient; seam left (Q32/§27) |
| Single-file fragment-merge parallelism | Prototype stays sequential; opt-in later (Q33/§27) |
| Untrusted end-user code execution | Trust seam exists; engineer-only + `security`-gated until N3 (§27/R5) |
| PR/commit push | Diff-only until git-hosting integration (N4/§27) |
| DB-backed user-authored workflows | File-backed hand-authored manifests now (Q5) |
| Hand-rolled / local `deepagents` runtime | Banned — always import the real library (INV-13/R15) |
| Auto-generated manifest index as source of truth | Manifests are hand-authored; generated index optional later, never authoritative (§28) |

## Traceability

Each v1 requirement maps to exactly one phase. Phases are GSD integers 1–12, mapped 1:1 to plan §25 sub-phases (`[0A]…[6]`). v2 / Out-of-Scope items are intentionally unmapped.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SAFE-01, SAFE-02, SAFE-03, SAFE-05, SAFE-06, SAFE-07 | Phase 1 [0A] | Pending |
| SAFE-04 | Phase 1 [0A] | Done (01-03) |
| DEL-02 | Phase 1 [0A] | Partial (ledger ratchet done 01-03; scans pending 01-04) |
| DEL-01, DEL-03, DEL-04 | Phase 1 [0A] | Done (01-03) |
| CTX-01, CTX-02, CTX-03, CTX-04, CTX-05 | Phase 2 [0B] | Pending |
| COMPACT-01, COMPACT-02, COMPACT-03 | Phase 3 [0C] | Pending |
| MAN-01, MAN-02, MAN-03, MAN-04, MAN-05 | Phase 4 [1A] | Pending |
| API-01 | Phase 4 [1A] | Pending |
| ART-01, ART-02, ART-03, ART-04 | Phase 5 [1B] | Pending |
| PERSIST-01, PERSIST-02, PERSIST-03 | Phase 5 [1B] | Pending |
| AUTHZ-01, AUTHZ-02, AUTHZ-03, AUTHZ-04 | Phase 5 [1B] | Pending |
| CAPRUN-01 | Phase 5 [1B] | Pending |
| API-04, API-05 | Phase 5 [1B] | Pending |
| MODEL-01, MODEL-02, MODEL-03, MODEL-04, MODEL-05 | Phase 6 [1C] | Pending |
| PARITY-01, PARITY-02, PARITY-03, PARITY-04, PARITY-05, PARITY-06, PARITY-07, PARITY-08, PARITY-09 | Phase 7 [2] | Pending |
| CAP-01, CAP-02, CAP-03 | Phase 8 [3] | Pending |
| GATE-01, GATE-02, GATE-03 | Phase 8 [3] | Pending |
| TOOLPERM-01, TOOLPERM-02, TOOLPERM-03 | Phase 8 [3] | Pending |
| VALID-01, VALID-02, VALID-03, VALID-04, VALID-05 | Phase 8 [3] | Pending |
| AGENTRT-01, AGENTRT-02, AGENTRT-03, AGENTRT-04, AGENTRT-05, AGENTRT-06 | Phase 8 [3] | Pending |
| SKILL-01 | Phase 8 [3] | Pending |
| HOOK-01, HOOK-02, HOOK-03, HOOK-04 | Phase 8 [3] | Pending |
| OBS-02 | Phase 8 [3] | Pending |
| API-02, API-03, API-06 | Phase 8 [3] | Pending |
| RUNTIME-01, RUNTIME-02, RUNTIME-03 | Phase 9 [4A] | Pending |
| REPO-01, REPO-02, REPO-03, REPO-04, REPO-05 | Phase 9 [4A] | Pending |
| MCP-01, MCP-02, MCP-03, MCP-04 | Phase 9 [4A] | Pending |
| INTEG-01, INTEG-02 | Phase 9 [4A] | Pending |
| EXEC-01, EXEC-02 | Phase 10 [4B] | Pending |
| FANOUT-01, FANOUT-02, FANOUT-03, FANOUT-04, FANOUT-05, FANOUT-06, FANOUT-07, FANOUT-08, FANOUT-09, FANOUT-10, FANOUT-11 | Phase 11 [5] | Pending |
| OBS-01 | Phase 11 [5] | Pending |
| RESUME-01 | Phase 11 [5] | Pending |
| WAVE-01, WAVE-02, WAVE-03 | Phase 12 [6] | Pending |
| RESUME-02, RESUME-03, RESUME-04 | Phase 12 [6] | Pending |

**Coverage:**

- v1 requirements: 117 total
- Mapped to phases: 117
- Unmapped: 0 ✓
- v2 (deferred, intentionally unmapped): ECS-01, ECS-02, SCHED-01, MERGE-01, GIT-01, WF-DB-01

**Per-phase counts:** P1=11 · P2=5 · P3=3 · P4=6 · P5=14 · P6=5 · P7=9 · P8=29 · P9=14 · P10=2 · P11=13 · P12=6 (= 117)

---
*Requirements defined: 2026-06-06*
*Last updated: 2026-06-06 after initial definition*
