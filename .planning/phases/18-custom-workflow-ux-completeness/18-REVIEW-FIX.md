---
phase: 18-custom-workflow-ux-completeness
fixed_at: 2026-06-13T16:08:48Z
review_path: .planning/phases/18-custom-workflow-ux-completeness/18-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 18: Code Review Fix Report

**Fixed at:** 2026-06-13T16:08:48Z
**Source review:** `.planning/phases/18-custom-workflow-ux-completeness/18-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (CR-01 blocker, WR-01/02/03 warnings, IN-01/02 info)
- Fixed: 6
- Skipped: 0

All findings — the CR-01 blocker, all three warnings, and (since trivial) both
Info findings — were applied and committed atomically with hooks enabled. The
INV-3 parity guard was re-proven after the engine.py change; the FE typecheck and
the full ISS-021 vitest area are green.

## Fixed Issues

### CR-01: Live `custom` HTML deliverable renders as escaped text (BLOCKER)

**Files modified:** `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/preview/PreviewPanel.tsx`, `frontend/src/components/preview/PreviewPanel.genericDeliverable.test.tsx`
**Commit:** db725a56
**Applied fix:** Dropped `custom` from the LIVE known-branch set in three places so
it flows into the generic mimetype-dispatched channel, mirroring the already-correct
reopen surface:
- `page.tsx` — removed `|| pipelineType === "custom"` from the user_stories branch
  so a live `custom` deliverable hits the generic `else` (`setGenericDeliverable`).
  Added the shared `deriveDeliverableMimetype(finalOutput)` as a defensive fallback
  when the BE-emitted `deliverable_mimetype` key is absent (older runs / forward-compat);
  the BE key remains authoritative when present.
- `PreviewPanel.tsx` — removed `"custom"` from `KNOWN_RENDER_TYPES`, from the
  `activeContent` ternary, and from the `(app_builder || custom)` render branch (which
  routed `custom` → `MarkdownPreview` → escaped HTML). A live `custom` HTML deliverable
  now renders through `GenericDeliverablePreview` → the `sandbox="allow-scripts"` (NO
  `allow-same-origin`) iframe; a live `custom` markdown deliverable still renders via
  `MarkdownPreview` (no regression to existing markdown-custom reports).
- Added two regression tests locking `workflowType="custom"` + `text/html` → sandboxed
  iframe (NOT MarkdownPreview) and `custom` + `text/markdown` → MarkdownPreview.

Live and reopen now agree; SC-001 holds (dispatch is on the declared mimetype, never
the `custom` name). **This is a logic/routing change — recommend a human eyeball of the
live `custom` render path during the deferred Playwright UI pass**, though the unit
tests assert the dispatch.

### WR-01: serialized_sandbox→streamed_text fallback emits a contradicting mimetype

**Files modified:** `backend/agents/execution_engine/engine.py`
**Commit:** 33c55a44
**Applied fix:** Introduced `_effective_strategy` (starts as the declared strategy,
flips to `"streamed_text"` when the `serialized_sandbox`-resolves-`None` fallback fires)
and derived the emitted `deliverable_mimetype` default from it instead of the declared
strategy. The advertised mimetype now matches the bytes the FE receives
(`text/markdown`, not `application/zip`, when the fallback produced markdown). The
author-declared `mimetype` still wins when present. **INV-3 re-proven** (see below).

### WR-02: history-reopen mis-types a non-markdown custom deliverable

**Files modified:** `frontend/src/types/index.ts`, `frontend/src/types/deriveDeliverableMimetype.test.ts`, `frontend/src/components/history/WorkflowHistory.tsx`
**Commit:** f22e105b
**Applied fix:** Extended the SHARED `deriveDeliverableMimetype` helper to recognise a
serialized-sandbox file bundle (the ```` ```filename: … ``` ```` fenced-block shape the
AppBuilder bundle parser consumes) and emit `application/zip`, so it is no longer
mis-typed to markdown on reopen. `WorkflowHistory.tsx` now routes a derived
`application/zip` to the `AppBuilderPreview` file-bundle view (matching the live
`GenericDeliverablePreview` dispatch), with a MarkdownPreview fallback when the bundle
yields no parseable files. The helper stays the single source both reopen surfaces
import, so live and reopen agree for zip/bundle custom deliverables too.

**Known limitation (recorded per the review's instruction):** the *ideal* fix is
persisting the declared `deliverable_mimetype`/`deliverable_filename` additively on the
run row and reading it on reopen. That additive column was treated as out of scope for
this fix pass (it is a schema change; the review explicitly permits the content-derive
heuristic "where the declared mimetype was not persisted"). Until that column lands, the
content heuristic keeps the live and reopen surfaces in sync for HTML and zip/bundle
deliverables. A custom binary deliverable with no detectable shape still derives to
`text/markdown` on reopen — the residual reopen-only divergence to close in a future
persistence pass.

### WR-03: confirm `MarkdownPreview` does NOT render raw HTML (sandbox-defeat check)

**Files modified:** `frontend/src/components/preview/MarkdownPreview.tsx`, `frontend/src/components/preview/MarkdownPreview.security.test.tsx`
**Commit:** f2ef8a7f
**Confirmation (no behavior change required):** `MarkdownPreview` uses `ReactMarkdown`
with `remarkPlugins={[remarkGfm]}` and **NO `rehypePlugins` / no `rehype-raw`**.
react-markdown's default escapes raw HTML to literal text rather than parsing it into
live DOM — so the generic `text/markdown` path cannot execute embedded `<script>`/
`<iframe>`/`<img onerror>` and cannot defeat the iframe sandbox (T-18-05) the
`text/html` path enforces. There is **no XSS hole**. Documented the invariant as a
SECURITY comment in the component and added a regression test asserting raw
`<script>`/`<iframe>`/`<img>` are not injected as live elements.

### IN-01: `CapabilitiesPalette` doc comment still said "the composer renders"

**Files modified:** `frontend/src/lib/api.ts`
**Commit:** 43be7d37
**Applied fix:** Updated the interface doc to describe the `model_catalog` rendered by
the relocated `AgentModelPicker`, noting the legacy `WorkflowComposer` was deleted in
ISS-014. (Addressed because trivial — doc-only.)

### IN-02: `AgentModelPicker` header docstring referenced the deleted composer

**Files modified:** `frontend/src/components/workflow/AgentModelPicker.tsx`
**Commit:** 6a541f7b
**Applied fix:** Refreshed the docstring to describe its new home (the AgentsPopup
Agents tab) as the primary model-selection surface and removed the "additive sibling
panel … existing composer behavior" line. (Addressed because trivial — doc-only.)

## Verification Performed

**INV-3 (after the engine.py WR-01 change):**
- 5 characterization goldens byte-identical: `pytest` on
  `test_characterization_{prototype,prototype_revision,od_prototype,od_ppt,app_builder}.py`
  → **10 passed** (5 goldens × 2), no `SNAPSHOT_UPDATE`. The new
  `deliverable_mimetype`/`deliverable_filename` keys remain stripped via
  `_VOLATILE_STRIP_KEYS`, so the parity is preserved. Deliverable bytes unchanged.
- `lint-imports` (`/opt/homebrew/bin/lint-imports`): **4 kept / 0 broken**.
- Zero migrations (WR-01/02/03 introduced no schema change; WR-02's bundle detection is
  a FE content heuristic, no run-row column added).

**Frontend:**
- `tsc --noEmit`: **clean** (after every FE change).
- vitest (ISS-021 area — `src/components/preview`, `src/components/history`, `src/types`,
  `FilesTab.test.tsx`): **48 passed / 7 files**, including the genericDeliverable +
  genericReopen + deriveDeliverableMimetype suites and the NEW live-custom-html,
  live-custom-markdown, WR-02 bundle, and WR-03 raw-HTML-escape tests. The 4 known
  deliverable types (user_stories / ppt / prototype / app_builder) still render their
  bespoke renderers (no-regression test green).
- **SC-001 grep clean:** no render-dispatch branch keys on the `custom` (or any) workflow
  name across `PreviewPanel.tsx`, `page.tsx`, `WorkflowHistory.tsx`. The only residual
  `"custom"` literals are a type-cast fallback default and a history filter-group label —
  neither a render decision.

**Security:** the HTML iframe stays `sandbox="allow-scripts"` with NO `allow-same-origin`
on BOTH the live (`GenericDeliverablePreview`) and reopen (`WorkflowHistory.tsx`) surfaces.

## Skipped Issues

None — all 6 findings were fixed.

---

_Fixed: 2026-06-13T16:08:48Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
