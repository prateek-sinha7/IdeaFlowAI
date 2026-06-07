---
phase: 02-executioncontext-ownership-0b
plan: 03
subsystem: security
status: complete
tags: [authz, ownership, parent-run, security-point-fix, L16, INV-8, revision]

# Dependency graph
requires:
  - phase: 02-executioncontext-ownership-0b (plan 02-01)
    provides: "ExecutionContext.owner_id (= user_id or 'anon', D-04) + parent_run_id threaded into execute(); the per-run seam the ownership check reads"
  - phase: 02-executioncontext-ownership-0b (plan 02-02)
    provides: "L14 ☑ (armed); _parse_rows escaped-pipe fix; D1 corrected to deferred CHECK row; phase-status test asserting {L14}"
provides:
  - "Pure assert_owns(owner_id, parent_run_id, parent_owner_id) ownership predicate (agents/execution_engine/authz.py) raising PermissionError on cross-owner — the D-06 seam Phase 5 AUTHZ-02 relocates as a MOVE"
  - "Explicit L16 parent-run ownership gate wired into execute() ABOVE the graceful-degrade try (D-07): cross-owner parent raises and propagates out of execute(); same-owner missing/swept parent still degrades gracefully"
  - "ExecutionEngine._derive_parent_owner() — by-convention 0B parent-owner derivation (user_id or 'anon'); Phase 5 replaces with a real store lookup"
  - "migration-ledger L16 flipped to ☑ (CHECK row, records the denial test); phase-status test now asserts {L14, L16}"
affects: ["Phase 5 [1B] store-layer authz (AUTHZ-02 relocates assert_owns + replaces the by-convention derivation)"]

# Tech tracking
tech-stack:
  added: []   # stdlib only — PermissionError builtin; no package installs
  patterns:
    - "Pure free-function ownership predicate in a lean relocatable module (state_machine.py shape) — no persistence/sandbox/IO so Phase 5 absorbs it as a mechanical move (D-06 / INV-12)"
    - "Security gate placed LEXICALLY ABOVE a broad graceful-degrade try so the denial is not swallowed (D-07)"
    - "By-convention owner derivation exposed as a method (not an inline expression) so the cross-owner path is exercisable end-to-end"

key-files:
  created:
    - "backend/agents/execution_engine/authz.py — assert_owns ownership helper (raises builtin PermissionError)"
    - "backend/tests/agents/test_parent_run_ownership.py — 5 unit + 4 end-to-end ownership tests"
  modified:
    - "backend/agents/execution_engine/engine.py — import assert_owns; _derive_parent_owner(); assert_owns() call above the parent_run seed try"
    - "specs/003-workflow-engine-decoupling/migration-ledger.md — L16 ☐→☑ (CHECK row, records the denial test)"
    - "backend/tests/agents/test_migration_ledger.py — phase-status test renamed test_ledger_parses_and_phase0b_flips_l14_l16; asserts {L14, L16}"

key-decisions:
  - "Denial exception = builtin PermissionError (D-07 recommended default) — reads as a denial, a test asserts pytest.raises(PermissionError); no named subclass needed"
  - "assert_owns home = new agents/execution_engine/authz.py (D-06 candidate), kept pure (no persistence/sandbox/IO) so Phase 5 AUTHZ-02 relocates it as a move not a rewrite"
  - "Insertion point = INSIDE `if parent_run_id:`, LEXICALLY ABOVE the existing `try:` at engine.py seed block (D-07) — the broad `except Exception` is UNCHANGED, so it keeps catching ONLY legitimate same-owner missing/swept parents and never the cross-owner PermissionError"
  - "By-convention parent_owner derivation extracted into ExecutionEngine._derive_parent_owner() (returns user_id or 'anon') so the cross-owner case is testable end-to-end via execute() while keeping RunSandbox keying byte-identical (D-05)"

requirements: [CTX-03, CTX-05]

