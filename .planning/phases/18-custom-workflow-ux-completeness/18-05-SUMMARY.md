---
phase: 18-custom-workflow-ux-completeness
plan: 05
subsystem: docs
tags: [issues-register, requirements, implementation-register, wontfix, iss-015, iss-014, paper-trail]

# Dependency graph
requires:
  - phase: 18-custom-workflow-ux-completeness
    provides: "18-04 (ISS-014 composer deletion + AgentModelPicker relocate/delete decision) — referenced; not yet run at 18-05 time, so SUMMARY records the locked-preferred relocation + v2 fallback"
provides:
  - "ISS-015 dispositioned WONTFIX (by-design) in the issues register with crisp rationale + the v2/WF-DB-01 guardrail"
  - "ISS-014 deletion paper trail reconciled across REQUIREMENTS.md (API-06 + traceability) and IMPLEMENTATION-REGISTER.md (Phase-8 + Phase-12)"
affects: [phase-19, cluster-E-closeout, WF-DB-01-v2]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deletion-as-superseded paper trail: annotate the originating requirement (API-06) + impl-register carry-forward notes as RESOLVED, pointing at the deleting plan (18-04) and the reconciling plan (18-05)"

key-files:
  created:
    - .planning/phases/18-custom-workflow-ux-completeness/18-05-SUMMARY.md
  modified:
    - .planning/ISSUES-REGISTER.md
    - .planning/REQUIREMENTS.md
    - .planning/IMPLEMENTATION-REGISTER.md

key-decisions:
  - "ISS-015 = WONTFIX (by-design): the launch surface is the closed 6-tile CreationHub + the PPT/Prototype wizards; a generic manifest-driven picker is v2/WF-DB-01 and MUST read /api/workflows + a user_launchable flag, never a hardcoded name dropdown (the REJECTED hack ships broken template-gated buttons + exposes test fixtures)"
  - "ISS-014 API-06 reconciliation framed as deletion-as-superseded: only the orphaned palette-panel UI (WorkflowComposer/CapabilityPalette) is deleted; the /api/capabilities + API-02 contract and the live agent-composer stand — API-06 NOT marked removed"
  - "AgentModelPicker disposition recorded as locked-preferred relocation into the live AgentsPopup (final disposition deferred to the 18-04 SUMMARY, which had not run at 18-05 time)"

patterns-established:
  - "Cluster-E close-out: register/requirements/implementation-register must agree before a WONTFIX/superseded item is considered dispositioned"

requirements-completed: [ISS-015, ISS-014]

# Metrics
duration: 2min
completed: 2026-06-13
---

# Phase 18 Plan 05: ISS-015 WONTFIX + ISS-014 Doc Reconciliation Summary

**Dispositioned ISS-015 as WONTFIX (by-design) with the wizards+agent-composer launch-surface rationale and the v2/WF-DB-01 manifest-picker guardrail, and reconciled the ISS-014 capability-palette-composer deletion-as-superseded paper trail across REQUIREMENTS.md API-06 and the IMPLEMENTATION-REGISTER Phase-8/Phase-12 composer-routing notes — docs only, zero code.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-06-13T15:25:18Z
- **Completed:** 2026-06-13T15:27:05Z
- **Tasks:** 1
- **Files modified:** 3 (+1 SUMMARY created)

## Accomplishments

