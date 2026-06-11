# Workflow Engine Decoupling & Universal Workflow Runtime

## What This Is

A brownfield refactor of Flowin's `agents/execution_engine/engine.py`: turn the prototype-/PPT-/revision-coupled `ExecutionEngine` into a small, **workflow-agnostic runtime kernel** driven by **declarative workflow manifests** that compile to a typed `ExecutionPlan`. Every rich capability today hardwired for `prototype` (per-task sub-agent loop, validation + fix-loop, context injection, deliverable resolution, clarify defaults) becomes a **declared, registered capability** any workflow can opt into. The Workspace / RuntimeEnvironment abstraction is **designed now** (local implementation only) so ECS/containers plug in later as a backend swap, not an engine rewrite.

It is for the engineers building and operating Flowin's agent workflows — and, through the dynamic composer, for users who compose custom workflows from an allow-listed capability palette.

## Core Value

**A brand-new custom workflow can replicate `prototype` by manifest + AGENT.md only — with zero engine edits (SC-001).** If everything else fails, this must hold: the kernel knows no workflow by name, and all power lives in registered, declared capabilities.

## Requirements

### Validated

<!-- Existing engine behavior — preserved byte-for-byte (deterministic output) + at semantic event parity throughout the migration (INV-3). -->

- ✓ Generic DAG spine: DAG validation, step sequencing, `consumes` routing, Human gates, artifact storage — existing
- ✓ `prototype` / `od_prototype` workflow: spec → plan → per-task build loop → validate (per-task sub-agent loop, HTML deliverable) — existing
- ✓ `prototype_revision` workflow: parent-run seeding, pre-edit baselines, post-revision validation fix-loop — existing
- ✓ PPT / `od_ppt` workflow: carousel-deck sanitize, artifact unwrap, text-PPT deliverable — existing
- ✓ One code-gen pipeline — existing
- ✓ Human (HITL) review gate: `_run_review_gate` + `review_gate_*` events — existing
- ✓ LangChain `deepagents` runtime via `create_deep_agent` (`deepagents==0.6.7`, adopted in 002) — existing
- ✓ Disk skill hierarchy (user→global→built-in) + UI-attached skills — existing (partial)
- ✓ Inbound MCP server (`/flowin-handoff`) — existing
- ✓ GitHub handoff pipeline (scoped PAT) — existing (separate path, bypasses runtime)
- ✓ Declarative file-backed workflow manifests + thin no-DSL `WorkflowCompiler` → typed `CompiledWorkflow` (INV-5 / MAN-01 / MAN-02) — Phase 4 (1A)
- ✓ `CapabilityRegistry` name-seam (14 names) + Protocol ports; compiler validates every declared reference and rejects unknown (INV-4 / MAN-03) — Phase 4 (1A); concrete impls Phase 7, trust/self-registration Phase 8
- ✓ Every pipeline runs from its `CompiledWorkflow`; `pipeline_type` reduced to an id-alias; no legacy dispatch fallback; Phase-0A snapshots byte-identical (MAN-04 / MAN-05 / INV-3) — Phase 4 (1A)
- ✓ `GET /api/workflows[/{id}]` manifest-derived metadata + run-history relocated to `/api/runs` (API-01) — Phase 4 (1A)

### Active

<!-- The refactor scope. Building toward these (full detail + REQ-IDs in REQUIREMENTS.md, phases in ROADMAP.md). -->

