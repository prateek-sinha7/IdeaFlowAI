# Phase 18: Custom-Workflow UX Completeness - Context

**Gathered:** 2026-06-13
**Status:** Ready for planning
**Source:** Locked decisions from the 2026-06-13 deep root-cause investigation (cluster E). Findings + proper (no-hack) fixes are in `.planning/ISSUES-REGISTER.md` → "Deep Root-Cause Investigation". Code-proven file:line. No discuss round.

<domain>
## Phase Boundary

Close cluster E — the "SC-001 custom workflows are backend-complete but UI-incomplete, plus orphaned dual UI" gap. FE-weighted with one INV-3-sensitive BE addition.

1. **ISS-021** (minor, product) — a custom workflow's non-markdown deliverable (HTML/zip) has no faithful FE path. **The headline fix.**
2. **ISS-014** (minor, product) — the capability-palette composer (`WorkflowComposer.tsx` + `CapabilityPalette.tsx`, `/api/capabilities`) is orphaned dead UI (INV-3/12 dual-impl). Delete + relocate the model picker.
3. **ISS-019** (cosmetic, product) — the WaveTreePanel sits ~13px below the 1440×950 fold. CSS-only.
4. **ISS-015** (trivial, product) — no generic pipeline-type picker. WONTFIX (by-design); record rationale.

