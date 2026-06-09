# Phase 8: Capabilities Hardened — Registry, Gates, Tool Perms, Runtime [3] — Specification

**Created:** 2026-06-09
**Ambiguity score:** 0.15 (gate: ≤ 0.20)
**Requirements:** 16 locked (covering 29 requirement IDs)

## Goal

The `CapabilityRegistry` becomes self-registering with per-owner trust flags and gains the `tool`/`skill`/`hook`/`runtime` kinds; gates (`human`/`validation`/`approval`/`security`) become first-class registry-driven handlers with a real `Validation_Gate`; step tool-permissions are enforced least-privilege at `factory._build_runner_tools`; and the factory's hardcoded prompt-order/tool-switch/skills-hooks/constitution/runtime (F1–F5) are lifted into `PromptAssemblyPolicy` + provider registries + `AgentRuntimeAdapter` and **deleted** — all while every existing workflow stays at strict INV-3 parity.

## Background

Phase 7 proved SC-001 (a non-prototype manifest runs with zero engine edits) and left the kernel name-agnostic. The capability machinery that makes this work is still half-formed and the factory is still hardcoded:

- **Registry** (`agents/capabilities/registry.py`): `CapabilityRegistry` holds a `_KNOWN` set of 16 `(kind, name)` pairs and a `_IMPLS` map bound by an explicit `install()`. Its own docstring states the evolution to `@register`/`discover()` self-registration **plus per-owner trust flags is Phase 8** (deliberately deferred, not a dual implementation). Kinds present: strategy, validator, deliverable, context_provider, task_parser, gate, compaction, post_step, model_catalog. **Missing kinds**: `tool`, `skill`, `hook`, `runtime`, and the §30 capability layer.
- **Gates**: `human` works (`engine._run_review_gate` + `review_gate_*` events). `Validation_Gate` is accepted by the AGENT.md loader (`loader.py:355`) but **never implemented** — declared-but-dead. `approval`/`security` do not exist. The `GateHandler` Protocol port exists (`capabilities/base.py:105`) but no impls are bound.
- **Validators**: `static_check`/`render_check` exist as plain functions in `app/agents/`. `html_static`/`html_render` sit in `_KNOWN` but are **not bound** in `install()`. Phase 7 left the prototype fix-loop in `KernelServices.run_validation_fix_loop` (HTML-hardcoded). There is no `validation_results` table, no P0–P3→severity mapping, and no generic registered fix-loop.
- **Factory leaks (all ☐ in the migration ledger)**: F1 = `_compose_system_prompt` builds blocks with a hardcoded `blocks.append` order (`factory.py:174-255`); F2 = `_build_runner_tools` closed name→toolset switch that raises on unknown (`factory.py:384-446`); F3 = inline skills/hooks injection (`factory.py:220-245`); F4 = `_inject_constitution` async **no-op in production** — when an event loop is running it reads only the in-process `_mem` dict, so a Postgres-stored Constitution is silently NOT injected (`factory.py:282-306`, R12); F5 = `create_deep_agent` hardcoded in `app/agents/deep_agent_runner.py:240` with no runtime-selection seam.
- **Persistence**: Phase 5 added `artifact_refs`/`workspaces`/`run_events` and extended `workflow_runs`; `run_capabilities` exists. The §18 tables `validation_results`, `gate_events`, and `hook_runs` **do not exist yet** — this phase adds them additively.
- **Hooks**: today prompt-only — `attached_hooks` synthesized into a `## Active Behavioral Hooks` bullet list; not executable, not persisted. §30/N12 mandates executable lifecycle hooks.
- **API/frontend**: `GET /api/workflows[/{id}]` exists (Phase 4). `GET /api/capabilities` does not. The composer has no capability palette / per-agent model picker / validator panel.

This phase formalizes all of the above behind ports + registries + policy, deletes F1–F5, and fixes R12 — the factory-side analog of the engine-leak deletion that Phase 7 completed for the kernel.

