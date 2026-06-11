---
phase: 12
slug: wave-scheduler-durable-resume-6
status: secured
threats_open: 0
threats_closed: 32
asvs_level: 1
block_on: high
created: 2026-06-11
---

# SECURITY.md — Phase 12: Wave Scheduler + Durable Resume

**Phase:** 12 — wave-scheduler-durable-resume-6
**Audit disposition:** SECURED — 32/32 threats CLOSED
**ASVS Level:** 1 · **block_on:** high
**Audited:** 2026-06-11 · implementation files read-only (no implementation patched)

The threat register was authored at plan time and is complete (32 IDs across the
7 plan `<threat_model>` blocks). Each threat was verified against code by its declared
disposition (mitigate / accept) — documentation/intent was NOT accepted as evidence; every
`mitigate` was confirmed by a grep match at the correct entry point, and every `accept` was
confirmed to have a documented basis plus (where the disposition claims "inherited") the
inherited mechanism located in code.

---

## Threat Verification (32/32 CLOSED)

| Threat ID | Category | Disposition | Status | Evidence (file:line) |
|-----------|----------|-------------|--------|----------------------|
| T-12-01-IDOR | Information Disclosure | mitigate | CLOSED | `wave_runs` owner_id+workspace_id NOT NULL `alembic/versions/0020_wave_runs.py:38-39` + `app/models/wave_run.py:35-36`; `record_wave_run` stamps helper principal `agents/authz.py:1069-1070`; `update_wave_run`/`read_wave_runs` filter `_scope_owner_ws` `agents/authz.py:1095,1117`. Tests pass: `test_wave_runs.py::test_cross_owner_wave_read_returns_nothing`, `::test_cross_owner_wave_update_is_noop` |
| T-12-01-INPUT | Tampering / DoS | mitigate | CLOSED | Malformed JSON → ValueError `task_parsers/json_tasks.py:78-81`; named unknown depends_on `json_tasks.py:136-139`; `build_waves` cycle `strategies/wave_scheduler.py:104` + unknown-ref `:91-93` raise pre-spawn (zero rows). Tests: `test_json_tasks.py::test_malformed_json_raises_clear_valueerror`, `::test_unknown_depends_on_ref_raises_named_valueerror` |
| T-12-01-DOS | Denial of Service | accept (inherited) | CLOSED | Every wave funnels through the UNMODIFIED `run_fanout`; budget reserve-before-spawn `execution_engine/fanout.py:270-271`, `Semaphore(min(declared, DEFAULT_MAX_CONCURRENCY))` `fanout.py:27,160-169`, workspace aggregate ceiling `kernel_services.py:552-572`. Wave dispatch is the same path `wave_scheduler.py:251` — no new spawn surface |
| T-12-01-TRAVERSAL | Tampering | accept | CLOSED | `targets`/`conflict_keys` are scheduling/merge keys only (`wave_scheduler.py:112`); isolation is engine-decided via `_select_isolation_scope(base_workspace)` `execution_engine/fanout.py:226,325` — never the manifest |
| T-12-01-SC | Tampering (supply-chain) | mitigate | CLOSED | Zero new packages (stdlib build_waves; additive 0020 is a code artifact); `test_banned_patterns.py` green; no dep manifest in any plan's files_modified |
| T-12-02-REPLAY | Tampering | mitigate | CLOSED | Reuse-lookup reads OWNER-SCOPED `store.read_events` `engine.py:3768` (`_find_reused_completion`); `input_hash` = sha256 over sorted upstream content_hashes + resolved input `engine.py:3692-3707` |
| T-12-02-HASH | Spoofing | accept | CLOSED | `content_hash` documented as content-addressing for dedup/lineage, NOT a security control `agents/artifacts/graph.py:22-24`; equality never used as authz |
| T-12-02-DOS | Denial of Service | mitigate | CLOSED | Strictly bounded attempt loop (`attempt += 1`; `raise` on exhaustion/non-transient) `engine.py:3634-3662`; `_retry_sleep` honors backoff `engine.py:162-168`; dormant when no retry declared `engine.py:3610-3614` |
| T-12-02-SC | Tampering (supply-chain) | mitigate | CLOSED | Zero external packages (stdlib hashlib/json/asyncio + existing `_is_transient_throttle`); banned-pattern gate green |
| T-12-03-IDOR | Information Disclosure | mitigate | CLOSED | `reconnect_pipeline` replay reads `ScopedStore(owner_id=user.id).read_events` `app/api/websocket.py:636-642`; `after_seq` int-coerced (non-int rejected) `websocket.py:597-605`; `_scope_owner_ws` on `read_events` `agents/authz.py:325`. Test: `test_ws_reconnect_replay.py::test_cross_owner_reconnect_replays_nothing` |
| T-12-03-DOUBLEDRIVE | Tampering / DoS | mitigate | CLOSED | Classification runs once at startup; resume marker stamped BEFORE driver task — `_stamp_resume_marker(wr)` `engine.py:3003` precedes `create_task(resume_run(...))` `engine.py:3006`; marker is durable+resumable `engine.py:3070-3099` |
| T-12-03-CROSSNODE | Tampering | accept | CLOSED | Cross-process/multi-node locks explicitly OUT of scope (single-node startup-only, N8 v1) — documented `engine.py:3986-3987` |
| T-12-03-RESUMESCOPE | Elevation of Privilege | mitigate | CLOSED | `resume_run` rebuilds the ExecutionContext via the SHARED `_execute_impl` path `engine.py:3972-3975,4069`; owner/workspace read from the durable `workflow_runs` row (`wr.user_id`) `engine.py:4000`; workspace recovered, not re-minted `engine.py:3787-3818` |
| T-12-03-SC | Tampering (supply-chain) | mitigate | CLOSED | Zero external packages (in-process `asyncio.create_task` resume; durable reads via existing ScopedStore); banned-pattern gate green |
| T-12-04-DEDUP | Tampering | mitigate | CLOSED | `shouldApplyEvent` dedupes by event_id `frontend/src/lib/wsReplayState.ts:32-40`, called at the TOP of the handler for ALL event types `dashboard/page.tsx:212`; panel render is pure of deduped state `WaveTreePanel.tsx` |
| T-12-04-IDOR | Information Disclosure | mitigate (backend-enforced) | CLOSED | Client sends only `pipeline_run_id`+`after_seq`; backend replay is owner-scoped (12-03 substrate) `websocket.py:636-642`; cross-owner = ∅ |
| T-12-04-XSS | Tampering | mitigate | CLOSED | Task ids `WaveTreePanel.tsx:110`, agent names `:127`, statuses `:72` rendered as React text children; zero `dangerouslySetInnerHTML` in the wave/dashboard surface |
| T-12-04-SC | Tampering (supply-chain) | mitigate | CLOSED | Zero new FE deps (reuses motion/react + lucide); no package manifest changes |
| T-12-05-TENANT | Information Disclosure | mitigate | CLOSED | workspace_id recovered from a `RunEvent` row ALREADY FILTERED BY `owner_id == user.id` `websocket.py:625-633` (never client payload); replay store carries BOTH owner_id AND recovered workspace_id `websocket.py:636-642` — predicate never dropped. Tests: `test_ws_reconnect_replay.py::test_production_shaped_replay_recovers_workspace_and_returns_rows`, `::test_cross_owner_workspace_recovery_yields_empty_replay` |
| T-12-05-IDOR | Information Disclosure | mitigate | CLOSED | Replay stays owner-scoped (ScopedStore owner_id = user.id) `websocket.py:636-642`; `after_seq` int-coerced `:597-605`; cross-owner run → ∅ |
| T-12-05-SEQ | Tampering | mitigate | CLOSED | Resume seq counter seeded from the durable tail under the SAME owner+workspace scope (`_recover_workspace_id` → `ScopedStore` → `read_events`; `start = max(seq)+1`) `engine.py:4049-4067` — server-computed, no client influence; no schema/unique-constraint change |
| T-12-05-DOS | Denial of Service | accept | CLOSED | One bounded `read_events(after_seq=0)` per resumed run at startup over the server's own non-terminal run set `engine.py:4054`; documented inherited from existing startup classification |
| T-12-05-SC | Tampering (supply-chain) | mitigate | CLOSED | Zero new packages (stdlib itertools + existing ScopedStore/RunEvent ORM); banned-pattern gate green |
| T-12-06-INPUT | Tampering | mitigate | CLOSED | Duplicate ids → named ValueError in parser (primary) `json_tasks.py:125-129` + WaveBuildError in build_waves (defense-in-depth) `wave_scheduler.py:84-85`, both pre-spawn. Test: `test_json_tasks.py::test_duplicate_task_id_raises_named_valueerror` |
| T-12-06-DATALOSS | Tampering / Repudiation | mitigate | CLOSED | In-flight wave re-run WHOLE on resume — no prefix skip; only TERMINAL-completed waves skipped wholesale `wave_scheduler.py:201-206,219-222`; first incomplete wave re-fans every task `:222-275`. Per-task skip deferred (CR-03-followup, CONTEXT.md), not silently lost |
| T-12-06-CROSSSTEP | Information Disclosure | mitigate | CLOSED | Completed-wave-index read step-filtered `r.step == step_id` `wave_scheduler.py:203-206`; read owner+workspace-scoped via `ctx.runner` (import-pure, no direct store import) `kernel_services.py:515-532` |
| T-12-06-EVENT | Information Disclosure | accept | CLOSED | wave_index+step are non-sensitive scheduling ordinals stamped at the strategy re-yield boundary `wave_scheduler.py:262-266`, riding the existing owner-scoped run stream; no new cross-tenant data |
| T-12-06-SC | Tampering (supply-chain) | mitigate | CLOSED | Zero new packages; strategy import-pure (reads via ctx.runner, never the store) — confirmed by `grep -E "from agents.execution_engine\|from app\." = 0` on both modules; `lint-imports` → 4 kept / 0 broken |
| T-12-07-DEDUP | Tampering | mitigate | CLOSED | event_id dedup hoisted to the TOP of the handler for ALL event types via `shouldApplyEvent` `dashboard/page.tsx:200-214` + `wsReplayState.ts:32-40`; event_id originates server-side (Phase 5 sink) |
| T-12-07-STALE | Information Disclosure | mitigate | CLOSED | `resetReplayState` clears seen-set / lastSeq / waveGroups on a new run (`pipeline_start`) `dashboard/page.tsx:336-345` + `wsReplayState.ts:60-64` — no cross-run UI bleed |
| T-12-07-XSS | Information Disclosure | accept | CLOSED | Statuses/ids/agent names rendered as React text (auto-escaped); no `dangerouslySetInnerHTML`; values are server-emitted ordinals/ids on the owner-scoped stream `WaveTreePanel.tsx:72,110,127` |
| T-12-07-SC | Tampering (supply-chain) | mitigate | CLOSED | Zero new FE deps (reuses motion/react + lucide + existing vitest harness); no package manifest changes |

