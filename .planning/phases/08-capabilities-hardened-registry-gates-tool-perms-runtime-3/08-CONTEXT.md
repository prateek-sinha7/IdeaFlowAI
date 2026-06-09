# Phase 8: Capabilities Hardened — Registry, Gates, Tool Perms, Runtime [3] - Context

**Gathered:** 2026-06-09
**Status:** Ready for planning
**Mode:** Recommended options locked (gray-area question dismissed — user chose "lock all to recommendations", mirroring Phases 1/2/4/5/6/7). Every decision below is the `plan.md`-grounded recommendation (§6–§9/§16/§18/§22/§30/§32). Review/edit this file before planning if any needs changing.

<domain>
## Phase Boundary

Harden the capability layer that Phase 7 proved: turn the Phase-4/7 name-seam + explicit `install()` into a **self-registering `CapabilityRegistry` with per-owner trust flags** spanning the new `tool`/`skill`/`hook`/`runtime` kinds; make gates **first-class registry-driven `GateHandler`s** (`human`/`validation`/`approval`/`security`) with a **real `Validation_Gate`**; enforce **least-privilege `ToolPermissions`** at `factory._build_runner_tools` + `Workspace.ExecutionPolicy`; stand up a **`Validator` registry + generic fix-loop + P0–P3 severity** (migrate `html_static`/`html_render`, land Tier#4/5/6); and **lift the factory's hardcoded prompt-order/tool-switch/skills-hooks/constitution/runtime (F1–F5) into `PromptAssemblyPolicy` + provider registries + `AgentRuntimeAdapter`, deleting F1–F5 and fixing the R12 constitution no-op** — all at **strict INV-3 parity** for every existing workflow.

**Factory-side analog of Phase 7.** Phase 7 deleted the *engine* leaks (L1–L13) behind capabilities; Phase 8 deletes the *factory* leaks (F1–F5) behind adapters/registries/policy. The kernel stays name-agnostic; the new power is registered, trust-flagged, and permissioned — never inline. MCP client + integration providers are **Phase 9** (only the `mcp`/`integrations` permission *slots* land here); `exec`/`network`/`secrets` enablement is **Phase 10/N3** (the `security` gate is registered + default-denies but exec stays OFF); fan-out is **Phase 11** (only the `spawn_subagents` slot, default OFF).

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**16 requirements are locked** (covering all 29 requirement IDs: CAP-01..03, GATE-01..03, TOOLPERM-01..03, VALID-01..05, AGENTRT-01..06, SKILL-01, HOOK-01..04, OBS-02, API-02/03/06). See `08-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `08-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- Self-registering `CapabilityRegistry` (`@register` + `discover()`) + per-owner trust flags (`user_allowed`) + the `tool`/`skill`/`hook`/`runtime` kinds (CAP-01/02/03)
- `GateHandler` registry: `human`/`validation`/`approval`/`security`; a real `Validation_Gate`; human-gate parity (GATE-01/02/03)
- `ToolPermissions` resolution (intersection; AGENT.md may only lower) + enforcement at `factory._build_runner_tools` + `Workspace.ExecutionPolicy` (TOOLPERM-01/02/03)
- `Validator` registry + `DeliverableContext` + generic `FixPolicy` fix-loop + P0–P3→severity mapping; migrate `html_static`/`html_render`; Tier#4/5/6 validators as real validators (VALID-01..05)
- `AgentRuntimeAdapter` (`langchain_deepagents`), `PromptAssemblyPolicy`, `tool_provider`, `skill_provider`, `hook_provider`; **delete F1–F5**; fix R12 (AGENTRT-01..06, SKILL-01)
- Executable `HookHandler` framework + `secret_scan` + `otel_tracing` canonical hooks + `hook_runs` persistence + OTel observability (HOOK-01..04, OBS-02)
- Additive migration: `validation_results`, `gate_events`, `hook_runs` (each `owner_id` + `workspace_id`)
- `GET /api/capabilities` palette + additive run-stream events (`validator_result`/`validation_warning`/`gate_*`) (API-02, API-03)
- Frontend additive panels with live data: capability palette, per-agent model picker, validator/issue panel (API-06, partial)
- The `mcp` and `integrations` tool-permission **slots** (default `none`) — slots only, no client/servers this phase

**Out of scope (from SPEC.md):**
- MCP client + famous-server catalog (MCP-01..04) — Phase 9 / N13 (only the `mcp` slot lands)
- Integration providers (INTEG-01/02) — Phase 9 (only the `integrations` slot lands)
- `RuntimeEnvironment`/`Workspace`/`LocalSandboxRuntime` + repo workflows (RUNTIME/REPO-*) — Phase 9 (the `ExecutionPolicy` enforcement *point* is wired; the local-runtime port impl is Phase 9)
- Enabling `exec`/`network`/`secrets` + constrained-exec profile (EXEC-01/02) — Phase 10/N3 (`security` gate registered + default-denies; exec stays OFF)
- Fan-out / `spawn_subagents` real impl (FANOUT-*) — Phase 11 (only the `spawn_subagents` slot, default OFF)
- Subagent/wave tree + repo-diff frontend viewers — P11/P12/P9 (no backing data)
- Live firing of git-/exec-needing canonical hooks (`pre/post_commit` need `git`=P9; command hooks need `exec`=P10) — registered + permissioned now, only `secret_scan` (read_files) + `otel_tracing` (observability) fire this phase
- Prompt-content changes (constitution consolidation, clarify write-back, recommended-defaults, spec behavior changes) — Q37: separate content PR; only the R12 *bug fix* lands
- `claude_code_cli`/`custom_runner` adapters — designed-for via the port, not built (only `langchain_deepagents`)
- `isolation`/`merge` capability kinds — Phase 11

</spec_lock>

<decisions>
## Implementation Decisions

> SPEC locked the 29-ID WHAT (ambiguity 0.15) + three boundaries (frontend = backend + data-bearing panels; validator/gate depth = real plan-faithful; parity = strict INV-3). Below are the HOW decisions, each **locked to the `plan.md`-grounded recommendation** per the standing project directive ("honor plan.md, nothing dropped" — the same lock-all the user chose for Phases 1/2/4/5/6/7). The four annotated gray areas (Validator↔heavy-dep architecture, validation gate-vs-strategy ownership, self-registration/discovery, F1–F5 sequencing) plus the supporting decisions they imply.

### Area A — Self-registration & discovery (CAP-01/02; evolves Phase 7 D-02)

- **D-01: `@register(kind, name)` decorator + a startup `discover()` that explicitly imports the capability subpackages — replacing (deleting) Phase 7's explicit `install()`/`_register_builtins()`.** The decorator binds `(kind,name)→impl` into the registry at module import; `discover()` imports the known `agents/capabilities/{strategies,deliverables,context_providers,task_parsers,compaction,post_steps,validators,gates,tools,skills,hooks,runtimes}/` packages so registration is deterministic and import-linter-clean (NO `pkgutil`/namespace walk, NO entry-points magic). The registry stays a module-level singleton (capabilities are stateless; per-run state stays on `ExecutionContext`). `_KNOWN` (the compiler's pure-membership INV-4 surface) is regenerated from the registered set (or kept as the validated allow-list the decorator populates) so the compiler path stays impl-free where Phase 4 required it.
  - *Move-don't-copy (INV-12):* `install()`/`_register_builtins()` is **deleted** this phase — `discover()` is its single successor, not a parallel path. This is exactly the evolution Phase 4 D-07 / Phase 6 D-03 / Phase 7 D-02 framed.
  - *Rejected:* keeping `install()` beside `@register` (dual-impl the ledger forbids); `pkgutil.walk_packages` auto-discovery (non-deterministic ordering + can pull unintended modules, harder for the import-linter to reason about).
  - **Researcher directive:** confirm how the compiler's `is_registered`/`_KNOWN` pure-membership path (which `test_registry_capabilities.py` asserts has zero impls bound at compiler import) coexists with import-time `@register` binding — does `discover()` run only at engine import / first `execute()` (never at compiler import), or does `_KNOWN` become a separately-declared allow-list the decorator validates against? Confirm the import-linter contract still permits `agents/capabilities/<kind>/*.py` ↔ registry and forbids kernel→`app.*`.

