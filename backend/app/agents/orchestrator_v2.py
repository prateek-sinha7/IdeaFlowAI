"""WorkflowOrchestrator — Central coordinator for all agent workflows.

Replaces PipelineExecutor as the single point of control for:
- Agent selection and ordering (from slim agents/registry.py)
- Context passing between agents (per-agent context_from routing)
- Revision awareness (fetches previous output from DB)
- Streaming WebSocket events
- Error handling and retries

Architecture:
  WorkflowOrchestrator
    ├── WorkflowState (shared state across all agents)
    ├── _resolve_revision_context() — fetches previous output for revisions
    └── execute() — runs agents sequentially, yields WebSocket events

Skill injection, hook injection, and guardrail injection are handled by
factory._compose_system_prompt — the orchestrator only populates AgentContext
and calls create_agent().
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator

from agents.factory import AgentContext, create_agent
from agents.registry import get_pipeline_agents
from app.agents.base import BaseAgent, AgentConfigurationError, TokenUsage, estimate_cost_usd
from app.agents.deep_agent import DeepAgent
from app.agents.skills import get_skill_content
from app.agents.summarizer import summarize_agent_output
from app.agents.tools.workspace import AgentWorkspace

logger = logging.getLogger("app.agents.orchestrator_v2")


# ============================================================
# WORKFLOW STATE — Shared context across all agents in a run
# ============================================================

@dataclass
class WorkflowState:
    """Holds all state for a single workflow execution."""

    # Original user request (stripped of context blocks)
    user_request: str

    # Pipeline type (e.g., "ppt", "user_stories", "ppt_revision")
    pipeline_type: str

    # Base pipeline type (revision types map to their base)
    base_pipeline_type: str

    # Whether this is a revision run
    is_revision: bool

    # For revision runs: the previous output to modify
    previous_output: str = ""

    # Accumulated FULL outputs from each agent: {agent_id: output_text}
    # Used for final pipeline output and DB persistence.
    agent_outputs: dict[str, str] = field(default_factory=dict)

    # Detailed summaries of each agent's output: {agent_id: summary_text}
    # Used as context for downstream agents instead of the full output.
    # Falls back to full output if summarization is skipped or fails.
    agent_summaries: dict[str, str] = field(default_factory=dict)

    # Execution results for persistence
    results: list[dict] = field(default_factory=list)

    # Token usage per agent: {agent_id: TokenUsage}
    agent_token_usage: dict[str, TokenUsage] = field(default_factory=dict)


# ============================================================
# REVISION TYPE MAPPING
# ============================================================

REVISION_BASE_MAP: dict[str, str] = {
    "ppt_revision": "ppt",
    "user_stories_revision": "user_stories",
    "prototype_revision": "prototype",
    "app_builder_revision": "app_builder",
}

# Pipelines that need the previous output fetched from DB
REVISION_TYPES = set(REVISION_BASE_MAP.keys())


# ============================================================
# CONTEXT ROUTING — Build agent_outputs dict from spec.context_from
# ============================================================

def _build_agent_outputs(
    context_from: list[str],
    agent_index: int,
    agents: list,
    accumulated_outputs: dict[str, str],
) -> dict[str, str]:
    """Build the agent_outputs dict for an AgentContext based on spec.context_from.

    Routing rules:
      context_from == []           → empty dict (agent receives only user request)
      context_from == ["$previous"] and first agent (index 0) → empty dict
      context_from == ["$previous"] and not first → {prev_id: prev_output}
      context_from == [explicit IDs] → {id: output for id in context_from
                                         if id in accumulated_outputs}
    """
    if not context_from:
        return {}

    if context_from == ["$previous"]:
        if agent_index == 0:
            return {}
        prev_agent = agents[agent_index - 1]
        prev_id = prev_agent.id
        if prev_id in accumulated_outputs:
            return {prev_id: accumulated_outputs[prev_id]}
        return {}

    # Explicit agent IDs — silently omit any that haven't run yet
    return {
        aid: accumulated_outputs[aid]
        for aid in context_from
        if aid in accumulated_outputs
    }


# ============================================================
# WORKFLOW ORCHESTRATOR
# ============================================================

class WorkflowOrchestrator:
    """Central coordinator for all agent workflows.

    Manages agent selection, context passing, revision awareness, and streaming.
    Skill injection, hook injection, and guardrail injection are delegated to
    factory._compose_system_prompt via AgentContext.
    """

    def __init__(
        self,
        pipeline_type: str,
        custom_agents: list | None = None,
        db_session=None,
        user_id: str | None = None,
        attached_skills: list[dict] | None = None,
        attached_hooks: list[dict] | None = None,
    ):
        self.pipeline_type = pipeline_type
        self.is_revision = pipeline_type in REVISION_TYPES
        self.base_pipeline_type = REVISION_BASE_MAP.get(pipeline_type, pipeline_type)
        self.db_session = db_session
        self.user_id = user_id
        # UI-attached skills: list of {id, name, content, source}
        self.attached_skills: list[dict] = attached_skills or []
        # UI-attached hooks: list of {id, name, event, trigger, description}
        self.attached_hooks: list[dict] = attached_hooks or []

        # Shared workspace for deep agents — code-writing agents write files here;
        # at pipeline_complete the workspace is serialised into the final output.
        self._workspace = AgentWorkspace()

        # Load agents from slim registry (returns list[AgentSpec])
        self.agents = custom_agents or get_pipeline_agents(pipeline_type)
        logger.info(
            "WorkflowOrchestrator initialized — type=%s, agents=%d, revision=%s, "
            "attached_skills=%d, attached_hooks=%d",
            pipeline_type, len(self.agents), self.is_revision,
            len(self.attached_skills), len(self.attached_hooks),
        )

    def _load_skills(self) -> dict[str, str]:
        """Load skill content for all agents that have skills.

        Honors per-user skill overrides when ``self.user_id`` is set —
        ``get_skill_content`` walks user → global → built-in (see
        ``app.agents.skills.get_skill_content`` docstring). Without
        the ``user_id`` arg the lookup silently falls back to globals,
        which is the regression we hit when the WS handler stopped
        building the skills dict itself.
        """
        skills: dict[str, str] = {}
        for spec in self.agents:
            skill_content = get_skill_content(spec.id, user_id=self.user_id)
            if skill_content:
                skills[spec.id] = skill_content
                logger.debug("Skill loaded for agent %s (%d chars)", spec.id, len(skill_content))
        return skills

    def _extract_user_request(self, raw_message: str) -> str:
        """Extract the clean user request, stripping context blocks."""
        import re
        # Strip context blocks injected by revision/chain flows
        clean = re.split(
            r'\n\n===\s*(?:EXISTING|CONTEXT FROM PREVIOUS|USER PREFERENCES|ORIGINAL USER REQUEST)',
            raw_message
        )[0].strip()
        return clean or raw_message

    async def execute(
        self,
        user_message: str,
        cancel_event: asyncio.Event | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Execute the full workflow, yielding WebSocket events.

        This is the single entry point for all workflow executions.
        """
        total_start = time.time()

        # Build workflow state
        state = WorkflowState(
            user_request=user_message,
            pipeline_type=self.pipeline_type,
            base_pipeline_type=self.base_pipeline_type,
            is_revision=self.is_revision,
        )

        # Load disk-based skills for all agents (merged into attached_skills below)
        disk_skills = self._load_skills()

        logger.info("═══════════════════════════════════════════════════════")
        logger.info("WORKFLOW START — type=%s, agents=%d, revision=%s",
                    self.pipeline_type, len(self.agents), self.is_revision)
        logger.info("User message: %s", user_message[:100] + ("..." if len(user_message) > 100 else ""))
        logger.info("═══════════════════════════════════════════════════════")

        yield {
            "type": "pipeline_start",
            "data": {
                "pipeline_type": self.pipeline_type,
                "agent_count": len(self.agents),
                "agents": [
                    {"id": s.id, "name": s.name, "role": s.role, "icon": s.icon, "order": s.order}
                    for s in self.agents
                ],
            },
        }

        # Execute agents sequentially
        for i, spec in enumerate(self.agents):
            agent_start = time.time()

            # Check cancellation
            if cancel_event and cancel_event.is_set():
                logger.info("Workflow cancelled before agent %s", spec.name)
                break

            logger.info("───────────────────────────────────────────────────")
            logger.info("AGENT [%d/%d] START — %s (%s)", i + 1, len(self.agents), spec.name, spec.role)

            yield {
                "type": "agent_start",
                "data": {
                    "agent_id": spec.id,
                    "name": spec.name,
                    "role": spec.role,
                    "icon": spec.icon,
                    "index": i,
                    "total": len(self.agents),
                },
            }

            try:
                # Build the filtered agent_outputs dict from spec.context_from
                agent_outputs = _build_agent_outputs(
                    context_from=spec.context_from,
                    agent_index=i,
                    agents=self.agents,
                    accumulated_outputs=state.agent_outputs,
                )

                # Merge disk-based skills into attached_skills for this agent.
                # UI-attached skills take priority; disk skills are appended after.
                merged_skills: list[dict] = list(self.attached_skills)
                if spec.id in disk_skills:
                    merged_skills.append({"content": disk_skills[spec.id]})

                # Build AgentContext — factory handles guardrail/skill/hook injection
                ctx = AgentContext(
                    user_request=user_message,
                    agent_outputs=agent_outputs,
                    attached_skills=merged_skills,
                    attached_hooks=self.attached_hooks,
                    workspace=self._workspace,
                )

                # Instantiate agent via factory
                agent = create_agent(spec.id, ctx)

                # Capture model_id for pipeline-level cost estimation
                if not getattr(state, "_model_id", ""):
                    state._model_id = agent.model_id  # type: ignore[attr-defined]

                if i == 0:
                    thinking_msg = "Analyzing the request..."
                elif i == 1:
                    thinking_msg = "Processing with context from 1 previous agent..."
                else:
                    thinking_msg = f"Processing with context from {i} previous agents..."

                yield {
                    "type": "agent_thinking",
                    "data": {"agent_id": spec.id, "thinking": thinking_msg},
                }

                # Build the context message (user request + prior-agent summaries)
                # Summaries are used instead of full outputs to reduce token usage
                # while preserving all critical information. Full outputs are still
                # stored in state.agent_outputs for DB persistence and final output.
                context_parts = [
                    f"=== ORIGINAL USER REQUEST ===\n{user_message}\n=== END REQUEST ==="
                ]
                for aid, aout in agent_outputs.items():
                    # Find the spec for this agent to get its name/role for labelling
                    prev_spec = next((s for s in self.agents if s.id == aid), None)
                    label = f"{prev_spec.name} ({prev_spec.role})" if prev_spec else aid
                    # Use the detailed summary if available, fall back to full output
                    context_content = state.agent_summaries.get(aid, aout)
                    context_parts.append(
                        f"\n--- Summary from {label} ---\n{context_content}"
                    )
                context_message = "\n".join(context_parts)
                logger.debug("Context message: %d chars", len(context_message))

                # Stream agent response with retry
                output_chunks: list[str] = []
                agent_usage = TokenUsage()
                max_retries = 2

                # Determine whether this is a tool-using DeepAgent
                use_deep = bool(spec.tools) and isinstance(agent, DeepAgent)

                for attempt in range(max_retries + 1):
                    if cancel_event and cancel_event.is_set():
                        raise asyncio.CancelledError()

                    try:
                        output_chunks: list[str] = []
                        agent_usage = TokenUsage()
                        # DeepAgent: stream both text chunks AND tool events
                        if use_deep:
                            tool_input_tokens = 0
                            tool_output_tokens = 0
                            async for event in agent.astream_events(context_message):
                                if cancel_event and cancel_event.is_set():
                                    raise asyncio.CancelledError()
                                if event["type"] == "chunk":
                                    output_chunks.append(event["chunk"])
                                    yield {
                                        "type": "agent_chunk",
                                        "data": {"agent_id": spec.id, "chunk": event["chunk"]},
                                    }
                                elif event["type"] == "tool_call":
                                    yield {
                                        "type": "tool_call",
                                        "data": {
                                            "agent_id": spec.id,
                                            "tool": event["tool"],
                                            "args": event.get("args", {}),
                                        },
                                    }
                                elif event["type"] == "tool_result":
                                    yield {
                                        "type": "tool_result",
                                        "data": {
                                            "agent_id": spec.id,
                                            "tool": event["tool"],
                                            "result": str(event.get("result", ""))[:500],
                                        },
                                    }
                                elif event["type"] == "usage":
                                    # Accumulate token usage from each iteration
                                    tool_input_tokens += event.get("input_tokens", 0)
                                    tool_output_tokens += event.get("output_tokens", 0)
                            # Build TokenUsage from accumulated counts
                            agent_usage = TokenUsage(
                                input_tokens=tool_input_tokens,
                                output_tokens=tool_output_tokens,
                                total_tokens=tool_input_tokens + tool_output_tokens,
                            )
                        else:
                            async for item in agent.astream_with_usage(context_message):
                                if cancel_event and cancel_event.is_set():
                                    raise asyncio.CancelledError()
                                if isinstance(item, TokenUsage):
                                    agent_usage = item
                                else:
                                    output_chunks.append(item)
                                    yield {
                                        "type": "agent_chunk",
                                        "data": {"agent_id": spec.id, "chunk": item},
                                    }
                        break  # Success

                    except asyncio.CancelledError:
                        raise  # Always propagate cancellation

                    except Exception as stream_err:
                        err_name = type(stream_err).__name__
                        err_str = str(stream_err).lower()
                        # Recognise transient infrastructure and Bedrock-side
                        # rate-limit / capacity errors. Without ThrottlingException
                        # here, a single Bedrock throttle on agent N would emit
                        # `agent_error` and the orchestrator would then continue
                        # downstream agents with a garbage context — far worse
                        # than a 2-second retry.
                        is_transient = (
                            "RemoteProtocolError" in err_name
                            or "ReadTimeout" in err_name
                            or "chunked" in err_str
                            or "ThrottlingException" in err_name
                            or "ServiceQuotaExceededException" in err_name
                            or "ModelTimeoutException" in err_name
                            or "ModelStreamErrorException" in err_name
                            or "ServiceUnavailableException" in err_name
                            or "InternalServerException" in err_name
                            or "TooManyRequestsException" in err_name
                            or "throttl" in err_str
                            or "rate exceeded" in err_str
                        )
                        if attempt < max_retries and is_transient:
                            logger.warning(
                                "RETRY %d/%d for %s — %s",
                                attempt + 1, max_retries, spec.name, err_name
                            )
                            yield {
                                "type": "agent_thinking",
                                "data": {
                                    "agent_id": spec.id,
                                    "thinking": f"Connection interrupted, retrying ({attempt + 1}/{max_retries})...",
                                },
                            }
                            await asyncio.sleep(2)
                            continue
                        raise

                # Store full output in state (used for DB persistence and final output)
                output = "".join(output_chunks)
                duration = time.time() - agent_start
                state.agent_outputs[spec.id] = output
                state.agent_token_usage[spec.id] = agent_usage

                # Generate a detailed summary for use as downstream context.
                # This runs asynchronously after the agent completes and before
                # the next agent starts. The summary replaces the full output
                # in context_message for all downstream agents.
                # DeepAgent architecture is not affected — summarization only
                # changes what goes into the context_message user input.
                summary = await summarize_agent_output(
                    agent_name=spec.name,
                    agent_role=spec.role,
                    pipeline_type=self.pipeline_type,
                    output=output,
                )
                state.agent_summaries[spec.id] = summary

                cost = estimate_cost_usd(agent_usage, agent.model_id)
                state.results.append({
                    "agent_id": spec.id,
                    "name": spec.name,
                    "role": spec.role,
                    "icon": spec.icon,
                    "output": output,
                    "duration": duration,
                    "token_usage": agent_usage.to_dict(),
                })

                logger.info(
                    "AGENT [%d/%d] COMPLETE — %s | %.2fs | %d chars | in=%d out=%d (~$%.4f)",
                    i + 1, len(self.agents), spec.name, duration, len(output),
                    agent_usage.input_tokens, agent_usage.output_tokens, cost,
                )

                yield {
                    "type": "agent_complete",
                    "data": {
                        "agent_id": spec.id,
                        "name": spec.name,
                        "duration": round(duration, 2),
                        "output_length": len(output),
                        "index": i,
                        "total": len(self.agents),
                        "input_tokens": agent_usage.input_tokens,
                        "output_tokens": agent_usage.output_tokens,
                        "total_tokens": agent_usage.total_tokens,
                        "estimated_cost_usd": round(cost, 6),
                    },
                }

            except asyncio.CancelledError:
                logger.info("AGENT [%d/%d] CANCELLED — %s", i + 1, len(self.agents), spec.name)
                raise

            except AgentConfigurationError as e:
                logger.error("AGENT CONFIG ERROR — %s: %s", spec.name, e)
                yield {
                    "type": "agent_error",
                    "data": {"agent_id": spec.id, "error": str(e), "recoverable": False},
                }
                break

            except (FileNotFoundError, PermissionError) as e:
                # Factory could not locate or read the AGENT.md file — the pipeline
                # cannot continue with incomplete context, so halt immediately.
                # (AgentSpecError is also a fatal configuration error; it is imported
                # from agents.loader and handled here via the broad except below if
                # it is not a subclass of the above, but FileNotFoundError is the
                # primary case from create_agent per Requirement 9.7.)
                logger.error("AGENT SETUP FAILED — %s: %s", spec.name, e)
                duration = time.time() - agent_start
                yield {
                    "type": "agent_error",
                    "data": {
                        "agent_id": spec.id,
                        "error": str(e),
                        "duration": round(duration, 2),
                        "recoverable": False,
                    },
                }
                break

            except Exception as e:
                # Check for AgentSpecError (malformed AGENT.md) — also fatal.
                from agents.loader import AgentSpecError  # noqa: PLC0415
                if isinstance(e, AgentSpecError):
                    logger.error("AGENT SPEC ERROR — %s: %s", spec.name, e)
                    duration = time.time() - agent_start
                    yield {
                        "type": "agent_error",
                        "data": {
                            "agent_id": spec.id,
                            "error": str(e),
                            "duration": round(duration, 2),
                            "recoverable": False,
                        },
                    }
                    break

                logger.error("AGENT FAILED — %s: %s", spec.name, e, exc_info=True)
                duration = time.time() - agent_start
                yield {
                    "type": "agent_error",
                    "data": {
                        "agent_id": spec.id,
                        "error": str(e),
                        "duration": round(duration, 2),
                        "recoverable": True,
                    },
                }
                state.agent_outputs[spec.id] = f"[Error: {str(e)}]"
                continue

        # Pipeline complete
        total_duration = time.time() - total_start
        final_output = self._get_final_output(state)

        # Aggregate token usage across all agents
        pipeline_usage = TokenUsage()
        for usage in state.agent_token_usage.values():
            pipeline_usage = pipeline_usage + usage
        pipeline_model_id = getattr(state, "_model_id", "")
        pipeline_cost = estimate_cost_usd(pipeline_usage, pipeline_model_id)

        logger.info("═══════════════════════════════════════════════════════")
        logger.info(
            "WORKFLOW COMPLETE — type=%s | %.2fs | %d/%d agents | tokens: in=%d out=%d (~$%.4f)",
            self.pipeline_type, total_duration, len(state.results), len(self.agents),
            pipeline_usage.input_tokens, pipeline_usage.output_tokens, pipeline_cost,
        )
        logger.info("═══════════════════════════════════════════════════════")

        yield {
            "type": "pipeline_complete",
            "data": {
                "pipeline_type": self.pipeline_type,
                "total_duration": round(total_duration, 2),
                "agents_completed": len(state.results),
                "agents_total": len(self.agents),
                "final_output": final_output,
                "total_input_tokens": pipeline_usage.input_tokens,
                "total_output_tokens": pipeline_usage.output_tokens,
                "total_tokens": pipeline_usage.total_tokens,
                "estimated_cost_usd": round(pipeline_cost, 6),
                "token_usage_per_agent": {
                    aid: u.to_dict()
                    for aid, u in state.agent_token_usage.items()
                },
            },
        }

    def _get_final_output(self, state: WorkflowState) -> str:
        """Get the final output.

        If any deep agent wrote files to the workspace, the workspace contents
        take precedence — they represent the structured deliverable the user
        will download. Otherwise fall back to the last agent's text output.
        """
        if self._workspace.file_count() > 0:
            return self._workspace.to_final_output()
        if state.results:
            return state.results[-1].get("output", "")
        return ""

    def get_all_outputs(self, state: WorkflowState) -> dict[str, str]:
        """Get all agent outputs."""
        return dict(state.agent_outputs)
