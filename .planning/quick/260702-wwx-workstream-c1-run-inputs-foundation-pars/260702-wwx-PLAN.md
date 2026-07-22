---
phase: 260702-wwx
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/lib/runInput.ts
  - frontend/src/lib/runInput.test.ts
  - frontend/src/components/history/RevisionFamilyView.tsx
  - frontend/src/lib/api.ts
  - frontend/src/lib/api.getRunArtifacts.test.ts
  - frontend/src/types/index.ts
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/hooks/useWorkflow.ts
  - frontend/src/hooks/useWorkflow.clarifyRetention.test.ts
  - frontend/src/app/dashboard/page.tsx
autonomous: true
requirements:
  - C1-parser          # POR §6.1 — shared parseRunInput marker parser
  - C1-artifacts-fetch  # POR §6.6 — getRunArtifacts fetcher (first FE consumer of A's kind filter)
  - C1-clarify-types    # POR §6.5 — ClarifyRound type + PipelineRunState.clarifications
  - C1-live-retention   # POR §6.2/§6.5 — submittedBrief + clarify round survive per run
  - INV-12              # one parser project-wide (net-negative dup removal)
  - INV-3               # zero backend edits by construction

user_setup: []

must_haves:
  truths:
    - "parseRunInput decomposes a 2-attachment brief into a clean `brief` + `attachments[2]` (name+content), and an inline-revision blob (`=== EXISTING PROTOTYPE HTML ===` + `=== REVISION REQUEST ===`) into `revisionInstruction` set + `existingArtifactBlock` set + `brief===''`."
    - "A clean instruction-only string or a plain brief with no markers passes through parseRunInput unchanged as `brief` (format-tolerant); a chained input yields `chainContext`, a `=== USER PREFERENCES ===` blob yields `preferences`."
    - "getRunArtifacts issues `GET /api/runs/{id}/artifacts` with `?kind=` and `?include=content` query params and a `Bearer` token, returning the `{ workflow_id, artifacts }` shape (ArtifactNode has no created_at)."
    - "On the live clarify path, after handleQuestionnaireSubmit the answered Q&A survives the questionnaire panel clearing as a ClarifyRound reachable by C2's ClarificationsCard (POR §3 gap-3 closed); clarifications reset to empty at the start of a fresh run."
    - "submittedBrief is captured on the live onStartPipeline launch path and reset per run (previously dropped)."
    - "REGRESSION GUARD: the DashboardLayout chain sites and the RevisionFamilyView instruction-preview shim delegate to parseRunInput with NO behavior change — WorkflowHistory.{family,test,revise,genericReopen} + DashboardLayout.{catalogHome,waveMount} stay green."
    - "INV-12 one-parser: the inline safeCleanBrief/`=== REVISION REQUEST ===` regex logic in DashboardLayout and the marker-scanning body of extractRevisionInstructionPreview are deleted/delegated — parseRunInput is the single project-wide marker parser (no duplicate parser remains)."
  artifacts:
    - path: "frontend/src/lib/runInput.ts"
      provides: "parseRunInput + ParsedRunInput — single home for all FE-owned marker families"
      exports: ["parseRunInput", "ParsedRunInput"]
      min_lines: 40
    - path: "frontend/src/lib/runInput.test.ts"
      provides: "parser family unit tests (plain / attachments / revision blob / chain / preferences / instruction-only)"
    - path: "frontend/src/lib/api.ts"
      provides: "getRunArtifacts fetcher + RunArtifactsResponse/ArtifactNode types"
      contains: "getRunArtifacts"
    - path: "frontend/src/lib/api.getRunArtifacts.test.ts"
      provides: "fetch-mock test asserting URL + query params + Bearer + parsed shape"
    - path: "frontend/src/types/index.ts"
      provides: "ClarifyRound type + PipelineRunState.clarifications?"
      contains: "ClarifyRound"
    - path: "frontend/src/hooks/useWorkflow.ts"
      provides: "retainClarifyRound append + reset-on-fresh-run"
      contains: "retainClarifyRound"
    - path: "frontend/src/hooks/useWorkflow.clarifyRetention.test.ts"
      provides: "hook test: round appended survives, reset on fresh run"
    - path: "frontend/src/components/history/RevisionFamilyView.tsx"
      provides: "extractRevisionInstructionPreview delegates to parseRunInput"
    - path: "frontend/src/components/layout/DashboardLayout.tsx"
      provides: "chain sites rewired to parseRunInput + clarify fold before panel clear"
    - path: "frontend/src/app/dashboard/page.tsx"
      provides: "submittedBrief capture/reset + onRetainClarifyRound wiring"
  key_links:
    - from: "frontend/src/components/layout/DashboardLayout.tsx"
      to: "frontend/src/lib/runInput.ts"
      via: "parseRunInput import replacing inline safeCleanBrief"
      pattern: "parseRunInput"
    - from: "frontend/src/components/history/RevisionFamilyView.tsx"
      to: "frontend/src/lib/runInput.ts"
      via: "extractRevisionInstructionPreview delegates"
      pattern: "parseRunInput"
    - from: "frontend/src/lib/api.ts"
      to: "GET /api/runs/{id}/artifacts"
      via: "getRunArtifacts fetch"
      pattern: "runs/.*artifacts"
    - from: "frontend/src/components/layout/DashboardLayout.tsx"
      to: "frontend/src/hooks/useWorkflow.ts"
      via: "onRetainClarifyRound folds Q&A into pipelineState.clarifications before questionnaire clear"
      pattern: "onRetainClarifyRound"
