# Phase 42 — Run Screen State Fidelity (kill legacy full-screen takeovers) [B8]

**Milestone:** v2.0 (Universal Run Chat & VelocityAI UI Convergence). **Branch:** `feat/ui-2`.
**Predecessors:** 31 (Chat Lane MVP), 32 (Run-Screen Redesign), 39 (Run Screen Mock Fidelity), 41 (Composer). This phase closes the run-screen STATE fidelity those phases left half-done: the inline mock-matching surfaces were built but are **shadowed** by legacy full-screen panels that were never removed.

> **How this CONTEXT was produced.** Root-caused directly in code, then a 5-agent parallel deep investigation (render-decision tree · flow wiring · legacy inventory · paused-state mock diff · active/terminal mock diff), each grounded in `file:line` + mock markup, then the orchestrator spot-checked the load-bearing claims. Treat the findings below as verified.

---

## 1. Goal & Success Criteria

Make **every run state** — planning · streaming/live · clarify · review gate · complete · **failed** · revision — match the three VelocityAI run mocks, by REMOVING the legacy full-screen right-panel takeovers so the already-built inline surfaces (Steps clarify/gate cards, header pills, review-dot, planning-in-Steps) become reachable, plus the fidelity polish the mocks require. **No net-new construction of the correct surfaces — they exist; they are pre-empted.**

**Acceptance = SCREENSHOT-DIFF against the mocks, per state, human-signed-off** (the Phase-39/41 discipline — prose claims do not close a state). Build/extend the Phase-39 fidelity gallery to cover the paused/failed/planning states.

**Mocks = SOURCE OF TRUTH** (read fully): `/Users/1000060523/Documents/Work/VelocityAI-New-UI/`
- `Hexaware Run.dc.html` (settled/complete)
- `Hexaware Run - Live.dc.html` (live: planning/streaming/clarify/gate — has per-state `sc-if` blocks: `isClarify`/`isGate`/`clarAwaiting`/etc.; comments state the intent literally, e.g. `CLARIFY — status only; the questions live in Steps` and `AWAITING: the questions are answered here, in the timeline`)
- `Hexaware Run - Failed.dc.html` (failed: `tab:'audit'` default, tabs `[steps,audit,files]` — **no Preview**, failed = red `#A33A32`)

Mock brand accent = `#3C2CDA`; warm surfaces `#FCFBF7`/`#F6F4EE`; amber `#F5EEDD`/`#9A6B1E`; failed red `#A33A32`.

---

## 2. Root cause (verified)

`components/layout/DashboardLayout.tsx` execution view (`mainView==="execution"`, ~:1716+) is a 2-column flex. LEFT = `RunChatLane` (always). RIGHT = a **priority cascade** (`:1787-1869`):
1. `PlanningOverlay` (`:1791-1796`) — running & 0 agents & no clarify & no gate
2. `<ReviewGatePanel>` (`:1797-1812`) — `reviewGateData && isPipelineRunning` — **LEGACY full-screen**
3. `<QuestionnairePanel>` (`:1813-1821`) — clarify questions/loading present — **LEGACY full-screen**
4. `<PreviewPanel>` (`:1822-1868`) — else (the ONLY host of the mock-matching Steps inline surface)

Branches 1–3 sit ABOVE `PreviewPanel`, so whenever planning/gate/clarify is active, `PreviewPanel` **never mounts** — and it is the sole host of the Steps inline clarify/gate cards, the `RunHeader` status pills, and the Steps review-dot. Net: **legacy full-screen owns the right panel; the mock-correct surfaces are dead during the very phases they were built for.** Meanwhile the lane composer ALSO renders the full answer UI → a **triple implementation** (legacy panel + lane composer + Steps). Submit channels are SHARED across all three (`submit_questionnaire` / `approve_review`) — so removal is submit-safe.

The three full-screen panels are the ONLY legacy mounts (grep-verified): `DashboardLayout.tsx:1796`, `:1798`, `:1814`.

---

## 3. The consolidated findings register (the "places")

