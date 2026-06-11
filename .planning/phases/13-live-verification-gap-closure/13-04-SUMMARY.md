---
phase: 13-live-verification-gap-closure
plan: 04
subsystem: workflows-manifests, tests-live-evidence
tags: [sc-001, deliverable, serialized_sandbox, live-evidence, token-delta, budget-calibration]
requires:
  - "12-10: sample_wave serialized_sandbox precedent (commit 8ffae37c)"
  - "07-03/07-05: html_skeleton compaction capability (relocated engine skeleton helper)"
  - "Phase-7 generic injector: async ExecutionEngine._compose_context_message"
provides:
  - "sample_fanout deliverable resolved via the registered serialized_sandbox strategy (no single_file fallback)"
  - "test_phase3_token_delta_live re-pointed at the current engine seams (collects cleanly offline)"
  - "LIVE_BUDGET_USD recalibrated to the measured clean-sweep spend"
affects: [13-05, 13-06, end-of-milestone-live-pass]
tech-stack:
  added: []
  patterns:
    - "manifest-data-only deliverable swap (SC-001: zero engine edits)"
    - "module-level seam-existence assert so live-gated tests fail at OFFLINE collection on engine renames"
key-files:
  created: []
  modified:
    - backend/agents/workflows/sample_fanout/workflow.yaml
    - backend/tests/agents/test_sc001_fanout.py
    - backend/tests/agents/test_phase3_token_delta_live.py
    - backend/tests/agents/test_phase8_live.py
key-decisions:
  - "F6 fixed as manifest data only — deliverable strategy single_file/merged.txt -> serialized_sandbox, mirroring the sample_wave 8ffae37c precedent (SC-001 held: zero engine edits)"
  - "Compaction-off baseline sources skeleton bytes from the registered html_skeleton capability (resolve+compact on the typed prototype-build content) — byte-exact with the engine's injected block, no deleted engine helper"
  - "Added a module-level hasattr(_compose_context_message) assert so a future seam rename is caught by offline collection, not a paid live run"
  - "LIVE_BUDGET_USD 5.0 -> 8.0: calibration drift, not overspend — measured clean sweep $5.94 / 18.7M tokens after the 32768 MAX_OUTPUT_TOKENS lift; 8.0 keeps ~35% runaway headroom"
duration: ~10min
completed: 2026-06-12
---

# Phase 13 Plan 04: F6 + F7 Gap Closure (sample_fanout deliverable, live-test seams, budget) Summary

sample_fanout deliverable swapped to the registered serialized_sandbox strategy (manifest-data-only, SC-001), the live token-delta test re-pointed at async `_compose_context_message` + the `html_skeleton` capability, and the phase-8 live budget recalibrated to the measured $5.94 clean-sweep spend.

## What was done

### Task 1 — F6: sample_fanout deliverable resolves from produced files (commit 25c0d270)

- `backend/agents/workflows/sample_fanout/workflow.yaml`: replaced `deliverable: strategy: single_file / name: merged.txt` (a file no step ever writes — workers write part_1..3.txt merged by copy_disjoint) with `strategy: serialized_sandbox`. Header comment updated: capability list now names the deliverable, plus the explanatory paragraph mirroring sample_wave (cites UAT Gap 6 / F6, 13-04).
- `backend/tests/agents/test_sc001_fanout.py`: mirrored the 8ffae37c sample_wave test additions —
  - end-to-end test asserts `pipeline_complete.final_output` is the serialized_sandbox `filename:`-block bundle containing all three part files (`filename: part_1.txt` / `part_2.txt` / `part_3.txt`), non-empty, with no `(no files written)` marker (no fallback fired);
  - registered-capabilities test asserts `reg.is_registered("deliverable", "serialized_sandbox")`, manifest contains `strategy: serialized_sandbox`, and `merged.txt` is gone.
- Existing fan-out mechanics assertions (3 spawned + 3 results + 3 merged files + no merge_conflict) untouched and green.
- Zero edits under `backend/agents/execution_engine/` (verified via `git diff --stat` across both commits).

### Task 2 — F7 + UAT test 8: live-test seam repair + budget recalibration (commit b8bad06a)

- `backend/tests/agents/test_phase3_token_delta_live.py`:
  - compaction-OFF override re-pointed from the deleted `_build_context_message`/`_extract_html_skeleton` seams to the current engine: captured `engine._compose_context_message`, replaced the wrapper with an **async** function matching the 6-positional shape `(spec, index, ordered_agents, user_message, planning_context, ectx)` that awaits the original, then for `spec.id == "prototype-build"` task 2+ swaps the standalone `=== CURRENT PROTOTYPE (skeleton — …) ===` block back to the full-HTML block;
  - skeleton bytes recomputed via the registered capability — `discover()` then `CapabilityRegistry().resolve("compaction", "html_skeleton").compact(current_html)` on `engine._latest_typed_content(ectx, "prototype-build")`, the exact inputs the task_loop strategy uses, so the replace target matches byte-exactly;
  - stale pre-Phase-7 comments rewritten; module-level seam-existence assert added (`hasattr(ExecutionEngine, "_compose_context_message")`) so a future rename fails offline collection instead of a paid live run;
  - zero references to the deleted seam names remain (grep-verified 0/0).
- `backend/tests/agents/test_phase8_live.py:108`: `LIVE_BUDGET_USD = 8.0` with the measurement citation — recalibrated 2026-06-11 from the measured clean full sweep ($5.94 / 18.7M tokens, 17.5M input, Haiku 4.5 pricing after the 32768 MAX_OUTPUT_TOKENS lift); 5.0 was the pre-lift Phase-8 calibration.

## Verification

- `python3.11 -m pytest tests/agents/test_sc001_fanout.py -q` — **3 passed** (offline scripted model, with the new deliverable-bundle assertions).
- `python3.11 -m pytest tests/agents/test_phase3_token_delta_live.py tests/agents/test_phase8_live.py --collect-only -q` — **34 tests collected**, exit 0 offline (no setup-time AttributeError).
- Acceptance greps: `strategy: serialized_sandbox` ×1 and `merged.txt` ×0 in the manifest; `_build_context_message` ×0, `_extract_html_skeleton` ×0, `_compose_context_message` ×7, `html_skeleton` ×4 in the token-delta test; `LIVE_BUDGET_USD = 8.0` at test_phase8_live.py:108.
- `git diff --stat HEAD~2 HEAD` shows exactly the 4 planned files — nothing under `backend/agents/execution_engine/` (SC-001 manifest-data-only fix held).
- Live re-runs of the two RUN_LIVE_BEDROCK suites deferred to the end-of-milestone live pass (project convention).

## Deviations from Plan

None - plan executed exactly as written. (One in-flight correction: the first draft of the seam-repair comments mentioned the deleted seam names in prose, which violated the zero-reference acceptance grep — reworded before commit.)

## Known Stubs

None — no hardcoded empty values, placeholders, or unwired components introduced.

## Threat Flags

None — no new security surface. The budget-ceiling raise is the accepted T-13-04-02 disposition (soft, opt-in evidence-run guardrail, never CI); the spawn_subagents grant is unchanged (T-13-04-01).

## Commits

| Task | Commit | Message |
| ---- | ------ | ------- |
| 1 | 25c0d270 | fix(13-04): point sample_fanout deliverable at the produced merged base (F6) |
| 2 | b8bad06a | test(13-04): re-point token-delta live seams + recalibrate live sweep budget (F7) |

## Self-Check: PASSED

- 13-04-SUMMARY.md exists on disk
- Commits 25c0d270 and b8bad06a present in git log
- All 4 modified files verified present; no engine files touched