- **ISS-015 → WONTFIX (by-design):** flipped the OPEN status row in `.planning/ISSUES-REGISTER.md` to `WONTFIX (by-design) (18-05)` with the crisp rationale: the product launch surface is the hardcoded 6-tile `CreationHub.tsx:15-22` (closed launchable set); `od_ppt`/`od_prototype` go through the PPT/Prototype wizards (which must collect template + design-system — a bare picker structurally can't); bare `prototype`/`ppt` are template-gated-unreachable (D-13-06-a, `websocket.py:1344-1361`); `sample_*` are test fixtures; the custom-workflow need is met by the live agent-composer (ISS-014). Recorded the v2 guardrail: a user-facing named-manifest picker = WF-DB-01 (v2) and, if ever built, MUST read `GET /api/workflows` + a `user_launchable` flag — NOT a hardcoded dropdown of names (the REJECTED hack ships broken template-gated buttons + exposes test fixtures).
- **ISS-014 API-06 reconciliation:** annotated `REQUIREMENTS.md` API-06 (line 166) + its traceability row with a migration-ledger note — the capability-palette composer (`WorkflowComposer.tsx` + `CapabilityPalette.tsx`) is deleted-as-superseded by the live `AgentsPopup` agent-composer (deletion in 18-04); `/api/capabilities` + `test_capabilities_api.py` (API-02 contract + model catalog) RETAINED; model picker relocated into the live composer (or v2-carried per the 18-04 SUMMARY). API-06 deliberately NOT marked removed.
- **Implementation-register resolution:** marked the Phase-8 capability-palette note and the Phase-12 §1206 "separate composer-routing concern" (the dead `WaveTreePanel` mount in unrouted `WorkflowComposer.tsx`) as RESOLVED by Phase 18 / ISS-014 — the unrouted composer is deleted; the live mount stays in `DashboardLayout.tsx` (and 18-02 flex-budgets it).

## Task Commits

1. **Task 1: Record ISS-015 WONTFIX + reconcile the ISS-014 deletion docs** - `d92fe946` (docs)

## Files Created/Modified

- `.planning/ISSUES-REGISTER.md` - ISS-015 OPEN → WONTFIX (by-design) with rationale + v2 guardrail
- `.planning/REQUIREMENTS.md` - API-06 row + traceability row note the palette-composer deletion-as-superseded (API-02/`/api/capabilities` RETAINED)
- `.planning/IMPLEMENTATION-REGISTER.md` - Phase-8 capability-palette note + Phase-12 composer-routing concern marked RESOLVED by Phase 18 / ISS-014
- `.planning/phases/18-custom-workflow-ux-completeness/18-05-SUMMARY.md` - this summary

## Decisions Made

- **ISS-015 = WONTFIX (by-design)** — verbatim from the 18-CONTEXT LOCKED disposition; no code, the launch surface is intentionally closed.
- **API-06 framed deletion-as-superseded, NOT removed** — the API-02 `/api/capabilities` contract and the live agent-composer remain; only the orphaned palette-panel UI is deleted (18-04).
- **AgentModelPicker: recorded locked-preferred relocation + v2 fallback** — 18-04 had not run at 18-05 time (only 18-01/18-02 SUMMARYs existed), so the REQUIREMENTS annotation points the final disposition at the 18-04 SUMMARY rather than asserting it.

## Deviations from Plan

None - plan executed exactly as written.

The plan's read_first noted the "migration ledger" — the project's `specs/003-workflow-engine-decoupling/migration-ledger.md` (DEL-04) carries NO API-06/composer row, and the plan's `files_modified` lists only the three `.planning/*.md` docs. The migration-ledger note was therefore recorded inline on the REQUIREMENTS.md API-06 row (the requirement's own ledger annotation), keeping the edit within the plan's declared file set. This is a faithful read of the plan, not a deviation.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Cluster-E doc paper trail is consistent for ISS-015 (WONTFIX) and ISS-014 (deletion-as-superseded). The actual FE deletion + model-picker relocation lands in plan **18-04**; when 18-04 runs, confirm the REQUIREMENTS.md AgentModelPicker annotation matches its final relocate-vs-carry decision.
- Remaining Phase-18 plans: ISS-021 (generic deliverable renderer — 18-01 backend done; FE pending), ISS-014 deletion (18-04).

## Self-Check: PASSED

- `18-05-SUMMARY.md` exists on disk (FOUND).
- Task commit `d92fe946` present in git log (FOUND).
- Plan verification grep passes: WONTFIX in ISSUES-REGISTER.md, superseded in REQUIREMENTS.md, ISS-014 in IMPLEMENTATION-REGISTER.md.
- Diff is docs-only (3 `.planning/*.md` files; no source code).

---
*Phase: 18-custom-workflow-ux-completeness*
*Completed: 2026-06-13*
