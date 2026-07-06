---
phase: 260702-wag
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/components/preview/LiveVersionChip.tsx
  - frontend/src/components/history/RevisionFamilyView.tsx
  - frontend/src/components/history/WorkflowHistory.tsx
  - frontend/src/components/preview/PreviewPanel.tsx
  - frontend/src/components/preview/PreviewPanel.versionChip.test.tsx
  - frontend/src/components/history/WorkflowHistory.family.test.tsx
autonomous: true
requirements: [UIREV-B-A11Y-LISTBOX, UIREV-B-A11Y-CHILDROWS, UIREV-B-CONSISTENCY-VNUM, UIREV-B-MICROCOPY, UIREV-B-OBSERVABILITY]

must_haves:
  truths:
    - "UIREV-B-A11Y-LISTBOX (BLOCK, POR §8): In the live PreviewPanel version chip, OPENING the dropdown moves keyboard focus into the listbox so a keyboard-only user can operate it — ArrowUp/ArrowDown move the highlighted option, Enter/Space selects the highlighted version (loads it read-only via getWorkflow), and Escape closes the dropdown AND returns focus to the chip button. The existing pointer path (click chip, click option, mouseenter-to-highlight) and every aria attribute (chip aria-haspopup/aria-expanded, role=listbox, role=option + aria-selected) are preserved. No new styling is introduced."
    - "UIREV-B-A11Y-CHILDROWS (FLAG, POR §8): In the history family card, each EXPANDED child version row is a native <button type=\"button\"> (keyboard-focusable + Enter/Space-activatable) carrying aria-label=\"Version {n}, {status}\", and pressing Enter/Space (or click) opens that version via onSelectRun(member). The inherited row styling is visually unchanged. The ROOT family-card rows remain <div onClick> untouched (explicitly out of scope per the audit's zero-regression scoping)."
    - "UIREV-B-CONSISTENCY-VNUM (FLAG): groupRunsByFamily orders family members by (createdAt ASC, id ASC) — the SAME deterministic tie-break the Workstream-A /family endpoint uses — so the history list card and the detail timeline / live chip derive identical member orderings (identical v-numbers) for all present members, with an inline comment citing the backend contract (revision_index == created_at-ASC rank, tie-broken by id) AND the documented windowed-count caveat (POR §11 / B2 W3)."
    - "UIREV-B-MICROCOPY (FLAG): the revision-relationship annotation reads ONE canonical lowercase form on BOTH surfaces — list \"↳ revises v{n}\" and timeline \"↳ revises v{n-1} — '{preview}'\" (the timeline's previously-capitalized \"Revises\" is now lowercase)."
    - "UIREV-B-OBSERVABILITY (FLAG, LOW): a genuine /family fetch failure (WorkflowHistory family effect + version-fetch catch) and a read-only version fetch failure (PreviewPanel handleSelectVersion catch) each emit a one-line console.warn tagged \"[revision-family]\" for dev visibility, WITHOUT changing the graceful-degrade behavior (the version affordance still simply hides) and WITHOUT adding any UI (no error banner)."
    - "REGRESSION GUARD: the FULL named sibling suite set is green — PreviewPanel.versionChip, WorkflowHistory.family, PreviewPanel.degraded, PreviewPanel.genericDeliverable, FilesTab.test, FilesTab.baseVersion, WorkflowHistory.{test,revise,genericReopen}, DashboardLayout.{catalogHome,waveMount} — a UI-polish edit to LiveVersionChip/RevisionFamilyView must not regress any sibling that renders these components (B2/B3 regression-guard discipline)."
    - "TSC IDENTITY GATE: `cd frontend && npx tsc --noEmit` yields COUNT==3 total `error TS` lines AND 0 after filtering out the known mockApi/IdeaInputPage baseline (GATE_OK) — the edits introduce zero new type errors. INV-3 holds by construction (zero backend edits)."
  artifacts:
    - path: "frontend/src/components/preview/LiveVersionChip.tsx"
      provides: "Keyboard-reachable version listbox: roving-tabIndex role=option buttons with per-option refs, active option focused on open, ArrowUp/Down move highlight+focus, Enter/Space select, Escape closes+returns focus to chip (bubbling onKeyDown on the listbox)"
      contains: "role=\"option\""
      min_lines: 60
    - path: "frontend/src/components/history/RevisionFamilyView.tsx"
      provides: "Child version rows as <button type=button> with aria-label; groupRunsByFamily (createdAt ASC, id ASC) deterministic sort + backend-contract comment; timeline lowercase 'revises' microcopy"
      contains: "type=\"button\""
      min_lines: 60
    - path: "frontend/src/components/history/WorkflowHistory.tsx"
      provides: "console.warn('[revision-family] ...') in the family-fetch catch + the version-fetch catch (graceful-degrade behavior unchanged)"
      contains: "[revision-family]"
    - path: "frontend/src/components/preview/PreviewPanel.tsx"
      provides: "console.warn('[revision-family] ...') in the read-only handleSelectVersion catch (still falls back to setViewingVersion(null))"
      contains: "[revision-family]"
    - path: "frontend/src/components/preview/PreviewPanel.versionChip.test.tsx"
      provides: "Added real-DOM keyboard-nav spec: open chip, focus enters listbox, ArrowDown moves highlight, Enter selects → getWorkflow called, Escape closes + focus returns to chip"
      min_lines: 140
    - path: "frontend/src/components/history/WorkflowHistory.family.test.tsx"
      provides: "Added child-row keyboard spec (expand family, child row is a button with aria-label, Enter opens via onSelectRun) + unified lowercase 'revises' timeline microcopy assertion"
      min_lines: 220
  key_links:
    - from: "LiveVersionChip.tsx active role=option button (focused on open)"
      to: "the listbox div onKeyDown={handleListKeyDown}"
      via: "keydown bubbling from the focused option up to the listbox container (WAI-ARIA listbox idiom, mirrors VersionTimeline radiogroup)"
      pattern: "onKeyDown=\\{handleListKeyDown\\}"
    - from: "RevisionFamilyView.tsx child version row button onClick / Enter"
      to: "onSelectRun(member)"
      via: "native button activation"
      pattern: "onSelectRun\\(member\\)"
    - from: "groupRunsByFamily members sort"
      to: "the /family endpoint ordering (created_at ASC, id ASC)"
      via: "identical (createdAt, id) comparator so list v-numbers == timeline revision_index order"
      pattern: "createdAt.*id"
