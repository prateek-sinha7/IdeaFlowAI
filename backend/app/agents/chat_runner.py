"""app/agents/chat_runner.py — the free-chat sequencer on the deepagents stack.

The dedicated drop-in replacement for the legacy
``app/agents/orchestrator.AgentOrchestrator`` (migration Phase 7b, plan
``specs/002-deepagents-migration/plan.md`` §5 "Phase 7" — task 7b-10).

The conversational ``user_message`` WebSocket path is a SEPARATE subsystem from
the pipeline runtime (the ``ExecutionEngine``): it runs a multi-phase generator
(Discovery → Requirements → UserStories/PPT/Prototype/UIDesign → Preview) with
its OWN event vocabulary (``phase_start`` / ``stream`` / ``phase_end`` /
``error`` / trailing ``complete``) and a RUNTIME output-selection (parsed from
the discovery prose) that the engine cannot model. So the chat path keeps its
own sequencer; this class IS that sequencer, ported off ``BaseAgent`` onto the
``deepagents`` runtime.

What it reuses vs. reproduces:
  - **Reuses** ``agents.factory.create_runner("chat-<x>", ctx)`` to build each of
    the 7 chat agents as a ``DeepAgentRunner`` over a ``deepagents`` graph. The
    chat AGENT.md specs declare ``tools: []`` → ``_build_runner_tools`` returns
    ``([], exclude_builtin_tools=True)`` → a PURE-TEXT stream (no tool chips leak
    into the chat bubble). The agent's system prompt comes from its AGENT.md.
  - **Reproduces VERBATIM** (ported from ``AgentOrchestrator``, NOT reinvented):
    ``_parse_output_selection`` (keyword scan of the discovery text),
    ``_determine_active_phases`` (``OUTPUT_TO_PHASE`` + always-append phase 7,
    sorted), ``_compile_final_output`` (the 10-key ``FinalOutputModel``), the
    ``PHASE_SECTIONS`` map, and the exact per-phase event emission.

Event contract (byte-for-byte identical to the legacy — the frozen golden in
``tests/unit/test_chat_contract.py`` proves it). Every event is the
``StreamMessageModel`` shape ``{type, chunk, section, data}``:

    phase_start{section, data:{phase, name}}
      → stream{section, chunk}   (one per streamed chunk)
      → phase_end{section, data:{phase}}                         (per active phase)
    [error{section, data:{error, code, recoverable, phase}}  if a phase raises;
     the pipeline then CONTINUES to the next phase]
    complete{section:None, data:<10-key FinalOutputModel.model_dump()>}  (trailing)

Context + mode threading: ``DeepAgentRunner.astream(msg)`` takes a SINGLE message
string (not the legacy ``(user_message, context=…)`` pair), so this runner
composes one string that prepends ``mode_prompt`` and the flattened prior-phase
context onto the user message — functionally the same information the legacy
``BaseAgent._build_messages`` injected (mode_prompt into the system prompt + a
"context from previous phases" human turn). Byte-identical PROMPT composition is
NOT required (the golden mocks the LLM); the EVENT CONTRACT is. The accumulated
``context`` dict is maintained byte-identically to the legacy so the ported
``_parse_output_selection`` / ``_compile_final_output`` produce identical output.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, AsyncGenerator

from app.models.schemas import FinalOutputModel

if TYPE_CHECKING:
    from agents.factory import AgentContext
    from app.agents.deep_agent_runner import DeepAgentRunner

logger = logging.getLogger("app.agents.chat_runner")


class ChatRunner:
    """Free-chat multi-phase sequencer over ``deepagents`` (text-only) agents.

    Build one per chat turn (the WebSocket handler constructs it for each
    ``user_message``). ``astream_execute`` drives the 7 chat agents in phase
    order and yields the legacy WS event vocabulary.

    Args:
        ctx: Optional :class:`agents.factory.AgentContext`. The 7 chat
            ``DeepAgentRunner``s are built from it (``ctx.model`` selects the
            chat model; ``ctx.user_id`` / ``ctx.run_id`` root the — unused, for
            text-only agents — per-run sandbox). When ``None`` a minimal default
            context is constructed. The offline contract test (7b-6) passes a
            scripted model as ``ctx.model`` (and/or swaps each runner's
            ``.astream`` post-construction — see ``_runners``).
        user_id: Convenience to build a default context when ``ctx`` is ``None``.
        run_id: Convenience to build a default context when ``ctx`` is ``None``.
    """

    # ── Maps phase numbers to their section keys in Final_Output ──────────
    # (ported verbatim from AgentOrchestrator.PHASE_SECTIONS)
    PHASE_SECTIONS: dict[int, str] = {
        0: "discovery",
        1: "requirements",
        3: "user_stories",
        4: "ppt",
        5: "prototype",
        6: "ui_design",
        7: "ui_preview",
    }

    # ── Maps output-selection keys to their phase numbers ─────────────────
    # (ported verbatim from AgentOrchestrator.OUTPUT_TO_PHASE)
    OUTPUT_TO_PHASE: dict[str, int] = {
        "user_stories": 3,
        "ppt": 4,
        "prototype": 5,
        "ui_design": 6,
    }

    # ── phase → (chat agent id, phase_start display name) ─────────────────
    # The chat AGENT.md ids under the "chat" pipeline_type. The display name
    # matches the legacy phase_start payload EXACTLY: phases 0/1 use a capitalised
    # display name ("Discovery"/"Requirements"); phases 3-7 use the section key
    # itself (the legacy loop passes ``name=section`` for those — see the golden).
    _PHASE_AGENTS: dict[int, tuple[str, str]] = {
        0: ("chat-discovery", "Discovery"),
        1: ("chat-requirements", "Requirements"),
        3: ("chat-user-stories", "user_stories"),
        4: ("chat-ppt", "ppt"),
        5: ("chat-prototype", "prototype"),
        6: ("chat-ui-design", "ui_design"),
        7: ("chat-preview", "ui_preview"),
    }

    def __init__(
        self,
        ctx: "AgentContext | None" = None,
        *,
        user_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        from agents.factory import AgentContext, create_runner

        if ctx is None:
            ctx = AgentContext(user_request="", user_id=user_id, run_id=run_id)
        self._ctx = ctx

        # Instantiate the 7 chat agents as text-only DeepAgentRunners. Each is a
        # `create_deep_agent` graph (tools=[] → exclude_builtin_tools=True → pure
        # text). Building the graph does NOT call the model — the network is only
        # touched when `.astream(msg)` runs, so eager construction is cheap and
        # mirrors the legacy orchestrator (which constructed all 7 agents in
        # __init__). Stored in a phase→runner map so a phase's agent is fetched by
        # `_runner_for_phase(phase)`; the 7b-6 contract test swaps each runner's
        # `.astream` here exactly as the legacy test swaps each agent's `.astream`.
        self._runners: dict[int, "DeepAgentRunner"] = {}
        for phase, (agent_id, _name) in self._PHASE_AGENTS.items():
            self._runners[phase] = create_runner(agent_id, ctx)

    # -----------------------------------------------------------------------
    # Ported helpers — byte-for-byte from AgentOrchestrator (do NOT reinvent).
    # -----------------------------------------------------------------------

    def _runner_for_phase(self, phase: int) -> "DeepAgentRunner | None":
        """Return the chat ``DeepAgentRunner`` for a phase, or ``None`` if unmapped."""
        return self._runners.get(phase)

    def _determine_active_phases(self, output_selection: list[str]) -> list[int]:
        """Determine which phases 3-7 are active for the given Output_Selection.

        Ported verbatim from ``AgentOrchestrator._determine_active_phases``:
        map each selected output key to its phase via ``OUTPUT_TO_PHASE``, then
        ALWAYS append phase 7 (Preview compiles Final_Output), and return sorted.
        """
        active_phases: list[int] = []

        for output_key in output_selection:
            phase = self.OUTPUT_TO_PHASE.get(output_key)
            if phase is not None:
                active_phases.append(phase)

        # Phase 7 (Preview) always runs to compile Final_Output
        if 7 not in active_phases:
            active_phases.append(7)

        return sorted(active_phases)

    def _parse_output_selection(self, discovery_output: str) -> list[str]:
        """Parse the discovery agent's text to extract Output_Selection.

        Ported verbatim from ``AgentOrchestrator._parse_output_selection``: a
        keyword scan of the (lower-cased) discovery prose. The "all" fast-path
        and the per-deliverable keyword checks (and the default-to-all when
        nothing matched) MUST stay identical — the chat frontend's deliverable
        set is driven by exactly this parse.
        """
        output_lower = discovery_output.lower()
        selection: list[str] = []

        # Check for "all" keyword first
        if "all" in output_lower and (
            "generate: all" in output_lower
            or "i'll generate: all" in output_lower
            or "generate all" in output_lower
        ):
            return ["user_stories", "ppt", "prototype", "ui_design"]

        if "user stor" in output_lower:
            selection.append("user_stories")
        if (
            "ppt" in output_lower
            or "powerpoint" in output_lower
            or "presentation" in output_lower
            or "slide" in output_lower
        ):
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
        """Compile all phase outputs into the 10-key Final_Output structure.

        Ported verbatim from ``AgentOrchestrator._compile_final_output``. The
        key set + the per-section resolution rules are load-bearing (the chat
        frontend reads exactly these 10 keys):
          - ``auth`` / ``realtime`` / ``dashboard`` → static, not tied to a phase
            (``context.get(section)`` → ``None`` in practice);
          - a phase that produced output → its ``context[section]`` value
            (``{"output": text}`` or the JSON-parsed object for phases 4/5/7);
          - ``discovery`` / ``requirements`` / ``ui_preview`` always run → ``None``
            if somehow missing;
          - a phase SKIPPED by Output_Selection → ``{"status": "skipped", "value": None}``;
          - a failed phase carries ``{"status": "failed", "error": …}`` (already in
            ``context[section]`` from the per-phase except block).
        """
        # All possible sections with their phase mappings
        section_phase_map: dict[str, int | None] = {
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

        output_data: dict = {}

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

    # -----------------------------------------------------------------------
    # Context / mode threading — compose the single message string a
    # DeepAgentRunner consumes (the agent's system prompt is its AGENT.md body).
    # -----------------------------------------------------------------------

    @staticmethod
    def _compose_message(user_message: str, context: dict) -> str:
        """Fold ``mode_prompt`` + the flattened prior-phase context into one string.

        ``DeepAgentRunner.astream`` takes a single message string, so the
        information the legacy ``BaseAgent._build_messages`` spread across the
        system prompt (``mode_prompt``) and a "context from previous phases"
        human turn is composed here into ONE message. The prior-phase block uses
        the SAME filter + rendering the legacy used: every context key EXCEPT the
        ``mode`` / ``mode_prompt`` bookkeeping keys, rendered as ``"{key}: {value}"``
        (so a dict value like ``{"output": …}`` stringifies identically, and
        ``output_selection`` is included just as the legacy included it).

        Functional parity (the agent receives mode + prior outputs), NOT byte
        parity, is the requirement — the golden test mocks the LLM, so the
        composed string is never asserted; only the EVENT contract is.
        """
        parts: list[str] = []

        mode_prompt = context.get("mode_prompt")
        if mode_prompt:
            parts.append(mode_prompt)

        # Mirror BaseAgent._build_messages exactly: exclude only the mode/
        # mode_prompt bookkeeping keys; everything else (discovery, requirements,
        # prior phase outputs, output_selection) is rendered into the block.
        filtered_context = {
            k: v
            for k, v in context.items()
            if k not in ("mode", "mode_prompt")
        }
        if filtered_context:
            context_str = "\n".join(
                f"{key}: {value}" for key, value in filtered_context.items()
            )
            parts.append(f"Here is the context from previous phases:\n{context_str}")

        parts.append(user_message)
        return "\n\n".join(parts)

    # -----------------------------------------------------------------------
    # The sequencer — yields the legacy WS event vocabulary.
    # -----------------------------------------------------------------------

    async def astream_execute(
        self,
        user_message: str,
        chat_session_id: str | None = None,
        mode: str = "default",
        mode_prompt: str = "",
    ) -> AsyncGenerator[dict, None]:
        """Run the full chat pipeline, yielding StreamMessage-like dicts.

        Reproduces ``AgentOrchestrator.astream_execute`` event-for-event. Yields
        dicts with keys ``{type, chunk, section, data}``.

        Args:
            user_message: The user's input message.
            chat_session_id: Optional chat session id (tracking only; unused here,
                kept for signature parity with the legacy orchestrator).
            mode: The chat mode selected by the user (e.g. ``"thinking"``).
            mode_prompt: The mode-specific system-prompt enhancement.
        """
        context: dict = {}
        output_selection: list[str] = []

        # Inject mode context so agents are aware of the mode (mirrors legacy).
        if mode_prompt:
            context["mode"] = mode
            context["mode_prompt"] = mode_prompt

        # ── Phase 0: Discovery ────────────────────────────────────────────
        yield {"type": "phase_start", "section": "discovery", "chunk": None,
               "data": {"phase": 0, "name": "Discovery"}}
        try:
            logger.info("Chat Phase 0: Starting Discovery (streaming)")
            discovery_output_parts: list[str] = []
            async for chunk in self._runner_for_phase(0).astream(
                self._compose_message(user_message, context)
            ):
                discovery_output_parts.append(chunk)
                yield {"type": "stream", "chunk": chunk, "section": "discovery", "data": None}

            discovery_output = "".join(discovery_output_parts)
            context["discovery"] = {"output": discovery_output}
            output_selection = self._parse_output_selection(discovery_output)
            context["output_selection"] = output_selection
            logger.info("Chat Phase 0: Complete. Output_Selection: %s", output_selection)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            from app.agents.llm_errors import map_exception
            logger.error("Chat Phase 0 (Discovery) failed: %s", e)
            context["discovery"] = {"status": "failed", "error": str(e)}
            output_selection = ["user_stories", "ppt", "prototype", "ui_design"]
            context["output_selection"] = output_selection
            payload = map_exception(e)
            yield {
                "type": "error",
                "chunk": None,
                "section": "discovery",
                "data": {
                    "error": payload.message,
                    "code": payload.code,
                    "recoverable": payload.recoverable,
                    "phase": 0,
                },
            }
        yield {"type": "phase_end", "section": "discovery", "chunk": None, "data": {"phase": 0}}

        # ── Phase 1: Requirements ─────────────────────────────────────────
        yield {"type": "phase_start", "section": "requirements", "chunk": None,
               "data": {"phase": 1, "name": "Requirements"}}
        try:
            logger.info("Chat Phase 1: Starting Requirements (streaming)")
            requirements_parts: list[str] = []
            async for chunk in self._runner_for_phase(1).astream(
                self._compose_message(user_message, context)
            ):
                requirements_parts.append(chunk)
                yield {"type": "stream", "chunk": chunk, "section": "requirements", "data": None}

            requirements_output = "".join(requirements_parts)
            context["requirements"] = {"output": requirements_output}
            logger.info("Chat Phase 1: Complete")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            from app.agents.llm_errors import map_exception
            logger.error("Chat Phase 1 (Requirements) failed: %s", e)
            context["requirements"] = {"status": "failed", "error": str(e)}
            payload = map_exception(e)
            yield {
                "type": "error",
                "chunk": None,
                "section": "requirements",
                "data": {
                    "error": payload.message,
                    "code": payload.code,
                    "recoverable": payload.recoverable,
                    "phase": 1,
                },
            }
        yield {"type": "phase_end", "section": "requirements", "chunk": None, "data": {"phase": 1}}

        # ── Phase 2: Conditional Routing (no events; computes active phases) ──
        active_phases = self._determine_active_phases(output_selection)
        logger.info("Chat Phase 2: Routing. Active phases: %s", active_phases)

        # ── Phases 3-7: Sequential execution of selected phases ───────────
        for phase in active_phases:
            section = self.PHASE_SECTIONS.get(phase)
            if section is None:
                continue

            runner = self._runner_for_phase(phase)
            if runner is None:
                continue

            yield {"type": "phase_start", "section": section, "chunk": None,
                   "data": {"phase": phase, "name": section}}
            try:
                logger.info("Chat Phase %s: Starting (%s) (streaming)", phase, section)
                phase_parts: list[str] = []
                async for chunk in runner.astream(
                    self._compose_message(user_message, context)
                ):
                    phase_parts.append(chunk)
                    yield {"type": "stream", "chunk": chunk, "section": section, "data": None}

                phase_output = "".join(phase_parts)

                # Try to parse JSON for structured sections (ppt=4/prototype=5/preview=7).
                if phase in (4, 5, 7):
                    try:
                        context[section] = json.loads(phase_output)
                    except (json.JSONDecodeError, TypeError):
                        context[section] = {"output": phase_output}
                else:
                    context[section] = {"output": phase_output}

                logger.info("Chat Phase %s: Complete (%s)", phase, section)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                from app.agents.llm_errors import map_exception
                logger.error("Chat Phase %s (%s) failed: %s", phase, section, e)
                context[section] = {"status": "failed", "error": str(e)}
                payload = map_exception(e)
                yield {
                    "type": "error",
                    "chunk": None,
                    "section": section,
                    "data": {
                        "error": payload.message,
                        "code": payload.code,
                        "recoverable": payload.recoverable,
                        "phase": phase,
                    },
                }
            yield {"type": "phase_end", "section": section, "chunk": None, "data": {"phase": phase}}

        # ── Compile Final_Output ──────────────────────────────────────────
        final_output = self._compile_final_output(context, output_selection)
        logger.info("Chat pipeline complete. Final_Output compiled.")

        yield {
            "type": "complete",
            "chunk": None,
            "section": None,
            "data": final_output.model_dump(),
        }
