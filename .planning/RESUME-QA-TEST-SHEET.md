# Resume QA Test Sheet — milestone v3.0 live-Bedrock pass (feat/ui-2)

> Persisted QA record for the consolidated live verification of **milestone v3.0 — Top-Tier Resume & Durable Execution** (Phases 45–50, RESUME-05..18), plus regression of every existing surface those phases touched. Offline all 30 verification criteria passed; this campaign proves the same behavior on real Bedrock with real crashes.
>
> **Status legend:** ⬜ pending · 🔄 in-progress · ✅ pass · ❌ fail (→ BUG-Rxx in [RESUME-QA-BUG-LOG](./RESUME-QA-BUG-LOG.md)) · ⚠️ pass-with-concern · ⛔ blocked/input-gated · ⏭️ skipped/conditional
> **Evidence:** screenshots in the job scratch `shots-resume/`, curl transcripts as `.txt` beside them, DB evidence via SELECT-only psql (queries in §0.5). Every ❌ gets a deep-investigation agent (reads `.planning/IMPLEMENTATION-REGISTER.md` to EOF) BEFORE the bug is logged.
>
> Last updated: 2026-07-19 (campaign authored; execution pending SSO).

## 0. Runbook (session prep)

### 0.1 One user step

```
aws sso login --profile hex-ai-fe        # interactive browser login (type `! aws sso login --profile hex-ai-fe` in the session)
```

### 0.2 Backend — **NO `--reload` for this campaign**

`--reload` runs a supervisor that instantly restarts a SIGKILLed worker — it would silently fake every crash test. Run bare uvicorn so `kill -9` is a real crash and every restart is deliberate.

```
cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend        # ABSOLUTE path (stray backend/backend exists)
export AWS_PROFILE=hex-ai-fe            # Bedrock provider; leave ANTHROPIC_API_KEY empty
python3.11 -m alembic upgrade head      # brings 0026 (subagent task identity — additive nullable, safe)
python3.11 -m uvicorn app.main:app --port 8000   # NO --reload
```

**Crash procedure:** `kill -9 <uvicorn pid>` (SIGKILL — no graceful cleanup, the honest crash), then relaunch the same command. **Broken-env restart** (for the D1b failed-run specimen): relaunch with `AWS_PROFILE` unset/bogus so the first model call errors.

### 0.3 Frontend + login

```
cd frontend && npm run dev              # http://localhost:3000  (never 127.0.0.1)
```
Login `qa-enterprise@flowinqa.com` / `flowin-e2e-pass`. API token for curl:
```
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login -H 'content-type: application/json' \
  -d '{"email":"qa-enterprise@flowinqa.com","password":"flowin-e2e-pass"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
```

### 0.4 Launch recipes (from the SSE campaign)

- `od_prototype` — needs `template_id` + `design_system_id` (the wizard supplies them; API launch must include both). Richest subject: clarify → review gates (spec/plan Human_Gate) → per-task build (THE task-cursor surface).
- `user_stories` — brief-only; cheapest full pipeline; clarify + 6 sequential agents (THE step-cursor surface).
- `sample_fanout` — file-trusted manifest, 3 parallel self-copy workers writing disjoint `part_*.txt`, `copy_disjoint` merge (THE fan-out crash surface). `sample_wave` — 4 tasks in 2 dependency waves. Verify launchability via `POST /api/runs` at session start; if not catalog-exposed, launch via API `type`.
- Custom — via the composer (catalog recipe in `.planning/SSE-QA-TEST-SHEET.md` / composer QA memory).

### 0.5 DB evidence recipes (SELECT-only — never mutate)

