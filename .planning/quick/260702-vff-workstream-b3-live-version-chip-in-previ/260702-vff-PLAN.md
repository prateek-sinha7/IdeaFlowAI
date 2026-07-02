---
phase: 260702-vff
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/components/preview/PreviewPanel.tsx
  - frontend/src/components/preview/LiveVersionChip.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/components/results/FilesTab.tsx
  - frontend/src/components/preview/PreviewPanel.versionChip.test.tsx
  - frontend/src/components/results/FilesTab.baseVersion.test.tsx
autonomous: true
requirements: [POR-5-D5, POR-5-D6]

must_haves:
  truths:
    - "In the live dashboard preview, a 'v{n} ▾' chip appears in the PreviewPanel header ONLY when the on-screen content belongs to a revision family with >=2 members; it is absent for standalone / single-member content and when no family is threaded (POR-5-D5, UI-SPEC Surface 3)."
    - "Clicking the chip opens a version dropdown (listbox) listing v1..vN with status dots; selecting an OLDER version loads that version read-only via getWorkflow(memberId) and shows an amber 'Viewing v{k} (read-only) — Back to latest →' banner; 'Back to latest →' restores the live latest content (POR-5-D5, UI-SPEC Surface 3)."
    - "When a revision completes and the threaded family grows, the chip label increments v{n}→v{n+1} with a one-shot animate-pulse (POR-5-D5, UI-SPEC Surface 3)."
    - "A revision run's Files tab shows a collapsed 'From v{n-1}' base-version section that LAZILY fetches the parent run's files via getWorkflow(parentRunId) on first expand (no fetch while collapsed); a non-revision run (parentRunId null) shows NO such section (POR-5-D6, UI-SPEC Surface 4)."
    - "The version chip carries aria-haspopup='listbox' + aria-expanded, the dropdown is role='listbox' with role='option' aria-selected items, and the read-only banner is role='status' (POR §8 a11y, UI-SPEC Surfaces 3+4)."
    - "REGRESSION GUARD: every pre-existing suite that renders PreviewPanel or FilesTab still passes — all new props are OPTIONAL with safe defaults (undefined → chip/section absent), and no test breaks on a missing @/lib/api mock export or a new required prop."
  artifacts:
    - path: "frontend/src/components/preview/LiveVersionChip.tsx"
      provides: "Presentational live version chip + version dropdown (listbox) + read-only amber banner — all styling inherited per UI-SPEC Surface 3"
      min_lines: 60
    - path: "frontend/src/components/preview/PreviewPanel.tsx"
      provides: "Optional runFamily/liveRunId props; owns viewing-version state + getWorkflow read-only override; threads parentRunId to FilesTab"
      contains: "LiveVersionChip"
    - path: "frontend/src/components/layout/DashboardLayout.tsx"
      provides: "getRunFamily fetch keyed on contentSourceRunId; threads runFamily + liveRunId to PreviewPanel"
      contains: "getRunFamily"
    - path: "frontend/src/components/results/FilesTab.tsx"
      provides: "Base-version 'From v{n-1}' collapsed section with lazy getWorkflow(parentRunId); reused deriveDeliverableFiles helper"
      contains: "parentRunId"
    - path: "frontend/src/components/preview/PreviewPanel.versionChip.test.tsx"
      provides: "Real-DOM specs: chip visibility, dropdown+read-only load, pulse tick, a11y roles"
      min_lines: 80
    - path: "frontend/src/components/results/FilesTab.baseVersion.test.tsx"
      provides: "Real-DOM specs: base-version section presence/absence + lazy parent fetch on expand"
      min_lines: 50
  key_links:
    - from: "frontend/src/components/layout/DashboardLayout.tsx"
      to: "getRunFamily"
      via: "useEffect keyed on contentSourceRunId → setRunFamily; runFamily passed to PreviewPanel"
      pattern: "getRunFamily\\("
    - from: "frontend/src/components/preview/PreviewPanel.tsx"
      to: "getWorkflow"
      via: "read-only older-version content fetch on dropdown selection"
      pattern: "getWorkflow\\("
    - from: "frontend/src/components/preview/PreviewPanel.tsx"
      to: "frontend/src/components/results/FilesTab.tsx"
      via: "parentRunId + parentVersionNumber props threaded to FilesTab"
      pattern: "parentRunId="
    - from: "frontend/src/components/results/FilesTab.tsx"
      to: "getWorkflow"
      via: "lazy parent-files fetch on base-version section expand"
      pattern: "getWorkflow\\("
