# 003 — Workflow Engine Decoupling & Universal Workflow Runtime

> Turn the prototype-/PPT-/revision-coupled `ExecutionEngine` into a small, workflow-agnostic
> **runtime kernel** driven by **declarative workflow manifests** that compile to a typed
> **ExecutionPlan**. Every rich capability today hardwired for `prototype` (per-task sub-agent
> loop, validation + fix-loop, context injection, deliverable resolution, clarify defaults)
> becomes a **declared, registered capability** any workflow can opt into — so a brand-new
> custom workflow can replicate prototype **by manifest + AGENT.md only, with zero engine edits**.
> Design (not build) the **Workspace / RuntimeEnvironment** abstraction now so ECS/containers
> plug in later as a backend swap. Living document — update phase status + the decision log as work lands.

| | |
|---|---|
| **Branch** | `feature/003-workflow-engine-decoupling` (off `deepagents-full-swap`) |
| **Status** | 📋 Planned — Phase 0 next. No code landed yet. |
| **Created** | 2026-06-06 |
| **Builds on** | [002-deepagents-migration](../002-deepagents-migration/plan.md) (the deepagents runtime this refactor restructures) |
| **Supersedes** | the hardcoded `pipeline_type`/`spec.id == "prototype-build"` branches in `agents/execution_engine/engine.py` |

---

## 1. Goal & scope

**Problem.** `ExecutionEngine` is named "Universal" but ~half of `engine.py` is `prototype`/`od_*`/`ppt`
specifics keyed on **literal `pipeline_type` strings** and **a literal agent id** (`spec.id == "prototype-build"`,
`engine.py:872`). A custom workflow gets the generic spine (DAG validation, sequencing, `consumes` routing,
Human gates, artifact storage) but **silently none** of the rich machinery (per-task loop, validation/fix-loop,
`od_context` injection, HTML-aware deliverable, tailored clarify) because all of it is gated behind hardcoded
names. The engine also stores per-run state on the **singleton** (`self._od_context`, `self._completed_tasks`,
`self._current_task_block`, `self._revision_*`, `self._gate_agent_ids`), which is a latent multi-user
corruption bug and a hard blocker for fan-out / parallel waves / multi-tenant runtimes.

**Goal.** A workflow-agnostic kernel + declarative capabilities such that:

1. **Parity by declaration** — `prototype` is re-expressed as a manifest; the engine contains **no**
   `if pipeline_type == "prototype"` / `if spec.id == "prototype-build"` branches, and output is
   byte-identical (SC-001).
2. **Reusable powers** — per-task loop, fan-out, validation+fix, deliverable strategies, context providers,
   reference-file seeding, planner/clarify config, context compaction are **first-class declared capabilities**
   (Q36: all of them).
3. **Per-run isolation** — all run state lives in a per-run `ExecutionContext`; the kernel singleton is stateless (NFR-001).
4. **Workspace-ready** — engine talks to a `Workspace`/`RuntimeEnvironment` port; **local impl now**, ECS later as a backend swap, no engine rewrite (Q-N1).
5. **Agent-initiated fan-out** — any allowed agent can request sub-agent fan-out via an **engine-owned** tool; the engine (not the prompt) owns isolation, caps, routing, merge, events.

**In scope:** Phases 0–6 below + the Workspace/Runtime layer **as interfaces with a local implementation**.
**Out of scope (this spec):** ECS/EC2 provisioning, warm/dedicated containers, container networking/secrets,
CP-SAT scheduling, single-file fragment-merge parallelism, untrusted end-user code execution. These are
**designed-for** (interfaces exist) but **deferred** (§17), and code-execution security gets its **own gated spec** (§16 N3).

## 2. Firm decisions (locked via Q&A — Q1–Q45 + N1)

Terminology & framing
- **Q1** Unify on **`workflow`**; keep `pipeline_type` as a **migration alias** until callers move.
- **Q2** **Engineer-registered capabilities, user-composable manifests** (trust boundary). Internally start trusted (A).
- **Q3** **Preserve existing workflows exactly** during migration (characterization-tested, byte-identical).
- **Q4** Success = **prototype parity by manifest/config only, zero engine edits**.

Definition model
- **Q5** **File-backed built-in manifests now**; **DB-backed user workflow definitions later** (D).
- **Q6** **Agents declare what they do; workflows declare orchestration** (strict split).
- **Q7** **Migrate prototype to the same mechanism** (dogfood; no privileged path).

