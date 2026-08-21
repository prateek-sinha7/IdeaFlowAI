# Velocity — Architecture

> Base architecture and module map. The per-module detail lives in
> `.knowledge/architecture/MOD-*.md`; the machine-readable graph lives in
> `.knowledge/architecture/modules.json`.

## What Velocity is

Velocity (internally **Flowin**) is a **workflow-agnostic agent execution runtime**.

A workflow is described by a declarative, file-backed **manifest**. A thin
compiler — no DSL — turns that manifest into a typed `CompiledWorkflow` /
`ExecutionPlan`. A small **kernel** executes the plan. The kernel knows no
workflow by name: there is no `if pipeline_type == "prototype"` anywhere in it.

Everything that makes a workflow powerful is a **registered capability** that a
manifest opts into by declaration — execution strategies, validators,
deliverable resolvers, context providers, gates, merge strategies, task
parsers, worker agents, runtimes, skills, hooks, tools, MCP servers,
integrations.

### The load-bearing invariant

**A brand-new custom workflow can replicate the built-in `prototype` workflow
using a manifest and an `AGENT.md` alone — with zero engine edits.**

This is SC-001. If everything else is negotiable, this is not. It is what
"workflow-agnostic" actually means here, and it is proven by an executable test
rather than asserted.

### Design seams

- **Manifest -> compiler -> plan -> kernel.** The compiler validates every
  declared capability reference and rejects unknown names at compile time, not
  at run time.
- **`CapabilityRegistry`.** A central name-seam. Capabilities are resolved by
  `(kind, name)` and sit behind Protocol ports, so an implementation can be
  swapped without touching a caller.
- **`Workspace` / `RuntimeEnvironment` ports.** Only a local implementation
  exists today. ECS/containers are designed-for as a backend swap, deliberately
  not built. An import-linter contract locks this seam shut.
- **Durable state, agent-agnostic resume.** The kernel — never an agent —
  reads durable state, computes what remains, re-materializes completed work to
  disk, and continues. This holds across process restart, crash, sandbox loss,
  a paused gate, or a user-failed run, at task/worker granularity, including
  when the task list was edited in between.
- **Additive migrations only.** The persistence schema grows; it does not
  rewrite.
- **`deepagents` is mandatory.** The real LangChain library, always. A
  hand-rolled or vendored deep-agent runtime is banned and enforced by a
  banned-pattern CI gate.

### Shape

```
        manifest (file)                    frontend (Next.js)
              |                                    |
              v                                    | SSE / WebSocket
      WorkflowCompiler  --no DSL-->                v
              |                            FastAPI  (backend/app/api)
              v                                    |
       CompiledWorkflow / ExecutionPlan            |
              |                                    v
              v                             backend/app/models
        Kernel (backend/agents)  <---------  durable run state
              |                              run_events, artifact_refs,
              |  resolve(kind, name)         gate_events, subagent_runs, ...
              v
       CapabilityRegistry
        strategies · validators · deliverables
        context providers · gates · merge
        runtimes · hooks · tools · MCP
              |
              v
       Workspace / RuntimeEnvironment  (local only today; ECS is a swap)
```

## Domains

A **domain** is a system concern, declared by hand. A **module** is a folder,
derived by script. They are different questions and both are kept: a module
answers "what is in `backend/agents`", which no one has to maintain because
pydeps computes it; a domain answers "how does the execution kernel work",
which nothing can compute.

Domains overlap on purpose — `run_event.py` is in durable-state *and*
run-streaming — so they are a cover over the tree, not a partition of it. Each
card declares its `members:` as globs; membership, the file rollup and the
staleness signature are all resolved from that. A domain whose member files
change gets flagged the moment its `code_signature` moves away from the
`prose_signature` its prose was written against.

The diagrams below are lifted from the domain cards, never written twice.

<!-- DOMAIN-DIAGRAMS -->