---

<objective>
Deliver POR §5 deliverables 5 + 6 on the LIVE dashboard surface, FRONTEND-ONLY, strictly per WORKSTREAM-B-UI-SPEC.md Surfaces 3 + 4. Deliverable 5 adds a "v{n} ▾" live version chip to the PreviewPanel header that opens a version dropdown and loads older versions read-only. Deliverable 6 adds a collapsed "From v{n-1}" base-version section to the FilesTab that lazily loads the parent run's files.

This is the FINAL build unit of Workstream B (B1 = foundation/linkage shipped; B2 = history surface shipped). It CLOSES Workstream B by consuming B1's `getRunFamily` + `contentSourceRunId` + `WorkflowRun.parentRunId/rootRunId` and reusing B2's `statusDotClass` analog.

Purpose: give users a live, in-preview affordance to see they are on a revision family, jump to prior versions read-only, and reference the base version's files — with ZERO net-new visual language (every node inherits an existing analog).
Output: a new `LiveVersionChip.tsx` sub-component, wiring in `PreviewPanel.tsx` + `DashboardLayout.tsx` (fetch seam) + `FilesTab.tsx` (base section), and two new real-DOM vitest specs. ZERO backend edits (INV-3 by construction).
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/WORKSTREAM-B-UI-SPEC.md
@.planning/REVISION-FAMILY-AND-RUN-INPUTS-PLAN.md
@.planning/quick/260702-uos-workstream-b2-revision-family-history-gr/260702-uos-SUMMARY.md
@.planning/quick/260702-u2o-workstream-b1-revision-family-fe-foundat/260702-u2o-SUMMARY.md

# Files this plan touches / reuses (analogs cited inline in each task):
@frontend/src/components/preview/PreviewPanel.tsx
@frontend/src/components/results/FilesTab.tsx
@frontend/src/components/layout/DashboardLayout.tsx
@frontend/src/components/history/RevisionFamilyView.tsx
@frontend/src/lib/api.ts
@frontend/src/types/index.ts
@frontend/src/components/history/WorkflowHistory.family.test.tsx
</context>

<design_decisions>
Locked architecture (resolves the "where does the fetch happen" question in the task spec):

- **DashboardLayout owns the `getRunFamily` fetch** (not PreviewPanel, not page.tsx). Justification: DashboardLayout already receives `contentSourceRunId` as a prop (DashboardLayout.tsx:65,248) AND mounts PreviewPanel directly (:1479). Fetching here keyed on `contentSourceRunId` is the minimal seam — it avoids adding a page.tsx→DashboardLayout pass-through prop, and keeps PreviewPanel free of the family-lifecycle fetch. DashboardLayout threads `runFamily` + `liveRunId={contentSourceRunId}` into PreviewPanel as new OPTIONAL props.

- **PreviewPanel stays presentational for the family, but owns ONE on-demand fetch:** the read-only older-version content load via `getWorkflow(memberId)`. Justification: mapping a fetched run's `.output` into the correct render slot depends on `renderType`, which PreviewPanel already computes (PreviewPanel.tsx:385-398). Threading the override content up to DashboardLayout would duplicate that mapping. The chip/dropdown/banner UI is extracted to a presentational sibling `LiveVersionChip.tsx` (mirroring B2's `RevisionFamilyView.tsx`); PreviewPanel owns the `viewingVersionId` + `overrideContent` state.

- **The active on-screen version's `parent_run_id` is read from the threaded `runFamily.members`** (each member carries `parent_run_id`, types/index.ts:322) — no extra fetch. PreviewPanel derives `parentRunId` for the active member and passes it to FilesTab.

- **SC-001 (no workflow-name branching):** the chip gates purely on `runFamily.members.length >= 2`; the base-Files section gates purely on `parentRunId != null` (PreviewPanel already passes the base `renderType` — with `_revision` stripped — to FilesTab at :632, so a suffix check there is impossible AND unnecessary; `parentRunId` IS the generic revision signal from B1).

- **Regression safety by construction:** ALL new props are optional and default to undefined → the chip and the base-Files section are absent unless explicitly wired by the live mount. History callers (WorkflowHistory) and existing PreviewPanel/FilesTab test renders pass neither → zero visual/behavioral change.

