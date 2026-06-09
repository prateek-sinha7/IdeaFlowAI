"""agents/factory.py — composes system prompts and instantiates DeepAgentRunner.

Public API:
    create_runner(agent_id: str, ctx: AgentContext) -> DeepAgentRunner

AgentContext carries all runtime context needed to compose the system prompt:
  - user_request: the original user message
  - agent_outputs: prior-agent outputs keyed by agent ID (filtered view)
  - attached_skills: UI-attached skills [{name, content, source}]
  - attached_hooks: UI-attached hooks [{name, event, content}]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# Path to the guardrails directory
_GUARDRAILS_DIR = Path(__file__).resolve().parent / "guardrails"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class AgentContext:
    """Runtime context passed to create_runner().

    Constructed fresh for each agent invocation by the engine. The
    agent_outputs dict is a filtered view — it contains only the prior-agent
    outputs specified by spec.context_from, never the full accumulated outputs
    dict.
    """

    user_request: str                          # Original user message
    agent_outputs: dict[str, str] = field(default_factory=dict)
    attached_skills: list[dict] = field(default_factory=list)
    attached_hooks: list[dict] = field(default_factory=list)
    model: str | None = None                   # User-selected model ID (overrides system default)
    # od_context carries loaded template / design-system / craft content for
    # agents that declare an `injects` capability (od_prototype / od_ppt).
    # Keys: template_body, ds_id, ds_body, craft_block, template_id,
    #       is_design_system_required (deck conditional).
    od_context: dict | None = None
    # planning_context: cross-cutting guardrail (Phase 3 injects into system prompt).
    planning_context: dict | None = None
    # user_id: forwarded for Constitution injection from Workflow_Memory (T068)
    user_id: str | None = None
    # run_id: per-run id; create_runner roots the RunSandbox at <user>/<run>/
    run_id: str | None = None
    # prewarmed_constitution: the owner's Constitution, awaited ONCE at the async
    # engine run entry (before the SYNC create_runner calls) and stashed here so the
    # sync factory reads it WITHOUT awaiting inside the running event loop (AGENTRT-06 /
    # F4 / R12 — the production no-op fix). None ⇒ no Constitution set (graceful no-op,
    # matching the characterization runs which carry none → snapshots byte-identical).
    prewarmed_constitution: str | None = None


class TemplateMissingError(Exception):
    """Raised when an agent declares `injects` but the referenced template
    cannot be located. The ExecutionEngine catches this and halts the Workflow
    before any agent executes."""


@dataclass
class RuntimeBuildContext:
    """The seam the factory hands to the ``AgentRuntimeAdapter`` (08-05 / F5).

    ``create_runner`` (the composition root, permitted to import ``app``) does the
    spec-load / prompt-compose / tool-resolve / sandbox-build, then resolves the
    runtime via ``resolve("runtime", <id>)`` and asks the adapter to ``create`` the
    runner. The kernel-side runtime capability must NOT import ``app.*`` or call
    ``create_deep_agent`` (import-linter + INV-13 banned-pattern allow-list), so it
    cannot build the ``DeepAgentRunner`` itself — instead it invokes ``build``, a
    fully-bound zero-arg callable closing over the app-side construction the factory
    prepared. The adapter SELECTS the runtime and delegates construction (wrap, never
    replace).
    """

    agent_id: str
    build: "Callable[[], object]"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def create_runner(
    agent_id: str,
    ctx: AgentContext,
    *,
    checkpointer=None,
    interrupt_on: dict | None = None,
    thread_id: str | None = None,
):
    """Instantiate a DeepAgentRunner for the given agent ID and context.

    The LIVE pipeline entry point (the ExecutionEngine calls this for every
    agent). It loads the spec via ``load_agent_spec``, composes the system
    prompt via ``_compose_system_prompt``, resolves the per-agent tool-set via
    the ``tool_provider`` registry (``_resolve_runner_tools``), builds the per-run
    ``RunSandbox``, and constructs a ``DeepAgentRunner`` over a ``deepagents`` graph
    (native disk fs tools + a store-free ``report_task_complete``).

    **Sandbox (per-run, SHARED) vs checkpoint thread (per-agent, UNIQUE).**
    These two identifiers are split (plan §10 decision 2026-06-04 (b)):

    - The on-disk ``RunSandbox`` is rooted at ``<RUNS_ROOT>/<user>/<run>/`` from
      ``ctx.user_id`` + ``ctx.run_id`` and is **shared across every agent in a
      pipeline run** — that is how files like ``prototype.html`` (and code-gen
      deliverables) written by one agent persist for the next agent to read. It
      is deliberately keyed on ``ctx.run_id`` ONLY (never on ``thread_id``), so
      passing a per-agent ``thread_id`` does NOT fork the sandbox.
    - The LangGraph checkpoint ``thread_id`` isolates each agent's graph state
      and must be **unique per agent-invocation**, or sequential agents in the
      same run would collide on one checkpoint thread. The engine supplies a
      distinct id per agent (e.g. ``f"{pipeline_run_id}:{agent_id}"``); when
      omitted it falls back to ``ctx.run_id``.

    Args:
        agent_id: The agent to build (kebab-case folder/spec id).
        ctx: Runtime context. ``ctx.user_id`` + ``ctx.run_id`` root the per-run
            (shared) disk sandbox; ``ctx.model`` selects the chat model
            (``None`` ⇒ runner default via ``build_model``).
        checkpointer: Optional LangGraph checkpointer forwarded to the runner.
            The engine populates it with the per-run Postgres checkpointer
            (required for durable HITL/resume).
        interrupt_on: Optional ``{tool_name: True | InterruptOnConfig}`` HITL
            map forwarded to the runner; populated from per-agent HITL gate
            selections.
        thread_id: Optional caller-controlled LangGraph checkpoint thread id
            (per agent-invocation). Forwarded to the runner so each agent's
            graph state stays isolated; the disk sandbox is unaffected (it is
            per-run, keyed on ``ctx.run_id``). When ``None`` it falls back to
            ``ctx.run_id``. The engine passes a unique per-agent id (e.g.
            ``f"{pipeline_run_id}:{agent_id}"``).

    Raises:
        FileNotFoundError: propagated from the loader if agent_id is unknown.
        AgentSpecError: propagated from the loader if AGENT.md is malformed.
        KeyError: if spec.tools names a tool set with no registered ``tool_provider``
            (from ``_resolve_runner_tools`` → the registry, naming the unknown set).
    """
    # Lazy imports keep the factory import light and avoid dragging in the heavy
    # deepagents/langchain stack on import.
    from agents.loader import load_agent_spec
    from app.agents.deep_agent_runner import DeepAgentRunner
    from app.agents.sandbox import RunSandbox

    spec = load_agent_spec(agent_id)
    # Compose the system prompt — guardrails/skills/hooks/constitution/injection/
    # body, in the fixed injection order (see ``_compose_system_prompt``).
    system_prompt = _compose_system_prompt(spec, ctx)
    custom_tools, exclude_builtin_tools = _resolve_runner_tools(spec, ctx)

    # Per-run on-disk sandbox: <RUNS_ROOT>/<user>/<run>/. SHARED across every
    # agent in the pipeline run, so files (prototype.html, code-gen outputs)
    # written by one agent persist for the next — hence keyed on ctx.run_id
    # ONLY (NOT on the per-agent ``thread_id``). The runner roots its deepagents
    # FilesystemBackend at ``sandbox.root`` (traversal-proof).
    #   - Missing user_id ⇒ "anon" (RunSandbox additionally sanitises empty/
    #     unsafe segments to its own "anonymous"/"run" fallbacks).
    #   - Missing run_id ⇒ "adhoc": gives an isolated, deterministic dir for the
    #     (engine-less) no-run-id case.
    sandbox = RunSandbox(ctx.user_id or "anon", ctx.run_id or "adhoc")
    sandbox.ensure()

    # ``max_tokens`` is intentionally NOT passed: the runner's ``build_model``
    # already defaults to ``settings.MAX_OUTPUT_TOKENS``, so leaving it unset
    # yields the model ceiling without duplicating the constant here.
    #
    # F5 (08-05): the actual ``DeepAgentRunner`` construction is bound into a zero-arg
    # ``build`` closure and handed to the registry-resolved ``AgentRuntimeAdapter``
    # (``resolve("runtime", <id>)``). The adapter SELECTS/WRAPS the runtime — it never
    # imports ``app``/``create_deep_agent`` itself (INV-13 + import-linter); the
    # canonical ``create_deep_agent`` stays inside ``DeepAgentRunner`` (the allow-listed
    # ``app/agents/deep_agent_runner.py``). A future ``claude_code_cli``/``custom_runner``
    # slots in via the same port with NO kernel edit.
    def _build_deepagents_runner() -> DeepAgentRunner:
        return DeepAgentRunner(
            system_prompt=system_prompt,
            tools=custom_tools,
            model=ctx.model,
            run_sandbox=sandbox,
            checkpointer=checkpointer,
            # Checkpoint thread is per agent-invocation (caller-controlled): the
            # engine passes a unique id per agent so graph states never collide.
            # Falls back to the per-run ctx.run_id when omitted. NOTE: the sandbox
            # above is intentionally NOT keyed on this — it stays per-run/shared so
            # files persist across the run's agents.
            thread_id=(thread_id or ctx.run_id),
            interrupt_on=interrupt_on,
            exclude_builtin_tools=exclude_builtin_tools,
        )

    return _select_runtime(agent_id, _build_deepagents_runner)


# Default runtime id — the only one registered today (INV-13). A manifest/agent could
# select a future runtime by name; absent that, every agent runs on deepagents.
_DEFAULT_RUNTIME = "langchain_deepagents"


def _select_runtime(agent_id: str, build: Callable[[], object]) -> object:
    """Resolve the ``AgentRuntimeAdapter`` and delegate runner construction (F5 / 08-05).

    Builds a ``RuntimeBuildContext`` carrying the bound ``build`` seam, resolves
    ``resolve("runtime", _DEFAULT_RUNTIME)``, and asks the adapter to ``create`` the
    runner. The adapter invokes ``build`` (the app-side construction the factory
    prepared) — it never imports ``app``/``create_deep_agent`` itself, so the INV-13
    allow-list + import-linter stay green while runtime selection becomes a declared,
    registry-resolved capability (future runtimes slot in with no kernel edit).
    """
    from agents.capabilities.registry import CapabilityRegistry, discover

    discover()  # ensure the runtime adapter is bound (idempotent)
    adapter = CapabilityRegistry().resolve("runtime", _DEFAULT_RUNTIME)
    return adapter.create(agent_id, RuntimeBuildContext(agent_id=agent_id, build=build))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compose_system_prompt(spec, ctx: AgentContext) -> str:
    """Compose the system prompt via the registered ``PromptAssemblyPolicy`` (08-05 / F1/F3).

    Builds a named-block mapping and delegates block ORDER + join to the
    registry-resolved ``PromptAssemblyPolicy`` (``resolve("prompt", "default")``,
    default order ``injects → guardrails → skills → hooks → constitution →
    prompt_body``, ``"\\n\\n"`` join). The hardcoded inline block-append order (F1)
    and the inline skills/hooks injection (F3) are DELETED — the SKILLS block now comes
    from the ``skill_provider`` (``ui``, versioned — SKILL-01) and the HOOKS block from
    the ``hook_provider`` (``behavioral`` non-executable sub-type, which still renders the
    ``## Active Behavioral Hooks`` block). Composition is byte-identical to the pre-lift
    inline path for every existing agent (the 5 characterization snapshots gate it; NEVER
    re-baseline).

    The ``constitution`` slot keeps the factory's existing ``_inject_constitution`` output
    (F4 is 08-06's deletion — untouched here). Missing guardrail files produce a warning
    and contribute no block (agent still runs).
    """
    from agents.capabilities.hooks.behavioral import render_behavioral_block
    from agents.capabilities.registry import CapabilityRegistry, discover
    from agents.capabilities.skills.providers import extract_ui_skill_blocks

    blocks: dict[str, object] = {}

    # 0. Injection content (od_prototype / od_ppt agents)
    injects = getattr(spec, "injects", []) or []
    if injects:
        injection_block = _compose_injection(spec, ctx, injects)
        if injection_block:
            blocks["injects"] = injection_block

    # 1. Guardrails (each preceded by ## Guardrail: {name})
    guardrail_items: list[str] = []
    for guardrail_name in spec.guardrails:
        guardrail_file = _GUARDRAILS_DIR / f"{guardrail_name}.md"
        if not guardrail_file.exists():
            logger.warning(
                "Guardrail file not found: %s — skipping",
                guardrail_file,
            )
            content = ""
        else:
            try:
                content = guardrail_file.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning(
                    "Could not read guardrail file %s: %s — skipping",
                    guardrail_file,
                    exc,
                )
                content = ""

        if content:
            guardrail_items.append(f"## Guardrail: {guardrail_name}\n\n{content}")
    if guardrail_items:
        blocks["guardrails"] = guardrail_items

    # 2. Skills — via the ``ui`` skill_provider (versioned blocks; SKILL-01). The
    # factory consumes the versioned blocks' ``content`` for the prompt slot.
    skill_blocks = extract_ui_skill_blocks(ctx.attached_skills)
    skill_contents = [b.content for b in skill_blocks if b.content]
    if skill_contents:
        blocks["skills"] = skill_contents

    # 3. Hooks — via the ``behavioral`` hook_provider (the legacy prompt-only hook
    # survives as a non-executable sub-type; the ## Active Behavioral Hooks block render).
    hook_block = render_behavioral_block(ctx.attached_hooks)
    if hook_block:
        blocks["hooks"] = hook_block

    # 4. Constitution guardrail (F4 untouched — 08-06 owns its deletion).
    constitution = _inject_constitution(ctx)
    if constitution:
        blocks["constitution"] = constitution

    # 5. Prompt body (always present)
    blocks["prompt_body"] = spec.prompt_body

    discover()  # ensure the prompt policy is bound (idempotent)
    policy = CapabilityRegistry().resolve("prompt", "default")
    return policy.assemble(blocks, ctx)


def _inject_constitution(ctx: AgentContext) -> str:
    """Inject the per-user Constitution as a guardrail (FR-012 / T068).

    Retrieves the Constitution from Workflow_Memory and injects it into
    every governed agent's system prompt as a guardrail.
    Per-Workflow Constitution (ctx.planning_context.constitution_ref) overrides
    per-user Constitution.

    Returns empty string if no Constitution is set (graceful no-op).
    """
    # ── Sync-safe path (AGENTRT-06 / F4 / R12): the async engine pre-warms the owner's ──
    # Constitution ONCE at run entry and stashes it on ``ctx.prewarmed_constitution`` so
    # the factory (SYNC, called from the async engine under a RUNNING event loop) reads it
    # WITHOUT awaiting. This is the single sync-safe read; it injects a DB-stored
    # Constitution in production where the old ``_mem``-only running-loop branch silently
    # dropped it. None ⇒ no Constitution set (graceful no-op; the characterization runs
    # carry none, so snapshots stay byte-identical).
    prewarmed = getattr(ctx, "prewarmed_constitution", None)
    if prewarmed:
        constitution = prewarmed
    else:
        user_id = getattr(ctx, "user_id", None) or (
            # Extract user_id from planning_context if available
            (ctx.planning_context or {}).get("session_id") if ctx.planning_context else None
        )
        if not user_id:
            return ""

        try:
            import asyncio
            from agents.workflow_memory.memory import get_workflow_memory

            memory = get_workflow_memory()
            # Run the async get_constitution in the current event loop if available,
            # otherwise fall back to a new loop (factory is called from sync context).
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're inside an async context — schedule as a task and return empty
                    # (the constitution will be injected on the next call once cached).
                    # For now, use a thread-safe synchronous fallback via the in-memory store.
                    constitution = memory._mem.get(user_id, {}).get("constitution")
                else:
                    constitution = loop.run_until_complete(memory.get_constitution(user_id))
            except RuntimeError:
                constitution = None

            if not constitution:
                return ""
        except Exception as exc:
            logger.warning("_inject_constitution failed: %s", exc)
            return ""

    return (
        "## Constitution (Governing Principles — Supreme Authority)\n\n"
        f"{constitution}\n\n"
        "## End Constitution\n\n"
        "The above Constitution governs all your outputs. Any finding that "
        "conflicts with these principles is CRITICAL."
    )


def _compose_injection(spec, ctx: AgentContext, injects: list[str]) -> str:
    """Compose the injection block for an agent declaring `injects`.

    Mirrors od_runner._compose_system_prompt section order:
      critical rules → design system → craft rules → template skill body

    The role prompt (spec.prompt_body) is appended separately by the caller.

    Reads loaded content from ctx.od_context, which must contain:
      template_body, ds_id, ds_body, craft_block, template_id,
      is_design_system_required (deck conditional)

    Raises:
        TemplateMissingError: if `template` is declared but od_context lacks
                              a template_body — the engine halts before any
                              agent executes.
    """
    od = ctx.od_context or {}
    sections: list[str] = []

    # Validate template availability up front
    if "template" in injects and not od.get("template_body"):
        raise TemplateMissingError(
            f"Agent '{spec.id}' declares injects=['template', ...] but no template "
            f"body was loaded (od_context missing 'template_body'). Cannot compose "
            f"system prompt — halting before execution."
        )

    # 0. CRITICAL OUTPUT RULES — always present when any injection is declared
    sections.append(
        "═══════════════════════════════════════════════════════════\n"
        "CRITICAL OUTPUT RULES — READ BEFORE ANYTHING ELSE\n"
        "═══════════════════════════════════════════════════════════\n\n"
        "1. OUTPUT FORMAT: Emit ONE complete HTML file inside <artifact>...</artifact> tags.\n"
        "2. NAVIGATION: Every page must have a routed section; populate the routes map.\n"
        "3. CONTENT QUALITY: No placeholder text. Domain-specific, plausible content only.\n"
        "4. DESIGN TOKENS: Use ONLY :root CSS variables from the ACTIVE DESIGN SYSTEM.\n"
        "5. SELF-CHECK: Verify every interactive element is wired before emitting.\n"
    )

    # 1. DESIGN.md — for od_ppt this is conditional on is_design_system_required
    if "design_system" in injects and od.get("ds_body"):
        is_deck_conditional = od.get("is_design_system_required")
        include_ds = True if is_deck_conditional is None else bool(is_deck_conditional)
        if include_ds:
            sections.append(
                f"═══════════════════════════════════════════════════════════\n"
                f"ACTIVE DESIGN SYSTEM: {od.get('ds_id', 'custom')}\n"
                f"All color, font, and spacing values MUST come from the tokens below.\n"
                f"═══════════════════════════════════════════════════════════\n\n"
                f"{od['ds_body']}"
            )

    # 2. Craft rules
    if "craft" in injects and od.get("craft_block"):
        sections.append(
            f"═══════════════════════════════════════════════════════════\n"
            f"CRAFT RULES (required by this template)\n"
            f"═══════════════════════════════════════════════════════════\n\n"
            f"{od['craft_block']}"
        )

    # 3. SKILL.md body — the template's workflow
    if "template" in injects and od.get("template_body"):
        sections.append(
            f"═══════════════════════════════════════════════════════════\n"
            f"ACTIVE TEMPLATE SKILL: {od.get('template_id', '')}\n"
            f"The Workflow section below is your primary instruction.\n"
            f"═══════════════════════════════════════════════════════════\n\n"
            f"{od['template_body']}"
        )

    return "\n\n---\n\n".join(sections)


def _resolve_custom_tool_keys(keys: list[str]) -> list:
    """Map provider-emitted custom-tool KEYS → concrete tool objects (08-03 / F2).

    The kernel-side ``tool_provider`` capabilities (``agents/capabilities/tools/``)
    emit stable string keys, NOT concrete tool objects, so the capability package
    stays import-clean of ``app.*`` (import-linter: ``agents.capabilities`` ↛ ``app``).
    The factory IS the composition root (it may import ``app``), so it resolves each
    key to its concrete tool here:

      * ``"report_task_complete"`` → the store-free runner tool (one tool).
      * ``"planning"``             → the whole ``PLANNING_TOOLS`` set (a list).

    De-dups ``report_task_complete`` (in case both prototype set names co-occur),
    preserving the byte-identical custom-tool list the deleted switch produced.

    Raises:
        ValueError: if a key has no concrete resolver (a provider/factory drift).
    """
    # Lazy imports keep the factory import light (the heavy stack loads only on bind).
    from agents.planner.tools import PLANNING_TOOLS
    from app.agents.tools.runner_tools import report_task_complete

    resolved: list = []
    for key in keys:
        if key == "report_task_complete":
            if report_task_complete not in resolved:
                resolved.append(report_task_complete)
        elif key == "planning":
            resolved.extend(PLANNING_TOOLS)
        else:
            raise ValueError(
                f"unknown custom-tool key '{key}' emitted by a tool_provider; "
                f"no concrete resolver in the factory"
            )
    return resolved


def _resolve_runner_tools(spec, ctx: AgentContext) -> tuple[list, bool]:
    """Resolve spec.tools to the (custom_tools, exclude_builtin_tools) pair via the
    ``tool_provider`` registry (08-03 / F2 — replaces the closed switch, INV-12).

    Each declared tool-set name in ``spec.tools`` resolves to a registered
    ``ToolProvider`` (``agents/capabilities/tools/``); the provider returns
    ``(custom_tool_keys, exclude_builtin)`` for its set, and the factory maps the
    keys → concrete tools (``_resolve_custom_tool_keys``) and UNIONS the granted
    sets. This binds byte-identical tool sets to what the deleted switch produced
    (parity — ``test_create_runner.py`` + the 5 characterization snapshots gate it).

    Grant-driven (D-07 / INV-9): only tool sets whose effective ``ToolPermissions``
    permit them bind. The four existing sets all bind under the default
    ``read_files``-only posture (none requires write/exec), so parity holds; a future
    privileged set would be gated by the effective grant before resolution.

    ``exclude_builtin`` is the AND of every granted set's flag (a set that needs the
    native fs flips it ``False``); an empty ``spec.tools`` ⇒ pure-text agent
    (``([], True)``) — no provider to resolve.

    Returns:
        (custom_tools, exclude_builtin_tools)

    Raises:
        KeyError: if spec.tools names a tool set with no registered provider
            (the registry raises naming the unknown ``(kind, name)``).
    """
    from agents.capabilities.registry import CapabilityRegistry, discover

    # Empty tool set ⇒ pure-text agent: no custom tools, hide all native tools.
    if not spec.tools:
        return ([], True)

    discover()  # ensure the tool_provider impls are bound (idempotent)
    registry = CapabilityRegistry()

    custom_keys: list[str] = []
    exclude = True  # AND-accumulator: a set needing native fs flips it False

    for set_name in spec.tools:
        provider = registry.resolve("tool", set_name)
        keys, set_exclude = provider.provide(spec, ctx)
        for key in keys:
            if key not in custom_keys:
                custom_keys.append(key)
        # Mirror the deleted switch's exclude semantics: workspace/prototype set
        # exclude=False (native fs); planning leaves it True. The union excludes the
        # builtin tools only if EVERY granted set excludes them (AND).
        exclude = exclude and set_exclude

    return (_resolve_custom_tool_keys(custom_keys), exclude)
