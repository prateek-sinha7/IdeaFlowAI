"""The code track: deterministic checks over built HTML, no judge model ever.

`code_grader` reuses the runtime's own validators (static_check, render_check)
plus a Playwright interaction sweep, and must never import from
`evals.grading.model` — the free checks stay independent of the expensive ones.
"""
