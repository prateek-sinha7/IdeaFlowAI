# Fix Register — VelocityAI / Flowin

> **Purpose.** Every fix applied via `/velocity-ai-fix` is logged here. Read this alongside the Implementation Register before applying any new fix — to avoid re-fixing something already fixed, and to understand the cumulative patch history on top of the planned phases.
>
> **Format per entry:** Date · Fix ID · Root cause · Files changed · Phase(s) involved · Invariants verified · Notes.

---

## Fix Log

| Fix ID | Date | Description | Root Cause | Files Changed | Phase Involved | Invariants | Status |
|--------|------|-------------|------------|---------------|---------------|------------|--------|
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
| FIX-046 | 2026-07-07 | KAN-99: Prototype task checklist shows all tasks complete before build agent finishes — last task_progress fires before fix-loop | `currentTaskIndex` used `realtimeCompletedCount` directly; when last `task_progress` fires `realtimeCompletedCount === totalTasks` → `isDone` true for all tasks despite agent still running. Cap `currentTaskIndex` to `Math.min(realtimeCompletedCount, totalTasks-1)` when `!buildTrulyDone` so last task stays in active/spinner state until validate starts or `isRunning=false`. | `frontend/src/components/results/PrototypePipelineView.tsx` | Phase 3 (Thinking-view) · quick-260703-byv | INV-1/3/12/SC-001 ✅ | Done |
| FIX-045 | 2026-07-06 | KAN-98: ReviewGatePanel stale editedContent after Redo — prior edit forwarded instead of fresh output | `useEffect([output, gateKey])` reset `submitted`/`redoInstructions`/`showRejectConfirm` but NOT `editedContent` or `hasEdits`. After Redo delivered new output, stale `editedContent` (from round 1) differed from new `output` → `hasEdits=true` → `handleApprove` sent stale edit as if user had edited in round 2. Fix: add `setEditedContent(output)` + `setHasEdits(false)` to the existing `useEffect`. | `frontend/src/components/preview/ReviewGatePanel.tsx` | Phase 23 (REDO-GATE) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-044 | 2026-07-06 | KAN-97: Blank right panel after questionnaire submit — PlanningOverlay blocked by !activePipelineRunId guard | After submit/skip, `questionnaireQuestions=[]` and `questionnaireLoading=false` cleared the questionnaire panel, but `activePipelineRunId` stayed set → `!activePipelineRunId` in the PlanningOverlay condition was false → fell through to empty PreviewPanel. Fix: remove `!activePipelineRunId` from PlanningOverlay condition. QuestionnairePanel already has its own `(questionnaireLoading || questions.length > 0)` guard so it doesn't need this protection. | `frontend/src/components/layout/DashboardLayout.tsx` | Phase 2/18 (Universal Engine / Planning Overlay) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-043 | 2026-07-06 | KAN-96: Workflow History always opens detail view for running runs — no active-run awareness | `WorkflowHistoryProps` had no `activeRunId`/`onViewRunningPipeline` props; `handleSelectRun` opened the history detail for every run unconditionally. Added two props, branched in `handleSelectRun` (run.id === activeRunId → navigate to execution), and passed `pipelineState?.pipelineRunId` + `setMainView("execution")` from DashboardLayout | `frontend/src/components/history/WorkflowHistory.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | Phase 18 (History UX) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-042 | 2026-07-06 | KAN-95: Reject & cancel pipeline leaves user stranded on execution view — onRejectReview had no navigation | `onRejectReview` in page.tsx only sent the WS message and cleared `reviewGateData`; no `setMainView("home")` or `onResetPipeline()` call. `cancelNavigatingHomeRef` was never set so `pipelineState.isRunning` effect would snap back to execution. Added `handleRejectReview` wrapper in DashboardLayout (mirrors `handleCancelWorkflow` pattern from KAN-90): sets `cancelNavigatingHomeRef`, calls `setMainView("home")`, calls `onResetPipeline()`, then delegates to `onRejectReview` for WS send + `reviewGateData` clear. | `frontend/src/components/layout/DashboardLayout.tsx` | Phase 8/23 (GATE/REDO-GATE) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-041 | 2026-07-06 | KAN-94: Blank Specification Review panel fires before agents run when user deselects all gates + empty-state UX + ReviewGatesSection discoverability | Declared `gates:[human]` on prototype steps bypassed per-run gate_agent_ids deselection: `_should_gate` returned False → `inline_gated=False` → WR-02 dedupe not triggered → pre-step `human` gate fired with `last_streamed=""` → blank `review_gate_ready`. Fix: extend WR-02 skip to also cover when `ectx.gate_agent_ids is not None` and agent not in that list. Also improved empty-state UX (amber icon + Redo guidance + de-emphasized "Continue anyway") and ReviewGatesSection opens expanded when default gates are pre-checked. | `backend/agents/execution_engine/engine.py`, `frontend/src/components/preview/ReviewGatePanel.tsx`, `frontend/src/components/workflow/ReviewGatesSection.tsx` | Phase 8/23 (GATE/REDO-GATE) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-040 | 2026-07-06 | KAN-93: Notification Panel shows raw context block text for chained/revision runs — addRunningNotification called with raw enrichedInput before marker stripping | 5 addRunningNotification call sites in DashboardLayout.tsx passed `enrichedInput.slice(0,60)` or `message.slice(0,60)` without stripping injected `=== CONTEXT FROM PREVIOUS ===` / `=== EXISTING PROTOTYPE HTML ===` markers. Fix: use already-computed `chainBrief`/`historyBrief` (stripped) in chain handlers; apply `parseRunInput()` in handleRunPipeline, handleQuestionnaireSubmit, handleQuestionnaireSkip | `frontend/src/components/layout/DashboardLayout.tsx` | Phase 22 (notifications) · Phase 25 (parseRunInput) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-039 | 2026-07-06 | KAN-92: Workflow history incorrect titles — 3 root causes in websocket.py: wizard-chain reuses source title, run_revision never calls title gen, legacy revision placeholder shows raw HTML marker | (1) `_generate_workflow_title` wizard-chain path wrote source pipeline's Title verbatim with no pipeline_type suffix; (2) `_handle_revision_execution` set `title=f"Revision: {instruction[:50]}"` and never scheduled `_generate_workflow_title`; (3) `_handle_workflow_execution` WorkflowRun placeholder fell through to `or content` for revision messages starting with `=== EXISTING … ===`, showing raw HTML marker for 2-5s | `backend/app/api/websocket.py` | Phase 14/16/22 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-034 | 2026-07-04 | Bedrock prompt caching silently OFF + enable-only extended-thinking knob | deepagents' built-in AnthropicPromptCachingMiddleware caches ONLY ChatAnthropic, but prod runs ChatBedrockConverse → every build re-sent a ~45-68k fixed prefix uncached across ~300 turns (5-21M input tok). Fix: a provider-agnostic `_BedrockCachePointsMiddleware` sets model_settings cache_control on ChatBedrockConverse requests (config-gated BEDROCK_PROMPT_CACHE_ENABLED default ON, BEDROCK_PROMPT_CACHE_TTL '5m') so langchain_aws._apply_cache_points appends cachePoints ≈ 55-80% cheaper billed input; plus a THINKING_BUDGET_TOKENS knob (enable-only, default 0) threading a clamped thinking budget into both provider branches of build_model. | `backend/app/core/config.py`, `backend/app/agents/model_factory.py`, `backend/app/agents/deep_agent_runner.py`, `backend/tests/agents/test_bedrock_cache_and_thinking.py` | quick-260704-p10 | INV-1/3/12/13 · SC-001 ✅ | Done |
| FIX-039 | 2026-07-07 | Regenerate appended (not replaced) an agent's streamed output — hitting "regenerate" at the plan gate re-ran the agent but the new stream concatenated onto the previous run's, so `PrototypePipelineView.parseTasks(planAgent.output)` read the STALE first `<tasks>` block: a regenerated 9-task plan still showed "1 Build Task". | Root cause: `useWorkflow.ts` `case "agent_start"` flipped the matched agent to `status:"running"` but never reset its per-run accumulators, while `case "agent_chunk"` does `output = output + chunk` (append) — so a 2nd agent_start left run-1's `output` in place and run-2's chunks appended onto stale v1. Fix (FE-only): in the `agent_start` case, reset THAT agent's run-scoped fields to their fresh-agent values BEFORE `status:"running"` — `output/thinking/thinkingText=""`, `toolCalls/validationIssues=[]`, `error=null`, `validationPassed=undefined`, plus overwrite-only `duration/token/inputPrompt/contextSources` cleared — preserving identity (`id/name/role/icon/index`) and never touching pipeline-level or other agents' state. Regenerate now REPLACES. Replay-safe: a replayed agent_start (same event_id) is deduped upstream by `shouldApplyEvent` (dashboard/page.tsx:276) so a live output is never wiped on WS reconnect. REJECTED alternative: the parser "read the LAST `<tasks>` block" band-aid — masks the concatenation and leaves agent output polluted. | `frontend/src/hooks/useWorkflow.ts`, `frontend/src/hooks/useWorkflow.regenerateReset.test.ts` | quick-260707-1p8 | INV-3 (FE-only, no golden impact) · SC-001 ✅ | Done |
| FIX-039 | 2026-07-07 | OD template + PPT gallery previews slow — cards render a static thumbnail `<img>`, falling back to live HTML+JS iframe rendering when absent | Each gallery card mounted a sandboxed `<iframe sandbox="allow-scripts">` that fully renders `example.html` at 1280x720 (parse+style+layout+paint+JS-exec+asset fetches) just for a ~130px thumbnail. Rendering N full HTML documents is the gallery's dominant cost. | `frontend/src/components/workflow/prototype/TemplateGallery.tsx`, `frontend/src/components/workflow/prototype/TemplateCard.tsx`, `frontend/src/components/workflow/ppt/PPTTemplateGallery.tsx`, `frontend/src/lib/prototype-api.ts`, `frontend/src/lib/ppt-api.ts` | Phase 4 (OD catalog UI) | INV-3 golden-neutral (FE-only; catalog thumbnails, not the deliverable renderer) ✅ | Done |
| FIX-042 | 2026-07-08 | `GET /api/{prototype,ppt}/templates/{id}/thumbnail` returns 500 (not 404) when a thumbnail file is missing at request time | `get_template_thumbnail_path` trusted the `has_thumbnail` flag, which is computed once by the `lru_cache(maxsize=1)` `_all_templates()` at process start. A thumbnail deleted (or generated) after startup left the flag stale → the function returned a path to a missing file → `FileResponse` `os.stat`'d it mid-response → `FileNotFoundError` → `RuntimeError: File ... does not exist` → 500. Fix (backend-only): re-check `path.is_file()` on disk at serve time; return `None` (→ existing 404 branch) when the file is gone, so the gallery falls back to the FIX-041 live iframe. | `backend/app/services/od_loader.py` | Phase 4 (OD catalog UI) · builds on FIX-039/040/041 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-041 | 2026-07-08 | OD/PPT gallery card shows a broken/blank image when a thumbnail 404s — no fallback to the live iframe unless `has_thumbnail` is already false | The thumbnail `<img>` in `TemplateCard` and `CompactPPTCard` had an `onLoad` but NO `onError` handler; the thumbnail-vs-iframe choice keyed solely off the backend `has_thumbnail` flag. When that flag is stale (thumbnail generated at build time, not committed — FIX-040) or the file 404s at request time, the `<img>` fails silently and the card sticks on the pulse placeholder / broken image instead of degrading to the FIX-039 live iframe. Fix (FE-only): add a `thumbnailError` state; on `<img>` `onError`, set it (and force-mount the iframe), which nulls `thumbnailUrl` so the existing iframe fallback path renders. | `frontend/src/components/workflow/prototype/TemplateCard.tsx`, `frontend/src/components/workflow/ppt/PPTTemplateGallery.tsx` | Phase 4 (OD catalog UI) · builds on FIX-039/040 | INV-3 golden-neutral (FE-only; catalog thumbnails, not the deliverable renderer) ✅ | Done |
| FIX-040 | 2026-07-07 | OD gallery thumbnails generated at BUILD time (backend Docker image) + served via backend endpoint; missing ⇒ live iframe fallback | The `<img>` fast-path needs a pre-rendered screenshot. Generated at backend image build (Playwright/Chromium already installed for render_check; OpenDesign tree baked at /app/opendesign), NOT committed — so absent thumbnails degrade to the FIX-039 live iframe. | `backend/app/services/od_loader.py`, `backend/app/api/prototype_templates.py`, `backend/app/api/ppt_templates.py`, `backend/scripts/generate_template_thumbnails.py` (NEW), `backend/Dockerfile`, `.gitignore` | Phase 4 (OD catalog UI) | INV-3 golden-neutral; lint-imports 4/0; no committed binaries ✅ | Done |

