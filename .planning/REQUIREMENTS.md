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

- [x] **MAN-01**: `WorkflowManifest` schema + loader/validator reads hand-authored file-backed YAML manifests (one per workflow) (Q5/Q7 / §32)
- [x] **MAN-02**: `WorkflowCompiler` compiles a manifest to a validated typed `CompiledWorkflow` / `ExecutionPlan` (DAG of `Step`s) — thin, no DSL, no control flow in manifests (INV-5)
- [x] **MAN-03**: Compiler validates every capability reference against the `CapabilityRegistry` + trust + owner allow-list; unknown/not-allowed names → compile error (INV-4)
- [x] **MAN-04**: Every current pipeline runs from a compiled plan; artifacts still flow via the legacy `accumulated_outputs` mirror (no schema change yet) (Phase 1A Accept)
- [x] **MAN-05**: `pipeline_type` retained only as a temporary migration alias (Q1)

### Typed Artifacts, Lineage & Persistence (Phase 1B)

- [x] **ART-01**: `ArtifactGraph` + `ArtifactRef` — typed, content-addressed, owner-scoped DAG replaces loose `accumulated_outputs: dict[str,str]` (L15 / §17 / INV-10)
- [x] **ART-02**: Every artifact write records producer step/agent/task, content hash, location, version, parents, visibility, retention (INV-10)
- [x] **ART-03**: Typed `produces`/`consumes` routing replaces string matching; revision lineage tracked via `parents`/`derived_from` (§17)
- [x] **ART-04**: Default retention = **keep-by-default** — run artifacts are retained indefinitely; `run_ttl`/`days:N` are opt-in overrides (N9 — DECIDED keep-by-default, Phase 22 / DECIDE-01)
- [x] **PERSIST-01**: Migration adds `artifact_refs`, extends `workflow_runs` (+ workspace_id, owner_id, parent_run_id, source_run_id, plan_id, status, budget_snapshot_json), adds `workspaces`, `run_events` — additive only, every table carries `owner_id` + `workspace_id` (§18 / Q3)
- [x] **PERSIST-02**: Dual-write typed refs alongside the legacy mirror; reads migrate incrementally; the `accumulated_outputs` mirror is deleted in this phase once reads migrate (L15 / §31)
- [x] **PERSIST-03**: `run_events` rows carry monotonic per-run `seq` + `event_id` for durable replay/resume; index (run_id, seq) (§18/§21)
- [x] **AUTHZ-01**: Ownership model `user → workspace → (repository|project) → run → {artifacts, subagent_runs}`; everything carries `owner_id` + `workspace_id` (INV-8 / §19)
- [x] **AUTHZ-02**: Default-deny store-layer scoped-query helper; all artifact/run reads go through it; no cross-owner read/write (§19)
- [x] **AUTHZ-03**: Anonymous runs get a synthetic `anon:<session_id>` owner — never `None` (§19)
- [x] **AUTHZ-04**: Authz-denial tests (cross-owner parent/artifact access) pass (Phase 1B Accept / R8)

### Model Policy & Per-Agent Selection (Phase 1C)

- [x] **MODEL-01**: `ModelResolver` on `ExecutionContext` applies resolution order (highest wins): user per-agent override > `step.model` > agent default (AGENT.md) > `workflow.model` > global default (Haiku) (§20 / A10)
- [x] **MODEL-02**: `ModelPolicy` carries model id, `max_tokens` (doc-only; runtime caps at `MAX_OUTPUT_TOKENS`), `cost_class` (cheap/standard/premium), ordered `fallback` chain on throttle/error (§20)
- [x] **MODEL-03**: User per-agent `model_overrides: {agent_id → model_id}` applied at the top of the order and persisted per run (A12 / §18 `run_capabilities`)
- [x] **MODEL-04**: `ModelCatalog` registered capability lists selectable models (label, provider, cost_class, context window, `user_allowed`); surfaced via `/api/capabilities` (§20)
- [x] **MODEL-05**: Global default stays Haiku with an ordered `fallback` chain on throttle/error; per-step/workflow model honored; premium (`cost_class=premium`) models selectable by ALL tiers — **premium-open-to-all-tiers** (no per-tier premium gating) (Phase 1C Accept / N11 — DECIDED premium-open-to-all-tiers, Phase 22 / DECIDE-02)

### Prototype as Manifest — Parity Proof (Phase 2)

- [x] **PARITY-01**: Implement `single_shot` + `task_loop` execution strategies (Q8/L7)
- [x] **PARITY-02**: Implement `single_file` / `serialized_sandbox` / `streamed_text` deliverable resolvers (L2/L9/L10)
- [x] **PARITY-03**: Implement the `opendesign` context provider + declared `seed_files` + `heading_tasks` task parser (L11/L12/Q11)
- [x] **PARITY-04**: `html_skeleton` registered as a `CompactionStrategy`, re-expressing Phase 0C behind the capability (behavior-preserving vs 0C) (Q35 / L13)
- [x] **PARITY-05**: `prototype`, `od_prototype` (alias + OpenDesign provider), and `prototype_revision` (variant: `seed_files.from_run` + `previous_run` provider + post-edit `validation` gate) all expressed as manifests (§10)
- [x] **PARITY-06**: Delete kernel leaks L1–L12 — `_PPT_PIPELINE_TYPES`/`_PROTOTYPE_PIPELINE_TYPES`/`REVISION_FILE_NAME`, `_resolve_final_output`, `_sanitize_carousel_deck_html`/`_unwrap_artifact`, revision seeding/post-fix, `SKIP_PLANNER_FOR_PROTOTYPE`, `ALWAYS_CLARIFY` defaults, `spec.id == "prototype-build"`, HTML readback branch, build-loop internals (`_run_build_task_loop`/`_write_build_reference_files`/`_count_plan_tasks`/`_extract_task_block`/`_run_validation_fix_loop`/`_load_template_example`), `_build_context_message` per-pipeline branches (§4/§31)
- [x] **PARITY-07**: PPT deliverable handled by a `ppt` resolver + post-step transform/validator (L3)
- [x] **PARITY-08**: Kernel has zero workflow-name/agent-id branches — grep gate `if pipeline_type`/`spec.id ==` returns 0 (INV-1)
- [x] **PARITY-09**: prototype/od_/revision/ppt/code-gen at deliverable parity + semantic event parity vs the post-0C baseline (Phase 2 Accept)

### Capability Registry, Gates & Tool Permissions (Phase 3)