- [x] Workflow-agnostic kernel: no `if pipeline_type == "..."` / `if spec.id == "..."` branches anywhere (INV-1) — **Phase 7 kernel dispatch is name-free (proven)**: L1–L13 deleted from the kernel; banned-pattern hard-fail gate + migration-ledger ratchet green. **SC-001 fully met — Phase 7 gap-closure 07-07…07-11 (2026-06-09)** closed all 14 deep-review findings (07-REVIEW-DEEP.md): `task_loop`/kernel `prototype.html` de-hardcoded to `deliverable.name`, `previous_run` honors declared `seed_files`, the kernel-resident revision block was evicted to a `revision_validation` post-step capability, and context_message was re-pinned to the `acd1636` oracle (the 07-06 parity drift fixed). A brand-new non-prototype `task_loop` workflow produces `app.py` from manifest+AGENT.md with ZERO engine edits (`test_sc001_nonprototype_task_loop`). Re-verified PASSED 9/9. Routing was made manifest-driven in Phase 4 / 1A.
- [ ] Per-run `ExecutionContext`; stateless immutable kernel singleton (INV-2)
- [x] Declarative file-backed workflow manifests → thin compiler (no DSL) → typed `CompiledWorkflow`/`ExecutionPlan` (INV-5) — **Phase 4 / 1A complete** (MAN-01/02; step-level + top-level strict-key DSL rejection)
- [~] `CapabilityRegistry` + trust model: strategies, validators, deliverables, context providers, gates, isolation, merge, task parsers, worker agents, runtimes, skills, hooks, tools, MCP, integrations (INV-4) — **Phase 4 / 1A**: central name-seam (14 names) + Protocol ports + compiler validation done; **Phase 7**: concrete impls (strategies/deliverables/providers/parser/compaction) + `resolve(kind,name)` seam landed; trust/`@register`/self-registration remain Phase 8
- [~] Execution strategies: `single_shot`, `task_loop`, `fanout_batch`, `wave_scheduler` — **Phase 7**: `single_shot` + `task_loop` landed behind the `ExecutionStrategy` port (PARITY-01); **Phase 11**: `fanout_batch` landed (declarative entry funneling through kernel `run_fanout`); `wave_scheduler` is Phase 12
- [ ] Validator registry + generic fix-loop + P0–P3 severity; make `Validation_Gate` real
- [x] Deliverable resolver registry (`single_file`, `serialized_sandbox`, `streamed_text`, `repo_diff`, `ppt`) — **Phase 7**: single_file/serialized_sandbox/streamed_text/ppt landed behind the `DeliverableResolver` port (PARITY-02/07); **Phase 9**: `repo_diff` landed (diff-only via `Workspace.git_diff`, REPO-04)
- [~] Context provider registry (`opendesign`, `repo`, `previous_run`, `uploaded_files`, `memory`) + declared seed files — **Phase 7**: `opendesign` + `previous_run` + declared `seed_files` landed at byte-parity to legacy L12 (PARITY-03; context-injection gap closed in 07-06); **Phase 9**: `repo` provider landed (context_pack + context_selector, REPO-03); `uploaded_files`/`memory` are later phases
- [ ] Manifest `planner` / `clarify` config + per-agent injects
- [x] Context compaction: `_extract_html_skeleton` registered as the `html_skeleton` `CompactionStrategy` capability — **Phase 3 / 0C** (COMPACT-01/02/03 ✓: ≥50% deterministic gate + semantic parity, INV-3 sanctioned change) + **Phase 7** (PARITY-04: registered behind the `CompactionStrategy` port; L13 deleted from the kernel)
- [ ] Gate registry: `human` / `validation` / `approval` / `security` (INV-9 ties)
- [ ] Step-level least-privilege tool permissions; exec/network/secrets/spawn default OFF (INV-9)
- [ ] Typed artifacts + lineage: `ArtifactGraph`/`ArtifactRef`, content-addressed, owner-scoped (INV-10)
- [ ] Ownership everywhere, default-deny; explicit parent-run ownership check; `anon:<session_id>` owner (INV-8)
- [ ] Persistence schema (§18): `workflows`, `workflow_runs`(extend), `artifact_refs`, `workspaces`, `repositories`, `subagent_runs` (landed 0019, Phase 11), `wave_runs`, `validation_results`, `gate_events`, `run_events`, `run_capabilities`, `hook_runs` — additive migrations only
- [ ] Model policy + per-agent model selection (`model_overrides`, `ModelCatalog`, fallback chain) (§20)
- [x] `Workspace` / `RuntimeEnvironment` ports + `LocalSandboxRuntime` (local only) — **Phase 9 (4A)**: 4 stdlib-only Protocols in `agents/runtime/base.py` + `@register("runtime_env","local")` impl; 4th import-linter contract locks the ECS-swap seam; `RunSandbox` refolded onto `Workspace(has_git=False, exec=off)` with no engine fork; `repositories` + `kind=repo` workspaces persisted (migration 0017) (RUNTIME-01/02/03)
- [x] Repo workflows (no exec): inventory / index / context-pack + `repo_diff` (Phase 4A) — **Phase 9**: REPO-01..05 complete; sample brownfield workflow runs clone→branch→inventory→edit→diff end-to-end offline with exec OFF and ZERO engine edits; tree-sitter behind the `repo_index` capability (official per-language grammar wheels after the language-pack failed the offline proof)
- [x] Safe local exec behind the `security` gate + compile/test/lint validators (Phase 4B) — **Phase 10**: N3 RESOLVED (10-SPEC.md is the decision record); hardened argv/no-shell `exec_command`, trust-conditional compiler ceiling, security+approval gates, `code_compile`/`code_test`/`code_lint` validators reaching exec only via the workspace handle, `exec_runs` audit (alembic 0018). EXEC-01/EXEC-02 + SC-001 proven offline with zero engine edits
- [x] Engine-owned fan-out + merge-conflict flow + budgets + depth/concurrency caps (INV-7, Phase 5) — **Phase 11 COMPLETE (verified 13/13)**: kernel `run_fanout` single spawn path (declarative `fanout_batch` + gated `spawn_subagents` request-emitter, FANOUT-01..04); engine-decided `sub_sandbox`/`worktree` isolation on `LocalWorkspace` (FANOUT-05); `MergeStrategy` port + 4 impls + `merge_conflict` artifact/event + 4 `on_conflict` policies (FANOUT-06..08); enforcing `BudgetManager` reserve-before-spawn + trust-conditional `Limits` + per-workspace ceilings + `BudgetSnapshot` (FANOUT-09, OBS-01); `subagent_runs` rows + `subagent_*`/`merge_*` events (FANOUT-10); cancellation propagation + finally-teardown (FANOUT-11, RESUME-01); SC-001 sample fan-out workflow runs manifest+AGENT.md-only (registry 53→59)
- [ ] Wave scheduler (topo by `depends_on` + `conflict_keys`) + durable mid-wave resume (Phase 6)
- [ ] `AgentRuntimeAdapter` + `PromptAssemblyPolicy` (declared block order) (§30)
- [ ] Executable lifecycle hooks (`secret_scan`, `otel_tracing`, pre/post-commit, post-task, …) + `hook_runs` (N12)
- [x] MCP client + allow-listed famous-server catalog (GitHub/GitLab/Jira/Slack/…) (N13) — **Phase 9**: `McpClientAdapter` over `langchain-mcp-adapters` `MultiServerMCPClient` (async prewarm into `create_deep_agent` tools, INV-13 intact); 6-server catalog (4 user-allowed read-scoped, filesystem/postgres admin-only); Fernet-encrypted owner-scoped `McpCredential`; compiler `server.tool` validation; security-gate+secrets binding for powerful servers; `integration_provider` bridges (github/gitlab/jira/slack) via the same path — no parallel SDK (MCP-01..04, INTEG-01/02); CodingAgent handoff bypass deleted (D-09)
- [ ] Cancellation / idempotent retry / durable resume; monotonic event `seq` + replay cursor (§21)
- [~] Dynamic API/frontend contract: `/api/workflows`, `/api/capabilities`, artifact/diff trees, event replay (§22) — **Phase 4 / 1A**: `/api/workflows[/{id}]` manifest metadata + `/api/runs` relocation done (API-01); `/api/capabilities`, artifact/diff trees, event replay are later phases
- [ ] Code-deletion / anti-duplication discipline: move-don't-copy, §31 migration ledger, per-phase deletion gates + dead-code scan + import-linter (INV-12)
- [ ] LangChain `deepagents` mandated project-wide; banned-pattern CI gate against hand-rolled deep agents (INV-13 / R15)