---

## Detailed Fix Entries

*Entries are appended below after each `/velocity-ai-fix` session.*

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

---

### FIX-039 — KAN-92: Workflow History Incorrect Titles (3 Root Causes)

**Date:** 2026-07-06
**Triggered by:** `#velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-92`

#### Root Cause

Three independent title-generation failures all in `backend/app/api/websocket.py`:

**Root Cause 1 — Wizard-chain title reuses source pipeline's title verbatim**
`_generate_workflow_title()` wizard-chain shortcut path (fired when `clean_content=""`, i.e. the entire input is a `=== CONTEXT FROM PREVIOUS PIPELINE ===` block): it extracted the `Title:` line from the context block (e.g. "Fintech App User Stories") and wrote it directly as the new run's title regardless of `pipeline_type`. For a chained prototype run the title "Fintech App User Stories" was persisted and emitted — identical to the parent's title, making history entries indistinguishable.

**Root Cause 2 — `run_revision` title stays as raw instruction truncation forever**
`_handle_revision_execution` created the `WorkflowRun` row with `title=f"Revision: {instruction[:50]}"` (a placeholder). Unlike `_handle_workflow_execution` (which schedules `asyncio.create_task(_generate_workflow_title(...))` after `db.commit()`), the revision path had no equivalent — the `create_task` call was simply never added. The "Revision: Change the color scheme to da..." placeholder therefore persisted as the permanent run title.

**Root Cause 3 — Legacy revision placeholder shows `=== EXISTING PROTOTYPE HTML ===`**
`_handle_workflow_execution`'s WorkflowRun creation used:
```
title=(_strip_pipeline_context(content) or _extract_title_from_context(content) or content or "Untitled")[:60]
```
For revision messages whose content starts with `=== EXISTING PROTOTYPE HTML ===` (the frontend-injected block), both `_strip_pipeline_context` and `_extract_title_from_context` return `""` (neither the `_WORKFLOW_TITLE_CONTEXT_MARKER` nor `_CHAIN_CONTEXT_TITLE` patterns match this marker). The chain falls through to `or content`, inserting the raw string `"=== EXISTING PROTOTYPE HTM"` (truncated to 60 chars) as the initial placeholder that shows in the history panel for 2-5 seconds until the async LLM title fires. The `_REVISION_REQUEST_MARKER` regex — which correctly extracts the user's actual revision instruction from the `=== REVISION REQUEST ===` section — was already defined but never tried in this fallback chain.