- [x] **CAP-01**: One `CapabilityRegistry` keyed by `(kind, name)` for all capability kinds (strategies, validators, deliverables, context providers, gates, isolation, merge, task parsers, worker agents, runtimes, skills, hooks, tools, MCP, integrations) (§7 / INV-4)
- [x] **CAP-02**: Self-registering plugins (`@register(kind, name)`) + a startup `discover()` imports all capability packages — no central if/elif (§32)
- [x] **CAP-03**: Trust model — built-in/file manifests reference any registered capability; user/DB manifests validated against per-capability `user_allowed` + owner allow-list (§7 / Q2/Q27)
- [x] **GATE-01**: `GateHandler` registry with `human`, `validation`, `approval`, `security` gates, declared per step (ordered), evaluated at the step boundary; outcome ∈ pass|block|wait_human (§9 / A7)
- [x] **GATE-02**: `validation` gate makes the declared-but-unimplemented `Validation_Gate` real — runs validators, blocks on policy, emits `validation_warning` on residuals (§9)
- [x] **GATE-03**: `human` gate preserves semantic event parity (existing `_run_review_gate` + `review_gate_*`) (INV-3)
- [x] **TOOLPERM-01**: `ToolPermissions` least-privilege grant set: read_files (ON), write_files/git/spawn_subagents (OFF), exec/network (OFF), secrets/mcp/integrations (none) (§8 / INV-9)
- [x] **TOOLPERM-02**: Effective perms = intersection(owner_allow_list, workflow_ceiling, step_grant); AGENT.md may only lower a default, never raise (§8)
- [x] **TOOLPERM-03**: Enforcement at `factory._build_runner_tools` (binds only granted tool sets) and `Workspace.ExecutionPolicy` (runtime exec/network/secrets gating) (§8)
- [x] **VALID-01**: `Validator` registry; manifest lists `validators: [...]` per step; `DeliverableContext` carries path/content/Workspace/task-meta and may request browser/compile/test/static-analysis runners (Q21/Q22)
- [x] **VALID-02**: Generic fix-loop (deliverable name + max_attempts + fix-prompt template from `FixPolicy`); default warn-non-critical / block-critical, then `validation_warning` with residuals (Q23/Q25)
- [x] **VALID-03**: Severity P0–P3 internal with one mapping function to CRITICAL/HIGH/MEDIUM/LOW for the UI (Q24)
- [x] **VALID-04**: Migrate `html_static`/`html_render` to registered validators; each run/attempt → `validation_results` row (§16/§18)
- [x] **VALID-05**: Tier#4/#5/#6 ship as registered validators — `spec_plan_coverage` (pre-build analyze), `task_done_when` (per-task acceptance), `design_quality` (tokens/placeholder/a11y, warnings-first) (Q38)
- [x] **AGENTRT-01**: `AgentRuntimeAdapter` wraps `create_deep_agent`; `langchain_deepagents` is the mandated adapter; future `claude_code_cli`/`custom_runner` slot in without kernel edits (§6/§30 / INV-13)
- [x] **AGENTRT-02**: `create_deep_agent` is called only inside the `langchain_deepagents` adapter (F5 deletion gate)
- [x] **AGENTRT-03**: `PromptAssemblyPolicy` promotes the hardcoded block order (`factory.py:174-255`: injects→guardrails→skills→hooks→constitution→body) to a declared, registry-resolved policy (F1 / §6/§30)
- [x] **AGENTRT-04**: `tool_provider` registry replaces the closed `_build_runner_tools` switch (`factory.py:384-446`) (F2)
- [x] **AGENTRT-05**: `skill_provider` / `hook_provider` replace inline skills/hooks injection (`factory.py:220-245`); behavioral hook becomes a non-executable provider sub-type (F3)
- [x] **AGENTRT-06**: Constitution injection made sync-safe / pre-warmed so a Postgres-stored Constitution is injected in production; constitution-injected-in-prod test passes (R12 / F4)

### Local Workspace Runtime & Repo Workflows — No Exec (Phase 4A)

- [x] **RUNTIME-01**: `RuntimeEnvironment` port (read/write/search/exec_command/clone_repo/create_branch/git_diff/teardown) + `LocalSandboxRuntime` impl over the per-run disk dir (§6/§14) — done 09-01
- [x] **RUNTIME-02**: One `Workspace` abstraction (fs + optional git + optional exec + `ExecutionPolicy`); prototype's `RunSandbox` becomes a `has_git=False, exec=off` Workspace — no engine fork repo-vs-artifact (R3/§14)
- [x] **RUNTIME-03**: `repositories` + `workspaces` rows persisted (§18)
- [x] **REPO-01**: `RepoInventory` (`kind=repo_inventory`) — file tree, language stats, dependency graph, ignore rules (`.gitignore` + `.flowinignore`), binary-file skip, size caps, optional summaries (§15)
- [x] **REPO-02**: `RepoIndex` (optional, large repos) behind a port; default grep/glob for small repos; threshold = N6 (§15 — N6/N10 SETTLED: shipped at deliverable parity in Phase 9 [4A], 09-03/09-04; decision recorded, no open question)
- [x] **REPO-03**: `ContextPack` (`kind=context_pack`) — targeted per-task subset via a `context_selector` capability, lineage-tracked; surfaced via the `repo` context provider (§15)
- [x] **REPO-04**: `repo_diff` `DeliverableResolver` produces app-builder-style file tree + per-file diff (Q-N7 — N5/N7 SETTLED: shipped at deliverable parity in Phase 9 [4A], 09-03/09-04; decision recorded, no open question)
- [x] **REPO-05**: A sample brownfield workflow runs end-to-end locally without execution (clone → branch → inventory → agents read/edit/search → diff surface); prototype unaffected (Phase 4A Accept)

### Safe Local Exec — Gated on N3 (Phase 4B)

- [x] **EXEC-01**: A constrained `exec` profile runs only behind the `security` gate + `ExecutionPolicy` — command allow/deny, network default-deny, resource caps (cpu_seconds/mem_mb), ephemeral creds (§8/§14 / N3 ⚠️ — own threat model first)
- [x] **EXEC-02**: compile/test/lint validators land; a sample compile/test validator passes; egress denied by default (Phase 4B Accept)

### Engine-Owned Fan-Out & Merge (Phase 5)

- [x] **FANOUT-01**: `spawn_subagents(tasks=[{agent,input}], mode=…)` tool bound only to steps granted `tools.spawn_subagents`; it emits a structured request — the kernel fulfils it (INV-7 / §6/§12) ✅ 11-01
- [x] **FANOUT-02**: Kernel `run_fanout(requests, ctx)` funnels both declarative (`step.fanout`) and runtime (tool) entry points (§12) ✅ 11-01
- [x] **FANOUT-03**: Worker selection — `agent="self"` (N copies) or a named worker from `allowed_workers` + registry (Q14) ✅ 11-01
- [x] **FANOUT-04**: Mode parallel (capped `asyncio.gather`) or sequential; engine enforces `max_concurrency` (Q15) ✅ 11-01
- [x] **FANOUT-05**: `IsolationProvider.allocate(scope)` → shared_read | sub_sandbox | worktree; writes default isolated (Q20/Q34 — N2 SETTLED: shipped in Phase 11 [5]; writes-default-isolated decision recorded, no open question)
- [x] **FANOUT-06**: Results return both files/artifacts and a structured summary (Q16)
- [x] **FANOUT-07**: `MergeStrategy` integrates fragments (copy_disjoint/git_3way/json/html_fragment) (§13)
- [x] **FANOUT-08**: Merge-conflict flow — write a `merge_conflict` artifact + emit event; resolve per `on_conflict` policy (human_gate default | merge_agent (bounded) | partial | abort) (§13 / A6)
- [x] **FANOUT-09**: `BudgetManager` reserves-before-spawn and enforces total subagents, concurrency, tokens, cost, wall-clock, recursion, fan-out depth (`ctx.depth`); `BudgetExceeded` aborts gracefully with partial results (Q17/Q18/Q44)
- [x] **FANOUT-10**: Each child → a `subagent_runs` row; events `subagent_spawned`/`subagent_result`/`merge_*` (§12/§18) ✅ 11-01 (subagent_runs row + subagent_spawned/subagent_result; merge_* lands 11-03)
- [x] **FANOUT-11**: Fan-out cancellation propagates to children (§21)

### Wave Scheduler & Durable Resume (Phase 6)

- [x] **WAVE-01**: `wave_scheduler` strategy topo-sorts by `depends_on` + `conflict_keys` into waves, runs each wave via fan-out; deterministic builder, CP-SAT seam left (Q31/Q32)
- [x] **WAVE-02**: `wave_runs` persistence; a multi-file workflow runs disjoint tasks in parallel waves; prototype stays sequential (Q33 / Phase 6 Accept)
- [x] **WAVE-03**: Resume mid-wave via `subagent_runs`/`wave_runs` records after a restart (§21 / N8 — confirm)

### Cancellation, Retry & Resume (cross-cutting; basic in Phase 0, hardened 5–6)

