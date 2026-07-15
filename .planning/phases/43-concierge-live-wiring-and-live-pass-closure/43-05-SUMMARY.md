---
phase: 43-concierge-live-wiring-and-live-pass-closure
plan: 05
subsystem: api
tags: [steering, per-turn-images, execution-engine, live-ectx-registry, chat, run_commands, ports-and-adapters, INV-12]

# Dependency graph
requires:
  - phase: 43-01
    provides: "run_commands.py POST /messages Concierge backend (CHANNEL_STEERING branch, _live_ectx_for_run stub, apply_turn_images call site)"
  - phase: 43-03
    provides: "engine.py execute() injected-callback pattern (milestone_sink) — no engine→app import edge"
  - phase: 29-chat-backbone
    provides: "chat_router.apply_steering / apply_turn_images seams; engine === USER GUIDANCE === steering drain; ectx.steering_notes queue"
  - phase: 30-image-input
    provides: "engine _drain_turn_images (pending_turn_images → one-shot turn_images_once); RunImagesProvider content-blocks"
provides:
  - "A.3: process-local live-ectx registry (run_id → ExecutionContext) in run_commands.py — _live_ectx_for_run resolves the RUNNING in-process ectx (no longer always None)"
  - "engine execute() live_ectx_register/live_ectx_unregister injected callback pair — registers the run's ectx at run start, unregisters in the wrapper finally (no leak)"
  - "CHANNEL_STEERING now drains BOTH the steering note (=== USER GUIDANCE ===) AND per-turn images through the ONE resolved live handle — closes DEF-29-09-1 + DEF-30-03-1 (INV-12: one registry, one seam)"
affects: [43-06-sse-cutover, 43-07-live-B2-steering, part-c-sse-cutover]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Process-local per-run registry (dict keyed by run_id) mirroring _PIPELINE_TASKS / _CANCEL_EVENTS; register at run start, unregister in the engine wrapper finally"
    - "Injected register/unregister callback pair into the kernel (LiveEctxRegister/LiveEctxUnregister) — no engine→app import edge (import-linter 4/0)"
    - "ONE live handle resolution drains multiple generic per-run queues (steering_notes + pending_turn_images) — INV-12 single seam"

key-files:
  created: []
  modified:
    - backend/app/api/run_commands.py
    - backend/agents/execution_engine/engine.py
    - backend/tests/unit/test_run_message_images.py
    - backend/tests/agents/test_steering_seam.py
    - backend/tests/agents/_scripted_model.py

key-decisions:
  - "The live-ectx registry is a plain module-level dict in run_commands.py (NOT websocket.py — LOCK-B), safe for the single-process asyncio runtime; keyed by run_id ONLY (SC-001/INV-1) so concurrent runs never cross-deliver"
  - "The engine registers via an INJECTED callback (mirrors 43-03 milestone_sink) — no engine→app import; register after ectx construction, unregister in the execute() wrapper finally (ALWAYS — normal/exception/GeneratorExit, no leak)"
  - "The pre-existing engine drains (=== USER GUIDANCE === steering block at _compose_context_message; _drain_turn_images one-shot image carrier) were already built + tested in Phase 29/30 — this plan supplies the MISSING live handle that populates ectx.steering_notes / ectx.pending_turn_images"
  - "CHANNEL_STEERING previously applied NEITHER the steering note NOR (against a resolvable handle) images; it now resolves the live ectx ONCE and applies apply_steering + apply_turn_images through it — the actual DEF-29-09-1/DEF-30-03-1 closure"
  - "The registrar is wired at the run_commands SSE/REST launch path (in files_modified); the WS run_pipeline launch (websocket.py, LOCK-B) wiring is the Part-C SSE cutover — the live B.2 Bedrock observation is deferred"

patterns-established:
  - "Injected process-local registry: kernel receives register/unregister as generic callables; the app owns the dict + lifecycle"

requirements-completed: [A.3]

# Metrics
duration: ~50min
completed: 2026-07-15
---

# Phase 43 Plan 05: Steering Live-Drain + Per-Turn Images (Live-Ectx Registry) Summary

**`_live_ectx_for_run` now resolves the RUNNING run's in-process `ExecutionContext` from a process-local run_id→ectx registry (the engine registers it at run start via an injected callback and unregisters on teardown — no leak), so a mid-run chat steering note drains onto the next agent dispatch as a `=== USER GUIDANCE ===` block AND a per-turn image reaches that same dispatch through the ONE resolved handle — closing DEF-29-09-1 and DEF-30-03-1 with a single registry, a single seam, and the 5 characterization goldens byte-identical.**