### Out of Scope

<!-- §27 — designed-for via interfaces, NOT built in this milestone. -->

- ECS/EC2 provisioning, warm/dedicated containers — backend swap behind `RuntimeEnvironment` port (Phase 7, separate spec)
- Container networking & cloud secrets injection, production teardown/lease mgmt — infra follow-up
- CP-SAT scheduling — topo wave-builder only; seam left (Q32)
- Single-file fragment-merge parallelism — prototype stays sequential (Q33)
- Untrusted **end-user code execution** — trust seam exists; engineer-only + `security`+`approval`-gated (N3 resolved Phase 10; end-user exec remains out of scope behind the gates)
- PR/commit **push** — diff-only until git-hosting integration (N4)
- DB-backed user-authored workflows — file-backed manifests now; DB later (Q5)
- Hand-rolled / local `deepagents` runtime — banned (INV-13); always import the real library

## Context

- **Builds on** [002-deepagents-migration](../specs/002-deepagents-migration/plan.md) — the `deepagents` runtime this refactor restructures.
- **Supersedes** the hardcoded `pipeline_type` / `spec.id == "prototype-build"` branches in `agents/execution_engine/engine.py`.
- **The leak map (§4):** 16 verified couplings L1–L16 in `engine.py` (literal name frozensets, `_resolve_final_output`, carousel sanitize, revision seeding, skip-planner, clarify defaults, build-loop dispatch, HTML readback, build-loop internals, context injection, dead skeleton, singleton per-run state, untyped `accumulated_outputs`, unchecked parent seeding) — all must move to declarations.
- **Factory leaks (§30/§31):** F1 prompt-assembly inline order, F2 closed tool switch, F3 inline skills/hooks, F4 constitution no-op (R12), F5 hardcoded `create_deep_agent`.
- **Known production bugs surfaced by the plan:** R12 constitution injection is a silent no-op in production (`factory.py:282-290`); hooks are prompt-only, not persisted/executable; MCP is inbound-server-only (no client); runtime/tools/prompt-order all hardcoded.
- **Branch:** `feature/003-workflow-engine-decoupling` (off `deepagents-full-swap`). Repo is GitLab (`hexaware-uki/flowin`) → GitLab likely required for git hosting (N4).
- **Migration approach:** strangler/incremental (Q39) — introduce abstractions behind existing behavior, migrate prototype to declarations, delete hardcoded leaks while prototype keeps working throughout.
- **Full specification:** `specs/003-workflow-engine-decoupling/plan.md` (the authoritative source; nothing in it may be dropped).
- **Current state (2026-06-07):** Phases 0–2 + **Phase 3 (Token-Trim, 0C) complete** — the one sanctioned INV-3 non-byte-identical change is live: build-task-2+ `prototype`/`od_prototype` prompts inject the compact `_extract_html_skeleton` state-map instead of the full current HTML (96.9% measured reduction on a 2-page fixture), with the semantic event snapshots held green and deliverable goldens unchanged. Next: **Phase 4 — Manifest + Compiler (1A)**.

