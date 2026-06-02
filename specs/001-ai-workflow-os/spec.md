# Feature Specification: IdeaFlowAI — Universal AI Workflow Orchestration Engine

**Feature Branch**: `001-ai-workflow-os`  
**Version**: 3.0 (Merged — Option C)  
**Created**: 2026-05-29  
**Status**: Finalized for Spec Kit  
**Governed by**: `.specify/memory/constitution.md`

> **Merge strategy**: This specification combines the Universal Execution Engine and typed artifact contracts from the new requirements document with the Deep Planner Agent, Planning_Context intelligence, and Agent Thinking UI from the original 001-ai-workflow-os spec. The result is a single, coherent platform that delivers both the solid engineering foundation and the planning intelligence.

---

## 1. Introduction

Today, three separate execution runners implement bespoke variants of the same execution pattern. Agents couple to one another by identity through `context_from: [agent-ids]`, context flows as ephemeral in-memory text summaries, and workflow state is lost on backend restart. Pipelines fire immediately on user input with no planning stage, and there is no persistent artifact store.

This feature converges the three runners into **one universal execution engine**, adopts the GitHub Spec Kit methodology as constant engine behavior, adds a mandatory **Deep Planner Agent** that infers hidden requirements before any domain agent runs, and introduces a **persistent typed Artifact_Store** that replaces ephemeral summaries. The result is a planning-first, artifact-driven, composable AI Workflow Operating System.

### What This Spec Covers

- Universal Execution Engine replacing all three runners
- Typed Produces/Consumes contract model replacing `context_from` wiring
- DAG Wiring, Validation, and Visual Dependency Graph
- Deep Planner Agent with proactive constraint inference
- Spec Kit Agents as reusable runtime agents (Constitution, Specify, Clarify, Research, Plan, Tasks, Analyze)
- Declared Gates (Human_Gate, Validation_Gate) as AGENT.md properties
- Declared Injection Capability for template/design-system/craft injection
- Persistent, versioned, lineage-tracked Artifact_Store
- Workflow State Machine with full lifecycle and backend-restart resumability
- Cross-session Constitution Memory (per-user Workflow_Memory)
- Custom composable workflows (arbitrary DAGs of 1–50 agents)
- Revision intelligence with section-level targeting
- Agent Thinking tab (live reasoning, tool calls, input prompts, context sources)
- Schema-debt migration prerequisite
- Backward compatibility with all 14 existing pipeline types

### What This Spec Does NOT Cover

- Vector/semantic artifact search (pgvector) — clean insertion point reserved
- Distributed task queues (Celery, Temporal, Kafka) — clean insertion point reserved
- Redis pub/sub — clean insertion point reserved
- Multi-instance concurrent execution — single-process deployment assumed
- The Spec Kit `implement` phase as a runtime agent — generation is performed by existing Domain_Agents

---

## 2. Glossary

