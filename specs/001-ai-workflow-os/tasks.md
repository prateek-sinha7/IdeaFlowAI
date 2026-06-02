# Tasks: IdeaFlowAI — Universal AI Workflow Orchestration Engine

**Feature**: `001-ai-workflow-os` | **Version**: 3.0 | **Branch**: `infra-agent-integration-deepagents`
**Input**: `specs/001-ai-workflow-os/` (spec.md v3.0, plan.md v3.0, data-model.md, contracts/)
**Governed by**: `.specify/memory/constitution.md`

> **Phase numbering note**: "Phase 1–4" in spec.md and plan.md refer to the spec's own phase labels. In this tasks.md: spec Phase 1 = tasks Phase 1–2, spec Phase 2 = tasks Phases 3–5, spec Phase 3 = tasks Phases 6–8, spec Phase 4 = tasks Phase 9.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[Story]**: User story label (US1–US6) from spec.md
- All paths are relative to repo root

---

## Phase 1: Setup — Foundation (zero behavior change)

**Purpose**: Schema-debt resolved, new AGENT.md fields scaffolded, Artifact_Store in-memory, WorkflowState extended. All 14 pipelines work identically after this phase.

**Spec coverage**: FR-018 (schema-debt), FR-003 (produces/consumes fields), FR-010 (Artifact_Store scaffold), FR-011 (WorkflowState extension), FR-004 (Resolver stub)

- [X] T001 Create `backend/app/agents/types.py` — move `WorkflowState` from `backend/app/agents/orchestrator_v2.py` to this new module; `TokenUsage` is defined in `backend/app/agents/base.py` (not in orchestrator_v2.py) — import it from `base.py` in `types.py` rather than moving it; update all imports in `orchestrator_v2.py`, `websocket.py`, and any other files that reference `WorkflowState` directly
- [X] T002 Extend `WorkflowState` in `backend/app/agents/types.py` with optional fields: `session_id`, `pipeline_run_id`, `parent_run_id`, `execution_gate`, `execution_strategy`, `artifact_refs`; generate `pipeline_run_id = uuid4()` at execute() start
- [X] T003 [P] Add optional AGENT.md frontmatter fields to `backend/agents/loader.py`: (1) extend `AgentSpec` dataclass with `produces: list[str] = field(default_factory=list)`, `consumes: list[str] = field(default_factory=list)`, `gate: str | None = None`, `injects: list[str] = field(default_factory=list)`; (2) update `_build_spec()` to parse these four fields using `_optional_list_of_str` for produces/consumes/injects and a nullable string read for gate; (3) validate gate value is one of `None`, `"Human_Gate"`, `"Validation_Gate"` — raise `AgentSpecError` for any other value; existing AGENT.md files without these fields must load unchanged with empty-list/None defaults
- [X] T004 [P] Create `backend/agents/artifact_store/__init__.py` and `backend/agents/artifact_store/store.py` — in-memory `ArtifactStore` class implementing the full interface from `specs/001-ai-workflow-os/contracts/artifact-store-api.md`: `store`, `retrieve_latest`, `retrieve_version`, `list_by_type`, `list_lineage`, `get_resume_event`, `set_questionnaire_responses`, `get_questionnaire_responses`; module-level `get_artifact_store()` singleton
- [X] T005 [P] Create `backend/agents/execution_engine/__init__.py` and `backend/agents/execution_engine/resolver.py` — `WorkflowResolver` stub with `validate(agents: list[AgentSpec]) -> ValidationResult` and `resolve_execution_order(agents) -> list[AgentSpec]`; implement DAG validation, cycle detection, unmatched-type reporting per `specs/001-ai-workflow-os/contracts/workflow-resolver-api.md`; does NOT yet gate execution
- [X] T006 Audit existing Alembic migrations before creating new ones: migrations `0005_add_user_tier.py`, `0006_add_is_admin.py`, `0007_add_preferred_model.py`, `0008_add_workflow_run_model_id.py` already add `users.tier`, `users.is_admin`, `users.preferred_model`, `workflow_runs.model_id` — these are already migrated and must NOT be re-added. Verify whether `workflow_runs.token_usage` is covered by `0004_add_token_usage.py` (read that file). Create `backend/alembic/versions/0009_schema_debt.py` ONLY for any genuinely missing columns confirmed absent from existing migrations; include downgrade; if all columns are already present, create a no-op migration with a comment documenting the audit result
- [X] T007 [P] Write unit tests in `backend/tests/unit/test_artifact_store.py` — round-trip store/retrieve, version increment, lineage chain, resume event creation, questionnaire responses
- [X] T008 [P] Write unit tests in `backend/tests/unit/test_workflow_resolver.py` — satisfiable DAG, unsatisfiable (unmatched type), cycle detection, multi-producer tie-break, planning_context exemption
- [X] T009 [P] Write unit tests in `backend/tests/unit/test_loader_new_fields.py` — backward compat: existing AGENT.md without new fields loads with defaults; new fields parse correctly; **backward-compat integration test**: an AGENT.md with only `context_from` (no `produces`/`consumes`) loads without error, executes through `ExecutionEngine` without wiring failure, and `context_from` is parsed but silently ignored for wiring purposes

**Checkpoint**: Run `pytest backend/tests/unit/` — all pass. Run `alembic upgrade head` — migration applies cleanly. All 14 pipelines execute identically.


---

## Phase 2: Foundational — Universal Engine + Planning Gate

**Purpose**: Single Execution_Engine replaces all three runners. Deep_Planner_Agent gates every pipeline. Clarify_Engine supports pause/resume. All 14 pipelines migrated to Workflow definitions with produces/consumes contracts.

**Spec coverage**: FR-001 (Universal Engine), FR-002 (Deep Planner), FR-003 (contracts), FR-004 (DAG wiring), FR-006 (Spec Kit Agents), FR-007 (Gates), FR-008 (Injection), FR-009 (Clarify Gate), FR-019 (migration), FR-020 (Deep Agents only)

**⚠️ CRITICAL**: No user story work can begin until this phase is complete. Legacy runners deleted only after **both** T016 (golden-reference) and T025 (regression) pass. T020a (BaseAgent migration — constitution §II), T021a (BaseAgent guard), and T021b (cutover script) must also complete before T021 deletion.

