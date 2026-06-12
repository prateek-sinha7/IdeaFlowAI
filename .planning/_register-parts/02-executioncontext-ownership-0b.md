## Phase 02 — ExecutionContext + Ownership [0B]

**Folder:** `.planning/phases/02-executioncontext-ownership-0b/`  ·  **Status:** Complete (2026-06-07)  ·  **Plans:** 3/3  ·  **Plan-id → source plan §25:** 0B
**Requirements delivered:** CTX-01, CTX-02, CTX-03, CTX-05  ·  **Deferred:** CTX-04 (voided — `_handle_revision` is live)
**One-line outcome:** Lifted every per-run `self._*` datum off the `ExecutionEngine` singleton onto a new threaded per-run `ExecutionContext` (kernel now stateless after `__init__`) and added the explicit cross-owner `parent_run` ownership gate — with zero behavior change (0A snapshots byte-identical, L14 grep → 0).

### 1. Goal & Success Criteria (what was PLANNED)
Pure state-relocation + one security point-fix + one (intended) dead-code deletion — **no manifests, no typed artifacts, no new capabilities, no engine file-split** (→ 02-CONTEXT.md "Phase Boundary"; 02-SPEC.md "Goal"). Depends-on Phase 1 [0A] which provides the golden-snapshot characterization suite (`_scripted_model._drive`), the migration-ledger CI ratchet, and the import-linter kernel→ports scaffold (→ 02-01-SUMMARY.md frontmatter `requires`).

Five locked requirements (ambiguity score 0.09; → 02-SPEC.md "Requirements"):
- **CTX-01 / L14 / INV-2** — all enumerated `self._*` per-run state moves onto a per-run `ExecutionContext`; acceptance = L14 grep returns 0.
- **CTX-02 / NFR-001 / INV-2** — kernel singleton holds NO per-run attributes after construction (immutable kernel).
- **CTX-03 / L16 / INV-8** — explicit ownership check on `parent_run` seeding rejects cross-owner access; cross-owner denial test passes.
- **CTX-04 / D1** — delete dead `_handle_revision`. **VOIDED during execution** (→ 02-SPEC.md "Requirements §4").
- **CTX-05 / INV-3** — zero behavior change; deliverables byte-identical, events at semantic parity, `seq` contiguous (the hard gate on the whole phase).

### 2. What Was Implemented — per plan (what was BUILT)

| Plan | Title (short) | What it built (names only) | Key modules/files touched | Status | Detail |
|------|---------------|-----------------------------|----------------------------|--------|--------|
| 02-01 | ExecutionContext state lift | `ExecutionContext` dataclass; `ectx` param threaded through 6 read-site methods; all per-run `self._*` writes deleted | `context.py` (new), `engine.py`, `test_execution_context.py` (new) + 4 white-box test files | Complete | → 02-01-PLAN.md (planned) / 02-01-SUMMARY.md (built) |
| 02-02 | Delete `_handle_revision` (D1) + flip ledger | **RE-SCOPED**: delete VOIDED (method is live); flipped ONLY L14 → ☑; fixed `_parse_rows` escaped-pipe bug; corrected D1 ledger row | `migration-ledger.md`, `test_migration_ledger.py` (NO engine.py change) | Complete (re-scoped) | → 02-02-PLAN.md (planned) / 02-02-SUMMARY.md (built) |
| 02-03 | Parent-run ownership check (L16 / CTX-03) | `authz.py` + pure `assert_owns`; `_derive_parent_owner`; ownership gate wired above seed try; 9 ownership tests; L16 → ☑ | `authz.py` (new), `engine.py`, `test_parent_run_ownership.py` (new), `migration-ledger.md` | Complete | → 02-03-PLAN.md (planned) / 02-03-SUMMARY.md (built) |

