---
phase: 8
slug: capabilities-hardened-registry-gates-tool-perms-runtime-3
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-09
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> **This is a capability-hardening + factory-deletion phase under strict INV-3 parity.** The existing CI gates (5-pipeline characterization snapshots, migration-ledger F1–F5 ratchet, banned-pattern, import-linter) already encode every parity + deletion check; Phase 8 keeps them green while binding real impls into the registry/gate/validator/provider seams, then flips the F1–F5 ratchets. New unit coverage lands for the genuinely-new surfaces (gates, validators, hooks, trust, API). Source: `08-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest` + `pytest-asyncio` (Python 3.11, no venv) |
| **Config file** | `backend/pyproject.toml` (`[tool.pytest]`, `[tool.importlinter]`, `[tool.vulture]`) |
| **Quick run command** | `cd backend && python3.11 -m pytest tests/agents/test_<target>.py tests/agents/test_migration_ledger.py tests/agents/test_banned_patterns.py -x` (targeted cap test + fast ratchet/banned-pattern pulse) |
| **Full suite command** | `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v` |
| **Parity gate (every plan)** | `cd backend && python3.11 -m pytest tests/agents/test_characterization_*.py` (the 5 pipelines — byte + semantic-event parity) |
| **Adjacent gates** | `cd backend && lint_imports` (import-linter: kernel→ports, no `agents.capabilities → app`) · `cd backend && vulture app/ agents/` (orphan check before F1–F5 deletions) |
| **Estimated runtime** | ~60–120s full suite (offline; Chromium/Bedrock/Postgres degrade cleanly) |

---

## Sampling Rate

- **After every task commit:** Run the targeted unit test for that capability + `cd backend && python3.11 -m pytest tests/agents/test_migration_ledger.py tests/agents/test_banned_patterns.py -x` (fast ratchet + INV-13/F5 pulse).
- **After every plan wave:** Run `cd backend && python3.11 -m pytest tests/agents/test_characterization_*.py` (5 pipelines) + `lint_imports` + `vulture app/ agents/`. **Run in a CLEAN session** (the `test_strategies.py` global-registry pollution — fixed in 08-01; until then it corrupts the snapshots when run same-session).
- **Before `/gsd-verify-work`:** Full suite green + all 5 characterization snapshots byte-identical (no re-baseline) + migration-ledger F1–F5 rows ☑ + banned-pattern green + import-linter green.
- **Max feedback latency:** 120 seconds.

---

## Per-Task Verification Map

> Strategy-level map keyed by plan + requirement (tasks are created by the planner; the executor refines this into per-task rows). Plan IDs follow CONTEXT D-12 / ROADMAP 08-01..08-08. **PLAN.md frontmatter `wave:` is authoritative** — the waves below are the dependency-implied grouping (08-01 is the substrate everything registers into; 08-02/03/04 bind into it; 08-05/06 lift+delete the factory; 08-07 hooks; 08-08 API/frontend). The `0016` migration lands with the first plan that writes its rows (08-02 `gate_events` / 08-04 `validation_results` / 08-07 `hook_runs` — planner may front-load all three columns in one early migration).

