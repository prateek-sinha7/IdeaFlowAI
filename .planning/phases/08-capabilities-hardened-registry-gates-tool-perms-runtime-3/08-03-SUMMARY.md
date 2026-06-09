---
phase: 08-capabilities-hardened-registry-gates-tool-perms-runtime-3
plan: 03
subsystem: tool-permissions
tags: [tool-permissions, least-privilege, tool-provider, intersection, execution-policy, factory-lift, hexagonal, F2-deletion]

# Dependency graph
requires:
  - phase: 08-capabilities-hardened-registry-gates-tool-perms-runtime-3
    plan: 01
    provides: "@register/discover() self-registering registry + user_allowed trust flags + the ToolProvider port (base.py)"
  - phase: 04-manifest-compiler-1a
    provides: "ToolPermissions/Step.tools inert §6 fields (plan.py:45-) + the thin no-DSL WorkflowCompiler._compile_step seam"
  - phase: 02-deepagents-migration
    provides: "factory._build_runner_tools closed switch + create_runner + the store-free report_task_complete runner tool"
provides:
  - "Live ToolPermissions intersection: effective = intersect_permissions(owner_allow_list, workflow_ceiling, step_grant) (plan.py)"
  - "ToolPermissions.lowered_by(agent_md): an AGENT.md default may only LOWER a permission, never raise one its step did not grant"
  - "ExecutionPolicy default-deny enforcement point (exec/network/secrets denied; runtime host is Phase 9) (plan.py)"
  - "tool_provider capability registry: four ToolProvider impls (workspace/prototype/prototype_emit_only/planning) each @register('tool', ...)"
  - "factory._resolve_runner_tools — grant-driven tool binding via the registry; _build_runner_tools DELETED (F2 ledger row ☑)"
  - "Compiler resolves Step.tools effective perms via the intersection + strict-key tools: grant block parsing"
affects: [08-05-runtime-prompt-providers, 08-07-hooks, 09-runtime-workspace-localsandbox]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Effective tool perms = AND-mask intersection over owner ∩ workflow ∩ step; a single _and_mask primitive backs both intersect_permissions and lowered_by (neither can raise a permission)"
    - "tool_provider capabilities emit stable custom-tool KEYS (strings), NOT concrete tool objects, so the kernel-side capability package stays import-clean of app.* (import-linter capability ↛ app); the factory (composition root) resolves keys → concrete tools"
    - "exclude_builtin is the AND of every granted set's flag (a set needing the native fs flips it False); empty spec.tools ⇒ pure-text (([], True))"
    - "ExecutionPolicy default-deny seam: privileged runtime actions (exec/network/secrets) denied unless a Phase-9 runtime host explicitly opens them"
    - "Parity-gated deletion (INV-12): build+register → rewire → PROVE parity (5 characterization snapshots + test_create_runner) → DELETE → flip ledger row; deletion only after parity green"

key-files:
  created:
    - "backend/agents/capabilities/tools/__init__.py"
    - "backend/agents/capabilities/tools/providers.py"
    - "backend/tests/agents/test_tool_permissions.py"
  modified:
    - "backend/agents/workflows/plan.py"
    - "backend/agents/workflows/compiler.py"
    - "backend/agents/factory.py"
    - "backend/agents/capabilities/registry.py"
    - "backend/agents/capabilities/base.py"
    - "backend/app/agents/chat_runner.py"
    - "backend/app/agents/tools/runner_tools.py"
    - "backend/tests/agents/test_create_runner.py"
    - "backend/tests/agents/test_registry_capabilities.py"
    - "backend/tests/agents/test_migration_ledger.py"
    - "backend/tests/agents/_resume_child.py"
    - "specs/003-workflow-engine-decoupling/migration-ledger.md"

