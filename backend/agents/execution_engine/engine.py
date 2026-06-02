"""agents/execution_engine/engine.py — Universal Execution Engine (Phase 2).

The single entry point replacing WorkflowOrchestrator.execute(),
run_od_prototype_pipeline, and run_od_ppt_pipeline.

Phase 2 responsibilities:
  1. Validate the Workflow DAG via WorkflowResolver (halt if unsatisfiable)
  2. Prepend and run the Deep_Planner_Agent (15s timeout, default PROCEED)
  3. Evaluate the gate verdict; invoke ClarifyEngine if CLARIFY_REQUIRED
  4. Run domain agents in topological order
  5. Emit all WS events using the existing envelope shape
  6. Validation_Gate blocking (soft block — emit validation_gate_blocked, pause)
  7. ArtifactStoreWriteError propagation (do not mark step complete)
  8. Missing-template error (halt before any agent executes)

Phase 3 will add: planning_context injection, agent_input events,
DB-backed artifacts, lineage, revision intelligence, restart resumability.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from agents.artifact_store.store import ArtifactStoreWriteError, get_artifact_store
from agents.execution_engine.resolver import WorkflowResolver
from agents.execution_engine.state_machine import get_state_machine
from agents.factory import AgentContext, create_agent
from app.agents.base import TokenUsage
from app.agents.deep_agent import DeepAgent
from app.agents.tools.workspace import AgentWorkspace

logger = logging.getLogger("agents.execution_engine.engine")

# ---------------------------------------------------------------------------
# Structured JSON logging helper (FR-023 / T076)
# ---------------------------------------------------------------------------


def _log_event(
    event_type: str,
    pipeline_run_id: str,
    agent_id: str | None = None,
    duration_ms: float | None = None,
    error: str | None = None,
    **extra: object,
) -> None:
    """Emit a structured JSON log entry for a lifecycle event (FR-023 / SC-013).

    Every entry includes: timestamp, pipeline_run_id, event_type.
    Optional: agent_id, duration_ms, error.
    """
    import json as _json
    entry: dict = {
        "timestamp": _now(),
        "pipeline_run_id": pipeline_run_id,
        "event_type": event_type,
    }
    if agent_id is not None:
        entry["agent_id"] = agent_id
    if duration_ms is not None:
        entry["duration_ms"] = round(duration_ms, 2)
    if error is not None:
        entry["error"] = error
    entry.update(extra)
    logger.info("LIFECYCLE %s", _json.dumps(entry))

PLANNER_TIMEOUT_SECONDS = 20.0  # SmartPlanner: single call, 2-5s typical
PLANNER_AGENT_ID = "deep-planner"

# ── Human-in-the-loop: always ask clarifying questions ────────────────────────
# When True, the gate verdict is forced to CLARIFY_REQUIRED for every pipeline
# run regardless of what the planner returns. Set to False to let the planner
# decide autonomously.
ALWAYS_CLARIFY = True


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class ExecutionEngine:
    """Universal Execution Engine — single entry point for all workflows."""

    def __init__(self) -> None:
        self._resolver = WorkflowResolver()
        self._store = get_artifact_store()
        self._state_machine = get_state_machine()

    async def execute(
        self,
        agents: list,
        user_message: str,
        pipeline_run_id: str,
        pipeline_type: str = "custom",
        cancel_event: asyncio.Event | None = None,
        user_id: str | None = None,
        attached_skills: list[dict] | None = None,
        attached_hooks: list[dict] | None = None,
        model_id: str | None = None,
        od_context: dict | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Execute a workflow end-to-end, yielding WebSocket events.

        Args:
            agents: list[AgentSpec] resolved from PIPELINE_AGENTS[pipeline_type].
            user_message: The user brief.
            pipeline_run_id: UUID for this run.
            pipeline_type: Pipeline type label.
            cancel_event: Optional cancellation signal.
            user_id: Authenticated user ID (session_id). Forwarded to the disk
                     skill loader so per-user SKILL.md overrides are honoured.
            attached_skills / attached_hooks: UI-attached extras.
            model_id: User-selected model override.
            od_context: For od_prototype/od_ppt — loaded template/design-system
                        content passed through to the factory `injects` composer.
        """
        total_start = time.time()
        workspace = AgentWorkspace()
        self._od_context = od_context  # threaded into AgentContext per agent
        self._user_id = user_id

        # Create a shared ArtifactStore for prototype pipelines.
        # All four prototype agents (builder, polisher, finalizer, etc.) share
        # the same store so emit_artifact() in one agent is readable by the next.
        self._prototype_store = None
        if pipeline_type in ("od_prototype", "prototype", "prototype_revision"):
            from agents.prototype.artifact_store import PrototypeArtifactStore
            self._prototype_store = PrototypeArtifactStore()

        # Load per-user disk skills for all agents (user → global → built-in).
        # Honours per-user SKILL.md overrides — replicates the behaviour of the
        # former WorkflowOrchestrator._load_skills (WORKFLOWS.md §B6).
        self._disk_skills = self._load_disk_skills(agents, user_id)

        # ── Step 1: Validate the DAG ──────────────────────────────────────
        validation = self._resolver.validate(agents)
        yield {
            "type": "workflow_validated",
            "data": {
                "pipeline_run_id": pipeline_run_id,
                "satisfiable": validation.satisfiable,
                "dag_edges": [
                    {"from": e.from_agent_id, "to": e.to_agent_id, "artifact_type": e.artifact_type}
                    for e in validation.edges
                ],
                "unresolved_edges": [
                    {"consuming_agent_id": u.consuming_agent_id, "artifact_type": u.artifact_type}
                    for u in validation.unresolved_edges
                ],
                "timestamp": _now(),
            },
        }
        if not validation.satisfiable:
            yield {
                "type": "error",
                "data": {
                    "error": "Workflow DAG is unsatisfiable: " + "; ".join(validation.errors),
                    "code": "workflow_unsatisfiable",
                    "recoverable": False,
                },
            }
            return

        ordered_agents = validation.dag or list(agents)

        # Persist custom workflow definition (T061, FR-013)
        await self._persist_workflow_definition(
            user_id=user_id,
            pipeline_type=pipeline_type,
            agents=ordered_agents,
            validation_result=validation,
        )

        # ── Step 2: Run the Deep_Planner_Agent (gate) ─────────────────────
        self._state_machine.transition(pipeline_run_id, "planning")
        _log_event("workflow_run_created", pipeline_run_id, pipeline_type=pipeline_type)

        # ── Prototype pipelines (Approach 2+3): skip planner + clarifier ──
        # The prototype-specify agent handles planning and clarification as
        # part of its spec generation phase. Running the planner/clarifier
        # before it is redundant and adds unnecessary latency.
        from agents.prototype.pipeline import SKIP_PLANNER_FOR_PROTOTYPE, is_prototype_pipeline
        skip_planner = SKIP_PLANNER_FOR_PROTOTYPE and is_prototype_pipeline(pipeline_type)

        if skip_planner:
            logger.info("Prototype pipeline (Approach 2+3): skipping planner + clarifier")
            planning_context = self._default_planning_context(user_message)
            planning_context["pipeline_type"] = pipeline_type
            gate_verdict = "PROCEED"
            # Don't emit planner events — no overlay, no flash
        else:
            # Emit planner_start BEFORE running the planner so the frontend
            # can show a "planning…" overlay immediately.
            yield {
                "type": "planner_start",
                "data": {"pipeline_run_id": pipeline_run_id, "pipeline_type": pipeline_type, "timestamp": _now()},
            }

            planner_start_ms = time.time() * 1000
            planning_context, gate_verdict = await self._run_planner(
                user_message, pipeline_run_id, model_id, cancel_event, pipeline_type
            )

            # Human-in-the-loop override: force clarification on every run.
            if ALWAYS_CLARIFY and gate_verdict != "CLARIFY_REQUIRED":
                logger.info("ALWAYS_CLARIFY=True — overriding gate verdict PROCEED → CLARIFY_REQUIRED")
                gate_verdict = "CLARIFY_REQUIRED"
                planning_context["execution_gate"] = "CLARIFY_REQUIRED"
                if not planning_context.get("missing_information"):
                    has_topic = planning_context.get("has_topic", True)
                    _pipeline_defaults: dict[str, list[str]] = {
                        "od_ppt":        ["target_audience", "tone_and_style", "key_objectives", "slide_count"],
                        "ppt":           ["target_audience", "tone_and_style", "key_objectives", "slide_count"],
                        "od_prototype":  ["target_audience", "scope", "priority", "style"],
                        "prototype":     ["target_audience", "scope", "priority", "style"],
                        "user_stories":  ["target_audience", "scope", "priority", "technology"],
                        "app_builder":   ["technology", "scope", "target_audience", "security"],
                        "mulesoft_to_springboot": ["scope", "technology", "timeline", "priority"],
                        "dotnet_to_azure":        ["scope", "technology", "timeline", "priority"],
                        "custom":        ["target_audience", "key_objectives", "scope", "priority"],
                    }
                    defaults = _pipeline_defaults.get(pipeline_type, _pipeline_defaults["custom"])
                    if not has_topic:
                        defaults = ["topic"] + defaults
                    planning_context["missing_information"] = defaults
                    logger.info(
                        "ALWAYS_CLARIFY: seeding defaults has_topic=%s pipeline=%s: %s",
                        has_topic, pipeline_type, defaults
                    )

            _log_event(
                "planner_complete", pipeline_run_id,
                duration_ms=(time.time() * 1000 - planner_start_ms),
                gate_verdict=gate_verdict,
            )

            # Auto-generate PLANNER.md per run (T082)
            if planning_context and not planning_context.get("planner_timed_out"):
                try:
                    planner_md_lines = ["# PLANNER.md — Deep Planner Analysis\n"]
                    if planning_context.get("inferred_intent"):
                        planner_md_lines.append(f"**Inferred Intent**: {planning_context['inferred_intent']}\n")
                    if planning_context.get("topic"):
                        planner_md_lines.append(f"**Topic**: {planning_context['topic']}\n")
                    if planning_context.get("execution_gate"):
                        planner_md_lines.append(f"**Gate Verdict**: {planning_context['execution_gate']}\n")
                    if planning_context.get("explicit_constraints"):
                        planner_md_lines.append("\n**Explicit Constraints**:\n" +
                            "\n".join(f"- {c}" for c in planning_context["explicit_constraints"]))
                    if planning_context.get("implicit_constraints"):
                        planner_md_lines.append("\n**Implicit Constraints**:\n" +
                            "\n".join(f"- {c}" for c in planning_context["implicit_constraints"]))
                    if planning_context.get("quality_targets"):
                        planner_md_lines.append("\n**Quality Targets**:\n" +
                            "\n".join(f"- {q}" for q in planning_context["quality_targets"]))
                    if planning_context.get("inferred_personas"):
                        planner_md_lines.append("\n**Inferred Personas**:\n" +
                            "\n".join(f"- {p}" for p in planning_context["inferred_personas"]))
                    if planning_context.get("inferred_nfrs"):
                        planner_md_lines.append("\n**Non-Functional Requirements**:\n" +
                            "\n".join(f"- {n}" for n in planning_context["inferred_nfrs"]))
                    if planning_context.get("domain_insights"):
                        planner_md_lines.append("\n**Domain Insights**:\n" +
                            "\n".join(f"- {i}" for i in planning_context["domain_insights"]))
                    workspace.write_file("PLANNER.md", "\n".join(planner_md_lines))
                except Exception as _planner_md_exc:
                    logger.debug("PLANNER.md generation failed: %s", _planner_md_exc)
            async for event in self._emit_planner_events(
                pipeline_run_id, pipeline_type, planning_context, gate_verdict
            ):
                yield event

        # ── Step 3: Gate routing ──────────────────────────────────────────
        if gate_verdict == "CLARIFY_REQUIRED":
            self._state_machine.transition(pipeline_run_id, "clarifying")
            from agents.execution_engine.clarify_engine import ClarifyEngine

            clarify = ClarifyEngine()

            # Use a Queue so ClarifyEngine events (questionnaire_ready, etc.)
            # are streamed to the client in real-time while clarify.run()
            # is suspended at event.wait(). The previous _ws_collect pattern
            # buffered events and only yielded them AFTER clarify.run() returned
            # — which meant questionnaire_ready was never sent until after the
            # user had already answered (impossible: they couldn't see questions).
            event_queue: asyncio.Queue[dict | None] = asyncio.Queue()

            async def _ws_send(event: dict) -> None:
                await event_queue.put(event)

            self._state_machine.transition(pipeline_run_id, "waiting_for_user")

            # Run clarify.run() as a background task so we can yield its
            # events concurrently from the queue.
            clarify_task = asyncio.create_task(
                clarify.run(pipeline_run_id, planning_context, _ws_send)
            )

            # Drain the queue until clarify_task completes
            while not clarify_task.done():
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                    if event is not None:
                        yield event
                except asyncio.TimeoutError:
                    continue

            # Drain any remaining events after task completion
            while not event_queue.empty():
                event = event_queue.get_nowait()
                if event is not None:
                    yield event

            # Get the updated planning_context from the completed task
            try:
                planning_context = clarify_task.result()
            except Exception as _clarify_exc:
                logger.warning("ClarifyEngine failed: %s — proceeding with original context", _clarify_exc)

        # ── Step 4: Run domain agents ─────────────────────────────────────
        self._state_machine.transition(pipeline_run_id, "generating")

        yield {
            "type": "pipeline_start",
            "data": {
                "pipeline_type": pipeline_type,
                "pipeline_run_id": pipeline_run_id,
                "agent_count": len(ordered_agents),
                "agents": [
                    {"id": s.id, "name": s.name, "role": s.role, "icon": s.icon,
                     "order": getattr(s, "order", 0)}
                    for s in ordered_agents
                ],
            },
        }

        accumulated_outputs: dict[str, str] = {}
        results: list[dict] = []

        try:
            for i, spec in enumerate(ordered_agents):
                if cancel_event and cancel_event.is_set():
                    logger.info("Workflow cancelled before agent %s", spec.id)
                    break

                # ── Task-loop agents: call repeatedly until all tasks done ──
                # The prototype-build agent executes one task per call.
                # We call it N times (once per task) so each call is small
                # and focused — never runs out of tokens filling all pages.
                if getattr(spec, "id", None) == "prototype-build":
                    async for event in self._run_build_task_loop(
                        spec, i, ordered_agents, user_message, accumulated_outputs,
                        workspace, pipeline_run_id, pipeline_type, planning_context,
                        attached_skills, attached_hooks, model_id, results, cancel_event,
                    ):
                        yield event
                else:
                    async for event in self._run_agent(
                        spec, i, ordered_agents, user_message, accumulated_outputs,
                        workspace, pipeline_run_id, pipeline_type, planning_context,
                        attached_skills, attached_hooks, model_id, results, cancel_event,
                    ):
                        yield event

        except asyncio.CancelledError:
            self._state_machine.transition(pipeline_run_id, "cancelled")
            yield {"type": "pipeline_cancelled", "data": {"pipeline_run_id": pipeline_run_id}}
            raise

        # ── Step 5: Pipeline complete ─────────────────────────────────────
        # Guard: if the run was already cancelled (e.g. user rejected a review
        # gate), don't try to transition to "completed" — that would throw a
        # StateMachineError because "cancelled" is a terminal state.
        current_state = self._state_machine.get_state(pipeline_run_id)
        if current_state not in ("cancelled", "failed"):
            self._state_machine.transition(pipeline_run_id, "completed")

        # Determine final output:
        # - workspace.file_count() now excludes internal planning files (PLANNER.md)
        #   so it's > 0 only when domain agents actually wrote deliverable files
        #   (app_builder, mulesoft, dotnet code pipelines).
        # - For PPT / prototype / text pipelines, the last agent's streamed output
        #   IS the deliverable — workspace.file_count() == 0 for these.
        final_output = workspace.to_final_output() if workspace.file_count() > 0 else (
            results[-1]["output"] if results else ""
        )

        # For prototype pipelines: prefer the shared ArtifactStore HTML if available
        # (it's the clean HTML without the "✓ Artifact stored..." confirmation text).
        # Also strip <artifact>...</artifact> wrapper tags if present.
        proto_store = getattr(self, "_prototype_store", None)
        if proto_store is not None and hasattr(proto_store, "is_set") and proto_store.is_set():
            store_html = proto_store.html
            if store_html and len(store_html) > len(final_output):
                final_output = store_html

        # Strip <artifact>...</artifact> wrapper if present (finalizer wraps output)
        if final_output and "<artifact" in final_output:
            import re as _re
            m = _re.search(r"<artifact[^>]*>\s*([\s\S]*?)\s*</artifact>", final_output, _re.IGNORECASE)
            if m:
                final_output = m.group(1).strip()

        # ── Prototype revision: merge diff output back into original HTML ─
        # The revision agent outputs a structured diff (not the full HTML)
        # to stay within output token limits. We extract the original HTML
        # from the user_message and apply the diff sections to it.
        if pipeline_type == "prototype_revision" and final_output and "=== REVISION_DIFF ===" in final_output:
            final_output = self._apply_revision_diff(
                user_message=user_message,
                diff_output=final_output,
            )
        yield {
            "type": "pipeline_complete",
            "data": {
                "pipeline_type": pipeline_type,
                "pipeline_run_id": pipeline_run_id,
                "total_duration": round(time.time() - total_start, 2),
                "agents_completed": len(results),
                "agents_total": len(ordered_agents),
                "final_output": final_output,
            },
        }

    # ------------------------------------------------------------------
    # Deep Planner
    # ------------------------------------------------------------------

    async def _run_planner(
        self,
        user_message: str,
        pipeline_run_id: str,
        model_id: str | None,
        cancel_event: asyncio.Event | None,
        pipeline_type: str = "custom",
    ) -> tuple[dict, str]:
        """Run the Deep_Planner_Agent with a timeout. Returns (planning_context, gate)."""
        try:
            planning_context = await asyncio.wait_for(
                self._invoke_planner(user_message, model_id, pipeline_type),
                timeout=PLANNER_TIMEOUT_SECONDS,
            )
            gate = planning_context.get("execution_gate", "PROCEED")
            # Store the planning_context artifact
            try:
                await self._store.store(
                    run_id=pipeline_run_id,
                    artifact_type="planning_context",
                    name="planning_context",
                    content=json.dumps(planning_context),
                    producing_agent_id=PLANNER_AGENT_ID,
                )
            except ArtifactStoreWriteError as exc:
                logger.warning("planning_context store failed: %s", exc)
            return planning_context, gate
        except asyncio.TimeoutError:
            logger.warning("Deep planner timed out — defaulting to PROCEED")
            return self._default_planning_context(user_message, timed_out=True), "PROCEED"
        except Exception as exc:
            logger.exception("Deep planner failed — defaulting to PROCEED")
            ctx = self._default_planning_context(user_message)
            ctx["planner_error"] = str(exc)
            return ctx, "PROCEED"

    async def _invoke_planner(self, user_message: str, model_id: str | None, pipeline_type: str = "custom") -> dict:
        """Invoke the SmartPlanner — single structured LLM call, 2-5 seconds."""
        from agents.planner.smart_planner import SmartPlanner

        planner = SmartPlanner(model_id=model_id)
        return await planner.plan(user_message, pipeline_type)

    def _default_planning_context(self, user_message: str, timed_out: bool = False) -> dict:
        return {
            "inferred_intent": user_message[:200],
            "has_topic": len(user_message.split()) > 4,
            "topic": None,
            "explicit_constraints": [],
            "implicit_constraints": [],
            "missing_information": [],
            "execution_strategy": "sequential",
            "execution_gate": "PROCEED",
            "inferred_personas": [],
            "inferred_nfrs": [],
            "quality_targets": [],
            "domain_insights": [],
            "planner_timed_out": timed_out,
        }

    async def _emit_planner_events(
        self,
        pipeline_run_id: str,
        pipeline_type: str,
        planning_context: dict,
        gate_verdict: str,
    ) -> AsyncGenerator[dict, None]:
        # planner_start is emitted BEFORE _run_planner is called (in execute())
        # so the frontend sees it immediately. Only emit completion events here.
        if planning_context.get("planner_timed_out"):
            yield {
                "type": "planner_timeout",
                "data": {"pipeline_run_id": pipeline_run_id, "elapsed_seconds": PLANNER_TIMEOUT_SECONDS, "timestamp": _now()},
            }
        yield {
            "type": "planner_complete",
            "data": {
                "pipeline_run_id": pipeline_run_id,
                "planning_context": planning_context,
                "execution_gate": gate_verdict,
                "timestamp": _now(),
            },
        }
        yield {
            "type": "gate_status",
            "data": {"pipeline_run_id": pipeline_run_id, "verdict": gate_verdict, "timestamp": _now()},
        }

    # ------------------------------------------------------------------
    # Domain agent execution
    # ------------------------------------------------------------------

    async def _run_agent(
        self,
        spec,
        index: int,
        ordered_agents: list,
        user_message: str,
        accumulated_outputs: dict[str, str],
        workspace: AgentWorkspace,
        pipeline_run_id: str,
        pipeline_type: str,
        planning_context: dict,
        attached_skills: list[dict] | None,
        attached_hooks: list[dict] | None,
        model_id: str | None,
        results: list[dict],
        cancel_event: asyncio.Event | None,
    ) -> AsyncGenerator[dict, None]:
        """Run a single domain agent, yielding WS events."""
        # Guard: if the run is already in a terminal state (e.g. user rejected
        # a review gate), stop immediately without running the agent.
        current_state = self._state_machine.get_state(pipeline_run_id)
        if current_state in ("cancelled", "failed"):
            logger.info(
                "_run_agent: skipping %s — pipeline already in terminal state=%s",
                spec.id, current_state,
            )
            return

        agent_start = time.time()

        yield {
            "type": "agent_start",
            "data": {"agent_id": spec.id, "name": spec.name, "role": spec.role,
                     "icon": spec.icon, "index": index, "total": len(ordered_agents)},
        }
        _log_event("agent_start", pipeline_run_id, agent_id=spec.id)

        # Build context message from upstream outputs (consumes contract)
        context_message = self._build_context_message(
            spec, ordered_agents, user_message, accumulated_outputs,
            planning_context,
        )

        # Emit agent_input event (Phase 3 / T040) — shows full input prompt
        # and context sources in the Thinking tab (FR-015).
        context_sources = self._build_context_sources(spec, ordered_agents, accumulated_outputs)
        yield {
            "type": "agent_input",
            "data": {
                "agent_id": spec.id,
                "pipeline_run_id": pipeline_run_id,
                "timestamp": _now(),
                "context_message": context_message,
                "context_sources": context_sources,
                "tool_calls": [],
            },
        }

        try:
            # Merge disk-based skills into attached_skills for this agent.
            # UI-attached skills take priority; disk skill is appended after.
            merged_skills: list[dict] = list(attached_skills or [])
            disk_skills = getattr(self, "_disk_skills", {})
            if spec.id in disk_skills:
                merged_skills.append({"content": disk_skills[spec.id]})

            ctx = AgentContext(
                user_request=user_message,
                agent_outputs=self._filter_consumed_outputs(spec, ordered_agents, accumulated_outputs),
                attached_skills=merged_skills,
                attached_hooks=list(attached_hooks or []),
                workspace=workspace,
                model=model_id,
                od_context=getattr(self, "_od_context", None),
                planning_context=planning_context,
                user_id=getattr(self, "_user_id", None),
                prototype_store=getattr(self, "_prototype_store", None),
            )
            agent = create_agent(spec.id, ctx)

            output_chunks: list[str] = []
            use_deep = bool(spec.tools) and isinstance(agent, DeepAgent)

            # Per-agent timeout: estimated_duration * 6, capped per agent type.
            # Build agent: each task is one page, capped at 240s.
            # Validate agent: reads full HTML + fixes, capped at 300s.
            # Other tool agents: capped at 300s.
            # Text-only agents (tools=[]): capped at 180s.
            has_tools = bool(spec.tools)
            if spec.id == "prototype-build":
                agent_timeout = 240  # reads full HTML + fills one section, may take 2-3 min
            elif spec.id == "prototype-validate":
                agent_timeout = 300  # reads full HTML (60-80k), fixes all issues, emits
            else:
                agent_timeout = min(
                    max(getattr(spec, "estimated_duration", 30) * 6, 60),
                    300 if has_tools else 180,
                )

            async def _stream_agent() -> list[str]:
                chunks: list[str] = []
                if use_deep:
                    async for event in agent.astream_events(context_message):
                        if cancel_event and cancel_event.is_set():
                            raise asyncio.CancelledError()
                        etype = event["type"]
                        if etype == "chunk":
                            chunks.append(event["chunk"])
                        elif etype == "tool_call":
                            pass  # yielded below via separate path
                        elif etype == "tool_result":
                            pass
                    return chunks
                else:
                    async for item in agent.astream_with_usage(context_message):
                        if cancel_event and cancel_event.is_set():
                            raise asyncio.CancelledError()
                        if isinstance(item, TokenUsage):
                            break
                        chunks.append(item)
                    return chunks

            # Stream with live chunk events AND timeout guard
            timed_out = False
            agent_input_tokens = 0
            agent_output_tokens = 0
            if use_deep:
                try:
                    async with asyncio.timeout(agent_timeout):
                        async for event in agent.astream_events(context_message):
                            if cancel_event and cancel_event.is_set():
                                raise asyncio.CancelledError()
                            etype = event["type"]
                            if etype == "chunk":
                                output_chunks.append(event["chunk"])
                                yield {"type": "agent_chunk", "data": {"agent_id": spec.id, "chunk": event["chunk"]}}
                            elif etype == "usage":
                                agent_input_tokens += event.get("input_tokens", 0)
                                agent_output_tokens += event.get("output_tokens", 0)
                            elif etype == "tool_call":
                                yield {"type": "tool_call", "data": {"agent_id": spec.id, "tool": event["tool"], "args": event.get("args", {})}}
                            elif etype == "tool_result":
                                yield {"type": "tool_result", "data": {"agent_id": spec.id, "tool": event["tool"], "result": str(event.get("result", ""))[:500]}}
                                # ── Prototype task progress ──────────────────────────────
                                # When report_task_complete() is called, emit a task_progress
                                # event so the frontend can update the task checklist in real-time.
                                if event.get("tool") == "report_task_complete":
                                    proto_store = getattr(self, "_prototype_store", None)
                                    if proto_store is not None:
                                        yield {
                                            "type": "task_progress",
                                            "data": {
                                                "agent_id": spec.id,
                                                "pipeline_run_id": pipeline_run_id,
                                                "completed_tasks": proto_store.completed_tasks,
                                                "completed_count": proto_store.completed_task_count,
                                                "timestamp": _now(),
                                            },
                                        }
                except asyncio.TimeoutError:
                    timed_out = True
            else:
                try:
                    async with asyncio.timeout(agent_timeout):
                        async for item in agent.astream_with_usage(context_message):
                            if cancel_event and cancel_event.is_set():
                                raise asyncio.CancelledError()
                            if isinstance(item, TokenUsage):
                                agent_input_tokens = item.input_tokens or 0
                                agent_output_tokens = item.output_tokens or 0
                                break
                            output_chunks.append(item)
                            yield {"type": "agent_chunk", "data": {"agent_id": spec.id, "chunk": item}}
                except asyncio.TimeoutError:
                    timed_out = True

            if timed_out:
                logger.warning(
                    "Agent %s timed out after %.0fs — using best available output",
                    spec.id, agent_timeout,
                )
                # For tool-based agents: prefer whatever partial output was streamed
                # (may be partial HTML) over the previous agent's output (which may
                # be a spec/plan, not HTML). For text agents: fall back to previous.
                partial = "".join(output_chunks).strip()
                if partial and len(partial) > 500:
                    # Partial output is substantial — use it
                    output_chunks = [partial]
                    logger.info("Agent %s: using partial output (%d chars)", spec.id, len(partial))
                elif results:
                    fallback = results[-1].get("output", "")
                    output_chunks = [fallback] if fallback else output_chunks
                    logger.info("Agent %s: using previous agent output as fallback (%d chars)", spec.id, len(fallback))
                yield {
                    "type": "agent_error",
                    "data": {
                        "agent_id": spec.id,
                        "error": f"Agent timed out after {agent_timeout:.0f}s — using best available output",
                        "recoverable": True,
                    },
                }

            output = "".join(output_chunks)

            # ── Prototype pipeline: read HTML from shared ArtifactStore ──────
            # When a prototype agent calls emit_artifact(html=...), the HTML
            # goes into the tool args (not the text stream). The text stream
            # only gets "✓ Artifact stored: Prototype (X bytes)". We must read
            # the actual HTML from the shared store and use it as the output
            # so downstream agents receive the full HTML, not the confirmation.
            proto_store = getattr(self, "_prototype_store", None)
            if proto_store is not None and hasattr(proto_store, "is_set") and proto_store.is_set():
                html_from_store = proto_store.html
                if html_from_store and len(html_from_store) > len(output):
                    logger.info(
                        "Agent %s: using emit_artifact HTML (%d chars) instead of text output (%d chars)",
                        spec.id, len(html_from_store), len(output),
                    )
                    output = html_from_store

            accumulated_outputs[spec.id] = output

            # Summarize the agent output for use as downstream context (T075).
            # The summary replaces the full output in context_message for downstream
            # agents, reducing token usage while preserving all critical information.
            try:
                from app.agents.summarizer import summarize_agent_output
                summary = await summarize_agent_output(
                    agent_name=spec.name,
                    agent_role=spec.role,
                    pipeline_type=pipeline_type,
                    output=output,
                )
                # Store summary separately — full output still used for DB persistence
                if not hasattr(self, "_agent_summaries"):
                    self._agent_summaries: dict[str, str] = {}
                self._agent_summaries[spec.id] = summary
            except Exception as _sum_exc:
                logger.debug("Summarization failed for %s: %s", spec.id, _sum_exc)

            # Store the agent output as a typed artifact (if it produces any)
            for artifact_type in getattr(spec, "produces", []):
                try:
                    await self._store.store(
                        run_id=pipeline_run_id,
                        artifact_type=artifact_type,
                        name=f"{spec.id}_{artifact_type}",
                        content=output,
                        producing_agent_id=spec.id,
                    )
                except ArtifactStoreWriteError as exc:
                    # Do NOT mark step complete — surface error and fail the run
                    self._state_machine.transition(pipeline_run_id, "failed")
                    yield {
                        "type": "agent_error",
                        "data": {"agent_id": spec.id, "error": f"Artifact write failed: {exc}", "recoverable": False},
                    }
                    return

            duration = time.time() - agent_start
            agent_total_tokens = agent_input_tokens + agent_output_tokens
            results.append({
                "agent_id": spec.id, "name": spec.name, "role": spec.role,
                "icon": spec.icon, "output": output, "duration": duration,
                "input_tokens": agent_input_tokens, "output_tokens": agent_output_tokens,
                "total_tokens": agent_total_tokens,
            })
            _log_event("agent_complete", pipeline_run_id, agent_id=spec.id,
                       duration_ms=duration * 1000)
            yield {
                "type": "agent_complete",
                "data": {"agent_id": spec.id, "name": spec.name, "duration": round(duration, 2),
                         "output_length": len(output), "index": index, "total": len(ordered_agents),
                         "input_tokens": agent_input_tokens, "output_tokens": agent_output_tokens,
                         "total_tokens": agent_total_tokens},
            }

            # ── Human_Gate: pause for user review if agent declares gate ──
            # The agent's AGENT.md frontmatter declares `gate: Human_Gate`.
            # We pause here, emit review_gate_ready with the agent's output,
            # and wait for the user to approve (possibly with edits).
            # On approve: continue with (possibly edited) output.
            # On reject: cancel the pipeline.
            if getattr(spec, "gate", None) == "Human_Gate":
                async for gate_event in self._run_review_gate(
                    pipeline_run_id=pipeline_run_id,
                    agent_id=spec.id,
                    agent_name=spec.name,
                    output=output,
                    accumulated_outputs=accumulated_outputs,
                ):
                    if gate_event.get("type") == "_gate_rejected":
                        # User rejected — cancel the pipeline
                        # Guard: only transition if not already in a terminal state
                        current = self._state_machine.get_state(pipeline_run_id)
                        if current not in ("cancelled", "failed"):
                            self._state_machine.transition(pipeline_run_id, "cancelled")
                        yield {"type": "pipeline_cancelled", "data": {
                            "pipeline_run_id": pipeline_run_id,
                            "reason": f"User rejected output from {spec.name}",
                        }}
                        return
                    elif gate_event.get("type") == "_gate_edited":
                        # User edited the output — update accumulated_outputs
                        edited = gate_event.get("edited_content", output)
                        accumulated_outputs[spec.id] = edited
                        # Also update the last result
                        if results:
                            results[-1] = {**results[-1], "output": edited}
                    else:
                        yield gate_event

        except asyncio.CancelledError:
            raise
        except (FileNotFoundError, PermissionError) as exc:
            # Missing AGENT.md or template — fatal
            _log_event("agent_error", pipeline_run_id, agent_id=spec.id, error=str(exc))
            yield {"type": "agent_error", "data": {"agent_id": spec.id, "error": str(exc), "recoverable": False}}
        except Exception as exc:
            # If the run is already in a terminal state (cancelled/failed), don't
            # treat this as a recoverable error — re-raise so the pipeline stops.
            from agents.execution_engine.state_machine import StateMachineError
            if isinstance(exc, StateMachineError):
                current = self._state_machine.get_state(pipeline_run_id)
                if current in ("cancelled", "failed"):
                    logger.info(
                        "Agent %s: pipeline already in terminal state=%s — stopping",
                        spec.id, current,
                    )
                    return  # Stop the agent loop cleanly
            logger.exception("Agent %s failed", spec.id)
            _log_event("agent_error", pipeline_run_id, agent_id=spec.id, error=str(exc))
            yield {"type": "agent_error", "data": {"agent_id": spec.id, "error": str(exc), "recoverable": True}}
            accumulated_outputs[spec.id] = f"[Error: {exc}]"

    # ------------------------------------------------------------------
    # Build task loop — calls prototype-build once per task
    # ------------------------------------------------------------------

    async def _run_build_task_loop(
        self,
        spec,
        index: int,
        ordered_agents: list,
        user_message: str,
        accumulated_outputs: dict[str, str],
        workspace,
        pipeline_run_id: str,
        pipeline_type: str,
        planning_context: dict,
        attached_skills: list[dict] | None,
        attached_hooks: list[dict] | None,
        model_id: str | None,
        results: list[dict],
        cancel_event,
    ):
        """Counter-based build loop: calls prototype-build once per task.

        Extracts the task count from the planner output, then calls the
        build agent N times — once per task — passing the current task number
        and total count each time.
        """
        import re as _re

        plan_output = accumulated_outputs.get("prototype-plan", "")

        # Count tasks from the planner output (## Task N: headers)
        task_matches = _re.findall(r"^##\s+Task\s+(\d+)", plan_output, _re.MULTILINE)
        if not task_matches:
            # Fallback: try <tasks> wrapper
            tasks_section = _re.search(r"<tasks>([\s\S]*?)</tasks>", plan_output, _re.IGNORECASE)
            if tasks_section:
                task_matches = _re.findall(r"^##\s+Task\s+(\d+)", tasks_section.group(1), _re.MULTILINE)

        total_tasks = len(task_matches)
        if total_tasks == 0:
            logger.warning(
                "Build task loop: no tasks found in plan output (%d chars) — running once",
                len(plan_output),
            )
            total_tasks = 1

        logger.info(
            "Build task loop: %d tasks for pipeline=%s",
            total_tasks, pipeline_run_id,
        )

        for task_num in range(1, total_tasks + 1):
            if cancel_event and cancel_event.is_set():
                logger.info("Build task loop: cancelled at task %d", task_num)
                break

            # Guard: stop if pipeline was cancelled
            current_state = self._state_machine.get_state(pipeline_run_id)
            if current_state in ("cancelled", "failed"):
                logger.info(
                    "Build task loop: stopping at task %d — pipeline in terminal state=%s",
                    task_num, current_state,
                )
                break

            logger.info(
                "Build task loop: executing task %d/%d for pipeline=%s",
                task_num, total_tasks, pipeline_run_id,
            )

            # Inject task number so _build_context_message can pass it to the agent
            accumulated_outputs["_build_task_number"] = str(task_num)
            accumulated_outputs["_build_task_total"] = str(total_tasks)

            # Emit loop progress so frontend knows which task is running
            yield {
                "type": "task_loop_progress",
                "data": {
                    "agent_id": spec.id,
                    "pipeline_run_id": pipeline_run_id,
                    "task_number": task_num,
                    "total_tasks": total_tasks,
                    "timestamp": _now(),
                },
            }

            async for event in self._run_agent(
                spec, index, ordered_agents, user_message, accumulated_outputs,
                workspace, pipeline_run_id, pipeline_type, planning_context,
                attached_skills, attached_hooks, model_id, results, cancel_event,
            ):
                yield event

            # After each task: update accumulated HTML from artifact store
            proto_store = getattr(self, "_prototype_store", None)
            if proto_store is not None and proto_store.is_set():
                accumulated_outputs[spec.id] = proto_store.html
                logger.info(
                    "Build task loop: task %d/%d done — HTML=%d chars",
                    task_num, total_tasks, len(proto_store.html),
                )

        logger.info("Build task loop: finished %d tasks for pipeline=%s", total_tasks, pipeline_run_id)

    # ------------------------------------------------------------------
    # Review_Gate — Human review/edit/approve gate between agents
    # ------------------------------------------------------------------

    async def _run_review_gate(
        self,
        pipeline_run_id: str,
        agent_id: str,
        agent_name: str,
        output: str,
        accumulated_outputs: dict[str, str],
    ) -> AsyncGenerator[dict, None]:
        """Pause the pipeline for human review of an agent's output.

        Emits `review_gate_ready` with the agent's output.
        Waits for the user to call `approve_review` (via WebSocket).
        On approve: yields `review_gate_approved` and continues.
        On reject: yields `_gate_rejected` (internal signal to cancel).
        On edit+approve: yields `_gate_edited` with the new content.
        """
        gate_key = f"{pipeline_run_id}:{agent_id}"

        # Arm the event BEFORE emitting so a fast response doesn't miss it
        event = await self._store.get_review_event(gate_key)
        event.clear()

        # Guard: if the run is already in a terminal state (e.g. user rejected
        # a previous gate), don't open another gate — just signal rejection.
        current_state = self._state_machine.get_state(pipeline_run_id)
        if current_state in ("cancelled", "failed"):
            logger.info(
                "Review gate skipped: pipeline=%s agent=%s already in terminal state=%s",
                pipeline_run_id, agent_id, current_state,
            )
            yield {"type": "_gate_rejected"}
            return

        self._state_machine.transition(pipeline_run_id, "waiting_for_user")
        logger.info("Review gate opened: pipeline=%s agent=%s", pipeline_run_id, agent_id)

        yield {
            "type": "review_gate_ready",
            "data": {
                "pipeline_run_id": pipeline_run_id,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "gate_key": gate_key,
                "output": output,
                "timestamp": _now(),
            },
        }

        # Wait indefinitely for user response
        await event.wait()

        response = await self._store.get_review_response(gate_key)
        approved = response.get("approved", True) if response else True
        edited_content = response.get("edited_content") if response else None

        # Only transition back to generating if we're still in waiting_for_user.
        # If the user rejected (approved=False), we'll transition to cancelled below.
        if approved:
            self._state_machine.transition(pipeline_run_id, "generating")
        logger.info(
            "Review gate closed: pipeline=%s agent=%s approved=%s edited=%s",
            pipeline_run_id, agent_id, approved, edited_content is not None,
        )

        if not approved:
            yield {"type": "_gate_rejected"}
            return

        yield {
            "type": "review_gate_approved",
            "data": {
                "pipeline_run_id": pipeline_run_id,
                "agent_id": agent_id,
                "edited": edited_content is not None,
                "timestamp": _now(),
            },
        }

        if edited_content is not None:
            yield {"type": "_gate_edited", "edited_content": edited_content}

    # ------------------------------------------------------------------
    # Backend-restart resumability (T069)
    # ------------------------------------------------------------------

    async def restore_non_terminal_runs(self) -> None:
        """Restore non-terminal WorkflowRuns on backend startup (FR-011 / T069).

        Scans workflow_runs for non-terminal states and re-registers asyncio.Events
        in the ArtifactStore for runs in `waiting_for_user` state so they can be
        resumed by user action. Completes within 30 seconds of startup (SC-007).

        Called from the FastAPI @app.on_event('startup') handler (T070).
        """
        import asyncio  # noqa: F401 — used for asyncio.Event type annotation
        from datetime import datetime, timezone

        start = datetime.now(timezone.utc)
        logger.info("ExecutionEngine.restore_non_terminal_runs: scanning for paused runs…")

        try:
            from app.models.database import SessionLocal
            from app.models.workflow import WorkflowRun

            NON_TERMINAL = (
                "running", "planning", "clarifying", "waiting_for_user",
                "generating", "analyzing", "revising",
            )

            db = SessionLocal()
            try:
                stuck_runs = (
                    db.query(WorkflowRun)
                    .filter(WorkflowRun.status.in_(NON_TERMINAL))
                    .all()
                )
                restored = 0
                for wr in stuck_runs:
                    pipeline_run_id = getattr(wr, "pipeline_run_id", None)
                    if not pipeline_run_id:
                        continue
                    # Re-register the asyncio.Event so the run can be resumed
                    await self._store.get_resume_event(pipeline_run_id)
                    # Update state machine
                    try:
                        self._state_machine.transition(pipeline_run_id, wr.status)
                    except Exception:
                        pass
                    restored += 1

                elapsed = (datetime.now(timezone.utc) - start).total_seconds()
                logger.info(
                    "restore_non_terminal_runs: restored %d run(s) in %.2fs",
                    restored, elapsed,
                )
            finally:
                db.close()
        except Exception as exc:
            logger.warning("restore_non_terminal_runs failed: %s", exc)

    # ------------------------------------------------------------------
    # Custom Workflow persistence (T061)
    # ------------------------------------------------------------------

    async def _persist_workflow_definition(
        self,
        user_id: str | None,
        pipeline_type: str,
        agents: list,
        validation_result,
    ) -> str | None:
        """Persist a custom Workflow definition to the `workflows` table.

        Only persists when user_id is set and the pipeline_type is 'custom'
        or when the workflow was explicitly composed (not a standard pipeline).
        Returns the workflow definition ID, or None if not persisted.

        The 1–50 agent limit is enforced here (Deep_Planner_Agent is prepended
        automatically and does NOT count toward the limit).
        """
        if not user_id:
            return None

        # Only persist explicitly custom workflows (not standard pipeline types)
        from agents.registry import PIPELINE_AGENTS
        if pipeline_type in PIPELINE_AGENTS and pipeline_type != "custom":
            return None

        # Enforce 1–50 agent limit (Deep_Planner_Agent excluded)
        non_planner = [a for a in agents if a.id != "deep-planner"]
        if len(non_planner) > 50:
            logger.warning(
                "Custom workflow exceeds 50-agent limit (%d agents) — not persisted",
                len(non_planner),
            )
            return None

        try:
            import json as _json
            import uuid as _uuid
            from datetime import datetime, timezone as _tz
            from app.models.database import SessionLocal
            from app.models.workflow_definition import WorkflowDefinition

            agent_ids = [a.id for a in non_planner]
            artifact_edges = [
                {
                    "from_agent": e.from_agent_id,
                    "to_agent": e.to_agent_id,
                    "artifact_type": e.artifact_type,
                }
                for e in validation_result.edges
            ]

            db = SessionLocal()
            try:
                wf = WorkflowDefinition(
                    id=str(_uuid.uuid4()),
                    user_id=user_id,
                    name=f"{pipeline_type} workflow",
                    agents=_json.dumps(agent_ids),
                    artifact_edges=_json.dumps(artifact_edges),
                    created_at=datetime.now(_tz.utc),
                    updated_at=datetime.now(_tz.utc),
                )
                db.add(wf)
                db.commit()
                db.refresh(wf)
                logger.info(
                    "Custom workflow persisted: id=%s agents=%d",
                    wf.id, len(agent_ids),
                )
                return wf.id
            finally:
                db.close()
        except Exception as exc:
            logger.warning("Failed to persist workflow definition: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Revision intelligence (T053)
    # ------------------------------------------------------------------

    async def _handle_revision(
        self,
        parent_run_id: str,
        target_artifact_type: str,
        instruction: str,
        pipeline_run_id: str,
        websocket_send_fn,
        model_id: str | None = None,
    ) -> None:
        """Handle a revision request (FR-014).

        Retrieves the original Artifact, version history, and instruction as
        three separate structured inputs (NOT concatenated). Stores the result
        as a new Artifact version with derived_from_artifact_id.

        Raises ValueError for invalid inputs (empty instruction, missing artifact).
        """
        if not instruction or not instruction.strip():
            raise ValueError("Revision instruction must not be empty.")

        # Retrieve the original artifact
        original = await self._store.retrieve_latest(parent_run_id, target_artifact_type)
        if original is None:
            raise ValueError(
                f"No artifact of type {target_artifact_type!r} found for run {parent_run_id!r}. "
                "Revision MUST NOT proceed without original context (FR-014)."
            )

        # Retrieve version history
        version_history = await self._store.list_by_type(parent_run_id, target_artifact_type)

        # Check if parent run predates Phase 3 (no planning_context artifact)
        planning_context_artifact = await self._store.retrieve_latest(parent_run_id, "planning_context")
        planning_context_unavailable = planning_context_artifact is None

        # Build the three separate structured inputs (NOT concatenated)
        original_content = original["content"]
        history_summary = f"{len(version_history)} version(s) exist for this artifact."

        # Compose the revision context message with three clearly separated sections
        revision_context = (
            f"=== ORIGINAL ARTIFACT (type: {target_artifact_type}) ===\n"
            f"{original_content}\n"
            f"=== END ORIGINAL ARTIFACT ===\n\n"
            f"=== VERSION HISTORY ===\n"
            f"{history_summary}\n"
            f"=== END VERSION HISTORY ===\n\n"
            f"=== REVISION INSTRUCTION ===\n"
            f"{instruction}\n"
            f"=== END REVISION INSTRUCTION ==="
        )

        # If planning_context is available, prepend it as a guardrail
        if planning_context_artifact:
            revision_context = (
                f"=== PLANNING CONTEXT (original run guardrail) ===\n"
                f"{planning_context_artifact['content']}\n"
                f"=== END PLANNING CONTEXT ===\n\n"
            ) + revision_context

        # Run the appropriate revision agent (use the pipeline's revision type)
        # For now, emit the revision as a single-agent pipeline
        await websocket_send_fn({
            "type": "pipeline_start",
            "data": {
                "pipeline_type": f"{target_artifact_type}_revision",
                "pipeline_run_id": pipeline_run_id,
                "agent_count": 1,
                "agents": [{"id": "revision-agent", "name": "Revision Agent",
                             "role": "Intelligent Revision", "icon": "✏️", "order": 1}],
            },
        })

        # Store the revision result as a new artifact version
        # (In a full implementation, this would run a DeepAgent revision loop)
        # For Phase 3, we store the instruction + context as the revision artifact
        # and mark it with derived_from_artifact_id
        try:
            new_artifact_id = await self._store.store(
                run_id=pipeline_run_id,
                artifact_type=target_artifact_type,
                name=f"{target_artifact_type}_revision",
                content=revision_context,
                producing_agent_id="revision-agent",
                derived_from_id=original["id"],
            )
            logger.info(
                "Revision stored: parent_run=%s type=%s new_artifact=%s planning_unavailable=%s",
                parent_run_id, target_artifact_type, new_artifact_id, planning_context_unavailable,
            )
        except ArtifactStoreWriteError as exc:
            await websocket_send_fn({
                "type": "state_restoration_failed",
                "data": {
                    "pipeline_run_id": pipeline_run_id,
                    "parent_run_id": parent_run_id,
                    "error": str(exc),
                    "timestamp": _now(),
                },
            })
            return

        await websocket_send_fn({
            "type": "pipeline_complete",
            "data": {
                "pipeline_type": f"{target_artifact_type}_revision",
                "pipeline_run_id": pipeline_run_id,
                "total_duration": 0.0,
                "agents_completed": 1,
                "agents_total": 1,
                "final_output": revision_context,
                "planning_context_unavailable": planning_context_unavailable,
            },
        })

    def _build_context_sources(        self,
        spec,
        ordered_agents: list,
        accumulated_outputs: dict[str, str],
    ) -> list[dict]:
        """Build the context_sources list for the agent_input event (FR-015).

        For each upstream agent whose output is consumed, records:
        - type: "summary" (text output) or "artifact" (typed artifact)
        - agent_id, agent_name, summary_length, full_output_length
        """
        sources: list[dict] = []
        consumed = self._filter_consumed_outputs(spec, ordered_agents, accumulated_outputs)
        for aid, output in consumed.items():
            prev = next((s for s in ordered_agents if s.id == aid), None)
            sources.append({
                "type": "summary",
                "agent_id": aid,
                "agent_name": prev.name if prev else aid,
                "summary_length": len(output),
                "full_output_length": len(output),
            })
        return sources

    def _load_disk_skills(self, agents: list, user_id: str | None) -> dict[str, str]:
        """Load disk-based skill content for every agent (user → global → built-in).

        Forwards user_id to get_skill_content so per-user SKILL.md overrides
        win over admin global / built-in defaults (WORKFLOWS.md §B6). Returns
        {agent_id: skill_content} for agents that have any skill.
        """
        from app.agents.skills import get_skill_content

        skills: dict[str, str] = {}
        for spec in agents:
            try:
                content = get_skill_content(spec.id, user_id=user_id)
            except Exception:
                content = None
            if content:
                skills[spec.id] = content
        return skills

    def _filter_consumed_outputs(
        self, spec, ordered_agents: list, accumulated_outputs: dict[str, str]
    ) -> dict[str, str]:
        """Return only the upstream outputs whose produces match this agent's consumes."""
        consumes = set(getattr(spec, "consumes", []))
        if not consumes:
            return {}
        filtered: dict[str, str] = {}
        for upstream in ordered_agents:
            if upstream.id == spec.id:
                break
            # Skip internal engine markers (not real agent outputs)
            if upstream.id.startswith("_"):
                continue
            produced = set(getattr(upstream, "produces", []))
            if produced & consumes and upstream.id in accumulated_outputs:
                filtered[upstream.id] = accumulated_outputs[upstream.id]
        return filtered

    def _build_context_message(
        self,
        spec,
        ordered_agents: list,
        user_message: str,
        accumulated_outputs: dict[str, str],
        planning_context: dict,
    ) -> str:
        """Build the context message (user request + consumed upstream outputs).

        Phase 3 (FR-016): planning_context is injected cross-cutting to ALL agents.
        For od_ppt / od_prototype agents that declare `injects`, the template body
        and example HTML are also injected into the user message — the AGENT.md
        prompts explicitly expect them there (ACTIVE TEMPLATE, TEMPLATE EXAMPLE).

        Chain context (=== CONTEXT FROM PREVIOUS PIPELINE ===) is only shown to
        the FIRST agent in the pipeline — it interprets the brief. Downstream
        agents already receive the first agent's structured output (spec/HTML)
        via accumulated_outputs, so the raw chain context is noise for them.
        """
        # Determine if this is the first agent in the pipeline
        is_first_agent = (len(ordered_agents) == 0 or spec.id == ordered_agents[0].id)

        # For downstream agents, strip the chain context block from user_message
        # to avoid polluting their input with the full previous pipeline output.
        # Keep only the clean brief (everything before the first === CONTEXT === block).
        if not is_first_agent and "=== CONTEXT FROM PREVIOUS PIPELINE" in user_message:
            clean_brief = user_message.split("\n\n=== CONTEXT FROM PREVIOUS PIPELINE")[0].strip()
            effective_message = clean_brief
        else:
            effective_message = user_message

        parts = [f"=== ORIGINAL USER REQUEST ===\n{effective_message}\n=== END REQUEST ==="]

        # Inject planning_context for ALL pipelines (cross-cutting guardrail, FR-016)
        if planning_context and not planning_context.get("planner_timed_out"):
            intent = planning_context.get("inferred_intent", "")
            constraints = planning_context.get("explicit_constraints", [])
            implicit = planning_context.get("implicit_constraints", [])
            nfrs = planning_context.get("inferred_nfrs", [])
            personas = planning_context.get("inferred_personas", [])
            quality = planning_context.get("quality_targets", [])
            domain_insights = planning_context.get("domain_insights", [])

            ctx_lines = ["## Planning Context (Deep Planner Analysis)"]
            if intent:
                ctx_lines.append(f"\n**Inferred Intent**: {intent}")
            if constraints:
                ctx_lines.append("\n**Explicit Constraints**:\n" + "\n".join(f"- {c}" for c in constraints))
            if implicit:
                ctx_lines.append("\n**Implicit Constraints**:\n" + "\n".join(f"- {c}" for c in implicit))
            if personas:
                ctx_lines.append("\n**Inferred Personas**:\n" + "\n".join(f"- {p}" for p in personas))
            if nfrs:
                ctx_lines.append("\n**Non-Functional Requirements**:\n" + "\n".join(f"- {n}" for n in nfrs))
            if quality:
                ctx_lines.append("\n**Quality Targets**:\n" + "\n".join(f"- {q}" for q in quality))
            if domain_insights:
                ctx_lines.append("\n**Domain Insights**:\n" + "\n".join(f"- {i}" for i in domain_insights))
            ctx_lines.append("\n## End Planning Context")

            parts.append("\n".join(ctx_lines))

        # ── od_ppt / od_prototype: inject template + DS + example into user message ──
        # The AGENT.md prompts for these agents explicitly expect:
        #   - ACTIVE TEMPLATE (SKILL.md) — the template's workflow instructions
        #   - ACTIVE DESIGN SYSTEM (DESIGN.md) — the design tokens
        #   - TEMPLATE EXAMPLE (example.html) — concrete visual reference
        # Without these in the user message, the agent ignores the template and
        # generates a generic prototype that doesn't match the selected style.
        #
        # For prototype-build tasks 2+: skip the full DS body and template body
        # injection — the skeleton already has the DS tokens and the task list
        # has the CSS classes. Only inject for task 1 (HTML shell) and for
        # non-build agents (spec writer, planner, validate).
        od = getattr(self, "_od_context", None) or {}
        injects = getattr(spec, "injects", []) or []
        task_num_str = accumulated_outputs.get("_build_task_number", "")
        is_build_task_2_plus = (spec.id == "prototype-build" and task_num_str not in ("", "1"))

        # Inject design system into user message for ALL prototype agents
        # (it's also in the system prompt via factory.py, but repeating it
        # in the user message ensures text-only agents see it prominently).
        # Skip for build tasks 2+ — skeleton already has DS tokens.
        if "design_system" in injects and od.get("ds_body") and not is_build_task_2_plus:
            ds_id = od.get("ds_id", "custom")
            is_deck_conditional = od.get("is_design_system_required")
            include_ds = True if is_deck_conditional is None else bool(is_deck_conditional)
            if include_ds:
                parts.append(
                    f"=== ACTIVE DESIGN SYSTEM: {ds_id} ===\n"
                    f"Apply these tokens to ALL colors, fonts, and spacing. "
                    f"Map to :root variables: --bg, --fg, --accent, --surface, --border, --muted.\n"
                    f"{od['ds_body']}\n"
                    f"=== END ACTIVE DESIGN SYSTEM ==="
                )

        if "template" in injects and od.get("template_body"):
            template_id = od.get("template_id", "")
            # For build tasks 2+: skip the full template body — the task list
            # already has the CSS classes and layout patterns.
            if not is_build_task_2_plus:
                parts.append(
                    f"=== ACTIVE TEMPLATE (SKILL.md): {template_id} ===\n"
                    f"{od['template_body']}\n"
                    f"=== END ACTIVE TEMPLATE ==="
                )
                # Also inject example.html if available — gives the agent a concrete
                # visual reference for the template's class system and layout patterns.
                example_html = self._load_template_example(template_id)
                if example_html:
                    parts.append(
                        f"=== TEMPLATE EXAMPLE (example.html): {template_id} ===\n"
                        f"{example_html[:8000]}"
                        f"{'...[truncated]' if len(example_html) > 8000 else ''}\n"
                        f"=== END TEMPLATE EXAMPLE ==="
                    )

            # Pre-inject prototype reference files (template seed + layouts + checklist).
            # For build tasks 2+: inject ONLY the template seed (CSS classes needed
            # to build the page) — skip layouts.md and checklist.md to save tokens.
            # For task 1 and all other agents: inject all reference files.
            if "prototype_emit_only" in (getattr(spec, "tools", []) or []):
                # Build/validate agent — inject template seed always, others only for task 1
                from agents.prototype.context import get_template_injection_parts
                all_parts = get_template_injection_parts(template_id)
                if is_build_task_2_plus:
                    # Only inject the seed (first part) — skip layouts and checklist
                    seed_parts = [p for p in all_parts if "TEMPLATE SEED" in p]
                    for part in seed_parts:
                        parts.append(part)
                else:
                    for part in all_parts:
                        parts.append(part)
            elif "prototype" in (getattr(spec, "tools", []) or []):
                from agents.prototype.context import get_template_injection_parts
                for part in get_template_injection_parts(template_id):
                    parts.append(part)

        consumed = self._filter_consumed_outputs(spec, ordered_agents, accumulated_outputs)
        for aid, output in consumed.items():
            prev = next((s for s in ordered_agents if s.id == aid), None)
            label = f"{prev.name} ({prev.role})" if prev else aid
            parts.append(f"\n--- Output from {label} ---\n{output}")

        # For the build agent: inject the current task number and current HTML.
        # The agent reads === CURRENT TASK === to find its assigned task.
        if spec.id == "prototype-build":
            task_num_str = accumulated_outputs.get("_build_task_number", "")
            total_str = accumulated_outputs.get("_build_task_total", "")
            if task_num_str:
                parts.append(
                    f"\n=== CURRENT TASK ===\n"
                    f"Task {task_num_str} of {total_str}\n"
                    f"Execute ONLY this task from the task list above.\n"
                    f"=== END CURRENT TASK ==="
                )

            # Pass current HTML for modification
            current_html = accumulated_outputs.get("prototype-build", "")
            if current_html and not current_html.startswith("[Error:"):
                html_to_pass = current_html[:120000]
                truncated = len(current_html) > 120000
                parts.append(
                    f"\n--- CURRENT HTML (modify this — do NOT rebuild from scratch) ---\n"
                    f"{html_to_pass}"
                    f"{'...[truncated at 120k]' if truncated else ''}\n"
                    f"--- END CURRENT HTML ---"
                )

            # Template compliance reminder
            od = getattr(self, "_od_context", None) or {}
            ds_id = od.get("ds_id", "")
            template_id_val = od.get("template_id", "")
            parts.append(
                f"\n=== TEMPLATE COMPLIANCE ===\n"
                f"Template: {template_id_val} — use ONLY its CSS classes from the TEMPLATE SEED\n"
                f"Design System: {ds_id} — use ONLY :root variables, never raw hex colors\n"
                f"=== END TEMPLATE COMPLIANCE ==="
            )

        return "\n".join(parts)

    def _apply_revision_diff(self, user_message: str, diff_output: str) -> str:
        """Apply a structured revision diff back into the original HTML.

        The revision agent outputs a diff (not the full HTML) to stay within
        output token limits. This method:
        1. Extracts the original HTML from the user_message
        2. Parses REPLACE_SECTION, ADD_CSS, ADD_SCRIPT blocks from the diff
        3. Applies each change to the original HTML
        4. Returns the merged result

        If parsing fails, falls back to returning whatever the agent output.
        """
        import re as _re

        # ── Extract original HTML from user_message ───────────────────────
        original_html = ""
        html_match = _re.search(
            r"=== EXISTING PROTOTYPE HTML ===\s*([\s\S]*?)\s*=== END EXISTING HTML ===",
            user_message, _re.IGNORECASE
        )
        if html_match:
            original_html = html_match.group(1).strip()

        if not original_html:
            # No original HTML found — return the diff output as-is
            logger.warning("_apply_revision_diff: no original HTML found in user_message")
            return diff_output

        # ── Parse the diff ────────────────────────────────────────────────
        # Extract the content between === REVISION_DIFF === markers
        diff_match = _re.search(
            r"=== REVISION_DIFF ===([\s\S]*?)=== END_DIFF ===",
            diff_output, _re.IGNORECASE
        )
        if not diff_match:
            # Agent didn't follow the format — likely output full HTML anyway
            # If it looks like HTML, use it directly; otherwise return original
            stripped = diff_output.strip()
            if stripped.lower().startswith("<!doctype") or stripped.startswith("<html"):
                logger.info("_apply_revision_diff: agent output full HTML (not diff format) — using directly")
                return stripped
            logger.warning("_apply_revision_diff: no diff block found — returning original HTML")
            return original_html

        diff_content = diff_match.group(1)
        result_html = original_html

        # ── Apply REPLACE_SECTION blocks ──────────────────────────────────
        section_replacements = _re.findall(
            r"=== REPLACE_SECTION:\s*([^\s=]+)\s*===\s*([\s\S]*?)=== END_SECTION ===",
            diff_content, _re.IGNORECASE
        )
        for section_id, new_section_html in section_replacements:
            section_id = section_id.strip()
            new_section = new_section_html.strip()
            # Find and replace the existing <section data-page="section_id">...</section>
            # Use a regex that matches the section tag with its full content
            pattern = (
                r'<section[^>]+data-page=["\']' + _re.escape(section_id) + r'["\'][^>]*>'
                r'[\s\S]*?'
                r'</section>'
            )
            if _re.search(pattern, result_html, _re.IGNORECASE):
                result_html = _re.sub(pattern, new_section, result_html, flags=_re.IGNORECASE)
                logger.info("_apply_revision_diff: replaced section '%s' (%d chars)", section_id, len(new_section))
            else:
                # Section not found — append before </body>
                result_html = result_html.replace("</body>", f"\n{new_section}\n</body>")
                logger.info("_apply_revision_diff: section '%s' not found — appended before </body>", section_id)

        # ── Apply ADD_CSS blocks ──────────────────────────────────────────
        css_additions = _re.findall(
            r"=== ADD_CSS ===([\s\S]*?)=== END_CSS ===",
            diff_content, _re.IGNORECASE
        )
        for css_block in css_additions:
            css = css_block.strip()
            if css:
                # Append before </style>
                result_html = result_html.replace("</style>", f"\n/* Revision additions */\n{css}\n</style>", 1)
                logger.info("_apply_revision_diff: added CSS (%d chars)", len(css))

        # ── Apply ADD_SCRIPT blocks ───────────────────────────────────────
        script_additions = _re.findall(
            r"=== ADD_SCRIPT ===([\s\S]*?)=== END_SCRIPT ===",
            diff_content, _re.IGNORECASE
        )
        for script_block in script_additions:
            script = script_block.strip()
            if script:
                # Append before </script> (last one)
                last_script = result_html.rfind("</script>")
                if last_script >= 0:
                    result_html = result_html[:last_script] + f"\n// Revision additions\n{script}\n" + result_html[last_script:]
                    logger.info("_apply_revision_diff: added script (%d chars)", len(script))

        logger.info(
            "_apply_revision_diff: applied %d section(s), %d CSS block(s), %d script block(s) — result: %d chars",
            len(section_replacements), len(css_additions), len(script_additions), len(result_html),
        )
        return result_html

    def _load_template_example(self, template_id: str) -> str | None:
        """Load the example.html for a template, or None if not available."""
        if not template_id:
            return None
        try:
            from agents.prototype.context import get_example_html
            return get_example_html(template_id)
        except Exception as exc:
            logger.debug("Could not load template example for %s: %s", template_id, exc)
        return None

    def _extract_html_skeleton(self, html: str) -> str:
        """Extract a compact skeleton from the full HTML for build agent context.

        Option 1+5: instead of passing the full HTML (which grows with every task
        and causes O(n²) slowdown), extract only what the build agent needs:
          - :root token values (so DS tokens are preserved across calls)
          - List of <section data-page> IDs with filled/empty status
          - Routes map
          - Chrome structure summary

        Returns a compact ~1-3k char summary instead of the full 50k+ HTML.
        """
        import re as _re
        lines: list[str] = []

        # 1. Extract :root tokens
        root_match = _re.search(r":root\s*\{([^}]+)\}", html, _re.DOTALL)
        if root_match:
            root_content = root_match.group(1).strip()
            # Keep only the 6 key token lines
            token_lines = []
            for line in root_content.split("\n"):
                line = line.strip()
                if any(tok in line for tok in ["--bg:", "--fg:", "--accent:", "--surface:", "--border:", "--muted:", "--font-"]):
                    token_lines.append(f"  {line}")
            if token_lines:
                lines.append(":root tokens (current):\n" + "\n".join(token_lines[:12]))

        # 2. Extract routes map
        routes_match = _re.search(r"const routes\s*=\s*\{([^}]+)\}", html, _re.DOTALL)
        if routes_match:
            routes_content = routes_match.group(1).strip()
            lines.append(f"Routes map:\n  {{{ routes_content.strip() }}}")

        # 3. Scan all <section data-page> elements — filled vs empty
        sections = _re.findall(
            r'<section[^>]+data-page=["\']([^"\']+)["\'][^>]*>([\s\S]*?)(?=<section|</body>)',
            html, _re.IGNORECASE
        )
        filled = []
        empty = []
        for page_id, content in sections:
            # A section is "filled" if it has more than just whitespace/comments
            stripped = _re.sub(r'<!--.*?-->', '', content, flags=_re.DOTALL).strip()
            if len(stripped) > 100:
                filled.append(page_id)
            else:
                empty.append(page_id)

        if filled:
            lines.append(f"Pages already built ({len(filled)}): {', '.join(filled)}")
        if empty:
            lines.append(f"Pages still empty ({len(empty)}): {', '.join(empty)}")

        # 4. Chrome summary (topnav/sidebar presence)
        has_sidebar = bool(_re.search(r'<aside|data-od-id=["\']sidebar', html, _re.IGNORECASE))
        has_topnav = bool(_re.search(r'class=["\'][^"\']*topnav|data-od-id=["\']topnav', html, _re.IGNORECASE))
        chrome_type = "sidebar" if has_sidebar else ("topnav" if has_topnav else "none")
        lines.append(f"Chrome: {chrome_type} (copy chrome from any filled page — do NOT rewrite it)")

        # 5. Total HTML size for reference
        lines.append(f"Total HTML so far: {len(html):,} chars across {len(filled) + len(empty)} sections")

        return "\n".join(lines)


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_ENGINE: ExecutionEngine | None = None


def get_execution_engine() -> ExecutionEngine:
    """Return the module-level ExecutionEngine singleton."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = ExecutionEngine()
    return _ENGINE
