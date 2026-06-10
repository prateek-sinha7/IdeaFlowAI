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
    """Least-privilege grant set for a step (INV-9 / §8 / D-07).

    Defaults are the §8 least-privilege posture: ``read_files`` ON; everything
    else OFF/none — ``exec``/``network``/``secrets``/``spawn_subagents`` stay OFF
    (code-exec stays behind the ``security`` gate until N3). The ``mcp`` /
    ``integrations`` slots are present but default ``none`` (empty) — slots only,
    no client/servers this phase (Phase 9 lands the clients).

    Made LIVE in 08-03: ``intersect_permissions`` resolves the effective grant set
    as ``intersection(owner_allow_list, workflow_ceiling, step_grant)``, and
    ``lowered_by`` applies an AGENT.md default that may only LOWER a permission
    (never raise one its step did not grant).

    The bool fields are least-privilege gates; the list fields (``secrets`` /
    ``mcp`` / ``integrations``) are allow-lists that intersect to their common
    members.
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

    # Field names by kind — used by the intersection/lowering helpers so a new
    # permission slot is honored automatically (no parallel literal list).
    _BOOL_FIELDS = (
        "read_files",
        "write_files",
        "exec",
        "git",
        "network",
        "spawn_subagents",
    )
    _LIST_FIELDS = ("secrets", "mcp", "integrations")

    def lowered_by(self, agent_md: "ToolPermissions") -> "ToolPermissions":
        """Return ``self`` masked by an AGENT.md default that may only LOWER (D-07).

        FORWARD-SURFACE HELPER — correct in isolation, NOT yet wired into a call
        site. The intended consumer is the factory tool-binding seam, where an
        AGENT.md default would lower the step's effective grant before tool
        resolution; that wiring lands in Phase 9+ (alongside the first privileged
        tool set). The mask itself is a pure AND over the bool gates and an
        intersection over the list allow-lists: an AGENT.md declaring ``exec=True``
        over an ungranted ``exec`` is a no-op (stays OFF), while ``read_files=False``
        lowers it. It can never RAISE a permission. Do NOT cite this as an active
        enforcement point — it has no production caller this phase.
        """
        return _and_mask(self, agent_md)


def _and_mask(base: "ToolPermissions", mask: "ToolPermissions") -> "ToolPermissions":
    """AND-mask two ToolPermissions: a perm is ON only if ON in BOTH (D-07).

    Bool gates AND; list allow-lists intersect (preserving ``base`` order). This is
    the single primitive behind both ``intersect_permissions`` (owner ∩ workflow ∩
    step) and ``ToolPermissions.lowered_by`` (effective ∩ agent_md) — neither can
    raise a permission, only lower it.
    """
    bool_kwargs = {
        f: bool(getattr(base, f)) and bool(getattr(mask, f))
        for f in ToolPermissions._BOOL_FIELDS
    }
    list_kwargs = {
        f: [x for x in getattr(base, f) if x in set(getattr(mask, f))]
        for f in ToolPermissions._LIST_FIELDS
    }
    return ToolPermissions(**bool_kwargs, **list_kwargs)


def intersect_permissions(
    owner_allow_list: "ToolPermissions",
    workflow_ceiling: "ToolPermissions",
    step_grant: "ToolPermissions",
) -> "ToolPermissions":
    """Resolve the effective grant set ``= owner ∩ workflow ∩ step`` (D-07 / INV-9).

    A permission is effective ONLY if granted at ALL THREE levels (the intersection
    is the least-privilege resolution of TOOLPERM-01/02/03). The result is the
    ceiling an AGENT.md may then only LOWER (via ``ToolPermissions.lowered_by``).

    A missing owner allow-list (DB user manifests are a later phase) defaults to the
    workflow ceiling — callers pass ``workflow_ceiling`` for ``owner_allow_list``
    when no per-owner cap is bound, so the intersection collapses to
    ``workflow ∩ step`` without special-casing here.
    """
    return _and_mask(_and_mask(owner_allow_list, workflow_ceiling), step_grant)


# Privileged runtime actions gated by the ExecutionPolicy enforcement point (D-07).
# These are default-DENIED until the security gate + a runtime host (Phase 9/N3)
# enable them; ``read_files``/``write_files``/``git`` are tool-binding permissions
# (enforced at the tool_provider seam), NOT runtime-policy actions.
_PRIVILEGED_RUNTIME_ACTIONS: frozenset[str] = frozenset({"exec", "network", "secrets"})


@dataclass
class ExecutionPolicy:
    """Default-deny runtime policy helper for the Workspace boundary (D-07 / §8).

    FORWARD SURFACE — correct in isolation, NOT yet wired into the runtime action
    path. This is the DESIGN of the second D-07 enforcement point (the runtime
    ``exec``/``network``/``secrets`` gate); the actual call site lands with the
    ``LocalSandboxRuntime`` in Phase 9 (the runtime host that would invoke
    ``check`` before any privileged action). There is NO production caller of
    ``check`` this phase. The actual exec/network/secrets DENIAL this phase comes
    from (a) the compiler's ``intersect_permissions`` collapsing those perms OFF and
    (b) the ``security`` gate — both of which ARE wired. Do NOT cite ``check`` as an
    active runtime enforcement point until Phase 9 wires it.

    ``check(action, perms)`` returns ``(allowed, reason)``; a privileged action is
    denied UNLESS a runtime host (Phase 9) explicitly opens it — there is no host
    this phase, so privileged actions are uniformly denied (the helper is
    default-deny by construction, ready for the Phase-9 call site).
    """

    # Phase 9 attaches a runtime host that may open specific privileged actions.
    # Default ``None`` → every privileged action is denied (default-deny).
    runtime_host: object | None = None

    def check(self, action: str, perms: "ToolPermissions") -> tuple[bool, str]:
        """Return ``(allowed, reason)`` for a runtime ``action`` (default-deny).

        A privileged action (``exec``/``network``/``secrets``) is DENIED unless a
        runtime host is attached AND opens it — no host this phase, so it is denied
        regardless of what ``perms`` requests. A non-privileged action is allowed.
        """
        if action in _PRIVILEGED_RUNTIME_ACTIONS:
            if self.runtime_host is None:
                return (
                    False,
                    f"runtime action '{action}' is denied: no runtime host "
                    f"attached (default-deny; exec/network/secrets land in "
                    f"Phase 9/N3)",
                )
            # A host is attached (Phase 9) — delegate the per-action decision to it.
            opener = getattr(self.runtime_host, "allows", None)
            if callable(opener) and opener(action, perms):
                return (True, f"runtime action '{action}' opened by the runtime host")
            return (False, f"runtime action '{action}' is denied by the runtime host")
        # Non-privileged action (read_files/write_files/git binding) — not gated here.
        return (True, f"action '{action}' is not a privileged runtime action")


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

    ``source_step`` / ``spec_step`` are the DECLARED upstream step ids the
    ``task_loop`` strategy reads from (07-11 / CR-05) — replacing the hardcoded
    ``"prototype-plan"`` (the task plan source) and ``"prototype-specify"`` (the
    spec source) literals. They name the producer step whose typed-graph output
    the strategy parses into tasks / writes as the spec reference file. A manifest
    DECLARES these (the prototype manifest declares ``prototype-plan`` /
    ``prototype-specify``, so the prototype path stays byte-identical, INV-1); a
    workflow that omits them falls back to the legacy ids in the strategy (NOT a
    kernel default — the strategy owns the fallback so the compiler stays thin,
    INV-5).
    """

    kind: str = "none"            # none | inline | parsed | file
    parser: str | None = None     # capability name, e.g. "heading_tasks"
    target: str | None = None     # file/section the tasks come from
    source_step: str | None = None  # DECLARED task-plan producer step id (CR-05)
    spec_step: str | None = None    # DECLARED spec producer step id (CR-05)


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
    """Brownfield repo binding (§15). INERT in Phase 4 (repo phases 9–12).

    ``index`` is the DECLARED symbol-index opt-in (09-03 / REPO-02 / D-04): when
    ``True`` the workflow asks the optional ``repo_index`` (``tree_sitter``)
    capability to build an in-memory symbol index for the cloned repo. The
    compiler only RECORDS this flag (INV-5 — manifests are pure data, no control
    flow); the build DECISION (``index OR file_count > N6``) lives inside the
    ``repo_index`` capability, never the compiler. ``False`` (the default) means
    grep/glob is the only search path.
    """

    url: str | None = None
    ref: str | None = None
    branch: str | None = None
    index: bool = False


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

    ``revises_existing`` is the DECLARED revision-intent flag (07-10 / WR-04/WR-06):
    when ``True`` the workflow EDITS an existing artifact (named by ``name``) in
    place — the kernel seeds the prior artifact + gates the previous_run parent
    seed on THIS flag, NOT on a provider-name proxy (``"previous_run" in
    context_providers``) nor a workflow-name branch (INV-1). Only the
    ``prototype_revision`` manifest sets it ``True`` today; the four other
    ``previous_run``-declaring workflows leave it ``False`` (they regenerate the
    whole artifact, they do not in-place edit), so they are no longer
    misclassified as in-place revisions.
    """

    strategy: str | None = None   # capability name (deliverable resolver)
    name: str | None = None       # e.g. "prototype.html"
    revises_existing: bool = False  # DECLARED revision-intent (07-10 / WR-04/WR-06)


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
    hooks: list[str] = field(default_factory=list)           # §30 — executable-hook capability names (08-08 / CR-01/WR-03)
    task_source: TaskSource | None = None                    # Q10a/b
    post_step: str | None = None                             # post_step capability name (07-10 / CR-06)

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
