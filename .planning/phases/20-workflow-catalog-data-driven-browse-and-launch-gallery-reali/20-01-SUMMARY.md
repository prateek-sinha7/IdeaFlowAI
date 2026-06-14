---
phase: 20-workflow-catalog-data-driven-browse-and-launch-gallery-reali
plan: 01
subsystem: backend
tags: [workflow-catalog, manifest, api, additive, inv-3, inv-5, sc-001]
requires:
  - "agents.workflows.manifest.load_manifest (2-arg) + WorkflowManifest dataclass"
  - "agents.execution_engine.engine._WORKFLOWS_DIR (the resolved workflows base dir)"
  - "app.api.workflows.list_workflows (existing authenticated GET /api/workflows)"
provides:
  - "WorkflowManifest.user_launchable/display_name/description/icon/launch_surface (inert catalog fields)"
  - "manifest._optional_bool / manifest._optional_str validation helpers"
  - "WorkflowSummary.user_launchable/display_name/icon/launch_surface (API response fields)"
  - "user_launchable: true on 7 launchable workflow.yaml manifests (+ launch_surface: wizard on prototype/ppt)"
affects:
  - "Plan 20-02 frontend WorkflowCatalog (consumes GET /api/workflows user_launchable + launch_surface)"
tech-stack:
  added: []
  patterns:
    - "Additive-inert manifest field: default False/None, never read by compiler/kernel → goldens byte-identical (INV-3)"
    - "Bool-accept-only coercion (_optional_bool) — inverts the _optional_int int-subclass reject trap"
    - "Declared per-row trust/visibility flag surfaced over PIPELINE_AGENTS (no hardcoded name list) — SC-001"
key-files:
  created: []
  modified:
    - "backend/agents/workflows/manifest.py"
    - "backend/app/api/workflows.py"
    - "backend/agents/workflows/app_builder/workflow.yaml"
    - "backend/agents/workflows/user_stories/workflow.yaml"
    - "backend/agents/workflows/custom/workflow.yaml"
    - "backend/agents/workflows/mulesoft_to_springboot/workflow.yaml"
    - "backend/agents/workflows/dotnet_to_azure/workflow.yaml"
    - "backend/agents/workflows/prototype/workflow.yaml"
    - "backend/agents/workflows/ppt/workflow.yaml"
    - "backend/tests/agents/test_manifest.py"
    - "backend/tests/unit/test_workflows_api.py"
decisions:
  - "Skipped resolve_alias in list_workflows: it iterates real PIPELINE_AGENTS keys (never aliases), so load_manifest(workflow_id, _WORKFLOWS_DIR) is called with the real id directly (per plan read_first, overriding PATTERNS §8's illustrative resolve_alias)."
  - "Guarded the additive manifest read with try/except → manifest=None → defaults, so a single bad manifest cannot break the whole listing (mirrors the _spec_by_id posture)."
  - "BE WorkflowSummary intentionally omits a separate description field — manifest.description feeds the EXISTING description as a fallback (manifest.description or _describe(...))."
metrics:
  duration: "~12 min"
  completed: "2026-06-14"
  tasks: 3
  files: 11
---

# Phase 20 Plan 01: Workflow Catalog Data-Driven Backend Surface Summary

Additive, inert `user_launchable` (+ `display_name`/`description`/`icon`/`launch_surface`) catalog metadata landed on the `WorkflowManifest` schema and surfaced through the existing authenticated `GET /api/workflows`, with launchability sourced from a declared manifest flag enumerated generically over `PIPELINE_AGENTS` (never a hardcoded name list) — proven not to perturb the 5 INV-3 goldens, keep `when/if/for/expr` rejected (INV-5), and add no source→forbidden import edge (lint-imports 4/0).

## What Was Built

- **Task 1 — manifest schema (TDD):** Added 5 inert fields to `WorkflowManifest` (`user_launchable: bool = False`, `display_name`/`description`/`icon`/`launch_surface: str | None = None`), widened `_ALLOWED_TOP_KEYS` with exactly those 5 presentation/visibility keys, and added two helpers: `_optional_bool` (accepts ONLY a real bool — inverts the `_optional_int` int-subclass trap so `user_launchable: 1` is rejected) and `_optional_str` (returns `str | None`). Wired 5 extraction lines + 5 constructor kwargs into `_build_manifest`. New tests prove parse-all, defaults-when-absent, bool-reject, and str-reject; the INV-5 strict-key test is untouched and green.
- **Task 2 — API surfacing + YAML flags (TDD):** Extended `WorkflowSummary` with the 4 fields, imported `_WORKFLOWS_DIR` from `agents.execution_engine.engine` and `load_manifest` from `agents.workflows.manifest`, and additively read the manifest in `list_workflows` (guarded → defaults on failure) to populate `user_launchable`/`display_name` (fallback to `_display_name`)/`icon`/`launch_surface`, plus prefer `manifest.description` for the existing description field. Flagged `user_launchable: true` on the 5 plain launchables (app_builder/user_stories/custom/mulesoft_to_springboot/dotnet_to_azure) and added `user_launchable: true` + `launch_surface: "wizard"` to prototype/ppt. New `test_list_carries_launchable_flags` pins the launchable set; `test_list_returns_all_authored_workflows` stays unchanged.
- **Task 3 — invariant proof (verification-only):** Ran the 5 named characterization golden suites + `test_manifest_parity.py` + `test_manifest.py` + `test_workflows_api.py` with NO `SNAPSHOT_UPDATE` (85 passed, goldens byte-identical) and `lint-imports` (4 kept / 0 broken). No migration file created.

## Verification Evidence

- `cd backend && SNAPSHOT_UPDATE= python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py tests/agents/test_manifest_parity.py tests/agents/test_manifest.py tests/unit/test_workflows_api.py -q` → **85 passed** (5 goldens RUN byte-identical, no baseline rewrite — INV-3).
- `/opt/homebrew/bin/lint-imports` → **4 contracts kept, 0 broken** (PORTS-ADAPTERS; no new source→forbidden edge — the new `app → agents.execution_engine` import is a permitted direction).
- `grep -rl 'user_launchable: true' agents/workflows/*/workflow.yaml` → exactly the 7 launchables; `grep -rl 'launch_surface: .wizard'` → exactly prototype + ppt; no other YAML touched.
- `git status` → no new file under `backend/migrations` / `backend/alembic` (ADDITIVE-ONLY).
- Task-level suites green: `test_manifest.py` (19 passed, incl. preserved `test_rejects_unknown_key[when/if/for/expr]`), `test_workflows_api.py` (24 passed, incl. preserved `test_list_returns_all_authored_workflows`).

## Deviations from Plan

None — plan executed exactly as written. The only choice point (resolve_alias) was pre-resolved by the plan's read_first (call `load_manifest` with the real id directly), which this execution followed.

## Authentication Gates

None — no auth gates, no package installs (pure source/data + tests, per threat T-20-SC).

## Known Stubs

None — the new fields are intentionally inert catalog metadata (default False/None) consumed by the read endpoint; they are wired end-to-end (manifest YAML → schema → API response). Frontend consumption lands in Plan 20-02.

## Self-Check: PASSED
