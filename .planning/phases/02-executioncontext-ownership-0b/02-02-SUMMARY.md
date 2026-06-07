---
phase: 02-executioncontext-ownership-0b
plan: 02
subsystem: infra
status: complete (RE-SCOPED)
tags: [migration-ledger, ci-ratchet, spec-correction, rescope, revision]

# Dependency graph
requires:
  - phase: 02-executioncontext-ownership-0b (plan 02-01)
    provides: "ExecutionContext state-lift; L14 grep target (self._(od_context|completed_tasks|current_task_block|revision_|gate_agent_ids)) → 0 over backend/ source"
provides:
  - "Migration-ledger row L14 flipped to ☑ (deleting SHA 8b90fd2) — the L14 grep ratchet is now armed and enforced by CI"
  - "test_migration_ledger.py::_parse_rows fixed to split on UNESCAPED table pipes + un-escape \\| — alternation gate patterns (L14, and later L3/L10/L11) now reach grep -E intact instead of being truncated"
  - "Migration-ledger D1 row corrected: _handle_revision recorded as LIVE (run_revision handler), deletion VOIDED/deferred"
affects: [02-03, "Phase 2/7 (later ledger rows L1-L13/L15 with alternation patterns now flip correctly)"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Ledger gate cells holding grep alternations escape pipes as \\| for the markdown table; the parser un-escapes them before grep -E"

key-files:
  created:
    - ".planning/phases/02-executioncontext-ownership-0b/02-02-SUMMARY.md — this file"
  modified:
    - "specs/003-workflow-engine-decoupling/migration-ledger.md — L14 ☐→☑ (SHA 8b90fd2); D1 row corrected (LIVE, deferred) + ‡ finding note"
    - "backend/tests/agents/test_migration_ledger.py — _parse_rows pipe-escaping fix; renamed/reconciled phase-status test to assert only {L14} flipped"
    - ".planning/phases/02-executioncontext-ownership-0b/02-SPEC.md, 02-CONTEXT.md, 02-02-PLAN.md — CTX-04/D1 marked voided/deferred"
    - ".planning/REQUIREMENTS.md, .planning/ROADMAP.md — CTX-04 deferred; 02-02 re-scoped"
  NOT-modified:
    - "backend/agents/execution_engine/engine.py — _handle_revision RETAINED (live); no engine change in this plan"

requirements: [CTX-05]
requirements-deferred: [CTX-04]
---

# Plan 02-02 — SUMMARY (RE-SCOPED)

## Headline

The plan's premise was **factually wrong**. The gsd-executor correctly **blocked** before
deleting anything (zero changes, clean tree). On the user's decision, this plan was **re-scoped**
to deliver only its legitimate half (arm the L14 ratchet) and to **correct the spec defect**.

## The defect (CTX-04 / D1)

D1 / CTX-04 told this plan to delete `_handle_revision` as "dead code, superseded by inline
revision handling, never reached." It is **not dead**:

| Evidence | Location |
|----------|----------|
| Frontend **emits** `run_revision` | `frontend/src/components/layout/DashboardLayout.tsx:385` (`type: "run_revision"`, the PPT-revision feature) |
| Backend **handler** calls the method | `backend/app/api/websocket.py:625` — `run_revision` branch `await _rev_engine._handle_revision(...)` |
| Method definition | `backend/agents/execution_engine/engine.py:2156` |
| Dedicated test suite | `backend/tests/unit/test_revision_intelligence.py` (12 references) |
| 0A coverage of it | **none** — so "re-run 0A to prove it dead" is a false-green |

The inline `prototype_revision` pipeline (which the 0A snapshots *do* characterize) is a
**separate** mechanism from the `run_revision` → `_handle_revision` entrypoint. The spec
conflated the two. Deleting the method breaks PPT revision = a **CTX-05 behavior change**.
The `backend/CLAUDE.md` data-flow confirms revision is a live feature.

## What was delivered (re-scoped)

1. **L14 → ☑** in `migration-ledger.md` (deleting SHA `8b90fd2`, the 02-01 state-lift). The
   L14 grep ratchet is now armed and **green** (`self._(od_context|completed_tasks|current_task_block|revision_|gate_agent_ids)` → 0 in `backend/`).
2. **D1 row corrected** — reclassified from "dead, delete (0B)" to "LIVE `run_revision` handler;
   retain; deferred" with a CHECK gate (so it can never arm a false grep ratchet) and a `‡`
   footnote documenting the finding. **D1 stays `☐` and is NOT flipped.**
3. **`_parse_rows` bug fixed** (`test_migration_ledger.py`): it did a naïve `.split("|")`, which
   shredded the L14 gate cell on its own regex alternation pipes (`\|`), truncating the pattern to
   `gate_agent_ids)` → a false match on `list(gate_agent_ids)` in `live_harness.py`. Now it splits
   on **unescaped** pipes and un-escapes `\|` → `|`, so the full pattern reaches `grep -E`. L14 is
   the first alternation-pattern row to flip, so this latent Phase-1 bug surfaced now.
4. **Phase-status test reconciled**: `test_ledger_parses_and_all_phase1_rows_pending` →
   `test_ledger_parses_and_phase0b_flips_only_l14`, asserting the only `☑` row is `{L14}`.
5. **Spec/contract docs corrected**: SPEC.md (CTX-04 voided), CONTEXT.md, REQUIREMENTS.md
   (CTX-04 deferred), ROADMAP.md (success-criterion 3 + 02-02 re-scoped).

Also resolved an **environment** snag found during the spot-check: a stray gitignored
`backend/backend/.local/` (192 MB python3.13 pip-target, unused by the python3.11 test runtime)
vendored `alembic` whose `self._revision_map` false-matched the L14 `revision_` alternation. It
was removed (user-approved); CI was never affected (the dir is absent there).

## What was NOT done

- **`_handle_revision` was NOT deleted.** No `engine.py` change in this plan. Method retained, live.
- **D1 was NOT flipped to ☑** (it would arm a ratchet that real source legitimately violates).

## Gate results

- `cd backend && python3.11 -m pytest tests/agents/test_migration_ledger.py -v` → **4 passed**
  (L14 ratchet live & green; non-vacuity guard green; CHECK-row classification green; phase-status
  reconciliation green).
- `cd backend && python3.11 -m pytest tests/agents/ -q` → **269 passed, 17 skipped** (CTX-05 parity
  preserved — no engine change; the +1 pass / −1 skip vs 02-01 is exactly the now-live L14 ratchet
  parametrization).
- L14 grep over `backend/` source → **0**. D1 grep `_handle_revision` → 14 (the live method + caller
  + tests; correct, since D1 is retained).

## Requirements

- **CTX-05** (no behavior change) — met (0A green; no engine change).
- **CTX-01 / CTX-02** — already met by 02-01; the L14 ratchet that *enforces* them is now armed here.
- **CTX-04** — **DEFERRED** (voided in 0B). `_handle_revision` is live; deleting it needs a product
  decision to retire `run_revision` (a frontend + behavior change well beyond this backend phase).

## Follow-up for the user / product owner

Decide whether the `run_revision` PPT-revision path is being **retired** (then a future phase deletes
`_handle_revision` + the `app/api/websocket.py` handler + the `DashboardLayout.tsx` emitter + the
test suite, as a deliberate behavior change) or **kept** (then D1/CTX-04 is permanently dropped from
the 003 ledger). Until then D1 remains `☐` (deferred) and `_handle_revision` stays.
