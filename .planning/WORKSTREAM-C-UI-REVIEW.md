---
title: Workstream C — Run-Inputs Surfacing FE — UI Review (closing gate)
status: complete
phase: Workstream C (run-inputs surfacing FE)
baseline: .planning/WORKSTREAM-C-UI-SPEC.md + REVISION-FAMILY-AND-RUN-INPUTS-PLAN.md §8
audit_mode: CODE-ONLY (dev server auth-gated → no screenshots; Phase-21 / Workstream-B precedent)
date: 2026-07-03
---

# Workstream C — Run-Inputs Surfacing FE — UI Review

**Baseline:** WORKSTREAM-C-UI-SPEC.md (reuse-first contract, 21 analogs mapped) + plan §8 a11y mandate.
**Screenshots:** NOT captured — dev server is auth-gated offline. This is a **code-level** audit
(Tailwind-class fidelity, ARIA/role wiring, state coverage, microcopy, XSS surface). **Pixel / render
fidelity is explicitly deferred** to a live authenticated pass, per the Phase-21 / Workstream-B precedent.
**Files audited:** StartingPointCard.tsx, ClarificationsCard.tsx, AgentThinkingTab.tsx (timeline order +
prop plumbing), FilesTab.tsx ("Run input" section), WorkflowHistory.tsx + PreviewPanel.tsx (mount wiring),
lib/clarifications.ts (transform, XSS surface), types/index.ts (ClarifyRound).

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Typography | 4/4 | Only inherited 12/11/10/9px + semibold/medium/bold-microlabel/regular; zero raw sizes |
| 2. Color | 4/4 | Only inherited navy `#1B2A4A`/`#E8EDF5`, amber-50/200/700, emerald-200/50/600, gray tiers; zero new hex |
| 3. Spacing / Layout | 4/4 | 4-based scale throughout; both cards on the `relative pl-8` rail; "Run input" is the first Files section |
| 4. Visual hierarchy | 4/4 | Brief subordinate; revision emphasis block prominent; Q semibold > A emerald > impact micro-badge; timeline order correct |
| 5. Consistency | 3/4 | Same card family as PlannerCard, same renderFileRow; but the "revision of v{n-1}" chip is never threaded → dead in production |
| 6. Accessibility (§8) | 4/4 | Every expander is a native `<button>` w/ aria-expanded + aria-label; chevrons aria-hidden; aria-busy on both lazy regions; badges carry text. **B's div-onClick BLOCK is not repeated.** |

**Overall: 23 / 24**

---

## Top Priority Fixes

1. **The "revision of v{n-1}" header chip is dead code (consistency / contract completeness)** —
   `StartingPointCard.tsx:106-110` renders the chip only when `revisionParentVersion != null`, and the
   prop is plumbed through `AgentThinkingTab.tsx:589,637` — but **neither mount site passes it**:
   `PreviewPanel.tsx:752` (live) threads only `runInput`+`clarifications`, and `WorkflowHistory.tsx:814-820`
   (reopen) threads `originalBriefRootRunId` but **not** `revisionParentVersion` (grep: prop appears only
   inside StartingPointCard + AgentThinkingTab + its test, never at a mount). Net effect: the
   revision-variant chip mandated by UI-SPEC Surface 1 ("`revision of v{n-1}` chip present") never renders
   in the running app. *Fix:* thread `revisionParentVersion={selectedRun.parentVersionNumber}` (or the
   Workstream-B lineage field) at `WorkflowHistory.tsx:814` and the live equivalent at `PreviewPanel.tsx:752`.

2. **Original-brief expander is asymmetric across mounts (minor, graceful)** — the live
   `AgentThinkingTab` mount (`PreviewPanel.tsx:752`) does not thread `originalBriefRootRunId`, so on a
   **live** revision run the "Original brief (v1)" lazy expander is silently omitted; it only appears on
   the **reopen** mount (`WorkflowHistory.tsx:819`). This is the spec's sanctioned graceful-omit ("if
   absent, the expander is simply omitted"), so it is not a defect — but the live revision surface is
   feature-poorer than reopen for no stated reason. *Fix (optional):* thread the live root id if available.

