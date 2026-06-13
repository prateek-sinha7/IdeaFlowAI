---
phase: 18-custom-workflow-ux-completeness
plan: 03
subsystem: ui
tags: [iss-021, deliverable, mimetype, iframe, sandbox, sc-001, reopen, react, vitest, frontend]

requires:
  - phase: 18-custom-workflow-ux-completeness
    provides: "18-01 — deliverable_mimetype/deliverable_filename emitted on every pipeline_complete (the type-driven contract this FE dispatches on)"
  - phase: 16-iss017-degraded-empty
    provides: "the PreviewPanel/WorkflowHistory reopen surfaces + the terminal-empty affordance plumbing this builds beside"
provides:
  - "Generic mimetype-dispatched fallback renderer for ANY unknown pipeline_type (live PreviewPanel + history-reopen WorkflowHistory) — SC-001, no per-workflow FE branch"
  - "Sandboxed HTML iframe (sandbox='allow-scripts', NO allow-same-origin) on BOTH the live AND reopen surfaces (T-18-05 mitigation)"
  - "Shared exported deriveDeliverableMimetype(output) helper — the single reopen heuristic both reopen surfaces (page.tsx + WorkflowHistory.tsx) import so they cannot diverge"
  - "One generic deliverable row in the Files tab (results/FilesTab.tsx)"
affects: [live Playwright visual pass, any future custom-workflow deliverable shape]

tech-stack:
  added: []
  patterns:
    - "Generic deliverable surface: dispatch on the DECLARED mimetype (live) / output-shape heuristic (reopen), never a workflow name (SC-001)"
    - "Semi-trusted HTML is framed ONLY in a sandbox='allow-scripts' iframe with NO allow-same-origin (the PPTPreview non-od_ppt pattern), asserted as a blocking test on each surface (T-18-05)"
    - "A single shared helper is the reconciliation seam between two independently-rendered reopen surfaces"

key-files:
  created:
    - frontend/src/components/preview/PreviewPanel.genericDeliverable.test.tsx
    - frontend/src/components/history/WorkflowHistory.genericReopen.test.tsx
    - frontend/src/types/deriveDeliverableMimetype.test.ts
  modified:
    - frontend/src/types/index.ts
    - frontend/src/app/dashboard/page.tsx
    - frontend/src/components/layout/DashboardLayout.tsx
    - frontend/src/components/preview/PreviewPanel.tsx
    - frontend/src/components/results/FilesTab.tsx
    - frontend/src/components/results/FilesTab.test.tsx
    - frontend/src/components/history/WorkflowHistory.tsx

key-decisions:
  - "The reopen mimetype is DERIVED from the persisted output shape (<!doctype/<html → text/html, else text/markdown) via ONE shared helper — distinct from the rejected backend content-sniff; the live path uses the declared deliverable_mimetype from 18-01"
  - "The generic branch is a structural 'renderType matched none of the known set' fallback — never a workflow-name check (SC-001); the 4 bespoke renderers are untouched"
  - "Only a full document (doc/html prefix) is framed; a bare HTML fragment falls to markdown — avoids framing arbitrary inline snippets"
  - "Threaded the new generic channel through DashboardLayout (the page.tsx→PreviewPanel bridge) — a blocking plumbing requirement not in the plan file list (Rule 3)"

patterns-established:
  - "Generic mimetype-dispatched deliverable renderer reused on both live + reopen surfaces from a single GenericDeliverable channel"

requirements-completed: [ISS-021]

duration: 12 min
completed: 2026-06-13
---

# Phase 18 Plan 03: ISS-021 Frontend — Generic Mimetype-Dispatched Deliverable Renderer Summary

**A workflow-agnostic, mimetype-dispatched deliverable renderer (HTML→sandboxed iframe, markdown→MarkdownPreview, zip→bundle) for ANY unknown pipeline_type — on BOTH the live PreviewPanel path AND the history-reopen WorkflowHistory detail view — with a shared `deriveDeliverableMimetype` helper, a generic Files-tab row, and zero per-workflow FE branch (SC-001).**

## Performance

- **Duration:** 12 min
- **Started:** 2026-06-13T17:30Z
- **Completed:** 2026-06-13T17:41Z
- **Tasks:** 3 (TDD)
- **Files modified:** 10 (3 created, 7 modified)

## Accomplishments

