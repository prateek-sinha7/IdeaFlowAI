---
title: Workstream C — Run-Inputs Surfacing FE — UI Design Contract
status: draft
phase: Workstream C (run-inputs surfacing FE)
source_plan: .planning/REVISION-FAMILY-AND-RUN-INPUTS-PLAN.md (§5 deliverables 3, 4, 7; §7 brief-semantics-per-launch-path; §8 UI/UX contract)
sibling_contract: .planning/WORKSTREAM-B-UI-SPEC.md (same format + reuse-first bar; C's cards are simpler read-only surfaces)
discipline: REUSE-FIRST (Phase 20/21/22 UI-SPEC mandate — net-new visual language is a DEFECT)
date: 2026-07-02
---

# Workstream C — Run-Inputs Surfacing FE — UI Design Contract

This contract governs the three NEW read-only visual surfaces C2 builds (plan §5 deliverables 3, 4, 7).
Every node below names its **exact existing analog with `file:line`**. There is **no net-new visual
language** — the two new Thinking cards clone the `PlannerCard` idiom, the Files rows clone
`renderFileRow`, the impact badges clone the existing clarify-amber convention, and every chip,
chevron, collapsible, spinner, and card border already exists in this codebase and is inherited
verbatim. If an executor finds themselves inventing a hex value, a radius, a font size, an icon set,
or a motion curve, that is a defect — stop and cite the analog instead.

All file:line anchors below were read from source on 2026-07-02.

---

## 0. The organizing principle — timeline NARRATIVE ORDER

The Thinking tab is a **vertical timeline of one run's life**. Workstream C completes the narrative by
adding the true beginning (what the user asked) and the clarify exchange, so the tab reads top-to-bottom:

> **Starting point → Planner → Clarifications → Agents → Complete**

Concretely, in `AgentThinkingTab.tsx` main export render (`:614-658`):

1. **StartingPointCard** (deliverable 3) — inserted BEFORE the PlannerCard, at slot `:620` (the first
   child of the scroll region `:618`, ahead of `{pipelineState && <PlannerCard/>}` `:620-622`).
2. **PlannerCard** (existing, `:621`) — unchanged.
3. **ClarificationsCard** (deliverable 4) — inserted AFTER the PlannerCard and BEFORE the agent cards
   loop (`:624-636`).
4. **Agent cards** (existing) — unchanged.
5. **Pipeline complete** (existing, `:639-650`) — unchanged.

This ordering is a UI-checkable acceptance criterion (see each surface). Both new cards are **fully
props-driven** because this tab mounts on BOTH surfaces:
- **Live:** `PreviewPanel.tsx:746` (`<AgentThinkingTab agents pipelineState/>`) — `pipelineState` present.
- **Reopen / history:** `WorkflowHistory.tsx:791` (`<AgentThinkingTab agents={thinkingAgents}/>`) — **no
  `pipelineState`**. The cards MUST render here from their own props alone, never reading `pipelineState`.

---

## 1. Established design tokens (inherited — do NOT redefine)

Read out of the real components. Reuse exactly; declare no new ones. (These match the Workstream-B
contract §0 — same codebase, same tokens.)

### Color (60 / 30 / 10)
- **60% dominant surface:** white card bodies / `bg-white` (`AgentThinkingTab.tsx:139,475`); Files tab
  page `#f5f5f0` (`FilesTab.tsx:558`).
- **30% secondary:** `border-gray-100` / `border-gray-200` dividers + `bg-gray-50` hovers
  (`AgentThinkingTab.tsx:135,139`, `FilesTab.tsx:491`).
- **10% accent (RESERVED):** navy `#1B2A4A` + its tint `#E8EDF5` (`bg-[#E8EDF5]`). Reserved for: the
  card icon chip, the timeline dot fill, the revision-request emphasis, primary structural emphasis.
  Anchors: PlannerCard icon `AgentThinkingTab.tsx:141`, timeline dot `:124`, RevisionInstructionCard
  `:187-190`. **Do not introduce a second accent.**
- **Semantic (inherited maps — never invent):**
  - clarify / caution / **impact=high** → `text-amber-700 bg-amber-50 border-amber-200` — canonical at
    `QuestionnairePanel.tsx:285`, PlannerCard TIMEOUT badge `AgentThinkingTab.tsx:148,158`.
  - success / answered → `text-emerald-600 / text-emerald-700 bg-emerald-50` — Q/A answer line
    `QuestionnairePanel.tsx:182`, `:176`.
  - lower severity / muted → `bg-gray-100 text-gray-600` (severity map `AgentThinkingTab.tsx:262`).
  - error → red reserved for destructive/error only (`AgentThinkingTab.tsx:504,567`).

### Spacing
- 4-based scale already in use: `gap-1 / 1.5 / 2 / 2.5 / 3`, `px-3 py-2`, `px-4 py-3`, `px-5 py-4`,
  `pl-8` (timeline indent). Anchors: `AgentThinkingTab.tsx:119,139,618`, `FilesTab.tsx:491,558`. No new
  spacing values for this phase.

### Typography (inherited — 3 practical sizes + weights)
- Sizes: `text-[12px]` card title (`AgentThinkingTab.tsx:146`), `text-[11px]` body/answer
  (`:171`, `QuestionnairePanel.tsx:182`), `text-[10px]` subtitle/meta (`:151`), `text-[9px]`
  uppercase micro-label / badge (`:170,190`). Files rows: name `text-[12px] font-semibold`, meta
  `text-[10px]` (`FilesTab.tsx:497-499`).
- Weights: `font-semibold` (600) titles/active, `font-medium` (500) answer/controls, `font-bold`
  ONLY on the existing uppercase micro-labels (`:170,190`), regular (400) body. Previews use
  `line-clamp-2` / `truncate`.

### Radius
- Cards/rows: `rounded-xl` (`AgentThinkingTab.tsx:134`, `FilesTab.tsx:491`). Icon chips: `rounded-lg`
  (`AgentThinkingTab.tsx:141`). Timeline dot: `rounded-full` (`:122`). Badges/chips: `rounded-full`
  (`QuestionnairePanel.tsx:285`) or `rounded-lg` attachment chip (`IdeaInputPage.tsx:506`). Files count
  chip: `rounded` (`FilesTab.tsx:165`).

### Collapsible / chevron idioms (inherited — reuse, do not author new)
- **Controlled collapsible with chevron rotate:** a `<button onClick={()=>setOpen(v=>!v)}>` + `ChevronDown
  className={... transition-transform ${open ? "rotate-180" : ""}}` — PlannerCard `AgentThinkingTab.tsx:137-166`,
  InputPromptSection `:381-388`, OutputPreviewSection `:414-423`, ToolCallsSection `:318-325`. **This is
  THE collapsible for both new cards' bodies and every expander (Show more, attachment expand, Original
  brief).** (NB: `group-open:rotate-90` on native `<details>` is the B-side idiom; C uses the *controlled*
  `rotate-180` variant because these cards manage their own open state — the B2 "group-open only fires
  inside <details>" lesson applies.)
- **Card shell (collapsible):** `rounded-xl border overflow-hidden` header `button w-full flex items-center
  gap-3 px-4 py-3 bg-white hover:bg-gray-50/50 transition-colors text-left`, body `border-t border-gray-100
  px-4 py-3` — PlannerCard `AgentThinkingTab.tsx:134-173`. **This is THE card shell for both new cards.**
- **Line-clamp preview:** `line-clamp-2 leading-relaxed` (`HandoffAgentPanel.tsx:127`, OutputPreviewSection
  `AgentThinkingTab.tsx:426`). Show-more toggle is the same controlled `<button>` chevron idiom.

### Loading / spinner idioms
- `Loader2 ... animate-spin text-[#1B2A4A]` (`QuestionnairePanel.tsx:136`) or the ring spinner `span h-3.5
  w-3.5 border-2 border-gray-400 border-t-transparent rounded-full animate-spin` (`FilesTab.tsx:509,541`).
  Reuse either — no new spinner.

### Chips (inherited)
- **Attachment / file chip:** `inline-flex items-center gap-1 rounded-lg bg-gray-100 px-2.5 py-1
  text-[10px] text-gray-600` + a small lucide icon — `IdeaInputPage.tsx:506-511` (`File` icon). **This is
  THE attachment chip** ("📎 {name} — {n} chars" → use the `File`/`Paperclip` lucide icon + text; the 📎
  glyph is optional flavor, the chip shell is inherited).
- **Context-source chip (richer):** `flex items-center gap-1.5 bg-white border border-[#1B2A4A]/20 shadow-sm
  rounded-lg px-2.5 py-1.5` — `ContextSourcesRow AgentThinkingTab.tsx:296`. Use for the chained "From
  previous workflow" chip if a bordered variant reads better; the plain gray chip is the default.
- **Micro count/version chip:** `text-[9px] ... bg-gray-100 px-1.5 py-0.5 rounded-full font-medium`
  (`AgentThinkingTab.tsx:324`) — for the "revision of v{n-1}" chip.

### Non-goals (apply to ALL three surfaces)
- No new hex values, gradients, radii, font sizes, shadows, or motion curves.
- No new component library, no new icon set (lucide-react only — already imported).
- **No new parser.** `parseRunInput` is Workstream C1 (`lib/runInput.ts`, plan §6.1). These surfaces
  CONSUME its output; they MUST NOT re-implement marker extraction. (The one legacy inline regex,
  `RevisionInstructionCard AgentThinkingTab.tsx:183`, is NOT extended — C1 supersedes it.)
- **No workflow-name branch** (SC-001). StartingPointCard variant is chosen by parsed shape
  (`revisionInstruction?` / `chainContext?` present), not by `workflowType`. Files rows are
  type-agnostic.
- **No client-side clarify/round math** beyond grouping the already-structured `ClarifyRound[]` by its
  `round` field (plan §11: order by the content's `round`, artifacts have no `created_at`).

---

## Surface 1 — StartingPointCard (deliverable 3)

**Where:** `AgentThinkingTab.tsx` main export, a NEW card rendered as the FIRST child of the scroll
region `:618`, BEFORE the PlannerCard slot `:620`.
**Props (new, on `AgentThinkingTabProps` `:14-17`):** the parsed run input, e.g.
`startingPoint?: ParsedRunInput` where `ParsedRunInput = ReturnType<typeof parseRunInput>` (C1 shape:
`{brief, attachments[], revisionInstruction?, existingArtifactBlock?, chainContext?, preferences?}`),
plus the lineage hints needed for the revision variant (`rootRunId?`, `parentVersionNumber?`). Renders
`null` when `startingPoint` is absent (older mounts that don't thread it) — zero regression.
**Data source:** live = `submittedBrief` captured in the `onStartPipeline` wrapper (plan §6.2) parsed
through `parseRunInput`; reopen/history = `fullRun.input` / `selectedRun.input` parsed the same way.
The "Original brief (v1)" expander lazy-fetches the family ROOT run via `getWorkflow(rootRunId)` (root
id from Workstream B's `/family` / `rootRunId` field).

### Analog
- **Whole card shell** clones **PlannerCard** `AgentThinkingTab.tsx:108-177` verbatim: `relative pl-8`
  wrapper with the timeline dot (`:119-132`), `rounded-xl border overflow-hidden` (`:134`), header
  `button ... px-4 py-3 bg-white hover:bg-gray-50/50` (`:137-139`), icon chip `w-7 h-7 rounded-lg
  bg-[#E8EDF5]` (`:141`), title `text-[12px] font-semibold text-gray-900` (`:146`), subtitle `text-[10px]
  text-gray-400 truncate` (`:151`), trailing `ChevronDown ... rotate-180` (`:164`), expanded body
  `border-t border-gray-100 px-4 py-3` (`:168-169`).
- **Card icon:** a lucide glyph in the `bg-[#E8EDF5]` chip — use `FileText` (the brief-is-a-document
  read) or `MessageSquare`; NOT `Brain` (that is the Planner's). `text-[#1B2A4A]` fill matching `:142`.
- **Timeline dot (starting point):** clone `:119-132` — but this is the FIRST dot, so its dot is a solid
  `bg-[#1B2A4A]` filled circle (done state, `:124`) with the `FileText` glyph; the connector line
  `w-px flex-1 bg-gray-200` (`:131`) drops down into the PlannerCard's dot, making one continuous rail.
- **Revision-instruction emphasis block** (revision variant, primary content) clones
  **RevisionInstructionCard** `AgentThinkingTab.tsx:182-195` verbatim: `rounded-xl border-2
  border-[#1B2A4A]/30 bg-[#1B2A4A]/5 px-3 py-2.5`, `Pencil h-3 w-3 text-[#1B2A4A]`, label `text-[9px]
  font-bold text-[#1B2A4A] uppercase tracking-widest` "Revision Request", body `text-[11px]
  text-[#1B2A4A] font-medium leading-relaxed`.
- **Brief body (normal variant)** clones the line-clamp preview idiom: `text-[11px] text-gray-700
  leading-relaxed` (PlannerCard intent body `:171`) with `line-clamp-2` (`:426`) when collapsed; a
  **Show more / Show less** controlled `<button>` chevron toggle (InputPromptSection `:381-388`) expands
  to full text (`whitespace-pre-wrap`, capped-height scroll `max-h-[500px] overflow-y-auto` like `:398`).
- **Attachment chips** clone the attachment chip `IdeaInputPage.tsx:506-511`: `inline-flex items-center
  gap-1 rounded-lg bg-gray-100 px-2.5 py-1 text-[10px] text-gray-600` + `File`/`Paperclip` icon, label
  "{name} — {n} chars". Each chip is an **expander** (button) revealing that attachment's parsed content
  in the collapsible body idiom; wrap the chip row in `flex flex-wrap gap-1.5` (`IdeaInputPage.tsx:504`).
- **"revision of v{n-1}" chip** clones the micro count chip `AgentThinkingTab.tsx:324`
  (`text-[9px] bg-gray-100 ... px-1.5 py-0.5 rounded-full font-medium`), placed in the header title row
  beside the title (mirrors the TIMEOUT badge placement `:147-149`).
- **"Original brief (v1)" expander** (revision variant) clones **InputPromptSection** `:371-405`: a
  `<button>` uppercase micro-label + chevron that, when open, renders the lazily-fetched root brief in
  the bordered `pre`/text block (`:390-401`).
- **"From previous workflow" chip** (chained variant, collapsed) clones the same attachment/context chip;
  expanding reveals the `chainContext` string in the collapsible body.
- **Loading (lazy original-brief fetch):** the ring spinner `span h-3.5 w-3.5 border-2 border-gray-400
  border-t-transparent rounded-full animate-spin` (`FilesTab.tsx:509`) or `Loader2 animate-spin`
  (`QuestionnairePanel.tsx:136`) beside "Loading original brief…" `text-[10px] text-gray-400`.
- **Empty (no brief text — e.g. attachment-only run):** the muted fallback copy `text-[10px]
  text-gray-400` (`FilesTab.tsx:547,550`) e.g. "No typed brief — see attachments below." Never render an
  empty card frame with no content.

### Variants (plan §7 — chosen by parsed shape, NOT workflowType)
| Parsed shape (from `parseRunInput`) | Card renders |
|---|---|
| Normal (`brief` + `attachments[]`, no revision/chain markers) | Title "Starting point" · brief line-clamped w/ Show more · attachment chips (expandable) |
| Revision (`revisionInstruction` present) | RevisionInstructionCard emphasis block as PRIMARY · "revision of v{n-1}" chip in header · collapsed "Original brief (v1)" expander (lazy root fetch) |
| Chained (`chainContext` present) | Brief primary · collapsed "From previous workflow" chip |
| Legacy blobs (`existingArtifactBlock` / `preferences`) | Parser decomposes retroactively → falls into the revision/normal variant above; NO special UI |
| Post-Phase-D (instruction-only) | Pass-through → the revision or normal variant renders unchanged |

### Layout & states
- **collapsed (default):** header shows the `FileText` icon chip, title **"Starting point"** (or
  **"Revision request"** for the revision variant), a one-line `truncate` subtitle previewing the
  brief/instruction (`:151` idiom), the "revision of v{n-1}" chip when applicable, and the chevron.
- **hover:** header `hover:bg-gray-50/50` (inherited `:139`).
- **expanded:** chevron `rotate-180`; body reveals the variant content per the table above.
- **Show-more (brief):** collapsed brief = `line-clamp-2`; a "Show more"/"Show less" button toggles full
  text.
- **attachment expanded:** clicking a chip reveals that attachment's content inline (collapsible idiom).
- **loading:** only the "Original brief (v1)" region shows the spinner while `getWorkflow(rootRunId)`
  resolves; the rest of the card stays interactive.
- **empty:** muted-gray fallback line; no bare frame.
- **reopen (no `pipelineState`):** renders identically from `startingPoint` prop alone. This is a hard
  acceptance criterion.

### A11y (plan §8 — MANDATORY)
- The card header, the Show-more toggle, each attachment-chip expander, and the "Original brief (v1)"
  expander are all real `<button>`s carrying `aria-expanded` and a descriptive `aria-label`
  (e.g. `aria-label="Show original brief version 1"`, `aria-label={open ? "Collapse brief" : "Expand brief"}`).
- Chevrons are `aria-hidden` decoration; state is on the button's `aria-expanded`.
- Attachment chips convey name + size in accessible text (already text content, not icon-only).
- The lazy fetch region carries `aria-busy` while loading.

### UI-checkable acceptance
- [ ] StartingPointCard renders as the FIRST card in the Thinking scroll region, BEFORE PlannerCard.
- [ ] It renders on the reopen/history mount (`WorkflowHistory.tsx:791`, no `pipelineState`) from props.
- [ ] Card shell classes are the PlannerCard shell (`rounded-xl border overflow-hidden`, header `px-4
      py-3 bg-white hover:bg-gray-50/50`, icon chip `w-7 h-7 rounded-lg bg-[#E8EDF5]`) — no new frame.
- [ ] Normal variant: brief `line-clamp-2` with a working Show more/less toggle; attachment chips use
      the `IdeaInputPage.tsx:506` chip classes and expand.
- [ ] Revision variant: instruction shown in the RevisionInstructionCard emphasis block
      (`border-2 border-[#1B2A4A]/30 bg-[#1B2A4A]/5`); "revision of v{n-1}" chip present; "Original brief
      (v1)" is collapsed and fetched ONLY on first expand (lazy).
- [ ] Chained variant: collapsed "From previous workflow" chip.
- [ ] Variant is selected by parsed shape, not `workflowType` (no workflow-name string in the component).
- [ ] Uses `parseRunInput` output — no marker regex inside the card.
- [ ] Loading uses an inherited spinner; empty uses the muted-gray fallback copy.
- [ ] Header/expanders carry `aria-expanded` + `aria-label`; chevrons `aria-hidden`.

---

## Surface 2 — ClarificationsCard (deliverable 4)

**Where:** `AgentThinkingTab.tsx` main export, a NEW card rendered AFTER the PlannerCard (`:621`) and
BEFORE the agent cards loop (`:624`).
**Props (new):** `clarifications?: ClarifyRound[]` where `ClarifyRound = {round, qa: [{question_id,
question_text, impact_level, answer}]}` (plan §6.5). Renders `null` when the array is absent or empty —
a `PROCEED` run correctly shows NOTHING (plan §11).
**Data source:** live = the retained clarify state folded in `handleQuestionnaireSubmit` (C1, plan §6.5)
— the card appears the moment answers are submitted (answers visibly land, never vanish); reopen =
`getRunArtifacts(token, id, {kind:"clarifications", includeContent:true})` (C1 fetcher, plan §6.6)
parsed into `ClarifyRound[]`, ordered by the content's `round` field (plan §11).

### Analog
- **Card shell** clones the PlannerCard collapsible shell `AgentThinkingTab.tsx:134-173` (same
  `rounded-xl border overflow-hidden`, header, `bg-[#E8EDF5]` icon chip, body `border-t border-gray-100
  px-4 py-3`) with the same `relative pl-8` timeline dot + connector (`:119-132`) so it sits ON the
  timeline rail between Planner and Agents. Card icon: `MessageCircleQuestion` (the clarify glyph, imported
  in `QuestionnairePanel.tsx:6`), `text-[#1B2A4A]`.
- **Per-round group header** clones the section micro-label `text-[9px] font-bold ... uppercase
  tracking-widest` (ToolCallsSection `:323`, ContextSourcesRow `:279`) with a count chip `text-[9px]
  bg-gray-100 ... px-1.5 py-0.5 rounded-full font-medium` (`:324`) — label "Round {n}".
- **Each Q&A pair** clones the **QuestionnairePanel summary card** `QuestionnairePanel.tsx:174-185`:
  question `text-[12px] font-semibold text-gray-800 leading-snug` (`:180`), answer as a filled line
  `text-[11px] text-emerald-600 font-medium mt-1` prefixed with "✓" (`:182`). Wrap each pair in the same
  `rounded-xl border px-4 py-3` container (`:176`) — use `border-emerald-200 bg-emerald-50/30` for
  answered (`:176`), the exact analog.
- **Impact badge** clones the clarify impact badge `QuestionnairePanel.tsx:285`:
  - `impact_level === "high"` → `inline-flex items-center gap-1 text-[9px] font-semibold text-amber-700
    bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5` with "★ High impact".
  - `impact_level === "medium"` → the muted tier `text-gray-600 bg-gray-100` (severity map
    `AgentThinkingTab.tsx:262`) — "Medium impact".
  - `impact_level === "low"` / unset → omit the badge (avoid noise), OR a plain `text-[9px] text-gray-400`
    label. Never invent a new color.
  - Placed inline before/above the question text (mirrors `QuestionnairePanel.tsx:283-293` placement).
- **Collapsible body:** the whole card body follows the PlannerCard expand idiom (`:137-166`
  controlled chevron `rotate-180`); default OPEN (clarify is short and high-value), collapsible to save
  space. Rounds stack inside `space-y-*` (`:328` idiom).
- **Loading (reopen fetch):** `Loader2 animate-spin` (`QuestionnairePanel.tsx:136`) + "Loading
  clarifications…" `text-[10px] text-gray-400` inside the body while `getRunArtifacts` resolves.
- **Empty:** the card does not render at all (no rounds) — there is no "empty clarify" state, by design.

### Layout & states
- **hidden:** default when `clarifications` is empty/absent (PROCEED run) — nothing on the timeline.
- **present — collapsed:** header shows `MessageCircleQuestion` chip, title **"Clarifications"**, a
  subtitle `text-[10px] text-gray-400 truncate` e.g. "{N} questions across {R} round(s)", chevron.
- **present — expanded (default):** per-round groups, each with its "Round {n}" label + count chip, then
  the Q/A pair cards (question semibold, answer emerald filled line, impact badge).
- **hover:** header `hover:bg-gray-50/50` (inherited).
- **live submit:** the card mounts/updates the instant `handleQuestionnaireSubmit` folds the round in —
  answers persist across QuestionnairePanel unmount (retention is C1's job; the card just reads state).
- **reopen — loading:** spinner in the body until artifacts resolve.

### A11y (plan §8)
- Card header toggle is a `<button>` with `aria-expanded` + `aria-label="Clarifications, {N} questions"`.
- Each impact badge has accessible text ("High impact" / "Medium impact") — not color-only signaling.
- Questions and answers are plain readable text (no icon-only meaning); the "✓" answer marker is
  decorative and paired with the visible answer text.
- The reopen fetch region carries `aria-busy` while loading.

### UI-checkable acceptance
- [ ] ClarificationsCard renders AFTER PlannerCard and BEFORE the agent cards on the timeline.
- [ ] It renders NOTHING for a PROCEED run (empty/absent `clarifications`).
- [ ] Renders on both live (retained state) and reopen (`getRunArtifacts`) mounts.
- [ ] Per-round groups labelled "Round {n}" with the inherited micro-label + count-chip classes.
- [ ] Each Q/A uses the QuestionnairePanel summary-card classes (question `text-[12px] font-semibold
      text-gray-800`, answer `text-[11px] text-emerald-600 font-medium`, container `border-emerald-200
      bg-emerald-50/30`).
- [ ] Impact badges reuse `QuestionnairePanel.tsx:285` amber-high convention; medium = gray tier; no new
      color literals.
- [ ] Live: the card appears the moment answers are submitted and survives QuestionnairePanel unmount.
- [ ] Reopen: loading spinner is an inherited idiom; ordering follows the content `round` field.
- [ ] Header toggle carries `aria-expanded`; impact badges have accessible text.

---

## Surface 3 — Files "Run input" section (deliverable 7)

**Where:** `FilesTab.tsx`, a NEW section rendered in BOTH layout branches — the non-app-builder layout
(after the header row `:559-572`, alongside the "Final output"/"Agent outputs" sections `:616-637`) and
the app-builder layout (`:575-612`). Per the narrative-order principle, render it as the **first**
content section (the run's input precedes its outputs), directly under the "{N} files available" header
row `:560`.
**Props:** thread the parsed brief + clarify presence into `FilesTab`. Reuse the existing `parseRunInput`
output already available to the parent (do NOT re-parse here). Concretely add e.g. `runInputBrief?: string`
(the parsed `prompt.md` content) and `clarificationsMarkdown?: string` (rendered Q&A markdown, present
only when rounds exist). Both optional/undefined → the section does not render (zero regression for the
many existing `FilesTab` call sites that pass neither).
**Data source:** live = `submittedBrief`/retained clarify (C1) rendered to markdown; reopen/history =
`selectedRun.input` + `getRunArtifacts(...clarifications...)` (C1).

### Analog
- **Section header** clones the plain uppercase label variant used by "Final output"/"Agent outputs"
  `FilesTab.tsx:619,627`: `p className="text-[10px] uppercase tracking-wider text-gray-400 font-medium
  mb-2"` reading **"Run input"**. (The `SectionHeader` component `:161-167` with a count chip is an
  acceptable alternative — the plain label matches "Agent outputs" more exactly, per plan §5.7 "same
  section idiom as Agent outputs".)
- **Each file row** clones **`renderFileRow`** `FilesTab.tsx:483-515` VERBATIM (the `motion.div` with
  `initial/animate/transition delay idx*0.03`, `rounded-xl border border-gray-200 bg-white px-4 py-3
  hover:border-gray-300 hover:shadow-sm`, icon chip `h-9 w-9 rounded-lg bg-gray-100 border`, name
  `text-[12px] font-semibold text-gray-900 truncate`, meta `text-[10px] text-gray-400`, download button
  with the `Download`/spinner). Build the two rows as `FileItem`s (`:56-65`) and pass them through the
  SAME `renderFileRow`:
  - `prompt.md` — `{ name:"prompt.md", type:"Run input", icon: FileText, format:"Markdown (.md)",
    content: parsed brief (raw), mimeType:"text/markdown", size: formatSize(len) }`.
  - `clarifications.md` — same shape, `content:` rendered Q&A markdown, present **only when rounds exist**.
- **Download** reuses the existing `downloadBlob` path `FilesTab.tsx:465,652` (the `else` branch of
  `handleDownload` — plain `downloadBlob(file.content, file.name, file.mimeType)`). No new download code;
  `prompt.md`/`clarifications.md` fall straight into the default branch (they are not the special-cased
  `user-stories-md`/`project-zip`/`presentation-pptx` ids).
- **View (optional):** if a view affordance is wanted, reuse the existing row's single download control —
  do NOT add a new "view" button unless the row analog already has one (it does not; keep to download).

### Layout & states
- **default:** a "Run input" section label + the `prompt.md` row (always, when `runInputBrief` present)
  and the `clarifications.md` row (only when `clarificationsMarkdown` present), each a normal downloadable
  `renderFileRow`.
- **hover:** row `hover:border-gray-300 hover:shadow-sm` (inherited `:491`).
- **downloading:** the row's download button swaps to the ring spinner `h-3.5 w-3.5 border-2 ...
  animate-spin` (`:509`) via the existing `downloadingId` state.
- **no clarify rounds:** the `clarifications.md` row is absent (only `prompt.md` shows).
- **no run input threaded (legacy call site):** the whole section is absent.
- **totalCount:** the new rows count toward the existing "{N} files available" header (`:470,561`) so the
  count stays truthful; include them in the `totalCount` sum and the "Download All" iteration (`:564`).

### A11y
- Rows inherit the existing download button's `title={`Download ${file.name}`}` affordance (`:506`).
- The "Run input" label is a real heading-like `<p>` matching the sibling sections; no icon-only meaning.
- Fully keyboard-operable via the inherited download `<button>`.

### UI-checkable acceptance
- [ ] A "Run input" section renders (first content section) in BOTH the app-builder and non-app-builder
      layouts, using the plain uppercase label classes of "Agent outputs" (`text-[10px] uppercase
      tracking-wider text-gray-400 font-medium`).
- [ ] `prompt.md` row renders whenever the parsed brief is threaded; it is the unmodified `renderFileRow`
      shape and downloads the raw brief via `downloadBlob`.
- [ ] `clarifications.md` row renders ONLY when clarify rounds exist; same row shape; downloads the
      rendered Q&A markdown.
- [ ] Section is fully type-agnostic — no `workflowType` string branch anywhere in it (SC-001).
- [ ] New rows are counted in "{N} files available" and included in "Download All".
- [ ] No new row/header/button styling; no new parser (consumes C1's parsed output).
- [ ] Legacy call sites that thread neither prop show no "Run input" section (zero regression).

---

## Prop-threading contract (both mounts)

Both new Thinking cards and the Files section need their data threaded through the two tab mount sites.
The `parseRunInput` call + clarify retention live in the parents (C1); these components only receive
already-parsed props.

| Component | Live mount | Reopen / history mount |
|---|---|---|
| `AgentThinkingTab` (StartingPointCard + ClarificationsCard) | `PreviewPanel.tsx:746` | `WorkflowHistory.tsx:791` |
| `FilesTab` ("Run input" section) | `PreviewPanel.tsx:734` | `WorkflowHistory.tsx:797-814` |

(Plan §6.8 cites `PreviewPanel.tsx:632/644` and `WorkflowHistory.tsx:709/715`; the verified current
line numbers on 2026-07-02 are `746/734` and `791/797` respectively — thread the props at the actual
JSX call sites, wherever they have drifted to.) All four new props are optional and default-undefined so
every OTHER call site of these components compiles and renders unchanged.

---

## Reuse Analog Map

| New node | Existing analog (file:line) |
|---|---|
| StartingPointCard shell (card + timeline dot + collapsible) | `AgentThinkingTab.tsx:108-177` (PlannerCard) |
| Timeline dot + connector rail | `AgentThinkingTab.tsx:119-132` |
| Card icon chip (`bg-[#E8EDF5]`) | `AgentThinkingTab.tsx:141-143` |
| Revision-instruction emphasis block | `AgentThinkingTab.tsx:182-195` (RevisionInstructionCard) |
| Brief line-clamp preview | `AgentThinkingTab.tsx:426` / `HandoffAgentPanel.tsx:127` (`line-clamp-2`) |
| Show more / Original brief expander (collapsible + copy) | `AgentThinkingTab.tsx:371-405` (InputPromptSection) |
| Controlled chevron rotate | `AgentThinkingTab.tsx:164` (`ChevronDown ... rotate-180`) |
| Attachment chip ("📎 {name} — {n} chars") | `IdeaInputPage.tsx:504-511` (bg-gray-100 rounded-lg chip) |
| Chained "From previous workflow" chip | `IdeaInputPage.tsx:506` / `AgentThinkingTab.tsx:296` (context chip) |
| "revision of v{n-1}" micro chip | `AgentThinkingTab.tsx:324` (count chip) |
| ClarificationsCard shell | `AgentThinkingTab.tsx:134-173` (PlannerCard shell) |
| Clarify card icon (`MessageCircleQuestion`) | `QuestionnairePanel.tsx:6,247` |
| Round group micro-label + count chip | `AgentThinkingTab.tsx:323-324` (ToolCallsSection) |
| Q/A pair (question semibold + emerald answer line) | `QuestionnairePanel.tsx:174-185` (summary card) |
| Impact badge (high = amber) | `QuestionnairePanel.tsx:285` |
| Impact badge (medium = gray tier) | `AgentThinkingTab.tsx:262` (severity map) |
| "Run input" section label | `FilesTab.tsx:619,627` ("Agent outputs" plain label) / `SectionHeader:161-167` |
| `prompt.md` / `clarifications.md` rows | `FilesTab.tsx:483-515` (renderFileRow) |
| Download path | `FilesTab.tsx:465,652` (downloadBlob) |
| Loading spinner (Loader2) | `QuestionnairePanel.tsx:136` |
| Loading spinner (ring) | `FilesTab.tsx:509,541` |
| Empty / muted fallback copy | `FilesTab.tsx:547,550` |
| Parsed run input (data) | `lib/runInput.ts` `parseRunInput` (Workstream C1, plan §6.1) |

## No Analog Found

- **None visual.** Every visual, motion, chip, badge, collapsible, spinner, and row element maps to an
  existing analog above. These three surfaces are strictly simpler than Workstream B (read-only cards +
  file rows; no radiogroup, no dropdown, no cross-fade navigation).
- **Data dependency (not a defect):** `parseRunInput` (`lib/runInput.ts`) and the clarify retention +
  `getRunArtifacts` fetcher are **Workstream C1**, not visual language. These surfaces (C2) CONSUME them.
  The one legacy inline regex in `RevisionInstructionCard` (`AgentThinkingTab.tsx:183`) is superseded by
  C1 and MUST NOT be copied into the new cards (INV-12 "three FE parser copies → one lib").
- **Cross-workstream dependency (not a defect):** the StartingPointCard revision variant's "Original
  brief (v1)" needs the family ROOT id, which Workstream B ships (`rootRunId` / `/family`). If B's lineage
  props are threaded, the expander fetches the root; if absent, the expander is simply omitted (graceful).