3. **Clarifications timeline dot diverges from the PlannerCard done-dot (cosmetic nit)** —
   `ClarificationsCard.tsx:63` fills the dot with `bg-[#E8EDF5]` + navy border, whereas the
   StartingPointCard first dot (`:87`) and the PlannerCard done dot (`AgentThinkingTab.tsx:133`) use the
   solid `bg-[#1B2A4A]` fill. Both are inherited tokens (no new hex), and a tint fill legitimately reads
   as an "informational, non-terminal" step — acceptable, noted only for rail visual rhythm.

---

## Detailed Findings

### Pillar 1 — Typography (4/4)
- **PASS** — Every node uses only the inherited scale. StartingPointCard: title `text-[12px] font-semibold`
  (`:105`), body `text-[11px]` (`:127,165`), subtitle/meta `text-[10px]` (`:112,148,181`), micro-labels
  `text-[9px] font-bold ... uppercase tracking-widest` (`:107,125,137,172`). ClarificationsCard: question
  `text-[12px] font-semibold` (`:111`), answer `text-[11px] font-medium` (`:113`), round label + count
  `text-[9px]` (`:98,99`), badge `text-[9px] font-semibold` (`:30,37`). The `pre` blocks drop to
  `text-[9px] font-mono` (`:151,198,221`) — an inherited raw-content idiom, still in-scale. **No raw font
  size outside the 9/10/11/12 scale anywhere.**

### Pillar 2 — Color (4/4)
- **PASS** — Card icon chip `bg-[#E8EDF5]` + `text-[#1B2A4A]` (`StartingPointCard.tsx:100-101`,
  `ClarificationsCard.tsx:76-77`) matches the PlannerCard chip exactly (`AgentThinkingTab.tsx:150`).
  Revision emphasis block is the verbatim RevisionInstructionCard convention `border-2 border-[#1B2A4A]/30
  bg-[#1B2A4A]/5` + `text-[#1B2A4A]` (`StartingPointCard.tsx:122-127`, cf. `:182-195`). Q/A container is
  the inherited `border-emerald-200 bg-emerald-50/30` with answer `text-emerald-600`
  (`ClarificationsCard.tsx:104,113`). Impact badges reuse the exact clarify amber convention `text-amber-700
  bg-amber-50 border-amber-200` (high, `:30`) and the gray severity tier `text-gray-600 bg-gray-100`
  (medium, `:37`); low/unset omitted. First timeline dot solid navy (`StartingPointCard.tsx:87`). **No new
  hex value introduced** — grep of raw sizes/colors shows only inherited tokens.

### Pillar 3 — Spacing / Layout (4/4)
- **PASS** — Both cards sit on the `relative pl-8` timeline rail with the dot+connector
  (`StartingPointCard.tsx:84-91`, `ClarificationsCard.tsx:60-67`) matching PlannerCard `:128-141`; the
  connector `w-px flex-1 bg-gray-200` drops into the next dot for one continuous rail. Header `px-4 py-3
  gap-3`, body `border-t border-gray-100 px-4 py-3`, revision block `px-3 py-2.5`, chip `px-2.5 py-1`,
  badge `px-2 py-0.5`, `space-y-3`/`space-y-4`/`gap-1.5` — all inherited 4-based steps.
- **PASS** — Timeline **narrative order is correct**: StartingPointCard (`AgentThinkingTab.tsx:634`) →
  PlannerCard (`:641`) → ClarificationsCard (`:646`) → agent cards (`:649`) → Pipeline complete (`:663`).
  The `hasAnyData` guard (`:600-602`) was correctly widened so an inputs-only run does not short-circuit
  to `EmptyState`.
- **PASS** — The "Run input" section renders as the **first** content section, above the `isAppBuilder`
  ternary (`FilesTab.tsx:626-631`), so it appears in **both** layout branches without duplication, using
  the plain "Agent outputs" label classes `text-[10px] uppercase tracking-wider text-gray-400 font-medium`
  (`:628`). Rows are counted in `totalCount` (`:518`) and included in "Download All" (`:612`) — the file
  count stays truthful.

