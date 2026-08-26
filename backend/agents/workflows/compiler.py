"""agents/workflows/compiler.py — thin no-DSL WorkflowCompiler (MAN-02).

Transforms a validated ``WorkflowManifest`` (04-02) into the typed
``CompiledWorkflow`` the kernel executes. The compiler does EXACTLY two things
and nothing more (Pattern 3 / INV-5):

  1. Name-resolve every declared capability reference (strategy, validators,
     gates, task_source.parser, compaction, workflow-level context_providers,
     deliverable resolver) against the ``CapabilityRegistry`` — an unknown name
     is a ``CompilerError`` NAMING the bad reference (MAN-03 / INV-4).
  2. Map each raw step dict → a typed ``Step`` and topo-validate the resulting
     Step DAG (cycle-free, no duplicate agent ids).

Hard constraints (the kernel knows no workflow by name — SC-001):
  - NO workflow-name / ``pipeline_type`` / literal-id branch (INV-1). Resolution
    is purely by declared capability NAME against the registry — never by which
    workflow is being compiled.
  - NO ``eval``/``exec`` of any manifest value (T-04-06). The compiler is a pure
    data transform; a control-flow construct is rejected at load (strict-key,
    04-02) and any expression smuggled into a capability name simply fails the
    registry lookup (it is not a registered name).

Hexagonal direction: imports only stdlib + ``agents.workflows.{manifest,plan}``
+ ``agents.capabilities.registry`` (the port it validates against). It NEVER
imports the kernel (``agents.execution_engine``) or the web layer.
"""

from __future__ import annotations

import inspect
import logging
import re

from agents.capabilities.registry import CapabilityRegistry
from agents.workflows.artifacts import CUSTOM_AGENT_PREFIX
from agents.workflows.manifest import WorkflowManifest
from agents.workflows.plan import (
    ClarifySpec,
    CompiledWorkflow,
    DeliverableSpec,
    FanoutSpec,
    FixPolicy,
    Limits,
    ModelPolicy,
    RetryPolicy,
    RouteOutcome,
    RouteSpec,
    Step,
    TaskSource,
    ToolPermissions,
)
from agents.workflows.permission_caps import (
    ALLOWED_GRANT_KEYS,
    apply_cap,
    parse_grant,
)

logger = logging.getLogger(__name__)


class CompilerError(Exception):
    """Raised when a manifest references an unknown capability or has a bad DAG.

    The message always NAMES the offending reference (the bad capability name +
    the step it appears in) so the manifest author can locate it (MAN-03 / INV-4).
    Carries only repo-authored config text — no secret/PII surface.
    """


# ---------------------------------------------------------------------------
# Strict step-level key allow-list (D-08 / INV-5)
# ---------------------------------------------------------------------------

# EXACTLY the keys a step dict may declare. Mirrors the top-level
# ``_ALLOWED_TOP_KEYS`` strict-key rejection (manifest.py): the no-DSL guarantee
# must hold at EVERY level, not just the top (D-08). A control-flow / DSL field
# (``when:`` / ``if:`` / ``for:`` / ``${...}`` …) at step level has nowhere to
# live and is rejected by name. The first six keys are the ones authored across
# the 15 in-repo workflow.yaml manifests today; the remainder is the inert
# forward surface (declared now, consumed Phase 6/7).
_ALLOWED_STEP_KEYS: frozenset[str] = frozenset(
    {
        # consumed in Phase 4 (authored in the 15 manifests)
        "agent",
        "strategy",
        "gates",
        "hooks",  # declared executable-hook capabilities (08-08 / CR-01/WR-03)
        "validators",
        "compaction",
        "task_source",
        "post_step",  # declared post-step capability (07-10 / CR-06)
        "require_render",  # per-step render fail-closed knob (quick-260701-bob)
        # forward surface (inert in Phase 4 — declared now, consumed Phase 6/7)
        "tools",
        "model",
        "fix",
        "fanout",
        "route",
        "produces",     # spec 014 / R-05b: declared typed-artifact kinds (R-27's produces check)
        "consumes",     # R-29: the matching half — which upstream outputs reach this step
        "on_conflict",
        "retry",
        "injects",
        "depends_on",
        # spec 012 / per-agent-skills-custom-agents: per-instance identity + scoping.
        "instance_id",  # stable, immutable node slug (R-02/R-03)
        "name",         # user-editable display label; never affects instance_id (R-02)
        "prompt",       # per-instance purpose text; custom-agent steps only (R-02/R-06)
        "skills",       # per-step skill ids (R-01)
        "subagents",    # declarative child-step group (R-02/R-04)
        "produces_solution_plan",  # post-step solution-plan extraction flag
    }
)

# EXACTLY the keys a step ``subagents:`` dict may declare (D-08 at the nested level /
# spec 012 R-04). Mirrors ``_ALLOWED_TASK_SOURCE_KEYS`` / ``_ALLOWED_FANOUT_KEYS``: the
# key set is closed so a control-flow/DSL field smuggled into a subagents block is
# rejected by name rather than silently accepted (INV-5). The compiler VALIDATES this
# block (mode/task_source/steps) but does not yet expand it into child Steps — that
# expansion is a later task (T8/T12); here it is pure data, carried through validation
# only.
_ALLOWED_SUBAGENTS_KEYS: frozenset[str] = frozenset(
    {"mode", "max_parallel", "task_source", "steps"}
)

# EXACTLY the subagents.mode values a step may declare (spec 012 R-04). The kernel's
# child-group execution strategy (parallel/sequential/fanout) is selected by this NAME
# — never by a workflow-name/pipeline-id branch (INV-1) — and an unregistered mode is
# rejected at compile time (fail-loud) rather than silently defaulting.
_ALLOWED_SUBAGENT_MODES: frozenset[str] = frozenset({"parallel", "sequential", "fanout"})

# instance_id shape (spec 012 R-03): a lowercase-kebab slug, immutable once assigned.
_INSTANCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# EXACTLY two levels of subagents nesting are legal (spec 012 R-05 / F-03): a top-level
# step's subagents.steps (level 1 = "child") may themselves declare subagents.steps
# (level 2 = "grandchild"); a third level ("great-grandchild") is rejected naming the
# field. Counted as the depth of subagents BLOCKS, not step levels.
_MAX_SUBAGENTS_DEPTH = 2

# EXACTLY the keys a task_source dict may declare (D-08 at the nested level).
# ``source_step`` / ``spec_step`` are the DECLARED upstream producer step ids the
# task_loop strategy reads from (07-11 / CR-05) — pure data, no control flow (INV-5).
_ALLOWED_TASK_SOURCE_KEYS: frozenset[str] = frozenset(
    {"kind", "parser", "target", "source_step", "spec_step"}
)

# EXACTLY the keys a step ``fanout:`` dict may declare (D-08 at the nested level /
# Phase 11 / FANOUT-03). ``mode``/``max_parallel`` are the original fields;
# ``agent``/``count``/``workers`` select the worker; ``merge_agent`` designates the
# bounded merge worker for ``on_conflict: merge_agent`` (FANOUT-08 / §13). Pure data
# (INV-5): the run_fanout kernel owns the selection control flow, the compiler only
# materializes the data.
_ALLOWED_FANOUT_KEYS: frozenset[str] = frozenset(
    {"mode", "max_parallel", "agent", "count", "workers", "merge_agent"}
)

# EXACTLY the keys a step ``route:`` dict may declare (D-08 at the nested level /
# spec 014 / conditional gates). ``condition_agent``/``outcomes`` define the condition
# expression and the branching targets; ``default_next`` provides the fallback;
# ``loop_max_iterations``/``trigger_max_depth`` bound loop/trigger recursion. Pure data
# (INV-5): the conditional gate kernel owns the condition evaluation control flow, the
# compiler only materializes the data.
_ALLOWED_ROUTE_KEYS: frozenset[str] = frozenset(
    {"condition_agent", "outcomes", "default_next", "loop_max_iterations", "trigger_max_depth"}
)

# EXACTLY the keys a step ``route.outcomes:`` dict may declare (D-08 at the nested level /
# spec 014 / conditional outcomes). ``trigger`` is the condition predicate that must match;
# ``target`` names the next step to dispatch to. Pure data (INV-5): conditional routing
# evaluates the trigger expression and selects the target, purely declarative.
# ``feedback`` (R-28) is authored guidance injected into the target step's context on a
# BACKWARD jump — still pure data (INV-5): the compiler only records the string, the
# kernel decides when it applies.
_ALLOWED_OUTCOME_KEYS: frozenset[str] = frozenset(
    {"trigger", "target", "feedback"}
)

# EXACTLY the §13 on_conflict policy set a step may declare (FANOUT-08). The kernel
# ``_resolve_conflict`` dispatches on these four; an unknown policy is rejected at
# compile time (fail-loud) rather than silently falling back to human_gate.
_ALLOWED_ON_CONFLICT: frozenset[str] = frozenset(
    {"human_gate", "merge_agent", "partial", "abort"}
)

# EXACTLY the keys a step ``tools:`` grant block may declare (D-08 at the nested
# level / D-07). These are the §8 ToolPermissions grant fields — pure data, no
# control flow (INV-5). Mirrors ``ToolPermissions`` (plan.py:45-) one-for-one.
# DERIVED from ToolPermissions via permission_caps — never hand-listed, so a new
# permission cannot be silently rejected here by a stale copy.
_ALLOWED_TOOLS_KEYS: frozenset[str] = ALLOWED_GRANT_KEYS


# ---------------------------------------------------------------------------
# Manifest trust context (CAP-03 / D-02)
# ---------------------------------------------------------------------------

# The trust levels a manifest source carries. ``file`` and ``builtin`` are
# TRUSTED (engineer-authored, version-controlled) — they may reference any
# registered capability. ``user`` / ``db`` are UNTRUSTED — every reference is
# additionally checked against the per-capability ``user_allowed`` flag, so a
# user/DB manifest can never reference a privileged capability (exec/secrets/
# spawn/powerful runtimes) the engineer did not mark user-grantable.
_TRUSTED_SOURCES: frozenset[str] = frozenset({"file", "builtin"})


