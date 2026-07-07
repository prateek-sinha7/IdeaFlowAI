---
phase: 28-chat-contracts-guards-a0
reviewed: 2026-07-07T21:33:04Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - backend/tests/agents/characterization/_normalize.py
  - backend/tests/agents/test_phase3_cutover_verify.py
  - backend/tests/agents/test_chat_event_neutrality.py
findings:
  critical: 0
  warning: 1
  info: 1
  total: 2
status: issues_found
---

# Phase 28: Code Review Report

**Reviewed:** 2026-07-07T21:33:04Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

This is a contracts/tests-only phase (INV-3 additive-only, no kernel/runtime edit). The diff
range `826a011d..HEAD` touches exactly the three files declared in scope:

- `characterization/_normalize.py`: two new keys (`message_id`, `replayed_through_seq`) appended
  to `_VOLATILE_STRIP_KEYS`.
- `test_phase3_cutover_verify.py`: three new event types (`chat_message`, `chat_reply`,
  `stream_attached`) appended to `_DOCUMENTED_EVENT_TYPES`.
- `test_chat_event_neutrality.py`: new golden-neutrality proof module (89 lines).

**Verified directly (not just read):**
- `git diff` confirms `_REQUIRED_DATA_KEYS` has zero touched lines — untouched as claimed.
- All 5 golden event files (`app_builder`, `od_ppt`, `od_prototype`, `prototype_revision`,
  `prototype`) exist at the path the new test resolves (`tests/agents/characterization/golden/`)
  and are flat JSON arrays of `{type, data}` dicts — matching what `_load_golden_types` expects.
- None of the 5 golden event-type sets contain `chat_message`/`chat_reply`/`stream_attached`
  today (confirmed by direct inspection of all 5 files).
- Ran the new test module plus `test_phase3_cutover_verify.py` and all 5
  `test_characterization_*.py` suites — **22 passed**.
- Proved the neutrality assertion is NOT vacuous: patched `_GOLDEN_DIR` to a temp copy with an
  injected `chat_message` event and confirmed `test_chat_events_absent_from_golden` correctly
  raises `AssertionError`.
- No new production/kernel code touched; `agent_start`/`agent_complete`/etc. required-key shapes
  unchanged.

No blocking or correctness defects found in the diff. Two lower-severity observations below —
one about future coverage drift in the new proof test, one a documentation-accuracy nit in the
new `_normalize.py` comment.

## Warnings

### WR-01: Golden-pipeline list in the neutrality proof is hand-maintained, not derived — future pipelines can silently escape the guard

**File:** `backend/tests/agents/test_chat_event_neutrality.py:26-32`
**Issue:** `_GOLDEN_PIPELINES` is a hardcoded 5-tuple that the module docstring frames as "the
standing characterization proof" that chat events never fire on golden paths. It is not derived
from the contents of `characterization/golden/` (e.g. by globbing `*.events.json`). If a 6th
characterization pipeline's golden is added in a future phase without also updating this tuple,
`test_chat_events_absent_from_golden` will keep passing — silently — without ever having
inspected the new golden. The INV-3 guarantee this test exists to prove would then have a gap
that produces no red signal. (Note: this mirrors the existing convention in
`test_characterization_*.py`, each of which also hardcodes one pipeline name, so it is not a
novel pattern — but this particular module's job is explicitly to be the *exhaustive* proof
across "the 5 golden pipelines," which makes the enumeration's hand-maintained nature a real,
if latent, coverage risk specific to this test's stated purpose.)
**Fix:** Derive the pipeline list from the golden directory instead of hardcoding it, e.g.:
```python
_GOLDEN_PIPELINES = tuple(
    sorted(p.stem.removesuffix(".events") for p in _GOLDEN_DIR.glob("*.events.json"))
)
```
or, if a fixed enumeration is preferred for readability, add a cheap companion assertion (e.g.
`assert set(_GOLDEN_PIPELINES) == {p.stem.removesuffix(".events") for p in _GOLDEN_DIR.glob("*.events.json")}`)
so a new/renamed golden file that isn't reflected in `_GOLDEN_PIPELINES` fails loudly instead of
being silently skipped.

## Info

### IN-01: New `replayed_through_seq` strip-key rationale is inaccurate about where the key lives today

**File:** `backend/tests/agents/characterization/_normalize.py:169-183`
**Issue:** The new comment block frames `replayed_through_seq` as a subkey that "lands in Phase
29+" on the future `stream_attached` SSE handshake event. In fact `replayed_through_seq` is
already a live production key today — `app/api/websocket.py:1161` stamps it on the existing
`pipeline_reconnected` event (the WS reconnect-replay ack), which itself is not currently a
member of `_DOCUMENTED_EVENT_TYPES` at all. This is a pre-existing gap outside this phase's
diff (not something this phase needs to fix, and out of scope per INV-3 additive-only), but the
new comment's framing ("Phase 29+", tied only to `stream_attached`) will read as misleading to a
future maintainer who greps for `replayed_through_seq` and finds it already shipping under a
different, currently-undocumented event type. Because `_VOLATILE_STRIP_KEYS` strips the key
globally (not scoped to `stream_attached`'s `data` dict specifically), if `pipeline_reconnected`
data is ever captured by a future characterization/golden harness, this key would now be
silently stripped too, under a rationale comment that doesn't mention that event type at all.
**Fix:** Either (a) broaden the comment to acknowledge `replayed_through_seq` is already in live
use on `pipeline_reconnected` today, and note that this strip is intentionally shared, or (b) file
a follow-up to add `pipeline_reconnected` to `_DOCUMENTED_EVENT_TYPES` when the reconnect path is
brought under the same forward-vocabulary contract discipline.

---

_Reviewed: 2026-07-07T21:33:04Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
