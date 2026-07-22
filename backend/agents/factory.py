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
    # prewarmed_mcp_tools: the MCP/integration tools bound at the async engine
    # run-entry (the SAME seam as prewarmed_constitution) and stashed here so the
    # SYNC factory UNIONS them into the runner tool set WITHOUT awaiting inside the
    # running loop (09-05 / MCP-01 — the async→sync binding resolution, R-D). The
    # McpClientAdapter awaits get_tools() ONCE at run-entry; the factory only reads.
    # Empty ⇒ no MCP scope active (graceful no-op; the characterization runs carry
    # none → snapshots byte-identical, exactly like the Constitution no-op). These
    # tools AUGMENT the deepagents runtime, they never replace it (INV-13).
    prewarmed_mcp_tools: list = field(default_factory=list)
    # step_injects (WIRE-03 / D-16): the compiled ``Step.injects`` for THIS agent's
    # step, threaded off ``ectx.current_step`` by the engine. Merged order-stably with
    # the AGENT.md-derived ``spec.injects`` at the injection seam in
    # ``_compose_system_prompt`` (generic, keyed on this list — NO workflow/agent-name
    # branch, SC-001). Empty for every step that declares no per-step ``injects:`` (all
    # 5 characterization goldens) → the merge is a provable no-op → byte-identical (INV-3).
    step_injects: list[str] = field(default_factory=list)


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
    run_sandbox=None,
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
        run_sandbox: Optional RunSandbox-shaped sandbox OVERRIDE (Phase 11 /
            FANOUT-05 / CR-02). When provided (a fan-out worker's engine-allocated
            isolated workspace sandbox — the ``_ChildSandbox`` root), the runner's
            deepagents FilesystemBackend is rooted at IT instead of the shared
            per-run dir, so the worker's writes land isolated (two parallel
            workers writing the same relpath cannot cross-contaminate before the
            merge). ``None`` (every non-worker invocation) keeps the per-run
            shared sandbox byte-identical (parity).

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
    # Tools are resolved BEFORE prompt composition (13-02 / F4): the composed
    # prompt needs to know whether the agent has literally zero callable tools
    # so the anti-fabrication ``tool_availability`` preamble can be injected.
    custom_tools, exclude_builtin_tools = _resolve_runner_tools(spec, ctx)
    # ``no_tools`` is True ONLY for pure text-only agents (tools:[] with no
    # MCP tools pre-warmed): exclude_builtin AND zero custom tools. Workspace/
    # prototype agents flip exclude_builtin False; planning agents carry
    # PLANNING_TOOLS; MCP-bound agents flip exclude_builtin False — none of
    # those receive the preamble (their prompts stay byte-identical).
    no_tools = exclude_builtin_tools and not custom_tools
    # Compose the system prompt — guardrails/skills/hooks/constitution/injection/
    # body, in the fixed injection order (see ``_compose_system_prompt``).
    system_prompt = _compose_system_prompt(spec, ctx, no_tools=no_tools)

    # Per-run on-disk sandbox: <RUNS_ROOT>/<user>/<run>/. SHARED across every
    # agent in the pipeline run, so files (prototype.html, code-gen outputs)
    # written by one agent persist for the next — hence keyed on ctx.run_id
    # ONLY (NOT on the per-agent ``thread_id``). The runner roots its deepagents
    # FilesystemBackend at ``sandbox.root`` (traversal-proof).
    #   - Missing user_id ⇒ "anon" (RunSandbox additionally sanitises empty/
    #     unsafe segments to its own "anonymous"/"run" fallbacks).
    #   - Missing run_id ⇒ "adhoc": gives an isolated, deterministic dir for the
    #     (engine-less) no-run-id case.
    if run_sandbox is not None:
        # Phase 11 / FANOUT-05 (CR-02): a fan-out worker's engine-allocated
        # ISOLATED sandbox overrides the shared per-run dir for THIS invocation.
        sandbox = run_sandbox
    else:
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


# F4 (13-02): anti-fabrication preamble for agents with ZERO callable tools.
# Live Haiku fabricates Claude-internal tool syntax (<function_calls>/<invoke>/
# write_todos XML) as plain text when the composed prompt implies file/tool
# actions without bound tools. This terse, engineer-authored block (no
# interpolated user input — T-13-02-03) frames the whole prompt via the
# ``tool_availability`` slot, FIRST in the default assembly order.
_NO_TOOLS_PREAMBLE = """## Tool Availability

You have NO tools in this session. You must NEVER emit tool-call syntax of any
kind — no <function_calls>, no <invoke>, no write_todos, read_file, write_file,
edit_file, or to-do blocks. Any file content you produce must appear directly
in your response as plain text. Respond with prose or structured text only."""


