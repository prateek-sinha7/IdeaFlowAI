---
phase: 33-concierge-compaction-a5
plan: 05
subsystem: testing
tags: [manifest, compiler, concierge, chat-router, characterization, sc-001, inv-3, inv-5]

# Dependency graph
requires:
  - phase: 33-03
    provides: "route_chat_turn CHANNEL_CONCIERGE + ChatTurn.concierge opt-in marker + concierge_proposal event"
  - phase: 33-02
    provides: "chat:concierge capability reading getattr(compiled, chat, {})"
provides:
  - "WorkflowManifest.chat optional DATA field (INV-5) loaded via _optional_dict"
  - "CompiledWorkflow.chat carried verbatim by the compiler (manifest -> compiled propagation)"
  - "SC-001 throwaway-manifest lane+router+concierge proof + grep gate"
  - "INV-3 golden guards extended for concierge_proposal (5 goldens byte-identical)"
affects: [dynamic-composer, concierge, custom-workflows, milestone-close]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Manifest chat: block as pure DATA (INV-5) — carried, never branched on"
    - "SC-001 grep gate: assert a throwaway workflow name appears 0x in engine/router/concierge"

key-files:
  created:
    - backend/tests/agents/test_sc001_lane_router_concierge.py
  modified:
    - backend/agents/workflows/manifest.py
    - backend/agents/workflows/plan.py
    - backend/agents/workflows/compiler.py
    - backend/tests/agents/test_chat_event_neutrality.py
    - backend/tests/agents/test_phase3_cutover_verify.py

key-decisions:
  - "chat: compiles as pure DATA carried onto CompiledWorkflow.chat — no compiler control-flow (INV-5)"
  - "Propagating chat manifest->CompiledWorkflow required plan.py + compiler.py edits (Rule-3) — the compiler builds a fresh CompiledWorkflow and the Concierge reads getattr(compiled, chat, {})"
  - "_VOLATILE_STRIP_KEYS needed NO additions — 33-03 added no new pipeline_complete key; concierge_proposal never fires on goldens"

patterns-established:
  - "SC-001 name-freedom proven empirically by a tmp-scoped throwaway manifest + source-file grep gate"
  - "INV-3 goldens proven byte-identical with SNAPSHOT_UPDATE unset + git diff --stat clean"

requirements-completed: [SC-001, SC-4, D-05, INV-1, INV-3, INV-5]

# Metrics
duration: 35min
completed: 2026-07-09
---

# Phase 33 Plan 05: SC-001 + INV-3 Non-Negotiable Proof Summary

**A brand-new throwaway custom workflow gets lane + router + Concierge with ZERO engine/FE/orchestrator code — proven by a tmp-scoped manifest + grep gate, with the manifest `chat:` DATA block flowing to `CompiledWorkflow.chat` (INV-5) and the 5 characterization goldens byte-identical (INV-3).**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-07-09
- **Tasks:** 3
- **Files modified:** 6 (1 created, 5 modified)

## Accomplishments
- Added the optional `WorkflowManifest.chat` DATA field (INV-5) — loaded via `_optional_dict`, allow-listed in `_ALLOWED_TOP_KEYS`, with zero compiler control-flow keyed off it.
- Propagated `chat` verbatim onto `CompiledWorkflow.chat` so the shared Concierge's `getattr(compiled, "chat", {})` receives workflow-authored data (the SC-001 end-to-end loop).
- Authored the SC-001 proof: a throwaway `sc001_throwaway_wf` manifest routes identically through the name-free `route_chat_turn`, resolves the one shared `chat:concierge` impl, compiles its `chat:` block, and is read by the Concierge — with a grep gate asserting the name appears 0x in engine/router/concierge and no `pipeline_type==/spec.id==/workflow_name==` branch exists in the chat surface.
- Extended the INV-3 golden guards for `concierge_proposal` and proved the 5 goldens stay byte/event-identical with `SNAPSHOT_UPDATE` unset.

## Task Commits

1. **Task 1: manifest chat: DATA field + manifest->compiled propagation** - `b3edb1b6` (feat)
2. **Task 2: SC-001 throwaway-manifest proof + grep gate** - `11af97ba` (test)
3. **Task 3: INV-3 golden guards extended for concierge_proposal** - `033a2df2` (test)

## Files Created/Modified
- `backend/agents/workflows/manifest.py` - Added optional `chat: dict` field, `_ALLOWED_TOP_KEYS` entry, and `_optional_dict` load.
- `backend/agents/workflows/plan.py` - Added `chat: dict` field to `CompiledWorkflow` (Rule-3 propagation).
- `backend/agents/workflows/compiler.py` - Carry `chat=dict(getattr(manifest, "chat", {}) or {})` onto the compiled plan (Rule-3 propagation, pure data).
- `backend/tests/agents/test_sc001_lane_router_concierge.py` - NEW: 9 tests — routing, registry resolve, chat-data compile + concierge read, and the SC-001 grep gate.
- `backend/tests/agents/test_chat_event_neutrality.py` - Added `concierge_proposal` to `_CHAT_EVENT_TYPES` (fires on none of the 5 goldens).
- `backend/tests/agents/test_phase3_cutover_verify.py` - Added `concierge_proposal` to `_DOCUMENTED_EVENT_TYPES`.

## Decisions Made