- **Execution_Engine**: The single universal runner replacing `WorkflowOrchestrator.execute()`, `run_od_prototype_pipeline`, and `run_od_ppt_pipeline`. Provides stepped execution, persistent-workspace file sharing, forward-only artifact handoff, gates, and Planning_Context injection.
- **Methodology**: Constant engine behavior — stepped execution, persistent file-based context handoff, forward-only artifact flow, a supreme constitution, declared gates, and Planning_Context enrichment. Identical regardless of which agents a Workflow contains.
- **Workflow**: A composed, persisted DAG of Agents. May contain Spec_Kit_Agents, Domain_Agents, or both.
- **Agent_Spec**: The parsed representation of an `AGENT.md` file (YAML frontmatter + markdown prompt body).
- **Agent**: A runtime DeepAgent instance created from an Agent_Spec by `backend/agents/factory.py`.
- **Spec_Kit_Agent**: A reusable Agent adapted from a GitHub Spec Kit command. Set: Constitution_Agent, Specify_Agent, Clarify_Agent, Research_Agent, Plan_Agent, Tasks_Agent, Analyze_Agent.
- **Domain_Agent**: Any non-Spec-Kit Agent (e.g., `material-analyzer`, `html-prototype-builder`, `domain-analyst`, `epic-architect`, migration agents).
- **Deep_Planner_Agent**: A special Domain_Agent that runs before every Workflow. Proactively infers hidden constraints, produces a `planning_context` Artifact, and issues a gate verdict (PROCEED or CLARIFY_REQUIRED). Distinct from the Clarify_Agent (which is reactive).
- **Artifact**: A persistent, typed, versioned unit of work product produced by an Agent.
- **Artifact_Type**: The declared type label of an Artifact (e.g., `"spec"`, `"research"`, `"plan"`, `"planning_context"`, `"clarifications"`).
- **Produces_Contract**: The set of Artifact_Types an Agent declares it produces.
- **Consumes_Contract**: The set of Artifact_Types an Agent declares it requires as input.
- **Workflow_Resolver**: The Execution_Engine component that computes the DAG by matching Produces_Contract types to Consumes_Contract types and validates the Workflow before run.
- **Artifact_Store**: The `workflow_artifacts` persistence store — one row per Artifact version per run — with fields: `type`, `name`, `content`, `version`, `schema_version`, producing agent id, `derived_from_artifact_id`.
- **Planning_Context**: A typed Artifact (`"planning_context"`) produced by the Deep_Planner_Agent. Contains inferred intent, explicit and implicit constraints, missing information, execution strategy, and gate verdict. Consumed by all downstream agents as a guardrail.
- **Workspace**: The per-run file store (`AgentWorkspace`), write-through persistent against the Artifact_Store.
- **Gate**: A declared AGENT.md property causing the Execution_Engine to pause. Human_Gate pauses for user input; Validation_Gate pauses or blocks on CRITICAL findings.
- **Injection_Capability**: A declared AGENT.md capability causing the Execution_Engine to inject template, design_system, and craft content into the Agent's system prompt.
- **Clarify_Engine**: The Execution_Engine component that runs the Clarify_Agent, manages its Human_Gate, drives the QuestionnairePanel, and persists answers to Workflow_Clarifications.
- **Workflow_Clarifications**: The `workflow_clarifications` persistence store holding Q&A pairs per run.
- **Constitution**: The governing principles document with supreme authority over a Workflow.
- **Workflow_Memory**: The `workflow_memory` persistence store (per-user key/value) holding the Constitution and reusable domain knowledge.
- **WorkflowRun**: The `workflow_runs` row representing a single Workflow execution.
- **Revision_Run**: A WorkflowRun with `parent_run_id` referencing an originating run.
- **State_Machine**: The set of WorkflowRun lifecycle states and DB-persisted transitions.
- **PreviewPanel**: The existing right-hand frontend panel (Preview tab + Files tab) gaining a Thinking tab.
- **Thinking_Tab**: The new third tab in PreviewPanel showing per-agent live reasoning, tool calls, tool results, input prompts, and context sources.
- **QuestionnairePanel**: The existing frontend panel for clarification questions — visuals unchanged.
- **WebSocket_Event_Envelope**: The existing event message shape `{"type": ..., "data": {...}}`.
- **Schema_Migration**: An Alembic migration bringing the DB schema in line with declared ORM columns.

---

## 3. User Scenarios & Testing

### User Story 1 — Guided Pipeline Execution with Planning (Priority: P1)

As a user submitting a pipeline request, I want the system to automatically analyze my brief, infer what I actually need, and confirm it is ready to proceed — so that agents receive a complete, well-understood brief and produce higher-quality outputs without me having to re-run the pipeline.

**Independent Test**: Submit a `user_stories` pipeline. Verify `planner_start` WS event arrives before `pipeline_start`. Verify `planner_complete` contains a `planning_context` Artifact with `execution_gate: "PROCEED"`. Verify domain agents run and their outputs reflect inferred constraints the user did not state.

**Acceptance Scenarios**:
1. **Given** a user submits a pipeline request, **When** the pipeline starts, **Then** the Deep_Planner_Agent runs first, produces a `planning_context` Artifact, and emits a visible planning summary before any domain agent begins.
2. **Given** the planning stage completes with PROCEED, **When** domain agents run, **Then** each agent's output reflects the Planning_Context (inferred personas, NFRs, tech constraints) even if the user did not state them.
3. **Given** the planning stage determines critical information is missing, **When** the gate verdict is CLARIFY_REQUIRED, **Then** the pipeline pauses and the Clarify_Engine presents targeted questions before any domain agent runs.
4. **Given** a planning timeout occurs (exceeds 15 seconds), **When** the timeout fires, **Then** the system emits a visible timeout notice and defaults to PROCEED without blocking the pipeline.

---

### User Story 2 — Resumable Clarification (Priority: P2)

As a user whose pipeline is paused for clarification, I want to answer targeted questions and have the pipeline resume from where it stopped — so that I do not lose work and agents receive my answers as enriched context.

**Independent Test**: Trigger a CLARIFY_REQUIRED verdict. Wait >15 seconds. Submit answers. Verify pipeline resumes from the gate (not from the beginning). Verify 0 pipeline restarts. Verify answers are persisted to Workflow_Clarifications and survive a backend restart.

**Acceptance Scenarios**:
1. **Given** the gate verdict is CLARIFY_REQUIRED, **When** questions are presented, **Then** the pipeline remains paused indefinitely — no 15-second timeout.
2. **Given** the user submits answers, **When** answers are processed, **Then** the pipeline resumes from the gate with answers merged into the `planning_context` Artifact.
3. **Given** the backend restarts while the pipeline is paused, **When** the user reconnects, **Then** the pending questions and already-submitted answers are restored within 5 seconds.
4. **Given** three clarification rounds have occurred, **When** the third round completes, **Then** the pipeline proceeds with best available context and emits `clarification_limit_reached`.

---

### User Story 3 — Agent Execution Transparency (Priority: P3)

As a user watching a pipeline run, I want to see each agent's live reasoning, tool calls, input prompts, and context sources — so that I understand why the output looks the way it does.