### Pillar 4 — Visual hierarchy (4/4)
- **PASS** — StartingPointCard: the brief body is `text-[11px] text-gray-700 line-clamp-2` when collapsed
  (`:165`), subordinate to the louder agent cards; the revision instruction is promoted into the bordered
  navy emphasis block as PRIMARY content (`:122-128`) with its uppercase "Revision Request" micro-label.
  ClarificationsCard weights read correctly: question `text-[12px] font-semibold text-gray-800` > answer
  `text-[11px] text-emerald-600` > impact badge `text-[9px]` (`:111,113,30`). Card titles stay `text-[12px]
  font-semibold text-gray-900`, subordinate to the rail. Clean top-to-bottom "life of a run" read.

### Pillar 5 — Consistency (3/4)
- **PASS** — Both new cards are unmistakably the same family as PlannerCard: identical shell (`rounded-xl
  border overflow-hidden border-gray-100`), identical header button (`w-full flex items-center gap-3 px-4
  py-3 bg-white hover:bg-gray-50/50 text-left`), identical `bg-[#E8EDF5]` icon chip, identical controlled
  `ChevronDown ... rotate-180` chevron, identical dot+connector rail. The Files rows go through the SAME
  `renderFileRow` (`FilesTab.tsx:629`) as every existing section — byte-identical row shape and download
  path (`downloadBlob`). Round micro-label + count chip clone ToolCallsSection `:323-324`.
- **FLAG (see Top Fix 1)** — the "revision of v{n-1}" chip is authored to spec but its `revisionParentVersion`
  prop is never threaded at either mount, so the revision-variant header chip never appears in production;
  UI-SPEC Surface 1 acceptance ("`revision of v{n-1}` chip present") is unmet at runtime.
- **FLAG (minor, see Top Fix 3)** — the Clarifications dot uses a tint fill vs the solid-navy fill used by
  the StartingPoint/Planner dots. Inherited tokens, acceptable, but a small rail-rhythm inconsistency.

