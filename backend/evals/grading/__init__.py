"""Agent output grading — is this agent's output good?

Two tracks: `model_grader` (LLM-as-judge, for prose) and `code_grader`
(deterministic checks, for built HTML), both driven by `grade_runner`. Config and
run artifacts live under `model/` and `code/`; see PLAN.md and TASKS.md.

Conventions, binding for every module here:

- All imports at the top of the file. No function-level or inline imports.
  Where a test needs to monkeypatch a runtime seam, import the MODULE
  (`import agents.factory`) and call through it, so the attribute is looked up at
  call time.
- The `sys.path` bootstrap lives in `grade_runner.py` only — it is the sole entry
  point, and every other module imports normally.
- One job per module. `stage_input`, `scoring`, `compare` and `precheck` are PURE:
  no file I/O, no model calls, no imports from this package. `scoring` and
  `compare` take plain dicts (the artifact shapes), never typed objects, which is
  what keeps them leaf modules.
- `artifacts` is the sole owner of every run-folder path.
- `evals/model_graded/` is READ-ONLY. Copy from it; never edit it.
"""
