---
phase: 15
slug: live-pass-prompt-contract-closure
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-13
---

# Phase 15 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register sources: `<threat_model>` blocks of 15-01-PLAN.md, 15-02-PLAN.md, 15-03-PLAN.md.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| AGENT.md body → composed system prompt → live LLM | engineer-authored static prompt content steers model output rendered by the FE | prompt text (low sensitivity, behavior-bearing) |
| AGENT.md frontmatter → loader → factory | frontmatter grants tools/ordering — a silent frontmatter edit changes runtime permissions | tool grants, pipeline routing |
| test code → engine drive | the LV-02 composition test executes the REAL engine offline with a scripted model — a test that patched gates or goldens could mask regressions | engine events, deliverable bytes |
| golden snapshots → INV-3 backward-compat guarantee | goldens are the byte-level contract; any re-baseline silently changes the guaranteed behavior | golden snapshot bytes |
| local driver → live AWS Bedrock | real cloud calls under existing SSO profiles; spend + account metadata exposure | AWS identity, token spend |
| live outputs → committed planning docs | evidence files are committed to the repo — must not leak credentials/account identifiers | run ids, deck HTML |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-15-01 | Tampering | AGENT.md frontmatter (tool grants/order) | mitigate | bodies-only edits proven: zero frontmatter-key `+/-` lines in commits cf5fb56b/3fff6879/dbcd88c8/aa33d5ea/e0cc2e84; durable freeze pin `test_contract_agents_frontmatter_frozen` (backend/tests/agents/test_prompt_contracts.py:230, `_FROZEN_FRONTMATTER` lines 156–226 pinning order/pipeline_type/tools/guardrails/context_from/max_tokens/injects/gate for all five agents — hardened from 3 to 8 fields by WR-03, commit 0557423f); `test_loader.py` green in gate | closed |
| T-15-02 | Spoofing | composed system prompt (prompt injection) | accept | bodies static, engineer-authored, version-controlled; phase-range diff (`e6530025..HEAD`) shows no user-input interpolation added — backend changes confined to five AGENT.md bodies + one test file; see Accepted Risks AR-15-01 | closed |
| T-15-03 | Tampering | resolver/capability files (`ppt.py`, `_artifact.py`) | mitigate | `git status --porcelain backend/agents/capabilities/ backend/agents/execution_engine/ factory.py loader.py registry.py` empty (audit re-run 2026-06-13); no capability/engine file in any phase commit stat or in the phase-range filelist | closed |
| T-15-04 | Tampering | test harness weakening security/regression gates | mitigate | additive-only proven: d4dc4861 creates test_prompt_contracts.py (1 file, 246 insertions); 0557423f/7b507ce7 touch only that file; `_scripted_model.py`/`live_harness.py`/`characterization/` porcelain empty; characterization suite ran unmodified in the gate (all 5 snapshot pipelines green within 99 passed) | closed |
| T-15-05 | Tampering | golden re-baseline (INV-3 violation) | mitigate | `SNAPSHOT_UPDATE` env count = 0 at audit gate run; `git status --porcelain tests/agents/characterization/golden/` = 0 lines; no golden file in the phase-range filelist; characterization tests pass byte-identical (audit re-run 2026-06-13) | closed |
| T-15-06 | Repudiation | gate evidence not reproducible | mitigate | single deterministic gate command recorded in 15-02-SUMMARY "Phase Gate Evidence"; independently re-run by this audit: **99 passed, 7 skipped in 35.75s** + lint-imports **4 kept / 0 broken** — matches the recorded 99 passed / 7 skipped / 4-kept evidence; per-task commit cadence present (10 commits) | closed |
| T-15-07 | Information disclosure | PHASE-15-RECHECK.md + saved live artifacts | mitigate | audit greps on PHASE-15-RECHECK.md + both phase15-od-ppt-*.html artifacts: 12-digit account-id pattern → no match; credential patterns (AKIA…, aws_secret, secret_access_key, session_token, sso.amazonaws, awsapps.com, Authorization: Bearer) → no match; record carries run ids, profile NAME + region only | closed |
| T-15-08 | Elevation of privilege | live Bedrock invocation | accept | existing SSO profiles only; `sts get-caller-identity` precheck recorded in 15-03-SUMMARY; actual spend $0.092 within ~$0.10 budget; no new IAM surface (zero backend changes by 15-03 — `git status --porcelain backend/` empty); see Accepted Risks AR-15-02 | closed |
| T-15-09 | Denial of service | quota/throttle burn from retry loops | mitigate | LIVE branch succeeded on first attempt (retry path unexercised); cost fence verifiably held: only 2 od_ppt artifacts exist under live-verification/artifacts/, F4/F5 dispositions = `NEXT-LIVE-PASS` (no app_builder live run); locked DEFERRED fallback documented in 15-03-PLAN + RECHECK conventions | closed |
| T-15-SC | Tampering | npm/pip/cargo installs (declared in all three plans) | accept | zero package installs proven: `git diff e6530025..HEAD` empty for requirements*.txt / pyproject.toml / package.json / package-lock.json / Cargo.toml; see Accepted Risks AR-15-03 | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-15-01 | T-15-02 | Prompt-injection surface unchanged: the five edited bodies are static, engineer-authored, version-controlled markdown; no user input is interpolated by this phase (mirrors 13-03 T-13-03-01). Review fixes WR-01/WR-02 (aa33d5ea, e0cc2e84) further hardened contract internal consistency. | Phase-15 plan (gsd) / security audit | 2026-06-13 |
| AR-15-02 | T-15-08 | Live Bedrock ran under pre-existing SSO profiles with sts precheck; bounded $0.092 spend (~$0.10 budget); no new IAM surface or credentials created. | Phase-15 plan (gsd) / security audit | 2026-06-13 |
| AR-15-03 | T-15-SC | Zero package installs across all three plans — supply-chain surface unchanged (verified: no dependency-manifest diff in the phase range). | Phase-15 plan (gsd) / security audit | 2026-06-13 |

*Accepted risks do not resurface in future audit runs.*

---

## Unregistered Flags

None. No `## Threat Flags` section exists in 15-01/15-02/15-03 SUMMARY files, and the phase-range filelist shows no new attack surface (backend changes = five prompt bodies + one additive test file).

Informational (mapped, not flags):
- 15-03-SUMMARY notes the live validator's pre-artifact commentary exceeded the contract's two-sentence cap (~1,046 chars). Adherence note on LV-02, not new attack surface — load-bearing clauses (exactly ONE artifact, complete deck, nothing after) held and resolution was correct.
- Review-fix commits map onto the register as hardening: WR-03 (0557423f) and WR-04 (7b507ce7) strengthen the T-15-01 freeze pin and the F4 anti-fabrication pins; WR-01 (aa33d5ea) / WR-02 (e0cc2e84) tighten prompt-contract consistency under AR-15-01.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-13 | 10 | 10 | 0 | gsd-security-auditor (Claude) |

Audit evidence (re-derived, not taken from documentation):
- Frontmatter integrity: grep over `git show` diffs of all five prompt commits for frontmatter-key `+/-` lines → empty.
- Fence porcelain: capabilities / execution_engine / factory / loader / registry / _scripted_model / live_harness / characterization → empty.
- Targeted gate re-run (offline, `python3.11`, no venv, `SNAPSHOT_UPDATE`=absent): 99 passed, 7 skipped; lint-imports 4 kept / 0 broken; golden porcelain 0 lines.
- Leak screens on committed live evidence: 12-digit + credential-pattern greps → no match.
- Supply chain: dependency-manifest diff over `e6530025..HEAD` → empty.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-13
