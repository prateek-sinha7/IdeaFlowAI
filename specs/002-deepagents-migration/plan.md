# 002 — DeepAgents Migration Plan

> Swap the custom hand-rolled agent runtime for the **LangChain `deepagents`**
> library across all pipelines, engine-driven, with the frontend visuals
> unchanged. Living document — update phase status + the decision log as work lands.

| | |
|---|---|
| **Branch** | `deepagents-full-swap` (off `0e9c410`) |
| **Status** | Phases 0–5 ✅ complete (Phase 0 `bfd573b` · Phase 1 `666e531` · Phase 2 `0d09702` · Phase 3 `030820b` · Phase 4 `218582d` · Phase 5 `8819f40`) · Phases 6–10 planned |
| **Created** | 2026-06-03 |
| **Supersedes** | the custom `app/agents/deep_agent.py` ReAct loop (deleted in Phase 7) |

---

## Current state — START HERE (resume point)

**As of 2026-06-04.** Phases **0–5 complete & committed locally** on `deepagents-full-swap`;
**Phase 6 (frontend additive HITL toggle) is next**. The deepagents runtime is **live across all
pipelines** (Phase 3); the prototype build runs the **per-task sub-agent + Both-validation** model
(Phase 4); and **prototype revision** now runs the same validation + seeds the parent run's
spec/design (Phase 5). The WebSocket/UI event contract is **byte-identical to pre-migration**
(audited GREEN each phase).

**What works now:** every pipeline agent runs as a `DeepAgentRunner` (a deepagents
`create_deep_agent` graph) built by `create_runner`, driven by the engine through ONE
`astream_events` loop; deliverables are read from a per-run disk **sandbox** (`prototype.html` /
code-gen `filename:` blocks); per-run HITL gate-selection (default = static `Human_Gate`);
Postgres/InMemory checkpointer with per-agent threads; prototype build = one isolated sub-agent per
task (reads `spec.md`/`design.md` + an injected `=== CURRENT TASK ===` block) with per-task
static+render validation and a bounded **internal** fix-loop.

**⚠️ Unpushed:** the branch is **7 commits ahead of `origin`** — `030820b`,`017c241` (Phase 3) +
`218582d`,`9349328` (Phase 4) + `171160c` (resume-doc) + `8819f40` (Phase 5 feat) + this Phase 5 docs commit. **Push is blocked on GitLab auth** (git-credential-manager hangs /
`HTTP Basic: Access denied`; earlier-session pushes worked, so the credential lapsed — likely
GlobalProtect VPN must be **off**, or refresh the GCM token). `git push origin HEAD` ships all 4
once auth is fixed. **Commits are local — nothing is lost.**

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

