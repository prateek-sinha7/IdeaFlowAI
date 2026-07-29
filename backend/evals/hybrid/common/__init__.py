"""Shared eval-framework machinery — reusable across every pipeline's eval
coverage under evals/hybrid/workflow/<domain>/<variant>/.

Conventions this package establishes and expects callers to follow:

- **`workflow/<domain>/<variant>/` nesting.** `<domain>` is a pipeline_type
  with any trailing `_revision` stripped; `<variant>` is `build` or
  `revision`. `scenario_discovery.discover_all_scenarios()` globs exactly 2
  levels below `workflow/` (`workflow/*/*/scenarios/`) — if a 3rd nesting
  level (e.g. per pipeline-step) is ever added, that glob needs a matching
  update.
- **3rd nesting level, if ever needed**: use the pipeline manifest's own
  step names (from `workflow.yaml`), not agent names — a step's agent is an
  implementation detail that can change independently of the step identity.
- **`agent_id` is required in every scenario YAML** — `run_live_scenario_once`
  is generic across pipelines/agents; nothing here hardcodes which agent a
  scenario drives.
- **Pipeline-agnostic tests belong in `evals/hybrid/engine/`, not nested
  under one pipeline's `workflow/<domain>/<variant>/` folder.** Verify
  "pipeline-agnostic" against production source before moving something
  here — e.g. `grep -rl <thing> agents/workflows/*/workflow.yaml` to check
  how many pipelines' manifests actually reference it — never assume.
- **When to extract a new `common/` helper**: only once a SECOND real
  consumer needs the same shape — extracting from a single example risks
  guessing at the wrong abstraction (see PLAN.md's L4-stub discussion for
  why that extraction was deliberately deferred).
"""
