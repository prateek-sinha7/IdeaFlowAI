---
quick_id: 260710-ftq
type: execute
mode: quick-full
branch: feat/ui-2
wave: 1
depends_on: []
autonomous: true
requirements: [DEFECT-1, DEFECT-2]
files_modified:
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/app/dashboard/launchImageAndRecents.source.test.ts   # new, optional source-lock
user_setup: []

must_haves:
  truths:
    - "A prototype (od_prototype) launch with an attached image sends an `images` field on the outbound WS run_pipeline frame — the model sees the image."
    - "A ppt (od_ppt) launch with an attached image sends an `images` field on the outbound WS run_pipeline frame."
    - "An image-LESS launch is byte-identical to today: no `images` key in the frame (INV-3 dormancy preserved by the length-guarded spread)."
    - "Clicking a Home 'Recent runs' chip both loads the run AND switches the shell to the execution view (the run actually opens)."
  artifacts:
    - path: "frontend/src/app/dashboard/page.tsx"
      provides: "pendingOdProtoParams + pendingOdPptParams now carry images through the launch-staging setter"
      contains: "pending.images && pending.images.length > 0 ? { images: pending.images }"
    - path: "frontend/src/components/layout/DashboardLayout.tsx"
      provides: "Recents chip navigates to execution view on open"
      contains: "setMainView(\"execution\")"
    - path: "frontend/src/app/dashboard/launchImageAndRecents.source.test.ts"
      provides: "Source-lock proof both wirings are present (idiom: revisionFamilyLinkage.source.test.ts)"
  key_links:
    - from: "frontend/src/app/dashboard/page.tsx (setPendingOdProtoParams / setPendingOdPptParams)"
      to: "pendingOd*Params.images"
      via: "length-guarded images spread, immediately after the agentIds spread"
      pattern: "pending\\.images && pending\\.images\\.length > 0 \\? \\{ images: pending\\.images \\}"
    - from: "frontend/src/components/layout/DashboardLayout.tsx extraParams image-guard (lines ~757 / ~805, ALREADY CORRECT)"
      to: "WS run_pipeline `images` field"
      via: "consumes pendingOd*Params.images — now populated by the fix"
      pattern: "pendingOd\\w+Params\\.images && pendingOd\\w+Params\\.images\\.length > 0 \\? \\{ images \\}"
    - from: "frontend/src/components/layout/DashboardLayout.tsx recents chip onClick (line ~1525)"
      to: "execution view"
      via: "onSelectWorkflowRun?.(run) THEN setMainView(\"execution\")"
      pattern: "onSelectWorkflowRun\\?\\.\\(run\\); setMainView\\(\"execution\"\\)"
---

<objective>
Fix two frontend-only wiring defects found during live Playwright/Bedrock UI testing on 2026-07-10. Both are already exactly root-caused — this plan APPLIES the specified fixes and verifies offline. Do NOT re-investigate or re-debug.

- DEFECT 1 (High): the prototype/ppt run-launch staging setter in `dashboard/page.tsx` rebuilds the pending-params state object with an explicit field list that OMITS `images`, so `pendingOd*Params.images` is always `undefined` and DashboardLayout's (already-correct) extraParams image-guard evaluates false → the WS `run_pipeline` frame carries no image. Proven prototype-specific: the identical image on the `user_stories` path DOES reach the wire.
- DEFECT 2 (Medium): the Home "Recent runs" chip loads run content via `onSelectWorkflowRun?.(run)` but never calls `setMainView("execution")`, so the run never opens. Every other run-open path already switches the view.

Purpose: restore multimodal input on the prototype/ppt launch path (the model must see attached images) and make the fused-Home recents chips live.
Output: two edited source files (2 setters + 1 onClick), one optional source-lock test.

SCOPE FENCES (hard): exactly two source files + optionally one new small test file. NO backend / engine / manifest / AGENT.md / characterization-golden edits. No new deps. Additive only. NO commit trailer. DashboardLayout's extraParams image-guard is ALREADY CORRECT — do not touch it.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md

# The two files to fix (already read + root-caused — DO NOT re-debug):
@frontend/src/app/dashboard/page.tsx
@frontend/src/components/layout/DashboardLayout.tsx

# Sanctioned source-lock test idiom (reads BOTH target files via readFileSync):
@frontend/src/app/dashboard/revisionFamilyLinkage.source.test.ts