### Pillar 6 — Accessibility (4/4) — §8 scrutiny, learning from B's BLOCK
- **PASS** — **Every** collapsible/expander is a real native `<button>`, not a `div onClick` (this is the
  precise defect that produced B's BLOCK + child-row FLAG — **not repeated here**):
  - Card headers: `StartingPointCard.tsx:94-98` and `ClarificationsCard.tsx:70-74`, each with
    `aria-expanded` + descriptive `aria-label` ("Collapse/Expand starting point", "Clarifications, N questions").
  - Show more/less brief toggle: `:168-172` (`aria-expanded` + "Show more/less of the brief").
  - "Original brief (v1)" expander: `:133-137` (`aria-expanded` + `aria-label="Show original brief version 1"`).
  - Each attachment-chip expander: `:210-214` (`aria-expanded` + "Expand/Collapse attachment {name}").
  - Chained "From previous workflow" expander: `:187-191` (`aria-expanded` + aria-label).
  Native buttons are inherently keyboard-focusable and Enter/Space-activatable — no stranded keyboard path.
- **PASS** — All chevrons and decorative glyphs carry `aria-hidden` (`:88,101,114,124,139,141,175,193,195,
  216,218`; `ClarificationsCard.tsx:64,77,83,90`); state lives on the button's `aria-expanded`.
- **PASS** — Both lazy/async regions carry `aria-busy`: the Original-brief fetch wrapper
  `aria-busy={originalLoading}` (`StartingPointCard.tsx:132`) and the Clarifications reopen body
  `aria-busy={loading || undefined}` (`ClarificationsCard.tsx:87`).
- **PASS** — Impact badges convey meaning in accessible **text** ("High impact" / "Medium impact"), not
  color-only; the ★ and ✓ glyphs are decorative and paired with visible text (`:30-38`, `:113`).
- **PASS** — Files "Run input" rows inherit the existing download `<button>` + `title` affordance via the
  unmodified `renderFileRow`, so they are fully keyboard-operable; the label is a real `<p>` heading-analog.

### Reuse-fidelity
- **HONORED — zero net-new visual language.** Every node cites and matches its UI-SPEC analog: card shell +
  dot (PlannerCard `:108-177`), revision emphasis (RevisionInstructionCard `:182-195`), Show-more / Original-
  brief expander (InputPromptSection idiom), attachment chip (IdeaInputPage `:506`), micro count chip (`:324`),
  Q/A summary card (QuestionnairePanel `:174-185`), impact badge (`:285`), severity gray tier (`:262`), ring +
  Loader2 spinners, `renderFileRow` (`FilesTab.tsx:483-515`), `downloadBlob` path. No new hex, radius, font
  size, shadow, or motion curve. No `workflowType` branch — variants chosen by parsed shape
  (`StartingPointCard.tsx:35-36`), SC-001 respected. No re-implemented parser — both surfaces consume C1's
  `parseRunInput` / `renderClarificationsMarkdown` (`StartingPointCard.tsx:5,34`, `FilesTab.tsx:55,69`); the
  legacy inline regex is not copied (INV-12 respected).

### Async / empty / loading states
- **PASS** — Original-brief lazy fetch gates on `!originalFetched` + first expand only
  (`StartingPointCard.tsx:66`), shows the inherited ring spinner + "Loading original brief…" (`:145-149`),
  and degrades to "No original brief available." on empty/error (`:152`, `catch → ""` at `:75-76`).
  Clarifications reopen shows `Loader2` + "Loading clarifications…" (`:88-92`). PROCEED run renders NOTHING
  (`ClarificationsCard.tsx:52`). Attachment-only run shows "No typed brief — see attachments below."
  (`StartingPointCard.tsx:180-181`); a fully empty input renders `null` (`:56`) — no bare card frame. All
  graceful, no blank/broken frame.

### XSS-safety (UI layer)
- **PASS** — Grep confirms **no** `dangerouslySetInnerHTML` and **no** `<iframe`/embed in any C surface.
  Brief, revision instruction, attachment content, chain context, questions, and answers all render as
  React text nodes / inside `<pre>` (`StartingPointCard.tsx:127,151,165,198,217,222`;
  `ClarificationsCard.tsx:111,113`). `renderClarificationsMarkdown` produces a plain string for download,
  never injected as HTML (`lib/clarifications.ts:70-84`).

### Microcopy
- **PASS** — "Starting point" / "Revision request" (`:58`), "Revision Request" micro-label (`:125`),
  "revision of v{n}" (`:108`, currently dead — see Fix 1), "Original brief (v1)" (`:140`), "From previous
  workflow" (`:194`), "No typed brief — see attachments below." (`:181`), "{name} — {n} chars" (`:217`),
  "{N} question(s) across {R} round(s)" with correct pluralization (`ClarificationsCard.tsx:57`), "★ High
  impact" / "Medium impact" (`:31,38`), "prompt.md" / "clarifications.md" (`FilesTab.tsx:59,72`). All match
  the spec's copy contract and pluralize correctly.

---

## Overall Verdict

**SHIP (23/24).** This is a cleaner result than Workstream B: the a11y lesson landed. Every expander is a
native `<button>` with `aria-expanded` + descriptive `aria-label`, chevrons are `aria-hidden`, both lazy
regions carry `aria-busy`, and impact is signalled in text — **B's stranded-listbox BLOCK and non-focusable
div-row FLAG are both absent here**, so there is **no BLOCK**. Reuse discipline is total (zero net-new visual
language, SC-001 honored, C1 parser consumed not re-authored), the timeline narrative order is correct on
both live and reopen mounts, and XSS surface is clean. The one substantive gap is a **wiring** miss, not a
visual one: the `revision of v{n-1}` chip is authored to spec but never threaded at either mount, so a
contract-mandated affordance is dead in production. Fix that thread (and, optionally, symmetrize the live
Original-brief root id) before the closing sign-off. Pixel fidelity remains deferred to a live authenticated pass.

### Findings tally
- **BLOCK: 0**
- **FLAG: 3** — `revision of v{n-1}` chip never threaded (dead affordance); live-mount Original-brief root
  id not threaded (asymmetric, graceful); Clarifications dot tint-fill vs solid (cosmetic rail nit).
- **PASS:** typography, color, spacing/layout, visual hierarchy, reuse-fidelity, all a11y §8 mandates
  (buttons/aria-expanded/aria-label/aria-hidden/aria-busy/accessible-badge-text), async/empty/lazy states,
  XSS-safety, microcopy, both-mount prop threading (runInput + clarifications), narrative order, Files
  section in both layouts + truthful count.