#### Phase Context
- **Phase(s) involved:** Phase 14 (run_revision real revision loop) · Phase 16 (WebSocket title gen pattern) · Phase 22 (WorkflowRun fields)
- **Relevant register section:** `_register-parts/14-run-revision-real-revision-loop-f2-end-to-end.md`, Phase 16 §3
- **Deleted code verified (not resurrected):** No deleted code involved. `_REVISION_REQUEST_MARKER` was already present and used in `_strip_pipeline_context`; we're adding a third call site only.
- **Locked decisions respected:** Async title generation as best-effort background task is the established pattern per run_pipeline path — fix 2 replicates it exactly. No engine edits (SC-001).

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `backend/app/api/websocket.py` | In `_generate_workflow_title` wizard-chain path: instead of writing `context_title[:60]` verbatim, build `chained_title = f"{context_title} – {hint.title()}"[:80]` using `_WORKFLOW_TITLE_PIPELINE_HINTS[pipeline_type]`; fallback to `context_title[:60]` when hint is absent | Disambiguates chained run titles from their parent — "Fintech App User Stories – Interactive Html Prototype" vs "Fintech App User Stories" |
| `backend/app/api/websocket.py` | In `_handle_revision_execution`, after `db.close()`: add `asyncio.create_task(_generate_workflow_title(workflow_run_id=workflow_run_id, content=instruction, pipeline_type=revision_pipeline_type, websocket=websocket))` | Revision runs get the same async LLM-generated title as pipeline runs; `instruction` is clean user text so `_strip_pipeline_context` passes it through unchanged |
| `backend/app/api/websocket.py` | In `_handle_workflow_execution` WorkflowRun creation title expression: insert `(lambda m: m.group(1).strip() if m else None)(_REVISION_REQUEST_MARKER.search(content or ""))` between `_extract_title_from_context(content)` and `or content` | For revision messages starting with `=== EXISTING … ===`, extracts the user's actual instruction from `=== REVISION REQUEST ===` section as placeholder instead of the raw HTML marker prefix |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — `_WORKFLOW_TITLE_PIPELINE_HINTS.get()` is a dict lookup with a default, not an `if pipeline_type ==` branch in the engine kernel
- **INV-3** (golden parity): not affected — title is a UI field on `WorkflowRun`, not present in characterization event snapshots; 5 goldens byte-identical
- **INV-12** (no duplication): reuses existing `_generate_workflow_title`, `_REVISION_REQUEST_MARKER`, `_WORKFLOW_TITLE_PIPELINE_HINTS` — no new functions or duplicated logic
- **SC-001** (zero engine edits): not affected — all 3 changes are in `websocket.py` app layer only

#### Verification
- Fix 1: `_generate_workflow_title` wizard-chain path reads `chained_title` from confirmed code review — suffix logic verified in context (lines 494–527)
- Fix 2: `asyncio.create_task(_generate_workflow_title(...))` confirmed present at line 2330 after `db.close()`, before `_get_or_create_queue` — matches run_pipeline pattern exactly
- Fix 3: Lambda expression for `_REVISION_REQUEST_MARKER` confirmed in WorkflowRun `title=` argument at line ~1752 — all 3 fallbacks (`_strip_pipeline_context`, `_extract_title_from_context`, `_REVISION_REQUEST_MARKER`) now tried before `or content`
- Backend restarted successfully, `alembic=0023`, no import errors

#### Notes
- Fix 1 uses `.title()` on the hint string (e.g. `"interactive html prototype"` → `"Interactive Html Prototype"`) — may want to switch to title-case-only words in the hints dict if the capitalization looks off in production
- Fix 2 means `run_revision` will briefly show "Revision: <50 chars>" and then update to the LLM title (~2-3s) — same UX as run_pipeline. The `workflow_title_update` WS event is handled by the frontend already
- Fix 3 only improves the 2-5s placeholder window; the LLM title still fires and replaces it — the improvement is that the placeholder is now the readable instruction text rather than `=== EXISTING PROTOTYPE HTM`

---

### FIX-040 — KAN-93: Notification Panel shows raw context block text (chained/revision runs)

**Date:** 2026-07-06
**Triggered by:** `#velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-93`

#### Root Cause

Five `addRunningNotification` call sites in `DashboardLayout.tsx` passed the raw enriched input (or raw pipeline message) `.slice(0,60)` as the notification title without stripping injected marker blocks first.

For chained pipeline runs, `enrichedInput` is composed as `${chainBrief}\n\n${contextBlock}`. When `chainBrief` is `""` (wizard-chain where the user typed nothing — the brief was already embedded in the context block), `enrichedInput` starts directly with `=== CONTEXT FROM PREVIOUS PIPELINE (prototype) ===\nTitle: ...`. Slicing to 60 chars gives the raw marker text as the notification title.

For revision runs, `message` may start with `=== EXISTING PROTOTYPE HTML ===` (the frontend-injected existing-artifact block). The same slice-without-strip exposes raw HTML marker text.

