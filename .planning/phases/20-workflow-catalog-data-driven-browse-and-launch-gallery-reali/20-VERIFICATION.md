---
phase: 20-workflow-catalog-data-driven-browse-and-launch-gallery-reali
verified: 2026-06-14T12:05:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
---

# Phase 20: Workflow Catalog — Data-Driven Browse-and-Launch Verification Report

**Phase Goal:** Replace the hardcoded home tiles with a data-driven catalog that reads the live `GET /api/workflows` list, shows only user-ready (`user_launchable`) workflows the user's tier entitles, and launches each through the EXISTING run flow — proving the SC-001 dividend (zero engine/kernel edits, no new tables/migrations), reuse-first.
**Verified:** 2026-06-14T12:05:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (the 5 ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Catalog renders ONLY `user_launchable` ∧ tier-entitled rows from a LIVE `GET /api/workflows` fetch; no hardcoded name list; `sample_*`/`*_revision`/`od_*` never appear | ✓ VERIFIED | `WorkflowCatalog.tsx:69` `rows.filter((w) => w.user_launchable)` (gate 1) + `:88,:159` `canRunPipeline(userTier, type)` (gate 2). `grep -c "const WORKFLOWS" WorkflowCatalog.tsx` = **0** (the CreationHub hardcoded array is GONE). Rows come from `getWorkflowDefinitions` → `api.ts:560 request("/api/workflows")`. Backend enumerates generically over `PIPELINE_AGENTS` (`workflows.py:187 for workflow_id in PIPELINE_AGENTS`), launchability sourced from `manifest.user_launchable` (`:229`), never a name literal. vitest + Playwright assert `*_revision`/`od_*` rows are never rendered (both green). |
| 2 | Idea-box workflows launch via EXISTING `run_pipeline` path; `prototype`/`ppt` route to the template wizard (no bare run); gated rows show the existing lock/upgrade affordance | ✓ VERIFIED | `WorkflowCatalog.tsx:102 onSelectFeature(type)` — the SAME `handleSelectFeature` the existing CreationHub uses (`DashboardLayout.tsx:1059` & `:1073` pass the identical callback). Wizard fork `:90-101` routes via `CHAIN_OPTIONS` (`workflowChaining.ts:40-41,52-53` ppt/prototype `requiresWizard:true wizardPath:/workflow/{type}/templates`) + explicit prototype/ppt fallback. Gated rows: `:177-199` `Lock` icon + `:189 Requires {TIER_LABELS[upgradeTo]} plan`. Playwright `TS-Z-02` proves an entitled idea-box row reaches `IdeaInputPage`; `TS-Z-01` proves the gated row is shown-locked (not hidden). |
| 3 | Net-new UI minimal + reuse-bound — catalog is a data-driven CreationHub mounted as ONE new DashboardLayout view; each new file names its analog | ✓ VERIFIED | `WorkflowCatalog.tsx:3-23` header names both analogs (AgentModelPicker fetch shell + CreationHub rows/launch/gating); row JSX classes copied verbatim. ONE new MainView value (`DashboardLayout.tsx:117 "catalog"`) + one `key="catalog"` view block (`:1064-1075`) + `handleNavigate` union (`:971`) + headerPage map (`:986`). AppHeader: one Catalog nav button (`:113-121`) copied from Library + `"catalog"` on both unions (`:25-26`). `api.ts:557 getWorkflowDefinitions` names its `getCapabilities` analog. No new Next route (`src/app/catalog/page.tsx` absent). |
| 4 | Backend additive-only — the 5 manifest fields surfaced via the EXISTING endpoint; NO new tables, NO migration | ✓ VERIFIED | `manifest.py:75-79` 5 inert fields (`user_launchable: bool = False` + 4 `str\|None = None`); surfaced through existing `list_workflows` (`workflows.py:195 load_manifest(workflow_id, _WORKFLOWS_DIR)` additive read, `:229-235` populate). `git status` → NO file under `backend/migrations`/`backend/alembic`; Phase-20 commits (`6e3bc097`/`0ad642f7`/`c96173d0`/`e5a4b419`/`ce62d96f`) touch no migration/engine/kernel/compiler. No new ORM table. |
| 5 | INV-3 parity (5 goldens byte-identical) + lint-imports 4/0 + Playwright + vitest pass + strict-key still rejects when/if/for/expr | ✓ VERIFIED | **RAN myself:** `SNAPSHOT_UPDATE= pytest test_characterization_{prototype,od_prototype,prototype_revision,od_ppt,app_builder}.py test_manifest_parity.py test_manifest.py test_workflows_api.py -q` → **85 passed** (goldens byte-identical, no baseline rewrite). `lint-imports` → **4 kept, 0 broken**. `test_rejects_unknown_key[when/if/for/expr]` → **4 passed** (INV-5 preserved). `npx vitest --run src/components/catalog` → **1 file 1 passed** (6 assertions: two gates, revision/od_* hidden, friendly-label fallback, raw-name suppression). `npx playwright test ts-z.catalog.spec.ts` → **3 passed** (filter + launch + tier un-gate; no `test.fixme` on load-bearing assertions). |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `backend/agents/workflows/manifest.py` | 5 inert fields + `_optional_bool`/`_optional_str` + 5 allow-list keys | ✓ VERIFIED | Fields `:75-79`; allow-list `:107-111`; `_optional_bool :304` accepts ONLY real bool (`:316 if not isinstance(value, bool): raise`) — inverts the int-subclass trap; `_optional_str :324`. |
| `backend/app/api/workflows.py` | `WorkflowSummary` + 4 fields; `list_workflows` populates off the manifest | ✓ VERIFIED | `:80-83` 4 summary fields; `:36,:39` imports `_WORKFLOWS_DIR`+`load_manifest`; `:195` guarded additive read → `:229-235` populate; degrades to defaults on load failure. |
| 7 × `workflow.yaml` | `user_launchable: true` on the 7 launchables; `launch_surface: wizard` on prototype/ppt only | ✓ VERIFIED | `grep -rl 'user_launchable: true'` → exactly app_builder/custom/dotnet_to_azure/mulesoft_to_springboot/ppt/prototype/user_stories. `launch_surface: wizard` → exactly ppt + prototype. No revision/od_*/reverse_engineer/chat YAML flagged. |
| `WorkflowCatalog.tsx` | data-driven CreationHub, two-gate filter, no WORKFLOWS const | ✓ VERIFIED | See Truth 1/2/3. WIRED into DashboardLayout, imported `:10`, mounted `:1073`. |
| `WorkflowCatalog.test.tsx` | vitest two-gate filter + friendly-label | ✓ VERIFIED | 5-fixture mixed list; 6 assertions; green. |
| `frontend/src/lib/api.ts` | `getWorkflowDefinitions` + `WorkflowSummary` type | ✓ VERIFIED | `:539` type; `:557` fetcher hitting `/api/workflows`. WIRED (imported by WorkflowCatalog `:35`). |
| `DashboardLayout.tsx` / `AppHeader.tsx` | catalog view + nav button | ✓ VERIFIED | View block `:1064-1075`; nav button `AppHeader.tsx:113-121`. |
| `e2e/tests/ts-z.catalog.spec.ts` | mocked Playwright: filter + launch + gating | ✓ VERIFIED | 3 tests, all green; per-spec `/api/workflows` route override. |

### Key Link Verification

| From | To | Via | Status |
| --- | --- | --- | --- |
| `workflows.py:list_workflows` | `manifest.load_manifest` | additive read alongside compile_for_run | ✓ WIRED (`:195`) |
| `workflow.yaml` | `WorkflowManifest.user_launchable` | declared top-level key | ✓ WIRED (7 YAMLs parse to True) |
| `WorkflowCatalog.tsx` | `api.getWorkflowDefinitions` → `/api/workflows` | mount useEffect | ✓ WIRED (`:66`) |
| `WorkflowCatalog.tsx` | `entitlements.canRunPipeline` | gate 2 | ✓ WIRED (`:88,:159`) |
| `DashboardLayout mainView==='catalog'` | `WorkflowCatalog onSelectFeature={handleSelectFeature}` | existing launch path | ✓ WIRED (`:1073`) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Goldens byte-identical + manifest/API tests | `SNAPSHOT_UPDATE= pytest <8 suites> -q` | 85 passed (36.8s) | ✓ PASS |
| Ports & Adapters | `/opt/homebrew/bin/lint-imports` | 4 kept, 0 broken | ✓ PASS |
| INV-5 strict-key | `pytest test_manifest.py::test_rejects_unknown_key -q` | 4 passed | ✓ PASS |
| FE two-gate filter | `npx vitest --run src/components/catalog` | 1 passed | ✓ PASS |
| Mocked e2e filter/launch/gating | `npx playwright test --project=mocked ts-z.catalog.spec.ts` | 3 passed (3.1s) | ✓ PASS |

### Requirements Coverage

Phase 20 declares process-invariant requirement tags (REUSE-MANDATE, SC-001, INV-3, INV-5, ADDITIVE-ONLY, ADDITIVE-BACKEND, PORTS-ADAPTERS) rather than REQUIREMENTS.md IDs; it realizes WF-DB-01 / closes ISS-015. All tags map to verified truths above (SC-001→Truth 1, REUSE-MANDATE→Truth 3, ADDITIVE→Truth 4, INV-3/INV-5/PORTS→Truth 5). No orphaned IDs.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| `backend/app/api/workflows.py` | 138,141 | "TBD" in `_describe()` reverse_engineer copy | ℹ️ Info | **Pre-existing** (git blame → commit `e2633391`, Phase 04-05; NOT introduced by Phase 20). Describes `reverse_engineer`'s empty-plan UI blurb, not unfinished Phase-20 work. No gate impact. |

No Phase-20-introduced debt markers, stubs, empty handlers, or hollow data paths. The catalog is wired end-to-end (manifest YAML → schema → API → fetch → two-gate render → existing launch).

### Human Verification Required

None. All criteria are verifiable offline and were verified by running the targeted suites. (Live-Bedrock visual confirmation of the gallery is not a phase blocker per project policy; the mocked Playwright spec covers the FE behavior deterministically.)

### Gaps Summary

No gaps. All 5 ROADMAP Success Criteria are met by shipped code, confirmed by reading the source (not the SUMMARY) and by running the goldens-parity suite (85 passed), lint-imports (4/0), the INV-5 strict-key test (4 passed), the FE vitest (1 passed), and the mocked Playwright spec (3 passed). Backend is additive-only with no migration; the FE catalog is genuinely data-driven (no `WORKFLOWS` const) with both gates AND'd and the existing launch path reused.

---

_Verified: 2026-06-14T12:05:00Z_
_Verifier: Claude (gsd-verifier)_