```sql
-- status ladder for a run
SELECT id, status, error IS NOT NULL AS has_err, updated_at FROM workflow_runs WHERE id='<RUN>';
-- 0026 task-identity stamping + which tasks ran/skipped (duplicates = red flag)
SELECT task_id, worker_index, status, created_at FROM subagent_runs WHERE run_id='<RUN>' ORDER BY created_at;
-- uploads durably mirrored (Phase 47)
SELECT kind, version, created_at FROM artifact_refs WHERE run_id='<RUN>' AND kind='upload_text';
-- gate-edit lineage (Phase 48)
SELECT kind, version, derived_from FROM artifact_refs WHERE run_id='<RUN>' AND derived_from IS NOT NULL;
-- open-gate pendency: a review_gate_ready with no later resolution event
SELECT type, seq FROM run_events WHERE run_id='<RUN>' AND type LIKE '%gate%' ORDER BY seq;
```
(Adjust table/column names against the live schema at session start if they drift; keep SELECT-only.)

### 0.6 Known-open pre-existing (do NOT re-log as new bugs)

- **BUG-009** (SSE log) — od_ppt can complete with an empty deck (prompt-contract, ROOT-CAUSED, open). Not resume-related.
- Offline-held red suites (proven pre-existing at phase baselines): `redo_gate_safety` 4/3 harness drift · `declared_gate_streaming` 3 FK env-reds · `test_migrations` 2 stale-head asserts · `attach_replay` 1 SSE red.
- **AUD-1 (explicit audit item, not a known bug):** offline analysis found `resume_run` itself writes no `WorkflowRun.status` — the restore scan's driver must land the terminal status. R-A1's final-status check IS this audit; if a crashed-and-auto-resumed run completes but its DB status stays `running`, that's the first bug of the campaign.

---

## A. Crash → auto-resume (restart while running) — Phases 45/46

Kill the backend mid-run, restart it, and the restore scan must resume the run correctly: completed work skipped (per-task cursor + 0026 identity), disk re-materialized from durable artifacts, and — the Phase 46-05 headline — the resumed half is **fully alive** (milestone cards, steering, Concierge), where before v3.0 it ran silent.

| ID | Scenario | Expected proof | Evidence / shots | Status | Bug |
|----|----------|----------------|------------------|--------|-----|
| R-A1 | od_prototype: launch → let **≥2 build tasks complete** (watch steps UI) → `kill -9` → restart → auto-resume → completes | Restore scan picks it up; `run_resuming` marker in stream; completed tasks **skipped** (no duplicate `subagent_runs` rows for done task_ids; pre-crash pages NOT regenerated); deliverable contains ALL pages incl. pre-crash ones (re-materialization); history shows **one** run; **final DB status = `completed`** (AUD-1) | `a1-precrash-steps` (N complete visible) · `a1-postrestart-stream` (live badge + resuming marker) · `a1-deliverable` · `a1-history` · DB: status ladder + subagent_runs (task_id/worker stamped, no dupes) | ⬜ | |
| R-A2 | Live-layer alive on the resumed half (46-05 dormancy fix) | During R-A1's resumed half: milestone cards render in the lane; steering composer accepts a note and the run acknowledges/applies it; Concierge answers | `a2-milestone-cards` · `a2-steer-ack` | ⬜ | |
| R-A3 | Steering re-drain: send a steering note, `kill -9` BEFORE it's consumed → restart | The un-consumed note is re-drained on resume (visible in stream/agent behavior), not lost | `a3-redrain` | ⬜ | |
| R-A4 | user_stories: crash **between agents** (≥2 agents complete) → restart | Step-level resume (Phase 45 strategy-conditional completeness): completed agents skipped, next agent runs, pipeline completes; no re-run of finished agents | `a4-precrash` · `a4-postrestart` · `a4-complete` | ⬜ | |
| R-A5 | Crash EARLY (during planning/clarify-gen, 0 tasks done) → restart | Resumes from the incomplete step (nothing to skip); completes normally | `a5-postrestart` | ⬜ | |
| R-A6 | Fan-out crash: `sample_fanout` (3 parallel workers) killed mid-fan; separately `sample_wave` killed after wave 1 | Completed workers skipped (DB `worker_index` rows), remaining workers run, `copy_disjoint` merge yields ALL `part_*.txt` (mid-wave merge re-entry); wave 2 deps still honored | `a6-fanout-resume` · `a6-deliverable` · DB worker rows | ⬜ | |
| R-A7 | Double-crash ladder: crash the RESUMED run of R-A1 again mid-build → second restart | Second resume also correct — cursor monotonic, still no duplicate artifacts/rows, completes | `a7-second-resume` | ⬜ | |

