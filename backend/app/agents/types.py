"""app/agents/types.py — Shared type definitions for workflow execution.

Centralises WorkflowState so it can be imported by both orchestrator_v2.py
(legacy, until Phase 2 deletion) and the new execution_engine/engine.py
without circular imports.

TokenUsage is defined in app.agents.base — import it from there.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.agents.base import TokenUsage  # noqa: F401 — re-exported for convenience


# ============================================================
# WORKFLOW STATE — Shared context across all agents in a run
# ============================================================


@dataclass
class WorkflowState:
    """Holds all state for a single workflow execution.

    Phase 1: extended with optional fields for the Universal Engine.
    All new fields are optional with safe defaults so existing callers
    (orchestrator_v2.py) continue to work without modification.
    """

    # ── Core fields (required by orchestrator_v2.py) ──────────────────────
    user_request: str
    pipeline_type: str
    base_pipeline_type: str
    is_revision: bool
    previous_output: str = ""
    agent_outputs: dict[str, str] = field(default_factory=dict)
    agent_summaries: dict[str, str] = field(default_factory=dict)
    results: list[dict] = field(default_factory=list)
    agent_token_usage: dict[str, Any] = field(default_factory=dict)

    # ── Phase 1 extensions (optional, safe defaults) ──────────────────────
    # session_id: maps to user_id (JWT sub) for cross-session continuity
    session_id: str | None = None

    # pipeline_run_id: UUID generated at execute() start; used for WS event
    # correlation and ArtifactStore keying. Generated lazily if not supplied.
    pipeline_run_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # parent_run_id: set for revision/chained runs; references originating run
    parent_run_id: str | None = None

    # execution_gate: PROCEED | CLARIFY_REQUIRED — set by Deep_Planner_Agent
    execution_gate: str | None = None

    # execution_strategy: sequential (Phase 2); parallel/conditional (future)
    execution_strategy: str | None = None

    # artifact_refs: {artifact_type: artifact_id} for Artifact_Store lookups
    artifact_refs: dict[str, str] = field(default_factory=dict)
