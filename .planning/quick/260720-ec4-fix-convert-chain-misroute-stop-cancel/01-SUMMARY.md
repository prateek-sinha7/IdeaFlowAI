---
phase: quick-260720-ec4
plan: 01
subsystem: run-screen (FE chat classifier + BE engine cooperative-cancel)
tags: [bugfix, chat, engine, cancel, clarify, gates, SC-001, INV-3]
requires: []
provides:
  - "matchChainTarget(text, suggestions) FE helper — routes a settled-run '<transform> into <available chain target>' phrase to onSuggestion(id)"
  - "clarify drain-loop cancel_event check — Stop cancels a clarify-parked run"
  - "run_human_gate → _run_review_gate cancel_event thread — Stop cancels a declared-gate-parked run"
affects:
  - frontend/src/components/chat/RunChatLane.tsx
  - backend/agents/execution_engine/engine.py
  - backend/agents/execution_engine/kernel_services.py
tech-stack:
  added: []
  patterns: ["data-driven suggestion-label match (SC-001)", "cooperative cancel_event reuse (Phase 16-02)"]
key-files:
  created: []
  modified:
    - frontend/src/components/chat/RunChatLane.tsx
    - frontend/src/components/chat/RunChatLane.test.tsx
    - backend/agents/execution_engine/engine.py
    - backend/agents/execution_engine/kernel_services.py
    - backend/tests/agents/test_gates.py
    - backend/tests/agents/test_restart_resume.py
decisions:
  - "BUG-1 keys on the DATA-DRIVEN suggestions[].label (never a workflow-name literal) — SC-001/INV-1 held (RunChatLane.tsx banned-grep stays 0)."
  - "BUG-2 reuses the shipped cooperative-cancel MODEL + the existing pipeline_cancelled terminal — no new event type, no second mechanism; DORMANT when cancel_event is None (goldens 10/10)."
  - "Condition-A test drives a PARKING fake ClarifyEngine (never emits questionnaire_complete), NOT the real one (which does an offline-hanging LLM call) — per the plan-checker."
metrics:
  duration: "~35 min"
  completed: "2026-07-20"
---

# Phase quick-260720-ec4 Plan 01: Fix convert→chain misroute (BUG-1) + Stop no-op at clarify/declared-gate (BUG-2) Summary

Two independent pre-existing run-screen bugs fixed in two atomic commits on `feat/ui-2`: BUG-1 (FE) routes a settled-run "convert it into presentation"-style phrase to the chain seam (`onSuggestion`) instead of a same-run revision; BUG-2 (BE) makes the Stop button cancel-aware at the two states where it silently no-ops — a clarify-parked run and a declared human/approval-gate-parked run — by reusing the shipped cooperative-cancel machinery.

## Task 1 — BUG-1 (FE, commit `8ad16739`, `fix(chat)`)

**`matchChainTarget(text, suggestions): string | null`** added at `RunChatLane.tsx:329`, a two-part gate:
1. **Transform shape** — `CHAIN_TRANSFORM = /\b(convert|turn|make|transform|change|render|export|generate)\b.*\b(into|to|as)\b/i`. No connector ⇒ null (a bare "make it bigger" stays a change).
2. **Named available target** — take the TAIL after the FIRST connector (`CHAIN_CONNECTOR.exec`), and for each `suggestions[]` match case-insensitively against `label` (substring) OR any whitespace token of the label with length ≥ 4. Returns the FIRST matching `id`, else null. Matching the TAIL (not the whole text) is load-bearing so "convert the presentation-buttons into pills" does not spuriously match.

**Insertion point:** `handleFreeText` (`RunChatLane.tsx:1011`), inside the `runState === "complete"` block, BEFORE the `classifyFreeText(text) === "ask"` check: `const chainId = matchChainTarget(text, suggestions); if (chainId && onSuggestion) { onSuggestion(chainId); return; }`. `onSuggestion` added to the useCallback deps. Any non-match falls through to the UNCHANGED ask/change/held-refinement path. SC-001-safe — no workflow-name literal (banned-grep 0).

**RED evidence:** against the unchanged source (new tests present), the positive test `settled-run 'convert it into presentation' … fires onSuggestion(ppt)` FAILED — `expect(onSuggestion).toHaveBeenCalledTimes(1)` got 0 calls (the phrase misrouted to the held-refinement chip). The two NEG tests (no-target / no-suggestions) already passed on the unchanged source since they assert preserved behavior. **GREEN:** 47/47 after the fix.

## Task 2 — BUG-2 (BE, commit `31fa1954`, `fix(engine)`)