# Metrics
metrics:
  duration: ~12 min
  tasks_completed: 2
  files_created: 2
  files_modified: 3
  completed: 2026-06-07
---

# Phase 2 Plan 03: Parent-Run Ownership Check (L16 / CTX-03 / INV-8) Summary

**Closed the L16 unenforced-ownership leak — the one substantive security fix of Phase 0B — with a small pure `assert_owns` helper raising `PermissionError` on a cross-owner `parent_run` seed, wired LEXICALLY ABOVE the graceful-degrade try so the denial propagates out of `execute()` instead of being swallowed; same-owner missing/swept parents still degrade gracefully (CTX-05 parity, full 0A suite green).**

## What was built

### Task 1 — `authz.py` + pure `assert_owns` (commit `f1f194c`)
- New `backend/agents/execution_engine/authz.py` following the lean `state_machine.py` pure-helper shape (module docstring, `from __future__ import annotations`, `logging`, module logger, a single free function).
- `assert_owns(owner_id, parent_run_id, parent_owner_id) -> None` raises `PermissionError` iff `parent_owner_id != owner_id`; the message names the owner, the parent run id, and the parent's owner. Pure string compare — **no** persistence/sandbox/IO access, so Phase 5 AUTHZ-02 relocates it as a mechanical MOVE (D-06 / INV-12).
- `"anon"` is treated as a **real owner** (D-04) — never a fallback that bypasses the check.
- 5 unit tests: same-owner allow, cross-owner deny, anon cross-owner deny, anon same-session allow, and a by-construction purity scan (parses the function body via `ast`, strips the docstring, asserts no I/O tokens).

### Task 2 — wire the gate + record L16 (commit `d91e4d7`)
- `engine.py`: `from agents.execution_engine.authz import assert_owns` at module top; the call wired INSIDE `if parent_run_id:` and **lexically above** the existing `try:` at the parent_run seed block (D-07). The broad `except Exception as _seed_exc` is **unchanged** — it keeps catching only legitimate same-owner missing/TTL-swept parents and never the cross-owner `PermissionError`.
- `engine.py::_derive_parent_owner(user_id, parent_run_id)` — the by-convention 0B parent-owner derivation (`user_id or "anon"`, the SAME principal the parent sandbox is keyed under). Exposed as a method so the cross-owner path is exercisable end-to-end; Phase 5 replaces the body with a real store/workspace lookup.
- `RunSandbox(user_id or "anon", parent_run_id)` keying is **byte-identical** (D-05).
- 4 end-to-end tests driving the real `execute()` on `prototype_revision` (offline, scripted models): cross-owner denial (raises `PermissionError` out of `execute()` **and** asserts NOTHING was seeded — alice's run sandbox has no `spec.md`/`design.md`/`tasks.md`, bob's parent sandbox untouched), same-owner missing-parent graceful-degrade (no raise, run completes), anon cross-owner denial, anon same-session allow.
- `migration-ledger.md` L16 flipped `☐ → ☑` (CHECK row, gate cell records the denial test `tests/agents/test_parent_run_ownership.py`).
- `test_migration_ledger.py` phase-status test renamed `test_ledger_parses_and_phase0b_flips_l14_l16`, now asserts the `☑` set is exactly `{L14, L16}` (docstring updated). The grep ratchet (`_checked_grep_rows`) still classifies L16 as a CHECK row and skips it — flipping L16 did NOT arm a false grep ratchet; its enforcement lives entirely in the new denial test.

## Wiring point (D-07)

```
if parent_run_id:
    # L16 ownership gate — BEFORE the try (D-07)
    _parent_owner = self._derive_parent_owner(user_id, parent_run_id)
    assert_owns(owner_id=ectx.owner_id, parent_run_id=parent_run_id,
                parent_owner_id=_parent_owner)        # cross-owner → raises, propagates
    try:                                              # graceful-degrade (UNCHANGED)
        parent_sb = RunSandbox(user_id or "anon", parent_run_id)
        ...
    except Exception as _seed_exc:  # noqa: BLE001 — only same-owner missing/swept parents
        ...
```

