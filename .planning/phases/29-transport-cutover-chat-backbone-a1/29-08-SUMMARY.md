---
phase: 29-transport-cutover-chat-backbone-a1
plan: 08
subsystem: engine
tags: [steering, chat, execution-engine, consume-once, context-injection, INV-3, SC-001, D-06, ND-11]

# Dependency graph
requires:
  - phase: 28-chat-contracts-guards-a0
    provides: "RESOLVED-DECISIONS.md (ND-11 = Phase-29 first design task; USER GUIDANCE in the strip marker family)"
  - phase: 07 (universal-runtime)
    provides: "the generic _compose_context_message injector + the redo_directive/spec_revision_context consume-once seam idiom"
provides:
  - "ND-11-SEAM-DECISION.md — the consume-once seam-unification (COEXIST) + steering thread-id policy decision record"
  - "ectx.steering_notes — a consume-once mid-run steering queue (list of {text, sticky}) on ExecutionContext"
  - "=== USER GUIDANCE === composition in _compose_context_message (read+clear during composition; sticky vs one-shot)"
  - "test_steering_seam.py — offline fault-injection proof that a steering note lands in the next dispatch"
affects: [29-09 mechanical-router, 29-02 chat-persistence, chat-backbone, steering, concierge]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Third consume-once injection seam sharing the generic injector + the F3 read/clear idiom (COEXIST, not unify — ND-11)"
    - "Read+clear DURING composition (not around the caller) for an externally/async-enqueued seam"
    - "Sticky-vs-one-shot queue semantics: one-shot dropped after one dispatch, sticky retained"

key-files:
  created:
    - ".planning/phases/29-transport-cutover-chat-backbone-a1/ND-11-SEAM-DECISION.md"
    - "backend/tests/agents/test_steering_seam.py"
  modified:
    - "backend/agents/execution_engine/context.py"
    - "backend/agents/execution_engine/engine.py"

key-decisions:
  - "ND-11: COEXIST — steering_notes is a generic THIRD consume-once seam; the two shipped seams (redo_directive, KAN-101 spec_revision_context) stay byte-stable (INV-3/LOCK-B)"
  - "Steering thread-id policy: NO fork, inject into the NEXT dispatch on the agent's base thread (no rollback) — sidesteps both the Redo-fork and the KAN-101 BASE-thread replay hazard"
  - "Consume-once clear lives INSIDE _compose_context_message (router enqueues async), keeping sticky notes and dropping one-shot ones"
  - "ND-9: steering-state across resume is server-derived from run_events (29-02); no new column/table in 29-08 (LOCK-B)"

patterns-established:
  - "Consume-once seam family: additive ectx scratch field + generic injector block, dormant-when-empty for INV-3 byte-parity"
  - "Delimited === USER GUIDANCE === block joins the chat-launch strip marker family (POR §6)"

requirements-completed: [CHAT-03]

# Metrics
duration: ~14min
completed: 2026-07-08
---

# Phase 29 Plan 08: Steering seam (ND-11 + === USER GUIDANCE ===) Summary

**Consume-once `ectx.steering_notes` queue that renders as a `=== USER GUIDANCE ===` block in the generic context injector at the next agent dispatch — sticky/one-shot semantics, kernel name-free, INV-3 goldens byte-identical — preceded by the ND-11 seam-unification decision record.**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-07-08 (execution session)
- **Completed:** 2026-07-08
- **Tasks:** 3
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- **ND-11 resolved in writing FIRST:** a decision record that decides COEXIST (steering_notes as a generic third consume-once seam, the two shipped seams left byte-stable), states the steering thread-id policy (no fork, next-dispatch on the base thread), reconciles the Redo `:redo{N}` fork vs KAN-101 BASE-thread replay divergence (KAN-101 unbounded-replay risk acknowledged + logged out-of-scope), and records the ND-9 resume tie-in.
- **The steering carrier + composition:** `ectx.steering_notes` (a `list` of `{text, sticky}` consume-once queue) mirrors the `redo_directive` field lifecycle; `_compose_context_message` renders pending notes as one `=== USER GUIDANCE ===` block at the next dispatch, then read+clears (one-shot dropped, sticky retained).
- **Offline fault-injection proof:** `test_steering_seam.py` (5 tests) drives `_compose_context_message` directly — note lands in the next dispatch + consumed once; sticky persists across dispatches while one-shot does not; golden-neutral when empty.
- **INV-3 / SC-001 held:** 5 characterization goldens byte/event-identical (no SNAPSHOT_UPDATE); banned-patterns gate green (no kernel name branch); lint-imports 4/0.

## Task Commits

Each task was committed atomically:

1. **Task 1: ND-11 seam-unification + thread-id decision record (FIRST)** — `e6ffebad` (docs)
2. **Task 2: ectx.steering_notes carrier + === USER GUIDANCE === composition** — `69c07de6` (feat)
3. **Task 3: offline fault-injection proof (test_steering_seam.py)** — `8c2f83c3` (test)