**Independent Test**: Run any pipeline. Switch to the Thinking tab. Verify each agent card shows live reasoning text, tool calls with args and results, the full input prompt, and context sources with compression ratios. Verify the tab is accessible during live execution and in Workflow History.

**Acceptance Scenarios**:
1. **Given** a pipeline is running, **When** the user switches to the Thinking tab, **Then** the tab shows a live card per agent with reasoning text, tool calls, and tool results ordered chronologically.
2. **Given** an agent has completed, **When** the user expands its card, **Then** the card shows: full input prompt, context sources (which agents contributed and compression ratio), tool calls with args and results, and full output.
3. **Given** a pipeline has completed, **When** the user views the run in Workflow History, **Then** the Thinking tab is available and populated from persisted `agent_outputs`.
4. **Given** an `agent_thinking`, `tool_call`, or `tool_result` event arrives, **When** the Thinking tab is selected, **Then** the event content renders within 1 second of receipt.

---

### User Story 4 — Intelligent Revision with Lineage (Priority: P4)

As a user running a revision, I want the system to automatically retrieve the original planning context and artifact history — so that the revision agent understands original intent without me re-explaining it.

**Independent Test**: Complete a pipeline. Run a revision with a targeted instruction. Verify the revision agent receives the original `planning_context` Artifact, the artifact being revised, and the revision instruction as three separate structured inputs. Verify unchanged content is byte-for-byte identical to the prior version.

**Acceptance Scenarios**:
1. **Given** a user runs a revision on a completed run, **When** the revision starts, **Then** the revision agent receives the original `planning_context` Artifact, the artifact being revised, and the revision instruction as three separate structured inputs — not concatenated.
2. **Given** a revision instruction targets a specific section, **When** the revision agent produces output, **Then** all content outside the targeted section is byte-for-byte identical to the prior version.
3. **Given** a revision completes, **When** the user views history, **Then** the Artifact_Store shows the revision as a new version with `derived_from_artifact_id` referencing the prior version.

---

### User Story 5 — Custom Composable Workflows (Priority: P5)

As a power user, I want to compose arbitrary agent DAGs from any agent in the arsenal — so that I can build custom pipelines with any combination of Spec_Kit_Agents and Domain_Agents.

**Independent Test**: Compose a Workflow with `constitution → specify → clarify → material-analyzer → html-prototype-builder`. Submit it. Verify the Workflow_Resolver validates the DAG, the visual dependency graph renders, and the Execution_Engine runs all agents in topological order.

**Acceptance Scenarios**:
1. **Given** a user composes a Workflow with agents from the arsenal, **When** the Workflow is submitted, **Then** the Workflow_Resolver validates the DAG and rejects unsatisfiable workflows before any agent runs.
2. **Given** a valid custom Workflow is submitted, **When** it executes, **Then** the Execution_Engine applies identical Methodology behavior (planning gate, artifact handoff, gates) regardless of which agents the Workflow contains.
3. **Given** a Workflow contains an unsatisfied Consumes_Contract, **When** the user views the dependency graph, **Then** unsatisfied edges are visually distinct from satisfied edges.

---

### User Story 6 — Workflow Session Continuity (Priority: P6)

As a user returning to a previous workflow, I want the system to remember planning context and artifact history — so that follow-up pipelines and revisions benefit from accumulated knowledge across sessions.

**Independent Test**: Complete a pipeline. Close the browser. Reopen it. Run a revision. Verify the revision agent receives the original `planning_context` Artifact from DB (not in-memory). Verify the Workflow_Memory Constitution is injected as a guardrail.

**Acceptance Scenarios**:
1. **Given** a pipeline completed in a previous session, **When** the user initiates a revision in a new session, **Then** the system retrieves the original `planning_context` Artifact from the Artifact_Store and injects it into the revision pipeline.
2. **Given** a user has a Constitution in their Workflow_Memory, **When** any pipeline runs, **Then** the Constitution is injected into every agent's system prompt as a guardrail.

---

### Edge Cases

- **Browser closed during CLARIFY_REQUIRED**: Pipeline remains in `waiting_for_user` state. On reconnect, questions and prior answers restored within 5 seconds.
- **Pipeline cancelled in `waiting_for_user`**: Run marked `cancelled`; all persisted Artifacts retained; no domain agents have run.
- **Semantic Memory / Artifact_Store retrieval failure for revision**: Pipeline halts with `state_restoration_failed` error. Revision MUST NOT proceed without original context.
- **Unsatisfiable Workflow submitted**: Workflow_Resolver rejects before any agent runs; reports every unmatched Artifact_Type.
- **Backend restart during non-terminal run**: WorkflowRun restored from DB within 30 seconds of backend startup.
- **Artifact_Store write failure**: Execution_Engine surfaces error, does not mark agent step as complete, does not leave partial Artifact row.
- **Deep Planner timeout (>15s)**: Emits `planner_timeout`, defaults to PROCEED, pipeline continues.
- **Custom workflow user selects 0 agents**: Workflow_Resolver rejects with "minimum 1 agent required."
- **Thinking tab opened for pre-migration pipeline**: Shows "Input data not available for this pipeline run" gracefully.

