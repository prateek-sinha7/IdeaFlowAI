# Building Custom Workflows in VelocityAI

*A guide to how the VelocityAI workflow engine composes agents, what you can and cannot change, and how to build a brand-new workflow -- either as an engineer (via files) or as a user (via the in-app composer).*

> Verified against the engine on branch `feat/ui-2` (2026-07-17). Code paths are relative to the repository root. "Agent" = one AI step in a pipeline; "workflow"/"pipeline" = an ordered set of agents that produces a deliverable.

---

## TL;DR

- **The engine is workflow-agnostic.** The kernel knows no workflow by name -- a new workflow is a declarative manifest (`workflow.yaml`) plus agent files, with **zero engine edits**. This is the core design guarantee (SC-001) and it is proven by test.
- **An agent's inputs and outputs are FIXED in its own `AGENT.md`** and are the same in every workflow. You cannot rewire them per-workflow. What a workflow *can* change per agent is *how* it runs (its strategy, gates, validators, model, etc.).
- **There are two ways to build a custom workflow:** as an engineer editing files (a permanent new pipeline), or as a user in the live in-app composer (mix agents from different pipelines, no files).
- **The catch when mixing agents:** agents connect by a fixed dependency graph. A combination only runs if every agent's required upstream producers are also in the set. Otherwise the run is rejected at launch.

---

## 1. The mental model

At launch, the engine compiles a **declarative manifest** into a typed execution plan, and drives that plan deterministically. The LLM never decides which agent runs next.

Two sources of truth, cleanly split:

| Source | File | Answers |
|---|---|---|
| **The registry** | `backend/agents/registry.py` (`PIPELINE_AGENTS`) | *Which* agents are in a pipeline, and in what order |
| **The manifest** | `backend/agents/workflows/<id>/workflow.yaml` | *How* each agent runs (its per-step capabilities) + the workflow's deliverable, clarify config, planner flag |

The compile seam is `compile_for_run(pipeline_type)` (`backend/agents/execution_engine/engine.py:545-563`): it resolves any alias (e.g. `od_prototype` -> `prototype`), loads the manifest, and compiles it into a typed `CompiledWorkflow`. If a pipeline has no manifest, the run never starts. A **membership assertion** (`engine.py:1643-1658`) requires the manifest's steps to match the registry's agent list exactly, so the two can never silently diverge.

Every capability an agent can use -- execution strategies, validators, gates, deliverable resolvers, context providers (~70 in total) -- is a self-registering entry in a **Capability Registry** (`backend/agents/capabilities/registry.py`). Adding a new capability is "a module plus a `@register` line"; the kernel reaches implementations only through a static registry lookup (no `eval`, no dynamic dispatch). A CI gate forbids any `if pipeline_type == "..."` branch inside the engine.

**SC-001 -- "a brand-new custom workflow can replicate the prototype pipeline by manifest + `AGENT.md` only, with zero engine edits" -- is true today and proven** by a non-prototype test fixture that runs an end-to-end build loop with no engine changes.

---

## 2. Anatomy of a workflow

A workflow is three things:

1. **A manifest** -- `backend/agents/workflows/<id>/workflow.yaml`. Declares the ordered `steps` (each step = one agent + its capabilities), plus workflow-level settings: the single `deliverable`, the `clarify` config, the `planner` flag, context/input providers, seed files, and limits. It is pure data -- there is no control flow (`if`/`for`/`${}` are rejected).
2. **The agents** -- one folder per agent at `backend/agents/prompts/<id>/AGENT.md`, each with YAML frontmatter (`id`, `name`, `role`, `pipeline_type`, `order`, `max_tokens`, `produces`, `consumes`, `injects`, `guardrails`, ...) and a system-prompt body.
3. **The capabilities** -- the registered strategies/validators/gates/etc. the steps reference by name.

To belong to a workflow, an agent needs: (1) an `AGENT.md` with valid frontmatter, (2) its `pipeline_type` listed in `SUPPORTED_PIPELINE_TYPES` (`backend/agents/loader.py:29-50`), (3) its id in `PIPELINE_AGENTS[<pipeline>]` at the right position, and (4) a matching step in that pipeline's `workflow.yaml`.

---

## 3. How agents connect: inputs and outputs

**This is the most important thing to understand before mixing agents.**

An agent's input/output **contract is fixed in its `AGENT.md`** via two frontmatter fields, and it is identical in every workflow that uses the agent. There is **no per-step override** for it.

The contract is **keyed by agent-id**:

- `produces:` -- a single typed output, named after the agent itself.
- `consumes:` -- the list of **upstream agent-ids** whose output this agent needs.

