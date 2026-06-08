---
phase: 06-model-policy-1c
audited: 2026-06-08
auditor: gsd-security-auditor
asvs_level: 1
block_on: high
register_authored_at_plan_time: true
threats_total: 14
threats_closed: 14
threats_open: 0
high_open: 0
status: SECURED
gates:
  import_linter: 3 kept / 0 broken
  banned_pattern: 8/8 passed
  characterization_parity: 10/10 unchanged
  proving_tests: 146 passed (catalog 9, resolver 25, run_pipeline_validation 50, run_capabilities 4, fallback 4, loader 44, banned 8, characterization 10 ... overlap)
---

# Phase 6 — Model Policy [1C] — Security Threat Verification

Verification of the plan-time threat register against the **implemented** code. Every
declared mitigation was located in source (grep + read) and, where a gate exists, the gate
was executed read-only to confirm effectiveness. Implementation files were not modified.

**Result: SECURED — 14/14 threats CLOSED, 0 OPEN, 0 HIGH open.**

## Threat Verification

| Threat ID | Category | Sev | Disposition | Evidence (file:line / gate) |
|-----------|----------|-----|-------------|------------------------------|
| T-06-01 | Tampering (kernel purity) | — | mitigate | No `app.*` import in `agents/capabilities/model_catalog.py` (grep: NONE). import-linter contract `agents.capabilities must not import the execution kernel or the web layer` = **KEPT** (3 kept / 0 broken). |
| T-06-02 | Info Disclosure/Integrity (INV-12 single list) | — | mitigate | `app/api/settings.py:46-54` `AVAILABLE_MODELS` and `:57` `_VALID_MODEL_IDS` are derived projections over `ModelCatalog().list()/.ids()`. The ONE hand-maintained model-id LIST is `model_catalog.py:50-101 _ENTRIES`. Other verbatim model-id occurrences (`config.py:63/70/75`, `model_factory.py:46`, `smart_planner.py:166`) are single-value Haiku **defaults**, not a second allow-list. `test_model_catalog.py` 9/9. |
| T-06-03 | Tampering (AGENT.md `model` field) | — | mitigate | `loader.py:368-374` string-or-null type guard → `AgentSpecError`. `model_policy.py:109-114 ModelResolver.resolve` validates `agent_model ∈ ModelCatalog.is_allowed` — and WR-01 fix confirmed: validation gated on `override is None and step_model is None and agent_model is not None` (fires only when tier-3 is the selected tier). `test_model_resolver.py` 25/25. |
| T-06-04 | Tampering/Elevation (INV-3 parity, no-override) | — | mitigate | Tier-5 default = `session_model_id or haiku_default` (`model_policy.py:103-104`); engine seeds `session_model_id=model_id` (`engine.py:1026`). Revision path uses the same `_resolve_model(ectx, spec, model_id)` (`engine.py:1328`). Characterization snapshots **10/10 unchanged**. |
| T-06-05 | Elevation (INV-13 deepagents-only) | — | mitigate | Resolved id → `AgentContext.model` (`engine.py:1623`) → `create_runner` → `build_model` only. `deep_agent_runner.py:53` canonical `from deepagents import create_deep_agent`; `:240` sole graph build. Banned-pattern gate **8/8**. |
| **T-06-06** | **Tampering/Elevation (model_overrides ingress)** | **HIGH** | **mitigate** | `_validate_model_overrides` (`websocket.py:53-113`) allow-list-validates `model_id ∈ ModelCatalog().ids()` (`:96,108`); rejects BEFORE `engine.execute` (`:1142-1151`, returns without creating a WorkflowRun) with `code="invalid_model_override"`. **CR-01 hardening present:** non-dict guard `:87-91`, non-string agent_id/model_id guard `:98-102`. Single ingress chokepoint (only call site `:1142`; `run_revision` carries no override field). `test_run_pipeline_validation.py` 50/50 incl. malformed-payload regressions. |
| T-06-07 | Tampering (override unknown agent_id) | MED | mitigate | `_validate_model_overrides` `:103-107` rejects `agent_id ∉ run_agent_ids` (the resolved `{spec.id for spec in agents}` set, `:1143`). |
| T-06-08 | Info Disclosure (cross-tenant override leak) | LOW | mitigate | `ScopedStore.record_capabilities` (`authz.py:~300`) stamps `owner_id=self._owner_id`, `workspace_id=self._workspace_id`; `RunCapabilities` model carries non-null `owner_id`+`workspace_id` (`run_capabilities.py:28-29`). Phase-5 default-deny scoped path; no new access path introduced. |
| T-06-09 | Tampering (INV-3 persisted-row parity) | — | mitigate | `engine.py:755` persists `model_overrides=(ectx.model_overrides or None)` so `{}`→SQL NULL — row-identical to legacy/no-override rows. `test_run_capabilities.py` 4/4. |
| T-06-10 | DoS/Repudiation (unbounded retry) | — | mitigate | Retry loop bounded by `_max_attempts = len(_chain)` (`engine.py:1724`); exhaustion (`_next_id is None or _attempt >= _max_attempts`, `:1812`) re-raises the last throttle (`:1819`) — no infinite retry, no silent success-mask. `test_model_fallback.py` 4/4. |
| T-06-11 | Tampering/Repudiation (mis-classified error swallowed) | — | mitigate | Only `_is_transient_throttle`-matched exceptions retry (`engine.py:1804` `if not _is_transient_throttle(_exc): raise`); runner re-raises ONLY transient throttles (`deep_agent_runner.py:461-471`), non-transient keep the `yield {"type":"error"}` swallow. Proving test `test_non_transient_propagates` (`test_model_fallback.py:258`) PASS. |
| T-06-12 | Elevation (INV-13 on fallback rebuild) | — | mitigate | Fallback rebuild via `create_runner` (`engine.py:1843-1848`) — no new `create_deep_agent`. Banned-pattern gate **8/8**. |
| T-06-13 | Tampering (INV-3 no-throttle path) | — | mitigate | Retry engages only on a re-raised throttle; the no-throttle first attempt consumes to completion and breaks after one pass (`engine.py:1791-1792`). Characterization **10/10 unchanged**. |
| T-06-SC | Tampering (supply chain) | — | **accept** | Phase 6 installs ZERO new packages. `requirements.txt`/`requirements-dev.txt`/`pyproject.toml` last modified Jun 3–7 (pre-phase-6, which is Jun 8); recent git log shows no dependency-manifest or `migrations/`/`alembic` change (only `.planning/REQUIREMENTS.md`, a planning doc). No new migration. **Accepted risk logged here.** |