---

## 4. Functional Requirements

### FR-001 — Universal Execution Engine
The system MUST execute every Workflow through a single entry point, replacing `WorkflowOrchestrator.execute()`, `run_od_prototype_pipeline`, and `run_od_ppt_pipeline`. The Execution_Engine MUST apply identical Methodology behavior to every Workflow regardless of which agents it contains.

### FR-002 — Deep Planner Agent (Proactive Planning)
The Deep_Planner_Agent MUST execute before every Workflow as the first step. It MUST be implemented as a LangGraph DeepAgent (ReAct) with `max_iterations: 20`. It MUST proactively infer hidden constraints (personas, NFRs, tech stack, compliance) not stated by the user, produce a `planning_context` Artifact, and issue a gate verdict of PROCEED or CLARIFY_REQUIRED. It MUST complete within 15 seconds; on timeout, emit `planner_timeout` and default to PROCEED. The `planning_context` Artifact MUST be consumed by all downstream agents as a guardrail. When the gate verdict is CLARIFY_REQUIRED, the Execution_Engine MUST invoke the Clarify_Engine, which runs the Clarify_Agent and manages the Human_Gate. The Deep_Planner_Agent does not directly invoke the Clarify_Agent — the Execution_Engine mediates between them.

### FR-003 — Typed Produces/Consumes Contract Model
Every Agent_Spec MUST support optional `produces` and `consumes` frontmatter fields declaring lists of Artifact_Type strings (0–50 entries, each 1–100 characters). The Loader MUST wire agents by type matching and MUST NOT use `context_from` for wiring. Legacy `context_from` fields MUST parse without error to allow incremental migration; the Execution_Engine MUST ignore `context_from` for wiring. All 76+ existing AGENT.md files MUST have `produces`/`consumes` contracts assigned before Phase 2 deployment — during Phase 2 migration, agents are wired exclusively by contracts, not by `context_from`.

### FR-004 — DAG Wiring and Validation
The Workflow_Resolver MUST compute the Workflow DAG by exact, case-sensitive Artifact_Type matching. It MUST reject unsatisfiable workflows (unmatched Consumes_Contract types or dependency cycles) before any agent runs, reporting every unmatched type. When a Consumes_Contract Artifact_Type is produced by more than one upstream Agent, the Workflow_Resolver MUST resolve the dependency to the nearest upstream producer (fewest DAG edges), breaking ties by selecting the producer that appears latest in declared Agent order. It MUST complete validation before execution starts.

### FR-005 — Visual Dependency Graph
The frontend MUST render the computed dependency graph within the existing agent-detail presentation surface — one node per agent, one directed edge per resolved producer-to-consumer Artifact_Type relationship. Unsatisfied edges MUST be visually distinct from satisfied edges.

### FR-006 — Spec Kit Agents as Runtime Agents
The following Spec_Kit_Agents MUST reside in `backend/agents/prompts/{id}/AGENT.md` and be available in any Workflow: Constitution_Agent, Specify_Agent, Clarify_Agent, Research_Agent, Plan_Agent, Tasks_Agent, Analyze_Agent. Each MUST declare appropriate produces/consumes contracts as follows:
- **Constitution_Agent**: `produces: ["constitution"]`
- **Specify_Agent**: `produces: ["spec"]`
- **Clarify_Agent**: `consumes: ["spec", "brief"]`, `produces: ["clarifications"]`
- **Research_Agent**: `produces: ["research"]`
- **Plan_Agent**: `consumes: ["spec", "research"]`, `produces: ["plan", "data_model", "contracts"]`
- **Tasks_Agent**: `consumes: ["plan"]`, `produces: ["tasks"]`
- **Analyze_Agent**: `consumes: ["spec", "plan", "tasks"]`, `produces: ["analysis_report"]`, `gate: Validation_Gate`

The Spec Kit `implement` phase is NOT realized as a runtime agent — generation is performed by existing Domain_Agents wired downstream by Artifact_Type.

### FR-007 — Declared Gates
Agent_Spec MUST support an optional `gate` field with value `Human_Gate` or `Validation_Gate`. Human_Gate pauses the Workflow for user input with no automatic timeout. Validation_Gate blocks on CRITICAL findings. Any agent in any Workflow can declare a gate — no per-Workflow manual configuration required. The Analyze_Agent MUST declare a Validation_Gate; findings conflicting with the Constitution MUST be classified CRITICAL.

**Validation_Gate resolution (soft block)**: When a Validation_Gate fires, the Execution_Engine MUST emit a `validation_gate_blocked` WS event and pause execution. The frontend MUST present the CRITICAL findings to the user with two explicit actions: **"Proceed anyway"** (override — pipeline continues with findings logged as acknowledged) and **"Cancel run"** (run transitions to `cancelled`). There is no automatic timeout — the gate remains open until the user acts. The override decision MUST be persisted to the WorkflowRun record (`gate_override: true`, `gate_override_at: timestamp`) for audit purposes. No inline spec editing or re-triggering of the Analyze_Agent is supported in this phase.

