---
phase: 260702-uos
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/components/history/WorkflowHistory.tsx
  - frontend/src/components/history/RevisionFamilyView.tsx
  - frontend/src/components/history/WorkflowHistory.family.test.tsx
autonomous: true
requirements: [POR-5-D3, POR-5-D4]

must_haves:
  truths:
    - "In the history list, a multi-run revision family renders as ONE root card with a 'v{N}' count pill and the latest member's status; a single-run (or legacy NULL-parent) family renders as a plain row with no pill/expander (zero regression)."
    - "Expanding a family reveals chronological version rows (v1..vN by created_at), each clickable to open that version, with '↳ revises v{n}' microcopy on revision members."
    - "Opening a run detail shows a version-timeline chip row (only when the family has >=2 members) with one chip per member, chronological, and the active chip matching the open version."
    - "Clicking a version chip loads that member into the SAME detail surface (Preview/Files/Thinking/Audit) via getWorkflow, cross-faded, with the active chip following the loaded version."
    - "A revision version shows a '↳ Revises v{n-1} — {instruction preview}' context line; the root version shows none."
    - "The version chip row is a keyboard-navigable radiogroup (role=radiogroup; chips role=radio with aria-checked)."
    - "Zero backend files changed; type-filter tabs still work with each family counted once under its base type."
  artifacts:
    - path: "frontend/src/components/history/RevisionFamilyView.tsx"
      provides: "groupRunsByFamily, FamilyGroupCard, VersionTimeline, extractRevisionInstructionPreview, statusDotClass"
      min_lines: 120
    - path: "frontend/src/components/history/WorkflowHistory.tsx"
      provides: "Grouped family list view + detail version-timeline wiring (getRunFamily fetch, handleSelectVersion, content cross-fade)"
      contains: "groupRunsByFamily"
    - path: "frontend/src/components/history/WorkflowHistory.family.test.tsx"
      provides: "5 behavior specs: grouping, single-member, timeline, version switch, a11y"
      contains: "role=\"radiogroup\""
  key_links:
    - from: "frontend/src/components/history/WorkflowHistory.tsx"
      to: "groupRunsByFamily(runs) -> FamilyGroupCard"
      via: "client-side grouping by rootRunId in the list view"
      pattern: "groupRunsByFamily"
    - from: "frontend/src/components/history/WorkflowHistory.tsx"
      to: "getRunFamily(token, selectedRun.rootRunId)"
      via: "detail-view useEffect keyed on rootRunId -> family state -> VersionTimeline"
      pattern: "getRunFamily\\("
    - from: "frontend/src/components/history/RevisionFamilyView.tsx (VersionTimeline chip)"
      to: "handleSelectVersion(memberId) -> getWorkflow(token, memberId)"
      via: "onSelectVersion callback loads the chosen member into the detail surface"
      pattern: "onSelectVersion"
    - from: "frontend/src/components/history/WorkflowHistory.tsx (detail content region)"
      to: "AnimatePresence mode=\"wait\" keyed on selectedRun.id"
      via: "cross-fade of all tabs on version switch"
      pattern: "AnimatePresence mode=\"wait\""
---

<objective>
Deliver POR §5 deliverables 3 + 4 — the first UI-heavy unit of revision families — FRONTEND-ONLY, strictly per `WORKSTREAM-B-UI-SPEC.md` (reuse-first: every new node inherits an existing analog with file:line). Consumes the shipped B1 foundation (`getRunFamily`, `WorkflowRun.parentRunId`/`rootRunId`, commit 9a8da4d0).

- **Deliverable 3 — History family grouping:** the flat run list in `WorkflowHistory.tsx` becomes grouped by `rootRunId`; one card per family root with a "v{N}" pill + the latest member's status, expandable into chronological version rows.
- **Deliverable 4 — Detail version timeline:** the run detail view gains a version-timeline chip row above the tab bar; clicking a chip loads that version into the same surface with a cross-fade.

Purpose: users see revisions as ONE workflow versioned, not a scatter of orphan rows — the core value of revision families in the surface they actually reach (history).
Output: `WorkflowHistory.tsx` (grouped list + timeline wiring), a new `RevisionFamilyView.tsx` (grouping helper + two presentational components + the preview shim), and `WorkflowHistory.family.test.tsx` (5 behavior specs).

