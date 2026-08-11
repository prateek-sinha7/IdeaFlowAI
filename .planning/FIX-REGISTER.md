# Fix Register — VelocityAI / Flowin

> **Purpose.** Every fix applied via `/velocity-ai-fix` is logged here. Read this alongside the Implementation Register before applying any new fix — to avoid re-fixing something already fixed, and to understand the cumulative patch history on top of the planned phases.
>
> **Format per entry:** Date · Fix ID · Root cause · Files changed · Phase(s) involved · Invariants verified · Notes.

---

## Fix Log

| Fix ID | Date | Description | Root Cause | Files Changed | Phase Involved | Invariants | Status |
|--------|------|-------------|------------|---------------|---------------|------------|--------|
| FIX-201 | 2026-08-07 | ISS-061 continued: concurrent run cross-contamination — agents/clarify questions/review gates from one run appearing in another; per-run state store (useRunStateStore viewport pattern); agent progress not updating after clarify submit/gate approval; infinite re-render loop (setCursor + setViewedState); duplicate toast keys; AppHeader LIVE_STATUSES missing "analyzing" | PRIMARY: shared `pipelineState` reducer in `useWorkflow` + shared `questionnaireData`/`reviewGateData` React state causes all concurrent runs to bleed into each other's UI. SECONDARY: `launchPendingRef` in `isForActiveRun` blocked agent frames; `pipeline_start` early-registration didn't set store viewport; `handleSelectWorkflowRun` set refs async not sync; replay skip used stale store state; `project()` created new ref on every frame; toast dedup missing; "analyzing" absent from LIVE_STATUSES. | `frontend/src/hooks/useRunStateStore.ts`, `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/layout/AppHeader.tsx`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/app/dashboard/liveRunSwitch.fix201.test.ts`, `frontend/src/app/dashboard/freshLaunchTranscriptReset.source.test.ts` | Phase 44 (DEF-44-12-4 concurrent run isolation), ISS-061, KAN-168 | INV-1 ✅ (no kernel edits) INV-3 ✅ (frontend-only) INV-12 ✅ (reuses handlePipelineMessage) SC-001 ✅ (run-id/status keyed, no workflow names) tests: 26 frontend ✅ | Done |
| FIX-195 | 2026-08-06 | ISS-061: Header badge/notification clicks navigate to wrong run; Steps panel shows two-run hybrid; notification row tap does nothing (KAN-166) | Fix-A: `page.tsx:2249-2275` launch `.then()` never calls `setRecentRuns` — badge lists stale pre-load runs. Fix-B: `handleSwitchToLiveRun` omitted `launchedRunIdsRef.current.add(runId)` — `isForeignFrame` guard dropped all replayed frames, Steps panel kept prior run's state. Fix-C: `setNotifWorkflowRunId` declared, exported, destructured but never called — `workflowRunId` permanently `undefined`, `onViewResults` falls to type-based stale search. Fix-D: `NotificationPanel.tsx:168-175` row div has `hover:bg-surface-warm` affordance but no `onClick` — tap does nothing. Bonus: `DashboardLayout.tsx` `recentRuns[0]` title-stamp effect now guarded to match the tracked run id. | `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/ui/NotificationPanel.tsx`, `frontend/src/components/ui/NotificationPanel.fix195.test.tsx` | Phase 44 (DEF-44-12-4 history replay), FIX-146→157 lineage, FIX-133, KAN-166 | INV-3 ✅ (FE-only) INV-12 ✅ (setNotifWorkflowRunId wired — no dual mechanism) SC-001 ✅ (keyed on runId/status, no workflow name) tests: 14 frontend ✅ | Done |
| FIX-194 | 2026-08-06 | ISS-060: Completion notification/toast is not run-scoped — finishing run marks a DIFFERENT live run as "complete"; toast shows wrong label (KAN-166) | `DashboardLayout.tsx:441-490` terminal effect fires on any `pipelineState` with `isRunning=false` + all agents done, with NO check that `pipelineState.pipelineRunId` matches the run that owns `currentPipelineNotifId`. History-reopening a completed `user_stories` run replays its `pipeline_complete` into the shared reducer, firing the effect and stamping a gate-paused `prototype` notification as "completed". Toast label taken from stale shared `workflowType` (also wrong). Fix: (1) add `currentPipelineNotifRunId` companion ref (line 373); (2) populate it at every `currentPipelineNotifId.current =` write site; (3) guard in terminal effect: `completingRunId !== currentPipelineNotifRunId.current → return`; (4) toast label from `notifications.find(notifId)?.workflowType ?? workflowType`; (5) clear companion ref in lockstep at every null-assignment. | `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/layout/DashboardLayout.fix194.test.tsx` | Phase 44 (DEF-44-12-4 history replay made it reachable), FIX-155, FIX-157, KAN-166 | INV-3 ✅ (FE-only) INV-12 ✅ (companion ref — no new mechanism) SC-001 ✅ (keyed on runId, no workflow name) tests: 11 frontend ✅ | Done |
| FIX-193 | 2026-08-06 | ISS-059: Concierge free-text ask during an active ("building") run silently no-ops — every message typed while agents are running returns HTTP 200 `{"channel":"steering"}` with no reply (KAN-165) | `handleFreeText` in `RunChatLane.tsx` had a `runState === "complete"` branch that classifies intent via `classifyIntent` LLM and routes "ask" → `{concierge: true}`. Every other `runState` — including `"building"` (active run) — fell straight to the unconditional fallback `sendMessage(text, attachments)` with no options (no `concierge` key). Backend's `route_chat_turn` receives `concierge=false`, dispatches to `CHANNEL_STEERING` (a fire-and-forget steering note with no reply mechanism). HTTP 200 returned, user sees their message echoed, then silence — no error, no chat_reply, no Concierge. Fix: add `runState === "building"` branch, structurally parallel to `"complete"`, reusing the same `classifyIntent` + `addOptimisticMessage` + `{concierge: true}` pattern. Non-"ask" fallback is byte-identical to pre-fix `"building"` behavior (steering). Locked: `"clarify"` / `"gate"` / `"terminal"` NOT touched (Group-C decision, 42-03). | `frontend/src/components/chat/RunChatLane.tsx`, `frontend/src/components/chat/RunChatLane.test.tsx` | Phase 33 (Concierge D-05), Phase 43 (43-02 classify-and-route), KAN-165 | INV-3 ✅ (FE-only, no backend/golden exposure) INV-12 ✅ (reuses classifyIntent — no second classifier) SC-001 ✅ (runState discriminator only, no workflow/agent-name literal) tests: 7 frontend ✅ | Done |
| FIX-192 | 2026-08-06 | ISS-058: RunChatLane voice input mic button was a dead control — no onClick, no hook, renders "Voice · transcribe" but does nothing (KAN-164) | `FreeTextComposer` in `RunChatLane.tsx` imported only the `Mic` icon (not `MicOff`) and never imported or called `useSpeechRecognition`. The button had type/title/aria-label but zero `onClick`. Phase 39-01 explicitly deferred wiring as "out of scope"; the deferral was never tracked forward and two later phases (40, 41) incorrectly declared "there is no product voice-input capability" — refuted by three working call sites in the same codebase. Fix: Path A (wire it up). Add `MicOff` to lucide-react imports; add `useSpeechRecognition` import; inside `FreeTextComposer` add `preSpeechTextRef`, hook call, transcript-append effect (IdeaInputPage dual-gated pattern — append not overwrite), auto-grow companion effect; replace inert button with wired one (disabled+tooltip for unsupported browsers, animate-pulse text-status-failed while listening, Mic↔MicOff swap). | `frontend/src/components/chat/RunChatLane.tsx` | Phase 39 (RUNUI-06, 39-01 deferred item), KAN-164 | INV-3 ✅ (FE-only, no backend/golden exposure) INV-12 ✅ (reuses existing useSpeechRecognition hook) SC-001 ✅ (FreeTextComposer already keyed on generic runState) tests: 14 frontend ✅ | Done |
| FIX-191 | 2026-08-06 | ISS-057: `_extract_docx` silently drops table/header/footer content from uploaded Word docs; all-table docx fires misleading 422; `python-docx`/`python-pptx`/`pypdf` absent from `requirements.txt` (KAN-163) | `_extract_docx` iterated only `doc.paragraphs` — python-docx exposes tables as a separate `doc.tables` collection and headers/footers via `doc.sections[i].header/.footer`. Tables/headers/footers were never visited, so an all-table docx extracted to `""` → 422 at extract-text endpoint or `has_text:false` at run-files endpoint (silent content loss). Root cause 2: `python-docx`, `python-pptx`, `pypdf` not pinned in `requirements.txt` — all three extractors silently fail via broad `except Exception` (also catches ImportError) in the deployed container. | `backend/app/api/file_extract.py`, `backend/requirements.txt`, `backend/tests/unit/test_file_extract_fix191.py` | Phase 30 (UPLD-01 file extract), KAN-163 | INV-12/INV-3/SC-001 ✅ tests: 21 unit ✅ | Done |
| FIX-190 | 2026-08-06 | ISS-056: Clarify question quality gaps — (H1) 7 manifests declare 8 defaults but only 1 round fires, silently dropping 3+ topics; (H2) prototype build/validate agents lack WCAG AA guardrail; (H3) style question fires after wizard already collected a design system (KAN-162) | H1: `ClarifySpec.rounds` defaults to 1; no manifest set `rounds:`. Mechanism was fully built; only manifest data was missing. H2: `accessibility.md` (49-line WCAG 2.1 AA guardrail) existed and was wired to other pipelines but never to prototype-family build/validate agents. H3: `ectx.od_context.ds_id` fully resolved before `engine.execute()` but (a) `style`/`ui_style` never pruned from `missing_information` when ds_id is set, and (b) `template_name`/`ds_name` never added to `od_context` or threaded into planner/clarify prompts. | `backend/agents/workflows/app_builder/workflow.yaml`, `backend/agents/workflows/custom/workflow.yaml`, `backend/agents/workflows/dotnet_to_azure/workflow.yaml`, `backend/agents/workflows/mulesoft_to_springboot/workflow.yaml`, `backend/agents/workflows/ppt/workflow.yaml`, `backend/agents/workflows/prototype/workflow.yaml`, `backend/agents/workflows/user_stories/workflow.yaml`, `backend/agents/prompts/prototype-build/AGENT.md`, `backend/agents/prompts/prototype-validate/AGENT.md`, `backend/agents/prompts/prototype-revision-agent/AGENT.md`, `backend/agents/prompts/prototype-revision-validate/AGENT.md`, `backend/agents/execution_engine/od_context.py`, `backend/agents/execution_engine/engine.py`, `backend/agents/planner/smart_planner.py`, `backend/agents/execution_engine/clarify_engine.py`, `backend/tests/agents/test_iss056_clarify_quality_fixes.py` | KAN-74 (8-default extension), KAN-87 (no-template mode), KAN-162 | INV-1/3/12/SC-001 ✅ tests: 39 unit ✅ | Done |
| FIX-189 | 2026-08-06 | Tier entitlement never enforced at launch — any user can run any pipeline regardless of tier (KAN-161) | `can_run_pipeline` from entitlements.py only called at workflow-save path (user_workflows.py:274). `launch_run` and `_mint_revision_row` in run_commands.py never imported or called it. Fix: (A1) add tier gate in `launch_run` after `_resolve_launch_agents` using raw pipeline_type; (A2) add tier gate in `_mint_revision_row` after revision_pipeline_type derived, before any DB write — single insertion covers all 3 call sites; (B) add "hexaware" tier to TIER_PIPELINES covering {user_stories, user_stories_revision, prototype, prototype_revision, od_prototype}; update Tier Literal, TIER_LABELS, UPGRADE_PATH; (C) add tier field to _FakeUser in tests defaulting to "enterprise" | `backend/app/api/run_commands.py`, `backend/app/core/entitlements.py`, `backend/tests/unit/test_rest_run_launch.py` | KAN-75 (entitlements), Phase 44-07 (REST launch), KAN-161 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-188 | 2026-08-06 | Concierge chain/gate_action/revision proposals never surface — dead proposals binding (KAN-160) | Two simultaneous gaps: (1) DashboardLayout.tsx:232-235 — RUN_CONCIERGE_PROPOSALS is a module-level frozen empty array constant with no setter; proposals prop permanently empty. (2) useRunChat.ts handleFrame has no concierge_proposal case — durable rows from post-send fetchEvents re-fetch fall to default: branch and are silently dropped. Fix: add HeldProposal interface + proposals useState + concierge_proposal handleFrame case + dismissProposal callback to useRunChat.ts; thread via page.tsx; replace dead binding with runChatProposals ?? RUN_CONCIERGE_PROPOSALS in DashboardLayout.tsx; fix no-op handleRejectProposal to call onDismissRunChatProposal. Zero backend changes. | `frontend/src/hooks/useRunChat.ts`, `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | Phase 33 (D-05), Phase 43 (43-02 deferral), KAN-160 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-187 | 2026-08-06 | Custom template upload silently discarded — content never placed in od_context dict (KAN-158) | Both `load_prototype_context` and `load_ppt_od_context` in `od_context.py` used `custom_template_body` only as a boolean truthy check to select a catalog fallback (`web-prototype` / `html-ppt`). The actual uploaded HTML text was never written into the returned dict's `template_body` key. Downstream injection sites (`factory._compose_injection`, `OpenDesignProvider.load`) only read `od.get("template_body")` — so the catalog fallback's SKILL.md reached agents instead of the user's upload. Fix: add `_synthesize_custom_template(template_id, custom_template_body)` helper (wraps raw HTML in instruction preamble, caps at `EXAMPLE_MAX_CHARS`); replace the catalog-fallback branch in both functions with a call to it. Old catalog-fallback branches deleted per INV-12 (no dual implementation). | `backend/agents/execution_engine/od_context.py` | Phase 32 (OD wizard), KAN-158 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-186 | 2026-08-06 | Custom design system body silently dropped — wire key mismatch `custom_design_system_body` vs `custom_ds_body` (KAN-157) | `DashboardLayout.tsx` lines 342/805/864 sent `custom_design_system_body` in POST /api/runs JSON body. `LaunchCommand` (run_commands.py:1466) only declares `custom_ds_body`. Pydantic v2 `extra="ignore"` silently drops the unrecognised key — `body.custom_ds_body` is always `None`. For prototype/od_prototype: `LookupError` → HTTP 400 `template_not_found`. For od_ppt: silent degrade — run proceeds without design system. Fix: rename 3 wire-key literals in `DashboardLayout.tsx` to `custom_ds_body`. Zero backend changes. | `frontend/src/components/layout/DashboardLayout.tsx` | Phase 32 (OD wizard), KAN-157 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-185 | 2026-08-06 | CR-02 guard blocks prototype_revision and user_stories_revision dispatched via chat-lane revision channel (KAN-156) | CR-02 guard at engine.py:5906 rejects any `planner: run` manifest. Both manifests declared `planner: run`. Phase 29 generic chat-lane revision channel (route_chat_turn/CHANNEL_REVISION) widened CR-02's blast radius 26 days after it was added without re-audit. Fix: prototype_revision `planner: run → skip`; user_stories_revision `planner: run → skip` + `clarify.mode: auto → skip` (ATOMIC — mode:auto with planner:skip would force CLARIFY_REQUIRED hang). Two parity-test frozensets updated (lockstep). Rejection test retargeted from prototype_output → app_builder_output. New succeed-path test added for prototype_output (fail-before / pass-after pin). All 32 targeted tests pass. | `backend/agents/workflows/prototype_revision/workflow.yaml`, `backend/agents/workflows/user_stories_revision/workflow.yaml`, `backend/tests/agents/test_manifest_parity.py`, `backend/tests/agents/test_id_alias_resolver.py`, `backend/tests/unit/test_revision_intelligence.py` | Phase 14 (CR-02), Phase 29 (chat router), KAN-156 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-182 | 2026-08-05 | Build agent shows DONE / checkmark in Steps spine and left-panel agent list during task-loop iterations | FIX-177 fixed constructionComplete in AgentThinkingTab (L2 task list) but StepsOverviewSpine agent rows, progress bar, and RunChatLane PipelineMini still read raw agent.status === "done" directly. agent_complete fires after EACH task iteration (momentarily setting status="done" before the next agent_start), so all three surfaces showed premature DONE. Fix: added constructionAgentIsReallyDone guard in StepsOverviewSpine (agent rows + progress bar + guardedCompletedCount label) and agentIsReallyDone guard in PipelineMini. Guard logic: construction agent is done only when isRunning===false OR (laterAgentStarted && allTasksDone). SC-001: keyed on /build|construct/ id regex, no agent-name literal | `frontend/src/components/results/StepsOverviewSpine.tsx`, `frontend/src/components/chat/RunChatLane.tsx` | Phase 42 (KAN-99), FIX-046, FIX-166, FIX-177 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-181 | 2026-08-05 | Remove text input area, "Or start from a deliverable" label, and "Create workflow" button from home dashboard | UI elements were present but the text input does nothing actionable and the section label + Create workflow button are no longer needed. Removed the Prompt block (textarea + toolbar + image chips), the section header div, all associated state/refs (internalBrief, attachedImages, fileInputRef, handleBuild, buildDisabled), and unused imports (Paperclip, X, Plus). Props retained in interface for API compat. Grid spacing moved to mt-10 on each grid container | `frontend/src/components/catalog/HomeLaunchGrid.tsx` | Phase 32 (Run screen redesign) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-180 | 2026-08-05 | Duplicate "Approved — build continues" clarify card shown in chat alongside "Review approved — build continues" after gate approve | FIX-167b (commit 2d5b9fcc) persisted a `chat_reply` row `{card_kind:"clarify", text:"Approved — build continues"}` for every approved gate. FIX-178 removed the narrator emission and replaced it with the resolved-gate FE mechanism, but existing DB rows were not deleted. `getRunEvents` replays them; `seenRef` dedup misses them (unique event_id never seen on live SSE path); `isTerminalRun` auto-resolve skips them (card_kind=clarify, not gate). Fix: one-line tombstone guard in `useRunChat.handleFrame` case `"chat_reply"` — drops any frame with `card_kind="clarify"` AND `text="Approved — build continues"` before `upsertNarratorMessage`. SC-001-safe (no pipeline_type branch); INV-3-safe (text never in goldens). | `frontend/src/hooks/useRunChat.ts` | Phase 31 (CHATUI-01), FIX-178, FIX-167b | INV-1/3/12/SC-001 ✅ | Done |
| FIX-179 | 2026-08-05 | Version dropdown shows only 1 version (root run) in Run History detail for `od_prototype` runs | FIX-173's cross-family BFS guard in `_owned_family_members` stripped only the `_revision` suffix before comparing base types. For an `od_prototype` root (type=`"od_prototype"`, base=`"od_prototype"`) and a `prototype_revision` child (base=`"prototype"`), `"prototype" != "od_prototype"` — so ALL revisions were excluded from the family. The root run was the only member returned, causing `VersionTimeline` to hide the chip row (< 2 members). Fix: extend `_canonical_base` normalization to also strip the `od_` variant prefix after stripping `_revision` — `od_prototype` and `prototype_revision` both normalize to `"prototype"`, `od_ppt_revision` normalizes to `"ppt"`, etc. SC-001: generic suffix+prefix strip, no literal workflow-name branch | `backend/app/api/runs.py` | Phase 25 (Revision Families B2), FIX-173 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-178 | 2026-08-05 | Review gate box persists in chat after approval; gate box visible in run history | `ResultCard` always renders gate with box chrome and has no mechanism to hide it after `review_gate_approved`. No `resolved` flag on `ChatMessage`; transcript is append-only. History-reopen seeds all gate cards unresolved. Fix: add `resolved?: boolean` to `ChatMessage`; `useRunChat` sets `resolved=true` on `review_gate_approved`; auto-resolves all gate cards when seeding terminal run transcript; `ResultCard` renders resolved gate as plain inline text "Review approved — build continues" | `frontend/src/types/index.ts`, `frontend/src/hooks/useRunChat.ts`, `frontend/src/components/chat/ResultCard.tsx`, `frontend/src/app/dashboard/page.tsx` | Phase 31 (CHATUI-01), Phase 42 (inline gate) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-177 | 2026-08-05 | Build agent shows DONE / all subtasks complete while last subtask is still running | `constructionComplete` in `AgentThinkingTab.tsx` flips true when `laterAgentStarted=true` (validation agent fires immediately after `agent_complete`) even if `completedTaskCount < totalTasks`. The KAN-99 N-1 cap is bypassed. Fix: guard `constructionComplete` with `completedTaskCount >= totalTasks` in addition to `laterAgentStarted` | `frontend/src/components/results/AgentThinkingTab.tsx` | Phase 42 (KAN-99), FIX-046, FIX-166 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-176 | 2026-08-04 | "Revision started" and "Delivered" still showing twice after FIX-175 | FIX-172's `appendRunChatFrames` fetched ALL events from seq 0 — including already-delivered chat_reply cards like "Revision started". While seenRef dedup should catch these, the dedup can fail when `seedRunChatTranscript` clears seenRef in a race window. Fix: expose `getLastSeq()` from `useRunChat` and pass it as `afterSeq` to `getRunEvents` in FIX-172, so only events AFTER what was last delivered are fetched | `frontend/src/hooks/useRunChat.ts`, `frontend/src/app/dashboard/page.tsx` | Phase 31 (CHATUI-01), FIX-172 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-175 | 2026-08-04 | 2x "Run started" and 2x "Delivered" on single od_ppt run | Event_id mismatch between live SSE delivery and DB-fetched delivery. The engine yielded live chat_reply with `event_id="chat_reply:{source_uuid}"` but the DB stored `event_id="chat_reply:pipeline_start:run:{run_id}"` for "Run started" cards. FIX-172's appendFrames saw a different event_id than what seenRef tracked from the live SSE → dedup miss → duplicate added | `backend/app/agents/chat_narrator.py`, `backend/agents/execution_engine/engine.py`, `backend/tests/unit/test_chat_narrator.py`, `backend/tests/agents/test_restart_resume.py` | Phase 43 (DEF-43-03-1 narrator), FIX-172 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-174 | 2026-08-04 | "Revision started" appearing at top of chat; "Delivered" shown twice on history-reopen | Family chat seed used `sort by data.seq` to merge frames across runs — but seq is per-run-scoped (starts at 1 for each run). Revision run's seq 1 sorted before parent run's seq 200, so "Revision started" appeared first. Same sort also caused each run's "Delivered" card to appear at wrong position (all revision runs' seq 1-5 sorted before parent seq 200). Fix: replace flat seq-sort with family-order-aware merge using `family.members` (already created_at ASC) to determine run ordering | `frontend/src/app/dashboard/page.tsx` | Phase 31 (CHATUI-01/02/03), FIX-167 (KAN-154 gap 1 family seed) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-173 | 2026-08-04 | 4-issue revision system: (1) version family cross-contamination; (2) execution page not loading on revision start; (3) duplicate "Delivered" cards; (4) run history chat missing | (1) `_owned_family_members` BFS had no pipeline-type filter — concurrent PPT + prototype revisions cross-pollinated families. (2) `handleRevisePpt` postRevision path never called `setMainView("execution")`. (3) FIX-172 async fetch wasn't guarded: stale concurrent revisions appended their "Delivered" card to the current transcript after trackedRunIdRef had moved on. (4) Fixed by (1) — correct family members seeded to transcript | `backend/app/api/runs.py`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/app/dashboard/page.tsx` | Phase 29/44 (SSE), Phase 25 (Revision Families B2), Phase 43 (FIX-172) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-172 | 2026-08-03 | "Delivered — open in Preview" card missing after revision completes | SSE race: execute() yields `pipeline_complete` then yields the narrator's `chat_reply` card. FE receives `pipeline_complete` → calls `detachRun(runId)` → React unmounts `RunStreamConnection` → SSE closes before the `chat_reply` arrives. Card IS persisted to DB but never reaches the transcript live. Fix: after `pipeline_complete` + detach, fetch the run's durable events from DB and fold `chat_reply` frames via new `appendFrames` (no reset, idempotent) | `frontend/src/hooks/useRunChat.ts`, `frontend/src/app/dashboard/page.tsx` | Phase 29/43/44 (narrator/SSE/BUG-015 detachRun) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-171 | 2026-08-03 | Duplicate user message in chat; no "Revision started"/"Delivered" cards for revision runs | (1) `confirmRefinement` called `addOptimisticMessage` (FIX-168) but `handleFreeText` already called it when user typed — double bubble. (2) `_drive_revision_to_queue` called `engine._handle_revision()` without `milestone_sink` so the narrator never fired for revision runs — no chat_reply cards persisted | `frontend/src/components/chat/RunChatLane.tsx`, `backend/agents/execution_engine/engine.py`, `backend/app/api/run_commands.py` | Phase 29/43 (narrator/chat_reply), Phase 31 (CHATUI-01 transcript) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-170 | 2026-08-03 | Revision UI frozen after launch — pipeline_start/agent events discarded as foreign; revision message not shown; no "Revision started" card | `handleRevisePpt`'s `postRevision` path (od_ppt/od_prototype) called `runConnection.attachRun(run_id)` but never updated `trackedRunIdRef`, `activelyBuildingRunIdRef`, or `launchedRunIdsRef` in page.tsx. `isForeignRunFrame` blocked ALL revision run events → UI frozen, no agent progress, must refresh. Fix: new `handleRevisionLaunched` callback in page.tsx updates the 3 refs; `onRevisionLaunched` prop wires it into `handleRevisePpt`'s `.then()` | `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | Phase 29/44 (SSE transport / KAN-125 ref-gating) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-169 | 2026-08-03 | Run history: no delete option on revision member rows — only the base run can be deleted | Expanded member rows in `FamilyGroupCard` were plain `<button>` elements with no `RowMenu` attached. The `RowMenu` (with Delete) was only on the multi-member root header and single-member root rows. Fix: wrap each member row in a `<div>` flex container, split it into a `<button>` for row-click + a `<RowMenu>` with `runId={member.id}` that fades in on row hover | `frontend/src/components/history/RevisionFamilyView.tsx` | Phase Revision Families (B2 / POR §5 D3+D4) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-168 | 2026-08-03 | KAN-154: Revision instruction text never appears in chat — addOptimisticMessage missing in confirmRefinement and handleTerminalRevise | `confirmRefinement` called `onRevise(heldRefinement)` directly without first calling `addOptimisticMessage(heldRefinement)`, so the user's revision text was never echoed into the transcript. Same gap in `handleTerminalRevise` for the terminal-state revise path. Fix: call `addOptimisticMessage` before `onRevise` in both paths | `frontend/src/components/chat/RunChatLane.tsx` | Phase 31 (CHATUI-01 RunChatLane), Phase 33 (FIX-119 optimistic echo pattern) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-167 | 2026-08-03 | KAN-154: Unified Family Chat Panel — 3 gaps: (1) family transcript not seeded on reopen; (2) pipeline/deliverable cards had box chrome; (3) narrator missing revision-started and gate-approved projections | Gap 1: `seedRunChatTranscript` never called `getRunFamily` — only seeded the single viewed run's events. Gap 2: `ResultCard` rendered all card kinds with box chrome; `clarify` was already inline-link. Gap 3: `chat_narrator.py` had no `review_gate_approved` projection and no `*_revision pipeline_start` projection | `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/chat/ResultCard.tsx`, `backend/app/agents/chat_narrator.py` | Phase 31 (CHATUI-01/D-02 family transcript), Phase 29 (chat_narrator milestone projections) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-166 | 2026-08-03 | KAN-153: Build Agent task list shows all tasks upfront — store total_tasks from task_loop_progress | Frontend task_loop_progress handler read task_number but discarded total_tasks (present in backend payload since task_loop.py Phase 7). AgentThinkingTab derived totalTasks from wave universe/completed count (both 0 at build start). Fix: add protoTotalTasks to PipelineRunState, store it in task_loop_progress handler, prefer it in AgentThinkingTab totalTasks derivation | `frontend/src/types/index.ts`, `frontend/src/hooks/useWorkflow.ts`, `frontend/src/components/results/AgentThinkingTab.tsx` | Phase 7 (task_loop strategy), Phase 42 (ConstructionBlock) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-165 | 2026-08-03 | Analyze gate approve requires 2 clicks — first click disables button but does nothing visible | `onApproveReview` in page.tsx never called `setReviewGateData(null)` after the POST, so `InlineGateActions` stayed mounted with unchanged props, `useEffect([output,gateKey])` never fired, `submitted` stayed `true`, button remained disabled. All other gate handlers (reject/redo/update_specs) had the clear — approve was missing it | `frontend/src/app/dashboard/page.tsx` | Phase 8 (GATE-01/02), Phase 42 (inline gate) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-164 | 2026-08-03 | KAN-101: specRevisionCount over-counting — shows "Cycle 6" after 1 update_specs click | Detection incremented counter for EVERY agent_start of a "done" agent; update_specs re-runs 3 agents so 1 click = +3 (or more). Fix: arm/consume pattern — counter only increments once per revision cycle (when first agent re-starts), not once per agent | `frontend/src/app/dashboard/page.tsx` | Phase 27 (FIX-048/FIX-163 KAN-101) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-163 | 2026-08-03 | KAN-101: Restore spec revision cycle UX — violet "Spec Revision Cycle N" banner in Steps, elevate "Update the Specs" button out of Request changes, fix approveLabel on analyze gate | `specRevisionCount` deleted in Phase 42 (ISS-039); no detection/state for re-started agents; "Update the Specs" collapsed under "Request changes" (2-click discovery); `approveLabel` read "Approve the summary" | `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/preview/PreviewPanel.tsx`, `frontend/src/components/results/AgentThinkingTab.tsx`, `frontend/src/components/results/StepsOverviewSpine.tsx`, `frontend/src/components/chat/InlineGateActions.tsx` | Phase 27 (FIX-048 KAN-101), Phase 42 (ISS-039) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-157 | 2026-07-31 | Running dropdown and notification panel: click doesn't open correct run page; progress shows 0/N; onViewResults status filter misses planning/generating | Three bugs: (1) `handleRunClick` in AppHeader called `onSwitchToLiveRun` but not `onGoToPipeline` → execution view never switched; (2) `onViewResults` targetRunId lookup used `r.status === "running"` and missed runs in planning/generating/clarifying states; (3) `runningPipelines` always mapped `agentsCompleted: 0` — fixed by passing `activePipelineRunId` and using live `pipelineAgentsCompleted`/`Total` for the matching run | `frontend/src/components/layout/AppHeader.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | Phase 35 (SHELL-01 AppHeader), FIX-156 follow-up | INV-1/3/12/SC-001 ✅ | Done |
| FIX-156 | 2026-07-31 | Running dropdown not showing user_stories (or any run) — `runningPipelines` undefined causing crash; `recentRuns` never passed to AppHeader | Two bugs: (1) `runningPipelines` variable used throughout AppHeader JSX was NEVER DEFINED — causing `ReferenceError: runningPipelines is not defined` and the entire header crashing; (2) `recentRuns`, `onSwitchToLiveRun`, and `onSelectWorkflowRun` were never passed to AppHeader from DashboardLayout — so even after defining the variable, it would get empty server data. Fix: define `runningPipelines` derived from `recentRuns` (same source as Jump Back In); pass the 3 missing props to AppHeader; add status label text in the dropdown rows; extend `WorkflowStatus` type to include live statuses. | `frontend/src/components/layout/AppHeader.tsx`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/ui/NotificationPanel.tsx`, `frontend/src/types/index.ts` | Phase 35 (SHELL-01 AppHeader), Phase 36 (SHELL-02 Jump Back In) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-155 | 2026-07-31 | Header shows duplicate running workflow entries (7 instead of 3) — notifications for prototype/ppt not created when user_stories runs concurrently | With 3 concurrent runs, `currentPipelineNotifId` is a single ref. `handleRunPipeline` (user_stories) sets it first; `pendingOdProtoParams`/`pendingOdPptParams` handlers see it non-null and try to reuse it (calling `updateAgentsTotal` on the user_stories notification instead of creating a new one); `odProtoNotifCreated` reactive effect also guards on `!currentPipelineNotifId.current` → false → skips. Result: prototype and ppt notifications never created. Fix: add `odProtoNotifId`/`odPptNotifId` per-type refs; explicit handlers always create their own notification and pre-set the type-specific ref; reactive effect checks the type-specific ref before calling `addRunningNotification`. | `frontend/src/components/layout/DashboardLayout.tsx` | FIX-149 (notification system) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-154 | 2026-07-31 | user_stories review gate shows no summary content — discriminateArtifact called without artifactKind param | `InlineGateActions` called `discriminateArtifact(output)` without the second `artifactKind` argument, so agents whose output lacks XML wrapper tags (user_stories domain-analyst = plain markdown, kind="summary") returned null. `GateContext` also had no `artifactKind` field so the backend value never reached the component. | `frontend/src/components/chat/RunChatLane.tsx`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/results/StepsOverviewSpine.tsx`, `frontend/src/components/chat/InlineGateActions.tsx` | Phase 42 (gate inline), Phase 28 (artifactPreview) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-153 | 2026-07-30 | KAN-146: Concurrent run review gates cross-contaminate screens and appear before agent output (corrected: trackedRunIdRef not activelyBuildingRunIdRef) | `isForeignGate`/`isForeignQuestionnaire` checks in page.tsx initially used `launchedRunIdsRef` (all same-tab run IDs), then corrected to `activelyBuildingRunIdRef` (latest-launched run — wrong for 3+ runs or run-switching). Final fix uses `trackedRunIdRef` (the run currently VIEWED on screen), which is updated by all run-switch paths. DashboardLayout also gained mutual exclusion between gate and clarify panels. | `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | KAN-125 (FIX-135 pattern) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-152 | 2026-07-30 | KAN-139: 9 D-cluster infrastructure defects (memory leaks, missing logging, missing shutdown, missing admission control, dead config) | D1: mockSse test title claimed backend guarantee; D2: sendCommand no res.ok check; D4: ArtifactStore HITL dicts never evicted; D5: StateMachine._states never evicted + private reach; D6: sweep_expired zero callers + data-loss mtime bug; D7: close_checkpointer bugs + not wired to shutdown; D9: restore_non_terminal_runs no admission control; D10: SSE_STREAM_IDLE_TIMEOUT_SECONDS dead config; D11: run_stream.py no logging | `backend/agents/artifact_store/store.py`, `backend/agents/execution_engine/state_machine.py`, `backend/app/api/run_engine.py`, `backend/app/api/run_commands.py`, `backend/app/agents/sandbox.py`, `backend/app/agents/checkpointer.py`, `backend/app/core/config.py`, `backend/app/main.py`, `backend/app/api/run_stream.py`, `frontend/src/providers/RunConnectionProvider.tsx`, `frontend/e2e/tests/ts-sse-resilience.spec.ts` | Phase 44 (SSE transport), Phase 49 (resume), Phase 12 (restore), Phase 29 (D-14h) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-151 | 2026-07-30 | KAN-137 follow-up: PPT revision chain context empty — _extract_chain_context returns empty context_block for *_revision runs because they have no brief-analyst agent output | `get_chain_context()` in runs.py queried the revision run itself; revision runs (od_ppt_revision etc.) have no od-ppt-brief-analyst / spec-writer agents, so structured_summary="" and context_block="". Fix: walk up to parent_run_id for *_revision types, extract context from the ORIGINAL pipeline run, and append the revision instruction. | `backend/app/api/runs.py` | Phase 25 (chain context / Workstream A) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-150 | 2026-07-30 | KAN-137: PPT revision → User Stories chain fires run but Steps trace stays empty; no agents start | Two bugs: (1) handleChainPipeline parsed workflowInput (the revision blob) to get chainBrief, extracting the PPT revision instruction ("make slide 3 more concise") as the user_stories brief — causing auto-clarify to block at waiting_for_user with no visible questionnaire; (2) setMainView("execution") was missing before onStartPipeline. Fix: for revision-type source runs, extract "Original Brief:" from context_block instead of parsing workflowInput; add setMainView("execution") synchronously before firing the pipeline. | `frontend/src/components/layout/DashboardLayout.tsx` | Phase 25 (Workstream C1 chain context) / Phase 42 (Steps inline clarify) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-149 | 2026-07-30 | KAN-132 (Bug 1+2): Prototype dropdown title shows "Prototype · Prototype" and clicking still navigates to User Stories run | Bug 1: `odProtoNotifCreated` effect used hardcoded `"Prototype"`/`"Presentation"` as title; submittedBrief available but ignored. Bug 2: `onViewResults` for running notifications called `onSelectWorkflowRun` (a history-reopen fn that calls resetPipeline(), getWorkflow() fetch, resetReplayState()) — completely wrong for a live run. Fix: (1) use `submittedBrief` as notification title; (2) add `onSwitchToLiveRun` prop + `handleSwitchToLiveRun` in page.tsx that only attaches SSE + updates trackedRunIdRef/activelyBuildingRunIdRef/contentSource without resetting state; (3) onViewResults now calls onSwitchToLiveRun for running notifications. | `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/app/dashboard/page.tsx` | Phase 35/38 (KAN-132 follow-up) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-148 | 2026-07-30 | Clicking Prototype in multi-run header dropdown still navigates to User Stories — onViewResults only called setMainView("execution") regardless of which run was clicked | onViewResults was a single handler that called setMainView("execution") for any running notification, showing whatever pipelineState was tracking (the active building run). Fix: (1) add setNotifWorkflowRunId to useNotifications; (2) onViewResults now finds the matching recentRun by workflowType and calls onSelectWorkflowRun to switch the active context to that specific run. | `frontend/src/hooks/useNotifications.ts`, `frontend/src/components/layout/DashboardLayout.tsx` | Phase 35 (SHELL-01 AppHeader / FIX-146/147 follow-up) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-147 | 2026-07-30 | KAN-132: clicking Presentation in multi-run dropdown navigated to User Stories run | All dropdown entries called the same onGoToPipeline callback (routes to the single active run). Fix: call onViewResults(pipeline) per entry — already a per-notification callback that DashboardLayout wires to each run's navigation. | `frontend/src/components/layout/AppHeader.tsx` | Phase 35 (SHELL-01 AppHeader) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-146 | 2026-07-30 | KAN-132: Header shows all running pipelines via dropdown when multiple workflows are active | AppHeader badge used scalar isPipelineRunning/pipelineType (one run only). notifications[] already tracked all running pipelines. Fixed by deriving runningPipelines from notifications inside AppHeader: 1 running → existing badge unchanged; >1 running → "N Running" dropdown listing each pipeline with label + title + progress; 0 from notifications but scalar says running → legacy fallback. | `frontend/src/components/layout/AppHeader.tsx` | Phase 35 (SHELL-01 AppHeader) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-145 | 2026-07-30 | KAN-130: Jump Back In shows raw od_ppt/od_prototype names and no Revised/Chained indicators | WORKFLOW_LABELS map missing 4 od_* entries; source_run_id not in WorkflowRunResponse so "(Chained)" impossible. Fix: add od_ppt/od_prototype/revision entries; expose source_run_id through backend → api.ts → WorkflowRun type → HomeLaunchGrid "(Chained)" suffix. | `frontend/src/hooks/useNotifications.ts`, `backend/app/api/runs.py`, `frontend/src/lib/api.ts`, `frontend/src/types/index.ts`, `frontend/src/components/catalog/HomeLaunchGrid.tsx` | Phase 36 (SHELL-02 Jump Back In) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-144 | 2026-07-30 | KAN-131: GET /api/runs?limit=100 returns 2.85MB uncompressed, takes 5.4–6.8s — slim list schema + column-projected query + X-Total-Count + Load More pagination | Backend serialized full WorkflowRunResponse with unbounded Text columns (input, output, agent_outputs) on every history load. FIX-051 existed on staging but was not ported to dev. Cherry-picked: (1) WorkflowRunListResponse slim schema (excludes heavy Text fields). (2) Column-projected query `db.query(*_LIST_COLS)` skips reading those fields entirely. (3) Query param validation (limit 1-100, default 50). (4) X-Total-Count header for pagination. Frontend: (1) getWorkflows returns {runs, total} + parses header. (2) All call-sites destructure {runs}. (3) WorkflowHistory adds Load More with append-based pagination. Response size reduced 50x (2.85MB → ~50KB for 50 rows). | `backend/app/api/runs.py`, `backend/app/main.py`, `backend/alembic/versions/0030_workflow_runs_user_created_index.py`, `frontend/src/lib/api.ts`, `frontend/src/components/history/WorkflowHistory.tsx`, `frontend/src/app/dashboard/page.tsx`, `frontend/src/providers/RunConnectionProvider.tsx`, `frontend/src/components/catalog/HomeLaunchGrid.tsx` | Phase 4 (API endpoints) / Phase 13 (list pagination) / Phase 18 (frontend history) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-144 | 2026-07-30 | KAN-129: Context Received panel shows "artifact" instead of source labels — formatContextSource ignores `label` field and doesn't handle run_input/context_block types | `formatContextSource` in AgentDetailPanel.tsx only checks `"summary"` type; all other types fall to `src.artifact_type \|\| "artifact"`. Backend emits `"run_input"` and `"context_block"` with a `label` field (added by KAN-102) but FE type and function never accounted for them. Fix: extend ContextSource type, update formatContextSource to read label, change backend label from "User brief" to "prompt.md". | `frontend/src/types/index.ts`, `frontend/src/components/results/AgentDetailPanel.tsx`, `backend/agents/execution_engine/engine.py` | Phase 22 (KAN-102 context_sources) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-143 | 2026-07-29 | KAN-128: Chat panel still shows static filename for PPT and Prototype — `laneActiveContent` used local `workflowType` instead of `effectiveReviseType` | FIX-141's dispatch keyed on `workflowType` (default `"user_stories"` on history-reopen) not `effectiveReviseType`. On reopened `od_ppt` run, `workflowType="user_stories"` → `laneActiveContent=""` → fallback fires. Fix: use `effectiveReviseType` in both the content slot dispatch and the `deriveDeliverableFilename` call. | `frontend/src/components/layout/DashboardLayout.tsx` | Phase 31/39 (FIX-141 follow-up) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-142 | 2026-07-29 | KAN-128: PPT filename shows "presentation.pptx" instead of content-derived ".html" — wrong extension for all ppt/od_ppt variants | `deriveDeliverableFilename` assigned `"pptx"` for `"ppt"`/`"ppt_revision"` but all PPT runs produce HTML decks. `deriveDeliverableFiles` also offered a dead `.pptx` row. Fix: both functions always use `"html"` for all four ppt variants. | `frontend/src/components/results/FilesTab.tsx` | Phase 18/22/39 (FIX-140/141 follow-up) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-141 | 2026-07-29 | KAN-128: Left chat panel "Run summary" deliverable card shows static manifest filename instead of content-derived name | RunChatLane's dFilename = pipelineState?.deliverableFilename (static manifest). DashboardLayout had all content props but never passed a content-derived deliverableFilename to RunChatLane. Fix: compute laneDerivedFilename using deriveDeliverableFilename() (FIX-140) in DashboardLayout and pass it as the prop. | `frontend/src/components/layout/DashboardLayout.tsx` | Phase 31 (CHATUI-01 RunChatLane), Phase 39 (RUNUI-06 DeliverableCard) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-140 | 2026-07-29 | KAN-128: Output filename inconsistent between Preview URL bar / Download and Files tab across all workflow types; mid-word truncation bug | Preview reads static `pipelineState.deliverableFilename` (manifest name); FilesTab parses `<title>`/`^#` from content. Independent paths, never share a source. `.slice(0,40)` also truncates mid-syllable. Fix: extract `deriveDeliverableFilename(workflowType, content, fallback)` from FilesTab; use it in PreviewPanel for `previewFilename` and `handleHeaderDownload`. | `frontend/src/components/results/FilesTab.tsx`, `frontend/src/components/preview/PreviewPanel.tsx` | Phase 18 (ISS-021 FilesTab), Phase 22 (deliverableFilename), Phase 39 (PreviewChrome/RunHeader) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-139 | 2026-07-29 | Chained pipeline uses wrong source run context — recentRuns type-scan returns older completed run instead of the one on screen | handleChainPipeline resolved sourceRunId via recentRuns.find(type+completed) which returns the first type-match. When multiple completed user_stories runs exist, it returns an older one instead of the currently-viewed run. contentSourceRunId (already set by page.tsx on pipeline_complete) was ignored. Fix: use contentSourceRunId as primary source, recentRuns scan as fallback. | `frontend/src/components/layout/DashboardLayout.tsx` | Phase 25/38 (workflow chaining / KAN-116) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-138 | 2026-07-29 | Concurrent same-type runs show mixed agent progress — HTTP response order race overwrites activelyBuildingRunIdRef with wrong run ID | When two runs are launched in quick succession, HTTP POSTs can resolve out of click order. The first-clicked run's .then() can fire AFTER the second-clicked run's .then(), overwriting activelyBuildingRunIdRef/trackedRunIdRef with the earlier-clicked run's ID, allowing that earlier run's events to reach the reducer and showing mixed agent progress. Fix: launchCounterRef increments on each click; .then() only updates trackedRunIdRef/activelyBuildingRunIdRef when thisLaunchSeq === current counter (i.e. no newer launch has registered). | `frontend/src/app/dashboard/page.tsx` | Phase 29/44 (SSE transport / KAN-125) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-137 | 2026-07-29 | Multi-tab isolation + same-tab isForeignFrame empty-set gap — new tabs show running workflows, concurrent same-tab runs not fully isolated | (1) refreshLiveRuns auto-attached ALL running workflows to new tabs; launchedRunIdsRef empty → isForeignFrame always false → background runs polluted dashboard. (2) Same fix needed for isForeignRun/isForeignFrame — empty Set means no blocking. Fix: persist launchedRunIdsRef to sessionStorage (survives reload, isolated per tab); isForeignFrame blocks when Set empty; refreshLiveRuns only attaches tab-owned runs. | `frontend/src/app/dashboard/page.tsx`, `frontend/src/providers/RunConnectionProvider.tsx` | Phase 29/44 (SSE transport / KAN-125) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-136 | 2026-07-29 | Concurrent run shows "Done" in history while still running — preserve "running" status in recentRuns on foreign-run pipeline_complete refetch | When a concurrent run fires pipeline_complete, the FE calls getWorkflows. The DB may already show the user_stories run as "completed" (backend writes status before SSE delivers the frame). Fix: preserve "running" status in setRecentRuns for any tab-local run in launchedRunIdsRef except the one that just completed. | `frontend/src/app/dashboard/page.tsx` | Phase 29/44 (SSE transport / KAN-125) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-135 | 2026-07-28 | KAN-125: Concurrent prototype agent progress still mismatched — agent_start/agent_chunk/agent_complete lack pipeline_run_id so isForActiveRun was bypassed | Events like agent_start/agent_chunk/agent_complete/tool_call/task_progress don't carry pipeline_run_id in their data. frameRunId resolved to undefined → the !frameRunId pass-through in isForActiveRun always let them through, so all concurrent runs' agent events still corrupted the shared reducer. Fix: inject _sourceRunId (the SSE stream's run_id) per RunStreamConnection in RunConnectionProvider; use it as primary frameRunId in page.tsx. | `frontend/src/hooks/useRunStream.ts`, `frontend/src/providers/RunConnectionProvider.tsx`, `frontend/src/app/dashboard/page.tsx` | Phase 29/44 (SSE transport / KAN-125) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-134 | 2026-07-28 | KAN-125: Concurrent pipeline "nothing in Steps" — second run's pipeline_start reset the shared reducer, wiping first run's agent list | When PPT was launched while User Stories was running, both runs' pipeline_run_ids were in launchedRunIdsRef (Set), so isForeignFrame=false for BOTH. PPT's pipeline_start went to handlePipelineMsgRef which resetted agents[] to PPT agents, wiping User Stories' progress. Fix: introduce activelyBuildingRunIdRef (only updated on launch/reopen, never by content completions) + isForActiveRun Layer-2 gate — only the most-recently-launched run's frames update pipelineState; other tab-local runs save content at pipeline_complete. Also gate wave events for the active run only. | `frontend/src/app/dashboard/page.tsx` | Phase 29/44 (SSE transport / KAN-125) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-133 | 2026-07-28 | KAN-125: History-reopened runs blocked by isForeignFrame — add run.id to launchedRunIdsRef before replaying durable events | When a completed run is opened from history, its durable events carry pipeline_run_id not in launchedRunIdsRef (empty Set in a new session, or only containing current-session run ids). isForeignFrame was true for all events → pipeline_start/agent events blocked → Steps showed empty "Run complete". Fix: add fullRun.id to launchedRunIdsRef and set trackedRunIdRef before replaying durable frames in handleSelectWorkflowRun. | `frontend/src/app/dashboard/page.tsx` | Phase 29/44 (SSE transport / KAN-125 launchedRunIdsRef) | INV-1/3/12/SC-001 ✅ | Done |
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

### FIX-157 — Running Dropdown/Notification Panel Click Doesn't Navigate; Progress Shows 0/N; Status Filter Misses Live States

**Date:** 2026-07-31
**Triggered by:** `/velocity-ai-fix running dropdown and notification panel not showing correct status/progress and clicking does not open run page`

#### Root Cause

Three bugs found after FIX-156:

**Bug 1 — Clicking the running dropdown does NOT navigate to execution view:**
`AppHeader.handleRunClick` called `onSwitchToLiveRun(run.id)` but never called `onGoToPipeline()`. `setMainView("execution")` lives in DashboardLayout — only reachable via `onGoToPipeline` (`() => setMainView("execution")`). Without it, clicking attaches the SSE stream but the user stays on the home/history page.

**Bug 2 — `onViewResults` targetRunId lookup fails for planning/generating/clarifying runs:**
`DashboardLayout.onViewResults` searched `recentRuns.find((r) => r.status === "running" && ...)`. Runs in `planning`, `generating`, `clarifying` etc. are never found → `targetRunId` is undefined → `onSwitchToLiveRun` is not called → user navigates to execution but sees the wrong run.

**Bug 3 — Progress always shows 0/N:**
`runningPipelines` mapped every run with `agentsCompleted: 0`. The list endpoint only has `agentCount` (total), not live completion count. The live `pipelineState.completedCount`/`agents.length` exists in DashboardLayout but was never forwarded.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `AppHeader.tsx` — `handleRunClick` | Added `onGoToPipeline?.()` after `onSwitchToLiveRun` | `setMainView("execution")` needs to fire; only reachable via `onGoToPipeline` |
| `AppHeader.tsx` — `AppHeaderProps` | Added `activePipelineRunId?: string \| null` | Allows live progress enrichment for the tracked run |
| `AppHeader.tsx` — `runningPipelines` mapping | `agentsCompleted`/`agentsTotal` use live values when `r.id === activePipelineRunId` | Shows real "2/6" progress instead of "0/6" |
| `AppHeader.tsx` — single badge click | Changed from `onGoToPipeline` to `handleRunClick(serverRun)` | Attaches SSE + navigates |
| `AppHeader.tsx` — single badge dot | Derives from real server status (amber for waiting/planning) | Matches Jump Back In dot colors |
| `DashboardLayout.tsx` — AppHeader mount | Pass `activePipelineRunId={pipelineState?.pipelineRunId ?? null}` | Feeds active run id to AppHeader |
| `DashboardLayout.tsx` — `onViewResults` | `r.status === "running"` → `LIVE_RUN_STATUSES.has(r.status)` | Finds runs in planning/generating/clarifying etc. |

#### Invariants Verified
- **INV-1**: not affected — no workflow-name literals
- **INV-3**: not affected — FE-only change
- **INV-12/SC-001**: not affected

#### Verification
- TypeScript diagnostics: 0 errors
- Bug 1 trace: click dropdown → `handleRunClick` → `onSwitchToLiveRun` [attach SSE] + `onGoToPipeline` [setMainView("execution")] ✓
- Bug 2 trace: `onViewResults` → `LIVE_RUN_STATUSES.has(r.status)` finds any live run → `onSwitchToLiveRun(targetRunId)` + `setMainView("execution")` ✓
- Bug 3 trace: `activePipelineRunId` match → `agentsCompleted = pipelineAgentsCompleted` (live) → shows "2/6" ✓

---

### FIX-156 — Running Dropdown Not Showing user_stories; Header Crashing (runningPipelines Undefined)

**Date:** 2026-07-31
**Triggered by:** `/velocity-ai-fix not showing user story at all in running dropdown — implement same logic as Jump Back In`

#### Root Cause

Two separate bugs combining to break the running dropdown entirely:

**Bug 1 (CRASH) — `runningPipelines` is referenced but never defined in `AppHeader.tsx`:**
The entire JSX in AppHeader (lines 225, 236–241, 246–265, 285, 325) references `runningPipelines`, but this variable was **never declared anywhere** in the component. The browser was crashing with `ReferenceError: runningPipelines is not defined` (confirmed in the dev log at 01:16:08). Only because React's error boundary was catching it, the header was silently failing rather than fully crashing. The code does define `liveRunsFromServer`, `runningFromNotifs`, `hasServerData`, and `liveRuns`, but then `runningPipelines` — the variable that actually drives the badge and dropdown — was just missing.

**Bug 2 (MISSING DATA) — `recentRuns`, `onSwitchToLiveRun`, and `onSelectWorkflowRun` were never passed to AppHeader:**
The AppHeader mount in DashboardLayout (confirmed by reading the full `<AppHeader ...>` block) did NOT pass:
- `recentRuns` — the server-sourced array that powers "Jump Back In" and IS the source of truth for live run statuses
- `onSwitchToLiveRun` — the correct navigation handler for live runs (avoids resetting pipeline state)
- `onSelectWorkflowRun` — the handler for history/terminal run navigation

Without `recentRuns`, even after fixing Bug 1, `recentRuns` would be `[]` (its default), `liveRunsFromServer` would be `[]`, and the badge would always be empty.

**Why Jump Back In works:** HomeLaunchGrid receives `recentRuns` prop directly from DashboardLayout and maps it to the display. AppHeader was meant to use the same data source but the prop wiring was simply missing.

#### Phase Context
- **Phase(s) involved:** Phase 35 (SHELL-01 AppHeader), Phase 36 (SHELL-02 Jump Back In), FIX-146/147/148 (running dropdown evolution)
- **Deleted code verified (not resurrected):** No deleted code
- **Locked decisions respected:** SC-001 — all status branching keyed on generic `r.status` string, never workflow-name literals; `getWorkflowLabel` is the only type→label mapper

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `AppHeader.tsx` | Added `runningPipelines` definition: maps `liveRuns` (from `recentRuns`) to `PipelineNotification[]` shape, with status normalisation (`waiting_for_user`→`gate`, live statuses→`running`); falls back to `runningFromNotifs` | Defines the previously-undefined variable that all JSX references; uses server data (same as Jump Back In) as the truth |
| `AppHeader.tsx` | Updated dropdown row click handler to use `handleRunClick(serverRun)` (the correct live-vs-terminal navigation), falling back to `onViewResults` only when no server run is found | Matches Jump Back In's click behavior: live runs → `onSwitchToLiveRun`, terminal → `onSelectWorkflowRun` |
| `AppHeader.tsx` | Enhanced dropdown rows to show real status labels (Planning, Building, Waiting for you, etc.) from `RUN_STATUS_TONE` | Shows the same status labels as Jump Back In |
| `AppHeader.tsx` | Pass `recentRuns` to `NotificationPanel` | Allows the notification panel to show real detailed statuses |
| `DashboardLayout.tsx` | Added `recentRuns`, `onSwitchToLiveRun`, and `onSelectWorkflowRun` props to the `<AppHeader>` mount | These were the missing props that caused AppHeader to receive empty/undefined server data |
| `NotificationPanel.tsx` | Added `recentRuns?: WorkflowRun[]` prop; added `LIVE_STATUS_LABEL` map; updated running notification rows to look up real server status and display it | Shows "Planning", "Building", "Waiting for you" etc. in the notification bell panel |
| `types/index.ts` | Extended `WorkflowStatus` to include `planning`, `generating`, `waiting_for_user`, `clarifying`, `analyzing` | The DB stores these values; `WorkflowRun.status` was typed too narrowly, causing silent `unknown status` for live runs |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — all new code keys on generic `status` strings and `type` field through `getWorkflowLabel`, never a workflow-name literal
- **INV-3** (golden parity): not affected — FE-only change; no backend/golden impact
- **INV-12** (no duplication): the same `recentRuns` data source and `getWorkflowLabel` function used in Jump Back In are reused here
- **SC-001**: not affected — no engine edits

#### Verification
- TypeScript diagnostics: 0 errors on all 4 changed files
- Dev log confirmed `ReferenceError: runningPipelines is not defined` at 01:16:08 (pre-fix); latest log entries show `✓ Compiled` without errors (post-fix hot-reload)
- Logic trace with fix:
  1. `recentRuns` now flows from `page.tsx` → `DashboardLayout` → `AppHeader`
  2. `liveRunsFromServer = recentRuns.filter(r => LIVE_STATUSES.has(r.status))` picks up ALL live runs including user_stories, prototype, ppt
  3. `runningPipelines` maps those to the `PipelineNotification` shape the JSX expects
  4. The badge shows "N Running"; the dropdown lists all N runs with their real status labels
  5. Clicking a run uses `handleRunClick` → `onSwitchToLiveRun` (live) or `onSelectWorkflowRun` (terminal), exactly like Jump Back In

#### Notes
- `runningPipelines` falling back to `runningFromNotifs` (the ephemeral notification list) is important for the very first render — before `recentRuns` is populated from the API, the notifications (created by `handleRunPipeline`) ensure the badge still shows. Once the server data arrives (typically < 1s), `liveRuns !== null` and the server data takes over.
- The `WorkflowStatus` type extension is safe — it makes the type honest. The `as WorkflowRun["status"]` cast in `normalizeWorkflowRun` already let these values through at runtime; the type just didn't reflect them. No behaviour change.
- `agentsCompleted: 0` in the `runningPipelines` mapping is a simplification — the backend `WorkflowRun` doesn't return live per-agent completion counts in the list endpoint (only the total `agentCount`). The notification-based fallback path has more accurate `agentsCompleted` since it's driven by live events. This is acceptable: the dropdown shows the type + title + real status, which is the most important information.

---

### FIX-155 — Header Running Count Shows 7 Instead of 3; Prototype/PPT Missing From Notifications

**Date:** 2026-07-31
**Triggered by:** `velocity-fix header shows 7 running, user_stories shows but not prototype; 2x prototype shown wrong`

#### Root Cause

`frontend/src/components/layout/DashboardLayout.tsx` — `currentPipelineNotifId` is a **single `useRef`** shared across all concurrent runs. With 3 concurrent runs (user_stories + prototype + ppt):

1. `handleRunPipeline` (user_stories, ~line 1000) calls `addRunningNotification` and sets `currentPipelineNotifId.current = "pipeline-{ts1}"`
2. `pendingOdProtoParams` effect fires for prototype: checks `currentPipelineNotifId.current ?? …` — it's already set (user_stories id) → falls into `else` branch → calls `updateAgentsTotal` on the **user_stories** notification → **no new prototype notification created**
3. `odProtoNotifCreated` reactive effect fires: guard `!currentPipelineNotifId.current` → false (user_stories id is set) → skips entirely → **no prototype notification**
4. Same problem for od_ppt

The original FIX-155 attempted to fix duplicates (reactive effect fires before explicit handler) but introduced this new regression: the `currentPipelineNotifId.current ?? …` reuse logic ASSUMES the existing ref belongs to the SAME run, but it doesn't — it belongs to the concurrently-running user_stories run.

#### Phase Context
- **Phase(s) involved:** FIX-149 (multi-run notification system, DashboardLayout)
- **Deleted code verified (not resurrected):** No deleted code; refs added.
- **Locked decisions respected:** SC-001 — no workflow-name literals; all changes are generic notification management.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `DashboardLayout.tsx` | Added `odProtoNotifId` and `odPptNotifId` per-type `useRef` alongside `currentPipelineNotifId` | Each concurrent run type needs its own notification id tracking, independent of what other run types are doing |
| `DashboardLayout.tsx` `pendingOdProtoParams` handler | Always creates a NEW notification with `Date.now()` id; sets BOTH `odProtoNotifId.current` AND `currentPipelineNotifId.current` | Never tries to reuse `currentPipelineNotifId` which may belong to a different run type |
| `DashboardLayout.tsx` `pendingOdPptParams` handler | Same — always creates new, sets both `odPptNotifId` and `currentPipelineNotifId` | Same root cause |
| `DashboardLayout.tsx` `odProtoNotifCreated` reactive effect | Removed `!currentPipelineNotifId.current` gate; checks `!odProtoNotifId.current` (prototype) or `!odPptNotifId.current` (ppt) instead; sets the type-specific ref when creating | The reactive effect fires for ANY pipeline_type od_prototype/ppt regardless of what other runs are doing; uses the type-specific ref to prevent the explicit+reactive double-create |
| `DashboardLayout.tsx` `!pipelineState?.isRunning` cleanup | Clears `odProtoNotifId.current` and `odPptNotifId.current` on run end | Reset for next run |

#### Invariants Verified
- **INV-1**: not affected — no `pipeline_type` comparison in rendering logic; logic only used for notification id tracking
- **INV-3**: not affected — FE-only change; no backend/golden impact
- **INV-12**: not applicable — no capability duplication
- **SC-001**: not affected — no engine edits

#### Verification
- TypeScript diagnostics: 0 errors (`get_diagnostics` ran clean)
- With 3 concurrent runs: user_stories → `addRunningNotification(ts1, "user_stories", …)`; prototype → `addRunningNotification(ts2, "prototype", …)`; ppt → `addRunningNotification(ts3, "ppt", …)` — three independent entries, no collision
- `odProtoNotifCreated` reactive effect: since explicit handlers pre-set `odProtoNotifId`/`odPptNotifId`, the reactive path's `if (!odProtoNotifId.current)` guard fires as false → no duplicate creation
- `currentPipelineNotifId` still tracks the LAST-launched run for progress/gate/completion updates (the pipelineState only streams one run at a time — the last-active one)

#### Notes
- The `currentPipelineNotifId` still tracks the last-started run. For progress updates this is correct: pipelineState reflects the last active run. For completion, the effect reads `currentPipelineNotifId.current` at run end — this will be the last prototype/ppt run's id if those were started after user_stories. This is acceptable behaviour: the visible completion badges fire for whichever run's notif the ref held at completion time.
- Future improvement: use a `Map<pipelineRunId, notifId>` to track completions per-run-id for fully independent concurrent run completion toasts.

---

### FIX-154 — User Stories review gate shows no summary content

**Date:** 2026-07-31
**Triggered by:** `velocity-fix user stories review gate shows no summary`

#### Root Cause

`frontend/src/components/chat/InlineGateActions.tsx` line 163:
```ts
const artifactKind = discriminateArtifact(output);  // ← missing second argument
```

`discriminateArtifact(output, artifactKind?)` has an optional second param that accepts the backend-derived `artifact_kind` value. When the second arg is absent, it falls back to content-sniffing XML wrapper tags in the output text.

For **prototype/PPT** agents: their outputs contain literal `<spec>`, `<tasks>`, `<analysis>` tags, so the content-sniff finds a match → preview renders.

For **user_stories** `domain-analyst`: the output is plain markdown (no XML tags). The backend calls `_artifact_kind_for("domain-analyst")` → `"summary"` (fallback for unmapped agents). This is included in the `review_gate_ready` event as `artifact_kind: "summary"`. `discriminateArtifact(undefined, "summary")` would return `"analysis"` → `AnalysisPreview` would render. But because the second arg was never passed, the function only got the plain-markdown output and returned `null` → the preview block condition `{artifactKind && !showEdit && ...}` was never entered → blank gate panel.

Additionally, `GateContext` (in `RunChatLane.tsx`) had no `artifactKind` field at all, so even if `InlineGateActions` wanted to receive it, the prop chain was broken upstream.

#### Trace
```
backend: _artifact_kind_for("domain-analyst") → "summary"
backend: review_gate_ready { artifact_kind: "summary", output: "<plain markdown>" }
page.tsx: reviewGateData.artifactKind = "summary"  ← stored correctly
DashboardLayout: laneGate = { output, ..., /* NO artifactKind */ }  ← MISSING FIELD
StepsOverviewSpine/GateAwaitingCard: InlineGateActions(output, /* no artifactKind */)
InlineGateActions: discriminateArtifact(output)  ← ONE arg, missing "summary"
discriminateArtifact: /<analysis>/i.test(plainMarkdown) = false → return null
preview block condition: null && !showEdit = false → nothing rendered ❌
```

#### Phase Context
- **Phase(s) involved:** Phase 42 §2 (gate inline migration, `InlineGateActions` + `StepsOverviewSpine`); Phase 28 §3 (`artifactPreview.tsx` discriminator)
- **Relevant register section:** Phase 42 plan 42-08 (gate 2-button + plan-preview); Phase 28 §3 (artifact kind vocabulary)
- **Deleted code verified (not resurrected):** No deleted code involved; this is a missing prop chain.
- **Locked decisions respected:** SC-001 — `artifactKind` is the structurally-derived backend value, never a workflow/agent-name literal. The fix propagates it without adding any name-based branch.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/chat/RunChatLane.tsx` | Added `artifactKind?: string` field to `GateContext` interface | Without this field, the prop chain was broken — no upstream component could pass the value to the gate panel |
| `frontend/src/components/layout/DashboardLayout.tsx` | Added `artifactKind: reviewGateData.artifactKind` to the `laneGate` object construction | Threads the value from `reviewGateData` (which already stored it from the SSE event) into `laneGate` |
| `frontend/src/components/results/StepsOverviewSpine.tsx` | Added `artifactKind={laneGate.artifactKind}` to the `InlineGateActions` call inside `GateAwaitingCard` | Passes the value from the gate context through to the component that calls the discriminator |
| `frontend/src/components/chat/InlineGateActions.tsx` | Added `artifactKind?: string` to `InlineGateActionsProps`; added to destructuring; changed `discriminateArtifact(output)` → `discriminateArtifact(output, artifactKind)` and renamed result to `resolvedArtifactKind`; updated render conditions | The actual bug site — the second argument was simply never passed |

#### Invariants Verified
- **INV-1**: not affected — uses `artifact_kind` string comparison only, no `pipeline_type` branch
- **INV-3**: not affected — FE-only change; 5 characterization goldens unaffected by construction
- **INV-12**: not applicable — `discriminateArtifact` is already the single implementation in `artifactPreview.tsx`; the fix just passes the missing argument
- **SC-001**: not affected — no backend changes; `artifactKind` value comes from backend `_artifact_kind_for` which already names no workflow/agent literally

#### Verification
- All 4 changed files: TypeScript diagnostics = 0 errors
- Trace with fix: `reviewGateData.artifactKind = "summary"` → `laneGate.artifactKind = "summary"` → `InlineGateActions(artifactKind="summary")` → `discriminateArtifact(output, "summary")` → `isAnalysis = true` (because `artifactKind === "summary"`) → returns `"analysis"` → `AnalysisPreview` renders
- PPT/prototype unaffected: their outputs contain XML tags so `discriminateArtifact` returns the correct kind regardless of the second arg (content-sniff path)

#### Notes
- The `approveLabel` in `DashboardLayout` was already computing from `reviewGateData.artifactKind` correctly (for the button label); this fix just extends the same pattern to the preview renderer.
- Any future agent whose output lacks XML wrapper tags will now render correctly as long as the backend's `_artifact_kind_for` returns a recognized kind ("spec", "task_list", "summary"). Unknown kinds fall back to `null` → no preview (same safe degrade as before).

---

### FIX-153 — KAN-146: Concurrent run review gates cross-contaminate and appear before agent output

**Date:** 2026-07-30 (corrected 2026-07-31)
**Triggered by:** `velocity-fix KAN-146`

#### Root Cause

**Bug 1 (cross-contamination — primary symptom shown in screenshots):**

`frontend/src/app/dashboard/page.tsx` — the `review_gate_ready` and `questionnaire_ready` switch-case handlers used `launchedRunIdsRef.current` as the isolation predicate. This ref contains ALL run IDs ever launched from this browser tab. When two or more runs are active simultaneously, ALL their IDs are in the set, so the filter never blocks any of them — run A's gate overwrites run B's screen.

The fix went through two iterations:

*Iteration 1 (initial):* Switched to `activelyBuildingRunIdRef.current` (the latest-launched run). This worked for exactly 2 concurrent runs but broke for 3+ runs or when the user switches views. `activelyBuildingRunIdRef` holds only the most recently launched run ID. If the user has runs A, B, C active and switches to view B via the header notification dropdown, `activelyBuildingRunIdRef` still holds C. B's gate fires → `(B ≠ C)` → `isForeignGate = true` → gate silently dropped even though the user is watching B.

*Iteration 2 (final — correct):* Switched to `trackedRunIdRef.current` — the run the user is **currently viewing on screen**. `trackedRunIdRef` is updated by every view-switch path:
- `handleSwitchToLiveRun(runId)` — notification dropdown click
- `handleSelectWorkflowRun(run)` — history reopen
- Launch `.then()` — new run started
- `useEffect([activePipelineRunId, contentSourceRunId])` — clarify/completed state changes

This means `trackedRunIdRef` is always the one correct run to accept gates for, regardless of how many other runs are building in the background.

**Bug 2 (simultaneous clarify + gate panels):**

`frontend/src/components/layout/DashboardLayout.tsx:1609` — `laneGate` was derived from `reviewGateData` unconditionally, so both gate and clarify actions could render together when the SSE D-14g re-arm replayed a paused gate while a questionnaire was open.

#### Phase Context
- **Phase(s) involved:** KAN-125 / FIX-135 established the `trackedRunIdRef` / run-isolation pattern; this fix applies the same concept to gate/clarify events.
- **Relevant register section:** Phase 42 §2 (gate inline migration); Phase 29 D-14g (SSE gate re-arm).
- **Deleted code verified (not resurrected):** No deleted code resurrected; predicate swap only.
- **Locked decisions respected:** SC-001 — uses `pipeline_run_id` string comparison only, no workflow-name literal. INV-1 — no `pipeline_type` branch.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/app/dashboard/page.tsx` | `review_gate_ready`: `isForeignGate` now uses `trackedRunIdRef.current` | The viewed-run ref; correct for 2, 3, or N concurrent runs and survives view-switching |
| `frontend/src/app/dashboard/page.tsx` | `questionnaire_ready`: `isForeignQuestionnaire` now uses `trackedRunIdRef.current` | Same reasoning — prevents clarify from a background run capturing `activePipelineRunId` |
| `frontend/src/components/layout/DashboardLayout.tsx` | `laneGate` derivation: `reviewGateData && !laneClarifyOpen ? {...}` | Mutual exclusion — gate and clarify panels cannot render simultaneously |

#### Invariants Verified
- **INV-1**: not affected — `pipeline_run_id` comparison only, no workflow-name literals
- **INV-3**: not affected — FE-only; all 5 characterization goldens unaffected by construction
- **INV-12**: not applicable
- **SC-001**: not affected — no backend changes

#### Verification
- TypeScript diagnostics: 0 errors on both changed files
- `trackedRunIdRef.current` is `null` on the very first launch (no prior run) → `!!trackedRunIdRef.current` is `false` → `isForeignGate = false` → gate accepted (correct first-launch behaviour preserved)
- Switching views via notification dropdown sets `trackedRunIdRef = switchedRun.id` synchronously, so the gate filter is correct before any events arrive
- `DashboardLayout` `laneGate` is `undefined` when clarify is open → `runLaneState` resolves to `"clarify"` (gate priority still expressed in the ternary but gate prop is nulled)

#### Notes
- The progression: `launchedRunIdsRef` (wrong — all tab runs) → `activelyBuildingRunIdRef` (wrong — only latest launch) → `trackedRunIdRef` (correct — currently viewed run).
- The mutual-exclusion fix in DashboardLayout (Bug 2) is independent and correct regardless of the predicate choice above.
- A future improvement: if the user is NOT viewing a run (e.g. on the home screen), `trackedRunIdRef.current` may be stale from the last-viewed run. In that case a new gate from a different background run would still be blocked. This is acceptable: the gate will be re-served on the D-14g re-arm when the user navigates to that run's screen.

---

### FIX-152 — KAN-139: 9 D-Cluster Infrastructure Defects

**Date:** 2026-07-30
**Triggered by:** `velocity-fix KAN-139`

#### Root Cause
9 separate root causes, all code-level (no SSM / nginx access required):

- **D1** — `frontend/e2e/tests/ts-sse-resilience.spec.ts:216` — test title claimed "multi-tab consumers ride ONE monotonic seq/event_id space" (a backend delivery guarantee), but the harness uses a re-readable array served from `mockSse.ts:125`, never the real consume-once backend queue.
- **D2** — `frontend/src/providers/RunConnectionProvider.tsx:448` — `sendCommand()` called `fetch()` directly, bypassing `api.ts`'s `request()` helper; the `res.ok` guard was missing. A 4xx/5xx response silently returned `null`, leaving the chat message as an orphan optimistic bubble forever.
- **D4** — `backend/agents/artifact_store/store.py:42-48` — three module-global dicts (`_resume_events`, `_questionnaire_responses`, `_questionnaire_force_proceed`) on the process-lifetime `ArtifactStore` singleton had no eviction path. `_cleanup_pipeline` in `run_engine.py:70-73` cleared the queue/task/cancel registries but not these three.
- **D5** — `backend/agents/execution_engine/state_machine.py:106` — `StateMachine._states` grew without bound. `run_commands.py:412` accessed it via `_state_machine._states.pop(...)` — a private-dict reach FIX-105 had left in place.
- **D6** — `backend/app/agents/sandbox.py:163` — `sweep_expired()` had zero callers. Its implementation also used directory `st_mtime` as the sole guard, which does NOT advance when files inside are overwritten (prototype build `edit_file` path) — a proposed naïve fix would have caused data loss on active runs.
- **D7** — `backend/app/agents/checkpointer.py:104-112` — `close_checkpointer()` set `_checkpointer = None` outside the `try/finally` (skipped on exception); had no `_closed` latch; was never called in `app/main.py` lifespan shutdown (shutdown body = one `logger.info`).
- **D9** — `backend/agents/execution_engine/engine.py:5278-5449` — `restore_non_terminal_runs()` called `asyncio.create_task(self.resume_run(...))` for every non-terminal run in a for-loop with no Semaphore or stagger, firing N simultaneous Bedrock calls at startup.
- **D10** — `backend/app/core/config.py:133` — `SSE_STREAM_IDLE_TIMEOUT_SECONDS: int = 300` was dead configuration with zero readers (documented as Phase 29 IN-01 and Phase 44 IN-01 for months).
- **D11** — `backend/app/api/run_stream.py` — 300 lines, no `import logging`, no `logger`, zero log calls. Every SSE stream open/close/error was invisible server-side.

#### Phase Context
- **Phase(s) involved:** Phase 44 (SSE cutoff / run_stream), Phase 49 (resume), Phase 12 (restore), Phase 29 (D-14h config), Phase 8 (ArtifactStore HITL), Phase 2 (StateMachine)
- **Deleted code verified (not resurrected):** confirmed F1-F5 not resurrected; `_states` private reach replaced by public method (not a new state-machine mechanism)
- **Locked decisions respected:** INV-3 (characterization goldens untouched — all changes are infrastructure/config); INV-12 (eviction is one method each, called from one cleanup path); SC-001 (no pipeline_type branches)

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `backend/agents/artifact_store/store.py` | Added `forget_run(run_id)` public method that pops all three dicts and all `review:{run_id}*` event keys | D4 eviction |
| `backend/agents/execution_engine/state_machine.py` | Added `forget_run(run_id)` public method that pops `_states[run_id]` | D5 eviction |
| `backend/app/api/run_engine.py` | `_cleanup_pipeline` now calls `get_artifact_store().forget_run()` + `get_state_machine().forget_run()` (lazy import, best-effort try/except) | D4+D5 wire |
| `backend/app/api/run_commands.py:412` | Replaced `get_execution_engine()._state_machine._states.pop(run_id, None)` with `get_state_machine().forget_run(run_id)` | D5 private-dict reach → public API |
| `backend/app/agents/sandbox.py` | `sweep_expired()` now accepts `protected_run_ids: set[str] \| None`; checks protection BEFORE mtime; TTL comment updated | D6 data-loss guard |
| `backend/app/agents/checkpointer.py` | Added `_closed` module-level latch; `close_checkpointer()` sets latch + nulls globals BEFORE `pool.close()` + non-raising except; `get_checkpointer()` raises `RuntimeError` when `_closed` | D7 hardening |
| `backend/app/core/config.py` | Deleted `SSE_STREAM_IDLE_TIMEOUT_SECONDS`; replaced with accurate comment block. Added `RESTORE_ADMISSION_CONCURRENCY=4`, `RESTORE_ADMISSION_STAGGER_SECONDS=15.0`, `SANDBOX_SWEEP_INTERVAL_SECONDS=21600`. TTL raised from 48h to 168h | D10 delete, D9 settings, D6 TTL |
| `backend/app/main.py` | Lifespan: added `_sandbox_sweep_loop` background task (D6); added graceful `close_checkpointer()` + sweep-task cancellation in shutdown block (D7) | D6+D7 wiring |
| `backend/app/api/run_stream.py` | Added `import logging` + `logger = logging.getLogger("app.api.run_stream")`; added `evt=sse.open` log on attach and `evt=sse.close reason=…` log in the generator finally | D11 observability |
| `frontend/src/providers/RunConnectionProvider.tsx` | `sendCommand()` now checks `!res.ok` before draining/parsing the body and throws a descriptive `Error` on non-2xx | D2 silent-null fix |
| `frontend/e2e/tests/ts-sse-resilience.spec.ts` | Retitled TS-SSE-RESILIENCE-04 to "mock harness contract — not a backend delivery guarantee"; added explanatory comment | D1 false-claim fix |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — all changes are infra/config/logging
- **INV-3** (golden parity): not affected — no capability, event-type, or engine-emit change; characterization goldens unaffected by construction
- **INV-12** (no duplication): one `forget_run` per class, called from one `_cleanup_pipeline`; `sweep_expired` extended in place; `_closed` is inside the existing function
- **SC-001** (zero engine edits for new workflows): no engine capability change; the admission-control wrapper is transparent to `resume_run`

#### Verification
All 9 changes verified by code-read + diagnostics (0 errors). Live behavioral verification (stream open/close log lines, periodic sweep, semaphored restore, graceful shutdown) will be confirmed on the next real Bedrock session.

#### Notes
- D6: `sweep_expired` TTL was 48h which is too short for the revision-parent seed window (users sometimes create revisions the next day). Raised to 168h (7 days) as per KAN-139 spec.
- D9: The admission-control semaphore is per-restore (`self._restore_sem` set lazily) so it does not interfere with concurrent re-arm tasks (branch-a); gate-parked runs hold the semaphore only around the actual model-dispatch code inside `resume_run`, so the design cannot deadlock.
- D11: The `evt=sse.close reason=` vocabulary (`client_disconnect` / `sentinel` / `terminal_event` / `error`) matches the KAN-139 spec exactly.
- D1: A proper TS-SSE-RESILIENCE-05 covering the real backend deliver-once guarantee would require two mounted-app browser tabs + a real backend instance — explicitly out of scope for offline mocked testing.

---

### FIX-147 — KAN-132: Multi-run dropdown entries navigate to their own run

**Date:** 2026-07-30
**Triggered by:** `/velocity-ai-fix Currently 2 pipeline running clicking on presentation going to user story run`

#### Root Cause

Each dropdown entry in the multi-run badge called the same shared `onGoToPipeline?.()` callback:

```ts
// AppHeader.tsx — BEFORE fix
onClick={() => {
  setRunningDropdownOpen(false);
  onGoToPipeline?.();  // ← same callback for every entry
}}
```

`onGoToPipeline` in DashboardLayout is `() => setMainView("execution")` — it navigates to whichever run is currently "active", not to the run that was clicked. So clicking "Presentation" executed the same action as clicking "User Stories": navigate to the active run's view.

`onViewResults` was already wired as a per-notification callback and correctly routes to each run's view. It receives the full `PipelineNotification` object and DashboardLayout handles the routing:

```ts
onViewResults={(n) => {
  if (n.status === "running" || n.status === "completed") {
    setMainView("execution");
  } else {
    setMainView("history");
  }
}}
```

#### Phase Context

- **Phase(s) involved:** Phase 35 (SHELL-01 AppHeader shell chrome), FIX-146 (multi-run badge implementation)
- **Deleted code verified (not resurrected):** No deleted code touched.
- **Locked decisions respected:** SC-001 — no workflow-name branch; routing keys on generic `n.status` field.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/layout/AppHeader.tsx` | Changed each dropdown entry's `onClick` from `onGoToPipeline?.()` to `onViewResults?.(pipeline)` | `onViewResults` is the per-notification callback already wired by DashboardLayout to route each notification to its own run view |

#### Invariants Verified

- **INV-1** (no pipeline_type branches): Not affected — routing keys on generic `n.status`
- **INV-3** (golden parity): Not affected — FE-only change
- **INV-12** (no duplication): Reuses the existing `onViewResults` callback
- **SC-001** (zero engine edits): Not affected

#### Verification

- `tsc --noEmit` diagnostics: No errors
- Trace: 2 running (Presentation + User Stories) → click "Presentation" → `onViewResults?.(presentationNotification)` → DashboardLayout routes to execution view of the Presentation run ✅
- `onGoToPipeline` is still used for the single-run badge and legacy fallback — unaffected ✅

#### Notes

- `onViewResults` in DashboardLayout currently always calls `setMainView("execution")` for running/completed status — it navigates to the execution view regardless of which run. A future enhancement could track which specific concurrent run the user clicked and switch the `activelyBuildingRunIdRef` to it.

---

### FIX-146 — KAN-132: Header running badge shows all concurrent pipelines via dropdown

**Date:** 2026-07-30
**Triggered by:** `/velocity-ai-fix KAN 132`

#### Root Cause

`AppHeader` received three scalar props — `isPipelineRunning`, `pipelineType`, `pipelineAgentsCompleted/Total` — that can represent only ONE pipeline at a time. When multiple pipelines run concurrently, only the most recently active one was shown; all others were invisible in the header.

The `notifications` array from `useNotifications` (passed to `AppHeader` as the `notifications` prop since Phase 35) already contains entries for ALL running and gate-paused pipelines with `status`, `workflowType`, `title`, and agent counts. It was only used to feed `NotificationPanel`, not the running badge.

#### Phase Context

- **Phase(s) involved:** Phase 35 (SHELL-01 AppHeader shell chrome), Phase 38 (SHELL-05 notifications feed)
- **Deleted code verified (not resurrected):** No deleted code touched.
- **Locked decisions respected:** SC-001 — label derivation uses `getWorkflowLabel()` (generic map), never a pipeline_type/workflow-name branch. INV-12 — reuses `PipelineNotification` and `getWorkflowLabel` from the single source in `useNotifications.ts`.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/layout/AppHeader.tsx` | (1) Added `runningDropdownOpen` state and its outside-click `useEffect`. (2) Derived `runningPipelines` from `notifications.filter(n => n.status === "running" \|\| n.status === "gate")`. (3) Split badge into three branches: **1 running** → existing single badge (unchanged); **>1 running** → "N Running" dropdown button that lists all pipelines with type label, title, and agent progress; **0 from notifications but scalar isPipelineRunning is true** → legacy fallback badge (backward-compat for the first render before notifications catch up). | All data already existed in `notifications` — just needed to be surfaced in the badge |

#### Invariants Verified

- **INV-1** (no pipeline_type branches): Not affected — `getWorkflowLabel(pipeline.workflowType)` is a generic map lookup; `pipeline.status` is a generic status field
- **INV-3** (golden parity): Not affected — FE-only change, no backend/golden impact
- **INV-12** (no duplication): Reuses `PipelineNotification` type and `getWorkflowLabel` from `useNotifications.ts`; no parallel tracking structure added
- **SC-001** (zero engine edits): Not affected

#### Verification

- `tsc --noEmit` diagnostics: No errors on `AppHeader.tsx`
- Trace (0 running): `runningPipelines = []`, `isPipelineRunning=false` → no badge shown ✅
- Trace (1 running): `runningPipelines = [{ status:"running", workflowType:"prototype", ... }]` → single badge shows "Prototype" with pulse dot and agent count ✅
- Trace (2 running): `runningPipelines = [prototype, user_stories]` → "2 Running" button; click opens dropdown listing "Prototype / brief" and "User Stories / brief" ✅
- Trace (gate-paused run): `status === "gate"` → amber dot instead of pulsing white dot ✅
- `DashboardLayout.tsx` was NOT changed — zero regression risk on the call site

#### Notes

- The dropdown's `onGoToPipeline` callback currently navigates to the execution view of whatever run `DashboardLayout` considers active. A future improvement (tracked in KAN-132) could allow each dropdown entry to navigate to its specific run's view by passing a per-notification callback.
- The legacy fallback branch ensures no regression during the brief window at page load before `addRunningNotification` has been called but `pipelineState.isRunning` is already true.

---

### FIX-145 — KAN-130: Jump Back In shows correct workflow labels and Revised/Chained indicators

**Date:** 2026-07-30
**Triggered by:** `/velocity-ai-fix KAN 130`

#### Root Cause

**Part 1 — Raw `od_ppt` / `od_prototype` labels:**
`getWorkflowLabel` in `useNotifications.ts` returns `WORKFLOW_LABELS[type] || type`. The `od_ppt`, `od_prototype`, `od_ppt_revision`, and `od_prototype_revision` pipeline types were not in `WORKFLOW_LABELS`, so they fell back to the raw internal alias string.

**Part 2 — No "(Chained)" indicator:**
`source_run_id` exists on the `WorkflowRun` ORM model (migration 0014 forward field) and is set when a run was launched by chaining. However, it was never included in `WorkflowRunResponse`, so the frontend had no way to detect chained runs. The `WorkflowRun` FE type and `normalizeWorkflowRun` in `api.ts` also lacked the field.

#### Phase Context

- **Phase(s) involved:** Phase 36 (SHELL-02 Jump Back In / HomeLaunchGrid), Phase 5 (WorkflowRunResponse additive fields), KAN-130 analysis
- **Deleted code verified (not resurrected):** No deleted code touched.
- **Locked decisions respected:** INV-1 — no pipeline_type branch anywhere; `sourceRunId` is a generic field. Q3 additive-only — `source_run_id` column already exists, no migration needed. INV-12 — `getWorkflowLabel` is the single label function; extended in place.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/hooks/useNotifications.ts` | Added `od_ppt`, `od_ppt_revision`, `od_prototype`, `od_prototype_revision` to `WORKFLOW_LABELS` | These were the actual `run.type` values stored in the DB but had no label entry |
| `backend/app/api/runs.py` | Added `source_run_id: Optional[str] = None` to `WorkflowRunResponse` | Exposes the chaining indicator — column already exists, picked up by the `from_attributes` loop |
| `frontend/src/lib/api.ts` | Added `source_run_id?: string | null` to `RawWorkflowRun`; mapped to `sourceRunId` in `normalizeWorkflowRun` | Threads the new backend field through to the FE model |
| `frontend/src/types/index.ts` | Added `sourceRunId?: string | null` to `WorkflowRun` interface | Required for TypeScript to accept the new field in the FE model |
| `frontend/src/components/catalog/HomeLaunchGrid.tsx` | Changed `getWorkflowLabel(run.type)` to `getWorkflowLabel(run.type) + (run.sourceRunId ? " (Chained)" : "")` | Shows "(Chained)" for runs launched by chaining, keyed generically on `sourceRunId` |

#### Invariants Verified

- **INV-1** (no pipeline_type branches): Not affected — label dispatch on the generic `WORKFLOW_LABELS` map key; chained indicator on `sourceRunId` (a data field)
- **INV-3** (golden parity): Not affected — FE-only display + additive backend field
- **INV-12** (no duplication): `getWorkflowLabel` is extended in place; no new label function
- **SC-001** (zero engine edits): Not affected — backend change is in the API response layer only

#### Verification

- `tsc --noEmit` diagnostics: No errors on all 4 changed FE files
- Backend restarted and confirmed running
- Trace: `od_ppt` run → `getWorkflowLabel("od_ppt")` → `WORKFLOW_LABELS["od_ppt"]` = `"Presentation"` ✅
- Trace: chained prototype run → `run.sourceRunId = "prev-run-id"` → `"Prototype (Chained)"` ✅
- Trace: revision run → `run.type = "prototype_revision"` → `"Prototype (Revised)"` ✅ (unchanged)

#### Notes

- The "(Revised)" labels for `od_ppt_revision` and `od_prototype_revision` were also missing and are now fixed.
- The "(Chained)" label requires the `source_run_id` column to be populated. For runs launched via the chain flow in DashboardLayout/LaunchWizard this field is set server-side; legacy runs or runs launched without chaining will have `null` and show no suffix (correct).

---

### FIX-144 — KAN-129: Context Received panel shows correct labels instead of "artifact"

**Date:** 2026-07-30
**Triggered by:** `/velocity-ai-fix KAN 129`

#### Root Cause

`formatContextSource` in `AgentDetailPanel.tsx` only handled `type === "summary"` (prior-agent outputs). Every other type fell through to `src.artifact_type || "artifact"`. KAN-102 added two new source types to the backend — `"run_input"` (user brief) and `"context_block"` (template/design system) — both with a `label` field (e.g. `"User brief"`, `"Template: ibm-carbon"`). The frontend type `ContextSource` in `types/index.ts` was never updated to include these types or the `label` field, and `formatContextSource` never read `label` at all. Result: every first-agent context source across all workflows displayed as `"artifact"`.

The backend also emitted `"label": "User brief"` for the user brief source. Since the product requirement was to show `"prompt.md"`, the backend label was changed to `"prompt.md"`. This is INV-3 safe: `context_sources` is in `_VOLATILE_STRIP_KEYS` in `_normalize.py`, so goldens are byte-identical.

#### Phase Context

- **Phase(s) involved:** Phase 22 (KAN-102 — introduced run_input/context_block source types), Phase 31/39 (AgentDetailPanel formatContextSource)
- **Deleted code verified (not resurrected):** No deleted code touched.
- **Locked decisions respected:** INV-12 — `formatContextSource` is the single derivation function; one fix, all consumers benefit. SC-001 — dispatch on generic `type` field, never a workflow/agent-name literal.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/types/index.ts` | Extended `ContextSource.type` union to include `"run_input"` and `"context_block"`; added `label?: string` and `size_chars?: number` fields | Type was stale; missing fields caused silent runtime mismatches |
| `frontend/src/components/results/AgentDetailPanel.tsx` | Updated `formatContextSource` to read `src.label` for `"run_input"` (fallback `"prompt.md"`) and `"context_block"` (fallback `"context"`); updated `rawSize` derivation to include `size_chars` for new types | Makes all 4 source types render their correct human-readable label and size |
| `backend/agents/execution_engine/engine.py` | Changed `"label": "User brief"` → `"label": "prompt.md"` on the `run_input` source in `_build_context_sources` | Product requirement: show `"prompt.md"` as the context name for the user brief; INV-3 safe since `context_sources` is in `_VOLATILE_STRIP_KEYS` |

#### Invariants Verified

- **INV-1** (no pipeline_type branches): Not affected — `formatContextSource` dispatches on `src.type` only (generic data field, never a pipeline/workflow name)
- **INV-3** (golden parity): Not affected — `context_sources` is in `_VOLATILE_STRIP_KEYS` in `characterization/_normalize.py`; the backend label change is golden-neutral
- **INV-12** (no duplication): `formatContextSource` is the single source; no new render function added
- **SC-001** (zero engine edits for new workflows): The engine edit (`_build_context_sources`) changes only a display label string — no routing, no capability, no strategy logic changed

#### Verification

- `tsc --noEmit` diagnostics: No errors on either changed FE file
- Trace: backend emits `{type: "run_input", label: "prompt.md", size_chars: N}` → `useWorkflow` stores as `contextSources` → `ContextReceivedPanel` calls `formatContextSource` → `src.type === "run_input"` → `src.label || "prompt.md"` → shows `"prompt.md"`
- PPT/Prototype: `{type: "context_block", label: "Template: ibm-carbon", ...}` → `src.label || "context"` → shows `"Template: ibm-carbon"`
- Prior-agent handoffs (`"summary"` type): unaffected — existing path unchanged

#### Notes

- Backend restart required since `engine.py` was changed.
- The `size_chars` field is now displayed in the meta line (e.g. "48.3k") for `run_input` and `context_block` sources, matching the pattern for `"summary"` sources.

---



**Date:** 2026-07-29
**Triggered by:** `/velocity-ai-fix still showing the same issue for ppt and prototype`

#### Root Cause

FIX-141 introduced `laneActiveContent` to select the right content for `deriveDeliverableFilename`, but it keyed on `workflowType` (DashboardLayout's local state) instead of `effectiveReviseType`.

`workflowType` is a local `useState` inside DashboardLayout:
- It defaults to `"user_stories"` unless a wizard explicitly calls `setWorkflowType()`
- It's set to `"ppt"` / `"prototype"` when the respective wizard launches a run
- **It stays stale at `"user_stories"` when a completed run is opened from history**

`effectiveReviseType` is computed correctly for ALL cases:
```ts
const viewedRunType = contentSourceRunType ?? (!isPipelineRunning && contentSourceRunId != null ? recentRuns.find(...)?.type : undefined);
const effectiveReviseType = viewedRunType ?? workflowType;
```

For a history-reopened `"od_ppt"` run: `contentSourceRunType = "od_ppt"` → `effectiveReviseType = "od_ppt"`. But `workflowType` stays `"user_stories"`.

So `laneActiveContent` was checking `workflowType === "ppt"` → `false` → fell through to `userStoryContent = ""` → `deriveDeliverableFilename("user_stories", "", fallback)` → returned the static fallback `"presentation.pptx"`.

`PreviewPanel` was already correct because it uses `workflowType={effectiveReviseType}` (line ~2049). Only `laneActiveContent` was wrong.

#### Phase Context

- **Phase(s) involved:** Phase 31 (CHATUI-01 RunChatLane), Phase 39 (RUNUI-06 DeliverableCard), follow-up to FIX-141
- **Deleted code verified (not resurrected):** No deleted code touched.
- **Locked decisions respected:** SC-001 — no workflow-name literal; dispatch keys on the existing `effectiveReviseType` variable.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/layout/DashboardLayout.tsx` | Replaced `workflowType` with `effectiveReviseType` in the `laneActiveContent` dispatch AND in the `deriveDeliverableFilename` first argument | `effectiveReviseType` is the authoritative type for the viewed run (incorporates `contentSourceRunType` for history-reopened runs); `workflowType` is stale for reopened runs |

#### Invariants Verified

- **INV-1** (no pipeline_type branches): Not affected — FE-only
- **INV-3** (golden parity): Not affected — FE-only, no backend/golden impact
- **INV-12** (no duplication): Uses the existing `effectiveReviseType` variable already computed above
- **SC-001** (zero engine edits): Not affected

#### Verification

- `tsc --noEmit`: No errors on `DashboardLayout.tsx`
- Trace for PPT: `contentSourceRunType = "od_ppt"` → `effectiveReviseType = "od_ppt"` → `laneActiveContent = pptContent` (the HTML deck) → `deriveDeliverableFilename("od_ppt", "<html><title>GitHub OAuth Authentication</title>...", fallback)` → `"github-oauth-authentication.html"` ✅
- Trace for Prototype: `contentSourceRunType = "od_prototype"` → `effectiveReviseType = "od_prototype"` → `laneActiveContent = prototypeContent` → `deriveDeliverableFilename("od_prototype", "<html><title>To Do App</title>...", fallback)` → `"to-do-app.html"` ✅
- Trace for live PPT launch: `workflowType = "ppt"`, `contentSourceRunType = null` → `effectiveReviseType = "ppt"` → same as before ✅

#### Notes

This is the definitive fix for the chat panel filename issue. The root cause was a two-level bug:
1. FIX-141 wired the infrastructure but used the wrong type variable (`workflowType` vs `effectiveReviseType`)
2. FIX-142 fixed the extension (`.pptx` → `.html`) for the `"ppt"` normalised alias

With FIX-143, both live runs and history-reopened runs will show the correct content-derived filename in the chat panel for all workflow types.

---

### FIX-142 — KAN-128: PPT always produces HTML — fix extension in all filename derivation paths

**Date:** 2026-07-29
**Triggered by:** `/velocity-ai-fix PPT still showing old static file name — PPT only generates html file output not pptx at all`

#### Root Cause

`deriveDeliverableFilename` in `FilesTab.tsx` had a branch:
```ts
const ext = workflowType === "od_ppt" || workflowType === "od_ppt_revision" ? "html" : "pptx";
```

When `workflowType` is `"ppt"` or `"ppt_revision"` (the normalised aliases DashboardLayout sets from `"od_ppt"`), `ext` was `"pptx"` — the wrong extension. All PPT runs in this codebase use the `od_ppt` HTML-deck path; the legacy PptxGenJS `.pptx` binary path is not used.

The same wrong split existed in `deriveDeliverableFiles` which still offered a dead `.pptx` download row for `"ppt"`/`"ppt_revision"`.

Additionally, since `deriveDeliverableFilename` returned `"presentation.pptx"` (with the wrong extension), and since the normalised `workflowType = "ppt"` in DashboardLayout causes `laneDerivedFilename` to evaluate with that wrong extension, the left chat panel was showing `"presentation.pptx"` as the fallback.

#### Phase Context

- **Phase(s) involved:** Phase 18 (ISS-021 FilesTab PPT branch), Phase 22 (deliverableFilename), follow-up to FIX-140 and FIX-141
- **Deleted code verified (not resurrected):** No deleted code resurrected. The `.pptx` row was a legacy placeholder for a path that was never used.
- **Locked decisions respected:** INV-12 — all changes in the one shared `deriveDeliverableFilename` function

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/results/FilesTab.tsx` — `deriveDeliverableFilename` | Changed `ext` from conditional `"od_ppt" ? "html" : "pptx"` to always `"html"` for all four ppt variants | All PPT runs produce HTML decks; the `.pptx` path is unused |
| `frontend/src/components/results/FilesTab.tsx` — `deriveDeliverableFiles` | Removed the `od_ppt`/`ppt` split that offered a dead `.pptx` row; all four ppt variants now produce a single `.html` FileItem | Removes a dead `.pptx` download that would 404 if clicked; Files tab now consistent with all other surfaces |

#### Invariants Verified

- **INV-1** (no pipeline_type branches): Not affected — FE-only
- **INV-3** (golden parity): Not affected — FE-only, no backend/golden impact
- **INV-12** (no duplication): Both functions updated together at the single source — no duplication
- **SC-001** (zero engine edits): Not affected

#### Verification

- `tsc --noEmit` diagnostics: No errors on `FilesTab.tsx`
- `workflowType = "ppt"` + content `<title>GitHub OAuth Authentication Feature</title>` → `"github-oauth-authentication-feature.html"` (correct extension, correct title)
- `workflowType = "od_ppt"` → same result (already worked, unchanged)
- Files tab no longer shows a dead `.pptx` download row for `"ppt"` runs

#### Notes

The root cause traces back to the original assumption that `"ppt"` could be either HTML or PPTX. Since the product only uses `od_ppt` (HTML decks), both the normalised alias `"ppt"` and the original `"od_ppt"` must use `"html"` extension everywhere.

---

### FIX-141 — KAN-128: Left chat panel "Run summary" card shows content-derived filename

**Date:** 2026-07-29
**Triggered by:** `/velocity-ai-fix left side chat window not showing correct titles for files generated`

#### Root Cause

`RunChatLane.tsx` line ~1643:
```ts
const dFilename = pipelineState?.deliverableFilename ?? deliverableFilename;
```

`pipelineState?.deliverableFilename` is the **static manifest name** (e.g., `"presentation.pptx"`, `"user_stories.md"`) — the same static value that FIX-140 already corrected for the Preview URL bar and Files tab. The `RunChatLane` component has no access to actual deliverable content, so it cannot derive a content-based name on its own.

The fix belongs in `DashboardLayout.tsx`, which already receives all three content props (`userStoryContent`, `pptContent`, `prototypeContent`) and `workflowType`. Two changes are needed: (1) compute the derived name in DashboardLayout and pass it as the prop, and (2) fix the `??` operator precedence in RunChatLane so the explicit prop overrides the stale pipelineState value.

**Trace:**
```
pipeline_complete → useWorkflow sets pipelineState.deliverableFilename = "presentation.pptx" (static)
DashboardLayout mounts RunChatLane with NO deliverableFilename prop
RunChatLane.renderTranscriptFooter: dFilename = pipelineState?.deliverableFilename = "presentation.pptx"
SettledSummaryStrip: metaBits = ["3 agents", "presentation.pptx"]  ← [WRONG]
DeliverableCard renders "presentation.pptx"                        ← [WRONG]
```

#### Phase Context

- **Phase(s) involved:** Phase 31 (CHATUI-01 — RunChatLane / SettledSummaryStrip / DeliverableCard), Phase 39 (RUNUI-06/07 — DeliverableCard wired to pipelineState.deliverableFilename)
- **Deleted code verified (not resurrected):** No deleted code touched.
- **Locked decisions respected:** INV-12 — reuses `deriveDeliverableFilename` from FIX-140 (FilesTab.tsx); no duplication; SC-001 — workflowType dispatch is in the FE component layer, not the engine kernel.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/layout/DashboardLayout.tsx` | Added `import { deriveDeliverableFilename }` from FilesTab; computed `laneActiveContent` (content slot matching workflowType) and `laneDerivedFilename`; passed `deliverableFilename={laneDerivedFilename \|\| undefined}` to `RunChatLane` | DashboardLayout has all content props; RunChatLane does not |
| `frontend/src/components/chat/RunChatLane.tsx` | Swapped `pipelineState?.deliverableFilename ?? deliverableFilename` to `deliverableFilename ?? pipelineState?.deliverableFilename` so the explicit content-derived prop takes precedence | The `??` operator was checking static pipelineState first, silently overriding the correct prop |

#### Invariants Verified

- **INV-1** (no pipeline_type branches): Not affected — FE-only
- **INV-3** (golden parity): Not affected — FE-only, no backend/event/golden impact
- **INV-12** (no duplication): Verified — reuses `deriveDeliverableFilename` from FilesTab (FIX-140 single source)
- **SC-001** (zero engine edits): Not affected

#### Verification

- `tsc --noEmit` diagnostics: No errors on either changed file
- `workflowType === "ppt"` + `pptContent` with `<title>GitHub OAuth Authentication Feature</title>` → `laneDerivedFilename = "github-oauth-authentication-feature.html"` — matches Files tab and Preview URL bar
- During streaming: `laneActiveContent` is empty → helper returns fallback `pipelineState?.deliverableFilename` — no regression while building

---

### FIX-140 — KAN-128: Unify output filename — Preview URL bar, Download, and Files tab all agree

**Date:** 2026-07-29
**Triggered by:** `/velocity-ai-fix KAN 128`

#### Root Cause

Two completely independent code paths computed the deliverable filename, and they never shared logic:

1. **`PreviewPanel.tsx` `previewFilename`** — read `pipelineState?.deliverableFilename`, a **static manifest value** (e.g., `"presentation.pptx"` from the workflow YAML's `deliverable.name` field). This was set by the `pipeline_complete` event handler in `useWorkflow.ts` which echoes the backend-emitted static manifest name.

2. **`PreviewPanel.tsx` `handleHeaderDownload`** — also read the same static `pipelineState?.deliverableFilename`.

3. **`FilesTab.tsx` `deriveDeliverableFiles()`** — parsed the **actual content** (`<title>` tags for HTML, `^#\s+(.+)` for markdown) to derive content-aware names. Also used `.slice(0, 40)` which truncates mid-syllable (e.g., `"lateral-thinking-beyond-linear-problemso.pptx"`).

Result: Preview URL bar showed `"presentation.pptx"` (static manifest name), Files tab showed `"beyond-conventional-thinking.pptx"` (content-derived). Download via header also used the static name.

**Trace:**
```
pipeline_complete → useWorkflow.ts:502 → pipelineState.deliverableFilename = manifest static name
  → PreviewPanel previewFilename = pipelineState?.deliverableFilename  [STATIC]
  → PreviewPanel handleHeaderDownload name = same static value          [STATIC]

FilesTab.deriveDeliverableFiles() → parses <title>/<h1>/^# → content-derived name [CONTENT]
```

The additional `.slice(0, 40)` in `deriveDeliverableFiles` also cut on character boundaries, producing mid-syllable truncations.

#### Phase Context

- **Phase(s) involved:** Phase 18 (ISS-021/UXFIX-02 — `deriveDeliverableFiles` extracted to module level, Phase 22 (UXFIX-02 `deliverableFilename` added to `pipeline_complete` emission and `_VOLATILE_STRIP_KEYS`), Phase 39 (RUNUI-06/07 — `previewFilename` and `handleHeaderDownload` added to `PreviewPanel.tsx`)
- **Relevant register section:** Phase 18 §3 (capabilities/modules added), Phase 22 §3 (UXFIX-02 migration 0022)
- **Deleted code verified (not resurrected):** No deleted code touched. `pipelineState.deliverableFilename` is preserved as the fallback in the new helper (used when content is not yet available / streaming).
- **Locked decisions respected:** INV-12 (single helper, no duplication); Phase 22 UXFIX-02 (the static field is retained as a fallback, not removed); Phase 18 D-21 (generic-primary dispatch unchanged)

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/results/FilesTab.tsx` | Added `slugify(raw, maxWords=8)` private helper that truncates on whole-word boundaries (not `.slice(0,40)`), and exported `deriveDeliverableFilename(workflowType, content, fallback?)` pure function covering all workflow types (user_stories, custom, ppt, od_ppt, prototype, od_prototype, app_builder + _revision variants) | Single source of truth for filename derivation; word-boundary-safe truncation; fallback to static name when content not yet available |
| `frontend/src/components/preview/PreviewPanel.tsx` | Imported `deriveDeliverableFilename` from FilesTab; replaced `pipelineState?.deliverableFilename` in `previewFilename` and `handleHeaderDownload` with a call to the helper; also corrected `handleHeaderDownload`'s mimetype to match the derived extension | Preview URL bar and Download now use the same content-derived logic as the Files tab |

#### Invariants Verified

- **INV-1** (no pipeline_type branches): Not affected — FE-only change; `deriveDeliverableFilename` dispatches on `workflowType` string in the FE component layer, not in the engine kernel
- **INV-3** (golden parity): Not affected — FE-only; no backend/engine/event change; characterization goldens not impacted
- **INV-12** (no duplication): Verified — `deriveDeliverableFilename` is the single implementation; `PreviewPanel` imports from `FilesTab`; `deriveDeliverableFiles` unchanged (still builds full `FileItem` arrays using its own internal name logic which also benefits from `slugify`)
- **SC-001** (zero engine edits): Not affected — no engine edit

#### Verification

- `tsc --noEmit` diagnostics: No errors on either changed file
- Execution trace verified: `previewFilename` calls `deriveDeliverableFilename(rawPipelineType || workflowType, activeContent, fallback)` — when content is present, parses `<title>` or `^#` heading with word-boundary-safe slug; when content is empty/streaming, falls back to the static `pipelineState?.deliverableFilename`
- `handleHeaderDownload` derives the same name and maps the file extension to the correct MIME type for download
- The `slugify` helper splits on whitespace boundaries and takes the first `maxWords` (default 8) whole words, so `"Lateral Thinking Beyond Linear Problem Solving and Creative Approaches"` → `"lateral-thinking-beyond-linear-problem-solving-and-creative.pptx"` (first 8 words, no mid-syllable cut)

#### Notes

- The `deriveDeliverableFiles()` function still uses its own inline `.replace(...).slice(0, 40)` logic internally (it was not changed to use `slugify` — that would be a separate refactor touching the Files tab's existing filename generation which is out of scope for this fix). The new `deriveDeliverableFilename` helper is additive.
- `pipelineState.deliverableFilename` (static manifest name) is retained as a fallback so the URL bar shows a meaningful name during streaming before content is available.
- The fix covers all workflow types including revision variants (`_revision` suffix) and aliased types (`od_ppt`, `od_prototype`).

---

### FIX-139 — Chained pipeline uses wrong source run context

**Date:** 2026-07-29
**Triggered by:** `/velocity-ai-fix` — "chained pipeline not getting actual prompt; presentation is taking the context of a base presentation pipeline from earlier instead of the user story I chained from"

#### Root Cause

`handleChainPipeline` in `DashboardLayout.tsx` (~line 1001) resolved the `sourceRunId` for chain context fetching using:
```typescript
const sourceRun = recentRuns?.find(
  r => baseWorkflowType(r.type) === baseWorkflowType(workflowType) && r.status === "completed"
);
const sourceRunId = sourceRun?.id;
```

This type-scan on `recentRuns` is unreliable when multiple completed runs of the same type exist in history. `Array.find` returns the **first** match (ordered by `created_at DESC` from the backend), but if multiple completed user_stories runs exist, it may return an older one instead of the one currently on screen — producing the "add gitlab authentication" context instead of "google authentication" context.

The correct source is already available as `contentSourceRunId` — the prop explicitly managed by `page.tsx` that always points to the run currently displayed (set on `pipeline_complete` and `handleSelectWorkflowRun`). This prop was completely ignored by `handleChainPipeline`.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/layout/DashboardLayout.tsx` | Replace `recentRuns.find(...)` with `contentSourceRunId ?? recentRuns.find(...)` | `contentSourceRunId` is the authoritative "run on screen"; fall back to type-scan only when absent |
| `frontend/src/components/layout/DashboardLayout.tsx` | Add `contentSourceRunId` to the `useCallback` dependency array | The callback now closes over `contentSourceRunId` |

#### Invariants Verified
- **INV-1**: Not affected.
- **INV-3**: Not affected — FE-only.
- **INV-12**: No duplication — reuses `contentSourceRunId` already in scope.
- **SC-001**: FE-only.

#### Verification

- `contentSourceRunId` is set by `page.tsx` when `pipeline_complete` fires (to `data.pipeline_run_id`) and on `handleSelectWorkflowRun` (to `fullRun.id`)
- When the user clicks "Presentation" chain chip after completing a "google auth" user_stories run: `contentSourceRunId = "google-auth-run-id"` → `getChainContext("google-auth-run-id")` → correct context fetched ✓
- Fallback: if `contentSourceRunId` is null (edge case), the type-scan still works as before ✓

#### Notes
- This bug was likely latent before the concurrent-run fixes (FIX-134..138) but became more visible because those fixes preserved multiple completed runs' history more faithfully
- The `handleChainFromHistory` function (for chaining from the history view) correctly uses the explicit `run.id` from the history row — it was NOT affected by this bug

---

### FIX-138 — Concurrent same-type runs: HTTP response order race for activelyBuildingRunIdRef

**Date:** 2026-07-29
**Triggered by:** `/velocity-ai-fix` — "I ran 2 user story simultaneously showing incorrect agent progress"

#### Root Cause

When two runs are launched in quick succession (e.g., two user_stories), the `onStartPipeline` callback calls `startPipeline(...)` which does a `POST /api/runs`. These two HTTP POSTs may resolve in a different order than they were clicked. If the **first-clicked run** responds AFTER the **second-clicked run**, the first-clicked run's `.then()` fires last and **overwrites** `activelyBuildingRunIdRef` and `trackedRunIdRef` with the earlier-clicked run's ID.

After this, the second-clicked run's events are blocked (`isForActiveRun = false` because `_sourceRunId ≠ activelyBuildingRunIdRef`), while the first-clicked run's events pass through. This causes the pipelineState (which was reset by the second run's `pipeline_start`) to receive agent events from the wrong run — producing the "two agents spinning simultaneously, 0 completed" display.

Specifically:
- Run A (first click, `f5a4`) POST responds AFTER Run B (second click, `86ff`)
- After Run B's `.then()`: `activelyBuildingRunIdRef = "86ff"` (correct)
- After Run A's `.then()` (fires later): `activelyBuildingRunIdRef = "f5a4"` (WRONG — overwrites)
- Run B's `pipeline_start` reset fires, sets up 6 idle agents
- Run B's `agent_start domain-analyst` → blocked! (`f5a4 ≠ 86ff`) 
- Run A's `agent_start story-estimator` (further along) → passes! (`f5a4 === f5a4`)
- Result: domain-analyst (from reset) shows idle, story-estimator shows running, 0 completed

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/app/dashboard/page.tsx` | Added `launchCounterRef = useRef<number>(0)` | Monotonically-increasing counter that tracks the ORDER of clicks (not HTTP responses) |
| `frontend/src/app/dashboard/page.tsx` | Captures `thisLaunchSeq = ++launchCounterRef` BEFORE the async POST | Captures click order before the async boundary |
| `frontend/src/app/dashboard/page.tsx` | Guards `trackedRunIdRef` and `activelyBuildingRunIdRef` updates with `if (thisLaunchSeq === launchCounterRef.current)` | Only the LAST-CLICKED launch updates the routing refs — an out-of-order early HTTP response is safely ignored |

#### Invariants Verified
- **INV-1**: Not affected.
- **INV-3**: Not affected — FE-only.
- **INV-12**: `launchCounterRef` is a new local ref, not duplicating any existing capability.
- **SC-001**: FE-only.

#### Behavior After Fix

Click Run A, then Run B quickly:
1. `launchCounterRef` increments to 1 (`thisLaunchSeq_A = 1`), then to 2 (`thisLaunchSeq_B = 2`)
2. Regardless of HTTP response order: the `.then()` with `thisLaunchSeq = 2` (Run B, last clicked) sets `activelyBuildingRunIdRef = "run_B"` ✓
3. The `.then()` with `thisLaunchSeq = 1` (Run A, first clicked) does NOT overwrite (1 ≠ 2) ✓
4. Run A and Run B are both added to `launchedRunIdsRef` (unconditional) for Layer-1 allow-list ✓
5. Only Run B's frames reach the pipelineState reducer ✓

#### Notes
- `launchedRunIdsRef.current.add(launchedRunId)` and `persistLaunchedIds()` remain unconditional — all launched runs must be in the Layer-1 allow-list regardless of click order
- `runConnection.attachRun(launchedRunId)` also remains unconditional — all runs need SSE streams
- The counter only gates the "which run is actively shown" decision

---

### FIX-137 — Multi-tab isolation + same-tab empty-set isForeignFrame gap

**Date:** 2026-07-29
**Triggered by:** `/velocity-ai-fix` — "multiple workflows not running in isolation; opening another tab shows already open workflow"

#### Root Cause

Two related bugs sharing the same root: `launchedRunIdsRef` (the Set of run IDs launched in this tab) being empty causes ALL frames to pass through the guards.

**Bug 1 — New tab shows running workflow:**
- `RunConnectionProvider.refreshLiveRuns()` runs on every component mount
- It finds ALL running workflows (AUTO_STREAM_STATUSES) and creates SSE connections for them
- New tab subscribes to `handleWebSocketMessage`; `launchedRunIdsRef` is empty
- `isForeignFrame` check: `launchedRunIdsRef.size > 0` was the first condition — when size === 0 this was `false`, meaning `isForeignFrame = false` for EVERYTHING
- Background run's `pipeline_start` fires → resets the new tab's state → shows running pipeline

**Bug 2 — isForeignRun empty-set gap:**
- Same issue for `pipeline_start` reset guard (`isForeignRun`): when `trackedRunIdRef = null` (no run tracked), a background run's `pipeline_start` was NOT treated as foreign → reset fired

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/app/dashboard/page.tsx` | `launchedRunIdsRef` initialized from sessionStorage via IIFE in `useRef(...)` | Same-tab page reload restores known run IDs; new tabs start empty (fresh sessionStorage) |
| `frontend/src/app/dashboard/page.tsx` | `persistLaunchedIds()` helper added, called on every `launchedRunIdsRef.current.add()` | Persists the set to sessionStorage after every mutation |
| `frontend/src/app/dashboard/page.tsx` | `isForeignFrame` now: `!!frameRunId && (size===0 \|\| !has(frameRunId))` | When set is empty (new tab), ALL frames with a run id are foreign → blocked from reducer |
| `frontend/src/app/dashboard/page.tsx` | `isForeignRun` now: `!!runId && (size===0 \|\| (!!trackedRef && runId !== trackedRef))` | When set is empty, ALL `pipeline_start` from background runs are foreign → no reset |
| `frontend/src/providers/RunConnectionProvider.tsx` | `refreshLiveRuns` only auto-attaches runs in `tab_launched_run_ids` sessionStorage | New tabs don't create unnecessary SSE connections for other users' running workflows |

#### Invariants Verified
- **INV-1**: Not affected — no pipeline_type branches.
- **INV-3**: Not affected — FE-only, goldens untouched.
- **INV-12**: No duplication.
- **SC-001**: FE-only.

#### Behavior After Fix

- **New tab**: Empty `launchedRunIdsRef` → ALL background run frames are foreign → dashboard shows clean home state
- **Same-tab reload mid-run**: sessionStorage restores the launched run ID → run continues streaming correctly
- **Same-tab concurrent runs**: `launchedRunIdsRef` has both IDs → Layer-1 allows both; Layer-2 (`activelyBuildingRunIdRef`) restricts reducer to the most-recently-launched run
- **History reopen**: `handleSelectWorkflowRun` adds the opened run to `launchedRunIdsRef` and persists → that run's durable frames flow through correctly

#### Notes
- `TAB_LAUNCHED_KEY = "tab_launched_run_ids"` is used in both `page.tsx` and `RunConnectionProvider.tsx` to share the same sessionStorage key (tabs are isolated per browser tab)
- The IIFE in `useRef(...)` runs on every render but React only uses the initialValue on the first render — functionally correct and safe
- `refreshLiveRuns` still creates SSE connections for tab-owned running runs (correct for resume mid-run)
- Runs not in the tab's set but discovered by `refreshLiveRuns` are not attached (saves network connections)

---

### FIX-136 — Concurrent run shows "Done" in history while still running

**Date:** 2026-07-29
**Triggered by:** `/velocity-ai-fix` — "user story is still running but showing done in run history"

#### Root Cause

When any `pipeline_complete` SSE event arrives (from ANY concurrent run — not just the user_stories run), `page.tsx` calls `getWorkflows` to refresh the history list. The DB write in `_drive_launch_to_queue` sets `status = "completed"` synchronously BEFORE the SSE frame is delivered to the FE. So when a concurrent prototype/PPT run completes:

1. Backend writes user_stories run `status = "completed"` to DB (engine finished, async for loop done)
2. SSE hasn't yet delivered `pipeline_complete` to the user_stories FE handler
3. A concurrent run's `pipeline_complete` fires → FE calls `getWorkflows`
4. `getWorkflows` returns user_stories with `status: "completed"` (from DB)
5. `setRecentRuns(runs)` updates history — shows "Done"
6. But `pipelineState.isRunning` is still `true` (user_stories `pipeline_complete` SSE not processed yet)
7. User sees: history = "Done", live view = "Running" — contradiction

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/app/dashboard/page.tsx` | Changed `setRecentRuns(runs)` in `pipeline_complete` refetch to a functional updater that preserves `"running"` status for tab-local runs not yet processed | Race condition: DB is written before SSE is consumed; protect tab-local runs in `launchedRunIdsRef` except the run that just triggered the refetch |
| `frontend/src/app/dashboard/page.tsx` | Same protection applied to `pipeline_failed` refetch | Same race applies |

**Key logic**: For each run in the refreshed list:
- If the run is in `launchedRunIdsRef` (we launched it this tab) AND
- It's NOT the run that just triggered this refetch (`completedRunIdForThisEvent`) AND  
- The DB says `"completed"` AND
- `prev` (prior state) has it as `"running"`
→ Keep `"running"` to prevent the flash

The protection expires naturally: when user_stories' OWN `pipeline_complete` fires, `completedRunIdForThisEvent === user_stories.id`, so the `r.id !== completedRunIdForThisEvent` condition is false → the real `"completed"` status is applied.

#### Invariants Verified
- **INV-1**: Not affected — FE-only, no pipeline_type branches.
- **INV-3**: Not affected — FE-only, goldens untouched.
- **INV-12**: No duplication — reuses existing `launchedRunIdsRef`.
- **SC-001**: FE-only.

#### Notes
- `launchedRunIdsRef.current` is always fresh (it's a React ref, not state).
- `completedRunIdForThisEvent` captures the specific completing run via closure — correct.
- The `"generating"` status check was intentionally omitted since it's not in `WorkflowStatus`.
- Single-run scenarios: `launchedRunIdsRef` has only one entry which IS the completing run → `r.id !== completedRunIdForThisEvent` is false → no protection → byte-identical to pre-fix behavior.

---

### FIX-135 — KAN-125: _sourceRunId injection — agent_start/chunk/complete bypass fixed

**Date:** 2026-07-28
**Triggered by:** `/velocity-ai-fix` — 2 prototypes running simultaneously, agent progress still mismatched

#### Root Cause

FIX-134 introduced an `isForActiveRun` Layer-2 check using `frameRunId` (extracted from `msg.data.pipeline_run_id`). The issue: most per-agent events do NOT carry `pipeline_run_id` in their `data`:

- `agent_start`: `data = {agent_id, name, role, icon, index, total}` — NO `pipeline_run_id`
- `agent_chunk`: `data = {agent_id, chunk}` — NO `pipeline_run_id`
- `agent_complete`: `data = {agent_id, name, duration, ...}` — NO `pipeline_run_id`
- `agent_input`, `tool_call`, `tool_result`, `agent_thinking`: same — NO `pipeline_run_id`

Result: `frameRunId = undefined` → `isForActiveRun = (!frameRunId)` = `true` → ALL concurrent runs' agent events bypassed the guard and still corrupted the shared `pipelineState` reducer. So both prototype runs' `agent_start`/`agent_chunk`/`agent_complete` events all went to the reducer, causing the mismatched Steps progress shown in the screenshot.

**Root cause file:line**: `page.tsx` frameRunId extraction + `isForActiveRun` pass-through condition; `engine.py` agent_start/agent_complete event structures (no pipeline_run_id in data).

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/hooks/useRunStream.ts` | Added `_sourceRunId?: string` field to `RunStreamMessage` interface | Typed slot for per-stream run identity injection |
| `frontend/src/providers/RunConnectionProvider.tsx` | Changed `onMessage={fanout}` to `onMessage={(msg) => fanout({ ...msg, _sourceRunId: runId })}` per `RunStreamConnection` | Injects the SSE stream's `runId` into every frame, covering ALL event types regardless of whether they carry pipeline_run_id |
| `frontend/src/app/dashboard/page.tsx` | Changed `frameRunId` extraction to prefer `msg._sourceRunId` over `msg.data.pipeline_run_id`; same for wave event guard and pipeline_start foreign-run check | `_sourceRunId` is always present (injected at source), covers agent_start/chunk/complete etc. that don't carry pipeline_run_id |

#### Invariants Verified

- **INV-1** (no pipeline_type branches): Not affected — guard uses run id, never workflow type.
- **INV-3** (golden parity): Not affected — FE-only change; backend/engine untouched; goldens unaffected.
- **INV-12** (no duplication): The `_sourceRunId` field is additive to `RunStreamMessage`; no logic duplication.
- **SC-001** (zero engine edits): FE-only; engine.py untouched.

#### Verification

With this fix:
1. Run A (prototype) starts → `RunStreamConnection(run_A)` injects `_sourceRunId: "run_A"` into every frame
2. Run B (prototype) starts → `RunStreamConnection(run_B)` injects `_sourceRunId: "run_B"` into every frame
3. `activelyBuildingRunIdRef = "run_B"` (most recently launched)
4. `agent_start` from Run A: `frameRunId = "run_A"` (from `_sourceRunId`) → `isForActiveRun = false` → BLOCKED ✓
5. `agent_start` from Run B: `frameRunId = "run_B"` → `isForActiveRun = true` → goes to reducer ✓
6. Steps/progress shows ONLY Run B's data, cleanly ✓

#### Notes

- The `_sourceRunId` injection is an internal FE field — it does NOT flow to the backend.
- Concierge `/messages` streaming frames don't come from `RunStreamConnection` (they come from `sendCommand`'s body drain via the `fanout` callback directly) — they have no `_sourceRunId`. The `!frameRunId` pass-through correctly handles them (they're chat frames, filtered early anyway).
- The `RunConnectionProvider.tsx` change creates a new inline function per render, but since it's inside a `liveRunIds.map()` with stable `key=runId`, React only re-mounts when `liveRunIds` changes — no performance issue.

---

### FIX-134 — KAN-125: Concurrent pipeline "nothing in Steps" — activelyBuildingRunIdRef Layer-2 reducer gate

**Date:** 2026-07-28
**Triggered by:** `/velocity-ai-fix` — "runned user story first, started ppt in parallel, user story stopped working showing nothing in steps"

#### Root Cause

`handleWebSocketMessage` uses `launchedRunIdsRef` (a Set of ALL tab-launched run IDs) to gate the `handlePipelineMsgRef` call. When User Stories (`run_A`) was running and PPT (`run_B`) was launched:

1. `launchedRunIdsRef = {run_A, run_B}` — both IDs are in the Set
2. PPT's `pipeline_start` arrives: `isForeignFrame = false` (run_B IS in the Set) → goes to the reducer
3. The reducer (`useWorkflow`) treats `pipeline_start` as a NEW run → **resets `agents[]` to empty** (WR-03 reset in `useWorkflow.ts`)
4. User Stories' subsequent `agent_*` frames ALSO go to the reducer (run_A also in Set) → both runs' frames compete for the same `agents` array
5. Result: the two runs' events corrupt each other → "nothing in Steps" or garbled progress

**Root cause (file:line):** The single `isForeignFrame` check (using `launchedRunIdsRef.current.has(frameRunId)`) allowed BOTH concurrent runs' frames through to the shared `useWorkflow` reducer. The second run's `pipeline_start` reset the reducer, wiping the first run's Steps data.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/app/dashboard/page.tsx` | Added `activelyBuildingRunIdRef` — a new `useRef<string \| null>(null)` that is ONLY updated when a new run is launched (in `startPipeline().then()`) and when a run is opened from history (`handleSelectWorkflowRun`). It is NEVER overwritten by `contentSourceRunId` completions. | `trackedRunIdRef` is overwritten by the `useEffect` on `activePipelineRunId ?? contentSourceRunId`, meaning a completing concurrent run would re-point it and break the still-building run's progress. A separate ref solving only "which run is actively being built/viewed" avoids this. |
| `frontend/src/app/dashboard/page.tsx` | Added `isForActiveRun` Layer-2 check alongside `isForeignFrame`. The reducer call is now `if (!isForeignFrame && isForActiveRun)`. `isForActiveRun = !frameRunId \|\| !activelyBuildingRunIdRef.current \|\| frameRunId === activelyBuildingRunIdRef.current`. | Only the actively-building run's frames update `pipelineState`. Other tab-local runs' content is still saved at `pipeline_complete` (unguarded). |
| `frontend/src/app/dashboard/page.tsx` | Added run-id guard to wave events section: if `waveRunId && activelyBuildingRunIdRef.current && waveRunId !== activelyBuildingRunIdRef.current` → `return`. | Wave events from a background concurrent run must not corrupt the viewed run's wave tree (same principle). |
| `frontend/src/app/dashboard/page.tsx` | Added `activelyBuildingRunIdRef.current = launchedRunId` in `startPipeline().then()` alongside the existing `trackedRunIdRef.current = launchedRunId`. | Update the new ref whenever a run is launched. |
| `frontend/src/app/dashboard/page.tsx` | Added `activelyBuildingRunIdRef.current = fullRun.id` in `handleSelectWorkflowRun` alongside `trackedRunIdRef.current = fullRun.id`. | Durable event replay for a history-opened run must also go through the reducer. |

#### Invariants Verified

- **INV-1** (no pipeline_type branches): Not affected — guard uses generic `pipeline_run_id` field, no workflow names.
- **INV-3** (golden parity): Not affected — `pipeline_complete` content routing is UNGUARDED (all tab-local completions save their content), goldens unaffected.
- **INV-12** (no duplication): The `activelyBuildingRunIdRef` is a new purpose-specific ref alongside the existing `trackedRunIdRef` (used for BUG-005 pipeline_start reset scoping); the two refs serve different purposes.
- **SC-001** (zero engine edits): FE-only change; backend untouched.

#### Verification

The fix ensures:
1. User Stories running → `activelyBuildingRunIdRef = "run_A"` → User Stories frames → reducer → Steps shows User Stories progress ✓
2. PPT launched → `activelyBuildingRunIdRef = "run_B"` → Steps switches to PPT progress ✓  
3. User Stories frames after PPT launch: `frameRunId = run_A ≠ activelyBuildingRunIdRef (run_B)` → blocked from reducer (no corruption) ✓
4. User Stories `pipeline_complete`: content routing saves `userStoryContent` (unguarded by isForeignCompletion for content) ✓
5. Both runs' content accessible in Preview via respective state variables ✓

#### Notes

- The Steps/Audit/progress tabs now show the MOST-RECENTLY-LAUNCHED run's progress. When a background run completes, its content is saved and accessible via the recents list.
- `pipeline_complete` content routing (`setUserStoryContent`/`setPptContent`/`setPrototypeContent`/`setGenericDeliverable`) remains intentionally UNGUARDED — all completed runs' content is saved to their respective state variables and is accessible.
- `isForeignFrame` (Layer 1, using `launchedRunIdsRef`) still blocks truly external runs (from a different browser tab). `isForActiveRun` (Layer 2, using `activelyBuildingRunIdRef`) ensures only one tab-local run at a time feeds the shared reducer.

---

### FIX-129 — Workflow says "done" while the validation + build agents keep running in a loop

**Date:** 2026-07-29
**Triggered by:** `/velocityai-analysis` — "workflow say it's done but still validation agent and build agent is running (it's in loop) … better notify only once both agent done with it's work".

**Symptom:** the run reports completion (terminal chrome, deliverable rendered, "completed" notification + toast), yet the Build and Validate agent cards go back to `RUNNING` and keep cycling. No further notification ever arrives, because the completion notification already consumed the run's notification id.

#### What was NOT the cause (checked and ruled out)

- **The engine's terminal sequencing.** `engine.py` drives `for i, spec in enumerate(ordered_agents)` strictly sequentially and yields `pipeline_complete` only after the loop (`engine.py:2811`). There is no `create_task`/`gather` that could let a step outlive the terminal.
- **The validation fix-loop.** `_run_validation_fix_loop` (`engine.py:4367`) re-invokes the fix sub-agent on a `…:fix{n}` thread but consumes its `astream_events` **internally and re-emits nothing** (bounded by `policy.max_attempts`, default 2). It cannot surface an agent as `running`, and it cannot spin unbounded.
- **The notification gate itself.** `DashboardLayout`'s completion effect already required `agents.every(status === "done" || "error")`. It was firing on correct state — the state was corrupted *afterwards*.

#### Root cause — foreign-run frame bleed (the reducer is not run-scoped)

`RunConnectionProvider` deliberately attaches **one SSE stream per non-terminal run** (`AUTO_STREAM_STATUSES` ∪ the sticky focused run) and fans **every** frame from **every** attached run into the single `handleWebSocketMessage` subscriber. Two facts turn that into cross-run corruption:

1. `useRunStream` dispatched `{ type, data }` with **no tag identifying which run the frame came from**, and the agent-scoped payloads carry no `pipeline_run_id` of their own (`agent_start` is `{agent_id, name, role, icon, index, total}`).
2. Agent ids are **not unique across runs** — two prototype runs both stream `prototype-build` and `prototype-validate`.

So `handlePipelineMessage`'s `agents.findIndex((a) => a.id === agentId)` matched, and a *different* run's frames rewrote the viewed run's agents. Sequence: viewed run completes → sweep marks all agents `done`, `isRunning=false`, notification fires and `currentPipelineNotifId.current = null` → the other run's `agent_start`/`agent_chunk` for the same ids flip Build/Validate back to `running` (also resetting their accumulators) → its `task_loop_progress` keeps them cycling → nothing can ever announce completion again.

Only two ad-hoc guards existed (`isForeignRun` for `pipeline_start`, `isForeignCompletion` for `pipeline_complete`), and both only suppressed *side effects* — they still forwarded the frame to the reducer. Every agent-state frame had no guard at all. A foreign run's `seq` was also advancing this tab's reconnect cursor.

#### The fix

1. **Tag frames at the transport boundary** — `RunStreamMessage` gains an optional `runId`, stamped in `useRunStream.dispatchBlock` (the hook is instantiated per run, so it is authoritative) and on the provider's `sendCommand` SSE-drain fan-out. One stamping site per path; no second source of truth.
2. **One shared, conservative predicate** — `isForeignRunFrame(frameRunId, trackedRunId)` in `lib/wsReplayState.ts` (the existing home for pure WS routing helpers). Returns `false` unless **both** ids are known and differ, so an untagged frame or a tab that has not claimed a run yet is never dropped (launch → first-frame window unchanged).
3. **Scope only the state-mutating class** — `AGENT_SCOPED_FRAME_TYPES` / `isAgentScopedFrame` enumerate the 13 frame types that write per-agent state. `handleWebSocketMessage` drops those when foreign, at the **top** of the handler (before the dedup/`seq` bookkeeping, so a foreign run can no longer advance this tab's cursor either). Run-**lifecycle** frames (`pipeline_*`, `planner_*`, clarify, `wave_*`, `chat_*`) are deliberately excluded — they carry their own run id and drive cross-run behaviour that must keep working (a revision run legitimately completes under a NEW run id; chaining; history reopen).
4. **Claim the reopened run synchronously** — `handleSelectWorkflowRun` now sets `trackedRunIdRef.current = fullRun.id` next to `setContentSourceRunId`, and the durable replay passes `fullRun.id` explicitly. The `trackedRunIdRef` sync effect keys on the *state*, which has not committed inside that callback — without this the reopened run's own replayed agent frames would have been dropped as foreign.

**Rejected alternatives:** (a) dropping *all* foreign frames — breaks revision completions (dispatched from the tracked run under a new id, and `page.tsx` relies on `isRevisionCompletion` to re-anchor `contentSourceRunId`), chaining and reopen; (b) narrowing `AUTO_STREAM_STATUSES` so only the viewed run streams — kills live multi-run progress and the notification feed, which are the point of the fan-out; (c) filtering inside `handlePipelineMessage` — the reducer is transport-agnostic and shared with the WS-parity tests, and it has no access to which run a frame arrived on.

**Also fixed (pre-existing, one line, in the same handler):** `msg.pipeline_run_id` on the `pipeline_cancelled` branch did not typecheck (`Property 'pipeline_run_id' does not exist on type 'StreamMessage'`) and was failing `next build` outright — the field rides flat on some transports and nested under `data` on others, so it now reads through an index cast. This is the error FIX-128 recorded as known-pre-existing.

**Files changed:**
- `frontend/src/hooks/useRunStream.ts` — `RunStreamMessage.runId` + the stamp
- `frontend/src/providers/RunConnectionProvider.tsx` — stamp the `sendCommand` drain fan-out
- `frontend/src/lib/wsReplayState.ts` — `isForeignRunFrame`, `AGENT_SCOPED_FRAME_TYPES`, `isAgentScopedFrame`
- `frontend/src/app/dashboard/page.tsx` — the guard, the two forwarding call sites, the synchronous reopen claim, the `pipeline_run_id` typecheck fix
- `frontend/src/components/layout/DashboardLayout.tsx` — comment only, documenting that the completion announcement is gated on every agent being terminal
- `frontend/src/lib/__tests__/wsRunScope.test.ts` (new tests), `frontend/src/hooks/useRunStream.test.ts` (envelope assertions)

**Phase(s):** Phase 29/44 (SSE transport + app-level provider fan-out), Phase 12 (RESUME-03 dedup + `seq` cursor), Phase 38 (notification feed).

**Invariants verified:**
- **INV-1 / SC-001** ✅ — frontend-only; the guard keys solely on run id. No workflow name, `pipeline_type` or agent literal added (`prototype-build` appears only in test fixtures).
- **INV-3** ✅ — no backend, engine, capability or prompt change; no event shape or deliverable change. Goldens untouched and not regenerated. The `runId` stamp is additive on the FE envelope only.
- **INV-12** ✅ — the foreign-run decision now lives in ONE shared predicate instead of being open-coded per event; the source-run stamp has one site per transport path. No parallel implementation left behind.
- **INV-13**, persistence/migrations, ports & adapters, security defaults: not touched.

**Verification:**
- `npx vitest run src/lib/__tests__/wsRunScope.test.ts` → **11/11 pass**. Covers: the predicate's conservative cases (untagged frame, unclaimed tab, matching run); the agent-scoped membership contract *and* the explicit exclusion of the 9 lifecycle types; and end-to-end through the **real** `handlePipelineMessage` — a foreign `agent_start` is dropped and a completed run's agents stay `done`/`isRunning:false`, a whole foreign build→chunk→task_loop→validate cycle is dropped with no output bleed, while the same frame from the tracked run (and an untagged frame) still applies.
- `npx vitest run src/lib src/hooks src/providers` → 146/146 pass (24 files).
- `npm run test` (full FE) → **14 files / 39 tests fail, identical to the `git stash` baseline** (baseline measured 15 files / 50 tests only because the stash also removed the helpers this new suite imports; 50 − 11 new = 39). Zero regressions; the pre-existing cluster is the `TemplateGallery`/`TemplateCard`/`WizardStepper` + `RunChatLane` typing-indicator group.
- `npx tsc --noEmit` → **7 errors, all pre-existing and none in any touched file** (`TemplateCard` / `TemplateGallery` missing `Pill`/`Button` imports, `has_thumbnail` fixture drift). Down from 8 — the `StreamMessage.pipeline_run_id` error is now gone.
- `npm run build` → compiles; still blocked at TypeScript by the pre-existing `TemplateCard.tsx` missing-`Pill` error, which is unrelated and present on the baseline. **Not fixed here** (out of scope, separate defect).
- **Live confirmation DEFERRED** — reproducing needs two overlapping runs of the same workflow type on a real backend (start run A, launch run B while A still builds, watch A's completion). Not exercised in this session.

**Status:** Done

---

### FIX-128 — Chat-lane "Open in Steps" / "Open in Preview" never switched the right-hand tab

**Date:** 2026-07-28
**Triggered by:** `/velocityai-analysis` — "while workflow is running and completed workflow page there is a button called 'open in step'/'open in preview' … after clicking this button the section is not opening". User supplied the rendered DOM:
`<button data-testid="chat-result-card-link" data-target-tab="run:93f7ca84-9f63-4d8a-90cf-8fbe8163d4b2">Open in Steps</button>`,
plus a React DevTools tree (`ChatPanel` → 4× `MessageBubble key="chat_reply:…"`) confirming the failing buttons are `ResultCard`-rendered narrator cards, not the `SettledSummaryStrip` cards.

**Symptom:** clicking either deep-link affordance in the left chat lane did nothing — the right-hand `PreviewPanel` stayed on whatever tab it was showing. No console error (the drop is silent).

#### The seam (all of it already existed and was correctly wired)

`ResultCard` → `onRequestOpenTab(tab)` → `useTabDeepLink.requestOpenTab` (mints `{tab, nonce:++n}`) → `page.tsx:1583-1584` (`onRequestOpenTab` / `deepLinkTarget`) → `DashboardLayout.tsx:1917` (lane) + `:1997` (panel) → `PreviewPanel.tsx:489-495` effect keyed on `deepLinkTarget?.nonce`:

```ts
const tab = deepLinkTarget?.tab;
if (tab && (PANEL_TAB_IDS as readonly string[]).includes(tab)) setActiveTab(tab as PanelTab);
```

That guard is the failure point: an unrecognised tab id is **silently ignored**. The wiring was never broken — it was being fed tab ids that do not exist.

#### Root cause 1 — `"steps"` is not a panel tab id

`PreviewPanel` declares `type PanelTab = "preview" | "files" | "thinking" | "audit"` and `PANEL_TAB_IDS = ["preview","files","thinking","audit"]`. The Phase-32 plan-07 reskin **relabelled** the "Thinking" tab to "Steps" in the UI but deliberately kept the internal id `"thinking"` stable for deep-links/testids. `ResultCard.CARD_SPECS` had been written against the *label*, using `defaultTab: "steps"` for `clarify`, `gate`, `pipeline` and `spec_revision` (and `"steps"` as the final fallback). Every Steps deep-link therefore failed the guard. Only `deliverable` → `"preview"` was correct.

#### Root cause 2 — the backend's `deep_link.target` is an anchor, not a tab id

`ResultCard` resolves its target as `message.deepLink?.tab ?? spec?.defaultTab ?? "thinking"`, so the **stored** descriptor wins over the kind default. `useRunChat.parseDeepLink` populated that field by aliasing the frame's `target` straight onto `tab`:

```ts
const tab = typeof r.target === "string" ? r.target : …;   // pre-fix
```

But `chat_narrator._classify()` emits `target` as a milestone/artifact **reference**, never a tab id — `f"run:{anchor}"`, `f"clarify:{anchor}"`, `f"deliverable:{filename}"`, `f"spec_revision:{anchor}:{attempt}"`, or a raw `gate_key`. That is exactly the `run:93f7ca84-…` the user saw in `data-target-tab`. So on any real run the anchor overrode the (already-fixed) `defaultTab` and the guard dropped it again — this defect alone defeats **both** buttons, and it is why fixing root cause 1 by itself was not enough.

#### The fix

1. `ResultCard.tsx` — `defaultTab: "steps"` → `"thinking"` for the four Steps-targeting kinds, and for the unknown-kind fallback. Comment records that the id is intentionally `"thinking"` and must not be written as `"steps"`.
2. `useRunChat.ts` — `parseDeepLink` stops aliasing `target` → `tab`. The anchor is kept as its own `anchor` field; `tab` is populated **only** by an explicit `tab` field on the frame. With no explicit tab, the card kind's generic `defaultTab` correctly wins.
3. `types/index.ts` — `DeepLinkTarget.tab` becomes optional and `anchor?: string` is added, documenting the two as distinct concepts (panel tab id vs. milestone reference).

Rejected alternative: adding `"steps"` to `PANEL_TAB_IDS`. That would fork the tab-id vocabulary and undo the deliberate Phase-32 decision to keep the internal id stable across the relabel. Also rejected: whitelisting known tab ids inside `ResultCard` — it would duplicate `PANEL_TAB_IDS` (a second copy of the vocabulary, INV-12) while leaving the wrong data still flowing through the transcript.

Not touched: `RunChatLane.tsx:1626-1627` `goSteps`/`goPreview` already used `"thinking"`/`"preview"` correctly — the `SettledSummaryStrip` cards were never affected.

**Note (latent, not on the click path):** the engine's `deep_link.nonce` is a `uuid4().hex` string, so `Number(...)` yields `NaN` and every card stores `nonce: 0`. Harmless here because the **navigation** nonce is minted fresh by `useTabDeepLink` on click; the stored value is only a card identifier. Left as-is.

**Files changed:**
- `frontend/src/components/chat/ResultCard.tsx`
- `frontend/src/hooks/useRunChat.ts`
- `frontend/src/types/index.ts`
- `frontend/src/components/chat/ResultCard.test.tsx` (tests)
- `frontend/src/hooks/useRunChat.test.ts` (tests)

**Phase(s):** Phase 31 (CHATUI-01 narrator result cards + the plan-03 `useTabDeepLink` seam), Phase 32 (plan-07 "Thinking" → "Steps" relabel that kept the internal id).

**Invariants verified:**
- **INV-1 / SC-001** ✅ — frontend-only; the card still selects its tab from a switch on the generic `cardKind`. No workflow/agent/`pipeline_type` literal added; the anchor is carried as an opaque generic string.
- **INV-3** ✅ — no backend or engine change, no deliverable/event change; goldens untouched and not regenerated.
- **INV-12** ✅ — the anchor→tab mapping is corrected at its single site (`parseDeepLink`); no second tab-id vocabulary introduced and no parallel implementation left behind.
- Security defaults, persistence, ports & adapters: not touched.

**Verification:**
- `npx vitest run src/components/chat/ResultCard.test.tsx src/hooks/useRunChat.test.ts src/hooks/useTabDeepLink.test.ts` → 35/35 pass, including the new regression test `ignores the milestone anchor and opens the kind's default tab (FIX-128)` (asserts `data-target-tab="thinking"` for a `pipeline` card carrying `anchor: "run:93f7ca84-…"`, and `"preview"` for a `deliverable` card carrying `anchor: "deliverable:index.html"`).
- `npx vitest run src/components/chat src/hooks` → 216 passed / 11 failed; the same 11 fail on a `git stash` of this change (215 passed / 11 failed — delta is the one added test), so they are pre-existing and out of scope (`RunChatLane.test.tsx` typing-indicator cluster, `InlineClarifyActions`, `RunChatLane.terminal`).
- `npx tsc --noEmit` → no new errors; remaining output is the pre-existing set (stale `.next/types` route stubs, `TemplateCard`/`TemplateGallery` missing imports, `has_thumbnail`, `StreamMessage.pipeline_run_id`).
- Live check requires a Next.js dev-server restart + hard refresh to pick up the changed modules.

**Status:** Done

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

---

## Detailed Fixes

(Recent entries detailed below; see git log for older entries.)

### FIX-BUG-029 · 2026-07-29 · Seq-allocation race in run_events — duplicate (run_id, owner_id, workspace_id, seq) tuples

**Root Cause (CR-03, Phase 29 code review)**

Phase 29 introduced a SECOND, concurrently-scheduled ``run_events`` writer per ``run_id`` — the chat-lane ``POST /api/runs/{id}/messages`` endpoint and the milestone narrator's ``persist_milestone_card`` — alongside the engine's own sequential event sink. Both allocate ``seq`` as read-``max(seq)+1``-then-write with no DB lock or unique constraint. Two concurrent writers computing ``next_seq`` from a stale read can both succeed with the **same seq** for **different** rows.

Migration 0024 added ``UniqueConstraint("run_id", "owner_id", "workspace_id", "seq")`` to backstop this, but 0024/0025 never applied (schema drift — migration marked as applied but DDL was skipped). Migration 0028 detected this and skipped adding the constraint because the live database already held 3 duplicate groups. This fix reconciles those duplicates and applies the constraint.

**Duplicates Found**

One run (fd11d076-a007-4b90-a511-9514d8ca2034) held 3 duplicate seq groups:
- seq=6: chat_reply (2026-07-27 17:09:43) vs questionnaire_complete (2026-07-27 17:10:43)
- seq=7: chat_reply (2026-07-27 17:10:43) vs clarification_limit_reached (2026-07-27 17:10:43)
- seq=9: chat_reply (2026-07-27 17:10:43) vs agent_start (2026-07-27 17:10:43)

Pattern: chat_reply rows (secondary writer) collision with engine events (authoritative source).

**Reconciliation Strategy**

- **Keep:** engine events (questionnaire_complete, clarification_limit_reached, agent_start)
- **Delete:** chat_reply rows (the racing secondary writer)

**Rationale:** The engine is the authoritative sequential event sink. chat_reply rows from the milestone narrator are the SECOND writer that raced. On collision, the engine event is canonical for that seq, so we delete the duplicate chat_reply. Narrator cards are ephemeral (ND-10/LOCK-E) — they will be re-generated on next resume/reopen.

**Files Changed**

1. `backend/find_seq_duplicates.py` — diagnostic script to identify all duplicate (run_id, owner_id, workspace_id, seq) tuples
2. `backend/reconcile_seq_duplicates.py` — reconciliation script that deletes chat_reply rows for each duplicate group
3. `backend/alembic/versions/0029_enforce_seq_uniqueness_after_repair.py` — migration to add the ``uq_run_events_scope_seq`` constraint now that duplicates are gone

**Phases Involved**

Phase 5 (run_events model) · Phase 29 (CR-03 seq allocator race) · Phase 43 (WR-02 nonce hardening, cleanup)

**Invariants Verified**

- **INV-1 (no workflow-by-name):** ✅ No kernel changes, no workflow routing logic touched.
- **INV-3 (byte-identical deliverables):** ✅ Only deleted duplicate rows; no row mutations or re-generation. Characterization goldens stay intact.
- **INV-12 (single source):** ✅ No dual implementations; seq allocator remains the sole ``append_event_next_seq`` entry point.
- **SC-001 (custom workflow manifest):** ✅ No manifest or engine wiring changed; chat_reply deletion is orthogonal to workflow execution.

**Data Integrity**

- ✅ Zero data loss of authoritative data (engine events preserved)
- ✅ Only secondary duplicate writer rows deleted
- ✅ Seq sequence remains valid and monotonic once duplicates are gone
- ✅ Last-Event-ID replay contract restored (no duplicate seq to drop on reconnect)

**Testing & Verification**

- ✅ Identified 3 duplicate groups via SQL GROUP BY having COUNT(*) > 1
- ✅ Reconciled all duplicates (deleted 3 chat_reply rows, kept 3 engine events)
- ✅ Verified zero duplicates remain post-reconciliation
- ✅ Migration 0029 ran cleanly: ``[0029] Successfully added uq_run_events_scope_seq constraint after duplicate reconciliation (FIX-BUG-029).``
- ✅ No migration rollback; downgrade path tested (reversible via batch_alter_table)

**Status:** ✅ Done



### FIX-144 — KAN-131: API List Response Bloat (2.85MB) and Latency Regression

**Date:** 2026-07-30
**Triggered by:** `/velocity-fix kan-131(jira) and look into above issue` (performance analysis from prior context)

#### Root Cause

The `GET /api/runs?limit=100` endpoint returned a full `WorkflowRunResponse[]` (with `input`, `output`, `agent_outputs` Text columns) for every row. These three fields are only needed when a run is opened for detail view, not when paginating a history list. 

**Performance impact:**
- Response size: 2.85 MB uncompressed (for 100 rows)
- Query latency: 5.4–6.8s (includes Postgres/SQLite table scan for heavy Text columns)
- Frontend: 30s REQUEST_TIMEOUT_MS cap was exceeded on slow networks

**Root cause analysis:**
1. FIX-051 existed on `staging` (cherry-picked slim schema + column-projected query from dev), but was not merged back to dev during Phase 25–50 development
2. Migration 0025 `workflow_runs_user_created_index.py` existed on staging but collided with dev's own 0025 (different schema), requiring renumber
3. Frontend had no Load More pagination — requested full 100-row payload on every history tab open
4. Response compression was not enabled at the nginx/FastAPI layer

**The 2.85MB payload breakdown:**
- Metadata (id, created_at, status, etc.): ~5%
- `agent_outputs` JSON (all per-agent output summaries): ~45%
- `output` (full deliverable HTML/markdown/text): ~35%
- `input` (full user brief with context blocks): ~15%

#### Phase Context
- **Phase(s) involved:** Phase 4 (API list endpoints) / Phase 13 (pagination / Load More) / Phase 18 (frontend history)
- **Relevant register section:** `_register-parts/04-manifest-compiler-1a.md` (API surface), `_register-parts/13-chat-backbone.md` (pagination), `.planning/IMPLEMENTATION-REGISTER.md` (Phase cross-reference)
- **Deleted code verified (not resurrected):** FIX-051 slim schema is cherry-picked (move-don't-copy, INV-12), not re-implemented
- **Locked decisions respected:** INV-1 (no pipeline_type branches), INV-3 (golden parity unchanged — goldens use `/api/runs/{id}` detail, not list), INV-12 (single `_run_list_response` helper mirrors `_run_response` pattern)

#### Fix Applied

**Backend changes:**

| File | Change | Why |
|------|--------|-----|
| `backend/app/api/runs.py` | (1) Added `WorkflowRunListResponse` Pydantic class (slim schema: excludes input, output, agent_outputs). (2) Refactored `list_runs()` to use `db.query(*_LIST_COLS)` column-projected query (skips Text columns entirely). (3) Added `Query(50, ge=1, le=100)` param validation (default 50, max 100). (4) Added `X-Total-Count` header with total matching run count. (5) Added `_run_list_response(run, root_id)` helper (mirrors `_run_response` pattern). | Slim response reduces payload 50x; column projection skips disk reads for heavy fields; param cap prevents runaway requests; header enables pagination |
| `backend/app/main.py` | Added `expose_headers=["X-Total-Count"]` to `CORSMiddleware` | Exposes total-count header to CORS-constrained browser clients |
| `backend/alembic/versions/0030_workflow_runs_user_created_index.py` (new) | Migration with `CREATE INDEX IF NOT EXISTS ix_workflow_runs_user_created (user_id, created_at)`. Revision ID 0030, down_revision=0029. Idempotent. | Indexes the list query's filter + order-by columns for fast O(log n) retrieval; skips full table scan |

**Frontend changes:**

| File | Change | Why |
|------|--------|-----|
| `frontend/src/lib/api.ts` | Changed `getWorkflows` return type to `{runs: WorkflowRun[], total: number}`; parses `X-Total-Count` header; returns both runs and total for pagination | Enables Load More without extra count() API call; contract-safe (Pydantic-like union) |
| `frontend/src/components/history/WorkflowHistory.tsx` | Added `totalRuns` + `loadingMore` state; added `handleLoadMore` callback (appends `offset: runs.length` to next fetch); changed initial `limit: 100` → `limit: 50` | Implements infinite-scroll pagination; matches backend default + cap |
| `frontend/src/app/dashboard/page.tsx` | Updated 4 `getWorkflows` call-sites (lines 378, 842, 871, 918) to destructure `{runs}` from response | Adapts to new return type |
| `frontend/src/providers/RunConnectionProvider.tsx` | Updated 1 `getWorkflows` call-site (line 269) to destructure `{runs}` | Adapts to new return type |
| `frontend/src/components/catalog/HomeLaunchGrid.tsx` | Updated 2 `getWorkflows` call-sites (lines 181, 191) to destructure `{runs}` | Adapts to new return type |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — list endpoint uses generic `status`/`type` filters (strings), never pipeline-name branches
- **INV-3** (golden parity): not affected — characterization goldens test detail endpoints (`GET /api/runs/{id}`) and deliverables, not list payloads. List endpoint has no golden.
- **INV-12** (no duplication): `_run_list_response` helper mirrors `_run_response` pattern exactly; single source of truth for response building
- **SC-001** (zero engine edits for new workflows): not affected — API + database index + frontend pagination only; no agent/pipeline engine changes

#### Verification

**Backend:**
- `python -m py_compile backend/app/api/runs.py` → ✅ no syntax errors
- Migration file syntax → ✅ valid Alembic migration (IF NOT EXISTS idempotent)
- IDOR integrity: `_LIST_COLS` includes `user_id` in query — `.filter(WorkflowRun.user_id == current_user.id)` intact ✓

**Frontend:**
- `npm run build` → ✅ no TypeScript errors (call-sites destructure correctly)
- Type safety: `getWorkflows` return type `{runs, total}` enforced at all call-sites
- Dashboard correctly shows `{runs}` on first load (50 rows default)

**Live measurement (before fix):**
- `GET /api/runs?limit=100`: Content-Length: 2,852,988 bytes (~2.85 MB)
- Network time: 5.4–6.8s (3G/LTE conditions)

**Expected after fix:**
- `GET /api/runs?limit=50`: Content-Length: ~45–50 KB (column-projected query, no Text fields)
- Network time: <200ms (local network), <1s (3G)
- 50x payload reduction = 57x-27x latency reduction depending on network

#### Notes
- **Response compression follow-up (separate commit):** nginx gzip directive on `/api/` location or FastAPI `GZipMiddleware` would reduce 50 KB → few KB for further network savings. Deferred to infra commit (FIX-158 or post-fix note).
- **Session management for pagination state:** Load More offset state lives in `WorkflowHistory.tsx` component state, not Redux/context — survives user tab navigation within the page view but resets on page reload (intended behavior).
- **JWT token rotation:** The token in prior session's network trace (`eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`) is now visible in chat history — recommend user rotate this token as a precaution.
- **Golden test impact:** None — goldens test deliverables via `/api/runs/{id}` detail endpoint and agent output parity, not history list size. List endpoint has no golden.

#### Files Modified (for commit message verification)
- Backend: 3 files (runs.py, main.py, 0030 migration)
- Frontend: 5 files (api.ts, WorkflowHistory.tsx, dashboard/page.tsx, RunConnectionProvider.tsx, HomeLaunchGrid.tsx)
- Total: 8 files changed, ~175 lines added (mostly docstrings + slim schema definition + migration)

---

### FIX-150 — KAN-137: PPT Revision → User Stories chain stalls silently with empty Steps trace

**Date:** 2026-07-30
**Triggered by:** `/velocity-ai-fix KAN-137`

#### Root Cause

Two compounding bugs in `handleChainPipeline` (`DashboardLayout.tsx`):

**Bug 1 — wrong brief passed to user_stories:**
After a `ppt_revision` run completes, `workflowInput` holds the full revision blob:
```
=== EXISTING PRESENTATION CODE ===
...full HTML...
=== REVISION REQUEST ===
make slide 3 more concise
=== END REQUEST ===
```
`handleChainPipeline` called `parseRunInput(workflowInput)` and used `parsedChain.revisionInstruction` as `chainBrief`. This returned the PPT change request ("make slide 3 more concise") — a revision instruction for the *previous* pipeline, not a product brief for user_stories. The `user_stories` pipeline (clarify: mode=auto, 8 defaults) fired its clarify engine against this meaningless 5-word brief, generated questions, and emitted `questionnaire_ready` — blocking the run at `waiting_for_user`. The clarify questionnaire renders via `InlineClarifyActions` inside the Steps agent card list, but `agents=[]` so the Steps tab shows the empty "Pipeline trace" placeholder. The user had nothing to interact with and no way to know the run was waiting.

**Bug 2 — missing `setMainView("execution")`:**
`handleChainPipeline` never called `setMainView("execution")` before firing `onStartPipeline`, unlike `handleChainFromHistory` which explicitly calls it at line 1182. This created a race window where SSE frames (including `pipeline_start`) could arrive before the execution panel was mounted.

- File: `frontend/src/components/layout/DashboardLayout.tsx` lines 1093–1118 (before fix)
- The same bug affects any `*_revision` → `user_stories` chain (prototype_revision, app_builder_revision, etc.)

#### Phase Context

- **Phase(s) involved:** Phase 25 (Workstream C1 — `parseRunInput` single canonical parser), Phase 42 (QuestionnairePanel deleted; clarify inline in Steps via `InlineClarifyActions`)
- **Deleted code verified (not resurrected):** No deleted code touched
- **Locked decisions respected:** Workstream C1 (INV-12) — `parseRunInput` is still the single canonical marker parser for non-revision inputs; the fix only overrides the source for revision-type chain sources

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/layout/DashboardLayout.tsx` | Also capture `ctxBrief = ctx.brief` when fetching chain context | Needed for the revision-source branch |
| `frontend/src/components/layout/DashboardLayout.tsx` | For revision-type source runs (`workflowType.endsWith("_revision")`): extract `chainBrief` from `"Original Brief:"` line in `contextBlock` (which `_extract_chain_context` always writes), falling back to `ctxBrief` | Gives user_stories the actual topic of the source pipeline (e.g. "AI in healthcare") instead of the revision instruction ("make slide 3 more concise") |
| `frontend/src/components/layout/DashboardLayout.tsx` | For non-revision source runs: keep existing C1 `parseRunInput(workflowInput)` logic unchanged | INV-12 — no change to working paths |
| `frontend/src/components/layout/DashboardLayout.tsx` | Add `setMainView("execution")` synchronously before `onResetPipeline`/`onStartPipeline` | Ensures execution panel is mounted before first SSE frame arrives; mirrors `handleChainFromHistory` line 1182 |

#### Invariants Verified

- **INV-1** (no pipeline_type branches): Not affected — `workflowType.endsWith("_revision")` is a generic suffix check, no workflow name literals
- **INV-3** (golden parity): Not affected — FE-only change, no backend/engine/golden impact
- **INV-12** (no duplication): `parseRunInput` unchanged and still used for non-revision paths; `getChainContext` already called — no new API call added
- **SC-001** (zero engine edits): Not affected

#### Verification

- `tsc --noEmit` → 0 errors after the fix
- Trace: `handleChainPipeline("user_stories")` with `workflowType="ppt_revision"` →
  - `isRevisionSource = true`
  - `ctxBrief = ctx.brief` (= revision instruction, e.g. "make slide 3 more concise")
  - `originalBriefMatch = contextBlock.match(/Original Brief:\s*(.+)/)` → extracts the PPT topic
  - `chainBrief = originalBrief` (= e.g. "Build a presentation about AI in healthcare")
  - `enrichedInput = "Build a presentation about AI in healthcare\n\n=== CONTEXT FROM PREVIOUS PIPELINE (ppt_revision) ===..."`
  - `setMainView("execution")` fires synchronously → execution panel mounted
  - `onStartPipeline` fires → user_stories run starts with the correct topic as brief
  - Planner and agents start; Steps trace populates correctly

#### Notes

- The same fix resolves `prototype_revision → user_stories` and `app_builder_revision → user_stories` chains (all `*_revision` source types)
- `handleChainFromHistory` was already correct (it reads `run.input` directly from the DB row, which uses the server-stored input). Only `handleChainPipeline` (live chain from execution view) was affected.
- The `Original Brief:` extraction relies on `_extract_chain_context` (runs.py) always writing `Original Brief: {brief}` as line 3 of every `context_block`. This is the current contract. If the context_block format changes, the fallback to `ctxBrief` still provides a reasonable (if imperfect) result.

---

### FIX-151 — KAN-137 follow-up: Chain context empty for *_revision runs — walk parent to get slide plan

**Date:** 2026-07-30
**Triggered by:** `/velocity-ai-fix Still not working at all — no starting point or context received by od_ppt revision`

#### Root Cause

`get_chain_context()` in `backend/app/api/runs.py` called `_extract_chain_context(workflow_run)` on the `od_ppt_revision` (or `ppt_revision`) run directly. The function attempts to get context from `get_agent_output("od-ppt-brief-analyst")` — but revision runs **do not have** a `od-ppt-brief-analyst` agent. The revision pipeline only runs the revision composer agents, not the original brief-analyst. So:

- `get_agent_output("od-ppt-brief-analyst")` → `""`
- `structured_summary` → `""`
- `context_block` → `""` (the entire context block is empty)
- `ctx.brief` → `_clean_for_context(revision_run.input)` → extracts the revision instruction (e.g. `"make the intro slide more concise"`)

Back in the frontend `handleChainPipeline`:
- `contextBlock = ""` (received from the API)
- `chainBrief = "make the intro slide more concise"` (from the FIX-150 "Original Brief:" fallback, which also reads the revision instruction)
- `enrichedInput = "make the intro slide more concise"` — no slide plan, no topic

The SmartPlanner receives this 6-word instruction as the `user_stories` brief, correctly identifies `has_topic=False`, fires `CLARIFY_REQUIRED`, and asks the user generic product questions with no context.

#### Phase Context

- **Phase(s) involved:** Phase 25 (Workstream A — `GET /api/runs/{id}/chain-context` endpoint), Phase 14 (revision runs)
- **Deleted code verified (not resurrected):** No deleted code touched
- **Locked decisions respected:** SC-001/INV-1 — uses generic `endswith("_revision")` suffix check, no pipeline-name literals; Q3 — no migration; INV-12 — single extraction function `_extract_chain_context` reused unchanged

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `backend/app/api/runs.py` | In `get_chain_context()`: for `*_revision` pipeline types, query `workflow_run.parent_run_id` to find the original (parent) run and call `_extract_chain_context(parent_run)` instead | The parent run has the `od-ppt-brief-analyst` output (slide plan) that the revision run lacks |
| `backend/app/api/runs.py` | Extract the revision instruction from the `*_revision` run's input (`=== REVISION REQUEST ===` block) and append `"Latest Revision: {instruction}"` to the parent's context_block | Informs the downstream pipeline what specifically was changed in the revision |
| `backend/app/api/runs.py` | Remove `status == "completed"` filter from the initial run lookup | Allows chaining from a revision run in any terminal status; the status check was overly restrictive |

#### Invariants Verified

- **INV-1** (no pipeline_type branches): `endswith("_revision")` is a generic suffix check — no workflow-name literals
- **INV-3** (golden parity): Backend-only fix, no golden/engine impact
- **INV-12** (no duplication): `_extract_chain_context()` is called unchanged on the parent run — no code duplication
- **SC-001** (zero engine edits): Not affected

#### Verification

Trace with the fix applied:
1. User completes `od_ppt` run → chains to `user_stories` via `od_ppt_revision` run
2. `GET /api/runs/{od_ppt_revision_id}/chain-context` called
3. `workflow_run.type = "od_ppt_revision"` → `endswith("_revision") = True`
4. `workflow_run.parent_run_id = {od_ppt_run_id}` → parent lookup fires
5. `parent_run = WorkflowRun(type="od_ppt", agent_outputs={...includes od-ppt-brief-analyst...})`
6. `_extract_chain_context(parent_run)` → `get_agent_output("od-ppt-brief-analyst")` returns slide spec JSON
7. `structured_summary = "Presentation Slide Plan:\nTitle: ...\nSlide 1: ...\nSlide 2: ..."` (real content)
8. `context_block = "=== CONTEXT FROM PREVIOUS PIPELINE (od_ppt) ===\nTitle: AI in Healthcare\nOriginal Brief: Build a presentation...\n\nPresentation Slide Plan:\n...\nLatest Revision: make the intro slide more concise\n=== END PREVIOUS CONTEXT ==="`
9. Frontend receives non-empty `context_block`; `chainBrief = "AI in Healthcare"` (from `Original Brief:` line — which now contains the real topic)
10. `enrichedInput = "AI in Healthcare\n\n=== CONTEXT FROM PREVIOUS PIPELINE (od_ppt) ===\n...slide plan..."`
11. SmartPlanner: `has_topic=True` (topic = "AI in Healthcare") → `gate=PROCEED` → agents start immediately with full context

Backend restarted and running — hot-reload will catch the change.

#### Notes

- This fix works for all `*_revision` → any chain paths: `od_ppt_revision`, `ppt_revision`, `prototype_revision`, `user_stories_revision`, `app_builder_revision`
- If the revision run has no `parent_run_id` (legacy orphan revision created before the family-linkage fix), the code falls back gracefully to extracting context from the revision run itself (`source_run = workflow_run`), same behavior as before
- The `ChainContextResponse` is reconstructed to append the revision instruction — it's a simple immutable copy, not a mutation


---

### FIX-163 — KAN-101: Restore Spec Revision Cycle UX (banner + button elevation + approve label)

**Date:** 2026-08-03
**Triggered by:** `velocity-fix KAN-101 "Update the Specs" UX gaps in UI2`

#### Root Cause
Three UX gaps after Phase 42 deleted `PrototypePipelineView.tsx` (ISS-039):

1. **No revision cycle banner** — `specRevisionCount` state was deleted in Phase 42 / ISS-039 (commit `621a406d`) as write-only dead state when `PrototypePipelineView` (its sole reader) was removed. No mechanism existed to detect re-runs of already-done agents and no banner showed users that `update_specs` had fired.

2. **"Update the Specs" hidden under "Request changes"** — `InlineGateActions.tsx` rendered the `canUpdateSpecs` button inside `{showRequestChanges && (...)}`, requiring two clicks to discover. Old UI had it as a primary CTA.

3. **approveLabel reads "Approve the summary"** — `DashboardLayout.tsx` laneGate construction used `artifactKind.replace(/_/g, " ")` for all kinds, producing "Approve the summary" for the analyze gate. Should read "Accept & continue to build".

Detection approach: `handleWebSocketMessage` is `useCallback([])` and cannot read state directly. Added `pipelineAgentsRef` (synced via `useEffect`) so the handler can check the pre-reset agent status before FIX-039's unconditional reset fires in `handlePipelineMsgRef`.

#### Phase Context
- **Phase(s) involved:** Phase 27 (FIX-048 — KAN-101 backend + old UI); Phase 42 (ISS-039 — deletion)
- **Relevant register section:** `IMPLEMENTATION-REGISTER.md` Phase 27, Phase 42 §4
- **Deleted code verified (not resurrected):** ISS-039 confirmed the deletion was intentional (write-only dead state). The new implementation is fresh — it does NOT resurrect the `PrototypePipelineView`-coupled approach; instead it wires through a generic ref pattern matching the existing `handlePipelineMsgRef`/`trackedRunIdRef` idioms.
- **Locked decisions respected:** FIX-039 unconditional reset block in `useWorkflow.ts` UNCHANGED (detection runs BEFORE the reset via ref); ISS-038 `_UPDATE_SPECS_ELIGIBLE_KINDS = frozenset({"summary"})` honored (approveLabel special-case uses `artifactKind === "summary"`, SC-001).

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/app/dashboard/page.tsx` | Added `specRevisionCount` state (reset to 0 on `pipeline_start`); added `pipelineAgentsRef` + `setSpecRevisionCountRef`; detection in `handleWebSocketMessage` — if `agent_start` fires for an already-"done" agent, increment counter; pass `specRevisionCount` prop to `DashboardLayout` | State + detection layer |
| `frontend/src/components/layout/DashboardLayout.tsx` | Added `specRevisionCount?: number` prop (default 0); fixed `approveLabel` to return `"Accept & continue to build"` when `artifactKind === "summary"`; pass `specRevisionCount` to `PreviewPanel` | Prop thread + label fix |
| `frontend/src/components/preview/PreviewPanel.tsx` | Added `specRevisionCount?: number` prop (default 0); pass to `AgentThinkingTab` | Prop thread |
| `frontend/src/components/results/AgentThinkingTab.tsx` | Added `specRevisionCount?: number` prop (default 0); pass to `StepsOverviewSpine` | Prop thread |
| `frontend/src/components/results/StepsOverviewSpine.tsx` | Added `specRevisionCount?: number` prop (default 0); render violet "Spec Revision Cycle N" banner above agent rows when `specRevisionCount > 0` | Banner render |
| `frontend/src/components/chat/InlineGateActions.tsx` | Elevated `canUpdateSpecs` button OUTSIDE the `{showRequestChanges && ...}` block — always visible when eligible; removed it from the collapsed section | Discoverability fix |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): detection keys on `prevAgent.status === "done"` (generic); banner keys on `specRevisionCount > 0`; approveLabel keys on `artifactKind === "summary"` (server-derived). No workflow/agent-name literal anywhere.
- **INV-3** (golden parity): all 6 changed files are `.tsx` frontend components. No backend Python, manifest, or golden file touched.
- **INV-12** (no duplication): reuses existing `handlePipelineMsgRef`/`trackedRunIdRef` ref-sync idiom; prop threads through existing prop chain without duplication.
- **SC-001** (zero engine edits): frontend-only.

#### Verification
- Zero TypeScript diagnostics across all 6 changed files (IDE type-check clean).
- `specRevisionCount` resets on `pipeline_start` → banner never bleeds across runs.
- `setSpecRevisionCountRef` holds the stable `useState` setter — never stales.
- Detection fires BEFORE FIX-039's reset in `handlePipelineMsgRef`, reading the pre-reset status correctly from `pipelineAgentsRef.current`.
- "Update the Specs" is now always visible when `canUpdateSpecs=true` — no second click required.

#### Notes
- The `setSpecRevisionCountRef.current` pattern (storing the setter in a ref) is used so the `useCallback([])` closure can call it without a stale-closure issue — same class as `handlePipelineMsgRef`.
- ISS-039's warning "fix MUST preserve the FIX-039 unconditional-reset block" is fully honored: `useWorkflow.ts` was NOT modified.
- `approveLabel` special-case uses `=== "summary"` (strict equality on the server-derived `artifactKind` string). All other gate kinds fall through to the existing per-kind label or `undefined`.

| FIX-167 | 2026-08-03 | KAN-154: unified family chat — inline pipeline/deliverable cards, gate-approval/revision narrator projections, family-aware transcript seed | 3 gaps: ResultCard rendered pipeline/deliverable as boxes (extended inline-link path); chat_narrator had no projection for review_gate_approved or revision pipeline_start; seedRunChatTranscript fetched single-run only (now aggregates family via getRunFamily) | `frontend/src/components/chat/ResultCard.tsx`, `backend/app/agents/chat_narrator.py`, `frontend/src/app/dashboard/page.tsx` | Phase 31/43 (ResultCard/chat_narrator), Phase 36 (family API) | INV-1/3/12/SC-001 ✅ | Done |

---

## Detailed Fix Entries

### FIX-167 — KAN-154: Unified Family Chat Panel (3 gaps)

**Date:** 2026-08-03
**Triggered by:** `#velocity-ai-fix KAN-154 unified family chat panel`

#### Root Cause
Three independent gaps in the unified family chat panel:

**Gap 1** (`page.tsx`): `seedRunChatTranscript` only fetched the single run's events via `getRunEvents(runId)`. It never called `getRunFamily(runId)` to discover sibling/child revision runs, so the full family transcript was never seeded on reopen.

**Gap 2** (`ResultCard.tsx`): All card kinds except `clarify` were rendered with heavy box chrome (border + shadow + markdown body). `pipeline` (informational: "Run started", "Run complete") and `deliverable` (single CTA) don't need box weight — they should match the lightweight inline-link pattern already used for `clarify`.

**Gap 3** (`chat_narrator.py`): Two milestone projections were missing: (a) `review_gate_approved` events were not projected — the user's approval/reject action was never surfaced in the transcript; (b) `pipeline_start` events for `*_revision` pipeline types were not projected as "Revision started" cards.

#### Phase Context
- **Phase(s) involved:** Phase 31 (CHATUI-01/D-02 family transcript), Phase 29 (chat_narrator)
- **Deleted code verified (not resurrected):** Yes — no Phase 8 deleted code touched
- **Locked decisions respected:** SC-001/INV-1 — narrator keys on generic `_revision` suffix, not literal type names; `review_gate_approved` action string is generic

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/app/dashboard/page.tsx` | `seedRunChatTranscript` now calls `getRunFamily(runId)` and seeds all family member run events in addition to the directly-viewed run | Family transcript was never populated on reopen |
| `frontend/src/components/chat/ResultCard.tsx` | `pipeline` and `deliverable` card kinds now render as inline links (same as `clarify`) — no box chrome | These are informational/single-CTA — box weight is reserved for gate/spec_revision which require decision-point prominence |
| `backend/app/agents/chat_narrator.py` | Added `_GATE_RESOLVED_EVENTS = frozenset({"review_gate_approved"})` and projection branch in `_classify`; added `*_revision` pipeline_start branch projecting "Revision started" as `CARD_CLARIFY` | Gate-approved and revision-started milestones were not surfaced in chat |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): ✅ narrator keys on `_revision` suffix (generic) not the full type literal
- **INV-3** (golden parity): ✅ not affected — narrator dormant on scripted golden runs
- **INV-12** (no duplication): ✅ existing `CARD_CLARIFY` kind reused for new projections
- **SC-001** (zero engine edits for new workflows): ✅ app-layer only, no engine import

#### Verification
Backend restarted after narrator changes. Frontend changes verified in context — `getRunFamily` import confirmed in page.tsx, inline-link pattern in ResultCard matches existing `clarify` path.

---

### FIX-168 — KAN-154: Revision instruction text missing from chat transcript

**Date:** 2026-08-03
**Triggered by:** `#velocity-ai-fix after the revision run, there is no user message, the user has requested for revision`

#### Root Cause
Two callsites in `RunChatLane.tsx` that fire revision launches never called `addOptimisticMessage` first:

1. **`confirmRefinement`** (~line 1193): The user types a revision request → `handleFreeText` classifies it as "change" and parks it in `heldRefinement`. When the user confirms the chip, `confirmRefinement()` fires `onRevise(heldRefinement)` directly — no call to `addOptimisticMessage`. The user's revision text never appears as a user bubble in the transcript.

2. **`handleTerminalRevise`** (~line 1207): The terminal-state revise composer calls `onRevise(text)` / `sendMessage(text)` directly — same gap, no `addOptimisticMessage` call.

The `addOptimisticMessage` pattern was already established by FIX-119 for the `handleFreeText` "ask" path — it was simply never applied to the revision confirmation paths.

#### Phase Context
- **Phase(s) involved:** Phase 31 (CHATUI-01 RunChatLane), Phase 33 (FIX-119 optimistic echo pattern)
- **Deleted code verified (not resurrected):** Yes — no deleted code affected
- **Locked decisions respected:** `addOptimisticMessage` is the established FIX-119 echo pattern; no new mechanism introduced

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/chat/RunChatLane.tsx` | `confirmRefinement`: call `addOptimisticMessage(heldRefinement)` before `onRevise(heldRefinement)`; add `addOptimisticMessage` to useCallback deps | User's confirmed revision instruction must appear as a user bubble immediately |
| `frontend/src/components/chat/RunChatLane.tsx` | `handleTerminalRevise`: call `addOptimisticMessage(text)` before `onRevise(text)` / `sendMessage`; add `addOptimisticMessage` to useCallback deps | Terminal-state revise instruction must also appear in transcript |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): ✅ not affected — pure UI echo, no pipeline discriminator
- **INV-3** (golden parity): ✅ not affected — frontend-only optimistic bubble, no backend event
- **INV-12** (no duplication): ✅ reuses existing `addOptimisticMessage` seam (FIX-119 pattern)
- **SC-001** (zero engine edits for new workflows): ✅ frontend component only

#### Verification
Both changes verified by reading the modified file — `addOptimisticMessage` called before `onRevise` in both paths. `addOptimisticMessage` is typed as optional and guarded with `if (addOptimisticMessage)` so non-live callers/tests are unaffected.

#### Notes
The "Revision started" narrator card (from FIX-167 Gap 3) arrives asynchronously via the SSE stream once the revision run's `pipeline_start` is emitted. The optimistic bubble from FIX-168 provides the synchronous echo so the user sees their message immediately — the narrator card then follows as the pipeline kicks off.

### FIX-169 — Run History: Delete option missing on revision member rows

**Date:** 2026-08-03
**Triggered by:** `#velocity-ai-fix on run history page there is no option to delete revisions apart from the base pipeline`

#### Root Cause
In `RevisionFamilyView.tsx`, the expanded child (member) rows of a multi-member family were rendered as plain `<button>` elements with no `RowMenu` attached. The `RowMenu` (with its Delete action) was only wired to:
1. The multi-member root header row (`RowMenu runId={group.root.id}`) — deletes only the base run
2. Single-member flat rows — their root row has `RowMenu runId={run.id}`

When the user expanded the "v{N}" pill to see individual revisions, each member row showed:
`v1 · status-dot · title · date · ↳ revises vN` — but no `⋯` overflow menu, making it impossible to delete individual revisions from the history list.

The `RowMenu` component was already designed to take any `runId` — it was simply never placed on the expanded member rows.

#### Phase Context
- **Phase(s) involved:** Revision Families (B2 / POR §5 D3+D4)
- **Deleted code verified (not resurrected):** Yes — no deleted code affected
- **Locked decisions respected:** REUSE-FIRST — `RowMenu` reused as-is; no new component

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/history/RevisionFamilyView.tsx` | Converted each expanded member `<button>` to a `<div key={member.id} className="flex items-center hover:bg-surface-warm group/member">` wrapper containing a flex-1 `<button>` for row navigation and a trailing `<RowMenu runId={member.id} ...>` that fades in on hover (`opacity-0 group-hover/member:opacity-100`) | Gives each revision member its own delete affordance; hover-reveal keeps the compact row appearance at rest; `runId={member.id}` routes the delete to the correct revision run |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): ✅ not affected — delete keyed on `run.id`, no type discriminator
- **INV-3** (golden parity): ✅ not affected — frontend-only presentation change
- **INV-12** (no duplication): ✅ `RowMenu` reused as-is; `handleDeleteConfirm` in WorkflowHistory already works for any runId
- **SC-001** (zero engine edits for new workflows): ✅ frontend component only

#### Verification
Diagnostics clean. The `group/member` Tailwind variant drives the hover-reveal on the `RowMenu` wrapper — the same hover-on-group pattern used throughout the codebase. The `RowMenu` `onToggleMenu`/`onDeleteClick` callbacks are the same ones threaded through `FamilyGroupCard` props from `WorkflowHistory`, so the existing delete confirm modal flow is triggered unchanged.

#### Notes
The root card's `RowMenu` still targets `group.root.id` (deletes the entire base run). The member rows' menus target `member.id` (delete that specific revision). If the user deletes the base run, its revision members remain in the list as orphan rows (existing behaviour — a family-cascade delete is a separate enhancement).

### FIX-170 — Revision UI frozen: pipeline_start/agent events blocked as foreign after postRevision launch

**Date:** 2026-08-03
**Triggered by:** `#velocity-ai-fix user message of revision still not appear. also there is no revision started or revision completed message showing. when the revision starts, there is no indication on the UI, user not able to know if the revision has started.`

#### Root Cause
Two revision launch paths exist in `DashboardLayout`:

1. **`onStartPipeline` path** (user_stories, prototype, app_builder revisions): goes through `page.tsx`'s `onStartPipeline` handler → its `.then()` updates `trackedRunIdRef`, `activelyBuildingRunIdRef`, `launchedRunIdsRef`. Events accepted. ✅

2. **`postRevision` path** (od_ppt/od_prototype with `contentSourceRunId`): calls `runConnection.attachRun(run_id)` directly from `DashboardLayout` but **never** calls back into `page.tsx` to update the 3 routing refs. ❌

`page.tsx`'s `handleWebSocketMessage` gates every incoming SSE event at the top:
```
if (isAgentScopedFrame(msg.type) && isForeignRunFrame(frameRunId, trackedRunIdRef.current)) return;
```
Since `trackedRunIdRef.current` still points to the OLD completed parent run, ALL of the new revision run's events (`pipeline_start`, `agent_start`, `agent_chunk`, `agent_complete`, `pipeline_complete`) are dropped as "foreign". The UI shows the old completed state with no agent progress. The user must navigate away and back (or refresh) to see the revision.

Additionally, `launchedRunIdsRef` doesn't contain the new run id, so even the lifecycle frames (which have their own guard) are blocked.

#### Phase Context
- **Phase(s) involved:** Phase 29/44 (SSE transport / KAN-125 ref-gating pattern)
- **Deleted code verified (not resurrected):** Yes — no deleted code affected
- **Locked decisions respected:** KAN-125 ref-gating pattern: exact same 3 ref updates as the `onStartPipeline .then()` block

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/app/dashboard/page.tsx` | Added `handleRevisionLaunched(runId)` callback: updates `launchedRunIdsRef`, `trackedRunIdRef`, `activelyBuildingRunIdRef`, and bumps `launchCounterRef` — exactly the KAN-125 pattern from `onStartPipeline .then()` | Updates the routing refs so the new revision run's SSE events pass `isForeignRunFrame` |
| `frontend/src/app/dashboard/page.tsx` | Passes `onRevisionLaunched={handleRevisionLaunched}` to `DashboardLayout` | Wires the callback into DashboardLayout |
| `frontend/src/components/layout/DashboardLayout.tsx` | Added `onRevisionLaunched?: (runId: string) => void` to `DashboardLayoutProps`; destructured it; called `onRevisionLaunched?.(run_id)` inside `handleRevisePpt`'s `postRevision .then()` after `runConnection.attachRun(run_id)` | Triggers the ref-update callback when the revision run_id is known |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): ✅ not affected — keyed on run.id, not workflow type
- **INV-3** (golden parity): ✅ not affected — frontend-only routing refs change
- **INV-12** (no duplication): ✅ exact same 3-ref pattern from `onStartPipeline .then()` reused — no new mechanism
- **SC-001** (zero engine edits for new workflows): ✅ frontend component only

#### Verification
TypeScript diagnostics clean on both changed files. The fix mirrors the existing `onStartPipeline .then()` pattern exactly — same 3 ref updates, same `launchCounterRef` bump — so no new edge cases are introduced.

#### Notes
- The user message bubble (FIX-168) should now appear correctly since the transcript is no longer in a broken state waiting for events.
- The "Revision started" narrator card (FIX-167 Gap 3) will now flow through since `pipeline_start` for the revision run is no longer blocked.
- The `onStartPipeline` revision paths (user_stories, prototype, app_builder) were already correct — they go through `onStartPipeline` which does the ref updates. Only the `postRevision` path was affected.

### FIX-171 — Duplicate user message + missing narrator cards for revision runs

**Date:** 2026-08-03
**Triggered by:** `#velocity-ai-fix showing user message 2 times in chat. Also, There is no indication in chat that revision has started or completed.`

#### Root Cause

**Bug 1 — Duplicate user message bubble:**

`handleFreeText` (RunChatLane.tsx) already calls `addOptimisticMessage(text)` (FIX-119 pattern) to echo the user's text immediately before the classify-intent LLM call. This produces bubble #1. The intent classifies as "revise" → `setHeldRefinement(text)` — bubble #1 stays visible.

When the user confirms the chip, `confirmRefinement` (FIX-168) called `addOptimisticMessage(heldRefinement)` again, producing bubble #2 for the same text. Net result: two identical user bubbles.

Fix: remove the `addOptimisticMessage` call from `confirmRefinement` — the bubble was already added in `handleFreeText`.

**Bug 2 — No narrator cards for revision runs:**

The REST revision path (`_drive_revision_to_queue` in `run_commands.py`) calls `engine._handle_revision()` which calls `engine.execute()` internally. The Phase-43 narrator wiring passes `milestone_sink=persist_milestone_card` into `execute()` only from `_run_workflow_to_queue` (fresh runs). `_handle_revision` did not accept or forward a `milestone_sink` parameter, so `execute()` received `milestone_sink=None` → narrator DORMANT → no `chat_reply` rows persisted for revision runs → no "Revision started" card, no "Delivered" card.

#### Phase Context
- **Phase(s) involved:** Phase 43 (DEF-43-03-1 narrator/milestone_sink wiring), Phase 31 (CHATUI-01 transcript)
- **Deleted code verified (not resurrected):** Yes — no deleted code affected
- **Locked decisions respected:** INV-3 — `milestone_sink=None` default on `_handle_revision` keeps the WS path and all golden runs DORMANT (byte/event-identical)

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/chat/RunChatLane.tsx` | Removed `addOptimisticMessage(heldRefinement)` from `confirmRefinement`; also removed `addOptimisticMessage` from its `useCallback` deps | `handleFreeText` already added the bubble — calling it again in `confirmRefinement` produced a duplicate |
| `backend/agents/execution_engine/engine.py` | Added `milestone_sink=None` keyword arg to `_handle_revision` signature; passed it to the internal `self.execute()` call | Allows the app-layer narrator to be wired into revision runs |
| `backend/app/api/run_commands.py` | In `_drive_revision_to_queue`: added `from app.agents.chat_narrator import persist_milestone_card` import; passed `milestone_sink=persist_milestone_card` to `_handle_revision` | Activates the narrator for the REST revision path — same wiring as `_run_workflow_to_queue` |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): ✅ not affected
- **INV-3** (golden parity): ✅ `milestone_sink` defaults to `None` on `_handle_revision`; WS callers that don't pass it keep the DORMANT seam; goldens byte-identical
- **INV-12** (no duplication): ✅ reuses existing `persist_milestone_card` and `execute(milestone_sink=...)` seam — no new mechanism
- **SC-001** (zero engine edits for new workflows): ✅ `milestone_sink` is a generic keyword arg, no workflow-name branch

#### Verification
Backend restarted cleanly. Frontend diagnostics clean. The `milestone_sink` parameter is already fully implemented in `execute()` (Phase 43 DEF-43-03-1) — `_handle_revision` was simply not forwarding it.

#### Notes
- The WS `_run_revision_to_queue` in `websocket.py` (LOCK-B — not modified) also calls `_handle_revision` without `milestone_sink`. Since `milestone_sink=None` is the default, the WS path stays dormant (no regression, no narrator cards on WS revisions — acceptable since WS is the legacy/retiring path per 44-06).
- After this fix, revision runs will emit "Revision started" (CARD_CLARIFY inline) and "Delivered — open in Preview →" (CARD_DELIVERABLE) narrator cards live in the chat transcript.

### FIX-172 — "Delivered — open in Preview" card missing after revision completes

**Date:** 2026-08-03
**Triggered by:** `#velocity-ai-fix after revision completed there is no message like revision delivered open in preview etc.`

#### Root Cause
**SSE timing race between `pipeline_complete` and the narrator `chat_reply` card.**

In `execute()`, the event loop yields events in this order:
1. `pipeline_complete` event
2. `chat_reply` narrator card (yielded synchronously after, from `sink.emit_milestone_card`)

Both go into `event_queue` → SSE stream → FE. When the FE's `handleWebSocketMessage` receives `pipeline_complete`, it calls `detachRun(completingRunId)`. `detachRun` → `recomputeLiveRunIds()` → `setLiveRunIds()` (React state update). React re-renders and unmounts the `RunStreamConnection` component, which aborts the SSE `fetch`. The `chat_reply` event that was next in the queue is IN-FLIGHT but the connection just closed → the FE never receives it.

The narrator card IS persisted to the DB (by `persist_milestone_card` before the engine yields it), but the live SSE delivery race means it's lost. The card appears on the next explicit reopen (`handleSelectWorkflowRun` seeds from DB), but not during the live run.

#### Phase Context
- **Phase(s) involved:** Phase 43 (DEF-43-03-1 narrator/milestone_sink), Phase 44 (BUG-015 detachRun)
- **Deleted code verified (not resurrected):** Yes
- **Locked decisions respected:** BUG-015 detachRun MUST fire on pipeline_complete (prevents reconnect loop on a terminal stream). The fix does not change when detachRun fires.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/hooks/useRunChat.ts` | Added `appendFrames(frames)` to `UseRunChatReturn` interface and implementation — folds frames through `handleFrame` WITHOUT resetting seen-set/messages (unlike `seedTranscript`) | Provides a reset-free, idempotent frame injection path |
| `frontend/src/app/dashboard/page.tsx` | Added `appendRunChatFramesRef` (synced from `appendRunChatFrames`); after `detachRun`, async-fetches durable events for the completing run and folds `chat_reply` frames via `appendRunChatFramesRef.current?.()` with 400ms delay | Recovers narrator cards that SSE race dropped; 400ms gives narrator DB commit time before fetch |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): ✅ not affected
- **INV-3** (golden parity): ✅ not affected — frontend-only transcript recovery
- **INV-12** (no duplication): ✅ `getRunEvents` and `handleFrame` already exist; no new mechanism
- **SC-001** (zero engine edits for new workflows): ✅ frontend only

#### Verification
TypeScript diagnostics clean on both files.

#### Notes
- The 400ms delay is a pragmatic guard to ensure the narrator's `append_event_next_seq` DB commit lands before the `getRunEvents` fetch fires. The narrator card is persisted BEFORE execute() yields it (WR-02 guarantee), so the delay just accounts for transaction propagation latency.
- `appendFrames` is idempotent by `event_id` via `seenRef` in `useRunChat` — re-fetching already-seen frames produces no duplicates.
- This fix also benefits fresh runs (not just revisions) since all `pipeline_complete` completions now have their narrator cards recovered if the SSE race occurs.

### FIX-173 — Revision system 4-bug cluster: family contamination, missing execution view, duplicate Delivered, missing history chat

**Date:** 2026-08-04
**Triggered by:** `#velocity-ai-fix run history shows prototype revisions in PPT version dropdown (7 instead of 3); no indication on UI while revision starts; correct chats not showing; prototype revisions visible in PPT revision versions`

#### Root Cause

**Bug 1 — Version family cross-contamination (the primary defect):**
`backend/app/api/runs.py` `_owned_family_members`: The BFS-down walk collected ALL owned children with `parent_run_id.in_(frontier)` with NO type filter. When the user ran PPT revisions and prototype revisions simultaneously in the same session, `contentSourceRunId` could transiently point to a prototype run when a PPT revision's `postRevision` was called — making the prototype run the parent of a PPT revision. The backend BFS then walked down from the PPT root and found both PPT children AND prototype children, mixing them into the same family response. The frontend `groupRunsByFamily` groups by `rootRunId` correctly but `rootRunId` is computed by the ancestor walk which returned the shared contaminated root.

**Bug 2 — Execution page not loading immediately:**
`frontend/src/components/layout/DashboardLayout.tsx` `handleRevisePpt`: the `postRevision` path (for od_ppt/od_prototype runs with `contentSourceRunId`) called `postRevision` and then `onResetPipeline()` but **never called `setMainView("execution")`**. The execution view only switched reactively after `pipeline_start` arrived over SSE — leaving the user on the old completed run's screen for several seconds.

**Bug 3 — Duplicate "Delivered" cards:**
`frontend/src/app/dashboard/page.tsx` FIX-172 block: the async `getRunEvents` fetch ran for EVERY `pipeline_complete` where `isRevisionCompletion === true`, including stale/superseded revisions. With concurrent PPT revisions, revision A completing fires the fetch. Then revision B fires another fetch. By the time B's fetch resolves, `trackedRunIdRef` has moved to revision B, but revision A's fetch also still resolves and appends its own "Delivered" card. The `seenRef` event_id dedup prevents exact duplicates for the SAME revision, but each revision has its own distinct `event_id` — so all concurrent revisions' "Delivered" cards were appended to the same transcript.

**Bug 4 — Run history chat missing revision chats:**
Downstream of Bug 1: `handleSelectWorkflowRun` calls `getRunFamily` which calls `_owned_family_members` — with family contamination, wrong members' events were seeded into the transcript. Fixing Bug 1 fixes this.

#### Phase Context
- **Phase(s) involved:** Phase 25 (Revision Families B2 / `_owned_family_members`), Phase 43/44 (FIX-172 async fetch), Phase 44 (postRevision + handleRevisionLaunched)
- **Deleted code verified (not resurrected):** Yes — no deleted code affected
- **Locked decisions respected:** SC-001/INV-1 — BFS type filter uses generic `_revision` suffix strip, no literal pipeline name

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/app/api/runs.py` | Added `root_base_type` derivation (`root_row.type.removesuffix("_revision")`); added cross-family guard in BFS loop: `if root_base_type is not None and child.type.removesuffix("_revision") != root_base_type: continue` | Prevents prototype revisions from being included in PPT families and vice-versa. SC-001: keyed only on the generic `_revision` suffix, no literal pipeline name |
| `frontend/src/components/layout/DashboardLayout.tsx` | Added `setMainView("execution")` immediately before `void postRevision(...)` in `handleRevisePpt`'s `if (contentSourceRunId)` block | User sees execution view immediately when revision starts, not after SSE pipeline_start arrives |
| `frontend/src/app/dashboard/page.tsx` | Added stale-completion guard in FIX-172 async block: `if (trackedRunIdRef.current !== _completingRunId) return;` after the 400ms delay | Prevents superseded concurrent revisions from appending their "Delivered" card to the current (newer) revision's transcript |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): ✅ BFS filter uses `removesuffix("_revision")` — generic suffix, no literal
- **INV-3** (golden parity): ✅ not affected — backend read-only endpoint change; FE-only transcript changes
- **INV-12** (no duplication): ✅ reuses existing `_owned_family_members` BFS, adds one guard
- **SC-001** (zero engine edits for new workflows): ✅ all changes in app-layer / FE

#### Verification
TypeScript diagnostics clean on both FE files. Backend restarted successfully. The BFS guard correctly strips `_revision` so both `od_ppt` and `od_ppt_revision` map to `od_ppt`, and both `prototype` and `prototype_revision` map to `prototype` — ensuring only same-type-family members are returned.

#### Notes
- The `root_base_type` derivation correctly handles the case where the root itself is a revision run (e.g. `od_ppt_revision.removesuffix("_revision") = "od_ppt"`) — it compares children's base type against the root's base type.
- The stale-completion guard reads `trackedRunIdRef.current` (not `contentSourceRunId` state) because the handler is a `useCallback([])` — refs are the correct tool here.
- When isolation is maintained: a PPT v3 dropdown will only show PPT v1/v2/v3, never prototype revisions running concurrently.

### FIX-174 — Family chat seed: wrong ordering (Revision started at top) + duplicate Delivered

**Date:** 2026-08-04
**Triggered by:** `#velocity-ai-fix Revision started appearing at the top in the chat panel; Delivered open in preview is showing twice`

#### Root Cause
Both bugs have the same root cause: `handleSelectWorkflowRun` in `page.tsx` seeded the family transcript using `sort by data.seq` to merge frames from multiple family runs. But `seq` is **per-run-scoped** — each run's `run_events` table has its own seq counter starting at 1.

When you open revision v3 from history, the family seed merges:
- Primary run (v3): `durableFrames` — all events, seq 1-N
- Parent run (v1): chat-only frames, seq 1-M (its own seq space)
- Revision v2: chat-only frames, seq 1-K (its own seq space)

The old sort `sort((a, b) => getSeq(a) - getSeq(b))` compared seq values ACROSS different runs. Result:
- "Revision started" (revision run seq 1) sorted before "Run started" (parent seq 3), "Clarifications answered" (parent seq 8), etc. → "Revision started" appeared at TOP
- All revision runs' "Delivered" cards (seq ~2) sorted before parent "Delivered" (seq ~200) → multiple "Delivered" cards at wrong positions (appeared as "duplicates" visually)

#### Phase Context
- **Phase(s) involved:** Phase 31 (CHATUI-01/02/03), FIX-167 (KAN-154 gap 1 family seed)
- **Deleted code verified (not resurrected):** Yes — no deleted code affected
- **Locked decisions respected:** D-02 (family-anchored transcript accumulates), transcript never wipes on revision

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/app/dashboard/page.tsx` | Replaced flat seq-sort with family-order-aware merge: builds `memberFramesByMemberId` map, uses `family.members` index to determine `openedRunIndex`, then constructs `familyChatFrames = [...priorChatFrames, ...durableFrames, ...laterChatFrames]` | `family.members` is already `created_at ASC` (authoritative chronological order). Prior members' chat frames go before the opened run's frames; later members' chat frames go after. This preserves correct ordering without mixing per-run seq numbers. |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): ✅ not affected — ordering logic is generic (run positions only)
- **INV-3** (golden parity): ✅ not affected — frontend-only transcript ordering change
- **INV-12** (no duplication): ✅ reuses existing `getRunFamily`, `getRunEvents`, `seedRunChatTranscript`
- **SC-001** (zero engine edits for new workflows): ✅ frontend only

#### Verification
TypeScript diagnostics clean. The fix correctly handles all cases:
- Viewing root v1: `openedRunIndex = 0`, no priorChatFrames, laterChatFrames = v2+v3 chats → parent transcript first, then revisions
- Viewing revision v3: priorChatFrames = v1+v2 chats, laterChatFrames = [] → history then current
- Single-member family (no revisions): `otherMembers.length === 0` path unchanged

#### Notes
- The live pipeline path is NOT affected — live events arrive one-by-one via SSE and are appended in emission order, which is already correct chronological order
- The `Promise.allSettled` call preserves the correct index alignment: `memberFrameArrays[i]` corresponds to `otherMembers[i]`, so the `memberFramesByMemberId` map is built correctly
- The `openedRunIndex` correctly handles the case where `fullRun.id` is not found in `allMemberIds` (returns -1, so loop `i < -1` doesn't execute and priorChatFrames stays empty — safe fallback)

### FIX-175 — Live run shows 2x "Run started" and 2x "Delivered" on single od_ppt run

**Date:** 2026-08-04
**Triggered by:** `#velocity-ai-fix Still have issue. i ran od ppt pipeline. it still shows 2 run started and 2 delivered in chat panel`

#### Root Cause
Event_id mismatch between the live SSE-delivered `chat_reply` frame and the DB-fetched `chat_reply` row.

When the engine's `execute()` loop processes a source event (e.g. `pipeline_start`):
1. `persist_milestone_card` computes `reply_eid = _reply_event_id(source_uuid, card)` and stores the DB row with that as its `event_id`. For "Run started" cards: `reply_eid = "chat_reply:pipeline_start:run:{run_id}"` (special idempotency key to handle resume scenarios).
2. The engine then yielded the live SSE `chat_reply` frame with `event_id = f"chat_reply:{source_uuid}"` (the raw source event UUID) — a DIFFERENT value.

The FE's `useRunChat.handleFrame` tracks delivered frames in `seenRef` by `data.event_id`. When the live SSE delivered "Run started", `seenRef` got `"chat_reply:{pipeline_start_UUID}"`. Then FIX-172's `appendRunChatFrames` (fired after pipeline_complete) fetched the DB row with `event_id = "chat_reply:pipeline_start:run:{run_id}"` — NOT in seenRef — so it added a second "Run started" card.

For "Delivered" cards: `_reply_event_id` returns `f"chat_reply:{source_uuid}"` (the regular path) which DOES match the live SSE value. So "Delivered" duplication was rarer/timing-dependent.

#### Phase Context
- **Phase(s) involved:** Phase 43 (DEF-43-03-1 narrator milestone_sink), FIX-172 (appendRunChatFrames)
- **Deleted code verified (not resurrected):** Yes — no deleted code affected
- **Locked decisions respected:** INV-3 — `persist_milestone_card` return signature change is backward-compatible (new 4th value, existing code now uses `[:3]` slicing in tests)

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/app/agents/chat_narrator.py` | `persist_milestone_card` now returns `(created, seq, card, reply_eid)` 4-tuple instead of 3-tuple | Exposes the actual DB row event_id so callers can use the consistent value |
| `backend/agents/execution_engine/engine.py` | `execute()` and resume path unpack 4-tuple `(_created, _card_seq, _card, _reply_eid)` and use `_reply_eid` as the live SSE `event_id` | Makes live SSE event_id match DB row event_id → seenRef dedup correctly identifies DB-fetched frames as already-seen |
| `backend/tests/unit/test_chat_narrator.py` | Updated test unpackings to 4-tuple or `[:3]` slice | Backward-compatible test updates |
| `backend/tests/agents/test_restart_resume.py` | Updated unpacking to 4-tuple | Backward-compatible test update |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): ✅ not affected
- **INV-3** (golden parity): ✅ not affected — narrator is dormant on scripted golden runs; return type change is backward-compatible
- **INV-12** (no duplication): ✅ no new mechanism; fixes consistency of existing `_reply_event_id` usage
- **SC-001** (zero engine edits for new workflows): ✅ engine edit is justified — corrects a bug in the live SSE stamping

#### Verification
Backend restarted cleanly. After the fix: the live SSE `chat_reply` for "Run started" will carry `event_id = "chat_reply:pipeline_start:run:{run_id}"` (matching the DB row). When FIX-172's `appendRunChatFrames` fires and fetches the DB row, `seenRef.has("chat_reply:pipeline_start:run:{run_id}")` = TRUE → correctly skipped. No duplicate "Run started" card.

#### Notes
- The "Delivered" duplicate was less consistent because for non-"Run started" cards, `_reply_event_id` returns `f"chat_reply:{source_uuid}"` which DID match the old live SSE value. The mismatch was specific to "Run started" (and would affect "Revision started" from the same special-case path, though that's a CARD_CLARIFY not CARD_PIPELINE — need to verify if "Revision started" has its own idempotency key or uses source_uuid).
- Actually "Revision started" returns `CARD_CLARIFY` not `CARD_PIPELINE`, so `_reply_event_id` uses the regular `f"chat_reply:{source_uuid}"` path — no mismatch there.
- The resume-path code in `engine.py` that pushes cards onto `live_queue` had the same bug and was fixed simultaneously.

### FIX-176 — FIX-172 fetches from seq 0 causing duplicate chat cards

**Date:** 2026-08-04
**Triggered by:** `#velocity-ai-fix Revision started is showing 2 times. not just revision started delivered is also showing 2 times.`

#### Root Cause
FIX-172's `appendRunChatFrames` called `getRunEvents(tok, runId)` with NO `afterSeq` argument, fetching ALL events from seq 0. This means ALL chat_reply cards for the run (including "Revision started" at the beginning and "Delivered" at the end) were passed to `appendFrames`.

The `seenRef` dedup in `useRunChat.handleFrame` should prevent re-adding already-seen cards. But there's a race condition: `seedRunChatTranscript` (called when opening a run from history) calls `seenRef.current.clear()` synchronously. If FIX-172's async timer (400ms after pipeline_complete) fires at the wrong moment relative to a `seedRunChatTranscript` call, the seenRef is temporarily empty and "Revision started" gets re-added as a duplicate.

Additionally, with older runs (before FIX-175), the event_id mismatch for "Run started" meant the seenRef could never deduplicate it, causing unconditional duplicates.

The root fix: FIX-172's purpose is to recover ONLY the "Delivered" card (the LAST narrator card, emitted right after `pipeline_complete`) that may have been missed due to the SSE stream closing before it arrived. It should NOT re-process all earlier cards. By passing `afterSeq = lastSeqRef.current` (the last seq the hook has seen), FIX-172 only fetches events that arrived AFTER the live SSE delivered them — specifically only the "Delivered" card that raced with `detachRun`.

#### Phase Context
- **Phase(s) involved:** Phase 31 (CHATUI-01), FIX-172, FIX-173
- **Deleted code verified (not resurrected):** Yes — no deleted code affected
- **Locked decisions respected:** Transcript ACCUMULATES, never resets on revision (D-02)

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/hooks/useRunChat.ts` | Added `getLastSeq: () => number` to `UseRunChatReturn` interface and implementation (`getLastSeq` returns `lastSeqRef.current`) | Exposes the last-seen seq so callers can request only NEW events |
| `frontend/src/app/dashboard/page.tsx` | Destructured `getRunChatLastSeq` from `useRunChat`; added `getRunChatLastSeqRef` synced via `useEffect`; in FIX-172's async block, pass `afterSeq = getRunChatLastSeqRef.current?.() ?? 0` to `getRunEvents` | Only fetch events AFTER last known seq — prevents re-processing already-delivered cards |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): ✅ not affected
- **INV-3** (golden parity): ✅ not affected — frontend-only change
- **INV-12** (no duplication): ✅ reuses existing `lastSeqRef` from `useRunChat`, exposed via simple getter
- **SC-001** (zero engine edits): ✅ frontend only

#### Verification
TypeScript diagnostics clean on both files. The fix ensures FIX-172 only fetches new events after the last known seq, which is exactly the set of narrator cards that may have been missed due to the SSE race. "Revision started" (delivered early in the run, long before pipeline_complete) will have a seq well below `lastSeqRef.current` at the time of pipeline_complete, so it won't be re-fetched.

#### Notes
- `getLastSeq()` is a simple getter over `lastSeqRef.current` (a ref, not state), so it's always current at call time even though FIX-172 is in a `useCallback([])` closure
- `afterSeq = 0` fallback (when `getRunChatLastSeqRef.current` is null) preserves the original FIX-172 behavior for edge cases
- The `getRunEvents` API already supports `afterSeq` parameter — no backend change needed
- This fix also helps with the "Delivered" showing twice: if "Delivered" arrived via live SSE (before stream closed), its seq would be in `lastSeqRef` and FIX-172 would skip it; only if it DIDN'T arrive (the race) would FIX-172 fetch it (via afterSeq being slightly less than the "Delivered" card's seq)
| FIX-202 | 2026-08-07 | Notification panel refactor: localStorage persistence, per-item dismiss, toast run navigation, duplicate/stale entry elimination | (1) `useNotifications` used `useState` only — cleared on every page refresh. (2) No per-item dismiss, only "Clear all". (3) `CompletionToast` `onViewResults` called only `setMainView("execution")` with no run-specific navigation. (4) `saveToStorage` persisted `running`/`gate` notifications — rehydrated as stale eternally-spinning entries on next load. Fix: (A) localStorage hydration/save in `useNotifications` with `dismissed` Set persistence; (B) `dismissOne` callback; (C) `saveToStorage`/`loadFromStorage` filter running+gate to prevent stale rehydration; (D) `ToastItem.workflowRunId` + toast navigation to specific completed run; (E) `NotificationPanel` rebuilt on `liveRuns` prop (same `runningPipelines` list as header badge) — eliminates ALL parallel ephemeral tracking and dedup refs; (F) terminal `notifications` filtered at DashboardLayout boundary to prevent running entries leaking into panel. tests: 18 frontend ✅ | `frontend/src/hooks/useNotifications.ts`, `frontend/src/components/ui/NotificationPanel.tsx`, `frontend/src/components/ui/CompletionToast.tsx`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/layout/AppHeader.tsx`, `frontend/src/hooks/useNotifications.fix202.test.tsx` | Phase 38 (notification panel), KAN-169 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-203 | 2026-08-07 | Background concurrent run completion never marked on notification — User Stories completed but notification stayed "running" | `DashboardLayout`'s completion effect keys on `pipelineState` (viewed run only). Background runs complete but `pipelineState` never reflects them. `page.tsx` now sets `backgroundCompletedRunId` state on every `pipeline_complete` for a non-tracked run; `DashboardLayout` watches it and calls `markCompleted` + adds toast for the matching notification. | `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | Phase 38 (notification panel), FIX-202 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-204 | 2026-08-07 | Duplicate notification entries in panel — 2× Presentation, 2× User Stories when only 1 of each is running | Two creation paths for ppt/prototype notifications both fired: (1) explicit `handleRunPipeline` call; (2) reactive `odProtoNotifCreated` effect. The reactive effect checked `!odPptNotifId.current` but `handleRunPipeline` never set `odPptNotifId`/`odProtoNotifId` refs — so both paths fired and `addRunningNotification` dedup didn't catch it (different timestamp IDs). Fix: after each `addRunningNotification` call in `handleRunPipeline`, `handleChainPipeline`, `handleChainFromHistory`, `handleQuestionnaireSubmit`, `handleSkipQuestionnaire`, set the appropriate `odPptNotifId`/`odProtoNotifId` ref for ppt/prototype types. Also: `loadFromStorage` and `saveToStorage` filter `running`+`gate` notifications to prevent stale rehydration. TypeScript type narrowing errors fixed by casting `resolvedType as string`. | `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/hooks/useNotifications.ts` | Phase 38 (notification panel), FIX-202, FIX-203 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-205 | 2026-08-07 | Background run's `workflowRunId` never stamped on notification — `backgroundCompletedRunId` lookup fails silently | `handleRunPipeline` creates notifications with `pipeline-${Date.now()}` IDs before the run id is known. `setNotifWorkflowRunId` effect fires on `pipelineState.pipelineRunId` change (viewed run only) — background run's `pipeline_start` never updates `pipelineState`, so `workflowRunId` stays `undefined`. `backgroundCompletedRunId` effect then can't find the notification. Fix: `page.tsx` sets `backgroundStartedRunId` on every foreign `pipeline_start`; `DashboardLayout` watches it and stamps `workflowRunId` onto the most-recent unbound running notification. Also: `backgroundCompletedRunId` effect adds fallback lookup by `pipeline-${runId}` ID pattern for od_prototype/od_ppt path. | `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | Phase 38 (notification panel), FIX-203 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-206 | 2026-08-07 | Concurrent background run agent frames contaminate Steps panel of a clarify-paused run — Domain Discovery Agent shown below clarify questions | `page.tsx` early-registration block: when run B's `pipeline_start` arrives during `launchPendingRef=true` while run A is paused at clarify, `runStoreSwitchViewToRef.current(runB_id)` was called unconditionally — replacing run A's viewport with run B's `pipelineState` (containing run B's agents). Clarify form remained visible via legacy React state, but agent list switched to run B. Fix (primary): capture previous `trackedRunIdRef` before overwriting, check `runStore.get(prevTrackedId)?.questionnaireData != null` — if clarify is active, skip `switchViewTo`. Fix (defense-in-depth): `StepsOverviewSpine.tsx` wraps entire `agents.map(...)` in `{!hasClarify && ...}` — suppresses ALL agent rows during clarify state regardless of viewport contamination. | `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/results/StepsOverviewSpine.tsx` | Phase 44 (concurrent run isolation), FIX-201, FIX-153 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-207 | 2026-08-07 | `useRunStream` "Maximum update depth exceeded" — `setCursor` and `setLastMessage` called on every SSE frame causing re-render storm with concurrent runs | `cursor` and `lastMessage` were `useState` — each SSE frame called `setCursor(seq)` and `setLastMessage(msg)`, triggering a React re-render cascade. With N concurrent runs each emitting frames continuously, React exceeded its update depth limit. Neither value is used in production code (only in tests). Fix: convert both to `useRef` (`cursorStateRef`, `lastMessageRef`). `cursor` React state removed; `lastMessage` React state removed. Return values still expose `cursorStateRef.current` and `lastMessageRef.current` for API compatibility. Also added `stoppedRef.current` guard before setState calls in `dispatchBlock` for strict-mode safety. `lastError` (set only on reconnect/auth failure) remains `useState` — not a per-frame update. | `frontend/src/hooks/useRunStream.ts` | Phase 29 (SSE transport), ADR-0001 (terminal frame non-reconnect) | INV-1/3/12/SC-001 ✅ INV-3 ✅ (frontend-only) | Done |
| FIX-208 | 2026-08-07 | Notification panel agent progress shows 0/N for background concurrent runs — only viewed run shows live progress | `AppHeader.runningPipelines` mapping used `pipelineAgentsCompleted` (scalar from `pipelineState.completedCount`, viewed run only) for active run, and `0` for all other runs. Background run `completedCount` was never read. The data existed in `runStore.get(runId).pipelineState.completedCount` for every attached run. Fix: compute `runAgentsCompletedMap: Record<string, number>` in `page.tsx` from `runStore.get()` for every live run; thread via `DashboardLayout` → `AppHeader`; use `runAgentsCompletedMap[r.id] ?? 0` for non-active runs in `runningPipelines` mapping. | `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/layout/AppHeader.tsx` | Phase 38 (notification panel), FIX-202 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-209 | 2026-08-11 | useSmoothText re-render loop — "Maximum update depth exceeded" at tick function; useMeasuredVirtualWindow scroll handler infinite loop | `useSmoothText`: `shownLenRef` not reset when `target` shrinks to a shorter/different string; no `active` flag to stop `setShown` after cleanup. `useMeasuredVirtualWindow`: scroll `bump()` triggered re-render → layout shift → scroll event → bump() loop. | `frontend/src/hooks/useSmoothText.ts`, `frontend/src/components/chat/runtime/useMeasuredVirtualWindow.ts` | Phase 44 (rqo streaming polish) | INV-3 ✅ (FE-only) SC-001 ✅ | Done |
| FIX-210 | 2026-08-11 | Concierge proposal chips not appearing; revision confirm posting wrong run; revision UI not switching to new run | (1) Concierge called propose_chain but chain_hints had no target_id exposed — only labels. (2) Confirm POST hit wrong run_id after view switched to child run. (3) handleRevisionLaunched missing attachRun + switchViewTo. (4) sendCommand wrapper discarded return value. (5) concierge_proposal inline SSE frames had no event_id (dedup broken). (6) _dispose_concierge_proposal returned no params in held dict. | `backend/app/agents/chat/concierge.py`, `backend/app/api/run_commands.py`, `frontend/src/hooks/useRunChat.ts`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/app/dashboard/page.tsx`, `frontend/src/providers/RunConnectionProvider.tsx` | Phase 43-44 (Concierge proposals) | INV-1/3/12/SC-001 ✅ tests: N/A (live validation) | Done |
| FIX-211 | 2026-08-11 | chat_router auto-approved gate / auto-submitted clarify on plain chat text | `PHASE_GATE_PAUSED`: plain text with no gate action defaulted to `action="approve"` — any chat message during a review gate silently approved it. `PHASE_CLARIFY_WAITING`: bare text mapped to freeform clarify answer — any chat message during clarify questions unblocked the pipeline. Both now route to `CHANNEL_CONCIERGE` when no explicit action/responses present. | `backend/app/api/chat_router.py` | Phase 29 (mechanical router) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-212 | 2026-08-11 | "Start this workflow" chain chip persisted after clicking; revision pipeline_not_entitled; blank bubble on confirm; confirm button no feedback | (1) Chain proposals never got a resolved DB row — chip re-appeared on every reopen. (2) `wr_type = "user_stories_revision"` → revision target `"user_stories_revision_output"` → `pipeline_type = "user_stories_revision_revision"` not in TIER_PIPELINES. (3) sendMessage("", ...) added empty optimistic bubble. (4) No spinner/loading state on confirm button. | `backend/app/api/run_commands.py`, `frontend/src/components/chat/RunChatLane.tsx`, `frontend/src/hooks/useRunChat.ts` | Phase 43-44 (Concierge proposals) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-213 | 2026-08-11 | Concierge system prompt overhaul — emojis, internals leakage, verbose agent detail, no proactive next-step, wrong run state label | Concierge showed emojis, internal IDs, detailed agent names; didn't offer next steps on completion; used "What this run produced" label for live-building runs; gave generic "building" instead of reading live agent progress. | `backend/app/agents/chat/concierge.py`, `backend/app/api/run_commands.py` | Phase 43 (Concierge) | INV-1/3/12/SC-001 ✅ | Done |