### FR-008 — Declared Injection Capability
Agent_Spec MUST support an `injects` field declaring a subset of `[template, design_system, craft]`. When declared, the Execution_Engine MUST compose the system prompt by injecting content in the order: critical output rules → design system → craft rules → template skill body → agent role prompt — byte-for-byte identical to the current `od_runner.py` output for the same inputs. For deck agents (`od_ppt`), the design system MUST be injected only when the template declares `design_system.requires == true` or a custom design-system body is supplied, matching the current behavior of `run_od_ppt_pipeline`. If an Agent declaring an Injection_Capability references a template that cannot be located, the Execution_Engine MUST report a descriptive error identifying the missing resource and halt the Workflow before any Agent executes.

### FR-009 — Unified Clarify Gate
The Clarify_Engine MUST present questions through the existing QuestionnairePanel (visuals unchanged). It MUST operate in spec-grounded mode (when a `spec` Artifact exists) or brief-grounded mode (when no `spec` Artifact exists). The Clarify_Agent MUST classify detected ambiguities using the 11-category ambiguity taxonomy, ask between 0 and 5 questions where the count does not exceed the number of detected ambiguities, and present one question at a time each with exactly one recommended answer. It MUST persist every Q&A pair to Workflow_Clarifications. The WorkflowRun MUST be created immediately when the user submits a pipeline request — before the Deep_Planner_Agent executes — so that both the planning stage and the clarification gate are resumable across reconnect and backend restart. On reconnect, pending questions and prior answers MUST be restored within 5 seconds. Clarification results MUST be consumed as a structured `clarifications` Artifact — the retired `=== USER PREFERENCES ===` prompt block MUST NOT be used.

### FR-010 — Persistent, Versioned, Lineage-Tracked Artifact_Store
The Artifact_Store MUST persist one row per Artifact version per run with fields: `type`, `name`, `content`, `version`, `schema_version`, producing agent id, `derived_from_artifact_id`. Every Artifact write MUST occur before the Artifact is made available to downstream agents. `AgentWorkspace.write_file` MUST persist to the Artifact_Store (write-through) with `type: "workspace_file"` and `name` equal to the file path; workspace files are available to downstream agents that declare `"workspace_file"` in their Consumes_Contract. All Artifact versions MUST be retained — no deletion or overwrite. Round-trip equality MUST be guaranteed. If a write fails, the Execution_Engine MUST surface an error and NOT mark the agent step as complete.

### FR-011 — Workflow State Machine and Resumability
WorkflowRun MUST include `parent_run_id`. The State_Machine MUST support lifecycle states: `clarifying`, `waiting_for_user`, `planning`, `analyzing`, `generating`, `revising`, `completed`, `failed`, `cancelled`. The `specifying` state has been removed — the Specify_Agent runs inside a Workflow as a standard agent step and does not warrant a dedicated top-level WorkflowRun state. State mapping: WorkflowRun transitions to `planning` when the Deep_Planner_Agent begins, to `clarifying` when the Clarify_Engine opens its gate, to `waiting_for_user` while paused for user input, and to `generating` when domain agents begin. Every state transition MUST be persisted to DB before execution of the new state begins. In Phases 1–2, state is persisted in-memory only; DB persistence of state transitions is introduced in Phase 3. On backend restart, non-terminal WorkflowRuns MUST be restored and resumed within 30 seconds. Runs in `waiting_for_user` MUST remain resumable indefinitely across restarts.

### FR-012 — Cross-Session Constitution Memory
Workflow_Memory MUST persist per-user key/value entries (key: 1–255 chars; value: up to 1,048,576 chars; up to 1,000 entries per user). The Constitution MUST be retrieved from Workflow_Memory and injected into every governed agent's system prompt as a guardrail. Per-Workflow Constitution overrides per-user Constitution. Entries MUST be available across sessions and backend restarts. Entries MUST NOT be exposed to other users.

**Constitution editor UI**: The frontend MUST provide a dedicated "My Constitution" section within the existing Settings page (`frontend/src/app/settings/` or equivalent). The section MUST allow the user to write, edit, and save their Constitution as free-form text. On save, the frontend calls a REST endpoint (`PUT /api/user/constitution`) which writes to `workflow_memory` via `WorkflowMemory.set_constitution(user_id, content)`. The saved Constitution is displayed on next page load. A "Clear" action removes the Constitution entry. No per-run Constitution prompt is shown — the Constitution is silently injected by the engine.

### FR-013 — Custom Composable Workflows
The Execution_Engine MUST allow composition of Workflows with 1–50 agents from any agent in the arsenal. The Deep_Planner_Agent is automatically prepended to every Workflow and does NOT count toward the 1–50 agent limit. The Workflow definition (agents, edges, Constitution reference) MUST be persisted and retrievable after restart. The Workflow_Resolver MUST validate every custom Workflow before execution. All Spec_Kit_Agents MUST be available to any custom Workflow.

