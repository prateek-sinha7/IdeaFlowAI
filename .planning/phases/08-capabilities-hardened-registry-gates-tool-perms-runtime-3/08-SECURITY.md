---
phase: 08
slug: capabilities-hardened-registry-gates-tool-perms-runtime-3
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-10
---

# Phase 08 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

**Phase goal:** Formalize the capability registry + trust flags, make gates first-class (incl. a real `validation` gate), enforce least-privilege tool permissions, and lift the factory's hardcoded runtime/tools/prompt-order into adapters/registries/policy — at strict INV-3 parity.

**Verification mode:** `register_authored_at_plan_time: true` — all 8 PLAN.md files carried parseable `<threat_model>` blocks. Auditor ran in **verify-mitigations** mode (confirm declared mitigations exist; no new-threat scanning). Independently confirmed in tree `feature/003-workflow-engine-decoupling`; prior-review remediations (CR-01, WR-01..05, IN-03) verified present and load-bearing.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| manifest author (user/DB) → compiler | An untrusted user/DB manifest may reference any capability name | capability refs (untrusted) |
| capability module import → global registry | `@register` binds impls into a process-global singleton at import | capability bindings |
| step request → security gate | A step may request a privileged permission (exec/network/secrets) | permission request |
| capability → §18 audit tables | Gate/validation/hook firings write owner/workspace-scoped audit rows | owner_id + workspace_id scoped rows |
| AGENT.md grant → effective perms | An AGENT.md may attempt to raise a permission | permission set |
| step → ExecutionPolicy | A step may request exec/network/secrets | execution policy decision |
| kernel ↔ app heavy-dep validators | Validators live app-side; the kernel must not import app | port handle (legal direction) |
| kernel → deepagents runtime | `create_deep_agent` must stay behind the allow-listed adapter (INV-13) | runtime construction |
| DB Constitution store → composed prompt | A governing Constitution must inject in production (not silently dropped) | governance prompt text |
| write payload → secret_scan | A deliverable write may carry a secret | deliverable payload (sensitive) |
| OTel package install | A new external dependency enters the tree | supply-chain artifact |
| client → GET /api/capabilities | An unauthenticated client must not read the palette | capability palette (JWT-gated) |
| run stream → frontend panels | New events must not break the existing-workflow event contract | WS events (additive) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-08-01-EoP | Elevation of Privilege | compiler trust check (CAP-03) | mitigate | `compiler.py:186-211` `_check_trust` raises `CompilerError` under untrusted `user`/`db` when `user_allowed=False`; `_TRUSTED_SOURCES={file,builtin}`; privileged caps `user_allowed=False` (security/approval/runtime); exec/secrets/spawn default OFF (`plan.py:65-73`) | closed |
| T-08-01-T | Tampering | registry resolve() static lookup | mitigate | `registry.py:280-300` `resolve()` = static dict lookup over `_KNOWN`-validated names; `discover()` (`:162-245`) explicit enumerated `importlib.import_module` — no `pkgutil`/`eval`/`exec`/`__import__` | closed |
| T-08-01-arch | Tampering (architecture) | discover() importing app/validators | mitigate | `pyproject.toml:165-169` forbids `agents.capabilities → {execution_engine, app}`; validators import kernel PORT (legal direction); `lint-imports` KEPT | closed |
| T-08-01-SC | Tampering | npm/pip installs | accept | No backend dep added in 08-01; OTel gated to 08-07 behind a blocking human checkpoint | closed |
| T-08-02-EoP | Elevation of Privilege | security gate | mitigate | `security.py:35-72` default-denies exec/network/secrets → `GATE_BLOCK`; `user_allowed=False`; defaults OFF this phase | closed |
| T-08-02-ID | Information Disclosure | gate_events cross-owner read | mitigate | `authz.py:499-548` `record_gate_event`/`read_gate_events` stamp + scope owner_id/workspace_id via `_scope_owner_ws`; `gate_events` owner/ws `nullable=False` | closed |
| T-08-02-parity | Tampering (regression) | human gate re-route | mitigate | `human.py:51-81` delegates to unchanged `_run_review_gate` via `ctx.runner.run_human_gate`; characterization gate parity intact | closed |
| T-08-02-SC | Tampering | npm/pip installs | accept | No backend dep added in 08-02 | closed |
| T-08-03-EoP1 | Elevation of Privilege | over-privileged tool binding | mitigate | `plan.py:103-138` `intersect_permissions` = owner∩workflow∩step AND-mask (can only LOWER); bound at `compiler.py:310-323`; F2 switch deleted, registry-resolved (`factory.py:491-514`) | closed |
| T-08-03-EoP2 | Elevation of Privilege | exec/network/secrets accidental enable | mitigate | `plan.py:65-73` defaults OFF; `ExecutionPolicy.check` (`:172-193`) default-denies exec/network/secrets with no runtime host; exec OFF until N3/Phase 10 | closed |
| T-08-03-parity | Tampering (regression) | F2 switch replacement | mitigate | Provider registry reproduces byte-identical tool sets (`providers.py:56-112`); gated by 5 characterization snapshots + `test_create_runner` before deletion | closed |
| T-08-03-SC | Tampering | npm/pip installs | accept | No backend dep added in 08-03 | closed |
| T-08-04-arch | Tampering (architecture) | kernel reaching into app for heavy deps | mitigate | `app/agents/validators/__init__.py:14-29` imports kernel PORT; validators reach `static_check`/`render_check` via `target.runner` handle; `lint-imports` forbids `capabilities→app` (KEPT) | closed |
| T-08-04-ID | Information Disclosure | validation_results cross-owner read | mitigate | `authz.py:550-585` `record_validation_result` stamps owner/ws; validation gate builds real `DeliverableContext` (`validation.py:140-167`, WR-01) | closed |
| T-08-04-parity | Tampering (regression) | task_loop validation re-point | mitigate | Parity vs 5 snapshots; no re-baseline (suite green) | closed |
| T-08-04-SC | Tampering | npm/pip installs | accept | No backend dep added in 08-04 | closed |
| T-08-05-runtime | Tampering | hand-rolled deep agent / runtime swap | mitigate | `langchain_deepagents.py:38-70` WRAPS `create_deep_agent` via factory `build` seam (no app import); banned-pattern gate allow-lists single file `deep_agent_runner.py`; INV-13 (`test_banned_patterns` 11 pass) | closed |
| T-08-05-arch | Tampering (architecture) | runtime capability importing app | mitigate | Runtime reaches `DeepAgentRunner` via the handle, not a kernel→app import; `lint-imports` green | closed |
| T-08-05-parity | Tampering (regression) | F1/F3 prompt-assembly lift | mitigate | Prompt policy fixed block order `injects→guardrails→skills→hooks→constitution→body` (`policy.py:7,45`); byte parity vs 5 snapshots before deletion | closed |
| T-08-05-SC | Tampering | npm/pip installs | accept | No backend dep added in 08-05 | closed |
| T-08-06-R | Repudiation/Integrity | constitution silently dropped in prod | mitigate | `engine.py:687-700` pre-warms DB Constitution under running loop → `ectx.prewarmed_constitution`; `factory.py:316-342` reads it sync-safely (no await), fixing the R12 prod no-op; `test_constitution_prod.py` (3 pass) is the gate | closed |
| T-08-06-parity | Tampering (regression) | F4 fix changing existing snapshots | mitigate | Characterization runs carry no Constitution → empty string → snapshots byte-identical; test additive | closed |
| T-08-06-SC | Tampering | npm/pip installs | accept | No backend dep added in 08-06 | closed |
| T-08-07-ID | Information Disclosure | secret written to a deliverable | mitigate | **CR-01 remediation verified live:** `engine.py:1748-1758` fires declared `before_write` hooks over the payload BEFORE persist; `block`→`output=""`; `_fire_hooks:2174-2239` declaration-driven; `secret_scan.py:88-123` blocks + writes `hook_runs` row; exercised by `test_engine_fire_hooks_before_write_blocks_secret` | closed |
| T-08-07-EoP | Elevation of Privilege | over-privileged hook binding | mitigate | `hooks/base.py:69-95` `is_bound` gates on `required_permission` vs effective perms; git/exec OFF → unbound, never fires | closed |
| T-08-07-ID2 | Information Disclosure | hook_runs cross-owner read | mitigate | `authz.py:587-619` `record_hook_run` stamps owner/ws; `hook_runs` `nullable=False` | closed |
| T-08-07-SC | Tampering (supply chain) | opentelemetry-api/sdk install | mitigate | Blocking-human PyPI checkpoint (commit `2be056a`); `requirements.txt:61-62` `opentelemetry-api/sdk==1.42.1` (CNCF, human-verified); guarded import degrades to no-op (`otel_tracing.py:48-59,104-120`, WR-02); secret_scan imported first (`hooks/__init__.py:26-27`, IN-03) | closed |
| T-08-08-auth | Spoofing/Access Control | /api/capabilities | mitigate | `capabilities.py:90-93` `Depends(get_current_user)` (JWT); `dependencies.py` HTTPBearer + `decode_access_token` → `HTTP_401_UNAUTHORIZED` without a token | closed |
| T-08-08-ID | Information Disclosure | palette exposes privileged caps | mitigate | `capabilities.py:111-118` palette surfaces `user_allowed` per cap; privileged kinds (exec/secrets/spawn/runtimes) `user_allowed=False` | closed |
| T-08-08-parity | Tampering (regression) | new WS events | mitigate | `websocket.py:1431-1434` generic by-type forward; new `gate_*`/`validation_warning`/`validator_result` additive only (no rename/remove); existing event contract unchanged | closed |
| T-08-08-SC | Tampering | npm/pip installs | accept | No new backend dep in 08-08; frontend uses existing deps | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-08-01 | T-08-01-SC / T-08-02-SC / T-08-03-SC / T-08-04-SC / T-08-05-SC / T-08-06-SC / T-08-08-SC | These plan areas added **no backend dependency** — supply-chain exposure is nil for them. Git diff confirms the only runtime dependency added across the entire Phase 8 branch is `opentelemetry-api/sdk` (commit `94b77b3`, 08-07), which is the registered + mitigated + checkpoint-gated T-08-07-SC. | gsd-security-auditor (offline audit) | 2026-06-10 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-10 | 28 | 28 | 0 | gsd-security-auditor (opus) |