| Plan | Wave | Requirement | Behavior to Prove | Test Type | Automated Command | File Exists | Status |
|------|------|-------------|-------------------|-----------|-------------------|-------------|--------|
| 08-01 | 1 | CAP-01, CAP-02 | `@register`+`discover()` resolvable; no central `if/elif`; adding a module makes it resolvable with zero registry edits; idempotent | unit | `pytest tests/agents/test_registry_capabilities.py -x` | ✅ (update `_EXPECTED_NAMES` + count assertion) | ⬜ pending |
| 08-01 | 1 | CAP-03 | user-trust compile of a non-`user_allowed` cap raises a naming error; file/built-in manifest compiles unrestricted | unit | `pytest tests/agents/test_compiler*.py -k trust -x` | ❌ W0 (new trust test) | ⬜ pending |
| 08-01 | 1 | D-12 fold (test-isolation) | autouse `_IMPLS` save/restore reset fixture; `test_strategies.py` no longer pollutes the global registry across a session | unit | `pytest tests/agents/test_strategies.py tests/agents/test_characterization_*.py -x` (same session, green) | ✅ fix existing | ⬜ pending |
| 08-02 | 2 | GATE-01 | 4 gate kinds resolve from the registry; `gates:[security]`+`exec` blocks (exec OFF); `gates:[approval]` pauses for sign-off; each exercised by ≥1 test manifest | unit | `pytest tests/agents/test_gates.py -x` | ❌ W0 | ⬜ pending |
| 08-02 | 2 | GATE-02 | `gates:[validation]` with a P0 issue blocks; with only a P2 issue emits `validation_warning` and proceeds | unit | `pytest tests/agents/test_gates.py -k validation -x` | ❌ W0 | ⬜ pending |
| 08-02 | 2 | GATE-03 | `human` gate routes through `_run_review_gate`; identical `review_gate_*` sequences; no snapshot re-baseline | characterization | `pytest tests/agents/test_characterization_prototype.py -k gate -x` | ✅ (no re-baseline) | ⬜ pending |
| 08-03 | 2 | TOOLPERM-01/02/03 | effective = `intersection(owner, workflow, step)`; AGENT.md only lowers; a step without `write_files` binds no write tool; `exec`/`network`/`secrets`/`spawn` unbindable by default; existing agents bind identical sets | unit | `pytest tests/agents/test_create_runner.py -x` + new perm-intersection test | ✅ + ❌ W0 | ⬜ pending |
| 08-03 | 2 | AGENTRT-04 (F2) | `_build_runner_tools` grep → 0; tool sets resolve via the `tool_provider` registry; identical tool sets (parity) | gate + unit | `pytest tests/agents/test_create_runner.py tests/agents/test_migration_ledger.py -x` | ✅ flip F2 | ⬜ pending |
| 08-04 | 2 | VALID-01/02/03 | registry-run validators; generic `FixPolicy` loop (not hardcoded `prototype.html`); single P0–P3→CRITICAL/HIGH/MEDIUM/LOW mapping function | unit | `pytest tests/agents/test_validators.py -x` | ❌ W0 | ⬜ pending |
| 08-04 | 2 | VALID-04 | `html_static`/`html_render` registered; `task_loop` routes through them; each attempt writes a `validation_results` row; deliverable + event parity held | unit + characterization | `pytest tests/agents/test_validators.py tests/agents/test_characterization_prototype.py -x` | ❌ W0 + ✅ | ⬜ pending |
| 08-04 | 2 | VALID-05 (Tier#4/5/6) | `spec_plan_coverage`/`task_done_when`/`design_quality` registered + run; each exercised by ≥1 test manifest; `design_quality` non-blocking (warn only) | unit | `pytest tests/agents/test_validators.py -k tier -x` | ❌ W0 | ⬜ pending |
| 08-05 | 3 | AGENTRT-01/02 (F5) | `create_deep_agent` imported/called ONLY inside the `langchain_deepagents` adapter; `create_runner` selects runtime via adapter | gate | `pytest tests/agents/test_banned_patterns.py -x` | ✅ | ⬜ pending |
| 08-05 | 3 | AGENTRT-03 (F1) | `blocks\.append` grep → 0 in `factory.py`; `PromptAssemblyPolicy` drives block order; composed prompts byte-identical for existing agents | gate + characterization | `pytest tests/agents/test_migration_ledger.py tests/agents/test_characterization_*.py -x` | ✅ flip F1 | ⬜ pending |
| 08-05 | 3 | AGENTRT-05, SKILL-01 (F3) | `_inject_skills\|_inject_hooks` grep → 0; skills resolve via `skill_provider` with version metadata; `## Active Behavioral Hooks` block still renders | gate + unit | `pytest tests/agents/test_guardrails.py tests/agents/test_migration_ledger.py -x` | ✅ flip F3 | ⬜ pending |
| 08-06 | 3 | AGENTRT-06 (F4/R12) | DB-stored Constitution injected under a running event loop; constitution-injected-in-prod test passes | unit (NEW) | `pytest tests/agents/test_constitution_prod.py -x` | ❌ W0 | ⬜ pending |
| 08-07 | 4 | HOOK-01/02/03/04 | `secret_scan` blocks a `before_write` carrying a secret + writes a `hook_runs` row `outcome=block`; a hook lacking its required permission is not bound; every firing writes a row | unit | `pytest tests/agents/test_hooks.py -x` | ❌ W0 | ⬜ pending |
| 08-07 | 4 | OBS-02 | `otel_tracing` fires on `*` non-blocking → span/log + `hook_runs` row | unit | `pytest tests/agents/test_hooks.py -k otel -x` | ❌ W0 | ⬜ pending |
| 08-02/04/07 | 2–4 | PERSIST (D-10) | additive `0016` adds `validation_results`/`gate_events`/`hook_runs`; each row carries `owner_id`+`workspace_id`; writes via `ScopedStore` | migration + unit | `cd backend && alembic upgrade head` + `pytest tests/unit/test_migrations.py -x` | ❌ W0 | ⬜ pending |
| 08-08 | 5 | API-02 | `GET /api/capabilities` returns the palette (kind, name, `user_allowed`, config schema) incl. runtimes/skills/hooks/model catalog with required auth + permission scopes | unit | `pytest tests/unit/test_capabilities_api.py -x` | ❌ W0 | ⬜ pending |
| 08-08 | 5 | API-03 | run stream emits `validator_result`/`validation_warning`/`gate_*` additively; existing workflows at semantic parity (no event renamed/removed) | unit + characterization | `pytest tests/unit/test_capabilities_api.py tests/agents/test_characterization_*.py -x` | ❌ W0 + ✅ | ⬜ pending |
| 08-08 | 5 | API-06 (partial) | capability palette + per-agent model picker + validator/issue panel render from live API data | manual (frontend) | see Manual-Only Verifications | n/a | ⬜ pending |
| all plans | 1–5 | INV-3 (strict parity) | 5 characterization snapshots byte-identical (deliverables) + semantic-event parity; new events additive only | characterization | `pytest tests/agents/test_characterization_*.py -x` | ✅ | ⬜ pending |
| 08-01,03,05 | 1–3 | F1–F5 ledger ratchet | F1–F5 rows flip ☑; grep/CHECK gates become permanent ratchets; no regression of L1–L16 | ratchet | `pytest tests/agents/test_migration_ledger.py -x` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> New unit coverage + test-coupling migrations the executor must land before/with the capability work (from RESEARCH § Wave 0 Gaps). The existing characterization suite already covers the 5-pipeline parity surface; these cover the genuinely-new gate/validator/hook/trust/API surfaces.

- [ ] `tests/agents/test_gates.py` — GATE-01/02 (security/approval/validation handlers + outcomes pass|block|wait_human)
- [ ] `tests/agents/test_validators.py` — VALID-01..05 (registry-run, generic `FixPolicy` loop, P0–P3 severity mapping, Tier#4/5/6, `design_quality` non-blocking)
- [ ] `tests/agents/test_hooks.py` — HOOK-01..04/OBS-02 (`secret_scan` block + row, `otel_tracing` span + row, permission gating leaves unpermissioned hooks unbound)
- [ ] `tests/agents/test_constitution_prod.py` — AGENTRT-06 (DB Constitution injected under a running event loop)
- [ ] `tests/agents/test_compiler*.py` trust cases — CAP-03 (`user_allowed=False` reference raises a naming compile error; file/built-in manifest unrestricted)
- [ ] `tests/unit/test_capabilities_api.py` — API-02/03 (`/api/capabilities` palette + auth + scopes; additive WS events)
- [ ] `tests/unit/test_migrations.py` (or `alembic upgrade head` smoke) — PERSIST (3 tables exist additively; rows carry `owner_id`+`workspace_id`)
- [ ] **Update existing:** `test_registry_capabilities.py` `_EXPECTED_NAMES` + the impl-free count assertion (new `tool`/`skill`/`hook`/`runtime` kinds + names bump the count — expected in-scope edit; the impl-free-at-compiler-import contract must still hold)
- [ ] **Fix existing (D-12 fold):** `test_strategies.py` autouse `_IMPLS` save/restore reset fixture (the global-registry pollution that corrupts same-session characterization snapshots)
- [ ] **Framework install (conditional):** `pip install opentelemetry-api opentelemetry-sdk` — **only if** real OTLP export is chosen for OBS-02; verify the package split + exporter on PyPI first. Logging-only span analog is the no-new-dep fallback. Gate the install behind a `checkpoint:human-verify` (RESEARCH A1).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Capability palette + per-agent model picker + validator/issue panel render from live data | API-06 | Frontend visual render; no headless DOM harness in the parity suite | Run the dev frontend against `/api/capabilities`; confirm the three panels populate from live API data (kind/name/`user_allowed`, model catalog, validator issues) |
| Live render-validated build (real Chromium) for `html_render` | VALID-04 | Headless Chromium absent locally — `render_check` degrades to `available=False` offline | Defer to end-of-milestone live pass (one real prototype build with Chromium present; confirm `html_render` fix-loop render lines + `validation_results` rows) |
| Real OTLP span export (if real OTel chosen over logging-only) | OBS-02 | Requires a running collector/exporter not present in CI | Defer to end-of-milestone live pass (export a span to a collector; confirm trace appears) — OR ship logging-only and mark N/A |

> Per project convention ([[defer-live-verification-to-milestone-end]]): parity is proven **offline** by design (the characterization suite runs fully offline). Live Chromium / real-OTLP checks are deferred to an end-of-milestone live pass and do not block phase completion.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (the 7 new test files + 2 update/fix-existing + conditional OTel install above)
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
