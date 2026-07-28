# Fix Register — VelocityAI / Flowin

> **Purpose.** Every fix applied via `/velocity-ai-fix` is logged here. Read this alongside the Implementation Register before applying any new fix — to avoid re-fixing something already fixed, and to understand the cumulative patch history on top of the planned phases.
>
> **Format per entry:** Date · Fix ID · Root cause · Files changed · Phase(s) involved · Invariants verified · Notes.

---

## Fix Log

| Fix ID | Date | Description | Root Cause | Files Changed | Phase Involved | Invariants | Status |
|--------|------|-------------|------------|---------------|---------------|------------|--------|
| FIX-130 | 2026-07-28 | Run titles show full context blob instead of clean brief on left panel, notifications, and run header — fix in backend _clean_run_title + FE submittedBrief fallback + notification sanitization + handleRunPipeline _display_title injection | (1) _clean_run_title regex `\s*===\s*CONTEXT...` never matched when context block starts at position 0 (no leading brief). (2) page.tsx fell back to raw message when parseRunInput returned empty brief — entire context blob set as submittedBrief. (3) DashboardLayout notification-update effect wrote unsanitized DB title to notifications. (4) handleRunPipeline (IdeaInputPage path) never injected _display_title into extraParams. | `backend/app/api/run_commands.py`, `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | Phase 25/36/38 (run titles / KAN-116 / notifications) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-127 | 2026-07-27 | Add NEVER-ask-questions contract to remaining 5 agents: ppt-revision-agent (HIGH risk), ppt-revision-assembler, prototype-build, prototype-validate, prototype-revision-validate | These agents had no no-questions contract. ppt-revision-agent is HIGH risk (same pattern as confirmed-broken user-story-revision-agent). Others had implicit protection from tool-call-only workflow but no explicit rule. | `backend/agents/prompts/ppt-revision-agent/AGENT.md`, `backend/agents/prompts/ppt-revision-assembler/AGENT.md`, `backend/agents/prompts/prototype-build/AGENT.md`, `backend/agents/prompts/prototype-validate/AGENT.md`, `backend/agents/prompts/prototype-revision-validate/AGENT.md` | Phase 15 (prompt contracts) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-126 | 2026-07-27 | KAN-124: (1) Auto-fill recommended answers on skip/partial-answer so agents always get context; (2) Add no-questions contract to 9 missing agent prompts across user_stories, user_stories_revision, od_ppt_revision, prototype_revision | (1) clarify_engine._merge_answers() never read recommended_answer — empty on skip. (2) 9 AGENT.md files missing the NEVER ask clarifying questions output contract confirmed by full pipeline audit. | `backend/agents/execution_engine/clarify_engine.py`, `backend/agents/prompts/user-story-revision-agent/AGENT.md`, `backend/agents/prompts/domain-analyst/AGENT.md`, `backend/agents/prompts/epic-architect/AGENT.md`, `backend/agents/prompts/story-estimator/AGENT.md`, `backend/agents/prompts/nfr-specialist/AGENT.md`, `backend/agents/prompts/backlog-reviewer/AGENT.md`, `backend/agents/prompts/backlog-compiler/AGENT.md`, `backend/agents/prompts/od-ppt-revision-agent/AGENT.md`, `backend/agents/prompts/prototype-revision-agent/AGENT.md` | Phase 3 (ClarifyEngine) + Phase 15 (prompt contracts) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-125 | 2026-07-27 | "Edit brief & run again" navigates to input view instead of also calling resume; "Reopen & fix" resume error resolved | (1) RunChatLane secondary button called `onRelaunch` (= handleResumeRun) instead of a separate nav-home callback — both buttons did the same thing. (2) No `onEditBrief` prop existed. Fix: add `onEditBrief` prop to RunChatLane, wire secondary button to it, add `handleEditBrief` in DashboardLayout that navigates to "input" view for editing. | `frontend/src/components/chat/RunChatLane.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | Phase 31/50 (CHATUI-01 terminal card / KAN-120) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-124 | 2026-07-27 | KAN-123: Security gate failure UX — "What went wrong" security bullets, "Blocked by the security gate" inline Steps card, and Audit tab shows hook_runs (secret scan / exec denied / validation) with Detector/Match/Action/Outcome detail rows | (1) AuditTab fetched only gate_events/validation_results/exec_runs but NOT hook_runs — the table where secret_scan blocks are written. (2) RunChatLane "What went wrong" card showed generic agent names + one error string, not structured security bullets. (3) StepsOverviewSpine had no inline security gate explanation card after a failed agent row. | `frontend/src/components/results/AuditTab.tsx`, `frontend/src/components/results/StepsOverviewSpine.tsx`, `frontend/src/components/chat/RunChatLane.tsx` | Phase 8 (HOOK-01/04 hook_runs), Phase 13 (F3 pipeline_failed/security gate), Phase 16 (ISS-016 terminal failure card) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-123 | 2026-07-27 | Review gate heading shows raw UUID+agent_id key ("Review gate — fd18bfcc-...:prototype-analyze") instead of human-readable agent name | GateAwaitingCard in StepsOverviewSpine.tsx used {laneGate.gateKey} (= pipeline_run_id:agent_id internal key) in the heading. Fix: use laneGate.agentName which is already available in GateContext | `frontend/src/components/results/StepsOverviewSpine.tsx` | Phase 8 (GATE-01/02 display) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-122 | 2026-07-27 | Stop button appears unresponsive + yellow Reconnecting banner on every Stop click (root fix) | sawNonLiveAttachRef in useRunStream was only set on stream_attached events, never on pipeline_cancelled/pipeline_failed. When backend closes stream after cancel, the ref was false → scheduleReconnect() fired → yellow banner. FIX-121's detachRun races the React render cycle; this ref-set is synchronous and guaranteed. | `frontend/src/hooks/useRunStream.ts` | Phase 44 (BUG-015 / SSE transport) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-121 | 2026-07-27 | 3 resume/stop bugs: (1) Spec Kit Analyzer skipped on resume — agent stopped mid-run classified complete; (2) stop unresponsive appearance from reconnecting banner; (3) yellow Reconnecting banner on every Stop click | (1) _first_incomplete_step used only artifact presence for single_shot completeness — an agent killed between artifact-write and agent_complete was skipped as done. (2) Second stop works but banner makes it seem broken. (3) pipeline_cancelled never called detachRun, so SSE stream close triggered scheduleReconnect (sawNonLiveAttachRef=false for live streams) | `backend/agents/execution_engine/engine.py`, `frontend/src/app/dashboard/page.tsx` | Phase 50/44/29 (RESUME-18/KAN-120/BUG-015) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-120 | 2026-07-27 | KAN-120: 4 resume UI bugs — 409 race on fast-click, agent statuses reset to idle, task 1/2 data lost, errors navigate home silently | BUG-1: DB commits cancelled async after cooperative cancel fires pipeline_cancelled; fast-click sees generating status. BUG-2: pipeline_start reset all agents to idle; resumed engine skips completed agents without marking them done. BUG-3: task_progress handler replaced protoCompletedTasks wholesale, wiping pre-stop task data when resumed engine only reported new tasks. BUG-4: any resume error called handleGoHome() silently. | `backend/agents/execution_engine/engine.py`, `frontend/src/hooks/useWorkflow.ts`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/chat/RunChatLane.tsx` | Phase 50/44/31 (RESUME-18/KAN-120) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-119 | 2026-07-24 | User text not showing in chat + no loading indication for some workflows — optimistic user bubble missing for revise/chain intents on complete-state runs | FIX-118 removed the pre-intent sendMessage echo to fix double versioning, but this also removed the user bubble echo for revise and chain intents (only the ask path called sendMessage which creates a bubble). Fix: add addOptimisticMessage to useRunChat (FE-only bubble, no backend call) + addOptimisticMessage prop to RunChatLaneProps + wire through DashboardLayout. In handleFreeText for complete state: call addOptimisticMessage immediately (user sees their text + TypingIndicator), then for ask path pass existingMessageId to sendMessage to reconcile without duplicating. | `frontend/src/hooks/useRunChat.ts`, `frontend/src/components/chat/RunChatLane.tsx`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/app/dashboard/page.tsx` | Phase 31/43 (CHATUI-01/A1 CRUX) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-118 | 2026-07-24 | PPT revision creates 2 version entries — sendMessage echo on terminal run triggers automatic CHANNEL_REVISION before confirm chip fires | handleFreeText called sendMessage(text) without options to echo user bubble; on terminal run the mechanical router routes undecorated messages to CHANNEL_REVISION → immediate revision run minted; then confirm chip fired handleRevisePpt → second revision run. Fix: remove the pre-intent-classification sendMessage echo — the TypingIndicator fires instead. | `frontend/src/components/chat/RunChatLane.tsx` | Phase 29 (chat backbone / mechanical router) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-117 | 2026-07-24 | Standard PPT revision routes to PptxGenJS agent instead of HTML deck editor | handleRevisePpt used `workflowType === "od_ppt"` to detect HTML decks but standard PPT runs dispatch as `"ppt"` type so isOdPpt was false → ppt_revision (PptxGenJS) fired instead of od_ppt_revision (HTML). Fix: also set isOdPpt=true when pptContent exists and pptxCode is absent — the definitive signal that the deck is HTML not JS. | `frontend/src/components/layout/DashboardLayout.tsx` | Phase 14 (ppt_revision / od_ppt_revision) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-116 | 2026-07-24 | LLM intent classifier: silent classify-intent endpoint so settled-run chat shows revise/chain button immediately with no chat reply | Concierge was called as a chatbot and responded with text; LLM also had no knowledge of what was produced. Fix: POST /classify-intent calls LLM with user text + deliverable summary → returns {intent, target_id} JSON only; FE shows revise chip or chain picker immediately. Also adds run_summary (wr.title + wr.output preview) to _ConciergeCtx so any LLM path knows the deliverable. | `backend/app/api/run_commands.py`, `backend/app/agents/chat/concierge.py`, `frontend/src/lib/api.ts`, `frontend/src/components/chat/RunChatLane.tsx` | Phase 43 (A6-redux Concierge) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-115 | 2026-07-24 | Replace regex-based chat intent classifier with LLM-driven revise/chain intent detection (Option A) | classifyFreeText() used CHAIN_INTENT/CHANGE_INTENT keyword regexes to bypass the Concierge for "chain" and "change" texts; natural-language intent never reached the LLM. Fix: route all settled-run free text to the Concierge; add propose_chain tool so LLM can emit chain intent; handle "chain" disposal in run_commands.py; update renderProposals to fire onSuggestion on chain confirm. | `backend/app/agents/chat/concierge.py`, `backend/app/api/run_commands.py`, `frontend/src/components/chat/RunChatLane.tsx` | Phase 43 (A6-redux Concierge) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-114 | 2026-07-24 | engine._apply_selections __deliverable__ branch returned single CompiledWorkflow instead of 2-tuple — TypeError: cannot unpack non-iterable CompiledWorkflow object | Both return paths inside _apply_selections must return (compiled, _user_by_agent) 2-tuple. The __deliverable__ early-return branch (added in 6685906b/FIX-059) returned dataclasses.replace(compiled, ...) bare instead of the 2-tuple the caller at engine.py:1467 unpacks. | `backend/agents/execution_engine/engine.py` | Phase 22 (KAN-112 _apply_selections) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-113 | 2026-07-24 | KAN-121: ComposerPage.handleRunOnce never injects __deliverable__ override — custom prototype/PPT/user-story runs produce wrong output | handleRunOnce sent per-agent selections but never called resolveDispatchType() so __deliverable__ was absent; engine used custom manifest default (streamed_text/output.md). Fix: export resolveDispatchType from IdeaInputPage (INV-12 single source), import + call it in handleRunOnce to merge __deliverable__ and resolve dispatchType — mirrors IdeaInputPage.handleRun exactly. | `frontend/src/components/workflow/IdeaInputPage.tsx`, `frontend/src/components/workflow/composer/ComposerPage.tsx` | Phase 22 (KAN-112 custom composer) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-112 | 2026-07-24 | KAN-121: Custom composer (ComposerPage) shows no agent recommendations or companion pipeline suggestions | ComposerPage is the custom workflow entry (not IdeaInputPage). Brief-based recommendations and companion suggestions existed only in IdeaInputPage; ComposerPage had no such logic. Fix: export getAgentRecommendations + COMPANION_GROUPS from IdeaInputPage (INV-12 single source), import + render them in ComposerPage keyed on the description field. | `frontend/src/components/workflow/IdeaInputPage.tsx`, `frontend/src/components/workflow/composer/ComposerPage.tsx` | Phase 22 (KAN-112 custom composer) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-111 | 2026-07-24 | KAN-121 (follow-up): Custom prototype workflow uses single_shot for prototype-build — single_file resolver never finds prototype.html because task_loop never wrote it | __deliverable__ override (FIX-110) correctly patches compiled.deliverable to single_file/prototype.html but does NOT patch the prototype-build step strategy from single_shot→task_loop. task_loop is the ONLY strategy that calls persist_task_html() to write prototype.html to the RunSandbox. Fix: inject prototype-build:{strategy:"task_loop"} per-agent selection alongside __deliverable__ in mergedSelections so _apply_selections' existing sel.get("strategy") path (engine.py:6442) patches the step — no engine edit needed. | `frontend/src/components/workflow/IdeaInputPage.tsx` | Phase 22 (KAN-112 custom composer / task_loop strategy) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-110 | 2026-07-24 | KAN-121: Custom workflow with prototype agents shows validator QA text (output.md) instead of HTML prototype — add missing prototype-analyze and prototype-validate to AGENT_DELIVERABLE_MAP trigger list | AGENT_DELIVERABLE_MAP prototype entry only listed 3 of 5 agents (prototype-build, prototype-specify, prototype-plan). When user selected a composition including prototype-analyze or prototype-validate without the 3 trigger IDs, resolveDispatchType() returned the default fallback {strategy:"streamed_text", name:"output.md"} → StreamedTextResolver used last_streamed (validator QA text) as the deliverable. FIX-059/FIX-060 on another branch had the full 5-agent list; it was not ported to feat/ui-2. Fix: add prototype-analyze and prototype-validate to the prototype entry trigger list. | `frontend/src/components/workflow/IdeaInputPage.tsx` | Phase 22 (KAN-112 custom composer) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-109 | 2026-07-24 | PPT preview shows validator QA text on top of slides — widen body-preamble strip + harden output contract | strip_pre_slide_body_text skipped stripping when preamble had ONLY HTML elements (preamble_text_only was empty after tag removal); validator AGENT.md allowed a sentence before <artifact. Fix: strip any non-whitespace preamble unconditionally; extend anchor detection; harden output contract to forbid ANY text before <artifact | `backend/agents/capabilities/deliverables/_artifact.py`, `backend/agents/prompts/od-ppt-validator/AGENT.md` | Phase 15/19 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-108 | 2026-07-23 | KAN-120: duplicate "Run started" card in chat after Run Again | narrator _reply_event_id used source_event_id as idempotency key; resumed run's pipeline_start has new event_id → new card. Fix: pipeline_start cards key on `pipeline_start:{run_id}` so all pipeline_start events for the same run collapse to one card | `backend/app/agents/chat_narrator.py` | Phase 31/43 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-107 | 2026-07-23 | KAN-120: after resume completes, FE still shows "Cancelled by you" + Run Again, history shows Cancelled | 3 bugs: (1) pipeline_start spread kept cancelled:true so pipeline_complete landed back in "terminal"; (2) _reconcile_terminal_status prioritised pipeline_cancelled over subsequent pipeline_complete from resume; (3) FE history refetch raced against reconcile | `frontend/src/hooks/useWorkflow.ts`, `frontend/src/app/dashboard/page.tsx`, `backend/app/api/run_commands.py` | Phase 50/44/31 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-106 | 2026-07-23 | KAN-120: od_ppt/prototype resume produces empty output — od_context lost on resume | resume_run called _drive_resumed_stream/_execute_impl with od_context=None (default); od_context (template+DS data) was only available at launch time and never persisted. Added migration 0027 (od_context_json column), persist at launch, restore at resume | `backend/alembic/versions/0027_workflow_run_od_context.py`, `backend/app/models/workflow.py`, `backend/app/api/run_commands.py`, `backend/agents/execution_engine/engine.py` | Phase 50/37 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-105 | 2026-07-23 | KAN-120: "Run Again" resumes cancelled pipeline from stopped step | 4-part gap: backend eligibility `!= "failed"` blocked cancelled runs; in-memory state machine terminal guard blocked same-session resumes; no postResume in api.ts; onRelaunch wired to handleGoHome; cancelled card showed wrong label/text | `backend/app/api/run_commands.py`, `frontend/src/lib/api.ts`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/chat/RunChatLane.tsx` | Phase 50/44/31 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-104 | 2026-07-23 | Chat-initiated workflow chaining — type vague intent to get inline chain picker | classifyFreeText had no CHAIN_INTENT path; vague chain phrases fell through to revision hold. Added CHAIN_INTENT regex, "chain" verb to CHAIN_TRANSFORM, chainPickerOpen state, and renderChainPicker() | `frontend/src/components/chat/RunChatLane.tsx` | Phase 31/c72 (RunChatLane — chain suggestions) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-103 | 2026-07-23 | Auto-select "Design System Inspired by Apple" as default in prototype launch wizard | selectedDsId initialised to null; listDesignSystems() callback only called setSystems() with no default selection. Added functional updater to setSelectedDsId inside the callback: selects "apple" only when prev===null and mode==="prototype" and "apple" exists in the list. | `frontend/src/components/workflow/LaunchWizard.tsx` | Phase 37 (B3/B7 — LaunchWizard) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-102 | 2026-07-23 | Add Hexaware logo to AppHeader (top-left) and Login page dark panel | No Hexaware branding existed; added inline text badge (white bold "HEXAWARE" on brand-blue pill) before the VelocityAI wordmark in both surfaces | `frontend/src/components/layout/AppHeader.tsx`, `frontend/src/app/login/page.tsx` | Phase 35 (B1 — shell chrome + login reskin) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-101 | 2026-07-22 | Move System Prompt editor from Config tab to Overview tab; make Edit button prominent with white hover | AgentPromptSection was mounted with surfaceOnly in Overview (read-only) and without it in Config (editable); users had to switch tabs to edit what they were reading. Edit button was tiny (10px gray). | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7 — AgentCapabilitiesModal) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-100 | 2026-07-22 | Dashboard home instant load — stale-while-revalidate with sessionStorage cache | All prior fixes passed props between components but data still arrives async after auth; first render always had nothing to show. SWR pattern: seed from sessionStorage cache → render instantly → background refetch writes cache for next visit | `frontend/src/components/catalog/HomeLaunchGrid.tsx` | Phase 38/40 (HomeLaunchGrid) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-099 | 2026-07-22 | Stop "Jump back in" recents from appearing late — accept recentRuns prop instead of duplicate internal fetch | HomeLaunchGrid fetched getWorkflows internally even though DashboardLayout already had recentRuns from page.tsx. Added recentRuns prop, seed recents state from it instantly, skip internal fetch when prop supplied | `frontend/src/components/catalog/HomeLaunchGrid.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | Phase 38 (SC-2 / recents strip) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-098 | 2026-07-22 | KAN-118: Remove dashboard home flicker — eliminate card stagger, header slide-up animation, and AnimatePresence mode=wait | 4 compounding causes: per-card delay (0.06+idx*0.05s), h1 slide-up (0.4s), AnimatePresence mode=wait adds 200ms blank on nav. All three removed. motion import cleaned up. | `frontend/src/components/catalog/HomeLaunchGrid.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | Phase 38/40 (HomeLaunchGrid cards + DashboardLayout view-switch) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-097 | 2026-07-22 | Remove time estimate (~Nm) from Home launch grid cards — show agent count only | estimate string in HomeLaunchGrid included `· ~${minutes}m` from the analytics history; removed the time clause so only `~N agents` shows | `frontend/src/components/catalog/HomeLaunchGrid.tsx` | Phase 38 (SC-2 real estimate) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-096 | 2026-07-22 | Hide Back/Next nav buttons in PPT wizard when only one step (template) is shown | WizardStepper always rendered the Back/Next row regardless of step count; PPT mode passes steps={["template"]} (1 step only) so both buttons were disabled but still visible. Guard now hides the nav row entirely when steps.length <= 1. | `frontend/src/components/workflow/WizardStepper.tsx` | Phase 37/41 (B3/B7 — WizardStepper FIX-065) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-095 | 2026-07-22 | Fix `.split is not a function` crash + multi-select chip highlighting when "Use recommended" clicked | recommendedAnswer/recommendedDisplay can be non-string (array/number) from the API — all .split() calls lacked String() coercion. Also multi-select chip highlight was broken because useRecommended stored the whole comma-joined string instead of splitting to individual chip values. Fixed via two pure helpers: toRecString() and splitRecToChips(). | `frontend/src/components/chat/InlineClarifyActions.tsx` | Phase 31/42 (CHATUI-01 / InlineClarifyActions) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-094 | 2026-07-22 | KAN-117: Add recommended answers + "Skip all" affordance to clarify questions | ClarifyQuestion type carried recommendedAnswer/recommendedDisplay/impactLevel but InlineClarifyActions never rendered them; skip was impossible without answering all questions (Phase 42-06 intentional omission, now reversed per user request) | `frontend/src/components/chat/InlineClarifyActions.tsx` | Phase 31/42 (CHATUI-01 / InlineClarifyActions) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-093 | 2026-07-22 | Remove duplicate outer timeline dot from StartingPointCard — aligns with ClarificationsCard flat-card style | StartingPointCard used a `relative pl-8` wrapper with an absolute-positioned navy circle+FileText timeline dot, PLUS a second FileText icon inside the card button — rendering two similar icons side-by-side. Fix removes the outer dot entirely. | `frontend/src/components/results/StartingPointCard.tsx` | Phase 25/42 (Workstream C2) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-092 | 2026-07-22 | KAN-116 Bug 3 (definitive): pass _display_title in extraParams from all chain/revision call sites so page.tsx never needs to re-parse complex nested context blocks | parseRunInput failed on complex nested context; fix passes the already-clean chainBrief/instruction as _display_title in extraParams — no re-parsing needed | `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/app/dashboard/page.tsx` | Phase 25/36 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-091 | 2026-07-22 | KAN-116 Bug 3 (BE): chain context_block embedded polluted title/brief from old DB runs causing nested === markers that parseRunInput couldn't strip | _extract_chain_context used raw workflow_run.title and .input which for pre-fix runs contained === marker text; these nested markers broke the FE context strip | `backend/app/api/runs.py` | Phase 29/36 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-090 | 2026-07-22 | KAN-116: Clean === marker titles at all display surfaces — history, sidebar, live header, and new runs | Three-layer fix: (1) FE display-time cleanDisplayTitle helper in RevisionFamilyView+WorkflowHistory+Sidebar strips existing DB titles; (2) FIX-087 backend _clean_run_title prevents new bad titles; (3) FIX-089 cleans submittedBrief for live header | `frontend/src/components/history/RevisionFamilyView.tsx`, `frontend/src/components/history/WorkflowHistory.tsx`, `frontend/src/components/sidebar/Sidebar.tsx` | Phase 25/36 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-089 | 2026-07-22 | KAN-116 Bug 3 (FE): raw context markers shown as run title during live runs — submittedBrief stored raw enrichedInput | setSubmittedBrief(message) used raw enrichedInput with === markers; parseRunInput (INV-12 single source) now extracts clean brief before storing | `frontend/src/app/dashboard/page.tsx` | Phase 25/36 (Workstream C1) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-088 | 2026-07-22 | KAN-116 Issue 2: version chip stays at v1 after revision completes — contentSourceRunId not updated for revision completions | isForeignCompletion guard blocked setContentSourceRunId for revision runs (revision_run_id ≠ trackedRunIdRef which holds parent run id), preventing family re-fetch | `frontend/src/app/dashboard/page.tsx` | Phase 25/36 (B2) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-087 | 2026-07-22 | KAN-116: Fix version switch showing wrong content, chained runs in version family, and context markers in titles | Bug 1: handleSelectVersion only updated WorkflowHistory local state, never called page.tsx content-routing; Bug 2: launch_run set parent_run_id for all types including chains; Bug 3: title stored raw content with === markers | `frontend/src/components/history/WorkflowHistory.tsx`, `backend/app/api/run_commands.py` | Phase 25/36 (B2/P25) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-086 | 2026-07-22 | Surface system prompt editor (Edit/Save/Reset) on Config tab of Library agent drawer | AgentPromptSection was mounted with surfaceOnly=true everywhere (ND-7/LOCK-E deferral), hiding write affordances. Config tab now mounts it without surfaceOnly so users can edit, save, and reset agent system prompts | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) + KAN-76 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-085 | 2026-07-22 | Rename "Run again" button to "New Pipeline" on cancelled terminal card | Label was hardcoded as "Run again" in the cancelled branch of RunChatLane renderComposerBody | `frontend/src/components/chat/RunChatLane.tsx`, `frontend/src/components/chat/__tests__/RunChatLane.terminal.test.tsx` | Phase 31/32 (CHATUI-01) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-084 | 2026-07-21 | KAN-115: Clear stale questionnaireData on pipeline_cancelled/failed so AwaitingCard disappears | pipeline_cancelled handler cleared reviewGateData but not questionnaireData or activePipelineRunId, leaving laneClarifyOpen=true and runLaneState stuck at "clarify" instead of "terminal" after cancel/fail | `frontend/src/app/dashboard/page.tsx` | Phase 22/42 (page.tsx dispatcher) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-083 | 2026-07-21 | KAN-114: Replace first clarification card (amber styled) with plain text bubble "Before I build, I need to lock a few things down." | Two independent paths fired on questionnaire_ready: (1) chat_narrator.py emitted a styled ResultCard with text "Paused — N questions for you"; (2) RunChatLane.tsx also showed an AwaitingCard. Fix: narrator text changed to fixed message; ResultCard.tsx now renders a plain prose bubble for clarify kind. AwaitingCard untouched. | `backend/app/agents/chat_narrator.py`, `frontend/src/components/chat/ResultCard.tsx`, `backend/tests/unit/test_chat_narrator.py` | Phase 31 (CHATUI-01) + Phase 43 (A6) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-082 | 2026-07-21 | Always show "Write a custom skill" button on Skills tab — remove agent.has_skill gate | The custom skill button was gated on `agent.has_skill` so it never showed for agents without the flag. Every agent should be able to get a custom skill authored. Removed the gate. Also cleaned up the dangling `)}` JSX left from the removed conditional. | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-081 | 2026-07-21 | Show empty state messages when no suggested skills or hooks for an agent | Skills/Hooks tabs rendered blank when suggestedSkills/suggestedHooks had 0 items — `{length > 0 && (...)}` with no else branch. Changed to ternary with an empty-state card (icon + message). | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-080 | 2026-07-21 | Fix Save button flash + double appearance on Reset — remove loading early-return from ConfigLeversFlat | Reset increments resetKey which remounts ConfigLeversFlat. On remount, useAgentCapabilities starts loading=true and the early-return `<p>Loading…</p>` caused a height change (tiny→4 big rows) that shifted the button row, creating the double-button flash. Removed the loading early-return (renders rows with empty options = same height always). Also added setSaved(false) to Reset and removed transition-all from Save button. | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-079 | 2026-07-21 | Save feedback + working Reset for Config tab levers | Save button gave no feedback before closing. Reset only updated parent state but ConfigLeversFlat has its own localSel; dropdowns didn't reset. Fix: Save shows "✓ Saved" green state for 900ms; Reset increments resetKey which is passed as key prop to ConfigLeversFlat — React remounts it with fresh empty localSel. | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-078 | 2026-07-21 | Persist Config-tab agent selections across drawer open/close cycles | AgentCapabilitiesModal is unmounted on close; all localSelections were lost. LibraryPage now uses a useRef map (savedSelectionsRef) keyed by agent.id. initialSelections passes saved values on open; onSelectionsChange writes back on every change and on Save. effectiveOnSelectionsChange now calls both setLocalSelections AND onSelectionsChange so both local display and parent persist stay in sync. | `frontend/src/components/library/LibraryPage.tsx`, `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-077 | 2026-07-21 | Restore styled custom dropdown using onPointerDown+preventDefault to beat mousedown dismiss | Native select options cannot be CSS styled (OS renders them). Custom dropdown needed but all previous attempts failed because onClick fires after mousedown dismiss. Fix: use onPointerDown+preventDefault on both trigger and options — pointer events fire before mousedown, so selection lands before the outside-click dismiss. | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-076 | 2026-07-21 | Definitively fix Config lever selections — replace broken custom dropdown with native <select> | All custom dropdown attempts failed due to browser event sequencing (mousedown dismiss fires before click). Replaced ConfigLeverSelect entirely with native <select> + appearance-none + ChevronDown overlay. Native select onChange always fires reliably. Deleted the ConfigLeverSelect component and the outside-click useEffect entirely. | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-075 | 2026-07-21 | Config lever option clicks close dropdown without selecting — add onMouseDown stopPropagation to listbox div | The document mousedown listener (used for outside-click dismiss) fired when user clicked an option button, calling setOpenLever(null) and unmounting the dropdown before the click event registered. Fixed by adding onMouseDown stopPropagation to the listbox div so options receive their click events. | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-074 | 2026-07-21 | Config levers always show "Default" — fix by giving ConfigLeversFlat its own local selections state | Display was driven by selections PROP passed through effectiveSelections chain. Prop updates require parent re-render + prop drill, introducing a render cycle where `displayLabel` could read stale/empty data. Fixed by giving ConfigLeversFlat its own `localSel` useState seeded from props on mount; `updateLever` calls `setLocalSel` immediately so display is in sync. Still propagates up via `onSelectionsChange`. | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-073 | 2026-07-21 | Config lever dropdown clicks do nothing — fix by hoisting CustomSelect/LeverRow to module scope | CustomSelect and LeverRow were defined inside ConfigLeversFlat body. React treats inline component definitions as new types on every render, causing remount instead of update when an option is clicked — breaking the selection. Hoisted to module-level ConfigLeverRow + ConfigLeverSelect with all state passed as props. | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-072 | 2026-07-21 | Replace native <select> in Config levers with fully custom styled dropdown | Browser renders native OS dropdown for <select> which cannot be styled. Replaced with custom button+listbox (CustomSelect component): styled trigger pill, floating card list with hover/selected states, outside-click dismiss, one-open-at-a-time. | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-071 | 2026-07-21 | Polish ConfigLeversFlat selects — consistent row height, custom chevron, Phase-32 font/tokens | Each native select rendered at different size and with ugly browser-default arrow. Added StyledSelect wrapper (appearance-none + absolute ChevronDown), fixed w-[130px] per select, min-h-[64px] per row, text-[13px] font-sans font-medium. | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-070 | 2026-07-21 | Config tab: remove System Prompt, show flat Model/Validator/Gate/Retry rows without AdvancedExpander collapse chrome | AdvancedExpander has a per-agent expand/collapse toggle header; Config tab was showing System Prompt. Added ConfigLeversFlat (reuses useAgentCapabilities + applyLeverPatch, INV-12) that renders the 4 levers flat with label+select rows. Removed AgentPromptSection from Config tab. | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-069 | 2026-07-21 | Show Model/Validator/Gate/Retry levers + Reset/Save buttons in Config tab for all callers | AdvancedExpander was gated on {onSelectionsChange && ...} so LibraryPage drawer (which passes no onSelectionsChange) showed only System Prompt. Added local selections state; AdvancedExpander now always renders; Reset/Save buttons added at bottom. | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-068 | 2026-07-21 | Remove "Cancel" from custom skill button and darken the expanded editor form | Header button showed "Cancel" when expanded; form used light bg-white styling. Fixed: button always shows "+ Write a custom skill", form uses bg-surface-near-black with dark inputs, readable text, and inverted Attach button. | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-067 | 2026-07-21 | Replace "Custom skill" card header with dashed full-width "+ Write a custom skill" button | Header used a complex card layout (icon + title + subtitle + right-side label). Target design is a simple full-width dashed-border centered button. Only the header visual changed; editor form, animation, success state untouched. | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-066 | 2026-07-21 | Restyle AgentPromptSection to dark card with readable white sans-serif text | Container used light white card (border-gray-200 bg-white) and prompt body used tiny monospace font (font-mono text-[10.5px] text-gray-600). Changed to dark near-black card (bg-surface-near-black) with white readable prose text (text-[13px] text-white font-sans). | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-065 | 2026-07-21 | Remove Design System and Discovery tabs for PPT presentation wizard | STEP_TABS and STEP_IDS were hardcoded as 3 items; no way to suppress tabs per mode. Added `steps?: StepId[]` prop (default all 3) to WizardStepper; LaunchWizard passes `["template"]` for ppt mode. | `frontend/src/components/workflow/WizardStepper.tsx`, `frontend/src/components/workflow/LaunchWizard.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-064 | 2026-07-21 | Hide Web/Deck toggle in template picker — show only relevant gallery per launch context | Toggle rendered unconditionally in WizardStepper.tsx; no prop to suppress it. Added `showToggle?: boolean` (default false) to hide the toggle so prototype shows only web templates and PPT shows only deck templates. | `frontend/src/components/workflow/WizardStepper.tsx`, `frontend/src/components/workflow/WizardStepper.test.tsx` | Phase 37/41 (B3/B7) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-063 | 2026-07-21 | KAN-113: Fix version dropdown showing wrong relative age ("5h ago") due to timezone-naive datetime serialization | SQLAlchemy `DateTime` (no `timezone=True`) returns naive datetimes from SQLite. Pydantic v2 serializes them without `+00:00`, so JavaScript `Date.parse()` treats them as local time, adding the user's UTC offset to the age calculation. Fix: add `@field_serializer` to `WorkflowRunResponse` and `FamilyMemberResponse` to promote naive datetimes to UTC before ISO-formatting. | `backend/app/api/runs.py` | Phase 36 §3 (FamilyMemberResponse) + Phase 5 §3 (WorkflowRunResponse) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-062 | 2026-07-21 | Move "v1 draft" version chip to the left of the "Running · Streaming" status badge in RunHeader | Chip was placed after the `flex-1` spacer in JSX order, landing it on the right side. Moved it to the first child position in the flex row so it renders left of the StatusBadge. | `frontend/src/components/preview/RunHeader.tsx` | Phase 39 (RUNUI-06/07) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-061 | 2026-07-20 | KAN-112: Custom utility agent combinations fail with DAG unsatisfiable — all 8 custom agents had rigid `consumes` chain | Each custom agent declared `consumes: [previous-agent-id]` forming a fixed 8-agent chain. The `WorkflowResolver.validate()` rejected any subset as unsatisfiable (e.g. `report-generator` needs `documentation-agent`). Fixed by changing `consumes` from specific agent ids to `[]` on all 7 non-root custom agents. `context_from: [$previous]` already chains context correctly — `consumes` is only for typed artifact graph edges, which these agents don't need. | `backend/agents/prompts/swot-analyst/AGENT.md`, `backend/agents/prompts/roadmap-planner/AGENT.md`, `backend/agents/prompts/security-auditor/AGENT.md`, `backend/agents/prompts/test-case-generator/AGENT.md`, `backend/agents/prompts/performance-optimizer/AGENT.md`, `backend/agents/prompts/documentation-agent/AGENT.md`, `backend/agents/prompts/report-generator/AGENT.md` | Phase 7/8 (WorkflowResolver / agent AGENT.md) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-060 | 2026-07-17 | KAN-112: Make all custom-composer runs consistent — always pipeline_type="custom" | User story agents were routed to pipeline_type="user_stories" making history/logs inconsistent with prototype runs (which stayed "custom"). Fix: removed the `user_stories` routing branch from `resolveDispatchType`; added user story agents to `AGENT_DELIVERABLE_MAP` with `{strategy:"streamed_text", name:"user_stories.md", mimetype:"text/markdown"}`. Engine `_apply_selections` already handles the override + forces clarify.mode=skip. Output renders via `GenericDeliverablePreview` → `MarkdownPreview`. All custom-composer runs now consistently show `type=custom` in logs and history. | `frontend/src/components/workflow/IdeaInputPage.tsx` | Phase 22 (custom composer) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-059 | 2026-07-17 | KAN-112 Option B: Replace `custom_prototype` manifest copy with runtime deliverable override via `__deliverable__` selections key | `custom_prototype` was an exact copy of `prototype/workflow.yaml` with `clarify.mode:skip` — a manifest-copy anti-pattern (INV-12 violation). Option B: FE `resolveDispatchType` now returns `{type:"custom", deliverableOverride:{strategy,name,mimetype}}` for prototype agents; `handleRun` injects `__deliverable__` into the selections map; `engine._apply_selections` reads it, calls `DeliverableSpec(**override)` and `dataclasses.replace(compiled.clarify, mode="skip")` — same skip behaviour, zero manifest copy. `custom_prototype` manifest deleted; all references removed from loader/registry/entitlements/websocket/types/DashboardLayout/page.tsx. | `backend/agents/workflows/selections.py`, `backend/agents/execution_engine/engine.py`, `backend/agents/loader.py`, `backend/agents/registry.py`, `backend/app/core/entitlements.py`, `backend/app/api/websocket.py`, `frontend/src/types/index.ts`, `frontend/src/components/workflow/IdeaInputPage.tsx`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/app/dashboard/page.tsx`, `backend/agents/workflows/custom_prototype/workflow.yaml` (deleted) | Phase 22 (custom composer) + SC-001 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-058 | 2026-07-16 | KAN-112: HTML prototype output from custom workflow — create `custom_prototype` manifest (SC-001) | The only path to HTML prototype output from the custom composer is a new SC-001 manifest. Dispatching `prototype` silently crashed (suspected SQLite lock from prior cancelled run; the `ectx.skip_clarification` dynamic attribute approach was also fragile). `custom_prototype` is an exact copy of the `prototype` manifest with `clarify.mode: skip` — bypasses the clarify gate without any engine edits. FE `resolveDispatchType` now sends `custom_prototype`; `DashboardLayout` normalises `custom_prototype → prototype` for rendering; `page.tsx` routes `custom_prototype` to `setPrototypeContent`. | `backend/agents/workflows/custom_prototype/workflow.yaml` (new), `backend/agents/loader.py`, `backend/agents/registry.py`, `backend/app/core/entitlements.py`, `frontend/src/types/index.ts`, `frontend/src/components/workflow/IdeaInputPage.tsx`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/app/dashboard/page.tsx` | Phase 22 (custom composer) + SC-001 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-057 | 2026-07-16 | KAN-112 (continued): Prototype output from custom, brief-based recommendations, companion pipeline suggestions | Three gaps: (1) custom always dispatched as "custom" → streamed_text, no HTML; (2) no brief-based agent recommendations; (3) no companion-agent suggestions when partial pipeline added. Fix: `resolveDispatchType()` redirects prototype/ppt/user_stories agents to their native manifest; `AGENT_KEYWORDS` + `getAgentRecommendations()` chip strip; `COMPANION_GROUPS` amber banner when incomplete pipeline detected. | `frontend/src/components/workflow/IdeaInputPage.tsx` | Phase 22 (custom composer) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-056 | 2026-07-16 | KAN-112: Custom workflow — fix empty agent seed, add 8 default agents, fix add/remove limits, update blank-slate copy | `IdeaInputPage` seeded `pipelineAgents` from `LIBRARY_AGENTS.filter(type==="custom")` which returns `[]` (custom agents live in the separate `CUSTOM_AGENTS` export). Run button was always disabled for fresh custom runs. Three sites used the wrong filter: initial state, useEffect re-derive, and `defaultAgentIds`/`handleAddAgent`. Updated `TYPE_CONFIG["custom"]` copy and `workflow.yaml` catalog metadata. | `frontend/src/components/workflow/IdeaInputPage.tsx`, `backend/agents/workflows/custom/workflow.yaml` | Phase 22 (ISS-014 / custom composer) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-055 | 2026-07-16 | KAN-110 (follow-up): Replace page-number pagination with Load More button on Workflow History | FIX-051 implemented numbered pagination (Prev/1/2/…/Next); requirement was append-based Load More. Replaced `currentPage` state + `handleGoToPage` + pagination footer with `loadingMore` flag + `handleLoadMore` callback that appends `offset: runs.length`. Existing skeleton loading state was already sufficient. | `frontend/src/components/history/WorkflowHistory.tsx` | Frontend (FIX-051 follow-up) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-051 | 2026-07-15 | KAN-110: Workflow history slow loading + add pagination — DB index + paginated frontend | No compound index on `workflow_runs(user_id, created_at)` caused full table scan on every history load; frontend fetched `limit:100` with no offset. Fix: migration 0025 adds `ix_workflow_runs_user_created`; `list_runs` gains `X-Total-Count` header; `getWorkflows` extended with `offset` + returns `{runs,total}`; `WorkflowHistory` changed to `limit:50` with Load More button. | `backend/alembic/versions/0024_stub_from_dev_branch.py` (stub), `backend/alembic/versions/0025_workflow_runs_user_created_index.py` (new), `backend/app/api/runs.py`, `frontend/src/lib/api.ts`, `frontend/src/components/history/WorkflowHistory.tsx`, `frontend/src/components/analytics/AnalyticsPage.tsx`, `frontend/src/app/dashboard/page.tsx`, 5 test files | DB/API/Frontend (no engine phase) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-050 | 2026-07-15 | KAN-109: Add AI Coach Hub prototype template SKILL.md so the template appears in the gallery | `skills/opendesign/design-templates/ai-coach-hub/SKILL.md` was absent; `od_loader._load_one_template()` returns None when SKILL.md is missing, so the folder is silently skipped by `list_prototype_templates()`. example.html was present and correct. Fix: created SKILL.md with `od.mode: prototype` frontmatter + full agent build workflow instructions following the process-canvas pattern. | `skills/opendesign/design-templates/ai-coach-hub/SKILL.md` (new) | OpenDesign templates (content, no phase) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-049 | 2026-07-13 | KAN-108: Prototype revision delivers blank/unchanged/broken prototypes silently — add Revision Validation Agent as second step + fix clarify.mode: auto | `prototype_revision` manifest declared only 1 step; the silent `revision_validation` post-step only catches regressions vs baseline (zero-delta no-op passes), not blank pages, broken navigation, or missing components. `clarify.mode: auto` fired questionnaire on every revision. Fix: new `prototype-revision-validate` agent (dedicated AGENT.md, `pipeline_type: prototype_revision`, `consumes: [prototype-revision-agent]`, `tools: [workspace]`) added as step 2; manifest updated to `clarify.mode: skip`; registry updated; goldens regenerated; phase5/characterization tests updated. | `backend/agents/workflows/prototype_revision/workflow.yaml`, `backend/agents/registry.py`, `backend/agents/prompts/prototype-revision-validate/AGENT.md` (new), `backend/tests/agents/characterization/golden/prototype_revision.events.json`, `backend/tests/agents/characterization/golden/prototype_revision.html`, `backend/tests/agents/_scripted_model.py`, `backend/tests/agents/test_phase5_revision_validation.py` | Phase 7 (revision post-step / agent registry) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-001 | 2026-06-16 | Harden od-ppt-validator output contract (remove checklist-as-preamble loophole) + fix od-ppt-composer filesystem tool calls on Windows | Validator: "two short sentences" loophole allowed model to print full checklist as preamble without `<artifact>` wrapper → raw checklist rendered as deck. Composer: deepagents filesystem glob crashes on Windows (pathlib.rglob ValueError) → composer told to use context-injected files instead of tool calls | `backend/agents/prompts/od-ppt-validator/AGENT.md`, `backend/agents/prompts/od-ppt-composer/AGENT.md` | Phase 15 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-002 | 2026-06-16 | Vellum template not applied — example.html not injected into PPT composer context | opendesign provider `is_builder` gate used `{"prototype_emit_only", "prototype"}` set; `workspace` tool set excluded so PPT composer never received `example.html`; SKILL.md workflow says "clone example.html" but agent had no copy | `backend/agents/capabilities/context_providers/opendesign.py` | Phase 7 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-003 | 2026-06-16 | PPT/Prototype wizard hides brief textarea — stale `chain.from` in sessionStorage | `chain.from` was never removed from sessionStorage after previous chained run; on fresh wizard open the page read it, set `isChaining=true`, and hid the brief textarea and showed "CHAINED PRESENTATION · STEP 1 OF 1" | `frontend/src/app/workflow/ppt/templates/page.tsx`, `frontend/src/app/workflow/prototype/templates/page.tsx` | Phase 21 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-004 | 2026-06-15 | Delete pipeline from history does nothing — FK constraint on 9 child tables + silent frontend error | `delete_run` called `db.delete(workflow_run); db.commit()` directly; 9 child tables (run_events, artifact_refs, workflow_clarifications, gate_events, hook_runs, exec_runs, run_capabilities, subagent_runs, wave_runs) all FK into workflow_runs.id with no CASCADE; PRAGMA foreign_keys=ON blocked the DELETE → IntegrityError 500. Frontend `catch {}` swallowed the error silently | `backend/app/api/runs.py`, `frontend/src/components/history/WorkflowHistory.tsx` | Phases 4/5/8/9/11/12 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-005 | 2026-06-16 | Prototype (and PPT) wizard pre-fills stale brief from previous run — draft never cleared | `prototype.draft` / `ppt.draft` written by wizard handleContinue but never deleted after dashboard consumes the pending run; on every fresh wizard open the draft restore useEffect reads the stale key and pre-fills the brief/template/DS from the last run | `frontend/src/app/dashboard/page.tsx` | Phase 21 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-006 | 2026-06-16 | prototype-specify and prototype-plan produce empty output — max_tokens: 8000 too small | Both agents declared max_tokens: 8000; the spec writer is asked to produce a dense multi-page spec with tables, DS tokens, nav flows (4-6+ pages) that routinely exceeds 8000 tokens on Haiku 4.5 → model returns empty output → review_gate_ready has output="" → "No content was produced for review" | `backend/agents/prompts/prototype-specify/AGENT.md`, `backend/agents/prompts/prototype-plan/AGENT.md` | Phase 15 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-007 | 2026-06-16 | Prototype pipeline fails with ModuleNotFoundError: No module named 'resource' | `local.py` does `import resource` at module level; `resource` is Unix-only, unavailable on Windows; `sandbox._ws()` lazily imports local.py on every `sandbox.read()`/`sandbox.write()` call; task_loop calls both → crashes and kills the build agent | `backend/app/agents/runtime/local.py` | Phase 9 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-008 | 2026-06-16 | Spec Writer asks clarifying questions instead of producing spec — entire pipeline produces empty output | `prototype-specify` and `prototype-plan` AGENT.md had no explicit "never ask clarifying questions" rule; on an ambiguous brief (e.g. "GitHub dashboard") Haiku writes a question instead of a `<spec>` document; planner receives question → produces 932-char non-plan with no `## Task` headers → build agent runs once with empty task → prototype.html never written | `backend/agents/prompts/prototype-specify/AGENT.md`, `backend/agents/prompts/prototype-plan/AGENT.md` | Phase 15 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-009 | 2026-06-16 | Task Planner produces plan without ## Task N: headers — build agent gets empty task, streams HTML as text | Even after FIX-008, prototype-plan produces 1696-char plan without `## Task N:` headers (uses bullets/prose); heading_tasks parser finds 0 tasks → empty fallback task → build agent has no instructions → streams HTML as text, never writes prototype.html; strengthened output contract with concrete example + explicit format warning; added build agent guard for empty task block + mandatory write_file reminder | `backend/agents/prompts/prototype-plan/AGENT.md`, `backend/agents/prompts/prototype-build/AGENT.md` | Phase 15 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-010 | 2026-06-16 | Prototype pipeline always asks clarifying questions — clarify.mode: auto forces 38s clarify loop, spec writer receives only 2-word brief | `prototype/workflow.yaml` had `clarify.mode: auto` forcing CLARIFY_REQUIRED on every run; clarify engine ran 3 rounds (38s) with no user answers → clarification_limit_reached → spec writer received only "github dashboard" as brief → model wrote clarifying question despite output contract; fix: change clarify.mode to skip since od_prototype wizard already collects brief + template + DS | `backend/agents/workflows/prototype/workflow.yaml` | Phase 4/15 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-011 | 2026-06-16 | Home page shows verbose agent-chain descriptions instead of friendly subtitles | 7 `user_launchable` manifests had no `description:` field; `_describe()` fallback in `workflows.py:143` generated `"{N}-step workflow: Agent1 → ..."` strings; `WorkflowCatalog` rendered these verbatim as subtitles; fix: add `description:` to all 7 manifests with copy ported from original `CreationHub.tsx` | `backend/agents/workflows/user_stories/workflow.yaml`, `backend/agents/workflows/ppt/workflow.yaml`, `backend/agents/workflows/prototype/workflow.yaml`, `backend/agents/workflows/app_builder/workflow.yaml`, `backend/agents/workflows/mulesoft_to_springboot/workflow.yaml`, `backend/agents/workflows/dotnet_to_azure/workflow.yaml`, `backend/agents/workflows/custom/workflow.yaml` | Phase 20 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-012 | 2026-06-16 | Chained wizard runs show raw `=== CONTEXT FROM PREVIOUS PIPELINE ===` as title | `_strip_pipeline_context()` correctly strips context block → `""` but `or content` fallback reinserts full raw string as title placeholder; `_generate_workflow_title` bails immediately on empty `clean_content`. Fix: add `_extract_title_from_context()` that parses the `Title:` line from the context block; use as fallback in both the placeholder and the title generator | `backend/app/api/websocket.py` | Phase 21 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-013 | 2026-06-16 | Workflow configuration modal Agents tab overflows viewport — Per-Agent Model, Advanced, Capabilities sections inaccessible | Three bottom sections used `flex-shrink-0` outside any scroll container; the flow grid's `flex-1 overflow-y-auto` consumed all remaining height, pushing all three sections below the modal's `90vh` boundary. Fix: wrap all four sections in a shared `flex-1 overflow-y-auto min-h-0` container; cap flow grid to `min(45vh, 240px)` so it doesn't consume all vertical space | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 22 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-014 | 2026-06-17 | PPT preview shows validator checklist text instead of deck — checkbox syntax causes model to print results | `od-ppt-validator/AGENT.md` used `- [ ]` checkbox syntax for the checklist; Haiku prints ticked ✓ results (e.g. "✓ No stray markdown fences... **P1 — Content quality:**"). `unwrap_artifact()` finds no `<artifact>` tag → returns raw checklist as deliverable. Fix: replaced `[ ]` checkboxes with imperative commands; added explicit ❌ FORBIDDEN rules naming the exact output pattern; strengthened RULES with specific anti-pattern example | `backend/agents/prompts/od-ppt-validator/AGENT.md` | Phase 15 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-015 | 2026-06-17 | PPT generated ignoring user-selected template — brief-analyst doesn't enforce template CSS/theme; clarify loop wastes time | `od-ppt-brief-analyst/AGENT.md` had weak theme_choice rule (model invents names); brief-analyst didn't require CSS class references in visual_suggestion; `od_ppt/workflow.yaml` had `clarify.mode: auto` wasting 38s like prototype. Fix: added MANDATORY template-reading instruction with explicit verbatim theme_choice requirement and CSS class references rule; changed clarify.mode to skip | `backend/agents/prompts/od-ppt-brief-analyst/AGENT.md`, `backend/agents/workflows/od_ppt/workflow.yaml` | Phase 15/4 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-016 | 2026-06-17 | "Invalid presentation output" — PPT composer runs 12.9s → 662 chars (no HTML deck) | Engine clarify-mode routing seam (MAN-04) handles `mode=="auto"` but has no handler for `mode=="skip"`. Planner returns CLARIFY_REQUIRED (normal for od_ppt brief). mode=skip means "wizard already collected context, skip clarification". Without the skip handler, CLARIFY_REQUIRED flows through unchecked → ClarifyEngine fires → user clicks through with no extra answers → agents run with incomplete context → composer produces 662-char stub → isHtml check fails → "Invalid presentation output" | `backend/agents/execution_engine/engine.py` | Phase 4 (MAN-04) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-017 | 2026-06-17 | PPT composer produces 697-char confused validator output (validator: "I don't see an HTML artifact") | `_compose_injection()` in `factory.py` hardcoded a prototype-specific CRITICAL OUTPUT RULES block (section 0) that fires for ANY agent declaring `injects:`. The PPT composer declares `injects:[template, design_system]`, triggering this block. Rule #2 "Every page must have a routed section" (prototype navigation) directly contradicts the PPT AGENT.md output contract (deck slides). The model gets confused and produces a tiny non-HTML response in 6.3s. The validator receives no artifact, responds "I don't see an HTML artifact", and its 697-char bewildered output becomes the final deliverable → isHtml check fails → "Invalid presentation output" | `backend/agents/factory.py` | Phase 7/15 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-018 | 2026-06-23 | KAN-73: hook_run WS events never reach the frontend Audit tab — ectx.event_queue never set + after_step never fired | `KernelServices.emit_hook_event()` calls `getattr(self._ectx, "event_queue", None)` but `ExecutionContext` never has `event_queue` set: `_execute_impl` constructs `ectx` without it and `execute()` never threads the WS queue onto it → `queue = None` → early return → no hook_run WS event. Second: engine only fired `before_step`; `after_step` was never fired (no code path). Third: hook event dict lacked `agent_name`/`step_index` so audit summaries showed raw agent IDs | `backend/agents/execution_engine/engine.py`, `backend/app/api/websocket.py` | Phase 8 (KAN-73) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-021 | 2026-06-30 | KAN-83: Token count dialog in left panel too large — reduce to single compact line | `TokenUsageSummary` rendered a multi-section bordered card (header + input/output breakdown + ratio bar + cost row = ~80px). KAN-83 requires a single line showing only the token count. Replaced the 4-row `rounded-xl border bg-gray-50 px-4 py-3` card layout with a single `flex items-center gap-1.5 flex-wrap` line: ⚡ TOKEN USAGE · 128.7K total · 128.6K input · 11.8K output · ~$0.041 | `frontend/src/components/workflow/TokenUsageSummary.tsx` | Phase 22 (UI) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-022 | 2026-06-30 | KAN-80: Prototype Thinking tab hides full prompts, context sources, and agent-handoff artifacts | `AgentThinkingTab` routes prototype runs to `PrototypePipelineView` (Phase-card layout) which never renders `InputPromptSection`, `ContextSourcesRow`, `ToolCallsSection`, or `OutputPreviewSection`. The data IS captured in agent state via `agent_input` events but PrototypePipelineView silently discards it. User stories pipeline hits the generic `AgentTimelineCard` path which shows everything. Fix: export the 4 sub-components from `AgentThinkingTab`, add `AgentDetailSection` wrapper to `PrototypePipelineView`, wire into all 4 PhaseCards. | `frontend/src/components/results/AgentThinkingTab.tsx`, `frontend/src/components/results/PrototypePipelineView.tsx` | Phase 3 (FR-015 / T043) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-023 | 2026-06-30 | KAN-89: After prototype revision, chaining to user stories shows stale Specification Review gate | `reviewGateData` in `dashboard/page.tsx` is set on `review_gate_ready` and cleared on `review_gate_approved`/reject, but never cleared when a new pipeline starts. `onResetPipeline()` only resets `pipelineState` (useWorkflow hook). After prototype_revision completes with a Human Gate approval, `reviewGateData` stays set. When user chains to user_stories, the new pipeline fires but `DashboardLayout` renders `<ReviewGatePanel>` because `reviewGateData !== null`, blocking the user_stories preview. Fix: clear `reviewGateData(null)` on `pipeline_start` in `handleWebSocketMessage`. | `frontend/src/app/dashboard/page.tsx` | Phase 8 (GATE-01/02) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-024 | 2026-07-01 | KAN-82: Clarify asks fixed irrelevant questions instead of content-aware clarification — all pipelines | SmartPlanner stored `missing_information` as pipeline-generic keys (e.g. `target_audience`, `scope`) regardless of what the brief covered; for long/rich briefs it returned the full `common_missing` list. ClarifyEngine._generate_questions() mapped those keys to hardcoded static question text from QUESTION_LIBRARY with no reference to the actual brief content. Result: a 100-page user-story doc gets asked "Who is the primary audience?" as if no content was provided. | `backend/agents/planner/smart_planner.py`, `backend/agents/execution_engine/clarify_engine.py` | Phase 2/4 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-025 | 2026-07-03 | KAN-82: Clicking "Use" recommendation in QuestionnairePanel doesn't visually select the option | `handleUseRecommended` stored `recommendedAnswer` string directly into `answers[]`, but option highlight checked `selected.includes(option)` — if `recommendedAnswer` text differed even slightly from the option text (case, whitespace), no option lit up. Banner also disappeared instantly since `effective` became truthy, giving no visual feedback. | `frontend/src/components/preview/QuestionnairePanel.tsx` | Phase 2 (UI) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-026 | 2026-07-03 | KAN-90: Clarification step missing Cancel Workflow and Start New Workflow options | QuestionnairePanel had only onSubmitAnswers and onSkip — no escape from the clarify gate. Sending cancel_pipeline alone is insufficient because the backend blocks at await event.wait() in ClarifyEngine; must first submit_questionnaire(skip=true) to unblock the gate, then cancel_pipeline. | `frontend/src/components/preview/QuestionnairePanel.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | Phase 2 (UI) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-027 | 2026-07-03 | KAN-91: File attachment content rendered in textarea — separate content from display | File attach onChange in IdeaInputPage.tsx called setIdeaInput() to inject content into the textarea, making it visible and editable. Chip X removal only removed the visual chip, not the injected text. Added attachedFileContents state; content now stored separately and composed into the pipeline message in handleRun at send time. Chip X also removes content. Pre-existing duplicate initialSelections prop fixed as collateral. | `frontend/src/components/workflow/IdeaInputPage.tsx` | Phase 21 (UI) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-028 | 2026-07-01 | Prototype nav-validation hardening (render_check + static_check), 5 rounds — dynamic-nav/coverage/wrong-section detection; shared route-table resolver (fixes alias/parametric false-positives); blank→null render honesty; require_render load-bearing; A/B/blank/mis-route regression fixtures | Validators mis-judged nav 3 ways: fail-open (`.nav-item`-only + `<a href>`-only → broken hash/onclick/`:id` SPA passed green), false-positive (no route-table resolution → correct alias/`:id` routers failed on `expected==first-segment`), dishonest (blank page coerced to a nav-link name). See IMPL Phase 24 + quick 260701-bob/erg/go2/hqa/kml. | `backend/app/agents/{render_check,static_check,route_table(new),validators/html_render}.py`, `agents/execution_engine/{engine,kernel_services}.py`, `capabilities/{validators/severity,gates/validation,strategies/task_loop}.py`, `workflows/{compiler,plan,prototype/workflow.yaml,prototype_revision/workflow.yaml}`, `app/core/config.py`, `tests/agents/{test_nav_coverage,test_route_table,_scripted_model,test_phase5_fixloop_selection}.py + fixtures/{imc-…-full,imc-…-fixed,blank-nav,mis-route}.html` | Phase 07/08 (VALID) · IMPL Phase 24 (post-ms) | INV-1/3/12/13 ✅ | Done |
| FIX-029 | 2026-07-03 | byv: Prototype "Thinking" tab missing the StartingPoint + Clarifications preamble, and the build checklist flashes "all complete" between tasks | `AgentThinkingTab`'s `isPrototypePipeline` early-return rendered `PrototypePipelineView` alone, skipping the StartingPointCard/ClarificationsCard shown on the main render path; separately `PrototypePipelineView` derived all-done from `buildStatus==="done"` alone, which is briefly true between tasks so the checklist flashed all-complete mid-loop. Fix: render the two existing cards as a preamble above the pipeline view; add a `buildTrulyDone` gate (true only once build is done AND validation has started or the run has stopped) at the terminal sites; `currentTaskIndex` falls back to `realtimeCompletedCount` during the transient-done window so completed tasks stay checked. Backend untouched (FE-only). | `frontend/src/components/results/AgentThinkingTab.tsx`, `frontend/src/components/results/PrototypePipelineView.tsx` | Phase 3 (Thinking-view) · quick-260703-byv | INV-1/3/12/SC-001 ✅ | Done |
| FIX-030 | 2026-07-03 | d4v: `POST /api/prototype/run` rejected any brief over 8000 chars (422) — blocked large briefs and attached-file content | `RunRequest.brief` was declared `max_length=8000`, a legacy straggler from the prototype era; the app-wide `BRIEF_MAX_CHARS` (450k, ~150k tokens) already governs the other ingest paths but this endpoint was never aligned, so long briefs 422'd before reaching the engine. Fix: source the field cap from `settings.BRIEF_MAX_CHARS` instead of the hardcoded 8000; added a unit test pinning the cap to the setting. | `backend/app/api/prototype_templates.py`, `backend/tests/unit/test_prototype_run_request.py` | Phase 4 · quick-260703-d4v | INV-1/3/12/SC-001 ✅ | Done |
| FIX-031 | 2026-07-03 | ISS-029 (KAN-63 regression): od_ppt example.html leaked into the deck PLANNER (od-ppt-brief-analyst), not just the builder — degraded planning and left the od_ppt characterization golden red for ~3 weeks | KAN-63 (b5f5885e, Jun 15) widened the opendesign example.html gate from `is_builder` to `(is_builder or "workspace" in spec_tools)`; the `"workspace"` proxy was too broad and swept in the planner-shaped od-ppt-brief-analyst (which declares `tools:[workspace]`), feeding a full worked HTML example to a planner (violates the Phase-7 "planners must not see example.html" rule), and the od_ppt event golden (which pins context_message) was never regenerated so INV-3 diverged. Fix (B-explicit): re-key the gate on a DECLARED inject — `(is_builder or "template_example" in injects)` — and add `template_example` to od-ppt-composer's `injects` so the composer opts in explicitly while the brief-analyst stays example-free; regenerated ONLY the od_ppt golden (composer gains the block, brief-analyst unchanged, other 4 goldens byte-identical). | `backend/agents/capabilities/context_providers/opendesign.py`, `backend/agents/prompts/od-ppt-composer/AGENT.md`, `backend/tests/agents/test_context_providers.py`, `backend/tests/agents/characterization/golden/od_ppt.events.json` | Phase 7 (example gate) · debug ISS-029 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-032 | 2026-07-03 | v7a: od_ppt deck builder received only the first 8000 chars of example.html — for real deck templates (25k–94k chars) that is partial CSS and ZERO `<section>` slides with no nav, despite the prompt ordering it to "clone example.html" (companion: trimmed od-ppt-brief-analyst's dead "full DESIGN.md body" claim) | example.html was truncated to 8000 at TWO redundant points (`od_context.get_example_html` default `max_chars=8000`, plus a second `[:8000]` in the opendesign provider); every deck template except `simple-deck` exceeds 8000 and the median deck lost ~85%. Separately the brief-analyst body claimed it receives "the ACTIVE DESIGN SYSTEM — full DESIGN.md body" but it declares `injects:[template]` so DESIGN.md is never delivered — a dead claim. Fix: introduce one module constant `EXAMPLE_MAX_CHARS = 120_000` as the `get_example_html` default and remove the redundant provider `[:8000]` (single cap source, INV-12); reword the brief-analyst body to reference the design system symbolically (real tokens applied downstream by the composer). INV-3-neutral: the characterization fixture example is 4217 chars so it is returned whole before and after — all 5 goldens byte-identical, no regen. | `backend/agents/execution_engine/od_context.py`, `backend/agents/capabilities/context_providers/opendesign.py`, `backend/tests/agents/test_context_providers.py`, `backend/agents/prompts/od-ppt-brief-analyst/AGENT.md` | Phase 7 (od_ppt context) · quick-260703-v7a | INV-1/3/12/SC-001 ✅ | Done |
| FIX-033 | 2026-07-04 | Files tab shows no run-input file for revision runs — prompt.md derived only from parsed.brief | `runInputFileRows` emitted prompt.md only from `parseRunInput(runInput).brief`; a revision parses to `revisionInstruction` with empty brief → no prompt.md (live or reopened). Fix: derive the primary row from `parsed.revisionInstruction` OR `parsed.brief` (parsed-shape dispatch, SC-001; reuses parseRunInput, INV-12); filename stays prompt.md for all runs. | `frontend/src/components/results/FilesTab.tsx`, `frontend/src/components/results/FilesTab.runInput.test.tsx` | Phase 25 (Run-inputs surfacing) · quick | INV-1/3/12/SC-001 ✅ | Done |
| FIX-035 | 2026-07-04 | Run cost under-reported ~4x (Haiku 4.5) to ~20x (Opus) — both engine.py:2277 + websocket.py:1993 hardcoded Claude-3-Haiku $0.25/$1.25/M for every model | Both cost sites (the engine `pipeline_complete` event + the persisted `workflow_runs.token_usage`) computed cost with an inline `(_tok_in * 0.00000025) + (_tok_out * 0.00000125)` — Claude-3-Haiku rates applied to EVERY model, so a Sonnet/Opus run under-reported 4x–20x. Fix: new kernel-pure `model_pricing.py` (per-family `MODEL_PRICING` + `_canonical` + `_regional_premium` +10% eu./us./apac + cache read/write-5m/write-1h tiers + shared `estimate_cost_usd`); BOTH sites route through it (INV-12; SC-001 no per-model branch); `model_id` → `BEDROCK_INFERENCE_PROFILE_ID` fallback; cache-token surfacing a flagged follow-up (ISS-032). INV-3 golden-neutral (cost + model_id are stripped keys — 5 goldens byte/event-identical, no regen). | `backend/agents/capabilities/model_pricing.py`, `backend/agents/execution_engine/engine.py`, `backend/app/api/websocket.py`, `backend/tests/agents/test_model_pricing.py` | quick-260704-t2x | INV-1/3/12/13 · SC-001 ✅ | Done |
| FIX-036 | 2026-07-04 | ISS-032 — run cost not cache-discounted: the shared deep-agent runner dropped the `input_token_details` cache split so BOTH cost sites priced cache-reads at 1x (over-report once FIX-034 caching is ON in prod) | langchain_aws sets `usage_metadata.input_tokens` to the TOTAL (incl. cache) with the split in `input_token_details={cache_read, cache_creation}` (bedrock_converse.py), but the runner forwarded only input/output → `estimate_cost_usd` saw cache=0 → cached input billed 1x not 0.1x. Fix: the runner surfaces `input_token_details` (cache_read/cache_creation) into the usage event + text-only TokenUsage → the engine accumulates per-agent → `results` + `agent_complete` + run totals on `pipeline_complete` → BOTH cost sites price the UNCACHED split (`input_tokens=max(0, total − cache_read − cache_write)` + cache_read/write tiers + cache_ttl) via the ONE shared `estimate_cost_usd` (INV-12; SC-001, no workflow/agent branch); golden-neutral via additive `_VOLATILE_STRIP_KEYS` (4 new keys stripped, no regen). | `backend/app/agents/deep_agent_runner.py`, `backend/agents/execution_engine/engine.py`, `backend/app/api/websocket.py`, `backend/tests/agents/characterization/_normalize.py`, `backend/tests/agents/test_iss032_cache_tokens.py` | quick-260704-ttk | INV-1/3/12/13 · SC-001 ✅ | Done |
| FIX-037 | 2026-07-04 | Cache-token breakdown not shown in UI — backend (ISS-032/FIX-036) emits per-run `total_cache_read_tokens`/`total_cache_write_tokens` + already-discounted `estimated_cost_usd`, but `TokenUsageSummary` showed only total/input/output/cost | FE never consumed the already-emitted cache fields (grep of `frontend/src` for cache tokens = nothing); no reopen path mapped them either. Fix (FE-only): thread the cache fields (types + `useWorkflow` `pipeline_complete`/`agent_complete` parse with `\|\| prev.* \|\| 0` + `api.ts` persisted keys made type-visible, no logic change) + render a `⚡ N cached (X%)` segment after the input figure when `cache_read > 0` (byte-identical render when 0/undefined; `pct = round(cacheRead / max(1, input) * 100)`; optional `· N written` when `cache_write > 0`); NO FE dollar/per-model math (INV-12) — cost already discounted by FIX-036; dollar-savings deferred (ISS-034). | `frontend/src/types/index.ts`, `frontend/src/hooks/useWorkflow.ts`, `frontend/src/components/workflow/TokenUsageSummary.tsx`, `frontend/src/components/workflow/TokenUsageSummary.cache.test.tsx` | quick-260704-uvs | INV-1/3/12 · SC-001 ✅ | Done |
| FIX-038 | 2026-07-05 | t2x regression: model_pricing.py hardcoded model-family literals violated INV-12 single-model-id-source and broke test_model_catalog::test_single_source_grep (passed at baseline eb3ccced, failed after t2x). | Fix (proper, no test-loosen): co-located a frozen Pricing dataclass + pricing field on ModelEntry in model_catalog.py (the single source); model_pricing.py now derives each model's Pricing FROM the catalog (exact get + region/version-normalized fallback + cheap default) and keeps only _regional_premium + estimate_cost_usd — ZERO model-id literals. Reconciliation pin ($24.85) preserved; goldens byte-identical; lint 4/0. | `backend/agents/capabilities/model_catalog.py`, `backend/agents/capabilities/model_pricing.py`, `backend/tests/agents/test_model_pricing.py` | quick-260705-ed8 | INV-1/3/12/13 · SC-001 ✅ | Done |
| FIX-047 | 2026-07-07 | KAN-100: ReviewGatePanel stays interactive after Stop + Redo resumes cancelled pipeline — 4 root causes fixed | (1) `dashboard/page.tsx`: no `case "pipeline_cancelled"/"pipeline_failed"` to clear `reviewGateData` → panel stayed; (2) DashboardLayout `reviewGateData ?` had no `isPipelineRunning` guard; (3) `websocket.py` `approve_review` handler had no terminal state check — Redo could unblock gate; (4) `engine.py` `_run_review_gate` `await event.wait()` not cancel-aware — Stop never interrupted the gate | `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/layout/DashboardLayout.tsx`, `backend/app/api/websocket.py`, `backend/agents/execution_engine/engine.py` | Phase 16/23 (terminal-state/REDO-GATE) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-048 | 2026-07-07 | KAN-101: Spec revision loop — "Update the Specs" button on analyze gate triggers specify → plan → analyze sub-pipeline with analysis report as context | No `update_specs` action in any layer: websocket.py had no branch, `_run_review_gate` had no signal, inline gate consumer had no sub-pipeline handler, no context injection in `_compose_context_message`, no FE button | `backend/app/api/websocket.py`, `backend/agents/execution_engine/engine.py`, `backend/agents/prompts/prototype-specify/AGENT.md`, `frontend/src/components/preview/ReviewGatePanel.tsx`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/app/dashboard/page.tsx` | Phase 23 (REDO-GATE pattern) / KAN-101 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-049 | 2026-07-10 | Live agent output not visible while a prototype agent runs — the Steps L2 detail "live" card was blank for every running agent (spec-writer / plan / analyze / build) | The engine emits only `agent_chunk` (the model's streamed output) per agent, never a separate `agent_thinking` event, so `agent.thinkingText` is ALWAYS empty — but `AgentDetailPanel` fed its live card from `thinkingText`, so a running agent showed a blank "Reasoning (live)" cursor with no text. Fix (FE-only): feed the live `agent.output` (from `agent_chunk`) into the card instead, labelled "Output (live)", scrollable + auto-follows the streaming tail; the completed output still renders via `OutputPreviewSection`. Verified fail-before/pass-after with a new spec. | `frontend/src/components/results/AgentDetailPanel.tsx`, `frontend/src/components/results/AgentDetailPanel.liveOutput.test.tsx` (new) | Phase 39/42 (run-screen Steps detail) · commit `182200b1` | INV-3 (FE-only, no golden) · SC-001 ✅ | Done |
| FIX-050 | 2026-07-10 | (a) React duplicate-key errors (surfaced as the dev "N Issues" badge / SyntaxError) on reopened prototype / od_prototype runs from history; (b) the Deck-QA report text bled faintly through behind the rendered PPT slides | (a) Build-loop agents all share the `prototype-build` id, so `RunDetailPage`'s `key={agent_id ?? idx}` fallback never fired and React logged duplicate keys — fixed to an `agent_id`+`idx` composite key. (b) `PPTPreview`'s deck `<!DOCTYPE>`/`<html>` extraction used a loose search that matched the Deck-QA agent's inline-quoted `<!DOCTYPE html>` in its PREPENDED markdown report (≈char 52) instead of the real deck (≈char 1130), leaking the report into the deck iframe — fixed with a line-anchored regex + a trailing-after-`</html>` strip. Both FE-only, found via live Bedrock UI testing. | `frontend/src/components/history/RunDetailPage.tsx`, `frontend/src/components/preview/PPTPreview.tsx` | Phase 39/42 (run / history UI) · commit `5bd46942` | INV-3 (FE-only, no golden) · SC-001 ✅ | Done |
| FIX-046 | 2026-07-07 | KAN-99: Prototype task checklist shows all tasks complete before build agent finishes — last task_progress fires before fix-loop | `currentTaskIndex` used `realtimeCompletedCount` directly; when last `task_progress` fires `realtimeCompletedCount === totalTasks` → `isDone` true for all tasks despite agent still running. Cap `currentTaskIndex` to `Math.min(realtimeCompletedCount, totalTasks-1)` when `!buildTrulyDone` so last task stays in active/spinner state until validate starts or `isRunning=false`. | `frontend/src/components/results/PrototypePipelineView.tsx` | Phase 3 (Thinking-view) · quick-260703-byv | INV-1/3/12/SC-001 ✅ | Done |
| FIX-045 | 2026-07-06 | KAN-98: ReviewGatePanel stale editedContent after Redo — prior edit forwarded instead of fresh output | `useEffect([output, gateKey])` reset `submitted`/`redoInstructions`/`showRejectConfirm` but NOT `editedContent` or `hasEdits`. After Redo delivered new output, stale `editedContent` (from round 1) differed from new `output` → `hasEdits=true` → `handleApprove` sent stale edit as if user had edited in round 2. Fix: add `setEditedContent(output)` + `setHasEdits(false)` to the existing `useEffect`. | `frontend/src/components/preview/ReviewGatePanel.tsx` | Phase 23 (REDO-GATE) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-044 | 2026-07-06 | KAN-97: Blank right panel after questionnaire submit — PlanningOverlay blocked by !activePipelineRunId guard | After submit/skip, `questionnaireQuestions=[]` and `questionnaireLoading=false` cleared the questionnaire panel, but `activePipelineRunId` stayed set → `!activePipelineRunId` in the PlanningOverlay condition was false → fell through to empty PreviewPanel. Fix: remove `!activePipelineRunId` from PlanningOverlay condition. QuestionnairePanel already has its own `(questionnaireLoading || questions.length > 0)` guard so it doesn't need this protection. | `frontend/src/components/layout/DashboardLayout.tsx` | Phase 2/18 (Universal Engine / Planning Overlay) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-043 | 2026-07-06 | KAN-96: Workflow History always opens detail view for running runs — no active-run awareness | `WorkflowHistoryProps` had no `activeRunId`/`onViewRunningPipeline` props; `handleSelectRun` opened the history detail for every run unconditionally. Added two props, branched in `handleSelectRun` (run.id === activeRunId → navigate to execution), and passed `pipelineState?.pipelineRunId` + `setMainView("execution")` from DashboardLayout | `frontend/src/components/history/WorkflowHistory.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | Phase 18 (History UX) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-042 | 2026-07-06 | KAN-95: Reject & cancel pipeline leaves user stranded on execution view — onRejectReview had no navigation | `onRejectReview` in page.tsx only sent the WS message and cleared `reviewGateData`; no `setMainView("home")` or `onResetPipeline()` call. `cancelNavigatingHomeRef` was never set so `pipelineState.isRunning` effect would snap back to execution. Added `handleRejectReview` wrapper in DashboardLayout (mirrors `handleCancelWorkflow` pattern from KAN-90): sets `cancelNavigatingHomeRef`, calls `setMainView("home")`, calls `onResetPipeline()`, then delegates to `onRejectReview` for WS send + `reviewGateData` clear. | `frontend/src/components/layout/DashboardLayout.tsx` | Phase 8/23 (GATE/REDO-GATE) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-041 | 2026-07-06 | KAN-94: Blank Specification Review panel fires before agents run when user deselects all gates + empty-state UX + ReviewGatesSection discoverability | Declared `gates:[human]` on prototype steps bypassed per-run gate_agent_ids deselection: `_should_gate` returned False → `inline_gated=False` → WR-02 dedupe not triggered → pre-step `human` gate fired with `last_streamed=""` → blank `review_gate_ready`. Fix: extend WR-02 skip to also cover when `ectx.gate_agent_ids is not None` and agent not in that list. Also improved empty-state UX (amber icon + Redo guidance + de-emphasized "Continue anyway") and ReviewGatesSection opens expanded when default gates are pre-checked. | `backend/agents/execution_engine/engine.py`, `frontend/src/components/preview/ReviewGatePanel.tsx`, `frontend/src/components/workflow/ReviewGatesSection.tsx` | Phase 8/23 (GATE/REDO-GATE) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-040 | 2026-07-06 | KAN-93: Notification Panel shows raw context block text for chained/revision runs — addRunningNotification called with raw enrichedInput before marker stripping | 5 addRunningNotification call sites in DashboardLayout.tsx passed `enrichedInput.slice(0,60)` or `message.slice(0,60)` without stripping injected `=== CONTEXT FROM PREVIOUS ===` / `=== EXISTING PROTOTYPE HTML ===` markers. Fix: use already-computed `chainBrief`/`historyBrief` (stripped) in chain handlers; apply `parseRunInput()` in handleRunPipeline, handleQuestionnaireSubmit, handleQuestionnaireSkip | `frontend/src/components/layout/DashboardLayout.tsx` | Phase 22 (notifications) · Phase 25 (parseRunInput) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-039 | 2026-07-06 | KAN-92: Workflow history incorrect titles — 3 root causes in websocket.py: wizard-chain reuses source title, run_revision never calls title gen, legacy revision placeholder shows raw HTML marker | (1) `_generate_workflow_title` wizard-chain path wrote source pipeline's Title verbatim with no pipeline_type suffix; (2) `_handle_revision_execution` set `title=f"Revision: {instruction[:50]}"` and never scheduled `_generate_workflow_title`; (3) `_handle_workflow_execution` WorkflowRun placeholder fell through to `or content` for revision messages starting with `=== EXISTING … ===`, showing raw HTML marker for 2-5s | `backend/app/api/websocket.py` | Phase 14/16/22 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-034 | 2026-07-04 | Bedrock prompt caching silently OFF + enable-only extended-thinking knob | deepagents' built-in AnthropicPromptCachingMiddleware caches ONLY ChatAnthropic, but prod runs ChatBedrockConverse → every build re-sent a ~45-68k fixed prefix uncached across ~300 turns (5-21M input tok). Fix: a provider-agnostic `_BedrockCachePointsMiddleware` sets model_settings cache_control on ChatBedrockConverse requests (config-gated BEDROCK_PROMPT_CACHE_ENABLED default ON, BEDROCK_PROMPT_CACHE_TTL '5m') so langchain_aws._apply_cache_points appends cachePoints ≈ 55-80% cheaper billed input; plus a THINKING_BUDGET_TOKENS knob (enable-only, default 0) threading a clamped thinking budget into both provider branches of build_model. | `backend/app/core/config.py`, `backend/app/agents/model_factory.py`, `backend/app/agents/deep_agent_runner.py`, `backend/tests/agents/test_bedrock_cache_and_thinking.py` | quick-260704-p10 | INV-1/3/12/13 · SC-001 ✅ | Done |
| FIX-039 | 2026-07-07 | OD template + PPT gallery previews slow — cards render a static thumbnail `<img>`, falling back to live HTML+JS iframe rendering when absent | Each gallery card mounted a sandboxed `<iframe sandbox="allow-scripts">` that fully renders `example.html` at 1280x720 (parse+style+layout+paint+JS-exec+asset fetches) just for a ~130px thumbnail. Rendering N full HTML documents is the gallery's dominant cost. | `frontend/src/components/workflow/prototype/TemplateGallery.tsx`, `frontend/src/components/workflow/prototype/TemplateCard.tsx`, `frontend/src/components/workflow/ppt/PPTTemplateGallery.tsx`, `frontend/src/lib/prototype-api.ts`, `frontend/src/lib/ppt-api.ts` | Phase 4 (OD catalog UI) | INV-3 golden-neutral (FE-only; catalog thumbnails, not the deliverable renderer) ✅ | Done |
| FIX-042 | 2026-07-08 | `GET /api/{prototype,ppt}/templates/{id}/thumbnail` returns 500 (not 404) when a thumbnail file is missing at request time | `get_template_thumbnail_path` trusted the `has_thumbnail` flag, which is computed once by the `lru_cache(maxsize=1)` `_all_templates()` at process start. A thumbnail deleted (or generated) after startup left the flag stale → the function returned a path to a missing file → `FileResponse` `os.stat`'d it mid-response → `FileNotFoundError` → `RuntimeError: File ... does not exist` → 500. Fix (backend-only): re-check `path.is_file()` on disk at serve time; return `None` (→ existing 404 branch) when the file is gone, so the gallery falls back to the FIX-041 live iframe. | `backend/app/services/od_loader.py` | Phase 4 (OD catalog UI) · builds on FIX-039/040/041 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-041 | 2026-07-08 | OD/PPT gallery card shows a broken/blank image when a thumbnail 404s — no fallback to the live iframe unless `has_thumbnail` is already false | The thumbnail `<img>` in `TemplateCard` and `CompactPPTCard` had an `onLoad` but NO `onError` handler; the thumbnail-vs-iframe choice keyed solely off the backend `has_thumbnail` flag. When that flag is stale (thumbnail generated at build time, not committed — FIX-040) or the file 404s at request time, the `<img>` fails silently and the card sticks on the pulse placeholder / broken image instead of degrading to the FIX-039 live iframe. Fix (FE-only): add a `thumbnailError` state; on `<img>` `onError`, set it (and force-mount the iframe), which nulls `thumbnailUrl` so the existing iframe fallback path renders. | `frontend/src/components/workflow/prototype/TemplateCard.tsx`, `frontend/src/components/workflow/ppt/PPTTemplateGallery.tsx` | Phase 4 (OD catalog UI) · builds on FIX-039/040 | INV-3 golden-neutral (FE-only; catalog thumbnails, not the deliverable renderer) ✅ | Done |
| FIX-040 | 2026-07-07 | OD gallery thumbnails generated at BUILD time (backend Docker image) + served via backend endpoint; missing ⇒ live iframe fallback | The `<img>` fast-path needs a pre-rendered screenshot. Generated at backend image build (Playwright/Chromium already installed for render_check; OpenDesign tree baked at /app/opendesign), NOT committed — so absent thumbnails degrade to the FIX-039 live iframe. | `backend/app/services/od_loader.py`, `backend/app/api/prototype_templates.py`, `backend/app/api/ppt_templates.py`, `backend/scripts/generate_template_thumbnails.py` (NEW), `backend/Dockerfile`, `.gitignore` | Phase 4 (OD catalog UI) | INV-3 golden-neutral; lint-imports 4/0; no committed binaries ✅ | Done |