- **Live path (PreviewPanel):** a generic `GenericDeliverablePreview` fallback, taken only when `renderType` matches none of the known set (user_stories/ppt/prototype/app_builder/custom) AND a generic deliverable is present. Dispatches on the DECLARED `deliverable_mimetype` (18-01 emits it).
- **Reopen path (WorkflowHistory):** replaced the `isMarkdown = isCustom` line (which swallowed HTML into escaped MarkdownPreview) with a structural `isGeneric` flag + a mimetype derived from the persisted output via the SHARED helper. HTML reopens now render the SAME sandboxed iframe, NOT escaped markdown text — the 2nd ISS-021 facet.
- **Security (T-18-05):** the HTML iframe on BOTH surfaces is exactly `sandbox="allow-scripts"` with NO `allow-same-origin` (the PPTPreview non-od_ppt pattern). Asserted as a blocking test on each surface.
- **Shared helper:** `deriveDeliverableMimetype(output)` exported from `types/index.ts`, imported by page.tsx's reopen block AND WorkflowHistory.tsx — the two reopen surfaces cannot diverge.
- **Files tab:** one generic deliverable row (resolved mimetype + filename, existing `downloadBlob` path), per-agent `.md` outputs preserved.

## The generic renderer dispatch table (identical on live + reopen)

| Declared / derived mimetype | Renderer | Security |
|---|---|---|
| `text/html` (or `text/html;…`) | `<iframe srcDoc sandbox="allow-scripts">` | NO `allow-same-origin` (T-18-05) |
| `text/markdown` / `text/x-markdown` | `<MarkdownPreview>` | n/a (no raw HTML execution) |
| `application/zip` / `*zip*` | AppBuilder file-bundle view | parsed, not executed |
| anything else (live only) | safe download affordance | never inline/execute (T-18-06) |

Reopen has no zip/bundle shape detectable from raw bytes, so the reopen heuristic resolves to `text/html` (doc/html prefix) or `text/markdown` (everything else); markdown covers the prior `custom` behavior.

## The exact iframe sandbox attribute (PROVEN no allow-same-origin on each surface)

- **Live (PreviewPanel.tsx):** `<iframe srcDoc={content} sandbox="allow-scripts" />` — asserted by `PreviewPanel.genericDeliverable.test.tsx`: `getAttribute("sandbox") === "allow-scripts"` AND `not.toContain("allow-same-origin")`.
- **Reopen (WorkflowHistory.tsx):** `<iframe srcDoc={selectedOutput} sandbox="allow-scripts" />` — asserted by `WorkflowHistory.genericReopen.test.tsx` with the same two assertions, PLUS `queryByTestId("markdown-preview")` is `not.toBeInTheDocument()` (the old escaped-HTML path is gone).

## The shared reopen heuristic (both surfaces import it)

`deriveDeliverableMimetype(output)` in `frontend/src/types/index.ts`: `output.trimStart().toLowerCase()` starts with `<!doctype` or `<html` → `text/html`; else → `text/markdown` (empty/null/fragment → `text/markdown`, nothing to frame). Imported by:
- `frontend/src/app/dashboard/page.tsx` (the page.tsx reopen block, `else` fallback for unknown `fullRun.type`).
- `frontend/src/components/history/WorkflowHistory.tsx` (the detail-view `isGeneric` dispatch — the user-visible reopen surface).

## SC-001 no-name-literal grep result

```
grep -rn "ui_custom_proto" \
  frontend/src/components/preview/PreviewPanel.tsx \
  frontend/src/components/results/FilesTab.tsx \
  frontend/src/components/history/WorkflowHistory.tsx
→ 0 matches
```

Dispatch is on mimetype / output-shape only, on all three deliverable surfaces.

## Task Commits

1. **Task 1: Generic content channel + shared deriveDeliverableMimetype helper** — `5f6ca616` (feat) — TDD: helper test authored + green.
2. **Task 2: Generic renderer in PreviewPanel + sandboxed iframe + generic Files row** — `3ae12120` (feat) — TDD: `PreviewPanel.genericDeliverable.test.tsx` (RED→GREEN) + extended `FilesTab.test.tsx`.
3. **Task 3: Close the reopen facet in WorkflowHistory.tsx** — `13d1ad0c` (feat) — TDD: `WorkflowHistory.genericReopen.test.tsx` authored RED, driven GREEN.

## Files Created/Modified