- [X] T010 Capture golden-reference system prompts for prototype and deck agents: run `backend/app/agents/od_runner.py` and `backend/app/agents/od_ppt_runner.py` against a fixed set of test inputs (template, design system, brief, discovery); store outputs as fixtures in `backend/tests/fixtures/golden_prototype_prompt.txt` and `backend/tests/fixtures/golden_ppt_prompt.txt`
- [X] T011 [P] Create `backend/agents/planner/__init__.py` and `backend/agents/planner/tools.py` — implement `analyze_request`, `infer_constraints`, `assess_readiness`, `build_execution_plan`, `store_planning_context`, `retrieve_planning_context` as LangChain `@tool` functions
- [X] T012 [P] Create `backend/agents/prompts/deep-planner/AGENT.md` — frontmatter: `agent_type: planner`, `tools: ["planning"]`, `max_iterations: 20`, `planning_required: false`, `produces: ["planning_context"]`; prompt body: proactively infer hidden constraints (personas, NFRs, tech stack, compliance), produce Planning_Context JSON, issue gate verdict PROCEED or CLARIFY_REQUIRED
- [X] T013 [P] Create 7 Spec_Kit_Agent AGENT.md files with correct produces/consumes contracts and gate declarations per `specs/001-ai-workflow-os/data-model.md` Section 6; **before creating these files**, add `"spec_kit"` to `SUPPORTED_PIPELINE_TYPES` in `backend/agents/loader.py` — the loader validates `pipeline_type` against this frozenset and will raise `AgentSpecError` for any unknown value; all 7 Spec_Kit_Agent AGENT.md files MUST use `pipeline_type: spec_kit`:
  - `backend/agents/prompts/constitution-agent/AGENT.md` — `produces: ["constitution"]`
  - `backend/agents/prompts/specify-agent/AGENT.md` — `produces: ["spec"]`
  - `backend/agents/prompts/clarify-agent/AGENT.md` — `consumes: ["spec","brief"]`, `produces: ["clarifications"]`, `gate: Human_Gate`
  - `backend/agents/prompts/research-agent/AGENT.md` — `produces: ["research"]`
  - `backend/agents/prompts/plan-agent/AGENT.md` — `consumes: ["spec","research"]`, `produces: ["plan","data_model","contracts"]`
  - `backend/agents/prompts/tasks-agent/AGENT.md` — `consumes: ["plan"]`, `produces: ["tasks"]`
  - `backend/agents/prompts/analyze-agent/AGENT.md` — `consumes: ["spec","plan","tasks"]`, `produces: ["analysis_report"]`, `gate: Validation_Gate`
