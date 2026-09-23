# Domain 10 — frontend·composer — Run report

**Date:** 2026-09-02T12:00:00Z  
**Cards:** 14  
**Batches:** B1 (11 × ComposerPage.tsx, sonnet) + B2 (3 × mixed, haiku)  
**tsc:** EXIT_CODE=0 (zero errors)  
**vitest ComposerPage.test.tsx:** 14/14 GREEN  
**vitest composer/ (7 files):** 83/83 GREEN  
**Dedup regenerated:** 139 → 136 units

---

## B1 — ComposerPage.tsx (11 cards)

### FIXED (3 new FIX cards)

| ISS | FIX | What |
|-----|-----|------|
| ISS-353 | FIX-470 | Save button `isSavingRef` mutex — prevents duplicate `createUserWorkflow` POST on rapid double-click |
| ISS-333 | FIX-468 | `handleRunOnce` + onClick: `pipelineAgents.length === 0` guard — no more 9-agent pool substitution on an empty canvas |
| ISS-431 | FIX-469 | Run once brief < 3 guard now calls `setSaveError` banner (A' replicate FIX-375) |

### ALREADY FIXED (pre-existing, confirmed by code read)

| ISS | Fixed by | Evidence |
|-----|----------|---------|
| ISS-340 | Prior work (FIX-401 era) | `deliverableLabel = deliverableStrategyLabel(runConfig?.deliverable?.strategy)` already in source |
| ISS-192 | Prior work (FIX-325 era) | `needsFullManifestOnSave(…, builtinCanvasType, …)` already in source |

### ESCALATED (5 cards — not safe to fix in this domain)

| ISS | Reason |
|-----|--------|
| ISS-183 | **DESIGN DECISION** — `base_pipeline_type: "custom"` is hardcoded deliberately in `handleSave`. The card itself says "deliberately not resolved here — bending either side without deciding which is correct would hide the conflict." Needs a product decision: either give ComposerPage a non-stale type source (explicit prop), or declare the hardcode canonical and rewrite the 7 failing tests. |
| ISS-223 | **ADR-0027 conflict — human ruling needed.** `deliverable/ppt` is not `user_allowed`. Card lists 3 options; none can be implemented without a decision on the trust boundary. Backend primary. |
| ISS-334 | `page.tsx:494-496` unconditional catch is domain 8's primary fix site. ComposerPage consequence (9-agent substitution) is **closed by FIX-468** (the guard now blocks the launch regardless of how the canvas reached `pipelineAgents=[]`). The `page.tsx` retry/error-surface half goes to domain 8. |
| ISS-410 | `page.tsx:494-496` unconditional catch is domain 8's primary fix site. ComposerPage consequence (duplicate Save row on fetch failure) is **mitigated by FIX-470** (the `isSavingRef` mutex prevents a concurrent second Save). The `page.tsx` half goes to domain 8. |
| ISS-393 | Fix belongs in `AgentsPopup.tsx` (`AgentCapabilitiesModal` — missing `onSelectionsChange`). `AgentsPopup.tsx` is domain 7's primary file per collision rules. Escalated to domain 7/12. |
| ISS-604 | `ComposerPage`'s `seededRunConfig` effect already exists and runs correctly. The remaining race is in `CanvasView`'s combobox read timing and/or `page.tsx`'s fetch-before-mount sequence. Both are in domain 8/12 territory. ComposerPage has no more to add without touching those files. |

---

## B2 — mixed composer files (3 cards)

### FIXED (3 new FIX cards)

| ISS | FIX | File | What |
|-----|-----|------|------|
| ISS-489 | FIX-472 | `AgentSkillsPicker.tsx` | Escape now closes the skill-detail popup — `useEscapeToClose` hook (A' replicate FIX-388) |
| ISS-382 | FIX-471 | `CanvasNode.tsx` | Tools chip added to override-chip row — amber when `hasToolOverride(selection)` |
| ISS-178 | FIX-473 | `graphLayout.ts`, `userWorkflows.ts`, `types/index.ts` | `depends_on` as third edge source in `computeRootLayout`; `AgentDef.depends_on?` propagated from `manifestStepToAgent` |

---

## Files changed

- `frontend/src/components/workflow/composer/ComposerPage.tsx`
- `frontend/src/components/workflow/composer/AgentSkillsPicker.tsx`
- `frontend/src/components/workflow/composer/CanvasNode.tsx`
- `frontend/src/components/workflow/composer/graphLayout.ts`
- `frontend/src/store/api/userWorkflows.ts`
- `frontend/src/types/index.ts`

## New knowledge cards

FIX-468 · FIX-469 · FIX-470 · FIX-471 · FIX-472 · FIX-473

## Ready to commit

All changes are in the working tree. No `git commit/add/push` performed (operator owns git).

## Human action needed

1. **ISS-183** — decide: give ComposerPage a prop-injected `base_pipeline_type` (removes hardcode), OR declare the hardcode canonical and rewrite the 7 currently-failing tests in `ComposerPage.test.tsx`.
2. **ISS-223** — decide which of the 3 options in the card to pursue (`user_allowed=True`, override-only save, or frontend filter with visible notice).
3. **ISS-334 / ISS-410 / ISS-604** — domain 8 (`page.tsx` unconditional catch) and domain 12 (`CanvasView` timing) will close the remaining symptoms.
4. **ISS-393** — domain 7/12 will close (`AgentsPopup.tsx` `onSelectionsChange` wiring).