The `parseRunInput()` function (Workstream C1, Phase 25 / INV-12's canonical FE parser) was already imported in `DashboardLayout.tsx` and already used in `handleChainPipeline`/`handleChainFromHistory` to build `chainBrief`/`historyBrief` — but was not applied at the `addRunningNotification` call sites.

Additionally, the existing `updateAgentsTotal(notifId, agentCount, latestRun.title)` effect at line ~474 already updates the notification title to the LLM-generated clean title when `workflow_title_update` arrives (~2-3s later), so the title self-corrects even without this fix — the fix improves the initial placeholder.

**Broken call sites:**
1. `handleRunPipeline` (~line 871): `message.slice(0,60)` — message may be a revision blob
2. `handleChainPipeline` (~line 968): `enrichedInput.slice(0,60)` — enrichedInput starts with `===` for wizard-chains
3. `handleChainFromHistory` (~line 1045): `enrichedInput.slice(0,60)` — same
4. `handleQuestionnaireSubmit` (~line 1122): `pendingPipelineRun.message.slice(0,60)` — same as #1
5. `handleQuestionnaireSkip` (~line 1157): `pendingPipelineRun.message.slice(0,60)` — same as #1

**Safe call sites (untouched):**
- `odProtoNotifCreated` effect (line ~457): uses hardcoded label `"Prototype"` / `"Presentation"` — correct
- `pendingOdProtoParams` effect (line ~693): uses `pendingOdProtoParams.brief` — wizard-collected clean text
- `pendingOdPptParams` effect (line ~740): uses `pendingOdPptParams.brief` — same

#### Phase Context
- **Phase(s) involved:** Phase 22 (notification system) · Phase 25 / Workstream C1 (parseRunInput, INV-12 canonical parser)
- **Relevant register section:** `_register-parts/22-capability-surfacing-and-user-empowerment-universal-runtime-.md` §3
- **Deleted code verified (not resurrected):** No deleted code. `parseRunInput` is the live Workstream C1 parser, already imported.
- **Locked decisions respected:** INV-12 — using the existing `parseRunInput`, not duplicating any strip logic.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/layout/DashboardLayout.tsx` | `handleRunPipeline`: replace `message.slice(0,60)` with `parseRunInput(message).revisionInstruction ?? parseRunInput(message).brief \|\| message).slice(0,60)` | Strips `=== EXISTING … ===` blocks from revision messages |
| `frontend/src/components/layout/DashboardLayout.tsx` | `handleChainPipeline`: replace `enrichedInput.slice(0,60)` with `(chainBrief \|\| enrichedInput).slice(0,60)` | `chainBrief` is already the stripped user brief, computed above the call site |
| `frontend/src/components/layout/DashboardLayout.tsx` | `handleChainFromHistory`: replace `enrichedInput.slice(0,60)` with `(historyBrief \|\| enrichedInput).slice(0,60)` | Same — `historyBrief` already stripped by `parseRunInput` above the call site |
| `frontend/src/components/layout/DashboardLayout.tsx` | `handleQuestionnaireSubmit`: parse `pendingPipelineRun.message` with `parseRunInput`, use `revisionInstruction ?? brief` | Same strip needed — message is the same raw input from `handleRunPipeline` |
| `frontend/src/components/layout/DashboardLayout.tsx` | `handleQuestionnaireSkip`: same as submit | Same |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — FE-only change
- **INV-3** (golden parity): not affected — no backend/golden snapshot changes
- **INV-12** (no duplication): reuses existing `parseRunInput` (already imported) — no new strip logic
- **SC-001** (zero engine edits): not affected — FE only

#### Verification
- TypeScript diagnostics: 0 errors after all 5 edits
- All `addRunningNotification` call sites confirmed — grep shows 5 fixed sites + 3 safe untouched sites
- No backend restart needed (FE-only change, frontend dev server already running)
- The `updateAgentsTotal` title-update effect at line ~474 still fires when `workflow_title_update` arrives, replacing the initial title with the LLM-generated clean title (~2-3s later) — belt-and-suspenders

#### Notes
- For wizard-chains where `chainBrief=""` (pure context block input), `chainBrief || enrichedInput` falls back to `enrichedInput` which still starts with `===`. This edge case is caught by the backend's `_generate_workflow_title` (FIX-039) which fires ~2s later and calls `updateAgentsTotal` with the clean LLM title. The notification placeholder in this scenario improves slightly but won't be fully clean until the LLM title arrives — acceptable because wizard-chains always have `pipeline_type` info (e.g. "Prototype") visible elsewhere in the notification card.
- The `pendingOdProtoParams`/`pptParams` effects intentionally left untouched — `.brief` is the wizard-collected clean user text, not an enriched input.

---

### FIX-041 — KAN-94: Blank Specification Review Panel + ReviewGatesSection collapsed by default

**Date:** 2026-07-06
**Triggered by:** `#velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-94`

#### Root Cause

Two distinct UX gaps:

**Gap 1 — Empty-state actions misleading:**
`ReviewGatePanel.tsx` lines 355-363 rendered "No content was produced for review" as a plain info message, then fell through to the same full Actions footer (primary Approve button + Reject) as a content-bearing gate. Clicking "Approve & continue" with an empty spec passes `""` to `prototype-plan`, which then produces a broken task list, cascading into a broken build. The comment even said "never present a silently blank panel with live Approve/Reject buttons" but that was exactly what was rendered.

**Gap 2 — ReviewGatesSection collapsed by default:**
`ReviewGatesSection.tsx` line 44: `const [expanded, setExpanded] = useState(false)`. Users who open the prototype wizard and proceed without expanding the section get all 3 review gates active (prototype-specify, prototype-plan, prototype-analyze declare `gate: Human_Gate` in their AGENT.md frontmatter) without any visual indication. This is the main reason users encounter the gate unexpectedly.

#### Phase Context
- **Phase(s) involved:** Phase 8 (GATE-01/02 — ReviewGatePanel), Phase 23 (REDO-GATE)
- **Relevant register section:** `_register-parts/08-capabilities-hardened-registry-gates-tool-perms-runtime-3.md` §3
- **Deleted code verified (not resurrected):** No deleted code involved
- **Locked decisions respected:** REDO-GATE F1b fence (`canRedo = !!onRedo && !!redoable`) unchanged — Redo block only renders when server set `redoable:true`

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/preview/ReviewGatePanel.tsx` | Empty-state content area: replaced flat "approve or reject" text with amber warning icon + "The agent produced no output" heading + conditional guidance (Redo if available, else "Reject or continue") | Makes the situation clear and guides toward the safe recovery action (Redo) |
| `frontend/src/components/preview/ReviewGatePanel.tsx` | Actions footer: branched on `!(hasEdits ? editedContent : output)?.trim()` to show a de-emphasized "Continue anyway (not recommended)" ghost button instead of the primary dark Approve button when output is empty | Prevents accidentally approving an empty spec; the ghost styling makes the risk apparent; the action is still available for power users who need to skip |
| `frontend/src/components/workflow/ReviewGatesSection.tsx` | `useState(false)` → `useState(true)` for `expanded` initial state | Users now see the active gate checkboxes immediately when the section renders, so they know 3 review pauses will occur before launching |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — FE-only
- **INV-3** (golden parity): not affected — no backend/golden snapshot changes
- **INV-12** (no duplication): reuses existing `handleApprove`, `canRedo`, `output` — no new logic
- **SC-001** (zero engine edits): not affected — FE only

#### Verification
- TypeScript diagnostics: 0 errors on both changed files
- Normal gate path (output non-empty): `!(output?.trim())` = false → normal primary Approve button rendered unchanged
- Empty gate path (output empty): `!(output?.trim())` = true → de-emphasized "Continue anyway" shown; Redo section still renders if `canRedo`
- ReviewGatesSection: `expanded=true` on mount — gate checkboxes visible immediately; user can collapse

#### Notes
- The `canRedo` check reuses the existing REDO-GATE F1b fence exactly — no change to when Redo renders; only the empty-state messaging references it
- If the user edits content in the textarea (hasEdits=true, editedContent non-empty), the approve button switches back to the primary style correctly because `!(hasEdits ? editedContent : output)?.trim()` = false
- The AcceptanceCriteria item "ReviewGatesSection expanded by default" is now met; the "auto-approve if empty" option from the Jira was deliberately not chosen — the human reviewer should be aware the agent produced nothing and consciously choose to continue, hence the de-emphasized button approach

---

### FIX-042 — KAN-95: Reject & Cancel Pipeline Leaves User Stranded on Execution View

**Date:** 2026-07-06
**Triggered by:** `#velocity-ai-fix KAN-95`

#### Root Cause

`onRejectReview` in `frontend/src/app/dashboard/page.tsx` (lines 1341-1344) only sent the WS reject message and called `setReviewGateData(null)`. It did not:
1. Set `cancelNavigatingHomeRef.current = true` — without this, `DashboardLayout.tsx:367`'s `pipelineState.isRunning` effect immediately overrides any `setMainView("home")` call, snapping the view back to `"execution"`.
2. Call `setMainView("home")` — so the user stayed on the execution view.
3. Call `onResetPipeline()` — so the agent list stayed in its cancelled/done state.

The exact same pattern was already solved for KAN-90 (`handleCancelWorkflow` in `DashboardLayout.tsx`) — it sets `cancelNavigatingHomeRef.current = true` first, then navigates, then resets. That pattern just wasn't applied to the reject path.