- [X] T014 Add `produces`/`consumes` contracts to all 76+ existing AGENT.md files in `backend/agents/prompts/` — mapping algorithm: for each agent with `context_from: [agent-ids]`, set `consumes` to union of `produces` of those named agents; `context_from: []` → `consumes: []`; `context_from: ['$previous']` → `consumes` = `produces` of immediately preceding agent; do NOT add `planning_context` to any `consumes` list (cross-cutting); **special case for app_builder**: `registry.py` has `PIPELINE_CONTEXT_MAPS["app_builder"]` with explicit non-linear context routing for all 15 agents — use this map as the authoritative source for `consumes` contracts on app_builder agents (e.g., `app-code-generator` consumes from `material-analyzer`, `app-system-design`, `app-api-design`, `app-database-design`); after all 15 app_builder AGENT.md files have contracts, remove `PIPELINE_CONTEXT_MAPS` from `registry.py` — the Execution_Engine resolves routing by contract, not by this map; **note**: `reverse_engineer` pipeline has an empty agent list — skip it in migration and add it to the exclusion list in regression tests (T025)
- [X] T015 Update `backend/agents/factory.py` — **depends on T010 (golden references must exist before this task starts)**; handle `gate` field (Human_Gate/Validation_Gate); handle `injects` field: compose system prompt in order critical rules → design system → craft rules → template skill body → role prompt (byte-for-byte match to od_runner.py); deck agent conditional for design system; `_inject_constitution()` returns empty string (Phase 3 placeholder); **error path**: if `injects` is declared but the referenced template file cannot be located, raise a descriptive `TemplateMissingError` identifying the missing path — engine.py catches this and halts before any agent executes
- [X] T016 [P] Write golden-reference test in `backend/tests/unit/test_factory_injects.py` — verify `factory.py` `injects` composition produces byte-for-byte identical output to golden fixtures from T010 for prototype and deck agents
- [X] T017 Create `backend/agents/execution_engine/clarify_engine.py` — `ClarifyEngine.run(pipeline_run_id, planning_context, websocket_send_fn)`: runs Clarify_Agent, emits `questionnaire_ready`, awaits `asyncio.Event` from ArtifactStore, retrieves responses, merges into planning_context; max 3 rounds; emits `clarification_limit_reached`; spec-grounded mode (spec Artifact exists) vs brief-grounded mode
- [X] T018 Create `backend/agents/execution_engine/state_machine.py` — `StateMachine.transition(run_id, new_state)`: in-memory dict persistence (Phase 2); handles 9 lifecycle states (note: `specifying` removed — no trigger exists): `clarifying`, `waiting_for_user`, `planning`, `analyzing`, `generating`, `revising`, `completed`, `failed`, `cancelled`; persists before returning
- [X] T019 Create `backend/agents/execution_engine/engine.py` — `ExecutionEngine.execute(agents: list[AgentSpec], user_message: str, websocket_send_fn, pipeline_run_id: str)`: call `WorkflowResolver.validate(agents)` first; emit `workflow_validated` WS event; if unsatisfiable halt; prepend Deep_Planner_Agent; run planner with 15s timeout (emit `planner_timeout` on expiry, default PROCEED); evaluate gate; invoke ClarifyEngine if CLARIFY_REQUIRED; run domain agents in topological order; emit all WS events per `specs/001-ai-workflow-os/contracts/websocket-events.md`; **implement Validation_Gate blocking**: when an agent declares `gate: Validation_Gate` and produces CRITICAL findings, emit `validation_gate_blocked` WS event (fields: `pipeline_run_id`, `agent_id`, `blocking_findings`), pause execution, and await user resolution or cancellation — do NOT auto-proceed; **implement ArtifactStoreWriteError propagation**: on any `store.store()` call raising `ArtifactStoreWriteError`, surface the error to the WebSocket client, do NOT mark the agent step as complete, transition run to `failed`; **implement missing-template error**: if an agent declares `injects` but the referenced template cannot be located, emit a descriptive error identifying the missing resource and halt the Workflow before any agent executes
- [X] T020 Update `backend/app/api/websocket.py` — replaced `_handle_pipeline_execution`, `_handle_od_prototype_execution`, `_handle_od_ppt_execution` with single `_handle_workflow_execution` calling `ExecutionEngine.execute()`; unified handler forwards `template_id`, `design_system_id`, `discovery`, `custom_ds_body`, `custom_template_body`; added `submit_questionnaire` handler; removed 15s timeout; deleted `_handle_questionnaire()` and `generate_questions` handler block
- [X] T020a Migrated `_generate_workflow_title()` AND the chat title generator in `backend/app/api/websocket.py` from `BaseAgent` to `DeepAgent(tools=[], max_iterations=1)` — constitution §II compliant
- [X] T021 Deleted `backend/app/agents/orchestrator_v2.py`, `backend/app/agents/od_runner.py`, `backend/app/agents/od_ppt_runner.py` — legacy runners physically removed. Migrated 3 dependent test files: `test_orchestrator_skill_resolution.py` → `test_engine_skill_resolution.py` (engine `_load_disk_skills`), `test_pipeline_cancel.py` (now targets `_handle_workflow_execution` + stub engine), removed stale `TestOrchestratorMarkerWrap` (tested a removed code path), deleted `tests/agents/test_orchestrator.py`. Per-user disk skill loading ported into `engine._load_disk_skills` (forwards user_id — WORKFLOWS.md §B6).
- [X] T021a Added CI/grep guard in `backend/tests/unit/test_no_baseagent.py` — asserts new engine modules are BaseAgent-free (12 files guarded); runs at every phase boundary
- [X] T021b Wrote cutover script `backend/scripts/cutover_legacy_runs.py` — marks in-flight legacy WorkflowRuns as `cancelled` with `legacy_runner_cutover` annotation; supports `--dry-run`
- [X] T022 [P] Update `frontend/src/hooks/useWorkflow.ts` — handles `planner_start`, `planner_complete`, `planner_timeout`, `planner_error`, `gate_status`, `clarification_limit_reached`; tracks `pipelineRunId` from `planner_start`; added `submitQuestionnaire(pipelineRunId, responses)` sending the `submit_questionnaire` WS message. Parent `dashboard/page.tsx` routes the new events + maps `questionnaire_ready`/`questionnaire_complete` to the existing QuestionnairePanel state.
- [X] T023 [P] Update `frontend/src/components/layout/DashboardLayout.tsx` — removed the 15-second `generate_questions` pre-step and timeout; `handleRunPipeline` now starts the pipeline directly (planner gates mid-run). `handleQuestionnaireSubmit`/`handleQuestionnaireSkip` detect a mid-run clarify gate (`activePipelineRunId`) and call `onSubmitQuestionnaire` to resume the paused run instead of restarting; QuestionnairePanel render condition updated to show for active paused runs.
- [X] T024 [P] Write unit tests in `backend/tests/unit/test_execution_engine.py` — gate logic (PROCEED path, CLARIFY_REQUIRED path, timeout path), ClarifyEngine pause/resume, WorkflowResolver integration, all 14 pipeline type definitions resolve to valid DAGs
- [X] T025 [P] Regression suite in `backend/tests/integration/test_pipeline_workflows.py` — **two tiers**: (1) structural regression (no credentials) verifies every pipeline resolves to a satisfiable DAG, preserves dependency-valid topological order, and has every `consumes` satisfied upstream — per SC-004; (2) live streaming regression (marked `requires_api_key`, auto-skipped without Bedrock/Anthropic credentials) exercises the real engine.execute() planner→pipeline_start→agent_*→pipeline_complete sequence. Replaces the deleted orchestrator integration tests.

**Checkpoint**: Run `pytest backend/tests/` — all pass including golden-reference and regression. Verify `grep -r "od_runner\|od_ppt_runner\|orchestrator_v2" backend/app/` returns 0 results. All 14 pipelines execute through `ExecutionEngine`.


---

## Phase 3: User Story 1 — Guided Pipeline Execution with Planning (Priority: P1) 🎯 MVP

**Goal**: Deep_Planner_Agent runs before every pipeline, produces a `planning_context` Artifact, emits planning WS events, and gates execution. Users see a visible planning summary before any domain agent begins.

**Independent Test**: Submit a `user_stories` pipeline. Verify `planner_start` WS event arrives before `pipeline_start`. Verify `planner_complete` contains a `planning_context` Artifact with `execution_gate: "PROCEED"`. Verify domain agents run and their outputs reflect inferred constraints the user did not state.

**Spec coverage**: FR-002, FR-007, FR-009, FR-016, US1 acceptance scenarios

- [X] T026 [US1] Implement Deep_Planner_Agent tool execution in `backend/agents/planner/tools.py` — `analyze_request` extracts explicit requirements; `infer_constraints` proactively infers personas, NFRs, tech stack, compliance; `assess_readiness` determines PROCEED vs CLARIFY_REQUIRED; `build_execution_plan` selects execution strategy; `store_planning_context` writes to ArtifactStore; `retrieve_planning_context` reads from ArtifactStore
- [X] T027 [US1] Wire Deep_Planner_Agent into `backend/agents/execution_engine/engine.py` — prepend to every Workflow; enforce 15s timeout with `asyncio.wait_for`; emit `planner_start`, `planner_complete`, `planner_timeout`, `planner_error`, `gate_status` events per websocket-events.md contract
- [X] T028 [US1] Implement gate verdict routing in `backend/agents/execution_engine/engine.py` — PROCEED: continue to domain agents; CLARIFY_REQUIRED: invoke ClarifyEngine; after ClarifyEngine completes: re-evaluate gate; after 3 rounds emit `clarification_limit_reached` and proceed with best available context
- [X] T029 [P] [US1] Implement `planning_context` cross-cutting injection in `backend/agents/execution_engine/engine.py` — supply `planning_context` Artifact to ALL agents regardless of Consumes_Contract; injected as `## Planning Context` block in the context_message (user message side) for all pipelines; structured with inferred_intent, constraints, personas, NFRs, quality_targets
- [X] T030 [P] [US1] Update `frontend/src/hooks/useWorkflow.ts` — render `planner_start` as "Analyzing your request…" status; render `planner_complete` summary in AgentProgressPanel; render `gate_status` verdict; render `planner_timeout` notice (completed in T022)
- [X] T031 [P] [US1] Write unit tests in `backend/tests/unit/test_planner_tools.py` — `analyze_request` extracts requirements, `infer_constraints` produces non-empty implicit constraints, `assess_readiness` returns PROCEED for complete brief, CLARIFY_REQUIRED for ambiguous brief, timeout defaults to PROCEED