- [x] **RESUME-01**: Cooperative `cancel_event` checked per-chunk and at step/gate/fanout/wave boundaries; on cancel → mark `cancelled`, preserve partial artifacts, `teardown()` isolated workspaces, emit `pipeline_cancelled` (§21)
- [x] **RESUME-02**: Idempotent per-step retry `retry: {max, on}` for transient errors, keyed by `(run_id, step_id, input content_hash)`; reuses the existing artifact on hash match — distinct from the validator fix-loop (§21)
- [x] **RESUME-03**: Reconnect = durable replay from `run_events` via `after=<last_seq>`, idempotent by `event_id` (§21/§22)
- [x] **RESUME-04**: Server restart = `restore_non_terminal_runs` extended to step granularity; `waiting_for_user` gates resume on user action; in-flight steps resume from checkpoint or re-run idempotently (§21)

### Agent Runtime, Skills, Hooks, MCP & Integrations (§30; lands across Phases 1B/3/4+)

- [x] **HOOK-01**: `HookHandler` executable lifecycle/tool-call hooks bound to events (before/after run·step·tool_call·write, post_task, pre/post_commit, on_validation, before/after_merge, or `*`); outcome continue|warn|block; blocking hooks halt the offending action (N12 / §30)
- [x] **HOOK-02**: Canonical hooks — `secret_scan` (before_write/pre_commit, blocking), `otel_tracing`/logging (`*`, non-blocking → observability), pre/post_commit, post_task (§30/§23)
- [x] **HOOK-03**: Hooks are permissioned (a command-running hook needs `exec`, a git hook needs `git`, a scanner needs `read_files`); engineer-registered, users attach allow-listed only (INV-9/§30)
- [x] **HOOK-04**: Every hook firing → a `hook_runs` row for replay/debug; legacy prompt-only hook survives as a `kind: behavioral` non-executable sub-type (§18/§30)
- [x] **MCP-01**: `McpClientAdapter` (e.g. `langchain-mcp-adapters` `MultiServerMCPClient`) connects to external MCP servers (stdio/SSE/HTTP), lists tools/resources/prompts, binds allowed ones into the agent tool set (N13 / §30)
- [x] **MCP-02**: Allow-listed famous-server catalog (GitHub, GitLab, Jira/Atlassian, Confluence, Slack, Notion, Linear, Sentry, Figma, Filesystem, Postgres, Google Drive, web-search, Playwright, …), each with transport + exposed tools + scoped per-owner creds + `user_allowed` (§30)
- [x] **MCP-03**: `McpCapabilityRegistry` — compiler validates `tools.mcp` only names tools from servers the step + owner may reach; unknown `server.tool` → compile error (§7/§30)
- [x] **MCP-04**: Powerful servers (Filesystem/Postgres/write/network) sit behind the `security` gate + scoped creds + `secrets` permission (R13/§30)
- [x] **INTEG-01**: `integration_provider` capabilities (GitHub/GitLab/Jira/Slack/Confluence/Figma/OpenDesign) make repo/GitHub reachable from the unified `create_runner` path, not only the handoff pipeline (§30)
- [x] **INTEG-02**: `integrations` tool-permission scopes (e.g. `gitlab_read`, `jira_read`) default none; scoped per-owner creds (§8/§30/R13)
- [x] **SKILL-01**: `skill_provider` capabilities (ui · disk · template · repo) with a provider interface + versioning replace the flattened skill content list (§30)
- [x] **CAPRUN-01**: `run_capabilities` persistence records the active runtime + resolved skill/hook/integration/MCP names + versions + `model_overrides` per run for replay/debug (§18/§30)

### Dynamic API / Frontend Contract (parallel track, §22)

- [x] **API-01**: `GET /api/workflows` → list + metadata; `GET /api/workflows/{id}` → full step configs, gates, validators, deliverable, declared capabilities (§22)
- [x] **API-02**: `GET /api/capabilities` → registry palette (kind, name, `user_allowed`, config schema) incl. runtimes, skills, hooks, MCP servers, integrations, model catalog — with required auth + permission scopes (§22/§7/§30)
- [x] **API-03**: Run stream (WS/ndjson) emits existing events + new (`subagent_*`, `wave_*`, `validator_result`, `validation_warning`, `merge_*`, `budget_warning`, `gate_*`); existing-workflow contract stays at semantic parity (Q43/INV-3)
- [x] **API-04**: `GET /api/runs/{id}/artifacts` → typed artifact tree (lineage); `GET /api/runs/{id}/diff` → repo diff (§22)
- [x] **API-05**: `GET /api/runs/{id}/events?after=<seq>` → durable event replay (monotonic seq + event_id) for reconnect/resume (§22/§21)
- [x] **API-06**: Dynamic composer + capability palette + per-agent model picker; validator/issue panel; subagent + wave tree; artifact/diff viewer (reuse app-builder `FilesTab`/`AppBuilderPreview`) — additive panels (§22)
  - _Migration-ledger note (ISS-014, Phase 18 / deletion-as-superseded):_ the **capability-palette composer** half of API-06 (`WorkflowComposer.tsx` + `CapabilityPalette.tsx`) was orphaned dead UI (mounted by no route; INV-3/12 dual-impl) and is **DELETED-as-superseded** by the live `AgentsPopup` agent-composer (the "Compose a custom workflow" → Workflow-configuration modal, which is the real shipped composer). Deletion lands in plan **18-04**; rationale recorded here in 18-05. The per-agent **model picker** is relocated into the live `AgentsPopup` (locked-preferred — threads `model_overrides` for MODEL-03 end-to-end); if relocation proves too invasive it is carried to v2 (final disposition recorded in the 18-04 SUMMARY). **RETAINED:** the `GET /api/capabilities` endpoint + `test_capabilities_api.py` (API-02 registry-reflection contract + model-catalog source) — only the orphaned palette-panel UI is removed, the API contract and the agent-composer stand.

### Capability Surfacing & User Empowerment (Phase 22)