**Condition A — clarify drain loop** (`engine.py:1934-1957`, the `except asyncio.TimeoutError:` branch of the `while not clarify_task.done()` drain loop): before the existing `continue`, added `if cancel_event is not None and cancel_event.is_set():` (line `1943`) → `clarify_task.cancel()`, defensively `await` it swallowing `(asyncio.CancelledError, Exception)`, `self._state_machine.transition(pipeline_run_id, "cancelled")`, yield the existing `{"type": "pipeline_cancelled", "data": {"pipeline_run_id": pipeline_run_id}}`, and `return`. Runs on the loop's existing 1s heartbeat (bounded latency); DORMANT when `cancel_event is None` (byte-identical `continue`).

**Condition B — declared-gate delegate** (`kernel_services.py:1120`): added `cancel_event=self.cancel_event` as a keyword arg to the `self._engine._run_review_gate(...)` call in `run_human_gate` (KernelServices already stores `self.cancel_event` from `engine.execute`). The EXISTING cancel-aware race in `_run_review_gate` then fires on the declared path exactly as at the inline gate sites; the downstream `_gate_rejected → GATE_BLOCK → cancel → pipeline_cancelled` chain is unchanged. `None`-caller behavior (plain `await event.wait()`) preserved.

**Test recipe (parking ClarifyEngine):** `test_stop_at_clarify_yields_pipeline_cancelled` (`test_restart_resume.py`) adds an additive `clarify_mode="off"` param to `_ResumeHarness.__init__` (used in `_patched_compile` in place of the hardcoded `"off"`; default keeps every caller byte-identical), enters with `clarify_mode="auto"`, monkeypatches `clarify_engine.ClarifyEngine` to `_ParkingClarify` (emits ONE `questionnaire_ready` then `await asyncio.Event().wait()` — never completes), overrides `_run_planner` to return `CLARIFY_REQUIRED` + `missing_information=["target audience"]`, then drives `engine._execute_impl(..., cancel_event=ev)` inside `asyncio.wait_for(..., timeout=8)`, setting `ev` on the first `questionnaire_ready`. Condition B: `_FakeReviewEngine._run_review_gate` extended to accept + record `cancel_event=None` (`self.seen_cancel`), `_kernel_services` extended with an optional `cancel_event`; `test_run_human_gate_threads_cancel_event_into_review_gate` asserts `fake_engine.seen_cancel is ev`.

**RED evidence:** against unchanged BE source — Condition A: `asyncio.wait_for(_drive(), timeout=8)` raised `TimeoutError` (the drain loop ignored `ev`, the run hung at clarify); Condition B: `assert fake_engine.seen_cancel is ev` FAILED with `seen_cancel is None` (the delegate received no cancel_event). **GREEN:** both pass after the fix.

## Gate Results

| Gate | Result |
|------|--------|
| FE vitest `RunChatLane.test.tsx` | 47/47 passed |
| BE targeted (`test_gates.py` + `test_restart_resume.py` + `test_execution_engine.py`) | 101 passed, 3 pre-existing failures (see below) |
| 5 characterization goldens (SNAPSHOT_UPDATE unset) | 10/10 byte/event-identical |
| Banned-grep RunChatLane.tsx / engine.py / kernel_services.py | 0 / 87 / 19 (all baselines held) |
| `test_banned_patterns.py` | 11 passed |
| `lint-imports` | 4 kept / 0 broken |

## Deviations from Plan

None to the implementation. The plan was executed exactly as written, honoring all three plan-checker concerns (parking ClarifyEngine for Condition A; BUG-1 tail-match breadth kept as-is; `_FakeReviewEngine._run_review_gate` extended with `cancel_event=None`).

## Deferred Issues (pre-existing, out of scope)

3 tests in `tests/agents/test_gates.py` fail on the PRISTINE tree (verified: pristine source + pristine test file → 3 failed, 38 passed), unrelated to this plan's files/changes — test-harness stub drift (`_Ctx` missing `gate_agent_ids`; `_Ectx` missing `artifacts`):
- `test_raising_hitl_gate_blocks_and_stops_gate_evaluation`
- `test_engine_sentinel_carries_human_gate_edit_detail`
- `test_apply_declared_gate_edit_rewrites_upstream_artifact_and_result`

Logged to `deferred-items.md`. Not touched (scope boundary — pre-existing failures in tests this plan does not modify).

## Self-Check: PASSED

- Commit `8ad16739` FOUND (Task 1, FE).
- Commit `31fa1954` FOUND (Task 2, BE).
- `matchChainTarget` present at `RunChatLane.tsx:329`; drain-loop cancel check at `engine.py:1943`; `cancel_event=self.cancel_event` at `kernel_services.py:1120`.
</content>
</invoke>