SCOPE FENCE: `frontend/src/**` only. ZERO backend edits. NO deliverable-5 live PreviewPanel chip. NO deliverable-6 Files base-version section. NO full `parseRunInput` (Workstream C) — B2 uses a preview-only inline slice shim. NO new visual language / hex values (UI-SPEC mandates reuse).
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/WORKSTREAM-B-UI-SPEC.md
@.planning/REVISION-FAMILY-AND-RUN-INPUTS-PLAN.md
@.planning/quick/260702-u2o-workstream-b1-revision-family-fe-foundat/260702-u2o-SUMMARY.md
@CLAUDE.md

# The main file (grouping goes in the list view ~:866; timeline goes in the detail view above the tab bar ~:574; detail load via getWorkflow :154-171; the flat-row markup to clone :867-951; typeCounts :749-758)
@frontend/src/components/history/WorkflowHistory.tsx
# WorkflowRun.parentRunId/rootRunId + RunFamily/FamilyMember (B1); statusDotClass semantics live in WorkflowStatus
@frontend/src/types/index.ts
# getRunFamily :344-354 (raw RunFamily), getWorkflow :333-342
@frontend/src/lib/api.ts
# The tab-pill-group analog for the timeline chips :550-568; the cross-fade idiom :586-594
@frontend/src/components/preview/PreviewPanel.tsx
# STATUS_COLOR/STATUS_ICON semantic maps :55-73 (source of truth for status-dot colors)
@frontend/src/components/sidebar/Sidebar.tsx
# The test idiom to clone (mocks + makeRun fixture + real-render behavior asserts)
@frontend/src/components/history/WorkflowHistory.revise.test.tsx
</context>

<tasks>

<task type="auto">
  <name>Task 1: Deliverable 3 — History family grouping (list view)</name>
  <files>frontend/src/components/history/RevisionFamilyView.tsx (new), frontend/src/components/history/WorkflowHistory.tsx</files>
  <action>
Create `RevisionFamilyView.tsx` exporting three helpers + one component. All styling is INHERITED — cite the UI-SPEC analog, invent nothing:

1. `statusDotClass(status: WorkflowStatus): string` — maps status → a `w-1.5 h-1.5 rounded-full` bg class per UI-SPEC §0 "Semantic status colors" + `Sidebar.tsx:66-73` + dot shape `PrototypePreview.tsx:509,538`: completed → `bg-emerald-400`; cancelled/degraded → `bg-amber-400`; failed → `bg-gray-300`; running/revising → `bg-blue-400`. These are inherited semantic dots, NOT new literals.

2. `groupRunsByFamily(runs: WorkflowRun[]): FamilyGroup[]` — pure client-side grouping on the B1 `rootRunId` field (UI-SPEC Surface 1 Data; POR §2 D2 chronological index). Bucket runs into a Map keyed by `rootRunId`; sort each bucket's members by `createdAt` ASC (v1..vN chronological); pick `root` = the member whose `id === rootRunId`, else `members[0]` (legacy NULL-parent / earliest present); `latest` = `members[members.length-1]`. Return `{ rootRunId, root, members, latest }[]` ordered by `latest.createdAt` DESC so the newest family sits first (preserves today's newest-first list order → zero ordering regression). Define/export the `FamilyGroup` interface locally.