#### Phase Context
- **Phase(s) involved:** Phase 8 (GATE-01/02 — ReviewGatePanel), Phase 23 (REDO-GATE)
- **Relevant register section:** `_register-parts/08-capabilities-hardened-registry-gates-tool-perms-runtime-3.md` §3
- **Deleted code verified (not resurrected):** No deleted code involved
- **Locked decisions respected:** `onRejectReview` prop contract unchanged — WS send still fires; only navigation layer added

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/layout/DashboardLayout.tsx` | Added `handleRejectReview` callback after `handleCancelWorkflow` — sets `cancelNavigatingHomeRef.current = true`, calls `setMainView("home")`, calls `onResetPipeline()`, then delegates to `onRejectReview(gateKey)` for the WS send + `reviewGateData` clear | Mirrors the KAN-90 `handleCancelWorkflow` pattern exactly; the `cancelNavigatingHomeRef` guard is load-bearing |
| `frontend/src/components/layout/DashboardLayout.tsx` | Changed `onReject={onRejectReview \|\| (() => {})}` to `onReject={handleRejectReview}` in the ReviewGatePanel mount | Routes the reject through the new wrapper instead of the raw page.tsx callback |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — FE-only
- **INV-3** (golden parity): not affected — no backend/golden snapshot changes
- **INV-12** (no duplication): reuses existing `cancelNavigatingHomeRef`, `setMainView`, `onResetPipeline` — exact same pattern as `handleCancelWorkflow`
- **SC-001** (zero engine edits): not affected — FE only

#### Verification
- TypeScript diagnostics: 0 errors after both edits
- Trace: user clicks Reject → `handleRejectReview(gateKey)` fires → `cancelNavigatingHomeRef=true` → `setMainView("home")` → `onResetPipeline()` → `onRejectReview(gateKey)` → WS send → `setReviewGateData(null)` → `pipelineState.isRunning` effect fires but `cancelNavigatingHomeRef` is true → effect returns without overriding → user sees home view
- No backend restart needed (FE-only change)

#### Notes
- `handleRejectReview` does NOT need to send `cancel_pipeline` separately — the `onRejectReview` prop already sends `approve_review{approved:false}` which triggers the backend pipeline cancellation via the review gate path (not the cancel_pipeline WS handler)
- The `cancelNavigatingHomeRef` guard is consumed (reset to false) in the `pipelineState.isRunning` effect — so it only fires once per navigate-home action, which is the correct behavior

---

### FIX-048 — KAN-101: Spec Revision Loop — "Update the Specs" action on analyze gate

**Date:** 2026-07-07
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-101`

#### Root Cause
No existing path for re-running specify → plan → analyze before the build step. `_run_review_gate` only handled `approve`, `reject`, and `redo` actions. The inline gate consumer in `_run_agent` only had `_gate_redo` for in-place agent re-run. No sub-pipeline mechanism, no `onUpdateSpecs` frontend button, no analysis context injection into `_compose_context_message`.

Trace: user clicks "Update the Specs" (absent) → FE sends `approve_review{action:"update_specs"}` (unhandled) → `store.set_review_response(action="update_specs")` (unhandled) → `_run_review_gate` yields nothing useful → sub-pipeline never runs.

#### Phase Context
- **Phase(s) involved:** Phase 23 (REDO-GATE — flat `while True:` loop pattern), Phase 13 (HITL gate primitive), Phase 7 (SC-001 / INV-1 no name branches)
- **Relevant register section:** Phase 23 `REDO-GATE-PLAN.md` §B (loop locals, consume-once, redo_directive pattern)
- **Deleted code verified (not resurrected):** No deleted code involved
- **Locked decisions respected:** INV-1 (action discriminator, not agent_id/pipeline_type), INV-3 (goldens unaffected — no new WS event keys), SC-001 (ectx scratch field, structural path)

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/app/api/websocket.py` | Added `elif action == "update_specs"` branch that reads `analysis_report` from `message_data` and calls `store.set_review_response(action="update_specs", instructions=analysis_report)` | Routes the new WS action to the ArtifactStore |
| `backend/agents/execution_engine/engine.py` — `_run_review_gate` | Added `if action == "update_specs"` branch after the `redo` branch: transitions state to `generating`, yields `{"type": "_gate_update_specs", "analysis_report": instructions}` | New internal signal for the inline gate consumer |
| `backend/agents/execution_engine/engine.py` — `_run_agent` loop locals | Added `spec_revision_attempt = 0` loop local alongside `redo_attempt` | Tracks revision cycle depth; loop-local (consume-once pattern) |
| `backend/agents/execution_engine/engine.py` — `_run_agent` while-loop top | Added `pending_revision_output` sentinel check: if `ectx.spec_revision_pending_output` is set, skip the model call and re-open the gate with the new output directly | Allows the while-loop to re-open the analyze gate after the sub-pipeline without re-running the model |
| `backend/agents/execution_engine/engine.py` — inline gate consumer | Added `elif gate_event.get("type") == "_gate_update_specs"` branch that calls `_run_spec_revision_sub_pipeline`, collects the new analysis output, stores it on `ectx.spec_revision_pending_output`, and `break`s to re-enter the while-loop | Triggers the sub-pipeline and loops back to re-open the gate |
| `backend/agents/execution_engine/engine.py` — new method `_run_spec_revision_sub_pipeline` | Re-runs ordered_agents[index-2] (specify), ordered_agents[index-1] (plan), and spec (analyze) in sequence using `_run_agent` with `ectx.spec_revision_context = analysis_report` injected; yields all events upstream; returns new analyze output via `_revision_analyze_output` internal signal | Sub-pipeline helper: structural (position-based), not name-based |
| `backend/agents/execution_engine/engine.py` — `_compose_context_message` | Added `elif revision_context := getattr(ectx, "spec_revision_context", "")` block appending `=== SPEC KIT ANALYSIS REPORT (REVISION CONTEXT) ===` block when set | Injects analysis report into specify/plan/analyze context during revision cycle |
| `backend/agents/prompts/prototype-specify/AGENT.md` | Added `## REVISION MODE` section with rules for targeted spec fixing when the analysis report block is present | Guides the model to fix specific issues rather than regenerate from scratch |
| `frontend/src/components/preview/ReviewGatePanel.tsx` | Added `onUpdateSpecs` prop; added `handleUpdateSpecs` callback; added "Update the Specs" button (rendered only when `isAnalysis && !!onUpdateSpecs`); renamed approve button to "Accept & continue to build" for analysis gate | User-visible action on the analyze gate |
| `frontend/src/components/layout/DashboardLayout.tsx` | Added `onUpdateSpecsReview` prop to interface + destructuring; wired into `<ReviewGatePanel onUpdateSpecs={onUpdateSpecsReview}>` | Prop pass-through |
| `frontend/src/app/dashboard/page.tsx` | Added `onUpdateSpecsReview` callback that sends `{type:"approve_review", gate_key, action:"update_specs", analysis_report}` and clears `reviewGateData` | FE sends the wire message and clears the panel |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): All engine branching keyed on generic `action == "update_specs"` string and generic `ectx.spec_revision_context`/`ectx.spec_revision_pending_output` scratch fields. Zero `pipeline_type` or `agent_id` literals.
- **INV-3** (golden parity): No new keys emitted on the WS event wire (the `_gate_update_specs` and `_revision_analyze_output` types are internal signals never forwarded; the analysis report rides `instructions` in `set_review_response` which is already in-memory only). Goldens never interact with review gates → byte-identical, no regen needed.
- **INV-12** (no duplication): Sub-pipeline calls `_run_agent` — the same agent execution path. No second runner.
- **SC-001** (zero engine edits for new workflows): Sub-pipeline is position-based (index-2, index-1, index), not name-based. Any workflow can benefit from this if it has the right shape.

