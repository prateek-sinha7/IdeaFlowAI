"""Edge-case manifest tests (D-05).

  - reverse_engineer compiles to a CompiledWorkflow with empty steps (the
    empty-plan stub; agents TBD).
  - chat loads + compiles (7 agents) AND is marked engine-non-dispatchable: it is
    in agents.registry._INTERNAL_PIPELINES, so allowed_custom_agent_ids returns ∅
    — the ExecutionEngine never dispatches it (ChatRunner-driven).
"""

from __future__ import annotations

from pathlib import Path

from agents.capabilities.registry import CapabilityRegistry
from agents.registry import _INTERNAL_PIPELINES, allowed_custom_agent_ids
from agents.workflows.compiler import WorkflowCompiler
from agents.workflows.manifest import load_manifest

_BASE = Path(__file__).resolve().parents[2] / "agents" / "workflows"


def _compile(workflow_id: str):
    return WorkflowCompiler().compile(
        load_manifest(workflow_id, _BASE), CapabilityRegistry()
    )


def test_reverse_engineer_empty_plan() -> None:
    plan = _compile("reverse_engineer")
    assert plan.id == "reverse_engineer"
    assert plan.steps == []


def test_chat_compiles_but_non_dispatchable() -> None:
    plan = _compile("chat")
    assert plan.id == "chat"
    assert [s.agent_id for s in plan.steps] == [
        "chat-discovery",
        "chat-requirements",
        "chat-user-stories",
        "chat-ppt",
        "chat-prototype",
        "chat-ui-design",
        "chat-preview",
    ]
    # Engine-non-dispatchable marker (D-05): chat is driven by the ChatRunner.
    assert "chat" in _INTERNAL_PIPELINES
    assert allowed_custom_agent_ids("chat") == set()