- **Revision-instruction parser:** NOT needed here. The read-only banner reads "Viewing v{k} (read-only)"; no instruction text. Do NOT author a parser (Workstream C owns `parseRunInput`); if a preview string were ever needed, reuse B2's `extractRevisionInstructionPreview` shim.
</design_decisions>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Deliverable 5 — live version chip in PreviewPanel + DashboardLayout family fetch seam</name>
  <files>frontend/src/components/preview/LiveVersionChip.tsx, frontend/src/components/preview/PreviewPanel.tsx, frontend/src/components/layout/DashboardLayout.tsx</files>
  <behavior>
    - Chip hidden when runFamily is undefined/null or has <2 members (standalone content).
    - Chip visible as "v{n} ▾" when runFamily has >=2 members; n = the on-screen version's 1-based index.
    - Clicking the chip opens a dropdown listing all members v1..vN (status dot + timestamp), active member highlighted.
    - Selecting an OLDER member calls getWorkflow(token, memberId), renders that member's output read-only, shows the amber "Viewing v{k} (read-only) — Back to latest →" banner, and the chip shows the amber sub-dot.
    - "Back to latest →" clears the read-only view; the live latest content renders again and the banner disappears.
    - When runFamily.members.length increases (revision completed → new member) the chip label ticks to v{n+1} and briefly carries animate-pulse.
    - When liveRunId changes, any active read-only view resets to latest.
  </behavior>
  <action>
    Create `frontend/src/components/preview/LiveVersionChip.tsx` as a presentational sibling (the B2 `RevisionFamilyView.tsx` pattern): a top-of-file REUSE-FIRST comment block citing UI-SPEC Surface 3, then export two components. (1) `LiveVersionChip`: props `{ family: RunFamily | null, activeRunId: string | null, isViewingOlder: boolean, pulse: boolean, onSelectVersion: (id) => void, onBackToLatest: () => void }`. Render nothing when family is null or has fewer than 2 members. Order members by `revision_index` ASC. The chip is a `button` cloning the PrototypePreview toggle-pill (UI-SPEC analog PrototypePreview.tsx:529-539): classes `flex h-6 items-center gap-1 rounded px-1.5 text-[10px] font-medium`, idle `text-gray-400 hover:bg-gray-100 hover:text-gray-700`, open `bg-[#1B2A4A] text-white`; label `v{activeIdx+1}` plus a trailing `ChevronDown` (lucide, AgentThinkingTab.tsx:164 analog); apply `animate-pulse` (AgentThinkingTab.tsx:123,163 analog) when `pulse` is true; when `isViewingOlder`, append the amber sub-dot `ml-0.5 h-1.5 w-1.5 rounded-full bg-amber-400` (PrototypePreview.tsx:538 analog). Chip a11y: `aria-haspopup="listbox"`, `aria-expanded={open}`, and an `aria-label` of the form "Current version vN, choose version". The dropdown clones the WorkflowHistory row-menu (UI-SPEC analog WorkflowHistory.tsx:925-944): an `AnimatePresence` plus a `motion.div` with `initial opacity:0 scale:0.95 y:-4` → `animate opacity:1 scale:1 y:0` → `exit`, `transition duration:0.1`, panel classes `absolute right-0 top-8 z-20 bg-white border border-gray-200 rounded-lg shadow-lg py-1 min-w-[120px]`, wrapped so the chip and panel share a `relative` container; add the outside-click catcher `fixed inset-0 z-10` (WorkflowHistory.tsx:961-963 analog) and an Escape handler that closes the dropdown and returns focus to the chip. Dropdown is `role="listbox"`; each item a `button role="option" aria-selected={isActive}` showing a v-chip label plus a status dot (reuse the inherited status→dot color; import `statusDotClass` from `@/components/history/RevisionFamilyView` — do NOT re-derive) plus a relative timestamp (a small local relative-time helper is fine; do not import from a component that would create a cycle). Active option highlighted `bg-gray-100 text-gray-900`. Arrow Up/Down move the highlighted option, Enter selects, Escape closes. (2) `ReadOnlyVersionBanner`: props `{ versionNumber, onBackToLatest }`, cloning the ReviewGatePanel amber notice (UI-SPEC analog ReviewGatePanel.tsx:398-403): `flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2` plus `text-[10px] text-amber-700`, a leading amber icon (`AlertTriangle h-3.5 w-3.5 text-amber-600`), text "Viewing v{versionNumber} (read-only)", and a link-style text button `text-amber-700 font-medium` reading "Back to latest →"; the banner root carries `role="status"`.

    Wire `PreviewPanel.tsx`: add OPTIONAL props to `PreviewPanelProps` — `runFamily?: RunFamily | null` and `liveRunId?: string | null` (default undefined). Import `RunFamily` from `@/types/index`, add `getWorkflow` to the existing `@/lib/api` import (PreviewPanel already imports `getToken` from `@/lib/api`), and import `LiveVersionChip`, `ReadOnlyVersionBanner` from `./LiveVersionChip`. Add state: `viewingVersion` as `{ id, content } | null` (the read-only override) and `pulse` boolean. Compute `sortedMembers` from `runFamily` by `revision_index`; `latestId` = last member id (fallback `liveRunId`); `activeRunId` = `viewingVersion?.id ?? liveRunId ?? latestId`; `activeIdx` = index of `activeRunId` in `sortedMembers`. `isViewingOlder` = `viewingVersion != null` and its id !== `latestId`. Handler `handleSelectVersion(id)`: if id === latestId, clear `viewingVersion` (back to live); else `getWorkflow(getToken(), id)` inside try/catch, then `setViewingVersion({ id, content: run.output })`. Handler `handleBackToLatest`: `setViewingVersion(null)`. Effect on `runFamily?.members.length`: when it increases past the previous value (stored in a ref), set `pulse` true then clear after ~1200ms. Effect on `liveRunId`: reset `viewingVersion` to null (a new live run supersedes any read-only view). Rendering: (a) mount `LiveVersionChip` as the FIRST control inside the header control cluster `flex items-center gap-1` (PreviewPanel.tsx:528, before the Copy button per UI-SPEC "Where"), passing family/activeRunId/isViewingOlder/pulse/onSelectVersion/onBackToLatest. (b) Render `ReadOnlyVersionBanner` (versionNumber = activeIdx+1) as a slim strip directly under the header (after the header div at :548, above the tab bar at :550) ONLY when `isViewingOlder`. (c) When `viewingVersion` is set, the deliverable renderers must use the override content: derive effective userStory/ppt/prototype content by routing `viewingVersion.content` into the slot matching `renderType` (user_stories/app_builder → userStory slot, ppt → ppt slot, prototype → prototype slot) and feed those into `FIRST_PARTY_RENDERERS` plus `activeContent`/`hasContent`; force the bespoke renderers' `onRevise*` to undefined while viewing older (read-only). Keep all existing degraded/generic branches intact when NOT viewing older. Do NOT fetch getRunFamily inside PreviewPanel.

    Wire `DashboardLayout.tsx`: import `getRunFamily` plus `getToken` from `@/lib/api` and `RunFamily` from `@/types/index`. Add state `runFamily` as `RunFamily | null` (null default). Add a `useEffect` keyed on `contentSourceRunId`: if falsy, `setRunFamily(null)` and return; else `getRunFamily(getToken(), contentSourceRunId)` with `.then(setRunFamily).catch(() => setRunFamily(null))` — the catch guarantees it never throws even if a test invokes it. At the PreviewPanel mount (:1479) add `runFamily={runFamily}` and `liveRunId={contentSourceRunId ?? null}`. Do NOT change any existing prop or the chat-composer revise handlers.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | grep -c "error TS"</automated>
  </verify>
  <done>LiveVersionChip.tsx exists exporting LiveVersionChip + ReadOnlyVersionBanner; PreviewPanel mounts the chip in the header control cluster with optional runFamily/liveRunId props and owns viewingVersion/pulse state + getWorkflow read-only override; DashboardLayout fetches getRunFamily keyed on contentSourceRunId and threads runFamily + liveRunId to PreviewPanel. tsc error count is still 3 (the known baseline — no new red).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Deliverable 6 — base-version "From v{n-1}" Files section (FilesTab) + parentRunId thread</name>
  <files>frontend/src/components/results/FilesTab.tsx, frontend/src/components/preview/PreviewPanel.tsx</files>
  <behavior>
    - FilesTab with parentRunId=null (or omitted): NO base-version section rendered (non-revision + all existing renders unchanged).
    - FilesTab with a non-null parentRunId: a collapsed "From v{n-1}" section renders (SectionHeader style); parent files are NOT fetched while collapsed.
    - Expanding the section calls getWorkflow(token, parentRunId) exactly once, then renders the parent run's file rows via the same renderFileRow shape; a spinner shows while loading; "No files in the base version." shows if the parent has none.
    - The section toggle is a real button with aria-expanded + aria-label; the section carries aria-busy while fetching.
  </behavior>
  <action>
    In `FilesTab.tsx`: (1) Refactor the per-type single-deliverable file-building branches currently inline in the component body (FilesTab.tsx:220-292 — the user_stories, ppt, prototype, and custom `files.push(...)` branches) into a module-level pure helper `deriveDeliverableFiles(workflowType, content)` returning `FileItem[]`, where `content` is `{ userStoryContent?, pptContent?, prototypeContent? }`. Keep behavior byte-identical for the current run: the component body calls this helper to build its `files` array for the non-app-builder single-deliverable branches (net-negative duplication per INV-12 — the extracted branches are DELETED from the body, not copied). Leave the app_builder ZIP special-case (:229-260) and the generic-deliverable row (:300-313) in the component body unchanged (they need agentOutputs/JSZip and are out of scope for the base-version reference). (2) Add OPTIONAL props to `FilesTabProps`: `parentRunId?: string | null` and `parentVersionNumber?: number` (default undefined). (3) Add a new controlled base-version section rendered at the END of BOTH the app-builder and non-app-builder layout branches (UI-SPEC Surface 4 "Where": after the Final output / Agent outputs sections), gated on `parentRunId` being truthy. Section header clones `SectionHeader` (FilesTab.tsx:152-159) with label "From v{parentVersionNumber ?? previous}"; the collapse affordance is a controlled `button` with `aria-expanded={baseOpen}` and an aria-label of the form "From version {parentVersionNumber ?? previous}", plus a chevron that rotates when open (controlled rotate — the B2 W2 lesson: NOT group-open, which only fires inside a native details element). On first expand, set `baseOpen` true and lazily fetch: `const { getWorkflow, getToken } = await import("@/lib/api")` (reuse the existing dynamic-import idiom at FilesTab.tsx:359) → `getWorkflow(getToken(), parentRunId)` → store the resolved run; derive its rows with `deriveDeliverableFiles(parentRun.type, { userStoryContent: parentRun.output, pptContent: parentRun.output, prototypeContent: parentRun.output })` (route the parent `.output` into every slot — `deriveDeliverableFiles` self-selects by `parentRun.type`). While the fetch is in flight, mark the section `aria-busy` and show the existing row-spinner idiom (`span h-3.5 w-3.5 border-2 border-gray-400 border-t-transparent rounded-full animate-spin`, FilesTab.tsx:438). On loaded: render each parent file via `renderFileRow` (verbatim reuse) plus a caption `text-[10px] text-gray-400` "Files from the previous version this revision was based on." On empty: "No files in the base version." in `text-[10px] text-gray-400` (FilesTab.tsx:404-406 muted analog). Guard the fetch so it runs at most once (track a `baseFetched` flag). IMPORTANT: the `totalCount === 0` early return (:401) must NOT suppress the base section when the current run has content — the base section lives inside the normal render path, which is only reached when totalCount > 0; that is acceptable (a completed revision always has current content).

    In `PreviewPanel.tsx`: at the `FilesTab` mount (:632), compute the active member's parent from the threaded family — find the sorted member whose id === activeRunId, read its `parent_run_id` (null if none) — and pass `parentRunId={activeParentRunId}` and `parentVersionNumber={activeIdx}` (the parent is the immediately-prior version → its 1-based number equals the active member's 0-based index `activeIdx`). Leave every other FilesTab prop unchanged.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | grep -c "error TS"</automated>
  </verify>
  <done>FilesTab exposes optional parentRunId + parentVersionNumber; a collapsed "From v{n-1}" section renders only when parentRunId is non-null and lazily fetches parent files via getWorkflow on first expand using the reused deriveDeliverableFiles + renderFileRow; the current-run file lists are byte-identical (helper extraction is behavior-preserving); PreviewPanel threads parentRunId + parentVersionNumber from the active family member. tsc error count is still 3.</done>
