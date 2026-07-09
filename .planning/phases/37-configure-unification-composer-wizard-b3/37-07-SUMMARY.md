# 37-07 — Unified WizardStepper launch page (prototype + ppt) — SUMMARY

**Status:** COMPLETE (offline-verified). Live `/dashboard` launch → Phase-34 live-deferred.
**Branch:** feat/ui-2. **Commits (atomic, per task):**
- `f4719f27` extract launch-contract serialization + freeze golden parity gate
- `cc109721` unified WizardStepper-hosted LaunchWizard page (prototype + ppt)
- `3a1db670` repoint launch entry points to unified /workflow/create
- `3b5d6f70` retire the route-split template pages (LaunchWizard is sole impl)

## What shipped

BOTH flagship launch flows (prototype + ppt) rebuilt into ONE generic, mode-keyed
page — `src/components/workflow/LaunchWizard.tsx`, mounted at the new reachable route
`src/app/workflow/create/page.tsx` (`?mode=prototype|ppt`). It hosts the plan-37-04
`WizardStepper` chrome (Template → Design System → Discovery + a Web/Deck toggle via
render-slots) and wraps it with the brief, review gates, agent composer (`AgentsPopup`),
save-workflow, and launch affordances. The two retired route-split pages are DELETED.

The wizard→dashboard hand-off serialization (previously inlined byte-identically in the
two pages) is extracted to `src/lib/launchDraft.ts` as the single source of truth
(`buildLaunchDraft` / `buildDiscoveryValue`) — INV-12 no dual implementation.

## ⭐ Contract-parity proof (the binding offline gate) — BYTE-IDENTICAL, per mode

The retired flow is the ORACLE. Its exact sessionStorage hand-off is frozen in golden
fixtures (`src/components/workflow/__fixtures__/launchContract.ts`) and proven THREE ways:

1. **Render-oracle (transitional, now retired with the pages; in git history at
   `f4719f27`/`cc109721`):** rendered the REAL `prototype/templates` + `ppt/templates`
   pages, drove 6 scenarios (base, blank-canvas, ds-not-required, custom-bodies + chain +
   gates + levers) and asserted their live `handleContinue` output === the goldens. GREEN.
   This RED-first characterization caught a real assumption bug: for ppt,
   `designSystemId = dsRequired ? selectedDsId : null`, and a custom ppt template forces
   `dsRequired=false` → `designSystemId:null` — the goldens were corrected against reality.
2. **Durable parity gate — `src/lib/launchDraft.parity.test.ts` (12 assertions):**
   `buildLaunchDraft(mode, inputs)` === the frozen goldens, byte-for-byte, per mode.
3. **Real-component parity — `src/components/workflow/LaunchWizard.test.tsx`:** the REAL
   `LaunchWizard` render's launch output === the goldens (base proto, blank canvas, ppt
   base, ppt ds-null, mode-toggle→ppt).

