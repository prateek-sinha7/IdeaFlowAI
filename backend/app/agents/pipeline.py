"""Pipeline Executor — Runs a chain of agents sequentially with streaming status updates."""

import logging
import time
from typing import AsyncGenerator

from app.agents.base import BaseAgent, AgentConfigurationError
from app.agents.registry import AgentDefinition, get_pipeline_agents

logger = logging.getLogger("app.agents.pipeline")


class PipelineExecutor:
    """Executes a pipeline of agents sequentially, streaming status updates.

    Each agent receives the accumulated context from all previous agents.
    Status updates are yielded as dicts for WebSocket streaming.
    """

    def __init__(self, pipeline_type: str, custom_agents: list[AgentDefinition] | None = None):
        self.pipeline_type = pipeline_type
        self.agents = custom_agents or get_pipeline_agents(pipeline_type)
        self.context: dict[str, str] = {}
        self.results: list[dict] = []
        logger.info("Pipeline initialized — type=%s, agents=%d", pipeline_type, len(self.agents))

    async def execute(
        self, user_message: str, skills: dict[str, str] | None = None
    ) -> AsyncGenerator[dict, None]:
        """Execute the full pipeline, yielding status updates for each agent."""
        skills = skills or {}
        total_start = time.time()

        logger.info("═══════════════════════════════════════════════════════")
        logger.info("PIPELINE START — type=%s, agents=%d", self.pipeline_type, len(self.agents))
        logger.info("User message: %s", user_message[:100] + ("..." if len(user_message) > 100 else ""))
        logger.info("═══════════════════════════════════════════════════════")

        yield {
            "type": "pipeline_start",
            "data": {
                "pipeline_type": self.pipeline_type,
                "agent_count": len(self.agents),
                "agents": [
                    {"id": a.id, "name": a.name, "role": a.role, "icon": a.icon, "order": a.order}
                    for a in self.agents
                ],
            },
        }

        for i, agent_def in enumerate(self.agents):
            agent_start = time.time()

            logger.info("───────────────────────────────────────────────────")
            logger.info("AGENT [%d/%d] START — %s (%s)", i + 1, len(self.agents), agent_def.name, agent_def.role)
            logger.info("   ID: %s | Pipeline: %s | Est: %.1fs", agent_def.id, agent_def.pipeline_type, agent_def.estimated_duration)

            yield {
                "type": "agent_start",
                "data": {
                    "agent_id": agent_def.id,
                    "name": agent_def.name,
                    "role": agent_def.role,
                    "icon": agent_def.icon,
                    "index": i,
                    "total": len(self.agents),
                },
            }

            try:
                # Build the agent with optional skill injection
                system_prompt = agent_def.system_prompt
                if agent_def.id in skills:
                    system_prompt = f"{skills[agent_def.id]}\n\n{system_prompt}"
                    logger.debug("   Skill injected for agent %s", agent_def.id)

                agent = BaseAgent(system_prompt=system_prompt, max_tokens=agent_def.max_tokens)

                # Build context message for this agent
                context_message = self._build_context_message(user_message, i)
                logger.debug("   Context message length: %d chars (from %d previous agents)", len(context_message), i)

                # Stream the agent's response
                output_chunks: list[str] = []

                yield {
                    "type": "agent_thinking",
                    "data": {
                        "agent_id": agent_def.id,
                        "thinking": f"Processing with context from {i} previous agents...",
                    },
                }

                async for chunk in agent.astream(context_message):
                    output_chunks.append(chunk)
                    yield {
                        "type": "agent_chunk",
                        "data": {
                            "agent_id": agent_def.id,
                            "chunk": chunk,
                        },
                    }

                # Store the result
                output = "".join(output_chunks)
                duration = time.time() - agent_start

                self.context[agent_def.id] = output
                self.results.append({
                    "agent_id": agent_def.id,
                    "name": agent_def.name,
                    "output": output,
                    "duration": duration,
                })

                logger.info("AGENT [%d/%d] COMPLETE — %s | %.2fs | %d chars output",
                           i + 1, len(self.agents), agent_def.name, duration, len(output))

                yield {
                    "type": "agent_complete",
                    "data": {
                        "agent_id": agent_def.id,
                        "name": agent_def.name,
                        "duration": round(duration, 2),
                        "output_length": len(output),
                        "index": i,
                        "total": len(self.agents),
                    },
                }

            except AgentConfigurationError as e:
                logger.error("AGENT [%d/%d] CONFIG ERROR — %s: %s", i + 1, len(self.agents), agent_def.name, e)
                yield {
                    "type": "agent_error",
                    "data": {
                        "agent_id": agent_def.id,
                        "error": str(e),
                        "recoverable": False,
                    },
                }
                break  # Stop pipeline on config error

            except Exception as e:
                logger.error("AGENT [%d/%d] FAILED — %s: %s", i + 1, len(self.agents), agent_def.name, e, exc_info=True)
                duration = time.time() - agent_start

                yield {
                    "type": "agent_error",
                    "data": {
                        "agent_id": agent_def.id,
                        "error": str(e),
                        "duration": round(duration, 2),
                        "recoverable": True,
                    },
                }
                # Continue to next agent on recoverable errors
                self.context[agent_def.id] = f"[Error: {str(e)}]"
                continue

        # Pipeline complete
        total_duration = time.time() - total_start

        logger.info("═══════════════════════════════════════════════════════")
        logger.info("PIPELINE COMPLETE — type=%s | %.2fs total | %d/%d agents succeeded",
                   self.pipeline_type, total_duration, len(self.results), len(self.agents))
        logger.info("═══════════════════════════════════════════════════════")

        yield {
            "type": "pipeline_complete",
            "data": {
                "pipeline_type": self.pipeline_type,
                "total_duration": round(total_duration, 2),
                "agents_completed": len(self.results),
                "agents_total": len(self.agents),
                "final_output": self._get_final_output(),
            },
        }

    def _build_context_message(self, user_message: str, current_index: int) -> str:
        """Build the context message for the current agent.
        
        Strategy: 
        - Keep original request prominent
        - For prototype pipeline: only pass the LAST agent's output (HTML) to avoid bloat
        - For other pipelines: pass all previous outputs with reasonable limits
        """
        parts = [f"=== ORIGINAL USER REQUEST ===\n{user_message}\n=== END REQUEST ==="]

        if (self.pipeline_type == "prototype" and current_index >= 2) or (self.pipeline_type == "ppt" and current_index >= 2):
            # For prototype/PPT polisher agents, only pass the immediately previous agent's output
            # (the HTML) — they don't need the content plan
            prev_agent = self.agents[current_index - 1]
            if prev_agent.id in self.context:
                prev_output = self.context[prev_agent.id]
                max_len = 30000
                if len(prev_output) > max_len:
                    prev_output = prev_output[:max_len] + "\n...[truncated]"
                parts.append(f"\n--- Output from {prev_agent.name} ({prev_agent.role}) ---\n{prev_output}")
        else:
            for i, prev_agent in enumerate(self.agents[:current_index]):
                if prev_agent.id in self.context:
                    prev_output = self.context[prev_agent.id]
                    max_len = 8000
                    if len(prev_output) > max_len:
                        prev_output = prev_output[:max_len] + "\n...[truncated]"
                    parts.append(f"\n--- Output from {prev_agent.name} ({prev_agent.role}) ---\n{prev_output}")

        return "\n".join(parts)

    def _get_final_output(self) -> str:
        """Get the final compiled output from the last agent."""
        if self.results:
            return self.results[-1].get("output", "")
        return ""

    def get_all_outputs(self) -> dict[str, str]:
        """Get all agent outputs as a dict."""
        return dict(self.context)
