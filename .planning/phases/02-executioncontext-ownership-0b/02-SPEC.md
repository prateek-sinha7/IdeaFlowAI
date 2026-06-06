# Phase 2: ExecutionContext + Ownership [0B] — Specification

**Created:** 2026-06-07
**Ambiguity score:** 0.09 (gate: ≤ 0.20)
**Requirements:** 5 locked

## Goal

Move every per-run `self._*` attribute off the `ExecutionEngine` singleton onto a new per-run `ExecutionContext`, make the kernel immutable/stateless after construction (NFR-001/INV-2), add an explicit cross-owner ownership check on `parent_run` seeding (L16/INV-8), and delete the dead `_handle_revision` (D1) — with **zero behavior change** (deliverables byte-identical, events at semantic parity).

## Background

Grounded in `backend/agents/execution_engine/engine.py` (2643 lines) as of this phase:

- **Per-run state lives on the shared singleton.** `execute()` mutates instance attributes during each run: `self._od_context` (`:474`), `self._user_id` (`:475`), `self._gate_agent_ids` (`:481`), `self._checkpointer` (`:503`), `self._completed_tasks` (`:517`), `self._current_task_block` (`:1536`), `self._revision_original_html/_revision_instruction/_revision_baseline_static/_revision_baseline_console` (`:532–550`), and `self._parent_run_id` (`:486`). This is the **L14** leak (`plan.md` §4/§6) and violates INV-2 — unsafe for concurrency/fan-out.
- **`parent_run` seeding is implicitly owner-keyed.** `engine.py:583–609` seeds from `RunSandbox(user_id or "anon", parent_run_id)` keyed on the same user **implicitly**; there is no explicit check that the caller owns `parent_run`. This is the **L16** leak (`plan.md` §19), an unenforced INV-8 boundary.
- **`_handle_revision` is dead.** The method at `engine.py:2138` (ledger range `:2138–2251`) is superseded by inline revision handling and never reached. This is **D1**.

Phase 1 [0A] already recorded green characterization snapshots (deliverable byte-snapshots + semantic event snapshots, contiguous per-run `seq`) for prototype, od_prototype, prototype_revision, ppt/od_ppt, and one code-gen pipeline. The plan (`specs/003-workflow-engine-decoupling/plan.md`, recorded in `STATE.md` as the authoritative complete spec) fixes the target `ExecutionContext` dataclass shape (§6, lines 329–349) and the migration ledger (`migration-ledger.md`) defines the verbatim deletion gates for L14/L16/D1.

## Requirements

