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
| **Revised** | 2026-06-06 (r1) review additions §8–§22 + INV-8…10 · 2026-06-06 (r2) phase splits (0A/B/C · 1A/B/C · 4A/B), semantic event parity (INV-3), synthetic `anon:<session_id>` owner, hand-authored manifests, durable event `seq`/replay cursor · 2026-06-06 (r3) agent-runtime/skills/hooks/MCP/integration capability layer (§30, INV-11) · 2026-06-06 (r4) executable lifecycle hooks (N12 ✅) + MCP client / all famous servers (N13 ✅) · 2026-06-06 (r5) code-deletion / anti-duplication ledger (§31, INV-12) · 2026-06-06 (r6) per-agent model selection (§20, A12) + target directory structure & patterns (§32) + ledger CI guard in Phase 0A + LangChain `deepagents` mandated throughout (INV-13) · 2026-06-06 (r7) runtime adapter id standardized to `langchain_deepagents` (PyPI package stays `deepagents`); INV-13/R15 disambiguated |
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
   `if pipeline_type == "prototype"` / `if spec.id == "prototype-build"` branches; the deliverable is
   **identical where deterministic** and the event stream is at **semantic parity** (SC-001, INV-3).
2. **Reusable powers** — per-task loop, fan-out, validation+fix, deliverable strategies, context providers,
   reference-file seeding, planner/clarify config, context compaction are **first-class declared capabilities**
   (Q36: all of them).
3. **Per-run isolation** — all run state lives in a per-run `ExecutionContext`; the kernel singleton is stateless (NFR-001).
4. **Workspace-ready** — engine talks to a `Workspace`/`RuntimeEnvironment` port; **local impl now**, ECS later as a backend swap, no engine rewrite (Q-N1).
5. **Agent-initiated fan-out** — any allowed agent can request sub-agent fan-out via an **engine-owned** tool; the engine (not the prompt) owns isolation, caps, routing, merge, events.
6. **Safe multi-tenant by construction** — every workflow, run, artifact, workspace, and repository is **owner-scoped** (INV-8); every step runs **least-privilege** tools (INV-9); every artifact is **lineage-tracked** (INV-10); gates are first-class (§9).

**In scope:** Phases 0–6 below + the Workspace/Runtime layer **as interfaces with a local implementation** +
the foundational platform contracts the review surfaced (typed artifacts & lineage §17, persistence §18,
authorization §19, tool-permission policy §8, gate registry §9, model policy §20, cancellation/retry/resume §21,
and the dynamic API/frontend contract §22 as a parallel track).
**Runtime mandate:** every agent — in every workflow, prototype and custom alike — runs on the **LangChain `deepagents` library** (`create_deep_agent`), the same runtime the prototype pipeline uses today; **never a hand-rolled "deep agent"** (INV-13).
**Out of scope (this spec):** ECS/EC2 provisioning, warm/dedicated containers, container networking/secrets,
CP-SAT scheduling, single-file fragment-merge parallelism, untrusted end-user code execution. These are
**designed-for** (interfaces exist) but **deferred** (§27), and code-execution security gets its **own gated spec** (§26 N3).

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

