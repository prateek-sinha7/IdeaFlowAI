# The AGENT.md vs workflow.yaml configuration split

Audit of which execution concerns are declared on the agent
(`agents/prompts/<id>/AGENT.md`) versus on the workflow
(`agents/workflows/<id>/workflow.yaml`), and what that costs.

Seeded from three known leaks (`depends_on`, `produces`/`consumes`, `context_from`);
everything else here was found by the audit.

> **Verdict: not yet decided.** None of this report's 8 ranked recommendations have been
> formalized as a decision — including #7 (move `produces`/`consumes` toward the step),
> which `dag-ownership.md` covers in full and which is also undecided. See `../ADR.md`'s
> Open questions.

## The pattern in one line

Anything declared on the **agent** is identical for every workflow that agent appears in. Anything declared on the **step** can differ per workflow. Most execution config is on the agent.

## Verdict

The split is bad and getting worse. The three seeded leaks are real, but they are the *smallest* problems.

The worst offender is **`order`**: it drives `PIPELINE_AGENTS` membership and sort at import time and is treated across `.planning/` history as load-bearing (*"the membership assertion... MUST NOT BREAK"*, cited in six-plus phase plans through Phase 51) — but `engine.py:1473-1491` has removed that assertion. Execution order now comes entirely from `compiled.steps`; `AgentSpec.order`/`PIPELINE_AGENTS` order is dead for execution and alive only for `/api/agents` listing and `get_all_agents_flat`. `backend/CLAUDE.md` and `.planning/IMPLEMENTATION-REGISTER.md` still describe the assertion as existing — the docs are stale, not just the schema.

Runner-up: **`tools:` is a name collision, not a duplication.** `AgentSpec.tools` (tool-set names like `"workspace"`) fully controls fs-tool binding via `_resolve_runner_tools`, while the identically-named step `tools:` (a `ToolPermissions` grant block) is documented as "does NOT yet read step.tools" and is authored only in 5 non-product `sample_*` manifests. Anyone reading `tools:` in a workflow.yaml would reasonably assume it affects tool binding. It does not.

## Inventory

| Field | Lives in | Should live in | Read at | Usage | Can vary per workflow? | Breaks template instances? | Severity |
|---|---|---|---|---|---|---|---|
| `order` | AGENT.md | manifest step position | `loader.py:184-238` (`list_agent_ids` sort); real order from `engine.py:1491` | 88/88 required | No | N/A (template excluded) | **Critical** — docs claim an enforcement that no longer exists |
| `pipeline_type` | AGENT.md | manifest | `loader.py:307` (shape only); `registry.py:62-90` bucketing | 88/88 required | No — exactly one value | Meaningless: `custom-agent` declares `custom`, irrelevant to the N manifests instantiating it | High |
| `tools` (AGENT.md) | AGENT.md | fine for the *set name*, collides with step `tools:` | `factory.py:966-1057`, reads ONLY `spec.tools` | 26/88 | No | Identical across instances | High (collision) |
| `tools` (step) | workflow.yaml step | — (dead / demo-only) | `compiler.py:1076-1109`; `plan.py:45-73`; NOT consulted by `_resolve_runner_tools` (`factory.py:979`) | 7/86 steps, all `sample_*` | Structurally yes — but doesn't gate the runtime tool set | N/A | High |
| `gate` (AGENT.md) | AGENT.md | manifest step | `engine.py:4916-4933` (`_should_gate`) | 5/88 | No | Identical for every instance | High |
| `gates` (step) | workflow.yaml step | correct, but overlaps `gate` | `engine.py:2412-2433` | 4/86 steps | Yes | N/A | Medium |
| `max_tokens` | AGENT.md | nowhere (dead) | `app/core/config.py:161-170`; `factory.py:309-310` explicitly NOT passed; `model_factory.py:36-37` always wins | 88/88 required, inert | N/A | N/A | Medium |
| `guardrails` | AGENT.md | fine as identity, but no workflow override | `factory.py:451` | 37/88 | No | A template used for two jobs gets the same guardrails for both | Medium |
| `injects` (AGENT.md) | AGENT.md | correctly UNION-merged with step `injects` | `factory.py:433-445` | 6/88; step `injects` 0/86 | **Yes** — additive merge | N/A | Low — the one field that gets this right |
| `context_from` | AGENT.md | nowhere (dead) | `loader.py:69,356` — parsed, stored, never read | 57/88 | N/A | N/A | Low |
| `produces` / `consumes` | AGENT.md | manifest (per-edge) | `_filter_consumed_outputs` / `_latest_typed_content`; `WorkflowResolver` | produces 80/88, consumes 56/88 | No | Meaningless for `custom-agent`; routing goes via instance-id artifact naming (`engine.py:3190-3233`) instead | High |
| `depends_on` | manifest step | manifest | `compiler.py:857,1275-1297` | 0/86 authored; compiler-synthesized only | Yes | N/A | Low |
| `role`/`description`/`icon`/`estimated_duration` | AGENT.md | fine — presentation | never read by the execution path | icon 86/88, description 84/88 | No, doesn't need to | Identical but harmless | Low |
| `model` (AGENT.md) | AGENT.md | tier-3 default, correctly below step/workflow | `agents/model_policy.py`, D-02 precedence | 0/88 set it | Yes — step overrides | N/A | Low |
| `skills` (step) | workflow.yaml step | correct — per-instance | `factory.py:88-95,130` | 1/86 steps | Yes | N/A — spec-012's fix for this exact problem | Low |

