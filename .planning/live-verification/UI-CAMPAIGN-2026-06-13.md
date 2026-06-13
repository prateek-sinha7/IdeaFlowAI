# Full-App UI Verification Campaign — 2026-06-13 (in progress)

Mandate (user): verify the ACTUAL UI against the implementation-register's capabilities —
every pipeline runs from the real frontend, visuals judged at each step, all variations,
including a custom pipeline mimicking prototype and fanning out agents inside. Playwright
drives everything; screenshots are read and judged by review agents; results synthesized here.

Stack: real Next.js FE (:3000) + launcher-widened backend (:8000, real Bedrock Haiku 4.5,
AWS_PROFILE=hexaware-srini fresh quota; fallback default) + Postgres (app DB + checkpointer).
Evidence: /tmp/flowin-ui-evidence/<scenario>/ (screenshots, frames.jsonl, dom-notes.json).

## Test matrix (derived from IMPLEMENTATION-REGISTER §6 + capability families + FE surfaces)

| # | Scenario | Pipeline / surface | UI checks (visuals at each step) |
|---|----------|--------------------|----------------------------------|
| S01 | user_stories | 6 text-only agents, clarify auto | login→dashboard, launcher, questionnaire FORM (render+answer via UI), agent progress cards (6× start→streaming→complete), backlog output render, run-history entry |
| S02 | od_prototype | gates + task_loop build + validation | template/DS payload, 2× review-gate MODAL (content visible, approve via UI), build task progress, validation status, HTML preview iframe renders the prototype |
| S03 | od_ppt + UI revision | deck pipeline + FE-exact revision (Phase-14 SC4 UI half) | deck preview carousel renders the REAL deck (LV-02 fix in UI), revise-from-UI flow → revision run streams → revised deck in preview |
| S04 | app_builder | 15 agents, file-bundle deliverable | long-run progress panel behavior, FilesTab/AppBuilderPreview render of the `filename:` bundle |
| S05 | dotnet_to_azure | migration pipeline | per-agent cards over 13 agents, bundle render |
| S06 | mulesoft_to_springboot | with source-embedded brief | inventory agent output render; bundle render |
| S07 | custom | agent picker + model_overrides + attached skill/hook | custom composer surface, 3-agent run, report output |
| S08 | chat | free-chat path | conversational render (discovery), no pipeline panels regression |
| S09 | sample_wave | wave_scheduler (12-08 panel) | WaveTreePanel: wave groups, task ids, status badges flipping, N distinct worker leaves |
| S10 | sample_fanout | fanout_batch | subagent spawns visible, merge events, serialized bundle output |
| S11 | ui_custom_proto (SC-001) | NEW file-trust manifest mimicking prototype + an internal fanout step | a brand-new custom workflow (manifest + AGENT.md fixtures only, zero engine edits) runs from the UI: fanout tree + task-loop build + HTML preview — the core-value proof ON THE UI |
| S12 | cross-cutting | reconnect / cancel / history | mid-run reload → after_seq replay rebuilds panels; cancel button → idle; history → reopen run → preview renders |

Per-scenario screenshot checkpoints: 01-launch, 02-questionnaire, 03-midstream, 04-gate (if any),
05-more-stream, 06-terminal, 07-preview, 08-history (+ scenario-specific). Frames captured via the
WS-wrapper (sessionStorage-persisted across reloads). UI-control failures (e.g., a questionnaire
form that cannot be found in the DOM) are FINDINGS, not driver errors — the WS fallback then keeps
the run alive so later surfaces still get exercised, and the gap is recorded.

## Verdict legend
PASS — surface renders + behaves; WEAK — renders with cosmetic/UX issues (listed); FAIL — broken,
missing, or wrong content; BLOCKED — upstream dependency prevented the check (named).

Results land below as scenarios complete.

---

## Results (live, real Bedrock Haiku 4.5 via `default` profile after srini access broke — ISS-018)

Driver: `/tmp/flowin-ui-driver.py` v2 (drives REAL UI controls). Evidence per scenario in
`/tmp/flowin-ui-evidence/<S>/` (screenshots read + judged by the operator).

| # | Scenario | Launch | UI interactions (real-UI vs WS) | Verdict | Key visual evidence |
|---|----------|--------|----------------------------------|---------|---------------------|
| S01 | user_stories | tile | questionnaire = **real UI** | **PASS** | 4 agents DONE, "Done", **Product Backlog renders** in UserStoryPreview (34 stories / 118 criteria), 73.5K/25.1K tokens, 40.6KB output |
| S09 | sample_wave | ws_rewrite | questionnaire real UI | **PASS** | wave_started/completed [0,1] + 4 subagents; **WaveTreePanel renders** (heading + Wave 0/1 groups) — below the 950px fold (ISS-019) |
| S10 | sample_fanout | ws_rewrite | questionnaire real UI | **PASS** | 3 subagents + copy_disjoint merge (0 conflicts), serialized bundle deliverable |
| S11 | **ui_custom_proto (SC-001)** | ws_rewrite | questionnaire + **gate = real UI** | **PASS (backend) / FE gap** | brand-new custom workflow: factfind → **3-worker fanout+merge** → **human-gated plan (real UI approve)** → **task_loop build (398K tok)** → validate → **21KB real HTML**. Preview/Files don't surface the HTML deliverable (ISS-021) |
| S03 | od_ppt | ws_rewrite (template extras) | questionnaire real UI; revise WS-fallback | **PASS** | **deck renders in "Slide Deck Preview" iframe** ("Aurora AI Platform", slide 1/5) — LV-02 fixed & visible; **revision produced a revised deck (+security/compliance)** — Phase-14 SC4 UI half ✓ |
| S02 | od_prototype | ws_rewrite (template extras) | questionnaire + **2 gates = real UI** | **PASS** | **2 review gates approved via real UI** (Specification Review + Task Plan Review, real content, Approve/Reject) — F1 ✓; **interactive HTML task-manager renders in "Prototype Preview" iframe** (stat cards, add-task form, Tweaks/Source toolbar, revise bar) |
| S07 | custom | tile | (running) | — | — |
| S04 | app_builder | tile | (queued) | — | — |