---

<objective>
Deliver Workstream-C1 — the FRONTEND-ONLY plumbing that C2 (StartingPointCard + ClarificationsCard + Files rows) consumes to surface the original brief and clarify Q&A. This plan ships the shared marker parser, the artifacts fetcher, the clarify types, and the live-retention state — NO visual cards, NO Files rows, NO backend edits.

Three foundations, per the Plan of Record (`.planning/REVISION-FAMILY-AND-RUN-INPUTS-PLAN.md` §6 items 1/2/5/6 and §7 the parseRunInput contract):
1. `lib/runInput.ts` — `parseRunInput(input) -> { brief, attachments[], revisionInstruction?, existingArtifactBlock?, chainContext?, preferences? }`: the SINGLE home for every FE-owned marker family (per §7 every format is FE-composed, so parsing is exact, not heuristic). This REPLACES the duplicated `safeCleanBrief`/`=== REVISION REQUEST ===` logic in DashboardLayout and DELEGATES B2's `extractRevisionInstructionPreview` shim — one parser project-wide (INV-12 net-negative).
2. `getRunArtifacts` fetcher + `RunArtifactsResponse`/`ArtifactNode` types — the FIRST FE consumer of Workstream-A's `?kind=` filter on `GET /api/runs/{id}/artifacts` (shipped 260702-s3p).
3. `ClarifyRound` type + `PipelineRunState.clarifications?` + LIVE retention: the answered Q&A must survive the questionnaire panel unmount (today it is wiped — POR §3 gap-3), and the submitted brief must survive the launch (today it is dropped — POR §1 gap-2).

Purpose: unblock C2 with the exact parser + fetcher + types + retained state it renders, without introducing a second parser or any new storage (INV-12).
Output: 1 new lib (+ test), api.ts + types extensions (+ test), retention wiring across DashboardLayout/useWorkflow/page.tsx (+ test), and the RevisionFamilyView shim delegating to the one parser.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/REVISION-FAMILY-AND-RUN-INPUTS-PLAN.md
@CLAUDE.md

