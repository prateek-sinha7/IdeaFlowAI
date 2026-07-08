---
phase: 30-uploads-multimodal-a2
plan: 03
subsystem: api
tags: [chat, multimodal, images, steering, execution-engine, run_events, sse]

# Dependency graph
requires:
  - phase: 29-run-chat-backbone
    provides: "POST /api/runs/{id}/messages chat_message path + chat_router.route_chat_turn/apply_steering + ectx.steering_notes consume-once seam"
  - phase: 30-uploads-multimodal-a2 (image spine, waves edw/frv/gvq)
    provides: "_validate_images ingress caps, _normalize_run_images, ectx.run_images carrier, RunImagesProvider input_provider, _compose_input_blocks injects gate"
provides:
  - "MessageCommand.images — per-turn image ingress on the Phase-29 /messages endpoint, cap-validated by the SHARED _validate_images (400 on violation, nothing queued)"
  - "chat_router.apply_turn_images() — the image analogue of apply_steering; normalizes + appends {mime_type,data} to ectx.pending_turn_images"
  - "ExecutionContext.pending_turn_images — the consume-once per-turn image queue (dormant by default)"
  - "engine _drain_turn_images() — drains pending_turn_images -> run_images before _compose_input_blocks at each dispatch (consume-once)"
  - "ND-10/LOCK-E no-persistence lock — per-turn images stamped retained:false with no bytes; never in sandbox/DB/run_events (locked by test)"
affects: [30-04 (client resize + ND-10 reopen placeholder), 33 (concierge), 34 (milestone-end live pass)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-turn multimodal steering: reuse the Phase-29 chat_message path + the run-entry image spine — a new capability rides existing seams with zero new route/table/migration"
    - "Consume-once injection-seam family: pending_turn_images joins steering_notes/redo_directive/spec_revision_context (drain-then-clear at the next dispatch)"

key-files:
  created:
    - "backend/tests/unit/test_run_message_images.py"
  modified:
    - "backend/app/api/run_commands.py"
    - "backend/app/api/chat_router.py"
    - "backend/agents/execution_engine/engine.py"
    - "backend/agents/execution_engine/context.py"
    - "backend/tests/unit/test_mechanical_router.py"

key-decisions:
  - "Live in-process ectx delivery is the SAME deferred piece as DEF-29-09-1 (no live-ectx registry exists) — the endpoint's apply_turn_images call is best-effort via _live_ectx_for_run (returns None today); the seam + engine drain are proven offline, live end-to-end delivery deferred to the milestone-end live pass"
  - "Per-turn images are cap-validated BEFORE persist/route (mirrors the launch path's pre-mint validation) so a cap violation leaves no chat_message row and nothing queued"
  - "The inline engine drain was extracted into an importable module-level _drain_turn_images(ectx) helper so the consume-once drain is unit-testable without a full _run_agent invocation"

patterns-established:
  - "apply_turn_images seam mirrors apply_steering exactly (best-effort no-op when the ectx attribute is absent; keyed on the generic queue only, SC-001/INV-1)"

requirements-completed: [UPLD-02]

# Metrics
duration: 20min
completed: 2026-07-08
---

# Phase 30 Plan 03: Per-Turn Image Carrier (UPLD-02 residue) Summary

**Images attached to an in-flight chat turn ride the Phase-29 `POST /api/runs/{id}/messages` path — cap-validated by the shared `_validate_images` ingress caps, queued via `apply_turn_images` onto `ectx.pending_turn_images`, and drained onto `ectx.run_images` at the next dispatch so an `injects:[images]` agent's HumanMessage carries the base64 content-blocks — staying payload-transient (ND-10, never persisted) and byte-identical dormant on golden runs (INV-3).**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-08
- **Tasks:** 2
- **Files modified:** 5 (4 modified + 1 created)

## Accomplishments
- Per-turn image ingress on the REUSED Phase-29 `/messages` endpoint (`MessageCommand.images`) — validated by the exact `_validate_images` caps the launch path uses (mime allow-list, ~3.75 MB/image, ≤20, ~8 MB aggregate, vision-model guard); a violation → 400 `invalid_image_input` before any persist/queue.
- `chat_router.apply_turn_images()` seam + `ChatTurn.images` — the image analogue of `apply_steering`, normalizing to `{mime_type,data}` and appending to the generic `ectx.pending_turn_images` queue (best-effort no-op when absent).
- Engine drain (`_drain_turn_images`) before `_compose_input_blocks` at each dispatch — consume-once: `pending_turn_images` → `run_images`, so each attached image reaches exactly the next dispatch's HumanMessage; dormant (empty) → `run_images` unchanged.
- ND-10/LOCK-E no-persistence lock: per-turn images stamped `retained:false` with NO bytes in the persisted `chat_message` row; no base64 anywhere in DB/run_events; images gone on replay/reopen (locked by test).

## Task Commits

Each task was committed atomically:

1. **Task 1: Per-turn image carrier (MessageCommand.images → validate → apply_turn_images → next dispatch run_images)** — `57f7a41d` (feat)
2. **Task 2: Tests — per-turn image delivery, ND-10 no-persistence lock, INV-3 dormancy** — `3682cb9c` (test)

_Note: Task 1 was a tdd-tagged production task; its inline drain was refactored into `_drain_turn_images` within the same commit (amended) for testability._

## Files Created/Modified
- `backend/agents/execution_engine/context.py` — added `ExecutionContext.pending_turn_images` consume-once scratch (image analogue of `steering_notes`; default-empty → dormant).
- `backend/app/api/chat_router.py` — `ChatTurn.images` + `apply_turn_images()` seam; added to `__all__`.
- `backend/agents/execution_engine/engine.py` — `_drain_turn_images()` module-level helper + inline call before `_compose_input_blocks`.
- `backend/app/api/run_commands.py` — `MessageCommand.images`; pre-route `_validate_images` gate (400 on violation); `retained:false` image refs in `_persist_chat_message`; `apply_turn_images` on the best-effort live handle in the steering branch; `_live_ectx_for_run` best-effort resolver (DEF-29-09-1 deferred wiring).
- `backend/tests/unit/test_run_message_images.py` — NEW, 11 tests (delivery + caps + ND-10 + INV-3).
- `backend/tests/unit/test_mechanical_router.py` — +3 `apply_turn_images` seam tests.

## Decisions Made
- **Live delivery deferred (DEF-29-09-1 parity):** no live-ectx registry exists, so the endpoint's `apply_turn_images` call is best-effort (`_live_ectx_for_run` → `None` today). The router seam + engine drain are proven offline; live end-to-end multimodal delivery is deferred to the milestone-end live pass (Phase 34), consistent with the 29-08/29-09 steering seam disposition and the project's defer-live-verification convention.
- **Validate before persist:** per-turn images are cap-checked before the `chat_message` row is written, so a rejection leaves no row and nothing queued.
- **Extracted `_drain_turn_images`:** the 3-line inline drain became an importable helper so the consume-once semantics are unit-testable without spinning up `_run_agent` + a scripted model.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking/testability] Added `ExecutionContext.pending_turn_images` field + extracted `_drain_turn_images` helper**
- **Found during:** Task 1 (carrier implementation)
- **Issue:** The plan's carrier requires a per-run scratch queue (`pending_turn_images`) that lives alongside `run_images`/`steering_notes` in `context.py` (not listed in `files_modified`), and the inline drain was not directly unit-testable.
- **Fix:** Added the `pending_turn_images` dataclass field to `ExecutionContext` (the same D-03 idiom as `steering_notes`) and extracted the drain into a module-level `_drain_turn_images(ectx)` helper called inline before `_compose_input_blocks`.
- **Files modified:** `backend/agents/execution_engine/context.py`, `backend/agents/execution_engine/engine.py`
- **Verification:** 39 target-file tests green; 15 characterization/steering goldens byte-identical.
- **Committed in:** `57f7a41d` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking/testability). No scope creep — the field is the carrier the plan's action mandates ("Initialize `pending_turn_images` alongside the existing run-entry `run_images`/`steering_notes` scratch"), and the helper is a pure refactor of the plan's inline drain.
**Impact on plan:** None on behavior — both are structural necessities for the declared carrier.