## Dual-declaration conflicts

**1. `gate` (AGENT.md) vs `gates` (step).** Both feed the same human-review pause via different mechanisms. `_should_gate(spec, ectx)` (`engine.py:4916-4933`) decides whether the *inline* legacy review gate fires, keyed on `spec.gate == "Human_Gate"` or the per-run `gate_agent_ids` override. Separately `_evaluate_gates(step, ...)` (`engine.py:2412-2433`) evaluates the step's declared gate names.

**Precedence is explicit, not accidental**: the pre-step call passes `inline_gated=self._should_gate(spec, ectx)` and the comment states *"the inline gate wins... the declared `human` gate is skipped for this step only"* (`engine.py:2424-2433`). AGENT.md wins for `human`; `security`/`approval`/`Validation_Gate` have no dedupe and are additive.

**Consequence:** a workflow cannot turn a gate *off* for an agent that declares one.

**2. `tools` vs `tools`.** Not "both read" — a name collision that looks like duplication. `_resolve_runner_tools(spec, ctx)` (`factory.py:966-1057`) resolves `spec.tools` (tool-SET names) into bound tools and the `exclude_builtin` flag; its docstring says *"This function does NOT yet read `step.tools` / intersect any `ToolPermissions`"* (`:979-980`). `step.tools` is consumed only in the fanout/exec/MCP/`spawn_subagents` privilege checks (`compiler.py:753-826`). Two fields, same name, disjoint concerns.

**3. `model` × 3 sites.** AGENT.md, step, workflow top-level — resolved by `ModelResolver` with documented D-02 precedence `override > step.model > AgentSpec.model > workflow.model > session model_id or Haiku` (`engine.py:1716-1736`). A legitimately layered override system, not a leak. Currently moot: 0/88 agents and 0/18 manifests declare it.

**4. The EMP-01 selections overlay** (`engine.py:6805-6825`) adds a fourth site for composed/`custom` workflows: `_apply_selections` merges user selections onto the compiled step — additive dedup-union for `validators`/`gates`/`injects`, override for `model`/`retry`. Legitimate and well-scoped.

## Blockers to one agent in two workflows

- **Structural**: `pipeline_type` is a single required string (`loader.py:61,307`), and `list_agent_ids`/`_discover_pipeline_agents` (`registry.py:62-90`) bucket every agent into exactly one `PIPELINE_AGENTS[pt]`. An agent's `produces`/`consumes`/`gate`/`guardrails`/`tools`/`order` are fixed at authoring time for one pipeline.

- **Verified empirically**: no non-template agent is referenced from a `workflow.yaml` whose id differs from its declared `pipeline_type` — all 18 manifests checked including nested `subagents.steps`, zero mismatches. The split has not bitten only because nobody has tried it.

- **The designed exception is `custom-agent`** (`template: true`), which sidesteps the problem by carrying almost no agent-level config and pushing every instance-varying concern to the step (`instance_id`, `display_name`, `prompt`, `skills` — `plan.py:386-392`).

- **`allowed_custom_agent_ids("custom")` already unions agents across pipelines** for the composer (`registry.py:312-335`) — the platform is one step from letting a user compose e.g. `story-estimator` (pipeline_type `user_stories`) into a prototype-flavored custom run, at which point its fixed `guardrails`/`produces`/`consumes` would be wrong. The registry comment calls this "OPEN BY DESIGN."

## What this means for custom-agent template instances

For N instances `custom-agent:<id1>`, `custom-agent:<id2>`, …:

