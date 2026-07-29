"""Model-graded eval branch — LLM-as-judge grading, standalone from the
deterministic ``evals/hybrid/workflow/`` track (see specs/005-prompt-eval-scoring/).

This package answers a different question than ``workflow/``: not "is this
structurally correct" (deterministic checkers) but "is this actually good"
(a judge model scores the response against a rubric). The two tracks share
no code in either direction — ``common/live_scenario.py`` and
``workflow/prototype/revision/`` are untouched by this package, and nothing
here imports from them.

Conventions:

- ``driver.py`` dispatches to any named, already-registered pipeline agent
  via ``agents/factory.py::create_runner`` (reused as-is — see
  specs/005-prompt-eval-scoring/clarifications.md Q9/Q11 for why a raw
  chat-completion call was rejected: only ``create_runner`` reproduces the
  actual composed production system prompt, e.g. injected template/design-
  system content).
- ``precheck.py`` is a single, generic, agent-agnostic structural check
  driven entirely by a scenario's YAML ``precheck:`` config — no per-agent
  Python required for the common case (Q10).
- ``judge.py`` builds the grading prompt from a scenario's plain-text
  ``rubric:`` YAML block via one shared prompt-builder — likewise no
  per-agent module (Q10).
- ``report.py`` is pure data plumbing (JSONL persistence) with zero model
  or agent dependencies.
- ``agents/<agent_id>/`` holds only data (scenario YAML) plus, at most, one
  narrow custom precheck hook for a check the generic config genuinely
  can't express.
"""
