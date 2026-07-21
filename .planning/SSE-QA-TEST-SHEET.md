# SSE QA Test Sheet — feat/ui-2 (live Bedrock, post SSE-only cutover)

> Persisted QA record for the full live-SSE test campaign. Every pipeline × interaction × visual.
> **Status legend:** ⬜ pending · 🔄 in-progress · ✅ pass · ❌ fail (→ BUG-id in [SSE-QA-BUG-LOG](./SSE-QA-BUG-LOG.md)) · ⚠️ pass-with-concern · ⛔ blocked/input-gated · ⏭️ skipped
> **Evidence:** screenshots in the job scratch (`shots-qa/`), referenced per row. Every run also asserts **0 `/ws/chat`** connections.
> Live run ids (this campaign): user_stories `ab90f5f4`, od_prototype `4cd2f478`, od_ppt `6c6f38c7`, app_builder `bb6dc438`.

Last updated: 2026-07-16 (campaign start).

## A. Per-pipeline live over SSE

| ID | Pipeline | Test | Status | Evidence | Notes |
|----|----------|------|--------|----------|-------|
| A1-US | user_stories | Launch accepted + run mints | ✅ | api | POST /api/runs → run id |
| A2-US | user_stories | Clarifying questions asked (count/content correct) | ⬜ | | needs held-at-clarify run |
| A3-US | user_stories | Clarify UI visually correct | ⬜ | | |
| A4-US | user_stories | Clarify answered (real answers) → resumes | ⬜ | | |
| A5-US | user_stories | Streaming trace: steps + inner agents + live chunks + scroll | 🔄 | | run ab90f5f4 |
| A7-US | user_stories | Deliverable renders (backlog) | ✅ | 11/12 (prior) | grocery run rendered 8 epics/28 stories |
| A8-US | user_stories | 0 /ws/chat on run | ⬜ | | |
| A1-PROTO | od_prototype | Launch accepted (template+design_system) + mints | ✅ | api | needs template_id + design_system_id |
| A2-PROTO | od_prototype | Clarifying questions asked | ⬜ | | |
| A5-PROTO | od_prototype | Streaming trace visuals | 🔄 | | run 4cd2f478 |
| A6-PROTO | od_prototype | Review gate (Human_Gate) pause + resume | ⬜ | | prototype-specify / prototype-plan gates |
| A7-PROTO | od_prototype | Deliverable renders (prototype.html) | ⬜ | | |
| A8-PROTO | od_prototype | 0 /ws/chat | ⬜ | | |
| A1-PPT | od_ppt | Launch accepted (template) + mints | ✅ | api | template_id html-ppt |
| A5-PPT | od_ppt | Streaming trace visuals | 🔄 | | run 6c6f38c7 |
| A7-PPT | od_ppt | Deliverable renders (deck) | ⬜ | | |
| A8-PPT | od_ppt | 0 /ws/chat | ⬜ | | |
| A1-APP | app_builder | Launch accepted + mints | ✅ | api | brief only |
| A5-APP | app_builder | Streaming trace visuals (multi-agent) | 🔄 | | run bb6dc438 |
| A7-APP | app_builder | Deliverable renders (files) | ⬜ | | |
| A8-APP | app_builder | 0 /ws/chat | ⬜ | | |
| A1-MIG | mulesoft/dotnet/reverse_engineer | Migration pipelines | ⛔ | | input-gated (need real source repo) — deferred |

## B. History / revise / interactions

| ID | Test | Status | Evidence | Notes |
|----|------|--------|----------|-------|
| B1 | Workflow History → tap a run → run screen opens | ⬜ | | |
| B2 | Left chat panel present on opened run (revise affordance) | ⬜ | | user asks: "left chat panel should be there to help revise" |
| B3 | Concierge: ask a question → reply renders as its OWN turn | ⬜ | | DEF-44-12-2 fix — verify live |
| B4 | Revision/refinement: request change via chat → refinement workflow runs over SSE | ⬜ | | run_revision retired → refinement |
| B5 | Open-from-history LIVE run → streaming trace renders | ⬜ | | DEF-44-12-4 fix — verify live |
| B6 | Cancel → pipeline_cancelled over SSE | ⬜ | | |
| B7 | Reconnect/resume: reload mid-run → trace continues (Last-Event-ID) | ⬜ | | |

## C. Visual / design capture (each surface — "every visual needs to be tested")

| ID | Surface | Status | Evidence | Notes |
|----|---------|--------|----------|-------|
| C1 | Home composer + deliverable cards | ✅ | 05 (prior) | |
| C2 | Clarify questionnaire UI (asked properly, looks OK) | ⬜ | | |
| C3 | Steps tab — agent cards, icons, order, live badge | ⬜ | | |
| C4 | Live streaming — chunk animation, reasoning text updates | ⬜ | | |
| C5 | Scrolling — steps list scroll + inner-agent scroll + transcript scroll | ⬜ | | user: "their scrolling" |
| C6 | Deliverable Preview render (per pipeline type) | 🔄 | | US done; proto/ppt/app pending |
| C7 | Chat / revise panel UI | ⬜ | | |
| C8 | Version dropdown + tabs (Preview/Steps/Files/Audit) | ⬜ | | |