## Performance
- **Duration:** ~50 min
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- **Task 1 — live-ectx registry (`d9bfb43b`).**
  - `run_commands.py`: added the process-local `_LIVE_ECTX: dict[str, ExecutionContext]` registry plus `register_live_ectx` / `unregister_live_ectx`, and rewrote `_live_ectx_for_run(run_id)` from an unconditional `return None` to `return _LIVE_ECTX.get(run_id)`. Keyed by run_id only (SC-001/INV-1); the endpoint already owner-gates the run (404) BEFORE resolving the ectx, so a caller only ever reaches their own run's context (T-43-05-XINJECT).
  - `engine.py`: `execute()` gained the `live_ectx_register` / `live_ectx_unregister` injected callback pair (typed `LiveEctxRegister` / `LiveEctxUnregister` — generic callables, no app import). `_execute_impl` registers the run's `ExecutionContext` immediately after construction; the `execute()` wrapper's new `try/finally` ALWAYS unregisters (normal completion, exception, or early `GeneratorExit`) so the registry never leaks. Both callbacks default `None` → the seam is dormant for the goldens and every current caller.
  - Wired the registrar into the `run_commands` SSE/REST launch path. `CHANNEL_STEERING` now resolves the live ectx ONCE and applies BOTH `apply_steering(ectx, dispatch.note)` and `apply_turn_images(ectx, images)` through it — the actual DEF-29-09-1 (steering) + DEF-30-03-1 (per-turn image) closure. INV-12: one registry, one seam.
- **Task 2 — offline proof (`26a79801`).** The engine-side drains (`=== USER GUIDANCE ===` at `_compose_context_message`; `_drain_turn_images` one-shot image carrier) were ALREADY built + tested in Phase 29/30 — this plan proved the missing live handle end-to-end:
  - Registry unit tests (register→resolve identity, unregister no-leak, cross-run isolation / no cross-delivery, degrade-safe `None` for a non-live run, double-unregister safe).
  - A REAL scripted engine run (`_drive("prototype", live_ectx_register=…, live_ectx_unregister=…)`) proves the engine registers its ectx MID-RUN (resolvable via `_live_ectx_for_run`) and unregisters on teardown (registry empty).
  - REST end-to-end: a RUNNING-phase steering turn (text + image) posted to `POST /messages` lands the note on `ectx.steering_notes` AND the image on `ectx.pending_turn_images` via the live handle; a non-live run stays degrade-safe (200 + durable record, no crash).
  - Steering-seam integration: a note applied through the registry renders `=== USER GUIDANCE ===` on the next dispatch, consume-once.

## Task Commits
1. **Task 1: live-ectx registry — `_live_ectx_for_run` resolves the running ectx** — `d9bfb43b` (feat)
2. **Task 2: prove registry resolves + steering/image drain end-to-end** — `26a79801` (test)

**Plan metadata:** _(this commit)_ `docs(43-05)`

## Files Created/Modified
- `backend/app/api/run_commands.py` — `_LIVE_ECTX` registry + `register_live_ectx`/`unregister_live_ectx`; rewrote `_live_ectx_for_run`; `CHANNEL_STEERING` resolves the live ectx once and applies `apply_steering` + `apply_turn_images`; wired the registrar into the SSE/REST `engine.execute(...)` call; imported `apply_steering` + `typing.Any`.
- `backend/agents/execution_engine/engine.py` — `LiveEctxRegister`/`LiveEctxUnregister` type aliases; `execute()` + `_execute_impl()` gained the injected callback params; register after ectx construction; `try/finally` unregister in the `execute()` wrapper.
- `backend/tests/unit/test_run_message_images.py` — `TestLiveEctxRegistry`, `TestLiveEctxEngineSeam`, `TestSteeringAndImageReachLiveEctx`.
- `backend/tests/agents/test_steering_seam.py` — `test_note_via_live_registry_renders_guidance_on_next_dispatch`.
- `backend/tests/agents/_scripted_model.py` — `_drive` gained an optional `**execute_kwargs` passthrough (test infra).

## Verification Evidence
- `python3.11 -m pytest tests/agents/ -k characterization -q` → **10 passed, 1481 deselected** (~36s).
- `git diff --stat backend/tests/agents/characterization/golden/` → **EMPTY** (goldens byte-identical; steering/images fire on ZERO golden paths).
- `python3.11 -m pytest tests/agents/test_steering_seam.py tests/unit/test_run_message_images.py <5 characterization files> -q` (Task 2 verify) → **38 passed**.
- `python3.11 -m pytest tests/unit/test_execution_engine.py -q` → **13 passed** (execute() signature change safe).
- `/opt/homebrew/bin/lint-imports` → **4 kept, 0 broken**.
- Engine→app import edge: `grep -rn "app.api.run_commands" agents/execution_engine/` → **0** (register/unregister injected as callbacks).

