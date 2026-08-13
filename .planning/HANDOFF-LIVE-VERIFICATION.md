# Handoff — what still needs LIVE Playwright + backend verification

**Session:** 2026-08-12 · **Branch:** `bugfix/spec-revision-context-loss` @ `c04a08b4`, **pushed**, tree clean
**Shipped:** FIX-231 … FIX-246 (16 fixes) closing ISS-034, 070, 074, 082, 083, 087, 088, 089,
091, 092, 097, 102, 121, 123, 124, 126.
**Filed, not fixed:** ISS-094 … ISS-142 (~40 new rows). ISS-103 deferred with a mechanical reason.

**Standing gates, re-measured after every single fix:** characterization goldens **10 passed**,
**zero golden files ever regenerated**; `lint-imports` (run from `backend/`) **4 kept / 0 broken**;
the pre-existing red set byte-identical throughout.

---

## 0. Before you test anything

The local backend must be restarted onto this code (any running instance predates the last fixes):

```
AWS_PROFILE=hex-uki AWS_REGION=eu-central-1 ENV=development ANTHROPIC_API_KEY= \
RUNS_ROOT=/tmp/flowin-runs DATABASE_URL="sqlite:///./dev.db" \
python3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --timeout-graceful-shutdown 5
```

Frontend: `cd frontend && npm run dev` (:3000). Login `qa-enterprise@flowinqa.com` / `flowin-e2e-pass`.
SSO is live on profile **`hex-uki`** (acct 265331052706, eu-west-2) — **`hex-ai-fe` is a DIFFERENT,
expired account**; the Bedrock inference profile `eu.anthropic.claude-haiku-4-5-20251001-v1:0`
resolves in eu-central-1 under `hex-uki` (verified, control-plane call, free).

### Money rules — non-negotiable
- **Never launch/resume/approve an `od_prototype`.** 5–21M tokens; measured ceiling **37.3M**.
- **Run `41f77342-…` is a PAUSED `od_prototype`** sitting on the dashboard. Never approve it.
- **Dashboard runs `6e38b9a7` and `41f77342` have IDENTICAL brief text** and differ only by the
  status prefix. **Match on the `DONE`/`CANCELLED` prefix, never on brief text.** Reusable safe-open
  helper: `scratchpad/batch2/lib-safeopen.mjs` (session scratchpad).
- Never `getByText(/Spec\b/i)` — `\b` also matches "Approve the spec".
- Never sweep `header button` for "Run History" — it clicks the sidebar run pill and OPENS THE
  ACTIVE RUN. That mistake cost 16,530,718 tokens once.
- Opening a **terminal** run from history is free and starts no agent.

---

## 1. NEVER live-verified — do these first