# ---------------------------------------------------------------------------
# Trust-conditional Limits ceiling (FANOUT-09 / OBS-01 / 08-03/10-02 precedent)
# ---------------------------------------------------------------------------

# The static budget-ceiling defaults the trust gate enforces against. These MIRROR the
# runtime module constants in ``agents.execution_engine.budget`` (DEFAULT_MAX_SUBAGENTS=8
# / DEFAULT_MAX_DEPTH=2 / DEFAULT_WALL_CLOCK_SECONDS=900) but are DEFINED here so the
# compiler never imports the kernel (the import-linter ``agents.workflows ↛
# agents.execution_engine`` contract). The budget module is the RUNTIME enforcer; this is
# the STATIC compile-time gate — a file/builtin manifest may RAISE a Limits cap above the
# ceiling (engineer-authored, trusted), but a user/db manifest may only LOWER (it may not
# raise a cap above the default ceiling — the 08-03 AGENT.md-only-lowers + 10-02 ceiling
# precedent). The runtime concurrency clamp (min(declared, 4) in run_fanout) is the
# backstop; THIS is the static gate.
_LIMITS_DEFAULT_CEILING: dict[str, int] = {
    "max_subagents": 8,
    "max_depth": 2,
    "wall_clock_seconds": 900,
    # max_tokens has no module-constant default ceiling (uncapped unless declared); a
    # user/db manifest declaring max_tokens only constrains itself, so it is never a
    # "raise above the ceiling" — it is omitted from the raise-rejection set.
}