# Behavioral image-payload reference tests that MUST stay green (regression fence):
@frontend/src/hooks/useWorkflow.imagePayload.test.ts
@frontend/src/components/workflow/IdeaInputPage.imageInput.test.tsx
</context>

<tasks>

<task type="auto">
  <name>Task 1: DEFECT 1 — carry images through the prototype + ppt launch-staging setters</name>
  <files>frontend/src/app/dashboard/page.tsx, frontend/src/app/dashboard/launchImageAndRecents.source.test.ts</files>
  <action>
Two one-line additions in `frontend/src/app/dashboard/page.tsx`, each mirroring the `selections`/`agentIds` length-guarded spreads that already sit in the SAME object. The state types (`pendingOdProtoParams` ~line 178-184, `pendingOdPptParams` ~line 186-192) ALREADY declare `images?: { name: string; mime_type: string; data: string }[]`, and the `pending` object ALREADY carries `images: draft.images` (proto ~line 976, ppt ~line 1047) — so NO type change and NO other edit is needed.

1. In the `setPendingOdProtoParams({ ... })` call (~lines 996-1011), immediately AFTER the existing `agentIds` spread line
   `...(pending.agentIds && pending.agentIds.length > 0 ? { agentIds: pending.agentIds } : {}),` (~line 1010),
   add exactly this line:
   `...(pending.images && pending.images.length > 0 ? { images: pending.images } : {}),`

2. In the `setPendingOdPptParams({ ... })` call (~lines 1068-1083), immediately AFTER its `agentIds` spread line (~line 1082), add the SAME line:
   `...(pending.images && pending.images.length > 0 ? { images: pending.images } : {}),`

Use a length-guarded spread (NOT an unconditional `images: pending.images`) so an image-less launch stays byte-identical — no `images` key — preserving INV-3 dormancy exactly as the sibling `selections`/`agentIds` spreads do.

DO NOT modify DashboardLayout's extraParams image-guard (~lines 757 and 805) — it is already correct and consumes `pendingOd*Params.images`. DO NOT touch any backend, manifest, AGENT.md, or characterization golden.

3. (Optional but recommended) Create the source-lock test `frontend/src/app/dashboard/launchImageAndRecents.source.test.ts`, following the EXACT idiom of the co-located `revisionFamilyLinkage.source.test.ts` (plain `readFileSync` + `resolve(__dirname, ...)` grep-style assertions — the sanctioned pattern for the huge page.tsx / DashboardLayout that are impractical to render). This test file covers BOTH Task 1 and Task 2. Assert:
   - `dashboardPage` (from `./page.tsx`) contains the string `pending.images && pending.images.length > 0 ? { images: pending.images }` — and that it appears TWICE (once per setter): `expect(dashboardPage.split("pending.images && pending.images.length > 0").length - 1).toBe(2)`.
   - (Task 2 assertion — see Task 2) `dashboardLayout` (from `../../components/layout/DashboardLayout.tsx`) contains `onSelectWorkflowRun?.(run); setMainView("execution")`.
Keep it small (one describe, 2-3 `it` blocks). Do NOT attempt to render the full page or extract a helper — that exceeds the minimal additive fence.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | grep -v mockApi.ts | grep -c "error TS"</automated>
    <automated>cd frontend && grep -c "pending.images && pending.images.length > 0 ? { images: pending.images }" src/app/dashboard/page.tsx</automated>
    <automated>cd frontend && npx vitest run src/hooks/useWorkflow.imagePayload.test.ts src/components/workflow/IdeaInputPage.imageInput.test.tsx src/app/dashboard/launchImageAndRecents.source.test.ts</automated>
  </verify>
  <done>
`npx tsc --noEmit` shows no NEW type errors (identity vs baseline 0 after the mockApi.ts filter). `grep -c` returns `2` (the images spread present in BOTH setters). The image-payload regression tests (useWorkflow.imagePayload, IdeaInputPage.imageInput) stay green, and the new source-lock test passes. No edit outside page.tsx + the new test file.
  </done>
</task>

<task type="auto">
  <name>Task 2: DEFECT 2 — Home "Recent runs" chip opens the run in the execution view</name>
  <files>frontend/src/components/layout/DashboardLayout.tsx</files>
  <action>
Single one-line change in `frontend/src/components/layout/DashboardLayout.tsx` at the Home recents chip (~line 1525). The chip currently loads run data but never switches the shell view. `setMainView` is ALREADY in scope in this component (used at ~line 736 `setMainView("execution")` and by every other run-open path).

Change:
  `onClick={() => onSelectWorkflowRun?.(run)}`
