---
phase: 05-typed-artifacts-persistence-ownership-1b
plan: 04
subsystem: engine
tags: [execution-engine, artifacts, persistence, ownership, scoped-store, artifact-graph, run-events, langchain-deepagents, websocket]

# Dependency graph
requires:
  - phase: 05-01
    provides: ArtifactGraph + ArtifactRef typed substrate (write_ref/tree/consumed_for/lineage)
  - phase: 05-02
    provides: run_events / run_capabilities / artifact_refs tables (additive migration 0014)
  - phase: 05-03
    provides: default-deny ScopedStore helper (write_ref/get_ref/list_refs/append_event/get_run/create_workspace/record_capabilities/assert_owns)
provides:
  - "execute() entry sets a real DB owner principal (user_id or anon:<session_id>), default per-run workspace, one run_capabilities row (runtime=langchain_deepagents), and a per-run ArtifactGraph"
  - "decoupled disk principal (ctx.disk_principal = user_id or 'anon') keeps RunSandbox/create_runner disk paths byte-identical (byte-identity guard CTX-05)"
  - "single per-run monotonic seq + uuid event_id stamped at the execute() emit boundary, persisted to run_events via the ScopedStore sink"
  - "typed ArtifactRefs dual-written (in-mem ArtifactGraph + best-effort artifact_refs DB) ALONGSIDE the still-live accumulated_outputs mirror"
  - "engine reads (consumes routing, context sources, build-loop seeds, prototype-build current_html) migrated to typed-first reads with mirror fallback"
  - "websocket reconnect clarifications read owner-scoped via ScopedStore ownership gate (T-5-IDOR)"
  - "seq/event_id stripped from the 0A characterization multiset so semantic-event parity holds (INV-3)"
affects: [05-05, 05-06, workflow-runtime-kernel]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Strangler dual-write: typed graph + DB written alongside the live mirror; mirror stays source-of-truth until parity-gated deletion (05-06)"
    - "Typed-first read with documented mirror fallback (_latest_typed_content / _filter_consumed_outputs)"
    - "Single emit-boundary stamping sink for per-run seq/event_id (one chokepoint, not the ndjson adapter)"
    - "Decoupled disk principal vs DB principal to preserve byte-identity while introducing a real scoped owner"
    - "Best-effort persistence: DB write failures degrade (log) and never perturb deliverable bytes / event stream"

key-files:
  created:
    - backend/tests/unit/test_run_events.py
  modified:
    - backend/agents/execution_engine/context.py
    - backend/agents/execution_engine/engine.py
    - backend/app/api/websocket.py
    - backend/tests/agents/characterization/_normalize.py
    - backend/tests/unit/test_agent_input_event.py

key-decisions:
  - "D-09 anon source: ctx.owner_id = user_id or anon:<session_id> (session-scoped isolation); ctx.disk_principal = user_id or 'anon' (UNCHANGED disk keying — byte-identity guard)"
  - "D-11: introduce exactly ONE monotonic counter at the execute() emit boundary; NO DB-side MAX(seq)+1 / Postgres sequence; NOT tapped in ndjson_adapter.py"
  - "D-01 kind mapping: producer agent id → ARTIFACT_KINDS for the persisted row; consumes ROUTING stays id-based so an unmapped agent still routes correctly"
  - "L16 assert_owns wrapped: PermissionError propagates (cross-owner denial); other store errors degrade like a same-owner missing/TTL-swept parent (CTX-05 parity — the prior pure predicate never touched the DB)"
  - "websocket clarifications: ownership-gated via ScopedStore.get_run; the clarifications PAYLOAD stays in the thin store this plan (full dual-write of clarifications is a later increment); the typed store is the OWNERSHIP gate on the read"
  - "_handle_revision thin-store reads left on the thin store (mirror/thin-store alive until 05-06); cross-owner parent reads gated by assert_owns above the graceful-degrade try"

patterns-established:
  - "Dual-write strangler: typed substrate is the live handoff; mirror is the fallback until parity proves the cutover (deletion 05-06)"
  - "0A parity preservation via _VOLATILE_STRIP_KEYS additions for newly-introduced volatile fields (seq, event_id)"

requirements-completed: [ART-01, ART-03, AUTHZ-01, AUTHZ-02, AUTHZ-03, PERSIST-02, PERSIST-03, CAPRUN-01]

# Metrics
duration: ~35min (continuation reconcile + verify + commit)
completed: 2026-06-08
---

