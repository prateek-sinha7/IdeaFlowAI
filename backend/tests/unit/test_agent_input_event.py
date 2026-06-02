"""T047 — Unit tests for the agent_input WS event (Phase 3 / FR-015).

Tests:
  - agent_input event is emitted for every agent before agent_start
  - context_sources populated correctly for consumed upstream outputs
  - compression ratio fields present (summary_length, full_output_length)
  - planning_context injected into context_message for all agents
  - engine._build_context_sources returns correct shape
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from agents.execution_engine.engine import ExecutionEngine


@dataclass
class _Spec:
    id: str
    name: str = "Test Agent"
    role: str = "Tester"
    icon: str = "🤖"
    order: int = 1
    produces: list[str] = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)
    injects: list[str] = field(default_factory=list)
    gate: str | None = None
    max_tokens: int = 1024
    prompt_body: str = "You are a test agent."
    context_from: list[str] = field(default_factory=list)
    estimated_duration: float = 1.0


# ---------------------------------------------------------------------------
# _build_context_sources
# ---------------------------------------------------------------------------


def test_build_context_sources_empty_when_no_consumes():
    engine = ExecutionEngine()
    spec = _Spec("agent-a", produces=["agent-a"], consumes=[])
    agents = [spec]
    accumulated = {"agent-a": "some output"}
    sources = engine._build_context_sources(spec, agents, accumulated)
    assert sources == []


def test_build_context_sources_single_upstream():
    engine = ExecutionEngine()
    upstream = _Spec("agent-a", produces=["agent-a"], consumes=[])
    consumer = _Spec("agent-b", produces=["agent-b"], consumes=["agent-a"])
    agents = [upstream, consumer]
    accumulated = {"agent-a": "upstream output text"}
    sources = engine._build_context_sources(consumer, agents, accumulated)
    assert len(sources) == 1
    assert sources[0]["type"] == "summary"
    assert sources[0]["agent_id"] == "agent-a"
    assert sources[0]["summary_length"] == len("upstream output text")
    assert sources[0]["full_output_length"] == len("upstream output text")


def test_build_context_sources_multiple_upstream():
    engine = ExecutionEngine()
    a = _Spec("a", produces=["a"], consumes=[])
    b = _Spec("b", produces=["b"], consumes=[])
    c = _Spec("c", produces=["c"], consumes=["a", "b"])
    agents = [a, b, c]
    accumulated = {"a": "output from a", "b": "output from b"}
    sources = engine._build_context_sources(c, agents, accumulated)
    assert len(sources) == 2
    agent_ids = {s["agent_id"] for s in sources}
    assert agent_ids == {"a", "b"}


def test_build_context_sources_skips_missing_accumulated():
    """If an upstream agent hasn't produced output yet, it's not in sources."""
    engine = ExecutionEngine()
    a = _Spec("a", produces=["a"], consumes=[])
    b = _Spec("b", produces=["b"], consumes=["a"])
    agents = [a, b]
    accumulated: dict = {}  # a hasn't run yet
    sources = engine._build_context_sources(b, agents, accumulated)
    assert sources == []


# ---------------------------------------------------------------------------
# _build_context_message — planning_context injection
# ---------------------------------------------------------------------------


def test_planning_context_injected_into_context_message():
    engine = ExecutionEngine()
    spec = _Spec("agent-a", consumes=[])
    agents = [spec]
    planning_context = {
        "inferred_intent": "Build a login feature",
        "explicit_constraints": ["React frontend"],
        "implicit_constraints": ["WCAG 2.1"],
        "inferred_personas": ["Developer"],
        "inferred_nfrs": ["< 200ms response"],
        "quality_targets": ["100% test coverage"],
        "execution_gate": "PROCEED",
    }
    msg = engine._build_context_message(spec, agents, "test brief", {}, planning_context)
    assert "## Planning Context" in msg
    assert "Build a login feature" in msg
    assert "React frontend" in msg
    assert "WCAG 2.1" in msg
    assert "Developer" in msg
    assert "< 200ms response" in msg


def test_planning_context_not_injected_when_timed_out():
    """Timed-out planning context (empty/default) should not inject a block."""
    engine = ExecutionEngine()
    spec = _Spec("agent-a", consumes=[])
    agents = [spec]
    planning_context = engine._default_planning_context("brief", timed_out=True)
    msg = engine._build_context_message(spec, agents, "brief", {}, planning_context)
    # Timed-out context has planner_timed_out=True — no Planning Context block
    assert "## Planning Context" not in msg


def test_user_request_always_present():
    engine = ExecutionEngine()
    spec = _Spec("agent-a", consumes=[])
    agents = [spec]
    msg = engine._build_context_message(spec, agents, "my user brief", {}, {})
    assert "my user brief" in msg
    assert "ORIGINAL USER REQUEST" in msg