### [Agent runtime — model selection and the deepagents adapter](architecture/DOMAIN-agent-runtime.md)

This domain answers one question for every LLM call the system makes: *which model, built how, and what happens when the provider says no.* It owns the model list itself (`ModelEntry` / `ModelCatalog`), the per-agent precedence that picks an id (`ModelResolver`), the single constructor that turns an id into a live chat client (`build_model`), the deepagents graph that client is handed to (`DeepAgentRunner`), the cheap non-agent path for one-shot calls (`cached_invoke`), the classifier that decides whether a provider failure is worth another attempt (`_is_transient_throttle`), the mapping from a provider exception to something a user can read (`map_exception`), and the cost arithmetic derived from the same catalog (`estimate_cost_usd`).

```mermaid
flowchart TD
  engine["execution_engine/engine.py"]
  resolver["model_policy.ModelResolver"]
  catalog["model_catalog.py"]
  pricing["model_pricing.py"]
  factory["agents/factory.py"]
  registry["capabilities/registry.py"]
  adapter["runtimes/langchain_deepagents.py"]
  runner["deep_agent_runner.py"]
  build["model_factory.build_model"]
  cached["cached_invoke.py"]
  errors["llm_errors.py"]
  chat["app/agents/chat_runner.py"]

  engine -->|"resolve(spec, step) → model id"| resolver
  resolver -->|"is_allowed / cost_class"| catalog
  engine -->|"create_runner(agent_id, ctx.model)"| factory
  factory -->|"resolve('runtime','langchain_deepagents')"| registry
  registry --> adapter
  adapter -->|"ctx.build() — kernel → app seam"| runner
  runner -->|"build_model(model, max_tokens)"| build
  cached -->|"build_model(model, max_tokens)"| build
  runner -->|"_is_transient_throttle(exc) → re-raise"| engine
  engine -->|"resolver.advance() → rebuild on next id"| factory
  engine -->|"estimate_cost_usd(model_id, tokens)"| pricing
  pricing -->|"ModelEntry.pricing"| catalog
  chat -->|"map_exception(exc) → code/recoverable"| errors
```

### [Auth and entitlements — who may run what](architecture/DOMAIN-auth-and-entitlements.md)

This domain answers three questions that the rest of the system is not allowed to answer for itself: *who is calling* (a JWT or a long-lived API key resolved to a `User` row), *what plan are they on* (`users.tier`, checked against `TIER_PIPELINES` before a run is launched), and *which rows may they see* (`owner_id` + `workspace_id`, enforced on every durable read by `ScopedStore`).

```mermaid
flowchart LR
  config["core/config.py"] -->|"SECRET_KEY"| security["core/security.py"]
  auth["api/auth.py"] -->|"create_access_token"| security
  security -->|"is_token_revoked(jti)"| revoked["models/revoked_token.py"]
  deps["core/dependencies.py"] -->|"decode + revocation gate"| security
  deps -->|"User row"| user["models/user.py"]
  apikey["api/api_key_auth.py"] -->|"X-Flowin-API-Key digest"| user
  admin["api/admin.py"] -->|"require_admin, writes tier"| user
  runcmd["api/run_commands.py"] -->|"Depends(get_current_user)"| deps
  user -->|"user.tier"| ent["core/entitlements.py"]
  runcmd -->|"can_run_pipeline(tier, type)"| ent
  fe["frontend/src/lib/entitlements.ts"] -.->|"advisory UI mirror"| ent
  runcmd -->|"ScopedStore(owner_id, workspace_id)"| authz["agents/authz.py"]
  engine["execution_engine/engine.py"] -->|"owner_id = user_id or anon:sid"| authz
  authz -->|"encrypt_pat / decrypt_pat"| crypto["core/crypto.py"]
  authz -->|"owner-scoped rows"| mcpcred["models/mcp_credential.py"]
```

### [Capability registry — the (kind, name) seam](architecture/DOMAIN-capability-registry.md)