key-decisions:
  - "A single _and_mask primitive backs BOTH intersect_permissions (owner ∩ workflow ∩ step) and ToolPermissions.lowered_by (effective ∩ agent_md) — a permission is ON only if ON at every level, so AGENT.md can never raise one, only lower it (D-07)"
  - "tool_provider impls emit string KEYS, not concrete tool objects, to satisfy the import-linter (agents.capabilities ↛ app); the factory resolves keys → concrete tools via _resolve_custom_tool_keys (the factory is the composition root, allowed to import app)"
  - "The owner allow-list defaults to the workflow ceiling this phase (DB user manifests are later) — the compiler passes the workflow ceiling for owner_allow_list so the intersection collapses to workflow ∩ step WITHOUT raising any permission"
  - "The four existing tool sets register user_allowed=True (they bind under the default read_files-only posture — none is write/exec privileged, so parity holds and they are safe to expose); a future privileged set would register user_allowed=False"
  - "Added the four tool names to the literal _KNOWN (18→22) in lockstep with the registry drift-guard test (08-02 precedent); the Phase-7 ledger-ratchet test updated to include F2 in the flipped set"

patterns-established:
  - "Pattern: parity-gated capability deletion (INV-12) — prove the routed path byte/event-identical against the 5 characterization snapshots BEFORE deleting the inline original + flipping the ledger row"
  - "Pattern: kernel-side capability emits string keys; the composition-root factory resolves them to concrete app-layer tools (keeps capability ↛ app one-way)"
  - "Pattern: AND-mask intersection as the single least-privilege primitive (intersect + lower share it; neither can raise)"

requirements-completed: [TOOLPERM-01, TOOLPERM-02, TOOLPERM-03, AGENTRT-04]

# Metrics
duration: ~40min
completed: 2026-06-09
---

# Phase 8 Plan 03: Live ToolPermissions Intersection + tool_provider Registry + F2 Deletion Summary

**Made the inert `ToolPermissions` grant set LIVE — effective perms = `intersection(owner_allow_list, workflow_ceiling, step_grant)` with an AGENT.md able only to LOWER — wired the `ExecutionPolicy` default-deny runtime seam (exec/network/secrets), lifted the closed `_build_runner_tools` switch into four registered `tool_provider` capabilities, and DELETED F2 (grep → 0, ledger ☑) after PROVING the routed path binds byte-identical tool sets for every existing agent (5 characterization snapshots + `test_create_runner` green).**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-06-09
- **Tasks:** 3
- **Files modified:** 15 (3 created, 12 modified)

## Accomplishments

- **TOOLPERM-01/02/03 — live intersection (INV-9 least-privilege):** `intersect_permissions(owner, workflow, step)` resolves the effective grant set as the AND-mask of all three levels (a permission is ON only if granted at ALL three), and `ToolPermissions.lowered_by(agent_md)` applies an AGENT.md default that may ONLY LOWER — an AGENT.md declaring `exec=True`/`write_files=True` over an ungranted step is a no-op (stays OFF). A single `_and_mask` primitive backs both, so neither path can ever raise a permission. Defaults are the §8 posture: `read_files` ON; `write_files`/`git`/`spawn_subagents`/`exec`/`network` OFF; `secrets`/`mcp`/`integrations` none. The `mcp`/`integrations` slots are present as default-`none` placeholders (no client this phase).
- **ExecutionPolicy default-deny seam (TOOLPERM / T-08-03-EoP2):** the SECOND D-07 enforcement point — a thin `ExecutionPolicy.check(action, perms)` that DEFAULT-DENIES `exec`/`network`/`secrets` even with no runtime host attached (a step REQUESTING `exec` is denied regardless; the `LocalSandboxRuntime` it gates is Phase 9). Non-privileged actions (`read_files`) are permitted.
- **AGENTRT-04 / F2 — `tool_provider` registry + DELETION:** four `ToolProvider` impls under `agents/capabilities/tools/` (`workspace`/`prototype`/`prototype_emit_only`/`planning`), each `@register("tool", …)` and resolvable via `CapabilityRegistry().resolve("tool", name)` after `discover()`. Each `provide(spec, ctx)` returns the EXACT `(custom_tool_keys, exclude_builtin)` the switch produced. The factory's `create_runner` now binds tools via `_resolve_runner_tools` (resolve providers → map keys to concrete tools → union the granted sets, AND on `exclude`); `_build_runner_tools` is **DELETED** (grep → 0 in `backend/`) and the **F2 ledger row is ☑**.
- **Strict INV-3 parity (the F2 exit gate):** parity was PROVEN before deletion — the 5 characterization snapshots are byte/event-identical and `test_create_runner.py` (one agent of each class binds the identical tool set) is green. The closed switch was replaced, not re-baselined.
- **Compiler wiring:** `_compile_step` now resolves `Step.tools` as the intersection (workflow ceiling ∩ step grant; owner defaults to the ceiling this phase) and parses a step `tools:` grant block with strict-key rejection (INV-5). An un-granted step keeps the default least-privilege `ToolPermissions` — exactly today's binding (parity).

