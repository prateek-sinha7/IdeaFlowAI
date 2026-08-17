---
phase: quick-260720-9pt
plan: 01
subsystem: backend-agents
tags: [registry, discovery, single-source-of-truth, srp]
requires:
  - agents/loader.py list_agent_ids/load_agent_spec (the dynamic scan get_pipeline_agents already trusted)
provides:
  - agents/registry.py PIPELINE_AGENTS computed from agents/prompts/ at import time
  - app/api/workflows.py _KNOWN_WORKFLOW_IDS computed from agents/workflows/*/workflow.yaml (gated on SUPPORTED_PIPELINE_TYPES)
affects:
  - Adding a new agent to an existing pipeline no longer requires a registry.py edit
  - Adding a new pipeline still requires a workflow.yaml manifest to become launchable (unchanged requirement, now the ONLY requirement)
tech-stack:
  added: []
  patterns:
    - module-level discovery function computed once at import time, same public shape as before (dict[str, list[str]] / frozenset[str])
key-files:
  created:
    - backend/tests/agents/test_registry_discovery.py
  modified:
    - backend/agents/registry.py
    - backend/app/api/workflows.py
    - backend/CLAUDE.md
    - backend/tests/unit/test_workflows_api.py
    - backend/tests/agents/test_manifest_coverage.py
    - backend/tests/agents/test_manifest_parity.py
    - backend/tests/agents/test_compiled_plan_runs.py
    - backend/tests/agents/test_id_alias_resolver.py
    - backend/tests/integration/test_pipeline_workflows.py
    - backend/tests/unit/test_execution_engine.py
decisions:
  - PIPELINE_AGENTS is derived (scan), not hand-maintained — closes ISS-035/FIX-051
  - "ppt" stays an explicit one-line alias to "od_ppt" (no AGENT.md declares pipeline_type: ppt) — closes WR-01 at the root, zero changes to the 3 existing fallback call sites
  - "od_prototype" is excluded from PIPELINE_AGENTS entirely (a pure _OD_ALIAS_BASE id-alias, never a real pipeline_type) — matches original hand-maintained-dict behavior
  - _KNOWN_WORKFLOW_IDS = SUPPORTED_PIPELINE_TYPES ∩ (has agents/workflows/<id>/workflow.yaml) — NOT PIPELINE_AGENTS.keys() — so spec_kit (agents, no manifest) and sample_* (manifest, not a real pipeline_type) are both correctly excluded from GET /api/workflows
  - spec_kit's produces/consumes contracts are unfinished (clarify-agent consumes 'brief', nothing produces it) — left as a documented, explicit test carve-out, NOT fixed (out of scope; a product decision)
metrics:
  duration: ~90 min
  completed: 2026-07-20
---

# Quick 260720-9pt: Agent/Workflow Discovery Single Source of Truth Summary

Closed ISS-035: `PIPELINE_AGENTS` in `agents/registry.py` was a ~150-line hand-maintained literal dict that `get_all_agents_flat()`, `allowed_custom_agent_ids()`, and `app/api/workflows.py`'s workflow catalog all read directly — while `get_pipeline_agents()` (the function that actually drives pipeline execution) was already fully dynamic. The result: a new agent's `AGENT.md` was live for execution but invisible to the agent library, the custom-workflow allow-list, and `GET /api/workflows` until someone remembered to hand-edit the dict. Proven live: 8 fully-formed `spec_kit` agents existed on disk, discoverable by nothing except direct pipeline execution.

## What Was Built

**Root fix — `agents/registry.py`.** Replaced the literal `PIPELINE_AGENTS` dict with `_discover_pipeline_agents()`, computed once at import time by scanning every `SUPPORTED_PIPELINE_TYPES` value via the loader's own `list_agent_ids()` — the identical scan `get_pipeline_agents()` already trusted. The dict's public shape (`dict[str, list[str]]`) is unchanged, so every existing consumer (`get_all_agents_flat`, `allowed_custom_agent_ids`, the 3 WR-01 fallback call sites in `engine.py`/`websocket.py`/`workflows.py`) needed zero code changes. Two explicit exclusions preserve prior, correct behavior: `"ppt"` stays a one-line alias pointing at `"od_ppt"`'s agent list (no `AGENT.md` declares `pipeline_type: ppt`), and `"od_prototype"` (a pure `_OD_ALIAS_BASE` id-alias, resolved to `"prototype"` before any lookup) is excluded from the dict entirely, matching how the original hand-maintained dict never listed it either.

**Root fix — `app/api/workflows.py`.** `_KNOWN_WORKFLOW_IDS` used to mirror `PIPELINE_AGENTS.keys()`. Since `PIPELINE_AGENTS` now legitimately contains pipeline_types with agents but no manifest (`spec_kit`), that mirror would have 500'd `GET /api/workflows` (`compile_for_run` raising `FileNotFoundError`). Replaced with `_discover_manifest_ids()`: the intersection of `SUPPORTED_PIPELINE_TYPES` and directories under `agents/workflows/` that actually contain a `workflow.yaml` — the exact precondition `compile_for_run` requires. This also correctly keeps out the `sample_brownfield`/`sample_fanout`/`sample_wave` test-fixture manifest dirs (real files on disk, but not real pipeline_types), which ISS-015 already established must never surface as real workflows.

**Test-suite ripple (10 files).** Several existing tests were parametrized directly off `sorted(PIPELINE_AGENTS)` or `set(PIPELINE_AGENTS)` as a proxy for "the 15 compilable/dispatchable pipelines" — that proxy broke once `PIPELINE_AGENTS` legitimately grew. Each was re-scoped to the actual invariant it meant to test: manifest-backed ids for compile/dispatch tests (`test_manifest_coverage.py`, `test_manifest_parity.py`, `test_compiled_plan_runs.py`, `test_id_alias_resolver.py`), and an explicit `spec_kit` carve-out for the two DAG-structural-validation tests (`test_pipeline_workflows.py`, `test_execution_engine.py`) that correctly started catching `spec_kit`'s pre-existing unfinished `produces`/`consumes` contracts once its real agents became visible. New `test_registry_discovery.py` adds the actual drift-prevention pins: no orphaned agent, `get_all_agents_flat()` completeness (spec_kit proof), pre-fix-list parity (behavior-preserving safety net), and ppt/od_ppt alias correctness. `test_workflows_api.py` gained a parallel set for the manifest-discovery side (matches-disk, spec_kit-not-exposed, sample_*-not-exposed).

**Docs.** `backend/CLAUDE.md`'s "Adding an Agent" and "Adding a Pipeline" sections had a "Step 3 — Add the agent ID to PIPELINE_AGENTS" instruction; deleted (folded the note into the verify step) since that step no longer exists.

## Deviations from Plan

- The original `.investigations/hardcoded-agents/PLAN.md` didn't anticipate that `od_prototype` needed explicit exclusion from `PIPELINE_AGENTS` — this surfaced during verification (`test_id_alias_resolver.py`'s alias-identity test) and was root-caused to the same class of bug: `od_prototype` is a pure id-alias, not a real pipeline_type, and including it broke `resolve_alias(key) == key` for every "real" `PIPELINE_AGENTS` key. Fixed by excluding `_OD_ALIAS_BASE` keys from the scan — smaller footprint than anticipated, not larger.
- The plan anticipated ~2 files changing; the actual diff touched `agents/registry.py` + `app/api/workflows.py` (the real fix) plus 8 test files whose parametrize lists were implicitly coupled to the old literal dict's exact key set. All 8 were pre-existing couplings to the bug being fixed, not new work invented — each got the same "scope to manifest-backed ids" or "carve out spec_kit" treatment.
- 28 pre-existing test failures (4 unrelated root causes: `allowed_custom_agent_ids` cross-pipeline union, stale `clarify.defaults` snapshots, a stale FE-mirroring 4-vs-5-agent prototype list, one `dotnet_to_azure` launchable-flag assertion) were confirmed identical on the unmodified base branch and left untouched — out of scope for this fix.