</task>

<task type="auto">
  <name>Task 3: vitest real-DOM specs + regression audit + hard gates</name>
  <files>frontend/src/components/preview/PreviewPanel.versionChip.test.tsx, frontend/src/components/results/FilesTab.baseVersion.test.tsx</files>
  <action>
    Create two vitest specs following the B2 `WorkflowHistory.family.test.tsx` idioms: the motion/react Proxy mock (strip animation-only props; `AnimatePresence` passes children), a full `@/lib/api` mock exporting `getToken`, `getWorkflow`, `getRunFamily` (mock ALL three even if a spec only uses one — matches the B2 mock surface so nothing is undefined), and stubs for the heavy bespoke preview children the same way `PreviewPanel.degraded.test.tsx` does (UserStoryPreview/PPTPreview/PrototypePreview/MarkdownPreview/AppBuilderPreview/AgentThinkingTab → cheap markers). Assert on REAL rendered DOM (roles/text), never source-lock — both PreviewPanel and FilesTab render in vitest.

    `PreviewPanel.versionChip.test.tsx` — cases: (1) CHIP VISIBILITY — render PreviewPanel with `prototypeContent` plus a `runFamily` of >=2 members plus `liveRunId` = the latest member id → a chip button with `aria-haspopup="listbox"` and a label containing "v{N}" is present; render with `runFamily={null}` (or a single-member family) → no such button (query returns null). (2) DROPDOWN + READ-ONLY LOAD — with a >=2 family, click the chip → a `role="listbox"` appears with `role="option"` items; `mockGetWorkflow` returns an older member's run keyed by id; click the older option → assert `getWorkflow` was called with that member id AND a `role="status"` banner containing "Viewing v" and "read-only" appears; click "Back to latest" → the banner is gone. (3) CHIP PULSE/TICK — render with a 2-member family (chip shows v2), then rerender with a 3-member family plus liveRunId = the new member → the chip label reflects v3 (assert the incremented label text; the animate-pulse class is a nice-to-have, the label increment is the load-bearing assertion). (4) A11Y — chip has aria-haspopup="listbox" plus aria-expanded; after opening, the listbox plus options carry role plus aria-selected.

    `FilesTab.baseVersion.test.tsx` — cases: (5) BASE SECTION PRESENCE + LAZY FETCH — render FilesTab with workflowType="prototype", a prototype current content, parentRunId="parent-1", parentVersionNumber={1} → a collapsed "From v1" section toggle is present and `getWorkflow` has NOT been called yet; click the toggle → assert `getWorkflow` called with "parent-1" and the parent's file row(s) render (mock `getWorkflow` to resolve a prototype run whose output parses to one file). (6) ABSENCE — render the same FilesTab with `parentRunId={null}` (or omitted) → no "From v" section anywhere (query returns null); the current-run prototype file still renders (regression: existing behavior intact).

    REGRESSION AUDIT — this is a must_have. The full set of pre-existing suites that render PreviewPanel or FilesTab (audited from source): PreviewPanel.degraded.test.tsx, PreviewPanel.genericDeliverable.test.tsx, FilesTab.test.tsx, WorkflowHistory.test.tsx, WorkflowHistory.revise.test.tsx, WorkflowHistory.family.test.tsx, WorkflowHistory.genericReopen.test.tsx, DashboardLayout.catalogHome.test.tsx, DashboardLayout.waveMount.test.tsx. Run ALL of them plus the two new specs. If ANY pre-existing suite fails on a missing @/lib/api mock export (e.g. a suite that mocks @/lib/api without getRunFamily/getWorkflow now that DashboardLayout/PreviewPanel reference them) or a new required prop, FIX by adding the missing mock export or ensuring the prop stays optional — never by weakening an assertion. (Note: the two DashboardLayout suites do not mock @/lib/api and render with contentSourceRunId undefined → the guarded getRunFamily effect never fires; the existing PreviewPanel suites pass no runFamily → no chip, no getWorkflow call. Both are expected green without edits; run them to prove it.)
  </action>
  <verify>
    <automated>cd frontend && npx vitest run src/components/preview/PreviewPanel.versionChip.test.tsx src/components/results/FilesTab.baseVersion.test.tsx src/components/preview/PreviewPanel.degraded.test.tsx src/components/preview/PreviewPanel.genericDeliverable.test.tsx src/components/results/FilesTab.test.tsx src/components/history/WorkflowHistory.test.tsx src/components/history/WorkflowHistory.revise.test.tsx src/components/history/WorkflowHistory.family.test.tsx src/components/history/WorkflowHistory.genericReopen.test.tsx src/components/layout/DashboardLayout.catalogHome.test.tsx src/components/layout/DashboardLayout.waveMount.test.tsx</automated>
    <automated>cd frontend && COUNT=$(npx tsc --noEmit 2>&1 | grep -c 'error TS'); NEW=$(npx tsc --noEmit 2>&1 | grep 'error TS' | grep -vcE 'mockApi\.ts|IdeaInputPage\.tsx'); test "$COUNT" = "3" && test "$NEW" = "0" && echo GATE_OK || echo GATE_FAIL</automated>
  </verify>
  <done>Two new specs (PreviewPanel.versionChip + FilesTab.baseVersion) are green with real-DOM assertions covering chip visibility, dropdown+read-only load, pulse/tick, base-version presence/absence+lazy fetch, and a11y roles. ALL 9 pre-existing PreviewPanel/FilesTab suites still pass (regression guard). tsc shows EXACTLY the 3 known reds by identity (COUNT==3 AND the non-mockApi/IdeaInputPage filter is 0 → GATE_OK).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser → GET /api/runs/{id} + /family | Read-only fetch of sibling/parent run content for the version dropdown, read-only view, and base-version files |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-vff-01 | Information Disclosure | getWorkflow / getRunFamily (read-only view of a sibling/parent run) | accept | No NEW boundary — B1 established these fetchers against the Workstream-A IDOR-hardened `GET /api/runs/{id}` + `/family` endpoints (owner_id/workspace_id scoped server-side, per B1 SUMMARY). The FE only requests ids the server already returned in the family payload; access control is enforced server-side, unchanged. |
