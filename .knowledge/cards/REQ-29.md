---
id: REQ-29
type: req
status: done
area: [resume, workflow, artifacts]
summary: >-
  Resume Correctness (Phase 45 [R0])
source: .planning/REQUIREMENTS.md#resume-correctness-phase-45-r0
---

### Resume Correctness (Phase 45 [R0])

- [x] **RESUME-05**: A run interrupted mid-build resumes by re-entering the build step and completing ONLY the unfinished tasks — a partially-completed build is never classified "complete" and silently skipped (fixes the `engine.py:6002` first-task-persist bug). Completeness is strategy-conditional: task-granular steps (task_loop/wave) count tasks-in-current-list vs completed per-task artifacts; `single_shot` steps keep produced-ref/`step_completed` semantics byte-unchanged; `step_reused` (input_hash) behavior untouched.