This domain owns the **name seam**: the single `(kind, name)` namespace through which every declared capability in the system is validated, trust-checked, described and finally resolved to a live object.

```mermaid
flowchart LR
  compiler["workflows/compiler.py"]
  engine["execution_engine/engine.py"]
  api["app/api/capabilities.py"]
  base["capabilities/base.py"]
  subgraph reg["capabilities/registry.py"]
    known["_KNOWN"]
    impls["_IMPLS / _TRUST / _META"]
    discover["discover()"]
  end
  kernelcaps["agents/capabilities/*/ impl modules"]
  appcaps["app/agents/{validators,runtime,repo_index,chat}"]
  alias["agents/registry.py _OD_ALIAS_BASE"]
  catalog["capabilities/model_catalog.py"]

  compiler -->|"is_registered(kind,name)"| known
  compiler -->|"is_user_allowed → CAP-03"| impls
  engine -->|"resolve(kind,name) → impl"| impls
  api -->|"discover(); sorted(_KNOWN)"| known
  api -->|"describe / is_user_allowed"| impls
  api -->|"ModelCatalog().list()"| catalog
  impls -->|"unbound on first read"| discover
  discover -->|"importlib, kernel-side"| kernelcaps
  discover -->|"importlib, into MOD-backend-app-agents"| appcaps
  kernelcaps -->|"@register(kind,name)"| impls
  appcaps -->|"@register(kind,name)"| impls
  base -.->|"Protocol ports, satisfied structurally"| kernelcaps
  reg -->|"imports _OD_ALIAS_BASE"| alias
```

### [Chat and handoff — the conversational surfaces](architecture/DOMAIN-chat-and-handoff.md)

This domain owns every place a human talks to Velocity in prose rather than by starting a workflow — and, crucially, owns the rule that prose is never allowed to become an action on its own.

```mermaid
flowchart LR
  run_commands["run_commands.py"] -->|"RunState + ChatTurn"| chat_router["chat_router.py"]
  chat_router -->|"Dispatch(channel)"| run_commands
  run_commands -->|"converse(ctx, msg)"| concierge["chat/concierge.py"]
  concierge -->|"bounded owner-scoped reads"| scoped["agents/authz.ScopedStore"]
  concierge -->|"exclude_builtin_tools=True"| runner["deep_agent_runner.py"]
  concierge -->|"ProposalIntent"| run_commands
  run_commands -->|"Message rows"| chat_models["models/chat.py"]
  main["app/main.py"] -->|"run event"| narrator["chat_narrator.py"]
  narrator -->|"append_event_next_seq(chat_reply)"| scoped
  run_commands -->|"astream_execute"| chat_runner["chat_runner.py"]
  chat_runner -->|"create_runner('chat-*')"| factory["agents/factory.py"]
  handoff_api["api/handoff.py"] -->|"run_handoff_pipeline()"| hpipe["handoff_pipeline.py"]
  hpipe -->|"propose_edits / analyse / review"| hagents["agents/handoff/*.py"]
  hpipe -->|"clone / push / create_pull_request"| gh["handoff_github.py"]
  hpipe -->|"dispatch_event(token)"| ws["websocket_handoff.py"]
```

### [Context assembly — what an agent is told](architecture/DOMAIN-context-assembly.md)

This domain owns the answer to one question: **when the kernel is about to invoke an agent, what text does that agent actually see?** It covers both halves of that text — the system prompt (identity, guardrails, skills, hooks, constitution, body) and the per-dispatch context message (the user brief, upstream outputs, design-system and template blocks, uploaded documents, chat history, revision subjects, steering notes) — plus the transforms that keep either half from outgrowing the model's window.