Execution strategies
- **Q8** **ExecutionStrategy registry** (`single_shot`, `task_loop`, `fanout_batch`, `wave_scheduler`).
- **Q9** **Workflow step chooses strategy; agent may provide a default.**
- **Q10** **All four** become declarative: task-source agent, task parser, seed files, deliverable path.
- **Q11** **Canonical `Task` schema + adapters** (heading/JSON/`[P]` parsers feed one schema).

Fan-out & sub-agents
- **Q12** **Both** declarative fan-out **and** runtime fan-out.
- **Q13** **Engine-owned `spawn_subagents` tool** (never raw library `task`).
- **Q14** **Caller chooses** same agent (N copies) or a **named worker from the allowed registry**.
- **Q15** **Configurable** parallel/sequential **with concurrency caps**.
- **Q16** **Files/artifacts + structured summary** returned to caller (D).
- **Q17** **Nested fan-out allowed, strict depth cap.**
- **Q18** Engine caps: **subagents, concurrency, tokens, cost, wall-clock, recursion/depth.**
- **Q19** **Separate** fan-out from **real code-execution sandboxing** (C) — fan-out now, code-exec its own track.
- **Q20** **Per-workflow isolation choice**; default **isolated sub-sandbox/worktree for writes**, shared only for safe reads.

Validation
- **Q21** **Validator registry**; workflow lists validators.
- **Q22** Validator receives a **`DeliverableContext`** and may request **browser/compile/test/static-analysis** resources.
- **Q23** **Generic fix-loop** (deliverable name + max-attempts + fix-prompt template from config).
- **Q24** **Internal `P0/P1/P2/P3`** (matches existing prototype prose); **map to `CRITICAL/HIGH/MEDIUM/LOW`** externally.
- **Q25** **Configurable policy; default: warn on non-critical, block on critical**, bounded attempts, then surface `validation_warning`.

Deliverables & context
- **Q26** **Deliverable-strategy enum + registered custom resolvers.**
- **Q27** **Engineers register resolvers; users select safe ones.**
- **Q28** **Context-provider registry** (`opendesign`, `repo`, `previous_run`, `uploaded_files`, `memory`, …).
- **Q29** **Seed files declared in the workflow manifest.**
- **Q30** **Planner/clarify config in the workflow manifest** (`planner: skip|run`, `clarify: always|gated|off`, `clarify_defaults`).

Parallel waves & isolation
- **Q31** **Decouple first; waves are a registered strategy added after.**
- **Q32** **Deterministic topo wave-builder now; seam for smarter (CP-SAT) later.**
- **Q33** **Prototype stays sequential**; single-file fragment-merge is **later & opt-in**.
- **Q34** **Sub-directory isolation in the run sandbox first**; **real git worktrees** for brownfield repo workflows.

Tier improvements
- **Q35** Token-trim = a **context-compaction strategy**; HTML skeleton is one implementation.
- **Q36** **All** major powers are declared capabilities.
- **Q37** Prompt-content changes (constitution/clarify-writeback/spec-behavior) are a **separate PR after decoupling**; the **HTML-skeleton token fix lands early**.
- **Q38** Analyze gate / done-when / design checks become **validators/gates in the framework**.

Migration & non-functionals
- **Q39** **Strangler / incremental** (prototype works throughout).
- **Q40** **Characterization tests first.**
- **Q41** Order: **token-trim → manifest/config → strategies → validators/deliverables/context-providers → fan-out → waves.**
- **Q42** **Decouple & generalize now; design fan-out/code-exec interfaces now, build fan-out next milestone.**
- **Q43** **New event vocabulary** for fan-out, waves, validators, merge, budgets.
- **Q44** **Per-run and per-workspace budget enforcement.**
- **Q45 / "What Must Be Added"** Explicit models for **workspace/project/repo/worktree, trust/security, durable resume, typed artifact references, merge policy, per-run execution state.**
- **N1** **Delay ECS/EC2**; build `Workspace` + `RuntimeEnvironment` interface + `LocalSandboxRuntime` now.

## 3. Hard invariants (apply to every phase)

