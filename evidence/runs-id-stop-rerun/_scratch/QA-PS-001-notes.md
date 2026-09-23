# QA-PS-001 validation notes

Bug: Stop and rerun skips saving the interrupted build task's agent file (/runs/{id})

## Cycle 1 — cold start, run 80b00eba-c146-4d04-a47c-9193ab4228cc
- Brief: budgeting app prototype
- Answered 4 clarifications with "Use recommended"
- Waited until Build Agent showed "Executing task 2 of 7...", let it run ~20s into task 2, clicked Stop
- Clicked "Run Again" (same run id, no new clarification gate on rerun)
- Waited for full completion (status: completed)
- Workspace/.agents folder: 01, 02, 03, 04-t1 through 04-t7, 05, all present. 04-prototype-build-t2.md PRESENT (26 KB).
- Result: NOT reproduced

## Cycle 2 — cold start, run 4bb4bbcb-9a0e-4831-a58d-577bd5fd1832
- Brief: habit tracker prototype (2 rounds of clarifications, answered with "Use recommended")
- Clicked Stop IMMEDIATELY on first render of "Executing task 2 of 6..." (timing axis: fast vs cycle 1's ~20s)
- Clicked "Run Again", waited for Build Agent to finish all 6 tasks
- Workspace: 04-prototype-build-t1.md through t6.md all present, including t2 (31 KB)
- Result: NOT reproduced

## Cycle 3 — cold start, run 0333366f-539c-4339-8e16-ad6d1528fc61
- Brief: notes app prototype
- Waited until Build Agent hit "Executing task 2 of 7...", clicked Stop right away
- Clicked "Run Again", waited for all 7 build tasks + Validation Agent
- Workspace: 04-prototype-build-t1.md through t7.md all present, including t2 (30 KB)
- Result: NOT reproduced

## Axes swept across the 3 cycles
- Timing: stopped ~20s into task 2 (cycle 1), immediately on task-2 start (cycle 2), immediately on task-2 start (cycle 3)
- Entry path: always cold /create/prototype -> Continue -> answer clarifications -> Stop -> Run Again (same run id) — matches the reported repro steps
- Data/brief: three different prototype briefs, different total task counts (6 or 7 build tasks)
- All 3 runs were run to full completion after rerun before checking .agents folder

## Score: 0/3 — UNREPRODUCIBLE
No axis produced the missing-file symptom. In every cycle the full .agents build-task
sequence (04-prototype-build-t1..tN) was present after Stop + Run Again + completion,
with no gaps.

## Side observation (NOT part of this bug, not investigated further)
"Spec Kit Analyzer" (03-prototype-analyze.md) was present in cycle 1's original attempt
but absent from the reruns in cycles 2 and 3 (pipeline showed only 4 agents: Spec Writer,
Task Planner, Build, Validation — no Spec Kit Analyzer step at all on rerun). This looks
like a distinct behavior worth a separate look, but it is unrelated to the QA-PS-001 claim
(missing build-task file) and was not chased further here.