```mermaid
flowchart TD
    launch["app/api/launch_context.py"] -->|"resolve_launch_od_context"| odctx["od_context.py"]
    odctx -->|"template / DS disk reads"| odloader["app/services/od_loader.py"]
    odctx -->|"od_context dict"| ectx["context.py — ExecutionContext"]
    memory["workflow_memory/memory.py"] -->|"SessionLocal query"| db["app/models/workflow_memory.py"]
    memory -->|"prewarmed_constitution"| ectx
    engine["engine.py — _compose_context_message"] --> ectx
    engine -->|"resolve(context_provider, name)"| registry["capabilities/registry.py"]
    registry --> providers["context_providers/*.py"]
    providers -->|"ctx.runner / ctx.scoped_store"| ectx
    providers -->|"block map"| engine
    providers -->|"resolve(compaction, chat_history)"| registry
    registry --> compaction["compaction/*.py"]
    registry --> pack["context_pack/pack.py"]
    factory["agents/factory.py"] -->|"resolve(prompt, default)"| registry
    registry --> policy["prompt/policy.py"]
```

### [Deliverables and artifacts — turning output into a result](architecture/DOMAIN-deliverables-and-artifacts.md)

This domain owns the answer to "what did the run actually produce, and how do I get it back later." It has three jobs that share one contract.

```mermaid
flowchart LR
    single_file["single_file.py"] --> artifact_helpers["_artifact.py"]
    ppt["ppt.py"] --> artifact_helpers
    streamed_text["streamed_text.py"] --> artifact_helpers
    single_file --> mimetype["_mimetype.py"]
    ppt --> mimetype
    streamed_text --> mimetype
    serialized_sandbox["serialized_sandbox.py"] --> mimetype
    repo_diff["repo_diff.py"]
    merges["merge/{copy_disjoint,git_3way,json_merge,html_fragment}.py"] --> merge_base["merge/base.py"]
    artifact_graph["artifacts/graph.py"] -->|"mapped by agents/authz.py::ScopedStore.write_ref"| row["app/models/artifact_ref.py"]
```

### [Durable state and resume — surviving restart and crash](architecture/DOMAIN-durable-state-resume.md)

This domain owns the answer to one question: **after the process dies, what does the next process know?** It is the durable substrate a run is reconstructed from — the append-only event log (run_event.py), the per-child and per-wave progress rows (subagent_run.py, wave_run.py), the per-run capability snapshot (run_capabilities.py), the exec audit trail (exec_runs.py) — plus the SQLAlchemy engine/session/`Base` those tables hang off (database.py).

```mermaid
flowchart LR
    scoped["authz.py::ScopedStore"] --> run_event["run_event.py"]
    scoped --> subagent_run["subagent_run.py"]
    scoped --> wave_run["wave_run.py"]
    scoped --> run_capabilities["run_capabilities.py"]
    scoped --> exec_runs["exec_runs.py"]
    run_event --> database["database.py"]
    subagent_run --> database
    wave_run --> database
    run_capabilities --> database
    exec_runs --> database
    state_machine["state_machine.py"] --> database
    store["artifact_store/store.py"]
```

### [Execution kernel — running a compiled plan](architecture/DOMAIN-execution-kernel.md)

This domain is the thing that actually *runs* a workflow.

```mermaid
flowchart TD
    reg["agents/registry.py"]
    resolver["execution_engine/resolver.py"]
    engine["execution_engine/engine.py"]
    ectx["execution_engine/context.py::ExecutionContext"]
    planner["planner/smart_planner.py"]
    clarify["execution_engine/clarify_engine.py"]
    services["execution_engine/kernel_services.py::KernelServices"]
    caps["capabilities/registry.py::CapabilityRegistry"]
    budget["execution_engine/budget.py::BudgetManager"]
    state["execution_engine/state_machine.py"]

    reg -->|"get_pipeline_agents → membership"| engine
    engine -->|"validate(agents) → topo DAG"| resolver
    engine -->|"one instance per run"| ectx
    engine -->|"plan(brief, pipeline_type)"| planner
    engine -->|"gate_verdict == CLARIFY_REQUIRED"| clarify
    engine -->|"resolve('strategy', step.strategy)"| caps
    engine -->|"transition(run_id, state)"| state
    ectx -->|"ctx.runner"| services
    ectx -->|"ctx.budget"| budget
    services -->|"run_agent → _run_agent"| engine
    services -->|"run_fanout → reserve()"| budget
```