_Note: Task 1 (the decision record) was authored and committed BEFORE any engine/context edit, per the ND-11-first discipline._

## Files Created/Modified
- `.planning/phases/29-transport-cutover-chat-backbone-a1/ND-11-SEAM-DECISION.md` — the ND-11 COEXIST + steering thread-id decision record (created)
- `backend/tests/agents/test_steering_seam.py` — offline fault-injection proof, 5 tests (created)
- `backend/agents/execution_engine/context.py` — `steering_notes: list` consume-once carrier added after `redo_directive` (modified)
- `backend/agents/execution_engine/engine.py` — `=== USER GUIDANCE ===` composition block in `_compose_context_message` (read+clear consume-once, sticky-vs-one-shot) (modified)

## Verification Evidence

Offline, targeted invocations (`python3.11`, no venv; full pytest deliberately avoided — it hangs offline here):

- **5 goldens + steering seam** (`test_steering_seam.py` + 5 `test_characterization_*.py`, `-x -q`): **15 passed** in 35.56s (5 steering + 2 prototype + 2 od_prototype + 2 od_ppt + 2 prototype_revision + 2 app_builder). No `SNAPSHOT_UPDATE`; no golden fixture edited → the 5 goldens are byte/event-identical (INV-3 holds — steering dormant on golden runs).
- **Banned-patterns (SC-001/INV-1)** (`test_banned_patterns.py -x -q`): **11 passed** — no `if pipeline_type ==` / `spec.id ==` kernel branch introduced.
- **Import boundaries** (`/opt/homebrew/bin/lint-imports`): **4 kept, 0 broken**.
- **Steering seam standalone** (`test_steering_seam.py -x -q`): **5 passed** in 0.09s.

### LOCK-B confirmation (git diff --name-only)

The full change set for this plan is exactly the four allow-listed files:

```
.planning/phases/29-transport-cutover-chat-backbone-a1/ND-11-SEAM-DECISION.md
backend/agents/execution_engine/context.py
backend/agents/execution_engine/engine.py
backend/tests/agents/test_steering_seam.py
```

Forbidden-file check: **PASS** — `backend/app/api/websocket.py`, `backend/app/api/websocket_handoff.py`, and `frontend/src/hooks/useWebSocket.ts` are NOT in the diff. No `/ws/chat` handler touched, no deletion ratchet armed, no migration-ledger deletion row, zero new DB tables/columns.

## Decisions Made
- **COEXIST over unify (ND-11):** the three consume-once seams are semantically distinct (Redo = rollback+re-run same agent on a fresh thread; KAN-101 = sub-pipeline re-run looping to the same gate on BASE threads; steering = next-dispatch guidance, no rollback). Unifying would rewrite proven-byte-stable seams for zero functional gain and violate the additive/no-deletion LOCK-B posture. Rationale + evidence anchors in ND-11-SEAM-DECISION.md.
- **Steering = base-thread, next-dispatch, no fork:** a steering note injects into a not-yet-run dispatch (no prior checkpoint state to collide with), so it needs neither the Redo fork nor carries the KAN-101 replay risk.
- **Read+clear during composition:** unlike `redo_directive` (set/clear around the compose call in `_run_agent`), steering notes are enqueued externally/async by the 29-09 router, so the consume-once clear lives inside `_compose_context_message` (the key-link contract).

## Deviations from Plan

None - plan executed exactly as written. (Task 2 and Task 3 carry `tdd="true"`; executed as implement-then-prove since global `tdd_mode` is false and the offline proof is itself Task 3 — the goldens acted as the always-green INV-3 regression gate throughout.)

## Issues Encountered
None.

## Known Stubs
None — the carrier + composition are fully wired and exercised by the offline proof. The router that ENQUEUES steering notes (`propose_steering_note` / mechanical router) is the explicit next plan (29-09) per the objective; `steering_notes` is intentionally empty-by-default until then (the INV-3 dormancy the goldens rely on), not a stub.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The steering injection seam is live and offline-proven — 29-09 (mechanical router) can now enqueue steering turns onto `ectx.steering_notes` and they will land in the next agent's composed context.
- ND-11 thread-id policy is recorded for the router to honor (no fork for steering).
- Standing audit item carried forward (out of scope here): the KAN-101 BASE-thread unbounded-replay risk over many `update_specs` cycles — to be bounded/audited in 29-09 or the Phase 34 live pass.
- ND-9 resume re-hydration (server-derived from run_events) lands with 29-02/29-09; 29-08 is resume-safe by construction (dormant on an empty re-hydrated queue).

---
*Phase: 29-transport-cutover-chat-backbone-a1*
*Completed: 2026-07-08*
