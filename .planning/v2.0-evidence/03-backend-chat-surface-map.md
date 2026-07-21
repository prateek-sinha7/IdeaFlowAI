# Backend Chat-Surface Investigation (file:line-anchored)

> **Evidence doc — Milestone v2.0** (see `README.md` in this directory and the POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md`).
> Verbatim final report of a max-effort investigation agent, 2026-07-07. Feeds Phases 28-30 and 33. Anchors are as-of 2026-07-07 on branch new-workflow-engine - verify before acting.

---

All investigation complete. Synthesizing the full evidence-anchored map across all 8 sections.

---

# CHAT-in-Workflow-Runs — Backend Investigation Map

Repo: `/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend` (branch `new-workflow-engine`). All paths absolute. Every claim carries file:line.

**Headline findings (read first):**
1. A **legacy free-chat subsystem already exists** (`user_message` WS path → `ChatRunner`, its own `chat` pipeline + 7 agents + frozen golden test) but is **NOT wired to workflow runs** and carries **no cross-message history** (each message = a fresh multi-phase run).
2. **Image input is ~80% built as a dormant capability** (`input_provider:run_images`, dated `260707` = today) — plumbed engine→model but never wired at WS ingress and no manifest opts in.
3. The **HITL gate/clarify/redo machinery is the exact bidirectional pattern** a mid-run chat channel would follow: emit event → `asyncio.Event.wait()` → inbound WS message sets response → engine re-composes context and re-runs.
4. **`run_events` is the natural persistence home** for per-run chat (owner+workspace-scoped, seq-ordered, idempotent replay, live HTTP + WS reconnect replay already exist).
5. **Prompt caching is now ON** on Bedrock (recently added middleware) — this contradicts the older "caching silently OFF" memory note; verify below.

---

## 1. RUN LIFECYCLE & TRANSPORT

### Launch transport = WebSocket, not REST
- **WS endpoint:** `@router.websocket("/ws/chat")` → `websocket_chat(websocket)` at `app/api/websocket.py:564-565`. (There is **no** REST "start run" endpoint; runs are launched over the socket.)
- **Auth:** JWT via `Sec-WebSocket-Protocol: bearer.<jwt>` subprotocol (`websocket.py:594-632`), legacy `?token=` deprecated (`websocket.py:606-611`). Re-auth mid-session via `_authenticate_token(token, db)` (`websocket.py:270-297`, called again at `1283`).
- **Message loop:** `while True: raw = await websocket.receive_text()` → `json.loads` → dispatch on `msg_type` (`websocket.py:666-683`).

### Inbound client→server message types (complete)
| type | line | purpose | how it enters |
|---|---|---|---|
| `run_pipeline` | `689` | launch a run | user brief = `message_data["message"] or ["content"]` (`711`); also `pipeline_type`, `agent_ids`, `attached_skills/hooks`, `gate_agent_ids`, `model_overrides`, `selections`, `template_id`, `design_system_id`, `custom_*_body`, `source_workflow_run_id` (`710-770`) |
| `cancel_pipeline` | `777` | cooperative cancel | sets per-run `asyncio.Event` in `_CANCEL_EVENTS[run_id]` (`779-802`) |
| `reconnect_pipeline` | `824` | resume/replay | `pipeline_run_id` + optional `after_seq` (`825, 909`) |
| `run_revision` | `1132` | revise an artifact | `parent_run_id`, `target_artifact_type`, `instruction` (`1155-1157`) |
| `submit_questionnaire` | `1195` | **clarify answers** | `pipeline_run_id`, `responses`, `skip_clarification` → `store.set_questionnaire_responses(...)` (`1197-1213`) |
| `approve_review` | `1220` | **gate approve/reject/redo** | `gate_key`, `approved`, `edited_content`, `action` (`"approve"`/`"redo"`), `instructions` → `store.set_review_response(...)` (`1222-1260`); redo at `1253` |
| `ping` | `1263` | keepalive | replies `pong` (`1266`) |
| `user_message` | `1271` | **legacy free-chat** | `content` + `chat_session_id`; persists `Message` rows, runs `ChatRunner` (`1271-1445`) — see §2/§7 |

### Outbound server→client event taxonomy (complete)
Frames are wrapped `{"type", "chunk", "section", "data"}` at the WS boundary (drainer `websocket.py:2114-2118`; `section = pipeline_type`). The **engine** yields `{"type","data"}` (queue) and the drainer wraps them.

- **Engine/subsystem event types** (grep of `agents/execution_engine/`, `agents/capabilities/`, `agents/artifact_store/`):
  `pipeline_start, pipeline_complete, pipeline_cancelled, pipeline_failed, pipeline_error, budget_aborted, budget_warning, workflow_validated, planner_start, planner_complete, planner_timeout, gate_status, gate_blocked, gate_wait_human, agent_start, agent_input, agent_chunk, agent_thinking, agent_complete, agent_error, agent_model_fallback, tool_call, tool_result, task_progress, task_loop_progress, summary, step_completed, step_retry, step_reused, review_gate_ready, review_gate_approved, questionnaire_ready, questionnaire_complete, clarification_limit_reached, validation_warning, state_restoration_failed, hook_run, subagent_spawned, subagent_result, wave_started, wave_completed, wave_failed, merge_started/attempt/completed/partial/conflict/failed/human_gate_skipped`.
  Internal (consumed, never sent to wire): `_gate_rejected`, `_gate_redo`, `_gate_edited` (`engine.py:4178,4221,4248`).
- **Canonical allowed vocabulary** pinned by `_DOCUMENTED_EVENT_TYPES` (frozenset) at `tests/agents/test_phase3_cutover_verify.py:182-227`; per-type required data keys `_REQUIRED_DATA_KEYS` at `232-245`.
- **WS-only frames:** `error` (26×), `pipeline_heartbeat` (`2094`), `pipeline_reconnected` (`1009,1024`), `workflow_title_update` (`504,552`), `title_update` (legacy chat, `1353`), `pong` (`1266`), `questionnaire_ready` (reconnect restore, `1115`).
- `questionnaire_ready`/`questionnaire_complete` are emitted by the clarify engine, not `engine.py` (`clarify_engine.py:263,291`).

### Event queue + durable persistence architecture
- Per-run in-memory queue + bg task, decoupled from WS: `_PIPELINE_QUEUES`, `_PIPELINE_TASKS`, `_CANCEL_EVENTS` (`websocket.py:39-59`).
- `_handle_workflow_execution` (`websocket.py:1493`) mints `pipeline_run_id = uuid4()` (`1707`), creates the `WorkflowRun` row (`1734-1759`), spawns `_run_pipeline_to_queue` (`1819`) which drives `engine.execute(...)` (`1828-1855`) and `event_queue.put({...})` each event (`1856`); the drainer forwards queue→WS (`2080-2137`).
- **Durable log:** inside the engine, the single emit boundary stamps `seq` + `event_id` and calls `_RunEventSink.persist → ScopedStore.append_event → RunEvent(...)` (`engine.py:818-876, 303-353`; `agents/authz.py:284-312`). This is separate from the in-memory queue.

### Reconnect/replay contract
- On `reconnect_pipeline`: if live task exists → live attach + ack `pipeline_reconnected {live:true}` (`websocket.py:1020-1034`); else replay durable tail `ScopedStore.read_events(run_id, after_seq)` + ack `{live:false, replayed_through_seq}` (`985-1018`).
- Owner-scoped: workspace recovered from an `owner_id==user.id`-filtered `RunEvent` row, then `ScopedStore(owner_id, workspace_id)` default-deny read (`938-987`). Cross-owner → ∅.
- `section` re-derived for revision runs via `type.removesuffix('_revision')+'_output'` (`976-979`); FE dedupes by `event_id`.
- Disconnect **suspends, does not cancel** — bg task keeps running, events still persisted (`websocket.py:1447-1455`).

---

## 2. EXISTING CONVERSATIONAL TOUCHPOINTS (the user↔agent channels to mirror)

All three use the same **in-memory `asyncio.Event` resume registry** in `agents/artifact_store/store.py` (per-process, keyed by run_id / `review:{gate_key}`; `store.py:40-48`). This is the canonical mid-run injection pattern.

### (a) Clarify Q&A phase
- Loop in `clarify_engine.py:240-308`: `_generate_questions` → `event.clear()` → emit `questionnaire_ready` → `await event.wait()` → read `get_questionnaire_responses` → `_persist_qa` → `_merge_answers` → emit `questionnaire_complete`.
- Resume: WS `submit_questionnaire` → `store.set_questionnaire_responses(run_id, responses, skip_clarification)` sets the event (`store.py:62-86`; `websocket.py:1211-1213`).
- **Persisted** as an artifact: Q&A pairs written via `ScopedStore` as `kind="clarifications"` refs (read back at `websocket.py:1098-1103` and `runs.py:812` via `?kind=clarifications&include=content`). This is the "clarifications.md/ClarificationsCard" (P25) store.
- `skip_clarification` force-proceed short-circuits the loop (`clarify_engine.py:301-308`).

### (b) Human review gates (incl. Redo-with-instructions)
- `_run_review_gate` (`engine.py:4139-4248`): `event.clear()` → transition `waiting_for_user` → emit `review_gate_ready {gate_key, output, redoable}` → `await event.wait()` → read response → branch on `action`:
  - `approve` → `review_gate_approved`; optional `_gate_edited` (`4237-4248`).
  - `reject` → `_gate_rejected` → pipeline cancelled (`3440-3450`).
  - **`redo`** → `_gate_redo {instructions}` (`4215-4222`).
- **Redo consumer** (`engine.py:3475-3521`): sets `redo_directive = instructions`, records `redo_derived_from` lineage, pops the rejected result, `redo_attempt += 1`, `break` → the flat enclosing `while`-loop re-runs the SAME agent.
- **Thread fork:** re-run uses a **fresh checkpoint thread** `f"{run}:{agent}:redo{N}"` (`engine.py:2801-2809`) so the checkpointer doesn't replay the rejected turn. (Same `:retry{n}`/`:fix{n}` idiom for throttle-fallback and validation fix-loop.)
- **How the instruction reaches the agent:** `_compose_context_message` appends `=== ADDITIONAL INSTRUCTIONS (REVISE) ===\n{redo_directive}\n=== END ===` (`engine.py:5916-5922`), consumed-once (`ectx.redo_directive` set at `2687`, cleared at `2692`). **This is the precise mechanism a mid-run chat message would reuse.**
- Owner-gated write (P13): `_review_gate_owned_by(gate_key, user.id)` checks `WorkflowRun.user_id == user_id` before any resume (`websocket.py:224-248, 1243-1249`); denies "Unknown gate_key" without revealing existence.

### (c) run_revision (new-run channel)
- `_handle_revision_execution` (`websocket.py:2214`) creates a **new** `WorkflowRun` with `parent_run_id` + `owner_id=user.id` (`2278-2312`), dispatches the `<base>_revision` pipeline; the revision agent gets the parent's artifact + spec/design seeded via the `previous_run` context provider (`context_providers/previous_run.py:129-222`), and the user's `instruction` flows in as the run brief.

---

## 3. AGENT SPAWNING & MESSAGE INJECTION

### Message construction into `create_deep_agent`
- INV-13: `create_deep_agent` is called **only** in `app/agents/deep_agent_runner.py:347` (banned-pattern gate; §7).
- The human turn: `self._graph.astream_events({"messages":[HumanMessage(content=user_message)]}, ...)` (`deep_agent_runner.py:475-476`; also `415`). `user_message` is typed `"str | list"` — `HumanMessage(content=...)` accepts either a bare string **or a content-block list** (`deep_agent_runner.py:406, 730, 794`).
- The engine chooses which via `_dispatch_payload(context_message, input_blocks)` (`engine.py:431-442`): bare str when no blocks (byte-identical default), else `[{"type":"text","text":context_message}, *input_blocks]`. Call site `engine.py:2941` → `agent.astream_events(_dispatch)`.
- **System prompt assembly** (factory, fixed order): `tool_availability → injects → guardrails → skills → hooks → constitution → prompt_body` via `PromptAssemblyPolicy.DEFAULT_ORDER` (`agents/capabilities/prompt/policy.py:45-56`); AGENT.md body + `_compose_injection` template/DS/craft (`factory.py:286-414, 656-739`). Composed **fresh on every `create_runner`** (`factory.py:330`).
- **Context message assembly** (`engine._compose_context_message`, `engine.py:5775-5976`), in order: `ORIGINAL USER REQUEST` → `Planning Context` → OD provider blocks → consumed upstream outputs (`_filter_consumed_outputs`) → `ADDITIONAL INSTRUCTIONS (REVISE)` (redo) → `CURRENT TASK` → `CURRENT PROTOTYPE (skeleton)` → `TEMPLATE COMPLIANCE`.

### Can a HumanMessage with extra content be appended mid-run?
- **No append-to-a-running-graph.** Each agent invocation is a fresh `create_deep_agent(...).astream_events({messages:[HumanMessage]})` run to completion (`engine.py:2810` build → `2941` stream). There is no persistent multi-turn conversation *within* an agent — the message is composed once per invocation.
- Injection is therefore done by **(a) re-composing the context** (the redo `ADDITIONAL INSTRUCTIONS` pattern — the established seam), **(b) the content-list path** (`input_blocks`), or **(c) a new declared step/agent**.

### Checkpoint thread keying (fork mechanism)
- Base: `f"{pipeline_run_id}:{spec.id}"`; build loop `:{task}`; redo `:redo{N}`; throttle fallback `:retry{n}`; validation fix `:fix{attempt}` (`engine.py:2796-2809, 3153, 3775`). **Per-invocation, not per-conversation** — nothing carries a running dialogue across invocations. The disk `RunSandbox` is the only per-run shared state (files persist agent→agent; `engine.py:2785`).

### Interrupt / resume support
- LangGraph native resume IS supported for HITL: `self._graph.ainvoke(Command(resume={"decisions":[...]}), self.config)` and interrupt detection via post-loop `aget_state(self.config)` (`deep_agent_runner.py:443-451, 555-574`).
- **But the LIVE pipeline gate does NOT use it** — `interrupt_on` is intentionally kept `None` (`engine.py:2792-2794`), so the review gate is the engine-level `asyncio.Event` pause (§2b), not a LangGraph interrupt. `Command(resume=...)` is scaffolded (Phase 3) but dormant on the live path.

---

## 4. MULTIMODAL & FILES

### Image / multimodal input — BUILT END-TO-END, DORMANT
- **Model SDKs support it:** `build_model()` selects `ChatAnthropic` (local) or `ChatBedrockConverse` (prod) — both accept image content blocks (`app/agents/model_factory.py:57-70, 104-121`). Factory sets no image config; content flows through `HumanMessage`.
- **Provider:** `RunImagesProvider.load` returns LangChain-standard blocks `{"type":"image","source_type":"base64","mime_type","data"}` (`agents/capabilities/input_providers/run_images.py:40-50`), registered `@register("input_provider","run_images", user_allowed=True)` (`:24`).
- **Engine plumbing:** `_normalize_run_images` (`engine.py:410-428`) → `execute(images=...)` (`799, 812, 891`) → `ectx.run_images` (`1018`; carrier `context.py:113-117`) → `_compose_input_blocks(spec, ectx)` gated on `"images" in spec.injects ∪ step.injects` (`engine.py:5978-6016`) → `_dispatch_payload` (`431`). Observability `image_count` emitted when present (`2719-2720`).
- **Manifest/compiler support:** `input_providers:` parsed (`agents/workflows/manifest.py:62-64`), validated (`compiler.py:213-218`), materialized onto `CompiledWorkflow.input_providers` (`compiler.py:258`), threaded to `ectx.compiled_input_providers` (`engine.py:1714`).
- **NOT wired at ingress:** WS `run_pipeline` handler never reads `images` and never passes `images=` to `engine.execute` (grep of `images` in `websocket.py` = 0 hits); **no** `workflow.yaml` declares `input_providers:`; **no** `AGENT.md` declares `injects:[images]`. Test scaffold exists: `tests/agents/test_image_input_wiring.py`.

### File upload endpoints
- **Only one upload surface in the whole backend:** `POST /api/files/extract-text` (`app/api/file_extract.py:87-136`; router prefix `/api/files`, `:31`; auth `get_current_user`). Accepts PDF/DOCX/PPTX ≤10MB, returns extracted **text** (`ExtractResponse{filename,text,truncated}`), truncated to `settings.BRIEF_MAX_CHARS`. **No persistence** — bytes read into memory, discarded; the frontend folds the text into the brief string. No image/OCR. No other `UploadFile`/`File(...)`/multipart handler exists.

### Where uploads COULD be stored
- **Per-run disk sandbox** (best fit for agent-readable files): `RunSandbox(user_id, run_id)` under `RUNS_ROOT` (default `/app/runs`, `app/agents/sandbox.py:49-149`; `app/core/config.py:149`), traversal-proof, TTL-swept 48h. This is the deepagents `FilesystemBackend(root_dir=...)` root (`deep_agent_runner.py:339`) — agents read via native `read_file`.
- **`artifact_refs` table:** content stored **inline in a `Text` column** (`app/models/artifact_ref.py:40`) — good for text artifacts, **poor for binary blobs**; a `location` column exists as an unused out-of-line hook.
- **`Workspace` model** (`app/models/workspace.py:20-37`): `id, owner_id, workspace_id, kind, runtime, repo_id, ttl` — the DB row for the sandbox.

### Files tab data source
- **No `/files` listing endpoint.** The Files tab reads `WorkflowRun.output` — a `filename:`-block string from `serialize_sandbox_deliverable(root)` (`app/agents/sandbox.py:236-301`), served by `GET /api/runs/{id}` (`runs.py:386-408`). Typed artifacts endpoint `GET /api/runs/{id}/artifacts` (`runs.py:793-855`) exists but is used mainly for `?kind=clarifications`.

---

## 5. CONTEXT & COMPRESSION

### Context assembly
- Two containers: per-run `ExecutionContext` (`agents/execution_engine/context.py:40-249`) and per-agent `AgentContext` (`agents/factory.py:32`).
- Context providers are **capabilities** (`ContextProvider` port: `name` + `async load(ctx)->dict[str,str]`): `opendesign` (`context_providers/opendesign.py:56-179`), `previous_run` (`:129-222`), `repo` (REPO-03). Declared in `workflow.yaml` `context_providers:`, validated by compiler, threaded to `ectx.compiled_context_providers` (`engine.py:1710`), looped in `_compose_context_message` (`5866-5901`), gated per-agent by `injects:` (`5849-5850`).
- Deliverable resolution: `ctx.deliverable` (compiled `DeliverableSpec`, `context.py:200`) resolved at run end by `deliverable` capabilities (`single_file/ppt/serialized_sandbox/streamed_text/repo_diff`).

### The fixed-context / token-cost problem
- **Primary fixed blob = system-prompt injects** (`factory._compose_injection`, `factory.py:656-739`): full `template_body` (SKILL.md) + full `ds_body` (DESIGN.md) + `craft_block`, re-composed **fresh on every `create_runner`** (`factory.py:330`) with **NO task-2+ suppression** — the whole template+DS+craft re-emitted for every task and every fix attempt.
- **Secondary blob = context-message OD blocks** (`OpenDesignProvider.load`), incl. `example.html` up to `EXAMPLE_MAX_CHARS=120_000` (`od_context.py:38`) — this path **is** suppressed on build task ≥2 (`opendesign.py:82-108`).
- **Re-sent per sub-agent** by `task_loop` (one isolated sub-agent per task, `strategies/task_loop.py:280` → `engine._run_agent`), each with a **new checkpoint thread** so nothing is reused. N=2 fix-loop + retries multiply invocations (the ~300× count). In-code notes: `compaction/html_skeleton.py:49`, `deep_agent_runner.py:214-215` ("every build re-sends its large fixed prefix uncached").

### Compaction / summarization
- **`html_skeleton` capability** (`agents/capabilities/compaction/html_skeleton.py:45-107`, `@register("compaction","html_skeleton")`): trims 50k+ prototype HTML to a ~1-3k skeleton. This is the verbatim lift of the former `engine._extract_html_skeleton` (tombstone `engine.py:6045-6050`). Invoked by `task_loop` only on task ≥2 (`task_loop.py:253-263`), threaded to `ectx.current_prototype_skeleton`, emitted at `engine.py:5952-5959`. Parity tests `tests/agents/test_phase3_compaction.py`.
- Other caps: `od_context` example cap 120k (`:189-191`), seed `[:6000]`/ref `[:4000]` (`:160,169`); skill truncation (`app/agents/skills.py:82,131`); brownfield `context_pack` selector `MAX_NEIGHBORS=8` (`context_pack/pack.py:37`).
- No general LLM summarizer on the live path (deepagents' built-in `SummarizationMiddleware` stays on, `deep_agent_runner.py:346`); legacy `app/agents/summarizer.py` is dead.

### Prompt caching status — **ON** (note discrepancy with memory)
- `BEDROCK_PROMPT_CACHE_ENABLED = True`, `BEDROCK_PROMPT_CACHE_TTL = "5m"` (`app/core/config.py:110-111`).
- `_BedrockCachePointsMiddleware` injects `model_settings["cache_control"]={"type":"ephemeral","ttl":...}` **only** on `ChatBedrockConverse` requests (`deep_agent_runner.py:205-258`, wired at `:352`). Added in commit `582b90c8` ("Bedrock prompt-caching middleware, config-gated, default on"); telemetry ISS-032.
- **Discrepancy:** the `prototype-token-cost` memory note says caching is "silently OFF on Bedrock." The code shows a recently-added middleware that turns it **ON**. The root cause the note describes (deepagents' `AnthropicPromptCachingMiddleware` caches only `ChatAnthropic`) is real and documented at `deep_agent_runner.py:212-215` — this middleware is the fix. **Caveat:** whether it caches the *growing* conversation prefix in a multi-turn chat depends on where `langchain_aws` places the single cache point — verify before relying on multi-turn cache reuse.

---

## 6. PERSISTENCE MODEL FOR A CHAT

### `run_events` is the natural home
- `RunEvent` (`app/models/run_event.py:20-38`): `id, run_id (FK workflow_runs), owner_id NOT NULL, workspace_id NOT NULL, seq (monotonic/run), event_id (idempotent), type, payload_json (JSON), created_at`; index `ix_run_events_run_seq (run_id,seq)`. Created in migration `0014` (`alembic/versions/0014_typed_artifacts_persistence.py:101-117`).
- Write seam: `ScopedStore.append_event` (`agents/authz.py:284-312`) via `_RunEventSink.persist` (`engine.py:329-353`). Read seam: `ScopedStore.read_events(run_id, after_seq)` (`authz.py:314-329`), exposed at `GET /api/runs/{id}/events` (`runs.py:858-909`) + WS reconnect replay (`websocket.py:985-987`).
- A chat message = a `type="chat_message"` `run_events` row → inherits per-run keying, ordering, idempotent replay, owner+workspace default-deny, **zero new table, zero new authz surface**.

### Migration convention
- **Next number = `0024`, `down_revision="0023"`.** Additive-only: `op.batch_alter_table("workflow_runs")` + `add_column(..., nullable=True)`, reversible downgrade (templates `0022`, `0023`). New tables (if not riding `run_events`): follow `0014` — `create_table` with `owner_id`+`workspace_id` NOT NULL + FK→`workflow_runs.id` + index.
- Guards a new migration must satisfy: single-head chain test (`tests/unit/test_migrations.py:180-190`), model↔migration parity (`tests/unit/test_alembic.py:116-143` + `alembic check`), migration-ledger content ratchet (`tests/agents/test_migration_ledger.py`).

### Ownership / IDOR patterns a chat API must follow
- `current_user` via `get_current_user` (`app/core/dependencies.py:153-178`, `HTTPBearer` + JWT + revocation). WS: `_authenticate_token` (`websocket.py:270-297`).
- **Two-layer pattern (canonical):** (1) `db.query(WorkflowRun).filter(id==workflow_id, user_id==current_user.id).first()` → **404** on miss; (2) `ScopedStore(owner_id, workspace_id, session).get_run(...) is None` → 404. Examples: `get_run_events` (`runs.py:872-896`), `get_run_artifacts` (`822-848`). **IDOR → 404, never 403** (`runs.py:14-17`).
- **P25** hardened family walk: `get_run_family` BFS over `parent_run_id.in_(...) AND user_id==current_user.id` only (`runs.py:933-1010`).
- **P13** WS cross-run write gate: `_review_gate_owned_by(gate_key, user_id)` before any resume write (`websocket.py:224-248`).
- **Do NOT reuse `chat.py::Message`** for per-run chat: legacy free-chat, keyed by `chat_session_id`, **user-scoped only, no `run_id`/`owner_id`/`workspace_id`** (`app/models/chat.py:37-52`).

### Table inventory (owner_id + workspace_id convention)
- BOTH NOT NULL (AUTHZ-01): `artifact_refs, run_events, run_capabilities, exec_runs, gate_events, hook_runs, validation_results, subagent_runs, wave_runs, mcp_credentials, repositories, workspaces`.
- Present but nullable (backfilled): `workflow_runs` (`workflow.py:58-59`), `workflows` (`workflow_definition.py:36-37`).
- Neither (user_id-scoped legacy): `chat_sessions/messages, workflow_memory, workflow_clarifications, handoff_*, users`.

---

## 7. CONSTRAINTS & LANDMINES

### A `chat` subsystem already exists (collision risk)
- `PIPELINE_AGENTS["chat"]` = 7 agents (`chat-discovery`…`chat-preview`), marked **INTERNAL** (`_INTERNAL_PIPELINES`, `agents/registry.py:172-194, 369-376`). Manifest `agents/workflows/chat/workflow.yaml` (never dispatched by the engine — driven by `ChatRunner`). Sequencer `app/agents/chat_runner.py` with its own vocab `phase_start/stream/phase_end/error/complete`. `chat_session_id` is "tracking only; unused" (`chat_runner.py:333`) → **no cross-message history is loaded** — each `user_message` is a fresh multi-phase run.

### Banned-pattern gate (`tests/agents/test_banned_patterns.py`)
- `create_deep_agent` import/call allowed **only** in `app/agents/deep_agent_runner.py` (`_ALLOWED_CREATE_DEEP_AGENT`, `:69`); no `class DeepAgent`/`def deep_agent`/`for _ in range(max_iterations)`; no local `deepagents`/`langchain_deepagents` module (except the sanctioned runtime cap). Kernel INV-1: `if pipeline_type ==` / `spec.id ==` banned in `agents/execution_engine/` (`_INV1_PATTERN`, test `:368`). `BaseAgent` token banned everywhere (`tests/unit/test_no_baseagent.py`).

### Import-linter (`pyproject.toml:131-185`)
- `agents.workflows`, `agents.capabilities`, `agents.runtime` **must not import** `agents.execution_engine` (kernel) or `app` (web layer). Kernel must not import `app.api`. → a chat **capability** lives under `agents/capabilities/**` (no `app.*`); heavy-dep impls go under `app/agents/**` importing only the port.

### Golden / characterization tests (INV-3)
- 5 byte+event goldens pinned: `prototype, od_prototype, od_ppt, prototype_revision, app_builder` (`tests/agents/characterization/golden/*`). Plus the **chat golden** `tests/agents/test_chat_contract.py` (byte-frozen `ChatRunner` output incl. 10-key `FinalOutputModel`).
- **`_VOLATILE_STRIP_KEYS`** (`tests/agents/characterization/_normalize.py:101-170`): keys dropped from the canonical multiset — `timestamp, pipeline_run_id, run_id, total_duration, estimated_cost_usd, model_id, context_sources, seq, event_id, deliverable_mimetype, deliverable_filename, redoable, cache_read_tokens, cache_write_tokens, total_cache_read_tokens, total_cache_write_tokens, image_count`. **Any new event key must be added here** or it breaks the 5 goldens; **any new event type must be added to `_DOCUMENTED_EVENT_TYPES`** (`test_phase3_cutover_verify.py:182`).

### Capability registry (how a chat capability registers)
- `@register(kind, name, *, user_allowed=False, description, config_schema)` (`registry.py:179-217`) + add `(kind,name)` to `_KNOWN` (`:81-147`) + add module import to `discover()` (`:251-322`). KINDs are free strings (no central branch). Registered kinds incl. `strategy, merge, validator, deliverable, context_provider, input_provider, task_parser, gate, tool, compaction, post_step, runtime, prompt, skill, hook, model_catalog, runtime_env, repo_index, context_pack, mcp_server, integration_provider`. **There is no `chat` kind today.**

### SC-001 / INV-1
- Kernel (`agents/execution_engine/`) is name-free (grep of `if pipeline_type ==|spec.id ==` = 0). Sanctioned name-branches live OUTSIDE the kernel: `websocket.py:1543/1556/1569` (od_* dispatch), `registry.py:384` (`=="custom"`). A chat feature must keep name-dispatch in the app/WS/ChatRunner layer, never the kernel.

### CI reality check
- The only wired CI (`infra/buildspec.yml:95`, AWS CodeBuild) runs `python3 -m compileall backend` — a **syntax gate only**. `.pre-commit-config.yaml` runs `ruff`/`pyright`(imports)/`eslint`/`tflint`. The banned-pattern/import-linter/characterization/ledger suites are **runnable pytest tests but not observed wired into the deploy pipeline** — treat as review-gate + local `pytest`/`lint-imports` (matches the "offline-test-suite" memory note). Verify with the team whether a separate test-CI runs them.

---

## 8. GAP ANALYSIS

### (a) Mid-run bidirectional chat (user↔agent while a run is live)
- **Exists:** the full pause/resume machinery — `asyncio.Event` registry (`store.py`), WS inbound handlers, `review_gate_ready`→`event.wait()`→`approve_review`, and the **redo instruction-injection seam** (`redo_directive` → `ADDITIONAL INSTRUCTIONS` block, `engine.py:5916-5922`). Cooperative cancel + suspend/reconnect are robust.
- **Missing:** (i) a WS inbound `chat_message` type; (ii) a way to deliver a user message to an agent that is *mid-generation* (there is none — an agent invocation runs to completion; you can only inject into the *next* composed context, exactly like redo); (iii) a generic engine event `chat_message`/`agent_reply`; (iv) an outbound path for the agent to *ask* the user mid-stream.
- **Shortest legal path:** model it on redo. Add a WS `chat_message` handler that (1) persists the user turn to `run_events` (`type="chat_message"`), and (2) either sets a new per-run `asyncio.Event` the engine awaits at a declared "chat gate" step, OR appends to a new consume-once `ectx.chat_directive` scratch that `_compose_context_message` renders as a `=== USER MESSAGE ===` block on the next agent invocation. Keep all name-dispatch in `websocket.py`/a capability; the kernel stays generic. A cleaner long-term form: a `gate:chat` capability (new `gate` impl under `agents/capabilities/gates/`) that loops emit→wait→inject, reusing the `human` gate as a template (`gates/human.py`).

### (b) Image upload into agent context
- **Exists:** ~80% — provider (`run_images`), normalization, per-agent gate, split-transport dispatch, manifest/compiler support, both model SDKs. Dormant.
- **Missing (3 switches):** (i) WS `run_pipeline` (and/or a new `chat_message`) must extract an `images` list and pass `images=` into `engine.execute(...)` (`websocket.py:1828`); (ii) a `workflow.yaml` must declare `input_providers: [run_images]`; (iii) the target agent/step must declare `injects: [images]`. Add `image_count` is already in `_VOLATILE_STRIP_KEYS` (goldens safe). For a chat channel specifically, also thread images onto a per-turn carrier (not just run-entry `ectx.run_images`).
- **Shortest legal path:** wire the three switches; for mid-run chat, extend the carrier so a chat turn's images become `input_blocks` on the next dispatch. No kernel change (all seams exist).

### (c) Arbitrary (non-image) context/file upload
- **Exists:** only `/api/files/extract-text` (PDF/DOCX/PPTX → brief text, no persistence). Repos ingest as a cloned working tree on the sandbox.
- **Missing:** any endpoint that persists uploaded bytes; any file→agent-context path beyond brief-text and the (dormant) image path. Bedrock/Anthropic natively accept only images (and Anthropic PDFs) as blocks — other binaries need extraction-to-text or sandbox placement.
- **Shortest legal path:** add an authed `POST /api/runs/{id}/files` (two-layer owner check → 404) that writes bytes under the run's `RunSandbox` (`sandbox.py`) so agents `read_file` them, and/or records an `artifact_ref` (text) / a `run_events` row referencing the sandbox path. Mirror `run_images` with a `file_content` `input_provider` for formats the model accepts as blocks. Migration only if a new table is needed (else ride `run_events`/sandbox).

### (d) Per-run chat history surviving reconnect + reopen
- **Exists:** `run_events` gives durable, owner+workspace-scoped, seq-ordered, idempotent replay; live WS reconnect replay (`websocket.py:985-1018`) and REST history (`GET /api/runs/{id}/events`) already stream the full tail. `agent_input` context and `agent_chunk` outputs are already persisted per-run.
- **Missing:** a `chat_message`/`agent_reply` event type persisted to `run_events`; a FE conversation view keyed off `/events`. The legacy `Message` table is unsuitable (no run linkage).
- **Shortest legal path:** persist each chat turn as a `run_events` row via `ScopedStore.append_event` (`type="chat_message"`, add to `_DOCUMENTED_EVENT_TYPES` + `_VOLATILE_STRIP_KEYS` for any volatile subkeys). History then survives reconnect and reopen through the existing replay paths with **zero new table**.

### (e) Context compression for long chats
- **Exists:** a `compaction` capability seam (`compact(text)->str`, invoked by `task_loop`) with a working impl (`html_skeleton`); deepagents `SummarizationMiddleware` stays on for in-graph history; Bedrock prompt-caching middleware is on.
- **Missing:** a conversation-history compaction/summarization impl (html_skeleton is HTML-specific); the checkpoint thread is per-invocation, so a growing dialogue is not carried natively — history would be re-composed into each turn's context and needs trimming.
- **Shortest legal path:** add a `compaction` capability (e.g. `chat_history`) and/or a `context_provider` (e.g. `conversation_history` reading the run's `chat_message` `run_events` rows, compacted) composed into the human turn by `_compose_context_message`. Both are declarative capability additions (no kernel edit); verify prompt-cache placement for multi-turn reuse before relying on it.

### Cross-cutting recommendation
Every piece lands as **capabilities + app/WS-layer wiring + at most one additive migration (`0024`)** — never a kernel `if pipeline_type ==` branch (SC-001/INV-1). The redo-with-instructions flow is the single closest working analog for bidirectional injection; `run_events` is the persistence spine; `run_images` is the template for multimodal/file providers. Watch the collision with the existing internal `chat` pipeline + its frozen golden, and add any new event type/key to both `_DOCUMENTED_EVENT_TYPES` and `_VOLATILE_STRIP_KEYS`.

---

## CORRECTIONS (2026-07-07 post-merge verification — do not act on the superseded claims above)

The verbatim report above predates the same-day merge of origin (KAN-92..101) and the image-input waves. Verified corrections:

1. **§4 "NOT wired at ingress" — now FALSE on all three clauses.** WS `run_pipeline` reads `images` and passes `images=` (`websocket.py:879/:911/:2055`, with `_validate_images` at `:1887-1910`); `prototype/workflow.yaml:40` declares `input_providers: [run_images]`; `prototype-specify/AGENT.md:9-12` declares `injects: […, images]`. The image path is LIVE end-to-end for `prototype` (offline-proven, `test_prototype_image_optin.py`). Landed via `.planning/IMAGE-INPUT-PLAN.md` + quick tasks `260707-{edw,frv,gvq}`. Bonus hardening not in the original scope: mime allow-list, ~3.75MB/image + ≤20 + ~8MB aggregate caps, vision-model guard, `IMAGE_INPUT_ENABLED`. Images are **payload-transient** (never sandbox/DB/run_events) → do not survive reopen/replay (ND-10).
2. **§4 "Only one upload surface … no persistence" — STILL TRUE.** UPLD-01/03 remain fully open (no `POST /runs/{id}/files`, no `context_provider:uploaded_files` — grep 0).
3. **§1 `approve_review` actions — now FOUR:** `approve`/`redo`/**`update_specs`** (+ reject); `update_specs` carries `analysis_report` in the `instructions` field (`websocket.py:1417`). New WS error `pipeline_not_running` (recoverable:false) fences the channel on terminal runs (KAN-100).
4. **§1 internal signals** now also include `_gate_update_specs` and `_revision_analyze_output` (never on the wire; absent from `_DOCUMENTED_EVENT_TYPES` by design).
5. **§3 thread-id claim "nothing carries a running dialogue across invocations" — now has an EXCEPTION:** KAN-101's `_run_spec_revision_sub_pipeline` (`engine.py:4295`) re-runs specify→plan→analyze on their **BASE** thread_ids (no `:redo{N}`-style fork), accumulating dialogue across unlimited revision cycles — an unaudited checkpoint-replay risk (ND-11).
6. **§2/§8 "redo is the single closest analog for bidirectional injection" — superseded:** `update_specs` is a richer shipped precedent (gate-triggered multi-agent sub-pipeline with its own consume-once seam `ectx.spec_revision_context`, cleared in `finally`; re-opens the same gate via `spec_revision_pending_output` without an extra model call). "Mid-generation injection is impossible" still holds.
7. **§2 gate semantics:** `_run_review_gate` now races `cancel_event` (Stop dismisses a paused gate — the P23 F7 deferral is effectively shipped); `_evaluate_gates` skips the declared human gate when `gate_agent_ids` excludes the agent (KAN-94) — gates are event-driven, not manifest-driven.
8. Many cited line numbers in §§1-3 shifted (KAN-100/101 insertions); re-grep before use.
