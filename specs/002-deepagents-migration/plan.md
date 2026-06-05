# 002 — DeepAgents Migration Plan

> Swap the custom hand-rolled agent runtime for the **LangChain `deepagents`**
> library across all pipelines, engine-driven, with the frontend visuals
> unchanged. Living document — update phase status + the decision log as work lands.

| | |
|---|---|
| **Branch** | `deepagents-full-swap` (off `0e9c410`) |
| **Status** | Phases 0–7 ✅ complete (Phase 0 `bfd573b` · Phase 1 `666e531` · Phase 2 `0d09702` · Phase 3 `030820b` · Phase 4 `218582d` · Phase 5 `8819f40` · Phase 6 `01c183f` · Phase 7 `424765e`+`e973cf0`+`92bd531` [7a/7b/7c]) · **🎉 true zero-legacy reached** · Phases 8–10 planned |
| **Created** | 2026-06-03 |
| **Supersedes** | the custom `app/agents/deep_agent.py` ReAct loop (deleted in Phase 7) |

---

## Current state — START HERE (resume point)

**As of 2026-06-05.** Phases **0–7c complete & committed locally** on `deepagents-full-swap`;
**Phase 8 (verify — Bedrock Haiku, local) is next.** Phase 7 is fully landed and **the codebase is now
true zero-legacy** — no `BaseAgent`/`DeepAgent`/`AgentOrchestrator` anywhere: **7a** excised the dead
pipeline-legacy + moved title-gen off `DeepAgent`; **7b** migrated free-chat onto `ChatRunner` (deleted
`orchestrator.py`/7 chat agents/`deep_agent.py`); **7c** migrated `/flowin-handoff` off `BaseAgent` and
**deleted `base.py`**. The deepagents runtime is **live across all pipelines** (Phase 3); the prototype build runs the **per-task sub-agent + Both-validation** model
(Phase 4); **prototype revision** runs the same validation + seeds the parent run's spec/design
(Phase 5); and the agent registries are **reconciled to a single source of truth** with a per-agent HITL
gate toggle live (Phase 6). The WebSocket/UI event contract is **byte-identical to pre-migration**
(audited GREEN each phase).

**What works now:** every pipeline agent runs as a `DeepAgentRunner` (a deepagents
`create_deep_agent` graph) built by `create_runner`, driven by the engine through ONE
`astream_events` loop; deliverables are read from a per-run disk **sandbox** (`prototype.html` /
code-gen `filename:` blocks); per-run HITL gate-selection (default = static `Human_Gate`);
Postgres/InMemory checkpointer with per-agent threads; prototype build = one isolated sub-agent per
task (reads `spec.md`/`design.md` + an injected `=== CURRENT TASK ===` block) with per-task
static+render validation and a bounded **internal** fix-loop.

**⚠️ Unpushed:** the branch is **17 commits ahead of `origin/deepagents-full-swap`** (its upstream was
last pushed 2026-06-03 at Phase 2 `b306ecc`) — everything Phase 3 → Phase 7c + their docs commits + this
refresh. **Push is blocked on GitLab auth** (git-credential-manager hangs / `HTTP Basic: Access denied`;
earlier-session pushes worked, so the credential lapsed — likely GlobalProtect VPN must be **off**, or
refresh the GCM token). `git push origin HEAD` ships them all once auth is fixed. **Commits are local —
nothing is lost.**

**Map of this doc:** per-phase outcomes are in §5 (each ✅ phase has a **Landed** note); all
deferred/carried-forward items are in **§9**; the **code map** (new modules + key functions + tests)
is **§11**; the **working method** (how phases are executed + the test recipe + dev-runtime gotchas)
is **§12**.

---

## 1. Goal & scope

Replace the bespoke `DeepAgent` (a hand-rolled `for i in range(max_iterations)` loop
over `llm.bind_tools().stream()`) with the LangChain `deepagents` library for **every**
pipeline agent. The execution engine remains the deterministic sequencer; each agent
becomes a `create_deep_agent` graph behind an adapter that maps LangGraph stream events
to our existing WebSocket events, so the UI is unchanged. Adopt the library's native
filesystem, summarization, HITL interrupts, and checkpointing. Add per-task sub-agents
to the spec-driven build (prototype first).

Motivation: the custom loop's brittle tool-calling produced the build/revision failures
diagnosed earlier (planner format misfires, route↔section ID mismatches, shallow
revisions). The library brings planning, isolated sub-agents, automatic context
management, durable HITL, and resume — on a maintained ecosystem.

## 2. Firm decisions (locked via Q&A)

- **Hybrid control flow.** Engine sequences the pipeline + gates; every agent is a
  `create_deep_agent` graph behind a `DeepAgentRunner` adapter.
- **Per-task sub-agents, engine-orchestrated** (prototype first). The engine launches
  ONE isolated sub-agent per task; each is *forced* to read its task + requirements
  (spec) + architecture/design before executing, then validates.
- **Real-disk sandboxed filesystem**, isolation **per-user/per-run**
  (`<RUNS_ROOT>/<user>/<run>/` on the persistent EBS data volume), `execute` enabled.
- **Per-task validation = BOTH**: static self-check (routes↔sections resolve, no dead
  links/handlers) **+** sandbox headless render, fix-loop until pass.
- **HITL = per-agent toggle** at submit, between agents; today's gated agents
  pre-checked; durable via the checkpointer.
- **Reliability**: embed botocore retries/timeouts; **DROP** per-agent iteration caps
  (high `recursion_limit` backstop + cost watch).
- **Adopt** library auto-summarization (replaces `summarizer.py`), HITL interrupts, and
  LangGraph checkpointing+resume (Postgres).
- **Model** stays user-selected (Haiku default); a stronger model just for executor
  sub-agents is a noted future lever.
- **Version**: `deepagents==0.6.7` (DeltaChannel O(N) checkpoints), which bumped
  `langchain→1.3.4 / langchain-core→1.4.0 / langgraph→1.2.4`.

## 3. Hard invariants (apply to every phase)

- **🚫 No legacy, no backward compatibility.** No feature flag, no dual runtime path, no
  `isinstance`-both checks, no compat shims. Consumers are *switched*, not duplicated;
  the old runtime is *deleted* (Phase 7). Rollback is VCS-level (don't merge/deploy until
  green) — there is no runtime toggle.
- **🎨 UI stays identical, enhance-only.** Existing visuals/events must not regress in any
  phase; only additive enhancements are allowed. Enforced by a WebSocket event-parity
  capture (old vs new) at the end of every phase that touches streaming.

## 4. Target architecture

```
ExecutionEngine (deterministic sequencer — unchanged role)
 ├─ per-agent HITL gate (user-toggled, checkpoint-backed pause/resume)
 ├─ create_agent(spec) -> DeepAgentRunner ──wraps──► create_deep_agent(graph)
 │      model=build_model(ctx.model)  backend=DiskBackend(<user>/<run>/)
 │      checkpointer=Postgres   summarization=on   library-subagents=off
 │      .astream_events ─► STREAM ADAPTER ─► {chunk,usage,tool_call,tool_result,
 │                                            task_progress,done,__interrupt__}
 │                       ─► WebSocket (frontend UNCHANGED)
 └─ EXECUTE step (prototype): engine loops the plan's task list →
        for each task: launch 1 isolated sub-agent graph
          → forced read(task) + read(spec) + read(design)
          → edit prototype.html on disk
          → validate: static checks + headless render → fix loop
```

## 5. Phases

Legend: ✅ done · 🔜 next · ⏳ planned · ⛔ blocked

### Phase 0 — Foundations ✅ (commit `bfd573b`)
Additive scaffolding; nothing wired into the engine. Tasks #14–#23.
- deps pinned + resolved (deepagents 0.6.7 + checkpointer + playwright; langchain bump).
- `app/agents/model_factory.py` `build_model()` (provider select + botocore retries).
- `app/agents/sandbox.py` `RunSandbox` (per-user/run dirs, traversal-proof, TTL sweep).
- `app/agents/checkpointer.py` (AsyncPostgresSaver factory; InMemory dev fallback).
- `app/agents/render_check.py` (headless Chromium: console errors + nav assertions).
- config: `RUNS_ROOT`, `AGENT_RECURSION_LIMIT=400`, `RUN_DIR_TTL_HOURS=48`.
- Dockerfile: Playwright Chromium + `/app/runs`; compose + bootstrap: runs volume.
- **Verify gate ✅**: pip resolves; modules import; sandbox traversal blocked; real
  Chromium renders a sample SPA with working nav; deepagents 0.6.7 builds the
  Bedrock+HITL+checkpointer graph.
- **UI**: unchanged. **#15** live Bedrock invoke + HITL pause/resume ✅ verified on 0.6.7
  (2+2 via tool-call; `interrupt_on` paused at `HumanInTheLoopMiddleware.after_model`;
  `Command(resume)` → 7).

### Phase 1 — `DeepAgentRunner` adapter + stream mapping ✅ (commit `666e531`)

**Landed.**
- `app/agents/deep_agent_runner.py` — `DeepAgentRunner` wrapping `create_deep_agent`;
  methods `astream_events` (emits `chunk`/`usage`/`tool_call`/`tool_result`/`done`/`gate`/
  `error`), `astream_with_usage`, `astream`, `run`, plus `model_id` / `tools` accessors.
- Library sub-agents off + built-in tool exclusion via a per-graph `_ToolFilterMiddleware`
  (public `AgentMiddleware`/`ModelRequest.override` API), **not** `HarnessProfile`; the
  `exclude_builtin_tools` flag gives `tools==[]` agents a pure-text stream (no tool chips).
- Disk `FilesystemBackend(virtual_mode=True)` rooted at the Phase-0 `RunSandbox`;
  checkpointer + `interrupt_on` plumbed; HITL `gate` detected post-loop via `aget_state`.
- **Verify**: offline parity test (`tests/agents/test_deep_agent_runner_parity.py`) green —
  event-type sequence + tool name/args/result + usage byte-match legacy; live HITL smoke
  (`tests/agents/test_deep_agent_runner_hitl_live.py`, opt-in/SSO-gated) proven against
  Bedrock Haiku (`gate` → `Command(resume)` → terminal).
- **NOT** wired into the factory/engine yet (Phase 2/3).

The heart of the swap. New module `app/agents/deep_agent_runner.py` wraps a
`create_deep_agent` graph and re-exposes the **exact** contract the engine consumes from
the legacy `DeepAgent` today, so Phase 3 can swap it in with one `isinstance`/dispatch
change. **Built + parity-tested in isolation; NOT wired into the factory or engine yet**
(the factory keeps returning `DeepAgent` until Phase 2).

**Contract to reproduce** (verified against `app/agents/deep_agent.py` +
`agents/execution_engine/engine.py:742–832, 1088–1098`). The engine consumes:
- `agent.astream_events(msg)` → dicts: `chunk{chunk}`, `usage{input_tokens,output_tokens}`,
  `tool_call{tool,args}`, `tool_result{tool,result}`, `done{output}`, `error{error}`.
  Engine maps chunk→`agent_chunk`, sums `usage`, tool_call→`tool_call`, tool_result→
  `tool_result` (and `tool=='report_task_complete'` → `task_progress` from `_prototype_store`).
  Note: the engine loop does **not** read `done`/`error` (output is built from `chunk`s) —
  parity is on the *streamed* event vocabulary, not on `done`.
- `agent.astream_with_usage(msg)` → text chunks then a final `TokenUsage`
  (`app/agents/base.py`) — used for text-only agents (`tools==[]`).
- `agent.run(msg)` → `str`; plus `agent.model_id: str`, `agent.tools: list`.

**Construction** (per §4): `create_deep_agent(model=build_model(model)|instance,
tools=tools, system_prompt=system_prompt, backend=FilesystemBackend(root_dir=<RunSandbox.root>,
virtual_mode=True), checkpointer=<Phase-0 factory>, subagents=None, interrupt_on=… )`,
driven with `config={"configurable":{"thread_id":run_id}, "recursion_limit":AGENT_RECURSION_LIMIT}`.
- **Library sub-agents OFF**: `subagents=None` + exclude the `task` tool
  (`HarnessProfile.excluded_tools`) so the model can't spawn its own sub-agents (engine
  orchestrates those in Phase 4).
- **Disk filesystem ON**: `deepagents.backends.FilesystemBackend(virtual_mode=True)` rooted at
  the Phase-0 `RunSandbox` dir (traversal-proof). `FilesystemMiddleware`/`SubAgentMiddleware`
  are *mandatory* in `create_deep_agent` and cannot be excluded.
