# Phase 43: Concierge Live Wiring and Live-Pass Closure [A6-redux]

**Gathered:** 2026-07-15  ·  **Milestone:** v2.0 (Universal Run Chat & VelocityAI UI Convergence)  ·  **Branch:** `feat/ui-2`
**Status:** SUPERVISED — Part A + Part C are offline-doable; **Part B needs live AWS Bedrock** (SSO) + running dev server + uvicorn + alembic. NOT an autonomous run.
**Supersedes:** **Phase 34 (Live Pass & Closure [A6])** — never executed; its `34-CONTEXT.md` was written **2026-07-10**, before Phases 35–42 + the quick/FIX patches shipped. This phase carries every Phase-34 item and **updates it for the later run-screen / transport / composer changes**. (Mark Phase 34 superseded-by-43 in ROADMAP at plan time.)

> **How this CONTEXT was produced.** The ENTIRE `IMPLEMENTATION-REGISTER.md` (L1–3633) was read end-to-end and cross-checked against current code (file:line verified on FE + BE), plus `34-CONTEXT.md`, `33-concierge-compaction-a5/deferred-items.md`, `ISSUES-REGISTER.md`, `FIX-REGISTER.md`. The load-bearing crux — a settled-run free-text turn currently launches a `*_revision` pipeline, and the Concierge props are unwired — was independently orchestrator-verified. Treat the findings as verified.

---

## 0. Orientation — what's different from Phase 34's plan

Phase 34's shape (Part A wiring → Part B live → Part C closure) still holds. But the run screen was restructured THREE times since its CONTEXT was written (Phase 32 redesign, Phase 39 fidelity, **Phase 42 legacy-takeover removal**), so:

1. **A.1 (Concierge FE wiring) is materially harder than "add props."** The left chat lane currently treats a **settled-run free-text turn as a revision trigger** — so wiring the Concierge means **re-routing the free-text path**, not just attaching props. **[verified end-to-end]**
2. **The Concierge is transport-coupled to SSE/REST (`POST /messages`); the active transport is legacy WebSocket (`/ws/chat`), SSE dormant (LOCK-B).** So A.1's live reachability depends on a transport decision — a NEW **A.0**. **[verified]**
3. **Several Phase-34 refs are stale** — `ReviewGatePanel`/`QuestionnairePanel` were DELETED in Phase 42; the RunChatLane mount moved to `DashboardLayout.tsx:1660`. See the stale-ref table (§6).
4. **Several Part-B "live" items now have their OFFLINE half done** (Phase 37 LaunchWizard, Phase 38 analytics/notifications, Phase 30 run-entry images, Phase 42 mocked-e2e 132/0) — those shrink to a live-confirm only.

---

## 1. Part A — Updated offline-doable WIRING (do FIRST; offline-verify each: 5 characterization goldens byte-identical, `tsc --noEmit`, targeted tests, `lint-imports` 4/0; commit atomically)