**Checkpoint**: Submit any pipeline. Confirm `planner_start` → `planner_complete` → `gate_status: PROCEED` → `pipeline_start` sequence in WS events. Confirm domain agent outputs reference inferred constraints.


---

## Phase 4: User Story 2 — Resumable Clarification (Priority: P2)

**Goal**: When the Deep_Planner_Agent issues CLARIFY_REQUIRED, the pipeline pauses at a Human_Gate, presents targeted questions via QuestionnairePanel, and resumes from the gate with answers merged into `planning_context`. Paused state survives backend restart.

**Independent Test**: Trigger a CLARIFY_REQUIRED verdict. Wait >15 seconds. Submit answers. Verify pipeline resumes from the gate (not from the beginning). Verify 0 pipeline restarts. Verify answers are persisted to Workflow_Clarifications and survive a backend restart.

**Spec coverage**: FR-009, FR-011 (waiting_for_user state), US2 acceptance scenarios

- [X] T032 [US2] Implement full ClarifyEngine in `backend/agents/execution_engine/clarify_engine.py` — Clarify_Agent classifies ambiguities using 11-category taxonomy; asks `min(5, detected_ambiguity_count)` questions (count ≤ detected ambiguities, max 5); one question at a time with recommended answer; persists every Q&A pair to ArtifactStore; **spec-grounded mode** when a `spec` Artifact exists upstream (applies only to Spec_Kit_Agent workflows where Specify_Agent has run); **brief-grounded mode** for all standard pipelines (`prototype`, `user_stories`, `od_ppt`, etc.) where no Specify_Agent runs — standard pipelines always use brief-grounded mode
- [X] T033 [US2] Implement Human_Gate pause/resume in `backend/agents/execution_engine/clarify_engine.py` — emit `questionnaire_ready` with questions; await `asyncio.Event` from `ArtifactStore.get_resume_event(pipeline_run_id)`; no automatic timeout while waiting; on `submit_questionnaire` WS message: call `ArtifactStore.set_questionnaire_responses()` which sets the event; merge answers into `planning_context` Artifact
- [X] T034 [US2] Implement StateMachine transitions in `backend/agents/execution_engine/state_machine.py` — WorkflowRun transitions: `planning` when Deep_Planner_Agent begins; `clarifying` when ClarifyEngine opens gate; `waiting_for_user` while paused; `generating` when domain agents begin; `completed`/`failed`/`cancelled` on terminal states; persist before returning
- [X] T035 [US2] Ensure WorkflowRun is created immediately on pipeline submission in `backend/app/api/websocket.py` — **this must also be implemented in Phase 2 (T020)** as a prerequisite: T020 must create the WorkflowRun row before calling `ExecutionEngine.execute()`, so both the planning stage and clarification gate are resumable across reconnect and backend restart from the very first Phase 2 deployment; T035 validates and tests this behavior end-to-end
- [X] T036 [P] [US2] Implement reconnect restoration in `backend/app/api/websocket.py` — on `reconnect_pipeline` WS message with existing `pipeline_run_id`, restore pending questions and prior answers from ArtifactStore; re-emit `questionnaire_ready` if run is in `waiting_for_user` state
- [X] T037 [P] [US2] Update `frontend/src/hooks/useWorkflow.ts` — handle `questionnaire_ready` (route to QuestionnairePanel); handle `questionnaire_complete` (update gate status); handle `clarification_limit_reached` (show notice, continue); `submitQuestionnaire(pipeline_run_id, responses)` sends `submit_questionnaire` WS message (completed in T022)
- [X] T038 [P] [US2] Update `frontend/src/components/layout/DashboardLayout.tsx` — remove any remaining questionnaire timeout logic; route `questionnaire_ready` to QuestionnairePanel; QuestionnairePanel visuals unchanged (completed in T023)
- [X] T039 [P] [US2] Write unit tests in `backend/tests/unit/test_clarify_engine.py` — pause/resume cycle, max 3 rounds, `clarification_limit_reached` emission, Q&A persistence, reconnect restoration within 5s, pipeline does not restart on resume (covered in test_execution_engine.py Phase 2)

**Checkpoint**: Trigger CLARIFY_REQUIRED. Confirm pipeline pauses indefinitely. Submit answers. Confirm pipeline resumes from gate. Restart backend while paused. Confirm questions restored on reconnect within 5s.


---

## Phase 5: User Story 3 — Agent Execution Transparency / Thinking Tab (Priority: P3)

**Goal**: PreviewPanel gains a third "Thinking" tab showing each agent's live reasoning, tool calls, input prompts, and context sources. Available during live execution and in Workflow History.

**Independent Test**: Run any pipeline. Switch to the Thinking tab. Verify each agent card shows live reasoning text, tool calls with args and results, the full input prompt, and context sources with compression ratios. Verify the tab is accessible during live execution and in Workflow History.

**Spec coverage**: FR-015, FR-017, US3 acceptance scenarios

