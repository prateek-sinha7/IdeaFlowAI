---
phase: 04-manifest-compiler-1a
plan: 02
subsystem: engine
tags: [dataclass, yaml, manifest, workflow, hexagonal, declaration-layer]

# Dependency graph
requires:
  - phase: 04-manifest-compiler-1a (04-01)
    provides: agents/capabilities/ package (CapabilityRegistry) — sibling, not imported by this plan
provides:
  - "agents/workflows/ package — the declarative workflow data layer (no engine/api imports)"
  - "plan.py — full §6 typed contract: CompiledWorkflow / Step / Task (+ inert forward types, D-06)"
  - "manifest.py — WorkflowManifest dataclass + ManifestValidationError + load_manifest (D-10/MAN-01)"
  - "Strict-key rejection of unknown top-level keys (_ALLOWED_TOP_KEYS, D-08/INV-5)"
  - "yaml.safe_load-only manifest parsing (T-04-03 mitigation)"
affects: [04-03 (compiler consumes WorkflowManifest -> CompiledWorkflow), 04-04, 04-05, engine-routing-seam, api-workflows]

# Tech tracking
tech-stack:
  added: []  # no new packages — PyYAML + python-frontmatter already installed
  patterns:
    - "Typed-config loader mirroring agents/loader.py: @dataclass + yaml.safe_load + per-field validation naming the field"
    - "Strict top-level key allow-list (frozenset) -> reject DSL/control-flow keys by name (INV-5)"
    - "Full §6 contract declared now, forward fields inert with safe defaults (D-06)"

key-files:
  created:
    - backend/agents/workflows/__init__.py
    - backend/agents/workflows/plan.py
    - backend/agents/workflows/manifest.py
    - backend/tests/agents/test_manifest.py
  modified: []

key-decisions:
  - "Forward §6 fields modeled as minimal stub dataclasses (ToolPermissions/ModelPolicy/TaskSource/FixPolicy/FanoutSpec/RetryPolicy/RepoSpec/Limits/DeliverableSpec/ClarifySpec) rather than dict|None — type-complete now, still inert (D-06 discretion)"
  - "Used yaml.safe_load (not frontmatter.loads) — manifests are body-less pure YAML; cleaner fit and the cleaner safety story (T-04-03)"
  - "WorkflowManifest carries raw steps as list[dict]; typed Step construction is the compiler's job (04-03)"

patterns-established:
  - "ManifestValidationError(field) — every validation failure names the offending field/key (MAN-01)"
  - "_ALLOWED_TOP_KEYS frozenset + set-difference rejection enforces INV-5 strict-key policy"

requirements-completed: [MAN-01]

# Metrics
duration: 4min
completed: 2026-06-07
---

# Phase 04 Plan 02: Declaration Data Layer (plan.py + manifest.py) Summary

**Net-new `agents/workflows/` data layer: the full §6 `CompiledWorkflow`/`Step`/`Task` typed contract (D-06) plus a `yaml.safe_load`-backed `WorkflowManifest` loader that mirrors `agents/loader.py` and rejects unknown/DSL top-level keys by name (D-08/INV-5).**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-06-07T16:08:23Z
- **Completed:** 2026-06-07T16:12:08Z
- **Tasks:** 2
- **Files modified:** 4 (all created)

## Accomplishments
- Created the `agents/workflows/` package — the hexagonal data layer that imports only stdlib + `yaml` (no kernel/api import; import-linter green).
- `plan.py` declares the complete §6 contract now (D-06): `CompiledWorkflow`, `Step`, `Task`, with Phase-4-consumed fields populated and forward fields (`model`, `tools`, `validators`, `fix`, `compaction`, `fanout`, `on_conflict`, `retry`, `injects`, `repo`, `limits`) declared-but-inert via safe defaults. No Pydantic, no workflow-name/pipeline-id dispatch branch.
- `manifest.py` loads `workflow.yaml` into a typed `WorkflowManifest`, validates each required field naming any that is missing (MAN-01), rejects unknown top-level keys (strict-key, D-08/INV-5), permits `steps: []` (reverse_engineer stub, D-05), and parses with `yaml.safe_load` only (T-04-03).
- 15 tests cover the five required behaviors plus file-missing and non-mapping edge cases — all green.

## Task Commits

Each task was committed atomically:

1. **Task 1: plan.py — CompiledWorkflow/Step/Task §6 contract** — `a18337c` (feat)
2. **Task 2 (TDD RED): failing manifest loader tests** — `192c048` (test)
3. **Task 2 (TDD GREEN): manifest loader/validator implementation** — `fa2a39f` (feat)

_No REFACTOR commit — the GREEN implementation already mirrored the `loader.py` idiom cleanly._

**Plan metadata:** committed separately (docs).

## Files Created/Modified
- `backend/agents/workflows/__init__.py` - Package marker + hexagonal-direction docstring for the workflows data layer.
- `backend/agents/workflows/plan.py` - Full §6 typed contract: `CompiledWorkflow`/`Step`/`Task` + inert forward dataclasses (D-06).
- `backend/agents/workflows/manifest.py` - `WorkflowManifest` + `ManifestValidationError` + `load_manifest` (D-10/MAN-01/D-08).
- `backend/tests/agents/test_manifest.py` - 15 tests: load, named-field errors, strict-key rejection, `steps:[]`, safe_load, file-missing, non-mapping.

## Decisions Made
- **Forward types as stub dataclasses, not `dict|None`:** D-06 left this to discretion; minimal stub dataclasses make the §6 surface type-complete now while remaining inert (defaults encode the §6 least-privilege posture — `exec`/`network`/`secrets`/`spawn_subagents` OFF).
- **`yaml.safe_load` over `frontmatter.loads`:** manifests are body-less pure YAML, so `safe_load` is the cleaner read and the clearest T-04-03 safety story (RESEARCH Standard Stack endorsed either).

## Deviations from Plan

None - plan executed exactly as written. Two cosmetic in-task adjustments were made to docstrings so the acceptance-criteria source greps return their required zero counts (the acceptance greps for `if pipeline_type|== "prototype"` in plan.py and `yaml\.load\b|FullLoader` in manifest.py are intentionally exact-match; the original docstrings *mentioned* those tokens to explain what the code avoids). Reworded the explanatory docstrings to remove the literal tokens; behavior unchanged. Tracked here for transparency, not a deviation rule trigger.

## Issues Encountered
None — the loader pattern transferred directly. The plan.py false-positive grep on a docstring `if pipeline_type` mention and the manifest.py false-positive on a docstring `yaml.load` mention were both resolved by rewording the docstrings (no logic change).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- 04-03 (the compiler) can now build: it has both the `WorkflowManifest` source model and the typed `CompiledWorkflow`/`Step`/`Task` target, plus the 04-01 `CapabilityRegistry` for name validation.
- `load_manifest(workflow_id, base_dir)` is ready for the per-id `agents/workflows/<id>/workflow.yaml` files authored in a later plan.
- No blockers.

## Self-Check: PASSED

- FOUND: backend/agents/workflows/__init__.py
- FOUND: backend/agents/workflows/plan.py
- FOUND: backend/agents/workflows/manifest.py
- FOUND: backend/tests/agents/test_manifest.py
- FOUND commit: a18337c (Task 1)
- FOUND commit: 192c048 (Task 2 RED)
- FOUND commit: fa2a39f (Task 2 GREEN)

---
*Phase: 04-manifest-compiler-1a*
*Completed: 2026-06-07*