## Threat Register Disposition (plan `<threat_model>`)
- **T-43-05-XINJECT** (mitigate): registry keyed by run_id; the endpoint owner-gates the run (404) before resolving the ectx → a caller only reaches their own run. Cross-run isolation tested (no cross-delivery). ✅
- **T-43-05-IMGCAP** (mitigate): images cap-validated by `_validate_images` at ingress BEFORE queueing; payload-transient (unchanged from 30-03). ✅
- **T-43-05-GUIDANCE** (accept): steering text is the user's own guidance to their own run; consume-once bounds replay. ✅
- **T-43-05-IMPORT** (mitigate): register/unregister injected as callbacks; import-linter 4/0. ✅
- **T-43-05-LEAK** (mitigate): unregister in the `execute()` wrapper finally (ALWAYS); no unbounded growth. Tested (registry empty post-run). ✅
- **T-43-05-SC** (accept): no new packages. ✅

## Deviations from Plan

### Scoping decision (not an auto-fix): CHANNEL_STEERING now applies the steering NOTE, and the live wiring is the SSE/REST path (WS launch = Part-C)
- **Engine drains pre-existed.** Task 2's `=== USER GUIDANCE ===` steering block and the `_drain_turn_images` one-shot image carrier were already built + tested in Phase 29/30 (`test_steering_seam` / `test_run_message_images`). The real gap was purely Task 1's live handle. Task 2 therefore proves the handle end-to-end rather than re-building the drain.
- **CHANNEL_STEERING note application added.** The mechanical `CHANNEL_STEERING` branch previously applied NEITHER the steering note (it relied on an ND-9 "re-derive from run_events" path that is NOT implemented in the engine) NOR images against a resolvable handle. Since the engine only reads `ectx.steering_notes`, the branch now calls `apply_steering(_live_ectx_for_run(run_id), dispatch.note)` — the plan's explicit `key_link` (`CHANNEL_STEERING → apply_steering via _live_ectx_for_run`). This is the actual behavioral closure of DEF-29-09-1, within the plan's declared scope.
- **Live wiring is the SSE/REST launch path.** The registrar is wired into `run_commands.py`'s `engine.execute()` (in files_modified). The WS `run_pipeline` launch (`websocket.py`, LOCK-B — not modified) will wire the SAME register/unregister pair at the supervised Part-C SSE transport cutover; that path is where the main prototype run launches, so the live Bedrock observation (B.2 — steering lands in the next agent's live prompt) is **Part-B/C deferred** (no offline Bedrock; do not fabricate a live run). The resume-path `_execute_impl` call (engine.py:6145) keeps the callbacks dormant — a Part-C follow-up if resumed runs must also register.
- **Test-infra extension (Rule 3 supporting).** Added an optional `**execute_kwargs` passthrough to the shared `_drive` harness so the engine-seam test can inject the register/unregister pair. Backward-compatible; no existing caller affected (goldens unchanged).

**Total deviations:** 0 auto-fixed bugs + documented scoping decisions above.
**Impact on plan:** Both tasks delivered; goldens byte-identical, lint 4/0. No scope creep.

## What is B.2-live-deferred
- **B.2** (mid-run steering lands in the NEXT agent's LIVE Bedrock prompt) requires the Part-C SSE transport cutover (`NEXT_PUBLIC_SSE_TRANSPORT` ON) + live Bedrock. Proven OFFLINE here: the registry resolves the running ectx, the CHANNEL_STEERING seam applies the note through it, and the engine drain renders `=== USER GUIDANCE ===` on the next dispatch. The live observation rides 43-06 (SSE mount/flip) + 43-07 (B.2 live check).
- **Per-turn image half of B.1** (DEF-30-03-1) is likewise offline-proven (image lands on the live `pending_turn_images` → one-shot carrier → next dispatch block); the live multimodal delivery rides 43-07 (B.1).

## Issues Encountered
None.

## Next Phase Readiness
- **43-06 (SSE cutover)** wires the same register/unregister pair at the WS/SSE live launch and flips the transport — the seam then goes live for the main run.
- **43-07** runs the B.2 (steering) + B.1 (per-turn image) live Bedrock checks against this handle.

## Self-Check: PASSED
- `backend/app/api/run_commands.py` — FOUND (modified).
- `backend/agents/execution_engine/engine.py` — FOUND (modified).
- `.planning/phases/43-concierge-live-wiring-and-live-pass-closure/43-05-SUMMARY.md` — FOUND.
- Commit `d9bfb43b` (Task 1) — FOUND. Commit `26a79801` (Task 2) — FOUND.
- Characterization: 10 passed, goldens byte-identical. Targeted: 38 passed. lint-imports 4/0. No engine→app import.

---
*Phase: 43-concierge-live-wiring-and-live-pass-closure*
*Completed: 2026-07-15*