### FR-014 — Revision Intelligence
A revision request MUST create a new WorkflowRun with `parent_run_id`. The revision agent MUST receive the original Artifact, version history, and revision instruction as three separate structured inputs — NOT concatenated. When a revision instruction targets a specific section, content outside that section MUST be byte-for-byte identical to the prior version. The Artifact_Store MUST store the result as a new version with `derived_from_artifact_id`. Revision requests referencing non-existent Artifacts or with empty instructions MUST be rejected before creating a WorkflowRun. If a revision request references a run completed before Phase 3 (no Artifact_Store entries exist), the Execution_Engine MUST proceed without the `planning_context` Artifact and annotate the run with `planning_context_unavailable: true`.

### FR-015 — Thinking Tab
The PreviewPanel MUST present exactly three tabs in order: Preview (default), Files, Thinking. The Thinking tab MUST display content grouped by agent showing: reasoning text from `agent_thinking` events, tool invocations from `tool_call` events, tool results from `tool_result` events, full input prompt, and context sources — all ordered chronologically. For agents receiving summarized prior-agent outputs, context sources MUST show which agents contributed and the compression ratio (summary_length vs. full_output_length). For agents receiving typed Artifacts via Consumes_Contract, context sources MUST show the `artifact_type` and `artifact_size_chars` instead of a compression ratio. Events MUST render within 1 second of receipt. The Thinking tab MUST retain all content until a new run begins. The Thinking tab MUST be available in Workflow History populated from persisted `agent_outputs`.

### FR-016 — Scoped Context Isolation
The Execution_Engine MUST supply each agent ONLY the Artifacts whose Artifact_Types are declared in that agent's Consumes_Contract. Artifacts of undeclared types MUST be excluded. The `planning_context` Artifact is an exception: it MUST be supplied to ALL agents regardless of their Consumes_Contract (it is a cross-cutting guardrail, not a workflow artifact). For standard pipelines, `planning_context` MUST be injected into the agent's system prompt as a `## Planning Context` block after hooks and before the AGENT.md prompt body. For `od_prototype` and `od_ppt` pipelines, `planning_context` MUST be injected into the user message (not the system prompt) to preserve the template/design-system system prompt composition order. Agents with empty Consumes_Contract receive only the user brief, the Constitution guardrail, and the `planning_context` Artifact.

### FR-017 — Preservation of Existing Preview and Streaming Behavior
The Execution_Engine MUST emit events using the existing WebSocket_Event_Envelope shape. `agent_chunk` events MUST be emitted incrementally in generation order. Code-writing agents MUST serialize workspace files using the existing `filename:` code-block format. The AgentProgressPanel and PreviewPanel MUST present the same visual layout as the pre-migration baseline — the Thinking tab is the only permitted addition.

### FR-018 — Schema-Debt Prerequisite Migration
A Schema_Migration MUST add any genuinely missing ORM columns before any new schema lands. **Codebase audit**: migrations `0005`–`0008` already add `users.tier`, `users.is_admin`, `users.preferred_model`, and `workflow_runs.model_id`. Migration `0004` adds `workflow_runs.token_usage`. Implementers MUST audit existing migrations before creating `0009_schema_debt.py` — only columns confirmed absent from all existing migrations should be added. This migration MUST be ordered before any migration introducing the Artifact_Store, Workflow_Clarifications, Workflow_Memory, `parent_run_id`, or extended `status`. Each added column MUST have a downgrade defined. If all schema-debt columns are already present, a no-op migration with an audit comment is acceptable.

### FR-019 — Migration and Backward Compatibility
Every existing pipeline (`prototype`, `od_ppt`, `app_builder`, `user_stories`, migration pipelines) MUST be converted to a Workflow definition executable by the Execution_Engine, preserving existing agent ordering. Every existing Agent_Spec MUST be assigned `produces` and `consumes` contracts such that the resolved DAG reproduces the upstream-to-downstream dependencies previously expressed by `context_from`. No in-flight WorkflowRun created under a legacy runner MUST be left in a non-terminal, non-resumable state at cutover.

### FR-020 — Deep Agents Only
All agents MUST be LangGraph DeepAgent (ReAct) instances. BaseAgent (single LLM call, stateless, no tools) MUST NOT be used in any new or migrated pipeline. The summarizer and title generator MUST be migrated to DeepAgent with `tools=[], max_iterations=1` (utility functions — `tools=[]` is intentional).

### FR-021 — Test-First for New Modules
Unit tests for the Execution_Engine, Artifact_Store, Workflow_Resolver, Clarify_Engine, State_Machine, and Workflow_Memory MUST be written before or alongside implementation. The pytest suite MUST pass at every phase boundary with zero regressions.

### FR-022 — Foundational Extensibility
The Artifact_Store MUST assign a non-null `schema_version` to every Artifact. The persistence schema MUST permit vector search, distributed task queues, and Redis pub/sub to be added later through additive changes only. Previously stored Artifacts MUST be returned without error when new optional fields are added.