## D. Transport invariants

| ID | Test | Status | Evidence | Notes |
|----|------|--------|----------|-------|
| D1 | 0 `/ws/chat` connections across all surfaces | ✅ | prior smoke | re-assert per run this campaign |
| D2 | SSE `/events/stream` is the sole live down-channel | ✅ | curl (prior) | |
| D3 | `/ws/handoff` survivor still works (the one WS that stays) | ⬜ | | if exercised |

## Session 1 results (2026-07-16) — live streaming pass (4 pipelines)

**Transport: 0 `/ws/chat` across all 4 opened runs; SSE `/events/stream` attached per run.** ✅ (D1/D2 re-confirmed live).

- **A5-US** ✅ user_stories 6-agent trace streamed correctly (Domain Discovery → … → Delivery Compilation, live "streaming" chip, progress bar, per-agent timings/tokens, steer composer). Screenshot `shots-qa/user_stories-steps.png`.
- **A5-PROTO** ✅ + **A6-PROTO** 🔄 od_prototype streamed; **review gate (Human_Gate) rendered beautifully** — "Paused · review gate", Spec Writer spec (dashboard + Apple DS), **Approve the spec / Request changes** buttons. Resume test pending. `shots-qa/od_prototype-steps.png`.
- **A5-PPT** ✅ + **A7-PPT** 🔄 od_ppt **completed** (3 agents, `presentation.pptx` deliverable; 49% prompt-cache hit). Preview render check pending. `shots-qa/od_ppt-steps.png`.
- **A5-APP** ✅ app_builder 15-agent trace streaming (Architecture → User Stories → System Design … → SDLC Governance). `shots-qa/app_builder-steps.png`.
- **C3** ✅ steps/agent cards render; **C4** ✅ live streaming (chunk/badge/progress); **C5** 🔄 scrolling (steps list scrolls; inner-agent drilldown pending).

**🟠 BUG-001 (ROOT-CAUSED, logged):** the run-screen **left-lane title** shows the most-recently-created run's title (`recentRuns[0].title`, DashboardLayout.tsx:1323), not the viewed run's — all 3 non-latest runs showed the od_prototype "fitness dashboard" title. Pre-existing (Phase 39, commit 5003aca47); DEF-44-12-4 *exposed* it. Fix proposed (bind to `contentSourceRunId`). The pipeline-type LABEL was a shared-page harness artifact (fresh context shows correct label). See BUG-001 in the bug log.

### Interaction results (Session 1)

| ID | Test | Status | Evidence | Notes |
|----|------|--------|----------|-------|
| A6-PROTO | Review gate (Human_Gate) pause + resume | ✅ | `gate-before/after`, backend `review_gate_approved:1` | Approve the spec → advanced gate1→agent→gate2. POST /gate, 0 /ws/chat. |
| B2 | Home recents → left chat lane + composer present | ✅ | `recents-open-run.png` | `execution-chat-lane` + steer/revise composer present |
| B3 | Concierge reply renders as its OWN turn | ✅ | `concierge-reply2.png` | grounded reply bubble, distinct from question (id-collision fix works); POST /messages; 0 /ws/chat. **DEF-44-12-2 live-proven.** |
| B5 | Open-from-history LIVE run → streaming trace renders | ✅ | `*-steps.png` | all 4 opened runs `emptyTrace:false` (was empty pre-fix). **DEF-44-12-4 live-proven.** |
| B1 | Run History → tap run → left chat panel present | ❌ | `history-row-tap.png` | **BUG-002** — history-tap opens a degraded `RunDetailPage`: NO chat lane/composer, wrong "QUEUED" status, "No agent data" + "No preview available", different tabs (Thinking vs Steps). Investigation agent running. |
| B4 | Revision/refinement via chat → refinement runs over SSE | ❌ | `revise-chip.png`, `revise-clean-after.png` | Confirm-first chip ("RUN A REFINEMENT WITH THIS CHANGE? [Run refinement]") appears CORRECTLY, but clicking **Run refinement fires ZERO requests + launches no revision**. **BUG-003** (investigation running). |
| B6 | Cancel → pipeline_cancelled over SSE | ✅ | `cancel-after.png` | Stop → POST /cancel → status `cancelled`. 0 /ws/chat. |
| B7 | Reconnect/resume (reload mid-run) | ✅ | `reconnect-before/after.png` | reload mid-stream → trace persists + **SSE stream re-attaches** (Last-Event-ID). 0 /ws/chat. |
| A2/C2 | Clarifying questions asked + visual | ✅ | `clarify-ui.png` | 5 well-formed domain-relevant questions + multi-select chips ("Select all that apply"), clear AWAITING YOU. Excellent. |
| A7-PPT | od_ppt deliverable Preview renders | ⚠️ | `ppt-preview.png` | "No preview available" NOT shown, but pptx renders BLANK inline on a recents-open (may be a binary-deliverable/content-load gap — see BUG-003 confound). |
| C5 | Inner-agent drilldown + scrolling | ✅ | `agent-drilldown.png` | Click agent → FULL INPUT PROMPT (20.7k chars) + AGENT OUTPUT (19.5k) + timing/tokens + "CONTEXT RECEIVED · N sources fed in" (produces/consumes viz). Scroll works. |
| C3/C4 | Steps + inner agents + live streaming (visual) | ✅ | `*-steps.png` | agent cards, icons, order, live "streaming" chip, progress bar, per-agent timing/tokens. |

