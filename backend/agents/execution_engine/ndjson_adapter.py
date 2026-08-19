"""agents/execution_engine/ndjson_adapter.py — NDJSON streaming adapter.

The REST endpoint POST /api/prototype/run (prototype_templates.py) streams the
prototype pipeline as flat NDJSON events. It previously called the deleted
od_runner.run_od_prototype_pipeline. This adapter runs the same pipeline through
the Universal Execution_Engine and flattens the {type, data} WS envelopes into
the flat event shapes the endpoint's frontend reader expects.

Event shapes emitted (matching the former od_runner contract):
  {type: "pipeline_start", agents: [...]}
  {type: "agent_start",    agent_id, name, role, icon, index}
  {type: "agent_chunk",    agent_id, chunk}
  {type: "agent_complete", agent_id, output_length, duration}
  {type: "agent_error",    agent_id, error}
  {type: "pipeline_complete", final_html, duration}
  {type: "pipeline_error", error}
"""

from __future__ import annotations

import uuid
from typing import Any, AsyncGenerator

from agents.execution_engine.engine import get_execution_engine
from agents.execution_engine.od_context import load_prototype_od_context
from agents.registry import get_pipeline_agents


async def run_prototype_pipeline(
    template_id: str,
    design_system_id: str,
    brief: str,
    discovery: dict[str, Any] | None,
    custom_ds_body: str | None = None,
    custom_template_body: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Drop-in replacement for the deleted od_runner.run_od_prototype_pipeline.

    Runs the prototype pipeline through the Universal Execution_Engine and
    flattens its {type, data} envelopes into the flat NDJSON event shapes the
    REST endpoint emits.
    """
    try:
        od_context = load_prototype_od_context(
            template_id, design_system_id,
            custom_ds_body=custom_ds_body, custom_template_body=custom_template_body,
        )
    except LookupError as exc:
        yield {"type": "pipeline_error", "error": str(exc)}
        return

    agents = get_pipeline_agents("prototype")
    if not agents:
        yield {"type": "pipeline_error", "error": "No prototype agents found"}
        return

    engine = get_execution_engine()
    pipeline_run_id = str(uuid.uuid4())
    final_output = ""

    try:
        async for ev in engine.execute(
            agents=agents,
            user_message=brief,
            pipeline_run_id=pipeline_run_id,
            pipeline_type="prototype",
            od_context=od_context,
        ):
            etype = ev["type"]
            data = ev.get("data", {})
            # Flatten {type, data} → flat event; pass through engine-internal
            # planner/gate/workflow events as-is (frontend ignores unknowns).
            if etype == "pipeline_complete":
                final_output = data.get("final_output", "")
                yield {"type": "pipeline_complete", "final_html": final_output,
                       "duration": data.get("total_duration", 0)}
            elif etype in ("agent_start", "agent_chunk", "agent_complete",
                           "agent_error", "pipeline_start"):
                yield {"type": etype, **data}
            else:
                # planner_start, planner_complete, gate_status, workflow_validated,
                # questionnaire_*, tool_call, tool_result — forward flattened
                yield {"type": etype, **data}
    except Exception as exc:  # noqa: BLE001
        yield {"type": "pipeline_error", "error": str(exc)}