**Supporting gates (green at audit time):** `lint-imports` 3/3 contracts KEPT · `test_banned_patterns` 11 pass · targeted gate/hook/api/constitution/registry suite 107 pass · hook-firing subset 13 pass. Prior `08-REVIEW.md` (commit `9a92c0c`) confirmed the core security model sound (no trust bypass, intersection AND-only/can't-widen, security gate fail-closed, no IDOR, auth enforced); CR-01/WR-01..05/IN-03 remediations independently re-verified present and load-bearing.

---

## Auditor Notes (non-blocking, forward surface)

- **T-08-03-EoP1 nuance (Phase-9 carry-forward):** Two D-07 enforcement points (`ToolPermissions.lowered_by`, `ExecutionPolicy.check`, factory `_build_runner_tools` grant-gating) are honestly documented as *forward surface not wired this phase* (`plan.py:87-99,148-166`; `factory.py:468-478` — the WR-04/WR-05 honest-wording remediation). Acceptable for Phase 8: no privileged tool set exists, exec/network/secrets default OFF, the intersection collapses them OFF, and the `security` gate fail-closes — both ACTIVE. When the first privileged tool set / `LocalSandboxRuntime` lands (Phase 9), the grant-gating call sites must be wired and re-audited. Flagged for the Phase-9 threat model, **not a Phase-8 gap.**

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-10