## Constraints

- **Tech stack**: Python · FastAPI · PostgreSQL · LangGraph checkpointer — extend, don't replace.
- **Runtime mandate (INV-13)**: every agent runs on LangChain `deepagents` — canonical import `from deepagents import create_deep_agent` (PyPI `deepagents==0.6.7`); adapter id `langchain_deepagents`. No hand-rolled deep agent, no local `deepagents`/`langchain_deepagents` module, no re-implemented agent loop. Enforced by banned-pattern CI gate (R15).
- **Architecture**: Ports & Adapters (hexagonal) — kernel depends only on capability ports; concrete impls self-register into the `CapabilityRegistry`. Adding a capability = add a module + register; no kernel edit. Enforced by import-linter (§31).
- **Compiler**: thin, no DSL (INV-5) — manifests are data; control flow lives inside strategies.
- **Persistence**: additive migrations only (Q3); every new table carries `owner_id` + `workspace_id`.
- **Security**: `exec`/`network`/`secrets`/`spawn_subagents` default OFF; code-exec stays behind the `security`+`approval` gates (N3 resolved Phase 10 — 10-SPEC.md; `network`/`secrets` remain gated-off).
- **No dual implementations (INV-3/INV-12)**: a phase that adds an abstraction without deleting the code it supersedes is **not done**. Only sanctioned temporary duplication: the `accumulated_outputs` mirror (removed Phase 1B).
- **Backward-compat (Q3, INV-3)**: existing prototype/`od_*`/PPT/code-gen behavior stays deterministic-byte-identical + semantic-event-parity, proven by characterization tests (Phase 0A).

## Key Decisions

