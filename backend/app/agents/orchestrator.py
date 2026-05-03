"""Agent Orchestrator: Multi-phase execution pipeline coordinator."""

import json
import logging
from typing import AsyncGenerator

from app.agents import (
    DiscoveryAgent,
    PPTAgent,
    PreviewAgent,
    PrototypeAgent,
    RequirementsAgent,
    UIDesignAgent,
    UserStoryAgent,
)
from app.models.schemas import FinalOutputModel

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Orchestrates the multi-phase AI agent execution pipeline.

    Manages Phases 0-7:
      Phase 0: Discovery (determines Output_Selection)
      Phase 1: Requirements generation
      Phase 2: Conditional routing (determines which phases 3-7 to run)
      Phase 3: User Story generation
      Phase 4: PPT slide generation
      Phase 5: Prototype generation
      Phase 6: UI Design generation
      Phase 7: Preview/Final_Output compilation
    """

    # Maps phase numbers to their section keys in Final_Output
    PHASE_SECTIONS = {
        0: "discovery",
        1: "requirements",
        3: "user_stories",
        4: "ppt",
        5: "prototype",
        6: "ui_design",
        7: "ui_preview",
    }

    # Maps output selection keys to their corresponding phase numbers
    OUTPUT_TO_PHASE = {
        "user_stories": 3,
        "ppt": 4,
        "prototype": 5,
        "ui_design": 6,
    }

    def __init__(self):
        """Initialize the orchestrator with all specialized agents."""
        self.discovery_agent = DiscoveryAgent()
        self.requirements_agent = RequirementsAgent()
        self.user_story_agent = UserStoryAgent()
        self.ppt_agent = PPTAgent()
        self.prototype_agent = PrototypeAgent()
        self.ui_design_agent = UIDesignAgent()
        self.preview_agent = PreviewAgent()

    def _get_agent_for_phase(self, phase: int):
        """Return the agent instance responsible for a given phase.

        Args:
            phase: The phase number (0-7).

        Returns:
            The agent instance for the phase, or None for Phase 2 (routing).
        """
        agents = {
            0: self.discovery_agent,
            1: self.requirements_agent,
            3: self.user_story_agent,
            4: self.ppt_agent,
            5: self.prototype_agent,
            6: self.ui_design_agent,
            7: self.preview_agent,
        }
        return agents.get(phase)

    def _determine_active_phases(self, output_selection: list[str]) -> list[int]:
        """Determine which phases 3-7 should be active based on Output_Selection.

        Args:
            output_selection: List of selected output types
                (e.g., ["user_stories", "ppt", "prototype"]).

        Returns:
            Sorted list of phase numbers to execute.
        """
        active_phases = []

        for output_key in output_selection:
            phase = self.OUTPUT_TO_PHASE.get(output_key)
            if phase is not None:
                active_phases.append(phase)

        # Phase 7 (Preview) always runs to compile Final_Output
        if 7 not in active_phases:
            active_phases.append(7)

        return sorted(active_phases)

    def _parse_output_selection(self, discovery_output: str) -> list[str]:
        """Parse the discovery agent's output to extract Output_Selection.

        Looks for keywords indicating which deliverables the user wants.

        Args:
            discovery_output: The text output from the Discovery Agent.

        Returns:
            List of selected output keys.
        """
        output_lower = discovery_output.lower()
        selection = []

        # Check for "all" keyword first
        if "all" in output_lower and (
            "generate: all" in output_lower
            or "i'll generate: all" in output_lower
            or "generate all" in output_lower
        ):
            return ["user_stories", "ppt", "prototype", "ui_design"]

        if "user stor" in output_lower:
            selection.append("user_stories")
        if "ppt" in output_lower or "powerpoint" in output_lower or "presentation" in output_lower or "slide" in output_lower:
            selection.append("ppt")
        if "prototype" in output_lower:
            selection.append("prototype")
        if "ui design" in output_lower or "design spec" in output_lower:
            selection.append("ui_design")

        # Default to all if nothing specific was detected
        if not selection:
            selection = ["user_stories", "ppt", "prototype", "ui_design"]

        return selection

    def _compile_final_output(
        self, context: dict, output_selection: list[str]
    ) -> FinalOutputModel:
        """Compile all phase outputs into the Final_Output structure.

        Args:
            context: Accumulated context dict with outputs from each phase.
            output_selection: The selected output types.

        Returns:
            A FinalOutputModel with all 10 required sections.
        """
        # All possible sections with their phase mappings
        section_phase_map = {
            "auth": None,
            "realtime": None,
            "dashboard": None,
            "discovery": 0,
            "requirements": 1,
            "user_stories": 3,
            "ppt": 4,
            "prototype": 5,
            "ui_design": 6,
            "ui_preview": 7,
        }

        output_data = {}

        for section, phase in section_phase_map.items():
            if phase is None:
                # Static sections not tied to a phase
                output_data[section] = context.get(section)
            elif section in context:
                # Phase was executed and produced output
                phase_output = context[section]
                if isinstance(phase_output, dict) and phase_output.get("status") == "failed":
                    output_data[section] = phase_output
                else:
                    output_data[section] = phase_output
            elif section in ("discovery", "requirements", "ui_preview"):
                # These phases always run; if missing, set to None
                output_data[section] = None
            elif section in self.OUTPUT_TO_PHASE and section not in output_selection:
                # Phase was skipped due to Output_Selection
                output_data[section] = {"status": "skipped", "value": None}
            else:
                output_data[section] = None

        return FinalOutputModel(**output_data)

    async def _run_phase(
        self, phase: int, user_message: str, context: dict
    ) -> str | None:
        """Execute a single phase and return its output.

        Args:
            phase: The phase number to execute.
            user_message: The original user message.
            context: Accumulated context from prior phases.

        Returns:
            The agent's output string, or None if the phase has no agent.
        """
        agent = self._get_agent_for_phase(phase)
        if agent is None:
            return None

        return await agent.run(user_message, context=context)

    async def execute(
        self, user_message: str, chat_session_id: str | None = None
    ) -> FinalOutputModel:
        """Run the full multi-phase execution pipeline.

        Args:
            user_message: The user's input message.
            chat_session_id: Optional chat session ID for tracking.

        Returns:
            The compiled FinalOutputModel with all phase outputs.
        """
        context: dict = {}
        output_selection: list[str] = []

        # Phase 0: Discovery
        try:
            logger.info("Phase 0: Starting Discovery")
            discovery_output = await self._run_phase(0, user_message, context)
            if discovery_output:
                context["discovery"] = {"output": discovery_output}
                output_selection = self._parse_output_selection(discovery_output)
                context["output_selection"] = output_selection
            logger.info(f"Phase 0: Complete. Output_Selection: {output_selection}")
        except Exception as e:
            logger.error(f"Phase 0 (Discovery) failed: {e}")
            context["discovery"] = {"status": "failed", "error": str(e)}
            output_selection = ["user_stories", "ppt", "prototype", "ui_design"]
            context["output_selection"] = output_selection

        # Phase 1: Requirements
        try:
            logger.info("Phase 1: Starting Requirements")
            requirements_output = await self._run_phase(1, user_message, context)
            if requirements_output:
                context["requirements"] = {"output": requirements_output}
            logger.info("Phase 1: Complete")
        except Exception as e:
            logger.error(f"Phase 1 (Requirements) failed: {e}")
            context["requirements"] = {"status": "failed", "error": str(e)}

        # Phase 2: Conditional Routing
        active_phases = self._determine_active_phases(output_selection)
        logger.info(f"Phase 2: Routing. Active phases: {active_phases}")

        # Phases 3-7: Sequential execution of selected phases
        for phase in active_phases:
            section = self.PHASE_SECTIONS.get(phase)
            if section is None:
                continue

            try:
                logger.info(f"Phase {phase}: Starting ({section})")
                phase_output = await self._run_phase(phase, user_message, context)
                if phase_output:
                    # Try to parse JSON output for structured sections
                    if phase in (4, 5, 7):
                        try:
                            context[section] = json.loads(phase_output)
                        except (json.JSONDecodeError, TypeError):
                            context[section] = {"output": phase_output}
                    else:
                        context[section] = {"output": phase_output}
                logger.info(f"Phase {phase}: Complete ({section})")
            except Exception as e:
                logger.error(f"Phase {phase} ({section}) failed: {e}")
                context[section] = {"status": "failed", "error": str(e)}

        # Compile Final_Output
        final_output = self._compile_final_output(context, output_selection)
        logger.info("Pipeline complete. Final_Output compiled.")
        return final_output

    async def astream_execute(
        self, user_message: str, chat_session_id: str | None = None,
        mode: str = "default", mode_prompt: str = "",
    ) -> AsyncGenerator[dict, None]:
        """Run the full pipeline, yielding StreamMessage-like dicts for WebSocket streaming.

        Yields dicts with keys: type, chunk, section, data.

        Args:
            user_message: The user's input message.
            chat_session_id: Optional chat session ID for tracking.
            mode: The chat mode selected by the user.
            mode_prompt: The mode-specific system prompt enhancement.

        Yields:
            Dicts conforming to StreamMessageModel structure.
        """
        context: dict = {}
        output_selection: list[str] = []

        # Inject mode context so agents are aware of the mode
        if mode_prompt:
            context["mode"] = mode
            context["mode_prompt"] = mode_prompt

        # Phase 0: Discovery
        yield {"type": "phase_start", "section": "discovery", "chunk": None, "data": {"phase": 0, "name": "Discovery"}}
        try:
            logger.info("Phase 0: Starting Discovery (streaming)")
            discovery_output_parts = []
            async for chunk in self.discovery_agent.astream(user_message, context=context):
                discovery_output_parts.append(chunk)
                yield {"type": "stream", "chunk": chunk, "section": "discovery", "data": None}

            discovery_output = "".join(discovery_output_parts)
            context["discovery"] = {"output": discovery_output}
            output_selection = self._parse_output_selection(discovery_output)
            context["output_selection"] = output_selection
            logger.info(f"Phase 0: Complete. Output_Selection: {output_selection}")
        except Exception as e:
            logger.error(f"Phase 0 (Discovery) failed: {e}")
            context["discovery"] = {"status": "failed", "error": str(e)}
            output_selection = ["user_stories", "ppt", "prototype", "ui_design"]
            context["output_selection"] = output_selection
            yield {"type": "error", "chunk": None, "section": "discovery", "data": {"error": str(e), "phase": 0}}
        yield {"type": "phase_end", "section": "discovery", "chunk": None, "data": {"phase": 0}}

        # Phase 1: Requirements
        yield {"type": "phase_start", "section": "requirements", "chunk": None, "data": {"phase": 1, "name": "Requirements"}}
        try:
            logger.info("Phase 1: Starting Requirements (streaming)")
            requirements_parts = []
            async for chunk in self.requirements_agent.astream(user_message, context=context):
                requirements_parts.append(chunk)
                yield {"type": "stream", "chunk": chunk, "section": "requirements", "data": None}

            requirements_output = "".join(requirements_parts)
            context["requirements"] = {"output": requirements_output}
            logger.info("Phase 1: Complete")
        except Exception as e:
            logger.error(f"Phase 1 (Requirements) failed: {e}")
            context["requirements"] = {"status": "failed", "error": str(e)}
            yield {"type": "error", "chunk": None, "section": "requirements", "data": {"error": str(e), "phase": 1}}
        yield {"type": "phase_end", "section": "requirements", "chunk": None, "data": {"phase": 1}}

        # Phase 2: Conditional Routing
        active_phases = self._determine_active_phases(output_selection)
        logger.info(f"Phase 2: Routing. Active phases: {active_phases}")

        # Phases 3-7: Sequential execution of selected phases
        for phase in active_phases:
            section = self.PHASE_SECTIONS.get(phase)
            if section is None:
                continue

            agent = self._get_agent_for_phase(phase)
            if agent is None:
                continue

            yield {"type": "phase_start", "section": section, "chunk": None, "data": {"phase": phase, "name": section}}
            try:
                logger.info(f"Phase {phase}: Starting ({section}) (streaming)")
                phase_parts = []
                async for chunk in agent.astream(user_message, context=context):
                    phase_parts.append(chunk)
                    yield {"type": "stream", "chunk": chunk, "section": section, "data": None}

                phase_output = "".join(phase_parts)

                # Try to parse JSON for structured sections
                if phase in (4, 5, 7):
                    try:
                        context[section] = json.loads(phase_output)
                    except (json.JSONDecodeError, TypeError):
                        context[section] = {"output": phase_output}
                else:
                    context[section] = {"output": phase_output}

                logger.info(f"Phase {phase}: Complete ({section})")
            except Exception as e:
                logger.error(f"Phase {phase} ({section}) failed: {e}")
                context[section] = {"status": "failed", "error": str(e)}
                yield {"type": "error", "chunk": None, "section": section, "data": {"error": str(e), "phase": phase}}
            yield {"type": "phase_end", "section": section, "chunk": None, "data": {"phase": phase}}

        # Compile Final_Output
        final_output = self._compile_final_output(context, output_selection)
        logger.info("Pipeline complete. Final_Output compiled.")

        yield {
            "type": "complete",
            "chunk": None,
            "section": None,
            "data": final_output.model_dump(),
        }