---

## Unregistered Flags

None. The 5 SUMMARY.md `## Threat Flags` sections that exist (12-01, 12-02, 12-03, 12-05, 12-06)
each declare "None — covered by the plan's threat model" and every new surface they name maps to an
existing registered threat ID. Summaries 12-04 and 12-07 carry no `## Threat Flags` section (their
FE surface is covered by T-12-04-* / T-12-07-*). No new attack surface appeared during implementation
without a threat mapping.

---

## Accepted Risks Log

The following threats are dispositioned `accept` in the plan-time register and are accepted for this
phase. Each has a documented basis verified in code:

- **T-12-01-DOS** (accept, inherited) — per-wave fan-out inherits the Phase-11 budget
  reserve-before-spawn + concurrency cap + workspace aggregate ceiling; no new spawn path.
- **T-12-01-TRAVERSAL** (accept) — `targets`/`conflict_keys` are scheduling keys, not filesystem
  paths; isolation is engine-decided, never manifest-driven.
- **T-12-02-HASH** (accept) — `content_hash`/`input_hash` are dedup/idempotency only, never an authz
  control (documented `graph.py:22-24`).
- **T-12-03-CROSSNODE** (accept) — cross-process/multi-node resume locks explicitly out of scope
  (single-node startup-only, N8 v1).
