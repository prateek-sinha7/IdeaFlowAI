---
phase: 13-live-verification-gap-closure
plan: 01
subsystem: engine
tags: [gates, hitl, streaming, async-generator, review-gate, websocket]

# Dependency graph
requires:
  - phase: 08-capability-gates
    provides: HumanGate/ApprovalGate registered gate capabilities + _evaluate_gates seam (WR-04 sentinel)
  - phase: 10-security
    provides: ApprovalGate D-03 first-exec memory + D-04 policy-snapshot payload
provides:
  - Streaming gate-evaluation protocol (evaluate_stream) on HumanGate + ApprovalGate
  - Streaming-aware engine._evaluate_gates that forwards gate events as produced
  - review_gate_ready reaches the execute() consumer BEFORE the gate awaits approval (F1 closed)
  - Handler-driving regression test for the declared-gate pause/approve/resume cycle
affects: [13-live-verification-gap-closure, live-verification, websocket]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Streaming gate protocol: evaluate_stream yields public event dicts as produced, then exactly one terminal GateOutcome (events=[] — no double emission)"
    - "evaluate() as thin collector over evaluate_stream (INV-12 single implementation)"
    - "Engine duck-types the streaming branch on getattr(gate, 'evaluate_stream') — no workflow/agent names (SC-001)"

key-files:
  created:
    - backend/tests/agents/test_declared_gate_streaming.py
  modified:
    - backend/agents/capabilities/gates/human.py
    - backend/agents/capabilities/gates/approval.py
    - backend/agents/execution_engine/engine.py

key-decisions:
  - "Streamed event dicts ride a non-halting 'pass' placeholder outcome; the definitive outcome follows as the WR-04 (None, outcome) sentinel — dispatch-loop contract unchanged"
  - "Approval gate's offline gate_wait_human event is streamed too, so the evaluate() collector reconstructs the exact pre-fix GateOutcome (events + detail)"
  - "Regression test approves only in response to review_gate_ready via store.set_review_response — the exact websocket.py approve_review call; verified to fail by 30s timeout against pre-fix code"

patterns-established:
  - "Streaming capability surface: a gate opts into streaming by exposing evaluate_stream; non-streaming gates (validation/security) keep the awaited path byte-identically"

requirements-completed: [F1]

# Metrics
duration: ~12min
completed: 2026-06-12
---

# Phase 13 Plan 01: Declared-Gate Streaming (F1) Summary

**Manifest-declared `gates:[human]` steps now stream `review_gate_ready` to the WS consumer while the run is paused — pause/approve/resume works from a real UI, closing UAT Gap 1 (F1)**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-11T22:26:05Z
- **Completed:** 2026-06-11T22:38:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- `HumanGate.evaluate_stream` + `ApprovalGate.evaluate_stream`: async generators that re-yield each public `run_human_gate` delegate event the moment it is produced (no list buffering), then yield a terminal `GateOutcome` with `events=[]` — so `review_gate_ready` propagates up the generator chain while `_run_review_gate` is suspended at its yield, BEFORE `await event.wait()`, matching the working inline path's ordering.
- `evaluate()` on both gates rewritten as a thin collector over `evaluate_stream` (INV-12 single implementation) — every non-streaming caller (incl. all 11 existing `test_gates.py` gate-contract tests) gets the byte-identical pre-fix contract, including the approval gate's D-03 short-circuit, D-04 payload, and offline `gate_wait_human` event + detail.
- `engine._evaluate_gates` streaming branch: duck-typed on `getattr(gate, "evaluate_stream", None)`; streamed dicts yield as `(event, "pass")` (non-halting placeholder), the terminal maps to the WR-04 `(None, outcome)` sentinel. Validation/security gates keep the await-then-yield path untouched. No workflow/agent-id literals (SC-001).
- Regression test drives the declared-gate path over the public `engine.execute()` generator with `gate_agent_ids=[]` (inline path silenced) and the REAL `_run_review_gate`: asserts ready arrives before any approval for its gate_key, approves via `store.set_review_response` only in response to ready, asserts both declared gated steps (specify, plan) pause and ready→approved ordering holds, and the run resumes to `pipeline_complete`.
- Empirically verified the test FAILS by bounded timeout (30.5s) against the pre-fix buffering code and passes in ~9s with the fix.

## Task Commits

Each task was committed atomically:

1. **Task 1: Stream declared-gate events through evaluate_stream + a streaming-aware _evaluate_gates** - `eaee864b` (fix)
2. **Task 2: Handler-driving regression test — ready received while paused, approve, resume** - `03d55a75` (test)

## Files Created/Modified

- `backend/agents/capabilities/gates/human.py` - `evaluate_stream` async-gen + `evaluate` collector (HumanGate)
- `backend/agents/capabilities/gates/approval.py` - same streaming restructure preserving D-03/D-04/offline semantics (ApprovalGate)
- `backend/agents/execution_engine/engine.py` - streaming branch in `_evaluate_gates` (duck-typed, inside the gate-never-aborts try/except)
- `backend/tests/agents/test_declared_gate_streaming.py` - F1 regression: ready-while-paused, approve, resume to pipeline_complete

## Decisions Made

- Streamed event dicts carry a non-halting `"pass"` placeholder outcome; only the terminal WR-04 sentinel carries the definitive outcome — the dispatch-loop `(event, outcome)` contract and halt semantics are unchanged.
- The approval gate's offline `gate_wait_human` event is streamed (then collected by `evaluate()`), keeping the offline no-handle contract (`events=[dict]`, `detail` set) byte-identical for awaited callers.
- The regression test reconstructs `gate_key` for `review_gate_approved` events from `f"{run_id}:{agent_id}"` (the approved event carries `agent_id`, not `gate_key`).

## Deviations from Plan

None - plan executed exactly as written. (One micro-adjustment within task scope: `ArtifactStore` has no pre-existing `store` attribute — the test's save/restore of the no-op store patch uses a `getattr` sentinel + `delattr` cleanup instead of a plain read-then-restore.)

## Issues Encountered

None. All verification green on first full run: 43 tests (test_gates.py 32 + new regression 1 + 5 characterization suites x2) pass; zero files under `tests/agents/characterization/golden/` modified (INV-3, no re-baseline); `/opt/homebrew/bin/lint-imports` 4 contracts kept.

## Known Stubs

None.

## Threat Flags

None — no new ingress surface; the streaming branch resolves gates from the same registry, and the approve path (`set_review_response`) is the unchanged websocket.py handler call (per the plan's threat register, all dispositions `accept`).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- ROADMAP Phase 13 criterion 1 holds at the engine boundary: a UI client receives `review_gate_ready` while the run is paused and approval resumes it — prototype-family UI runs no longer hang at specify.
- Plans 13-02..13-06 (remaining F2–F7 gap closures) can proceed; the streaming gate protocol is available for any gate capability that needs pre-await event visibility.

## Self-Check: PASSED

- 13-01-SUMMARY.md: FOUND
- backend/tests/agents/test_declared_gate_streaming.py: FOUND
- Commit eaee864b (Task 1): FOUND
- Commit 03d55a75 (Task 2): FOUND

---
*Phase: 13-live-verification-gap-closure*
*Completed: 2026-06-12*
