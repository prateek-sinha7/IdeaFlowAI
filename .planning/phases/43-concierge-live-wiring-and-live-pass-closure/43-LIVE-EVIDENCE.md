# Phase 43 — Live-Pass Evidence (Part B / C)

Live checks run against real AWS Bedrock (Haiku, `eu-central-1`) via SSO profile `hex-ai-fe`, local stack (uvicorn :8000 on current Part-A code, schema `alembic=0025`; next dev :3000 with `NEXT_PUBLIC_SSE_TRANSPORT=1` — the supervised cutover). QA login `qa-enterprise@flowinqa.com`. Each check records the observable evidence (pass / issue). Recorded 2026-07-15.

---

## Environment (the supervised cutover — 43-06 A.0/A.2)
- **Transport flipped:** `RunConnectionProvider` mounted (`app/layout.tsx`, commit `61a5c78c`) + `NEXT_PUBLIC_SSE_TRANSPORT=1` → `useRunConnection().enabled=true` → `useRunChat.sendMessage` routes to `POST /api/runs/{id}/messages` (SSE up-channel). Legacy `/ws/chat` still present (deleted only at 43-09 exit gate).
- **Backend on Bedrock (not Anthropic-direct):** boot log `LLM provider: bedrock-iam (model=anthropic.claude-haiku-4-5-20251001-v1:0 region=eu-central-1)`; `/health` → `{"status":"healthy","llm_provider":"bedrock"}`; `ANTHROPIC_API_KEY` empty.
- **Migration applied:** `0023 → 0024 → 0025` (the WR-02 `deep_link_nonces` table) on `dev.db` (backed up to `dev.db.bak-pre43-cutover` first).

---

## B.3 — Concierge Q&A live (grounded, confirm-gated) — **PASS ✓** [43-06]

**Method:** as the QA user, POST a settled-run status ASK with `{concierge:true}` to a completed `od_prototype` run (`4286d016-…`, "Task Manager Core Requirements").

`POST /api/runs/4286d016-…/messages {"text":"What is the current status of this run and what did it produce?","concierge":true,"message_id":"client-livecheck-…"}`
→ `HTTP 200 {"ok":true,"seq":17908,"persisted":true,"channel":"concierge","reply":true,"proposals":[]}`

**Routed to the Concierge, NOT a revision** — `channel:"concierge"` (the 43-02 crux live: a settled-run ASK is answered, not launched as a `*_revision`).

**Grounded, non-hallucinated** — the persisted `chat_reply` (seq 17909) read the run's real events/artifacts (43-01 M2 read-tool serialization working live) and reported: correct status **COMPLETED**, real deliverable ("Task Manager MVP prototype, single-file HTML"), real timestamps (Started Jul 14 14:43:03 → Completed 15:56:17 UTC), real pipeline stages (Planning→Spec→Build-plan→Cross-artifact→Build→Validation), and the actual prototype feature list (task list, Create-Task modal, complete/undo, status filters, sort, dark-mode + localStorage, assignee autocomplete, CSV export, toasts, priority bar chart). None of this is generic — it is this run's data.

**Reached Bedrock via DeepAgentRunner (INV-13)** — uvicorn log:
- `build_model: ChatBedrockConverse model=eu.anthropic.claude-haiku-4-5-20251001-v1:0 region=eu-central-1 max_tokens=32768`
- `DeepAgentRunner init: model_id=eu.anthropic.claude-haiku-4-5-… tools=7 excluded=['task'] sandbox=False … thread_id=4286d016-…:concierge`
- `botocore.tokens: Loading cached SSO token for hex-ai-fe-sso`
No `create_deep_agent` / hand-rolled loop; the Concierge ran on the sanctioned `DeepAgentRunner` with its 7 read tools.

**Proposals:** `proposals:[]` (a status question is non-consequential — no confirm-hold expected). The consequential-proposal confirm-chip path (H1 durable-row disposal) is verified separately when a proposal-bearing turn is exercised.