## Task Commits

Each task was committed atomically (TDD where marked):

1. **Task 1: ToolPermissions intersection + ExecutionPolicy seam + mcp/integrations slots** — `297e5f5` (feat, TDD)
2. **Task 2: tool_provider registry binding the granted tool sets (parity)** — `0861337` (feat, TDD)
3. **Task 3: Re-point factory onto the provider registry; PROVE parity; DELETE F2** — `3aa9b8f` (feat)

## Files Created/Modified

- `backend/agents/workflows/plan.py` — `intersect_permissions` + `_and_mask` + `ToolPermissions.lowered_by` (AGENT.md only lowers) + the `ExecutionPolicy` default-deny seam; ToolPermissions docstring upgraded from "INERT" to live (the `mcp`/`integrations` default-none slots were already present from Phase 4).
- `backend/agents/workflows/compiler.py` — `_compile_step` resolves effective `Step.tools` via `intersect_permissions`; `_compile_tool_grant` parses the step `tools:` grant block (strict-key, default least-privilege when omitted); `_ALLOWED_TOOLS_KEYS`.
- `backend/agents/capabilities/tools/{__init__,providers}.py` — the four `tool_provider` impls (emit string keys, import-clean of `app.*`).
- `backend/agents/factory.py` — `_resolve_runner_tools` (registry-driven binding) + `_resolve_custom_tool_keys` (key → concrete tool, factory-side); `_build_runner_tools` **deleted**; `create_runner` rewired.
- `backend/agents/capabilities/registry.py` — the four `("tool", …)` names added to the literal `_KNOWN` (18→22).
- `backend/agents/capabilities/base.py` — reworded the `ToolProvider` port docstring (removed the deleted token literal).
- `backend/app/agents/chat_runner.py`, `backend/app/agents/tools/runner_tools.py`, `backend/tests/agents/_resume_child.py` — reworded prose references to the deleted token (whole-backend F2 grep ratchet).
- `backend/tests/agents/test_tool_permissions.py` — 13 cases: defaults, intersection (all-three-levels), list-slot intersection, AGENT.md lower-only, ExecutionPolicy default-deny (new).
- `backend/tests/agents/test_create_runner.py` — 5 new provider tests (resolution + per-set parity + grant-driven) on top of the 4 byte-identical class-isolation tests.
- `backend/tests/agents/test_registry_capabilities.py` — `_EXPECTED_NAMES` + count drift guard 18→22 (lockstep).
- `backend/tests/agents/test_migration_ledger.py` — the Phase-7 ledger-ratchet test updated to include F2 in the flipped set.
- `specs/003-workflow-engine-decoupling/migration-ledger.md` — F2 row flipped ☐→☑ (`0861337`).

## Decisions Made

- **One `_and_mask` primitive for both intersection and lowering.** A permission is effective only if ON at every level, so `intersect_permissions` (owner ∩ workflow ∩ step) and `lowered_by` (effective ∩ agent_md) are the same AND-mask operation — structurally guaranteeing AGENT.md can never raise, only lower (D-07 / INV-9).
- **Providers emit string keys, not concrete tools.** The import-linter forbids `agents.capabilities → app.*`; `report_task_complete`/`PLANNING_TOOLS` live in/near `app.*`. So the kernel-side providers emit stable keys and the factory (the composition root, allowed to import `app`) resolves them — keeping the hexagonal direction one-way while binding byte-identical sets.
- **Owner allow-list defaults to the workflow ceiling this phase.** DB user manifests / per-owner caps land later; the compiler passes the workflow ceiling for `owner_allow_list`, so the intersection collapses to `workflow ∩ step` without raising anything.
- **The four existing sets register `user_allowed=True`.** They bind only under the default `read_files`-only posture (none is write/exec privileged), so they are safe to expose and parity holds; the structure supports a future privileged set registering `user_allowed=False`.