**Locked additions (post-review, 2026-06-06)** — promoted from "risks/notes" to first-class requirements:
- **A1** **Dynamic API/frontend contract** is a deliverable, not a risk (§22). The composer fetches workflow metadata + capabilities + event types + artifact/diff trees dynamically; no hardcoded workflow types.
- **A2** **Concrete persistence schema** (§18): `workflows`, `workflow_runs`(extend), `artifact_refs`, `workspaces`, `repositories`, `subagent_runs`, `wave_runs`, `validation_results`, `gate_events`.
- **A3** **Ownership is an invariant** (INV-8, §19): every workflow/run/artifact/repo/parent-run/workspace is user+workspace scoped; default-deny; parent/source-run access is ownership-checked.
- **A4** **Step-level tool-permission policy** (INV-9, §8): `read_files`/`write_files`/`exec`/`git`/`network`/`secrets`/`spawn_subagents`; exec/network/secrets default OFF.
- **A5** **Repo index / context selection** (§15): `RepoInventory`/`RepoIndex`/`ContextPack` as first-class artifacts/providers (ignore rules, binary skip, summaries, dep graph, targeted selection).
- **A6** **Merge-conflict flow** (§13): on merge failure → conflict artifact + `on_conflict` policy (human gate | merge agent | partial | abort).
- **A7** **Gate registry** (§9): `human` / `validation` / `approval` / `security` gates first-class (today's `Validation_Gate` is declared-but-unimplemented — make it real).
- **A8** **Artifact lineage** (INV-10, §17): producer step/agent/task, content hash, path, version, visibility, retention, parents.
- **A9** **Cancellation / retry / resume** (§21): defined cancellation semantics, idempotent step retry, durable reconnect/restart resume.
- **A10** **Model policy** (§20): per-workflow/per-step model, max tokens, cost class, fallback chain.
- **A11** **Agent-runtime & integration capability layer** (§30, INV-11): `agent_runtime` / `skill_provider` / `hook_provider` / `tool_provider` / `mcp_server` / `integration_provider` are **registered, owned, allow-listed, permissioned** capabilities — not free-form prompt text or unconstrained tools. Adds `AgentRuntimeAdapter` + `PromptAssemblyPolicy` (§6).
- **A12** **User per-agent model selection** (§20): the user can visually pick **any allowed model for any agent** in the composer; `model_overrides: {agent_id → model_id}` is applied at the **top** of the model-resolution order and persisted per run.

## 3. Hard invariants (apply to every phase)

- **INV-1 Kernel knows no workflow by name.** No `if pipeline_type in {...}` / `if spec.id == "..."` for behavior selection anywhere in the kernel. Grep gate: the only place a workflow id appears is the manifest loader.
- **INV-2 No per-run state on the singleton.** All mutable run state is on `ExecutionContext`. Kernel instances are immutable after construction.
- **INV-3 Semantic-compatible migration.** Each phase preserves the **deliverable byte-for-byte where the output is deterministic**, and the WS event stream at **semantic parity** — same event *types*, order, and required fields, and the same final result. Volatile fields (timestamps, streamed-text chunk boundaries, generated IDs, token/usage counts, durations) are **normalized out** of the snapshot. The one sanctioned exception is an intentional context/compaction change (e.g. Phase 0C), gated on the semantic snapshot + a measured token delta — not byte-identity. No feature-flag dual-paths **and no dual *implementation*** left after a phase lands — the legacy code a phase supersedes is **deleted in that same phase** (INV-12 / §31), never left beside the new capability.
- **INV-4 Capabilities are registered, manifests reference by name.** Engineers register; manifest validation rejects any unknown/​not-allowed capability name (trust boundary, Q2).
- **INV-5 Thin compiler, no DSL.** A manifest compiles to a validated `ExecutionPlan`. No control flow (`if`/`while`/expressions) in manifests — loops/conditionals live inside strategies.
- **INV-6 Ports, not implementations.** Engine depends on `Workspace`/`RuntimeEnvironment`/`Validator`/`Strategy`/`DeliverableResolver`/`ContextProvider`/`IsolationProvider`/`MergeStrategy`/`GateHandler` **interfaces**; concrete impls are injected/registered.
- **INV-7 Engine owns fan-out.** Agents request via the engine tool; the agent prompt never decides isolation/caps/merge.
- **INV-8 Ownership everywhere (default-deny).** Every workflow, run, artifact, workspace, repository, and parent/source run is scoped to `(owner_id, workspace_id)`. No cross-owner read/write; parent-run/source-run seeding and artifact retrieval are ownership-checked at the store layer (§19).
- **INV-9 Least-privilege tools.** A step gets only the tool permissions its manifest grants (read/write/exec/git/network/secrets/spawn). `exec`/`network`/`secrets`/`spawn_subagents` default **OFF**. A capability the workflow's owner isn't allowed → compile error (§8).
- **INV-10 Every artifact is lineage-tracked.** No anonymous deliverables: producer step/agent/task, content hash, version, parents, visibility, retention are recorded at write time (§17).
- **INV-11 Runtime/skills/hooks/MCP/integrations are capabilities, not free text.** The agent runtime, skills, hooks, MCP servers, and integrations are registered, owned (INV-8), allow-listed (§7), and permissioned (§8/§9) — never arbitrary prompt text or unconstrained tools (§30). The prompt-assembly order is a declared `PromptAssemblyPolicy`, not hardcoded.
- **INV-12 Move, don't copy (single implementation).** Every capability extraction **moves** existing logic behind its interface and **deletes** the inline original in the **same phase** — no behavior has two implementations, no legacy branch survives its phase. Enforced by per-phase **deletion gates** (grep banned-patterns + dead-code scan + import-linter) and the **migration ledger** (§31). The only sanctioned temporary coexistence is the `accumulated_outputs` legacy mirror, removed in Phase 1B.
- **INV-13 Use LangChain `deepagents` — never hand-roll.** The agent runtime is the **LangChain `deepagents` library**, wrapped by `DeepAgentRunner` behind the `langchain_deepagents` `AgentRuntimeAdapter` (§6/§30). **The canonical import is exactly `from deepagents import create_deep_agent` (PyPI package `deepagents==0.6.7`, adopted in [002](../002-deepagents-migration/plan.md)); our runtime adapter/identifier is `langchain_deepagents`.** **No module may create its own `deepagents`/`langchain_deepagents` package, define a `DeepAgent`/`deep_agent` class, or re-implement the agent loop** — always import the real library. Any other runtime (`claude_code_cli`, …) is an *additional* adapter, never an excuse to reinvent. Enforced by a banned-pattern CI gate (R15).

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
| L15 | loose run handoff: `accumulated_outputs: dict[str,str]` (untyped) + thin `ArtifactStore` | throughout | no typed artifacts/lineage |
| L16 | `parent_run_id` seeding reads `RunSandbox(user_id, parent_run_id)` with **no explicit ownership check** | 583–610 | implicit, not enforced (INV-8) |

## 5. Target architecture

```
   built-in manifest (file)         user workflow (DB, later)
            \                              /
             ▼                            ▼
          ┌──────────────────────────────────┐
          │  WorkflowCompiler (thin, no DSL)  │  validate refs vs CapabilityRegistry + trust + owner allow-list
          └──────────────────────────────────┘
                          │  CompiledWorkflow (ExecutionPlan: typed DAG of Steps)
                          ▼
          ┌──────────────────────────────────┐
          │       Runtime Kernel              │  knows NO workflow by name (INV-1)
          │  execute(plan, ExecutionContext)  │  sequence • gates • events • budgets • cancel/resume
          └──────────────────────────────────┘
    │        │        │        │        │        │
  Strategy Validator Deliverable Context  Gate   Policy        (registries, INV-4)
  single   html_*    single_file opendesign human  model        + ToolPermissions (INV-9)
  task_loop compile  serialized  repo       valid. tool-perm
  fanout   test/lint streamed    prev_run   approv.
  waves    coverage  repo_diff   memory     security(N3)
    │
    ▼
  ArtifactGraph (typed, lineage, owner-scoped, INV-8/10) ──► Persistence (§18)
    │
    ▼
  Workspace ──backed by── RuntimeEnvironment (port)   IsolationProvider + MergeStrategy + BudgetManager
  (fs + opt git + opt exec + ExecutionPolicy)         LocalSandboxRuntime  [EcsRuntime later]
    │
    └─► dynamic API/frontend contract (§22): /workflows, /capabilities, /runs/{id}/artifacts|diff, events
```

**Layering (dependency direction inward):** Compiler → Kernel → Capability ports. The kernel imports
**ports**; concrete capabilities register into the `CapabilityRegistry` at startup. Workflows are **data**;
capabilities are **code**; the kernel is the **only** orchestrator (it owns fan-out, INV-7). Ownership (§19) +
persistence (§18) wrap every artifact/run; the frontend (§22) reads it all dynamically.

## 6. Core abstractions (contracts)

Illustrative signatures (final names TBD in Phase 1). Python `Protocol`/`dataclass`.

```python
# --- per-run state (replaces all self._* on the engine; L14) ---
@dataclass
class ExecutionContext:
    run_id: str
    owner_id: str                        # user, or synthetic "anon:<session_id>" — never None (INV-8)
    workspace_id: str
    plan: CompiledWorkflow
    workspace: Workspace
    artifacts: ArtifactGraph             # typed + lineage (§17)
    budget: BudgetManager
    models: ModelResolver                # §20 — user per-agent override > step > agent > workflow > global
    model_overrides: dict = field(default_factory=dict)  # {agent_id -> model_id} from the UI (§20/A12)
    planning_context: dict
    cancel_event: asyncio.Event
    parent_run_id: str | None            # ownership-checked before use (INV-8/L16)
    checkpointer: object
    accumulated_outputs: dict[str, str] = field(default_factory=dict)  # legacy mirror during migration
    results: list[AgentResult] = field(default_factory=list)
    completed_tasks: list[dict] = field(default_factory=list)
    depth: int = 0                       # fan-out nesting (Q17)
    # strategy-local scratch (e.g. current task block) lives in the strategy, not here.

# --- declarative step (compiled from the manifest) ---
@dataclass
class Step:
    agent_id: str
    strategy: str = "single_shot"          # Q8/Q9
    gates: list[Gate] = field(default_factory=list)        # §9 (was a single gate)
    tools: ToolPermissions = field(default_factory=ToolPermissions)  # INV-9 / §8
    model: ModelPolicy | None = None       # §20 (step > agent > workflow > global)
    task_source: TaskSource | None = None  # Q10a/b
    validators: list[str] = field(default_factory=list)   # Q21
    fix: FixPolicy | None = None           # Q23/Q25
    compaction: str | None = None          # Q35
    fanout: FanoutSpec | None = None       # Q12 declarative
    on_conflict: str = "human_gate"        # §13: human_gate | merge_agent | partial | abort
    retry: RetryPolicy | None = None       # §21
    injects: list[str] = field(default_factory=list)

@dataclass
class CompiledWorkflow:
    id: str
    owner_id: str                          # never None — "anon:<session_id>" if unauthenticated (INV-8)
    workspace_id: str
    steps: list[Step]                      # topo-validated DAG
    context_providers: list[str]           # Q28
    seed_files: dict[str, SeedSource]      # Q29
    deliverable: DeliverableSpec           # Q26
    planner: str                           # "skip" | "run"  (Q30)
    clarify: ClarifySpec                   # mode + defaults (Q30)
    model: ModelPolicy                     # workflow default (§20)
    repo: RepoSpec | None = None           # §15 (brownfield)
    limits: Limits = field(default_factory=Limits)         # Q18/Q44

# --- canonical task (Q11) ---
@dataclass
class Task:
    id: str; title: str; body: str
    targets: list[str]                     # section selectors / file paths
    depends_on: list[str]
    parallel: bool
    conflict_keys: list[str]               # wave scheduling (Q32/Q33) + merge (§13)
    done_when: list[str]                   # Tier#5 / validators
    inputs: dict; outputs: dict

class TaskParser(Protocol):                # adapters → Task (Q11): heading_tasks | json_tasks | bracket_p
    def parse(self, text: str) -> list[Task]: ...

# --- capability ports ---
class ExecutionStrategy(Protocol):
    name: str
    async def run(self, step: Step, ctx: ExecutionContext) -> AsyncIterator[dict]: ...

class Validator(Protocol):
    name: str
    async def validate(self, target: "DeliverableContext") -> list["Issue"]: ...

@dataclass
class Issue:
    severity: str          # P0|P1|P2|P3 internally (Q24)  → CRITICAL/HIGH/MEDIUM/LOW externally
    code: str; message: str
    target: str | None = None
    fixable: bool = True

class DeliverableResolver(Protocol):
    name: str
    def resolve(self, ctx: ExecutionContext) -> str | "ArtifactRef": ...

class ContextProvider(Protocol):
    name: str
    async def load(self, ctx: ExecutionContext) -> dict[str, str]: ...   # block-name -> content

class GateHandler(Protocol):               # §9
    kind: str                              # human | validation | approval | security
    async def evaluate(self, step: Step, ctx: ExecutionContext) -> "GateOutcome": ...  # pass|block|wait_human

# --- security & policy (§8 / §20) ---
@dataclass
class ToolPermissions:                      # least-privilege grant set (INV-9)
    read_files: bool = True
    write_files: bool = False
    exec: bool = False                      # default OFF (N3)
    git: bool = False
    network: bool = False                   # default OFF
    secrets: list[str] = field(default_factory=list)     # named, scoped; default none
    mcp: list[str] = field(default_factory=list)          # allowed MCP tool names (§30); default none
    integrations: list[str] = field(default_factory=list) # allowed integration scopes (§30); default none
    spawn_subagents: bool = False

@dataclass
class ExecutionPolicy:                       # per-step runtime guardrails on the Workspace
    tools: ToolPermissions
    exec_allow: list[str] = field(default_factory=list)  # command allow-list (N3)
    exec_deny: list[str] = field(default_factory=list)
    network_allow: list[str] = field(default_factory=list)
    cpu_seconds: int | None = None
    mem_mb: int | None = None

@dataclass
class ModelPolicy:                           # §20
    model: str | None = None                 # None → inherit (step>agent>workflow>global Haiku)
    max_tokens: int | None = None            # doc-only; runtime caps at MAX_OUTPUT_TOKENS
    cost_class: str = "standard"             # cheap | standard | premium
    fallback: list[str] = field(default_factory=list)    # ordered model fallback on throttle/error

# --- typed artifacts with lineage (INV-10 / §17) ---
@dataclass
class ArtifactRef:
    id: str
    kind: str           # spec|plan|task_list|html_file|file_bundle|repo_inventory|repo_diff|context_pack|validation_report|merge_conflict|summary|patch
    owner_id: str; workspace_id: str; run_id: str      # INV-8
    producer_step: str; producer_agent: str; task_id: str | None
    content_hash: str                                   # content-addressed (replay/dedup)
    location: str                                       # sandbox path | store id | git ref
    version: int
    parents: list[str] = field(default_factory=list)    # lineage
    visibility: str = "private"                          # private | workspace | public
    retention: str = "run_ttl"                           # run_ttl | keep | days:N

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
    owner_id: str; workspace_id: str    # INV-8
    has_git: bool
    exec_policy: ExecutionPolicy

class IsolationProvider(Protocol):  # Q20/Q34
    async def allocate(self, ctx: ExecutionContext, scope: str) -> Workspace: ...  # shared_read | sub_sandbox | worktree

class MergeStrategy(Protocol):      # §13
    name: str
    async def merge(self, base: Workspace, fragments: list[Workspace]) -> "MergeResult": ...  # copy_disjoint|git_3way|json|html_fragment

class BudgetManager:                # Q18/Q44 — tokens, cost, subagents, depth, concurrency, wall-clock
    def reserve(self, *, tokens=0, subagents=0) -> None: ...   # raises BudgetExceeded
    def spent(self) -> "BudgetSnapshot": ...

# --- agent runtime & prompt assembly (§30) ---
class AgentRuntimeAdapter(Protocol):        # today: langchain_deepagents wraps LangChain deepagents.create_deep_agent (INV-13)
    name: str                               # langchain_deepagents (MANDATED) | claude_code_cli | custom_runner
    async def run(self, prompt: str, tools: list, ctx: ExecutionContext) -> AsyncIterator[dict]: ...

@dataclass
class PromptAssemblyPolicy:                  # declared block order (today hardcoded in factory.py:174-255)
    order: list[str] = field(default_factory=lambda: [
        "injects", "guardrails", "skills", "hooks", "constitution", "prompt_body"])

class HookHandler(Protocol):                 # EXECUTABLE lifecycle/tool-call hook (§30) — net-new
    name: str
    events: list[str]                        # before_write|pre_commit|post_commit|post_task|before_tool_call|... | "*"
    blocking: bool = False                   # a blocking hook can halt the offending action
    async def on_event(self, event: str, ctx: ExecutionContext, payload: dict) -> "HookOutcome": ...  # continue|warn|block

class McpClientAdapter(Protocol):            # CONSUME external MCP servers (§30) — net-new
    name: str                                # github | gitlab | jira | slack | filesystem | postgres | ...
    async def list_tools(self) -> list[dict]: ...                       # discover allowed tools/resources
    async def call(self, tool: str, args: dict, ctx: ExecutionContext) -> dict: ...
```

**Fan-out (engine-owned, INV-7).** A runner tool `spawn_subagents(tasks=[{agent, input}], mode=…)` is bound
**only** to steps whose `tools.spawn_subagents` is granted (INV-9). The tool **does not** spawn anything; it
emits a structured request the **kernel** fulfils: pick `IsolationProvider`, enforce `BudgetManager` + depth
cap, run via `asyncio.gather` (parallel, capped) or sequentially, route outputs to the `ArtifactGraph`,
`MergeStrategy` back (→ §13 on conflict), emit `subagent_*`/`merge_*` events, return files+summary (Q16-D).

## 7. Capability registry & trust model (Q2, Q27, INV-4)

- One `CapabilityRegistry` keyed by `(kind, name)` for: strategies, validators, deliverable resolvers,
  context providers, gate handlers, isolation providers, merge strategies, task parsers, worker agents,
  **agent runtimes, skill providers, hook providers, tool providers, MCP servers, integration providers** (§30).
- **Engineers register** capabilities in code at startup. **Manifests reference by name.**
- **Trust:** built-in/file manifests may reference any registered capability. **User/DB manifests** (later)
  are validated against a per-capability **`user_allowed: bool`** flag + the owner's allow-list — unknown,
  not-user-allowed, or not-owned (repos/workspaces) names → compile error. This is the seam that keeps
  fan-out / exec / secrets off the user palette until explicitly allow-listed (code-exec stays off until N3).

## 8. Tool permission policy & least privilege (A4 / INV-9 / N3)

Step-level permissions, enforced **before** brownfield/exec work exists so nothing ships over-privileged.

| Permission | Meaning | Default |
|---|---|---|
| `read_files` | read workspace/sandbox files | **ON** |
| `write_files` | create/edit deliverable files | OFF |
| `git` | branch/worktree/diff/commit (no push w/o N4) | OFF |
| `exec` | run shell/compile/test in the workspace | **OFF** (N3) |
| `network` | outbound network from a step/exec | **OFF** |
| `secrets` | named, scoped secret access | **none** |
| `spawn_subagents` | request engine fan-out (§6) | OFF |
| `mcp` | named MCP tools from allowed servers (§30) | **none** |
| `integrations` | named integration scopes (§30), e.g. `gitlab_read`, `jira_read` | **none** |

- **Resolution:** effective = `intersection(owner_allow_list, workflow_ceiling, step_grant)`. An agent's
  AGENT.md may declare a **default it can only lower**, never raise.
- **Enforcement points:** (1) `factory._build_runner_tools` binds only the granted tool sets; (2) the
  `Workspace.ExecutionPolicy` gates `exec`/`network`/`secrets` at runtime (allow/deny lists, resource caps).
- **Trust tie-in (§7):** user manifests may only grant from the user-allowed permission set; `exec`/`secrets`
  are never user-grantable until N3's threat model lands. Default-deny throughout.

## 9. Gate registry (A7)

Gates become first-class, registry-driven `GateHandler`s declared per step (`gates: [...]`, ordered),
evaluated by the kernel at the step boundary. Outcome ∈ `pass | block | wait_human`.

| Gate | Behavior | Today |
|---|---|---|
| `human` | review/approve/edit/reject — the existing `_run_review_gate` + `review_gate_*` events | ✅ works |
| `validation` | run the step's validators; block on policy (Q25); emit `validation_warning` on residuals | ⚠️ `Validation_Gate` declared in AGENT.md schema but **never implemented** — this makes it real |
| `approval` | explicit sign-off before a sensitive action (e.g. PR push, first `exec`) | new |
| `security` | gate `exec`/`network`/`secrets`/code-exec; default-deny until N3 | new (ties N3) |

The HITL `human` gate keeps **semantic event parity** (INV-3). `validation`/`approval`/`security` are additive.

## 10. Prototype re-expressed as a manifest (the parity proof — SC-001)

`agents/workflows/prototype/workflow.yaml` (illustrative):

```yaml
id: prototype
version: 1
model: { model: null, cost_class: standard }     # inherit global default (Haiku); §20
planner: skip                                     # was SKIP_PLANNER_FOR_PROTOTYPE (L5)
clarify:
  mode: always                                    # was ALWAYS_CLARIFY
  defaults: [target_audience, scope, priority, style]   # was the L6 dict entry
context_providers: [opendesign]                   # was od_context branches (L12)
seed_files:                                       # was _write_build_reference_files (L11)
  spec.md:  { from: prototype-specify }
  tasks.md: { from: prototype-plan }
  design.md: { from_provider: opendesign }         # template_body + ds_body
deliverable: { strategy: single_file, name: prototype.html }   # was L2/L10
limits: { max_subagents: 0, max_concurrency: 1 }               # prototype = sequential (Q33)
steps:
  - { agent: prototype-specify, gates: [human], tools: { read_files: true } }
  - { agent: prototype-plan,    gates: [human], tools: { read_files: true } }
  - agent: prototype-build
    strategy: task_loop                            # was the L7 spec.id branch
    tools: { read_files: true, write_files: true }  # least-privilege (INV-9): no exec/net/spawn
    task_source: { from: prototype-plan, parser: heading_tasks }   # was _count/_extract (L11)
    compaction: html_skeleton                       # was the dead L13 helper (now wired; Q35/Tier#1)
    validators: [html_static, html_render]          # was _run_validation_fix_loop (L11)
    fix: { max_attempts: 2, policy: warn_noncritical_block_critical }
  - { agent: prototype-validate, tools: { read_files: true, write_files: true } }
```

`od_prototype` = same manifest with the OpenDesign provider configured (alias → same plan). `prototype_revision`
= a variant with `seed_files.parent: { from_run: parent }` (ownership-checked, INV-8) + the revision deliverable
+ a post-edit `validation` gate (was L4/L8). **Acceptance:** **identical `prototype.html` (deterministic)** + **semantic event parity** as today
(characterization tests), with L1–L16 branches deleted from the kernel.

## 11. Leak → new-home mapping (every L# from §4)

| Leak | New home |
|---|---|
| L1 names/`REVISION_FILE_NAME` | manifest `deliverable.name` + `seed_files`; no frozensets |
| L2 `_resolve_final_output` | `DeliverableResolver` registry |
| L3 carousel/`<artifact>` | a `ppt` `DeliverableResolver` + a `ppt` post-step transform/validator |
| L4 revision seeding/baseline | `seed_files.from_run` + `previous_run` ContextProvider (ownership-checked); baselines = validator concern |
| L5 skip-planner | manifest `planner: skip` |
| L6 clarify defaults | manifest `clarify.defaults` |
| L7 build-loop dispatch | `strategy: task_loop` from the step (Q9) |
| L8 post-revision fix | `validation` gate + `task_loop`/validators on the revision step |
| L9 final-output + sanitize | `DeliverableResolver.resolve()` |
| L10 HTML read-back | `task_loop` reads the declared `deliverable.name` from the workspace |
| L11 build-loop internals | `TaskLoopStrategy` + `TaskParser` + `Validator`s + generic fix-loop + `seed_files` |
| L12 context injection | `ContextProvider(opendesign)` + per-agent `injects` resolved by a generic injector |
| L13 dead skeleton | `CompactionStrategy(html_skeleton)` via `compaction:` (Tier#1) |
| L14 singleton state | `ExecutionContext` (Phase 0) |
| L15 untyped handoff | `ArtifactGraph` + `ArtifactRef` (§17); `accumulated_outputs` kept as a mirror during migration |
| L16 unchecked parent seeding | ownership check at the store layer (INV-8 / §19) |

## 12. Fan-out & sub-agents (Q12–Q20) — interfaces now, build in Phase 5

- **Two entry points:** declarative (`step.fanout`) and runtime (`spawn_subagents` tool, gated by `tools.spawn_subagents`). Both funnel through one kernel `run_fanout(requests, ctx)`.
- **Worker selection (Q14):** `agent="self"` (N copies) or a named worker in the workflow's `allowed_workers` + registry.
- **Mode (Q15):** `parallel` (capped `asyncio.gather`) or `sequential`; engine enforces `max_concurrency`.
- **Isolation (Q20/Q34):** `IsolationProvider.allocate(scope)` → shared-read | sub_sandbox | worktree; writes default isolated.
- **Merge (Q16-D):** results land as artifacts; `MergeStrategy` integrates; conflicts → §13.
- **Nesting/limits (Q17/Q18):** `ctx.depth` capped; `BudgetManager` enforces subagents/concurrency/tokens/cost/wall-clock; `BudgetExceeded` aborts gracefully (partial results surfaced).
- **Persistence:** each child is a `subagent_runs` row (§18); events `subagent_spawned`/`subagent_result`.

## 13. Merge conflict flow (A6)

When `MergeStrategy.merge` reports conflicts (overlapping `conflict_keys`/files, failed 3-way):

1. Write a `merge_conflict` `ArtifactRef` (the conflicting hunks/files) and emit a `merge_conflict` event.
2. Resolve per the step's `on_conflict` policy:
   - **`human_gate`** (default) — pause via a `human` gate showing the conflict; resume on user resolution.
   - **`merge_agent`** — spawn a designated merge worker (bounded attempts) to auto-resolve, then re-validate.
   - **`partial`** — keep non-conflicting fragments, mark conflicted tasks failed, continue; surface in the report.
   - **`abort`** — fail the wave/run.
3. Applies to fan-out (Phase 5), waves (Phase 6), and worktree merges. Bounded `merge_agent` retries (avoid oscillation).

## 14. Workspace / RuntimeEnvironment layer (Q-N1, N2, N7) — interfaces now, `LocalSandboxRuntime` only

- **One `Workspace`** abstraction: filesystem + optional git + optional exec + `ExecutionPolicy`. Prototype's
  `RunSandbox` becomes a `Workspace` with `has_git=False, exec=off`. **No engine fork** for repo vs artifact (R3).
- **`LocalSandboxRuntime`** implements the port over the per-run disk dir (clone into the run dir, local
  branch/worktree, `git diff`). **`EcsRuntime` deferred** (§27) behind the same port.
- **Repo workflow (local):** `clone_repo` → `create_branch`/worktree → repo inventory (§15) → agents
  read/edit/search → `DeliverableResolver(repo_diff)` → app-builder-style **file tree + diff** (Q-N7) — this is
  **Phase 4A (no exec)**. `exec` + compile/test/lint validators behind the `security` gate are **Phase 4B**
  (after the N3 threat model). PR push waits on git-hosting (N4).

## 15. Repo index / context selection (A5 / N6)

Codex-like repo work needs more than `search()`. Three first-class artifacts/providers:

- **`RepoInventory`** (`kind=repo_inventory`) — file tree, language stats, dependency graph, **ignore rules**
  (`.gitignore` + `.flowinignore`), **binary-file skip**, size caps, optional per-dir/file **summaries**.
  Produced by a `repo_inventory` step/provider after clone.
- **`RepoIndex`** (optional, large repos) — symbol/embedding index behind a port; default = grep/glob for small
  repos. The grep-vs-index threshold is **N6** (repo scale).
- **`ContextPack`** (`kind=context_pack`) — the **targeted subset** (files/snippets) an agent needs for a task,
  built by a `context_selector` capability; avoids dumping the repo into context (the brownfield analog of the
  prototype `html_skeleton` compaction). Lineage-tracked, per task.
- Surfaced to agents via the `repo` `ContextProvider`.

## 16. Validation framework & severity (Q21–Q25)

- `Validator` registry; manifest lists `validators: [...]` per step. `DeliverableContext` carries path,
  content, `Workspace`, and task meta, and may request a browser/compile/test/static-analysis runner (Q22).
- **Generic fix-loop** (replaces L11's HTML-hardcoded one): deliverable name + `max_attempts` + fix-prompt
  template from `FixPolicy`. Default **warn on non-critical, block on critical** (via the `validation` gate, §9),
  then emit `validation_warning` with residuals (Q25, lands Tier#9). Each run/attempt → `validation_results` row (§18).
- **Severity:** internal `P0/P1/P2/P3`; one mapping function exposes `CRITICAL/HIGH/MEDIUM/LOW` to the UI (Q24).
- **Tier #4/#5/#6** ship as registered validators: `spec_plan_coverage` (pre-build analyze), `task_done_when`
  (per-task acceptance), `design_quality` (tokens/placeholder/a11y, warnings-first).

## 17. Artifact graph & lineage (A8 / INV-10)

- `ArtifactGraph` = the typed, **content-addressed**, **owner-scoped** DAG of `ArtifactRef`s for a run (and
  across runs via `parents`). Replaces the loose `accumulated_outputs: dict[str,str]` (L15) and the thin store.
- Every write records producer step/agent/task, `content_hash`, `version`, `parents`, `visibility`, `retention`.
- Powers: typed `produces`/`consumes` routing (not string matching), revision lineage (`derived_from`),
  dedup/replay, deliverable resolution, and debugging ("what produced this, from what"). Retention default
  `run_ttl` (= the 48h sandbox TTL) unless `keep`/`days:N` (N9).

## 18. Persistence schema (A2 / Q45)

New/extended tables (all carry `owner_id` + `workspace_id`; additive migrations only, Q3):

| Table | Key columns |
|---|---|
| `workflows` (definitions) | id, owner_id, workspace_id, source(`file`/`db`), manifest_json, version, created/updated |
| `workflow_runs` *(extend)* | + workspace_id, owner_id, parent_run_id, source_run_id, plan_id, status, budget_snapshot_json |
| `artifact_refs` | full `ArtifactRef` (§17) + FKs(run_id, owner_id, workspace_id); idx (run_id, kind), (content_hash) |
| `workspaces` | id, owner_id, kind(`sandbox`/`repo`), repo_id?, runtime(`local`/`ecs`), created, ttl |
| `repositories` | id, owner_id, provider(`github`/`gitlab`/`local`), url, default_branch, auth_ref(scoped), created |
| `subagent_runs` | id, parent_run_id, parent_step, worker_agent, depth, isolation, workspace_id, status, tokens, cost |
| `wave_runs` | id, run_id, step, wave_index, task_ids[], status |
| `validation_results` | id, run_id, step, validator, severity, code, message, target, attempt, created |
| `gate_events` | id, run_id, step, gate_kind, outcome, actor, created |
| `run_events` | id, run_id, **seq** (monotonic per run), event_id, type, payload_json, created; idx (run_id, seq) — durable event log for replay/resume (§21/§22) |
| `run_capabilities` | id, run_id, runtime, **model_overrides{agent→model}** (§20), skills[], hooks[], integrations[], mcp_servers[], versions — **what was active** for replay/debug (§30); **nothing recorded today** |
| `hook_runs` | id, run_id, step, hook, event, outcome(`continue`/`warn`/`block`), blocking, detail, created — executable-hook firings (§30) |

Migrations live in the existing migrations dir (002 referenced migration 0013). A retention sweep aligns
`artifact_refs`/`workspaces` with the sandbox TTL.

## 19. Authorization & multi-user boundaries (A3 / INV-8)

- **Ownership model:** `user → workspace → (repository | project) → run → {artifacts, subagent_runs}`.
  Everything carries `owner_id` + `workspace_id`.
- **Default-deny:** a run may only read/seed from a `parent_run`/`source_run`/artifact/workspace/repo it owns
  (or that is shared at `workspace` visibility). The current `parent_run_id` seeding (`engine.py:583-610`, L16)
  reads `RunSandbox(user_id, parent_run_id)` keyed on the same user **implicitly** — make it an **explicit,
  enforced** check that rejects cross-owner access.
- **Enforcement at the store/repository layer** (a single scoped-query helper), not scattered in callers — mirrors
  how `RunSandbox` already namespaces by user on disk. All artifact/run reads go through it.
- **Anonymous runs are allowed but never `None`-owned:** an unauthenticated run gets a synthetic owner `anon:<session_id>` so every scope check has a real principal and artifacts/workspaces stay isolated per session.
- **User-authored workflows** (later): may only reference owned repos/workspaces + user-allowed capabilities (§7/§8).

## 20. Model policy + per-agent model selection (A10 / A12)

- **Resolution order (highest wins):** **user per-agent override (UI)** > `step.model` > agent default (AGENT.md) > `workflow.model` > global default (Haiku). A `ModelResolver` on `ExecutionContext` applies it per agent invocation via `model_factory.build_model`.
- **User picks any model for any agent (A12).** The composer shows every agent in the workflow with a **model dropdown** drawn from the allowed **`ModelCatalog`**; the chosen map `model_overrides: {agent_id → model_id}` rides in the run payload (extends today's single session-level `model_id`), is applied at the **top** of the resolution order, and is **persisted per run** (`run_capabilities`, §18) for replay. Selection is from the allow-listed catalog (Q2 trust), never arbitrary strings.
- **`ModelCatalog`** — a registered capability listing selectable models with `label`, `provider`, `cost_class` (`cheap`/`standard`/`premium`), context window, and `user_allowed`. Surfaced via `/api/capabilities` (§22) so the UI renders real options (no hardcoded list).
- **Fields (per `ModelPolicy`):** model id, `max_tokens` (doc-only; runtime caps at `MAX_OUTPUT_TOKENS`), `cost_class`, ordered `fallback` chain (on provider throttle/error → next model).
- **Budget tie-in:** `cost_class` informs `BudgetManager`; a `premium` choice on one agent upgrades just that step. (Resolves/extends N11.)

## 21. Cancellation, retry & resume (A9)

- **Cancellation:** cooperative `cancel_event`, checked per-chunk **and** at step/gate/fanout/wave boundaries.
  On cancel → mark run `cancelled`, **preserve partial artifacts** (lineage), `teardown()` isolated workspaces,
  emit `pipeline_cancelled`. Fan-out cancellation **propagates to children**.
- **Retry (idempotent):** per-step `retry: {max, on}` for **transient** errors (provider/throttle) — distinct
  from the validator **fix-loop** (which refines content). A step is keyed by `(run_id, step_id, input content_hash)`;
  re-entry **reuses the existing artifact** if the hash matches (no duplicate work).
- **Resume:** durable **step-level** run state (status per step) + the LangGraph checkpointer (per-agent thread)
  + `artifact_refs`. Every emitted event carries a **monotonic per-run `seq` + `event_id`**, persisted to
  `run_events` (§18). **Reconnect** = replay from the durable log via `after=<last_seq>` (§22), idempotent by
  `event_id` (no loss, no double-apply). **Server restart** = `restore_non_terminal_runs` extended to step
  granularity: a `waiting_for_user` gate resumes on user action; an in-flight step resumes from its checkpoint
  or re-runs idempotently. Long brownfield jobs (N8) resume **mid-wave** via `subagent_runs`/`wave_runs` records.

## 22. API / frontend contract (A1)

The composer must become **dynamic** — no hardcoded workflow types or flat agent sequences. Backend endpoints:

- `GET /api/workflows` → list + metadata (id, name, description, step summary).
- `GET /api/workflows/{id}` → full step configs, gates, validators, deliverable, declared capabilities.
- `GET /api/capabilities` → registry (kind, name, `user_allowed`, config schema) — the composer **palette** (§7), incl. **runtimes, skills, hooks, MCP servers, integration tools, the model catalog (§20)** with their **required auth + permission scopes** (§30).
- run stream (WS/ndjson) → existing events **+** new (Q43): `subagent_*`, `wave_*`, `validator_result`,
  `validation_warning`, `merge_*`, `budget_warning`, `gate_*`.
- `GET /api/runs/{id}/artifacts` → typed artifact tree (lineage); `GET /api/runs/{id}/diff` → repo diff.
- `GET /api/runs/{id}/events?after=<seq>` → **durable event replay** (each event carries a monotonic `seq` + `event_id`; §18 `run_events`, §21) for reconnect/resume.
- subagent tree + wave view derived from events / `subagent_runs` / `wave_runs`.

**Frontend track (parallel, flagged per phase):** dynamic composer + capability palette + **per-agent model picker (§20)**; validator/issue panel;
subagent + wave tree; artifact/diff viewer (**reuse the app-builder `FilesTab`/`AppBuilderPreview`** for
`repo_diff`/`file_bundle`). The event contract for **existing** workflows stays at **semantic parity** (INV-3); all new
panels are additive. Risk R6 is now this section, not a footnote.

## 23. Budgets, limits, observability (Q18, Q43, Q44)

- `BudgetManager` per-run **and** per-workspace ceilings (tokens, €, subagents, depth, concurrency, wall-clock);
  reserve-before-spawn; graceful abort; snapshot persisted on the run (§18).
- New events (Q43): `subagent_*`, `wave_start`/`wave_complete`, `validator_result`, `validation_warning`,
  `merge_*`, `gate_*`, `budget_warning`. Existing events stay at **semantic parity** for migrated workflows (INV-3).
- **Logging/tracing hooks** (§30) bound to `"*"` emit OpenTelemetry-style spans/logs per lifecycle event → the native observability path (no bespoke instrumentation per capability); each firing also lands in `hook_runs` (§18).

## 24. Backward-compat & testing strategy (Q3, Q40, INV-3)

- **Characterization tests FIRST (Phase 0A):** for `prototype`, `od_prototype`, `prototype_revision`,
  `ppt`/`od_ppt`, and one code-gen pipeline, driven by a scripted model (`tests/agents/_scripted_model.py`):
  - **Deliverable snapshot** — byte-for-byte where the output is deterministic.
  - **Semantic event snapshot** — event *types*, order, and required fields + the final result, with volatile
    fields **normalized out** (timestamps, streamed-text chunk boundaries, generated IDs, token/usage counts,
    durations). The monotonic event `seq` (§21) is asserted **contiguous**, not by absolute value.
- Per-capability suites as each registry lands; **authz denial tests** (cross-owner parent/artifact access) from Phase 1B.
- Phase 0C and any prompt/compaction change is gated on the **semantic** snapshot + a measured token/cost delta,
  **not** byte-identity (a context change can legitimately alter generated text).
- Each phase leaves snapshots green before merge. No dual-path flags left behind (INV-3).

## 25. Phase plan

> Strangler migration (Q39). Each phase is independently shippable and keeps prototype working.
> **Definition of Done includes deletion (INV-12 / §31):** a phase that adds an abstraction without deleting the code it supersedes — and proving it via the grep/dead-code gate — is **not done**. The §31 ledger tracks every legacy element → new home → phase → deletion gate → status.

**Phase 0A — Safety net + deletion guard.** Characterization tests (§24) — deliverable + semantic-event snapshots for
prototype/od_/revision/ppt/code-gen — **plus the §31 migration-ledger CI guard**: `tests/test_migration_ledger.py` (asserts each `☑` item's banned grep-pattern returns 0) + the **import-linter** contract (kernel imports only ports). Both start green/empty and tighten as items are deleted; no runtime behavior change. *Accept:* snapshots recorded + green; ledger guard + import-linter run in CI.

**Phase 0B — `ExecutionContext` + ownership.** Extract all `self._*` run state into `ExecutionContext` (L14);
add the **explicit ownership check** on `parent_run` seeding (L16/INV-8). **No behavior change.** *Accept:*
snapshots green (deliverable byte-identical); kernel has no per-run attributes (NFR-001); cross-owner parent seed rejected.

**Phase 0C — Token-trim (measured change).** Wire the dead `_extract_html_skeleton` as the build-task-2+ context
compaction (Tier#1). This **alters build prompts → generated text may differ**, so it is gated on the **semantic**
snapshot (same pages/routes, equal-or-better validation pass) **+ a measured token/cost delta**, not byte-identity.
*Accept:* equal-or-better validation pass rate; measured token reduction on a multi-task build.

**Phase 1A — Manifest + compiler (legacy artifact mirror).** `WorkflowManifest` (file-backed, **hand-authored**)
+ `WorkflowCompiler` → `CompiledWorkflow`. Existing pipelines run from a compiled plan; artifacts still flow via
the legacy `accumulated_outputs` mirror (no schema change yet). *Accept:* every current pipeline runs from a
compiled plan; snapshots green.

**Phase 1B — Typed artifacts + persistence (dual-write).** `ArtifactGraph`/`ArtifactRef` (§17) + the persistence
schema (§18: `artifact_refs`, extend `workflow_runs`, `workspaces`, `run_events`); **dual-write** typed refs
alongside the legacy mirror, migrating reads incrementally. *Accept:* artifacts typed + lineage-tracked + persisted;
**authz denial tests** (cross-owner) pass; snapshots green.

**Phase 1C — Model policy.** `ModelResolver` (§20): resolution order + fallback chain + cost_class. *Accept:*
per-step/workflow model honored; global default unchanged (Haiku).

**Phase 2 — Prototype as manifest (parity proof, SC-001).** Implement `single_shot` + `task_loop` strategies,
`single_file`/`serialized_sandbox`/`streamed_text` resolvers, `opendesign` provider, `seed_files`, `heading_tasks`
parser, and `html_skeleton` as a registered `CompactionStrategy` (re-expressing the Phase 0C trim behind the
capability — behavior-preserving vs 0C). **Delete L1–L16 kernel branches.** *Accept:* prototype/od_/revision/ppt/code-gen
at **deliverable parity + semantic event parity** (vs the post-0C baseline) with **zero name/id branches** in the kernel (grep gate, INV-1).

**Phase 3 — Capabilities hardened: registries + gates + tool perms.** Formalize `CapabilityRegistry` + trust flags
(§7); `GateHandler` registry (`human`/`validation`/`approval`/`security`, §9) — make `Validation_Gate` real;
`ToolPermissions` enforcement at `factory._build_runner_tools` (§8/INV-9); migrate `html_static`/`html_render`
validators + generic fix-loop; severity mapping; `validation_warning`. *Accept:* validators+gates registry-driven;
least-privilege enforced; Tier#4/5/6 land as validators (Q38).

**Phase 4A — Local Workspace runtime + repo workflows (no exec).** `RuntimeEnvironment` port + `LocalSandboxRuntime`;
`Workspace` + `ExecutionPolicy` (**exec off**); `repositories`/`workspaces` rows; repo inventory/index/context-pack
(§15); `repo_diff` resolver. First brownfield workflow end-to-end locally **without execution** (clone → branch →
inventory → agents read/edit/search → diff surface). *Accept:* a sample repo workflow produces a diff; **no `exec`**;
prototype unaffected.

**Phase 4B — Safe local exec (gated on N3).** After the N3 threat model: enable a constrained `exec` profile behind
the `security` gate (command allow/deny, network default-deny, resource caps, ephemeral creds) + compile/test/lint
validators. *Accept:* `exec` runs only under the `security` gate + `ExecutionPolicy`; egress denied by default; a
sample compile/test validator passes.

**Phase 5 — Engine-owned fan-out + merge.** `spawn_subagents` tool (gated) + kernel `run_fanout`;
`IsolationProvider` (sub_sandbox/worktree) + `MergeStrategy` + **merge-conflict flow** (§13); `BudgetManager`;
depth/concurrency caps; `subagent_runs` persistence; cancellation propagation (§21); `subagent_*`/`merge_*` events.
*Accept:* an agent fans out N workers under caps; results merge deterministically; conflicts follow `on_conflict`;
budgets abort gracefully.

**Phase 6 — Wave scheduler + durable resume.** `wave_scheduler` strategy: topo-sort by `depends_on` +
`conflict_keys` into waves, run each wave via fan-out; `wave_runs` persistence; resume **mid-wave** (§21). Enabled
for multi-file workflows; **prototype stays sequential** (Q33). *Accept:* a multi-file workflow runs disjoint tasks
in parallel waves; a restart resumes mid-wave; CP-SAT seam left (Q32).

**Phase 7 (later) — ECS/EC2 runtime** behind the unchanged `RuntimeEnvironment` port (separate spec; §27).

*Cross-cutting:* the **frontend contract (§22)** is a parallel track touched every phase (new events/panels);
**cancellation/retry/resume (§21)** is basic in Phase 0 and hardened through Phases 5–6.

## 26. Open decisions (decision records — confirm before the relevant phase)

- **N1 ✅ DECIDED** — Local runtime now; ECS later behind the port.
- **N2 (Phase 4)** — *Proposed:* isolation granularity MVP = **ephemeral per-run local**; abstraction allows warm/dedicated later. **Confirm.**
- **N3 (Phase 4 exec) ⚠️ OPEN — highest risk** — Local `exec_command` security: network egress (none/allow-list), secrets (none-by-default/scoped), credentials (ephemeral), command allow/deny, resource caps. **Own threat-model decision; code-exec disabled (security gate) until set.**
- **N4 (Phase 4+)** — Git hosting scope/order. *Note:* your repo is GitLab (`hexaware-uki/flowin`) → GitLab likely required. **Confirm GitHub-first vs GitLab-first vs both.**
- **N5 (Phase 4)** — *Proposed:* branch/PR **manifest-declared, runtime-enforced** (`base_branch`, `working_branch`, `commit_policy`, `pr_policy`); v1 = **diff-only, no PR push** until N4. **Confirm.**
- **N6 (Phase 4)** — Target repo scale (kLOC / file count) → grep-vs-index threshold for §15. **Provide a ballpark.**
- **N7 (Phase 4)** — *Proposed:* repo deliverable = app-builder-style **file tree + per-file diff + test/build results + summary** (PR link when N4 lands). **Confirm.**
- **N8 (Phase 4+)** — Long-job orchestration substrate. *Proposed:* in-process (FastAPI task) for local v1; durable queue/worker is an infra follow-up. **Confirm.**
- **N9 (Phase 1)** — Artifact **retention** default. *Proposed:* `run_ttl` (= 48h sandbox TTL); `keep` for deliverables surfaced to the user. **Confirm.**
- **N10 (Phase 4)** — `RepoIndex` approach for large repos: grep-only vs symbol index vs embeddings (tied to N6). **Confirm when N6 known.**
- **N11 (Phase 1)** — Model policy: global default (Haiku) + whether `premium` models are allowed per workflow, and the default fallback chain. **Confirm.**
- **N12 ✅ DECIDED (Phase 3+)** — Hooks are **executable lifecycle/tool-call hooks** (secret-scan, logging/tracing, pre/post-commit, post-task, before/after-write, …), not prompt-only. `HookHandler` + lifecycle events + blocking outcomes + `hook_runs` persistence (§30/§18). The legacy behavioral/prompt hook (`factory.py:230-245`) remains a non-executable sub-type.
- **N13 ✅ DECIDED (Phase 4+)** — Adopt an **MCP client** (`langchain-mcp-adapters`) and integrate **all famous MCP servers** via an allow-listed catalog (GitHub/GitLab/Jira/Confluence/Slack/Notion/Sentry/Figma/Filesystem/Postgres/…), each with scoped per-owner creds + the `security` gate (§30/§7/R13).

## 27. Non-goals / deferred (designed-for, not built here)

ECS/EC2 provisioning · warm/dedicated containers · container networking & cloud secrets injection · production
container teardown/lease mgmt · CP-SAT scheduling (topo seam only) · single-file fragment-merge parallelism
(prototype stays sequential) · untrusted **end-user code execution** (trust seam exists; capability stays
engineer-only + `security`-gated until N3) · PR/commit **push** (diff-only until git-hosting integration, N4).
All sit behind interfaces defined in this spec so each is a **backend swap, not a rewrite**.

## 28. File-by-file change map (initial)

- `agents/execution_engine/engine.py` → split into `kernel.py` (workflow-agnostic) + delete L1–L16 branches.
- new `agents/execution_engine/context.py` — `ExecutionContext` (Phase 0).
- new `agents/workflows/` — `manifest.py`, `compiler.py`, `plan.py`, `<id>/workflow.yaml` per workflow.
- new `agents/capabilities/` — `registry.py` + `strategies/`, `validators/`, `deliverables/`, `context_providers/`, `gates/`, `policy/` (model + tool resolution), `isolation/`, `merge/`, `task_parsers/`, `repo/` (inventory/index/context_selector).
- new `agents/authz.py` — ownership-scoped query/seed helpers (INV-8).
- new `app/agents/runtime/` — `base.py` (`RuntimeEnvironment`/`Workspace`/`ExecutionPolicy` ports), `local.py` (`LocalSandboxRuntime`).
- new `app/agents/tools/fanout.py` — `spawn_subagents` (Phase 5).
- `app/agents/static_check.py` / `render_check.py` → wrapped as registered `Validator`s.
- `app/models/` — extend `workflow.py`/`workflow_definition.py`; new `artifact_ref.py`, `workspace.py`, `repository.py`, `subagent_run.py`, `wave_run.py`, `validation_result.py`, `gate_event.py`; new migrations (§18).
- `app/api/` — new `workflows.py`, `capabilities.py`; extend run/artifact/diff endpoints (§22).
- `agents/registry.py` — `PIPELINE_AGENTS` superseded by **hand-authored** built-in `workflow.yaml` manifests (one per workflow); `pipeline_type` kept as an alias; an auto-generated manifest **index** is optional later (never the source of truth).
- frontend — dynamic composer + capability palette + validator/subagent/wave/diff panels (parallel track, §22).
- tests — `tests/agents/test_characterization_*.py` (Phase 0); per-capability + authz suites after.

## 29. Risks

- **R1 Parity regression** — behavior secretly encoded in `engine.py`. *Mitigation:* Phase 0 characterization snapshots; INV-3.
- **R2 Compiler scope-creep into a DSL** — *Mitigation:* INV-5; manifest is data, strategies hold logic.
- **R3 Two engines** (artifact vs repo) — *Mitigation:* one `Workspace` abstraction (INV-6); prototype = git-off Workspace.
- **R4 Fan-out cost/recursion blowups** — *Mitigation:* `BudgetManager` + depth/concurrency caps; engine-owned (INV-7).
- **R5 Code-exec security** — the scariest surface. *Mitigation:* N3 own spec; `security` gate default-deny; off the user allow-list.
- **R6 Frontend lag** — now a first-class deliverable (§22), not a footnote. *Mitigation:* dynamic metadata/events; parallel track per phase.
- **R7 Durable resume for long jobs** — *Mitigation:* typed artifacts + step/subagent/wave run records (§18/§21); N8.
- **R8 Cross-tenant leakage** — *Mitigation:* INV-8; store-layer scoped queries; ownership denial tests from Phase 1.
- **R9 Persistence migration risk** — *Mitigation:* additive migrations only (Q3); back-compat columns; staged rollout.
- **R10 Model cost / throttle** — *Mitigation:* `cost_class` + `BudgetManager` + fallback chain (§20).
- **R11 Merge-conflict oscillation** — *Mitigation:* bounded `merge_agent` attempts; `on_conflict` policy; human gate fallback (§13).
- **R12 Constitution injection no-op (existing bug)** — `_inject_constitution` reads only the in-process `_mem` dict when an event loop is running (`factory.py:282-290`), so a Postgres-stored Constitution is **silently NOT injected** in production. *Mitigation:* fix in Phase 3 (sync-safe await / pre-warm the cache); until then the "supreme authority" claim (§19) is unenforced.
- **R13 Capability auth & secrets (MCP / integrations / executable hooks)** — external MCP servers, integrations, and executable hooks (esp. those with `exec`/`network`/`secrets`) widen the attack surface and need scoped, per-owner credentials (the GitHub-PAT precedent, `handoff.py:40`). *Mitigation:* `secrets`/`integrations`/`mcp` permissions (§9) + scoped creds + the `security` gate + a **`secret_scan`** hook (§30); powerful MCP servers (filesystem/postgres) and executable hooks are engineer-registered + allow-listed, never user-grantable until reviewed (§7/§30).
- **R14 Duplication / dead-code drift** — the migration could leave new capabilities *beside* the old branches → two code paths, the exact "duplicate code all over" failure. *Mitigation:* INV-12 (move-don't-copy) + the §31 deletion ledger + per-phase grep banned-pattern gates + a dead-code scan + an import-linter (kernel imports only ports, never legacy `engine`/`factory` internals); a phase is not done until its ledger deletions are proven.
- **R15 Hand-rolled / hallucinated "deep agent"** — an implementer (human or LLM) defines a custom `DeepAgent` class, **creates a local `deepagents`/`langchain_deepagents` module/package**, or re-implements the agent loop instead of importing the real LangChain library (the exact regression 002 fixed). *Mitigation:* INV-13 + a permanent **banned-pattern CI gate** (`class DeepAgent` / `def deep_agent` / a new module named `deepagents` or `langchain_deepagents` / bespoke `for _ in range(max_iterations)` loops outside the `langchain_deepagents` adapter → fail) + the import-linter (only `app/agents/runtime` + that adapter may `from deepagents import …`; importing a non-existent `langchain_deepagents` package is forbidden).

## 30. Agent runtime, skills, hooks, MCP & integrations (A11 / INV-11)

Skills, hooks, the agent runtime, MCP, and external integrations are **first-class, owned, allow-listed, permissioned capabilities** — **not** arbitrary prompt text or unconstrained tools. The kernel is unchanged; the `CapabilityRegistry` (§7) gains these kinds.

> **The rule:** MCP, integrations, skills, and hooks are **capabilities with ownership (INV-8), allow-lists (§7 trust), and permissions (§8/§9)** — never free-form prompt text or arbitrary tools.

### Capability kinds — current state (grounded in code)

| Kind | Examples | Current state (`file:line`) |
|---|---|---|
| `agent_runtime` | **`langchain_deepagents`** = LangChain `deepagents` (`create_deep_agent`, pinned `0.6.7`, per 002) — the **MANDATED** runtime (INV-13); future `claude_code_cli`/`custom_runner` are *added* adapters | **Hardcoded** — `create_deep_agent` is called in exactly one module (`deep_agent_runner.py:240`); `create_runner` always builds a `DeepAgentRunner` (`factory.py:152`). No selection seam → `AgentRuntimeAdapter` **net-new** (wraps the library; never replaces/​reinvents it). |
| `skill_provider` | UI skills · disk `SKILL.md` (user→global→built-in) · template/repo skills | **Partially exists** — disk hierarchy `skills.py:320` (`get_skill_content`), loaded `engine.py:655`; UI via `AgentContext.attached_skills` (`factory.py:42`, WS `websocket.py:421`); merged UI-first/disk-last `engine.py:1167-1172`; both flattened into one `content` list (no provider interface, no versioning). |
| `hook_provider` | **executable** — secret-scan · logging/tracing · pre/post-commit · post-task · before/after-write · before/after-step (+ legacy behavioral/prompt hooks) | **Today: prompt-only** — `attached_hooks` (`factory.py:43`) synthesized into a bullet list under `## Active Behavioral Hooks` (`factory.py:230-245`); runtime-only, no REST/DB, not executed. **Target: EXECUTABLE** (see "Executable hooks" below; N12 ✅). |
| `tool_provider` | deepagents native FS · `report_task_complete` · `PLANNING_TOOLS` · repo tools · fan-out | **Closed enum** — `_build_runner_tools` name→toolset switch that **raises on unknown** (`factory.py:384-446`); `task` force-excluded via `_ToolFilterMiddleware` (`deep_agent_runner.py:118-157,227`). |
| `mcp_server` | **all famous MCP servers** — GitHub, GitLab, Jira/Atlassian, Confluence, Slack, Notion, Linear, Sentry, Figma, Filesystem, Postgres, web-search, … | **Net-new (consumer)** — backend is an *inbound* MCP **server** only (`mcp.py:48`); no MCP **client**, `langchain-mcp-adapters` not a dep. **Target: adopt an MCP client + catalog** (see "MCP integration" below; N13 ✅). |
| `integration_provider` | GitHub · GitLab · Jira · Slack · Confluence · Figma · OpenDesign | **Partially exists** — GitHub via the **separate handoff pipeline** (`handoff_github.py`; scoped PAT `handoff.py:40`; REST `settings.py:125`) which **bypasses the deepagents runtime** (`coding_agent.py:164`); OpenDesign via `od_context`/`injects` (`od_loader.py`, `factory.py:309`). All others absent. |

### Declared per step (manifest)

```yaml
runtime: langchain_deepagents
skills: [opendesign_template, repo_conventions]
hooks:                                                # EXECUTABLE, lifecycle-bound (§30)
  - { name: secret_scan,      on: [before_write, pre_commit], blocking: true }
  - { name: otel_tracing,     on: ["*"],        blocking: false }   # logging/tracing
  - { name: post_task_summary, on: [post_task] }
integrations: [gitlab_read]                           # scoped integration capabilities
mcp_servers: [github, jira, slack]                    # from the famous-MCP catalog (§30)
tools: { read_files: true, write_files: true, git: true, spawn_subagents: false,
         mcp: ["github.search_issues", "jira.search", "slack.post_message"],
         integrations: ["gitlab_read"] }
```

### The 6 expected changes (where they land)

1. **`AgentRuntimeAdapter`** (§6) — wraps today's `create_deep_agent`; lets `claude_code_cli`/`custom_runner` slot in without touching the kernel. **Phase 3.**
2. **`PromptAssemblyPolicy`** (§6) — block order is hardcoded inline (`factory.py:174-255`: injects→guardrails→skills→hooks→constitution→body, joined `\n\n`). Promote to a declared, registry-resolved policy. **Phase 3.**
3. **`McpCapabilityRegistry`** — registers MCP servers + exposed tools/resources/prompts; the compiler validates **which step may reach which server/tool** (trust §7). Requires adding an MCP **client** (e.g. `langchain-mcp-adapters`). **Phase 4+ / N13.**
4. **Extend `ToolPermissions`** (§6/§9) — `mcp` (allowed tool names) + `integrations` (allowed scopes); skills/hooks are likewise allow-listed, not free text. exec/network/secrets/mcp/integrations default **OFF/none**.
5. **Per-run capability persistence** (§18 `run_capabilities`) — record the active runtime + resolved skill/hook/integration/MCP **names + versions** per run (today **nothing** is recorded — `WorkflowRun` `workflow.py:12-53`). Needed for replay/debug. **Phase 1B.**
6. **Frontend `/api/capabilities`** (§22) — return runtimes, skills, hooks, MCP servers, integration tools + **required auth + permission scopes**, so the composer renders them dynamically. **Parallel track.**

### Executable hooks (N12 ✅ DECIDED: executable)

Hooks are **executable lifecycle/tool-call handlers** the kernel fires at defined points — not merely prompt text. Each is an engineer-registered `HookHandler` (trusted code; users compose from the allow-list, §7), bound to one or more lifecycle **events**, optionally **blocking**.

- **Lifecycle events:** `before_run`/`after_run` · `before_step`/`after_step` · `post_task` · `before_tool_call`/`after_tool_call` · `before_write`/`after_write` · `pre_commit`/`post_commit` · `on_validation` · `before_merge`/`after_merge`. Bind to `"*"` for all.
- **Outcome:** `continue | warn | block` — a blocking hook halts the offending action (e.g. a secret found at `pre_commit`).
- **Canonical hooks:** **secret_scan** (`before_write`/`pre_commit`, blocking — fine-grained complement to the coarse `security` gate, §9); **otel_tracing / logging** (`*`, non-blocking → observability, §23); **pre_commit/post_commit** (lint/format/sign, then notify/update status); **post_task** (per-task summary, metrics, cleanup).
- **Permissioned (INV-9):** a hook that runs commands needs `exec`; a git hook needs `git`; a scanner needs `read_files`. Executable hooks are **engineer-registered** (trusted); users only attach allow-listed ones.
- **Persisted:** every firing → a `hook_runs` row (§18) for replay/debug. The legacy prompt-only hook survives as a non-executable `kind: behavioral` sub-type (`## Active Behavioral Hooks`, `factory.py:230-245`).

### MCP integration — all famous servers (N13 ✅ DECIDED: adopt)

Flowin will **consume external MCP servers** (not just expose the inbound `/flowin-handoff` server). Add an **`McpClientAdapter`** (e.g. `langchain-mcp-adapters` `MultiServerMCPClient`) that connects to a server (stdio/SSE/HTTP), lists its tools/resources/prompts, and binds the **allowed** ones into the agent's tool set.

- **Catalog (allow-listed, famous servers):** GitHub, GitLab, Jira/Atlassian, Confluence, Slack, Notion, Linear, Sentry, Figma, Filesystem, Postgres, Google Drive, web-search (Brave/Tavily), Playwright/Puppeteer, … Each is an `mcp_server` capability: transport + connection, exposed tools, **scoped per-owner credentials** (the GitHub-PAT pattern, `handoff.py:40`), and a `user_allowed` flag.
- **Validation (`McpCapabilityRegistry`, §7):** the compiler checks a step's `tools.mcp` only names tools from servers the step + owner may reach — unknown `server.tool` → compile error.
- **Security:** powerful servers (Filesystem, Postgres, anything with write/network) sit behind the `security` gate (§9) + scoped creds + the `secrets` permission (R13). Exposed tools + required auth are surfaced via `/api/capabilities` (§22).

### Current-state gaps the spec must fix (from the code investigation)

- **Constitution injection is a no-op in production** (`factory.py:282-290`) → **R12**; fixed in Phase 3 when prompt-assembly becomes a policy.
- **Hooks aren't persisted or executable** — they vanish after the run and only shape the prompt. True lifecycle/tool-call hooks are a new execution mechanism → **N12**.
- **MCP is backwards** — inbound server, no client → adopting it means adding a client + dependency → **N13**.
- **Runtime, tool set, and prompt order are all hardcoded** (`deep_agent_runner.py:240`, `factory.py:384-446`, `factory.py:174-255`) — the factory-side analog of the engine leak map (§4); they move to adapters/registries/policy in **Phase 3**.
- **GitHub support bypasses the main runtime** (`coding_agent.py:164`) — the `integration_provider` capability should make repo/GitHub reachable from the unified `create_runner` path, not only the handoff pipeline.

## 31. Code deletion, migration ledger & anti-duplication (INV-12)

The strangler migration **moves** code; it never copies it. For every legacy element the sequence is **wrap → rewire call-sites → delete**, completed **within the phase that supersedes it**. A phase that adds a capability while leaving the old branch in place is **not done**. This section is the **living ledger** the planning phase produces and the execution phase ticks off — so every function that must be refactored is *logged*, and each is proven *moved (not duplicated)* before deletion. This is the explicit answer to "don't leave duplicate code all over."

### Rules
- **One implementation per behavior.** After a leak's phase, its logic exists **only** behind the capability/port; the inline original is gone.
- **Deletion is an exit gate.** Each phase ships a **banned-pattern test** (grep → 0 for the deleted symbols/branches), a **dead-code scan** (ruff / vulture: no orphaned legacy functions), and an **import-linter** rule (the `kernel` imports only ports/capabilities — never legacy `engine`/`factory` internals). **Definition of Done = behavior moved + call-sites rewired + legacy deleted + gates green + snapshots green (§24).**
- **Ratchet.** Once deleted, the banned-pattern test stays — reintroducing a symbol fails CI (complements INV-1's `if pipeline_type` / `spec.id ==` gate).
- **One sanctioned temporary duplication:** the `accumulated_outputs` legacy mirror coexists with `ArtifactGraph` from Phase 1A and is **deleted in Phase 1B** once reads migrate (L15). No other dual-state is permitted.

### Migration & deletion ledger
`☐` pending · `☑` done — updated (status + deleting commit SHA) as phases land, like the decision log. `L#` = engine leak (§4); `F#` = factory/runtime; `D#` = dead code.

| Item | Legacy (`file:line`) | New home | Phase | Deletion gate (grep → 0 / check) | Status |
|---|---|---|---|---|---|
| L14 | `self._od_context/_completed_tasks/_current_task_block/_revision_*/_gate_agent_ids` (engine, throughout) | `ExecutionContext` (§6) | 0B | `self\._(od_context\|completed_tasks\|current_task_block\|revision_\|gate_agent_ids)` | ☐ |
| L16 | unchecked `parent_run` seed `engine.py:583-610` | authz store check (§19) | 0B | cross-owner denial test passes | ☐ |
| D1 | dead `_handle_revision` `engine.py:2138-2251` | delete (superseded by inline revision) | 0B | `_handle_revision` | ☐ |
| L13 | `_extract_html_skeleton` wired inline in 0C `engine.py:2565` | `CompactionStrategy(html_skeleton)` (§30) | 0C→2 | inline copy removed; only the strategy remains | ☐ |
| L1 | `_PPT_PIPELINE_TYPES`/`_PROTOTYPE_PIPELINE_TYPES`/`REVISION_FILE_NAME` `engine.py:93-110` | manifest `deliverable`/`seed_files` | 2 | `_PROTOTYPE_PIPELINE_TYPES\|_PPT_PIPELINE_TYPES` | ☐ |
| L2/L9 | `_resolve_final_output` `engine.py:316-397` | `DeliverableResolver` registry | 2 | `_resolve_final_output` | ☐ |
| L3 | `_sanitize_carousel_deck_html`/`_unwrap_artifact` `engine.py:232-313` | `ppt` resolver/transform capability | 2 | both names absent from the kernel | ☐ |
| L4/L8 | `prototype_revision` seeding + post-fix `engine.py:519-650,917-962` | `seed_files.from_run` + `previous_run` provider + `validation` gate | 2 | revision block absent from `execute()` | ☐ |
| L5 | `SKIP_PLANNER_FOR_PROTOTYPE` `engine.py:704-712` | manifest `planner` | 2 | `SKIP_PLANNER_FOR_PROTOTYPE` | ☐ |
| L6 | `ALWAYS_CLARIFY` defaults dict `engine.py:733-743` | manifest `clarify.defaults` | 2 | the per-pipeline defaults dict | ☐ |
| L7 | `spec.id == "prototype-build"` dispatch `engine.py:872` | `strategy: task_loop` (§8/§9) | 2 | `spec.id == "prototype-build"` (INV-1) | ☐ |
| L10 | `pipeline_type in ("od_prototype","prototype")` HTML readback `engine.py:1328-1335` | `task_loop` reads `deliverable.name` | 2 | that branch | ☐ |
| L11 | build-loop internals `engine.py:1450-1704,2554-2563` | `TaskLoopStrategy`+`TaskParser`+validators+fix-loop+`seed_files` | 2 | `_run_build_task_loop\|_write_build_reference_files\|_count_plan_tasks\|_extract_task_block\|_run_validation_fix_loop\|_load_template_example` | ☐ |
| L12 | `_build_context_message` od/ppt/build injection `engine.py:2378-2512` | `ContextProvider` + generic injector | 2 | per-pipeline branches in `_build_context_message` | ☐ |
| L15 | `accumulated_outputs: dict[str,str]` mirror (throughout) | `ArtifactGraph`/`ArtifactRef` (§17) | 1A→**1B (delete mirror)** | mirror reads removed; typed-artifact reads only | ☐ |
| F1 | prompt-assembly inline order `factory.py:174-255` | `PromptAssemblyPolicy` (§6/§30) | 3 | inline `blocks.append` ordering replaced by the policy | ☐ |
| F2 | `_build_runner_tools` closed switch `factory.py:384-446` | `tool_provider` registry (§30) | 3 | the `if/elif` tool-set switch | ☐ |
| F3 | inline skills/hooks injection `factory.py:220-245` | `skill_provider` / `hook_provider` (§30) | 3 | inline skill/hook blocks (behavioral hook → provider) | ☐ |
| F4 | `_inject_constitution` async no-op `factory.py:258-306` (R12) | sync-safe load via `PromptAssemblyPolicy` | 3 | constitution-injected-in-prod test passes | ☐ |
| F5 | `create_deep_agent` hardcoded `deep_agent_runner.py:240` | `AgentRuntimeAdapter` (§6/§30) | 3 | `create_deep_agent` called only inside the `langchain_deepagents` adapter | ☐ |

> The ledger is the single source of truth for "what still needs refactoring." A standalone `specs/003-…/migration-ledger.md` (asserted by the banned-pattern test) may mirror it operationally so CI fails if any `☑` item's pattern reappears.

## 32. Target directory structure & engineering patterns

Structure follows **Ports & Adapters (hexagonal)**: the **kernel** depends only on capability **ports** (Protocols); concrete capabilities are **adapters** that **self-register** into the `CapabilityRegistry` at startup. Adding a capability = add a module + register it — **no kernel edit** (Open-Closed). The agent runtime is the **LangChain `deepagents` library** behind the `langchain_deepagents` adapter (INV-13). The import-linter (§31) enforces the dependency direction.

### Target layout

```
backend/
├── agents/
│   ├── prompts/<agent>/AGENT.md            # agent identity + system-prompt body (unchanged)
│   ├── guardrails/*.md                      # injectable rule sets (unchanged)
│   ├── workflows/                           # ✦ declarative workflows (DATA, not code)
│   │   ├── <id>/workflow.yaml               #   hand-authored manifest (one per workflow)
│   │   ├── manifest.py                      #   schema + loader/validator
│   │   ├── compiler.py                      #   manifest → CompiledWorkflow (thin, no DSL — INV-5)
│   │   └── plan.py                          #   ExecutionPlan / Step / Task dataclasses
│   ├── capabilities/                        # ✦ the registry + every capability kind
│   │   ├── base.py                          #   the PORTS (Protocols): Strategy, Validator, Deliverable,
│   │   │                                    #   ContextProvider, GateHandler, HookHandler, MergeStrategy,
│   │   │                                    #   IsolationProvider, TaskParser, AgentRuntimeAdapter, …
│   │   ├── registry.py                      #   CapabilityRegistry((kind,name)→impl) + trust flags (§7)
│   │   ├── strategies/                      #   single_shot · task_loop · fanout_batch · wave_scheduler
│   │   ├── validators/                      #   spec_plan_coverage · task_done_when · design_quality (pure)
│   │   ├── deliverables/                    #   single_file · serialized_sandbox · streamed_text · repo_diff
│   │   ├── context_providers/               #   opendesign · repo · previous_run · uploaded_files · memory
│   │   ├── gates/                           #   human · validation · approval · security
│   │   ├── hooks/                           #   secret_scan · otel_tracing · pre/post_commit · post_task · behavioral
│   │   ├── runtimes/                        #   langchain_deepagents (wraps LangChain deepagents) · [claude_code_cli]
│   │   ├── skills/                          #   providers: ui · disk · template · repo
│   │   ├── integrations/                    #   base + github · gitlab · jira · slack · …
│   │   ├── mcp/                             #   client adapter + server catalog + per-server config
│   │   ├── isolation/                       #   shared_read · sub_sandbox · worktree
│   │   ├── merge/                           #   copy_disjoint · git_3way · json · html_fragment
│   │   ├── task_parsers/                    #   heading_tasks · json_tasks · bracket_p
│   │   ├── compaction/                      #   html_skeleton · repo_context_pack
│   │   ├── models/                          #   ModelCatalog · ModelResolver (§20)
│   │   └── policy/                          #   tool_permissions · prompt_assembly (§8/§30)
│   ├── execution_engine/                    # ✦ the KERNEL — workflow-agnostic (INV-1)
│   │   ├── kernel.py                        #   was engine.py: pure sequencer (imports only ports)
│   │   ├── context.py                       #   ExecutionContext (per-run state, INV-2)
│   │   ├── fanout.py                        #   run_fanout (engine-owned, INV-7)
│   │   ├── budget.py                        #   BudgetManager
│   │   ├── resolver.py · state_machine.py   #   DAG validation · run lifecycle
│   ├── artifacts/                           # ✦ ArtifactGraph + ArtifactRef (typed, lineage — §17)
│   ├── authz.py                             # ✦ ownership-scoped query/seed helpers (INV-8)
│   ├── loader.py · registry.py · planner/   #   agent loader · agent registry · deep-planner
└── app/
    └── agents/
        ├── runtime/                         # ✦ RuntimeEnvironment/Workspace PORTS + impls
        │   ├── base.py · local.py · [ecs.py]
        ├── deep_agent_runner.py             #   langchain_deepagents impl — wraps LangChain create_deep_agent (INV-13)
        ├── model_factory.py · sandbox.py · checkpointer.py
        ├── validators/                      #   static_check.py · render_check.py (heavy deps; registered as Validators)
        └── tools/                           #   runner_tools.py · fanout.py · mcp_tools.py
    ├── models/                              #   workflow · artifact_ref · workspace · repository · subagent_run ·
    │                                        #   wave_run · validation_result · gate_event · hook_run · run_event · run_capabilities
    └── api/                                 #   workflows.py · capabilities.py · runs.py · …
```
`✦` = new. Heavy-dependency impls (the LangChain `deepagents` runtime, the Chromium `render_check`) stay under `app/agents/` near their deps but **register into the registry** — so the kernel still imports only `capabilities.base` ports.

### Best patterns
- **Ports & Adapters / Dependency Inversion** — kernel → `capabilities.base` Protocols only; impls depend inward, never the reverse. Enforced by import-linter (§31).
- **Self-registering plugins** — each impl does `@register("validator", "html_static")`; a startup `discover()` imports all capability packages (no central if/elif).
- **Strategy / registry over conditionals** — every former `if pipeline_type`/`if spec.id` becomes a registry lookup by declared name (INV-1).
- **Declarative data, thin compiler** — manifests are YAML data; logic lives in strategies; the compiler only validates + resolves names → impls (INV-5).
- **Use the library, never hand-roll the agent loop (INV-13)** — `langchain_deepagents` wraps LangChain `create_deep_agent`; new runtimes are added adapters, not bespoke loops.
- **Immutable kernel + per-run `ExecutionContext`** (INV-2) — safe concurrency/fan-out.
- **Typed seams** — `@dataclass`/`Protocol` at every boundary; typed `ArtifactRef` handoff, not `dict[str,str]`.
- **One name everywhere** — capability `name` == registry key == manifest reference (consistent snake_case).
- **Open-Closed** — new workflow = new `workflow.yaml`; new power = new capability module + register; kernel untouched (the success test, SC-001).
- **Move-don't-copy + ledger gates** (INV-12/§31) keep the tree free of dead/duplicate code as it grows.
- **Test pyramid** — pure unit tests per capability · characterization snapshots (§24) · the ledger CI guard + import-linter · authz-denial tests.

---

*Decision log: append dated entries here as phases land.*

- **2026-06-06 (r2)** — review tweaks: split Phase 0→0A/0B/0C, 1→1A/1B/1C, 4→4A/4B; **INV-3 relaxed to semantic event parity** (deliverables byte-identical only where deterministic; Phase 0C is the sanctioned context-change exception); **anonymous runs use a synthetic `anon:<session_id>` owner** (never None); **built-in manifests are hand-authored** (generated index optional later); added a **durable event `seq` + replay cursor** (`run_events` §18, resume §21, `GET /runs/{id}/events?after=` §22); Phase 4 exec split out behind N3.
- **2026-06-06 (r3)** — added the **agent-runtime / skills / hooks / MCP / integrations capability layer** (§30, A11, INV-11), grounded in the current code (prompt-assembly order `factory.py:174-255`; runtime hardcoded `deep_agent_runner.py:240`; skills `skills.py:320` + `engine.py:1167`; hooks ephemeral/prompt-only `factory.py:230-245`; tools closed-enum `factory.py:384`; MCP inbound-server-only `mcp.py:48`; GitHub in the parallel handoff pipeline `coding_agent.py:164`). Added `AgentRuntimeAdapter` + `PromptAssemblyPolicy` (§6), `mcp`/`integrations` tool permissions (§9), `run_capabilities` persistence (§18), `/api/capabilities` expansion (§22), N12/N13, R12/R13. Flagged the **constitution-injection no-op** (R12) and **hooks-not-persisted/not-executable** gaps.
- **2026-06-06 (r4)** — owner clarifications: **hooks are executable lifecycle/tool-call hooks** (secret-scan, logging/tracing, pre/post-commit, post-task, before/after-write, …) → **N12 ✅**; **integrate all famous MCP servers** via an MCP client + allow-listed catalog → **N13 ✅**. Added `HookHandler` + `McpClientAdapter` (§6), the lifecycle taxonomy + MCP catalog (§30), `hook_runs` persistence (§18), logging/tracing-hook observability (§23); extended R13 to the executable-hook/MCP attack surface (with `secret_scan` as a mitigation).
- **2026-06-06 (r5)** — added **code-deletion / anti-duplication discipline**: INV-12 (move-don't-copy, single implementation), the §31 **migration & deletion ledger** (every L#/F#/D# legacy element → new home → phase → deletion grep-gate → status), per-phase deletion gates + dead-code scan + import-linter folded into each phase's Definition of Done, and R14 (duplication/dead-code drift). Strengthened INV-3 (no dual *implementation*, not just no flags). Answers the "don't leave duplicate code all over" concern.
- **2026-06-06 (r6)** — owner asks: **ledger CI guard into Phase 0A** (`test_migration_ledger.py` + import-linter); **user per-agent model selection** (§20/A12 — `model_overrides` at the top of the resolution order + `ModelCatalog`, persisted); **target directory structure & engineering patterns** (§32, ports-and-adapters / self-registering capabilities); and **LangChain `deepagents` mandated project-wide** (INV-13 + R15 + scope mandate + §30/§32) — never a hand-rolled deep agent.
- **2026-06-06 (r7)** — naming disambiguation (anti-hallucination): standardized the runtime adapter/identifier to **`langchain_deepagents`** throughout 003; clarified in INV-13/R15 that the **canonical import is exactly `from deepagents import create_deep_agent`** (PyPI `deepagents==0.6.7`) and that creating a local `deepagents`/`langchain_deepagents` module or `DeepAgent` class is banned. Real artifacts kept accurate: the `deepagents` package, `create_deep_agent`, `DeepAgentRunner`, `deep_agent_runner.py`, and the `002-deepagents-migration` doc reference.