def _compose_system_prompt(spec, ctx: AgentContext, *, no_tools: bool = False) -> str:
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

    # -1. Tool-availability preamble (F4 / 13-02) — ONLY when the agent resolved
    # to literally zero callable tools (text-only). The slot is FIRST in the
    # default order so the constraint frames everything that follows. Tool-having
    # agents never carry the key, so their composition stays byte-identical.
    if no_tools:
        blocks["tool_availability"] = _NO_TOOLS_PREAMBLE

    # 0. Injection content (od_prototype / od_ppt agents)
    # WIRE-03 / D-16: merge the AGENT.md-derived spec.injects (the live source) with
    # the compiled per-step Step.injects (ctx.step_injects), order-stable and
    # de-duplicated. The merge keys on the GENERIC step_injects list — NO workflow/
    # agent-name branch (SC-001). When ctx.step_injects == [] (every step that
    # declares no per-step injects:, incl. all 5 goldens) this returns exactly
    # spec.injects → identical _compose_injection input → byte-identical prompt (INV-3).
    spec_injects = getattr(spec, "injects", []) or []
    step_injects = getattr(ctx, "step_injects", []) or []
    injects = list(spec_injects) + [
        i for i in step_injects if i not in spec_injects
    ]
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
        hook_names = [h.get("name", h.get("id", "?")) for h in ctx.attached_hooks]
        logger.debug(
            "_compose_system_prompt: %d hook(s) injected into agent=%s — %s",
            len(ctx.attached_hooks), spec.id, ", ".join(hook_names),
        )
    else:
        logger.debug(
            "_compose_system_prompt: no hooks attached for agent=%s", spec.id
        )

    # 4. Constitution guardrail (F4 untouched — 08-06 owns its deletion).
    constitution = _inject_constitution(ctx)
    if constitution:
        blocks["constitution"] = constitution

    # 5. Prompt body — use the user's saved override if present, else the
    # canonical AGENT.md body (KAN-76). The import is lazy to keep factory.py
    # import-light; the override module is app-layer (allowed here — factory is
    # the composition root). Falls back to spec.prompt_body when user_id is
    # absent (e.g. tests, anonymous runs) so all 5 characterization goldens
    # remain byte-identical (INV-3).
    prompt_body = spec.prompt_body
    user_id = getattr(ctx, "user_id", None)
    if user_id:
        try:
            from app.agents.prompt_overrides import read_user_prompt_override
            override = read_user_prompt_override(spec.id, user_id=user_id)
            if override:
                logger.debug(
                    "_compose_system_prompt: applying user prompt override for agent=%s user=%s",
                    spec.id, user_id,
                )
                prompt_body = override
        except Exception as exc:  # noqa: BLE001 — never let an override lookup crash a run
            logger.warning(
                "_compose_system_prompt: prompt override lookup failed for agent=%s: %s — using base prompt",
                spec.id, exc,
            )
    blocks["prompt_body"] = prompt_body

    discover()  # ensure the prompt policy is bound (idempotent)
    policy = CapabilityRegistry().resolve("prompt", "default")
    return policy.assemble(blocks, ctx)


def _inject_constitution(ctx: AgentContext) -> str:
    """Inject the per-user Constitution as a guardrail (FR-012 / T068).

    Retrieves the Constitution from Workflow_Memory and injects it into
    every governed agent's system prompt as a guardrail.
    Per-Workflow Constitution (ctx.planning_context.constitution_ref) overrides
    per-user Constitution.

    The Constitution is awaited ONCE at the async engine run entry and threaded in
    as ``ctx.prewarmed_constitution`` so this SYNC factory (called from the async engine
    under a RUNNING event loop) reads it WITHOUT awaiting — the single sync-safe path
    (AGENTRT-06 / F4 / R12). A DB-stored Constitution is therefore injected in production
    where the deleted ``_mem``-only running-loop branch silently dropped it. Returns the
    empty string when no Constitution is pre-warmed (graceful no-op; the characterization
    runs carry none → snapshots byte-identical).
    """
    constitution = getattr(ctx, "prewarmed_constitution", None)
    if not constitution:
        return ""

    return (
        "## Constitution (Governing Principles — Supreme Authority)\n\n"
        f"{constitution}\n\n"
        "## End Constitution\n\n"
        "The above Constitution governs all your outputs. Any finding that "
        "conflicts with these principles is CRITICAL."
    )


