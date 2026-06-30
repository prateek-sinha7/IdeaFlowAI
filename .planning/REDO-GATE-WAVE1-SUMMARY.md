# REDO-GATE — Wave 1 (backend) execution summary

Branch: `new-workflow-engine` (no worktree — main tree edited). Plan:
`.planning/REDO-GATE-PLAN.md` (v2, review-hardened). Frontend (Wave 2) NOT touched.

One-liner: the human review gate now supports a generic, name-free **Redo (with
optional additional instructions)** action that re-runs the gated agent in place as a
flat `while True:` loop, keeps the rejected output as a prior `ArtifactRef` version with
`derived_from` lineage, re-pauses at the same gate, and is safely fenced off the
un-wired declared-gate path — with the 5 characterization goldens kept byte-identical
(redo path dormant on every normal run).

---

## Tasks completed

| Task | What | Files | Commit |
|------|------|-------|--------|
| T1 | `ExecutionContext.redo_directive` additive scratch field | `agents/execution_engine/context.py` | 802cb6fe |
| T2 | `set_review_response` additive `action`/`instructions` kwargs + store test | `agents/artifact_store/store.py`, `tests/unit/test_artifact_store.py` | b4e2286f |
| T6 | `approve_review` WS handler accepts `action:"redo"`/`instructions` (owner-check unchanged) + ownership pin | `app/api/websocket.py`, `tests/unit/test_approve_review_ownership.py` | 7500d4b0 |
| T3 | `_run_review_gate` redo branch + generic `redoable` flag on `review_gate_ready` + `redoable` ∈ `_VOLATILE_STRIP_KEYS` | `agents/execution_engine/engine.py`, `tests/agents/characterization/_normalize.py` | f18de868 |
| T-human | `HumanGate` **and** `ApprovalGate` consume `_gate_redo` (never yield, never `GATE_PASS`; honest non-PASS audit) | `agents/capabilities/gates/human.py`, `agents/capabilities/gates/approval.py` | 8d53b1ce |
| T4 (+B5, +T7) | `_run_agent` run+gate → `while True:` loop; `_gate_redo` consumer with consume-once loop locals; `results.pop()`; `redoable=True` from the inline site; `derived_from=_iter_derived` on the main write (B5); best-effort redo audit row (T7) | `agents/execution_engine/engine.py` | f783d2db |
| T5 (B6+B10) | `=== ADDITIONAL INSTRUCTIONS (REVISE) ===` block in `_compose_context_message`; `_latest_typed_content` selects max-`version` (F5) | `agents/execution_engine/engine.py` | 9be9f5b1 |
| Safety tests | F1 (human+approval), F2, F3 (empty+exception), F5 | `tests/agents/test_redo_gate_safety.py` | d66df568 |

**T8 (optional F7 cancel-aware gate wait): SKIPPED** as instructed — documented as a
follow-up. The Stop-while-paused gap (`engine.py` `await event.wait()` in
`_run_review_gate`) is pre-existing; unbounded redos amplify the open-panel window. Not
implemented in Wave 1.

---

## Verification results (offline targeted suite, `python3.11`, no venv)

| Check | Result |
|-------|--------|
| `tests/unit/test_artifact_store.py` | 11 passed (incl. new redo round-trip + updated default-keys) |
| `tests/unit/test_approve_review_ownership.py` | 7 passed (incl. redo IDOR pin) |
| `tests/agents/test_declared_gate_streaming.py` | 3 passed |
| `tests/agents/test_redo_gate_safety.py` (F1×2, F2, F3×2, F5) | 6 passed |
| `tests/unit/test_execution_engine.py` + cutover + hooks + model_fallback (one batch) | 74 passed total (this batch) |
| revision suites (`test_revision_gating`, `test_revision_file_editing`, `test_revision_intelligence`) | passed |
| 5 characterization goldens (no `SNAPSHOT_UPDATE`) | **4/5 byte-identical** (prototype, od_prototype, prototype_revision, app_builder) — INV-3 holds; od_ppt event snapshot fails (PRE-EXISTING, see below) |
| `tests/agents/test_migration_ledger.py` | 23 passed, 7 skipped |
| `tests/agents/test_banned_patterns.py` (R15) | 11 passed |
| `lint-imports` (`/opt/homebrew/bin/lint-imports`) | **4 kept / 0 broken** |
| Dispatch-loop pin grep (`for i, spec in enumerate(ordered_agents)`) | exactly **1** occurrence |
| SC-001 grep over `agents/execution_engine/` | clean — redo path keys only on `action=="redo"` / `_gate_redo` / `redoable` / `redo_directive`; **no** workflow/agent-id literal |

