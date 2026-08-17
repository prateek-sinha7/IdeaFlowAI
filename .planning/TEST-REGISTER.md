# TEST-REGISTER.md — Flowin Production-Readiness QA Register

**Project:** Workflow Engine Decoupling & Universal Workflow Runtime
**Branch:** `feature/003-workflow-engine-decoupling` · **Milestone:** v1.0 (`verifying`) · **Phases covered:** 0A → 19
**Authored:** 2026-06-13 · **Source of truth:** `.planning/IMPLEMENTATION-REGISTER.md` (+ `_register-parts/00..19`), the live frontend under `frontend/src/`, and `.planning/live-verification/CAMPAIGN-2026-06-13-phases16-19.md`.

---

## 0. Purpose, scope & how to use this register

This is the **single QA reference** for taking Flowin to production. It enumerates **every testable behavior** the architecture ships (backend kernel guarantees + frontend user-observable behavior), maps each to a **concrete verification method**, and records **current status** (verified / not verified). **Playwright is the eyes** — the mandate is that every user-observable behavior is exercised and visually asserted by Playwright; humans do not hand-test.

**Two test layers:**
- **BE — Backend (pytest / API / WS-contract):** kernel guarantees that have no UI surface (compiler, persistence, model resolver, capability registry, gates, exec, fan-out, waves, parity). Run with `python3.11` from `backend/`.
- **UI — End-to-end (Playwright):** everything a user sees or does — workflow selection, composing agents, model selection, triggering, live agent panels, waves, gates, deliverables, terminal states, cancel/reconnect, revisions, history. **Driven through a real browser against the live backend on real Bedrock.**

**How to read a test case:** every UI case gives **Precondition → Steps (Playwright actions) → Expected (exact visible strings / badges / iframe attrs / timing) → Selector → Status**. Strings in `monospace` are the *exact* on-screen text to assert (the app ships almost **no `data-testid`** — see §1.5 — so selectors are text/role/title-based).

### 0.1 Status legend

| Badge | Meaning |
|---|---|
| ✅ **LIVE** | Confirmed on real Bedrock **and** visually (Playwright/screenshot) in a live campaign (2026-06-12 / 2026-06-13). Behavior proven to work once; still needs a **committed, repeatable** Playwright test (none exists yet — §1.5/§7). |
| 🟡 **LIVE-MECH** | Live mechanism fired on the wire; the specific value/edge is offline-backed. |
| 🟢 **OFFLINE** | Green in pytest / contract / characterization snapshot. Backend-trustworthy; UI binding still to automate. |
| 🟠 **OFFLINE-ONLY** | Proven offline (fault-injection / prompt-pin); live re-confirm explicitly deferred. |
| 🔴 **TO-BUILD** | No test exists yet. The case below is the spec to automate — **author it in Playwright**. |
| ⚪ **KNOWN-FAIL** | Pre-existing baseline failure (logged ISS-022/025/026). Not a regression; do **not** block on it. |

> **Status update (2026-06-14):** the committed Playwright suite now **EXISTS** at `frontend/e2e/` (§7-G1 DONE) — **123 mocked tests pass, 0 fail**, 15 intentional `fixme`s, + 7 live tests (4 real drivers) that collect. It covers all 25 suites below (TS-A…TS-Y) via a browser-level mock-WS + mock-API harness (no backend needed for the mocked layer), plus a real-Bedrock `*.live.spec.ts` layer. Run with `cd frontend && npm run e2e`. See `frontend/e2e/README.md`. The 🔴 **TO-BUILD** badges in §3 are now **automated** (the few un-mockable rows are `fixme` with documented reasons — drag-reorder, revision lineage/terminal-fidelity, wizard-path live drivers; see the README). The remaining work to "continuously gated" is wiring `npm run e2e` into CI (§7-G4) and adding `data-testid`s (§7-G3).

---

## 1. Test environment, prerequisites & setup

### 1.1 Run the stack

```bash
# BACKEND — python3.11, NO venv, port 8000, NO --reload
# --timeout-graceful-shutdown is REQUIRED (ISS-088): a live SSE stream keeps
# uvicorn waiting forever on SIGTERM, so without it the server survives Ctrl-C
# and `kill` (only kill -9 ends it) and its shutdown code never runs.
cd backend
RUNS_ROOT=/tmp/flowin-runs AWS_PROFILE=default AWS_REGION=eu-central-1 \
  python3.11 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    --timeout-graceful-shutdown 5
#   API   http://localhost:8000      WS  ws://localhost:8000/ws/chat      health GET /health
#   one-time dep if missing:  python3.11 -m pip install --user python-frontmatter
#   DB init (sqlite dev):     python3.11 backend/init_db.py   (alembic upgrade head)

# FRONTEND — next dev, port 3000
cd frontend && npm run dev
#   env: NEXT_PUBLIC_API_URL=http://localhost:8000  NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws/chat
```

### 1.2 AWS / Bedrock (live runs)

- **Profile `default`** = acct **473293451041**, region **eu-central-1**, model **Haiku 4.5** (`eu.anthropic.claude-haiku-4-5-20251001-v1:0`) — **working** (use for all live runs). Set `AWS_PROFILE`/`AWS_REGION` before launching uvicorn; restart the backend after any code change (`--reload` reloads source, but a stale long-lived process will not).
- **Profile `hexaware-srini`** = acct 731451715500 — returns `ValidationException: Operation not allowed` on every Bedrock call. **Use it as the deliberate fault-injector** for the model-error path (TS-Q / ISS-016).

### 1.3 Auth & seed user — **PREREQUISITE GAP**

- JWT lives in `localStorage["auth_token"]`. Login: `POST /api/auth/login {email,password}` → `{token,user:{id,email,tier,is_admin}}` (24h). `GET /api/auth/me` returns the user. WS auth = subprotocol `["bearer.<jwt>","flowin.v1"]` (transitional `?token=<jwt>` still accepted; close code **4001** = expired → redirect `/login`).
- ⚠️ **Self-registration is 403-disabled** (`POST /api/auth/register` → 403). Users are **admin-only** via `POST /api/admin/users` (needs an existing admin JWT). **There is no seed script.** → **Playwright login needs an out-of-band pre-seeded user** (direct DB insert with `app.core.security.hash_password`, or a manually-bootstrapped admin who creates the test users). **Create at least 3 fixtures: a `basic`, a `pro`, and an `enterprise` user** (tier drives workflow entitlement — §3 TS-B).

### 1.4 Workflow & capability fixtures

- 18 committed workflow dirs under `backend/agents/workflows/<id>/workflow.yaml`; AGENT.md bodies live separately under `backend/agents/prompts/<agent-id>/AGENT.md`. `od_prototype`/`od_ppt` are **lookup aliases** (no own dir).
- **SC-001 / custom-pipeline fixtures:** committed CI fixture `backend/tests/agents/fixtures/sc001_task_loop/` (the real zero-engine-edit proof). The UI campaign's custom workflow `ui_custom_proto` (5 agents: factfind → 3-worker `fanout_batch` w/ human-gate-on-conflict → human-gated plan → `task_loop` build w/ `html_static`+`html_render` validators → validate) is preserved at `.planning/live-verification/ui_custom_proto-fixture/` and must be admitted via a custom launcher (it is intentionally **not** in the product tree).

### 1.5 Selector strategy — **the app ships almost no `data-testid`**

Every `data-testid` in the repo is inside Vitest mocks / `src/data/skills.ts`, **not** in production components. Playwright must anchor on **exact visible text**, **`getByRole`**, **`iframe[title=…]`**, **`button[title=…]`**, and the few `aria-label`s (`Close preview`, `Manage skill`). The §3 cases give the exact handle per element. **Recommended (see §7-G3):** before/while authoring, add `data-testid` to the load-bearing nodes flagged in §7 (Stop button, agent-card status badges, the failure-affordance root, the generic iframe, history rows + status badges, reconnect banners). Text selectors work today but are brittle to copy changes.

### 1.6 Commands cheat-sheet (backend + FE unit gates)

```bash
# ── BACKEND offline suite (full pytest HANGS offline — Postgres/Bedrock/Chromium-gated; use these) ──
cd backend
# 5 characterization goldens (byte + event parity)
python3.11 -m pytest tests/agents/test_characterization_{prototype,od_prototype,prototype_revision,od_ppt,app_builder}.py -q
# Targeted offline parity+gate suite (~35s) = CI backend:characterization
python3.11 -m pytest tests/agents/test_characterization_{prototype,od_prototype,prototype_revision,od_ppt,app_builder}.py \
  tests/agents/test_migration_ledger.py tests/agents/test_banned_patterns.py -q     # 44 passed, 7 skipped
# SC-001 zero-engine-edit proofs
python3.11 -m pytest tests/agents/test_sc001_nonprototype_task_loop.py tests/agents/test_sc001_fanout.py -q
# HITL / review-gate seam — OFFLINE-safe despite the *_live* filenames (ISS-074, ~40s)
python3.11 -m pytest tests/agents/test_live_harness.py tests/agents/test_phase8_live.py -q  # 34 passed, 16 skipped
# Gate-stub signature-drift guard (ISS-074) — <1s, catches the next _run_review_gate param
python3.11 -m pytest tests/agents/test_gate_stub_signature_drift.py -q
# Hexagonal boundary (4 contracts kept / 0 broken)
lint-imports          # binary: /opt/homebrew/bin/lint-imports — MUST be run from backend/;
                      # elsewhere it prints "Could not read any configuration" and reads as a false pass
# Avoid offline: -m requires_api_key, tests/integration (Postgres)
# NOT a reason to skip: the *_live* filename. It is not a gate — test_live_harness.py has no
# module skip, and test_phase8_live.py gates only TestLiveHITL/TestLivePipelines, leaving
# TestOfflineHITL ungated. Excluding those two files by NAME is what hid ISS-074 for 43 days:
# five offline reds, from 2026-06-30 to 2026-08-12, that no sweep ever ran. Check the actual
# skip marks (`-m requires_api_key`, `@requires_live`), never the filename.

# ── FRONTEND unit (vitest — NOT in CI; 102 pass / 7 known-fail baseline) ──
cd frontend && npm test
npx tsc --noEmit          # CI frontend:typecheck      npm run lint   # CI frontend:lint
```