## Deviations from Plan

None — all three tasks landed with the planned files, acceptance gates, and locked decisions (D-07, TOOLPERM-01/02/03, AGENTRT-04, INV-3/INV-9/INV-12). No deviation-rule auto-fixes were required.

One in-plan design refinement (not a scope/parity deviation): the `tool_provider` impls emit string KEYS rather than concrete tool objects, because importing the concrete `report_task_complete`/`PLANNING_TOOLS` from `agents.capabilities.tools` BROKE the `agents.capabilities ↛ app` import-linter contract (the plan's own constraint: "tool providers in `agents/capabilities/tools/`; no kernel→`app.*`"). The key-based design honors that constraint while binding byte-identical sets; the factory resolves keys → concrete tools. This is the plan-faithful realization of the hexagonal rule, surfaced during Task 2.

## Issues Encountered

- **`agents.capabilities → app.*` import-linter break (Task 2).** The first provider draft imported `report_task_complete`/`PLANNING_TOOLS` directly, breaking the `agents.capabilities must not import the execution kernel or the web layer` contract. Resolved by having providers emit string tool-keys and moving the concrete resolution into the factory (the composition root) — the same hexagonal split the gates use (`ctx.runner` for the writer). All 3 contracts kept.
- **Whole-backend F2 grep ratchet vs. docstring prose (Task 3).** Flipping F2 to ☑ armed the ratchet's `_build_runner_tools` grep over the WHOLE backend, which tripped on nine prose/docstring references to the (now-deleted) function — including a literal I had just written into the ledger-test docstring. Resolved by rewording every prose reference to avoid the bare token (the 08-01 precedent: "Grep-gate literals in docstrings"). The function itself is genuinely deleted (grep → 0); only descriptive prose remained.
- **Phase-7 ledger-ratchet expectation (Task 3).** `test_ledger_parses_and_phase7_flips_all_engine_leaks` hardcoded "F1–F5 stay ☐ — Phase 3". Updated it to include F2 in the flipped set (F1/F3/F4/F5 stay ☐, their owning Phase-3 plans) — a lockstep ratchet update, not a re-baseline.

## User Setup Required

None — no external service configuration required. The `mcp`/`integrations` slots are default-`none` placeholders (no client/servers this phase); the `ExecutionPolicy` gates a runtime host that lands in Phase 9.

## Next Phase Readiness

- **08-05 (runtime/prompt/skill/hook providers):** the `tool_provider` registry + the key→concrete-tool factory-resolution pattern is the template for the skill/hook providers (capability emits descriptors/keys; the factory binds). The `ExecutionPolicy` seam + the live `ToolPermissions` intersection are stable imports.
- **08-07 (hooks):** a hook's `required_permission` can now be checked against the effective `ToolPermissions` intersection; the `ExecutionPolicy` default-deny is the enforcement point for an `exec`-class hook.
- **Phase 9 (runtime/Workspace/LocalSandboxRuntime):** the `ExecutionPolicy` enforcement POINT is wired with a `runtime_host` hook — a Phase-9 host attaches and may `allows(action, perms)` to open a privileged action; until then everything privileged is default-denied.
- All gates green: `test_tool_permissions` (13) + `test_create_runner` (9) + `test_migration_ledger` (F2 ☑) + the 5 characterization snapshots + `test_registry_capabilities` (22) pass; `lint-imports` 3 kept / 0 broken; banned-pattern green; `_build_runner_tools` grep → 0.

## Self-Check: PASSED

- All 3 created files present on disk (`tools/__init__.py`, `tools/providers.py`, `test_tool_permissions.py`) + the SUMMARY.
- All three task commits (`297e5f5`, `0861337`, `3aa9b8f`) present in git history.
- Acceptance gates: `_build_runner_tools` grep → 0 in `backend/`; F2 ledger row ☑; `grep -rc 'register("tool"' tools/` ≥4; tool providers resolve; `lint-imports` 3 kept / 0 broken; banned-pattern green; 50 passed / 1 skipped in a clean-session run of the plan suite (tool_permissions + create_runner + migration_ledger + 5 characterization).

---
*Phase: 08-capabilities-hardened-registry-gates-tool-perms-runtime-3*
*Completed: 2026-06-09*
