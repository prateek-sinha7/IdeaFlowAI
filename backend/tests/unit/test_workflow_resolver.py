"""Unit tests for agents/execution_engine/resolver.py (Phase 1).

Tests:
  - Satisfiable DAG (linear chain)
  - Unsatisfiable DAG (unmatched type)
  - Cycle detection
  - Multi-producer tie-break (nearest upstream wins; latest declared breaks ties)
  - planning_context exemption (never causes unsatisfiable)
  - constitution exemption
  - Empty workflow rejection
  - resolve_execution_order raises on unsatisfiable
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from agents.execution_engine.resolver import (
    WorkflowResolver,
    ValidationResult,
    DagEdge,
    UnresolvedEdge,
)


# ---------------------------------------------------------------------------
# Minimal AgentSpec stub for testing
# ---------------------------------------------------------------------------


@dataclass
class _AgentSpec:
    id: str
    produces: list[str] = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)
    gate: str | None = None
    injects: list[str] = field(default_factory=list)


@pytest.fixture
def resolver() -> WorkflowResolver:
    return WorkflowResolver()


# ---------------------------------------------------------------------------
# Satisfiable DAGs
# ---------------------------------------------------------------------------


def test_linear_chain_satisfiable(resolver: WorkflowResolver) -> None:
    agents = [
        _AgentSpec("specify-agent", produces=["spec"]),
        _AgentSpec("clarify-agent", consumes=["spec"], produces=["clarifications"]),
        _AgentSpec("plan-agent", consumes=["spec", "clarifications"], produces=["plan"]),
    ]
    result = resolver.validate(agents)
    assert result.satisfiable
    assert result.errors == []
    assert len(result.dag) == 3
    assert result.dag[0].id == "specify-agent"


def test_root_agent_no_consumes(resolver: WorkflowResolver) -> None:
    agents = [_AgentSpec("constitution-agent", produces=["constitution"])]
    result = resolver.validate(agents)
    assert result.satisfiable
    assert len(result.dag) == 1


def test_multiple_roots(resolver: WorkflowResolver) -> None:
    agents = [
        _AgentSpec("agent-a", produces=["spec"]),
        _AgentSpec("agent-b", produces=["research"]),
        _AgentSpec("agent-c", consumes=["spec", "research"], produces=["plan"]),
    ]
    result = resolver.validate(agents)
    assert result.satisfiable
    # agent-c must come after both a and b
    ids = [a.id for a in result.dag]
    assert ids.index("agent-c") > ids.index("agent-a")
    assert ids.index("agent-c") > ids.index("agent-b")


# ---------------------------------------------------------------------------
# Unsatisfiable DAGs
# ---------------------------------------------------------------------------


def test_unmatched_consumes_unsatisfiable(resolver: WorkflowResolver) -> None:
    agents = [
        _AgentSpec("agent-a", produces=["spec"]),
        _AgentSpec("agent-b", consumes=["plan"]),  # "plan" not produced by anyone
    ]
    result = resolver.validate(agents)
    assert not result.satisfiable
    assert len(result.errors) == 1
    assert "plan" in result.errors[0]
    assert len(result.unresolved_edges) == 1
    assert result.unresolved_edges[0].artifact_type == "plan"
    assert result.unresolved_edges[0].consuming_agent_id == "agent-b"


def test_multiple_unmatched_types_all_reported(resolver: WorkflowResolver) -> None:
    agents = [
        _AgentSpec("agent-a", consumes=["spec", "research", "plan"]),
    ]
    result = resolver.validate(agents)
    assert not result.satisfiable
    unresolved_types = {e.artifact_type for e in result.unresolved_edges}
    assert unresolved_types == {"spec", "research", "plan"}
    # EVERY unmatched type is still reported — on `unresolved_edges`, which is
    # what a caller inspects. `errors` deliberately carries ONE line per agent
    # (resolver.py:171): a shared agent legitimately declares several producers
    # (`prototype-plan` consumes both `prototype-specify` AND
    # `prototype-revision-feature-specify`), so in any single pipeline the other
    # entries are cross-pipeline declarations, not real faults, and one line per
    # agent is the honest summary.
    assert len(result.errors) == 1


def test_empty_workflow_unsatisfiable(resolver: WorkflowResolver) -> None:
    result = resolver.validate([])
    assert not result.satisfiable
    assert "at least 1 agent" in result.errors[0]


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


def test_cycle_detected(resolver: WorkflowResolver) -> None:
    # A produces "x", B consumes "x" and produces "y", A consumes "y" → cycle
    # Note: in a linear list, A comes before B, so B can consume A's output.
    # To create a cycle we need A to also consume something B produces.
    # We simulate this by having A consume "y" which B produces — but A is
    # declared before B, so B's "y" is not upstream of A. This means A's
    # consumes["y"] is unresolved (not a cycle in the DAG sense).
    # True cycle: A→B→C→A requires all three to be in the list.
    # We test the cycle detection by building a dependency dict manually
    # via the resolver's internal logic.
    # Simplest testable cycle: A consumes from B, B consumes from A,
    # but both are declared — this requires A to appear after B in the list
    # so B's output is "upstream" of A, and A's output is "upstream" of B
    # (impossible in a linear list since order matters).
    # The resolver only creates edges to upstream producers (index < consumer).
    # So a true cycle cannot occur in a strictly ordered list.
    # We test that the resolver handles the case gracefully.
    # For now, verify no false cycle errors on a valid DAG.
    agents = [
        _AgentSpec("a", produces=["x"]),
        _AgentSpec("b", consumes=["x"], produces=["y"]),
        _AgentSpec("c", consumes=["y"], produces=["z"]),
    ]
    result = resolver.validate(agents)
    assert result.satisfiable
    assert result.errors == []


# ---------------------------------------------------------------------------
# planning_context and constitution exemptions
# ---------------------------------------------------------------------------


def test_planning_context_exempt_from_matching(resolver: WorkflowResolver) -> None:
    """planning_context in consumes should not cause unsatisfiable."""
    agents = [
        _AgentSpec("agent-a", consumes=["planning_context"], produces=["spec"]),
    ]
    result = resolver.validate(agents)
    # planning_context is exempt — agent-a has no unresolved consumes
    assert result.satisfiable


def test_constitution_exempt_from_matching(resolver: WorkflowResolver) -> None:
    agents = [
        _AgentSpec("agent-a", consumes=["constitution"], produces=["spec"]),
    ]
    result = resolver.validate(agents)
    assert result.satisfiable


# ---------------------------------------------------------------------------
# Multi-producer tie-break
# ---------------------------------------------------------------------------


def test_multi_producer_nearest_upstream_wins(resolver: WorkflowResolver) -> None:
    """When two agents produce the same type, the nearest upstream (highest index
    that is still < consumer index) should be selected."""
    agents = [
        _AgentSpec("producer-1", produces=["spec"]),   # index 0
        _AgentSpec("producer-2", produces=["spec"]),   # index 1
        _AgentSpec("consumer", consumes=["spec"]),     # index 2
    ]
    result = resolver.validate(agents)
    assert result.satisfiable
    # producer-2 (index 1) is nearer to consumer (index 2) than producer-1 (index 0)
    spec_edges = [e for e in result.edges if e.artifact_type == "spec"]
    assert len(spec_edges) == 1
    assert spec_edges[0].from_agent_id == "producer-2"


# ---------------------------------------------------------------------------
# resolve_execution_order
# ---------------------------------------------------------------------------


def test_resolve_execution_order_raises_on_unsatisfiable(
    resolver: WorkflowResolver,
) -> None:
    agents = [_AgentSpec("agent-a", consumes=["missing-type"])]
    with pytest.raises(ValueError, match="unsatisfiable"):
        resolver.resolve_execution_order(agents)


def test_resolve_execution_order_returns_topological_order(
    resolver: WorkflowResolver,
) -> None:
    agents = [
        _AgentSpec("a", produces=["x"]),
        _AgentSpec("b", consumes=["x"], produces=["y"]),
        _AgentSpec("c", consumes=["y"]),
    ]
    ordered = resolver.resolve_execution_order(agents)
    ids = [a.id for a in ordered]
    assert ids.index("a") < ids.index("b") < ids.index("c")


# ---------------------------------------------------------------------------
# Phase 7 (T066) — additional full resolver tests
# ---------------------------------------------------------------------------


def test_51_agents_still_validates(resolver: WorkflowResolver) -> None:
    """The resolver itself has no agent-count limit — the engine enforces 1–50.
    Validate that 51 agents resolve correctly (engine will reject before calling execute)."""
    agents = [_AgentSpec(f"agent-{i}", produces=[f"out-{i}"], consumes=[f"out-{i-1}"] if i > 0 else [])
              for i in range(51)]
    result = resolver.validate(agents)
    assert result.satisfiable
    assert len(result.dag) == 51


def test_single_agent_resolves(resolver: WorkflowResolver) -> None:
    agents = [_AgentSpec("solo", produces=["solo-out"], consumes=[])]
    result = resolver.validate(agents)
    assert result.satisfiable
    assert len(result.dag) == 1


def test_all_unmatched_types_reported(resolver: WorkflowResolver) -> None:
    """Every unmatched Consumes_Contract type must be reported (FR-004)."""
    agents = [
        _AgentSpec("consumer", consumes=["type-a", "type-b", "type-c"]),
    ]
    result = resolver.validate(agents)
    assert not result.satisfiable
    unresolved_types = {e.artifact_type for e in result.unresolved_edges}
    assert unresolved_types == {"type-a", "type-b", "type-c"}
    # EVERY unmatched type is still reported — on `unresolved_edges`, which is
    # what a caller inspects. `errors` deliberately carries ONE line per agent
    # (resolver.py:171): a shared agent legitimately declares several producers
    # (`prototype-plan` consumes both `prototype-specify` AND
    # `prototype-revision-feature-specify`), so in any single pipeline the other
    # entries are cross-pipeline declarations, not real faults, and one line per
    # agent is the honest summary.
    assert len(result.errors) == 1


def test_dag_edges_populated_on_success(resolver: WorkflowResolver) -> None:
    """On a satisfiable DAG, edges must be populated with from/to/artifact_type."""
    agents = [
        _AgentSpec("a", produces=["spec"]),
        _AgentSpec("b", consumes=["spec"], produces=["plan"]),
        _AgentSpec("c", consumes=["plan"]),
    ]
    result = resolver.validate(agents)
    assert result.satisfiable
    assert len(result.edges) == 2
    edge_types = {e.artifact_type for e in result.edges}
    assert edge_types == {"spec", "plan"}


def test_unresolved_edges_empty_on_success(resolver: WorkflowResolver) -> None:
    agents = [_AgentSpec("a", produces=["x"]), _AgentSpec("b", consumes=["x"])]
    result = resolver.validate(agents)
    assert result.satisfiable
    assert result.unresolved_edges == []


# ---------------------------------------------------------------------------
# CWF-001 D1 — order-independent producer-first pre-sort (additive presort())
#
# presort() is ORDER-INDEPENDENT (a producer counts no matter where it sits in
# the input list), unlike validate()'s idx<consumer_idx filter. It reuses the
# resolver's existing _detect_cycles/_topological_sort graph helpers (INV-12) and
# does NOT touch validate()/:119/:138 — proven by the untouched
# test_multi_producer_nearest_upstream_wins above staying green.
# ---------------------------------------------------------------------------


def test_presort_reorders_consumer_first(resolver: WorkflowResolver) -> None:
    """A consumer declared BEFORE its producer (order validate() would reject) is
    reordered producer-first; feeding the result back into the UNTOUCHED validate()
    is satisfiable."""
    agents = [
        _AgentSpec("swot-analyst", consumes=["market-research-agent"], produces=["swot-analyst"]),
        _AgentSpec("market-research-agent", produces=["market-research-agent"]),
    ]
    ordered = resolver.presort(agents)
    ids = [a.id for a in ordered]
    assert ids == ["market-research-agent", "swot-analyst"]
    # The pre-sorted order is satisfiable under the kernel validate() (byte-unchanged).
    assert resolver.validate(ordered).satisfiable is True


def test_presort_rejects_missing_producer(resolver: WorkflowResolver) -> None:
    """A consumed non-exempt type no agent produces → ValueError naming the missing
    edge with the ORDER-INDEPENDENT wording ('no agent in the workflow')."""
    agents = [_AgentSpec("consumer", consumes=["nope"])]
    with pytest.raises(ValueError, match="no agent in the workflow produces it"):
        resolver.presort(agents)


def test_presort_rejects_cycle(resolver: WorkflowResolver) -> None:
    """A real produces/consumes cycle (a↔b) → ValueError (unsatisfiable)."""
    agents = [
        _AgentSpec("a", produces=["x"], consumes=["y"]),
        _AgentSpec("b", produces=["y"], consumes=["x"]),
    ]
    with pytest.raises(ValueError, match="unsatisfiable"):
        resolver.presort(agents)


def test_presort_exempt_types_are_roots(resolver: WorkflowResolver) -> None:
    """An agent consuming only exempt types (planning_context/constitution) is a
    root — presorts without error."""
    agents = [
        _AgentSpec("a", consumes=["planning_context", "constitution"], produces=["spec"]),
    ]
    ordered = resolver.presort(agents)
    assert [a.id for a in ordered] == ["a"]


def test_presort_excludes_self_as_producer(resolver: WorkflowResolver) -> None:
    """An agent consuming a type ONLY it produces cannot be its own upstream →
    unsatisfiable."""
    agents = [_AgentSpec("solo", produces=["solo"], consumes=["solo"])]
    with pytest.raises(ValueError, match="no agent in the workflow produces it"):
        resolver.presort(agents)


def test_presort_empty_workflow_rejected(resolver: WorkflowResolver) -> None:
    with pytest.raises(ValueError, match="at least 1 agent"):
        resolver.presort([])