### A.0 [RESOLVED 2026-07-15 → (a) Activate SSE; transport flip SEQUENCED to Part C]: Transport activation
The whole Concierge-live effort is gated by this. The `chat:concierge` subsystem is reachable ONLY via `POST /api/runs/{id}/messages` (`run_commands.py:622` → `route_chat_turn` → `CHANNEL_CONCIERGE` at `:815-874`, `converse` at `:852`). The active transport is the legacy WebSocket `/ws/chat` (`websocket.py:703`), which has **zero** concierge references. SSE is dormant: `NEXT_PUBLIC_SSE_TRANSPORT` defaults OFF (`env.ts:59-64`), `RunConnectionProvider` unmounted (returns inert `DEFAULT_VALUE`, `RunConnectionProvider.tsx:76-83`). **DECISION (user, 2026-07-15): (a) Activate SSE — but the transport flip is SEQUENCED to Part C, not Part A.**
- **Part A (offline, this phase's wiring):** wire the Concierge offline-correct against the `POST /messages` contract — the composer re-routing (A.1), the four backend defects (M1/M2/M3/H1) + the proposal drain, steering (A.3), narrator (A.4). NOTHING flips live in Part A: `NEXT_PUBLIC_SSE_TRANSPORT` stays OFF and the wiring is proven with the SSE path dark (5 goldens byte-identical, `tsc`, targeted unit tests, `lint-imports` 4/0).
- **Part C (ONE supervised cutover):** mount `RunConnectionProvider` (`app/layout.tsx`) + enable the flag so `useRunChat.sendMessage` routes to `POST /messages`. The live Concierge Q&A check (**B.3**) is verified AS PART OF this cutover; then `/ws/chat` is deleted (the INV-12 exit gate, **C.3**). Consequence: **A.2 (SSE mount) is a Part-C step**, and **B.3 is contingent on the cutover** — there is no Part-A live transport flip.
- **Rejected: (b) WS-route the Concierge** — would add concierge escalation onto `/ws/chat`, discarded when WS→SSE lands; avoided to prevent duplicate/throwaway backend surface.
> Note: the Phase-31 latent SSE `runId` bug was FIXED in Phase 32 plan 32-05 (**ISS-036 RESOLVED**, register L3032/L3615) — `useRunChat` targets `pipelineState.pipelineRunId ?? activePipelineRunId` — so activating SSE no longer spawns an unrelated run.

### A.1 Concierge composer re-routing (the CRUX)
**Frontend:**
- Attach the Concierge props at the RunChatLane mount (`DashboardLayout.tsx:1660`): `proposals` / `onConfirmProposal` / `onRejectProposal` / `onCompact` / `compactAvailable`. They EXIST on `RunChatLaneProps` (`RunChatLane.tsx:173/180/182/190/192`) but **no caller passes them** — grep-verified: "concierge" appears in FE `src` ONLY in `RunChatLane.tsx` + its test.
- **Re-route the settled-run free-text path.** Today `handleFreeText` (`RunChatLane.tsx:646-655`) is the single decision point: `if (runState==="complete" && onRevise) { onRevise(text); return; }` else `sendMessage(text)`. `onRevise` = `activeReviseHandler` (`DashboardLayout.tsx:1678` → `:1255-1260`) → `handleRevisePrototype` (`:539-552`) → **`onStartPipeline("prototype_revision", …)`** (sibling: ppt/user_stories/app_builder `_revision`). So "what's the status?" launches a revision. Make this Concierge-aware: an **ask** is answered by the Concierge (POST `{concierge:true}` via `useRunChat.sendMessage`), a **change request** still routes to `onRevise`. Classification is FE-side or deferred to the mechanical router — INV-1: NO workflow-name/agent-id branch.
- On chip confirm, POST `{concierge:true, confirm_proposal:{channel,params}}`.

**Backend (all four defects + the dead drain still present at verified lines):**
- **M3** — thread the run's `CompiledWorkflow` onto `_ConciergeCtx` (`run_commands.py:848-851`); else `concierge.py:270 getattr(ctx,"compiled",None)` is None → the manifest `chat:` block is never injected.
- **M2** — serialize the Concierge `_read_tools` ORM rows to plain dicts (`concierge.py:211`; `read_events`:221 / `list_refs`:227 / `get_ref`:233 / `read_gate_events`:238 return raw SQLAlchemy rows → the `@tool` coerces them to `str()` reprs → the live model gets no usable data; masked offline by the scripted-fake model).
- **H1** — server-enforce the confirm-hold (`run_commands.py:825-841`): on confirm, look up the durable `concierge-proposal:{message_id}:{channel}` pending row, verify exists+pending, dispose from the DURABLE params (not client `body.confirm_proposal`), mark resolved. (Pending write at `:538-551`; only guards today are the KAN-94/KAN-100 gate-live-state fences at `:557-570`.)
- **M1** — default a missing gate `action` to a non-consequential/explicit action, not `approve` (`run_commands.py:571`).
- **drain** — give `ConciergeCapability` a `drain_proposals` so `_drain_concierge_proposals` (`run_commands.py:478`, returns `[]` today) can surface tool-result proposals on a fresh ask (`converse()` returns `str` only today).

### A.2 SSE provider mount — **now a Part-C step** (per the A.0 decision)
Mount `RunConnectionProvider` in `frontend/src/app/layout.tsx` behind `NEXT_PUBLIC_SSE_TRANSPORT` (was outside Phase-29's 5-file LOCK-B scope). Per the A.0 decision this executes in **Part C as the supervised transport cutover**, together with the live Concierge check (B.3) and the `/ws/chat` deletion (C.3) — NOT in Part A.

### A.3 Steering live-drain (ALSO fixes per-turn images)
Implement the live-ectx registry so `_live_ectx_for_run` (`run_commands.py:361`, `return None` at `:373`) resolves the RUNNING in-process `ectx`; drain queued `steering_notes` into the next agent dispatch (`=== USER GUIDANCE ===`). **This same seam closes DEF-30-03-1 / DEF-29-09-1** (a per-turn image delivered to an already-running run — Phase 30/29).

### A.4 Narrator live call-site
Invoke `chat_narrator.project_milestone_card` / `persist_milestone_card` (`chat_narrator.py:188/234`, zero live callers) from the engine/stream so milestone cards emit live. **Harden the deep-link nonce FIRST** (Phase-29 WR-02: in-memory/unbounded/unscoped → DB-backed, ownership-checked) before live exposure.

### A.x [RESOLVED 2026-07-15 → BUILD NOW] — ISS-033 shared cached-invoke helper
SmartPlanner (`smart_planner.py:389`) + ClarifyEngine (`clarify_engine.py:492-493`) + handoff Test/Compliance call the model DIRECTLY → NO Bedrock prompt-caching + their tokens are UNCOUNTED in run cost. **DECISION (user, 2026-07-15): BUILD the shared cached-invoke helper in this phase.** Route those direct calls through it so they hit Bedrock prompt-caching and their tokens are counted; this directly feeds the **B.4** live check (`cache_read>0`, multi-turn cache-point placement). ISS-034 (dollar-savings display) rides alongside.

---

## 2. Part B — LIVE verification (needs Bedrock SSO; record each result with evidence — pass / issue)

The 7 headline checks (from Phase-34 SC), each un-verified-until-live:
1. **B.1** Live multi-turn chat **with images** on a real run (Phase 29/30). *(Run-entry image path already ad-hoc live-proven 2026-07-10, quick-260710-ftq, `image_count=1` reached spec-writer — register L2900/L3182; per-turn + document image paths still owed.)*
2. **B.2** **Steering mid-run** — a chat instruction lands in the NEXT agent's live prompt `=== USER GUIDANCE ===` (post-A.3).
3. **B.3** **Concierge Q&A live** — grounded/non-hallucinated answers from real run data; proposals execute only through existing channels behind confirm chips. **Verified DURING the Part-C SSE cutover** (post-A.1 offline wiring + A.2 mount + flag ON), per the A.0 decision — not a Part-A live flip.
4. **B.4** **`cache_read > 0`** incl. **multi-turn cache-point placement** — the standing P26 deferral (ISS-031/032); ISS-033 direct-call agents ride along (close-or-re-disposition).
5. **B.5** **Unified `LaunchWizard` live launch** — prototype + ppt actually launch via `/dashboard` (offline byte-identical, Phase 37 WR-01; ⚠ the Phase-41 single-screen Configure was built then REVERTED — quick-260713-rcf `131c4e30` — prototype/ppt route back to `LaunchWizard` because a bare `prototype` fails the backend `missing_template_context` guard, register L3519-3527).
6. **B.6** Live `GET /api/analytics/summary` HTTP round-trip **+** live notification **PUSH** over the real connection (Phase 38; offline half done).
7. **B.7** **Live Playwright chat suite green.** *(The MOCKED run-screen suite is already 132/0/42 after Phase 42's reconciliation — register L3622/L3629; only the LIVE chat suite + Phase-39's 4 shell-surface mocked reds ts-a/b/c/e + the `ts-l` `test.fixme` quarantines remain, register L3515-3517.)*

**Also fold these `default`-profile live re-confirms** (offline-proven, live pending): ISS-003 (token-delta A/B), ISS-004 (0 `<function_calls>`/`<invoke>` in live sdlc-governance chunks), ISS-011 (Phase-8 HITL 3 cases), ISS-027 ("Skip all & run directly"), P16 SC1/SC2 (`ValidationException→pipeline_failed` / `Stop→pipeline_cancelled` — confirmed on `srini`, re-confirm on `default`). See §5 for the exhaustive list.

---

## 3. Part C — Closure / sweeps

- **C.1** Reconcile ISSUES / FIX / IMPLEMENTATION registers with live results (ISS-004/005/006/011/027/029/031/032 re-confirms; ISS-033/034 disposition).
- **C.2** Deferred-items sweep across every phase's `deferred-items.md`.
- **C.3** The **WS→SSE deletion + INV-12 exit gate** (LOCK-B supervised follow-up) — decide/execute ONLY after the live SSE cutover validates (POR L38/L66). This is the milestone's big INV-12/INV-3 exit gate.
- **C.4** `/gsd-complete-milestone` for v2.0 + reconcile the v1.0 close-out (POR §7).

---

## 4. Genuinely-NEW considerations to encode in the plan (surfaced by Phases 35–42)

1. **Concierge-vs-revision composer routing (THE CRUX).** The left lane treats settled-run free text as a revision trigger, so A.1 must re-route `RunChatLane.tsx:648`, not just add props. A "status" question must be answered, not launch a run. **[verified]**
2. **Transport coupling.** The Concierge is reachable only via `POST /messages` (SSE/REST); the active transport is legacy `/ws/chat` (SSE dormant). A.1's live reachability depends on A.0/A.2 — a genuine architectural fork. **[verified]**
3. **Steering + per-turn images share ONE seam** (`_live_ectx_for_run → None`): fixing A.3 also closes DEF-30-03-1. Plan them together.
4. **Run-screen refs are stale.** `ReviewGatePanel`/`QuestionnairePanel` are DELETED; the mount is at `DashboardLayout.tsx:1660`; gate/clarify are inline (Steps `InlineGateActions`/`InlineClarifyActions`); the `<spec>/<tasks>/<analysis>` discriminator/parsers now live in `components/results/artifactPreview.tsx` (Phase 42). Any plan citing the old full-screen panels is obsolete.
5. **Offline halves already landed.** Phase 37 LaunchWizard, Phase 38 analytics/notifications, Phase 30 run-entry images, Phase 42 mocked-e2e — those Part-B items are live-confirm-only.

---

## 5. Exhaustive live-deferred register (the Part B/C sweep must reconcile ALL of these)

Consolidated in `22-LIVE-01-EVIDENCE.md` (register L2317-2332): COMPACT-03 live token-delta [L408]; P6 CR-02 live-checkpointer `:retry{n}` [L679]; P8 OTLP live collector (ISS-010, optional) [L880]; P13 F1 `review_gate_ready` on live WS [L1307]; P13 F4 → ISS-004 [L1310]; P13 F5 → ISS-005/006 [L1311]; P14 SC4 (content closed by P15) [L1486]; P16 SC1/SC2 re-confirm-on-`default` [L2328-2329]; P19 ISS-004 (0 tool-XML in live chunks) [L2330].
Issue-tracked: **ISS-003** [L1804]; **ISS-004** (live re-confirm pending) [L2001]; **ISS-005/006** (since live-confirmed — reconcile the register's stale "deferred" note); **ISS-011** [L1804]; **ISS-027**; **ISS-031/032** (`cache_read>0`) [L2595]; **ISS-033 (OPEN — decide)** [L2593]; **ISS-034 (OPEN)** [L2594].
Phase-29 chat backbone [L2810-2818]: RunConnectionProvider unmounted (=A.2); DEF-29-09-1 steering (=A.3); narrator zero callers (=A.4); **WR-02** nonce hardening; **WR-03** `/messages` gate actions can't carry `edited_content` (thread it or document gate-edit as `/gate`-only); **IN-01/IN-02** (`SSE_STREAM_IDLE_TIMEOUT_SECONDS` unenforced; `_gate_is_pending` reaches a private dict); KAN-101 base-thread unbounded-replay audit.
Phase-30 [L2896-2899]: DEF-30-03-1 (=A.3); `StartingPointCard.attachmentRefs` no caller; live multimodal doc+per-turn image.
Phase-32/37/38 live-deferred (offline half done): Phase-32 live Audit-tab data + e2e + reskin pixel [L3087]; Phase-37 live create→launch [L3396/L3405]; Phase-38 live notification PUSH + analytics round-trip [L3475].

---

## 6. Stale-ref → current (all verified this session)

| Historical ref (34/33 docs) | Current [verified] |
|---|---|
| `DashboardLayout.tsx:~1602` (RunChatLane mount) | **`DashboardLayout.tsx:1660`** (Concierge props NOT passed) |
| free-text → revision path | `RunChatLane.tsx:646-655` → `onRevise` (`DashboardLayout.tsx:1678/1255-1260/539-552`) → `onStartPipeline("prototype_revision")` |
| `run_commands.py:825-841` (confirm / H1) | same |
| `run_commands.py:538-549` (pending write) | **`:538-551`** |
| `run_commands.py:848` (`_ConciergeCtx` / M3) | **`:848-851`** |
| `chat_router.py:266` (escalation) | same (`MessageCommand.concierge` `:346`, read `:726`) |
| M1 default-approve | `run_commands.py:571` |
| M2 read tools | `concierge.py:211` (ORM rows) |
| `_live_ectx_for_run → None` (A.3) | `run_commands.py:361`, `return None` at `:373` |
| narrator callers | `chat_narrator.py:188/234`, ZERO live callers |
| `ReviewGatePanel` / `QuestionnairePanel` | **DELETED (Phase 42)** — obsolete |

---

## 7. Invariants & constraints (do NOT violate)
- **SC-001 / INV-1** — every render/route branch keys on GENERIC state (`runState`, `laneGate`, the artifact discriminator), never a workflow-name/agent-id literal. The Concierge system prompt is DATA-composed (no `pipeline_type`/`spec.id` branch).
- **INV-3** — the 5 characterization goldens stay byte/event-identical for the offline (Part A) wiring; `concierge_proposal` is the only new event and fires on zero golden paths. Any live-pass code change re-runs all 5 goldens.
- **INV-13** — the Concierge model reaches Bedrock ONLY via `DeepAgentRunner` (Haiku default); no `create_deep_agent`.
- **LOCK-B** — legacy WS is the active transport; the SSE cutover (A.0(a)/A.2/C.3) is a SUPERVISED decision, not an autonomous flip.
- **Additive-only** (Q3) — new persistence carries `owner_id`+`workspace_id`; IDOR→404.
- **Ship path** ([[ship-path-dev-codebuild]]) — integrate via `dev` (never main/staging); merge `dev` INTO `feat/ui-2` first for a clean MR.
- **Deferred BEYOND this milestone (LOCK-E — do NOT build):** team-sharing (ND-12), resume-from-failed (ND-4), per-agent prompt-override persistence (ND-7), image-persistence-on-reopen (ND-10), notifications reload-survival, ND-13.6/7 product-input, the Handoff screen (post-v2.0).

## 8. Prerequisites (user runs, for Part B) — [[local-run-bedrock]]
- `aws sso login` (SSO profile per the live-run memory; leave `ANTHROPIC_API_KEY` empty; `RUNS_ROOT` writable; alembic first).
- Backend `uvicorn app.main:app --host 127.0.0.1 --port 8000` (`python3.11`); frontend `next dev`.
- QA login: `qa-enterprise@flowinqa.com` / `flowin-e2e-pass` (the `@flowin.test` users are unusable).
- Flags: `NEXT_PUBLIC_SSE_TRANSPORT` (per A.0), `BEDROCK_PROMPT_CACHE_ENABLED` (ON since P26).

## 9. Session flow
1. Confirm prerequisites. 2. **A.0 RESOLVED** → (a) Activate SSE, transport flip sequenced to Part C (§A.0); **ISS-033 helper = BUILD** (§A.x). 3. Part A: the wiring edits (offline-verify each: 5 goldens byte-identical, tsc, targeted tests, lint 4/0; commit atomically). 4. Part B: drive the live checks on a real Bedrock run; record each with evidence. 5. Part C: sweep registers + deferred-items; decide the WS deletion; complete the milestone. Live checks that fail → file as issues, fix, re-run. Do NOT mark the milestone complete on any un-run Part-B item.
