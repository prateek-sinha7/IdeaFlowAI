---
phase: quick-260701-n4l
plan: 01
subsystem: agents-test-harness
tags: [KAN-86, SAFE-02, INV-3, INV-12, characterization, goldens]
requires: []
provides:
  - "Offline harness drives the prototype-analyze agent with a faithful <analysis> turn"
  - "Regenerated 5-step prototype + od_prototype event goldens"
affects:
  - backend/tests/agents/_scripted_model.py
  - backend/tests/agents/characterization/golden/prototype.events.json
  - backend/tests/agents/characterization/golden/od_prototype.events.json
tech-stack:
  added: []
  patterns: ["dedicated per-agent script branch in _scripts_for (INV-12 extend-in-place)"]
key-files:
  created: []
  modified:
    - backend/tests/agents/_scripted_model.py
    - backend/tests/agents/characterization/golden/prototype.events.json
    - backend/tests/agents/characterization/golden/od_prototype.events.json
decisions:
  - "Modelled prototype-analyze as a dedicated text-only branch (mirroring prototype-plan), not the generic TEXT_ONLY stub, so the golden captures a realistic <analysis> report."
  - "Fixed usage=(28,16) and a fixed 528-char analysis body for deterministic normalization/output_length."
metrics:
  duration: ~7m
  completed: 2026-07-01
---

# Phase quick-260701-n4l Plan 01: Complete KAN-86 loose end (add prototype-analyze to the offline harness) Summary

Taught the offline characterization harness the upstream-merged 5th prototype agent `prototype-analyze` with a faithful `<analysis>…</analysis>` turn, then regenerated ONLY the `prototype` + `od_prototype` event goldens to the 5-step stream — restoring the offline safety net after an intentional workflow addition, with zero production/registry/manifest changes.

## Tasks

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Add a faithful prototype-analyze branch to `_scripts_for` | `64f671f7` | `backend/tests/agents/_scripted_model.py` |
| 2 | Regenerate ONLY the prototype + od_prototype event goldens | `40ffb585` | `golden/prototype.events.json`, `golden/od_prototype.events.json` |

## What changed

- **Harness (T1):** Added a dedicated `agent_id == "prototype-analyze"` branch in `_scripts_for` (extended in place — INV-12), placed in the prototype family group after `prototype-validate`. It returns exactly one `_ScriptedTurn` whose text starts with `<analysis>`, ends with `</analysis>`, contains `## Spec Kit Analysis Report`, a `### Summary` sentence, two `### Findings` rows, and a `### Readiness verdict` / `READY TO BUILD` line. Fixed `usage=(28, 16)`; fixed 528-char body. No change to `_drive`, `_OD_ALIAS_FOR_LOOKUP`, `od_context`, or any other branch.
- **Goldens (T2):** Regenerated `golden/{prototype,od_prototype}.events.json` with `SNAPSHOT_UPDATE=1` on ONLY the two event-snapshot tests. The whole suite was NOT run under the flag; the 3 out-of-scope goldens were not regenerated.

## Captured event-golden diff (reconciled against the plan's EXPECTED DIFF)

`git diff --numstat` on each golden: `78` added / `21` removed lines (identical for both files). Normalized, order-canonical multiset deltas (old → new), identical for `prototype` and `od_prototype`:

| Change | Old | New |
| ------ | --- | --- |
| Total events | 41 | 45 |
| `pipeline_start.agent_count` | 4 | 5 |
| `agent_start` | 5 | 6 (+1 for prototype-analyze) |
| `agent_complete` | 5 | 6 (+1 for prototype-analyze) |
| `agent_input` | 5 | 6 (+1 for prototype-analyze) |
| `agent_chunk` | 8 | 9 (+1 for prototype-analyze, single-piece turn) |
| `gate_status` | 1 | 1 (unchanged) |
| `review_gate*` / `gate_ready` | 0 | 0 (none appeared) |

`prototype-analyze` was inserted into `pipeline_start.agents` (order 3, "Spec Kit Analyzer", role/icon/id) and contributes exactly these 4 event types: `agent_start`, `agent_complete`, `agent_input`, `agent_chunk`.

Index/total shifts (agent_start), OLD → NEW:
- `prototype-specify`: (0,4) → (0,5)
- `prototype-plan`: (1,4) → (1,5)
- `prototype-analyze`: — → (2,5) *(new)*
- `prototype-build`: (2,4)×2 → (3,5)×2 *(runs twice: one per task)*
- `prototype-validate`: (3,4) → (4,5)

No changes to `tool_call` (4), `tool_result` (4), `task_progress` (2), `task_loop_progress` (2), `planner_start`/`planner_complete`, `pipeline_complete`, or `workflow_validated`.

**This is ONLY the analyze-step addition + the index/total shifts — nothing else.**

## STOP-tripwire confirmations (none fired)

1. **Byte goldens UNCHANGED:** `git diff --stat` on `golden/prototype.html` and `golden/od_prototype.html` is EMPTY. Both byte-snapshot tests (`test_*_deliverable_byte_snapshot`) still pass — analyze is read-only/terminal (nothing consumes it; the deliverable is read from on-disk `prototype.html`), so the built artifact is byte-identical.
2. **No gate events:** 0 `review_gate` / `gate_ready` in either regenerated golden; `gate_status` stays 1 each. (Gates suppressed in the harness via `gate_agent_ids=[]` + no-op `_run_review_gate`.)
3. **No unexpected event changes:** the only new event types belong to `prototype-analyze`; no validator-related or dropped/reordered non-analyze events.
4. **Out-of-scope goldens UNCHANGED:** `git diff --stat` on `prototype_revision.events.json`, `od_ppt.events.json`, `app_builder.events.json` (and the `.html` byte goldens) is EMPTY — they were not regenerated.

## Verification

- `pytest` offline verify suite (NO `SNAPSHOT_UPDATE`): `test_characterization_prototype` + `test_characterization_od_prototype` + `test_characterization_prototype_revision` + `test_characterization_app_builder` + `test_nav_coverage` + `test_route_table` → **64 passed** in ~79s. Real assertions against the regenerated 5-step goldens.
- Task-1 automated checks: `_scripts_for("prototype-analyze")` returns one turn, `<analysis>`-wrapped, contains `READY TO BUILD`, usage=(28,16), len=528. Both deliverable byte-snapshot tests pass.
- `/opt/homebrew/bin/lint-imports` (from `backend/`): **4 kept, 0 broken.**
- `od_ppt` remains its known pre-existing environmental failure — out of scope, untouched, excluded from the verify suite.

## Deviations from Plan

None — plan executed exactly as written. No production/registry/manifest change; no migration. `_scripts_for` extended in place (INV-12). The regen diff matched the plan's pre-computed EXPECTED DIFF byte-for-shape.

## Known Stubs

None. The `prototype-analyze` scripted turn is intentionally a fixed test fixture (deterministic offline harness content), not a production stub.

## Self-Check: PASSED

- `backend/tests/agents/_scripted_model.py` — FOUND (modified, `prototype-analyze` branch present)
- `backend/tests/agents/characterization/golden/prototype.events.json` — FOUND (agent_count 5, `prototype-analyze` present)
- `backend/tests/agents/characterization/golden/od_prototype.events.json` — FOUND (agent_count 5, `prototype-analyze` present)
- Commit `64f671f7` — FOUND
- Commit `40ffb585` — FOUND