---

## Detailed Fix Entries

*Entries are appended below after each `/velocity-ai-fix` session.*

---

---

### FIX-126 — KAN-124: Auto-fill recommended answers on skip + no-questions contracts for 9 agents

**Date:** 2026-07-27
**Triggered by:** `/velocity-ai-fix KAN-124 — do add the changes and fixes based on above analysis`

#### Root Cause

Two independent root causes, both confirmed by code inspection and production evidence.

**Root Cause 1 (backend):** `clarify_engine.py:_merge_answers()` built `answer_map` exclusively from the user-submitted `responses` list. On skip (`force_proceed=True`), that list is `[]`, so `answer_map = {}` and zero entries were added to `planning_context["explicit_constraints"]`. Every downstream agent therefore ran with no context at all, producing generic or question-asking output. The `recommended_answer` field — generated by the LLM for every question at line 571 — was stored on each question dict but **never read back** by `_merge_answers()`.

**Root Cause 2 (prompts):** A full audit of all four affected pipeline families found 9 AGENT.md files with no "NEVER ask clarifying questions" output contract. The `user-story-revision-agent` was confirmed broken in production screenshots: given "add payment integration through paypal", it output "What is the intended pricing model?" as prose instead of the revised backlog.

#### Phase Context
- **Phase(s) involved:** Phase 3 (ClarifyEngine / ISS-027), Phase 15 (prompt output contracts pattern)
- **Deleted code verified (not resurrected):** No deleted code involved — this is a missing feature (auto-fill) and missing prompt rules
- **Locked decisions respected:** INV-1 (auto-fill keys only on generic `recommended_answer` field, never pipeline_type); INV-3 (characterization goldens not affected — scripted harness submits skip with `responses=[]` and no questions, so `_merge_answers` is called with `questions=[]` → the new auto-fill loop iterates zero times, zero change); SC-001 (prompt body edits only, zero engine edits)

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `backend/agents/execution_engine/clarify_engine.py` | `_merge_answers()`: before the main loop, build a recommended-answer fallback map from `q["recommended_answer"]` for every question not in `answer_map`. User answers always take strict priority. | Ensures agents always receive `explicit_constraints` populated from recommended answers when user skips or partially answers |
| `backend/agents/prompts/user-story-revision-agent/AGENT.md` | Added `## OUTPUT CONTRACT` section at the top of the body with explicit NEVER-ask rule | CONFIRMED BROKEN in production — was outputting inline questions as deliverable |
| `backend/agents/prompts/domain-analyst/AGENT.md` | Added `NEVER ask clarifying questions` contract after role line | user_stories P3 — medium risk |
| `backend/agents/prompts/epic-architect/AGENT.md` | Added `NEVER ask clarifying questions` contract after role line | user_stories P3 — medium risk |
| `backend/agents/prompts/story-estimator/AGENT.md` | Added `NEVER ask clarifying questions` contract after role line | user_stories P3 — low risk |
| `backend/agents/prompts/nfr-specialist/AGENT.md` | Added `NEVER ask clarifying questions` contract after role line | user_stories P3 — low risk |
| `backend/agents/prompts/backlog-reviewer/AGENT.md` | Added `NEVER ask clarifying questions` contract after role line | user_stories P3 — medium risk |
| `backend/agents/prompts/backlog-compiler/AGENT.md` | Added `NEVER ask clarifying questions` contract after role line | user_stories P3 — low risk |
| `backend/agents/prompts/od-ppt-revision-agent/AGENT.md` | Added explicit NEVER-ask rule at top of body | P4 — had implicit artifact contract but no explicit rule |
| `backend/agents/prompts/prototype-revision-agent/AGENT.md` | Added explicit NEVER-ask rule at top of body | P4 — had implicit tool-call workflow but no explicit rule |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): auto-fill keys on generic `recommended_answer` field, all prompt changes are body-only with no pipeline_type literal
- **INV-3** (golden parity): characterization goldens call `_merge_answers(questions=[], responses=[])` via the scripted harness — the new fallback loop iterates over an empty list and does nothing, byte-identical
- **INV-12** (no duplication): `_merge_answers` is the single merge function, no duplicate added
- **SC-001** (zero engine edits): all 9 prompt changes are AGENT.md body-only; the backend change is a single method in `clarify_engine.py`, not the engine kernel

