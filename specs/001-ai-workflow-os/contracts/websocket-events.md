# WebSocket Event Contracts

All existing events are preserved unchanged. New events are additive.

---

## Existing Events (unchanged)

`pipeline_start`, `agent_start`, `agent_thinking`, `agent_chunk`, `agent_complete`,
`agent_error`, `pipeline_complete`, `pipeline_cancelled`, `tool_call`, `tool_result`,
`questionnaire`, `workflow_title_update`, `error`

---

## New Events (Phase 2)

### `planner_start`
```json
{"type": "planner_start", "data": {"pipeline_run_id": "uuid", "pipeline_type": "user_stories", "timestamp": "..."}}
```

### `planner_complete`
```json
{"type": "planner_complete", "data": {
  "pipeline_run_id": "uuid",
  "planning_context": {"inferred_intent": "...", "explicit_constraints": [], "implicit_constraints": [], "missing_information": [], "execution_strategy": "sequential", "execution_gate": "PROCEED"},
  "execution_gate": "PROCEED",
  "timestamp": "..."
}}
```

### `planner_timeout`
```json
{"type": "planner_timeout", "data": {"pipeline_run_id": "uuid", "elapsed_seconds": 15.2, "timestamp": "..."}}
```

### `planner_error`
```json
{"type": "planner_error", "data": {"pipeline_run_id": "uuid", "error": "...", "timestamp": "..."}}
```

### `gate_status`
```json
{"type": "gate_status", "data": {"pipeline_run_id": "uuid", "verdict": "PROCEED", "timestamp": "..."}}
```

### `questionnaire_ready`
```json
{"type": "questionnaire_ready", "data": {
  "pipeline_run_id": "uuid",
  "questions": [{"question_id": "q1", "question_text": "...", "impact_level": "high", "answer_type": "single_choice", "options": ["A", "B"], "recommended_answer": "A"}],
  "round": 1,
  "timestamp": "..."
}}
```

### `questionnaire_complete`
```json
{"type": "questionnaire_complete", "data": {"pipeline_run_id": "uuid", "responses": [{"question_id": "q1", "answer": "A"}], "updated_gate": "PROCEED", "timestamp": "..."}}
```

### `clarification_limit_reached`
```json
{"type": "clarification_limit_reached", "data": {"pipeline_run_id": "uuid", "unresolved_items": ["preferred tech stack"], "timestamp": "..."}}
```

### `validation_gate_blocked`
```json
{"type": "validation_gate_blocked", "data": {"pipeline_run_id": "uuid", "agent_id": "analyze-agent", "blocking_findings": [{"id": "C1", "severity": "CRITICAL", "summary": "..."}], "timestamp": "..."}}
```

---

## New Events (Phase 3)

### `agent_input`
```json
{"type": "agent_input", "data": {
  "agent_id": "epic-architect",
  "pipeline_run_id": "uuid",
  "timestamp": "...",
  "context_message": "=== ORIGINAL USER REQUEST ===\n...",
  "context_sources": [
    {"type": "summary", "agent_id": "domain-analyst", "agent_name": "Domain Analyst", "summary_length": 847, "full_output_length": 4200},
    {"type": "artifact", "artifact_type": "spec", "artifact_size_chars": 12400}
  ],
  "tool_calls": []
}}
```

### `state_restoration_failed`
```json
{"type": "state_restoration_failed", "data": {"pipeline_run_id": "uuid", "parent_run_id": "uuid", "error": "...", "timestamp": "..."}}
```

### `workflow_validated`
```json
{"type": "workflow_validated", "data": {"pipeline_run_id": "uuid", "satisfiable": true, "dag_edges": [{"from": "specify-agent", "to": "clarify-agent", "artifact_type": "spec"}], "timestamp": "..."}}
```

---

## New Inbound Message Types (Phase 2)

### `submit_questionnaire`
```json
{"type": "submit_questionnaire", "pipeline_run_id": "uuid", "responses": [{"question_id": "q1", "answer": "Executives"}]}
```

### `run_pipeline` (extended — Phase 3)
```json
{"type": "run_pipeline", "pipeline_type": "prototype", "message": "...", "agent_ids": null, "attached_skills": [], "attached_hooks": [], "source_workflow_run_id": "uuid-of-parent-run"}
```
