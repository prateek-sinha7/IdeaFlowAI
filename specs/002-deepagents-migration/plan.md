# 002 — DeepAgents Migration Plan

> Swap the custom hand-rolled agent runtime for the **LangChain `deepagents`**
> library across all pipelines, engine-driven, with the frontend visuals
> unchanged. Living document — update phase status + the decision log as work lands.

| | |
|---|---|
| **Branch** | `deepagents-full-swap` (off `0e9c410`) |
| **Status** | Phase 0 ✅ complete (commit `bfd573b`) · Phases 1–10 planned |
| **Created** | 2026-06-03 |
| **Supersedes** | the custom `app/agents/deep_agent.py` ReAct loop (deleted in Phase 7) |

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

### Phase 1 — `DeepAgentRunner` adapter + stream mapping 🔜
The heart of the swap. Wrap `create_deep_agent`; expose the engine's existing contract
(`astream_events` yielding our event dicts, `run()`, `model_id`, `tools`). Map LangGraph
events → ours (`on_chat_model_stream→chunk`, `…end.usage_metadata→usage`,
`on_tool_start→tool_call`, `on_tool_end→tool_result` incl. the
`tool=='report_task_complete'→task_progress` sentinel, graph end→`done`,
`__interrupt__→gate`). Disable library sub-agents (`task`); enable disk filesystem +
summarization; attach checkpointer.
- **Verify gate**: event-parity test vs the current runtime for a scripted tool sequence
  (must match before proceeding).
- **UI**: unchanged (parity-gated).

### Phase 2 — Factory + tools on disk ⏳
`factory.create_agent` → `DeepAgentRunner` (composed `system_prompt` + tools +
`build_model(ctx.model)`); high `recursion_limit`; embed retries. Tools target the disk
sandbox; keep `report_task_complete` (progress); `emit_artifact` → writes `prototype.html`.
Retire `AgentWorkspace`/`PrototypeArtifactStore` usage (cross-agent handoff via files).
- **UI**: unchanged.

### Phase 3 — Engine dispatch + per-agent HITL + checkpointing ⏳
Switch the engine to the runner directly (retire the `use_deep`/`astream_with_usage`
split). Per-agent HITL: read per-run gate selections; pause after gated agents via
checkpointer + `Command(resume)`; emit the **same** `review_gate_*` events; default =
currently-gated agents pre-checked. Remove summarizer calls; token totals from adapter.
- **UI**: unchanged (identical gate/usage events).

### Phase 4 — Prototype: per-task sub-agent execute + Both validation ⏳
Planner writes `tasks`/`spec`/`design` files to the run dir. Engine execute loop launches
ONE isolated sub-agent per task, forced to read task + spec + design before editing
`prototype.html`; validate = static checks **+** sandbox headless render (`render_check`),
bounded fix-loop. Same `task_loop_progress`/`task_progress` events.
- **UI**: unchanged (same progress events; richer build underneath).

### Phase 5 — Revision on disk + chaining ⏳
Revision seeds `prototype.html` into the run dir; the revision sub-agent reads spec +
edits + runs the same validation. Cross-agent chaining via files the next agent reads;
agents may `ls/grep/read` to explore.
- **UI**: unchanged.

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

## 9. Open items

- [x] #15 live Bedrock invoke + HITL pause/resume on 0.6.7 — ✅ verified 2026-06-03 (Haiku, eu-central-1).
- [ ] Confirm whether HITL should also support tool-level approvals (currently inter-agent only).
- [ ] Decide stronger-model-for-executor-sub-agents (deferred; Haiku for now).

## 10. Decision log

- 2026-06-03 — Library `deepagents` chosen over the custom runtime; engine-driven hybrid.
- 2026-06-03 — Pinned 0.6.7 (over 0.5.6) for DeltaChannel checkpoints; accepted the
  langchain-core/langgraph bump (resolver-verified).
- 2026-06-03 — Real-disk sandbox on persistent EBS (over ephemeral/in-state); Playwright
  in-image (over sidecar); install into global env (option A, no venv).
- 2026-06-03 — Phase 0 landed (`bfd573b`).
- 2026-06-03 — #15 live-verified: deepagents 0.6.7 Bedrock streaming + tool loop + HITL pause/resume all OK.