# The parser contract, exact marker formats, and the shim hand-off:
@frontend/src/components/workflow/IdeaInputPage.tsx        # :542 the `=== Attached: {name} === … === End: {name} ===` format
@frontend/src/components/history/RevisionFamilyView.tsx     # :367-393 extractRevisionInstructionPreview shim (delegate); :452 call site
@frontend/src/components/layout/DashboardLayout.tsx         # :931-947 & :1015-1024 safeCleanBrief dup (rewire); :289-293 questionnaireQuestions shape; :1055-1072 handleQuestionnaireSubmit new-flow clarify fold; :496-548/:1278-1307 EXISTING/REVISION marker families
@frontend/src/lib/api.ts                                    # :79-101 request<T> + authHeaders; :333-354 getWorkflow/getRunFamily analog; :300-313 normalizeWorkflowRun
@frontend/src/types/index.ts                               # :522-533 PipelineRunState (extend with clarifications?)
@frontend/src/hooks/useWorkflow.ts                          # :15-46 INITIAL_STATE + startPipeline fresh state (reset boundary); :122-132 submitQuestionnaire; :136-143 hook return
@frontend/src/app/dashboard/page.tsx                        # :1298-1320 onStartPipeline wrapper (capture submittedBrief); wiring down to DashboardLayout
@frontend/src/lib/api.getRunFamily.test.ts                  # fetch-mock idiom to clone for getRunArtifacts test
@frontend/src/lib/workflowChaining.test.ts                  # pure-lib vitest idiom to clone for runInput.test.ts
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Shared parseRunInput parser + RevisionFamilyView shim delegation (INV-12 one parser)</name>
  <files>frontend/src/lib/runInput.ts, frontend/src/lib/runInput.test.ts, frontend/src/components/history/RevisionFamilyView.tsx</files>
  <behavior>
    parseRunInput(input: string): ParsedRunInput where
    ParsedRunInput = { brief: string; attachments: { name: string; content: string }[]; revisionInstruction?: string; existingArtifactBlock?: string; chainContext?: string; preferences?: string }.
    Marker families (all FE-composed, exact — see the source anchors, formats stable since Phase 3):
    - Attachment (symmetric name): `=== Attached: {name} ===` newline {content} newline `=== End: {name} ===` -> push { name, content } (content trimmed of the trailing newline), and STRIP the whole block from brief. Support multiple attachments.
    - Existing base (ASYMMETRIC label — open `=== EXISTING {X} ===`, close `=== END EXISTING {Y} ===`, X != Y e.g. `EXISTING PROTOTYPE HTML` / `END EXISTING HTML`) -> existingArtifactBlock = inner content; stripped from brief.
    - Revision request: `=== REVISION REQUEST ===` newline {instruction}, closing at `=== END REQUEST ===` OR the next line beginning with `===` OR EOF (format-TOLERANT — an UNCLOSED block still yields the instruction; the B2 shim test feeds `=== REVISION REQUEST ===` + newline + `make the header blue` with no close) -> revisionInstruction = inner (trimmed); stripped from brief.
    - Chain context: `=== CONTEXT FROM PREVIOUS PIPELINE ({type}) ===` newline {content} newline `=== END PREVIOUS CONTEXT ===` -> chainContext = block content; stripped from brief.
    - User preferences: `=== USER PREFERENCES ===` newline {lines} newline `=== END PREFERENCES ===` -> preferences = inner; stripped from brief.
    - brief = the remaining user-authored text after stripping ALL recognized blocks, trimmed.
    Test cases (real behavior, clone the workflowChaining.test.ts pure-lib idiom):
    - Plain brief, no markers -> { brief: <unchanged>, attachments: [] }; optional fields undefined.
    - Brief + 2 `=== Attached ===` blocks -> brief clean (attachment text removed), attachments.length === 2 with correct name+content.
    - Inline-revision blob (`=== EXISTING PROTOTYPE HTML ===` + <html> + `=== END EXISTING HTML ===` + `=== REVISION REQUEST ===` + <instruction> + `=== END REQUEST ===`) -> revisionInstruction === '<instruction>', existingArtifactBlock contains '<html>', brief === ''.
    - Chained input with `=== CONTEXT FROM PREVIOUS PIPELINE (prototype) ===` -> chainContext set, brief = the leading text.
    - `=== USER PREFERENCES ===` blob -> preferences set.
    - Clean instruction-only string (post-Phase-D shape, no markers) -> brief unchanged, no revisionInstruction.
    - RevisionFamilyView delegation (behavior-preserving): extractRevisionInstructionPreview(input) now DELEGATES — its body computes parseRunInput(input).revisionInstruction (falling back to parseRunInput(input).brief when no revision block), then keeps the EXISTING preview formatting: first non-empty non-marker line, clamped to 60 chars + ellipsis. The existing B2 timeline test (WorkflowHistory.family.test.tsx — input `=== REVISION REQUEST ===` + `make the header blue`, asserts /make the header blue/) MUST still pass. Keep the same exported signature + the :452 call site unchanged.
  </behavior>
  <action>
    Create `frontend/src/lib/runInput.ts` exporting the ParsedRunInput type and parseRunInput, implementing all six marker families above as an EXACT (non-heuristic) parser per POR §7. Write `frontend/src/lib/runInput.test.ts` first (RED) with the seven cases in the behavior block, cloning the pure-lib vitest idiom from workflowChaining.test.ts (no DOM). Then in RevisionFamilyView.tsx replace the marker-scanning body of extractRevisionInstructionPreview (:371-393 — the MARKER/indexOf/line-collect logic) with a thin delegation to parseRunInput (keep the first-meaningful-line + 60-char clamp preview formatting, keep the exported name and the :452 call site). This is the INV-12 net-negative: one parser project-wide, no second copy. Do NOT create any StartingPointCard/ClarificationsCard/Files rows (C2). Do NOT touch DashboardLayout in this task (Task 3 owns the chain-site rewire).
  </action>
  <verify>
    <automated>cd frontend && npx vitest run src/lib/runInput.test.ts src/components/history/WorkflowHistory.family.test.tsx 2>&1 | tail -20</automated>
  </verify>
  <done>runInput.test.ts green (all seven parser cases); WorkflowHistory.family.test.tsx still green (`make the header blue` preview preserved); RevisionFamilyView imports parseRunInput and its shim body no longer scans markers manually (`grep -c 'MARKER = ' frontend/src/components/history/RevisionFamilyView.tsx` === 0).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: getRunArtifacts fetcher + RunArtifactsResponse/ArtifactNode + ClarifyRound types</name>
  <files>frontend/src/lib/api.ts, frontend/src/lib/api.getRunArtifacts.test.ts, frontend/src/types/index.ts</files>
  <behavior>
    getRunArtifacts(token, runId, opts?: { kind?: string; includeContent?: boolean }): Promise<RunArtifactsResponse> ->
    GET /api/runs/{runId}/artifacts, appending `?kind={kind}` when opts.kind is set and `include=content` when opts.includeContent is true (build query with URLSearchParams; both/either/neither compose), using the authHeaders(token) Bearer idiom (clone getWorkflow/getRunFamily, :333-354). Returns the raw wire shape verbatim like getRunFamily/getChainContext (unnormalized).
    RunArtifactsResponse = { workflow_id: string; artifacts: ArtifactNode[] } where
    ArtifactNode = { id: string; kind: string; producer_step: string; producer_agent: string; task_id: string; content_hash: string; version: number; visibility: string; location: string; parents: string[]; derived_from: string[]; children: string[]; content?: string } — mirrors the backend node shape (runs.py:590-608); content present ONLY with include=content; NOTE: nodes have NO created_at.
    ClarifyRound = { round: number; qa: { question_id: string; question_text: string; impact_level: string; answer: string | null }[] } in types/index.ts (mirrors the backend kind="clarifications" artifact content: JSON list of {question_id, question_text, impact_level, answer, round}, grouped by round).
    PipelineRunState (types/index.ts :522) gains `clarifications?: ClarifyRound[]`.
    Test (clone api.getRunFamily.test.ts fetch-mock idiom): getRunArtifacts with { kind: 'clarifications', includeContent: true } -> the fetched URL String() contains `/api/runs/{id}/artifacts`, `kind=clarifications`, and `include=content`; options.method === 'GET'; Authorization === 'Bearer {tok}'; returns the parsed { workflow_id, artifacts } shape with an ArtifactNode carrying content. A second case with no opts -> URL has no query string (byte-identical no-param path).
  </behavior>
  <action>
    In api.ts add the RunArtifactsResponse/ArtifactNode interfaces and the getRunArtifacts fetcher next to getRunFamily (:346), using request<RunArtifactsResponse> + authHeaders and URLSearchParams for the query (mirror getWorkflows' `if (qs) path += ...` pattern). In types/index.ts add the ClarifyRound interface and extend PipelineRunState with `clarifications?: ClarifyRound[]`. Write api.getRunArtifacts.test.ts (RED first) cloning api.getRunFamily.test.ts. This is the first FE consumer of Workstream-A's kind filter (260702-s3p) — no backend edits.
  </action>
  <verify>
    <automated>cd frontend && npx vitest run src/lib/api.getRunArtifacts.test.ts 2>&1 | tail -15</automated>
  </verify>
  <done>api.getRunArtifacts.test.ts green (URL + kind + include=content + Bearer asserted, {workflow_id, artifacts} parsed, no-param path clean); ClarifyRound + PipelineRunState.clarifications compile-visible for Task 3.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Live retention (submittedBrief + clarify round) + DashboardLayout chain-site rewire to parseRunInput</name>
  <files>frontend/src/hooks/useWorkflow.ts, frontend/src/hooks/useWorkflow.clarifyRetention.test.ts, frontend/src/components/layout/DashboardLayout.tsx, frontend/src/app/dashboard/page.tsx</files>
  <behavior>
    Clarify round retention (POR §3 gap-3 — the Q&A survives the panel unmount):
    - useWorkflow exposes retainClarifyRound(round: ClarifyRound) that appends the round to pipelineState.clarifications (setPipelineState(prev => ({ ...prev, clarifications: [ ...(prev.clarifications ?? []), round ] }))). The fresh-run boundary (startPipeline's fresh state object at :39, and INITIAL_STATE) resets clarifications to empty — a new live run starts with no rounds. Justification for placement: clarifications live in PipelineRunState (per the type spec + frontmatter) because C2's ClarificationsCard already reads pipelineState on the live path, and the fresh-state reset in startPipeline is the single canonical per-run boundary; the pipeline_start WS echo spreads prev (downstream of startPipeline) so the reset holds.
    - Hook test (renderHook, clone useWorkflow.reconnect.test.ts idiom): after startPipeline then retainClarifyRound(r1) then retainClarifyRound(r2), pipelineState.clarifications === [r1, r2]; after a second startPipeline, pipelineState.clarifications is empty (reset per run).
    - DashboardLayout.handleQuestionnaireSubmit (new-flow branch, :1057-1071): BEFORE setQuestionnaireQuestions([]) at :1068, map the current questionnaireQuestions + the built responses (+ freeform when present) into a ClarifyRound { round: (pipelineState.clarifications?.length ?? 0) + 1, qa: [{ question_id: q.id, question_text: q.question, impact_level: q.impactLevel ?? '', answer: <matching response.answer or null> }, ...] } and call the new onRetainClarifyRound?.(round) prop. Order matters — fold THEN clear.
    submittedBrief retention (POR §1 gap-2 — the live brief is otherwise dropped):
    - page.tsx onStartPipeline wrapper (:1298): capture the launch message into a submittedBrief state (useState), reset per run (set it on every launch; the wrapper already distinguishes revision vs fresh — capture on both, it is the run's input either way). This covers the LIVE path only; reopen/history already have fullRun.input / selectedRun.input.
    DashboardLayout chain-site rewire (INV-12 net-negative):
    - Replace the two inline safeCleanBrief IIFEs + `=== REVISION REQUEST ===` regexes in handleChainPipeline (:931-947) and handleChainFromHistory (:1015-1024) with parseRunInput(...): cleanBrief becomes parseRunInput(input).revisionInstruction ?? parseRunInput(input).brief (parse once, reuse) — behavior-preserving: a plain brief -> its brief; a revision blob starting with `===` -> the revision instruction (the empty-string fallback path is subsumed by parseRunInput returning brief='' for a pure revision blob). Delete the now-dead safeCleanBrief helpers. The chain contextBlock composition stays as-is.
  </behavior>
  <action>
    In useWorkflow.ts: add `clarifications: []` to INITIAL_STATE and the startPipeline fresh-state object; add the retainClarifyRound callback and include it in the hook return + UseWorkflowReturn type. Write useWorkflow.clarifyRetention.test.ts (RED first, renderHook). In page.tsx: add submittedBrief state, capture message in the onStartPipeline wrapper (:1298), thread onRetainClarifyRound={retainClarifyRound} and (optionally) submittedBrief down to DashboardLayout — but DO NOT render any card (C2 consumes these; C1 only wires the state to be reachable). In DashboardLayout.tsx: add the onRetainClarifyRound? prop to the component props type; fold the ClarifyRound in handleQuestionnaireSubmit's new-flow branch BEFORE setQuestionnaireQuestions([]); import parseRunInput and rewire both chain sites, deleting the safeCleanBrief helpers. Match the surrounding style; NO new visual language. Because DashboardLayout is a huge file whose internal call-order wiring cannot be cheaply unit-driven, source-lock the two invariants (fold-before-clear order; parseRunInput replaces safeCleanBrief) via the grep gates in verify — the runtime retention/reset behavior is proven at the useWorkflow hook level.
  </action>
  <verify>
    <automated>cd frontend && npx vitest run src/hooks/useWorkflow.clarifyRetention.test.ts 2>&1 | tail -15 && echo "--- INV-12 net-negative ---" && test $(grep -c 'safeCleanBrief' src/components/layout/DashboardLayout.tsx) -eq 0 && grep -q 'parseRunInput' src/components/layout/DashboardLayout.tsx && grep -q 'onRetainClarifyRound' src/components/layout/DashboardLayout.tsx && grep -q 'submittedBrief' src/app/dashboard/page.tsx && echo INV12_OK</automated>
  </verify>
  <done>useWorkflow.clarifyRetention.test.ts green (round appended + survives, reset on fresh run); INV12_OK printed (safeCleanBrief count 0, parseRunInput + onRetainClarifyRound wired in DashboardLayout, submittedBrief in page.tsx).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser FE -> `GET /api/runs/{id}/artifacts` | getRunArtifacts crosses the client->API boundary carrying a Bearer JWT; the endpoint is owner-scoped (Workstream A, 260702-s3p: 404-not-403 on foreign/missing runs). C1 is a pure consumer — it adds no new server authz surface. |
| WS event -> pipelineState.clarifications | clarify Q&A folded from FE-held state into run-scoped React state; never sent back to the server (INV-12: clarifications single-sourced in existing refs; retention is display-only). |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-wwx-01 | Information Disclosure | getRunArtifacts fetch of a foreign run id | accept | Server enforces owner-scope (404 on non-owned); FE fetcher passes the caller's Bearer only — no client-side authz to bypass. No new exposure vs the existing getRunFamily/getWorkflow fetchers. |
| T-wwx-02 | Tampering | parseRunInput parsing attacker-influenced `run.input` markers | mitigate | Parser is exact string-slicing over FE-composed markers, no eval/DOM-injection; output is plain strings rendered by C2 later (React escapes). Malformed/partial markers degrade to `brief` (format-tolerant), never throw. |
| T-wwx-03 | Denial of Service | pathological giant `run.input` (60k+ inline base) through the parser | accept | Bounded, single-pass regex/slice over an already-capped input (ATTACH_MAX_CHARS / 40k-60k slice at compose time); no catastrophic backtracking (anchored `[\s\S]*?` with fixed delimiters). |
| T-wwx-SC | Tampering | npm/pip/cargo installs | accept | Zero new dependencies — parser, fetcher, types, retention use only existing React/vitest/URLSearchParams. No install task, no package-legitimacy gate needed. |
</threat_model>

<verification>
Run from the repo root unless noted.

1. **TypeScript identity gate (COUNT==3, filtered==0):** the 3 known pre-existing tsc errors (mockApi + IdeaInputPage) must persist unchanged and NO new error may appear:
   `cd frontend && ERRS=$(npx tsc --noEmit 2>&1 | grep -E "error TS" || true); TOTAL=$(printf '%s\n' "$ERRS" | grep -c "error TS"); NEW=$(printf '%s\n' "$ERRS" | grep -vE "mockApi|IdeaInputPage" | grep -c "error TS"); echo "total=$TOTAL new=$NEW"; [ "$TOTAL" -eq 3 ] && [ "$NEW" -eq 0 ] && echo GATE_OK`
   Expect: `GATE_OK` (tsc emits file(line,col) — verify by identity, not eyeballing).

2. **New/touched specs green:**
   `cd frontend && npx vitest run src/lib/runInput.test.ts src/lib/api.getRunArtifacts.test.ts src/hooks/useWorkflow.clarifyRetention.test.ts 2>&1 | tail -20`

3. **REGRESSION GUARD (the B2/B3 lesson — parseRunInput replaces DashboardLayout parsing + the RevisionFamilyView shim, so the suites that render them must stay green):**
   `cd frontend && npx vitest run src/components/history/WorkflowHistory.family.test.tsx src/components/history/WorkflowHistory.test.tsx src/components/history/WorkflowHistory.revise.test.tsx src/components/history/WorkflowHistory.genericReopen.test.tsx src/components/layout/DashboardLayout.catalogHome.test.tsx src/components/layout/DashboardLayout.waveMount.test.tsx 2>&1 | tail -25`
   Expect: all green. Known-red baseline (~7 unrelated failing specs elsewhere) is NOT chased — only the six sibling suites above are the guard.

4. **INV-12 net-negative (one parser, no dup remains):**
   `cd frontend && test $(grep -c 'safeCleanBrief' src/components/layout/DashboardLayout.tsx) -eq 0 && test $(grep -c 'MARKER = ' src/components/history/RevisionFamilyView.tsx) -eq 0 && grep -q 'parseRunInput' src/components/history/RevisionFamilyView.tsx && grep -q 'parseRunInput' src/components/layout/DashboardLayout.tsx && echo NET_NEGATIVE_OK`

5. **INV-3 by construction:** `git status --porcelain` shows ZERO changes under `backend/` — only `frontend/src/**` files touched.
</verification>

<success_criteria>
- `lib/runInput.ts` exports parseRunInput/ParsedRunInput and correctly decomposes all six marker families; format-tolerant on clean/instruction-only input (7 parser cases green).
- `getRunArtifacts` fetches `/api/runs/{id}/artifacts` with `?kind=`/`?include=content` + Bearer and parses `{ workflow_id, artifacts }` (fetch-mock test green).
- `ClarifyRound` type + `PipelineRunState.clarifications?` added; retainClarifyRound appends and resets per run (hook test green).
- Live clarify Q&A survives the questionnaire panel clear (folded before `setQuestionnaireQuestions([])`); submittedBrief captured on launch.
- RevisionFamilyView shim + both DashboardLayout chain sites delegate to parseRunInput; safeCleanBrief and the shim's manual marker scan are deleted (NET_NEGATIVE_OK).
- tsc identity gate `GATE_OK`; six sibling regression suites green; zero backend changes.
- NO StartingPointCard / ClarificationsCard / Files rows / new visual language shipped (C2 scope untouched).
</success_criteria>

<output>
Create `.planning/quick/260702-wwx-workstream-c1-run-inputs-foundation-pars/260702-wwx-SUMMARY.md` when done.
</output>
