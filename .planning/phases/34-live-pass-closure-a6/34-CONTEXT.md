# Phase 34: Live Pass & Closure [A6] — Live-Pass Worklist

**Gathered:** 2026-07-10
**Status:** SUPERVISED — needs live AWS Bedrock (SSO) + a running dev server + uvicorn. NOT an autonomous run.
**Purpose:** The consolidated worklist for the milestone-end live verification. Every "human_needed"/live-deferred item accumulated across Phases 29–38 is gathered here, ordered: (A) deferred WIRING (code — offline-doable, do first), (B) LIVE verification (needs SSO), (C) closure/sweeps.

<domain>
## Prerequisites (user runs)
- `aws sso login` — per [[local-run-bedrock]]: SSO profile `hex-ai-fe`, leave `ANTHROPIC_API_KEY` empty, `RUNS_ROOT` writable, run alembic first.
- Backend `uvicorn app.main:app --host 127.0.0.1 --port 8000` with `python3.11`; frontend `next dev`.
- QA login: `qa-enterprise@flowinqa.com` / `flowin-e2e-pass` (the `@flowin.test` users are unusable).
- Flags: `NEXT_PUBLIC_SSE_TRANSPORT` (SSE path), `BEDROCK_PROMPT_CACHE_ENABLED` (already ON since P26).

## Part A — Deferred WIRING (code; do first, offline-verify then live-confirm)
1. **Concierge caller-wiring (Phase 33 — [[phase33-concierge-dormant-wiring]]).** The Concierge subsystem is built + isolation-tested but wired to NO caller. Do: make `concierge=True` reachable; pass the FE props (DashboardLayout → RunChatLane); thread `compiled` onto `_ConciergeCtx` (M3 — manifest `chat:` inert live otherwise); **server-enforce the confirm-hold** (H1 — client-trust today, an integrity/idempotency gap); serialize the ORM read-tool rows (M2). Full list in `33/deferred-items.md`.
2. **SSE provider mount (Phase 29 human_verify #1).** Mount `RunConnectionProvider` in `frontend/src/app/layout.tsx` behind `NEXT_PUBLIC_SSE_TRANSPORT`. (LOCK-B kept legacy WS as the active transport; this is the supervised activation.)
3. **Steering live-drain (Phase 29 DEF-29-09-1).** The `engine.py` edit so a steering note reaches the RUNNING in-process `ectx` at the next dispatch — `_live_ectx_for_run` returns `None` today.
4. **Narrator live call-site (Phase 29 human_verify #3).** Invoke `chat_narrator.project_milestone_card`/`persist_milestone_card` from the engine/stream so milestone cards emit live (zero production callers today).

## Part B — LIVE verification (needs SSO)
Per ROADMAP SC + POR §76:
1. **Live multi-turn chat with images** on a real run (Phases 29/30).
2. **Steering mid-run** — a chat instruction lands in the NEXT agent's live prompt (`=== USER GUIDANCE ===`) (Phase 29).
3. **Concierge Q&A live** — answers from real run data; proposals execute only through existing channels behind confirm chips (Phase 33).
4. **`cache_read > 0` confirmation incl. multi-turn cache-point placement** — the standing P26 deferral (ISS-031/032); **ISS-033** direct-call agents (SmartPlanner/ClarifyEngine/handoff Test/Compliance) ride along — decide close-or-re-disposition.
5. **Unified `LaunchWizard` live launch** — prototype + ppt actually launch via `/dashboard` (the draft/pending contract is offline-proven byte-identical; Phase 37 WR-01).
6. **Live `GET /api/analytics/summary` HTTP round-trip** + **live notification PUSH** over the real connection (Phase 38).
7. **Playwright live suite green** — the mocked specs were live-deferred throughout (offline `webServer` timeout); run them live + the live chat suite.

## Part C — Closure
- Update ISSUES-REGISTER / FIX-REGISTER / IMPLEMENTATION-REGISTER with live re-confirms (ISS-004/005/006/011/029/031/032 live re-confirms; ISS-046/047/048 live-touch where relevant).
- Deferred-items sweep: each phase's `deferred-items.md`.
- The **WS→SSE deletion + INV-12 exit gate** (the LOCK-B supervised follow-up) — decide/execute only AFTER the live SSE cutover validates.
- `/gsd-complete-milestone` for v2.0 + reconcile the v1.0 close-out (POR §7).
</domain>

<decisions>
## Honest status going in
- **Everything offline is built + verified** (10/11 phases, byte-identical goldens, SC-001 proven). What Phase 34 adds is (i) 4 small WIRING edits (Part A — the deferred live-activation code) and (ii) LIVE confirmation of behavior that offline proof can't reach.
- **No offline evidence was fabricated as live.** Each Part-B item is genuinely unverified-until-live; the offline proofs (wire-parity golden, contract-parity byte-identical, unit tests) are strong predictors but not live confirmation.
- **Order matters:** Part A (wiring) before Part B (verify) — you can't verify Concierge Q&A live until the Concierge has a caller. Do A's 4 edits (offline-verify: goldens byte-identical, tsc, targeted tests), then SSO and run B.

## Deferred BEYOND this milestone (LOCK-E — do NOT build)
Team-sharing (ND-12), resume-from-failed (ND-4), per-agent prompt-override persistence (ND-7), image-persistence-on-reopen (ND-10), notifications reload-survival (Phase 38), the ND-13.6/7 product-input items, the Handoff screen (post-v2.0).

## Ship path reminder ([[ship-path-dev-codebuild]])
Integrate via **dev** (never main/staging); a dev push auto-fires a non-atomic CodeBuild→Docker→EC2 deploy behind 4 gates; merge dev INTO `feat/ui-2` first for a clean MR.
</decisions>

<specifics>
## Session flow when the user is ready
1. Confirm prerequisites (SSO active, servers up, alembic run).
2. Part A: dispatch the 4 wiring edits (offline-verify each: 5 goldens byte-identical, tsc identity, targeted tests, lint 4/0). Commit atomically.
3. Part B: drive the 7 live checks against a real Bedrock run; record each result (pass / issue) with evidence.
4. Part C: sweep the registers + deferred-items; decide the WS deletion; complete the milestone.
Live checks that fail → file as issues, fix, re-run. Do NOT mark milestone complete on any un-run Part-B item.
</specifics>