### FR-023 — Observability
The Execution_Engine MUST emit structured JSON logs for all significant lifecycle events: WorkflowRun creation, state transitions, agent start/complete/error, gate open/close, planner timeout, and Artifact_Store write failures. Each log entry MUST include: `timestamp`, `pipeline_run_id`, `event_type`, `agent_id` (where applicable), `duration_ms` (where applicable), and `error` (where applicable). The following pipeline metrics MUST be tracked and available for export to existing infrastructure: per-agent latency (ms), Deep_Planner_Agent latency (ms), gate outcome counts (PROCEED / CLARIFY_REQUIRED / override / cancel), pipeline failure rate by pipeline type, and Artifact_Store write failure count. Distributed tracing (OpenTelemetry) is a clean insertion point reserved for a future phase — not required in this spec.

---

## 5. Key Entities

- **Planning_Context** (`"planning_context"` Artifact_Type): Produced by Deep_Planner_Agent. Contains inferred intent, explicit constraints, implicit constraints, missing information, execution strategy, gate verdict. Consumed by ALL agents as a cross-cutting guardrail regardless of their Consumes_Contract.
- **Artifact**: Persistent, typed, versioned unit of work. Fields: `type`, `name`, `content`, `version`, `schema_version`, `producing_agent_id`, `derived_from_artifact_id`, `workflow_run_id`.
- **Artifact_Store** (`workflow_artifacts` table): One row per Artifact version per run. Immutable — no deletes or overwrites.
- **Workflow_Clarifications** (`workflow_clarifications` table): Per-run Q&A pairs from the Clarify_Engine. Structured, not a JSON blob.
- **Workflow_Memory** (`workflow_memory` table): Per-user key/value store. Holds Constitution and reusable domain knowledge. Available across sessions.
- **WorkflowRun** (`workflow_runs` table): Extended with `parent_run_id`, `status` (full lifecycle), `session_id`, `pipeline_run_id`, `execution_gate`, `execution_strategy`.
- **Workflow** (`workflows` table — NEW): Persisted DAG definition. Fields: `id`, `user_id`, `name`, `agents` (ordered list), `artifact_edges` (producer→consumer type mappings), `constitution_ref`, `created_at`.
- **AgentThinkingEntry**: Per-agent transparency record in `agent_outputs` JSON. Fields: `agent_id`, `name`, `role`, `icon`, `output`, `duration`, `input_prompt`, `context_sources` (list of `{agent_id, agent_name, summary_length, full_output_length}` for summarized inputs OR `{artifact_type, artifact_size_chars}` for typed Artifact inputs), `tool_calls`, `thinking_text`.
- **Gate**: Declared AGENT.md property. Values: `Human_Gate` (pause for user input), `Validation_Gate` (soft block on CRITICAL findings — user must explicitly "Proceed anyway" or "Cancel run").
- **Injection_Capability**: Declared AGENT.md `injects` field. Values: subset of `[template, design_system, craft]`.

---

## 6. Success Criteria

- **SC-001**: Every pipeline type in `SUPPORTED_PIPELINE_TYPES` executes through the universal Execution_Engine — 0 legacy runner calls remain.
- **SC-002**: The Deep_Planner_Agent completes in under 15 seconds for all standard pipeline types.
- **SC-003**: Total time from pipeline submission to first domain agent starting (planning + clarification if triggered) does not exceed 30 seconds.
- **SC-004**: All 14 existing pipeline types pass structural regression after migration — verified by: correct agent execution sequence, all expected WebSocket events emitted in order, all expected workspace files produced, and zero regressions in the existing pytest suite at each phase boundary. Subjective output quality is not a CI gate.
- **SC-005**: Revision pipelines receive the original `planning_context` Artifact automatically — 0 instances of users needing to re-state the original brief.
- **SC-006**: The Thinking tab renders `agent_thinking`, `tool_call`, and `tool_result` events within 1 second of receipt.
- **SC-007**: WorkflowRuns in non-terminal states are restored and resumed within 30 seconds of backend restart.
- **SC-008**: Clarification questions and prior answers are restored within 5 seconds of user reconnect to a paused run.
- **SC-009**: Custom Workflows with arbitrary agent combinations are validated by the Workflow_Resolver before execution — 0 unsatisfiable workflows start running.
- **SC-010**: The Artifact_Store guarantees round-trip equality — content read back is byte-for-byte equal to content written.
- **SC-011**: Zero existing AGENT.md prompt bodies are modified during migration — only `produces`/`consumes` frontmatter fields are added.
- **SC-012**: The Thinking tab in Workflow History is populated for 100% of runs completed after Phase 3 deployment.
- **SC-013**: Every WorkflowRun state transition, agent lifecycle event, and gate outcome produces a structured JSON log entry containing `timestamp`, `pipeline_run_id`, `event_type`, and `duration_ms` where applicable.

---

## 7. Assumptions

