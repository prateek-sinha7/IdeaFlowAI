---
phase: 37-configure-unification-composer-wizard-b3
plan: 01
subsystem: api
tags: [launch-boundary, od_context, opendesign, context_providers, declared-signal, hexagonal, INV-3, SC-001]

# Dependency graph
requires:
  - phase: earlier-manifest-compiler
    provides: CompiledWorkflow.context_providers (declared capability names) + resolve_alias/compile_for_run
provides:
  - "app/api/launch_context.py::resolve_launch_od_context — shared declared-signal od_context seam"
  - "Both launch boundaries (REST + WS) rewired to declared-signal eligibility; od_prototype/od_ppt name-branch deleted"
  - "A new deliverable gains template/DS acceptance by declaring context_providers:[opendesign] — zero engine/boundary edit"
affects: [composer, wizard, dynamic-workflow-composition, future-opendesign-deliverables]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Declared-signal eligibility at the app boundary (manifest context_providers, not workflow-name literals)"
    - "Name-free legacy-alias discrimination via agents.registry._OD_ALIAS_BASE (single source of truth)"
    - "Boundary-only seam: app-side, imports only agents.* ports + od_context loaders (import-linter 4/0)"

key-files:
  created:
    - backend/app/api/launch_context.py
  modified:
    - backend/app/api/run_commands.py
    - backend/app/api/websocket.py
    - backend/tests/unit/test_rest_run_launch.py

key-decisions:
  - "Eligibility = declared opendesign AND pipeline_type not in _OD_ALIAS_BASE.values() — byte-preserves the legacy od_prototype-vs-bare-prototype split without a name literal"
  - "od_ppt_revision per-boundary behavior preserved: REST -> od_context None; WS -> non-fatal ppt loader (fatal=False)"
  - "Loader-profile selection kept as a documented compatibility shim keyed on the resolved base family (generic declaration deferred, RESEARCH Open Question 2)"

patterns-established:
  - "Declared manifest signals drive boundary behavior; kernel/boundary knows no workflow by name (SC-001/INV-1)"

requirements-completed: [SHELL-04]

# Metrics
duration: 40min
completed: 2026-07-09
---

# Phase 37 Plan 01: Declared-Signal od_context Launch Seam (D-15/C) Summary

**Promoted template/design-system od_context from a prototype-hardcoded run-launch name-branch to a shared declared-signal seam (`context_providers:[opendesign]`) that both the REST and WS launch boundaries call — byte-identical for prototype/PPT, engine untouched.**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-07-09
- **Tasks:** 3 (2 code commits + 1 verification-only)
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments

- Created `app/api/launch_context.py::resolve_launch_od_context` — the single app-side seam that keys od_context eligibility on the DECLARED manifest signal instead of the `pipeline_type == "od_prototype"/"od_ppt"` literals (SC-001/INV-1 leak closed).
- Rewired BOTH launch boundaries to the seam (`run_commands.py::_resolve_launch_agents` REST, `websocket.py::_handle_workflow_execution` WS) and DELETED the name-literal eligibility branch. `resolve_launch_od_context` is defined once and called from both boundaries (no dual impl — INV-3/INV-12).
- Proved ADDITIVE: the 5 characterization goldens are byte-identical with `SNAPSHOT_UPDATE` unset (`git status --porcelain golden/` EMPTY), import-linter 4 kept / 0 broken, and `engine.py` / all runners UNCHANGED (INV-13).

## The 3-manifest opendesign audit (Task 1 finding)

`grep -rn 'opendesign' agents/workflows/*/workflow.yaml | grep 'context_providers'` returns EXACTLY THREE manifests declaring `context_providers: [opendesign]`:

- `agents/workflows/prototype/workflow.yaml`
- `agents/workflows/od_ppt/workflow.yaml`
- `agents/workflows/od_ppt_revision/workflow.yaml`

This **contradicts RESEARCH assumption A1 ("two")** and confirms the plan's PLAN-TIME FINDING ("three"). The seam therefore had to preserve `od_ppt_revision`'s exact per-boundary behavior, not just prototype/od_ppt.

