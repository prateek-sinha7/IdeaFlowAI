---
id: TEST-40
type: test
status: done
area: [sse, resume, workflow, agents, auth, artifacts]
summary: >-
  TS-Y — Resilience & long-run
source: .planning/TEST-REGISTER.md#ts-y-resilience-long-run
covers: [TS-Y-01, TS-Y-02, TS-Y-03, TS-Y-04, TS-V-01, TS-V-02, TS-V-03, TS-V-04, TS-V-05, TS-V-06, TS-V-07, TS-V-08, TS-V-09, BE-CMP-01, BE-ART, TS-O-07, BE-MODEL-01, BE-PARITY-01, BE-CAP-01, BE-GATE-01]
covers_total: 33
---

### TS-Y — Resilience & long-run

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-Y-01 | WS drop & auto-reconnect | kill/restore the WS mid-run | banner `Reconnecting...`; exponential backoff; on reconnect, run resumes via `reconnect_pipeline` (TS-S) | 🔴 |
| TS-Y-02 | Backend restart mid-run | SIGKILL backend mid-wave, restart | durable resume: completed wave skipped, first incomplete wave re-runs; FE reconnect resolves (live SIGKILL mid-wave-2 verified P12) | 🟡 |
| TS-Y-03 | Long build heartbeat | a multi-minute app_builder run | no idle-timeout disconnect (20s pings); `pipeline_heartbeat`/`pong` dropped at transport, never reach handlers | 🔴 |
| TS-Y-04 | JWT mid-run expiry | token expires during a run | 4001 close → `/login`; on re-login the active run is reconnect-discoverable (sessionStorage `active_pipeline_run_id`) | 🔴 |

## 4. Per-workflow end-to-end matrices (what Playwright asserts at each stage)

Each row is one green-path live run. `od_prototype`/`od_ppt` are the alias forms the FE actually sends. Agent counts from `PIPELINE_AGENTS`. Establish the timing SLO from the first 3 green runs.

| Workflow | Entry | Stages / agents (ordered) | Gates | Waves/fanout | Deliverable + mimetype | UI render | Test |
|---|---|---|---|---|---|---|---|
| `user_stories` | IdeaInputPage | clarify → 6 text agents (domain-analyst … backlog-compiler) | none default | no | markdown backlog | `Product Backlog` cards; 0 tool-XML | TS-V-01 |
| `od_prototype` | prototype wizard | specify → plan → build(`task_loop`) → validate | **2 human** (specify, plan) | build loop | HTML prototype (`text/html`) | `Spec Kit Pipeline` → `Prototype Preview` iframe (`allow-scripts allow-same-origin`, blobUrl) | TS-V-02 |
| `od_ppt` | ppt wizard | brief-analyst → composer → validator | none default | no | HTML deck (`text/html`) | `Slide Deck Preview` iframe (`allow-scripts allow-same-origin`); ROI revise | TS-V-03 |
| `app_builder` | IdeaInputPage | 15 agents (material-analyzer … devops, sdlc-governance) | none default | possible | code bundle (`application/zip`) | IDE file tree, Download ZIP; `/api/v1` + `getDatabase` contracts | TS-V-04 |
| `custom` (`ui_custom_proto`) | IdeaInputPage (compose) | factfind → 3-worker `fanout_batch` → plan → build(`task_loop`) → validate | **human-on-conflict + human plan** | **3 workers** | custom HTML (`text/html`) | wave panel (3 workers) → **generic `Deliverable Preview` iframe `allow-scripts`** | TS-V-05 |
| `sample_fanout` | admit | factfind → fanout → merge | none | 3 workers + `copy_disjoint` | serialized bundle | wave panel + bundle | TS-V-06 |
| `sample_wave` | admit | json_tasks → wave_scheduler | none | multi-wave | per-wave merge | wave groups (fold above fold) | TS-V-07 |
| `mulesoft_to_springboot` | migration tile | inventory → decompose → AWS landing → harness (13) | varies | possible | migration artifacts | needs source-repo inputs | TS-V-08 |
| `dotnet_to_azure` | migration tile | inventory → map → modernise → AI-augment (13) | varies | possible | migration artifacts | needs source-repo inputs | TS-V-09 |
| `*_revision` (all) | revise affordance | real revision agents, `planner: skip` | none (no clarify) | no | revised artifact + `derived_from` | content preserved until new output | TS-U-* |

---

## 5. Coverage matrix — every IMPLEMENTATION-REGISTER capability has a test

| Architectural capability (register) | Backend test | UI test | Gap? |
|---|---|---|---|
| Manifest → ExecutionPlan compiler (no-DSL, unknown-cap reject, trust) | BE-CMP-01..10 | TS-D (composer sends pipeline_type+agent_ids) | — |
| Typed artifacts + persistence + `owner_id`/`workspace_id` | BE-ART/PERS/AUTHZ-01..02 | TS-O-07 (files/lineage), TS-T (history) | — |
| Model policy / catalog / `model_overrides` gate | BE-MODEL-01..06 | TS-E, TS-W | — |
| **SC-001 prototype-as-manifest (the core value)** | BE-PARITY-01..06 | **TS-V-05** (custom workflow, zero engine edits) | — |
| Capability registry (63) + ports/adapters + import-linter | BE-CAP-01..05 | (indirect: every workflow runs off registered caps) | — |
| Security gates (human/validation/approval/security) + tool perms | BE-GATE-01..05 | TS-N (HITL), TS-J (validation) | — |
| Workspace / RuntimeEnvironment (ECS seam) + safe exec | BE-RT/EXEC-01..02 | (no direct UI; exec ungranted on product workflows) | exec UI N/A by design |
| Engine fan-out / merge + conflicts | BE-FAN-01..03 | **TS-K** (wave/worker tree), TS-V-05/06 | — |
| Wave scheduler + durable resume | BE-WAVE-01..02, BE-RES-01..02 | **TS-K**, TS-S, TS-Y-02 | — |
| Live verification gap closure (gate streaming, failed/degraded, template guard) | part 13 BE tests | TS-N-01, TS-Q-02, TS-V | — |
| Run-revision real loop (F2) | part 14 BE tests | **TS-U-01..08** | — |
| Prompt-contract closure (od_ppt deck, /api/v1, getDatabase) | part 15/19 `test_prompt_contracts.py` | TS-O-04, TS-V-04 | ISS-004 sdlc-governance live-deferred |
| Terminal-state integrity + reconnect frame contract | part 16 BE tests | **TS-Q, TS-R, TS-S** | — |
| Test-infra & verification gap closure | part 17 (test fixes) | (meta) | ISS-022/025/026 KNOWN-FAIL |
| Custom-workflow UX completeness (composer del., wave fold, custom HTML, model picker) | part 18 | TS-K-01, TS-P-01, TS-E, TS-D | — |
| Prompt & deliverable adherence (api_prefix validator, mimetype resolution) | part 19, BE-CAP-05 (api_prefix) | TS-O-04, TS-P, TS-V-04 | — |
| WS transport (subprotocol, ping, backoff, 4001) | useWebSocket | TS-A-03/04, TS-X-01/02, TS-Y | — |
| Deliverable mimetype dispatch + iframe security | `deriveDeliverableMimetype.test` | **TS-P (security)** | — |

**Result:** every register capability maps to ≥1 test. The only *coverage gaps* are: (a) **ISS-004** (`app-sdlc-governance` anti-tool-XML) never reached its live window — offline-pinned only; (b) **migration with real source repos** (TS-V-08/09) live-confirmed once on 06-12, not repeatably; (c) exec has no UI surface (by design — not granted on product workflows).

---

## 6. Verification status rollup
