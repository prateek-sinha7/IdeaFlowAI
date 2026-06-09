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
        steps = [self._compile_step(raw, registry, trusted) for raw in manifest.steps]

        # ── Workflow-level reference validation ──────────────────────────────
        where = f"workflow '{manifest.id}'"
        for cp in manifest.context_providers:
            if not registry.is_registered("context_provider", cp):
                raise CompilerError(f"unknown context_provider '{cp}' in {where}")
            self._check_trust(registry, "context_provider", cp, trusted, where)

        deliverable = self._compile_deliverable(manifest, registry, trusted)

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
            deliverable=deliverable,
            planner=manifest.planner,
            clarify=clarify,
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
        self, raw: dict, registry: CapabilityRegistry, trusted: bool
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
        workflow_ceiling = ToolPermissions()  # §8 least-privilege ceiling this phase
        effective_tools = intersect_permissions(
            workflow_ceiling, workflow_ceiling, step_grant
        )

        return Step(
            agent_id=agent_id,
            strategy=strategy,
            gates=gates,
            task_source=task_source,
            validators=validators,
            compaction=compaction,
            post_step=post_step,
            tools=effective_tools,
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
