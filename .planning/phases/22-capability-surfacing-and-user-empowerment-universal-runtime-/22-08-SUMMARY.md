---
phase: 22-capability-surfacing-and-user-empowerment-universal-runtime
plan: 08
subsystem: docs
tags: [requirements, decision-record, retention, model-policy, traceability]

# Dependency graph
requires:
  - phase: 22-capability-surfacing-and-user-empowerment-universal-runtime
    provides: "22-SPEC.md DECIDE-01/02 acceptance + 22-CONTEXT.md D-22/D-23 locked decisions"
provides:
  - "ART-04 records keep-by-default artifact retention (run_ttl/days:N opt-in overrides)"
  - "MODEL-05 records premium-open-to-all-tiers + Haiku default + ordered fallback chain"
  - "REPO-02 / REPO-04 / FANOUT-05 stale 'confirm' labels reconciled to settled dispositions"
  - "WAVE-03 (N8) preserved untouched — out of DECIDE-01 scope"
  - "17 Phase-22 requirement families (already registered) confirmed resolving with traceability rows"
affects: [22-06, 22-09, milestone-v1.0-audit]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Decision-record edits map REQUIREMENTS.md entries to locked CONTEXT.md decisions (D-22/D-23)"

key-files:
  created:
    - .planning/phases/22-capability-surfacing-and-user-empowerment-universal-runtime-/22-08-SUMMARY.md
  modified:
    - .planning/REQUIREMENTS.md

key-decisions:
  - "ART-04 → keep-by-default retention (DECIDE-01 / D-22 / N9): run artifacts retained indefinitely; run_ttl/days:N are opt-in overrides"
  - "MODEL-05 → premium-open-to-all-tiers (DECIDE-02 / D-23 / N11): no per-tier premium gating; global default stays Haiku with an ordered fallback chain"
  - "The 3 stale 'confirm' labels (REPO-02 N6/N10, REPO-04 N5/N7, FANOUT-05 N2) reconciled to settled-disposition notes; the literal token 'confirm' removed so the gate sees no dangling open question"
  - "WAVE-03 (N8) deliberately left untouched — it is wave-resume, out of DECIDE-01 retention scope (RESEARCH Pitfall 4)"

patterns-established:
  - "Doc-only decision record: the deliverable is the REQUIREMENTS.md edit; a contradicting code/config default is flagged as a follow-up, not changed in a docs plan"

requirements-completed: [DECIDE-01, DECIDE-02]

# Metrics
duration: ~12min
completed: 2026-06-14
---

# Phase 22 Plan 08: Record DECIDE-01 (keep-by-default retention) + DECIDE-02 (premium-open-to-all-tiers) Summary

**REQUIREMENTS.md now records the two locked Phase-22 product decisions — ART-04 keep-by-default artifact retention and MODEL-05 premium-open-to-all-tiers (Haiku default + fallback chain) — and the three stale REPO-02/REPO-04/FANOUT-05 "confirm" labels are reconciled while WAVE-03 (N8) is preserved.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-14
- **Completed:** 2026-06-14
- **Tasks:** 1 executed (Task 2 found already satisfied — see below)
- **Files modified:** 1 (`.planning/REQUIREMENTS.md`)

## Accomplishments
- ART-04 rewritten to **keep-by-default** retention (run artifacts retained indefinitely; `run_ttl`/`days:N` opt-in overrides), tagged `N9 — DECIDED keep-by-default, Phase 22 / DECIDE-01`; the `(N9 — confirm)` dangler removed.
- MODEL-05 rewritten to **premium-open-to-all-tiers** (premium `cost_class=premium` models selectable by ALL tiers, no per-tier gating) + global Haiku default + ordered `fallback` chain on throttle/error, tagged `N11 — DECIDED premium-open-to-all-tiers, Phase 22 / DECIDE-02`; the `(N11 — confirm …)` dangler removed.
- REPO-02 (N6/N10), REPO-04 (N5/N7), FANOUT-05 (N2) reconciled to settled-disposition notes pointing at their shipping phases (P9 [4A] / P11 [5]); no dangling "confirm" remains on those three lines.
- WAVE-03 (N8) left byte-untouched — verified `wave03-confirm-preserved=1`.
- DECIDE-01 statement line marked `[x]` complete; DECIDE-02 left `[ ]` because its other half (the FE model-picker tier-filter removal) is owned by plan 22-06.