## B. Uploads durability — Phase 47

| ID | Scenario | Expected proof | Evidence / shots | Status | Bug |
|----|----------|----------------|------------------|--------|-----|
| R-B1 | Attach a text document (docx/pdf) at launch → clean run, NO crash | Ingest dual-write regression: run uses doc facts in spec/output; DB has `upload_text` artifact row; normal path byte-normal | `b1-attach` · `b1-output-uses-doc` · DB upload_text | ⬜ | |
| R-B2 | Doc attach → crash mid-build → restart → auto-resume | Post-resume agents STILL doc-grounded (durable fallback — the pre-v3.0 failure was silent context loss); run completes citing doc facts in post-crash tasks | `b2-postresume-output` · DB: upload_text row created pre-crash | ⬜ | |
| R-B3 | IMAGE attach → crash → resume | Completes WITHOUT error; image context absent post-resume — **EXPECTED** (ND-10: images locked transient). Document observed behavior; only a crash/error is a bug | `b3-resume-ok` | ⬜ | |

## C. Gates & clarify survive restart — Phase 49 (KAN-88)

The headline restoration: a run parked `waiting_for_user` used to be flipped **failed** on restart. Now it re-arms. All actions ride `POST /api/runs/{id}/gate` — approve/reject/redo/update_specs, with `edited_content` on approve for the edit path (KAN-98); use curl where the FE lacks a button.

| ID | Scenario | Expected proof | Evidence / shots | Status | Bug |
|----|----------|----------------|------------------|--------|-----|
| R-C1 | od_prototype parked at review gate → `kill -9` → restart | Status **stays `waiting_for_user`** (NOT failed — the KAN-88 flip is gone); backend log shows re-arm; DB status identical before/after | `c1-status-after-restart` · DB before/after · log excerpt | ⬜ | |
| R-C2 | Reopen the re-armed run in FE | Gate UI renders via SSE-attach re-emit (D-14g): "Paused · review gate" + the REAL pre-crash spec text (WR-02 — reviews actual output, not a placeholder) | `c2-gate-ui-postrestart` (spec text legible) | ⬜ | |
| R-C3 | **Approve** post-restart | Run proceeds downstream (next agent streams) → completes/reaches next gate; status transitions normally | `c3-approved-proceeding` | ⬜ | |
| R-C4 | **Approve + `edited_content`** post-restart (KAN-98 edit) | Downstream consumes the EDITED spec (visible in later output); DB `derived_from` lineage populated (Phase 48) | `c4-curl.txt` · `c4-downstream-uses-edit` · DB derived_from | ⬜ | |
| R-C5 | **Redo numbering across restart:** redo once live (`:redo1`) → park again at gate → `kill -9` → restart → redo again | Second redo is attempt **2** (`:redo2` thread / `redo_attempt=2` in gate_events) — never reuses the pre-restart thread (P23 replay bug class); output regenerates; then approve → proceeds | `c5-redo2` · DB/log gate_events attempts | ⬜ | |
| R-C6 | **Reject** post-restart (fresh gated run) | Behaves exactly as a live reject does today | `c6-reject` | ⬜ | |
| R-C7 | **update_specs** post-restart | The Phase-27 analysis sub-pipeline fires from the re-entered loop; gate re-presents after | `c7-update-specs` | ⬜ | |
| R-C8 | **Clarify twin:** run parked at questionnaire → `kill -9` → restart → reopen | SAME questions replayed from durable payload — byte-identical, near-instant, **no model call** (log shows replay, not generation); answering rides unchanged `POST /answers`; run proceeds to build normally | `c8-questions-before` · `c8-questions-after-restart` (identical) · `c8-proceeding` · log | ⬜ | |
| R-C9 | Re-arm fail-safe (observe-only) | IF a re-arm ever fails, the run must fall back to `failed` (honest), never hang `waiting_for_user` with no waiter. Opportunistic — log if seen | log excerpt | ⏭️ | |

