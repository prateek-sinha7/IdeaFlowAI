# Phase 2: ExecutionContext + Ownership [0B] - Context

**Gathered:** 2026-06-07
**Status:** Ready for planning
**Mode:** Recommended options locked (gray-area question dismissed) — every decision below is the plan-grounded recommendation; review/edit before planning if any needs changing.

<domain>
## Phase Boundary

Lift every per-run `self._*` attribute off the `ExecutionEngine` singleton into a new per-run `ExecutionContext`, make the kernel immutable/stateless after construction (INV-2/NFR-001), add an explicit cross-owner ownership check on `parent_run` seeding (L16/INV-8), and delete the dead `_handle_revision` (D1) — with **zero behavior change** (deliverable bytes identical, events at semantic parity, proven by the Phase 0A golden snapshots).

**This phase is a pure state-relocation + one security point-fix + one dead-code deletion.** No manifests, no typed artifacts, no new capabilities, no engine file-split.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**5 requirements are locked.** See `02-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `02-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- New `ExecutionContext` per-run state container (plan: `agents/execution_engine/context.py`)
- Migrating all enumerated `self._*` run state off the singleton onto `ExecutionContext`, threaded through `execute()`
- Making the kernel singleton stateless / immutable after construction (NFR-001)
- An explicit parent-run ownership check at the seed/store boundary (L16) + a cross-owner denial test
- ~~Deleting the dead `_handle_revision` method (D1)~~ — **VOIDED in execution (2026-06-07): `_handle_revision` is live (the frontend `run_revision` PPT-revision handler), not dead. D1/CTX-04 deferred pending a product decision on `run_revision`. See `02-02-SUMMARY.md`.**
- Flipping migration-ledger row **L14** to `☑` (grep ratchet enforced → 0) and recording the L16 denial test **(D1 flip voided — live)**

**Out of scope (from SPEC.md):**
- Manifests/compiler/typed `ArtifactGraph` (Phase 4/5) — `accumulated_outputs` legacy mirror stays
- Real `ModelResolver`/`BudgetManager` behavior (Phase 6/11) — not built here
- Token-trim / `_extract_html_skeleton` wiring (L13) — Phase 3 [0C]
- Deleting workflow-name/`pipeline_type`/`spec.id` kernel leaks L1–L13, L15 — Phase 7 [2]
- Splitting `engine.py` into `kernel.py` — later (Phase 7); 0B lifts state only
- The full default-deny store-layer scoped-query helper for all reads (AUTHZ-02) — Phase 5 [1B]
- `Workspace`/`RuntimeEnvironment` abstraction — Phase 9
- **Any** behavior or semantic change — forbidden by CTX-05 / INV-3

</spec_lock>

<decisions>
## Implementation Decisions

> These are the four HOW forks the plan leaves open (it specifies the end-state `ExecutionContext`, not the strangler increment). Each is locked to the recommended option.

### ExecutionContext scope (D-01, D-02)
- **D-01: Minimal 0B context — add only fields with real backing now.** `ExecutionContext` (new `agents/execution_engine/context.py`) carries: run identity (`run_id`, `owner_id` — see D-05), the migrated run state (`od_context`, `completed_tasks`, `gate_agent_ids`, `parent_run_id`, `checkpointer`, and the `revision_*` group: `original_html`, `instruction`, `baseline_static`, `baseline_console`), the legacy `accumulated_outputs` mirror, `cancel_event`, and `depth: int = 0`. Do **NOT** lay down the heavy later-phase fields (`plan: CompiledWorkflow`, `workspace: Workspace`, `artifacts: ArtifactGraph`, `budget: BudgetManager`, `models: ModelResolver`) — they reference types that don't exist until Phases 4/9/5/11/6. *Rationale:* INV-12 (no abstractions you don't yet use) + INV-3 (no behavior change) — speculative placeholder fields contradict the plan's "thin" philosophy. The dataclass grows in each later phase as its types land. `workspace_id` is **deferred to Phase 5 (1B)** when the `workspaces` table exists — nothing in 0B consumes it.
- **D-02: `_current_task_block` rides on the per-run context in 0B.** The plan (dataclass comment, plan.md:349) says strategy-local scratch ultimately lives *in the strategy, not on ctx* — but strategies don't exist until Phase 7. For 0B the only way to get it off the singleton (L14 grep gate) is onto the context. Carry it on `ExecutionContext` now; flagged in Deferred Ideas to migrate into `TaskLoopStrategy` in Phase 7. *(This is the one field that is a known temporary home — call it out in the SUMMARY so Phase 7 reclaims it.)*

### Threading mechanism (D-03)
- **D-03: Explicit `ctx: ExecutionContext` parameter threaded through every read-site — no `contextvars`.** `execute()` constructs the ctx once and passes it down through the 6 methods that read run state: `_run_agent` (1108), `_run_build_task_loop` (1450), `_run_validation_fix_loop` (1706), `_build_context_message` (2315), `_should_gate` (1890). *Rationale:* this is exactly the plan's port signature shape (`run(step, ctx)`, `resolve(ctx)`, `load(ctx)`, `evaluate(step, ctx)` — plan.md:400-423). A `contextvars` ambient ContextVar would minimize signature churn but reintroduce hidden ambient state — a different flavor of the very coupling this phase removes — and the fan-out/wave phases (5/6, where multiple ctx coexist) would have to undo it. The signature churn *is* the refactor. ~28 references across 6 methods + their call sites.