class WorkflowCompiler:
    """Thin, no-DSL manifest → ``CompiledWorkflow`` transform (MAN-02).

    Stateless: ``compile`` takes the manifest and the registry it validates
    declared references against. No per-workflow knowledge lives here.
    """

    def compile(
        self,
        manifest: WorkflowManifest,
        registry: CapabilityRegistry,
        *,
        trust: str = "file",
    ) -> CompiledWorkflow:
        """Compile ``manifest`` into a typed, validated ``CompiledWorkflow``.

        ``trust`` is the manifest's source/trust context (CAP-03 / D-02): ``file``
        or ``builtin`` are TRUSTED (the default — the 15 file-backed manifests
        compile unrestricted, so Phase-4/7 parity holds); ``user`` or ``db`` are
        UNTRUSTED — every declared capability reference is additionally checked
        against the registry's ``user_allowed`` flag, and a not-user-allowed
        reference is a ``CompilerError`` NAMING the offending ``(kind, name)``.

        Raises:
            CompilerError: if any declared capability reference is unknown to the
                registry (naming the bad reference); under an untrusted ``trust``,
                if a reference is registered but not ``user_allowed`` (naming the
                ``(kind, name)``); or the Step DAG has a duplicate agent id / cycle.
        """
        trusted = trust in _TRUSTED_SOURCES
        # Recorded only so the tool_permission trace can name the workflow a step
        # belongs to — the step compiler has no other handle on the manifest.
        self._workflow_id = manifest.id

        # ── instance_id / prompt / subagents validation over the FLATTENED tree ──
        # (spec 012 R-02/R-03/R-05/R-06/R-09/F-03/F-11). Runs BEFORE per-step
        # compilation so a bad nested step is rejected before any Step is built.
        self._validate_step_identity_tree(manifest.steps, 0, set())

        steps: list[Step] = []
        for raw in manifest.steps:
            flat, _own = self._expand_step(raw, registry, trusted, trust)
            steps.extend(flat)

        # ── Workflow-level reference validation ──────────────────────────────
        where = f"workflow '{manifest.id}'"
        for cp in manifest.context_providers:
            if not registry.is_registered("context_provider", cp):
                raise CompilerError(f"unknown context_provider '{cp}' in {where}")
            self._check_trust(registry, "context_provider", cp, trusted, where)

        # image-input Wave 1: validate declared input_provider references (mirrors the
        # context_provider loop exactly). Dormant — no manifest declares the key.
        for ip in getattr(manifest, "input_providers", []) or []:
            if not registry.is_registered("input_provider", ip):
                raise CompilerError(f"unknown input_provider '{ip}' in {where}")
            self._check_trust(registry, "input_provider", ip, trusted, where)

        deliverable = self._compile_deliverable(manifest, registry, trusted)

        # ── Trust-conditional Limits materialization (FANOUT-09 / OBS-01) ─────
        # The formerly declared-but-inert ``manifest.limits`` is now materialized into
        # a typed ``Limits`` on the CompiledWorkflow (consumed by the run-entry
        # BudgetManager.from_limits). Under a TRUSTED (file/builtin) manifest a Limits
        # cap may RAISE above the default ceiling; under an UNTRUSTED (user/db) manifest
        # a cap that RAISES any ceiling is a CompilerError naming the dimension (user/db
        # may only LOWER — the 08-03/10-02 precedent).
        limits = self._compile_limits(
            getattr(manifest, "limits", None), trusted, where
        )

        # ── Topo-validate the Step DAG (cycle-free, no duplicate agents) ──────
        # R-09 regression guard (spec 014): _validate_dag's Kahn-algorithm graph
        # must be built ONLY from step.depends_on and must NEVER read
        # route.outcomes — identical carve-out to fanout/task_source today (route
        # targets are a separate, dedicated resolution pass — _validate_route_targets
        # below — invisible to the DAG's cycle check). Zero changes to _validate_dag
        # itself back this: the assertion inspects its live source rather than
        # duplicating/re-deriving its graph, so a future edit that folds route data
        # into the Kahn graph trips this immediately.
        assert "route" not in inspect.getsource(self._validate_dag), (
            "R-09 violated: _validate_dag must never reference step.route/outcomes"
        )
        self._validate_dag(steps)

        # ── Fan-out source_step-must-be-upstream guard (D9 / FANOUT-05) ───────
        self._validate_fanout_source_upstream(steps)

        # ── Conditional-route target resolution guard (spec 014 / R-10/R-27) ──
        self._validate_route_targets(steps)

        # ── Leaf computation (spec 014 / R-26) ─────────────────────────────────
        self._compute_is_leaf(steps)

        clarify_raw = manifest.clarify or {}
        clarify = ClarifySpec(
            mode=clarify_raw.get("mode", "auto"),
            defaults=list(clarify_raw.get("defaults", []) or []),
            rounds=int(clarify_raw.get("rounds", 1) or 1),
        )

        # ── WIRE-01: top-level model: → CompiledWorkflow.model (D-14) ─────────
        # The manifest top-level ``model:`` is the workflow-default policy (ModelResolver
        # tier 4, model_policy.py:101). Absent → the empty ``ModelPolicy()`` default
        # (model is None) so every existing manifest resolves exactly as today (parity).
        workflow_model = (
            self._compile_model_policy(manifest.model, where)
            if getattr(manifest, "model", None) is not None
            else ModelPolicy()
        )

        return CompiledWorkflow(
            id=manifest.id,
            steps=steps,
            model=workflow_model,
            context_providers=list(manifest.context_providers),
            input_providers=list(getattr(manifest, "input_providers", []) or []),
            seed_files=dict(manifest.seed_files),
            # Phase 11 / FANOUT-03: the workflow-level named-worker allow-list, pure data
            # (INV-5). run_fanout validates a named worker against this list + the agent
            # registry BEFORE any spawn — a disallowed worker is rejected pre-spawn.
            allowed_workers=self._allowed_workers(manifest, steps),
            deliverable=deliverable,
            planner=manifest.planner,
            clarify=clarify,
            limits=limits,
            # Plan 33-05 / INV-5: carry the manifest's optional chat/concierge DATA
            # block verbatim onto the compiled plan. Pure data pass-through — NO
            # control-flow keys off it (the run Concierge reads it via getattr). A
            # manifest without the key ⇒ {} (parity — the 5 goldens are untouched).
            chat=dict(getattr(manifest, "chat", {}) or {}),
        )

    # ── Trust-conditional Limits (FANOUT-09 / OBS-01 / 08-03/10-02 precedent) ──

    @staticmethod
    def _compile_limits(raw_limits: object, trusted: bool, where: str) -> Limits:
        """Materialize the workflow ``limits:`` dict → a typed ``Limits`` (trust-conditional).

        ``None`` (no ``limits:`` key) → the empty ``Limits()`` (every cap ``None`` →
        run_fanout falls back to the module-constant defaults; parity — every existing
        manifest is untouched). A declared block coerces each value onto the ``Limits``
        slot.

        Trust rule (the static budget ceiling gate): under a TRUSTED (file/builtin)
        manifest a cap may RAISE above ``_LIMITS_DEFAULT_CEILING`` (engineer-authored).
        Under an UNTRUSTED (user/db) manifest a cap that RAISES any ceiling is a
        ``CompilerError`` NAMING the offending dimension — a user/db manifest may only
        LOWER a cap (08-03 AGENT.md-only-lowers + 10-02 ceiling precedent). ``max_tokens``
        is omitted from the raise-rejection set (it has no module-constant ceiling; a
        user/db manifest declaring it only constrains itself).
        """
        if raw_limits is None:
            return Limits()
        if not isinstance(raw_limits, dict):
            raise CompilerError(
                f"workflow 'limits' must be a mapping in {where}; "
                f"got {type(raw_limits).__name__}"
            )
        allowed = {"max_tokens", "max_subagents", "max_depth", "wall_clock_seconds"}
        extra = set(raw_limits) - allowed
        if extra:
            raise CompilerError(
                f"unknown limits key(s) {sorted(extra)} in {where} — manifests are "
                f"pure data; only {sorted(allowed)} are valid Limits caps (INV-5)"
            )
        if not trusted:
            # A user/db manifest may only LOWER a cap. A declared value ABOVE the default
            # ceiling RAISES it → reject naming the dimension (the static budget gate).
            for dim, ceiling in _LIMITS_DEFAULT_CEILING.items():
                declared = raw_limits.get(dim)
                if declared is not None and int(declared) > ceiling:
                    raise CompilerError(
                        f"limits.{dim}={declared} raises the cap above the default "
                        f"ceiling {ceiling} in {where} — a user/db manifest may only "
                        f"LOWER a budget cap, never raise it (FANOUT-09 / CAP-03)"
                    )
        return Limits(
            max_tokens=raw_limits.get("max_tokens"),
            max_subagents=raw_limits.get("max_subagents"),
            max_depth=raw_limits.get("max_depth"),
            wall_clock_seconds=raw_limits.get("wall_clock_seconds"),
        )

    # ── Trust check (CAP-03 / D-02) ──────────────────────────────────────────

    @staticmethod
    def _check_trust(
        registry: CapabilityRegistry,
        kind: str,
        name: str,
        trusted: bool,
        where: str,
    ) -> None:
        """Reject a not-user-allowed reference under an untrusted trust context.

        A no-op for a trusted (``file``/``builtin``) manifest — the default path,
        so every existing file-backed manifest compiles unrestricted (parity). For
        an untrusted (``user``/``db``) manifest, a reference that is registered but
        not ``user_allowed`` raises a ``CompilerError`` NAMING the ``(kind, name)``
        (the seam that keeps exec/secrets/spawn off the user palette). Called at the
        SAME per-reference site as ``is_registered`` — the validation path is not
        forked. (The owner allow-list is a later-phase seam: DB manifests are Q5/
        later, so a missing allow-list defaults to the ``user_allowed`` flag only.)
        """
        if trusted:
            return
        if not registry.is_user_allowed(kind, name):
            raise CompilerError(
                f"capability ({kind!r}, {name!r}) is not user-allowed in {where} "
                f"— a user/db manifest may not reference it (CAP-03)"
            )

    # ── instance_id / prompt / subagents validation (spec 012) ──────────────

    @staticmethod
    def _step_where(raw: dict) -> str:
        """Build the ``where`` label for an error message, mirroring ``_compile_step``."""
        agent_id = raw.get("agent")
        if isinstance(agent_id, str) and agent_id.strip():
            return f"step '{agent_id}'"
        instance_id = raw.get("instance_id")
        if isinstance(instance_id, str) and instance_id.strip():
            return f"step '{instance_id}'"
        return "step '<unknown>'"

    def _validate_step_identity_tree(
        self,
        raw_steps: list,
        subagents_depth: int,
        seen_instance_ids: set[str],
    ) -> None:
        """Recursively validate ``instance_id``/``prompt``/``subagents`` over the tree.

        Walks ``raw_steps`` (a top-level ``manifest.steps`` list or a nested
        ``subagents.steps`` list) and, for every raw step dict:

          * rejects an unknown step key (INV-5 — applies at every nesting level, not
            just the top);
          * validates ``instance_id`` shape (R-03) and uniqueness across the
            FLATTENED tree — ``seen_instance_ids`` is a single set threaded through
            the whole recursion, so a grandchild sharing a top-level id is caught
            (F-03), not just siblings at the same level;
          * rejects a non-empty ``prompt`` on a step whose ``agent`` is not
            ``"custom-agent"`` (R-06);
          * validates a declared ``subagents`` block (mode/task_source/steps, R-04),
            rejects nesting deeper than two levels (R-05/F-03), and recurses into
            ``subagents.steps`` with ``subagents_depth + 1``.

        Every error NAMES the offending field and the step it appeared in (R-09).
        This pass only VALIDATES — it never expands ``subagents`` into child Steps
        (that is a later task) and never mints synthetic agent ids.
        """
        for raw in raw_steps:
            where = self._step_where(raw)

            extra = set(raw) - _ALLOWED_STEP_KEYS
            if extra:
                raise CompilerError(
                    f"unknown step key(s) {sorted(extra)} in {where} — manifests "
                    f"are pure data; a control-flow/DSL field has nowhere to live "
                    f"(INV-5)"
                )

            instance_id = raw.get("instance_id")
            if instance_id is not None:
                if not isinstance(instance_id, str) or not _INSTANCE_ID_RE.match(
                    instance_id
                ):
                    raise CompilerError(
                        f"invalid instance_id {instance_id!r} in {where} — must "
                        f"match ^[a-z0-9][a-z0-9-]*$ (R-03)"
                    )
                if instance_id in seen_instance_ids:
                    raise CompilerError(
                        f"duplicate instance_id {instance_id!r} in {where} — "
                        f"instance_id must be unique across the whole workflow, "
                        f"including nested subagents.steps (R-03/F-03)"
                    )
                seen_instance_ids.add(instance_id)

            prompt = raw.get("prompt")
            agent_id = raw.get("agent")
            if prompt and agent_id != "custom-agent":
                raise CompilerError(
                    f"step 'prompt' in {where} is only valid on a 'custom-agent' "
                    f"step — built-in agents keep the existing prompt-override "
                    f"mechanism (app/agents/prompt_overrides.py) (R-06)"
                )

            raw_subagents = raw.get("subagents")
            if raw_subagents is None:
                continue
            if not isinstance(raw_subagents, dict):
                raise CompilerError(
                    f"step 'subagents' must be a mapping in {where}; "
                    f"got {type(raw_subagents).__name__}"
                )
            extra_sub = set(raw_subagents) - _ALLOWED_SUBAGENTS_KEYS
            if extra_sub:
                raise CompilerError(
                    f"unknown subagents key(s) {sorted(extra_sub)} in {where} — "
                    f"manifests are pure data; a control-flow/DSL field has "
                    f"nowhere to live (INV-5)"
                )

            mode = raw_subagents.get("mode")
            if mode not in _ALLOWED_SUBAGENT_MODES:
                raise CompilerError(
                    f"unknown subagents.mode {mode!r} in {where} — must be one "
                    f"of {sorted(_ALLOWED_SUBAGENT_MODES)} (R-04)"
                )
            task_source = raw_subagents.get("task_source")
            if mode == "fanout" and not task_source:
                raise CompilerError(
                    f"subagents.task_source is required in {where} when "
                    f"subagents.mode is 'fanout' (R-04)"
                )
            if mode != "fanout" and task_source is not None:
                raise CompilerError(
                    f"subagents.task_source in {where} is only valid when "
                    f"subagents.mode is 'fanout' (R-04)"
                )

            # T34 used to reject max_parallel on a 'parallel' group because nothing
            # honored it — the siblings ran serially regardless, so accepting a bound
            # would have made the manifest read as if it constrained something real.
            # It now binds: the group compiles to a parallel_group step whose
            # FanoutSpec.max_parallel is the kernel's concurrency cap (clamped to
            # DEFAULT_MAX_CONCURRENCY, as everywhere else). Validate the value here
            # so a nonsensical bound fails at compile time rather than silently
            # falling back to the default at run time.
            _mp = raw_subagents.get("max_parallel")
            if mode == "parallel" and _mp is not None:
                if not isinstance(_mp, int) or isinstance(_mp, bool) or _mp < 1:
                    raise CompilerError(
                        f"subagents.max_parallel in {where} must be an integer >= 1; "
                        f"got {_mp!r}"
                    )

            child_steps = raw_subagents.get("steps")
            if not isinstance(child_steps, list) or not child_steps:
                raise CompilerError(
                    f"subagents.steps in {where} must be a non-empty list (F-11)"
                )
            if mode == "fanout" and len(child_steps) > 1:
                raise CompilerError(
                    f"subagents.steps in {where} has {len(child_steps)} entries "
                    f"when subagents.mode is 'fanout' — a fan-out clones ONE "
                    f"worker template; declare exactly one child (R-04)"
                )

            if subagents_depth + 1 > _MAX_SUBAGENTS_DEPTH:
                raise CompilerError(
                    f"subagents in {where} nests deeper than "
                    f"{_MAX_SUBAGENTS_DEPTH} levels — a fourth-level "
                    f"(great-grandchild) subagents group is rejected (R-05)"
                )

            self._validate_step_identity_tree(
                child_steps, subagents_depth + 1, seen_instance_ids
            )

    # ── subagents expansion (spec 012 R-17/R-18/R-19 / D-02 / T12-T13) ──────

    def _expand_step(
        self, raw: dict, registry: CapabilityRegistry, trusted: bool, trust: str
    ) -> tuple[list[Step], Step]:
        """Compile ``raw`` into its own ``Step`` plus, for a declared ``subagents``
        group, the flattened list of every step it expands to (D-02).

        Returns ``(flat, own)`` where ``flat`` is the ordered list of ALL compiled
        steps this raw step expands to (children/grandchildren first, ``own``
        last) and ``own`` is the compiled ``Step`` for ``raw`` itself — the caller
        needs ``own`` (not just its position in ``flat``) to wire sibling/parent
        edges by ``agent_id``.

        No new scheduler, no runtime branch (D-02): this purely emits ordinary
        ``Step``s plus ``depends_on`` edges. The existing Kahn topo-sort in
        ``_validate_dag`` is what turns those edges into children-before-parent —
        this method never orders anything itself beyond building ``flat`` in the
        depth-first child-before-parent sequence the DAG sort will also produce.

        ``subagents.mode``:
          * ``parallel``/``sequential`` (R-17/R-18/R-19, T12/T13): children are
            expanded depth-first (grandchildren before their own child, R-19) and
            emitted BEFORE the parent; the parent's ``depends_on`` gains every
            DIRECT child's ``agent_id`` (merged with any ``depends_on`` the parent
            already declares — not clobbered), so children always run to
            completion before the parent starts (R-17). ``sequential`` additionally
            chains sibling ``depends_on`` (child *i* depends on child *i-1*, R-18);
            ``parallel`` adds NO edges between siblings, so the DAG leaves them
            free to run concurrently (bounded by ``max_parallel`` — R-18). Step has
            no existing concurrency-hint field distinct from ``FanoutSpec.max_parallel``
            (a different mechanism: multiplying ONE worker template, not bounding N
            already-distinct sibling steps), so the declared ``max_parallel`` is
            NOT carried onto the child Steps here — reported to the caller as a gap
            rather than inventing a new ``Step`` field.
          * ``fanout`` (T14, R-18/AC-08/F-05/F-10): an ADAPTER over the existing
            ``FanoutSpec``/``run_fanout`` machinery — NO new fan-out code path.
            The group's single child (validated to be exactly one entry —
            ``_validate_step_identity_tree`` rejects more, a fan-out clones one
            template) is compiled and then augmented in place: ``strategy`` is
            set to ``"fanout_batch"`` (the strategy that reads ``task_source``/
            ``fanout`` and calls ``ctx.runner.run_fanout`` — ``fanout_batch.py``),
            ``task_source`` becomes the GROUP's (already-validated) task_source,
            and ``fanout`` becomes ``FanoutSpec(mode="parallel", max_parallel=
            <group's declared value or None>, agent="self")`` — the exact shape
            ``sample_fanout/workflow.yaml`` hand-authors today. The parent
            (``raw`` itself) is compiled normally and gains a ``depends_on`` edge
            on the fanned-out child, same as ``parallel``/``sequential`` (R-17).
            ``run_fanout`` and the budget ceiling (``max_subagents=8``,
            ``max_depth=2``) apply completely unchanged.
          * absent: no expansion, ``raw`` compiles to exactly one ``Step``.
        """
        flat: list[Step] = []
        extra_depends_on: list[str] = []
        direct_children: list[Step] = []
        parallel_group_children: list[str] = []

        raw_subagents = raw.get("subagents")
        if isinstance(raw_subagents, dict) and raw_subagents.get("mode") == "fanout":
            # T14: adapter over the existing FanoutSpec/run_fanout machinery
            # (D-02). Exactly one child (enforced by
            # _validate_step_identity_tree) is compiled and then materialized
            # with the group's task_source + a FanoutSpec — no new spawn/
            # scheduling logic lives here, only field wiring onto the SAME
            # Step shape the fanout_batch strategy already reads.
            where = self._step_where(raw)
            child_raws = raw_subagents.get("steps") or []
            child_flat, child_own = self._expand_step(
                child_raws[0], registry, trusted, trust
            )
            flat.extend(child_flat)

            child_own.task_source = self._compile_task_source(
                raw_subagents.get("task_source"), where, registry, trusted
            )
            child_own.fanout = FanoutSpec(
                mode="parallel",
                max_parallel=raw_subagents.get("max_parallel"),
                agent="self",
            )
            child_own.strategy = "fanout_batch"

            extra_depends_on = [child_own.agent_id]
        elif isinstance(raw_subagents, dict) and raw_subagents.get("mode") in (
            "parallel",
            "sequential",
        ):
            mode = raw_subagents["mode"]
            child_raws = raw_subagents.get("steps") or []
            for child_raw in child_raws:
                child_flat, child_own = self._expand_step(
                    child_raw, registry, trusted, trust
                )
                flat.extend(child_flat)
                direct_children.append(child_own)

            if mode == "sequential":
                for i in range(1, len(direct_children)):
                    prev_id = direct_children[i - 1].agent_id
                    if prev_id not in direct_children[i].depends_on:
                        direct_children[i].depends_on = list(
                            direct_children[i].depends_on
                        ) + [prev_id]

            extra_depends_on = [c.agent_id for c in direct_children]

            if mode == "parallel":
                # Removing the sibling edges is not enough to get concurrency: the
                # engine's dispatch loop walks the compiler's flat topological order
                # one step at a time, so edge-free siblings still ran strictly
                # serially (measured: 13ms gap, zero overlap). Wire them to the
                # kernel fan-out instead — the one place in this engine that
                # actually runs agents concurrently (INV-12).
                #
                # The children stay in `flat`, so they remain in `compiled.steps`,
                # the roster, the artifact graph and `agent_exists`. They are marked
                # `dispatched_by` so the SERIAL loop skips them; the parent spawns
                # them through run_fanout instead.
                parallel_group_children = [c.agent_id for c in direct_children]

        own = self._compile_step(raw, registry, trusted, trust)

        if parallel_group_children:
            # The children stay in `flat`, so they remain in `compiled.steps`, the
            # roster, the artifact graph and `agent_exists`. Marking them
            # `dispatched_by` removes them from the SERIAL loop only — the parent
            # spawns them through run_fanout instead.
            for child in direct_children:
                child.dispatched_by = own.agent_id
            own.strategy = "parallel_group"
            own.fanout = FanoutSpec(
                mode="parallel",
                max_parallel=raw_subagents.get("max_parallel"),
                # Heterogeneous fan-out: request i → workers[i]. An existing
                # run_fanout field, not a new mechanism.
                workers=parallel_group_children,
                count=len(parallel_group_children),
            )
        if extra_depends_on:
            merged = list(own.depends_on)
            for dep in extra_depends_on:
                if dep not in merged:
                    merged.append(dep)
            own.depends_on = merged
        flat.append(own)
        return flat, own

    @staticmethod
    def _allowed_workers(manifest: object, steps: list[Step]) -> list[str]:
        """The manifest's declared worker allow-list, plus every parallel-group child.

        ``run_fanout`` rejects any NAMED worker absent from this list before it
        spawns (FANOUT-03). A ``subagents: {mode: parallel}`` child is named in the
        very manifest being compiled, so adding it here restates what the author
        already wrote rather than widening anything — a worker the author did NOT
        declare as a child still cannot reach the spawn path. Without this, using
        the mode would mean also hand-maintaining a parallel copy of every child id
        under ``allowed_workers``, and forgetting one is a run-time ``FanoutError``.

        Declared order is preserved and children are appended in plan order, so the
        list is deterministic. A manifest with no parallel group returns exactly the
        declared list (parity).
        """
        declared = list(getattr(manifest, "allowed_workers", []) or [])
        out = list(declared)
        for step in steps:
            if getattr(step, "dispatched_by", "") and step.agent_id not in out:
                out.append(step.agent_id)
        return out

    # ── Step compilation ─────────────────────────────────────────────────────

    def _compile_step(
        self, raw: dict, registry: CapabilityRegistry, trusted: bool, trust: str
    ) -> Step:
        """Map one raw step dict → a typed ``Step``, validating each reference."""
        agent_id = raw.get("agent")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise CompilerError(
                f"step missing a non-empty 'agent' id: {raw!r}"
            )
        where = f"step '{agent_id}'"

        # Strict step-level key rejection (D-08 / INV-5): a DSL/control-flow
        # field at step level has nowhere to live. Name the offending key(s).
        extra = set(raw) - _ALLOWED_STEP_KEYS
        if extra:
            raise CompilerError(
                f"unknown step key(s) {sorted(extra)} in {where} — manifests "
                f"are pure data; a control-flow/DSL field has nowhere to live "
                f"(INV-5)"
            )

        strategy = raw.get("strategy", "single_shot")
        if not registry.is_registered("strategy", strategy):
            raise CompilerError(f"unknown strategy '{strategy}' in {where}")
        self._check_trust(registry, "strategy", strategy, trusted, where)

        gates = list(raw.get("gates", []) or [])
        for gate in gates:
            if not registry.is_registered("gate", gate):
                raise CompilerError(f"unknown gate '{gate}' in {where}")
            self._check_trust(registry, "gate", gate, trusted, where)

        # At most ONE human-family gate per step. A HITL pause is keyed durably on
        # ``gate_key = f"{run_id}:{agent_id}:{visit_count}"`` (engine.py) — the gate
        # NAME is not part of it — so two HITL gates on the same step in the same
        # visit would resolve to the same durable slot: the second pause would read
        # the first one's resolution and the run would advance past a review nobody
        # answered. Rejecting it here makes that a compile error naming the step
        # rather than a silent mis-resume at runtime.
        _hitl = [g for g in gates if g in ("human", "before-human", "approval")]
        if len(_hitl) > 1:
            raise CompilerError(
                f"step in {where} declares more than one human-review gate "
                f"({', '.join(sorted(_hitl))}) — a step may declare at most one, "
                f"because all HITL gates share one durable gate_key per visit"
            )

        # Declared executable hooks (08-08 / CR-01/WR-03): a step fires ONLY the
        # hooks it declares here (filtered by permission at the firing point) — NOT
        # every registered executable hook. A legacy step (prototype/od_/ppt/code-gen)
        # declares no hooks → fires NOTHING (parity). Name-resolved + trust-checked
        # like every other capability reference (INV-4 / CAP-03).
        # KAN-73: inject the default audit_logger hook for every step that does NOT
        # explicitly declare hooks:. This enables default audit trails without
        # requiring every manifest to be edited. Steps that declare hooks: [] or
        # hooks: [something] are untouched — explicit declaration always wins.
        _raw_hooks = raw.get("hooks")
        if _raw_hooks is None:
            # No hooks key declared → inject the default audit hook so every
            # agent execution produces an audit record by default (KAN-73).
            # Also inject secret_scan so every agent write is security-scanned
            # by default (KAN-73 "security hooks enabled by default").
            # Only inject when the hook is actually registered (graceful degradation
            # if the capability package is not yet loaded).
            _DEFAULT_AUDIT_HOOKS = ["audit_logger", "secret_scan"]
            hooks = [
                h for h in _DEFAULT_AUDIT_HOOKS
                if registry.is_registered("hook", h)
            ]
        else:
            hooks = list(_raw_hooks or [])
        for hook in hooks:
            if not registry.is_registered("hook", hook):
                raise CompilerError(f"unknown hook '{hook}' in {where}")
            self._check_trust(registry, "hook", hook, trusted, where)

        validators = list(raw.get("validators", []) or [])
        for v in validators:
            if not registry.is_registered("validator", v):
                raise CompilerError(f"unknown validator '{v}' in {where}")
            self._check_trust(registry, "validator", v, trusted, where)

        compaction = raw.get("compaction")
        if compaction is not None and not registry.is_registered("compaction", compaction):
            raise CompilerError(f"unknown compaction '{compaction}' in {where}")
        if compaction is not None:
            self._check_trust(registry, "compaction", compaction, trusted, where)

        post_step = raw.get("post_step")
        if post_step is not None and not registry.is_registered("post_step", post_step):
            raise CompilerError(f"unknown post_step '{post_step}' in {where}")
        if post_step is not None:
            self._check_trust(registry, "post_step", post_step, trusted, where)

        task_source = self._compile_task_source(
            raw.get("task_source"), where, registry, trusted
        )

        # ── Effective ToolPermissions (D-07 / INV-9) ─────────────────────────
        # Parse the step's declared ``tools:`` grant (default least-privilege when
        # omitted, so existing un-granted steps keep ``read_files`` ON / rest OFF —
        # parity), then resolve the effective set as
        # ``intersection(owner_allow_list, workflow_ceiling, step_grant)``. The
        # per-owner allow-list (Phase-5 run_capabilities / ScopedStore) is not bound
        # at compile time this phase (DB user manifests are later) → it defaults to
        # the workflow ceiling, so the intersection collapses to
        # ``workflow ∩ step`` WITHOUT raising any permission (least-privilege).
        step_grant = self._compile_tool_grant(raw.get("tools"), where)
        # MCP-03 / MCP-04: validate + gate each declared ``tools.mcp`` server.tool
        # reference at the SAME per-reference site as is_registered (no forked path).
        self._validate_mcp_grant(step_grant, gates, registry, trusted, where)

        # ── GRANT-PATH (EXEC-01) — trust-conditional privileged-grant rules ──
        # exec/network/secrets are ENGINEER-ONLY (file/builtin trust). A user/db
        # manifest granting any of them is a CompilerError NAMING the grant + step
        # (N3: exec is never user-grantable; T-10-02-01). file/builtin manifests may
        # author them, but an exec grant additionally requires the security+approval
        # gates (D-01, T-10-02-02). Both checks fire ONLY when a privileged perm is
        # granted, so the un-granted path is untouched (parity).
        if not trusted:
            granted_priv: list[str] = []
            if step_grant.exec:
                granted_priv.append("exec")
            if step_grant.network:
                granted_priv.append("network")
            if step_grant.secrets:
                granted_priv.append("secrets")
            # WR-01 fail-loud symmetry: spawn_subagents is engineer-only too — the
            # trust-conditional ceiling already collapses it OFF, but rejecting the
            # grant NAMES it instead of silently dropping it.
            if step_grant.spawn_subagents:
                granted_priv.append("spawn_subagents")
            if granted_priv:
                raise CompilerError(
                    f"step grant of {granted_priv!r} is not permitted for "
                    f"{trust!r}-trust manifests in {where} — "
                    f"exec/network/secrets/spawn_subagents are engineer-only "
                    f"(file/builtin trust)"
                )

        # D-01 GATES-REQUIRED: an exec-granting step MUST declare BOTH the
        # ``security`` and ``approval`` gates. The compiled plan must MIRROR the
        # authored manifest — the compiler raises, it NEVER auto-injects the gates
        # (RESEARCH anti-pattern; T-10-02-03).
        if step_grant.exec:
            missing = {"security", "approval"} - set(gates)
            if missing:
                raise CompilerError(
                    f"step grants tools.exec but is missing required gate(s) "
                    f"{sorted(missing)} in {where} — an exec-granting step MUST "
                    f"declare gates: [security, approval] (D-01)"
                )

        # ── Permissions (D-07 / INV-9 / GRANT-PATH) ─────────────────────────
        # The cap, the intersection and the trace all live in
        # ``agents/workflows/permission_caps.py``. The compiler does not decide
        # permissions — it hands the step's request and the manifest's trust to
        # the one module that does, and stores the answer on the Step.
        effective_tools = apply_cap(
            step_grant,
            trust,
            workflow=getattr(self, "_workflow_id", ""),
            agent=agent_id,
        )

        # ── Declarative fan-out (Phase 11 / Q12 / FANOUT-03) ─────────────────
        # The ``fanout`` key was already in _ALLOWED_STEP_KEYS but never constructed
        # (declared-but-inert). Materialize it now so ``Step.fanout`` is populated for
        # the fanout_batch strategy. A step with no ``fanout`` key keeps ``fanout=None``
        # (parity — every existing manifest is untouched).
        fanout = self._compile_fanout(raw.get("fanout"), where)

        # ── Declarative conditional route (spec 014 / R-02) ──────────────────
        # The ``route`` key was already in _ALLOWED_STEP_KEYS but never constructed
        # (declared-but-inert). Materialize it now, mirroring the fanout precedent
        # above. A step with no ``route`` key keeps ``route=None`` (parity — every
        # existing manifest is untouched).
        route = self._compile_route(raw.get("route"), where)

        # Declared typed-artifact kinds this step supplies (spec 014 / R-05b). Only
        # currently checked by R-27 (a route's decision-source step must declare
        # produces: ["route_decision"]) — pure data pass-through otherwise, same
        # accepted-but-materialized precedent as the fields above. A step omitting
        # the key keeps the dataclass default ([]) — parity.
        produces = list(raw.get("produces") or [])
        # R-29: pure data pass-through, same shape as ``produces`` above. The match is a
        # plain set intersection of arbitrary strings (engine._filter_consumed_outputs),
        # so a label like "greeting" is as valid as a registered artifact kind.
        consumes = list(raw.get("consumes") or [])

        # ── R-03 cross-field check (spec 014): gates:[conditional] ⇔ route: ────
        # A one-off check, NOT a generalized "capability requires gate" mechanism
        # (scope discipline — plan.md RISK-01: no existing sibling key cross-
        # validates against gates: today, so a general mechanism is speculative
        # until a second capability needs one).
        if "conditional" in gates and (route is None or not route.outcomes):
            raise CompilerError(
                f"{where} declares gates: [conditional] but has no route (or "
                f"route.outcomes is empty) — route: is required when "
                f"gates: [conditional] is declared (R-03)"
            )
        if route is not None and route.outcomes and "conditional" not in gates:
            raise CompilerError(
                f"{where} declares route: but is missing gates: [conditional] — "
                f"gates: [conditional] is required when route: is declared (R-03)"
            )

        # ── Declared on_conflict policy (Phase 11 / §13 / FANOUT-08 / CR-03) ──
        # Carry the authored policy onto the compiled Step (it was silently dropped
        # before — a manifest declaring ``on_conflict: abort`` was downgraded to the
        # human_gate default). Validated against the §13 four-policy set, fail-loud.
        on_conflict = raw.get("on_conflict", "human_gate") or "human_gate"
        if on_conflict not in _ALLOWED_ON_CONFLICT:
            raise CompilerError(
                f"unknown on_conflict policy {on_conflict!r} in {where} — must be "
                f"one of {sorted(_ALLOWED_ON_CONFLICT)} (§13 / FANOUT-08)"
            )

        # ── WIRE-01/02/03 + fix/depends_on: declared-but-inert keys made live ──
        # These keys were already in _ALLOWED_STEP_KEYS but the constructor dropped
        # them (accepted-but-dropped — D-17). Materialize them now, mirroring the
        # fanout/on_conflict inert-field-made-live precedent above. A step omitting
        # a key keeps the dataclass default (None / []), so every existing manifest
        # is byte-identical (parity) — the 5 characterization goldens declare none
        # of these per-step keys, so the merge/resolve consumers see the same input.
        model = self._compile_model_policy(raw.get("model"), where)        # WIRE-01
        retry = self._compile_retry_policy(raw.get("retry"), where)        # WIRE-02
        injects = list(raw.get("injects") or [])                          # WIRE-03
        fix = self._compile_fix_policy(raw.get("fix"), where)
        depends_on = list(raw.get("depends_on") or [])
        # Per-step render fail-closed knob (quick-260701-bob / REQUIRE-RENDER-KNOB).
        # Pure pass-through: None (absent) preserves the Settings-default behavior
        # (skip-is-a-pass — INV-3); a declared bool threads to the render consumers.
        raw_require_render = raw.get("require_render")
        require_render = (
            None if raw_require_render is None else bool(raw_require_render)
        )

        # ── Declaration-driven post-step solution-plan extraction flag ────────
        # (revision-pipeline-refactor / INV-1/SC-001): the engine branches on this
        # boolean, never on agent id or pipeline name. bool() coerces any truthy
        # YAML value (e.g. "true") to True without raising. Default False → DORMANT
        # on all existing steps → INV-3 byte/event-identical on the 5 goldens.
        produces_solution_plan = bool(raw.get("produces_solution_plan", False))

        # ── Per-instance identity + scoping (spec 012 R-01/R-02) ──────────────
        # instance_id/prompt/subagents were already validated (shape, uniqueness,
        # nesting depth, prompt/agent gating) by ``_validate_step_identity_tree``
        # before this method ran. Here we only MATERIALIZE the already-validated
        # values onto the Step — a step omitting any of these keeps the dataclass
        # default ("" / []), so every existing manifest is byte-identical (parity).
        # ``subagents`` itself is NOT carried — Step has no field for it yet; it is
        # validated and then dropped (expansion into child Steps is a later task).
        instance_id = str(raw.get("instance_id") or "")
        display_name = str(raw.get("name") or "")
        prompt = str(raw.get("prompt") or "")
        skills = list(raw.get("skills") or [])

        # ── Synthetic agent id for custom-agent instances (spec 012 R-03a/D-01) ──
        # The engine keys every step by agent_id, and the DAG check rejects
        # duplicate agent ids — so N reuses of the one blank custom-agent must
        # carry N distinct ids. A non-custom step's agent_id is untouched.
        if agent_id == "custom-agent" and instance_id:
            agent_id = f"{CUSTOM_AGENT_PREFIX}{instance_id}"

        return Step(
            agent_id=agent_id,
            strategy=strategy,
            gates=gates,
            hooks=hooks,
            task_source=task_source,
            validators=validators,
            compaction=compaction,
            post_step=post_step,
            require_render=require_render,
            tools=effective_tools,
            fanout=fanout,
            route=route,
            produces=produces,
            consumes=consumes,
            on_conflict=on_conflict,
            model=model,
            retry=retry,
            injects=injects,
            fix=fix,
            depends_on=depends_on,
            instance_id=instance_id,
            display_name=display_name,
            prompt=prompt,
            skills=skills,
            # Wave-scheduling conflict key — DERIVED, never authored, so
            # `_ALLOWED_STEP_KEYS` stays closed (INV-5). Semantics on
            # `Step.conflict_keys` in workflows/plan.py.
            #
            # Only custom-agent instances get one; a built-in step's write targets
            # are invisible to the compiler, and build_waves reads "no keys" as "no
            # conflict". Give built-ins real keys before enabling wave concurrency,
            # or two steps writing prototype.html could co-schedule.
            conflict_keys=[instance_id] if instance_id else [],
            produces_solution_plan=produces_solution_plan,
        )

    def _compile_task_source(
        self,
        raw_ts: object,
        where: str,
        registry: CapabilityRegistry,
        trusted: bool,
    ) -> "TaskSource | None":
        """Map a ``task_source:`` dict → a typed ``TaskSource``.

        Factored out of ``_compile_step`` so T14's fanout-group adapter can
        compile the group's ``subagents.task_source`` through the SAME
        validated path a step-level ``task_source:`` uses (no second copy of
        the strict-key / parser-registry-lookup logic).
        """
        if raw_ts is None:
            return None
        extra_ts = set(raw_ts) - _ALLOWED_TASK_SOURCE_KEYS
        if extra_ts:
            raise CompilerError(
                f"unknown task_source key(s) {sorted(extra_ts)} in {where} "
                f"— manifests are pure data; a control-flow/DSL field has "
                f"nowhere to live (INV-5)"
            )
        parser = raw_ts.get("parser")
        if parser is not None and not registry.is_registered("task_parser", parser):
            raise CompilerError(f"unknown task_parser '{parser}' in {where}")
        if parser is not None:
            self._check_trust(registry, "task_parser", parser, trusted, where)
        return TaskSource(
            kind=raw_ts.get("kind", "none"),
            parser=parser,
            target=raw_ts.get("target"),
            source_step=raw_ts.get("source_step"),
            spec_step=raw_ts.get("spec_step"),
        )

    @staticmethod
    def _compile_fanout(raw_fanout: object, where: str) -> "FanoutSpec | None":
        """Map a step ``fanout:`` dict → a typed ``FanoutSpec`` (Phase 11 / INV-5).

        ``None`` (no ``fanout:`` key) → ``None`` (parity — the step is not a fan-out).
        A declared block strict-key rejects any non-fanout field (INV-5; a
        control-flow/DSL field has nowhere to live) and coerces each value onto the
        FanoutSpec slot. The compiler only RECORDS the declaration — the worker
        selection / parallel-vs-sequential control flow lives inside ``run_fanout``,
        never here (INV-5 / no DSL).
        """
        if raw_fanout is None:
            return None
        if not isinstance(raw_fanout, dict):
            raise CompilerError(
                f"step 'fanout' must be a mapping in {where}; "
                f"got {type(raw_fanout).__name__}"
            )
        extra = set(raw_fanout) - _ALLOWED_FANOUT_KEYS
        if extra:
            raise CompilerError(
                f"unknown fanout key(s) {sorted(extra)} in {where} — manifests "
                f"are pure data; a control-flow/DSL field has nowhere to live (INV-5)"
            )
        workers = list(raw_fanout.get("workers", []) or [])
        return FanoutSpec(
            mode=raw_fanout.get("mode"),
            max_parallel=raw_fanout.get("max_parallel"),
            agent=raw_fanout.get("agent"),
            count=raw_fanout.get("count"),
            workers=workers,
            # The designated merge worker for on_conflict=merge_agent (§13 / CR-03).
            merge_agent=raw_fanout.get("merge_agent"),
        )

    @staticmethod
    def _compile_route(raw_route: object, where: str) -> "RouteSpec | None":
        """Map a step ``route:`` dict → a typed ``RouteSpec`` (spec 014 / INV-5).

        ``None`` (no ``route:`` key) → ``None`` (parity — the step is not a conditional
        gate). A declared block strict-key rejects any non-route field (INV-5; a
        control-flow/DSL field has nowhere to live) and coerces each value onto the
        RouteSpec slot. Each ``outcomes`` entry strict-key rejects any non-outcome
        field, validates ``trigger`` is exactly ``"step"`` or ``"workflow"``, and
        validates ``target`` is a non-empty string — building a typed ``RouteOutcome``
        per entry. ``trigger_max_depth`` is fixed at ``5`` in v1 (R-19, clarified): a
        declared value other than ``5`` is rejected here (the field's own default is
        already ``5``, so an author omitting the key is unaffected). The compiler only
        RECORDS the declaration — the condition evaluation / dispatch control flow
        lives inside the conditional-gate kernel, never here (INV-5 / no DSL).
        """
        if raw_route is None:
            return None
        if not isinstance(raw_route, dict):
            raise CompilerError(
                f"step 'route' must be a mapping in {where}; "
                f"got {type(raw_route).__name__}"
            )
        extra = set(raw_route) - _ALLOWED_ROUTE_KEYS
        if extra:
            raise CompilerError(
                f"unknown route key(s) {sorted(extra)} in {where} — manifests "
                f"are pure data; a control-flow/DSL field has nowhere to live (INV-5)"
            )

        raw_outcomes = raw_route.get("outcomes") or {}
        if not isinstance(raw_outcomes, dict):
            raise CompilerError(
                f"route 'outcomes' must be a mapping in {where}; "
                f"got {type(raw_outcomes).__name__}"
            )
        outcomes: dict[str, RouteOutcome] = {}
        for outcome_key, raw_outcome in raw_outcomes.items():
            if not isinstance(raw_outcome, dict):
                raise CompilerError(
                    f"route outcome {outcome_key!r} must be a mapping in {where}; "
                    f"got {type(raw_outcome).__name__}"
                )
            extra_outcome = set(raw_outcome) - _ALLOWED_OUTCOME_KEYS
            if extra_outcome:
                raise CompilerError(
                    f"unknown route outcome key(s) {sorted(extra_outcome)} in "
                    f"{where} — manifests are pure data; a control-flow/DSL field "
                    f"has nowhere to live (INV-5)"
                )
            trigger = raw_outcome.get("trigger")
            if trigger not in ("step", "workflow"):
                raise CompilerError(
                    f"route outcome {outcome_key!r} in {where} has invalid "
                    f"trigger {trigger!r} — must be exactly 'step' or 'workflow' "
                    f"(R-05b)"
                )
            target = raw_outcome.get("target")
            if not isinstance(target, str) or not target.strip():
                raise CompilerError(
                    f"route outcome {outcome_key!r} in {where} has a missing or "
                    f"empty 'target' — must be a non-empty string"
                )
            feedback = raw_outcome.get("feedback")
            if feedback is not None and not isinstance(feedback, str):
                raise CompilerError(
                    f"route outcome {outcome_key!r} in {where} has a non-string "
                    f"'feedback' ({type(feedback).__name__}) — must be a string "
                    f"or omitted (R-28)"
                )
            outcomes[outcome_key] = RouteOutcome(
                trigger=trigger, target=target, feedback=feedback
            )

        trigger_max_depth = raw_route.get("trigger_max_depth", 5)
        if trigger_max_depth != 5:
            raise CompilerError(
                f"route.trigger_max_depth={trigger_max_depth!r} in {where} — "
                f"the ONLY valid declared value in v1 is 5 (R-19, clarified); "
                f"omit the key to use the default"
            )

        return RouteSpec(
            condition_agent=raw_route.get("condition_agent"),
            outcomes=outcomes,
            default_next=raw_route.get("default_next"),
            loop_max_iterations=raw_route.get("loop_max_iterations", 5),
            trigger_max_depth=trigger_max_depth,
        )

    @staticmethod
    def _compile_model_policy(raw_model: object, where: str) -> "ModelPolicy | None":
        """Map a step/workflow ``model:`` dict → a typed ``ModelPolicy`` (WIRE-01 / D-14).

        ``None`` (no ``model:`` key) → ``None`` for a step (ModelResolver tier-2 sees
        no per-step override — parity). A declared block strict-key rejects any
        non-ModelPolicy field (INV-5 at the nested level) and coerces each value onto
        the ModelPolicy slot. The compiler only RECORDS the policy — ModelResolver
        (model_policy.py tiers 2/4) owns the precedence/fallback control flow.
        """
        if raw_model is None:
            return None
        if not isinstance(raw_model, dict):
            raise CompilerError(
                f"step/workflow 'model' must be a mapping in {where}; "
                f"got {type(raw_model).__name__}"
            )
        allowed = {"model", "max_tokens", "cost_class", "fallback"}
        extra = set(raw_model) - allowed
        if extra:
            raise CompilerError(
                f"unknown model key(s) {sorted(extra)} in {where} — manifests are "
                f"pure data; only {sorted(allowed)} are valid ModelPolicy keys (INV-5)"
            )
        return ModelPolicy(
            model=raw_model.get("model"),
            max_tokens=raw_model.get("max_tokens"),
            cost_class=raw_model.get("cost_class", "standard"),
            fallback=list(raw_model.get("fallback", []) or []),
        )

    @staticmethod
    def _compile_retry_policy(raw_retry: object, where: str) -> "RetryPolicy | None":
        """Map a step ``retry:`` dict → a typed ``RetryPolicy`` (WIRE-02 / D-15).

        ``None`` (no ``retry:`` key) → ``None`` (the RESUME-02 wrapper stays dormant —
        parity). A declared block strict-key rejects any non-RetryPolicy field (INV-5)
        and coerces each value onto the slot. The compiler only RECORDS the policy —
        the engine retry wrapper (gated on ``step.retry.max_attempts > 0``) owns the
        control flow.
        """
        if raw_retry is None:
            return None
        if not isinstance(raw_retry, dict):
            raise CompilerError(
                f"step 'retry' must be a mapping in {where}; "
                f"got {type(raw_retry).__name__}"
            )
        allowed = {"max_attempts", "backoff_seconds", "on"}
        extra = set(raw_retry) - allowed
        if extra:
            raise CompilerError(
                f"unknown retry key(s) {sorted(extra)} in {where} — manifests are "
                f"pure data; only {sorted(allowed)} are valid RetryPolicy keys (INV-5)"
            )
        kwargs: dict = {}
        if "max_attempts" in raw_retry:
            kwargs["max_attempts"] = int(raw_retry["max_attempts"])
        if "backoff_seconds" in raw_retry:
            kwargs["backoff_seconds"] = float(raw_retry["backoff_seconds"])
        if "on" in raw_retry:
            kwargs["on"] = list(raw_retry["on"] or [])
        return RetryPolicy(**kwargs)

    @staticmethod
    def _compile_fix_policy(raw_fix: object, where: str) -> "FixPolicy | None":
        """Map a step ``fix:`` dict → a typed ``FixPolicy`` (forward surface / D-17).

        ``None`` (no ``fix:`` key) → ``None`` (no validation fix-loop — parity). A
        declared block strict-key rejects any non-FixPolicy field (INV-5) and coerces
        each value onto the slot. Materialized so ``fix:`` is not accepted-but-dropped
        (D-17); the compiler only RECORDS the policy.
        """
        if raw_fix is None:
            return None
        if not isinstance(raw_fix, dict):
            raise CompilerError(
                f"step 'fix' must be a mapping in {where}; "
                f"got {type(raw_fix).__name__}"
            )
        allowed = {"mode", "max_attempts"}
        extra = set(raw_fix) - allowed
        if extra:
            raise CompilerError(
                f"unknown fix key(s) {sorted(extra)} in {where} — manifests are "
                f"pure data; only {sorted(allowed)} are valid FixPolicy keys (INV-5)"
            )
        kwargs: dict = {}
        if "mode" in raw_fix:
            kwargs["mode"] = raw_fix["mode"]
        if "max_attempts" in raw_fix:
            kwargs["max_attempts"] = int(raw_fix["max_attempts"])
        return FixPolicy(**kwargs)

    @staticmethod
    def _compile_tool_grant(raw_tools: object, where: str) -> ToolPermissions:
        """Map a step ``tools:`` grant block → a ``ToolPermissions`` (D-07 / INV-9).

        ``None`` (no ``tools:`` block) → the §8 least-privilege default
        (``read_files`` ON, everything else OFF/none) — so existing un-granted steps
        bind exactly what they bind today (parity). A declared block strict-key
        rejects any non-permission field (INV-5) and coerces each value onto the
        ToolPermissions slot (bools for the gate fields, lists for
        ``secrets``/``mcp``/``integrations``).
        """
        if raw_tools is None:
            return ToolPermissions()
        if not isinstance(raw_tools, dict):
            raise CompilerError(
                f"step 'tools' must be a permission-grant mapping in {where}; "
                f"got {type(raw_tools).__name__}"
            )
        extra = set(raw_tools) - _ALLOWED_TOOLS_KEYS
        if extra:
            raise CompilerError(
                f"unknown tools grant key(s) {sorted(extra)} in {where} — "
                f"manifests are pure data; a control-flow/DSL field has nowhere "
                f"to live (INV-5)"
            )
        # The vocabulary and the parse both live in ``permission_caps`` — the
        # compiler raises the diagnostic, it does not define what a permission is.
        return parse_grant(raw_tools)

    @staticmethod
    def _validate_mcp_grant(
        step_grant: ToolPermissions,
        gates: list,
        registry: CapabilityRegistry,
        trusted: bool,
        where: str,
    ) -> None:
        """Validate + gate the step's ``tools.mcp`` ``server.tool`` references (MCP-03/04).

        Per declared ``server.tool`` in ``step_grant.mcp`` (the SAME per-reference site
        as every other capability check — no forked path):

          * MCP-03: split ``server.tool``; the ``mcp_server`` MUST be registered (else
            ``CompilerError`` naming the offending ``server.tool``); under an UNTRUSTED
            (user/db) manifest the server MUST be ``user_allowed`` (else CompilerError);
            and the named ``tool`` MUST be in that server's exposed-tool allow-list
            (else CompilerError naming the ``server.tool``).
          * MCP-04: a POWERFUL/write server (``filesystem``/``postgres``, ``powerful=True``)
            requires the ``security`` gate on the step AND the ``secrets`` permission
            granted; a read-scoped server (gitlab_read/jira_read) binds ungated. A
            powerful reference without ``security`` + ``secrets`` is a ``CompilerError``.

        A reference missing the ``server.tool`` ``.`` separator is a CompilerError (the
        manifest must name BOTH the server and the tool).
        """
        mcp_refs = list(getattr(step_grant, "mcp", None) or [])
        if not mcp_refs:
            return
        from agents.capabilities.mcp_servers.catalog import CATALOG

        has_security_gate = "security" in (gates or [])
        granted_secrets = list(getattr(step_grant, "secrets", None) or [])

        for ref in mcp_refs:
            if "." not in str(ref):
                raise CompilerError(
                    f"mcp reference {ref!r} in {where} must be 'server.tool' "
                    f"(name BOTH the server and the tool) — MCP-03"
                )
            server, _, tool = str(ref).partition(".")
            if not registry.is_registered("mcp_server", server):
                raise CompilerError(
                    f"unknown mcp_server.tool {ref!r} in {where} — no registered "
                    f"mcp_server {server!r} (MCP-03)"
                )
            # Trust check (CAP-03): a user/db manifest may not reference a
            # not-user-allowed (powerful) server.
            if not trusted and not registry.is_user_allowed("mcp_server", server):
                raise CompilerError(
                    f"mcp_server {server!r} (referenced as {ref!r} in {where}) is "
                    f"not user-allowed — a user/db manifest may not reference it "
                    f"(MCP-03 / CAP-03)"
                )
            entry = CATALOG.get(server)
            if entry is None or not entry.is_tool_exposed(tool):
                raise CompilerError(
                    f"mcp tool {ref!r} in {where} is not in the {server!r} "
                    f"exposed-tool allow-list (MCP-03)"
                )
            # MCP-04 gating: a powerful/write server requires security + secrets.
            if entry.powerful and not (has_security_gate and granted_secrets):
                raise CompilerError(
                    f"mcp_server {server!r} (referenced as {ref!r} in {where}) is "
                    f"powerful/write — it requires the 'security' gate AND a "
                    f"'secrets' grant on the step (MCP-04); read-scoped servers "
                    f"bind ungated"
                )

    def _compile_deliverable(
        self, manifest: WorkflowManifest, registry: CapabilityRegistry, trusted: bool
    ) -> DeliverableSpec:
        """Validate + build the workflow's deliverable spec."""
        raw = manifest.deliverable or {}
        strategy = raw.get("strategy")
        if strategy is not None and not registry.is_registered("deliverable", strategy):
            raise CompilerError(
                f"unknown deliverable '{strategy}' in workflow '{manifest.id}'"
            )
        if strategy is not None:
            self._check_trust(
                registry,
                "deliverable",
                strategy,
                trusted,
                f"workflow '{manifest.id}'",
            )
        # DECLARED revision-intent (07-10 / WR-04): copied verbatim onto the compiled
        # model (default False). Coerced to bool so a truthy/None YAML scalar lands as
        # a clean flag; NO workflow-name knowledge lives here (INV-1).
        # ``mimetype`` is a thin pass-through (ISS-021 / 18-01): copied verbatim from
        # the manifest (default None). NO defaulting logic lives here — the
        # per-resolver default is computed at emission time (INV-5: no DSL/defaulting
        # in the compiler).
        return DeliverableSpec(
            strategy=strategy,
            name=raw.get("name"),
            revises_existing=bool(raw.get("revises_existing", False)),
            mimetype=raw.get("mimetype"),
        )

    # ── Fan-out source_step-must-be-upstream guard (D9 / FANOUT-05 / INV-5) ──

    @staticmethod
    def _validate_fanout_source_upstream(steps: list[Step]) -> None:
        """Reject a fan-out step whose ``task_source.source_step`` is not EARLIER (D9).

        Pure-data, INV-5-safe post-compile pass over the already-ordered ``steps``
        (per-step compilation runs in input order, so "earlier" == a strictly
        lower index). For every step whose ``strategy == "fanout_batch"`` that
        declares a truthy ``task_source.source_step``, the referenced id MUST be
        the agent id of a step at a lower index; a forward/self/unknown reference
        is a ``CompilerError`` NAMING the offending step + the bad ``source_step``
        (mirrors the ``CompilerError(f"... in {where}")`` style). Deterministic at
        compile time (SAVE + LAUNCH both compile), closing the "fan-out reads the
        empty / wrong producer" gap.

        Name-free (INV-1 / SC-001): the check compares ids POSITIONALLY — it keys
        only on the ``fanout_batch`` strategy name + the accumulated earlier-step
        id set, never on a workflow/agent-name literal. A non-fanout_batch step, or
        a fanout_batch step with no ``source_step``, is untouched (parity — the 5
        characterization goldens declare no such step).
        """
        upstream: set[str] = set()
        for step in steps:
            task_source = step.task_source
            source_step = (
                task_source.source_step if task_source is not None else None
            )
            if step.strategy == "fanout_batch" and source_step:
                if source_step not in upstream:
                    where = f"step '{step.agent_id}'"
                    raise CompilerError(
                        f"fanout_batch task_source.source_step "
                        f"'{source_step}' in {where} does not name an EARLIER "
                        f"step — a fan-out producer must precede the fan-out "
                        f"step (D9 / FANOUT-05)"
                    )
            upstream.add(step.agent_id)

    # ── Conditional-route target resolution guard (spec 014 / R-10) ──────────

    @staticmethod
    def _validate_route_targets(steps: list[Step]) -> None:
        """Reject a conditional-route outcome or ``default_next`` whose target does
        not resolve (spec 014 / R-10).

        Pure-data, INV-5-safe post-compile pass over the already-compiled ``steps``
        (mirrors ``_validate_fanout_source_upstream`` in structure — runs once,
        after the full step list compiles, at the same point that guard and
        ``_validate_dag`` already run). For every step's ``route.outcomes[...]``:

          * ``trigger == "step"``: ``target`` MUST be the ``agent_id`` of a step in
            THIS workflow's compiled step set — else a ``CompilerError`` NAMING the
            step, the outcome's condition-value key, and the unresolved target.
          * ``trigger == "workflow"``: ``target`` MUST be the literal ``"self"`` OR
            a reference to a real saved ``user_workflow_id``. Existing-helper
            search (as directed by this task): ``agents/registry.py`` has no
            ``user_workflow_id``/``WorkflowDefinition`` lookup of any kind.
            ``app/api/user_workflows.py`` has exactly one —
            ``_owned(db: Session, workflow_id: str, user: User) -> WorkflowDefinition``
            (`:413`, the sole non-test ``WorkflowDefinition``-by-id query in the
            codebase) — but it is owner-scoped
            (``WorkflowDefinition.user_id == user.id``), requires a live DB
            ``Session`` + the request's ``User``, and raises ``HTTPException`` — a
            web-layer, per-request helper. ``compile()`` receives only
            ``(manifest, registry, trust)``; it never gets a db session or a user
            (confirmed by ``_compile_check_manifest`` in that same file, which
            already compiles with ``trust="db"`` and zero db/user context), and
            this module's own docstring is explicit that it "NEVER imports the
            kernel ... or the web layer." Calling ``_owned`` from here would
            require threading a DB session + user through every ``compile()``
            call site (engine.py's ``compile_for_run``, ``_compile_check_manifest``,
            tests, …) — a signature/layering change, not a reuse. So a
            non-``"self"`` target is accepted here as a SYNTACTIC reference only
            (already non-empty-string-validated by ``_compile_route``); its DB
            existence/ownership is authoritatively resolved by that SAME
            ``_owned`` helper at launch/trigger time (kernel_services.py's
            ``run_trigger_workflow``), exactly as this manifest's other
            ``trust="db"`` references already defer ownership checks to the
            request-scoped launch path.
          * ``default_next``, when declared, is validated the SAME way as a
            ``trigger: "step"`` target (R-10).

        Resolvable id set: a step's own ``agent_id`` (the identifier every OTHER
        compile-time reference — ``depends_on``, ``fanout.task_source.source_step``
        — matches against) PLUS, for a custom-agent instance, its bare
        ``instance_id`` too. A custom-agent step's ``agent_id`` is the synthesized
        ``"custom-agent:<instance_id>"`` (`_compile_step`, R-03a/D-01) — but the
        checked-in reference fixtures (``ex_A1_loop``/
        ``branch_new``/…) author every ``route`` target as the bare
        ``instance_id`` (e.g. ``target: greet``, matching the step declaring
        ``instance_id: greet``), the natural human-facing id a workflow author
        writes. Accepting both forms is parity for a non-custom-agent step (whose
        ``instance_id`` is ``""`` and adds nothing to the set) and is what makes
        those fixtures compile (plan.md's own acceptance bar for this task).

        Name-free (INV-1 / SC-001): the check compares ids against the
        already-compiled step-id set, never a workflow/agent-name literal.

        Also extended with R-27 (spec 014): for every step whose ``route.outcomes``
        is non-empty, the DECISION SOURCE — ``route.condition_agent`` if set, else
        the step itself (R-05) — must declare ``produces: ["route_decision"]`` in
        the manifest. Resolved via the SAME dual agent_id/instance_id lookup as the
        outcome-target check above (``by_name``), so an author-facing bare
        ``instance_id`` reference on ``condition_agent`` resolves exactly like an
        outcome ``target`` does. An unresolvable ``condition_agent`` and a resolved
        step missing the declaration are both a ``CompilerError`` naming the step
        and its (attempted) decision-source step.
        """
        step_ids = {s.agent_id for s in steps} | {
            s.instance_id for s in steps if s.instance_id
        }
        # R-27: the same dual-identity lookup as step_ids above, but keyed to the
        # Step object itself (not just its id) so the decision-source's `produces`
        # can be read once resolved.
        by_name: dict[str, Step] = {}
        for s in steps:
            by_name[s.agent_id] = s
            if s.instance_id:
                by_name[s.instance_id] = s
        for step in steps:
            route = step.route
            if route is None:
                continue
            where = f"step '{step.agent_id}'"
            for outcome_key, outcome in route.outcomes.items():
                if outcome.trigger == "step" and outcome.target not in step_ids:
                    raise CompilerError(
                        f"route outcome {outcome_key!r} in {where} has "
                        f"trigger='step' target {outcome.target!r} which does not "
                        f"name a step id in this compiled workflow (R-10)"
                    )
                # trigger == "workflow": "self" is always valid; any other target
                # is a syntactic user_workflow_id reference only — see docstring
                # above for why its DB existence is not (and cannot be) checked
                # here.
            if route.default_next is not None and route.default_next not in step_ids:
                raise CompilerError(
                    f"route.default_next {route.default_next!r} in {where} does "
                    f"not name a step id in this compiled workflow (R-10)"
                )

            # ── R-27: the route's decision source must declare produces ───────
            if route.outcomes:
                decision_ref = route.condition_agent or step.agent_id
                decision_step = by_name.get(decision_ref)
                if decision_step is None:
                    raise CompilerError(
                        f"route.condition_agent {route.condition_agent!r} in "
                        f"{where} does not name a step id in this compiled "
                        f"workflow (R-27)"
                    )
                if "route_decision" not in decision_step.produces:
                    raise CompilerError(
                        f"{where}'s conditional route reads its decision from "
                        f"step '{decision_step.agent_id}' (resolved decision "
                        f"source), but that step does not declare "
                        f"produces: ['route_decision'] in the manifest — a "
                        f"conditional gate's decision source MUST declare the "
                        f"typed artifact its outcome match is read from (R-27)"
                    )

    # ── Leaf computation (spec 014 / R-26) ────────────────────────────────────

    @staticmethod
    def _compute_is_leaf(steps: list[Step]) -> None:
        """Set ``Step.is_leaf`` for every step (R-26): a pure graph-shape pass over
        the already-validated ``route``/``depends_on`` data — no new data source.

        Runs once, after ``_validate_route_targets`` (so every ``outcome.target`` /
        ``default_next`` is already known to resolve — R-10) and after
        ``_validate_dag`` (so ``depends_on`` is already known cycle-free — no
        ordering dependency either way, just a natural "after the graph is proven
        sane" placement, mirroring where ``_validate_fanout_source_upstream`` sits).

        A step has "nothing compiled to run after it" (is a leaf) unless ONE of:

          * it is named in some OTHER step's ``depends_on`` — that step is
            compiled to run after it regardless of route/array position;
          * it declares a non-empty ``route.outcomes`` with at least one
            ``trigger == "step"`` outcome, or a ``default_next`` — its own route
            IS its continuation (a route-having step never falls through to plain
            array-adjacency; a ``trigger == "workflow"`` outcome does not count —
            R-13 stops THIS run, it does not continue within this compiled
            workflow, so an all-workflow-trigger route with no ``default_next``
            makes the step a leaf);
          * it has no route, and the step immediately following it in manifest
            order exists AND is not itself named as a ``trigger == "step"``
            outcome target / ``default_next`` anywhere in the workflow — plain
            array-adjacency is the step's implicit continuation UNLESS that next
            step is really a branch sibling reached only via a jump (the
            ``ex_A2_branch`` case: ``say_hello``/``say_hola`` sit
            array-adjacent under one shared route step, R-26's whole point — a
            naive index+1 check would wrongly mark ``say_hello`` as non-leaf).

        For a workflow with no ``route`` anywhere (every pre-014 manifest), this
        collapses to exactly the old ``index == len(steps) - 1`` check (parity) —
        ``jump_target_idx`` is empty, so only the last array position lacks a
        next-step index.
        """
        index_of: dict[str, int] = {}
        for i, step in enumerate(steps):
            index_of[step.agent_id] = i
            if step.instance_id:
                index_of[step.instance_id] = i

        depended_on: set[str] = set()
        for step in steps:
            depended_on.update(step.depends_on or [])

        jump_target_idx: set[int] = set()
        for step in steps:
            if step.route is None:
                continue
            for outcome in step.route.outcomes.values():
                if outcome.trigger == "step" and outcome.target in index_of:
                    jump_target_idx.add(index_of[outcome.target])
            if step.route.default_next and step.route.default_next in index_of:
                jump_target_idx.add(index_of[step.route.default_next])

        for i, step in enumerate(steps):
            if step.agent_id in depended_on:
                step.is_leaf = False
                continue
            if step.route is not None and step.route.outcomes:
                has_next = any(
                    o.trigger == "step" for o in step.route.outcomes.values()
                ) or bool(step.route.default_next)
                step.is_leaf = not has_next
                continue
            step.is_leaf = (i + 1 >= len(steps)) or ((i + 1) in jump_target_idx)

    # ── DAG validation (no duplicate agents, no cycle) ───────────────────────

    @staticmethod
    def _validate_dag(steps: list[Step]) -> None:
        """Topo-validate the Step DAG.

        Steps form a declared sequence; optional ``depends_on`` edges (on the
        forward Task surface) are not yet author-exposed in 1A, so the DAG is the
        linear step list. We assert (a) no duplicate agent id and (b) no cycle in
        any declared step-to-step dependency (Kahn's algorithm over edges among
        the step set). An empty step list is valid (reverse_engineer, D-05).
        """
        if not steps:
            return

        ids = [s.agent_id for s in steps]
        seen: set[str] = set()
        for agent_id in ids:
            if agent_id in seen:
                raise CompilerError(
                    f"duplicate step agent id '{agent_id}' in workflow"
                )
            seen.add(agent_id)

        # Build the dependency graph from any declared depends_on among steps in
        # this workflow (forward-safe; today the sequence has no explicit edges).
        indeg: dict[str, int] = {a: 0 for a in ids}
        adj: dict[str, list[str]] = {a: [] for a in ids}
        for step in steps:
            for dep in getattr(step, "depends_on", []) or []:
                if dep in indeg:
                    adj[dep].append(step.agent_id)
                    indeg[step.agent_id] += 1

        # Kahn's algorithm: if we cannot remove every node, there is a cycle.
        queue = [a for a in ids if indeg[a] == 0]
        removed = 0
        while queue:
            node = queue.pop()
            removed += 1
            for nxt in adj[node]:
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    queue.append(nxt)

        if removed != len(ids):
            raise CompilerError("cycle detected in workflow Step DAG")
