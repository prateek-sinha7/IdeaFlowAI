---
phase: 37-configure-unification-composer-wizard-b3
reviewed: 2026-07-09T00:00:00Z
depth: deep
files_reviewed: 16
files_reviewed_list:
  - backend/app/api/launch_context.py
  - backend/app/api/run_commands.py
  - backend/app/api/websocket.py
  - backend/tests/unit/test_rest_run_launch.py
  - frontend/src/app/workflow/configure/page.tsx
  - frontend/src/app/workflow/ppt/templates/page.tsx
  - frontend/src/app/workflow/prototype/discovery/page.tsx
  - frontend/src/app/workflow/prototype/templates/page.tsx
  - frontend/src/components/workflow/AgentLibrary.tsx
  - frontend/src/components/workflow/AgentsPopup.tsx
  - frontend/src/components/workflow/ConfigureScreen.tsx
  - frontend/src/components/workflow/WizardStepper.tsx
  - frontend/src/components/workflow/WorkflowDialog.tsx
  - frontend/src/components/workflow/prototype/DesignSystemPicker.tsx
  - frontend/src/lib/draft.ts
  - frontend/src/components/workflow/AgentsPopup.reskin.test.tsx
findings:
  critical: 0
  warning: 7
  info: 7
  total: 14
status: issues_found
rereviews:
  - id: 37-07-and-fixes
    reviewed: 2026-07-10T00:00:00Z
    diff_base: 7a84f6bc..6167b302
    findings: { critical: 0, warning: 3, info: 4, total: 7 }
---

# Phase 37: Code Review Report

**Reviewed:** 2026-07-09
**Depth:** deep
**Files Reviewed:** 16
**Status:** issues_found

## Summary

Phase 37 (Configure Unification + Composer/Wizard [B3]) was reviewed adversarially with
Phase-36's dropped-behavior regressions in mind. The single highest-risk change — the
**37-01 D-15/C run-launch seam** — is **verified correct and byte-preserving**. I traced
every one of the three opendesign manifests (`prototype`/`od_ppt`/`od_ppt_revision`) plus
the legacy `od_prototype`/bare-`prototype` split through both boundaries and confirmed:

- `compile_for_run` resolves the `od_prototype`→`prototype` alias *internally* (engine.py:501),
  so `compile_for_run("od_prototype")` does **not** FileNotFoundError-drop od_context even
  though no `od_prototype/` manifest dir exists.
- `_OD_ALIAS_BASE.values() == {"prototype"}` correctly excludes bare `prototype` from
  self-eligibility, preserving the 13-06 `missing_template_context` guard.
- REST keeps `od_ppt_revision` → `None`; WS keeps it non-fatal (`fatal=False`, `if template_id`).
- No over-broadening: only the three legacy manifests declare `opendesign` today.
- Parity tests assert **dict-equality** (not just non-null) for `od_prototype`/`od_ppt`, and
  `None` for undeclared/`user_stories`/REST-`od_ppt_revision`. `tests/unit/test_rest_run_launch.py`
  **17/17 pass**. INV-3 byte-identity is genuinely defended, not asserted hollowly.

The **37-03 composer reskin preserved every load-bearing behavior** (unlike Phase 36):
`COUPLED_GATE="validation"`, `RETRY_OPTIONS=[1,2,3]`, live `/api/capabilities` palette,
`user_allowed` lock, and the standalone `AgentModelPicker` is correctly NOT mounted (reskin
test enforces it). The **37-06 / ND-7 surface-only fix is airtight** — the durable
PUT/DELETE `/api/agents/{id}/prompt` path is genuinely unreachable from the drawer.

The defects are not correctness regressions in the shipped seam — they are **unwired/dead
deliverables and a stale-model-persistence seam** in the composer/wizard surfaces. No BLOCKERs.

## Warnings

### WR-01: Wizard new-build (WizardStepper, 37-04) is mounted nowhere — unreachable feature