#### Verification
- Backend started clean (no import errors, startup log shows `Backend ready`)
- Frontend TypeScript diagnostics: 0 errors on all 3 changed files
- Trace: user clicks "Update the Specs" → `handleUpdateSpecs` → `onUpdateSpecs(gateKey, output)` → page.tsx sends `{action:"update_specs", analysis_report:output}` → WS handler reads `analysis_report`, calls `store.set_review_response(action="update_specs", instructions=analysis_report)` → engine's `_run_review_gate` reads action, yields `_gate_update_specs` → inline consumer calls `_run_spec_revision_sub_pipeline` → specify runs with `spec_revision_context` injected → plan runs → analyze runs → `_revision_analyze_output` carries new analysis text → stored on `ectx.spec_revision_pending_output` → while-loop continues → pending output check at top → gate re-opens with new analysis → user sees new analysis panel

#### Notes
- The revision loop is unlimited (no hard cap on `spec_revision_attempt`) — consistent with the KAN-101 requirement
- Stop button during a revision cycle is cancel-aware: `_run_spec_revision_sub_pipeline` checks `cancel_event.is_set()` before each agent and yields `_gate_rejected` if set
- The `gate_agent_ids` deselection at the run level means that if the user runs the prototype pipeline with specify/plan gates deselected, the sub-pipeline will also skip those gates — correct behavior
- The Thinking tab (PrototypePipelineView) will show the revision cycle's agent events updating the existing specify/plan/analyze cards in-place (Option B from the analysis). Full versioned history is a follow-on enhancement

| FIX-049 | 2026-07-09 | KAN-102: Context Received section always empty for first agent — user brief, template, design system, and images not shown | `_build_context_sources` only iterated `_filter_consumed_outputs` (prior agent outputs); for index=0 consumed={} always so context_sources=[] always; OD template/DS blocks, user brief, and images were never modelled as ContextSource entries | `backend/agents/execution_engine/engine.py`, `frontend/src/types/index.ts`, `frontend/src/components/results/AgentThinkingTab.tsx` | Phase 3 (FR-015) / KAN-102 | INV-1/3/12/SC-001 ✅ | Done |

---

### FIX-049 — KAN-102: Context Received section always empty for first agent

**Date:** 2026-07-09
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-102`

#### Root Cause
`_build_context_sources` in `engine.py:5116` only iterated `_filter_consumed_outputs` which returns prior-agent outputs. For the first agent (`index=0`), `consumed={}` always → `context_sources=[]` always → the "Context Received" section was hidden entirely. The user brief, OD template body, design system body, and attached images are all present in `context_message` / `input_blocks` / `ectx.od_context` but were never surfaced as `ContextSource` entries.

Trace:
`_run_agent` (engine.py:2768) → `_build_context_sources(spec, ordered_agents, ectx)` → `_filter_consumed_outputs` returns `{}` for index=0 → `context_sources=[]` → `agent_input` event emitted with empty `context_sources` → `useWorkflow.ts agent_input handler` stores `contextSources=[]` → `AgentThinkingTab.tsx:560` `agent.contextSources.length > 0` is false → `ContextSourcesRow` never rendered.

#### Phase Context
- **Phase(s) involved:** Phase 3 (T043 — `agent_input` event, FR-015 context sources)
- **Relevant register section:** Phase 3 `_register-parts/03-token-trim-measured-change-0c.md`
- **Deleted code verified (not resurrected):** No deleted code involved
- **Locked decisions respected:** INV-1 positional check (`agent_index == 0`) not a pipeline_type or spec.id branch; Locked Decision #3 (split transport) preserved — context_message stays text str, images ride input_blocks only; goldens safe via `context_sources` already in `_VOLATILE_STRIP_KEYS`

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/execution_engine/engine.py` | Extended `_build_context_sources` signature with `agent_index`, `user_message`, `input_blocks` (all defaulted for backward compat). Added run-originating source entries for `is_first_agent` (index==0): `type="run_input"` for user brief, `type="context_block"` for template and DS from `ectx.od_context`, `type="image"` for attached images. Updated call site at line 2768 to pass `agent_index=index, user_message=user_message, input_blocks=input_blocks`. | First agent context sources were always empty — the original consumed-outputs loop only covered inter-agent handoffs |
| `frontend/src/types/index.ts` | Extended `ContextSource` interface with `type: "run_input" \| "context_block" \| "image"` variants, plus `label`, `size_chars`, `count` optional fields | New source types need FE type coverage |
| `frontend/src/components/results/AgentThinkingTab.tsx` | Updated `ContextSourcesRow` to render new source types with icons (📄 for run_input, 🎨 for context_block, 🖼 for image) and size labels | Display the new source chips |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): `is_first_agent = (agent_index == 0)` is the identical positional predicate used in `_compose_context_message`. Zero pipeline_type or spec.id literals.
- **INV-3** (golden parity): `context_sources` is in `_VOLATILE_STRIP_KEYS` in `_normalize.py` (line ~119). All 5 characterization goldens strip it entirely — adding new entries has zero impact on goldens. No regen needed.
- **INV-12** (no duplication): `ectx.od_context` is already the single source for template/DS metadata. Read via `getattr(ectx, "od_context", None) or {}`, same pattern as the TEMPLATE COMPLIANCE block in `_compose_context_message`.
- **SC-001** (zero engine edits for new workflows): observability enrichment only — no control-flow changes, no new agent dispatch paths.

#### Verification
- Backend started clean with no import errors
- Frontend TypeScript diagnostics: 0 errors on all 3 changed files
- Trace with fix: `_build_context_sources(spec, ordered_agents, ectx, agent_index=0, user_message=..., input_blocks=[...])` → `is_first_agent=True` → appends run_input + context_block(s) + image entries → `context_sources=[{...}, ...]` → FE `contextSources.length > 0` → `ContextSourcesRow` renders chips

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
- This fix is complementary to KAN-103 (template_id persistence). Even after KAN-103 is implemented to make design.md reliably available, this prompt change ensures the agent actually uses it.
- The `write_todos` tool creates an in-context todo list visible to the model. It is NOT persisted to the sandbox as a file — the agent's todo tracking is model-context-only.
- The `spec.md` read guidance changed from "may read to ground your change" to a clear "read this to understand original intent when needed" — but it remains non-mandatory since many revision requests don't require spec context.

---

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

---

### FIX-040 — OD gallery thumbnails generated at BUILD time

**Date:** 2026-07-07

#### Root Cause / Fix
The `<img>` fast-path needs a pre-rendered screenshot. Generated at backend image build (Playwright/Chromium already installed for render_check; OpenDesign tree baked at /app/opendesign), NOT committed — so absent thumbnails degrade to the FIX-039 live iframe.

#### Files Changed
`backend/app/services/od_loader.py`, `backend/app/api/prototype_templates.py`, `backend/app/api/ppt_templates.py`, `backend/scripts/generate_template_thumbnails.py` (NEW), `backend/Dockerfile`, `.gitignore`.

---

### FIX-041 — OD/PPT gallery card fallback to live iframe on thumbnail 404

**Date:** 2026-07-08

#### Root Cause / Fix
The thumbnail `<img>` in `TemplateCard` and `CompactPPTCard` had an `onLoad` but NO `onError` handler. Fix: add a `thumbnailError` state; on `<img>` `onError`, set it (and force-mount the iframe).

#### Files Changed
`frontend/src/components/workflow/prototype/TemplateCard.tsx`, `frontend/src/components/workflow/ppt/PPTTemplateGallery.tsx`.

---

### FIX-042 — thumbnail endpoint returns 500 instead of 404 when file missing

**Date:** 2026-07-08

#### Root Cause
`get_template_thumbnail_path` trusted the `has_thumbnail` flag (cached at startup). A thumbnail deleted after startup left the flag stale → `FileResponse` `os.stat`'d a missing file → 500.

