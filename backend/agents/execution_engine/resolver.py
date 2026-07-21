"""agents/execution_engine/resolver.py — Workflow DAG Resolver.

Implements the WorkflowResolver contract defined in:
  specs/001-ai-workflow-os/contracts/workflow-resolver-api.md

Phase 1: Full validation logic (satisfiable/unsatisfiable/cycle detection).
         Does NOT yet gate execution — the ExecutionEngine (Phase 2) calls
         validate() and halts on unsatisfiable results.

Validation rules:
  1. Exact, case-sensitive Artifact_Type matching
  2. Unsatisfied Consumes_Contract → unsatisfiable
  3. Dependency cycle → unsatisfiable
  4. Multi-producer tie-break: fewest DAG edges; ties broken by latest declared order
  5. planning_context is exempt — always available to all agents (cross-cutting)
  6. constitution is exempt — injected from Workflow_Memory, not matched by type
  7. Agents with empty consumes are DAG roots
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Artifact types that are cross-cutting and exempt from type matching
_EXEMPT_TYPES: frozenset[str] = frozenset({"planning_context", "constitution"})


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DagEdge:
    """A resolved producer→consumer edge in the Workflow DAG."""
    from_agent_id: str
    to_agent_id: str
    artifact_type: str


@dataclass
class UnresolvedEdge:
    """An unsatisfied Consumes_Contract entry (no upstream producer found)."""
    consuming_agent_id: str
    artifact_type: str


@dataclass
class ValidationResult:
    """Result of WorkflowResolver.validate()."""
    satisfiable: bool
    errors: list[str] = field(default_factory=list)
    dag: list = field(default_factory=list)          # list[AgentSpec] in topological order
    edges: list[DagEdge] = field(default_factory=list)
    unresolved_edges: list[UnresolvedEdge] = field(default_factory=list)


# ---------------------------------------------------------------------------
# WorkflowResolver
# ---------------------------------------------------------------------------


class WorkflowResolver:
    """Computes and validates the Workflow DAG from a list of AgentSpec objects.

    Usage:
        resolver = WorkflowResolver()
        result = resolver.validate(agents)
        if not result.satisfiable:
            # halt — report result.errors
        ordered = resolver.resolve_execution_order(agents)
    """

    def validate(self, agents: list) -> ValidationResult:
        """Compute and validate the Workflow DAG.

        Args:
            agents: list[AgentSpec] — the agents to validate (Deep_Planner_Agent
                    is assumed to be prepended by the ExecutionEngine before this
                    call; its planning_context output is cross-cutting and exempt).

        Returns:
            ValidationResult with satisfiable, errors, dag, edges, unresolved_edges.
        """
        if not agents:
            return ValidationResult(
                satisfiable=False,
                errors=["Workflow must contain at least 1 agent."],
            )

        errors: list[str] = []
        resolved_edges: list[DagEdge] = []
        unresolved_edges: list[UnresolvedEdge] = []

        # Build a map: artifact_type → list of (agent_index, agent_id) that produce it
        # Index is used for tie-breaking (latest declared order = highest index)
        produces_map: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for idx, agent in enumerate(agents):
            for artifact_type in getattr(agent, "produces", []):
                produces_map[artifact_type].append((idx, agent.id))

        # Build adjacency list for cycle detection: {agent_id: set of agent_ids it depends on}
        dependencies: dict[str, set[str]] = {agent.id: set() for agent in agents}

        # Validate each agent's consumes contract
        for consumer_idx, consumer in enumerate(agents):
            for artifact_type in getattr(consumer, "consumes", []):
                # Exempt types are always available — skip matching
                if artifact_type in _EXEMPT_TYPES:
                    continue

                producers = produces_map.get(artifact_type, [])

                # Filter to only upstream producers (index < consumer_idx)
                upstream = [(idx, aid) for idx, aid in producers if idx < consumer_idx]

                if not upstream:
                    unresolved_edges.append(
                        UnresolvedEdge(
                            consuming_agent_id=consumer.id,
                            artifact_type=artifact_type,
                        )
                    )
                    errors.append(
                        f"Agent '{consumer.id}' consumes '{artifact_type}' but no upstream "
                        f"agent produces it."
                    )
                    continue

                # Tie-break: fewest DAG edges (nearest upstream producer).
                # We approximate "fewest edges" as smallest index distance.
                # Among equal distances, pick the one with the highest index
                # (latest declared order).
                best_idx, best_aid = max(upstream, key=lambda t: t[0])

                resolved_edges.append(
                    DagEdge(
                        from_agent_id=best_aid,
                        to_agent_id=consumer.id,
                        artifact_type=artifact_type,
                    )
                )
                dependencies[consumer.id].add(best_aid)

        # Cycle detection via Kahn's algorithm
        if errors:
            # Already unsatisfiable — skip cycle check
            return ValidationResult(
                satisfiable=False,
                errors=errors,
                unresolved_edges=unresolved_edges,
            )

        cycle_errors = self._detect_cycles(agents, dependencies)
        if cycle_errors:
            errors.extend(cycle_errors)
            return ValidationResult(
                satisfiable=False,
                errors=errors,
                edges=resolved_edges,
                unresolved_edges=unresolved_edges,
            )

        # Topological sort
        topo_order = self._topological_sort(agents, dependencies)

        return ValidationResult(
            satisfiable=True,
            errors=[],
            dag=topo_order,
            edges=resolved_edges,
            unresolved_edges=[],
        )

    def resolve_execution_order(self, agents: list) -> list:
        """Return agents in deterministic topological execution order.

        Raises:
            ValueError: if the DAG is unsatisfiable.
        """
        result = self.validate(agents)
        if not result.satisfiable:
            raise ValueError(
                f"Workflow DAG is unsatisfiable: {'; '.join(result.errors)}"
            )
        return result.dag

    def presort(self, agents: list) -> list:
        """Order-independent produces/consumes satisfiability check + producer-first
        topological pre-sort (CWF-001 D1). ADDITIVE — a NEW public entry point that
        does NOT touch ``validate()`` / the ``idx < consumer_idx`` producer filter /
        the ``max(upstream, …)`` tie-break.

        Unlike ``validate()`` — which only counts a producer that is DECLARED before
        the consumer (``idx < consumer_idx``) — ``presort`` treats ``produces`` as an
        ORDER-INDEPENDENT set: a consumer is satisfiable iff SOME OTHER agent anywhere
        in the list produces each of its non-exempt consumed types. It then reuses the
        resolver's existing ``_detect_cycles`` + ``_topological_sort`` graph helpers
        (INV-12 — no re-implemented DAG logic) to return the agents in producer-first
        execution order — an order that ``validate()`` (byte-unchanged) will accept.

        Determinism: ``_topological_sort`` seeds and scans in ``agents`` list order,
        so the output is deterministic from the input order (the producer sets are
        used only for edge membership).

        Args:
            agents: list[AgentSpec] — the USER composition to reorder.

        Returns:
            The same agents, producer-first (topological order).

        Raises:
            ValueError: prefixed ``"Workflow DAG is unsatisfiable: "`` when a consumed
                non-exempt type has no producer among the agents (self excluded), when
                a real produces/consumes cycle exists, or when ``agents`` is empty.
        """
        if not agents:
            raise ValueError(
                "Workflow DAG is unsatisfiable: Workflow must contain at least 1 agent."
            )

        # Order-independent producer map: artifact_type → set of producing agent ids
        # over ALL agents (no index filter — this is the key difference from validate()).
        produces_map: dict[str, set[str]] = defaultdict(set)
        for agent in agents:
            for artifact_type in getattr(agent, "produces", []):
                produces_map[artifact_type].add(agent.id)

        dependencies: dict[str, set[str]] = {agent.id: set() for agent in agents}
        errors: list[str] = []

        for consumer in agents:
            for artifact_type in getattr(consumer, "consumes", []):
                # Exempt types are always available — never unsatisfiable.
                if artifact_type in _EXEMPT_TYPES:
                    continue
                # Exclude self — an agent cannot be its own upstream producer.
                producers = produces_map.get(artifact_type, set()) - {consumer.id}
                if not producers:
                    errors.append(
                        f"Agent '{consumer.id}' consumes '{artifact_type}' but no agent "
                        f"in the workflow produces it."
                    )
                    continue
                dependencies[consumer.id].update(producers)

        if errors:
            raise ValueError("Workflow DAG is unsatisfiable: " + "; ".join(errors))

        cycle_errors = self._detect_cycles(agents, dependencies)
        if cycle_errors:
            raise ValueError("Workflow DAG is unsatisfiable: " + "; ".join(cycle_errors))

        return self._topological_sort(agents, dependencies)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_cycles(
        self,
        agents: list,
        dependencies: dict[str, set[str]],
    ) -> list[str]:
        """Detect cycles using DFS. Returns list of error strings (empty = no cycles)."""
        visited: set[str] = set()
        in_stack: set[str] = set()
        errors: list[str] = []

        def dfs(agent_id: str) -> None:
            visited.add(agent_id)
            in_stack.add(agent_id)
            for dep_id in dependencies.get(agent_id, set()):
                if dep_id not in visited:
                    dfs(dep_id)
                elif dep_id in in_stack:
                    errors.append(
                        f"Dependency cycle detected involving agents "
                        f"'{agent_id}' and '{dep_id}'."
                    )
            in_stack.discard(agent_id)

        for agent in agents:
            if agent.id not in visited:
                dfs(agent.id)

        return errors

    def _topological_sort(
        self,
        agents: list,
        dependencies: dict[str, set[str]],
    ) -> list:
        """Kahn's algorithm topological sort. Returns agents in execution order."""
        # in-degree count: in_degree[node] = number of nodes that must precede it
        in_degree: dict[str, int] = {a.id: len(dependencies.get(a.id, set())) for a in agents}

        queue: deque = deque()
        for agent in agents:
            if in_degree[agent.id] == 0:
                queue.append(agent)

        result: list = []
        while queue:
            current = queue.popleft()
            result.append(current)
            # Find agents that depend on current
            for agent in agents:
                if current.id in dependencies.get(agent.id, set()):
                    in_degree[agent.id] -= 1
                    if in_degree[agent.id] == 0:
                        queue.append(agent)

        return result