**File:** `frontend/src/components/workflow/WizardStepper.tsx:1-227`
**Issue:** The 37-04 deliverable — the unified Template→Design System→Discovery stepper with
the Web/Deck toggle — is a fully-built 227-line component with a 140-line test suite, but it
is **imported and mounted by zero live modules**. The only reference in the app is a docstring
comment in `frontend/src/app/workflow/prototype/discovery/page.tsx:17`; grep confirms no
`import { WizardStepper }` and no `<WizardStepper` JSX anywhere outside its own file/test. The
route-split flow (`prototype/templates`, `ppt/templates`, `prototype/discovery`) remains the
live path and was only reskinned (color tokens), not replaced. The "new-build wizard" therefore
ships **unreachable** this phase. If it is intended to *supersede* the route-split chrome, INV-3
requires deleting the superseded flow; if it is a staged deferral, it is dead code at HEAD.
**Fix:** Either (a) wire `WizardStepper` into a live route (and retire the route-split pages it
replaces, per INV-3), or (b) explicitly mark it deferred in the phase record and gate it behind
a follow-up so an unmounted component + test is not counted as a shipped surface. Confirm intent
with the PM before merge — this is the exact "reskin/reuse dropped the live behavior" class the
Phase-36 review caught, inverted (built but unwired).

### WR-02: WorkflowDialog (SURF-03 detail viewer) is mounted nowhere — dead component

**File:** `frontend/src/components/workflow/WorkflowDialog.tsx:1-301`
**Issue:** A 300-line read-only compiled-workflow detail dialog (context providers / declared
capabilities / compaction, with the `user_allowed` engineer-lock reflection) is built and tested
(`WorkflowDialog.test.tsx`) but **has no consumer** — grep for `<WorkflowDialog` / `import ...
WorkflowDialog` outside its own file and test returns nothing. It cannot be opened by any user.
**Fix:** Mount it where the SURF-03 "inspect this workflow" affordance is intended (e.g. the
catalog/library card), or remove it from this phase and track as deferred. Do not leave a
300-line unreachable surface in the tree.

### WR-03: Save-to-catalogue persists a STALE `model_overrides` seed; `onModelOverridesChange` is now a dead prop

**File:** `frontend/src/components/workflow/AgentsPopup.tsx:1793-1799` (and prop at :57, :1747)
**Issue:** The new composer footer "Save workflow" builds its payload with
`...(initialModelOverrides && Object.keys(initialModelOverrides).length > 0 ? { model_overrides:
initialModelOverrides } : {})` — i.e. from the **static `initialModelOverrides` prop seed**, not
a live value. In this phase the standalone `AgentModelPicker` was (correctly) removed and per-agent
model selection moved to the inline `AdvancedExpander` Model lever, which writes to
`selections[id].model` (mirrored live into `liveSelections`). As a result `onModelOverridesChange`
is **never invoked anywhere** in `AgentsPopup` (grep: only the prop declaration at :57, destructure
at :1747, and a stale comment at :2063) — the `modelOverrides` mechanism is dead in this component.
Two consequences:
  1. A saved workflow can carry a **divergent** model record: `selections.model` = the user's live
     choice, while `model_overrides` = the (possibly empty or outdated) seed. Whichever the
     reload/launch path prefers determines behavior; if it prefers `model_overrides`, the user's
     in-session model choice is silently lost on reload.
  2. `onModelOverridesChange` is a dead prop and the comment at :2060-2064 describes a picker that
     no longer exists (misleading).