- [x] **SURF-01**: One capability palette/inspector reads the live `GET /api/capabilities` registry and renders EVERY capability kind grouped by kind, each showing name / description / `user_allowed` (trust) flag / security-gated flag / config schema — no hardcoded capability-name list in the FE (SC-001); embedded in `AgentsPopup` (Phase 22 / D-01)
- [x] **SURF-02**: `/api/capabilities` extended additively so every registered capability supplies `description` + a security-gated flag + a populated per-capability `config_schema` (the `{}` stub filled); auth + permission scopes preserved (API-02 intact) (Phase 22 / D-08)
- [x] **SURF-03**: For each launchable workflow the composer shows which capabilities each step declares, sourced from the compiled plan (`GET /api/workflows/{id}` / compiled projection), not a hardcoded description (Phase 22)
- [x] **EMP-01**: The live composer lets a user opt step(s) into user-allowed capabilities — at minimum a validator + a human/validation gate + a non-default model + retry — and the selection reaches the run path (saved-workflow payload → compiler/engine) and demonstrably takes effect at execution (Phase 22 / D-05)
- [x] **EMP-02**: Trust/tier gating enforced in UI AND server: `user_allowed=False` capabilities render visible-but-locked, never user-composable; a smuggled privileged grant is server-rejected by compiling with `trust="user"` (`_check_trust` / CAP-03), re-validated at SAVE and at LAUNCH (Phase 22 / D-04/D-12)
- [x] **EMP-03**: Saved workflows persist the richer per-step capability selections additively (reused `manifest_json` column), owner-scoped (IDOR→404), re-validated with `trust="user"` at launch (Phase 22 / D-11)
- [x] **EMP-04**: Selecting a capability that requires a coupled gate auto-attaches the required gate in the composer; the compiler's coupling checks stay the server-side backstop (Phase 22 / D-07)
- [x] **WIRE-01**: The compiler materializes top-level `model:` → `CompiledWorkflow.model` and per-step `model:` → `Step.model` so `ModelResolver` honors a manifest-declared model; INV-3 goldens byte-identical (Phase 22 / D-14)
- [x] **WIRE-02**: The compiler materializes per-step `retry:` → `Step.retry` so a manifest can activate the transient-retry wrapper (RESUME-02 reachable from a manifest) (Phase 22 / D-15)
- [x] **WIRE-03**: Per-step `injects:` is consumed (materialized into `Step.injects` + merged at the factory seam) or fails loud; a parametrized test asserts no `_ALLOWED_STEP_KEYS` entry is accepted-but-dropped (INV-5 preserved) (Phase 22 / D-16/D-17)
- [x] **UXFIX-01**: The catalog shows the friendly authored `display_name` (not the title-cased raw id); the P20 BE coalesce fix stays intact (Phase 22 / D-18)
- [x] **UXFIX-02**: `deliverable_mimetype`/`deliverable_filename` persist on the `WorkflowRun` row (additive columns, owner_id+workspace_id scope) and drive history-reopen so a custom binary deliverable re-renders faithfully (Phase 22 / D-19)
- [x] **UXFIX-03**: The data-driven catalog is the home landing so "no hardcoded name list" holds on the default view; `CreationHub.WORKFLOWS` no longer drives the default landing (Phase 22 / D-20)
- [x] **UXFIX-04**: The generic mimetype-dispatched deliverable renderer is the PRIMARY dispatch path; the 4 first-party types become routed entries rendering identically (no visual regression) (Phase 22 / D-21)
- [x] **DECIDE-01**: (N9) Artifact retention = keep-by-default (run artifacts retained indefinitely); `run_ttl`/`days:N` opt-in overrides; ART-04 updated; the 3 stale open-question labels (REPO-02/REPO-04/FANOUT-05) reconciled — WAVE-03 (N8) left out of scope (Phase 22 / D-22)
- [x] **DECIDE-02**: (N11) Premium-model policy = open to all tiers (no per-tier premium gating); global default stays Haiku with an ordered fallback chain; MODEL-05 updated; the model-picker tier filter removed (Phase 22 / D-23)
- [x] **LIVE-01**: One consolidated live-Bedrock confirmation pass on the AWS `default` profile (acct 473293451041, `claude-haiku-4-5`) records per-item evidence for the 8 standing deferrals (or an explicit disposition); phase completion gates on offline evidence (deferred to milestone-end, Phase 22 / D-24)

### Budgets & Observability (cross-cutting, §23)

- [x] **OBS-01**: `BudgetManager` enforces per-run AND per-workspace ceilings (tokens, €, subagents, depth, concurrency, wall-clock); reserve-before-spawn; graceful abort; snapshot persisted on the run (§23/§18)
- [x] **OBS-02**: Logging/tracing hooks bound to `*` emit OpenTelemetry-style spans/logs per lifecycle event → native observability; each firing lands in `hook_runs` (§23/§30)

### Anti-Duplication & Deletion Ledger (cross-cutting, INV-12/§31)

- [x] **DEL-01**: Every legacy element follows wrap → rewire call-sites → delete, completed within the phase that supersedes it; one implementation per behavior (INV-12)
- [x] **DEL-02**: Each phase ships a banned-pattern test (grep → 0 for deleted symbols/branches), a dead-code scan (ruff/vulture), and the import-linter rule as exit gates; Definition of Done = behavior moved + call-sites rewired + legacy deleted + gates green + snapshots green (§31) — _ledger ratchet (01-03) + banned-pattern test + vulture dead-code scan + import-linter contract (01-04) all shipped and green_
- [x] **DEL-03**: Banned-pattern tests are ratchets — a deleted symbol's reintroduction fails CI (§31)
- [x] **DEL-04**: The `specs/003-…/migration-ledger.md` mirrors the §31 ledger operationally (L1–L16, F1–F5, D1) with status + deleting commit SHA, asserted by CI (§31)

## Milestone v2.0 Requirements — Universal Run Chat & VelocityAI UI Convergence

Registered 2026-07-07 via `/gsd-import`. Plan of record: `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` (locked decisions D-01..D-12, open decision records ND-1..ND-9). Phases 28–38 (23–27 reserved for the post-milestone standalone efforts in IMPLEMENTATION-REGISTER). All requirements inherit the standing invariants: SC-001/INV-1 (no kernel workflow-name branches), INV-3 (5 goldens byte/event-identical), INV-5, INV-12, INV-13, Q3 (additive migrations; owner_id+workspace_id).

### Chat Channel (Phases 28–29)

- [x] **CHAT-01**: Chat turns enter via `POST /api/runs/{id}/messages` (idempotent by client `message_id`) and persist as `run_events` rows (`chat_message`/`chat_reply`) through the single stamping boundary — replay, reopen, and owner-scoping inherited; all server→client delivery rides the per-run SSE stream (D-01/D-13); zero new tables
- [x] **CHAT-07**: Transport cutover (D-13) — per-run SSE stream (`Last-Event-ID`=`seq`, `stream_attached` handshake) + REST command endpoints replace `/ws/chat` IN FULL within Phase 29: wire-parity characterization green (SSE ≡ recorded WS frame sequences for the 5 golden pipelines), every inbound-handler test suite ported 1:1 (IDOR/ownership, terminal fences, redo/update_specs, questionnaire, cancel, revision, image caps), `user_message` ported to a POST+stream shim, app-level FE connection provider + server-derived reattach + gate re-arm on restart (D-14), deploy-ordered rollout, then the WS run-handlers + transport flag DELETED with grep ratchets + a ledger row (INV-12); `websocket_handoff.py` + inbound MCP untouched
- [x] **CHAT-02**: Mechanical intent router delivers turns by run state — clarify answer / gate action (approve·reject·redo+instructions·**update_specs** — routing to the shipped KAN-101 spec-revision loop) / steering note / revision — with zero model calls for routable turns; gates treated as event-driven (KAN-94) and fenced on terminal runs (`pipeline_not_running`, KAN-100)
- [x] **CHAT-03**: Steering seam — consume-once `ectx.steering_notes` rendered as a `=== USER GUIDANCE ===` block at the next agent dispatch (redo idiom); sticky (uploads) vs one-shot (directives) semantics
- [x] **CHAT-04**: Narrator `chat_reply` result cards for clarify/gate/pipeline/deliverable milestones, deep-linking into the run tabs
- [x] **CHAT-05**: Family-anchored transcript — turns persist on the active run; FE stitches across parent/child runs via `GET /api/runs/{id}/family`
- [x] **CHAT-06**: Golden neutrality — new event types in `_DOCUMENTED_EVENT_TYPES`, volatile keys in `_VOLATILE_STRIP_KEYS`, characterization proof that chat never fires on golden paths

### Uploads & Multimodal (Phase 30)

- [x] **UPLD-01**: `POST /api/runs/{id}/files` (multipart, two-layer owner check → 404) persisting bytes under the run's `RunSandbox` — **DONE 30-01** (owner-scoped, capped, traversal-proof; docs land under reserved `.uploads/` + extract-text sidecar + manifest; deliverable-excluded, INV-3 dormant)
- [~] **UPLD-02**: `run_images` provider live end-to-end (WS ingress → engine → `HumanMessage` content blocks) incl. per-turn images — **run-entry path LANDED 2026-07-07 pre-milestone** (IMAGE-INPUT-PLAN waves `edw`/`frv`/`gvq`, offline-proven for `prototype`; validation caps + vision guard included); **per-turn carrier LANDED 30-03 (2026-07-08)** — images on the Phase-29 `POST /api/runs/{id}/messages` path → `apply_turn_images` → `ectx.pending_turn_images` → engine `_drain_turn_images` → `run_images` → `_compose_input_blocks` blocks; cap-validated by the shared `_validate_images`; ND-10 payload-transient (retained:false, no bytes), INV-3 dormant, offline-proven (39 green + 15 goldens byte-identical); **remaining: live Bedrock proof (Phase 34/LIVE-02) + the DEF-30-03-1 live in-process ectx delivery handle (== DEF-29-09-1)**
- [x] **UPLD-03**: Documents extract-to-sticky-context AND land in the sandbox for agent `read_file`; `context_provider:uploaded_files` registered; uploaded context present in every subsequent `agent_input`
- [~] **UPLD-04**: Launch-time attachments (incl. images, client-resized) ride `run_pipeline` — **image attachments LANDED 2026-07-07 pre-milestone** (FE picker + base64 + preview chips on 3 surfaces → `run_pipeline` `images`); remaining: client-side resize, paste/drag-drop (Phase 31 UI)