## Requirements

1. **Self-registering capability registry**: `CapabilityRegistry` keyed by `(kind, name)` covers every capability kind and is populated by self-registration, not a central switch.
   - Current: `_KNOWN` is a hand-maintained 16-pair set; impls bound by an explicit imperative `install()`; no `tool`/`skill`/`hook`/`runtime` kinds; no `@register`/`discover()`.
   - Target: a `@register(kind, name)` decorator + a startup `discover()` that imports all capability packages so each plugin self-registers; the registry enumerates kinds incl. strategies, validators, deliverables, context providers, gates, task parsers, compaction, post_steps, **tools, skills, hooks, runtimes, model catalog** (isolation/merge/MCP/integration remain later-phase kinds) (CAP-01, CAP-02).
   - Acceptance: no central `if/elif` dispatch in registry resolution (grep); adding a capability module + `@register` makes it resolvable with zero registry edits (test); `discover()` registers all built-in capability packages and is idempotent.

2. **Capability trust model**: every capability carries a trust flag; user/DB manifests are validated against it.
   - Current: no `user_allowed` flag; the compiler validates names against `_KNOWN` membership only (INV-4) with no trust/owner dimension.
   - Target: each registered capability declares `user_allowed: bool`; built-in/file manifests may reference any registered capability; user/DB manifests are validated against `user_allowed` + the owner's allow-list — unknown / not-user-allowed / not-owned → compile error (CAP-03).
   - Acceptance: a user-trust-context compile of a manifest referencing a `user_allowed=False` capability raises a compile error naming the capability; a built-in/file manifest referencing the same capability compiles.

3. **Gate registry + first-class gates**: `human`/`validation`/`approval`/`security` are registered `GateHandler`s declared per step (ordered), evaluated at the step boundary.
   - Current: only `human` is implemented (`_run_review_gate`); `GateHandler` port exists but no impls bound; `approval`/`security` absent.
   - Target: a `GateHandler` registry; gates declared as `gates: [...]` per step, evaluated in order at the step boundary; outcome ∈ `pass | block | wait_human`; `security` default-denies `exec`/`network`/`secrets` (which stay OFF this phase); `approval` requires explicit sign-off before a sensitive action (GATE-01).
   - Acceptance: all four gate kinds resolve from the registry; a step declaring `gates: [security]` that requests `exec` is blocked (exec OFF); a step declaring `gates: [approval]` pauses for sign-off; `approval`/`security` each exercised by ≥1 test manifest.

4. **Real validation gate**: the declared-but-unimplemented `Validation_Gate` runs the step's validators and blocks per policy.
   - Current: `Validation_Gate` is accepted by `loader.py` but does nothing at runtime.
   - Target: the `validation` gate runs the step's declared `validators: [...]`, applies the failure policy (block on critical / warn on non-critical), and emits `validation_warning` on residual non-critical issues (GATE-02).
   - Acceptance: a manifest step with `gates: [validation]` + a validator that produces a P0 issue blocks; the same with only a P2 issue emits `validation_warning` and proceeds.

5. **Human-gate parity**: the existing HITL human gate is preserved unchanged behind the registry.
   - Current: `_run_review_gate` + `review_gate_*` events drive the inter-agent HITL pause/resume.
   - Target: the `human` gate is registered and routes through the existing `_run_review_gate` behavior — semantic event parity preserved (GATE-03).
   - Acceptance: the existing characterization snapshots for gated agents (e.g. `prototype-specify`/`prototype-plan`) emit identical `review_gate_*` event sequences; no snapshot re-baseline.