- **INV-1 Kernel knows no workflow by name.** No `if pipeline_type in {...}` / `if spec.id == "..."` for behavior selection anywhere in the kernel. Grep gate: the only place a workflow id appears is the manifest loader.
- **INV-2 No per-run state on the singleton.** All mutable run state is on `ExecutionContext`. `ExecutionEngine`/kernel instances are immutable after construction.
- **INV-3 Byte-identical migration.** Each phase keeps the existing WS event stream + deliverable identical for `prototype`/`od_*`/`ppt`/code-gen (characterization tests are the gate). No feature flag dual-paths left after a phase lands.
- **INV-4 Capabilities are registered, manifests reference by name.** Engineers register; manifest validation rejects any unknown/​not-allowed capability name (trust boundary, Q2).
- **INV-5 Thin compiler, no DSL.** A manifest compiles to a validated `ExecutionPlan`. No control flow (`if`/`while`/expressions) in manifests — loops/conditionals live inside strategies.
- **INV-6 Ports, not implementations.** Engine depends on `Workspace`/`RuntimeEnvironment`/`Validator`/`Strategy`/`DeliverableResolver`/`ContextProvider`/`IsolationProvider`/`MergeStrategy` **interfaces**; concrete impls are injected/registered.
- **INV-7 Engine owns fan-out.** Agents request via the engine tool; the agent prompt never decides isolation/caps/merge.

## 4. The problem — current coupling (the "as-is" leak map)

Verified leaks in `agents/execution_engine/engine.py` (all must move to declarations):

| # | Leak | Location | Coupled to |
|---|---|---|---|
| L1 | `_PPT_PIPELINE_TYPES`, `_PROTOTYPE_PIPELINE_TYPES`, `REVISION_FILE_NAME="prototype.html"` | 93–110 | literal names |
| L2 | `_resolve_final_output` branches (revision / prototype / code-gen / text-PPT) | 316–397 | every deliverable shape hardcoded |
| L3 | `_sanitize_carousel_deck_html`, `_unwrap_artifact` | 232–313 | PPT composer quirks |
| L4 | `prototype_revision` seeding + pre-edit baselines (~130 lines) | 519–650 | inside `execute()` |
| L5 | `SKIP_PLANNER_FOR_PROTOTYPE` branch | 704–712 | prototype |
| L6 | `ALWAYS_CLARIFY` per-pipeline `missing_information` defaults dict | 733–743 | every name hardcoded |
| L7 | `if spec.id == "prototype-build"` → build loop dispatch | 872–878 | **literal agent id** |
| L8 | post-revision validation fix-loop | 917–962 | prototype_revision |
| L9 | `_resolve_final_output` call + PPT carousel sanitize | 971–983 | prototype/PPT |
| L10 | `if pipeline_type in ("od_prototype","prototype")` → read `prototype.html` back | 1328–1335 | prototype |
| L11 | entire `_run_build_task_loop` / `_write_build_reference_files` / `_count_plan_tasks` / `_extract_task_block` / `_run_validation_fix_loop` / `_load_template_example` | 1450–1704, 2554–2563 | prototype only |
| L12 | `_build_context_message`: od_ppt/od_prototype template/DS/example injection + `prototype-build` CURRENT-TASK + full-HTML + compliance | 2378–2512 | prototype/PPT |
| L13 | **dead** `_extract_html_skeleton` (built, never called) | 2565–2628 | the token-trim that was never wired |
| L14 | per-run state on `self` (`_od_context`, `_completed_tasks`, `_current_task_block`, `_revision_*`, `_gate_agent_ids`, `_user_id`, `_checkpointer`) | 474–550, throughout | singleton mutation |

## 5. Target architecture

```
   built-in manifest (file)         user workflow (DB, later)
            \                              /
             ▼                            ▼
          ┌──────────────────────────────────┐
          │  WorkflowCompiler (thin, no DSL)  │  validate refs vs CapabilityRegistry + trust
          └──────────────────────────────────┘
                          │  CompiledWorkflow (ExecutionPlan: typed DAG of Steps)
                          ▼
          ┌──────────────────────────────────┐
          │       Runtime Kernel              │  knows NO workflow by name (INV-1)
          │  execute(plan, ExecutionContext)  │  sequence • gates • events • budgets • artifacts
          └──────────────────────────────────┘
             │            │            │
   ExecutionStrategy   Validator   DeliverableResolver   ContextProvider   (registries, INV-4)
   single_shot         html_static  single_file          opendesign
   task_loop           html_render  serialized_sandbox   repo / previous_run / uploaded / memory
   fanout_batch        compile/test streamed_text(_unwrapped)
   wave_scheduler      lint/schema  <registered custom>
                          │
                ┌─────────┴─────────┐
                ▼                   ▼
          ArtifactGraph        Workspace ──backed by── RuntimeEnvironment (port)
          (typed refs)         (fs + opt git + opt exec)   LocalSandboxRuntime  [EcsRuntime later]
                                       │
                              IsolationProvider + MergeStrategy + BudgetManager
```