### Invariant compliance
- **SC-001 / INV-1:** name-free (grep clean). v1 covers all *live* (inline) human gates;
  declared/user-composed gates are safely fenced (`redoable=false` + consume-arm).
- **INV-2:** new per-run state is `ExecutionContext.redo_directive`; `redo_derived_from`
  is a `_run_agent` loop local — neither is process/singleton state.
- **INV-3:** 4/5 goldens byte/event-identical; the one new golden-path key `redoable`
  is in `_VOLATILE_STRIP_KEYS`; `_gate_redo` is internal (consumed on both consumers).
- **INV-12:** reuses the one `_run_review_gate` pause + `set_review_response`/
  `get_review_event` channel + `approve_review` owner-gated handler + `_run_agent`
  dispatch + `ArtifactGraph` versioning. Single dispatch loop intact (pin = 1).
- **Additive-only:** NO Alembic migration added.
- **Ports & adapters:** lint-imports 4/0.

---

## Pre-existing failures (NOT introduced by this work — verified at the pre-work commit)

1. `tests/agents/test_characterization_od_ppt.py::test_od_ppt_event_snapshot` — diverges
   at `agent_input.context_message` (the od_ppt template/example block), NOT
   `review_gate_ready`/redo. Confirmed FAILING at committed HEAD before T3 (stashed my
   uncommitted T3 changes → still failed). The od_ppt **deliverable** snapshot passes.
2. `tests/agents/test_restart_resume.py::test_waiting_for_user_run_is_rearmed_not_driven`
   — expects a `waiting_for_user` run to be re-armed, but `restore_non_terminal_runs`
   marks it `failed`. Confirmed FAILING against `engine.py` at the pre-work commit
   (1327acce). This is exactly the **F4 known limitation** the plan documents (§9 R3):
   a mid-gate restart loses the in-memory pause; pending redo is lost; no corruption.

Both are logged as out-of-scope per the deviation scope boundary (only auto-fix issues
directly caused by the current task's changes). Neither is touched by the redo path.

---

## Deviations from plan

- **None functional.** Task numbering note: the plan lists B5 (`derived_from` on the main
  write) under T5, but it physically lives inside the `_run_agent` loop body (T4's hunk),
  so it was committed with T4. T7 (audit row) was committed with T4 for the same reason.
  B6/B10 are the T5 commit. No behavior change vs the plan.
- **Implementation choice (bounded by the plan):** the declared-path stray-redo outcome
  is `GATE_WAIT_HUMAN` (the plan's recommended non-PASS option; `GATE_BLOCK` was the
  alternative). The two safety assertions the plan pins (no `_gate_redo` leak; outcome ≠
  `GATE_PASS`) hold either way.

## Items deferred / follow-ups (as planned)
- **T8 / F7** cancel-aware gate wait — not implemented (Wave 1 optional, skipped).
- **Wave 2 frontend** (`ReviewGatePanel`, `DashboardLayout`, `page.tsx`, `types`, F8
  agent-panel idempotency) — out of scope for this wave.
- **Declared-path real redo** (a `GateOutcome "redo"` re-running the gated producer step)
  — documented follow-up (R2); v1 fences it safely.
- **F4 durable resume** — known limitation (pre-existing); pending redo lost on a
  mid-gate restart, run marked `failed`, no corruption.

## Self-check
- All listed files exist and were committed (8 commits b4e2286f…d66df568 + 802cb6fe).
- `engine.py` AST-parses; redo identifiers present and generic.
- Working tree clean except the pre-existing unrelated `app/core/config.py` change
  (left untouched, unstaged) and untracked `.planning/REDO-GATE-PLAN*.md` (not mine).