# Phase 05 Plan 04: Typed Substrate + Persistence Wiring Summary

**Wired the typed ArtifactGraph + run_events durable log + scoped owner/workspace/capabilities into the engine via a dual-write strangler — deliverables stay byte-identical and the 0A semantic-event snapshot is unperturbed (INV-3 held across all 5 characterization pipelines).**

## Performance

- **Duration:** ~35 min (continuation agent: reconcile in-flight Task 3, prove parity, commit remainder)
- **Completed:** 2026-06-08
- **Tasks:** 3 (Tasks 1 & 2 committed by the interrupted run; Task 3 reconciled + finished + committed here)
- **Files modified:** 5 (+1 created: test_run_events.py)

## Accomplishments

- **Task 3 finished:** typed `ArtifactRef`s dual-written via `_dual_write_artifact` (in-mem `ctx.artifacts` graph + best-effort `artifact_refs` DB through the per-run `ScopedStore`) at every genuine producer site (agent output, gate-edited output, per-task build HTML, fix-loop HTML when changed, error placeholder), ALONGSIDE the still-live `accumulated_outputs` mirror.
- **Engine reads migrated to the typed graph** via `_latest_typed_content` (typed-first, mirror-fallback) and a re-signatured `_filter_consumed_outputs` / `_build_context_sources`: consumes routing, agent_input context sources, build-loop plan task list, `_seed_build_inputs` spec.md/tasks.md, and prototype-build `current_html`. Build scratch keys (`_build_task_number`/`_build_task_total`) deliberately kept on the mirror (NOT artifacts).
- **websocket.py reconnect clarifications read owner-scoped** through `ScopedStore.get_run` (T-5-IDOR mitigation); the literal `retrieve_latest("clarifications")` is gone (kind parameterized + ownership-gated).
- **INV-3 parity proven GREEN:** 0A characterization suite — 10 snapshots across prototype / prototype_revision / od_prototype / od_ppt / app_builder — byte-identical deliverables + semantic-event parity, with `seq`/`event_id` confirmed in `_VOLATILE_STRIP_KEYS`.

## Task Commits

1. **Task 1: ExecutionContext + execute() entry wiring + disk-principal decouple** — `f392b07` (feat) *(interrupted run)*
2. **Task 2: per-run seq/event_id sink + run_events persist + strip-keys** — `35d7cf6` (feat) + `14b60e7` (test) *(interrupted run)*
3. **Task 3: dual-write typed ArtifactRefs + read/clarifications migration** — `3584a35` (feat) *(this run)*

**Plan metadata / deferred note:** `64ebe8f` (docs — deferred lint)

_Note: Tasks 1 & 2 were committed by an earlier interrupted executor; verified present in git log and reconciled. Task 3 source + its read-migration test change were committed atomically here._

## Files Created/Modified

- `backend/agents/execution_engine/context.py` — `ExecutionContext` gained `artifacts: ArtifactGraph`, `workspace_id`, `disk_principal`; owner_id upgraded to the DB principal (Task 1).
- `backend/agents/execution_engine/engine.py` — entry owner/workspace/capabilities/artifacts wiring (T1), seq/event_id sink + run_events persist (T2), dual-write helpers + typed-first read migration + L16 graceful-degrade wrap (T3).
- `backend/app/api/websocket.py` — reconnect clarifications read ownership-gated via ScopedStore (T3).
- `backend/tests/agents/characterization/_normalize.py` — `seq`/`event_id` added to `_VOLATILE_STRIP_KEYS` (T2).
- `backend/tests/unit/test_run_events.py` — PERSIST-03 durable-log coverage (created, T2).
- `backend/tests/unit/test_agent_input_event.py` — re-signatured `_ectx` + seeds the typed graph (read-migration consequence, T3).

## Decisions Made

See `key-decisions` frontmatter. Headline: dual-write strangler keeps the mirror as source-of-truth (deletion deferred to 05-06); the typed graph is the live handoff the reads now prefer.

## Deviations from Plan

### Reconciliation adjustments (continuation)

**1. [Rule 3 - Blocking consequence] `test_agent_input_event.py` re-signatured to the migrated helper API**
- **Found during:** Task 3 (read-migration)
- **Issue:** `_build_context_sources` / `_filter_consumed_outputs` signatures changed (now take `ectx` and read from `ctx.artifacts`), so the existing unit test's calls no longer matched.
- **Fix:** Updated `_ectx` to seed the per-run typed `ArtifactGraph` and rewired the three `_build_context_sources` call sites; behavioral assertions unchanged.
- **Files modified:** backend/tests/unit/test_agent_input_event.py
- **Verification:** `tests/unit/test_agent_input_event.py` — 7 passed.
- **Committed in:** `3584a35`

