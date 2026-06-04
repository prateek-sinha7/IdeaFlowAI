"""app/agents/types.py — Shared type definitions for workflow execution.

Centralises ``WorkflowState`` and ``TokenUsage`` so they can be imported by the
LIVE runtime (``app/agents/deep_agent_runner.py``, ``app/agents/chat_runner.py``)
without depending on the soon-to-be-deleted legacy ``app/agents/base.py``.

``TokenUsage`` was relocated here (migration Phase 7b-3) from ``base.py``: it is
used by the LIVE ``DeepAgentRunner`` text-only path, so it must outlive the
deletion of ``base.py`` in 7b-5. ``base.py`` now imports it FROM here (re-export)
for its own remaining, soon-to-be-deleted use — so deleting ``base.py`` cannot
affect the runner's ``TokenUsage``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


# ============================================================
# TOKEN USAGE — per-invocation token accounting
# ============================================================


@dataclass
class TokenUsage:
    """Token usage for a single agent invocation."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
        )

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }


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