### Owner identity in 0B (D-04, D-05)
- **D-04: Reuse today's `user_id` (with `"anon"` fallback) as the owner principal — do NOT introduce `anon:<session_id>` yet.** `ExecutionContext.owner_id` is populated from `user_id or "anon"`, exactly as `RunSandbox(user_id or "anon", …)` keys disk today. *Rationale:* keeps sandbox paths byte-identical → 0A snapshots stay green (CTX-05). The formal synthetic-session owner (`anon:<session_id>`, never None) is **AUTHZ-03 / Phase 5** — doing it here would change keying (behavior change) and is scope creep into 1B.
- **D-05: `RunSandbox` keying is unchanged in 0B.** The L16 fix is about *who may seed from a parent run*, not about renaming disk dirs. Sandbox construction stays `RunSandbox(owner_principal, run_id)` with the same string that's used today.

### Ownership-check seam + denial behavior (D-06, D-07)
- **D-06: A small dedicated ownership helper, sited so Phase 5's store layer absorbs it as a *move*.** Introduce a tiny `assert_owns(owner_id, parent_run_id)` (candidate home: a new `agents/execution_engine/authz.py` seed, or a clearly-named method) rather than an inline owner-compare buried at `engine.py:583`. *Rationale:* INV-12 move-don't-copy + the import-linter trajectory (D-12 from Phase 1) — Phase 5's "single scoped-query helper at the store layer" (AUTHZ-02, plan §19) should *relocate* this check, not rewrite an inline tangle. Keep it small and pure so the move is mechanical.
- **D-07: The check raises a typed denial BEFORE the graceful-degrade try/except — cross-owner fails fast.** Today the seeding block (`engine.py:583-609`) swallows ANY failure (missing/TTL-swept parent → log + proceed). The ownership check must run **before** that try so a cross-owner `parent_run_id` raises (e.g. `PermissionError`) and is *not* swallowed → the run fails. *Rationale:* CTX-03's acceptance is "cross-owner parent seed is **rejected**"; a denial test expects rejection, not a silent skip. Cross-owner is a brand-new path (no 0A snapshot exercises it), so raising is not a CTX-05 behavior change. The graceful-degrade stays ONLY for *legitimate same-owner* missing/swept parents.

