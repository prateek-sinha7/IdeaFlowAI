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

## Remaining live checks (pending this session)
- **B.1** multi-turn chat + per-turn/document images · **B.2** mid-run steering into the next agent's live prompt · **B.4** `cache_read>0` incl. multi-turn cache placement (+ ISS-033 agents counted) · **B.5** unified LaunchWizard live launch (prototype+ppt) · **B.6** analytics round-trip + notification push · **B.7** live Playwright chat suite · plus the `default`-profile re-confirms (CONTEXT §2/§5).
- **DEF-43-03-1** narrator live injection + seq reconciliation (43-06 backend half, run_commands.py:1243) — pending.