---

<objective>
Apply the Workstream-B closing UI-review findings (`.planning/WORKSTREAM-B-UI-REVIEW.md`, 21/24) — fix the 1 BLOCK + the 4 actionable FLAGs. This is the a11y sign-off gate for Workstream B (precedent: quick task 260615-dzk "Apply Phase 22 UI-REVIEW findings"). FRONTEND-ONLY polish, reuse-first: the fixes mirror the CORRECT patterns already in the codebase — the auditor named VersionTimeline's `role="radiogroup"` (RevisionFamilyView.tsx:384-478) as the reference implementation for the a11y fixes.

Purpose: unblock the a11y sign-off (keyboard-operability against the plan §8 mandate) and remove the cross-surface version-numbering / microcopy inconsistencies the audit flagged — with ZERO behavior change beyond a11y + numbering determinism, ZERO backend, and ZERO net-new visual language.

Output: keyboard-operable live version listbox + history child rows; deterministic member ordering; unified microcopy; observable fetch failures; extended (not parallel) specs; both hard gates (tsc identity + full sibling-suite regression) green.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.planning/WORKSTREAM-B-UI-REVIEW.md
@.planning/WORKSTREAM-B-UI-SPEC.md

# The reference a11y pattern the fixes must mirror (auditor-praised):
#   VersionTimeline in RevisionFamilyView.tsx:384-478 — role=radiogroup (:442),
#   per-chip refs (:452), roving tabIndex (:456), Arrow/Enter/Space handler on the
#   container (:421-433), managed focus-after-switch (:394-411).
@frontend/src/components/history/RevisionFamilyView.tsx
@frontend/src/components/preview/LiveVersionChip.tsx
@frontend/src/components/history/WorkflowHistory.tsx
@frontend/src/components/preview/PreviewPanel.tsx
</context>