### Claude's Discretion
- Exact field names/order inside `ExecutionContext` (within D-01's set) and whether the `revision_*` group is a flat set of fields or a small nested `RevisionState` value object.
- The precise home/name of the ownership helper (D-06: `authz.py` function vs. engine method), provided it stays small and pure enough for Phase 5 to relocate without a rewrite.
- The exact exception type for the denial (D-07), provided it propagates out of `execute()` and a denial test can assert it.
- Plan-task granularity (the SPEC/ROADMAP suggest 02-01 context+thread, 02-02 migrate+statelessness+delete `_handle_revision`, 02-03 ownership check+denial test — keep or resplit as planning sees fit).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked requirements (read FIRST)
- `.planning/phases/02-executioncontext-ownership-0b/02-SPEC.md` — the 5 locked requirements (CTX-01..05), boundaries, acceptance criteria. **MUST read before planning.**

### The specification (authoritative)
- `specs/003-workflow-engine-decoupling/plan.md` — Phase 2 anchors:
  - **§6 lines 329-349** — the target `ExecutionContext` dataclass shape (the end-state; 0B builds the D-01 subset).
  - **§19 lines 719-730** — Authorization & multi-user boundaries (ownership model, default-deny, the L16 parent-seed fix, `anon:<session_id>` note → Phase 5).
  - **§25 lines 802-804** — Phase 0B accept criteria ("snapshots green; kernel has no per-run attributes (NFR-001); cross-owner parent seed rejected").
  - **§4 lines 283-285** — the L14/L16 leak rows (current `file:line`).
  - **§3 lines 251** — INV-2 (no per-run state on the singleton; immutable kernel).
- `specs/003-workflow-engine-decoupling/migration-ledger.md` — the **L14 / L16 / D1** rows: verbatim grep patterns the CI ratchet enforces, owning phase 0B. L14 grep = `self\._(od_context|completed_tasks|current_task_block|revision_|gate_agent_ids)`; D1 grep = `_handle_revision`; L16 = CHECK (denial test).

### Project planning
- `.planning/REQUIREMENTS.md` — CTX-01..05 with plan anchors.
- `.planning/ROADMAP.md` §"Phase 2" — goal, success criteria, candidate plan breakdown (02-01/02/03).
- `.planning/PROJECT.md` — invariants/constraints (INV-2, INV-3, INV-12, INV-13; no-dual-implementations).
- `.planning/phases/01-safety-net-deletion-guard-0a/01-CONTEXT.md` — Phase 1 decisions that constrain this phase (golden-snapshot parity mechanism, ledger ratchet, import-linter scaffold designed to tighten when `kernel.py` lands, INV-1 warn-only until Phase 7).

### Code to read (targets / assets)
- `backend/agents/execution_engine/engine.py` — the engine being refactored. Key sites:
  - `execute()` **:408** — signature + the `self._*` init block **:472-550** (where state is stashed today).
  - parent-run seeding **:583-609** (L16 target; graceful-degrade try/except to preserve for same-owner).
  - `_run_agent` **:1108**, `_run_build_task_loop` **:1450**, `_run_validation_fix_loop` **:1706**, `_build_context_message` **:2315**, `_should_gate` **:1890** — the read-sites to thread `ctx` through.
  - `_handle_revision` **:2138-2251** — dead method to delete (D1).
- `backend/tests/agents/_scripted_model.py` — the offline `_drive()` harness + 0A golden snapshots; **the parity-verification mechanism** for CTX-05 (must stay green).
- `backend/app/agents/sandbox.py` — `RunSandbox(user_id, run_id)` keying (D-04/D-05: unchanged).
- `backend/app/agents/checkpointer.py` — `get_checkpointer()` process-wide singleton (the `_checkpointer` field moves onto ctx but the underlying singleton is acquired the same way).
- `backend/CLAUDE.md` — backend architecture guide (engine = deterministic sequencer; data-flow; commit scopes — use `engine`/`tests` scopes).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`_scripted_model.py` `_drive(pipeline_type)`** — runs `execute()` end-to-end offline and returns ordered event dicts; the 0A golden snapshots (deliverable byte + semantic event) are the regression gate for "no behavior change". Re-run after each migration step.
- **The 0A migration-ledger CI guard** (`tests/agents/test_migration_ledger.py`) already exists — flipping L14/D1 to `☑` arms their grep ratchets automatically (no new test infra needed for those two).
- **`get_checkpointer()`** — process-wide cached singleton; the per-run `_checkpointer` reference moves to ctx, but acquisition stays `await get_checkpointer()` (do not close per-run; it's an app-shutdown concern — see the inline docstring at `engine.py:488-501`).

### Established Patterns
- The engine is the **deterministic sequencer**; `_run_agent` runs one agent via one `astream_events` loop. `create_runner(agent_id, ctx)` already takes an `AgentContext` (factory) — note the *engine's* new `ExecutionContext` is distinct from the *factory's* `AgentContext` (per-agent); don't conflate them. `od_context` flows engine → AgentContext per agent today (`engine.py:474` comment).
- Dev runtime: `python3.11`, no venv (project memory `dev-runtime`). Tests: `cd backend && python3.11 -m pytest tests/agents/ -v`.
- Commit scopes (backend/CLAUDE.md): `engine` for `execution_engine/` changes, `tests` for test files. Never commit to `main`; PR off `feature/003-workflow-engine-decoupling`.

### Integration Points
- New `context.py` is imported by `engine.py` only (0B). The import-linter kernel→ports contract (Phase 1 scaffold) anticipates `context.py` — keep the import direction clean (context defines data; it must not import legacy factory/engine internals).
- The ownership helper (D-06) is the seam Phase 5's store-layer `authz` scoped-query helper will absorb — keep it isolated.

</code_context>

<specifics>
## Specific Ideas

- Standing project directive (init): *"everything from plan.md must be honored — nothing dropped."* For 0B that means the migration-ledger L14/L16/D1 rows flip to `☑` with their **verbatim** grep patterns enforced, and the `ExecutionContext` end-state shape (plan §6) is respected even though 0B only populates the D-01 subset.
- The user dismissed the per-area discussion → all four forks locked to the plan-grounded recommendation (this mirrors Phase 1's `--auto` capture). Treat these as locked unless the user edits this file.

</specifics>

<deferred>
## Deferred Ideas

- **`workspace_id` on `ExecutionContext`** — add in Phase 5 (1B) when the `workspaces` table lands (AUTHZ-01/PERSIST-01). Nothing in 0B consumes it.
- **`anon:<session_id>` synthetic owner (never None)** — Phase 5 (1B) / AUTHZ-03. 0B reuses `user_id or "anon"` (D-04).
- **Full default-deny store-layer scoped-query helper** for all artifact/run reads — Phase 5 (1B) / AUTHZ-02. 0B ships only the L16 point-fix on `parent_run` seeding; the D-06 helper is the seam it absorbs.
- **`_current_task_block` → `TaskLoopStrategy`** — Phase 7 [2]. 0B parks it on the context (D-02) because no strategy exists yet.
- **Heavy `ExecutionContext` fields** (`CompiledWorkflow`/`Workspace`/`ArtifactGraph`/`BudgetManager`/`ModelResolver`) — each added in its owning phase (4/9/5/11/6).
- **`engine.py` → `kernel.py` split + import-linter contract tightening** — Phase 7/8. 0B keeps the single `engine.py` module (Phase 1 D-12 scaffold stays green).

None of these are scope creep — all are explicitly later-phase per ROADMAP.md / the §31 ledger.

</deferred>

---

*Phase: 2-ExecutionContext + Ownership [0B]*
*Context gathered: 2026-06-07*