### Area B — Trust model (CAP-03)

- **D-02: Per-capability `user_allowed: bool` on the registration, validated by the compiler against the manifest's trust context + owner allow-list.** Built-in/file manifests reference any registered capability (unrestricted); user/DB manifests are validated against `user_allowed` + the owner's allow-list — unknown / not-user-allowed / not-owned → a compile error naming the bad reference. This is the seam that keeps `exec`/`secrets`/`spawn_subagents`/powerful-MCP off the user palette (never user-grantable until N3). The trust context is threaded into the compile call (a manifest `source: file|db` / trust flag, defaulting to trusted for the file-backed manifests that exist today so Phase-4/7 parity holds).
  - *Rationale:* §7 trust model; the user-authored-workflow seam (designed-for, not built — DB manifests are Q5/later) needs the flag present now so the palette + compiler are complete.
  - **Researcher directive:** confirm where the compiler currently validates references (Phase 4 `compiler.py` INV-4 path) so the trust check slots in without forking it; confirm the default trust for the existing file manifests keeps Phase-4/7 compile parity (no existing manifest should newly fail).

### Area C — Gate registry + first-class gates (GATE-01/02/03)

- **D-03: `GateHandler` registry; gates declared per step (`gates: [...]`, ordered) and evaluated at the step boundary by the kernel; outcome ∈ `pass | block | wait_human`.** `human` is registered and routes to the existing `engine._run_review_gate` + `review_gate_*` events (semantic parity, no snapshot re-baseline). `validation` runs the step's declared validators + the generic fix-loop (D-06) and blocks per policy, emitting `validation_warning` on residuals. `approval` requires explicit sign-off before a sensitive action (real handler; no sensitive action exists to trigger it until P9/P10, so it is exercised by a test manifest). `security` default-denies `exec`/`network`/`secrets` (which stay OFF this phase) — a step requesting them under a `security` gate blocks. Each gate firing → a `gate_events` row (D-10).
  - *Rationale:* §9 gate registry; the `GateHandler` Protocol port already exists (`capabilities/base.py:105`) — this binds real impls.
  - **Researcher directive:** confirm the exact step-boundary seam in `engine.py` where gates evaluate relative to the Phase-7 `resolve(strategy).run(step,ctx)` dispatch (the existing `_should_gate`/`_run_review_gate` call site) so `human` parity is byte/event-identical and the new gates are additive; confirm the revision post-edit validation (Phase 7's `revision_validation` post-step) is the natural `gates: [validation]` consumer or stays a post_step (see D-06).

### Area D — Validator framework + heavy-dep architecture (VALID-01..05) ⟵ gray area 1

- **D-04: `Validator` impls live in `app/agents/validators/` (a new package), import BOTH the `agents/capabilities/base.py` `Validator` port AND the heavy-dep checks (`app/agents/static_check.py`/`render_check.py`), and self-register via `@register("validator", ...)`; the kernel/`task_loop` reach them through the registry `resolve` + the Phase-7 `KernelServices` runner handle — never a direct kernel→`app.*` import.** This honors §32 ("`static_check`/`render_check` stay in `app/agents/validators/`; heavy deps") while keeping the import-linter kernel→ports direction intact: the capability lives on the `app` side of the boundary (which may import the port), and the kernel only touches the port + the handle. `DeliverableContext` carries path/content/`Workspace`/task-meta and may request browser/compile/test/static-analysis runners (Q22). Severity is internal P0–P3 with one mapping function to CRITICAL/HIGH/MEDIUM/LOW (Q24). Each validator run/attempt → a `validation_results` row (D-10).
  - *Rationale:* the deepest architecture fork — registered Validators must reach Chromium/stdlib checks without the kernel importing `app.*`. Placing the Validator impl on the `app` side (where the heavy deps already live) + reaching it via the handle is the move-don't-copy home §32 names. `html_static` wraps `static_check`; `html_render` wraps `render_check`.
  - **Researcher directive (HIGH — the backbone fork):** confirm (1) whether `app/agents/validators/*.py` self-registering at import is compatible with `discover()` (D-01) — i.e. `discover()` must import the `app/agents/validators/` package too, OR validators register via a separate `app`-side discovery hook the engine triggers; (2) the exact `KernelServices` handle shape Phase 7 exposed (`run_validation_fix_loop`, `static_check`/`render_check` access) so the generic fix-loop (D-06) reaches validators through it; (3) that the import-linter contract permits `app/agents/validators/` to import `agents/capabilities/base` (port) without creating a kernel→app edge.

- **D-05: Tier#4/5/6 ship as real registered validators (Q38).** `spec_plan_coverage` (pre-build analyze), `task_done_when` (per-task acceptance), `design_quality` (tokens/placeholder/a11y, **warnings-first / non-blocking** — emits P2/P3 only). Each is exercised by ≥1 test manifest. Live in `app/agents/validators/` (or `agents/capabilities/validators/` if pure-stdlib with no heavy dep — planner's call per the D-04 boundary).
  - **Researcher directive:** confirm which of the three need heavy deps (→ `app/agents/validators/`) vs pure-stdlib (→ `agents/capabilities/validators/`); confirm `design_quality`'s warnings-first contract maps to P2/P3 so it never blocks.

### Area E — Validation ownership: gate vs strategy (GATE-02 / VALID-02) ⟵ gray area 2

- **D-06: The generic `FixPolicy` fix-loop REPLACES the internals of Phase 7's `KernelServices.run_validation_fix_loop` (behavior-identical, now config-driven: deliverable name + `max_attempts` + fix-prompt template + registered validators), and stays where `task_loop` invokes it. The `validation` gate is the DECLARED step-boundary mechanism for steps that declare `gates: [validation]`.** Existing prototype build-loop validation keeps running inside `task_loop` (at strict INV-3 parity — same events), now driving registered `html_static`/`html_render` + the generic loop instead of the hardcoded one. The `validation` gate is additive: it's how a *non-build* step (e.g. the revision post-edit gate, today the `revision_validation` post_step) declares "run my validators + block on policy." Default policy = warn-non-critical / block-critical, then `validation_warning` with residuals (Q25).
  - *Rationale:* strict INV-3 (SPEC boundary) — moving ALL validation into the gate would risk the build-loop's event parity. The parity-safe split: `task_loop` owns its inline validation (now registry-backed); the `validation` gate is the new declarative entry point. The `revision_validation` post_step (Phase 7 / CR-06) is the candidate to re-express as a `gates: [validation]` step if parity holds — else it stays a post_step.
  - **Researcher directive:** confirm that re-pointing `task_loop`'s validation onto registered validators + the generic fix-loop produces byte/event-identical output to Phase 7's `run_validation_fix_loop` (the 5-pipeline characterization snapshots are the gate); decide (with parity evidence) whether Phase 7's `revision_validation` post_step becomes a `validation` gate or remains a post_step.

### Area F — Tool permissions (TOOLPERM-01/02/03)

- **D-07: `ToolPermissions` (the §6 dataclass: `read_files` ON; `write_files`/`git`/`spawn_subagents` OFF; `exec`/`network` OFF; `secrets`/`mcp`/`integrations` none) resolved as `effective = intersection(owner_allow_list, workflow_ceiling, step_grant)`; an AGENT.md default may only LOWER, never raise. Enforced at (1) `factory._build_runner_tools` (the `tool_provider` registry binds only the granted tool sets) and (2) `Workspace.ExecutionPolicy` (runtime `exec`/`network`/`secrets` gate).** The `mcp`/`integrations` slots are present but default `none` (no client/servers this phase). The `ExecutionPolicy` enforcement *point* is wired now even though the `LocalSandboxRuntime` it gates is Phase 9 — a step requesting `exec` is denied regardless (security default-OFF).
  - *Rationale:* §8/INV-9; enforcement must exist "before brownfield/exec work" so nothing ships over-privileged. F2's deletion (D-08) and the `tool_provider` registry are the binding mechanism.
  - **Researcher directive:** confirm the `ToolPermissions` dataclass + `CompiledWorkflow`/`Step` carry the grant fields (Phase 4 `plan.py` §6 — `Step.tools: ToolPermissions`) or whether they need adding; confirm the owner-allow-list source (per-owner caps from Phase 5 `run_capabilities`/`ScopedStore`) for the intersection; map how `_build_runner_tools`'s current `workspace`/`prototype`/`planning` switch (F2) becomes grant-driven without changing what existing agents bind (parity).

### Area G — F1–F5 factory lift + deletion (AGENTRT-01..06, SKILL-01)

- **D-08: Lift each factory leak behind its declared abstraction and DELETE the inline original in-plan (move-don't-copy, INV-12) — F1–F5 rows flip to ☑.**
  - **F1 → `PromptAssemblyPolicy`:** the hardcoded `blocks.append` order (`factory.py:174-255`, `injects→guardrails→skills→hooks→constitution→prompt_body`) becomes a declared, registry-resolved policy; `blocks\.append` grep → 0; composed prompts byte-identical for existing agents.
  - **F3 → `skill_provider` / `hook_provider`:** inline skills/hooks injection (`factory.py:220-245`) becomes provider capabilities; `skill_provider` (ui · disk · template · repo) gains a provider interface + versioning (SKILL-01); the legacy prompt-only hook survives as a `kind: behavioral` non-executable sub-type (the `## Active Behavioral Hooks` block still renders); `_inject_skills|_inject_hooks` grep → 0.
  - **F4 → constitution sync-safe (R12):** `_inject_constitution`'s event-loop-running branch (reads only `_mem`, `factory.py:282-306`) is fixed via the `PromptAssemblyPolicy` path (sync-safe await / pre-warmed cache) so a Postgres-stored Constitution is injected in production; constitution-injected-in-prod test passes.
  - **F2 → `tool_provider` registry:** the closed `_build_runner_tools` switch (raises on unknown) becomes registry resolution (binds D-07's granted sets); `_build_runner_tools` grep → 0.
  - **F5 → `AgentRuntimeAdapter`:** `create_deep_agent` (`deep_agent_runner.py:240`) is reached only inside the `langchain_deepagents` adapter; `create_runner` selects the runtime via the adapter; CHECK gate: `create_deep_agent` called only in the adapter; banned-pattern + import-linter green.
  - *Coupling note:* F1/F3/F4 all live inside `_compose_system_prompt` — they land together (PromptAssemblyPolicy is the home for the block order, the skill/hook provider outputs, and the constitution block). F2 (tools) and F5 (runtime) are separable.
  - **Researcher directive:** inventory every caller of the F1–F5 sites + their tests (`test_create_runner.py`, `test_guardrails.py`, the prompt-composition tests) so the lift is byte-parity; confirm the constitution sync-safe fix (await-in-running-loop vs pre-warm at run entry) given `create_runner` is sync and called from the async engine; confirm `AgentRuntimeAdapter` wraps (never replaces) `DeepAgentRunner`/`create_deep_agent` (INV-13).

### Area H — Executable hooks + persistence + observability (HOOK-01..04, OBS-02)

- **D-09: `HookHandler` framework binds executable hooks to lifecycle/tool-call events (`before/after_run·step·tool_call·write`, `post_task`, `pre/post_commit`, `on_validation`, `before/after_merge`, or `*`); outcome `continue|warn|block` (blocking halts the offending action); hooks are permissioned (scanner→`read_files`, git→`git`, command→`exec`). This phase's LIVE canonical hooks are `secret_scan` (`before_write`/`pre_commit`, blocking, `read_files`) and `otel_tracing`/logging (`*`, non-blocking → OpenTelemetry spans/logs, OBS-02). Git-/exec-needing hooks (`pre/post_commit` command hooks) are registered + permissioned but do not fire (git=P9, exec=P10). Every firing → a `hook_runs` row (D-10). The legacy prompt-only hook is the `behavioral` non-executable sub-type (shared with D-08/F3).**
  - *Rationale:* §30 / N12; `secret_scan` is the fine-grained complement to the coarse `security` gate (R13); `otel_tracing` delivers the §23 observability. Only the read-only + observability hooks have a firing path before exec/git land.
  - **Researcher directive:** confirm the engine lifecycle points where `before_write`/`post_task`/`before_step` fire today (the runner's tool-call/write events, the engine's step loop) so hooks bind without new events leaking into existing snapshots (blocking-hook halts are additive); confirm the OTel dependency/setup (is there an existing tracer, or does `otel_tracing` need a lib + exporter config).

### Area I — Persistence migration (PERSIST, supports VALID-04/GATE/HOOK-04)

- **D-10: One additive Alembic migration `0016` adds `validation_results`, `gate_events`, and `hook_runs` (§18 columns), each carrying `owner_id` + `workspace_id`, following the Phase-5 additive pattern (latest is `0015`).** No table is altered destructively; indexes per §18 (`validation_results` (run_id, step); `gate_events` (run_id); `hook_runs` (run_id)). Writes go through the Phase-5 `ScopedStore` (default-deny, owner-scoped).
  - **Researcher directive:** confirm the `0015`→`0016` head chain + the Phase-5 model/`ScopedStore` pattern (where `artifact_refs`/`run_events` models live) so the three new models + scoped writers mirror it; confirm `owner_id`/`workspace_id` are sourced from `ExecutionContext` at write time (Phase 5 wiring).

### Area J — API + frontend (API-02/03/06)

- **D-11: `GET /api/capabilities` returns the registry palette (kind, name, `user_allowed`, config schema) incl. runtimes/skills/hooks/model catalog with required auth + permission scopes (§22); the run stream emits the new `validator_result`/`validation_warning`/`gate_*` events additively (existing workflows at semantic parity); the frontend adds the data-bearing panels only — capability palette, per-agent model picker, validator/issue panel — reusing app-builder patterns where they fit. Subagent/wave tree + repo-diff viewer are deferred (no backing data until P9/11/12).** Built on the Phase-4 `/api/workflows[/{id}]` + `/api/runs` foundation in `backend/app/api/`.
  - **Researcher directive:** confirm the auth/permission-scope decoration pattern on existing endpoints (`workflows.py`/`runs.py`) so `/api/capabilities` matches; identify the frontend composer + per-agent surfaces (`frontend/src/components/workflow/`, `library/`, `results/`) the three panels extend (reuse, not rebuild); confirm the WS event vocabulary addition is additive in `websocket.py` (no existing event renamed/removed).

### Area K — Plan sequencing / strangler safety (the 8 sketched plans) ⟵ gray area 4

- **D-12: Follow the ROADMAP's 8-plan split in strangler dependency order; each F# is wrapped→rewired→deleted within its plan (deletion is the exit gate), mirroring Phase 7 D-05.** (1) **08-01** `CapabilityRegistry` `@register`/`discover()` + trust flags + the new kinds (foundation everything registers into; delete `install()`). (2) **08-02** `GateHandler` registry + real `Validation_Gate` (human parity). (3) **08-03** `ToolPermissions` resolution + enforcement (delete F2 switch). (4) **08-04** `Validator` registry + generic fix-loop + severity + migrate `html_static`/`html_render` + re-point `task_loop`'s validation (parity gate). (5) **08-05** `AgentRuntimeAdapter` + `PromptAssemblyPolicy` + `skill_provider`/`hook_provider` (delete F1/F3/F5). (6) **08-06** constitution sync-safe (delete F4/R12). (7) **08-07** executable `HookHandler` + `secret_scan` + `otel_tracing` + `hook_runs`. (8) **08-08** `/api/capabilities` + the three frontend panels. The `0016` migration (D-10) lands with the first plan that writes its rows (08-02 gate_events / 08-04 validation_results / 08-07 hook_runs) — planner may front-load all three columns in one early migration.
  - *Rationale:* registry self-registration (08-01) is the substrate gates/perms/validators/providers register into; the factory deletions (08-05/06) depend on the providers + policy existing; each plan leaves the 0A/0C/Phase-7 characterization suites green (the deletion plans are pure removal of now-unreachable inline code).
  - **Critical sequencing constraint:** F1–F5 inline code is deleted only AFTER its abstraction is proven at parity (the routed path produces identical output) — never before. The 5-pipeline characterization snapshots gate every deletion.

### Claude's Discretion
- The exact `@register` signature + whether `_KNOWN` is decorator-populated or a separate declared allow-list (D-01) — provided the compiler's impl-free membership path is preserved.
- Where `discover()` is invoked (engine import vs first `execute()`) and how `app/agents/validators/` self-registration is triggered relative to it (D-01/D-04).
- Whether the `validation` gate subsumes Phase 7's `revision_validation` post_step or they coexist (D-06) — decided by parity evidence.
- `PromptAssemblyPolicy` shape (dataclass with `order: list[str]` per §6 vs a richer policy object) and whether it's a registered capability or a config object on the compiled workflow (D-08/F1).
- Single `0016` migration vs per-table migrations (D-10) — single is the recommendation.
- Tier#4/5/6 validator placement (`app/agents/validators/` vs `agents/capabilities/validators/`) per the heavy-dep boundary (D-05).
- Frontend panel composition — extend existing composer components vs new sibling panels (D-11).
- Plan-task granularity within the 8-plan frame (D-12) — e.g. whether trust flags (08-01) split from self-registration, or the migration is its own plan.

### Folded Items (carried forward from Phase 7 — opportunistic, NOT locked SPEC scope)
- **Test-isolation hygiene (07 `deferred-items.md`):** `tests/agents/test_strategies.py` mutates the process-global capability registry (`registry_mod.install()` + `_IMPLS[...]`) and its `finally` only pops one key, polluting the characterization snapshots when run in the same session. Phase 8 reworks exactly this registry (D-01) — fold the fix (an autouse registry save/restore reset fixture, or full `_IMPLS` snapshot/restore) into the 08-01 registry work. Natural, low-cost, and prevents the self-registration rework from inheriting the bug.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked requirements (read FIRST)
- `.planning/phases/08-capabilities-hardened-registry-gates-tool-perms-runtime-3/08-SPEC.md` — the 16 locked requirements (29 IDs), boundaries, 20 acceptance criteria. **Locked requirements — MUST read before planning.**

### The specification (authoritative — `specs/003-workflow-engine-decoupling/plan.md`)
- **§6 (lines ~324–522)** — Core abstractions: `AgentRuntimeAdapter` (line 497), `PromptAssemblyPolicy` (line 502), `HookHandler` (line 506), `ToolPermissions` (line 434), `GateHandler` (line 421), `Step.tools`/`Step.gates`/`Step.model`. The contracts F1–F5 + gates + tool-perms lift behind.
- **§7 (lines 524–533)** — Capability registry & trust model: `(kind,name)` keying for all kinds incl. runtimes/skills/hooks/tools; engineer-registered, manifests reference by name; `user_allowed` + owner allow-list trust seam (D-01/D-02).
- **§8 (lines 535–556)** — Tool permission policy & least-privilege: the grant table + defaults, `effective = intersection(...)`, AGENT.md may only lower, the two enforcement points (`_build_runner_tools` + `Workspace.ExecutionPolicy`) (D-07).
- **§9 (lines 558–570)** — Gate registry: `human`/`validation`/`approval`/`security`, evaluated at the step boundary, outcome pass|block|wait_human; `validation` makes the dead `Validation_Gate` real (D-03/D-06).
- **§16 (lines 677–686)** — Validation framework & severity: `Validator` registry + `DeliverableContext`, generic fix-loop from `FixPolicy`, P0–P3→CRITICAL/HIGH/MEDIUM/LOW, Tier#4/5/6 (`spec_plan_coverage`/`task_done_when`/`design_quality`) (D-04/D-05/D-06).
- **§18 (lines 697–717)** — Persistence schema: `validation_results`, `gate_events`, `hook_runs` columns (+ `run_capabilities` already landed Phase 5); additive, every table carries `owner_id`+`workspace_id` (D-10).
- **§22 (lines 755–771)** — API/frontend contract: `GET /api/capabilities` palette + the new run-stream events + "existing workflows at semantic parity, all new panels additive" (D-11).
- **§30 (lines 921–988)** — Agent runtime/skills/hooks/MCP/integrations capability layer: the current-state table (F1–F5 grounded in code), the 6 expected changes (items 1/2/4 = Phase 3; item 3 MCP + integration_provider = Phase 9), executable hooks (N12), the constitution no-op (R12) (D-08/D-09).
- **§31 (lines 989–1024) + `migration-ledger.md`** — F1–F5 rows (legacy `file:line` → new home → grep/CHECK gate); wrap→rewire→delete; deletion-is-DoD. The exact F1–F5 patterns to flip to ☑ (D-08/D-12).
- **§32 (lines 1027–1098)** — Target directory structure & Ports & Adapters patterns: self-registering capabilities (`@register`/`discover()`), `static_check`/`render_check` stay in `app/agents/validators/`, import-linter direction (D-01/D-04).
- **Q21–Q25 (lines 116–129)** — validator registry/interface/fix-loop/severity/policy; **Q38 (lines 183–184)** — Tier#4/5/6 as framework validators+gates; **Q24 (line 126)** — P0–P3→severity; **N12/N13 (lines ~876–877)** — executable hooks decided / MCP-client decided (Phase 9).

### Project planning
- `.planning/REQUIREMENTS.md` — CAP/GATE/TOOLPERM/VALID/AGENTRT/SKILL/HOOK/OBS/API IDs (lines 80–99, 156, 162–166) with plan anchors; the Phase 8 traceability rows (233–241).
- `.planning/ROADMAP.md` § Phase 8 — goal, the 4 success criteria, the 08-01…08-08 candidate plan breakdown (D-12).
- `.planning/PROJECT.md` — invariants (INV-1/3/9/12/13); the §30/§31 factory-leak note (F1–F5, R12); the "deferred → Phase 8: WR-02/03/05 + test-isolation hygiene" line (143); "nothing from plan.md dropped".
- `.planning/STATE.md` — Phase 7 closure decisions (07-05/07-10/07-11) the capabilities Phase 8 hardens build on.

### Prior phase context (the evolution this phase completes)
- `.planning/phases/07-prototype-as-manifest-parity-proof-sc-001-2/07-CONTEXT.md` — D-02 (the explicit `install()`/`resolve()` seam Phase 8 evolves to `@register`/`discover()`); the `KernelServices` runner-handle pattern (D-03) the Validators + fix-loop reach through; the §32 layout (D-01); the Phase-7 `<deferred>` list — **every item there ("Self-registration + trust", "Formal Validator registry + generic fix-loop + severity + Tier#4/5/6 + migrate html_static/html_render", "Formal GateHandler + Validation_Gate real", "PromptAssemblyPolicy/AgentRuntimeAdapter/ToolPermissions/F1–F5") is Phase 8 scope**.
- `.planning/phases/07-…/07-SPEC.md` — the Phase-7 boundary that explicitly scoped these out of 7 and into 8.
- `.planning/phases/07-…/deferred-items.md` — the test-isolation pollution detail (D-12 fold) + the (out-of-scope) logout/cancel/`live_harness.store` failures.
- `.planning/phases/07-…/07-REVIEW.md` + commit `20be07c` — WR-02/03/05 (code-review findings marked deferred to Phase 8; latent, not goal-blocking — triage during the validator/parity work, see `<deferred>`).
- `.planning/phases/05-typed-artifacts-persistence-ownership-1b/05-CONTEXT.md` — the additive-migration + `ScopedStore` (default-deny, owner/workspace-scoped) pattern D-10 mirrors.
- `.planning/phases/04-manifest-compiler-1a/04-CONTEXT.md` — D-07 (name-only registry → the trust/self-reg evolution); the compiler INV-4 validation path D-02 extends.

### Code to read (targets / assets)
- `backend/agents/factory.py` (446 lines) — **F1** `_compose_system_prompt` `blocks.append` order (:174-255); **F3** inline skills (:220-225) + hooks (:226-245); **F4** `_inject_constitution` async no-op (:258-306, the `_mem`-only running-loop branch :282-292 = R12); **F2** `_build_runner_tools` closed switch (:384-446). `create_runner` (:69) is the entry the `AgentRuntimeAdapter` + policy reshape.
- `backend/app/agents/deep_agent_runner.py:240` — **F5** `create_deep_agent` hardcoded; the `AgentRuntimeAdapter` wraps it (INV-13 — wrap, never replace).
- `backend/agents/capabilities/registry.py` (192 lines) — `CapabilityRegistry` + `_KNOWN` (16 pairs) + `install()`/`_register_builtins()` (the explicit binding D-01 deletes) + `resolve`/`is_registered`/`resolve_alias`. The docstring states `@register`/`discover()` + trust flags are THIS phase.
- `backend/agents/capabilities/base.py` (112 lines) — the Protocol ports; `GateHandler` (:105) + `Validator` (:54) get real impls; new ports needed for `tool`/`skill`/`hook`/`runtime` kinds + `PromptAssemblyPolicy`/`AgentRuntimeAdapter`/`HookHandler`.
- `backend/app/agents/static_check.py` + `render_check.py` — wrapped as `html_static`/`html_render` registered Validators (D-04); stay in `app/agents/` (heavy deps) — new package `app/agents/validators/`.
- `backend/agents/capabilities/strategies/task_loop.py` — the Phase-7 strategy whose inline validation re-points onto registered validators + the generic fix-loop (D-06); `run_validation_fix_loop` (via `KernelServices`) is the home the generic loop replaces.
- `backend/agents/capabilities/post_steps/revision_validation.py` — Phase 7's revision post-edit validation; the candidate to re-express as a `gates: [validation]` step (D-06) if parity holds.
- `backend/agents/execution_engine/engine.py` — `_run_review_gate` (:2043) + `review_gate_*` (the `human` gate parity, D-03); `_should_gate`; the Phase-7 `resolve(strategy).run(step,ctx)` step-dispatch seam where gates evaluate.
- `backend/agents/execution_engine/kernel_services.py` — the `KernelServices` handle Validators + the fix-loop reach through (D-04/D-06; kernel must not import `app.*`).
- `backend/agents/loader.py:355` — `Validation_Gate` accepted in the AGENT.md schema but never implemented (made real, D-03); `gate` field (:101).
- `backend/agents/workflows/plan.py` — `Step.tools`/`Step.gates`/`Step.model`, `ToolPermissions`, `CompiledWorkflow` (confirm the §6 grant/gate fields are present or add them, D-07/D-03).
- `backend/agents/workflows/compiler.py` — the INV-4 capability-reference validation the trust check extends (D-02).
- `backend/alembic/versions/0015_drop_thin_artifact_store.py` (+ `0014`/`0011`) — the migration head + Phase-5 additive pattern `0016` follows (D-10).
- `backend/app/api/workflows.py` · `runs.py` · `websocket.py` — the Phase-4 `/api/workflows`+`/api/runs` foundation `/api/capabilities` joins; the WS event vocabulary the new `validator_result`/`validation_warning`/`gate_*` events extend additively (D-11).
- `frontend/src/components/{workflow,library,results,preview}/` — the composer/run surfaces the capability palette + per-agent model picker + validator/issue panel extend (reuse, D-11).
- `backend/tests/agents/test_characterization_*.py` + the 5-pipeline deliverable/event snapshots — the strict-INV-3 parity gate every plan (esp. the deletions + validation re-point) must keep green.
- `backend/tests/agents/test_migration_ledger.py` + `test_banned_patterns.py` — the F1–F5 ratchet + INV-13/import-linter gates (flip F1–F5 to ☑).
- `backend/tests/agents/test_strategies.py` — the registry-global mutation that needs the autouse reset fixture (D-12 fold).
- `backend/CLAUDE.md` — engine = deterministic sequencer; `_compose_system_prompt` injection order; tool-set mapping; commit scopes (`factory`/`runner`/`registry`/`engine`/`tests`); dev runtime `python3.11`, no venv; PR off `feature/003-workflow-engine-decoupling`, never `main`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`agents/capabilities/registry.py`** — `CapabilityRegistry` + `_KNOWN` + `install()`/`resolve()`/`is_registered()`/`resolve_alias()`: the exact seam D-01 evolves to `@register`/`discover()` + `user_allowed` (the docstring already names Phase 8 as the owner).
- **`agents/capabilities/base.py`** — `GateHandler` + `Validator` Protocol ports already authored; D-03/D-04 bind real impls. New ports (`tool`/`skill`/`hook`/`runtime`, `PromptAssemblyPolicy`, `AgentRuntimeAdapter`, `HookHandler`) follow the same one-method-Protocol idiom.
- **Phase-7 `KernelServices` runner handle on `ExecutionContext`** (typed `object`, import-pure) — the established way capabilities reach kernel/`app.*` primitives; Validators + the generic fix-loop (D-04/D-06) reach `static_check`/`render_check`/`run_validation_fix_loop` through it without a kernel→app edge.
- **`engine._run_review_gate` + `review_gate_*` events** — the working `human` gate D-03 registers behind the `GateHandler` registry at event parity.
- **`app/agents/static_check.py` + `render_check.py`** — the heavy-dep checks `html_static`/`html_render` wrap (D-04); already called by Phase-7 `task_loop`.
- **Phase-5 `ScopedStore` + additive-migration pattern (`0014`/`0015`)** — D-10's `0016` (validation_results/gate_events/hook_runs) + scoped writers mirror it; `owner_id`/`workspace_id` sourced from `ExecutionContext`.
- **Phase-4 `/api/workflows[/{id}]` + `/api/runs`** — the API foundation `/api/capabilities` (D-11) extends; the WS event contract the new events join additively.
- **`agents/capabilities/strategies/task_loop.py` + `post_steps/revision_validation.py`** — Phase-7 homes the Validator framework + `validation` gate re-point onto (D-06).

### Established Patterns
- **Evolution, not dual-impl (Phase 4 D-07 / 6 D-03 / 7 D-02)** — explicit `install()` → `@register`/`discover()`; name-only registry → trust-flagged. D-01/D-02 are the final step of this arc; `install()` is **deleted** (INV-12), not kept beside `discover()`.
- **Move-don't-copy + deletion-is-exit-gate (INV-12 / §31)** — F1–F5 inline code is deleted in-plan once its abstraction is proven at parity; the ledger grep/CHECK ratchet + import-linter + banned-pattern gates enforce it (D-08/D-12).
- **Ports & Adapters / import-linter direction** — kernel imports only `capabilities.base` ports + the resolve seam + the `KernelServices` handle; heavy-dep capabilities (Validators) live on the `app` side, reached via the handle, never a kernel→`app.*` import (D-04).
- **Strict INV-3 parity (SPEC boundary)** — existing-workflow deliverables byte-identical + semantic event parity; the 5-pipeline characterization snapshots stay UNCHANGED; new validator/gate/hook events are additive only. Every deletion + the `task_loop` validation re-point gates on these snapshots.
- **Least-privilege default-OFF (INV-9)** — `read_files` ON; everything else OFF/none; AGENT.md only lowers; the `security` gate + `ExecutionPolicy` enforce even though exec/runtime land later (D-03/D-07).
- **Dev runtime** — `python3.11`, no venv; `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v`; commit scopes per `backend/CLAUDE.md`; PR off `feature/003-workflow-engine-decoupling`, never `main`.

### Integration Points
- **Net-new:** `@register`/`discover()` + trust in `capabilities/registry.py`; new ports in `capabilities/base.py`; `app/agents/validators/` package (Validator impls + Tier#4/5/6); `PromptAssemblyPolicy`/`tool_provider`/`skill_provider`/`hook_provider`/`AgentRuntimeAdapter` + `HookHandler` framework; `GET /api/capabilities`; Alembic `0016`; the three frontend panels.
- **Grows:** `factory.py` (F1–F4 → policy/providers); `deep_agent_runner.py` (F5 → adapter); `engine.py` (gate registry at the step boundary; hook firing points); `task_loop.py` (validation → registered validators + generic fix-loop); `plan.py`/`compiler.py` (tool-perm grants + trust check); `websocket.py` (additive events).
- **Shrinks → deleted:** F1 (`blocks.append`), F2 (`_build_runner_tools` switch), F3 (`_inject_skills`/`_inject_hooks`), F4 (constitution no-op), F5 (hardcoded `create_deep_agent`); `registry.install()`.
- **CI gates that constrain the work:** the 5-pipeline characterization snapshots (strict INV-3), migration-ledger ratchet (flip F1–F5; don't regress L1–L16), import-linter (kernel→ports; no kernel→app), banned-pattern (INV-1 + INV-13 deepagents-only + F5 CHECK).

</code_context>

<specifics>
## Specific Ideas

- **Standing project directive (init):** "everything from plan.md must be honored — nothing dropped." Every lock above takes the plan-faithful option (§32 self-registration; §7 trust; §8 intersection perms; §9 gate registry; §16 validator framework; §30 F1–F5 lift + executable hooks; §18 additive tables).
- **Mode:** the user dismissed the per-area gray-area question (mirrors Phases 1/2/4/5/6/7 "lock all to recommendations"). Treat D-01..D-12 as locked unless this file is edited before planning.
- **The deepest research risk (D-04):** the Validator↔heavy-dep architecture — how registered `html_static`/`html_render`/Tier-validators reach `static_check`/`render_check` (and the `task_loop` fix-loop reaches the registry) without the kernel importing `app.*`. Placing Validator impls in `app/agents/validators/` + reaching them via the `KernelServices` handle is the recommendation; the researcher must confirm `discover()` ↔ `app`-side self-registration and the import-linter contract.
- **The strictest constraint (SPEC boundary):** strict INV-3 — the existing characterization snapshots are UNCHANGED. The two riskiest changes for parity are (a) re-pointing `task_loop`'s validation onto registered validators + the generic fix-loop (D-06) and (b) the F1/F3/F4 prompt-assembly lift (D-08). Both must produce byte/event-identical output; the snapshots gate them.
- **Parity trap (F4/R12):** fixing the constitution no-op is a *behavior change in production* (a previously-silently-dropped Constitution now injects) — but the existing characterization runs have NO Constitution set, so snapshots stay byte-identical. The constitution-injected-in-prod test is a NEW test, not a snapshot re-baseline.

## Deferred-but-adjacent (planner triage, NOT locked scope)
- **WR-02/03/05** (Phase-7 `07-REVIEW.md`, deferred via commit `20be07c` — "latent, not goal-blocking → Phase 8"): triage these during the validator-migration/parity work; fold only if they touch the migrated validators / prompt-assembly and stay within strict INV-3. Do NOT expand the locked SPEC scope to chase them.

</specifics>

<deferred>
## Deferred Ideas

- **MCP client + allow-listed famous-server catalog + `McpCapabilityRegistry` (MCP-01..04)** — Phase 9 / N13. Only the `mcp` tool-permission slot (default none) lands in Phase 8 (D-07).
- **Integration providers (gitlab/github/jira/slack — INTEG-01/02)** — Phase 9. Only the `integrations` slot (default none) lands now.
- **`RuntimeEnvironment`/`Workspace`/`LocalSandboxRuntime` + repo inventory/index/context-pack + `repo_diff` (RUNTIME/REPO-*)** — Phase 9. Phase 8 wires the `ExecutionPolicy` enforcement *point* only.
- **Constrained `exec` profile + compile/test/lint validators (EXEC-01/02)** — Phase 10 / N3. The `security` gate is registered + default-denies; exec stays OFF.
- **Fan-out / `spawn_subagents` real impl + `IsolationProvider`/`MergeStrategy`/`BudgetManager` (FANOUT-*) + `isolation`/`merge` capability kinds** — Phase 11. Only the `spawn_subagents` permission slot (default OFF) lands now.
- **Wave scheduler + durable resume (WAVE-*/RESUME-*)** — Phase 12.
- **Subagent/wave tree + repo-diff frontend viewers (part of API-06)** — P9/11/12 (no backing data until then). Phase 8 ships only the capability palette + per-agent model picker + validator/issue panel.
- **Prompt-content changes** (constitution consolidation, clarify write-back, recommended-defaults, spec behavior changes — Q37) — a separate content PR after decoupling. Phase 8 lands only the R12 no-op *bug fix*, not content edits.
- **`claude_code_cli` / `custom_runner` runtime adapters** — designed-for via `AgentRuntimeAdapter`, built later. Phase 8 ships only `langchain_deepagents` (INV-13).
- **Out-of-scope Phase-7 deferred failures** (07 `deferred-items.md`): `tests/unit/test_logout.py`/`test_pipeline_cancel.py` (auth/cancel subsystems, untouched) + `tests/agents/live_harness.py` `_store.store` snapshot (a 05-07 follow-up: repoint to the typed `ScopedStore`). NOT Phase 8 scope — surfaced for separate triage. (The test-isolation pollution item IS folded — see `<decisions>` Folded Items.)

### Reviewed Todos (not folded)
None — `todo.match-phase 8` returned 0 matches.

</deferred>

---

*Phase: 8-capabilities-hardened-registry-gates-tool-perms-runtime-3*
*Context gathered: 2026-06-09*