6. **Tool-permission resolution + enforcement**: a least-privilege `ToolPermissions` grant set is resolved by intersection and enforced at the tool-binding boundary.
   - Current: `_build_runner_tools` is a closed name→toolset switch (`workspace`/`prototype`/`prototype_emit_only`/`planning`) that raises on unknown; no permission model.
   - Target: `ToolPermissions` with defaults `read_files` ON; `write_files`/`git`/`spawn_subagents` OFF; `exec`/`network` OFF; `secrets`/`mcp`/`integrations` none. Effective perms = `intersection(owner_allow_list, workflow_ceiling, step_grant)`; an AGENT.md default may only **lower** a permission, never raise. Enforced at `factory._build_runner_tools` (binds only granted tool sets) and the `Workspace.ExecutionPolicy` (runtime exec/network/secrets gating) (TOOLPERM-01, TOOLPERM-02, TOOLPERM-03).
   - Acceptance: a step without `write_files` binds no write tool; an AGENT.md declaring a permission its step did not grant does not raise it (test asserts effective = intersection); `exec`/`network`/`secrets`/`spawn` remain unbindable by default.

7. **Validator registry + generic fix-loop + severity mapping**: validators are registered and declared per step; the fix-loop is generic; severity has one mapping.
   - Current: `static_check`/`render_check` are functions; `html_static`/`html_render` are in `_KNOWN` but unbound; the fix-loop is HTML-hardcoded in `KernelServices.run_validation_fix_loop`; no severity mapping; no `validation_results` rows.
   - Target: a `Validator` registry; manifests list `validators: [...]` per step; a `DeliverableContext` carries path/content/Workspace/task-meta and may request browser/compile/test/static-analysis runners; a generic fix-loop parameterized by deliverable name + `max_attempts` + a `FixPolicy` fix-prompt template (default warn-non-critical / block-critical, then `validation_warning` with residuals); internal P0–P3 severities with one function mapping to CRITICAL/HIGH/MEDIUM/LOW for the UI (VALID-01, VALID-02, VALID-03).
   - Acceptance: a step's declared validators run via the registry; the fix-loop drives off `FixPolicy` config (not hardcoded `prototype.html`); the P0–P3→CRITICAL/HIGH/MEDIUM/LOW mapping is a single tested function.

8. **Migrate html_static / html_render to registered validators**: prototype's structural + render checks run through the validator registry, persisting results.
   - Current: `static_check`/`render_check` called directly inside the prototype fix-loop.
   - Target: `html_static` and `html_render` are registered `Validator`s; the prototype `task_loop` validation routes through them; each run/attempt writes a `validation_results` row (VALID-04).
   - Acceptance: prototype build runs `html_static`/`html_render` via the registry; `validation_results` rows are written per attempt; deliverable + event parity held (see Req 16).

9. **Tier#4/5/6 validators land**: three new framework validators ship as real registered validators (Q38).
   - Current: no analyze-gate / done-when / design-quality checks exist as framework features.
   - Target: `spec_plan_coverage` (pre-build analyze), `task_done_when` (per-task acceptance), and `design_quality` (tokens/placeholder/a11y, **warnings-first / non-blocking**) ship as real registered validators that run and emit `validation_results` (VALID-05).
   - Acceptance: each of the three validators is registered, runs against a target, and is exercised by ≥1 test manifest; `design_quality` issues are non-blocking (warn only).

10. **AgentRuntimeAdapter (F5)**: `create_deep_agent` is reached only through a runtime adapter.
    - Current: `create_deep_agent` is hardcoded in `deep_agent_runner.py:240`; `create_runner` always builds a `DeepAgentRunner` with no selection seam.
    - Target: an `AgentRuntimeAdapter` wraps `create_deep_agent`; `langchain_deepagents` is the mandated adapter (INV-13); `create_deep_agent` is called **only** inside that adapter; future `claude_code_cli`/`custom_runner` slot in without kernel edits (AGENTRT-01, AGENTRT-02).
    - Acceptance (F5 CHECK gate): `create_deep_agent` is imported/called only inside the `langchain_deepagents` adapter module (test/grep); the banned-pattern + import-linter gates stay green.