### Chat Lane UI (Phase 31)

- [x] **CHATUI-01**: Revived in-repo chat kit renders the family transcript with streaming markdown, `aria-live`/`role="log"`, and the open-design borrow-list mechanisms (Apache-2.0 attribution)
- [x] **CHATUI-02**: Gate/clarify quick-actions available in-lane, mirroring Steps (single backend channel either way)
- [x] **CHATUI-03**: Attachment UI (picker/paste/drag-drop/preview/resize) + token-usage widget from P26 telemetry

### Run-Screen Redesign (Phase 32)

- [x] **RUNUI-01**: Token layer (black/beige/one-blue `#3C2CDA`, Manrope/Heebo) + shared primitives; run screens consume tokens, no new hardcoded palette
- [x] **RUNUI-02**: Run screen = chat lane (left) + Preview/Steps/Files/Audit (right); typed-renderer switcher as manual override over existing dispatch
- [x] **RUNUI-03**: Steps 3-level drill-down from real events (overview spine → agent detail + Context-received rail → task detail, dual task-loop/fanout source); gate/clarify inline
- [x] **RUNUI-04**: Audit tab reads new `gate_events`/`validation_results`/`exec_runs` endpoints; counters/filters/CSV-JSON export; status palette only for governance
- [x] **RUNUI-05**: E2E hardened — brittle color-class assertions fixed, `data-testid`s on chat surfaces, mockWs chat driver in use

### Run-Screen Mock Fidelity (Phase 39)

- [x] **RUNUI-06**: Every run-screen surface (left lane, run header, Preview/Steps/Files/Audit + all sub-navigation) matches its VelocityAI-New-UI mock across settled/live/failed to the intended-divergence register — proven by a side-by-side screenshot-diff gallery + human sign-off, not a prose claim (Phase 39 SC-1)
- [x] **RUNUI-07**: Net-new as-is affordances land — Share (client-only link), the Version ▾ menu (from `runFamily`), the "Renders as" deliverable-type switch, and the fuller Audit categories (secret-scan / performance / behavioral) (Phase 39 SC-2)
- [x] **RUNUI-08**: Data stays real & live (SC-001) — no cloned mock values; the deliverable renderers are reused not rebuilt; intended divergences (VelocityAI / My Workflows / nav underline) preserved (Phase 39 SC-3)
- [ ] **RUNUI-09**: The mocked e2e suite is green again against feat/ui-2 (home-grid / launch-flow / run-family fixes) and the fidelity screenshot harness + side-by-side gallery run under `frontend/e2e` (Phase 39 SC-4)

### Shell Mock Fidelity (Phase 40 [B6])

