---
phase: quick-260629-wrb
plan: 01
subsystem: docs
tags: [backend, docs, manifest, execution-engine]
requires: []
provides: ["Updated backend architecture guide reflecting the manifest-driven runtime"]
affects: [backend/CLAUDE.md]
tech-stack:
  added: []
  patterns: []
key-files:
  created: []
  modified: [backend/CLAUDE.md]
decisions:
  - "context_from documented as legacy/vestigial (still parsed, not used by engine routing); produces/consumes is the live routing mechanism via _filter_consumed_outputs"
  - "Required workflow.yaml manifest step inserted as Step 4 (before optional REVISION_BASE_MAP, renumbered to Step 5) since the manifest references the agent ids"
metrics:
  duration: ~6 min
  completed: 2026-06-29
---

# Phase quick-260629-wrb Plan 01: Update backend CLAUDE.md (manifest-driven runtime) Summary

Surgically updated `backend/CLAUDE.md` so it documents the LIVE manifest-driven runtime
(compile_for_run → CompiledWorkflow from `agents/workflows/<id>/workflow.yaml`) instead of
the stale pre-manifest "registry + order-only" mental model — four verified-stale areas only,
every unrelated section byte-unchanged.

## What Was Built

Doc-only edit to one file, `backend/CLAUDE.md` (53 insertions, 16 deletions):

- **Fix 1 — Architecture Overview + Data Flow.** The Overview prose now states the full mental
  model: the engine compiles a typed `CompiledWorkflow` from a declarative manifest at run entry
  via `compile_for_run(pipeline_type)` and sources the agent sequence / deliverable / clarify /
  planner from it; per-step capabilities come from the manifest `steps`. The registry's narrower
  real role (membership/order via `PIPELINE_AGENTS` / `get_pipeline_agents()`) is preserved, with
  the split summarized crisply (registry = WHICH agents; manifest = HOW they run). The Data Flow
  diagram gained the compile seam (`compile_for_run` → `resolve_alias` →
  `load_manifest(agents/workflows/<id>/workflow.yaml)` → `_WORKFLOW_COMPILER.compile` → typed
  plan), the `FileNotFoundError`-on-missing-manifest note, and the membership-assertion
  `RuntimeError`-on-drift note. The narration paragraph was updated so the ordered sequence is
  sourced from the compiled plan while the registry supplies membership (asserted equal).
- **Fix 2 — Adding a Pipeline.** Added a new REQUIRED Step 4: create
  `agents/workflows/<id>/workflow.yaml` (declaring `steps` / `deliverable` / `clarify` /
  `planner`), citing the `FileNotFoundError` without it and the membership `RuntimeError` if the
  step agent-ids do not match `PIPELINE_AGENTS`; points the reader at
  `agents/workflows/prototype/workflow.yaml` as a template. The optional `REVISION_BASE_MAP` step
  was renumbered to Step 5.
- **Fix 3 — context_from routing claim.** The AGENT.md schema `context_from` row is marked
  legacy/vestigial (still parsed/stored, not used by engine routing); the `produces`/`consumes`
  row now documents the live routing rule (`set(upstream.produces) & set(this.consumes)` non-empty,
  content from `ectx.artifacts` via `_filter_consumed_outputs` / `_latest_typed_content`), keeping
  the `WorkflowResolver` DAG-validation mention. The "Adding a Pipeline" note inverted its
  emphasis, and a leading note was added to the `context_from` Examples subsection (examples kept
  for reference).
- **Fix 4 — factory function rename.** Replaced all 4 stale `_build_runner_tools` tokens with the
  live `_resolve_runner_tools` (Module Responsibilities table, Data Flow diagram, Tool Sets intro,
  Adding a custom runner tool).

## How to Verify

- `grep -c '_build_runner_tools' backend/CLAUDE.md` → `0`; `grep -q '_resolve_runner_tools' backend/CLAUDE.md` → present.
- Documented symbols exist in source: `def compile_for_run` (engine.py:423), the membership
  `raise RuntimeError` (engine.py:1401), `_filter_consumed_outputs` (engine.py:5395),
  `def _resolve_runner_tools` (factory.py:570), `_build_runner_tools` count in factory.py = 0.
- `git diff --name-only` lists only `backend/CLAUDE.md` (no `.py` source touched).
- Both task verify gates printed `OK-FIX1-2` and `OK-FIX3-4`.

## Deviations from Plan

None - plan executed exactly as written.

## Pre-edit Symbol Re-verification

All claims re-confirmed against the branch before editing (symbol names are the contract, line
numbers are guides):

| Symbol | Location confirmed |
|--------|--------------------|
| `compile_for_run(pipeline_type)` def / call | engine.py:423 / :1145 (raises FileNotFoundError on missing manifest) |
| membership assertion `raise RuntimeError` | engine.py:1401 (compares `[s.agent_id for s in compiled.steps]` vs `get_pipeline_agents` / `PIPELINE_AGENTS`) |
| `PIPELINE_AGENTS` / `get_pipeline_agents` | registry.py:29 / :223 |
| `_filter_consumed_outputs` / `_latest_typed_content` | engine.py:5395 / :4627 |
| `context_from` still parsed | loader.py:90 / :309 / :388 |
| `_resolve_runner_tools` def | factory.py:570 (called :186); `_build_runner_tools` count in factory.py = 0 |
| `load_manifest` / `resolve_alias` | manifest.py:124 / engine.py:408 |
| manifest exists | `agents/workflows/prototype/workflow.yaml` (keys: steps, deliverable, clarify, planner) |

## Commits

- b09aa561: docs(engine): document manifest-driven runtime in backend guide

## Self-Check: PASSED

- backend/CLAUDE.md: FOUND (modified, 53 insertions / 16 deletions)
- Commit b09aa561: FOUND in git log
- No `.py` source files modified: confirmed (`git diff --name-only` = `backend/CLAUDE.md` only)