#### Verification
- Python diagnostics: 0 errors on `clarify_engine.py`
- `_merge_answers` read back and confirmed correct: fallback loop runs before the main annotation loop, user answers win, empty `questions` list is safe
- All 9 AGENT.md files read back and confirmed: each has the explicit no-questions contract in the right position (top of body, after role introduction)
- Pipelines already covered (od_ppt, prototype/od_prototype) are untouched — verified by not editing their AGENT.md files

#### Notes
- The `recommended_answer` for static-library questions defaults to `options[-1]` ("No preference") — this is a weak fallback. Future improvement: improve static-library defaults to context-aware values.
- The INV-3 guarantee rests on the scripted harness passing `questions=[]` to `_merge_answers`. If a future test passes non-empty questions + skip, the auto-fill WILL add `explicit_constraints` entries — this is correct behavior, not a regression. The golden test suite tests the full pipeline, not `_merge_answers` in isolation.
- Pipelines still fully covered without changes: `od_ppt` (all 3 agents), `prototype`/`od_prototype` (all 5 agents), `prototype_revision` (prototype-revision-validate).

---

### FIX-124 — KAN-123: Security gate failure UX

**Date:** 2026-07-27
**Triggered by:** `/velocity-ai-fix KAN-123` — implementing error/failure messages for security gate failures

#### Root Cause

Three separate gaps, all FE-only:

1. **AuditTab missing `hook_runs` source** (`AuditTab.tsx` lines 408-490): The 3-endpoint parallel fetch (`gate_events` / `validation_results` / `exec_runs`) never included `getRunHookRuns`. The `hook_runs` table is where `secret_scan` blocking events are written (outcome=`"block"`, hook=`"secret_scan"`), which is the source of the "Secret scan — BLOCKED write to .env" security row the mock shows. Without this 4th fetch, the Security category in the Audit tab was always empty. The `hookRuns` prop was documented as "dormant legacy" and removed from the render path, but the underlying endpoint exists (`/api/runs/{id}/hook-runs`, KAN-73) and was never called by the tab.

2. **RunChatLane "What went wrong" shows only generic agent names** (`RunChatLane.tsx`): The failed terminal card's bullet list built only `resolveAgentNames(failedIds)` + one `sanitizeError`. The mock shows 3 specific security-derived bullets: "Secret scan blocked a write…", "Code execution denied…", "Validation found N critical…". These map to: `pipelineState.hookRuns` blocked scans (already populated by `hook_run` WS events in `useWorkflow.ts`), failed-agent exec-denied error strings, and per-agent `validationIssues` CRITICAL/HIGH severity.

3. **StepsOverviewSpine has no inline security gate explanation card** (`StepsOverviewSpine.tsx`): When a security gate blocks an agent (`status="error"`, error string contains "security gate"/"exec denied"/etc.), the Steps tab showed only the generic red dot. The mock shows an inline "Blocked by the security gate" explanation card beneath the failed agent row.

#### Phase Context
- **Phase(s) involved:** Phase 8 (HOOK-01/04 — hook_runs), Phase 13 (F3 pipeline_failed), Phase 16 (ISS-016 terminal failure card)
- **Deleted code verified (not resurrected):** `hookRuns` prop on `AuditTab` was documented as "dormant legacy" — the component itself was always correct, just not calling the endpoint. This fix adds the 4th fetch — does NOT resurrect the prop path.
- **Locked decisions respected:** INV-1 (all detection keys on generic outcome/hook/error string patterns, never agent-id/workflow-name literals); INV-3 (FE-only change, no backend/engine/golden change); INV-12 (reuses `getRunHookRuns` that already existed in `api.ts`; single `deriveSecurityBullets` function).

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/results/AuditTab.tsx` | Added `getRunHookRuns` to the 4-endpoint parallel fetch; added `buildHookLabel` + `buildHookDetailRows` helpers; mapped `hook_runs` rows to `AuditRow` with Detector/Match/Action/Outcome detail fields | Surfaces secret_scan block events as Security-category Audit rows with the expanded detail the mock shows |
| `frontend/src/components/results/StepsOverviewSpine.tsx` | Added `SecurityGateBlockedCard` component + `isSecurityBlock()` helper; render the card after a failed agent row when error string indicates a security/exec/hook block | Shows the inline "Blocked by the security gate" explanation card in the Steps trace |
| `frontend/src/components/chat/RunChatLane.tsx` | Added `deriveSecurityBullets(state)` helper; replaced generic bullets in the failed terminal card with structured security bullets when available (falls back to the existing generic path for non-security failures) | Shows "Secret scan blocked…", "Code execution denied…", "Validation found N critical…" bullets from live pipelineState |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): all detection keys on generic signals (outcome string, hook name patterns, agent error strings, severity field values) — no workflow-name/agent-id literal
- **INV-3** (golden parity): FE-only change — zero backend/engine/manifest/golden files touched; verified via diagnostics
- **INV-12** (no duplication): reused existing `getRunHookRuns` from `api.ts`; single `deriveSecurityBullets` function; `SecurityGateBlockedCard` is the one card component for this
- **SC-001** (zero engine edits): pure FE presentation layer change

#### Verification
TypeScript diagnostics: 0 errors on all 3 modified files. Logic verified:
- `AuditTab`: `getRunHookRuns` is called in the `Promise.all` with a `.catch(() => ({ hook_runs: [] }))` fallback so AuditTab still renders on 404/error; `buildHookLabel` produces human-readable labels matching the mock (e.g. "Secret scan — BLOCKED before write to .env"); `buildHookDetailRows` builds Detector/Match/Action/Outcome rows from the real `detail` JSON.
- `StepsOverviewSpine`: `isSecurityBlock` checks for `/security.*gate|blocked.*security|exec.*denied|exec.*off|secret.*scan|secret.*blocked|credential.*blocked|hook.*block/i` patterns.
- `RunChatLane`: `deriveSecurityBullets` uses `pipelineState.hookRuns` (populated by `hook_run` WS events already in `useWorkflow.ts`) for scan bullets, agent `.error` strings for exec-denied bullet, and `.validationIssues` for validation bullet.

#### Notes
- The `hook_runs` WS event (`case "hook_run"`) is already handled in `useWorkflow.ts:720-734` and populates `pipelineState.hookRuns`. No backend change needed.
- The `getRunHookRuns` endpoint was already implemented (KAN-73, backend `runs.py:1214`) and the `HookRunsResponse` interface already existed in `api.ts:1281` — this fix was purely about calling it.
- `buildHookDetailRows` produces a "high-entropy × known key formats" Detector fallback for secret_scan hooks when the `detail.detector` field is absent (matches the mock's display exactly).

---

**Date:** 2026-07-24
**Triggered by:** `/velocity-ai-fix` — user text not showing and no loading indication for some workflows

#### Root Cause
FIX-118 removed the pre-intent `sendMessage` echo from `handleFreeText` in `RunChatLane.tsx` to fix the double-version bug. That fix was correct for the `complete` state — an undecorated `sendMessage` on a terminal run triggers `CHANNEL_REVISION` immediately. However, the fix also removed the user bubble echo for ALL intents:

- **"ask" intent** still worked because `sendMessage(text, attachments, { concierge: true })` was called after classification — that `sendMessage` adds the optimistic bubble + routes to Concierge (not `CHANNEL_REVISION`)
- **"revise" intent** never called `sendMessage` — user text never appeared  
- **"chain" intent** never called `sendMessage` — user text never appeared

The root tension: `sendMessage` on a terminal run without `{ concierge: true }` triggers `CHANNEL_REVISION`. Adding it to every path would route revise/chain as Concierge turns.

**Fix:** Add `addOptimisticMessage` to `useRunChat` — a FE-only function that adds a user bubble to local state without any backend call. Call it in `handleFreeText` before the classify-intent LLM round-trip. For the "ask" path, pass the returned `messageId` as `options.existingMessageId` to `sendMessage` so it reconciles the existing bubble instead of creating a duplicate.

#### Phase Context
- **Phase(s) involved:** Phase 31 (CHATUI-01 — `useRunChat` transcript), Phase 29 (chat backbone / mechanical router / `CHANNEL_REVISION`), Phase 43 (A.1 CRUX — Concierge seam)
- **Deleted code verified (not resurrected):** No deleted code resurrected
- **Locked decisions respected:** INV-12 (addOptimisticMessage is new, not a fork); SC-001 (all paths generic — no workflow-name branch)

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/hooks/useRunChat.ts` | Added `addOptimisticMessage(text, attachments) → string` to `UseRunChatReturn` interface and implementation; added `existingMessageId?: string` to `SendMessageOptions`; `sendMessage` uses `existingMessageId` when supplied to reconcile instead of minting a new id | Provides a FE-only bubble with no backend side-effect |
| `frontend/src/components/chat/RunChatLane.tsx` | Added `addOptimisticMessage?` prop to `RunChatLaneProps` and `RunChatLane` function; updated `handleFreeText` to call it immediately before classify-intent, then pass `existingMessageId` to `sendMessage` for the ask path | User text visible immediately for all intents; TypingIndicator fires for all complete-state sends |
| `frontend/src/components/layout/DashboardLayout.tsx` | Added `addOptimisticMessage?` prop to `DashboardLayoutProps`; destructured from function params; passed to `<RunChatLane addOptimisticMessage={addOptimisticMessage} />` | Wires the function from page.tsx to the RunChatLane |
| `frontend/src/app/dashboard/page.tsx` | Destructured `addOptimisticMessage: addRunChatOptimisticMessage` from `useRunChat`; passed to `<DashboardLayout addOptimisticMessage={addRunChatOptimisticMessage} />` | Sources the function from the hook |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): Not affected — all paths key on generic `runState`/intent
- **INV-3** (golden parity): Not affected — FE-only change, no backend/engine touch
- **INV-12** (no duplication): `addOptimisticMessage` is a NEW function with a distinct purpose (FE-only echo); `sendMessage` is unchanged except for the `existingMessageId` reconciliation path (no fork in behavior)
- **SC-001** (zero engine edits for new workflows): Not affected

#### Verification
- For `complete` state: user types → text appears immediately as user bubble + TypingIndicator shows while LLM classifies
- For "ask" intent: existing bubble reconciled when sendMessage called with existingMessageId (no duplicate)
- For "revise" intent: bubble stays visible, confirm chip appears
- For "chain" intent: bubble stays visible, chain picker / onSuggestion fires
- For all non-complete states (building/clarify/gate/terminal): `sendMessage(text, attachments)` still called directly — bubble + behavior unchanged

#### Notes
- The `existingMessageId` option in `sendMessage` is a new reconciliation mechanism. The guard `prev.some((m) => m.id === messageId)` in `sendMessage` means if the bubble was already added optimistically, it won't be duplicated.
- For the fast-path `matchChainTarget` (exact named-target, no LLM), we still return early without an echo — this is intentional as the chain fires immediately (no user message needed in chat).

---

### FIX-088 — KAN-116 Issue 2: Version chip stays at v1 after revision completes

**Date:** 2026-07-22
**Triggered by:** `/velocity-ai-fix KAN-116 issue 2 — version chip only shows v1 after ppt_revision`

#### Root Cause
In `page.tsx`, the `pipeline_complete` handler uses `isForeignCompletion` to prevent concurrent foreign runs from hijacking `contentSourceRunId`. For revision pipelines (`ppt_revision`, `prototype_revision`, etc.), `completingRunId` (the revision run's ID) !== `trackedRunIdRef.current` (the parent run's ID that was being tracked), so `isForeignCompletion = true`. This blocked `setContentSourceRunId(completingRunId)` from firing.

Since `contentSourceRunId` didn't change, `DashboardLayout`'s `useEffect([contentSourceRunId])` that calls `getRunFamily` never re-fired. The family stayed with just 1 member (v1) even after the revision (v2) completed and was stored with `parent_run_id = ppt_run_id`.

The `trackedRunIdRef` correctly held the parent run's ID — but for revision pipelines this is intentional: the user is revising a run they were already viewing, so the revision completion should advance the content source to the new revision.

#### Phase Context
- **Phase(s) involved:** Phase 25 (Workstream B1 — revision family linkage), Phase 36 (B2 — version timeline)
- **Deleted code verified (not resurrected):** No deleted code
- **Locked decisions respected:** SC-001/INV-1 — uses generic `endsWith("_revision")` check, no hardcoded pipeline name

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/app/dashboard/page.tsx` | Added `completingPipelineType` from `data.pipeline_type`; added `isRevisionCompletion = completingPipelineType?.endsWith("_revision")`; changed gate to `(!isForeignCompletion || isRevisionCompletion)` so revision completions always update `contentSourceRunId` | Revision runs are intentionally dispatched from the tracked run; their completion must advance the content source to trigger the family re-fetch |

#### Invariants Verified
- **INV-1**: `endsWith("_revision")` is a generic suffix check — no `pipeline_type ==` literal
- **INV-3**: FE-only change — no backend/engine/golden impact
- **INV-12**: No duplication — reuses existing `trackedRunIdRef` and `setContentSourceRunId` pattern
- **SC-001**: No engine edit

#### Verification
After the fix:
1. User views PPT run (v1) → `contentSourceRunId = ppt_run_id` → `getRunFamily(ppt_run_id)` → 1 member
2. User triggers revision → `ppt_revision` pipeline completes → `completingPipelineType = "ppt_revision"` → `isRevisionCompletion = true` → `setContentSourceRunId(revision_run_id)` fires
3. `DashboardLayout` effect re-fires → `getRunFamily(revision_run_id)` → backend walks up parent chain → returns 2 members (v1 + v2)
4. Version chip shows "v2 ▾" with both v1 and v2 selectable

#### Notes
- This fix applies to ALL `*_revision` pipeline types: `ppt_revision`, `od_ppt_revision`, `prototype_revision`, `user_stories_revision`, `app_builder_revision`
- The `isRevisionCompletion` flag does NOT affect the `detachRunRef` call — revision completions also correctly detach the stream

---

### FIX-087 — KAN-116: Version switch wrong content, chained runs in family, context markers in titles

**Date:** 2026-07-22
**Triggered by:** `/velocity-ai-fix KAN-116 — three bugs: version switch, chained family grouping, title markers`

#### Root Cause

**Bug 1 (version switch wrong content):** `WorkflowHistory.tsx handleSelectVersion` only called `setSelectedRun`/`setSelectedOutput` (WorkflowHistory-local state). When `onOpenRun` is available (the shared run screen path), it must route through `onOpenRun(full)` instead — which calls `page.tsx handleSelectWorkflowRun`, the sole function that clears ALL content states (`userStoryContent`, `prototypeContent`, `pptContent`, etc.) and re-populates only the matching type. Without this, switching from prototype (v3) back to user stories (v1/v2) kept showing prototype HTML.

**Bug 2 (chained runs in version family):** `run_commands.py launch_run` set `parent_run_id = _resolve_owned_parent_run_id(...)` for ALL pipeline types, including chained pipelines of a different base type. `_owned_family_members` BFS (`runs.py:960`) has no type filter — it includes ALL children. A chained `prototype` run with `parent_run_id = user_stories_run_id` appeared as v3 of the user story family.

**Bug 3 (context markers in titles):** `run_commands.py:1591` set `title = content[:60]`, where `content` for revision pipelines is the full structured message including `=== EXISTING PRODUCT BACKLOG ===` / `=== EXISTING PROTOTYPE HTML ===` markers; for chained pipelines it is `enrichedInput = brief + "\n\n=== CONTEXT FROM PREVIOUS PIPELINE ==="`. The stored title became the first 60 characters of these marker strings.

#### Phase Context
- **Phase(s) involved:** Phase 25 (Workstream A — revision family linkage), Phase 36 (B2 — history/version), Phase 29/44 (run_commands.py launch_run)
- **Deleted code verified (not resurrected):** No deleted code involved
- **Locked decisions respected:** SC-001/INV-1 — Bug 2 fix uses generic `endswith("_revision")` check, never a hardcoded pipeline name; Bug 3 helper uses generic regex marker matching

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/history/WorkflowHistory.tsx` | `handleSelectVersion`: when `onOpenRun` is available, call `onOpenRun(full)` instead of local `setSelectedRun`/`setSelectedOutput` | Routes version switch through page.tsx content-routing so all content states are cleared and re-populated by the selected version's type |
| `backend/app/api/run_commands.py` | Added `_clean_run_title(content, pipeline_type)` helper (strips `=== REVISION REQUEST ===`, `=== CONTEXT FROM PREVIOUS PIPELINE ===`, and `=== EXISTING ... ===` marker blocks); used in `launch_run` WorkflowRun creation | Stores clean user brief / instruction as title, not raw marker text |
| `backend/app/api/run_commands.py` | `launch_run`: `parent_run_id` is now set only when `pipeline_type.endswith("_revision")`; chained pipelines get `parent_run_id = None` | Chained runs are separate history entries, not grouped as versions of the source family |

#### Invariants Verified
- **INV-1**: Bug 2 uses `endswith("_revision")` — generic suffix, no `pipeline_type ==` literal
- **INV-3**: FE-only change for Bug 1; BE title change and parent_run_id fix don't touch engine events or goldens
- **INV-12**: No duplication — `_clean_run_title` is a new pure helper called from `launch_run`; no existing capability duplicated
- **SC-001**: No engine edits; purely app-layer (run_commands.py) and frontend (WorkflowHistory.tsx)

#### Verification
- Backend started cleanly after changes (no import errors)
- `_clean_run_title` helper correctly extracts revision instruction from `=== REVISION REQUEST ===` block and strips `=== CONTEXT FROM PREVIOUS PIPELINE ===` from chained content
- `handleSelectVersion` now has `[onOpenRun]` in its dependency array, matching the prop-dependent behaviour
- All three fixes are generic (no hardcoded workflow names) — apply to user_stories, prototype, ppt, app_builder and their od_ variants

#### Notes
- Existing runs in the DB that already have marker-polluted titles or wrong parent_run_id are NOT retroactively fixed (this is a forward fix for new runs only)
- Bug 2: chained runs launched BEFORE this fix will still appear in the version family; new chained runs will be separate
- The `_re_title` module-level import at the top of the helper block is intentional (module-scope lazy import to keep the helper self-contained)

---

### FIX-086 — Surface system prompt editor on Config tab of Library agent drawer

**Date:** 2026-07-22
**Triggered by:** `/velocity-ai-fix system prompt editing from dev branch — reapply to new UI2`

#### Root Cause
All call sites of `AgentPromptSection` in `AgentsPopup.tsx` passed `surfaceOnly` (or `surfaceOnly={true}`), which hides the Edit, Save override, and Revert-to-default buttons. This was the ND-7/LOCK-E design decision from Phase 37/41 that explicitly deferred prompt-override persistence in the drawer. The backend storage (`prompt_overrides.py`), REST API (`GET/PUT/DELETE /api/agents/{id}/prompt`), factory injection (`factory.py:_compose_system_prompt`), and FE API client (`api.ts`) are all fully wired — the only missing piece was removing the `surfaceOnly` gate on the Config tab.

#### Phase Context
- **Phase(s) involved:** Phase 37/41 (B3/B7) + KAN-76 (dev branch)
- **Relevant register section:** Phase 37 §5 (ND-7/LOCK-E decision)
- **Deleted code verified (not resurrected):** No deleted code — intentional gate reversal
- **Locked decisions respected:** ND-7/LOCK-E superseded for the Library drawer Config tab only; Composer surfaces keep `surfaceOnly`

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/workflow/AgentsPopup.tsx` | Added `<AgentPromptSection agent={agent} />` (without `surfaceOnly`) at the top of the Config tab section | Surfaces Edit/Save override/Revert affordances; overview tab unchanged (still surfaceOnly) |

#### Invariants Verified
- **INV-1**: Not affected — FE-only
- **INV-3**: Not affected — factory falls back gracefully; goldens unaffected
- **INV-12**: Reuses existing `AgentPromptSection` — no duplication
- **SC-001**: Not affected

#### Verification
Config tab now shows collapsible "System Prompt" section at top with Edit/Save/Revert. Save calls `PUT /api/agents/{id}/prompt`; Revert calls `DELETE`. Factory reads the override at runtime via `read_user_prompt_override`.

---

### FIX-084 — KAN-115: Clear stale questionnaireData on pipeline_cancelled/failed

**Date:** 2026-07-21
**Triggered by:** `/velocity-ai-fix KAN-115`

#### Root Cause
`frontend/src/app/dashboard/page.tsx` lines 913–921: the `pipeline_cancelled` / `pipeline_failed` case called `setReviewGateData(null)` but NOT `setQuestionnaireData(null)` or `setActivePipelineRunId(null)`. When a user cancels during the clarify gate, `questionnaire_complete` never fires, so `questionnaireData` remains populated. `DashboardLayout` subscribes to it and sets `questionnaireQuestions`, making `laneClarifyOpen = true`. Since `laneClarifyOpen ? "clarify"` is checked before `(failed || cancelled) ? "terminal"` in the `runLaneState` ternary, the lane stays in `"clarify"` mode, the `AwaitingCard` persists, and the correct terminal affordance is never shown.

**Critical implementation detail found during verification:** `pipeline_cancelled` and `pipeline_failed` are in the `pipelineTypes` array (line ~463), so they are handled in the `pipelineTypes` block which ends with `return;` before the `switch` statement. The initial fix was placed in the `switch` case at line ~913 — which is **dead code** for these event types. The working fix is in the `pipelineTypes` block, just before `return;`, using an `if (msg.type === "pipeline_cancelled" || msg.type === "pipeline_failed")` guard. Additionally, `setReviewGateData(null)` from the KAN-100 fix was also in the dead switch case and has been moved here.

#### Phase Context
- **Phase(s) involved:** Phase 22/42 — frontend pipeline state dispatcher in `page.tsx`
- **Relevant register section:** Phase 42 §2 (RUNUI-08 — inline clarify/gate affordances)
- **Deleted code verified (not resurrected):** No deleted code involved — surgical one-case addition
- **Locked decisions respected:** LIVE-STATE-CONTRACT `runLaneState` priority order (clarify > terminal) is preserved; the fix clears the stale upstream state so the priority resolves correctly

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/app/dashboard/page.tsx` | Added `setQuestionnaireData(null)` and `setActivePipelineRunId(null)` to the `pipeline_cancelled` / `pipeline_failed` case | Mirrors the identical clear already present in the `pipeline_start` handler (lines ~528–533); ensures `laneClarifyOpen` goes false on cancel/fail so `runLaneState` resolves to `"terminal"` |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): Not affected — FE-only, no engine change
- **INV-3** (golden parity): Not affected — FE-only, no backend/golden impact
- **INV-12** (no duplication): Not applicable — reusing existing state setters
- **SC-001** (zero engine edits): Not affected — FE-only

#### Verification
After the fix: when `pipeline_cancelled` fires, `setQuestionnaireData(null)` clears `questionnaireData` → `DashboardLayout` effect fires `setQuestionnaireQuestions([])` → `laneClarifyOpen = false` → `runLaneState` evaluates past `"clarify"` to `"terminal"` → `AwaitingCard` disappears. The `questionnaire_complete` path (normal clarify-then-proceed) is unaffected. The `pipeline_start` clear (stale-state-from-previous-run) is unaffected.

#### Notes
- `setActivePipelineRunId(null)` is also cleared as a second-layer defense: even if `questionnaireQuestions` somehow stayed non-empty, `laneClarifyOpen` also gates on `(!!activePipelineRunId)`, so clearing it prevents any residual false positive.
- The chained-run clarify box (screenshot 2 in KAN-115) is also addressed by this fix — any stale `questionnaireData` from a prior run's clarify round is cleared when the terminal event fires.
- FE-only change; no backend restart needed.

---

### FIX-083 — KAN-114: Replace styled clarify ResultCard with plain text bubble

**Date:** 2026-07-21
**Triggered by:** `/velocity-ai-fix KAN-114`

#### Root Cause

When `questionnaire_ready` fired, two independent code paths both rendered clarification-related boxes in the left chat lane simultaneously:

1. **`backend/app/agents/chat_narrator.py` `_classify()`** — emitted a `chat_reply` with `card_kind="clarify"` and text `"Paused — N questions for you"`. The FE rendered this via `MessageBubble → ResultCard` as a styled amber card with the "Clarification needed" header (from `CARD_SPECS["clarify"]` in `ResultCard.tsx`).

2. **`frontend/src/components/chat/RunChatLane.tsx` `renderTranscriptFooter()`** — independently rendered an `AwaitingCard` whenever `runState === "clarify"`, showing "Paused — N questions for you" with an "Answer in Steps" CTA.

The user wants to KEEP the `AwaitingCard` (box 2) and replace box 1 with a plain conversational text bubble reading `"Before I build, I need to lock a few things down."`.

#### Phase Context

- **Phase(s) involved:** Phase 31 (CHATUI-01 — ResultCard narrator architecture), Phase 43 (A6 — `chat_narrator.py` narrator projection)
- **Relevant register section:** Phase 31 §3 (ResultCard), Phase 43 §3 (chat_narrator.py)
- **Deleted code verified (not resurrected):** No deleted code involved
- **Locked decisions respected:** SC-001 — all changes keyed on generic `cardKind: "clarify"`, no workflow-name branch

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `backend/app/agents/chat_narrator.py` | Changed `questionnaire_ready` narrator text from `f"Paused — {n} questions for you"` to the fixed string `"Before I build, I need to lock a few things down."` | Box 1 needs to be a conversational message, not a status repeat of box 2 |
| `frontend/src/components/chat/ResultCard.tsx` | Added a `clarify`-specific render branch that returns a plain `<p>` text bubble + small "Answer in Steps" link; no styled card chrome, no amber icon/header | Box 1 should look like a conversational assistant message, not a status card |
| `backend/tests/unit/test_chat_narrator.py` | Updated `test_clarify_card_from_questionnaire_ready` assertion from `assert "3" in card["text"]` to `assert card["text"] == "Before I build, I need to lock a few things down."` | Test was asserting the old dynamic count-bearing text which no longer applies |

#### Invariants Verified

- **INV-1** (no pipeline_type branches): Not affected — all changes keyed on generic `cardKind` / event type, no workflow name
- **INV-3** (golden parity): Not affected — `chat_narrator` is dormant on scripted golden runs; the 5 characterization goldens are byte-identical
- **INV-12** (no duplication): Not affected — single narrator path used; AwaitingCard unchanged
- **SC-001** (zero engine edits for new workflows): Not affected — no engine edit; FE/app-layer only

#### Verification

- `ResultCard.tsx` `clarify` branch renders `data-testid="chat-result-card"` and `data-card-kind="clarify"` — existing test assertions still pass
- Existing `test_clarify_card_from_questionnaire_ready` updated to assert the new fixed text
- `renderTranscriptFooter()` for `runState === "clarify"` (the AwaitingCard) untouched — confirmed in `RunChatLane.tsx:1419–1431`
- Backend restart required (chat_narrator.py changed)

#### Notes

- The `questionnaire_complete` text (`"N clarifications answered"`) is untouched — only the `questionnaire_ready` text changed
- Same fix naturally applies to revision and chaining flows since they share the same `questionnaire_ready` event path through `chat_narrator.py`
- The `CARD_SPECS["clarify"]` entry in `ResultCard.tsx` is kept (it defines `linkLabel: "Answer in Steps"` and `defaultTab: "steps"`) because the new clarify branch still reads `spec?.linkLabel` and `tab` from it

---

### FIX-066 — Restyle AgentPromptSection to dark card with readable white text

**Date:** 2026-07-21
**Triggered by:** `/velocity-ai-fix make the above changes` (dark card, better text font for System Prompt)

#### Root Cause

`frontend/src/components/workflow/AgentsPopup.tsx` — the `AgentPromptSection` component returned a light white card with four specific styling problems:

1. Outer wrapper used `border border-gray-200` + white background → light card appearance
2. Header texts used `text-gray-700` / `text-gray-400` → low contrast on light background
3. Expanded body `<div>` had `bg-white` → no distinction between card and drawer background
4. Prompt body `<pre>` used `font-mono text-[10.5px] text-gray-600` → tiny monospace text that looked like raw code instead of readable instructions

The target design (Hexaware mock) shows a dark near-black rounded card with white readable prose text.

#### Phase Context
- **Phase(s) involved:** Phase 37 (B3 — Configure + Composer/Wizard), Phase 41 (B7 — Configure Composer Rebuild)
- **Relevant register section:** Phase 37/41 §3 (`AgentPromptSection` in `AgentsPopup.tsx`)
- **Deleted code verified (not resurrected):** N/A — styling-only change
- **Locked decisions respected:** INV-12 — `AgentPromptSection` is the single source; all 4 callsites (drawer Config, drawer Overview, AgentRow, CanvasConfigRail) inherit the change correctly. Phase-32 token layer (`bg-surface-near-black`, `text-ink-*`) used instead of raw hex.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/workflow/AgentsPopup.tsx` | Outer wrapper: `border border-gray-200` → `bg-surface-near-black` (no border) | Dark card background |
| `frontend/src/components/workflow/AgentsPopup.tsx` | Header button: `hover:bg-gray-50` → `hover:bg-white/5` | Dark-appropriate hover |
| `frontend/src/components/workflow/AgentsPopup.tsx` | Icon + labels: `text-gray-400/700` → `text-ink-400` / `text-white` | Readable on dark background |
| `frontend/src/components/workflow/AgentsPopup.tsx` | Expanded border: `border-gray-200` → `border-white/10` | Subtle dark separator |
| `frontend/src/components/workflow/AgentsPopup.tsx` | Expanded body: `bg-white` → `bg-surface-near-black` | Consistent dark card |
| `frontend/src/components/workflow/AgentsPopup.tsx` | Source badge (default): `bg-gray-100 text-gray-500 border-gray-200` → `bg-white/10 text-ink-300 border-white/20` | Dark-card-appropriate pill |
| `frontend/src/components/workflow/AgentsPopup.tsx` | Prompt body: `<pre> font-mono text-[10.5px] text-gray-600` → `<p> font-sans text-[13px] text-white leading-relaxed` | Larger, white, readable prose instead of monospace code |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — React styling only
- **INV-3** (golden parity): not affected — no engine or event stream changes
- **INV-12** (no duplication): `AgentPromptSection` remains the single source; change propagates to all 4 callsites correctly
- **SC-001** (zero engine edits): not affected

#### Verification

All 4 callsites receive the dark card automatically:
- Drawer Overview tab: `AgentsPopup.tsx` ~line 606
- Drawer Config tab: `AgentsPopup.tsx` ~line 619
- Composer AgentRow: `AgentRow.tsx` line 224
- Canvas CanvasConfigRail: `CanvasConfigRail.tsx` line 366

Tests query by `getByText(/system prompt/i)` or `getByRole("button", { name: /system prompt/i })` — not by className — so no test regressions.

The edit textarea (when `surfaceOnly=false` and user clicks Edit) was intentionally left with its existing light styling — the target screenshot only shows the read-only state.

#### Notes

- The `font-mono` class on the `<pre>` tag was replaced with a `<p>` tag with `font-sans` — this is the key change that makes the text look like readable instructions rather than raw code.
- `whitespace-pre-wrap` is preserved on the `<p>` to maintain line breaks from the AGENT.md content.
- No backend restart needed — FE-only change.

---

### FIX-064 — Hide Web/Deck toggle in template picker (show only relevant gallery per launch context)

**Date:** 2026-07-21
**Triggered by:** `/velocity-ai-fix fix above changes` (hide Web/Deck filter; show web templates for prototype, deck templates for PPT)

#### Root Cause

`frontend/src/components/workflow/WizardStepper.tsx` lines 119–138 — the Web/Deck toggle `<div role="group">` block was rendered unconditionally whenever `activeStep === 0`. There was no prop to suppress it. The gallery content already correctly displayed based on the `mode` prop (`web` → `TemplateGallery`, `deck` → `PPTTemplateGallery`), but the toggle gave users the ability to manually switch between families mid-wizard, which was not the intended UX.

When launched from `?mode=prototype` the toggle showed "Web" and "Deck" buttons above web templates. When launched from `?mode=ppt` the same toggle appeared above deck templates. The user wants the gallery locked to the launch mode with no toggle visible.

#### Phase Context
- **Phase(s) involved:** Phase 37 (B3 — Configure + Composer/Wizard), Phase 41 (B7 — Configure Composer Rebuild)
- **Relevant register section:** Phase 37 §3 (`WizardStepper`, `LaunchWizard`)
- **Deleted code verified (not resurrected):** N/A — this is an additive prop, no prior deleted code involved
- **Locked decisions respected:** SC-001/INV-1 — `mode` stays a generic data value, no workflow-name branch introduced

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/workflow/WizardStepper.tsx` | Added `showToggle?: boolean` to `WizardStepperProps` (default `false`); added `showToggle = false` to destructure; wrapped the toggle `<div>` block in `{showToggle && (...)}` | Hides the toggle by default; all existing callers (LaunchWizard) get the correct behavior without any prop change |
| `frontend/src/components/workflow/WizardStepper.test.tsx` | Updated `Harness` component to accept `showToggle` prop; replaced the old toggle-swap test with: (1) a test confirming toggle is hidden by default, (2) a test confirming toggle still works when `showToggle={true}` | Test must reflect the new default behavior |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — `mode` stays a generic data value; no workflow-name branch
- **INV-3** (golden parity): not affected — FE-only change, no backend, no engine, no golden snapshots
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected

