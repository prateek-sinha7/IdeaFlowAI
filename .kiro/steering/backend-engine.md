---
inclusion: fileMatch
fileMatchPattern: "backend/agents/execution_engine/**"
---

# Backend — Execution Engine Domain

> Loaded when editing files under `backend/agents/execution_engine/`. See `invariants.md` for hard constraints that always apply.

---

## Key Files in This Domain

| File | Purpose |
|------|---------|
| `engine.py` | Runtime kernel — the `ExecutionEngine` class |
| `context.py` | `ExecutionContext` dataclass (per-run state) |
| `kernel_services.py` | `KernelServices` — the handle capabilities reach the kernel through |
| `fanout.py` | Single spawn path: `run_fanout`, `_merge_fragments`, budget, cancel |
| `budget.py` | `BudgetManager` / `BudgetSnapshot` / module-level defaults |
| `authz.py` (was here, now `agents/authz.py`) | Moved to `agents/authz.py` in Phase 5 |

---

## ExecutionContext Field Rules

- **Do NOT add** fields for future phases speculatively (INV-12).
- Fields added per-phase: `redo_directive` (P23), `spec_revision_context` / `spec_revision_pending_output` (P27), `steering_notes` (P29), `pending_turn_images` / `turn_images_once` (P30), `resume_completed_task_ids` (P46), `gate_reentry` (P49).
- `current_task_block` was a deliberate Phase-7-temporary home — it lives in `TaskLoopStrategy` now.
- `accumulated_outputs` was **deleted** in Phase 5 (L15 ratchet armed). Do not resurrect it.
- Scratch fields (consume-once, loop-local) must be drained unconditionally every iteration (F3 pattern from Phase 23).

## `_run_agent` While-Loop Contract

- The gate-dispatch loop is a flat `while True:` (not recursive) — Phase 23 locked this.
- On `_gate_redo`: set loop locals (`redo_directive`, `redo_derived_from`), `results.pop()`, `continue`.
- On `_gate_update_specs` (KAN-101): call `_run_spec_revision_sub_pipeline`, set `ectx.spec_revision_pending_output`, `break`.
- Each redo uses a fresh `{run_id}:{agent}:redo{N}` checkpoint thread — do NOT reuse the base thread (LangGraph replays prior turn otherwise).
- `_gate_redo` and `_gate_update_specs` are internal signals — never forwarded to the WS/SSE wire.

## `_apply_selections` Overlay (Phase 22 / Phase 51)

- Called at BOTH the in-plan overlay site and the absent-agent synthesis site.
- Synthesizes `strategy` / `fanout` / `task_source` onto the run-plan step — keyed on `agent_id` (generic, never workflow-name).
- Does NOT overlay `tools` — `run_fanout` does no permission check and `trust="user"` forces `spawn_subagents` OFF regardless.
- `resume_run` does NOT call `_apply_selections` — composed fan-out resume loses the overlay (known open issue, WR-02).

## `_compose_context_message` Injection Order

Each seam appends a block when its backing field is non-empty (all dormant → byte-identical → INV-3 safe):
1. `=== CURRENT PROTOTYPE (skeleton …) ===` — html_skeleton compaction (Phase 3)
2. `=== ADDITIONAL INSTRUCTIONS (REVISE) ===` — `ectx.redo_directive` (Phase 23)
3. `=== SPEC KIT ANALYSIS REPORT (REVISION CONTEXT) ===` — `ectx.spec_revision_context` (Phase 27)
4. `=== USER GUIDANCE ===` — `ectx.steering_notes` consume-once queue (Phase 29)

## Fan-Out Rules (INV-7)

- `run_fanout` is the **single** spawn path — both `fanout_batch` strategy and `spawn_subagents` tool funnel through it.
- Budget defaults are **locked module constants** in `budget.py`: max_subagents=8, max_concurrency=4, max_depth=2, wall_clock=900s.
- `reserve()` must be the **first** call in `run_fanout` (bypass-proof).
- Teardown runs in `finally` for happy + cancel + BudgetExceeded paths (zero residue).
- `spawn_subagents` tool body is spawn-free (no asyncio/run_fanout/kernel import inside the tool).

## Resume Paths (v3.0, Phases 45–51)

- `_first_incomplete_step` completeness is strategy-conditional: `task_loop` needs distinct-`task_id` count ≥ parser-derived total; `single_shot` is byte-unchanged.
- `_resuming = _is_resume` (NOT `_resume_from > 0`) — an offset-0 resume is still a resume (BUG-R05 fix).
- On resume, `workspace_id` is recovered from a durable owner-scoped row — **never re-minted**.
- `_run_spec_revision_sub_pipeline` is position-based (index-2 / index-1 / index), never agent-id literal.
- Resume re-applies `_apply_selections` at offset: `resume_run` does NOT currently call it (open WR-02).

## Milestone Card / Narrator Seam (Phase 43)

- `MilestoneSink` + `LiveEctxRegister` are injected generic callables — no `engine.py → app.*` import.
- The milestone card draws its `seq` from the engine's **own** `itertools.count` (yielded as a first-class event) — do NOT use an out-of-band `append_event_next_seq` write (causes a seq-uniqueness collision, DEF-43-03-1).
- `live_ectx_register` / `unregister` in `run_commands.py:_LIVE_ECTX`, NOT in any WS module.

## Locked Decisions Specific to This Domain

- **D-03 (Phase 2):** explicit `ectx` parameter threading — no `contextvars`/ambient state.
- **`_handle_revision` STAYS** — it is the PPT-revision handler called by REST `/revisions`. The old WS *driver* was deleted in Phase 44; the engine method survives.
- **`od_prototype` alias must be resolved** before any roster lookup — `get_pipeline_agents(resolve_alias(pipeline_type))` (BUG-R01/R02 fix).
- **Milestone-end live-Bedrock pass:** consolidates all LIVE-01 deferrals. Do not mark an item "live-confirmed" without evidence.