## Task Commits

1. **Task 1: declared-signal od_context launch-parity cases (TDD RED)** - `c77ccc1f` (test)
2. **Task 2: declared-signal seam + both boundaries rewired** - `39e9a67e` (feat)
3. **Task 3: ADDITIVE byte-identity proof** - verification-only, no source changes (folded into this SUMMARY; no code commit)

Baseline before work: `20d28142`.

## Files Created/Modified

- `backend/app/api/launch_context.py` - NEW: `resolve_launch_od_context()` — name-free declared-signal eligibility + preserved loader-profile shim + fatal/non-fatal arms.
- `backend/app/api/run_commands.py` - `_resolve_launch_agents` rewired to the seam (fatal=True); od_prototype/od_ppt name-branch deleted; od_ppt_revision kept `None` on REST.
- `backend/app/api/websocket.py` - `_handle_workflow_execution` rewired to the seam; name-branch deleted; od_ppt_revision non-fatal arm (fatal=False, "only if template_id") preserved.
- `backend/tests/unit/test_rest_run_launch.py` - NEW od_context-parity (dict-equality), undeclared→None, unknown-type rejection, REST od_ppt_revision→None, and seam fatal/non-fatal cases.

## Seam design (byte-identity mechanism)

`resolve_launch_od_context(pipeline_type, template_id, design_system_id, *, custom_ds_body, custom_template_body, fatal)` returns `(base_pipeline_type, od_context)`:

