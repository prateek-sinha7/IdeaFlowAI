# Data Model: IdeaFlowAI Universal Workflow Orchestration Engine

---

## 1. New DB Tables (Phase 3 Alembic migrations)

### `workflow_artifacts` (Artifact_Store)
```sql
id                    VARCHAR  PK  (UUID)
workflow_run_id       VARCHAR  FK → workflow_runs.id
type                  VARCHAR  NOT NULL   -- Artifact_Type string
name                  VARCHAR  NOT NULL   -- human-readable name or file path
content               TEXT     NOT NULL   -- full artifact content
version               INTEGER  NOT NULL   -- monotonically increasing per type per run
schema_version        VARCHAR  NOT NULL   -- e.g. "1.0"
producing_agent_id    VARCHAR  NOT NULL   -- agent id that produced this artifact
derived_from_artifact_id VARCHAR FK → workflow_artifacts.id  -- lineage
created_at            DATETIME NOT NULL
```

### `workflow_clarifications`
```sql
id                    VARCHAR  PK  (UUID)
workflow_run_id       VARCHAR  FK → workflow_runs.id
question_id           VARCHAR  NOT NULL
question_text         TEXT     NOT NULL
impact_level          VARCHAR  NOT NULL   -- "high" | "medium" | "low"
answer_type           VARCHAR  NOT NULL   -- "free_text" | "single_choice" | "multi_choice" | "boolean"
options               TEXT     NULL       -- JSON array of strings
answer                TEXT     NULL       -- user's answer (NULL until answered)
recommended_answer    TEXT     NULL
round                 INTEGER  NOT NULL   -- 1, 2, or 3
created_at            DATETIME NOT NULL
answered_at           DATETIME NULL
```

### `workflow_memory`
```sql
id                    VARCHAR  PK  (UUID)
user_id               VARCHAR  FK → users.id  NOT NULL
key                   VARCHAR(255) NOT NULL
value                 TEXT     NOT NULL   -- up to 1,048,576 chars
created_at            DATETIME NOT NULL
updated_at            DATETIME NOT NULL
UNIQUE(user_id, key)
```

### `workflows` (Workflow definitions)
```sql
id                    VARCHAR  PK  (UUID)
user_id               VARCHAR  FK → users.id  NOT NULL
name                  VARCHAR  NOT NULL
agents                TEXT     NOT NULL   -- JSON: ordered list of agent IDs
artifact_edges        TEXT     NOT NULL   -- JSON: [{from_agent, to_agent, artifact_type}]
constitution_ref      VARCHAR  NULL       -- key in workflow_memory for per-workflow constitution
created_at            DATETIME NOT NULL
updated_at            DATETIME NOT NULL
```

---

## 2. Extended `workflow_runs` Table (Phase 3)

New columns added to existing table:
```sql
session_id            VARCHAR  NULL   -- = user_id (JWT sub)
pipeline_run_id       VARCHAR  NULL   -- UUID per run (in-memory Phase 1-2, DB Phase 3)
parent_run_id         VARCHAR  NULL   FK → workflow_runs.id  -- for chains/revisions
status                VARCHAR  NOT NULL DEFAULT 'running'
                      -- extended: clarifying | waiting_for_user |
                      --           planning | analyzing | generating | revising |
                      --           completed | failed | cancelled
execution_gate        VARCHAR  NULL   -- PROCEED | CLARIFY_REQUIRED
execution_strategy    VARCHAR  NULL   -- sequential (Phase 2); parallel/conditional (future)
planning_context_unavailable BOOLEAN NULL DEFAULT FALSE  -- for pre-Phase3 revisions
```

---

## 3. Schema-Debt Columns (Phase 1 — `0009_schema_debt.py`)

Added to existing tables (these ORM fields exist but have no migration):
```sql
users.tier                VARCHAR  NULL
users.is_admin            BOOLEAN  NULL
users.preferred_model     VARCHAR  NULL
workflow_runs.token_usage TEXT     NULL
workflow_runs.model_id    VARCHAR  NULL
```

---