11. **PromptAssemblyPolicy (F1)**: the hardcoded prompt block order becomes a declared, registry-resolved policy.
    - Current: `_compose_system_prompt` appends blocks in a fixed inline order (`blocks.append`, `factory.py:174-255`).
    - Target: a declared `PromptAssemblyPolicy` (default order `injects→guardrails→skills→hooks→constitution→prompt_body`) drives assembly; the inline `blocks.append` ordering is deleted (AGENTRT-03).
    - Acceptance (F1 grep gate): `blocks\.append` returns 0 in `factory.py`; composed prompts are byte-identical to today for existing agents (parity test).

12. **tool_provider registry (F2)**: the closed tool switch is replaced by a provider registry.
    - Current: `_build_runner_tools` raises on unknown tool-set names.
    - Target: a `tool_provider` registry resolves tool sets by name; the closed switch is deleted (AGENTRT-04).
    - Acceptance (F2 grep gate): `_build_runner_tools` returns 0; tool sets resolve via the registry; existing agents bind identical tool sets (parity test).

13. **skill_provider + hook_provider (F3, SKILL-01)**: inline skills/hooks injection is replaced by provider capabilities; the behavioral hook survives as a non-executable sub-type.
    - Current: skills/hooks injected inline in `_compose_system_prompt`; skills flattened into one content list (no provider interface, no versioning).
    - Target: `skill_provider` capabilities (ui · disk · template · repo) with a provider interface + versioning replace the flattened skill list; a `hook_provider` replaces inline hook injection; the legacy prompt-only hook survives as a `kind: behavioral` non-executable provider sub-type (AGENTRT-05, SKILL-01).
    - Acceptance (F3 grep gate): `_inject_skills|_inject_hooks` returns 0; skills resolve via `skill_provider` with version metadata; the `## Active Behavioral Hooks` block still renders for behavioral hooks.

14. **Constitution sync-safe fix (F4 / R12)**: a Postgres-stored Constitution is injected in production.
    - Current: `_inject_constitution` reads only the in-process `_mem` dict when an event loop is running → silently not injected in prod.
    - Target: constitution injection is made sync-safe / pre-warmed (via the `PromptAssemblyPolicy` path) so a DB-stored Constitution is injected in production (AGENTRT-06).
    - Acceptance (F4 CHECK gate): a constitution-injected-in-prod test passes — a DB-stored Constitution appears in the composed prompt under a running event loop.

15. **Executable hook framework + canonical hooks + persistence + observability**: lifecycle hooks fire executably and persist.
    - Current: hooks are prompt-only, not executed, not persisted; no `hook_runs` table.
    - Target: a `HookHandler` framework binds executable hooks to lifecycle/tool-call events (`before/after_run·step·tool_call·write`, `post_task`, `pre/post_commit`, `on_validation`, `before/after_merge`, or `*`); outcome `continue|warn|block` (blocking hooks halt the offending action); hooks are permissioned (a scanner needs `read_files`, a git hook needs `git`, a command hook needs `exec`); canonical hooks `secret_scan` (before_write/pre_commit, blocking) and `otel_tracing`/logging (`*`, non-blocking → OpenTelemetry-style spans/logs) fire; every firing writes a `hook_runs` row; the legacy prompt-only hook is the `behavioral` sub-type (HOOK-01, HOOK-02, HOOK-03, HOOK-04, OBS-02).
    - Acceptance: `secret_scan` blocks a `before_write` carrying a secret and writes a `hook_runs` row with `outcome=block`; `otel_tracing` fires on `*` non-blocking and emits a span + `hook_runs` row; a hook lacking its required permission is not bound.