### chat manifest -> compiled propagation path
The Concierge reads its workflow-authored suggestions/notes via `getattr(compiled, "chat", {})` where `compiled` is the `CompiledWorkflow` (`ctx.compiled`, set by the app layer). The `WorkflowCompiler.compile()` builds a **fresh** `CompiledWorkflow` object — a manifest-only `chat` field would dead-end and never reach the Concierge (`getattr` would always return `{}`). So the data flow is: `workflow.yaml chat:` → `WorkflowManifest.chat` (manifest.py, `_optional_dict`) → `CompiledWorkflow.chat` (compiler.py carries it verbatim: `chat=dict(getattr(manifest, "chat", {}) or {})`) → `ConciergeCapability._compose_system_prompt` (`getattr(compiled, "chat", {})`). This is pure data at every hop — no control-flow construct keys off `chat` anywhere (INV-5 grep clean).

### _VOLATILE_STRIP_KEYS needed no additions
33-03 introduced exactly ONE new event type — `concierge_proposal` — and reused `chat_reply` for answers; it added **no** new `pipeline_complete` keys. `concierge_proposal` carries `message_id` (already stripped) + `text` and fires ONLY on the chat lane, never on any of the 5 scripted golden streams. So `characterization/_normalize.py::_VOLATILE_STRIP_KEYS` required **no** change — `_normalize.py` was left untouched, and the goldens stay byte-identical.

### SC-001 grep-gate result
`grep -rc "sc001_throwaway_wf"` over `backend/agents/execution_engine/`, `backend/app/api/chat_router.py`, and `backend/app/agents/chat/concierge.py` returns **0** in every source path (the throwaway name lives only in the tmp fixture + the test itself). The `_NAME_BRANCH_RE` (`(pipeline_type|spec.id|workflow_name)\s*==`) finds **0** matches in the chat surface (router + concierge). SC-001/INV-1 holds: the kernel knows no workflow by name.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Propagate chat onto CompiledWorkflow (plan.py + compiler.py)**
- **Found during:** Task 1 / Task 2
- **Issue:** The plan's `files_modified` listed only `manifest.py` for the data field, but the Concierge reads `getattr(compiled, "chat", {})` off the `CompiledWorkflow`, which the compiler builds fresh. A manifest-only field would never reach the Concierge, making Task 2 acceptance #3 ("the compiled manifest exposes the chat block") and the SC-001 end-to-end proof impossible.
- **Fix:** Added `chat: dict = field(default_factory=dict)` to `CompiledWorkflow` (plan.py) and carried it verbatim in `WorkflowCompiler.compile()` (compiler.py) — pure data, no branch.
- **Files modified:** backend/agents/workflows/plan.py, backend/agents/workflows/compiler.py
- **Verification:** `CompiledWorkflow` has `chat` field (dataclasses.fields check True); INV-5 grep clean over manifest.py + compiler.py; test_sc001 `test_chat_block_compiles_as_data` + `test_concierge_reads_compiled_chat_data` pass.
- **Committed in:** `b3edb1b6` (Task 1 commit)

**2. [Scope Boundary] _normalize.py left untouched**
- The plan listed `characterization/_normalize.py` in `files_modified`, but no `_VOLATILE_STRIP_KEYS` addition was required (see Decisions). Left untouched — a gratuitous edit would violate small-diff discipline. Net change: `plan.py` + `compiler.py` added to the file set; `_normalize.py` removed.

---

**Total deviations:** 1 auto-fixed (Rule 3 - blocking) + 1 scope-boundary decision.
**Impact on plan:** The Rule-3 propagation is essential for correctness (SC-001 end-to-end). No scope creep — both edits are pure data pass-through. `test_chat_contract.py` untouched (INV-12); goldens untouched (INV-3).

## Issues Encountered
- **Pre-existing manifest test failures** (`test_manifest.py` / `test_manifest_parity.py`) fail identically on the clean baseline (9a81a0b3) and after 33-05 (74 passed on both). Unrelated to `chat:` — logged to `deferred-items.md`. Out of scope.
- **`tests/agents/characterization` collects 0 tests** — the characterization tests live at `tests/agents/test_characterization_*.py` (5 files), not inside the `characterization/` package dir. Ran the 5 explicitly (10 tests, all pass) to prove byte-identity.

## Verification Evidence
- `test_sc001_lane_router_concierge.py`: 9 passed.
- `test_chat_event_neutrality.py` + `test_phase3_cutover_verify.py`: 12 passed.
- 5 characterization pipelines: 10 passed (SNAPSHOT_UPDATE unset).
- `git diff --stat backend/tests/agents/characterization/golden/`: EMPTY (goldens byte-identical, INV-3).
- INV-5 grep (`if .*\.chat\b|chat ==|manifest\.chat and`) over manifest.py + compiler.py: 0 matches.
- SC-001 grep (`sc001_throwaway_wf`) over engine/router/concierge: 0 each.
- `grep -c concierge_proposal test_chat_event_neutrality.py`: 3.
- `lint-imports` (from backend/): 4 kept, 0 broken.
- Final wave gate (`test_registry_capabilities.py` + neutrality + cutover): 104 passed.

## Next Phase Readiness
- SC-001 / INV-1 / INV-3 / INV-5 are empirically proven — the milestone's non-negotiable core value holds.
- The manifest `chat:` field is live for custom workflows to author; the dynamic composer can expose it.
- LIVE-DEFERRED: none — this proof plan is fully offline-provable.

---
*Phase: 33-concierge-compaction-a5*
*Completed: 2026-07-09*

## Self-Check: PASSED

All created files exist; all 3 task commits (b3edb1b6, 11af97ba, 033a2df2) present in git log.