- [X] T040 [US3] Emit `agent_input` WS event per agent in `backend/agents/execution_engine/engine.py` — fields: `agent_id`, `pipeline_run_id`, `timestamp`, `context_message` (full input prompt), `context_sources` (list of summary or artifact source objects), `tool_calls: []`; per websocket-events.md contract
- [X] T041 [US3] Extend `agent_outputs` JSON in `backend/app/api/websocket.py` — add optional fields to each entry: `input_prompt`, `context_sources`, `tool_calls`, `thinking_text`; non-breaking (existing consumers ignore unknown fields)
- [X] T042 [P] [US3] Add new TypeScript interfaces to `frontend/src/types/index.ts` — `AgentRunState.inputPrompt`, `AgentRunState.contextSources`, `AgentRunState.toolCalls`, `AgentRunState.thinkingText`; `ContextSource` (type: "summary" | "artifact", fields per data-model.md Section 4); `ToolCallEntry` (tool, args, result, timestamp)
- [X] T043 [P] [US3] Update `frontend/src/hooks/useWorkflow.ts` — handle `agent_input` event (store inputPrompt and contextSources on agent state); accumulate `tool_call`/`tool_result` events into `toolCalls` array; capture `agent_thinking` into `thinkingText`; all events render within 1s of receipt
- [X] T044 [US3] Create `frontend/src/components/results/AgentThinkingTab.tsx` — per-agent cards with: thinking text (live streaming), tool calls with args and results (chronological), full input prompt (expandable), context sources with compression ratios (summary_length/full_output_length) or artifact_type/artifact_size_chars; auto-expands running agent card; renders within 1s
- [X] T045 [US3] Update `frontend/src/components/preview/PreviewPanel.tsx` — add Thinking tab as third tab (order: Preview, Files, Thinking); pass `pipelineState.agents` to `AgentThinkingTab`; Thinking tab retains all content until new run begins
- [X] T046 [P] [US3] Update `frontend/src/components/history/WorkflowHistory.tsx` — add Thinking tab to detail view; extend `detailTab` state type to `"preview" | "files" | "thinking"`; map `agentOutputs` from DB to `AgentRunState[]`; populate Thinking tab from persisted `agent_outputs`
- [X] T047 [P] [US3] Write unit tests in `backend/tests/unit/test_agent_input_event.py` — `agent_input` event emitted for every agent, context_sources populated correctly for summarized inputs and typed Artifact inputs, compression ratio calculated correctly

**Checkpoint**: Run any pipeline. Switch to Thinking tab. Confirm per-agent cards appear within 1s of each `agent_thinking` event. Confirm tool calls render. Confirm input prompt visible. Open Workflow History — confirm Thinking tab populated for completed runs.


---

## Phase 6: User Story 4 — Intelligent Revision with Lineage (Priority: P4)

**Goal**: Revision requests create a new WorkflowRun with `parent_run_id`. The revision agent receives the original `planning_context` Artifact, the artifact being revised, and the revision instruction as three separate structured inputs. Section-level targeting preserves unchanged content byte-for-byte.

**Independent Test**: Complete a pipeline. Run a revision with a targeted instruction. Verify the revision agent receives the original `planning_context` Artifact, the artifact being revised, and the revision instruction as three separate structured inputs. Verify unchanged content is byte-for-byte identical to the prior version.

**Spec coverage**: FR-014, FR-010 (lineage), FR-011 (parent_run_id), US4 acceptance scenarios

**Prerequisites**: Phase 6 requires DB-backed Artifact_Store (T048–T052 below must complete first)

- [X] T048 Create Alembic migration `backend/alembic/versions/0010_artifact_store.py` — create `workflow_artifacts` table per `specs/001-ai-workflow-os/data-model.md` Section 1; include downgrade
- [X] T049 Create Alembic migration `backend/alembic/versions/0011_workflow_tables.py` — create `workflow_clarifications`, `workflow_memory`, `workflows` tables per data-model.md Section 1; include downgrade
- [X] T050 Create Alembic migration `backend/alembic/versions/0012_workflow_run_extended.py` — add `parent_run_id`, `status` (extended), `session_id`, `pipeline_run_id`, `execution_gate`, `execution_strategy`, `planning_context_unavailable` to `workflow_runs`; include downgrade
- [X] T051 [P] Create SQLAlchemy models: `backend/app/models/artifact.py` (WorkflowArtifact), `backend/app/models/workflow_clarification.py` (WorkflowClarification), `backend/app/models/workflow_memory.py` (WorkflowMemory), `backend/app/models/workflow_definition.py` (WorkflowDefinition) — per data-model.md Section 1
- [X] T052 Migrate `backend/agents/artifact_store/store.py` from in-memory to DB-backed — public interface unchanged; all existing callers continue to work without modification; `use_db=False` flag for unit tests; graceful fallback to in-memory when DB table not yet created
- [X] T053 [US4] Implement `ExecutionEngine._handle_revision(parent_run_id, target_artifact_type, instruction)` in `backend/agents/execution_engine/engine.py` — retrieve original Artifact, version history, and instruction as three separate structured inputs (NOT concatenated); store result as new Artifact version with `derived_from_artifact_id`; annotate run with `planning_context_unavailable: true` if parent run predates Phase 3
- [X] T054 [US4] Add `run_revision` WebSocket message handler in `backend/app/api/websocket.py` — message shape: `{type: 'run_revision', parent_run_id, target_artifact_type, instruction}`; validate non-empty instruction and existing parent Artifact before creating WorkflowRun; call `ExecutionEngine._handle_revision()`
- [X] T055 [P] [US4] Update `frontend/src/lib/workflowChaining.ts` — add `CHAIN_SOURCE_RUN_ID_KEY`; wizard pages pass `source_workflow_run_id` in `run_pipeline` message
- [X] T056 [P] [US4] Update `frontend/src/app/workflow/ppt/templates/page.tsx` and `frontend/src/app/workflow/prototype/templates/page.tsx` — pass `source_workflow_run_id` from chaining state (CHAIN_SOURCE_RUN_ID_KEY added to workflowChaining.ts; wizard pages can now read it)
- [X] T057 [P] [US4] Update `frontend/src/components/layout/DashboardLayout.tsx` — revision buttons send `run_revision` WS message when `currentWorkflowRunId` is available (replacing current `=== EXISTING ... ===` text injection pattern); fall back to legacy text injection for pre-Phase3 runs
- [X] T058 [P] [US4] Write unit tests in `backend/tests/unit/test_revision_intelligence.py` — three separate structured inputs (not concatenated), section-level targeting preserves unchanged content byte-for-byte, `derived_from_artifact_id` set correctly, empty instruction rejected, non-existent Artifact rejected, pre-Phase3 run annotated with `planning_context_unavailable`