### [Execution strategies — how a step is driven](architecture/DOMAIN-execution-strategies.md)

This domain owns the answer to one question: **given a compiled step, how is its work actually driven?** Five strategies answer it five ways — run the agent once (`single_shot`), split a plan into tasks and run one isolated sub-agent per task against a cumulative file (`task_loop`), fan a task list out to parallel workers in one batch (`fanout_batch`), partition a dependency-carrying task list into topological waves and fan each wave out in turn (`wave_scheduler`), or run already- distinct sibling sub-agents concurrently then run the parent over their results (`parallel_group`).

```mermaid
flowchart LR
    engine["engine.py"] --> single_shot["single_shot.py"]
    engine --> task_loop["task_loop.py"]
    engine --> fanout_batch["fanout_batch.py"]
    engine --> wave_scheduler["wave_scheduler.py"]
    engine --> parallel_group["parallel_group.py"]
    task_loop --> parsers["task_parsers/*.py"]
    fanout_batch --> parsers
    wave_scheduler --> parsers
    task_loop --> task_identity["task_identity.py"]
    wave_scheduler --> task_identity
    single_shot --> runner["KernelServices"]
    task_loop --> runner
    fanout_batch --> runner
    wave_scheduler --> runner
    parallel_group --> runner
    runner --> fanout["fanout.py::run_fanout"]
```

### [Human-in-the-loop gating — pause, approve, resume](architecture/DOMAIN-hitl-gating.md)

This domain owns the **step boundary as a decision point**: before (and after) a step runs, something other than the model gets to say *pass*, *block*, or *stop and ask a human* — and if it asks, the run has to survive the wait.

```mermaid
flowchart LR
    run_commands["run_commands.py::resolve_gate"]
    store["artifact_store/store.py"]
    evaluate["engine.py::_evaluate_gates"]
    review["engine.py::_run_review_gate"]
    delegate["kernel_services.py::run_human_gate"]
    hitl["gates/human.py + gates/approval.py"]
    policy["gates/security.py + gates/validation.py"]
    base["gates/base.py::GateOutcome"]
    write["capabilities/gates/write.py::write_gate_event"]
    audit["app/models/gate_events.py::GateEvent"]
    pendency["gate_pendency.py::derive_open_gate"]
    checkpointer["app/agents/checkpointer.py"]

    evaluate -->|"resolve('gate', name)"| hitl
    evaluate -->|"resolve('gate', name)"| policy
    hitl -->|"ctx.runner.run_human_gate"| delegate
    delegate --> review
    review -->|"get_review_event / get_review_response"| store
    run_commands -->|"set_review_response → event.set()"| store
    run_commands -->|"review_event_pending"| store
    hitl --> base
    policy --> base
    base --> evaluate
    hitl --> write
    policy --> write
    write -->|"ctx.runner.record_gate_event"| audit
    review -->|"emits review_gate_ready"| pendency
    checkpointer --> review
```

### [Run streaming — the backend-to-browser event contract](architecture/DOMAIN-run-streaming.md)

This domain owns the **event contract between a running pipeline and a browser tab**: how an engine event becomes an SSE frame, how a client that was not attached when the event happened catches up, and how a client that was attached is released when the run (or the process) ends.