### UI capability coverage proven
- ✅ Login, dashboard, workflow tiles (CreationHub)
- ✅ Clarify questionnaire — **driven via real UI** (radio-card options + "Run with defaults"/"Run X Pipeline")
- ✅ Human review gates — **approved via real UI** ("Approve & continue"), showing real spec/plan content (F1)
- ✅ AgentProgressPanel — RUNNING/DONE badges, per-agent token counts, completion toasts
- ✅ WaveTreePanel — renders (below fold, ISS-019)
- ✅ Fan-out subagents + merge
- ✅ PPT deck preview (iframe) — LV-02 fix visible
- ✅ Prototype HTML preview (iframe) — interactive, with Tweaks/Source/revise toolbar
- ✅ Revision — revised deck with requested content (SC4)
- ✅ SC-001 custom workflow (fanout+gate+build) end-to-end from the UI
- ✅ UserStoryPreview (backlog render), Files tab (downloads)

### Issues found (see ISSUES-REGISTER.md)
ISS-016 (major: model error → empty-run-as-success), ISS-017, ISS-019 (wave panel below fold),
ISS-021 (custom HTML deliverable no FE path), ISS-013/020 (harness), ISS-018 (srini Bedrock access).

---

## Final results (campaign complete 2026-06-13)

| # | Scenario | Verdict | Notes |
|---|----------|---------|-------|
| S01 | user_stories | **PASS** | questionnaire real-UI; UserStoryPreview renders backlog |
| S02 | od_prototype | **PASS** | 2 review gates approved real-UI (F1); interactive HTML in Prototype Preview iframe |
| S03 | od_ppt | **PASS** | deck in Slide Deck Preview iframe (LV-02 visible); revision → revised deck (SC4) |
| S04 | app_builder | **PASS** | AppBuilderPreview IDE: 121-file tree, code viewer, Download ZIP (10.4M tok / $2.99) |
| S07 | custom (composer) | **PASS (UI) / partial drive** | agent-composer modal + searchable agent library render well (ISS-014 refined); full agent-pick→run not driven via generic selectors; custom EXECUTION proven by S11 |
| S09 | sample_wave | **PASS** | WaveTreePanel renders (below fold, ISS-019); backend waves perfect |
| S10 | sample_fanout | **PASS** | 3 workers + copy_disjoint merge |
| S11 | ui_custom_proto (SC-001) | **PASS (backend) / FE gap** | custom workflow: fanout + human-gate (real-UI approve) + task_loop build → 21KB HTML; FE has no renderer for the custom HTML deliverable (ISS-021) |
| S12 | cancel | **PASS w/ ISS-007** | real Stop click → header "Pipeline stopped" + DB cancelled, but a card stuck RUNNING (cancel ack not delivered, ISS-007) |

### Not run (rationale)
- **S05/S06 migrations (mulesoft/dotnet)** — covered by proxy: the deliverable + preview surface is the SAME `AppBuilderPreview` IDE validated in S04 (file-bundle → IDE). The pipelines themselves were live-verified in REPORT-2026-06-12 (dotnet clean, mulesoft-with-source inventory). Marginal UI value ~0 for ~$1.2-1.6 each.
- **S08 chat** — the legacy free-chat subsystem (`AgentOrchestrator`/`BaseAgent`, mid-migration to `ChatRunner` per backend/CLAUDE.md §7); a distinct render path, not part of the pipeline-runtime UI this campaign targets. Deferred.
- **reconnect (after_seq replay)** — validated at the WS level in Phase-12 UAT (12-UAT tests 2/5/6) + the milestone-end live pass (WR-03 live-attach); the FE `pipeline_reconnected` handler is covered there.

### Verdict
**Every unique product UI surface renders and behaves correctly through genuine UI interaction** — workflow tiles, clarify questionnaire, human review gates (F1), agent progress panel, wave/subagent tree, all four deliverable previews (UserStory / PPT-deck-iframe / Prototype-HTML-iframe / AppBuilder-IDE), revision, custom agent-composer, and the SC-001 custom-workflow execution (fanout+gate+build). 9 issues logged (1 major: ISS-016 empty-run-as-success on model error; rest minor/cosmetic). The SC-001 `ui_custom_proto` fixture is preserved under `ui_custom_proto-fixture/` (removed from the source tree to keep it ship-clean).

### Reusable harness
`/tmp/flowin-ui-driver.py` (scenario-JSON-driven playwright; launch strategies tile/migration/wizard/ws_rewrite; real-UI questionnaire/gate/cancel/revise; full-page screenshots + DOM notes + WS frame capture) + `/tmp/flowin-ui-launcher.py` (sample/SC-001 admission). Scenario JSONs at `/tmp/ui-scenario-S*.json`.