**Checkpoint**: Complete a pipeline. Run a revision targeting a specific section. Confirm unchanged sections are byte-for-byte identical. Confirm Artifact_Store shows new version with `derived_from_artifact_id`. Confirm Thinking tab shows revision agent received three separate inputs.


---

## Phase 7: User Story 5 — Custom Composable Workflows (Priority: P5)

**Goal**: Users compose arbitrary agent DAGs (1–50 agents) from any agent in the arsenal. Workflow_Resolver validates the DAG before execution. Visual Dependency Graph renders in the frontend. Spec_Kit_Agents are available in any custom Workflow.

**Independent Test**: Compose a Workflow with `constitution → specify → clarify → material-analyzer → html-prototype-builder`. Submit it. Verify the Workflow_Resolver validates the DAG, the visual dependency graph renders, and the Execution_Engine runs all agents in topological order.

**Spec coverage**: FR-013, FR-004, FR-005, FR-006, US5 acceptance scenarios

- [X] T059 [US5] Implement full `WorkflowResolver.validate()` in `backend/agents/execution_engine/resolver.py` — exact case-sensitive Artifact_Type matching; reject unsatisfiable (unmatched types, cycles) before any agent runs; multi-producer tie-break: fewest DAG edges, ties broken by latest declared order; `planning_context` and `constitution` exempt from type matching; return `ValidationResult` with `satisfiable`, `errors`, `dag`, `edges`, `unresolved_edges` (completed in Phase 1)
- [X] T060 [US5] Implement `WorkflowResolver.resolve_execution_order()` in `backend/agents/execution_engine/resolver.py` — topological sort of validated DAG; raises ValueError if unsatisfiable (completed in Phase 1)
- [X] T061 [US5] Implement custom Workflow persistence in `backend/agents/execution_engine/engine.py` — persist Workflow definition (agents, edges, constitution_ref) to `workflows` table via `WorkflowDefinition` model; retrievable after restart; 1–50 agent limit enforced (Deep_Planner_Agent prepended automatically, does not count toward limit)
- [X] T062 [P] [US5] Emit `workflow_validated` WS event in `backend/agents/execution_engine/engine.py` — fields: `pipeline_run_id`, `satisfiable`, `dag_edges` (list of from/to/artifact_type), `unresolved_edges`; emitted before any agent executes (completed in Phase 2)
- [X] T063 [P] [US5] Add `dagEdges` and `unresolvedEdges` to `PipelineRunState` in `frontend/src/types/index.ts`; add `DagEdge` and `UnresolvedEdge` interfaces
- [X] T064 [P] [US5] Update `frontend/src/hooks/useWorkflow.ts` — handle `workflow_validated` event; store `dag_edges` in `pipelineState.dagEdges` and `unresolved_edges` in `pipelineState.unresolvedEdges`
- [X] T065 [US5] Create `frontend/src/components/workflow/DependencyGraph.tsx` — render DAG nodes (one per agent) and directed edges (one per resolved producer→consumer Artifact_Type relationship); unsatisfied edges (from `unresolvedEdges`) visually distinct (dashed/red) from satisfied edges (solid/green); mounted within `AgentProgressPanel` below the agent list when `dagEdges` is non-empty
- [X] T065a [US5] Create custom Workflow composition UI in `frontend/src/components/workflow/WorkflowComposer.tsx` — agent selector (searchable list of all available agents from arsenal); ordered list to compose agent sequence (1–50 agents); submit button that sends `run_pipeline` WS message with `agent_ids`; accessible via custom workflow pipeline type
- [X] T066 [P] [US5] Write unit tests in `backend/tests/unit/test_workflow_resolver.py` — satisfiable multi-agent DAG, unsatisfiable (unmatched type reported), cycle detection, multi-producer tie-break, 0-agent rejection, 51-agent validation, planning_context exemption, constitution exemption, all unmatched types reported, dag_edges populated on success

**Checkpoint**: Compose a custom Workflow with mixed Spec_Kit_Agents and Domain_Agents. Confirm `workflow_validated` event arrives with correct `dag_edges`. Confirm visual dependency graph renders. Confirm unsatisfied edges are visually distinct. Confirm Execution_Engine runs agents in topological order.


---

## Phase 8: User Story 6 — Workflow Session Continuity (Priority: P6)

**Goal**: Workflow_Memory persists per-user Constitution and domain knowledge across sessions. Backend-restart resumability restores non-terminal WorkflowRuns within 30 seconds. Planning_Context injected from DB into revision pipelines in new sessions.

**Independent Test**: Complete a pipeline. Close the browser. Reopen it. Run a revision. Verify the revision agent receives the original `planning_context` Artifact from DB (not in-memory). Verify the Workflow_Memory Constitution is injected as a guardrail.

**Spec coverage**: FR-012, FR-011 (resumability), FR-016 (planning_context injection), US6 acceptance scenarios

- [X] T067 [US6] Create `backend/agents/workflow_memory/memory.py` — `WorkflowMemory` class with `get_constitution(user_id)`, `set_constitution(user_id, content)`, `delete_constitution(user_id)`, `get_entry(user_id, key)`, `set_entry(user_id, key, value)`, `delete_entry(user_id, key)`; per-user isolation; key 1–255 chars; value up to 1,048,576 chars; up to 1,000 entries per user; available across sessions and backend restarts; `use_db=False` for unit tests
- [X] T068 [US6] Activate Constitution injection in `backend/agents/factory.py` — `_inject_constitution(ctx)` retrieves Constitution from Workflow_Memory and injects into every governed agent's system prompt as a guardrail; per-Workflow Constitution overrides per-user Constitution; `user_id` added to `AgentContext` and forwarded from engine
- [X] T069 [US6] Implement backend-restart resumability in `backend/agents/execution_engine/engine.py` — `ExecutionEngine.restore_non_terminal_runs()`: scan `workflow_runs` for non-terminal states; re-register asyncio.Events in ArtifactStore for runs in `waiting_for_user`; complete within 30 seconds of startup
- [X] T070 [US6] Register startup handler in `backend/app/main.py` — lifespan handler calls `ExecutionEngine.restore_non_terminal_runs()` on startup (non-fatal if it fails)
- [X] T071 [P] [US6] Upgrade `backend/agents/execution_engine/state_machine.py` — `_persist()` now also writes to `workflow_runs.status` DB column (best-effort, non-fatal); in-memory dict remains authoritative for current process
- [X] T072 [P] [US6] Persist `session_id` and `pipeline_run_id` to DB in `backend/app/api/websocket.py` — write to `WorkflowRun.session_id` and `WorkflowRun.pipeline_run_id` on WorkflowRun creation
- [X] T073 [P] [US6] Write unit tests in `backend/tests/unit/test_workflow_memory.py` — per-user isolation, key/value round-trip, Constitution retrieval, 1000-entry limit, cross-session persistence, key/value length validation
- [X] T074 [P] [US6] Write unit tests in `backend/tests/unit/test_resumability.py` — non-terminal runs restored within 30s, waiting_for_user runs remain resumable after restart, asyncio.Events re-registered correctly
- [X] T074a [US6] Add `GET/PUT/DELETE /api/settings/constitution` REST endpoints in `backend/app/api/settings.py` — accepts `{content: str}`, calls `WorkflowMemory.set_constitution(user_id, content)`; returns current value or null
- [X] T074b [P] [US6] Create "My Constitution" section in `frontend/src/components/settings/AccountSettings.tsx` — free-form textarea for Constitution text; Save button calls `PUT /api/settings/constitution`; Clear button calls `DELETE /api/settings/constitution`; loads current value on mount via `GET /api/settings/constitution`

