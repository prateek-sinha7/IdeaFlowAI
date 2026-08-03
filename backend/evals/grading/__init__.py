"""Agent output grading — is this agent's output good?

Two tracks, each in its own subpackage: `model/` (dispatch agents, LLM-as-judge,
prompt advice — everything that touches a model) and `code/` (deterministic
checks over built HTML, never a model). Both are driven by `grade_runner`, and
the shared plumbing — `artifacts`, `config`, `render`, `hooks`,
`markdown_report`, `compare` — lives at this level. The model track's config
tree (workflows, rubrics, datasets) sits inside `model/` beside its code.

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