## By-convention derivation note (for Phase 5)

In 0B the parent's owner is derived **by convention** — a parent sandbox is keyed on disk under `(user_id or "anon", parent_run_id)`, so the conventional parent owner is the same principal the caller keys this run with. This makes the same-owner assumption an explicit, testable HARD gate without changing keying. **Phase 5 (AUTHZ-02)** replaces `_derive_parent_owner` with a real store/workspace lookup of the parent run's recorded `owner_id` and **relocates `assert_owns` into the store-layer scoped-query helper as a MOVE** (the D-06 seam this plan ships).

## Deviations from Plan

None — plan executed exactly as written. Two discretionary points the plan left open were resolved as recommended: (1) denial exception = builtin `PermissionError`; (2) `assert_owns` home = new `authz.py`. One small, in-scope refinement: the cross-owner end-to-end "nothing seeded" assertion was strengthened to read alice's run sandbox directly (by threading an explicit `run_id`) and confirm `spec.md`/`design.md`/`tasks.md` are absent — a stronger guarantee than only checking the parent is untouched.

## Gate results

- `cd backend && python3.11 -m pytest tests/agents/test_parent_run_ownership.py -v` → **9 passed** (5 unit + 4 e2e).
- `cd backend && python3.11 -m pytest tests/agents/test_migration_ledger.py -v` → **4 passed, 1 skipped** (L14 ratchet green; L16 CHECK row skipped by the grep ratchet; CHECK-row classification green; phase-status {L14, L16} green; non-vacuity guard green).
- `cd backend && python3.11 -m pytest tests/agents/ -q` → **278 passed, 18 skipped** (CTX-05 parity preserved; +9 passed / +1 skipped vs the 269/17 baseline = exactly the 9 new ownership tests + the 1 new L16 CHECK-row skip). Revision snapshots hit the graceful-degrade path, not the denial path — cross-owner is a brand-new path no 0A snapshot exercises, so raising is not a CTX-05 violation.
- `cd backend && python3.11 -m pytest tests/unit/test_execution_engine.py tests/unit/test_revision_intelligence.py -q` → **16 passed** (live revision + engine units unaffected).
- Acceptance greps: `def assert_owns` → 1; I/O tokens in `authz.py` → 0; engine/factory imports in `authz.py` → 0; `assert_owns(` in `engine.py` → 1; `RunSandbox(user_id or "anon", parent_run_id)` in `engine.py` → 1 (keying byte-identical).

## Requirements

- **CTX-03** (explicit cross-owner parent-run ownership check; cross-owner rejected, same-owner degrade preserved, anon is a real owner) — **met**.
- **CTX-05** (no behavior change on existing paths) — **met** (full 0A suite green; same-owner graceful-degrade byte/semantic-identical).

## Ledger / orchestrator coordination

- **L16** → `☑` (recorded with its denial test `tests/agents/test_parent_run_ownership.py`; stays a CHECK row, no grep ratchet armed).
- **L14** stays `☑` (untouched).
- **D1** stays `☐` (deferred — `_handle_revision` is the live `run_revision` handler; not touched).
- Phase-status test updated to assert `{L14, L16}` as required.

## Known Stubs

None. `assert_owns` is fully wired and enforced; the by-convention `_derive_parent_owner` is an intentional, documented 0B convention (not a stub) that Phase 5 AUTHZ-02 replaces with a real store lookup.

## Self-Check: PASSED

- `backend/agents/execution_engine/authz.py` — FOUND
- `backend/tests/agents/test_parent_run_ownership.py` — FOUND
- `.planning/phases/02-executioncontext-ownership-0b/02-03-SUMMARY.md` — FOUND
- commit `f1f194c` (Task 1) — FOUND
- commit `d91e4d7` (Task 2) — FOUND