3. `FamilyGroupCard` — props `{ group: FamilyGroup; index: number; expanded: boolean; onToggle: () => void; onSelectRun: (run: WorkflowRun) => void; openMenuId: string | null; onToggleMenu: (runId: string, e?: React.MouseEvent) => void; onDeleteClick: (runId: string, e?: React.MouseEvent) => void }`. **(W1 fix — plan-checker):** the existing flat row `:871-951` includes the per-row overflow **menu + Delete** block `:920-947`, which references the `WorkflowHistory`-local `openMenuId`/`setOpenMenuId`/`handleDeleteClick`/`deleteConfirmId`. A verbatim clone into this new component would NOT compile (undefined identifiers) AND dropping the menu would REMOVE delete-from-history (regression vs truth #1). So the delete/menu affordance MUST be threaded through props: pass `openMenuId` (read), `onToggleMenu` (wraps `setOpenMenuId(openMenuId === id ? null : id)`), and `onDeleteClick` (wraps `handleDeleteClick`) down from `WorkflowHistory`; the menu popover markup + the `AnimatePresence` menu (`:925-944`) is reproduced in the card keyed on `openMenuId === <rowRunId>`. The delete-confirm modal itself stays in `WorkflowHistory` (unchanged); the card only opens the menu + fires `onDeleteClick`.
   - **Single-member family (`group.members.length === 1`):** render the EXACT existing flat row from `WorkflowHistory.tsx:871-951` (the `motion.div` flex row with `w-9 h-9 rounded-xl bg-gray-100` icon, title `text-[13px] font-semibold`, meta `text-[10px] text-gray-400` via `formatDate`, the status badge block `:902-918`, AND the overflow menu/Delete block `:920-947` wired through the props above), clicking the row → `onSelectRun(group.root)`. No pill, no expander (UI-SPEC Surface 1 "Single-member family" — visually indistinguishable from today, delete included).
   - **Multi-member family (>=2):** same row shape (incl. the threaded overflow menu on the root row), but beside the LATEST member's status badge add a "v{N}" count pill using the filter-count-pill class `text-[9px] font-semibold px-1 rounded bg-gray-200 text-gray-500` (`WorkflowHistory.tsx:806`, UI-SPEC Surface 1 analog line 70) with `aria-label="{N} versions"`. **(W3 fix — plan-checker):** derive `N` defensively as `group.members.length` (the count of family members PRESENT in the ≤100-run `getWorkflows` window) and add a comment: "// v{N} counts window-present members — a summary; the detail VersionTimeline (from /family) is the authoritative full-family count. They coincide for recent clustered families; a family with members beyond the fetch window shows fewer here by design (POR §11 large-family edge case)." Show the LATEST member's status badge (task spec: "the latest member's status dot"). Add a chevron toggle `<button>` with `aria-expanded={expanded}` and `aria-label={expanded ? "Collapse versions" : "Show versions"}`; **(W2 fix — plan-checker):** rotate the chevron with the CONTROLLED-state class `` `h-3.5 w-3.5 text-gray-400 transition-transform ${expanded ? "rotate-90" : ""}` `` (NOT `group-open:rotate-90` — that Tailwind variant only fires inside a native `<details open class="group">`, never on a controlled `aria-expanded` button; the UI-SPEC offers this controlled variant at line 79/187). The toggle calls `onToggle`; clicking the card BODY → `onSelectRun(group.latest)` (UI-SPEC Surface 1 Interaction: chevron toggles, body opens latest). When `expanded`, render indented child rows (`pl-8` per `AgentThinkingTab.tsx:119`, UI-SPEC analog line 233) for each member v1..vN: a v-chip ("v{i+1}", count-pill style), title + `formatDate(member.createdAt)`, a status dot (`statusDotClass`), and — for members with a non-null `parentRunId` — a "↳ revises v{n}" span in `text-[10px] text-gray-400` (`AgentThinkingTab.tsx:151-153`, UI-SPEC analog line 234) where n = the 1-based index of the member whose `id === member.parentRunId` in `group.members` (fallback: the current index, i.e. the previous sibling, if the parent is not present in the list). Child row `onClick` → `onSelectRun(member)`.

In `WorkflowHistory.tsx` LIST VIEW:
   - Import `groupRunsByFamily`, `FamilyGroupCard` (and `FamilyGroup`) from `./RevisionFamilyView`.
   - Extract today's inline filter predicate (`WorkflowHistory.tsx:194-204`) into a reusable `matchesFilter(run)` (same normalize-then-match logic — od_prototype→prototype, od_ppt→ppt, strip `_revision`; search on title). Keep the existing `_revision`→base normalization untouched.
   - Add `expandedFamilies` state (`useState<Set<string>>(new Set())`) keyed by `rootRunId`; a `toggleFamily(rootRunId)` helper flips membership.
   - Replace the `filteredRuns.map(...)` block (`:867-953`) with `groupRunsByFamily(runs).filter(g => g.members.some(matchesFilter)).map((group, idx) => <FamilyGroupCard key={group.rootRunId} group={group} index={idx} expanded={expandedFamilies.has(group.rootRunId)} onToggle={() => toggleFamily(group.rootRunId)} onSelectRun={handleSelectRun} openMenuId={openMenuId} onToggleMenu={(id, e) => { e?.stopPropagation(); setOpenMenuId(openMenuId === id ? null : id); }} onDeleteClick={handleDeleteClick} />)` (UI-SPEC Surface 1: filter operates on the family root, match if ANY member matches, applied post-grouping). **(W1 fix)** the `openMenuId`/`setOpenMenuId` state + `handleDeleteClick` already exist in `WorkflowHistory` (:132-ish menu state, :169 handleDeleteClick) — thread them so the existing delete UX survives the extraction. Change the empty-state guard from `filteredRuns.length === 0` to the grouped/filtered families being empty.
   - Update `typeCounts` (`:749-758`) to count FAMILIES once per base type, not per run (task spec: "a family should count once under its base type"): iterate the grouped families, normalize the family root's type to its base, increment; `all` = number of families. Keep the tab rendering (`:790-812`), search (`:778-787`), skeleton (`:817-859`) and empty state (`:860-864`) blocks otherwise unchanged.

Do NOT touch the detail view in this task. NO backend files.
  </action>
  <verify>
    <automated>cd frontend && test "$(npx tsc --noEmit 2>&1 | grep 'error TS' | grep -vE 'mockApi.ts|IdeaInputPage.tsx:738' | wc -l | tr -d ' ')" = "0"</automated>
    Behavior is asserted by the specs authored in Task 3 (grouping + single-member). This task's automated gate is: `npx tsc --noEmit` introduces ZERO new errors (only the 3 known pre-existing reds in mockApi.ts ×2 + IdeaInputPage.tsx:738 remain).
  </verify>
  <done>`RevisionFamilyView.tsx` exports `groupRunsByFamily`, `FamilyGroupCard`, `statusDotClass`. The list view renders one `FamilyGroupCard` per `rootRunId` family: single-member families are byte-identical to today's flat row; multi-member families show a "v{N}" pill + chevron and expand into chronological version rows with "↳ revises v{n}" microcopy. typeCounts count families once per base type. tsc has zero new errors. No backend file changed.</done>
</task>

<task type="auto">
  <name>Task 2: Deliverable 4 — Detail version timeline (chips + switch + cross-fade)</name>
  <files>frontend/src/components/history/RevisionFamilyView.tsx, frontend/src/components/history/WorkflowHistory.tsx</files>
  <action>
Add to `RevisionFamilyView.tsx`:

1. `extractRevisionInstructionPreview(input: string): string` — a PREVIEW-ONLY inline shim (UI-SPEC "Revision-instruction display" micro-contract). Add a comment: "// B2 preview-only shim — Workstream C (§6.1) replaces this call site with parseRunInput(input).revisionInstruction. Do NOT expand into a full marker-family parser here (INV-12: one lib in C, not a second copy in B)." Logic: if `input` contains the marker `=== REVISION REQUEST ===`, take the substring after it up to the next line beginning with `===` (or end-of-string); else use the whole `input`. From that slice take the first non-empty line that is NOT itself a `=== … ===` marker, trim it, and if it exceeds 60 chars return `slice(0, 60) + "…"`. Return `""` when nothing usable.

2. `VersionTimeline` — props `{ family: RunFamily | null; activeRunId: string; activeInput: string; onSelectVersion: (memberId: string) => void }`. Render `null` when `family` is null OR `family.members.length < 2` (UI-SPEC Surface 2 "empty (single-member) → render NO chips row"; same "hide when not a family" rule as the list). Otherwise:
   - **Chips row container:** `flex items-center gap-1 px-5 py-2 border-b border-gray-100 bg-white` with `role="radiogroup"` and `aria-label="Workflow versions"` (mirrors the tab-bar container `WorkflowHistory.tsx:574` per UI-SPEC Surface 2 "chips row" layout).
   - Members ordered by `revision_index` ASC. Each chip is a `<button role="radio">` with `aria-checked={member.id === activeRunId}`, `aria-label={`Version ${i+1}${member.parent_run_id ? `, revises version ${i}` : ""}, ${member.status}`}`, roving `tabIndex={member.id === activeRunId ? 0 : -1}`, class `text-[11px] font-medium px-3 py-1.5 rounded-md` (detail-tab button shape `WorkflowHistory.tsx:580`); active = `bg-[#1B2A4A] text-white` (accent fill `WorkflowHistory.tsx:801`, UI-SPEC Surface 2 "active version = filled"); sibling = ghost `text-gray-500 hover:text-gray-700` (`WorkflowHistory.tsx:583` / `PreviewPanel.tsx:561`). Each chip carries a `statusDotClass(member.status)` dot marked `aria-hidden` (status is in the aria-label). `onClick` → `onSelectVersion(member.id)`.
   - **Keyboard (UI-SPEC Surface 2 A11y — MANDATORY):** `onKeyDown` on the group: Arrow Left/Up → previous member, Arrow Right/Down → next member (clamp at ends); Enter/Space activates the focused member; moving with arrows both moves focus (roving tabindex) and activates via `onSelectVersion`. **Managed focus:** hold a `chipRefs` array of button refs + a `userSwitched` ref flag; in a `useEffect` keyed on `activeRunId`, if `userSwitched.current` is set, focus the active chip so keyboard users are not stranded (do NOT steal focus on initial mount).
   - **Context line:** find the active member (`family.members` where `id === activeRunId`); if it has a non-null `parent_run_id`, render beneath the chips a single-line `↳ Revises v{k-1} — '{extractRevisionInstructionPreview(activeInput)}'` in `text-[10px] text-gray-400 truncate` (`AgentThinkingTab.tsx:151-153`), where k = the active member's 1-based position. Root version (null parent) → no context line.

In `WorkflowHistory.tsx` DETAIL VIEW:
   - Import `getRunFamily` from `@/lib/api` and `VersionTimeline` from `./RevisionFamilyView`; import `RunFamily` type.
   - Add top-level (above the `if (selectedRun)` early return `:290`, with the other hooks — Rules of Hooks) `family`/`familyLoading` state and a cancellable `useEffect` keyed on `selectedRun?.rootRunId`: when `selectedRun` and a token exist, call `getRunFamily(token, selectedRun.rootRunId)` → `setFamily`; clear on unmount/change. Keying on the STABLE `rootRunId` (same for every member) means switching versions does NOT refetch the family.
   - Add `handleSelectVersion = useCallback(async (memberId) => {...})`: `setLoadingDetail(true)`; `getWorkflow(token, memberId)` → `setSelectedRun(full)` + `setSelectedOutput(full.output || null)`; do NOT reset `detailTab` (preserve the current tab so a version switch feels like one workflow, not navigation); `finally setLoadingDetail(false)`. (Mirrors the fetch half of `handleSelectRun` `:162-170` but keyed by id and tab-preserving.)
   - Insert `<VersionTimeline family={family} activeRunId={selectedRun.id} activeInput={selectedRun.input} onSelectVersion={handleSelectVersion} />` as a full-width strip directly ABOVE the tab-bar container `div` at `:574` (inside the main content column `:572`).
   - Wrap the detail CONTENT region so all tabs cross-fade on switch: inside the content `div` (`:627`), wrap the tab-content branch in `<AnimatePresence mode="wait">` + `<motion.div key={selectedRun.id} initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} transition={{duration:0.15}}>` (the exact `PreviewPanel.tsx:586-594` idiom, UI-SPEC Surface 2 "version-switch cross-fade") so Preview/Files/Thinking/Audit re-render together keyed on `selectedRun.id`. Keep the existing `loadingDetail` spinner branch (`:628-631`) as-is.

Do NOT touch the list view from Task 1. NO backend files. NO PreviewPanel live chip (deliverable 5). NO FilesTab base-version section (deliverable 6).
  </action>
  <verify>
    <automated>cd frontend && test "$(npx tsc --noEmit 2>&1 | grep 'error TS' | grep -vE 'mockApi.ts|IdeaInputPage.tsx:738' | wc -l | tr -d ' ')" = "0"</automated>
    Behavior is asserted by the specs authored in Task 3 (timeline render + version switch + a11y). This task's automated gate is: `npx tsc --noEmit` introduces ZERO new errors beyond the 3 known pre-existing reds.
  </verify>
  <done>Opening a run detail fetches its family via `getRunFamily(token, selectedRun.rootRunId)` and renders a `VersionTimeline` chip row above the tab bar ONLY when the family has >=2 members: chips are chronological, the active chip is `bg-[#1B2A4A] text-white` with `aria-checked`, siblings are ghost, each with a status dot. Clicking a sibling chip calls `handleSelectVersion` → `getWorkflow(token, memberId)` and cross-fades all tabs via `AnimatePresence mode="wait"`. A revision version shows the "↳ Revises v{n-1} — '{preview}'" line; the root shows none. The chip row is `role="radiogroup"` with Arrow-key nav + managed focus. tsc has zero new errors. No backend file changed.</done>
</task>

<task type="auto">
  <name>Task 3: vitest behavior specs (grouping / single / timeline / switch / a11y)</name>
  <files>frontend/src/components/history/WorkflowHistory.family.test.tsx (new)</files>
  <action>
Author `WorkflowHistory.family.test.tsx`, cloning the mock scaffold + `makeRun` fixture from `WorkflowHistory.revise.test.tsx` VERBATIM, then ADD `getRunFamily` to the `@/lib/api` mock (`getRunFamily: (t, id) => mockGetRunFamily(t, id)`) and declare `const mockGetRunFamily = vi.fn(...)`. Keep the existing preview-component mocks (PPTPreview/UserStoryPreview/PrototypePreview/MarkdownPreview/FilesTab) and the `motion/react` proxy mock (which strips motion props and renders `AnimatePresence` children directly — this makes the cross-fade content synchronously present). Assert against the REAL rendered DOM (behavior tests), never source-lock — WorkflowHistory renders fine in vitest (the B1 revise spec proves it).

Write 5 tests:

1. **Grouping** — `getWorkflows` resolves 4 runs: root `{id:"root", rootRunId:"root", parentRunId:null, createdAt:t0}`, rev1 `{id:"r1", rootRunId:"root", parentRunId:"root", type:"prototype_revision", createdAt:t1}`, rev2 `{id:"r2", rootRunId:"root", parentRunId:"r1", type:"prototype_revision", createdAt:t2}`, standalone `{id:"solo", rootRunId:"solo", parentRunId:null, createdAt:t3}`. Assert exactly ONE "v3" pill is rendered (`screen.getByText("v3")` or by `aria-label="3 versions"`) AND the standalone's title renders as a plain row (present, with no "v" pill of its own). Click the family's expander (`screen.getByLabelText("Show versions")`); assert 3 version rows appear and the microcopy `↳ revises v1` (rev1 revises root=v1) and `↳ revises v2` (rev2 revises rev1=v2) are present.

2. **Single-member family** — `getWorkflows` resolves `[standalone]` only. Assert the row title renders, `screen.queryByLabelText("Show versions")` is null, and no "v" count pill is present (plain-row, zero regression).

3. **Timeline render** — `getWorkflows` resolves a family (root + 2 revisions sharing rootRunId "root"); `getWorkflow` resolves the latest member with `input` containing `"=== REVISION REQUEST ===\nmake the header blue"`; `getRunFamily` resolves `{ root_id:"root", members:[{id:"root",revision_index:0,parent_run_id:null,...}, {id:"r1",revision_index:1,parent_run_id:"root",...}, {id:"r2",revision_index:2,parent_run_id:"r1",...}] }`. Open the family detail (click the card body → opens latest = v3). Assert 3 chips with `role="radio"` render in chronological order; the active chip (`aria-checked="true"`) corresponds to the loaded `selectedRun`; and the context line shows the extracted instruction text `make the header blue`.

4. **Version switch** — from the open detail of test 3, click the v1 sibling chip (the first `role="radio"`). **(I1 fix — plan-checker):** `mockGetWorkflow` MUST be keyed by id (e.g. `mockGetWorkflow.mockImplementation((t, id) => Promise.resolve(runsById[id]))`) so that clicking v1 resolves an object whose `id === v1id` — otherwise `activeRunId={selectedRun.id}` never re-matches the first chip and the assertion is vacuous. Assert `mockGetWorkflow` was called with the v1 member id, and (via `waitFor`) the active chip moves to v1 (`aria-checked="true"` now on the first chip, `"false"` on v3) — proving the `setSelectedRun` re-render path fired and the active chip follows the loaded version.

5. **A11y** — with a >=2-member family detail open, assert the chip row container has `role="radiogroup"` and every chip has `role="radio"` with an `aria-checked` attribute present.

Follow the revise-spec robustness lessons: use `fireEvent`/`waitFor` for state-driven re-renders (do NOT rely on `userEvent.type` through per-keystroke churn). Distinct `createdAt` timestamps so chronological ordering is deterministic.
  </action>
  <verify>
    <automated>cd frontend && npx vitest run src/components/history/WorkflowHistory.family.test.tsx</automated>
    All 5 specs green. Also confirm the tsc gate still holds: `npx tsc --noEmit` shows only the 3 known pre-existing reds.
  </verify>
  <done>`WorkflowHistory.family.test.tsx` exists with 5 passing specs covering grouping (v3 pill + plain standalone + expand microcopy), single-member plain-row, timeline chips (3 chips, active matches selectedRun, instruction preview shown), version switch (getWorkflow called with member id, active chip follows), and a11y (radiogroup + radio/aria-checked). `npx vitest run` on the file is fully green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| API → React render | `getRunFamily` / `getWorkflow` / `getWorkflows` responses (titles, statuses, instruction input) are rendered in the history UI. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-uos-01 | Information disclosure | `getRunFamily(token, rootRunId)` family payload | mitigate | Fetcher is Bearer-authed (`api.ts:346-354`); the `/family` endpoint was IDOR-hardened + owner-scoped in Workstream A / B1 — B2 adds no new ingress, only consumes the existing authed fetcher. |
| T-uos-02 | Tampering (XSS) | Instruction-preview + member titles rendered in chips/rows | mitigate | Rendered as plain React text nodes (auto-escaped); `extractRevisionInstructionPreview` returns a `slice(0,60)` string, never HTML. NO `dangerouslySetInnerHTML` introduced. |
| T-uos-SC | Tampering | npm installs | accept | No package installs — frontend-only change reusing existing deps (motion/react, lucide-react, existing fetchers). Zero new dependencies → supply-chain surface unchanged. |
</threat_model>

<verification>
- `cd frontend && npx tsc --noEmit` → only the 3 KNOWN pre-existing reds (mockApi.ts:95,96 TS2352; IdeaInputPage.tsx:738 TS17001) in untouched files; ZERO new errors introduced by this plan.
- `cd frontend && npx vitest run src/components/history/WorkflowHistory.family.test.tsx` → 5 specs green.
- `git status backend/` empty — INV-3 by construction: this is a FRONTEND-ONLY change (no engine/websocket/manifest/migration edit), so the backend characterization goldens + semantic-event parity are untouched.
- Known-red FE baseline NOT chased — run only the touched/new specs + tsc, per the offline-suite discipline.
</verification>

<success_criteria>
- Deliverable 3: history list groups runs by `rootRunId`; multi-member families render one root card with a "v{N}" pill + latest status, expandable into chronological version rows with "↳ revises v{n}" microcopy; single-member families are visually identical to today's flat row (zero regression); type-filter tabs count each family once per base type.
- Deliverable 4: run detail shows a version-timeline chip row (only when family >=2 members) above the tab bar; clicking a chip loads that version via `getWorkflow` into the same detail surface with an `AnimatePresence mode="wait"` cross-fade; the active chip follows the loaded version; revision versions show a "↳ Revises v{n-1} — '{preview}'" line; the chip row is a keyboard-navigable radiogroup with managed focus.
- Every visual node inherits an existing analog per `WORKSTREAM-B-UI-SPEC.md` — no new hex values, radii, font sizes, or motion curves.
- Preview instruction text uses the B2 inline shim (comment flags the Workstream C `parseRunInput` hand-off); no second parser authored.
- ZERO backend edits; tsc introduces no new errors; the 5 new specs are green.
</success_criteria>

<output>
Create `.planning/quick/260702-uos-workstream-b2-revision-family-history-gr/260702-uos-SUMMARY.md` when done.
</output>