- **Summarization ON** (base-stack default) — supersedes `summarizer.py` (deleted Phase 7).
- **Text-only parity**: because the mandatory middleware injects file/todo tools + prompt
  sections, `tools==[]` agents must additionally exclude the built-in tools
  (`task,write_todos,ls,read_file,write_file,edit_file,glob,grep,execute`) via a lean
  `HarnessProfile` so they stream **pure text** (no new tool chips appear in the UI).

**LangGraph → our-events mapping** (`graph.astream_events(..., version="v2")`):

| LangGraph event | Our event | Notes |
|---|---|---|
| `on_chat_model_stream` | `chunk{chunk}` | `_extract_text(data.chunk.content)`; accumulate `full_output` |
| `on_chat_model_end` | `usage{input,output}` | read `data.output.usage_metadata` (reliable on Bedrock) |
| `on_tool_start` | `tool_call{tool,args}` | `tool=event["name"]`, `args=data.input` |
| `on_tool_end` | `tool_result{tool,result}` | `result=str(data.output)`; `report_task_complete` name passes through → engine sentinel fires |
| stream end, no interrupt | `done{output}` | `output=full_output` |
| pending interrupt | `gate{interrupt,thread_id}` | post-loop `await graph.aget_state(config)`; payload = HITL `ActionRequest` (consumed Phase 3) |
| exception | `error{error}` | mirror legacy swallow; Phase 3 promotes to raise |

**Tasks**
1. `DeepAgentRunner.__init__` — build the graph (model via `build_model` or an injected
   `BaseChatModel`; disk backend from `RunSandbox`; checkpointer; subagents off + `task`
   excluded; summarization on; optional `interrupt_on`; recursion limit in config).
2. Lean `HarnessProfile` for `tools==[]` → pure-text stream (verify exact built-in tool names).
3. `astream_events()` — the mapping table above, `full_output` accumulation, error guard.
4. Interrupt detection → `gate` event (post-loop `aget_state`; thread_id/config plumbing).
5. `astream_with_usage()` — text chunks then one merged `TokenUsage`.
6. `run()` + `model_id` / `tools` accessors.
7. **Parity test** (offline, scripted fake model) — see verify gate.
8. Live HITL smoke (opt-in, SSO-gated): real Bedrock Haiku, 1 tool call + 1 interrupt →
   `gate` fires, `Command(resume)` → `done` (reuses the Phase-0 smoke pattern).

- **Verify gate**: `tests/agents/test_deep_agent_runner_parity.py` drives BOTH the legacy
  `DeepAgent` (fake llm patched onto `.llm_with_tools`) and the new `DeepAgentRunner`
  (fake `BaseChatModel` injected) over the **same** scripted sequence (text → call
  `report_task_complete` → result → final text) and asserts the ordered event-type stream
  + tool name/args/result match; plus a `tools==[]` case asserting `astream_with_usage`
  yields chunks then a `TokenUsage`. Parity is on event **type/semantics**, not byte-identical
  chunking. Must be green before Phase 2.