1. **Lift run state to ExecutionContext (CTX-01 / L14 / INV-2)**: All enumerated `self._*` per-run state moves off the singleton onto a per-run `ExecutionContext`.
   - Current: `_od_context`, `_completed_tasks`, `_current_task_block`, `_revision_*`, `_gate_agent_ids`, `_user_id`, `_checkpointer` are mutable attributes on the `ExecutionEngine` singleton (`engine.py:474–550`, `:1536`)
   - Target: a per-run `ExecutionContext` (new `agents/execution_engine/context.py`) carries this run state (`run_id`, `owner_id`, `workspace_id`, plus the migrated fields); `execute()` constructs one per run and threads it through the call tree. (Per plan line 349, strategy-local scratch such as the current task block ultimately belongs to a strategy — but strategies don't exist until Phase 7, so in 0B it moves onto the per-run context, never staying on `self`.)
   - Acceptance: `grep -rnE 'self\._(od_context|completed_tasks|current_task_block|revision_|gate_agent_ids)' backend/` returns **0** (L14 ratchet)

2. **Stateless, immutable kernel (CTX-02 / NFR-001 / INV-2)**: The kernel singleton holds no per-run attributes and is immutable after construction.
   - Current: `execute()` and its callees write per-run attributes (`self._*`, incl. `_user_id`, `_checkpointer`, `_parent_run_id`) onto the shared instance during every run
   - Target: after `__init__`, no run mutates instance attributes; the instance exposes only construction-time config (stores/factories); all run state is on `ExecutionContext`
   - Acceptance: no per-run attribute assignment remains on the singleton within `execute()` and below (NFR-001 verified by review + the L14 grep returning 0, including `_user_id`/`_checkpointer`/`_parent_run_id` relocated to the context)

3. **Explicit parent-run ownership check (CTX-03 / L16 / INV-8)**: `parent_run` seeding performs an explicit ownership check that rejects cross-owner access.
   - Current: `engine.py:583–609` reads `RunSandbox(user_id or "anon", parent_run_id)` keyed on the same user implicitly — no explicit cross-owner rejection
   - Target: an explicit ownership check at the seed/store boundary rejects a `parent_run` owned by a different owner *before* any seeding occurs; the synthetic `anon:<session_id>` principal is a real owner for the check (never `None`)
   - Acceptance: a cross-owner denial test — seeding with a `parent_run_id` owned by a different `owner_id` is rejected (refused/raised, nothing seeded) — passes (L16 CHECK row)

4. **Delete dead `_handle_revision` (CTX-04 / D1)**: The dead `_handle_revision` method is deleted.
   - Current: `_handle_revision` exists at `engine.py:2138` (`:2138–2251`), superseded by inline revision handling, never reached
   - Target: the method is removed entirely
   - Acceptance: `grep -rn '_handle_revision' backend/` returns **0** (D1 ratchet)

5. **No behavior change (CTX-05 / INV-3)**: Deliverable snapshots stay byte-identical and event snapshots stay at semantic parity.
   - Current: Phase 0A characterization snapshots are green for prototype/od_prototype/prototype_revision/ppt/od_ppt/code-gen (deliverable byte-snapshots + semantic event snapshots + contiguous `seq`)
   - Target: after the refactor the same snapshots remain green — deliverables byte-identical, events at semantic parity, per-run `seq` still contiguous
   - Acceptance: the Phase 0A characterization suite passes unchanged (deliverable byte-snapshots identical; event snapshots at semantic parity; `assert_seq_contiguous` holds)

## Boundaries

**In scope:**
- New `ExecutionContext` per-run state container (plan: `agents/execution_engine/context.py`)
- Migrating all enumerated `self._*` run state off the singleton onto `ExecutionContext`, threaded through `execute()`
- Making the kernel singleton stateless / immutable after construction (NFR-001)
- An explicit parent-run ownership check at the seed/store boundary (L16) + a cross-owner denial test
- Deleting the dead `_handle_revision` method (D1)
- Flipping migration-ledger rows L14 and D1 to `☑` (grep gates become enforced ratchets returning 0) and recording the L16 denial test

**Out of scope:**
- Manifests, compiler, typed `ArtifactGraph`/`ArtifactRef` — Phase 4/5; this phase keeps the legacy `accumulated_outputs` mirror (it may ride on `ExecutionContext` as a field but is **not** replaced here)
- Real `ModelResolver` / `BudgetManager` behavior — the plan's `ExecutionContext` dataclass references them, but their logic is Phase 6/11; in 0B they are threaded/placeholdered, not implemented
- Token-trim / wiring `_extract_html_skeleton` (L13) — Phase 3 [0C]
- Deleting the workflow-name/`pipeline_type`/`spec.id` kernel leaks L1–L13, L15 — Phase 7 [2]
- Splitting `engine.py` into `kernel.py` — later (Phase 7); 0B lifts state only, no file split mandated
- The full default-deny store-layer scoped-query helper for *all* reads (AUTHZ-02) — Phase 5 [1B]; 0B adds only the L16 point-fix on `parent_run` seeding
- `Workspace` / `RuntimeEnvironment` abstraction — Phase 9
- **Any** behavior or semantic change — forbidden by CTX-05 / INV-3

## Constraints

- **Backward-compat (INV-3):** deliverable bytes identical where deterministic; semantic event parity — proven by the Phase 0A characterization snapshots; this is the hard gate on the whole phase.
- **INV-2:** no per-run state on the singleton; kernel immutable after construction (the defining success condition, NFR-001).
- **Additive / extend-don't-replace:** Python · FastAPI · PostgreSQL · LangGraph checkpointer stack unchanged; no migrations required this phase (state move is in-memory).
- **INV-13:** agents still run on LangChain `deepagents`; this phase does not touch the agent runtime.
- **Anonymous principal:** the ownership check must treat the synthetic `anon:<session_id>` owner as a real principal (never `None`).
- **Hexagonal / import-linter:** must not introduce new kernel→legacy coupling that the §31 import-linter contract forbids.
- **Verbatim deletion gates:** L14 grep `self\._(od_context|completed_tasks|current_task_block|revision_|gate_agent_ids)` → 0; D1 grep `_handle_revision` → 0; L16 is a CHECK (denial test), not a grep.

## Acceptance Criteria

- [ ] `ExecutionContext` exists, is constructed once per run in `execute()`, and is threaded through the run
- [ ] L14 grep `self\._(od_context|completed_tasks|current_task_block|revision_|gate_agent_ids)` over `backend/` returns 0
- [ ] Kernel singleton has no per-run attribute writes after construction (NFR-001/INV-2), including `_user_id`, `_checkpointer`, and `_parent_run_id` relocated to the context
- [ ] Cross-owner `parent_run` seed is rejected by an explicit ownership check (L16 denial test passes)
- [ ] grep `_handle_revision` over `backend/` returns 0 (D1)
- [ ] Phase 0A deliverable byte-snapshots remain byte-identical
- [ ] Phase 0A semantic event snapshots remain at parity; per-run `seq` contiguous
- [ ] Migration-ledger rows L14 and D1 flipped to `☑` (grep ratchets green); L16 row recorded with its denial test

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                                        |
|--------------------|-------|------|--------|--------------------------------------------------------------|
| Goal Clarity       | 0.95  | 0.75 | ✓      | Plan fixes exact attributes, dataclass shape, no-change rule |
| Boundary Clarity   | 0.92  | 0.70 | ✓      | Strangler order draws explicit walls; later-phase leaks out  |
| Constraint Clarity | 0.85  | 0.65 | ✓      | Byte-identity + semantic parity + INV-2 + verbatim gates     |
| Acceptance Criteria| 0.88  | 0.70 | ✓      | L14/D1 grep→0, L16 denial test, 0A snapshots green           |
| **Ambiguity**      | 0.09  | ≤0.20| ✓      | Gate passed on initial assessment; no interview required     |

Status: ✓ = met minimum, ⚠ = below minimum (planner treats as assumption)

## Interview Log

No Socratic interview was run. The initial ambiguity assessment (from ROADMAP.md + REQUIREMENTS.md + the authoritative `specs/003-workflow-engine-decoupling/plan.md`, which `STATE.md` records as the complete spec) passed the gate at 0.09 with all dimensions clearing their minimums. Per the project's plan-ingestion preference, requirements were copied faithfully from the plan rather than re-derived interactively. User confirmed "Write SPEC.md now."

| Round | Perspective | Question summary                          | Decision locked                                              |
|-------|-------------|-------------------------------------------|-------------------------------------------------------------|
| —     | (auto)      | Initial gate already ≤ 0.20?              | Yes (0.09) — derive from plan §25 [0B] / §6 / §19           |
| —     | (auto)      | Scope = which ledger rows?                | L14 (state lift) + L16 (ownership check) + D1 (delete dead) |
| —     | (auto)      | Behavior change allowed?                  | No — INV-3 byte-identity + semantic event parity            |

---

*Phase: 02-executioncontext-ownership-0b*
*Spec created: 2026-06-07*
*Next step: /gsd-discuss-phase 2 — implementation decisions (ExecutionContext field layout, threading strategy, ownership-check seam)*