## Accepted Risks Log

- **T-06-SC (supply chain)** — *accepted.* Phase 6 is pure application logic (resolver,
  fallback loop, override validation, catalog projection). No new pip/npm/cargo dependency
  and no new DB migration were introduced, so the package-install / migration attack surface
  is unchanged from Phase 5. Re-verify if a future sub-phase adds a dependency.

## Code-Review Cross-Check (06-REVIEW.md)

The HIGH-relevant review findings were confirmed fixed in source, not just documented:
- **CR-01** (malformed `model_overrides` silent task death) — isinstance guards present at
  `websocket.py:87-91` and `:98-102`. Closes the T-06-06 crash-not-reject hazard.
- **WR-01** (tier-3 precedence-inversion) — validation correctly deferred to the selected-tier
  branch (`model_policy.py:109-114`). Supports T-06-03.
- **CR-02** (fallback thread-id collision) — fresh `…:retry{n}` thread per attempt
  (`engine.py:1842`). Supports T-06-12 clean-restart intent. (Live-checkpointer behavior is a
  human-verify item per the verification report; the offline harness asserts the fresh thread.)
- **WR-03** (`reset_output: true` on `agent_model_fallback`) — present `engine.py:1861`.

## Unregistered Flags

None. No `## Threat Flags` section is present in any phase-6 `*-SUMMARY.md`, and no new
client-facing attack surface beyond the registered `model_overrides` ingress (T-06-06/07) was
observed. The override map enters from exactly one path (`run_pipeline` → `_handle_workflow_execution`
→ `_validate_model_overrides`) and is validated before any run state is created.

## Gates Executed (read-only)

- import-linter: **3 kept / 0 broken**
- banned-pattern (`test_banned_patterns.py`): **8 passed**
- characterization / INV-3 parity (5 files): **10 passed**
- proving suites (`test_model_catalog`, `test_model_resolver`, `test_run_pipeline_validation`,
  `test_run_capabilities`, `test_model_fallback`, `test_loader`): **all passed**

(The 8 pre-existing environmental failures in `test_logout.py` / `test_pipeline_cancel.py`
— "self-registration disabled" 403 — are unrelated to this phase and were not exercised.)

---

_Audited: 2026-06-08 — gsd-security-auditor — ASVS L1, block_on: high — verdict: SECURED._