- `name`, `role`, `icon`, `estimated_duration`, `description`, `max_tokens`, `guardrails`, `tools`, `gate`, `injects`, `produces`, `consumes`, `order`, `pipeline_type` are **all identical across every instance** — `load_agent_spec` for a synthetic id (`loader.py:138-143`) just `replace()`s the base spec's `id`.
- `produces`/`consumes` are **meaningless** for the template today (both empty) and would be *actively wrong* if populated — one contract cannot describe N differently-purposed instances. Routing goes through a parallel, instance-id-keyed artifact mechanism (`artifact_name(instance_id, topic)`, `engine.py:3190,3233`) that exists precisely because contracts cannot do this job.
- `guardrails`/`tools`/`gate` are harmless only because `custom-agent` declares none. **Landmine:** if someone "improves" the template by adding `guardrails: [typescript]` because most instances write code, every instance gets it — including one writing a joke.
- The fields that DO vary per instance (`instance_id`, `display_name`, `prompt`, `skills`) all live on `Step`. The architecture already knows the right home for per-instance config; it has not been generalized.

## Recorded history

- `backend/CLAUDE.md:38-41` — the only statement of the split as intentional: *"the registry says WHICH agents belong to a pipeline (membership/order); the manifest (`workflow.yaml`) says HOW they run."*
- `.planning/IMPLEMENTATION-REGISTER.md:3738-3740` records it as a **deliberate, locked decision**: *"registry's narrower real role (membership/order via `PIPELINE_AGENTS`/`get_pipeline_agents`) preserved — registry = WHICH agents, manifest = HOW they run... `context_from` marked legacy/vestigial... step agent-ids must match `PIPELINE_AGENTS` or the membership assertion raises RuntimeError."* **That last clause is now false**; the register was never updated.
- `.planning/phases/04-manifest-compiler-1a/04-04-SUMMARY.md:88` — first acknowledgment that manifest order and registry order legitimately diverge: *"Membership vs DAG order: the engine executes in the resolver's topo-sorted `validation.dag`, which legitimately reorders contract-coupled agents in the code-gen pipelines... The compiled plan... is therefore asserted against the registry MEMBERSHIP source, not `validation.dag`."* `order` was already known to be imprecise at Phase 4; the team chose to check membership (set), not order.
- The assertion's removal is itself undocumented in `.planning/` — see [plan-as-roster.md](plan-as-roster.md) ("Why the guard existed") for the full citation trail, including the still-uncorrected `.planning/phases/51-.../51-PATTERNS.md:117` *"DO NOT BREAK"*. **Resolved 2026-08-11**: `.knowledge/cards/ADR-0003.md` now records the decision to delete rather than restore it.
- **INV-5** (*"No DSL — control-flow keys stay rejected"*) explains why `depends_on`/`fanout`/`retry` exist as declared-but-inert step keys: every nested block in `compiler.py` is strict-key-validated for exactly that reason. "Declared but not yet wired" surface area is a deliberate consequence, not sloppiness.
- **INV-7** (*"The engine decides, never the manifest"*) is why `on_conflict`/gate outcomes/merge selection resolve in `engine.py` even when a manifest declares a policy name — the manifest records the policy, it never branches control flow. Its parenthetical scope is fan-out merge specifically.

## Ranked: what to move, what to delete

1. **Reconcile the stale membership-assertion documentation** (`backend/CLAUDE.md:39-41,350`, `IMPLEMENTATION-REGISTER.md:3740`) with `engine.py:1473-1491`. Trivial effort, no blast radius, urgent — a reader will believe a safety net exists that does not.
2. **Decide `order`'s remaining job and document it as UI-listing-only.** Small; blast radius limited to `get_all_agents_flat` / `/api/agents`.
3. **Rename step `tools:` (`ToolPermissions`) to `permissions:`.** The most confusing accidental collision found. Medium (compiler + plan.py + 5 demo manifests + tests); contained to `sample_*`.
4. **Delete `context_from`** — 57/88 agents carry it, never read. Remove the `AgentSpec` field, strip the frontmatter, drop the CLAUDE.md section. Medium but mechanical; no blast radius.
5. **Delete `max_tokens` from AGENT.md** (or wire it, but CLAUDE.md says don't) — 88/88 required, proven dead. Medium: it is a *required* loader field, so removal is a schema migration across 88 files.
6. **Move `gate` into the manifest as a step-level default**, keeping the dedupe. Directly fixes "one agent, two workflows, different HITL needs." Medium — the dedupe in `_evaluate_gates` must be re-derived without `spec.gate`.
7. **`produces`/`consumes` toward step-level** — or accept and document that DAG-typed routing does not apply to `custom-agent` instances, which is already true in practice. Large (80/88 declare `produces`); needs a dedicated phase. Lowest priority to execute, highest to document as a permanent limit. **See `dag-ownership.md`** for the full argument and migration path.
8. **Leave `injects` as-is** — the one field that already does the right thing. Use it as the template for how `guardrails`/`gate` should work if made overridable.