- Single-process, single-EC2 deployment. Concurrent execution of independent DAG branches and multi-worker fan-out are deferred.
- Migration is a one-time cutover during a deployment window. Legacy runners and universal engine do not run simultaneously for the same Workflow.
- LLM provider (AWS Bedrock / Anthropic) and existing DeepAgent execution model remain unchanged.
- In-memory storage is sufficient for Phases 1–2; DB migrations are Phase 3 only.
- The `migration` meta-pipeline type resolves to its concrete sub-type before WorkflowRun creation.
- The Spec Kit `implement` phase is not a runtime agent — generation is performed by existing Domain_Agents wired downstream by Artifact_Type.
- Latency bounds (5s clarification restore, 30s run resume, 1s Thinking tab render) assume single-instance deployment under nominal load.
- All existing tests must pass at every phase boundary; no phase is complete if existing tests regress.

---

## 8. Implementation Phases

### Phase 1 — Foundation (zero behavior change)
- Schema-debt migration (FR-018): add missing ORM columns
- `workflow_artifacts` table, `workflow_clarifications` table, `workflow_memory` table, `workflows` table
- `produces`/`consumes` fields added to Agent_Spec and Loader (backward compatible)
- `gate` and `injects` fields added to Agent_Spec (backward compatible)
- Workflow_Resolver scaffold (validates but does not yet gate execution)
- WorkflowState extended with new optional fields
- Artifact_Store in-memory implementation
- All existing pipelines work identically

### Phase 2 — Universal Engine + Planning Gate
- Execution_Engine replaces all three runners
- Deep_Planner_Agent AGENT.md + planning tools
- Clarify_Engine with Human_Gate and asyncio.Event pause/resume
- Spec_Kit_Agents AGENT.md files (Constitution, Specify, Clarify, Research, Plan, Tasks, Analyze)
- Declared Gates active for all agents
- Declared Injection_Capability replaces od_runner.py bespoke injection
- All 14 pipelines migrated to Workflow definitions with produces/consumes contracts
- `context_from` retired for wiring (parsed but ignored); all 76+ AGENT.md files assigned contracts
- In Phase 2, the `planning_context` Artifact is produced and stored in the in-memory Artifact_Store. It is **not yet injected into agent system prompts** (that begins in Phase 3 per FR-016). Agents that explicitly declare `"planning_context"` in their Consumes_Contract will receive it; cross-cutting automatic injection to ALL agents regardless of Consumes_Contract is a Phase 3 behaviour.
- Frontend: questionnaire timeout removed, `planner_start`/`planner_complete`/`gate_status` events handled

### Phase 3 — Artifact_Store, Lineage, State Machine, Thinking Tab
- Artifact_Store migrated from in-memory to DB (Alembic migration)
- Full State_Machine with all lifecycle states persisted to DB
- Backend-restart resumability (WorkflowRun restored within 30s)
- Workflow_Memory (per-user Constitution + domain knowledge)
- Planning_Context injection into all agent system prompts (additive)
- `agent_input` WS event emitted per agent
- Thinking tab (PreviewPanel third tab + WorkflowHistory)
- Visual Dependency Graph in frontend
- Revision intelligence (section-level targeting, three separate structured inputs)
- Custom composable Workflow UI

### Phase 4 — Hardening
- BaseAgent → DeepAgent migration (summarizer, title generator)
- End-to-end integration tests for all 14 pipeline types through the universal engine
- Performance validation (SC-002, SC-003, SC-007, SC-008)
- Rollout guide for adding new pipeline types
- `PLANNER.md` auto-generated per run

---

*This specification is the authoritative input for Spec Kit's `/speckit-plan`, `/speckit-tasks`, and `/speckit-implement` workflow.*  
*Governed by: `.specify/memory/constitution.md` v1.0.0*  
*Supersedes: specs/001-ai-workflow-os/spec.md v2.0 and the separate new requirements document.*

---

## Clarifications

### Session 2026-05-29

- Q: When the Validation_Gate blocks a pipeline (Analyze_Agent finds CRITICAL findings), what can the user do from the UI? → A: Soft block — user sees CRITICAL findings, can choose "Proceed anyway" (override, logged with audit trail) or "Cancel run"; no auto-timeout; no inline re-triggering in this phase.
- Q: What level of observability should be built into the Execution_Engine? → A: Structured JSON logging for all lifecycle events + key pipeline metrics (per-agent latency, gate outcomes, failure rates); distributed tracing deferred to a future phase.
- Q: What should SC-004 regression tests actually verify for the 14 pipeline types? → A: Structural regression — correct agent sequence, all expected WS events emitted in order, all expected workspace files produced, zero regressions in existing pytest suite; subjective output quality is not a CI gate.
- Q: The `specifying` state in FR-011 has no defined trigger — keep or remove? → A: Remove — the Specify_Agent runs as a standard agent step inside a Workflow and does not warrant a dedicated top-level WorkflowRun state; keeping it creates dead code in the state machine.
- Q: Where should the Constitution editor UI live? → A: Settings page — dedicated "My Constitution" section; user writes/edits/saves free-form text; saved via `PUT /api/user/constitution`; silently injected by engine on every run; no per-run prompt.