to:
  `onClick={() => { onSelectWorkflowRun?.(run); setMainView("execution"); }}`

This mirrors the existing run-open paths (notification `onViewResults` ~line 1454, History, live launch) which all call `setMainView("execution")` after loading run content. Do NOT change the chip's data-loading call, styling, or any other handler. FE-only, additive.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | grep -v mockApi.ts | grep -c "error TS"</automated>
    <automated>cd frontend && grep -c 'onSelectWorkflowRun?.(run); setMainView("execution")' src/components/layout/DashboardLayout.tsx</automated>
    <automated>cd frontend && npx vitest run src/components/layout/DashboardLayout.catalogHome.test.tsx src/components/layout/DashboardLayout.waveMount.test.tsx src/app/dashboard/launchImageAndRecents.source.test.ts</automated>
  </verify>
  <done>
`npx tsc --noEmit` shows no NEW type errors. `grep -c` returns `1` (the recents chip now calls both `onSelectWorkflowRun` and `setMainView("execution")`). The existing DashboardLayout mount/home suites stay green and the source-lock test passes. No edit outside DashboardLayout.tsx.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser FE → WS run_pipeline → backend | Attached image bytes cross here. This fix RESTORES an existing, already-validated carrier path; it introduces no new boundary. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-ftq-01 | Information Disclosure | `images` payload on run_pipeline frame | accept | Images ride the EXISTING out-of-band `images` carrier already server-validated by `_validate_images` (mime allow-list / per-image + aggregate size caps / ≤20 / vision-model guard) on the WS run_pipeline path. This FE fix only re-populates `pendingOd*Params.images`; no new data leaves the client that the user did not attach, and base64 never enters the brief (D3, unchanged). |
| T-ftq-02 | Tampering | INV-3 characterization goldens | mitigate | Length-guarded spread keeps image-less launches byte-identical (no `images` key), so backend goldens are untouched by construction. FE-only diff — zero backend/manifest/golden edits (scope fence). |
| T-ftq-SC | Tampering | npm/pip/cargo installs | mitigate | No package installs in this plan (additive FE edits, no new deps) — no supply-chain surface. |
</threat_model>

<verification>
Offline verification only (executor MUST NOT run a live Bedrock pipeline):

1. `cd frontend && npx tsc --noEmit 2>&1 | grep -v mockApi.ts | grep -c "error TS"` → identity vs baseline (expect 0 new errors in the two touched files).
2. `cd frontend && grep -c "pending.images && pending.images.length > 0 ? { images: pending.images }" src/app/dashboard/page.tsx` → `2`.
3. `cd frontend && grep -c 'onSelectWorkflowRun?.(run); setMainView("execution")' src/components/layout/DashboardLayout.tsx` → `1`.
4. `cd frontend && npx vitest run src/hooks/useWorkflow.imagePayload.test.ts src/components/workflow/IdeaInputPage.imageInput.test.tsx src/components/layout/DashboardLayout.catalogHome.test.tsx src/components/layout/DashboardLayout.waveMount.test.tsx src/app/dashboard/launchImageAndRecents.source.test.ts` → all green.
5. `cd frontend && git diff --name-only` → exactly `src/app/dashboard/page.tsx`, `src/components/layout/DashboardLayout.tsx`, and (if created) `src/app/dashboard/launchImageAndRecents.source.test.ts`. NO backend/engine/manifest/golden path in the diff.

NOTE for the executor: DO NOT run a live Bedrock pipeline. The definitive live proof — a prototype run with an attached image whose outbound `run_pipeline` frame now carries `images`, the spec-writer `agent_input` carrying `image_count`, and the recents chip opening the run — is performed by the orchestrator against the running local app AFTER this plan completes.
</verification>

<success_criteria>
- `setPendingOdProtoParams` and `setPendingOdPptParams` in page.tsx each carry the length-guarded `images` spread (grep == 2).
- The Home recents chip in DashboardLayout.tsx calls `setMainView("execution")` alongside `onSelectWorkflowRun` (grep == 1).
- `npx tsc --noEmit` shows no new type errors; the image-payload + DashboardLayout regression suites and the source-lock test are green.
- `git diff --name-only` is confined to the two source files (+ optional test). No backend/engine/manifest/golden touched. No new deps. No commit trailer.
</success_criteria>

<output>
Create `.planning/quick/260710-ftq-fix-prototype-image-drop-on-launch-and-r/260710-ftq-SUMMARY.md` when done.
</output>