---

## 2. Backend test suites (pytest / API / WS-contract)

These are the kernel guarantees from the IMPLEMENTATION-REGISTER. Most are **backend-only** (no UI). They are the trust floor under every UI test in §3. **All rows below are 🟢 OFFLINE-green + characterization-locked unless noted**; re-run the §1.6 suite before any release. Deep rationale per row lives in the cited `_register-parts/` file.

### 2.1 Manifest → ExecutionPlan compiler  (register part 04)

| ID | Guarantee (assert) | Verify | Status |
|---|---|---|---|
| BE-CMP-01 | `workflow.yaml` parses via `yaml.safe_load` only into a typed `WorkflowManifest`; 5 required fields present | `pytest tests/agents/test_manifest.py` (15) | 🟢 |
| BE-CMP-02 | Malformed manifest → `ManifestValidationError` **naming the field** | `pytest tests/agents/test_manifest.py -k missing` | 🟢 |
| BE-CMP-03 | **No-DSL (INV-5):** any key outside the allow-list at **every** nesting level (top/step/task_source/fanout/tools) → rejected; no `when:`/`if:`/`for:`/`${}` | `pytest tests/agents/test_compiler.py -k "dsl or strict or unknown"` (13) | 🟢 |
| BE-CMP-04 | Unknown capability ref (`strategy`/`gate`/`validator`/`deliverable`/`post_step`/…) → `CompilerError` **naming `(kind,name)`** | `pytest tests/agents/test_compiler.py -k unknown` | 🟢 |
| BE-CMP-05 | **Thin compiler (INV-1):** no `if pipeline_type ==` / `spec.id ==`, no `eval`/`exec` of manifest values | `pytest tests/agents/test_banned_patterns.py`; `grep -nE "if pipeline_type|spec.id ==|eval\(|exec\(" agents/workflows/compiler.py` → 0 | 🟢 CI-gated |
| BE-CMP-06 | Step DAG topo-validated: dup `agent` / `depends_on` cycle → `CompilerError`; empty `steps:[]` valid | `pytest tests/agents/test_compiler.py -k "dag or cycle or duplicate"` | 🟢 |
| BE-CMP-07 | **Trust-conditional compile (CAP-03):** `user`/`db` manifests reject not-`user_allowed` caps + privileged grants (`exec`/`network`/`secrets`/`spawn_subagents`) + ceiling-raising Limits | `pytest tests/agents/test_compiler.py -k "trust or user_allowed or privileged"` | 🟢 |
| BE-CMP-08 | All 18 in-repo manifests compile; `planner: run` + `clarify.defaults` verbatim (INV-3 parity traps) | `pytest tests/agents/test_manifest_coverage.py test_manifest_parity.py` (16+26) | 🟢 char-locked |
| BE-CMP-09 | `GET /api/workflows` lists manifest-derived workflows; `GET /api/workflows/{id}` → compiled config, unknown → 404 | `pytest tests/unit/test_workflows_api.py` (7); API calls | 🟢 |
| BE-CMP-10 | Run-history under `/api/runs/*` with IDOR owner-filter (cross-owner → 404) | `pytest tests/unit/test_runs_api.py` (11) | 🟢 |

### 2.2 Typed artifacts, persistence & ownership  (register part 05)

| ID | Guarantee | Verify | Status |
|---|---|---|---|
| BE-ART-01 | Typed sha256-content-addressed `ArtifactGraph`/`ArtifactRef`; typed `consumes` routing; lineage walk | `pytest tests/agents/test_artifact_graph.py` (7) | 🟢 |
| BE-ART-02 | **`accumulated_outputs` mirror DELETED (INV-12);** `ctx.artifacts` sole prior-output source | `pytest tests/agents/test_migration_ledger.py`; `grep -rn accumulated_outputs backend --include=*.py \| grep -v test` → 0 | 🟢 CI-gated |
| BE-PERS-01 | Migration `0014` additive + reversible; cold `0001→0020` chain; **single head `0020`** | `pytest tests/unit/test_migration_0014.py`; `alembic upgrade head` | 🟢 |
| BE-AUTHZ-01 | **Every new table carries `owner_id` + `workspace_id` NOT NULL** (11 tables: artifact_refs, workspaces, run_events, run_capabilities, validation_results, gate_events, hook_runs, repositories, exec_runs, subagent_runs, wave_runs) | `grep -nE 'create_table\|owner_id\|workspace_id' alembic/versions/00{14,16,17,18,19,20}_*.py` — both NOT NULL on every table | 🟢 (confirmed all 11) |
| BE-AUTHZ-02 | Default-deny `ScopedStore` is the single read/write path; cross-owner read denied; `assert_owns` raises `PermissionError` (never swallowed) | `pytest tests/agents/test_parent_run_ownership.py` (13) | 🟢 |
| BE-PERS-02 | Durable `run_events` with **contiguous `seq`** (deltas==1) + unique `event_id`; both stripped from parity multiset | `pytest tests/unit/test_run_events.py` (6); `assert_seq_contiguous` | 🟢 char-locked |
| BE-API-04/05 | `GET /api/runs/{id}/artifacts` (owner-scoped lineage tree, content opt-in); `GET /api/runs/{id}/events?after=<seq>` (seq>after asc, non-int → 422) | `pytest tests/unit/test_runs_api_artifacts.py test_runs_api_events.py` (5+7) | 🟢 |
| BE-SEC | 19/19 threats closed (ASVS L1); revision-run `run_events` NOT NULL on real DB (round-2 CR-01) | `pytest tests/.../test_revision_run_events_persist_and_resolve_on_real_db` | 🟢 |

### 2.3 Model policy / catalog / overrides  (register part 06)

| ID | Guarantee | Verify | Status |
|---|---|---|---|
| BE-MODEL-01 | `ModelCatalog` is the **single** model-id source (5 frozen entries: Haiku 4.5, Sonnet 4.5/4.6, Opus 4.5/4.6); literals live only here | `pytest tests/agents/test_model_catalog.py` (9) | 🟢 |
| BE-MODEL-02 | 5-tier precedence: override > step.model > AGENT.md > workflow.model > session/global Haiku; tier-5 default = INV-3 anchor | `pytest tests/unit/test_model_resolver.py` (25) | 🟢 |
| BE-MODEL-03 | Tier-descent fallback chains from `cost_class`; transient-throttle classifier → bounded engine rebuild-retry + `agent_model_fallback` event (never `with_fallbacks`) | `pytest tests/agents/test_model_fallback.py` (4); `grep with_fallbacks` → 0 | 🟢 |
| BE-MODEL-04 | **`_validate_model_overrides` ingress gate:** per-run `{agent_id→model_id}` checked vs `ModelCatalog.ids()` AND `run_agent_ids`; malformed/bogus rejected **before** `WorkflowRun` created → `code:"invalid_model_override"` | `pytest tests/unit/test_run_pipeline_validation.py` (50); WS msg with bogus id → error frame | 🟢 |
| BE-MODEL-05 | `GET /api/capabilities` (JWT) → `{capabilities:[…user_allowed…], model_catalog:[…]}`; 401 unauth | `pytest tests/unit/test_capabilities_api.py` (8) | 🟢 → drives UI TS-E |
| BE-MODEL-06 | No-override run = byte/semantic-identical (every tier `None` today) | 5 goldens unchanged | 🟢 char-locked |

### 2.4 SC-001 — prototype-as-manifest parity proof (THE CORE VALUE)  (register part 07)

| ID | Guarantee | Verify | Status |
|---|---|---|---|
| BE-PARITY-01 | **A brand-new non-prototype `task_loop` workflow runs from manifest + AGENT.md, ZERO engine edits** (git-containment check: no proof artifact under `execution_engine/`; manifest uses only registered caps) | `pytest tests/agents/test_sc001_nonprototype_task_loop.py` (3) | 🟢 **PROVEN** |
| BE-PARITY-02 | Same proven for fan-out (`sample_fanout`) | `pytest tests/agents/test_sc001_fanout.py` (3) | 🟢 |
| BE-PARITY-03 | **5 goldens byte-identical** (prototype/prototype_revision/od_prototype/od_ppt/app_builder) — deliverable bytes == committed golden | `pytest tests/agents/test_characterization_*.py -k byte_snapshot` (5) | 🟢 char-locked |
| BE-PARITY-04 | **5 goldens semantic-event-parity** — normalized event stream == golden; fails on dropped/reordered event or lost key | `…-k event_snapshot` (5) | 🟢 char-locked |
| BE-PARITY-05 | Kernel knows no workflow by name (INV-1): banned-pattern grep == 0, CI hard-fail; `agents/prototype/` package DELETED | `pytest tests/agents/test_banned_patterns.py` (11); `ls agents/prototype` → absent | 🟢 CI-gated |
| BE-PARITY-06 | 9 capability families live behind ports off the compiled manifest (strategies/resolvers/providers/parser/compaction) | `pytest tests/agents/test_routing_parity.py test_strategies.py` | 🟢 |

### 2.5 Capability registry & ports/adapters  (register part 08) — **63 registered capabilities**

