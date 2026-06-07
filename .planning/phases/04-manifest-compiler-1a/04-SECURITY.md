---
phase: 04
slug: manifest-compiler-1a
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-07
---

# Phase 04 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (all 5 PLAN.md carried `<threat_model>` blocks); verified retroactively against the implementation. Phase 4 is a declaration/routing + read-only-metadata phase — it introduces NO new auth surface, NO code-exec, NO secrets.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| repo file → manifest loader | `workflow.yaml` is repo-authored but parsed by code into typed dataclasses | untrusted-by-shape YAML |
| manifest data → compiler → registry | declared capability-name strings validated against a known set; nothing is executed | capability-name strings |
| run entry (WS / api / `_drive`) → engine | the legacy `pipeline_type` label crosses into the engine; id-alias resolver maps it to a known manifest id before any load | run-type label string |
| browser (JWT) → `/api/runs/*` | authenticated user requests their own run-history; cross-owner access must be denied | run records (owner-scoped) |
| browser (JWT) → `/api/workflows/{id}` | user-supplied manifest id path param crosses into the definitions router | manifest id (path param) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-04-01 | Tampering / EoP | capability name → registry | mitigate | `is_registered` is pure `(kind, name)` set-membership — no `eval`/`exec`/`getattr`/dynamic import (verified: 0 in `registry.py`); names map to nothing executable in 1A | closed |
| T-04-02 | Elevation of Privilege | trust/allow-list omission | accept | Trust flags / `user_allowed` / owner allow-list are explicitly Phase 8 (D-07); registering names only is the sanctioned 1A seam — no privilege decision made here | closed |
| T-04-03 | Tampering / EoP | YAML deserialization (`load_manifest`) | mitigate | `yaml.safe_load` only (verified ×4); 0 `yaml.load`/`FullLoader`/`Loader=` — no arbitrary-object construction RCE (ASVS V5) | closed |
| T-04-04 | Tampering | DSL/expression injection via top-level manifest keys | mitigate | `_ALLOWED_TOP_KEYS` strict-key rejection in `manifest.py` → `ManifestValidationError`; a `when:`/`if:`/`for:`/`${}` field has nowhere to live (INV-5 / D-08) | closed |
| T-04-05 | Information Disclosure | validation error message | accept | Error names the offending field/key only (repo-authored config) — no secret/PII surface; this is the required MAN-01 behavior | closed |
| T-04-06 | Tampering / EoP | DSL/expression injection into a manifest (compiler) | mitigate | Compiler does 0 `eval`/`exec`; `_ALLOWED_STEP_KEYS` + `_ALLOWED_TASK_SOURCE_KEYS` reject step-level DSL keys (CR-01 fix); 3 `test_rejects_*dsl*` guards (INV-5 / D-08) | closed |
| T-04-07 | Tampering | unregistered capability reference | mitigate | Every reference validated via `CapabilityRegistry.is_registered` (7 call sites in `compiler.py`); unknown → `CompilerError` naming the bad ref (INV-4 / MAN-03) | closed |
| T-04-08 | Spoofing | step-order drift vs. registry | mitigate | `test_manifest_coverage.py` asserts compiled step order equals `get_pipeline_agents(id)` — prevents a manifest silently reordering agents (precursor to INV-3 parity) | closed |
| T-04-09 | Tampering | manifest id resolution at run entry | mitigate | Resolver maps `pipeline_type` to a known manifest id (`_OD_ALIAS_BASE`/identity over the registered set); unknown id loads no manifest — never `open(base / arbitrary)` (no path traversal via run label) | closed |
| T-04-10 | Tampering / DoS | behavioral-line drift breaking the migration ledger | mitigate | Pinned L7/L10 lines stay byte-identical; `test_migration_ledger.py` (4 passed) + the routing structure test guard against edits/new branches | closed |
| T-04-11 | Repudiation / Integrity | silent behavior change vs. legacy | mitigate | Phase-0A characterization snapshots (deliverable byte + semantic-event multiset) green 10/10 — the blocking parity gate (INV-3) | closed |
| T-04-12 | EoP / Information Disclosure | IDOR on relocated `/api/runs/{id}` | mitigate | `.filter(WorkflowRun.user_id == current_user.id)` preserved on every relocated query (verified ×6: list/get/delete/chain-context/export-pptx); cross-user → 404 (ASVS V4); `test_runs_api.py` | closed |
| T-04-13 | Tampering | path traversal via `/api/workflows/{id}` | mitigate | `{id}` resolved against the in-memory known-manifest-id set; 404 on miss; 0 `open(base / id)` on unvalidated id in `workflows.py` (ASVS V5); `test_get_and_404` | closed |
| T-04-14 | Tampering | HTTP response splitting via export-pptx filename | mitigate | `re.sub(r"[^A-Za-z0-9._-]", "_", title)[:40]` carried over verbatim in the relocated handler (verified ×2 in `runs.py`); no regression of the original fix | closed |
| T-04-15 | Spoofing / EoP | auth weakening during relocation | mitigate | Both routers keep `Depends(get_current_user)` JWT (verified ×6 runs / ×3 workflows); API-key surface untouched (D-02: no external consumer) | closed |
| T-04-SC | Tampering (supply chain) | npm/pip/cargo installs | accept | Zero new packages phase-wide (`yaml` 6.0.3 + `python-frontmatter` 1.1.0 already installed; `typing.Protocol` stdlib; frontend repoint is string edits) — RESEARCH Package Legitimacy Audit | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-04-01 | T-04-02 | Capability trust flags / `user_allowed` / owner allow-list are scoped to Phase 8 (CAP-02/CAP-03) by design; 1A registers names only and makes no privilege decision | Phase plan (D-07) | 2026-06-07 |
| AR-04-02 | T-04-05 | Manifest validation errors name the offending field only (repo-authored config, no user/secret data) — required MAN-01 behavior, no disclosure surface | Phase plan | 2026-06-07 |
| AR-04-03 | T-04-SC | No new third-party packages introduced in this phase (all parsers pre-installed; stdlib Protocol; frontend string edits) | RESEARCH Package Legitimacy Audit | 2026-06-07 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-07 | 16 | 16 | 0 | gsd-secure-phase (orchestrator verification; corroborated by phase code-review + verifier) |

Method: register authored at plan time (5 `<threat_model>` blocks); each `mitigate` threat verified by direct source inspection of the implemented control (grep of the named pattern/file), triangulated against the phase code-review (which independently audited the IDOR filter, path-traversal 404, export-pptx sanitization, `safe_load`, and DSL rejection — and fixed the step-level DSL gap, CR-01) and the phase verifier (snapshots 10/10, migration-ledger green). `accept` threats documented in the Accepted Risks Log.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-07