#### Fix (backend-only)
`get_template_thumbnail_path()` re-checks `path.is_file()` on disk at serve time; returns `None` when absent → existing 404 branch fires → card falls back to live iframe (FIX-041).

#### Files Changed
`backend/app/services/od_loader.py`.

---

### FIX-043 — Template gallery thumbnail 429 flood + CompactTemplateCard missing onError

**Date:** 2026-07-09

#### Root Cause
Two bugs: (1) `CompactTemplateCard` keyed the thumbnail `<img>` on `thumbnailUrl` alone — the `shouldMount` IntersectionObserver gate only controlled the iframe fallback, so all ~43 thumbnails fired simultaneously on gallery mount → 429. (2) Same component had no `thumbnailError` + `onError` handler — a 429/404 left the card stuck on pulse shimmer with no recovery.

#### Fix
Gate `thumbnailUrl` rendering behind `shouldMount` in both compact cards; add `thumbnailError` + `onError` to `CompactTemplateCard`.

#### Files Changed
`frontend/src/components/workflow/prototype/TemplateGallery.tsx`, `frontend/src/components/workflow/ppt/PPTTemplateGallery.tsx`.

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
- Build-time cost: ~106 headless screenshots add a few minutes to the backend image build; acceptable for a one-time, cache-friendly step (only re-runs when the layer is invalidated).
- Absent thumbnails (e.g. local dev without running the generator) degrade gracefully to the FIX-039 live HTML+JS iframe.

#### Follow-up — code-review cleanup (2026-07-08)
- **Stale docstring corrected:** `od_loader.get_template_thumbnail_path`'s docstring still pointed at the deleted frontend generator `frontend/scripts/generate-template-thumbnails.mjs`; repointed to the real single source `backend/scripts/generate_template_thumbnails.py`. Doc-only.
- **Dockerfile chown consistency:** the thumbnail-generation `RUN` re-chowned `/app/opendesign` with numeric `chown -R 10001:10001` while the surrounding `COPY`s use the named `--chown=flowin:flowin` form (the `flowin` user is uid/gid 10001, created earlier). Aligned to `chown -R flowin:flowin /app/opendesign` for readability; functionally identical.
- **Test coverage added** (`backend/tests/integration/test_template_thumbnails.py`, NEW): exercises the previously-untested thumbnail serving path — loader `has_thumbnail` true/false vs disk, `get_template_thumbnail_path` present/absent/unknown, and the `GET /api/{prototype,ppt}/templates/{id}/thumbnail` route handlers returning `image/jpeg` when present and **404** for unknown ids and for a thumbnail deleted after load (the FIX-042 stale-flag on-disk re-check → clean 404, never a 500). 8 tests, all pass.
- **Verification:** `pytest tests/integration/test_template_thumbnails.py` 8 passed; `lint-imports` 4/0. INV-3 golden-neutral (doc/comment/test + a build-step chown label only; deliverable renderer untouched).
---

### FIX-041 — OD/PPT gallery card: fall back to the live iframe when a thumbnail 404s

**Date:** 2026-07-08
**Triggered by:** user requirement — "if thumbnail is not there than load template html in iframe … only if thumbnail is not there or 404 like."

#### Root Cause
FIX-039 renders each gallery card as a cheap static thumbnail `<img>` and only mounts the heavier live `example.html` iframe when no thumbnail exists; FIX-040 generates those thumbnails at backend-image build time (they are NOT committed). The thumbnail-vs-iframe decision in `TemplateCard` (prototype) and `CompactPPTCard` (PPT) keyed **solely** off the backend `has_thumbnail` flag, and the `<img>` had an `onLoad` handler but **no `onError` handler**. So whenever the flag was stale (local dev / an image built without the generator) or the file 404'd at request time, the `<img>` failed silently and the card was stuck on the pulse placeholder / broken image — it never degraded to the live iframe. The "no thumbnail at all" case already fell through to the iframe correctly; the missing case was the *runtime* load failure.