16. **Persistence + API + frontend + strict INV-3 parity**: additive tables, the capability palette endpoint + event contract, the data-bearing composer panels, and unchanged existing-workflow behavior.
    - Current: `validation_results`/`gate_events`/`hook_runs` tables absent; no `GET /api/capabilities`; no capability palette / per-agent model picker / validator panel in the composer.
    - Target: an additive migration adds `validation_results`, `gate_events`, `hook_runs` (each carrying `owner_id` + `workspace_id`); `GET /api/capabilities` returns the registry palette (kind, name, `user_allowed`, config schema) incl. runtimes/skills/hooks/model catalog with required auth + permission scopes; the run stream emits the new `validator_result`/`validation_warning`/`gate_*` events additively; the frontend renders the **capability palette + per-agent model picker + validator/issue panel** (subagent/wave tree + repo-diff viewer deferred — no backing data); existing workflows (prototype/od_/revision/ppt/code-gen) stay at strict INV-3 parity (API-02, API-03, API-06, AGENTRT/VALID/GATE parity).
    - Acceptance: the three tables exist via an additive migration; `GET /api/capabilities` returns the palette with auth + scopes; the three frontend panels render from live API data; the existing characterization snapshots remain byte-identical (deliverables) + semantic event parity, with new events additive only (no snapshot re-baseline).

## Boundaries

**In scope:**
- Self-registering `CapabilityRegistry` (`@register` + `discover()`) + per-owner trust flags (`user_allowed`) + the `tool`/`skill`/`hook`/`runtime` capability kinds (CAP-01/02/03)
- `GateHandler` registry: `human`/`validation`/`approval`/`security`; a real `Validation_Gate`; human-gate parity (GATE-01/02/03)
- `ToolPermissions` resolution (intersection; AGENT.md may only lower) + enforcement at `factory._build_runner_tools` + `Workspace.ExecutionPolicy` (TOOLPERM-01/02/03)
- `Validator` registry + `DeliverableContext` + generic `FixPolicy` fix-loop + P0–P3→severity mapping; migrate `html_static`/`html_render`; Tier#4/5/6 validators as real validators (VALID-01..05)
- `AgentRuntimeAdapter` (`langchain_deepagents`), `PromptAssemblyPolicy`, `tool_provider`, `skill_provider`, `hook_provider`; **delete F1–F5**; fix R12 (AGENTRT-01..06, SKILL-01)
- Executable `HookHandler` framework + `secret_scan` + `otel_tracing` canonical hooks + `hook_runs` persistence + OTel observability (HOOK-01..04, OBS-02)
- Additive migration: `validation_results`, `gate_events`, `hook_runs` (each `owner_id` + `workspace_id`)
- `GET /api/capabilities` palette + additive run-stream events (`validator_result`/`validation_warning`/`gate_*`) (API-02, API-03)
- Frontend additive panels with live data: capability palette, per-agent model picker, validator/issue panel (API-06, partial)
- The `mcp` and `integrations` **tool-permission slots** (default `none`) — slots only, no client/servers wired this phase

**Out of scope:**
- **MCP client + famous-server catalog (MCP-01..04)** — Phase 9 / N13; only the `mcp` permission slot lands now
- **Integration providers (INTEG-01/02)** — Phase 9; only the `integrations` permission slot lands now
- **`RuntimeEnvironment`/`Workspace`/`LocalSandboxRuntime` + repo workflows (RUNTIME/REPO-*)** — Phase 9; the `ExecutionPolicy` enforcement point is wired but the local runtime port impl is Phase 9
- **Enabling `exec`/`network`/`secrets` + constrained-exec profile (EXEC-01/02)** — Phase 10 / N3; the `security` gate is registered and default-denies, but exec stays OFF
- **Fan-out / `spawn_subagents` real implementation (FANOUT-*)** — Phase 11; only the `spawn_subagents` permission slot (default OFF) lands now
- **Subagent/wave tree + repo-diff frontend viewers** — P11/P12/P9; no backing data until those phases
- **Live firing of git-/exec-needing canonical hooks** (`pre/post_commit` need `git`=Phase 9; command hooks need `exec`=Phase 10) — registered + permissioned now, but only `secret_scan` (read_files) and `otel_tracing` (observability) actually fire this phase
- **Prompt-content changes** (constitution consolidation, clarify write-back, recommended-defaults, spec behavior changes) — Q37: a separate content PR after decoupling; only the R12 no-op **bug fix** lands, not content changes
- **`claude_code_cli` / `custom_runner` adapters** — designed-for via the `AgentRuntimeAdapter` port, not built (only `langchain_deepagents`)
- **`isolation`/`merge` capability kinds** — Phase 11 (fan-out)