**Layering (dependency direction inward):** Compiler → Kernel → Capability ports. The kernel imports
**ports**; concrete capabilities register themselves into the `CapabilityRegistry` at startup. Workflows
are **data**; capabilities are **code**; the kernel is the **only** orchestrator (it owns fan-out, INV-7).

## 6. Core abstractions (contracts)

Illustrative signatures (final names TBD in Phase 1). Python `Protocol`/`dataclass`.

```python
# --- per-run state (replaces all self._* on the engine) ---
@dataclass
class ExecutionContext:
    run_id: str
    user_id: str | None
    plan: CompiledWorkflow
    workspace: Workspace
    artifacts: ArtifactGraph
    budget: BudgetManager
    planning_context: dict
    cancel_event: asyncio.Event
    gate_agent_ids: list[str] | None
    parent_run_id: str | None
    checkpointer: object
    accumulated_outputs: dict[str, str] = field(default_factory=dict)
    results: list[AgentResult] = field(default_factory=list)
    completed_tasks: list[dict] = field(default_factory=list)
    depth: int = 0                      # fan-out nesting (Q17)
    # NOTE: strategy-local scratch (e.g. current task block) lives in the strategy, not here.

# --- declarative workflow (compiled from the manifest) ---
@dataclass
class Step:
    agent_id: str
    strategy: str = "single_shot"          # Q8/Q9
    gate: str | None = None                # "human" | None
    task_source: TaskSource | None = None  # Q10a/b
    validators: list[str] = field(default_factory=list)   # Q21
    fix: FixPolicy | None = None           # Q23/Q25
    compaction: str | None = None          # Q35
    fanout: FanoutSpec | None = None       # Q12 declarative
    injects: list[str] = field(default_factory=list)

@dataclass
class CompiledWorkflow:
    id: str
    steps: list[Step]                      # topo-validated DAG
    context_providers: list[str]           # Q28
    seed_files: dict[str, SeedSource]      # Q29
    deliverable: DeliverableSpec           # Q26
    planner: str                           # "skip" | "run"  (Q30)
    clarify: ClarifySpec                   # mode + defaults (Q30)
    limits: Limits                         # Q18/Q44

# --- canonical task (Q11) ---
@dataclass
class Task:
    id: str; title: str; body: str
    targets: list[str]                     # section selectors / file paths
    depends_on: list[str]
    parallel: bool
    conflict_keys: list[str]               # wave scheduling (Q32/Q33)
    done_when: list[str]                   # Q-Tier5 / validators
    inputs: dict; outputs: dict

class TaskParser(Protocol):                # adapters → Task (Q11)
    def parse(self, text: str) -> list[Task]: ...   # heading_tasks | json_tasks | bracket_p ...

# --- capability ports ---
class ExecutionStrategy(Protocol):
    name: str
    async def run(self, step: Step, ctx: ExecutionContext) -> AsyncIterator[dict]: ...

class Validator(Protocol):
    name: str
    async def validate(self, target: "DeliverableContext") -> list["Issue"]: ...

@dataclass
class Issue:
    severity: str          # P0|P1|P2|P3 internally (Q24)
    code: str; message: str
    target: str | None = None
    fixable: bool = True

class DeliverableResolver(Protocol):
    name: str
    def resolve(self, ctx: ExecutionContext) -> str | "ArtifactRef": ...

class ContextProvider(Protocol):
    name: str
    async def load(self, ctx: ExecutionContext) -> dict[str, str]: ...   # block-name -> content

# --- workspace / runtime (designed now, local impl now; Q-N1) ---
class RuntimeEnvironment(Protocol):
    async def read_file(self, path: str) -> str: ...
    async def write_file(self, path: str, content: str) -> None: ...
    async def search(self, query: str, **opts) -> list[str]: ...
    async def exec_command(self, argv: list[str], **opts) -> "ExecResult": ...   # gated by ExecutionPolicy (N3)
    async def clone_repo(self, url: str, ref: str) -> None: ...
    async def create_branch(self, name: str, base: str) -> None: ...
    async def git_diff(self, base: str) -> str: ...
    async def teardown(self) -> None: ...

class Workspace(Protocol):          # fs + optional git + optional exec, backed by a RuntimeEnvironment
    runtime: RuntimeEnvironment
    has_git: bool
    exec_policy: "ExecutionPolicy"

class IsolationProvider(Protocol):  # Q20/Q34
    async def allocate(self, ctx: ExecutionContext, scope: str) -> Workspace: ...  # shared_read | sub_sandbox | worktree

class MergeStrategy(Protocol):      # Q-"What Must Be Added"
    name: str
    async def merge(self, base: Workspace, fragments: list[Workspace]) -> None: ...  # copy_disjoint | git_3way | json | html_fragment

class BudgetManager:                # Q18/Q44 — tokens, cost, subagents, depth, concurrency, wall-clock
    def reserve(self, *, tokens=0, subagents=0) -> None: ...   # raises BudgetExceeded
    def spent(self) -> "BudgetSnapshot": ...
```