**2. [Plan-action narrowing] clarifications PAYLOAD kept in the thin store; ScopedStore used as the OWNERSHIP gate**
- **Found during:** Task 3 (websocket clarifications rewire)
- **Issue:** The clarifications payload is not yet dual-written into `artifact_refs` (its write site is `clarify_engine.py`, a later increment). A pure payload read off the typed store would return nothing.
- **Fix:** Owner-scope the read via `ScopedStore.get_run` (run the user does not own → None → no read), satisfying the T-5-IDOR mitigation and removing the literal `retrieve_latest("clarifications")` while the payload remains in the still-live thin store (alive until 05-06).
- **Files modified:** backend/app/api/websocket.py
- **Verification:** `grep retrieve_latest("clarifications")` returns 0; HITL half (`submit_questionnaire`/`approve_review`/store resume+review events) intact.
- **Committed in:** `3584a35`

**3. [Plan-action deferral] `_handle_revision` thin-store reads left on the thin store**
- **Found during:** Task 3
- **Issue:** Plan action text suggested migrating `_handle_revision`'s `retrieve_latest`/`list_by_type` reads to `ScopedStore`. The phase-critical constraint keeps the mirror/thin-store alive until 05-06, and Task 3's acceptance criteria only require `_handle_revision` to still exist + the cross-owner gate.
- **Fix:** Left `_handle_revision` reads on the thin store; the cross-owner threat (T-5-SEED) is mitigated by `assert_owns(parent_run_id)` wired above the graceful-degrade try in Task 1. Full migration/deletion is 05-06.
- **Verification:** `_handle_revision` definition present; characterization (incl. prototype_revision) GREEN.
- **Committed in:** n/a (intentional non-change)

---

**Total deviations:** 2 reconciliation fixes + 1 intentional deferral. All consistent with the plan's strangler/byte-identity constraints. No scope creep; mirror NOT deleted.

## Issues Encountered

- **Pre-existing environmental test failures (out of scope, NOT chased):** `tests/unit/test_logout.py` (7 — "Self-registration is disabled" → 403, confirmed) and `tests/unit/test_pipeline_cancel.py` (1 — expired AWS Bedrock token). Both predate this plan and are unrelated to the typed-substrate wiring.
- **Pre-existing ruff lint** in `_normalize.py` (B905) and `websocket.py:619` (B023) logged to `deferred-items.md` per the SCOPE BOUNDARY rule.

## Verification Results

- `tests/agents/test_characterization_*.py` — **10 passed** (byte-identity + semantic-event parity, all 5 pipelines).
- `tests/unit/test_run_events.py` + `tests/agents/test_artifact_graph.py` + `tests/agents/test_parent_run_ownership.py` + `tests/unit/test_agent_input_event.py` — **33 passed**.
- `cd backend && lint-imports` — **exit 0** (3 contracts kept, 0 broken).
- Broad sweep `tests/agents/ tests/unit/` — **928 passed, 19 skipped**, only the 2 known environmental suites failed (8 tests). No new failures.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The typed graph is now the live read handoff; the mirror + thin store remain as fallback. **05-06** can perform the parity-gated DELETION of the `accumulated_outputs` mirror and the thin store (INV-3/INV-12 — no dual implementations after that increment).
- **05-05** (artifact/run API endpoints) can read the persisted `run_events` / `artifact_refs` / `run_capabilities` rows produced by this wiring.
- Clarifications payload dual-write into `artifact_refs` (from `clarify_engine.py`) remains a later increment; the read is already ownership-gated.

## Known Stubs

None that block the plan goal. The clarifications payload remaining in the thin store (read ownership-gated) is the documented strangler state, resolved when its write site dual-writes in a later increment; the mirror/thin-store retention is the sanctioned temporary duplication removed in 05-06.

## Self-Check: PASSED

All created/modified files present on disk; all 5 plan commits (`f392b07`, `35d7cf6`, `14b60e7`, `3584a35`, `64ebe8f`) present in git log.

---
*Phase: 05-typed-artifacts-persistence-ownership-1b*
*Completed: 2026-06-08*
