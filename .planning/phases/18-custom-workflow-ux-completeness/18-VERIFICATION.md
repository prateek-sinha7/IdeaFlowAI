---
phase: 18-custom-workflow-ux-completeness
verified: 2026-06-13T18:20:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
deferred:
  - truth: "ISS-019 — visual proof the 'WAVE / SUBAGENT TREE' heading bottom ≤ 950 at 1440×950 (no scroll) during an active wave run"
    addressed_in: "Deferred live Playwright UI pass (post-phase, default Bedrock profile)"
    evidence: "ROADMAP SC-3 + 18-CONTEXT deferred: offline proof is the className-contract assertion (verified); the TRUE pixel-fold proof runs in the dedicated Playwright pass. Memory: defer-live-verification-to-milestone-end."
  - truth: "ISS-021 — visual confirmation a live custom HTML deliverable renders in the sandboxed iframe (pixels)"
    addressed_in: "Deferred live Playwright UI pass (post-phase)"
    evidence: "18-REVIEW-FIX CR-01 recommends a human eyeball of the live custom render during the deferred Playwright pass; the unit tests assert the dispatch (verified)."
---

# Phase 18: Custom-Workflow UX Completeness Verification Report

**Phase Goal:** Close cluster E — custom-workflow deliverable rendering (ISS-021), delete the orphaned capability-palette composer + relocate the model picker (ISS-014), fix the wave-panel fold (ISS-019), WONTFIX the generic pipeline picker (ISS-015). FE-weighted + one INV-3-sensitive BE addition. SC-001, INV-3, additive-migrations-only.
**Verified:** 2026-06-13T18:20:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (the 5 ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Custom/unknown HTML deliverable renders in a sandboxed iframe via a GENERIC mimetype-dispatched renderer (md→markdown, zip→bundle), no per-workflow FE branch, on BOTH live + reopen (surfaces agree); resolved deliverable listed/downloadable in Files; BE emits `deliverable_mimetype`/`deliverable_filename` on `pipeline_complete`, both in `_VOLATILE_STRIP_KEYS`; iframe `sandbox="allow-scripts"` NO `allow-same-origin` on both surfaces. (ISS-021) | ✓ VERIFIED | BE: `engine.py:1924-1947` emits both keys from `getattr(ectx.deliverable,...)` via `_default_mimetype(_effective_strategy,...)`; `_mimetype.py` per-resolver defaults (stdlib-only, no boundary cross); `_normalize.py:139-140` both keys in `_VOLATILE_STRIP_KEYS`. FE live: `PreviewPanel.tsx:162-196` `GenericDeliverablePreview` dispatches text/html→`sandbox="allow-scripts"` iframe (`:181`, no allow-same-origin), text/markdown→MarkdownPreview, zip→AppBuilderIDEPreview; `KNOWN_RENDER_TYPES:379` = only the 4 known types (CR-01 fix `db725a56` removed `custom`); `page.tsx:404-426` live `custom` falls to generic `else`→`setGenericDeliverable` keyed on `data.deliverable_mimetype` (+`deriveDeliverableMimetype` fallback). FE reopen: `WorkflowHistory.tsx:277-285` structural `isGeneric` flag + shared `deriveDeliverableMimetype`, render `:570-591` HTML→`sandbox="allow-scripts"` iframe (`:577`). Files: `FilesTab.tsx:294-301` one generic row. Both surfaces import the SAME `deriveDeliverableMimetype` helper (`types/index.ts:342`) → cannot diverge. Tests: 45 vitest passed incl. CR-01 live-custom+html→sandboxed iframe (NOT MarkdownPreview), genericReopen, deriveDeliverableMimetype. |
| 2 | `WorkflowComposer.tsx` + `CapabilityPalette.tsx` deleted (0 import refs, build green); model picker relocated into live `AgentsPopup` with `model_overrides` reaching `run_pipeline` ONLY when non-default picked (empty selection byte-identical); `/api/capabilities` + `test_capabilities_api.py` retained + green. (ISS-014) | ✓ VERIFIED | Both files absent (ls→No such file); grep refs = only doc-comments, no imports; tsc clean. `AgentModelPicker.tsx` imported by `AgentsPopup.tsx:11`, rendered `:978-980` onChange→`onModelOverridesChange`→`IdeaInputPage.tsx:197-199` ref→`handleRun:229-237` includes `model_overrides` ONLY when `Object.keys(overrides).length>0` else omitted→`useWorkflow.ts:94-95` `Object.assign(payload, context)` single send site. `capabilities.py` + `test_capabilities_api.py` retained; `test_capabilities_api.py` → 8 passed. Byte-identical test: `IdeaInputPage.modelOverrides.test.tsx` asserts empty→no key + non-empty→`{model_overrides:{...}}`. |
| 3 | Left-column flex budget applied: column `flex flex-col overflow-hidden`; agent wrapper `flex-1 min-h-0`; wave wrapper `flex-shrink-0 max-h-[40%]` — CSS-only. (ISS-019; visual fold deferred) | ✓ VERIFIED (offline contract) | `DashboardLayout.tsx:1181` column `...flex flex-col overflow-hidden`; `:1183` agent wrapper `flex-1 min-h-0 overflow-hidden`; `:1215` wave wrapper `flex-shrink-0 max-h-[40%] overflow-y-auto`. No logic change to AgentProgressPanel/WaveTreePanel. `DashboardLayout.waveMount.test.tsx` green. Pixel-fold proof deferred (see Deferred Items). |
| 4 | ISS-015 dispositioned WONTFIX in the register with by-design rationale. (ISS-015) | ✓ VERIFIED | `ISSUES-REGISTER.md:24` + `:55` ISS-015 → "WONTFIX (by-design)" with full rationale (CreationHub closed launchable set; wizards collect template+design-system; template-gated-unreachable; sample_* fixtures; v2/WF-DB-01 guardrail). No code. |
| 5 | INV-3 parity holds (5 goldens byte-identical, lint-imports 4/0, zero new migrations); SC-001 honored (mimetype dispatch, no workflow-name FE branch — grep clean); FE tsc + vitest green. (INV-3/SC-001) | ✓ VERIFIED | 5 goldens (10 tests) + 17 mimetype unit tests → 27 passed (no SNAPSHOT_UPDATE). lint-imports → 4 kept / 0 broken. Zero new migration files (find newermt 2026-06-13 → none). SC-001 grep: no workflow-name render-decision literal in PreviewPanel.tsx/WorkflowHistory.tsx. tsc --noEmit → exit 0. Phase-18 vitest areas → 45 passed / 8 files. |

**Score:** 5/5 truths verified

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | ISS-019 visual fold proof (heading ≤ 950px at 1440×950, no scroll) | Deferred live Playwright pass | ROADMAP SC-3 + 18-CONTEXT: offline proof = className contract (verified); pixel proof deferred. Per phase brief: do NOT block on it. |
| 2 | ISS-021 live custom HTML pixel render | Deferred live Playwright pass | 18-REVIEW-FIX CR-01 recommends human eyeball; unit tests assert the dispatch (verified). |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/agents/workflows/plan.py` | `DeliverableSpec.mimetype` optional | ✓ VERIFIED | `:291 mimetype: str \| None = None` |
| `backend/agents/workflows/compiler.py` | `_compile_deliverable` reads `raw.get("mimetype")` | ✓ VERIFIED | `:688 mimetype=raw.get("mimetype")` |
| `backend/agents/capabilities/deliverables/_mimetype.py` | Per-resolver default mimetype (stdlib-only) | ✓ VERIFIED | `default_mimetype(strategy,name)`; single_file→ext infer, serialized_sandbox→zip, streamed_text→md, ppt→html |
| `backend/agents/execution_engine/engine.py` | Emits both keys on `pipeline_complete` | ✓ VERIFIED | `:1940-1941`; WR-01 `_effective_strategy` fallback fix `:1848-1857` |
| `backend/tests/agents/characterization/_normalize.py` | Both keys in `_VOLATILE_STRIP_KEYS` | ✓ VERIFIED | `:139-140` |
| `backend/tests/unit/test_deliverable_mimetype.py` | Default + emission coverage | ✓ VERIFIED | 17 tests pass |
| `frontend/src/components/preview/PreviewPanel.tsx` | Generic mimetype dispatch + sandboxed iframe | ✓ VERIFIED | `GenericDeliverablePreview`; `custom` removed from KNOWN_RENDER_TYPES |
| `frontend/src/components/history/WorkflowHistory.tsx` | Reopen generic fallback (sandbox/md/bundle) | ✓ VERIFIED | `:277-285`,`:570-591` |
| `frontend/src/app/dashboard/page.tsx` | Generic channel for unknown type (live+reopen) | ✓ VERIFIED | `:404-426`, shared derive helper |
| `frontend/src/components/results/FilesTab.tsx` | One generic deliverable row | ✓ VERIFIED | `:294-301` |
| `frontend/src/types/index.ts` | event typing + shared `deriveDeliverableMimetype` | ✓ VERIFIED | `:302-303`,`:311`,`:342` |
| `frontend/src/components/layout/DashboardLayout.tsx` | Flex-budgeted left column (CSS-only) | ✓ VERIFIED | `:1181`,`:1183`,`:1215` |
| `frontend/src/components/workflow/AgentsPopup.tsx` | Relocated model picker wired to model_overrides | ✓ VERIFIED | `:11`,`:978-980`,`onModelOverridesChange` |
| `.planning/ISSUES-REGISTER.md` | ISS-015 WONTFIX disposition | ✓ VERIFIED | `:24`,`:55` |
| `WorkflowComposer.tsx` / `CapabilityPalette.tsx` | DELETED | ✓ VERIFIED | Both absent; 0 import refs |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| engine.py | ectx.deliverable | getattr mimetype/name | ✓ WIRED | `:1924,:1930` |
| _normalize.py | _VOLATILE_STRIP_KEYS | frozenset membership | ✓ WIRED | `:139-140` |
| page.tsx pipeline_complete | generic content channel | data.deliverable_mimetype for unknown type | ✓ WIRED | `:420-425` |
| PreviewPanel.tsx | sandboxed iframe / markdown / bundle | mimetype dispatch on fallback | ✓ WIRED | `:173,:189,:194` |
| WorkflowHistory.tsx | sandboxed iframe / markdown / bundle | generic-mimetype fallback (reopen heuristic) | ✓ WIRED | `:279,:284,:570,:586` |
| AgentsPopup model picker onChange | run_pipeline model_overrides | IdeaInputPage extraParams → DashboardLayout → startPipeline merge | ✓ WIRED | AgentsPopup:978→IdeaInputPage:197/229→useWorkflow:95 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| GenericDeliverablePreview | deliverable.content | live: pipeline_complete `final_output`+`deliverable_mimetype`; reopen: `selectedOutput`+derived mimetype | Yes (real resolved deliverable bytes from `ectx.deliverable`) | ✓ FLOWING |
| FilesTab generic row | genericDeliverable.content | same channel as preview | Yes | ✓ FLOWING |
| model_overrides | modelOverridesRef | AgentModelPicker selection | Yes (only when non-default picked) | ✓ FLOWING (conditional-by-design) |

### Behavioral Spot-Checks / Probe Execution

| Check | Command | Result | Status |
|-------|---------|--------|--------|
| 5 characterization goldens byte-identical | pytest 5 char files | 10 passed | ✓ PASS |
| Mimetype default/emission unit | pytest test_deliverable_mimetype.py | 17 passed | ✓ PASS |
| Import boundaries | lint-imports | 4 kept / 0 broken | ✓ PASS |
| capabilities API retained | pytest test_capabilities_api.py | 8 passed | ✓ PASS |
| FE typecheck | tsc --noEmit | exit 0 | ✓ PASS |
| FE phase-18 suites | vitest (preview/history/types/layout/modelOverrides) | 45 passed / 8 files | ✓ PASS |
| New migrations | find -newermt 2026-06-13 migrations | none | ✓ PASS |

### Requirements Coverage

Phase requirement IDs are ISSUE IDs (ISS-021/014/019/015), not REQUIREMENTS.md REQ-IDs — no REQ-traceability flag applies. ISS-014 doc-reconciliation against REQUIREMENTS API-06 + IMPLEMENTATION-REGISTER §855/§1207 verified present (deletion-as-superseded ledger note).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | No TBD/FIXME/XXX in any phase-18-modified file | — | — |

Pre-existing FE failures (`workflowChaining.test.ts`, `AgentProgressPanel.test.tsx` — 7 cases) are documented in `deferred-items.md`, confirmed identical before/after the 18-04 deletion, and last touched in commits `4889e3a8`/`a219fade` (pre-phase-18). Neither file is a phase-18 deliverable. NOT a phase-18 gap.

### Human Verification Required

None gating. The TWO visual confirmations (ISS-019 fold pixels, ISS-021 live custom HTML render) are recorded as DEFERRED follow-ups for the dedicated Playwright pass per the phase contract and the defer-live-verification memory note — they do NOT block phase completion. Offline className-contract + dispatch-unit proofs are VERIFIED.

### Gaps Summary

No gaps. All 5 ROADMAP Success Criteria are verified against actual code:
- ISS-021 BE emits both keys (parity-neutral via `_VOLATILE_STRIP_KEYS`); FE renders generically on both live + reopen surfaces with matching sandboxed iframes (`sandbox="allow-scripts"`, no `allow-same-origin`) and a shared derive helper guaranteeing agreement. The CR-01 blocker (live `custom`→escaped HTML) is closed: `custom` removed from `KNOWN_RENDER_TYPES`, regression-tested.
- ISS-014 deletion is import-clean; model picker relocated + wired with the empty-selection byte-identical guard; `/api/capabilities` + test retained and green.
- ISS-019 className contract applied (CSS-only); pixel proof deferred to Playwright.
- ISS-015 WONTFIX recorded with rationale.
- INV-3 holds (5 goldens, 4/0 imports, 0 migrations); SC-001 holds (mimetype dispatch, no workflow-name FE branch, grep clean); tsc + vitest green.

---

_Verified: 2026-06-13T18:20:00Z_
_Verifier: Claude (gsd-verifier)_