## Constraints

- **INV-3 (strict, locked this phase)**: existing workflows (prototype/od_prototype/prototype_revision/ppt/code-gen) keep **byte-identical deterministic deliverables** AND **semantic event parity**; the existing characterization snapshots are **unchanged (no re-baseline)**; new events (`validator_result`/`validation_warning`/`gate_*`) are **additive only**.
- **INV-9 least-privilege**: `read_files` ON; `write_files`/`git`/`spawn_subagents` OFF; `exec`/`network` OFF; `secrets`/`mcp`/`integrations` none; AGENT.md may only lower a default, never raise; effective = intersection(owner, workflow, step).
- **INV-12 move-don't-copy**: F1–F5 are **deleted in this phase** (not left beside the new capability); the migration-ledger F1–F5 rows flip to ☑ and their grep/CHECK gates become permanent ratchets.
- **INV-13 deepagents-only**: `create_deep_agent` reached only via the `langchain_deepagents` adapter; no hand-rolled deep agent / local `deepagents` module / re-implemented agent loop; banned-pattern CI gate (R15) stays green.
- **Hexagonal (Ports & Adapters)**: the kernel depends only on capability ports; concrete impls self-register; the import-linter contract (kernel imports only ports, never `engine`/`factory` internals) stays green.
- **Additive migrations only (Q3)**: `validation_results`/`gate_events`/`hook_runs` added additively; every new table carries `owner_id` + `workspace_id`.
- **Security defaults OFF**: `exec`/`network`/`secrets`/`spawn_subagents` stay OFF; the `security` gate is registered + default-denies; code-exec stays gated until N3 (Phase 10).
- **Tech stack**: Python · FastAPI · PostgreSQL · LangGraph checkpointer · `deepagents==0.6.7` — extend, don't replace.

## Acceptance Criteria