## Issues Encountered
None. The vision guard passed for valid images with a fake user because the default `BEDROCK_INFERENCE_PROFILE_ID` (`eu.anthropic.claude-haiku-4-5`) is a vision-capable catalog entry — the same reason the WS/REST launch image tests pass.

## Verification Evidence (OFFLINE)
- `python3.11 -m pytest tests/unit/test_run_message_images.py tests/unit/test_mechanical_router.py -q` → **39 passed** (11 new image + 28 router).
- 5 characterization goldens (prototype, od_prototype, prototype_revision, od_ppt, app_builder) + steering_seam → **15 passed**, byte/event-identical, **NO SNAPSHOT_UPDATE**, no golden fixtures changed (INV-3).
- Regression: `test_chat_messages_endpoint.py` + `test_image_ws_ingress.py` → **24 passed** (Phase-29 endpoint + image ingress intact).
- `/opt/homebrew/bin/lint-imports` → **4 kept, 0 broken**.
- Zero new tables / migrations. SC-001/INV-1: the carrier keys on the generic `pending_turn_images` queue only — no workflow name / `pipeline_type` / `spec.id`.

## Deferred to Live (Phase 34 milestone-end pass)
- **DEF-30-03-1 (== DEF-29-09-1):** live in-process delivery of a queued per-turn image to a running run's `ectx` requires the live-ectx handle / run_events re-derivation that is not yet wired. Proven at the SEAM offline (`apply_turn_images` → `pending_turn_images` → `_drain_turn_images` → `run_images` → `RunImagesProvider` block); end-to-end live multimodal steering confirmed at the consolidated live Bedrock pass.

## Next Phase Readiness
- UPLD-02 residue delivered. 30-04 (client-side image resize + the ND-10 "image not retained" reopen placeholder) can build on the locked `retained:false` disposition proven here.

## Self-Check: PASSED

---
*Phase: 30-uploads-multimodal-a2*
*Completed: 2026-07-08*