### 3. Capabilities, Modules, Schema & API Added
No registered capabilities, no Alembic migrations, no API endpoints, no event types (pure infra/refactor phase — → 02-SPEC.md "Constraints": "no migrations required this phase"). New code symbols:
- **`ExecutionContext`** — mutable `@dataclass` in new `backend/agents/execution_engine/context.py` (the engine-level per-run state container; DISTINCT from factory's per-agent `AgentContext` — do not conflate). D-01 minimal field set: `run_id`, `owner_id` (required); `od_context`, `completed_tasks`, `gate_agent_ids`, `parent_run_id`, `checkpointer`, `current_task_block`, the FLAT `revision_*` group (`revision_original_html`/`revision_instruction`/`revision_baseline_static`/`revision_baseline_console`), `accumulated_outputs`, `cancel_event`, `disk_skills`, `depth`. NO speculative later-phase fields (`plan`/`workspace`/`artifacts`/`budget`/`models`/`workspace_id`) — INV-12 (→ 02-01-SUMMARY.md "Final ExecutionContext field layout"). Stdlib-only imports (import-direction clean).
- **`assert_owns(owner_id, parent_run_id, parent_owner_id) -> None`** — pure free function in new `backend/agents/execution_engine/authz.py`; raises builtin `PermissionError` iff `parent_owner_id != owner_id`; no I/O (Phase-5-relocatable). The D-06 seam Phase 5 AUTHZ-02 absorbs as a MOVE (→ 02-03-SUMMARY.md "Task 1").
- **`ExecutionEngine._derive_parent_owner(user_id, parent_run_id)`** — by-convention 0B parent-owner derivation, returns `user_id or "anon"`; Phase 5 replaces with a real store lookup (→ 02-03-SUMMARY.md "By-convention derivation note").
- **`ectx` parameter** added (positional, last) to `_run_agent`, `_run_build_task_loop`, `_should_gate`, `_build_context_message`, `_write_build_reference_files`; `_run_validation_fix_loop` got a keyword-only `checkpointer=` arg (NOT a full `ectx` — named `ectx` everywhere to avoid shadowing its existing `ctx: AgentContext` param) (→ 02-01-SUMMARY.md "New ectx parameter added").
- Registry counter `_KNOWN`: not applicable (no capability registration this phase).

### 4. What Was Deleted / Superseded (INV-12 move-don't-copy)
- **L14 dissolved** — every per-run `self._*` write DELETED from the `ExecutionEngine` singleton; only `_resolver`/`_store`/`_state_machine` (the 3 `__init__` construction-time singletons) survive. Relocated: `_od_context`, `_user_id`, `_gate_agent_ids`, `_parent_run_id`, `_checkpointer`, `_completed_tasks`, `_current_task_block`, the four `_revision_*`, `_disk_skills` → all now on `ectx` (→ 02-01-SUMMARY.md "Accomplishments").
- **Ledger row L14 flipped ☐→☑** (deleting SHA `8b90fd2`) — its grep ratchet `self\._(od_context|completed_tasks|current_task_block|revision_|gate_agent_ids)` is now ARMED and enforced by CI; reappearance fails the build permanently (→ 02-02-SUMMARY.md "What was delivered").
- **Ledger row L16 flipped ☐→☑** as a CHECK row (NOT a grep ratchet — enforcement lives in `test_parent_run_ownership.py`) (→ 02-03-SUMMARY.md "Ledger / orchestrator coordination").
- **D1 / `_handle_revision` NOT deleted** — the planned deletion was VOIDED (see §5/§7). D1 row stays ☐ (deferred, with a `‡` finding note in the ledger).
- **No Alembic migration, no import-linter contract added** this phase (state move is in-memory; `context.py`/`authz.py` keep the existing Phase-1 kernel→ports scaffold green by importing only stdlib).

### 5. Key Decisions & Locked Constraints (do NOT contradict)
- **D-01** minimal field set; do NOT add `plan`/`workspace`/`artifacts`/`budget`/`models`/`workspace_id` to `ExecutionContext` (added in owning phases 4/9/5/11/6; `workspace_id` → Phase 5) (→ 02-CONTEXT.md "ExecutionContext scope"; 02-01-SUMMARY.md).
- **D-02** `current_task_block` is a **DELIBERATE Phase-7-TEMPORARY home** on `ExecutionContext` — the only known-temporary field; **Phase 7 [2] must reclaim it into `TaskLoopStrategy`** (→ 02-01-SUMMARY.md "D-02 flag for Phase 7").
- **D-03** explicit `ectx` parameter threading — NO `contextvars`/ambient state (fan-out phases 5/6 would have to undo it) (→ 02-CONTEXT.md "Threading mechanism").
- **D-04** `owner_id = user_id or "anon"`; `"anon"` is a REAL owner principal, never None — it cannot bypass the ownership check. The formal `anon:<session_id>` synthetic owner is deferred to Phase 5 / AUTHZ-03 (→ 02-CONTEXT.md "Owner identity").
- **D-05** `RunSandbox(user_id or "anon", parent_run_id)` disk keying is BYTE-IDENTICAL — do NOT swap in `ectx.owner_id` at the keying call (keeps 0A paths identical) (→ 02-CONTEXT.md "Owner identity"; verified grep still matches).
- **D-06** `assert_owns` kept small/pure in `authz.py` so Phase 5 AUTHZ-02 relocates it as a MOVE, not a rewrite (→ 02-03-SUMMARY.md "key-decisions").
- **D-07** denial = builtin `PermissionError`, raised LEXICALLY ABOVE the graceful-degrade `try:` so it is NOT swallowed by the broad `except Exception as _seed_exc`; do NOT widen that except to catch `PermissionError`. Same-owner missing/TTL-swept parents still degrade gracefully (→ 02-03-SUMMARY.md "Wiring point (D-07)").
- **CTX-05 / INV-3** is the binding gate: any future engine edit here must keep 0A snapshots byte-identical + semantic-event parity.

### 6. Status, Verification & Evidence (what HAPPENED)
- **Verdict: PASSED — 4/4 must-have truths verified** (→ 02-VERIFICATION.md "Goal Achievement"). Evidence: `ExecutionContext(` at engine.py:485; `assert_owns(` at engine.py:598 (inside `if parent_run_id:` line 587, above `try:` line 603); only 3 `self._` assignments in engine.py (all `__init__`); L14 grep → 0; full 0A suite **278 passed, 18 skipped**; ledger guard **4 passed, 1 skipped** (L16 CHECK-row skip is correct); 9/9 ownership tests pass (5 unit + 4 end-to-end).
- **Code review: 2 Critical, 3 Warning, 4 Info (9 total), status `issues_found`** (→ 02-REVIEW.md). The two Criticals are SECURITY-relevant and **as-designed for 0B, not fixed**:
  - **CR-01** — ownership check is reached only when `existing_html` is truthy (nested inside `if pipeline_type == "prototype_revision":` → `if existing_html:`); a `parent_run_id` supplied with no HTML block skips both check and seeding. Impact limited in 0B (seeding is gated by the same condition, so no cross-boundary copy), but the guard does not unconditionally cover the `parent_run_id` parameter. Reviewer recommends hoisting the check to guard the param unconditionally.
  - **CR-02** — `_derive_parent_owner` always returns the caller's own identity, so `assert_owns` is a **no-op in all real 0B production invocations** (only test monkey-patching exercises the deny path). **L16 ☑ implies enforcement that does not exist until Phase 5 AUTHZ-02 lands** — a hard carry-forward constraint. (CR/WR/IN findings appear to be advisory; no `02-REVIEW-FIX.md` exists in the folder.)
- **Security threats**: T-02-01..10 registered across the three plans (info-disclosure on shared singleton, cross-owner seeding, anon-bypass, graceful-degrade re-widening, regression) all dispositioned `mitigate`; package-install threats `accept` (stdlib only) (→ 02-01/02/03-PLAN.md threat_model). No standalone `02-SECURITY.md` in folder.
- **Key commits**: `5a71931` (02-01 Task 1 context.py), `8b90fd2` (02-01 Task 2 state lift; also the L14 deleting SHA), `f1f194c` (02-03 Task 1 authz.py), `d91e4d7` (02-03 Task 2 wire gate + L16).

### 7. Gotchas, Survivors & Carry-Forward
- **`_handle_revision` is a LIVE SURVIVOR — do NOT delete it.** Despite the spec/D1 calling it "dead," it is the live handler for the frontend `run_revision` PPT-revision message (`DashboardLayout.tsx:385` → `app/api/websocket.py:625` → `engine.py::_handle_revision`), with a dedicated `backend/tests/unit/test_revision_intelligence.py` suite. The inline `prototype_revision` pipeline (which 0A snapshots characterize) is a SEPARATE mechanism — the spec conflated them. Deleting would break PPT revision (CTX-05 violation). D1/CTX-04 deferred pending a product decision to retire `run_revision` (→ 02-02-SUMMARY.md "The defect"; 02-VERIFICATION.md "Deferred Items").
- **L16 gate is structurally wired but provides ZERO real enforcement in 0B production** (CR-02) — `_derive_parent_owner` returns the caller's own id. Real protection requires Phase 5 AUTHZ-02 to land. Do not assume cross-owner seeding is actually blocked yet.
- **`accumulated_outputs` field on `ExecutionContext` is a sanctioned DEAD mirror (L15)** — the live map is a local dict in `execute()` (engine.py:878); `ectx.accumulated_outputs` is never written. Reading it returns an empty dict (WR-03). Removed in Phase 1B.
- **`current_task_block` carry-forward (D-02)** — Phase 7 must reclaim it into `TaskLoopStrategy`.
- **`_parse_rows` escaped-pipe bug fixed in 02-02** — ledger gate cells holding grep alternations must escape pipes as `\|` for the markdown table; the parser un-escapes before `grep -E`. L14 was the first alternation-pattern row to flip, surfacing this latent Phase-1 bug. Later alternation rows (L3/L10/L11) now flip correctly (→ 02-02-SUMMARY.md "What was delivered" #3).
- **Stray gitignored `backend/backend/.local/`** (192 MB python3.13 pip-target) vendored alembic whose `self._revision_map` false-matched the L14 `revision_` alternation; removed (user-approved), never affected CI (→ 02-02-SUMMARY.md). The L14 ratchet greps with `--include=*.py` over git-tracked source.
- **Pre-existing unrelated test failures NOT caused by this phase** (do not chase): `tests/unit/test_logout.py` x7 (JWT/DB auth) and `tests/unit/test_pipeline_cancel.py::test_cancel_marks_workflow_cancelled_and_sends_ack` (expired AWS Bedrock token; the test stubs the engine so real `execute()` never runs) (→ deferred-items.md).
- **`ExecutionContext` vs `AgentContext`**: engine-level per-RUN vs factory per-AGENT — distinct objects, same dataclass idiom; `_run_validation_fix_loop` carries both (its `ctx: AgentContext` plus relocated state via args).

### 8. File Index (every file in this folder)
- `02-01-PLAN.md` — plan to create `ExecutionContext` + thread `ectx`, relocate all per-run state. Open for the exact lift table (write-site → field) and the planned method-signature changes.
- `02-01-SUMMARY.md` — built record of the state lift; the canonical `ExecutionContext` field-layout table, the D-02 Phase-7 flag, the new `ectx` params, and the 10 white-box-test auto-fixes. Open this first to understand the seam.
- `02-02-PLAN.md` — original plan to delete `_handle_revision` + flip L14/D1; carries the prominent `rescope_notice` banner explaining the void. Open to see what was planned vs. what the executor blocked.
- `02-02-SUMMARY.md` — the re-scope record; the `_handle_revision`-is-live evidence table, the L14-only flip, the `_parse_rows` bug fix, and the product follow-up. Open before touching revision code or the ledger parser.
- `02-03-PLAN.md` — plan for the `authz.py`/`assert_owns` ownership gate, its placement above the seed try, and the L16 denial tests. Open for the exact wiring contract (D-06/D-07).
- `02-03-SUMMARY.md` — built record of the ownership gate; the wiring snippet, the by-convention `_derive_parent_owner` note for Phase 5, and the 9 tests. Open before any parent-run/ownership work.
- `02-CONTEXT.md` — the four locked HOW decisions (D-01..D-07), canonical refs, reusable assets, deferred ideas. Open before planning any adjacent ExecutionContext/ownership work.
- `02-DISCUSSION-LOG.md` — audit trail of the four dismissed gray-area forks (all locked to plan-recommended option). Reference only; not planning input.
- `02-PATTERNS.md` — analog map: `AgentContext` dataclass idiom for `context.py`, `state_machine.py` shape + `TemplateMissingError` idiom for `authz.py`, the engine lift/threading tables with (now-stale) line numbers. Open for the copy-this-idiom guidance.
- `02-REVIEW.md` — code review: 2 Critical (CR-01 conditional-bypass, CR-02 no-op guard), 3 Warning (timeout crash path WR-01, stale docstring WR-02, dead `accumulated_outputs` WR-03), 4 Info. Open to understand the L16 enforcement caveat and the WR-01 timeout-format latent bug.
- `02-SPEC.md` — the 5 locked requirements (CTX-01..05), boundaries, acceptance criteria, ambiguity report. CTX-04 marked VOIDED. Open for the authoritative scope walls.
- `02-VERIFICATION.md` — PASSED, 4/4 truths verified, with concrete grep/test evidence and the CTX-04 deferred-by-design entry. Open for the proof-of-done.
- `deferred-items.md` — the two pre-existing unrelated test failures (test_logout, test_pipeline_cancel) recorded as out-of-scope. Open if those tests fail and you need to confirm it is not this phase's regression.
