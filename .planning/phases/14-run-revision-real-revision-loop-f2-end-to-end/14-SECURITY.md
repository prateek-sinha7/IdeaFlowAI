---
phase: 14
slug: run-revision-real-revision-loop-f2-end-to-end
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-12
---

# Phase 14 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| manifest data → compiler → engine | file-trust manifests; `planner` key is engine control data | planner/clarify routing flags |
| FE WS frame → run_revision branch | untrusted client input (parent_run_id, target_artifact_type, instruction) | revision dispatch parameters |
| WS layer → engine | owner principal (user.id) threads as owner_id | run ownership principal |
| queue/task registries | per-run global maps (`_PIPELINE_QUEUES`/`_PIPELINE_TASKS`) shared across connections | live event streams |
| FE instruction → composed context → model prompt | untrusted user text now reaches a real model (it never did under the stub) | revision instruction + parent artifact content |
| revision run → parent run artifacts | cross-run read, owner-gated | parent deliverable/summary/planning_context refs |
| lineage write → artifact_refs | cross-tenant-sensitive persistence | exact-kind revision ref with derived_from |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-14-01-01 | Tampering | `planner: skip` removes the clarify gate for the two revision manifests | accept | Clarify questionnaire is UX, not a security control. Supporting claims VERIFIED in code: revision input still validated at WS ingress — `empty_revision_instruction` (websocket.py:916-922) and `missing_revision_params` (:923-929) fire before any dispatch; ownership still gated by `assert_owns` (engine.py:3721). File-trust manifests only — the flip is a one-key data edit in two repo-committed workflow.yaml files (`planner: skip` at ppt_revision/workflow.yaml:11 and od_ppt_revision/workflow.yaml:11); compiler trust ceiling for user/db manifests untouched. | closed |
| T-14-01-02 | Elevation | a future od revision agent declaring template/design_system injects would dispatch without template context | mitigate | `test_run_revision_revision_agents_declare_no_template_injects` exists (test_manifest_parity.py:112) and asserts `"template" not in spec.injects` (:141) and `"design_system" not in spec.injects` (:146) for every step agent of both `_RUN_REVISION_DISPATCHED` manifests (:42, :137). Confirmed none of the three revision agents declares an `injects` key (od-ppt-revision-agent / ppt-revision-agent / ppt-revision-assembler AGENT.md frontmatter). | closed |
| T-14-01-SC | Tampering | package installs | accept | No dependency-manifest changes (requirements/pyproject/lockfiles) in any phase-14 commit (`git log --name-only 22e10df0~1..HEAD` — zero matches). | closed |
| T-14-02-01 | Repudiation | failed revision recorded as completed, then offered as a revision parent by the FE `status === "completed"` lookup | mitigate | Terminal status derived from observed terminal events inside `_run_revision_to_queue`: `_queue_send` closure records `pipeline_complete_seen`/`pipeline_failed_seen`/`degraded_seen` from the forwarded stream (websocket.py:1898-1917); persist is keyed on those flags — completed iff clean complete (:1949-1955), ValueError → failed (:1956-1962), CancelledError → cancelled (:1963-1971), Exception → failed (:1972-1979); no path leaves "revising". Pinned by test_run_revision_ws_dispatch.py: scenario (b) `test_pipeline_failed_records_failed_not_completed` (:224), (c) :259, (d) :292, (f) `test_cancellation_lands_row_cancelled` (:366). Review fix WR-02 hardened further: degraded completions persist "degraded", never "completed" (:1904-1914; test :434). | closed |
| T-14-02-02 | Elevation | cross-owner revision via forged parent_run_id | mitigate (existing, preserved) | Ownership enforced in the engine: `ScopedStore(owner_id=owner_id)` then `await store.assert_owns(parent_run_id)` BEFORE any cross-run read (engine.py:3716-3721, T-5-SEED); `assert_owns` raises typed `PermissionError` on owner mismatch (authz.py:1198-1202). WS layer threads `owner_id=user.id` only (websocket.py:1944) — never a client-supplied principal. PermissionError surfaces through the broad-except as `revision_error` (websocket.py:1972-1979); no data crosses (`assert events == []` pinned at test_revision_intelligence.py:588/:1027). | closed |
| T-14-02-03 | Elevation | reconnect/live-attach to another owner's revision queue via `_PIPELINE_QUEUES` membership | mitigate (existing, preserved) | Live attach is owner-gated (12-05 CR-01, websocket.py:632-683): run row resolved FILTERED BY `WorkflowRun.owner_id == user.id` (:663-669), then re-resolved through the default-deny `ScopedStore.get_run` (:679-683); a miss demotes to the no-live-task path. Revision runs registered in `_PIPELINE_TASKS`/`_PIPELINE_QUEUES` (:1986-1987) are discoverable only through this same gated path — no new attach surface. | closed |
| T-14-02-04 | DoS | unbounded per-run queue while WS is slow/dead | accept | Identical to the existing run_pipeline pattern, VERIFIED: unbounded queue via `_get_or_create_queue` (websocket.py:1884), drainer exits on dead WS at both heartbeat (:2010-2017) and send failure (:2028-2036), `_cleanup_pipeline` in the bg task's finally (:1980-1983). Revision event volume is 1-2 single_shot agents — strictly smaller than existing pipelines. | closed |
| T-14-02-05 | Tampering | client-supplied target_artifact_type flows into agent_count derivation and section stamping | mitigate | `get_pipeline_agents` over the derived alias is a closed registry lookup — unknown alias → empty list → cosmetic `agent_count=len(_rev_agents) or 1` with no dispatch implication (websocket.py:1828-1835, :1875); `section` is echo-only display data stamped on the drainer wrapper (:2026). Unknown targets fail at the engine pre-dispatch guard: empty registry lookup raises ValueError before any spawn (engine.py:3832-3842) → `revision_validation_error`. | closed |
| T-14-02-SC | Tampering | package installs | accept | Same evidence as T-14-01-SC — no dependency-file changes in the phase commit range. | closed |
| T-14-03-01 | Elevation | IDOR: revise another owner's parent run | mitigate (existing, preserved byte-identical) | `await store.assert_owns(parent_run_id)` stays FIRST (engine.py:3721) — before all three FR-014 chain reads (:3741/:3744/:3755-3757) AND before the `self.execute` dispatch (:3882). Pinned by `test_cross_owner_revision_denied` (test_revision_intelligence.py:565, kept in 14-04) and `test_fe_target_cross_owner_still_denied_on_realistic_parent` (:1000), both asserting PermissionError with `events == []` (:588/:1027 — denial before any event). | closed |
| T-14-03-02 | Tampering | prompt injection via the revision instruction into the dispatched agents | accept (bounded) | Bounding claims VERIFIED: all three revision agents declare `tools: []` in AGENT.md frontmatter (no filesystem/exec/builtin tool grants — factory maps `[]` to `exclude_builtin=True`); dispatch passes `gate_agent_ids=[]` (engine.py:3890), which removes only an HITL pause (not an authority grant) and `od_context=None` (:3889); no new tool surface added. Same composed context the stub already built (:3789-3807) now reaches a model. | closed |
| T-14-03-03 | DoS | revisions now consume model tokens/runtime | mitigate | Dispatch rides `execute()`'s per-run enforcing `BudgetManager.from_limits(compiled.limits, ...)` (engine.py:932-946) with `budget_aborted` terminal handling (:1679-1696); `recursion_limit = settings.AGENT_RECURSION_LIMIT` backstop on every runner invoke (deep_agent_runner.py:314); revision pipelines are 1-2 single_shot steps; pre-dispatch ValueError rejects unmapped targets before any spawn (engine.py:3832-3842). | closed |
| T-14-03-04 | Tampering | unvalidated target_artifact_type reaching manifest loading | mitigate | Generic suffix transform (engine.py:3819-3821, data-only, SC-001) + `get_pipeline_agents` over the closed registry — empty → ValueError pre-dispatch (:3832-3842). `compile_for_run` is reached only AFTER the registry-membership gate passes (:3856 — the argument is by then a registered pipeline key, so no arbitrary string reaches `load_manifest`); `compile_for_run` itself resolves through the closed alias set (T-04-09, engine.py:222-229). Review fix CR-02 added a further planner-dispatchability gate: non-`planner: skip` manifests are rejected pre-dispatch (:3844-3862). | closed |
| T-14-03-05 | Repudiation | failed dispatch leaving a poisoned exact-kind lineage ref | mitigate | Lineage write guarded `if final_output and not terminal_failed:` (engine.py:3908) — `terminal_failed` set from observed `pipeline_failed` (:3895-3896), `final_output` captured only from `pipeline_complete` (:3893-3894); failure paths write nothing under the exact kind, so FR-014 chain link 1 stays clean. Run-row half covered by 14-02 terminal-status fidelity (T-14-02-01, incl. the WR-02 degraded mapping). | closed |
| T-14-03-06 | Information Disclosure | lineage ref leaking across tenants | mitigate (existing pattern) | Ref stamped `owner_id=owner_id`, `workspace_id=original.workspace_id`, `visibility="workspace"` (engine.py:3917-3936); persisted via the owner-scoped `store.write_ref` (:3937). Reads go through the default-deny ScopedStore owner+visibility filter: `_scope_with_visibility` requires `owner_id == caller` AND (own workspace OR workspace/public visibility) (authz.py:104-115), applied to `get_ref`/`list_refs` (:212-245) — cross-owner reads resolve nothing. | closed |
| T-14-03-SC | Tampering | package installs | accept | Same evidence as T-14-01-SC. | closed |
| T-14-04-01 | Elevation | regression cover for the ownership gates could be weakened by the test rewrite | mitigate | All ownership-gate tests present by name post-rewrite: `test_cross_owner_revision_denied` (test_revision_intelligence.py:565), `test_fe_target_cross_owner_still_denied_on_realistic_parent` (:1000), plus NEW `test_falsy_owner_raises` (:332, AUTHZ-03 — added by 14-04 because the engine guard at engine.py:3700-3703 was previously untested). Both cross-owner tests strengthened with `assert events == []` (:588/:1027) making "PermissionError BEFORE any event" executable. | closed |
| T-14-04-02 | Repudiation | losing the single-stamping regression trap | mitigate | `test_revision_run_events_persist_and_resolve_on_real_db` (test_revision_intelligence.py:602) asserts run_events from the execute() chokepoint with `seqs == list(range(1, len(seqs) + 1))` (:676-678 — contiguous, no duplicates; a reintroduced second counter fails it) and seq-ordered endpoint replay parity (:701-707). Sibling trap in test_run_revision_fe_contract.py:218-220 asserts contiguity over ALL forwarded events. | closed |
| T-14-04-SC | Tampering | package installs | accept | Same evidence as T-14-01-SC. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-14-01 | T-14-01-01 | Clarify questionnaire is UX, not a security control; revision input still WS-ingress-validated and ownership-gated (both verified in code); file-trust manifests only — compiler trust ceiling for user/db manifests unchanged | plan-time threat model (14-01-PLAN.md) | 2026-06-12 |
| AR-14-02 | T-14-02-04 | Unbounded per-run queue identical to the proven run_pipeline pattern (dead-WS drainer exit + cleanup verified); revision event volume strictly smaller than existing pipelines | plan-time threat model (14-02-PLAN.md) | 2026-06-12 |
| AR-14-03 | T-14-03-02 | Prompt injection bounded: revision agents are `tools: []` (no filesystem/exec grants — verified in all three AGENT.md frontmatters), surgical-edit prompts, no new tool surface; `gate_agent_ids=[]` removes only an HITL pause | plan-time threat model (14-03-PLAN.md) | 2026-06-12 |
| AR-14-04 | T-14-01-SC / T-14-02-SC / T-14-03-SC / T-14-04-SC | No packages installed in any phase-14 plan (verified: zero dependency-manifest/lockfile changes across the phase commit range) | plan-time threat models (all 4 PLANs) | 2026-06-12 |

*Accepted risks do not resurface in future audit runs.*

---

## Unregistered Flags

None. No `## Threat Flags` section exists in any of the four SUMMARYs. The post-plan review fixes found in the implementation (14-REVIEW CR-01 overlap-rejection guard websocket.py:888-910, WR-01 residual drain :2059-2084, WR-02 degraded-status mapping :1904-1914, WR-03 reconnect section preservation :647-676, CR-02 planner-dispatchability gate engine.py:3844-3862) are hardening additions mapping onto existing register entries (T-14-02-01, T-14-02-03, T-14-03-04) — informational, no new attack surface.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-12 | 19 | 19 | 0 | gsd-security-auditor (read-only static audit per offline-test convention; evidence: source verification of websocket.py / engine.py / authz.py / both workflow.yaml manifests / AGENT.md frontmatters + grep-pinned test presence in test_revision_intelligence.py (17 tests), test_run_revision_ws_dispatch.py (8 tests incl. WR scenarios), test_run_revision_fe_contract.py, test_manifest_parity.py; 14-04 phase-gate battery previously green: 226 passed, 7 skipped, lint-imports 4 kept) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-12
