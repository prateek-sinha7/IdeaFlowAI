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

from agents.capabilities.registry import CapabilityRegistry
from agents.workflows.manifest import WorkflowManifest
from agents.workflows.plan import (
    ClarifySpec,
    CompiledWorkflow,
    DeliverableSpec,
    FanoutSpec,
    Limits,
    Step,
    TaskSource,
    ToolPermissions,
    intersect_permissions,
)


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
        # forward surface (inert in Phase 4 — declared now, consumed Phase 6/7)
        "tools",
        "model",
        "fix",
        "fanout",
        "on_conflict",
        "retry",
        "injects",
        "depends_on",
    }
)

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

# EXACTLY the §13 on_conflict policy set a step may declare (FANOUT-08). The kernel
# ``_resolve_conflict`` dispatches on these four; an unknown policy is rejected at
# compile time (fail-loud) rather than silently falling back to human_gate.
_ALLOWED_ON_CONFLICT: frozenset[str] = frozenset(
    {"human_gate", "merge_agent", "partial", "abort"}
)

# EXACTLY the keys a step ``tools:`` grant block may declare (D-08 at the nested
# level / D-07). These are the §8 ToolPermissions grant fields — pure data, no
# control flow (INV-5). Mirrors ``ToolPermissions`` (plan.py:45-) one-for-one.
_ALLOWED_TOOLS_KEYS: frozenset[str] = frozenset(
    {
        "read_files",
        "write_files",
        "exec",
        "git",
        "network",
        "secrets",
        "mcp",
        "integrations",
        "spawn_subagents",
    }
)


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
        steps = [
            self._compile_step(raw, registry, trusted, trust)
            for raw in manifest.steps
        ]

        # ── Workflow-level reference validation ──────────────────────────────
        where = f"workflow '{manifest.id}'"
        for cp in manifest.context_providers:
            if not registry.is_registered("context_provider", cp):
                raise CompilerError(f"unknown context_provider '{cp}' in {where}")
            self._check_trust(registry, "context_provider", cp, trusted, where)

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
        self._validate_dag(steps)

        clarify_raw = manifest.clarify or {}
        clarify = ClarifySpec(
            mode=clarify_raw.get("mode", "auto"),
            defaults=list(clarify_raw.get("defaults", []) or []),
        )

        return CompiledWorkflow(
            id=manifest.id,
            steps=steps,
            context_providers=list(manifest.context_providers),
            seed_files=dict(manifest.seed_files),
            # Phase 11 / FANOUT-03: the workflow-level named-worker allow-list, pure data
            # (INV-5). run_fanout validates a named worker against this list + the agent
            # registry BEFORE any spawn — a disallowed worker is rejected pre-spawn.
            allowed_workers=list(getattr(manifest, "allowed_workers", []) or []),
            deliverable=deliverable,
            planner=manifest.planner,
            clarify=clarify,
            limits=limits,
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

        # Declared executable hooks (08-08 / CR-01/WR-03): a step fires ONLY the
        # hooks it declares here (filtered by permission at the firing point) — NOT
        # every registered executable hook. A legacy step (prototype/od_/ppt/code-gen)
        # declares no hooks → fires NOTHING (parity). Name-resolved + trust-checked
        # like every other capability reference (INV-4 / CAP-03).
        hooks = list(raw.get("hooks", []) or [])
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

        task_source = None
        raw_ts = raw.get("task_source")
        if raw_ts is not None:
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
            task_source = TaskSource(
                kind=raw_ts.get("kind", "none"),
                parser=parser,
                target=raw_ts.get("target"),
                source_step=raw_ts.get("source_step"),
                spec_step=raw_ts.get("spec_step"),
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
            if granted_priv:
                raise CompilerError(
                    f"step grant of {granted_priv!r} is not permitted for "
                    f"{trust!r}-trust manifests in {where} — exec/network/secrets "
                    f"are engineer-only (file/builtin trust)"
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

        # ── Trust-conditional workflow ceiling (D-07 / INV-9 / GRANT-PATH) ───
        # For TRUSTED (file/builtin) trust the ceiling permits ``exec`` to survive
        # ``intersect_permissions`` so a file/builtin exec grant binds True; for an
        # untrusted trust the bare §8 least-privilege ceiling collapses exec OFF
        # (the user/db guard above already rejected the grant). ``network``/
        # ``secrets`` stay OFF in the ceiling for BOTH trust levels this phase — they
        # remain gate-blocked at runtime (out of scope here), so a file-trust
        # ``network:true`` grant still intersects to False.
        # ``spawn_subagents`` rides the SAME trust-conditional ceiling as ``exec``
        # (Phase 11 / FANOUT-03 / T-11-05-03): a TRUSTED (file/builtin) manifest may
        # grant the privileged fan-out spawn, so it survives the intersection and binds
        # True; an UNTRUSTED (user/db) manifest's ceiling collapses it OFF (and the
        # CAP-03 ``_check_trust`` of the ``tool:spawn_subagents`` reference — which is
        # ``user_allowed=False`` — already rejects the user/db grant upstream). Mirrors
        # the exec posture exactly: the privilege is engineer-authored-only.
        workflow_ceiling = ToolPermissions(exec=trusted, spawn_subagents=trusted)
        effective_tools = intersect_permissions(
            workflow_ceiling, workflow_ceiling, step_grant
        )

        # ── Declarative fan-out (Phase 11 / Q12 / FANOUT-03) ─────────────────
        # The ``fanout`` key was already in _ALLOWED_STEP_KEYS but never constructed
        # (declared-but-inert). Materialize it now so ``Step.fanout`` is populated for
        # the fanout_batch strategy. A step with no ``fanout`` key keeps ``fanout=None``
        # (parity — every existing manifest is untouched).
        fanout = self._compile_fanout(raw.get("fanout"), where)

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

        return Step(
            agent_id=agent_id,
            strategy=strategy,
            gates=gates,
            hooks=hooks,
            task_source=task_source,
            validators=validators,
            compaction=compaction,
            post_step=post_step,
            tools=effective_tools,
            fanout=fanout,
            on_conflict=on_conflict,
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
        bool_fields = ("read_files", "write_files", "exec", "git", "network", "spawn_subagents")
        list_fields = ("secrets", "mcp", "integrations")
        kwargs: dict = {}
        for f in bool_fields:
            if f in raw_tools:
                kwargs[f] = bool(raw_tools[f])
        for f in list_fields:
            if f in raw_tools:
                kwargs[f] = list(raw_tools[f] or [])
        return ToolPermissions(**kwargs)

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
        return DeliverableSpec(
            strategy=strategy,
            name=raw.get("name"),
            revises_existing=bool(raw.get("revises_existing", False)),
        )

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