| ID | Guarantee | Verify | Status |
|---|---|---|---|
| BE-CAP-01 | `@register` binds `(kind,name)→instance` into `_IMPLS`, adds to `_KNOWN`, records `user_allowed`; **two surfaces** — `_KNOWN` literal (compiler, impl-free at compiler import) vs runtime `discover()` | `pytest tests/agents/test_registry_capabilities.py` | 🟢 |
| BE-CAP-02 | **Registry drift guard: `len(_KNOWN)==63`** and `==_EXPECTED_NAMES`; `resolve()` static-dict (no `getattr`/`eval`/`importlib`); unknown → `KeyError`, known-unbound → `RuntimeError` | `pytest …test_registry_capabilities.py` (asserts 63) | 🟢 |
| BE-CAP-03 | **Add a capability = add module + `@register` + `discover()` + bump `_KNOWN` — no kernel edit** (the architecture promise) | new-capability test fixture compiles + resolves | 🟢 |
| BE-CAP-04 | **Import-linter 4 contracts kept / 0 broken** (engine ↛ app.api; workflows/capabilities/runtime ↛ {execution_engine, app}) | `lint-imports` | 🟢 |
| BE-CAP-05 | Capability inventory by kind exists & resolvable: `strategy`(single_shot/task_loop/fanout_batch/wave_scheduler), `merge`(copy_disjoint/git_3way/json/html_fragment), `validator`(html_static/html_render/design_quality/spec_plan_coverage/task_done_when/code_compile/code_test/code_lint/api_prefix), `deliverable`(single_file/serialized_sandbox/streamed_text/ppt/repo_diff), `context_provider`(opendesign/previous_run/repo), `task_parser`(heading_tasks/json_tasks), `gate`(human/validation/approval/security), `tool`(workspace/prototype/prototype_emit_only/planning/spawn_subagents), `post_step`(revision_validation/api_prefix_audit), `compaction`(html_skeleton), `runtime`(langchain_deepagents), `prompt`(default), `skill`(ui/disk/template/repo), `hook`(behavioral/secret_scan/otel_tracing), `runtime_env`(local), `mcp_server`/`integration_provider`(github/gitlab/jira/slack/…) | `pytest tests/agents/test_registry_capabilities.py` membership + per-impl tests | 🟢 |

### 2.6 Security gates & tool permissions  (register part 08/10)

| ID | Guarantee | Verify | Status |
|---|---|---|---|
| BE-GATE-01 | `exec`/`network`/`secrets`/`spawn_subagents` default **OFF**; `intersect_permissions` AND-mask can only LOWER | `pytest tests/agents/test_tool_permissions.py` | 🟢 |
| BE-GATE-02 | exec needs `gates:[security,approval]` or compile-error (D-01); `security` gate network/secrets **BLOCK** (byte-identical deny); exec PASS only behind security+approval+workspace allow-list | `pytest tests/agents/test_gates.py test_compiler_trust.py` | 🟢 |
| BE-GATE-03 | `human`/`approval` gates delegate to the **one** durable HITL → `review_gate_*` events byte-identical; first-exec approval memory run-scoped & durable | `pytest tests/agents/test_gates.py test_declared_gate_streaming.py` | 🟢 → drives UI TS-N |
| BE-GATE-04 | `validation` gate: CRITICAL→`block`+`gate_blocked`, residual→`validation_warning`+pass | `pytest tests/agents/test_gates.py` | 🟢 → drives UI TS-J/TS-N |
| BE-GATE-05 | INV-13 banned-pattern gate: no 2nd `create_deep_agent`, no local deepagents shadow, deepagents `task` tool excluded | `pytest tests/agents/test_banned_patterns.py` | 🟢 |

### 2.7 Workspace / RuntimeEnvironment + safe local exec  (register parts 09/10)

| ID | Guarantee | Verify | Status |
|---|---|---|---|
| BE-RT-01 | 4 runtime/workspace ports kernel-side interface-only (ECS-swap seam); `LocalSandboxRuntime` provisions a traversal-proof `LocalWorkspace` (`..` escape → `ValueError`); sole git-subprocess owner (hardened clone) | `pytest tests/agents/test_local_runtime.py` (8); `lint-imports` | 🟢 |
| BE-RT-02 | Repo workflow class end-to-end no-exec (`sample_brownfield`), zero `if repo:` engine fork; SC-001 holds | `pytest tests/agents/test_sample_brownfield_workflow.py` (3); `grep "if repo" execution_engine/` → 0 | 🟢 |
| BE-EXEC-01 | Hardened `exec_command`: argv-only (no shell), allow-list python/python3/pytest/ruff (deny beats allow), scrubbed env, rlimits cpu60s/mem512MB + 120s group-kill, 64KB truncation; **deny-default until granted** | `pytest tests/agents/test_local_runtime.py test_exec_runs.py` | 🟢 |
| BE-EXEC-02 | Code validators (compile/test/lint) reach exec only via workspace handle; refuse-before-spawn if exec ungranted (never silent pass); SC-001 proof via `sample_exec_workflow` | `pytest tests/agents/test_code_validators.py` | 🟢 |

### 2.8 Engine fan-out / merge + wave scheduler & durable resume  (register parts 11/12)

| ID | Guarantee | Verify | Status |
|---|---|---|---|
| BE-FAN-01 | Single `run_fanout` spawn path (declarative `fanout_batch` + runtime `spawn_subagents` funnel through it); **engine decides isolation/caps/merge, never the manifest (INV-7)**; reserve-before-spawn budget | `pytest tests/agents/test_fanout.py test_isolation.py test_budget.py` | 🟢 |
| BE-FAN-02 | `copy_disjoint` deterministic (sorted) + overlap→conflict (evicted, never silent overwrite); conflicts first-class (artifact+event+4 policies); parallel ≤ cap 4 | `pytest tests/agents/test_merge.py test_merge_conflict.py` | 🟢 |
| BE-FAN-03 | `subagent_runs` rows (never `workflow_runs`); cancellation tears down every allocation (zero residue); emits `subagent_spawned/result`, `merge_*`, `budget_*` | `pytest tests/agents/test_subagent_runs.py test_fanout_cancel.py` | 🟢 → drives UI TS-K |
| BE-WAVE-01 | `wave_scheduler` topo-sorts `json_tasks` into deterministic parallel waves (Kahn levels, conflict-key split), **one `run_fanout` per wave**, per-wave merge; cycle/dup → `WaveBuildError` pre-spawn | `pytest tests/agents/test_wave_scheduler.py test_json_tasks.py` | 🟢 → drives UI TS-K |
| BE-WAVE-02 | `wave_runs` rows (owner/workspace NOT NULL); emits `wave_started/completed/failed` + `subagent_*` carrying `wave_index`+`step` | `pytest tests/agents/test_wave_runs.py` | 🟢 → drives UI TS-K |
| BE-RES-01 | Per-step retry + content-hash reuse (restart-stable `input_hash`); WS `after_seq` replay (owner-scoped, idempotent by `event_id`); cross-owner reconnect → ∅ + `live:false` | `pytest tests/agents/test_step_retry.py test_ws_reconnect_replay.py` | 🟢 → drives UI TS-S |
| BE-RES-02 | Step-granular auto-resume incl. **mid-wave** (completed wave skipped wholesale, first incomplete wave re-runs in entirety); `workspace_id` recovered from durable owner-scoped row (not re-minted) | `pytest tests/agents/test_restart_resume.py` | 🟢 (live SIGKILL mid-wave-2 + restart ✅ in P12 UAT) |

---
## 3. UI end-to-end test suites (Playwright) — every user-observable behavior

> **Routing reality:** `/` redirects to `/login`. The entire app is `/dashboard` — a **single-page view state machine** (`MainView = home | input | execution | history | library | settings | analytics`), **not** a router. Flow: `home`(CreationHub) → select → `input`(IdeaInputPage) → Run → `execution`(2-panel). `prototype`/`ppt` are the exception — they hard-navigate to `/workflow/{prototype,ppt}/templates` wizards. **Dead/legacy (do NOT test):** `WorkflowView.tsx`, `WorkflowControls.tsx`, `PipelineGraph.tsx`+`AgentNode.tsx` (alt dark surface, unmounted), `WorkflowComposer.tsx`+`CapabilityPalette.tsx` (DELETED — ISS-014), `ValidatorIssuePanel.tsx` (built but unmounted).

### TS-A — Authentication, routing & tier entitlement

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-A-01 | Unauth redirect | GET `/` unauthenticated | 307/redirect to `/login`; `/dashboard` also bounces to `/login` | 🔴 |
| TS-A-02 | Login persists JWT | `POST`-style login via the form (pre-seeded user) | `localStorage["auth_token"]` set; lands on `/dashboard` `home`; `getByText("What would you like to build today?")` visible | 🔴 |
| TS-A-03 | WS connects w/ subprotocol | After login, observe the WS handshake | WS opens with subprotocols `["bearer.<jwt>","flowin.v1"]`; **no token in URL**; server echoes `flowin.v1` | 🔴 |
| TS-A-04 | JWT-expired logout | Force a 4001 close (expired token) | redirect to `/login`; banner/`lastError` `Your session has expired. Please log in again.` | 🔴 |
| TS-A-05 | Tier gating (basic) | Login as **basic** user, view CreationHub | `app_builder`/`migration`/`custom` rows are `disabled`, `opacity-60`, show `Requires Pro plan`/`Requires Enterprise plan`; clicking them does nothing | 🔴 |
| TS-A-06 | Tier gating (enterprise) | Login as **enterprise** user | All 6 rows enabled; `custom`+`migration` clickable; migration row shows `NEW` pill | 🔴 |

### TS-B — Workflow selection (CreationHub)

Vertical **list** of 6 `<button>` rows (not tiles). Header H1 `What would you like to build today?`. Assert each row's exact H2 + routing.

