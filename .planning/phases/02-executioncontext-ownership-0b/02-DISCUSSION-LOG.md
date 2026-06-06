# Phase 2: ExecutionContext + Ownership [0B] - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-07
**Phase:** 2-ExecutionContext + Ownership [0B]
**Areas discussed:** ExecutionContext scope, Threading mechanism, Owner identity in 0B, Ownership-check seam + denial

> SPEC.md locked the 5 requirements (CTX-01..05) — discussion covered HOW only. The four
> gray-area question was presented (multiSelect) and **dismissed**; per the user's standing
> plan-ingestion / minimal-interaction preference (and mirroring Phase 1's `--auto` capture),
> each fork was locked to the plan-grounded recommended option.

---

## ExecutionContext scope

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal 0B context | Only fields with real backing now (run identity + migrated `self._*` + legacy `accumulated_outputs` mirror); heavy later-phase types added in their phases | ✓ |
| Full plan dataclass now | Lay down all plan fields, later-phase types as Optional/placeholder | |

**User's choice:** Recommended (Minimal) — locked by default on dismissal.
**Notes:** Rationale = INV-12 (no unused abstractions) + INV-3 (no behavior change). `_current_task_block` parks on the context for 0B (no strategy exists until Phase 7). `workspace_id` deferred to 1B. See CONTEXT.md D-01/D-02.

---

## Threading mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit `ctx` parameter | Thread `ctx: ExecutionContext` through the 6 read-site methods — matches the plan's `run(step, ctx)` port signatures | ✓ |
| `contextvars` ambient ContextVar | Set at `execute()` entry, read anywhere — less churn, but reintroduces hidden ambient state | |

**User's choice:** Recommended (Explicit param) — locked by default on dismissal.
**Notes:** ~28 references across `execute`/`_run_agent`/`_run_build_task_loop`/`_run_validation_fix_loop`/`_build_context_message`/`_should_gate`. contextvars would be undone by fan-out/wave phases (5/6). See CONTEXT.md D-03.

---

## Owner identity in 0B

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse `user_id` (+ "anon" fallback) | `owner_id = user_id or "anon"`; RunSandbox keying byte-identical | ✓ |
| Introduce `owner_id`/`anon:<session_id>` now | Formal synthetic-session owner — risks changing sandbox paths (behavior change) | |

**User's choice:** Recommended (Reuse user_id) — locked by default on dismissal.
**Notes:** Keeps 0A snapshots green (CTX-05). The `anon:<session_id>` synthesis is AUTHZ-03 / Phase 5. See CONTEXT.md D-04/D-05.

---

## Ownership-check seam + denial

| Option | Description | Selected |
|--------|-------------|----------|
| Small `assert_owns()` helper + raise BEFORE graceful-degrade | Isolated helper Phase 5's store layer absorbs (move-don't-copy); cross-owner raises a typed denial and fails fast | ✓ |
| Inline owner-compare at engine.py:583 | Buried inline; harder for Phase 5 to relocate | |
| Deny-seeding-but-proceed | Fold into existing graceful-degrade (silent skip) | |

**User's choice:** Recommended (helper + raise-before-try) — locked by default on dismissal.
**Notes:** Denial test expects rejection, not silent skip. Cross-owner is a new path (no 0A snapshot) so raising isn't a CTX-05 change. Graceful-degrade stays for legitimate same-owner missing/swept parents. See CONTEXT.md D-06/D-07.

---

## Claude's Discretion

- Exact `ExecutionContext` field names/order (within the D-01 set); flat `revision_*` fields vs. a nested `RevisionState`.
- Home/name of the ownership helper (`authz.py` function vs. engine method), provided it stays relocatable.
- Exact denial exception type (provided it propagates out of `execute()` and is assertable).
- Plan-task granularity (ROADMAP suggests 02-01/02/03; planner may resplit).

## Deferred Ideas

- `workspace_id` on `ExecutionContext` → Phase 5 (1B).
- `anon:<session_id>` synthetic owner → Phase 5 (1B) / AUTHZ-03.
- Full default-deny store-layer scoped-query helper → Phase 5 (1B) / AUTHZ-02.
- `_current_task_block` → `TaskLoopStrategy` → Phase 7 [2].
- Heavy `ExecutionContext` fields (CompiledWorkflow/Workspace/ArtifactGraph/BudgetManager/ModelResolver) → owning phases 4/9/5/11/6.
- `engine.py` → `kernel.py` split + import-linter tighten → Phase 7/8.