**Checkpoint**: Complete a pipeline. Restart backend. Confirm non-terminal runs restored within 30s. Set a Constitution in Workflow_Memory. Run a new pipeline. Confirm Constitution appears in agent system prompts. Run a revision in a new session. Confirm original `planning_context` retrieved from DB.


---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: BaseAgent migration, performance validation, end-to-end integration tests, rollout guide, schema extensibility.

**Spec coverage**: FR-020 (Deep Agents only), FR-021 (test-first), FR-022 (extensibility), Phase 4 Hardening

- [X] T075 Migrate `backend/app/agents/summarizer.py` from BaseAgent to `DeepAgent(tools=[], max_iterations=1)` — add comment `# tools=[] intentional: utility function, not pipeline agent`; wire the migrated summarizer into `backend/agents/execution_engine/engine.py` for inter-agent context summarization (same role as in `orchestrator_v2.py` — summarize each agent's output before passing as context to the next agent)
- [X] T076 [P] Add FR-023 structured JSON logging to `backend/agents/execution_engine/engine.py` — emit a structured JSON log entry for every significant lifecycle event: WorkflowRun creation, state transitions, agent start/complete/error, gate open/close (Human_Gate and Validation_Gate), planner timeout, and Artifact_Store write failures; each entry MUST include `timestamp`, `pipeline_run_id`, `event_type`, `agent_id` (where applicable), `duration_ms` (where applicable), `error` (where applicable); use Python's `logging` module with a JSON formatter (e.g., `python-json-logger` if available, otherwise format manually); satisfies SC-013
- [X] T076a [P] Add FR-023 pipeline metrics collection to `backend/agents/execution_engine/engine.py` — track and expose: per-agent latency (ms), Deep_Planner_Agent latency (ms), gate outcome counts (PROCEED / CLARIFY_REQUIRED / override / cancel), pipeline failure rate by pipeline_type, Artifact_Store write failure count; first audit `backend/app/` for any existing metrics/monitoring infrastructure (CloudWatch, Prometheus, custom) and export to that system; if none exists, write metrics to a structured log sink as a fallback
- [X] T077 [P] Verify `schema_version` is non-null on every Artifact write in `backend/agents/artifact_store/store.py` — default `"1.0"`; add assertion in store() method
- [X] T078 [P] Verify Artifact_Store schema permits additive extension — confirm no column is NOT NULL without a default; confirm previously stored Artifacts return without error when new optional fields added
- [X] T079 Write end-to-end integration tests in `backend/tests/integration/test_pipeline_workflows.py` — all 14 pipeline types through universal engine; verify `planner_start` → `planner_complete` → `pipeline_start` → `pipeline_complete` sequence; verify `agent_input` events emitted; verify `workflow_validated` before `pipeline_start`
- [X] T080 [P] Performance validation tests in `backend/tests/integration/test_performance.py` — Deep_Planner_Agent < 15s (SC-002); total pre-pipeline < 30s (SC-003); clarification restore < 5s (SC-008); all credential-gated (auto-skipped without LLM provider)
- [X] T081 [P] Write `ROLLOUT.md` in `specs/001-ai-workflow-os/` — 5-step guide for adding a new pipeline type to the universal engine: (1) create AGENT.md files with produces/consumes, (2) add to SUPPORTED_PIPELINE_TYPES + PIPELINE_AGENTS, (3) run WorkflowResolver.validate(), (4) update frontend WorkflowType union, (5) add regression test
- [X] T082 [P] Auto-generate `PLANNER.md` per run in `backend/agents/execution_engine/engine.py` — write planning_context summary to workspace file `PLANNER.md` after Deep_Planner_Agent completes; available to all downstream agents via workspace
- [X] T083 [P] Run full regression suite `pytest backend/tests/` — confirm zero regressions across all 14 pipeline types; confirm all new unit tests pass; confirm ruff check passes with zero errors (141 passed, 5 skipped, 0 failed; ruff clean)
- [X] T084 [P] Run TypeScript typecheck `npx tsc --noEmit` in `frontend/` — confirm zero type errors in all new and modified files (exit=0, 0 errors)

**Checkpoint**: All tests pass. `ruff check backend/` returns 0 errors. `tsc --noEmit` returns 0 errors. All 14 pipelines execute through universal engine. Performance targets met. No BaseAgent usage in any pipeline.


---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1: Setup (T001–T009)
  └── No dependencies — start immediately

Phase 2: Foundational (T010–T025)
  └── Depends on Phase 1 complete
  └── ⚠️ BLOCKS all user story phases

Phase 3: US1 — Planning (T026–T031)
  └── Depends on Phase 2 complete

Phase 4: US2 — Clarification (T032–T039)
  └── Depends on Phase 2 complete
  └── Can run in parallel with Phase 3

Phase 5: US3 — Thinking Tab (T040–T047)
  └── Depends on Phase 2 complete
  └── Can run in parallel with Phases 3–4

Phase 6: US4 — Revision + DB (T048–T058)
  └── Depends on Phase 2 complete
  └── T048–T052 (DB migrations) must complete before T053–T058

Phase 7: US5 — Custom Workflows (T059–T066)
  └── Depends on Phase 2 complete (resolver stub)
  └── Can run in parallel with Phases 3–6

Phase 8: US6 — Session Continuity (T067–T074)
  └── Depends on Phase 6 (DB-backed Artifact_Store, T052)
  └── T071 (StateMachine DB upgrade) depends on T050

Phase 9: Polish (T075–T084)
  └── Depends on all user story phases complete
```

### User Story Dependencies

| Story | Depends On | Can Parallelize With |
|---|---|---|
| US1 Planning (P1) | Phase 2 | US2, US3, US5 |
| US2 Clarification (P2) | Phase 2 | US1, US3, US5 |
| US3 Thinking Tab (P3) | Phase 2 | US1, US2, US5 |
| US4 Revision (P4) | Phase 2 + DB migrations (T048–T052) | US5 |
| US5 Custom Workflows (P5) | Phase 2 | US1, US2, US3, US4 |
| US6 Session Continuity (P6) | US4 DB (T052) | US5 |

### Critical Path

```
T001 → T002 → T003/T004/T005 (parallel) → T006 → T007/T008/T009 (parallel)
  → T010 → T011/T012/T013 (parallel) → T014 → T015 → T016 → T017 → T018 → T019 → T020 → T021
  → T022/T023/T024/T025 (parallel)
  → [US1–US5 in parallel] → T048–T052 → [US4, US6]
  → T075–T084 (parallel)
```

---

## Parallel Execution Examples

### Phase 1 Parallel Batch
```
Parallel: T003 (loader fields), T004 (ArtifactStore), T005 (Resolver stub)
Then: T006 (migration)
Parallel: T007 (ArtifactStore tests), T008 (Resolver tests), T009 (loader tests)
```

### Phase 2 Parallel Batch
```
Parallel: T011 (planner tools), T012 (deep-planner AGENT.md), T013 (Spec Kit AGENT.md files)
Then: T014 (76+ AGENT.md contracts)
Then: T015 (factory.py injects)
Parallel: T016 (golden-reference tests), T017 (ClarifyEngine), T018 (StateMachine)
Then: T019 (engine.py) → T020 (websocket.py) → T021 (delete legacy runners)
Parallel: T022 (useWorkflow.ts), T023 (DashboardLayout.tsx), T024 (engine tests), T025 (regression tests)
```

### User Story Parallel Batch (after Phase 2)
```
Parallel streams:
  Stream A: T026 → T027 → T028 → T029/T030/T031 (US1)
  Stream B: T032 → T033 → T034 → T035 → T036/T037/T038/T039 (US2)
  Stream C: T040 → T041 → T042/T043 → T044 → T045 → T046/T047 (US3)
  Stream D: T048 → T049 → T050 → T051/T052 → T053 → T054 → T055/T056/T057/T058 (US4)
  Stream E: T059 → T060 → T061 → T062/T063/T064 → T065/T066 (US5)
  Stream F (after T052): T067 → T068 → T069 → T070 → T071/T072/T073/T074 (US6)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T009)