| ID | Row (H2 label, exact) | Click → | Expected | Status |
|---|---|---|---|---|
| TS-B-01 | `Generate product requirements` (`user_stories`) | `input` view | IdeaInputPage with eyebrow `Generate product requirements`, H1 `Provide the brief` | 🔴 |
| TS-B-02 | `Pitch an idea` (`ppt`) | **`/workflow/ppt/templates`** | PPT template wizard loads (not IdeaInputPage) | 🔴 |
| TS-B-03 | `Build an interactive prototype` (`prototype`) | **`/workflow/prototype/templates`** | Prototype template wizard loads | 🔴 |
| TS-B-04 | `Build an end-to-end application` (`app_builder`) | `input` view | H1 `Describe the application` | 🔴 (pro+) |
| TS-B-05 | `Platform workflows` (`migration`, `NEW`) | `input` view | H1 `Modernise a legacy estate`; **two migration tiles** shown; Run disabled until a path is picked | 🔴 (ent) |
| TS-B-06 | `Compose a custom workflow` (`custom`) | `input` view | H1 `Describe the task`; AgentsPopup pulls the 8 `custom` agents (cap 8) | 🔴 (ent) |
| TS-B-07 | Row hover affordance | hover an allowed row | label → navy `#1B2A4A`, arrow translates right; staggered fade-in on mount | 🔴 |

### TS-C — Idea input & pipeline trigger (IdeaInputPage)

| ID | Title | Steps | Expected (exact) | Status |
|---|---|---|---|---|
| TS-C-01 | Placeholder per type | open each entry workflow | textarea placeholder matches type, e.g. user_stories `e.g. Generate epics and stories for a refunds workflow with multi-currency support.`; app_builder `e.g. A SaaS platform for managing freelance invoices with Stripe integration.`; custom `e.g. Research the competitive landscape for AI coding assistants and generate a SWOT analysis.` | 🔴 |
| TS-C-02 | Run button disabled states | empty idea / no agents / migration-no-path | label = `Run workflow` only when valid; else `Add agents first` (no agents) or `Pick a migration path` (migration); `disabled` + `opacity-30` when `!idea.trim()` or `agents==0` | 🔴 |
| TS-C-03 | Run enables on input | type a brief with ≥1 agent | Run button enabled, label `Run workflow`, navy `bg-gray-900` | 🔴 |
| TS-C-04 | Keyboard submit | focus textarea, press `Cmd/Ctrl+Enter` | triggers run (same as clicking Run); plain Enter inserts newline | 🔴 |
| TS-C-05 | Auto-focus | open `input` | textarea focused ~200ms after mount | 🔴 |
| TS-C-06 | Attach file | click `+ Attach file`, pick `spec.pdf` | a chip `spec.pdf` appears; textarea gains `[Attached: spec.pdf]`; **note: only the name is injected, bytes not uploaded** | 🔴 |
| TS-C-07 | Voice (Chromium) | click `Voice` | toggles to `Stop`, red `animate-pulse`, placeholder → `Listening... speak your idea`; (button absent in Firefox — assert absence) | 🔴 |
| TS-C-08 | Migration path select | pick tile `Mulesoft → Spring Boot microservices on AWS` | tile fills navy `bg-[#1B2A4A]` white; all heading/placeholder copy swaps to mulesoft; Run unlocks | 🔴 |
| TS-C-09 | Advanced summary line | observe the `Advanced` button | shows `{n} agents` + (if est) ` · ~{X}s`/`~{Y}m` + (if attached) ` · {k} skill/hook`; clicking opens AgentsPopup | 🔴 |
| TS-C-10 | **Trigger → execution transition** | click `Run workflow` | view **immediately** swaps to `execution` (2-col); a running notification toast (label = first 60 chars); the `run_pipeline` WS frame is sent (see TS-H for payload) | 🔴 |

### TS-D — Agent composer (AgentsPopup)

Modal title `Workflow configuration`, eyebrow `Advanced`. Tabs `Agents ({n})` / `Skills & Hooks`.

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-D-01 | Open/close | click `Advanced`; click backdrop / `X` / `Cancel` / `Save changes` | modal opens; **all four close affordances close it identically** (state is already live; `Save changes` ≡ `Cancel`) | 🔴 |
| TS-D-02 | Roles & locks | inspect agent cards | locked agents show `Core` pill + `Lock` icon (not draggable/removable); required show `Required` (draggable, not removable); optional show `X` `title="Remove agent"` | 🔴 |
| TS-D-03 | Remove optional agent | click a card's `X` | agent removed; `Agents ({n})` count decrements; Add cell shows `+ Add agent ({slotsLeft} left)` | 🔴 |
| TS-D-04 | Drag-reorder | drag an optional card | order changes; dragging card `opacity:0.4`, drop target `scale 1.02`+navy border; locked cards refuse drag | 🔴 |
| TS-D-05 | Add-agent cap | add optional agents to the cap | cap = 8 for `custom`, 5 otherwise; at cap the Add cell reads `Limit reached` | 🔴 |
| TS-D-06 | Agent Library | click `Browse agent library →` | modal `Add agent`; categories `All/User Stories/Presentation/Prototype/App Builder/Mulesoft → Spring Boot/.NET → Azure/Custom`; search `Search agents...`; `+ Add` adds + **closes the library** | 🔴 |
| TS-D-07 | Custom hides anchors | in `custom`, browse library | the `HIDDEN_FROM_CUSTOM` set (ppt-assembler, backlog-compiler, prototype-finalizer, app-sdlc-governance, …) is filtered out | 🔴 |
| TS-D-08 | Capabilities modal | click a card's `title="View capabilities"` | modal shows `What this agent does`, `Pipeline · Step {n}`, `Suggested Skills`, `Suggested Hooks`, and (if `has_skill`) a `Custom skill` inline editor (`Attach skill` disabled until name+content) | 🔴 |

### TS-E — Per-agent model selection (AgentModelPicker) — **the live model-selection surface**

In AgentsPopup → Agents tab footer. Header `Per-Agent Model`. Options are **live from `GET /api/capabilities → model_catalog` (filtered `user_allowed`)** — not hardcoded; the only static option text is `Default`.

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-E-01 | States | open with no agents / unauth / loaded | no agents → `Add agents to assign per-agent models.`; loading → `Loading model catalog…`; no JWT → `Not authenticated.`; loaded → one `<select>` per agent, first option `Default` | 🔴 |
| TS-E-02 | Catalog reflects backend | inspect the `<select>` options | option set == `model_catalog` labels where `user_allowed` (cross-check `GET /api/capabilities`); each `<option value>` == model `id`, text == `label` | 🔴 |
| TS-E-03 | **Pick a non-default model per agent** | for agent A choose e.g. `Sonnet 4.6`; leave agent B `Default` | selection persists in the picker; on Run the `run_pipeline` payload carries `model_overrides:{ "<A.id>":"<sonnet-id>" }` (B omitted) — assert on the WS frame (TS-H) | 🔴 |
| TS-E-04 | Default removes override | re-select `Default` for agent A | that agent's key removed from `model_overrides`; if all Default → field omitted entirely (byte-identical payload) | 🔴 |
| TS-E-05 | Override reflected post-run | run with an override | on `pipeline_complete`, the Token Usage card cost label shows the resolved model short-name (`Est. cost (Sonnet 4.6)`); backend `model_id` matches | 🔴 (live) |
| TS-E-06 | Bogus override rejected | (negative) inject an invalid model id on the wire | backend refuses **before** run starts: `{type:"error", code:"invalid_model_override"}`; no execution view progress | 🟢 (BE-MODEL-04) / 🔴 UI |

### TS-F — Skills & Hooks (AgentsPopup → Skills & Hooks tab)

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-F-01 | Empty states | open the tab | `No skills attached · click "Add skill" to browse`; `No hooks attached · click "Add hook" to browse` | 🔴 |
| TS-F-02 | Attach skill | `Add skill` → search/filter → `Add` | row shows `CheckCircle2 {name}`; button `Add`→`Added` (disabled, Check); count pill increments | 🔴 |
| TS-F-03 | Skill category filter | click category pills | pills `All/Planning/Testing/Workflow/Security/Debugging/Collaboration/Meta` filter the list; `No skills found` when empty | 🔴 |
| TS-F-04 | Attach hook | `Add hook`, attach e.g. `Quality Gate` | 8 hooks available with event pills (`PostToolUse` etc.); event filter pills `All Events/Pre Tool Use/Post Tool Use/On Stop/Session Start/Session End` | 🔴 |
| TS-F-05 | Persisted into payload | attach 1 skill + 1 hook, Run | `run_pipeline` carries `attached_skills:[{id,name,content,source,compatible_agents:[]}]` + `attached_hooks:[{id,name,event,trigger,description}]` (TS-H) | 🔴 |
| TS-F-06 | Survives reopen | attach, close popup, reopen | attachments persist (global `SkillsHooksContext`) | 🔴 |

### TS-G — Review gates pre-run (ReviewGatesSection, on IdeaInputPage)

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-G-01 | Collapsed summary | observe `Review gates` header | `no gates` when none checked; else `{n} agent[s] pause for review`; chevron toggles | 🔴 |
| TS-G-02 | Default gates | open for prototype agents | `prototype-specify` + `prototype-plan` pre-checked (`gate==="Human_Gate"`), each with a `default` pill | 🔴 |
| TS-G-03 | Toggle → payload | check/uncheck an agent, Run | `gate_agent_ids` sent **only when touched**; the ordered checked ids match | 🔴 |
| TS-G-04 | Hidden when no agents | remove all agents | section renders nothing (`agents.length===0`) | 🔴 |