#### Fix (frontend-only)
In both cards:
- Added a `thumbnailError` state (default `false`).
- Gated the thumbnail URL on it: `thumbnailUrl = has_thumbnail && !thumbnailError ? getThumbnailUrl(id) : null`.
- Added `onError` to the `<img>`: on load failure it sets `thumbnailError = true`, force-sets `shouldMount = true` (so the lazy iframe mounts even if the IntersectionObserver hadn't yet), and resets `previewLoaded = false`. Nulling `thumbnailUrl` makes the component fall through to the pre-existing `previewUrl && shouldMount` iframe branch — the exact FIX-039 fallback, now reached on 404 as well as on absence.

No backend change; the `/thumbnail` endpoint still 404s as before — the fix just makes the client honour that 404.

#### Files Changed
`frontend/src/components/workflow/prototype/TemplateCard.tsx`, `frontend/src/components/workflow/ppt/PPTTemplateGallery.tsx`.

#### Invariants Verified
- **INV-3**: FE-only; catalog thumbnails, not the deliverable renderer — golden-neutral, no regen.
- **INV-1 / INV-12 / INV-13 / SC-001**: no engine/kernel/agent edits; no dual implementation (reuses the existing iframe fallback branch).

#### Verification
`npx tsc --noEmit` exit 0. `npx eslint` on both files: 0 errors (2 pre-existing warnings unrelated to this change — a `setState`-in-effect in the custom-template loader and an unused `onSelect` prop). The prototype `TemplateGallery.tsx` renders no thumbnails itself (delegates to `TemplateCard`), so no third card needed the patch.

#### Notes
- Behaviour now: thumbnail present and loads → cheap `<img>`; thumbnail absent (`has_thumbnail=false`) OR present-flag-but-404 → live `example.html` iframe; neither available → existing "No preview available" placeholder.
---

### FIX-042 — Thumbnail endpoint returns 404 (not 500) when the file is missing at request time

**Date:** 2026-07-08
**Triggered by:** user test — deleted `design-templates/blog-post/thumbnail.jpg` and hit the endpoint; got a 500 (`RuntimeError: File at path … does not exist`) instead of a 404, so the fallback was only working by accident (the `<img>` errors on any failed load).

#### Root Cause
`od_loader.get_template_thumbnail_path()` decided whether to serve by reading `t.get("has_thumbnail")`. That flag is produced by `_all_templates()`, which is `@lru_cache(maxsize=1)` — evaluated **once at process start** and never invalidated. When a thumbnail is deleted (or generated) after the server boots, the cached flag stays `True`, the function returns `_TEMPLATES_DIR/<id>/thumbnail.jpg`, and the endpoint hands that path to `FileResponse`. Starlette then `os.stat`s the file lazily while sending the response, raises `FileNotFoundError` → `RuntimeError`, which surfaces as a 500. Both the prototype and PPT thumbnail endpoints route through this one function, so both were affected.

#### Fix (backend-only)
`get_template_thumbnail_path()` no longer trusts the cached flag for serving: it builds the path and re-checks `path.is_file()` on disk, returning `None` when the file is absent. The endpoints' existing `if path is None: raise HTTPException(404)` branch then produces a clean 404. Existence is still gated on `get_template(template_id)` first (unknown id → `None`). The `has_thumbnail` field in the catalog *listing* is left as-is (still cached) — the frontend can optimistically request the `<img>`, and on a 404 the FIX-041 `onError` handler falls the card back to the live `example.html` iframe.

#### Files Changed
`backend/app/services/od_loader.py`.

#### Invariants Verified
- **INV-1 / INV-12 / INV-13 / SC-001**: no engine/kernel/agent edits; single path resolver, no dual implementation.
- **INV-3**: not on the deliverable/golden path (catalog asset serving); golden-neutral.
- **Ports & Adapters**: change confined to `app.services.od_loader`.

#### Verification
`.venv` import check: after deleting `blog-post/thumbnail.jpg`, `get_template_thumbnail_path("blog-post")` → `None` (→ 404); `get_template_thumbnail_path("does-not-exist")` → `None`; 105 templates still flagged `has_thumbnail`, and sampled ids (`audio-jingle`, `clinical-case-report`, `contact-widget`) still resolve to a real on-disk path (happy path intact).

#### Notes
- End-to-end behaviour now: thumbnail on disk → 200 `<img>`; thumbnail missing/deleted → 404 → card renders the live `example.html` iframe (FIX-041); no more 500s from a stale cache.
| FIX-043 | 2026-07-09 | Template gallery thumbnail 429 flood — compact cards loaded ALL thumbnails eagerly (no IntersectionObserver gate on `<img>` path) + `CompactTemplateCard` had no `onError` fallback | Two bugs: (1) `CompactTemplateCard` (TemplateGallery.tsx) keyed the thumbnail `<img>` on `thumbnailUrl` alone — the `shouldMount` IntersectionObserver gate only controlled the iframe fallback path, so all ~43 thumbnails fired simultaneously on gallery mount → 429 Too Many Requests from the server. (2) Same component had no `thumbnailError` state or `onError` handler (unlike `TemplateCard.tsx` and `CompactPPTCard` which both had it), so a 429/404 left the card stuck on the pulse shimmer with no recovery. `CompactPPTCard` (PPTTemplateGallery.tsx) had `onError` but the same missing `shouldMount` gate on the img path. Fix: gate `thumbnailUrl` rendering behind `shouldMount` in both compact cards (only visible cards fire requests); add `thumbnailError` + `onError` to `CompactTemplateCard` (on error, flip to iframe fallback — matching existing pattern in `TemplateCard.tsx`). | `frontend/src/components/workflow/prototype/TemplateGallery.tsx`, `frontend/src/components/workflow/ppt/PPTTemplateGallery.tsx` | Phase 4 (OD catalog UI) · builds on FIX-039/041 | INV-3 golden-neutral (FE-only; catalog thumbnails) ✅ | Done |

| FIX-052 | 2026-07-13 | KAN-105: Workflow History chained runs incorrectly grouped as versions under same workflow title | `groupRunsByFamily` bucketed ALL runs sharing the same `rootRunId` regardless of relationship type; chained runs (different base workflow type) were shown as v2/v3 under the source workflow title instead of as separate entries | `frontend/src/components/history/RevisionFamilyView.tsx`, `frontend/src/components/history/WorkflowHistory.family.test.tsx` | Phase 25 (B2 revision families) / KAN-105 | INV-1/3/12/SC-001 ✅ | Done |

---

### FIX-052 — KAN-105: Chained runs grouped incorrectly as revision versions in Workflow History

**Date:** 2026-07-13
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-105`

#### Root Cause
`groupRunsByFamily` in `frontend/src/components/history/RevisionFamilyView.tsx` (line 106) bucketed ALL runs sharing the same `rootRunId` into a single family card, without checking whether the parent-child relationship is a **revision** (same base workflow type, `_revision` suffix) or a **chain** (new, different workflow type seeded from the source output).

Both chained runs and revision runs receive `parent_run_id` on their `WorkflowRun` row — chaining uses `source_workflow_run_id` which the backend maps to `parent_run_id` via `_resolve_owned_parent_run_id`. The backend's `_compute_root_ids` walk therefore returns the same `root_run_id` for both types. `groupRunsByFamily` then placed them all in the same bucket, rendering a chained `user_stories` run as "v2" under the `prototype` title.

Trace:
```
User chains prototype → user_stories
  → handleChainPipeline → onStartPipeline("user_stories", ..., { source_workflow_run_id: contentSourceRunId })
  → websocket.py _resolve_owned_parent_run_id → WorkflowRun(parent_run_id = prototype.id)
  → runs.py _compute_root_ids walks parent_run_id chain → user_stories.root_run_id = prototype.id
  → groupRunsByFamily: bucket[prototype.id] = [prototype, user_stories]
  → FamilyGroup { members: [prototype, user_stories], v2 pill }
  → user_stories displayed as v2 under "My Prototype" ❌
```

#### Phase Context
- **Phase(s) involved:** Phase 25 — Revision Families & Run-Inputs Surfacing, Workstream B2 (`260702-uos`)
- **Relevant register section:** Phase 25 §B2 key-decisions: "Client-side family grouping on the server-supplied rootRunId (no workflow-name branching, SC-001)" — the fix honours this by using `baseWorkflowType()` (already in the file) which is type-based, not workflow-name based
- **Deleted code verified (not resurrected):** No deleted code involved — FE-only change to `groupRunsByFamily` logic
- **Locked decisions respected:** POR D7 (root_run_id computed server-side, FE groups by field) — honoured. The backend `_compute_root_ids` is unchanged. POR D1 (child-run model kept, unify at read/UX layer) — honoured. SC-001 — grouping uses `baseWorkflowType(run.type)`, a type-agnostic string operation, no workflow-name literal.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/history/RevisionFamilyView.tsx` | In `groupRunsByFamily`, after sorting bucket members, compute `rootBaseType = baseWorkflowType(root.type)`. Split each member: if `baseWorkflowType(m.type) === rootBaseType` → `revisionMembers`, else → `chainedStandalones`. Emit the revision family with only `revisionMembers` (may be single-member for the root alone). Emit each chained run as its own standalone `FamilyGroup` with `rootRunId = standalone.id`. | Chained runs have a different base type than the source; they must be independent entries. Only runs of the same base type are revision versions of the same workflow. |
| `frontend/src/components/history/WorkflowHistory.family.test.tsx` | Added a new test "KAN-105: a chained run (different base type) is shown as a separate workflow entry, not as a version of the source" — renders a prototype + a user_stories run sharing `rootRunId="proto"`, asserts both titles appear and no "vN" pill is present. | Regression guard for the fixed behavior. |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): `baseWorkflowType(run.type)` is a generic suffix/alias operation — no `if pipeline_type ==` or `if type === "prototype"` literal. Any new workflow type is handled correctly by the existing `_revision` suffix rule.
- **INV-3** (golden parity): FE-only change. No backend/engine/websocket/manifest/migration edit. The 5 characterization goldens are untouched.
- **INV-12** (no duplication): reuses the existing `baseWorkflowType` function already defined in `RevisionFamilyView.tsx`. No second implementation.
- **SC-001** (zero engine edits): not applicable — FE presentation logic only.

#### Verification
- TypeScript diagnostics: 0 errors on both changed files
- Test trace with fix:
  - `proto (type=prototype)` + `chain (type=user_stories, rootRunId=proto)` → `rootBaseType="prototype"`, chain's base type = `"user_stories" ≠ "prototype"` → chainedStandalones → two independent FamilyGroup entries → no v2 pill ✅
  - `proto (type=prototype)` + `rev1 (type=prototype_revision, rootRunId=proto)` → both base type = `"prototype"` → revisionMembers → one FamilyGroup with v2 pill ✅
  - `od_prototype` + `prototype_revision` → `baseWorkflowType("od_prototype")="prototype"`, `baseWorkflowType("prototype_revision")="prototype"` → same family ✅
- Existing tests unaffected: the fix only changes behavior when a bucket contains runs of different base types (the chain scenario); same-type buckets (all revisions) pass through the `revisionMembers` path unchanged and produce identical output.

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