#### Verification

Mental trace with fix applied:
1. User opens `/workflow/create?mode=prototype`
2. `create/page.tsx` → `mode = "prototype"` → `LaunchWizard(initialMode="prototype")`
3. `LaunchWizard` → `STEPPER_MODE["prototype"] = "web"` → `<WizardStepper mode="web" ...>` (no `showToggle` prop → defaults to `false`)
4. `WizardStepper` → `showToggle = false` → `{false && <div>...</div>}` → toggle NOT rendered ✅
5. `mode === "web"` → `<TemplateGallery>` renders → only web templates visible ✅

PPT path: same but `mode="deck"` → `<PPTTemplateGallery>` renders → only deck templates visible ✅

`LaunchWizard.test.tsx` not changed: it uses a mock stub of `WizardStepper` that directly exposes toggle buttons regardless of `showToggle`; those tests cover `handleModeChange` logic in `LaunchWizard` which remains intact.

#### Notes

- The `onModeChange` prop and `handleModeChange` logic in `LaunchWizard` are intentionally preserved — they remain available if cross-family switching is ever needed in future (just pass `showToggle={true}` to re-enable).
- The `Globe` and `Presentation` icon imports in `WizardStepper.tsx` are preserved (they're needed if `showToggle={true}` is used).
- No backend restart needed — FE-only change.

---

### FIX-063 — KAN-113: Fix version dropdown wrong relative age (timezone-naive datetime)

**Date:** 2026-07-21
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-113`

#### Root Cause

`backend/app/api/runs.py` — `WorkflowRunResponse` and `FamilyMemberResponse` both declare `created_at: datetime` and `completed_at: Optional[datetime]` without any timezone-aware serialization configuration.

SQLAlchemy's `DateTime` column (`workflow.py` lines 38-41) stores datetimes without timezone info (uses `DateTime`, not `DateTime(timezone=True)`). When read back from SQLite, the datetime object has `tzinfo=None` — a naive datetime — even though it was originally written as `datetime.now(timezone.utc)`.

Pydantic v2 serializes a naive datetime as `"2026-07-21T10:30:00"` (no `+00:00` or `Z` suffix). JavaScript's `Date.parse()` treats an ISO 8601 string without a timezone suffix as **local time** per the ECMAScript spec. For a user in UTC+5:30 (India), this adds 5.5 hours to the epoch value, making a freshly-created run appear as "5h ago" rather than "just now".

Trace:
```
WorkflowRun.created_at = datetime(2026,7,21,10,30,0)  ← naive (no tzinfo)
  → FamilyMemberResponse.created_at = same naive datetime
  → Pydantic v2 JSON: "2026-07-21T10:30:00"  ← NO +00:00
  → JS Date.parse("2026-07-21T10:30:00") treats as LOCAL time (UTC+5:30 adds 5.5h)
  → Date.now() - then = tiny positive or negative → shows "5h ago"
```

#### Phase Context
- **Phase(s) involved:** Phase 36 §3 (`FamilyMemberResponse` / Workstream A read surface) + Phase 5 §3 (`WorkflowRunResponse` / typed artifacts persistence)
- **Relevant register section:** `_register-parts/05-typed-artifacts-persistence-ownership-1b.md` §3 and Phase 36 §3
- **Deleted code verified (not resurrected):** N/A — new serializer code only
- **Locked decisions respected:** INV-12 — the fix reuses the `_coerce_to_aware_utc` pattern already established in `backend/app/core/dependencies.py` lines 20-31, applied as a `@field_serializer` at the API boundary

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `backend/app/api/runs.py` | Added `timezone` to `from datetime import datetime, timezone` | Required by the serializer to call `.replace(tzinfo=timezone.utc)` |
| `backend/app/api/runs.py` | Added `field_serializer` to `from pydantic import BaseModel, Field, field_serializer` | Required for the `@field_serializer` decorator |
| `backend/app/api/runs.py` | Added `@field_serializer("created_at", "completed_at")` method `_serialize_dt` to `WorkflowRunResponse` | Promotes naive UTC datetimes to timezone-aware before JSON serialization |
| `backend/app/api/runs.py` | Added same `@field_serializer("created_at", "completed_at")` to `FamilyMemberResponse` | Same fix — this is the model consumed by the version dropdown's `formatRelativeAge` |

The serializer logic:
```python
@field_serializer("created_at", "completed_at")
def _serialize_dt(self, v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.isoformat()
```
Result: `"2026-07-21T10:30:00+00:00"` instead of `"2026-07-21T10:30:00"`.

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — Python API model only
- **INV-3** (golden parity): not affected — no engine or event stream changes; golden snapshots do not cover API JSON serialization
- **INV-12** (no duplication): the `_coerce_to_aware_utc` helper in `dependencies.py` is the prior art for this pattern; `@field_serializer` is the Pydantic v2 canonical way to apply it at the serialization boundary
- **SC-001** (zero engine edits): not affected — API model only

#### Verification

Mental trace with fix applied:
1. SQLite returns `datetime(2026,7,21,10,30,0)` (naive)
2. `FamilyMemberResponse._serialize_dt()` called with that value
3. `v.tzinfo is None` → `v = v.replace(tzinfo=timezone.utc)` → `datetime(2026,7,21,10,30,0, tzinfo=UTC)`
4. `.isoformat()` → `"2026-07-21T10:30:00+00:00"` ✅
5. Frontend `Date.parse("2026-07-21T10:30:00+00:00")` → correct UTC epoch
6. `Date.now() - then` → correct small delta → "just now" or "4m ago" ✅

UTC-aware datetimes on Postgres (already have `tzinfo`): `v.tzinfo is None` is False → `.isoformat()` called directly → no change in behavior.

#### Notes

- The same naive-datetime issue potentially exists in other API files (analytics.py, user_workflows.py, etc.) for any `created_at` / `updated_at` fields, but those are lower-priority since they don't feed the `formatRelativeAge` function in the UI.
- The underlying SQLAlchemy column (`DateTime` without `timezone=True`) is intentionally left unchanged — switching to `DateTime(timezone=True)` would require a migration and has risks on SQLite compatibility. The serializer boundary fix is the correct minimal approach.
- Backend server restart required after this change.

---

### FIX-062 — Move "v1 draft" chip to left of "Running · Streaming" badge in RunHeader

**Date:** 2026-07-21
**Triggered by:** `/velocity-ai-fix please apply option A` (from `/velocity-ai-analyze` on the run header layout)

#### Root Cause

`frontend/src/components/preview/RunHeader.tsx` — the version chip `<span>` ("v1 draft") was placed **after** the `<div className="flex-1" />` spacer in the JSX flex row. Flex-1 pushes all subsequent siblings to the right edge, so the chip appeared in the top-right corner. The status badge ("Running · Streaming") was placed before the spacer on the left side.

Sequence:
```
[StatusBadge LEFT] → [flex-1 spacer] → [v1 draft chip RIGHT] → [Share RIGHT]
```

The user wanted the chip on the **left of** the status badge, which requires it to be the first child in the flex container.

#### Phase Context
- **Phase(s) involved:** Phase 39 (RUNUI-06/07) — `RunHeader` component built to match `Hexaware Run - Live.dc.html:159-166`
- **Deleted code verified (not resurrected):** N/A — purely JSX ordering change
- **Locked decisions respected:** Phase 39 D39-1 (mock-fidelity) — user explicitly overrides the original right-side placement

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/preview/RunHeader.tsx` | Moved the `{!isSettled && versionLabel && <span>...}` chip block from after the `flex-1` spacer to **before** the `{isSettled ? <VersionMenu/> : <StatusBadge/>}` block | Makes the chip the leftmost element in the flex row, rendering it to the left of the status badge |

New render order:
```
[v1 draft chip] → [Running · Streaming badge] → [flex-1 spacer] → [Share button]
```

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — React component only
- **INV-3** (golden parity): not affected — no engine or event changes
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected

#### Verification
- Chip and badge are in the correct DOM order after the edit
- `RunHeader.test.tsx` asserts presence of "v1 draft" text only (not position) — no test regression
- `tsc` — no type changes; same props, same conditionals
- Settled state: chip conditional `!isSettled` is false → chip not rendered → `VersionMenu` renders as before — zero regression on the settled state
- Failed state: "v1 · partial" chip appears leftmost, then the red "Run failed" badge — also correct behavior

#### Notes
- The chip's styling, conditional logic, and text content are completely unchanged
- Only JSX position was altered

---

### FIX-050 — KAN-109: Add AI Coach Hub SKILL.md to expose template in gallery

**Date:** 2026-07-15
**Triggered by:** `/velocity-ai-fix KAN-109 — add SKILL.md for ai-coach-hub template`

#### Root Cause

`skills/opendesign/design-templates/ai-coach-hub/SKILL.md` was absent. The loader
`backend/app/services/od_loader.py::_load_one_template()` checks `(folder / "SKILL.md").is_file()`
first and returns `None` if the file is missing — the folder is then silently excluded from
`list_prototype_templates()` which only returns entries with `od.mode == "prototype"`. The
`example.html` file was present and correct (six navigable screens, all `data-od-id` attributes,
hash-based router, inline JS controller).

Trace:
```
GET /api/prototype-templates/list
  → list_prototype_templates()
  → _all_templates()  [@lru_cache — cleared on restart]
  → _load_one_template(ai-coach-hub/)
  → skill_path = folder / "SKILL.md"
  → if not skill_path.is_file(): return None   ← ai-coach-hub/ skipped
  → template never added to result list
  → gallery shows no AI Coach Hub card
```

#### Phase Context

- **Phase(s) involved:** N/A — OpenDesign templates are pure content under `skills/`, not tracked by any engine phase.
- **Relevant register section:** Not applicable (content file, no phase section).
- **Deleted code verified (not resurrected):** No code deleted or modified.
- **Locked decisions respected:** N/A — pure content addition.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `skills/opendesign/design-templates/ai-coach-hub/SKILL.md` | Created new file with `od.mode: prototype` frontmatter, name/description/triggers/od block, and full agent build workflow (pre-flight, domain replacement, JS data adaptation, six-screen self-check, nav integrity check, output contract) | `od_loader._load_one_template()` requires SKILL.md; `list_prototype_templates()` requires `od.mode == "prototype"` to include the template in the gallery |

#### Invariants Verified

- **INV-1** (no pipeline_type branches): not affected — no engine code changed.
- **INV-3** (golden parity): not affected — no agent or engine code changed.
- **INV-12** (no duplication): not applicable — pure content addition.
- **SC-001** (zero engine edits): not affected — zero engine edits.

#### Verification

1. Confirmed `od.mode: prototype` present in the new SKILL.md via grep.
2. Backend restarted — `@lru_cache` on `_all_templates()` cleared.
3. Template will appear at `http://localhost:3000/workflow/prototype/templates` with name "AI Coach Hub", tags DESKTOP and SAAS-PRODUCT, and the live preview.

#### Notes

- The template was previously built and verified working (screenshot confirmed by user), then reverted due to missing branch discipline. KAN-109 was created to track the redo.
- The SKILL.md follows the exact `process-canvas/SKILL.md` pattern: YAML frontmatter with `od` block + markdown body with pre-flight / workflow / hard-rules / output-contract sections.
- All six screen `data-page` ids and `data-od-id` attributes documented in the SKILL.md screen inventory table so agents know what to change vs preserve when re-skinning.

---

### FIX-049 — KAN-108: Add Revision Validation Agent to prototype_revision pipeline

**Date:** 2026-07-13
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-108`

#### Root Cause

`backend/agents/workflows/prototype_revision/workflow.yaml` declared only one step (`prototype-revision-agent`). The silent `revision_validation` post-step fires after this agent and runs a regression-only fix loop (max 2 attempts). It only catches issues that are NEW compared to the pre-edit baseline. A no-op edit (edit_file anchor miss → file unchanged), blank pages, missing requested components, and broken navigation all produce a baseline delta of zero → fix loop exits → broken/unchanged prototype delivered with `pipeline_complete`. Additionally `clarify.mode: auto` fired a questionnaire on every revision run — prototype and od_ppt were corrected to `skip` in FIX-010/FIX-015 but `prototype_revision` was not updated.

The `prototype-validate` agent (final step of the base `prototype` pipeline) already implements the needed comprehensive checks (fills empty pages, verifies navigation, enforces DS tokens, etc.) but declares `consumes: [prototype-build]` and `injects: [template, design_system]` — contracts that are incompatible with the `prototype_revision` pipeline where there is no `prototype-build` and design context is seeded via `previous_run` from the sandbox. Reusing it directly would cause the DAG satisfiability check to fail hard.

#### Phase Context

- **Phase(s) involved:** Phase 7 (07-10/CR-06 — `revision_validation` post-step + agent registry). FIX-010/FIX-015 (clarify.mode: skip precedent).
- **Relevant register section:** `_register-parts/07-prototype-as-manifest-parity-proof-sc-001-2.md` §3 (capabilities added)
- **Deleted code verified (not resurrected):** No deleted code resurrected. The new agent is a forward addition.
- **Locked decisions respected:** D-01 (SC-001: no workflow-name literals; manifest + AGENT.md only). D-14 (planner: run stays on `prototype_revision` — it rides `run_pipeline`, not the `run_revision` dispatch path that requires `planner: skip`). FIX-010/015 precedent: `clarify.mode: skip` is the correct setting for any pipeline whose launch surface already provides the complete brief.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `backend/agents/prompts/prototype-revision-validate/AGENT.md` | New file — dedicated Revision Validation Agent with `pipeline_type: prototype_revision`, `consumes: [prototype-revision-agent]`, `injects: []`, `tools: [workspace]`, `order: 2`. Same prompt body as `prototype-validate` adapted to read `design.md` via workspace tools (no opendesign injection needed — design.md is seeded from the parent run sandbox). | Cannot reuse `prototype-validate` — its `consumes: [prototype-build]` makes the DAG unsatisfiable in `prototype_revision`; a dedicated agent with correct contracts is required |
| `backend/agents/workflows/prototype_revision/workflow.yaml` | Added second step `prototype-revision-validate` (strategy: single_shot, gates: []). Changed `clarify.mode` from `auto` to `skip`. | Adds the visible validation step after the revision; eliminates the questionnaire friction |
| `backend/agents/registry.py` | Updated `prototype_revision` list from `["prototype-revision-agent"]` to `["prototype-revision-agent", "prototype-revision-validate"]`. | Single source of truth for pipeline membership |
| `backend/tests/agents/_scripted_model.py` | Added scripted branch for `prototype-revision-validate` returning a clean text-only turn `["Validated — 1 page checked, no issues found."]` | Harness needs a script for every declared agent in the pipeline |
| `backend/tests/agents/characterization/golden/prototype_revision.events.json` | Regenerated (SNAPSHOT_UPDATE=1) — now includes `prototype-revision-validate` events: `pipeline_start` with 2 agents, `agent_start/input/chunk/complete` for both, `pipeline_complete` with `agents_total: 2`. | INV-3: golden must reflect the new 2-agent event stream |
| `backend/tests/agents/characterization/golden/prototype_revision.html` | Regenerated — deliverable is still `prototype.html` from the revision agent (validation agent text-only in scripted harness). | Byte snapshot stays valid |
| `backend/tests/agents/test_phase5_revision_validation.py` | Updated 4 `turns_for` callbacks in `TestFixPolicyEndToEnd` and `TestEventVocabularyUnchanged` to return `_clean_revision_turns()` for `prototype-revision-validate`. Updated `test_internal_fix_loop_leaks_no_phantom_second_agent` assertions: `agent_start == 2`, `agent_complete == 2`, `starts == ["prototype-revision-agent", "prototype-revision-validate"]`, `edit_file count == 2`. | Tests were written for a 1-agent pipeline; update to reflect the correct 2-agent contract |

#### Invariants Verified

- **INV-1** (no pipeline_type branches): not affected — no `if pipeline_type ==` literals added anywhere. The new agent is dispatched generically by the engine via manifest steps.
- **INV-3** (golden parity): `prototype_revision` golden intentionally regenerated (new second agent step changes the event stream). Other 4 goldens (`prototype`, `od_prototype`, `od_ppt`, `app_builder`) pass unchanged — verified 8/8.
- **INV-12** (no duplication): the new `prototype-revision-validate` agent has different DAG contracts from `prototype-validate` (`consumes`, `injects`, `pipeline_type`, `tools` all differ) — not a duplicate; reuse of `prototype-validate` was explicitly rejected because its contracts are incompatible with this pipeline.
- **SC-001** (zero engine edits for new workflows): no engine edits. Change is manifest + AGENT.md + registry + test update only.

#### Verification

- `pytest tests/agents/test_characterization_prototype_revision.py` — **2/2 passed**
- `pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_app_builder.py` — **8/8 passed** (other goldens byte-identical)
- `pytest tests/agents/test_phase5_revision_validation.py tests/agents/test_manifest_parity.py::test_planner_run_everywhere tests/agents/test_manifest_parity.py::test_run_revision_manifests_declare_planner_skip tests/agents/test_manifest_parity.py::test_run_revision_revision_agents_declare_no_template_injects` — **26/26 passed**
- `pytest tests/agents/test_registry_capabilities.py` — all passed (no capability count change — new agent uses existing registered capabilities only)

#### Notes

- The `clarify.mode: skip` change makes `prototype_revision` consistent with `prototype` and `od_ppt` (FIX-010/FIX-015). The `clarify.defaults` list is unchanged — it's irrelevant when mode is `skip` but the existing list already matches the `_CUSTOM_DEFAULTS` fallback in `test_clarify_defaults_match_engine`.
- The `test_clarify_defaults_match_engine` failures for `prototype`, `ppt`, `app_builder`, etc. are **pre-existing** and unrelated to this fix (they predate this session).
- On live Bedrock, `prototype-revision-validate` will receive `design.md` from the parent run's sandbox (seeded by `previous_run` provider) and read `prototype.html` via `workspace` tools — no opendesign injection needed, which is correct since the design context is already materialized in the sandbox.

---

**Date:** 2026-06-16
**Triggered by:** `#velocity-ai-fix PPT preview not showing correctly, multiple issues`

#### Root Cause

**Issue 1 (Screenshot 1 — checklist text rendering as deck):**
`od-ppt-validator/AGENT.md` had the line "At most two short sentences of commentary may precede the artifact." The live Haiku model treats this as permission to print its full VALIDATION CHECKLIST (all the ✅/❌ bullets) as the "commentary" before `<artifact>`. When the checklist appears without any `<artifact>` wrapper at all, `unwrap_artifact()` in `ppt.py` finds no `<artifact>` tag, returns the raw checklist text unchanged, and that becomes the deliverable rendered in the preview iframe.

**Issue 2 (Screenshot 2 — "Invalid presentation output"):**
`od-ppt-composer/AGENT.md` instructed the model to "Use your filesystem tools (read_file, ls, glob) to read them." On Windows, the deepagents filesystem backend calls `pathlib.rglob()` with a compound `**` pattern. Python 3.12 raises `ValueError: Invalid pattern: '**' can only be an entire path component`. The workspace tool calls silently fail, the composer receives no template content, and produces only ~634 chars of minimal output instead of a full HTML deck. The validator then has nothing valid to re-emit, resulting in "Invalid presentation output".

Trace for Issue 1:
```
od-ppt-validator streams → checklist text before <artifact> tag (or no tag)
→ PptResolver.resolve(ctx): last_streamed = full validator output
→ unwrap_artifact(last_streamed): no <artifact> found → returns raw text
→ final_output = checklist text → iframe renders it → "random text" shown
```

Trace for Issue 2:
```
od-ppt-composer calls read_file/glob via workspace tool
→ deepagents filesystem.glob() → pathlib.rglob() → ValueError on Windows
→ composer gets no template → produces 634-char stub with no <!DOCTYPE html>
→ PPTPreview.tsx isHtml check fails → "Invalid presentation output"
```

#### Phase Context
- **Phase(s) involved:** Phase 15 — Live-Pass Prompt Contract Closure (LV-02 recurring)
- **Relevant register section:** `_register-parts/15-live-pass-prompt-contract-closure.md` §1, §5
- **Deleted code verified (not resurrected):** Phase 15 §5 locked decision respected — no code change to `ppt.py` resolver. Resolver-fallback alternative remains rejected as INV-3-sensitive.
- **Locked decisions respected:** "Fix must be prompt-body only" — both changes are AGENT.md body edits below the frontmatter `---`.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/prompts/od-ppt-validator/AGENT.md` | Removed "two short sentences" preamble allowance; added "response MUST begin with `<artifact`"; added "SILENTLY" to checklist instruction; added "Why this matters" explanation; added "checklist is a SILENT internal tool" rule | Eliminates the loophole that let the model treat checklist output as valid commentary before the artifact |
| `backend/agents/prompts/od-ppt-composer/AGENT.md` | Replaced "WORKSPACE — use filesystem tools" section with "TEMPLATE FILES — already in your context message" section explicitly telling the model NOT to call filesystem tools | Prevents Windows pathlib.rglob ValueError by directing the model to use the pre-injected context blocks instead of tool calls |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — prompt-body changes only
- **INV-3** (golden parity): not affected — scripted model ignores prompt bodies; characterization goldens stay byte-identical
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected — zero engine edit

#### Verification
AGENT.md files are read from disk at agent dispatch time — no backend restart needed. Both grep verifications confirmed:
- Validator: `"Your response MUST begin with \`<artifact\`"` present; `"SILENTLY"` present; `"two short sentences"` absent
- Composer: `"Do NOT call filesystem tools"` present; `"TEMPLATE FILES — already in your context message"` present

#### Notes
- Issue 2 (Windows glob) is a deepagents library limitation — the architectural fix is to pre-inject template files into the context message (which the system already does via `od_context.template_injection_parts`). The composer prompt now correctly directs the model to use those pre-injected blocks rather than calling filesystem tools.
- If Issue 1 recurs after this fix, the next escalation would be a code-level guard in `PPTPreview.tsx` to detect non-HTML content and show a clear error — but this is only appropriate if the prompt fix proves insufficient across multiple runs.
- The `template_files` dict in `od_context` still seeds files into the run sandbox for production (Linux) where the filesystem tool works. The prompt change makes the tool calls optional rather than required.

### FIX-002 — Vellum Template Not Applied (example.html Never Injected into Composer Context)

**Date:** 2026-06-16
**Triggered by:** `#velocity-ai-fix slides different from the vellum template`

#### Root Cause
The opendesign context provider (Phase 7 / PARITY-03) gates `example.html` injection on `is_builder = bool(spec_tools & {"prototype_emit_only", "prototype"})`. The od-ppt-composer has `tools: [workspace]` — `"workspace"` is not in that set, so `is_builder = False` and `example.html` was never included in the composer's context message.

The vellum SKILL.md workflow says:
> 1. **Clone `example.html`** into the user's workspace as the working file.
> 2. **Replace placeholder content** with the user's real headlines…

Without `example.html` in its context, the composer has no visual reference for the template's dark navy canvas, warm-yellow italic Cormorant serifs, dusty teal accent, corner brackets, paper grain, etc. It invents a generic deck instead of following the vellum identity.

Additionally, vellum has no `assets/template.html` seed file, so `template_files = {}` — the sandbox seeding path also yields nothing. The only template content the composer received was the SKILL.md text — which instructs it to clone a file it doesn't have.

Trace:
```
od_ppt run with template_id="html-ppt-zhangzara-vellum"
→ load_ppt_od_context() → template_files = {} (no assets/template.html)
→ opendesign provider.load() called
→ is_builder = False (workspace ∉ {prototype_emit_only, prototype})
→ example.html block NOT emitted
→ composer context: SKILL.md only, no example.html
→ composer ignores vellum identity → deck looks nothing like the template
```

#### Phase Context
- **Phase(s) involved:** Phase 7 — Prototype as Manifest, Parity Proof (PARITY-03)
- **Relevant register section:** `_register-parts/07-prototype-as-manifest-parity-proof-sc-001-2.md` §3 (opendesign provider, block #3 example gate, CR-02 07-06)
- **Deleted code verified (not resurrected):** The CR-02 gate was added to protect planning agents (tools=[]). Extending to `workspace` is not resurrecting deleted code — it's correctly extending the gate to cover the PPT builder case which was never considered.
- **Locked decisions respected:** Phase 7 §5 CR-02: "planning agents (tools=[]) must NOT see example.html" — honoured: the fix only extends to `"workspace"`, not to `tools=[]`.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/capabilities/context_providers/opendesign.py` | Changed `if is_builder` to `if (is_builder or "workspace" in spec_tools)` in block (3) example.html gate | PPT composer (workspace tool) now receives example.html in context; added explanatory comment explaining why workspace is included |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — gated on `spec_tools` (tool set), never on pipeline_type name
- **INV-3** (golden parity): not affected — od_ppt is not in the 5 characterization goldens (prototype/od_prototype/prototype_revision/od_ppt/app_builder — wait, od_ppt IS in the goldens but example.html is added to `_VOLATILE_STRIP_KEYS` content or... actually checked: example.html is in `blocks` dict which goes to context_message, not the golden deliverable output. The golden asserts the DELIVERABLE bytes, not the context message content.)
- **INV-12** (no duplication): reusing the existing `runner.template_example()` call pattern
- **SC-001** (zero engine edits): not affected — capability provider change only

#### Verification
Backend restarted clean. Next vellum PPT run will include `=== TEMPLATE EXAMPLE (example.html): html-ppt-zhangzara-vellum ===` block in the composer's context message. The composer can then follow the SKILL.md workflow step "Clone example.html" using the provided content.

#### Notes
- The `example.html` for vellum is large (~600+ lines). It is truncated to 8000 chars by the existing provider logic (`truncated = example_html[:8000]`). This should be sufficient to convey the visual identity (fonts, colors, slide structure, CSS) but may not include all slides. This is consistent with how prototype templates work.
- Vellum also has no `assets/template.html` seed, so `template_files` remains `{}` — the sandbox seeding path yields nothing for vellum. This is fine since the composer is now told NOT to use filesystem tools (FIX-001) and will use the injected example.html context instead.
- Other PPT templates with `assets/template.html` (like `html-ppt`) will continue to work via the existing `=== TEMPLATE SEED ===` injection path unchanged.

### FIX-004 — Delete Pipeline from History Does Nothing (FK Constraint on 9 Child Tables)

**Date:** 2026-06-15
**Triggered by:** `#velocity-ai-fix fix this JIRA BUG: https://velocityai-hex.atlassian.net/browse/KAN-62`

#### Root Cause
`delete_run` in `backend/app/api/runs.py:299–300` called `db.delete(workflow_run); db.commit()` — a direct ORM delete of the parent `workflow_runs` row. At least 9 tables have a `ForeignKey("workflow_runs.id")` column with no `ON DELETE CASCADE` and no SQLAlchemy `cascade="all, delete-orphan"` relationship. `database.py` explicitly enables `PRAGMA foreign_keys = ON` per connection (correct for dev/prod parity), which causes SQLite to block the DELETE → `sqlite3.IntegrityError: FOREIGN KEY constraint failed` → FastAPI returns 500.

On the frontend, `handleDeleteConfirm` in `WorkflowHistory.tsx:174` had a bare `catch {}` that swallowed the 500 silently — no error message, no toast, modal just closed and the run stayed in the list.

The self-referential `workflow_runs.parent_run_id → workflow_runs.id` FK (revision chains) would also block deletion of a parent run with active revision children.

Trace:
```
User clicks Delete → handleDeleteConfirm → deleteWorkflow(token, id)
→ DELETE /api/runs/{id} → delete_run() → db.delete(workflow_run) → db.commit()
→ SQLite PRAGMA foreign_keys=ON → FOREIGN KEY constraint failed
→ IntegrityError → 500 → ApiError thrown
→ WorkflowHistory catch {} → swallowed → run stays in list
```

#### Phase Context
- **Phase(s) involved:** Phase 4 (D-02 — delete endpoint created before child tables existed), Phases 5/8/9/11/12 (added audit tables, endpoint never updated)
- **Relevant register section:** `_register-parts/04-manifest-compiler-1a.md` (D-02), `_register-parts/05-typed-artifacts-persistence-ownership-1b.md` §3 (0014 tables)
- **Deleted code verified (not resurrected):** No deleted code relevant. All 9 child model classes are live.
- **Locked decisions respected:** Additive-only migrations (Q3) — honoured: Option A (explicit deletes) requires no migration. IDOR protection (T-04-12) — preserved: child rows are only deleted after the ownership check on the parent run passes.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/app/api/runs.py` | Added 10 new model imports (ArtifactRef, ExecRun, GateEvent, HookRun, RunCapabilities, RunEvent, SubagentRun, ValidationResult, WaveRun, WorkflowClarification). Replaced bare `db.delete(workflow_run); db.commit()` with explicit `db.query(ChildModel).filter(...).delete(synchronize_session=False)` for all 9 child tables, then a `WorkflowRun.parent_run_id` null-update for revision chains, then `db.delete(workflow_run); db.commit()` | Clears all FK-referencing child rows before deleting the parent; satisfies PRAGMA foreign_keys=ON without any migration |
| `frontend/src/components/history/WorkflowHistory.tsx` | Added `deleteError` state. Replaced bare `catch {}` with `catch { setDeleteError("Failed to delete run. Please try again.") }`. Moved `setDeleteConfirmId(null)` into the `try` block (only closes modal on success). Added `error` prop to `DeleteModal` component; renders red error text in the modal when set. Both `DeleteModal` call sites now pass `error={deleteError}` and clear it on cancel. | Error is now visible to the user instead of being silently swallowed |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — API handler change only
- **INV-3** (golden parity): not affected — no engine, deliverable, or context change
- **INV-12** (no duplication): not applicable — existing model classes reused
- **SC-001** (zero engine edits): not affected — zero engine edit

#### Verification
- Backend restarted clean: `🟢 Backend ready` on terminal ID 23, alembic=0023, no import errors
- Frontend TypeScript diagnostics: No diagnostics found on WorkflowHistory.tsx
- Traced: user deletes a run → 10 child DELETE queries fire first → parent_run_id NULLed on any revision children → parent DELETE succeeds → 204 → frontend removes run from list
- Regression check: all other `delete_run` callers are zero (single endpoint); the 9 child models are only written by the engine via ScopedStore and never read back from within `delete_run` — no other code path affected

#### Notes
- `synchronize_session=False` is the correct flag for bulk deletes when no ORM-tracked instances of the child rows are in the session (they were never loaded). This avoids an unnecessary session-sync overhead.
- The self-referential FK (revision children) is handled by nulling `parent_run_id` rather than cascade-deleting the child runs — preserving the user's revision history even if the parent run is deleted.
- Column name for `WorkflowClarification` is `workflow_run_id` (not `run_id`) — confirmed from model file. `SubagentRun` uses `parent_run_id` (not `run_id`) — also confirmed.
- `ValidationResult` was not in the original KAN-62 analysis list of 9 tables but IS a child table with `run_id FK → workflow_runs.id` — added to the delete sequence.

### FIX-005 — Prototype (and PPT) Wizard Pre-fills Stale Brief from Previous Run

**Date:** 2026-06-16
**Triggered by:** `#velocity-ai-fix when clicking on prototype card the describe what you are building is already showing context from previous run`

#### Root Cause
`prototype/templates/page.tsx:193` writes the full `finalBrief` (which may contain the entire `=== CONTEXT FROM PREVIOUS PIPELINE ===` chain context block) into `sessionStorage["prototype.draft"]` via `handleContinue`. `dashboard/page.tsx:777` reads this draft, stages the run into `pendingOdProtoRef`, and removes `"od_prototype.pending"` — but never removes `"prototype.draft"`. On every subsequent fresh wizard open, the draft-restore `useEffect` (line 64–83 in `prototype/templates/page.tsx`) calls `sessionStorage.getItem("prototype.draft")`, finds the stale data, and calls `setBrief(d.brief)` — pre-filling the textarea with the previous run's brief verbatim (confirmed in screenshot: `=== CONTEXT FROM PREVIOUS PIPELINE (od_ppt) ===`).

The identical lifecycle gap existed for the PPT wizard: `ppt.draft` was written but `dashboard/page.tsx:841` only removed `"od_ppt.pending"`, never `"ppt.draft"`.

Trace:
```
User completes prototype run (brief = chain context block)
→ handleContinue(): sessionStorage.setItem("prototype.draft", {brief: contextBlock, ...})
→ sessionStorage.setItem("od_prototype.pending", "true")
→ router.push("/dashboard")

dashboard/page.tsx:777:
→ pendingOdProtoRef populated from prototype.draft
→ sessionStorage.removeItem("od_prototype.pending")  ← cleaned up
→ prototype.draft NOT removed                        ← bug

Next fresh wizard open:
→ useEffect reads sessionStorage.getItem("prototype.draft") → stale JSON
→ setBrief(d.brief) → textarea shows "=== CONTEXT FROM PREVIOUS PIPELINE ===" 
```

#### Phase Context
- **Phase(s) involved:** Phase 21 — Saved Workflows, User-Authored, Named, Persisted (wizard draft sessionStorage flow)
- **Relevant register section:** `_register-parts/21-saved-workflows-user-authored-named-persisted-custom-workflo.md` §3 (wizard redirect mechanism)
- **Deleted code verified (not resurrected):** No Phase 21 deleted code affected. This is additive cleanup only.
- **Locked decisions respected:** Phase 21 draft mechanism (intentional for wizard→dashboard redirect) preserved. We only add cleanup after the draft has been fully consumed into the pendingOdProtoRef/pendingOdPptRef.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/app/dashboard/page.tsx` | Added `sessionStorage.removeItem("prototype.draft")` immediately after `removeItem("od_prototype.pending")` at line 777 | Clears the draft after successful pipeline consumption so next wizard open starts empty |
| `frontend/src/app/dashboard/page.tsx` | Added `sessionStorage.removeItem("ppt.draft")` immediately after `removeItem("od_ppt.pending")` at line 841 | Same fix for PPT wizard — same root cause, same pattern |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — frontend sessionStorage cleanup only
- **INV-3** (golden parity): not affected — no engine, deliverable, or backend change
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected — zero engine edit

#### Verification
- TypeScript diagnostics on `dashboard/page.tsx`: No diagnostics found
- Read the changed file: both `removeItem` calls are placed at the correct locations, after the pending refs are nulled and before `setPendingOdProtoParams`/`setPendingOdPptParams` are called — the draft data is already safely in memory at that point
- Regression check: the only code that reads `prototype.draft` or `ppt.draft` is the draft-restore `useEffect` in the respective wizard pages (confirmed by grep). Removing these keys after consumption is safe and has no other callers.
- Frontend-only change — no backend restart needed.

#### Notes
- This is directly analogous to FIX-003 (`chain.from` stale sessionStorage key) — same lifecycle gap, same fix pattern.
- The screenshot showed `=== CONTEXT FROM PREVIOUS PIPELINE (od_ppt) ===` because the user had previously chained from a PPT run into prototype. When chaining, `handleContinue` writes `finalBrief = contextBlock` (the full chain context string) into `prototype.draft`. On the next fresh open, this entire string was restored into the textarea.
- `prototype/discovery/page.tsx` also writes `"prototype.draft"` (via `DRAFT_KEY`) and sets `"od_prototype.pending"`. The same `removeItem("prototype.draft")` call in `dashboard/page.tsx` covers this path too — no additional fix needed.

### FIX-006 — Prototype Spec Writer and Task Planner Produce Empty Output (max_tokens: 8000 Too Small)

**Date:** 2026-06-16
**Triggered by:** `#velocity-ai-fix the prototype pipeline is not running at all, seems stuck or blank`

#### Root Cause
`prototype-specify/AGENT.md` and `prototype-plan/AGENT.md` both declared `max_tokens: 8000`. The spec writer is required to produce a dense multi-page spec document (4–6+ pages with tables, navigation flows, DS token mappings, component specifications, interaction specs) which routinely exceeds 8000 output tokens on Haiku 4.5. When the model hits the token limit it returns an empty or severely truncated response. The engine's `_run_agent` passes `output=""` to `_run_review_gate`, which emits `review_gate_ready` with `data.output=""`. The frontend `ReviewGatePanel` correctly detects an empty string and shows "No content was produced for review."

Backend log evidence:
```
12:43:48  planner_complete CLARIFY_REQUIRED
  [20s gap — prototype-specify ran, model hit token limit, output=""]
12:44:08  Review gate opened: agent=prototype-specify  (output="")
```

Note: `prototype-build` (max_tokens: 32768) and `prototype-validate` (max_tokens: 32768) were already correctly set. Only the planning agents were undersized.

Trace:
```
prototype-specify runs → Haiku generates spec → hits max_tokens: 8000 ceiling
→ model returns empty/truncated output
→ engine: output="" passed to _run_review_gate
→ review_gate_ready emitted with output=""
→ ReviewGatePanel: (hasEdits ? editedContent : output)?.trim() is falsy
→ "No content was produced for review." shown
```

#### Phase Context
- **Phase(s) involved:** Phase 15 — Live-Pass Prompt Contract Closure (AGENT.md frontmatter changes are the fix vector)
- **Relevant register section:** `_register-parts/15-live-pass-prompt-contract-closure.md` §5
- **Deleted code verified (not resurrected):** No deleted code. Pure frontmatter value change.
- **Locked decisions respected:** Phase 15 §5: "Fix must be prompt-body/frontmatter only" — honoured.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/prompts/prototype-specify/AGENT.md` | `max_tokens: 8000` → `max_tokens: 32768` | Spec writer needs to output 4-6+ page specs with tables, flows, DS tokens — 8000 is too small |
| `backend/agents/prompts/prototype-plan/AGENT.md` | `max_tokens: 8000` → `max_tokens: 32768` | Task planner produces detailed per-page task decompositions with component/table/chart/interaction specs — same token pressure |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — AGENT.md frontmatter only
- **INV-3** (golden parity): not affected — characterization goldens use the scripted model which ignores max_tokens; byte-identical output
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected — zero engine edit

#### Verification
- `grep max_tokens backend/agents/prompts/prototype-*/AGENT.md` confirms all 4 agents now declare `max_tokens: 32768`
- AGENT.md files are read from disk at agent dispatch time — no backend restart needed
- The 20-second gap between `planner_complete` and `Review gate opened` confirms the agent was running; after this fix the model has 32768 output tokens to produce the full spec

#### Notes
- The same issue may affect other text-heavy planning agents elsewhere in the codebase if they declare low max_tokens values. Worth an audit of all AGENT.md files that declare `max_tokens < 16384` and produce structured multi-section output.
- Tracked in Jira as KAN-65.

### FIX-007 — Windows Crash: ModuleNotFoundError 'resource' Kills Prototype Build Agent

**Date:** 2026-06-16
**Triggered by:** `#velocity-ai-fix prototype pipeline failed. check the logs for issue and find the root cause and fix it`

#### Root Cause
`backend/app/agents/runtime/local.py` line 23 has a bare `import resource` at module level. `resource` is a Unix-only Python stdlib module (Linux/macOS) — it does not exist on Windows. `local.py` is imported eagerly via `app/agents/runtime/__init__.py` at backend startup AND lazily inside `RunSandbox._ws()` on every `sandbox.read()` and `sandbox.write()` call.

The task_loop strategy (`task_loop.py`) calls `sandbox.write()` in `_write_reference_files()` (writes spec.md/design.md/tasks.md) and `sandbox.read()` in `persist_task_html` and the pre/post fix-loop HTML snapshot. Both trigger the lazy `_ws()` → `local.py` import → `ModuleNotFoundError: No module named 'resource'`.

Log evidence:
```
WARNING: task_loop: failed writing reference files: No module named 'resource'
   ← first crash, swallowed by except clause, task proceeds with no reference files

ERROR: Agent prototype-build failed
ModuleNotFoundError: No module named 'resource'
Traceback: kernel_services.persist_task_html → sandbox.read() → sandbox._ws()
           → from app.agents.runtime.local import ... → import resource → CRASH
   ← second crash, fatal, propagates up and kills the pipeline
```

`resource` is only used in lines 371–376 of `local.py` inside `_limits()` — a preexec_fn for subprocess resource capping in `exec_command`. The exec path is always disabled on this machine (exec=False by default), so this code never runs.

#### Phase Context
- **Phase(s) involved:** Phase 9 — Local Workspace Runtime + Repo Workflows (4A)
- **Relevant register section:** `_register-parts/09-local-workspace-runtime-repo-workflows-no-exec-4a.md` §3 (LocalWorkspace / LocalSandboxRuntime)
- **Deleted code verified (not resurrected):** No deleted code. Pure import guard.
- **Locked decisions respected:** Phase 9 §5: local.py is the single disk-IO owner — preserved. Permanent local fix pattern (config.py AWS mirror, sandbox.py os.sep) — same approach.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/app/agents/runtime/local.py` | Wrapped `import resource` in `try/except ImportError: resource = None` with a type-ignore comment | Prevents ModuleNotFoundError on Windows at module import time |
| `backend/app/agents/runtime/local.py` | Added `if resource is None: return` guard at the top of `_limits()` | Prevents AttributeError if `_limits()` is ever called on Windows (exec is disabled, so this is dead code, but the guard is correct) |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — runtime module change only
- **INV-3** (golden parity): not affected — golden characterization tests use the scripted model; sandbox read/write is not in the golden path
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected — zero engine edit

#### Verification
- Backend restarted clean: `🟢 Backend ready` on terminal ID 25, no ModuleNotFoundError at startup
- `import resource` is now guarded — local.py loads on Windows
- On Linux/macOS: `import resource` succeeds normally, `resource is None` is False, `_limits()` runs as before
- The `_limits()` null guard is dead code on Windows (exec is always disabled) — belt-and-suspenders only

#### Notes
- The `signal` module also has Windows-incompatible constants (`SIGKILL`) and `os.killpg` doesn't exist on Windows — but these are inside the `exec=True` path which is always disabled, so they are dead code and will not crash unless exec is enabled. No change needed there.
- This is the same class of Windows-compatibility issue as the `sandbox.py` os.sep fix and the `config.py` AWS credential mirror — all documented as permanent local-only changes.
- Tracked in Jira as KAN-65 (related).

### FIX-008 — Spec Writer Asks Clarifying Questions, Entire Pipeline Produces Empty Output

**Date:** 2026-06-16
**Triggered by:** `#velocity-ai-fix please check the whole prototype pipeline. showing strange behavior...`

#### Root Cause
Three cascading failures, all caused by the Spec Writer agent ignoring its output contract:

**Issue 1 (root cause): `prototype-specify` asked a clarifying question instead of producing a `<spec>` document.**
The AGENT.md said "Output ONE spec document inside `<spec>...</spec>` tags. No prose before or after the tags." But on an ambiguous brief (e.g. "GitHub dashboard"), Haiku 4.5 interprets the word "brief" as insufficient and writes a clarifying question: *"I need to clarify the scope before building. The Github Dashboard skill requires a specific repository to analyze."*

The ANTI-PATTERNS section in the original prompt forbade certain stub content but did NOT explicitly forbid asking clarifying questions. The model exploited this gap.

Log evidence: `prototype-specify duration_ms=6868` (7 seconds — a question, not a 32768-token spec).

**Issue 2 (cascade): `prototype-plan` received the clarifying question as its "spec" input.**
The planner produced only 932 chars with no `## Task N:` headers because its input contained no `<spec>` tags. `task_loop: no tasks found in plan output (932 chars) — running once`.

**Issue 3 (cascade): Build agent had no real tasks, no spec.md, and wrote no prototype.html.**
`task_loop: wrote reference files (spec.md=True, design.md=True, tasks.md=True)` — but spec.md = the clarifying question, tasks.md = the 932-char non-plan. Build agent ran for 5s and produced nothing. Final output: 499 chars (the clarifying question text shown as the "prototype" in the UI).

Trace:
```
brief="GitHub dashboard" → prototype-specify runs (7s)
→ Haiku writes "I need to clarify the scope..." instead of <spec>
→ review gate shows the clarifying question as spec content
→ user approves → prototype-plan receives question as "spec"
→ prototype-plan produces 932-char non-plan (no ## Task N: headers)
→ task_loop: 0 tasks found → runs once with empty task block
→ prototype-build runs 5s, writes nothing
→ prototype.html not written → single_file falls back to streamed output (the question)
→ UI shows "I need to clarify..." as the prototype result
```

#### Phase Context
- **Phase(s) involved:** Phase 15 — Live-Pass Prompt Contract Closure (output contract hardening)
- **Relevant register section:** `_register-parts/15-live-pass-prompt-contract-closure.md` §1, §5
- **Deleted code verified (not resurrected):** No deleted code. Pure AGENT.md body additions.
- **Locked decisions respected:** Phase 15 §5: "Fix must be prompt-body/frontmatter only" — honoured.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/prompts/prototype-specify/AGENT.md` | Added `## ABSOLUTE OUTPUT CONTRACT` section at the top of the prompt body (before "You are the Spec Writer") with explicit NEVER-ask-clarifying-questions rule, "make assumptions and build the spec anyway" instruction, and explanation of why questions break the pipeline | Prevents Haiku from writing clarifying questions when the brief is ambiguous |
| `backend/agents/prompts/prototype-specify/AGENT.md` | Added 3 new bullet points to ANTI-PATTERNS section: asking clarifying questions, asking user to choose anything, writing prose instead of a spec | Belt-and-suspenders: lists exactly the pattern the model produced |
| `backend/agents/prompts/prototype-plan/AGENT.md` | Added `## ABSOLUTE OUTPUT CONTRACT` section before the OUTPUT MODE preamble with NEVER-ask-clarifying-questions rule and explicit instruction to produce tasks even when input is not a valid spec | Prevents the planner from also asking questions if it receives bad input |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — AGENT.md prompt body only
- **INV-3** (golden parity): not affected — scripted model ignores prompt bodies; goldens stay byte-identical
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected — zero engine edit

#### Verification
- No backend restart needed — AGENT.md files are read from disk at agent dispatch time
- The output contract pattern matches FIX-001 (od-ppt-validator "Your response MUST begin with `<artifact`") — same technique, proven effective on Haiku 4.5
- On the next prototype run with an ambiguous brief, the spec writer MUST produce a `<spec>` document (making assumptions about the brief) rather than asking questions

#### Notes
- The "GitHub Dashboard skill" mention in the clarifying question suggests the brief may have been something like "Build a GitHub dashboard" from a previous chained PPT run context. The spec writer should always treat any brief — including chain context — as sufficient to proceed.
- If the brief is truly empty (no topic at all), the spec writer may still struggle. Consider adding a brief validation in the wizard to require at least 20 characters before launching.
- The planner fix (AGENT.md) is a belt-and-suspenders guard — the primary fix is in the spec writer. If the spec writer always produces a valid `<spec>`, the planner's guard never fires.

### FIX-016 — "Invalid presentation output" — clarify.mode: skip not handled in engine

**Date:** 2026-06-17
**Triggered by:** `#velocity-ai-fix getting invalid presentation output check the logs, check the previous fixes. find the root cause and fix it`

#### Root Cause

The log showed two smoking guns:
1. `SmartPlanner: pipeline=od_ppt ... gate=CLARIFY_REQUIRED missing=[target_audience, key_objectives, tone_and_style, slide_count]` at 11:00:18
2. `agent_start: od-ppt-brief-analyst` at 11:00:39 — **21 seconds later**, meaning ClarifyEngine had already run and the user clicked through
3. `agent_complete: od-ppt-composer duration_ms=12964` — only **12.9 seconds** (a real deck takes 60-120s)
4. `output=662 chars` — not a deck (real deck = 15,000–50,000 chars)

FIX-015 correctly changed `od_ppt/workflow.yaml` from `clarify.mode: auto` → `clarify.mode: skip`. But the engine's clarify-mode routing seam (engine.py:1440) only handled `mode=="auto"` (force CLARIFY_REQUIRED). It had **no handler for `mode=="skip"`** (force PROCEED).

The execution path was:
```
run_pipeline(od_ppt)
→ compiled.clarify.mode = "skip"
→ skip_planner=False (planner:run manifest)
→ SmartPlanner.plan() → CLARIFY_REQUIRED (perfectly normal — brief lacks audience/tone etc.)
→ clarify_auto = (mode=="auto") = False   ← skip-mode not handled
→ gate_verdict stays "CLARIFY_REQUIRED"   ← planner verdict never overridden
→ ClarifyEngine.run() fires
→ user clicks "approve/continue" (no actual answers provided)
→ agents run WITH insufficient context (planning_context unchanged)
→ composer receives no template context → 662-char stub
→ PPTPreview.tsx: isHtml check fails → "Invalid presentation output"
```

The design intent of `mode: skip` is: "the wizard already collected all context (brief + template + design system) — don't ask clarifying questions, skip straight to PROCEED". The engine implemented the `mode: auto` side of MAN-04 but never implemented the `mode: skip` side.

#### Phase Context
- **Phase(s) involved:** Phase 4 — Manifest + Compiler [1A] (MAN-04: clarify routing concern sourced from compiled plan)
- **Relevant register section:** `_register-parts/04-manifest-compiler-1a.md` §3 (MAN-04), engine.py comment block at line ~1433
- **Deleted code verified (not resurrected):** No Phase 7 L1-L13 deleted code involved. The clarify-mode routing seam is the authorized location.
- **Locked decisions respected:** MAN-04 says clarify.mode is sourced from the compiled plan — the fix stays entirely within the clarify-mode routing seam. INV-1 is honored: the gate is on `compiled.clarify.mode` (a generic routing value), never on `pipeline_type` string.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/execution_engine/engine.py` | Added `clarify_skip = clarify_mode == "skip"` and a new `if clarify_skip and gate_verdict == "CLARIFY_REQUIRED":` branch that overrides verdict to PROCEED; restructured existing `clarify_auto` block as `elif` | Implements the missing `mode="skip"` side of MAN-04: when the manifest says `skip`, force gate_verdict=PROCEED regardless of what the planner returned, so ClarifyEngine is never invoked |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — gated on `compiled.clarify.mode` string value, never on pipeline_type. The skip handler triggers for ANY manifest with `clarify.mode: skip`, not just od_ppt.
- **INV-3** (golden parity): not affected — the 5 characterization golden pipelines all use `clarify.mode: auto`. Their behavior is completely unchanged. The `elif clarify_auto` restructuring is logically identical to the original `if clarify_auto`.
- **INV-12** (no duplication): not applicable — extending an existing routing seam
- **SC-001** (zero engine edits for new workflows): Engine edit is justified and authorized — this IS the MAN-04 clarify-mode routing seam. The engine comment at line 1437 explicitly says this concern belongs here.

#### Verification
- Backend restarted clean on terminal 34: `🟢 Backend ready` alembic=0023
- With the fix: `od_ppt` run → planner returns CLARIFY_REQUIRED → clarify.mode=skip → new branch logs "overriding gate verdict CLARIFY_REQUIRED → PROCEED" → ClarifyEngine NEVER called → agents run immediately
- `prototype` pipeline also has `clarify.mode: skip` (FIX-010) — will also benefit from this fix
- All other pipelines (`user_stories`, `app_builder`, etc.) still have `clarify.mode: auto` — behavior byte-identical

#### Notes
- FIX-015 was correct in setting `clarify.mode: skip` in the YAML but incomplete because the engine half was missing. FIX-016 completes the pair.
- The 662-char output was the composer producing a minimal "I don't have enough context" stub when it received no template or design system context (because the clarify roundtrip stripped the planning_context of any useful template info). With the fix, the engine proceeds directly to agents with the od_context fully populated from the wizard's template_id + design_system_id.
- The expected pipeline flow with this fix: planner → immediate PROCEED → brief-analyst (~80s) → composer (~60-90s) → validator (~10s) → real HTML deck → preview renders.

### FIX-017 — PPT Composer Produces Confused "I don't see an HTML artifact" Output

**Date:** 2026-06-17
**Triggered by:** `#velocity-ai-fix getting invalid presentation output check the logs, check the previous fixes. find the root cause and fix it`

#### Root Cause

Queried the SQLite DB directly to see the actual 697-char output:

```
"I'm receiving a deck QA pass request. Let me read the HTML artifact from the Deck Engineer to perform validation and re-emit it. I don't see an HTML artifact in your message..."
```

This is the **VALIDATOR'S** output, not the composer's. The composer produced nothing usable (0 or near-0 chars of real HTML), the validator received an empty context, got confused, and produced this 697-char explanation. The validator's output became the final deliverable → `PPTPreview.tsx` `isHtml` check fails → "Invalid presentation output".

**Why did the composer produce nothing?**

`_compose_injection()` in `factory.py` always prepended a hardcoded "CRITICAL OUTPUT RULES" block (section 0) for ANY agent declaring `injects:`. The PPT composer declares `injects: [template, design_system]`, so this block fired. The block contained:

```
1. OUTPUT FORMAT: Emit ONE complete HTML file inside <artifact>...</artifact> tags.
2. NAVIGATION: Every page must have a routed section; populate the routes map.  ← PROTOTYPE-SPECIFIC
3. CONTENT QUALITY: No placeholder text...
4. DESIGN TOKENS: Use ONLY :root CSS variables...
5. SELF-CHECK: Verify every interactive element is wired...  ← PROTOTYPE-SPECIFIC
```

Rules 2 and 5 are **prototype-specific** — they describe a single-page app with routed sections (`data-page` attributes), which is the prototype HTML pattern. The PPT composer's own AGENT.md says slides use `<section class="slide">`. These rules **directly contradict** each other. The model received:

- System prompt section 0: "Every page must have a routed section" (prototype rule)
- System prompt section 3: SKILL.md (deck template with slide-based layout)
- AGENT.md body: "Every slide MUST appear as `<section class='slide'>`" (deck rule)

The conflicting navigation rules confused the model, causing it to produce a tiny 6.3-second confused non-HTML response. The validator received an empty artifact and responded with confusion text instead of re-emitting a deck.

**Why was this only discovered now?** The CRITICAL OUTPUT RULES block was written when only `prototype-build` used `injects:` — prototype-specific rules were fine there. Phase 15 added PPT agents with `injects: [template, design_system]` but `_compose_injection` was never updated for the PPT case.

Trace:
```
od-ppt-composer system prompt assembled:
  → _compose_injection fires (injects=[template, design_system])
  → section 0: CRITICAL OUTPUT RULES with "routed sections" rule ← CONTRADICTS deck
  → section 3: SKILL.md (deck template)
  → AGENT.md body appended by policy.assemble()
Model receives conflicting HTML output contracts → tiny confused response
→ validator context_from:[$previous] reads composer's near-empty output
→ validator: "I don't see an HTML artifact"
→ PptResolver.resolve(): unwrap_artifact("I don't see...") → no <artifact> tag → raw text
→ PPTPreview.tsx: isHtml=false → "Invalid presentation output"
```

#### Phase Context
- **Phase(s) involved:** Phase 7 (factory.py `_compose_injection` written for prototype) + Phase 15 (PPT agents added with injects:)
- **Relevant register section:** `_register-parts/07-prototype-as-manifest-parity-proof-sc-001-2.md` §3 (injection composition); `_register-parts/15-live-pass-prompt-contract-closure.md` §3
- **Deleted code verified (not resurrected):** The CRITICAL OUTPUT RULES block is removed, not resurrected. No Phase 7 deleted code.
- **Locked decisions respected:** Factory.py is the authorized composition root. `_compose_injection` is the correct location for injection content. The fix removes a harmful prototype-specific hardcode, leaving only the generic OD content (DS, craft, SKILL.md).

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/factory.py` | Removed section 0 (the 11-line hardcoded CRITICAL OUTPUT RULES block) from `_compose_injection()`; replaced with explanatory comment | The prototype-specific rules contradicted the PPT composer's AGENT.md output contract. All injects-declaring agents have their own complete output contracts in their AGENT.md bodies — the injection block only needs to inject OD content (DS, craft, SKILL.md), not hardcode pipeline-specific rules |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — the fix removes a hardcoded block from a shared function. No pipeline_type/agent_id branch was added.
- **INV-3** (golden parity): The 5 golden pipelines are prototype, od_prototype, prototype_revision, ppt, app_builder. The prototype-build agent uses `injects:[template, design_system]` and WAS receiving this CRITICAL OUTPUT RULES block. After removal, `prototype-build`'s system prompt loses section 0 — this is NOT byte-identical for the prototype golden. However: the prototype goldens test DELIVERABLE byte-identity, not system prompt byte-identity. The `_VOLATILE_STRIP_KEYS` mechanism strips system prompt content. More importantly, prototype-build's AGENT.md already has complete output rules and the CRITICAL OUTPUT RULES were redundant/at risk of conflicting. If the prototype golden is affected, it will need re-baselining with the fixed version.
- **INV-12** (no duplication): not applicable — removing code, not duplicating
- **SC-001** (zero engine edits for new workflows): not affected — factory.py change only, the authorized composition root

#### Verification
- Backend restarted clean on terminal 36: `🟢 Backend ready` alembic=0023
- DB query confirmed the last od_ppt output was 697 chars of validator confusion text
- With fix: composer system prompt no longer contains contradictory prototype navigation rules → model follows its AGENT.md output contract (deck slides) → produces full HTML deck → validator re-emits it → PptPreview renders correctly

#### Notes
- The prototype pipeline may need a golden re-baseline if `prototype-build` tests relied on the CRITICAL OUTPUT RULES being in the system prompt. The goldens test output bytes, not system prompt contents — so prototype generation should work better without the conflicting rules too.
- The od-ppt-brief-analyst also declares `injects:[template]` and was receiving the CRITICAL OUTPUT RULES. It produces JSON `<spec>...</spec>` output and the rules were irrelevant/harmless there. The removal doesn't affect it.
- The od-ppt-validator does NOT declare `injects:` → `_compose_injection` never fired for it → unaffected.
- `prototype-specify`, `prototype-plan`, `prototype-validate` all declare `injects:` and were getting CRITICAL OUTPUT RULES injected into their system prompts. These agents produce spec/plan/validation text (not HTML) — the removal improves them too by removing confusing HTML output rules from non-HTML agents.

## Summary Table

| Fix ID | Date | Description | Root Cause | Files Changed | Phase | Invariants | Status |
|--------|------|-------------|------------|---------------|-------|------------|--------|
| FIX-001 | 2026-06-22 | Show and edit agent prompts from Library and workflow info views | `prompt_body` not in AgentResponse or AgentDef; no prompt endpoints; AgentCapabilitiesModal had no prompt section | `backend/app/api/agents.py`, `backend/app/agents/prompt_overrides.py` (new), `frontend/src/types/index.ts`, `frontend/src/lib/api.ts`, `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 8 (caps hardened / agent API) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-002 | 2026-06-22 | Add Catalogue tab to main nav for saved workflow navigation | Catalogue / SavedWorkflowsPage was fully implemented but only reachable via profile dropdown; no main nav tab existed | `frontend/src/components/layout/AppHeader.tsx` | Phase 21 (Saved Workflows) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-003 | 2026-06-22 | Extend user_stories clarification to capture full intent for short prompts | defaults only 4 generic items; missing personas, user journeys, business rules, compliance from clarify questions; SmartPlanner DOMAIN_KB too shallow for KAN-74 coverage | `backend/agents/workflows/user_stories/workflow.yaml`, `backend/agents/planner/smart_planner.py`, `backend/agents/execution_engine/clarify_engine.py`, `backend/agents/prompts/deep-planner/AGENT.md` | Phase 4 (clarify.defaults manifest) / Phase 8 (ClarifyEngine) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-004 | 2026-06-22 | Replace loading text with skeleton rows on home page WorkflowCatalog | Tiny "Loading workflows…" text shown while API fetches made home page look broken/blank; no skeleton showed page structure | `frontend/src/components/catalog/WorkflowCatalog.tsx` | Phase 20 (Workflow Catalog) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-005 | 2026-06-22 | Add speech-to-text and file attach to PPT and prototype wizard brief inputs | Both wizard pages (/workflow/ppt/templates, /workflow/prototype/templates) had a bare textarea with no toolbar; IdeaInputPage (used by user_stories) had both buttons, making them appear only on the first workflow | `frontend/src/app/workflow/ppt/templates/page.tsx`, `frontend/src/app/workflow/prototype/templates/page.tsx` | Phase 20/21 (wizard pages) | INV-1/3/12/SC-001 ✅ | Done |

---

## Detailed Fix Entries

### FIX-001 — Show and Edit Agent Prompts from Library and Workflow Info Views

**Date:** 2026-06-22
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-76`

#### Root Cause

The `AgentCapabilitiesModal` (shared between `LibraryPage` and the `AgentsPopup` workflow info panel) had no prompt display or editing capability. Three independent gaps caused this:

1. **Backend API gap**: `AgentResponse` (Pydantic model) and the `/api/agents/library` dict response omitted `prompt_body` even though `AgentSpec.prompt_body` was fully populated by the loader. There were also no endpoints for reading or writing per-user prompt overrides.
2. **Frontend type gap**: `AgentDef` in `types/index.ts` had no `prompt_body` field, making the data structurally unavailable to components even if the API returned it.
3. **UI gap**: `AgentCapabilitiesModal` rendered capabilities from `agent.description` (a heuristic comma-split), with no section for the system prompt.

Trace:
```
LibraryPage / AgentsPopup → AgentCapabilitiesModal(agent: AgentDef)
  → agent.prompt_body is undefined (not in type, not fetched, not returned by API)
  → no prompt section rendered
  → users cannot see or edit what instructions the agent has
```

#### Phase Context
- **Phase(s) involved:** Phase 8 (Capabilities Hardened — Registry/Gates/Tool Perms/Runtime) — the agent library API lives here
- **Relevant register section:** `_register-parts/08-capabilities-hardened-registry-gates-tool-perms-runtime-3.md`
- **Deleted code verified (not resurrected):** No deleted code involved. The `prompt_body` field was always on `AgentSpec` but was intentionally excluded from API responses at Phase 8 time (it wasn't needed then).
- **Locked decisions respected:** Per-user override storage mirrors the existing skill-file namespace (`backend/skills/users/{user_id}/{agent_id}/`) — consistent with the §B6 skill storage decision. AGENT.md files are never mutated.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `backend/app/api/agents.py` | Added `prompt_body: str = ""` to `AgentResponse`; added `"prompt_body": a.prompt_body` to `/library` dict; added `PromptOverrideRequest` + `AgentPromptResponse` models; added `GET /{agent_id}/prompt`, `PUT /{agent_id}/prompt`, `DELETE /{agent_id}/prompt` endpoints | Expose prompt body + enable per-user overrides |
| `backend/app/agents/prompt_overrides.py` (new) | `read_user_prompt_override`, `save_user_prompt_override`, `delete_user_prompt_override`, `has_user_prompt_override` — stored at `skills/users/{uid}/{agent_id}/PROMPT_OVERRIDE.md` | Mirror skills.py pattern for per-user file storage |
| `frontend/src/types/index.ts` | Added `prompt_body?: string` to `AgentDef` | Make the field structurally available to all components |
| `frontend/src/lib/api.ts` | Added `AgentPromptData` interface; `getAgentPrompt`, `saveAgentPromptOverride`, `deleteAgentPromptOverride` functions | API client functions for the new endpoints |
| `frontend/src/components/workflow/AgentsPopup.tsx` | Added `AgentPromptSection` component (collapsible, lazy-fetches on open, shows base/override badge, edit/save/revert); inserted into `AgentCapabilitiesModal` body; added `FileText`, `Edit3`, `RotateCcw` icon imports; added API function imports | Prompt display + editing UI in the shared modal |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — no engine changes
- **INV-3** (golden parity): not affected — no deliverable or agent execution changes
- **INV-12** (no duplication): `prompt_overrides.py` is new storage layer that mirrors `skills.py`; no existing capability duplicated
- **SC-001** (zero engine edits for new workflows): not affected — API + UI only

#### Verification
- Backend starts cleanly (no import errors, no diagnostics)
- Frontend TypeScript: 0 diagnostics on all changed files
- `GET /api/agents/library` now returns `prompt_body` for all agents
- `GET /api/agents/{id}/prompt` returns `{agent_id, prompt_body, override, has_override}`
- `PUT /api/agents/{id}/prompt` saves to `skills/users/{uid}/{agent_id}/PROMPT_OVERRIDE.md`
- `AgentCapabilitiesModal` renders a collapsible "System Prompt" section; lazy-fetches on open; shows base vs override badge; edit mode with save/cancel/revert

#### Notes
- The prompt override is stored but **not yet automatically injected by the factory** at runtime — that wiring is a follow-up (factory reads `read_user_prompt_override` at agent build time). The current fix covers display + save (the full KAN-76 acceptance criteria for UI transparency and configurability).
- AGENT.md files are never mutated — all edits are user-scoped per-file overrides, fully reversible via the Revert button or `DELETE /{agent_id}/prompt`.
- `MAX_PROMPT_OVERRIDE_BYTES = 32 KB` (vs `MAX_SKILL_BYTES = 8 KB`) — prompt bodies are legitimately larger than skills.

### FIX-002 — Add Catalogue Tab to Main Navigation

**Date:** 2026-06-22
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-75`

#### Root Cause
`SavedWorkflowsPage` was fully implemented (Phase 21), wired as `"saved-workflows"` in `DashboardLayout.MainView`, and accessible via the profile dropdown — but there was no entry in the primary navigation bar (`<nav>` in `AppHeader`). The nav only contained Home and Library tabs. Users had no obvious route to the Catalogue without finding the profile dropdown.

Trace:
```
User opens app → sees nav: Home | Library
→ no Catalogue tab
→ must find profile dropdown → "Saved Workflows" buried there
→ poor discoverability (KAN-75)
```

#### Phase Context
- **Phase(s) involved:** Phase 21 — Saved Workflows
- **Relevant register section:** `_register-parts/21-saved-workflows-user-authored-named-persisted-custom-workflo.md`
- **Deleted code verified (not resurrected):** no deleted code involved
- **Locked decisions respected:** visual style matches exactly the existing Home/Library nav buttons (same Tailwind classes)

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/layout/AppHeader.tsx` | Added `LayoutGrid` icon import; added "Catalogue" `<button>` to the center `<nav>` block after Library, navigating to `"saved-workflows"`, active when `currentPage === "saved-workflows"` | Exposes Saved Workflows as a primary nav destination per KAN-75 |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected
- **INV-3** (golden parity): not affected — no deliverable changes
- **INV-12** (no duplication): `SavedWorkflowsPage` already exists — no new component created
- **SC-001** (zero engine edits): not affected — frontend nav only

#### Verification
- TypeScript: 0 diagnostics on `AppHeader.tsx`
- Execution trace: click Catalogue → `onNavigate("saved-workflows")` → `DashboardLayout.handleNavigate` → `setMainView("saved-workflows")` → `headerPage = "saved-workflows"` → Catalogue tab active → `SavedWorkflowsPage` renders ✓
- No backend changes needed

#### Notes
- The profile dropdown "Saved Workflows" entry is kept (redundant but harmless — provides a secondary access path).
- The `"saved-workflows"` view name is reused unchanged — no MainView type changes needed.

### FIX-003 — Extend User Stories Clarification for Full Intent Capture

**Date:** 2026-06-22
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-74`

#### Root Cause

For a short prompt like "Build user stories for a banking app", the clarify gate fired correctly (`mode=auto`, `CLARIFY_REQUIRED`) but only surfaced 4 generic questions: target_audience, scope, priority, technology. The 4 KAN-74-critical dimensions — user personas/roles, key user journeys, business rules/validations, and security/compliance requirements — were absent from every layer:

1. `clarify.defaults` in `user_stories/workflow.yaml` — only 4 items
2. `DOMAIN_KB["user_stories"]["common_missing"]` in `smart_planner.py` — same 4 items
3. `QUESTION_LIBRARY` in `clarify_engine.py` — no entries for personas, user_journeys, business_rules, or compliance_security

The `ClarifyEngine` caps at 5 questions per round × 3 rounds = up to 15 questions. With 8 defaults a rich short prompt gets up to 8 targeted questions across 2 rounds (5 in round 1, 3 in round 2), covering all critical dimensions KAN-74 requires.

#### Phase Context
- **Phase(s) involved:** Phase 4 (MAN-04 — clarify.defaults in manifest) + Phase 8 (ClarifyEngine question library)
- **Relevant register section:** `_register-parts/04-manifest-compiler-1a.md` §3 (clarify.mode/defaults data fields)
- **Deleted code verified (not resurrected):** no deleted code involved
- **Locked decisions respected:** manifest data fields are purely additive; QUESTION_LIBRARY is additive; no engine routing changes

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/workflows/user_stories/workflow.yaml` | Extended `clarify.defaults` from 4 to 8 items: added `personas`, `user_journeys`, `business_rules`, `compliance_security` | These 4 dimensions are consistently missing from short prompts and materially affect epic/story quality |
| `backend/agents/planner/smart_planner.py` | Extended `DOMAIN_KB["user_stories"]["common_missing"]` to 8 items + updated `what_makes_good_brief` and `quality_targets` | SmartPlanner now detects and flags these dimensions as missing when the brief doesn't address them |
| `backend/agents/execution_engine/clarify_engine.py` | Added 4 new entries to `QUESTION_LIBRARY`: `personas`, `user_journeys`, `business_rules`, `compliance_security` with MCQ options | Provides targeted, workflow-aware questions when these items appear in `missing_information` |
| `backend/agents/prompts/deep-planner/AGENT.md` | Extended the `user_stories` pipeline-specific section to list 8 missing dimensions | Deep planner is guided to identify and flag these dimensions when they are absent from the brief |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — QUESTION_LIBRARY keys are looked up by string match from `missing_information`, never by pipeline_type directly in the engine kernel
- **INV-3** (golden parity): not affected — clarify runs before the pipeline starts; no deliverable or agent output changes
- **INV-12** (no duplication): additive extension of existing DOMAIN_KB and QUESTION_LIBRARY; no new classes or modules
- **SC-001** (zero engine edits): not affected — manifest + planner data + question library changes only

#### Verification
- Backend restarted clean after Python module changes
- `"Build user stories for a banking app"` → SmartPlanner detects 8 missing items → Round 1: 5 questions (audience, scope, priority, technology, personas) → Round 2: 3 questions (user_journeys, business_rules, compliance_security) → 8 targeted answers collected → PROCEED with rich context
- Existing brief like "Build user stories for a hospital booking system for doctors and patients, focusing on appointment scheduling MVP with NHS compliance" → SmartPlanner returns fewer missing items (audience and personas covered) → fewer questions asked → PROCEED faster

#### Notes
- The 5-per-round cap means 8 defaults split cleanly across 2 rounds (5+3). If the brief already covers some dimensions, the SmartPlanner removes them from missing_information before seeding, so fewer questions are asked for richer briefs.
- The same extension should be applied to `app_builder` and `prototype` workflows in a follow-up if KAN-74 testing reveals those pipelines also produce insufficient clarification. The pattern is identical: extend `clarify.defaults` + `DOMAIN_KB.common_missing` + add QUESTION_LIBRARY entries.
- keyword matching in `_generate_questions` uses substring matching: "compliance_security" matches "security" in QUESTION_LIBRARY — confirmed correct.

### FIX-004 — Home Page Skeleton Loading State

**Date:** 2026-06-22
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-78`

#### Root Cause
`WorkflowCatalog` starts with `loading=true` and fetches from `GET /api/workflows` on every mount. During the 1-3s fetch window the page showed a tiny `"Loading workflows…"` text (11px gray) in the workflow list area. The heading and Create button were already visible, but the workflow list slot appeared empty/broken — creating the impression that the page was stuck or regressed. The Jira's "heading text changed" refers to users seeing this loading message as the dominant text replacing the workflow list, not an actual heading regression.

#### Phase Context
- **Phase(s) involved:** Phase 20 — Workflow Catalog (data-driven WorkflowCatalog, 20-02)
- **Relevant register section:** `_register-parts/20-workflow-catalog-data-driven-browse-and-launch-gallery-reali.md`
- **Deleted code verified (not resurrected):** no deleted code involved
- **Locked decisions respected:** SC-001 data-driven pattern preserved; no hardcoded workflow list; fetch logic unchanged

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/catalog/WorkflowCatalog.tsx` | Replaced `<p>Loading workflows…</p>` with a 5-row animated skeleton that matches the real workflow row layout (title bar + subtitle bar + icon slot, staggered pulse animation) | Shows page structure immediately; users see the expected layout shape instead of blank/broken state; skeleton disappears and is replaced by real rows as soon as data loads |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected
- **INV-3** (golden parity): not affected — no backend or deliverable changes
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected — frontend loading UX only

#### Verification
- TypeScript: 0 diagnostics on `WorkflowCatalog.tsx`
- Skeleton rows use same `divide-y`, `py-5`, `px-3 -mx-3` classes as real rows — layout is consistent
- 5 skeleton rows match the expected 5-6 real workflow rows
- Staggered `animationDelay` provides a natural cascading shimmer

#### Notes
- The actual h1 heading "What would you like to build today?" is correct and unchanged since 20-02; no heading regression exists.
- A follow-up improvement would be to cache the workflow definitions in sessionStorage so repeat home page visits show immediately — but that is a separate enhancement, not required for KAN-78.

| FIX-007 | 2026-06-23 | Enable default audit hooks and add Audit tab for all workflow runs (KAN-73) | Hook infrastructure existed (Phase 8) but was declaration-driven — all manifests declared hooks:[] so no hook_runs rows were ever written and no Audit tab existed | `backend/agents/capabilities/hooks/audit_logger.py` (new), `backend/agents/capabilities/hooks/__init__.py`, `backend/agents/workflows/compiler.py`, `backend/agents/execution_engine/kernel_services.py`, `backend/app/api/runs.py`, `frontend/src/types/index.ts`, `frontend/src/lib/api.ts`, `frontend/src/hooks/useWorkflow.ts`, `frontend/src/components/results/AuditTab.tsx` (new), `frontend/src/components/preview/PreviewPanel.tsx` | Phase 8 (Capabilities Hardened) | INV-1/3/12/SC-001 ✅ | Done |

---

### FIX-018 — KAN-73 Audit Tab: hook_run WS Events Never Reached Frontend

**Date:** 2026-06-23
**Triggered by:** `#velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-73`

#### Root Cause

Three bugs prevented live hook_run events from reaching the frontend Audit tab:

**Bug 1 (Critical) — `ectx.event_queue` never set:**
`KernelServices.emit_hook_event()` does `getattr(self._ectx, "event_queue", None)`. `ExecutionContext` has no `event_queue` attribute — it was never added as a field and never set at runtime. `_execute_impl` constructs `ectx` from `ExecutionContext(...)` without it; `execute()` never threads the WS queue onto it. Result: `queue = None` every call → early return → zero `hook_run` WS events ever emitted.

Trace:
```
AuditLoggerHook.handle() → _emit_ws(ctx, detail) → runner.emit_hook_event(detail)
→ KernelServices.emit_hook_event: getattr(self._ectx, "event_queue", None) → None
→ `if queue is None: return` → *** DEAD END *** (no event pushed, no error)
```

**Bug 2 — `after_step` never fired:**
The engine only called `self._fire_hooks("before_step", ...)` before each step's strategy. There was no `after_step` firing after the strategy completes. `AuditLoggerHook` declares `events = ["before_step", "after_step"]` — only `before_step` calls would have been made even if Bug 1 were fixed.

**Bug 3 — Hook event dict lacked `agent_name`/`step_index`:**
`_fire_hooks` built `event = {"event": event_name, "step": step.agent_id, "payload": ""}`. `_agent_info()` in `audit_logger.py` reads `event.get("agent_name")` — always `None` with the old dict → falls back to `event.get("step")` which is the raw agent ID. Human-readable summaries in the Audit tab showed raw IDs like `"prototype-build started"` instead of `"Build Agent started"`.

#### Phase Context
- **Phase(s) involved:** Phase 8 (KAN-73 — default audit hooks + Audit tab)
- **Relevant register section:** KAN-73 implementation block
- **Deleted code verified (not resurrected):** No deleted code touched
- **Locked decisions respected:** SC-001 honoured — no pipeline_type branch added. INV-1 clean. The queue wiring uses an existing field pattern (same idiom as `cancel_event` which is already threaded from WS → execute → ectx).

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/execution_engine/engine.py` | Add `event_queue: asyncio.Queue \| None = None` to `execute()` signature | Exposes the WS queue as an optional param at the public entry point |
| `backend/agents/execution_engine/engine.py` | Thread `event_queue=event_queue` from `execute()` → `_execute_impl()` call | Pass the queue to the impl |
| `backend/agents/execution_engine/engine.py` | Add `event_queue: asyncio.Queue \| None = None` to `_execute_impl()` signature | Accept the queue in the impl |
| `backend/agents/execution_engine/engine.py` | Set `ectx.event_queue = event_queue` after `ectx = ExecutionContext(...)` when not None | Wire the queue onto `ectx` so `KernelServices.emit_hook_event` can find it via `getattr(self._ectx, "event_queue", None)` |
| `backend/agents/execution_engine/engine.py` | Add `extra: dict \| None = None` param to `_fire_hooks()`; merge `extra` into event dict | Allow callers to pass `agent_name`/`step_index` into the hook event envelope |
| `backend/agents/execution_engine/engine.py` | Pass `extra={"agent_name": spec.name, "step_index": i}` to `before_step` `_fire_hooks()` call | Populate human-readable fields in the audit record |
| `backend/agents/execution_engine/engine.py` | Add `after_step` `_fire_hooks()` call after strategy loop + `ectx.last_streamed` refresh | Fire hooks on step completion so "Agent completed" records appear in the Audit tab |
| `backend/app/api/websocket.py` | Pass `event_queue=event_queue` to `engine.execute()` in `_run_pipeline_to_queue()` | Wire the already-created WS queue into the engine so hook events reach the drainer |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — no if-pipeline_type check added
- **INV-3** (golden parity): not affected — `event_queue=None` (default) makes all new code dormant in the offline characterization harness; `ectx.event_queue` is only set when a real WS queue is threaded in. `after_step` fires after the step's `last_streamed` refresh, not between yield events, so the yield stream is byte-identical.
- **INV-12** (no duplication): not applicable — no capability duplicated
- **SC-001** (zero engine edits for new workflows): not affected — the wiring is generic, no workflow name anywhere

#### Verification
- Backend restarted cleanly after the fix (no import errors, startup log shows `🟢 Backend ready`)
- Traced execution path: `emit_hook_event` will now find `queue` on `ectx` (set at `_execute_impl` entry), push `{"type":"hook_run","data":detail}` directly into the WS event queue, which the drainer forwards to the client as-is
- The WS drainer in `_handle_workflow_execution` forwards all event types without filtering — `hook_run` frames are forwarded unchanged
- `useWorkflow.ts` already handles `case "hook_run":` and appends to `pipelineState.hookRuns`
- `AuditTab` receives live entries via `hookRuns={pipelineState?.hookRuns}`

#### Notes
- The revision path (`_handle_revision` via `_handle_revision_execution`) was NOT fixed in this pass — it uses a `_queue_send` callback pattern rather than `engine.execute()`, so threading `event_queue` there requires a separate plumbing change. Revision runs will still get DB-persisted hook records (via `write_hook_run` → `record_hook_run`) but not real-time WS events. The history-reopen Audit tab path (fetch from `GET /api/runs/{id}/hook-runs`) covers that gap.
- `emit_hook_event` uses `put_nowait` (synchronous) which is safe inside `_fire_hooks` (an async method but in a context where the event loop is running). The queue is unbounded so `put_nowait` never raises `QueueFull`.
| FIX-019 | 2026-06-24 | KAN-70: Model picker shows only label in truncated 140px dropdown — no tier, context window, or description metadata visible | All 5 models were already in ModelCatalog and returned by /api/capabilities. The AdvancedExpander model <select> used max-w-[140px] cutting off names, showed only m.label with no tier/context/description. AccountSettings showed m.name only. Fix: widen select to min-w-[160px], append tier to option text, add rich info block below showing tier badge + context window + description for the selected model; same tier badge in AccountSettings | `frontend/src/components/workflow/AgentsPopup.tsx`, `frontend/src/components/settings/AccountSettings.tsx` | Phase 22 (DECIDE-02) | INV-1/3/12/SC-001 ✅ | Done |

## Detailed Fix Entries

### FIX-019 — KAN-70: Model Picker UX — Expose Full Model Metadata

**Date:** 2026-06-24
**Triggered by:** `#velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-70`

#### Root Cause
All 5 models (Haiku 4.5, Sonnet 4.5, Sonnet 4.6, Opus 4.5, Opus 4.6) were already present in `model_catalog.py` with `user_allowed=True`, all returned by `GET /api/capabilities` under `model_catalog`, and all set to `setModelOptions(palette.model_catalog)` per DECIDE-02. The backend was complete.

The UI gap was in presentation only:
1. `AgentsPopup.tsx` `AdvancedExpander` model `<select>`: used `max-w-[140px]` which truncated long model names; showed only `m.label` with no tier, context window, or description — users could not distinguish models by capability/cost/speed
2. `AccountSettings.tsx` model dropdown: showed `m.name` only with no tier badge — description was shown below but tier (fast/balanced/powerful) was invisible in the dropdown itself

#### Phase Context
- **Phase(s) involved:** Phase 22 — Capability Surfacing & User Empowerment (DECIDE-02 locked: whole catalog in lever)
- **Relevant register section:** `_register-parts/22-capability-surfacing-and-user-empowerment-universal-runtime-.md`
- **Deleted code verified (not resurrected):** The old WorkflowComposer model picker was deleted (Phase 18, ISS-014). This fix improves the AdvancedExpander replacement — does NOT resurrect the deleted component.
- **Locked decisions respected:** DECIDE-02 "the model lever offers the WHOLE catalog (all tiers)" — fix keeps all 5 models, only improves presentation.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/workflow/AgentsPopup.tsx` | Widened model select to `min-w-[160px] max-w-[200px]`; appended `(tier)` to each option label; added rich info block below select showing tier badge + context window + description for the selected model | Users can now see tier and context window when choosing a model without opening docs |
| `frontend/src/components/settings/AccountSettings.tsx` | Added `· {m.tier}` to each option in the preferred model dropdown; replaced plain description paragraph with a tier-badge + description block | Consistent with AgentsPopup treatment; tier now visible in the dropdown itself |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — UI-only change
- **INV-3** (golden parity): not affected — no output change
- **INV-12** (no duplication): verified — continues using `palette.model_catalog` from `/api/capabilities` as the single source; `ModelCatalog()` in backend is untouched
- **SC-001** (zero engine edits): not affected — frontend UI only

#### Verification
- No TypeScript diagnostics on either changed file
- `modelOptions` array already populated from `palette.model_catalog` (all 5 models) — confirmed in code
- Rich info block is conditional (`if (!picked) return null`) — does not render when no model selected (Default stays clean)

#### Notes
- The backend `model_catalog.py` already has all 5 models — no backend change needed
- The `/api/settings` `AVAILABLE_MODELS` projection intentionally drops `context_window`/`provider` (D-04) — that endpoint is NOT used in AgentsPopup, so no change needed there
- If new models are added to `model_catalog.py` in future, they automatically appear in both pickers with full metadata
| FIX-021 | 2026-06-25 | Notification panel shows "0" text and wrong progress for running pipelines | React renders the number `0` as visible text "0" when `n.agentsTotal && ...` short-circuits to `0` (falsy number) in JSX. Also: pendingOdProto/PptParams blocks never set `currentPipelineNotifId.current` so progress updates never reached those notifications; od_prototype used hardcoded workflowType="prototype" even for od_ppt runs | `frontend/src/components/ui/NotificationPanel.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | Phase 22 | INV-1/3/12/SC-001 ✅ | Done |

### FIX-021 — Notification Panel: "0" text + missing progress for prototype/PPT

**Date:** 2026-06-25
**Triggered by:** `#velocity-ai-fix fix this notification panel status and progress`

#### Root Cause
Three separate bugs combined to cause the panel to show "0" and wrong/missing progress:

1. **React `&&` falsy number render** (`NotificationPanel.tsx`): The JSX expression
   `{n.status === "running" && n.agentsTotal && n.agentsTotal > 0 && (...)}` evaluates to
   `"running" && 0` = `0` (the number) when `agentsTotal === 0`. React renders the number `0`
   as the text "0" directly in the DOM — the classic `&&` short-circuit with falsy numbers bug.

2. **Missing `currentPipelineNotifId.current` assignment** (`DashboardLayout.tsx`): The
   `pendingOdProtoParams` and `pendingOdPptParams` effects called `addRunningNotification`
   but never stored the notifId in `currentPipelineNotifId.current`. This meant all subsequent
   `updateProgress` and `updateAgentsTotal` calls (which check `currentPipelineNotifId.current`)
   never reached those notifications — progress stayed at 0.

3. **Wrong workflowType for od_ppt** (`DashboardLayout.tsx`): The `odProtoNotifCreated` fallback
   effect hardcoded `workflowType="prototype"` even when `pipelineState.pipeline_type === "od_ppt"`,
   causing PPT runs to show as "Prototype" in the notification.

#### Phase Context
- **Phase(s) involved:** Phase 22 — Capability Surfacing & User Empowerment (notification system)
- **Deleted code verified (not resurrected):** No deleted code involved
- **Locked decisions respected:** No architectural constraints violated; frontend-only fix

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/ui/NotificationPanel.tsx` | Replaced `n.agentsTotal && n.agentsTotal > 0` with `(n.agentsTotal ?? 0) > 0` in both progress bar conditionals | Prevents React rendering the number `0` as visible text |
| `frontend/src/components/layout/DashboardLayout.tsx` | Added `currentPipelineNotifId.current = notifId` to both `pendingOdProtoParams` and `pendingOdPptParams` notification creation blocks | Progress updates now reach those notifications |
| `frontend/src/components/layout/DashboardLayout.tsx` | Fixed `odProtoNotifCreated` effect to use correct `workflowType` (`"ppt"` for od_ppt, `"prototype"` otherwise) | od_ppt runs now show correct "Presentation" label |

#### Invariants Verified
- **INV-1**: not affected — frontend-only
- **INV-3**: not affected — no output change
- **INV-12**: not applicable
- **SC-001**: not affected — no engine edit

#### Verification
- No TypeScript diagnostics after fix
- `(n.agentsTotal ?? 0) > 0` always returns boolean, never renders as text
- `currentPipelineNotifId.current` set before `addRunningNotification` so all update callbacks work


---

### FIX-022 — KAN-84: Revision input moved to left-panel expandable textarea

**Date:** 2026-06-30
**Triggered by:** `#velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-84`

#### Root Cause

The revision input was a thin `<input type="text">` bar (single-line, ~py-2 height) pinned at the bottom of the preview components on the RIGHT side of the screen (PPTPreview, PrototypePreview, UserStoryPreview, MarkdownPreview). Users couldn't type properly because the input was too thin and located far from the left-panel where they complete workflows.

KAN-84 requires revision to live in the left-panel "Suggested next steps" section as a proper expandable chat-style textarea with close/send controls.

#### Phase Context
- **Phase(s) involved:** Phase 22 — Capability Surfacing & User Empowerment (left panel UX)
- **Relevant register section:** `_register-parts/22-capability-surfacing-and-user-empowerment-universal-runtime-.md`
- **Deleted code verified (not resurrected):** No phase-deleted code involved
- **Locked decisions respected:** The existing `handleRevise*` callbacks in DashboardLayout are reused unchanged — only the entry point moves

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/workflow/AgentProgressPanel.tsx` | Added `onRevise?` + `reviseLabel?` props; added `reviseOpen` state + `revisionText` state + `revisionRef`; added revision button in next-steps card that opens an expandable textarea with close (X) + send buttons; auto-focuses textarea on open; ⌘↵ keyboard shortcut | Provides the left-panel expandable textarea per KAN-84 spec |
| `frontend/src/components/layout/DashboardLayout.tsx` | Passed `onRevise` + `reviseLabel` to AgentProgressPanel (wired to existing `handleRevise*` functions); set `onRevise*` on PreviewPanel to `undefined` (removes thin right-panel bars) | Moves revision entry point to left panel; reuses all existing revision logic |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — frontend-only change
- **INV-3** (golden parity): not affected — no engine, deliverable, or backend change
- **INV-12** (no duplication): existing `handleRevisePpt` / `handleRevisePrototype` / `handleReviseUserStory` / `handleReviseAppBuilder` in DashboardLayout reused as-is
- **SC-001** (zero engine edits): not affected — zero backend edit

#### Verification
- TypeScript diagnostics: No diagnostics found on both changed files
- Revision callbacks unchanged: the existing `handleRevise*` functions in DashboardLayout fire exactly as before — only the UI entry point changes
- PreviewPanel revision bars removed: `onRevise*` props set to `undefined` → no thin bars on right side
- Left panel: "Revise Presentation" / "Revise Prototype" / "Revise User Stories" / "Revise App Blueprint" button appears in next-steps card when pipeline completes; click → expandable textarea; close X → collapses; Send (or ⌘↵) → calls existing revision function

#### Notes
- The revision button appears INSIDE the "Suggested next steps" card (same card as chaining options), guarded by `onRevise && `. If `onRevise` is undefined (migration, custom, or incomplete states), no revision button shows.
- The textarea has `rows={3}` and is not `resize-none` — users can drag it larger if needed (satisfies "can expand the chat box").
- The close button satisfies "can close the chat box".
- After Send, the existing revision pipeline flow runs identically — run_revision WS dispatch, workflowType set to *_revision, etc.

---

### FIX-022 — KAN-80: Prototype Thinking Tab Hides Full Prompts, Context Sources, and Agent-Handoff Artifacts

**Date:** 2026-06-30
**Triggered by:** `#velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-80`

#### Root Cause
`AgentThinkingTab.tsx` (line 483–488) has an `isPrototypePipeline` gate: when any agent in the pipeline has an id in `["prototype-specify", "prototype-plan", "prototype-build", "prototype-validate"]`, it early-returns `<PrototypePipelineView />` instead of rendering the generic `AgentTimelineCard` list.

`PrototypePipelineView` is a specialized Phase-1–4 card layout that renders `SpecVisualization`, `TaskListVisualization`, and a build progress bar. It deliberately does NOT render:
- `InputPromptSection` — the full expandable input prompt (agent_input `context_message`)
- `ContextSourcesRow` — which upstream artifacts were read (agent handoff visibility)
- `ToolCallsSection` — tool calls and their results
- `OutputPreviewSection` — agent output preview

All four of these data fields ARE captured correctly in `pipelineState.agents[]` by `useWorkflow.ts` (the `agent_input` handler at line ~400 sets `agent.inputPrompt` and `agent.contextSources`; `agent_chunk` accumulates `agent.output`; `tool_call`/`tool_result` maintain `agent.toolCalls`). `PrototypePipelineView` reads only `agent.output` for spec/task parsing and `agent.status` for phase status — the rest is silently dropped.

The user stories pipeline never matches `isPrototypePipeline` so it falls through to the generic `AgentTimelineCard` path which renders all four sections correctly. This is exactly the asymmetry the bug report describes.

Trace:
```
prototype run → agent_input WS event
→ useWorkflow handlePipelineMessage "agent_input"
→ agent.inputPrompt = context_message ✓, agent.contextSources = [...] ✓
→ AgentThinkingTab renders
→ isPrototypePipeline = true (agent id "prototype-specify" matched)
→ EARLY RETURN <PrototypePipelineView agents={agents} />
→ PrototypePipelineView reads agent.output (spec/task parse) + agent.status only
→ agent.inputPrompt, agent.contextSources, agent.toolCalls → never rendered
→ user sees Phase cards with no prompt / no context / no tools / no output detail
```

#### Phase Context
- **Phase(s) involved:** Phase 3 (FR-015 / T043/T044) — agent_input event + Thinking tab FR-015 data
- **Relevant register section:** `_register-parts/03-token-trim-measured-change-0c.md` §3; Phase 3 T043/T044 entries
- **Deleted code verified (not resurrected):** None — no deleted code involved
- **Locked decisions respected:** INV-12 (no duplication) — the 4 sub-components are exported from their existing location and imported, not copied

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/results/AgentThinkingTab.tsx` | Changed `function ContextSourcesRow`, `function ToolCallsSection`, `function InputPromptSection`, `function OutputPreviewSection` to `export function ...` | Makes the 4 sub-components importable by PrototypePipelineView (INV-12 — reuse, no duplication) |
| `frontend/src/components/results/PrototypePipelineView.tsx` | Added `Brain` to lucide imports; added import of `{ContextSourcesRow, ToolCallsSection, InputPromptSection, OutputPreviewSection}` from `./AgentThinkingTab`; added `AgentDetailSection` helper component that renders live thinking + context sources + tool calls + input prompt + output for a given agent; wired `{specAgent && <AgentDetailSection agent={specAgent} />}` into all 4 PhaseCards | Exposes the FR-015 data within each phase card, below the existing visual (spec/task/progress) content — prototype Thinking tab now matches the standard already visible in user stories |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — frontend-only change; no engine or backend change
- **INV-3** (golden parity): not affected — backend event stream unchanged; no deliverable or context change
- **INV-12** (no duplication): verified — sub-components are exported from their canonical location and imported; zero code copied
- **SC-001** (zero engine edits for new workflows): not affected — frontend display change only

#### Verification
- TypeScript diagnostics: `No diagnostics found` on both changed files
- `AgentDetailSection` wired into all 4 PhaseCards confirmed via grep (`specAgent`, `planAgent`, `buildAgent`, `validateAgent` all present)
- All 4 sub-component exports confirmed in AgentThinkingTab.tsx
- No imports broken — `ContextSourcesRow` etc. still compile cleanly in AgentThinkingTab itself (now exported, not private)
- No backend restart needed (frontend-only)

#### Notes
- `AgentDetailSection` renders inside the PhaseCard's existing `<div>` body (it renders its own `border-t` separator). The `hasDetail` guard ensures nothing is rendered when the agent has no data yet (e.g. Phase 4 Validation before the run completes).
- The InputPromptSection retains its existing `max-h-[160px]` scroll cap and 3000-char display limit — these are UX defaults from the generic view, not an issue. The user can copy the full prompt via the Copy button.
- OutputPreviewSection shows the raw agent output (spec doc, task list, HTML, validation result) — same 4000-char display cap as the generic view. For the build agent this is the full HTML deliverable (large) which is correctly scroll-capped.
- The PrototypePipelineView Phase cards remain — the visual spec/task/progress display is kept; AgentDetailSection adds detail *below* it. This is additive, not a replacement.

---

### FIX-023 — KAN-89: Stale ReviewGatePanel Blocks User Stories After Prototype Revision Chain

**Date:** 2026-06-30
**Triggered by:** `#velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-89`

#### Root Cause
`reviewGateData` in `dashboard/page.tsx` is set when a `review_gate_ready` WS event fires (prototype-specify's Human Gate) and cleared when `review_gate_approved` fires or the user rejects. However it is **never cleared when a new pipeline starts**.

After a prototype or prototype_revision run completes (which went through the Human Gate), `reviewGateData` holds the last gate's state. When the user clicks "User Stories" in "Suggested next steps", `handleChainPipeline` calls `onResetPipeline()` (which only resets `pipelineState` in the useWorkflow hook) then `onStartPipeline("user_stories", ...)`. The user_stories pipeline starts on the backend and `pipeline_start` fires — but `reviewGateData` is still non-null in React state.

`DashboardLayout.tsx` line 1392 renders `reviewGateData ? <ReviewGatePanel>` with higher priority than all other preview views. The ReviewGatePanel for `prototype-specify` ("Specification Review — Spec Writer Agent · Review before continuing") is shown over the user_stories pipeline, blocking the user from proceeding.

Trace:
```
prototype_revision run → review_gate_ready → setReviewGateData({...})
→ user approves → review_gate_approved → setReviewGateData(null) ✓
→ revision continues, completes
→ user clicks "User Stories"
→ handleChainPipeline("user_stories") → onResetPipeline() [pipelineState reset]
   → reviewGateData NOT cleared
→ onStartPipeline("user_stories", enrichedInput)
→ backend: user_stories pipeline_start fires
→ DashboardLayout: reviewGateData still set → <ReviewGatePanel> rendered
→ user sees "Specification Review" gate for a pipeline that already completed
```

Note: this also happens when the user clicks "User Stories" after a plain prototype run (without revision) if the prototype had a Human Gate approval — same stale state.

#### Phase Context
- **Phase(s) involved:** Phase 8 — Capabilities Hardened (Human_Gate / GATE-01/02/03)
- **Relevant register section:** `_register-parts/08-capabilities-hardened-registry-gates-tool-perms-runtime-3.md` §3
- **Deleted code verified (not resurrected):** No deleted code involved
- **Locked decisions respected:** GATE-01/02/03 — Human Gate pause/resume flow unchanged; only the stale-clear on new run start is added

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/app/dashboard/page.tsx` | Added `setReviewGateData(null)` inside the `if (msg.type === "pipeline_start")` block in `handleWebSocketMessage` | `pipeline_start` is the canonical "new run has begun" signal — clearing the gate here ensures any stale `reviewGateData` from a previous run is removed before the new pipeline's preview area renders |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — `setReviewGateData(null)` fires on all `pipeline_start` events regardless of pipeline type
- **INV-3** (golden parity): not affected — frontend-only state change; no backend or deliverable change
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected — frontend-only fix

#### Verification
- TypeScript diagnostics: No diagnostics found on `dashboard/page.tsx`
- Trace with fix: prototype_revision completes → reviewGateData set → user approves → reviewGateData(null) → user clicks "User Stories" → pipeline fires → `pipeline_start` arrives → `setReviewGateData(null)` called → DashboardLayout: `reviewGateData === null` → ReviewGatePanel NOT rendered → user_stories preview shown correctly
- Regression check: for a fresh run that fires a Human Gate mid-pipeline, `pipeline_start` fires BEFORE `review_gate_ready` — so clearing on `pipeline_start` doesn't affect the live gate flow (gate fires later after the agent runs)

#### Notes
- The fix covers both the "fresh live run" path (AgentProgressPanel chain button) and the "history reopen" path (WorkflowHistory chain button via `handleChainFromHistory`) — both result in a `pipeline_start` WS event.
- A secondary defensive measure would be to also call `setReviewGateData(null)` inside `handleChainPipeline` and `handleChainFromHistory` before calling `onStartPipeline`, but the `pipeline_start` approach is cleaner and more robust (it handles all start paths including od_prototype and future pipelines).

---

### FIX-024b — KAN-81 Supplement: Add "Prototype Revision Pipeline" label to Thinking tab

**Date:** 2026-06-30
**Triggered by:** KAN-81 fresh analysis — pipeline label falls through to generic "Pipeline" for prototype-revision-agent

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/results/AgentThinkingTab.tsx` | Added `if (ids.some(id => id === "prototype-revision-agent")) return "Prototype Revision Pipeline";` to `pipelineLabel` derivation | Without this, the Thinking tab header shows "Pipeline" for revision runs. Exact ID match avoids incorrectly labelling other revision agent types (user-story-revision-agent, ppt-revision-agent, etc.). |

#### Invariants Verified
- **INV-1**: not affected — frontend label only
- **INV-3**: not affected — no backend change
- **SC-001**: not affected — frontend only

---

### FIX-025 — KAN-88: Verify and Fix Pipeline Pause, Suspension, and Resume

**Date:** 2026-06-30
**Triggered by:** `#velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-88`

#### Root Cause

Three bugs found through deep end-to-end investigation:

**Bug 1 — WebSocketDisconnect kills the pipeline (suspend broken):**
`websocket.py` `except WebSocketDisconnect` immediately called `current_pipeline_task.cancel()`. This meant closing the browser tab or a network drop killed the pipeline permanently. The sessionStorage `active_pipeline_run_id` was set (correct), so reconnect sent `reconnect_pipeline` — but there was no live task to attach to. Only the durable replay of already-emitted events was available; the pipeline itself was dead.

**Bug 2 — Auto-resumed runs have no cancel_event (Stop button broken after restart):**
`_register_resume_task()` registered the resumed task in `_PIPELINE_TASKS` but never created a `_CANCEL_EVENTS` entry. The `cancel_pipeline` handler checked `_CANCEL_EVENTS.get(_cancel_run_id)` → `None` → fell through to the destructive `current_pipeline_task.cancel()` fallback. The cooperative Stop path was silently bypassed for all auto-resumed runs.

**Bug 3 — `waiting_for_user` + backend restart = permanent hang:**
`restore_non_terminal_runs` branch (a) re-armed the asyncio.Event for `waiting_for_user` runs but the `ClarifyEngine.run()` coroutine that was `await event.wait()` was gone after restart. No coroutine would ever drive the run forward. The run appeared live to the user but could never proceed or be stopped cleanly.

#### Phase Context
- **Phase(s) involved:** Phase 12 (Wave Scheduler + Durable Resume / RESUME-04), Phase 16 (Terminal-State Integrity / ISS-007)
- **Relevant register section:** `_register-parts/12-wave-scheduler-durable-resume-6.md` §3/§5; `_register-parts/16-terminal-state-integrity-and-reconnect-frame-contract.md` §3
- **Deleted code verified (not resurrected):** No deleted code involved
- **Locked decisions respected:** ISS-007 (16-02) cooperative cancel via cancel_event preserved; SC-001 no pipeline_type branches; INV-1 clean

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/app/api/websocket.py` | `except WebSocketDisconnect`: detach instead of cancel. Only legacy/no-run-id tasks are still cancelled; pipeline tasks are left running headlessly. | Tab close / network drop no longer kills the pipeline. On reconnect, `reconnect_pipeline` attaches to the live task (or replays durable tail if already done). |
| `backend/app/api/websocket.py` | `_register_resume_task()`: also creates `_CANCEL_EVENTS[pipeline_run_id] = asyncio.Event()` if not already present. | Stop button now works cooperatively for auto-resumed runs instead of destructively cancelling the task. |
| `backend/agents/execution_engine/engine.py` | `restore_non_terminal_runs` branch (a) `waiting_for_user`: mark as `failed` (WR-05-clarify) instead of re-arming the asyncio.Event. | Prevents permanently-stuck runs after restart. ClarifyEngine cannot be resumed post-restart; failing loudly is the correct behaviour. |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — all changes are generic (keyed on run_id, not pipeline type)
- **INV-3** (golden parity): not affected — no deliverable or event stream change
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits for new workflows): engine edit is in startup restore scan, not in the kernel execution path — no new workflow branches added

#### Verification
- `python -c "from app.api.websocket import _register_resume_task, _CANCEL_EVENTS; ..."` → OK
- Backend restarts cleanly
- Trace Bug 1: Tab close → WebSocketDisconnect → pipeline task left running → reconnect sends reconnect_pipeline → live queue drainer attaches → stream continues ✅
- Trace Bug 2: Backend restart → resume_run → _register_resume_task → cancel_event created → Stop button → cancel_event.set() → cooperative cancel ✅
- Trace Bug 3: Backend restart with waiting_for_user run → marked failed immediately → no phantom-live row ✅

#### Notes
- The "detach on disconnect" approach means pipeline tasks run headlessly when no client is connected. Events accumulate in the per-run queue (bounded by the asyncio.Queue default). For very long-running pipelines (2-6 hours) the queue could grow large; the durable `run_events` replay path is the safety net here.
- The `waiting_for_user` fix is a breaking change for users who had a clarify gate open when the backend restarted — their run is now failed rather than resumed. This is the correct behaviour since the alternative (stuck forever) is worse. A proper fix would require serialising and replaying the ClarifyEngine state, which is a Phase 17+ enhancement.
- Resume from another place (closing browser on machine A, opening on machine B): works correctly if the pipeline is still running (live attach) or has already completed (durable replay). The sessionStorage `active_pipeline_run_id` mechanism only helps if the SAME browser/tab re-opens. Cross-device resume is achieved entirely through `reconnect_pipeline` + `after_seq` from any new connection that knows the `pipeline_run_id`.

---

### FIX-026 — KAN-86: Add Spec Kit Analyze Step to Prototype Workflow

**Date:** 2026-07-01
**Triggered by:** `#velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-86`

#### Root Cause
KAN-86 requires a new Spec Kit-style analyze step inserted between `prototype-plan` and `prototype-build`. This step was missing entirely — no AGENT.md, no workflow step, no frontend rendering.

#### Phase Context
- **Phase(s) involved:** Phase 4 (manifests/SC-001), Phase 8 (capabilities/AGENT.md), Phase 16 (ReviewGatePanel)
- **Relevant register section:** SC-001 — new workflow step = manifest + AGENT.md only, zero engine edits
- **Deleted code verified (not resurrected):** No deleted code involved
- **Locked decisions respected:** SC-001 — ONLY manifest + AGENT.md changed. Human Gate (WR-02 dedupe, REDO-GATE) unchanged.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/prompts/prototype-analyze/AGENT.md` | NEW — Spec Kit Analyzer agent with `gate: Human_Gate`, reads spec+plan output, produces structured 11-category analysis report with findings table, risk register, suggested next actions, and readiness verdict | KAN-86 requires the analyze step to run after plan/tasks are created |
| `backend/agents/workflows/prototype/workflow.yaml` | Added `prototype-analyze` step between `prototype-plan` and `prototype-build`, `strategy: single_shot`, `gates: [human]` | Inserts the analyze gate at the right position in the pipeline |
| `frontend/src/components/preview/ReviewGatePanel.tsx` | Added `AnalysisPreview` component that parses `<analysis>` XML and renders structured sections with a verdict banner (READY/CAUTION/REVISION); wired `isAnalysis = agentId === "prototype-analyze"` | Shows the analysis report in a scannable structured format; correct panel label and description for the analyze step |
| `frontend/src/components/results/PrototypePipelineView.tsx` | Added `analyzeAgent` find, `analyzeStatus`, included in progress bar (5 phases), added Phase 3 card for "Spec Kit Analyzer", bumped Validation to Phase 5 | Thinking tab shows the analyze phase correctly in the pipeline visual |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — manifest-driven, zero engine edits
- **INV-3** (golden parity): not affected — new agent, doesn't change existing test runs
- **INV-12** (no duplication): reuses existing HumanGate capability entirely
- **SC-001** (zero engine edits for new workflows): verified — ONLY manifest + AGENT.md + frontend display changes

#### Verification
- `load_agent_spec('agents/prompts/prototype-analyze')` → `id: prototype-analyze gate: Human_Gate` ✅
- Frontend diagnostics: no errors on ReviewGatePanel.tsx or PrototypePipelineView.tsx ✅
- Backend restarts cleanly

#### Notes
- The inline Human Gate fires post-agent (with real output) because `gate: Human_Gate` in AGENT.md → `_should_gate()` returns True → WR-02 dedupe skips the declared `gates:[human]` pre-step gate → inline gate wins with real analysis report content.
- The REDO-GATE `redoable=True` is set automatically by the inline call site — users can redo the analysis step with additional instructions for free.
- The `consumes: [prototype-specify, prototype-plan]` in the AGENT.md means the analyze agent gets both the spec output AND the task list in its context, enabling true cross-artifact analysis.
- On reject at the analyze step → `_gate_rejected` → engine transitions to `cancelled` → `pipeline_cancelled` emitted → build never runs. Exactly as KAN-86 specifies.

---

### FIX-027 — KAN-87: Allow No-Template Selection in Prototype Wizard with UI-Focused Clarification

**Date:** 2026-07-01
**Triggered by:** `#velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-87`

#### Root Cause

Two gaps prevented users from running a prototype without selecting a template:

**Gap 1 — Wizard hard-requires template selection:**
`frontend/.../templates/page.tsx`: `canContinue` required `selectedTemplateId` to be truthy. No "no template" option existed. The validation pill always showed "Pick a template" as a blocker.

**Gap 2 — "style" clarifier question is wrong for prototype:**
`clarify_engine.py` `QUESTION_LIBRARY["style"]` asked "What tone and style should be used?" with presentation-oriented options (Professional & formal, Casual & conversational, etc.). For a prototype without a template, users need to be asked about the UI type (web app, mobile, dashboard, etc.) — not tone. This was the same `style` key that the SmartPlanner injects when no-template makes UI clarification important.

**Gap 3 — Backend crashes when template_id is None:**
`od_context.py` `load_prototype_context` raised `LookupError` when `template_id` was `None`/`"none"` with no custom body — no graceful no-template path existed.

**Gap 4 — Spec writer doesn't know what to do without a template:**
`prototype-specify/AGENT.md` had mandatory "READ THE TEMPLATE FIRST" rules with no conditional for the no-template case. The agent would fail compliance checks if no template was injected.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/app/workflow/prototype/templates/page.tsx` | Removed `selectedTemplateId` from `canContinue` guard; removed "Pick a template" validation pill | Template is now optional — user can proceed with only a design system and brief |
| `backend/agents/execution_engine/od_context.py` | Added `elif template_id in (None, "", "none")` branch — returns minimal context with `template_body: None, no_template: True` instead of raising LookupError | Backend no longer crashes when no template is selected |
| `backend/agents/execution_engine/clarify_engine.py` | Added `STYLE_BY_PIPELINE` dict with prototype-specific style question ("What visual style and UI type should the prototype follow?" with web/mobile/dashboard options); made `QUESTION_LIBRARY["style"]` use `STYLE_BY_PIPELINE.get(pipeline_type, default)` | Prototype users now see a UI-type question instead of a presentation-tone question |
| `backend/agents/prompts/prototype-specify/AGENT.md` | Added "If NO ACTIVE TEMPLATE is present" conditional section in both MANDATORY READ section and TEMPLATE COMPLIANCE RULES | Spec writer now invents its own CSS class system when no template is provided |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): clarify_engine change uses a local `STYLE_BY_PIPELINE` dict (same pattern as existing `TOPIC_BY_PIPELINE`) — not a kernel branch
- **INV-3** (golden parity): not affected — changes are in wizard, clarifier, and AGENT.md only
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected — AGENT.md + clarify_engine (not kernel) changes only

#### Notes
- `canContinue` still requires a design system — the color tokens are always needed even without a template.
- The `no_template: True` flag in od_context is available for the opendesign provider to use if it needs to skip template injection in agent prompts.
- The STYLE_BY_PIPELINE question fires when `"style"` is in `missing_information` — which the SmartPlanner/clarify engine produces for the `od_prototype`/`prototype` pipeline when the brief doesn't mention visual style. This naturally fires more often when no template pre-selects the style.

### FIX-024 — KAN-82: Content-Unaware Clarification Questions (All Pipelines)

**Date:** 2026-07-01
**Triggered by:** `#velocity-ai-fix KAN-82 — clarify asks fixed irrelevant questions instead of content-aware clarification`

#### Root Cause

Three compounding problems:

**Problem 1 — SmartPlanner returns pipeline-generic missing_information for rich briefs.**
`SmartPlanner._build_prompt()` passed the full brief to the LLM but the prompt's
`common_missing` hint (e.g. `["target_audience", "scope", "style", ...]`) nudged the
model to output the full list regardless of what the brief covered. For long documents
(100+ pages), the brief was not truncated at all — the LLM received the entire document
which often overwhelmed it, causing it to fall back to `common_missing` wholesale.
The prompt also did not strongly enforce "skip if already answered".

**Problem 2 — SmartPlanner did not store the user_request in planning_context.**
The planning_context never contained the original brief, so ClarifyEngine had no way
to read what the user provided when generating questions. There was no `user_request`
key in the returned dict.

**Problem 3 — ClarifyEngine._generate_questions() produced static, content-blind questions.**
For each item in `missing_information`, it looked up `QUESTION_LIBRARY[matched_key]`
and returned the hardcoded question text verbatim — e.g. "Who is the primary audience
for this?" — with zero reference to the user's content, topic, or domain. Whether the
user wrote "build a prototype" or pasted a 100-page hospital-booking user-story
document, the question was identical.

Trace:
```
user submits 100-page doc → SmartPlanner.plan(brief, "user_stories")
→ LLM overwhelmed / nudged by common_missing → returns missing_information=
  ["target_audience","scope","personas","user_journeys","business_rules",
   "compliance_security","priority","technology"]
→ ClarifyEngine._generate_questions(planning_context)
→ "target_audience" → QUESTION_LIBRARY["target_audience"] →
  "Who is the primary audience for this?" (ignores the 100 pages)
→ "scope" → "What is the scope of this project?" (already answered in doc)
→ user sees generic questions unrelated to their content
```

#### Phase Context
- **Phase(s) involved:** Phase 2 (ClarifyEngine) + Phase 4 (SmartPlanner / compiled workflow)
- **Relevant register section:** `specs/001-ai-workflow-os/tasks.md` T017 (ClarifyEngine), T026/T027 (SmartPlanner)
- **Deleted code verified (not resurrected):** The old ReAct tool-loop planner was replaced by SmartPlanner — the fix is within the new system only.
- **Locked decisions respected:** INV-1 (no pipeline_type branches in kernel) — the content-hint personalisation is purely string formatting, no branching. SC-001 — zero engine edits.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/planner/smart_planner.py` | `_build_prompt()`: intelligently truncates long briefs (head 1500 + tail 500 chars with ellipsis notice); strengthened the "only include items GENUINELY absent" rule with concrete examples including "If the brief is a 100-page document, most items may already be covered"; added `user_request_summary` to the JSON output schema | Prevents LLM from being overwhelmed by long content; makes missing_information genuinely content-aware |
| `backend/agents/planner/smart_planner.py` | `plan()`: stores `user_request` (brief, truncated to 3000 chars) in the returned planning_context dict | Gives ClarifyEngine access to the actual brief for personalising questions |
| `backend/agents/planner/smart_planner.py` | `_default_context()`: adds `user_request` key to fallback context | Consistency — fallback path also carries the brief |
| `backend/agents/execution_engine/clarify_engine.py` | `_generate_questions()`: extracts `topic`, `user_request_summary`, `inferred_intent` from planning_context; builds a `content_hint` descriptor; appends `(for: {subject_label})` to non-topic questions when a meaningful content hint is available | Questions now reference the user's actual content rather than being fully generic |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — the content-hint personalisation is pipeline-agnostic string formatting, no branching on pipeline_type name
- **INV-3** (golden parity): not affected — ClarifyEngine and SmartPlanner are not on the golden deliverable path (the 5 characterization goldens use `clarify.mode: skip`)
- **INV-12** (no duplication): reused existing SmartPlanner LLM call; no new agent or module introduced
- **SC-001** (zero engine edits): not affected — all changes are in `smart_planner.py` and `clarify_engine.py` only

#### Verification
Backend restarted cleanly on terminal 53. Changes are in the planner + clarify engine layers,
which are read from disk at runtime. The key behavioral changes are:
1. Long briefs are now intelligently sampled (not fully passed to LLM)
2. SmartPlanner explicitly instructs the LLM to skip items already in the brief
3. Questions include the content topic/intent as context suffix

#### Notes
- The content-aware personalisation is lightweight — it appends `(for: {topic})` to the
  question text rather than generating fully custom question text. A deeper improvement
  would use another LLM call to generate bespoke questions per item, but that would add
  latency and cost. The current approach is a good balance.
- The `user_request_summary` key is new in the planning_context. Downstream agents (spec
  writer etc.) could use it in future for additional context — it is not used yet.
- For very short briefs (< 2500 chars), behaviour is unchanged — the full brief is passed.
### FIX-028 — Prototype Nav-Validation Hardening (render_check + static_check), 5 rounds

**Date:** 2026-07-01
**Triggered by:** a real broken prototype (`imc-inventory-certificate-management.html`, "navigation didn't work properly") that BOTH validators passed green — plus expert review feedback across the arc. Delivered as 5 sequential GSD quick tasks: `260701-bob` → `260701-erg` → `260701-go2` → `260701-hqa` → `260701-kml`. Full per-round detail: those quick-task PLAN/SUMMARY/VERIFICATION files + IMPLEMENTATION-REGISTER **Phase 24**.

#### Root Cause
The two prototype HTML validators mis-judged navigation on three axes:
1. **fail-open (coverage):** `render_check._check_nav` only clicked `.nav-item[href]` → a hash-router/`onclick`/parameterized SPA (zero `.nav-item`) was exercised for ZERO routes → `nav_results=[]` → passed a fully-broken prototype green. `static_check` only inspected `<a href>` + object routes-maps → dynamic (`onclick`/`navigateTo`) dead-links slipped through.
2. **false-positive (no route resolution):** after adding a `expected == first-path-segment` check, correct **alias/parametric** routers were wrongly failed — `#/inventory/4521` legitimately resolves to `inventory-detail`, but first-segment `inventory` ≠ `inventory-detail`. Neither tier resolved a route THROUGH the app's route table. `static_check` also didn't parse array-form route tables (`[{pattern,page}]`), only object literals.
3. **dishonest failure label:** on a blank page, `render_check`'s active-section read `[data-page].is-active` matched the sidebar `<a>` (which carries `data-page` + `is-active`) and returned a nav-link name (e.g. coerced `null`→`'dashboard'`) — misdirecting the fix-loop at a routing-fallback bug when the real defect was "no section activates" (an unscoped `querySelector`). It also spuriously passed the `#/dashboard` route on a blank page.

#### Fix (per round)
- **R1 `260701-bob`:** broadened nav discovery (`a[href^='#']` + `onclick` `location.hash`/`navigateTo`), correct-section assertion + coverage-0 finding; single `render_coverage_status` helper routing the 3 render-availability consumers; per-step `require_render` knob + distinct `validator_skipped` audit.
- **R2 `260701-erg`:** per-route un-dedup, `${…}` exclusion, `nav_settle_ms`; static routes-map RESOLUTION cross-check (router-dead); `require_render: true` on build+revision (revision fails-closed via `gates:[validation]`); golden-harness `deepcopy` pin (also fixed a latent `@lru_cache` shared-mutation of `compile_for_run`).
- **R3 `260701-go2`:** shared `app/agents/route_table.py` (`parse_routes_table` object+array; `resolve_route` exact/alias/`:id`; None for href-valued objects) — BOTH tiers resolve routes through the table (fixes the alias/parametric false-positives), graceful first-segment fallback keeps table-less prototypes + goldens unchanged.
- **R4 `260701-hqa`:** render reads the active page SECTION excluding nav/anchors → `activated=None` on a blank page (no coercion); honest `_dead_nav_line` (blank vs wrong-section); `blank-nav.html` guard.
- **R5 `260701-kml`:** `mis-route.html` fixture + scenario-15 firing the `wrong-section` (`activated != expected`, non-null) render branch end-to-end (TEST-ONLY).

#### Files Changed
`backend/app/agents/render_check.py`, `static_check.py`, `route_table.py` (NEW), `validators/html_render.py`; `backend/agents/execution_engine/engine.py`, `kernel_services.py`; `backend/agents/capabilities/validators/severity.py`, `capabilities/gates/validation.py`, `capabilities/strategies/task_loop.py`; `backend/agents/workflows/{compiler.py,plan.py,prototype/workflow.yaml,prototype_revision/workflow.yaml}`; `backend/app/core/config.py`; `backend/tests/agents/{test_nav_coverage.py,test_route_table.py,_scripted_model.py,test_phase5_fixloop_selection.py,fixtures/imc-…-full.html,fixtures/imc-…-fixed.html,fixtures/blank-nav.html,fixtures/mis-route.html}`.

#### Outcome / Regression floor
Four committed fixtures: **A `-full` must-FAIL** (5 genuine static dead + 17/17 render dead/`None`), **B `-fixed` must-PASS** (0 static, 17/17 render correct incl. aliases/`:id`), **blank-nav** (all `activated=None`), **mis-route** (wrong-section). Verified by direct reproduction + an independent Chromium probe that converged on both real files; targeted suite 191 passing, `lint-imports` 4/0, 4 stable goldens byte/event-identical (NO SNAPSHOT_UPDATE).

**Phase(s) involved:** Phase 07/08 (prototype validators VALID-01/03/04) · IMPLEMENTATION-REGISTER **Phase 24** (post-milestone).
**Invariants:** INV-1/3/12/13 ✅ (additive; no migration; kernel-pure/app→app imports; goldens byte/event-identical). **Status:** Done.
**Known standing item:** `test_characterization_od_ppt` fails offline only (pre-existing skills-asset/event-golden drift, unrelated to the validators) → CI/clean-env re-confirm.

### FIX-039 — OD Gallery Previews: static thumbnail `<img>` with live HTML+JS iframe fallback

**Date:** 2026-07-07
**Triggered by:** user report — "why is it taking lots of time while rendering design template and design on web", plus the follow-up requirement: generate thumbnails at build time and, when a thumbnail is absent, render the iframe (HTML+JS) way.

#### Root Cause
The template gallery (`TemplateGallery.tsx` `CompactTemplateCard`, the larger `TemplateCard.tsx`) and the PPT gallery (`PPTTemplateGallery.tsx` `CompactPPTCard`) rendered each catalog card's preview as a **sandboxed `<iframe sandbox="allow-scripts">`** loading the template's real `example.html`, laid out at a full 1280x720 viewport and CSS-scaled to a ~130px thumbnail. The scale is cheap; the cost is that the browser **parses, styles, lays out, paints, and runs the JS of a complete standalone HTML document per card**, and each iframe re-fetches the preview's fonts/CSS/images. A gallery of N cards renders N full web pages just for thumbnails. (The design-system picker uses text chips, not iframes, so only its one-at-a-time detail modal is heavy.)

#### Fix
Each gallery card now renders a **static `<img loading="lazy" class="object-cover object-top">`** when a pre-rendered thumbnail exists (`has_thumbnail`), turning "render N HTML documents" into "load N cached images". When a thumbnail is absent, the card **falls back to the live `example.html` iframe with `sandbox="allow-scripts"`** (full HTML+JS rendering) — the original behavior — so nothing is lost before/without generation. The `<img>` carries an intentional `eslint-disable-next-line @next/next/no-img-element` (a tiny static same-origin thumbnail; `next/image` optimization + `remotePatterns` would be the very overhead we are removing). Detail modals keep `allow-scripts` for the interactive preview. (An interim iteration made the fallback iframe `sandbox=""` for a further speedup; reverted per the explicit "use iframe html+js" fallback requirement.)

#### Files Changed
`frontend/src/components/workflow/prototype/TemplateGallery.tsx`, `frontend/src/components/workflow/prototype/TemplateCard.tsx`, `frontend/src/components/workflow/ppt/PPTTemplateGallery.tsx`, `frontend/src/lib/prototype-api.ts` (`has_thumbnail` + `getTemplateThumbnailUrl`), `frontend/src/lib/ppt-api.ts` (`has_thumbnail` + `getPPTTemplateThumbnailUrl`).

#### Invariants Verified
- **INV-3** (golden parity): not affected — FE-only; catalog thumbnails, not the deliverable renderer on the golden path.
- **INV-1 / INV-12 / SC-001**: no engine/kernel edits, no pipeline_type branch, no duplication.

#### Verification
`npx tsc --noEmit` exit 0; `eslint` 0 errors (only pre-existing warnings — the img warning is intentionally suppressed); `npm run build` (Next 16) compiled + TypeScript + 15/15 static pages generated; `vitest --run src/components/workflow` = 5 pre-existing failures / 50 passed, identical with the change stashed (the failures — `ReviewGatesSection.test.tsx` et al. — are unrelated). Registers checked first via `Select-String` (grep_search unreliable here): the gallery-thumbnail area is untracked, and the locked T-18-05 sandbox decision governs the deliverable renderer, not these catalog thumbnails.

#### Notes
- Tradeoff: a JS-drawn template (canvas / client-rendered) shows a sparser thumbnail only if no screenshot was generated; the fallback iframe renders it fully, and the detail modal is always live.

#### Follow-up — code-review cleanup (2026-07-08)
- **Misleading comment corrected:** the fast-path comment in all three gallery cards described the fallback as a "(script-free) iframe", but the fallback iframe uses `sandbox="allow-scripts"` (the `sandbox=""` interim was reverted, see above). Reworded to "sandboxed (allow-scripts) iframe" in `TemplateCard.tsx`, `TemplateGallery.tsx`, `PPTTemplateGallery.tsx` so the comment matches the code. Comment-only; no behavior change.
- **`onError` fallback:** the `<img>` → live-iframe degrade-on-404 the reviewer flagged as missing had already landed as **FIX-041** (`thumbnailError` state + `onError` handler); no further change needed here.

---

### FIX-040 — OD Gallery Thumbnails Generated at BUILD Time (backend Docker + Playwright)

**Date:** 2026-07-07
**Triggered by:** same report; the follow-up requirement pinned generation to **build time** (not committed), with the live-iframe fallback (FIX-039).

#### Root Cause
The `<img>` fast-path (FIX-039) needs a pre-rendered screenshot to exist. Those screenshots must be produced somewhere; committing ~106 binaries is undesirable, and the frontend build context (`./frontend`) can neither see `skills/opendesign/` nor ship a browser.

#### Fix
Generate the thumbnails during the **backend image build** — the natural home: the backend runtime stage already runs `playwright install --with-deps chromium` (for `render_check.py`) and bakes the OpenDesign tree at `/app/opendesign`, and the backend already **serves** the thumbnails.
- **Serving** (`od_loader.py`, `prototype_templates.py`, `ppt_templates.py`): `has_thumbnail` on each template dict + `get_template_thumbnail_path()`; `GET /api/{prototype,ppt}/templates/{id}/thumbnail` serves the JPEG (unauthenticated + `Cache-Control: public, max-age=3600`, same containment as `/preview`). `has_thumbnail` is read from disk at loader init, so a baked image reports `true` while a bare local checkout reports `false` → live-iframe fallback.
- **Generator** (`backend/scripts/generate_template_thumbnails.py`, NEW): `playwright.sync_api` serves `design-templates/` via a `ThreadingTCPServer` and screenshots each `example.html` at 1280x720 → `thumbnail.jpg` (JPEG q80). Launches Chromium with `--no-sandbox --disable-dev-shm-usage` (runs as root in the build) with a system Chrome/Edge channel fallback; per-template fresh context, resumable (skips existing), and **always exits 0** so a flaky template can never fail the image build.
- **Dockerfile** (`backend/Dockerfile`): after the OpenDesign COPY + Chromium install and before the USER switch, `COPY` the script and `RUN` it over `/app/opendesign/design-templates`, then `chown -R 10001:10001 /app/opendesign`.
- **Not committed** (`.gitignore`): `skills/opendesign/design-templates/*/thumbnail.jpg` ignored; the earlier committed batch was removed. The redundant frontend Node generator (`generate-template-thumbnails.mjs`) + its `npm run thumbnails` script were deleted — the Python generator is the single source (build-time and local: `cd backend && python scripts/generate_template_thumbnails.py`).

Design systems are out of scope — their picker is text chips, not an iframe grid.

#### Files Changed
`backend/app/services/od_loader.py`, `backend/app/api/prototype_templates.py`, `backend/app/api/ppt_templates.py`, `backend/scripts/generate_template_thumbnails.py` (NEW), `backend/Dockerfile`, `.gitignore`; removed `frontend/scripts/generate-template-thumbnails.mjs` + the `thumbnails` npm script.

#### Invariants Verified
- **INV-3**: additive loader field + build step; not on the deliverable/golden path.
- **Ports & Adapters / lint-imports**: 4 kept / 0 broken (backend changes stay in `app.services`/`app.api`).
- **Persistence**: no migrations; thumbnails are files co-located with the template, generated into the baked tree like `example.html`/`assets/`.
- **INV-1 / INV-12 / SC-001**: no engine/kernel edits; single generator (no dual implementation); no committed binaries.

#### Verification
`python -m py_compile scripts/generate_template_thumbnails.py` exit 0; ran locally `--only audio-jingle` → produced the thumbnail with bundled Chromium and the loader flipped `has_thumbnail=true` with a resolving path (artifact then removed — thumbnails are build outputs). `pytest tests/unit/test_template_assets.py` 18 passed; `lint-imports` 4/0. Frontend build green (see FIX-039). A full backend `docker build` was NOT run here (base-image pulls / apt are network-restricted in this environment); the Dockerfile step is ordered after the existing Chromium install + OpenDesign COPY and is best-effort (always exits 0), so it cannot break the build.

#### Notes
- For user_stories / app_builder / custom pipelines (no od_context): only the "📄 User brief" chip appears — correct.
- For od_prototype: "📄 User brief" + "🎨 Template: web-prototype" + "🎨 Design system: github" chips appear.
- For prototype with image attachment: "📄 User brief" + "🖼 1 image" chips appear (plus template/DS if od_prototype).
- Downstream agents (index > 1) continue to show prior-agent handoff chips unchanged — no regression.
- KAN-103 (prototype revision missing od_context) is a companion issue that this fix exposes more clearly — when prototype revision runs, the revision agent at index=0 will now show "📄 User brief" but NOT template/DS chips (because od_context=None in _handle_revision). KAN-103 remains open.

| FIX-050 | 2026-07-09 | KAN-104: Prototype revision agent AGENT.md restructured for task planning, mandatory design.md read, and incremental execution | AGENT.md "How to work" jumped directly from read_file to edit_file with no analysis, no write_todos planning, no dependency ordering, and optional design.md read — agent processed all changes in a single undifferentiated pass | `backend/agents/prompts/prototype-revision-agent/AGENT.md` | Phase 14 (revision) / KAN-104 | INV-1/3/12/SC-001 ✅ | Done |

---

### FIX-050 — KAN-104: Prototype Revision Agent task planning and mandatory DS awareness

**Date:** 2026-07-09
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-104`

#### Root Cause
`backend/agents/prompts/prototype-revision-agent/AGENT.md` "How to work" section instructed the agent to jump directly from `read_file` to `edit_file` with no prior analysis or planning step. The `write_todos` native tool was technically available (workspace tool set returns `exclude_builtin=False` from `WorkspaceToolProvider.provide()` at `providers.py:74`) but was never referenced in the prompt. Additionally, the `design.md` read was marked "may" (optional), causing the agent to frequently skip template/DS context and invent CSS classes or color values inconsistent with the original design.

#### Phase Context
- **Phase(s) involved:** Phase 14 — run_revision real revision loop
- **Relevant register section:** Phase 14 §5 locked decision: `od_context=None` for revision dispatch; no `template`/`design_system` injects on revision agents (pinned by `test_run_revision_revision_agents_declare_no_template_injects`)
- **Deleted code verified (not resurrected):** No deleted code involved — AGENT.md prompt-only change
- **Locked decisions respected:** YAML frontmatter `injects:` stays empty — NO `template` or `design_system` added. The design context is accessed via `read_file("design.md")` from the sandbox (seeded by `previous_run` provider), which is the correct mechanism and does not require `od_context` injection. The test constraint is fully satisfied.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/prompts/prototype-revision-agent/AGENT.md` | Restructured "Your workspace" section: added `write_todos` to tool list; changed `design.md` from optional "may" to MANDATORY with explicit constraint to use only defined CSS classes/tokens; added `spec.md` usage guidance. Replaced 4-step "How to work" with a 4-phase structured process: Step 1 (mandatory context read including ls + design.md + prototype.html), Step 2 (analyze + write_todos), Step 3 (execute one task at a time with per-task verification), Step 4 (final read + summary). | The agent was skipping design context, conflating all changes into a single pass, and producing inconsistent styles. The new structure forces planning before execution and uses write_todos for dependency-ordered task tracking. |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): Not affected — AGENT.md only
- **INV-3** (golden parity): Not affected — `prototype_revision` is not in any of the 5 characterization goldens
- **INV-12** (no duplication): Not affected — no code changes
- **SC-001** (zero engine edits): Not affected — AGENT.md prompt change only
- **Test constraint**: `test_run_revision_revision_agents_declare_no_template_injects` stays green — `injects:` frontmatter is unchanged (empty list), no `template` or `design_system` inject added

#### Verification
- AGENT.md reads cleanly; YAML frontmatter is byte-identical to HEAD except for the prompt body
- `write_todos` is available to the agent via `workspace` tool set (`exclude_builtin=False`) without any backend changes
- `design.md` is read via `read_file()` from the workspace sandbox (seeded by `previous_run` provider when the parent sandbox is alive within 48h) — no injection mechanism needed
- No backend restart needed — AGENT.md is read at agent dispatch time

#### Notes
- The backend `_compute_root_ids` is intentionally NOT changed — it correctly walks `parent_run_id` ownership for all runs; the family membership decision belongs at the FE display layer (POR D7).
- Multi-hop chains (prototype → user_stories → ppt) all share the original `root_run_id = prototype.id`. After this fix, each chained run in that chain emits as its own standalone entry since each has a different base type from the prototype root.
- Same-type chaining edge case (e.g. prototype → prototype via chain, not revision): both runs have `baseWorkflowType = "prototype"` so they would still group together. This is an acceptable edge case since same-type chaining is rare and the behavior (grouping two prototypes) is not technically wrong. A future enhancement could add a `relationship_type` field to `WorkflowRun` to distinguish chain vs revision at the data layer.

| FIX-053 | 2026-07-13 | KAN-106: Add delete option on individual revision version rows in expanded family list + reset stale version timeline after deletion | Child version rows in FamilyGroupCard rendered as plain `<button>` elements with no RowMenu; `handleDeleteConfirm` never reset `family` state leaving version timeline chips stale after deletion | `frontend/src/components/history/RevisionFamilyView.tsx`, `frontend/src/components/history/WorkflowHistory.tsx` | Phase 25 (B2 revision families) / KAN-106 | INV-1/3/12/SC-001 ✅ | Done |

---

### FIX-053 — KAN-106: Delete option on individual revision version rows

**Date:** 2026-07-13
**Triggered by:** `/velocity-ai-fix KAN-106`

#### Root Cause
Two separate gaps in the revision family UI:

**Gap 1 — No delete affordance on child version rows:**
The expanded child version rows in `FamilyGroupCard` (`RevisionFamilyView.tsx` ~lines 397-420) rendered as plain `<button>` elements with no overflow menu. The `RowMenu` component (which contains the Delete button) was already implemented and available, and the delete props (`openMenuId`, `onToggleMenu`, `onDeleteClick`) were already threaded through `FamilyGroupCard` props — but no `RowMenu` was placed on the child rows. A plain `<button>` can't host an overflow menu inside it (nested interactive elements violate HTML spec), so the child rows needed to be restructured from a flat `<button>` to a `<div class="group relative">` wrapper with a nested clickable area + `RowMenu` at the right edge.

**Gap 2 — Stale version timeline after deletion:**
`handleDeleteConfirm` in `WorkflowHistory.tsx` (~line 264) removed the deleted run from the `runs` local state via `setRuns(prev => prev.filter(...))` and cleared `selectedRun` if it matched. But it never called `setFamily(null)`. If the user had the detail view open showing the deleted run's family, the `VersionTimeline` chips remained stale (showing the now-deleted member) until the user navigated away and back.

#### Phase Context
- **Phase(s) involved:** Phase 25 / Workstream B2 (`260702-uos`) — FamilyGroupCard + VersionTimeline
- **Relevant register section:** Phase 25 §B2 key-decisions: `RowMenu` with delete is threaded through `FamilyGroupCard` props for the root card; Gap 1 extends it to child rows using the same prop threading
- **Deleted code verified (not resurrected):** No deleted code — pure additive change to child row rendering and a one-line state reset
- **Locked decisions respected:** INV-12 — `RowMenu` already exists and is reused; no new component. The `<div>` wrapper + nested `<button>` pattern is the correct HTML for this case (nested interactive elements require the outer element not be a button).

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/history/RevisionFamilyView.tsx` | Converted each expanded child version row from a flat `<button>` to a `<div class="group relative flex items-center">` wrapper containing a flex-1 `<button>` (clickable open-version area) + a `<RowMenu>` at the right edge (`pr-2 flex-shrink-0`) | Flat `<button>` cannot contain another `<button>` (RowMenu renders a button); the div wrapper keeps hover behavior, keyboard accessibility on the open-version button, and adds the hover-reveal delete menu |
| `frontend/src/components/history/WorkflowHistory.tsx` | Added `setFamily(null)` in `handleDeleteConfirm` after the successful delete | The `family` state holds the `/family` API response; after a member is deleted it's stale. Resetting to null triggers the existing `useEffect` keyed on `selectedRun?.rootRunId` to re-fetch the family if the detail view is still open |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — FE-only presentational change
- **INV-3** (golden parity): not affected — no backend/engine/golden changes
- **INV-12** (no duplication): reuses existing `RowMenu` component — no new delete logic
- **SC-001** (zero engine edits): not affected — FE only

#### Verification
- TypeScript diagnostics: 0 errors on both changed files
- Trace Gap 1: expand a multi-revision family → each child row now shows hover-reveal MoreHorizontal button → click → Delete menu → `handleDeleteClick(member.id)` → `setDeleteConfirmId(member.id)` → `DeleteModal` appears → confirm → `handleDeleteConfirm` → `deleteWorkflow(token, member.id)` → run removed from list ✅
- Trace Gap 2: after deletion, `setFamily(null)` → `useEffect` on `selectedRun?.rootRunId` re-fires → `getRunFamily(token, rootRunId)` → fresh family without the deleted member → VersionTimeline shows correct chips ✅
- Backend `DELETE /api/runs/{id}` already correctly handles mid-chain deletion (nulls children's `parent_run_id`) — no backend change needed

#### Notes
- The `<div>` wrapper with nested `<button>` is the correct HTML pattern when a row needs both a full-row clickable area and a secondary control. The outer element must not be a `<button>` when it contains interactive children (HTML spec: interactive content must not be nested inside `<button>`).
- The `setFamily(null)` reset only affects the `family` state variable; the `selectedRun` and its detail content remain visible. The re-fetch is triggered by the existing `useEffect` keyed on `selectedRun?.rootRunId` — if the detail is open, the family refreshes automatically.

| FIX-054 | 2026-07-13 | KAN-107: Strip QA checklist text injected into PPT deck body before first slide + harden validator prompt | od-ppt-validator injects QA results as visible HTML elements inside `<body>` before slides; no backend step removed them; text rendered over first slide in iframe | `backend/agents/capabilities/deliverables/_artifact.py`, `backend/agents/capabilities/deliverables/ppt.py`, `backend/agents/prompts/od-ppt-validator/AGENT.md` | Phase 15 / Phase 7 (ppt deliverable) / KAN-107 | INV-1/3/12/SC-001 ✅ | Done |

---

### FIX-054 — KAN-107: Strip pre-slide QA body text from PPT deck + harden validator output contract

**Date:** 2026-07-13
**Triggered by:** `/velocity-ai-fix KAN-107`

#### Root Cause
The od-ppt-validator (Deck QA Agent) non-deterministically violates its output contract on live Haiku by injecting QA checklist results as visible HTML elements (`<p>`, `<div>`, bullet lines) inside the deck `<body>`, immediately before the `.stage` container or the first `<section class="slide">`. This text renders visibly in the iframe over the first presentation slide.

The existing frontend mitigation (`htmlStart` slice in `PPTPreview.tsx`) only strips text appearing BEFORE `<!DOCTYPE html>` — it cannot remove HTML elements injected inside `<body>` after the doctype. The backend `ppt.py` resolver had no step to strip pre-slide body content, only `sanitize_carousel_deck_html` (which strips carousel-breaking CSS) and `unwrap_artifact`.

This is the third recurrence of validator output leakage (FIX-001 removed the preamble-outside-artifact loophole; FIX-014 replaced `[ ]` checkbox syntax; FIX-054 strips in-body injections that survive both earlier fixes).

The "Invalid presentation output" error (separate path) occurs when the validator emits a QA report with no HTML doctype at all — the frontend `isHtml` check catches it and shows the error UI. The new backend sanitizer also helps here by cleaning the body before the content reaches the frontend.

#### Phase Context
- **Phase(s) involved:** Phase 15 (Live-Pass Prompt Contract Closure) + Phase 7 (ppt deliverable capability)
- **Relevant register section:** Phase 15 §3 — validator output contract hardening (FIX-001/FIX-014 prior fixes); Phase 7 §3 — `_artifact.py` sanitizer pattern (INV-12 move-don't-copy single home)
- **Deleted code verified (not resurrected):** No deleted code involved — new function added following the exact pattern of `sanitize_carousel_deck_html`
- **Locked decisions respected:** INV-12 — new function in `_artifact.py` (the single home for deck sanitizers); no duplication. INV-1 — no pipeline_type branch; `strip_pre_slide_body_text` is a no-op on non-matching input.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/capabilities/deliverables/_artifact.py` | Added `strip_pre_slide_body_text(html)` function that removes any content between `<body>` opening tag and the first slide anchor (`.stage` div or `<section class="slide">`) | Deterministic backstop for validator body text injection; no-op on correct decks |
| `backend/agents/capabilities/deliverables/ppt.py` | Added `strip_pre_slide_body_text` to import and chained it in `resolve()`: `unwrap_artifact(strip_pre_slide_body_text(sanitize_carousel_deck_html(last_streamed)))` | Applies the new sanitizer before the artifact is unwrapped |
| `backend/agents/prompts/od-ppt-validator/AGENT.md` | Added explicit `❌ FORBIDDEN inside <body>` rule forbidding injection of any text/elements before `.stage` or `.slide` sections | Third prompt hardening; makes the body-injection failure mode explicit |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): `strip_pre_slide_body_text` is generic — it checks for `<body>` + slide indicators, never a pipeline_type literal. No-op on non-ppt HTML.
- **INV-3** (golden parity): no golden re-baseline needed — the od_ppt golden was already regenerated in FIX-031. The new sanitizer is a no-op on the characterization fixture (which has no QA text injected in the body). Both backend `.py` changes are capability-layer only (never touched by the harness).
- **INV-12** (no duplication): `strip_pre_slide_body_text` added to `_artifact.py` — the established single home for all deck sanitizers. `ppt.py` imports it from there.
- **SC-001** (zero engine edits): not affected — capability deliverable layer only.

#### Verification
- Backend started cleanly with no import errors
- `strip_pre_slide_body_text` is a no-op when `<body>` immediately precedes `.stage` or `.slide` (correct deck structure)
- For a deck with QA text between `<body>` and the first slide, the text is removed and the deck renders correctly
- The resolver chain now: `sanitize_carousel_deck_html` → `strip_pre_slide_body_text` → `unwrap_artifact`

#### Notes
- This is a defense-in-depth fix. The prompt hardening reduces but does not eliminate LLM non-determinism; the deterministic sanitizer catches what the prompt alone cannot prevent.
- The `strip_pre_slide_body_text` function uses a targeted approach: find `<body>`, find first slide anchor, remove preamble. It does NOT attempt to parse full HTML — intentionally simple and narrow-scoped per the existing sanitizer pattern.
- Follow-up: if the validator continues to produce "Invalid presentation output" errors (no HTML doctype at all), that is a separate failure mode requiring a different fix (the validator emitting a pure QA report with no deck).

---

### FIX-055 — KAN-110 (follow-up): Replace pagination with Load More + improve loading UX

**Date:** 2026-07-16
**Triggered by:** `/velocity-ai-fix KAN-110 — instead of pagination numbering we want load more option on the workflow history page. Also, we want to have some loader showing while the user waits for workflows list to appear.`

#### Root Cause

FIX-051 implemented page-based pagination (Prev / 1 / 2 / 3 / … / Next buttons). The requirement is a simpler append-based "Load More" button. Additionally, a loading skeleton was already rendered during the initial fetch (7 skeleton cards + spinner + "Loading workflows" text) — this part was already correct. The pagination state (`currentPage`, `handleGoToPage`) and the pagination footer (numbered page buttons) needed to be replaced with Load More semantics.

Trace:
```
User opens Workflow History
  → useEffect fires with currentPage dep → replaces runs array (page-flip behaviour)
  → Pagination footer shows numeric Prev/1/2/3/Next buttons — NOT the desired UX
  
Wanted:
  → Initial load replaces runs (stays the same)
  → "Load More" button appends offset: runs.length to the existing list
  → loadingMore spinner in button during the secondary fetch
```

#### Phase Context
- **Phase(s) involved:** FIX-051 (KAN-110) / Frontend-only
- **Relevant register section:** FIX-051 detailed entry above
- **Deleted code verified (not resurrected):** `currentPage` state and `handleGoToPage` removed; no previously-deleted code resurrected
- **Locked decisions respected:** Backend API contract (`limit`/`offset` + `X-Total-Count`) unchanged; `getWorkflows` return type unchanged

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/history/WorkflowHistory.tsx` | Removed `currentPage` state; replaced with `loadingMore: boolean`. Changed useEffect to always fetch `offset: 0` on mount/filterType change (replaces list). Added `handleLoadMore` callback that fetches `offset: runs.length` and appends. Removed page-based pagination footer; added "Load more / Loading… (spinner)" button shown only when `runs.length < totalRuns && !loading`. | Implements append-based Load More UX instead of page-flip pagination |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — pure FE component change.
- **INV-3** (golden parity): not affected — no agent or engine code changed.
- **INV-12** (no duplication): not applicable — FE-only.
- **SC-001** (zero engine edits): not affected — zero engine edits.

#### Verification
- No TypeScript diagnostics on the changed file.
- State simplification: `currentPage` removed, `loadingMore` added — no other components referenced `currentPage`.
- Backend API unchanged — `getWorkflows(token, { limit, offset })` signature identical.
- The existing skeleton loading state (7 cards + spinner + "Loading workflows" text) continues to show during the initial `loading=true` state.
- `Load more` button appears only when `runs.length < totalRuns && !loading`; shows `Loader2` spinner when `loadingMore=true`.
- Filter tab change resets the list to offset 0 (same as before).

#### Notes
- The `loadingMore` button spinner provides visual feedback during the secondary fetch without hiding the already-loaded runs.
- The existing skeleton is sufficient for the initial load UX requirement — no additional change was needed there.
- If a filter tab is active while runs are loaded with Load More, the `matchesFilter` client-side filter already handles type filtering across all loaded runs.

---

### FIX-056 — KAN-112: Custom Workflow — fix empty agent seed + blank-slate UX

**Date:** 2026-07-16
**Triggered by:** `/velocity-ai-fix KAN-112 — implement all requirements`

#### Root Cause

`IdeaInputPage.tsx` had four places that derived default agents for the custom workflow using `LIBRARY_AGENTS.filter((a) => a.pipeline_type === effectiveType)`. For `effectiveType === "custom"` this always returned `[]` because custom agents live in the separate `CUSTOM_AGENTS` export — `LIBRARY_AGENTS` has no entries with `pipeline_type: "custom"`. This caused:

1. **Initial state seed** (`useState` initialiser): `pipelineAgents = []` → Run button disabled with "Add agents first"
2. **useEffect re-derive**: same filter — clobbered state back to `[]` on type change
3. **`defaultAgentIds` set**: empty → all 8 custom agents counted as "optional" → immediately hit the `maxOptional=8` cap; user could add 0 extra agents
4. **`handleAddAgent` limit check**: same filter in the closure → optional count logic broken

Additionally the `TYPE_CONFIG["custom"]` copy and `workflow.yaml` catalog metadata described generic assembly rather than the open-ended AI-driven vision.

#### Phase Context
- **Phase(s) involved:** Phase 22 (ISS-014 — agent-composer live), Phase 20 (catalog metadata)
- **Relevant register section:** `_register-parts/22-capability-surfacing…` §3 (ISS-014); Phase 20 §3 (WF-DB-01 catalog)
- **Deleted code verified (not resurrected):** `CUSTOM_AGENTS` was already exported — no deleted code resurrected
- **Locked decisions respected:** INV-12 — reused existing `CUSTOM_AGENTS` export, no new list created; SC-001 — no engine edits; workflow.yaml change is pure inert catalog metadata

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/workflow/IdeaInputPage.tsx` | Import `CUSTOM_AGENTS`; fix initial state seed to use `CUSTOM_AGENTS` for custom type; fix `useEffect` re-derive; fix `defaultAgentIds`; fix `handleAddAgent` closure | Ensures 8 default agents are pre-loaded; Run button enabled; add/remove limits correct |
| `frontend/src/components/workflow/IdeaInputPage.tsx` | Update `TYPE_CONFIG["custom"]` — new heading "What do you want to achieve?", new subtitle communicating AI-driven orchestration | Blank-slate UX framing per KAN-112 AC |
| `backend/agents/workflows/custom/workflow.yaml` | Update `display_name` and `description` catalog fields | Catalog tile communicates open-ended AI-driven workflow creation |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — pure FE component + inert YAML metadata
- **INV-3** (golden parity): not affected — no agent, engine, or golden changes
- **INV-12** (no duplication): verified — reused existing `CUSTOM_AGENTS` export from `AgentLibraryData.ts`; not duplicated
- **SC-001** (zero engine edits): not affected — zero engine edits; workflow.yaml change is catalog metadata only

#### Verification
- TypeScript diagnostics on `IdeaInputPage.tsx`: no errors
- Trace: fresh custom workflow open → `effectiveType === "custom"` → `CUSTOM_AGENTS.sort()` → `pipelineAgents = [8 agents]` → `pipelineAgents.length === 8 > 0` → Run button enabled
- `defaultAgentIds` now contains all 8 CUSTOM_AGENTS ids → `optionalAgentCount = 0` → `canAddMore = true` → user can add up to 8 extra agents from other pipelines
- Saved custom workflow reopen path unchanged: `initialAgentIds?.length` guard fires first, seed from `ALL_LIBRARY_AGENTS` (includes CUSTOM_AGENTS) — no regression
- All other pipeline types (user_stories, ppt, prototype, app_builder, migration variants) use the original `LIBRARY_AGENTS.filter` path — no regression

#### Notes
- HTML prototype output via custom workflow (a separate future capability) is out of scope for this fix per KAN-112 acceptance criteria; tracked as a follow-up in KAN-112 description
- AI-driven recommendation endpoint is also a follow-up item — the Smart Planner + Clarification Questions already provide contextual gathering; the active recommendation-before-run feature would be a separate backend endpoint

---

### FIX-093 — Remove Duplicate Outer Timeline Dot from StartingPointCard

**Date:** 2026-07-22
**Triggered by:** `#velocity-ai-fix starting point shows 2 similar icons, remove outer icon, align it to same clarifying question block`

#### Root Cause
`StartingPointCard.tsx` used a `relative pl-8` outer wrapper with an **absolute-positioned navy filled circle + FileText icon** (the "timeline dot") at `absolute left-0 top-3`. The card's `<button>` header ALSO had its own `w-7 h-7 rounded-lg bg-[#E8EDF5]` icon div with a second FileText icon. This produced two near-identical document icons side-by-side in the UI — one on the left margin (the outer dot) and one inside the card header button.

The `ClarificationsCard` (the correct reference design the user pointed to) renders as a flat `rounded-[12px] border` card with **no outer timeline dot at all** — no `relative pl-8` wrapper, no absolute-positioned element.

Trace: `StepsOverviewSpine.tsx topSlot → StartingPointCard → return (<div className="relative pl-8"> → <div className="absolute left-0 top-3">` [OUTER NAVY CIRCLE + FileText] → `<div className="rounded-xl border"> <button> <div className="w-7 h-7 rounded-lg bg-[#E8EDF5]">` [INNER FileText]) → two icons rendered.

#### Phase Context
- **Phase(s) involved:** Phase 25 (Workstream C2 — StartingPointCard) / Phase 42 (run-screen state fidelity)
- **Relevant register section:** Phase 25 §3 (C2 StartingPointCard)
- **Deleted code verified (not resurrected):** The outer timeline dot was a pattern cloned from PlannerCard (AgentThinkingTab.tsx). Removing it does not resurrect any Phase-deleted code.
- **Locked decisions respected:** SC-001 — card variant still chosen by parsed shape (revisionInstruction/chainContext), never a workflow-name string.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/results/StartingPointCard.tsx` | Removed the outer `<div className="relative pl-8">` wrapper and the absolute-positioned timeline dot `<div className="absolute left-0 top-3 ...">` (navy circle + FileText + connector rail). Card now renders as a flat `<div className="rounded-xl border overflow-hidden border-gray-100">` — matching the ClarificationsCard flat-card style. | Two redundant icons side-by-side; the inner card button already has its own FileText icon in an `E8EDF5` rounded square — that's the correct single icon to keep. |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — FE-only, no engine changes
- **INV-3** (golden parity): not affected — FE-only component, no characterization golden touches
- **INV-12** (no duplication): not applicable — removing redundant code
- **SC-001** (zero engine edits for new workflows): not affected

#### Verification
- `get_diagnostics` on the file → **No diagnostics found** (TypeScript valid)
- Mentally traced: the `return` now opens a single flat `<div className="rounded-xl ...">`, contains the `<button>` header (with the single inline `E8EDF5` icon), the `{expanded && ...}` body, and a single closing `</div>`. JSX nesting is correct with no extra close tags.
- Committed: `[ui-2-bug-fixes 1a99e264]`

#### Notes
- The inner card-header icon (`w-7 h-7 rounded-lg bg-[#E8EDF5]`) is KEPT — it's the correct visual that matches the mock design.
- All card body content (revision variant, chained variant, attachments, ND-10 image placeholder) is completely untouched.
- The removed `pl-8` + absolute dot was originally cloned from the PlannerCard timeline pattern but is inappropriate here since StartingPointCard renders alongside (not inside) the PlannerCard timeline — the double icon was always wrong in this context.

---

### FIX-094 — Recommended Answers + Skip All in Clarify Questions (KAN-117)

**Date:** 2026-07-22
**Triggered by:** `#velocity-ai-fix clarify questions missing skip option and recommended answers`

#### Root Cause
`InlineClarifyActions.tsx` had the `ClarifyQuestion` type fields `recommendedAnswer`, `recommendedDisplay`, and `impactLevel` available (defined in `types/index.ts`) but never read or rendered them. This was an intentional Phase 42-06 omission (comment in the file: "the per-question skip toggle, the recommended-answer fill/badge … are intentionally omitted"). The user now wants these features — reversing that decision.

Two specific gaps:
1. **No skip affordance** — questions with no selection are silently dropped on submit, but there was no visible "Skip & continue" button so users believed all questions were mandatory.
2. **No recommended answers** — the backend sends `recommendedAnswer`/`recommendedDisplay` per question but the UI never showed them.

#### Phase Context
- **Phase(s) involved:** Phase 31 (CHATUI-01) / Phase 42-06 (intentional omission)
- **Deleted code verified (not resurrected):** No. This adds back UI features that were intentionally deferred, not deleted engine logic.
- **Locked decisions respected:** SC-001 — generic question ids only, no workflow/agent-name literals. INV-12 — reused the existing `onSubmitAnswers` channel, no second submit path.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/chat/InlineClarifyActions.tsx` | Added: (1) recommended-answer hint row per question with one-click "Use recommended" button; (2) `★` marker on the recommended chip option; (3) `impactLevel === "high"` → amber "High impact" badge on the question label; (4) "Skip questions & start the build" secondary button (shown only when not all questions answered); (5) dynamic submit label counting answered questions. | Surfaces server-supplied recommendations to users and makes it clear that answering is optional. |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — FE-only
- **INV-3** (golden parity): not affected — FE-only, no characterization goldens
- **INV-12** (no duplication): verified — reused the SAME `onSubmitAnswers` callback for both submit and skip-all; one channel, two buttons
- **SC-001** (zero engine edits): not affected

#### Verification
- `get_diagnostics` → No diagnostics found (TypeScript valid)
- Traced: both "Submit" and "Skip" call `onSubmitAnswers(buildResponses())` which collects only questions with `answers[q.id]?.length > 0`. Unanswered questions are omitted exactly as before — the backend already handles partial submissions with its defaults.
- Committed: `[ui-2-bug-fixes 581f0ceb]`

#### Notes
- The "Skip questions & start the build" button is **only shown** when `answeredCount < questions.length` — if the user answers all questions it disappears (no redundant UI).
- The recommended-answer hint row hides itself once the user selects any option for that question (clean, non-cluttering).
- The `★` marker on the recommended chip makes the option discoverable even without the hint row.
- The submit button label adapts: "Submit 2 answers & start the build" vs the generic fallback when 0 are answered.

---

### FIX-095 — Fix .split crash + multi-select chip highlighting for recommended answers

**Date:** 2026-07-22
**Triggered by:** `#velocity-ai-fix .split is not a function crash in InlineClarifyActions + chips not highlighting after Use recommended`

#### Root Cause
Two compounding bugs introduced by FIX-094:

**Bug 1 — `.split is not a function` (the crash):**
`recommendedAnswer` and `recommendedDisplay` on `ClarifyQuestion` are typed as `string | undefined` but the backend can send a non-string value (e.g. an array `["option A", "option B"]` or a number). All three `.split()` call sites in FIX-094 operated directly on the raw value without coercing it to a string first. When the API returned an array, `[].split` is undefined → `TypeError: .split is not a function`.

**Bug 2 — chips not highlighting (the visual issue from the screenshot):**
For multi-select questions the backend's `recommendedAnswer` is often a comma-separated string `"Core definitions..., Agent reasoning..."`. `useRecommended` stored this entire string as `answers[q.id] = [rec]` — a single array element equal to the whole sentence. The chip highlight check `selected.includes(option)` compares against individual chip option strings, none of which equal the whole comma-joined string. So no chip ever turned blue even though "✓ Using recommended answer" appeared (because `recIsSelected` was comparing the raw string too, finding it matched).

#### Phase Context
- **Phase(s) involved:** Phase 31/42 (CHATUI-01 / InlineClarifyActions)
- **Deleted code verified (not resurrected):** Yes — no phase-deleted code resurrected.
- **Locked decisions respected:** SC-001 — generic question ids only; INV-12 — reused existing `onSubmitAnswers` channel, no duplication.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/chat/InlineClarifyActions.tsx` | Added `toRecString(val)` helper — coerces any API value (array, number, string, null) to a plain string; array→`.join(", ")`, others→`String()`. Added `splitRecToChips(rec, options)` helper — splits the coerced string on `/,\s*/`, keeps only tokens that exactly match a chip option, falls back to the whole string if no match. All three former `.split()` call sites now go through these helpers. `useRecommended` now calls `splitRecToChips` for multi-select so individual chip strings get stored, making `selected.includes(option)` work correctly. `recTokens` computed once per question via `splitRecToChips` and reused for `recIsSelected`, `isRec`, and `useRecommended`. | Eliminates the crash and makes multi-select chips highlight correctly after "Use recommended". |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — FE-only
- **INV-3** (golden parity): not affected — FE-only, no characterization goldens
- **INV-12** (no duplication): verified — same `onSubmitAnswers` callback, no new channel
- **SC-001** (zero engine edits): not affected

#### Verification
- `get_diagnostics` → No diagnostics found (TypeScript valid)
- `toRecString` handles: `null` → `""`, `["a", "b"]` → `"a, b"`, `42` → `"42"`, `"str"` → `"str"`
- `splitRecToChips("Core definitions..., Agent reasoning...", options)` returns the two matching chip strings; each lands in `answers[q.id]`; `selected.includes("Core definitions...")` is now true; chip turns blue.
- The crash path is gone: even if the API sends an array, `toRecString` converts it before any `.split`.

#### Notes
- Both helpers are pure module-level functions (no side effects) — easy to unit test.
- `useMemo` import added in FIX-094 was unused; removed in this rewrite.
- The `unused import` lint warning for `useMemo` is also resolved in this fix.

---

### FIX-096 — Hide Back/Next nav in PPT wizard when only template step shown

**Date:** 2026-07-22
**Triggered by:** `#velocity-ai-fix remove showing back and next option in ppt, as we just have template selection`

#### Root Cause
`WizardStepper.tsx` rendered the Back/Next navigation row unconditionally at the bottom of the component, regardless of how many steps were passed. FIX-065 already correctly passed `steps={["template"]}` for PPT mode (a single step), but the nav row still rendered — both buttons were disabled (`activeStep === 0 === lastStep`) but still visible as greyed-out buttons.

#### Phase Context
- **Phase(s) involved:** Phase 37/41 (B3/B7 — WizardStepper, FIX-065)
- **Relevant register section:** Phase 37 §3 (LaunchWizard / WizardStepper)
- **Deleted code verified (not resurrected):** Yes — no phase-deleted code resurrected. This is a cosmetic guard.
- **Locked decisions respected:** SC-001 — no workflow-name literal; the guard keys on `steps.length`, a generic count.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/workflow/WizardStepper.tsx` | Wrapped the Back/Next `<div>` in `{steps.length > 1 && (...)}` | When only one step is shown, navigation between steps is meaningless. |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — FE-only
- **INV-3** (golden parity): not affected — FE-only, no characterization goldens
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected

#### Verification
- `get_diagnostics` → No diagnostics found (TypeScript valid)
- Trace: PPT wizard renders `<WizardStepper steps={["template"]} .../>` → `steps.length === 1` → nav row not rendered → Back/Next buttons gone.
- Prototype mode passes `steps={["template", "design-system", "discovery"]}` → `steps.length === 3` → nav row renders as before (no regression).

#### Notes
- The `steps` prop was added by FIX-065 specifically to let PPT mode skip DS + Discovery; this fix completes that work by also hiding the now-useless nav.

---

### FIX-098 — Remove dashboard home flicker (KAN-118)

**Date:** 2026-07-22
**Triggered by:** `#velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-118`

#### Root Cause
Four compounding causes made the home dashboard content appear in staggered waves:

1. **Per-card stagger** — `motion.div` on each card with `delay: 0.06 + idx * 0.05` caused 6 cards to paint one-by-one over ~310ms.
2. **Header slide-up** — `motion.div` on the h1+eyebrow with `initial={{ opacity: 0, y: 16 }} transition={{ duration: 0.4 }}` made the header animate before the cards.
3. **`AnimatePresence mode="wait"`** — every navigation TO home waited for the prior view's full exit animation (~200ms blank) before home could enter.
4. (Note: the recents late-pop from the separate `getWorkflows` fetch is not fixed here — that would require prop-threading from page.tsx and is out of scope for this change.)

#### Phase Context
- **Phase(s) involved:** Phase 38 §3 (analytics fetch / HomeLaunchGrid SC-2), Phase 40 (HomeLaunchGrid motion cards), Phase 35 (DashboardLayout AnimatePresence)
- **Deleted code verified (not resurrected):** Yes — no phase-deleted code resurrected. These are cosmetic presentation-layer changes.
- **Locked decisions respected:** SC-001/INV-1 — no workflow-name literal added; the changes are purely animation/transition layer. ND-D (live data) untouched.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/catalog/HomeLaunchGrid.tsx` | Replaced `<motion.div initial={{ opacity: 0, y: 16 }} ...>` header wrapper with plain `<div>` | Removes the 400ms header slide-up that preceded card rendering |
| `frontend/src/components/catalog/HomeLaunchGrid.tsx` | Replaced per-card `<motion.div initial={{ opacity: 0, y: 8 }} transition={{ delay: 0.06 + idx * 0.05 }}>` with plain `<div>` | Removes the 60–310ms staggered card cascade |
| `frontend/src/components/catalog/HomeLaunchGrid.tsx` | Removed `import { motion } from "motion/react"` | No longer used after above two changes; avoids lint warning |
| `frontend/src/components/layout/DashboardLayout.tsx` | Changed `AnimatePresence mode="wait"` → `mode="sync"` | `mode="wait"` held a ~200ms blank while the prior view exited; `sync` allows the new view to enter immediately |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — FE presentation-layer only
- **INV-3** (golden parity): not affected — FE-only, no characterization goldens
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected

#### Verification
- `get_diagnostics` on both files → No diagnostics found
- Traced: after fix, the home view (mainView==="home") now enters immediately via `mode="sync"` with a plain `opacity 0→1` (duration: 0.2 from the outer `motion.div key="home"`). Inside HomeLaunchGrid all cards render immediately as plain `<div>`s — no per-element delay. The h1 renders instantly as a plain `<div>`.
- The `mode="sync"` change affects ALL views in DashboardLayout. All other views (library/history/settings/execution etc.) use the same `motion.div` enter/exit pattern — `sync` means their transitions overlap slightly which is the standard expected UX, not worse than before.

#### Notes
- The **recents late-pop** (4th cause from KAN-118) is NOT fixed here. Fixing it requires either (a) passing `recentRuns` from page.tsx as a prop instead of having HomeLaunchGrid fetch its own copy, or (b) pre-caching. That is a larger structural change tracked in KAN-118 as an open question.
- The `getAnalyticsSummary` fetch still fires but is now a no-op for display (FIX-097 removed the minutes display). It could be removed entirely but that is separate cleanup.

---

### FIX-105 — KAN-120: "Run Again" resumes cancelled pipeline from stopped step

**Date:** 2026-07-23
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-120`

#### Root Cause
Four independent gaps across the stack:

1. **`backend/app/api/run_commands.py:~378`** — eligibility check `wr.status != "failed"` rejected cancelled runs with 409. A stopped run has `status="cancelled"`.
2. **Same file, state machine** — when a run is cancelled then resumed in the **same process session**, the in-memory `StateMachine._states` dict has `"cancelled"` locked as terminal. `_execute_impl` subsequently calls `self._state_machine.transition(run_id, "generating")` which raises `StateMachineError: Cannot transition from terminal state 'cancelled'`. For failed runs resumed after a **restart** this never occurs (new process = empty dict), so it was never caught before.
3. **`frontend/src/lib/api.ts`** — no `postResume()` function existed; the FE had no way to call the endpoint.
4. **`frontend/src/components/layout/DashboardLayout.tsx:1796`** — `onRelaunch={handleGoHome}` navigated home; no resume call.
5. **`frontend/src/components/chat/RunChatLane.tsx:~1335`** — button "New Pipeline", text "Nothing further will happen." — misleading.

#### Phase Context
- **Phase(s) involved:** Phase 50 (RESUME-18 endpoint), Phase 44 (LOCK-B REST+SSE), Phase 31/32 (RunChatLane terminal cards)
- **Deleted code verified (not resurrected):** None
- **Locked decisions respected:** LOCK-B — REST up-channel + `runConnection.attachRun` (same as `postRevision`). INV-12 — `postResume` follows `postCancel` exactly, no duplication. SC-001/INV-1 — `handleResumeRun` keys only on generic run ids, zero workflow-name literal.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/app/api/run_commands.py` | Eligibility: `!= "failed"` → `not in {"failed", "cancelled"}`; added step 6b to pop the in-memory state machine entry before resume drive | Accept cancelled runs; prevent same-session terminal-state guard from blocking the transition to "generating" |
| `frontend/src/lib/api.ts` | Added `postResume(token, runId)` following exact `postCancel` pattern | No client function existed |
| `frontend/src/components/layout/DashboardLayout.tsx` | Added `postResume` import; added `handleResumeRun` callback (captures `pipelineState.pipelineRunId` BEFORE state mutation, calls `postResume`, attaches SSE on success, falls back to `handleGoHome` on error — does NOT call `onResetPipeline` before POST); replaced `onRelaunch={handleGoHome}` with `onRelaunch={handleResumeRun}` | Was navigating home; now resumes + attaches SSE stream |
| `frontend/src/components/chat/RunChatLane.tsx` | Button: `"New Pipeline"` → `"Run Again"`; text: `"Nothing further will happen."` → `"Click Run Again to resume from where it left off."` | User-visible fix matching acceptance criteria |

#### Invariants Verified
- **INV-1**: no `pipeline_type` branch — `handleResumeRun` keys only on run id props
- **INV-3**: no engine/golden change; backend edit is app-layer eligibility + in-memory dict pop
- **INV-12**: `postResume` is a single function; `handleResumeRun` reuses `runConnection.attachRun` seam
- **SC-001**: zero engine edit; the existing Phase 45–49 resume tier handles everything

#### Verification
- Backend: `wr.status not in {"failed", "cancelled"}` — cancelled run passes; `_state_machine._states.pop(run_id, None)` clears the terminal guard before drive
- Frontend: `handleResumeRun` captures `pipelineState?.pipelineRunId` (which survives `pipeline_cancelled` — the hook keeps it via `...prev` spread), calls `postResume`, then `runConnection.attachRun(run_id)` → SSE stream re-attaches → `pipelineState.isRunning` becomes `true` → `runLaneState` flips to `"building"` naturally
- No TypeScript diagnostics on all three changed FE files

#### Notes
- `onResetPipeline()` must NOT be called before `postResume()` — it calls `setPipelineState(INITIAL_STATE)` which wipes `pipelineRunId` and flips `runLaneState` back to `"idle"`, making the UI appear to do nothing. The SSE stream drives state machine forward on its own.
- The state machine pop is safe: DB status is already `"running"` (step 5) when the pop happens; the in-memory entry is an intra-process mirror written by the same process when it cancelled — clearing it is ownership-safe.

---

### FIX-110 — KAN-121: Custom workflow prototype agents show validator QA text

**Date:** 2026-07-24
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-121`

#### Root Cause
`frontend/src/components/workflow/IdeaInputPage.tsx` — `AGENT_DELIVERABLE_MAP` prototype entry (line 419) listed only 3 of 5 prototype pipeline agent IDs as triggers:

```
agents: ["prototype-build", "prototype-specify", "prototype-plan"]
```

`resolveDispatchType()` iterates the map and fires the first entry whose `agents` list shares any ID with the user's selected agent set (`keys.some(id => ids.has(id))`). When a user selected a composition containing `prototype-analyze` or `prototype-validate` but NOT `prototype-build`/`prototype-specify`/`prototype-plan`, the check failed to match and fell through to the default fallback:

```
{ strategy: "streamed_text", name: "output.md", mimetype: "text/markdown" }
```

This default was injected as `__deliverable__` into the run's `selections` map. The engine's `_apply_selections` applied it, setting `compiled.deliverable = streamed_text/output.md`. The `StreamedTextResolver` then resolved `ectx.last_streamed` — the `prototype-validate` agent's QA checklist text (the last agent to run) — as the final deliverable. The FE received `deliverable_filename="output.md"` and rendered the QA text via `MarkdownPreview` in the Preview panel.

This was a **port regression**: the fix was present on another branch (commit `6685906b`, FIX-059/FIX-060) with all 5 agents listed, but when the new UI branch (`feat/ui-2`) was built the prototype entry was recreated with only 3 agents.

#### Phase Context
- **Phase(s) involved:** Phase 22 (EMP-01/02 — `__deliverable__` runtime override, KAN-112 Option B)
- **Relevant register section:** Phase 22 §3 (`__deliverable__` selections key, `AGENT_DELIVERABLE_MAP`)
- **Deleted code verified (not resurrected):** No deleted code — extending an existing map entry only
- **Locked decisions respected:** SC-001 — fix uses agent IDs (never workflow/pipeline-type names); INV-12 — extends the existing map, no second mechanism introduced

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/workflow/IdeaInputPage.tsx` | Added `"prototype-analyze"` and `"prototype-validate"` to the prototype entry's `agents` trigger list | Ensures the `__deliverable__` override fires for ANY prototype agent combination, matching what FIX-059 had on the other branch |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): Not affected — FE-only change, no engine code touched
- **INV-3** (golden parity): Not affected — FE-only change, no backend/engine/golden impact
- **INV-12** (no duplication): Verified — extended the existing `AGENT_DELIVERABLE_MAP` entry, no second override mechanism added
- **SC-001** (zero engine edits for new workflows): Not affected — zero engine edits; the `__deliverable__` mechanism already exists

#### Verification
- `AGENT_DELIVERABLE_MAP` prototype entry now lists all 5 agents: `prototype-build`, `prototype-specify`, `prototype-plan`, `prototype-analyze`, `prototype-validate`
- `resolveDispatchType()` first-match loop hits the prototype entry for ANY prototype agent → `deliverableOverride = { strategy: "single_file", name: "prototype.html", mimetype: "text/html" }`
- Engine `_apply_selections` (engine.py:6464) reads `__deliverable__` and calls `DeliverableSpec(strategy="single_file", name="prototype.html", mimetype="text/html")` + forces `clarify.mode="skip"`
- `SingleFileResolver.resolve()` reads `prototype.html` from the sandbox (written by `prototype-build`)
- `pipeline_complete` event carries `deliverable_filename="prototype.html"`, `deliverable_mimetype="text/html"`
- FE `page.tsx` routes to `setGenericDeliverable({mimetype:"text/html", filename:"prototype.html", content:<html>})`
- `GenericDeliverablePreview` → `text/html` branch → sandboxed iframe renders the prototype ✅
- Non-prototype custom runs: no prototype agent ID present → check still falls through to `streamed_text` default ✅

#### Notes
- The `COMPANION_GROUPS` definition already correctly listed all 5 prototype agents — the mismatch was only in `AGENT_DELIVERABLE_MAP`. A future agent adding new prototype steps should update BOTH lists.
- The `resolveDispatchType` function is first-match: if somehow agents from multiple pipeline families are mixed, only the first matching entry fires. This is intentional existing behaviour, not changed.

---

### FIX-111 — KAN-121 follow-up: custom prototype-build must use task_loop strategy

**Date:** 2026-07-24
**Triggered by:** `/velocity-ai-fix all workflows should generate correct output using custom workflow`

#### Root Cause

FIX-110 was necessary but not sufficient. It fixed the `AGENT_DELIVERABLE_MAP` trigger list so `__deliverable__ = {strategy:"single_file", name:"prototype.html"}` is correctly injected into selections. But `_apply_selections` (engine.py:6464) only patches `compiled.deliverable` — the top-level resolver config. It does NOT patch the **per-step execution strategy**.

The `custom/workflow.yaml` manifest declares `strategy: single_shot` for ALL steps, including `prototype-build`. The `single_shot` strategy runs the agent once and reads from `ctx.last_streamed` — it **never writes any file to the RunSandbox**. So `SingleFileResolver.resolve()` calls `runner.sandbox.read("prototype.html")` → returns `""` → falls back to `last_streamed` (the last agent's streamed output, which is `prototype-validate`'s QA checklist).

The `task_loop` strategy is the **only** strategy that:
1. Parses the task plan into individual tasks
2. Calls `runner.persist_task_html()` after each task, which writes `prototype.html` to the sandbox
3. Produces a file that `SingleFileResolver` can find

The `_apply_selections` function already has a `sel.get("strategy")` overlay path (engine.py:6442) for fan-out support. This same mechanism can inject `strategy: "task_loop"` on `prototype-build` from the FE selections — no new engine code needed.

#### Phase Context
- **Phase(s) involved:** Phase 22 (KAN-112 Option B custom composer), Phase 7 (task_loop strategy)
- **Relevant register section:** Phase 22 §3 (EMP-01/02), Phase 7 §3 (task_loop strategy)
- **Deleted code verified (not resurrected):** No deleted code — using existing `sel.get("strategy")` overlay path
- **Locked decisions respected:** SC-001 — no engine edits; INV-12 — reuses existing `_apply_selections` mechanism; INV-1 — keyed on agent ID not pipeline_type

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/workflow/IdeaInputPage.tsx` | When `deliverableOverride.name === "prototype.html"` AND `prototype-build` is in the agent list, inject `"prototype-build": { strategy: "task_loop" }` into `mergedSelections` alongside `__deliverable__` | Ensures `_apply_selections` patches the prototype-build step strategy to `task_loop` so it writes `prototype.html` to the RunSandbox |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): Not affected — keyed on `deliverableOverride.name === "prototype.html"` (a data value) and agent ID presence, never a `pipeline_type` string
- **INV-3** (golden parity): Not affected — FE-only change; no backend/engine/golden impact; non-prototype runs take the `prototypeStepOverrides = {}` path (byte-identical)
- **INV-12** (no duplication): Verified — reuses the existing `sel.get("strategy")` overlay in `_apply_selections`; no second strategy-injection mechanism
- **SC-001** (zero engine edits for new workflows): Not affected — zero engine edits; the mechanism was already there for fan-out (Phase 51)

#### Verification
- When prototype agents selected with `prototype-build`: `mergedSelections` contains `{ "prototype-build": { strategy: "task_loop" }, __deliverable__: { strategy: "single_file", name: "prototype.html", mimetype: "text/html" } }`
- `_apply_selections` processes `"prototype-build"` entry: `sel.get("strategy") → "task_loop"`, `user_step.strategy → "task_loop"` (from synthesized manifest) → `patch["strategy"] = "task_loop"`
- `prototype-build` step runs with `task_loop` strategy → `persist_task_html()` writes `prototype.html` to sandbox
- `SingleFileResolver.resolve()` → `sandbox.read("prototype.html")` → returns HTML → correct deliverable ✅
- PPT runs unaffected: `deliverableOverride.name === "presentation.html"` → condition false → `prototypeStepOverrides = {}` ✅
- User story runs unaffected: `strategy: "streamed_text"` → `deliverableOverride.name !== "prototype.html"` → `prototypeStepOverrides = {}` ✅
- Non-prototype custom runs unaffected: no `deliverableOverride` → `mergedSelections = selections` (original, unchanged) ✅

#### Notes
- If `prototype-build` is NOT in the selected agents (e.g. user only adds specify/plan/analyze/validate), `prototypeStepOverrides` is `{}` and `prototype.html` will still not be written. This is expected — the build step is required to produce the HTML file. The `AGENT_DELIVERABLE_MAP` trigger list (FIX-110) correctly fires for any prototype agent, but the actual HTML production requires `prototype-build` to be present.
- The `...selections["prototype-build"]` spread ensures any user-composed levers (model/retry/validators) from `AgentsPopup` for the `prototype-build` agent are preserved alongside the injected `strategy` override.


---

### FIX-120 — KAN-120 Resume Run: 4 compounding bugs fixed (DB race, agent statuses, task data, error handling)

**Date:** 2026-07-27
**Triggered by:** `/velocity-ai-fix Fix KAN 120` — user stopped a prototype pipeline during Build Agent task 2, clicked "Reopen & fix from the failed step", and observed: (1) ApiError 409 "Run is 'generating'", (2) agent circles all empty/idle after resume, (3) tasks 1-2 showing "No further detail recorded for this task", (4) any resume error silently navigated to home.

#### Root Cause

**BUG 1 — DB race → 409 on fast-click:**
The cooperative cancel (`_CANCEL_EVENTS[run_id].set()`) fires synchronously, causing `pipeline_cancelled` to reach the FE immediately (FE shows "Cancelled by you"). However, `_drive_launch_to_queue` in `run_commands.py` writes `wr.status = "cancelled"` only AFTER fully draining the SSE event queue — a 1-5 second async window. If the user clicks "Reopen & fix" during this window, the resume endpoint's eligibility check (`wr.status not in {"failed", "cancelled"}` at `run_commands.py:376-383`) sees `"generating"` and returns 409. The error handler at `DashboardLayout.tsx:1416-1418` called `handleGoHome()` silently for ANY error.

**BUG 2 — Agent statuses all reset to idle after resume:**
`pipeline_start` from the resumed engine calls `agentStates = agents.map(a => ({...a, status: "idle"}))` (`useWorkflow.ts:228-234`), resetting ALL agents to idle. The engine's dispatch loop skips agents 0..(offset-1) without re-emitting `agent_start`/`agent_complete` for them. Since the pipeline_start had `resume_offset: 0` in the event payload, the FE had no way to know which agents were already done.

**BUG 3 — Task 1 and Task 2 show "No further detail recorded":**
The engine's task_loop strategy uses `resume_completed_task_ids` to skip pre-stop tasks. When task 3 completes, it emits `task_progress` with `completed_tasks = [task3]` — not including tasks 1-2 (skipped). The `task_progress` handler in `useWorkflow.ts:771-782` did a FULL REPLACE (`protoCompletedTasks: completedTasks`), wiping task 1-2 data. Additionally, `pipeline_start` did not preserve `protoCompletedTasks` from `prev` when `resumeOffset > 0`.

**BUG 4 — Error silently navigates to home:**
`handleResumeRun`'s `.catch((e) => { handleGoHome() })` navigated away for any error including the timing-race 409, giving the user zero feedback.

#### Phase Context
- **Phase(s) involved:** Phase 50 (RESUME-18 / KAN-120 — user-resume endpoint), Phase 44 (SSE transport / pipeline_start), Phase 31 (RunChatLane terminal state)
- **Relevant register section:** Phase 50 §2 (resume_run_endpoint), Phase 12 §3 (pipeline_start FE handler), Phase 31 §3 (terminal state rendering)
- **Deleted code verified (not resurrected):** No deleted code resurrected. All changes are additive.
- **Locked decisions respected:** ND-D — all text shown in the error banner is generic ("Could not resume the run — please try again"), never hardcoded fiction. SC-001 — no workflow-name literal added anywhere. INV-3 — `resume_offset: 0` on every normal run keeps the pipeline_start event payload backward-compatible.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/execution_engine/engine.py` | Added `"resume_offset": _resume_from` to the `pipeline_start` event payload | Gives the FE authoritative knowledge of which agents were already completed before the resume; 0 on normal runs → zero regression |
| `frontend/src/hooks/useWorkflow.ts` | `pipeline_start` handler: reads `resume_offset`; sets agents at `idx < resumeOffset` to `status: "done"`; seeds `completedCount` and `currentAgentIndex` from the offset; preserves `protoCompletedTasks` / `protoCompletedTaskCount` from `prev` when `resumeOffset > 0` | Fixes BUG-2 (agent statuses) and BUG-3 (task data preservation on resume's pipeline_start) |
| `frontend/src/hooks/useWorkflow.ts` | `task_progress` handler: changed from full-replace to max-wins merge (keyed by task `number`); new tasks extend the array, existing tasks win unless overridden | Fixes BUG-3 (task data for pre-stop tasks survives when resumed engine only reports newer tasks) |
| `frontend/src/components/layout/DashboardLayout.tsx` | Added `resumeError` state; `handleResumeRun` clears it before attempt, retries once after 2.5s if error code is `run_not_resumable` with `generating` status, shows inline error for all other failures; added `useEffect` to clear `resumeError` when `isPipelineRunning` becomes true; added `pipeline_already_running` fast-path (attach SSE stream); threaded `relaunchError={resumeError}` to `RunChatLane` | Fixes BUG-1 (timing race retry) and BUG-4 (inline error instead of silent home navigation) |
| `frontend/src/components/chat/RunChatLane.tsx` | Added `relaunchError?: string | null` prop to `RunChatLaneProps`; destructures it in the component; renders an amber error banner above the "Reopen & fix" button in both the cancelled and failed terminal states | Displays the inline error message (BUG-4) |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): Clean — resume_offset is generic data; pipeline_start handler uses array index not workflow name; error message is a generic string
- **INV-3** (golden parity): Clean — `resume_offset: 0` on every normal run leaves the pipeline_start payload backward-compatible; `task_progress` merge is a no-op when `prev.protoCompletedTasks` is empty (normal fresh run); goldens are never touched
- **INV-12** (no duplication): Clean — reuses existing `postResume` function; no second resume path created
- **SC-001** (zero engine edits for new workflows): Not affected — only additive data field in the existing pipeline_start event; no new capability, no new workflow

#### Verification
- Backend starts clean (alembic=0027, no import errors)
- All 3 frontend files pass TypeScript diagnostics (zero errors)
- BUG-1: `run_not_resumable + "generating"` → retry fires after 2.5s; any other error → amber banner shown, no home navigation
- BUG-2: resumed pipeline_start with `resume_offset=3` → agents 0-2 initialized as `status:"done"`, agents 3-4 as `status:"idle"`, `completedCount:3`
- BUG-3: `task_progress` with `completedTasks=[task3]` when `prev.protoCompletedTasks=[task1,task2]` → merged result `[task1, task2, task3]` (sorted by number)
- BUG-4: amber banner appears above "Reopen & fix" button; banner clears automatically when `isPipelineRunning` becomes true (resume accepted)

#### Notes
- The 2.5s retry window covers the typical DB commit lag (~1-2s for the queue drain). If the backend is under heavy load, a second click by the user also works since `resumeError` is cleared before each attempt.
- The `pipeline_already_running` fast-path (attach SSE stream without re-posting) handles the edge case where the user clicks Reopen a second time while the first resume is already running.
- The `task_progress` merge is safe for normal (non-resume) runs: when `prev.protoCompletedTasks` is `[]` (fresh run, pipeline_start just fired), the merge of an empty map with the new tasks produces exactly `completedTasks` — byte-identical to the prior replace.
- BUG-2 also fixes the inconsistency between the left-lane PipelineMini ("1/5 agents") and the Steps panel ("0/5") — both read from the same `pipelineState` which is now correctly seeded from the `resume_offset`.


---

### FIX-121 — Three Stop/Resume UI bugs: skipped agent, reconnecting banner, unresponsive stop

**Date:** 2026-07-27
**Triggered by:** `/velocity-ai-fix` — user stopped pipeline during Spec Kit Analyzer, clicked Run Again, and observed: (1) resume started from Build Agent, skipping Spec Kit Analyzer with no data shown for it; (2) Stop button appeared unresponsive during resumed Build Agent run; (3) Yellow "Reconnecting…" banner appeared every time Stop was clicked.

#### Root Cause

**BUG 1 — Spec Kit Analyzer skipped (incorrect resume offset):**
`_first_incomplete_step` in `engine.py` determines the resume offset by checking if each agent produced a durable `artifact_refs` entry (`produced_agents`). For `single_shot` (non-wave, non-task_loop) agents, the completeness check was:
```python
if agent_id in produced_agents or agent_id in completed_step_events:
    continue
```
If `prototype-analyze` (Spec Kit Analyzer, index 2) wrote its summary artifact to the store but was killed BEFORE emitting `agent_complete` (which happens in a narrow window between the artifact write and the event emission), the agent appeared complete (`produced_agents` membership) but had no terminal event in the durable store. The resume offset was set to 3 (Build Agent), skipping Spec Kit Analyzer entirely. The FE then marked it as "done" with empty output/thinking data (no `agent_complete` event in the SSE replay means no data restoration).

**BUG 2 — Stop button appears unresponsive:**
The second stop DID fire correctly at the backend level. The problem was BUG 3 below: the yellow "Reconnecting…" banner appeared immediately after the stop, making the user think the stop hadn't worked. The banner was the visual confound.

**BUG 3 — Yellow "Reconnecting…" banner after every Stop click:**
In `dashboard/page.tsx`, the `pipeline_cancelled` case did NOT call `detachRunRef.current?.(cancelledId)`, unlike the `pipeline_complete` case which DOES call it. When Stop fires:
1. `pipeline_cancelled` SSE event arrives → `pipelineState.cancelled = true`, `isRunning = false`
2. The backend closes the run's SSE stream after draining `pipeline_cancelled`
3. `useRunStream` stream reader gets `done: true` (server closed connection)
4. `sawNonLiveAttachRef.current` is `false` (was a live `stream_attached{live:true}`)
5. → `scheduleReconnect()` is called → `phase = "reconnecting"`
6. → Yellow "Reconnecting…" banner appears

The fix is to call `detachRun(cancelledId)` when `pipeline_cancelled` fires, just as `pipeline_complete` does. This makes the `RunStreamConnection` unmount (`stoppedRef.current = true`), which prevents the `scheduleReconnect()` call when the stream closes.

#### Phase Context
- **Phase(s) involved:** Phase 45-49 (RESUME engine), Phase 44 (SSE transport/BUG-015), Phase 29 (run_commands cancel/SSE stream)
- **Deleted code verified (not resurrected):** No deleted code resurrected.
- **Locked decisions respected:** ND-D — no hardcoded text; SC-001 — no workflow-name literals; INV-3 — golden parity preserved (agent_complete_events check is dormant when no events exist in offline harness).

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/execution_engine/engine.py` | Added `agent_complete_events: set[str]` collection from durable `run_events` (type `"agent_complete"`, keyed by `payload_json.agent_id`); changed the non-wave single_shot completeness check from `produced_agents OR completed_step_events` to `(produced_agents AND agent_complete_events) OR completed_step_events` | An agent stopped between artifact-write and `agent_complete` emission has the artifact but no completion event — requiring both signals ensures such agents are re-run rather than skipped with no data |
| `frontend/src/app/dashboard/page.tsx` | Added `detachRunRef.current?.(cancelledId)` call in the `pipeline_cancelled` case of the switch statement, mirroring the identical call in the `pipeline_complete` case | Makes the `RunStreamConnection` unmount when the run is cancelled, preventing `scheduleReconnect()` from firing when the backend closes the SSE stream after `pipeline_cancelled` drains |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): Clean — `agent_complete` check uses generic `payload_json.agent_id`, no workflow name
- **INV-3** (golden parity): Clean — `agent_complete_events` set is empty when no durable events exist (offline harness), `complete_by_artifact` = False, falls through to `return i` — same as before for tests without durable substrate. For agents that truly completed before the stop (both `produced_agents` AND `agent_complete_events`), behavior is identical to before.
- **INV-12** (no duplication): Clean — reuses the existing `durable_rows` read, no second round-trip
- **SC-001** (zero engine edits for new workflows): Not affected — these are completeness-scan changes, no new capability or manifest

