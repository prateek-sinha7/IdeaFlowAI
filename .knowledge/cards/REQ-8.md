---
id: REQ-8
type: req
status: done
area: [workflow, agents, evals, artifacts, runtime]
summary: >-
  Capability Registry, Gates & Tool Permissions (Phase 3)
source: .planning/REQUIREMENTS.md#capability-registry-gates-tool-permissions-phase
---

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
