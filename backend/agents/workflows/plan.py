"""agents/workflows/plan.py — the typed §6 declaration contract (D-06).

Defines the workflow-agnostic compiled plan the kernel executes:
``CompiledWorkflow`` (a topo-validated ``Step`` DAG + workflow-level deliverable /
planner / clarify config) and the canonical ``Task`` produced by task parsers.

Phase-4 scope (D-06): define the FULL §6 field set now, populate only the
Phase-4-consumed fields, and declare every forward field as *inert* — present
with a safe default but NOT consumed by any Phase-4 behavior. The forward fields
(``model``, ``tools``, ``validators``, ``fix``, ``compaction``, ``fanout``,
``on_conflict``, ``retry``, ``injects``, ``repo``, ``limits``) become live in
later phases (model policy = Phase 6, capability impls = Phase 7, …). The only
hard constraint: NO Phase-4 behavior keys off an inert field.

Conventions (mirrors ``agents/loader.py::AgentSpec`` + the ``resolver.py``
dataclass cluster): plain ``@dataclass`` with required fields first and defaulted
fields second; ``field(default_factory=...)`` for mutable defaults. NOT Pydantic
(D-10 / §6 / §32). No workflow-name / pipeline-id dispatch branch lives here —
this module is pure data.

Phase-4-consumed fields:
  - ``Step.agent_id``, ``Step.strategy`` (name), ``Step.gates`` (names),
    ``Step.task_source``
  - ``CompiledWorkflow.id``, ``.steps``, ``.context_providers`` (names),
    ``.seed_files``, ``.deliverable``, ``.planner``, ``.clarify``

Everything else is declared-but-inert forward surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Forward / nested config types (D-06 — declared, INERT in Phase 4)
#
# These are minimal stub dataclasses so the §6 field set is type-complete now.
# None of them is consumed by Phase-4 behavior; later phases give them meaning
# (ToolPermissions / ModelPolicy = §8/§20 Phase 6; FixPolicy / RetryPolicy /
# FanoutSpec = Phase 7; RepoSpec = the brownfield repo phases). Defaults encode
# the §6 least-privilege posture (exec/network/secrets/spawn_subagents OFF).
# ---------------------------------------------------------------------------


@dataclass
class ToolPermissions:
    """Least-privilege grant set for a step (INV-9 / §8). INERT in Phase 4.

    Defaults keep ``exec``/``network``/``secrets``/``spawn_subagents`` OFF —
    code-exec stays behind the ``security`` gate until N3.
    """

    read_files: bool = True
    write_files: bool = False
    exec: bool = False
    git: bool = False
    network: bool = False
    secrets: list[str] = field(default_factory=list)
    mcp: list[str] = field(default_factory=list)
    integrations: list[str] = field(default_factory=list)
    spawn_subagents: bool = False


@dataclass
class ModelPolicy:
    """Per-scope model selection policy (§20). INERT in Phase 4 (Phase 6 = MODEL-*)."""

    model: str | None = None
    max_tokens: int | None = None
    cost_class: str = "standard"
    fallback: list[str] = field(default_factory=list)


@dataclass
class TaskSource:
    """Where a strategy sources its task list from (Q10a/b).

    Phase-4-consumed only insofar as it is carried on the compiled Step; the
    ``parser`` name is validated against the registry by the compiler (04-03).
    """

    kind: str = "none"            # none | inline | parsed | file
    parser: str | None = None     # capability name, e.g. "heading_tasks"
    target: str | None = None     # file/section the tasks come from


@dataclass
class FixPolicy:
    """Validation fix-loop policy (Q23/Q25). INERT in Phase 4 (Phase 7)."""

    mode: str = "off"             # off | internal | gated
    max_attempts: int = 0


@dataclass
class FanoutSpec:
    """Declarative fan-out spec (Q12). INERT in Phase 4 (Phase 7)."""

    mode: str | None = None       # parallel | sequential
    max_parallel: int | None = None


@dataclass
class RetryPolicy:
    """Per-step retry policy (§21). INERT in Phase 4."""

    max_attempts: int = 0
    backoff_seconds: float = 0.0


@dataclass
class RepoSpec:
    """Brownfield repo binding (§15). INERT in Phase 4 (repo phases 9–12)."""

    url: str | None = None
    ref: str | None = None
    branch: str | None = None


@dataclass
class Limits:
    """Per-workflow budget caps (Q18/Q44). INERT in Phase 4."""

    max_tokens: int | None = None
    max_subagents: int | None = None
    max_depth: int | None = None
    wall_clock_seconds: int | None = None


@dataclass
class DeliverableSpec:
    """The workflow's deliverable resolution declaration (Q26).

    Phase-4-consumed: ``strategy`` (a deliverable-resolver capability NAME, e.g.
    ``single_file``/``serialized_sandbox``/``streamed_text``/``ppt``) is validated
    by the compiler; ``name`` is the output filename hint.
    """

    strategy: str | None = None   # capability name (deliverable resolver)
    name: str | None = None       # e.g. "prototype.html"


@dataclass
class ClarifySpec:
    """Clarifier configuration (Q30). Phase-4-consumed.

    ``defaults`` reproduces the engine's per-pipeline default-question list
    (``_pipeline_defaults``) — the routing seam (MAN-04) sources it from here.
    """

    mode: str = "auto"
    defaults: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Canonical Task (Q11) — produced by TaskParser adapters (Phase 7)
# ---------------------------------------------------------------------------


@dataclass
class Task:
    """A single unit of work a task-loop strategy dispatches (Q11).

    Phase 4 defines the full typed shape; task PARSING (the adapters that build
    these) lands with the strategy impls in Phase 7. ``targets``/``depends_on``/
    ``conflict_keys``/``done_when``/``inputs``/``outputs`` are the forward fields
    the wave scheduler and merge layer consume later.
    """

    # ── Required ──────────────────────────────────────────────────────────
    id: str
    title: str
    body: str

    # ── Forward surface (defaulted; INERT in Phase 4) ─────────────────────
    targets: list[str] = field(default_factory=list)        # section selectors / file paths
    depends_on: list[str] = field(default_factory=list)
    parallel: bool = False
    conflict_keys: list[str] = field(default_factory=list)  # wave scheduling (Q32/Q33) + merge
    done_when: list[str] = field(default_factory=list)      # Tier#5 / validators
    inputs: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Declarative Step (compiled from a manifest step dict)
# ---------------------------------------------------------------------------


@dataclass
class Step:
    """One compiled step in the workflow DAG (full §6 field set, D-06).

    Phase-4-consumed: ``agent_id``, ``strategy`` (capability name), ``gates``
    (gate capability names), ``task_source``. Everything below ``task_source``
    is declared-but-inert forward surface (Phase 6/7+).
    """

    # ── Required ──────────────────────────────────────────────────────────
    agent_id: str

    # ── Phase-4-consumed (defaulted) ──────────────────────────────────────
    strategy: str = "single_shot"                            # Q8/Q9 — capability name
    gates: list[str] = field(default_factory=list)           # §9 — gate capability names
    task_source: TaskSource | None = None                    # Q10a/b

    # ── Forward surface (declared, INERT in Phase 4) ──────────────────────
    tools: ToolPermissions = field(default_factory=ToolPermissions)  # INV-9 / §8
    model: ModelPolicy | None = None                         # §20
    validators: list[str] = field(default_factory=list)      # Q21 — capability names
    fix: FixPolicy | None = None                             # Q23/Q25
    compaction: str | None = None                            # Q35 — capability name
    fanout: FanoutSpec | None = None                         # Q12
    on_conflict: str = "human_gate"                          # §13
    retry: RetryPolicy | None = None                         # §21
    injects: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Compiled workflow (the kernel's execution target)
# ---------------------------------------------------------------------------


@dataclass
class CompiledWorkflow:
    """The typed plan the kernel executes — output of the compiler (MAN-02).

    Phase-4-consumed: ``id``, ``steps``, ``context_providers`` (capability
    names), ``seed_files``, ``deliverable``, ``planner``, ``clarify``. The
    ``model``/``repo``/``limits`` forward fields are declared-but-inert (Phase
    6 / repo phases).

    ``steps`` may be empty (the ``reverse_engineer`` empty-plan stub, D-05).
    """

    # ── Required (Phase-4-consumed) ───────────────────────────────────────
    id: str

    # ── Phase-4-consumed (defaulted) ──────────────────────────────────────
    steps: list[Step] = field(default_factory=list)          # topo-validated DAG (may be [])
    context_providers: list[str] = field(default_factory=list)  # Q28 — capability names
    seed_files: dict = field(default_factory=dict)           # Q29
    deliverable: DeliverableSpec = field(default_factory=DeliverableSpec)  # Q26
    planner: str = "run"                                     # "skip" | "run" (Q30)
    clarify: ClarifySpec = field(default_factory=ClarifySpec)  # mode + defaults (Q30)

    # ── Forward surface (declared, INERT in Phase 4) ──────────────────────
    model: ModelPolicy = field(default_factory=ModelPolicy)  # workflow default (§20)
    repo: RepoSpec | None = None                             # §15 (brownfield)
    limits: Limits = field(default_factory=Limits)           # Q18/Q44