- [ ] `CapabilityRegistry` is self-registering (`@register` + `discover()`); no central `if/elif` dispatch; adding a capability module makes it resolvable with zero registry edits
- [ ] Per-capability `user_allowed` trust flag enforced: a user-trust compile referencing a non-user-allowed capability raises a naming compile error; file/built-in manifests are unrestricted
- [ ] `tool`/`skill`/`hook`/`runtime` capability kinds exist and resolve from the registry
- [ ] `GateHandler` registry implements `human`/`validation`/`approval`/`security`; gates declared per step are evaluated in order at the step boundary (outcome pass|block|wait_human)
- [ ] `Validation_Gate` is real: runs declared validators, blocks on critical policy, emits `validation_warning` on residual non-critical issues
- [ ] `human` gate preserves identical `review_gate_*` event sequences (no snapshot re-baseline)
- [ ] `ToolPermissions` enforced at `factory._build_runner_tools` (binds only granted sets) + `ExecutionPolicy`; effective = intersection(owner, workflow, step); AGENT.md can only lower
- [ ] `html_static`/`html_render` are registered validators; each run/attempt writes a `validation_results` row; a single P0–P3→CRITICAL/HIGH/MEDIUM/LOW mapping function exists
- [ ] Generic fix-loop (deliverable name + `max_attempts` + `FixPolicy` template) replaces the HTML-hardcoded loop; default warn-non-critical / block-critical
- [ ] `spec_plan_coverage`, `task_done_when`, `design_quality` are registered validators that run; `design_quality` is warnings-first/non-blocking; each exercised by ≥1 test manifest
- [ ] F5: `create_deep_agent` is called only inside the `langchain_deepagents` adapter (CHECK gate); banned-pattern + import-linter green
- [ ] F1: `blocks\.append` grep → 0 in `factory.py`; `PromptAssemblyPolicy` drives block order; composed prompts byte-identical for existing agents
- [ ] F2: `_build_runner_tools` grep → 0; tool sets resolve via the `tool_provider` registry; existing agents bind identical tool sets
- [ ] F3: `_inject_skills|_inject_hooks` grep → 0; `skill_provider`/`hook_provider` resolve injection; behavioral hook survives as a non-executable sub-type
- [ ] F4/R12: constitution-injected-in-prod test passes (DB-stored Constitution injected under a running event loop)
- [ ] Executable `HookHandler` fires on lifecycle events; `secret_scan` blocks a secret at `before_write`; `otel_tracing` fires on `*` non-blocking; each firing writes a `hook_runs` row
- [ ] Additive migration adds `validation_results`, `gate_events`, `hook_runs` (each carries `owner_id` + `workspace_id`)
- [ ] `GET /api/capabilities` returns the palette (kind, name, `user_allowed`, config schema) incl. runtimes/skills/hooks/model catalog with required auth + permission scopes
- [ ] Frontend renders the capability palette + per-agent model picker + validator/issue panel from live API data
- [ ] Existing characterization snapshots (prototype/od_/revision/ppt/code-gen) remain byte-identical (deliverables) + semantic event parity; new events additive only
- [ ] Migration-ledger F1–F5 rows flipped to ☑; ledger CI guard + import-linter + banned-pattern gates green

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                                        |
|--------------------|-------|------|--------|--------------------------------------------------------------|
| Goal Clarity       | 0.88  | 0.75 | ✓      | 29 anchored reqs, 4 SCs, F1–F5 deletion gates defined        |
| Boundary Clarity   | 0.86  | 0.70 | ✓      | Frontend scope + impl depth + MCP/integ deferral locked      |
| Constraint Clarity | 0.82  | 0.65 | ✓      | Strict INV-3 (snapshots unchanged); INV-9/12/13; additive    |
| Acceptance Criteria| 0.82  | 0.70 | ✓      | F1–F5 grep/CHECK gates + parity bar = crisp pass/fail        |
| **Ambiguity**      | 0.15  | ≤0.20| ✓      | Plan-authoritative; one focused boundary round closed gaps   |

Status: ✓ = met minimum, ⚠ = below minimum (planner treats as assumption)

## Interview Log

| Round | Perspective     | Question summary                                  | Decision locked                                                                 |
|-------|-----------------|---------------------------------------------------|---------------------------------------------------------------------------------|
| 0     | Researcher      | What exists today (registry/gates/validators/F1–F5)? | Grounded in code: registry seam defers @register/trust to P8; Validation_Gate dead; html_* unbound; F1–F5 all ☐; §18 tables absent |
| 1     | Boundary Keeper | How much of the API-06 frontend is in scope?      | Backend `/api/capabilities` + additive events + data-bearing panels (palette, model picker, validator panel); defer subagent/wave/diff viewers |
| 1     | Simplifier      | Validator + approval/security gate impl depth?    | Real, plan-faithful: Tier#4/5/6 real validators (design_quality warnings-first); approval/security real handlers (security default-denies) |
| 1     | Failure Analyst | Parity bar for existing workflows after migration?| Strict INV-3 — byte-identical deliverables + semantic event parity; existing snapshots unchanged; new events additive only |

> Plan-ingestion note: `specs/003-workflow-engine-decoupling/plan.md` (§6–§9, §16, §18, §22, §30) is the authoritative source; requirements were copied faithfully and the interview targeted only the genuinely-open boundary/scope decisions rather than re-deriving the plan.

---

*Phase: 08-capabilities-hardened-registry-gates-tool-perms-runtime-3*
*Spec created: 2026-06-09*
*Next step: /gsd-discuss-phase 8 — implementation decisions (how to build what's specified above)*