- **UI**: unchanged (adapter not wired; parity-gated).
- **Phase-1 risks**: (a) interrupts aren't first-class in `astream_events` → post-loop
  `aget_state`, fallback to `astream(stream_mode=["messages","updates","values"])`;
  (b) mandatory middleware → text-only needs tool exclusion (task #2); (c) Bedrock async
  streaming blocking the loop (why legacy used `to_thread`) → verify the native async path,
  thread-offload if needed; (d) `usage_metadata` zeros (seen before) → read off
  `on_chat_model_end`, fallback to last chunk.

### Phase 2 — Runner factory + disk tool-sets (additive; wired NOWHERE) ✅ (commit `0d09702`)

**Landed.** `create_runner(agent_id, ctx)` + `_build_runner_tools(spec, ctx)` (per-agent tool-set
+ `exclude_builtin_tools`) in `agents/factory.py`; store-free `report_task_complete`
(`app/agents/tools/runner_tools.py`); additive `AgentContext.run_id`. All additive, wired
NOWHERE — `create_agent`/`DeepAgent`/engine byte-unchanged (independently audited GREEN).
Isolation gate `tests/agents/test_create_runner.py` proves each class behaves: text-only→pure
text (no tool chips); code-gen→file on the sandbox disk; prototype-build→`prototype.html` +
`report_task_complete` event; planning→`PLANNING_TOOLS` only. Native `deepagents` tools
(`FilesystemBackend` + `write_todos`) replace `AgentWorkspace`/`todo_write`/`emit_artifact`.

**Re-scoped 2026-06-03**: the factory→runner and engine→runner switches are inseparable
(shared `create_agent`; the `use_deep` `isinstance` gate at `engine.py:745`; no dual-path
allowed), and AGENT.md prompt bodies are shared with the live path — so the breaking cutover
moves entirely to Phase 3. Phase 2 builds the runner-construction path **additively** and
verifies it in isolation (Phase-1 discipline); `create_agent`/`DeepAgent` stay live and
untouched, the engine is unchanged, every commit stays green.
- **`create_runner(agent_id, ctx)`** in `factory.py`, alongside (NOT replacing) `create_agent`:
  reuses `_compose_system_prompt` verbatim; builds a `RunSandbox(ctx.user_id, ctx.run_id)`;
  constructs a `DeepAgentRunner` (model `build_model(ctx.model)`, disk backend, `checkpointer`
  + `interrupt_on` params plumbed but defaulted off, `recursion_limit` — retries/limits already
  embedded by the runner in Phase 1).
- **`_build_runner_tools(spec, ctx)`** — per-agent tool-set + `exclude_builtin_tools`, mapping
  the native `deepagents` tools onto today's tool sets:
  - text-only (`tools==[]`) → `([], exclude=True)` — pure text, no tool chips.
  - code-gen (`workspace`) → `([], exclude=False)` — native `write_file`/`read_file`/`edit_file`/
    `ls` replace `make_workspace_tools`; deliverables live on the sandbox disk.
  - prototype build/validate (`prototype_emit_only`) & full (`prototype`) →
    `([report_task_complete], exclude=False)`; `emit_artifact` dropped (agent writes
    `prototype.html` via native `write_file`/`edit_file`), `todo_write`→native `write_todos`,
    template-read tools **dropped** (already pre-injected into the prompt).
  - planning (`planning`) → `(PLANNING_TOOLS, exclude=True)` — stub tools unchanged; no disk.
- **Store-free `report_task_complete`** — a new runner tool that just returns a confirmation
  (no `PrototypeArtifactStore`); Phase 3's engine derives `task_progress` from its tool events.
- **`AgentContext.run_id`** (additive) so `create_runner` can root the sandbox per-run.
- **Verify gate**: isolation test — `create_runner` for one agent of each class (text-only,
  code-gen, prototype-build, planning) produces a correctly-configured runner that *behaves*
  (scripted model + temp `RunSandbox`): text-only streams pure text; code-gen writes a file to
  the sandbox disk; prototype-build writes `prototype.html` + emits a `report_task_complete`
  tool_result with the right args; planning exposes `PLANNING_TOOLS` and no native fs tools.
- **UI**: unchanged (nothing wired). **Out of scope → Phase 3**: the cutover, AGENT.md prompt
  edits, reading outputs from disk, HITL, checkpointing.

### Phase 3 — Atomic cutover: engine drives the runner + HITL + checkpointing ✅ (commit `030820b`)

**Landed.** Engine flipped to `create_runner` + a single `astream_events` loop (`use_deep`/`astream_with_usage`
deleted); deliverables read from the per-run sandbox (`prototype.html`; code-gen via `serialize_sandbox_deliverable`,
byte-matching `to_final_output`); `task_progress` derived from `report_task_complete` events (run-level/cumulative);
Postgres/InMemory checkpointer wired with per-agent `thread_id`s; per-run HITL gate-selection (default = static
`Human_Gate` set; `review_gate_*` events unchanged); dead cross-agent summarizer removed; 4 prototype prompts
rewired to `write_file("prototype.html")`. **Independently audited GREEN** — WS event-type set identical (22 types),
payload shapes byte-equal, no dual-path/shims, exact scope. The verify gate caught + fixed a per-task `task_progress`
count regression (now cumulative). **Pending → Phase 8**: live Bedrock runs (SSO) + cross-process resume-after-kill
(Postgres). Accepted cosmetic deltas: native `write_file` result text + LangGraph tool-event interleave order (the
UI keys on event type + `data`, so it's unaffected). `DeepAgent`/`summarizer.py` remain dead until Phase 7.

The single breaking change — **all pipelines at once** (forced by shared `create_agent` + the
The single breaking change — **all pipelines at once** (forced by shared `create_agent` + the
no-dual-path invariant). Lands green-together:
- **Flip**: the engine calls `create_runner` (or `create_agent` now returns the runner); delete
  the `use_deep`/`astream_with_usage` split and drive `runner.astream_events` directly.
- **Outputs from disk**: the engine reads the deliverable from the run sandbox — `prototype.html`
  for prototype/od_prototype/revision; code-gen files serialized into the **same** `filename:`
  block format `to_final_output()` produced (UI-identical). `task_progress` derived from
  `report_task_complete` tool events (replacing `PrototypeArtifactStore.completed_tasks`);
  revision seeds `prototype.html` into the sandbox instead of `AgentWorkspace`.
- **AGENT.md prompt edits** (shared with the now-dead live path, so they land here): "call
  `emit_artifact`" → "write `prototype.html`"; workspace-tool references → native fs tools.
- **Per-agent HITL**: read per-run gate selections; keep emitting the **same** `review_gate_*`
  events; durable via the checkpointer + `Command(resume)`; default = currently-gated agents
  pre-checked. (Inter-agent gate stays engine-level; the runner's tool-level `gate` is the
  future lever — open item.)
- **Checkpointing**: real `get_checkpointer()` (Postgres) wired; `summarizer.py` calls removed
  (library summarization); token totals from the adapter's `usage` events.
- **Verify gate**: full WS event-parity capture (old vs new) across a text, code-gen, and
  prototype run; checkpoint resume after a kill.
- **UI**: unchanged (identical chunk/tool/usage/gate/progress events; deliverables byte-same).

### Phase 4 — Prototype: per-task sub-agent execute + Both validation ✅ (commit `218582d`)

**Landed.** Prototype build runs an isolated sub-agent per task: the engine writes
`spec.md`/`design.md`/`tasks.md` to the run sandbox, injects the current `## Task N:` block under
`=== CURRENT TASK ===`, and after each task runs Both-validation (`static_check` + `render_check`)
with a bounded **N=2, same-sub-agent, INTERNAL fix-loop** (a non-yielding coroutine → UI events
unchanged). `static_check` (stdlib: routes↔sections / routes-map / handlers / is-active) added as a
sibling to `render_check`. **Independently audited GREEN** — 11/11 checks, event vocabulary
identical, executor on the run-selected model, exact 6-file scope. Durable tests:
`test_phase4_build_loop.py` (8) + `test_static_check.py` (25). **Pending → Phase 8**: live Bedrock
end-to-end (SSO). Note: `backend/CLAUDE.md` is stale (pre-migration) — refresh in Phase 7.


Replace `_run_build_task_loop`'s "call prototype-build N times with injected context" with an
**isolated sub-agent per task + per-task Both-validation + bounded fix-loop**, building on the
Phase-3 per-task `create_runner` loop. Scope = the **`prototype`** pipeline (specify → plan →
build → validate); `od_prototype` isn't registered; code-gen sub-agents are Phase 10.

**Pipeline facts:** `prototype-specify` ("Specification & Architecture") emits `<spec>` (spec +
Template/Design-System section); `prototype-plan` emits `<tasks>` as **Task 1 = full HTML shell**
(every empty `<section data-page>` + nav chrome + routes map + DS tokens) · **Tasks 2..N = one page
each** · **Task N+1 = validation**. Because the shell is built first, render+nav checks are
meaningful after EVERY task.

**Locked decisions (2026-06-04 Q&A):**
- **Context = Both**: the engine writes `spec.md` (specify's `<spec>`), `design.md` (active template
  SKILL.md + DESIGN.md from `od_context`), and `tasks.md` to the run sandbox; each per-task sub-agent
  gets its **current task injected** AND is told it may `read_file` spec/design for deeper detail.
- **Validation = Both, every task**: after each task — static check (routes↔sections resolve, routes
  map complete, every handler/onclick defined, no dead refs) **+** `render_check` (headless Chromium:
  nav switches, no console errors).
- **Fix-loop**: on failure, re-invoke the **same** task sub-agent with the validation errors + current
  `prototype.html`; **bounded N=2**, then log + continue (never block the whole build).
- **Executor model**: the run's **user-selected model (Haiku default)**; planner/validator too.
- **Engine-orchestrated**: the engine writes the spec/design/tasks files (no specify/plan prompt
  change); `report_task_complete`/`task_loop_progress`/`task_progress` events **unchanged** (UI
  identical, richer build underneath). The planner's final "validation task" stays a normal task —
  the engine's programmatic Both-validation is the real gate.

**Tasks:** (1) `app/agents/static_check.py` — no-browser routes↔sections/handlers validator + test;
(2) `prototype-build` prompt: add the read-`spec.md`/`design.md`-first framing for a per-task
sub-agent; (3) engine build-loop rewrite — write spec/design/tasks to the sandbox + isolated per-task
sub-agent (current-task injection) + Both-validation (static + render) + bounded fix-loop; (4) verify
gate (multi-task build renders + nav works; an injected defect is caught+fixed; events unchanged;
offline + live-if-SSO); (5) independent audit; (6) plan update + commit + push.
- **UI**: unchanged (same progress events).

### Phase 5 — Revision: validation + parent-context seeding ✅ (commit `8819f40`)

**Landed.** Revision now runs the build's Both-validation as a **smart-hybrid policy**, and the
revision agent can consult the parent run's spec/design. `_run_validation_fix_loop` generalized
(`agent_id`/`baseline_static`/`baseline_console`/`user_instruction`/`label`; **empty baseline +
no instruction + `label=""` ⇒ build path byte-identical**) with module-level helpers
`_static_issue_sigs`/`_console_sigs`/`_select_issues_to_fix`. `execute(parent_run_id=…)` seeds
`spec.md`/`design.md`/`tasks.md` from the parent sandbox (`RunSandbox(user_id, parent_run_id)`;
graceful degrade), baselines the seeded original **pre-edit**, and after the revision agent runs
invokes the fix-loop (`agent_id="prototype-revision-agent"`, `label="revision"`) **before** read-back
— **internal/non-yielding** (emits no events), **never blocks**. Frontend sends
`source_workflow_run_id`; websocket threads `parent_run_id` into `execute()`. **Independently audited
GREEN** — exact 6-file scope; all 3 locked decisions + invariants verified at file:line; build
byte-identity proven exhaustively (108 selection cases, 0 mismatches); no new WS event types / no
phantom 2nd agent. Tests: `test_phase5_fixloop_selection.py` (17) + `test_phase5_revision_validation.py`
(8); full agent net **83 passed**. **Pending → Phase 8**: live Bedrock end-to-end.

Scope = the **`prototype_revision`** pipeline (ONE agent, `prototype-revision-agent`, editing
`prototype.html` in place). **"Chaining via files" is already realized** (Phase 3/4: the engine writes
`spec.md`/`design.md`/`tasks.md`; the build reads them; the revision agent already has native
`ls`/`grep`/`read_file`), so Phase 5 = **(1)** a programmatic post-revision validation + bounded
fix-loop and **(2)** seeding the parent run's spec/design into the revision sandbox. **Build loop
unchanged.**

**Already done (Phase 3):** `execute()` seeds the inlined HTML as `prototype.html` in the run sandbox,
slims the prompt to a file-pointer (`engine.py:279-289`), runs `prototype-revision-agent`, and reads
the edited file back as the deliverable (`546-563`). The agent's prompt already enforces
route/section/handler wiring + a re-read-before-finish self-check.

**The gap:** no *programmatic* validation runs after a revision (Phase-4's `_run_validation_fix_loop`
is hardcoded to `prototype-build`/"task N of M" and only called in the build loop), and the revision
agent can't consult the original spec/design.

**Locked decisions (Q&A 2026-06-04):**
- **Validation = smart hybrid** (NOT "fix-all", NOT "log-only" — the user's words: *"fix everything it
  broke … focus on what the user said … and if there is an issue that needs fixing otherwise the html
  won't work / won't display proper content, fix that too"*). After the revision edits `prototype.html`,
  auto-fix (bounded, internal):
  - **regressions** — static/render issues that are NEW vs. a **baseline** computed on the seeded
    original *before* the agent edits; PLUS
  - **hard render-breakage regardless of baseline** — uncaught page errors, dead nav links (a click
    activates no `<section data-page>` → blank page), blank/empty render (the "won't display proper
    content" class);
  - while **ignoring pre-existing static nits / benign pre-existing console noise** the revision did
    NOT introduce and that don't break rendering.
  - The fix prompt re-injects the **original revision instruction** (stay focused on what the user
    asked) and says "fix ONLY the listed issues, keep the requested change intact, touch nothing else."
    Bounded **N=2**, then log residual + continue — **never blocks**.
- **Seed parent spec/design = YES.** The frontend sends `source_workflow_run_id` for prototype revision
  (the field already exists — od_prototype uses it); the backend threads it as `parent_run_id` into
  `execute()`; for `prototype_revision` the engine reads `spec.md`/`design.md`/`tasks.md` from the
  **parent run's sandbox** (`RunSandbox(user_id, parent_run_id)` — the build wrote them there and
  sandboxes survive to the 48h TTL, no run-end `cleanup()`) and writes them into the revision sandbox.
  **Graceful degrade** (log + proceed on HTML+instruction only) if the parent files are gone.
- **Chaining = revision-only** — NO specify→plan→build handoff refactor.

**Mechanism (grounded):**
- `execute(… , parent_run_id: str | None = None)` (additive). `websocket._run_pipeline_to_queue`
  passes the already-resolved `parent_run_id` (`websocket.py:1016-1023`) into `engine.execute(…)`
  (today it's used only for the `WorkflowRun` row).
- Generalize `_run_validation_fix_loop`: add `agent_id` (default `"prototype-build"` → build path
  unchanged; revision passes `"prototype-revision-agent"`), `baseline_static`/`baseline_console` sets,
  and a `user_instruction` for the fix prompt. **Empty baseline → byte-identical to today's build
  behavior** (fix-all). The fix sub-agent runs on a `…:revision:fix{n}` thread, consumed **internally**
  (non-yielding) → **UI unchanged**.
- Invoke order for revision: seed parent files + compute baseline (right after seeding `prototype.html`,
  `engine.py:283`) → run `prototype-revision-agent` (visible, as today) → generalized fix-loop
  (internal) → read back `prototype.html`.

**Tasks** (one Opus-4.8 max-effort sub-agent each; the two `engine.py` tasks 1→2 run **sequentially**,
same file; tasks 3/4/5 touch different files → parallel-safe):
1. **Generalize `_run_validation_fix_loop`** (`engine.py`) — `agent_id` + baseline + `user_instruction`
   params; regression ∪ hard-render-break selection; build path byte-identical (empty baseline). Unit
   test: build mode unchanged; revision mode fixes a regression + a render-break, ignores a pre-existing
   static nit.
2. **Post-revision validation + parent seeding** (`engine.py`) — add `parent_run_id` to `execute()`;
   for `prototype_revision`: baseline the seeded original, seed parent `spec.md`/`design.md`/`tasks.md`
   (graceful degrade), then run the generalized fix-loop (`agent_id="prototype-revision-agent"` +
   instruction) before reading back `prototype.html`.
3. **Thread `parent_run_id` through the WS** (`websocket.py`) — pass it into `engine.execute(…)`.
4. **Frontend** (`DashboardLayout.tsx`) — `handleRevisePrototype` passes
   `{ source_workflow_run_id: currentWorkflowRunId }` as `extraParams` when a completed parent exists.
5. **Revision agent prompt** (`prototype-revision-agent/AGENT.md`) — note `spec.md`/`design.md` are
   readable for the original requirements + design system; reinforce the post-edit self-check.
6. **Verify gate** — durable offline test (`test_phase5_revision_validation.py`): scripted
   `prototype_revision` end-to-end (original carries a pre-existing static nit; the agent introduces a
   render-break/regression) → the fix-loop fixes the regression + render-break, LEAVES the pre-existing
   nit, deliverable = validated HTML; parent seeding from a fake parent sandbox populates
   `spec.md`/`design.md`; degrade-gracefully with no parent; WS event vocabulary unchanged.
7. **Independent read-only audit** — a fresh agent verifies the diff matches the tasks + locked
   decisions + invariants (UI unchanged, no dual-path, exact scope), greps for regressions, runs the
   tests. Must be GREEN before commit.

- **UI**: unchanged — validation/fix is internal (non-yielding); seeding is server-side; the only
  client delta is sending an already-accepted field. Event vocabulary identical.
- **Discovered, OUT OF SCOPE:** `_handle_revision` (`engine.py:1682`, the `run_revision` path used by
  **PPT** revision) is a non-agentic stub ("In a full implementation, this would run a DeepAgent
  revision loop" — it stores the instruction as the artifact and runs no agent), so PPT "revision"
  currently emits a placeholder artifact. PPT isn't a prototype/deepagents concern → flagged for a
  separate fix, not Phase 5 (added to §9).

### Phase 6 — Registry reconciliation + per-agent HITL gate toggle ✅ (commit `01c183f`)

**Landed.** Reconciled the two diverged agent registries to a single source of truth (engine
`agents.registry` + loader) and added the per-agent HITL gate toggle. `loader.py`: optional
`description` (role fallback). `agents/registry.py`: `get_all_agents_flat`/`get_agent_by_id`/
`allowed_custom_agent_ids` (+ `od_prototype`/`od_ppt`/`od_ppt_revision` handling). `app/api/agents.py`
+ `websocket.py` repointed to the real registry; `AgentResponse` exposes `gate`+`description`. Frontend
`AgentLibraryData.ts` regenerated to real ids + `gate` (`AgentDef.gate` added). `ReviewGatesSection.tsx`
(inline expandable; pre-checks `gate==="Human_Gate"`; `touched` flag) placed in `IdeaInputPage` **and**
the prototype/ppt templates wizard; `gate_agent_ids` rides the existing `extraParams`/`context` channel
(untouched ⇒ omit ⇒ backend static default **byte-identical**; touched ⇒ explicit array, incl. `[]` = no
gates). **Fixed two latent bugs**: (1) custom-selected prototype runs no longer validate+load the retired
`prototype_v1` agents (now the real spec-kit ids); (2) `allowed_custom_agent_ids("od_ppt")` was ∅ →
non-empty. **Independently audited GREEN** — engine ↔ API ↔ validation ↔ frontend agree; agreeing
pipelines (`user_stories`/`app_builder`/revisions) byte-identical; exact scope (legacy
`app/agents/registry.py` untouched); no Phase-6-caused test failures. Tests: 90 backend
(`test_registry_helpers` + `test_agents_api_real_registry` + `test_phase6_frontend_consistency`) + 19
frontend (`ReviewGatesSection.test.tsx`). **Pending → Phase 7**: delete legacy `app/agents/registry.py`
+ rewrite `test_run_pipeline_validation.py`; migrate the frontend to a live `/api/agents` fetch.
**Noted (pre-existing, report-only)**: `get_pipeline_agents("ppt")==[]` (the od-ppt AGENT.md declare
`pipeline_type: od_ppt`) — harmless here (frontend uses the static regenerated data, never fetches the
`ppt` endpoint); matters only for the future live-fetch migration (pinned by a characterization test).

Re-scoped after a prep finding: a gate toggle needs the **real** per-pipeline agents + gate, but the
`/api/agents` endpoint, the `agent_ids` validation, and the frontend `LIBRARY_AGENTS` all read the
**legacy `app.agents.registry`**, which has **diverged** from the engine's `agents.registry` for
**`prototype`** and **`ppt`** (only those two; `user_stories`/`app_builder`/all revisions agree). So
Phase 6 = **6a reconcile the registries** (single source of truth = the engine's `agents.registry` +
loader, with `gate` exposed) **then 6b the gate toggle** on top. **User decision (2026-06-04): reconcile
first.**

**Two latent bugs the reconciliation fixes** (found during prep): (1) a **custom-selected** prototype
run sends the stale frontend ids → they pass the stale `allowed_custom_agent_ids` → the engine then
`load_agent_spec`s the **retired `prototype_v1` agents** (`requirements-analyst`/…) and runs the WRONG
pipeline (a *default* prototype run is fine — empty `agent_ids` → real registry). (2)
`allowed_custom_agent_ids("od_ppt")` returns `∅` → any `od_ppt` run that supplies `agent_ids` is rejected.

**Grounded facts (reconciliation survey):**
- **Blast radius = 2 production files**: `app/api/agents.py` (imports `get_pipeline_agents`/
  `get_all_agents_flat`/`get_agent_by_id`) + `websocket.py:979` (`allowed_custom_agent_ids`). Everything
  else already uses the real registry.
- **One field gap**: the real loader `AgentSpec` has `id/name/role/pipeline_type/order/icon/
  estimated_duration/tools/gate` but **no `description`** (it has `prompt_body`); `AgentResponse` + the
  frontend `AgentDef` need `description`.
- Real registry lacks `get_all_agents_flat`/`get_agent_by_id`/`allowed_custom_agent_ids` (build against
  `PIPELINE_AGENTS` + the loader). **`CUSTOM_AGENTS` are loader-backed** (real `"custom"` pipeline) —
  nothing legacy-only to preserve.
- Only **`prototype`** (real: `specify/plan/build/validate`) and **`ppt`** (real:
  `od-ppt-brief-analyst/composer/validator`) diverge. `od_` resolution lives in `websocket.py`
  (`od_prototype→prototype`; `od_ppt` stays), not the registries.

**Locked decisions (Q&A 2026-06-04):**
- **Reconcile first**, then toggle.
- **`description`**: add an **optional** `description` to the loader `AgentSpec` (frontmatter) with a
  **fallback to `role`** when absent — **no mass backfill** of the ~27 AGENT.md files now.
- **Repoint, don't delete**: the 2 consumers import the rebuilt helpers from the real `agents.registry`;
  the legacy `app.agents.registry` file is left in place (now dead for listing/validation) for **Phase 7**
  to delete. (`tests/unit/test_run_pipeline_validation.py` still imports legacy symbols → keeps passing but
  now covers dead code; the verify task adds coverage for the real validation.)
- **Frontend fold-in = regenerate the static `AgentLibraryData.ts`** (not fetch): rewrite it to the real
  registry (prototype/ppt ids + names/roles/icons/`gate` from the real AGENT.md frontmatter; fix
  `PIPELINE_CATEGORIES` counts ppt 4→3, all 55→54). Fixes all 4 consumers + the custom-prototype bug at
  once; stays static (future live-fetch migration noted → Phase 7/later).
- **Gate toggle (earlier round)**: **all pipelines**; **all agents listed, default-gated pre-checked**;
  **inline expandable "Review gates" section** beside Skills/Hooks.

**Gate mechanism (grounded):**
- `_should_gate` (`engine.py:1781`): `gate_agent_ids is not None` → gate iff `spec.id ∈ set`; else the
  static `gate: Human_Gate` set (real default = `prototype-specify`/`prototype-plan`).
- `gate_agent_ids` rides the **existing** `extraParams`/`context` channel (Phase 5's
  `source_workflow_run_id` path): `onStartPipeline(…,extraParams)` → `startPipeline(…,context)` →
  `Object.assign(payload,context)` (`useWorkflow.ts`) — bypasses the `if length>0` guards, so `[]` is sent
  verbatim. **Untouched ⇒ omit** (backend `None` → static default, byte-identical); **touched ⇒ send the
  explicit array (even `[]` = no gates)**; a `touched` flag distinguishes them.
- The regenerated `LIBRARY_AGENTS` now carries real ids + `gate`, so the toggle reads the **same** static
  data as the agent-selector (consistent; no separate fetch). For prototype/ppt the submit UI is the
  **templates flow** — the section goes wherever Skills/Hooks already render in each pipeline's submit step.

**Tasks** (one Opus-4.8 max-effort sub-agent each; 6a before 6b):
*6a — reconciliation:*
1. **Loader `description`** (`backend/agents/loader.py`) — optional frontmatter `description` on
   `AgentSpec`, fallback to `role` (or first prompt line) when absent. + test.
2. **Real-registry helpers** (`backend/agents/registry.py`) — add `get_all_agents_flat()`,
   `get_agent_by_id()` (loader-guarded → `None` on miss), `allowed_custom_agent_ids()` (legacy
   branch-semantics, sourced from `PIPELINE_AGENTS` + `custom`; **add `od_ppt`/`od_ppt_revision`/
   `od_prototype`** → fixes bug 2). + tests incl. allow-list parity vs legacy for the agreeing pipelines.
3. **Repoint consumers + expose gate/description** (`backend/app/api/agents.py` + `app/api/websocket.py`)
   — import the helpers from `agents.registry`; add `gate` + `description` to `AgentResponse`;
   `websocket.py` imports the real `allowed_custom_agent_ids`. + endpoint test (real prototype ids; gate
   values; `od_ppt` allow-list non-empty).
4. **Regenerate `AgentLibraryData.ts`** (`frontend/.../AgentLibraryData.ts` + `AgentDef` in
   `types/index.ts`) — real prototype/ppt ids + metadata + `gate?`; fix `PIPELINE_CATEGORIES` counts.
   (Fixes the custom-prototype bug + the selector staleness across all 4 consumers.)
*6b — gate toggle:*
5. **"Review gates" section** — inline expandable (Tailwind, `ReviewGatePanel` palette); reads the
   now-real agents+gate; checkbox per agent, pre-checked iff `gate==="Human_Gate"`; selection + `touched`.
   Placed beside Skills/Hooks in each submit UI (incl. the prototype/ppt templates step).
6. **Wire `gate_agent_ids`** into `run_pipeline` via `extraParams`/`context` (the `IdeaInputPage` path +
   the `od_prototype`/`od_ppt` template paths); untouched-omit / touched-send-even-empty.
*gates:*
7. **Verify gate** — backend pytest (helper/validation parity + `od_ppt` fix + endpoint gate/description);
   frontend typecheck/lint + a JS unit test (untouched ⇒ omit; toggling ⇒ real ids; `[]` ⇒ no gates;
   regenerated data matches the real registry).
8. **Independent read-only audit** — reconciliation correctness (engine + API + validation + frontend all
   agree; both latent bugs fixed; agreeing pipelines unchanged); gate additive-only; exact file scope; run
   all tests; flag regressions.

- **UI**: enhanced. The agent-selector now shows the **real** agents (a bug fix — prototype/ppt names
  change); the gate section is new + additive (untouched ⇒ wire byte-identical). No agent-selection
  *behavior* removed.
- **Out of scope → Phase 7**: delete the legacy `app.agents.registry` + rewrite
  `test_run_pipeline_validation.py`; migrate the frontend from static `AgentLibraryData.ts` to live
  `/api/agents` fetch (noted).

### Phase 7 — Excise legacy + migrate the chat subsystem ✅ (7a `424765e` · 7b `e973cf0`)

**7a LANDED (`424765e`, net −6,091 lines).** Excised the genuinely-dead pipeline-legacy +
migrated title-gen off `DeepAgent`: deleted `create_agent`/`_build_tools` (+ max_iterations map) from
`factory.py`, `summarizer.py`, `tools/workspace.py`, `tools/prototype.py`, `prototype/tools.py`,
`prototype/artifact_store.py`, the legacy `app/agents/registry.py`, `PROTOTYPE_AGENTS_V1` + the 4
`prototype_v1` AGENT.md folders; title-gen (chat + run) now uses `build_model().ainvoke`; rewrote the
legacy tests (incl. **inlining the sandbox byte-oracle** + repointing the phase3/4/5 tests to a new
`_scripted_model.py`); refreshed `CLAUDE.md`. **Independently audited GREEN** — grep-zero for the dead
symbols, live stack imports, full suite identical to baseline (no new reds), byte-oracle + title-gen
events/persistence preserved. `DeepAgent`/`BaseAgent`/`AgentOrchestrator` deliberately KEPT for 7b.

**7b LANDED (`e973cf0`).** Free-chat (`user_message`) migrated off the legacy `AgentOrchestrator` +
7 `BaseAgent` agents + `DeepAgent` onto **`ChatRunner`** (the `create_runner` stack): 7 `chat-*`
AGENT.md specs (text-only) under a new `"chat"` pipeline_type; ported `_parse_output_selection`/
`_determine_active_phases`/`_compile_final_output` verbatim; emits the `phase_start`/`stream`/`phase_end`/
`complete{10-key FinalOutputModel}` contract **byte-for-byte** (a FROZEN golden characterization test
now asserts `ChatRunner` == the captured legacy stream). `websocket.py` repointed (persistence + events
unchanged); `TokenUsage` relocated `base.py`→`types.py`; deleted `orchestrator.py` + the 7 chat agents +
`deep_agent.py` + `test_base_agent.py`; `test_no_baseagent.py` widened to the whole tree.
**Independently audited GREEN** — golden drives a real `ChatRunner`; helpers byte-identical to the
git-history orchestrator; grep-zero on code tokens; suite 493 passed (only pre-existing env reds).

> **⚠️ Zero-legacy is NOT fully reached — `BaseAgent`/`base.py` survives.** A prep-missed **second** live
> consumer was found: the **`/flowin-handoff` IDE-to-PR subsystem** (`app/agents/handoff/{classifier,
> coding_agent,test_agent,compliance_agent}.py`, wired via `app/main.py`) subclasses/uses `BaseAgent`.
> Deleting `base.py` would break `import app.main`, so it was KEPT; `test_no_baseagent.py` **exempts
> exactly** `base.py` + `handoff/` (documented + self-guarded). Chat + pipeline runtimes ARE zero-legacy;
> true zero-`BaseAgent` needs a **separate handoff migration** (a new live-subsystem migration, like the
> chat one was) — **OPEN decision (§9): migrate handoff now, or defer.**

Re-scoped after two prep audits found the original "delete it all" framing **wrong**: **`DeepAgent` and
`BaseAgent` are LIVE** — the migration only ever swapped the *pipeline* runtime. `DeepAgent` powers title
generation; `AgentOrchestrator` + 7 `BaseAgent` chat agents power the **free-chat `user_message`** path (a
full multi-phase generator: Discovery → Requirements → UserStories/PPT/Prototype/UIDesign → Preview).
**User decision (2026-06-04): true zero-legacy** — excise the genuinely-dead pipeline-legacy AND migrate
the chat subsystem onto the new stack, then delete `DeepAgent`/`BaseAgent`/`AgentOrchestrator`. Two parts:
**7a** excise dead pipeline-legacy + migrate title-gen (well-mapped; clears the known reds); **7b** migrate
the chat orchestrator (a live-subsystem migration — the biggest single piece in the whole effort).

**Corrected DEAD vs LIVE (prep audits):**
- **Genuinely dead** (engine uses `create_runner`; nothing live touches): `factory.create_agent`+`_build_tools`
  (+ their inline `max_iterations` map), `summarizer.py` (zero importers), `app/agents/tools/workspace.py`
  (`AgentWorkspace`/`make_workspace_tools`), `app/agents/tools/prototype.py` (shim), `agents/prototype/tools.py`
  (`emit_artifact`/`read_template_seed`/…), `agents/prototype/artifact_store.py` (`PrototypeArtifactStore`),
  `PROTOTYPE_AGENTS_V1` + the 4 retired `prototype_v1` AGENT.md folders, the legacy `app/agents/registry.py`
  (only 3 tests import it post-Phase-6), `astream_with_usage` (only the parity test calls it).
- **LIVE until 7b migrates them** (do NOT pre-delete): `DeepAgent` (`deep_agent.py` — title-gen),
  `BaseAgent`/`base.py` + `AgentOrchestrator`/`orchestrator.py` + the 7 chat agents + `app/agents/__init__.py`
  (free-chat); and **`TokenUsage`** (in `base.py`, **used by the live `DeepAgentRunner`** — relocate, don't delete).
- `orchestrator_v2.py`/`od_runner.py` don't exist (stale `CLAUDE.md` prose only).

**🔑 Biggest traps:** (1) `test_sandbox_deliverable.py` uses dead `AgentWorkspace.to_final_output()` as the
**byte-oracle for the LIVE `serialize_sandbox_deliverable`** — inline the expected bytes before deleting
`workspace.py`. (2) **The chat WS event contract** must be reproduced byte-for-byte — `phase_start{phase,name}`
/ `stream{chunk,section}` / `phase_end{phase}` / `error` / trailing `complete{10-key FinalOutputModel}` +
side-channel `title_update`, the `{type,chunk,section,data}` shape, the per-`section` routing
(discovery/requirements/user_stories/ppt/prototype/ui_design/ui_preview) — any drift sends messages into the
FE *pipeline* handler and silently breaks the chat bubble. (3) `TokenUsage` relocation. (4) The 5 chat **modes**
+ the runtime **output-selection** (`_parse_output_selection` of the discovery prose) have **zero tests** —
characterize first.

**Locked decisions (2026-06-04):**
- **True zero-legacy** (migrate chat, don't keep it).
- **Dedicated chat sequencer (`ChatRunner`)**, NOT the `ExecutionEngine` (it can't model the chat's runtime
  multi-output selection or its distinct event vocabulary). It reuses `create_runner` (text-only) for the 7
  agents but keeps the legacy sequencing + `_parse_output_selection`/`_determine_active_phases`/
  `_compile_final_output` + event emission **verbatim**.
- **7 chat agents → `tools:[]` AGENT.md specs** under a NEW `"chat"` pipeline_type (added to
  `SUPPORTED_PIPELINE_TYPES`), bodies = the inline prompts verbatim.
- **Keep the chat `prototype`/`ppt` phases as independent single-agent prompts** (their JSON/text output is
  what the chat FE expects) — do NOT cross-wire to the real prototype/ppt pipelines (would change the FE
  artifact type → violates the UI invariant). Note the redundancy for a future product call.
- **Relocate `TokenUsage`** out of `base.py` to a live module before deleting `base.py`.
- **Title-gen** → direct `build_model().ainvoke` one-shot (both sites); then `DeepAgent` is deletable.
- **Chat persistence unchanged**: keep writing `Message` rows + `ChatSession.final_output` (NOT `WorkflowRun`).
- **Repoint, then delete**: land green, then delete the legacy files; grep-assert zero refs; widen
  `test_no_baseagent.py` to the whole tree.

**Tasks** (Opus-4.8 agents; 7a before 7b; EACH part ends with verify + independent audit + commit):

*7a — excision + title-gen (dead importers removed before the code):*
1. **Migrate title-gen** off `DeepAgent` (chat-title `websocket.py:~742` + run-title `~218`) → `build_model().ainvoke` one-shot; keep `title_update`/`workflow_title_update` events identical.
2. **Tests first** — delete `test_factory.py`; rewrite `test_guardrails.py` → `_compose_system_prompt`; rewrite `test_run_pipeline_validation.py` → real `agents.registry`/`loader`; trim legacy-import lines from `test_agents_api_real_registry.py` + `test_registry_helpers.py`; rewrite `test_revision_file_editing.py` (drop the `AgentWorkspace` block) and **`test_sandbox_deliverable.py` (inline the byte-oracle)**; delete `_parity_driver.py` + `test_deep_agent_runner_parity.py`.
3. **Delete dead factory entry points** — `create_agent` + `_build_tools` (+ `max_iterations` map) from `factory.py` (keep the live `create_runner`/`AgentContext`/`_compose_system_prompt`/`_build_runner_tools`).
4. **Delete dead modules** (order: `summarizer.py` → `tools/workspace.py`, `tools/prototype.py`, `prototype/tools.py` → `prototype/artifact_store.py`); trim `agents/prototype/__init__.py` docstrings.
5. **Delete dead config/folders** — `PROTOTYPE_AGENTS_V1` (`prototype/pipeline.py`); the 4 `prototype_v1` AGENT.md folders; `"prototype_v1"` from `loader.py`.
6. **Refresh `backend/CLAUDE.md`** to the post-migration architecture; purge `orchestrator_v2`/`create_agent`/`emit_artifact` from stale docstrings.
7. **7a verify** (grep-zero for the dead symbols; full suite green — the legacy reds disappear; sandbox byte-oracle preserved) → **independent audit → commit.**

*7b — chat migration:*
8. **Characterization test** — capture the legacy `AgentOrchestrator.astream_execute` event sequence (mocked LLM): per-phase `phase_start`/`stream`/`phase_end`, the runtime `_parse_output_selection`, the trailing `complete{10-key}`, the 5 modes. Locks the contract before cutover.
9. **7 chat AGENT.md specs** under `"chat"` (add to `SUPPORTED_PIPELINE_TYPES`): `chat-discovery`/`chat-requirements`/`chat-user-stories`/`chat-ppt`/`chat-prototype`/`chat-ui-design`/`chat-preview` — bodies = the inline prompts verbatim.
10. **`ChatRunner` sequencer** — `create_runner` per agent (text-only); reproduce `_parse_output_selection`/`_determine_active_phases`/`_compile_final_output` verbatim; thread context (flatten prior outputs into the message); prepend `mode_prompt`; emit the legacy events; relocate `TokenUsage`; reconcile the `AgentConfigurationError` catch.
11. **Repoint `websocket.py`** `user_message` handler → `ChatRunner` (keep the `Message`/`ChatSession.final_output` persistence block as-is).
12. **Delete the legacy chat stack** — `orchestrator.py`, the 7 chat agents, `base.py` (after `TokenUsage` moved), `deep_agent.py` (now unused), `modes.py` if folded in; clean `app/agents/__init__.py`; widen `test_no_baseagent.py`; grep-assert zero `BaseAgent`/`DeepAgent`/`AgentOrchestrator`.
13. **7b verify** (characterization test passes against `ChatRunner` — event-parity old↔new; modes + output-selection + persistence covered; full suite + grep-zero green) → **independent audit → commit.**

- **UI**: unchanged — 7a is dead-code removal; 7b reproduces the chat WS event contract byte-for-byte (the FE chat handler is untouched), enforced by the characterization/event-parity test.
- **Scale note**: the largest phase — 7b alone is comparable to the pipeline migration; runs as **two commit-pairs** (7a, then 7b).

### Phase 7c — Handoff migration (the last `BaseAgent`) ✅ (commit `92bd531`)

**LANDED.** The 4 `/flowin-handoff` agents migrated off `BaseAgent` → `build_model().ainvoke` (prompts/
config/`BEDROCK_CODING_MODEL_ID` override/JSON-extract/`setdefault`/classifier-fallback byte-preserved;
public API unchanged so `handoff_pipeline.py`/`handoff_github.py`/REST/WS are untouched); **`base.py`
DELETED** (zero importers; `TokenUsage` already in `types.py`); `test_no_baseagent.py` widened to the
whole tree with **NO exemptions** (+ a base.py-stays-deleted guard). New: `test_handoff_contract.py` (a
FROZEN golden driving the REAL `run_handoff_pipeline` — WS event contract + `pipeline_output`, coding +
test modes) + `test_handoff_agents.py`. **Independently audited GREEN** — agents byte-faithful, pipeline
0-diff, golden drives real code, `import app.main` OK, **zero `BaseAgent`/`DeepAgent`/`AgentOrchestrator`
code tokens tree-wide**; suite 583 passed (only pre-existing env reds). **🎉 True zero-legacy reached.**

Completes true zero-legacy: migrate the `/flowin-handoff` IDE→PR subsystem off `BaseAgent`, then delete
`base.py`. **Survey finding: this is small** — all 4 handoff agents (`classifier`, `coding_agent`,
`test_agent`, `compliance_agent`) are **pure-text, one-shot (`.run()` only), no tools, no streaming**;
they use `BaseAgent` ONLY for LLM construction (= `build_model`) + `.run()` (= `ainvoke`). The
orchestration `app/services/handoff_pipeline.py` (a hand-written async generator: clone→classify→code→
`_apply_edits`→test→comply→commit→push→PR) is **healthy and owns the WS event contract + git
side-effects** — it must stay verbatim. The agents return **text JSON plans**; the *pipeline* applies
edits via a validated traversal-guarded `_apply_edits` trust boundary — do NOT give agents fs tools.

**Locked design (from the survey):**
- **Rewrite only the 4 `app/agents/handoff/*.py`** to use `build_model(model=…, max_tokens=…).ainvoke([SystemMessage, HumanMessage])` + `_extract_text` instead of `BaseAgent`. NO new runner/sequencer class; `handoff_pipeline.py`/`handoff_github.py`/`handoff.py`/`websocket_handoff.py` are **untouched**. Preserve exactly: `coding_agent`'s `BEDROCK_CODING_MODEL_ID` override + `max_tokens=16000`; `classifier`'s `max_tokens=8` + fallback-to-`"coding"`; each agent's JSON-extract + `setdefault` defaults. `AgentConfigurationError`→`ModelConfigurationError` (same role).
- **`base.py`→new-stack gap = NONE** (`build_model` = identical Bedrock/Anthropic construction + retries; `ainvoke` = `.run`; `TokenUsage` already in `types.py`; `estimate_cost_usd`/`AgentConfigurationError` have zero other consumers → die with the file).
- **Characterize first** (the biggest risk — ZERO pipeline test coverage today; the one `/start` test stubs the pipeline out): freeze the pipeline's WS event contract (≈20 events + `agent_error`/`handoff_error`, the `{type,chunk,section,data}` shape, the per-`section` values, the `agent_complete` report shapes) **+ the `pipeline_output` shape** (the FE refresh-hydration path depends on it) for `mode="coding"` (full path incl. PR) AND `mode="test"` (no PR), mocking the 4 agents + `handoff_github`. Model on `test_chat_contract.py`.
- After migration: **delete `base.py`**; remove the `test_no_baseagent.py` exemptions for `base.py`+`handoff/` + its `test_exemptions_are_genuinely_live`; grep-assert zero `BaseAgent` tree-wide.

**Tasks** (Opus-4.8 agents; characterize + rewrite in parallel — different files):
1. **Characterization golden** — `run_handoff_pipeline` event-contract + `pipeline_output` frozen test (coding + test modes; mocked agents + mocked `handoff_github`). Locks the FE contract.
2. **Rewrite the 4 handoff agents** → `build_model().ainvoke` (drop `BaseAgent`); preserve prompts/config/overrides/JSON-parsing/fallbacks verbatim. + agent-level tests (scripted model → correct JSON, the coding model-override, the classifier fallback).
3. **Delete `base.py`** + remove the `test_no_baseagent` exemptions (+ the now-false `test_exemptions_are_genuinely_live`); grep-assert zero `BaseAgent`/`AgentConfigurationError`/`estimate_cost_usd` tree-wide; confirm `import app.main`.
4. **Verify gate** — the golden passes against the migrated agents; agent-level tests pass; widened `test_no_baseagent` (no exemptions) green; full suite + grep-zero; `import app.main` OK.
5. **Independent read-only audit.**

- **UI**: unchanged — the WS/REST handoff contract is reproduced (characterization-gated); only the agents' internal LLM-call mechanism changes.

### Phase 8 — Verify (live Bedrock Haiku, local) ⏳ PLANNED (2026-06-05)

**Goal:** prove the migrated runtime works end-to-end against the **real** model (not scripted) across
**every** pipeline, with a **committed, repeatable harness** — then run it live. All prior verification is
offline (scripted models + real validators); this closes the live gap before deploy (Phase 9).

**Locked decisions (Q&A 2026-06-05):**
- **Model = AWS Bedrock Haiku 4.5 via the DEFAULT profile** (NOT `personal-sso`). `build_model()` →
  `ChatBedrockConverse` `eu.anthropic.claude-haiku-4-5-20251001-v1:0` (eu-central-1) when
  `ANTHROPIC_API_KEY` is empty. Opt-in via `RUN_LIVE_BEDROCK=1` + the existing STS preflight
  (`test_deep_agent_runner_hitl_live.py`). **Verified feasible now:** the default profile resolves
  (`ImranY@hexaware.com`, acct `473293451041`, SSO-backed, currently valid) and Bedrock Haiku 4.5 is
  accessible in eu-central-1.
- **Scope = ALL pipelines** — the 6 headline (`prototype` build+revision, `app_builder`, `user_stories`,
  `ppt`/od_ppt, free-`chat`, `/flowin-handoff`) + the rest of the registered set the harness can drive
  with a synthetic brief (repo-input code-gen pipelines get a minimal fixture or are flagged in the playbook).
- **Resume-after-kill = NOW, with local Postgres** (docker — native pg absent; docker IS running;
  `langgraph-checkpoint-postgres`+`psycopg`+`psycopg_pool` installed). True cross-process crash recovery.
- **Structure = automated committed harness**, proven offline first (scripted model → **zero Bedrock
  cost**), then flipped live.

**Grounded facts (Phase-8 survey):**
- **No headless runner exists** — but `tests/agents/_scripted_model.py::_drive(pipeline_type)` already
  drives the REAL `engine.execute()` (`engine.py:292`; `get_pipeline_agents(pipeline_type)` →
  `engine.execute(agents=…, pipeline_type=…, gate_agent_ids=…, od_context=…)`) by patching `ctx.model`.
  The live harness = `_drive` **with the model patch removed** (let `create_runner`→`build_model()` build
  real Bedrock) + the real planner.
- **Three drive worlds** (not all go through the engine): engine pipelines via `engine.execute()`;
  **free-chat** via `ChatRunner.astream_execute()`; **handoff** via `run_handoff_pipeline()` (real agents +
  **mocked `handoff_github`** + a temp local git repo — never hit real GitHub). Chat/handoff already have
  offline goldens (`test_chat_contract.py` / `test_handoff_contract.py`) to extend.
- **Live text is nondeterministic** → assertions are **content-agnostic**: event types/ordering/required
  keys, non-zero token usage, and **deliverable validity** (prototype.html passes `static_check`+
  `render_check`; code-gen has `filename:` blocks; chat has the 10-key `FinalOutputModel`; handoff has the
  `pipeline_output` shape) — NOT exact text.
- **Cost watch** — accumulate the runner's `usage` events; Haiku pricing already encoded ($0.25/M in,
  $1.25/M out, `websocket.py:1207`).
- **Resume** — same `pipeline_run_id` → same per-agent `thread_id=f"{run}:{spec.id}"`; Postgres
  `AsyncPostgresSaver.setup()` persists state across a process kill.
- **Planner nuance** — engine pipelines run the real planner live with `ALWAYS_CLARIFY=False` +
  PROCEED-friendly briefs; if it clarifies, the harness auto-proceeds (no WS round-trip needed).

**Build / run split:** the BUILD tasks (harness, validators, tests, playbook) are agent-built and
**offline-proven with the scripted model → zero live cost**, committed green. The LIVE RUN (flip
`RUN_LIVE_BEDROCK=1`) is executed separately — the verify gate runs **one cheap live smoke** + the resume
test; the full all-pipelines sweep is run from the playbook (cost reported).

**Tasks** (Opus-4.8 agents; T1 first — foundation; then T2/T4/T5 parallel; T3 after T2; T6→T7 gates):
1. **Harness core** (`backend/tests/agents/live_harness.py`, NEW) — a generic driver for the 3 worlds
   (engine/chat/handoff): builds the REAL model via `build_model()` (default-profile Bedrock Haiku), runs
   the real planner (`ALWAYS_CLARIFY` off), captures the ordered event stream, accumulates per-agent +
   cumulative tokens, controls gates (on/off), carries the `RUN_LIVE_BEDROCK` guard + STS preflight.
   **Offline self-test** drives it with `ScriptedFakeChatModel` (zero Bedrock) to prove the machinery.
2. **Contract validator + cost watcher** (`backend/tests/agents/live_contract.py`, NEW) — content-agnostic
   per-world assertions (event vocab/order/keys, non-zero tokens, deliverable validity) + a token/cost
   summary printer with a soft ceiling. Built on T1's capture format.
3. **Per-pipeline live suite + HITL on/off** (`backend/tests/agents/test_phase8_live.py`, NEW,
   `RUN_LIVE_BEDROCK`-gated) — one live case per pipeline (prototype build+revision, app_builder,
   user_stories, ppt, chat, handoff) wiring T1+T2; plus gate-on (pause → `Command(resume)` → complete) vs
   gates-off scenarios. Mocks only side-effects (handoff git/GitHub, artifact-store DB), **never the model**.
4. **Cross-process resume-after-kill** (`backend/tests/agents/test_phase8_resume.py` + a subprocess runner,
   NEW) — spin up docker Postgres, `DATABASE_URL`→it, run a pipeline to a gate in a child process, **kill
   it**, start a fresh process, resume from the checkpoint (same run_id), assert completion + state continuity.
5. **Live-verify playbook** (`specs/002-deepagents-migration/PHASE8_VERIFY.md`, NEW) — exact env + commands
   (default profile, `RUN_LIVE_BEDROCK=1`, the Bedrock id), per-pipeline invocations, expected outputs, the
   docker-Postgres resume recipe, cost guidance, SSO-refresh troubleshooting.
6. **Verify gate** — full offline suite green (harness self-tests + validators, scripted model, no creds) +
   **one cheap live smoke** (a single prototype run against real Bedrock, cost reported) + the resume test
   against docker Postgres.
7. **Independent read-only audit** — confirm the live path uses the REAL stack (no scripted model leaks into
   the live path), assertions are meaningful + content-agnostic, **no production code changed** (verify-only:
   harness/tests/docs only), resume is genuinely cross-process, playbook commands are accurate. GREEN before commit.

- **UI**: unchanged — Phase 8 adds **no production code** (harness + tests + a playbook doc only); it
  verifies the existing contract, doesn't alter it.
- **Out of scope:** the full all-pipelines live sweep cost (run from the playbook); deploy (Phase 9);
  code-gen per-task sub-agents (Phase 10).

### Phase 9 — Deploy ⏳
Ship the Chromium/sandbox image; deploy the branch; monitor token/compute. Rollback =
redeploy previous image / revert the merge.

### Phase 10 — Roll out per-task sub-agents to code-gen pipelines ⏳ (follow-on)
After prototype is proven: extend the sub-agent-per-task model to `app_builder`,
`mulesoft_to_springboot`, `dotnet_to_azure` (+ their revisions). Per-task validation for
code = build/lint in the sandbox.

## 6. New dependencies & infra

- `deepagents==0.6.7`, `langgraph-checkpoint-postgres==3.1.0`, `playwright==1.60.0`
  (langchain trio bumped to satisfy the 0.6.7 floor).
- Playwright Chromium bundled in the backend image (`/opt/playwright`, ~+350 MB).
- Persistent runs volume: `/opt/flowin/data/runs` (EBS) → `/app/runs` (container).
- LangGraph checkpoint tables in Postgres (managed by `AsyncPostgresSaver.setup()`).

## 7. Risks & mitigations

- **Cost/latency** (uncapped iters × per-task sub-agents × validate-fix loops × headless
  render) → `recursion_limit=400` backstop, bounded validate retries, cost telemetry,
  optional stronger-executor model later.
- **Sandbox security** (real disk + `execute`) → per-user/run confinement (traversal-proof
  `path_for`), TTL cleanup, dropped privileges / no-network execute.
- **Stream parity** (the "visuals identical" promise) → event-parity tests in Phase 1/8.
- **Chromium in container** (image size, resources) → pinned headless build, per-render
  timeout, graceful skip if the browser is unavailable.
- **Migration breadth** → prototype-first contains the blast radius (Phase 4/10 split).

## 8. Rollout & rollback

No runtime feature flag (per the no-legacy invariant). The branch is the new world; it is
not deployed until green. Rollback = don't merge / revert the merge / redeploy the prior
image tag. The Phase 0 deps install upgrades the shared local env, so the legacy `:8000`
dev server is expected to be unhappy until Phase 1+ lands — that's accepted.

## 9. Open items & deferred (carried-forward)

**Resolved:**
- [x] #15 live Bedrock invoke + HITL pause/resume on 0.6.7 — verified 2026-06-03 (Haiku, eu-central-1).
- [x] Phase-1 risks: interrupt detection (post-loop `aget_state`) + text-only tool exclusion (per-graph `_ToolFilterMiddleware`) — covered by tests.
- [x] Engine HITL bridge — Phase 3 added per-run gate-selection via the existing `_run_review_gate` (the runner's tool-level `gate` stays dormant — see levers below).
- [x] **Frontend per-agent HITL toggle UI** — DONE Phase 6 (`01c183f`): inline "Review gates" section (IdeaInputPage + the prototype/ppt templates wizard).
- [x] **Frontend `LIBRARY_AGENTS` staleness** — DONE Phase 6: regenerated to the real registry (real prototype/ppt ids + `gate`). (A live `/api/agents` fetch instead of static data remains an optional nicety — see levers.)
- [x] **Excise legacy / dead code** — DONE Phase 7a/7b/7c: `deep_agent.py`/`DeepAgent`, `base.py`/`BaseAgent`, `orchestrator.py`/the 7 chat agents, `summarizer.py`, `AgentWorkspace`/`PrototypeArtifactStore`/`emit_artifact`, `create_agent`/`_build_tools`, the legacy `app/agents/registry.py`, `prototype_v1` — all deleted; grep-zero tree-wide. **🎉 true zero-legacy.**
- [x] **7 `test_factory.py` reds** — DONE 7a: `test_factory.py` deleted (the `create_agent`/`_build_tools` it tested are gone); the chat `test_base_agent.py` reds also gone (7b).
- [x] **`backend/CLAUDE.md` stale** — DONE 7a-3: refreshed to the live deepagents architecture.

**Deferred to a specific later stage** (a fresh session must NOT assume these are done):
- **Push the ~16 queued commits** — as soon as GitLab auth works (VPN off / refresh GCM token): `git push origin HEAD`.
- **Live Bedrock end-to-end runs** (prototype / app_builder / user_stories / prototype_revision) → **Phase 8**. All verification so far is offline (scripted models + real validators). Needs `aws sso login --profile personal-sso` (SSO keeps expiring between sessions).
- **Cross-process checkpoint resume-after-kill** → **Phase 8**. In-process graph-level resume is proven; true crash-recovery needs Postgres (dev falls back to `InMemorySaver`).
- **Per-task sub-agents for code-gen** (`app_builder` / `mulesoft_to_springboot` / `dotnet_to_azure` + revisions; validation = build/lint in the sandbox) → **Phase 10** (after the prototype model is proven).
- **PPT revision is a non-agentic stub** (discovered during Phase 5 planning): the `run_revision` WS path → `_handle_revision` (`engine.py:1682`) stores the instruction text as the new artifact and runs **no agent** ("In a full implementation, this would run a DeepAgent revision loop"). So a PPT revision via the Phase-3-preferred `run_revision` path yields a placeholder, not a revised deck (the legacy `run_pipeline(ppt_revision)` fallback still runs the real agent when no completed run id exists). NOT a prototype/deepagents concern → **separate fix, out of Phase 5**.
- **Frontend live `/api/agents` fetch** (optional nicety — the `LIBRARY_AGENTS` staleness itself is RESOLVED, Phase 6): post-Phase-6 the gate section + agent-selector read the regenerated static `AgentLibraryData.ts` (correct real ids + `gate`). Migrating to a live `GET /api/agents/pipelines/{type}` fetch (single source of truth, no future static drift) is optional — not scheduled.
- **✅ RESOLVED (Phase 7c `92bd531`) — `/flowin-handoff` was the last live `BaseAgent` user** (discovered Phase 7b-5): the IDE-to-PR handoff subsystem (`app/agents/handoff/{classifier,coding_agent,test_agent,compliance_agent}.py`, wired via `app/main.py` → `app.api.handoff`/`websocket_handoff` → `app.services.handoff_pipeline`) subclasses/uses `BaseAgent`, so `base.py` could NOT be deleted in Phase 7 (`test_no_baseagent.py` exempts `base.py` + `handoff/`, self-guarded). To reach **true zero-`BaseAgent`/zero-legacy**, the handoff subsystem must be migrated onto the new stack (`create_runner`/`build_model`) — a fresh live-subsystem migration (its own design + agents + verification, like the chat one). **Decide: migrate handoff (new phase) now, or defer + accept `BaseAgent`-for-handoff.**

**Still-open design levers** (no stage committed):
- [ ] Tool-level HITL approvals — the runner CAN emit a tool-level `gate` (built + tested in Phase 1, dormant; inter-agent gating is engine-level). Decide if/when to surface tool approvals.
- [ ] Stronger model for executor sub-agents — deferred; executors use the run-selected model (Haiku default). Revisit if per-page prototype quality needs it.

## 10. Decision log

- 2026-06-03 — Library `deepagents` chosen over the custom runtime; engine-driven hybrid.
- 2026-06-03 — Pinned 0.6.7 (over 0.5.6) for DeltaChannel checkpoints; accepted the
  langchain-core/langgraph bump (resolver-verified).
- 2026-06-03 — Real-disk sandbox on persistent EBS (over ephemeral/in-state); Playwright
  in-image (over sidecar); install into global env (option A, no venv).
- 2026-06-03 — Phase 0 landed (`bfd573b`).
- 2026-06-03 — #15 live-verified: deepagents 0.6.7 Bedrock streaming + tool loop + HITL pause/resume all OK.
- 2026-06-03 — Phase 1 landed — `DeepAgentRunner` adapter; parity test green; live HITL pause/resume proven on Bedrock Haiku.
- 2026-06-03 — Tool exclusion via a per-graph `_ToolFilterMiddleware` (public `AgentMiddleware`/`ModelRequest.override` API) chosen over `HarnessProfile.excluded_tools` — the profile route is a global `provider:model`-keyed registry that can't express the per-agent text-only distinction and silently no-ops on a wrong key. `subagents=None` alone does NOT drop `task` (create_deep_agent auto-adds a general-purpose subagent that re-injects it).
- 2026-06-03 — Built-in model-visible tool set verified (deepagents 0.6.7): `{write_todos, ls, read_file, write_file, edit_file, glob, grep, task}`; `execute` is created by FilesystemMiddleware but self-stripped unless the backend is a `SandboxBackendProtocol`. `exclude_builtin_tools=True, tools=[]` → 0 model-visible tools (pure text).
- 2026-06-03 — HITL `gate` event payload = `{action_requests, review_configs, interrupt_ids, next}`; interrupt detected post-loop via `aget_state` (interrupts at `state.interrupts` / `state.tasks[*].interrupts`, `Interrupt.value` = the HITLRequest). Resume via `Command(resume={"decisions":[{"type":"approve"}]})` (one Decision per pending action_request).
- 2026-06-03 — `on_tool_end` extracts `ToolMessage.content` (not `str(ToolMessage)`) so the UI `tool_result` text is byte-identical to legacy — honors the UI-identical invariant (found by the parity gate).
- 2026-06-03 — Phase 2 re-scoped to **additive prep** (build `create_runner` + disk tool-sets, verified in isolation, wired nowhere); the inseparable factory+engine **cutover** moves entirely to Phase 3. Rationale: `create_agent` is shared by all pipelines, the engine's `use_deep` `isinstance` gate + the no-dual-path invariant forbid a bridge, and AGENT.md prompt bodies are shared with the live path — so the breaking change can't be additive and must land atomically. Keeps every commit green (Phase-1 discipline).
- 2026-06-03 — Native `deepagents` tools replace the custom file tools: `FilesystemBackend` (`write_file`/`read_file`/`edit_file`/`ls`/`glob`/`grep`) replaces `AgentWorkspace`/`make_workspace_tools`; agent writes `prototype.html` via native `write_file` (replaces `emit_artifact`); native `write_todos` replaces `todo_write`. Survivors: `report_task_complete` (store-free, progress via tool events) and `PLANNING_TOOLS` (unchanged). Template-read tools **dropped** — content is already pre-injected into the system prompt.
- 2026-06-04 — Phase 3 scope = **FULL** (user choice over the minimal-cutover recommendation): the all-pipelines runtime flip PLUS per-run HITL gate-selection, Postgres checkpointing + resume, and cross-agent summarizer removal — all in one cutover. Baked-in findings: (a) the cross-agent summarizer is **dead** — `_agent_summaries` is written (`engine.py:900-902`) but never read; downstream context already uses the full `accumulated_outputs`, so removal is behavior-neutral and drops a wasted per-agent LLM call; (b) the sandbox is **per-pipeline-run** (shared, so `prototype.html`/code files persist across agents) while the checkpoint `thread_id` is **per-agent-invocation** (unique); (c) the inter-agent gate stays engine-level (`_run_review_gate`) — Phase 3 adds per-run *selection* of which agents gate (toggle UI in Phase 6); (d) only 4 prototype AGENT.md files reference `emit_artifact`/template tools.
- 2026-06-04 — Phase 3 landed (`030820b`) — atomic cutover; offline old-vs-new WS event-parity GREEN (22 event types identical); verify gate caught + fixed a per-task `task_progress` count regression (made cumulative/run-level). Live runs + cross-process resume deferred to Phase 8.
- 2026-06-04 — Phase 4 decisions (Q&A): context = **Both** (inject current task + write `spec.md`/`design.md` to the sandbox); validation = **Both, every task** (static_check + render_check; feasible because the planner builds the full shell — all sections + nav — in Task 1); fix-loop = **re-invoke the same sub-agent, bounded N=2, INTERNAL** (a non-yielding coroutine → no UI events); executor model = **run-selected (Haiku default)**; engine writes the spec/design/tasks files (no specify/plan prompt change).
- 2026-06-04 — Phase 4 landed (`218582d`) — per-task sub-agents + Both-validation; audited GREEN (event vocabulary identical, exact 6-file scope). `static_check.py` (stdlib) added. Live E2E deferred to Phase 8.
- 2026-06-04 — Phase 5 planned (decisions Q&A). Scope = `prototype_revision` ONLY — "chaining via files" is already realized (Phase 3/4: engine writes spec/design/tasks; build reads them; the revision agent already has native ls/grep/read). (a) **Validation = smart hybrid**: after the revision edits prototype.html, auto-fix regressions (NEW static/render issues vs. a baseline computed on the seeded original) ∪ hard render-breakage regardless of baseline (page errors, dead nav, blank render — "html won't display proper content"), while ignoring pre-existing static nits / benign pre-existing console noise; the fix prompt re-injects the user's instruction; bounded N=2, never blocks. (b) **Seed parent spec/design**: frontend sends `source_workflow_run_id` (existing field) → backend threads `parent_run_id` into `execute()` → reads spec.md/design.md/tasks.md from the **parent run's sandbox** (`RunSandbox(user_id, parent_run_id)`; no new persistence — the build wrote them, sandboxes survive to the 48h TTL) → seeds the revision sandbox; graceful degrade if absent. (c) `_run_validation_fix_loop` generalized (`agent_id` + baseline + user_instruction; **empty baseline = build path byte-identical**). UI unchanged (fix is internal/non-yielding; only an already-accepted WS field is added). Grounded refs: seed/slim `engine.py:279-289`, read-back `546-563`, fix-loop `1292`, `_write_build_reference_files` `1219`, parent_run_id resolution `websocket.py:1016-1023`, frontend `handleRevisePrototype` `DashboardLayout.tsx:426` + `extraParams` forward `dashboard/page.tsx:884-896`. Discovered out-of-scope: `_handle_revision` (PPT `run_revision`) is a non-agentic stub (§9).
- 2026-06-04 — Phase 5 landed (`8819f40`). Generalized `_run_validation_fix_loop` (build **byte-identical**, proven exhaustively over 108 selection cases) + `execute(parent_run_id)` parent spec/design/tasks seeding (graceful degrade) + post-revision **smart-hybrid** fix-loop (regressions vs. a pre-edit baseline ∪ hard render-breakage; ignore pre-existing nits; re-inject user instruction; bounded N=2; internal/non-yielding; never blocks). Executed as 7 tasks via Opus-4.8 agents (2 sequential `engine.py`, 3 parallel: `websocket.py`/`DashboardLayout.tsx`/`AGENT.md`, verify-gate test, independent read-only audit). **Audited GREEN** — exact 6-file scope, all locked decisions + invariants verified at file:line, no new WS event types / no phantom 2nd agent. Tests: `test_phase5_fixloop_selection.py` (17) + `test_phase5_revision_validation.py` (8); full agent net 83 passed. Live Bedrock E2E → Phase 8.
- 2026-06-04 — Phase 6 planned (decisions Q&A): scope = **ALL pipelines**; granularity = **all agents listed, default-gated pre-checked**; UI = **inline expandable "Review gates" section** (beside Skills/Hooks). Forced design: source the agent list + gate status from the backend `GET /api/agents/pipelines/{type}` endpoint (add an additive `gate` field) — NOT the stale `LIBRARY_AGENTS` (a front/back drift: prototype shows `requirements-analyst`/… vs. the real `prototype-specify`/`plan`/`build`/`validate`; emitting wrong ids in a non-null `gate_agent_ids` would DISABLE the real default gates). `gate_agent_ids` rides the EXISTING `extraParams`/`context` channel (no new plumbing); untouched ⇒ omit (backend static default), touched ⇒ send the explicit array (even `[]` = no gates). Grounded refs: `_should_gate` `engine.py:1781`, gate frontmatter `prototype-specify`/`prototype-plan`, endpoint `app/api/agents.py:83-112`, payload merge `useWorkflow.ts`, submit UI `IdeaInputPage.tsx`, gate palette `ReviewGatePanel.tsx`. Discovered: stale `LIBRARY_AGENTS` is a pre-existing bug (§9).
- 2026-06-04 — Phase 6 **re-scoped** (deeper finding supersedes the prior entry's "fetch from endpoint" premise): the `/api/agents` endpoint AND `allowed_custom_agent_ids` validation read the **legacy `app.agents.registry`**, which has diverged from the engine's `agents.registry` for **prototype + ppt only** (user_stories/app_builder/all revisions agree) — so the endpoint is *also* stale, not just `LIBRARY_AGENTS`. Two latent bugs found: (1) custom-selected prototype runs `load_agent_spec` the **retired `prototype_v1`** agents (wrong pipeline); (2) `allowed_custom_agent_ids("od_ppt")` = ∅ rejects od_ppt custom runs. **User chose: reconcile registries first, then the toggle.** Phase 6 = **6a** (loader optional `description` w/ role fallback; build `get_all_agents_flat`/`get_agent_by_id`/`allowed_custom_agent_ids` on the REAL registry + od_ handling; repoint `app/api/agents.py` + `websocket.py:979` to the real registry; add `gate`+`description` to `AgentResponse`; **regenerate** `AgentLibraryData.ts` → real ids/metadata/gate + fix category counts) + **6b** (inline "Review gates" section + `gate_agent_ids` wiring via the existing extraParams/context channel). Legacy `app.agents.registry` left for **Phase 7** deletion (a test still imports it). Survey: real `AgentSpec` lacks only `description` (`loader.py:64-98`); just **2** prod consumers of the legacy registry; `CUSTOM_AGENTS` are loader-backed.
- 2026-06-04 — Phase 6 landed (`01c183f`). 6a reconciliation (loader optional `description`; real-registry `get_all_agents_flat`/`get_agent_by_id`/`allowed_custom_agent_ids` + od_ handling; repoint `app/api/agents.py` + `websocket.py`; `AgentResponse` gets `gate`+`description`; regenerate `AgentLibraryData.ts`) + 6b gate toggle (`ReviewGatesSection` in `IdeaInputPage` + the prototype/ppt templates wizard; `gate_agent_ids` via the existing extraParams/context channel; untouched ⇒ omit, byte-identical). Executed as T1–T5b + verify-gate + independent audit via Opus-4.8 agents. **Audited GREEN** — engine ↔ API ↔ validation ↔ frontend agree; agreeing pipelines byte-identical (real-vs-legacy parity table); **2 latent bugs fixed** (custom-prototype runs now use the real spec-kit agents, not retired `prototype_v1`; `od_ppt` allow-list non-empty); exact scope (legacy `app/agents/registry.py` untouched). Tests: 90 backend + 19 frontend; no Phase-6-caused failures (the 25+9 backend / 7 frontend reds are pre-existing legacy/env/SSO). Scope grew mid-flight by user choice: added the **wizard gate UI** (T5b) so prototype/ppt gates are customizable (not just IdeaInputPage). Deferred → Phase 7: delete legacy registry + rewrite `test_run_pipeline_validation.py`; live `/api/agents` fetch. Report-only: `get_pipeline_agents("ppt")==[]` (od-ppt frontmatter) — harmless (static frontend data).
- 2026-06-04 — Phase 7 planned (re-scoped via 2 prep audits). **Key correction:** the original "delete DeepAgent + BaseAgent" was WRONG — both are LIVE (`DeepAgent` = title-gen `websocket.py:218/742`; `AgentOrchestrator` + 7 `BaseAgent` agents = the free-chat `user_message` multi-phase generator `orchestrator.py:293`, Discovery→Requirements→UserStories/PPT/Prototype/UIDesign→Preview). The pipeline migration never touched free-chat. **User chose TRUE zero-legacy.** **7a** excise the genuinely-dead pipeline-legacy (`create_agent`/`_build_tools` + max_iterations map, `summarizer.py`, `workspace.py`/`tools/prototype.py`/`prototype/tools.py`/`artifact_store.py`, `PROTOTYPE_AGENTS_V1` + 4 `prototype_v1` folders, legacy `app/agents/registry.py`, `astream_with_usage`) + migrate title-gen → `build_model`; **7b** migrate the chat subsystem to a dedicated **`ChatRunner`** (`create_runner` text-only per agent + 7 `"chat"` AGENT.md specs; reproduce `_parse_output_selection`/`_determine_active_phases`/`_compile_final_output` + the `phase_start`/`stream`/`phase_end`/`complete` WS event contract VERBATIM; relocate `TokenUsage` out of `base.py`; preserve the 5 modes + `Message`/`ChatSession` persistence), then delete `orchestrator.py`/`base.py`/`deep_agent.py`/the 7 chat agents. **Decisions:** dedicated sequencer (NOT the engine — it can't model the chat's runtime multi-output selection / distinct events); keep chat prototype/ppt as independent prompts (their JSON/text is what the FE expects — no cross-wire); repoint-then-delete + grep-zero + widen `test_no_baseagent.py`. **Traps:** `test_sandbox_deliverable` uses dead `AgentWorkspace.to_final_output()` as the byte-oracle for the LIVE `serialize_sandbox_deliverable` (inline before deleting); chat event-contract drift → FE *pipeline* handler; **zero existing chat tests** (characterize first). Largest phase — runs as two commit-pairs.
- 2026-06-04 — Phase 7 landed (7a `424765e`, 7b `e973cf0`). 7a excised the dead pipeline-legacy (`create_agent`/`_build_tools`, `summarizer.py`, `workspace.py`/prototype-tools/`artifact_store.py`, the legacy `app/agents/registry.py`, `prototype_v1`; net −6,091) + moved title-gen → `build_model`. 7b migrated free-chat → **`ChatRunner`** (7 `chat-*` specs + ported sequencing; byte-for-byte event contract via a frozen golden) + deleted `orchestrator.py`/the 7 chat agents/`deep_agent.py`/`test_base_agent.py`; `TokenUsage` → `types.py`. Both audited GREEN; suite 493 passed (only pre-existing env reds: logout/cancel). **Key discovery (7b-5):** a SECOND live `BaseAgent` consumer — the **`/flowin-handoff`** subsystem (`app/agents/handoff/*` via `app/main.py`) — so `base.py` was KEPT (deleting it breaks `import app.main`); `test_no_baseagent.py` widened with self-guarded exemptions for `base.py` + `handoff/`. Chat + pipeline runtimes are zero-legacy; **true zero-`BaseAgent` needs a handoff migration (§9 open).**
- 2026-06-05 — Phase 7c landed (`92bd531`) — **🎉 true zero-legacy reached.** Migrated the 4 `/flowin-handoff` agents (the last live `BaseAgent` users) off `BaseAgent` → `build_model().ainvoke` (survey found them pure-text/one-shot/no-tools — a small migration; prompts/config/`BEDROCK_CODING_MODEL_ID` override/JSON-extract/`setdefault`/classifier-fallback byte-preserved; public API unchanged so `handoff_pipeline.py`/`handoff_github.py`/REST/WS untouched), then **deleted `base.py`**. Characterized first (frozen golden over the real `run_handoff_pipeline` — WS contract + `pipeline_output`, coding + test modes; mocks agents at the pipeline boundary + `handoff_github`). `test_no_baseagent.py` widened tree-wide, no exemptions. Audited GREEN — zero `BaseAgent`/`DeepAgent`/`AgentOrchestrator` code tokens tree-wide; `import app.main` OK; suite 583 passed (only pre-existing env reds: logout/handoff_api self-registration-disabled, cancel timing). 5 tasks via Opus-4.8 agents (characterize ∥ rewrite → delete → verify → audit).
- 2026-06-05 — Phase 8 planned (decisions Q&A): model = **Bedrock Haiku 4.5 via the AWS default profile** (NOT personal-sso; verified resolving now — `ImranY@hexaware.com`/acct 473293451041 — + Bedrock Haiku 4.5 access confirmed in eu-central-1); scope = **ALL pipelines**; resume-after-kill = **now, via docker Postgres** (native pg absent, docker running, langgraph-postgres+psycopg installed); structure = **committed automated harness** (offline-proven with the scripted model → zero live cost, then flipped live via `RUN_LIVE_BEDROCK=1`). Grounded: `_scripted_model._drive` already drives the REAL `engine.execute()` (`engine.py:292`) by patching `ctx.model` → the live harness is `_drive` MINUS the model patch + the real planner (`ALWAYS_CLARIFY=False`); **3 drive worlds** (engine `execute()` / `ChatRunner.astream_execute` / `run_handoff_pipeline` with mocked `handoff_github` + temp git repo); **content-agnostic assertions** (event types/order/keys + non-zero tokens + deliverable validity: static_check+render_check / `filename:` blocks / 10-key FinalOutputModel / pipeline_output), NOT exact text; cost via `usage` events (Haiku $0.25/$1.25 per M). 7 tasks: T1 harness core → (T2 validator ∥ T4 resume-after-kill ∥ T5 playbook) → T3 per-pipeline live suite + HITL on/off → T6 verify gate (offline green + 1 cheap live smoke + docker-pg resume) → T7 independent audit. **Verify-only — no production code touched** (harness/tests/`PHASE8_VERIFY.md` only).

## 11. Code map — what exists now (post Phase 7)

> **Added since Phase 4:** `chat_runner.py` (`ChatRunner` — free-chat on `create_runner`) + 7 `chat-*`
> AGENT.md specs (the `"chat"` pipeline); the `/flowin-handoff` agents now on `build_model().ainvoke`
> (`app/agents/handoff/*`); `TokenUsage` moved to `app/agents/types.py`. **Deleted (Phase 7 — true
> zero-legacy):** `deep_agent.py`/`base.py`/`orchestrator.py`/the 7 chat agents/`summarizer.py`/
> `tools/workspace.py`/`tools/prototype.py`/`prototype/{tools,artifact_store}.py`/the legacy
> `app/agents/registry.py`/`create_agent`+`_build_tools`/`prototype_v1`. No `BaseAgent`/`DeepAgent`/
> `AgentOrchestrator` remain.

**New runtime modules** (`backend/app/agents/`):
- `deep_agent_runner.py` — `DeepAgentRunner`: wraps a `create_deep_agent` graph; `astream_events`
  (chunk/usage/tool_call/tool_result/done/gate/error), `astream_with_usage`, `astream`, `run`,
  `model_id`/`tools`. Tool exclusion via a per-graph `_ToolFilterMiddleware`; `exclude_builtin_tools`
  → pure text. Disk `FilesystemBackend(virtual_mode=True)` rooted at the run sandbox; HITL `gate`
  via post-loop `aget_state`; `on_tool_end` extracts `ToolMessage.content`.
- `model_factory.py` — `build_model(model, max_tokens)` (Bedrock/Anthropic select + botocore retries).
- `sandbox.py` — `RunSandbox(user_id, run_id)` (per-user/run dir, traversal-proof, TTL sweep) +
  `serialize_sandbox_deliverable(root)` / `count_sandbox_deliverables(root)` (byte-match `to_final_output`).
- `checkpointer.py` — `get_checkpointer()` (AsyncPostgresSaver singleton / InMemory dev) + `close_checkpointer()`.
- `render_check.py` — `async render_check(path)` (headless Chromium: console errors + nav assertions; graceful skip).
- `static_check.py` — `static_check(html|path)` (stdlib: routes↔sections / routes-map / handlers / is-active).
- `tools/runner_tools.py` — store-free `report_task_complete` (+ `make_runner_prototype_tools`).

**Factory** (`backend/agents/factory.py`):
- `create_runner(agent_id, ctx, *, checkpointer=None, interrupt_on=None, thread_id=None)` — the LIVE
  path (reuses `_compose_system_prompt`; builds the per-run `RunSandbox`; constructs `DeepAgentRunner`).
- `_build_runner_tools(spec, ctx) -> (tools, exclude_builtin)` — maps tool-sets onto native tools.
- `AgentContext.run_id`. (`create_agent`/`_build_tools` were DELETED in Phase 7a — `create_runner` is the only entry point.)

**Engine** (`backend/agents/execution_engine/engine.py`):
- `execute()` — per-run `RunSandbox` + `await get_checkpointer()`; `gate_agent_ids` param; sets `ctx.run_id=pipeline_run_id`.
- `_run_agent` — single `astream_events` loop (no `use_deep`/`astream_with_usage`); `create_runner` with a
  unique per-agent `thread_id`; `task_progress` from `report_task_complete` events (cumulative `self._completed_tasks`);
  reads the deliverable from the sandbox; `_should_gate(spec)`.
- `_run_build_task_loop` (prototype) — `_write_build_reference_files` (spec.md/design.md/tasks.md) +
  `_extract_task_block` + `=== CURRENT TASK ===` injection (via `_build_context_message`) +
  `_run_validation_fix_loop` (static+render, bounded N=2 INTERNAL fix — a non-yielding coroutine).

**Tests**: `test_deep_agent_runner_hitl_live.py` (opt-in, SSO), `test_create_runner.py`,
`test_sandbox_deliverable.py` (inlined byte-oracle), `test_phase3_cutover_verify.py`, `test_static_check.py`,
`test_phase4_build_loop.py`, `test_phase5_*`, `test_registry_helpers.py`, `unit/test_agents_api_real_registry.py`,
`unit/test_chat_contract.py` + `unit/test_chat_runner.py` (chat golden), `integration/test_handoff_contract.py`
+ `unit/test_handoff_agents.py` (handoff golden), `unit/test_no_baseagent.py` (whole-tree, NO exemptions). The
reusable scripted `BaseChatModel` is `tests/agents/_scripted_model.py` (was `_parity_driver.py`). Known
pre-existing reds (NOT migration-caused): env-gated `test_logout`/`test_handoff_api` (self-registration disabled)
+ `test_pipeline_cancel` (timing). [`test_factory.py`/`test_deep_agent_runner_parity.py`/`test_base_agent.py`
were deleted in Phase 7.]

**Deps** (`backend/requirements.txt`): `deepagents==0.6.7`, `langgraph-checkpoint-postgres==3.1.0`,
`playwright==1.60.0`; langchain 1.3.4 / langchain-core 1.4.0 / langgraph 1.2.4. Backend image bundles
Chromium; `/app/runs` on the EBS data volume.

## 12. Working method (how phases are executed)

Each phase: **lock decisions via Q&A → break into tasks → one Opus-4.8 max-effort sub-agent per task**
(each handed the full plan + grounding + its task; tasks sharing a file run sequentially, independent
files in parallel). Every phase ends with a **verify gate** (a durable committed test) + an
**independent read-only audit** agent (must be GREEN before commit). Git stays with the orchestrator:
a `feat(agents)` code commit + a `docs(agents)` plan commit referencing the code SHA (the
`<pending>`→SHA two-commit pattern).

**Facts a fresh session needs:**
- **Dev runtime**: homebrew `python3.11`, NO venv; tests via `python3.11 -m pytest`; `ruff` is on PATH.
- **Scripted-model test recipe**: the stock LangChain fakes do NOT drive the deepagents loop (they raise
  on `bind_tools` and drop `tool_calls`/`usage_metadata`). Use a minimal `BaseChatModel` whose `_stream`
  yields real `AIMessageChunk`s with `tool_call_chunks` + `usage_metadata`, and a no-op `bind_tools`.
  Inject it into the engine by passing the INSTANCE as `model_id` (→ `ctx.model` → `create_runner`).
- **Tests + `RUNS_ROOT`**: `settings.RUNS_ROOT` defaults to `/app/runs` (not writable locally) —
  monkeypatch it to a temp dir before `create_runner`. Stub the artifact-store DB write (no `workflow_runs`
  row in tests).
- **`render_check` Chromium IS available locally** (renders for real); degrades to a skip if absent.
- **`write_file` won't overwrite** (deepagents `FilesystemBackend`) — prototype Task 1 uses `write_file`,
  tasks 2+ and ALL fixes use `edit_file`. The prototype-build prompt + the fix-loop message enforce this.
- **Contract characterization** (the chat/handoff migrations): freeze the live event contract as a GOLDEN
  (`unit/test_chat_contract.py`, `integration/test_handoff_contract.py`) — a scripted model + mocked
  side-effects drive the REAL runner/pipeline, and the migrated impl must reproduce the golden byte-for-byte.
  The old worktree-at-HEAD parity harness was retired in Phase 7a; the reusable scripted `BaseChatModel`
  survives as `tests/agents/_scripted_model.py`.