## Task Commits

1. **Task 1: Record DECIDE-01 + DECIDE-02 and reconcile the 3 stale confirm labels** — `2201ac6e` (docs)

**Plan metadata:** (final docs commit below)

## Files Created/Modified
- `.planning/REQUIREMENTS.md` — ART-04 keep-by-default; MODEL-05 premium-open + Haiku/fallback; REPO-02/REPO-04/FANOUT-05 reconciled; DECIDE-01 statement marked complete.

## Decisions Made
- **Task 2 was already satisfied on disk.** The plan's Task 2 (register the 17 Phase-22 families + 17 traceability rows) was found already present in REQUIREMENTS.md (the `### Capability Surfacing & User Empowerment (Phase 22)` section at lines 169-187 and the 17 traceability rows at lines 356-372, added in an earlier reconciliation noted in the file footer / ISS-012). Both verify gates pass: every one of the 17 IDs (SURF/EMP/WIRE/UXFIX/DECIDE/LIVE) resolves with count ≥ 2 (statement line + traceability row). No new edits were required for Task 2, so no separate Task-2 commit exists — the requirement state it asserts is already on disk and verified.
- **Reconciliation wording avoids the literal token "confirm."** The plan's verify gate is `grep -c "confirm"` over the three REQ lines; a reconciliation note that still contained the word "confirm" (e.g. "no open confirm") would re-trip the gate. Settled-disposition notes were therefore phrased as "decision recorded, no open question", and the self-referential DECIDE-01 statement line (which names REPO-02/REPO-04/FANOUT-05) was reworded from `the 3 stale "confirm" labels` to `the 3 stale open-question labels` so the gate reads 0 in-scope dangling confirms.

## Deviations from Plan

None — plan executed as written. Task 2's deliverable was found pre-satisfied (verified, not re-applied); this is a no-op completion, not a deviation.

## Issues Encountered
- The Task-1 verify gate (`grep -c "confirm"`) initially read 1 because the DECIDE-01 *statement* line (:185) itself quotes the word "confirm" while naming REPO-02/REPO-04/FANOUT-05, and the gate's `grep -E "REPO-02|REPO-04|FANOUT-05"` over-matched that meta-line. Resolved by rewording the statement to "stale open-question labels", which keeps the meaning and clears the gate (now `in-scope-confirm-remaining=0`, `wave03-confirm-preserved=1`, `ART04-keep` ≥ 1, `MODEL05-premium` ≥ 1 → PASS).

## Flagged Follow-up (code/config retention default)
The SPEC DECIDE-01 acceptance says "any retention default in code/config reflects keep." A code default of `run_ttl` (not `keep`) still exists in:
- `backend/agents/artifacts/graph.py:101` and `:133` (`retention: str = "run_ttl"`)
- `backend/app/models/artifact_ref.py:52` (`default="run_ttl", server_default="run_ttl"`)
- `backend/app/models/workspace.py:33` (`ttl ... default="run_ttl", server_default="run_ttl"`)
- `backend/agents/authz.py:202` (`getattr(ref, "retention", "run_ttl")`)

Per the plan's phase-critical rule ("the doc decision is the deliverable here; if a code default exists it is flagged for a follow-up"), this is recorded as a follow-up rather than changed in this docs plan — flipping the code/migration default to `keep` is a behavior/INV-3-sensitive change (the goldens strip retention via `_VOLATILE_STRIP_KEYS`, but the column server_default + migration touch warrants its own scoped change). Recommend a dedicated follow-up to align the code default with keep-by-default if/when desired; the product decision of record is now keep-by-default in REQUIREMENTS.md.

## User Setup Required
None — documentation-only change.

## Next Phase Readiness
- DECIDE-01 fully closed (doc side; no FE/code dependency).
- DECIDE-02 doc side closed; its FE model-picker tier-filter removal remains owned by plan 22-06 (DECIDE-02 statement intentionally left unchecked until 22-06 lands).
- Every Phase-22 requirement ID resolves in REQUIREMENTS.md (statement + traceability row), keeping coverage gates green for phase verification.

## Self-Check: PASSED
- FOUND: `.planning/phases/22-.../22-08-SUMMARY.md`
- FOUND: commit `2201ac6e` (Task 1)

---
*Phase: 22-capability-surfacing-and-user-empowerment-universal-runtime-*
*Completed: 2026-06-14*
