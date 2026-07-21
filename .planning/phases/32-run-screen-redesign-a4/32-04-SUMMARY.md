---
phase: 32-run-screen-redesign-a4
plan: 04
subsystem: engine
tags: [sc-001, review-gate, characterization-goldens, deepagents, kan-101]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign-a4 (03/prior waves)
    provides: the redoable/_VOLATILE_STRIP_KEYS precedent + _artifact_kind_for kind resolver
provides:
  - "review_gate_ready.data now carries a generic, name-free update_specs_eligible: bool + artifact_kind: str"
  - "Structural (kind-based) eligibility derivation the FE can drive the Update-the-Specs affordance off — zero prototype-* literal"
  - "Both new keys added to _VOLATILE_STRIP_KEYS so the 5 characterization goldens stay byte-identical"
affects: [run-screen FE plans (05/06/08), ReviewGatePanel, InlineGateActions, KAN-101]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SC-001 name-free discriminator: stamp a declared flag derived structurally from _artifact_kind_for, never an agent-id literal, mirroring redoable exactly"
    - "Golden-neutral additive payload key: add to _VOLATILE_STRIP_KEYS and prove byte-identity (no fixture regen)"

key-files:
  created:
    - backend/tests/agents/test_sc001_gate_flag.py
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/tests/agents/characterization/_normalize.py

key-decisions:
  - "_UPDATE_SPECS_ELIGIBLE_KINDS = {spec, task_list, summary}: the analyze/spec/plan gate kinds. summary is included because prototype-analyze is unmapped in _AGENT_KIND_MAP and falls back to summary (D-01), so excluding it would silently drop the analyze gate's Update-Specs affordance and break current FE behavior."
  - "artifact_kind defaults to \"\" on the declared path (mirroring redoable's False default) and the key is ALWAYS present so the FE reads a stable shape."
  - "Eligibility computed at BOTH inline call sites (pending-revision re-open + general live human gate) from the same _ek = _artifact_kind_for(spec) the branches already use; declared/user gates never pass the flag → default False."

patterns-established:
  - "Name-free gate discriminator: FE affordances key on declared payload flags derived from structural artifact-kinds, not workflow/agent-id string literals (SC-001)."

requirements-completed: [SC-2]

# Metrics
duration: 22min
completed: 2026-07-08
---

# Phase 32 Plan 04: SC-001 Name-Free Update-Specs Discriminator Summary

**review_gate_ready.data now carries a generic, structurally-derived update_specs_eligible + artifact_kind (mirroring the redoable precedent) so the FE drops the prototype-analyze/prototype-specify agent-id literal — with the 5 characterization goldens proven byte-identical.**

## Performance

- **Duration:** ~22 min
- **Started:** 2026-07-08
- **Completed:** 2026-07-08
- **Tasks:** 2 (TDD: RED test → GREEN stamp+strip)
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- Closed the SC-001 literal leak AT ITS SOURCE: the engine now supplies a declared, name-free `update_specs_eligible`/`artifact_kind` discriminator on `review_gate_ready.data`, so plans 05/06/08 can drive KAN-101's Update-the-Specs affordance off the payload flag instead of matching the `prototype-analyze`/`prototype-specify` agent-id string.
- Eligibility is derived STRUCTURALLY from `_artifact_kind_for(spec)` via a new `_UPDATE_SPECS_ELIGIBLE_KINDS` frozenset ({spec, task_list, summary}) — no workflow/agent-id literal in the emit path (grep-clean; net-zero new prototype-* literal vs HEAD).
- Proved INV-3: added both keys to `_VOLATILE_STRIP_KEYS` and confirmed all 5 characterization goldens pass BYTE-identical with NO SNAPSHOT_UPDATE set and NO golden fixture in the diff.
- Runtime untouched (INV-13): metadata on an existing event only; `deep_agent_runner`/`create_deep_agent`/the agent loop were not touched; no new event type.

## Task Commits

Each task was committed atomically (TDD: test → feat):