```mermaid
flowchart LR
    queues["run_engine.py::_PIPELINE_QUEUES"] --> pump["run_engine.py::_pump_run_events"]
    pump --> subs["run_engine.py::_SUBSCRIBERS"]
    subs --> frames["run_stream.py::_iter_sse_frames"]
    frames --> endpoint["run_stream.py::stream_run_events"]
    endpoint --> hook["useRunStream.ts"]
    hook --> parse["sseFrame.ts::parseSseBlock"]
    parse --> replay["wsReplayState.ts::resolveFrameRunId"]
    replay --> store["useRunStateStore.ts::handleFrame"]
    store --> reducer["useWorkflow.ts::handlePipelineMessage"]
    shutdown["run_shutdown.py::shutdown_run_infrastructure"] --> pump
    ndjson["ndjson_adapter.py::run_prototype_pipeline"]
```

### [Validation and quality gates — judging agent output](architecture/DOMAIN-validation-and-quality.md)

This domain owns the question **"is what the agent just produced actually any good?"** — and, crucially, it owns only the *judging*.

```mermaid
flowchart LR
    severity["validators/severity.py"]
    tier["validators/task_done_when.py + spec_plan_coverage.py"]
    apiprefix["validators/api_prefix.py"]
    codeval["validators/code_compile.py + code_lint.py + code_test.py"]
    execsup["validators/_exec_support.py"]
    appval["app/agents/validators/html_static.py + html_render.py + design_quality.py"]
    static["static_check.py"]
    render["render_check.py"]
    routes["route_table.py"]
    poststeps["post_steps/revision_validation.py + api_prefix_audit.py"]
    model["models/validation_results.py"]

    codeval --> execsup
    codeval --> severity
    tier --> severity
    apiprefix --> severity
    appval --> severity
    appval -->|"via target.runner"| static
    appval -->|"via target.runner"| render
    static --> routes
    render --> routes
    render --> static
    poststeps -->|"resolve('validator', …)"| apiprefix
    appval -->|"record_validation_result"| model
```

### [Workflow compilation — manifest to ExecutionPlan](architecture/DOMAIN-workflow-compilation.md)

This domain owns the transform from **authored declaration to typed executable object**, and it owns the moment every declared name is checked.

```mermaid
flowchart LR
    manifest["workflows/manifest.py"] --> compiler["workflows/compiler.py"]
    selections["workflows/selections.py"] --> manifest
    compiler --> plan["workflows/plan.py"]
    compiler --> cap_registry["capabilities/registry.py"]
    compiler --> artifacts["workflows/artifacts.py"]
    loader["loader.py"] --> factory["factory.py"]
    factory --> cap_registry
    factory --> artifacts
    factory --> runner["app/agents/deep_agent_runner.py"]
```

### [Workspace isolation — sandboxes and the runtime seam](architecture/DOMAIN-workspace-isolation.md)

This domain owns the answer to *where does a run's bytes live, and who can reach them*.

```mermaid
flowchart LR
    base["agents/runtime/base.py"]
    caps["capabilities/registry.py"]
    row["app/models/workspace.py"]
    runtime["LocalSandboxRuntime"]
    workspace["LocalWorkspace"]
    policy["LocalExecutionPolicy"]
    sandbox["RunSandbox"]
    child["_ChildSandbox"]
    sweep["sandbox.py::sweep_expired"]
    serialize["serialize_sandbox_deliverable"]

    runtime -->|"satisfies the Protocol ports"| base
    caps -->|"resolve('runtime_env','local')"| runtime
    row -->|"workspaces.id → workspace_id"| runtime
    runtime -->|"create_workspace(has_git, exec)"| workspace
    workspace -->|"policy.allows('exec')"| policy
    workspace -->|"path_for / cleanup"| sandbox
    sandbox -->|"_ws() → read_file / write_file"| workspace
    workspace -->|"allocate_sub_sandbox / allocate_worktree"| child
    sandbox -->|"root under RUNS_ROOT"| sweep
    sandbox -->|"root walked"| serialize
```

<!-- /DOMAIN-DIAGRAMS -->

## Module map

<!-- MODULE-MAP -->

36 logical modules over 628 tracked source files. Each entry links to its
architecture card, which carries an auto-generated file and import rollup. Module
cards describe FOLDERS and carry no diagrams — for how a concern actually works,
read the domains above.