## D. User resume-from-failed — Phase 50 (`POST /api/runs/{id}/resume`)

No FE button yet (deferred) — the endpoint is driven by curl; the FE story is: refresh/reopen the run after resume → `running` ∈ AUTO_STREAM_STATUSES → live stream attaches.

| ID | Scenario | Expected proof | Evidence / shots | Status | Bug |
|----|----------|----------------|------------------|--------|-----|
| R-D1a | **Specimen A — fail-fast:** launch BEFORE SSO login (or bogus profile) → first model call errors | Run lands `failed` honestly, 0 tasks, error recorded | `d1a-failed-history` · DB status/error | ⬜ | |
| R-D1b | **Specimen B — partial:** healthy launch → ≥2 tasks done → `kill -9` → restart with `AWS_PROFILE` unset → auto-resume errors → `failed` → restart healthy | Run lands `failed` with PARTIAL durable artifacts (the reopen-and-fix precondition) | DB: failed + partial subagent_runs/artifact_refs | ⬜ | |
| R-D2 | **The headline:** `curl -X POST .../api/runs/<D1b>/resume -H "Authorization: Bearer $TOKEN"` | 200; status `failed→running`; `run_resuming` marker; FE reopen auto-attaches live; completed tasks SKIPPED (cursor); deliverable completes; **same run id** — history shows ONE row, family intact; terminal status lands honestly | `d2-curl-200.txt` · `d2-live-stream` · `d2-deliverable` · `d2-history-single-row` · DB ladder | ⬜ | |
| R-D3 | Resume the D1a zero-task specimen (after SSO fixed) | Runs from planning → completes (fail-fast case also recoverable) | `d3-complete` | ⬜ | |
| R-D4 | **Negative battery** (curl transcripts): resume a `completed` run · a `cancelled` run (Stop one first — R-F5) · double-POST while the resumed run is live · bogus run id · no token | 409 `run_not_resumable` · 409 `run_not_resumable` · 409 `pipeline_already_running` · 404 · 401. No unguarded re-mint path | `d4-curl.txt` (full transcript) | ⬜ | |
| R-D5 | Reopen a `failed` run in FE BEFORE resuming | Static view, no stream (terminal — intended BUG-013 semantics), error surfaced | `d5-failed-static` | ⬜ | |
| R-D6 | Failed run with an OPEN durable gate → resume re-enters the GATE, not past it (49 classifier override) | Conditional — needs a natural specimen (e.g. C9 fail-safe fired). Covered offline; opportunistic live | — | ⏭️ | |

## E. Task-list edit → reconciliation — Phase 48

Driver: the gate-edit path (`approve` + `edited_content` on the plan/spec gate). Task identity is content-addressed (`task_key` = upstream-hash · content · ordinal) — an upstream edit re-keys downstream tasks (they re-run); untouched prefixes keep their artifacts.

| ID | Scenario | Expected proof | Evidence / shots | Status | Bug |
|----|----------|----------------|------------------|--------|-----|
| R-E1 | Edit ONE task's requirement at the gate → approve | Affected task + its downstream re-run; deliverable reflects the edit; untouched tasks keep artifacts (timing/log/no-dup evidence) | `e1-edited-deliverable` · DB task_list versions | ⬜ | |
| R-E2 | Edit that DELETES a task → approve | Build excludes it; assembly omits the page (count drops); the old artifact stays as a benign orphan (kept in history, out of the deliverable) | `e2-deliverable-count` · DB | ⬜ | |
| R-E3 | Edit that ADDS a task → approve → crash mid-build after some tasks → restart → auto-resume | Task keys stable across the restart: completed keys skip, the added task builds, deliverable complete — reconciliation + cursor compose | `e3-postresume` · DB subagent_runs keys | ⬜ | |

## F. Regression — existing surfaces the milestone touched