**BUG-002 (ROOT-CAUSED, logged):** History-list tap → WorkflowHistory's internal `RunDetailPage` (`handleSelectRun→setSelectedRun`, DashboardLayout:1506 passes no `onSelectWorkflowRun`) — no chat lane, one-shot `getRunSummary` (stale "QUEUED"), no SSE attach ("No agent data"/"No preview"). Pre-existing; Home recents was rewired to the run screen, History never was. Fix: route History tap through `onOpenRun`→`setMainView("execution")` (same as Home recents). See bug log.

**BUG-003 🟠 (ROOT-CAUSED, logged):** revise-via-chat "Run refinement" no-ops on a reopened od_ppt run. A **pre-existing empty-content guard** `if (!pptxCode && !pptContent) return;` (DashboardLayout.tsx:493) short-circuits BEFORE the self-sufficient REST path (`postRevision(token, contentSourceRunId, …)`, :504, which reseeds the parent server-side and needs no local content); `confirmRefinement` then clears the chip unconditionally → nothing fires. Trigger: od_ppt's `fullRun.output` was **empty** (also why the Preview was blank — an LV-02 recurrence: the deck is a prompt-contract, not a hard guarantee); `pptxCode` is structurally undefined for od_ppt (no ppt-code-generator agent). The swallow defect dates to 2026-07-15 (the REST branch `a931c066a` was added below the stale 2026-05-11 guard without relaxing it). Fix: relax to `if (!contentSourceRunId && !pptxCode && !pptContent) return;` + bind revise-handler selection to the viewed run's type on reopen. NOT caused by BUG-001 (contentSourceRunId is correctly set) nor by DEF-44-12-4. See bug log.

### Session 3 — migration/custom pipelines, deliverables, survivor, + BUG-004

| ID | Test | Status | Notes |
|----|------|--------|-------|
| A1-MIG | mulesoft_to_springboot / dotnet_to_azure / custom launch + stream | ✅ | all 3 launched (13/13/8 agents) with sample source input; **streamed to clarify over SSE** (planner + questionnaire_ready delivered over the stream) → transport proven for them. `reverse_engineer` has **no registered agents** (not runnable as a pipeline). |
| A1-MIG-done | migration full completion + deliverable | ⛔ | blocked by **BUG-004** (DB pool exhaustion under the 10+ concurrent-run load — `skip_clarification` 500'd, then the backend saturated to HTTP 000). Not a pipeline defect. |
| A7-APP | app_builder deliverable | ⚠️ | run `completed` with `output:True` (verified via API earlier); UI screenshot blocked by recents-fallout + pool saturation. |
| D3 | `/ws/handoff` survivor present | ✅ | `@router.websocket("/ws/handoff/{token}")` (websocket_handoff.py:80) + `main.py:193`. Live exercise needs a real handoff token (deferred). |
| D1 (re-confirm) | 0 `/ws/chat` | ✅ | `GET /ws/chat → 404` (deleted); browser opened 0 across the entire campaign. |

**🟠 BUG-004 (ROOT-CAUSED — a genuine CONNECTION LEAK, activated by the SSE cutover):** NOT merely a small pool — the SSE endpoint `stream_run_events` (`run_stream.py:208,233-237`) injects its `Depends(get_db)` request session into `ScopedStore(session=db)` then queries INSIDE the streaming generator. FastAPI ≥0.106 tears down `yield`-deps BEFORE the body streams, so `get_db`'s `db.close()` fires first; the generator re-acquires a FRESH pool connection on the closed session and `ScopedStore._acquire` (owned=False) never closes it → **each live SSE stream leaks 1 connection** (reclaimed only by GC — proven empirically). With the default pool (5+10=15) + reconnects/tabs, ~10+ streams exhaust it → `submit_answers` 500s → backend HTTP 000. **Went HOT when SSE became the SOLE run-event transport on 2026-07-15 (44-07)** — one day before observed. Not load-abnormal — it will exhaust under normal multi-user production load. Checkpointer uses a separate pool (not involved). Fix: give `_iter_sse_frames` a session-less `ScopedStore(session=None)` (self-manages `SessionLocal`, holds nothing during idle drain) + explicit pool sizing as defense-in-depth. **This is the most significant finding — a leak in the core SSE path introduced by the cutover.** See bug log BUG-004.

**Still deferred (low-value / high-friction):** od_prototype build deliverable (gate-2 `gate_key` friction; the gate *resume* is already proven — A6-PROTO ✅), migration full completion (BUG-004), `/ws/handoff` live exercise (needs a share token).

**Run History view (C-visual)** ✅ — clean list (67 runs, type filters All/User Stories/Presentation/Prototype/App Builder/Custom, Sort Newest/Longest/Tokens, status badges, grouped Today/Older). `history-list.png`.