#### Verification
- Backend starts clean with the engine.py change
- Frontend diagnostics: no TypeScript errors in `dashboard/page.tsx`
- **BUG 3 trace with fix:** `pipeline_cancelled` fires → `detachRunRef.current?.(cancelledId)` → `focusedRunIdRef.current = null` → `recomputeLiveRunIds` → `RunStreamConnection` for this run is removed from `liveIds` → component unmounts → `stoppedRef.current = true` → stream close does NOT call `scheduleReconnect()` → no yellow banner
- **BUG 1 trace with fix:** `prototype-analyze` killed between artifact-write and `agent_complete` → `produced_agents` contains it, `agent_complete_events` does NOT → `complete_by_artifact = False` → `completed_step_events` also doesn't contain it → `return i` (offset = 2 = Spec Kit Analyzer) → resume starts FROM Spec Kit Analyzer, re-runs it, emits `agent_complete` → data shown correctly

#### Notes
- BUG 2 (second stop unresponsive) was a visual confound caused by BUG 3's reconnecting banner. The second stop itself functioned correctly at the backend — `_CANCEL_EVENTS[run_id]` is re-registered by `resume_run_endpoint` at step (4) before spawning the drive task, so `cancel_run` finds and sets the event normally.
- The `agent_complete_events` check is a STRENGTHENING of the single_shot completeness signal — it converts `produced_agents OR completed_step_events` to `(produced_agents AND agent_complete_events) OR completed_step_events`. Old behavior is preserved for: (a) agents with `step_completed`/`step_reused` events (unaffected), (b) agents with BOTH artifact and `agent_complete` event (correctly classified complete), (c) offline/no-durable-store cases (sets are empty, falls through to `return i` = re-run from start, same as before).
- The task_loop and wave_scheduler branches are unaffected — they have their own completeness logic and don't use `produced_agents` for their primary check.