### GROUP A — Kill the full-screen takeovers  [HIGH]
- **A1 · Remove `ReviewGatePanel` branch** `DashboardLayout.tsx:1797-1812` (+ import `:28`) → inline gate-in-Steps renders (`StepsOverviewSpine.tsx:61-103` `GateAwaitingCard`, rendered `:254-263`, fallback `:274-283`, wired via `laneGate` passthrough `:1856-1860`).
- **A2 · Remove `QuestionnairePanel` branch** `:1813-1821` (+ import `:27`) → inline clarify-in-Steps renders (`StepsOverviewSpine.tsx:197-208`, wired via `clarifyQuestions` passthrough `:1861-1863`). **RISK — re-home the "Cancel Workflow" affordance:** `handleCancelWorkflow` (`DashboardLayout.tsx:1290`) is wired ONLY to `QuestionnairePanel` (`:1820`); `InlineClarifyActions` has only `onSkipAll`. Add a cancel-workflow trigger to the inline clarify (lane + Steps) bound to the existing `handleCancelWorkflow`, OR accept Stop/skip (product decision — flag at plan).
- **A3 · Remove `PlanningOverlay` branch** `:1791-1796` (defined `:184-255`) → `PreviewPanel` keeps its tabs during planning (its `isStillRunning` path already renders the mock's streaming chrome). The mock has **no** prep overlay — planning shows as a lane phase-pill + the Steps "Running" status head. Add a planning card in the lane/Steps if needed (the `AwaitingCard` pattern is ready).
- **A4 · Delete the orphaned files** `components/preview/QuestionnairePanel.tsx` + `ReviewGatePanel.tsx` (INV-12 no-dual-impl). **KEEP all state + handlers** (they feed the inline path): `reviewGateData`, `questionnaireData`, `questionnaireQuestions`, `questionnaireLoading`, `activePipelineRunId`; the `questionnaireData→questionnaireQuestions` effect (`:650-654`); the `laneGate` mapping (`:1376-1388`); `runLaneState`/`laneClarifyOpen` (`:1354-1363`); and every submit handler (`handleQuestionnaireSubmit`, `handleLaneSubmitAnswers`, `handleQuestionnaireSkip`, `handleRejectReview`, `handleCancelWorkflow`, `onApproveReview`, `onRedoReview`, `onUpdateSpecsReview`). **SEQUENCING (load-bearing):** `ReviewGatePanel.tsx` holds the `<spec>/<tasks>/<analysis>` discriminator + the Spec/Tasks/Analysis parsers that the new artifact cards **and** the gate plan-preview (§F) reuse (§9) — so **extract those into a shared module BEFORE deleting this file**. `QuestionnairePanel.tsx` has no reusable logic → delete early (W1). `ReviewGatePanel.tsx` file-delete moves LAST (W4, after extraction). Removing the panel BRANCH from the cascade (A1) is independent of the FILE delete and still happens in W1.

### GROUP B — Auto-select the right tab per state  [HIGH]
`PreviewPanel.tsx:448` defaults `activeTab="preview"`; no effect switches to Steps on gate/clarify (`hasActiveGate`/`hasOpenClarify` at `:625-626` only drive the dot). Add a state-keyed default: **live → Steps (`"thinking"`)**, **clarify/gate → Steps**, **failed → Audit**, **settled → Preview**. Mock: Live `tab:'steps'`, Failed `tab:'audit'`. (The tab id `"thinking"` is labelled "Steps" at `:353`.)

### GROUP C — Lane composer = plain hint during clarify/gate  [HIGH]
`RunChatLane.tsx:717-746` mounts the full `InlineClarifyActions`/`InlineGateActions` in the composer — duplicating Steps. Mock composer is a plain text input with a phase hint (`composerHint`: "Answer the questions above to continue…" / "Approve the plan above, or add a note…"). Replace the clarify/gate composer cases with a `FreeTextComposer` hint input (the pattern already used for building `:901` / complete `:754`). **KEEP** the `AwaitingCard` status card (`:359-398`, `:960-991`) — it already matches the mock. Steps = the sole answer surface.

### GROUP D — Failed run: drop Preview, default Audit, red not amber  [HIGH]
`PreviewPanel` always renders 4 tabs incl. Preview (`TAB_CONFIG` `:352-355`); on failure Preview shows `DegradedRunAffordance` (amber, `:374-445`, mounted `:937`). Mock drops the Preview tab (`Run - Failed:230` tabs `[steps,audit,files]`), defaults Audit (`:194`), failed = **red** `#A33A32` (`:95`). For terminal-failure runs: remove the Preview tab + default Audit; retire `DegradedRunAffordance` on the run screen (also mounted `RunDetailPage.tsx:296` — decide history separately). The failed Steps/Audit/Files/header surfaces already match (see KEEP).

### GROUP E — Delete dead code  [MED, INV-12]
Zero mounts, superseded/never-wired: **`AgentProgressPanel`** (`components/workflow/AgentProgressPanel.tsx` + test — controls absorbed into RunChatLane), **`WaveTreePanel`** (`components/workflow/WaveTreePanel.tsx` — superseded by `AgentDetailPanel`'s inline tree, Phase 39), **`TodoCard`** (`components/chat/blocks/TodoCard.tsx` — no `todo` block kind emitted; ISS-037). Delete component + test; fix the stale comments (`DashboardLayout.tsx:1781-1784`, `app/dashboard/page.tsx:115`).

### GROUP F — Gate fidelity  [MED]
Mock gate = **two** buttons ("Approve & build" / "Request changes") + a **task-plan preview** block (`Run - Live:269-278`, detail `:482-491`). We render 4–5 (`InlineGateActions.tsx`: Edit `:152`, Approve `:181`, Update-Specs `:194`, Redo `:208`, Reject 2-step `:247`). Collapse redo/update-specs/reject under a single "Request changes" affordance; add the plan-preview block. (Preserve the underlying redo/update-specs/reject CHANNELS — just restructure the UI.)

### GROUP G — Steps header + clarify copy + extras  [MED]
- Steps overview header (`StepsOverviewSpine.tsx:133,170`) only shows "Running/Run complete/Run failed" — add the mock's phase **pill** (CLARIFY/REVIEW/BUILDING, `Run - Live:981`) + phase **label** ("Waiting on your answers" / "Paused for your approval" / "Pipeline running · N/M").
- Clarify submit copy `InlineClarifyActions.tsx:243` "Send answers" → mock "**Submit answers & start the build**" (`Run - Live:229`).
- Drop the extra clarify affordances the mock omits (`InlineClarifyActions.tsx:185-254`: per-question Skip / "Use recommended" / "Rec." badge / "Anything else?" freeform / "Skip all") — OR register them as intended divergences.

### GROUP H — Live-state polish  [MED/LOW]
- Running spine row (`StepsOverviewSpine.tsx:246`): drop the Zap "Live" badge; add the mock's violet running-row highlight (`background:#F4F2FB, border:#DED9F7`) + node glow (`Run - Live:924,928`). Keep the "LIVE" pill in the L2 detail header only.
- Files hero (`FilesTab.tsx:645-681`): add a **building** variant (spinner + "task 4 of 7 · not yet validated" + top progress bar, suppress Download/Download-All) while `pipelineState.isRunning` (`Run - Live:564-575`).
- Live Audit (`AuditTab.tsx`): add pulsing "live" badge + "in progress" elapsed + violet "monitoring live" banner (`Run - Live:623,649,662`).
- Settled agent-detail (`AgentDetailPanel.tsx:548-591`): the mock adds per-agent artifact cards (pages/tasks/checks) + a handoff note (`Run:389-476,534-559`). **RESOLVED (decision 2): BUILD them — generic + frontend-only.** Verified data path, reuse plan, and the two brittle-parse follow-ups are in §9. The Build-Agent construction card already exists (§4 KEEP) and is out of scope.

### GROUP I — Reskin the inline clarify/gate/result cards to brand tokens  [MED]
`InlineClarifyActions.tsx` (`:144,171,177,240`), `InlineGateActions.tsx` (`:146,159,186,200,226,268`), `ResultCard.tsx` (`:65,141`) still use retired navy `#1B2A4A` + raw gray/blue/red/violet/amber. Because these render inside the Steps `AwaitingCard`, there is a visible token-header/navy-body seam. Route through the Phase-32 token layer (`bg-brand` / `border-brand-border` / `text-brand`, mock accent `#3C2CDA`). (This is part of the deferred Phase-35+ palette campaign but is load-bearing for THIS phase's surfaces.) Do NOT touch user-facing font/color OPTIONS in `TweaksPanel.tsx` (they are content values).

---

## 4. KEEP — already mock-faithful, do NOT touch (INV-3 / no-regression)
Lane status cards (`RunChatLane` `AwaitingCard` clarify `:960`, gate `:975`); RunHeader status pills (`:212-232`); Steps inline card chrome (highlight ring `:55`, "Awaiting you" badge, settled "Review gate — {gate} · approved" strip `:108-121`); the **failed lane** (`RunChatLane:803-869` — What-went-wrong + Resume options + change-composer); Steps failed rows + "Pipeline halted" banner (`:163-247,286-294`); Files "Build incomplete" banner (`:710-722`); Audit "governance stopped this run" verdict (`:723-741`); RunHeader red failed badge (`:188-195`); `LaneRunHeader`; `AgentDetailPanel` 2-col + sticky Context-received + reasoning caret + construction block; `VersionMenu` + `ReadOnlyVersionBanner`; `PreviewChrome`; settled Files + Audit. `PrototypePipelineView`/`LiveVersionChip`/`RendererSwitcher` are already deleted.

---

## 5. Proposed waves (refine at plan)
- **W0 · Fidelity harness** — extend the Phase-39 gallery (`frontend/e2e/fidelity/`) to drive our screen through planning/clarify/gate/failed/live via mocked-WS + capture side-by-side vs the mocks (the acceptance oracle).
- **W1 · Kill the takeovers (A) + auto-tab (B)** — the core unshadowing; re-home Cancel-Workflow (A2 risk). Removes the three panel BRANCHES + deletes `QuestionnairePanel.tsx`; the `ReviewGatePanel.tsx` FILE-delete defers to W4 (its parsers are extracted there first, §9). Per-state screenshot sign-off (clarify, gate, planning).
- **W2 · Lane composer hint (C) + failed tab/Audit-default + retire DegradedRunAffordance (D)** — sign-off failed + paused composer.
- **W3 · Delete dead code (E)** — AgentProgressPanel/WaveTreePanel/TodoCard + stale comments + tests.
- **W4 · Fidelity polish + artifact cards** — in dependency order:
  (a) **Extract the shared artifact-preview module** — the `<spec>/<tasks>/<analysis>` name-free discriminator + the Spec/Tasks/Analysis parsers — OUT of `ReviewGatePanel.tsx` into `components/results/` (e.g. `artifactPreview.tsx`), then delete `ReviewGatePanel.tsx` (completes §A4). One parser, ≥2 consumers (INV-12).
  (b) **Gate = 2 buttons + plan-preview** (F), the preview reusing (a).
  (c) **Settled agent-detail artifact cards** (§9, decision 2): pages/sections · tasks · checks + handoff line, in `AgentDetailPanel.tsx`. Card TYPE keyed on the (a) discriminator; tasks from `protoCompletedTasks`, handoff from `dagEdges`/agent-order, checks-badge from `validation*` — all generic + conditional (no card when the artifact kind is absent).
  (d) Steps pills + copy + **drop the extra clarify affordances** (G).
  (e) Running-row highlight + Files-building hero + live-Audit (H).
  (f) Inline reskin navy→brand (I).
  Per-surface screenshot sign-off. Register the two brittle-parse follow-ups (§9).
- **W5 · Gallery regen + full per-state human sign-off + register/ISSUES reconcile** (incl. ISS-035/036 stale-OPEN).

---

## 6. Invariants & constraints (do NOT violate)
- **SC-001 / INV-1** — every render branch keys on generic state/props (`runState`, `laneGate`, `clarifyQuestions`, `artifactKind`), NEVER a workflow-name/agent-id literal.
- **INV-3 / LOCK-B** — FRONTEND-ONLY; zero backend / `useWorkflow` / `useRunStream` / transport / manifest / golden changes. The 5 characterization goldens stay byte/event-identical by construction.
- **INV-12 / no dual implementation** — removing the legacy panels + dead components is the point; collapse the triple answer-UI to the Steps mount + lane status card. No new dual surface.
- **Reskin-look, keep-behavior (D-15)** — reuse the existing inline components; do NOT rebuild from the mock's hardcoded/inert values. Bind to LIVE data (the mock's "6 questions", fixed transcript are fiction).
- **Screenshot-diff acceptance** — per-state human sign-off against the mocks via the fidelity gallery; NOT prose (the discipline that stopped 12 phases of drift before Phase 39). Intended divergences go in an ND register.
- **Submit channels are shared** — keep `submit_questionnaire` / `approve_review {approved/action}` intact; do not touch the handlers.

## 7. Negative space / forbidden
- Do NOT touch the KEEP surfaces (§4) toward the mock — they already match; a diff there is a regression.
- Do NOT break the submit channels or delete the state that feeds the inline path (§A4).
- Do NOT drop the "Cancel Workflow" affordance silently (§A2).
- Do NOT reskin `TweaksPanel` font/color OPTIONS (content, not chrome).
- FE-only; `feat/ui-2`; no push without explicit go-ahead; no commit trailer.

## 8. Scope decisions — RESOLVED (2026-07-14, user-confirmed)
1. **Cancel-Workflow during clarify → RE-HOME.** Bind the existing `handleCancelWorkflow` (`DashboardLayout.tsx:1290`) to a "Cancel workflow" affordance on the inline clarify (lane status card + Steps `InlineClarifyActions`). Do NOT drop it silently. (§A2)
2. **Settled agent-detail artifact cards → BUILD (generic, frontend-only).** User decision: do not defer. All three cards + the handoff line are frontend-feasible with zero backend/golden change — verified data path in §9. Keyed on the generic artifact discriminator, never a workflow/agent name. Two output-parses are brittle (pages, coverage-%) → registered follow-ups (§9). (§H)
3. **Extra clarify affordances → REMOVE.** Drop the per-question Skip / "Use recommended" / "Rec." badge / "Anything else?" freeform / "Skip all" (`InlineClarifyActions.tsx:185-254`) to match the mock's single "Submit answers & start the build". (§G)
4. **`DegradedRunAffordance` on the history reopen surface (`RunDetailPage.tsx:296`) → OUT OF SCOPE.** This phase retires it on the RUN screen only; the history/reopen view is untouched (separate surface). (§D)

---

## 9. Artifact-card data path — VERIFIED (frontend-only) [decision 2]

Two read-only investigations (FE data-path + BE event/REST vocabulary), orchestrator spot-checked (FE claims re-verified in code). **Conclusion: the four card elements build FRONTEND-ONLY — no engine / golden / transport change is forced.** The card TYPE is chosen by the existing **name-free discriminator** already SC-001-audited at `ReviewGatePanel.tsx:270-273` (`artifactKind === "spec" || /<spec[\s>]/i.test(output)`, likewise `<tasks>`/`<analysis>`): `<spec>` → pages/sections card, `<tasks>` → tasks card, `<analysis>` → checks card. **Never an agent-name/id literal.**

| Card element | FE source (file:line) | Verdict | Note |
|---|---|---|---|
| **tasks** | `pipelineState.protoCompletedTasks{number,title,summary}[]` + `protoCompletedTaskCount` (`types/index.ts:605-606`; reducer `useWorkflow.ts:774-780`) | IN_STATE, clean | Same data the construction card consumes. **Empty for `single_shot` workflows** — only `task_loop` steps emit tasks (BE) → card renders only when tasks exist (correct, generic). |
| **checks — badge/rows** | `agent.validationPassed` / `validationIssues` (`types/index.ts:543-544`; reducers `useWorkflow.ts:814-864`); fuller rows via REST `GET /runs/{id}/validation-results` (already fetched by AuditTab) | IN_STATE + REST, clean | Pass/fail + issues are structured; no engine change. |
| **checks — coverage % / verdict text** | parse analyzer `agent.output` `<analysis>` + `### Readiness verdict` (reuse `AnalysisPreview`) | DERIVABLE, **BRITTLE** | Structured coverage-% is genuinely ABSENT — grep-empty in REST **and** the WS stream (both agents). **Follow-up F1 (post-phase, additive-safe): compute a `{coverage,counts{P0..P3}}` aggregate on `GET /runs/{id}/validation-results` — event-free persist+REST, goldens untouched.** |
| **pages / sections** | parse spec `agent.output` `<spec>` → `## ` headings (reuse `SpecPreview` `ReviewGatePanel.tsx:57-102`) | DERIVABLE, **BRITTLE** | Generic as "spec sections"; the mock's "pages" are just this prototype spec's sections. A fully-typed generic extractor = a per-`deliverable.strategy` capability. **Follow-up F2 (post-phase): additive event-free `sections` extractor + `/artifacts?kind=sections`.** |
| **handoff line** | `pipelineState.dagEdges{from,to,artifact_type}[]` (`types/index.ts:603`; reducer `useWorkflow.ts:805-810`); fallback `agents[index+1].name` (ordered, `useWorkflow.ts:235-246`) | IN_STATE, clean, SC-001 | `dagEdges` gives producer→consumer + artifact label ("Validated plan"); may be absent on prototype (skips planner) → order fallback always holds. |

**Reuse / no-dual-impl (INV-12) — load-bearing:** the parsers the cards need (`SpecPreview` `ReviewGatePanel.tsx:57-102`, `TasksPreview` `:104-160`, `AnalysisPreview` `:~170-200`) live inside `ReviewGatePanel.tsx`, which §A4 deletes. **Extract them + the discriminator into a shared module FIRST** (W4-a), then the settled artifact cards **and** the gate plan-preview (§F) both consume it; delete `ReviewGatePanel.tsx` last. No orphaned logic, no second copy.

**Cards are conditional + degrade generically:** an agent whose output carries no recognized artifact tag renders exactly as today (reasoning · context · tools · input · output) with no card — so non-prototype / `single_shot` workflows are unaffected (SC-001).

**Registered follow-ups (do NOT build this phase — they are backend/additive, out of the FE-only fence):** F1 structured coverage/counts aggregate on `/validation-results`; F2 event-free `sections` extractor capability. Until then the pages + coverage-% cards parse agent output and are flagged brittle (not silently shipped as robust).
