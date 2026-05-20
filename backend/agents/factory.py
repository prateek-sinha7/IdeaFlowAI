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
        # Workspace agents write many files — cap iterations to avoid runaway loops.
        # Text-only agents (tools=[]) complete in 1 iteration anyway.
        max_iterations=10 if tools else 1,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compose_system_prompt(spec, ctx: AgentContext) -> str:
    """Compose the system prompt by concatenating in order:

    1. Guardrail content blocks (each preceded by ## Guardrail: {name})
    2. Skill content blocks from ctx.attached_skills
    3. Hook guideline blocks from ctx.attached_hooks
    4. spec.prompt_body

    All blocks are joined with double newlines.
    Missing guardrail files produce a warning and an empty block (agent still runs).
    """
    blocks: list[str] = []

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

    # 3. Hooks
    for hook in ctx.attached_hooks:
        content = hook.get("content", "")
        if content:
            blocks.append(content)

    # 4. Prompt body
    blocks.append(spec.prompt_body)

    return "\n\n".join(blocks)


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
    from app.agents.tools.prototype import make_prototype_tools, ArtifactStore

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
            artifact_store = ArtifactStore()
            tools.extend(make_prototype_tools("mobile", artifact_store))
        else:
            raise ValueError(
                f"Unrecognized tool name '{tool_name}' in agent '{spec.id}'. "
                f"Supported tool sets: 'workspace', 'prototype'."
            )

    return tools
