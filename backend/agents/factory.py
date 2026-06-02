"""agents/factory.py — composes system prompts and instantiates DeepAgent.

Public API:
    create_agent(agent_id: str, ctx: AgentContext) -> DeepAgent

AgentContext carries all runtime context needed to compose the system prompt:
  - user_request: the original user message
  - agent_outputs: prior-agent outputs keyed by agent ID (filtered view)
  - attached_skills: UI-attached skills [{name, content, source}]
  - attached_hooks: UI-attached hooks [{name, event, content}]
  - workspace: shared AgentWorkspace for tool-using agents (optional)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.tools.workspace import AgentWorkspace

logger = logging.getLogger(__name__)

# Path to the guardrails directory
_GUARDRAILS_DIR = Path(__file__).resolve().parent / "guardrails"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class AgentContext:
    """Runtime context passed to create_agent().

    Constructed fresh for each agent invocation by the orchestrator.
    The agent_outputs dict is a filtered view — it contains only the
    prior-agent outputs specified by spec.context_from, never the full
    accumulated outputs dict.
    """

    user_request: str                          # Original user message
    agent_outputs: dict[str, str] = field(default_factory=dict)
    attached_skills: list[dict] = field(default_factory=list)
    attached_hooks: list[dict] = field(default_factory=list)
    workspace: "AgentWorkspace | None" = None
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
    # prototype_store: shared ArtifactStore for prototype pipeline agents.
    # All four prototype agents share the same store so emit_artifact() in
    # one agent is readable by the next agent via the accumulated HTML.
    prototype_store: "object | None" = None


class TemplateMissingError(Exception):
    """Raised when an agent declares `injects` but the referenced template
    cannot be located. The ExecutionEngine catches this and halts the Workflow
    before any agent executes."""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def create_agent(agent_id: str, ctx: AgentContext):
    """Instantiate a DeepAgent for the given agent ID and context.

    Raises:
        FileNotFoundError: propagated from loader if agent_id is unknown.
        AgentSpecError: propagated from loader if AGENT.md is malformed.
        ValueError: if spec.tools contains an unrecognized tool name.
    """
    from agents.loader import load_agent_spec
    from app.agents.deep_agent import DeepAgent

    spec = load_agent_spec(agent_id)
    system_prompt = _compose_system_prompt(spec, ctx)
    tools = _build_tools(spec, ctx)

    return DeepAgent(
        system_prompt=system_prompt,
        tools=tools,
        max_tokens=spec.max_tokens,
        # max_iterations per agent type:
        #   - prototype-build: 3 (think → report_task_complete → emit_artifact)
        #   - prototype-validate: 8 (needs to check all pages + fix + emit)
        #   - other tool agents: 10
        #   - text-only agents (tools=[]): 1
        max_iterations=(
            3 if spec.id == "prototype-build"
            else (8 if spec.id == "prototype-validate"
            else (10 if tools else 1))
        ),
        model=ctx.model,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compose_system_prompt(spec, ctx: AgentContext) -> str:
    """Compose the system prompt by concatenating in order:

    0. Injection content (when spec.injects is non-empty) — critical rules,
       design system, craft rules, template skill body (mirrors od_runner.py)
    1. Guardrail content blocks (each preceded by ## Guardrail: {name})
    2. Skill content blocks from ctx.attached_skills
    3. Hook guideline blocks from ctx.attached_hooks
    4. Constitution guardrail (Phase 2: no-op placeholder; Phase 3: from Workflow_Memory)
    5. spec.prompt_body

    All blocks are joined with double newlines.
    Missing guardrail files produce a warning and an empty block (agent still runs).
    """
    blocks: list[str] = []

    # 0. Injection content (od_prototype / od_ppt agents)
    injects = getattr(spec, "injects", []) or []
    if injects:
        injection_block = _compose_injection(spec, ctx, injects)
        if injection_block:
            blocks.append(injection_block)

    # 1. Guardrails
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
            blocks.append(f"## Guardrail: {guardrail_name}\n\n{content}")

    # 2. Skills
    for skill in ctx.attached_skills:
        content = skill.get("content", "")
        if content:
            blocks.append(content)

    # 3. Hooks — convert hook metadata to behavioral guidelines injected into
    # the system prompt. Hooks don't carry a "content" field (they are event-
    # driven behavioral rules, not skill documents), so we synthesize a
    # guideline block from their metadata: name, event, trigger, description.
    if ctx.attached_hooks:
        hook_lines: list[str] = []
        for hook in ctx.attached_hooks:
            name = hook.get("name", "")
            event = hook.get("event", "")
            trigger = hook.get("trigger", "")
            description = hook.get("description", "")
            if name:
                hook_lines.append(f"- **{name}** ({event}): {description or trigger}")
        if hook_lines:
            blocks.append(
                "## Active Behavioral Hooks\n\n"
                "The following behavioral guidelines are active for this run. "
                "Apply them throughout your response:\n\n"
                + "\n".join(hook_lines)
            )

    # 4. Constitution guardrail
    constitution = _inject_constitution(ctx)
    if constitution:
        blocks.append(constitution)

    # 5. Prompt body
    blocks.append(spec.prompt_body)

    return "\n\n".join(blocks)


def _inject_constitution(ctx: AgentContext) -> str:
    """Inject the per-user Constitution as a guardrail (FR-012 / T068).

    Retrieves the Constitution from Workflow_Memory and injects it into
    every governed agent's system prompt as a guardrail.
    Per-Workflow Constitution (ctx.planning_context.constitution_ref) overrides
    per-user Constitution.

    Returns empty string if no Constitution is set (graceful no-op).
    """
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

        return (
            "## Constitution (Governing Principles — Supreme Authority)\n\n"
            f"{constitution}\n\n"
            "## End Constitution\n\n"
            "The above Constitution governs all your outputs. Any finding that "
            "conflicts with these principles is CRITICAL."
        )
    except Exception as exc:
        logger.warning("_inject_constitution failed: %s", exc)
        return ""


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


def _build_tools(spec, ctx: AgentContext) -> list:
    """Resolve spec.tools to a list of LangChain tool objects.

    Supported tool set names:
      "workspace"  → write_file, read_file, list_workspace_files
      "prototype"  → read_template_seed, read_layout_reference,
                     read_checklist, todo_write, emit_artifact

    Raises:
        ValueError: if spec.tools contains an unrecognized tool name.
    """
    from app.agents.tools.workspace import make_workspace_tools

    tools: list = []

    for tool_name in spec.tools:
        if tool_name == "workspace":
            workspace = ctx.workspace
            if workspace is None:
                # Create a transient workspace if none provided
                from app.agents.tools.workspace import AgentWorkspace
                workspace = AgentWorkspace()
            tools.extend(make_workspace_tools(workspace))
        elif tool_name == "prototype":
            from agents.prototype.artifact_store import PrototypeArtifactStore
            from agents.prototype.tools import make_prototype_tools
            # Use the shared prototype_store from ctx if available (so all
            # prototype agents share the same store and emit_artifact() in
            # one agent is readable by the next). Fall back to a fresh store
            # if not set (shouldn't happen in normal pipeline flow).
            if ctx.prototype_store is not None:
                artifact_store = ctx.prototype_store
            else:
                artifact_store = PrototypeArtifactStore()
            # Use the actual selected template ID from od_context, not "mobile"
            template_id = (ctx.od_context or {}).get("template_id") or "web-prototype"
            tools.extend(make_prototype_tools(template_id, artifact_store))
        elif tool_name == "prototype_emit_only":
            # Slim 2-tool set: only emit_artifact + report_task_complete.
            # Used by prototype-build and prototype-validate to reduce tool
            # schema tokens and eliminate wrong-tool calls.
            from agents.prototype.artifact_store import PrototypeArtifactStore
            from agents.prototype.tools import make_prototype_emit_only_tools
            if ctx.prototype_store is not None:
                artifact_store = ctx.prototype_store
            else:
                artifact_store = PrototypeArtifactStore()
            tools.extend(make_prototype_emit_only_tools(artifact_store))
        elif tool_name == "planning":
            from agents.planner.tools import PLANNING_TOOLS
            tools.extend(PLANNING_TOOLS)
        else:
            raise ValueError(
                f"Unrecognized tool name '{tool_name}' in agent '{spec.id}'. "
                f"Supported tool sets: 'workspace', 'prototype', 'planning'."
            )

    return tools