- `frontend/src/types/index.ts` — `PipelineCompleteData`/`GenericDeliverable` types + exported `deriveDeliverableMimetype` helper.
- `frontend/src/app/dashboard/page.tsx` — `genericDeliverable` state; live `pipeline_complete` + history-reopen `else` fallbacks; reset on every new-run/reopen; thread to DashboardLayout.
- `frontend/src/components/layout/DashboardLayout.tsx` — pass-through plumbing for the generic channel (page.tsx→PreviewPanel bridge).
- `frontend/src/components/preview/PreviewPanel.tsx` — `GenericDeliverablePreview` (html/md/zip/download dispatch) + `hasGenericDeliverable` gating + FilesTab wiring.
- `frontend/src/components/results/FilesTab.tsx` — one generic deliverable row + `genericDeliverableExtension` mimetype→metadata helper.
- `frontend/src/components/history/WorkflowHistory.tsx` — `isGeneric`/`genericMimetype` dispatch; sandboxed reopen iframe; FilesTab generic wiring.
- 3 test files (created) — generic deliverable (live), generic reopen, and the shared-helper unit test.

## Verification Evidence (PROVEN)

- `cd frontend && npx tsc --noEmit` → clean (no output).
- `npx vitest run src/components/preview/PreviewPanel.genericDeliverable.test.tsx src/components/results/FilesTab.test.tsx src/components/history/WorkflowHistory.genericReopen.test.tsx src/types/deriveDeliverableMimetype.test.ts` → **27 passed**.
- Broader sweep `npx vitest run src/components/preview src/components/results src/components/history src/types` → **41 passed** (no regression to PreviewPanel.degraded / WorkflowHistory chain tests).
- SC-001 grep across all 3 deliverable surfaces → **0 matches**.
- Diff is **frontend-only** (no backend change — consumes 18-01's emitted keys).

## Decisions Made

See `key-decisions` frontmatter. Headline: the live path dispatches on the DECLARED `deliverable_mimetype`; the reopen path derives the mimetype from the persisted output shape via ONE shared helper — never a workflow name (SC-001), and the HTML iframe is sandboxed (allow-scripts, no allow-same-origin) on BOTH surfaces.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Threaded the generic channel through DashboardLayout.tsx (not in the plan's file list)**
- **Found during:** Task 1 (generic content channel)
- **Issue:** PreviewPanel is rendered by `DashboardLayout`, not directly by `page.tsx`. The plan's `files_modified` listed page.tsx → PreviewPanel but omitted the intermediary; without threading the new `genericDeliverable` prop through DashboardLayout, the channel could not reach PreviewPanel (TS error + no runtime data).
- **Fix:** Added `genericDeliverable?: GenericDeliverable` to `DashboardLayoutProps`, destructured it, and passed it to the `<PreviewPanel>` render. Pure pass-through plumbing — no logic.
- **Files modified:** frontend/src/components/layout/DashboardLayout.tsx
- **Verification:** tsc clean; the live channel reaches PreviewPanel (covered by the genericDeliverable render tests).
- **Committed in:** 5f6ca616 (Task 1 commit)

**2. [Rule 2 - Missing Critical] Added a focused unit test for the shared helper (deriveDeliverableMimetype.test.ts)**
- **Found during:** Task 1
- **Issue:** The shared helper is the single reconciliation seam between two independently-rendered reopen surfaces; the plan's named test files cover the rendered surfaces but not the helper's edge cases (empty/null/fragment/case-insensitivity) directly.
- **Fix:** Added `frontend/src/types/deriveDeliverableMimetype.test.ts` (6 cases). Additive — does not replace any named plan test.
- **Files modified:** frontend/src/types/deriveDeliverableMimetype.test.ts (created)
- **Verification:** 6/6 green.
- **Committed in:** 5f6ca616 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking plumbing, 1 missing-critical test). **Impact:** Both necessary for correctness/coverage; no scope creep — the diff stays frontend-only and SC-001-clean.

## Issues Encountered

- The generic download-affordance test initially matched two "download" texts (copy + button). Resolved by asserting `getByRole("button", { name: /download/i })`. Test-construction detail, not a behavior change.

## Known Stubs

None — the generic renderer wires real data (`genericDeliverable.content` from the live `pipeline_complete` event / the persisted reopen output). No hardcoded/placeholder content introduced.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

ISS-021 is now closed on BOTH FE facets (live + reopen) atop 18-01's backend contract. The true visual proof (a real custom HTML deliverable rendering in the sandboxed iframe on both surfaces) runs in the deferred live Playwright pass — offline proof is the 27 component tests. No blockers.

## Self-Check: PASSED

- `frontend/src/components/preview/PreviewPanel.genericDeliverable.test.tsx` — FOUND
- `frontend/src/components/history/WorkflowHistory.genericReopen.test.tsx` — FOUND
- `frontend/src/types/deriveDeliverableMimetype.test.ts` — FOUND
- Commit `5f6ca616` — FOUND
- Commit `3ae12120` — FOUND
- Commit `13d1ad0c` — FOUND

---
*Phase: 18-custom-workflow-ux-completeness*
*Completed: 2026-06-13*