**Fix:** Drop `model_overrides` from the save payload entirely and rely on `selections.model` as
the single source of truth (matches the reskin's "the inline Model lever already satisfies per-agent
model selection"), OR mirror live overrides into local state like `liveSelections` and save that.
Remove the now-dead `onModelOverridesChange` prop and the stale :2060-2064 comment. Verify the
saved-workflow reload path reads model from `selections.model`, not `model_overrides`.

### WR-04: ConfigureScreen opendesign gate diverges from the backend seam for the bare `prototype` deliverable

**File:** `frontend/src/components/workflow/ConfigureScreen.tsx:111-114`
**Issue:** `acceptsTemplateDs = (detail?.context_providers ?? []).includes("opendesign")` gates
the Templates + Design System accordions on the **raw** declared signal. The backend seam
(`launch_context.py:57-62`) keys on the *same* signal **but additionally excludes any base with a
dedicated `od_` alias** (`pipeline_type in _OD_ALIAS_BASE.values() == {"prototype"}`). The
`prototype` manifest declares `opendesign`, so ConfigureScreen opened for the bare `prototype`
workflow **will render the template/DS pickers and let the user select a template** — but if that
run is then launched as bare `prototype` (not the `od_prototype` alias), the backend seam returns
`od_context=None` and the 13-06 `missing_template_context` guard **rejects the run**, silently
discarding the user's template selection. The two ends of the D-15/C signal are not aligned for the
one base that has a legacy alias. Currently latent because `onLaunch` (live launch) is
Phase-34/deferred, but it is a real trap the moment launch is wired.
**Fix:** Make the frontend gate mirror the backend eligibility exactly — either resolve/launch the
`prototype` deliverable via its `od_prototype` alias so od_context loads, or exclude bare
`prototype` from the accordion gate the same way the seam does (share a single eligibility helper
across both ends rather than duplicating the predicate).

## Info

### IN-01: Discovery answers captured but never threaded into the composed launch command

**File:** `frontend/src/components/workflow/ConfigureScreen.tsx:215-229`
**Issue:** `handleLaunch` composes `ComposedLaunchCommand` from `brief` but omits the `discovery`
answers state — only `saveDraft`/`composeDraft` persist `discovery`. Discovery answers therefore
never reach `onLaunch`. Also, ConfigureScreen mounts `<DiscoveryForm templateInputs={[]} …>` so no
template-driven questions render here regardless. Low impact (launch is deferred; the form is inert
with empty inputs), but the captured answers are silently dropped at hand-off.
**Fix:** Include the discovery answers (or their derived context) in `ComposedLaunchCommand` when
the live launch is wired, or document that discovery is draft-only on this surface.

### IN-02: Step-counter mismatch across the route-split flow

**File:** `frontend/src/app/workflow/prototype/discovery/page.tsx:151` vs `.../prototype/templates/page.tsx:363`
**Issue:** The discovery page header now reads "Step 3 of 3" while the templates page still reads
"Step 1 of 2" (and ppt/templates "Step 1 of 2"). The two live pages disagree on the total step
count shown to the user (X of 2 vs 3 of 3).
**Fix:** Reconcile the step labels to a single consistent numbering for the route-split flow (or
finish the WizardStepper consolidation that would own the count centrally — see WR-01).

### IN-03: Launch seam now compiles every manifest at the boundary; only FileNotFoundError is caught

**File:** `backend/app/api/launch_context.py:52-55`
**Issue:** `resolve_launch_od_context` calls `compile_for_run(pipeline_type)` for **every** launch
(all pipeline types, both boundaries), catching only `FileNotFoundError`. Per `compile_for_run`'s
contract it can also raise `CompilerError`/`ManifestValidationError` on a malformed manifest. For a
malformed-but-supported manifest, the failure now surfaces at the launch boundary (uncaught → REST
500 / unshaped WS error) rather than deeper in `engine.execute`. `compile_for_run` is `lru_cache`d
so there is no correctness/perf regression for valid manifests; this is a fail-fast behavior/shape
change, not a data-loss bug.
**Fix:** If a shaped rejection is desired for malformed manifests, catch `Exception`/the compiler
error types at the seam and map to a `template_not_found`-style rejection; otherwise document the
fail-fast intent.

---

_Reviewed: 2026-07-09_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_

---

# 37-07 + Fixes Re-Review (diff `7a84f6bc..6167b302`)

**Reviewed:** 2026-07-10
**Depth:** deep (cross-file, contract-parity oracle re-derivation)
**Scope:** the 6 review-fix commits (WR-02/03/04, IN-01/02, ISS-046 doc) + the flagship 37-07 unified `LaunchWizard` rebuild.
**Status:** issues_found — **0 blockers, 3 warnings, 4 info.**

## Verified sound (adversarially, Phase-36 lesson applied)

- **Launch-contract byte-identity — re-derived against the deleted oracle.** I pulled the retired
  `prototype/templates` + `ppt/templates` pages from git `7a84f6bc` and diffed their real
  `handleContinue` serialization, `finalBrief` composition, and `handleSaveWorkflow` payload against
  `lib/launchDraft.ts` + `LaunchWizard.tsx`. Key order, truthy/length-guarded optional spreads
  (`customDsBody`→`customTemplateBody`→`sourceRunId`→`gateAgentIds`→`modelOverrides`→`selections`→`images`→`agentIds`),
  the ppt `designSystemId = dsRequired ? id : null` rule, and the `_wizard` save config are **all
  reproduced exactly**. The extraction to `buildLaunchDraft` is a true single-source refactor (INV-12).
- **Old-flow retirement is clean.** No orphan imports of / navigation to the deleted routes anywhere in
  `src/` — remaining matches are doc comments + the legitimate `/api/*/templates` backend endpoints.
  All entry points (`CreationHub`, `HomeLaunchGrid`, `DashboardLayout` saved-restore, `workflowChaining`,
  discovery back-links) repointed to `/workflow/create?mode=…` as string-only swaps.
- **SC-001 holds.** The page keys on the generic `mode` axis (`"prototype"|"ppt"`) via `MODE_CONFIG` +
  `buildLaunchDraft`; no per-workflow-name branch. `?mode=` parsing is safe (defaults to prototype for
  any non-`ppt` value; only ever used to index the two-key maps — no injection surface).
- **The 6 fixes are correctly applied and test-covered, not weakened.** WR-02 mounts `WorkflowDialog`
  via a **sibling** (never nested) inspect button with a proper `aria-label` + a new reachability test;
  WR-03 drops the stale `model_overrides` seed and adds an assertion that it is no longer persisted;
  WR-04 excludes the `od_` alias base from the Configure gate; IN-01 threads `discovery` into the launch
  command. Test diffs are **additive** (no deleted assertions).
- **Backend D-15/C seam untouched.** The only `launch_context.py` change is a comment (ISS-046 tracking).
  FE-only phase respected.

## Contract-parity coverage — GAP FOUND (answers the review's headline question)

The parity gate is genuine and byte-exact for the branches it covers (both modes base, blank-canvas,
custom-DS, gates empty `[]`+non-empty, images, sourceRunId/levers). **But one dashboard-relevant branch
is uncovered by both the golden fixtures AND the component test: the ppt custom-template case** — the one
scenario that simultaneously forces `customTemplateBody` present **and** `designSystemId:null`
(`dsRequired=false`). `launchContract.ts` explicitly *avoided* it (its comment says the rich ppt scenario
"deliberately uses a ds-requiring built-in, not a custom template"), and `LaunchWizard.test.tsx` has a
`pick-web-custom` stub button but **no `pick-deck-custom`**. This is exactly the class of assumption bug
the retired render-oracle caught (the review even cites it). The path is wired end-to-end
(`WizardStepper`→`PPTTemplateGallery` accept the deck-custom props) and is byte-correct *by construction*,
but it is **unproven** — see WR-06. Secondary: the chaining launch draft and out-of-band images are
fixture-only (not component-proven), and the `discovery · template inputs only` golden is unreachable from
the component (see IN-05).

## Warnings

### WR-05: Web/Deck toggle leaves the page chrome labelled for the WRONG deliverable (`cfg` frozen to `initialMode`)

**File:** `frontend/src/components/workflow/LaunchWizard.tsx:125` (consumed at :514, :517, :584, :590, :793)
**Issue:** `const cfg = MODE_CONFIG[initialMode];` derives the header eyebrow/title, brief label,
placeholder, and **save-modal title** from the immutable `initialMode` prop — while every data-bearing
value correctly uses the live `mode` state (`MODE_CONFIG[mode].agentPipeline` :114/:782,
`MODE_CONFIG[mode].savePipeline` :430). The 37-07 flagship affordance is the in-page Web/Deck toggle
(`handleModeChange`→`setMode`). After a user toggles prototype→deck, the page still shows
**"Configure your prototype" / "Describe what you're building" / the prototype placeholder / "Save
prototype workflow"** while actually composing and saving a ppt deck (correct `base_pipeline_type: od_ppt`).
The user is told they are saving a prototype when the persisted artifact is a presentation. The toggle
test (`LaunchWizard.test.tsx:166`) asserts only the agent pipeline + launch keys, so it missed the stale
chrome — the Phase-36 failure mode (test guards the data contract, not the visible behavior).
**Fix:** `const cfg = MODE_CONFIG[mode];` and extend the toggle test to assert the header title / brief
label / save-modal title flip to the ppt copy after `toggle-deck`.

### WR-06: ppt custom-template launch branch has no parity golden and no component test

**File:** `frontend/src/components/workflow/__fixtures__/launchContract.ts:171-197` (no scenario);
`frontend/src/components/workflow/LaunchWizard.test.tsx:49-75` (no `pick-deck-custom`)
**Issue:** The only ppt branch that produces `customTemplateBody` **and** `designSystemId:null` together
(a deck custom template forces `dsRequired=false`) is never exercised. The golden set deliberately swapped
in a ds-requiring built-in to sidestep it; the stepper stub exposes a web custom-template button but no
deck one. The `designSystemId` *resolution* for this case runs in the component
(`mode==="ppt" ? (dsRequired ? selectedDsId : null) : …` at LaunchWizard.tsx:459 with
`dsRequired = mode==="ppt" && selectedDeckTemplate?.design_system?.requires===true`, and
`selectedDeckTemplate=undefined` for a custom id) — untested. A silent regression here would ship a
broken flagship deck launch with green tests.
**Fix:** Add a golden `ppt · custom template (customTemplateBody + designSystemId:null)` to
`DRAFT_SCENARIOS`, and a `pick-deck-custom` stub button + a component test that selects a deck custom
template and asserts the launched `ppt.draft` carries `customTemplateBody` with `designSystemId:null`.

### WR-07: chaining launch is not proven — the `finalBrief = contextBlock` composition is untested at the component level

**File:** `frontend/src/components/workflow/LaunchWizard.test.tsx:262-269`
**Issue:** The chaining test asserts only that the brief editor is hidden and the banner shows; it never
clicks **Continue**. The load-bearing chain launch logic — `isChaining && contextBlock → finalBrief =
contextBlock`, else append; plus `sourceRunId` pulled from `chain.source_run_id` and `chain.context_block`
consumed/removed (LaunchWizard.tsx:444-451) — is exercised by no component test. The `sourceRunId` golden
is a direct `buildLaunchDraft` input, so the component's chain-context→brief composition path is unproven.
Chaining is one of the 13 ported behaviors and a live flagship path.
**Fix:** Extend the chaining test to seed `chain.context_block` + `chain.source_run_id`, click Continue,
and assert `JSON.parse(prototype.draft).brief === <contextBlock>` and `.sourceRunId` is threaded.

## Info

### IN-04: dead `onModelOverridesChange` prop + vestigial `modelOverrides` draft field (post-WR-03)

**File:** `frontend/src/components/workflow/LaunchWizard.tsx:319-321, :470, :787`
**Issue:** WR-03 removed `onModelOverridesChange`/`initialModelOverrides` from `AgentsPopup`'s destructure,
so `AgentsPopup` never calls the callback. `LaunchWizard` still passes `onModelOverridesChange`
(:787) — now a no-op — and `modelOverridesRef` is written **only** by the draft-restore effect (:223).
`handleLaunch` still emits `modelOverrides: modelOverridesRef.current` (:470). For a from-scratch compose
it is always `{}` (harmless), but on a *restored saved workflow* carrying legacy `model_overrides`, the
draft can emit BOTH the stale restored `modelOverrides` AND fresh `selections[id].model` — the divergent
model record WR-03 set out to eliminate, just relocated to the launch draft.
**Fix:** Drop the dead `onModelOverridesChange` prop from the `AgentsPopup` call, and stop emitting
`modelOverrides` from the launch draft (make `selections[id].model` the single source of truth on launch,
matching the save path). Confirm the dashboard/backend reads model from `selections`, not draft `modelOverrides`.

### IN-05: orphaned `prototype/discovery` route + template-input discovery dropped from the unified flow

**File:** `frontend/src/app/workflow/prototype/discovery/page.tsx` (whole route);
`frontend/src/components/workflow/LaunchWizard.tsx:715` (`templateInputs={[]}`)
**Issue:** Nothing in `src/` navigates to `/workflow/prototype/discovery` (already orphaned at the base
commit; the repoint only touched its internal back-links). It reads `prototype.draft`, which
`LaunchWizard.handleLaunch` writes-then-immediately-supersedes with `od_prototype.pending` + a push to
`/dashboard`, so even a manual visit bounces. Meanwhile the unified inline discovery step hardcodes
`<DiscoveryForm templateInputs={[]} …>`, so template-specific discovery questions — the discovery route's
entire purpose — are unreachable. Result: two discovery implementations, one dead (INV-12 smell), and the
`discovery · template inputs only` golden (`launchContract.ts:213`) is unreachable from any component.
Not a regression (the old *live* path had no discovery), but dead surface left by the retirement.
**Fix:** Either wire the inline discovery step to fetch the selected template's `od.inputs` and pass real
`templateInputs` (restoring the behavior), or delete the orphaned discovery route + the unreachable golden
scenario. Do not leave a bounce-only route + an unreachable fixture branch.

### IN-06: WR-04 FE mirror keys on `workflowId`, not the resolved base pipeline_type

**File:** `frontend/src/components/workflow/ConfigureScreen.tsx:127-134` (`OD_ALIAS_BASE_PIPELINES.has(workflowId)`)
**Issue:** The backend seam excludes on the *resolved base* (`pipeline_type in _OD_ALIAS_BASE.values()`).
The FE carve-out matches only when `workflowId` is literally `"prototype"`. A user/custom workflow whose
`base_pipeline_type==="prototype"` but whose `workflowId` is a custom id would NOT be carved out,
re-introducing the exact gate/seam divergence WR-04 fixed (Configure offers template/DS for a deliverable
the seam would reject). Latent while live launch is deferred.
**Fix:** Gate on the resolved base pipeline type (from `detail`), or share one eligibility helper across
both ends rather than mirroring the literal id set.

### IN-07: redundant auth gate — `create/page.tsx` and `LaunchWizard` both getToken/redirect

**File:** `frontend/src/app/workflow/create/page.tsx:21-25` + `LaunchWizard.tsx:177-188`
**Issue:** Both the route wrapper and the component independently `getToken()` → `router.replace("/login")`
and maintain their own `authChecked`. Harmless duplication (double loading flash possible), but a dead
guard now that the wrapper always gates first.
**Fix:** Drop the auth check from one layer (keep it in `LaunchWizard`, since it also owns the chain pickup),
or document the wrapper gate as the single owner.

---

_Re-reviewed: 2026-07-10_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep — oracle re-derived from git `7a84f6bc`_
