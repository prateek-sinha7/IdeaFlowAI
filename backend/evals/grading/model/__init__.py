"""The model track: dispatch real agents, judge their prose, score the verdicts.

Everything that touches an LLM lives here — `dispatch` (the agent under test),
`judge` (the grader), `prompt_advisor` (the improvement proposals) — plus the
model track's pure helpers: `stage_input`, `precheck`, `scoring`. The
orchestrator is `model_grader.run_workflow`, which also owns the rejudge
replay mode.

This folder doubles as the model track's CONFIG tree: `workflows/` (stage
order, rubrics, datasets) and `_templates/`. Shared plumbing — artifacts,
config loading, rendering, reports — stays one level up in `evals.grading`.
"""