Phase 40 [B6] is the shell-convergence completion — it does NOT mint new requirement
ids; it OWNS and closes the existing **SHELL-01..04** (defined under "Shell
Convergence (Phases 35–38)" below) through the same anti-drift, mock-fidelity method
Phase 39 used for the run screen. The four Phase-40 success criteria map onto them as
a fidelity lens (Wave 1 = 40-01 harness; Wave 2 = 40-02..07 surfaces; the Configure/
Composer rebuild defers to Phase 41):

- **SHELL-01 (Phase 40 SC-1 — fidelity):** Each in-scope shell surface + every sub-view/sub-tab/state matches its `Hexaware Workspace v2` mock to the intended-divergence register (ND-A..D carried + ND-W..Z), proven by the side-by-side shell gallery (`gallery-shell.html`) + a HUMAN sign-off — not a prose claim.
- **SHELL-02 (Phase 40 SC-2 — as-is affordances):** The net-new as-is affordances land on live data — Home 3×2 deliverable card grid + "Jump back in" recents, Library card grids, Settings richer profile form, History filter chips / Sort tabs / date groups, the Catalogue grid.
- **SHELL-03 (Phase 40 SC-3 — live data / SC-001):** Data stays real & live (SC-001/ND-D) — no cloned mock values, no fabricated fields (ND-Y); existing components reused, chrome/layout rebuilt; intended divergences (ND-A brand · ND-B "My Workflows" · ND-C nav underline · ND-W "Run History" · ND-X no Voice · ND-Y no fabricated profile fields · ND-Z Library drawer → Phase 41) preserved.
- **SHELL-04 (Phase 40 SC-4 — oracle + green specs):** The blocked Catalogue is stubbed (`/api/user-workflows`) + the empty surfaces seeded, the shell fidelity oracle is formalized (repo-relative, `SHELL_CAPTURE`-gated, per-surface `--surface` gallery regeneration), and each touched surface's mocked-e2e spec is re-anchored green.

### Concierge & Compaction (Phase 33)

- [ ] **CONC-01**: `chat:concierge` registered capability — one implementation, per-run instances, read + proposal-only tools, confirm chips, execution only through existing channels (INV-13 via `deep_agent_runner`)
- [ ] **CONC-02**: `compaction:chat_history` + `context_provider:conversation` bound composed history within budget (recent verbatim, older summarized)
- [ ] **CONC-03**: Post-run chat turns produce revision runs stitched into the family transcript

### Live Confirmation (Phase 34)

- [ ] **LIVE-02**: Live-Bedrock pass — multi-turn chat with images, mid-run steering observed in next dispatch, Concierge Q&A, `cache_read>0` with multi-turn cache-point placement (closes the P26 deferral), Playwright live suite

### Shell Convergence (Phases 35–38, closed to mock fidelity in Phase 40 [B6])

- [ ] **SHELL-01**: Shell chrome (dark top bar, nav pill Home·Library·My Workflows, profile menu, notifications) + reskin-only pages (Settings, pickers, Library) on the token layer
- [x] **SHELL-02**: Fused Home (launcher+grid+recents); History grouping/sort/delete; **My Workflows** rename + kebab actions; `WorkflowCatalog`→`HomeLaunchGrid`; "Catalogue" reserved for future marketplace (D-11)
- [x] **SHELL-03**: Run detail/reopen page off a run-summary endpoint aggregating existing data (agents, KPIs, failure banner, version timeline)
- [ ] **SHELL-04**: Generic Configure surface (Describe/Templates/DS/Gates/Settings for every deliverable) + Agent drawer + Workflow dialog with `user_allowed` gating (ND-1/ND-7/ND-8 gated) — **closed-by-Phase-41 [B7]**: the mock-fidelity rebuild of the single Configure screen (CFGUI-01/02) + the Library agent-detail drawer (CMPUI-05) close this requirement's Configure-surface + Agent-drawer clauses.
- [x] **SHELL-05**: Date-scoped analytics aggregations + chart components + per-deliverable estimates + notifications feed

### Configure Unification + Composer Rebuild (Phase 41 [B7])

The two structural REBUILDS Phase 40 deferred — the unified **Configure** screen
and the full-page **Composer** (Simple + Canvas) — to mock/proposal fidelity, plus
the harness that unblocks their fidelity gates. Closes SHELL-04. Intended
divergences ND-AE..AJ (see `41-UI-SPEC.md` / `assemble-phase41-gallery.mjs`).

- [ ] **CFGUI-01**: The unified one-screen Configure surface — Step-1 brief + four accordions (Templates · Design System · Review Gates · Workflow Settings) + overlays — matches the mock (screenshot-diff + HUMAN sign-off), closed to the ND-AE..AI register.
- [ ] **CFGUI-02**: ConfigureScreen revived as the SINGLE Configure screen with a real `onLaunch` through the existing `onStartPipeline` seam + in-app nav; the overlapping Configure code in IdeaInputPage (brief-launch) + LaunchWizard + WizardStepper is DELETED — no dual Configure implementation survives (INV-3).
- [ ] **CMPUI-01**: The Composer is a full-page surface with entry from Home + edit-from-My-Workflows and a Simple⇄Canvas toggle, bound to the AgentsPopup shared data model; the modal shell is replaced (INV-3).
- [ ] **CMPUI-02**: The Simple view matches `Hexaware Composer.dc.html` — identity card + reorderable agent rows + model picker + override chips + custom prompt + capability palette + skills & hooks + summary rail (screenshot-diff + HUMAN sign-off).
- [ ] **CMPUI-03**: The hand-rolled node-graph Canvas view matches the APPROVED proposal `composer-canvas-proposal.html` — design-match HUMAN sign-off (ND-AJ); no graph library (D-CMP-CANVAS).
- [x] **CMPUI-04**: Run-once launches through the existing `onStartPipeline` seam (functional test) + Save-to-catalogue reuses `createUserWorkflow`; no engine/backend/manifest change, no fabricated cost (ND-AG). *(41-06, commit 19f9fdf7 — composer-run.spec.ts mocked 2/2 green)*
- [ ] **CMPUI-05**: The Library agent-detail right-drawer rebuilt from AgentCapabilitiesModal — closes SHELL-04's Agent-drawer clause (ND-Z).
- [ ] **HARN-01**: The Configure template/DS/ppt APIs stubbed + seeded (opt-in) + the Phase-41 fidelity oracle formalized (repo-relative, per-surface `--surface`-regenerable, carrying ND-AE..AJ + a Canvas design-match target).

## Milestone v3.0 Requirements — Top-Tier Resume & Durable Execution

> POR: `.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` (all 7 design decisions LOCKED §8; LOCK-E/ND-4 supersede record §8.1). Continues the v1.0 RESUME-01..04 family. Substrate = `artifact_refs` (NOT git — Q1); cursor computed by the KERNEL, never an agent; every phase golden-safe (INV-3), additive-only (Q3), kernel name-free (INV-1/SC-001), single-dispatch-path (INV-12), deepagents-only (INV-13).

### Resume Correctness (Phase 45 [R0])

- [ ] **RESUME-05**: A run interrupted mid-build resumes by re-entering the build step and completing ONLY the unfinished tasks — a partially-completed build is never classified "complete" and silently skipped (fixes the `engine.py:6002` first-task-persist bug). Completeness is strategy-conditional: task-granular steps (task_loop/wave) count tasks-in-current-list vs completed per-task artifacts; `single_shot` steps keep produced-ref/`step_completed` semantics byte-unchanged; `step_reused` (input_hash) behavior untouched.

### Per-Task Substrate, Cursor & Live Layer (Phase 46 [R1])

- [ ] **RESUME-06**: `subagent_runs` carries per-child task identity — additive nullable `task_id` + `worker_index` columns (the pre-authorized CR-03-followup; free-String, named FK, reversible single-head after 0025), written at spawn (before the crash window — the 0023 `selections_json` precedent).
- [ ] **RESUME-07**: GENERIC per-task capture (Q7): every file a task wrote is durably captured per task — not just the declared deliverable file — superseding `persist_task_html`'s single-file scope so any future multi-file task workflow resumes from day one.
- [ ] **RESUME-08**: Durable→disk re-materialization: resume walks the latest durable `artifact_refs` (by `location`, `max(version)`, filtered to completed task keys) and rebuilds the fresh `RunSandbox` — including MERGE RE-ENTRY for an in-flight wave (fragments re-materialized + the per-wave merge re-run before remaining workers dispatch). Worktree/sandbox state reconstructs from `artifact_refs`, never from git.
- [ ] **RESUME-09**: Per-worker wave skip + per-task sequential skip: completed workers/tasks are never re-invoked on resume (identity-based kernel cursor — NOT the deleted-for-cause prefix-by-count skip); agents receive the completed work as injected context but never decide the skip set.
- [ ] **RESUME-10**: A resumed run is a first-class LIVE run: both resume paths (auto `restore_non_terminal_runs` branch (b) AND the Phase-50 user endpoint) thread `register_live_ectx` (+ unregister in `finally`) and `milestone_sink` — mid-run steering, per-turn images, Concierge context, and narrator milestone cards all work on resumed runs; milestone-card `seq` drawn from the engine counter (DEF-43-03-1, 0024 constraint).
- [ ] **RESUME-11**: Steering notes durably logged as `chat_message` rows but not yet drained at crash time are re-queued onto `ectx.steering_notes` at resume (no silent loss of accepted guidance).

### Uploads Durability (Phase 47 [R2])

- [ ] **RESUME-12**: Uploaded documents' extracted text + manifest are persisted durably at ingest (additive, owner_id+workspace_id-scoped; existing per-file/count/aggregate caps unchanged) — closing the `.uploads/` disk-only hole (Q6).
- [ ] **RESUME-13**: The `uploaded_files` context provider falls back to the durable mirror when the sandbox `.uploads/` copy is missing, so a resumed run on a fresh sandbox keeps FULL document context in every subsequent `agent_input`. Images stay payload-transient (ND-10 locked — explicitly untouched).

### Task Identity & Mutable Task List (Phase 48 [R3])

- [ ] **RESUME-14**: Content-addressed task identity — `task_key = sha256(upstream_context_hash · normalized_task_content · occurrence_ordinal)`: position-independent (reorder/insert-safe), duplicate-text-safe (ordinal), and upstream-aware (a spec edit rotates the keys so tasks built against a stale spec re-run); hash discipline inherited from `input_hash` (sorted, no timestamp/uuid — cross-restart stable).
- [ ] **RESUME-15**: The task list is user-editable as a VERSIONED `task_list` artifact (Q3): add/edit/delete mints a new version via the extended gate-Edit mechanism (KAN-98 path; `edited_content` rides `POST /{id}/gate` only — WR-03); old versions kept with `derived_from` lineage, `max(version)` wins; NO new tasks table (respects the "no new step-status table" lock).
- [ ] **RESUME-16**: AUTOMATIC reconciliation (Q2) on resume or re-run-after-edit: completed+present → skip + re-materialize + inject as prior context; new/edited/rotated → run; deleted-but-completed → excluded from the assembled deliverable at read time (rows NEVER deleted — `artifact_refs` immutable); spec edits auto-invalidate affected tasks with no confirm prompt.

### Gate Survival (Phase 49 [R4])

- [ ] **RESUME-17**: Clarify AND review gates survive a backend restart: restart branch (a) flips fail→re-arm for compiled-manifest runs with durable state (WR-05 stateless/legacy path byte-untouched), rebuilt on the EXISTING seams (`derive_open_gate`/KAN-94 durable pendency + the D-14g `_dangling_review_gate` SSE re-emit — no parallel pending-arm store; `_gate_is_pending` gains a public accessor, closing the IN-02 debt); the review gate RE-ENTERS `_run_agent`'s loop AT its gate phase with the output reconstructed from `artifact_refs`, so ALL five gate actions (approve/reject/edit/redo/update_specs) work identically post-restart; the pre-existing red `test_restart_resume::test_waiting_for_user_run_is_rearmed_not_driven` flips GREEN (the KAN-88 restoration anchor).

### Reopen & Fix (Phase 50 [R5])

- [ ] **RESUME-18**: A user can resume a terminal-FAILED run via `POST /api/runs/{id}/resume`: two-layer owner check (`user_id`, 404 never 403), overlap-guarded (`pipeline_already_running` precedent) and replay-idempotent (the P33 M4 lesson); recovers workspace_id from durable rows (never fresh-minted — Pitfall 2), `selections_json` (0023), completed steps/tasks via the cursor, and disk via re-materialization; re-registers in `_PIPELINE_QUEUES` BEFORE FE attach (BUG-015 live-attach semantics) reusing the `run_engine.py` bridge — NO third hand-copied driver; status transition (failed→running or a `run_resuming` EVENT per INV-12 preference) makes FE `AUTO_STREAM_STATUSES` auto-attach; live-layer callbacks threaded (RESUME-10 mechanism). Authorized by the LOCK-E/ND-4 supersede record (POR §8.1).

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

Each v1 requirement maps to exactly one phase, **one row per requirement** (REQ-ID alone in the first cell — no grouped/comma rows). Phases are GSD integers 1–12, mapped 1:1 to plan §25 sub-phases (`[0A]…[6]`). Each v1 row carries the owning phase's verification verdict (every phase 1–12 has `NN-VERIFICATION.md` `status: passed`). v2 / Out-of-Scope items are listed for completeness with phase `v2 (deferred)` — intentionally unmapped this milestone.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SAFE-01 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06) |
| SAFE-02 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06) |
| SAFE-03 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06) |
| SAFE-04 | Phase 1 [0A] | Complete (P1 verified — passed; ledger ratchet 01-03) |
| SAFE-05 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06) |
| SAFE-06 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06) |
| SAFE-07 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06) |
| CTX-01 | Phase 2 [0B] | Complete (P2 verified — passed, 2026-06-07) |
| CTX-02 | Phase 2 [0B] | Complete (P2 verified — passed, 2026-06-07) |
| CTX-03 | Phase 2 [0B] | Complete (P2 verified — passed, 2026-06-07) |
| CTX-04 | Phase 2 [0B] | VOIDED/DEFERRED — `_handle_revision` is LIVE (the `run_revision` PPT-revision handler), not dead; deletion would break PPT revision (CTX-05). Deferred pending a product decision on retiring `run_revision`. See Phase 2 `02-02-SUMMARY.md`. |
| CTX-05 | Phase 2 [0B] | Complete (P2 verified — passed, 2026-06-07) |
| COMPACT-01 | Phase 3 [0C] | Complete (P3 verified — passed, 2026-06-07) |
| COMPACT-02 | Phase 3 [0C] | Complete (P3 verified — passed, 2026-06-07) |
| COMPACT-03 | Phase 3 [0C] | Complete (P3 verified — passed, 2026-06-07) |
| MAN-01 | Phase 4 [1A] | Complete (P4 verified — passed, 2026-06-07) |
| MAN-02 | Phase 4 [1A] | Complete (P4 verified — passed, 2026-06-07) |
| MAN-03 | Phase 4 [1A] | Complete (P4 verified — passed, 2026-06-07) |
| MAN-04 | Phase 4 [1A] | Complete (P4 verified — passed, 2026-06-07) |
| MAN-05 | Phase 4 [1A] | Complete (P4 verified — passed, 2026-06-07) |
| ART-01 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| ART-02 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| ART-03 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| ART-04 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| PERSIST-01 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| PERSIST-02 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| PERSIST-03 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| AUTHZ-01 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| AUTHZ-02 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| AUTHZ-03 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| AUTHZ-04 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| MODEL-01 | Phase 6 [1C] | Complete (P6 verified — passed, 2026-06-08) |
| MODEL-02 | Phase 6 [1C] | Complete (P6 verified — passed, 2026-06-08) |
| MODEL-03 | Phase 6 [1C] | Complete (P6 verified — passed, 2026-06-08; FE per-agent picker relocated into the live AgentsPopup in Phase 18 — ISS-014) |
| MODEL-04 | Phase 6 [1C] | Complete (P6 verified — passed, 2026-06-08) |
| MODEL-05 | Phase 6 [1C] | Complete (P6 verified — passed, 2026-06-08) |
| PARITY-01 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| PARITY-02 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| PARITY-03 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| PARITY-04 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| PARITY-05 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| PARITY-06 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| PARITY-07 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| PARITY-08 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| PARITY-09 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| CAP-01 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-01) |
| CAP-02 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-01) |
| CAP-03 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-01) |
| GATE-01 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-02) |
| GATE-02 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-02, validation-gate context wired in review remediation) |
| GATE-03 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-02) |
| TOOLPERM-01 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-03) |
| TOOLPERM-02 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-03) |
| TOOLPERM-03 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-03) |
| VALID-01 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-04) |
| VALID-02 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-04) |
| VALID-03 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; single-source `map_severity` in 08-01) |
| VALID-04 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-04) |
| VALID-05 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-04) |
| AGENTRT-01 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-03/08-05) |
| AGENTRT-02 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-03/08-05) |
| AGENTRT-03 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-03/08-05) |
| AGENTRT-04 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-03/08-05) |
| AGENTRT-05 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-03/08-05) |
| AGENTRT-06 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-06) |
| SKILL-01 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-05) |
| HOOK-01 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-07) |
| HOOK-02 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-07) |
| HOOK-03 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-07) |
| HOOK-04 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-07) |
| OBS-02 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-07) |
| API-02 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-08) |
| API-03 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-08) |
| API-06 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-08, human-verified). Capability-palette composer UI (`WorkflowComposer`/`CapabilityPalette`) DELETED-as-superseded by the live agent-composer (ISS-014, Phase 18 — deletion 18-04, reconciled 18-05); `/api/capabilities` + the API-02 contract RETAINED. |
| RUNTIME-01 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-01/09-02) |
| RUNTIME-02 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-01/09-02) |
| RUNTIME-03 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-01/09-02) |
| REPO-01 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-03/09-04) |
| REPO-02 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-03/09-04) |
| REPO-03 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-03/09-04) |
| REPO-04 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-03/09-04) |
| REPO-05 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-03/09-04) |
| MCP-01 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-05) |
| MCP-02 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-05) |
| MCP-03 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-05) |
| MCP-04 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-05) |
| INTEG-01 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10) |
| INTEG-02 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10) |
| EXEC-01 | Phase 10 [4B] | Complete (P10 verified — passed, 2026-06-10) |
| EXEC-02 | Phase 10 [4B] | Complete (P10 verified — passed, 2026-06-10) |
| FANOUT-01 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11; 11-01) |
| FANOUT-02 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11; 11-01) |
| FANOUT-03 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11; 11-01) |
| FANOUT-04 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11; 11-01) |
| FANOUT-05 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11) |
| FANOUT-06 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11) |
| FANOUT-07 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11) |
| FANOUT-08 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11) |
| FANOUT-09 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11) |
| FANOUT-10 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11; 11-01) |
| FANOUT-11 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11) |
| OBS-01 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11) |
| RESUME-01 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11) |
| WAVE-01 | Phase 12 [6] | Complete (P12 verified — passed, 2026-06-11) |
| WAVE-02 | Phase 12 [6] | Complete (P12 verified — passed, 2026-06-11) |
| WAVE-03 | Phase 12 [6] | Complete (P12 verified — passed, 2026-06-11) |
| RESUME-02 | Phase 12 [6] | Complete (P12 verified — passed, 2026-06-11) |
| RESUME-03 | Phase 12 [6] | Complete (P12 verified — passed, 2026-06-11) |
| RESUME-04 | Phase 12 [6] | Complete (P12 verified — passed, 2026-06-11) |
| CAPRUN-01 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| API-01 | Phase 4 [1A] | Complete (P4 verified — passed, 2026-06-07) |
| API-04 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| API-05 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| DEL-01 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06; 01-03) |
| DEL-02 | Phase 1 [0A] | Complete (P1 verified — passed; ledger ratchet 01-03 + dead-code scans/import-linter 01-04) |
| DEL-03 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06; 01-03) |
| DEL-04 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06; 01-03) |
| SURF-01 | Phase 22 | Planned (22-05) |
| SURF-02 | Phase 22 | Complete (22-02; tests + lint-imports + SC-001 green) |
| SURF-03 | Phase 22 | Planned (22-05) |
| EMP-01 | Phase 22 | Planned (22-04, 22-06) |
| EMP-02 | Phase 22 | Planned (22-04, 22-05) |
| EMP-03 | Phase 22 | Planned (22-04) |
| EMP-04 | Phase 22 | Planned (22-06) |
| WIRE-01 | Phase 22 | Planned (22-01) |
| WIRE-02 | Phase 22 | Planned (22-01) |
| WIRE-03 | Phase 22 | Planned (22-01) |
| UXFIX-01 | Phase 22 | Planned (22-07) |
| UXFIX-02 | Phase 22 | Planned (22-03) |
| UXFIX-03 | Phase 22 | Planned (22-07) |
| UXFIX-04 | Phase 22 | Planned (22-07) |
| DECIDE-01 | Phase 22 | Complete (22-08; ART-04 keep-by-default recorded; 3 stale open-question labels reconciled; N8 wave-resume left out of scope) |
| DECIDE-02 | Phase 22 | Planned (22-06, 22-08) |
| LIVE-01 | Phase 22 | Planned (22-09) |
| ECS-01 | v2 (deferred) | Deferred — v2, intentionally unmapped (remote runtime; separate spec §27) |
| ECS-02 | v2 (deferred) | Deferred — v2, intentionally unmapped (warm/dedicated containers §27) |
| SCHED-01 | v2 (deferred) | Deferred — v2, intentionally unmapped (CP-SAT; topo seam left Phase 12 / Q32) |
| MERGE-01 | v2 (deferred) | Deferred — v2, intentionally unmapped (single-file fragment merge; Q33) |
| GIT-01 | v2 (deferred) | Deferred — v2, intentionally unmapped (PR/commit push; diff-only until N4) |
| WF-DB-01 | v2 (deferred) | Deferred — v2, intentionally unmapped (DB-backed user workflows; file-backed only now, Q5) |

