# Workflow Resolver API Contract

Module: `backend/agents/execution_engine/resolver.py`

```python
@dataclass
class ValidationResult:
    satisfiable: bool
    errors: list[str]          # empty when satisfiable
    dag: list[AgentSpec]       # topological execution order (empty when unsatisfiable)
    edges: list[DagEdge]       # resolved producer→consumer edges for display
    unresolved_edges: list[UnresolvedEdge]  # for visual graph unsatisfied display


@dataclass
class DagEdge:
    from_agent_id: str
    to_agent_id: str
    artifact_type: str


@dataclass
class UnresolvedEdge:
    consuming_agent_id: str
    artifact_type: str          # the unmatched type


class WorkflowResolver:

    def validate(self, agents: list[AgentSpec]) -> ValidationResult:
        """
        Compute and validate the Workflow DAG.

        Rules:
        - Exact, case-sensitive Artifact_Type matching
        - Unsatisfied Consumes_Contract → unsatisfiable
        - Dependency cycle → unsatisfiable
        - Multi-producer tie-break: fewest DAG edges; ties broken by latest declared order
        - Deep_Planner_Agent is always prepended; its planning_context is cross-cutting
          (not matched by type — supplied to all agents regardless of Consumes_Contract)
        - Must complete before any agent executes
        """

    def resolve_execution_order(self, agents: list[AgentSpec]) -> list[AgentSpec]:
        """
        Return agents in deterministic topological execution order.
        Raises ValueError if DAG is unsatisfiable.
        """
```

## Validation Rules

1. For each agent A with `consumes: [t1, t2, ...]`, every `ti` must be produced by at least one upstream agent
2. No cycles in the dependency graph
3. `planning_context` is exempt from type matching — it is always available to all agents
4. `constitution` Artifact is also exempt — injected from Workflow_Memory, not matched by type
5. Agents with empty `consumes` are DAG roots — they receive only the user brief + planning_context + constitution
