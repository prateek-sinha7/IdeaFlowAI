# Research: IdeaFlowAI Universal Workflow Orchestration Engine

**Date**: 2026-05-29 | **Feature**: 001-ai-workflow-os | **Version**: 3.0

---

## Decision 1: Universal Engine entry point

**Decision**: New `agents/execution_engine/engine.py` with `ExecutionEngine.execute()` as the single entry point. `orchestrator_v2.py`, `od_runner.py`, and `od_ppt_runner.py` are deleted in Phase 2 after migration is verified.

**Rationale**: Three runners implement the same pattern with diverging behavior. A single engine with declared `injects` capability reproduces od_runner's template/DS injection without bespoke code. The existing `DeepAgent` and `factory.py` are reused — no new LLM infrastructure.

**Alternatives considered**: Adapter pattern wrapping existing runners — rejected because it perpetuates divergence and makes the contract model impossible to enforce.

---

## Decision 2: Artifact_Store — in-memory Phase 1-2, DB Phase 3

**Decision**: `ArtifactStore` class with identical public interface in both phases. Phase 1-2: module-level dict. Phase 3: SQLAlchemy writes to `workflow_artifacts` table.

**Rationale**: Constitution §VI mandates in-memory for Phases 1-2. The interface abstraction means callers never change. The `asyncio.Event` for pause/resume stays in-memory even in Phase 3 (cannot be persisted).

**Alternatives considered**: Redis for Phase 1-2 — rejected (no new infrastructure per spec).

---

## Decision 3: planning_context as typed Artifact with cross-cutting exception

**Decision**: `planning_context` is a typed Artifact (`"planning_context"`) stored in the Artifact_Store. It is the one exception to scoped context isolation — supplied to ALL agents regardless of their Consumes_Contract. For standard pipelines: injected into system prompt. For od_prototype/od_ppt: injected into user message.

**Rationale**: Typed Artifact enables versioning, lineage, and cross-session retrieval. Cross-cutting exception is necessary because planning intelligence must enrich every agent — it is a guardrail, not a workflow artifact. The od_runner injection position preserves the template/DS system prompt composition order.

**Alternatives considered**: Injecting planning_context only for agents that declare it in Consumes_Contract — rejected because agents would need to be updated and the planning benefit would be opt-in rather than universal.

---

## Decision 4: Workflow_Resolver validates before execution

**Decision**: `WorkflowResolver.validate()` runs synchronously before `ExecutionEngine.execute()` starts any agent. Unsatisfiable workflows are rejected with a full error report.

**Rationale**: Failing fast before any LLM call is made saves cost and avoids partial runs. The validation is cheap (pure graph computation). The visual dependency graph is derived from the same validation output.

**Alternatives considered**: Lazy validation (validate each agent just before it runs) — rejected because it allows partial runs that waste tokens and leave the Artifact_Store in an inconsistent state.

---

## Decision 5: Spec_Kit_Agents as AGENT.md files in the shared arsenal

**Decision**: 7 Spec_Kit_Agents live in `backend/agents/prompts/{id}/AGENT.md` alongside Domain_Agents. They are available to any Workflow. The `implement` phase is NOT a runtime agent.

**Rationale**: Uniform treatment — Spec_Kit_Agents and Domain_Agents are both DeepAgents loaded by the same factory. No special-casing in the engine. The `implement` phase is excluded because generation is performed by existing Domain_Agents (prototype, app_builder, etc.) wired downstream by Artifact_Type.

**Alternatives considered**: Separate Spec_Kit_Agent registry — rejected (unnecessary complexity; the shared arsenal already supports this).

---

## Decision 6: Declared Gates as AGENT.md properties

**Decision**: `gate: Human_Gate | Validation_Gate` in AGENT.md frontmatter. The Execution_Engine reads this field and applies the gate behavior automatically — no per-Workflow configuration.

**Rationale**: Gates are a property of the agent's role, not of the workflow. The Clarify_Agent always needs a Human_Gate; the Analyze_Agent always needs a Validation_Gate. Declaring it in AGENT.md means any workflow containing these agents inherits the gate automatically.

**Alternatives considered**: Per-Workflow gate configuration — rejected because it requires workflow authors to know which agents need gates, creating a maintenance burden.

---

## Decision 7: StateMachine persists transitions before execution

**Decision**: `StateMachine.transition(run_id, new_state)` writes to DB before returning. In Phases 1-2, writes to in-memory dict. In Phase 3, writes to `workflow_runs.status`.

**Rationale**: Persisting before execution ensures that if the backend crashes mid-transition, the run is in the new state (not the old one) when restored. This is the safer failure mode — a run that appears to be in `planning` but hasn't started planning yet is recoverable; a run that appears to be in `running` but has already completed planning is not.

**Alternatives considered**: Persist after execution — rejected because it creates a window where the run is in an inconsistent state on restart.
