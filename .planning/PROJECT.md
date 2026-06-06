# Workflow Engine Decoupling & Universal Workflow Runtime

## What This Is

A brownfield refactor of Flowin's `agents/execution_engine/engine.py`: turn the prototype-/PPT-/revision-coupled
`ExecutionEngine` into a small, **workflow-agnostic runtime kernel** driven by **declarative workflow manifests**
that compile to a typed `ExecutionPlan`. Every rich capability today hardwired for `prototype` (per-task sub-agent
loop, validation + fix-loop, context injection, deliverable resolution, clarify defaults) becomes a **declared,
registered capability** any workflow can opt into. The Workspace / RuntimeEnvironment abstraction is **designed now**
(local implementation only) so ECS/containers plug in later as a backend swap, not an engine rewrite.

It is for the engineers building and operating Flowin's agent workflows — and, through the dynamic composer, for
users who compose custom workflows from an allow-listed capability palette.

## Core Value

**A brand-new custom workflow can replicate `prototype` by manifest + AGENT.md only — with zero engine edits (SC-001).**
If everything else fails, this must hold: the kernel knows no workflow by name, and all power lives in registered,
declared capabilities.

## Requirements

See `.planning/REQUIREMENTS.md` for the full, ID'd list and phase traceability. Summary:

### Validated

<!-- Shipped and confirmed. Inherited from the codebase this refactor builds on. -->

- ✓ `prototype`, `od_*`, PPT, and code-gen workflows run today on the LangChain `deepagents` runtime — existing (002)
- ✓ HITL `human` review gate + `review_gate_*` events work — existing
- ✓ Per-user run sandbox namespacing on disk (`RunSandbox`) — existing
- ✓ GitHub handoff pipeline with scoped PAT — existing (separate from the main runtime)

### Active

<!-- This refactor's scope. Building toward these. -->

- [ ] Workflow-agnostic kernel: no `if pipeline_type` / `spec.id ==` behavior branches (INV-1)
- [ ] All per-run state in a per-run `ExecutionContext`; kernel singleton stateless (INV-2)
- [ ] Declarative file-backed manifests → thin compiler → typed `ExecutionPlan` (INV-5)
- [ ] `CapabilityRegistry` for strategies, validators, resolvers, providers, gates, runtimes, hooks, MCP, integrations (INV-4)
- [ ] Typed, lineage-tracked, owner-scoped `ArtifactGraph` replacing `accumulated_outputs` (INV-10)
- [ ] Ownership everywhere, default-deny (INV-8); least-privilege step tool permissions (INV-9)
- [ ] Per-agent model policy + user model overrides (§20)
- [ ] Engine-owned fan-out + merge, wave scheduler, durable resume (§12/§13/§21)
- [ ] Local Workspace/RuntimeEnvironment + repo (brownfield) workflows, no exec first (§14)
- [ ] LangChain `deepagents` mandated as the runtime — never hand-rolled (INV-13)
- [ ] Strangler migration with move-don't-copy deletion discipline + ledger (INV-12, §31)
- [ ] Dynamic API/frontend contract: `/workflows`, `/capabilities`, artifact/diff/event endpoints (§22)

### Out of Scope

<!-- §27 non-goals — designed-for via interfaces, not built here. -->

- ECS/EC2 provisioning, warm/dedicated containers, container networking & cloud secrets — backend swap behind the `RuntimeEnvironment` port, later (Phase 7, separate spec)
- Untrusted **end-user code execution** — trust seam exists; capability stays engineer-only + `security`-gated until the N3 threat model
- CP-SAT scheduling — topo wave-builder only; smarter scheduling is a seam (Q32)
- Single-file fragment-merge parallelism — prototype stays sequential (Q33)
- PR / commit **push** — diff-only until git-hosting integration lands (N4)

## Context

