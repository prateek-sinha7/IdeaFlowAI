---
phase: 6
slug: model-policy-1c
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-08
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `06-RESEARCH.md` § Validation Architecture. Task IDs are linked once `06-*-PLAN.md` files exist.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.4 (+ pytest-asyncio 0.24.0 STRICT, hypothesis 6.122.3) |
| **Config file** | `backend/pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd backend && python3.11 -m pytest tests/agents/<file>.py -q` |
| **Full suite command** | `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v` |
| **Estimated runtime** | ~60 seconds (gate subset: 59 passed / 1 skipped at baseline) |

Supplemental gates (not pytest): `lint-imports` (import-linter — 3 contracts kept), characterization snapshots `tests/agents/characterization/` (INV-3 parity), banned-pattern (deepagents-only), migration-ledger ratchet.

---

## Sampling Rate

- **After every task commit:** Run the touched file's quick test (e.g. `pytest tests/unit/test_model_resolver.py -x`) + `lint-imports`.
- **After every plan wave:** `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -q` + `lint-imports` + `pytest tests/agents/characterization/ -q`.
- **Before `/gsd-verify-work`:** Full suite green + characterization snapshots unchanged (INV-3) + banned-pattern + migration-ledger green.
- **Max feedback latency:** ~60 seconds (gate subset).

---

## Per-Task Verification Map

Task IDs (`06-PP-TT`) are assigned at plan time; rows below are the requirement-level validation contract from research. The planner/executor links each row to its task.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | — | MODEL-01/05 | — | Precedence: 5 tiers, override>step>agent>workflow>global, None-skipping | unit | `python3.11 -m pytest tests/unit/test_model_resolver.py -x` | ❌ W0 | ⬜ pending |
| TBD | — | — | MODEL-01 (parity) | — | No-override run resolves to `session model_id or Haiku` == today | unit + characterization | `python3.11 -m pytest tests/agents/characterization/ -q` | ✅ assert unchanged | ⬜ pending |
| TBD | — | — | MODEL-02 | — | `ModelPolicy` drives `build_model` with resolved id; policy max_tokens does NOT raise runtime cap (still `MAX_OUTPUT_TOKENS`) | unit | `python3.11 -m pytest tests/unit/test_model_resolver.py::test_max_tokens_doc_only -x` | ❌ W0 | ⬜ pending |
| TBD | — | — | MODEL-02 (fallback) | — | Simulated throttle on chain[0] → engine advances → run completes on chain[1] (APPROACH B, no live Bedrock) | unit (scripted) | `python3.11 -m pytest tests/agents/test_model_fallback.py::test_throttle_advances -x` | ❌ W0 | ⬜ pending |
| TBD | — | — | MODEL-02 (exhaustion) | — | Every chain entry throttles → original/last error re-raised | unit (scripted) | `python3.11 -m pytest tests/agents/test_model_fallback.py::test_chain_exhaustion_reraises -x` | ❌ W0 | ⬜ pending |
| TBD | — | — | MODEL-02 (chain) | — | Empty `fallback` derives tier-descent: Opus→[Sonnet,Haiku], Sonnet→[Haiku], Haiku→[] | unit | `python3.11 -m pytest tests/unit/test_model_resolver.py::test_default_chains -x` | ❌ W0 | ⬜ pending |
| TBD | — | — | MODEL-03 | — | `model_overrides={agent→id}` resolves that agent; persists to `run_capabilities.model_overrides` | unit + integration | `python3.11 -m pytest tests/unit/test_run_capabilities.py -k model_overrides -x` | ✅ add case | ⬜ pending |
| TBD | — | — | MODEL-03 (reject) | T-6: arbitrary/unknown model id; T-6: unknown agent_id | Unknown model id OR unknown agent id → clear rejection (no run), reusing existing `{"type":"error"}` event | unit | `python3.11 -m pytest tests/unit/test_run_pipeline_validation.py -k override -x` | ✅ add case | ⬜ pending |
| TBD | — | — | MODEL-04 | — | Catalog lists entries w/ label/provider/cost_class/context_window/user_allowed; Opus `user_allowed=true`; registry membership | unit | `python3.11 -m pytest tests/agents/test_model_catalog.py -x` | ❌ W0 | ⬜ pending |
| TBD | — | — | MODEL-04 (INV-12) | — | `AVAILABLE_MODELS` derives; grep proves ONE model-id list; `/api/settings` shape unchanged | unit + grep | `python3.11 -m pytest tests/agents/test_model_catalog.py::test_available_models_is_projection -x` | ❌ W0 | ⬜ pending |
| TBD | — | — | AGENT.md model | — | `model:` parses to `AgentSpec.model` (None when absent); schema test green for all agents | unit | `python3.11 -m pytest tests/agents/test_loader.py -x` | ✅ extend | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_model_resolver.py` — precedence (5 tiers + None-skip), parity default, max_tokens-doc-only, default tier-descent chains (MODEL-01/02/05)
- [ ] `tests/agents/test_model_fallback.py` — scripted-throttle advance + chain-exhaustion re-raise (MODEL-02)
- [ ] `tests/agents/test_model_catalog.py` — catalog field set + registry membership + `AVAILABLE_MODELS`-is-projection + grep-single-source (MODEL-04 / INV-12)
- [ ] Extend `tests/agents/_scripted_model.py` — a throttle-raising variant for a given model id (no live Bedrock)
- [ ] Extend `tests/unit/test_run_capabilities.py` (model_overrides persisted) + `tests/unit/test_run_pipeline_validation.py` (override rejection) + `tests/agents/test_loader.py` (model field)
- [ ] Framework install: **none** — pytest stack already present.

---

## Manual-Only Verifications

All phase behaviors have automated verification. The model-switch fallback is proven with a scripted offline `BaseChatModel` (no live Bedrock); precedence, catalog, override-validation, and persistence are unit/integration tested; INV-3 parity is held by existing characterization snapshots.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