1. `base_pipeline_type = resolve_alias(pipeline_type)` (single alias source).
2. Peek `compile_for_run(pipeline_type).context_providers` (wrapped in `try/except FileNotFoundError` → `(base, None)` so an unknown id is rejected by the caller's `SUPPORTED_PIPELINE_TYPES` gate — no path traversal).
3. Eligibility: `"opendesign" in context_providers` **AND** `pipeline_type not in _OD_ALIAS_BASE.values()`.
4. Loader-profile by base family: `prototype` → `load_prototype_od_context`; od_ppt-family (`od_ppt`, `od_ppt_revision`) → `load_ppt_od_context`, with the OLD per-branch argument shaping reproduced verbatim (`design_system_id or ""` for prototype; raw `design_system_id` for od_ppt).
5. Fatality: `fatal=True` propagates `LookupError` (caller shapes rejection, V5 preserved); `fatal=False` swallows → `None` (reproduces websocket.py:1741-1753).

## Decisions Made

- **Eligibility discriminator (`_OD_ALIAS_BASE.values()`):** A plain base whose OpenDesign flavor is a dedicated `od_` alias is NOT self-OD-eligible; its OD context is requested by launching the alias. This byte-preserves the legacy `od_prototype`-vs-bare-`prototype` split (see deviation #1) without any workflow-name literal, sourced from the single alias source of truth. A brand-new deliverable that declares `opendesign` and has NO legacy `od_` alias still opts in when launched by its own name — the D-15/C win.
- **Loader-profile shim retained** (FIXME documented in-code): generic loader-profile declaration deferred to a follow-up; byte-preserving because only the three audited manifests declare `opendesign` today.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug/Regression prevention] Added a name-free exclusion so bare `prototype` keeps `od_context=None`**
- **Found during:** Task 2 (seam design)
- **Issue:** The plan specified eligibility = "manifest declares opendesign" (`compile_for_run(pipeline_type).context_providers`). But the base `prototype` manifest ALSO declares `opendesign` (its OD flavor is the dedicated `od_prototype` alias). A pure declared-signal check would newly LOAD od_context (and fatally reject on a bare launch) for `pipeline_type == "prototype"`, where the old name-branch loaded nothing → `od_context None`. That change breaks the existing INV-3 behavioral test `tests/unit/test_pipeline_failure_semantics.py::test_bare_prototype_without_template_rejected_at_ingress`, which pins bare `prototype` → exactly one `missing_template_context` error with the engine never invoked. The plan under-specified this legacy-alias asymmetry.
- **Fix:** Eligibility additionally requires `pipeline_type not in _OD_ALIAS_BASE.values()` (`= {"prototype"}`), derived from the single alias source of truth — no name literal. Bare `prototype` stays `od_context None` → the downstream 13-06 `missing_template_context` guard fires unchanged.
- **Files modified:** backend/app/api/launch_context.py
- **Verification:** `tests/unit/test_pipeline_failure_semantics.py` 8/8 green (bare-prototype guard preserved) AND `tests/unit/test_rest_run_launch.py` 17/17 green; goldens byte-identical.
- **Committed in:** `39e9a67e` (Task 2 commit)

**2. [Rule 2 - Preserve mandated per-boundary behavior] REST `od_ppt_revision` kept `od_context=None`**
- **Found during:** Task 2 (REST rewire)
- **Issue:** `od_ppt_revision` declares `opendesign`, so the shared seam would load it. The REST launch twin never loaded od_context for the revision arm (WS owns the non-fatal template load; REST fell through to `None`). A uniform seam call would flip REST from `None` to load-or-reject — forbidden by guardrail #2 ("REST never reaches it / None"). The plan's literal REST instruction ("call the seam, fatal=True") omitted this.
- **Fix:** REST `_resolve_launch_agents` keeps an explicit `od_ppt_revision → None` arm before the general seam call (passes the SC-001 grep, which forbids only the `od_prototype`/`od_ppt` literals). WS retains its non-fatal `od_ppt_revision` arm via `fatal=False`.
- **Files modified:** backend/app/api/run_commands.py, backend/app/api/websocket.py
- **Verification:** `test_od_ppt_revision_rest_keeps_none` + WS non-fatal seam cases green.
- **Committed in:** `39e9a67e` (Task 2 commit)

---

**Total deviations:** 2 (both behavior-preserving / regression-preventing; no scope creep).
**Impact on plan:** Both deviations are required to hold INV-3 byte-identity that the plan's literal declared-signal instruction would otherwise have broken for the legacy-alias cases. The core D-15/C win (declared-signal eligibility, name-branch deleted) is delivered exactly as specified.

## Issues Encountered

- None beyond the two deviations above. The naive "declared opendesign only" eligibility was caught before commit by running `test_pipeline_failure_semantics.py` (not in the plan's verify list but an INV-3 behavioral pin) and corrected in the seam.

## Verification Evidence

- **SC-001 grep** `pipeline_type == "od_prototype"|pipeline_type == "od_ppt"` on both boundary files: **0 hits** (comments reworded to avoid the literal).
- **Seam def+callsites** `grep -rc resolve_launch_od_context app/api/`: launch_context.py=1 (def), run_commands.py=3, websocket.py=4 (>= 3 def+2 callsites).
- **Goldens + launch suite** (SNAPSHOT_UPDATE unset): **27 passed, 0 failed, 0 skipped** (5 characterization suites + test_rest_run_launch.py).
- **Byte-identity** `git status --porcelain backend/tests/agents/characterization/golden/`: **EMPTY**.
- **import-linter** (run from backend/): **Contracts: 4 kept, 0 broken.**
- **Engine/runner guard** `git diff --name-only 20d28142..HEAD`: only the 4 plan files; NO `execution_engine/engine.py`, NO runner (INV-13 held).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- D-15/C landed: template/DS is a declared run input any deliverable can opt into by declaring `context_providers:[opendesign]`, with zero engine/boundary edit — unblocking composer/wizard custom-workflow OD opt-in.
- LIVE-DEFERRED: a live run-launch with a non-prototype deliverable declaring template/DS (needs live Bedrock + server) is deferred per the plan's verification note.
- Follow-up (documented FIXME): generic loader-profile declaration (RESEARCH Open Question 2) — deferred, byte-preserving today.

## Self-Check: PASSED

- FOUND: backend/app/api/launch_context.py
- FOUND: commit c77ccc1f (Task 1)
- FOUND: commit 39e9a67e (Task 2)
- Golden tree byte-identical (empty porcelain); engine.py/runners unchanged.

---
*Phase: 37-configure-unification-composer-wizard-b3*
*Completed: 2026-07-09*