### Backend — Python (287 files)

| Module | Path | Files |
|---|---|---|
| [MOD-backend-agents](architecture/MOD-backend-agents.md) | `backend/agents` | 121 |
| [MOD-backend-app-agents](architecture/MOD-backend-app-agents.md) | `backend/app/agents` | 38 |
| [MOD-backend-alembic-versions](architecture/MOD-backend-alembic-versions.md) | `backend/alembic/versions` | 32 |
| [MOD-backend-app-api](architecture/MOD-backend-app-api.md) | `backend/app/api` | 30 |
| [MOD-backend-app-models](architecture/MOD-backend-app-models.md) | `backend/app/models` | 24 |
| [MOD-backend](architecture/MOD-backend.md) | `backend` | 10 |
| [MOD-backend-evals](architecture/MOD-backend-evals.md) | `backend/evals` | 9 |
| [MOD-backend-app-core](architecture/MOD-backend-app-core.md) | `backend/app/core` | 7 |
| [MOD-backend-scripts](architecture/MOD-backend-scripts.md) | `backend/scripts` | 6 |
| [MOD-backend-app-services](architecture/MOD-backend-app-services.md) | `backend/app/services` | 5 |
| [MOD-backend-app](architecture/MOD-backend-app.md) | `backend/app` | 2 |
| [MOD-backend-app-scripts](architecture/MOD-backend-app-scripts.md) | `backend/app/scripts` | 2 |
| [MOD-backend-alembic](architecture/MOD-backend-alembic.md) | `backend/alembic` | 1 |

### Frontend — TypeScript (341 files)

| Module | Path | Files |
|---|---|---|
| [MOD-frontend-src-components-workflow](architecture/MOD-frontend-src-components-workflow.md) | `frontend/src/components/workflow` | 56 |
| [MOD-frontend-src-lib](architecture/MOD-frontend-src-lib.md) | `frontend/src/lib` | 42 |
| [MOD-frontend-src-components-chat](architecture/MOD-frontend-src-components-chat.md) | `frontend/src/components/chat` | 38 |
| [MOD-frontend-src](architecture/MOD-frontend-src.md) | `frontend/src` | 33 |
| [MOD-frontend-src-hooks](architecture/MOD-frontend-src-hooks.md) | `frontend/src/hooks` | 32 |
| [MOD-frontend-src-app](architecture/MOD-frontend-src-app.md) | `frontend/src/app` | 28 |
| [MOD-frontend-src-components-results](architecture/MOD-frontend-src-components-results.md) | `frontend/src/components/results` | 27 |
| [MOD-frontend-src-components-preview](architecture/MOD-frontend-src-components-preview.md) | `frontend/src/components/preview` | 18 |
| [MOD-frontend-src-components-history](architecture/MOD-frontend-src-components-history.md) | `frontend/src/components/history` | 12 |
| [MOD-frontend-src-components-ui](architecture/MOD-frontend-src-components-ui.md) | `frontend/src/components/ui` | 11 |
| [MOD-frontend-src-components-handoff](architecture/MOD-frontend-src-components-handoff.md) | `frontend/src/components/handoff` | 8 |
| [MOD-frontend-src-components-layout](architecture/MOD-frontend-src-components-layout.md) | `frontend/src/components/layout` | 7 |
| [MOD-frontend-src-components-analytics](architecture/MOD-frontend-src-components-analytics.md) | `frontend/src/components/analytics` | 6 |
| [MOD-frontend-src-components-catalog](architecture/MOD-frontend-src-components-catalog.md) | `frontend/src/components/catalog` | 4 |
| [MOD-frontend-src-components-library](architecture/MOD-frontend-src-components-library.md) | `frontend/src/components/library` | 3 |
| [MOD-frontend-src-components-savedworkflows](architecture/MOD-frontend-src-components-savedworkflows.md) | `frontend/src/components/savedworkflows` | 3 |
| [MOD-frontend-src-components-settings](architecture/MOD-frontend-src-components-settings.md) | `frontend/src/components/settings` | 3 |
| [MOD-frontend-src-components-sidebar](architecture/MOD-frontend-src-components-sidebar.md) | `frontend/src/components/sidebar` | 2 |
| [MOD-frontend-src-providers](architecture/MOD-frontend-src-providers.md) | `frontend/src/providers` | 2 |
| [MOD-frontend-src-styles](architecture/MOD-frontend-src-styles.md) | `frontend/src/styles` | 2 |
| [MOD-frontend-src-types](architecture/MOD-frontend-src-types.md) | `frontend/src/types` | 2 |
| [MOD-frontend-src-components-home](architecture/MOD-frontend-src-components-home.md) | `frontend/src/components/home` | 1 |
| [MOD-frontend-src-context](architecture/MOD-frontend-src-context.md) | `frontend/src/context` | 1 |

