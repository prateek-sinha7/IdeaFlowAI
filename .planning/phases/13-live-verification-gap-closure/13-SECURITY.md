---
phase: 13
slug: live-verification-gap-closure
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-12
---

# Phase 13 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| WS client → approve_review handler | untrusted client supplies gate_key + approved flag | gate approval decisions (run-scoped) |
| gate capability → kernel | registered capability streams events into the dispatch loop | gate lifecycle events |
| model output → JSON edit-plan applier | untrusted LLM text parsed into file-edit operations | file-edit operations (path-validated) |
| prompt composition → model | engineer/user-attached blocks composed into the system prompt | static engineer-authored prompt text |
| AGENT.md files → composed system prompts | engineer-authored, file-trusted prompt content | version-controlled prompt bodies |
| workflow.yaml manifests → compiler | file-trusted engineer-authored manifest data | capability grants, deliverable blocks |
| WS client → run_revision ingress | untrusted parent_run_id + target_artifact_type + instruction | cross-run artifact references |
| revision flow → parent run artifacts | cross-run read of another run's persisted content | owner-scoped run artifacts |
| WS client → run_pipeline ingress | untrusted pipeline_type/template_id/agent_ids admission | run admission parameters |
| engine → WS client | failure detail (error strings, failed agent ids) emitted to the run owner | agent error strings (owner-only WS) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-13-01-01 | Elevation of privilege | approve_review (websocket.py) approving another user's gate | mitigate | REOPENED by 13-REVIEW CR-01 (plan-time accept rationale falsified: handler had no ownership check), re-closed 2026-06-12: `_review_gate_owned_by` (websocket.py:155-179) resolves the run from gate_key and requires the authenticated principal to own it; guard at :1006 (`continue` on deny) precedes the sole non-test `set_review_response` call site :1014 (grep: only store.py:89 def + websocket.py:1014); ownership keys on `WorkflowRun.user_id` (nullable=False, workflow.py:20; set at both WS creation sites :891/:1431) NOT the nullable Phase-5 `owner_id` backfill (workflow.py:55) the main creation path :1426-1441 leaves NULL; unknown and unowned runs are indistinguishable (single combined id+user_id filter :172-176; identical "Unknown gate_key"/invalid_gate_key error :1007-1012); regression suite tests/unit/test_approve_review_ownership.py 7/7 passed (owner-allowed with owner_id NULL, cross-user denied, unknown-run denied, 3× malformed-key denied, source-order pin guard-before-write) | closed |
| T-13-01-02 | Tampering | streamed gate events injected by a malicious capability | accept | capabilities are file-trusted engineer-authored code (CAP-03 gates user-trust manifests); streaming branch resolves gates from the same registry | closed |
| T-13-01-03 | Denial of service | a gate stream that never terminates blocking the run | accept | identical exposure to the previously awaited evaluate(); fix makes the human-wait VISIBLE (ready event reaches the UI), reducing the hang class | closed |
| T-13-02-01 | Tampering | _extract_json fallback grabbing a {...} span from polluted text | mitigate | `_FABRICATED_TOOL_XML_RE.sub("", raw)` applied first in `_extract_json` (backend/app/agents/handoff/coder.py:120,133) — strip only removes spans, never widens parser input; downstream `_safe_workspace_join` path-traversal validation (handoff_pipeline.py:165-189) untouched by phase 13; pinned by test_handoff_coder_hardening.py:128,137 | closed |
| T-13-02-02 | Denial of service | unbounded re-prompt loop on persistent parse failure | mitigate | `_MAX_PARSE_ATTEMPTS = 2` module constant (coder.py:151), bounded loop at :219, re-raise on final attempt :254-255; RuntimeError raised outside the retried except — never retried; pinned by test_two_bad_attempts_raise_after_exactly_two, test_runtime_error_event_is_never_retried | closed |
| T-13-02-03 | Spoofing / prompt injection | preamble block weakening user-attached skill/hook instructions | accept | preamble is static engineer-authored text containing no interpolated user input; constrains output FORM only | closed |
| T-13-02-04 | Denial of service | ReDoS via the XML-strip regex on adversarial output | mitigate | non-greedy linear `[\s\S]*?` span patterns, no nested quantifiers (coder.py:120; deep_agent_runner.py:114-116); inputs max_tokens-capped (coder 16000; runner settings.MAX_OUTPUT_TOKENS); pinned by test_text_only_prompt_hygiene.py (10/10) | closed |
| T-13-03-01 | Spoofing / prompt injection | prompt bodies interpolating user input | accept | AGENT.md bodies are static version-controlled engineer content; no user input interpolated; runtime user context flows through separate skills/hooks channels unchanged | closed |
| T-13-03-02 | Tampering | prompt edits silently changing agent tool grants | mitigate | byte-level frontmatter comparison across commits d905059b/02c68cb0/070ace5a and worktree: YAML frontmatter (incl. tools:) of all 9 modified AGENT.md files identical — only bodies changed; loader schema suite re-validates every agent (test_loader.py 44/44) | closed |
| T-13-04-01 | Elevation of privilege | sample_fanout grants spawn_subagents | accept | unchanged grant, file-trust only (CAP-03 rejects it from user/db manifests); plan touched only the deliverable block | closed |
| T-13-04-02 | Tampering | budget ceiling raise masking runaway live spend | accept | LIVE_BUDGET_USD is a soft evidence-run guardrail (opt-in RUN_LIVE_BEDROCK, never CI); 8.0 stays within ~35% of measured clean-sweep cost | closed |
| T-13-05-01 | Elevation of privilege / IDOR | fallback chain reading a parent run the caller does not own | mitigate | `await store.assert_owns(parent_run_id)` executes FIRST (engine.py:3511, T-5-SEED ordering), before all three fallback-chain `list_refs` links (:3531/:3534/:3537); cross-owner tests test_cross_owner_revision_denied (:336) + test_fe_target_cross_owner_still_denied_on_realistic_parent (:679) — PermissionError before any chain read | closed |
| T-13-05-02 | Tampering | attacker-supplied target_artifact_type as a kind filter | accept | value is only an equality filter on owner-scoped list_refs (parameterized, no interpolation) and a kind label on the revision's own ref — unchanged exposure with two fixed generic fallbacks | closed |
| T-13-05-03 | Information disclosure | deliverable ref visibility="workspace" exposing run output workspace-wide | accept | identical to existing producer/summary write policy (05-06 decision); deliverable content already flows to every workspace member via the run itself | closed |
| T-13-06-01 | Denial of service | malformed run_pipeline payloads forcing engine startup work | mitigate | ingress guard keyed on resolved specs' declared injects rejects with `missing_template_context` and returns (websocket.py:1331-1348) BEFORE WorkflowRun creation (:1370), title generation (:1413), engine.execute (:1448); engine-never-invoked asserted by test_pipeline_failure_semantics.py:326/:355/:389 | closed |
| T-13-06-02 | Information disclosure | pipeline_failed.error / agents_failed leaking internals | accept | events flow only on the owner's own authenticated WS connection; payload carries the same agent_error strings the client already receives per-agent | closed |
| T-13-06-03 | Tampering | degraded fields injected into clean-run payloads breaking FE assumptions | mitigate | degraded keys written only inside `if results and _failed_agent_ids:` (engine.py:1788-1790); failure set populated by pure observation of agent_error events (:1568-1574); clean-run key-set pinned by test_clean_run_payload_carries_no_degraded_keys; characterization byte-parity gated, zero golden re-baselines in phase range | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| ~~AR-13-01~~ | T-13-01-01 | WITHDRAWN 2026-06-12 — rationale falsified by 13-REVIEW CR-01 (handler performed no run-ownership check; "owner-scoped at ingress" did not hold for the approve_review write path). Disposition changed to mitigate; see threat register row. | 13-REVIEW CR-01 / re-audit | 2026-06-12 |
| AR-13-02 | T-13-01-02 | capabilities are file-trusted engineer-authored code; CAP-03 gates user-trust manifests | plan-time threat model (13-01-PLAN.md) | 2026-06-12 |
| AR-13-03 | T-13-01-03 | exposure identical to awaited evaluate(); fix makes the wait visible, reducing hang class | plan-time threat model (13-01-PLAN.md) | 2026-06-12 |
| AR-13-04 | T-13-02-03 | preamble is static engineer text, no interpolated user input, constrains output form only | plan-time threat model (13-02-PLAN.md) | 2026-06-12 |
| AR-13-05 | T-13-03-01 | AGENT.md bodies static + version-controlled; no user input interpolated | plan-time threat model (13-03-PLAN.md) | 2026-06-12 |
| AR-13-06 | T-13-04-01 | spawn_subagents grant unchanged, file-trust only; CAP-03 rejects from user/db manifests | plan-time threat model (13-04-PLAN.md) | 2026-06-12 |
| AR-13-07 | T-13-04-02 | LIVE_BUDGET_USD is soft, opt-in, never CI; ceiling within ~35% of measured cost | plan-time threat model (13-04-PLAN.md) | 2026-06-12 |
| AR-13-08 | T-13-05-02 | equality filter on owner-scoped list_refs, parameterized, no interpolation | plan-time threat model (13-05-PLAN.md) | 2026-06-12 |
| AR-13-09 | T-13-05-03 | identical to existing producer/summary write policy (05-06 decision) | plan-time threat model (13-05-PLAN.md) | 2026-06-12 |
| AR-13-10 | T-13-06-02 | events owner-WS-only; payload reuses agent_error strings client already receives | plan-time threat model (13-06-PLAN.md) | 2026-06-12 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-12 | 17 | 17 | 0 | gsd-security-auditor (read-only audit; evidence suites: test_handoff_coder_hardening 6 passed, test_loader 44 passed, test_revision_intelligence + test_run_revision_fe_contract 15 passed, test_pipeline_failure_semantics + test_run_pipeline_validation + test_characterization_prototype 58 passed, test_text_only_prompt_hygiene 10 passed) |
| 2026-06-12 (re-audit) | 1 (T-13-01-01, reopened by 13-REVIEW CR-01) | 1 | 0 | gsd-security-auditor (scoped re-audit; disposition accept→mitigate; evidence: websocket.py:155-179/:1006/:1014, workflow.py:20/:55, test_approve_review_ownership.py 7 passed in 0.25s) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-12