IN SCOPE: FE — `frontend/src/components/preview/PreviewPanel.tsx`, `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/preview/FilesTab.tsx`, `frontend/src/hooks/useWorkflow.ts`, `frontend/src/types/index.ts`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/workflow/AgentsPopup.tsx` (model-picker relocation), and DELETE `frontend/src/components/workflow/WorkflowComposer.tsx` + `CapabilityPalette.tsx` (+ decide `AgentModelPicker.tsx`). BE (additive only) — `backend/agents/workflows/plan.py` (`DeliverableSpec.mimetype`), `backend/agents/workflows/compiler.py` (`_compile_deliverable`), `backend/agents/execution_engine/engine.py` (the `pipeline_complete` data dict ~:1854-1866), `backend/tests/agents/characterization/_normalize.py` (`_VOLATILE_STRIP_KEYS`), optional per-resolver default mimetype in `backend/agents/capabilities/deliverables/*`. The register WONTFIX flip for ISS-015.

OUT OF SCOPE: the `/api/capabilities` endpoint + `test_capabilities_api.py` (KEEP — API-02 contract). Cluster D (ISS-004/005/006 → Phase 19). Any new pipeline-type launch picker (ISS-015 is WONTFIX). The live Playwright visual confirmation (runs in the dedicated UI pass after this phase).

</domain>

<decisions>
## Implementation Decisions (LOCKED — proven file:line)

### ISS-021 — generic type-driven deliverable surface (headline) [LOCKED]
- **Root cause:** the FE deliverable surface is a CLOSED dispatch keyed on hardcoded pipeline-type strings (`frontend/src/app/dashboard/page.tsx:359-367` content routing; `PreviewPanel.tsx:191-204` `renderType` + :297-304; `WorkflowHistory.tsx:264-269` reopen) with NO generic fallback; and BE `pipeline_complete` (`engine.py:1854-1866`) carries `final_output` but NO mimetype/filename/renderer hint (though the resolved `DeliverableSpec` is already on `ectx.deliverable` at `engine.py:919-923`). The Files tab (`FilesTab.tsx:206-277`) lists only the per-agent `.md` scratch outputs, never the resolved deliverable. 2nd facet: even the `custom` branch routes to `MarkdownPreview` (no `rehype-raw`) → HTML renders as escaped text.
- **Fix — BE (additive, parity-neutral):**
  1. Add optional `mimetype` to `DeliverableSpec` (`plan.py:265-286`); read it through `_compile_deliverable` (`compiler.py:663-684` via `raw.get("mimetype")`). Sensible per-resolver defaults (single_file→infer from `name` extension; serialized_sandbox→`application/zip`; streamed_text→`text/markdown`; ppt→`text/html`) so existing manifests need no edit.
  2. Emit `"deliverable_mimetype"` + `"deliverable_filename"` on the `pipeline_complete` data dict (`engine.py:~1854-1866`) from `getattr(ectx.deliverable, ...)` — no new plumbing.
  3. **INV-3 guard (MANDATORY):** add the new key name(s) to `_VOLATILE_STRIP_KEYS` in `backend/tests/agents/characterization/_normalize.py:107-131` (the sanctioned home for additive-but-parity-neutral keys — `model_id`/`estimated_cost_usd` live there). This keeps the 5 characterization event goldens byte-identical. `_REQUIRED_DATA_KEYS["pipeline_complete"]` is a SUBSET check so additive keys pass.
- **Fix — FE (generic, no per-workflow code):**
  1. Carry `deliverable_mimetype`/`deliverable_filename` from the event into a single new generic content channel for ANY `pipeline_type` that didn't match a known branch (`page.tsx:359-367`), mirrored for history-reopen (`WorkflowHistory.tsx`, persisted via the run row / `wr` fields). 
  2. Add a generic fallback renderer in `PreviewPanel.tsx` keyed on mimetype (used when `renderType` is none of the known set): `text/html`→sandboxed `<iframe srcDoc sandbox="allow-scripts">` (reuse the exact pattern in `PrototypePreview.tsx:605-611` / `PPTPreview.tsx:194-199`); `text/markdown`→`MarkdownPreview`; `application/zip`/bundle→the AppBuilder file-bundle view. Replace the neutral empty-state with the rendered deliverable when one is present.
  3. FilesTab: add ONE generic deliverable row when present (reuse `FileItem.mimeType`/`downloadBlob`, `FilesTab.tsx:33-42,501-516`), keeping the per-agent `.md`s as "Agent outputs".
- **REJECTED hacks:** hardcode `ui_custom_proto`→iframe (DIRECT SC-001 violation — FE knows a workflow by name); route unknown→the `custom` branch (markdown-not-HTML → escaped text); BE content-sniff `final_output` (`startswith("<!doctype")`) — brittle; the manifest already DECLARES the shape.
- **Coordinate with the 4 known types:** their bespoke renderers stay unchanged (no regression to user_story/ppt/prototype/app_builder). The generic path is a FALLBACK.

### ISS-014 — delete the orphaned composer; relocate the model picker [LOCKED]
- **Root cause:** `WorkflowComposer.tsx` is mounted by NO route (pre-existing legacy, base commit `4889e3a8`; grep the FE router → 0 usages); `CapabilityPalette.tsx` + `AgentModelPicker.tsx` are consumed ONLY by it (transitively dead); `/api/capabilities` is live but has ZERO FE consumer. Phase-8 API-06 hung new panels into the legacy unrouted composer; Phase-12 logged it "a separate composer-routing concern" and never resolved it → INV-3/12 dual-impl smell.
- **Fix:** (a) DELETE `frontend/src/components/workflow/WorkflowComposer.tsx` and `CapabilityPalette.tsx` (100% unreachable, superseded by the live `AgentsPopup` agent-composer). (b) `AgentModelPicker` — **prefer to RELOCATE it into the live `AgentsPopup` Agents tab and thread its `onChange` into the `run_pipeline` payload via `useWorkflow.ts` (`model_overrides`), which delivers MODEL-03 end-to-end (BE already persists `model_overrides`)**; if relocation proves too invasive for this phase, DELETE `AgentModelPicker.tsx` too and record MODEL-03's FE-half as a v2 carry-forward (decision recorded in SUMMARY). Do NOT leave it orphaned. (c) KEEP `/api/capabilities` + `test_capabilities_api.py` — API-02 registry-reflection contract + the model-catalog data source.
- **REJECTED hacks:** route the legacy `WorkflowComposer` to "make API-06 real" (resurrects a superseded dual impl with a hardcoded 15-agent stub + an unwired `onSubmit`); delete `/api/capabilities` (regresses API-02/MODEL-04).
- **Reconcile docs:** REQUIREMENTS.md API-06 "Done" + the migration ledger should note the palette-panel deletion-as-superseded; IMPLEMENTATION-REGISTER Phase-8 §line 846 / Phase-12 §line 1198 ("separate composer-routing concern") are now resolved.

### ISS-019 — flex-budget the left execution column [LOCKED]
- **Root cause:** `frontend/src/components/layout/DashboardLayout.tsx:1158-1190` — `AgentProgressPanel` (`flex h-full`, designed to fill 100% + scroll its cards internally) is the FIRST of two block siblings in an `overflow-y-auto` column, so it eats the full height and `WaveTreePanel` (the 2nd sibling) starts at/after the fold; the COLUMN (not the panel) owns the only scroll. The lone test stubs `AgentProgressPanel` so it never caught the fold.
- **Fix (CSS-only, `DashboardLayout.tsx`):** make the column a height-owning flex parent — column wrapper `flex flex-col overflow-hidden` (keep `md:h-full`/widths/borders); wrap `AgentProgressPanel` in `flex-1 min-h-0 overflow-hidden` (it flexes to remaining space, its existing internal `flex-1 overflow-y-auto` cards region scrolls — no `AgentProgressPanel.tsx` change); wrap `WaveTreePanel` as a non-shrinking bottom region `flex-shrink-0 max-h-[40%] overflow-y-auto` (its own `max-h-[260px]` list scroll already present). Both usable at 1440×950; no horizontal regression; nothing hard-clipped.
- **REJECTED hacks:** clamp the agent panel / shrink the wave panel to a fixed px height (clips content; viewport-fragile — the 122px-vs-13px drift); reorder the wave tree ABOVE the agent panel (pushes the headline agent progress below the fold instead).
- **Preserve:** the unconditional `WaveTreePanel` render (`:1186-1190`, panel slot stable) and its props-driven pure-render shape — intentional Phase-12 decisions.

### ISS-015 — WONTFIX (by-design) [LOCKED]
- **Disposition:** the entire product launch surface is the hardcoded 6-tile `CreationHub.tsx:15-22`; `od_ppt`/`od_prototype` go through the PPT/Prototype wizards (which must collect template + design-system — a bare picker structurally can't); bare `prototype`/`ppt` are template-gated-unreachable by design (D-13-06-a, `websocket.py:1344-1361`); `sample_*` aren't in `SUPPORTED_PIPELINE_TYPES` (test fixtures). The custom-workflow need is already met by the live agent-composer (ISS-014). A user-facing named-manifest picker = WF-DB-01 (v2). `GET /api/workflows` (manifest discovery) exists but has no FE consumer — it would power such a picker if v2 wants it.
- **Action:** record WONTFIX in `.planning/ISSUES-REGISTER.md` with this rationale. No code. (A manifest-driven picker, if ever built, must read `/api/workflows` + a `user_launchable` manifest flag — NOT a hardcoded dropdown of names; that hack would ship broken template-gated buttons + expose test fixtures.)

### INVARIANTS
- **INV-3:** the 5 characterization goldens (prototype/od_prototype/prototype_revision/od_ppt/app_builder) MUST stay byte/event-identical. The ONLY parity risk is the new `pipeline_complete` field (ISS-021) — neutralize via `_VOLATILE_STRIP_KEYS`; deliverable BYTES are unchanged. Run the goldens to PROVE it.
- **SC-001:** the generic deliverable renderer dispatches on the declared `mimetype`, never a workflow name — a brand-new custom workflow renders with zero per-workflow FE code. No FE-side workflow-name branch.
- **Ports & Adapters / import-linter:** the BE change reads `ectx.deliverable` the engine already owns (no new cross-boundary import); `lint-imports` stays 4 kept / 0 broken.
- **Additive migrations only:** if history-reopen needs the mimetype persisted, add it as an additive field on the existing run row (carries owner_id/workspace_id) — but prefer deriving it on reopen without a schema change if feasible. Zero destructive migrations.

</decisions>

<canonical_refs>
## Canonical References (read before planning/implementing)

### The WHY
- `.planning/ISSUES-REGISTER.md` → "Deep Root-Cause Investigation" rows ISS-021 / ISS-014 / ISS-019 / ISS-015 (root cause / proper fix / rejected hack / verification).

### Behavior anchors (READ-ONLY unless an edit target)
- BE: `backend/agents/execution_engine/engine.py` (`pipeline_complete` dict ~:1854-1866; `ectx.deliverable` set at :919-923); `backend/agents/workflows/plan.py:265-286` (`DeliverableSpec`); `backend/agents/workflows/compiler.py:663-684` (`_compile_deliverable`); `backend/tests/agents/characterization/_normalize.py:107-131` (`_VOLATILE_STRIP_KEYS` — the parity seam); `backend/agents/capabilities/deliverables/*` (per-resolver default mimetype).
- FE: `frontend/src/components/preview/PreviewPanel.tsx` (`renderType` :191-204, render :297-304, empty-state :291-294); `frontend/src/app/dashboard/page.tsx` (content routing :359-367, reopen :1006); `frontend/src/components/preview/FilesTab.tsx` (:33-42 FileItem, :206-277 deliverable rows, :501-516 downloadBlob); `frontend/src/components/preview/PrototypePreview.tsx:605-611` + `PPTPreview.tsx:194-199` (the sandboxed-iframe pattern to reuse); `frontend/src/components/workflow/WorkflowComposer.tsx` + `CapabilityPalette.tsx` + `AgentModelPicker.tsx` (DELETE/relocate targets); `frontend/src/components/workflow/AgentsPopup.tsx` (relocation host); `frontend/src/hooks/useWorkflow.ts:47-55` (the `run_pipeline` payload — add `model_overrides`); `frontend/src/components/layout/DashboardLayout.tsx:1158-1190` (the ISS-019 column); `frontend/src/components/home/CreationHub.tsx:15-22` (the 6-tile launch surface, ISS-015 context).
- KEEP: `backend/app/api/capabilities.py` + `backend/tests/unit/test_capabilities_api.py`.

</canonical_refs>

<specifics>
## Specific Ideas / Landmines
- ISS-021 is the only INV-3-sensitive item: the new `pipeline_complete` field MUST be in `_VOLATILE_STRIP_KEYS` or the goldens break. Prove with the characterization suite.
- ISS-021 FE: sandbox the HTML iframe (`sandbox="allow-scripts"`, no `allow-same-origin`) — reuse the existing PrototypePreview/PPTPreview pattern; do not introduce a new unsandboxed render path (security).
- ISS-014: before deleting, fault-injection-confirm orphan-ness — rename the files to `.bak`, run `tsc --noEmit` + the FE test suite; both must pass with zero broken imports (proves no live consumer). The wave-mount test (`DashboardLayout.waveMount.test.tsx`) references "unrouted WorkflowComposer" only in a comment — harmless.
- ISS-019: verify with the existing `/tmp/wave_panel_probe.py` (it measures the heading `y`); the fix target is heading bottom ≤ 950 at 1440×950 WITHOUT scroll, during an active `sample_wave` run. Also re-check a long agent list (app_builder ≥8 cards) still scrolls internally + a non-wave run keeps the compact empty state.
- File-overlap to sequence: `PreviewPanel.tsx`/`page.tsx`/`useWorkflow.ts` are touched by ISS-021 (+ possibly ISS-014 model_overrides); `DashboardLayout.tsx` by ISS-019 (+ ISS-014 if the picker relocates through it). The planner must wave/sequence so no two same-wave plans edit the same FE file (use_worktrees=false → sequential anyway, but keep waves honest).

</specifics>

<deferred>
## Deferred Ideas
- Live Playwright visual confirmation of all four (HTML deliverable renders, composer gone, wave panel above fold) — the dedicated UI pass after this phase, on the `default` Bedrock profile.
- A generic manifest-driven pipeline picker (ISS-015) — v2 / WF-DB-01.
- If AgentModelPicker relocation is deferred: MODEL-03 FE-half → v2.
- Cluster D (ISS-004/005/006) → Phase 19.
</deferred>

---

*Phase: 18-custom-workflow-ux-completeness*
*Context: 2026-06-13 from the cluster-E deep investigation, code-proven file:line.*