Examples (verified):

| Agent | consumes | Meaning |
|---|---|---|
| `domain-analyst` | `[]` | A DAG root -- needs nothing upstream |
| `prototype-specify` | `[]` | A DAG root |
| `od-ppt-brief-analyst` | `[]` | A DAG root |
| `backlog-compiler` | `[epic-architect, story-estimator, nfr-specialist]` | Needs all three upstreams |
| `od-ppt-composer` | `[od-ppt-brief-analyst]` | Needs the brief analyst |
| `app-code-generator` | `[material-analyzer, app-system-design, app-api-design]` | Needs three upstreams |

Routing is automatic: an upstream agent's output reaches a downstream agent **only if what the upstream produces matches what the downstream consumes** (`_filter_consumed_outputs`, `engine.py:6281-6312`). Content flows through a typed artifact graph. (The older `context_from` field is vestigial -- it is still parsed but no longer drives routing.)

### What is fixed vs configurable

| Fixed in the agent (`AGENT.md`) | Configurable per-step in the workflow (`workflow.yaml`) |
|---|---|
| `produces` / `consumes` (the I/O contract) | `strategy` (single-shot / per-task build loop / fan-out) |
| the system-prompt body, role | `gates` (human review pause) |
| `guardrails` | `validators` (e.g. HTML static + render checks) |
| which `injects` it *can* take | `model`, `retry`, `compaction`, `task_source`, `tools`, `hooks`, `post_step`, `depends_on` |
| | `injects` actually applied (template / design system / craft) -- merged from both the agent and the step |

**Workflow-level** settings (top of the manifest): the single `deliverable`, `clarify` mode/defaults, the `planner` flag, context/input providers, seed files, limits, and the default model.

**So: the *data* an agent needs is baked into the agent; the *way it executes* is workflow-configurable.** The same agent cannot produce or consume different things in different workflows -- that is deliberate, so the typed graph stays consistent and any composition can be validated.

---

## 4. Two ways to build a custom workflow

### Path A -- Engineer, via files (a permanent new pipeline)

1. Add the new type to `SUPPORTED_PIPELINE_TYPES` (`backend/agents/loader.py:29-50`).
2. Create an `AGENT.md` for each agent (with `pipeline_type: <new-id>` and a sequential `order`).
3. Add the ordered agent-id list to `PIPELINE_AGENTS` (`backend/agents/registry.py`).
4. Create `backend/agents/workflows/<new-id>/workflow.yaml` whose step agents match that list, in order. (Copy an existing manifest as a template.)

**Gotcha:** an agent declares exactly **one** `pipeline_type`. So at the *static* (file) level, agents are siloed to their pipeline. To "reuse" an existing agent's behavior in a new pipeline you author a new `AGENT.md` for it under the new pipeline. (The `od_ppt` agents are the one shared case -- they are used by both `ppt` and `od_ppt`.)

### Path B -- User, via the live composer (mix agents, no files)

VelocityAI ships a **working in-app composer** that genuinely mixes agents across pipelines -- this is the real "combine different agents from different workflows" path, and it requires no engineering.

- **Where:** Home -> "Compose a custom workflow" -> the Composer page (a Simple / Canvas view).
- **The palette** comes live from `GET /api/capabilities` (`backend/app/api/capabilities.py:111-162`), which enumerates the registry and marks each capability `user_allowed` or locked. The **allow-list of agents** you can pick is `allowed_custom_agent_ids(...)` (`backend/agents/registry.py:332-411`): a `custom` run may include agents from the custom pool **plus every base pipeline** (prototype, user_stories, ppt, app_builder, ...). Revisions and internal pipelines (like `chat`) are intentionally locked to nothing.
- **What you do:** pick a base type, assemble a cross-pipeline agent set, optionally set per-agent levers (validator / gate / model / retry) from the allowed palette, then name/save (`POST /api/user-workflows`) and launch.
- **Server-side safety:** the saved selection is re-compiled and re-validated with a "user" trust level, so a locked capability can never be smuggled in. At launch, the selection is overlaid onto the compiled plan by agent-id (`engine._apply_selections`, `engine.py:5546-5625`); an empty selection is a byte-identical no-op.

