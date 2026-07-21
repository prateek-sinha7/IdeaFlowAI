---
phase: 28-chat-contracts-guards-a0
plan: 01
subsystem: testing
tags: [contracts, chat-events, characterization, golden, inv-3, chat-06]

# Dependency graph
requires:
  - phase: 18-01
    provides: "_VOLATILE_STRIP_KEYS additive-strip precedent (deliverable_mimetype/redoable/image_count) + _DOCUMENTED_EVENT_TYPES forward-vocabulary guard"
provides:
  - "chat_message/chat_reply/stream_attached registered in the documented outbound WS vocabulary (_DOCUMENTED_EVENT_TYPES) — legal before any code emits them"
  - "message_id + replayed_through_seq registered in _VOLATILE_STRIP_KEYS (belt-and-suspenders volatile strip)"
  - "test_chat_event_neutrality.py — standing characterization proof that chat events never fire on the 5 golden pipelines (POR §7 landmine guard)"
affects: [29-chat-persistence, 31-run-ui, 32-inline-gate, chat-lane, narrator]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Forward-vocabulary widening as parity-neutral additive contract: register a future event type in _DOCUMENTED_EVENT_TYPES BEFORE any code emits it, guarded by a golden-neutrality proof so INV-3 is provably preserved"
    - "Paired guards: a neutrality assertion (event absent from goldens) pinned together with a documented-membership assertion (event in vocabulary) so an accidental removal fails loudly"

key-files:
  created:
    - backend/tests/agents/test_chat_event_neutrality.py
  modified:
    - backend/tests/agents/test_phase3_cutover_verify.py
    - backend/tests/agents/characterization/_normalize.py

key-decisions:
  - "chat_message/chat_reply/stream_attached added to _DOCUMENTED_EVENT_TYPES with a documenting comment; parity-neutral because the scripted golden harness has no chat lane (POR D-01)"
  - "Only the run-specific/client-generated subkeys were stripped: message_id (FE idempotency key) + replayed_through_seq (replay cursor). stream_attached.live (deterministic boolean) and chat_reply card discriminators (stable) were deliberately NOT stripped"
  - "_REQUIRED_DATA_KEYS left untouched — the three chat types carry no load-bearing required keys under the golden harness"
  - "No golden fixture regenerated — a passing run against the UNCHANGED golden/* fixtures IS the INV-3 proof"

patterns-established:
  - "Chat-lane contracts are pinned as tests/docs BEFORE the emitting code (Phase 29+), keeping every later phase's contract legal and golden-neutral from day one"

requirements-completed: [CHAT-06]

# Metrics
duration: ~9min
completed: 2026-07-07
---

# Phase 28 Plan 01: Chat Event Vocabulary & Golden-Neutrality Proof Summary

**Registered the three run-chat event types (chat_message/chat_reply/stream_attached) in the documented WS vocabulary + their volatile subkeys in the normalizer, with a standing characterization proof that chat events never perturb the 5 golden pipelines (INV-3 held, no fixture regenerated).**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-07-07T21:03Z (approx)
- **Completed:** 2026-07-07T21:12:08Z
- **Tasks:** 2
- **Files modified:** 3 (2 modified, 1 created)

## Accomplishments
- Added `chat_message`, `chat_reply`, `stream_attached` to `_DOCUMENTED_EVENT_TYPES` (POR D-01) with a documenting comment matching the existing "Declared-gate dispatch events" convention — parity-neutral superset widening.
- Added `message_id` + `replayed_through_seq` to `_VOLATILE_STRIP_KEYS` following the `image_count` belt-and-suspenders precedent; `live` and card discriminators deliberately left intact.
- Created `test_chat_event_neutrality.py` — parametrized proof that none of the three chat types appears in any of the 5 golden event streams, plus a paired assertion that the three types are documented so an accidental removal fails there.
- Proved INV-3: the 5 characterization goldens + the cutover forward-guard stay byte/event-identical against UNCHANGED fixtures (22/22 green, no `SNAPSHOT_UPDATE`, no golden touched). lint-imports 4 kept / 0 broken.

## Task Commits

Each task was committed atomically on `feat/ui-2`:

1. **Task 1: Add chat event vocabulary + volatile subkeys** - `2acdc83f` (test)
2. **Task 2: Golden-neutrality proof test** - `3cf00459` (test)

**Plan metadata:** (docs commit — this SUMMARY + STATE + ROADMAP)

## Files Created/Modified
- `backend/tests/agents/test_phase3_cutover_verify.py` - Added the 3 chat event types to `_DOCUMENTED_EVENT_TYPES` with a documenting comment block.
- `backend/tests/agents/characterization/_normalize.py` - Added `message_id` + `replayed_through_seq` to `_VOLATILE_STRIP_KEYS` with a documenting comment.
- `backend/tests/agents/test_chat_event_neutrality.py` - New golden-neutrality proof (CHAT-06): chat events absent from all 5 goldens + documented-membership guard.

## Decisions Made
- Stripped only the two run-specific/client-generated subkeys (`message_id`, `replayed_through_seq`); left `stream_attached.live` (deterministic) and `chat_reply` card discriminators (stable) unstripped, per the plan's explicit instruction.
- Left `_REQUIRED_DATA_KEYS` untouched — the chat types have no load-bearing required keys under the golden harness.
- Did NOT regenerate any golden fixture; the passing run against committed fixtures is the INV-3 proof.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None. Both verify gates passed on the first run.

## Verification Evidence
- Task 1 automated verify: vocabulary + volatile-key import assertion printed `OK`.
- Task 2 automated verify: `python3.11 -m pytest` on the neutrality test + `test_phase3_cutover_verify` + the 5 `test_characterization_*.py` goldens → **22 passed, 1 warning in 51.76s** (offline, unchanged fixtures).
- `git status` on `backend/tests/agents/characterization/golden/` — empty (zero fixture modifications).
- `/opt/homebrew/bin/lint-imports` (from `backend/`) — **4 kept, 0 broken**.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The chat event vocabulary + volatile subkeys are now legal in the documented contract and guarded by a standing neutrality proof — Phase 29 (persist `chat_message`/`chat_reply`) and Phases 31/32 (render them) can emit these types without perturbing the goldens.
- No blockers.

## Self-Check: PASSED

---
*Phase: 28-chat-contracts-guards-a0*
*Completed: 2026-07-07*