---

## B.5 — Live launch on Bedrock — **PASS ✓**
`POST /api/runs {"pipeline_type":"prototype","message":"…pomodoro timer…"}` → `HTTP 200 {run_id:7cd26895-…}`. The run drove live on Bedrock: `workflow_validated → planner_start → SmartPlanner (ChatBedrockConverse, gate PROCEED→CLARIFY_REQUIRED) → questionnaire_ready → clarification_limit_reached → pipeline_start → prototype-specify (agent_input + 1296 agent_chunks + agent_complete) → review_gate_ready → [approved] → prototype-plan`. Two real agents ran end-to-end on Haiku. (ppt half not launched this session — prototype proves the unified launch path; ppt is the same `POST /api/runs` contract.)

## B.2 — Mid-run steering into the next agent's live prompt — **PASS ✓**
A bare-text turn on the running run routed to `channel:"steering"` (`route_chat_turn → CHANNEL_STEERING → apply_steering → ectx.steering_notes`). After approving the specify gate, the **prototype-plan** agent's `agent_input.context_message` (seq 1313) contained verbatim:
```
=== USER GUIDANCE ===
Here is a reference screenshot for the visual style.
=== END USER GUIDANCE ===
```
The A.3 live-ectx registry resolved the running run and drained the queued steering note into the NEXT agent's live prompt. (Note: a bare-text turn while the run is paused at a *clarify questionnaire* is correctly consumed as a clarify **answer** (`channel:"answers"`), not steering — the steering channel engages once past clarify; timing matters, mechanism verified.)

## B.1 — Per-turn image to a running run — **PARTIAL**
The per-turn image (`{mime_type:image/png,data:…}`) was accepted and routed to `channel:"steering"` (the shared `apply_turn_images` seam, 43-05). But no image/`image_count` signal appeared in the next agent's `agent_input` and no image-delivery log line was observed, so **delivery-to-model was not confirmed this session**. The **run-entry** image path is separately live-proven (quick-260710-ftq, `image_count=1` to the spec-writer). Per-turn image (DEF-30-03-1) delivery needs a deeper trace — logged as still-owed.

## B.4 — Bedrock prompt caching — **PARTIAL (cache WRITE live-proven; cache_read>0 not observed)**
Real, observable improvement over the "caching silently off on Bedrock" baseline: pipeline agent `agent_complete` usage carried **`cache_write_tokens=5094`** (prototype-specify) and **`8781`** (prototype-plan) — the `_BedrockCachePointsMiddleware` IS injecting `cache_control` and Bedrock IS creating cache entries. But **`cache_read_tokens=0`** on both (distinct system prefixes across agents → nothing re-read), and the Concierge's multi-turn usage is not surfaced in the run event stream, so `cache_read>0` (the actual token savings) was not observable this session. Standing ISS-031/032; the ISS-033 helper (43-04) places cache_control offline-proven + cache_write now live — but the multi-turn cache-READ + the ISS-033 token-count delta remain owed.

## B.6 — analytics + notifications — **B.6a PASS ✓ / B.6b pending**
- **B.6a:** `GET /api/analytics/summary` → `HTTP 200` with real KPIs (`total:47, completed:29, failed:3, success_rate:0.617`) + per-day token breakdowns. Live round-trip confirmed.
- **B.6b:** notifications are client-derived (`useNotifications` fed by pipeline frames over the now-SSE connection), not a REST push (`/api/notifications` → 404). Verified-by-construction that run events drive them; a browser observation of the toast/panel firing over SSE is still owed.

## Still pending this session
- **B.7** live Playwright chat suite · **B.6b** browser notification observation · the `default`-profile re-confirms (CONTEXT §2/§5) · **B.1** per-turn image delivery trace · **B.4** cache_read>0 + ISS-033 count.
- **DEF-43-03-1** narrator live injection + seq reconciliation (43-06 backend half, run_commands.py:1243).