Per-mode contract confirmed identical to the old flow:
- prototype → `prototype.draft` + `od_prototype.pending="true"` (+ `prototype.discovery`
  when the Discovery step is engaged; cleared otherwise — matches the old discovery route's
  Generate/Skip, and the old templates flow's no-discovery=null).
- ppt → `ppt.draft` + `od_ppt.pending="true"` (`designSystemId = dsRequired ? id : null`).
- Draft key order preserved exactly: `templateId, designSystemId, brief, [customDsBody],
  [customTemplateBody], [sourceRunId], [gateAgentIds], [modelOverrides], [selections],
  [images], agentIds`. The dashboard consumer (`dashboard/page.tsx` ~216–279 / ~952–1072)
  reads this unchanged.

## Behavior-port checklist (13 live behaviors — all ported + test-covered)

| # | Behavior | Ported | Evidence |
|---|----------|--------|----------|
| 1 | Brief input | ✓ | textarea (aria-label="Brief"); a11y test |
| 2 | File-attach + text extraction | ✓ | `onFilesPicked` + `extractFileText` (verbatim) |
| 3 | Out-of-band images (D3) | ✓ | `attachedImages` → draft `images`; golden scenario |
| 4 | Speech-to-text | ✓ | `useSpeechRecognition` + transcript mirror |
| 5 | Example-prompt | ✓ | "Use template example" fills brief; test |
| 6 | Chaining (panel/banner/prefill) | ✓ | chain.* pickup + `finalBrief` compose; chaining test |
| 7 | Custom-template modal | ✓ | `onSelectCustomTemplate` via stepper slots |
| 8 | Custom-DS modal | ✓ | `DesignSystemPicker onSelectCustom` (ds slot) |
| 9 | Blank-canvas | ✓ | `onWebSelect(null)` → templateId:null; test |
| 10 | Review gates | ✓ | `ReviewGatesSection`; gates test threads gateAgentIds |
| 11 | AgentsPopup composer | ✓ | reused as-is (Model lever intact; no AgentModelPicker mount) |
| 12 | Save-workflow | ✓ | `createUserWorkflow` + `_wizard` config; save test |
| 13 | Draft restore/clear | ✓ | one-shot draft hydrate + FIX-005 clear; restore test |

## Entry-point repoints (→ /workflow/create?mode=…)

- `CreationHub.tsx` (2) — NOTE: already superseded by `HomeLaunchGrid` (not mounted); repointed defensively.
- `HomeLaunchGrid.tsx` (2) — the live landing.
- `DashboardLayout.tsx` (2) — saved-workflow restore path (writes `*.draft` then navigates).
- `workflowChaining.ts` (2) — `CHAIN_OPTIONS.wizardPath` (the chain-to-wizard source).
- `prototype/discovery/page.tsx` (4) — KEPT per plan (writes `prototype.discovery`); back-links repointed.
- e2e realigned: `ts-b.selection` (real waitForURL assertions), `ts-v`/`ts-z` (comments + live assertions).
- `draft.ts` doc comment updated.
All repoints are string-only swaps: **0 retired-palette added** (verified via diff).

## Old-flow deletion (INV-12: no dual impl)

Deleted: `prototype/templates/page.tsx` (765 LOC), `ppt/templates/page.tsx` (730 LOC), and
the transitional render-oracle test. Grep proof: no orphan imports of the deleted modules
(remaining matches are doc comments + the unrelated `/api/*/templates` backend endpoints).
Net diff: 17 files, +1597 / −1520.

## SC-001 / guardrails held

- **SC-001:** the page keys on a generic `mode` ("prototype"|"ppt") data value — the Web/Deck
  toggle — driven by `MODE_CONFIG` + `buildLaunchDraft`; NO per-workflow-name branch.
- Reuse preserved (not rebuilt): live `/api/capabilities` palette, `AdvancedExpander`
  validator→gate coupling + `RETRY_OPTIONS=[1,2,3]`, `user_allowed` lock, ND-7 surface-only
  Config — all via reusing `AgentsPopup` unchanged. **AgentModelPicker NOT mounted** (the
  inline Model lever already satisfies it; re-mounting = INV-3 dual-impl, rejected per 37-CONTEXT).
- Token gate: retired-palette **0** on all new files + **0 added** across the whole diff;
  positive @theme usage (52 hits in LaunchWizard). a11y: aria-label brief + back control;
  stepper keyboard/aria covered by `WizardStepper.test.tsx`.
- LOCK-B: no transport touch. FE-only: backend characterization goldens **byte-identical**
  (`git status **/golden/` clean).

## Offline verification (python3.11 not needed — FE-only; full pytest NEVER run)

- Contract-parity gate: `launchDraft.parity.test.ts` **12/12 green** (byte-identical per mode).
- `LaunchWizard.test.tsx` **13/13 green** (every ported behavior + toggle + real-component parity).
- `tsc --noEmit` identity: **0 errors** (excl mockApi.ts) — matches pre-phase baseline.
  (Stale `.next/types` route artifacts for the deleted routes were cleared; `.next` is gitignored.)
- Per-file retired-palette grep: **0** on all new/touched files; 0 added diff-wide.
- `/opt/homebrew/bin/lint-imports`: **4 kept / 0 broken**.
- Backend goldens: git-clean (untouched).
- Full `vitest run`: **557 passed / 10 failed**. All 10 failures are **PRE-EXISTING**
  (verified identical at pre-work `07a038dd` with my touched source reverted): ReviewGatesSection
  (3, LIBRARY_AGENTS reconciliation + no-gates payload), HomeLaunchGrid Phase-21 saved-workflows
  (5), AgentProgressPanel suggested-next-steps (1), IdeaInputPage declared-capabilities (1) —
  none in 37-07 scope. **Zero regressions introduced.**
- Mocked Playwright: offline-timeout → live-deferred (per 37-CONTEXT).

## Phase-34 live-launch deferral

The launch contract is offline-proven byte-identical to the retired flow, so the actual
`/dashboard` auto-fire SHOULD work unchanged. Live confirmation of the end-to-end
`/workflow/create` → dashboard → pipeline launch is **explicitly deferred to Phase 34**
(live env), consistent with the milestone's live-verification policy.