**Coverage:**

- v1 requirements: 117 total — all 117 present as individual rows above (one row per REQ-ID).
- Mapped to a phase: 117 / 117 ✓ (Phases 1–12; every phase `NN-VERIFICATION.md` `status: passed`).
- v1 delivered: 116 Complete + 1 VOIDED/DEFERRED (CTX-04 — `_handle_revision` is live; deletion deferred pending a `run_revision` retirement decision).
- v2 (deferred, intentionally unmapped, listed for completeness): ECS-01, ECS-02, SCHED-01, MERGE-01, GIT-01, WF-DB-01 (6).
- Traceability rows total: 123 (117 v1 + 6 v2) — every REQ-ID defined in the body has its own row.

**Per-phase counts:** P1=11 · P2=5 · P3=3 · P4=6 · P5=14 · P6=5 · P7=9 · P8=29 · P9=14 · P10=2 · P11=13 · P12=6 (= 117)

### Milestone v2.0 Traceability (phases 28–38, registered 2026-07-07)

| Requirement | Phase | Status |
|-------------|-------|--------|
| CHAT-01 | Phase 29 [A1] | Complete |
| CHAT-02 | Phase 29 [A1] | Complete |
| CHAT-03 | Phase 29 [A1] | Complete |
| CHAT-04 | Phase 29 [A1] | Complete |
| CHAT-05 | Phase 29 [A1] | Complete |
| CHAT-06 | Phase 28 [A0] | Complete |
| CHAT-07 | Phase 29 [A1] | Complete |
| UPLD-01 | Phase 30 [A2] | Complete (30-01) |
| UPLD-02 | Phase 30 [A2] | Carrier landed 30-03 (offline); live Bedrock proof deferred (Phase 34/LIVE-02) |
| UPLD-03 | Phase 30 [A2] | Complete |
| UPLD-04 | Phase 30 [A2] | Pending |
| CHATUI-01 | Phase 31 [A3] | Complete |
| CHATUI-02 | Phase 31 [A3] | Complete |
| CHATUI-03 | Phase 31 [A3] | Complete |
| RUNUI-01 | Phase 32 [A4] | Complete |
| RUNUI-02 | Phase 32 [A4] | Complete |
| RUNUI-03 | Phase 32 [A4] | Complete |
| RUNUI-04 | Phase 32 [A4] | Complete |
| RUNUI-05 | Phase 32 [A4] | Complete |
| CONC-01 | Phase 33 [A5] | Pending |
| CONC-02 | Phase 33 [A5] | Pending |
| CONC-03 | Phase 33 [A5] | Pending |
| LIVE-02 | Phase 34 [A6] | Pending |
| SHELL-01 | Phase 35 [B1] | Pending |
| SHELL-02 | Phase 36 [B2] | Complete |
| SHELL-03 | Phase 36 [B2] | Complete |
| SHELL-04 | Phase 37 [B3] → Phase 41 [B7] | Pending (closed-by-Phase-41) |
| SHELL-05 | Phase 38 [B4] | Complete |
| RUNUI-06 | Phase 39 [B5] | Complete |
| RUNUI-07 | Phase 39 [B5] | Complete |
| RUNUI-08 | Phase 39 [B5] | Complete |
| RUNUI-09 | Phase 39 [B5] | Pending |
| CFGUI-01 | Phase 41 [B7] | Pending |
| CFGUI-02 | Phase 41 [B7] | Pending |
| CMPUI-01 | Phase 41 [B7] | Pending |
| CMPUI-02 | Phase 41 [B7] | Pending |
| CMPUI-03 | Phase 41 [B7] | Pending |
| CMPUI-04 | Phase 41 [B7] | Complete (41-06) |
| CMPUI-05 | Phase 41 [B7] | Pending |
| HARN-01 | Phase 41 [B7] | Pending |

