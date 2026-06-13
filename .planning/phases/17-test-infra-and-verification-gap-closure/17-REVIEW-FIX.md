---
phase: 17-test-infra-and-verification-gap-closure
fixed_at: 2026-06-13T14:42:00Z
review_path: .planning/phases/17-test-infra-and-verification-gap-closure/17-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 17: Code Review Fix Report

**Fixed at:** 2026-06-13T14:42:00Z
**Source review:** .planning/phases/17-test-infra-and-verification-gap-closure/17-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (WR-01, IN-01, IN-02)
- Fixed: 3
- Skipped: 0

All fixes are TEST-ONLY (`git diff --name-only` shows only `backend/tests/...`; no
production file touched). Verification is deterministic and offline.

## Fixed Issues

### WR-01: `_drive_live` leaks `engine_mod.create_runner` — never restored in `finally`

**File modified:** `backend/tests/agents/test_phase3_token_delta_live.py`
**Commit:** da98b266
**Applied fix:** Snapshotted `_orig_engine_create_runner = engine_mod.create_runner`
immediately before the `engine_mod.create_runner = _live_create_runner` patch, and added
`engine_mod.create_runner = _orig_engine_create_runner` to the existing `finally` block
(alongside the `compile_for_run` and `factory_mod.create_runner` restores). This mirrors
the established `_scripted_model._drive` precedent for this same module global.

**Empirical no-leak verification (the leak check the reviewer used):** drove the offline
scripted `_drive_live(compaction_on=True)` and asserted that after it returns,
`engine_mod.create_runner is <original factory.create_runner>` (and
`.__name__ != "_live_create_runner"`). Result: PASSED — the global is restored, so no later
engine-driving test in the session routes through the live-Bedrock `_live_create_runner`.

This finding is an isolation/logic fix; logic was confirmed empirically (not just by syntax),
so no further human verification is required.

### IN-01: trailing `monkeypatch.setattr(otel, "_TRACER", None)` comment overstated

**File modified:** `backend/tests/agents/test_hooks.py`
**Commit:** 4d64a5fd
**Applied fix:** Kept the line (belt-and-suspenders) but rewrote the comment to state
accurately that `monkeypatch` already reverts `_TRACER` to its pre-test value on teardown
(it dedupes by `(target, name)` and restores the original captured at the first `setattr`),
so the explicit null is redundant for isolation. No behavior change.

### IN-02: `_compose_context_message` instance override not restored

**File modified:** `backend/tests/agents/test_phase3_token_delta_live.py`
**Commit:** 4451b2e5
**Applied fix:** Added a comment at the
`engine._compose_context_message = _full_html_compose_ctx` override noting it is safe with
no restore only because `engine` is a fresh per-call `ExecutionEngine()` instance, and that
a future refactor reusing one engine across both A/B drives must restore it. No behavior
change.

## Verification Summary

- `pytest tests/agents/test_phase3_token_delta_live.py` → 1 passed / 1 skipped (no hang, 8.78s)
- Empirical WR-01 no-leak check → `engine_mod.create_runner` restored to original: PASSED
- `pytest tests/agents/test_hooks.py -k otel` → 10 passed
- 5 characterization goldens (`test_characterization_{app_builder,od_ppt,od_prototype,prototype_revision,prototype}.py`) → 10 passed
- `/opt/homebrew/bin/lint-imports` → 4 kept / 0 broken
- `git diff --name-only` → test-only (`backend/tests/agents/test_hooks.py`, `backend/tests/agents/test_phase3_token_delta_live.py`)

---

_Fixed: 2026-06-13T14:42:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