### Phase 6 — Frontend: additive HITL toggle ⏳
Add a per-agent check/uncheck HITL control at submit (pre-checked = today's gated agents),
styled to the design system. Nothing existing changed or removed.
- **UI**: enhanced (additive only) — verified no existing component/behavior changed.

### Phase 7 — Excise legacy (explicit, no shims) ⏳
**Delete** the hand-rolled `DeepAgent` loop, `summarizer.py`, `AgentWorkspace`,
`PrototypeArtifactStore`, the per-agent `max_iterations` map, `emit_artifact`, the
`astream_with_usage` path, and any `BaseAgent`-for-execution. Grep-assert zero references
remain. No fallback left in the tree.
- **UI**: unchanged (pure dead-code removal).

### Phase 8 — Verify (Bedrock Haiku, local) ⏳
Prototype end-to-end (plan → per-task sub-agents → validate); HITL on/off; **checkpoint
resume after a kill**; revision; full **WS event-parity capture**; cost watch.

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

**Deferred to a specific later stage** (a fresh session must NOT assume these are done):
- **Push the 4 queued commits** — as soon as GitLab auth works (VPN off / refresh GCM token): `git push origin HEAD`.
- **Live Bedrock end-to-end runs** (prototype / app_builder / user_stories / prototype_revision) → **Phase 8**. All verification so far is offline (scripted models + real validators). Needs `aws sso login --profile personal-sso` (SSO keeps expiring between sessions).
- **Cross-process checkpoint resume-after-kill** → **Phase 8**. In-process graph-level resume is proven; true crash-recovery needs Postgres (dev falls back to `InMemorySaver`).
- **Excise legacy / dead code** → **Phase 7**: `app/agents/deep_agent.py` (`DeepAgent`), `app/agents/summarizer.py`, `AgentWorkspace`, `PrototypeArtifactStore`, `emit_artifact`, the per-agent `max_iterations` map, and `create_agent` + `_build_tools` (all DEAD since the Phase-3 cutover — the engine calls `create_runner`). Grep-assert zero refs after deletion.
- **7 pre-existing `test_factory.py` reds** (`TestCreateAgentToolWiring`/`TestBuildTools` prototype tool-wiring + `TestComposeSystemPrompt` hook composition) → **Phase 7**: they test the now-dead `create_agent`/`_build_tools` path; they fail identically at every commit incl. HEAD (unrelated to the migration). Delete/rewrite with that code.
- **`backend/CLAUDE.md` is stale** (describes the pre-migration architecture: `orchestrator_v2.py`, `deep_agent.py`, `emit_artifact`, old prototype tools) → refresh in **Phase 7**.
- **Frontend per-agent HITL toggle UI** → **Phase 6**: the backend already accepts `gate_agent_ids` (Phase 3); Phase 6 adds the submit-time check/uncheck control (pre-checked = static `Human_Gate` set).
- **Per-task sub-agents for code-gen** (`app_builder` / `mulesoft_to_springboot` / `dotnet_to_azure` + revisions; validation = build/lint in the sandbox) → **Phase 10** (after the prototype model is proven).
- **PPT revision is a non-agentic stub** (discovered during Phase 5 planning): the `run_revision` WS path → `_handle_revision` (`engine.py:1682`) stores the instruction text as the new artifact and runs **no agent** ("In a full implementation, this would run a DeepAgent revision loop"). So a PPT revision via the Phase-3-preferred `run_revision` path yields a placeholder, not a revised deck (the legacy `run_pipeline(ppt_revision)` fallback still runs the real agent when no completed run id exists). NOT a prototype/deepagents concern → **separate fix, out of Phase 5**.

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

## 11. Code map — what exists now (post Phase 4)

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
- `AgentContext.run_id` (additive). `create_agent`/`_build_tools` remain but are DEAD (Phase 7 deletes).

**Engine** (`backend/agents/execution_engine/engine.py`):
- `execute()` — per-run `RunSandbox` + `await get_checkpointer()`; `gate_agent_ids` param; sets `ctx.run_id=pipeline_run_id`.
- `_run_agent` — single `astream_events` loop (no `use_deep`/`astream_with_usage`); `create_runner` with a
  unique per-agent `thread_id`; `task_progress` from `report_task_complete` events (cumulative `self._completed_tasks`);
  reads the deliverable from the sandbox; `_should_gate(spec)`.
- `_run_build_task_loop` (prototype) — `_write_build_reference_files` (spec.md/design.md/tasks.md) +
  `_extract_task_block` + `=== CURRENT TASK ===` injection (via `_build_context_message`) +
  `_run_validation_fix_loop` (static+render, bounded N=2 INTERNAL fix — a non-yielding coroutine).

**Tests** (`backend/tests/agents/`): `test_deep_agent_runner_parity.py`, `test_deep_agent_runner_hitl_live.py`
(opt-in, SSO), `test_create_runner.py`, `test_sandbox_deliverable.py`, `test_phase3_cutover_verify.py`,
`test_static_check.py`, `test_phase4_build_loop.py`, `_parity_driver.py` (old-vs-new harness). Pre-existing
reds: 7 in `test_factory.py` (legacy; Phase 7).

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
  row in tests) and, pre-Phase-7, the summarizer.
- **`render_check` Chromium IS available locally** (renders for real); degrades to a skip if absent.
- **`write_file` won't overwrite** (deepagents `FilesystemBackend`) — prototype Task 1 uses `write_file`,
  tasks 2+ and ALL fixes use `edit_file`. The prototype-build prompt + the fix-loop message enforce this.
- **Old-vs-new parity**: `HEAD` is the pre-cutover engine; `tests/agents/_parity_driver.py` drives BOTH
  the old (worktree at HEAD) and new (working tree) engines with the same scripted model.