### TS-H — Trigger contract & execution-view transition (what happens when a pipeline fires)

| ID | Title | Steps | Expected (exact wire + visual) | Status |
|---|---|---|---|---|
| TS-H-01 | run_pipeline payload | Run a `user_stories` brief | WS frame `{type:"run_pipeline", pipeline_type:"user_stories", message:"<trimmed>", agent_ids:[…]}`; optional `attached_skills/attached_hooks/gate_agent_ids/model_overrides` present **only** when set; **no override → byte-identical legacy payload** | 🔴 |
| TS-H-02 | Optimistic transition | click Run | `execution` view shows **immediately** (before any server event); `AgentProgressPanel` left (~340–360px), preview right; a `Running` notification appears | 🔴 |
| TS-H-03 | Queue-on-connect | Run while WS not yet `connected` | the start is stashed and fires on the next `connected` transition (no lost run on reconnect/hot-reload) | 🔴 |
| TS-H-04 | pipeline_start seeds cards | observe first server event | `pipeline_start` → agent cards seeded `idle` from the server agent list; `currentAgentIndex=0`; sessionStorage `active_pipeline_run_id` + `active_pipeline_type` set | 🔴 |
| TS-H-05 | Wizard path (prototype/ppt) | run via `/workflow/prototype/templates` | brief+template+design-system staged in sessionStorage; on WS connect a `run_pipeline` with `pipeline_type:"od_prototype"`, `template_id`, `design_system_id` fires | 🔴 |

### TS-I — Live agent panels (AgentProgressPanel) — **per-agent visual states & timing**

Primary live surface (left column, light theme). Status model `idle→thinking/running→done/error`.