def _compose_injection_no_template(spec, od: dict, injects: list[str], sections: list) -> str:
    """KAN-87: compose injection block when no template was selected.

    Injects the design system tokens + a concrete "blank canvas" scaffold that
    gives agents the same structural foundation as a TEMPLATE SEED — without
    forcing any visual style. Agents have full creative latitude to build any
    layout they choose, but the scaffold ensures:
      - A working CSS class system (they can extend or replace it)
      - The correct router pattern
      - A clear statement that template constraints don't apply

    This is intentionally generous — agents should produce rich, creative,
    fully-interactive prototypes, not minimal skeletons.
    """
    ds_body = od.get("ds_body")
    ds_id = od.get("ds_id", "custom") or "custom"

    # 1. Design system tokens
    if "design_system" in injects and ds_body:
        sections.append(
            f"═══════════════════════════════════════════════════════════\n"
            f"ACTIVE DESIGN SYSTEM: {ds_id}\n"
            f"Map ALL color, font, and spacing values from these tokens.\n"
            f"Map to :root variables: --bg, --fg, --accent, --surface, --border, --muted.\n"
            f"═══════════════════════════════════════════════════════════\n\n"
            f"{ds_body}"
        )

    # 2. Blank canvas scaffold — gives agents a full starting point
    sections.append(
        """═══════════════════════════════════════════════════════════
BLANK CANVAS MODE — Full Creative Freedom
═══════════════════════════════════════════════════════════

The user chose NOT to use a pre-made template. You have FULL CREATIVE FREEDOM
to design the visual layout, CSS class system, and HTML structure from scratch.

There are NO template constraints. Design the best possible prototype for the
user's brief — rich, interactive, fully populated with real data.

## Starter CSS Scaffold (use, extend, or replace freely)

The following is a STARTING POINT only — a minimal working class system.
You are free to add any classes, layouts, or visual elements you need.
The spec writer will define the actual class system in spec.md — read that
first and implement whatever class system the spec defines.

```css
/* ── Blank Canvas Starter — extend freely ── */
:root {
  /* Map from ACTIVE DESIGN SYSTEM above */
  --bg: #f8f9fa;
  --fg: #111827;
  --accent: #2563eb;
  --surface: #ffffff;
  --border: #e5e7eb;
  --muted: #6b7280;
  --font-display: system-ui, sans-serif;
  --font-body: system-ui, sans-serif;
  --font-mono: 'Courier New', monospace;
  --radius: 8px;
  --shadow: 0 1px 3px rgba(0,0,0,.1);
  --sidebar-w: 240px;
}

/* Page sections — shown/hidden by JS router */
.page { display: none; width: 100%; min-height: 100vh; }
.page.is-active { display: block; }

/* Layout primitives */
.container { max-width: 1200px; margin: 0 auto; padding: 0 24px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
.grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }
.grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; }

/* Cards */
.card { background: var(--surface); border: 1px solid var(--border);
        border-radius: var(--radius); padding: 24px; box-shadow: var(--shadow); }
.card-header { font-size: 13px; font-weight: 600; color: var(--muted);
               text-transform: uppercase; letter-spacing: .04em; margin-bottom: 8px; }
.card-value { font-size: 28px; font-weight: 700; color: var(--fg); }

/* Navigation chrome */
.topbar { position: sticky; top: 0; background: var(--surface);
          border-bottom: 1px solid var(--border); z-index: 100;
          display: flex; align-items: center; padding: 0 24px; height: 60px; gap: 32px; }
.topbar .logo { font-weight: 700; font-size: 18px; color: var(--fg); text-decoration: none; }
.nav-link { color: var(--muted); text-decoration: none; font-size: 14px;
            padding: 6px 10px; border-radius: 6px; transition: all .15s; }
.nav-link:hover, .nav-link.active { color: var(--fg); background: rgba(0,0,0,.05); }

/* Sidebar (optional — use if the layout calls for it) */
.sidebar { position: fixed; left: 0; top: 60px; width: var(--sidebar-w);
           height: calc(100vh - 60px); background: var(--surface);
           border-right: 1px solid var(--border); overflow-y: auto; padding: 16px 0; }
.sidebar .nav-link { display: block; padding: 10px 20px; border-radius: 0; width: 100%; }
.sidebar .nav-link.active { background: rgba(37,99,235,.08); color: var(--accent);
                             border-left: 3px solid var(--accent); }
.main-with-sidebar { margin-left: var(--sidebar-w); padding: 32px 40px; }

/* Buttons */
.btn { display: inline-flex; align-items: center; gap: 8px; padding: 8px 16px;
       border-radius: var(--radius); border: none; cursor: pointer; font-size: 14px;
       font-weight: 500; transition: all .15s; }
.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:hover { opacity: .9; }
.btn-secondary { background: var(--surface); color: var(--fg);
                 border: 1px solid var(--border); }
.btn-secondary:hover { background: var(--bg); }
.btn-sm { padding: 5px 10px; font-size: 13px; }
.btn-danger { background: #dc2626; color: #fff; }

/* Tables */
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 16px; font-size: 12px; font-weight: 600;
            color: var(--muted); text-transform: uppercase; letter-spacing: .04em;
            border-bottom: 2px solid var(--border); }
.table td { padding: 12px 16px; border-bottom: 1px solid var(--border);
            font-size: 14px; color: var(--fg); }
.table tr:hover td { background: rgba(0,0,0,.02); }
.table-wrap { background: var(--surface); border: 1px solid var(--border);
              border-radius: var(--radius); overflow: hidden; }

/* Badges / status pills */
.badge { display: inline-flex; align-items: center; padding: 3px 10px;
         border-radius: 100px; font-size: 12px; font-weight: 500; }
.badge-green  { background: #dcfce7; color: #15803d; }
.badge-red    { background: #fee2e2; color: #b91c1c; }
.badge-yellow { background: #fef9c3; color: #854d0e; }
.badge-blue   { background: #dbeafe; color: #1d4ed8; }
.badge-gray   { background: #f3f4f6; color: #374151; }

/* Forms */
.form-group { margin-bottom: 20px; }
.form-label { display: block; font-size: 13px; font-weight: 500;
              color: var(--fg); margin-bottom: 6px; }
.form-input { width: 100%; padding: 9px 12px; border: 1px solid var(--border);
              border-radius: var(--radius); font-size: 14px; color: var(--fg);
              background: var(--surface); outline: none;
              transition: border-color .15s; box-sizing: border-box; }
.form-input:focus { border-color: var(--accent); }
.form-select { appearance: none; background-image:
  url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%236b7280' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 12px center; }

/* Charts (pure CSS / SVG) */
.chart-wrap { background: var(--surface); border: 1px solid var(--border);
              border-radius: var(--radius); padding: 24px; }
.chart-title { font-size: 14px; font-weight: 600; color: var(--fg); margin-bottom: 16px; }
.bar-chart { display: flex; align-items: flex-end; gap: 8px; height: 160px; }
.bar { flex: 1; background: var(--accent); border-radius: 4px 4px 0 0;
       opacity: .85; transition: opacity .15s; cursor: pointer; position: relative; }
.bar:hover { opacity: 1; }
.bar-label { position: absolute; bottom: -22px; left: 50%; transform: translateX(-50%);
             font-size: 11px; color: var(--muted); white-space: nowrap; }

/* Page header */
.page-header { padding: 32px 0 24px; border-bottom: 1px solid var(--border);
               margin-bottom: 32px; }
.page-title { font-size: 24px; font-weight: 700; color: var(--fg); }
.page-subtitle { font-size: 14px; color: var(--muted); margin-top: 4px; }

/* Utilities */
.flex { display: flex; }
.items-center { align-items: center; }
.justify-between { justify-content: space-between; }
.gap-8 { gap: 8px; }
.gap-16 { gap: 16px; }
.mt-24 { margin-top: 24px; }
.mb-24 { margin-bottom: 24px; }
.text-sm { font-size: 13px; }
.text-muted { color: var(--muted); }
.font-bold { font-weight: 700; }
```

## Router Pattern (MANDATORY — copy verbatim)

```javascript
function navigateTo(pageId) {
  window.location.hash = '#/' + pageId;
}

function handleRouteChange() {
  const hash = window.location.hash.replace(/^#\\/?/, '') || 'FIRST_PAGE_ID';
  // ALWAYS use section[data-page] — never [data-page] alone
  document.querySelectorAll('section[data-page]').forEach(s => s.classList.remove('is-active'));
  const page = document.querySelector('section[data-page="' + hash + '"]');
  if (page) page.classList.add('is-active');
  document.querySelectorAll('a.nav-link').forEach(a => a.classList.remove('active'));
  document.querySelectorAll('a.nav-link[href="#/' + hash + '"]').forEach(a => a.classList.add('active'));
}
window.addEventListener('hashchange', handleRouteChange);
window.addEventListener('load', handleRouteChange);
```

Replace `FIRST_PAGE_ID` with the actual first page ID.
`data-page` goes ONLY on `<section>` elements — NEVER on `<a>` tags.

## Creative guidelines

- **Full creative freedom**: design the visual layout that best fits the brief
- **Rich content**: every page must have real data, tables with 5+ rows, charts, forms
- **Beautiful UI**: use the design system colours, clean typography, consistent spacing
- **Interactive**: every button/link wired, modals, state changes all work
- **Read spec.md first** — the spec writer has defined the exact class system to implement
═══════════════════════════════════════════════════════════"""
    )
    return "\n\n".join(s for s in sections if s)


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

    # Validate template availability up front — but only hard-fail for od_*
    # pipelines that are specifically supposed to inject a template. For custom
    # workflows that happen to include template-declaring agents (e.g. prototype
    # agents), silently skip the template block rather than aborting the run.
    has_template = bool(od.get("template_body"))
    if "template" in injects and not has_template:
        # If od_context is completely absent, this is a custom run — just skip
        # all injection (there's nothing to inject).
        if not od:
            return ""
        # KAN-87: no-template mode — the user explicitly chose not to select a
        # template. od_context has no_template=True. Skip template injection
        # silently; the agent's AGENT.md has instructions for this case.
        if od.get("no_template"):
            return _compose_injection_no_template(spec, od, injects, sections)
        # od_context is present but template_body is missing — this is a real
        # configuration error for an od_* pipeline (template was expected).
        raise TemplateMissingError(
            f"Agent '{spec.id}' declares injects=['template', ...] but no template "
            f"body was loaded (od_context missing 'template_body'). Cannot compose "
            f"system prompt — halting before execution."
        )

    # 0. CRITICAL OUTPUT RULES — deliberately removed (FIX-017 / 2026-06-17).
    # This block was prototype-specific: rule 2 ("routed sections") and rule 5
    # ("every interactive element") describe a single-page app navigation pattern
    # that CONTRADICTS the PPT composer's deck output contract (slides use
    # <section class="slide">, not data-page routing). All injects-declaring agents
    # carry their own complete output contracts in their AGENT.md bodies — the
    # injection block only needs to provide OD content (DS, craft, SKILL.md).

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
    from app.agents.tools.runner_tools import report_task_complete, spawn_subagents

    resolved: list = []
    for key in keys:
        if key == "report_task_complete":
            if report_task_complete not in resolved:
                resolved.append(report_task_complete)
        elif key == "planning":
            resolved.extend(PLANNING_TOOLS)
        elif key == "spawn_subagents":
            # Phase 11 / FANOUT-01: the store-free / spawn-free fan-out request emitter.
            # Only binds when the step DECLARES the spawn_subagents tool set (user_allowed
            # =False at the registry, so a user/db manifest can never grant it — CAP-03).
            if spawn_subagents not in resolved:
                resolved.append(spawn_subagents)
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

    Grant model (D-07 / INV-9) — FORWARD SURFACE, not yet enforced here: the D-07
    design is that only tool sets whose effective ``ToolPermissions`` permit them
    should bind. This function does NOT yet read ``step.tools`` / intersect any
    ``ToolPermissions`` — it resolves every named provider unconditionally. That is
    SAFE this phase because none of the four registered sets is write/exec-privileged
    (all bind under the default ``read_files``-only posture), so there is nothing to
    gate. The grant-driven binding check (skip/deny a set whose required permission is
    not granted) is the tool-binding enforcement POINT that lands when the first
    privileged tool set is introduced (Phase 9+, alongside the LocalSandboxRuntime).
    Until then this is the resolution seam only — do NOT cite it as an active
    permission enforcement point.

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

    # Pre-warmed MCP/integration tools (09-05 / MCP-01): bound at the async engine
    # run-entry and stashed on ctx.prewarmed_mcp_tools. The SYNC factory only READS
    # them here and UNIONS them into custom_tools — NO await and NO re-entrant event
    # loop inside the running loop (Pitfall 3 double-loop). They are already-instantiated
    # LangChain BaseTools, so they bypass the key→impl resolution (which is for the
    # registered tool_provider keys). Empty ⇒ no MCP scope active (graceful no-op).
    mcp_tools = list(getattr(ctx, "prewarmed_mcp_tools", None) or [])

    # Empty tool set ⇒ pure-text agent EXCEPT when MCP tools are pre-warmed: those
    # must still bind (and they need the native tool surface available, so the agent
    # can actually call them — flip exclude_builtin off when any MCP tool is bound).
    if not spec.tools:
        if mcp_tools:
            return (mcp_tools, False)
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

    resolved = _resolve_custom_tool_keys(custom_keys)
    # Union the pre-warmed MCP tools after the registered keys (a pre-bound MCP tool
    # needs the native fs surface, so it flips exclude off too — INV-13 augment).
    if mcp_tools:
        resolved = list(resolved) + mcp_tools
        exclude = False
    return (resolved, exclude)