## 4. Extended `agent_outputs` JSON (non-breaking)

Each entry in the `workflow_runs.agent_outputs` JSON array gains new optional fields:
```json
{
  "agent_id": "...",
  "name": "...",
  "role": "...",
  "icon": "...",
  "output": "...",
  "duration": 3.2,
  "input_prompt": "=== ORIGINAL USER REQUEST ===\n...",
  "context_sources": [
    {
      "type": "summary",
      "agent_id": "domain-analyst",
      "agent_name": "Domain Analyst",
      "summary_length": 847,
      "full_output_length": 4200
    },
    {
      "type": "artifact",
      "artifact_type": "spec",
      "artifact_size_chars": 12400
    }
  ],
  "tool_calls": [
    {"tool": "analyze_request", "args": {}, "result": "...", "timestamp": "..."}
  ],
  "thinking_text": "Let me analyze the brief...\nI can see the user needs..."
}
```

---

## 5. New AGENT.md Frontmatter Fields (Phase 1 — all optional with defaults)

| Field | Type | Default | Purpose |
|---|---|---|---|
| `produces` | `list[str]` | `[]` | Artifact_Types this agent produces |
| `consumes` | `list[str]` | `[]` | Artifact_Types this agent requires |
| `gate` | `str \| null` | `null` | `Human_Gate` or `Validation_Gate` |
| `injects` | `list[str]` | `[]` | Subset of `[template, design_system, craft]` |

---

## 6. Spec_Kit_Agent Contracts

| Agent | consumes | produces | gate |
|---|---|---|---|
| Constitution_Agent | `[]` | `["constitution"]` | — |
| Specify_Agent | `[]` | `["spec"]` | — |
| Clarify_Agent | `["spec", "brief"]` | `["clarifications"]` | `Human_Gate` |
| Research_Agent | `[]` | `["research"]` | — |
| Plan_Agent | `["spec", "research"]` | `["plan", "data_model", "contracts"]` | — |
| Tasks_Agent | `["plan"]` | `["tasks"]` | — |
| Analyze_Agent | `["spec", "plan", "tasks"]` | `["analysis_report"]` | `Validation_Gate` |
| Deep_Planner_Agent | `[]` | `["planning_context"]` | — (gate verdict is internal) |

---

## 7. Workflow State Transitions

```
WorkflowRun created (status: running)
        │
        ▼
status: planning  ← Deep_Planner_Agent begins
        │
        ├── gate = PROCEED ──────────────────────────────────────────┐
        │                                                            │
        └── gate = CLARIFY_REQUIRED                                  │
                │                                                    │
                ▼                                                    │
        status: clarifying  ← Clarify_Agent runs                    │
                │                                                    │
                ▼                                                    │
        status: waiting_for_user  ← Human_Gate open                 │
                │                                                    │
                ▼  (user submits answers)                            │
        status: clarifying  ← re-evaluate gate                      │
                │                                                    │
                └── (max 3 rounds) ──────────────────────────────────┤
                                                                     │
                                                                     ▼
                                                             status: generating
                                                             ← domain agents run
                                                                     │
                                                                     ▼
                                                     completed | failed | cancelled
```

---

## 8. ArtifactStore Public Interface

```python
class ArtifactStore:
    async def store(run_id: str, artifact_type: str, name: str,
                    content: str, producing_agent_id: str,
                    derived_from_id: str | None = None) -> str  # returns artifact id

    async def retrieve_latest(run_id: str, artifact_type: str) -> dict | None

    async def retrieve_version(artifact_id: str) -> dict | None

    async def list_by_type(run_id: str, artifact_type: str) -> list[dict]

    async def list_lineage(run_id: str) -> list[dict]  # all artifacts in run lineage
```

---

## 9. WorkflowResolver Public Interface

```python
class WorkflowResolver:
    def validate(workflow_def: WorkflowDefinition) -> ValidationResult
    # ValidationResult: {satisfiable: bool, errors: list[str], dag: dict}

    def resolve_dag(workflow_def: WorkflowDefinition) -> list[AgentSpec]
    # Returns agents in topological execution order
```