The engine hot paths (`_first_incomplete_step`, `persist_task_html`, task_loop/wave strategies, gate loop entry, clarify engine, ingest, drivers) were all modified. A clean, crash-free pass over each is the anchor that v3.0 changed nothing it shouldn't have.

| ID | Scenario | Expected proof | Evidence / shots | Status | Bug |
|----|----------|----------------|------------------|--------|-----|
| R-F1 | **The anchor:** clean od_prototype full ladder — launch → clarify (questions generated ONCE) → gate approve → build → complete. No restarts | Every stage visually/behaviorally normal; SSE healthy; deliverable renders; status `completed` | `f1-clarify` · `f1-gate` · `f1-build` · `f1-deliverable` | ⬜ | |
| R-F2 | Clean custom composer workflow → completes; PLUS the CWF-001 regression: an unsatisfiable-DAG custom run lands `failed` (not "completed") | Composer catalog path unaffected by identity-based skip changes | `f2-custom-complete` · `f2-dag-failed` | ⬜ | |
| R-F3 | `sample_fanout` + `sample_wave` CLEAN runs (no crash) | Fan-out/wave strategies with the new identity stamping behave identically; disjoint merge intact | `f3-fanout-clean` | ⬜ | |
| R-F4 | Stop/cancel mid-run | `pipeline_cancelled` → status `cancelled`; feeds R-D4 (cancelled → 409 on resume) | `f4-cancelled` | ⬜ | |
| R-F5 | Refinement/revision on a COMPLETED run via chat | Revision launches and completes (BUG-003 fix holds; shared engine paths unbroken); family linkage correct | `f5-refinement` | ⬜ | |
| R-F6 | History across the campaign menagerie | completed / failed / cancelled / waiting_for_user / running rows all show correct status + type; resumed runs appear ONCE | `f6-history-menagerie` | ⬜ | |
| R-F7 | Idle-backend restart (no live runs) | Startup clean, alembic no-op at 0026, restore scan no-ops, ZERO status flips (DB statuses identical before/after) | log excerpt · DB count-by-status before/after | ⬜ | |
| R-F8 | Steering on a never-crashed live run | Normal steering unaffected by the re-drain addition | fold into R-F1 evidence | ⬜ | |
| R-F9 | Concurrent: 2 runs live during ONE crash → restart | BOTH resume correctly (multi-run restore; pool sized post-BUG-004) — stretch goal | `f9-both-resumed` | ⬜ | |
| R-F10 | Transport invariant re-assert | 0 `/ws/chat` connections across the campaign; SSE sole down-channel (v3.0 added no WS types) | devtools check, note per session | ⬜ | |

---

## Coverage map (phase → rows)

- **45 completeness fix** → R-A4, R-A5, R-F1
- **46 cursor + capture + re-materialization + live-layer** → R-A1, R-A2, R-A3, R-A6, R-A7, R-D2, R-F3
- **47 uploads durability** → R-B1, R-B2, R-B3
- **48 task identity + reconciliation** → R-E1, R-E2, R-E3, R-C4 (derived_from)
- **49 gate/clarify restart** → R-C1..C9
- **50 resume-from-failed** → R-D1a..D6
- **Regression of touched surfaces** → R-F1..F10 (+ AUD-1 inside R-A1)

## Session order of play

1. §0 prep (SSO → backend no-reload → alembic → FE → token) → R-F7 (idle restart) as the smoke.
2. R-F1 anchor clean run → then R-A1/A2/A3 (crash the next od_prototype) → R-A7 ladder.
3. R-C1..C3 + C8 (gate/clarify restarts) → C4/C5/C6/C7 across gated runs.
4. R-B1/B2/B3 (uploads) — can share crash runs with A-group where timing allows.
5. R-D1a/D1b specimens → D2/D3/D4/D5 (the resume endpoint battery).
6. R-E1..E3 (gate-edit reconciliation), R-A4..A6, R-F2..F6, F9/F10 fill-ins.
7. Close: update every row, log bugs (investigation-first), final campaign summary at the bottom of this sheet.