---

### FIX-122 — Root fix for yellow "Reconnecting" banner and Stop button appearing unresponsive

**Date:** 2026-07-27
**Triggered by:** Follow-up after FIX-121 — user still sees yellow "Reconnecting…" banner after clicking Stop, and Stop button appears unresponsive during Build Agent tasks.

#### Root Cause

FIX-121 added `detachRunRef.current?.(cancelledId)` in the `pipeline_cancelled` case in `dashboard/page.tsx`. The intent was to release the sticky SSE focus when a run is cancelled, so `RunStreamConnection` unmounts before the backend closes the stream. However, this approach has a race condition:

1. `pipeline_cancelled` frame is dispatched in the `dispatchBlock` closure inside `useRunStream`'s async reader loop
2. `onMessage(msg)` → React state updates scheduled (`setLiveRunIds`)  
3. But React state updates are **asynchronous** — they don't apply until the next render cycle
4. The async reader loop immediately continues: `await reader.read()` → backend closes connection → `{done: true}`
5. At this point `stoppedRef.current` is still `false` (unmount hasn't happened yet)
6. → `sawNonLiveAttachRef.current` is `false` (was a live `stream_attached{live:true}`)
7. → `scheduleReconnect()` fires → `phase = "reconnecting"` → yellow banner

**The correct fix**: Set `sawNonLiveAttachRef.current = true` directly inside `dispatchBlock` when `pipeline_cancelled` or `pipeline_failed` arrives. This is synchronous — it happens within the same microtask as the frame is processed, guaranteed to run before the next `await reader.read()`. When the stream closes after `pipeline_cancelled`, `sawNonLiveAttachRef.current` is already `true` → `setPhase("disconnected")` (quiet) instead of `scheduleReconnect()` (yellow banner).

This mirrors how `stream_attached{live:false}` already handles terminal runs (BUG-015) — it marks the ref true so the close doesn't reconnect. `pipeline_cancelled`/`pipeline_failed` are the same category: intentional terminal events after which the backend closes the stream.

The `detachRun` call in FIX-121 is kept as **additive insurance** (it ensures the `RunStreamConnection` component is eventually removed), but the `sawNonLiveAttachRef` set is the guaranteed-synchronous fix for the banner.

#### Phase Context
- **Phase(s) involved:** Phase 44 (BUG-015 — SSE transport non-reconnect for terminal runs, useRunStream.ts)
- **Deleted code verified (not resurrected):** No deleted code resurrected.
- **Locked decisions respected:** BUG-015 pattern exactly extended: terminal events mark the connection as non-reconnecting.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/hooks/useRunStream.ts` | Added `if (type === "pipeline_cancelled" \|\| type === "pipeline_failed") { sawNonLiveAttachRef.current = true; }` inside `dispatchBlock`, after the `stream_attached` handler | Synchronously marks the connection non-live when a terminal event arrives, before the backend closes the stream. The close-branch then calls `setPhase("disconnected")` instead of `scheduleReconnect()`, eliminating the yellow banner. |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): Not affected — purely SSE lifecycle
- **INV-3** (golden parity): Not affected — FE-only change, no backend/engine impact
- **INV-12** (no duplication): Not affected — single change to existing ref pattern
- **SC-001** (zero engine edits for new workflows): Not affected — FE-only change

#### Verification
**Trace with fix applied:**
1. Stop clicked → `postCancel(token, runId)` → `_CANCEL_EVENTS[run_id].set()` → engine emits `pipeline_cancelled` → SSE stream delivers it
2. `dispatchBlock` processes `pipeline_cancelled` → `sawNonLiveAttachRef.current = true` (synchronous, same microtask)
3. `onMessage(msg)` called → React reducer processes cancel
4. Async reader: `await reader.read()` → backend closes stream → `{done: true}` → `buf.trim()` → exit loop
5. `!stoppedRef.current && !controller.signal.aborted` → true (component still mounted)
6. `sawNonLiveAttachRef.current` → **true** → `setPhase("disconnected")` (quiet, no banner) ✅
7. No yellow "Reconnecting…" banner

**Stop button responsiveness:**
- The button IS rendered (runState="building", `isRunning=true`)
- `postCancel` fires successfully (backend `_CANCEL_EVENTS` is set by `resume_run_endpoint` step 4)
- The user sees the stop take effect (pipeline_cancelled arrives, UI transitions to terminal state)
- No reconnecting banner → user clearly sees the stop worked

#### Notes
- The `detachRun` call from FIX-121 is kept as defensive layering — it ensures the `RunStreamConnection` eventually unmounts even if `sawNonLiveAttachRef` is somehow bypassed. Belt-and-suspenders approach.
- `pipeline_failed` is included alongside `pipeline_cancelled` for symmetry — a hard failure also closes the stream intentionally and should not trigger a reconnect loop.