Under the hood, the agents you pick are threaded straight into `engine.execute(agents=..., pipeline_type=..., selections=...)`, and the **passed agent list drives execution** (not the base manifest's steps). An agent you inject that has no manifest step simply runs as a plain single-shot step with default capabilities.

---

## 5. Combining agents from different workflows -- the rules

Because inputs/outputs are **agent-id-keyed**, a mix only *runs* if every agent's required upstream producers are also present in your set (its "consumes closure"). The dependency graph is validated by the `WorkflowResolver` (`backend/agents/execution_engine/resolver.py:78-177`).

| You pick... | Result |
|---|---|
| Only **root agents** (`consumes: []`) from different pipelines -- e.g. `domain-analyst` + `prototype-specify` + `od-ppt-brief-analyst` | **Runs.** They execute in topological order, each producing its own output -- but they do not hand off to each other (a parallel-ish bundle, not a chain). |
| A **downstream agent without its producers** -- e.g. `backlog-compiler` without `epic-architect`/`story-estimator`/`nfr-specialist` | **Rejected at launch** with `workflow_unsatisfiable`. |
| A downstream agent **with** its full upstream closure | **Runs** as a proper hand-off chain (execution order is the resolver's topological sort, not your list order). |

Other constraints to know:

- **One deliverable per workflow.** The deliverable is workflow-level (from the base manifest), not per-agent. A `custom` run produces the base pipeline's deliverable type -- you cannot get `prototype.html` out of a `custom` run.
- **Template-requiring agents need a template.** If a selected agent expects a template/design-system inject (prototype/ppt) and none is loaded, the launch is rejected (`missing_template_context`).
- **No save-time dependency check (today).** The compiler validates capability names, trust, and step ordering, but **not** the produces/consumes graph. A broken combination *saves* fine and only fails when you *launch* it.
- **Revisions and internal pipelines are locked** to their own agents / nothing.

---

## 6. Implemented today vs planned

**Implemented (verified in code):**

- The workflow-agnostic kernel; the manifest -> compiler -> typed-plan layer; the registry/membership split; the ~70-entry Capability Registry; SC-001 (proven).
- The cross-pipeline agent allow-list.
- The live composer: browse launchable workflows; assemble a cross-pipeline agent set; set per-agent validator / gate / model / retry from the allowed palette; name / save / rename / duplicate / delete / launch -- all through the UI and `/api/capabilities` + `/api/user-workflows`, with server-side "user" trust enforcement.

**A user CAN:** compose and launch a custom agent set across pipelines with per-agent levers. **A user CANNOT (by design):** author a raw `workflow.yaml`, change the deliverable / clarify / planner settings, grant a locked capability, add a new capability *kind*, or change an agent's produces/consumes contract.

**Planned / not yet built:**

- Save-time validation of the produces/consumes dependency graph (broken mixes currently fail only at launch).
- Composing capabilities beyond the four per-agent levers (strategy swaps, fan-out, merges, integrations are declarable in the data shape but not surfaced in the composer UI).
- User-authored non-`custom` base types.
- Sharing / marketplace / org-shared / versioned workflows.

---

## 7. Reference: key files and endpoints

**Engine / compiler:**
- `backend/agents/execution_engine/engine.py` -- `:545-563` compile seam, `:1572-1600` DAG validation gate, `:1643-1658` membership assertion, `:2041-2099` per-step dispatch (incl. synthesized single-shot for un-manifested agents), `:5546-5625` `_apply_selections`, `:6281-6312` consumed-output routing.
- `backend/agents/execution_engine/resolver.py:78-177` -- the produces/consumes DAG validator (`WorkflowResolver`).

**Registry / loader / capabilities:**
- `backend/agents/registry.py` -- `PIPELINE_AGENTS` (membership), `allowed_custom_agent_ids` (`:332-411`, the cross-pipeline allow-list).
- `backend/agents/loader.py:29-110` -- `SUPPORTED_PIPELINE_TYPES`, `AgentSpec` (produces/consumes parsing).
- `backend/agents/capabilities/registry.py` -- the Capability Registry (`@register`, `discover`, trust flags, `resolve`).
- `backend/agents/factory.py:318-332` -- inject composition (agent + step).

**Manifests:**
- `backend/agents/workflows/<id>/workflow.yaml` -- compare `custom` vs `prototype` vs `od_ppt` for the range of step capabilities.

**API surface (the composer):**
- `GET /api/capabilities` (`backend/app/api/capabilities.py:111-162`) -- the live palette + trust flags.
- `POST /api/user-workflows` (`backend/app/api/user_workflows.py`) -- save a user composition (trust=user).
- `backend/app/api/run_commands.py:1069-1339` -- launch-time agent resolution + validation.

**Frontend composer:** `frontend/src/components/workflow/composer/` (the Composer page), the Workflow Catalog, and the capability palette embedded in the agents popup.

---

*Product: VelocityAI. This guide describes the post-migration (deepagents) runtime. For the built-in pipeline catalog and per-agent details, see `docs/WORKFLOWS.md` and `backend/CLAUDE.md`.*