<!-- /MODULE-MAP -->

`MOD-backend-agents` is the execution kernel and the capability registry — the
centre of gravity of the whole system. Read it first.

## Knowledge base conventions

```
.knowledge/
├── cards/            482 cards, {YYYYMMDD}[-{HHMM}]-{ID}.md
├── architecture/     14 DOMAIN-*.md  — hand-authored system concerns
│                     36 MOD-*.md     — one per folder, generated
│                     789 files/**.md — one per source file, generated
│                     + modules.json
├── .stage/           delta approval queue — proposals land here before applying
├── INDEX.md          one line per card
├── ARCHITECTURE.md   this file
├── CONTEXT.md        compacted context pack, built by `/velocity prime`
└── state.yaml        last sync commit + date, corpus counts
```

**Card types.** Four, and no others: `fix` (266), `issue` (162), `bug` (42),
`adr` (12). `requirement`, `phase` and `doc` were retired — every card of those
types was a generated stub whose body only pointed into `.planning/`, so they
were deleted rather than migrated. `kind: state` describes how things *are*;
`kind: event` records something that *happened*.

**Staleness is tracked, not assumed.** Every architecture card carries a
`code_signature` (derived from the files it is answerable for and their
symbols) and a `prose_signature` (stamped when its prose was last written).
Equal means current; different means the code moved underneath the analysis.

```
tools/knowledge/build_architecture.py --affected [FILE…]   which cards a changeset touches
tools/knowledge/build_architecture.py --stale-prose        which cards are out of date
tools/knowledge/build_architecture.py --stamp CARD         mark a card current after re-authoring
```

A domain's watch set is its `members:` globs **plus every file its prose
names** — so a change in a file the card merely passes through still flags it.

**IDs are permanent.** They are wikilink targets. A card is never renumbered
and never deleted. Corrections happen by **supersession** — write a new card,
link it to the old one, and set the old one's `status` to `superseded`. Never
rewrite a trusted card's meaning in place.

**Resolve a `[[CARD-ID]]`** by globbing `.knowledge/cards/*-<ID>.md`.

**The divider contract.** In every `MOD-*.md`, content above
the line beginning `<!-- AUTO-GENERATED BELOW THIS LINE`
is hand-authored and preserved across
regeneration; content below it is produced by `tools/knowledge/build_architecture.py` and
is overwritten. Never hand-edit below the divider.

## Regenerating

| Artifact | Command | Notes |
|---|---|---|
| `INDEX.md`, `state.yaml` | `python3 tools/knowledge/build_index.py` | Fully derived from `cards/` |
| `architecture/`, `modules.json` | `python3 tools/knowledge/build_architecture.py` | Preserves above-divider prose |
| `CONTEXT.md` | `/velocity prime` | Rebuilds only when the sync commit moved |

Git is the user's responsibility. No tool or skill in this system commits,
stages, or branches.