<tasks>

<task type="auto">
  <name>Task 1: A11y keyboard-operability — LiveVersionChip listbox (FIX 1 / BLOCK) + RevisionFamilyView child rows (FIX 2 / FLAG)</name>
  <files>frontend/src/components/preview/LiveVersionChip.tsx, frontend/src/components/history/RevisionFamilyView.tsx</files>
  <action>
FIX 1 — LiveVersionChip.tsx (BLOCK, POR §8). Today `handleListKeyDown` (:95-110) is bound to the `role="listbox"` `motion.div` (:148) but nothing focuses into it, so Arrow/Enter/Escape are inert. Make the keyboard path REACHABLE by mirroring VersionTimeline's roving-focus idiom on the PLAIN `role="option"` `<button>` elements (NOT the motion.div — a ref on the motion component would not attach under the tests' motion mock, whereas plain `<button>` refs do, exactly like VersionTimeline's chipRefs). Approach (b), roving-tabIndex:
  1. Add an option-refs array `const optionRefs = useRef<(HTMLButtonElement | null)[]>([])` (mirror RevisionFamilyView.tsx:392 `chipRefs`).
  2. On each `role="option"` button (:155-172) attach `ref={(el) => { optionRefs.current[i] = el; }}` and roving `tabIndex={i === highlightIdx ? 0 : -1}` so exactly the highlighted option is tab-reachable (mirror :452,:456). Keep the existing key, role="option", aria-selected, onMouseEnter (highlight), onClick (select), and all classNames unchanged.
  3. KEEP `onKeyDown={handleListKeyDown}` on the listbox `motion.div` — a keydown on the focused option BUBBLES up to the container handler (the WAI-ARIA listbox idiom; same reason VersionTimeline's onKeyDown lives on the radiogroup container).
  4. Focus the active option WHEN THE DROPDOWN OPENS: in the existing `useEffect` keyed on `[open, activeIdx]` (:77-79) that already sets highlightIdx, after computing the initial index also call `optionRefs.current[<that index>]?.focus()` so keydown lands on a focusable option. Focus only on open (do not steal focus on unrelated re-renders) — the active version only changes via select(), which closes the dropdown, so keying the focus on `open` is safe and matches VersionTimeline's "focus only after a user action" intent.
  5. In `handleListKeyDown` (:99-104) ArrowDown/ArrowUp: compute the NEXT index explicitly (`Math.min(highlightIdx+1, members.length-1)` / `Math.max(highlightIdx-1, 0)`), pass it to `setHighlightIdx`, AND `optionRefs.current[next]?.focus()` so roving tabIndex + focus + highlight stay in lockstep. Enter/Space (:105-109) already selects `members[highlightIdx]` — keep. Escape (:96-98) already calls `close()` which returns focus to `chipRef` (:84-87) — keep exactly.
Preserve every aria attribute (chip aria-haspopup="listbox"/aria-expanded/aria-label :120-122, listbox role/aria-label :146-147, option role/aria-selected :157-158) and the outside-click catcher (:139). Introduce NO new className / hex / radius / motion values.

FIX 2 — RevisionFamilyView.tsx (FLAG, POR §8). The expanded child version rows (:328-342) are plain `<div onClick>` — not keyboard reachable. Convert EACH child row `<div>` to a native `<button type="button">`: keep `key`, keep `onClick={() => onSelectRun(member)}`, keep the EXACT existing className string but append `w-full text-left` so the button reproduces the full-width flex row (no visual change), and add `aria-label={\`Version ${i + 1}, ${member.status}\`}`. The inner spans (v-pill, status dot, title, date, "↳ revises v{n}") are unchanged. Do NOT touch the ROOT family-card rows (:233-238, :277-282) — the audit explicitly scoped those out (pre-existing history-row pattern, separate future sweep). Native buttons are Enter/Space-activatable for free — no manual key handler needed.
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend && grep -q 'optionRefs' src/components/preview/LiveVersionChip.tsx && grep -q 'type="button"' src/components/history/RevisionFamilyView.tsx && grep -q 'aria-label={`Version ' src/components/history/RevisionFamilyView.tsx && echo A11Y_WIRED</automated>
  </verify>
  <done>LiveVersionChip options carry per-option refs + roving tabIndex, the active option is focused on open, Arrow moves highlight+focus, Enter selects, Escape closes+returns focus to the chip; every child version row in RevisionFamilyView is a native button with aria-label="Version {n}, {status}" that opens via onSelectRun; root family-card rows unchanged; no new styling. grep gate prints A11Y_WIRED.</done>
</task>

<task type="auto">
  <name>Task 2: Consistency + microcopy + observability — deterministic member sort (FIX 3), unified lowercase "revises" (FIX 4), console.warn on swallowed fetch failures (FIX 5)</name>
  <files>frontend/src/components/history/RevisionFamilyView.tsx, frontend/src/components/history/WorkflowHistory.tsx, frontend/src/components/preview/PreviewPanel.tsx</files>
  <action>
FIX 3 — RevisionFamilyView.tsx groupRunsByFamily (:113-117). Today members sort by `createdAt` ASC only. Add the SAME deterministic tie-break the Workstream-A /family endpoint uses — sort by `(createdAt ASC, id ASC)`: when the two createdAt values are equal, break the tie by `a.id.localeCompare(b.id)` (string id compare). This makes the list ordering PROVABLY identical to the timeline/chip `revision_index` ordering for all present members (the backend defines revision_index as created_at-ASC rank, id-tie-broken). Add an inline comment on the comparator citing: (1) the backend contract — "revision_index == created_at-ASC rank, tie-broken by id (Workstream A /family orders by created_at ASC, id ASC) → list and timeline derive identical member orderings for present members"; and (2) the windowed-count caveat — "a family with members OUTSIDE the <=100-run getWorkflows list window shows fewer versions in this list card than the authoritative detail timeline (POR §11 / B2 W3), by design". Do NOT fetch /family per list card (N fetches — rejected). The `root`/`latest`/newest-family-first logic below (:120-128) is unchanged.

FIX 4 — RevisionFamilyView.tsx VersionTimeline context line (:472-473). Unify capitalization to the canonical LOWERCASE form: change the timeline string from "↳ Revises v{currentIdx} — '{preview}'" to "↳ revises v{currentIdx} — '{preview}'" (lowercase "revises"). The list child-row string (:340) is already lowercase "↳ revises v{revisesN}" — leave it. Result: both surfaces read "↳ revises v{n}". (No test currently asserts the capitalized "Revises" — the assertion is added in Task 3.)

FIX 5 — observability (LOW, keep graceful degradation, add NO UI). Add a single tagged console.warn at each swallowed fetch-failure site, preserving the existing degrade behavior:
  1. WorkflowHistory.tsx family effect catch (:193): the `.catch(() => { if (!cancelled) setFamily(null); })` — take the error arg and add `console.warn("[revision-family] family fetch failed", err)` BEFORE `setFamily(null)` (still inside the `if (!cancelled)` guard).
  2. WorkflowHistory.tsx handleSelectVersion catch (:209): the empty `catch {}` around getWorkflow — capture the error and `console.warn("[revision-family] version fetch failed", err)` inside it (the surrounding setLoadingDetail(false) finally stays).
  3. PreviewPanel.tsx handleSelectVersion read-only catch (:426-429): before/at `setViewingVersion(null)` add `console.warn("[revision-family] read-only version fetch failed", err)` (capture the caught error; the setViewingVersion(null) fallback stays). Do NOT add an error banner or any UI — just the one-line logs.
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend && grep -q 'localeCompare' src/components/history/RevisionFamilyView.tsx && [ "$(grep -c 'revises v' src/components/history/RevisionFamilyView.tsx)" -ge 2 ] && [ "$(grep -v '^//' src/components/history/RevisionFamilyView.tsx | grep -c 'Revises v')" -eq 0 ] && [ "$(grep -c '\[revision-family\]' src/components/history/WorkflowHistory.tsx)" -ge 2 ] && grep -q '\[revision-family\]' src/components/preview/PreviewPanel.tsx && echo CONSISTENCY_OK</automated>
  </verify>
  <done>groupRunsByFamily sorts by (createdAt, id) with a comment citing the backend contract + windowed-count caveat; both list and timeline read lowercase "↳ revises v{n}" (zero "Revises v" remaining); WorkflowHistory has >=2 "[revision-family]" console.warn sites and PreviewPanel has one; graceful-degrade behavior and all aria unchanged; no UI added. grep gate prints CONSISTENCY_OK.</done>
</task>

<task type="auto">
  <name>Task 3: Extend existing specs (real rendered-DOM, fireEvent.keyDown) + run BOTH hard gates</name>
  <files>frontend/src/components/preview/PreviewPanel.versionChip.test.tsx, frontend/src/components/history/WorkflowHistory.family.test.tsx</files>
  <action>
EXTEND the two existing specs — do NOT create parallel files. Real rendered-DOM behavior (fireEvent.keyDown), never source-lock. The existing motion mock renders `motion.div` as a real `<div>` with tabIndex/onKeyDown passed through, and renders `<button>` children with working refs, so focus + keydown are drivable in jsdom.

PreviewPanel.versionChip.test.tsx — add ONE keyboard-nav `it(...)` inside the existing describe (reuse family3 / M / mockGetWorkflow):
  - Render `<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={family3} liveRunId="r2" />` with `mockGetWorkflow.mockImplementation((_t, id) => Promise.resolve({ id, output: \`<html>${id}</html>\` }))`.
  - Open the dropdown: `fireEvent.click(screen.getByLabelText(/Current version v3/))`.
  - Assert focus ENTERED the listbox: query `screen.getByRole("listbox")` and assert `screen.getByRole("listbox").contains(document.activeElement)` is true (an option button is focused).
  - Arrow moves the highlight: `fireEvent.keyDown(document.activeElement!, { key: "ArrowUp" })` then assert focus moved to another option still within the listbox.
  - Enter selects: `fireEvent.keyDown(document.activeElement!, { key: "Enter" })` then `await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalled())` (an older version was loaded read-only).
  - Escape closes + returns focus to chip: re-open, `fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" })`, then `await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull())` and assert `document.activeElement === screen.getByLabelText(/Current version/)` (the chip button).

WorkflowHistory.family.test.tsx — (a) add a child-row keyboard `it(...)` in the "history grouping (D3)" describe: render with `familyRuns()` + `mockGetRunFamily.mockResolvedValue(familyPayload())`, expand via `fireEvent.click(screen.getByLabelText("Show versions"))`, then assert a child row is a BUTTON with the aria-label — `const row = await screen.findByRole("button", { name: /Version 2, completed/ })` (v2 = "Rev one") — and that activating it opens the version: `fireEvent.click(row)` (or `fireEvent.keyDown(row, { key: "Enter" })`) fires the detail open path — `await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalled())` (onSelectRun → handleSelectRun fetches the member). (b) Update the timeline microcopy assertion: in the "detail version timeline (D4)" describe's instruction-preview test, add an assertion that the context line is the lowercase unified form — `expect(screen.getByText(/↳ revises v/)).toBeInTheDocument()` (and NOT the capitalized "Revises"). The existing list-row assertions at :149-150 already assert lowercase "↳ revises v1/v2" — keep them.

Then run BOTH hard gates below.
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend && npx vitest run src/components/preview/PreviewPanel.versionChip.test.tsx src/components/history/WorkflowHistory.family.test.tsx src/components/preview/PreviewPanel.degraded.test.tsx src/components/preview/PreviewPanel.genericDeliverable.test.tsx src/components/results/FilesTab.test.tsx src/components/results/FilesTab.baseVersion.test.tsx src/components/history/WorkflowHistory.test.tsx src/components/history/WorkflowHistory.revise.test.tsx src/components/history/WorkflowHistory.genericReopen.test.tsx src/components/layout/DashboardLayout.catalogHome.test.tsx src/components/layout/DashboardLayout.waveMount.test.tsx</automated>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend && OUT=$(npx tsc --noEmit 2>&1 || true); COUNT=$(printf '%s\n' "$OUT" | grep -c 'error TS'); FILT=$(printf '%s\n' "$OUT" | grep 'error TS' | grep -vE 'mockApi|IdeaInputPage' | grep -c 'error TS'); [ "$COUNT" -eq 3 ] && [ "$FILT" -eq 0 ] && echo GATE_OK || echo "GATE_FAIL count=$COUNT filt=$FILT"</automated>
  </verify>
  <done>Both existing specs are EXTENDED (no parallel files) with real fireEvent.keyDown behavior: the version-chip spec drives open→focus-in-listbox→ArrowUp→Enter(getWorkflow)→Escape(close+focus-to-chip); the family spec asserts a child version row is a button named "Version 2, completed" that opens on activation, and asserts the unified lowercase "↳ revises v" timeline microcopy. The FULL 11-suite regression set is green and the tsc identity gate prints GATE_OK (COUNT==3, FILT==0).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| (none new) | FRONTEND-ONLY a11y/consistency polish on already-rendered version data. No new input crosses any trust boundary: no new network calls, no new user-supplied data path, no new deserialization. The read-only fetch and /family fetch already existed and are unchanged (only a console.warn added). Zero backend edits. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-wag-01 | Information disclosure | new console.warn("[revision-family] …") log sites | accept | Logs a static tag + the caught fetch error object (already client-visible in the failing network request); no secrets/PII/tokens are logged. Dev-observability only, matches the audit's "note for observability" guidance. |
| T-wag-02 | Tampering | version aria-label / child-row button label built from member.status / member.title | accept | Rendered as React text children / attribute values (auto-escaped) exactly as the pre-existing rows already render member.title; no dangerouslySetInnerHTML, no new sink introduced. |
| T-wag-SC | Tampering | npm/pip/cargo installs | accept | No package installs in this plan — zero new dependencies (uses existing React/testing-library/vitest already in package.json). No Package Legitimacy Gate required. |
</threat_model>

<verification>
Phase-level checks (run from `frontend/`):
1. A11y wiring present (Task 1 grep gate): `A11Y_WIRED`.
2. Consistency/microcopy/observability wiring present (Task 2 grep gate): `CONSISTENCY_OK`.
3. Full 11-suite regression set green: `npx vitest run` over PreviewPanel.versionChip, WorkflowHistory.family, PreviewPanel.degraded, PreviewPanel.genericDeliverable, FilesTab.test, FilesTab.baseVersion, WorkflowHistory.{test,revise,genericReopen}, DashboardLayout.{catalogHome,waveMount} — all pass.
4. tsc identity gate: `GATE_OK` (COUNT==3 total `error TS`, 0 after filtering mockApi/IdeaInputPage baseline).
5. INV-3 by construction: `git diff --name-only` touches only `frontend/src/**` (zero backend files).
</verification>

<success_criteria>
- FIX 1 (BLOCK): the live version listbox is fully keyboard-operable — focus enters on open, Arrow moves highlight+focus, Enter/Space selects, Escape closes + returns focus to the chip; pointer path + all aria preserved; no new styling.
- FIX 2 (FLAG): every history child version row is a native button with aria-label="Version {n}, {status}", keyboard-activatable; root rows untouched; visually unchanged.
- FIX 3 (FLAG): groupRunsByFamily sorts by (createdAt ASC, id ASC) with a comment citing the backend contract + windowed-count caveat; list and timeline v-numbers coincide for present members.
- FIX 4 (FLAG): both surfaces read lowercase "↳ revises v{n}"; zero "Revises v" remaining.
- FIX 5 (FLAG): family + read-only fetch failures emit a one-line "[revision-family]" console.warn; graceful degradation and UI unchanged.
- Both existing specs EXTENDED with real-DOM keyboard/microcopy assertions (no parallel files).
- Both hard gates green: full 11-suite regression + tsc identity (GATE_OK). Zero backend edits (INV-3).
</success_criteria>

<output>
Create `.planning/quick/260702-wag-apply-workstream-b-ui-review-findings-a1/260702-wag-SUMMARY.md` when done.
</output>