| T-vff-02 | Tampering | npm/pip/cargo installs | mitigate | None needed — ZERO new packages (reuses motion/react, lucide-react, existing fetchers). No install task, so no package-legitimacy checkpoint required. |
</threat_model>

<verification>
Phase-level checks (run from repo root):

1. **tsc identity gate (hard):** `cd frontend && npx tsc --noEmit 2>&1 | grep -c "error TS"` == `3`, AND `cd frontend && npx tsc --noEmit 2>&1 | grep "error TS" | grep -vE 'mockApi\.ts|IdeaInputPage\.tsx'` is EMPTY. This proves the only reds are the 3 known pre-existing ones (`mockApi.ts` ×2, `IdeaInputPage.tsx(738,9)`) and NO new file regressed. Verify by identity (filename filter), NOT by a `file:line` grep — tsc emits `file(line,col)`, so a literal `IdeaInputPage.tsx:738` filter under-matches (the B2 lesson).
2. **New specs green:** the two new spec files pass with real rendered-DOM assertions.
3. **Regression guard (hard, must_have):** all 9 pre-existing suites that render PreviewPanel or FilesTab pass unchanged — PreviewPanel.degraded, PreviewPanel.genericDeliverable, FilesTab, WorkflowHistory (×4: test/revise/family/genericReopen), DashboardLayout.catalogHome, DashboardLayout.waveMount.
4. **INV-3 by construction:** `git diff --name-only -- backend/` is empty for this plan's commits — FRONTEND-ONLY, zero engine/websocket/manifest/migration edits. Backend golden battery + semantic-event parity untouched.
5. **Reuse-first (UI-SPEC):** no net-new hex/radius/font-size/motion-curve introduced — every visual node cites an existing analog; the only hex literals in new code are the inherited `#1B2A4A`/`#f5f5f0`, no new ones.
</verification>

<success_criteria>
- Live "v{n} ▾" chip renders in the PreviewPanel header ONLY for on-screen content in a >=2-member revision family; absent otherwise (POR-5-D5).
- Chip dropdown lists v1..vN; selecting an older version loads it read-only via getWorkflow + shows the amber "Viewing v{k} (read-only) — Back to latest →" banner; "Back to latest →" restores live content (POR-5-D5).
- Chip label ticks v{n}→v{n+1} with a one-shot pulse when the family grows on revision-complete (POR-5-D5).
- A revision run's Files tab shows a collapsed "From v{n-1}" section that lazily loads the parent's files via getWorkflow(parentRunId) on expand; non-revision runs show no such section (POR-5-D6).
- a11y: chip aria-haspopup="listbox"/aria-expanded, dropdown role="listbox"/option/aria-selected, banner role="status", base-section toggle aria-expanded + aria-busy while fetching (POR §8).
- tsc: exactly the 3 known reds (identity-verified). New specs green. ALL 9 pre-existing PreviewPanel/FilesTab suites green (regression guard). ZERO backend edits (INV-3).
</success_criteria>

<output>
Create `.planning/quick/260702-vff-workstream-b3-live-version-chip-in-previ/260702-vff-SUMMARY.md` when done.
</output>