2. Complete Phase 2: Foundational (T010–T025) — **CRITICAL, blocks everything**
3. Complete Phase 3: US1 Planning (T026–T031)
4. **STOP and VALIDATE**: Submit any pipeline, confirm planning gate works end-to-end
5. Deploy/demo: users see Deep_Planner_Agent running before every pipeline

### Incremental Delivery

| Milestone | Tasks | Deliverable |
|---|---|---|
| M1: Foundation | T001–T025 | Universal engine live, all 14 pipelines migrated |
| M2: Planning | T026–T031 | Deep Planner gates every pipeline |
| M3: Clarification | T032–T039 | Pause/resume clarification working |
| M4: Transparency | T040–T047 | Thinking tab live |
| M5: Persistence | T048–T058 | DB-backed artifacts, revision intelligence |
| M6: Composability | T059–T066 | Custom workflows + visual DAG |
| M7: Continuity | T067–T074 | Session memory, restart resumability |
| M8: Hardened | T075–T084 | All tests pass, performance validated |

### Parallel Team Strategy

With 3 developers after Phase 2:
- **Dev A**: US1 (Planning) + US2 (Clarification) — backend-heavy
- **Dev B**: US3 (Thinking Tab) + US5 (Custom Workflows) — frontend-heavy
- **Dev C**: US4 (Revision + DB) + US6 (Session Continuity) — DB-heavy

---

## Task Count Summary

| Phase | Tasks | Story |
|---|---|---|
| Phase 1: Setup | T001–T009 (9 tasks) | — |
| Phase 2: Foundational | T010–T025 + T020a, T021a, T021b (19 tasks) | — |
| Phase 3: US1 Planning | T026–T031 (6 tasks) | US1 |
| Phase 4: US2 Clarification | T032–T039 (8 tasks) | US2 |
| Phase 5: US3 Thinking Tab | T040–T047 (8 tasks) | US3 |
| Phase 6: US4 Revision | T048–T058 (11 tasks) | US4 |
| Phase 7: US5 Custom Workflows | T059–T066 + T065a (9 tasks) | US5 |
| Phase 8: US6 Session Continuity | T067–T074 + T074a, T074b (10 tasks) | US6 |
| Phase 9: Polish | T075–T077 + T076a (10 tasks) | — |
| **Total** | **91 tasks** | |

---

## Notes

- `[P]` tasks operate on different files with no shared dependencies — safe to run in parallel
- `[Story]` label maps each task to its user story for traceability
- Each user story phase is independently completable and testable
- Legacy runners (`orchestrator_v2.py`, `od_runner.py`, `od_ppt_runner.py`) MUST NOT be deleted (T021) until T016 (golden-reference), T020a (BaseAgent migration), T021a (BaseAgent guard), T021b (cutover script), AND T025 (regression suite) are all green
- All new AGENT.md frontmatter fields are optional with defaults — backward compatible
- `planning_context` is cross-cutting: never add it to any agent's `consumes` list
- Phases 1–2 use in-memory storage; DB migrations are Phase 3 (T048–T052) only
- Commit after each task or logical group; push to both `origin` and `gitlab` remotes on branch `infra-agent-integration-deepagents`