**v2.0 counts:** P28=1 · P29=6 · P30=4 · P31=3 · P32=5 · P33=3 · P34=1 · P35=1 · P36=2 · P37=1 · P38=1 · P39=4 · P41=8 (= 40)

### Milestone v3.0 Traceability (phases 45–50, registered 2026-07-18)

| Requirement | Phase | Status |
|-------------|-------|--------|
| RESUME-05 | Phase 45 [R0] | Pending |
| RESUME-06 | Phase 46 [R1] | Pending |
| RESUME-07 | Phase 46 [R1] | Pending |
| RESUME-08 | Phase 46 [R1] | Pending |
| RESUME-09 | Phase 46 [R1] | Pending |
| RESUME-10 | Phase 46 [R1] | Pending |
| RESUME-11 | Phase 46 [R1] | Pending |
| RESUME-12 | Phase 47 [R2] | Pending |
| RESUME-13 | Phase 47 [R2] | Pending |
| RESUME-14 | Phase 48 [R3] | Pending |
| RESUME-15 | Phase 48 [R3] | Pending |
| RESUME-16 | Phase 48 [R3] | Pending |
| RESUME-17 | Phase 49 [R4] | Pending |
| RESUME-18 | Phase 50 [R5] | Pending |

**v3.0 counts:** P45=1 · P46=6 · P47=2 · P48=3 · P49=1 · P50=1 (= 14; 100% mapped, each REQ → exactly one phase)

---
*Requirements defined: 2026-06-06*
*Last updated: 2026-07-18 — Milestone v3.0 requirement family registered (RESUME-05..18, 14 REQ-IDs → phases 45–50) from the POR `.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` (plan-ingestion, decisions pre-locked §8). Prior: 2026-07-07 — Milestone v2.0 requirement families registered (CHAT/UPLD/CHATUI/RUNUI/CONC/LIVE-02/SHELL, 27 REQ-IDs → phases 28–38) via /gsd-import of `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md`. Prior: 2026-06-14 — Traceability table reconciled to one-row-per-REQ; 113 body REQ-IDs that were missing from the table (grouped-row drift) added; statuses refreshed to the verified-complete state (ISS-012).*