<!-- Locked decisions from the plan (Q1–Q45, A1–A12, N1–N13). Open items (N2–N11) confirm before their phase. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Unify vocabulary on `workflow`; `pipeline_type` kept as temporary alias (Q1) | Avoid privileged built-in paths | — Pending |
| Engineer-registered capabilities + user-composable manifests; trust boundary (Q2) | Power as data, safe palette for users | — Pending |
| Success = prototype parity by manifest/config only, zero engine edits (Q4 / SC-001) | The one test that must hold | ✓ Proven — **Phase 7 gap-closure 07-07…07-11 (2026-06-09)** closed all 14 deep-review findings (07-REVIEW-DEEP.md): context_message re-pinned to the `acd1636` oracle (parity drift fixed), `prototype.html` de-hardcoded, declared `seed_files` honored. A brand-new non-prototype `task_loop` workflow produces `app.py` from manifest+AGENT.md with ZERO engine edits (`test_sc001_nonprototype_task_loop`, 3 hard passes). Re-verified PASSED 9/9. |
| File-backed manifests now; DB-backed user workflows later (Q5) | Dogfood the model without DB scope | — Pending |
| `ExecutionStrategy` registry: single_shot/task_loop/fanout_batch/wave_scheduler (Q8) | "How a step runs" is pluggable | — Pending |
| Canonical `Task` schema + parser adapters (Q11) | One task model, many formats | — Pending |
| Engine owns fan-out via `spawn_subagents` tool (Q13 / INV-7) | Agents never call raw lib task mechanism | ✓ Proven — **Phase 11**: `spawn_subagents` is a spawn-free request-emitter (`user_allowed=False`); the engine derives + fulfils via kernel `run_fanout`; library `task` tool stays excluded |
| Deterministic topo wave-builder first; CP-SAT seam later (Q31/Q32) | Decouple before scheduling sophistication | — Pending |
| Per-sub-agent subdirs first; git worktrees for brownfield (Q34) | Filesystem isolation primitive | ✓ Proven — **Phase 11**: `sub_sandbox` child dirs + `worktree` branch-per-worker on `LocalWorkspace` (single git owner); engine selects scope by `has_git` (INV-7) |
| Internal P0–P3 severities → external CRITICAL/HIGH/MEDIUM/LOW (Q24) | Match existing prose, clean UI mapping | — Pending |
| Local runtime now; ECS later behind the port (N1 ✅) | Defer infra, keep the seam | — Pending |
| Hooks are executable lifecycle/tool-call handlers (N12 ✅) | Real enforcement (secret-scan, tracing) | — Pending |
| Adopt MCP client + all famous servers via allow-listed catalog (N13 ✅) | Consume external MCP, scoped per-owner creds | — Pending |
| User per-agent model selection at top of resolution order (A12) | Composer model dropdown per agent | — Pending |
| **Open (confirm before phase):** N4 git hosting (GitHub vs GitLab) · N8 long-job substrate · N9 artifact retention · N11 model default/premium policy | Decision records pending | — Pending |
| **Resolved:** N2 isolation MVP (Phase 9 LocalSandboxRuntime) · **N3 exec threat-model (Phase 10 — 10-SPEC.md is the decision record)** · N5/N7 repo deliverable shape (Phase 9 diff-only `repo_diff`) · N6/N10 RepoIndex approach (Phase 9 grep-default + opt-in tree-sitter) | — | — Resolved |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions (sync with the plan's §32 decision log + §31 ledger status)
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — SC-001 still the right priority?
3. Audit Out of Scope — N#/§27 reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-11 — Phase 12 COMPLETE (final phase; offline-verified 15/15 after UAT gap closure). Milestone-end live UAT pass (playwright, real stack) verified the wave/resume backend live but found 3 gaps: WaveTreePanel dead UI, resumed-run tail never delivered to reconnecting clients (3 sub-causes), sample_wave deliverable fallback. Gap plans 12-08/09/10 closed all three: WaveTreePanel mounted in DashboardLayout + FE `pipeline_reconnected` handling; engine→WS resume bridge (3 injected hooks, wired in app/main.py only — kernel still app-free), consistent `workflow_runs.workspace_id` stamping + resume-marker workspace recovery; sample_wave deliverable → registered `serialized_sandbox` (zero engine edits, SC-001 held). Code review of the gap delta found 1 critical (live-attach IDOR — now owner-gated, AUTHZ-03) + 3 warnings (cleanup leak, task-before-queue race, swallowed PermissionError) — all fixed (12-REVIEW-FIX.md, all_fixed). Security pass done earlier (12-SECURITY.md, threats_open 0); AUTHZ-03 hardening recorded in REVIEW-FIX. Offline evidence: 163 backend targeted + 15 FE vitest green, 10 characterization snapshots byte-identical, lint-imports 4/0, tsc clean. Milestone-end live re-pass (2026-06-11, /gsd-verify-work 12) re-verified ALL 4 deferred items live: WaveTreePanel rendered live wave groups + 2 distinct worker leaves per wave on the dashboard; SIGKILL-mid-wave-2 + restart live-attached via the bridge (after_seq=17 → tail 19..29 incl. pipeline_complete) and the page resolved; deliverable resolved as the serialized_sandbox bundle with zero fallback warnings; cross-owner reconnect demoted to ∅ replay + live:false through the real handler (CR-01). VERIFICATION.md status: passed. Phase 12 + milestone v1.0 COMPLETE (12/12 phases).*