- **Builds on** `specs/002-deepagents-migration` — the LangChain `deepagents` runtime this refactor restructures.
- **Source design doc:** `specs/003-workflow-engine-decoupling/plan.md` (this `.planning/` set is its GSD translation).
- **The "as-is" leak map (§4):** 16 verified couplings (L1–L16) in `engine.py` plus factory leaks (F1–F5) must move
  to declarations and be deleted in the phase that supersedes them.
- **Migration approach:** strangler/incremental (Q39) — introduce abstractions behind existing behavior, migrate
  prototype to declarations, then delete the hardcoded branches while prototype keeps working throughout.
- **Backward-compat bar (INV-3):** deliverables byte-identical **where deterministic** + WS event stream at
  **semantic parity** (same types/order/required fields + final result; volatile fields normalized out). Phase 0C
  is the one sanctioned context-change exception (gated on semantic snapshot + measured token delta).
- **Open decisions to confirm before their phase:** N2–N11 (esp. N3 exec threat model, N4 GitHub-vs-GitLab,
  N6 repo scale, N9 retention, N11 model policy). N1/N12/N13 already decided.

## Constraints

- **Tech stack**: Python · FastAPI · PostgreSQL · LangGraph checkpointer — extend, don't replace.
- **Runtime mandate (INV-13)**: every agent runs on the LangChain `deepagents` library — canonical import
  `from deepagents import create_deep_agent` (PyPI `deepagents==0.6.7`); our adapter id is `langchain_deepagents`.
  No hand-rolled deep agent, no local `deepagents`/`langchain_deepagents` module, no re-implemented agent loop. Enforced by a banned-pattern CI gate (R15).
- **Architecture**: Ports & Adapters (hexagonal) — kernel depends only on capability ports; concrete impls
  self-register into the `CapabilityRegistry`. Adding a capability = add a module + register; no kernel edit. Enforced by import-linter (§31).
- **Compiler**: thin, no DSL (INV-5) — manifests are data; control flow lives inside strategies.
- **Persistence**: additive migrations only (Q3); every new table carries `owner_id` + `workspace_id`.
- **Security**: `exec`/`network`/`secrets`/`spawn_subagents` default OFF; code-exec stays behind the `security` gate until N3.
- **No dual implementations (INV-3/INV-12)**: a phase that adds an abstraction without deleting the code it supersedes is not done.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Unify vocabulary on `workflow`; keep `pipeline_type` as a temporary alias (Q1) | One term; non-breaking migration | — Pending |
| Engineer-registered capabilities + user-composable manifests; trust boundary (Q2) | Safe extensibility; user palette is allow-listed | — Pending |
| Success = prototype parity by manifest/config only, zero engine edits (Q4, SC-001) | The single proof the decoupling worked | — Pending |
| Built-in workflows are **hand-authored** file manifests; generated index optional later (Q5/§28) | Avoid a privileged generated source-of-truth | — Pending |
| Named `ExecutionStrategy` registry: single_shot, task_loop, fanout_batch, wave_scheduler (Q8) | "How a step runs" becomes pluggable | — Pending |
| Strangler/incremental migration with characterization tests first (Q39/Q40) | De-risk parity regressions | — Pending |
| Rollout order: token-trim → manifest → strategies → validators/deliverables/providers → fan-out → waves (Q41) | Lowest-risk first; each phase shippable | — Pending |
| **N1** Local runtime now; ECS later behind the port | Avoid premature infra; keep it a backend swap | ✓ Decided |
| **N12** Hooks are **executable** lifecycle/tool-call handlers (+ persisted), not prompt-only | Real secret-scan/tracing/commit hooks | ✓ Decided |
| **N13** Adopt an MCP **client** + allow-listed catalog of famous servers | Consume GitHub/GitLab/Jira/Slack/… safely | ✓ Decided |
| **INV-13** LangChain `deepagents` mandated project-wide; never hand-roll | Prevent the regression 002 fixed | ✓ Decided |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions (update Outcome on the N#/Q# rows as phases confirm them)
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-06 after initialization (translated from specs/003-workflow-engine-decoupling/plan.md)*
