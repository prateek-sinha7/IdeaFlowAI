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

### Active

<!-- The refactor scope. Building toward these (full detail + REQ-IDs in REQUIREMENTS.md, phases in ROADMAP.md). -->

- [ ] Workflow-agnostic kernel: no `if pipeline_type == "..."` / `if spec.id == "..."` branches anywhere (INV-1)
- [ ] Per-run `ExecutionContext`; stateless immutable kernel singleton (INV-2)
- [ ] Declarative file-backed workflow manifests → thin compiler (no DSL) → typed `CompiledWorkflow`/`ExecutionPlan` (INV-5)
- [ ] `CapabilityRegistry` + trust model: strategies, validators, deliverables, context providers, gates, isolation, merge, task parsers, worker agents, runtimes, skills, hooks, tools, MCP, integrations (INV-4)
- [ ] Execution strategies: `single_shot`, `task_loop`, `fanout_batch`, `wave_scheduler`
- [ ] Validator registry + generic fix-loop + P0–P3 severity; make `Validation_Gate` real
- [ ] Deliverable resolver registry (`single_file`, `serialized_sandbox`, `streamed_text`, `repo_diff`, `ppt`)
- [ ] Context provider registry (`opendesign`, `repo`, `previous_run`, `uploaded_files`, `memory`) + declared seed files
- [ ] Manifest `planner` / `clarify` config + per-agent injects
- [ ] Context compaction strategy (wire the dead `_extract_html_skeleton` as `html_skeleton`)
- [ ] Gate registry: `human` / `validation` / `approval` / `security` (INV-9 ties)
- [ ] Step-level least-privilege tool permissions; exec/network/secrets/spawn default OFF (INV-9)
- [ ] Typed artifacts + lineage: `ArtifactGraph`/`ArtifactRef`, content-addressed, owner-scoped (INV-10)
- [ ] Ownership everywhere, default-deny; explicit parent-run ownership check; `anon:<session_id>` owner (INV-8)
- [ ] Persistence schema (§18): `workflows`, `workflow_runs`(extend), `artifact_refs`, `workspaces`, `repositories`, `subagent_runs`, `wave_runs`, `validation_results`, `gate_events`, `run_events`, `run_capabilities`, `hook_runs` — additive migrations only
- [ ] Model policy + per-agent model selection (`model_overrides`, `ModelCatalog`, fallback chain) (§20)
- [ ] `Workspace` / `RuntimeEnvironment` ports + `LocalSandboxRuntime` (local only)
- [ ] Repo workflows (no exec): inventory / index / context-pack + `repo_diff` (Phase 4A)
- [ ] Safe local exec behind the `security` gate + compile/test/lint validators (Phase 4B, gated on N3)
- [ ] Engine-owned fan-out + merge-conflict flow + budgets + depth/concurrency caps (INV-7, Phase 5)
- [ ] Wave scheduler (topo by `depends_on` + `conflict_keys`) + durable mid-wave resume (Phase 6)
- [ ] `AgentRuntimeAdapter` + `PromptAssemblyPolicy` (declared block order) (§30)
- [ ] Executable lifecycle hooks (`secret_scan`, `otel_tracing`, pre/post-commit, post-task, …) + `hook_runs` (N12)
- [ ] MCP client + allow-listed famous-server catalog (GitHub/GitLab/Jira/Slack/…) (N13)
- [ ] Cancellation / idempotent retry / durable resume; monotonic event `seq` + replay cursor (§21)
- [ ] Dynamic API/frontend contract: `/api/workflows`, `/api/capabilities`, artifact/diff trees, event replay (§22)
- [ ] Code-deletion / anti-duplication discipline: move-don't-copy, §31 migration ledger, per-phase deletion gates + dead-code scan + import-linter (INV-12)
- [ ] LangChain `deepagents` mandated project-wide; banned-pattern CI gate against hand-rolled deep agents (INV-13 / R15)

### Out of Scope

<!-- §27 — designed-for via interfaces, NOT built in this milestone. -->