**Fan-out (engine-owned, INV-7).** A new runner tool `spawn_subagents(tasks=[{agent, input}], mode=…)` is
bound to allowed agents. The tool **does not** spawn anything itself; it emits a structured request the
**kernel** fulfils: pick `IsolationProvider`, enforce `BudgetManager` + depth cap, run via `asyncio.gather`
(parallel, capped) or sequentially, route outputs to the `ArtifactGraph`/sub-sandbox, `MergeStrategy` back,
emit `subagent_*`/`merge_*` events, and return a files+summary payload (Q16-D) to the caller's next turn.

## 7. Capability registry & trust model (Q2, Q27, INV-4)

- One `CapabilityRegistry` keyed by `(kind, name)` for: strategies, validators, deliverable resolvers,
  context providers, isolation providers, merge strategies, task parsers, worker agents.
- **Engineers register** capabilities in code at startup. **Manifests reference by name.**
- **Trust:** built-in/file manifests may reference any registered capability. **User/DB manifests** (later)
  are validated against a per-capability **`user_allowed: bool`** flag — unknown or not-user-allowed names
  → compile error. This is the security seam that keeps "fan-out / exec" from being user-composable until
  explicitly allow-listed (and code-exec stays off the user list until N3 lands).

## 8. Prototype re-expressed as a manifest (the parity proof — SC-001)

`agents/workflows/prototype/workflow.yaml` (illustrative):

```yaml
id: prototype
version: 1
planner: skip                                   # was SKIP_PLANNER_FOR_PROTOTYPE (L5)
clarify:
  mode: always                                  # was ALWAYS_CLARIFY
  defaults: [target_audience, scope, priority, style]   # was the L6 dict entry
context_providers: [opendesign]                 # was od_context branches (L12)
seed_files:                                     # was _write_build_reference_files (L11)
  spec.md:  { from: prototype-specify }
  tasks.md: { from: prototype-plan }
  design.md: { from_provider: opendesign }       # template_body + ds_body
deliverable: { strategy: single_file, name: prototype.html }   # was L2/L10
limits: { max_subagents: 0, max_concurrency: 1 }               # prototype = sequential (Q33)
steps:
  - { agent: prototype-specify, gate: human }
  - { agent: prototype-plan,    gate: human }
  - agent: prototype-build
    strategy: task_loop                          # was the L7 spec.id branch
    task_source: { from: prototype-plan, parser: heading_tasks }   # was _count/_extract (L11)
    compaction: html_skeleton                     # was the dead L13 helper (now wired, Q35/Tier#1)
    validators: [html_static, html_render]        # was _run_validation_fix_loop (L11)
    fix: { max_attempts: 2, policy: warn_noncritical_block_critical }
  - { agent: prototype-validate }
```

`od_prototype` = the same manifest selected with the OpenDesign context provider configured (alias → same plan).
`prototype_revision` = a variant manifest with `seed_files.parent: { from_run: parent }` + the revision deliverable
+ the post-edit validation step (was L4/L8). **Acceptance:** running this manifest produces the identical event
stream + `prototype.html` as today (characterization tests), with the L1–L14 branches deleted from the kernel.