| ID | Title | Steps | Expected (exact badge + style + timing) | Status |
|---|---|---|---|---|
| TS-I-01 | RUNNING badge | agent starts | badge `RUNNING` white-on-navy `bg-[#1B2A4A]`; card navy border; **two animations**: pinging white dot (`animate-ping`) + `Loader2 animate-spin`; status line = `agent.thinking` or `In progress...` | ✅ (campaign) |
| TS-I-02 | DONE badge | agent completes | badge `DONE` emerald `text-emerald-700 bg-emerald-50`; optional `{N}s` (0-dec) left of badge; `Click to view output` (if output) / `Completed successfully`; token pill `{X}K tokens` | ✅ |
| TS-I-03 | ERROR badge | agent fails | badge `ERROR` red `text-red-700 bg-red-50`; card red border; red error text = `agent.error` | ✅ (ISS-016 srini) |
| TS-I-04 | Expand output | click a DONE-with-output card | `role="button"` + `aria-expanded` toggles; `<pre>` mono `text-[10px]` `max-h-64` shows `agent.output` | 🔴 |
| TS-I-05 | Header states | through a run | running → `{completed} / {total} agents`; complete → `Done in {X.X}s`; cancelled → `Pipeline stopped`; else `Agent Progress` | ✅ |
| TS-I-06 | Progress bar | through a run | `h-0.5` fill width = completed/total; color navy normal / `bg-red-400` if any error / `bg-gray-300` if cancelled | 🔴 |
| TS-I-07 | Stop button | while running | `Stop` + `Square` icon visible only while `isRunning && !cancelled`; click → see TS-R | ✅ |
| TS-I-08 | Completion footer | on complete | `TokenUsageSummary` (TS-L) + optional `Suggested next steps` chain buttons + `New Pipeline` (`RotateCcw`) | 🔴 |
| TS-I-09 | Cards seed-then-transition | whole run | all cards exist from `pipeline_start` (seeded `idle`), transition **in place** (don't appear/disappear); stagger entry `delay index*0.04` | 🔴 |
| TS-I-10 | Duration format | any completed agent | assert regex `/\d+(\.\d)?s/` (wall-clock, non-deterministic — never assert exact value) | 🔴 |

### TS-J — Live streaming, planner & execution gate (AgentThinkingTab / PreviewPanel "Thinking" tab)

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-J-01 | Empty trace | before a run | `Pipeline Trace` + `Start a pipeline to see real-time agent reasoning, tool calls, and context flow.` | 🔴 |
| TS-J-02 | **Reasoning (live) stream** | agent thinking | header `Reasoning (live)` + last 300 chars of `thinkingText` (mono) + blinking cursor `▌` (`animate-pulse`). **NOTE:** `agent_chunk` output is NOT shown live — only `agent_thinking` drives this | ✅ |
| TS-J-03 | Per-card LIVE/DONE/ERROR | through a run | running → `LIVE` (Zap, navy on `#E8EDF5`); done → `DONE`; error → `ERROR` (red); auto-expand + `scrollIntoView` follows the running card | 🔴 |
| TS-J-04 | Pipeline status banner | running/complete/errors | `Pipeline Running` (navy pulsing dot) / `Pipeline Complete` / `Completed with errors` (red) | 🔴 |
| TS-J-05 | Execution gate badge | after planner | `✓ PROCEED` (navy) or `⚡ CLARIFY` (amber); Deep Planner card title `Deep Planner`, subtitle `Intent: {…}` or `Analyzing brief & planning execution…` | 🔴 |
| TS-J-06 | Spec-Kit live view (prototype) | run a prototype | replaces the trace body: `Spec Kit Pipeline`, 4 PhaseCards `Spec Writer — Specification`/`Task Planner — Build Decomposition`/`Build Agent — Incremental Construction`/`Validation Agent — P0/P1 Checks`; running phase shows `LIVE` + status copy; build shows per-task rows; complete → `Prototype complete — {N}s` | ✅ (S02) |
| TS-J-07 | Planning overlay | planner_start | right panel `Planner is thinking…`, 4 steps rotate every 1800ms | 🔴 |

### TS-K — Wave / Subagent tree (WaveTreePanel) — fan-out & wave visualization

Mounted bottom-left in a **fold-fix container** (`flex-shrink-0 max-h-[40%]`). Heading `Wave / Subagent Tree` (CSS-uppercased). This is the UI for BE-FAN-* / BE-WAVE-*.

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-K-01 | **Fold-above-the-fold (ISS-019)** | open execution at 1440×950 | heading `Wave / Subagent Tree` visible **without page scroll** (heading y≈884, bottom ≤950); page has no overflow (`bodyScrollH==viewportH`) | ✅ (V1: y=884) |
| TS-K-02 | Empty state | no fan-out running | `No waves running.` (exact, trailing period) in a gray pill | ✅ |
| TS-K-03 | Wave groups | run a fan-out/wave workflow (`sample_fanout`/`sample_wave`/custom) | one card per wave `Wave {index}` (`Wave 0`, `Wave 1`…) sorted asc; comma-joined task ids; wave status badge | ✅ (V2/S10: 3 workers) |
| TS-K-04 | Worker leaves | during fan-out | ≥2 distinct worker leaves nested under a wave (`pl-4 border-l`), each `worker.agent` + status badge | ✅ |
| TS-K-05 | Status buckets | through wave lifecycle | badge color by substring: running→blue (`Loader2 spin`), completed→emerald (`CheckCircle2`), **failed/cancel→red** (`XCircle`), else pending→gray; text = raw status | 🔴 |
| TS-K-06 | Populated scroll | many waves | list scrolls within `max-h-[260px]`/`max-h-[40%]`, panel stays in the fold | 🔴 |
| TS-K-07 | Reconnect dedup | reload mid-fanout | replayed `subagent_*`/`wave_*` frames don't duplicate leaves (idempotent by `event_id`) — see TS-S | 🟡 |

### TS-L — Token usage (TokenUsageSummary)

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-L-01 | Summary card | on complete | header `Token Usage` + `{X}K total`; breakdown `{X} input` / `{Y} output`; ratio bar; cost row `Est. cost ({model})` | 🔴 |
| TS-L-02 | Number formats | various totals | `formatTokens`: ≥1M `{n}M`, ≥1000 `{n}K`, else raw; assert regex `/[\d.]+[KM]? total/` | 🔴 |
| TS-L-03 | Cost formats | zero / tiny / normal | `0`→`—`; `<0.001`→`<$0.001`; else `~$X.XXX` | 🔴 |
| TS-L-04 | Per-agent token pill | DONE cards | `{X}K tokens` (mono) when total>0 | 🔴 |

### TS-M — Questionnaire / clarify gate (QuestionnairePanel)

Accordion of MCQ cards (not native radios). Header `Quick Setup`. **No required-answer validation — submit never disabled; defaults filled server-side.**

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-M-01 | Loading | clarify analyzing | `Analyzing your brief…` + `Preparing smart questions to get the best output` | 🔴 |
| TS-M-02 | Render | `questionnaire_ready` arrives | `Quick Setup` + `{label} · {n} questions to personalise your output`; first question auto-expanded; counter `{answered} of {n} answered` | ✅ (S01) |
| TS-M-03 | Select option | click an MCQ option `<button>` | selected fills navy `bg-[#1B2A4A] text-white`; single-select (replaces); **auto-advances to next question after 300ms** | 🔴 |
| TS-M-04 | Hybrid free-text | a `hybrid` question | `Describe your own topic` input (placeholder `e.g. Q3 sales results, climate change impact, AI in healthcare…`); typing clears the MCQ selection | 🔴 |
| TS-M-05 | Submit labels | varying answered count | all answered → `Run {label} Pipeline`; some → `Continue with {a}/{n} answered`; none → `Run with defaults`; secondary `Skip all & run directly` | ✅ |
| TS-M-06 | Submit proceeds | click submit (even 0 answered) | run starts; `questionnaire_complete` clears the panel; unanswered questions omitted from payload | 🔴 |

### TS-N — Mid-run human review gate (ReviewGatePanel) — HITL

Replaces the right panel when an agent with `gate: Human_Gate` completes. This is BE-GATE-03 / Phase 13 F1 made visible.

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-N-01 | **Gate streams BEFORE await (F1)** | run od_prototype | the review modal appears **mid-run, before** you approve (not after); title `Specification Review` (specify) / `Task Plan Review` (plan); subtitle `{agent} · Review before continuing` | ✅ (S02; t=4.9s/25.5s) |
| TS-N-02 | Preview mode | observe spec/tasks | spec → `##`-section cards; tasks → `{N} task[s] · Click ✕ to remove a task before building`, deletable task rows | 🔴 |
| TS-N-03 | Edit mode | toggle `Edit` | textarea (mono) prefilled; amber dot on Edit when dirty; helper `Edit the {specification\|task list} directly. Changes will be used by the next agent.` | 🔴 |
| TS-N-04 | Approve | click approve | label `Approve & continue` (or `Approve with edits & continue` if edited); gate closes; run proceeds to next agent; `review_gate_approved` on wire | ✅ |
| TS-N-05 | Reject cancels | click `Reject & cancel pipeline` | run ends; **maps to `pipeline_cancelled`** (WR-03), no downstream agents | 🔴 |
| TS-N-06 | Empty-content gate | gate with no content | `No content was produced for review.` + `The agent returned an empty result. Reject to cancel the pipeline, or approve to continue anyway.` | 🔴 |
| TS-N-07 | Single prompt per agent | agent with inline + declared gate | pauses **exactly once** (inline suppresses the declared duplicate — WR-02) | 🟡 |

### TS-O — Deliverable preview by workflow type (PreviewPanel dispatch)

Header `Generating...`/`Results`/`Preview` (state-dependent). Tabs `Preview`/`Files`/`Thinking`. `renderType` normalizes revisions/od-aliases; `KNOWN_RENDER_TYPES=[user_stories,ppt,prototype,app_builder]`; **`custom` is deliberately NOT known → generic channel (TS-P).**

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-O-01 | Empty | before content | `Output will appear here` (exact) | ✅ |
| TS-O-02 | User stories | complete a `user_stories` run | `UserStoryPreview`: sticky `Product Backlog`, stats `Epics/Stories/Points/Sprints`, priority pills `{n} Must-have`/`Should-have`/`Nice-to-have`, epic toggles, stories with bolded `Given`/`When`/`Then`, `Copy MD` | 🔴 |
| TS-O-03 | App builder IDE | complete `app_builder` | `AppBuilderPreview`: file-tree explorer (search `Search files...`, `Collapse/Expand all`), `{n} files` badge, `Full Screen`, `Download ZIP` (→ `Zipping...`), code viewer with line numbers; **121-file tree** rendered in campaign | ✅ (S04) |
| TS-O-04 | PPT deck | complete `od_ppt` | `iframe[title="Slide Deck Preview"]` renders the deck (`<!DOCTYPE html>`, `<section class="slide">×5`) — **NOT** QA narration (ISS-001 fix); `Download` (od → presentation.html / else `/api/runs/export-pptx` → `Exporting…`) + `Full Screen` | ✅ (S03; 18,661-char deck) |
| TS-O-05 | Prototype live app | complete `od_prototype` | `iframe[title="Prototype Preview"]` `src=<blobUrl>` renders the live app; browser-chrome bar `prototype.preview`; zoom controls; `Tweaks`/`Source`/`Open` toggles | ✅ |
| TS-O-06 | Tabs switch | click `Files` / `Thinking` | Files tab (TS-O-07); Thinking tab (TS-J); ~150ms AnimatePresence transition | 🔴 |
| TS-O-07 | Files tab | after a run | empty `No files available` + `Run a workflow to generate downloadable files`; else `{n} file[s] available` + `Download All`; app_builder sections `Project Download`/`Source Code Files`/`Agent Outputs ({n})` | 🔴 |
| TS-O-08 | Copy button | `hasContent` | `title="Copy"` copies `activeContent`, green check for 2000ms | 🔴 |

### TS-P — Generic deliverable & iframe security (custom/unknown mimetype) — **SECURITY-CRITICAL**

`GenericDeliverablePreview` dispatches on **`deliverable_mimetype` (lowercased), never a workflow name (SC-001)**. This is the ISS-021 + Phase 18 custom-deliverable path and the highest-value security assertion in the register.

| ID | Title | Steps | Expected (exact) | Status |
|---|---|---|---|---|
| TS-P-01 | **Custom HTML in sandboxed iframe** | run `custom`/SC-001 workflow producing `text/html` | `iframe[title="Deliverable Preview"]` with **`sandbox="allow-scripts"` EXACTLY — NO `allow-same-origin`**, `srcDoc=<html>`, no `allow=` attr; renders the live HTML | ✅ (V2: live "Habit Tracker") |
| TS-P-02 | Markdown escaped | `text/markdown` deliverable | `MarkdownPreview` (NOT an iframe); raw `<script>`/`<iframe>`/`<img onerror>` in the markdown is **escaped to literal text** (no `rehype-raw`) — assert no live nodes injected | 🟢 (security.test) / 🔴 UI |
| TS-P-03 | Zip → IDE | `application/zip` deliverable | renders `AppBuilderPreview` bundle | 🔴 |
| TS-P-04 | Unknown → download card | any other mimetype | `Deliverable ready` + `This deliverable ({mimetype}) can be downloaded from the Files tab.` + `Download {filename}` button (triggers real browser download); **no iframe** | 🔴 |
| TS-P-05 | **iframe sandbox matrix** | inspect each iframe | generic HTML = `allow-scripts` only; non-od PPT = `allow-scripts` only; **od_ppt** = `allow-scripts allow-same-origin`; **prototype** = `allow-scripts allow-same-origin` (`src=blobUrl`). Assert each exactly | 🟢 (component tests) / 🔴 UI |
| TS-P-06 | XSS payload contained | inject `<script>parent.location=…</script>` into a custom HTML deliverable | script cannot reach parent (no same-origin); no navigation/cookie theft | 🔴 |

### TS-Q — Terminal states & degraded affordance (server-signal-gated)

`DegradedRunAffordance` shows when `!hasContent && isTerminal && (server failed/degraded OR reopened status∈{failed,cancelled,degraded})`. **Strictly server-derived — never a client "empty==failed" guess** (a clean empty run shows the neutral state).

| ID | Title | Steps | Expected (exact) | Status |
|---|---|---|---|---|
| TS-Q-01 | Success | normal completion | deliverable renders; header `Results`; no failure chrome | ✅ |
| TS-Q-02 | **Model error → failed (ISS-016)** | run on the **srini** backend (forces `ValidationException`) | per-agent `ERROR` badges, sanitized text `The model rejected this request.` (raw exception server-side only — WR-02); terminal `pipeline_failed` (6 `agent_error`/0 `agent_complete`); **degraded panel** `This run did not complete successfully` + `No deliverable was produced. The run ended in a failed or degraded state.` + `Failed agents` list + `View details / retry` — **NOT** DONE badges + `Output will appear here` | ✅ (V3/V8 live) |
| TS-Q-03 | Degraded (partial) | a run with `status:"degraded"` | degraded agents → `error`, others swept `done`; partial deliverable still renders; chat warning `[code:pipeline_degraded]` | 🟡 |
| TS-Q-04 | Cancelled (history) | reopen a `cancelled` run | `This run was cancelled` + `The run was stopped before producing a deliverable.` | 🔴 |
| TS-Q-05 | Clean empty ≠ failed | a completed run with no content + no failure flag | **neutral** `Output will appear here` (NOT the affordance) — server-signal-gating proof | 🟢 (degraded.test) / 🔴 UI |
| TS-Q-06 | Content wins | terminal with content but a stale `failed` flag | renders the deliverable, not the affordance | 🟢 / 🔴 UI |
| TS-Q-07 | Retry affordance | degraded run with a revise handler | `View details / retry` button → calls retry; without handler → `Open the Thinking tab to view details.` | 🔴 |

### TS-R — Cancel (Stop)

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-R-01 | **Stop delivers cancel (ISS-007/002)** | click `Stop` mid-run | WS sends `{type:"cancel_pipeline"}`; engine cooperative-cancel (not destructive); `pipeline_cancelled` is **delivered to the FE wire** | ✅ (V4 live, count 1) |
| TS-R-02 | In-flight cards clear | after cancel | running/thinking agents → `idle` (badges cleared, **no stuck RUNNING**); done/error untouched; header `Pipeline stopped` | ✅ (`[]` badges) |
| TS-R-03 | Live cancel ≠ failure chrome | after a live Stop | preview shows neutral/last-content, **NOT** the degraded affordance (live cancel sets no `failed`/`degraded` flag — only history-reopen of a `cancelled` run shows cancelled copy) | 🟡 |
| TS-R-04 | Cancel during revision | Stop a revision run | bg task cancelled, row `cancelled`, no exact-kind ref written (no poisoned parent) | 🟡 |

### TS-S — Reconnect / replay (resilience of a live run)

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-S-01 | **Reconnect ack (ISS-008/009)** | reload mid-run | on WS `connected`, FE sends `{type:"reconnect_pipeline", pipeline_run_id, after_seq:<lastSeq>}`; `pipeline_reconnected` ack carries `live`, `replayed_through_seq`, `status` all present (`live` always explicit) | ✅ (V5 live) |
| TS-S-02 | live:true keeps streaming | reconnect to a still-running run | `live!==false` → keep `isRunning`, tail streams via subsequent `agent_*`/`pipeline_complete` | 🟡 |
| TS-S-03 | live:false + terminal resolves | reconnect after backend restart/finish | `live:false` + `status∈{completed,failed,cancelled}` → resolve out of running (stops the "running forever" hang); completed sweeps agents `done` | 🟡 |
| TS-S-04 | Panels rebuild | reload mid-run | replayed durable tail re-drives `pipeline_start`→`agent_*` → panels rebuild from scratch; no home-flash | ✅ |
| TS-S-05 | Replay dedup | reload | replayed frames idempotent by `event_id` — no duplicated streamed text / wave leaves; `seq` cursor only advances after dedup | 🟢 (wsReplayState.test) / 🔴 UI |
| TS-S-06 | Revision replay section (ISS-008) | reconnect mid-revision | replay frames carry the revision `section` (e.g. `od_ppt_output`), matching live-attach (WR-03) | 🟡 (29 live-attach frames ✅) |
| TS-S-07 | Cross-owner demotion | reconnect another user's run id | → ∅ + `live:false` + null status (no leak) | 🟢 (live P12) |

### TS-T — Workflow history (WorkflowHistory)

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-T-01 | List & badges | open History | rows: icon + title + `{label} · {date} · {duration}`; status badge `Done`(emerald)/`Cancelled`(amber)/`Failed`(gray)/`Running`(gray, also degraded/revising) | 🔴 |
| TS-T-02 | Filter & search | tabs + search | tabs `all/user_stories/ppt/prototype/app_builder/custom`; `Search workflows...` filters by title | 🔴 |
| TS-T-03 | Reopen | click a row | detail view (agents sidebar + Preview/Files/Thinking); content from `run.output` or `getWorkflow(id)` | 🔴 |
| TS-T-04 | **Generic reopen (ISS-021 parity)** | reopen a custom HTML run | same heuristic as live: `text/html` → `iframe[title="Deliverable Preview"]` `sandbox="allow-scripts"` (no same-origin); `zip`→IDE; else MarkdownPreview | 🟢 (genericReopen.test) / 🔴 UI |
| TS-T-05 | Reopen failed/cancelled | reopen a failed/cancelled run | degraded/cancelled affordance via `reopenedRunStatus` (TS-Q-02/04) | 🔴 |
| TS-T-06 | Delete | kebab → Delete → confirm | modal `Delete workflow` / `The workflow run and all its output will be permanently deleted.`; `deleteWorkflow` removes the row | 🔴 |
| TS-T-07 | Chaining | completed run footer | `Suggested next steps` → `availableChainTargets(type)` buttons start the chained pipeline | 🔴 ⚪(chaining.test ×6 KNOWN-FAIL) |

### TS-U — Revision runs (F2 end-to-end) — the real revision loop (Phase 14/15)

The revision loop must be tested end-to-end per workflow. A revision dispatches **real** agents (a model runs), produces a **revised** deliverable (not the instruction echo), persists `derived_from` lineage, and bypasses clarify.

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-U-01 | **od_ppt revise (SC1)** | from a completed od_ppt run, click revise, enter `Add a slide about ROI` | a **revision run streams** (real agent cards/output) → revised deck in `Slide Deck Preview`; existing deck stays visible until new output (section contract — content not cleared for `*_revision`) | ✅ (S03 live, 118 frames) |
| TS-U-02 | No clarify on revision (A1) | observe a revision run | **zero** `questionnaire_ready` frames (manifest `planner: skip`); no clarify form | 🟡 (live: 0 across 4) |
| TS-U-03 | Lineage (SC2) | after a revision completes | persists a `derived_from` ref to the parent (owner/workspace-scoped, exact kind); a **failed** revision writes NOTHING (no poisoned parent) | 🟡 |
| TS-U-04 | Revision-of-revision | revise a revision | resolves via FR-014 chain link 1; produces a 2nd revised deliverable | 🟢 / 🔴 UI |
| TS-U-05 | Terminal fidelity (SC4) | drive a revision to each outcome | row lands `completed`/`degraded`/`failed`/`cancelled` correctly — **never stuck `revising`**; a failed revision is not offered as a future parent | 🟡 |
| TS-U-06 | Surgical-diff prototype revise | revise a prototype with `Add a Reports page` | agent returns only changed sections; engine merges into full HTML; updated prototype renders | 🔴 |
| TS-U-07 | User-story / app revise | revise via the per-preview `Revise` bars | each preview's revision input (exact placeholders per type) + `Revise` button starts a `*_revision` run | 🔴 |
| TS-U-08 | Reconnect during revision (WR-03) | reload mid-revision | live-attach frames carry `section` = `{base}_output`; panels rebuild | 🟡 (29 frames ✅) |

### TS-V — Full per-workflow end-to-end (each pipeline, real Bedrock)

One green-path run per workflow type, asserting the full chain (trigger → clarify? → agents → gates? → waves? → deliverable + mimetype). Detailed expectations in §4.

| ID | Workflow | Key assertions | Status |
|---|---|---|---|
| TS-V-01 | `user_stories` (6 agents) | clarify questionnaire → agent cards → `Product Backlog`; **0** fabricated tool-XML in any chunk/final (F4) | ✅ (S01) |
| TS-V-02 | `od_prototype` (4 agents, wizard) | template wizard → 2 human gates (`Specification Review`, `Task Plan Review`) → Spec-Kit live view → prototype iframe | ✅ (S02) |
| TS-V-03 | `od_ppt` (3 agents, wizard) | deck in `Slide Deck Preview` (not QA narration) → revise → revised deck | ✅ (S03) |
| TS-V-04 | `app_builder` (15 agents) | IDE file tree; infra-generator emits `/api/v1` (≥6, 0 bare `/api/` — ISS-005); `getDatabase` not `getDb` (ISS-006); devops emits files | ✅ (V7 live) |
| TS-V-05 | **`custom` SC-001 (`ui_custom_proto`)** | factfind → 3-worker fanout (wave panel) → human gate → task_loop build (validators) → custom **HTML deliverable in generic iframe** — **proves a brand-new workflow runs with zero engine edits** | ✅ (V2 live, 190s/$0.17) |
| TS-V-06 | `sample_fanout` | 3 workers + `copy_disjoint` merge in wave panel; serialized bundle deliverable | ✅ (S10) |
| TS-V-07 | `sample_wave` | multi-wave topo execution; wave fold above the fold | ✅ (V1) |
| TS-V-08 | `mulesoft_to_springboot` | migration path tile → inventory/decompose agents → deliverable | 🟠 (06-12 with source) |
| TS-V-09 | `dotnet_to_azure` | migration path tile → .NET inventory/modernise agents → deliverable | 🟠 (06-12) |

### TS-W — Per-agent model selection, live (model override actually applied)

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-W-01 | Override one agent live | compose a run, set agent A → a non-Haiku model, Run on real Bedrock | run completes; backend resolves agent A on the chosen model; `pipeline_complete.model_id` + Token cost label reflect it; other agents stay default Haiku | 🔴 (live) |
| TS-W-02 | Override invalid blocked | set a model id not in the catalog (tampered) | run refused at ingress (`invalid_model_override`), no agents run | 🟢 / 🔴 UI |
| TS-W-03 | No-override parity | run with all Default | payload omits `model_overrides`; behavior identical to pre-model-policy | 🟢 char-locked |

### TS-X — Performance & timing budgets

Durations are wall-clock (assert **ranges/regex**, not exact values). Capture per-run timings to a CSV for trend tracking.

| ID | Title | Target / assert | Status |
|---|---|---|---|
| TS-X-01 | Client ping | WS sends `{type:"ping"}` every **20000ms** while OPEN (keeps long builds alive) | 🔴 |
| TS-X-02 | Reconnect backoff | `min(1000·2^n, 30000)`ms, no retry cap; banner `Connection lost. Reconnecting in {s}s… (attempt {n})` | 🔴 |
| TS-X-03 | Questionnaire auto-advance | 300ms after MCQ select | 🔴 |
| TS-X-04 | Prototype tweaks debounce | 400ms token-change → iframe rebuild | 🔴 |
| TS-X-05 | Copy toast | 2000ms revert | 🔴 |
| TS-X-06 | Custom pipeline wall-clock | `ui_custom_proto` ≈ **190s, ~$0.17** on Haiku (V2 baseline) — alert if a run exceeds ~2× baseline | ✅ baseline |
| TS-X-07 | Per-workflow budgets | record expected ranges: user_stories (clarify+6 agents), od_prototype (4 + 2 gates), od_ppt (3), app_builder (15 ≈ minutes), custom (5). Establish SLOs from first green runs | 🔴 |
| TS-X-08 | No spinner-forever | every run reaches a terminal state (no stuck `RUNNING`/`isRunning`) within its budget — the cancel/reconnect regressions this guards | ✅ (R/S) |

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

### 6.1 What IS verified

- **Backend (🟢):** the entire §2 set is green offline + characterization-locked + CI-gated (44 passed/7 skipped parity+gate suite; 206-test compiler/model/gate suite; `lint-imports` 4/0; SC-001 proofs; alembic head 0020; registry==63). This is the trust floor.
- **Live + visual (✅), 2026-06-13 campaign (V1–V8) + 2026-06-12 re-pass + UI-CAMPAIGN (S01–S12):**
  - ISS-016/017 model-error → `pipeline_failed` + degraded panel (on the srini `ValidationException`) — **the major one**.
  - ISS-021 custom HTML in the generic sandboxed iframe; ISS-007/002 cancel delivery + cards clear; ISS-019 wave-fold above the fold; ISS-014 composer deleted + relocated model picker; ISS-005 `/api/v1`×6; ISS-006 `getDatabase`.
  - F1 declared-gate streaming (2 review gates); F4 zero tool-XML (user_stories/od_ppt); F6 sample_fanout; ISS-001/LV-02 od_ppt deck (18,661 chars); SC1 revision real loop (118 frames); WR-03 revision reconnect section (29 frames).
  - Per-workflow green paths: user_stories, od_prototype (Spec-Kit + 2 gates), od_ppt, app_builder (121-file IDE), **custom `ui_custom_proto` (the SC-001 headline, 190s/$0.17)**, sample_fanout, sample_wave.
- **Live-mech + offline-backed (🟡):** ISS-008/009 reconnect contract; revision lineage/terminal-fidelity; degraded partial.

### 6.2 What is NOT (yet) verified — close before production sign-off

| Gap | Why | Action |
|---|---|---|
| **No committed Playwright suite** | campaign used throwaway `/tmp` harnesses (not in repo) | **§7-G1 — build the suite from §3.** Highest priority. |
| ISS-004 `app-sdlc-governance` anti-tool-XML | agent sits deep in app_builder; never reached the live window | 🟠 OFFLINE-ONLY — drive a full app_builder run to completion and assert 0 tool-XML in its stream |
| Migration with source repos (TS-V-08/09) | needs repo inputs the bare-brief harness lacks | 🟠 — provide a fixture source repo, run mulesoft + dotnet to a deliverable |
| Multi-worker isolated-write (fan-out) | offline harness runs `shared_read` | drive a live fan-out where 2 workers write different files; assert no cross-contamination |
| Live `has_git=True` workspace provisioning | forward ECS seam | exercise the brownfield/repo workflow live |
| Prototype surgical-diff revise (TS-U-06) | not in the campaign | author the Playwright case |

### 6.3 Known-fail baseline (⚪ — do NOT block on these)

| Item | Where | Logged |
|---|---|---|
| `AgentProgressPanel.test.tsx` (×1, "hides chain panel when all base complete") | FE vitest | ISS-022 |
| `workflowChaining.test.ts` (×6, `availableChainTargets` ordering) | FE vitest | ISS-025 |
| `test_phase5_revision_validation.py::…event_types_subset_of_documented_vocabulary` | BE | ISS-026 |

These are pre-existing, triaged, non-regression. The register flags them so a QA run of `npm test` (102 pass / 7 fail) isn't misread as new breakage. (ISS-012 REQUIREMENTS.md traceability drift and ISS-023/024 cosmetics are also logged-open backlog, not test failures.)

### 6.4 Production-readiness verdict

**Backend kernel: production-ready** (verified + CI-gated). **UI behavior: now repeatably automated** — the committed Playwright suite (`frontend/e2e/`, 123 mocked green + 7 live) exercises every §3 surface in a real browser, so QA can verify everything by running `npm run e2e` (mocked) and `npm run e2e:live` (real Bedrock). Remaining to full sign-off: wire `e2e` (mocked) into CI as an MR gate (§7-G4), seed users + run the live layer to close the §6.2 deferred items, and optionally add `data-testid`s (§7-G3) to de-brittle selectors.

---

## 7. Gaps & prerequisites to make this register runnable

### G1 — Build the committed Playwright E2E suite (the headline work) — ✅ DONE (2026-06-14)

**Built and green** at `frontend/e2e/` — 21 spec files (19 mocked TS-A…TS-Y + 2 live), 123 mocked tests passing / 0 failing / 15 documented `fixme`, ~1.3 min. Architecture exactly as specified below: a browser-level **mock-WS** (`page.routeWebSocket`) + **mock-API** (`page.route('**/api/**')`) harness for the deterministic mocked layer (no backend), and a `*.live.spec.ts` layer (`fixtures/live.ts`) for real Bedrock. `@playwright/test@^1.56` added; `seed_test_users.py` written (G2). See `frontend/e2e/README.md` + `frontend/e2e/FIXTURE-CONTRACT.md`. The original target layout that was built:

```
frontend/e2e/
  playwright.config.ts            # baseURL http://localhost:3000, projects: chromium (+firefox for voice-absent), webServer optional
  fixtures/
    auth.ts                       # programmatic login → seed localStorage["auth_token"]; per-tier storageState (basic/pro/enterprise)
    ws.ts                         # helpers to assert outbound run_pipeline frames + capture inbound events
  tests/
    ts-a.auth.spec.ts  ts-b.selection.spec.ts  ts-c.input-trigger.spec.ts
    ts-d.composer.spec.ts  ts-e.model-picker.spec.ts  ts-f.skills-hooks.spec.ts
    ts-i.agent-panels.spec.ts  ts-k.wave-tree.spec.ts  ts-m.questionnaire.spec.ts
    ts-n.review-gate.spec.ts  ts-o.deliverables.spec.ts  ts-p.iframe-security.spec.ts
    ts-q.terminal-states.spec.ts  ts-r.cancel.spec.ts  ts-s.reconnect.spec.ts
    ts-t.history.spec.ts  ts-u.revisions.spec.ts  ts-v.e2e-per-workflow.spec.ts
```

- **Two run modes:** *mocked-WS* (deterministic, fast, no Bedrock — drive each `pipeline_*`/`agent_*`/`wave_*`/gate frame from fixtures to assert UI mapping for TS-I/J/K/Q/R/S) **and** *live-Bedrock* (`AWS_PROFILE=default`, the §4 per-workflow runs — slower, real). The campaign's throwaway scenario-JSON driver is the template; commit its successor.
- **Reuse the srini fault-injector** for TS-Q-02 (run a backend instance with `AWS_PROFILE=hexaware-srini` to force the `ValidationException`).
- Mirror the existing security assertions (`PreviewPanel.degraded.test.tsx`, `genericDeliverable.test.tsx`, `MarkdownPreview.security.test.tsx`) **in-browser** for TS-P.

### G2 — Seed users (hard prerequisite)

Registration is 403-disabled, user creation is admin-only, **no seed script exists**. Add `backend/scripts/seed_test_users.py` (direct insert via `app.core.security.hash_password`) creating `qa-basic@`, `qa-pro@`, `qa-enterprise@`, and an admin. Playwright `fixtures/auth.ts` logs in via `POST /api/auth/login` and stores per-tier `storageState`.

### G3 — Add `data-testid` to load-bearing nodes

Text/role selectors work but are brittle. Add stable testids to: the Stop button, agent-card status badge (`RUNNING`/`DONE`/`ERROR`), the wave panel heading + each wave/worker leaf, the failure-affordance root, the generic deliverable iframe, history rows + status badges, the reconnecting/connection-lost banners, the per-agent model `<select>`, and the questionnaire submit. This de-brittles TS-I/K/Q/T/E/M.

### G4 — Wire tests into CI

Today CI runs only `backend:characterization` (7 files) + `backend:test` (`tests/unit`) + `backend:lint` (`lint-imports`/`ruff`/`vulture`) + `frontend:lint`/`frontend:typecheck`. **FE vitest (109 tests) and the new Playwright suite are NOT gated.** Add `frontend:test` (vitest, with the 7 known-fails quarantined/fixed) and `e2e:mocked` (Playwright mocked-WS) as MR gates; run `e2e:live` nightly.

### G5 — Offline backend test ergonomics

Full `pytest` hangs offline (Postgres/Bedrock/Chromium-gated) and the `requires_api_key` marker isn't applied uniformly to `*_live.py`/Chromium suites. Add an `offline` marker (or `-m "not requires_api_key and not live"`) and a `make test-offline` target wrapping the §1.6 list so QA has one reliable offline command.

---

## Appendix A — Source maps consumed to build this register

- Architecture spine: `.planning/IMPLEMENTATION-REGISTER.md` + `_register-parts/00..19`.
- Frontend behavior (exact strings/states/selectors/timing): the 4 component maps — compose/trigger (`IdeaInputPage`/`AgentsPopup`/`AgentModelPicker`/`CreationHub`), live panels (`AgentProgressPanel`/`WaveTreePanel`/`AgentThinkingTab`/`TokenUsageSummary`), preview/terminal (`PreviewPanel`/`MarkdownPreview`/`QuestionnairePanel`/`ReviewGatePanel`/per-workflow previews), state/WS/history (`useWorkflow`/`useWebSocket`/`wsReplayState`/`WorkflowHistory`/`DashboardLayout`).
- Live evidence: `.planning/live-verification/CAMPAIGN-2026-06-13-phases16-19.md` (V1–V8), `UI-CAMPAIGN-2026-06-13.md` (S01–S12), `REPORT-2026-06-12.md` (re-pass).
- Issue WHY: `.planning/ISSUES-REGISTER.md` (deep root-cause investigation, ISS-001..026).

## Appendix B — Exact UI strings quick-reference (assert verbatim)

`What would you like to build today?` · `Run workflow` / `Add agents first` / `Pick a migration path` · `Per-Agent Model` / `Default` · `Workflow configuration` · `Review gates` / `no gates` / `{n} agents pause for review` · `Wave / Subagent Tree` / `No waves running.` · `RUNNING`/`DONE`/`ERROR` · `Pipeline stopped` / `{n} / {m} agents` / `Done in {x}s` · `Reasoning (live)` + `▌` · `✓ PROCEED` / `⚡ CLARIFY` · `Quick Setup` / `Run with defaults` / `Skip all & run directly` · `Specification Review` / `Task Plan Review` / `Approve & continue` / `Reject & cancel pipeline` · `Output will appear here` · `This run did not complete successfully` / `No deliverable was produced. The run ended in a failed or degraded state.` / `Failed agents` / `View details / retry` · `This run was cancelled` · `Deliverable ready` / `Deliverable Preview` (iframe `sandbox="allow-scripts"`) · `Slide Deck Preview` / `Prototype Preview` · History badges `Done`/`Cancelled`/`Failed`/`Running` · `The model rejected this request.`

---
*End of TEST-REGISTER. This document is the QA reference for v1.0 production sign-off. Update the Status column as Playwright cases are authored and live runs are recorded.*