- ECS/EC2 provisioning, warm/dedicated containers — backend swap behind `RuntimeEnvironment` port (Phase 7, separate spec)
- Container networking & cloud secrets injection, production teardown/lease mgmt — infra follow-up
- CP-SAT scheduling — topo wave-builder only; seam left (Q32)
- Single-file fragment-merge parallelism — prototype stays sequential (Q33)
- Untrusted **end-user code execution** — trust seam exists; engineer-only + `security`-gated until N3
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

## Constraints

- **Tech stack**: Python · FastAPI · PostgreSQL · LangGraph checkpointer — extend, don't replace.
- **Runtime mandate (INV-13)**: every agent runs on LangChain `deepagents` — canonical import `from deepagents import create_deep_agent` (PyPI `deepagents==0.6.7`); adapter id `langchain_deepagents`. No hand-rolled deep agent, no local `deepagents`/`langchain_deepagents` module, no re-implemented agent loop. Enforced by banned-pattern CI gate (R15).
- **Architecture**: Ports & Adapters (hexagonal) — kernel depends only on capability ports; concrete impls self-register into the `CapabilityRegistry`. Adding a capability = add a module + register; no kernel edit. Enforced by import-linter (§31).
- **Compiler**: thin, no DSL (INV-5) — manifests are data; control flow lives inside strategies.
- **Persistence**: additive migrations only (Q3); every new table carries `owner_id` + `workspace_id`.
- **Security**: `exec`/`network`/`secrets`/`spawn_subagents` default OFF; code-exec stays behind the `security` gate until N3.
- **No dual implementations (INV-3/INV-12)**: a phase that adds an abstraction without deleting the code it supersedes is **not done**. Only sanctioned temporary duplication: the `accumulated_outputs` mirror (removed Phase 1B).
- **Backward-compat (Q3, INV-3)**: existing prototype/`od_*`/PPT/code-gen behavior stays deterministic-byte-identical + semantic-event-parity, proven by characterization tests (Phase 0A).

## Key Decisions

<!-- Locked decisions from the plan (Q1–Q45, A1–A12, N1–N13). Open items (N2–N11) confirm before their phase. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Unify vocabulary on `workflow`; `pipeline_type` kept as temporary alias (Q1) | Avoid privileged built-in paths | — Pending |
| Engineer-registered capabilities + user-composable manifests; trust boundary (Q2) | Power as data, safe palette for users | — Pending |
| Success = prototype parity by manifest/config only, zero engine edits (Q4 / SC-001) | The one test that must hold | — Pending |
| File-backed manifests now; DB-backed user workflows later (Q5) | Dogfood the model without DB scope | — Pending |
| `ExecutionStrategy` registry: single_shot/task_loop/fanout_batch/wave_scheduler (Q8) | "How a step runs" is pluggable | — Pending |
| Canonical `Task` schema + parser adapters (Q11) | One task model, many formats | — Pending |
| Engine owns fan-out via `spawn_subagents` tool (Q13 / INV-7) | Agents never call raw lib task mechanism | — Pending |
| Deterministic topo wave-builder first; CP-SAT seam later (Q31/Q32) | Decouple before scheduling sophistication | — Pending |
| Per-sub-agent subdirs first; git worktrees for brownfield (Q34) | Filesystem isolation primitive | — Pending |
| Internal P0–P3 severities → external CRITICAL/HIGH/MEDIUM/LOW (Q24) | Match existing prose, clean UI mapping | — Pending |
| Local runtime now; ECS later behind the port (N1 ✅) | Defer infra, keep the seam | — Pending |
| Hooks are executable lifecycle/tool-call handlers (N12 ✅) | Real enforcement (secret-scan, tracing) | — Pending |
| Adopt MCP client + all famous servers via allow-listed catalog (N13 ✅) | Consume external MCP, scoped per-owner creds | — Pending |
| User per-agent model selection at top of resolution order (A12) | Composer model dropdown per agent | — Pending |
| **Open (confirm before phase):** N2 isolation MVP · N3 exec threat-model ⚠️ · N4 git hosting (GitHub vs GitLab) · N5 branch/PR policy · N6 repo scale · N7 repo deliverable shape · N8 long-job substrate · N9 artifact retention · N10 RepoIndex approach · N11 model default/premium policy | Decision records pending | — Pending |

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
*Last updated: 2026-06-06 after initialization*