- **T-12-05-DOS** (accept) — one bounded startup `read_events` per resumed run over the server's own
  non-terminal run set (not client-driven).
- **T-12-06-EVENT** (accept) — wave_index/step are non-sensitive ordinals on the existing
  owner-scoped stream; no new cross-tenant data.
- **T-12-07-XSS** (accept) — server-emitted ids/ordinals rendered as auto-escaped React text; no raw
  HTML injection surface.

---

## Verification Notes

- Implementation files were read-only; no implementation was patched during this audit.
- Security mitigation tests run green (8 IDOR/tenant/input tests + banned-pattern + migration-ledger
  + 0020 reversibility/free-String-status).
- `lint-imports` → 4 contracts kept / 0 broken (capability import purity, T-12-06-SC).
- SC-001 holds: 0 references to `sample_wave` inside `backend/agents/execution_engine/` (zero engine edits).
- The two gap-closure mitigations flagged in the audit brief were independently confirmed in code:
  - **T-12-05-TENANT (CR-02)** — workspace_id recovered from an owner-filtered `RunEvent` row, never
    from client input; workspace predicate always re-applied (`websocket.py:625-642`).
  - **T-12-06-DATALOSS (CR-03)** — in-flight wave re-run whole on resume; only terminal-completed
    waves skipped (`wave_scheduler.py:201-275`).
