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
  warning: 4
  info: 3
  total: 7
status: issues_found
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