## 9. Leak → new-home mapping (every L# from §4)

| Leak | New home |
|---|---|
| L1 names/`REVISION_FILE_NAME` | manifest `deliverable.name` + `seed_files`; no frozensets |
| L2 `_resolve_final_output` | `DeliverableResolver` registry (`single_file`/`serialized_sandbox`/`streamed_text`/`…`) |
| L3 carousel/`<artifact>` | a `ppt` `DeliverableResolver` + a `ppt` post-step validator/transform (registered) |
| L4 revision seeding/baseline | `seed_files.from_run` + a `previous_run` ContextProvider; baselines = validator concern |
| L5 skip-planner | manifest `planner: skip` |
| L6 clarify defaults | manifest `clarify.defaults` |
| L7 build-loop dispatch | `strategy: task_loop` resolved from the step (Q9) |
| L8 post-revision fix | the same `task_loop`/validators on the revision step |
| L9 final-output + sanitize | `DeliverableResolver.resolve()` |
| L10 HTML read-back | `task_loop` strategy reads the declared `deliverable.name` from the workspace |
| L11 build-loop internals | `TaskLoopStrategy` + `TaskParser` + `Validator`s + generic fix-loop + `seed_files` |
| L12 context injection | `ContextProvider` (opendesign) + per-agent `injects` resolution in a generic injector |
| L13 dead skeleton | `CompactionStrategy(html_skeleton)` wired via `compaction:` (Tier#1) |
| L14 singleton state | `ExecutionContext` (Phase 0) |

## 10. Fan-out & sub-agents (Q12–Q20) — interfaces now, build in Phase 5

- **Two entry points:** declarative (`step.fanout` over a task list) and runtime (`spawn_subagents` tool).
  Both funnel through one kernel `run_fanout(requests, ctx)`.
- **Worker selection (Q14):** `agent="self"` (N copies) or a named worker that must be in the workflow's
  `allowed_workers` + registry.
- **Mode (Q15):** `parallel` (capped `asyncio.gather`) or `sequential`; engine enforces `max_concurrency`.
- **Isolation (Q20/Q34):** `IsolationProvider.allocate(scope)` → shared-read | sub_sandbox | worktree; writes default to isolated.
- **Merge (Q16-D):** results land as artifacts/files; `MergeStrategy` integrates them; caller gets files + a structured summary.
- **Nesting/limits (Q17/Q18):** `ctx.depth` capped; `BudgetManager` enforces subagent count, concurrency, tokens, cost, wall-clock; `BudgetExceeded` aborts fan-out gracefully (partial results surfaced).
- **Events (Q43):** `subagent_spawned` / `subagent_result` / `merge_start` / `merge_complete` / `budget_warning`.

## 11. Workspace / RuntimeEnvironment layer (Q-N1, N2, N7) — interfaces now, `LocalSandboxRuntime` only

- **One `Workspace`** (INV-2 of the design): filesystem + optional git + optional exec. Prototype's
  `RunSandbox` becomes a `Workspace` with `has_git=False, exec=off`. **No engine fork** for repo vs artifact.
- **`LocalSandboxRuntime`** implements the port over the existing per-run disk dir (clone into the run dir,
  local branch/worktree, `git diff`). **`EcsRuntime` is deferred** (§17) behind the same port.
- **Repo workflow (local, Phase 4):** `clone_repo` → `create_branch`/worktree → agents read/edit/search/exec
  → validators (compile/test/lint) → `DeliverableResolver(repo_diff)` → app-builder-style **file tree + diff +
  validation results** surface (Q-N7). PR push waits on a git-hosting integration (N4).

## 12. Validation framework & severity (Q21–Q25)

- `Validator` registry; manifest lists `validators: [...]` per step. `DeliverableContext` carries path,
  content, `Workspace`, and task meta, and can request a browser/compile/test runner (Q22).
- **Generic fix-loop** (replaces L11's HTML-hardcoded one): deliverable name + `max_attempts` + fix-prompt
  template from `FixPolicy`. Default policy **warn on non-critical, block on critical**, then emit
  `validation_warning` with residuals (Q25, lands Tier#9).
- **Severity:** internal `P0/P1/P2/P3`; a single mapping function exposes `CRITICAL/HIGH/MEDIUM/LOW` to the UI (Q24).
- **Tier #4/#5/#6** become registered validators/gates: `spec_plan_coverage` (pre-build analyze), `task_done_when`
  (per-task acceptance), `design_quality` (tokens/placeholder/a11y, warnings-first).

## 13. Budgets, limits, observability (Q18, Q43, Q44)

- `BudgetManager` per-run **and** per-workspace ceilings (tokens, €, subagents, depth, concurrency, wall-clock);
  reserve-before-spawn; graceful abort.
- New events (Q43): `subagent_*`, `wave_start`/`wave_complete`, `validator_result`, `validation_warning`,
  `merge_*`, `budget_warning`. Existing events stay byte-identical for migrated workflows (INV-3).

## 14. Backward-compat & testing strategy (Q3, Q40)

- **Characterization tests FIRST (Phase 0):** golden deliverable + recorded event-stream snapshots for
  `prototype`, `od_prototype`, `prototype_revision`, `ppt`/`od_ppt`, and one code-gen pipeline, driven by a
  scripted model (`tests/agents/_scripted_model.py`). These are the regression gate for every later phase.
- Each phase must leave those snapshots **green** before it merges. No dual-path flags left behind (INV-3).

## 15. Phase plan

> Strangler migration (Q39). Each phase is independently shippable and keeps prototype working.

**Phase 0 — Safety net + `ExecutionContext`.** Characterization tests (§14). Extract all `self._*` run state
into `ExecutionContext`; thread it through `execute`/`_run_agent`/build-loop. **No behavior change.**
*Accept:* snapshots green; kernel instance has no per-run attributes (NFR-001). Also lands **Tier#1 token-trim** (wire `_extract_html_skeleton`) as the first measurable win (Q37/Q41).

**Phase 1 — Manifest + typed artifacts + thin compiler.** `WorkflowManifest` (file-backed), `ArtifactGraph`/
`ArtifactRef`, `WorkflowCompiler` → `CompiledWorkflow`. Existing pipelines load via a generated manifest
(behavior unchanged). *Accept:* every current pipeline runs from a compiled plan; snapshots green.

**Phase 2 — Prototype as manifest (parity proof, SC-001).** Implement `single_shot` + `task_loop` strategies,
`single_file`/`serialized_sandbox`/`streamed_text` resolvers, `opendesign` context provider, `seed_files`,
`heading_tasks` parser. Delete L1–L13 kernel branches. *Accept:* prototype/od_/revision/ppt/code-gen
byte-identical (snapshots green) with **zero name/id branches** in the kernel (grep gate, INV-1).

**Phase 3 — Capability registries hardened.** Formalize `CapabilityRegistry` + trust flags (Q2/Q7); migrate
validators (`html_static`, `html_render`) and the generic fix-loop; severity mapping; `validation_warning`.
*Accept:* validators are registry-driven; Tier#4/5/6 land as validators (Q38).

**Phase 4 — Local Workspace runtime.** `RuntimeEnvironment` port + `LocalSandboxRuntime`; `Workspace`;
`repo_diff` resolver; minimal repo tools (read/edit/search/exec/git_diff) behind `ExecutionPolicy`. First
brownfield workflow end-to-end **locally** (clone → branch → agents → compile/test validators → diff surface).
*Accept:* a sample repo workflow produces a diff + validation results; prototype unaffected.

**Phase 5 — Engine-owned fan-out.** `spawn_subagents` tool + kernel `run_fanout`; `IsolationProvider`
(sub_sandbox/worktree) + `MergeStrategy`; `BudgetManager`; depth/concurrency caps; `subagent_*`/`merge_*` events.
*Accept:* an agent can fan out N workers under caps, results merge deterministically; budgets abort gracefully.

**Phase 6 — Wave scheduler.** `wave_scheduler` strategy: topo-sort tasks by `depends_on` + `conflict_keys`
into waves, run each wave via fan-out. Enabled for multi-file workflows; **prototype stays sequential** (Q33).
*Accept:* a multi-file workflow runs disjoint tasks in parallel waves; seam left for CP-SAT (Q32).

**Phase 7 (later) — ECS/EC2 runtime** behind the unchanged `RuntimeEnvironment` port (separate spec; §17).

## 16. Open decisions (decision records — confirm before the relevant phase)

- **N1 ✅ DECIDED** — Local runtime now; ECS later behind the port.
- **N2 (Phase 4)** — *Proposed:* isolation granularity MVP = **ephemeral per-run local**; abstraction allows warm/dedicated later. **Confirm.**
- **N3 (gates Phase 4 exec) ⚠️ OPEN — highest risk** — Local `exec_command` security: network egress (none/allow-list), secrets (none-by-default/scoped), credentials (ephemeral), command allow/deny, resource caps. **Needs its own threat-model decision; code-exec stays disabled until set.**
- **N4 (Phase 4+)** — Git hosting scope. *Note:* your repo is GitLab (`hexaware-uki/flowin`) → GitLab likely required, not just GitHub. **Confirm order: GitHub-first vs GitLab-first vs both.**
- **N5 (Phase 4)** — *Proposed:* branch/PR **manifest-declared, runtime-enforced** (`base_branch`, `working_branch`, `commit_policy`, `pr_policy`); v1 = **diff-only, no PR push** until N4 lands. **Confirm.**
- **N6 (Phase 4)** — Target repo scale (kLOC / file count) → drives index-vs-grep for repo inventory. **Provide a ballpark.**
- **N7 (Phase 4)** — *Proposed/confirmed-ish:* repo deliverable = app-builder-style **file tree + per-file diff + test/build results + summary** (PR link when N4 lands). **Confirm.**
- **N8 (Phase 4+)** — Long-job orchestration substrate. *Proposed:* in-process (FastAPI task) for local v1; durable queue/worker is an infra follow-up. **Confirm.**

## 17. Non-goals / deferred (designed-for, not built here)

ECS/EC2 provisioning · warm/dedicated containers · container networking & cloud secrets injection · production
container teardown/lease mgmt · CP-SAT scheduling (topo seam only) · single-file fragment-merge parallelism
(prototype stays sequential) · untrusted **end-user code execution** (trust seam exists; capability stays
engineer-only until N3) · PR/commit push (diff-only until git-hosting integration). All sit behind interfaces
defined in this spec so each is a **backend swap, not a rewrite**.

## 18. File-by-file change map (initial)

- `agents/execution_engine/engine.py` → split into `kernel.py` (workflow-agnostic) + delete L1–L13 branches.
- new `agents/execution_engine/context.py` — `ExecutionContext` (Phase 0).
- new `agents/workflows/` — `manifest.py`, `compiler.py`, `plan.py`, and `<id>/workflow.yaml` per workflow.
- new `agents/capabilities/` — `registry.py` + `strategies/`, `validators/`, `deliverables/`, `context_providers/`, `isolation/`, `merge/`, `task_parsers/`.
- new `app/agents/runtime/` — `base.py` (`RuntimeEnvironment`/`Workspace` ports), `local.py` (`LocalSandboxRuntime`).
- new `app/agents/tools/fanout.py` — `spawn_subagents` (Phase 5).
- `app/agents/static_check.py` / `render_check.py` → wrapped as registered `Validator`s.
- `agents/registry.py` — `PIPELINE_AGENTS` becomes (or is generated from) manifests; alias `pipeline_type`.
- tests: `tests/agents/test_characterization_*.py` (Phase 0), then per-capability suites.

## 19. Risks

- **R1 Parity regression** — behavior secretly encoded in `engine.py`. *Mitigation:* Phase 0 characterization snapshots; INV-3.
- **R2 Compiler scope-creep into a DSL** — *Mitigation:* INV-5; manifest is data, strategies hold logic.
- **R3 Two engines** (artifact vs repo) — *Mitigation:* one `Workspace` abstraction (INV-6); prototype = git-off Workspace.
- **R4 Fan-out cost/recursion blowups** — *Mitigation:* `BudgetManager` + depth/concurrency caps; engine-owned (INV-7).
- **R5 Code-exec security** — the scariest surface. *Mitigation:* N3 own spec; capability disabled until threat-model set; off the user allow-list.
- **R6 Frontend lag** — UI assumes known types/flat sequences. *Mitigation:* workflow metadata + new events fetched dynamically (tracked separately).
- **R7 Durable resume for long repo jobs** — *Mitigation:* typed artifacts + run-state records; N8.

---

*Decision log: append dated entries here as phases land.*