| # | Fix | What to do | Expected | Cost |
|---|---|---|---|---|
| 1 | **FIX-242 · ISS-097** *(critical)* | In the composer build a **fan-out** workflow and **tick the review-gate box on the fan-out agent**, then run it | Runs straight through. **Before: hung forever with NO visible gate and no way out** — zero frames on the wire, zero rows in the log, status `waiting_for_user` indefinitely | a few ¢ |
| 2 | **FIX-241 · ISS-070** | Reject at a gate normally through the UI | Rejection still works. (The malformed-action path is API-only; the fix constrained the accepted set, so confirm the *legitimate* path is untouched) | ~$0.01 |
| 3 | **FIX-243 · ISS-089** | Start a run → **Stop** → kill the backend → start it again | **The run must NOT come back to life.** Status must be `cancelled` and the boot scan must spawn no driver | ~$0.01 |
| 4 | **FIX-244 · ISS-124** | Stop a run, then read `workflow_runs.status` | Must be **`cancelled`**, not `failed`. *(Before this fix the owner's Stop was recorded as a **failure** — worse than the row claimed)* | shares #3 |
| 5 | **FIX-245 · ISS-126** | Open an **old cancelled** run from history | Header reads **"Cancelled"**, no Stop button. Browser A/B already passed on `808612bf` vs `1ea6d262` — **re-confirm after the restart**, since 20 green unit tests did nothing on screen before three separate changes landed | free |

---

## 2. Partially verified — the unproven half

| Fix | Verified | **NOT verified** |
|---|---|---|
| **FIX-233 · Concierge** | bounded (**16,001 tok** vs hundreds of thousands), tools visibly used, `chat_usage` recorded, $0.0116 | **Answer QUALITY.** No test can judge it. Ask real questions on a long run — highest-risk thing shipped |
| **FIX-234 · shutdown** | probe only: 31s hang → 5.8s clean exit | **Real app under a LIVE stream.** Start a run, and *while streaming*, `kill -TERM` the backend → should die in ~5s |
| **FIX-235 · reducer** | replay half: two replays byte-identical | **Partial redelivery mid-stream.** Reload or drop the network mid-run → agent text must not duplicate |
| **FIX-239 · cache delta** | backend correct vs a real **negative** delta; the catastrophic-number guard proven | **The visible line has never rendered** (see §3) |

---

## 3. Known-wrong — do NOT report these as new bugs

- **Analytics cache-savings line shows nothing.** Correct. Every legacy run contributes a zero delta
  by design, so the aggregate rounds to 0% and suppresses. It appears once the 30-day window fills
  with metered runs. Filed as **ISS-122** (the `metered_runs` count is fetched but not surfaced).
- **Old cancelled runs may still show a lingering clarify panel.** On `808612bf` that panel is
  **ISS-123 damage** — its `questionnaire_complete` row is one of the 15 destroyed events.
- **Mocked Playwright suite is ~33 red** (**ISS-076**) and `playwright.config.ts` sets
  `reuseExistingServer: true`, so a worktree baseline silently tests the main tree.
  **Compare failing IDs, never counts**; check `lsof -ti:3000` first.
- **Frontend `tsc --noEmit` has 2 pre-existing errors**; `ResultCard.test.tsx` is 1 failed / 12 passed
  (**ISS-114**).
- Backend pre-existing reds (unchanged all session): `test_gates` 3 · `test_declared_gate_streaming` 3 ·
  `test_wire_parity` 4 · `test_prompt_contracts` 1 · `test_model_factory` 6 · `test_rest_run_launch` 2 ·
  `test_chat_messages_endpoint` 3 · `test_mechanical_router` 3 · `test_concierge_proposal_channels` 1 ·
  `test_attach_replay_matrix` 1 · `test_phase6_frontend_consistency` 2 · `test_sample_brownfield_workflow` 2 ·
  `test_text_only_prompt_hygiene` 1 · `test_execution_engine` 3.

---

## 4. Traps that cost real time this session

- **The offline harness stubs `_run_review_gate` as an INSTANCE attribute**, silently shadowing the
  real method. An investigation nearly filed ISS-097 "not reachable" because of it — `del
  engine._run_review_gate` is what exposed the defect. **Any gate assertion on that harness must
  un-shadow or it proves nothing.**
- **`backend/dev.db` is 246 MB; there are TWO 0-byte decoys** (repo root and `backend/backend/`).
  Always use an absolute path.
- **`lint-imports` from anywhere but `backend/`** prints "Could not read any configuration" and reads
  as a false pass.
- **A bad path in a multi-path pytest invocation** yields `collected 0 items` with **exit 0** — a
  green-looking suite that never ran.
- **Two disjoint `TEST-*` id series**: `FIX-TEST-REGISTER.md` uses padded `TEST-0NN` (now 029);
  `.knowledge/cards/TEST-NN.md` is a separate series (max 49). The four-source max returns the wrong one.
- **Green unit tests are not verification here.** FIX-245 had 20 green tests and did nothing on screen.

---

## 5. Highest-value open work (my ranking)

1. **ISS-126 residual / ISS-138** — the FIX-201 bridge copies legacy state into the store *wholesale*
   and clobbered the terminal patch ~4s later. Reconciled, but the dual-container arrangement stands.
2. **ISS-131** *(created by FIX-242)* — a fan-out step that both declares a human gate **and** has its
   agent ticked now has its declared gate deduped against a gate that no longer fires ⇒ **no gate at
   all**. Composed-selections only; no shipped manifest reaches it.
3. **ISS-134** — the durable-cancel fix is **single-process-safe only**. `_is_run_live` is process-local.
   **Breaks under the locked ECS Fargate target.**
4. **ISS-133** — `_stamp_resume_marker` still appends through the collision-unsafe `max(seq)+1` path.
5. **ISS-076** — until the mocked suite is trustworthy, every frontend fix is verified by hand.

---

## 6. Cost facts (measured, correcting the registers)

Ceiling **37,327,891 tok / $7.07** (`6e38b9a7`). The incident that started this work: `d5dbc9f2`
**16,530,718 tok / $3.58 total, ≈$1.61 (45%) billed AFTER the cancel returned success**.
All 14 metered runs, all time: **78,203,819 tok / $17.75**.
**Say the dollars, not just the tokens** — on this Haiku workload it is a correctness-and-trust
defect first, a cost defect second. On an Opus-tier model it is ~an order of magnitude worse.
**Total live spend for this session's entire verification pass: $0.079.**