1. **Task 1 (RED): failing test_sc001_gate_flag** - `62dea368` (test)
2. **Task 2 (GREEN): stamp update_specs_eligible + artifact_kind + strip keys** - `5797ee90` (feat)

## Files Created/Modified
- `backend/tests/agents/test_sc001_gate_flag.py` (created) - Pins: helper stamps the flag next to redoable (inline True, declared-path default False); eligibility derived structurally from `_artifact_kind_for` (spec/task_list/summary eligible; html_file/validation_report not); no prototype-* literal ties to eligibility; both keys in `_VOLATILE_STRIP_KEYS`.
- `backend/agents/execution_engine/engine.py` (modified) - `_run_review_gate` gains `update_specs_eligible: bool = False` + `artifact_kind: str = ""` params stamped into `.data` next to `redoable`; new `_UPDATE_SPECS_ELIGIBLE_KINDS` class constant; both inline analyze/spec call sites compute `_ek = _artifact_kind_for(spec)` and pass `update_specs_eligible=_ek in self._UPDATE_SPECS_ELIGIBLE_KINDS, artifact_kind=_ek`.
- `backend/tests/agents/characterization/_normalize.py` (modified) - Added `"update_specs_eligible"` and `"artifact_kind"` to `_VOLATILE_STRIP_KEYS` next to `redoable`, with the mirror-comment updated to name them.

## Verification Evidence

- 5 goldens + test_sc001: `19 passed, 1 warning in 35.19s` (no SNAPSHOT_UPDATE in env — confirmed).
- `git diff --name-only` (working tree, GREEN): exactly `engine.py` + `_normalize.py`; the RED commit added only the test file. NO `*.wsframes.json`/golden fixture, NO runner/factory/loader file.
- No new `prototype-analyze|prototype-specify|prototype-plan` literal added to engine.py (net-zero vs HEAD; the only additions to engine.py are behavioral code deriving eligibility from `_artifact_kind_for`).
- `deep_agent_runner`/`create_deep_agent`/agent loop untouched.
- `/opt/homebrew/bin/lint-imports`: `Contracts: 4 kept, 0 broken.`

## Decisions Made
- **Eligible kinds = {spec, task_list, summary}.** These are the artifact kinds of the three prototype gate agents (specify→spec, plan→task_list, analyze→summary via the D-01 fallback). `summary` is the catch-all fallback, so a genuinely-unmapped gating agent in a custom workflow would also read eligible — this is the intended SC-001 generalization ("custom prototype-like workflows get the affordance IFF the structural kind matches"), and build/validation gates (html_file/validation_report) are correctly excluded.

## Deviations from Plan

None - plan executed exactly as written. (One cosmetic hardening: the emit-helper docstring was reworded to avoid spelling the `prototype-analyze`/`prototype-specify` tokens, keeping the guardrail's "no new prototype-* literal" grep net-zero. This changed only a docstring — payload bytes and goldens unaffected.)

## Issues Encountered
None. The A1 assumption (adding the keys to `_VOLATILE_STRIP_KEYS` keeps goldens byte-identical) was proven empirically on first run — no golden drift, no fixture regeneration.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The backend half of SC-001 (KAN-101) is complete: the FE plans (05/06/08) can now read `review_gate_ready.data.update_specs_eligible` / `artifact_kind` and delete the `agentId === "prototype-analyze"` / `"prototype-specify"` / `"prototype-plan"` literals in `ReviewGatePanel.tsx` / `AgentThinkingTab.tsx`.
- The wiring props already exist on the FE (`InlineGateActions.tsx:50`, `RunChatLane.tsx:66` per RESEARCH §2).

## Self-Check: PASSED

- Files: all 4 (test_sc001_gate_flag.py, engine.py, _normalize.py, 32-04-SUMMARY.md) FOUND.
- Commits: 62dea368 (RED test), 5797ee90 (GREEN feat) FOUND.

---
*Phase: 32-run-screen-redesign-a4*
*Completed: 2026-07-08*
